"""Input contract models for story-to-script draft timelines."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

TrackType = Literal["voice", "music", "sfx", "ambience"]
TrackRole = Literal["voice", "foreground", "background"]
SFXSemanticRole = Literal["impact", "movement", "ambience", "interaction", "texture"]


class VoiceProfile(BaseModel):
    """Character voice distinctness metadata."""
    gender: str | None = None
    age_hint: str | None = None
    tone: str | None = None
    pace: str | None = None


class DraftTrack(BaseModel):
    id: str
    type: TrackType
    role: TrackRole
    eq_preset: str | None = None
    gain: int = 0
    semantic_role: SFXSemanticRole | None = None
    voice_profile: VoiceProfile | None = None


MusicPosition = Literal["intro", "outro", "background"]


class DraftClip(BaseModel):
    tts_text: str | None = None
    order: int | None = None
    segment_type: str | None = None
    has_sound_event: bool | None = None
    delivery: str | None = None
    dramatic_function: str | None = None
    pre_silence_ms: int | None = None
    post_silence_ms: int | None = None
    mood: str | None = None
    energy_hint: float | None = Field(default=None, ge=0.0, le=1.0)
    position: MusicPosition | None = None
    atmosphere: str | None = None
    sfx_hint: str | None = None
    semantic_role: SFXSemanticRole | None = None
    sfx_category: str | None = None
    anchor_order: int | None = None
    anchor_position: str | None = None
    eq_preset: str | None = None
    loop: bool | None = None
    gain: int | None = None
    fade_in: float | dict[str, Any] | None = None
    fade_out: float | dict[str, Any] | None = None


class DraftScene(BaseModel):
    id: str
    name: str
    energy: float = Field(ge=0.0, le=1.0)
    rules: dict[str, Any] | None = None
    tracks: dict[str, list[DraftClip]]


class DraftProject(BaseModel):
    name: str = "auto_generated"
    sample_rate: int = 48000
    bit_depth: int = 16


class DraftTimeline(BaseModel):
    project: DraftProject = Field(default_factory=DraftProject)
    settings: dict[str, Any] = Field(default_factory=dict)
    tracks: list[DraftTrack]
    scenes: list[DraftScene]

