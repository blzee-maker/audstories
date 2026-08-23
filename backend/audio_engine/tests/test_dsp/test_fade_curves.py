"""
Unit tests for fade curve generation and application.
"""
import numpy as np
from pydub import AudioSegment

from audio_engine.dsp.fade_curves import FadeCurve, generate_fade_curve
from audio_engine.dsp.fades import apply_fade_in, apply_fade_out


def test_fade_curve_enum():
    """Test FadeCurve enum values."""
    assert FadeCurve.LINEAR.value == "linear"
    assert FadeCurve.LOGARITHMIC.value == "logarithmic"
    assert FadeCurve.EXPONENTIAL.value == "exponential"


def test_fade_curve_from_string():
    """Test converting strings to FadeCurve."""
    assert FadeCurve.from_string("linear") == FadeCurve.LINEAR
    assert FadeCurve.from_string("logarithmic") == FadeCurve.LOGARITHMIC
    assert FadeCurve.from_string("exponential") == FadeCurve.EXPONENTIAL
    assert FadeCurve.from_string("LINEAR") == FadeCurve.LINEAR  # Case insensitive
    assert FadeCurve.from_string("  logarithmic  ") == FadeCurve.LOGARITHMIC  # Strip whitespace
    assert FadeCurve.from_string(None) == FadeCurve.LINEAR  # Default
    assert FadeCurve.from_string("invalid") == FadeCurve.LINEAR  # Invalid defaults to linear


def test_linear_curve():
    """Test linear curve generation."""
    num_samples = 100
    curve = generate_fade_curve(FadeCurve.LINEAR, num_samples, fade_in=True)
    
    assert len(curve) == num_samples
    assert np.isclose(curve[0], 0.0, atol=1e-6)  # Start at 0
    assert np.isclose(curve[-1], 1.0, atol=1e-6)  # End at 1
    assert np.all(curve >= 0.0) and np.all(curve <= 1.0)  # All values in range
    
    # Linear should be approximately linear
    mid_point = curve[num_samples // 2]
    assert np.isclose(mid_point, 0.5, atol=0.1)  # Middle should be around 0.5


def test_logarithmic_curve():
    """Test logarithmic curve generation."""
    num_samples = 100
    curve = generate_fade_curve(FadeCurve.LOGARITHMIC, num_samples, fade_in=True)
    
    assert len(curve) == num_samples
    assert np.isclose(curve[0], 0.0, atol=1e-6)  # Start at 0
    assert np.isclose(curve[-1], 1.0, atol=1e-6)  # End at 1
    assert np.all(curve >= 0.0) and np.all(curve <= 1.0)  # All values in range
    
    # Logarithmic should start slower than linear
    mid_point = curve[num_samples // 2]
    assert mid_point < 0.5  # Should be less than 0.5 at midpoint (slower start)


def test_exponential_curve():
    """Test exponential curve generation."""
    num_samples = 100
    curve = generate_fade_curve(FadeCurve.EXPONENTIAL, num_samples, fade_in=True)
    
    assert len(curve) == num_samples
    assert np.isclose(curve[0], 0.0, atol=1e-6)  # Start at 0
    assert np.isclose(curve[-1], 1.0, atol=1e-6)  # End at 1
    assert np.all(curve >= 0.0) and np.all(curve <= 1.0)  # All values in range
    
    # Exponential should start faster than linear
    mid_point = curve[num_samples // 2]
    assert mid_point > 0.5  # Should be greater than 0.5 at midpoint (faster start)


def test_fade_out_curve():
    """Test fade-out curves (reversed)."""
    num_samples = 100
    
    # Fade-out should go from 1.0 to 0.0
    linear_out = generate_fade_curve(FadeCurve.LINEAR, num_samples, fade_in=False)
    assert np.isclose(linear_out[0], 1.0, atol=1e-6)  # Start at 1
    assert np.isclose(linear_out[-1], 0.0, atol=1e-6)  # End at 0
    
    log_out = generate_fade_curve(FadeCurve.LOGARITHMIC, num_samples, fade_in=False)
    assert np.isclose(log_out[0], 1.0, atol=1e-6)
    assert np.isclose(log_out[-1], 0.0, atol=1e-6)
    
    exp_out = generate_fade_curve(FadeCurve.EXPONENTIAL, num_samples, fade_in=False)
    assert np.isclose(exp_out[0], 1.0, atol=1e-6)
    assert np.isclose(exp_out[-1], 0.0, atol=1e-6)


def test_curve_comparison():
    """Test that different curves produce different results."""
    num_samples = 100
    
    linear = generate_fade_curve(FadeCurve.LINEAR, num_samples, fade_in=True)
    logarithmic = generate_fade_curve(FadeCurve.LOGARITHMIC, num_samples, fade_in=True)
    exponential = generate_fade_curve(FadeCurve.EXPONENTIAL, num_samples, fade_in=True)
    
    # All curves should be different
    assert not np.allclose(linear, logarithmic, atol=0.01)
    assert not np.allclose(linear, exponential, atol=0.01)
    assert not np.allclose(logarithmic, exponential, atol=0.01)
    
    # At midpoint, logarithmic < linear < exponential
    mid_idx = num_samples // 2
    assert logarithmic[mid_idx] < linear[mid_idx] < exponential[mid_idx]


def test_fade_integration():
    """Test fade application with different curves."""
    # Create a test audio segment
    audio = AudioSegment.silent(duration=2000) + AudioSegment.sine(440, duration=2000)
    canvas = AudioSegment.silent(duration=5000)
    canvas = canvas.overlay(audio, position=1000)
    
    # Test fade-in with different curves
    for curve in [FadeCurve.LINEAR, FadeCurve.LOGARITHMIC, FadeCurve.EXPONENTIAL]:
        result = apply_fade_in(canvas, start_ms=1000, fade_ms=500, curve=curve)
        assert len(result) == len(canvas)
        assert result is not None
    
    # Test fade-out with different curves
    for curve in [FadeCurve.LINEAR, FadeCurve.LOGARITHMIC, FadeCurve.EXPONENTIAL]:
        result = apply_fade_out(
            canvas=canvas,
            clip_start_ms=1000,
            clip_len_ms=2000,
            project_len_ms=5000,
            fade_ms=500,
            curve=curve
        )
        assert len(result) == len(canvas)
        assert result is not None


def test_empty_fade():
    """Test fade with zero duration."""
    curve = generate_fade_curve(FadeCurve.LINEAR, 0, fade_in=True)
    assert len(curve) == 0
    
    audio = AudioSegment.silent(duration=1000)
    result = apply_fade_in(audio, start_ms=0, fade_ms=0, curve=FadeCurve.LINEAR)
    assert len(result) == len(audio)


if __name__ == "__main__":
    print("Running fade curve tests...")
    test_fade_curve_enum()
    print("✓ FadeCurve enum test passed")
    
    test_fade_curve_from_string()
    print("✓ FadeCurve.from_string test passed")
    
    test_linear_curve()
    print("✓ Linear curve test passed")
    
    test_logarithmic_curve()
    print("✓ Logarithmic curve test passed")
    
    test_exponential_curve()
    print("✓ Exponential curve test passed")
    
    test_fade_out_curve()
    print("✓ Fade-out curve test passed")
    
    test_curve_comparison()
    print("✓ Curve comparison test passed")
    
    test_fade_integration()
    print("✓ Fade integration test passed")
    
    test_empty_fade()
    print("✓ Empty fade test passed")
    
    print("\nAll tests passed!")
