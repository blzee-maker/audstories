from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import PROJECTS_ROOT, cors_origins  # noqa: F401 — PROJECTS_ROOT re-exported for tests/back-compat
from .deps import store, worker  # noqa: F401 — re-exported for tests/back-compat
from .routes import assets, output, pipeline, projects, script

app = FastAPI(title="AS FastAPI bridge", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Each router owns one slice of the API surface; see api/routes/.
app.include_router(projects.router)
app.include_router(script.router)
app.include_router(assets.router)
app.include_router(pipeline.router)
app.include_router(output.router)
