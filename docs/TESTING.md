# Testing

All five suites pass. A full backend run takes about a minute.

| Suite | Location | Tests | Runtime |
|---|---|---|---|
| `asset_engine` | `backend/asset_engine` | 54 | ~1.4s |
| `api` | `backend` (run `pytest api/`) | 2 | ~0.8s |
| `audio_engine` | `backend/audio_engine` | 15 | ~3.7s |
| `story-to-script` | `backend/pcddj_engine/story-to-script` | 309 | ~45s |
| frontend | `frontend` (`npm test`) | 11 | ~27s |

## Running them

```bash
# from the repo root, with the venv active
cd backend/asset_engine                  && pytest
cd backend                               && pytest api/
cd backend/audio_engine                  && pytest
cd backend/pcddj_engine/story-to-script  && pytest

cd frontend && npm test
```

## Prerequisites

- **Both spaCy models.** The runtime pipeline loads `en_core_web_lg`; the
  story-to-script test fixture loads `en_core_web_sm`. `setup.ps1` installs both.
  Missing the small model produces 27 errors of the form
  `OSError [E050] Can't find model 'en_core_web_sm'`.
- **FFmpeg on PATH**, for anything that touches `pydub`.
- No API keys are needed. Nothing in the suites calls Gemini.

## Conventions worth knowing

**`tests/` contains only tests.** Pytest imports every module it collects, so a
module that does work at import time runs that work during collection. The
`audio_engine` suite previously held eight `test_*.py` files with no test
functions that rendered audio on import — collection alone took 3m10s and wrote
tens of megabytes of WAVs into the working tree. Those now live in
`backend/audio_engine/scripts/` (see the README there). Keep it that way: if a
file has no test functions, it does not belong in `tests/`.

**Tests must not touch the real workspace.** `api/conftest.py` points
`AS_WORKSPACE_DIR` at a temp directory, and the CLIs honour `--projects-root`.
Both matter: `cmd_init` used to ignore `--projects-root` and write to
`workspace/projects` regardless, so the CLI tests created real projects and then
tripped over them on later runs. After any test run, `git status` should be
clean.

**Narrator behaviour is the audiobook contract.** `build_tracks` and
`build_voice_clips` default to `project_type="audio_drama"`, where narration is
silent and voices are per character. A test asserting narrator output must pass
`project_type="audiobook"` explicitly.

**Slugs are lower-cased.** `_sanitize_project_id` lower-cases so a project
resolves identically on Windows and Linux. The helper is duplicated in
`book_cli.py`, `drama_cli.py` and `run_pipeline.py`; all three must agree or a
project created by one is invisible to another.

**Fountain SFX syntax is `SFX: description`,** with no brackets — see
`docs/AUDIO_DRAMA_SCRIPT_SPEC.md`. A blank line ends a dialogue block; speech
only resumes across a blank line when a parenthetical beat (`(then)`, `(beat)`,
`(silence)`) interrupted it.
