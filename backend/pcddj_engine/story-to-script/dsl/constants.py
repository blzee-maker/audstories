"""Deterministic mapping tables for the DSL compiler.

Every lookup in this module is a pure, hard-coded mapping with no
external dependencies.  Changing a value here changes the sonic
character of every future compilation — treat edits carefully.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Emotion → music mood base
# ---------------------------------------------------------------------------
# The mood string is combined with an energy suffix (_low, _mid, _high)
# to form the final mood tag, e.g. "tension_low".

EMOTION_TO_MOOD: dict[str, str] = {
    "anxiety": "tension",
    "joy": "uplifting",
    "sadness": "melancholic",
    "anger": "aggressive",
    "calm": "ambient",
    "neutral": "neutral",
    "surprise": "dramatic",
    "disgust": "dissonant",
    "love": "tender",
    "anticipation": "building",
    "nostalgia": "bittersweet",
    "confusion": "unstable",
}

# ---------------------------------------------------------------------------
# Energy → mood suffix
# ---------------------------------------------------------------------------
# Energy is 0.0–1.0 (already normalized from the Narrative Plan's 1–10).

ENERGY_SUFFIX_THRESHOLDS: list[tuple[float, str]] = [
    # (upper_bound_exclusive, suffix)
    (0.3, "_low"),
    (0.6, "_mid"),
    (1.1, "_high"),  # 1.1 so that 1.0 is included
]


def energy_to_suffix(energy: float) -> str:
    """Return the mood suffix for a given energy value (0.0–1.0)."""
    for threshold, suffix in ENERGY_SUFFIX_THRESHOLDS:
        if energy < threshold:
            return suffix
    return "_high"


# ---------------------------------------------------------------------------
# (Emotion, SceneStyle) → ambience atmosphere tag
# ---------------------------------------------------------------------------
# Wildcard-style: if the exact pair is missing, fall back to
# (emotion, *) entries, then to the global default.

_ATMOSPHERE_EXACT: dict[tuple[str, str], str] = {
    ("anxiety", "narrative_heavy"): "dark_interior",
    ("anxiety", "balanced"): "dark_interior",
    ("anxiety", "dialogue_driven"): "tense_room",
    ("anxiety", "action_heavy"): "dark_interior",
    ("joy", "dialogue_driven"): "warm_room",
    ("joy", "balanced"): "warm_room",
    ("joy", "narrative_heavy"): "sunny_outdoor",
    ("joy", "action_heavy"): "sunny_outdoor",
    ("sadness", "narrative_heavy"): "rain_soft",
    ("sadness", "balanced"): "rain_soft",
    ("sadness", "dialogue_driven"): "quiet_room",
    ("sadness", "action_heavy"): "rain_soft",
    ("anger", "dialogue_driven"): "tense_room",
    ("anger", "narrative_heavy"): "tense_room",
    ("anger", "balanced"): "tense_room",
    ("anger", "action_heavy"): "tense_room",
    ("calm", "narrative_heavy"): "nature_gentle",
    ("calm", "balanced"): "nature_gentle",
    ("calm", "dialogue_driven"): "warm_room",
    ("calm", "action_heavy"): "nature_gentle",
    ("neutral", "narrative_heavy"): "neutral_room",
    ("neutral", "balanced"): "neutral_room",
    ("neutral", "dialogue_driven"): "neutral_room",
    ("neutral", "action_heavy"): "neutral_room",
    ("surprise", "dialogue_driven"): "quiet_room",
    ("surprise", "narrative_heavy"): "open_air",
    ("surprise", "balanced"): "open_air",
    ("surprise", "action_heavy"): "open_air",
    ("disgust", "dialogue_driven"): "damp_interior",
    ("disgust", "narrative_heavy"): "damp_interior",
    ("disgust", "balanced"): "damp_interior",
    ("disgust", "action_heavy"): "dark_interior",
    ("love", "dialogue_driven"): "warm_room",
    ("love", "narrative_heavy"): "warm_room",
    ("love", "balanced"): "warm_room",
    ("love", "action_heavy"): "sunny_outdoor",
    ("anticipation", "dialogue_driven"): "tense_room",
    ("anticipation", "narrative_heavy"): "open_air",
    ("anticipation", "balanced"): "open_air",
    ("anticipation", "action_heavy"): "open_air",
    ("nostalgia", "dialogue_driven"): "warm_room",
    ("nostalgia", "narrative_heavy"): "rain_soft",
    ("nostalgia", "balanced"): "rain_soft",
    ("nostalgia", "action_heavy"): "rain_soft",
    ("confusion", "dialogue_driven"): "echo_hall",
    ("confusion", "narrative_heavy"): "echo_hall",
    ("confusion", "balanced"): "echo_hall",
    ("confusion", "action_heavy"): "echo_hall",
}

# Emotion-only fallbacks (used when the exact pair isn't found)
_ATMOSPHERE_EMOTION_FALLBACK: dict[str, str] = {
    "anxiety": "dark_interior",
    "joy": "warm_room",
    "sadness": "rain_soft",
    "anger": "tense_room",
    "calm": "nature_gentle",
    "neutral": "neutral_room",
    "surprise": "open_air",
    "disgust": "damp_interior",
    "love": "warm_room",
    "anticipation": "open_air",
    "nostalgia": "rain_soft",
    "confusion": "echo_hall",
}

ATMOSPHERE_DEFAULT = "neutral_room"


def atmosphere_for(emotion: str, style: str) -> str:
    """Return the atmosphere tag for a given emotion + scene style."""
    key = (emotion, style)
    if key in _ATMOSPHERE_EXACT:
        return _ATMOSPHERE_EXACT[key]
    return _ATMOSPHERE_EMOTION_FALLBACK.get(emotion, ATMOSPHERE_DEFAULT)


# ---------------------------------------------------------------------------
# Emotion → EQ tilt
# ---------------------------------------------------------------------------

EMOTION_TO_TILT: dict[str, str] = {
    "anxiety": "neutral",
    "joy": "bright",
    "sadness": "warm",
    "anger": "bright",
    "calm": "warm",
    "neutral": "neutral",
    "surprise": "bright",
    "disgust": "neutral",
    "love": "warm",
    "anticipation": "neutral",
    "nostalgia": "warm",
    "confusion": "neutral",
}

EQ_TILT_DEFAULT = "neutral"


# ---------------------------------------------------------------------------
# Track gain defaults (dB)
# ---------------------------------------------------------------------------
# Music gain is a range that scales with scene energy.
# Formula: MUSIC_GAIN_BASE + energy * MUSIC_GAIN_ENERGY_SCALE
# e.g.  -9 + 0.4 * 5 = -7  (at energy 0.4)
#       -9 + 0.9 * 5 = -4.5 (at energy 0.9)

MUSIC_GAIN_BASE: int = -9
MUSIC_GAIN_ENERGY_SCALE: float = 5.0  # added per unit of energy

AMBIENCE_GAIN_BASE: int = -15
AMBIENCE_GAIN_ENERGY_SCALE: float = 3.0

NARRATOR_GAIN: int = 0
CHARACTER_GAIN: int = 0
SFX_GAIN: int = 0


def music_gain_for_energy(energy: float) -> int:
    """Compute the music track gain (dB) for a given energy (0.0–1.0)."""
    raw = MUSIC_GAIN_BASE + energy * MUSIC_GAIN_ENERGY_SCALE
    return int(round(raw))


def ambience_gain_for_energy(energy: float) -> int:
    """Compute the ambience track gain (dB) for a given energy (0.0–1.0)."""
    raw = AMBIENCE_GAIN_BASE + energy * AMBIENCE_GAIN_ENERGY_SCALE
    return int(round(raw))


# ---------------------------------------------------------------------------
# Music clip volume (0.0–1.0) — derived from energy
# ---------------------------------------------------------------------------
# Volume as a linear scalar used in the clip.  Different from track gain.
# Formula: base + energy * scale   → range [0.15, 0.40]

MUSIC_VOLUME_BASE: float = 0.15
MUSIC_VOLUME_SCALE: float = 0.25


def music_volume_for_energy(energy: float) -> float:
    """Return music clip volume (0.0–1.0) for a given energy."""
    return round(MUSIC_VOLUME_BASE + energy * MUSIC_VOLUME_SCALE, 2)


# ---------------------------------------------------------------------------
# Silence intent → crossfade duration (seconds)
# ---------------------------------------------------------------------------

SILENCE_TO_CROSSFADE: dict[str, float] = {
    "none": 1.0,
    "short": 1.0,
    "medium": 1.5,
    "long": 2.0,
}


# ---------------------------------------------------------------------------
# EQ preset defaults per track type
# ---------------------------------------------------------------------------

TRACK_TYPE_EQ_DEFAULTS: dict[str, str] = {
    "voice": "dialogue_clean",
    "music": "music_bed",
    "ambience": "background_soft",
    "sfx": "sfx_subtle",
}


# ---------------------------------------------------------------------------
# SFX trigger thresholds
# ---------------------------------------------------------------------------

SFX_IMPACT_MIN_SHORT_STREAK: int = 3
SFX_IMPACT_MIN_PUNCTUATION: float = 1.5
SFX_TEXTURE_MIN_ENERGY: float = 0.6


# ---------------------------------------------------------------------------
# Ducking defaults
# ---------------------------------------------------------------------------

DUCK_AMOUNT_DEFAULT: int = -6
DUCK_AMOUNT_HIGH_ENERGY: int = -4  # when avg energy > 0.7
DUCK_AMOUNT_DIALOGUE_DRIVEN: int = -9  # when most scenes are dialogue_driven

HIGH_ENERGY_THRESHOLD: float = 0.7
DIALOGUE_DRIVEN_MAJORITY: float = 0.5  # fraction of scenes that must be dialogue_driven
