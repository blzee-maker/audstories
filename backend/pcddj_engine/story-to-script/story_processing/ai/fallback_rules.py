"""Fallback rules — pure heuristic classification (no LLM).

This module is the deterministic safety net.  It converts raw numeric
signals into discrete classification labels using only rule-based logic.

All tunable weights and thresholds live in :class:`HeuristicConfig`.
Genre-specific presets (``THRILLER_CONFIG``, ``LITERARY_CONFIG``) are
exported for future use; the default is ``DEFAULT_CONFIG``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from story_processing.context import StoryContext

# Allowed enum values (single source of truth for heuristic path)
_EMOTIONS = (
    "anxiety", "joy", "sadness", "anger", "calm", "neutral",
    "surprise", "disgust", "love", "anticipation", "nostalgia", "confusion",
)
_SCENE_STYLES = ("dialogue_driven", "narrative_heavy", "balanced", "action_heavy")
_SILENCE_INTENTS = ("none", "short", "medium", "long")

# High-arousal emotions that contribute to energy
_HIGH_AROUSAL: frozenset[str] = frozenset({
    "anxiety", "anger", "surprise", "anticipation",
})


# ---------------------------------------------------------------------------
# Configurable heuristic parameters
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class HeuristicConfig:
    """All tunable weights and thresholds for heuristic classification.

    Create custom instances for genre-specific tuning.  The function
    :func:`classify_heuristic` uses ``DEFAULT_CONFIG`` when no config
    is supplied.
    """

    # -- Energy formula weights -----------------------------------------------
    w_punctuation: float = 2.0
    w_variance: float = 0.4
    w_action_verbs: float = 2.5
    w_arousal: float = 1.5
    w_pacing: float = 1.0
    energy_base: float = 2.5

    # -- Scene style: dialogue thresholds -------------------------------------
    narrative_heavy_max_dialogue: float = 0.1
    dialogue_driven_min_dialogue: float = 0.5

    # -- Scene style: weighted action score (not OR) --------------------------
    w_action_streak: float = 0.35
    w_action_punct: float = 0.30
    w_action_verbs_style: float = 0.35
    action_streak_cap: float = 5.0     # normalize streak to 0-1
    action_punct_cap: float = 3.0      # normalize punctuation to 0-1
    action_verb_cap: float = 0.08      # normalize verb density to 0-1
    action_score_threshold: float = 0.45

    # -- Confidence scoring ---------------------------------------------------
    confidence_min: float = 0.20
    confidence_max: float = 0.85
    confidence_gap_scale: float = 1.2
    confidence_abs_weight: float = 0.3


# ---------------------------------------------------------------------------
# Genre presets
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = HeuristicConfig()

THRILLER_CONFIG = HeuristicConfig(
    w_arousal=2.0,
    narrative_heavy_max_dialogue=0.15,
    action_verb_cap=0.06,
)

LITERARY_CONFIG = HeuristicConfig(
    w_punctuation=1.5,
    w_pacing=0.5,
    narrative_heavy_max_dialogue=0.20,
    action_score_threshold=0.55,
)


# ---------------------------------------------------------------------------
# Context influence caps (Guardrail 5)
# ---------------------------------------------------------------------------
_MAX_ENERGY_CONTEXT_SHIFT: float = 1.5
_MAX_EMOTION_CONTEXT_SHIFT: float = 0.15

# Momentum activation thresholds (Guardrail 3)
_MOMENTUM_GAP_THRESHOLD: float = 0.10
_MOMENTUM_AROUSAL_BASELINE: float = 0.5


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify_heuristic(
    signals: dict[str, Any],
    config: HeuristicConfig | None = None,
    story_context: StoryContext | None = None,
) -> dict[str, Any]:
    """Produce a classification dict from raw signals, no LLM involved.

    Parameters
    ----------
    signals:
        Merged dict of structure + semantic signals.  Expected keys
        include ``emotion_scores`` (dict[str, float]), ``dialogue_ratio``,
        ``punctuation_score``, ``sentence_length_variance``,
        ``avg_sentence_length``, ``short_sentence_streak``,
        ``sentence_count``, ``action_verb_density``, etc.
    config:
        Optional tuning knobs.  Falls back to ``DEFAULT_CONFIG``.
    story_context:
        Optional cross-scene context from :class:`StoryContextBuilder`.
        When provided, enables emotion momentum and energy adjustments.

    Returns
    -------
    dict with keys: ``primary_emotion``, ``energy_level``,
    ``emotion_intensity``, ``scene_style``, ``silence_intent``,
    ``confidence_score``.
    """
    cfg = config or DEFAULT_CONFIG

    emotion_scores: dict[str, float] = dict(signals.get("emotion_scores", {}))
    dialogue_ratio: float = signals.get("dialogue_ratio", 0.0)
    punctuation_score: float = signals.get("punctuation_score", 0.0)
    variance: float = signals.get("sentence_length_variance", 0.0)
    avg_sent_len: float = signals.get("avg_sentence_length", 10.0)
    short_streak: int = signals.get("short_sentence_streak", 0)
    sentence_count: int = signals.get("sentence_count", 1)
    action_verb_density: float = signals.get("action_verb_density", 0.0)

    # ------------------------------------------------------------------
    # Context: Emotion momentum (Guardrails 3 + 5)
    # ------------------------------------------------------------------
    if story_context is not None and emotion_scores:
        emotion_scores = _apply_emotion_momentum(
            emotion_scores, story_context,
        )

    # ------------------------------------------------------------------
    # primary_emotion — highest embedding similarity
    # ------------------------------------------------------------------
    if emotion_scores:
        sorted_emotions = sorted(
            emotion_scores.items(), key=lambda x: x[1], reverse=True,
        )
        primary_emotion = sorted_emotions[0][0]
        top_score = sorted_emotions[0][1]
        second_score = sorted_emotions[1][1] if len(sorted_emotions) > 1 else 0.0
    else:
        primary_emotion = "neutral"
        top_score = 0.0
        second_score = 0.0

    if primary_emotion not in _EMOTIONS:
        primary_emotion = "neutral"

    # ------------------------------------------------------------------
    # energy_level — multi-signal weighted sum
    # ------------------------------------------------------------------
    arousal_boost = sum(emotion_scores.get(e, 0.0) for e in _HIGH_AROUSAL)
    pacing = min(sentence_count / 15.0, 1.0)  # saturates at 15 sentences

    energy_raw = (
        cfg.w_punctuation * punctuation_score
        + cfg.w_variance * (variance ** 0.5)
        + cfg.w_action_verbs * action_verb_density * 10
        + cfg.w_arousal * arousal_boost
        + cfg.w_pacing * pacing
    )
    energy_level = int(min(10, max(1, round(energy_raw + cfg.energy_base))))

    # ------------------------------------------------------------------
    # Context: Energy adjustment (Guardrails 3 + 5)
    # ------------------------------------------------------------------
    if story_context is not None:
        energy_level = _apply_energy_adjustment(
            energy_level, story_context,
        )

    # ------------------------------------------------------------------
    # emotion_intensity — from top embedding score
    # ------------------------------------------------------------------
    intensity_raw = top_score * 10
    emotion_intensity = int(min(10, max(1, round(intensity_raw))))

    # ------------------------------------------------------------------
    # scene_style — dialogue thresholds + weighted action score
    # ------------------------------------------------------------------
    if dialogue_ratio < cfg.narrative_heavy_max_dialogue:
        # Check action score even within low-dialogue scenes
        action_score = _compute_action_score(
            short_streak, punctuation_score, action_verb_density, cfg,
        )
        if action_score >= cfg.action_score_threshold:
            scene_style = "action_heavy"
        else:
            scene_style = "narrative_heavy"
    elif dialogue_ratio > cfg.dialogue_driven_min_dialogue:
        scene_style = "dialogue_driven"
    else:
        action_score = _compute_action_score(
            short_streak, punctuation_score, action_verb_density, cfg,
        )
        if action_score >= cfg.action_score_threshold:
            scene_style = "action_heavy"
        else:
            scene_style = "balanced"

    # ------------------------------------------------------------------
    # silence_intent — from short_sentence_streak + sentence density
    # ------------------------------------------------------------------
    if short_streak >= 5:
        silence_intent = "long"
    elif short_streak >= 3:
        silence_intent = "medium"
    elif sentence_count < 5 or avg_sent_len < 6:
        silence_intent = "short"
    else:
        silence_intent = "none"

    # ------------------------------------------------------------------
    # confidence_score — continuous formula
    # ------------------------------------------------------------------
    gap = top_score - second_score
    gap_component = min(gap / cfg.confidence_gap_scale, 1.0)
    abs_component = min(top_score, 1.0)
    raw_conf = (
        (1.0 - cfg.confidence_abs_weight) * gap_component
        + cfg.confidence_abs_weight * abs_component
    )
    confidence_score = cfg.confidence_min + raw_conf * (
        cfg.confidence_max - cfg.confidence_min
    )

    return {
        "primary_emotion": primary_emotion,
        "energy_level": energy_level,
        "emotion_intensity": emotion_intensity,
        "scene_style": scene_style,
        "silence_intent": silence_intent,
        "confidence_score": round(confidence_score, 2),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compute_action_score(
    short_streak: int,
    punctuation_score: float,
    action_verb_density: float,
    cfg: HeuristicConfig,
) -> float:
    """Weighted composite action score (0.0–1.0 range).

    Prevents single-signal spikes from overclassifying scenes as
    ``action_heavy``.
    """
    streak_norm = min(short_streak / cfg.action_streak_cap, 1.0)
    punct_norm = min(punctuation_score / cfg.action_punct_cap, 1.0)
    verb_norm = min(action_verb_density / cfg.action_verb_cap, 1.0)

    return (
        cfg.w_action_streak * streak_norm
        + cfg.w_action_punct * punct_norm
        + cfg.w_action_verbs_style * verb_norm
    )


def _apply_emotion_momentum(
    emotion_scores: dict[str, float],
    ctx: StoryContext,
) -> dict[str, float]:
    """Boost the previous dominant emotion if momentum conditions are met.

    Guardrail 3: only boost when gap is tight or arousal is high.
    Guardrail 5: cap shift to ``_MAX_EMOTION_CONTEXT_SHIFT``.
    """
    # Need at least 2 prior scenes with the same dominant emotion
    prev = ctx.prev_emotions
    if len(prev) < 2 or prev[-1] != prev[-2]:
        return emotion_scores

    momentum_emotion = prev[-1]
    if momentum_emotion not in emotion_scores:
        return emotion_scores

    # Check activation conditions (Guardrail 3)
    sorted_scores = sorted(emotion_scores.values(), reverse=True)
    top = sorted_scores[0]
    runner_up = sorted_scores[1] if len(sorted_scores) > 1 else 0.0
    gap = top - runner_up

    arousal = sum(emotion_scores.get(e, 0.0) for e in _HIGH_AROUSAL)

    if gap >= _MOMENTUM_GAP_THRESHOLD and arousal <= _MOMENTUM_AROUSAL_BASELINE:
        # One emotion clearly dominates AND arousal is low — skip momentum
        return emotion_scores

    # Apply boost with hard cap (Guardrail 5)
    original = emotion_scores[momentum_emotion]
    boosted = original * 1.15
    shift = min(boosted - original, _MAX_EMOTION_CONTEXT_SHIFT)
    emotion_scores[momentum_emotion] = original + shift

    # Re-normalize: scale all scores so max ≤ 1.0
    max_score = max(emotion_scores.values()) if emotion_scores else 1.0
    if max_score > 1.0:
        for k in emotion_scores:
            emotion_scores[k] /= max_score

    # Clamp all to [0, 1]
    for k in emotion_scores:
        emotion_scores[k] = max(0.0, min(1.0, emotion_scores[k]))

    return emotion_scores


def _apply_energy_adjustment(
    energy_level: int,
    ctx: StoryContext,
) -> int:
    """Adjust energy based on story-level trends.

    Guardrail 5: total context shift capped at ``_MAX_ENERGY_CONTEXT_SHIFT``.
    """
    bonus = 0.0

    # Escalating emotion trend + back half of story → +1.0
    if ctx.emotion_trend == "escalating" and ctx.position_ratio > 0.5:
        bonus += 1.0

    # Accelerating pacing → +0.5
    if ctx.pacing_trend == "accelerating":
        bonus += 0.5

    # Hard cap (Guardrail 5)
    bonus = min(bonus, _MAX_ENERGY_CONTEXT_SHIFT)

    adjusted = int(min(10, max(1, round(energy_level + bonus))))
    return adjusted
