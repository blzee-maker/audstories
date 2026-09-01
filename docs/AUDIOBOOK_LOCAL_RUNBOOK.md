# AudioBook Local Runbook (UI + Backend)

## 1) Backend (`backend/`)

1. Install API dependencies (use the repo-root venv from SETUP.md):
   - `./setup.sh` (or `setup.ps1` on Windows) from the repo root installs everything
2. Create env file:
   - copy `.env.example` to `.env`
   - set `SUPABASE_URL` and `GEMINI_API_KEY` (no JWT secret needed on Supabase's
     JWT Signing Keys model — see [SETUP.md](../SETUP.md))
3. Start FastAPI bridge:
   - `uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload`

The bridge starts a local worker thread automatically and runs stage jobs with `book_cli.py`.

## 2) Frontend (`frontend/`)

1. Copy `.env.example` to `.env`
2. Set:
   - `VITE_SUPABASE_URL`
   - `VITE_SUPABASE_ANON_KEY`
   - `VITE_API_BASE_URL=http://localhost:8000`
3. Start UI:
   - `npm install`
   - `npm run dev`

## 3) End-to-end smoke test

1. Sign in.
2. Create project with `Audio Book`.
3. Use `AI Voice` or `Self Narrated`.
4. Paste story and click `Analyse Story`.
5. AI Voice:
   - Wait for output page.
6. Self Narrated:
   - Upload required clips in `Place Assets`
   - Click `Render Final Audio`
7. Verify waveform loads and download works from `Output` page.

