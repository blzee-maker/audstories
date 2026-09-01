"""Manifest models for traceability and debuggability."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ManifestSummary(BaseModel):
    total: int = Field(ge=0)
    resolved: int = Field(ge=0)
    missing: int = Field(ge=0)
    skipped: int = Field(ge=0)


class ManifestAsset(BaseModel):
    clip_id: str
    scene_id: str
    track: str
    descriptor: str
    file: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    confidence_note: str
    resolution_status: str
    source: str | None = None
    score: float | None = None
    resolution_details: dict[str, Any] | None = None


class AssetManifest(BaseModel):
    project: str
    generated_at: datetime
    summary: ManifestSummary
    assets: list[ManifestAsset]

    @field_validator("assets")
    @classmethod
    def _ensure_assets(cls, value: list[ManifestAsset]) -> list[ManifestAsset]:
        if not value:
            raise ValueError("assets list cannot be empty")
        return value
