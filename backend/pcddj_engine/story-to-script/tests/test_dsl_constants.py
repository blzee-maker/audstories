"""Tests for dsl.constants."""

import pytest

from dsl.constants import (
    ATMOSPHERE_DEFAULT,
    EMOTION_TO_MOOD,
    EMOTION_TO_TILT,
    _ATMOSPHERE_EMOTION_FALLBACK,
    ambience_gain_for_energy,
    atmosphere_for,
    energy_to_suffix,
    music_gain_for_energy,
    music_volume_for_energy,
)
from story_processing.validation.schema import EmotionType

# Extract the allowed emotion strings from the Literal type
_ALL_EMOTIONS: tuple[str, ...] = EmotionType.__args__  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# energy_to_suffix boundary tests
# ---------------------------------------------------------------------------

class TestEnergyToSuffix:
    def test_zero(self):
        assert energy_to_suffix(0.0) == "_low"

    def test_just_below_030(self):
        assert energy_to_suffix(0.29) == "_low"

    def test_exactly_030(self):
        assert energy_to_suffix(0.3) == "_mid"

    def test_just_below_060(self):
        assert energy_to_suffix(0.59) == "_mid"

    def test_exactly_060(self):
        assert energy_to_suffix(0.6) == "_high"

    def test_one(self):
        assert energy_to_suffix(1.0) == "_high"


# ---------------------------------------------------------------------------
# atmosphere_for
# ---------------------------------------------------------------------------

class TestAtmosphereFor:
    def test_exact_match(self):
        assert atmosphere_for("anxiety", "narrative_heavy") == "dark_interior"

    def test_emotion_fallback(self):
        # "surprise" is now in the exact table → should NOT fall back to default
        result = atmosphere_for("surprise", "balanced")
        assert result == "open_air"

    def test_known_emotion_unknown_style(self):
        # "joy" with an unknown style should fall back to emotion-only
        result = atmosphere_for("joy", "totally_unknown")
        assert result == "warm_room"

    def test_unknown_both(self):
        result = atmosphere_for("unknown_emotion", "unknown_style")
        assert result == ATMOSPHERE_DEFAULT


# ---------------------------------------------------------------------------
# Gain functions
# ---------------------------------------------------------------------------

class TestGainFunctions:
    def test_music_gain_at_zero(self):
        assert music_gain_for_energy(0.0) == -9

    def test_music_gain_at_one(self):
        # -9 + 1.0 * 5 = -4
        assert music_gain_for_energy(1.0) == -4

    def test_ambience_gain_at_zero(self):
        assert ambience_gain_for_energy(0.0) == -15

    def test_ambience_gain_at_one(self):
        # -15 + 1.0 * 3 = -12
        assert ambience_gain_for_energy(1.0) == -12

    def test_music_volume_at_zero(self):
        assert music_volume_for_energy(0.0) == 0.15

    def test_music_volume_at_one(self):
        assert music_volume_for_energy(1.0) == 0.40


# ---------------------------------------------------------------------------
# Drift-guard: every emotion in the schema must have a mapping
# ---------------------------------------------------------------------------

class TestEmotionMappingCompleteness:
    """Ensure all 12 schema emotions are covered in every DSL lookup table."""

    @pytest.mark.parametrize("emotion", _ALL_EMOTIONS)
    def test_emotion_to_mood_complete(self, emotion: str):
        assert emotion in EMOTION_TO_MOOD, (
            f"{emotion!r} missing from EMOTION_TO_MOOD"
        )

    @pytest.mark.parametrize("emotion", _ALL_EMOTIONS)
    def test_atmosphere_emotion_fallback_complete(self, emotion: str):
        assert emotion in _ATMOSPHERE_EMOTION_FALLBACK, (
            f"{emotion!r} missing from _ATMOSPHERE_EMOTION_FALLBACK"
        )

    @pytest.mark.parametrize("emotion", _ALL_EMOTIONS)
    def test_emotion_to_tilt_complete(self, emotion: str):
        assert emotion in EMOTION_TO_TILT, (
            f"{emotion!r} missing from EMOTION_TO_TILT"
        )


# ---------------------------------------------------------------------------
# Spot-checks for newly added emotions
# ---------------------------------------------------------------------------

class TestNewEmotionMappings:
    def test_love_atmosphere_balanced(self):
        assert atmosphere_for("love", "balanced") == "warm_room"

    def test_nostalgia_atmosphere_narrative(self):
        assert atmosphere_for("nostalgia", "narrative_heavy") == "rain_soft"

    def test_confusion_atmosphere_dialogue(self):
        assert atmosphere_for("confusion", "dialogue_driven") == "echo_hall"

    def test_surprise_atmosphere_action(self):
        assert atmosphere_for("surprise", "action_heavy") == "open_air"

    def test_disgust_atmosphere_action(self):
        assert atmosphere_for("disgust", "action_heavy") == "dark_interior"

    def test_anticipation_atmosphere_fallback(self):
        # Unknown style should fall back to emotion-only entry
        assert atmosphere_for("anticipation", "totally_unknown") == "open_air"
