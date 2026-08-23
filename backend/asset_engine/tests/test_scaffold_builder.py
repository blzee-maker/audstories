from pathlib import Path

from asset_engine.contracts.requirements_models import AssetRequirement
from asset_engine.scaffold.builder import build_scaffold


def _voice_req() -> AssetRequirement:
    return AssetRequirement(
        requirement_id="scene_1:narrator:0",
        asset_kind="voice",
        scene_id="scene_1",
        scene_name="Abandoned House",
        scene_index=0,
        track_id="narrator",
        clip_index=0,
        descriptor="The room was silent.",
        tts_text="The room was silent.",
    )


def _music_req() -> AssetRequirement:
    return AssetRequirement(
        requirement_id="scene_1:music:0",
        asset_kind="music",
        scene_id="scene_1",
        scene_name="Abandoned House",
        scene_index=0,
        track_id="music",
        clip_index=0,
        descriptor="tension_low",
        mood="tension_low",
        energy_hint=0.35,
        loop=True,
    )


def test_build_scaffold_creates_folders_and_docs(tmp_path: Path):
    library_root = tmp_path / "assets"
    result = build_scaffold(
        requirements=[_voice_req(), _music_req()],
        library_root=library_root,
        project_name="Demo Story",
    )

    assert result.folders_created == 2
    assert (library_root / "voice").exists()
    assert (library_root / "music").exists()
    assert (library_root / "REQUIREMENTS.md").exists()

    script_files = list((library_root / "voice").rglob("SCRIPT.txt"))
    descriptor_files = list((library_root / "music").rglob("DESCRIPTOR.txt"))
    assert len(script_files) == 1
    assert len(descriptor_files) == 1


def test_build_scaffold_is_idempotent(tmp_path: Path):
    library_root = tmp_path / "assets"
    requirements = [_voice_req(), _music_req()]

    first = build_scaffold(
        requirements=requirements,
        library_root=library_root,
        project_name="Demo Story",
    )
    second = build_scaffold(
        requirements=requirements,
        library_root=library_root,
        project_name="Demo Story",
    )

    assert first.folders_created == 2
    assert second.folders_created == 0
    assert second.folders_unchanged == 2
