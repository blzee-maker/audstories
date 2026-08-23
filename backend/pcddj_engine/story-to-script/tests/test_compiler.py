"""Tests for dsl.compiler."""

import orjson

from dsl.compiler import compile_timeline, compile_timeline_json


def _minimal_narrative_plan():
    """Return a minimal valid Narrative Plan dict (1 scene, 1 speaker)."""
    return {
        "schema_version": "1.0",
        "scenes": [
            {
                "scene_id": "scene_000_abc12345",
                "structure": {
                    "scene_id": "scene_000_abc12345",
                    "sentence_count": 2,
                    "word_count": 10,
                    "sentences": ["Hello world.", "How are you?"],
                    "dialogue_turns": [
                        {
                            "speaker": "Alice",
                            "text": "Hello world.",
                            "start_char": 0,
                            "end_char": 12,
                            "quote_style": "double",
                        },
                    ],
                    "speakers": ["Alice"],
                    "sfx_events": [],
                    "ambience_cue": None,
                    "narration_segments": [],
                },
                "signals": {
                    "avg_sentence_length": 5.0,
                    "sentence_length_variance": 1.0,
                    "short_sentence_streak": 0,
                    "punctuation_score": 0.0,
                    "action_verb_density": 0.0,
                    "dialogue_ratio": 0.5,
                    "dialogue_turn_count": 1,
                    "avg_dialogue_length": 2.0,
                    "emotion_scores": {"neutral": 0.5, "joy": 0.3},
                    "emotion_arc": [],
                },
                "interpretation": {
                    "primary_emotion": "neutral",
                    "energy_level": 5,
                    "emotion_intensity": 5,
                    "scene_style": "balanced",
                    "silence_intent": "none",
                    "confidence_score": 0.5,
                },
            },
        ],
    }


class TestCompileTimeline:
    def test_produces_required_keys(self):
        plan = _minimal_narrative_plan()
        result = compile_timeline(plan)
        assert "project" in result
        assert "settings" in result
        assert "tracks" in result
        assert "scenes" in result

    def test_has_narrator_track_for_audiobook(self):
        plan = _minimal_narrative_plan()
        result = compile_timeline(plan, project_type="audiobook")
        track_ids = [t["id"] for t in result["tracks"]]
        assert "narrator" in track_ids

    def test_has_character_track(self):
        plan = _minimal_narrative_plan()
        result = compile_timeline(plan)
        track_ids = [t["id"] for t in result["tracks"]]
        assert "character_alice" in track_ids

    def test_scene_count_matches(self):
        plan = _minimal_narrative_plan()
        result = compile_timeline(plan)
        assert len(result["scenes"]) == 1

    def test_scene_has_voice_clips(self):
        plan = _minimal_narrative_plan()
        result = compile_timeline(plan)
        scene = result["scenes"][0]
        all_clips = []
        for tid, clips in scene["tracks"].items():
            all_clips.extend(clips)
        assert len(all_clips) > 0

    def test_empty_plan(self):
        plan = {"schema_version": "1.0", "scenes": []}
        result = compile_timeline(plan)
        assert result["scenes"] == []


class TestCompileTimelineAudiobookNarrationOnly:
    def test_voice_track_only_no_music_ambience(self):
        plan = _minimal_narrative_plan()
        result = compile_timeline(
            plan, project_type="audiobook", narration_only=True,
        )
        track_ids = [t["id"] for t in result["tracks"]]
        assert track_ids == ["narrator"]
        assert result["settings"].get("narration_only") is True
        scene = result["scenes"][0]
        assert "music" not in scene.get("tracks", {})
        assert "ambience" not in scene.get("tracks", {})
        assert "narrator" in scene["tracks"]


class TestCompileTimelineJson:
    def test_returns_bytes(self):
        plan = _minimal_narrative_plan()
        data = compile_timeline_json(plan)
        assert isinstance(data, bytes)

    def test_valid_json(self):
        plan = _minimal_narrative_plan()
        data = compile_timeline_json(plan)
        parsed = orjson.loads(data)
        assert "tracks" in parsed
        assert "scenes" in parsed
