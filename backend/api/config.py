from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB
# Workspace location is overridable via AS_WORKSPACE_DIR (used to isolate tests
# from the real workspace, and to relocate runtime state in deployments).
WORKSPACE_DIR = Path(os.environ.get("AS_WORKSPACE_DIR") or (REPO_ROOT / "workspace"))
PROJECTS_ROOT = WORKSPACE_DIR / "projects"
STATE_FILE = WORKSPACE_DIR / "api_state.db"

# Engines are imported lazily inside request handlers; make their source roots
# importable at process start so those deferred imports resolve. The shim lives
# in engine_paths.py at the repo root (see that file for why it is required).
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from engine_paths import ensure_engine_paths  # noqa: E402 — needs REPO_ROOT on path first

ensure_engine_paths()

SAFE_STEM = re.compile(r"[^A-Za-z0-9._-]+")
ALLOWED_AUDIO_EXT = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}


def cors_origins() -> list[str]:
    origins = [o.strip() for o in (os.environ.get("CORS_ORIGINS") or "").split(",") if o.strip()]
    if not origins:
        origins = [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
        ]
    return origins
