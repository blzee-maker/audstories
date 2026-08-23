"""Manual smoke test for Gemini Flash TTS — requires GEMINI_API_KEY.

Install: pip install -r narration_tts/requirements.txt
Run from repo root::

    python narration_tts/tests/manual_gemini_tts_smoke.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_ASSET_SRC = _ROOT / "asset_engine" / "src"
if str(_ASSET_SRC) not in sys.path:
    sys.path.insert(0, str(_ASSET_SRC))

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

from narration_tts.google_tts import synthesize_text_to_linear16_wav


def main() -> None:
    if not os.environ.get("GEMINI_API_KEY"):
        print(
            "Set GEMINI_API_KEY in the environment or narration_tts/tests/.env",
            file=sys.stderr,
        )
        sys.exit(1)
    out = Path(__file__).resolve().parent / "sample_gemini_tts.wav"
    text = "Hello. This is a short narration sample for the audiobook pipeline."
    synthesize_text_to_linear16_wav(text, out)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
