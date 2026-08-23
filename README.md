# AudStories

AI-powered audio production platform. Turns story text into finished audio in two
modes — **audiobook** and **audio drama**.

The pipeline runs: story text → NLP/AI analysis → Fountain script → asset requirements
→ TTS synthesis → DSP/audio rendering → WAV output.

```
React SPA  →  FastAPI  →  subprocess CLIs  →  processing engines  →  WAV
```

---

> **🚧 This README is a placeholder.** It is written in full at Stage 4 of the release
> plan, with an architecture diagram, screenshots, a demo audio sample, and a verified
> quickstart. What follows is the minimum needed to orient someone reading the code today.

---

## Repository layout

| Path | Contents |
|---|---|
| `backend/api/` | FastAPI app — routes, auth, job worker, SQLite state store |
| `backend/asset_engine/` | Requirements extraction, asset resolution, pacing rules |
| `backend/audio_engine/` | DSP, timeline renderer, loudness |
| `backend/pcddj_engine/story-to-script/` | NLP pipeline, Fountain DSL, narrative plan |
| `backend/narration_tts/` | Gemini Flash TTS synthesis |
| `frontend/` | React + Vite single-page app |
| `docs/` | Engine and pipeline documentation |
| `examples/` | Sample Fountain scripts and an example asset library |

## Status

This repository is mid-migration from a local working tree. Known gaps, tracked and
being worked through in order:

- Setup is currently **Windows-only** (`setup.ps1`). Cross-platform support and a
  container image are planned.
- Running the pipeline currently requires **a Supabase project** and **a Gemini API
  key**. A no-account development mode is planned.
- Some test suites have known failures. See the notes in `CLAUDE.md`.

## Licence

Apache-2.0 — see [LICENSE](LICENSE).

Audio assets are licensed separately and individually; see [CREDITS.md](CREDITS.md).
That file is **incomplete** and must be finished before this repository is made public.
