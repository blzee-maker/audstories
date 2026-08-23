"""Semantic metrics — emotion classification and embedding signals.

Uses:
- GoEmotions classifier (configurable, default SamLowe/roberta-base-go_emotions)
  for multi-label emotion scoring with weighted category mapping.
- sentence-transformers (all-MiniLM-L6-v2) for text encoding, retained solely
  for the scene segmenter's semantic shift detection.
- Singleton model loading for both models.
- LRU cache on text encoding.
- Batched inference for emotion classification.
- Arc stabilization (EMA smoothing, peak gating, min segment duration).
"""

from __future__ import annotations

import functools
import re
import threading
from typing import Any, Literal

import numpy as np

# ---------------------------------------------------------------------------
# Emotion categories — our 12 target categories
# ---------------------------------------------------------------------------
EMOTION_CATEGORIES: tuple[str, ...] = (
    "anxiety",
    "joy",
    "sadness",
    "anger",
    "calm",
    "neutral",
    "surprise",
    "disgust",
    "love",
    "anticipation",
    "nostalgia",
    "confusion",
)

# ---------------------------------------------------------------------------
# GoEmotions → category weighted mapping
# ---------------------------------------------------------------------------
# Each GoEmotions label maps to one or more target categories with weights.
# Single-target labels use weight 1.0.
# Multi-target labels use primary (0.7) and secondary (0.3) weights.
# These weights are trivially tunable without code changes.
GOEMOTION_WEIGHTS: dict[str, list[tuple[str, float]]] = {
    # ---- Single-target mappings (weight 1.0) ----
    "fear": [("anxiety", 1.0)],
    "nervousness": [("anxiety", 1.0)],
    "joy": [("joy", 1.0)],
    "amusement": [("joy", 1.0)],
    "pride": [("joy", 1.0)],
    "relief": [("joy", 1.0)],
    "sadness": [("sadness", 1.0)],
    "disappointment": [("sadness", 1.0)],
    "anger": [("anger", 1.0)],
    "annoyance": [("anger", 1.0)],
    "disapproval": [("anger", 1.0)],
    "approval": [("calm", 1.0)],
    "gratitude": [("calm", 1.0)],
    "neutral": [("neutral", 1.0)],
    "realization": [("neutral", 1.0)],
    "surprise": [("surprise", 1.0)],
    "disgust": [("disgust", 1.0)],
    "embarrassment": [("disgust", 1.0)],
    "love": [("love", 1.0)],
    "admiration": [("love", 1.0)],
    "confusion": [("confusion", 1.0)],
    # ---- Multi-target mappings (primary 0.7, secondary 0.3) ----
    "excitement": [("joy", 0.7), ("anticipation", 0.3)],
    "curiosity": [("anticipation", 0.7), ("surprise", 0.3)],
    "grief": [("sadness", 0.7), ("nostalgia", 0.3)],
    "desire": [("love", 0.7), ("anticipation", 0.3)],
    "caring": [("love", 0.7), ("calm", 0.3)],
    "remorse": [("sadness", 0.7), ("nostalgia", 0.3)],
    "optimism": [("anticipation", 0.7), ("joy", 0.3)],
}

# ---------------------------------------------------------------------------
# Configurable model settings
# ---------------------------------------------------------------------------
_EMOTION_MODEL_NAME = "SamLowe/roberta-base-go_emotions"
_EMOTION_BATCH_SIZE = 16
_EMOTION_MAX_LENGTH = 512

# Max tokens for text encoding (MiniLM max is 256 word-pieces; we pre-truncate)
_MAX_TOKENS = 512

# ---------------------------------------------------------------------------
# Singleton models
# ---------------------------------------------------------------------------
_lock = threading.Lock()
_model: Any | None = None  # sentence-transformers (for encode_text)
_classifier: Any | None = None  # GoEmotions classifier pipeline


def _get_model():
    """Lazily load the sentence-transformer model (once)."""
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from sentence_transformers import SentenceTransformer
                _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def _get_classifier():
    """Lazily load the GoEmotions classifier pipeline (once).

    Performs a label integrity check on first load to ensure the model's
    output labels are compatible with ``GOEMOTION_WEIGHTS``.
    """
    global _classifier
    if _classifier is None:
        with _lock:
            if _classifier is None:
                from transformers import pipeline as hf_pipeline

                clf = hf_pipeline(
                    "text-classification",
                    model=_EMOTION_MODEL_NAME,
                    top_k=None,
                )
                # --- Label integrity check ---
                expected_labels = set(GOEMOTION_WEIGHTS.keys())
                model_labels = set(clf.model.config.id2label.values())
                if not expected_labels.issubset(model_labels):
                    missing = expected_labels - model_labels
                    raise RuntimeError(
                        f"Emotion model {_EMOTION_MODEL_NAME!r} is missing "
                        f"labels required by GOEMOTION_WEIGHTS: {missing}. "
                        f"Only models with the full GoEmotions 28-label set "
                        f"are compatible."
                    )
                _classifier = clf
    return _classifier


# ---------------------------------------------------------------------------
# Cached text encoding (retained for scene segmenter)
# ---------------------------------------------------------------------------
@functools.lru_cache(maxsize=256)
def encode_text(text: str) -> tuple[float, ...]:
    """Encode text and return a unit-normalized vector as a tuple.

    The tuple type keeps it hashable for the LRU cache.
    Truncates to ``_MAX_TOKENS`` whitespace tokens before encoding.

    This is intentionally public so the scene segmenter can reuse
    the same model + cache for paragraph-level semantic shift detection.
    """
    tokens = text.split()[:_MAX_TOKENS]
    truncated = " ".join(tokens)
    model = _get_model()
    vec = model.encode(truncated, convert_to_numpy=True)
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return tuple(vec.tolist())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _map_goemotion_scores(raw_scores: list[dict[str, Any]]) -> dict[str, float]:
    """Map a single text's GoEmotions output to our 12 categories.

    Parameters
    ----------
    raw_scores:
        List of dicts with ``"label"`` and ``"score"`` keys from the
        classifier (one entry per GoEmotions label when ``top_k=None``).

    Returns
    -------
    dict mapping our 12 category names to aggregated scores.
    """
    category_scores: dict[str, float] = {cat: 0.0 for cat in EMOTION_CATEGORIES}
    for item in raw_scores:
        label = item["label"]
        score = float(item["score"])
        if label in GOEMOTION_WEIGHTS:
            for category, weight in GOEMOTION_WEIGHTS[label]:
                category_scores[category] += score * weight
    # Clamp to [0, 1]
    return {k: min(1.0, max(0.0, v)) for k, v in category_scores.items()}


def _split_paragraphs(text: str) -> list[str]:
    """Split *text* into paragraphs on blank lines."""
    paragraphs: list[str] = []
    for chunk in re.split(r"\n\s*\n", text):
        chunk = chunk.strip()
        if chunk:
            paragraphs.append(chunk)
    # Fallback: treat whole text as one paragraph
    if not paragraphs and text.strip():
        paragraphs.append(text.strip())
    return paragraphs


def _split_sliding_window(text: str, window_size: int = 3) -> list[str]:
    """Split *text* into overlapping sentence windows.

    Uses a simple sentence-boundary heuristic (split on ``.``, ``!``, ``?``
    followed by whitespace).
    """
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]

    if len(sentences) <= window_size:
        return [" ".join(sentences)] if sentences else []

    windows: list[str] = []
    for i in range(len(sentences) - window_size + 1):
        windows.append(" ".join(sentences[i : i + window_size]))
    return windows


# ---------------------------------------------------------------------------
# Arc stabilization
# ---------------------------------------------------------------------------

def smooth_emotion_arc(
    raw_arc: list[dict[str, float]],
    *,
    alpha: float = 0.3,
    peak_threshold: float = 0.10,
    min_segment_chunks: int = 2,
) -> list[tuple[dict[str, float], str]]:
    """Stabilize a raw emotion arc.

    Applies three mechanisms in sequence:

    1. **EMA smoothing** — blends each chunk's scores with the previous
       chunk to dampen single-chunk spikes.
    2. **Peak detection threshold** — a new dominant emotion is only
       assigned when the top score exceeds the runner-up by at least
       *peak_threshold*; otherwise the previous dominant carries forward.
    3. **Minimum segment duration** — segments shorter than
       *min_segment_chunks* are absorbed into their longest neighbor.

    Parameters
    ----------
    raw_arc:
        List of per-chunk score dicts (category → float).
    alpha:
        EMA decay factor (0.0 = full carry-forward, 1.0 = no smoothing).
    peak_threshold:
        Minimum gap between 1st and 2nd place scores to trigger a
        dominant emotion change.
    min_segment_chunks:
        Minimum number of consecutive chunks for an emotion segment to
        survive merging.

    Returns
    -------
    List of ``(smoothed_scores_dict, dominant_emotion)`` tuples, one per
    input chunk.
    """
    if not raw_arc:
        return []

    if len(raw_arc) == 1:
        scores = dict(raw_arc[0])
        dominant = max(scores, key=lambda k: scores[k])
        return [(scores, dominant)]

    # ---- Step 1: EMA smoothing ----
    smoothed: list[dict[str, float]] = [dict(raw_arc[0])]
    for i in range(1, len(raw_arc)):
        prev = smoothed[-1]
        curr = raw_arc[i]
        blended = {
            cat: alpha * curr.get(cat, 0.0) + (1.0 - alpha) * prev.get(cat, 0.0)
            for cat in EMOTION_CATEGORIES
        }
        smoothed.append(blended)

    # ---- Step 2: Peak detection ----
    dominants: list[str] = []
    prev_dominant = max(smoothed[0], key=lambda k: smoothed[0][k])
    for scores in smoothed:
        sorted_vals = sorted(scores.values(), reverse=True)
        top = sorted_vals[0]
        runner_up = sorted_vals[1] if len(sorted_vals) > 1 else 0.0

        if top - runner_up >= peak_threshold:
            dominant = max(scores, key=lambda k: scores[k])
        else:
            dominant = prev_dominant

        dominants.append(dominant)
        prev_dominant = dominant

    # ---- Step 3: Minimum segment duration ----
    # Build segments: list of (start_inclusive, end_exclusive, emotion)
    segments: list[list[Any]] = []  # mutable: [start, end, emotion]
    seg_start = 0
    for i in range(1, len(dominants)):
        if dominants[i] != dominants[seg_start]:
            segments.append([seg_start, i, dominants[seg_start]])
            seg_start = i
    segments.append([seg_start, len(dominants), dominants[seg_start]])

    # Repeatedly absorb the shortest segment into its longest neighbor
    while len(segments) > 1:
        shortest_idx = min(
            range(len(segments)),
            key=lambda idx: segments[idx][1] - segments[idx][0],
        )
        shortest_len = segments[shortest_idx][1] - segments[shortest_idx][0]
        if shortest_len >= min_segment_chunks:
            break  # all segments are long enough

        if shortest_idx == 0:
            # First segment — absorb into right neighbor
            segments[1][0] = segments[0][0]
            segments.pop(0)
        elif shortest_idx == len(segments) - 1:
            # Last segment — absorb into left neighbor
            segments[-2][1] = segments[-1][1]
            segments.pop(-1)
        else:
            # Middle — absorb into the longer neighbor
            left_len = segments[shortest_idx - 1][1] - segments[shortest_idx - 1][0]
            right_len = segments[shortest_idx + 1][1] - segments[shortest_idx + 1][0]
            if left_len >= right_len:
                segments[shortest_idx - 1][1] = segments[shortest_idx][1]
            else:
                segments[shortest_idx + 1][0] = segments[shortest_idx][0]
            segments.pop(shortest_idx)

    # Re-assign dominants from the merged segments
    for start, end, emotion in segments:
        for j in range(start, end):
            dominants[j] = emotion

    # ---- Combine smoothed scores with stabilized dominants ----
    return list(zip(smoothed, dominants))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_emotion_scores(scene_text: str) -> dict[str, float]:
    """Classify *scene_text* and return aggregated emotion scores.

    Returns a dict mapping our 12 emotion category names to scores in
    ``[0.0, 1.0]``.  Uses the GoEmotions classifier with weighted
    category mapping on the full scene text (no chunking).
    """
    if not scene_text.strip():
        return {cat: 0.0 for cat in EMOTION_CATEGORIES}

    classifier = _get_classifier()
    results = classifier(
        scene_text,
        truncation=True,
        max_length=_EMOTION_MAX_LENGTH,
    )
    return _map_goemotion_scores(results)


def compute_emotion_arc(
    scene_text: str,
    *,
    strategy: Literal["paragraph", "sliding_window"] = "paragraph",
    window_size: int = 3,
    alpha: float = 0.3,
    peak_threshold: float = 0.10,
    min_segment_chunks: int = 2,
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    """Compute an emotion arc for a scene with sub-scene granularity.

    Chunks the scene text, classifies each chunk via batched inference,
    applies stabilization (EMA + peak gating + min segment duration),
    and returns both scene-level aggregate scores and a per-chunk
    emotion arc.

    Parameters
    ----------
    scene_text:
        Full text of the scene.
    strategy:
        Chunking strategy: ``"paragraph"`` (split on blank lines) or
        ``"sliding_window"`` (overlapping sentence windows).
    window_size:
        Number of sentences per window (only for ``"sliding_window"``).
    alpha:
        EMA decay factor for smoothing (lower = more smoothing).
    peak_threshold:
        Minimum score gap to assign a new dominant emotion.
    min_segment_chunks:
        Minimum segment length; shorter segments are absorbed.

    Returns
    -------
    ``(emotion_scores, emotion_arc)``
        - *emotion_scores*: dict mapping 12 category names to
          scene-level aggregated float scores.
        - *emotion_arc*: list of dicts, each with keys
          ``chunk_index``, ``text_preview``, ``dominant_emotion``,
          ``scores``.
    """
    empty_scores = {cat: 0.0 for cat in EMOTION_CATEGORIES}
    if not scene_text.strip():
        return empty_scores, []

    # 1. Chunk
    if strategy == "sliding_window":
        chunks = _split_sliding_window(scene_text, window_size=window_size)
    else:
        chunks = _split_paragraphs(scene_text)

    if not chunks:
        return empty_scores, []

    # 2. Batched inference
    classifier = _get_classifier()
    all_results = classifier(
        chunks,
        batch_size=_EMOTION_BATCH_SIZE,
        truncation=True,
        max_length=_EMOTION_MAX_LENGTH,
    )

    # 3. Map GoEmotions → our 12 categories
    raw_arc: list[dict[str, float]] = [
        _map_goemotion_scores(chunk_results) for chunk_results in all_results
    ]

    # 4. Stabilize
    stabilized = smooth_emotion_arc(
        raw_arc,
        alpha=alpha,
        peak_threshold=peak_threshold,
        min_segment_chunks=min_segment_chunks,
    )

    # 5. Build output arc with metadata
    arc_output: list[dict[str, Any]] = []
    for i, ((scores, dominant), chunk_text) in enumerate(zip(stabilized, chunks)):
        preview = chunk_text[:80] + ("..." if len(chunk_text) > 80 else "")
        arc_output.append({
            "chunk_index": i,
            "text_preview": preview,
            "dominant_emotion": dominant,
            "scores": {k: round(v, 4) for k, v in scores.items()},
        })

    # 6. Aggregate scene-level scores (mean of stabilized arc)
    scene_scores: dict[str, float] = {cat: 0.0 for cat in EMOTION_CATEGORIES}
    for scores, _ in stabilized:
        for cat, val in scores.items():
            scene_scores[cat] += val
    n = len(stabilized)
    scene_scores = {k: round(v / n, 4) for k, v in scene_scores.items()}

    return scene_scores, arc_output
