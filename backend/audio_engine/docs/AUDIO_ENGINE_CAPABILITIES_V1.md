# Audio Engine Capabilities (v1)

**Document Version:** 1.0  
**Last Updated:** February 2026  
**Audience:** Engineers, maintainers, and future contributors

---

## What This Engine Does Well

### Timeline & Rendering Core

- **JSON-driven timeline format** — Single source of truth for all audio behavior
- **Deterministic rendering** — Same input always produces identical output
- **Multi-track composition** — Supports voice, music, ambience, and SFX tracks
- **Scene-based authoring** — Scenes compile into clips at preprocessing; clean separation between author intent and runtime entities
- **Auto-fix overlaps** — Automatically detects and resolves clip collisions on the same track
- **Input validation** — Validates timeline structure and file existence before rendering

### DSP Processing

| Capability | Description |
|------------|-------------|
| **EQ Presets** | Intent-based presets (`dialogue_clean`, `music_bed`, `sfx_punch`, etc.) — authors describe what they want, engine handles frequency details |
| **Scene Tonal Shaping** | Broad tonal adjustments at scene level: `tilt` (warm/neutral/bright), `high_shelf`, `low_shelf` |
| **Ducking** | Audacity-style envelope-based ducking with configurable fade-down/fade-up, onset delay, and minimum pause threshold |
| **Dialogue Compression** | Per-voice-track compression with configurable threshold, ratio, attack, release, and makeup gain |
| **Fade Curves** | Three curve types: linear (default), logarithmic (natural fade-ins), exponential (dramatic transitions) |
| **Scene Crossfades** | Automatic fade-out/fade-in with overlap between adjacent scenes |
| **LUFS Normalization** | Industry-standard loudness normalization targeting -20 LUFS (cinematic standard) |
| **Peak Normalization** | Optional safety limiter ensuring peaks don't exceed -1.0 dBFS |
| **Role-Based Loudness** | Different LUFS targets per role (voice, music, background, SFX semantic roles) |

### SFX Semantic Processing

Five semantic roles with role-specific behavior:

| Role | LUFS Target | Fade In | Fade Out | Curve |
|------|-------------|---------|----------|-------|
| `impact` | -18.0 | 0ms | 75ms | Exponential |
| `movement` | -20.0 | 150ms | 150ms | Linear |
| `ambience` | -22.0 | 750ms | 750ms | Logarithmic |
| `interaction` | -20.0 | 250ms | 250ms | Linear |
| `texture` | -24.0 | 1500ms | 1500ms | Logarithmic |

Semantic roles participate in ducking via explicit rules (e.g., `{ "when": "voice", "duck": ["sfx:ambience"] }`).

### Scene Intelligence

- **Energy system** — Scene energy (0.0–1.0) drives music gain with smooth transitions between scenes
- **Dialogue density analysis** — Automatic categorization (high/medium/low) with corresponding music pullback
- **Rule merging** — Global settings → Scene rules → Clip properties, with later values overriding earlier

### Streaming Render

- **Chunked processing** — Time-windowed rendering for projects larger than available memory
- **Clip scheduling** — Determines which clips are active per chunk, including loop handling
- **Parallel track workers** — Per-chunk track processing uses thread pool
- **Two-pass LUFS** — Accurate loudness normalization via measure-then-correct passes
- **Stateful DSP** — Streaming compressor and EQ filters maintain state across chunk boundaries
- **Peak normalization** — Full two-pass support in streaming mode

### Architecture

- **Modular design** — Separate components for clip processing, track mixing, and master processing
- **Dependency injection** — DSP functions are injectable for testing
- **Legacy compatibility** — `render_timeline()` API preserved for backward compatibility
- **Standard/Streaming parity** — Both render modes apply the same DSP chain

---

## Supported Use Cases

This engine is designed for **narration-centric, story-driven audio content**:

| Use Case | Suitability |
|----------|-------------|
| Audio drama / fiction podcasts | ✅ Primary target |
| Audiobooks with music/ambience | ✅ Well-suited |
| Narration-heavy content | ✅ Well-suited |
| Documentary-style audio | ✅ Well-suited |
| Podcast production | ✅ Supported |
| Long-form content (1+ hours) | ✅ Via streaming mode |
| Music-only production | ⚠️ Possible, but not optimized for |
| Real-time audio processing | ❌ Not designed for |
| Interactive/game audio | ❌ Not designed for |

**Output characteristics:**

- WAV format (uncompressed)
- Configurable sample rate (44.1kHz, 48kHz typical)
- -20 LUFS integrated loudness (cinematic standard)
- -1.0 dBFS peak ceiling (when peak normalization enabled)

---

## Current Limitations

### Not Implemented

| Limitation | Category | Notes |
|------------|----------|-------|
| No reverb or spatial effects | DSP | No room simulation, panning, or 3D audio |
| No true-peak limiting | Mastering | Peak normalization uses sample peaks, not inter-sample peaks |
| No multiband compression | DSP | Single-band dialogue compression only |
| No API server | Interface | Command-line only; no REST/HTTP interface |
| No automatic semantic role detection | SFX | Roles must be explicitly specified; no filename inference |

### Partially Implemented

| Feature | Status | Location |
|---------|--------|----------|
| SFX micro-timing | Placeholder only | `dsp/sfx_processor.py:182-187` — function body is effectively `pass` |
| Sample-accurate energy ramps | Unused | `interpolate_gain()` defined but not called; pydub fade approximation used instead |
| Continuous dialogue density | Calculated but unused | Ratio (0.0–1.0) computed but only categorical label applied |

### Performance Constraints

| Constraint | Standard Render | Streaming Render |
|------------|-----------------|------------------|
| Memory | Full project in memory | Chunked; low memory |
| Parallelism | Sequential track processing | Parallel track workers per chunk |
| Best for | Projects < 30 minutes | Projects of any length |

---

## Intentional Tradeoffs

These are deliberate design choices, not oversights.

### 1. Intent-First EQ via Presets

**Choice:** Authors use semantic presets (`dialogue_clean`, `music_bed`) rather than raw Hz/Q/gain values.

**Rationale:**
- Timeline authors describe what they want, not how to achieve it
- Frequency knowledge stays internal to the engine
- Presets can evolve without breaking existing timelines
- Reduces cognitive load for non-audio-engineers

### 2. Timeline-Space Processing

**Choice:** All perceptual effects (fades, ducking) operate in timeline space, not clip space.

**Rationale:**
- `AudioSegment.overlay()` doesn't preserve perceptual fades reliably
- Timeline-space processing mirrors DAW behavior exactly
- Ensures predictable interaction between DSP systems

### 3. Scenes as Authoring Constructs

**Choice:** Scenes are not runtime entities; they compile to clips during preprocessing.

**Rationale:**
- Simplifies the rendering pipeline (only deals with clips)
- Scene rules merge cleanly into clip metadata
- Clear separation between authoring and rendering

### 4. Opt-In Ducking for SFX

**Choice:** Semantic roles define ducking *eligibility*, not mandatory behavior. Actual ducking requires explicit rules.

**Rationale:**
- Keeps the system predictable and debuggable
- Authors have full control over ducking behavior
- Prevents unexpected volume changes
- Matches professional audio workflow expectations

### 5. Minimal SFX Timing Adjustments

**Choice:** No automatic timeline position changes or delay compensation for SFX.

**Rationale:**
- Prevents sync drift and hard-to-trace bugs
- Audio position is author-controlled
- Micro-timing (silence trimming) is non-destructive to timeline

### 6. Fixed DSP Processing Order

**Choice:** Processing order is documented and immutable.

**Rationale:**
- EQ before ducking: spectral separation reduces need for heavy ducking
- Compression before fades: prevents fades from affecting compression
- LUFS on full mix: operates on perceptual loudness correctly
- Reordering causes subtle but significant artifacts

### 7. Categorical Dialogue Density

**Choice:** Dialogue density uses categorical labels (high/medium/low), not continuous ratio.

**Rationale:**
- Simpler to reason about and debug
- Avoids micro-adjustments that are imperceptible
- Three levels map to clear -6dB/-3dB/+0dB adjustments

### 8. Scene Tonal Shaping Restrictions

**Choice:** Scene-level EQ is limited to broad adjustments (tilt, shelves). No narrow parametric bands or HPF/LPF overrides.

**Rationale:**
- Prevents conflicts with role-based EQ presets
- Broad shaping is safer for all content types
- Narrow bands are handled at preset level

### 9. LUFS Correction Clamping

**Choice:** LUFS gain adjustments are clamped (max +6 dB boost, max -10 dB cut).

**Rationale:**
- Prevents noise floor amplification on quiet content
- Avoids over-correction on very loud content
- Safety bounds for unpredictable input levels

---

## Deferred / v2 Candidates

The following features are known but intentionally not implemented in v1.

### High Priority (Likely v2)

| Feature | Notes |
|---------|-------|
| **REST API** | FastAPI server for programmatic access; removes CLI-only constraint |
| **True-peak limiting** | Inter-sample peak detection for broadcast compliance |
| **SFX micro-timing implementation** | Currently placeholder; needs actual silence-trimming logic |
| **Sample-accurate energy ramps** | Replace pydub fade approximation with `interpolate_gain()` |

### Medium Priority

| Feature | Notes |
|---------|-------|
| **Reverb / spatial effects** | Room simulation, panning, stereo width |
| **Parallel standard render** | Track-level parallelism for non-streaming mode |
| **Additional SFX semantic roles** | `foley`, `atmosphere`, `sting`, custom roles |
| **Automatic semantic role inference** | Optional detection from file paths/names |

### Lower Priority / Research

| Feature | Notes |
|---------|-------|
| **Multiband EQ/compression** | More surgical frequency control; currently single-band only |
| **Continuous dialogue density** | Use computed ratio instead of categorical label |
| **ML-based semantic classification** | Automatic audio content analysis |
| **Real-time preview** | Live playback during editing (significant architecture change) |

---

## Reference: Processing Order

This order is **critical** and must not be changed.

### Clip-Level DSP

```
1.  Load audio
2.  Apply track/clip gain
3.  Apply EQ (role preset)
4.  Apply SFX semantic processing
5.  Apply energy ramp (background/music)
6.  Apply dialogue density adjustment
7.  Apply looping (if enabled)
8.  Apply ducking
9.  Apply dialogue compression (voice only)
10. Overlay to canvas
11. Apply fades
```

### Master Processing

```
12. Mix tracks
13. Apply scene tonal shaping
14. Apply master gain
15. Apply LUFS normalization
16. Apply peak normalization (optional)
17. Apply master fade-out (optional)
18. Export
```

---

## Reference: Loudness Standard

| Parameter | Value |
|-----------|-------|
| Integrated LUFS target | -20.0 |
| Dialogue anchor | ~-18 LUFS |
| True peak ceiling | -1.0 dBFS |

This preserves dynamic range appropriate for story-driven audio content.

---

*Document created: February 2026*
