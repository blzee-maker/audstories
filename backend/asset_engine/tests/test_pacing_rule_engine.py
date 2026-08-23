from asset_engine.contracts.draft_models import DraftTimeline
from asset_engine.contracts.requirements_models import AssetRequirement
from asset_engine.pacing.rule_engine import apply_pacing


def _draft() -> DraftTimeline:
    return DraftTimeline(
        project={"name": "demo", "sample_rate": 48000, "bit_depth": 16},
        settings={"default_silence": 0.5},
        tracks=[{"id": "narrator", "type": "voice", "role": "voice"}, {"id": "sfx", "type": "sfx", "role": "foreground"}],
        scenes=[
            {"id": "scene_1", "name": "Scene 1", "energy": 0.2, "tracks": {"narrator": [{"tts_text": "Hi", "order": 0}] }},
            {"id": "scene_2", "name": "Scene 2", "energy": 0.8, "tracks": {"narrator": [{"tts_text": "What?", "order": 0}] }},
        ],
    )


def _voice(req_id: str, scene_id: str, dramatic_function: str, *, energy_hint: float = 0.0, pre: float = 0.0, post: float = 0.0) -> AssetRequirement:
    return AssetRequirement(
        requirement_id=req_id,
        asset_kind="voice",
        scene_id=scene_id,
        track_id="narrator",
        clip_index=0,
        descriptor="line",
        tts_text="line",
        sequence=0,
        dramatic_function=dramatic_function,
        estimated_duration_seconds=1.0,
        timing_intent="scene_start",
        energy_hint=energy_hint,
        pre_silence_s=pre,
        post_silence_s=post,
    )


def test_dramatic_function_rules_apply_defaults():
    draft = _draft()
    reqs = [
        _voice("entry", "scene_1", "scene_entry"),
        _voice("close", "scene_2", "scene_close"),
        _voice("rapid", "scene_2", "rapid_exchange"),
    ]
    apply_pacing(reqs, draft)

    by_id = {r.requirement_id: r for r in reqs}
    assert by_id["entry"].pre_silence_s == 0.6
    assert by_id["close"].post_silence_s >= 4.0
    assert by_id["rapid"].post_silence_s == 0.2


def test_sfx_category_mapping_respects_anchor_position():
    draft = _draft()
    req = AssetRequirement(
        requirement_id="sfx_before",
        asset_kind="sfx",
        scene_id="scene_1",
        track_id="sfx",
        clip_index=0,
        descriptor="door slam",
        sfx_hint="door slam",
        semantic_role="impact",
        anchor_position="before",
    )
    apply_pacing([req], draft)
    assert req.pre_silence_s == 0.0
    assert req.post_silence_s == 0.0


def test_scene_floor_deficit_added_to_highest_emotion_clip():
    draft = _draft()
    reqs = [
        _voice("low", "scene_1", "dialogue", energy_hint=0.2),
        _voice("high", "scene_1", "revelation", energy_hint=0.9),
    ]
    apply_pacing(reqs, draft)
    by_id = {r.requirement_id: r for r in reqs}
    assert by_id["high"].post_silence_s > by_id["low"].post_silence_s


def test_author_supplied_pre_silence_is_preserved():
    draft = _draft()
    req = _voice("authored", "scene_1", "scene_entry", pre=1.4)
    apply_pacing([req], draft)
    assert req.pre_silence_s == 1.4
