# Engine Notes

Quick reference for working with the audio engine.

---

## Audio Pipeline Order

**DO NOT CHANGE THIS ORDER**

### Clip-Level DSP
```
1. Load Audio
2. Apply Track/Clip Gain
3. Apply EQ (role preset)
4. Apply SFX Processing
5. Apply Energy Ramp
6. Apply Ducking
7. Apply Dialogue Compression
8. Overlay to Canvas
9. Apply Scene Tonal Shaping
10. Apply Fades
```

### Master Processing
```
11. Track Mix
12. LUFS Loudness Correction
13. Master Gain
14. Peak Normalization
15. Export
```

**Why this order matters:**
- LUFS must operate on perceptual loudness of the full mix
- Peak normalization is safety, not loudness control
- Reordering breaks cinematic dynamics
- EQ before ducking allows lighter ducking

---

## Loudness Standard (Cinematic)

| Parameter | Value |
|-----------|-------|
| Integrated LUFS target | −20.0 |
| Dialogue anchor | ~−18 LUFS |
| True peak ceiling | −1.0 dBFS |

**Why:** Preserves dynamic range while maintaining clarity for story-driven audio.

---

## LUFS Design Rules

1. LUFS correction is **optional and explicit**
2. LUFS correction is **clamped**:
   - Max boost: +6 dB
   - Max cut: −10 dB
3. LUFS is applied **once per render**

This prevents:
- Noise floor amplification
- Over-compression
- Double loudness correction

---

## DSP Responsibility Boundaries

| Layer | Responsibility |
|-------|----------------|
| `dsp/*` | Pure signal processing only |
| `utils/*` | Math, ranges, debug, logging |
| `renderer/*.py` | Orchestration only |
| `scene_preprocessor.py` | Structural timeline expansion |

**DSP modules must NOT:**
- Know about scenes
- Know about tracks
- Know about timeline JSON structure

---

## Ducking Philosophy

1. Default ducking is **envelope-based**
2. Ducking reacts to dialogue ranges
3. Fade-down and fade-up are **asymmetric**
4. Behavior matches DAW-style sidechain ducking
5. Uses a short onset delay (~120ms) to avoid perceptual pre-duck dips

This ensures:
- Smooth transitions
- No abrupt volume drops
- Dialogue intelligibility

**Configuration:**
```json
"ducking": { 
  "mode": "audacity",
  "onset_delay_ms": 120
}
```

---

## EQ Presets Quick Reference

| Preset | Use Case |
|--------|----------|
| `dialogue_clean` | Standard dialogue (default for voice) |
| `dialogue_warm` | Intimate narration |
| `dialogue_broadcast` | Podcasts, radio |
| `music_full` | Music-focused content |
| `music_bed` | Music behind dialogue (default for music) |
| `background_soft` | Subtle ambience (default for background) |
| `background_distant` | Far-away atmospheres |
| `sfx_punch` | Impactful SFX |
| `sfx_subtle` | Gentle SFX |

---

## SFX Semantic Roles

| Role | LUFS | Fade In | Fade Out | Curve |
|------|------|---------|----------|-------|
| `impact` | -18 | 0ms | 75ms | Exponential |
| `movement` | -20 | 150ms | 150ms | Linear |
| `ambience` | -22 | 750ms | 750ms | Logarithmic |
| `interaction` | -20 | 250ms | 250ms | Linear |
| `texture` | -24 | 1500ms | 1500ms | Logarithmic |

---

## Fade Curves

| Curve | Behavior | Best For |
|-------|----------|----------|
| `linear` | Constant rate | Default, technical |
| `logarithmic` | Slow start, fast end | Natural fade-ins |
| `exponential` | Fast start, slow end | Dramatic transitions |

**JSON Format:**
```json
// Simple format (linear default):
"fade_in": 2.0

// Object format (with curve):
"fade_in": {
  "duration": 2.0,
  "curve": "logarithmic"
}
```

---

## Scene Tonal Shaping

**Allowed at scene level:**
- `tilt`: "warm", "neutral", "bright"
- `high_shelf`: dB adjustment above ~4kHz
- `low_shelf`: dB adjustment below ~200Hz

**NOT allowed at scene level:**
- Narrow parametric bands
- HPF/LPF overrides
- Per-role EQ overrides

```json
"rules": {
  "eq": {
    "tilt": "warm"
  }
}
```

---

## Common Commands

```bash
# Render timeline
python main.py timeline.json output/final.wav

# With specific output
python main.py test/test_sfx_semantic.json output/test_sfx_semantic.wav
```

---

## Debugging Tips

1. **Check log output** — Set log level to DEBUG for detailed info
2. **Use timeline debug view** — Shows clip placement, fades, ducking
3. **Render short segments** — Faster iteration for testing
4. **Compare baseline vs semantic** — For SFX, render both to hear differences

---

## Key Rules to Remember

1. **Timeline-space processing** — Effects operate in timeline space, not clip space
2. **Defensive clip handling** — Skip clips without `start` time
3. **Rule merging order** — Global → Scene → Clip
4. **Deterministic rendering** — Same input = same output
5. **Processing order is sacred** — Don't change the DSP order

---

*Last updated: February 2026*
