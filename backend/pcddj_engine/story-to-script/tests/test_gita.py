"""Tests for gita continuity helpers."""

from __future__ import annotations

from story_processing.fountain.gita import (
    apply_gita_to_plan,
    default_gita,
    normalize_gita,
    update_gita_from_plan,
)


def test_default_and_normalize_gita_shape():
    payload = default_gita("Trail_of_bells", "Trail of Bells", "Writer One")
    normalized = normalize_gita(payload)
    assert normalized["schema_version"] == "1.0"
    assert normalized["project_id"] == "Trail_of_bells"
    assert isinstance(normalized["characters"], dict)
    assert isinstance(normalized["episodes"], list)


def test_update_gita_from_plan_collects_episode_data():
    gita = default_gita("demo", "Demo", "Writer")
    plan = {
        "schema_version": "1.0",
        "scenes": [
            {
                "structure": {
                    "scene_title": "INT. SHRINE",
                    "speakers": ["EVA", "MANAS"],
                    "sfx_events": [{"sfx_label": "bell_strike", "intensity": "strong", "semantic_role": "impact"}],
                    "ambience_cue": {"primary_atmosphere": "temple_night"},
                },
                "interpretation": {"music_strategy": "low drones"},
            }
        ],
    }
    out = update_gita_from_plan(gita, plan, "episode_01")
    assert "eva" in out["characters"]
    assert out["episodes"][0]["chapter_slug"] == "episode_01"
    assert out["episodes"][0]["scene_count"] == 1
    assert "bell_strike" in out["episodes"][0]["sfx_labels"]


def test_normalize_gita_preserves_tts_voice():
    raw = {
        "schema_version": "1.0",
        "project_id": "demo",
        "characters": {
            "eva": {"name": "EVA", "aliases": ["EVA"], "tts_voice": "Aoede"},
            "narrator": {"name": "NARRATOR", "aliases": ["NARRATOR"]},
        },
    }
    out = normalize_gita(raw)
    assert out["characters"]["eva"]["tts_voice"] == "Aoede"
    assert out["characters"]["narrator"]["tts_voice"] == ""


def test_update_gita_seeds_tts_voice_field_for_new_characters():
    gita = default_gita("demo", "Demo", "Writer")
    plan = {
        "schema_version": "1.0",
        "scenes": [
            {
                "structure": {
                    "scene_title": "INT. ROOM",
                    "speakers": ["NEW_CHAR"],
                    "sfx_events": [],
                    "ambience_cue": None,
                }
            }
        ],
    }
    out = update_gita_from_plan(gita, plan, "ep1")
    assert "new_char" in out["characters"]
    assert out["characters"]["new_char"]["tts_voice"] == ""
    for fld in ("audio_profile", "style", "pace", "accent"):
        assert out["characters"]["new_char"][fld] == ""


def test_normalize_gita_preserves_audio_fields():
    raw = {
        "schema_version": "1.0",
        "project_id": "demo",
        "characters": {
            "eva": {
                "name": "EVA",
                "aliases": ["EVA"],
                "tts_voice": "Aoede",
                "audio_profile": "Soft mezzo, contemplative.",
                "style": "Whisper",
                "pace": "The Drift",
                "accent": "British (GB)",
            },
        },
        "audio": {"sample_context": "Audio drama, atmospheric."},
    }
    out = normalize_gita(raw)
    eva = out["characters"]["eva"]
    assert eva["audio_profile"] == "Soft mezzo, contemplative."
    assert eva["style"] == "Whisper"
    assert eva["pace"] == "The Drift"
    assert eva["accent"] == "British (GB)"
    assert out["audio"]["sample_context"] == "Audio drama, atmospheric."


def test_apply_gita_to_plan_applies_delivery_ambience_and_motif():
    gita = normalize_gita(
        {
            "project_id": "demo",
            "series_title": "Demo",
            "characters": {
                "eva": {"name": "EVA", "aliases": ["EVA"], "default_delivery": "whispered"},
            },
            "locations": {
                "int_shrine": {"title": "INT. SHRINE", "preferred_ambience": "stone_hall"},
            },
            "sfx_motifs": {
                "bell": {"label": "bell_strike", "intensity": "dramatic", "semantic_role": "impact"},
            },
        }
    )
    plan = {
        "schema_version": "1.0",
        "scenes": [
            {
                "structure": {
                    "scene_title": "INT. SHRINE",
                    "dialogue_turns": [{"speaker": "EVA", "text": "Hello", "start_char": 0, "end_char": 5, "quote_style": "double"}],
                    "sfx_events": [{"sfx_label": "bell_strike", "intensity": "moderate", "semantic_role": "interaction"}],
                    "ambience_cue": None,
                }
            }
        ],
    }
    out = apply_gita_to_plan(plan, gita)
    scene = out["scenes"][0]["structure"]
    assert scene["dialogue_turns"][0]["delivery_hint"] == "whispered"
    assert scene["ambience_cue"]["primary_atmosphere"] == "stone_hall"
    assert scene["sfx_events"][0]["intensity"] == "dramatic"
