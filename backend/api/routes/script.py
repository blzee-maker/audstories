from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException

from ..auth import require_user
from ..deps import get_project_or_404
from ..schemas import ScriptPreviewRequest, ScriptPreviewResponse

router = APIRouter()


def _build_script_preview(project_id: str, script_text: str) -> ScriptPreviewResponse:
    from story_processing.fountain.to_plan import process_script_bundle

    plan_bytes, ast = process_script_bundle(script_text, project_type="audio_drama")
    plan = json.loads(plan_bytes.decode("utf-8"))
    scenes_out = []
    for idx, scene in enumerate(plan.get("scenes", [])):
        structure = scene.get("structure", {})
        interpretation = scene.get("interpretation", {})
        sfx_labels = []
        for item in structure.get("sfx_events", []):
            if isinstance(item, dict):
                label = str(item.get("sfx_label", "")).strip()
                if label:
                    sfx_labels.append(label)
        ambience_labels: list[str] = []
        cue = structure.get("ambience_cue")
        if isinstance(cue, dict):
            primary = str(cue.get("primary_atmosphere", "")).strip()
            desc = str(cue.get("atmosphere_description", "")).strip()
            if primary:
                ambience_labels.append(primary)
            if desc:
                ambience_labels.extend([x.strip() for x in desc.split(",") if x.strip()])
        scenes_out.append(
            {
                "scene_index": idx,
                "heading": str(structure.get("scene_title") or f"Scene {idx + 1}"),
                "speakers": [str(x) for x in structure.get("speakers", []) if str(x).strip()],
                "sfx": sorted(set(sfx_labels)),
                "ambience": sorted(set(ambience_labels)),
                "energy_level": int(interpretation.get("energy_level", 5)),
                "primary_emotion": str(interpretation.get("primary_emotion", "neutral")),
            }
        )

    diagnostics = [
        {
            "line": d.line,
            "column": d.column,
            "code": d.code,
            "severity": d.severity,
            "message": d.message,
        }
        for d in ast.diagnostics
    ]
    return ScriptPreviewResponse(project_id=project_id, diagnostics=diagnostics, scenes=scenes_out)


@router.post("/api/projects/{project_id}/script/preview", response_model=ScriptPreviewResponse)
def preview_script(
    project_id: str,
    payload: ScriptPreviewRequest,
    user_id: str = Depends(require_user),
) -> ScriptPreviewResponse:
    project = get_project_or_404(project_id, user_id)
    if project.get("format") != "drama":
        raise HTTPException(status_code=400, detail="Script preview is available for drama projects only")
    text = (payload.story_text or project.get("story_text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="No script text provided")
    try:
        return _build_script_preview(project_id, text)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Preview parse failed: {exc}") from exc
