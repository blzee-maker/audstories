"""Tests for dsl.builders (tracks, clips, settings, scene_rules)."""

from dsl.builders.clips import (
    build_ambience_clips,
    build_music_clips,
    build_sfx_clips,
    build_voice_clips,
)
from dsl.builders.scene_rules import build_scene_rules
from dsl.builders.settings import build_settings
from dsl.builders.tracks import (
    _sanitize_track_id,
    build_tracks,
    collect_speaker_track_map,
)


# ---------------------------------------------------------------------------
# tracks.py
# ---------------------------------------------------------------------------

class TestSanitizeTrackId:
    def test_simple_name(self):
        assert _sanitize_track_id("Alice") == "character_alice"

    def test_name_with_spaces(self):
        assert _sanitize_track_id("Mr Smith") == "character_mr_smith"

    def test_name_with_hyphens(self):
        assert _sanitize_track_id("Mary-Jane") == "character_mary_jane"

    def test_special_chars_stripped(self):
        result = _sanitize_track_id("O'Brien!")
        assert result == "character_obrien"

    def test_empty_string(self):
        assert _sanitize_track_id("") == "character_unknown"


class TestBuildTracks:
    def test_narrator_always_present(self):
        plan = {"scenes": []}
        tracks = build_tracks(plan)
        ids = [t.id for t in tracks]
        assert "narrator" in ids

    def test_music_always_present(self):
        plan = {"scenes": []}
        tracks = build_tracks(plan)
        ids = [t.id for t in tracks]
        assert "music" in ids

    def test_ambience_always_present(self):
        plan = {"scenes": []}
        tracks = build_tracks(plan)
        ids = [t.id for t in tracks]
        assert "ambience" in ids

    def test_character_tracks_created(self):
        plan = {
            "scenes": [
                {"structure": {"speakers": ["Alice", "Bob"]}},
            ],
        }
        tracks = build_tracks(plan)
        ids = [t.id for t in tracks]
        assert "character_alice" in ids
        assert "character_bob" in ids

    def test_sfx_track_conditional(self):
        # No SFX signals → no SFX track
        plan = {
            "scenes": [
                {
                    "structure": {"speakers": [], "sfx_events": []},
                    "signals": {"short_sentence_streak": 0, "punctuation_score": 0.0},
                    "interpretation": {"energy_level": 5, "silence_intent": "none"},
                },
            ],
        }
        tracks = build_tracks(plan)
        ids = [t.id for t in tracks]
        assert "sfx" not in ids


class TestCollectSpeakerTrackMap:
    def test_maps_speakers(self):
        plan = {
            "scenes": [
                {"structure": {"speakers": ["Alice"]}},
                {"structure": {"speakers": ["Alice", "Bob"]}},
            ],
        }
        result = collect_speaker_track_map(plan)
        assert result["Alice"] == "character_alice"
        assert result["Bob"] == "character_bob"

    def test_empty_plan(self):
        assert collect_speaker_track_map({"scenes": []}) == {}


# ---------------------------------------------------------------------------
# clips.py
# ---------------------------------------------------------------------------

class TestBuildVoiceClips:
    def test_pure_narration(self):
        scene = {
            "structure": {
                "sentences": ["The sun rose.", "Birds sang."],
                "dialogue_turns": [],
            },
        }
        clips = build_voice_clips(scene, {})
        assert "narrator" in clips
        assert len(clips["narrator"]) == 2

    def test_dialogue_routed_to_speaker_track(self):
        scene = {
            "structure": {
                "sentences": ['"Hello," said Alice.'],
                "dialogue_turns": [
                    {"speaker": "Alice", "text": "Hello,", "start_char": 1, "end_char": 7, "quote_style": "double"},
                ],
            },
        }
        speaker_map = {"Alice": "character_alice"}
        clips = build_voice_clips(scene, speaker_map)
        assert "character_alice" in clips

    def test_indirect_speech_stays_on_narrator(self):
        scene = {
            "structure": {
                "sentences": ["She said that she was tired."],
                "dialogue_turns": [
                    {"speaker": "She", "text": "she was tired", "start_char": 14, "end_char": 27, "quote_style": "indirect"},
                ],
            },
        }
        clips = build_voice_clips(scene, {})
        assert "narrator" in clips
        # Should NOT create a separate character track for indirect speech
        assert all(k == "narrator" for k in clips)


class TestBuildMusicClips:
    def test_returns_music_key(self):
        scene = {"interpretation": {"primary_emotion": "joy"}}
        clips = build_music_clips(scene, 0.5)
        assert "music" in clips
        assert len(clips["music"]) == 1
        assert clips["music"][0].loop is True

    def test_mood_contains_energy_suffix(self):
        scene = {"interpretation": {"primary_emotion": "sadness"}}
        clips = build_music_clips(scene, 0.1)
        assert "_low" in clips["music"][0].mood

    def test_new_emotion_nostalgia_mood(self):
        scene = {"interpretation": {"primary_emotion": "nostalgia"}}
        clips = build_music_clips(scene, 0.1)
        assert clips["music"][0].mood == "bittersweet_low"

    def test_new_emotion_surprise_mood(self):
        scene = {"interpretation": {"primary_emotion": "surprise"}}
        clips = build_music_clips(scene, 0.8)
        assert clips["music"][0].mood == "dramatic_high"


class TestBuildAmbienceClips:
    def test_fallback_path(self):
        scene = {
            "structure": {},
            "interpretation": {"primary_emotion": "calm", "scene_style": "balanced"},
        }
        clips = build_ambience_clips(scene)
        assert "ambience" in clips
        assert clips["ambience"][0].atmosphere == "nature_gentle"

    def test_gemini_cue_path(self):
        scene = {
            "structure": {
                "ambience_cue": {"primary_atmosphere": "rainy_forest"},
            },
        }
        clips = build_ambience_clips(scene)
        assert clips["ambience"][0].atmosphere == "rainy_forest"


class TestBuildSfxClips:
    def test_no_sfx_track(self):
        scene = {"structure": {}, "signals": {}, "interpretation": {}}
        assert build_sfx_clips(scene, 0.5, has_sfx_track=False) == {}

    def test_gemini_sfx_events(self):
        scene = {
            "structure": {
                "sfx_events": [
                    {"sfx_label": "door_slam", "semantic_role": "impact"},
                ],
            },
        }
        clips = build_sfx_clips(scene, 0.5, has_sfx_track=True)
        assert "sfx" in clips
        assert clips["sfx"][0].sfx_hint == "door_slam"


# ---------------------------------------------------------------------------
# settings.py
# ---------------------------------------------------------------------------

class TestBuildSettings:
    def test_single_scene_no_crossfade(self):
        plan = {
            "scenes": [
                {"interpretation": {"energy_level": 5, "scene_style": "balanced", "silence_intent": "none"}},
            ],
        }
        settings = build_settings(plan)
        assert settings.scene_crossfade.enabled is False

    def test_multi_scene_crossfade_enabled(self):
        plan = {
            "scenes": [
                {"interpretation": {"energy_level": 5, "scene_style": "balanced", "silence_intent": "none"}},
                {"interpretation": {"energy_level": 5, "scene_style": "balanced", "silence_intent": "none"}},
            ],
        }
        settings = build_settings(plan)
        assert settings.scene_crossfade.enabled is True

    def test_ducking_always_enabled(self):
        plan = {"scenes": []}
        settings = build_settings(plan)
        assert settings.ducking.enabled is True


# ---------------------------------------------------------------------------
# scene_rules.py
# ---------------------------------------------------------------------------

class TestBuildSceneRules:
    def test_neutral_low_energy_returns_none(self):
        scene = {"interpretation": {"primary_emotion": "neutral"}}
        result = build_scene_rules(scene, energy=0.3)
        assert result is None

    def test_warm_emotion_returns_eq_tilt(self):
        scene = {"interpretation": {"primary_emotion": "sadness"}}
        result = build_scene_rules(scene, energy=0.3)
        assert result is not None
        assert result.eq is not None
        assert result.eq.tilt == "warm"

    def test_high_energy_returns_ducking_override(self):
        scene = {"interpretation": {"primary_emotion": "neutral"}}
        result = build_scene_rules(scene, energy=0.9, global_duck_amount=-6)
        assert result is not None
        assert result.ducking is not None
