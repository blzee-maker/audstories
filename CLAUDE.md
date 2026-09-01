# AudStories — guide for AI coding agents

Read [CONTRIBUTING.md](CONTRIBUTING.md) too; it carries the reasoning behind
everything below. This file is the short version, plus the things that are easy to
get wrong without noticing.

## What this is

Story text becomes finished audio. Two modes: **audiobook** (a narrator reads
everything) and **audio drama** (characters speak, description becomes sound).

The pipeline runs in two stages with a deliberate pause between them. Stage 1
analyses the story and emits asset requirements; the user supplies the audio;
Stage 2 resolves it into a timeline and renders a mixed, loudness-normalised WAV.

## Layout

```
backend/api/                          FastAPI. main.py is a small app factory;
                                      routes/ splits handlers by concern;
                                      worker.py is a daemon-thread job queue;
                                      state_store.py is SQLite (WAL).
backend/pcddj_engine/story-to-script/ Engine 1 — spaCy + Gemini, Fountain, plan
backend/asset_engine/src/             Engine 2 — requirements, resolution, timing
backend/narration_tts/                Gemini TTS synthesis
backend/audio_engine/audio_engine/    DSP, timeline renderer, loudness
frontend/                             React 19 + Vite 8 + Tailwind 4
```

## Commands

```bash
./setup.sh                              # or .\setup.ps1 — one venv at the repo root
python examples/render_demo.py          # key-free end-to-end check

cd backend && uvicorn api.main:app --reload
python book_cli.py  --projects-root workspace stage1 --project-id <id>
python drama_cli.py --projects-root workspace --project-id <id>
```

Tests: six suites, commands in [docs/TESTING.md](docs/TESTING.md). CI runs them all.

## Traps

**`asset_engine/` and `audio_engine/` shadow the real packages.** Those directories
have no `__init__.py`; the genuine packages are one level down. Two mechanisms
handle it and both are load-bearing: `backend/engine_paths.py` for in-process
imports, and the three `pip install -e` calls for the Stage 2 render subprocess.
Do not "simplify" either away.

**Install order is deliberate.** `audio_engine/requirements.txt` pins
`numpy==2.3.3` / `scipy==1.16.2`, downgrading what the NLP group pulls in. It is
verified ABI-compatible. The audio engine installs **last**. The order appears in
`setup.sh`, `setup.ps1`, `Dockerfile` and `.github/workflows/ci.yml` — change one,
change all four.

**Engine imports inside handlers are intentional.** Hoisting them to module top
level lets an import sorter move them above the `config` import that sets up
`sys.path`. Leave them where they are.

**Both spaCy models are needed for tests.** The fixtures load `en_core_web_sm`;
`test_cli_smoke.py` shells out to the CLI, which defaults to `en_core_web_lg`.

**`tests/` holds only tests.** Pytest imports what it collects, so a module doing
work at import time runs it during collection. Helper scripts go in `scripts/`.

**Tests must leave the tree clean.** CI asserts `git status --porcelain` is empty
after the run. Use `tmp_path`, respect `AS_WORKSPACE_DIR`, pass `--projects-root`.

**Slugs are lower-cased,** and `_sanitize_project_id` is duplicated in
`book_cli.py`, `drama_cli.py` and `run_pipeline.py`. All three must agree.

**Silent narration in drama mode is correct.** `build_tracks` and
`build_voice_clips` default to `project_type="audio_drama"`. Tests wanting narrator
output must pass `project_type="audiobook"`.

## Never commit

`.env` files, audio (`.gitignore` excludes it — a deliberate commit needs a
negation *and* a [CREDITS.md](CREDITS.md) row), or build output.

## Known limits

- The React frontend needs a real Supabase project: five pages call
  `supabase.from(...)` directly. `AS_DEV_NO_AUTH=1` unlocks the **API** only.
- The job queue is in-process. It survives restarts but does not distribute.
- `python-jose` is unmaintained; `PyJWT` is the successor.

## Auth

`api/auth.py` verifies Supabase tokens two ways, chosen by the token's `alg`:

- **ES256/RS256** — the current *JWT Signing Keys* model. Verified against the
  project's public JWKS (derived from `SUPABASE_URL`), cached 5 minutes. **No
  secret is configured for this path**, which is the point of it.
- **HS256** — the legacy shared secret, needs `SUPABASE_JWT_SECRET`. Kept so
  older projects still work; leave the variable blank otherwise.

The permitted algorithm comes from `ASYMMETRIC_ALGORITHMS`, never from the
token's own header — echoing the header back is the algorithm-confusion vector.
`test_auth_jwks.py` asserts that with forged tokens.
