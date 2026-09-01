from __future__ import annotations

import json
from pathlib import Path
import struct
import wave

from asset_engine.pipeline import run_asset_pipeline
from asset_engine.utils.path_utils import make_asset_folder_name, make_voice_folder_name


def _write_wav(path: Path, duration: float = 1.0, sample_rate: int = 22050) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = int(duration * sample_rate)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for _ in range(frames):
            wav.writeframesraw(struct.pack("<h", 0))


def _draft_payload() -> dict:
    return {
        "project": {"name": "demo", "sample_rate": 48000, "bit_depth": 16},
        "settings": {"default_silence": 0.3, "normalize": True},
        "tracks": [
            {"id": "narrator", "type": "voice", "role": "voice", "gain": 0},
            {"id": "music", "type": "music", "role": "background", "gain": -10},
            {"id": "ambience", "type": "ambience", "role": "background", "gain": -12},
            {"id": "sfx", "type": "sfx", "role": "foreground", "gain": -4},
        ],
        "scenes": [
            {
                "id": "scene_1",
                "name": "Abandoned House",
                "energy": 0.4,
                "tracks": {
                    "narrator": [{"tts_text": "Hello there", "order": 0}],
                    "music": [{"mood": "neutral_mid", "loop": True}],
                    "ambience": [{"atmosphere": "neutral_room", "loop": True}],
                    "sfx": [{"sfx_hint": "impact_accent", "semantic_role": "impact"}],
                },
            }
        ],
    }


def test_pipeline_applies_partial_policies(tmp_path: Path):
    library = tmp_path / "library"
    draft_path = tmp_path / "draft_timeline.json"
    draft_path.write_text(json.dumps(_draft_payload()), encoding="utf-8")

    # Provide only music + ambience + sfx. Voice is intentionally missing.
    _write_wav(
        library / "music" / make_asset_folder_name(0, "Abandoned House", "neutral_mid") / "music.wav",
        2.0,
    )
    _write_wav(
        library / "ambience" / make_asset_folder_name(0, "Abandoned House", "neutral_room") / "amb.wav",
        2.5,
    )
    _write_wav(
        library / "sfx" / make_asset_folder_name(0, "Abandoned House", "impact_accent") / "sfx.wav",
        0.8,
    )

    out_dir = tmp_path / "out"
    result = run_asset_pipeline(
        draft_timeline_path=draft_path,
        output_dir=out_dir,
        library_root=library,
        voice_mode="auto",
    )
    assert Path(result["final_timeline_path"]).exists()
    assert Path(result["manifest_path"]).exists()

    payload = json.loads(Path(result["final_timeline_path"]).read_text(encoding="utf-8"))
    voice_clips = payload["scenes"][0]["tracks"]["narrator"]
    assert len(voice_clips) == 1
    assert voice_clips[0]["file"].endswith("_silence.wav")


def test_pipeline_resolves_voice_when_present(tmp_path: Path):
    library = tmp_path / "library"
    draft_path = tmp_path / "draft_timeline.json"
    draft_path.write_text(json.dumps(_draft_payload()), encoding="utf-8")

    voice_folder = make_voice_folder_name(0, "Abandoned House", "narrator")
    _write_wav(library / "voice" / voice_folder / "clip_000" / "clip_000.wav", 1.0)
    _write_wav(library / "music" / make_asset_folder_name(0, "Abandoned House", "neutral_mid") / "music.wav")
    _write_wav(library / "ambience" / make_asset_folder_name(0, "Abandoned House", "neutral_room") / "amb.wav")
    _write_wav(library / "sfx" / make_asset_folder_name(0, "Abandoned House", "impact_accent") / "sfx.wav")

    out_dir = tmp_path / "out"
    result = run_asset_pipeline(
        draft_timeline_path=draft_path,
        output_dir=out_dir,
        library_root=library,
        voice_mode="auto",
    )
    payload = json.loads(Path(result["final_timeline_path"]).read_text(encoding="utf-8"))
    voice_file = payload["scenes"][0]["tracks"]["narrator"][0]["file"]
    assert voice_file.endswith("clip_000.wav")

def test_pipeline_writes_voice_status_file(tmp_path: Path):
    library = tmp_path / "library"
    draft_path = tmp_path / "draft_timeline.json"
    draft_path.write_text(json.dumps(_draft_payload()), encoding="utf-8")

    voice_folder = make_voice_folder_name(0, "Abandoned House", "narrator")
    _write_wav(library / "voice" / voice_folder / "clip_000" / "voice.wav", 1.2)
    _write_wav(library / "music" / make_asset_folder_name(0, "Abandoned House", "neutral_mid") / "music.wav")
    _write_wav(library / "ambience" / make_asset_folder_name(0, "Abandoned House", "neutral_room") / "amb.wav")
    _write_wav(library / "sfx" / make_asset_folder_name(0, "Abandoned House", "impact_accent") / "sfx.wav")

    out_dir = tmp_path / "out"
    result = run_asset_pipeline(
        draft_timeline_path=draft_path,
        output_dir=out_dir,
        library_root=library,
        voice_mode="auto",
    )

    voice_status = Path(result["voice_status_path"])
    assert voice_status.is_file()
    payload = json.loads(voice_status.read_text(encoding="utf-8"))
    assert payload["summary"]["total_voice_requirements"] == 1
    assert payload["summary"]["resolved"] == 1


def test_pipeline_require_voice_fails_when_unresolved(tmp_path: Path):
    from asset_engine.resolvers import ResolveOptions

    library = tmp_path / "library"
    draft_path = tmp_path / "draft_timeline.json"
    draft_path.write_text(json.dumps(_draft_payload()), encoding="utf-8")

    _write_wav(library / "music" / make_asset_folder_name(0, "Abandoned House", "neutral_mid") / "music.wav")
    _write_wav(library / "ambience" / make_asset_folder_name(0, "Abandoned House", "neutral_room") / "amb.wav")
    _write_wav(library / "sfx" / make_asset_folder_name(0, "Abandoned House", "impact_accent") / "sfx.wav")

    out_dir = tmp_path / "out"
    try:
        run_asset_pipeline(
            draft_timeline_path=draft_path,
            output_dir=out_dir,
            library_root=library,
            voice_mode="auto",
            resolve_options=ResolveOptions(require_voice=True),
        )
    except ValueError as exc:
        assert "Voice required" in str(exc)
    else:
        raise AssertionError("expected ValueError when require_voice is enabled")
