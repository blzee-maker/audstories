"""
Stateful EQ filters for chunk-by-chunk streaming processing.
"""

from typing import Optional

import numpy as np
from scipy import signal


class _StatefulFilter:
    """
    Generic stateful IIR filter wrapper using lfilter with preserved state.
    """

    def __init__(self, b: np.ndarray, a: np.ndarray):
        self.b = b
        self.a = a
        self._zi: Optional[np.ndarray] = None

    def _init_state(self, channels: int) -> None:
        zi = signal.lfilter_zi(self.b, self.a)
        if channels == 1:
            self._zi = zi
        else:
            self._zi = np.tile(zi, (channels, 1))

    def process_chunk(self, chunk: np.ndarray) -> np.ndarray:
        if chunk.size == 0:
            return chunk

        if chunk.ndim == 1:
            channels = 1
        else:
            channels = chunk.shape[1]

        if self._zi is None:
            self._init_state(channels)

        if channels == 1:
            output, self._zi = signal.lfilter(self.b, self.a, chunk, zi=self._zi)
            return output

        output = np.zeros_like(chunk)
        for ch in range(channels):
            output[:, ch], self._zi[ch] = signal.lfilter(
                self.b, self.a, chunk[:, ch], zi=self._zi[ch]
            )
        return output


class StreamingHighPass(_StatefulFilter):
    def __init__(self, cutoff_hz: float, sample_rate: int, order: int = 2):
        nyquist = sample_rate / 2.0
        normalized_cutoff = min(max(cutoff_hz / nyquist, 1e-6), 0.999999)
        b, a = signal.butter(order, normalized_cutoff, btype="high")
        super().__init__(b, a)


class StreamingLowPass(_StatefulFilter):
    def __init__(self, cutoff_hz: float, sample_rate: int, order: int = 2):
        nyquist = sample_rate / 2.0
        normalized_cutoff = min(max(cutoff_hz / nyquist, 1e-6), 0.999999)
        b, a = signal.butter(order, normalized_cutoff, btype="low")
        super().__init__(b, a)


class StreamingPeakEQ(_StatefulFilter):
    def __init__(self, freq_hz: float, gain_db: float, q: float, sample_rate: int):
        # Audio EQ Cookbook: peaking EQ
        A = 10 ** (gain_db / 40)
        omega = 2 * np.pi * freq_hz / sample_rate
        sin_omega = np.sin(omega)
        cos_omega = np.cos(omega)
        alpha = sin_omega / (2 * q)

        b0 = 1 + alpha * A
        b1 = -2 * cos_omega
        b2 = 1 - alpha * A
        a0 = 1 + alpha / A
        a1 = -2 * cos_omega
        a2 = 1 - alpha / A

        b = np.array([b0 / a0, b1 / a0, b2 / a0])
        a = np.array([1.0, a1 / a0, a2 / a0])
        super().__init__(b, a)
