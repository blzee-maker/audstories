# 🎧 Audio Engine

A timeline-based audio rendering engine that generates final audio output from structured JSON timeline files.
The engine reads timestamped audio events and renders them into a single, mixed audio track with precise control over timing, layering, and transitions.

## 🚀 Features

### Core Engine
- **Timeline-based audio execution** — Precise timestamp control
- **Multi-layer audio mixing** — Voice, music, ambience, SFX tracks
- **Deterministic rendering** — Same input → same output
- **JSON-driven and easy to extend**

### Professional DSP
- **EQ System** — Intent-based presets (`dialogue_clean`, `music_bed`, etc.)
- **Advanced Fade Curves** — Linear, logarithmic, exponential fades
- **Compressor** — Dialogue compression with configurable settings
- **Ducking** — Audacity-style envelope-based ducking
- **LUFS Loudness** — Industry-standard loudness normalization
- **Normalization** — Peak and LUFS-based mastering

### Intelligent Features
- **SFX Semantic Roles** — Impact, movement, ambience, interaction, texture
- **Scene Energy System** — 0.0-1.0 intensity mapping
- **Dialogue Density Analysis** — Automatic music gain adjustment
- **Scene Crossfades** — Smooth transitions between scenes
- **Auto-Fix Overlaps** — Automatically resolves clip conflicts

### Cinematic Logic
- **Dynamic music transitions**
- **Energy-based sound design**
- **Silence as a narrative device**

## 📥 Input: Timeline JSON

The engine consumes a JSON file describing when and how audio assets should play.

```json
{
  "project": {
    "name": "My Audio Drama",
    "duration": 120.0
  },
  "settings": {
    "normalize": true,
    "loudness": { "enabled": true, "target_lufs": -20.0 }
  },
  "tracks": [
    {
      "id": "music",
      "type": "music",
      "role": "background",
      "eq_preset": "music_bed",
      "clips": []
    }
  ],
  "scenes": [
    {
      "id": "scene_1",
      "start": 0,
      "duration": 40,
      "energy": 0.4,
      "tracks": {
        "music": [{ "file": "audio/music/intro.mp3", "loop": true }],
        "dialogue": [{ "file": "audio/voice/intro.wav", "offset": 2 }]
      }
    }
  ]
}
```

## ⚙️ How It Works

1. **Parses** the timeline JSON
2. **Validates** input and checks file existence
3. **Preprocesses** scenes into clips with merged rules
4. **Auto-fixes** overlapping clips
5. **Processes** each track with DSP effects (EQ, compression, ducking, fades)
6. **Mixes** tracks together
7. **Masters** the output (LUFS normalization, peak limiting)
8. **Exports** final audio file

## 🧩 Supported Audio Types

| Type | Description |
|------|-------------|
| 🎙️ **Dialogue** | Voice tracks with compression and clarity EQ |
| 🌿 **Ambience** | Looped or timed background atmosphere |
| 🎵 **Music** | Background music with energy-based gain |
| 🔊 **SFX** | Sound effects with semantic role processing |

## 🛠️ Installation

```bash
# Clone the repository
git clone <repository-url>
cd audio_engine

# Create virtual environment
python -m venv venv
.\venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt
```

## 📖 Usage

```bash
python main.py <timeline.json> <output.wav>

# Example
python main.py timeline.json output/final.wav
```

## 📁 Project Structure

```
audio_engine/
├── main.py                 # Entry point
├── renderer/               # Core rendering pipeline
│   ├── timeline_renderer.py   # Main orchestrator
│   ├── clip_processor.py      # Clip-level DSP
│   ├── track_mixer.py         # Track-level mixing
│   └── master_processor.py    # Master processing
├── dsp/                    # Signal processing modules
│   ├── eq.py                  # EQ system
│   ├── eq_presets.py          # Intent-based presets
│   ├── fade_curves.py         # Advanced fade curves
│   ├── fades.py               # Fade application
│   ├── ducking.py             # Envelope-based ducking
│   ├── compression.py         # Dialogue compression
│   ├── loudness.py            # LUFS measurement
│   ├── normalization.py       # Peak normalization
│   ├── balance.py             # Role-based loudness
│   └── sfx_processor.py       # SFX semantic processing
├── utils/                  # Utility modules
│   ├── logger.py              # Logging system
│   ├── dialogue_density.py    # Density analysis
│   └── energy.py              # Energy mapping
├── scene_preprocessor.py   # Scene → clip expansion
├── validation.py           # Input validation
├── autofix.py              # Overlap resolution
├── docs/                   # Documentation
└── test/                   # Test files
```

## 📚 Documentation

- [Timeline JSON Schema](docs/timeline_json_schema.md) — Complete JSON specification
- [EQ System](docs/eq_system_v1.md) — Intent-based EQ implementation
- [Fade Curves](docs/FADE_CURVES_IMPLEMENTATION.md) — Advanced fade curve details
- [SFX Implementation](docs/SFX_IMPLEMENTATION.md) — Semantic role processing
- [Engine Analysis](docs/AUDIO_ENGINE_ANALYSIS.md) — Architecture overview
- [Design Decisions](docs/DESIGN_DECISIONS.md) — Engineering rationale

## 🎯 Output

- **WAV format** — High-quality uncompressed audio
- **Configurable sample rate** — 44.1kHz, 48kHz, etc.
- **Loudness normalized** — Streaming-ready (-20 LUFS default)

## 📋 Requirements

- Python 3.8+
- pydub
- numpy
- scipy
- pyloudnorm

---

*Last Updated: February 2026*
