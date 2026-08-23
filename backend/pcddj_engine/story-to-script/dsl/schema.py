"""Pydantic v2 schema models for the Draft Timeline.

Mirrors the audio engine's ``timeline.json`` structure with additional
*descriptor fields* (``tts_text``, ``mood``, ``atmosphere``, etc.) that
the Asset Resolver consumes to produce the final concrete timeline.

Fields that only exist in the final timeline (``file``, ``start``,
``offset``, ``duration``, ``project.duration``) are intentionally
absent here — they are filled in downstream.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Allowed enum values
# ---------------------------------------------------------------------------

ProjectType = Literal["audiobook", "audio_drama"]
MusicPosition = Literal["intro", "outro", "background"]

TrackType = Literal["voice", "music", "sfx", "ambience"]
TrackRole = Literal["voice", "foreground", "background"]
SFXSemanticRole = Literal["impact", "movement", "ambience", "interaction", "texture"]

EQPreset = Literal[
    "dialogue_clean",
    "dialogue_warm",
    "dialogue_broadcast",
    "music_full",
    "music_bed",
    "background_soft",
    "background_distant",
    "sfx_punch",
    "sfx_subtle",
]

EQTilt = Literal["warm", "neutral", "bright"]
DuckingMode = Literal["audacity"]


# ---------------------------------------------------------------------------
# Settings sub-models
# ---------------------------------------------------------------------------

class DuckingRule(BaseModel):
    """A single role-based ducking rule."""
    when: str
    duck: list[str]


class DuckingConfig(BaseModel):
    """Global ducking configuration."""
    enabled: bool = True
    mode: DuckingMode = "audacity"
    duck_amount: int = Field(default=-6, le=0)
    fade_down_ms: int = Field(default=500, ge=0)
    fade_up_ms: int = Field(default=500, ge=0)
    min_pause_ms: int = Field(default=300, ge=0)
    onset_delay_ms: int = Field(default=120, ge=0)
    rules: list[DuckingRule] = Field(default_factory=list)


class DialogueCompression(BaseModel):
    """Dialogue compressor settings (applied to voice tracks)."""
    enabled: bool = True
    threshold: int = -22
    ratio: float = 2.5
    attack_ms: int = Field(default=20, ge=0)
    release_ms: int = Field(default=180, ge=0)
    makeup_gain: int = 1


class SceneCrossfade(BaseModel):
    """Global scene crossfade configuration."""
    enabled: bool = False
    duration: float = Field(default=1.5, ge=0.0)


class LoudnessConfig(BaseModel):
    """LUFS loudness normalization."""
    enabled: bool = True
    target_lufs: float = -20.0


class OutputPaddingConfig(BaseModel):
    """Head/tail silence on final export (audiobook mastering)."""

    enabled: bool = True
    head_seconds: float = Field(default=1.0, ge=0.0, le=60.0)
    tail_seconds_min: float = Field(default=1.0, ge=0.0, le=120.0)
    tail_seconds_max: float = Field(default=5.0, ge=0.0, le=120.0)


class DraftSettings(BaseModel):
    """Top-level ``settings`` block of the Draft Timeline."""
    project_type: ProjectType = "audio_drama"
    narration_only: bool = False
    # Populated for narration-only audiobook fast-path (plain text metrics).
    source_character_count: int | None = Field(default=None, ge=0)
    source_word_count: int | None = Field(default=None, ge=0)
    estimated_narration_seconds: float | None = Field(default=None, ge=0.0)
    default_silence: float = Field(default=0.5, ge=0.0)
    normalize: bool = True
    master_gain: int = 0
    ducking: DuckingConfig = Field(default_factory=DuckingConfig)
    dialogue_compression: DialogueCompression = Field(
        default_factory=DialogueCompression,
    )
    scene_crossfade: SceneCrossfade = Field(default_factory=SceneCrossfade)
    loudness: LoudnessConfig = Field(default_factory=LoudnessConfig)
    #: Sample peak ceiling for master peak normalization (dBFS, negative).
    peak_target_dbfs: float = Field(default=-1.0, ge=-96.0, le=0.0)
    #: Final mix head/tail silence (``project_type`` audiobook only).
    output_padding: OutputPaddingConfig | None = None


# ---------------------------------------------------------------------------
# Track definition
# ---------------------------------------------------------------------------

class VoiceProfile(BaseModel):
    """Distinctness metadata for a character voice track.

    Used in audio drama mode so that downstream TTS assigns genuinely
    different voices to each character.  No two character tracks in the
    same project should share identical profiles.
    """
    gender: str | None = None
    age_hint: str | None = None
    tone: str | None = None
    pace: str | None = None


class DraftTrack(BaseModel):
    """A top-level audio lane definition.

    In the draft, ``clips`` is always empty — clips live inside scenes.
    """
    id: str
    type: TrackType
    role: TrackRole
    eq_preset: EQPreset | None = None
    gain: int = 0
    semantic_role: SFXSemanticRole | None = None  # SFX tracks only
    voice_profile: VoiceProfile | None = None     # character tracks only


# ---------------------------------------------------------------------------
# Clip (inside a scene)
# ---------------------------------------------------------------------------

class DraftClip(BaseModel):
    """A single clip entry inside a scene's track list.

    Different track types populate different descriptor fields:

    * **Voice clips**: ``tts_text``, ``order``, optionally ``eq_preset``
    * **Music clips**: ``mood``, ``energy_hint``, ``loop``
    * **Ambience clips**: ``atmosphere``, ``loop``
    * **SFX clips**: ``sfx_hint``, ``semantic_role``
    """
    # -- Voice descriptors ---------------------------------------------------
    tts_text: str | None = None
    order: int | None = None
    segment_type: Literal[
        "action", "description", "scene_setting", "transition", "inner_thought"
    ] | None = None
    has_sound_event: bool | None = None

    delivery: str | None = None
    dramatic_function: str | None = None
    pre_silence_ms: int | None = Field(default=None, ge=0)
    post_silence_ms: int | None = Field(default=None, ge=0)

    # -- Music descriptors ---------------------------------------------------
    mood: str | None = None
    energy_hint: float | None = Field(default=None, ge=0.0, le=1.0)
    position: MusicPosition | None = None

    # -- Ambience descriptors ------------------------------------------------
    atmosphere: str | None = None

    # -- SFX descriptors -----------------------------------------------------
    sfx_hint: str | None = None
    semantic_role: SFXSemanticRole | None = None
    sfx_category: str | None = None
    anchor_order: int | None = None
    anchor_position: Literal["before", "under", "after"] | None = None

    # -- Common audio fields (subset of final timeline) ----------------------
    eq_preset: EQPreset | None = None
    loop: bool | None = None
    gain: int | None = None
    fade_in: float | None = Field(default=None, ge=0.0)
    fade_out: float | None = Field(default=None, ge=0.0)


# ---------------------------------------------------------------------------
# Scene
# ---------------------------------------------------------------------------

class SceneEQRules(BaseModel):
    """EQ-related overrides for a scene."""
    tilt: EQTilt | None = None
    high_shelf: float | None = None
    low_shelf: float | None = None


class SceneDuckingOverride(BaseModel):
    """Per-scene ducking overrides (merged on top of global)."""
    duck_amount: int | None = Field(default=None, le=0)


class SceneRules(BaseModel):
    """Optional per-scene rule overrides."""
    eq: SceneEQRules | None = None
    ducking: SceneDuckingOverride | None = None


class DraftScene(BaseModel):
    """A single scene in the Draft Timeline.

    ``tracks`` maps track IDs to lists of :class:`DraftClip`.
    Only tracks that have clips in this scene are included.
    """
    id: str
    name: str
    energy: float = Field(ge=0.0, le=1.0)
    rules: SceneRules | None = None
    tracks: dict[str, list[DraftClip]]


# ---------------------------------------------------------------------------
# Project config
# ---------------------------------------------------------------------------

class ProjectConfig(BaseModel):
    """Technical output configuration.

    ``duration`` is absent — it is unknown until the Asset Resolver
    measures actual audio lengths.
    """
    name: str = "auto_generated"
    sample_rate: int = 48000
    bit_depth: int = 16


# ---------------------------------------------------------------------------
# Top-level Draft Timeline
# ---------------------------------------------------------------------------

class DraftTimeline(BaseModel):
    """Top-level Draft Timeline output.

    Structurally mirrors the audio engine's ``timeline.json`` but uses
    descriptor fields instead of concrete file paths and timing.
    """
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    settings: DraftSettings = Field(default_factory=DraftSettings)
    tracks: list[DraftTrack]
    scenes: list[DraftScene]
