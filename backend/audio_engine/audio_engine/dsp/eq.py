"""
EQ (Equalization) DSP Module - Frequency shaping for audio.

This module provides intent-based EQ through semantic presets while
keeping frequency knowledge internal. Timeline authors use preset names
like "dialogue_clean", and the engine handles the DSP details.

Processing Order (in clip_processor.py):
1. Load audio
2. Apply track/clip gain
3. **Apply EQ (this module)** ← role preset or explicit
4. Apply SFX processing
5. Apply energy ramp
6. Apply ducking
7. Apply compression
8. Overlay to canvas
9. Apply scene-level tonal shaping (this module)
10. Apply fades
"""
import numpy as np
from typing import Optional, Dict, Any
from pydub import AudioSegment
from scipy import signal

from audio_engine.utils.logger import get_logger
from audio_engine.dsp.eq_presets import (
    EQ_PRESETS,
    PRESET_ALIASES,
    TILT_PRESETS,
    PRIMARY_BAND_Q_MIN,
    PRIMARY_BAND_Q_MAX,
    PRIMARY_BAND_GAIN_MAX,
    PRIMARY_BAND_FREQ_MIN,
    PRIMARY_BAND_FREQ_MAX,
    resolve_preset_version,
    get_preset_config,
    get_preset_for_role,
    get_tilt_config,
)

logger = get_logger(__name__)


# =============================================================================
# Audio Conversion Utilities
# =============================================================================

def _audiosegment_to_numpy(audio: AudioSegment) -> np.ndarray:
    """
    Convert AudioSegment to numpy float32 array normalized to [-1, 1].
    
    Returns:
        numpy array of shape (samples,) for mono or (samples, channels) for stereo
    """
    samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
    
    # Normalize to [-1, 1] based on bit depth
    max_val = 2 ** (8 * audio.sample_width - 1)
    samples = samples / max_val
    
    # Reshape for stereo
    if audio.channels > 1:
        samples = samples.reshape((-1, audio.channels))
    
    return samples


def _numpy_to_audiosegment(
    samples: np.ndarray,
    sample_rate: int,
    sample_width: int,
    channels: int
) -> AudioSegment:
    """
    Convert numpy float32 array back to AudioSegment.
    
    Args:
        samples: numpy array normalized to [-1, 1]
        sample_rate: Sample rate in Hz
        sample_width: Bytes per sample (1, 2, or 4)
        channels: Number of channels
    
    Returns:
        AudioSegment
    """
    # Clip to prevent overflow
    samples = np.clip(samples, -1.0, 1.0)
    
    # Flatten stereo back to interleaved
    if channels > 1 and samples.ndim > 1:
        samples = samples.flatten()
    
    # Scale back to integer range
    max_val = 2 ** (8 * sample_width - 1) - 1
    
    # Determine the appropriate dtype based on sample_width
    if sample_width == 1:
        dtype = np.int8
    elif sample_width == 2:
        dtype = np.int16
    elif sample_width == 4:
        dtype = np.int32
    else:
        dtype = np.int16
    
    samples_int = (samples * max_val).astype(dtype)
    
    return AudioSegment(
        data=samples_int.tobytes(),
        sample_width=sample_width,
        frame_rate=sample_rate,
        channels=channels
    )


# =============================================================================
# Core Filter Functions (Internal)
# =============================================================================

def apply_high_pass(audio: AudioSegment, cutoff_hz: float, order: int = 2) -> AudioSegment:
    """
    Apply a high-pass (low-cut) filter to remove frequencies below cutoff.
    
    Args:
        audio: Input audio segment
        cutoff_hz: Cutoff frequency in Hz
        order: Filter order (default 2 for gentle slope)
    
    Returns:
        Filtered audio segment
    """
    if audio is None:
        raise ValueError("Cannot apply high-pass filter: audio is None")
    
    if cutoff_hz <= 0:
        return audio
    
    sample_rate = audio.frame_rate
    
    # Ensure cutoff is below Nyquist
    nyquist = sample_rate / 2
    if cutoff_hz >= nyquist:
        logger.warning(f"High-pass cutoff {cutoff_hz}Hz >= Nyquist {nyquist}Hz, skipping filter")
        return audio
    
    # Normalize cutoff frequency
    normalized_cutoff = cutoff_hz / nyquist
    
    # Design Butterworth high-pass filter
    b, a = signal.butter(order, normalized_cutoff, btype='high')
    
    # Convert to numpy
    samples = _audiosegment_to_numpy(audio)
    
    # Apply filter (handle mono and stereo)
    if samples.ndim == 1:
        filtered = signal.filtfilt(b, a, samples)
    else:
        # Filter each channel separately
        filtered = np.zeros_like(samples)
        for ch in range(samples.shape[1]):
            filtered[:, ch] = signal.filtfilt(b, a, samples[:, ch])
    
    # Convert back to AudioSegment
    return _numpy_to_audiosegment(
        filtered.astype(np.float32),
        audio.frame_rate,
        audio.sample_width,
        audio.channels
    )


def apply_low_pass(audio: AudioSegment, cutoff_hz: float, order: int = 2) -> AudioSegment:
    """
    Apply a low-pass (high-cut) filter to remove frequencies above cutoff.
    
    Args:
        audio: Input audio segment
        cutoff_hz: Cutoff frequency in Hz
        order: Filter order (default 2 for gentle slope)
    
    Returns:
        Filtered audio segment
    """
    if audio is None:
        raise ValueError("Cannot apply low-pass filter: audio is None")
    
    if cutoff_hz <= 0:
        return audio
    
    sample_rate = audio.frame_rate
    
    # Ensure cutoff is below Nyquist
    nyquist = sample_rate / 2
    if cutoff_hz >= nyquist:
        # Cutoff at or above Nyquist means no filtering needed
        return audio
    
    # Normalize cutoff frequency
    normalized_cutoff = cutoff_hz / nyquist
    
    # Design Butterworth low-pass filter
    b, a = signal.butter(order, normalized_cutoff, btype='low')
    
    # Convert to numpy
    samples = _audiosegment_to_numpy(audio)
    
    # Apply filter (handle mono and stereo)
    if samples.ndim == 1:
        filtered = signal.filtfilt(b, a, samples)
    else:
        # Filter each channel separately
        filtered = np.zeros_like(samples)
        for ch in range(samples.shape[1]):
            filtered[:, ch] = signal.filtfilt(b, a, samples[:, ch])
    
    # Convert back to AudioSegment
    return _numpy_to_audiosegment(
        filtered.astype(np.float32),
        audio.frame_rate,
        audio.sample_width,
        audio.channels
    )


def apply_primary_band(
    audio: AudioSegment,
    freq_hz: float,
    gain_db: float,
    q: float = 1.0
) -> AudioSegment:
    """
    Apply a primary band (peak/bell) filter for boost/cut at a specific frequency.
    
    Note: Named "primary_band" not "presence_band" because it's not always
    for presence (e.g., low-mid warmth cuts).
    
    Constraints are enforced to keep presets musical, not surgical:
    - Q: 0.7 - 1.2 (wide, musical bandwidth)
    - Gain: ±3 dB max (gentle shaping)
    - Frequency: 80 - 8000 Hz (audible range)
    
    Args:
        audio: Input audio segment
        freq_hz: Center frequency in Hz
        gain_db: Gain in dB (positive = boost, negative = cut)
        q: Q factor / bandwidth (higher = narrower)
    
    Returns:
        Filtered audio segment
    """
    if audio is None:
        raise ValueError("Cannot apply primary band: audio is None")
    
    # Enforce constraints
    q = max(PRIMARY_BAND_Q_MIN, min(PRIMARY_BAND_Q_MAX, q))
    gain_db = max(-PRIMARY_BAND_GAIN_MAX, min(PRIMARY_BAND_GAIN_MAX, gain_db))
    freq_hz = max(PRIMARY_BAND_FREQ_MIN, min(PRIMARY_BAND_FREQ_MAX, freq_hz))
    
    if abs(gain_db) < 0.1:
        # Negligible gain, skip processing
        return audio
    
    sample_rate = audio.frame_rate
    nyquist = sample_rate / 2
    
    if freq_hz >= nyquist:
        logger.warning(f"Primary band freq {freq_hz}Hz >= Nyquist {nyquist}Hz, skipping")
        return audio
    
    # Convert to numpy
    samples = _audiosegment_to_numpy(audio)
    
    # Design peaking EQ filter using biquad coefficients
    # Based on Audio EQ Cookbook by Robert Bristow-Johnson
    A = 10 ** (gain_db / 40)  # Square root of linear gain
    omega = 2 * np.pi * freq_hz / sample_rate
    sin_omega = np.sin(omega)
    cos_omega = np.cos(omega)
    alpha = sin_omega / (2 * q)
    
    # Peaking EQ coefficients
    b0 = 1 + alpha * A
    b1 = -2 * cos_omega
    b2 = 1 - alpha * A
    a0 = 1 + alpha / A
    a1 = -2 * cos_omega
    a2 = 1 - alpha / A
    
    # Normalize coefficients
    b = np.array([b0/a0, b1/a0, b2/a0])
    a = np.array([1.0, a1/a0, a2/a0])
    
    # Apply filter (handle mono and stereo)
    if samples.ndim == 1:
        filtered = signal.filtfilt(b, a, samples)
    else:
        filtered = np.zeros_like(samples)
        for ch in range(samples.shape[1]):
            filtered[:, ch] = signal.filtfilt(b, a, samples[:, ch])
    
    return _numpy_to_audiosegment(
        filtered.astype(np.float32),
        audio.frame_rate,
        audio.sample_width,
        audio.channels
    )


def apply_shelf(
    audio: AudioSegment,
    freq_hz: float,
    gain_db: float,
    shelf_type: str = "high"
) -> AudioSegment:
    """
    Apply a shelving filter (high or low shelf).
    
    Args:
        audio: Input audio segment
        freq_hz: Shelf corner frequency in Hz
        gain_db: Gain in dB (positive = boost, negative = cut)
        shelf_type: "high" (affects frequencies above) or "low" (affects frequencies below)
    
    Returns:
        Filtered audio segment
    """
    if audio is None:
        raise ValueError("Cannot apply shelf filter: audio is None")
    
    if abs(gain_db) < 0.1:
        # Negligible gain, skip processing
        return audio
    
    sample_rate = audio.frame_rate
    nyquist = sample_rate / 2
    
    if freq_hz >= nyquist or freq_hz <= 0:
        logger.warning(f"Shelf freq {freq_hz}Hz outside valid range, skipping")
        return audio
    
    # Convert to numpy
    samples = _audiosegment_to_numpy(audio)
    
    # Design shelving filter using biquad coefficients
    # Based on Audio EQ Cookbook
    A = 10 ** (gain_db / 40)
    omega = 2 * np.pi * freq_hz / sample_rate
    sin_omega = np.sin(omega)
    cos_omega = np.cos(omega)
    
    # Use a moderate slope (S = 1)
    S = 1.0
    alpha = sin_omega / 2 * np.sqrt((A + 1/A) * (1/S - 1) + 2)
    
    if shelf_type == "low":
        # Low shelf
        b0 = A * ((A + 1) - (A - 1) * cos_omega + 2 * np.sqrt(A) * alpha)
        b1 = 2 * A * ((A - 1) - (A + 1) * cos_omega)
        b2 = A * ((A + 1) - (A - 1) * cos_omega - 2 * np.sqrt(A) * alpha)
        a0 = (A + 1) + (A - 1) * cos_omega + 2 * np.sqrt(A) * alpha
        a1 = -2 * ((A - 1) + (A + 1) * cos_omega)
        a2 = (A + 1) + (A - 1) * cos_omega - 2 * np.sqrt(A) * alpha
    else:
        # High shelf
        b0 = A * ((A + 1) + (A - 1) * cos_omega + 2 * np.sqrt(A) * alpha)
        b1 = -2 * A * ((A - 1) + (A + 1) * cos_omega)
        b2 = A * ((A + 1) + (A - 1) * cos_omega - 2 * np.sqrt(A) * alpha)
        a0 = (A + 1) - (A - 1) * cos_omega + 2 * np.sqrt(A) * alpha
        a1 = 2 * ((A - 1) - (A + 1) * cos_omega)
        a2 = (A + 1) - (A - 1) * cos_omega - 2 * np.sqrt(A) * alpha
    
    # Normalize coefficients
    b = np.array([b0/a0, b1/a0, b2/a0])
    a = np.array([1.0, a1/a0, a2/a0])
    
    # Apply filter
    if samples.ndim == 1:
        filtered = signal.filtfilt(b, a, samples)
    else:
        filtered = np.zeros_like(samples)
        for ch in range(samples.shape[1]):
            filtered[:, ch] = signal.filtfilt(b, a, samples[:, ch])
    
    return _numpy_to_audiosegment(
        filtered.astype(np.float32),
        audio.frame_rate,
        audio.sample_width,
        audio.channels
    )


# =============================================================================
# Intent-Based API (Exposed)
# =============================================================================

def apply_eq_preset(audio: AudioSegment, preset_name: str) -> AudioSegment:
    """
    Apply an EQ preset to audio.
    
    This is the main entry point for clip-level EQ. Timeline authors
    specify preset names like "dialogue_clean", and this function
    handles the frequency details internally.
    
    Args:
        audio: Input audio segment
        preset_name: Preset name (e.g., "dialogue_clean" or "dialogue_clean@v1")
    
    Returns:
        EQ'd audio segment
    
    Raises:
        ValueError: If preset name is unknown
    """
    if audio is None:
        raise ValueError("Cannot apply EQ preset: audio is None")
    
    try:
        config = get_preset_config(preset_name)
    except ValueError as e:
        logger.warning(f"Unknown EQ preset '{preset_name}', skipping EQ: {e}")
        return audio
    
    versioned_name = resolve_preset_version(preset_name)
    logger.debug(f"Applying EQ preset '{preset_name}' (resolved to '{versioned_name}')")
    
    result = audio
    
    # Apply high-pass filter
    if "high_pass" in config:
        result = apply_high_pass(result, config["high_pass"])
    
    # Apply low-pass filter
    if "low_pass" in config:
        result = apply_low_pass(result, config["low_pass"])
    
    # Apply primary band
    if "primary" in config:
        primary = config["primary"]
        result = apply_primary_band(
            result,
            freq_hz=primary.get("freq", 1000),
            gain_db=primary.get("gain", 0),
            q=primary.get("q", 1.0)
        )
    
    return result


def apply_scene_tonal_shaping(audio: AudioSegment, scene_eq: Dict[str, Any]) -> AudioSegment:
    """
    Apply scene-level tonal shaping (restricted to broad adjustments).
    
    Scene-level EQ is intentionally limited to prevent conflicts with
    role presets:
    - Tilt presets (warm, neutral, bright)
    - High/low shelf adjustments
    
    NOT allowed at scene level:
    - Narrow parametric bands
    - High-pass/low-pass overrides
    - Per-role EQ overrides
    
    Args:
        audio: Input audio segment (typically the mixed canvas)
        scene_eq: Scene EQ configuration dict with optional keys:
                  - tilt: "warm", "neutral", or "bright"
                  - high_shelf: dB adjustment (e.g., -2)
                  - low_shelf: dB adjustment (e.g., +1)
    
    Returns:
        Tonally shaped audio segment
    """
    if audio is None:
        raise ValueError("Cannot apply scene tonal shaping: audio is None")
    
    if not scene_eq:
        return audio
    
    result = audio
    
    # Apply tilt preset
    if "tilt" in scene_eq:
        try:
            tilt_config = get_tilt_config(scene_eq["tilt"])
            
            # Apply low shelf from tilt
            if "low_shelf_gain" in tilt_config and tilt_config["low_shelf_gain"] != 0:
                result = apply_shelf(
                    result,
                    freq_hz=tilt_config.get("low_shelf_freq", 200),
                    gain_db=tilt_config["low_shelf_gain"],
                    shelf_type="low"
                )
            
            # Apply high shelf from tilt
            if "high_shelf_gain" in tilt_config and tilt_config["high_shelf_gain"] != 0:
                result = apply_shelf(
                    result,
                    freq_hz=tilt_config.get("high_shelf_freq", 4000),
                    gain_db=tilt_config["high_shelf_gain"],
                    shelf_type="high"
                )
            
            logger.debug(f"Applied tilt preset '{scene_eq['tilt']}'")
            
        except ValueError as e:
            logger.warning(f"Failed to apply tilt preset: {e}")
    
    # Apply explicit high shelf override
    if "high_shelf" in scene_eq and scene_eq["high_shelf"] != 0:
        result = apply_shelf(
            result,
            freq_hz=4000,  # Fixed corner frequency for scene-level
            gain_db=scene_eq["high_shelf"],
            shelf_type="high"
        )
        logger.debug(f"Applied scene high shelf: {scene_eq['high_shelf']} dB")
    
    # Apply explicit low shelf override
    if "low_shelf" in scene_eq and scene_eq["low_shelf"] != 0:
        result = apply_shelf(
            result,
            freq_hz=200,  # Fixed corner frequency for scene-level
            gain_db=scene_eq["low_shelf"],
            shelf_type="low"
        )
        logger.debug(f"Applied scene low shelf: {scene_eq['low_shelf']} dB")
    
    return result


# Re-export preset functions for convenience
__all__ = [
    # Core filters
    "apply_high_pass",
    "apply_low_pass",
    "apply_primary_band",
    "apply_shelf",
    # Intent-based API
    "apply_eq_preset",
    "apply_scene_tonal_shaping",
    # Preset utilities (re-exported from eq_presets)
    "get_preset_for_role",
    "resolve_preset_version",
    "get_preset_config",
    "get_tilt_config",
]
