"""Audio cue extractor — LLM-powered extraction of SFX, ambience, and narration segments.

Calls the LLM (Gemini recommended) with a sound-designer prompt,
parses the structured JSON response, validates it, and returns
typed dataclasses that flow into the Narrative Plan.

Design rule: **never crash** — return an empty ``AudioCueResult`` on
total failure so the pipeline can continue with heuristic fallbacks.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from story_processing.ai.audio_cue_prompts import (
    build_audio_cue_prompt,
    get_system_prompt,
)
from story_processing.ai.llm_client import LLMClient, QuotaExhaustedError, call_with_backoff

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class SFXEvent:
    """A single sound effect event extracted from narration."""

    source_text: str
    sfx_label: str
    sfx_description: str
    intensity: Literal["subtle", "moderate", "strong", "dramatic"]
    semantic_role: Literal["impact", "movement", "ambience", "interaction", "texture"]
    timing: Literal["instant", "short", "sustained"]
    order_hint: int = 0


@dataclass(frozen=True, slots=True)
class AmbienceCue:
    """Scene-level ambience / atmosphere descriptor."""

    primary_atmosphere: str
    atmosphere_description: str
    intensity: Literal["minimal", "subtle", "moderate", "rich"]
    evolves: bool = False


@dataclass(frozen=True, slots=True)
class NarrationSegment:
    """A classified clause from narration text."""

    text: str
    segment_type: Literal[
        "action", "description", "scene_setting", "transition", "inner_thought"
    ]
    has_sound_event: bool = False


@dataclass(slots=True)
class AudioCueResult:
    """Complete audio cue extraction result for a scene."""

    sfx_events: list[SFXEvent] = field(default_factory=list)
    ambience: AmbienceCue | None = None
    narration_segments: list[NarrationSegment] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Valid enum sets (for clamping)
# ---------------------------------------------------------------------------

_INTENSITIES = frozenset({"subtle", "moderate", "strong", "dramatic"})
_SEMANTIC_ROLES = frozenset({"impact", "movement", "ambience", "interaction", "texture"})
_TIMINGS = frozenset({"instant", "short", "sustained"})
_AMBIENCE_INTENSITIES = frozenset({"minimal", "subtle", "moderate", "rich"})
_SEGMENT_TYPES = frozenset(
    {"action", "description", "scene_setting", "transition", "inner_thought"}
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_audio_cues(
    scene_text: str,
    dialogue_turns: list[dict[str, Any]],
    llm_client: LLMClient,
    *,
    max_retries: int = 1,
    project_type: str = "audio_drama",
) -> AudioCueResult:
    """Extract audio cues from a scene using the LLM.

    Parameters
    ----------
    scene_text:
        The full text of the scene.
    dialogue_turns:
        Already-extracted dialogue turns (so the LLM skips them).
    llm_client:
        An LLM client (``GeminiClient`` recommended).
    max_retries:
        Number of retries on parse failure.
    project_type:
        ``"audiobook"`` or ``"audio_drama"``.  Audio drama mode uses
        a more aggressive extraction prompt.

    Returns
    -------
    AudioCueResult with SFX events, ambience cue, and narration segments.
    Returns an empty result on total failure (never raises).
    """
    prompt = build_audio_cue_prompt(
        scene_text, dialogue_turns, project_type=project_type,
    )
    system_prompt = get_system_prompt(project_type)

    for attempt in range(1 + max_retries):
        try:
            raw = call_with_backoff(
                llm_client, prompt, system=system_prompt,
            )
            data = json.loads(raw)
            if not isinstance(data, dict):
                logger.warning(
                    "Audio cue extraction attempt %d: expected dict, got %s.",
                    attempt + 1,
                    type(data).__name__,
                )
                continue
            return _parse_audio_cue_response(data)
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning(
                "Audio cue extraction attempt %d failed (bad JSON): %s",
                attempt + 1,
                exc,
            )
        except Exception as exc:
            if isinstance(exc, QuotaExhaustedError):
                # Let the orchestrator switch to KB/heuristic mode.
                raise
            logger.warning(
                "Audio cue extraction attempt %d failed after retries: %s",
                attempt + 1,
                exc,
            )

    logger.warning(
        "All audio cue extraction attempts failed — returning empty result."
    )
    return AudioCueResult()


# ---------------------------------------------------------------------------
# Internal parsing
# ---------------------------------------------------------------------------

def _parse_audio_cue_response(data: dict[str, Any]) -> AudioCueResult:
    """Parse and validate raw LLM JSON into an ``AudioCueResult``."""

    # --- SFX events ---
    sfx_events: list[SFXEvent] = []
    for item in data.get("sfx_events", []):
        if not isinstance(item, dict):
            continue
        sfx_events.append(
            SFXEvent(
                source_text=str(item.get("source_text", "")),
                sfx_label=str(item.get("sfx_label", "unknown_sfx")),
                sfx_description=str(item.get("sfx_description", "")),
                intensity=_clamp_enum(item.get("intensity"), _INTENSITIES, "moderate"),
                semantic_role=_clamp_enum(
                    item.get("semantic_role"), _SEMANTIC_ROLES, "impact"
                ),
                timing=_clamp_enum(item.get("timing"), _TIMINGS, "instant"),
                order_hint=_safe_int(item.get("order_hint", 0)),
            )
        )

    # --- Ambience ---
    ambience: AmbienceCue | None = None
    amb_data = data.get("ambience")
    if amb_data and isinstance(amb_data, dict):
        ambience = AmbienceCue(
            primary_atmosphere=str(
                amb_data.get("primary_atmosphere", "neutral_room")
            ),
            atmosphere_description=str(
                amb_data.get("atmosphere_description", "")
            ),
            intensity=_clamp_enum(
                amb_data.get("intensity"), _AMBIENCE_INTENSITIES, "subtle"
            ),
            evolves=bool(amb_data.get("evolves", False)),
        )

    # --- Narration segments ---
    narration_segments: list[NarrationSegment] = []
    for item in data.get("narration_segments", []):
        if not isinstance(item, dict):
            continue
        narration_segments.append(
            NarrationSegment(
                text=str(item.get("text", "")),
                segment_type=_clamp_enum(
                    item.get("segment_type"), _SEGMENT_TYPES, "description"
                ),
                has_sound_event=bool(item.get("has_sound_event", False)),
            )
        )

    return AudioCueResult(
        sfx_events=sfx_events,
        ambience=ambience,
        narration_segments=narration_segments,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp_enum(value: Any, allowed: frozenset[str], default: str) -> str:
    """Return *value* if it is in *allowed*, else return *default*."""
    if isinstance(value, str) and value in allowed:
        return value  # type: ignore[return-value]
    return default  # type: ignore[return-value]


def _safe_int(value: Any, default: int = 0) -> int:
    """Safely coerce *value* to ``int``."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
