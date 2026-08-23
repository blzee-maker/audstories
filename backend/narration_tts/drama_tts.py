"""Per-character batched Gemini TTS for audio drama voice clips.

This module reuses the low-level Gemini Flash TTS helpers from
``narration_tts.google_tts`` but groups voice requirements by speaker
(`track_id`), processes one character at a time, and paces calls to
stay under Gemini Flash short-window quotas.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import time

from asset_engine.contracts.draft_models import DraftTimeline, DraftTrack
from asset_engine.contracts.requirements_models import AssetRequirement, TrackType
from asset_engine.requirements.extractor import extract_requirements

from narration_tts import google_tts
from narration_tts.drama_prompt import (
    build_drama_prompt,
    character_audio_from_gita,
    find_dialogue_turn,
    find_scene_for_speaker,
)
from narration_tts.folder_paths import voice_clip_asset_dir

logger = logging.getLogger(__name__)


_DEFAULT_VOICE_MALE = "Charon"
_DEFAULT_VOICE_FEMALE = "Achernar"
_DEFAULT_VOICE_NARRATOR = "Algieba"
_VOICE_FILENAME = "narration_tts.wav"
_META_FILENAME = "tts_meta.json"


@dataclass
class CharacterPackage:
    """All voice requirements for a single speaker."""

    speaker: str
    voice: str
    requirements: list[AssetRequirement] = field(default_factory=list)


@dataclass
class CharacterResult:
    """Per-character generation result."""

    speaker: str
    voice: str
    total_clips: int = 0
    generated: int = 0
    skipped_existing: int = 0
    skipped_empty: int = 0
    failed: list[dict] = field(default_factory=list)


@dataclass
class DramaTTSResult:
    """Aggregate result of a drama TTS run."""

    characters: list[CharacterResult]

    @property
    def total_generated(self) -> int:
        return sum(c.generated for c in self.characters)

    @property
    def total_failed(self) -> int:
        return sum(len(c.failed) for c in self.characters)

    def to_summary_dict(self) -> dict:
        return {
            "total_generated": self.total_generated,
            "total_failed": self.total_failed,
            "characters": [
                {
                    "speaker": c.speaker,
                    "voice": c.voice,
                    "total_clips": c.total_clips,
                    "generated": c.generated,
                    "skipped_existing": c.skipped_existing,
                    "skipped_empty": c.skipped_empty,
                    "failed": c.failed,
                }
                for c in self.characters
            ],
        }


def _norm_speaker_key(value: str) -> str:
    return "".join(ch for ch in value.upper().strip() if ch.isalnum())


def _resolve_voice_for_speaker(speaker: str, voice_map: dict[str, str], default_voice: str) -> str:
    """Look up the configured voice for *speaker*; fall back to default."""
    if not voice_map:
        return default_voice
    direct = voice_map.get(speaker)
    if direct:
        return str(direct)
    norm = _norm_speaker_key(speaker)
    for key, value in voice_map.items():
        if _norm_speaker_key(key) == norm:
            return str(value)
    return default_voice


def voice_map_from_gita(gita: dict, default_voice: str = _DEFAULT_VOICE_MALE) -> dict[str, str]:
    """Build a ``{speaker_alias: gemini_voice}`` mapping from a gita payload."""
    if not isinstance(gita, dict):
        return {}
    characters = gita.get("characters", {})
    out: dict[str, str] = {}
    if not isinstance(characters, dict):
        return out
    for entry in characters.values():
        if not isinstance(entry, dict):
            continue
        voice = str(entry.get("tts_voice") or "").strip()
        if not voice:
            continue
        name = str(entry.get("name") or "").strip()
        if name:
            out[name] = voice
        aliases = entry.get("aliases")
        if isinstance(aliases, list):
            for alias in aliases:
                a = str(alias).strip()
                if a:
                    out[a] = voice
    if default_voice and "*" not in out:
        out.setdefault("*", default_voice)
    return out


def _default_voice_for_speaker(
    speaker: str,
    *,
    track: DraftTrack | None = None,
) -> str:
    norm = _norm_speaker_key(speaker)
    if norm == "NARRATOR" or norm.endswith("NARRATOR"):
        return _DEFAULT_VOICE_NARRATOR
    if track is not None and getattr(track, "voice_profile", None) is not None:
        gender = str(getattr(track.voice_profile, "gender", "") or "").strip().lower()
        if gender == "female":
            return _DEFAULT_VOICE_FEMALE
        if gender == "male":
            return _DEFAULT_VOICE_MALE
    return _DEFAULT_VOICE_MALE


def _voice_for_speaker(
    speaker: str,
    voice_map: dict[str, str],
    default_voice: str | None,
    *,
    track: DraftTrack | None = None,
) -> str:
    if not voice_map:
        return default_voice or _default_voice_for_speaker(speaker, track=track)
    fallback = str(
        voice_map.get("*")
        or default_voice
        or _default_voice_for_speaker(speaker, track=track)
    )
    return _resolve_voice_for_speaker(speaker, voice_map, fallback)


def _group_by_character(
    requirements: list[AssetRequirement],
    voice_map: dict[str, str],
    default_voice: str | None,
    track_by_id: dict[str, DraftTrack],
) -> list[CharacterPackage]:
    """Group voice requirements deterministically by speaker."""
    groups: dict[str, list[AssetRequirement]] = defaultdict(list)
    for req in requirements:
        if req.track_type != TrackType.VOICE:
            continue
        text = (req.tts_text or req.descriptor or "").strip()
        if not text:
            continue
        groups[req.track_id].append(req)

    packages: list[CharacterPackage] = []
    for speaker in sorted(groups.keys(), key=lambda s: s.lower()):
        clips = sorted(groups[speaker], key=lambda r: (r.scene_index, r.clip_index))
        packages.append(
            CharacterPackage(
                speaker=speaker,
                voice=_voice_for_speaker(
                    speaker,
                    voice_map,
                    default_voice,
                    track=track_by_id.get(speaker),
                ),
                requirements=clips,
            )
        )
    return packages


def _write_meta(
    out_wav: Path,
    *,
    voice: str,
    model: str,
    temperature: float,
    speaker: str,
    line_text: str | None = None,
    delivery_hint: str | None = None,
    prompt: str | None = None,
) -> None:
    meta_path = out_wav.with_name(_META_FILENAME)
    payload: dict[str, object] = {
        "voice": voice,
        "model": model,
        "temperature": temperature,
        "speaker": speaker,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "wav": out_wav.name,
    }
    if line_text is not None:
        payload["line_text"] = line_text
    if delivery_hint:
        payload["delivery_hint"] = delivery_hint
    if prompt is not None:
        payload["prompt"] = prompt
    meta_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _set_voice_env(voice: str) -> str | None:
    """Override GEMINI_TTS_VOICE for a single batch; return prior value."""
    prev = os.environ.get("GEMINI_TTS_VOICE")
    os.environ["GEMINI_TTS_VOICE"] = voice
    return prev


def _restore_voice_env(prev: str | None) -> None:
    if prev is None:
        os.environ.pop("GEMINI_TTS_VOICE", None)
    else:
        os.environ["GEMINI_TTS_VOICE"] = prev


def plan_voice_packages(
    draft_path: Path,
    *,
    voice_map: dict[str, str] | None = None,
    default_voice: str | None = None,
    only_speaker: str | None = None,
) -> list[CharacterPackage]:
    """Build the ordered per-character package list without making any TTS calls."""
    payload = json.loads(draft_path.read_text(encoding="utf-8"))
    draft = DraftTimeline(**payload)
    track_by_id = {track.id: track for track in draft.tracks}
    reqs = extract_requirements(draft)
    packages = _group_by_character(reqs, voice_map or {}, default_voice, track_by_id)
    if only_speaker:
        norm_target = _norm_speaker_key(only_speaker)
        packages = [p for p in packages if _norm_speaker_key(p.speaker) == norm_target]
    return packages


def fill_drama_voice_requirements(
    draft_path: Path,
    library_root: Path,
    *,
    voice_map: dict[str, str] | None = None,
    default_voice: str | None = None,
    only_speaker: str | None = None,
    skip_existing: bool = True,
    pause_between_clips_s: float = 1.5,
    pause_between_characters_s: float = 5.0,
    max_clips_per_character_per_minute: int = 10,
    api_key: str | None = None,
    summary_path: Path | None = None,
    dry_run: bool = False,
    gita: dict | None = None,
    narrative_plan: dict | None = None,
    use_prompt: bool = True,
    sample_context: str | None = None,
) -> DramaTTSResult:
    """Generate WAVs for every drama voice clip, batched per character.

    Behavior:
    - Voice requirements grouped by ``track_id`` (speaker).
    - One character processed at a time (sequential), one clip at a time.
    - Manual recordings (existing WAVs in the folder) are honored when
      ``skip_existing=True``: any audio file already present skips that clip.
    - When ``use_prompt`` is True (default) and *narrative_plan*/*gita* are
      provided, each clip is wrapped in a structured prompt (Audio Profile,
      Director's Note, Scene, Sample Context, tagged Transcript) so Gemini
      Flash TTS reads the line in character and in scene.  Pass
      ``use_prompt=False`` to fall back to raw dialogue text.
    - Stable retries on 429/5xx are inherited from
      :func:`narration_tts.google_tts.synthesize_text_to_linear16_wav`.
    """
    packages = plan_voice_packages(
        draft_path,
        voice_map=voice_map,
        default_voice=default_voice,
        only_speaker=only_speaker,
    )

    results: list[CharacterResult] = []
    if dry_run:
        for pkg in packages:
            results.append(
                CharacterResult(
                    speaker=pkg.speaker,
                    voice=pkg.voice,
                    total_clips=len(pkg.requirements),
                )
            )
        result = DramaTTSResult(characters=results)
        if summary_path is not None:
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(
                json.dumps(result.to_summary_dict(), indent=2),
                encoding="utf-8",
            )
        return result

    if not packages:
        return DramaTTSResult(characters=[])

    key = google_tts._api_key(api_key)  # type: ignore[attr-defined]
    model = google_tts._tts_model()  # type: ignore[attr-defined]
    temperature = google_tts._tts_temperature()  # type: ignore[attr-defined]

    for idx, pkg in enumerate(packages):
        char_result = CharacterResult(
            speaker=pkg.speaker,
            voice=pkg.voice,
            total_clips=len(pkg.requirements),
        )

        char_audio = character_audio_from_gita(pkg.speaker, gita) if use_prompt else None

        prev_voice = _set_voice_env(pkg.voice)
        try:
            window_start = time.monotonic()
            window_count = 0
            for req in pkg.requirements:
                line_text = (req.tts_text or req.descriptor or "").strip()
                if not line_text:
                    char_result.skipped_empty += 1
                    continue

                folder = voice_clip_asset_dir(library_root, req)
                folder.mkdir(parents=True, exist_ok=True)
                if skip_existing and _folder_already_has_audio(folder):
                    char_result.skipped_existing += 1
                    continue

                out_wav = folder / _VOICE_FILENAME

                if max_clips_per_character_per_minute > 0:
                    elapsed = time.monotonic() - window_start
                    if window_count >= max_clips_per_character_per_minute and elapsed < 60.0:
                        sleep_for = 60.0 - elapsed
                        logger.info(
                            "Per-minute cap reached for %s; sleeping %.1fs",
                            pkg.speaker,
                            sleep_for,
                        )
                        time.sleep(sleep_for)
                        window_start = time.monotonic()
                        window_count = 0

                delivery_hint = ""
                if use_prompt and narrative_plan is not None:
                    scene = find_scene_for_speaker(
                        narrative_plan,
                        pkg.speaker,
                        scene_index=req.scene_index,
                    )
                    turn = find_dialogue_turn(scene, pkg.speaker, line_text) if scene else None
                    if turn:
                        delivery_hint = str(turn.get("delivery_hint") or "").strip()

                if use_prompt:
                    synthesis_text = build_drama_prompt(
                        line_text=line_text,
                        speaker=pkg.speaker,
                        gita=gita,
                        narrative_plan=narrative_plan,
                        scene_index=req.scene_index,
                        sample_context=sample_context,
                        delivery_hint_override=delivery_hint or None,
                        audio_override=char_audio,
                    )
                else:
                    synthesis_text = line_text

                try:
                    google_tts.synthesize_text_to_linear16_wav(
                        synthesis_text,
                        out_wav,
                        api_key=key,
                    )
                    _write_meta(
                        out_wav,
                        voice=pkg.voice,
                        model=model,
                        temperature=temperature,
                        speaker=pkg.speaker,
                        line_text=line_text,
                        delivery_hint=delivery_hint or None,
                        prompt=synthesis_text if use_prompt else None,
                    )
                    char_result.generated += 1
                    window_count += 1
                except Exception as exc:  # pragma: no cover - exercised in integration
                    char_result.failed.append(
                        {
                            "requirement_id": req.requirement_id,
                            "error": str(exc),
                        }
                    )
                    logger.warning(
                        "TTS failed for %s (%s): %s",
                        pkg.speaker,
                        req.requirement_id,
                        exc,
                    )

                if pause_between_clips_s > 0:
                    time.sleep(pause_between_clips_s)
        finally:
            _restore_voice_env(prev_voice)

        results.append(char_result)

        is_last = idx == len(packages) - 1
        if not is_last and pause_between_characters_s > 0:
            logger.info(
                "Sleeping %.1fs before next character package",
                pause_between_characters_s,
            )
            time.sleep(pause_between_characters_s)

    result = DramaTTSResult(characters=results)
    if summary_path is not None:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            json.dumps(result.to_summary_dict(), indent=2),
            encoding="utf-8",
        )
    return result


_AUDIO_EXTS = {".wav", ".mp3", ".ogg", ".flac", ".m4a"}


def _folder_already_has_audio(folder: Path) -> bool:
    if not folder.exists():
        return False
    for item in folder.iterdir():
        if item.is_file() and item.suffix.lower() in _AUDIO_EXTS and item.stat().st_size > 0:
            return True
    return False
