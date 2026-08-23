"""
ChunkLoader: load audio slices on-demand without loading full files.
"""

from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
from pydub import AudioSegment
from pydub.utils import mediainfo

from audio_engine.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class AudioMeta:
    duration_sec: float
    sample_rate: int
    channels: int
    sample_width: int


class ChunkLoader:
    """
    Load audio in chunks using ffmpeg-backed AudioSegment slicing.
    """

    def __init__(self, file_path: str):
        self.file_path = file_path
        self._meta_cache: Optional[AudioMeta] = None

    def _probe_metadata(self) -> AudioMeta:
        if self._meta_cache is not None:
            return self._meta_cache

        info = mediainfo(self.file_path)
        try:
            duration_sec = float(info.get("duration", 0.0))
        except (TypeError, ValueError):
            duration_sec = 0.0

        # Read a tiny slice to infer audio format (sample rate, channels, width)
        probe = AudioSegment.from_file(self.file_path, duration=0.01)
        self._meta_cache = AudioMeta(
            duration_sec=duration_sec,
            sample_rate=probe.frame_rate,
            channels=probe.channels,
            sample_width=probe.sample_width,
        )
        return self._meta_cache

    def get_metadata(self) -> AudioMeta:
        return self._probe_metadata()

    def get_chunk(
        self,
        start_sec: float,
        duration_sec: float,
        target_sample_rate: Optional[int] = None,
        target_channels: Optional[int] = None,
        target_sample_width: Optional[int] = None,
    ) -> Tuple[np.ndarray, AudioMeta]:
        """
        Load only the requested portion of audio.

        Returns:
            (samples, meta) where samples is float32 normalized [-1, 1]
        """
        if duration_sec <= 0:
            meta = self._probe_metadata()
            return np.zeros((0,), dtype=np.float32), meta

        audio = AudioSegment.from_file(
            self.file_path,
            start_second=max(0.0, start_sec),
            duration=duration_sec,
        )

        if target_sample_rate and audio.frame_rate != target_sample_rate:
            audio = audio.set_frame_rate(target_sample_rate)
        if target_channels and audio.channels != target_channels:
            audio = audio.set_channels(target_channels)
        if target_sample_width and audio.sample_width != target_sample_width:
            audio = audio.set_sample_width(target_sample_width)

        meta = AudioMeta(
            duration_sec=duration_sec,
            sample_rate=audio.frame_rate,
            channels=audio.channels,
            sample_width=audio.sample_width,
        )

        samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
        if audio.channels > 1:
            samples = samples.reshape((-1, audio.channels))

        max_val = float(2 ** (8 * audio.sample_width - 1))
        if max_val > 0:
            samples = samples / max_val

        return samples, meta
