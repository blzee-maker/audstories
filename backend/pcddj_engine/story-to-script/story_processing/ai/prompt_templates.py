"""Prompt templates — strict, enum-constrained classification prompts."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from story_processing.context import StoryContext

# ---------------------------------------------------------------------------
# System prompt — shared across all classification calls
# ---------------------------------------------------------------------------
SYSTEM_PROMPT: str = (
    "You are a scene classification engine. "
    "Return ONLY a valid JSON object. "
    "Do NOT include any explanation, commentary, or markdown formatting. "
    "Output raw JSON only."
)

SYSTEM_PROMPT_WITH_CONTEXT: str = (
    "You are a scene classification engine. "
    "Consider the story context to maintain emotional arc coherence across scenes. "
    "Return ONLY a valid JSON object. "
    "Do NOT include any explanation, commentary, or markdown formatting. "
    "Output raw JSON only."
)

# ---------------------------------------------------------------------------
# Classification prompt template
# ---------------------------------------------------------------------------
_CLASSIFICATION_TEMPLATE: str = """\
Given the following numeric signals extracted from a story scene, classify the scene.

SIGNALS:
{signals_json}

Return a JSON object with EXACTLY these fields:

{{
  "primary_emotion": <one of: "anxiety", "joy", "sadness", "anger", "calm", "neutral", "surprise", "disgust", "love", "anticipation", "nostalgia", "confusion">,
  "energy_level": <integer from 1 to 10>,
  "emotion_intensity": <integer from 1 to 10>,
  "scene_style": <one of: "dialogue_driven", "narrative_heavy", "balanced", "action_heavy">,
  "silence_intent": <one of: "none", "short", "medium", "long">,
  "confidence_score": <float from 0.0 to 1.0, your confidence in this classification>
}}

CONSTRAINTS:
- primary_emotion MUST be one of: "anxiety", "joy", "sadness", "anger", "calm", "neutral", "surprise", "disgust", "love", "anticipation", "nostalgia", "confusion"
- energy_level MUST be an integer between 1 and 10 inclusive
- emotion_intensity MUST be an integer between 1 and 10 inclusive
- scene_style MUST be one of: "dialogue_driven", "narrative_heavy", "balanced", "action_heavy"
- silence_intent MUST be one of: "none", "short", "medium", "long"
- confidence_score MUST be a float between 0.0 and 1.0
- Return ONLY the JSON object. No explanation. No markdown."""


def build_classification_prompt(signals: dict) -> str:
    """Build the classification prompt with the given signals dict embedded.

    Parameters
    ----------
    signals:
        A flat dict of numeric signal values (from structure_metrics
        and semantic_metrics).

    Returns
    -------
    str — the fully rendered prompt.
    """
    signals_json = json.dumps(signals, indent=2, default=str)
    return _CLASSIFICATION_TEMPLATE.format(signals_json=signals_json)


# ---------------------------------------------------------------------------
# Context-aware classification prompt (Guardrail 4: summary-level only)
# ---------------------------------------------------------------------------
_CONTEXT_BLOCK_TEMPLATE: str = """\

STORY CONTEXT (use this to maintain narrative coherence):
- Scene {scene_num} of {total} ({position} through the story)
- Previous emotions: {prev_emotions}
- Emotional trend: {emotion_trend}
- Pacing trend: {pacing_trend}
- Characters so far: {speakers}"""


def build_classification_prompt_with_context(
    signals: dict,
    story_context: StoryContext,
) -> str:
    """Build a classification prompt that includes cross-scene context.

    Guardrail 4: the context block is summary-level only (~5 lines).
    No raw score dicts, no structure metrics, no pacing numbers.

    Parameters
    ----------
    signals:
        A flat dict of numeric signal values.
    story_context:
        Cross-scene context from :class:`StoryContextBuilder`.

    Returns
    -------
    str — the fully rendered prompt with context appended.
    """
    base = build_classification_prompt(signals)

    # Format previous emotions (last 3 labels only)
    prev = story_context.prev_emotions[-3:] if story_context.prev_emotions else []
    prev_str = ", ".join(prev) if prev else "none (first scene)"

    # Format speakers
    speakers_str = (
        ", ".join(story_context.known_speakers)
        if story_context.known_speakers
        else "none identified yet"
    )

    # Position as percentage
    position_str = f"{story_context.position_ratio:.0%}"

    context_block = _CONTEXT_BLOCK_TEMPLATE.format(
        scene_num=story_context.scene_index + 1,
        total=story_context.total_scenes,
        position=position_str,
        prev_emotions=prev_str,
        emotion_trend=story_context.emotion_trend,
        pacing_trend=story_context.pacing_trend,
        speakers=speakers_str,
    )

    return base + context_block
