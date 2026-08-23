"""Scene segmenter — multi-signal scene boundary detection.

Layers (in priority order):
    1. Explicit markers  (``Chapter``, ``Scene``, ``---``, ``***``)
    2. Whitespace structure (format-aware: indent vs. block)
    3. Expanded temporal pattern matching + spaCy DATE/TIME NER
    4. Semantic embedding-shift detection (paragraph-level)

Each candidate boundary receives a *confidence score* from every layer.
Scores are summed (capped at 1.0) and a break fires when the cumulative
score meets ``break_threshold``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

import numpy as np

if TYPE_CHECKING:
    from spacy.tokens import Doc

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class SceneSpan:
    """A contiguous scene identified within the story text."""

    scene_index: int
    sent_start: int       # index of first sentence (inclusive)
    sent_end: int         # index of last sentence (exclusive)
    char_start: int
    char_end: int


@dataclass(slots=True)
class _BreakCandidate:
    """Internal accumulator for a potential scene boundary."""

    char_offset: int
    score: float = 0.0
    signals: list[str] = field(default_factory=list)

    def add(self, score: float, signal: str) -> None:
        self.score = min(1.0, self.score + score)
        self.signals.append(signal)


# ---------------------------------------------------------------------------
# Score constants
# ---------------------------------------------------------------------------
_SCORE_EXPLICIT_MARKER = 1.0
_SCORE_INDENT_BLANK_LINE = 0.85
_SCORE_TRIPLE_NEWLINE = 0.75
_SCORE_TEMPORAL_PHRASE = 0.65
_SCORE_SEMANTIC_SHIFT = 0.55
_SCORE_NER_DATETIME = 0.40


# ---------------------------------------------------------------------------
# Layer 1: Explicit markers
# ---------------------------------------------------------------------------
_MARKER_RE = re.compile(
    r"(?:^|\n)\s*(?:"
    r"(?:chapter|scene|act|part)\s+[\dIVXLCivxlc]+"
    r"|---+|===+|\*\*\*+"
    r")\s*(?:\n|$)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Layer 2: Whitespace structure
# ---------------------------------------------------------------------------
# Triple-newline (or more) — major structural break in block-format text
_TRIPLE_NEWLINE_RE = re.compile(r"\n\s*\n\s*\n")

# Double-newline — paragraph break (scene break in indent-format text)
_DOUBLE_NEWLINE_RE = re.compile(r"\n\s*\n")

# Indented line: tab or 2+ spaces at the start of a line
_INDENT_LINE_RE = re.compile(r"(?:^|\n)([ \t]{2,})\S", re.MULTILINE)


def detect_format(raw_text: str) -> Literal["indent", "block", "unknown"]:
    """Detect whether *raw_text* uses Normal Indent or Block formatting.

    **Normal Indent** (traditional novel typesetting):
        - Paragraphs start with a tab / 2+ spaces.
        - Same-scene paragraphs are separated by a single ``\\n`` (no blank
          line).
        - Blank lines (``\\n\\n``) signal scene breaks.

    **Block** (web / digital / pasted text):
        - No leading indentation on paragraphs.
        - Every paragraph separated by a blank line.
        - Scene breaks use explicit markers or triple-newlines.

    Returns ``"indent"``, ``"block"``, or ``"unknown"`` if the text is too
    short or ambiguous.
    """
    lines = raw_text.split("\n")
    if len(lines) < 4:
        return "unknown"

    # Count non-empty lines that start with indentation
    non_empty = [ln for ln in lines if ln.strip()]
    if not non_empty:
        return "unknown"

    indented = sum(
        1 for ln in non_empty
        if ln[0] in (" ", "\t") and len(ln) > 1
    )
    indent_ratio = indented / len(non_empty)

    # Count blank-line separations
    blank_lines = sum(1 for ln in lines if not ln.strip())
    blank_ratio = blank_lines / len(lines) if lines else 0

    # Heuristic decision
    if indent_ratio >= 0.35:
        # High indentation + relatively few blank lines = indent format
        return "indent"
    if blank_ratio >= 0.20 and indent_ratio < 0.10:
        return "block"
    return "unknown"


# ---------------------------------------------------------------------------
# Layer 3: Temporal patterns (expanded)
# ---------------------------------------------------------------------------
_TEMPORAL_RE = re.compile(
    r"\b(?:"
    # --- Original patterns (kept) ---
    r"the next (?:morning|day|evening|night|week|month|year)"
    r"|(?:hours|days|weeks|months|years|moments|minutes|centuries|decades) later"
    r"|a (?:few|long|couple of) (?:hours|minutes|moments|days|weeks|months|years) later"
    r"|the following (?:morning|day|evening|night|week|month|year)"
    r"|meanwhile"
    r"|later that (?:day|night|evening|morning)"
    r"|when (?:morning|dawn|dusk|night|evening) (?:came|arrived|broke|fell)"

    # --- NEW: Numeric time skips ---
    r"|(?:one|two|three|four|five|six|seven|eight|nine|ten"
    r"|eleven|twelve|thirteen|fourteen|fifteen|twenty|thirty|forty|fifty"
    r"|a hundred|a thousand|several|\d+)"
    r" (?:second|minute|hour|day|week|month|year|decade|century|millenni)s?"
    r" (?:passed|later|went by|elapsed|had (?:passed|gone by))"

    # --- NEW: Sleep / waking transitions ---
    r"|when (?:he|she|they|it|I|we|\w+) (?:woke(?: up)?|awoke|opened \w+ eyes)"
    r"|(?:he|she|they|I|we|\w+) (?:fell asleep|drifted off(?: to sleep)?)"

    # --- NEW: Event-based transitions ---
    r"|after the \w+"
    r"|once (?:the|it|he|she|they) \w+ (?:was|were|had|ended|finished|left|died)"
    r"|by the time (?:he|she|they|it|I|we|\w+)"

    # --- NEW: Seasonal / temporal shifts ---
    r"|it was (?:now |already )?(?:winter|spring|summer|autumn|fall|morning|night|dawn|dusk|noon|midnight)"
    r"|(?:winter|spring|summer|autumn|fall) (?:came|arrived|passed|had come|turned)"
    r"|that (?:winter|spring|summer|autumn|fall|morning|afternoon|evening|night)"

    # --- NEW: Generic time-skip openers ---
    r"|time (?:passed|went by|marched on|crawled)"
    r"|much later"
    r"|long after(?:ward)?s?"
    r"|some time (?:later|after(?:ward)?s?)"
    r"|not long after(?:ward)?s?"
    r"|before long"
    r"|in the days (?:that followed|ahead|to come)"
    r"|as the days (?:passed|went by|wore on)"
    r"|years? (?:passed|went by|elapsed)"
    r")\b",
    re.IGNORECASE,
)


def _detect_temporal_entities(doc: Doc) -> list[int]:
    """Return char offsets where DATE/TIME NER entities start a sentence.

    Uses spaCy's built-in NER — no extra computation since the Doc is
    already parsed.
    """
    breaks: list[int] = []
    sent_starts = {sent.start: sent.start_char for sent in doc.sents}
    for ent in doc.ents:
        if ent.label_ in ("DATE", "TIME") and ent.start in sent_starts:
            breaks.append(sent_starts[ent.start])
    return breaks


# ---------------------------------------------------------------------------
# Layer 4: Semantic shift detection
# ---------------------------------------------------------------------------

def _split_paragraphs(text: str) -> list[tuple[int, int, str]]:
    """Split *text* into paragraphs, returning ``(start, end, content)``."""
    paragraphs: list[tuple[int, int, str]] = []
    for m in re.finditer(r"(?:^|\n\s*\n)(.+?)(?=\n\s*\n|\Z)", text, re.DOTALL):
        content = m.group(1).strip()
        if content:
            paragraphs.append((m.start(1), m.end(1), content))

    # Fallback: if regex found nothing, treat the whole text as one paragraph
    if not paragraphs and text.strip():
        paragraphs.append((0, len(text), text.strip()))
    return paragraphs


def _detect_semantic_breaks(
    raw_text: str,
    *,
    threshold: float = 0.35,
) -> list[int]:
    """Return char offsets where consecutive paragraphs diverge semantically.

    Uses the sentence-transformer model already loaded by
    ``semantic_metrics.encode_text``.  We import lazily to avoid circular
    imports and to skip the heavyweight model load when ``semantic=False``.

    Parameters
    ----------
    raw_text:
        The (normalised) story text.
    threshold:
        Minimum *distance* (``1 − cosine_similarity``) to be considered a
        scene shift.  Lower = more sensitive.

    Returns
    -------
    list[int]
        Character offsets at which breaks were detected (start of the
        *second* paragraph in each divergent pair).
    """
    paragraphs = _split_paragraphs(raw_text)
    if len(paragraphs) < 2:
        return []

    from story_processing.signals.semantic_metrics import encode_text  # noqa: E402

    vectors = [np.array(encode_text(content)) for _, _, content in paragraphs]

    breaks: list[int] = []
    for i in range(1, len(vectors)):
        sim = float(np.dot(vectors[i - 1], vectors[i]))
        distance = 1.0 - sim
        if distance > threshold:
            breaks.append(paragraphs[i][0])

    return breaks


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def segment_scenes(
    doc: Doc,
    raw_text: str,
    *,
    format_hint: Literal["indent", "block", "auto"] = "auto",
    semantic: bool = True,
    break_threshold: float = 0.55,
    semantic_threshold: float = 0.35,
) -> list[SceneSpan]:
    """Segment a spaCy ``Doc`` into scenes using multi-signal detection.

    Pipeline:
        1. Detect text format (or use *format_hint*).
        2. Collect break candidates with scores from all layers.
        3. Merge candidates at overlapping offsets (sum scores, cap 1.0).
        4. Filter by *break_threshold*.
        5. Map to sentence indices → ``SceneSpan`` objects.

    Parameters
    ----------
    doc:
        Processed spaCy Doc.
    raw_text:
        The original (normalised) text.
    format_hint:
        ``"indent"`` / ``"block"`` / ``"auto"`` (auto-detect).
    semantic:
        If ``True``, use paragraph-embedding semantic shift detection
        (requires sentence-transformers model to be loadable).
    break_threshold:
        Minimum cumulative score for a boundary to fire (0.0–1.0).
    semantic_threshold:
        Distance threshold for semantic shift detection (0.0–1.0).

    Returns
    -------
    list[SceneSpan]
    """
    sentences = list(doc.sents)
    if not sentences:
        return []

    # -- Detect text format ------------------------------------------------
    fmt: Literal["indent", "block", "unknown"]
    if format_hint == "auto":
        fmt = detect_format(raw_text)
    else:
        fmt = format_hint  # type: ignore[assignment]
    logger.debug("Detected text format: %s", fmt)

    # -- Collect candidates ------------------------------------------------
    candidates: dict[int, _BreakCandidate] = {}

    def _add(offset: int, score: float, signal: str) -> None:
        if offset not in candidates:
            candidates[offset] = _BreakCandidate(char_offset=offset)
        candidates[offset].add(score, signal)

    # Layer 1: Explicit markers
    for m in _MARKER_RE.finditer(raw_text):
        _add(m.end(), _SCORE_EXPLICIT_MARKER, "explicit_marker")

    # Layer 2a: Triple-newline (always a strong signal)
    for m in _TRIPLE_NEWLINE_RE.finditer(raw_text):
        _add(m.end(), _SCORE_TRIPLE_NEWLINE, "triple_newline")

    # Layer 2b: Double-newline (strong in indent format only)
    if fmt == "indent":
        for m in _DOUBLE_NEWLINE_RE.finditer(raw_text):
            _add(m.end(), _SCORE_INDENT_BLANK_LINE, "indent_blank_line")

    # Layer 3a: Expanded temporal patterns
    for m in _TEMPORAL_RE.finditer(raw_text):
        _add(m.start(), _SCORE_TEMPORAL_PHRASE, "temporal_phrase")

    # Layer 3b: spaCy DATE/TIME entities at sentence starts
    for offset in _detect_temporal_entities(doc):
        _add(offset, _SCORE_NER_DATETIME, "ner_datetime")

    # Layer 4: Semantic shift detection (optional)
    if semantic:
        try:
            for offset in _detect_semantic_breaks(
                raw_text, threshold=semantic_threshold,
            ):
                _add(offset, _SCORE_SEMANTIC_SHIFT, "semantic_shift")
        except Exception:  # noqa: BLE001
            logger.warning(
                "Semantic shift detection failed; falling back to "
                "heuristic-only segmentation.",
                exc_info=True,
            )

    # -- Explicit-marker priority mode -------------------------------------
    # When the text contains 2+ explicit structural markers (Scene N,
    # Chapter N, ---, etc.) we trust only those and suppress all softer
    # signals.  This prevents double-newlines, temporal phrases, and
    # semantic shifts from fragmenting explicitly-marked scenes.
    explicit_candidates = [
        c for c in candidates.values()
        if "explicit_marker" in c.signals
    ]
    if len(explicit_candidates) >= 2:
        logger.debug(
            "Found %d explicit markers — using marker-only segmentation.",
            len(explicit_candidates),
        )
        candidates = {
            c.char_offset: c for c in explicit_candidates
        }

    # -- Filter by threshold -----------------------------------------------
    break_offsets: set[int] = set()
    for cand in candidates.values():
        if cand.score >= break_threshold:
            break_offsets.add(cand.char_offset)
            logger.debug(
                "Break at offset %d (score %.2f): %s",
                cand.char_offset, cand.score, ", ".join(cand.signals),
            )

    # -- Map char offsets → sentence indices --------------------------------
    break_sent_indices: set[int] = set()
    for i, sent in enumerate(sentences):
        for bc in break_offsets:
            if sent.start_char <= bc <= sent.end_char or (
                i > 0
                and sentences[i - 1].end_char <= bc <= sent.start_char
            ):
                break_sent_indices.add(i)

    # Index 0 is always the start of the first scene, not a "break"
    break_sent_indices.discard(0)
    sorted_breaks = sorted(break_sent_indices)

    # -- Build SceneSpan objects -------------------------------------------
    boundaries = [0] + sorted_breaks + [len(sentences)]
    scenes: list[SceneSpan] = []
    for idx in range(len(boundaries) - 1):
        s_start = boundaries[idx]
        s_end = boundaries[idx + 1]
        if s_start >= s_end:
            continue
        scenes.append(
            SceneSpan(
                scene_index=len(scenes),
                sent_start=s_start,
                sent_end=s_end,
                char_start=sentences[s_start].start_char,
                char_end=sentences[s_end - 1].end_char,
            )
        )

    return scenes
