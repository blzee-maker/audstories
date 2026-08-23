from __future__ import annotations

import json
import subprocess

from fastapi import APIRouter, Depends, Form, HTTPException

from ..auth import require_user
from ..config import PROJECTS_ROOT, REPO_ROOT
from ..deps import get_project_or_404, worker
from ..rate_limit import pipeline_limiter, rate_limited, tts_limiter
from ..schemas import JobResponse

router = APIRouter()


def _run_drama_cli_json(project_id: str, extra_args: list[str]) -> dict:
    cmd = [
        "python",
        "drama_cli.py",
        "--projects-root",
        str(PROJECTS_ROOT),
        *extra_args,
        "--project-id",
        project_id,
        "--json",
    ]
    result = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "drama_cli command failed").strip()
        raise HTTPException(status_code=400, detail=message)
    try:
        return json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to parse drama_cli JSON output: {exc}",
        ) from exc


@router.post("/api/projects/{project_id}/run-stage1", response_model=JobResponse)
def run_stage1(project_id: str, user_id: str = Depends(rate_limited(pipeline_limiter))) -> JobResponse:
    project = get_project_or_404(project_id, user_id)
    job_id = worker.enqueue(project_id=project_id, action="stage1", unit_slug=project["active_unit_slug"])
    return JobResponse(job_id=job_id, project_id=project_id, status="queued")


@router.post("/api/projects/{project_id}/run-stage2", response_model=JobResponse)
def run_stage2(project_id: str, user_id: str = Depends(rate_limited(pipeline_limiter))) -> JobResponse:
    project = get_project_or_404(project_id, user_id)
    job_id = worker.enqueue(project_id=project_id, action="stage2", unit_slug=project["active_unit_slug"])
    return JobResponse(job_id=job_id, project_id=project_id, status="queued")


@router.get("/api/projects/{project_id}/voice-map")
def voice_map(project_id: str, user_id: str = Depends(require_user)) -> dict:
    _ = get_project_or_404(project_id, user_id)
    return _run_drama_cli_json(project_id, ["voice-map"])


@router.post("/api/projects/{project_id}/tts-generate")
def tts_generate(
    project_id: str,
    character: str | None = Form(default=None),
    regenerate: bool = Form(default=False),
    user_id: str = Depends(rate_limited(tts_limiter)),
) -> dict:
    _ = get_project_or_404(project_id, user_id)
    args = ["tts-generate"]
    if character:
        args.extend(["--character", character])
    if regenerate:
        args.append("--regenerate")
    return _run_drama_cli_json(project_id, args)


@router.post("/api/projects/{project_id}/run-credits", response_model=JobResponse)
def run_credits(project_id: str, user_id: str = Depends(rate_limited(pipeline_limiter))) -> JobResponse:
    project = get_project_or_404(project_id, user_id)
    if project.get("format") != "book":
        raise HTTPException(status_code=400, detail="Credits are only available for audiobook projects")
    job_id = worker.enqueue(project_id=project_id, action="credits", unit_slug=project["active_unit_slug"])
    return JobResponse(job_id=job_id, project_id=project_id, status="queued")
