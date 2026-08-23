"""Scene and clip timing solver."""

from __future__ import annotations

from collections import defaultdict

from asset_engine.contracts.draft_models import DraftTimeline
from asset_engine.contracts.requirements_models import AssetRequirement, ResolvedAsset
from asset_engine.timing.voice_order_scheduler import compute_voice_offsets


def compute_timing(
    draft: DraftTimeline,
    requirements: list[AssetRequirement],
    resolved_map: dict[str, ResolvedAsset],
) -> tuple[dict[str, float], dict[str, float], dict[str, float], float]:
    """Compute clip offsets, scene starts, scene durations, project duration."""
    default_silence = float(draft.settings.get("default_silence", 0.5))
    offsets, scene_voice_end = compute_voice_offsets(
        requirements, resolved_map, default_silence=default_silence
    )

    reqs_by_scene_track: dict[tuple[str, str], list[AssetRequirement]] = defaultdict(list)
    for req in requirements:
        reqs_by_scene_track[(req.scene_id, req.track_id)].append(req)

    scene_duration: dict[str, float] = {}
    for scene in draft.scenes:
        max_end = scene_voice_end.get(scene.id, 0.0)
        for track_id, clips in scene.tracks.items():
            reqs = reqs_by_scene_track.get((scene.id, track_id), [])
            reqs.sort(key=lambda r: r.clip_index)

            track_cursor = 0.0
            for req in reqs:
                if req.requirement_id not in offsets:
                    if req.loop:
                        offsets[req.requirement_id] = 0.0
                    else:
                        offsets[req.requirement_id] = track_cursor

                clip_end = offsets[req.requirement_id] + resolved_map[req.requirement_id].duration
                max_end = max(max_end, clip_end)

                if not req.loop:
                    track_cursor = clip_end + default_silence
            if not clips:
                continue
        scene_duration[scene.id] = max(1.0, max_end)

    scene_start: dict[str, float] = {}
    cursor = 0.0
    for scene in draft.scenes:
        scene_start[scene.id] = cursor
        cursor += scene_duration[scene.id]

    return offsets, scene_start, scene_duration, cursor

