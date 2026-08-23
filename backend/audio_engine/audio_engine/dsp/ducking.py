from pydub import AudioSegment

from audio_engine.utils.ranges import merge_ranges


def apply_envelope_ducking(audio: AudioSegment, clip_start_sec: float, dialogue_ranges, cfg: dict) -> AudioSegment:

    duck_db = cfg["duck_amount"]
    fade_down = cfg["fade_down_ms"]
    fade_up = cfg["fade_up_ms"]
    min_pause = cfg["min_pause_ms"]
    delay_ms = cfg.get("onset_delay_ms", 0) / 1000.0

    ranges = merge_ranges(dialogue_ranges, min_pause)
    output = audio

    for start, end in ranges:
        start += delay_ms
        rel_start = int((start - clip_start_sec) * 1000)
        rel_end = int((end - clip_start_sec) * 1000)

        rel_start = max(0, rel_start)
        rel_end = min(len(output), rel_end)

        if rel_start >= rel_end:
            continue

        # 🔽 Fade down BEFORE dialogue
        down_start = max(0, rel_start - fade_down)
        down_end = rel_start

        if down_end > down_start:
            output = (
                output[:down_start] +
                output[down_start:down_end].fade_out(fade_down) +
                output[down_end:]
            )

        # 🔇 Duck hold
        output = (
            output[:rel_start] +
            output[rel_start:rel_end].apply_gain(duck_db) +
            output[rel_end:]
        )

        # 🔼 Fade up AFTER dialogue
        up_start = rel_end
        up_end = min(len(output), rel_end + fade_up)

        if up_end > up_start:
            output = (
                output[:up_start] +
                output[up_start:up_end].fade_in(fade_up) +
                output[up_end:]
            )

    return output
