"""Tests for story_processing.ai.classifier.

Mock discipline: only LLMClient.complete return value is mocked.
All classifier logic (retry, JSON parsing, fallback) executes fully.
"""

import json

from story_processing.ai.classifier import classify

# Re-use the MockLLMClient from conftest
from tests.conftest import MockLLMClient


def _base_signals():
    return {
        "emotion_scores": {"neutral": 0.5, "joy": 0.3},
        "dialogue_ratio": 0.3,
        "punctuation_score": 0.5,
        "sentence_length_variance": 4.0,
        "avg_sentence_length": 12.0,
        "short_sentence_streak": 0,
        "sentence_count": 10,
        "action_verb_density": 0.01,
    }


class TestClassify:
    def test_no_llm_uses_heuristic(self):
        result = classify(_base_signals(), llm_client=None)
        assert "primary_emotion" in result
        assert "energy_level" in result
        assert "confidence_score" in result

    def test_valid_llm_response(self):
        response = json.dumps({
            "primary_emotion": "joy",
            "energy_level": 7,
            "emotion_intensity": 6,
            "scene_style": "balanced",
            "silence_intent": "none",
            "confidence_score": 0.9,
        })
        client = MockLLMClient(response=response)
        result = classify(_base_signals(), llm_client=client)
        assert result["primary_emotion"] == "joy"
        assert result["confidence_score"] >= 0.85
        assert client.call_count == 1

    def test_invalid_json_triggers_retry_then_fallback(self):
        client = MockLLMClient(response="not valid json at all")
        result = classify(_base_signals(), llm_client=client)
        # Should have called complete twice (first try + retry), then fallen back
        assert client.call_count == 2
        # Result should be from heuristic fallback
        assert "primary_emotion" in result
        assert "energy_level" in result

    def test_missing_keys_triggers_retry(self):
        # Valid JSON but missing required keys
        response = json.dumps({"primary_emotion": "joy"})
        client = MockLLMClient(response=response)
        result = classify(_base_signals(), llm_client=client)
        assert client.call_count == 2  # first try + retry, then fallback
        assert "energy_level" in result

    def test_llm_result_has_all_required_keys(self):
        response = json.dumps({
            "primary_emotion": "sadness",
            "energy_level": 3,
            "emotion_intensity": 8,
            "scene_style": "narrative_heavy",
            "silence_intent": "medium",
            "confidence_score": 0.75,
        })
        client = MockLLMClient(response=response)
        result = classify(_base_signals(), llm_client=client)
        required = {
            "primary_emotion", "energy_level", "emotion_intensity",
            "scene_style", "silence_intent", "confidence_score",
        }
        assert required.issubset(result.keys())
