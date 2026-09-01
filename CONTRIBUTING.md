# Contributing to AudStories

Thanks for taking a look. This file covers getting a working environment, the
conventions the codebase relies on, and the handful of traps that are easy to hit
and hard to diagnose.

## Getting set up

```bash
./setup.sh          # macOS / Linux
.\setup.ps1         # Windows
```

You need **Python 3.13+**, **Node 20.19+ or 22+**, and **FFmpeg on PATH**. The
script creates one virtualenv at the repo root for all four engines, installs both
spaCy models, and seeds `.env` files from the examples. [SETUP.md](SETUP.md) has the
long-form walkthrough; `docker compose up --build` works too.

Confirm it worked without needing any API key:

```bash
python examples/render_demo.py
```

That renders a 30-second WAV through the real audio engine. If it produces a file,
your install is good.

## Running the tests

Six suites, 437 tests, about a minute for the backend. Commands and per-suite
detail are in [docs/TESTING.md](docs/TESTING.md).

CI runs all of them on every push and pull request, plus the frontend lint and a
production build. **Please run at least the suites you touched before opening a
PR.**

## Traps worth knowing before you start

These are the things that have cost real time. Most are commented in the code too.

### `asset_engine/` and `audio_engine/` shadow the real packages

Those directories have no `__init__.py`, and the genuine packages live one level
down (`asset_engine/src/asset_engine/`, `audio_engine/audio_engine/`). From the
repo root, a bare `import asset_engine` resolves to the empty shadow directory.

Two separate mechanisms deal with this and **both are needed**:

- `backend/engine_paths.py` inserts the real source roots at the front of
  `sys.path`. Every entry point calls `ensure_engine_paths()`. This handles
  in-process imports.
- The three `pip install -e` calls in the setup scripts handle the *render
  subprocess* — Stage 2 runs `python audio_engine/main.py` as a subprocess, and its
  `from audio_engine...` import only resolves once the package is installed.
  Editable installs are required, not a convenience.

Removing the shim properly would mean renaming the colliding directories, which
touches every entry point, every `pyproject.toml` and the egg-info. Deferred on
purpose; see the comments in `backend/engine_paths.py`.

### Install order matters

`audio_engine/requirements.txt` pins `numpy==2.3.3` and `scipy==1.16.2`, which
*downgrades* the 2.4.x the NLP group pulls in. The downgrade is deliberate and
verified ABI-compatible across torch, spaCy and scikit-learn — **do not "fix" it**.
The audio engine is installed last so its pins win. If you change the order in one
of `setup.sh`, `setup.ps1`, `Dockerfile` or `.github/workflows/ci.yml`, change it in
all four.

### Imports inside handlers are intentional

`from story_processing...` and `from asset_engine...` appear inside functions
rather than at module top level. That is not laziness: an import sorter moving an
engine import above the `config` import that sets up `sys.path` would break
resolution. Deferred imports are immune to that, and Python caches modules after
first use, so the cost is one-time.

### `tests/` contains only tests

Pytest imports every module it collects, so a module doing work at import time runs
that work during collection. The `audio_engine` suite once held eight `test_*.py`
files with no test functions that rendered audio on import — collection alone took
over three minutes and wrote tens of megabytes of WAVs into the tree. Helper
scripts belong in `backend/audio_engine/scripts/`.

### Tests must leave the tree clean

`git status` is checked in CI after the test run. Point temp output at `tmp_path`,
respect `AS_WORKSPACE_DIR`, and pass `--projects-root` to the CLIs.

### Project slugs are lower-cased

`_sanitize_project_id` lower-cases so a project resolves identically on Windows and
Linux. It is duplicated in `book_cli.py`, `drama_cli.py` and `run_pipeline.py` —
all three must agree, or a project created by one is invisible to another.

### Narration is silent in drama mode

`build_tracks` and `build_voice_clips` default to `project_type="audio_drama"`,
where description becomes sound rather than narration. That is the product
behaviour, not a bug. A test asserting narrator output must pass
`project_type="audiobook"` explicitly.

## Things not to commit

- **`.env` files.** Both repo roots gitignore them. Add new settings to
  `.env.example` with a comment saying where the value comes from.
- **Audio.** `.gitignore` excludes `*.wav`, `*.mp3` and friends. Media you drop into
  `examples/asset-library/` stays local, which is what keeps this repository free of
  third-party licence obligations. If you have a genuine reason to commit an audio
  file, add a `.gitignore` negation *and* a row in [CREDITS.md](CREDITS.md) recording
  its origin and licence.
- **Build output.** `frontend/dist/`, `workspace/`, `output/`, venvs.

## Pull requests

- Branch off `main`.
- Keep the change focused; a PR that fixes a bug and reformats a file is two PRs.
- Explain *why* in the commit message, not just what. The reasoning is the part
  that is expensive to reconstruct later.
- CI must be green.

## Reporting bugs

Use the issue templates. For pipeline failures the most useful things are the stage
that failed, whether you were in audiobook or audio drama mode, and your OS and
Python version. Note that error messages surfaced by the API are deliberately
redacted of filesystem paths, so the full traceback from the server log is more
informative than the one the UI shows you.

## Licence

By contributing you agree that your contributions are licensed under
[Apache-2.0](LICENSE), the same as the project.
