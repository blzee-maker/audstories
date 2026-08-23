"""Tests for story_processing.narrative_plan."""

import orjson

from story_processing.narrative_plan import assemble, serialize


def _valid_scene_data():
    return {
        "scene_id": "scene_001_abc12345",
        "structure": {
            "scene_id": "scene_001_abc12345",
            "sentence_count": 3,
            "word_count": 20,
            "sentences": ["First.", "Second.", "Third."],
            "dialogue_turns": [],
            "speakers": [],
        },
        "signals": {
            "avg_sentence_length": 6.7,
            "sentence_length_variance": 1.0,
            "short_sentence_streak": 0,
            "punctuation_score": 0.0,
            "action_verb_density": 0.0,
            "dialogue_ratio": 0.0,
            "dialogue_turn_count": 0,
            "avg_dialogue_length": 0.0,
            "emotion_scores": {"neutral": 0.5, "joy": 0.3, "sadness": 0.1,
                               "anger": 0.0, "calm": 0.0, "anxiety": 0.0,
                               "surprise": 0.0, "disgust": 0.0, "love": 0.0,
                               "anticipation": 0.0, "nostalgia": 0.0, "confusion": 0.0},
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
    }


class TestAssemble:
    def test_valid_data(self):
        plan = assemble([_valid_scene_data()])
        assert plan["schema_version"] == "1.0"
        assert len(plan["scenes"]) == 1
        assert plan["scenes"][0]["scene_id"] == "scene_001_abc12345"

    def test_empty_scenes(self):
        plan = assemble([])
        assert plan["schema_version"] == "1.0"
        assert plan["scenes"] == []

    def test_multiple_scenes(self):
        sd1 = _valid_scene_data()
        sd2 = _valid_scene_data()
        sd2["scene_id"] = "scene_002_def67890"
        sd2["structure"]["scene_id"] = "scene_002_def67890"
        plan = assemble([sd1, sd2])
        assert len(plan["scenes"]) == 2


class TestSerialize:
    def test_produces_valid_json(self):
        plan = assemble([_valid_scene_data()])
        data = serialize(plan)
        assert isinstance(data, bytes)
        parsed = orjson.loads(data)
        assert parsed["schema_version"] == "1.0"

    def test_empty_plan(self):
        plan = assemble([])
        data = serialize(plan)
        parsed = orjson.loads(data)
        assert parsed["scenes"] == []
