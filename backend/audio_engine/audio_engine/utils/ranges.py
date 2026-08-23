from typing import List, Tuple


Range = Tuple[float, float]  # (start_sec, end_sec)


def merge_ranges(
    ranges: List[Range],
    min_gap_ms: int = 0
) -> List[Range]:
    """
    Merge overlapping or closely spaced ranges.

    Args:
        ranges: List of (start, end) in seconds
        min_gap_ms: Minimum gap (ms) to consider ranges continuous

    Returns:
        Merged list of ranges
    """
    if not ranges:
        return []

    # Sort by start time
    ranges = sorted(ranges, key=lambda r: r[0])
    merged = [list(ranges[0])]

    for start, end in ranges[1:]:
        last_start, last_end = merged[-1]
        gap_ms = (start - last_end) * 1000

        if gap_ms <= min_gap_ms:
            merged[-1][1] = max(last_end, end)
        else:
            merged.append([start, end])

    return [(s, e) for s, e in merged]


def clamp_ranges(
    ranges: List[Range],
    min_time: float,
    max_time: float
) -> List[Range]:
    """
    Clamp ranges to [min_time, max_time].
    """
    clamped = []

    for start, end in ranges:
        s = max(min_time, start)
        e = min(max_time, end)

        if s < e:
            clamped.append((s, e))

    return clamped


def normalize_ranges(ranges: List[Range]) -> List[Range]:
    """
    Sort and remove invalid ranges.
    """
    clean = [
        (s, e) for s, e in ranges
        if s is not None and e is not None and s < e
    ]
    return sorted(clean, key=lambda r: r[0])
