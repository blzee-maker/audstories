"""Tests for Fountain AST -> Narrative Plan mapping."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import wave
from pathlib import Path

import orjson
import pytest

from dsl.compiler import compile_timeline_json
from dsl.schema import DraftTimeline
from story_processing.fountain.parser import parse_fountain
from story_processing.fountain.to_plan import process_script_json, script_to_narrative_plan_dict


def _eva_script_path() -> Path:
    return Path(__file__).resolve().parent.parent / "examples" / "eva_opening.fountain"


def _eva_golden_path() -> Path:
    return Path(__file__).resolve().parent.parent / "examples" / "eva_opening_golden.json"


def _trail_script_path() -> Path:
    return Path(__file__).resolve().parent.parent / "examples" / "trail_of_bells.fountain"


def _trail_golden_path() -> Path:
    return Path(__file__).resolve().parent.parent / "examples" / "trail_of_bells_golden.json"


def _write_silence_wav(path: Path, *, seconds: float = 0.2, sample_rate: int = 48000) -> None:
    frames = int(seconds * sample_rate)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * frames)


def test_eva_script_maps_to_expected_scene_and_voice_shapes():
    script_text = _eva_script_path().read_text(encoding="utf-8")
    ast = parse_fountain(script_text)
    plan = script_to_narrative_plan_dict(ast, project_type="audio_drama")

    assert plan["schema_version"] == "1.0"
    assert len(plan["scenes"]) == 2
    assert plan["scenes"][0]["structure"]["scene_title"] == "NOWHERE/EVERYWHERE"
    assert plan["scenes"][1]["structure"]["scene_title"] == "INT. EVA GRAFF'S QUARTERS"

    speakers = plan["scenes"][0]["structure"]["speakers"]
    assert "EVA" in speakers

    segments = plan["scenes"][0]["structure"]["narration_segments"]
    assert any(seg["segment_type"] == "inner_thought" for seg in segments)
    turns = plan["scenes"][0]["structure"]["dialogue_turns"]
    assert any("delivery_hint" in t for t in turns)


def test_eva_script_extracts_sfx_and_ambience_hints():
    script_text = _eva_script_path().read_text(encoding="utf-8")
    plan = orjson.loads(process_script_json(script_text, project_type="audio_drama"))

    scene0 = plan["scenes"][0]
    sfx_labels = {e["sfx_label"] for e in scene0["structure"]["sfx_events"]}
    assert "sonar_ping" in sfx_labels
    assert scene0["structure"]["ambience_cue"]["primary_atmosphere"] in {
        "underwater_deep",
        "ocean_depth",
    }
    assert scene0["interpretation"]["energy_level"] >= 5
    assert scene0["interpretation"]["primary_emotion"] in {
        "anxiety",
        "anticipation",
        "nostalgia",
        "neutral",
    }


def test_delivery_normalization_variants_and_mood_inference():
    script = """
INT. HALLWAY - NIGHT
A loud slam echoes in the dark corridor.

EVA
(in a whisper)
We should not be here.

MARCUS
(urgently)
Move now!
""".strip()
    plan = orjson.loads(process_script_json(script, project_type="audio_drama"))
    scene = plan["scenes"][0]
    turns = scene["structure"]["dialogue_turns"]
    hints = {t.get("delivery_hint") for t in turns}
    assert "whispered" in hints
    assert "urgent" in hints
    assert scene["interpretation"]["energy_level"] >= 6
    assert scene["interpretation"]["primary_emotion"] in {"anxiety", "anger", "anticipation"}


def test_compiled_timeline_validates_with_pydantic_schema():
    script_text = _eva_script_path().read_text(encoding="utf-8")
    plan = orjson.loads(process_script_json(script_text, project_type="audio_drama"))
    draft_bytes = compile_timeline_json(plan, project_type="audio_drama", narration_only=False)
    draft_payload = json.loads(draft_bytes.decode("utf-8"))

    validated = DraftTimeline(**draft_payload)
    assert len(validated.scenes) >= 1
    assert any(track.id.startswith("character_") for track in validated.tracks)


def test_eva_summary_matches_golden_fixture():
    script_text = _eva_script_path().read_text(encoding="utf-8")
    plan = orjson.loads(process_script_json(script_text, project_type="audio_drama"))
    summary = {
        "scene_count": len(plan["scenes"]),
        "scene_titles": [s["structure"]["scene_title"] for s in plan["scenes"]],
        "first_scene_sfx": sorted({e["sfx_label"] for e in plan["scenes"][0]["structure"]["sfx_events"]}),
        "first_scene_speakers": plan["scenes"][0]["structure"]["speakers"],
    }
    golden = json.loads(_eva_golden_path().read_text(encoding="utf-8"))
    assert summary == golden


def test_trail_of_bells_summary_matches_golden_fixture():
    script_text = _trail_script_path().read_text(encoding="utf-8")
    plan = orjson.loads(process_script_json(script_text, project_type="audio_drama"))
    summary = {
        "scene_count": len(plan["scenes"]),
        "scene_titles": [s["structure"]["scene_title"] for s in plan["scenes"]],
        "first_scene_sfx": sorted({e["sfx_label"] for e in plan["scenes"][0]["structure"]["sfx_events"]}),
        "first_scene_action_kinds": [b["kind"] for b in plan["scenes"][0]["structure"].get("action_blocks", [])],
    }
    golden = json.loads(_trail_golden_path().read_text(encoding="utf-8"))
    assert summary == golden


@pytest.mark.slow
def test_cli_process_fountain_no_llm(tmp_path: Path):
    script_src = _eva_script_path()
    script_path = tmp_path / "episode.fountain"
    script_path.write_text(script_src.read_text(encoding="utf-8"), encoding="utf-8")
    out_dir = tmp_path / "out"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cli",
            "process",
            "--input",
            str(script_path),
            "--output",
            str(out_dir),
            "--project-type",
            "audio_drama",
            "--no-llm",
        ],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(Path(__file__).resolve().parent.parent),
    )

    assert result.returncode == 0, (
        f"CLI failed with code {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert (out_dir / "narrative_plan.json").is_file()
    assert (out_dir / "draft_timeline.json").is_file()
    warnings_path = out_dir / "script_warnings.json"
    assert warnings_path.is_file()
    warnings_payload = json.loads(warnings_path.read_text(encoding="utf-8"))
    assert "summary" in warnings_payload
    assert "diagnostics" in warnings_payload


@pytest.mark.slow
def test_cli_process_with_gita_update_writes_continuity(tmp_path: Path):
    script_src = _eva_script_path()
    script_path = tmp_path / "episode.fountain"
    script_path.write_text(script_src.read_text(encoding="utf-8"), encoding="utf-8")
    out_dir = tmp_path / "out"
    gita_path = tmp_path / "gita.json"
    gita_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "project_id": "demo",
                "series_title": "Demo",
                "characters": {},
                "locations": {},
                "sfx_motifs": {},
                "music_themes": {},
                "relationships": [],
                "continuity_notes": [],
                "episodes": [],
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cli",
            "process",
            "--input",
            str(script_path),
            "--output",
            str(out_dir),
            "--project-type",
            "audio_drama",
            "--no-llm",
            "--gita",
            str(gita_path),
            "--update-gita",
        ],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(Path(__file__).resolve().parent.parent),
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    updated = json.loads(gita_path.read_text(encoding="utf-8"))
    assert len(updated.get("episodes", [])) >= 1


@pytest.mark.slow
def test_engine2_scaffold_status_resolve_with_seeded_assets(tmp_path: Path):
    script_text = _eva_script_path().read_text(encoding="utf-8")
    plan = orjson.loads(process_script_json(script_text, project_type="audio_drama"))
    draft_bytes = compile_timeline_json(plan, project_type="audio_drama", narration_only=False)

    draft_path = tmp_path / "out" / "draft_timeline.json"
    out_dir = tmp_path / "out"
    library = tmp_path / "library"
    out_dir.mkdir(parents=True, exist_ok=True)
    library.mkdir(parents=True, exist_ok=True)
    draft_path.write_bytes(draft_bytes)

    repo_root = Path(__file__).resolve().parents[3]
    asset_engine_dir = repo_root / "asset_engine"
    env = dict(**os.environ)
    py_path = str(asset_engine_dir / "src")
    env["PYTHONPATH"] = f"{py_path};{env.get('PYTHONPATH', '')}" if env.get("PYTHONPATH") else py_path
    if py_path not in sys.path:
        sys.path.insert(0, py_path)
    from asset_engine.contracts.draft_models import DraftTimeline as AssetDraftTimeline
    from asset_engine.requirements import extract_requirements
    from asset_engine.utils.path_utils import make_asset_folder_name, make_voice_folder_name, resolve_asset_folder

    cmd_base = [sys.executable, "-m", "asset_engine.cli"]
    scaffold = subprocess.run(
        cmd_base + ["scaffold", "--draft", str(draft_path), "--library", str(library)],
        cwd=str(asset_engine_dir),
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
    )
    assert scaffold.returncode == 0, scaffold.stderr

    wav_targets = []
    for folder in library.rglob("*"):
        if folder.is_dir() and (folder / "DESCRIPTOR.txt").is_file():
            wav_targets.append(folder / "sample.wav")
        if folder.is_dir() and (folder / "SCRIPT.txt").is_file():
            wav_targets.append(folder / "voice.wav")
    for wav in wav_targets:
        _write_silence_wav(wav)

    # Also seed resolver-expected folders directly from extracted requirements.
    draft_obj = AssetDraftTimeline(**json.loads(draft_path.read_text(encoding="utf-8")))
    reqs = extract_requirements(draft_obj)
    for req in reqs:
        kind = str(req.asset_kind)
        if kind == "voice":
            scene_folder = make_voice_folder_name(req.scene_index, req.scene_name, req.track_id)
            folder = resolve_asset_folder(library, kind, f"{scene_folder}/clip_{req.clip_index:03d}")
            _write_silence_wav(folder / "voice.wav")
        else:
            folder = resolve_asset_folder(
                library,
                kind,
                make_asset_folder_name(req.scene_index, req.scene_name, req.descriptor),
            )
            _write_silence_wav(folder / "sample.wav")

    status = subprocess.run(
        cmd_base + ["status", "--draft", str(draft_path), "--library", str(library)],
        cwd=str(asset_engine_dir),
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
    )
    assert status.returncode == 0, f"{status.stdout}\n{status.stderr}"

    resolve = subprocess.run(
        cmd_base + ["run", "--draft", str(draft_path), "--library", str(library), "--out", str(out_dir)],
        cwd=str(asset_engine_dir),
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
    )
    assert resolve.returncode == 0, f"{resolve.stdout}\n{resolve.stderr}"
    assert (out_dir / "final_timeline.json").is_file()
