# AudStories — Local Setup Guide

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| Python | 3.13+ | [python.org](https://python.org) |
| Node.js | 18+ | [nodejs.org](https://nodejs.org) |
| FFmpeg | any | `winget install Gyan.FFmpeg` |
| Git | any | [git-scm.com](https://git-scm.com) |

> **FFmpeg is required for audio rendering (Stage 2).** Without it, `pydub` will fail silently when trying to mix tracks. Install it and make sure `ffmpeg` is on your PATH before testing.

---

## Step 1 — Supabase project

1. Create a free project at [supabase.com](https://supabase.com).
2. Go to **SQL Editor** and run the contents of [`schema.sql`](schema.sql) — this creates the `projects` and `units` tables with Row-Level Security.
3. From **Project Settings → API**, note down:
   - Project URL
   - `anon public` key
   - JWT Secret (under JWT Settings)

---

## Step 2 — Gemini API key

Go to [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) and create an API key.

This is used for story NLP analysis (Stage 1) and TTS voice synthesis.

---

## Step 3 — Fill in environment files

**Backend** — copy and fill in `c:\AS\.env`:

```
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_ANON_KEY=...
SUPABASE_JWT_SECRET=...
GEMINI_API_KEY=...
```

**Frontend** — copy and fill in `c:\AS UI\audstories-ui\.env`:

```
VITE_SUPABASE_URL=https://xxxx.supabase.co
VITE_SUPABASE_ANON_KEY=...
VITE_API_BASE_URL=http://localhost:8000
```

The Supabase URL and anon key are the same values in both files.

---

## Step 4 — Run the setup script

From the repo root in PowerShell:

```powershell
.\setup.ps1
```

This will:
- Verify Python 3.13+ and FFmpeg are available
- Create a `.venv` at the repo root
- Install all four dependency groups (API, NLP, TTS, audio engine) into that one venv
- Editable-install the three in-repo engine packages (`audio_engine`, `asset_engine`, `story-to-script`) so they import as real packages — **required**, the Stage 2 audio render runs `audio_engine` as a subprocess and will fail without it
- Download the spaCy `en_core_web_lg` model (~560 MB, one-time)
- Copy `.env.example` to `.env` if not already present

> The script takes a few minutes on first run due to the spaCy model download and sentence-transformers.

---

## Step 5 — Start the backend

**Always activate the venv before starting the server.** The pipeline subprocesses inherit the active Python, so activating once is enough.

```powershell
# From c:\AS
.venv\Scripts\Activate.ps1
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

You should see:
```
INFO:     Application startup complete.
```

---

## Step 6 — Start the frontend

In a separate terminal (no venv needed here):

```powershell
cd "c:\AS UI\audstories-ui"
npm install        # first time only
npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

---

## Smoke test

1. Sign up for an account.
2. Create a new **Audio Drama** project.
3. Paste or upload a `.fountain` script. Two ready-made examples live in the repo root: [`missing.fountain`](missing.fountain) (single scene, two characters) and [`trailer.fountain`](trailer.fountain) (four scenes, multiple characters — exercises more of the pipeline).
4. Click **Run Stage 1** — wait for `awaiting_assets` status.
5. In the Voice panel, click **Generate All** to run TTS.
6. Once all voice clips are ready, click **Run Stage 2**.
7. When status shows `done`, open the Output page and play the rendered audio.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: story_processing` | Venv not activated | Run `.venv\Scripts\Activate.ps1` before `uvicorn` |
| `OSError: [Errno 2] ffmpeg not found` | FFmpeg missing or not on PATH | Install FFmpeg, restart terminal |
| `Can't find model 'en_core_web_lg'` | spaCy model not downloaded | Run `.venv\Scripts\python -m spacy download en_core_web_lg` |
| `ModuleNotFoundError: No module named 'audio_engine'` during Stage 2 | Engine packages not editable-installed | Run `.venv\Scripts\python -m pip install -e audio_engine --no-deps` (or re-run `setup.ps1`) |
| `Gemini TTS quota/rate limit reached` | Free tier quota | Wait ~60s and retry, or use a billed API key |
| `401 Unauthorized` from backend | Stale or wrong JWT secret | Check `SUPABASE_JWT_SECRET` matches Supabase dashboard |
| Frontend shows blank page | `.env` not filled in | Verify `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` are set |
