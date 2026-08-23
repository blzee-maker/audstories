from __future__ import annotations

import json
import wave
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from ..auth import require_user
from ..config import PROJECTS_ROOT, SAFE_STEM
from ..deps import get_project_or_404
from ..schemas import CreditsItem, CreditsResponse, OutputResponse

router = APIRouter()


def _credits_files(project_id: str) -> dict[str, Path]:
    generated = PROJECTS_ROOT / project_id / "output" / "generated"
    return {
        "opening": generated / "opening_credits.wav",
        "ending": generated / "ending_credits.wav",
    }


def _build_credits_response(project_id: str, status: str) -> CreditsResponse:
    files = _credits_files(project_id)
    items: list[CreditsItem] = []
    for slot, filename in (("opening", "opening_credits.wav"), ("ending", "ending_credits.wav")):
        path = files[slot]
        available = path.is_file() and path.stat().st_size > 0
        items.append(
            CreditsItem(
                slot=slot,  # type: ignore[arg-type]
                filename=filename,
                available=available,
                url=f"/api/projects/{project_id}/credits/{slot}/file" if available else None,
            )
        )
    return CreditsResponse(
        project_id=project_id,
        status=status,  # type: ignore[arg-type]
        items=items,
    )


def _sanitize_output_stem(value: str) -> str:
    cleaned = SAFE_STEM.sub("_", value.strip())
    cleaned = cleaned.strip("._-")
    return cleaned or "final"


def _chapter_output_stem_from_metadata(meta: dict, unit_id: str | None, unit_name: str | None) -> str | None:
    chapters = meta.get("chapters")
    active_slug = str(meta.get("active_chapter_slug", "")).strip()
    wanted_slug = (unit_id or "").strip() or active_slug
    if isinstance(chapters, list) and chapters:
        for chapter in chapters:
            if not isinstance(chapter, dict):
                continue
            if wanted_slug and str(chapter.get("slug", "")).strip() == wanted_slug:
                title = str(chapter.get("title") or chapter.get("slug") or "").strip()
                if title:
                    return _sanitize_output_stem(title)
        first = chapters[0]
        if isinstance(first, dict):
            title = str(first.get("title") or first.get("slug") or "").strip()
            if title:
                return _sanitize_output_stem(title)
    fallback_title = (unit_name or "").strip() or str(meta.get("chapter_title") or meta.get("chapter_slug") or "").strip()
    return _sanitize_output_stem(fallback_title) if fallback_title else None


def _select_output_wav(project_id: str, project: dict, unit_id: str | None, unit_name: str | None = None) -> Path | None:
    generated = PROJECTS_ROOT / project_id / "output" / "generated"
    wavs = [p for p in generated.glob("*.wav")] if generated.is_dir() else []
    if not wavs:
        return None

    eff_uid = (unit_id or "").strip() or str(project.get("active_unit_slug", "")).strip()
    eff_uname = (unit_name or "").strip()
    # Frontend placeholder when router state is missing — do not override real titles for stem lookup.
    if eff_uname.lower() in {"", "episode", "chapter"}:
        eff_uname = str(project.get("active_unit_name", "")).strip()

    meta_path = PROJECTS_ROOT / project_id / "book_metadata.json"
    meta: dict = {}
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            meta = {}

    # Book + audio drama both write mixes to output/generated/<chapter_stem>.wav (see drama_cli docs).
    stem = _chapter_output_stem_from_metadata(
        meta,
        unit_id=eff_uid,
        unit_name=eff_uname,
    )
    if stem:
        for wav in wavs:
            if wav.stem == stem:
                return wav

    story_wavs = [w for w in wavs if w.stem not in {"opening_credits", "ending_credits"}]
    if story_wavs:
        return max(story_wavs, key=lambda p: p.stat().st_mtime)

    return max(wavs, key=lambda p: p.stat().st_mtime)


def _wav_duration_seconds(path: Path) -> float | None:
    if not path.is_file():
        return None
    try:
        with wave.open(str(path), "rb") as wav_file:
            frame_rate = wav_file.getframerate()
            frame_count = wav_file.getnframes()
            if frame_rate <= 0:
                return None
            return round(frame_count / float(frame_rate), 3)
    except (wave.Error, OSError):
        return None


@router.get("/api/projects/{project_id}/output", response_model=OutputResponse)
def output(
    project_id: str,
    unit_id: str | None = None,
    unit_name: str | None = None,
    user_id: str = Depends(require_user),
) -> OutputResponse:
    project = get_project_or_404(project_id, user_id)
    selected = _select_output_wav(project_id, project, unit_id=unit_id, unit_name=unit_name)
    params: dict[str, str] = {}
    if unit_id:
        params["unit_id"] = unit_id
    if unit_name:
        params["unit_name"] = unit_name
    suffix = f"?{urlencode(params)}" if params else ""
    url = f"/api/projects/{project_id}/output/file{suffix}" if selected else None
    duration_seconds = _wav_duration_seconds(selected) if selected else None
    return OutputResponse(
        project_id=project_id,
        status=project.get("status", "failed"),
        url=url,
        filename=selected.name if selected else None,
        duration_seconds=duration_seconds,
    )


@router.get("/api/projects/{project_id}/credits", response_model=CreditsResponse)
def credits(project_id: str, user_id: str = Depends(require_user)) -> CreditsResponse:
    project = get_project_or_404(project_id, user_id)
    return _build_credits_response(project_id, project.get("status", "failed"))


@router.get("/api/projects/{project_id}/credits/{slot}/file")
def credits_file(project_id: str, slot: str, user_id: str = Depends(require_user)) -> FileResponse:
    _ = get_project_or_404(project_id, user_id)
    if slot not in {"opening", "ending"}:
        raise HTTPException(status_code=404, detail="Credits slot not found")
    files = _credits_files(project_id)
    path = files[slot]
    if not path.is_file() or path.stat().st_size == 0:
        raise HTTPException(status_code=404, detail="Credits audio not available")
    return FileResponse(str(path), media_type="audio/wav", filename=path.name)


@router.get("/api/projects/{project_id}/output/file")
def output_file(
    project_id: str,
    unit_id: str | None = None,
    unit_name: str | None = None,
    user_id: str = Depends(require_user),
) -> FileResponse:
    project = get_project_or_404(project_id, user_id)
    selected = _select_output_wav(project_id, project, unit_id=unit_id, unit_name=unit_name)
    if not selected:
        raise HTTPException(status_code=404, detail="Output not available")
    return FileResponse(str(selected), media_type="audio/wav", filename=selected.name)
