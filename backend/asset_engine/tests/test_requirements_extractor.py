from asset_engine.contracts.draft_models import DraftTimeline
from asset_engine.requirements import extract_requirements


def test_extract_requirements_counts():
    draft = DraftTimeline(
        project={"name": "x", "sample_rate": 48000, "bit_depth": 16},
        settings={"default_silence": 0.5},
        tracks=[
            {"id": "narrator", "type": "voice", "role": "voice"},
            {"id": "music", "type": "music", "role": "background"},
            {"id": "ambience", "type": "ambience", "role": "background"},
            {"id": "sfx", "type": "sfx", "role": "foreground"},
        ],
        scenes=[
            {
                "id": "scene_1",
                "name": "Scene 1",
                "energy": 0.4,
                "tracks": {
                    "narrator": [{"tts_text": "hello world", "order": 0}],
                    "music": [{"mood": "neutral_mid", "loop": True}],
                    "ambience": [{"atmosphere": "room_tone", "loop": True}],
                    "sfx": [{"sfx_hint": "door_close", "semantic_role": "impact"}],
                },
            }
        ],
    )

    reqs = extract_requirements(draft)
    assert len(reqs) == 4
    assert {r.asset_kind for r in reqs} == {"voice", "music", "ambience", "sfx"}


def test_narration_only_extracts_voice_only():
    draft = DraftTimeline(
        project={"name": "x", "sample_rate": 48000, "bit_depth": 16},
        settings={
            "default_silence": 0.5,
            "project_type": "audiobook",
            "narration_only": True,
        },
        tracks=[
            {"id": "narrator", "type": "voice", "role": "voice"},
            {"id": "music", "type": "music", "role": "background"},
        ],
        scenes=[
            {
                "id": "scene_1",
                "name": "Scene 1",
                "energy": 0.4,
                "tracks": {
                    "narrator": [{"tts_text": "hello world", "order": 0}],
                    "music": [{"mood": "neutral_mid", "loop": True}],
                },
            }
        ],
    )
    reqs = extract_requirements(draft)
    assert len(reqs) == 1
    assert reqs[0].asset_kind == "voice"

