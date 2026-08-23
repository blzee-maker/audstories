"""
SFX Processing Module

Handles sound effects processing based on semantic roles.
Semantic roles define what the sound represents (impact, movement, etc.),
which is separate from mix_role (where it sits in the mix hierarchy).
"""
from typing import Optional, Dict, Tuple
from pydub import AudioSegment

from audio_engine.dsp.fade_curves import FadeCurve
from audio_engine.utils.logger import get_logger

logger = get_logger(__name__)

# Valid semantic roles
VALID_SEMANTIC_ROLES = {"impact", "movement", "ambience", "interaction", "texture"}

# LUFS targets for each semantic role
SEMANTIC_ROLE_LUFS_TARGETS = {
    "impact": -18.0,
    "movement": -20.0,
    "interaction": -20.0,
    "ambience": -22.0,
    "texture": -24.0
}

# Default fade durations (in milliseconds) for each semantic role
SEMANTIC_ROLE_FADE_DEFAULTS = {
    "impact": {
        "fade_in_ms": 0,
        "fade_out_ms": 75,  # Short fade-out for sharp attacks
        "fade_in_curve": FadeCurve.LINEAR,
        "fade_out_curve": FadeCurve.EXPONENTIAL
    },
    "movement": {
        "fade_in_ms": 150,
        "fade_out_ms": 150,
        "fade_in_curve": FadeCurve.LINEAR,
        "fade_out_curve": FadeCurve.LINEAR
    },
    "ambience": {
        "fade_in_ms": 750,
        "fade_out_ms": 750,
        "fade_in_curve": FadeCurve.LOGARITHMIC,
        "fade_out_curve": FadeCurve.LOGARITHMIC
    },
    "interaction": {
        "fade_in_ms": 250,
        "fade_out_ms": 250,
        "fade_in_curve": FadeCurve.LINEAR,
        "fade_out_curve": FadeCurve.LINEAR
    },
    "texture": {
        "fade_in_ms": 1500,
        "fade_out_ms": 1500,
        "fade_in_curve": FadeCurve.LOGARITHMIC,
        "fade_out_curve": FadeCurve.LOGARITHMIC
    }
}

# Scene energy gain ranges per semantic role (min_db at low energy, max_db at high energy)
SCENE_ENERGY_GAIN_MAP = {
    "impact": {"min_db": -1.5, "max_db": 1.5},
    "movement": {"min_db": -1.0, "max_db": 1.0},
    "ambience": {"min_db": -2.0, "max_db": 0.5},
    "interaction": {"min_db": -1.0, "max_db": 1.0},
    "texture": {"min_db": -2.5, "max_db": 0.5},
}

SCENE_ENERGY_GAIN_CLAMP = (-6.0, 3.0)


def _normalize_scene_energy(scene_energy: float) -> float:
    value = 0.5 if scene_energy is None else float(scene_energy)
    value = max(0.0, min(1.0, value))
    return value * 2.0 - 1.0


def _resolve_scene_energy_gain_range(
    semantic_role: str,
    clip_rules: Optional[Dict],
) -> Optional[Tuple[float, float]]:
    default_range = SCENE_ENERGY_GAIN_MAP.get(semantic_role)
    if not default_range:
        return None

    override = None
    if clip_rules:
        override = clip_rules.get("sfx_scene_energy_gain")

    if isinstance(override, dict) and semantic_role in override:
        override = override[semantic_role]

    if isinstance(override, (int, float)):
        max_db = abs(float(override))
        return -max_db, max_db

    if isinstance(override, (list, tuple)) and len(override) == 2:
        return float(override[0]), float(override[1])

    if isinstance(override, dict):
        min_db = override.get("min_db", override.get("min"))
        max_db = override.get("max_db", override.get("max"))
        if min_db is not None or max_db is not None:
            return (
                float(min_db if min_db is not None else default_range["min_db"]),
                float(max_db if max_db is not None else default_range["max_db"]),
            )

    return float(default_range["min_db"]), float(default_range["max_db"])


def _compute_scene_energy_gain_db(
    scene_energy: float,
    gain_range: Tuple[float, float],
) -> float:
    min_db, max_db = gain_range
    norm = _normalize_scene_energy(scene_energy)
    gain_db = min_db + (norm + 1.0) * 0.5 * (max_db - min_db)
    return max(SCENE_ENERGY_GAIN_CLAMP[0], min(SCENE_ENERGY_GAIN_CLAMP[1], gain_db))


def get_sfx_loudness_target(semantic_role: Optional[str]) -> Optional[float]:
    """
    Get LUFS target for a semantic role.
    
    Args:
        semantic_role: Semantic role string (impact, movement, etc.)
        
    Returns:
        LUFS target value, or None if role is invalid/not specified
    """
    if not semantic_role or semantic_role not in VALID_SEMANTIC_ROLES:
        return None
    
    return SEMANTIC_ROLE_LUFS_TARGETS.get(semantic_role)


def get_sfx_fade_behavior(semantic_role: Optional[str]) -> Optional[Dict]:
    """
    Get default fade behavior for a semantic role.
    
    Args:
        semantic_role: Semantic role string (impact, movement, etc.)
        
    Returns:
        Dictionary with fade_in_ms, fade_out_ms, fade_in_curve, fade_out_curve,
        or None if role is invalid/not specified
    """
    if not semantic_role or semantic_role not in VALID_SEMANTIC_ROLES:
        return None
    
    return SEMANTIC_ROLE_FADE_DEFAULTS.get(semantic_role)


def apply_sfx_timing(audio: AudioSegment, semantic_role: Optional[str]) -> AudioSegment:
    """
    Apply role-specific micro-timing adjustments (v1: minimal only).
    
    This function only performs micro-timing adjustments:
    - Attack shaping (trimming silence at start)
    - Silence trimming at end
    
    It does NOT:
    - Shift audio across timeline
    - Add auto delays
    - Change timeline positions
    
    Args:
        audio: Audio segment to process
        semantic_role: Semantic role string
        
    Returns:
        Processed audio segment
    """
    if not semantic_role or semantic_role not in VALID_SEMANTIC_ROLES:
        return audio
    
    # v1: Only minimal micro-timing
    # For impacts, trim very short silence at start/end for sharp attacks
    if semantic_role == "impact":
        # Trim up to 10ms of silence at start and end
        silence_threshold_ms = 10
        # This is a placeholder - actual implementation would analyze audio
        # For now, return audio unchanged (minimal timing in v1)
        pass
    
    # For other roles, no timing adjustments in v1
    return audio


def apply_sfx_processing(
    audio: AudioSegment,
    semantic_role: Optional[str],
    scene_energy: float = 0.5,
    clip_rules: Optional[Dict] = None
) -> AudioSegment:
    """
    Main SFX processing function.
    
    Applies semantic role-based processing including:
    - Loudness targets (via balance module, not here)
    - Micro-timing adjustments
    
    Note: Loudness is applied separately via balance module.
    This function focuses on timing and other SFX-specific processing.
    
    Args:
        audio: Audio segment to process
        semantic_role: Semantic role string (impact, movement, etc.)
        scene_energy: Scene energy value (0.0-1.0)
        clip_rules: Optional clip rules dictionary
        
    Returns:
        Processed audio segment
    """
    if audio is None:
        raise ValueError("Cannot apply SFX processing: audio is None")
    
    if not semantic_role or semantic_role not in VALID_SEMANTIC_ROLES:
        # No SFX-specific processing if role is invalid/not specified
        return audio
    
    # Apply micro-timing adjustments
    audio = apply_sfx_timing(audio, semantic_role)
    
    gain_range = _resolve_scene_energy_gain_range(semantic_role, clip_rules)
    if gain_range:
        gain_db = _compute_scene_energy_gain_db(scene_energy, gain_range)
        if gain_db != 0:
            audio = audio.apply_gain(gain_db)
    
    return audio
