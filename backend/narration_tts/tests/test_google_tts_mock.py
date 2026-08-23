"""Mocked TTS fill — no network."""

from __future__ import annotations

import json
from pathlib import Path

from asset_engine.contracts.draft_models import DraftTimeline
from narration_tts import google_tts


def test_parse_audio_mime_type_rate():
    p = google_tts.parse_audio_mime_type("audio/L16;rate=48000")
    assert p["rate"] == 48000
    assert p["bits_per_sample"] == 16


def test_convert_to_wav_roundtrip_header():
    raw = b"\x00\x01" * 100
    wav = google_tts.convert_to_wav(raw, "audio/L16;rate=24000")
    assert wav[:4] == b"RIFF"
    assert b"WAVE" in wav[:12]


def test_fill_voice_requirements_skips_when_wav_exists(monkeypatch, tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_synth(text: str, out_wav: Path, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(text)
        out_wav.parent.mkdir(parents=True, exist_ok=True)
        out_wav.write_bytes(b"fake")

    monkeypatch.setattr(google_tts, "synthesize_text_to_linear16_wav", fake_synth)
    monkeypatch.setattr(google_tts, "_api_key", lambda: "dummy")

    library = tmp_path / "assets"
    out = tmp_path / "output"
    out.mkdir()
    draft = DraftTimeline(
        project={"name": "t", "sample_rate": 48000, "bit_depth": 16},
        settings={
            "project_type": "audiobook",
            "narration_only": True,
            "default_silence": 0.5,
        },
        tracks=[{"id": "narrator", "type": "voice", "role": "voice"}],
        scenes=[
            {
                "id": "scene_0",
                "name": "Open",
                "energy": 0.5,
                "tracks": {
                    "narrator": [
                        {"tts_text": "First line. Second line.", "order": 0},
                    ],
                },
            },
        ],
    )
    draft_path = out / "draft_timeline.json"
    draft_path.write_text(
        json.dumps(draft.model_dump(), indent=2),
        encoding="utf-8",
    )

    n = google_tts.fill_voice_requirements_from_draft(
        draft_path, library, skip_existing=True,
    )
    assert n == 1
    assert len(calls) == 1

    n2 = google_tts.fill_voice_requirements_from_draft(
        draft_path, library, skip_existing=True,
    )
    assert n2 == 0
