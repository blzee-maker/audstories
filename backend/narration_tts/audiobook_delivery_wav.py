"""Apply ``delivery_presets/audiobook_retail.json`` mastering to raw TTS WAVs (e.g. credits).

Resamples to project sample rate, LUFS toward ``target_lufs``, then peak ceiling.
(Output padding from the preset is **not** applied here—chapter renders get padding
in the audio engine; credits are short bumpers and may be re-run without stacking silence.)
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _ensure_audio_engine_on_path(repo_root: Path) -> None:
    ae = repo_root / "audio_engine"
    if str(ae.resolve()) not in sys.path:
        sys.path.insert(0, str(ae.resolve()))


def apply_audiobook_retail_to_wav(wav_path: Path, *, repo_root: Path) -> None:
    """Read *wav_path*, apply retail preset, write back in place."""
    preset_path = repo_root / "delivery_presets" / "audiobook_retail.json"
    if not preset_path.is_file():
        raise FileNotFoundError(f"Missing delivery preset: {preset_path}")

    raw = json.loads(preset_path.read_text(encoding="utf-8"))
    project = raw.get("project") or {}
    settings = raw.get("settings") or {}
    target_sr = int(project.get("sample_rate", 48000))
    peak_dbfs = float(settings.get("peak_target_dbfs", -3.0))
    target_lufs = float(settings.get("target_lufs", -20.0))

    _ensure_audio_engine_on_path(repo_root)
    from pydub import AudioSegment

    from audio_engine.dsp.loudness import apply_lufs_target
    from audio_engine.dsp.normalization import normalize_peak

    seg = AudioSegment.from_wav(str(wav_path))
    if seg.frame_rate != target_sr:
        seg = seg.set_frame_rate(target_sr)

    try:
        seg = apply_lufs_target(seg, target_lufs)
    except Exception as exc:
        logger.warning("LUFS step skipped for %s: %s", wav_path, exc)

    seg = normalize_peak(seg, peak_dbfs)
    seg.export(str(wav_path), format="wav")
