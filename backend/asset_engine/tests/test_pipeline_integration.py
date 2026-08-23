from __future__ import annotations

import json
from pathlib import Path
import struct
import wave

from asset_engine.pipeline import run_asset_pipeline
from asset_engine.utils.path_utils import make_asset_folder_name


def _write_wav(path: Path, duration: float = 1.0, sample_rate: int = 22050) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = int(duration * sample_rate)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for _ in range(frames):
            wav.writeframesraw(struct.pack("<h", 0))


def test_pipeline_builds_final_timeline(tmp_path: Path):
    library = tmp_path / "library"
    _write_wav(
        library / "music" / make_asset_folder_name(0, "Scene 1", "neutral_mid") / "neutral_mid.wav",
        2.0,
    )
    _write_wav(
        library / "ambience" / make_asset_folder_name(0, "Scene 1", "neutral_room") / "neutral_room.wav",
        2.5,
    )
    _write_wav(
        library / "sfx" / make_asset_folder_name(0, "Scene 1", "impact_accent") / "impact_accent.wav",
        0.8,
    )

    draft = {
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
                "name": "Scene 1",
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

    draft_path = tmp_path / "draft_timeline.json"
    draft_path.write_text(json.dumps(draft), encoding="utf-8")

    out_dir = tmp_path / "out"
    result = run_asset_pipeline(
        draft_timeline_path=draft_path,
        output_dir=out_dir,
        library_root=library,
        voice_mode="auto",
    )

    final_path = Path(result["final_timeline_path"])
    manifest_path = Path(result["manifest_path"])

    assert final_path.exists()
    assert manifest_path.exists()

    final_payload = json.loads(final_path.read_text(encoding="utf-8"))
    assert final_payload["project"]["duration"] > 0
    assert final_payload["scenes"][0]["duration"] > 0
    assert final_payload["scenes"][0]["start"] == 0.0

