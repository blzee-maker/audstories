# Audio Engine — Technical Reference

This document describes the **audio_engine** Python package: what it does, how it is structured, and how the pieces fit together. It is aimed at maintainers and integrators who need a full map of the codebase, not only a feature list.

For a shorter **capabilities and limitations** overview, see [AUDIO_ENGINE_CAPABILITIES_V1.md](./AUDIO_ENGINE_CAPABILITIES_V1.md). For planning and known issues, see [AUDIO_ENGINE_WORKPLAN.md](../AUDIO_ENGINE_WORKPLAN.md) at the package root.

---

## 1. Purpose and scope

**audio_engine** is a **JSON-driven, offline audio renderer**. It reads a **timeline** (project duration, tracks, clips, optional scenes, and settings), loads audio files, applies DSP (EQ, ducking, compression, loudness, fades), mixes tracks onto a single bus, and exports **WAV**.

It is designed for **narration-centric, story-driven** content (fiction podcasts, audiobooks with beds, documentary-style mixes), not for real-time or interactive audio.

**Non-goals:** live playback API, game middleware, full DAW feature parity, inter-sample true-peak limiting (see capabilities doc).

---

## 2. Package facts

| Item | Detail |
|------|--------|
| **Project name** | `audio_engine` (see `pyproject.toml`) |
| **Python** | `>=3.9,<3.14` |
| **Primary I/O** | Timeline JSON → WAV file |
| **Core audio API** | [Pydub](https://github.com/jiaaro/pydub) `AudioSegment` (FFmpeg-backed for decode/encode) |
| **DSP helpers** | NumPy, SciPy (filters), pyloudnorm (LUFS), soundfile (header-only duration probe) |

Pinned dependencies live in `requirements.txt`; runtime deps are declared in `[project].dependencies` in `pyproject.toml`.

---

## 3. Source layout

```
audio_engine/                 # Python package (import name: audio_engine)
├── main.py                   # CLI: timeline JSON + output WAV
├── config.py                 # RenderConfig dataclass
├── validation.py             # Timeline validation; ValidationError
├── exceptions.py             # AudioEngineError hierarchy (+ re-export ValidationError)
├── scene_preprocessor.py     # Scenes → clips; dialogue density; rule merge
├── autofix.py                # Same-track overlap repair
├── legacy_renderer.py        # Deprecated monolithic renderer (parity with TimelineRenderer)
├── timeline_debug.py         # Standalone timeline printer (loads files for duration)
├── renderer/
│   ├── __init__.py           # Exports TimelineRenderer, render_timeline
│   ├── timeline_renderer.py  # Main orchestrator (standard + streaming)
│   ├── clip_processor.py     # Per-clip DSP chain and overlay
│   ├── track_mixer.py        # Per-track silent canvas + clip loop
│   └── master_processor.py   # Master gain, LUFS, peak norm, master fade-out
├── streaming/
│   ├── clip_scheduler.py     # Active clips per time window (incl. loops)
│   ├── chunk_loader.py       # Partial file reads → numpy float
│   ├── chunk_processor.py    # Parallel per-track chunk mix + streaming EQ/compressor
│   ├── stream_writer.py      # Incremental WAV writer
│   └── loudness.py           # Streaming LUFS/peak helpers
├── dsp/
│   ├── eq.py / eq_presets.py # Intent presets, scene tonal shaping
│   ├── fades.py / fade_curves.py
│   ├── loudness.py           # Integrated LUFS, apply_lufs_target
│   ├── normalization.py      # Peak normalization
│   ├── ducking.py            # Envelope ducking (“audacity” mode)
│   ├── compression.py      # Dialogue compression (standard path)
│   ├── balance.py            # Per-role LUFS targets (incl. SFX semantic)
│   ├── sfx_processor.py      # Semantic SFX: energy gain, defaults, loudness helpers
│   ├── streaming_eq.py       # Stateful biquad-style filters for streaming
│   └── streaming_compressor.py
└── utils/
    ├── logger.py
    ├── audio_probe.py        # probe_duration() via soundfile (no full decode)
    ├── ranges.py             # Range merge for ducking
    ├── debug.py              # debug_print_timeline (emoji layout)
    ├── energy_ramp.py        # Scene energy → music intensity
    ├── energy.py
    └── dialogue_density.py
tools/slice_audio/slice.py    # Utility script (package tools)
```

Asset folders at the repo root (`audio/Music`, `audio/ambience`, etc.) are organizational; the engine resolves paths from the timeline JSON as given.

---

## 4. Core concepts

### 4.1 Timeline structure (logical model)

A timeline is a **JSON object** with at least:

- **`project`** — Must include a positive **`duration`** (seconds).
- **`tracks`** — A list of tracks. Each track typically has **`id`**, **`role`** (mix role), optional **`gain`**, optional **`semantic_role`** (for SFX), **`clips`**, and optional **`eq_preset`**.
- **`settings`** — Global defaults: silence gaps, ducking, dialogue compression, loudness, peak normalization, master gain/fade, optional **`streaming`** block, optional **`eq`** for scene tonal shaping, **`debug`**, etc.
- **`scenes`** (optional) — Authoring blocks that **inject clips** into named tracks for time ranges; see §6.

**Mix role (`track.role`)** — Where the track sits in the mix hierarchy: e.g. `voice`, `music`, `background`, `sfx`. This drives default EQ presets, role loudness, ducking rule matching, and compression eligibility.

**Semantic role (`semantic_role`)** — For SFX, what the sound *means*: `impact`, `movement`, `ambience`, `interaction`, `texture`. Used for SFX-specific processing, `sfx:*` ducking keys, and validation. Clip-level semantic role overrides track-level.

### 4.2 Clips

Each clip usually references a **`file`**, **`start`** (seconds on the timeline), optional **`gain`**, **`fade_in` / `fade_out`** (seconds or `{ "duration", "curve" }`), **`loop`** + **`loop_until`** for looping beds, optional **`eq_preset`**, optional **`semantic_role`**, and optional **`duration_seconds`** (avoids probing the file when correct).

Internal fields added at runtime include **`_rules`** (merged scene/global rules), **`_audio_override`** (streaming), **`_timeline_start`**, **`_overlay_start`**, **`_skip_eq`**, **`_skip_compression`**.

---

## 5. End-to-end pipeline (standard render)

The primary entry point is **`TimelineRenderer.render(timeline_path, output_path)`** in `renderer/timeline_renderer.py`.

```mermaid
flowchart LR
  A[Load JSON] --> B[preprocess_scenes]
  B --> C[auto_fix_overlaps per track]
  C --> D[validate_timeline]
  D --> E[RenderConfig from settings]
  E --> F[Silent canvas = project duration]
  F --> G[For each track: TrackMixer.process_track]
  G --> H[Overlay track onto canvas]
  H --> I[apply_scene_tonal_shaping if settings.eq]
  I --> J[MasterProcessor.process]
  J --> K[Export WAV]
```

1. **Load timeline** — JSON parse; errors become `FileError`.
2. **`preprocess_scenes`** — If `scenes` exist, expand scene clips onto tracks, compute dialogue density and scene energy rules, optional scene crossfades.
3. **`auto_fix_overlaps`** — Sorts clips on each track; shifts starts forward if they overlap (optional **`min_gap`** from `default_silence`). Looped clips adjust `loop_until` when shifted.
4. **`validate_timeline`** — Structural checks, file existence, duration via **`duration_seconds` or `probe_duration`**, ducking rule references, semantic roles. **Errors raise `ValidationError`**; warnings are logged.
5. **`RenderConfig.from_timeline_settings`** — Maps `settings` (loudness, normalize, master gain, master fade, streaming defaults, `debug`) into a **`RenderConfig`**.
6. **Debug** — If `settings.debug` is true, **`debug_print_timeline`** runs (verbose stdout).
7. **Role ranges** — If ducking is enabled, **`get_role_ranges`** builds `(start, end)` intervals per mix role and per `sfx:<semantic>` for envelope ducking.
8. **Canvas** — Silent `AudioSegment` for full project length.
9. **Tracks** — For each track, **`TrackMixer`** builds a track-length buffer by repeatedly calling **`ClipProcessor.process_clip`** and overlays each track onto the canvas.
10. **Scene EQ** — **`apply_scene_tonal_shaping`** on the full mix (tilt / shelves from `settings["eq"]`).
11. **Master** — **`MasterProcessor`**: master gain → optional integrated LUFS → optional peak normalize → optional master fade-out.
12. **Export** — **`canvas.export(output_path, format="wav")`**; output directory is created if needed.

The convenience function **`render_timeline()`** in `renderer/timeline_renderer.py` constructs a **`TimelineRenderer`** and calls **`render()`**.

---

## 6. Scene preprocessor (`scene_preprocessor.py`)

**`preprocess_scenes(timeline)`** runs when the timeline contains a **`scenes`** array.

- Builds a **`track_map`** by track `id`.
- Collects **voice** clip time ranges for **dialogue density** over each scene window (`compute_dialogue_density` / `classify_dialogue_density`).
- For each scene: merges **global `settings`** with **scene `rules`** via **`merge_rules`** (shallow merge; nested dicts merge one level).
- For each scene’s per-track clip list: copies clips, sets **`start = scene_start + offset`**, inherits **`semantic_role`** from track if missing, sets **`loop_until`** to scene end when looping, attaches **`_rules`** (density ratio/label, scene energy, previous scene energy, energy ramp duration).
- Optionally **`apply_scene_crossfades`** when `settings.scene_crossfade.enabled` — adjacent scene clips that “touch” get injected fade durations and slight start overlap.

This turns **high-level scene authoring** into ordinary **track clips** the rest of the engine already understands.

---

## 7. Clip processing order (`clip_processor.py`)

Order matters, especially for ducking vs EQ. The implementation follows this sequence (see module docstring in `clip_processor.py`):

1. Load audio (or use **`_audio_override`** in streaming).
2. **Gain** — Track gain + optional clip gain (dB).
3. **EQ** — `clip.eq_preset` → `track.eq_preset` → **`get_preset_for_role(track_role, semantic_role)`**, unless **`_skip_eq`**.
4. **SFX processing** — For `track_role == "sfx"` and a semantic role: **`apply_sfx_processing`**, then **`apply_role_loudness`** for that clip (SFX semantic targets).
5. **Energy ramp** — **`apply_energy_ramp`** using scene energy and music/background roles.
6. **Dialogue density** — For `background` / `music`, optional dB pullback by density label.
7. **Timeline position** — `start` / `_timeline_start`, `_overlay_start` for chunk-relative overlay.
8. **Looping** — Repeat audio to fill `[start, loop_until)` when `loop` is true.
9. **Ducking** — Rules keyed by **`when`** (mix role or `sfx:role`) and **`duck`** targets; **`audacity`** mode uses **`apply_envelope_ducking`**; **`scene`** mode applies a flat dB offset.
10. **Dialogue compression** — Voice tracks when compression is enabled and not **`_skip_compression`**.
11. **Overlay** — Clip audio onto the track canvas at **`_overlay_start`** (or `start`).
12. **Canvas fades** — Per-clip `fade_in` / `fade_out`, or SFX semantic defaults from **`get_sfx_fade_behavior`**.

Fades are applied **on the canvas** after overlay so that ducking and clip audio are shaped in **timeline space** (consistent with DAW-style behavior).

---

## 8. Renderer components

### 8.1 `TrackMixer`

- Allocates a **silent buffer** of `project_duration`.
- For each clip, delegates to **`ClipProcessor.process_clip`**.
- After all clips, applies **`apply_role_loudness`** for **non-SFX** tracks (SFX loudness is handled per clip in **`ClipProcessor`**).

### 8.2 `MasterProcessor`

- **`master_gain`** (dB).
- **`loudness`** — **`apply_lufs_target`** to **`target_lufs`** when enabled in config.
- **`normalize_peak`** — Peak normalization to **`peak_target_dbfs`** (default -1 dBFS).
- **`master_fade_out`** — End-of-mix fade using **`apply_fade_out`** and **`FadeCurve`**.

### 8.3 `RenderConfig` (`config.py`)

Central mapping from timeline **`settings`** to behavior:

| Field | Role |
|-------|------|
| `target_lufs`, `loudness` | Integrated loudness normalization |
| `normalize_peak`, `peak_target_dbfs` | Peak ceiling |
| `master_gain`, `master_fade_out` | Master bus |
| `default_silence` | Minimum gap for overlap auto-fix |
| `streaming_*` | Chunk size, workers, sample format, two-pass LUFS toggle |
| `debug` | Enable timeline debug print |

---

## 9. DSP layer (`dsp/`)

| Module | Responsibility |
|--------|----------------|
| **`eq` / `eq_presets`** | Named presets (dialogue, music, SFX), scene-level tilt/shelves; numpy/SciPy processing |
| **`fades` / `fade_curves`** | Fade-in/out on segments with linear/log/exp curves |
| **`loudness`** | Measure integrated LUFS; **`apply_lufs_target`** |
| **`normalization`** | Sample peak normalization |
| **`ducking`** | **`apply_envelope_ducking`** — merge dialogue ranges, fade down/up around speech |
| **`compression`** | **`apply_dialogue_compression`** (Pydub dynamic range) |
| **`balance`** | **`ROLE_LUFS_TARGETS`** and semantic SFX targets; bridges to **`apply_lufs_target`** |
| **`sfx_processor`** | Semantic loudness targets, fade defaults, scene-energy gain curves, **`get_sfx_fade_behavior`** |

**Validation** (`validation.py`) defines **`VALID_SEMANTIC_ROLES`** consistent with SFX processing.

---

## 10. Streaming render (`render_streaming`)

**`TimelineRenderer.render_streaming`** implements a **chunked** pipeline for long projects or constrained memory.

1. Same preprocessing, overlap fix, validation, and role-range setup as standard render.
2. **`ClipScheduler`** — For each `[chunk_start, chunk_end)`, computes active **`ClipSlice`** entries per track (non-looped: overlap trim; looped: repeated slices via **`_add_looped_slices`**).
3. **`ChunkProcessor.process_chunk`** — For each chunk:
   - **Parallel** per-track workers (`ThreadPoolExecutor`, `max_workers` from config).
   - **`ChunkLoader.get_chunk`** loads only the needed slice; resamples/channels to streaming format.
   - Streaming **EQ chain** (high/low pass + peak EQ from preset) may run in numpy form; then **`ClipProcessor`** is invoked with **`_audio_override`**, **`_skip_eq`** / **`_skip_compression`** as appropriate.
   - **Role loudness** on track buffer; **streaming compressor** for voice when dialogue compression is on.
   - Tracks are **overlaid** into one chunk buffer.
4. **`StreamWriter`** — Appends raw PCM frames to a WAV file.
5. **Per-chunk master treatment** — `master_gain`, optional **rolling LUFS estimator** or **two-pass** measure (`measure_lufs_from_file` on a temp file) + gain, **`StreamingPeakEstimator`** when peak normalize is on, **`apply_scene_tonal_shaping`**, **`apply_fade_out`** for master fade on the last segment logic.

**Note:** Streaming and standard paths aim for **parity** on DSP intent; exact numerical identity is not guaranteed across chunk boundaries for all stateful effects—see tests and workplan for parity thresholds.

---

## 11. Validation (`validation.py`)

- **`project.duration`** required and positive.
- **`tracks`** must be a list; each track’s **`clips`** must be a list.
- Files must exist; duration from **`duration_seconds`** or **`probe_duration`** (soundfile header read).
- Clip **`start`**, overlap warnings, loop **`loop_until`** sanity.
- **Ducking** rules: `sfx:<name>` references must use valid semantic roles.

**`ValidationError`** is defined here and re-exported from **`exceptions`** for a single import story.

---

## 12. Utilities

| Module | Purpose |
|--------|---------|
| **`utils/audio_probe.py`** | **`probe_duration(path)`** — fast duration via `soundfile.info`; raises `ValueError` on unreadable audio |
| **`utils/ranges.py`** | Merges time ranges (used by ducking) |
| **`utils/logger.py`** | Shared logger + `@log_performance` |
| **`utils/debug.py`** | **`debug_print_timeline`** — human-readable timeline dump (use with `settings.debug`) |
| **`utils/energy_ramp.py`** | Music intensity vs scene energy |
| **`utils/dialogue_density.py`** | Ratio and labels for scene rules |

---

## 13. CLI (`main.py`)

```text
python -m audio_engine.main <timeline.json> <output.wav>
```

Uses **`TimelineRenderer().render(...)`** (standard path, not streaming). Streaming is API-only unless you add a wrapper.

---

## 14. Legacy renderer (`legacy_renderer.py`)

An older **monolithic** implementation that duplicates much of the pipeline. The module-level **`render_timeline`** in **`legacy_renderer`** emits a **`DeprecationWarning`** (scheduled removal in v0.3 per message in source). Prefer **`TimelineRenderer`** from **`audio_engine.renderer`** or the thin **`render_timeline()`** wrapper exported from **`renderer/timeline_renderer.py`** (that wrapper is **not** deprecated—it delegates to **`TimelineRenderer.render`**). New work should not call **`legacy_renderer.render_timeline`**.

---

## 15. Extension and testing

- **Injected components** — **`TimelineRenderer`** accepts optional **`ClipProcessor`**, **`TrackMixer`**, **`MasterProcessor`** for unit testing.
- **`ClipProcessor`** accepts injectable ducking/compression/fade callables (defaults lazy-imported).
- Tests live under the package **`tests/`** directory (e.g. legacy parity); run with **`pytest`**.

---

## 16. Related documents

| Document | Contents |
|----------|----------|
| [AUDIO_ENGINE_CAPABILITIES_V1.md](./AUDIO_ENGINE_CAPABILITIES_V1.md) | Feature matrix, limitations, tradeoffs |
| [AUDIO_ENGINE_FEATURE_AUDIT.md](./AUDIO_ENGINE_FEATURE_AUDIT.md) | Feature audit |
| [AUDIO_ENGINE_STATUS.md](./AUDIO_ENGINE_STATUS.md) | Status tracking |
| [AUDIO_ENGINE_ANALYSIS.md](./AUDIO_ENGINE_ANALYSIS.md) | Analysis notes |
| [AUDIO_ENGINE_WORKPLAN.md](../AUDIO_ENGINE_WORKPLAN.md) | Blockers, fixes, implementation log |

---

## 17. Mental model (one paragraph)

**audio_engine** is a **deterministic offline mixer**: a JSON timeline describes **when** each file plays and **how** it should behave (roles, scenes, rules). The preprocessor **flattens scenes** into clips; overlap repair and validation **sanitize** the timeline; each track is built by **loading slices**, **shaping** them with EQ and role semantics, **ducking** them against speech or other roles, and **overlaying** them in time; the **master bus** applies loudness and safety limits; **streaming** repeats the same idea in **time windows** with **stateful** DSP where needed. Everything ultimately reduces to **Pydub segments** (or chunked numpy) and a **WAV** file on disk.
