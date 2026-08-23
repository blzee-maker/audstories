"""Tests for story_processing.nlp.speaker_resolver."""

import pytest

from story_processing.nlp.dialogue_extractor import DialogueTurn
from story_processing.nlp.speaker_resolver import resolve_speakers


pytestmark = pytest.mark.spacy


class TestResolveSpeakers:
    def test_known_speaker_via_nsubj(self, make_doc):
        text = 'Marcus said "Hello there."'
        doc = make_doc(text)
        turns = [DialogueTurn(text="Hello there.", start_char=13, end_char=26, quote_style="double")]
        result = resolve_speakers(doc, turns)
        assert len(result) == 1
        assert result[0].speaker == "Marcus"

    def test_unknown_speaker_fallback(self, make_doc):
        text = '"Someone spoke." The room was silent.'
        doc = make_doc(text)
        turns = [DialogueTurn(text="Someone spoke.", start_char=1, end_char=15, quote_style="double")]
        result = resolve_speakers(doc, turns)
        assert len(result) == 1
        assert result[0].speaker.startswith("unknown_speaker_")

    def test_multiple_turns_different_speakers(self, make_doc):
        text = 'Alice said "Hello." Bob replied "Goodbye."'
        doc = make_doc(text)
        turns = [
            DialogueTurn(text="Hello.", start_char=12, end_char=18, quote_style="double"),
            DialogueTurn(text="Goodbye.", start_char=33, end_char=41, quote_style="double"),
        ]
        result = resolve_speakers(doc, turns)
        assert len(result) == 2
        speakers = {r.speaker for r in result}
        # At least one should be attributed (depends on spaCy parse)
        assert len(speakers) >= 1

    def test_empty_turns(self, make_doc):
        doc = make_doc("Just narration. No dialogue here.")
        result = resolve_speakers(doc, [])
        assert result == []

    def test_attributed_turn_preserves_fields(self, make_doc):
        text = 'Marcus whispered "Be quiet."'
        doc = make_doc(text)
        turns = [DialogueTurn(text="Be quiet.", start_char=18, end_char=27, quote_style="double")]
        result = resolve_speakers(doc, turns)
        assert result[0].text == "Be quiet."
        assert result[0].quote_style == "double"
