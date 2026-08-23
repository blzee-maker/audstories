"""
Integration test: compare streaming render vs legacy render output.
"""

import json
import os
import tempfile
from pathlib import Path

import numpy as np
from pydub import AudioSegment

from audio_engine.renderer import TimelineRenderer


def _load_samples(audio: AudioSegment) -> np.ndarray:
    samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
    if audio.channels > 1:
        samples = samples.reshape((-1, audio.channels))
    return samples


def _make_paths_absolute(timeline: dict, repo_root: Path) -> None:
    for track in timeline.get("tracks", []):
        for clip in track.get("clips", []):
            file_path = clip.get("file")
            if file_path and not os.path.isabs(file_path):
                clip["file"] = str(repo_root / file_path)


def test_streaming_vs_legacy():
    renderer = TimelineRenderer()

    repo_root = Path(__file__).resolve().parents[1]
    with open(repo_root / "tests" / "test_gain.json", "r", encoding="utf-8") as f:
        timeline = json.load(f)
    _make_paths_absolute(timeline, repo_root)

    timeline["project"]["duration"] = 6
    timeline["settings"]["loudness"] = {"enabled": False}
    # Parity test targets the chunked mixer; default master tail fade is covered elsewhere.
    timeline["settings"]["master_fade_out"] = {"enabled": False}
    timeline["settings"]["streaming"] = {
        "enabled": True,
        "chunk_size_sec": 1.0,
        "max_workers": 2,
        "two_pass_lufs": False,
        "sample_rate": 48000,
        "channels": 2,
        "sample_width": 2,
    }

    with tempfile.TemporaryDirectory() as tmp_dir:
        timeline_path = os.path.join(tmp_dir, "timeline.json")
        legacy_path = os.path.join(tmp_dir, "legacy.wav")
        streaming_path = os.path.join(tmp_dir, "streaming.wav")

        with open(timeline_path, "w", encoding="utf-8") as f:
            json.dump(timeline, f)

        renderer.render(timeline_path, legacy_path)
        renderer.render_streaming(timeline_path, streaming_path)

        legacy = AudioSegment.from_file(legacy_path)
        streaming = AudioSegment.from_file(streaming_path)

        assert abs(len(legacy) - len(streaming)) <= 5
        assert abs(legacy.dBFS - streaming.dBFS) <= 1.0

        legacy_samples = _load_samples(legacy)
        streaming_samples = _load_samples(streaming)
        min_len = min(len(legacy_samples), len(streaming_samples))
        diff = legacy_samples[:min_len] - streaming_samples[:min_len]
        max_val = float(2 ** (8 * legacy.sample_width - 1))
        mean_abs_err = float(np.mean(np.abs(diff)) / max_val)
        assert mean_abs_err < 0.02


if __name__ == "__main__":
    test_streaming_vs_legacy()
    print("✓ Streaming vs legacy render comparison passed")
