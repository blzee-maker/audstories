"""Gemini Flash TTS helpers for narration audiobooks and audio dramas."""

from narration_tts.drama_prompt import (
    CharacterAudio,
    build_drama_prompt,
    character_audio_from_gita,
)
from narration_tts.drama_tts import (
    CharacterPackage,
    CharacterResult,
    DramaTTSResult,
    fill_drama_voice_requirements,
    plan_voice_packages,
    voice_map_from_gita,
)
from narration_tts.google_tts import fill_voice_requirements_from_draft

__all__ = [
    "fill_voice_requirements_from_draft",
    "fill_drama_voice_requirements",
    "plan_voice_packages",
    "voice_map_from_gita",
    "CharacterPackage",
    "CharacterResult",
    "DramaTTSResult",
    "CharacterAudio",
    "build_drama_prompt",
    "character_audio_from_gita",
]
