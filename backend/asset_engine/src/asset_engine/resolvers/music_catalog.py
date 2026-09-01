"""Tag-driven music catalog matching for deterministic drama scoring."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

from asset_engine.contracts.requirements_models import AssetRequirement


_TOKEN_RE = re.compile(r"[^a-z0-9]+")


def _tokenize(text: str | None) -> set[str]:
    if not text:
        return set()
    return {tok for tok in _TOKEN_RE.split(text.lower()) if tok}


@dataclass(frozen=True)
class MusicTrack:
    path: str
    role: str
    emotion: tuple[str, ...]
    genre: tuple[str, ...]
    tags: tuple[str, ...]
    energy: float | None
    duration_s: float | None
    loopable: bool


@dataclass(frozen=True)
class MusicMatch:
    file_path: Path
    score: float
    reason: str
    role: str
    tags: tuple[str, ...]


class MusicCatalog:
    """Loads and scores tracks from music_catalog.json."""

    def __init__(self, catalog_path: Path):
        self.catalog_path = catalog_path
        self._tracks: list[MusicTrack] = []

    @property
    def tracks(self) -> list[MusicTrack]:
        return self._tracks

    @classmethod
    def load(cls, catalog_path: Path) -> "MusicCatalog":
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
        tracks_raw = payload.get("tracks")
        if not isinstance(tracks_raw, list):
            raise ValueError("music catalog must contain a 'tracks' list")

        inst = cls(catalog_path=catalog_path)
        parsed: list[MusicTrack] = []
        for idx, item in enumerate(tracks_raw):
            if not isinstance(item, dict):
                raise ValueError(f"music catalog track at index {idx} must be an object")
            path = str(item.get("path", "")).strip()
            role = str(item.get("role", "")).strip().lower()
            if not path:
                raise ValueError(f"music catalog track at index {idx} missing 'path'")
            if role not in {"underscore", "stinger", "theme"}:
                raise ValueError(
                    f"music catalog track at index {idx} has invalid role '{role}'",
                )

            def _norm_list(value: Any) -> tuple[str, ...]:
                if not isinstance(value, list):
                    return ()
                out: list[str] = []
                for v in value:
                    s = str(v).strip().lower()
                    if s:
                        out.append(s)
                return tuple(out)

            energy = item.get("energy")
            energy_num: float | None = None
            if energy is not None:
                try:
                    energy_num = max(0.0, min(1.0, float(energy)))
                except (TypeError, ValueError):
                    energy_num = None

            duration = item.get("duration_s")
            duration_num: float | None = None
            if duration is not None:
                try:
                    duration_num = max(0.0, float(duration))
                except (TypeError, ValueError):
                    duration_num = None

            parsed.append(
                MusicTrack(
                    path=path,
                    role=role,
                    emotion=_norm_list(item.get("emotion")),
                    genre=_norm_list(item.get("genre")),
                    tags=_norm_list(item.get("tags")),
                    energy=energy_num,
                    duration_s=duration_num,
                    loopable=bool(item.get("loopable", False)),
                ),
            )

        if not parsed:
            raise ValueError("music catalog tracks cannot be empty")

        inst._tracks = parsed
        return inst

    def find_best(self, req: AssetRequirement, audio_library_root: Path | None) -> MusicMatch | None:
        descriptor_tokens = _tokenize(req.descriptor)
        emotion_tokens = _tokenize(req.mood) | descriptor_tokens
        desired_role = _infer_music_role(req)

        best: tuple[float, MusicTrack, str] | None = None
        for track in self._tracks:
            if track.role != desired_role:
                continue

            score, reason = _score_track(track, req, descriptor_tokens, emotion_tokens)
            if best is None or score > best[0]:
                best = (score, track, reason)

        if best is None:
            return None

        score, track, reason = best
        if score <= 0:
            return None

        base = audio_library_root if audio_library_root is not None else self.catalog_path.parent
        file_path = (base / track.path).resolve()
        if not file_path.is_file():
            return None

        return MusicMatch(
            file_path=file_path,
            score=round(score, 3),
            reason=reason,
            role=track.role,
            tags=track.tags,
        )


def _infer_music_role(req: AssetRequirement) -> str:
    pos = (req.position or "").strip().lower()
    if pos in {"intro", "outro"}:
        return "stinger"
    if pos == "theme":
        return "theme"

    desc = (req.descriptor or "").lower()
    if "theme" in desc or "leitmotif" in desc:
        return "theme"
    if "stinger" in desc or "hit" in desc or "accent" in desc:
        return "stinger"
    return "underscore"


def _score_track(
    track: MusicTrack,
    req: AssetRequirement,
    descriptor_tokens: set[str],
    emotion_tokens: set[str],
) -> tuple[float, str]:
    score = 0.0
    reasons: list[str] = [f"role={track.role}"]

    track_tokens = set(track.tags) | set(track.genre) | set(track.emotion)
    overlap = descriptor_tokens.intersection(track_tokens)
    if overlap:
        score += min(0.25, 0.05 * len(overlap))
        reasons.append(f"tags={','.join(sorted(overlap))}")

    emo_overlap = emotion_tokens.intersection(set(track.emotion))
    if emo_overlap:
        score += min(0.4, 0.2 + 0.1 * len(emo_overlap))
        reasons.append(f"emotion={','.join(sorted(emo_overlap))}")

    if req.energy_hint is not None and track.energy is not None:
        dist = abs(float(req.energy_hint) - float(track.energy))
        energy_score = max(0.0, 0.25 - 0.25 * dist)
        score += energy_score
        reasons.append(f"energy_delta={dist:.2f}")

    if _infer_music_role(req) == "underscore":
        if req.loop and track.loopable:
            score += 0.2
            reasons.append("loopable")
        if track.duration_s and track.duration_s >= 20:
            score += 0.1
            reasons.append("long")
    elif _infer_music_role(req) == "stinger":
        if track.duration_s and 3.0 <= track.duration_s <= 8.0:
            score += 0.25
            reasons.append("stinger_len")

    return score, "; ".join(reasons)
