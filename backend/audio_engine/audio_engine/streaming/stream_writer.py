"""
StreamWriter: write audio chunks progressively to a WAV file.
"""

import wave
from typing import Optional

from pydub import AudioSegment

from audio_engine.utils.logger import get_logger

logger = get_logger(__name__)


class StreamWriter:
    """
    Progressive WAV writer for streaming output.
    """

    def __init__(self, output_path: str, sample_rate: int, channels: int, sample_width: int = 2):
        self.output_path = output_path
        self.sample_rate = sample_rate
        self.channels = channels
        self.sample_width = sample_width
        self._wav: Optional[wave.Wave_write] = None

    def open(self) -> None:
        self._wav = wave.open(self.output_path, "wb")
        self._wav.setnchannels(self.channels)
        self._wav.setsampwidth(self.sample_width)
        self._wav.setframerate(self.sample_rate)

    def write_segment(self, audio: AudioSegment) -> None:
        if self._wav is None:
            raise RuntimeError("StreamWriter is not open")

        if audio.frame_rate != self.sample_rate:
            audio = audio.set_frame_rate(self.sample_rate)
        if audio.channels != self.channels:
            audio = audio.set_channels(self.channels)
        if audio.sample_width != self.sample_width:
            audio = audio.set_sample_width(self.sample_width)

        self._wav.writeframes(audio.raw_data)

    def close(self) -> None:
        if self._wav is not None:
            self._wav.close()
            self._wav = None

    def __enter__(self) -> "StreamWriter":
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.close()
        return False
