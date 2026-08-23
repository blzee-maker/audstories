"""
Stateful compressor for chunk-by-chunk streaming processing.
"""

from typing import Optional

import numpy as np


class StreamingCompressor:
    """
    Simple peak compressor with attack/release envelope state.
    """

    def __init__(
        self,
        sample_rate: int,
        threshold_db: float = -18.0,
        ratio: float = 4.0,
        attack_ms: float = 10.0,
        release_ms: float = 120.0,
        makeup_gain_db: float = 0.0,
    ):
        self.sample_rate = sample_rate
        self.threshold_db = threshold_db
        self.ratio = max(ratio, 1.0)
        self.attack_coeff = np.exp(-1.0 / (sample_rate * (attack_ms / 1000.0)))
        self.release_coeff = np.exp(-1.0 / (sample_rate * (release_ms / 1000.0)))
        self.makeup_gain = 10 ** (makeup_gain_db / 20.0)
        self._env: Optional[np.ndarray] = None

    def _init_env(self, channels: int) -> None:
        if channels == 1:
            self._env = np.array(0.0, dtype=np.float32)
        else:
            self._env = np.zeros((channels,), dtype=np.float32)

    def process_chunk(self, chunk: np.ndarray) -> np.ndarray:
        if chunk.size == 0:
            return chunk

        if chunk.ndim == 1:
            channels = 1
        else:
            channels = chunk.shape[1]

        if self._env is None:
            self._init_env(channels)

        threshold = 10 ** (self.threshold_db / 20.0)
        output = np.zeros_like(chunk)

        if channels == 1:
            env = float(self._env)
            for i, sample in enumerate(chunk):
                x = abs(sample)
                if x > env:
                    env = self.attack_coeff * env + (1 - self.attack_coeff) * x
                else:
                    env = self.release_coeff * env + (1 - self.release_coeff) * x

                if env > threshold and env > 0:
                    gain = (threshold + (env - threshold) / self.ratio) / env
                else:
                    gain = 1.0

                output[i] = sample * gain

            self._env = np.array(env, dtype=np.float32)
            return output * self.makeup_gain

        env = self._env.astype(np.float32)
        for i in range(chunk.shape[0]):
            frame = chunk[i]
            frame_abs = np.abs(frame)
            attack_mask = frame_abs > env
            env = np.where(
                attack_mask,
                self.attack_coeff * env + (1 - self.attack_coeff) * frame_abs,
                self.release_coeff * env + (1 - self.release_coeff) * frame_abs,
            )

            gain = np.ones_like(env)
            over_mask = env > threshold
            gain[over_mask] = (threshold + (env[over_mask] - threshold) / self.ratio) / env[over_mask]
            output[i] = frame * gain

        self._env = env
        return output * self.makeup_gain
