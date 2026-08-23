# Design Decisions

This document captures key engineering decisions made during the development of the audio engine.

---

## 1. Timeline-Space vs Clip-Space Processing

### Decision
All perceptual effects (fades, ducking, compression) operate in **timeline space**, not clip space.

### Reasoning
- `AudioSegment.overlay()` doesn't preserve perceptual fades reliably
- Timeline-space processing mirrors DAW behavior exactly
- Ensures predictable interaction between all DSP systems
- Eliminates overlay-related artifacts

### Implementation
```
1. Place clip on canvas
2. Apply effects to the exact timeline slice
3. Effects see the audio in its final position
```

---

## 2. Scenes as Authoring Constructs

### Decision
Scenes are **author intent**, not runtime entities. They compile into regular clips during preprocessing.

### Reasoning
- Simplifies the rendering pipeline (only deals with clips)
- Scene rules merge cleanly into clip metadata
- Enables scene-level features without runtime complexity
- Clear separation between authoring (scenes) and rendering (clips)

### Implementation
```
Scene Block → Extract clips → Merge rules → Attach _rules metadata → Add to track
```

---

## 3. Intent-First EQ Design

### Decision
EQ is exposed through **semantic presets** (`dialogue_clean`, `music_bed`) rather than raw Hz values.

### Reasoning
- Timeline authors describe what they want, not how to achieve it
- Frequency knowledge stays internal to the engine
- Presets can evolve without breaking timelines
- Reduces cognitive load for non-audio-engineers

### Implementation
```json
// Author writes:
"eq_preset": "dialogue_clean"

// Engine applies internally:
high_pass: 80Hz, primary_band: +2dB @ 3kHz
```

---

## 4. Mix Role vs Semantic Role Separation

### Decision
For SFX, `role` (mix_role) and `semantic_role` are **orthogonal concepts**.

### Reasoning
- Mix role = where it sits in the mix hierarchy (foreground/background)
- Semantic role = what the sound represents (impact/movement/ambience)
- These answer different questions and shouldn't be conflated
- Allows flexible configuration (e.g., ambient SFX in foreground)

### Implementation
```json
{
  "role": "foreground",        // Mix hierarchy
  "semantic_role": "ambience"  // What it represents
}
```

---

## 5. Opt-In Ducking for SFX

### Decision
Semantic roles define **eligibility** for ducking, not mandatory behavior. Actual ducking requires explicit rules.

### Reasoning
- Keeps the system predictable and debuggable
- Authors have full control over ducking behavior
- Prevents unexpected volume changes
- Matches professional audio workflow expectations

### Implementation
```json
// SFX only ducks if explicitly configured:
"rules": [
  { "when": "voice", "duck": ["sfx:ambience"] }
]
```

---

## 6. Processing Order is Sacred

### Decision
The DSP processing order is fixed and documented. Do not change it.

### Order
```
1. Load audio
2. Apply track/clip gain
3. Apply EQ
4. Apply SFX processing
5. Apply energy ramp
6. Apply ducking
7. Apply compression
8. Overlay to canvas
9. Apply scene tonal shaping
10. Apply fades
```

### Reasoning
- EQ before ducking: spectral separation reduces need for heavy ducking
- Compression before fades: prevents fade from affecting compression
- LUFS on full mix: operates on perceptual loudness correctly
- Reordering causes subtle but significant audio artifacts

---

## 7. Defensive Clip Handling

### Decision
All functions that operate on clips **must skip clips without `start` time**.

### Reasoning
- Prevents crashes during intermediate compilation stages
- Scene preprocessing creates temporary clip states
- Graceful degradation over hard failures

### Implementation
```python
if clip.get("start") is None:
    continue  # Skip this clip
```

---

## 8. Rule Merging Strategy

### Decision
Rules merge in order: **Global → Scene → Clip** with later values overriding earlier.

### Reasoning
- Predictable override behavior
- Scene rules can adjust global defaults
- Clip rules can adjust scene settings
- Matches CSS-like specificity model

### Implementation
- Global `settings` are the base
- Scene `rules` override global
- Clip-level properties override scene
- Final merged result stored as `_rules`

---

## 9. Backward Compatibility for JSON Format

### Decision
New features use **object format** with fallback to simple values.

### Example: Fade Curves
```json
// Old format (still works):
"fade_in": 2.0

// New format (with curve):
"fade_in": {
  "duration": 2.0,
  "curve": "logarithmic"
}
```

### Reasoning
- Existing timelines continue to work
- No migration required
- Gradual adoption of new features
- Simple default case stays simple

---

## 10. Loudness Standard: Cinematic

### Decision
Default to **-20 LUFS** (cinematic standard) instead of streaming standards.

### Reasoning
- Preserves dynamic range for narrative audio
- Appropriate for audiobooks, dramas, podcasts
- Can be adjusted via settings for specific platforms
- Professional-grade audio quality

### Values
| Parameter | Value |
|-----------|-------|
| Target LUFS | -20.0 |
| Dialogue | ~-18 LUFS |
| Peak ceiling | -1.0 dBFS |

---

## 11. Logging Over Print Statements

### Decision
Use Python's `logging` module throughout, not print statements.

### Reasoning
- Configurable log levels (DEBUG, INFO, WARNING, ERROR)
- Can output to file or console
- Performance timing for profiling
- Professional debugging experience

### Implementation
```python
from utils.logger import get_logger
logger = get_logger(__name__)
logger.debug("Processing clip...")
```

---

## 12. Primary Band Constraints

### Decision
EQ primary bands are constrained to prevent "surgical drift."

### Constraints
| Parameter | Constraint | Rationale |
|-----------|------------|-----------|
| Q | 0.7 – 1.2 | Wide enough to be musical |
| Gain | ±3 dB max | Gentle shaping only |
| Frequency | 80 – 8000 Hz | Audible range |

### Reasoning
- Presets should be broad and musical
- Prevents narrow notches that cause artifacts
- Keeps EQ presets safe for all content types

---

## 13. Deterministic Rendering

### Decision
Same input **must always** produce same output.

### Reasoning
- Reproducible builds for quality assurance
- A/B testing requires identical baselines
- Debugging requires consistent behavior
- Professional workflow requirement

### Implementation
- No random elements in processing
- Fixed processing order
- Consistent floating-point handling

---

*Document created: February 2026*
