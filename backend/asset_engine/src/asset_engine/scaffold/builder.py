"""Scaffold folder generation from extracted requirements."""

from __future__ import annotations

import logging
import math
from pathlib import Path

from asset_engine.contracts.requirements_models import (
    AssetRequirement,
    ScaffoldResult,
    TrackType,
)
from asset_engine.scaffold.docs_writer import write_requirements_md
from asset_engine.utils.path_utils import (
    make_asset_folder_name,
    make_voice_folder_name,
    resolve_asset_folder,
)

logger = logging.getLogger(__name__)


def _voice_folder_name(req: AssetRequirement) -> str:
    scene_folder = make_voice_folder_name(req.scene_index, req.scene_name, req.track_id)
    return f"{scene_folder}/clip_{req.clip_index:03d}"


def _non_voice_folder_name(req: AssetRequirement) -> str:
    if req.position and req.asset_kind in ("music", TrackType.MUSIC):
        return make_asset_folder_name(
            req.scene_index, req.scene_name,
            f"{req.descriptor}_{req.position}",
        )
    return make_asset_folder_name(req.scene_index, req.scene_name, req.descriptor)


def _write_if_missing(path: Path, content: str) -> bool:
    if path.exists():
        return False
    path.write_text(content, encoding="utf-8")
    return True


def _format_voice_script(req: AssetRequirement) -> str:
    """Build a structured SCRIPT.txt with context and recording instructions."""
    text = req.tts_text or req.descriptor
    est = req.estimated_duration_seconds
    if est is not None:
        est_str = f"~{math.ceil(est)} seconds"
    else:
        est_str = "unknown"

    scene_label = req.scene_name or req.scene_id
    clip_label = f"clip_{req.clip_index:03d}"

    return (
        "============================================================\n"
        "VOICE CLIP REQUIRED\n"
        "============================================================\n"
        "\n"
        f"Scene     : {scene_label}\n"
        f"Speaker   : {req.track_id}\n"
        f"Clip      : {clip_label}\n"
        "\n"
        "Line to record:\n"
        f'  "{text}"\n'
        "\n"
        "------------------------------------------------------------\n"
        "INSTRUCTIONS\n"
        "------------------------------------------------------------\n"
        "1. Record this line as a WAV file\n"
        "2. Name it anything — the resolver finds the first WAV in this folder\n"
        "3. Drop the file into this folder\n"
        "4. Run: asset-engine status to check readiness\n"
        "\n"
        f"Estimated duration: {est_str}\n"
        "============================================================\n"
    )


def build_scaffold(
    *,
    requirements: list[AssetRequirement],
    library_root: Path,
    project_name: str,
    project_type: str = "audio_drama",
) -> ScaffoldResult:
    """Create idempotent folder scaffold for all requirements."""
    logger.info("Building scaffold for %d requirements", len(requirements))
    library_root.mkdir(parents=True, exist_ok=True)

    folders_created = 0
    folders_unchanged = 0
    requirements_written = 0
    folder_map: dict[str, str] = {}

    for req in requirements:
        kind = TrackType(str(req.asset_kind)).value
        folder_name = _voice_folder_name(req) if kind == "voice" else _non_voice_folder_name(req)
        folder_path = resolve_asset_folder(library_root, kind, folder_name)
        folder_rel = folder_path.relative_to(library_root).as_posix()

        if folder_path.exists():
            folders_unchanged += 1
        else:
            folder_path.mkdir(parents=True, exist_ok=True)
            folders_created += 1

        if kind == "voice":
            wrote = _write_if_missing(
                folder_path / "SCRIPT.txt",
                _format_voice_script(req),
            )
        else:
            descriptor_lines = [
                f"Descriptor: {req.descriptor}",
                f"Scene: {req.scene_name or req.scene_id}",
            ]
            if req.energy_hint is not None:
                descriptor_lines.append(f"Energy: {req.energy_hint}")
            if req.semantic_role:
                descriptor_lines.append(f"Semantic Role: {req.semantic_role}")
            if req.position:
                descriptor_lines.append(f"Position: {req.position}")
                _POSITION_HINTS = {
                    "intro": "Opening music. Should fade in from silence. Plays at the start of the production.",
                    "outro": "Closing music. Should fade out to silence. Plays at the end of the production.",
                    "background": "Background music. Plays continuously under the scene. Should be loopable.",
                }
                hint = _POSITION_HINTS.get(req.position)
                if hint:
                    descriptor_lines.append(f"Instructions: {hint}")
            wrote = _write_if_missing(folder_path / "DESCRIPTOR.txt", "\n".join(descriptor_lines))
        if wrote:
            requirements_written += 1
        folder_map[req.requirement_id] = folder_rel

    write_requirements_md(
        requirements=requirements,
        project_name=project_name,
        project_type=project_type,
        output_path=library_root / "REQUIREMENTS.md",
        folder_map=folder_map,
    )
    logger.info(
        "Scaffold complete: created=%d unchanged=%d docs_written=%d root=%s",
        folders_created,
        folders_unchanged,
        requirements_written,
        library_root,
    )

    return ScaffoldResult(
        folders_created=folders_created,
        folders_unchanged=folders_unchanged,
        requirements_written=requirements_written,
        root_path=str(library_root),
    )
