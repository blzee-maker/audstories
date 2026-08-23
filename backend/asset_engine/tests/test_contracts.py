from asset_engine.contracts.requirements_models import (
    AssetRequirement,
    ResolutionStatus,
    ResolveResult,
    TrackType,
)
from asset_engine.requirements.extractor import estimate_voice_duration


def test_estimate_voice_duration_uses_minimum_floor():
    assert estimate_voice_duration("") == 0.5


def test_estimate_voice_duration_scales_with_words():
    # 5 words / 2.5 wps = 2.0 seconds
    assert estimate_voice_duration("one two three four five") == 2.0


def test_asset_requirement_defaults_and_compatibility_fields():
    req = AssetRequirement(
        requirement_id="scene_1:narrator:0",
        asset_kind="voice",
        scene_id="scene_1",
        track_id="narrator",
        clip_index=0,
        descriptor="hello world",
        order=1,
    )

    assert req.track_type == TrackType.VOICE
    assert req.sequence == 1
    assert req.clip_id == "scene_1:narrator:0"
    assert req.resolution_status == ResolutionStatus.MISSING


def test_resolve_result_properties():
    result = ResolveResult()
    assert result.is_complete
    assert not result.has_warnings

    result.missing.append(
        AssetRequirement(
            requirement_id="scene_1:music:0",
            asset_kind="music",
            scene_id="scene_1",
            track_id="music",
            clip_index=0,
            descriptor="tension_mid",
        )
    )
    assert not result.is_complete
