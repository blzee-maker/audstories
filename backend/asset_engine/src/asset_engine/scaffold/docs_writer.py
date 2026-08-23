"""Write human-readable scaffold requirement documentation."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from asset_engine.contracts.requirements_models import AssetRequirement, TrackType


def write_requirements_md(
    requirements: list[AssetRequirement],
    project_name: str,
    project_type: str,
    output_path: Path,
    folder_map: dict[str, str],
) -> None:
    """Write the scaffold REQUIREMENTS.md summary file."""
    by_type: dict[TrackType, list[AssetRequirement]] = {t: [] for t in TrackType}
    for req in requirements:
        by_type[TrackType(str(req.asset_kind))].append(req)

    lines = [
        "# Asset Requirements",
        "",
        f"**Project:** {project_name}  ",
        f"**Type:** {project_type}  ",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        "",
        "---",
        "",
        "## Summary",
        "",
        "| Asset Type | Count | Managed By |",
        "|------------|-------|------------|",
        f"| Voice | {len(by_type[TrackType.VOICE])} | You |",
        f"| Music | {len(by_type[TrackType.MUSIC])} | You |",
        f"| Ambience | {len(by_type[TrackType.AMBIENCE])} | You |",
        f"| SFX | {len(by_type[TrackType.SFX])} | You |",
        "",
        "---",
        "",
    ]

    for track_type in [TrackType.VOICE, TrackType.MUSIC, TrackType.AMBIENCE, TrackType.SFX]:
        reqs = by_type[track_type]
        if not reqs:
            continue
        lines.append(f"## {track_type.value.title()}")
        lines.append("")
        for req in reqs:
            lines.append(f"- **Clip:** `{req.clip_id}`")
            lines.append(f"- **Scene:** {req.scene_name or req.scene_id}")
            lines.append(f"- **Descriptor:** `{req.descriptor}`")
            if req.energy_hint is not None:
                lines.append(f"- **Energy:** {req.energy_hint}")
            if req.semantic_role:
                lines.append(f"- **Semantic Role:** {req.semantic_role}")
            if req.tts_text:
                lines.append(f"- **Text:** {req.tts_text}")
            lines.append(f"- **Folder:** `{folder_map.get(req.requirement_id, '')}`")
            lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
