"""List Gemini models that can produce audio (TTS), for the configured API key.

Use this to confirm a valid GEMINI_TTS_MODEL id for your account:

    python -m narration_tts.list_tts_models

Reads GEMINI_API_KEY from the environment (or c:\\AS\\.env). Prints every model
whose supported output includes audio, plus whether the id currently set in
GEMINI_TTS_MODEL (or the code default) is among them.
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

from narration_tts.google_tts import _tts_model


def main() -> int:
    load_dotenv()  # picks up .env in cwd / repo root if present
    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        print("GEMINI_API_KEY is not set. Fill it into .env first.", file=sys.stderr)
        return 1

    try:
        from google import genai
    except ImportError:
        print(
            "google-genai not installed. Run: python -m pip install -r narration_tts/requirements.txt",
            file=sys.stderr,
        )
        return 1

    client = genai.Client(api_key=key)

    tts_models: list[str] = []
    for model in client.models.list():
        actions = getattr(model, "supported_actions", None) or []
        outputs = getattr(model, "output_token_limit", None)  # noqa: F841 - kept for clarity
        name = getattr(model, "name", "") or ""
        # TTS models expose audio output; the SDK surfaces this differently across
        # versions, so match on the conventional id suffix as a reliable fallback.
        is_tts = "tts" in name.lower() or "audio" in [str(a).lower() for a in actions]
        if is_tts:
            tts_models.append(name.replace("models/", ""))

    if not tts_models:
        print("No TTS-capable models reported for this key.")
        print("Check that your key has access to Gemini TTS in AI Studio.")
        return 2

    current = _tts_model()
    print("TTS-capable models for this key:")
    for m in sorted(set(tts_models)):
        marker = "  <- current default" if m == current else ""
        print(f"  {m}{marker}")

    if current not in tts_models:
        print()
        print(f"WARNING: configured model '{current}' is NOT in the list above.")
        print("Set GEMINI_TTS_MODEL in .env to one of the ids listed.")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
