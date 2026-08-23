"""Build a resolution manifest."""

from __future__ import annotations

from datetime import datetime, timezone

from asset_engine.contracts.manifest_models import AssetManifest, ManifestAsset, ManifestSummary
from asset_engine.contracts.requirements_models import AssetRequirement, ResolutionStatus
from asset_engine.utils.constants import CONFIDENCE_EXACT, CONFIDENCE_FALLBACK, CONFIDENCE_MISSING


def _confidence_for_requirement(req: AssetRequirement) -> tuple[float, str]:
    if req.resolution_status in {ResolutionStatus.SKIPPED, ResolutionStatus.PLACEHOLDER}:
        return CONFIDENCE_MISSING, req.resolution_note or "policy fallback"
    if req.resolution_status == ResolutionStatus.MISSING:
        return CONFIDENCE_MISSING, req.resolution_note or "missing"

    confidence = float((req.metadata or {}).get("confidence", CONFIDENCE_EXACT))
    if confidence >= CONFIDENCE_EXACT:
        return CONFIDENCE_EXACT, req.resolution_note or "exact match"
    if confidence >= CONFIDENCE_FALLBACK:
        return CONFIDENCE_FALLBACK, req.resolution_note or "fallback match"
    return CONFIDENCE_MISSING, req.resolution_note or "unresolved"


def build_manifest(requirements: list[AssetRequirement], project_name: str) -> AssetManifest:
    assets: list[ManifestAsset] = []
    resolved = 0
    missing = 0
    skipped = 0

    for req in sorted(requirements, key=lambda item: item.requirement_id):
        confidence, note = _confidence_for_requirement(req)
        status = req.resolution_status.value
        if status == ResolutionStatus.RESOLVED.value:
            resolved += 1
        elif status == ResolutionStatus.SKIPPED.value:
            skipped += 1
            missing += 1
        elif status == ResolutionStatus.PLACEHOLDER.value:
            missing += 1
        else:
            missing += 1

        metadata = dict(req.metadata or {})
        details = metadata.get("details")
        assets.append(
            ManifestAsset(
                clip_id=req.clip_id,
                scene_id=req.scene_id,
                track=req.track_id,
                descriptor=req.descriptor,
                file=req.resolved_file,
                confidence=confidence,
                confidence_note=note,
                resolution_status=status,
                source=str(metadata.get("source")) if metadata.get("source") else None,
                score=float(metadata.get("score")) if metadata.get("score") is not None else None,
                resolution_details=details if isinstance(details, dict) else None,
            )
        )

    summary = ManifestSummary(
        total=len(requirements),
        resolved=resolved,
        missing=missing,
        skipped=skipped,
    )
    return AssetManifest(
        project=project_name,
        generated_at=datetime.now(timezone.utc),
        summary=summary,
        assets=assets,
    )
