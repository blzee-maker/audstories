from audio_engine.utils.ranges import merge_ranges

ranges = [(0.0, 1.0), (1.01, 2.0), (3.0, 4.0)]
merged = merge_ranges(ranges, min_gap_ms=20)

print(merged)
# Expected: [(0.0, 2.0), (3.0, 4.0)]
