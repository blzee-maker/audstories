"""Deterministic timing solver for folder-first asset flow."""

from __future__ import annotations

from asset_engine.contracts.requirements_models import (
    AssetRequirement,
    ResolutionStatus,
    TrackType,
)
from asset_engine.utils.constants import DEFAULT_SILENCE_SECONDS, MIN_CLIP_DURATION_SECONDS


def _voice_duration(req: AssetRequirement) -> float:
    if req.resolution_status == ResolutionStatus.RESOLVED and req.resolved_duration_seconds is not None:
        return req.resolved_duration_seconds
    if req.resolution_status == ResolutionStatus.PLACEHOLDER and req.estimated_duration_seconds is not None:
        return req.estimated_duration_seconds
    return req.estimated_duration_seconds or MIN_CLIP_DURATION_SECONDS


def _pre_silence(req: AssetRequirement) -> float:
    return max(0.0, float(getattr(req, "pre_silence_s", 0.0) or 0.0))


def _post_silence(req: AssetRequirement) -> float:
    return max(0.0, float(getattr(req, "post_silence_s", 0.0) or 0.0))


def compute_scene_timing(
    requirements: list[AssetRequirement],
    default_silence: float = DEFAULT_SILENCE_SECONDS,
) -> tuple[list[dict], float]:
    """Compute clip offsets for one scene and return scene duration."""
    voice_clips = sorted(
        [r for r in requirements if TrackType(str(r.asset_kind)) == TrackType.VOICE],
        key=lambda r: r.sequence if r.sequence is not None else 10_000,
    )
    non_voice = [r for r in requirements if TrackType(str(r.asset_kind)) != TrackType.VOICE]

    resolved_clips: list[dict] = []
    previous_voice_end = 0.0
    last_voice_offset = 0.0
    last_voice_duration = 0.0
    last_voice_post_silence = 0.0

    for req in voice_clips:
        gap = req.gap_ms / 1000.0 if req.gap_ms else default_silence
        intent = req.timing_intent or "after_previous_voice"
        pre = _pre_silence(req)
        post = _post_silence(req)
        gap_component = 0.0 if pre > 0 else gap

        if intent in {"scene_start", "with_scene_start"}:
            offset = pre
        elif intent == "after_previous_voice":
            offset = previous_voice_end + pre + gap_component
        else:
            offset = previous_voice_end + pre + gap_component

        duration = _voice_duration(req)
        previous_voice_end = offset + duration + post
        last_voice_offset = offset
        last_voice_duration = duration
        last_voice_post_silence = post

        resolved_clips.append(
            {
                "id": req.clip_id,
                "track": req.track_id,
                "file": req.resolved_file,
                "offset": round(offset, 3),
                "duration": round(duration, 3),
                "timing_source": (
                    "actual" if req.resolution_status == ResolutionStatus.RESOLVED else "estimated"
                ),
                "loop": req.loop,
                "semantic_role": req.semantic_role,
            }
        )

    scene_duration = (
        round(last_voice_offset + last_voice_duration + last_voice_post_silence, 3)
        if voice_clips
        else 0.0
    )

    # Build a map from voice sequence/order -> (offset, duration) for SFX anchoring
    voice_offset_map: dict[int, dict[str, float]] = {}
    for rc in resolved_clips:
        seq = None
        for vr in voice_clips:
            if vr.clip_id == rc["id"]:
                seq = vr.sequence
                break
        if seq is not None:
            voice_offset_map[seq] = {"offset": rc["offset"], "duration": rc.get("duration", 0.0)}

    for req in non_voice:
        if req.resolution_status == ResolutionStatus.SKIPPED:
            continue

        offset = 0.0
        if req.anchor_order is not None:
            anchor_voice = voice_offset_map.get(req.anchor_order)
            if anchor_voice is not None:
                pos = req.anchor_position or "under"
                if pos == "before":
                    offset = max(0.0, anchor_voice["offset"] - 0.2)
                elif pos == "after":
                    offset = anchor_voice["offset"] + anchor_voice["duration"]
                else:
                    offset = anchor_voice["offset"]

        resolved_clips.append(
            {
                "id": req.clip_id,
                "track": req.track_id,
                "file": req.resolved_file,
                "offset": round(offset, 3),
                "loop": req.loop,
                "semantic_role": req.semantic_role,
            }
        )

    return resolved_clips, scene_duration


def compute_project_timing(scenes: list[dict]) -> list[dict]:
    """Assign cumulative start times to scenes."""
    cursor = 0.0
    for scene in scenes:
        scene["start"] = round(cursor, 3)
        cursor += float(scene.get("duration", 0.0))
    return scenes


def compute_project_duration(scenes: list[dict]) -> float:
    """Return total duration for all scenes."""
    return round(sum(float(scene.get("duration", 0.0)) for scene in scenes), 3)
