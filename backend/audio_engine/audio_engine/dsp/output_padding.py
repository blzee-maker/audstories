"""Head/tail silence padding on the final master (audiobook delivery)."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from pydub import AudioSegment

logger = logging.getLogger(__name__)


def deterministic_tail_seconds(tail_min: float, tail_max: float, seed: str) -> float:
    """Pick a tail duration in [tail_min, tail_max] deterministically from *seed*."""
    if tail_max <= 0 and tail_min <= 0:
        return 0.0
    lo = min(tail_min, tail_max)
    hi = max(tail_min, tail_max)
    if hi <= lo:
        return lo
    h = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12], 16)
    r = (h % 1_000_000) / 1_000_000.0
    return lo + r * (hi - lo)


def _silent_matching(duration_ms: int, reference: AudioSegment) -> AudioSegment:
    """Digital silence with same frame rate and channel count as *reference*."""
    seg = AudioSegment.silent(duration=duration_ms, frame_rate=reference.frame_rate)
    ch = reference.channels
    if ch and ch != seg.channels:
        try:
            seg = seg.set_channels(ch)
        except Exception as exc:
            logger.warning("Could not match channel count for padding: %s", exc)
    return seg


def apply_output_padding(
    canvas: AudioSegment,
    settings: dict[str, Any],
    *,
    reproducibility_seed: str,
) -> AudioSegment:
    """Prepend/append silence when ``output_padding`` is enabled (audiobook only)."""
    op = settings.get("output_padding")
    if not isinstance(op, dict) or not op.get("enabled", False):
        return canvas
    if str(settings.get("project_type", "")).lower() != "audiobook":
        return canvas

    head_sec = float(op.get("head_seconds", 0.0))
    tail_min = float(op.get("tail_seconds_min", 0.0))
    tail_max = float(op.get("tail_seconds_max", tail_min))
    tail_sec = deterministic_tail_seconds(tail_min, tail_max, reproducibility_seed)

    head_ms = max(0, int(round(head_sec * 1000.0)))
    tail_ms = max(0, int(round(tail_sec * 1000.0)))
    if head_ms == 0 and tail_ms == 0:
        return canvas

    head = _silent_matching(head_ms, canvas) if head_ms else None
    tail = _silent_matching(tail_ms, canvas) if tail_ms else None

    parts: list[AudioSegment] = []
    if head is not None:
        parts.append(head)
    parts.append(canvas)
    if tail is not None:
        parts.append(tail)

    out = parts[0]
    for p in parts[1:]:
        out = out + p
    logger.info(
        "Applied audiobook output padding: head=%.2fs tail=%.2fs (deterministic)",
        head_ms / 1000.0,
        tail_ms / 1000.0,
    )
    return out
