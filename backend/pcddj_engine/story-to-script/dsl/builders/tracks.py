"""Track lane builder — determines which top-level tracks a project needs.

Rules vary by project type:

AudioBook:
    * One ``narrator`` voice track.
    * One ``music`` track.
    * One ``ambience`` track.

AudioDrama:
    * One ``character_<name>`` voice track per unique speaker (with voice profile).
    * One ``music`` track.
    * One ``ambience`` track.
    * One ``sfx`` track (conditional on signal thresholds).
"""

from __future__ import annotations

import re
from typing import Any

from dsl.constants import (
    AMBIENCE_GAIN_BASE,
    CHARACTER_GAIN,
    MUSIC_GAIN_BASE,
    NARRATOR_GAIN,
    SFX_GAIN,
    SFX_IMPACT_MIN_PUNCTUATION,
    SFX_IMPACT_MIN_SHORT_STREAK,
    SFX_TEXTURE_MIN_ENERGY,
    TRACK_TYPE_EQ_DEFAULTS,
)
from dsl.schema import DraftTrack, VoiceProfile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitize_track_id(speaker: str) -> str:
    """Turn a speaker name into a safe track ID.

    * Lowercased
    * Spaces / hyphens replaced with underscores
    * Non-alphanumeric characters (except underscores) stripped
    """
    tid = speaker.lower().strip()
    tid = re.sub(r"[\s\-]+", "_", tid)
    tid = re.sub(r"[^a-z0-9_]", "", tid)
    return f"character_{tid}" if tid else "character_unknown"


def _needs_sfx(
    scenes: list[dict[str, Any]],
    *,
    project_type: str = "audio_drama",
) -> bool:
    """Return ``True`` if any scene needs an SFX track.

    Always ``False`` for audiobook mode.  For audio drama, checks both
    Gemini-extracted audio cues **and** the legacy numeric-threshold
    heuristics (as a fallback).
    """
    if project_type == "audiobook":
        return False

    for scene in scenes:
        sfx_events = scene.get("structure", {}).get("sfx_events", [])
        if sfx_events:
            return True
        action_notes = scene.get("structure", {}).get("action_notes", [])
        if isinstance(action_notes, list) and action_notes:
            text = " ".join(str(x).lower() for x in action_notes)
            if any(tok in text for tok in ("door", "footstep", "slam", "traffic", "whisper", "sonar", "horn")):
                return True

        signals = scene.get("signals", {})
        interp = scene.get("interpretation", {})
        energy = interp.get("energy_level", 5) / 10.0

        short_streak = signals.get("short_sentence_streak", 0)
        punctuation = signals.get("punctuation_score", 0.0)
        silence_intent = interp.get("silence_intent", "none")

        if (
            short_streak >= SFX_IMPACT_MIN_SHORT_STREAK
            and punctuation > SFX_IMPACT_MIN_PUNCTUATION
        ):
            return True
        if silence_intent == "long" and energy >= SFX_TEXTURE_MIN_ENERGY:
            return True
    return False


# ---------------------------------------------------------------------------
# Voice profile generation
# ---------------------------------------------------------------------------

_VOICE_PROFILES = [
    VoiceProfile(gender="male", age_hint="adult", tone="warm", pace="moderate"),
    VoiceProfile(gender="female", age_hint="adult", tone="clear", pace="moderate"),
    VoiceProfile(gender="male", age_hint="elderly", tone="gravelly", pace="slow"),
    VoiceProfile(gender="female", age_hint="young_adult", tone="bright", pace="fast"),
    VoiceProfile(gender="male", age_hint="young_adult", tone="energetic", pace="fast"),
    VoiceProfile(gender="female", age_hint="elderly", tone="soft", pace="slow"),
    VoiceProfile(gender="male", age_hint="middle_aged", tone="deep", pace="moderate"),
    VoiceProfile(gender="female", age_hint="middle_aged", tone="warm", pace="moderate"),
]


def _assign_voice_profile(speaker_index: int) -> VoiceProfile:
    """Return a distinguishable voice profile for the *speaker_index*-th character."""
    return _VOICE_PROFILES[speaker_index % len(_VOICE_PROFILES)]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_tracks(
    narrative_plan: dict[str, Any],
    *,
    project_type: str = "audio_drama",
    narration_only: bool = False,
) -> list[DraftTrack]:
    """Build the list of top-level track definitions for a project.

    Parameters
    ----------
    narrative_plan:
        Full Narrative Plan dict (``{"schema_version": ..., "scenes": [...]}``)
    project_type:
        ``"audiobook"`` or ``"audio_drama"``.
    narration_only:
        When ``True`` with ``project_type="audiobook"``, emit only the
        narrator voice track (no music, ambience, or SFX lanes).

    Returns
    -------
    list[DraftTrack]
    """
    scenes = narrative_plan.get("scenes", [])
    tracks: list[DraftTrack] = []

    if project_type == "audiobook":
        # AudioBook: narrator only, no characters, no SFX
        tracks.append(
            DraftTrack(
                id="narrator",
                type="voice",
                role="voice",
                eq_preset=TRACK_TYPE_EQ_DEFAULTS["voice"],  # type: ignore[arg-type]
                gain=NARRATOR_GAIN,
            )
        )
        if narration_only:
            return tracks
    else:
        # AudioDrama: per-character tracks with voice profiles, no narrator
        all_speakers: list[str] = []
        seen: set[str] = set()
        for scene in scenes:
            structure = scene.get("structure", {})
            for speaker in structure.get("speakers", []):
                if speaker not in seen:
                    seen.add(speaker)
                    all_speakers.append(speaker)

        for idx, speaker in enumerate(all_speakers):
            track_id = _sanitize_track_id(speaker)
            tracks.append(
                DraftTrack(
                    id=track_id,
                    type="voice",
                    role="voice",
                    eq_preset=TRACK_TYPE_EQ_DEFAULTS["voice"],  # type: ignore[arg-type]
                    gain=CHARACTER_GAIN,
                    voice_profile=_assign_voice_profile(idx),
                )
            )

    # -- Music track (always) -----------------------------------------------
    tracks.append(
        DraftTrack(
            id="music",
            type="music",
            role="background",
            eq_preset=TRACK_TYPE_EQ_DEFAULTS["music"],  # type: ignore[arg-type]
            gain=MUSIC_GAIN_BASE,
        )
    )

    # -- Ambience track (always) --------------------------------------------
    tracks.append(
        DraftTrack(
            id="ambience",
            type="ambience",
            role="background",
            eq_preset=TRACK_TYPE_EQ_DEFAULTS["ambience"],  # type: ignore[arg-type]
            gain=AMBIENCE_GAIN_BASE,
        )
    )

    # -- SFX track (audio drama only, conditional) --------------------------
    if _needs_sfx(scenes, project_type=project_type):
        tracks.append(
            DraftTrack(
                id="sfx",
                type="sfx",
                role="foreground",
                eq_preset=TRACK_TYPE_EQ_DEFAULTS["sfx"],  # type: ignore[arg-type]
                gain=SFX_GAIN,
            )
        )

    return tracks


def collect_speaker_track_map(
    narrative_plan: dict[str, Any],
) -> dict[str, str]:
    """Return a mapping of ``speaker_name → track_id``.

    Used by the clip builder to route dialogue clips to the correct track.
    """
    speaker_map: dict[str, str] = {}
    for scene in narrative_plan.get("scenes", []):
        for speaker in scene.get("structure", {}).get("speakers", []):
            if speaker not in speaker_map:
                speaker_map[speaker] = _sanitize_track_id(speaker)
    return speaker_map
