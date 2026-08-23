# Manual DSP scripts

These are **not** tests. They are scratch scripts kept for manual inspection of the
DSP chain — they render audio, print measurements, and in some cases write WAV files
into `audio_engine/output/`.

They previously lived in `tests/` under `test_*.py` names. Because pytest imports every
module it collects, and these scripts do their work at import time rather than inside
test functions, simply *collecting* the test suite executed a full render and wrote tens
of megabytes of audio. Collection alone took over three minutes. Renaming them out of the
`test_` namespace fixed that.

## Running them

Each script is standalone. Run from the `audio_engine/` directory:

```bash
python scripts/loudness.py
```

## Input files

Most of these read audio that is **not committed to this repository** — the working
files under `audio_engine/audio/` were excluded for size and licensing reasons. Only
`audio/music/Days.mp3` is present, as a fixture for the real integration tests.

Point the scripts at your own audio, or restore the paths they expect, before running.
