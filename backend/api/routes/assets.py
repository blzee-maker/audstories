from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..auth import require_user
from ..config import ALLOWED_AUDIO_EXT, MAX_UPLOAD_BYTES, PROJECTS_ROOT, SAFE_STEM
from ..deps import get_project_or_404
from ..schemas import RequirementItem, RequirementsResponse

router = APIRouter()


def _build_requirements(project_id: str) -> list[RequirementItem]:
    from asset_engine.contracts.draft_models import DraftTimeline
    from asset_engine.requirements import extract_requirements
    from asset_engine.utils.path_utils import make_asset_folder_name, make_voice_folder_name, resolve_asset_folder

    project_root = PROJECTS_ROOT / project_id
    out_dir = project_root / "output"
    assets_root = project_root / "assets"
    draft_path = out_dir / "draft_timeline.json"
    if not draft_path.is_file():
        return []
    with draft_path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    requirements = extract_requirements(DraftTimeline(**payload))
    items: list[RequirementItem] = []
    for req in requirements:
        kind = str(req.asset_kind)
        if kind == "voice":
            scene_folder = make_voice_folder_name(req.scene_index, req.scene_name, req.track_id)
            folder_name = f"{scene_folder}/clip_{req.clip_index:03d}"
        else:
            folder_name = make_asset_folder_name(req.scene_index, req.scene_name, req.descriptor)
        folder = resolve_asset_folder(assets_root, kind, folder_name)
        has_audio = any(p.suffix.lower() in ALLOWED_AUDIO_EXT for p in folder.glob("*"))
        items.append(
            RequirementItem(
                requirement_id=req.requirement_id,
                asset_kind=kind,
                descriptor=req.descriptor,
                tts_text=req.tts_text,
                scene_index=req.scene_index,
                clip_index=req.clip_index,
                folder=str(folder),
                status="ready" if has_audio else "missing",
            )
        )
    return items


def _first_audio_file(folder: Path) -> Path | None:
    if not folder.is_dir():
        return None
    for candidate in sorted(folder.iterdir()):
        if candidate.is_file() and candidate.suffix.lower() in ALLOWED_AUDIO_EXT:
            return candidate
    return None


def _pacing_overrides_path(project_id: str) -> Path:
    return PROJECTS_ROOT / project_id / "output" / "pacing_overrides.json"


def _load_json_dict(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _estimate_scene_voice_duration(scene_reqs: list, default_silence: float) -> float:
    if not scene_reqs:
        return 0.0
    previous_end = 0.0
    last_offset = 0.0
    last_duration = 0.0
    last_post = 0.0
    ordered = sorted(scene_reqs, key=lambda r: ((r.sequence if r.sequence is not None else 10_000), r.clip_index))
    for req in ordered:
        gap = req.gap_ms / 1000.0 if req.gap_ms else default_silence
        pre = max(0.0, float(getattr(req, "pre_silence_s", 0.0) or 0.0))
        post = max(0.0, float(getattr(req, "post_silence_s", 0.0) or 0.0))
        gap_component = 0.0 if pre > 0 else gap
        intent = req.timing_intent or "after_previous_voice"
        if intent in {"scene_start", "with_scene_start"}:
            offset = pre
        else:
            offset = previous_end + pre + gap_component
        duration = float(req.resolved_duration_seconds or req.estimated_duration_seconds or 1.0)
        previous_end = offset + duration + post
        last_offset = offset
        last_duration = duration
        last_post = post
    return round(last_offset + last_duration + last_post, 3)


def _classify_scene_floor(scene_idx: int, total: int, voice_reqs: list, scene_energy: float) -> str:
    if scene_idx == 0:
        return "opening"
    if scene_idx == total - 1:
        return "closing"
    if len(voice_reqs) <= 1 and scene_energy <= 0.35:
        return "transition"
    return "standard"


def _build_pacing_payload(project_id: str) -> dict:
    from asset_engine.contracts.draft_models import DraftTimeline
    from asset_engine.pacing.rule_engine import SCENE_DURATION_FLOOR, apply_pacing
    from asset_engine.requirements import extract_requirements

    project_root = PROJECTS_ROOT / project_id
    draft_path = project_root / "output" / "draft_timeline.json"
    if not draft_path.is_file():
        return {"project_id": project_id, "scenes": [], "overrides": {"clips": {}}}

    draft_payload = _load_json_dict(draft_path)
    if not draft_payload:
        return {"project_id": project_id, "scenes": [], "overrides": {"clips": {}}}

    draft = DraftTimeline(**draft_payload)
    requirements = extract_requirements(draft)

    overrides_path = _pacing_overrides_path(project_id)
    overrides = _load_json_dict(overrides_path)

    gita_payload = _load_json_dict(project_root / "gita.json")
    audio_cfg = gita_payload.get("audio") if isinstance(gita_payload, dict) else None
    gita_pacing = audio_cfg.get("pacing") if isinstance(audio_cfg, dict) else None
    gita_pacing = gita_pacing if isinstance(gita_pacing, dict) else None

    apply_pacing(requirements, draft, overrides=overrides, gita_pacing=gita_pacing)

    default_silence = float(draft.settings.get("default_silence", 0.5))
    scene_reqs_map: dict[str, list] = {}
    for req in requirements:
        if str(req.asset_kind) != "voice":
            continue
        scene_reqs_map.setdefault(req.scene_id, []).append(req)

    scenes = []
    total_scenes = len(draft.scenes)
    for idx, scene in enumerate(draft.scenes):
        voice_reqs = scene_reqs_map.get(scene.id, [])
        floor_kind = _classify_scene_floor(idx, total_scenes, voice_reqs, scene.energy)
        floor_s = float(SCENE_DURATION_FLOOR.get(floor_kind, SCENE_DURATION_FLOOR.get("standard", 6.0)))
        current_duration = _estimate_scene_voice_duration(voice_reqs, default_silence)
        clips = []
        for req in sorted(voice_reqs, key=lambda r: ((r.sequence if r.sequence is not None else 10_000), r.clip_index)):
            clips.append({
                "requirement_id": req.requirement_id,
                "speaker": req.track_id,
                "line_text": req.tts_text or req.descriptor,
                "dramatic_function": req.dramatic_function,
                "pre_silence_s": round(float(req.pre_silence_s or 0.0), 3),
                "post_silence_s": round(float(req.post_silence_s or 0.0), 3),
            })
        scenes.append({
            "scene_id": scene.id,
            "scene_name": scene.name,
            "floor_kind": floor_kind,
            "floor_s": floor_s,
            "estimated_duration_s": current_duration,
            "clips": clips,
        })

    return {
        "project_id": project_id,
        "scenes": scenes,
        "overrides": overrides if isinstance(overrides, dict) else {"clips": {}},
    }


@router.get("/api/projects/{project_id}/requirements", response_model=RequirementsResponse)
def requirements(project_id: str, user_id: str = Depends(require_user)) -> RequirementsResponse:
    project = get_project_or_404(project_id, user_id)
    items = _build_requirements(project_id)
    return RequirementsResponse(project_id=project_id, status=project["status"], items=items)


@router.get("/api/projects/{project_id}/pacing")
def pacing(project_id: str, user_id: str = Depends(require_user)) -> dict:
    _ = get_project_or_404(project_id, user_id)
    return _build_pacing_payload(project_id)


@router.post("/api/projects/{project_id}/pacing")
def save_pacing(
    project_id: str,
    payload: dict = Body(...),
    user_id: str = Depends(require_user),
) -> dict:
    _ = get_project_or_404(project_id, user_id)
    incoming_clips = payload.get("clips") if isinstance(payload, dict) else None
    if not isinstance(incoming_clips, dict):
        raise HTTPException(status_code=400, detail="Payload must include a clips object")

    path = _pacing_overrides_path(project_id)
    existing = _load_json_dict(path)
    merged = {"clips": dict(existing.get("clips", {})) if isinstance(existing.get("clips"), dict) else {}}

    for req_id, values in incoming_clips.items():
        if not isinstance(req_id, str) or not isinstance(values, dict):
            continue
        target = dict(merged["clips"].get(req_id, {})) if isinstance(merged["clips"].get(req_id), dict) else {}
        if values.get("pre_silence_s") is not None:
            target["pre_silence_s"] = max(0.0, float(values["pre_silence_s"]))
        if values.get("post_silence_s") is not None:
            target["post_silence_s"] = max(0.0, float(values["post_silence_s"]))
        merged["clips"][req_id] = target

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    return {"ok": True, "overrides": merged}


@router.get("/api/projects/{project_id}/requirements/{requirement_id}/audio")
def requirement_audio(project_id: str, requirement_id: str, user_id: str = Depends(require_user)) -> FileResponse:
    _ = get_project_or_404(project_id, user_id)
    items = _build_requirements(project_id)
    req = next((item for item in items if item.requirement_id == requirement_id), None)
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")
    audio_file = _first_audio_file(Path(req.folder))
    if not audio_file:
        raise HTTPException(status_code=404, detail="Audio not available for this requirement")
    media_type = f"audio/{audio_file.suffix.lower().lstrip('.')}" if audio_file.suffix else "audio/wav"
    return FileResponse(str(audio_file), media_type=media_type, filename=audio_file.name)


@router.post("/api/projects/{project_id}/assets")
async def upload_asset(
    project_id: str,
    requirement_folder: str = Form(...),
    file: UploadFile = File(...),
    user_id: str = Depends(require_user),
) -> dict:
    _ = get_project_or_404(project_id, user_id)
    project_assets_root = (PROJECTS_ROOT / project_id / "assets").resolve()
    folder = Path(requirement_folder).resolve()
    if not str(folder).startswith(str(project_assets_root)):
        raise HTTPException(status_code=400, detail="Invalid requirement folder")
    safe_name = SAFE_STEM.sub("_", Path(file.filename or "upload.wav").name)
    safe_name = safe_name.strip("._-") or "upload.wav"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / safe_name
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 50 MB limit")
    target.write_bytes(content)
    return {"status": "ready", "path": str(target)}


@router.post("/api/projects/{project_id}/assets/remove")
def remove_asset(
    project_id: str,
    requirement_folder: str = Form(...),
    user_id: str = Depends(require_user),
) -> dict:
    _ = get_project_or_404(project_id, user_id)
    project_assets_root = (PROJECTS_ROOT / project_id / "assets").resolve()
    folder = Path(requirement_folder).resolve()
    if not str(folder).startswith(str(project_assets_root)):
        raise HTTPException(status_code=400, detail="Invalid requirement folder")
    if not folder.is_dir():
        return {"removed": 0, "folder": str(folder)}
    removed = 0
    for candidate in folder.iterdir():
        if candidate.is_file() and candidate.suffix.lower() in ALLOWED_AUDIO_EXT:
            candidate.unlink(missing_ok=True)
            removed += 1
    return {"removed": removed, "folder": str(folder)}
