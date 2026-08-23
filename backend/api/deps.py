from __future__ import annotations

from fastapi import HTTPException

from .config import REPO_ROOT, STATE_FILE
from .state_store import StateStore
from .worker import PipelineWorker

# Process-wide singletons. Creating the worker starts its background thread
# and runs restart recovery, so this must happen exactly once at import time.
store = StateStore(STATE_FILE)
worker = PipelineWorker(repo_root=REPO_ROOT, state_store=store)


def get_project_or_404(project_id: str, user_id: str) -> dict:
    project = store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return project
