# Testing

All six suites pass. A full backend run takes about a minute.

| Suite | Location | Tests | Runtime |
|---|---|---|---|
| `asset_engine` | `backend/asset_engine` | 54 | ~1.4s |
| `api` | `backend` (run `pytest api/`) | 20 | ~1.6s |
| `audio_engine` | `backend/audio_engine` | 15 | ~8s |
| `narration_tts` | `backend/narration_tts` | 18 | ~0.7s |
| `story-to-script` | `backend/pcddj_engine/story-to-script` | 309 | ~55s |
| frontend | `frontend` (`npm test`) | 11 | ~3s |

**427 tests**, none of them `xfail`. There is one conditional `pytest.skip` —
`asset_engine`'s contract test against the story-to-script sample — and it never
fires, because the sample draft it looks for is committed.

## Running them

```bash
# from the repo root, with the venv active
cd backend/asset_engine                  && pytest
cd backend                               && pytest api/
cd backend/audio_engine                  && pytest
cd backend/narration_tts                 && pytest
cd backend/pcddj_engine/story-to-script  && pytest

cd frontend && npm test
```

## Prerequisites

- **Both spaCy models.** The shared `nlp` fixture loads `en_core_web_sm`
  explicitly; missing it produces 27 errors of the form
  `OSError [E050] Can't find model 'en_core_web_sm'`. `en_core_web_lg` is the
  CLI's default, and `tests/test_cli_smoke.py` shells out to
  `python -m cli process` without naming a model, so it exercises that default and
  needs the large model present. `setup.ps1` and `setup.sh` install both.
- **FFmpeg on PATH**, for anything that touches `pydub`.
- No API keys are needed. Nothing in the suites calls Gemini — `narration_tts`
  mocks the client rather than reaching the network.

## In CI

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) runs all six suites on
every push and pull request, each as its own step so a failure names the engine
that broke.

[`.github/workflows/install.yml`](../.github/workflows/install.yml) is the slow
half: it runs `setup.sh` verbatim on a clean runner, builds the Docker image, and
renders the demo through both. It is triggered by changes to the setup or
dependency files, weekly on a schedule, and manually. The schedule is the point —
the dependency set is not pinned end to end, so a new numpy or a moved spaCy model
URL can break a fresh install with no commit landing.

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
clean — CI asserts exactly that.

**Narrator behaviour is the audiobook contract.** `build_tracks` and
`build_voice_clips` default to `project_type="audio_drama"`, where narration is
silent and voices are per character. A test asserting narrator output must pass
`project_type="audiobook"` explicitly.

**Slugs are lower-cased.** `_sanitize_project_id` lower-cases so a project
resolves identically on Windows and Linux. The helper is duplicated in
`book_cli.py`, `drama_cli.py` and `run_pipeline.py`; all three must agree or a
project created by one is invisible to another.

**Fountain SFX syntax is `SFX: description`,** with no brackets — see
[AUDIO_DRAMA_SCRIPT_SPEC.md](AUDIO_DRAMA_SCRIPT_SPEC.md). A blank line ends a
dialogue block; speech only resumes across a blank line when a parenthetical beat
(`(then)`, `(beat)`, `(silence)`) interrupted it.
