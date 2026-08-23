"""Heuristic sound/ambience extraction from action text."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SFXHint:
    """Normalized SFX hint extracted from action text."""

    label: str
    semantic_role: str
    source_text: str
    confidence: float = 1.0


_SFX_KEYWORDS: dict[str, tuple[str, str]] = {
    "footsteps": ("footsteps", "movement"),
    "walking": ("footsteps", "movement"),
    "runs": ("running_steps", "movement"),
    "running": ("running_steps", "movement"),
    "breathing": ("heavy_breathing", "texture"),
    "breath": ("heavy_breathing", "texture"),
    "door": ("door_movement", "interaction"),
    "slams": ("door_slam", "impact"),
    "knock": ("door_knock", "interaction"),
    "whispering": ("ominous_whispers", "texture"),
    "voices": ("crowd_voices", "ambience"),
    "sonar": ("sonar_ping", "interaction"),
    "ping": ("sonar_ping", "interaction"),
    "whale": ("whale_call_distant", "ambience"),
    "traffic": ("city_traffic_passby", "ambience"),
    "horn": ("car_horn_distant", "impact"),
}

_SFX_PHRASES: dict[str, tuple[str, str, float]] = {
    "sonar ping": ("sonar_ping", "interaction", 1.0),
    "whale song": ("whale_call_distant", "ambience", 0.95),
    "heavy breathing": ("heavy_breathing", "texture", 0.95),
    "city traffic": ("city_traffic_passby", "ambience", 0.9),
    "door slams": ("door_slam", "impact", 0.95),
}

_AMBIENCE_KEYWORDS: dict[str, str] = {
    "underwater": "underwater_deep",
    "ocean": "ocean_depth",
    "street": "city_street_busy",
    "city": "city_street_busy",
    "rain": "rain_outdoor",
    "storm": "storm_wind_rain",
    "wind": "wind_ambient",
    "forest": "forest_day",
    "room": "indoor_room_tone",
    "quarters": "indoor_room_tone",
}

_AMBIENCE_PHRASES: dict[str, tuple[str, float]] = {
    "busy street": ("city_street_busy", 1.0),
    "city traffic": ("city_street_busy", 0.95),
    "underwater world": ("underwater_deep", 1.0),
    "distant whale song": ("ocean_depth", 0.95),
    "room tone": ("indoor_room_tone", 0.9),
}

_INTENSITY_TOKENS = {"loud": 1.15, "intense": 1.15, "strong": 1.1, "faint": 0.85, "soft": 0.85}
_PROXIMITY_TOKENS = {"distant": "distant", "far": "distant", "near": "near", "close": "near"}


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def extract_sound_hints(action_text: str) -> tuple[list[SFXHint], list[str]]:
    """Extract SFX hints and ambience candidates from action text."""
    tokens = _tokenize(action_text)
    lower = action_text.lower()
    scored_sfx: dict[str, tuple[SFXHint, float]] = {}
    scored_amb: dict[str, float] = {}

    intensity_factor = 1.0
    for tok in tokens:
        intensity_factor *= _INTENSITY_TOKENS.get(tok, 1.0)

    proximity = ""
    for tok in tokens:
        p = _PROXIMITY_TOKENS.get(tok)
        if p:
            proximity = p
            break

    # Phrase matches first (higher confidence).
    for phrase, (label, role, score) in _SFX_PHRASES.items():
        if phrase in lower:
            final_score = max(0.1, min(1.0, score * intensity_factor))
            candidate = SFXHint(
                label=label,
                semantic_role=role,
                source_text=action_text,
                confidence=final_score,
            )
            best = scored_sfx.get(label)
            if best is None or final_score > best[1]:
                scored_sfx[label] = (candidate, final_score)

    for phrase, (amb, score) in _AMBIENCE_PHRASES.items():
        if phrase in lower:
            final_amb = f"{amb}_{proximity}" if proximity and not amb.endswith(proximity) else amb
            scored_amb[final_amb] = max(scored_amb.get(final_amb, 0.0), score * intensity_factor)

    # Token matches as fallback.
    for tok in tokens:
        if tok in _SFX_KEYWORDS:
            label, role = _SFX_KEYWORDS[tok]
            score = max(0.1, min(1.0, 0.75 * intensity_factor))
            candidate = SFXHint(
                label=label,
                semantic_role=role,
                source_text=action_text,
                confidence=score,
            )
            best = scored_sfx.get(label)
            if best is None or score > best[1]:
                scored_sfx[label] = (candidate, score)
        if tok in _AMBIENCE_KEYWORDS:
            amb = _AMBIENCE_KEYWORDS[tok]
            if proximity:
                amb = f"{amb}_{proximity}"
            scored_amb[amb] = max(scored_amb.get(amb, 0.0), 0.7 * intensity_factor)

    sfx_sorted = sorted(scored_sfx.values(), key=lambda item: item[1], reverse=True)
    amb_sorted = sorted(scored_amb.items(), key=lambda item: item[1], reverse=True)

    sfx = [item[0] for item in sfx_sorted[:4]]
    ambience = [item[0] for item in amb_sorted[:3]]
    return sfx, ambience
