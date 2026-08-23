"""Structured Gemini TTS prompts for audio drama dialogue.

The prompt mirrors the directorial style used in Google AI Studio:

    Read the following transcript based on the audio profile and director's note.

    # Audio Profile
    ...

    # Director's note
    Style: ... Pace: ... Accent: ...

    ## Scene:
    ...

    ## Sample Context:
    ...

    ## Transcript:
    [tag] dialogue text

Inputs come from:

- ``gita.json`` for per-character voice traits (``audio_profile``, ``style``,
  ``pace``, ``accent``, ``voice_treatment``, ``default_delivery``).
- ``narrative_plan.json`` for the per-scene scene/atmosphere description and
  the per-line ``delivery_hint``.
- An optional project-level ``sample_context`` (project genre, pace, tone)
  carried in ``gita.audio.sample_context``.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


_INSTRUCTION = (
    "Read the following transcript based on the audio profile and director's note."
)


@dataclass(frozen=True)
class CharacterAudio:
    """Resolved per-character audio direction."""

    audio_profile: str = ""
    style: str = ""
    pace: str = ""
    accent: str = ""
    delivery_default: str = ""

    def director_note(self, *, scene_delivery: str = "") -> str:
        parts: list[str] = []
        if self.style:
            parts.append(f"Style: {self.style}.")
        if self.pace:
            parts.append(f"Pace: {self.pace}.")
        if self.accent:
            parts.append(f"Accent: {self.accent}.")
        delivery = (scene_delivery or self.delivery_default or "").strip()
        if delivery:
            parts.append(f"Delivery: {delivery}.")
        return " ".join(parts).strip()


def _norm_speaker_key(value: str) -> str:
    return "".join(ch for ch in value.upper().strip() if ch.isalnum())


def _speaker_match_keys(value: str) -> set[str]:
    """Generate the set of normalized keys that should match *value*.

    Track ids look like ``character_arnav`` while narrative_plan dialogue uses
    bare names like ``ARNAV``.  We compare by both the full normalized form
    and a short form with the ``CHARACTER`` prefix stripped, so either side
    can resolve the other.
    """
    norm = _norm_speaker_key(value)
    keys = {norm}
    if norm.startswith("CHARACTER") and len(norm) > len("CHARACTER"):
        keys.add(norm[len("CHARACTER") :])
    return {k for k in keys if k}


def _speaker_matches(a: str, b: str) -> bool:
    return bool(_speaker_match_keys(a) & _speaker_match_keys(b))


def character_audio_from_gita(
    speaker: str,
    gita: dict[str, Any] | None,
) -> CharacterAudio:
    """Look up character audio direction by name or alias (case-insensitive)."""
    if not isinstance(gita, dict):
        return CharacterAudio()
    characters = gita.get("characters")
    if not isinstance(characters, dict):
        return CharacterAudio()

    target_keys = _speaker_match_keys(speaker)
    for entry in characters.values():
        if not isinstance(entry, dict):
            continue
        names: list[str] = []
        if entry.get("name"):
            names.append(str(entry["name"]))
        aliases = entry.get("aliases")
        if isinstance(aliases, list):
            names.extend(str(a) for a in aliases if a)
        if not any(target_keys & _speaker_match_keys(n) for n in names if n):
            continue
        audio_profile = str(entry.get("audio_profile") or entry.get("voice_treatment") or "").strip()
        return CharacterAudio(
            audio_profile=audio_profile,
            style=str(entry.get("style") or "").strip(),
            pace=str(entry.get("pace") or "").strip(),
            accent=str(entry.get("accent") or "").strip(),
            delivery_default=str(entry.get("default_delivery") or "").strip(),
        )

    return CharacterAudio()


def project_sample_context(gita: dict[str, Any] | None) -> str:
    """Extract the optional project-level sample context block."""
    if not isinstance(gita, dict):
        return ""
    audio = gita.get("audio")
    if isinstance(audio, dict):
        sc = audio.get("sample_context")
        if isinstance(sc, str) and sc.strip():
            return sc.strip()
    return ""


def find_scene_for_speaker(
    narrative_plan: dict[str, Any] | None,
    speaker: str,
    *,
    scene_index: int | None = None,
) -> dict[str, Any] | None:
    """Return the scene dict that holds dialogue for ``speaker``.

    When ``scene_index`` is provided we prefer that scene; otherwise we return
    the first scene that contains a dialogue turn for the speaker.
    """
    if not isinstance(narrative_plan, dict):
        return None
    scenes = narrative_plan.get("scenes")
    if not isinstance(scenes, list):
        return None

    if scene_index is not None and 0 <= scene_index < len(scenes):
        scene = scenes[scene_index]
        if isinstance(scene, dict):
            return scene

    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        structure = scene.get("structure") or {}
        speakers = structure.get("speakers") or []
        if any(_speaker_matches(speaker, str(sp)) for sp in speakers if sp):
            return scene
    return None


def find_dialogue_turn(
    scene: dict[str, Any] | None,
    speaker: str,
    line_text: str,
) -> dict[str, Any] | None:
    """Match a dialogue turn by speaker + (lower-cased) line text."""
    if not isinstance(scene, dict):
        return None
    structure = scene.get("structure") or {}
    turns = structure.get("dialogue_turns")
    if not isinstance(turns, list):
        return None

    target = (line_text or "").strip().lower()
    best_partial: dict[str, Any] | None = None
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        sp = str(turn.get("speaker") or "")
        if not _speaker_matches(speaker, sp):
            continue
        candidate = str(turn.get("text") or "").strip().lower()
        if candidate == target:
            return turn
        if target and candidate and (candidate in target or target in candidate):
            best_partial = best_partial or turn
    return best_partial


def _scene_summary(scene: dict[str, Any] | None) -> str:
    """Build the ``## Scene:`` paragraph from narrative_plan scene data."""
    if not isinstance(scene, dict):
        return ""
    structure = scene.get("structure") or {}

    title = str(structure.get("scene_title") or "").strip()
    ambience_obj = structure.get("ambience_cue")
    atmosphere = ""
    if isinstance(ambience_obj, dict):
        atmosphere = str(
            ambience_obj.get("atmosphere_description")
            or ambience_obj.get("primary_atmosphere")
            or ""
        ).strip()

    action_notes_raw = structure.get("action_notes")
    action_notes: list[str] = []
    if isinstance(action_notes_raw, list):
        for note in action_notes_raw:
            text = str(note or "").strip()
            if text:
                action_notes.append(text)

    parts: list[str] = []
    if title:
        parts.append(title)
    if atmosphere:
        parts.append(f"Atmosphere: {atmosphere}.")
    if action_notes:
        snippet = " ".join(action_notes[:2])
        parts.append(snippet)
    return " ".join(parts).strip()


def _interpretation_summary(scene: dict[str, Any] | None) -> str:
    """Build a deterministic Sample Context line from interpretation signals."""
    if not isinstance(scene, dict):
        return ""
    interpretation = scene.get("interpretation")
    if not isinstance(interpretation, dict):
        return ""

    primary_emotion = str(interpretation.get("primary_emotion") or "").strip()
    style = str(interpretation.get("scene_style") or "").strip()
    music_strategy = str(interpretation.get("music_strategy") or "").strip()
    energy = interpretation.get("energy_level")
    intensity = interpretation.get("emotion_intensity")

    parts: list[str] = []
    if style:
        parts.append(f"Style: {style}.")
    if primary_emotion and primary_emotion.lower() != "neutral":
        parts.append(f"Tone: {primary_emotion}.")
    if isinstance(energy, (int, float)):
        parts.append(f"Energy: {float(energy):.0f}/10.")
    if isinstance(intensity, (int, float)):
        parts.append(f"Intensity: {float(intensity):.0f}/10.")
    if music_strategy:
        parts.append(f"Music: {music_strategy}.")
    return " ".join(parts).strip()


_TAG_SAFE_RE = re.compile(r"[^a-z0-9]+")


def _delivery_to_tag(delivery_hint: str) -> str:
    """Convert a free-form delivery hint into a short ``[tag]`` token."""
    s = (delivery_hint or "").strip().lower()
    if not s:
        return ""
    s = _TAG_SAFE_RE.sub("_", s).strip("_")
    if not s:
        return ""
    if len(s) > 28:
        s = s[:28].rstrip("_")
    return f"[{s}]"


def _wrap_transcript(line_text: str, delivery_hint: str) -> str:
    text = (line_text or "").strip()
    tag = _delivery_to_tag(delivery_hint)
    if tag:
        return f"{tag} {text}"
    return text


def build_drama_prompt(
    *,
    line_text: str,
    speaker: str,
    gita: dict[str, Any] | None = None,
    narrative_plan: dict[str, Any] | None = None,
    scene_index: int | None = None,
    sample_context: str | None = None,
    delivery_hint_override: str | None = None,
    audio_override: CharacterAudio | None = None,
) -> str:
    """Assemble the full TTS prompt for a single drama dialogue line."""
    audio = audio_override or character_audio_from_gita(speaker, gita)
    scene = find_scene_for_speaker(narrative_plan, speaker, scene_index=scene_index)
    turn = find_dialogue_turn(scene, speaker, line_text) if scene else None
    delivery_hint = (
        delivery_hint_override
        if delivery_hint_override is not None
        else (str((turn or {}).get("delivery_hint") or "") if turn else "")
    )

    director_note = audio.director_note(scene_delivery=delivery_hint)
    scene_summary = _scene_summary(scene)
    sample_ctx = (
        sample_context
        if sample_context is not None
        else project_sample_context(gita)
    )
    if not sample_ctx:
        sample_ctx = _interpretation_summary(scene)

    transcript = _wrap_transcript(line_text, delivery_hint)

    sections: list[str] = [_INSTRUCTION]
    if audio.audio_profile:
        sections.append(f"# Audio Profile\n{audio.audio_profile}")
    if director_note:
        sections.append(f"# Director's note\n{director_note}")
    if scene_summary:
        sections.append(f"## Scene:\n{scene_summary}")
    if sample_ctx:
        sections.append(f"## Sample Context:\n{sample_ctx}")
    sections.append(f"## Transcript:\n{transcript}")

    return "\n\n".join(sections).strip() + "\n"
