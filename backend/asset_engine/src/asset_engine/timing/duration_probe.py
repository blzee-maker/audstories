"""Audio duration utilities."""

from __future__ import annotations

from pathlib import Path

import soundfile as sf


def probe_duration_seconds(file_path: str | Path) -> float:
    """Return media duration in seconds.

    Uses soundfile (libsndfile) which supports PCM, IEEE-float, and other WAV
    sub-formats, as well as FLAC, OGG, etc.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")

    try:
        info = sf.info(str(path))
        if info.samplerate <= 0:
            return 0.0
        return info.duration
    except RuntimeError as exc:
        raise ValueError(f"Cannot read audio duration for {path}: {exc}") from exc

