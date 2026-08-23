"""Pytest fixtures for the api package.

Redirects the workspace to a throwaway temp directory *before* the app is
imported, so tests never read from or write to the real ``workspace/``. This
runs at conftest import time, which pytest evaluates before collecting the
test modules that import ``api.main`` (and therefore ``api.config``).
"""

from __future__ import annotations

import os
import tempfile

# setdefault: respect an explicit override if the caller already set one.
os.environ.setdefault("AS_WORKSPACE_DIR", tempfile.mkdtemp(prefix="as-test-workspace-"))
