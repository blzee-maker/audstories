from __future__ import annotations

import json
from pathlib import Path
import struct
import wave

import pytest

from asset_engine import cli
from asset_engine.utils.path_utils import make_voice_folder_name


def _write_wav(path: Path, duration: float = 0.5, sample_rate: int = 22050) -> None:
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
        "settings": {"default_silence": 0.3},
        "tracks": [{"id": "narrator", "type": "voice", "role": "voice", "gain": 0}],
        "scenes": [
            {
                "id": "scene_1",
                "name": "Abandoned House",
                "energy": 0.4,
                "tracks": {"narrator": [{"tts_text": "Hello there", "order": 0}]},
            }
        ],
    }


def test_cli_scaffold_creates_structure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys):
    draft = tmp_path / "draft.json"
    draft.write_text(json.dumps(_draft_payload()), encoding="utf-8")
    library = tmp_path / "library"

    monkeypatch.setattr(
        "sys.argv",
        ["asset-engine", "scaffold", "--draft", str(draft), "--library", str(library)],
    )
    cli.main()
    output = capsys.readouterr().out
    assert "Scaffold root" in output
    assert (library / "REQUIREMENTS.md").exists()


def test_cli_run_missing_assets_exits_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    draft = tmp_path / "draft.json"
    draft.write_text(json.dumps(_draft_payload()), encoding="utf-8")
    library = tmp_path / "library"
    out_dir = tmp_path / "out"

    monkeypatch.setattr(
        "sys.argv",
        [
            "asset-engine",
            "run",
            "--draft",
            str(draft),
            "--library",
            str(library),
            "--out",
            str(out_dir),
        ],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 1
    output = capsys.readouterr().out
    assert "Assets missing. Fill folders and run again." in output


def test_cli_run_complete_prints_render_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    draft = tmp_path / "draft.json"
    draft.write_text(json.dumps(_draft_payload()), encoding="utf-8")
    library = tmp_path / "library"
    out_dir = tmp_path / "out"

    folder = make_voice_folder_name(0, "Abandoned House", "narrator")
    _write_wav(library / "voice" / folder / "clip_000" / "clip_000.wav")

    monkeypatch.setattr(
        "sys.argv",
        [
            "asset-engine",
            "run",
            "--draft",
            str(draft),
            "--library",
            str(library),
            "--out",
            str(out_dir),
        ],
    )
    cli.main()
    output = capsys.readouterr().out
    assert "Render ready." in output
    assert (out_dir / "final_timeline.json").exists()

def test_cli_library_index_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys):
    audio_root = tmp_path / "audio_library"
    _write_wav(audio_root / "sfx" / "door.wav")
    monkeypatch.setattr(
        "sys.argv",
        [
            "asset-engine",
            "library",
            "index",
            "--kind",
            "sfx",
            "--audio-library",
            str(audio_root),
        ],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "Index written" in out
    assert (audio_root / "index" / "sfx_index.json").is_file()


def test_cli_require_voice_fails_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    draft = tmp_path / "draft.json"
    draft.write_text(json.dumps(_draft_payload()), encoding="utf-8")
    library = tmp_path / "library"
    out_dir = tmp_path / "out"

    monkeypatch.setattr(
        "sys.argv",
        [
            "asset-engine",
            "resolve",
            "--draft",
            str(draft),
            "--library",
            str(library),
            "--out",
            str(out_dir),
            "--require-voice",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 1
