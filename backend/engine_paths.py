"""Single source of truth for making the in-repo engines importable.

WHY THIS EXISTS (read before "simplifying" it away)
---------------------------------------------------
The engine packages live in sibling directories whose names COLLIDE with the
package names they contain:

    asset_engine/                         <- plain directory, NO __init__.py
    asset_engine/src/asset_engine/...     <- the real `asset_engine` package
    audio_engine/                         <- plain directory, NO __init__.py
    audio_engine/audio_engine/...         <- the real `audio_engine` package

When a process runs from the repo root, the repo root is on sys.path, so a bare
`import asset_engine` resolves to the EMPTY shadow directory (its __file__ is
None) and `from asset_engine.contracts import ...` then fails. Inserting the
real source roots at the FRONT of sys.path makes the genuine packages win.

`pip install -e` is NOT sufficient on its own: an editable install does not
out-prioritise the cwd shadow directory when running from the repo root
(verified with audio_engine, which is installed editable yet still resolves to
its empty shadow from the repo root). Truly removing this shim would require
renaming the colliding directories — a larger structural change.

All entry points (the API in api/config.py and the book/drama/run CLIs) call
ensure_engine_paths() so import resolution is identical everywhere.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

# Inserted at the front of sys.path. Order in this tuple is intentional: the
# loop uses insert(0), so the LAST entry here ends up first. asset_engine/src
# must precede the repo root (and cwd) so the real package beats the shadow dir.
_ENGINE_SRC_ROOTS = (
    REPO_ROOT,                                       # narration_tts + top-level CLIs
    REPO_ROOT / "asset_engine" / "src",              # the real asset_engine package
    REPO_ROOT / "pcddj_engine" / "story-to-script",  # story_processing, dsl, cli
)


def ensure_engine_paths() -> None:
    """Put the engine source roots at the front of sys.path. Idempotent."""
    for root in _ENGINE_SRC_ROOTS:
        entry = str(root)
        if root.exists() and entry not in sys.path:
            sys.path.insert(0, entry)
