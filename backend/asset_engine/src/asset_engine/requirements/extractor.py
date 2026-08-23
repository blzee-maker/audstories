"""Extract asset requirements from draft timeline descriptors."""

from __future__ import annotations

from asset_engine.contracts.draft_models import DraftTimeline, DraftTrack
from asset_engine.contracts.requirements_models import AssetRequirement, TrackType
from asset_engine.utils.constants import AVG_WORDS_PER_SECOND, MIN_CLIP_DURATION_SECONDS


def _track_type_map(tracks: list[DraftTrack]) -> dict[str, str]:
    return {track.id: track.type for track in tracks}


def estimate_voice_duration(tts_text: str) -> float:
    """Estimate voice duration from word count."""
    if not tts_text:
        return MIN_CLIP_DURATION_SECONDS
    words = len(tts_text.strip().split())
    estimated = words / AVG_WORDS_PER_SECOND
    return max(round(estimated, 2), MIN_CLIP_DURATION_SECONDS)


def _allowed_track_types(project_type: str, *, narration_only: bool = False) -> set[str]:
    """Return the track types permitted for *project_type*."""
    if narration_only:
        return {"voice"}
    if project_type == "audiobook":
        return {"voice", "music", "ambience"}
    return {"voice", "music", "ambience", "sfx"}


def extract_requirements(draft: DraftTimeline) -> list[AssetRequirement]:
    """Flatten draft scene clips into typed requirements."""
    requirements: list[AssetRequirement] = []
    track_types = _track_type_map(draft.tracks)
    default_gap_ms = int(float(draft.settings.get("default_silence", 0.5)) * 1000)
    project_type = draft.settings.get("project_type", "audio_drama")
    narration_only = bool(draft.settings.get("narration_only", False))
    allowed = _allowed_track_types(project_type, narration_only=narration_only)

    for scene_idx, scene in enumerate(draft.scenes):
        scene_voice_requirements: list[AssetRequirement] = []
        for track_id, clips in scene.tracks.items():
            track_type = track_types.get(track_id)
            if track_type is None or track_type not in allowed:
                continue

            for clip_idx, clip in enumerate(clips):
                req_id = f"{scene.id}:{track_id}:{clip_idx}"
                track_enum = TrackType(track_type)
                timing_intent = (
                    "scene_start"
                    if track_enum == TrackType.VOICE and (clip.order == 0 or clip.order is None)
                    else "after_previous_voice"
                    if track_enum == TrackType.VOICE
                    else "with_scene_start"
                )

                if track_type == "voice" and clip.tts_text:
                    req = AssetRequirement(
                        requirement_id=req_id,
                        asset_kind="voice",
                        scene_id=scene.id,
                        scene_name=scene.name,
                        scene_index=scene_idx,
                        track_id=track_id,
                        clip_index=clip_idx,
                        clip_id=f"clip_scene{scene_idx:03d}_{track_id}_{clip_idx:03d}",
                        descriptor=clip.tts_text,
                        track_type=track_enum,
                        order=clip.order,
                        tts_text=clip.tts_text,
                        sequence=clip.order,
                        timing_intent=timing_intent,
                        dramatic_function=getattr(clip, "dramatic_function", None),
                        gap_ms=default_gap_ms,
                        pre_silence_s=((clip.pre_silence_ms or 0) / 1000.0 if getattr(clip, "pre_silence_ms", None) is not None else 0.0),
                        post_silence_s=((clip.post_silence_ms or 0) / 1000.0 if getattr(clip, "post_silence_ms", None) is not None else 0.0),
                        estimated_duration_seconds=estimate_voice_duration(clip.tts_text),
                        loop=bool(clip.loop),
                        metadata=clip.model_dump(exclude_none=True),
                    )
                    requirements.append(req)
                    scene_voice_requirements.append(req)
                elif track_type == "music" and clip.mood:
                    clip_position = getattr(clip, "position", None)
                    requirements.append(
                        AssetRequirement(
                            requirement_id=req_id,
                            asset_kind="music",
                            scene_id=scene.id,
                            scene_name=scene.name,
                            scene_index=scene_idx,
                            track_id=track_id,
                            clip_index=clip_idx,
                            clip_id=f"clip_scene{scene_idx:03d}_{track_id}_{clip_idx:03d}",
                            descriptor=clip.mood,
                            track_type=track_enum,
                            mood=clip.mood,
                            timing_intent=timing_intent,
                            energy_hint=clip.energy_hint,
                            loop=bool(clip.loop),
                            position=clip_position,
                            metadata=clip.model_dump(exclude_none=True),
                        )
                    )
                elif track_type == "ambience" and clip.atmosphere:
                    requirements.append(
                        AssetRequirement(
                            requirement_id=req_id,
                            asset_kind="ambience",
                            scene_id=scene.id,
                            scene_name=scene.name,
                            scene_index=scene_idx,
                            track_id=track_id,
                            clip_index=clip_idx,
                            clip_id=f"clip_scene{scene_idx:03d}_{track_id}_{clip_idx:03d}",
                            descriptor=clip.atmosphere,
                            track_type=track_enum,
                            atmosphere=clip.atmosphere,
                            timing_intent=timing_intent,
                            loop=bool(clip.loop),
                            metadata=clip.model_dump(exclude_none=True),
                        )
                    )
                elif track_type == "sfx" and clip.sfx_hint:
                    sfx_timing = (
                        f"with_voice_{clip.anchor_order}"
                        if clip.anchor_order is not None
                        else timing_intent
                    )
                    requirements.append(
                        AssetRequirement(
                            requirement_id=req_id,
                            asset_kind="sfx",
                            scene_id=scene.id,
                            scene_name=scene.name,
                            scene_index=scene_idx,
                            track_id=track_id,
                            clip_index=clip_idx,
                            clip_id=f"clip_scene{scene_idx:03d}_{track_id}_{clip_idx:03d}",
                            descriptor=clip.sfx_hint,
                            track_type=track_enum,
                            sfx_hint=clip.sfx_hint,
                            sfx_category=getattr(clip, "sfx_category", None),
                            timing_intent=sfx_timing,
                            anchor_order=clip.anchor_order,
                            anchor_position=clip.anchor_position,
                            semantic_role=clip.semantic_role,
                            loop=bool(clip.loop),
                            metadata=clip.model_dump(exclude_none=True),
                        )
                    )

        if scene_voice_requirements:
            last_voice = max(
                scene_voice_requirements,
                key=lambda r: ((r.sequence if r.sequence is not None else 10_000), r.clip_index),
            )
            last_voice.post_silence_s = max(last_voice.post_silence_s, 2.0)

    return requirements
