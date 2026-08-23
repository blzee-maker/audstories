"""Scene rules builder — per-scene EQ tilt and ducking overrides.

Computes optional ``rules`` blocks that override global settings on a
per-scene basis.  Returns ``None`` when the scene does not need any
overrides (i.e., it can rely on global defaults).
"""

from __future__ import annotations

from typing import Any

from dsl.constants import (
    DUCK_AMOUNT_HIGH_ENERGY,
    EMOTION_TO_TILT,
    EQ_TILT_DEFAULT,
)
from dsl.schema import SceneDuckingOverride, SceneEQRules, SceneRules


# High-energy threshold for per-scene ducking override
_SCENE_HIGH_ENERGY: float = 0.8


def build_scene_rules(
    scene: dict[str, Any],
    energy: float,
    *,
    global_duck_amount: int = -6,
) -> SceneRules | None:
    """Build per-scene rule overrides.

    Parameters
    ----------
    scene:
        A single scene dict from the Narrative Plan.
    energy:
        Normalized energy (0.0–1.0) for this scene.
    global_duck_amount:
        The ducking amount used in the global settings block.
        We only emit a per-scene override if it differs.

    Returns
    -------
    :class:`SceneRules` or ``None`` if no overrides are needed.
    """
    interp = scene.get("interpretation", {})
    emotion = interp.get("primary_emotion", "neutral")

    # -- EQ tilt -------------------------------------------------------------
    tilt = EMOTION_TO_TILT.get(emotion, EQ_TILT_DEFAULT)
    eq_rules: SceneEQRules | None = None
    if tilt != "neutral":
        eq_rules = SceneEQRules(tilt=tilt)  # type: ignore[arg-type]

    # -- Ducking override ----------------------------------------------------
    ducking_override: SceneDuckingOverride | None = None
    if energy > _SCENE_HIGH_ENERGY:
        scene_duck = DUCK_AMOUNT_HIGH_ENERGY
        if scene_duck != global_duck_amount:
            ducking_override = SceneDuckingOverride(duck_amount=scene_duck)

    # Return None if nothing to override
    if eq_rules is None and ducking_override is None:
        return None

    return SceneRules(eq=eq_rules, ducking=ducking_override)
