"""Tests for story_processing.nlp.dialogue_extractor."""

from story_processing.nlp.dialogue_extractor import (
    DialogueTurn,
    _resolve_overlaps,
    extract_dialogue,
    merge_dialogue,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _turn(text: str, start: int, end: int, style: str = "double") -> DialogueTurn:
    return DialogueTurn(text=text, start_char=start, end_char=end, quote_style=style)


# ---------------------------------------------------------------------------
# Regex extraction tests
# ---------------------------------------------------------------------------

class TestExtractDialogue:
    """Tests for regex-based dialogue extraction."""

    def test_double_quotes(self):
        text = 'She said "Hello there" loudly.'
        turns = extract_dialogue(text)
        assert len(turns) == 1
        assert turns[0].text == "Hello there"
        assert turns[0].quote_style == "double"

    def test_multiple_double_quotes(self):
        text = '"First quote." Then silence. "Second quote."'
        turns = extract_dialogue(text)
        assert len(turns) == 2

    def test_single_quotes(self):
        # Single quote dialogue requires whitespace/start before opening '
        text = "He said 'Not a chance' firmly."
        turns = extract_dialogue(text)
        single_turns = [t for t in turns if t.quote_style == "single"]
        assert len(single_turns) == 1
        assert single_turns[0].text == "Not a chance"

    def test_em_dash_dialogue(self):
        text = "\n\u2014 Get out of here!"
        turns = extract_dialogue(text)
        em_turns = [t for t in turns if t.quote_style == "em_dash"]
        assert len(em_turns) == 1
        assert "Get out of here!" in em_turns[0].text

    def test_empty_text(self):
        assert extract_dialogue("") == []

    def test_no_dialogue(self):
        text = "The sun rose over the mountains. Birds sang."
        turns = extract_dialogue(text)
        assert turns == []

    def test_sorted_by_start_char(self):
        text = '"First" came before "Second" in the text.'
        turns = extract_dialogue(text)
        assert len(turns) >= 2
        for i in range(1, len(turns)):
            assert turns[i].start_char >= turns[i - 1].start_char


# ---------------------------------------------------------------------------
# Overlap resolver tests
# ---------------------------------------------------------------------------

class TestResolveOverlaps:
    """Tests for _resolve_overlaps."""

    def test_empty_list(self):
        assert _resolve_overlaps([]) == []

    def test_no_overlaps(self):
        turns = [
            _turn("A", 0, 5),
            _turn("B", 10, 15),
        ]
        result = _resolve_overlaps(turns)
        assert len(result) == 2

    def test_full_containment_discards_inner(self):
        outer = _turn("outer", 0, 20)
        inner = _turn("inner", 5, 10)
        result = _resolve_overlaps([inner, outer])
        assert len(result) == 1
        assert result[0].text == "outer"

    def test_partial_overlap_keeps_longer(self):
        short = _turn("short", 0, 10)
        long = _turn("long span", 5, 20)
        result = _resolve_overlaps([short, long])
        assert len(result) == 1
        assert result[0].text == "long span"

    def test_adjacent_spans_kept(self):
        a = _turn("A", 0, 10)
        b = _turn("B", 10, 20)
        result = _resolve_overlaps([a, b])
        assert len(result) == 2

    def test_single_turn(self):
        t = _turn("only", 0, 5)
        result = _resolve_overlaps([t])
        assert len(result) == 1
        assert result[0].text == "only"


# ---------------------------------------------------------------------------
# Merge tests
# ---------------------------------------------------------------------------

class TestMergeDialogue:
    """Tests for merge_dialogue."""

    def test_direct_priority_over_indirect(self):
        direct = [_turn("direct", 0, 10, "double")]
        indirect = [_turn("indirect", 0, 10, "indirect")]
        # Direct comes first in merge — overlap resolver keeps the first/longer
        result = merge_dialogue(direct, indirect)
        assert len(result) == 1

    def test_non_overlapping_merge(self):
        direct = [_turn("direct", 0, 10, "double")]
        indirect = [_turn("indirect", 20, 30, "indirect")]
        result = merge_dialogue(direct, indirect)
        assert len(result) == 2

    def test_empty_inputs(self):
        assert merge_dialogue([], []) == []
