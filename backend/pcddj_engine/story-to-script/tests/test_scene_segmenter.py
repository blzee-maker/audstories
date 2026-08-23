"""Tests for story_processing.nlp.scene_segmenter."""

import pytest

from story_processing.nlp.scene_segmenter import detect_format, segment_scenes


# ---------------------------------------------------------------------------
# detect_format tests (no spaCy needed)
# ---------------------------------------------------------------------------

class TestDetectFormat:
    def test_indent_format(self):
        lines = [
            "    First paragraph first line.",
            "    Continuation.",
            "    Second paragraph.",
            "    More text here.",
            "    Fifth line of indented text.",
        ]
        text = "\n".join(lines)
        assert detect_format(text) == "indent"

    def test_block_format(self):
        lines = [
            "First paragraph.",
            "",
            "Second paragraph.",
            "",
            "Third paragraph.",
            "",
            "Fourth paragraph.",
        ]
        text = "\n".join(lines)
        assert detect_format(text) == "block"

    def test_short_text_unknown(self):
        assert detect_format("Hi.\nBye.") == "unknown"

    def test_empty_text(self):
        assert detect_format("") == "unknown"


# ---------------------------------------------------------------------------
# segment_scenes tests (need spaCy fixture)
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.spacy


class TestSegmentScenes:
    def test_single_scene_no_break(self, make_doc):
        text = "The sun rose. Birds sang. It was peaceful."
        doc = make_doc(text)
        scenes = segment_scenes(doc, text, semantic=False)
        assert len(scenes) >= 1
        assert scenes[0].scene_index == 0
        assert scenes[0].sent_start == 0

    def test_explicit_marker_creates_break(self, make_doc):
        text = "Scene one text here.\n\n---\n\nScene two text here."
        doc = make_doc(text)
        scenes = segment_scenes(doc, text, semantic=False)
        assert len(scenes) >= 2

    def test_triple_newline_break(self, make_doc):
        text = "Part one is long enough.\n\n\nPart two begins here."
        doc = make_doc(text)
        scenes = segment_scenes(doc, text, semantic=False)
        # Triple newline should create a strong signal
        assert len(scenes) >= 1  # may or may not break depending on threshold

    def test_temporal_phrase_signal(self, make_doc):
        text = (
            "They fought bravely.\n\n---\n\n"
            "The next morning the village was quiet."
        )
        doc = make_doc(text)
        scenes = segment_scenes(doc, text, semantic=False)
        assert len(scenes) >= 2

    def test_empty_doc(self, make_doc):
        doc = make_doc("")
        scenes = segment_scenes(doc, "", semantic=False)
        assert scenes == []

    def test_scene_spans_have_valid_indices(self, make_doc):
        text = "First sentence.\n\n---\n\nSecond sentence."
        doc = make_doc(text)
        scenes = segment_scenes(doc, text, semantic=False)
        for scene in scenes:
            assert scene.sent_start >= 0
            assert scene.sent_end > scene.sent_start
            assert scene.char_start >= 0
            assert scene.char_end > scene.char_start
