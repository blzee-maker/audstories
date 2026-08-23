"""Text normalizer — deterministic preprocessing of raw story text."""

from __future__ import annotations

import re
import unicodedata


# Mapping of curly/smart quotes to straight ASCII equivalents
_QUOTE_MAP: dict[str, str] = {
    "\u2018": "'",   # left single
    "\u2019": "'",   # right single
    "\u201A": "'",   # single low-9
    "\u201C": '"',   # left double
    "\u201D": '"',   # right double
    "\u201E": '"',   # double low-9
    "\u2039": "'",   # single left-pointing angle
    "\u203A": "'",   # single right-pointing angle
    "\u00AB": '"',   # left-pointing double angle
    "\u00BB": '"',   # right-pointing double angle
}

_QUOTE_RE = re.compile("|".join(re.escape(k) for k in _QUOTE_MAP))

# Control characters except newline (\n), carriage return (\r), and tab (\t)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]")

# Collapse runs of whitespace on a single line (spaces/tabs only)
_INLINE_WS_RE = re.compile(r"[^\S\n]+")

# Collapse 4+ consecutive newlines into exactly 3 (preserves the distinction
# between "paragraph break" (\n\n) and "major structural break" (\n\n\n)
# so that the scene segmenter can detect deliberate scene separators).
_MULTI_NEWLINE_RE = re.compile(r"\n{4,}")


def normalize(text: str) -> str:
    """Normalize raw story text for downstream NLP processing.

    Steps (in order):
    1. Unicode NFKC normalization
    2. Strip control characters
    3. Curly → straight quote normalization
    4. Collapse inline whitespace
    5. Collapse excessive blank lines (keep paragraph breaks)
    6. Strip leading/trailing whitespace

    Returns clean ``str``.
    """
    if not text:
        return ""

    # 1. Unicode NFKC
    text = unicodedata.normalize("NFKC", text)

    # 2. Strip control chars
    text = _CONTROL_RE.sub("", text)

    # 3. Quotes
    text = _QUOTE_RE.sub(lambda m: _QUOTE_MAP[m.group()], text)

    # 4. Collapse inline whitespace (preserve newlines)
    text = _INLINE_WS_RE.sub(" ", text)

    # 5. Collapse 4+ newlines → 3 (keep major-break vs paragraph-break distinction)
    text = _MULTI_NEWLINE_RE.sub("\n\n\n", text)

    # 6. Strip edges
    text = text.strip()

    return text
