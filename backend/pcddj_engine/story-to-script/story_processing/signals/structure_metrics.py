"""Structure metrics — lexical, punctuation, and dialogue signal extraction.

All functions in this module produce *numeric facts only*.
No interpretation. No emotion inference.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Sequence

import numpy as np

if TYPE_CHECKING:
    from spacy.tokens import Doc, Span

from story_processing.nlp.dialogue_extractor import DialogueTurn


# ---------------------------------------------------------------------------
# Punctuation weights
# ---------------------------------------------------------------------------
_PUNCT_WEIGHTS: dict[str, float] = {
    "!": 1.5,
    "?": 1.2,
    "...": 1.0,
    "\u2026": 1.0,   # ellipsis character
    "--": 0.8,
    "\u2014": 0.8,   # em-dash
    "\u2013": 0.8,   # en-dash
}

_ELLIPSIS_RE = re.compile(r"\.{3}|\u2026")
_DASH_RE = re.compile(r"--|\u2014|\u2013")

# Short sentence threshold (words)
_SHORT_SENTENCE_MAX_WORDS = 5
_SHORT_STREAK_MIN = 3

# ---------------------------------------------------------------------------
# High-energy action verb lemmas (for action_verb_density)
# ---------------------------------------------------------------------------
_ACTION_VERB_LEMMAS: frozenset[str] = frozenset({
    # Physical movement
    "run", "sprint", "dash", "race", "rush", "bolt", "charge", "flee",
    "chase", "leap", "jump", "dive", "dodge", "lunge", "tackle", "climb",
    "fall", "tumble", "collapse", "stumble",
    # Combat / force
    "hit", "punch", "kick", "strike", "slam", "smash", "crash", "shatter",
    "break", "tear", "rip", "fight", "attack", "shoot", "fire", "stab",
    "swing", "whip", "throw", "grab", "pull", "push", "shove", "drag",
    # Explosive / dramatic
    "explode", "burst", "blast", "erupt", "detonate", "ignite",
    # Rapid / urgent
    "hurry", "scramble", "snatch", "seize", "wrench", "yank", "hurl",
    "plunge", "surge", "storm",
})


@dataclass(slots=True)
class StructureSignals:
    """All structure-derived numeric signals for a single scene."""

    # Lexical
    avg_sentence_length: float = 0.0
    sentence_length_variance: float = 0.0
    short_sentence_streak: int = 0
    sentence_count: int = 0
    word_count: int = 0

    # Punctuation
    punctuation_score: float = 0.0

    # Action verbs
    action_verb_density: float = 0.0

    # Dialogue
    dialogue_ratio: float = 0.0
    dialogue_turn_count: int = 0
    avg_dialogue_length: float = 0.0


def compute_structure_signals(
    sentences: Sequence[Span],
    dialogue_turns: list[DialogueTurn],
    total_text: str,
) -> StructureSignals:
    """Compute all structure signals for a scene.

    Parameters
    ----------
    sentences:
        spaCy ``Span`` objects for sentences in this scene.
    dialogue_turns:
        Extracted dialogue turns overlapping this scene.
    total_text:
        The raw text of this scene (for punctuation scanning).
    """
    sig = StructureSignals()

    # ------------------------------------------------------------------
    # Lexical signals
    # ------------------------------------------------------------------
    lengths = [len([t for t in s if not t.is_punct and not t.is_space]) for s in sentences]
    sig.sentence_count = len(lengths)
    sig.word_count = sum(lengths)

    if lengths:
        arr = np.array(lengths, dtype=np.float64)
        sig.avg_sentence_length = float(np.mean(arr))
        sig.sentence_length_variance = float(np.var(arr))
        sig.short_sentence_streak = _max_short_streak(lengths)

    # ------------------------------------------------------------------
    # Action verb density
    # ------------------------------------------------------------------
    if sig.word_count > 0:
        action_count = sum(
            1
            for s in sentences
            for t in s
            if t.pos_ == "VERB" and t.lemma_.lower() in _ACTION_VERB_LEMMAS
        )
        sig.action_verb_density = action_count / sig.word_count

    # ------------------------------------------------------------------
    # Punctuation score
    # ------------------------------------------------------------------
    sig.punctuation_score = _compute_punctuation_score(total_text, sig.sentence_count)

    # ------------------------------------------------------------------
    # Dialogue signals
    # ------------------------------------------------------------------
    sig.dialogue_turn_count = len(dialogue_turns)
    if dialogue_turns:
        dialogue_word_counts = [len(t.text.split()) for t in dialogue_turns]
        total_dialogue_words = sum(dialogue_word_counts)
        sig.dialogue_ratio = (
            total_dialogue_words / sig.word_count if sig.word_count > 0 else 0.0
        )
        sig.avg_dialogue_length = float(np.mean(dialogue_word_counts))
    else:
        sig.dialogue_ratio = 0.0
        sig.avg_dialogue_length = 0.0

    return sig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _max_short_streak(lengths: list[int]) -> int:
    """Return the longest consecutive run of 'short' sentences."""
    best = 0
    current = 0
    for n in lengths:
        if n <= _SHORT_SENTENCE_MAX_WORDS:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best if best >= _SHORT_STREAK_MIN else 0


def _compute_punctuation_score(text: str, sentence_count: int) -> float:
    """Weighted punctuation score, normalized per sentence."""
    if sentence_count == 0:
        return 0.0

    score = 0.0

    # Count exclamation and question marks
    score += text.count("!") * _PUNCT_WEIGHTS["!"]
    score += text.count("?") * _PUNCT_WEIGHTS["?"]

    # Count ellipses
    score += len(_ELLIPSIS_RE.findall(text)) * _PUNCT_WEIGHTS["..."]

    # Count dashes
    score += len(_DASH_RE.findall(text)) * _PUNCT_WEIGHTS["--"]

    return score / sentence_count
