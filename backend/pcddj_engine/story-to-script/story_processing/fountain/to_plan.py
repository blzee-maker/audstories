"""Map Fountain AST to Narrative Plan-compatible dictionaries."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from typing import Any

from story_processing.narrative_plan import serialize
from story_processing.validation.schema import NarrativePlan

from .ast import ActionBlock, DialogueBlock, ScriptAST
from .parser import parse_fountain
from .sound_hints import extract_sound_hints

_VOICE_OVER_EXTS = {"V.O.", "VO", "V/O"}
_EMOTION_KEYS = (
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
_DELIVERY_MAP = {
    "whispering": "whispered",
    "whisper": "whispered",
    "shouting": "shouted",
    "shout": "shouted",
    "yelling": "shouted",
    "calmly": "calm",
    "calm": "calm",
    "urgently": "urgent",
    "urgent": "urgent",
    "then": "pause_then",
    "quietly": "soft",
    "softly": "soft",
    "in a whisper": "whispered",
    "muttering": "muttered",
    "mutter": "muttered",
    "angrily": "angry",
    "furious": "angry",
    "sadly": "sad",
    "nervously": "nervous",
    "hesitant": "hesitant",
    "hesitantly": "hesitant",
}


def _scene_id(scene_index: int, heading: str) -> str:
    digest = hashlib.sha1(f"{scene_index}:{heading}".encode("utf-8")).hexdigest()[:8]
    return f"scene_{scene_index:03d}_{digest}"


def _count_words(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text))


def _dialogue_turn(
    speaker: str,
    text: str,
    start_char: int,
    end_char: int,
) -> dict[str, Any]:
    return {
        "speaker": speaker,
        "text": text,
        "start_char": max(0, start_char),
        "end_char": max(0, end_char),
        "quote_style": "double",
    }


def _scene_defaults() -> tuple[dict[str, float], dict[str, Any]]:
    emotion_scores = {k: 0.0 for k in _EMOTION_KEYS}
    emotion_scores["neutral"] = 1.0
    interpretation = {
        "primary_emotion": "neutral",
        "energy_level": 5,
        "emotion_intensity": 5,
        "scene_style": "balanced",
        "silence_intent": "none",
        "confidence_score": 0.8,
    }
    return emotion_scores, interpretation


def _classify_dramatic_function(
    *,
    idx: int,
    total: int,
    turn: dict[str, Any],
    previous_turn: dict[str, Any] | None,
    next_turn: dict[str, Any] | None,
    block_index: int,
    scene_blocks: list[Any],
    is_vo: bool,
    energy_level: int,
) -> str:
    text = str(turn.get("text", "")).strip()

    if total <= 0:
        return "scene_entry"

    if block_index > 0 and isinstance(scene_blocks[block_index - 1], ActionBlock):
        prev_action = scene_blocks[block_index - 1]
        marker = str(prev_action.marker or "").strip().upper()
        if prev_action.kind == "sfx" or marker == "SFX":
            return "response_to_sfx"

    if text.endswith("?"):
        if next_turn is None:
            return "question_unanswered"
        next_block_idx = int(next_turn.get("_block_index", block_index + 1))
        between = scene_blocks[block_index + 1:next_block_idx]
        if any(isinstance(block, ActionBlock) for block in between):
            return "question_unanswered"
        return "question"

    if previous_turn is not None:
        prev_text = str(previous_turn.get("text", "")).strip()
        prev_speaker = str(previous_turn.get("speaker", "")).strip().upper()
        curr_speaker = str(turn.get("speaker", "")).strip().upper()
        if (
            curr_speaker
            and prev_speaker
            and curr_speaker != prev_speaker
            and _count_words(text) <= 6
            and _count_words(prev_text) <= 6
        ):
            return "rapid_exchange"

    if is_vo:
        return "internal"

    delivery_hint = str(turn.get("delivery_hint", "")).strip().lower()
    if "!" in text and energy_level >= 7:
        return "revelation"
    if delivery_hint in {"shouted", "urgent"}:
        return "revelation"

    if idx == total - 1:
        return "scene_close"
    if idx == 0:
        return "scene_entry"

    return "dialogue"


def _tag_dramatic_functions(
    dialogue_turns: list[dict[str, Any]],
    scene_blocks: list[Any],
    energy_level: int,
) -> None:
    for idx, turn in enumerate(dialogue_turns):
        previous_turn = dialogue_turns[idx - 1] if idx > 0 else None
        next_turn = dialogue_turns[idx + 1] if idx + 1 < len(dialogue_turns) else None
        block_index = int(turn.get("_block_index", idx))
        is_vo = bool(turn.get("_is_vo", False))
        turn["dramatic_function"] = _classify_dramatic_function(
            idx=idx,
            total=len(dialogue_turns),
            turn=turn,
            previous_turn=previous_turn,
            next_turn=next_turn,
            block_index=block_index,
            scene_blocks=scene_blocks,
            is_vo=is_vo,
            energy_level=energy_level,
        )

    for turn in dialogue_turns:
        turn.pop("_block_index", None)
        turn.pop("_is_vo", None)


def _normalize_delivery(parenthetical: str | None) -> str | None:
    if not parenthetical:
        return None
    key = re.sub(r"\s+", " ", parenthetical.strip().lower())
    if key in _DELIVERY_MAP:
        return _DELIVERY_MAP[key]
    return key[:40] if key else None


def _scene_energy_from_text(
    sentence_texts: list[str],
    action_notes: list[str],
    dialogue_turns: list[dict[str, Any]],
) -> int:
    text = " ".join(sentence_texts + action_notes).strip()
    if not text:
        return 5
    exclam = text.count("!")
    question = text.count("?")
    ellipsis = text.count("...")
    commas = text.count(",")
    caps_words = len(re.findall(r"\b[A-Z]{3,}\b", text))
    short_lines = sum(1 for s in sentence_texts if _count_words(s) <= 4)
    long_lines = sum(1 for s in sentence_texts if _count_words(s) >= 18)
    dialogue_ratio = (len(dialogue_turns) / len(sentence_texts)) if sentence_texts else 0.0
    action_words = _count_words(" ".join(action_notes))
    all_words = max(1, _count_words(text))
    action_density = action_words / all_words

    score = 5.0
    score += min(2.0, exclam * 0.4)
    score += min(1.0, question * 0.2)
    score += min(1.0, caps_words * 0.4)
    score += min(1.0, short_lines * 0.2)
    score += min(0.8, dialogue_ratio * 0.8)
    score += min(1.0, action_density * 2.2)
    score -= min(1.0, ellipsis * 0.2)
    score -= min(0.6, commas * 0.04)
    score -= min(0.6, long_lines * 0.2)
    return max(1, min(10, int(round(score))))


def _scene_mood_from_text(
    sentence_texts: list[str],
    action_notes: list[str],
    energy_level: int,
) -> str:
    text = " ".join(sentence_texts + action_notes).lower()
    if not text:
        return "neutral"
    if any(w in text for w in ("love", "warm", "tender", "embrace", "kiss")):
        return "love"
    if any(w in text for w in ("memory", "college", "past", "remember", "nostalgia")):
        return "nostalgia"
    if any(w in text for w in ("fear", "dark", "danger", "panic", "threat", "fright")):
        return "anxiety"
    if any(w in text for w in ("angry", "rage", "furious", "slam", "yell")):
        return "anger"
    if any(w in text for w in ("sad", "cry", "grief", "loss", "lonely")):
        return "sadness"
    if any(w in text for w in ("surprise", "suddenly", "shock")):
        return "surprise"
    if energy_level <= 3:
        return "calm"
    if energy_level >= 8:
        return "anticipation"
    return "neutral"


def script_to_narrative_plan_dict(ast: ScriptAST, *, project_type: str = "audio_drama") -> dict[str, Any]:
    """Convert parsed script AST into a Narrative Plan dict."""
    if project_type != "audio_drama":
        raise ValueError("script_to_narrative_plan_dict currently supports audio_drama only")

    scenes: list[dict[str, Any]] = []

    for idx, scene in enumerate(ast.scenes):
        sid = _scene_id(idx, scene.heading)
        dialogue_turns: list[dict[str, Any]] = []
        narration_segments: list[dict[str, Any]] = []
        speakers: list[str] = []
        action_notes: list[str] = []
        sfx_events: list[dict[str, Any]] = []
        ambience_tags: list[str] = []
        action_blocks: list[dict[str, Any]] = []
        sentence_cursor = 0
        sentence_texts: list[str] = []
        sfx_order = 0

        for block_idx, block in enumerate(scene.blocks):
            if isinstance(block, DialogueBlock):
                speaker = block.cue.name.strip()
                if speaker and speaker not in speakers:
                    speakers.append(speaker)

                line_text = " ".join(x.strip() for x in block.lines if x.strip()).strip()
                if not line_text:
                    continue
                delivery = _normalize_delivery(block.parenthetical)
                is_vo = any(ext.upper() in _VOICE_OVER_EXTS for ext in block.cue.extensions)

                start = sentence_cursor
                end = start + len(line_text)
                sentence_cursor = end + 1
                sentence_texts.append(line_text)
                turn = _dialogue_turn(speaker, line_text, start, end)
                turn["_block_index"] = block_idx
                turn["_is_vo"] = is_vo
                if delivery:
                    turn["delivery_hint"] = delivery
                dialogue_turns.append(turn)

                narration_segments.append(
                    {
                        "text": line_text,
                        "segment_type": "inner_thought" if is_vo else "description",
                        "has_sound_event": False,
                    }
                )
            elif isinstance(block, ActionBlock):
                txt = block.text.strip()
                if not txt:
                    continue
                action_notes.append(txt)
                action_blocks.append(
                    {
                        "kind": block.kind,
                        "marker": block.marker,
                        "text": txt,
                        "forced": block.forced,
                    }
                )
                sfx_hints, amb_hints = extract_sound_hints(txt)
                if block.kind == "ambience" and txt:
                    amb_hints = [txt.lower().replace(" ", "_"), *amb_hints]
                if block.kind == "sfx":
                    direct_label = re.sub(r"[^a-z0-9]+", "_", txt.lower()).strip("_")
                    if direct_label:
                        sfx_events.append(
                            {
                                "source_text": txt,
                                "sfx_label": direct_label[:48],
                                "sfx_description": "",
                                "intensity": "moderate",
                                "semantic_role": "interaction",
                                "timing": "short",
                                "order_hint": sfx_order,
                            }
                        )
                        sfx_order += 1
                ambience_tags.extend(amb_hints)
                for hint in sfx_hints:
                    sfx_events.append(
                        {
                            "source_text": hint.source_text,
                            "sfx_label": hint.label,
                            "sfx_description": "",
                            "intensity": "moderate",
                            "semantic_role": hint.semantic_role,
                            "timing": "short",
                            "order_hint": sfx_order,
                        }
                    )
                    sfx_order += 1

        all_text = " ".join(sentence_texts + action_notes).strip()
        sentence_count = len(sentence_texts)
        word_count = _count_words(all_text)
        avg_sentence_length = (word_count / sentence_count) if sentence_count else 0.0
        avg_dialogue_length = (
            sum(_count_words(turn["text"]) for turn in dialogue_turns) / len(dialogue_turns)
            if dialogue_turns
            else 0.0
        )
        emotion_scores, interpretation = _scene_defaults()
        interpretation["energy_level"] = _scene_energy_from_text(
            sentence_texts,
            action_notes,
            dialogue_turns,
        )
        _tag_dramatic_functions(
            dialogue_turns,
            scene.blocks,
            interpretation["energy_level"],
        )
        interpretation["primary_emotion"] = _scene_mood_from_text(
            sentence_texts,
            action_notes,
            interpretation["energy_level"],
        )
        interpretation["emotion_intensity"] = max(
            1,
            min(10, int(round((interpretation["energy_level"] + 2) / 1.2))),
        )

        ambience_cue = None
        if ambience_tags:
            primary = Counter(ambience_tags).most_common(1)[0][0]
            ambience_cue = {
                "primary_atmosphere": primary,
                "atmosphere_description": "",
                "intensity": "moderate",
                "evolves": False,
            }

        structure = {
            "scene_id": sid,
            "scene_title": scene.heading,
            "sentence_count": sentence_count,
            "word_count": word_count,
            "sentences": sentence_texts,
            "dialogue_turns": dialogue_turns,
            "speakers": speakers,
            "sfx_events": sfx_events,
            "ambience_cue": ambience_cue,
            "narration_segments": narration_segments,
            "action_notes": action_notes,
            "action_blocks": action_blocks,
        }
        signals = {
            "avg_sentence_length": round(avg_sentence_length, 3),
            "sentence_length_variance": 0.0,
            "short_sentence_streak": 0,
            "punctuation_score": float(all_text.count("!") + all_text.count("?") * 0.5),
            "action_verb_density": 0.0,
            "dialogue_ratio": (
                round(len(dialogue_turns) / sentence_count, 3) if sentence_count else 0.0
            ),
            "dialogue_turn_count": len(dialogue_turns),
            "avg_dialogue_length": round(avg_dialogue_length, 3),
            "emotion_scores": emotion_scores,
            "emotion_arc": [],
        }

        scenes.append(
            {
                "scene_id": sid,
                "structure": structure,
                "signals": signals,
                "interpretation": interpretation,
            }
        )

    plan = {"schema_version": "1.0", "scenes": scenes}
    validated = NarrativePlan(**plan)
    return validated.model_dump()


def process_script_json(script_text: str, *, project_type: str = "audio_drama") -> bytes:
    """Parse script text and return Narrative Plan JSON bytes."""
    ast = parse_fountain(script_text)
    plan = script_to_narrative_plan_dict(ast, project_type=project_type)
    return serialize(plan)


def process_script_bundle(
    script_text: str,
    *,
    project_type: str = "audio_drama",
) -> tuple[bytes, ScriptAST]:
    """Parse script and return ``(plan_json_bytes, ast)``."""
    ast = parse_fountain(script_text)
    plan = script_to_narrative_plan_dict(ast, project_type=project_type)
    return serialize(plan), ast
