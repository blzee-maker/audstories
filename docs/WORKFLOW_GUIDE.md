# PCDDJ Audio Storytelling Pipeline — Workflow Guide

*A practical reference for understanding, operating, and extending the end-to-end pipeline.*

---

## What This Pipeline Does

You write a story. The pipeline turns it into a fully mixed, broadcast-ready audio production — narration, background music, ambience, and sound effects — all scene-aware and mixed professionally. One command in, one `.wav` file out.

The system is built around three discrete engines that each do one job and hand off a structured JSON file to the next. No engine knows what came before or after it. They communicate entirely through files on disk.

```
story.txt
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  Engine 1 — Story-to-Script                         │
│  Reads raw text. Understands it. Describes it.      │
└──────────────────────┬──────────────────────────────┘
                       │  draft_timeline.json
                       ▼
┌─────────────────────────────────────────────────────┐
│  Engine 2 — Asset Engine                            │
│  Reads descriptions. Finds the audio that fits.     │
└──────────────────────┬──────────────────────────────┘
                       │  final_timeline.json
                       │  asset_manifest.json
                       ▼
┌─────────────────────────────────────────────────────┐
│  Engine 3 — Audio Engine                            │
│  Reads file paths and timing. Renders the WAV.      │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
                  final.wav
```

---

## The Three Engines in Detail

### Engine 1 — Story-to-Script

**Location:** `pcddj_engine/story-to-script/`  
**Input:** Raw story `.txt` file  
**Output:** `narrative_plan.json` + `draft_timeline.json`

This is the intelligence layer. It reads your story as prose and transforms it into a structured audio blueprint. It does not touch any audio files.

**What happens inside:**

1. **NLP pass (spaCy)** — sentence splitting, named entity recognition, tokenization. Identifies who is speaking and what is happening.
2. **Emotion and energy scoring** — each scene receives a 0.0–1.0 energy score and an emotion classification (tension, warmth, dread, wonder, etc.).
3. **Speaker attribution** — distinguishes the narrator from named characters. Assigns each line of dialogue to a speaker.
4. **Audio cue extraction** — identifies SFX moments, ambience type, and narration segments. This is where `"a door slams"` becomes `sfx_hint: "door_slam"`.
5. **LLM enrichment (optional)** — Gemini, OpenAI-compatible, or local Ollama can be used to produce richer, more contextual cues. When no LLM is available, deterministic heuristic classifiers run instead. Both paths produce the same output schema.
6. **DSL compilation** — everything is compiled into `draft_timeline.json`, a structured file with descriptor-level placeholders like `mood`, `atmosphere`, `sfx_hint`, and `tts_text`.

`draft_timeline.json` contains no file paths. It only describes intent — what kind of music should be playing, what the atmosphere feels like, what words should be spoken. Engine 2 turns those descriptions into real files.

**Status: Functionally complete.** This is the most mature component in the pipeline. 18 test files, solid coverage, deterministic fallback when LLM is unavailable.

---

### Engine 2 — Asset Engine

**Location:** `asset_engine/`  
**Input:** `draft_timeline.json`  
**Output:** `final_timeline.json` + `asset_manifest.json`

This is the logistics layer. It takes abstract descriptors and resolves them to concrete audio files. It does not do any audio processing — it only determines *which* files to use and *when* to play them.

**What happens inside:**

The Asset Engine uses a library-first model. It expects a folder of audio files that a human has curated. There is no external API call for music or ambience — you provide the library.

The workflow has a deliberate pause in the middle for you to fill in missing assets:

```
Step 1 — Scaffold
    asset-engine scaffold --draft draft_timeline.json --library workspace/projects/demo_project/assets/

    Creates a folder tree under workspace/projects/demo_project/assets/. Each folder is named after a descriptor.
    Voice folders contain a SCRIPT.txt with the exact line to record.
    Music/ambience/SFX folders contain a DESCRIPTOR.txt describing what to place there.

                ↓ (you fill the folders with audio files)

Step 2 — Status check
    asset-engine status --draft draft_timeline.json --library workspace/projects/demo_project/assets/

    Reports which clips are present vs. missing.
    Must show READY TO RESOLVE: YES before proceeding.

Step 3 — Resolve and assemble
    asset-engine run --draft draft_timeline.json --library workspace/projects/demo_project/assets/ --out workspace/projects/demo_project/output/

    Matches descriptors to files using token-overlap scoring.
    Probes file durations.
    Computes per-scene timing — which clip starts when, how long it runs.
    Emits final_timeline.json and asset_manifest.json.
```

**Confidence scoring in the manifest:**
- `1.0` — exactly one file found in the folder (exact match)
- `0.8` — multiple files in folder, alphabetical fallback used
- `0.0` — folder is empty or no match found

`final_timeline.json` contains real file paths with precise `start`, `duration`, and `offset` values for every clip. This is what Engine 3 reads.

**Status: Structurally complete.** Data flow, resolver architecture, timing computation, and CLI error handling are solid. The main open issue is a known bug in `catalog.find_best()` that can silently resolve a descriptor to an unrelated file when token overlap is zero. See the "What Needs Work" section.

---

### Engine 3 — Audio Engine

**Location:** `audio_engine/`  
**Input:** `final_timeline.json`  
**Output:** `final.wav`

This is the production layer. It reads the timeline and renders a multi-track, professionally mixed WAV. It has no understanding of story structure — it only knows file paths, timing, and DSP parameters.

**What happens inside:**

1. **Validation** — checks all referenced file paths exist, scene timing is internally consistent, and project duration is plausible.
2. **Scene preprocessing** — computes per-scene DSP parameters (EQ curve, ducking target gain, fade envelope).
3. **Multi-track rendering** — overlays voice, music, ambience, and SFX tracks according to the timeline.
4. **DSP chain per clip:**
   - 5 fade curve types: linear, exponential, logarithmic, S-curve, custom
   - 9 named EQ presets with versioning (dialogue clarity, warmth, brightness, etc.)
   - Voice-driven ducking: music and ambience automatically reduce in gain when voice is present
   - Role loudness balancing: narrator vs. character gain calibration
5. **Master processing** — LUFS normalization (broadcast/streaming target), peak limiting, master gain, fade-out.
6. **Two render modes:**
   - *Standard* — loads all audio into memory. Fast for short productions.
   - *Streaming* — chunked two-pass LUFS, lower memory footprint for long productions.

**Status: Feature-complete.** This is the most production-ready engine. The DSP chain is comprehensive and the render path is well-tested. The only hard dependency is that `audio/music/`, `audio/ambience/`, and `audio/sfx/` must contain actual WAV files before anything can render.

---

## How the Three Engines Connect

The key design decision is that each engine speaks a different language:

| Layer | Language | Example value |
|-------|----------|---------------|
| Engine 1 output | Descriptive intent | `mood: "dark_tense"`, `sfx_hint: "door_slam"` |
| Engine 2 output | Concrete file references | `file: "workspace/projects/demo_project/assets/sfx/door_creak_sfx.wav"`, `start: 4.2`, `duration: 1.8` |
| Engine 3 output | Rendered audio | `final.wav` |

This separation means each engine can be developed, tested, and replaced independently. You can swap Engine 1 for a different NLP approach without touching the audio renderer. You can upgrade the audio renderer's DSP without touching story analysis. The only contract between engines is the JSON schema.

The **orchestrator** (`run_pipeline.py`) chains all three in sequence, performs preflight checks at each stage, and exits with structured error messages if something is missing before wasting time on later stages.

---

## End-to-End Usage

### Why project-scoped assets are mandatory

Use a dedicated root per project to prevent asset and output collisions:

- `workspace/projects/<project_id>/assets/`
- `workspace/projects/<project_id>/output/`

This keeps parallel jobs isolated, simplifies cleanup, and avoids cross-project timeline references.

### Prerequisites

Each engine has its own Python virtual environment:

```
pcddj_engine/story-to-script/  →  venv with spaCy, sentence-transformers, httpx
asset_engine/                  →  pip install -e . (installs asset-engine CLI)
audio_engine/                  →  pip install -r requirements.txt
```

### One-command run (once setup is complete)

```powershell
python run_pipeline.py --story story.txt --project-id demo_project
```

### Manual step-by-step run

```powershell
# Step 1 — Engine 1: analyze story and produce draft timeline
cd pcddj_engine\story-to-script
audstories process --input story.txt --out ..\..\output\

# Step 2 — Engine 2: scaffold asset folders
asset-engine scaffold --draft workspace\projects\demo_project\output\draft_timeline.json --library workspace\projects\demo_project\assets\

# (fill asset folders with audio files — see below)

# Step 3 — Engine 2: verify asset library is complete
asset-engine status --draft workspace\projects\demo_project\output\draft_timeline.json --library workspace\projects\demo_project\assets\

# Step 4 — Engine 2: resolve and assemble final timeline
asset-engine run --draft workspace\projects\demo_project\output\draft_timeline.json --library workspace\projects\demo_project\assets\ --out workspace\projects\demo_project\output\

# Step 5 — Engine 3: render the WAV
cd audio_engine
python audio_engine\main.py ..\output\final_timeline.json ..\output\final.wav
```

### Naming your audio library files

Engine 2 matches descriptors to filenames using token overlap. The filename is the signal. If Engine 1 produces `mood: "dark_tense_underscore"`, a file named `dark_tense_underscore.wav` scores a perfect match. A file named `lullaby_soft.wav` scores zero.

**Rules for naming files:**
- Use the same keywords that appear in your story's mood and atmosphere descriptions
- Underscores between words, no spaces
- Common patterns: `<mood>_<context>_<type>.wav`
  - `dark_tense_underscore.wav`
  - `forest_rain_ambience.wav`
  - `door_creak_sfx.wav`
  - `warmth_strings_loop.wav`

Place files in:
- `audio_engine/audio/music/` — background music tracks
- `audio_engine/audio/ambience/` — environmental atmosphere loops
- `audio_engine/audio/sfx/` — one-shot sound effects
- `workspace/projects/<project_id>/assets/voice/<scene>/<clip>/` — recorded voice clips (named by scaffold)

---

## What the Pipeline Is Best At

**Structured narrative with clear scene transitions.** Stories that have defined scenes, changing emotional beats, a narrator voice, and dialogue will produce the richest output. Engine 1 was built for this shape of content.

**Library-based audio production.** If you have a curated set of audio assets with descriptive filenames, the pipeline resolves them accurately and places them precisely. The timing logic in Engine 2 is well-built and handles multi-clip scenes cleanly.

**Professional audio quality from simple input.** Engine 3's DSP chain — ducking, EQ, LUFS normalization, peak limiting — produces broadcast-quality output without any manual mixing. You do not need to touch a DAW.

**Fully offline operation.** The LLM is optional. With Ollama running locally or no LLM at all, the heuristic fallback in Engine 1 produces a complete `draft_timeline.json`. The asset library is local. The audio renderer has no network dependencies.

**Modular replacement of any layer.** Want to swap in ElevenLabs TTS? Replace the voice resolver in Engine 2. Want a different NLP model? Replace Engine 1's pipeline module. The JSON contracts between engines are the only interface.

---

## What Still Needs Work

### Hard blockers — pipeline cannot run without these

**1. The audio library is empty.**  
`audio_engine/audio/music/`, `audio_engine/audio/ambience/`, and `audio_engine/audio/sfx/` all contain no files. Neither Engine 2 nor Engine 3 can do anything until you place WAV files here. This is the most impactful single thing to address.

**2. Voice clips must be provided manually.**  
Engine 2 scaffolds the folders and writes `SCRIPT.txt` files, but no TTS synthesizer is connected. The `voice_resolver.py` currently produces a 190 Hz sine tone as a placeholder. Every voice clip in the rendered output will be a beep until you either record real clips into the scaffold folders or integrate a real TTS library (see below).

**3. `catalog.find_best()` silently returns a wrong file when score is zero.**  
If a descriptor has no token overlap with any filename in the library, the catalog returns the first alphabetically sorted file instead of reporting a miss. A descriptor like `epic_battle_drums` can silently resolve to `lullaby_soft.wav`. A minimum score threshold needs to be added so that zero-confidence matches return `None` and the pipeline warns rather than proceeding with wrong audio.

### High-priority correctness issues

**4. `assert` used as a production guard in `catalog.py`.**  
`assert self.library_root is not None` is silently bypassed when Python runs with the `-O` flag. Replace with an explicit `if` check and a `ValueError`.

**5. No LLM connection pooling.**  
Each call to `LocalLLMClient.complete()` and `OpenAIClient.complete()` creates a new `httpx.Client`. For a story with many scenes this adds significant latency. A persistent client should be shared across calls.

**6. `legacy_renderer.py` is ~497 lines of near-duplicate code.**  
The modern streaming renderer in `audio_engine/renderer/` is the correct path. The legacy file mirrors nearly the entire pipeline. Any bug fix must be applied in two places or the legacy path silently diverges. A parity test now exists — once it passes consistently, the legacy file should be deleted.

### Medium-priority robustness gaps

**7. No `--best-effort` mode in the Asset Engine.**  
A missing music or ambience file currently raises `ValueError` and aborts the entire pipeline. A `--best-effort` flag that skips missing assets with a logged warning instead of hard-failing would make iterative testing much faster.

**8. No asset duration caching.**  
Every `asset-engine run` re-probes all audio file durations from disk. Caching probed durations to a sidecar file would make repeat runs significantly faster for large libraries.

**9. No rate limiting for LLM batch calls.**  
Long stories can issue many LLM API calls in rapid succession with no backoff or throttle. On hosted APIs this can cause rate limit errors mid-run.

**10. `test_full_engine_lufs.py` has no assertions.**  
The test prints a LUFS value and always passes. It needs `assert -30.0 < lufs < -10.0` and a `pytest.skip` guard when the output file does not exist.

---

## Recommended Path to a First Full Render

Follow these steps in order. Each one unblocks the next.

**Step 1 — Rotate the Gemini API key** *(security — do this first)*  
The key in `pcddj_engine/story-to-script/.env` must be rotated. Go to [https://aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey), revoke the old key, generate a new one, and update `.env`. The committed `.env.example` file is the template — `.env` itself is gitignored.

**Step 2 — Add audio library files**  
Place at least 2–3 WAV files per category in:
- `audio_engine/audio/music/`
- `audio_engine/audio/ambience/`
- `audio_engine/audio/sfx/`

Name them to match the descriptors your story will generate (see the naming guide above).

**Step 3 — Run Engine 1 on your story**  
```powershell
audstories process --input story.txt --out workspace/projects/demo_project/output/
```
Inspect `workspace/projects/demo_project/output/draft_timeline.json`. Check the `mood`, `atmosphere`, and `sfx_hint` values — these are what Engine 2 will try to match against your library filenames.

**Step 4 — Scaffold and fill voice folders**  
```powershell
asset-engine scaffold --draft workspace/projects/demo_project/output/draft_timeline.json --library workspace/projects/demo_project/assets/
```
Each `voice/.../clip_xxx/` folder will contain a `SCRIPT.txt`. Record the line and drop the audio file into the folder. Run `asset-engine status` to confirm `READY TO RESOLVE: YES`.

**Step 5 — Fix the catalog score threshold**  
In `asset_engine/src/asset_engine/resolvers/catalog.py`, add a minimum score check to `find_best()` so it returns `None` on zero-overlap matches. This prevents wrong audio from silently entering the timeline.

**Step 6 — Run the full pipeline**  
```powershell
python run_pipeline.py --story story.txt --project-id demo_project
```

---

## Suggested Future Improvements

### Short-term (high value, low effort)

- **Connect a real TTS synthesizer.** `pyttsx3` is offline, has zero API cost, and can be integrated in under an hour. ElevenLabs or Google TTS can be swapped in later for quality. The voice resolver has a single stub method to replace.
- **Emotion-to-music BPM matching.** Engine 1 already computes an `energy_level` score (1–10) per scene. Pass it to the music resolver to prefer files with matching tempo metadata or filename keywords like `fast`, `slow`, `pulse`.
- **Asset library browser CLI.** A small command that prints each descriptor from `draft_timeline.json` alongside the file Engine 2 would resolve it to — before running the full pipeline. Useful for auditing matches without a full render.

### Medium-term

- **Automatic asset tagging.** Run a small audio classifier (e.g., YAMNet) over the library on first import to generate mood/tempo/environment tags. `catalog.find_best()` would then match on semantic tags instead of filename tokens, eliminating the filename-as-contract requirement.
- **Web UI dashboard.** A FastAPI + HTMX page to paste a story, click "Render", and watch the pipeline progress with a live log stream and waveform preview when done.
- **Per-character voice assignment.** Engine 1's speaker attribution already identifies named characters. Map each character name to a distinct TTS voice ID so the rendered output has distinguishable voices per character.

### Long-term architecture

- **Docker Compose setup.** One container per engine, a shared volume for JSON handoff files. Eliminates environment setup friction for spaCy model downloads and audio codec dependencies.
- **Unified `pyproject.toml` workspace.** A single `pip install -e .` that installs all three engines and their CLIs. Currently each engine requires separate environment setup.
- **Message queue between engines.** Engines emit events as they complete each scene. Engine 2 could start resolving assets for scene 1 while Engine 1 is still processing scene 3, reducing total wall-clock time for long productions.

---

## Quick Reference

| Command | What it does |
|---------|--------------|
| `audstories process --input story.txt --out workspace/projects/demo_project/output/` | Run Engine 1: story → draft timeline |
| `asset-engine scaffold --draft workspace/projects/demo_project/output/draft_timeline.json --library workspace/projects/demo_project/assets/` | Generate asset folder tree with SCRIPT.txt files |
| `asset-engine status --draft workspace/projects/demo_project/output/draft_timeline.json --library workspace/projects/demo_project/assets/` | Check how many clips are present vs. missing |
| `asset-engine run --draft workspace/projects/demo_project/output/draft_timeline.json --library workspace/projects/demo_project/assets/ --out workspace/projects/demo_project/output/` | Run Engine 2: draft timeline + library → final timeline |
| `python audio_engine/main.py output/final_timeline.json output/final.wav` | Run Engine 3: final timeline → rendered WAV |
| `python run_pipeline.py --story story.txt --project-id demo_project` | Run all three engines in sequence |

| File | What it is |
|------|-----------|
| `draft_timeline.json` | Engine 1 output — scene descriptors, no file paths |
| `final_timeline.json` | Engine 2 output — concrete file paths with timing |
| `asset_manifest.json` | Engine 2 output — provenance and confidence scores for every resolved asset |
| `final.wav` | Engine 3 output — rendered, mixed, mastered audio production |
| `PIPELINE_READINESS.md` | Current status checklist with hard blockers and minimum steps |
| `PIPELINE_STATUS.md` | Detailed per-engine issue tables with severity ratings |

---

*See `PIPELINE_READINESS.md` for the current go/no-go status of each engine, and `PIPELINE_STATUS.md` for the full issue backlog with severity ratings and suggested fixes.*
