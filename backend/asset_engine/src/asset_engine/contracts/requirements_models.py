"""Internal requirement and resolution models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

AssetKind = Literal["voice", "music", "ambience", "sfx"]


class TrackType(str, Enum):
    VOICE = "voice"
    MUSIC = "music"
    AMBIENCE = "ambience"
    SFX = "sfx"


class ResolutionStatus(str, Enum):
    RESOLVED = "resolved"
    MISSING = "missing"
    SKIPPED = "skipped"
    PLACEHOLDER = "placeholder"


@dataclass
class AssetRequirement:
    # Existing identity fields (kept for compatibility).
    requirement_id: str
    asset_kind: AssetKind | TrackType
    scene_id: str
    track_id: str
    clip_index: int
    descriptor: str

    # Extended identity/context.
    scene_name: str = ""
    scene_index: int = 0
    clip_id: str = ""
    track_type: TrackType | None = None

    # Existing optional fields.
    order: int | None = None
    semantic_role: str | None = None
    energy_hint: float | None = None
    loop: bool = False
    metadata: dict[str, Any] | None = None

    # Extended descriptor fields.
    mood: str | None = None
    atmosphere: str | None = None
    sfx_hint: str | None = None
    sfx_category: str | None = None

    # SFX anchor (links SFX to the voice clip it accompanies).
    anchor_order: int | None = None
    anchor_position: str | None = None

    # Music position (intro, outro, background).
    position: str | None = None

    # Voice/timing intent.
    tts_text: str | None = None
    sequence: int | None = None
    timing_intent: str | None = None
    dramatic_function: str | None = None
    gap_ms: int = 0
    pre_silence_s: float = 0.0
    post_silence_s: float = 0.0
    estimated_duration_seconds: float | None = None
    estimated_duration_confidence: str = "low"
    resolved_duration_seconds: float | None = None

    # Resolution fields used by new folder-first flow.
    resolved_file: str | None = None
    resolution_status: ResolutionStatus = ResolutionStatus.MISSING
    resolution_note: str | None = None

    def __post_init__(self) -> None:
        if self.track_type is None:
            self.track_type = TrackType(str(self.asset_kind))
        if not self.clip_id:
            self.clip_id = self.requirement_id
        if self.sequence is None:
            self.sequence = self.order


@dataclass(frozen=True)
class ResolvedAsset:
    requirement_id: str
    asset_kind: AssetKind
    file_path: str
    duration: float
    source: str
    confidence: float = 1.0
    notes: str | None = None


@dataclass
class ScaffoldResult:
    folders_created: int
    folders_unchanged: int
    requirements_written: int
    root_path: str


@dataclass
class ResolveResult:
    resolved: list[AssetRequirement] = field(default_factory=list)
    missing: list[AssetRequirement] = field(default_factory=list)
    skipped: list[AssetRequirement] = field(default_factory=list)
    placeholders: list[AssetRequirement] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return len(self.missing) == 0

    @property
    def has_warnings(self) -> bool:
        return len(self.skipped) > 0 or len(self.placeholders) > 0

