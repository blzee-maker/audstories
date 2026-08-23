from asset_engine.contracts.requirements_models import AssetRequirement, ResolutionStatus
from asset_engine.timing.compute_timing import (
    compute_project_duration,
    compute_project_timing,
    compute_scene_timing,
)


def make_voice_req(
    *,
    sequence: int,
    intent: str,
    gap_ms: int = 0,
    duration: float | None = None,
    estimated_duration: float | None = None,
    status: ResolutionStatus = ResolutionStatus.RESOLVED,
):
    req = AssetRequirement(
        requirement_id=f"scene_1:narrator:{sequence}",
        asset_kind="voice",
        scene_id="scene_1",
        scene_name="Scene 1",
        scene_index=0,
        track_id="narrator",
        clip_index=sequence,
        clip_id=f"clip_{sequence}",
        descriptor="line",
        sequence=sequence,
        timing_intent=intent,
        gap_ms=gap_ms,
        estimated_duration_seconds=estimated_duration,
    )
    req.resolution_status = status
    req.resolved_duration_seconds = duration
    req.resolved_file = "x.wav" if status == ResolutionStatus.RESOLVED else None
    return req


def make_music_req(intent: str = "with_scene_start"):
    req = AssetRequirement(
        requirement_id="scene_1:music:0",
        asset_kind="music",
        scene_id="scene_1",
        scene_name="Scene 1",
        scene_index=0,
        track_id="music",
        clip_index=0,
        clip_id="clip_music_0",
        descriptor="tension_mid",
        timing_intent=intent,
    )
    req.resolution_status = ResolutionStatus.RESOLVED
    req.resolved_file = "music.wav"
    req.resolved_duration_seconds = 10.0
    return req


def test_serial_voice_clips():
    reqs = [
        make_voice_req(sequence=0, intent="scene_start", gap_ms=0, duration=3.0),
        make_voice_req(sequence=1, intent="after_previous_voice", gap_ms=500, duration=2.0),
    ]
    clips, duration = compute_scene_timing(reqs)
    assert clips[0]["offset"] == 0.0
    assert clips[1]["offset"] == 3.5
    assert duration == 5.5


def test_missing_voice_uses_estimate():
    reqs = [
        make_voice_req(
            sequence=0,
            intent="scene_start",
            estimated_duration=4.0,
            status=ResolutionStatus.PLACEHOLDER,
        )
    ]
    clips, duration = compute_scene_timing(reqs)
    assert clips[0]["timing_source"] == "estimated"
    assert duration == 4.0


def test_music_gets_zero_offset():
    reqs = [make_music_req(intent="with_scene_start")]
    clips, _ = compute_scene_timing(reqs)
    assert clips[0]["offset"] == 0.0


def test_project_timing_and_duration():
    scenes = [{"id": "s1", "duration": 5.0}, {"id": "s2", "duration": 2.5}]
    output = compute_project_timing(scenes)
    assert output[0]["start"] == 0.0
    assert output[1]["start"] == 5.0
    assert compute_project_duration(output) == 7.5
