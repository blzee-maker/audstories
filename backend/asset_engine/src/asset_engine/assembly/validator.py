"""Validation for folder-first assembled timelines."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ValidationIssue:
    severity: str
    location: str
    message: str
    action: str


def validate_final_timeline(timeline: dict) -> list[ValidationIssue]:
    """Validate timeline consistency and file references."""
    issues: list[ValidationIssue] = []

    scenes = timeline.get("scenes", [])
    expected_start = 0.0
    for scene in scenes:
        scene_id = scene.get("id", "unknown_scene")
        scene_tracks = scene.get("tracks", {})

        # Every resolved file path must exist.
        for track_id, clips in scene_tracks.items():
            for clip in clips:
                file_path = clip.get("file")
                if file_path and not Path(file_path).exists():
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            location=f"{scene_id}.{track_id}",
                            message=f"File not found: {file_path}",
                            action="Re-run scaffold and replace missing file",
                        )
                    )

        # Scene must have voice or silence placeholder track entries.
        has_voice = any(
            track_id.startswith("narrator")
            or track_id.startswith("character_")
            or track_id == "voice"
            or track_id == "narrator"
            for track_id, clips in scene_tracks.items()
            if clips
        )
        if not has_voice:
            issues.append(
                ValidationIssue(
                    severity="error",
                    location=scene_id,
                    message="Scene has no voice clips and no silence placeholder",
                    action="Provide voice assets or ensure placeholder generation is enabled",
                )
            )

        start = float(scene.get("start", 0.0))
        if abs(start - expected_start) > 0.01:
            issues.append(
                ValidationIssue(
                    severity="error",
                    location=scene_id,
                    message=f"Scene start {start} does not match expected {expected_start}",
                    action="Re-run compute_project_timing",
                )
            )
        expected_start += float(scene.get("duration", 0.0))

        if "music" not in scene_tracks:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    location=f"{scene_id}.music",
                    message="Scene missing music clip",
                    action="Place file in scaffolded music folder or accept silence",
                )
            )
        if "ambience" not in scene_tracks:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    location=f"{scene_id}.ambience",
                    message="Scene missing ambience clip",
                    action="Place file in scaffolded ambience folder or accept silence",
                )
            )

        for track_id, clips in scene_tracks.items():
            for clip in clips:
                if clip.get("timing_source") == "estimated":
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            location=f"{scene_id}.{track_id}",
                            message="Clip uses estimated timing",
                            action="Provide actual audio for this clip",
                        )
                    )

    project_duration = float(timeline.get("project", {}).get("duration", 0.0))
    if abs(project_duration - expected_start) > 0.01:
        issues.append(
            ValidationIssue(
                severity="error",
                location="project.duration",
                message=f"Project duration {project_duration} does not match scene total {expected_start}",
                action="Re-run compute_project_duration",
            )
        )
    return issues
