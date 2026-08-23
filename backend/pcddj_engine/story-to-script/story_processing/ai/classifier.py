"""Classifier — controlled AI classification with retry and fallback.

Orchestrates the LLM call, handles JSON parsing failures, and delegates
to heuristic fallback when the LLM path fails.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from story_processing.ai.fallback_rules import classify_heuristic
from story_processing.ai.llm_client import LLMClient, QuotaExhaustedError, call_with_backoff
from story_processing.ai.prompt_templates import (
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_WITH_CONTEXT,
    build_classification_prompt,
    build_classification_prompt_with_context,
)

if TYPE_CHECKING:
    from story_processing.context import StoryContext

logger = logging.getLogger(__name__)

# Confidence scores assigned by classification path
_CONFIDENCE_LLM_FIRST_TRY = 0.85
_CONFIDENCE_LLM_RETRY = 0.70

# Fields the LLM must return
_REQUIRED_KEYS = frozenset({
    "primary_emotion",
    "energy_level",
    "emotion_intensity",
    "scene_style",
    "silence_intent",
    "confidence_score",
})


def classify(
    signals: dict[str, Any],
    llm_client: LLMClient | None = None,
    story_context: StoryContext | None = None,
) -> dict[str, Any]:
    """Classify a scene given its merged signals.

    Flow:
    1. If *llm_client* is provided, attempt LLM classification.
    2. On invalid JSON → retry once.
    3. On second failure (or no client) → heuristic fallback.

    The returned dict always contains ``confidence_score``.

    Parameters
    ----------
    signals:
        Merged dict of structure + semantic signals.
    llm_client:
        Optional LLM client.  When ``None``, heuristic fallback is used.
    story_context:
        Optional cross-scene context.  When provided, it enriches
        both the LLM prompt and the heuristic fallback.
    """
    if llm_client is None:
        logger.info("No LLM client provided — using heuristic fallback.")
        return classify_heuristic(signals, story_context=story_context)

    # Build prompt (with or without context)
    if story_context is not None and story_context.prev_emotions:
        prompt = build_classification_prompt_with_context(signals, story_context)
        system = SYSTEM_PROMPT_WITH_CONTEXT
    else:
        prompt = build_classification_prompt(signals)
        system = SYSTEM_PROMPT

    # --- First attempt ---
    result = _try_llm(llm_client, prompt, system=system)
    if result is not None:
        result["confidence_score"] = max(
            result.get("confidence_score", _CONFIDENCE_LLM_FIRST_TRY),
            _CONFIDENCE_LLM_FIRST_TRY,
        )
        return result

    # --- Retry ---
    logger.warning("LLM returned invalid JSON. Retrying once…")
    result = _try_llm(llm_client, prompt, system=system)
    if result is not None:
        result["confidence_score"] = _CONFIDENCE_LLM_RETRY
        return result

    # --- Fallback ---
    logger.warning("LLM retry failed. Falling back to heuristic classification.")
    return classify_heuristic(signals, story_context=story_context)


def _try_llm(
    client: LLMClient,
    prompt: str,
    *,
    system: str = SYSTEM_PROMPT,
) -> dict[str, Any] | None:
    """Attempt one LLM call and parse the response as JSON.

    Returns ``None`` if the call fails or the response is not valid JSON
    with the required keys.
    """
    try:
        raw = call_with_backoff(client, prompt, system=system)
    except QuotaExhaustedError:
        # Bubble up so the pipeline can switch to heuristic/KB mode.
        raise
    except Exception:
        logger.exception("LLM call failed after retries.")
        return None

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning("LLM response is not valid JSON: %s", raw[:200])
        return None

    if not isinstance(data, dict):
        return None

    # Verify all required keys are present
    if not _REQUIRED_KEYS.issubset(data.keys()):
        missing = _REQUIRED_KEYS - data.keys()
        logger.warning("LLM response missing keys: %s", missing)
        return None

    return data
