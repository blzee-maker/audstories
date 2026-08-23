"""Cross-episode continuity helpers for audio drama projects."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _norm_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def default_gita(project_id: str, title: str, writer: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "project_id": project_id,
        "series_title": title or project_id,
        "writer_name": writer or "",
        "characters": {},
        "locations": {},
        "sfx_motifs": {},
        "music_themes": {},
        "relationships": [],
        "continuity_notes": [],
        "episodes": [],
    }


def normalize_gita(payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload or {})
    out["schema_version"] = str(out.get("schema_version") or "1.0")
    out["project_id"] = str(out.get("project_id") or "").strip()
    out["series_title"] = str(out.get("series_title") or out["project_id"] or "").strip()
    out["writer_name"] = str(out.get("writer_name") or "").strip()
    for key in ("characters", "locations", "sfx_motifs", "music_themes"):
        val = out.get(key)
        out[key] = dict(val) if isinstance(val, dict) else {}
    for key in ("relationships", "continuity_notes", "episodes"):
        val = out.get(key)
        out[key] = list(val) if isinstance(val, list) else []

    characters = out.get("characters")
    if isinstance(characters, dict):
        for ckey, entry in list(characters.items()):
            if not isinstance(entry, dict):
                continue
            tts_voice = entry.get("tts_voice")
            entry["tts_voice"] = str(tts_voice).strip() if tts_voice else ""
            for audio_field in ("audio_profile", "style", "pace", "accent"):
                value = entry.get(audio_field)
                entry[audio_field] = str(value).strip() if value else ""
            characters[ckey] = entry

    audio = out.get("audio")
    if isinstance(audio, dict):
        sample_context = audio.get("sample_context")
        out["audio"] = {
            "sample_context": str(sample_context).strip() if sample_context else "",
        }
    elif audio is not None:
        out["audio"] = {"sample_context": ""}
    return out


def load_gita(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("gita.json must contain a JSON object")
    return normalize_gita(raw)


def save_gita(path: Path, payload: dict[str, Any]) -> None:
    normalized = normalize_gita(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, indent=2), encoding="utf-8")


def update_gita_from_plan(
    gita: dict[str, Any],
    plan: dict[str, Any],
    chapter_slug: str,
) -> dict[str, Any]:
    out = normalize_gita(gita)
    scenes = plan.get("scenes")
    if not isinstance(scenes, list):
        return out

    characters = out["characters"]
    locations = out["locations"]
    motifs = out["sfx_motifs"]
    episode_speakers: set[str] = set()
    episode_locations: set[str] = set()
    episode_sfx: set[str] = set()

    for sc in scenes:
        if not isinstance(sc, dict):
            continue
        structure = sc.get("structure")
        interpretation = sc.get("interpretation")
        if not isinstance(structure, dict):
            continue
        scene_title = str(structure.get("scene_title") or "").strip()
        if scene_title:
            loc_key = _norm_key(scene_title)
            if loc_key not in locations:
                locations[loc_key] = {
                    "title": scene_title,
                    "preferred_ambience": (
                        (structure.get("ambience_cue") or {}).get("primary_atmosphere")
                        if isinstance(structure.get("ambience_cue"), dict)
                        else None
                    ),
                }
            episode_locations.add(scene_title)

        for speaker in structure.get("speakers", []):
            s = str(speaker).strip()
            if not s:
                continue
            episode_speakers.add(s)
            key = _norm_key(s)
            if key not in characters:
                characters[key] = {
                    "name": s,
                    "aliases": [s],
                    "voice_treatment": "",
                    "default_delivery": "",
                    "tts_voice": "",
                    "audio_profile": "",
                    "style": "",
                    "pace": "",
                    "accent": "",
                }
            else:
                existing = characters[key]
                if isinstance(existing, dict):
                    for fld in (
                        "tts_voice",
                        "audio_profile",
                        "style",
                        "pace",
                        "accent",
                    ):
                        existing.setdefault(fld, "")

        for event in structure.get("sfx_events", []):
            if not isinstance(event, dict):
                continue
            label = str(event.get("sfx_label") or "").strip()
            if not label:
                continue
            episode_sfx.add(label)
            m_key = _norm_key(label)
            if m_key not in motifs:
                motifs[m_key] = {
                    "label": label,
                    "intensity": str(event.get("intensity") or "moderate"),
                    "semantic_role": str(event.get("semantic_role") or "interaction"),
                }

        if isinstance(interpretation, dict):
            music_strategy = str(interpretation.get("music_strategy") or "").strip()
            if music_strategy:
                theme_key = _norm_key(music_strategy)[:48] or "theme"
                out["music_themes"].setdefault(
                    theme_key,
                    {"name": music_strategy, "notes": ""},
                )

    episodes = out["episodes"]
    record = {
        "chapter_slug": chapter_slug,
        "scene_count": len(scenes),
        "speakers": sorted(episode_speakers),
        "locations": sorted(episode_locations),
        "sfx_labels": sorted(episode_sfx),
    }
    existing_idx = next(
        (
            i
            for i, e in enumerate(episodes)
            if isinstance(e, dict) and str(e.get("chapter_slug", "")).strip() == chapter_slug
        ),
        None,
    )
    if existing_idx is None:
        episodes.append(record)
    else:
        episodes[int(existing_idx)] = record
    return out


def apply_gita_to_plan(plan: dict[str, Any], gita: dict[str, Any]) -> dict[str, Any]:
    out = dict(plan)
    norm = normalize_gita(gita)
    scenes = out.get("scenes")
    if not isinstance(scenes, list):
        return out

    characters = norm.get("characters", {})
    locations = norm.get("locations", {})
    motifs = norm.get("sfx_motifs", {})
    alias_to_char: dict[str, dict[str, Any]] = {}
    for value in characters.values():
        if not isinstance(value, dict):
            continue
        name = str(value.get("name") or "").strip()
        aliases = value.get("aliases")
        if isinstance(aliases, list):
            for alias in aliases:
                a = str(alias).strip()
                if a:
                    alias_to_char[a.upper()] = value
        if name:
            alias_to_char[name.upper()] = value

    motif_by_label = {
        str(v.get("label", "")).strip().lower(): v
        for v in motifs.values()
        if isinstance(v, dict) and str(v.get("label", "")).strip()
    }

    for sc in scenes:
        if not isinstance(sc, dict):
            continue
        structure = sc.get("structure")
        if not isinstance(structure, dict):
            continue

        scene_title = str(structure.get("scene_title") or "").strip()
        loc = locations.get(_norm_key(scene_title))
        if isinstance(loc, dict):
            preferred = str(loc.get("preferred_ambience") or "").strip()
            if preferred:
                cue = structure.get("ambience_cue")
                if not isinstance(cue, dict):
                    cue = {
                        "primary_atmosphere": preferred,
                        "atmosphere_description": "",
                        "intensity": "moderate",
                        "evolves": False,
                    }
                else:
                    cue["primary_atmosphere"] = preferred
                structure["ambience_cue"] = cue

        turns = structure.get("dialogue_turns")
        if isinstance(turns, list):
            for turn in turns:
                if not isinstance(turn, dict):
                    continue
                speaker = str(turn.get("speaker") or "").strip().upper()
                if not speaker:
                    continue
                char = alias_to_char.get(speaker)
                if not isinstance(char, dict):
                    continue
                default_delivery = str(char.get("default_delivery") or "").strip()
                if default_delivery and not str(turn.get("delivery_hint") or "").strip():
                    turn["delivery_hint"] = default_delivery[:40]

        sfx_events = structure.get("sfx_events")
        if isinstance(sfx_events, list):
            for event in sfx_events:
                if not isinstance(event, dict):
                    continue
                label = str(event.get("sfx_label") or "").strip().lower()
                motif = motif_by_label.get(label)
                if not isinstance(motif, dict):
                    continue
                canonical = str(motif.get("label") or "").strip()
                if canonical:
                    event["sfx_label"] = canonical[:48]
                intensity = str(motif.get("intensity") or "").strip()
                if intensity:
                    event["intensity"] = intensity
                role = str(motif.get("semantic_role") or "").strip()
                if role:
                    event["semantic_role"] = role

    return out
