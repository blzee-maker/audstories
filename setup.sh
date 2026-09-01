#!/usr/bin/env bash
# AudStories - one-shot local setup for macOS / Linux.
# Run once from the repo root:  ./setup.sh
# Then follow the "Next steps" printed at the end.
#
# This mirrors setup.ps1. If you change one, change the other.
# Prefer `docker compose up` if you would rather not install this locally.

set -euo pipefail

info() { printf '\033[36m[INFO]\033[0m  %s\n' "$*"; }
ok()   { printf '\033[32m[ OK ]\033[0m  %s\n' "$*"; }
warn() { printf '\033[33m[WARN]\033[0m  %s\n' "$*"; }
fatal() { printf '\033[31m[FAIL]\033[0m  %s\n' "$*" >&2; exit 1; }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_ROOT="$REPO_ROOT/backend"
FRONTEND_ROOT="$REPO_ROOT/frontend"

[ -d "$BACKEND_ROOT" ] || fatal "Expected a 'backend' folder next to this script. Run setup.sh from the repo root."

# --- 1. Python version check --------------------------------------------------
info "Checking Python version..."
PYTHON_BIN=""
for candidate in python3.13 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 13) else 1)' 2>/dev/null; then
            PYTHON_BIN="$candidate"
            break
        fi
    fi
done
[ -n "$PYTHON_BIN" ] || fatal "Python 3.13+ not found. Install it from python.org or your package manager."
ok "Python $("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"

# --- 2. FFmpeg check ----------------------------------------------------------
info "Checking FFmpeg..."
if command -v ffmpeg >/dev/null 2>&1; then
    ok "FFmpeg found at $(command -v ffmpeg)"
else
    warn "FFmpeg not found on PATH."
    warn "Audio rendering (Stage 2) will fail without it."
    warn "Install:  macOS 'brew install ffmpeg'  |  Debian/Ubuntu 'sudo apt install ffmpeg'"
fi

# --- 3. Create virtual environment --------------------------------------------
VENV_DIR="$REPO_ROOT/.venv"
if [ -d "$VENV_DIR" ]; then
    info "Virtual environment already exists at .venv - skipping creation."
else
    info "Creating virtual environment..."
    "$PYTHON_BIN" -m venv "$VENV_DIR"
    ok "Virtual environment created at .venv"
fi
PY="$VENV_DIR/bin/python"

# --- 4. Install all dependencies ----------------------------------------------
info "Upgrading pip..."
"$PY" -m pip install --quiet --upgrade pip setuptools wheel

# Install order matters. audio_engine pins numpy==2.3.3 / scipy==1.16.2, which
# DOWNGRADES the 2.4.x the NLP group pulls in. That downgrade is deliberate and
# verified ABI-compatible, so the audio engine is installed LAST for its pins to win.
info "Installing API + engine dependencies..."
"$PY" -m pip install --quiet -r "$BACKEND_ROOT/requirements.txt"
ok "Core API deps installed"

# sentence-transformers pulls torch. On Linux the default PyPI wheel bundles CUDA
# and is several GB; nothing in this codebase touches a GPU (no cuda/device calls
# anywhere in backend/), so that download is pure waste. Install the CPU wheel
# first and let the resolve below see the requirement as satisfied.
# macOS wheels are CPU-only already, so this only applies to Linux.
# To use a GPU build instead, install your preferred torch before running this.
if [ "$(uname -s)" = "Linux" ] && ! "$PY" -c "import torch" >/dev/null 2>&1; then
    info "Installing CPU-only PyTorch (avoids a multi-GB CUDA download)..."
    "$PY" -m pip install --quiet --index-url https://download.pytorch.org/whl/cpu torch
    ok "PyTorch (CPU) installed"
fi

info "Installing story-processing (NLP) dependencies..."
"$PY" -m pip install --quiet -r "$BACKEND_ROOT/pcddj_engine/story-to-script/requirements.txt"
ok "NLP deps installed"

info "Installing narration TTS dependencies..."
"$PY" -m pip install --quiet -r "$BACKEND_ROOT/narration_tts/requirements.txt"
ok "TTS deps installed"

info "Installing audio engine dependencies..."
"$PY" -m pip install --quiet -r "$BACKEND_ROOT/audio_engine/requirements.txt"
ok "Audio engine deps installed"

# Editable installs are REQUIRED, not a convenience. The directories asset_engine/
# and audio_engine/ shadow the real packages one level down, and the Stage 2 render
# runs `python audio_engine/main.py` as a subprocess whose `from audio_engine...`
# import only resolves when the package is installed. --no-deps so pip cannot
# re-resolve the numpy/scipy pins settled above. See backend/engine_paths.py.
info "Registering in-repo engine packages (editable)..."
"$PY" -m pip install --quiet --no-deps -e "$BACKEND_ROOT/audio_engine"
"$PY" -m pip install --quiet --no-deps -e "$BACKEND_ROOT/asset_engine"
"$PY" -m pip install --quiet --no-deps -e "$BACKEND_ROOT/pcddj_engine/story-to-script"
ok "Engine packages registered"

# --- 5. Download spaCy language models ----------------------------------------
# en_core_web_lg (~560 MB) - the runtime NLP pipeline
# en_core_web_sm (~12 MB)  - the test suite's shared `nlp` fixture
# Skipped when already importable: re-running setup is common, and re-fetching
# 560 MB each time is slow and gives the transfer another chance to fail.
install_spacy_model() {
    local name="$1" size="$2"
    if "$PY" -c "import $name" >/dev/null 2>&1; then
        info "spaCy model $name already installed - skipping download."
        return
    fi
    info "Downloading spaCy English model ($name, $size)..."
    "$PY" -m spacy download "$name"
}
install_spacy_model en_core_web_lg "~560 MB, takes a minute"
install_spacy_model en_core_web_sm "~12 MB, used by the tests"
ok "spaCy models ready"

# --- 6. Seed .env files if missing --------------------------------------------
if [ ! -f "$BACKEND_ROOT/.env" ]; then
    cp "$BACKEND_ROOT/.env.example" "$BACKEND_ROOT/.env"
    warn "backend/.env created from .env.example - fill in your keys before starting."
else
    info "Backend .env already exists."
fi

if [ -d "$FRONTEND_ROOT" ] && [ ! -f "$FRONTEND_ROOT/.env" ]; then
    cp "$FRONTEND_ROOT/.env.example" "$FRONTEND_ROOT/.env"
    warn "frontend/.env created from .env.example - fill in your Supabase keys before starting."
elif [ -d "$FRONTEND_ROOT" ]; then
    info "Frontend .env already exists."
fi

# --- Done ---------------------------------------------------------------------
cat <<'EOF'

===============================================
 Setup complete. Next steps:
===============================================

 Fastest path - no accounts needed:
   1. Set AS_DEV_NO_AUTH=1 and GEMINI_API_KEY in backend/.env
   2. source .venv/bin/activate
   3. cd backend && uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
   4. Open http://localhost:8000/docs

 Full setup with the web UI:
   1. Run schema.sql in Supabase Dashboard -> SQL Editor
   2. Fill in backend/.env   (Supabase + Gemini keys)
   3. Fill in frontend/.env  (Supabase keys)

 Start backend (activate the venv first, and run from backend/):
   source .venv/bin/activate
   cd backend
   uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

 Start frontend (separate terminal):
   cd frontend
   npm install
   npm run dev

 Then open http://localhost:5173 in your browser.

 Run the tests:  see docs/TESTING.md

EOF
