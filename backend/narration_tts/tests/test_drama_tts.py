"""Per-character batched drama TTS tests (no network)."""

from __future__ import annotations

import json
from pathlib import Path

from asset_engine.contracts.draft_models import DraftTimeline

from narration_tts import drama_tts, google_tts


def _drama_draft() -> DraftTimeline:
    return DraftTimeline(
        project={"name": "drama_demo", "sample_rate": 48000, "bit_depth": 16},
        settings={"project_type": "audio_drama", "default_silence": 0.5},
        tracks=[
            {"id": "ARNAV", "type": "voice", "role": "voice"},
            {"id": "EVA", "type": "voice", "role": "voice"},
        ],
        scenes=[
            {
                "id": "scene_0",
                "name": "Forest Trail",
                "energy": 0.5,
                "tracks": {
                    "ARNAV": [
                        {"tts_text": "We should turn back.", "order": 0},
                        {"tts_text": "Did you hear that?", "order": 2},
                    ],
                    "EVA": [
                        {"tts_text": "Listen.", "order": 1},
                    ],
                },
            },
        ],
    )


def _write_draft(tmp_path: Path) -> Path:
    out = tmp_path / "output"
    out.mkdir()
    draft = _drama_draft()
    draft_path = out / "draft_timeline.json"
    draft_path.write_text(json.dumps(draft.model_dump(), indent=2), encoding="utf-8")
    return draft_path


def test_voice_map_from_gita_uses_name_and_aliases():
    gita = {
        "characters": {
            "arnav": {"name": "ARNAV", "aliases": ["ARNAV", "ARN"], "tts_voice": "Charon"},
            "eva": {"name": "EVA", "aliases": ["EVA"], "tts_voice": "Aoede"},
            "narrator": {"name": "NARRATOR", "aliases": ["NARRATOR"], "tts_voice": ""},
        }
    }
    voice_map = drama_tts.voice_map_from_gita(gita, default_voice="Charon")
    assert voice_map["ARNAV"] == "Charon"
    assert voice_map["ARN"] == "Charon"
    assert voice_map["EVA"] == "Aoede"
    assert voice_map["*"] == "Charon"
    assert "NARRATOR" not in voice_map


def test_plan_voice_packages_groups_by_speaker(tmp_path: Path):
    draft_path = _write_draft(tmp_path)
    packages = drama_tts.plan_voice_packages(
        draft_path,
        voice_map={"ARNAV": "Charon", "EVA": "Aoede", "*": "Charon"},
        default_voice="Charon",
    )
    by_speaker = {p.speaker: p for p in packages}
    assert set(by_speaker.keys()) == {"ARNAV", "EVA"}
    assert by_speaker["ARNAV"].voice == "Charon"
    assert by_speaker["EVA"].voice == "Aoede"
    assert len(by_speaker["ARNAV"].requirements) == 2
    assert len(by_speaker["EVA"].requirements) == 1


def test_fill_drama_voice_requirements_per_character_batching(monkeypatch, tmp_path: Path):
    calls: list[dict] = []

    def fake_synth(text: str, out_wav: Path, **kwargs):  # type: ignore[no-untyped-def]
        calls.append({"text": text, "voice": kwargs.get("api_key") and "set", "wav": str(out_wav)})
        out_wav.parent.mkdir(parents=True, exist_ok=True)
        out_wav.write_bytes(b"fake")

    monkeypatch.setattr(google_tts, "synthesize_text_to_linear16_wav", fake_synth)
    monkeypatch.setattr(google_tts, "_api_key", lambda explicit=None: "dummy")
    monkeypatch.setattr(google_tts, "_tts_model", lambda: "gemini-fake")
    monkeypatch.setattr(google_tts, "_tts_temperature", lambda: 1.0)

    draft_path = _write_draft(tmp_path)
    library = tmp_path / "assets"

    result = drama_tts.fill_drama_voice_requirements(
        draft_path,
        library,
        voice_map={"ARNAV": "Charon", "EVA": "Aoede"},
        default_voice="Charon",
        pause_between_clips_s=0,
        pause_between_characters_s=0,
    )

    assert result.total_generated == 3
    speakers = [c.speaker for c in result.characters]
    assert speakers == ["ARNAV", "EVA"]
    arnav = next(c for c in result.characters if c.speaker == "ARNAV")
    eva = next(c for c in result.characters if c.speaker == "EVA")
    assert arnav.generated == 2
    assert eva.generated == 1

    summary_path = tmp_path / "summary.json"
    drama_tts.fill_drama_voice_requirements(
        draft_path,
        library,
        voice_map={"ARNAV": "Charon", "EVA": "Aoede"},
        default_voice="Charon",
        pause_between_clips_s=0,
        pause_between_characters_s=0,
        summary_path=summary_path,
    )
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["total_generated"] == 0  # second run should skip-existing


def test_fill_drama_voice_requirements_only_speaker(monkeypatch, tmp_path: Path):
    calls: list[str] = []

    def fake_synth(text: str, out_wav: Path, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(str(out_wav))
        out_wav.parent.mkdir(parents=True, exist_ok=True)
        out_wav.write_bytes(b"fake")

    monkeypatch.setattr(google_tts, "synthesize_text_to_linear16_wav", fake_synth)
    monkeypatch.setattr(google_tts, "_api_key", lambda explicit=None: "dummy")
    monkeypatch.setattr(google_tts, "_tts_model", lambda: "gemini-fake")
    monkeypatch.setattr(google_tts, "_tts_temperature", lambda: 1.0)

    draft_path = _write_draft(tmp_path)
    library = tmp_path / "assets"

    result = drama_tts.fill_drama_voice_requirements(
        draft_path,
        library,
        voice_map={"ARNAV": "Charon", "EVA": "Aoede"},
        default_voice="Charon",
        only_speaker="EVA",
        pause_between_clips_s=0,
        pause_between_characters_s=0,
    )
    assert [c.speaker for c in result.characters] == ["EVA"]
    assert result.total_generated == 1
    assert len(calls) == 1


def test_fill_drama_voice_requirements_dry_run(tmp_path: Path):
    draft_path = _write_draft(tmp_path)
    library = tmp_path / "assets"
    summary_path = tmp_path / "plan.json"

    result = drama_tts.fill_drama_voice_requirements(
        draft_path,
        library,
        voice_map={"ARNAV": "Charon", "EVA": "Aoede"},
        default_voice="Charon",
        pause_between_clips_s=0,
        pause_between_characters_s=0,
        summary_path=summary_path,
        dry_run=True,
    )
    assert result.total_generated == 0
    assert {c.speaker for c in result.characters} == {"ARNAV", "EVA"}
    assert summary_path.is_file()
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["total_generated"] == 0


def test_fill_drama_voice_requirements_uses_structured_prompt(monkeypatch, tmp_path: Path):
    """When use_prompt is True and a narrative_plan is provided, the synthesized
    text should be the structured Director's prompt (not just the raw line)."""
    captured: list[str] = []

    def fake_synth(text: str, out_wav: Path, **kwargs):  # type: ignore[no-untyped-def]
        captured.append(text)
        out_wav.parent.mkdir(parents=True, exist_ok=True)
        out_wav.write_bytes(b"fake")

    monkeypatch.setattr(google_tts, "synthesize_text_to_linear16_wav", fake_synth)
    monkeypatch.setattr(google_tts, "_api_key", lambda explicit=None: "dummy")
    monkeypatch.setattr(google_tts, "_tts_model", lambda: "gemini-fake")
    monkeypatch.setattr(google_tts, "_tts_temperature", lambda: 1.0)

    draft_path = _write_draft(tmp_path)
    library = tmp_path / "assets"

    gita = {
        "characters": {
            "arnav": {
                "name": "ARNAV",
                "aliases": ["ARNAV"],
                "audio_profile": "Warm baritone scout.",
                "style": "Conversational",
                "pace": "Brisk",
                "accent": "Indian English",
                "tts_voice": "Charon",
            },
            "eva": {
                "name": "EVA",
                "aliases": ["EVA"],
                "audio_profile": "Soft mezzo, contemplative.",
                "style": "Whisper",
                "pace": "The Drift",
                "accent": "British (GB)",
                "tts_voice": "Aoede",
            },
        },
        "audio": {"sample_context": "Audio drama, atmospheric."},
    }
    narrative_plan = {
        "scenes": [
            {
                "structure": {
                    "scene_title": "EXT. FOREST - NIGHT",
                    "speakers": ["ARNAV", "EVA"],
                    "dialogue_turns": [
                        {"speaker": "ARNAV", "text": "We should turn back.", "delivery_hint": "nervous"},
                        {"speaker": "EVA", "text": "Listen.", "delivery_hint": "hushed"},
                        {"speaker": "ARNAV", "text": "Did you hear that?", "delivery_hint": "tense"},
                    ],
                    "ambience_cue": {"primary_atmosphere": "forest_night_owl"},
                    "action_notes": ["Distant rustle.", "Branches creak."],
                },
                "interpretation": {
                    "primary_emotion": "anxiety",
                    "energy_level": 6,
                    "emotion_intensity": 7,
                    "scene_style": "tense",
                },
            }
        ],
    }

    result = drama_tts.fill_drama_voice_requirements(
        draft_path,
        library,
        voice_map={"ARNAV": "Charon", "EVA": "Aoede"},
        default_voice="Charon",
        pause_between_clips_s=0,
        pause_between_characters_s=0,
        gita=gita,
        narrative_plan=narrative_plan,
        use_prompt=True,
    )

    assert result.total_generated == 3
    assert any("Warm baritone scout." in text for text in captured)
    assert any("Soft mezzo, contemplative." in text for text in captured)
    assert any("[nervous] We should turn back." in text for text in captured)
    assert any("[hushed] Listen." in text for text in captured)
    assert all("## Transcript:" in text for text in captured)
    assert all("EXT. FOREST - NIGHT" in text for text in captured)
    assert all("Audio drama, atmospheric." in text for text in captured)


def test_fill_drama_voice_requirements_no_prompt_sends_raw_text(monkeypatch, tmp_path: Path):
    captured: list[str] = []

    def fake_synth(text: str, out_wav: Path, **kwargs):  # type: ignore[no-untyped-def]
        captured.append(text)
        out_wav.parent.mkdir(parents=True, exist_ok=True)
        out_wav.write_bytes(b"fake")

    monkeypatch.setattr(google_tts, "synthesize_text_to_linear16_wav", fake_synth)
    monkeypatch.setattr(google_tts, "_api_key", lambda explicit=None: "dummy")
    monkeypatch.setattr(google_tts, "_tts_model", lambda: "gemini-fake")
    monkeypatch.setattr(google_tts, "_tts_temperature", lambda: 1.0)

    draft_path = _write_draft(tmp_path)
    library = tmp_path / "assets"

    result = drama_tts.fill_drama_voice_requirements(
        draft_path,
        library,
        voice_map={"ARNAV": "Charon", "EVA": "Aoede"},
        default_voice="Charon",
        pause_between_clips_s=0,
        pause_between_characters_s=0,
        use_prompt=False,
    )
    assert result.total_generated == 3
    assert all("## Transcript:" not in text for text in captured)
    assert "Listen." in captured


def test_fill_drama_voice_requirements_honors_manual_recording(monkeypatch, tmp_path: Path):
    """When a real WAV already exists, TTS should skip that clip (manual wins)."""
    monkeypatch.setattr(google_tts, "_api_key", lambda explicit=None: "dummy")
    monkeypatch.setattr(google_tts, "_tts_model", lambda: "gemini-fake")
    monkeypatch.setattr(google_tts, "_tts_temperature", lambda: 1.0)

    def fake_synth(text: str, out_wav: Path, **kwargs):  # type: ignore[no-untyped-def]
        out_wav.parent.mkdir(parents=True, exist_ok=True)
        out_wav.write_bytes(b"tts")

    monkeypatch.setattr(google_tts, "synthesize_text_to_linear16_wav", fake_synth)

    draft_path = _write_draft(tmp_path)
    library = tmp_path / "assets"

    # Manually create one WAV for ARNAV's first clip.
    from narration_tts.folder_paths import voice_clip_asset_dir
    from asset_engine.requirements.extractor import extract_requirements

    payload = json.loads(draft_path.read_text(encoding="utf-8"))
    draft = DraftTimeline(**payload)
    reqs = [r for r in extract_requirements(draft) if r.track_id == "ARNAV"]
    folder = voice_clip_asset_dir(library, reqs[0])
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "user_take.wav").write_bytes(b"user")

    result = drama_tts.fill_drama_voice_requirements(
        draft_path,
        library,
        voice_map={"ARNAV": "Charon", "EVA": "Aoede"},
        default_voice="Charon",
        pause_between_clips_s=0,
        pause_between_characters_s=0,
    )
    arnav = next(c for c in result.characters if c.speaker == "ARNAV")
    assert arnav.skipped_existing == 1
    assert arnav.generated == 1


def test_plan_voice_packages_uses_role_defaults(tmp_path: Path):
    draft = DraftTimeline(
        project={"name": "drama_demo", "sample_rate": 48000, "bit_depth": 16},
        settings={"project_type": "audio_drama", "default_silence": 0.5},
        tracks=[
            {
                "id": "NARRATOR",
                "type": "voice",
                "role": "voice",
            },
            {
                "id": "PRIYA",
                "type": "voice",
                "role": "voice",
                "voice_profile": {"gender": "female"},
            },
            {
                "id": "ARJUN",
                "type": "voice",
                "role": "voice",
                "voice_profile": {"gender": "male"},
            },
        ],
        scenes=[
            {
                "id": "scene_0",
                "name": "Open",
                "energy": 0.5,
                "tracks": {
                    "NARRATOR": [{"tts_text": "It was raining.", "order": 0}],
                    "PRIYA": [{"tts_text": "We need to go.", "order": 1}],
                    "ARJUN": [{"tts_text": "Now.", "order": 2}],
                },
            },
        ],
    )
    draft_path = tmp_path / "draft_timeline.json"
    draft_path.write_text(json.dumps(draft.model_dump(), indent=2), encoding="utf-8")

    packages = drama_tts.plan_voice_packages(draft_path, voice_map={})
    by_speaker = {p.speaker: p.voice for p in packages}
    assert by_speaker["NARRATOR"] == "Algieba"
    assert by_speaker["PRIYA"] == "Achernar"
    assert by_speaker["ARJUN"] == "Charon"
