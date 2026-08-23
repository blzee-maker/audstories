"""Assemble final timeline from draft, resolved assets, and solved timing."""

from __future__ import annotations

from asset_engine.contracts.draft_models import DraftTimeline
from asset_engine.contracts.final_models import FinalClip, FinalScene, FinalTimeline, FinalTrack
from asset_engine.contracts.requirements_models import AssetRequirement, ResolvedAsset


def _req_map(requirements: list[AssetRequirement]) -> dict[tuple[str, str, int], AssetRequirement]:
    return {(r.scene_id, r.track_id, r.clip_index): r for r in requirements}


def assemble_final_timeline(
    draft: DraftTimeline,
    *,
    requirements: list[AssetRequirement],
    resolved_map: dict[str, ResolvedAsset],
    offset_map: dict[str, float],
    scene_start_map: dict[str, float],
    scene_duration_map: dict[str, float],
    project_duration: float,
) -> FinalTimeline:
    """Build a FinalTimeline object."""
    req_lookup = _req_map(requirements)

    final_tracks = [
        FinalTrack(
            id=t.id,
            type=t.type,
            role=t.role,
            gain=t.gain,
            eq_preset=t.eq_preset,
            semantic_role=t.semantic_role,
            clips=[],
        )
        for t in draft.tracks
    ]

    final_scenes: list[FinalScene] = []
    for scene in draft.scenes:
        scene_tracks: dict[str, list[FinalClip]] = {}
        for track_id, clips in scene.tracks.items():
            out_clips: list[FinalClip] = []
            for idx, clip in enumerate(clips):
                req = req_lookup.get((scene.id, track_id, idx))
                if req is None:
                    continue
                resolved = resolved_map[req.requirement_id]
                offset = float(offset_map.get(req.requirement_id, 0.0))

                out_clip = FinalClip(
                    file=resolved.file_path,
                    offset=offset,
                    loop=bool(clip.loop) if clip.loop is not None else None,
                    loop_until=scene_duration_map[scene.id] if clip.loop else None,
                    gain=clip.gain,
                    eq_preset=clip.eq_preset,
                    semantic_role=clip.semantic_role,
                    fade_in=clip.fade_in,
                    fade_out=clip.fade_out,
                )
                out_clips.append(out_clip)
            if out_clips:
                scene_tracks[track_id] = out_clips

        final_scenes.append(
            FinalScene(
                id=scene.id,
                name=scene.name,
                start=scene_start_map[scene.id],
                duration=scene_duration_map[scene.id],
                energy=scene.energy,
                rules=scene.rules,
                tracks=scene_tracks,
            )
        )

    return FinalTimeline(
        project={
            "name": draft.project.name,
            "duration": project_duration,
            "sample_rate": draft.project.sample_rate,
            "bit_depth": draft.project.bit_depth,
        },
        settings=draft.settings,
        tracks=final_tracks,
        scenes=final_scenes,
    )

