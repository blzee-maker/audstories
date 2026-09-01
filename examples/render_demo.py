#!/usr/bin/env python3
"""Render a short audio clip with no API keys and no accounts.

    python examples/render_demo.py

This exercises the audio engine end to end — timeline parsing, gain staging,
fades and master loudness normalisation — using the one audio fixture committed
to this repository. It needs FFmpeg on PATH and the project's dependencies
installed (`./setup.sh`, `.\\setup.ps1`, or the Docker image), but no Gemini key
and no Supabase project.

It is the fastest way to confirm your install actually works.

Note on paths: the renderer resolves each clip's "file" against the *current
working directory*, not against the timeline file. This script therefore changes
into backend/audio_engine/ before rendering, so you can run it from anywhere.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_DIR = REPO_ROOT / "backend" / "audio_engine"
FIXTURE = "audio/music/Days.mp3"  # relative to ENGINE_DIR — see the note above

# A deliberately small timeline: one music clip, shaped by the engine's gain,
# fade and loudness stages so the output audibly differs from the source.
TIMELINE = {
    # duration matches the 30s fixture: a shorter project still renders, but the
    # validator warns that the clip overruns it, which is noise on a first run.
    "project": {"name": "AudStories render demo", "duration": 30},
    "settings": {
        "master_gain": -1,
        "master_fade_out": {"enabled": True, "duration": 2.0, "curve": "logarithmic"},
    },
    "tracks": [
        {
            "id": "music",
            "type": "music",
            "gain": -2,
            "clips": [
                {
                    "file": FIXTURE,
                    "start": 0.0,
                    "gain": 0,
                    "fade_in": {"duration": 1.5, "curve": "exponential"},
                }
            ],
        }
    ],
}


def main() -> int:
    if not ENGINE_DIR.is_dir():
        print(f"error: expected the audio engine at {ENGINE_DIR}", file=sys.stderr)
        return 1

    fixture_path = ENGINE_DIR / FIXTURE
    if not fixture_path.is_file():
        print(f"error: missing audio fixture {fixture_path}", file=sys.stderr)
        return 1

    out_dir = REPO_ROOT / "examples" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "render_demo.wav"

    previous_cwd = Path.cwd()
    os.chdir(ENGINE_DIR)
    try:
        from audio_engine.renderer import TimelineRenderer

        # The renderer takes a path, not a dict, so hand it a temporary file.
        with tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8"
        ) as handle:
            json.dump(TIMELINE, handle)
            timeline_path = handle.name

        try:
            print(f"rendering  {fixture_path.name}  ->  {out_path}")
            TimelineRenderer().render(timeline_path=timeline_path, output_path=str(out_path))
        finally:
            os.unlink(timeline_path)
    except ImportError as exc:
        print(
            f"error: could not import the audio engine ({exc}).\n"
            "The in-repo packages must be editable-installed — run ./setup.sh or "
            ".\\setup.ps1, or use the Docker image.",
            file=sys.stderr,
        )
        return 1
    finally:
        os.chdir(previous_cwd)

    if not out_path.is_file():
        print("error: the renderer reported success but wrote no file", file=sys.stderr)
        return 1

    size_kb = out_path.stat().st_size / 1024
    print(f"\ndone: {out_path}  ({size_kb:,.0f} KB)")
    print("Play it to confirm your install works.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
