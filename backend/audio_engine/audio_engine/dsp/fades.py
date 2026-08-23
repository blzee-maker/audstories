from pydub import AudioSegment
import numpy as np
import array

from audio_engine.dsp.fade_curves import FadeCurve, generate_fade_curve


def _apply_custom_fade(
    audio: AudioSegment,
    fade_ms: int,
    fade_in: bool,
    curve: FadeCurve = FadeCurve.LINEAR
) -> AudioSegment:
    """
    Apply a custom fade curve to an audio segment.
    
    Args:
        audio: Audio segment to fade
        fade_ms: Duration of fade in milliseconds
        fade_in: If True, fade in (0 to 1); if False, fade out (1 to 0)
        curve: Type of fade curve to apply
        
    Returns:
        Faded audio segment
    """
    if fade_ms <= 0 or len(audio) == 0:
        return audio
    
    # For linear curves, use pydub's optimized fade for performance
    if curve == FadeCurve.LINEAR:
        if fade_in:
            return audio.fade_in(fade_ms)
        else:
            return audio.fade_out(fade_ms)
    
    # For custom curves, use numpy-based implementation
    fade_ms = min(fade_ms, len(audio))
    
    # Get number of samples in the fade
    samples_per_ms = audio.frame_rate / 1000.0
    num_fade_samples = int(fade_ms * samples_per_ms)
    
    if num_fade_samples <= 0:
        return audio
    
    # Generate fade curve
    gain_curve = generate_fade_curve(curve, num_fade_samples, fade_in)
    
    # Convert audio to numpy array
    sample_array = audio.get_array_of_samples()
    samples = np.array(sample_array, dtype=np.int32)
    
    # Handle mono vs stereo
    is_stereo = audio.channels > 1
    if is_stereo:
        samples = samples.reshape((-1, audio.channels))
    
    # Calculate sample indices for fade region
    if fade_in:
        fade_start_idx = 0
        fade_end_idx = num_fade_samples
    else:
        fade_start_idx = len(samples) - num_fade_samples
        fade_end_idx = len(samples)
    
    # Apply fade curve to samples (convert to float, apply gain, convert back)
    fade_region = samples[fade_start_idx:fade_end_idx].copy()
    
    if is_stereo:
        # Apply gain curve to each channel
        for ch in range(audio.channels):
            fade_region[:, ch] = np.round(fade_region[:, ch].astype(np.float64) * gain_curve).astype(np.int32)
    else:
        # Mono: apply gain curve directly
        fade_region = np.round(fade_region.astype(np.float64) * gain_curve).astype(np.int32)
    
    samples[fade_start_idx:fade_end_idx] = fade_region
    
    # Convert back to array.array format
    if is_stereo:
        samples = samples.flatten()
    
    # Clamp values based on sample width
    max_val = 2 ** (8 * audio.sample_width - 1)
    if audio.sample_width == 1:
        # 8-bit: unsigned (0-255), pydub stores as signed with bias
        samples = np.clip(samples, -128, 127)
        array_type = 'b'  # signed char
    elif audio.sample_width == 2:
        # 16-bit: signed (-32768 to 32767)
        samples = np.clip(samples, -32768, 32767)
        array_type = 'h'  # signed short
    elif audio.sample_width == 4:
        # 32-bit: signed
        samples = np.clip(samples, -2147483648, 2147483647)
        array_type = 'i'  # signed int
    else:
        # Fallback: use pydub's fade
        if fade_in:
            return audio.fade_in(fade_ms)
        else:
            return audio.fade_out(fade_ms)
    
    # Convert to array.array (need to convert numpy array to list first)
    result_array = array.array(array_type, samples.astype(np.int32).tolist())
    
    # Create new AudioSegment from modified data
    return audio._spawn(
        data=result_array.tobytes(),
        overrides={
            "sample_width": audio.sample_width,
            "frame_rate": audio.frame_rate,
            "channels": audio.channels
        }
    )


def apply_fade_in(
    canvas: AudioSegment,
    start_ms: int,
    fade_ms: int,
    curve: FadeCurve = FadeCurve.LINEAR
) -> AudioSegment:
    """
    Apply a fade-in on the canvas starting at start_ms.
    
    Args:
        canvas: Audio canvas to apply fade to
        start_ms: Start position in milliseconds
        fade_ms: Duration of fade in milliseconds
        curve: Type of fade curve (default: LINEAR for backward compatibility)
        
    Returns:
        Canvas with fade-in applied
    """
    if fade_ms <= 0:
        return canvas

    before = canvas[:start_ms]
    middle = canvas[start_ms:start_ms + fade_ms]
    after = canvas[start_ms + fade_ms:]
    
    # Apply custom fade to middle segment
    middle = _apply_custom_fade(middle, fade_ms, fade_in=True, curve=curve)

    return before + middle + after


def apply_fade_out(
    canvas: AudioSegment,
    clip_start_ms: int,
    clip_len_ms: int,
    project_len_ms: int,
    fade_ms: int,
    curve: FadeCurve = FadeCurve.LINEAR
) -> AudioSegment:
    """
    Apply a fade-out at the end of a clip on the canvas.
    
    Args:
        canvas: Audio canvas to apply fade to
        clip_start_ms: Start position of clip in milliseconds
        clip_len_ms: Length of clip in milliseconds
        project_len_ms: Total project length in milliseconds
        fade_ms: Duration of fade in milliseconds
        curve: Type of fade curve (default: LINEAR for backward compatibility)
        
    Returns:
        Canvas with fade-out applied
    """
    if fade_ms <= 0:
        return canvas

    clip_end_ms = min(
        clip_start_ms + clip_len_ms,
        project_len_ms
    )

    fade_ms = min(fade_ms, clip_end_ms - clip_start_ms)
    if fade_ms <= 0:
        return canvas

    before = canvas[:clip_end_ms - fade_ms]
    middle = canvas[clip_end_ms - fade_ms:clip_end_ms]
    after = canvas[clip_end_ms:]
    
    # Apply custom fade to middle segment
    middle = _apply_custom_fade(middle, fade_ms, fade_in=False, curve=curve)

    return before + middle + after