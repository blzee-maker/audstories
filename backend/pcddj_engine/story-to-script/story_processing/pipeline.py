"""Pipeline orchestrator — end-to-end story processing.

Implements the full deterministic + controlled AI pipeline:

    Story Text → Preprocessing → NLP → Signals → Classification → Validation → Narrative Plan

Deterministic layers are parallelized per scene.
AI classification runs sequentially to respect local LLM throughput.
"""

from __future__ import annotations

import hashlib
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from typing import Any

from story_processing.ai.classifier import classify
from story_processing.ai.llm_client import LLMClient, QuotaExhaustedError
from story_processing.context import StoryContextBuilder, reconcile_speakers
from story_processing.narrative_plan import assemble, serialize
from story_processing.nlp.audio_cue_extractor import extract_audio_cues
from story_processing.nlp.sound_knowledge_base import extract_sound_cues_from_nlp
from story_processing.nlp.dialogue_extractor import (
    DialogueTurn,
    extract_dialogue,
    extract_indirect_speech,
    merge_dialogue,
)
from story_processing.nlp.scene_segmenter import (
    SceneSpan,
    detect_format,
    segment_scenes,
)
from story_processing.nlp.spacy_pipeline import run_spacy
from story_processing.nlp.speaker_resolver import resolve_speakers
from story_processing.preprocessing.normalizer import normalize
from story_processing.signals.semantic_metrics import compute_emotion_arc
from story_processing.signals.structure_metrics import (
    StructureSignals,
    compute_structure_signals,
)
from story_processing.validation.validator import validate_interpretation

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Scene heading detection and stripping
# ---------------------------------------------------------------------------

_SCENE_HEADING_RE = re.compile(
    r"^\s*(Scene|Chapter|Part|Act)\s*"
    r"(\d+|[IVXLCDM]+|one|two|three|four|five|"
    r"six|seven|eight|nine|ten)?"
    r"\s*[:\-\u2014]?\s*[^\n]*\n*",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True, slots=True)
class HeadingResult:
    """Result of stripping a scene heading from text."""
    body: str
    title: str | None


def strip_scene_heading(text: str, *, scene_index: int = 0) -> HeadingResult:
    """Strip a scene/chapter heading from the start of *text*.

    Returns a ``HeadingResult`` with the cleaned body and extracted title.
    If no heading is found, ``title`` falls back to ``Scene {index + 1}``.
    """
    m = _SCENE_HEADING_RE.match(text)
    if m is None:
        return HeadingResult(body=text, title=None)

    title = extract_scene_name(m)
    body = text[m.end():].lstrip("\n")
    return HeadingResult(body=body, title=title)


def extract_scene_name(heading_match: re.Match[str]) -> str:
    """Extract a human-readable scene name from a heading regex match."""
    full_heading = heading_match.group(0).strip()

    title_match = re.search(r"[:\-\u2014]\s*(.+)$", full_heading)
    if title_match:
        return title_match.group(1).strip()

    return full_heading


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def process_story(
    text: str,
    llm_client: LLMClient | None = None,
    *,
    model_name: str = "en_core_web_lg",
    project_type: str = "audio_drama",
) -> dict[str, Any]:
    """Process a story end-to-end and return a Narrative Plan dict.

    Parameters
    ----------
    text:
        Raw story text.
    llm_client:
        Optional LLM client for AI classification.  When ``None``,
        the pipeline uses heuristic-only classification.
    model_name:
        spaCy model name (default ``"en_core_web_lg"``).
    project_type:
        ``"audiobook"`` or ``"audio_drama"``.

    Returns
    -------
    dict — Narrative Plan conforming to ``NarrativePlan`` schema.
    """
    # 1. Detect text format on raw input (before normalization strips
    #    indentation cues needed for Normal Indent detection).
    text_format = detect_format(text)

    # 2. Preprocess
    normalized = normalize(text)
    if not normalized:
        return assemble([])

    # 3. Run spaCy
    doc = run_spacy(normalized, model_name=model_name)

    # 4. Extract dialogue
    #    a) Regex-based direct speech (operates on normalized text)
    #    b) spaCy dep-parse indirect/reported speech (operates on Doc)
    #    c) Merge + resolve overlaps (direct takes priority)
    direct_dialogue = extract_dialogue(normalized)
    indirect_dialogue = extract_indirect_speech(doc)
    all_dialogue = merge_dialogue(direct_dialogue, indirect_dialogue)

    # 5. Segment scenes (pass detected format so blank-line semantics
    #    are interpreted correctly for indent-format text).
    scenes = segment_scenes(
        doc,
        normalized,
        format_hint=text_format if text_format != "unknown" else "auto",
    )
    if not scenes:
        # Treat the whole text as a single scene
        sentences = list(doc.sents)
        scenes = [
            SceneSpan(
                scene_index=0,
                sent_start=0,
                sent_end=len(sentences),
                char_start=0,
                char_end=len(normalized),
            )
        ]

    # 6. Parallel: extract structure + signals per scene
    sentences = list(doc.sents)

    def _extract_scene_data(span: SceneSpan) -> dict[str, Any]:
        return _process_single_scene(
            span=span,
            sentences=sentences,
            all_dialogue=all_dialogue,
            doc=doc,
            normalized=normalized,
        )

    with ThreadPoolExecutor() as pool:
        scene_data_list = list(pool.map(_extract_scene_data, scenes))

    # 6b. Reconcile speakers globally (cross-scene character continuity)
    reconcile_speakers(scene_data_list, doc)

    # 7. Sequential: AI classification + audio cue extraction per scene
    #    with cross-scene context (rolling state builder).
    ctx_builder = StoryContextBuilder(total_scenes=len(scene_data_list))

    for i, scene_data in enumerate(scene_data_list):
        # 7a. Build cross-scene context for this scene
        story_ctx = ctx_builder.get_context(i)

        # 7b. Classification (heuristic or LLM, context-aware)
        merged_signals = _merge_signals(scene_data)
        try:
            raw_interp = classify(
                merged_signals, llm_client, story_context=story_ctx,
            )
        except QuotaExhaustedError:
            # Circuit-breaker: stop using LLM for the remainder of this story.
            logger.error(
                "LLM quota exhausted. Switching remaining scenes to heuristic/KB mode."
            )
            llm_client = None
            raw_interp = classify(
                merged_signals, llm_client, story_context=story_ctx,
            )
        scene_data["interpretation"] = validate_interpretation(
            structure=scene_data["structure"],
            signals=merged_signals,
            interpretation=raw_interp,
        )

        # 7c. Advance rolling context with this scene's data
        ctx_builder.advance(scene_data)

        # 7d. Audio cue extraction
        if llm_client is not None:
            try:
                scene_text = " ".join(
                    s.strip()
                    for s in scene_data["structure"]["sentences"]
                    if s.strip()
                )
                audio_cues = extract_audio_cues(
                    scene_text=scene_text,
                    dialogue_turns=scene_data["structure"]["dialogue_turns"],
                    llm_client=llm_client,
                    project_type=project_type,
                )
                scene_data["structure"]["sfx_events"] = [
                    asdict(e) for e in audio_cues.sfx_events
                ]
                scene_data["structure"]["ambience_cue"] = (
                    asdict(audio_cues.ambience) if audio_cues.ambience else None
                )
                scene_data["structure"]["narration_segments"] = [
                    asdict(s) for s in audio_cues.narration_segments
                ]
            except QuotaExhaustedError:
                # Circuit-breaker: audio cue LLM also can't run; fall back to KB.
                logger.error(
                    "LLM quota exhausted during audio cue extraction. Switching to KB mode."
                )
                llm_client = None
        if llm_client is None:
            # Knowledge-base fallback: extract audio cues from spaCy parse
            scene_span = scenes[i]
            doc_slice = doc.char_span(
                scene_span.char_start, scene_span.char_end,
                alignment_mode="expand",
            )
            kb_sfx, kb_ambience = extract_sound_cues_from_nlp(
                doc_slice, scene_data["structure"]["sentences"],
            )
            scene_data["structure"]["sfx_events"] = kb_sfx
            if kb_ambience:
                scene_data["structure"]["ambience_cue"] = {
                    "primary_atmosphere": kb_ambience[0],
                    "atmosphere_description": ", ".join(kb_ambience),
                    "intensity": "moderate",
                    "evolves": False,
                }
            else:
                scene_data["structure"]["ambience_cue"] = None
            scene_data["structure"]["narration_segments"] = []

    # 8. Assemble
    return assemble(scene_data_list)


def process_story_json(
    text: str,
    llm_client: LLMClient | None = None,
    *,
    model_name: str = "en_core_web_lg",
    project_type: str = "audio_drama",
) -> bytes:
    """Like :func:`process_story` but returns serialized JSON bytes."""
    plan = process_story(
        text, llm_client, model_name=model_name, project_type=project_type,
    )
    return serialize(plan)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _process_single_scene(
    span: SceneSpan,
    sentences: list,
    all_dialogue: list[DialogueTurn],
    doc,
    normalized: str,
) -> dict[str, Any]:
    """Extract structure + signals for a single scene (parallelizable)."""
    # Slice sentences for this scene
    scene_sents = sentences[span.sent_start : span.sent_end]
    scene_text = normalized[span.char_start : span.char_end]

    # Deterministic scene ID: content-based hash for reproducibility
    digest = hashlib.sha256(
        f"{span.scene_index}:{scene_text}".encode()
    ).hexdigest()[:8]
    scene_id = f"scene_{span.scene_index:03d}_{digest}"

    # Filter dialogue turns that overlap this scene
    scene_dialogue = [
        dt
        for dt in all_dialogue
        if dt.start_char < span.char_end and dt.end_char > span.char_start
    ]

    # Speaker resolution
    attributed = resolve_speakers(doc, scene_dialogue)
    speakers = sorted(set(a.speaker for a in attributed))

    # Structure signals
    struct_signals = compute_structure_signals(scene_sents, scene_dialogue, scene_text)

    # Semantic signals (emotion arc includes scene-level aggregate scores)
    emotion_scores, emotion_arc = compute_emotion_arc(scene_text)

    # Strip scene headings from sentence text so they don't become TTS clips.
    # The heading is extracted as the scene's human-readable title.
    raw_sentences = [sent.text for sent in scene_sents]
    scene_title: str | None = None
    if raw_sentences:
        heading_result = strip_scene_heading(
            raw_sentences[0], scene_index=span.scene_index,
        )
        if heading_result.title is not None:
            scene_title = heading_result.title
            cleaned_first = heading_result.body.strip()
            if cleaned_first:
                raw_sentences[0] = cleaned_first
            else:
                raw_sentences = raw_sentences[1:]

    clean_sentences = [s for s in raw_sentences if s.strip()]

    # Build output
    structure = {
        "scene_id": scene_id,
        "sentence_count": len(clean_sentences),
        "word_count": struct_signals.word_count,
        "sentences": clean_sentences,
        "dialogue_turns": [
            {
                "speaker": a.speaker,
                "text": a.text,
                "start_char": a.start_char,
                "end_char": a.end_char,
                "quote_style": a.quote_style,
            }
            for a in attributed
        ],
        "speakers": speakers,
    }
    if scene_title:
        structure["scene_title"] = scene_title

    signals = {
        "avg_sentence_length": round(struct_signals.avg_sentence_length, 3),
        "sentence_length_variance": round(struct_signals.sentence_length_variance, 3),
        "short_sentence_streak": struct_signals.short_sentence_streak,
        "punctuation_score": round(struct_signals.punctuation_score, 3),
        "action_verb_density": round(struct_signals.action_verb_density, 3),
        "dialogue_ratio": round(struct_signals.dialogue_ratio, 3),
        "dialogue_turn_count": struct_signals.dialogue_turn_count,
        "avg_dialogue_length": round(struct_signals.avg_dialogue_length, 3),
        "emotion_scores": {k: round(v, 4) for k, v in emotion_scores.items()},
        "emotion_arc": emotion_arc,
    }

    return {
        "scene_id": scene_id,
        "structure": structure,
        "signals": signals,
        # "interpretation" will be added after classification
    }


def _merge_signals(scene_data: dict[str, Any]) -> dict[str, Any]:
    """Flatten signals dict for classifier consumption."""
    signals = dict(scene_data["signals"])
    # Also add sentence_count for heuristic rules
    signals["sentence_count"] = scene_data["structure"]["sentence_count"]
    return signals
