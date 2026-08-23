"""Tests for SFX temporal anchoring in the timing solver."""

from asset_engine.contracts.requirements_models import AssetRequirement, ResolutionStatus
from asset_engine.timing.compute_timing import compute_scene_timing


def _voice_req(*, sequence: int, duration: float, gap_ms: int = 500):
    req = AssetRequirement(
        requirement_id=f"s1:narrator:{sequence}",
        asset_kind="voice",
        scene_id="s1",
        scene_name="Scene 1",
        scene_index=0,
        track_id="narrator",
        clip_index=sequence,
        clip_id=f"clip_voice_{sequence}",
        descriptor="line",
        sequence=sequence,
        timing_intent="scene_start" if sequence == 0 else "after_previous_voice",
        gap_ms=gap_ms,
    )
    req.resolution_status = ResolutionStatus.RESOLVED
    req.resolved_duration_seconds = duration
    req.resolved_file = f"voice_{sequence}.wav"
    return req


def _sfx_req(*, anchor_order: int | None = None, anchor_position: str | None = None):
    req = AssetRequirement(
        requirement_id="s1:sfx:0",
        asset_kind="sfx",
        scene_id="s1",
        scene_name="Scene 1",
        scene_index=0,
        track_id="sfx",
        clip_index=0,
        clip_id="clip_sfx_0",
        descriptor="door_slam",
        timing_intent=f"with_voice_{anchor_order}" if anchor_order is not None else "with_scene_start",
        anchor_order=anchor_order,
        anchor_position=anchor_position,
    )
    req.resolution_status = ResolutionStatus.RESOLVED
    req.resolved_file = "door_slam.wav"
    req.resolved_duration_seconds = 0.5
    return req


class TestSFXAnchoredTiming:
    def test_unanchored_sfx_at_scene_start(self):
        reqs = [
            _voice_req(sequence=0, duration=3.0, gap_ms=0),
            _sfx_req(anchor_order=None),
        ]
        clips, _ = compute_scene_timing(reqs)
        sfx_clip = [c for c in clips if c["track"] == "sfx"][0]
        assert sfx_clip["offset"] == 0.0

    def test_sfx_anchored_under_first_voice(self):
        reqs = [
            _voice_req(sequence=0, duration=3.0, gap_ms=0),
            _voice_req(sequence=1, duration=2.0),
            _sfx_req(anchor_order=0, anchor_position="under"),
        ]
        clips, _ = compute_scene_timing(reqs)
        sfx_clip = [c for c in clips if c["track"] == "sfx"][0]
        assert sfx_clip["offset"] == 0.0

    def test_sfx_anchored_under_second_voice(self):
        reqs = [
            _voice_req(sequence=0, duration=3.0, gap_ms=0),
            _voice_req(sequence=1, duration=2.0),
            _sfx_req(anchor_order=1, anchor_position="under"),
        ]
        clips, _ = compute_scene_timing(reqs)
        sfx_clip = [c for c in clips if c["track"] == "sfx"][0]
        assert sfx_clip["offset"] == 3.5

    def test_sfx_anchored_after_voice(self):
        reqs = [
            _voice_req(sequence=0, duration=3.0, gap_ms=0),
            _sfx_req(anchor_order=0, anchor_position="after"),
        ]
        clips, _ = compute_scene_timing(reqs)
        sfx_clip = [c for c in clips if c["track"] == "sfx"][0]
        assert sfx_clip["offset"] == 3.0

    def test_sfx_anchored_before_voice(self):
        reqs = [
            _voice_req(sequence=0, duration=3.0, gap_ms=0),
            _voice_req(sequence=1, duration=2.0),
            _sfx_req(anchor_order=1, anchor_position="before"),
        ]
        clips, _ = compute_scene_timing(reqs)
        sfx_clip = [c for c in clips if c["track"] == "sfx"][0]
        assert sfx_clip["offset"] == 3.3

    def test_sfx_anchor_nonexistent_voice_falls_back_to_zero(self):
        reqs = [
            _voice_req(sequence=0, duration=3.0, gap_ms=0),
            _sfx_req(anchor_order=99, anchor_position="under"),
        ]
        clips, _ = compute_scene_timing(reqs)
        sfx_clip = [c for c in clips if c["track"] == "sfx"][0]
        assert sfx_clip["offset"] == 0.0
