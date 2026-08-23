"""
Loudness utilities for streaming renders.
"""

from typing import List

import numpy as np
from pydub import AudioSegment
import pyloudnorm as pyln

from audio_engine.dsp.loudness import measure_integrated_lufs


def measure_lufs_from_file(path: str) -> float:
    audio = AudioSegment.from_file(path)
    return measure_integrated_lufs(audio)


def compute_lufs_gain_db(
    current_lufs: float,
    target_lufs: float,
    max_boost_db: float = 6.0,
    max_cut_db: float = 10.0,
) -> float:
    gain_db = target_lufs - current_lufs
    if gain_db > max_boost_db:
        gain_db = max_boost_db
    elif gain_db < -max_cut_db:
        gain_db = -max_cut_db
    return gain_db


class StreamingLoudnessEstimator:
    """
    Estimate integrated LUFS using rolling short-term measurements.
    """

    def __init__(self, sample_rate: int, target_lufs: float, block_size: float = 0.4):
        self.meter = pyln.Meter(sample_rate, block_size=block_size)
        self.measurements: List[float] = []
        self.target_lufs = target_lufs

    def process_chunk(self, samples: np.ndarray) -> None:
        if samples.size == 0:
            return
        loudness = self.meter.integrated_loudness(samples)
        self.measurements.append(loudness)

    def get_estimated_gain_db(self) -> float:
        if not self.measurements:
            return 0.0
        estimated_lufs = float(np.mean(self.measurements))
        return compute_lufs_gain_db(estimated_lufs, self.target_lufs)


def compute_peak_gain_db(max_abs: float, target_dbfs: float) -> float:
    """
    Compute gain needed to reach target peak dBFS from a max absolute sample value.
    """
    if max_abs <= 0.0:
        return 0.0
    current_dbfs = 20.0 * float(np.log10(max_abs))
    return target_dbfs - current_dbfs


class StreamingPeakEstimator:
    """
    Track max peak across chunks for streaming peak normalization.
    """

    def __init__(self) -> None:
        self.max_abs = 0.0

    def process_chunk(self, samples: np.ndarray) -> None:
        if samples.size == 0:
            return
        max_abs = float(np.max(np.abs(samples)))
        if max_abs > self.max_abs:
            self.max_abs = max_abs