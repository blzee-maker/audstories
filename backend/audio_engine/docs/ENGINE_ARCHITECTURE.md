# Audio Engine Architecture

This document explains how the audio engine works, comparing the **legacy (monolithic) architecture** with the **current modular architecture**, and detailing the rendering pipeline, streaming capabilities, and DSP processing chain.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Legacy vs Current Architecture](#legacy-vs-current-architecture)
3. [Rendering Pipeline](#rendering-pipeline)
4. [Streaming Pipeline](#streaming-pipeline)
5. [DSP Processing Chain](#dsp-processing-chain)
6. [Component Breakdown](#component-breakdown)
7. [Timeline Processing Flow](#timeline-processing-flow)

---

## Architecture Overview

The audio engine transforms **timeline JSON files** into **rendered audio output**. It supports two rendering modes:

| Mode | Use Case | Memory | Performance |
|------|----------|--------|-------------|
| **Standard Render** | Short-to-medium projects | Full project in memory | Fast for <30 min |
| **Streaming Render** | Long projects, low memory | Chunked processing | Scalable |

### Core Design Principles

1. **Deterministic Output** — Same input always produces identical output
2. **Timeline-Space Processing** — All effects operate in final timeline position
3. **Scenes as Authoring Constructs** — Scenes compile to clips at preprocessing
4. **Intent-Based DSP** — Semantic presets over raw parameters
5. **Modular Architecture** — Testable, replaceable components

---

## Legacy vs Current Architecture

### Legacy Architecture (`legacy_renderer.py`)

The original implementation was a **single monolithic file** (~476 lines) that handled everything:

```
┌─────────────────────────────────────────────────────────────┐
│                    legacy_renderer.py                        │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ load_timeline()                                         ││
│  │ create_canvas()                                         ││
│  │ get_role_ranges()                                       ││
│  │ apply_clip()          ← All DSP inline                  ││
│  │ render_timeline()     ← All orchestration here          ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

**Problems with Legacy:**
- ❌ Single 476-line file with mixed responsibilities
- ❌ DSP functions tightly coupled to rendering
- ❌ Difficult to test individual components
- ❌ No streaming support (entire project in memory)
- ❌ Hard to extend without breaking existing code
- ❌ No dependency injection for mocking

### Current Architecture (Modular)

The new architecture separates concerns into **dedicated modules**:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         TimelineRenderer                                 │
│                     (orchestrator/coordinator)                          │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        ▼                        ▼                        ▼
┌───────────────┐      ┌─────────────────┐      ┌─────────────────┐
│ ClipProcessor │      │   TrackMixer    │      │ MasterProcessor │
│  (clip DSP)   │      │ (track mixing)  │      │ (master effects)│
└───────┬───────┘      └────────┬────────┘      └────────┬────────┘
        │                       │                        │
        └───────────────────────┴────────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
            ┌─────────────┐         ┌─────────────┐
            │  dsp/*.py   │         │ streaming/* │
            │ (effects)   │         │ (chunked)   │
            └─────────────┘         └─────────────┘
```

**Benefits of Current Architecture:**
- ✅ **Separation of Concerns** — Each component has a single responsibility
- ✅ **Testability** — Components can be tested in isolation
- ✅ **Dependency Injection** — Easy mocking for unit tests
- ✅ **Streaming Support** — Chunked processing for large projects
- ✅ **Extensibility** — Add new DSP without touching orchestration
- ✅ **Maintainability** — Smaller, focused files

---

## Rendering Pipeline

### Standard Render Flow

```
                    ┌──────────────────┐
                    │  Timeline JSON   │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │  Load Timeline   │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ Scene Preprocess │  ← Scenes → Clips
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │  Auto-Fix Gaps   │  ← Resolve overlaps
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │    Validate      │  ← Check timeline
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ Calculate Ranges │  ← For ducking
                    └────────┬─────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
   ┌─────────┐         ┌─────────┐         ┌─────────┐
   │ Track 1 │         │ Track 2 │         │ Track N │
   │ Process │         │ Process │         │ Process │
   └────┬────┘         └────┬────┘         └────┬────┘
        │                    │                    │
        └────────────────────┼────────────────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │   Mix Tracks     │  ← Overlay all
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ Scene Tonal EQ   │  ← Broad shaping
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ Master Process   │  ← LUFS, fade-out
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │   Export WAV     │
                    └──────────────────┘
```

### Track Processing (per track)

Each track creates its own buffer, processes all clips, then returns the mixed buffer:

```python
# TrackMixer.process_track()
track_buffer = AudioSegment.silent(duration=project_duration)

for clip in clips:
    track_buffer = clip_processor.process_clip(
        canvas=track_buffer,
        clip=clip,
        track_gain=track_gain,
        role_ranges=role_ranges,
        ...
    )

# Apply track-level loudness
track_buffer = apply_role_loudness(track_buffer, track_role)
return track_buffer
```

---

## Streaming Pipeline

The streaming pipeline processes audio in **time chunks** to handle projects larger than available memory.

### Streaming Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         render_streaming()                               │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │     ClipScheduler      │  ← Which clips are active
                    │  (per-chunk planning)  │     in this time window?
                    └───────────┬────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
   ┌────▼────┐            ┌─────▼─────┐           ┌─────▼────┐
   │ Chunk 1 │            │  Chunk 2  │           │ Chunk N  │
   │ 0s-1s   │            │  1s-2s    │           │ Ns-(N+1)s│
   └────┬────┘            └─────┬─────┘           └─────┬────┘
        │                       │                       │
        ▼                       ▼                       ▼
   ┌─────────────────────────────────────────────────────────┐
   │              ChunkProcessor (parallel)                   │
   │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐    │
   │  │ Track A │  │ Track B │  │ Track C │  │ Track D │    │
   │  │ Worker  │  │ Worker  │  │ Worker  │  │ Worker  │    │
   │  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘    │
   │       └───────────┬┴───────────┘┴───────────┘          │
   │                   ▼                                     │
   │           Mix Track Buffers                             │
   └───────────────────┬─────────────────────────────────────┘
                       │
                       ▼
              ┌────────────────┐
              │  StreamWriter  │  ← Append to output file
              └────────────────┘
```

### Streaming Components

| Component | Responsibility |
|-----------|----------------|
| **ClipScheduler** | Determines which clips overlap each time chunk |
| **ChunkProcessor** | Processes all tracks within a chunk using parallel workers |
| **StreamWriter** | Writes processed chunks to output file incrementally |
| **ClipSlice** | Represents a portion of a clip within a chunk window |

### LUFS Normalization in Streaming

Streaming mode supports two approaches for loudness normalization:

**Two-Pass LUFS (Default):**
```
Pass 1: Render to temp file → Measure LUFS
Pass 2: Apply gain correction → Write final file
```

**Single-Pass Estimation:**
```
Rolling LUFS estimator → Apply estimated gain per chunk
(Less accurate but faster)
```

---

## DSP Processing Chain

The processing order is **critical** and should not be modified. Each step depends on the previous state.

### Clip Processing Order

```
┌─────────────────────────────────────────────────────────────┐
│  1. LOAD AUDIO                                              │
│     Load from file or use _audio_override (streaming)       │
└───────────────────────────────┬─────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────┐
│  2. GAIN APPLICATION                                        │
│     audio = audio + track_gain + clip_gain                  │
└───────────────────────────────┬─────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────┐
│  3. EQ (Intent-Based Presets)                               │
│     "dialogue_clean", "music_bed", "sfx_punch", etc.        │
│     → Shapes frequencies before other processing            │
└───────────────────────────────┬─────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────┐
│  4. SFX SEMANTIC PROCESSING                                 │
│     Apply loudness/fade defaults based on semantic_role     │
│     (impact, movement, ambience, interaction, texture)      │
└───────────────────────────────┬─────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────┐
│  5. ENERGY RAMP                                             │
│     Adjust music intensity based on scene energy (0.0-1.0)  │
│     Smooth ramping between scene transitions                │
└───────────────────────────────┬─────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────┐
│  6. DIALOGUE DENSITY ADJUSTMENT                             │
│     For background/music: pull back when dialogue is dense  │
│     high: -6dB | medium: -3dB | low: +0dB                   │
└───────────────────────────────┬─────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────┐
│  7. LOOPING (if enabled)                                    │
│     Repeat audio until loop_until timestamp                 │
└───────────────────────────────┬─────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────┐
│  8. DUCKING (Audacity-style Envelope)                       │
│     Duck background/music when voice is present             │
│     Configurable: fade_down_ms, fade_up_ms, duck_amount     │
└───────────────────────────────┬─────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────┐
│  9. DIALOGUE COMPRESSION (voice tracks only)                │
│     Light compression for consistent dialogue levels        │
└───────────────────────────────┬─────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────┐
│  10. OVERLAY TO CANVAS                                      │
│      canvas.overlay(audio, position=start_ms)               │
└───────────────────────────────┬─────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────┐
│  11. FADES (In/Out)                                         │
│      Apply fade curves: linear, logarithmic, exponential    │
│      SFX semantic defaults if not specified                 │
└─────────────────────────────────────────────────────────────┘
```

### Master Processing Order

After all tracks are mixed:

```
┌─────────────────────────────────────────────────────────────┐
│  1. SCENE TONAL EQ                                          │
│     Broad shaping: tilt, high_shelf, low_shelf              │
└───────────────────────────────┬─────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────┐
│  2. MASTER GAIN                                             │
│     Final volume adjustment                                 │
└───────────────────────────────┬─────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────┐
│  3. LUFS NORMALIZATION                                      │
│     Target: -20 LUFS (cinematic standard)                   │
│     Measures integrated loudness, applies gain              │
└───────────────────────────────┬─────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────┐
│  4. PEAK NORMALIZATION (optional)                           │
│     Ensure peaks don't exceed -1.0 dBFS                     │
└───────────────────────────────┬─────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────┐
│  5. MASTER FADE OUT                                         │
│     End-of-story fade with configurable curve               │
└─────────────────────────────────────────────────────────────┘
```

### Why This Order?

| Step | Reason for Position |
|------|---------------------|
| **EQ before ducking** | Spectral separation reduces need for heavy ducking |
| **SFX before ducking** | Semantic loudness must be set before ducking calculations |
| **Compression before fades** | Prevents fades from affecting compression dynamics |
| **Fades on canvas** | Timeline-space fades match DAW behavior |
| **LUFS on full mix** | Measures perceptual loudness of final mix |

---

## Component Breakdown

### `TimelineRenderer` (Orchestrator)

The main entry point that coordinates the rendering pipeline.

```python
class TimelineRenderer:
    def __init__(self):
        self.clip_processor = ClipProcessor()
        self.track_mixer = TrackMixer(self.clip_processor)
        self.master_processor = MasterProcessor()
    
    def render(self, timeline_path, output_path):
        # 1. Load and preprocess
        # 2. Process tracks
        # 3. Apply master effects
        # 4. Export
    
    def render_streaming(self, timeline_path, output_path):
        # Chunked processing for large projects
```

### `ClipProcessor` (Clip-Level DSP)

Handles all per-clip audio processing.

**Key Methods:**
- `process_clip()` — Apply all effects to a single clip

**Dependencies (injectable):**
- `ducking_func` — Envelope-based ducking
- `compression_func` — Dialogue compression
- `fade_in_func` / `fade_out_func` — Fade application

### `TrackMixer` (Track-Level Operations)

Manages track buffers and clip mixing.

**Key Methods:**
- `process_track()` — Process all clips on a track, return mixed buffer
- `apply_tonal_shaping()` — Scene-level EQ (convenience wrapper)

### `MasterProcessor` (Master Effects)

Applies final processing to the mixed output.

**Effects Applied:**
1. Master gain
2. LUFS normalization
3. Peak normalization
4. Master fade-out

### `RenderConfig` (Settings Container)

Dataclass holding all render configuration:

```python
@dataclass
class RenderConfig:
    target_lufs: float = -20.0
    normalize_peak: bool = False
    master_gain: float = 0.0
    master_fade_out: Optional[Dict] = None
    chunk_size_sec: float = 1.0
    streaming_max_workers: int = 4
    # ... etc
```

---

## Timeline Processing Flow

### Scene Preprocessing

Scenes are **authoring constructs** that compile into regular clips:

```
┌──────────────────────────────────────────────────────────────┐
│  Scene Block                                                  │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ id: "scene_1"                                           │ │
│  │ start: 10.0                                             │ │
│  │ duration: 30.0                                          │ │
│  │ energy: 0.7                                             │ │
│  │ tracks:                                                 │ │
│  │   music: [{ file: "intro.mp3", loop: true }]            │ │
│  │   voice: [{ file: "line1.wav", offset: 2 }]             │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼ preprocess_scenes()
┌──────────────────────────────────────────────────────────────┐
│  Expanded Clips (added to tracks)                            │
│                                                              │
│  Music Track:                                                │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ file: "intro.mp3"                                       │ │
│  │ start: 10.0                                             │ │
│  │ loop: true                                              │ │
│  │ loop_until: 40.0                                        │ │
│  │ _rules:                                                 │ │
│  │   scene_energy: 0.7                                     │ │
│  │   dialogue_density_label: "medium"                      │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                              │
│  Voice Track:                                                │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ file: "line1.wav"                                       │ │
│  │ start: 12.0      ← (scene_start + offset)               │ │
│  │ _rules:                                                 │ │
│  │   scene_energy: 0.7                                     │ │
│  │   prev_scene_energy: 0.5                                │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### Rule Merging

Rules merge in order: **Global → Scene → Clip** (later overrides earlier)

```
Global Settings          Scene Rules           Final _rules
┌───────────────┐       ┌───────────────┐      ┌───────────────┐
│ ducking:      │       │ ducking:      │      │ ducking:      │
│   amount: -12 │   +   │   amount: -8  │  →   │   amount: -8  │  ← Scene override
│   enabled: ✓  │       │               │      │   enabled: ✓  │  ← Global preserved
│ energy: 0.5   │       │ energy: 0.7   │      │ energy: 0.7   │  ← Scene override
└───────────────┘       └───────────────┘      └───────────────┘
```

---

## Summary: Before vs After

| Aspect | Legacy | Current |
|--------|--------|---------|
| **Files** | 1 monolithic file | 6+ specialized modules |
| **Testing** | Integration only | Unit + Integration |
| **Memory** | Full project | Streaming option |
| **Extensibility** | Edit main file | Add new DSP modules |
| **Parallelism** | Sequential | Parallel track workers |
| **Dependencies** | Hardcoded imports | Dependency injection |
| **Backward Compat** | N/A | `render_timeline()` preserved |

---

*Document created: February 2026*
