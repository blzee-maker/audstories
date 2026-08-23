import os
import json
from typing import Dict, List

from audio_engine.utils.audio_probe import probe_duration


# Valid semantic roles for SFX
VALID_SEMANTIC_ROLES = {"impact", "movement", "ambience", "interaction", "texture"}


class ValidationError(Exception):
    """Raised when timeline validation fails."""
    pass


def validate_timeline(timeline: Dict) -> List[str]:
    errors=[]
    warnings=[]

    # Project

    project =timeline.get("project")
    if not project:
        errors.append("Missing 'Project' Section")

    duration = project.get("duration") if project else None
    if not isinstance(duration,(int,float)) or duration <=0:
        errors.append("project duration must be a positive number")

    
    # Tracks

    tracks = timeline.get("tracks")
    if not isinstance(tracks, list):
        errors.append("'tracks' must be a list")
    
    # Tracks & Clip Checks

    for track in tracks or []:
        track_id = track.get("id","UNKNOWN_TRACK")
        
        # Validate semantic_role at track level (if present)
        track_semantic_role = track.get("semantic_role")
        if track_semantic_role is not None:
            if track_semantic_role not in VALID_SEMANTIC_ROLES:
                warnings.append(
                    f"Track '{track_id}' has invalid semantic_role '{track_semantic_role}'. "
                    f"Valid roles: {', '.join(sorted(VALID_SEMANTIC_ROLES))}"
                )
        
        # Warn if SFX track doesn't have semantic_role
        track_type = track.get("type", "")
        if track_type == "sfx" and track_semantic_role is None:
            warnings.append(
                f"SFX track '{track_id}' doesn't have semantic_role. "
                f"Consider adding one: {', '.join(sorted(VALID_SEMANTIC_ROLES))}"
            )

        clips = track.get("clips")

        if not isinstance(clips, list):
            errors.append(f"Track '{track_id}' clips must be a list")
            continue

        last_end = 0.0

        for clip in clips:
            file_path = clip.get("file")
            if not file_path:
                errors.append(f"Track '{track_id}': clip missing file path")
                continue
            
            # Validate semantic_role at clip level (if present)
            clip_semantic_role = clip.get("semantic_role")
            if clip_semantic_role is not None:
                if clip_semantic_role not in VALID_SEMANTIC_ROLES:
                    warnings.append(
                        f"Clip '{file_path}' in track '{track_id}' has invalid semantic_role '{clip_semantic_role}'. "
                        f"Valid roles: {', '.join(sorted(VALID_SEMANTIC_ROLES))}"
                    )

            if not os.path.exists(file_path):
                errors.append(f"Missing audio file:{file_path}")
                continue

            try:
                clip_duration = clip.get("duration_seconds")
                if not clip_duration:
                    clip_duration = probe_duration(file_path)

            except Exception:
                errors.append(f"Unreadable audio file: {file_path}")
                continue

            start = clip.get("start", last_end)
            if start < 0:
                errors.append(f"Negative start time in '{file_path}'")

            if start > duration:
                warnings.append(
                    f"Clip '{file_path}' start after project end"
                )

            
            end = start + clip_duration

            if end > duration:
                warnings.append(
                    f"Clip '{file_path}' exceeds project duration"
                )

            
            # Overlap warning (Same Track)
            if start < last_end:
                warnings.append(
                    f"Overlap detected in track '{track_id}' at '{file_path}'"
                )

            # loop Logic 
            if clip.get("loop"):
                loop_until = clip.get("loop_until", duration)
                if loop_until <= start:
                    errors.append(
                        f"Invalid loop_until for '{file_path}'"
                    )

            last_end = max(last_end, end)

    # Validate ducking rules reference valid semantic roles
    settings = timeline.get("settings", {})
    ducking_cfg = settings.get("ducking")
    if ducking_cfg and ducking_cfg.get("enabled"):
        rules = ducking_cfg.get("rules", [])
        for rule in rules:
            when_role = rule.get("when", "")
            # Check if it's a semantic role reference (sfx:role)
            if when_role.startswith("sfx:"):
                semantic_role = when_role.split(":", 1)[1]
                if semantic_role not in VALID_SEMANTIC_ROLES:
                    warnings.append(
                        f"Ducking rule references invalid semantic role '{semantic_role}' in 'when' field. "
                        f"Valid roles: {', '.join(sorted(VALID_SEMANTIC_ROLES))}"
                    )
            
            # Check duck targets
            duck_targets = rule.get("duck", [])
            for duck_target in duck_targets:
                if duck_target.startswith("sfx:"):
                    semantic_role = duck_target.split(":", 1)[1]
                    if semantic_role not in VALID_SEMANTIC_ROLES:
                        warnings.append(
                            f"Ducking rule references invalid semantic role '{semantic_role}' in 'duck' field. "
                            f"Valid roles: {', '.join(sorted(VALID_SEMANTIC_ROLES))}"
                        )

    if errors:
        raise ValidationError(
            "Validation Faild : \n" + "\n".join(errors)
        )

    return warnings