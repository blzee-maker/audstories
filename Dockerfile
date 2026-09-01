# AudStories backend — API + all four processing engines.
#
# Build from the repo root:   docker build -t audstories-api .
# Or just:                    docker compose up
#
# This image exists mainly to make local setup reproducible. Installing by hand
# has two traps that are easy to get wrong and hard to diagnose; both are handled
# below and commented so nobody "simplifies" them away.

FROM python:3.13-slim

# FFmpeg is a hard runtime requirement: pydub shells out to it for every mix, and
# without it Stage 2 fails at render time rather than at startup.
# build-essential is needed to compile a few wheels that have no manylinux build.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# --- Dependencies -------------------------------------------------------------
# Copy only the requirements first so dependency layers cache independently of
# source changes. Editing a .py file must not trigger a torch reinstall.
COPY backend/requirements.txt                                   backend/requirements.txt
COPY backend/audio_engine/requirements.txt                      backend/audio_engine/requirements.txt
COPY backend/narration_tts/requirements.txt                     backend/narration_tts/requirements.txt
COPY backend/pcddj_engine/story-to-script/requirements.txt      backend/pcddj_engine/story-to-script/requirements.txt

# sentence-transformers pulls torch, and on Linux the default wheel is the CUDA
# build (several GB). This is a CPU-only workload, so install the CPU wheel first
# and let the later resolve see the requirement as already satisfied.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch

# Install order matters and mirrors setup.ps1. audio_engine pins numpy==2.3.3 and
# scipy==1.16.2, which DOWNGRADES the 2.4.x that the NLP group pulls in. That
# downgrade is deliberate and verified ABI-compatible across torch / spaCy /
# scikit-learn, so the audio engine must be installed LAST for its pins to win.
RUN pip install -r backend/requirements.txt \
    && pip install -r backend/pcddj_engine/story-to-script/requirements.txt \
    && pip install -r backend/narration_tts/requirements.txt \
    && pip install -r backend/audio_engine/requirements.txt

# Two spaCy models, for different consumers:
#   en_core_web_lg (~560 MB) - the runtime NLP pipeline
#   en_core_web_sm (~12 MB)  - the test suite's shared `nlp` fixture
RUN python -m spacy download en_core_web_lg \
    && python -m spacy download en_core_web_sm

# --- Application --------------------------------------------------------------
COPY backend/ backend/
# examples/ carries render_demo.py and the example asset library (~126 KB). The
# README points Docker users at `python examples/render_demo.py` to verify their
# install, so it has to exist in the image.
COPY examples/ examples/

# The directories asset_engine/ and audio_engine/ shadow the real packages that
# live one level down (asset_engine/src/asset_engine, audio_engine/audio_engine).
# Editable installs are REQUIRED, not a convenience: the Stage 2 render runs
# `python audio_engine/main.py` as a subprocess, whose `from audio_engine...`
# import only resolves when the package is installed. --no-deps so pip cannot
# re-resolve the numpy/scipy pins settled above. See backend/engine_paths.py.
RUN pip install --no-deps -e backend/audio_engine \
    && pip install --no-deps -e backend/asset_engine \
    && pip install --no-deps -e backend/pcddj_engine/story-to-script

# Runtime state lives here and is mounted as a volume by compose, so rendered
# audio and the SQLite job store survive `docker compose down`.
ENV AS_WORKSPACE_DIR=/data/workspace
RUN mkdir -p /data/workspace

# Run as a non-root user; /data must be writable by it.
RUN useradd --create-home --uid 1000 audstories \
    && chown -R audstories:audstories /data /app
USER audstories

WORKDIR /app/backend

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/openapi.json', timeout=4)" || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
