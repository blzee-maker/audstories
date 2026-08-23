"""Deterministic pacing rules for audio drama timeline requirements."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from asset_engine.contracts.draft_models import DraftTimeline
from asset_engine.contracts.requirements_models import AssetRequirement, TrackType
from asset_engine.utils.constants import MIN_CLIP_DURATION_SECONDS

PACING_RULES: dict[tuple[str, str, str], float] = {
    ("dialogue", "scene_entry", "pre"): 0.6,
    ("dialogue", "scene_close", "post"): 4.0,
    ("dialogue", "revelation", "post"): 2.5,
    ("dialogue", "question_unanswered", "post"): 3.0,
    ("dialogue", "question", "post"): 0.8,
    ("dialogue", "rapid_exchange", "post"): 0.2,
    ("dialogue", "internal", "post"): 1.2,
    ("sfx", "any", "post"): 0.8,
    ("ambience", "scene_open", "post"): 2.0,
}

SFX_BREATH: dict[str, dict[str, float]] = {
    "impact": {"pre": 0.0, "post": 1.2},
    "transition": {"pre": 0.5, "post": 0.5},
    "ambient_in": {"pre": 0.0, "post": 2.0},
    "punctual": {"pre": 0.2, "post": 0.6},
    "bell": {"pre": 0.3, "post": 1.5},
}

SCENE_DURATION_FLOOR: dict[str, float] = {
    "opening": 8.0,
    "standard": 6.0,
    "transition": 3.0,
    "closing": 10.0,
}


def _deep_merge_dict(base: dict[str, Any], extra: Mapping[str, Any] | None) -> dict[str, Any]:
    if not extra:
        return base
    merged = dict(base)
    for key, value in extra.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dict(dict(merged[key]), value)
        else:
            merged[key] = value
    return merged


def _derive_sfx_category(req: AssetRequirement) -> str:
    if req.sfx_category:
        return str(req.sfx_category)
    role = str(req.semantic_role or "").strip().lower()
    if role in {"impact", "interaction"}:
        return "impact"
    if role in {"movement", "texture"}:
        return "transition"
    if role == "ambience":
        return "ambient_in"
    hint = str(req.sfx_hint or req.descriptor or "").lower()
    if "bell" in hint:
        return "bell"
    if any(x in hint for x in ("ring", "click", "tap", "phone")):
        return "punctual"
    return "punctual"


def _voice_duration(req: AssetRequirement) -> float:
    if req.resolved_duration_seconds is not None:
        return req.resolved_duration_seconds
    if req.estimated_duration_seconds is not None:
        return req.estimated_duration_seconds
    return MIN_CLIP_DURATION_SECONDS


def _lookup_rule(rules: dict[tuple[str, str, str], float], family: str, fn: str, side: str) -> float | None:
    return rules.get((family, fn, side))


def _classify_scene_floor(scene_idx: int, total_scenes: int, scene_voice_reqs: list[AssetRequirement], scene_energy: float) -> str:
    if scene_idx == 0:
        return "opening"
    if scene_idx == total_scenes - 1:
        return "closing"
    if len(scene_voice_reqs) <= 1 and scene_energy <= 0.35:
        return "transition"
    return "standard"


def _estimate_scene_duration(scene_voice_reqs: list[AssetRequirement], default_silence_s: float) -> float:
    if not scene_voice_reqs:
        return 0.0
    previous_end = 0.0
    last_offset = 0.0
    last_duration = 0.0
    last_post = 0.0
    sorted_reqs = sorted(
        scene_voice_reqs,
        key=lambda r: ((r.sequence if r.sequence is not None else 10_000), r.clip_index),
    )
    for req in sorted_reqs:
        gap = req.gap_ms / 1000.0 if req.gap_ms else default_silence_s
        pre = max(0.0, req.pre_silence_s)
        post = max(0.0, req.post_silence_s)
        gap_component = 0.0 if pre > 0 else gap
        intent = req.timing_intent or "after_previous_voice"
        if intent in {"scene_start", "with_scene_start"}:
            offset = pre
        else:
            offset = previous_end + pre + gap_component
        duration = _voice_duration(req)
        previous_end = offset + duration + post
        last_offset = offset
        last_duration = duration
        last_post = post
    return max(0.0, last_offset + last_duration + last_post)


def apply_pacing(
    requirements: list[AssetRequirement],
    draft: DraftTimeline,
    *,
    narrative_plan: dict[str, Any] | None = None,
    overrides: dict[str, Any] | None = None,
    gita_pacing: dict[str, Any] | None = None,
) -> list[AssetRequirement]:
    """Apply deterministic pacing defaults and scene-duration floors."""
    settings_pacing = {}
    if isinstance(draft.settings, dict):
        raw = draft.settings.get("pacing")
        if isinstance(raw, dict):
            settings_pacing = raw

    merged_cfg = _deep_merge_dict(
        {
            "rules": {f"{k[0]}::{k[1]}::{k[2]}": v for k, v in PACING_RULES.items()},
            "sfx_breath": SFX_BREATH,
            "scene_floor": SCENE_DURATION_FLOOR,
        },
        settings_pacing,
    )
    merged_cfg = _deep_merge_dict(merged_cfg, gita_pacing)

    rules: dict[tuple[str, str, str], float] = {}
    for key, value in merged_cfg.get("rules", {}).items():
        if not isinstance(key, str):
            continue
        parts = key.split("::")
        if len(parts) != 3:
            continue
        try:
            rules[(parts[0], parts[1], parts[2])] = float(value)
        except (TypeError, ValueError):
            continue

    sfx_breath = {
        category: {
            "pre": float(values.get("pre", 0.0)),
            "post": float(values.get("post", 0.0)),
        }
        for category, values in merged_cfg.get("sfx_breath", {}).items()
        if isinstance(values, Mapping)
    }

    scene_floor = {
        k: float(v)
        for k, v in merged_cfg.get("scene_floor", {}).items()
    }

    for req in requirements:
        if TrackType(str(req.asset_kind)) == TrackType.VOICE:
            fn = str(req.dramatic_function or "dialogue")
            pre_rule = _lookup_rule(rules, "dialogue", fn, "pre")
            post_rule = _lookup_rule(rules, "dialogue", fn, "post")
            if pre_rule is not None and req.pre_silence_s <= 0:
                req.pre_silence_s = max(0.0, pre_rule)
            if post_rule is not None and req.post_silence_s <= 0:
                req.post_silence_s = max(0.0, post_rule)
        elif TrackType(str(req.asset_kind)) == TrackType.SFX:
            category = _derive_sfx_category(req)
            req.sfx_category = category
            breath = sfx_breath.get(category)
            anchor = str(req.anchor_position or "under")
            if breath:
                pre_value = max(0.0, float(breath.get("pre", 0.0)))
                post_value = max(0.0, float(breath.get("post", 0.0)))
                if anchor == "before":
                    if req.pre_silence_s <= 0:
                        req.pre_silence_s = pre_value
                elif anchor == "after":
                    if req.post_silence_s <= 0:
                        req.post_silence_s = post_value
                else:
                    if req.pre_silence_s <= 0:
                        req.pre_silence_s = pre_value
                    if req.post_silence_s <= 0:
                        req.post_silence_s = post_value

    total_scenes = len(draft.scenes)
    default_silence_s = float(draft.settings.get("default_silence", 0.5))

    scene_voice_map: dict[str, list[AssetRequirement]] = {}
    for req in requirements:
        if TrackType(str(req.asset_kind)) != TrackType.VOICE:
            continue
        scene_voice_map.setdefault(req.scene_id, []).append(req)

    for idx, scene in enumerate(draft.scenes):
        scene_reqs = scene_voice_map.get(scene.id, [])
        if not scene_reqs:
            continue

        scene_kind = _classify_scene_floor(idx, total_scenes, scene_reqs, scene.energy)
        floor_s = float(scene_floor.get(scene_kind, scene_floor.get("standard", 0.0)))
        current = _estimate_scene_duration(scene_reqs, default_silence_s)
        deficit = floor_s - current
        if deficit <= 0:
            continue

        target = max(
            scene_reqs,
            key=lambda r: (
                1 if str(r.dramatic_function or "") == "revelation" else 0,
                float(r.energy_hint if r.energy_hint is not None else 0.0),
                (r.sequence if r.sequence is not None else 10_000),
            ),
        )
        target.post_silence_s = max(0.0, target.post_silence_s) + deficit

    clip_overrides = (overrides or {}).get("clips", {}) if isinstance(overrides, dict) else {}
    if isinstance(clip_overrides, Mapping):
        for req in requirements:
            payload = clip_overrides.get(req.requirement_id)
            if not isinstance(payload, Mapping):
                continue
            if payload.get("pre_silence_s") is not None:
                req.pre_silence_s = max(0.0, float(payload["pre_silence_s"]))
            if payload.get("post_silence_s") is not None:
                req.post_silence_s = max(0.0, float(payload["post_silence_s"]))

    return requirements
