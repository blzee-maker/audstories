"""Voice offset scheduling based on scene-global order."""

from __future__ import annotations

from collections import defaultdict

from asset_engine.contracts.requirements_models import AssetRequirement, ResolvedAsset


def _pre_silence(req: AssetRequirement) -> float:
    return max(0.0, float(getattr(req, "pre_silence_s", 0.0) or 0.0))


def _post_silence(req: AssetRequirement) -> float:
    return max(0.0, float(getattr(req, "post_silence_s", 0.0) or 0.0))


def compute_voice_offsets(
    requirements: list[AssetRequirement],
    resolved_map: dict[str, ResolvedAsset],
    *,
    default_silence: float,
) -> tuple[dict[str, float], dict[str, float]]:
    """Return (offset_by_requirement_id, voice_end_by_scene_id)."""
    grouped: dict[str, list[AssetRequirement]] = defaultdict(list)
    for req in requirements:
        if req.asset_kind == "voice":
            grouped[req.scene_id].append(req)

    offsets: dict[str, float] = {}
    scene_voice_end: dict[str, float] = {}

    for scene_id, scene_reqs in grouped.items():
        scene_reqs.sort(key=lambda r: ((r.order if r.order is not None else 10_000), r.clip_index))
        previous_voice_end = 0.0
        for req in scene_reqs:
            gap = req.gap_ms / 1000.0 if req.gap_ms else default_silence
            pre = _pre_silence(req)
            post = _post_silence(req)
            gap_component = 0.0 if pre > 0 else gap
            intent = req.timing_intent or "after_previous_voice"
            if intent in {"scene_start", "with_scene_start"}:
                offset = pre
            else:
                offset = previous_voice_end + pre + gap_component
            offsets[req.requirement_id] = offset
            duration = resolved_map[req.requirement_id].duration
            previous_voice_end = offset + duration + post
        scene_voice_end[scene_id] = max(0.0, previous_voice_end)

    return offsets, scene_voice_end
