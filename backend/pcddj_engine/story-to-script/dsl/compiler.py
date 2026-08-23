"""DSL Compiler — orchestrates the Narrative Plan → Draft Timeline transformation.

Public API:
    ``compile_timeline(narrative_plan) -> dict``
    ``compile_timeline_json(narrative_plan) -> bytes``
"""

from __future__ import annotations

import json
import logging
from typing import Any

try:
    import orjson  # type: ignore[import-not-found]
except ImportError:
    class _OrjsonFallback:
        OPT_INDENT_2 = None

        @staticmethod
        def dumps(value, option=None):  # noqa: ARG004
            return json.dumps(value, indent=2, ensure_ascii=False).encode("utf-8")

    orjson = _OrjsonFallback()

from dsl.builders.clips import (
    build_ambience_clips,
    build_music_clips,
    build_sfx_clips,
    build_voice_clips,
)
from dsl.builders.scene_rules import build_scene_rules
from dsl.builders.settings import build_settings
from dsl.builders.tracks import build_tracks, collect_speaker_track_map
from dsl.schema import DraftTrack, ProjectConfig
from dsl.validator import validate_draft_timeline

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compile_timeline(
    narrative_plan: dict[str, Any],
    *,
    project_type: str = "audio_drama",
    narration_only: bool = False,
    source_text_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile a Narrative Plan into a Draft Timeline dict.

    Parameters
    ----------
    narrative_plan:
        A Narrative Plan dict as produced by
        ``story_processing.pipeline.process_story()``.
    project_type:
        ``"audiobook"`` or ``"audio_drama"``.
    narration_only:
        If ``True`` (only meaningful for ``audiobook``), compile voice
        clips only — no music, ambience, or SFX in the draft.
    source_text_metrics:
        Optional metrics merged into ``settings`` (character/word counts,
        heuristic narration duration) for narration-only audiobook.

    Returns
    -------
    dict — Draft Timeline conforming to :class:`DraftTimeline` schema.
    """
    scenes = narrative_plan.get("scenes", [])
    if not scenes:
        logger.warning("Narrative Plan has no scenes — producing empty timeline.")

    # -- 1. Pre-scan ---------------------------------------------------------
    speaker_track_map = collect_speaker_track_map(narrative_plan)

    effective_narration_only = bool(
        narration_only and project_type == "audiobook",
    )

    # -- 2. Build top-level track definitions --------------------------------
    track_defs: list[DraftTrack] = build_tracks(
        narrative_plan,
        project_type=project_type,
        narration_only=effective_narration_only,
    )
    track_ids = {t.id for t in track_defs}
    has_sfx_track = "sfx" in track_ids

    # -- 3. Build global settings --------------------------------------------
    settings = build_settings(narrative_plan, has_sfx_track=has_sfx_track)
    settings.project_type = project_type  # type: ignore[assignment]
    settings.narration_only = effective_narration_only  # type: ignore[assignment]
    if source_text_metrics:
        for key in (
            "source_character_count",
            "source_word_count",
            "estimated_narration_seconds",
        ):
            if key in source_text_metrics and source_text_metrics[key] is not None:
                setattr(settings, key, source_text_metrics[key])
    global_duck_amount = settings.ducking.duck_amount

    # -- 4. Build scenes -----------------------------------------------------
    total_scenes = len(scenes)
    timeline_scenes: list[dict[str, Any]] = []

    for scene_idx, scene in enumerate(scenes):
        interp = scene.get("interpretation", {})
        energy_raw = interp.get("energy_level", 5)
        energy = round(energy_raw / 10.0, 2)  # normalize 1-10 → 0.0-1.0

        scene_id = scene.get("scene_id", f"scene_{scene_idx:03d}")
        scene_title = scene.get("structure", {}).get("scene_title")
        scene_name = scene_title or f"Scene {scene_idx + 1}"

        # 4a. Voice clips (narration + per-character dialogue)
        all_clips: dict[str, list[dict[str, Any]]] = {}

        voice_clips = build_voice_clips(
            scene, speaker_track_map, project_type=project_type,
        )
        for tid, clips in voice_clips.items():
            all_clips[tid] = [c.model_dump(exclude_none=True) for c in clips]

        # 4b. Music clips — intro/outro only (skipped for narration-only audiobook)
        music_clips: dict[str, list[Any]] = {}
        if not effective_narration_only:
            if total_scenes == 0:
                pass
            elif total_scenes == 1:
                pos = "intro" if project_type == "audiobook" else "background"
                music_clips = build_music_clips(scene, energy, position=pos)
            else:
                if scene_idx == 0:
                    music_clips = build_music_clips(scene, energy, position="intro")
                elif scene_idx == total_scenes - 1:
                    music_clips = build_music_clips(scene, energy, position="outro")

            for tid, clips in music_clips.items():
                all_clips[tid] = [c.model_dump(exclude_none=True) for c in clips]

            # 4c. Ambience clips
            ambience_clips = build_ambience_clips(scene)
            for tid, clips in ambience_clips.items():
                all_clips[tid] = [c.model_dump(exclude_none=True) for c in clips]

        # 4d. SFX clips (voice_clips passed for temporal anchoring)
        sfx_clips = build_sfx_clips(
            scene, energy, has_sfx_track,
            voice_clips=voice_clips,
            project_type=project_type,
        )
        for tid, clips in sfx_clips.items():
            all_clips[tid] = [c.model_dump(exclude_none=True) for c in clips]

        # 4e. Filter out track IDs that have no clips
        all_clips = {k: v for k, v in all_clips.items() if v}

        # 4f. Scene rules
        rules = build_scene_rules(
            scene,
            energy,
            global_duck_amount=global_duck_amount,
        )

        scene_dict: dict[str, Any] = {
            "id": scene_id,
            "name": scene_name,
            "energy": energy,
            "tracks": all_clips,
        }

        if rules is not None:
            scene_dict["rules"] = rules.model_dump(exclude_none=True)

        timeline_scenes.append(scene_dict)

    # -- 5. Assemble project config ------------------------------------------
    project = ProjectConfig()

    # -- 6. Assemble full draft timeline -------------------------------------
    raw_timeline: dict[str, Any] = {
        "project": project.model_dump(),
        "settings": settings.model_dump(),
        "tracks": [t.model_dump(exclude_none=True) for t in track_defs],
        "scenes": timeline_scenes,
    }

    # -- 7. Validate ---------------------------------------------------------
    validated = validate_draft_timeline(raw_timeline)

    logger.info(
        "Draft Timeline compiled: %d tracks, %d scenes.",
        len(validated.get("tracks", [])),
        len(validated.get("scenes", [])),
    )

    return validated


def compile_timeline_json(
    narrative_plan: dict[str, Any],
    *,
    project_type: str = "audio_drama",
    narration_only: bool = False,
    source_text_metrics: dict[str, Any] | None = None,
) -> bytes:
    """Like :func:`compile_timeline` but returns serialized JSON bytes.

    Uses ``orjson`` for performance with pretty-printing enabled.
    """
    timeline = compile_timeline(
        narrative_plan,
        project_type=project_type,
        narration_only=narration_only,
        source_text_metrics=source_text_metrics,
    )
    return orjson.dumps(timeline, option=orjson.OPT_INDENT_2)
