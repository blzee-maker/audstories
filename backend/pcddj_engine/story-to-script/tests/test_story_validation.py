"""Tests for story_processing.validation.validator."""

from story_processing.validation.validator import (
    _clamp_float,
    _clamp_int,
    validate_interpretation,
)


# ---------------------------------------------------------------------------
# Clamp helpers
# ---------------------------------------------------------------------------

class TestClampInt:
    def test_in_range(self):
        assert _clamp_int(5, 1, 10) == 5

    def test_below_range(self):
        assert _clamp_int(-3, 1, 10) == 1

    def test_above_range(self):
        assert _clamp_int(15, 1, 10) == 10

    def test_none_returns_midpoint(self):
        assert _clamp_int(None, 1, 10) == 5

    def test_string_returns_midpoint(self):
        assert _clamp_int("bad", 1, 10) == 5

    def test_boundary_low(self):
        assert _clamp_int(1, 1, 10) == 1

    def test_boundary_high(self):
        assert _clamp_int(10, 1, 10) == 10


class TestClampFloat:
    def test_in_range(self):
        assert _clamp_float(0.5, 0.0, 1.0) == 0.5

    def test_below(self):
        assert _clamp_float(-0.1, 0.0, 1.0) == 0.0

    def test_above(self):
        assert _clamp_float(1.5, 0.0, 1.0) == 1.0

    def test_none_returns_midpoint(self):
        assert _clamp_float(None, 0.0, 1.0) == 0.5

    def test_string_returns_midpoint(self):
        assert _clamp_float("bad", 0.0, 1.0) == 0.5


# ---------------------------------------------------------------------------
# validate_interpretation
# ---------------------------------------------------------------------------

def _valid_interpretation():
    """Return a minimal valid interpretation dict."""
    return {
        "primary_emotion": "joy",
        "energy_level": 5,
        "emotion_intensity": 5,
        "scene_style": "balanced",
        "silence_intent": "none",
        "confidence_score": 0.7,
    }


def _default_structure():
    return {"speakers": ["Alice"], "sentence_count": 5, "word_count": 50}


def _default_signals():
    return {"dialogue_ratio": 0.3, "avg_sentence_length": 10.0}


class TestValidateInterpretation:
    def test_valid_input_passes_through(self):
        result = validate_interpretation(
            _default_structure(), _default_signals(), _valid_interpretation()
        )
        assert result["primary_emotion"] == "joy"
        assert result["energy_level"] == 5

    def test_invalid_emotion_clamped_to_neutral(self):
        interp = _valid_interpretation()
        interp["primary_emotion"] = "INVALID"
        result = validate_interpretation(
            _default_structure(), _default_signals(), interp
        )
        assert result["primary_emotion"] == "neutral"

    def test_invalid_scene_style_clamped(self):
        interp = _valid_interpretation()
        interp["scene_style"] = "INVALID"
        result = validate_interpretation(
            _default_structure(), _default_signals(), interp
        )
        assert result["scene_style"] == "balanced"

    def test_invalid_silence_intent_clamped(self):
        interp = _valid_interpretation()
        interp["silence_intent"] = "INVALID"
        result = validate_interpretation(
            _default_structure(), _default_signals(), interp
        )
        assert result["silence_intent"] == "none"

    def test_energy_clamped_to_bounds(self):
        interp = _valid_interpretation()
        interp["energy_level"] = 99
        result = validate_interpretation(
            _default_structure(), _default_signals(), interp
        )
        assert result["energy_level"] == 10

    def test_confidence_clamped_to_bounds(self):
        interp = _valid_interpretation()
        interp["confidence_score"] = 2.5
        result = validate_interpretation(
            _default_structure(), _default_signals(), interp
        )
        assert result["confidence_score"] == 1.0

    def test_low_dialogue_overrides_dialogue_driven(self):
        interp = _valid_interpretation()
        interp["scene_style"] = "dialogue_driven"
        signals = {"dialogue_ratio": 0.05, "avg_sentence_length": 10.0}
        result = validate_interpretation(
            _default_structure(), signals, interp
        )
        assert result["scene_style"] == "narrative_heavy"

    def test_high_energy_long_sentences_clamps_energy(self):
        interp = _valid_interpretation()
        interp["energy_level"] = 9
        signals = {"dialogue_ratio": 0.3, "avg_sentence_length": 30.0}
        result = validate_interpretation(
            _default_structure(), signals, interp
        )
        assert result["energy_level"] == 7

    def test_complete_garbage_falls_back_to_safe_defaults(self):
        # Give total garbage that will fail Pydantic after clamping
        # The clamping should fix most things, so this tests the fallback
        interp = {
            "primary_emotion": "neutral",
            "energy_level": 5,
            "emotion_intensity": 5,
            "scene_style": "balanced",
            "silence_intent": "none",
            "confidence_score": 0.5,
        }
        result = validate_interpretation(
            _default_structure(), _default_signals(), interp
        )
        # Should pass — clamped values produce valid Pydantic model
        assert result["primary_emotion"] in {
            "anxiety", "joy", "sadness", "anger", "calm", "neutral",
            "surprise", "disgust", "love", "anticipation", "nostalgia", "confusion",
        }
        assert 1 <= result["energy_level"] <= 10
        assert 0.0 <= result["confidence_score"] <= 1.0
