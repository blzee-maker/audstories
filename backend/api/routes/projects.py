from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from ..auth import require_user
from ..config import PROJECTS_ROOT
from ..deps import get_project_or_404, store
from ..schemas import (
    CreateProjectRequest,
    CreateProjectResponse,
    SaveStoryRequest,
    StatusResponse,
)

router = APIRouter()


def _ensure_book_metadata(project: dict) -> Path:
    project_root = PROJECTS_ROOT / project["id"]
    chapter_slug = project["active_unit_slug"]
    chapter_title = project["active_unit_name"]
    is_drama = project.get("format") == "drama"
    chapter_file = f"chapters/{chapter_slug}.fountain" if is_drama else f"chapters/{chapter_slug}.txt"
    payload = {
        "book_title": project["name"],
        "project_id": project["id"],
        "writer_name": project.get("writer_name", ""),
        "project_type": "audiobook" if project.get("format") == "book" else "audio_drama",
        "narration_only": project.get("format") == "book",
        "delivery_profile": "audiobook_retail" if project.get("format") == "book" else "audio_drama_default",
        "chapters": [{"title": chapter_title, "slug": chapter_slug, "file": chapter_file}],
        "active_chapter_slug": chapter_slug,
        "chapter_title": chapter_title,
        "chapter_slug": chapter_slug,
        "chapter_file": chapter_file,
        "credits": {"tts_provider": "google"},
    }
    project_root.mkdir(parents=True, exist_ok=True)
    chapter_path = project_root / chapter_file
    chapter_path.parent.mkdir(parents=True, exist_ok=True)
    chapter_path.write_text(project.get("story_text", ""), encoding="utf-8")
    metadata_path = project_root / "book_metadata.json"
    metadata_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return metadata_path


@router.post("/api/projects", response_model=CreateProjectResponse)
def create_project(payload: CreateProjectRequest, user_id: str = Depends(require_user)) -> CreateProjectResponse:
    existing = store.get_project(payload.project_id)
    if existing and existing.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Project ID already belongs to another user")
    project = store.create_or_update_project(
        payload.project_id,
        {
            "id": payload.project_id,
            "unit_id": payload.unit_id,
            "name": payload.name,
            "active_unit_name": payload.unit_name,
            "active_unit_slug": payload.unit_id,
            "writer_name": payload.writer_name,
            "format": payload.format,
            "narration_choice": payload.narration_choice,
            "ai_voice_provider": payload.ai_voice_provider,
            "status": "queued",
            "user_id": user_id,
            "story_text": "",
            "active_job_id": None,
            "error": None,
        },
    )
    _ensure_book_metadata(project)
    return CreateProjectResponse(
        id=project["id"],
        unit_id=project["unit_id"],
        status=project["status"],
        narration_choice=project["narration_choice"],
        ai_voice_provider=project["ai_voice_provider"],
    )


@router.post("/api/projects/{project_id}/story")
def save_story(project_id: str, payload: SaveStoryRequest, user_id: str = Depends(require_user)) -> dict:
    project = get_project_or_404(project_id, user_id)
    project = store.update_project(
        project["id"],
        unit_id=payload.unit_id,
        active_unit_slug=payload.unit_id,
        active_unit_name=payload.unit_name or project.get("active_unit_name", payload.unit_id),
        story_text=payload.story_text,
    )
    _ensure_book_metadata(project)
    return {"ok": True}


@router.get("/api/projects/{project_id}/status", response_model=StatusResponse)
def status(project_id: str, user_id: str = Depends(require_user)) -> StatusResponse:
    project = get_project_or_404(project_id, user_id)
    return StatusResponse(
        project_id=project_id,
        status=project["status"],
        active_job_id=project.get("active_job_id"),
        error=project.get("error"),
    )
