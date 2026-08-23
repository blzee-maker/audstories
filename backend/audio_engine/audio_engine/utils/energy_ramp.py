from typing import Optional
from pydub import AudioSegment
from audio_engine.utils.energy import energy_to_music_gain


def interpolate_gain(start_gain: float, end_gain: float, progress: float) -> float:
    """
    Linear interpolation between two gain values.
    progress: 0.0 → start_gain, 1.0 → end_gain
    """
    progress = max(0.0, min(1.0, progress))
    return start_gain + (end_gain - start_gain) * progress


def apply_energy_ramp(
    audio: AudioSegment,
    scene_energy: float,
    prev_energy: Optional[float],
    ramp_duration_ms: int,
    track_role: str
) -> AudioSegment:
    """
    Apply energy-based gain ramping to audio for background/music tracks.
    
    Args:
        audio: Audio segment to process
        scene_energy: Current scene energy (0.0-1.0)
        prev_energy: Previous scene energy (None if first scene)
        ramp_duration_ms: Duration of ramp transition in milliseconds
        track_role: Track role (only "background" or "music" are processed)
    
    Returns:
        Processed audio segment with energy-based gain applied
    """
    # Only process background and music tracks
    if track_role not in ("background", "music"):
        return audio
    
    target_gain = energy_to_music_gain(scene_energy)
    
    # If no previous energy, just apply target gain
    if prev_energy is None:
        return audio + target_gain
    
    # Calculate starting gain from previous energy
    start_gain = energy_to_music_gain(prev_energy)
    
    # Ensure ramp duration doesn't exceed audio length
    ramp_duration_ms = min(ramp_duration_ms, len(audio))
    
    if ramp_duration_ms <= 0:
        # No ramp possible, just apply target gain
        return audio + target_gain
    
    # Split audio into ramp portion and rest
    ramp_part = audio[:ramp_duration_ms]
    rest_part = audio[ramp_duration_ms:]
    
    # Apply starting gain to ramp portion
    ramp_part = ramp_part + start_gain
    
    # Apply fade based on gain direction
    gain_delta = target_gain - start_gain
    if gain_delta < 0:
        # Decreasing gain: fade out
        ramp_part = ramp_part.fade_out(ramp_duration_ms)
    else:
        # Increasing gain: fade in
        ramp_part = ramp_part.fade_in(ramp_duration_ms)
    
    # Apply final target gain to rest of audio
    rest_part = rest_part + target_gain
    
    # Combine ramp and rest
    return ramp_part + rest_part
