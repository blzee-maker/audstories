# Audio Drama Script Spec (Fountain Subset v2)

This document defines the script format accepted by the audio-drama parser.
The parser is deterministic and does not require an LLM.

Goal: convert a `.fountain` script into `narrative_plan.json`, then into
`draft_timeline.json` using the existing DSL compiler.

## Input format

Use plain UTF-8 text with a `.fountain` extension.

CLI helpers:

- `python drama_cli.py init` for interactive paste
- `python drama_cli.py init --template` for starter scaffold
- `python drama_cli.py add-chapter --project-id <id>` to add another episode script
- `python drama_cli.py list-chapters --project-id <id>` to view chapter roster
- `python drama_cli.py set-chapter --project-id <id> --chapter <slug>` to switch active chapter
- `python drama_cli.py dry-run-parse --project-id <id> [--chapter <slug>] [--json]`

## Supported elements

### 1) Scene headings and markers

Supported forms:

- `INT. EVA GRAFF'S QUARTERS`
- `EXT. CITY STREET - NIGHT`
- `INT./EXT. CAR - DAY`
- Custom ALL-CAPS slug on its own line (example: `NOWHERE/EVERYWHERE`)
- Forced heading with leading dot (example: `.INT FORCED HALLWAY`)
- Marker headings: `SCENE 1`, `SCENE ONE`, `ACT 1`, `TEASER`, `TRAILER BEGINS`

Each heading starts a new scene.

### 2) Character cues

Supported forms:

- `EVA`
- `EVA (V.O.)`
- `CAPTAIN REYES (O.S.)`
- `EVA (CONT'D)`
- Forced cue with leading `@` (example: `@EVA`)

Character cue lines are followed by one dialogue block.

### 3) Dialogue lines

Non-empty lines below a character cue are captured as dialogue until a blank
line is reached.

### 4) Parentheticals

Parentheticals between cue and dialogue are supported:

- `(whispering)`
- `(then)`

In v1 they are mapped to `delivery` on the resulting voice clip.

Normalization examples (deterministic):

- `(whispering)`, `(in a whisper)` -> `whispered`
- `(shouting)`, `(yelling)` -> `shouted`
- `(urgently)` -> `urgent`
- `(calmly)` -> `calm`
- `(then)` -> `pause_then`

### 5) Action lines, directives, and title cards

Prose lines outside character dialogue are treated as action.
Action lines are not spoken in v1 by default.

Action lines are used to infer:

- scene ambience hints (`underwater`, `street`, `rain`, etc.)
- SFX hints (`footsteps`, `door_slam`, `sonar_ping`, etc.)

Supported directive forms:

- Transition/directive lines (example: `CUT TO:`, `FADE TO SILENCE.`)
- Title cards (example: `TITLE CARD - AUDIO ONLY:` and centered `>TEXT<`)
- Sound blocks:
  - `SFX: Bell rings close.`
  - `AMBIENCE: Night forest.`
  - Multiline continuation under `SFX:` / `AMBIENCE:` is captured as one block

### 6) Notes and boneyards

- Notes `[[...]]` are removed.
- Boneyards `/* ... */` are removed.

### 7) Title page block

Initial top-of-file key/value lines like `Title:`, `Author:`, etc. are ignored
for audio planning in v1.

## Partially supported / deferred

These patterns are not fully timed in v2:

- Dual dialogue (`CHARACTER ^`) is preserved as normal dialogue and emits warning
- Sections (`#`, `##`) still warn and are ignored
- Synopses (`=`) still warn and are ignored

## Parser diagnostics output

When processing `.fountain` in drama mode, the output folder also includes:

- `script_warnings.json`

Structure:

- `summary.count`
- `summary.by_severity`
- `summary.by_code`
- `diagnostics[]` entries with:
  - `line`
  - `column`
  - `code`
  - `severity`
  - `message`

## Mapping to audio structures

Parser output is transformed into Narrative Plan scenes with these rules:

- Character dialogue -> `structure.dialogue_turns`
- Character names -> `structure.speakers`
- `(V.O.)` -> narration segment type `inner_thought` for that dialogue line
- Parenthetical -> `delivery` on the voice clip
- Action lines -> `structure.sfx_events` and `structure.ambience_cue` hints
- Action/directive blocks -> `structure.action_blocks` (`action|sfx|ambience|transition|title_card`)
- Scene heading text -> `structure.scene_title`

Then existing DSL compilation produces:

- character voice tracks
- music/ambience tracks
- optional sfx track
- per-scene clips in `draft_timeline.json`

Non-LLM scene intelligence also infers:

- `interpretation.energy_level` from punctuation, pacing, caps, and action density
- `interpretation.primary_emotion` from deterministic cue words + energy fallback

Optional LLM Audio Director enrichment:

- Enable with `--director` in Engine 1 CLI.
- Writes `audio_director.json` beside `narrative_plan.json` / `draft_timeline.json`.
- If the LLM fails, pipeline falls back to deterministic parsing and emits warning.

Cross-episode continuity with Gita:

- Project-level continuity file: `workspace/projects/<project_id>/gita.json`
- CLI:
  - `python drama_cli.py gita-init --project-id <project_id>`
  - `python drama_cli.py gita-show --project-id <project_id> [--json]`
  - `python drama_cli.py gita-update --project-id <project_id> [--chapter <slug>]`
- Stage 1:
  - `--use-gita` applies continuity to parsed output before timeline compilation
  - `--update-gita` merges current chapter discoveries (speakers/locations/SFX motifs) into Gita

## Authoring guidance

- Keep one clear action paragraph between dialogue blocks.
- Use explicit scene headings when location/time changes.
- Use `(V.O.)` for inner voice/voice-over.
- Prefer concrete sound words in action lines:
  - good: `footsteps`, `sonar ping`, `distant traffic`
  - weak: `it felt noisy`

## Example excerpt

```text
SCENE ONE
NOWHERE/EVERYWHERE
The sounds of an underwater world. Rushing currents. Sonar pings.

EVA (V.O.)
They say that in the dark, the eyes begin to see.

INT. EVA GRAFF'S QUARTERS
EVA
Jesus...
```

This yields two scenes, EVA voice clips, underwater ambience hints, and
sonar-related SFX hints.
