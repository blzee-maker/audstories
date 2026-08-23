"""SFX resolver."""

from __future__ import annotations

from asset_engine.contracts.requirements_models import AssetRequirement, ResolvedAsset
from asset_engine.resolvers.catalog import AssetCatalog
from asset_engine.timing.duration_probe import probe_duration_seconds


def resolve_sfx_requirement(req: AssetRequirement, catalog: AssetCatalog) -> ResolvedAsset:
    descriptor = req.descriptor
    if req.semantic_role:
        descriptor = f"{descriptor} {req.semantic_role}"
    candidate = catalog.find_best("sfx", descriptor)
    if candidate is None:
        raise ValueError(f"No SFX asset found for descriptor '{descriptor}'.")
    return ResolvedAsset(
        requirement_id=req.requirement_id,
        asset_kind="sfx",
        file_path=str(candidate),
        duration=probe_duration_seconds(candidate),
        source="library",
        confidence=0.75,
    )

