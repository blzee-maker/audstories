"""Dialogue extractor — regex + dependency-parse extraction of speech.

Extracts:
    - Direct speech via regex (double-quoted, single-quoted, em-dash)
    - Indirect / reported speech via spaCy dependency parsing (``ccomp``)

Overlapping spans are resolved with a containment-aware algorithm that
prefers longer (more complete) matches and discards spans fully contained
within another.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from spacy.tokens import Doc


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class DialogueTurn:
    """A single stretch of dialogue found in the text."""

    text: str
    start_char: int
    end_char: int
    quote_style: Literal["double", "single", "em_dash", "indirect"]


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Double-quoted: "…"
_DOUBLE_QUOTE_RE = re.compile(r'"([^"]+)"')

# Single-quoted: '…'
# Constrained to avoid apostrophe / contraction collisions:
#   - Opening ' must follow whitespace or be at start of string
#   - Content must not cross line boundaries
#   - Closing ' must precede whitespace, punctuation, or end of string
_SINGLE_QUOTE_RE = re.compile(
    r"(?:(?<=\s)|(?<=^))"
    r"'([^'\n]{2,})'"
    r"(?=[\s.,!?;:\-)}\]—–\"]|$)",
    re.MULTILINE,
)

# Em-dash dialogue:  — …  (line-start em-dash, common in literary fiction)
_EM_DASH_RE = re.compile(r"(?:^|\n)\s*[—–]\s*(.+?)(?=\n|$)")


_PATTERNS: list[tuple[re.Pattern[str], Literal["double", "single", "em_dash"]]] = [
    (_DOUBLE_QUOTE_RE, "double"),
    (_SINGLE_QUOTE_RE, "single"),
    (_EM_DASH_RE, "em_dash"),
]


# ---------------------------------------------------------------------------
# Speech verbs used for indirect speech detection
# ---------------------------------------------------------------------------
# Core set matches SPEECH_VERBS in speaker_resolver.py; additional verbs
# commonly introduce indirect / reported speech.
_INDIRECT_SPEECH_LEMMAS: frozenset[str] = frozenset({
    # --- shared with speaker_resolver.SPEECH_VERBS ---
    "say", "tell", "ask", "whisper", "shout", "reply", "respond",
    "mutter", "exclaim", "murmur", "cry", "scream", "call",
    "announce", "declare", "add", "continue", "begin", "snap",
    "sigh", "groan", "plead", "insist", "demand", "stammer",
    # --- additional indirect-speech verbs ---
    "explain", "mention", "note", "observe", "remark", "state",
    "suggest", "warn", "inform", "describe", "reveal", "promise",
    "remind", "advise", "confess", "admit", "confirm", "deny",
    "claim", "argue", "assert",
})


# ---------------------------------------------------------------------------
# Containment-aware overlap resolver
# ---------------------------------------------------------------------------

def _resolve_overlaps(turns: list[DialogueTurn]) -> list[DialogueTurn]:
    """Remove overlapping spans, preferring longer matches.

    Algorithm:
        1. Sort by ``start_char``; break ties by span length (longest first).
        2. Walk the sorted list.  For each candidate:
           a. If it is fully **contained** within the current kept span
              → discard unconditionally.
           b. If it **partially overlaps** the current kept span
              → keep the longer of the two (drop the shorter).
           c. If it starts at or after the current kept span's end
              → keep it (no overlap).
    """
    if not turns:
        return []

    sorted_turns = sorted(
        turns,
        key=lambda t: (t.start_char, -(t.end_char - t.start_char)),
    )

    result: list[DialogueTurn] = [sorted_turns[0]]

    for candidate in sorted_turns[1:]:
        prev = result[-1]

        # No overlap — candidate starts at or after previous end
        if candidate.start_char >= prev.end_char:
            result.append(candidate)
            continue

        # Candidate is fully contained in prev → discard
        if candidate.end_char <= prev.end_char:
            continue

        # Partial overlap — keep the longer span
        prev_len = prev.end_char - prev.start_char
        cand_len = candidate.end_char - candidate.start_char
        if cand_len > prev_len:
            result[-1] = candidate
        # else: keep prev (already in result)

    return result


# ---------------------------------------------------------------------------
# Public API — direct (regex) extraction
# ---------------------------------------------------------------------------

def extract_dialogue(text: str) -> list[DialogueTurn]:
    """Extract all quoted dialogue spans from *text* using regex.

    Returns a list of :class:`DialogueTurn` sorted by ``start_char``.
    Overlapping spans are resolved with a containment-aware algorithm.
    """
    raw_turns: list[DialogueTurn] = []

    for pattern, style in _PATTERNS:
        for m in pattern.finditer(text):
            inner = m.group(1)
            raw_turns.append(
                DialogueTurn(
                    text=inner.strip(),
                    start_char=m.start(),
                    end_char=m.end(),
                    quote_style=style,
                )
            )

    # Sort + resolve overlaps
    raw_turns.sort(key=lambda t: t.start_char)
    return _resolve_overlaps(raw_turns)


# ---------------------------------------------------------------------------
# Public API — indirect (spaCy dep-parse) extraction
# ---------------------------------------------------------------------------

def extract_indirect_speech(doc: Doc) -> list[DialogueTurn]:
    """Extract indirect / reported speech from a spaCy ``Doc``.

    Walks the dependency tree looking for speech verbs with a clausal
    complement (``ccomp``).  The complement subtree's text is captured
    as an indirect dialogue turn.

    Parameters
    ----------
    doc:
        A fully parsed spaCy ``Doc``.

    Returns
    -------
    list[DialogueTurn]
        Sorted by ``start_char``.
    """
    turns: list[DialogueTurn] = []

    for token in doc:
        # Only consider verbs whose lemma is a known speech/communication verb
        if token.pos_ != "VERB":
            continue
        if token.lemma_.lower() not in _INDIRECT_SPEECH_LEMMAS:
            continue

        # Look for a clausal complement (ccomp) child
        for child in token.children:
            if child.dep_ != "ccomp":
                continue

            # Get the full span of the ccomp subtree
            subtree_tokens = sorted(child.subtree, key=lambda t: t.i)
            if not subtree_tokens:
                continue

            start_char = subtree_tokens[0].idx
            last_tok = subtree_tokens[-1]
            end_char = last_tok.idx + len(last_tok.text)
            span_text = doc.text[start_char:end_char].strip()

            if len(span_text) < 3:
                continue  # skip trivially short spans

            turns.append(
                DialogueTurn(
                    text=span_text,
                    start_char=start_char,
                    end_char=end_char,
                    quote_style="indirect",
                )
            )

    turns.sort(key=lambda t: t.start_char)
    return turns


# ---------------------------------------------------------------------------
# Public API — merge direct + indirect
# ---------------------------------------------------------------------------

def merge_dialogue(
    direct: list[DialogueTurn],
    indirect: list[DialogueTurn],
) -> list[DialogueTurn]:
    """Merge direct and indirect dialogue turns, resolving overlaps.

    Direct-quote matches take priority over indirect matches at the same
    span (direct speech is higher confidence).
    """
    # Combine with direct turns first (they sort earlier on ties due to
    # the overlap resolver preferring the first/longer match).
    combined = list(direct) + list(indirect)
    combined.sort(key=lambda t: t.start_char)
    return _resolve_overlaps(combined)
