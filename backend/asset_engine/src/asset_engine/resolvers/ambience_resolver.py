"""Ambience resolver."""

from __future__ import annotations

from asset_engine.contracts.requirements_models import AssetRequirement, ResolvedAsset
from asset_engine.resolvers.catalog import AssetCatalog
from asset_engine.timing.duration_probe import probe_duration_seconds


def resolve_ambience_requirement(req: AssetRequirement, catalog: AssetCatalog) -> ResolvedAsset:
    candidate = catalog.find_best("ambience", req.descriptor)
    if candidate is None:
        raise ValueError(f"No ambience asset found for descriptor '{req.descriptor}'.")
    return ResolvedAsset(
        requirement_id=req.requirement_id,
        asset_kind="ambience",
        file_path=str(candidate),
        duration=probe_duration_seconds(candidate),
        source="library",
        confidence=0.75,
    )

