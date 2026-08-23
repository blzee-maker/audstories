"""Narrative Plan — final assembly and serialization.

Combines validated structure, signals, and interpretation for each scene
into the top-level Narrative Plan JSON.
"""

from __future__ import annotations

import json
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

from story_processing.validation.schema import NarrativePlan, Scene


def assemble(scenes_data: list[dict[str, Any]]) -> dict[str, Any]:
    """Assemble a Narrative Plan dict from a list of per-scene dicts.

    Each item in *scenes_data* must contain keys:
    ``"scene_id"``, ``"structure"``, ``"signals"``, ``"interpretation"``.

    Returns a Python dict conforming to :class:`NarrativePlan`.
    """
    scenes: list[dict[str, Any]] = []
    for sd in scenes_data:
        scene = {
            "scene_id": sd["scene_id"],
            "structure": sd["structure"],
            "signals": sd["signals"],
            "interpretation": sd["interpretation"],
        }
        scenes.append(scene)

    plan_dict: dict[str, Any] = {
        "schema_version": "1.0",
        "scenes": scenes,
    }

    # Validate through Pydantic to guarantee correctness
    plan = NarrativePlan(**plan_dict)
    return plan.model_dump()


def serialize(plan: dict[str, Any]) -> bytes:
    """Serialize a Narrative Plan dict to pretty-printed JSON bytes.

    Uses ``orjson`` for performance.
    """
    return orjson.dumps(plan, option=orjson.OPT_INDENT_2)
