"""
Parity test: modern TimelineRenderer.render() vs deprecated legacy_renderer.render_timeline().

Tolerances (per AUDIO_ENGINE_WORKPLAN.md HIGH-3):
  - Duration:  abs(modern - legacy) < 0.1 seconds
  - Loudness:  abs(modern_lufs - legacy_lufs) < 0.5 dB
"""
import json
import os
import tempfile
from pathlib import Path

import pytest
from pydub import AudioSegment

from audio_engine.renderer import TimelineRenderer
from audio_engine.legacy_renderer import render_timeline as legacy_render_timeline
from audio_engine.streaming.loudness import measure_lufs_from_file


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "tests" / "test_gain.json"


def _make_paths_absolute(timeline: dict) -> None:
    for track in timeline.get("tracks", []):
        for clip in track.get("clips", []):
            file_path = clip.get("file")
            if file_path and not os.path.isabs(file_path):
                clip["file"] = str(REPO_ROOT / file_path)


def test_legacy_parity():
    with open(FIXTURE, "r", encoding="utf-8") as f:
        timeline = json.load(f)

    _make_paths_absolute(timeline)

    # Disable loudness normalisation so both paths produce raw comparable output.
    timeline["settings"]["loudness"] = {"enabled": False}

    with tempfile.TemporaryDirectory() as tmp:
        timeline_path = os.path.join(tmp, "timeline.json")
        modern_path = os.path.join(tmp, "modern.wav")
        legacy_path = os.path.join(tmp, "legacy.wav")

        with open(timeline_path, "w", encoding="utf-8") as f:
            json.dump(timeline, f)

        # Modern render
        TimelineRenderer().render(timeline_path, modern_path)

        # Legacy render — must emit DeprecationWarning
        with pytest.warns(DeprecationWarning, match="render_timeline is deprecated"):
            legacy_render_timeline(timeline_path, legacy_path)

        modern = AudioSegment.from_file(modern_path)
        legacy = AudioSegment.from_file(legacy_path)

        # Duration parity: within 100 ms
        modern_dur = len(modern) / 1000.0
        legacy_dur = len(legacy) / 1000.0
        assert abs(modern_dur - legacy_dur) < 0.1, (
            f"Duration mismatch: modern={modern_dur:.3f}s legacy={legacy_dur:.3f}s "
            f"(delta={abs(modern_dur - legacy_dur):.3f}s, tolerance=0.1s)"
        )

        # Loudness parity: within 0.5 dB LUFS
        modern_lufs = measure_lufs_from_file(modern_path)
        legacy_lufs = measure_lufs_from_file(legacy_path)
        assert abs(modern_lufs - legacy_lufs) < 0.5, (
            f"Loudness mismatch: modern={modern_lufs:.2f} LUFS legacy={legacy_lufs:.2f} LUFS "
            f"(delta={abs(modern_lufs - legacy_lufs):.2f} dB, tolerance=0.5 dB)"
        )
