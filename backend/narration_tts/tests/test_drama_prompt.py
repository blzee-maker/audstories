"""Tests for narration_tts.drama_prompt structured prompt construction."""

from __future__ import annotations

from narration_tts import drama_prompt


def _gita_with_arnav() -> dict:
    return {
        "characters": {
            "arnav": {
                "name": "ARNAV",
                "aliases": ["ARNAV"],
                "audio_profile": "Confident young pilgrim, warm baritone with a hint of mischief.",
                "style": "Conversational",
                "pace": "Brisk",
                "accent": "Indian English",
                "default_delivery": "",
                "tts_voice": "Charon",
            }
        },
        "audio": {"sample_context": "Audio drama; cinematic and atmospheric."},
    }


def _narrative_plan_one_scene() -> dict:
    return {
        "schema_version": "1.0",
        "scenes": [
            {
                "scene_id": "scene_000",
                "structure": {
                    "scene_id": "scene_000",
                    "scene_title": "EXT. VILLAGE OUTSKIRTS - DUSK",
                    "speakers": ["ARNAV"],
                    "dialogue_turns": [
                        {
                            "speaker": "ARNAV",
                            "text": "Dharamvana Village.",
                            "delivery_hint": "to his friends, grinning",
                        }
                    ],
                    "ambience_cue": {
                        "primary_atmosphere": "forest_day_distant",
                        "atmosphere_description": "",
                    },
                    "action_notes": [
                        "Mountain wind. Distant forest ambience.",
                        "Car door shuts.",
                    ],
                },
                "interpretation": {
                    "primary_emotion": "neutral",
                    "energy_level": 7,
                    "emotion_intensity": 8,
                    "scene_style": "balanced",
                    "music_strategy": None,
                },
            }
        ],
    }


def test_build_drama_prompt_includes_all_sections():
    prompt = drama_prompt.build_drama_prompt(
        line_text="Dharamvana Village.",
        speaker="character_arnav",
        gita=_gita_with_arnav(),
        narrative_plan=_narrative_plan_one_scene(),
        scene_index=0,
    )
    assert "# Audio Profile" in prompt
    assert "Confident young pilgrim" in prompt
    assert "# Director's note" in prompt
    assert "Style: Conversational." in prompt
    assert "Pace: Brisk." in prompt
    assert "Accent: Indian English." in prompt
    assert "Delivery: to his friends, grinning." in prompt
    assert "## Scene:" in prompt
    assert "EXT. VILLAGE OUTSKIRTS - DUSK" in prompt
    assert "Atmosphere: forest_day_distant." in prompt
    assert "## Sample Context:" in prompt
    assert "Audio drama; cinematic and atmospheric." in prompt
    assert "## Transcript:" in prompt
    assert "[to_his_friends_grinning] Dharamvana Village." in prompt


def test_build_drama_prompt_speaker_tracks_id_resolves_to_bare_name():
    """A track_id like 'character_arnav' should still find the ARNAV character."""
    prompt = drama_prompt.build_drama_prompt(
        line_text="Listen.",
        speaker="character_arnav",
        gita=_gita_with_arnav(),
    )
    assert "Confident young pilgrim" in prompt
    assert "Listen." in prompt


def test_build_drama_prompt_falls_back_to_interpretation_for_sample_context():
    gita = _gita_with_arnav()
    gita.pop("audio", None)
    prompt = drama_prompt.build_drama_prompt(
        line_text="Did you hear that?",
        speaker="ARNAV",
        gita=gita,
        narrative_plan=_narrative_plan_one_scene(),
        scene_index=0,
    )
    assert "## Sample Context:" in prompt
    assert "Style: balanced." in prompt
    assert "Energy: 7/10." in prompt
    assert "Intensity: 8/10." in prompt


def test_build_drama_prompt_omits_blocks_when_data_missing():
    prompt = drama_prompt.build_drama_prompt(
        line_text="Hello world.",
        speaker="UNKNOWN",
    )
    assert "# Audio Profile" not in prompt
    assert "# Director's note" not in prompt
    assert "## Scene:" not in prompt
    assert "## Sample Context:" not in prompt
    assert "## Transcript:" in prompt
    assert "Hello world." in prompt


def test_build_drama_prompt_sample_context_override_takes_priority():
    prompt = drama_prompt.build_drama_prompt(
        line_text="Listen.",
        speaker="ARNAV",
        gita=_gita_with_arnav(),
        narrative_plan=_narrative_plan_one_scene(),
        scene_index=0,
        sample_context="Project override context.",
    )
    assert "Project override context." in prompt
    assert "Audio drama; cinematic and atmospheric." not in prompt


def test_delivery_tag_normalized_safely():
    prompt = drama_prompt.build_drama_prompt(
        line_text="Run!",
        speaker="ARNAV",
        gita=_gita_with_arnav(),
        delivery_hint_override="Whisper, breathless...",
    )
    assert "[whisper_breathless] Run!" in prompt
