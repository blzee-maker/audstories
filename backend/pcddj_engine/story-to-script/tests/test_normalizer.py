"""Tests for story_processing.preprocessing.normalizer."""

from story_processing.preprocessing.normalizer import normalize


class TestNormalize:
    """Tests for the normalize() function."""

    def test_empty_string(self):
        assert normalize("") == ""

    def test_whitespace_only(self):
        assert normalize("   \n\n  ") == ""

    def test_curly_double_quotes(self):
        result = normalize("\u201cHello\u201d")
        assert result == '"Hello"'

    def test_curly_single_quotes(self):
        result = normalize("\u2018Hi\u2019")
        assert result == "'Hi'"

    def test_low9_double_quotes(self):
        result = normalize("\u201eHi\u201d")
        assert result == '"Hi"'

    def test_angle_quotes(self):
        result = normalize("\u00abHi\u00bb")
        assert result == '"Hi"'

    def test_control_chars_stripped(self):
        result = normalize("Hello\x00World\x7f!")
        # Control chars are removed (no space inserted)
        assert "\x00" not in result
        assert "\x7f" not in result
        assert "Hello" in result
        assert "World!" in result

    def test_tabs_preserved_as_space(self):
        # Inline whitespace collapsed to single space, but \n preserved
        result = normalize("Hello\t\tWorld")
        assert result == "Hello World"

    def test_inline_whitespace_collapse(self):
        result = normalize("Hello     World")
        assert result == "Hello World"

    def test_newlines_preserved(self):
        result = normalize("Line one\nLine two")
        assert "Line one\n" in result
        assert "Line two" in result

    def test_multi_newline_capping(self):
        # 4+ newlines should become exactly 3
        result = normalize("Part one\n\n\n\n\nPart two")
        assert "\n\n\n\n" not in result
        assert "\n\n\n" in result

    def test_double_newline_preserved(self):
        # 2 newlines (paragraph break) should stay
        result = normalize("Para one\n\nPara two")
        assert "\n\n" in result

    def test_triple_newline_preserved(self):
        # 3 newlines (major break) should stay
        result = normalize("Para one\n\n\nPara two")
        assert "\n\n\n" in result

    def test_nfkc_normalization(self):
        # NFKC normalises ﬁ (U+FB01 ligature) to 'fi' (two chars)
        result = normalize("na\ufb01ve")
        assert "nafive" in result
        assert "\ufb01" not in result

    def test_strip_edges(self):
        result = normalize("  \n Hello \n  ")
        assert result == "Hello"

    def test_combined(self):
        text = "  \u201cHello\u201d  \t World!\x00\n\n\n\n\nEnd  "
        result = normalize(text)
        assert '"Hello"' in result
        assert "World!" in result
        assert "\x00" not in result
        assert "\n\n\n\n" not in result
