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


# --- Development-only auth bypass ---------------------------------------------
# Every route is authenticated against Supabase, which means evaluating this
# project normally requires creating a Supabase project first. AS_DEV_NO_AUTH
# lets someone run the whole pipeline locally before deciding to do that.
#
# The API itself needs Supabase ONLY for auth - projects and jobs live in the
# local SQLite store - so disabling auth leaves a fully functional pipeline.
#
# This is a loaded footgun, so it is fenced: it refuses to activate if any CORS
# origin is non-local, which is the best available signal that the process is
# serving something other than the developer's own machine. The check runs at
# import time so a misconfigured deployment fails at startup rather than silently
# serving unauthenticated requests.
DEV_NO_AUTH_USER_ID = "dev-local-user"

_TRUTHY = {"1", "true", "yes", "on"}
_LOCAL_HOSTS = ("localhost", "127.0.0.1", "[::1]", "0.0.0.0")


def _is_local_origin(origin: str) -> bool:
    host = origin.split("://", 1)[-1].split("/", 1)[0]
    host = host.rsplit(":", 1)[0] if host.count(":") == 1 else host
    return host in _LOCAL_HOSTS


def dev_no_auth_enabled() -> bool:
    """True when the auth bypass is requested AND safe to honour."""
    if (os.environ.get("AS_DEV_NO_AUTH") or "").strip().lower() not in _TRUTHY:
        return False
    remote = [o for o in cors_origins() if not _is_local_origin(o)]
    if remote:
        raise RuntimeError(
            "AS_DEV_NO_AUTH is set, but CORS_ORIGINS contains non-local origins: "
            f"{', '.join(remote)}. The auth bypass is for local development only "
            "and will not be enabled for a deployment that serves remote origins. "
            "Unset AS_DEV_NO_AUTH, or restrict CORS_ORIGINS to localhost."
        )
    return True


# Evaluate once at import so misconfiguration is a startup failure.
DEV_NO_AUTH = dev_no_auth_enabled()
