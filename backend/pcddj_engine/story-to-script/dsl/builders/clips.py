"""Clip builder — generates per-scene clips routed to the correct track.

Each builder function returns a ``dict[str, list[DraftClip]]`` mapping
track IDs to their clip lists.  The compiler merges these into the
scene's ``tracks`` dict.

Ordering:
    The ``order`` field is a **scene-global** counter shared across all
    voice tracks.  It defines the reading sequence so the Asset Resolver
    can compute timing correctly even though clips live on separate tracks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from dsl.constants import (
    EMOTION_TO_MOOD,
    SFX_IMPACT_MIN_PUNCTUATION,
    SFX_IMPACT_MIN_SHORT_STREAK,
    SFX_TEXTURE_MIN_ENERGY,
    TRACK_TYPE_EQ_DEFAULTS,
    atmosphere_for,
    energy_to_suffix,
)
from dsl.schema import DraftClip


# ---------------------------------------------------------------------------
# Voice clip helpers
# ---------------------------------------------------------------------------

def _sentence_overlaps_dialogue(
    sentence: str,
    sent_idx: int,
    sentences: list[str],
    dialogue_turns: list[dict[str, Any]],
    char_offset: int,
) -> bool:
    """Return True if *sentence* overlaps any dialogue turn by char range.

    We approximate character positions by summing lengths of earlier
    sentences (since the Narrative Plan preserves original text in the
    ``sentences`` list).
    """
    start = char_offset
    for i, s in enumerate(sentences):
        if i == sent_idx:
            break
        start += len(s)
    end = start + len(sentence)

    for dt in dialogue_turns:
        dt_start = dt.get("start_char", 0)
        dt_end = dt.get("end_char", 0)
        if dt_start < end and dt_end > start:
            return True
    return False


# ---------------------------------------------------------------------------
# Narration segment index
# ---------------------------------------------------------------------------

_VALID_SEGMENT_TYPES = frozenset({
    "action", "description", "scene_setting", "transition", "inner_thought",
})


def _build_segment_index(
    narration_segments: list[dict[str, Any]],
) -> list[tuple[str, str | None, bool]]:
    """Build a list of ``(text, segment_type, has_sound_event)`` from raw dicts.

    Returns a list (preserving order) for substring matching against sentences.
    """
    result: list[tuple[str, str | None, bool]] = []
    for seg in narration_segments:
        if not isinstance(seg, dict):
            continue
        text = str(seg.get("text", "")).strip()
        if not text:
            continue
        seg_type = seg.get("segment_type")
        if seg_type not in _VALID_SEGMENT_TYPES:
            seg_type = None
        has_sound = bool(seg.get("has_sound_event", False))
        result.append((text, seg_type, has_sound))
    return result


def _lookup_segment(
    sentence: str,
    segment_index: list[tuple[str, str | None, bool]],
) -> tuple[str | None, bool | None]:
    """Find the best-matching narration segment for *sentence*.

    Uses substring containment (segment text in sentence or vice versa).
    Returns ``(segment_type, has_sound_event)`` or ``(None, None)`` if
    no match is found.
    """
    sent_lower = sentence.lower()
    for seg_text, seg_type, has_sound in segment_index:
        seg_lower = seg_text.lower()
        if seg_lower in sent_lower or sent_lower in seg_lower:
            return seg_type, has_sound
    return None, None


# ---------------------------------------------------------------------------
# Attribution stripper (Flag 1 — Requirement 3)
# ---------------------------------------------------------------------------

_ATTRIBUTION_VERBS = frozenset({
    "said", "replied", "answered", "asked", "whispered",
    "shouted", "muttered", "called", "cried", "exclaimed",
    "continued", "added", "noted", "observed", "stated",
    "yelled", "screamed", "murmured", "hissed", "sighed",
    "laughed", "groaned", "snapped", "pleaded", "demanded",
})

_PERFORMANCE_VERBS = frozenset({
    "whispered", "shouted", "muttered", "screamed", "yelled",
    "murmured", "hissed", "sighed", "laughed", "groaned",
    "snapped", "pleaded",
})

_ATTRIBUTION_RE = re.compile(
    r",?\s*"
    r"(?P<subject>[\w\s]+?)\s+"
    r"(?P<verb>" + "|".join(_ATTRIBUTION_VERBS) + r")"
    r"(?P<rest>[^\"']*?)$",
    re.IGNORECASE,
)

_ACTION_PRE_RE = re.compile(
    r"^(?P<action>[\w\s]+?)\s+"
    r"(?:and\s+)?"
    r"(?:" + "|".join(_ATTRIBUTION_VERBS) + r")"
    r"\s*,?\s*$",
    re.IGNORECASE,
)

_ACTION_PHRASE_RE = re.compile(
    r"\b(?:grabbing|pulling|pushing|looking|turning|leaning|"
    r"reaching|holding|dropping|running|walking|stepping|"
    r"sitting|standing|rising|falling|opening|closing|"
    r"nodding|shaking|pointing|waving|touching|lifting)\b"
    r"[^,\"']*",
    re.IGNORECASE,
)


@dataclass(slots=True)
class AttributionResult:
    """Result of stripping attribution from a dialogue-containing sentence."""
    clean_text: str
    sfx_hints: list[str] = field(default_factory=list)
    performance: str | None = None
    speaker: str | None = None


def strip_attribution(sentence: str, dialogue_text: str) -> AttributionResult:
    """Strip attribution from *sentence*, returning clean dialogue + metadata.

    Routes physical actions to ``sfx_hints`` and speech-verb delivery
    cues to ``performance``.
    """
    result = AttributionResult(clean_text=dialogue_text)

    attribution_part = sentence.replace(
        f'"{dialogue_text}"', ""
    ).replace(
        f"'{dialogue_text}'", ""
    ).replace(
        f"\u201c{dialogue_text}\u201d", ""
    ).strip(" ,\"'\u201c\u201d")

    if not attribution_part or len(attribution_part) <= 2:
        return result

    attr_lower = attribution_part.lower()

    for verb in _PERFORMANCE_VERBS:
        if verb in attr_lower:
            result.performance = verb
            break

    m = _ATTRIBUTION_RE.match(attribution_part)
    if m:
        result.speaker = m.group("subject").strip()
        rest = m.group("rest").strip(" ,.")
        if rest:
            for action_m in _ACTION_PHRASE_RE.finditer(rest):
                hint = action_m.group(0).strip(" ,.")
                if hint:
                    sfx_label = re.sub(r"\s+", "_", hint.lower().strip())
                    result.sfx_hints.append(sfx_label)
    else:
        m2 = _ACTION_PRE_RE.match(attribution_part)
        if m2:
            action = m2.group("action").strip()
            for action_m in _ACTION_PHRASE_RE.finditer(action):
                hint = action_m.group(0).strip(" ,.")
                if hint:
                    sfx_label = re.sub(r"\s+", "_", hint.lower().strip())
                    result.sfx_hints.append(sfx_label)

    return result


# ---------------------------------------------------------------------------
# Public builders
# ---------------------------------------------------------------------------

def build_voice_clips(
    scene: dict[str, Any],
    speaker_track_map: dict[str, str],
    *,
    project_type: str = "audio_drama",
) -> dict[str, list[DraftClip]]:
    """Build narration and dialogue clips for a scene.

    Dispatches to audiobook (narrator reads everything) or audio drama
    (characters only, attribution stripped) based on *project_type*.

    Returns a dict mapping track IDs to lists of :class:`DraftClip`.
    """
    if project_type == "audiobook":
        return _build_audiobook_voice_clips(scene)
    return _build_audiodrama_voice_clips(scene, speaker_track_map)


def _build_audiobook_voice_clips(
    scene: dict[str, Any],
) -> dict[str, list[DraftClip]]:
    """AudioBook: narrator reads every sentence in order, with attribution."""
    structure = scene.get("structure", {})
    sentences: list[str] = structure.get("sentences", [])
    narration_segments = structure.get("narration_segments", [])
    segment_index = _build_segment_index(narration_segments)

    clips: list[DraftClip] = []
    for order, sentence in enumerate(sentences):
        sent_text = sentence.strip()
        if not sent_text:
            continue
        seg_type, has_sound = _lookup_segment(sent_text, segment_index)
        clips.append(
            DraftClip(
                tts_text=sent_text,
                order=order,
                segment_type=seg_type,  # type: ignore[arg-type]
                has_sound_event=has_sound,
                eq_preset=TRACK_TYPE_EQ_DEFAULTS["voice"],  # type: ignore[arg-type]
            )
        )

    if clips:
        return {"narrator": clips}
    return {}


def _build_audiodrama_voice_clips(
    scene: dict[str, Any],
    speaker_track_map: dict[str, str],
) -> dict[str, list[DraftClip]]:
    """AudioDrama: only dialogue becomes voice clips; narration is silent."""
    structure = scene.get("structure", {})
    sentences: list[str] = structure.get("sentences", [])
    dialogue_turns: list[dict[str, Any]] = structure.get("dialogue_turns", [])

    clips_by_track: dict[str, list[DraftClip]] = {}
    order_counter = 0

    sorted_dialogue = sorted(
        dialogue_turns, key=lambda dt: dt.get("start_char", 0),
    )

    for sentence in sentences:
        sent_text = sentence.strip()
        if not sent_text:
            continue

        matched_dialogue: dict[str, Any] | None = None
        for dt in sorted_dialogue:
            dt_text = dt.get("text", "")
            if dt_text and dt_text in sent_text:
                matched_dialogue = dt
                break

        if matched_dialogue is None:
            continue

        sorted_dialogue = [
            d for d in sorted_dialogue if d is not matched_dialogue
        ]

        quote_style = matched_dialogue.get("quote_style", "double")
        if quote_style == "indirect":
            continue

        speaker = matched_dialogue.get("speaker", "unknown")
        track_id = speaker_track_map.get(speaker, f"character_{speaker}")

        attr_result = strip_attribution(sent_text, matched_dialogue["text"])
        delivery_hint = matched_dialogue.get("delivery_hint")

        clips_by_track.setdefault(track_id, []).append(
            DraftClip(
                tts_text=attr_result.clean_text,
                order=order_counter,
                delivery=attr_result.performance or delivery_hint,
                dramatic_function=matched_dialogue.get("dramatic_function"),
                eq_preset=TRACK_TYPE_EQ_DEFAULTS["voice"],  # type: ignore[arg-type]
            )
        )
        order_counter += 1

    return clips_by_track


def build_music_clips(
    scene: dict[str, Any],
    energy: float,
    *,
    position: str | None = None,
) -> dict[str, list[DraftClip]]:
    """Build a music clip for a scene with an explicit position tag.

    The compiler calls this only for intro/outro/background scenes.

    Returns ``{"music": [clip]}``."""
    interp = scene.get("interpretation", {})
    emotion = interp.get("primary_emotion", "neutral")

    mood_base = EMOTION_TO_MOOD.get(emotion, "neutral")
    suffix = energy_to_suffix(energy)
    mood = f"{mood_base}{suffix}"

    loop = position == "background"

    clip = DraftClip(
        mood=mood,
        energy_hint=round(energy, 2),
        loop=loop or None,
        position=position,  # type: ignore[arg-type]
    )
    return {"music": [clip]}


def build_ambience_clips(
    scene: dict[str, Any],
) -> dict[str, list[DraftClip]]:
    """Build a single ambience clip for a scene.

    Prefers Gemini-extracted ambience cues when available, falling
    back to the static emotion + style lookup.

    Returns ``{"ambience": [clip]}``."""
    structure = scene.get("structure", {})
    ambience_cue = structure.get("ambience_cue")

    if ambience_cue and isinstance(ambience_cue, dict):
        atmo = ambience_cue.get("primary_atmosphere")
        if atmo:
            clip = DraftClip(
                atmosphere=atmo,
                loop=True,
            )
            return {"ambience": [clip]}

    # Fallback: static lookup from emotion + scene style
    interp = scene.get("interpretation", {})
    emotion = interp.get("primary_emotion", "neutral")
    style = interp.get("scene_style", "balanced")

    atmo = atmosphere_for(emotion, style)

    clip = DraftClip(
        atmosphere=atmo,
        loop=True,
    )
    return {"ambience": [clip]}


def build_sfx_clips(
    scene: dict[str, Any],
    energy: float,
    has_sfx_track: bool,
    voice_clips: dict[str, list[DraftClip]] | None = None,
    *,
    project_type: str = "audio_drama",
) -> dict[str, list[DraftClip]]:
    """Build SFX clips for a scene.

    Returns empty for audiobook mode.  For audio drama, prefers
    Gemini/KB-extracted SFX events when available, falling back
    to the legacy numeric-threshold heuristics.

    Returns ``{"sfx": [clip, ...]}`` or an empty dict if no SFX needed.
    """
    if project_type == "audiobook" or not has_sfx_track:
        return {}

    structure = scene.get("structure", {})
    sfx_events: list[dict[str, Any]] = structure.get("sfx_events", [])

    # Flatten voice clips for anchor matching (Fix 3 uses this fully)
    flat_voice: list[DraftClip] = []
    if voice_clips:
        for clip_list in voice_clips.values():
            flat_voice.extend(clip_list)
        flat_voice.sort(key=lambda c: c.order if c.order is not None else 10_000)

    clips: list[DraftClip] = []

    # --- Primary path: extracted audio cues (LLM or KB) --------------------
    for event in sfx_events:
        if not isinstance(event, dict):
            continue
        semantic_role = event.get("semantic_role", "impact")
        if semantic_role not in _VALID_SEMANTIC_ROLES:
            semantic_role = "impact"

        anchor_order, anchor_position = _match_sfx_anchor(
            event, flat_voice, semantic_role,
        )
        clips.append(
            DraftClip(
                sfx_hint=event.get("sfx_label", "unknown_sfx"),
                semantic_role=semantic_role,  # type: ignore[arg-type]
                anchor_order=anchor_order,
                anchor_position=anchor_position,  # type: ignore[arg-type]
            )
        )

    # --- Fallback: legacy numeric thresholds --------------------------------
    if not clips:
        signals = scene.get("signals", {})
        interp = scene.get("interpretation", {})

        short_streak = signals.get("short_sentence_streak", 0)
        punctuation = signals.get("punctuation_score", 0.0)
        silence_intent = interp.get("silence_intent", "none")

        # Impact SFX — short action bursts
        if (
            short_streak >= SFX_IMPACT_MIN_SHORT_STREAK
            and punctuation > SFX_IMPACT_MIN_PUNCTUATION
        ):
            clips.append(
                DraftClip(
                    sfx_hint="impact_accent",
                    semantic_role="impact",
                )
            )

        # Texture SFX — tension risers
        if silence_intent == "long" and energy >= SFX_TEXTURE_MIN_ENERGY:
            clips.append(
                DraftClip(
                    sfx_hint="tension_riser",
                    semantic_role="texture",
                )
            )

        # Action-segment SFX — voice clips flagged has_sound_event by the LLM
        if not clips and flat_voice:
            for vc in flat_voice:
                if vc.has_sound_event and vc.segment_type == "action":
                    clips.append(
                        DraftClip(
                            sfx_hint="action_sfx",
                            semantic_role="impact",
                            anchor_order=vc.order,
                            anchor_position="under",  # type: ignore[arg-type]
                        )
                    )

    if clips:
        return {"sfx": clips}
    return {}


# ---------------------------------------------------------------------------
# SFX helpers
# ---------------------------------------------------------------------------
_VALID_SEMANTIC_ROLES = frozenset({"impact", "movement", "ambience", "interaction", "texture"})

_IMPACT_ROLES = frozenset({"impact", "interaction"})


def _match_sfx_anchor(
    event: dict[str, Any],
    flat_voice: list[DraftClip],
    semantic_role: str,
) -> tuple[int | None, str | None]:
    """Match an SFX event to the voice clip it should accompany.

    Uses ``source_text`` (substring containment against ``tts_text``)
    then falls back to ``order_hint`` mapped to the nearest voice clip.

    Returns ``(anchor_order, anchor_position)`` or ``(None, None)``.
    """
    if not flat_voice:
        return None, None

    position = "after" if semantic_role in _IMPACT_ROLES else "under"

    # Try source_text match first
    source_text = str(event.get("source_text", "")).strip().lower()
    if source_text:
        for vc in flat_voice:
            if vc.tts_text and source_text in vc.tts_text.lower():
                return vc.order, position

    # Fallback: map order_hint to nearest voice clip by index
    order_hint = event.get("order_hint")
    if order_hint is not None:
        try:
            idx = int(order_hint)
        except (TypeError, ValueError):
            return None, None
        if 0 <= idx < len(flat_voice):
            return flat_voice[idx].order, position
        if flat_voice:
            return flat_voice[-1].order, position

    return None, None
