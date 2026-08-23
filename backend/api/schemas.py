from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


ProjectStatus = Literal["queued", "stage1", "awaiting_assets", "stage2", "credits", "done", "failed"]
NarrationChoice = Literal["self", "ai", "voice_clone", "professional"]


class CreateProjectRequest(BaseModel):
    project_id: str = Field(..., min_length=1, max_length=128)
    unit_id: str = Field(..., min_length=1, max_length=128)
    name: str = Field(..., min_length=1, max_length=256)
    unit_name: str = Field(..., min_length=1, max_length=256)
    writer_name: str = ""
    format: Literal["book", "drama"] = "book"
    narration_choice: NarrationChoice = "self"
    ai_voice_provider: str = "google"


class CreateProjectResponse(BaseModel):
    id: str
    unit_id: str
    status: ProjectStatus
    narration_choice: NarrationChoice
    ai_voice_provider: str


class SaveStoryRequest(BaseModel):
    unit_id: str = Field(..., min_length=1, max_length=128)
    story_text: str = Field(..., min_length=1, max_length=100_000)
    unit_name: str | None = None


class ScriptPreviewRequest(BaseModel):
    story_text: str | None = Field(default=None, max_length=100_000)


class PreviewDiagnostic(BaseModel):
    line: int
    column: int
    code: str
    severity: str
    message: str


class PreviewScene(BaseModel):
    scene_index: int
    heading: str
    speakers: list[str] = Field(default_factory=list)
    sfx: list[str] = Field(default_factory=list)
    ambience: list[str] = Field(default_factory=list)
    energy_level: int = 5
    primary_emotion: str = "neutral"


class ScriptPreviewResponse(BaseModel):
    project_id: str
    diagnostics: list[PreviewDiagnostic] = Field(default_factory=list)
    scenes: list[PreviewScene] = Field(default_factory=list)


class JobResponse(BaseModel):
    job_id: str
    project_id: str
    status: ProjectStatus
    detail: str | None = None


class RequirementItem(BaseModel):
    requirement_id: str
    asset_kind: Literal["voice", "music", "ambience", "sfx"]
    descriptor: str
    tts_text: str | None = None
    scene_index: int | None = None
    clip_index: int | None = None
    folder: str
    status: Literal["missing", "ready"] = "missing"


class RequirementsResponse(BaseModel):
    project_id: str
    status: ProjectStatus
    items: list[RequirementItem]


class StatusResponse(BaseModel):
    project_id: str
    status: ProjectStatus
    active_job_id: str | None = None
    error: str | None = None


class OutputResponse(BaseModel):
    project_id: str
    status: ProjectStatus
    url: str | None
    filename: str | None = None
    duration_seconds: float | None = None


class CreditsItem(BaseModel):
    slot: Literal["opening", "ending"]
    filename: str
    available: bool
    url: str | None = None


class CreditsResponse(BaseModel):
    project_id: str
    status: ProjectStatus
    items: list[CreditsItem]

