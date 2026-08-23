"""Strict final timeline preflight checks."""

from __future__ import annotations

from pathlib import Path

from asset_engine.contracts.final_models import FinalTimeline


def validate_final_timeline(data: dict) -> list[str]:
    """Validate final timeline payload; raises ValueError on hard failures."""
    timeline = FinalTimeline(**data)
    warnings: list[str] = []
    errors: list[str] = []

    track_ids = {track.id for track in timeline.tracks}
    if not track_ids:
        errors.append("final timeline must contain at least one track")

    if timeline.project.duration <= 0:
        errors.append("project.duration must be positive")

    for scene in timeline.scenes:
        if scene.start < 0 or scene.duration <= 0:
            errors.append(f"scene '{scene.id}' has invalid start/duration")

        for track_id, clips in scene.tracks.items():
            if track_id not in track_ids:
                errors.append(f"scene '{scene.id}' references unknown track '{track_id}'")
                continue
            for clip in clips:
                if clip.offset < 0:
                    errors.append(f"clip in '{scene.id}/{track_id}' has negative offset")
                if not Path(clip.file).exists():
                    errors.append(f"missing audio file: {clip.file}")
                if clip.loop and clip.loop_until is not None and clip.loop_until <= clip.offset:
                    errors.append(
                        f"invalid loop_until in '{scene.id}/{track_id}' for file {clip.file}"
                    )
                if clip.semantic_role and clip.semantic_role not in {
                    "impact",
                    "movement",
                    "ambience",
                    "interaction",
                    "texture",
                }:
                    warnings.append(
                        f"clip semantic_role '{clip.semantic_role}' is non-standard for {clip.file}"
                    )

    if errors:
        joined = "\n".join(errors)
        raise ValueError(f"Final timeline validation failed:\n{joined}")
    return warnings

