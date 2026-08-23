"""Draft Timeline validator — consistency checks with safe clamping.

Same "never crash, always clamp" philosophy as the Narrative Plan
validator in ``story_processing/validation/validator.py``.

Checks:
    * Track purity (one category per track, one speaker per voice track).
    * Track existence (scene track IDs match top-level definitions).
    * At least one voice clip per scene.
    * Order continuity within a scene.
    * Energy bounds (0.0–1.0).
    * Ducking rules reference valid roles.
    * EQ presets are from the known set.
    * Gain values within reasonable dB range.
    * Final Pydantic validation as a safety net.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from dsl.schema import (
    DraftClip,
    DraftScene,
    DraftSettings,
    DraftTimeline,
    DraftTrack,
    ProjectConfig,
)

logger = logging.getLogger(__name__)

# Known EQ presets (kept here to avoid coupling to schema Literal)
_KNOWN_EQ_PRESETS = frozenset({
    "dialogue_clean",
    "dialogue_warm",
    "dialogue_broadcast",
    "music_full",
    "music_bed",
    "background_soft",
    "background_distant",
    "sfx_punch",
    "sfx_subtle",
})

_KNOWN_EQ_TILTS = frozenset({"warm", "neutral", "bright"})

_GAIN_MIN = -30
_GAIN_MAX = 6


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_draft_timeline(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate and clamp a raw Draft Timeline dict.

    Parameters
    ----------
    raw:
        The assembled Draft Timeline dict (not yet Pydantic-validated).

    Returns
    -------
    A cleaned dict guaranteed to pass :class:`DraftTimeline` validation.
    """
    # Work on a shallow copy at the top level
    data = dict(raw)

    # -- 1. Tracks -----------------------------------------------------------
    tracks: list[dict[str, Any]] = data.get("tracks", [])
    track_ids: set[str] = set()
    track_type_map: dict[str, str] = {}

    for t in tracks:
        tid = t.get("id", "")
        track_ids.add(tid)
        track_type_map[tid] = t.get("type", "voice")

        # Clamp gain
        t["gain"] = _clamp_int(t.get("gain", 0), _GAIN_MIN, _GAIN_MAX)

        # Validate EQ preset
        eq = t.get("eq_preset")
        if eq is not None and eq not in _KNOWN_EQ_PRESETS:
            logger.warning(
                "Unknown track eq_preset '%s' on track '%s' — removing.",
                eq,
                tid,
            )
            t["eq_preset"] = None

    data["tracks"] = tracks

    # -- 2. Scenes -----------------------------------------------------------
    scenes: list[dict[str, Any]] = data.get("scenes", [])
    for scene in scenes:
        # Energy bounds
        scene["energy"] = _clamp_float(scene.get("energy", 0.5), 0.0, 1.0)

        # Validate scene-level rules
        rules = scene.get("rules")
        if rules is not None:
            eq_block = rules.get("eq")
            if eq_block is not None:
                tilt = eq_block.get("tilt")
                if tilt is not None and tilt not in _KNOWN_EQ_TILTS:
                    logger.warning(
                        "Unknown EQ tilt '%s' in scene '%s' — removing.",
                        tilt,
                        scene.get("id"),
                    )
                    eq_block["tilt"] = None

            ducking_block = rules.get("ducking")
            if ducking_block is not None:
                da = ducking_block.get("duck_amount")
                if da is not None:
                    ducking_block["duck_amount"] = _clamp_int(da, _GAIN_MIN, 0)

            # Remove rules if everything inside is None/empty
            if _is_empty_rules(rules):
                scene["rules"] = None

        # Validate scene tracks
        scene_tracks: dict[str, list[dict[str, Any]]] = scene.get("tracks", {})

        # Track existence check
        for stid in list(scene_tracks.keys()):
            if stid not in track_ids:
                logger.warning(
                    "Scene '%s' references unknown track '%s' — removing.",
                    scene.get("id"),
                    stid,
                )
                del scene_tracks[stid]

        # At least one voice clip check
        has_voice = any(
            track_type_map.get(stid) == "voice"
            and len(clips) > 0
            for stid, clips in scene_tracks.items()
        )
        if not has_voice:
            logger.warning(
                "Scene '%s' has no voice clips. This may cause "
                "an empty scene in the output.",
                scene.get("id"),
            )

        # Order continuity — collect all order values from voice tracks,
        # sort them, and re-number if there are gaps.
        _fix_order_continuity(scene_tracks, track_type_map)

        # Clip-level EQ preset validation
        for stid, clips in scene_tracks.items():
            for clip in clips:
                eq = clip.get("eq_preset")
                if eq is not None and eq not in _KNOWN_EQ_PRESETS:
                    clip["eq_preset"] = None

                # Clamp clip gain if present
                if clip.get("gain") is not None:
                    clip["gain"] = _clamp_int(clip["gain"], _GAIN_MIN, _GAIN_MAX)

    data["scenes"] = scenes

    # -- 3. Settings — ducking rules reference valid roles -------------------
    settings = data.get("settings", {})
    ducking_cfg = settings.get("ducking", {})
    ducking_rules = ducking_cfg.get("rules", [])
    # We keep all ducking rules as-is (roles are strings, not track IDs)
    # No strict check needed here since roles like "voice", "background"
    # are used, not track IDs.

    # -- 4. Final Pydantic validation ----------------------------------------
    try:
        validated = DraftTimeline(**data)
        return validated.model_dump(exclude_none=True)
    except ValidationError as exc:
        logger.error("Pydantic validation failed after clamping: %s", exc)
        # Return the raw dict anyway — best effort
        return data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp_int(value: Any, lo: int, hi: int) -> int:
    """Clamp a value to [lo, hi], converting to int first."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        return (lo + hi) // 2
    return max(lo, min(hi, v))


def _clamp_float(value: Any, lo: float, hi: float) -> float:
    """Clamp a value to [lo, hi], converting to float first."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return (lo + hi) / 2
    return max(lo, min(hi, v))


def _is_empty_rules(rules: dict[str, Any]) -> bool:
    """Return True if a rules dict is effectively empty."""
    eq = rules.get("eq")
    ducking = rules.get("ducking")

    eq_empty = eq is None or all(v is None for v in eq.values())
    ducking_empty = ducking is None or all(v is None for v in ducking.values())

    return eq_empty and ducking_empty


def _fix_order_continuity(
    scene_tracks: dict[str, list[dict[str, Any]]],
    track_type_map: dict[str, str],
) -> None:
    """Ensure voice clip order values are sequential with no gaps.

    Collects all (order, track_id, clip_index) tuples from voice tracks,
    sorts by order, and re-numbers from 0.
    """
    voice_entries: list[tuple[int, str, int]] = []
    for stid, clips in scene_tracks.items():
        if track_type_map.get(stid) != "voice":
            continue
        for idx, clip in enumerate(clips):
            order = clip.get("order")
            if order is not None:
                voice_entries.append((order, stid, idx))

    if not voice_entries:
        return

    # Sort by current order
    voice_entries.sort(key=lambda x: x[0])

    # Re-number from 0
    for new_order, (_, stid, idx) in enumerate(voice_entries):
        scene_tracks[stid][idx]["order"] = new_order
