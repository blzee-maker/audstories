"""
Integration tests for fade curves in the full rendering pipeline.
Tests backward compatibility and new curve features.
"""
import json
import os
from pathlib import Path

from audio_engine.config import RenderConfig
from audio_engine.renderer.clip_processor import extract_fade_config
from audio_engine.dsp.fade_curves import FadeCurve


def test_backward_compatibility():
    """Test that old JSON format (number fades) still works."""
    # Test fade config extraction with old format (number)
    fade_ms, curve = extract_fade_config(2.0)
    assert fade_ms == 2000, "Fade duration should be 2000ms for 2.0 seconds"
    assert curve == FadeCurve.LINEAR, "Old format should default to LINEAR curve"
    print("✓ Backward compatibility: number format extracts correctly")
    
    # Test RenderConfig: timelines without master_fade_out get a default end fade-out
    settings = {
        "normalize": False,
        "master_gain": 0,
    }
    config = RenderConfig.from_timeline_settings(settings)
    assert config.master_fade_out is not None
    assert config.master_fade_out.get("enabled") is True
    assert config.master_fade_out.get("duration") == 2.0
    print("✓ Default master_fade_out when omitted from timeline")

    settings_off = {"normalize": False, "master_gain": 0, "master_fade_out": {"enabled": False}}
    assert RenderConfig.merge_master_fade_out(settings_off) is None
    print("✓ master_fade_out can be explicitly disabled")


def test_new_format():
    """Test that new JSON format (object fades) works."""
    # Test fade config extraction with new format (object)
    fade_config = {
        "duration": 2.0,
        "curve": "exponential"
    }
    fade_ms, curve = extract_fade_config(fade_config)
    assert fade_ms == 2000, "Fade duration should be 2000ms for 2.0 seconds"
    assert curve == FadeCurve.EXPONENTIAL, "Curve should be EXPONENTIAL"
    print("✓ New format: object format extracts correctly")
    
    # Test RenderConfig with new-style master_fade_out
    settings = {
        "normalize": False,
        "master_gain": 0,
        "master_fade_out": {
            "enabled": True,
            "duration": 3.0,
            "curve": "logarithmic"
        }
    }
    config = RenderConfig.from_timeline_settings(settings)
    assert config.master_fade_out is not None
    assert config.master_fade_out.get("duration") == 3.0
    assert config.master_fade_out.get("curve") == "logarithmic"
    print("✓ New format: RenderConfig extracts master_fade_out curve correctly")


def test_mixed_format():
    """Test mixing old and new formats in the same timeline."""
    # Test old format (number)
    fade_ms1, curve1 = extract_fade_config(2.0)
    assert fade_ms1 == 2000
    assert curve1 == FadeCurve.LINEAR
    
    # Test new format (object)
    fade_ms2, curve2 = extract_fade_config({"duration": 2.0, "curve": "logarithmic"})
    assert fade_ms2 == 2000
    assert curve2 == FadeCurve.LOGARITHMIC
    
    print("✓ Mixed format: Both old and new formats work together")


def test_all_curve_types():
    """Test that all curve types are accepted."""
    from audio_engine.dsp.fade_curves import FadeCurve
    
    for curve in FadeCurve:
        test_json = {
            "project": {
                "name": f"Curve Test: {curve.value}",
                "duration": 5
            },
            "settings": {
                "normalize": False,
                "master_gain": 0,
                "master_fade_out": {
                    "enabled": True,
                    "duration": 1.0,
                    "curve": curve.value
                }
            },
            "tracks": [
                {
                    "id": "music",
                    "type": "music",
                    "gain": 0,
                    "clips": [
                        {
                            "file": "audio/music/Days.mp3",
                            "start": 0,
                            "fade_in": {
                                "duration": 1.0,
                                "curve": curve.value
                            }
                        }
                    ]
                }
            ]
        }
        
        # Verify curve is valid
        parsed_curve = FadeCurve.from_string(curve.value)
        assert parsed_curve == curve, f"Curve {curve.value} not parsed correctly"
        print(f"✓ Curve type '{curve.value}' accepted")


if __name__ == "__main__":
    print("Running fade curves integration tests...\n")
    
    test_backward_compatibility()
    test_new_format()
    test_mixed_format()
    test_all_curve_types()
    
    print("\nAll integration tests passed!")
