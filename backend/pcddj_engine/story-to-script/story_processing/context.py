"""Cross-scene context — story-level memory for the pipeline.

Provides:
- ``StoryContext``:  per-scene snapshot of accumulated story state.
- ``StoryContextBuilder``:  rolling-state builder that produces
  ``StoryContext`` objects in O(1) per scene.
- ``reconcile_speakers``:  post-processing pass that enforces character
  continuity across scenes.

Inserted between the parallel extraction step and the sequential
classification step in :func:`story_processing.pipeline.process_story`.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from spacy.tokens import Doc

logger = logging.getLogger(__name__)

# High-arousal emotion categories (must match semantic_metrics / fallback_rules)
_HIGH_AROUSAL: frozenset[str] = frozenset({
    "anxiety", "anger", "surprise", "anticipation",
})

_UNKNOWN_SPEAKER_RE = re.compile(r"^unknown_speaker_\d+$")


# ---------------------------------------------------------------------------
# StoryContext dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class StoryContext:
    """Accumulated cross-scene information passed to the classifier.

    Constructed by :class:`StoryContextBuilder`.  Scene 0 receives a
    context with empty history (``prev_emotions == []``, trend ``"stable"``).
    """

    scene_index: int
    total_scenes: int
    position_ratio: float  # 0.0–1.0

    # Emotional trajectory (up to last 3 primary_emotion labels)
    prev_emotions: list[str] = field(default_factory=list)
    emotion_trend: str = "stable"  # escalating / de-escalating / stable / volatile

    # Pacing
    pacing_trend: str = "steady"  # accelerating / decelerating / steady

    # Speaker continuity — all named speakers seen so far
    known_speakers: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# StoryContextBuilder (rolling state)
# ---------------------------------------------------------------------------

class StoryContextBuilder:
    """Incrementally builds :class:`StoryContext` for each scene.

    Usage::

        builder = StoryContextBuilder(total_scenes=len(scene_data_list))
        for i, scene_data in enumerate(scene_data_list):
            ctx = builder.get_context(i)
            # … classify scene_data using ctx …
            builder.advance(scene_data)
    """

    def __init__(self, total_scenes: int) -> None:
        self._total = total_scenes

        # Rolling history — appended by advance()
        self._arousal_history: list[float] = []
        self._dominant_history: list[str] = []
        self._word_count_history: list[int] = []
        self._known_speakers: list[str] = []

    # -- public interface ---------------------------------------------------

    def get_context(self, scene_index: int) -> StoryContext:
        """Return the context for *scene_index* from current rolling state.

        O(1) — reads the last 3 entries of the rolling lists.
        """
        return StoryContext(
            scene_index=scene_index,
            total_scenes=self._total,
            position_ratio=scene_index / max(self._total, 1),
            prev_emotions=list(self._dominant_history[-3:]),
            emotion_trend=self._compute_emotion_trend(),
            pacing_trend=self._compute_pacing_trend(),
            known_speakers=list(self._known_speakers),
        )

    def advance(self, scene_data: dict[str, Any]) -> None:
        """Ingest one processed scene and update rolling state.

        Call this **after** classifying a scene so that the next scene's
        context includes this scene's data.
        """
        # Emotion scores → mean arousal
        emotion_scores: dict[str, float] = scene_data.get("signals", {}).get(
            "emotion_scores", {}
        )
        arousal = sum(emotion_scores.get(e, 0.0) for e in _HIGH_AROUSAL)
        self._arousal_history.append(arousal)

        # Dominant emotion — from interpretation if available, else from scores
        interp = scene_data.get("interpretation", {})
        dominant = interp.get("primary_emotion", "")
        if not dominant and emotion_scores:
            dominant = max(emotion_scores, key=lambda k: emotion_scores[k])
        self._dominant_history.append(dominant or "neutral")

        # Word count
        word_count = scene_data.get("structure", {}).get("word_count", 0)
        self._word_count_history.append(word_count)

        # Speakers — accumulate named (non-unknown) speakers
        speakers = scene_data.get("structure", {}).get("speakers", [])
        for spk in speakers:
            if not _UNKNOWN_SPEAKER_RE.match(spk) and spk not in self._known_speakers:
                self._known_speakers.append(spk)

    # -- trend computation (Guardrail 1: simple monotonic, no regression) ---

    def _compute_emotion_trend(self) -> str:
        """Coarse emotion trend from the last 3 arousal values."""
        window = self._arousal_history[-3:]
        if len(window) < 2:
            return "stable"

        # Check dominant emotion volatility first
        dom_window = self._dominant_history[-3:]
        if len(dom_window) >= 3:
            changes = sum(
                1 for i in range(1, len(dom_window))
                if dom_window[i] != dom_window[i - 1]
            )
            if changes > 1:  # > 2 different labels in 3 scenes ≡ 2+ changes
                return "volatile"

        # Simple monotonic comparison
        increasing = all(
            window[i] < window[i + 1] for i in range(len(window) - 1)
        )
        decreasing = all(
            window[i] > window[i + 1] for i in range(len(window) - 1)
        )

        if increasing:
            return "escalating"
        if decreasing:
            return "de-escalating"
        return "stable"

    def _compute_pacing_trend(self) -> str:
        """Coarse pacing trend from the last 3 word counts."""
        window = self._word_count_history[-3:]
        if len(window) < 2:
            return "steady"

        # Shorter scenes = faster pacing → "accelerating"
        decreasing_wc = all(
            window[i] > window[i + 1] for i in range(len(window) - 1)
        )
        increasing_wc = all(
            window[i] < window[i + 1] for i in range(len(window) - 1)
        )

        if decreasing_wc:
            return "accelerating"
        if increasing_wc:
            return "decelerating"
        return "steady"


# ---------------------------------------------------------------------------
# Speaker reconciliation
# ---------------------------------------------------------------------------

def reconcile_speakers(
    scene_data_list: list[dict[str, Any]],
    doc: Doc,
) -> None:
    """Reconcile speakers across scenes for character continuity.

    Mutates *scene_data_list* in place.

    Steps:
    1. Build a global registry of all **named** speakers from every scene.
    2. For each ``unknown_speaker_X``, check if a named speaker from the
       registry appears in the **same sentence or 1–2 sentences prior** to
       the dialogue turn.  If found, replace the unknown label.
       (Guardrail 2: tight proximity only.)
    3. Renumber remaining unknowns with a single global counter.
    4. Update ``speakers`` and ``dialogue_turns[].speaker`` per scene.
    """
    # ---- Step 1: Build global named-speaker registry ----------------------
    global_named: set[str] = set()
    for sd in scene_data_list:
        for spk in sd["structure"]["speakers"]:
            if not _UNKNOWN_SPEAKER_RE.match(spk):
                global_named.add(spk)

    if not global_named:
        # No named speakers anywhere — skip to renumbering
        _renumber_unknowns(scene_data_list)
        return

    # Pre-index: map char offset → sentence for proximity checks
    all_sents = list(doc.sents)
    sent_ranges: list[tuple[int, int]] = [
        (s.start_char, s.end_char) for s in all_sents
    ]

    # ---- Step 2: Cross-scene attribution ----------------------------------
    for sd in scene_data_list:
        turns = sd["structure"]["dialogue_turns"]
        for turn in turns:
            if not _UNKNOWN_SPEAKER_RE.match(turn["speaker"]):
                continue  # already attributed

            replacement = _find_named_speaker_near(
                turn_start=turn["start_char"],
                turn_end=turn["end_char"],
                sent_ranges=sent_ranges,
                all_sents=all_sents,
                named_speakers=global_named,
            )
            if replacement is not None:
                turn["speaker"] = replacement

    # ---- Step 3: Global renumbering of remaining unknowns -----------------
    _renumber_unknowns(scene_data_list)


def _find_named_speaker_near(
    turn_start: int,
    turn_end: int,
    sent_ranges: list[tuple[int, int]],
    all_sents: list,
    named_speakers: set[str],
) -> str | None:
    """Check if a named speaker appears in the same or 1–2 prior sentences.

    Returns the speaker name if found, else ``None``.
    Guardrail 2: tight proximity window only.
    """
    # Find the sentence index that contains the dialogue start
    turn_sent_idx: int | None = None
    for idx, (s_start, s_end) in enumerate(sent_ranges):
        if s_start <= turn_start < s_end:
            turn_sent_idx = idx
            break
    # Fallback: find closest sentence before the turn
    if turn_sent_idx is None:
        for idx in range(len(sent_ranges) - 1, -1, -1):
            if sent_ranges[idx][0] <= turn_start:
                turn_sent_idx = idx
                break
    if turn_sent_idx is None:
        return None

    # Search window: same sentence + up to 2 prior sentences
    start_idx = max(0, turn_sent_idx - 2)
    end_idx = turn_sent_idx + 1  # inclusive of turn's sentence

    for sidx in range(start_idx, end_idx):
        sent_text = all_sents[sidx].text
        for name in named_speakers:
            # Whole-word match to avoid partial matches ("Al" in "Also")
            if re.search(rf"\b{re.escape(name)}\b", sent_text):
                return name

    return None


def _renumber_unknowns(scene_data_list: list[dict[str, Any]]) -> None:
    """Renumber all remaining ``unknown_speaker_*`` with a global counter.

    Ensures unknowns are unique and sequential across scenes.
    """
    global_counter = 0
    # Map old unknown label → new global label (within the same scene
    # context, the same old label should map to the same new label).
    for sd in scene_data_list:
        label_map: dict[str, str] = {}
        turns = sd["structure"]["dialogue_turns"]

        for turn in turns:
            old = turn["speaker"]
            if not _UNKNOWN_SPEAKER_RE.match(old):
                continue
            if old not in label_map:
                global_counter += 1
                label_map[old] = f"unknown_speaker_{global_counter}"
            turn["speaker"] = label_map[old]

        # Rebuild speakers list from updated turns + any non-turn speakers
        all_speakers: set[str] = set()
        for turn in turns:
            all_speakers.add(turn["speaker"])
        # Preserve any named speakers that had no dialogue turns in this scene
        for spk in sd["structure"]["speakers"]:
            if not _UNKNOWN_SPEAKER_RE.match(spk):
                all_speakers.add(spk)
        sd["structure"]["speakers"] = sorted(all_speakers)
