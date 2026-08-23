"""Tests for story_processing.signals.structure_metrics."""

import pytest

from story_processing.nlp.dialogue_extractor import DialogueTurn
from story_processing.signals.structure_metrics import (
    _compute_punctuation_score,
    _max_short_streak,
    compute_structure_signals,
)


# ---------------------------------------------------------------------------
# _max_short_streak
# ---------------------------------------------------------------------------

class TestMaxShortStreak:
    def test_no_short_sentences(self):
        lengths = [10, 12, 15, 8, 20]
        assert _max_short_streak(lengths) == 0

    def test_below_threshold(self):
        # 2 consecutive short sentences — below _SHORT_STREAK_MIN (3)
        lengths = [3, 3, 10, 10]
        assert _max_short_streak(lengths) == 0

    def test_exactly_at_threshold(self):
        # 3 consecutive short sentences
        lengths = [3, 2, 4, 10, 10]
        assert _max_short_streak(lengths) == 3

    def test_longer_streak(self):
        lengths = [2, 1, 3, 2, 4, 10]
        assert _max_short_streak(lengths) == 5

    def test_empty(self):
        assert _max_short_streak([]) == 0

    def test_all_short(self):
        lengths = [1, 2, 3, 1, 2]
        assert _max_short_streak(lengths) == 5


# ---------------------------------------------------------------------------
# _compute_punctuation_score
# ---------------------------------------------------------------------------

class TestComputePunctuationScore:
    def test_zero_sentences(self):
        assert _compute_punctuation_score("Hello!", 0) == 0.0

    def test_exclamation_marks(self):
        score = _compute_punctuation_score("Wow! Amazing!", 2)
        assert score > 0.0
        # 2 exclamation marks * 1.5 weight / 2 sentences = 1.5
        assert abs(score - 1.5) < 1e-6

    def test_question_marks(self):
        score = _compute_punctuation_score("What? Why?", 2)
        # 2 * 1.2 / 2 = 1.2
        assert abs(score - 1.2) < 1e-6

    def test_mixed_punctuation(self):
        text = "What! Really? Wait..."
        score = _compute_punctuation_score(text, 3)
        assert score > 0.0

    def test_no_special_punctuation(self):
        score = _compute_punctuation_score("Hello world.", 1)
        assert score == 0.0


# ---------------------------------------------------------------------------
# compute_structure_signals (spaCy-dependent)
# ---------------------------------------------------------------------------

@pytest.mark.spacy
class TestComputeStructureSignals:
    def test_basic_computation(self, make_doc):
        text = "He ran fast. She jumped high. They fought bravely."
        doc = make_doc(text)
        sents = list(doc.sents)
        turns = []  # no dialogue
        sig = compute_structure_signals(sents, turns, text)
        assert sig.sentence_count == 3
        assert sig.word_count > 0
        assert sig.avg_sentence_length > 0.0
        assert sig.dialogue_ratio == 0.0
        assert sig.dialogue_turn_count == 0

    def test_with_dialogue(self, make_doc):
        text = 'He said "hello" and left.'
        doc = make_doc(text)
        sents = list(doc.sents)
        turns = [DialogueTurn(text="hello", start_char=9, end_char=14, quote_style="double")]
        sig = compute_structure_signals(sents, turns, text)
        assert sig.dialogue_turn_count == 1
        assert sig.dialogue_ratio > 0.0
        assert sig.avg_dialogue_length > 0.0

    def test_empty_input(self, make_doc):
        doc = make_doc("")
        sig = compute_structure_signals([], [], "")
        assert sig.sentence_count == 0
        assert sig.word_count == 0
        assert sig.avg_sentence_length == 0.0
