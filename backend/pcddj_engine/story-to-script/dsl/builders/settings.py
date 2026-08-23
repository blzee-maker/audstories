"""Settings builder — computes the global ``settings`` block.

The settings block includes ducking configuration, dialogue compression,
scene crossfade, and loudness normalization.  Values are derived from
overall story characteristics (average energy, dominant scene style).
"""

from __future__ import annotations

from typing import Any

from dsl.constants import (
    DIALOGUE_DRIVEN_MAJORITY,
    DUCK_AMOUNT_DEFAULT,
    DUCK_AMOUNT_DIALOGUE_DRIVEN,
    DUCK_AMOUNT_HIGH_ENERGY,
    HIGH_ENERGY_THRESHOLD,
    SILENCE_TO_CROSSFADE,
)
from dsl.schema import (
    DialogueCompression,
    DraftSettings,
    DuckingConfig,
    DuckingRule,
    LoudnessConfig,
    SceneCrossfade,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _compute_avg_energy(scenes: list[dict[str, Any]]) -> float:
    """Return the average energy across all scenes (0.0–1.0)."""
    if not scenes:
        return 0.5
    total = sum(
        s.get("interpretation", {}).get("energy_level", 5) / 10.0
        for s in scenes
    )
    return total / len(scenes)


def _dominant_style(scenes: list[dict[str, Any]]) -> str:
    """Return the most common ``scene_style`` across all scenes."""
    counts: dict[str, int] = {}
    for s in scenes:
        style = s.get("interpretation", {}).get("scene_style", "balanced")
        counts[style] = counts.get(style, 0) + 1
    if not counts:
        return "balanced"
    return max(counts, key=counts.get)  # type: ignore[arg-type]


def _dialogue_driven_fraction(scenes: list[dict[str, Any]]) -> float:
    """Fraction of scenes classified as ``dialogue_driven``."""
    if not scenes:
        return 0.0
    count = sum(
        1
        for s in scenes
        if s.get("interpretation", {}).get("scene_style") == "dialogue_driven"
    )
    return count / len(scenes)


def _dominant_silence_intent(scenes: list[dict[str, Any]]) -> str:
    """Return the most common ``silence_intent`` across scenes."""
    counts: dict[str, int] = {}
    for s in scenes:
        intent = s.get("interpretation", {}).get("silence_intent", "none")
        counts[intent] = counts.get(intent, 0) + 1
    if not counts:
        return "none"
    return max(counts, key=counts.get)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_settings(
    narrative_plan: dict[str, Any],
    *,
    has_sfx_track: bool = False,
) -> DraftSettings:
    """Build the global settings block for a Draft Timeline.

    Parameters
    ----------
    narrative_plan:
        Full Narrative Plan dict.
    has_sfx_track:
        Whether the project includes an SFX track (affects ducking rules).
    """
    scenes = narrative_plan.get("scenes", [])
    avg_energy = _compute_avg_energy(scenes)
    dd_fraction = _dialogue_driven_fraction(scenes)
    dom_silence = _dominant_silence_intent(scenes)

    # -- Ducking -------------------------------------------------------------
    # Base duck amount adjusted by story characteristics
    if avg_energy > HIGH_ENERGY_THRESHOLD:
        duck_amount = DUCK_AMOUNT_HIGH_ENERGY
    elif dd_fraction >= DIALOGUE_DRIVEN_MAJORITY:
        duck_amount = DUCK_AMOUNT_DIALOGUE_DRIVEN
    else:
        duck_amount = DUCK_AMOUNT_DEFAULT

    ducking_rules: list[DuckingRule] = [
        DuckingRule(when="voice", duck=["background"]),
        DuckingRule(when="voice", duck=["music"]),
    ]

    # If SFX ambience exists, voice should duck it too
    if has_sfx_track:
        ducking_rules.append(
            DuckingRule(when="voice", duck=["sfx:ambience"]),
        )
        # High-energy stories: impact SFX can duck music
        if avg_energy > HIGH_ENERGY_THRESHOLD:
            ducking_rules.append(
                DuckingRule(when="sfx:impact", duck=["music", "background"]),
            )

    ducking = DuckingConfig(
        enabled=True,
        mode="audacity",
        duck_amount=duck_amount,
        fade_down_ms=500,
        fade_up_ms=500,
        min_pause_ms=300,
        onset_delay_ms=120,
        rules=ducking_rules,
    )

    # -- Dialogue compression (static defaults) ------------------------------
    compression = DialogueCompression(
        enabled=True,
        threshold=-22,
        ratio=2.5,
        attack_ms=20,
        release_ms=180,
        makeup_gain=1,
    )

    # -- Scene crossfade -----------------------------------------------------
    if len(scenes) > 1:
        crossfade_duration = SILENCE_TO_CROSSFADE.get(dom_silence, 1.5)
        crossfade = SceneCrossfade(enabled=True, duration=crossfade_duration)
    else:
        crossfade = SceneCrossfade(enabled=False)

    # -- Loudness (static default) -------------------------------------------
    loudness = LoudnessConfig(enabled=True, target_lufs=-20.0)

    return DraftSettings(
        default_silence=0.5,
        normalize=True,
        master_gain=0,
        ducking=ducking,
        dialogue_compression=compression,
        scene_crossfade=crossfade,
        loudness=loudness,
    )
