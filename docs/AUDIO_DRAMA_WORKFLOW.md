# Audio Drama Workflow

This document explains how the audio drama system in this repository works: the user-facing workflow, the three engines, the project files they exchange, and the major features available around script parsing, asset preparation, timing, mixing, API usage, and final delivery.

The short version:

```text
Fountain script
  -> Engine 1: story-to-script
  -> narrative_plan.json + draft_timeline.json
  -> Engine 2: asset_engine
  -> scaffolded asset folders, final_timeline.json, asset_manifest.json
  -> Engine 3: audio_engine
  -> mixed WAV
```

The local drama workflow is centered on `drama_cli.py` and `run_pipeline.py`. The project data lives under `workspace/projects/<project_id>/`.

## Repository Map

| Path | Role |
| --- | --- |
| `drama_cli.py` | Drama-focused CLI for creating projects, managing chapters, dry parsing scripts, running Stage 1, resuming Stage 2, and managing Gita continuity. |
| `run_pipeline.py` | Main orchestrator. It calls Engine 1, applies delivery presets, runs asset scaffolding/resolution, renders the final WAV, and performs preflight checks. |
| `pcddj_engine/story-to-script/` | Engine 1. Converts a script or story into `narrative_plan.json` and `draft_timeline.json`. |
| `asset_engine/` | Engine 2. Converts draft descriptors into scaffold folders, resolved audio assets, timing, `final_timeline.json`, and `asset_manifest.json`. |
| `audio_engine/` | Engine 3. Renders `final_timeline.json` into a mixed and mastered WAV. |
| `narration_tts/` | Audiobook-oriented narration and credits utilities. It is more relevant to the audiobook path than the script-first drama path. |
| `api/` | FastAPI backend for project state, script preview, asset upload, stage jobs, status, and output serving. |
| `delivery_presets/` | Mix and export presets such as `audio_drama_default.json`. |
| `doc/` | Existing runbooks, specs, architecture notes, and pipeline status documents. |
| `workspace/projects/` | Per-project scripts, metadata, assets, intermediate files, manifests, and rendered outputs. |

## Core Concepts

### Project

A project is a folder under:

```text
workspace/projects/<project_id>/
```

A typical audio drama project contains:

```text
workspace/projects/<project_id>/
  book_metadata.json
  gita.json
  project_context.json
  chapters/
    <chapter_slug>.fountain
  assets/
    REQUIREMENTS.md
    voice/
    music/
    ambience/
    sfx/
  output/
    narrative_plan.json
    draft_timeline.json
    script_warnings.json
    audio_director.json
    final_timeline.json
    asset_manifest.json
    generated/
      <chapter_slug>.wav
```

`book_metadata.json` is shared with the broader book/audiobook tooling. For audio drama it usually includes:

```json
{
  "book_title": "Trail of bells",
  "project_id": "Trail_of_bells",
  "writer_name": "Om Jha",
  "project_type": "audio_drama",
  "narration_only": false,
  "delivery_profile": "audio_drama_default",
  "chapters": [
    {
      "title": "The Trail",
      "slug": "The_Trail",
      "file": "chapters/The_Trail.fountain"
    }
  ],
  "active_chapter_slug": "The_Trail"
}
```

### Chapter

For the drama-first workflow, each chapter is a `.fountain` script in `chapters/`. The active chapter is selected in metadata and can be changed through `drama_cli.py`.

### Draft Timeline

`draft_timeline.json` is the handoff from Engine 1 to Engine 2. It contains structured audio intent, not final file paths. Examples of intent include:

- voice text to record
- character or narrator tracks
- scene mood
- ambience descriptors
- SFX hints
- energy level
- silence and pacing settings

### Final Timeline

`final_timeline.json` is the handoff from Engine 2 to Engine 3. It contains concrete file paths, scene starts, durations, offsets, clip timing, and resolved track data.

### Asset Manifest

`asset_manifest.json` records what Engine 2 resolved, what was missing, and how confident each match was. It is the audit trail for asset readiness and provenance.

## End-to-End Local Workflow

Run commands from the repository root, `c:\AS`.

### 1. Create an Audio Drama Project

Interactive project creation:

```powershell
python drama_cli.py init
```

Starter template:

```powershell
python drama_cli.py init --template
```

This creates the project folder, the first `.fountain` chapter, `assets/`, `output/`, `book_metadata.json`, and `gita.json`.

Chapter commands:

```powershell
python drama_cli.py add-chapter --project-id <project_id>
python drama_cli.py list-chapters --project-id <project_id>
python drama_cli.py set-chapter --project-id <project_id> --chapter <chapter_slug>
```

### 2. Author the Fountain Script

The script-first drama path expects `.fountain` files. Supported elements include:

- scene headings such as `INT. HOUSE - NIGHT`, `EXT. FOREST - DUSK`, `SCENE 1`, or forced headings with `.`
- character cues such as `EVA`, `EVA (V.O.)`, `CAPTAIN (O.S.)`, or forced cues with `@`
- dialogue blocks under character cues
- parentheticals such as `(whispering)`, `(shouting)`, `(urgently)`, `(calmly)`
- action lines used for SFX and ambience inference
- explicit `SFX:` and `AMBIENCE:` blocks
- notes and boneyards, which are stripped

The parser is deterministic. It does not require an LLM for the normal script-to-plan conversion.

Useful authoring guidance:

- Use explicit scene headings when location or time changes.
- Keep action paragraphs clear and sound-specific.
- Use concrete sound language such as `footsteps`, `bell rings`, `door slam`, `wind`, or `distant traffic`.
- Use `(V.O.)` for voice-over or inner voice.
- Prefer `SFX:` and `AMBIENCE:` when a sound must be represented explicitly.

### 3. Dry Parse the Script

Preview the parser output without creating timelines or scaffold folders:

```powershell
python drama_cli.py dry-run-parse --project-id <project_id>
python drama_cli.py dry-run-parse --project-id <project_id> --json
```

This calls the Fountain parser and plan mapper used by Engine 1. It is the safest way to validate headings, characters, speaker extraction, ambience hints, SFX hints, energy, and diagnostics before running Stage 1.

### 4. Run Stage 1

Stage 1 parses the selected chapter, creates the narrative plan, compiles the draft timeline, applies the delivery preset, and scaffolds asset folders.

```powershell
python drama_cli.py stage1 --project-id <project_id>
```

Optional LLM audio director enrichment:

```powershell
python drama_cli.py stage1 --project-id <project_id> --director
```

Optional continuity:

```powershell
python drama_cli.py stage1 --project-id <project_id> --use-gita
python drama_cli.py stage1 --project-id <project_id> --update-gita
```

Stage 1 outputs:

| File | Purpose |
| --- | --- |
| `output/narrative_plan.json` | Scene-by-scene structured interpretation of the script. |
| `output/draft_timeline.json` | Descriptor-level timeline consumed by Engine 2. |
| `output/script_warnings.json` | Parser diagnostics: line, column, code, severity, and message. |
| `output/audio_director.json` | Optional LLM enrichment output when `--director` is used. |
| `assets/REQUIREMENTS.md` | Human-readable shopping list for required voice, music, ambience, and SFX. |
| `assets/**/SCRIPT.txt` | Recording instructions for voice clips. |
| `assets/**/DESCRIPTOR.txt` | Placement instructions for music, ambience, and SFX. |

### 5. Fill the Asset Folders

Stage 1 deliberately pauses after scaffolding. The system expects a human or external tool to provide actual audio files.

Place WAV files in the scaffolded folders:

```text
assets/voice/.../clip_*/
assets/music/.../
assets/ambience/.../
assets/sfx/.../
```

Voice folders contain `SCRIPT.txt` with the exact line to record. Non-voice folders contain `DESCRIPTOR.txt` describing the required sound.

For local predictability, use `.wav` files and descriptive filenames. The resolver primarily uses folder structure and descriptor/filename matching, so names like `forest_night_ambience.wav`, `bell_distant_sfx.wav`, or `tense_low_drone_music.wav` are easier to audit than generic names.

### 6. Resume Stage 2

Stage 2 checks readiness, resolves assets, computes timing, assembles the final timeline, and renders the WAV.

```powershell
python drama_cli.py resume --project-id <project_id>
```

Stage 2 outputs:

| File | Purpose |
| --- | --- |
| `output/final_timeline.json` | Resolved render timeline with file paths and timing. |
| `output/asset_manifest.json` | Resolution audit trail and confidence/missing information. |
| `output/generated/voice/*_silence.wav` | Silence placeholders when voice assets are missing. |
| `output/generated/<chapter_slug>.wav` | Final mixed audio drama WAV. |

### 7. One-Shot Run

`run` performs Stage 1 and then Stage 2:

```powershell
python drama_cli.py run --project-id <project_id>
```

In practice, the two-step `stage1` then `resume` flow is better for real productions because it gives you a pause to review requirements and add audio assets.

## What `run_pipeline.py` Does

`run_pipeline.py` is the central orchestrator. `drama_cli.py` resolves the project and chapter paths, then delegates to it.

For Stage 1, it:

1. Resolves canonical project paths under `workspace/projects/<project_id>/`.
2. Preflights the input script.
3. Runs Engine 1 through `pcddj_engine/story-to-script/cli.py process`.
4. Applies the selected delivery preset to `draft_timeline.json`.
5. Runs Engine 2 scaffold mode.
6. Writes `project_context.json`.
7. Prints a Stage 1 report and asset shopping list.

For Stage 2, it:

1. Verifies Stage 1 produced `output/draft_timeline.json`.
2. Re-applies the delivery preset.
3. Runs audio library and asset readiness preflights.
4. Runs Engine 2 resolve/run mode.
5. Computes the final WAV path under `output/generated/`.
6. Runs Engine 3 render.
7. Verifies manifest state, WAV header, and approximate output duration.

## Engine 1: Story-to-Script

Location:

```text
pcddj_engine/story-to-script/
```

Primary CLI entry:

```text
pcddj_engine/story-to-script/cli.py
```

Important modules:

| Module | Responsibility |
| --- | --- |
| `story_processing/fountain/parser.py` | Parses Fountain into an AST and diagnostics. |
| `story_processing/fountain/ast.py` | Defines script AST types such as scenes, dialogue blocks, action blocks, and diagnostics. |
| `story_processing/fountain/to_plan.py` | Converts the script AST into the Narrative Plan shape. |
| `story_processing/fountain/sound_hints.py` | Infers SFX labels and ambience tokens from action text. |
| `story_processing/fountain/audio_director.py` | Optional LLM-based scene enrichment. |
| `story_processing/fountain/gita.py` | Cross-episode continuity handling. |
| `dsl/compiler.py` | Compiles Narrative Plan into `draft_timeline.json`. |
| `dsl/builders/` | Builds tracks, clips, settings, and scene rules. |
| `story_processing/pipeline.py` | Prose `.txt` path with NLP and optional LLM classification. |

### Fountain Drama Path

When the input file is `.fountain` and `project_type` is `audio_drama`, Engine 1 follows the deterministic script path:

```text
script text
  -> parse_fountain()
  -> ScriptAST + diagnostics
  -> process_script_bundle()
  -> narrative plan
  -> optional Gita apply/update
  -> optional Audio Director enrichment
  -> compile_timeline_json()
  -> draft_timeline.json
```

The main outputs are `narrative_plan.json`, `draft_timeline.json`, and `script_warnings.json`.

### Prose Story Path

If the input is not a `.fountain` drama script, Engine 1 can process raw `.txt` story input through the heavier prose pipeline:

```text
raw story text
  -> preprocessing
  -> NLP
  -> scene segmentation
  -> dialogue extraction
  -> speaker attribution
  -> signal extraction
  -> optional LLM classification
  -> heuristic fallback
  -> narrative plan
  -> draft timeline
```

This path is useful for audiobook or story-to-audio experiments, but the current drama workflow should prefer `.fountain` because it gives the writer explicit control.

## Engine 2: Asset Engine

Location:

```text
asset_engine/
```

CLI module:

```text
asset_engine.cli
```

Engine 2 bridges abstract intent and concrete audio files. It reads `draft_timeline.json`, extracts requirements, creates folders, resolves assets from the library, computes timing, and writes the final render timeline.

Important modules:

| Module | Responsibility |
| --- | --- |
| `requirements/extractor.py` | Flattens draft clips into voice, music, ambience, and SFX requirements. |
| `scaffold/builder.py` | Creates asset folders and writes `SCRIPT.txt` or `DESCRIPTOR.txt`. |
| `pipeline/run_asset_pipeline.py` | Coordinates scaffold, resolve, timing, manifest, and final timeline output. |
| `resolvers/library_resolver.py` | Resolves requirements from the local asset library. |
| `resolvers/catalog.py` | Catalog and matching support. |
| `timing/compute_timing.py` | Computes scene and clip timing. |
| `timing/scene_timing.py` | Scene-level timing helpers. |
| `assembly/timeline_assembler.py` | Builds `final_timeline.json`. |
| `assembly/manifest_builder.py` | Builds `asset_manifest.json`. |
| `contracts/` | Pydantic contracts for draft timelines, requirements, and manifests. |

Manual Engine 2 commands:

```powershell
python -m asset_engine.cli scaffold --draft <draft_timeline.json> --library <assets_dir>
python -m asset_engine.cli status --draft <draft_timeline.json> --library <assets_dir>
python -m asset_engine.cli run --draft <draft_timeline.json> --library <assets_dir> --out <output_dir>
```

`scaffold` is idempotent and safe to re-run. Missing voice clips can be represented as generated silence placeholders in `output/generated/voice/`. Missing music, ambience, or SFX are reported in the manifest and status output.

## Engine 3: Audio Engine

Location:

```text
audio_engine/
```

Render entry:

```powershell
python audio_engine/main.py <final_timeline.json> <output.wav>
```

The orchestrator runs it with `cwd` set to `audio_engine/` and passes the project `final_timeline.json` plus the target WAV path.

Important modules:

| Module | Responsibility |
| --- | --- |
| `audio_engine/main.py` | CLI entry that invokes the renderer. |
| `audio_engine/renderer/timeline_renderer.py` | Main render orchestrator. |
| `audio_engine/renderer/clip_processor.py` | Per-clip loading and DSP. |
| `audio_engine/renderer/track_mixer.py` | Track-level mixing. |
| `audio_engine/renderer/master_processor.py` | Master processing. |
| `audio_engine/scene_preprocessor.py` | Expands scene blocks into renderable track clips. |
| `audio_engine/validation.py` | Timeline validation. |
| `audio_engine/autofix.py` | Overlap correction. |
| `audio_engine/dsp/` | EQ, fades, ducking, compression, loudness, normalization, balance, SFX processing. |
| `audio_engine/streaming/` | Chunked rendering for longer productions. |

Render stages:

1. Load `final_timeline.json`.
2. Preprocess scenes.
3. Auto-fix overlaps.
4. Validate timeline structure and file references.
5. Build render config from timeline settings.
6. Process voice, music, ambience, and SFX clips.
7. Apply clip-level and track-level DSP.
8. Mix tracks into a master bus.
9. Apply loudness normalization and peak limiting.
10. Export WAV.

Audio engine features include:

- timeline-based deterministic rendering
- voice, music, ambience, and SFX tracks
- EQ presets
- fade curves
- dialogue compression
- voice-driven ducking
- LUFS normalization
- peak normalization/limiting
- role-based loudness balancing
- semantic SFX processing
- scene energy handling
- standard and streaming render modes

## Delivery Presets

Delivery presets live in `delivery_presets/`. For audio drama, the default is:

```text
delivery_presets/audio_drama_default.json
```

It currently sets:

```json
{
  "project": {
    "sample_rate": 48000,
    "bit_depth": 16
  },
  "settings": {
    "peak_target_dbfs": -1.0
  }
}
```

`run_pipeline.py` applies the preset to `draft_timeline.json` during Stage 1 and again before Stage 2. Project metadata can select the profile through `delivery_profile`.

## Gita Continuity

Gita is the project-level continuity file:

```text
workspace/projects/<project_id>/gita.json
```

It tracks cross-episode context such as characters, locations, motifs, and discoveries. It is optional in the Stage 1 parse, but `drama_cli.py init` creates it for audio drama projects.

Commands:

```powershell
python drama_cli.py gita-init --project-id <project_id>
python drama_cli.py gita-show --project-id <project_id>
python drama_cli.py gita-show --project-id <project_id> --json
python drama_cli.py gita-update --project-id <project_id>
```

Stage 1 flags:

```powershell
python drama_cli.py stage1 --project-id <project_id> --use-gita
python drama_cli.py stage1 --project-id <project_id> --update-gita
```

`--use-gita` applies existing continuity to the parsed narrative plan. `--update-gita` merges discoveries from the current chapter back into `gita.json`.

## Audio Director Enrichment

The Audio Director is optional LLM enrichment for `.fountain` drama scripts.

Enable it with:

```powershell
python drama_cli.py stage1 --project-id <project_id> --director
```

It uses the parsed AST and an LLM client to enrich the plan. If the enrichment fails, the pipeline falls back to deterministic parsing and records a warning. When enabled, it writes:

```text
output/audio_director.json
```

The deterministic parser remains the baseline behavior. This keeps the drama path usable without network access or an LLM key.

## API and UI Surface

The backend lives in:

```text
api/
```

It exposes FastAPI routes for project creation, script preview, stage jobs, asset upload, status, and output serving. It loads state from:

```text
workspace/api_state.json
```

Notable route:

```text
POST /api/projects/{project_id}/script/preview
```

For drama projects, this preview route calls the same Fountain parsing and plan preview path used by the local dry-parse workflow. It is side-effect free and does not run Stage 1 or scaffold assets.

Important implementation note: the API worker currently shells through `book_cli.py`, which is more audiobook-oriented. The most complete local script-first drama path is `drama_cli.py` plus `run_pipeline.py`. If the UI is used for drama jobs, verify that its stage behavior matches the drama CLI options you need, especially `--director`, `--use-gita`, and `--update-gita`.

The API allows CORS for a Vite-style frontend at:

```text
http://localhost:5173
```

The sibling workspace `c:\AS UI` appears to be the frontend side referenced by the backend/frontend integration docs.

## Relationship to the Audiobook Workflow

The repository supports both:

- audio drama: script-first `.fountain`, project type `audio_drama`, usually human or external voice/SFX/music asset placement
- audiobook: prose/chapter-oriented flow, narration-only options, optional TTS synthesis and credits utilities

`book_cli.py` is the broader book/audiobook CLI. It shares metadata concepts with drama projects but does not fully replace `drama_cli.py` for the deterministic Fountain workflow.

For drama projects, prefer:

```powershell
python drama_cli.py init
python drama_cli.py dry-run-parse --project-id <project_id>
python drama_cli.py stage1 --project-id <project_id>
python drama_cli.py resume --project-id <project_id>
```

## Generated Files and Their Meaning

| File | Created by | Meaning |
| --- | --- | --- |
| `chapters/<slug>.fountain` | `drama_cli.py init` or `add-chapter` | Author-controlled script input. |
| `book_metadata.json` | `drama_cli.py` | Project metadata, active chapter, delivery profile, project type. |
| `gita.json` | `drama_cli.py` / Gita commands | Optional continuity state. |
| `project_context.json` | `run_pipeline.py` | Resolved paths and project context for later stages. |
| `output/narrative_plan.json` | Engine 1 | Structured scene interpretation. |
| `output/draft_timeline.json` | Engine 1 + delivery preset merge | Descriptor-level audio blueprint. |
| `output/script_warnings.json` | Engine 1 | Parser diagnostics and warnings. |
| `output/audio_director.json` | Engine 1 optional director | LLM enrichment payload. |
| `assets/REQUIREMENTS.md` | Engine 2 scaffold | Human-readable asset shopping list. |
| `assets/**/SCRIPT.txt` | Engine 2 scaffold | Voice recording instructions. |
| `assets/**/DESCRIPTOR.txt` | Engine 2 scaffold | Non-voice asset instructions. |
| `output/final_timeline.json` | Engine 2 resolve | Concrete render timeline with files and timing. |
| `output/asset_manifest.json` | Engine 2 resolve | Resolved/missing asset audit. |
| `output/generated/voice/*_silence.wav` | Engine 2 resolve | Placeholder silence for missing voice clips. |
| `output/generated/<chapter>.wav` | Engine 3 | Final rendered mix. |

## Operational Checklist

Use this when running a production-like chapter.

1. Create or select the project.
2. Confirm `book_metadata.json` has `project_type: "audio_drama"` and the expected active chapter.
3. Author or edit `chapters/<slug>.fountain`.
4. Run `dry-run-parse`.
5. Review the dry-parse diagnostics and fix script issues that matter for the scene.
6. Run `stage1`.
7. Read `assets/REQUIREMENTS.md`.
8. Record or generate voice clips into `assets/voice/.../clip_*/`.
9. Add music, ambience, and SFX WAVs to the scaffolded folders.
10. Run asset status manually if needed.
11. Run `resume`.
12. Inspect `output/asset_manifest.json`.
13. Listen to `output/generated/<chapter>.wav`.
14. Iterate on script, asset naming, or audio files as needed.

## Common Troubleshooting

### The parser misses a scene

Use clearer Fountain headings such as `INT. LOCATION - TIME`, `EXT. LOCATION - TIME`, `SCENE 1`, or a forced heading with leading `.`.

### A character line is treated as action

Use uppercase character cues on their own line, or force the cue with `@CHARACTER`.

### The wrong ambience or SFX is inferred

Use an explicit `SFX:` or `AMBIENCE:` block. The heuristic parser is more reliable when sound intent is concrete.

### Stage 2 cannot resolve assets

Open `assets/REQUIREMENTS.md`, fill the exact scaffold folders, and inspect `output/asset_manifest.json`. Use WAV files and descriptive names.

### Voice is missing in the output

Check the relevant `assets/voice/.../clip_*/` folder. If no voice file was added, Engine 2 may use generated silence placeholders.

### Music, ambience, or SFX is absent

Check the corresponding scaffold folder and the manifest. Missing non-voice assets may be skipped with warnings depending on the resolver path.

### The final WAV path is unexpected

`run_pipeline.py` writes final renders under `output/generated/`. It uses the active chapter slug when metadata is available and falls back to `final.wav` otherwise.

### The API preview works but the full UI run behaves differently

The preview route uses the drama parser directly. The API worker uses `book_cli.py` for queued stage work, so compare its behavior with `drama_cli.py` when debugging UI-driven drama jobs.

## Current Strengths

- Clear three-engine separation with JSON contracts between stages.
- Deterministic Fountain parser for script-first audio drama.
- Side-effect-free dry parse and API preview.
- Project-scoped assets and outputs.
- Idempotent asset scaffolding.
- Human-readable asset requirements.
- Delivery preset merge before render.
- Optional Gita continuity.
- Optional Audio Director enrichment.
- Professional render features in the audio engine: EQ, ducking, compression, fades, LUFS, peak limiting, and streaming render support.

## Current Gaps and Caveats

- The most complete audio drama path is local CLI-driven. UI/API stage execution should be checked against `drama_cli.py` behavior for drama-specific flags.
- Voice generation is not automatically wired into the script-first drama path. Voice clips are expected to be recorded, generated externally, or otherwise placed into the scaffold folders.
- Asset quality depends heavily on folder placement and descriptive files/names.
- Existing docs mention older prose/story workflows. For drama, prioritize `.fountain`, `drama_cli.py`, and `doc/AUDIO_DRAMA_LOCAL_RUNBOOK.md`.
- `book_cli.py` and `drama_cli.py` share concepts but are not interchangeable for every drama feature.

## Quick Reference

```powershell
# Create project
python drama_cli.py init

# Create project from template
python drama_cli.py init --template

# Preview parser output
python drama_cli.py dry-run-parse --project-id <project_id>

# Run script parse, draft generation, delivery preset merge, and asset scaffold
python drama_cli.py stage1 --project-id <project_id>

# Run Stage 1 with optional LLM enrichment
python drama_cli.py stage1 --project-id <project_id> --director

# Run Stage 1 with continuity
python drama_cli.py stage1 --project-id <project_id> --use-gita --update-gita

# Resolve assets and render
python drama_cli.py resume --project-id <project_id>

# Stage 1 plus Stage 2
python drama_cli.py run --project-id <project_id>

# Manual Engine 2 status check
python -m asset_engine.cli status --draft workspace/projects/<project_id>/output/draft_timeline.json --library workspace/projects/<project_id>/assets

# Manual Engine 3 render
cd audio_engine
python audio_engine/main.py ..\workspace\projects\<project_id>\output\final_timeline.json ..\workspace\projects\<project_id>\output\generated\manual.wav
```

## Best Mental Model

Think of the system as a file-based production line.

Engine 1 is the script and story intelligence layer. It understands scenes, characters, dialogue, action, sound hints, energy, and delivery intent.

Engine 2 is the production logistics layer. It turns intent into a checklist, waits for assets, chooses files, computes timing, and writes the exact render plan.

Engine 3 is the mixer. It does not care how the story was written. It reads the final timeline, loads audio files, applies DSP, mixes tracks, masters the result, and writes the WAV.

`run_pipeline.py` is the stage manager between them, and `drama_cli.py` is the most convenient local interface for audio drama projects.
