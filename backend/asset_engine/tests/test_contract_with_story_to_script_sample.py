from __future__ import annotations

import json
from pathlib import Path
import struct
import wave

import pytest

from asset_engine.pipeline import run_asset_pipeline


def _write_wav(path: Path, duration: float = 1.0, sample_rate: int = 22050) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = int(duration * sample_rate)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for _ in range(frames):
            wav.writeframesraw(struct.pack("<h", 0))


@pytest.mark.integration
def test_story_to_script_sample_contract(tmp_path: Path):
    sample_draft = Path("c:/AS/pcddj_engine/story-to-script/example_draft_timeline.json")
    if not sample_draft.exists():
        pytest.skip("story-to-script sample draft not found")

    library = tmp_path / "library"
    _write_wav(library / "music" / "neutral_mid.wav", 3.0)
    _write_wav(library / "ambience" / "neutral_room.wav", 4.0)
    _write_wav(library / "sfx" / "impact_accent.wav", 1.0)

    result = run_asset_pipeline(
        draft_timeline_path=sample_draft,
        output_dir=tmp_path / "out",
        library_root=library,
        voice_mode="auto",
    )

    final_payload = json.loads(Path(result["final_timeline_path"]).read_text(encoding="utf-8"))
    assert "project" in final_payload
    assert "tracks" in final_payload
    assert "scenes" in final_payload
    assert final_payload["project"]["duration"] > 0
    assert all("start" in s and "duration" in s for s in final_payload["scenes"])

