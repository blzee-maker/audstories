# AudStories - one-shot local setup for Windows (PowerShell)
# Run once from the repo root:  .\setup.ps1
# Then follow the "Next steps" printed at the end.
#
# NOTE: kept pure ASCII on purpose - Windows PowerShell 5.1 reads BOM-less
# scripts as ANSI, which would garble any non-ASCII characters.

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"   # applies to cmdlets; native calls use Invoke-Step

function Info  { Write-Host "[INFO]  $args" -ForegroundColor Cyan }
function Ok    { Write-Host "[ OK ]  $args" -ForegroundColor Green }
function Warn  { Write-Host "[WARN]  $args" -ForegroundColor Yellow }
function Fatal { Write-Host "[FAIL]  $args" -ForegroundColor Red ; exit 1 }

# Run a native command (pip/python) without letting its stderr writes be treated
# as terminating errors. PowerShell 5.1 wraps native stderr as NativeCommandError
# and, under ErrorActionPreference=Stop, aborts the script even on exit code 0.
# We flip to Continue for the call and judge success purely by the exit code.
function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)][string]$What,
        [Parameter(Mandatory = $true)][scriptblock]$Action
    )
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $Action
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prev
    }
    if ($code -ne 0) { Fatal "$What failed (exit code $code). See output above." }
}

$RepoRoot     = $PSScriptRoot
$BackendRoot  = Join-Path $RepoRoot "backend"
$FrontendRoot = Join-Path $RepoRoot "frontend"

if (-not (Test-Path $BackendRoot)) {
    Fatal "Expected a 'backend' folder next to this script. Run setup.ps1 from the repo root."
}

# --- 1. Python version check --------------------------------------------------
Info "Checking Python version..."
$PyCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $PyCmd) { Fatal "Python not found on PATH. Install Python 3.13 from python.org." }

$PyVer = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($PyVer -notmatch "^3\.1[3-9]") {
    Fatal "Python 3.13+ required (found $PyVer). Download from python.org."
}
Ok "Python $PyVer"

# --- 2. FFmpeg check ----------------------------------------------------------
Info "Checking FFmpeg..."
$FfmpegCmd = Get-Command ffmpeg -ErrorAction SilentlyContinue
$FfmpegExe = if ($FfmpegCmd) { $FfmpegCmd.Source } else { $null }
if (-not $FfmpegExe) {
    Warn "FFmpeg not found on PATH."
    Warn "Audio rendering (Stage 2) will fail without it."
    Warn "Install: winget install Gyan.FFmpeg  - then restart this terminal."
} else {
    Ok "FFmpeg found at $FfmpegExe"
}

# --- 3. Create virtual environment --------------------------------------------
$VenvDir = Join-Path $RepoRoot ".venv"
if (Test-Path $VenvDir) {
    Info "Virtual environment already exists at .venv - skipping creation."
} else {
    Info "Creating virtual environment..."
    Invoke-Step "venv creation" { & python -m venv $VenvDir }
    Ok "Virtual environment created at .venv"
}

# Use "python -m pip" everywhere: on Windows, running pip.exe directly cannot
# upgrade pip (it can't overwrite its own running .exe), and -m pip is the
# canonical, self-consistent invocation for a venv interpreter.
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"

# --- 4. Install all dependencies ----------------------------------------------
Info "Upgrading pip..."
Invoke-Step "pip upgrade" { & $PythonExe -m pip install --upgrade pip }

Info "Installing API + engine dependencies..."
Invoke-Step "Core API deps" { & $PythonExe -m pip install -r (Join-Path $BackendRoot "requirements.txt") }
Ok "Core API deps installed"

Info "Installing story-processing (NLP) dependencies..."
Invoke-Step "NLP deps" { & $PythonExe -m pip install -r (Join-Path $BackendRoot "pcddj_engine\story-to-script\requirements.txt") }
Ok "NLP deps installed"

Info "Installing narration TTS dependencies..."
Invoke-Step "TTS deps" { & $PythonExe -m pip install -r (Join-Path $BackendRoot "narration_tts\requirements.txt") }
Ok "TTS deps installed"

Info "Installing audio engine dependencies..."
Invoke-Step "Audio engine deps" { & $PythonExe -m pip install -r (Join-Path $BackendRoot "audio_engine\requirements.txt") }
Ok "Audio engine deps installed"

# Editable-install the three in-repo packages so they are importable as real
# packages. This is REQUIRED: the Stage 2 audio render runs `python
# audio_engine/main.py` as a subprocess, whose `from audio_engine...` import
# only resolves when audio_engine is installed (a bare script run does not put
# its parent dir on sys.path). --no-deps because every dependency is already
# installed above and we must not let pip re-resolve the numpy/scipy pins.
Info "Registering in-repo engine packages (editable)..."
Invoke-Step "audio_engine (editable)" { & $PythonExe -m pip install -e (Join-Path $BackendRoot "audio_engine") --no-deps }
Invoke-Step "asset_engine (editable)" { & $PythonExe -m pip install -e (Join-Path $BackendRoot "asset_engine") --no-deps }
Invoke-Step "story-to-script (editable)" { & $PythonExe -m pip install -e (Join-Path $BackendRoot "pcddj_engine\story-to-script") --no-deps }
Ok "Engine packages registered"

# --- 5. Download spaCy language models -----------------------------------------
# Two models are required, for different purposes:
#   en_core_web_lg (~560 MB) - loaded by the runtime NLP pipeline
#                              (story_processing/nlp/spacy_pipeline.py)
#   en_core_web_sm (~12 MB)  - loaded by the test suite's shared 'nlp' fixture
#                              (pcddj_engine/story-to-script/tests/conftest.py)
# Installing only the large model leaves the test suite erroring with
# OSError [E050] "Can't find model 'en_core_web_sm'".
#
# Each download is skipped when the model already imports. Re-running setup.ps1
# is common, and re-fetching 560 MB every time is slow and gives the download an
# extra chance to fail on a truncated transfer ("Wheel ... is invalid").
function Install-SpacyModel {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Size
    )
    & $PythonExe -c "import $Name" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Info "spaCy model $Name already installed - skipping download."
        return
    }
    Info "Downloading spaCy English model ($Name, $Size)..."
    Invoke-Step "spaCy $Name download" { & $PythonExe -m spacy download $Name }
}

Install-SpacyModel -Name "en_core_web_lg" -Size "~560 MB, takes a minute"
Install-SpacyModel -Name "en_core_web_sm" -Size "~12 MB, used by the tests"
Ok "spaCy models ready"

# --- 6. Seed .env files if missing --------------------------------------------
$BackendEnv  = Join-Path $BackendRoot ".env"
$FrontendEnv = Join-Path $FrontendRoot ".env"

if (-not (Test-Path $BackendEnv)) {
    Copy-Item (Join-Path $BackendRoot ".env.example") $BackendEnv
    Warn ".env created from .env.example - fill in your Supabase + Gemini keys before starting."
} else {
    Info "Backend .env already exists."
}

if (-not (Test-Path $FrontendEnv)) {
    Copy-Item (Join-Path $FrontendRoot ".env.example") $FrontendEnv
    Warn "Frontend .env created from .env.example - fill in your Supabase keys before starting."
} else {
    Info "Frontend .env already exists."
}

# --- Done ---------------------------------------------------------------------
Write-Host ""
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host " Setup complete. Next steps:" -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host " 1. Run schema.sql in Supabase Dashboard -> SQL Editor"
Write-Host " 2. Fill in backend\.env   (Supabase + Gemini keys)"
Write-Host " 3. Fill in frontend\.env  (Supabase keys)"
Write-Host ""
Write-Host " Start backend (activate the venv first, and run from backend\):"
Write-Host "   .venv\Scripts\Activate.ps1"
Write-Host "   cd backend"
Write-Host "   uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload"
Write-Host ""
Write-Host " Start frontend (separate terminal):"
Write-Host "   cd frontend"
Write-Host "   npm install"
Write-Host "   npm run dev"
Write-Host ""
Write-Host " Then open http://localhost:5173 in your browser."
Write-Host ""
Write-Host " Run the tests:  see docs\TESTING.md"
Write-Host ""
