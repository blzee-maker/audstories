"""Put repo root and asset_engine on sys.path for narration_tts tests."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_ASSET_SRC = _ROOT / "asset_engine" / "src"
if str(_ASSET_SRC) not in sys.path:
    sys.path.insert(0, str(_ASSET_SRC))
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
