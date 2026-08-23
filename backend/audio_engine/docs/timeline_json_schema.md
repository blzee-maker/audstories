# 📘 Timeline.json Specification

A complete guide to writing timelines for the Audio Engine

---

1️⃣ Overview

`timeline.json` is the single source of truth for the audio engine.

It defines:

* What audio plays
* When it plays
* How it behaves
* How scenes transition
* How intelligence (ducking, energy, loudness) is applied

The engine does not guess.
Everything is explicit, deterministic, and reproducible.

---

2️⃣ Top-Level Structure

```json
{
  "project": {},
  "settings": {},
  "tracks": [],
  "scenes": []
}
```

| Key        | Purpose                        |
| ---------- | ------------------------------ |
| `project`  | Technical output configuration |
| `settings` | Global audio behavior          |
| `tracks`   | Logical audio lanes            |
| `scenes`   | Story-based time blocks        |

---

3️⃣ `project` — Output Definition

```json
"project": {
  "name": "My Audio Drama",
  "duration": 120.0,
  "sample_rate": 48000,
  "bit_depth": 16
}
```

| Field         | Type         | Meaning             |
| ------------- | ------------ | ------------------- |
| `name`        | string       | Project label       |
| `duration`    | number (sec) | Total output length |
| `sample_rate` | number       | Audio sample rate   |
| `bit_depth`   | number       | Output bit depth    |

📌 `duration` is mandatory — all audio is clipped to this.

---

4️⃣ `settings` — Global Audio Rules

These apply unless overridden by scenes.

Example

```json
"settings": {
  "default_silence": 0.5,
  "normalize": true,
  "master_gain": 0
}
```

Common Settings

| Key               | Meaning                       |
| ----------------- | ----------------------------- |
| `default_silence` | Gap between auto-placed clips |
| `normalize`       | Peak normalization            |
| `master_gain`     | Final output gain             |

---

5️⃣ Ducking Configuration

```json
"ducking": {
  "enabled": true,
  "mode": "audacity",
  "duck_amount": -6,
  "fade_down_ms": 500,
  "fade_up_ms": 500,
  "min_pause_ms": 300,
  "onset_delay_ms": 120,
  "rules": [
    { "when": "voice", "duck": ["background"] },
    { "when": "voice", "duck": ["background", "sfx:ambience"] },
    { "when": "sfx:impact", "duck": ["music", "background"] }
  ]
}
```

What This Means

Music ducks after dialogue actually begins
Ducking is smooth and natural
Short dialogue gaps don't cause pumping
SFX can participate in bidirectional ducking (when explicitly configured)

| Field            | Meaning                    |
| ---------------- | -------------------------- |
| `mode`           | Ducking style (`audacity`) |
| `duck_amount`    | Gain reduction in dB       |
| `fade_down_ms`   | Fade into duck             |
| `fade_up_ms`     | Recovery fade              |
| `min_pause_ms`   | Ignore micro pauses        |
| `onset_delay_ms` | Delay before ducking       |
| `rules`          | Role-based behavior        |

**Ducking Rules with SFX Semantic Roles:**

Ducking is **opt-in** via rules. Semantic roles define eligibility, but ducking only happens when explicitly configured.

**Rule Format:**
- `when`: The role that triggers ducking (mix role like `"voice"` or semantic role like `"sfx:impact"`)
- `duck`: List of roles to duck (mix roles or semantic roles like `"sfx:ambience"`)

**Examples:**

```json
// Dialogue ducks background music and ambient SFX
{ "when": "voice", "duck": ["background", "sfx:ambience"] }

// Impact SFX ducks music and background
{ "when": "sfx:impact", "duck": ["music", "background"] }

// Dialogue ducks all movement SFX
{ "when": "voice", "duck": ["sfx:movement"] }
```

**Important:** Ducking is **not automatic** based on semantic role. You must explicitly configure ducking rules for the behavior you want. This keeps the system predictable, debuggable, and configurable.

---

6️⃣ Dialogue Compression

```json
"dialogue_compression": {
  "enabled": true,
  "threshold": -22,
  "ratio": 2.5,
  "attack_ms": 20,
  "release_ms": 180,
  "makeup_gain": 1
}
```

Used only on voice tracks.

Purpose:

Consistent loudness
No ear fatigue
Broadcast-style clarity

---

## 7️⃣ Scene Crossfade

```json
"scene_crossfade": {
  "enabled": true,
  "duration": 1.5
}
```

Automatically:

ades out previous scene
Fades in next scene
Overlaps scenes slightly

No silence gaps.

---

8️⃣ Loudness (LUFS)

```json
"loudness": {
  "enabled": true,
  "target_lufs": -20.0
}
```

Applied after rendering, before normalization.

Ensures:

Streaming-safe loudness
Consistent output level

---

8️⃣.5️⃣ EQ (Equalization) — Frequency Shaping

EQ gives the engine control over **frequency space**, not just volume. It prevents frequency clashes before they happen, improving clarity and balance. Sounds stop competing and start coexisting by design.

### Intent-First Design

EQ is exposed through **semantic presets** rather than raw Hz values. Authors describe what they want, and the engine handles the frequency details internally.

```json
"eq_preset": "dialogue_clean"
```

### Available Presets

| Preset | Intent | Best For |
| ------ | ------ | -------- |
| `dialogue_clean` | Clear voice, no rumble | Standard dialogue |
| `dialogue_warm` | Rich voice, less bright | Intimate narration |
| `dialogue_broadcast` | Broadcast-ready voice | Podcasts, radio |
| `music_full` | Full spectrum music | Music-focused content |
| `music_bed` | Music as background bed | Dialogue over music |
| `background_soft` | Non-invasive ambience | Subtle backgrounds |
| `background_distant` | Far-away feel | Distant atmospheres |
| `sfx_punch` | Impactful SFX | Door slams, impacts |
| `sfx_subtle` | Gentle SFX presence | Footsteps, rustling |

### Role-Based Defaults

When no preset is specified, roles get sensible defaults automatically:

| Role | Default Preset | Rationale |
| ---- | -------------- | --------- |
| voice | `dialogue_clean` | Clarity is paramount |
| music | `music_bed` | Creates space for dialogue |
| background | `background_soft` | Non-invasive by design |
| sfx | (varies by semantic_role) | Depends on sound type |

SFX semantic roles also have default presets:

| Semantic Role | Default Preset |
| ------------- | -------------- |
| impact | `sfx_punch` |
| movement | `sfx_subtle` |
| ambience | `background_soft` |
| texture | `background_distant` |

### Track-Level EQ Preset

Override the role default for an entire track:

```json
{
  "id": "dialogue",
  "type": "voice",
  "role": "voice",
  "eq_preset": "dialogue_broadcast",
  "clips": []
}
```

### Clip-Level EQ Preset

Override for a specific clip:

```json
{
  "file": "audio/voice/narrator_whisper.wav",
  "eq_preset": "dialogue_warm"
}
```

### Scene-Level Tonal Shaping

Scenes can apply **broad tonal adjustments** to the entire mix. This is intentionally limited to prevent conflicts with role presets.

**Allowed at scene level:**
- `tilt`: Overall tonal shift ("warm", "neutral", "bright")
- `high_shelf`: dB adjustment above ~4kHz
- `low_shelf`: dB adjustment below ~200Hz

**NOT allowed at scene level:**
- Narrow parametric bands (specific Hz + Q)
- High-pass/low-pass overrides
- Per-role EQ overrides

```json
"rules": {
  "eq": {
    "tilt": "warm"
  }
}
```

Or with explicit shelves:

```json
"rules": {
  "eq": {
    "high_shelf": -2,
    "low_shelf": 1
  }
}
```

### Global Tonal Shaping (Settings-Level)

Apply tonal shaping to the entire project output:

```json
"settings": {
  "eq": {
    "tilt": "bright",
    "high_shelf": 1.5
  }
}
```

### EQ + Ducking Relationship

EQ and ducking are **loosely coupled**. EQ improves spectral separation, which allows ducking to be lighter and more natural:

| Scenario | Without EQ | With EQ |
| -------- | ---------- | ------- |
| Voice over music | Duck -12dB | Duck -6dB (EQ carved space) |
| Ambience behind dialogue | Heavy ducking or muddy | Light ducking, clean separation |

**Tip:** When using EQ presets, you may be able to reduce your `duck_amount` for a more natural mix.

---

9️⃣ Tracks — Audio Lanes

Tracks define what kind of audio this is, not when it plays.

```json
{
  "id": "music",
  "type": "music",
  "role": "background",
  "gain": -6,
  "clips": []
}
```

Track Fields

| Field           | Meaning                           |
| --------------- | --------------------------------- |
| `id`            | Unique identifier                 |
| `type`          | music / voice / sfx / ambience    |
| `role`           | background / voice / foreground   |
| `semantic_role`  | (SFX only) impact / movement / ambience / interaction / texture |
| `eq_preset`     | EQ preset override (see EQ section) |
| `gain`          | Track-wide gain                   |
| `clips`         | (usually empty when using scenes) |

📌 With scenes, clips are usually declared inside scenes, not here.

**Important: Mix Role vs Semantic Role**

- `role` = **mix_role** (where it sits in the mix hierarchy: foreground/background/voice)
- `semantic_role` = **what the sound represents** (for SFX: impact, movement, etc.)

These are **orthogonal concepts**. An SFX can be "foreground" (mix_role) and "ambience" (semantic_role) simultaneously - they answer different questions.

---

9️⃣.5️⃣ Sound Effects (SFX) — Semantic Roles

SFX tracks can specify a `semantic_role` to define what the sound represents. This enables intent-driven processing with appropriate loudness, timing, and fade behavior.

**Valid Semantic Roles:**

- `impact` - Sharp attacks (door slams, impacts, crashes)
- `movement` - Movement sounds (footsteps, cloth rustling)
- `ambience` - Ambient textures (wind, water, background atmosphere)
- `interaction` - Interaction sounds (door creaks, button presses)
- `texture` - Very subtle ambient textures (room tone, subtle background)

**Track-Level Semantic Role:**

```json
{
  "id": "sfx",
  "type": "sfx",
  "role": "foreground",
  "semantic_role": "movement",  // Default for all clips on this track
  "clips": []
}
```

**Clip-Level Semantic Role (Overrides Track):**

```json
{
  "tracks": {
    "sfx": [
      {
        "file": "audio/sfx/footstep.mp3",
        "semantic_role": "movement"  // Clip-level override
      },
      {
        "file": "audio/sfx/door_slam.mp3",
        "semantic_role": "impact"  // Different role for this clip
      }
    ]
  }
}
```

**Semantic Role Behaviors:**

| Role       | LUFS Target | Fade In | Fade Out | Curve          |
| ---------- | ----------- | ------- | -------- | -------------- |
| `impact`   | -18.0       | 0ms     | 75ms     | Exponential    |
| `movement` | -20.0       | 150ms   | 150ms    | Linear         |
| `ambience` | -22.0       | 750ms   | 750ms    | Logarithmic    |
| `interaction` | -20.0    | 250ms   | 250ms    | Linear         |
| `texture`  | -24.0       | 1500ms  | 1500ms   | Logarithmic    |

**Ducking Eligibility:**

Semantic roles define **eligibility** for ducking, not mandatory behavior. Actual ducking comes from explicit ducking rules (see Ducking Configuration below).

- `impact` - Eligible to duck music/background
- `movement` - Eligible to be ducked by dialogue
- `ambience` - Eligible to be ducked by dialogue
- `interaction` - Eligible for ducking
- `texture` - Never participates in ducking

**Timing Adjustments (v1):**

Only minimal micro-timing adjustments are applied:
- Attack shaping (trimming silence at start)
- Silence trimming at end

**No timeline shifts** - audio position is never changed automatically.

---

🔟 Scenes — Story Blocks

Scenes define when and why audio plays.

```json
{
  "id": "scene_1",
  "name": "Opening Atmosphere",
  "start": 0,
  "duration": 40,
  "energy": 0.4,
  "tracks": {}
}
```

Scene Fields

| Field      | Meaning                       |
| ---------- | ----------------------------- |
| `id`       | Scene identifier              |
| `name`     | Human-readable name           |
| `start`    | Start time (sec)              |
| `duration` | Scene length                  |
| `energy`   | Narrative intensity (0.0–1.0) |
| `tracks`   | Scene-local clips             |

---

1️⃣1️⃣ Scene Energy (Important)

```json
"energy": 0.0 → very restrained  
"energy": 0.5 → neutral  
"energy": 1.0 → intense
```

Used to:

Adjust music presence
Drive cinematic ramps
Enable story-aware mixing

---

1️⃣2️⃣ Scene Tracks & Clips

```json
"tracks": {
  "music": [
    {
      "file": "audio/music/Days.mp3",
      "loop": true
    }
  ],
  "dialogue": [
    {
      "file": "audio/voice/Scene-1.wav",
      "offset": 2
    }
  ]
}
```

Clip Fields

| Field           | Meaning                   |
| --------------- | ------------------------- |
| `file`          | Audio file path           |
| `start`         | Absolute start (optional) |
| `offset`        | Scene-relative start      |
| `loop`          | Loop until scene ends     |
| `gain`          | Clip-level gain           |
| `eq_preset`     | EQ preset override (see EQ section) |
| `semantic_role` | (SFX only) Overrides track semantic_role |
| `fade_in`       | Fade-in duration (seconds) or object with `duration` and `curve` |
| `fade_out`      | Fade-out duration (seconds) or object with `duration` and `curve` |

**SFX Fade Defaults:**

If `fade_in` or `fade_out` are not specified for SFX clips, defaults are applied based on `semantic_role`:

- `impact`: No fade-in, 75ms exponential fade-out
- `movement`: 150ms linear fade-in/out
- `ambience`: 750ms logarithmic fade-in/out
- `interaction`: 250ms linear fade-in/out
- `texture`: 1500ms logarithmic fade-in/out

---

1️⃣3️⃣ Rule Overrides (Scene-Level)

Scenes can override global settings:

```json
"rules": {
  "ducking": {
    "duck_amount": -18
  },
  "dialogue_compression": {
    "threshold": -22
  }
}
```

These overrides:

Apply only inside this scene
Are merged into `_rules` during preprocessing

---

## 1️⃣4️⃣ Internal Fields (Engine-Generated)

These are not written manually:

| Field                  | Purpose            |
| ---------------------- | ------------------ |
| `_rules`               | Merged rule set    |
| `fade_in` / `fade_out` | Scene transitions  |
| `scene_energy`         | Active energy      |
| `prev_scene_energy`    | For ramps          |
| `energy_ramp_duration` | Smooth transitions |

---

1️⃣5️⃣ Philosophy

Timeline.json is declarative
No DSP logic lives here
Story intent > audio tricks
Same file can render:

  Podcast
  Audio drama
  Cinematic narration

---

*Last updated: February 2026*
