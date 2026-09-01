# AudStories — Local Setup Guide

## Prerequisites

> Using Docker instead? None of these are needed — skip to **Shortcut — Docker** below.

| Tool | Version | Windows | macOS | Linux |
|---|---|---|---|---|
| Python | 3.13+ | [python.org](https://python.org) | `brew install python@3.13` | your package manager |
| Node.js | 18+ | [nodejs.org](https://nodejs.org) | `brew install node` | your package manager |
| FFmpeg | any | `winget install Gyan.FFmpeg` | `brew install ffmpeg` | `sudo apt install ffmpeg` |
| Git | any | [git-scm.com](https://git-scm.com) | `brew install git` | your package manager |

> **FFmpeg is required for audio rendering (Stage 2).** Without it, `pydub` will fail silently when trying to mix tracks. Install it and make sure `ffmpeg` is on your PATH before testing.

---

## Shortcut — Docker

If you have Docker, this is the least error-prone path. It needs no Python, no Node,
no FFmpeg install, and sidesteps the editable-install requirement described below.

```bash
cp backend/.env.example backend/.env
# set AS_DEV_NO_AUTH=1 and GEMINI_API_KEY in backend/.env
docker compose up --build
```

Open <http://localhost:8000/docs>. Rendered audio and the job database live in a named
volume, so they survive `docker compose down`.

The web UI is behind a profile because it needs Supabase (see the next section):

```bash
docker compose --profile ui up --build
```

> First build downloads PyTorch and a 560 MB spaCy model, so expect it to take a while.
> Later builds reuse those layers unless a `requirements.txt` changes.

---

## Shortcut — try the pipeline without a Supabase account

Steps 1 and 3 exist to set up authentication. If you only want to see the pipeline
work, you can skip them:

1. Run `setup.ps1` (Step 4).
2. Put `AS_DEV_NO_AUTH=1` and your `GEMINI_API_KEY` in `backend/.env`.
3. Start the backend (Step 5) and open **<http://localhost:8000/docs>**.

That gives you the full API — create a project, run Stage 1, generate voices, render
Stage 2 — with no account and no sign-in. The API uses Supabase only for auth;
projects and jobs live in a local SQLite database.

**The React frontend is not covered by this.** Several of its pages read and write
the Supabase `projects`/`units` tables directly, so the UI still needs a real
Supabase project. Use `/docs` or the CLIs in `backend/` for the no-account path.

`AS_DEV_NO_AUTH` disables authentication completely. The server refuses to start
with it set if `CORS_ORIGINS` names any non-local origin, but never enable it on a
machine reachable from a network you do not control.

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

**Backend** — copy and fill in `backend/.env`:

```
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_ANON_KEY=sb_publishable_...
GEMINI_API_KEY=...
```

> **No JWT secret required.** On Supabase's current *JWT Signing Keys* model, user
> tokens are signed with an asymmetric key and the backend verifies them against
> your project's **public** JWKS endpoint, derived from `SUPABASE_URL`. Nothing
> secret to Supabase needs to live in `backend/.env`.
>
> If your project is still on the older shared secret, tokens arrive signed with
> HS256 and you also need `SUPABASE_JWT_SECRET=...` (Dashboard → JWT Keys →
> Legacy JWT Secret). Both paths work.

**Frontend** — copy and fill in `frontend/.env`:

```
VITE_SUPABASE_URL=https://xxxx.supabase.co
VITE_SUPABASE_ANON_KEY=sb_publishable_...
VITE_API_BASE_URL=http://localhost:8000
```

The Supabase URL and publishable key are the same values in both files. The
publishable key is public by design — it ships in the browser bundle, and the
row-level security policies in [`schema.sql`](schema.sql) are what actually
protect your data. Legacy `anon` keys still work in both places.

---

## Step 4 — Run the setup script

macOS / Linux:

```bash
./setup.sh
```

Windows, from the repo root in PowerShell:

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

Activate the venv, then start the server **from `backend/`** — `api.main` is only importable from there.

```powershell
# From the repo root
.venv\Scripts\Activate.ps1
cd backend
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
cd frontend
npm install        # first time only
npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

---

## Smoke test

### Fastest check — no keys, no accounts, no UI

```bash
python examples/render_demo.py
```

Renders a 30-second WAV into `examples/output/` using the audio fixture in the repo.
If this works, your Python environment, the editable engine installs, and FFmpeg are
all correct — which is most of what can go wrong during setup.

### Full pipeline

1. Sign up for an account.
2. Create a new **Audio Drama** project.
3. Paste or upload a `.fountain` script. Two ready-made examples live in [`examples/`](examples/): [`missing.fountain`](examples/missing.fountain) (single scene, two characters) and [`trailer.fountain`](examples/trailer.fountain) (four scenes, multiple characters — exercises more of the pipeline).
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
| `401 Unauthorized` from backend | Backend cannot verify the token | On JWT Signing Keys: check `SUPABASE_URL` is correct and reachable — it derives the JWKS URL. On the legacy shared secret: check `SUPABASE_JWT_SECRET` matches the dashboard |
| `401` mentioning `SUPABASE_JWT_SECRET is not set` | Project sends legacy HS256 tokens but no secret is configured | Either set `SUPABASE_JWT_SECRET`, or migrate the project to JWT Signing Keys |
| Frontend shows blank page | `.env` not filled in | Verify `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` are set |
