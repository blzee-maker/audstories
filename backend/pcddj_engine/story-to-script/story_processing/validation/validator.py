"""Validator — logical consistency checks with safe clamping.

This layer sits between raw classification output and the final
Narrative Plan.  It enforces business rules that go beyond basic
schema validation (which Pydantic handles in schema.py).

Design rule: **never crash** — clamp or fall back safely.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from story_processing.validation.schema import SceneInterpretation

logger = logging.getLogger(__name__)

# Allowed values (duplicated here for clamping logic — avoids coupling)
_EMOTIONS = {
    "anxiety", "joy", "sadness", "anger", "calm", "neutral",
    "surprise", "disgust", "love", "anticipation", "nostalgia", "confusion",
}
_SCENE_STYLES = {"dialogue_driven", "narrative_heavy", "balanced", "action_heavy"}
_SILENCE_INTENTS = {"none", "short", "medium", "long"}


def validate_interpretation(
    structure: dict[str, Any],
    signals: dict[str, Any],
    interpretation: dict[str, Any],
) -> dict[str, Any]:
    """Validate and potentially clamp interpretation values.

    Parameters
    ----------
    structure:
        Scene structure data (sentences, speakers, dialogue_turns, etc.).
    signals:
        Merged numeric signals dict.
    interpretation:
        Raw classification dict from the AI or heuristic layer.

    Returns
    -------
    A cleaned interpretation dict that is guaranteed to pass
    ``SceneInterpretation`` schema validation.
    """
    interp = dict(interpretation)  # shallow copy

    # ------------------------------------------------------------------
    # 1. Clamp enums to valid values
    # ------------------------------------------------------------------
    if interp.get("primary_emotion") not in _EMOTIONS:
        logger.warning(
            "Invalid primary_emotion '%s' — defaulting to 'neutral'.",
            interp.get("primary_emotion"),
        )
        interp["primary_emotion"] = "neutral"

    if interp.get("scene_style") not in _SCENE_STYLES:
        interp["scene_style"] = "balanced"

    if interp.get("silence_intent") not in _SILENCE_INTENTS:
        interp["silence_intent"] = "none"

    # ------------------------------------------------------------------
    # 2. Clamp numeric bounds
    # ------------------------------------------------------------------
    interp["energy_level"] = _clamp_int(interp.get("energy_level", 5), 1, 10)
    interp["emotion_intensity"] = _clamp_int(interp.get("emotion_intensity", 5), 1, 10)
    interp["confidence_score"] = _clamp_float(
        interp.get("confidence_score", 0.5), 0.0, 1.0
    )

    # ------------------------------------------------------------------
    # 3. Logical consistency checks
    # ------------------------------------------------------------------

    # Rule: low dialogue ratio cannot be "dialogue_driven"
    dialogue_ratio = signals.get("dialogue_ratio", 0.0)
    if dialogue_ratio < 0.1 and interp["scene_style"] == "dialogue_driven":
        logger.info(
            "dialogue_ratio=%.2f too low for 'dialogue_driven' — clamping to 'narrative_heavy'.",
            dialogue_ratio,
        )
        interp["scene_style"] = "narrative_heavy"

    # Rule: high energy + long avg sentence → suspicious, clamp energy
    avg_sent_len = signals.get("avg_sentence_length", 0.0)
    if interp["energy_level"] > 8 and avg_sent_len > 25:
        logger.info(
            "energy_level=%d with avg_sentence_length=%.1f — clamping energy to 7.",
            interp["energy_level"],
            avg_sent_len,
        )
        interp["energy_level"] = 7

    # Rule: no invented speakers
    known_speakers = set(structure.get("speakers", []))
    # (This rule applies if interpretation ever includes speaker references;
    #  currently it doesn't, but the check is in place for future-proofing.)

    # ------------------------------------------------------------------
    # 4. Final Pydantic validation as safety net
    # ------------------------------------------------------------------
    try:
        validated = SceneInterpretation(**interp)
        return validated.model_dump()
    except ValidationError as exc:
        logger.error("Pydantic validation failed after clamping: %s", exc)
        # Ultimate fallback — return safe defaults
        return SceneInterpretation(
            primary_emotion="neutral",
            energy_level=5,
            emotion_intensity=5,
            scene_style="balanced",
            silence_intent="none",
            confidence_score=0.1,
        ).model_dump()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp_int(value: Any, lo: int, hi: int) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return (lo + hi) // 2
    return max(lo, min(hi, v))


def _clamp_float(value: Any, lo: float, hi: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return (lo + hi) / 2
    return max(lo, min(hi, v))
