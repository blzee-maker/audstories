# Documentation

Start with the [project README](../README.md) for what AudStories does and how the
pieces fit together, and [CONTRIBUTING.md](../CONTRIBUTING.md) before changing code.

## Getting things running

| Document | What it covers |
|---|---|
| [../SETUP.md](../SETUP.md) | Full install walkthrough for both platforms |
| [AUDIOBOOK_LOCAL_RUNBOOK.md](AUDIOBOOK_LOCAL_RUNBOOK.md) | Running an audiobook end to end locally, UI included |
| [AUDIO_DRAMA_LOCAL_RUNBOOK.md](AUDIO_DRAMA_LOCAL_RUNBOOK.md) | The same for audio drama, starting from a Fountain script |
| [TESTING.md](TESTING.md) | The six suites, what they need, and the conventions they enforce |

## How the pipeline works

| Document | What it covers |
|---|---|
| [WORKFLOW_GUIDE.md](WORKFLOW_GUIDE.md) | End-to-end tour of the pipeline. The best single overview |
| [AUDIOBOOK_PIPELINE.md](AUDIOBOOK_PIPELINE.md) | The narration-only path: text to chapter WAVs, credits, masters |
| [AUDIO_DRAMA_WORKFLOW.md](AUDIO_DRAMA_WORKFLOW.md) | The drama path: script parsing, asset prep, timing, mixing, delivery |
| [AUDIO_DRAMA_SCRIPT_SPEC.md](AUDIO_DRAMA_SCRIPT_SPEC.md) | The Fountain subset the parser accepts. Deterministic, no LLM |

## Engine references

| Document | What it covers |
|---|---|
| [STORY_TO_SCRIPT_ENGINE.md](STORY_TO_SCRIPT_ENGINE.md) | Engine 1 — NLP pipeline, data contracts, the DSL layer, runtime modes |
| [ASSET_ENGINE.md](ASSET_ENGINE.md) | Engine 2 — requirements extraction, resolution, timing, assembly |
| [ASSET_ENGINE_V1_DESIGN.md](ASSET_ENGINE_V1_DESIGN.md) | Why the asset engine is shaped the way it is. Rationale, not reference |

The audio engine's own documentation lives beside the code, in
[../backend/audio_engine/](../backend/audio_engine/).

## Design notes

[AUD_STORIES_SEMANTIC_AUDIO_NOTES.md](AUD_STORIES_SEMANTIC_AUDIO_NOTES.md) assesses
replacing filename-based asset matching with CLAP audio embeddings plus a Freesound
fallback.

**This is a proposal, not a description of what ships.** The `--use-clap` and
`--use-freesound` flags exist and default to off, and
`asset_engine/resolvers/clap_index.py` is a token-matching stand-in rather than a
real embedding model. Read it as a direction under consideration. It also refers to
a `DEPLOYMENT_REQUIREMENTS.md` that is not part of this repository.

## Assets

`images/` holds the README diagrams, `audio/` the render demo. Both are generated
from sources described in [../CREDITS.md](../CREDITS.md).
