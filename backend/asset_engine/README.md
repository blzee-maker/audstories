# Asset Engine

**Full documentation:** [doc/ASSET_ENGINE.md](../doc/ASSET_ENGINE.md) (architecture, contracts, CLI, modules). Design history and roadmap: [ASSET_ENGINE_DESIGN.md](ASSET_ENGINE_DESIGN.md).

`asset_engine` bridges:

- `story-to-script` draft output (`draft_timeline.json`)
- `audio_engine` final input (`final_timeline.json`)

## What it does

1. Extracts asset requirements from draft descriptors (`tts_text`, `mood`, `atmosphere`, `sfx_hint`).
2. Builds scaffold folders for required assets (voice/music/ambience/sfx).
3. Resolves assets from those folders (library-first, deterministic).
4. Computes timing and duration (`scene.start`, `scene.duration`, clip `offset`).
5. Assembles and validates `final_timeline.json`.
6. Writes `asset_manifest.json` for traceability.

## Library-First CLI Workflow

```bash
# 1) Generate required folders and requirement docs
asset-engine scaffold --draft draft_timeline.json --library ./assets
```

```bash
# 2) Check readiness (what is missing / what is resolved)
asset-engine status --draft draft_timeline.json --library ./assets
```

```bash
# 3) Dry-run resolve (no outputs written)
asset-engine resolve --draft draft_timeline.json --library ./assets --out ./out --dry-run
```

```bash
# 4) Resolve and write outputs
asset-engine resolve --draft draft_timeline.json --library ./assets --out ./out
```

```bash
# 5) One-shot convenience command:
# scaffold (idempotent) -> resolve -> status
asset-engine run --draft draft_timeline.json --library ./assets --out ./out
```

## Behavior Notes

- `scaffold` is idempotent and safe to re-run.
- Missing voice assets are handled with silence placeholders.
- Missing music/ambience/sfx are skipped with warnings.
- `run` always prints status:
  - if assets are missing, exits non-zero and prints:
    `Assets missing. Fill folders and run again.`
  - if complete, writes outputs and prints:
    `Render ready.`

## Outputs

- `out/final_timeline.json`
- `out/asset_manifest.json`
- `out/generated/voice/*_silence.wav` (for missing voice placeholders)
