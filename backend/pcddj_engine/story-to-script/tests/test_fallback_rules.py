"""Tests for story_processing.ai.fallback_rules."""

import pytest

from story_processing.ai.fallback_rules import (
    _EMOTIONS,
    _SCENE_STYLES,
    _SILENCE_INTENTS,
    _compute_action_score,
    DEFAULT_CONFIG,
    classify_heuristic,
)
from story_processing.context import StoryContext


# ---------------------------------------------------------------------------
# Invariant checker (used across multiple tests — Refinement 3)
# ---------------------------------------------------------------------------

def _assert_invariants(result: dict):
    """Assert all guardrail invariants on a classify_heuristic result."""
    assert result["primary_emotion"] in _EMOTIONS, (
        f"Invalid emotion: {result['primary_emotion']}"
    )
    assert result["scene_style"] in _SCENE_STYLES, (
        f"Invalid scene_style: {result['scene_style']}"
    )
    assert result["silence_intent"] in _SILENCE_INTENTS, (
        f"Invalid silence_intent: {result['silence_intent']}"
    )
    assert 1 <= result["energy_level"] <= 10, (
        f"energy_level out of bounds: {result['energy_level']}"
    )
    assert 1 <= result["emotion_intensity"] <= 10, (
        f"emotion_intensity out of bounds: {result['emotion_intensity']}"
    )
    assert 0.0 <= result["confidence_score"] <= 1.0, (
        f"confidence_score out of bounds: {result['confidence_score']}"
    )


# ---------------------------------------------------------------------------
# Baseline signals
# ---------------------------------------------------------------------------

def _make_signals(**overrides):
    base = {
        "emotion_scores": {"neutral": 0.5, "joy": 0.3, "sadness": 0.1, "anger": 0.05, "calm": 0.05},
        "dialogue_ratio": 0.3,
        "punctuation_score": 0.5,
        "sentence_length_variance": 4.0,
        "avg_sentence_length": 12.0,
        "short_sentence_streak": 0,
        "sentence_count": 10,
        "action_verb_density": 0.01,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# classify_heuristic tests
# ---------------------------------------------------------------------------

class TestClassifyHeuristic:
    def test_low_dialogue_returns_narrative_heavy(self):
        signals = _make_signals(dialogue_ratio=0.05, action_verb_density=0.0)
        result = classify_heuristic(signals)
        assert result["scene_style"] == "narrative_heavy"
        _assert_invariants(result)

    def test_high_dialogue_returns_dialogue_driven(self):
        signals = _make_signals(dialogue_ratio=0.6)
        result = classify_heuristic(signals)
        assert result["scene_style"] == "dialogue_driven"
        _assert_invariants(result)

    def test_empty_emotion_scores_defaults_neutral(self):
        signals = _make_signals(emotion_scores={})
        result = classify_heuristic(signals)
        assert result["primary_emotion"] == "neutral"
        _assert_invariants(result)

    def test_high_action_density(self):
        signals = _make_signals(
            action_verb_density=0.1,
            short_sentence_streak=5,
            punctuation_score=3.0,
            dialogue_ratio=0.05,
        )
        result = classify_heuristic(signals)
        assert result["scene_style"] == "action_heavy"
        _assert_invariants(result)

    def test_silence_intent_long_on_high_streak(self):
        signals = _make_signals(short_sentence_streak=6)
        result = classify_heuristic(signals)
        assert result["silence_intent"] == "long"
        _assert_invariants(result)

    def test_silence_intent_medium_on_moderate_streak(self):
        signals = _make_signals(short_sentence_streak=3)
        result = classify_heuristic(signals)
        assert result["silence_intent"] == "medium"
        _assert_invariants(result)

    def test_invariants_with_extreme_signals(self):
        """Invariants must hold even with extreme input values."""
        extreme = _make_signals(
            punctuation_score=100.0,
            sentence_length_variance=10000.0,
            action_verb_density=1.0,
            sentence_count=1000,
            short_sentence_streak=100,
        )
        result = classify_heuristic(extreme)
        _assert_invariants(result)

    def test_invariants_with_minimal_signals(self):
        """Invariants must hold with near-zero signals."""
        minimal = _make_signals(
            emotion_scores={"neutral": 0.0},
            punctuation_score=0.0,
            sentence_length_variance=0.0,
            action_verb_density=0.0,
            sentence_count=0,
            dialogue_ratio=0.0,
        )
        result = classify_heuristic(minimal)
        _assert_invariants(result)


# ---------------------------------------------------------------------------
# _compute_action_score tests
# ---------------------------------------------------------------------------

class TestComputeActionScore:
    def test_all_zero(self):
        score = _compute_action_score(0, 0.0, 0.0, DEFAULT_CONFIG)
        assert score == 0.0

    def test_capped_values(self):
        # All inputs well above cap values
        score = _compute_action_score(100, 100.0, 1.0, DEFAULT_CONFIG)
        # Each normalized component is 1.0, weighted sum = 1.0
        assert abs(score - 1.0) < 1e-6

    def test_partial(self):
        score = _compute_action_score(3, 1.5, 0.04, DEFAULT_CONFIG)
        assert 0.0 < score < 1.0


# ---------------------------------------------------------------------------
# Context-aware adjustments
# ---------------------------------------------------------------------------

class TestContextAdjustments:
    def test_energy_adjustment_capped(self):
        """Energy context shift must be <= 1.5 (Guardrail 5)."""
        signals = _make_signals()
        ctx = StoryContext(
            scene_index=5,
            total_scenes=6,
            position_ratio=5 / 6,
            prev_emotions=["anger", "anger", "anger"],
            emotion_trend="escalating",
            pacing_trend="accelerating",
            known_speakers=[],
        )
        result_with_ctx = classify_heuristic(signals, story_context=ctx)
        result_without_ctx = classify_heuristic(signals, story_context=None)

        shift = abs(result_with_ctx["energy_level"] - result_without_ctx["energy_level"])
        assert shift <= 2  # 1.5 rounded can be at most 2 integer levels
        _assert_invariants(result_with_ctx)
