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

## Quick start

You need a [Gemini API key](https://aistudio.google.com/app/apikey) for story analysis
and TTS. You do **not** need a Supabase account to try the pipeline.

### With Docker

```bash
cp backend/.env.example backend/.env
# set AS_DEV_NO_AUTH=1 and GEMINI_API_KEY in backend/.env
docker compose up --build
```

Then open **<http://localhost:8000/docs>** and drive the pipeline from there — create a
project, run Stage 1, generate voices, render Stage 2.

### Without Docker

```bash
./setup.sh          # macOS / Linux
.\setup.ps1         # Windows
```

Both need Python 3.13+, Node 18+, and FFmpeg on PATH. Full detail in [SETUP.md](SETUP.md).

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
- The **React frontend requires a Supabase project** — several pages read and write
  its `projects`/`units` tables directly.
- The **API does not**: set `AS_DEV_NO_AUTH=1` in `backend/.env` and you can drive the
  whole pipeline from <http://localhost:8000/docs> with no account and no sign-in.
  You still need a `GEMINI_API_KEY` for story analysis and TTS. See
  [SETUP.md](SETUP.md) for the shortcut path.

All five test suites pass — 391 tests, about a minute for the backend. See
[docs/TESTING.md](docs/TESTING.md) for how to run them and the conventions they
rely on.

## Licence

Apache-2.0 — see [LICENSE](LICENSE).

Audio assets are licensed separately and individually; see [CREDITS.md](CREDITS.md).
That file is **incomplete** and must be finished before this repository is made public.
