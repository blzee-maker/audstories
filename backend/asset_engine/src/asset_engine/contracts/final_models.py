"""Output contract models for audio-engine-compatible timelines."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

TrackType = Literal["voice", "music", "sfx", "ambience"]
TrackRole = Literal["voice", "foreground", "background"]


class FinalClip(BaseModel):
    file: str
    offset: float = Field(default=0.0, ge=0.0)
    start: float | None = Field(default=None, ge=0.0)
    loop: bool | None = None
    loop_until: float | None = Field(default=None, ge=0.0)
    gain: int | None = None
    eq_preset: str | None = None
    semantic_role: str | None = None
    fade_in: float | dict[str, Any] | None = None
    fade_out: float | dict[str, Any] | None = None


class FinalTrack(BaseModel):
    id: str
    type: TrackType
    role: TrackRole
    gain: int = 0
    eq_preset: str | None = None
    semantic_role: str | None = None
    clips: list[FinalClip] = Field(default_factory=list)


class FinalScene(BaseModel):
    id: str
    name: str
    start: float = Field(ge=0.0)
    duration: float = Field(gt=0.0)
    energy: float = Field(ge=0.0, le=1.0)
    rules: dict[str, Any] | None = None
    tracks: dict[str, list[FinalClip]]


class FinalProject(BaseModel):
    name: str
    duration: float = Field(gt=0.0)
    sample_rate: int
    bit_depth: int


class FinalTimeline(BaseModel):
    project: FinalProject
    settings: dict[str, Any]
    tracks: list[FinalTrack]
    scenes: list[FinalScene]

