from pydub import AudioSegment
from typing import Optional
from audio_engine.dsp.loudness import apply_lufs_target
from audio_engine.dsp.sfx_processor import get_sfx_loudness_target


ROLE_LUFS_TARGETS = {
    "voice": -18.0,
    "music": -28.0,
    "background": -30.0,
    "sfx": -20.0  # Generic SFX fallback
}

# Semantic role-specific targets (sfx:role format)
SEMANTIC_ROLE_LUFS_TARGETS = {
    "sfx:impact": -18.0,
    "sfx:movement": -20.0,
    "sfx:interaction": -20.0,
    "sfx:ambience": -22.0,
    "sfx:texture": -24.0
}


def apply_role_loudness(
    audio: AudioSegment,
    role: str,
    semantic_role: Optional[str] = None
) -> AudioSegment:
    """
    Apply LUFS target based on track role (mix_role) and optional semantic role.
    
    Args:
        audio: Audio segment to process
        role: Mix role (voice, music, background, sfx) - where it sits in mix hierarchy
        semantic_role: Optional semantic role (impact, movement, etc.) - what sound represents
        
    Returns:
        Audio segment with loudness applied
    """
    if audio is None:
        raise ValueError("Cannot apply role loudness: audio is None")
    
    # Check for semantic role-specific target first (for SFX)
    if semantic_role and role == "sfx":
        semantic_target = get_sfx_loudness_target(semantic_role)
        if semantic_target is not None:
            result = apply_lufs_target(audio, semantic_target)
            if result is None:
                raise ValueError("apply_lufs_target returned None")
            return result
    
    # Fall back to mix role target
    if role not in ROLE_LUFS_TARGETS:
        return audio  # Unknown role → no change

    target_lufs = ROLE_LUFS_TARGETS[role]
    result = apply_lufs_target(audio, target_lufs)
    if result is None:
        raise ValueError("apply_lufs_target returned None")
    return result
