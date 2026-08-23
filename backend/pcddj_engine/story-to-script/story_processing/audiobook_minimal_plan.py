"""Minimal narrative plan for narration-only audiobook — no NLP, LLM, or scene segmentation.

Builds a single-scene plan with **one narrator clip for the entire chapter**
(whole chapter text as a single ``sentences`` entry), plus global character/word
counts and a heuristic narration duration estimate.
"""

from __future__ import annotations

import hashlib
from typing import Any

from story_processing.narrative_plan import assemble

# Align with asset_engine voice duration heuristic (words / second).
_NARRATION_HEURISTIC_WORDS_PER_SECOND = 2.5


def text_metrics_for_chapter(text: str) -> dict[str, Any]:
    """Return character count, word count, and heuristic narration duration (seconds)."""
    stripped = text.strip()
    words = len(stripped.split()) if stripped else 0
    chars = len(stripped)
    est_sec = round(max(words / _NARRATION_HEURISTIC_WORDS_PER_SECOND, 0.5), 2)
    return {
        "source_character_count": chars,
        "source_word_count": words,
        "estimated_narration_seconds": est_sec,
    }


def chapter_as_single_narration_block(text: str) -> list[str]:
    """Return the full chapter as a single narration string (one WAV downstream)."""
    text = text.strip()
    if not text:
        return []
    return [text]


# Back-compat for tests / callers expecting the old name.
split_into_narration_sentences = chapter_as_single_narration_block


def build_minimal_narrative_plan_dict(story_text: str) -> dict[str, Any]:
    """Return a valid Narrative Plan dict: one scene, one narrator clip (full chapter)."""
    sentences = chapter_as_single_narration_block(story_text)
    if not sentences:
        raise ValueError("Chapter text produced no narration sentences.")

    digest = hashlib.sha256(story_text.encode("utf-8")).hexdigest()[:8]
    scene_id = f"scene_000_{digest}"

    word_count = sum(len(s.split()) for s in sentences)
    sentence_count = len(sentences)
    avg_len = word_count / sentence_count if sentence_count else 0.0

    structure: dict[str, Any] = {
        "scene_id": scene_id,
        "sentence_count": sentence_count,
        "word_count": word_count,
        "sentences": sentences,
        "dialogue_turns": [],
        "speakers": [],
        "sfx_events": [],
        "ambience_cue": None,
        "narration_segments": [],
    }

    signals: dict[str, Any] = {
        "avg_sentence_length": round(avg_len, 2),
        "sentence_length_variance": 0.0,
        "short_sentence_streak": 0,
        "punctuation_score": 0.0,
        "action_verb_density": 0.0,
        "dialogue_ratio": 0.0,
        "dialogue_turn_count": 0,
        "avg_dialogue_length": 0.0,
        "emotion_scores": {"neutral": 1.0},
        "emotion_arc": [],
    }

    interpretation: dict[str, Any] = {
        "primary_emotion": "neutral",
        "energy_level": 5,
        "emotion_intensity": 5,
        "scene_style": "narrative_heavy",
        "silence_intent": "none",
        "confidence_score": 1.0,
    }

    scene = {
        "scene_id": scene_id,
        "structure": structure,
        "signals": signals,
        "interpretation": interpretation,
    }

    return assemble([scene])
