# Audio Drama Local Runbook (Script-First to Engine 2)

## 1) Create a drama project

From repo root (`c:\AS`):

- Interactive script paste:
  - `python drama_cli.py init`
- Starter template scaffold:
  - `python drama_cli.py init --template`

This creates:

- `workspace/projects/<project_id>/chapters/<chapter_slug>.fountain`
- `workspace/projects/<project_id>/assets/`
- `workspace/projects/<project_id>/output/`

Chapter ergonomics:

- Add chapter: `python drama_cli.py add-chapter --project-id <project_id>`
- List chapters: `python drama_cli.py list-chapters --project-id <project_id>`
- Set active chapter: `python drama_cli.py set-chapter --project-id <project_id> --chapter <slug>`

Cross-episode continuity (Gita):

- Initialize: `python drama_cli.py gita-init --project-id <project_id>`
- Show summary: `python drama_cli.py gita-show --project-id <project_id>`
- Show JSON: `python drama_cli.py gita-show --project-id <project_id> --json`
- Update from chapter parse: `python drama_cli.py gita-update --project-id <project_id> [--chapter <slug>]`

Preview parser + heuristics (no Stage 1 side effects):

- Human summary: `python drama_cli.py dry-run-parse --project-id <project_id>`
- JSON preview: `python drama_cli.py dry-run-parse --project-id <project_id> --json`

## 2) Run Stage 1 (script parse + draft generation + scaffold)

- `python drama_cli.py stage1 --project-id <project_id>`
- Optional director enrichment: `python drama_cli.py stage1 --project-id <project_id> --director`
- Optional continuity apply: `python drama_cli.py stage1 --project-id <project_id> --use-gita`
- Optional continuity update: `python drama_cli.py stage1 --project-id <project_id> --update-gita`

Outputs under project output folder:

- `narrative_plan.json`
- `draft_timeline.json`
- `script_warnings.json`
- `audio_director.json` (only when `--director` is enabled)
- `gita.json` (project continuity; created at project root)

## 3) Inspect script warnings

Open:

- `workspace/projects/<project_id>/output/script_warnings.json`

It contains:

- `summary.count`
- `summary.by_severity`
- `summary.by_code`
- `diagnostics[]` with `line`, `column`, `code`, `severity`, `message`

API preview workflow (side-effect free):

- `POST /api/projects/{id}/script/preview`
- Returns parse diagnostics + scene preview (speakers, SFX, ambience, mood/energy)
- Does not run Stage 1 or scaffold assets

## 4) Asset Engine workflow (Engine 2)

### 4.1 Scaffold (already run by stage1)

Manual command (if needed):

- `python -m asset_engine.cli scaffold --draft <draft_timeline.json> --library <assets_dir>`

### 4.2 Status

- `python -m asset_engine.cli status --draft <draft_timeline.json> --library <assets_dir>`

### 4.3 Resolve

- `python -m asset_engine.cli run --draft <draft_timeline.json> --library <assets_dir> --out <output_dir>`

Expected Engine 2 outputs:

- `final_timeline.json`
- `asset_manifest.json`

## 5) Asset placement guidance

The scaffolded folders are the source of truth. Place WAV files directly in:

- `assets/voice/.../clip_*/` for dialogue clips
- `assets/music/.../` for scene music
- `assets/ambience/.../` for environment beds
- `assets/sfx/.../` for effects

Tips:

- Use WAV (`.wav`) files for predictable local behavior.
- Keep filenames descriptive to help deterministic resolver matching.
- If status shows missing items, fill only those folders and run status again.

### 4.3.1 Generate character dialogues with Gemini Flash TTS (optional)

Use this between Stage 1 and Stage 2 to fill voice clips automatically per character. Each character is processed sequentially in its own package to stay under Gemini Flash short-window quotas.

Prerequisites:

- `GEMINI_API_KEY` set (same key Stage 1 uses).
- Per-character voice assignments in `gita.json` (`characters.*.tts_voice`). Speakers without a `tts_voice` use `--default-voice` (default `Charon`).

Inspect resolved speaker -> voice mapping (no TTS calls):

- `python drama_cli.py voice-map --project-id <project_id>`
- JSON variant: `python drama_cli.py voice-map --project-id <project_id> --json`

Generate clips for all characters (one character at a time):

- `python drama_cli.py tts-generate --project-id <project_id>`

Generate one character only:

- `python drama_cli.py tts-generate --project-id <project_id> --character ARNAV`

Common flags:

- `--dry-run` -> print the per-character plan without calling the API.
- `--regenerate` -> overwrite existing WAVs (manual recordings still win unless this is set).
- `--default-voice <name>` -> fallback Gemini voice (default `Charon`).
- `--pause-between-clips 1.5` -> seconds between clips inside a character package.
- `--pause-between-characters 5.0` -> seconds between character packages.
- `--max-clips-per-minute 10` -> soft per-minute cap inside a character package (0 disables).
- `--json` -> machine-readable run summary.

Outputs:

- WAVs are written into the existing scaffold folders: `assets/voice/.../clip_*/narration_tts.wav`.
- A sidecar `tts_meta.json` records voice, model, temperature, speaker, and timestamp for each clip.
- A run summary is written to `output/tts_summary.json`.

Manual override:

- If a folder already contains any audio file (any name), `tts-generate` skips that clip. To force re-synthesis pass `--regenerate`.

### 4.3.2 Director-style prompts (in-character delivery)

`tts-generate` wraps each line in a structured Gemini prompt by default so dialogue suits the scene. The prompt has up to five blocks:

- `# Audio Profile` -> from `characters.<key>.audio_profile` (or fallback to `voice_treatment`).
- `# Director's note` -> built from `characters.<key>.style`, `pace`, `accent`, plus the per-line `delivery_hint` (the Fountain parenthetical such as `(whispering)`).
- `## Scene:` -> auto-built from `narrative_plan.json` (scene title + ambience + first action notes).
- `## Sample Context:` -> from `gita.audio.sample_context` if set, otherwise auto-built from the scene interpretation (style/energy/intensity/music strategy). Override per run with `--sample-context "..."`.
- `## Transcript:` -> the line, prefixed with a short `[tag]` derived from the delivery hint (e.g. `[whisper] ...`, `[to_his_friends_grinning] ...`).

Per-character fields you can fill in `gita.json`:

```json
{
  "characters": {
    "arnav": {
      "name": "ARNAV",
      "tts_voice": "Charon",
      "audio_profile": "Confident young pilgrim, warm baritone with a hint of mischief.",
      "style": "Conversational",
      "pace": "Brisk",
      "accent": "Indian English",
      "default_delivery": ""
    }
  },
  "audio": {
    "sample_context": "Audio drama; cinematic, atmospheric pacing with naturalistic dialogue."
  }
}
```

Preview the exact prompt that will be sent for one speaker (no API calls):

- `python drama_cli.py voice-map --project-id <project_id> --show-prompt ARNAV`

Prompt-related flags on `tts-generate`:

- `--narrative-plan <path>` -> override the auto-detected `output/narrative_plan.json`.
- `--sample-context "..."` -> override the Sample Context block for this run.
- `--no-prompt` -> skip the Director's prompt and send raw dialogue text only.

The `tts_meta.json` sidecar next to each clip now also records the line text, the delivery hint that was applied, and the full prompt that was sent for traceability.

### 4.4 v1 advanced resolver flags (optional)

Use these when moving beyond folder-only matching:

- --require-voice -> fail Stage 2 when any voice clip is unresolved.
- --audio-library <path> -> shared library root for catalog/CLAP lookup.
- --music-catalog <path> -> tag-based music matching (music_catalog.json).
- --use-clap -> enable optional CLAP-style index lookup for SFX/ambience.
- --use-freesound -> enable optional Freesound fallback for unresolved SFX/ambience.
- --score-threshold 0.45 -> minimum match confidence for catalog/index.

Example:

- python drama_cli.py resume --project-id <project_id> --require-voice --audio-library <audio_library_root> --music-catalog <audio_library_root>/music_catalog.json --use-clap

Extra Engine 2 output:

- oice_status.json (resolved/placeholder/missing voice clips summary)
