"""
EQ Preset Definitions - Intent-based EQ configurations.

Presets expose semantic names to timeline authors while keeping
frequency knowledge internal. Authors describe what they want
(e.g., "dialogue_clean"), not how to achieve it.

Versioning allows preset curves to evolve without breaking old renders.
"""
from typing import Dict, Any, Optional


# =============================================================================
# Primary Band Constraints (Prevent Surgical Drift)
# =============================================================================
# These constraints keep presets broad and musical, not surgical.
# Enforced in apply_primary_band() in eq.py

PRIMARY_BAND_Q_MIN = 0.7      # Wide enough to be musical
PRIMARY_BAND_Q_MAX = 1.2      # Not narrow notches
PRIMARY_BAND_GAIN_MAX = 3.0   # ±3 dB max - gentle shaping
PRIMARY_BAND_FREQ_MIN = 80    # Hz - audible range start
PRIMARY_BAND_FREQ_MAX = 8000  # Hz - where broad shaping matters


# =============================================================================
# Versioned Preset Definitions
# =============================================================================
# Internal format: "preset_name@version"
# Each preset contains:
#   - high_pass: cutoff frequency in Hz (optional)
#   - low_pass: cutoff frequency in Hz (optional)
#   - primary: dict with freq, gain, q for the primary band (optional)

EQ_PRESETS: Dict[str, Dict[str, Any]] = {
    # -------------------------------------------------------------------------
    # Dialogue Presets
    # -------------------------------------------------------------------------
    "dialogue_clean@v1": {
        "high_pass": 80,
        "primary": {"freq": 3000, "gain": 2.0, "q": 1.0}
    },
    "dialogue_warm@v1": {
        "high_pass": 60,
        "primary": {"freq": 200, "gain": 1.0, "q": 0.8}
    },
    "dialogue_broadcast@v1": {
        "high_pass": 100,
        "primary": {"freq": 3000, "gain": 3.0, "q": 1.0}
        # Note: Original plan mentioned -1dB @ 200Hz, but v1 limits to single primary band
        # Multi-band can be added in v2
    },
    
    # -------------------------------------------------------------------------
    # Music Presets
    # -------------------------------------------------------------------------
    "music_full@v1": {
        "high_pass": 40
        # No primary band - let music breathe
    },
    "music_bed@v1": {
        "high_pass": 80,
        "low_pass": 12000,
        "primary": {"freq": 2500, "gain": -2.0, "q": 0.8}  # Carve space for dialogue
    },
    
    # -------------------------------------------------------------------------
    # Background/Ambience Presets
    # -------------------------------------------------------------------------
    "background_soft@v1": {
        "high_pass": 100,
        "low_pass": 8000
        # No primary band - just filtering
    },
    "background_distant@v1": {
        "high_pass": 150,
        "low_pass": 6000,
        "primary": {"freq": 1000, "gain": -2.0, "q": 0.7}  # Reduce presence
    },
    
    # -------------------------------------------------------------------------
    # SFX Presets
    # -------------------------------------------------------------------------
    "sfx_punch@v1": {
        "high_pass": 60,
        "primary": {"freq": 100, "gain": 2.0, "q": 0.8}  # Low-end impact
    },
    "sfx_subtle@v1": {
        "high_pass": 80,
        "low_pass": 10000
        # No primary band - gentle filtering only
    },
}


# =============================================================================
# Preset Aliases (Timeline-Friendly Names)
# =============================================================================
# Maps what timeline authors use → internal versioned name
# When upgrading presets, update the alias to point to new version

PRESET_ALIASES: Dict[str, str] = {
    "dialogue_clean": "dialogue_clean@v1",
    "dialogue_warm": "dialogue_warm@v1",
    "dialogue_broadcast": "dialogue_broadcast@v1",
    "music_full": "music_full@v1",
    "music_bed": "music_bed@v1",
    "background_soft": "background_soft@v1",
    "background_distant": "background_distant@v1",
    "sfx_punch": "sfx_punch@v1",
    "sfx_subtle": "sfx_subtle@v1",
}


# =============================================================================
# Role-Based Default Presets
# =============================================================================
# When no eq_preset is specified, roles get sensible defaults automatically

ROLE_DEFAULT_PRESETS: Dict[str, str] = {
    "voice": "dialogue_clean",
    "music": "music_bed",
    "background": "background_soft",
    # "sfx" intentionally omitted - varies too much, use semantic_role instead
}


# =============================================================================
# SFX Semantic Role → Preset Mapping
# =============================================================================
# Maps semantic roles to their default EQ presets

SFX_SEMANTIC_ROLE_PRESETS: Dict[str, str] = {
    "impact": "sfx_punch",
    "movement": "sfx_subtle",
    "ambience": "background_soft",
    "interaction": None,  # No default - too varied
    "texture": "background_distant",
}


# =============================================================================
# Scene-Level Tilt Presets
# =============================================================================
# Tilt applies a gentle slope across the frequency spectrum
# These are applied post-mix at scene level for broad tonal shaping

TILT_PRESETS: Dict[str, Dict[str, float]] = {
    "warm": {
        "low_shelf_freq": 200,
        "low_shelf_gain": 1.5,    # +1.5 dB below 200Hz
        "high_shelf_freq": 4000,
        "high_shelf_gain": -1.5,  # -1.5 dB above 4kHz
    },
    "neutral": {
        # No adjustments
    },
    "bright": {
        "low_shelf_freq": 200,
        "low_shelf_gain": -1.0,   # -1 dB below 200Hz
        "high_shelf_freq": 4000,
        "high_shelf_gain": 2.0,   # +2 dB above 4kHz
    },
}


# =============================================================================
# Helper Functions
# =============================================================================

def resolve_preset_version(preset_name: str) -> str:
    """
    Resolve a preset name to its versioned internal name.
    
    Args:
        preset_name: User-facing preset name (e.g., "dialogue_clean")
                     or already-versioned name (e.g., "dialogue_clean@v1")
    
    Returns:
        Versioned preset name (e.g., "dialogue_clean@v1")
    
    Raises:
        ValueError: If preset name is unknown
    """
    # Already versioned?
    if "@" in preset_name:
        if preset_name in EQ_PRESETS:
            return preset_name
        raise ValueError(f"Unknown versioned preset: {preset_name}")
    
    # Look up alias
    if preset_name in PRESET_ALIASES:
        return PRESET_ALIASES[preset_name]
    
    raise ValueError(f"Unknown preset: {preset_name}")


def get_preset_config(preset_name: str) -> Dict[str, Any]:
    """
    Get the configuration dictionary for a preset.
    
    Args:
        preset_name: User-facing or versioned preset name
    
    Returns:
        Preset configuration dictionary
    
    Raises:
        ValueError: If preset name is unknown
    """
    versioned_name = resolve_preset_version(preset_name)
    return EQ_PRESETS[versioned_name].copy()


def get_preset_for_role(role: str, semantic_role: Optional[str] = None) -> Optional[str]:
    """
    Get the default EQ preset for a role and optional semantic role.
    
    Args:
        role: Mix role (voice, music, background, sfx)
        semantic_role: Optional semantic role for SFX (impact, movement, etc.)
    
    Returns:
        Preset name or None if no default exists
    """
    # For SFX, check semantic role first
    if role == "sfx" and semantic_role:
        preset = SFX_SEMANTIC_ROLE_PRESETS.get(semantic_role)
        if preset:
            return preset
    
    # Fall back to role-based default
    return ROLE_DEFAULT_PRESETS.get(role)


def get_tilt_config(tilt_name: str) -> Dict[str, float]:
    """
    Get the configuration for a tilt preset.
    
    Args:
        tilt_name: Tilt preset name ("warm", "neutral", "bright")
    
    Returns:
        Tilt configuration dictionary
    
    Raises:
        ValueError: If tilt name is unknown
    """
    if tilt_name not in TILT_PRESETS:
        raise ValueError(f"Unknown tilt preset: {tilt_name}. Valid options: {list(TILT_PRESETS.keys())}")
    return TILT_PRESETS[tilt_name].copy()
