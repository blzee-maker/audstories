from asset_engine.contracts.requirements_models import AssetRequirement
from asset_engine.timing.compute_timing import compute_scene_timing


def _voice_req(req_id: str, sequence: int, *, pre: float = 0.0, post: float = 0.0) -> AssetRequirement:
    return AssetRequirement(
        requirement_id=req_id,
        asset_kind="voice",
        scene_id="scene_1",
        track_id="narrator",
        clip_index=sequence,
        descriptor=f"line {sequence}",
        tts_text=f"line {sequence}",
        sequence=sequence,
        timing_intent="scene_start" if sequence == 0 else "after_previous_voice",
        estimated_duration_seconds=1.0,
        gap_ms=500,
        pre_silence_s=pre,
        post_silence_s=post,
    )


def test_scene_close_post_silence_extends_scene_duration_by_two_seconds():
    reqs = [_voice_req("r0", 0), _voice_req("r1", 1, post=2.0)]
    _, duration_with_hold = compute_scene_timing(reqs, default_silence=0.5)

    reqs_no_hold = [_voice_req("r0", 0), _voice_req("r1", 1, post=0.0)]
    _, duration_without_hold = compute_scene_timing(reqs_no_hold, default_silence=0.5)

    assert round(duration_with_hold - duration_without_hold, 3) == 2.0


def test_pre_and_post_silence_shift_offsets_and_cumulative_end():
    reqs = [
        _voice_req("r0", 0, post=1.0),
        _voice_req("r1", 1, pre=0.5, post=0.0),
    ]
    clips, scene_duration = compute_scene_timing(reqs, default_silence=0.5)

    first = next(c for c in clips if c["id"] == "r0")
    second = next(c for c in clips if c["id"] == "r1")

    assert first["offset"] == 0.0
    assert second["offset"] == 2.5
    assert scene_duration == 3.5
