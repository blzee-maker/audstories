# Asset Engine — Design Document & Redesign Plan
*Status: Active Development | Last Updated: 2026-03-04*

---

## Table of Contents

1. [What the Asset Engine Does](#1-what-the-asset-engine-does)
2. [Current Architecture](#2-current-architecture)
3. [Current Problems](#3-current-problems)
4. [Redesign: Library-First Approach](#4-redesign-library-first-approach)
5. [New Workflow (Detailed)](#5-new-workflow-detailed)
6. [Folder Scaffold Design](#6-folder-scaffold-design)
7. [Matching Strategy (Folder-First)](#7-matching-strategy-folder-first)
8. [Phase Roadmap](#8-phase-roadmap)
9. [Thoughts, Suggestions & Ideas](#9-thoughts-suggestions--ideas)
10. [Files to Create or Modify](#10-files-to-create-or-modify)

---

## 1. What the Asset Engine Does

The Asset Engine is the **bridge** between Engine 1 (story analysis) and Engine 3 (audio renderer). It takes abstract descriptors and turns them into concrete audio file paths with timing.

```
draft_timeline.json          final_timeline.json
(descriptors, no files)  →   (real file paths + timing)
                         +   asset_manifest.json
```

**What it receives (from Engine 1):**

| Field | Example | Meaning |
|-------|---------|---------|
| `tts_text` | `"She opened the door slowly."` | Narration/dialogue to be spoken |
| `mood` | `"tension_mid"` | Music mood descriptor |
| `atmosphere` | `"dark_interior"` | Ambience descriptor |
| `sfx_hint` | `"door_creak"` | Sound effect descriptor |

**What it must produce (for Engine 3):**

| Field | Example | Meaning |
|-------|---------|---------|
| `file` | `"assets/voice/scene_01_narrator_0.wav"` | Real path to audio file |
| `offset` | `1.2` | Start time within scene (seconds) |
| `loop_until` | `14.5` | End time for looping clips |
| `duration` | `3.1` | Duration of the clip |

---

## 2. Current Architecture

```
run_asset_pipeline.py
        │
        ├─ extract_requirements()       ← flatten draft clips → AssetRequirement list
        │
        ├─ run_scaffold_phase()         ← create folder tree with SCRIPT.txt / DESCRIPTOR.txt
        │
        ├─ resolve_from_library()       ← folder-first lookup for all asset types
        │       (voice, music, ambience, sfx all use the same folder scan)
        │
        ├─ compute_timing()             ← voice ordering + scene start times + durations
        │
        ├─ assemble_final_timeline()    ← build FinalTimeline from resolved assets + timing
        │
        └─ validate_final_timeline()    ← check file existence, offsets, loop sanity
```

The `library_resolver` scans scaffolded folders by asset kind and picks the audio file in each folder. Exact folder-name match, no guessing.

---

## 3. Current Problems

### Critical

| Problem | Impact | Status |
|---------|--------|--------|
| ~~**TTS is a 190 Hz sine tone**~~ | ~~Every voice clip is inaudible garbage~~ | **RESOLVED** — `voice_resolver.py` removed. Voice uses folder-first lookup via `library_resolver.py`; missing clips get silence placeholders. |
| **`find_best()` always returns something** — if `score == 0` (no token overlap), it still returns the first alphabetical file | `"epic_battle_drums"` resolves to `"lullaby_soft.wav"` silently | Open (old `catalog.py` path; not used by active pipeline which uses `library_resolver`) |
| **No logging anywhere** — failures in resolvers, timing, and assembly produce raw Python tracebacks | Impossible to debug in production | Partially resolved — logging added to library_resolver and pipeline |

### High

| Problem | Impact |
|---------|--------|
| **CLI has no error handling** — any exception produces a raw traceback | Poor user experience |
| **`assert` used as production guard** in `catalog.py` | Silently disabled under `python -O` |
| **No soft-fail mode** — one missing asset aborts the entire pipeline | A missing ambience file stops all voice and music too |
| **Test coverage ~15–20%** — resolvers, timing, assembly have no unit tests | Regressions go undetected |

### Root Cause

The fundamental design problem is that the catalog tries to **guess** which file matches a descriptor by comparing filename tokens. This is inherently unreliable because the library was never designed around the descriptor vocabulary that Engine 1 generates.

**The fix:** make the folder structure itself the contract. If Engine 1 needs `"tension_mid"` music, there should be a folder called `tension_mid/` in the library. Exact match, no guessing.

---

## 4. Redesign: Library-First Approach

### Core Idea

Instead of guessing which file matches a descriptor, the Asset Engine becomes a **two-stage process**:

```
Stage 1 — SCAFFOLD          Stage 2 — RESOLVE
─────────────────           ─────────────────
Read draft_timeline  →  Generate folder structure
                         with instructions
                              │
                              ▼
                         User places audio files
                         in the correct folders
                              │
                              ▼
                         Engine scans folders  →  final_timeline.json
                         (exact folder match)  +  asset_manifest.json
```

### Why This Is Better

| Old Approach | New Approach |
|-------------|-------------|
| Guess from filename tokens | Exact folder name = descriptor |
| Fragile, wrong matches | Deterministic, always correct |
| User doesn't know what files are needed | User gets a clear folder + instructions file |
| TTS stub blocks pipeline | Voice folder + `.txt` file tells user what to record |
| All-or-nothing | Missing files produce clear warnings, not silent errors |
| Requires a pre-built library organized by our naming rules | User can reuse any existing audio collection |

### The Key Insight for Voice

Voice is different from music/ambience/SFX because it is **text-specific** — each clip is for a particular line of dialogue. The scaffold creates one folder per voice clip with a `SCRIPT.txt` file containing the exact text. The user (or later a TTS API) places the corresponding WAV file in that folder.

This also means voice recordings can be done in any tool (Audacity, a phone recorder, ElevenLabs UI) and just dropped in without any code change.

---

## 5. New Workflow (Detailed)

```
┌─────────────────────────────────────────────────────────────────────┐
│                        ASSET ENGINE WORKFLOW                        │
└─────────────────────────────────────────────────────────────────────┘

INPUT: draft_timeline.json  (from Engine 1)

                         │
                         ▼
            ┌────────────────────────┐
            │  1. EXTRACT            │
            │  requirements/         │
            │  extractor.py          │
            │                        │
            │  Parse all scenes and  │
            │  tracks. Produce a     │
            │  typed list of what    │
            │  audio is needed.      │
            └───────────┬────────────┘
                        │
                        ▼
            ┌────────────────────────┐
            │  2. SCAFFOLD    [NEW]  │
            │  scaffold/             │
            │  builder.py            │
            │                        │
            │  Create folder tree.   │
            │  Write SCRIPT.txt for  │
            │  voice, DESCRIPTOR.txt │
            │  for music/sfx/ambi.   │
            │  Write REQUIREMENTS.md │
            └───────────┬────────────┘
                        │
                        ▼ (user fills folders with audio files)
                        │
            ┌────────────────────────┐    ← can be run immediately if
            │  3. RESOLVE    [NEW]   │       files already exist, or
            │  resolvers/            │       after user places files
            │  library_resolver.py   │
            │                        │
            │  Scan each scaffolded  │
            │  folder for any audio  │
            │  file. Return path or  │
            │  log a warning.        │
            └───────────┬────────────┘
                        │
                        ▼
            ┌────────────────────────┐
            │  4. TIMING             │
            │  timing/               │
            │  scene_timing.py       │
            │  (unchanged)           │
            │                        │
            │  Voice ordering,       │
            │  scene durations,      │
            │  project duration.     │
            └───────────┬────────────┘
                        │
                        ▼
            ┌────────────────────────┐
            │  5. ASSEMBLE           │
            │  assembly/             │
            │  timeline_assembler.py │
            │  (minor changes)       │
            │                        │
            │  Build FinalTimeline   │
            │  and AssetManifest.    │
            └───────────┬────────────┘
                        │
                        ▼
            ┌────────────────────────┐
            │  6. VALIDATE           │
            │  validation/           │
            │  final_validator.py    │
            │  (unchanged)           │
            │                        │
            │  Check file existence, │
            │  offsets, loop sanity. │
            └───────────┬────────────┘
                        │
                        ▼

OUTPUT: final_timeline.json + asset_manifest.json  (→ Engine 3)
```

### CLI Commands After Redesign

```bash
# Stage 1: Scaffold (run once per story)
asset-engine scaffold --draft workspace/projects/demo_project/output/draft_timeline.json --library workspace/projects/demo_project/assets/

# Stage 2: Resolve (run after placing files, can be re-run)
asset-engine resolve --draft workspace/projects/demo_project/output/draft_timeline.json --library workspace/projects/demo_project/assets/ --out workspace/projects/demo_project/output/

# Or run both in sequence (scaffold if needed, then resolve)
asset-engine run --draft workspace/projects/demo_project/output/draft_timeline.json --library workspace/projects/demo_project/assets/ --out workspace/projects/demo_project/output/
```

---

## 6. Folder Scaffold Design

### Generated Folder Tree

Given a story with 2 scenes, the scaffold creates:

```
workspace/projects/demo_project/assets/
│
├── REQUIREMENTS.md              ← Human-readable summary of all needed files
│
├── voice/
│   ├── scene_01_village_square/
│   │   ├── clip_0_narrator/
│   │   │   ├── SCRIPT.txt       ← "The square was empty at dawn."
│   │   │   └── [place WAV here] ← user drops audio file here
│   │   └── clip_1_elder_thomas/
│   │       ├── SCRIPT.txt       ← "We should leave before nightfall."
│   │       └── [place WAV here]
│   └── scene_02_forest_path/
│       └── clip_0_narrator/
│           ├── SCRIPT.txt       ← "The trees whispered in the wind."
│           └── [place WAV here]
│
├── music/
│   ├── tension_mid/
│   │   ├── DESCRIPTOR.txt       ← "Mood: tension_mid | Energy: 0.7 | Scene: village_square"
│   │   └── [place WAV/MP3 here]
│   └── calm_reflective/
│       ├── DESCRIPTOR.txt       ← "Mood: calm_reflective | Energy: 0.3 | Scene: forest_path"
│       └── [place WAV/MP3 here]
│
├── ambience/
│   ├── dark_interior/
│   │   ├── DESCRIPTOR.txt       ← "Atmosphere: dark_interior | Scene: village_square"
│   │   └── [place WAV/MP3 here]
│   └── outdoor_night/
│       ├── DESCRIPTOR.txt       ← "Atmosphere: outdoor_night | Scene: forest_path"
│       └── [place WAV/MP3 here]
│
└── sfx/
    ├── door_creak/
    │   ├── DESCRIPTOR.txt       ← "SFX: door_creak | Role: interaction | Scene: village_square"
    │   └── [place WAV here]
    └── thunder_distant/
        ├── DESCRIPTOR.txt       ← "SFX: thunder_distant | Role: impact | Scene: forest_path"
        └── [place WAV here]
```

### REQUIREMENTS.md Format

The scaffold also writes a human-readable summary at the top level:

```markdown
# Asset Requirements
Generated from: draft_timeline.json
Scenes: 2 | Total requirements: 9

## Voice (3 clips)
All voice clips need audio files (.wav preferred).
Each folder contains a SCRIPT.txt with the exact text to record or synthesize.

| Folder | Text | Duration Estimate |
|--------|------|-------------------|
| voice/scene_01_village_square/clip_0_narrator | The square was empty at dawn. | ~2.5s |
| voice/scene_01_village_square/clip_1_elder_thomas | We should leave before nightfall. | ~3.2s |
| voice/scene_02_forest_path/clip_0_narrator | The trees whispered in the wind. | ~3.0s |

## Music (2 clips — can loop)
Place any music file in the folder. Looping files work best (seamless loop points).

| Folder | Mood | Energy | Used In |
|--------|------|--------|---------|
| music/tension_mid | tension_mid | 0.70 | village_square |
| music/calm_reflective | calm_reflective | 0.30 | forest_path |

## Ambience (2 clips — will loop)
Background room tone / environment. Any ambient loop works.

| Folder | Atmosphere | Used In |
|--------|-----------|---------|
| ambience/dark_interior | dark_interior | village_square |
| ambience/outdoor_night | outdoor_night | forest_path |

## SFX (2 clips)
One-shot sound effects. Short WAV files are ideal.

| Folder | Hint | Semantic Role | Used In |
|--------|------|---------------|---------|
| sfx/door_creak | door_creak | interaction | village_square |
| sfx/thunder_distant | thunder_distant | impact | forest_path |

---
Supported formats: .wav, .mp3, .ogg, .flac, .m4a
Run `asset-engine resolve` after placing all files.
```

---

## 7. Matching Strategy (Folder-First)

### How the New Resolver Works

The new `LibraryResolver` replaces `AssetCatalog.find_best()` with a folder-based exact lookup:

```
For each AssetRequirement:
  1. Compute the expected folder path from the descriptor
  2. Scan that folder for any audio file
  3a. If found → use it (confidence = 1.0, source = "library")
  3b. If not found → log a warning, mark requirement as UNRESOLVED
  3c. If multiple files found → use alphabetically first, log a warning
```

### Descriptor → Folder Name Mapping

The folder name is derived deterministically from the descriptor by sanitizing it to filesystem-safe characters:

```python
# "tension mid" → "tension_mid"
# "outdoor/night" → "outdoor_night"
# "door creak (metal)" → "door_creak_metal"
folder_name = re.sub(r"[^a-z0-9]+", "_", descriptor.lower()).strip("_")
```

This is the same token as what Engine 1 already generates in `dsl/constants.py` for moods and atmospheres — the names are already filesystem-safe.

### Partial Library Support

If only some folders are populated, the engine continues in "partial mode":

```
voice/scene_01_narrator/clip_0   → ✅ found narrator_line_01.wav
voice/scene_01_narrator/clip_1   → ⚠ MISSING — skipping clip
music/tension_mid                → ✅ found tension_mid_loop.mp3
ambience/dark_interior           → ⚠ MISSING — silence will be used
sfx/door_creak                   → ✅ found door_creak.wav
```

Missing voice clips skip that line of dialogue. Missing music/ambience produce silence in that layer. Missing SFX are simply dropped. The pipeline does not abort.

### Priority Order Within a Folder

If a folder contains multiple audio files:

1. Any file whose stem exactly matches the folder name (e.g., `tension_mid.wav` in `tension_mid/`)
2. Otherwise, alphabetically first file

---

## 8. Phase Roadmap

### Phase 1 — Library-Only (implement now)

**Goal:** Full pipeline working with user-supplied files. No external APIs.

| Task | File | Priority |
|------|------|----------|
| Build `scaffold/builder.py` — create folder tree + instruction files | `scaffold/builder.py` | P0 |
| Build `resolvers/library_resolver.py` — folder-first lookup | `resolvers/library_resolver.py` | P0 |
| Add `scaffold` and `resolve` subcommands to `cli.py` | `cli.py` | P0 |
| Add logging throughout pipeline | all modules | P0 |
| Add try/except with clean error messages to CLI | `cli.py` | P0 |
| Fix `assert` → `if` check in `catalog.py` | `catalog.py` | P1 |
| Add minimum score threshold to old `find_best()` (returns `None` on 0 score) | `catalog.py` | P1 |
| Add partial-mode (skip missing, log warning) to pipeline | `run_asset_pipeline.py` | P1 |
| Write unit tests for `builder.py` and `library_resolver.py` | `tests/` | P1 |
| Write end-to-end test: scaffold → place files → resolve | `tests/` | P1 |

**Deliverable:** Run `asset-engine scaffold`, drop in any audio files, run `asset-engine resolve`, get `final_timeline.json`.

---

### Phase 2 — TTS Integration (next after Phase 1)

**Goal:** Auto-fill voice folders using a free or paid TTS engine.

| Task | Notes |
|------|-------|
| Add `tts/` module with a `TTSProvider` base class | Defines `synthesize(text, out_path)` interface |
| Implement `PyttsTTSProvider` using `pyttsx3` | Offline, zero cost, lower quality |
| Wire TTS into scaffold — if `--tts` flag is passed, auto-generate voice files | Populates `voice/` folders automatically |
| Add `--tts-provider` CLI argument (`pyttsx3`, `elevenlabs`, `openai`) | Easy to swap backends |
| Cache by content hash of `tts_text` — skip re-synthesis if WAV already exists | Avoids re-generating on every run |

```bash
# Future usage
asset-engine scaffold --draft workspace/projects/demo_project/output/draft.json --library workspace/projects/demo_project/assets/ --tts pyttsx3
# → scaffolds folders AND auto-generates voice WAVs using pyttsx3
```

---

### Phase 3 — Premium Integrations (later)

| Feature | API / Library | Notes |
|---------|--------------|-------|
| High-quality TTS | ElevenLabs, OpenAI TTS, Google Cloud TTS | Per-character voice assignment using Engine 1 speaker names |
| Music generation | Suno, Udio, MusicGen (local) | Generate `music/tension_mid/` automatically from mood descriptor |
| SFX generation | ElevenLabs Sound FX, Freesound API | Auto-download matching SFX for each descriptor |
| Voice cloning | ElevenLabs, Coqui XTTS | Let user record a reference voice clip and clone it for all dialogue |
| Semantic audio search | OpenAI embeddings + Freesound | Match descriptors to online audio databases semantically |

---

## 9. Thoughts, Suggestions & Ideas

### On the Scaffold Approach

**The folder structure is the user interface.** Clear folder names + instruction files mean no documentation is needed. A non-technical user can fill the library by reading `REQUIREMENTS.md` and dragging files into folders. This is far more accessible than a command-line matching algorithm.

**Reuse across stories.** If the user builds a library over time — collecting good `tension_mid`, `calm_reflective`, `outdoor_night` files — each new story that generates those same descriptors automatically finds the right files without the user doing anything. The library compounds in value.

**Version the library.** Consider allowing multiple files per folder (e.g., `tension_mid_v1.wav`, `tension_mid_v2.wav`) and let the user pin a version in a `library.lock.json` file. This way the library can grow without changing past renders.

---

### On Voice Specifically

**Separate voice identity from voice content.** The scaffold currently organizes voice by scene + clip index. A better organization might be by character:

```
voice/
├── narrator/
│   ├── scene_01_clip_0/  SCRIPT.txt: "The square was empty..."
│   └── scene_02_clip_0/  SCRIPT.txt: "The trees whispered..."
├── elder_thomas/
│   └── scene_01_clip_1/  SCRIPT.txt: "We should leave..."
```

This way, when the user records `elder_thomas`, they record all his lines together in one session — more natural. And when TTS integration arrives, you can assign one voice ID to the entire `elder_thomas/` folder.

**Add a `voice_cast.json` config.** Let the user optionally define:
```json
{
  "narrator": { "voice": "natural", "pace": "slow" },
  "elder_thomas": { "voice": "gravelly", "pace": "normal" }
}
```
This config would be read by Phase 2 TTS integration to pick the right voice settings per character.

---

### On Music & Ambience

**Loop detection.** Music and ambience clips are marked `loop: true` in the draft timeline. Looping works best with seamlessly looped audio. Consider adding a `loop_check.py` utility that scans music/ambience files and warns if a file's start/end samples differ significantly (indicating it was not designed to loop).

**Multiple variants per mood.** Allow multiple files in a mood folder (e.g., 3 different `tension_mid` loops) and randomly select one per render pass. This prevents the same loop from always playing and makes repeated renders feel fresher.

**Energy scaling.** Engine 1 emits an `energy_hint` (0.0–1.0) alongside the mood. Use this to pick between variants:
- `tension_mid_low.wav` (energy 0.0–0.4)
- `tension_mid_mid.wav` (energy 0.4–0.7)
- `tension_mid_high.wav` (energy 0.7–1.0)

This can be encoded in the filename and parsed by the resolver automatically.

---

### On the Pipeline Architecture

**Add a `--dry-run` flag** to `asset-engine resolve`. It scans all folders and reports what is found and what is missing, but does not write `final_timeline.json`. Lets the user verify before committing to a full render.

```bash
asset-engine resolve --dry-run --draft workspace/projects/demo_project/output/draft.json --library workspace/projects/demo_project/assets/
# Output:
# ✅ voice (3/3 found)
# ✅ music (2/2 found)
# ⚠  ambience: outdoor_night — MISSING
# ✅ sfx (2/2 found)
# 1 missing asset. Run without --dry-run to render with silence for missing assets.
```

**Add a `status` command** that shows the current state of the library relative to a draft:

```bash
asset-engine status --draft workspace/projects/demo_project/output/draft.json --library workspace/projects/demo_project/assets/
```

**Consider an `asset_library.json` index file.** After the first scaffold run, write a JSON index of all folders and their expected content. On subsequent runs, the engine can quickly diff the index against what actually exists rather than scanning the filesystem from scratch.

---

### On Quality & Correctness

**Silence padding for missing voice clips.** If a voice clip is missing, rather than skipping it, insert a silence clip of the estimated duration (computed from `tts_text` word count). This preserves the timing of subsequent clips in the same scene.

**Add `confidence` to the manifest.** The manifest already has a `confidence` field. Use it meaningfully:
- `1.0` — exact folder name match, one file in folder
- `0.8` — exact folder name match, multiple files (used first alphabetically)
- `0.0` — missing, silence used

**Warn on format mismatch.** If Engine 3 is configured for 48 kHz / 16-bit but a library file is 44.1 kHz / 24-bit, log a warning. Pydub will transcode but the user should know.

---

### On Developer Experience

**Make the scaffold idempotent.** Re-running scaffold should not overwrite existing audio files or `.txt` instruction files if the folder already exists and already has content. Only create new folders for new requirements. This lets the user safely re-run scaffold after the story changes.

**Color-coded CLI output.** Add simple ANSI color codes to the CLI output:
- Green `✅` for resolved assets
- Yellow `⚠` for missing (soft warning)
- Red `✖` for hard failures (file corrupt, parse error)

**Progress bar for large libraries.** If the library has hundreds of files, the index scan could take a moment. Add a simple tqdm progress indicator during the catalog indexing step.

---

## 10. Files to Create or Modify

### New Files to Create

```
asset_engine/src/asset_engine/
├── scaffold/
│   ├── __init__.py
│   └── builder.py          ← ScaffoldBuilder class
│
└── resolvers/
    └── library_resolver.py ← LibraryResolver class (folder-first)
```

### Files to Modify

| File | Changes Needed |
|------|---------------|
| `cli.py` | Add `scaffold`, `resolve`, `status`, `run` subcommands; add try/except error handling |
| `pipeline/run_asset_pipeline.py` | Add partial-mode (skip missing); add logging; separate scaffold and resolve phases |
| `resolvers/catalog.py` | Fix `assert` → `if`; add minimum score threshold (return `None` on score=0) |
| ~~`resolvers/voice_resolver.py`~~ | **Deleted** — was dead code. Voice resolution handled by `library_resolver.py`. |
| `requirements/extractor.py` | Add estimated duration to `AssetRequirement` for voice (from word count) |
| `contracts/requirements_models.py` | Add `estimated_duration: float \| None` field to `AssetRequirement` |

### New Test Files to Create

```
asset_engine/tests/
├── test_scaffold_builder.py         ← test folder creation, REQUIREMENTS.md content
├── test_library_resolver.py         ← test exact match, multiple files, missing folder
└── test_e2e_scaffold_and_resolve.py ← test full two-stage workflow with real temp dirs
```

---

## Summary

| Phase | State | Goal |
|-------|-------|------|
| **Phase 1: Library-Only** | Build now | Scaffold folders → user fills → resolve → final_timeline.json |
| **Phase 2: Free TTS** | After Phase 1 | `pyttsx3` auto-fills voice folders, no API key needed |
| **Phase 3: Premium APIs** | After Phase 2 | ElevenLabs, MusicGen, Freesound for production-quality assets |

**The guiding principle:** make the simplest thing work first. A user dropping a WAV file into the right folder is more reliable than any matching algorithm. Build the pipeline around that reliability, then add automation on top.
