# Advanced Fade Curves Implementation

## Overview

This document describes the implementation of advanced fade curves for the audio engine. The feature adds support for logarithmic and exponential fade curves in addition to the existing linear fades, providing more natural and professional-sounding audio transitions.

**Implementation Date:** 2024  
**Feature:** Advanced Fade Curves (5.2.1 from AUDIO_ENGINE_ANALYSIS.md)

---

## What Changed

### New Features

1. **Three Fade Curve Types:**
   - **Linear** (default): Constant rate fade (existing behavior)
   - **Logarithmic**: Slower start, faster end (more natural for fade-ins)
   - **Exponential**: Faster start, slower end (sharper transitions)

2. **Enhanced JSON Format:**
   - Clip fades (`fade_in`/`fade_out`) can now specify curve type
   - Master fade-out can specify curve type
   - Backward compatible with existing number-based fade format

3. **Improved Audio Quality:**
   - More natural-sounding transitions
   - Better control over fade characteristics
   - Professional-grade fade curves

---

## Files Modified

### New Files Created

- **`dsp/fade_curves.py`**
  - `FadeCurve` enum (LINEAR, LOGARITHMIC, EXPONENTIAL)
  - `generate_fade_curve()` function for curve generation
  - `from_string()` method for string-to-enum conversion

### Files Modified

- **`dsp/fades.py`**
  - Updated `apply_fade_in()` to accept `curve` parameter
  - Updated `apply_fade_out()` to accept `curve` parameter
  - Added `_apply_custom_fade()` internal function for curve-based fading
  - Uses numpy for efficient custom curve application

- **`renderer/clip_processor.py`**
  - Added `extract_fade_config()` function to parse fade configs
  - Updated clip processing to extract and apply curve types
  - Supports both old (number) and new (object) fade formats

- **`renderer/master_processor.py`**
  - Updated master fade-out to extract and apply curve type
  - Supports curve specification in `master_fade_out` config

### Test Files Created

- **`test/test_dsp/test_fade_curves.py`**
  - Unit tests for curve generation
  - Tests for all curve types
  - Integration tests for fade application

- **`test/test_fade_curves_integration.py`**
  - Integration tests for JSON parsing
  - Backward compatibility tests
  - Mixed format tests

- **`test/test_fade_curves_integration.json`**
  - Example timeline JSON with various curve types

---

## Usage Guide

### Clip Fades

#### Old Format (Still Supported)

The original format using a simple number (seconds) continues to work and defaults to linear curves:

```json
{
  "clips": [
    {
      "file": "audio/music/track.mp3",
      "start": 0,
      "fade_in": 2.0,
      "fade_out": 3.0
    }
  ]
}
```

#### New Format (With Curve Selection)

You can now specify fade duration and curve type using an object:

```json
{
  "clips": [
    {
      "file": "audio/music/track.mp3",
      "start": 0,
      "fade_in": {
        "duration": 2.0,
        "curve": "logarithmic"
      },
      "fade_out": {
        "duration": 3.0,
        "curve": "exponential"
      }
    }
  ]
}
```

**Available curve types:**
- `"linear"` - Constant rate fade (default)
- `"logarithmic"` - Slower start, faster end (natural fade-in)
- `"exponential"` - Faster start, slower end (sharp fade-out)

### Master Fade-Out

Master fade-out now supports curve specification:

```json
{
  "settings": {
    "master_fade_out": {
      "enabled": true,
      "duration": 10.0,
      "curve": "exponential"
    }
  }
}
```

If `curve` is not specified, it defaults to `"linear"` for backward compatibility.

---

## Examples

### Example 1: Natural Music Fade-In

Use logarithmic curve for a smooth, natural music entrance:

```json
{
  "clips": [
    {
      "file": "audio/music/background.mp3",
      "start": 0,
      "fade_in": {
        "duration": 3.0,
        "curve": "logarithmic"
      }
    }
  ]
}
```

### Example 2: Sharp Scene Transition

Use exponential curve for a dramatic scene transition:

```json
{
  "clips": [
    {
      "file": "audio/music/dramatic.mp3",
      "start": 10.0,
      "fade_out": {
        "duration": 2.0,
        "curve": "exponential"
      }
    }
  ]
}
```

### Example 3: Mixed Formats

You can mix old and new formats in the same timeline:

```json
{
  "clips": [
    {
      "file": "audio/music/track1.mp3",
      "start": 0,
      "fade_in": 2.0,  // Old format - defaults to linear
      "fade_out": {
        "duration": 2.0,
        "curve": "logarithmic"  // New format
      }
    },
    {
      "file": "audio/music/track2.mp3",
      "start": 10.0,
      "fade_in": {
        "duration": 1.5,
        "curve": "exponential"
      },
      "fade_out": 3.0  // Old format
    }
  ]
}
```

### Example 4: Complete Timeline with Curves

```json
{
  "project": {
    "name": "Advanced Fade Example",
    "duration": 30
  },
  "settings": {
    "normalize": false,
    "master_gain": 0,
    "master_fade_out": {
      "enabled": true,
      "duration": 5.0,
      "curve": "exponential"
    }
  },
  "tracks": [
    {
      "id": "music",
      "type": "music",
      "gain": 0,
      "clips": [
        {
          "file": "audio/music/intro.mp3",
          "start": 0,
          "fade_in": {
            "duration": 3.0,
            "curve": "logarithmic"
          },
          "fade_out": {
            "duration": 2.0,
            "curve": "exponential"
          }
        }
      ]
    }
  ]
}
```

---

## Curve Characteristics

### Linear Curve
- **Formula:** `gain = progress`
- **Characteristics:**
  - Constant rate of change
  - Predictable and uniform
  - Best for: Simple fades, technical applications
- **Visual:** Straight line from 0 to 1 (or 1 to 0)

### Logarithmic Curve
- **Formula:** `gain = log10(1 + 9 * progress) / log10(10)`
- **Characteristics:**
  - Slow start, accelerates toward end
  - More natural-sounding fade-in
  - Perceptually smoother for music
- **Visual:** Curved line starting shallow, ending steep
- **Best for:** Music fade-ins, background ambience, natural transitions

### Exponential Curve
- **Formula:** `gain = (10^progress - 1) / 9`
- **Characteristics:**
  - Fast start, decelerates toward end
  - Sharper, more dramatic transitions
  - Creates sense of urgency or emphasis
- **Visual:** Curved line starting steep, ending shallow
- **Best for:** Dramatic scene transitions, sharp cutoffs, emphasis

---

## Technical Implementation

### Curve Generation

Curves are generated using numpy arrays for efficient processing:

```python
from dsp.fade_curves import FadeCurve, generate_fade_curve

# Generate fade-in curve (0.0 to 1.0)
gain_curve = generate_fade_curve(
    FadeCurve.LOGARITHMIC,
    num_samples=44100,  # 1 second at 44.1kHz
    fade_in=True
)

# Generate fade-out curve (1.0 to 0.0)
gain_curve = generate_fade_curve(
    FadeCurve.EXPONENTIAL,
    num_samples=44100,
    fade_in=False
)
```

### Audio Processing

Custom curves are applied using numpy for vectorized operations:

1. Extract audio samples from AudioSegment
2. Generate gain curve array
3. Apply gain multipliers sample-by-sample
4. Convert back to AudioSegment format

For linear curves, the implementation falls back to pydub's optimized fade methods for better performance.

### Performance Considerations

- **Linear fades:** Use pydub's optimized C-based implementation (fastest)
- **Custom curves:** Use numpy vectorized operations (efficient for large files)
- **Memory:** Processes audio in segments to minimize memory usage
- **Compatibility:** Supports mono and stereo audio, all sample widths (8-bit, 16-bit, 32-bit)

---

## Backward Compatibility

### Fully Backward Compatible

All existing timelines continue to work without modification:

- **Number-based fades** (`"fade_in": 2.0`) automatically default to linear curves
- **Missing curve specification** defaults to linear
- **Invalid curve names** default to linear with a warning
- **Master fade-out** without curve specification uses linear

### Migration Path

No migration required! Existing timelines work as-is. To take advantage of new curves:

1. Update fade specifications to object format
2. Add `curve` field with desired curve type
3. Keep `duration` field for fade length

---

## API Reference

### FadeCurve Enum

```python
from dsp.fade_curves import FadeCurve

# Available values
FadeCurve.LINEAR        # "linear"
FadeCurve.LOGARITHMIC   # "logarithmic"
FadeCurve.EXPONENTIAL   # "exponential"

# Convert from string
curve = FadeCurve.from_string("logarithmic")  # Returns FadeCurve.LOGARITHMIC
curve = FadeCurve.from_string(None)           # Returns FadeCurve.LINEAR (default)
```

### Fade Functions

```python
from dsp.fades import apply_fade_in, apply_fade_out
from dsp.fade_curves import FadeCurve

# Apply fade-in with curve
canvas = apply_fade_in(
    canvas=audio_canvas,
    start_ms=1000,
    fade_ms=2000,
    curve=FadeCurve.LOGARITHMIC
)

# Apply fade-out with curve
canvas = apply_fade_out(
    canvas=audio_canvas,
    clip_start_ms=1000,
    clip_len_ms=5000,
    project_len_ms=10000,
    fade_ms=2000,
    curve=FadeCurve.EXPONENTIAL
)
```

### Config Extraction

```python
from renderer.clip_processor import extract_fade_config

# Old format (number)
fade_ms, curve = extract_fade_config(2.0)
# Returns: (2000, FadeCurve.LINEAR)

# New format (object)
fade_config = {"duration": 2.0, "curve": "logarithmic"}
fade_ms, curve = extract_fade_config(fade_config)
# Returns: (2000, FadeCurve.LOGARITHMIC)
```

---

## Testing

### Running Unit Tests

```bash
python test/test_dsp/test_fade_curves.py
```

### Running Integration Tests

```bash
python test/test_fade_curves_integration.py
```

### Test Coverage

- ✅ Curve generation for all types
- ✅ Fade-in and fade-out directions
- ✅ String-to-enum conversion
- ✅ Backward compatibility
- ✅ JSON parsing (old and new formats)
- ✅ Mixed format support
- ✅ Audio processing integration

---

## Known Limitations

1. **Scene Crossfades:** Currently use linear fades (future enhancement)
2. **Ducking Fades:** Currently use linear fades (future enhancement)
3. **Energy Ramps:** Currently use linear fades (future enhancement)
4. **Custom Curve Parameters:** No support for curve steepness adjustment (future enhancement)

---

## Future Enhancements

Potential future improvements (from AUDIO_ENGINE_ANALYSIS.md):

1. **Additional Curve Types:**
   - Ease-in-out curves
   - Ease-out-cubic
   - Custom bezier curves

2. **Extended Support:**
   - Curve support for scene crossfades
   - Curve support for ducking fades
   - Curve support for energy ramps

3. **Advanced Features:**
   - Custom curve parameters (steepness, custom shapes)
   - Per-fade curve selection UI
   - Curve visualization tools

---

## Troubleshooting

### Issue: Fade doesn't sound different

**Solution:** Ensure you're using a non-linear curve type. Linear curves sound the same as before.

### Issue: Invalid curve name error

**Solution:** Check spelling. Valid values are: `"linear"`, `"logarithmic"`, `"exponential"` (case-insensitive).

### Issue: Fade not applying

**Solution:** 
1. Check fade duration is greater than 0
2. Verify fade region doesn't exceed clip length
3. Check JSON syntax (ensure proper object format if using new format)

### Issue: Audio artifacts

**Solution:** 
1. Ensure fade duration is reasonable (not too short)
2. Check audio file quality
3. Try different curve types (logarithmic is often smoother)

---

## References

- **Analysis Document:** `AUDIO_ENGINE_ANALYSIS.md` - Section 5.2.1
- **Implementation Plan:** Advanced Fade Curves Implementation Plan
- **Related Files:**
  - `dsp/fade_curves.py` - Curve generation
  - `dsp/fades.py` - Fade application
  - `renderer/clip_processor.py` - Clip processing
  - `renderer/master_processor.py` - Master processing

---

## Changelog

### Version 1.0.0 (2024)

**Added:**
- FadeCurve enum with LINEAR, LOGARITHMIC, EXPONENTIAL types
- Custom fade curve generation using numpy
- JSON support for curve specification in clip fades
- JSON support for curve specification in master fade-out
- Backward compatibility with existing number-based fade format
- Comprehensive unit and integration tests

**Changed:**
- `apply_fade_in()` now accepts optional `curve` parameter
- `apply_fade_out()` now accepts optional `curve` parameter
- Clip processor extracts curve from fade configs
- Master processor applies curve-aware fade-out

**Performance:**
- Linear fades use optimized pydub path
- Custom curves use efficient numpy vectorization
- Supports mono and stereo audio
- Handles all sample widths (8-bit, 16-bit, 32-bit)

---

*Document generated: 2024*  
*Last updated: February 2026*
