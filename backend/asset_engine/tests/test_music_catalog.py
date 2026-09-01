from __future__ import annotations

import json
from pathlib import Path
import struct
import wave

from asset_engine.contracts.requirements_models import AssetRequirement
from asset_engine.resolvers.music_catalog import MusicCatalog


def _write_wav(path: Path, duration: float = 1.0, sample_rate: int = 22050) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = int(duration * sample_rate)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for _ in range(frames):
            wav.writeframesraw(struct.pack("<h", 0))


def test_music_catalog_finds_role_and_energy_match(tmp_path: Path):
    audio_root = tmp_path / "audio_library"
    track_a = audio_root / "music" / "underscore" / "tense" / "tense_a.wav"
    track_b = audio_root / "music" / "underscore" / "calm" / "calm_a.wav"
    _write_wav(track_a)
    _write_wav(track_b)

    catalog_path = tmp_path / "music_catalog.json"
    catalog_path.write_text(
        json.dumps(
            {
                "version": "1",
                "tracks": [
                    {
                        "path": "music/underscore/tense/tense_a.wav",
                        "role": "underscore",
                        "emotion": ["tension"],
                        "energy": 0.75,
                        "loopable": True,
                        "duration_s": 35.0,
                        "tags": ["dark", "pulse"],
                    },
                    {
                        "path": "music/underscore/calm/calm_a.wav",
                        "role": "underscore",
                        "emotion": ["calm"],
                        "energy": 0.2,
                        "loopable": True,
                        "duration_s": 35.0,
                        "tags": ["soft"],
                    },
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    req = AssetRequirement(
        requirement_id="scene_1:music:0",
        asset_kind="music",
        scene_id="scene_1",
        scene_name="Hall",
        scene_index=0,
        track_id="music",
        clip_index=0,
        descriptor="tension underscore",
        mood="tension",
        energy_hint=0.8,
        loop=True,
    )

    catalog = MusicCatalog.load(catalog_path)
    match = catalog.find_best(req, audio_root)
    assert match is not None
    assert match.file_path == track_a.resolve()
    assert match.score > 0.45


def test_music_catalog_validation_rejects_bad_role(tmp_path: Path):
    catalog_path = tmp_path / "music_catalog.json"
    catalog_path.write_text(
        json.dumps(
            {
                "tracks": [
                    {
                        "path": "music/x.wav",
                        "role": "bad_role",
                    }
                ]
            },
        ),
        encoding="utf-8",
    )

    try:
        MusicCatalog.load(catalog_path)
    except ValueError as exc:
        assert "invalid role" in str(exc)
    else:
        raise AssertionError("expected validation failure for bad role")
