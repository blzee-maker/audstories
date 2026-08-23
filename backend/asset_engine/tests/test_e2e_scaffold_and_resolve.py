from __future__ import annotations

import json
from pathlib import Path
import struct
import wave

from asset_engine.pipeline.run_asset_pipeline import run_scaffold_phase
from asset_engine.pipeline import run_asset_pipeline
from asset_engine.contracts.draft_models import DraftTimeline
from asset_engine.requirements import extract_requirements
from asset_engine.utils.path_utils import make_asset_folder_name, make_voice_folder_name


def _write_wav(path: Path, duration: float = 0.75, sample_rate: int = 22050) -> None:
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
        "project": {"name": "e2e_demo", "sample_rate": 48000, "bit_depth": 16},
        "settings": {"default_silence": 0.5},
        "tracks": [
            {"id": "narrator", "type": "voice", "role": "voice"},
            {"id": "music", "type": "music", "role": "background"},
            {"id": "ambience", "type": "ambience", "role": "background"},
            {"id": "sfx", "type": "sfx", "role": "foreground"},
        ],
        "scenes": [
            {
                "id": "scene_1",
                "name": "Hallway",
                "energy": 0.5,
                "tracks": {
                    "narrator": [{"tts_text": "The hallway was empty.", "order": 0}],
                    "music": [{"mood": "tension_mid", "loop": True}],
                    "ambience": [{"atmosphere": "dark_interior", "loop": True}],
                    "sfx": [{"sfx_hint": "door_creak", "semantic_role": "interaction"}],
                },
            }
        ],
    }


def test_e2e_scaffold_then_resolve(tmp_path: Path):
    draft_path = tmp_path / "draft.json"
    library = tmp_path / "assets"
    out_dir = tmp_path / "out"
    draft_path.write_text(json.dumps(_draft_payload()), encoding="utf-8")

    draft = DraftTimeline(**_draft_payload())
    requirements = extract_requirements(draft)
    scaffold_result = run_scaffold_phase(draft=draft, requirements=requirements, library_root=library)
    assert scaffold_result["folders_created"] > 0
    assert (library / "REQUIREMENTS.md").exists()

    voice_folder = make_voice_folder_name(0, "Hallway", "narrator")
    _write_wav(library / "voice" / voice_folder / "clip_000" / "line.wav")
    _write_wav(library / "music" / make_asset_folder_name(0, "Hallway", "tension_mid") / "music.wav")
    _write_wav(library / "ambience" / make_asset_folder_name(0, "Hallway", "dark_interior") / "amb.wav")
    _write_wav(library / "sfx" / make_asset_folder_name(0, "Hallway", "door_creak") / "sfx.wav")

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
    assert final_payload["scenes"][0]["tracks"]["narrator"][0]["file"].endswith("line.wav")
