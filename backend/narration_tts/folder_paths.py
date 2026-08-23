"""Resolve scaffold voice folders matching asset_engine.scaffold.builder."""

from __future__ import annotations

from pathlib import Path

from asset_engine.contracts.requirements_models import AssetRequirement
from asset_engine.utils.path_utils import make_voice_folder_name, resolve_asset_folder


def voice_clip_asset_dir(library_root: Path, req: AssetRequirement) -> Path:
    """Return the voice subfolder path for a requirement (same layout as scaffold)."""
    scene_name = req.scene_name or req.scene_id
    scene_folder = make_voice_folder_name(req.scene_index, scene_name, req.track_id)
    folder_name = f"{scene_folder}/clip_{req.clip_index:03d}"
    return resolve_asset_folder(library_root, "voice", folder_name)
