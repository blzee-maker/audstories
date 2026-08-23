def compute_dialogue_density(dialogue_ranges, window_start, window_end):
    window_duration = window_end - window_start
    if window_duration <= 0:
        return 0.0

    dialogue_time = 0.0

    for d_start, d_end in dialogue_ranges:
        overlap_start = max(d_start, window_start)
        overlap_end = min(d_end, window_end)

        if overlap_start < overlap_end:
            dialogue_time += overlap_end - overlap_start

    return dialogue_time / window_duration


def classify_dialogue_density(ratio):
    if ratio < 0.25:
        return "low"
    elif ratio < 0.6:
        return "medium"
    else:
        return "high"
