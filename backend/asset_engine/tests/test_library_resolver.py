from pathlib import Path
import struct
import wave

from asset_engine.contracts.requirements_models import AssetRequirement, ResolutionStatus
from asset_engine.resolvers.library_resolver import resolve_from_library
from asset_engine.utils.path_utils import make_asset_folder_name, make_voice_folder_name


def _write_wav(path: Path, duration: float = 0.25, sample_rate: int = 22050) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = int(duration * sample_rate)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for _ in range(frames):
            wav.writeframesraw(struct.pack("<h", 0))


def _voice_req() -> AssetRequirement:
    return AssetRequirement(
        requirement_id="scene_1:narrator:0",
        asset_kind="voice",
        scene_id="scene_1",
        scene_name="Room",
        scene_index=0,
        track_id="narrator",
        clip_index=0,
        descriptor="hello world",
        tts_text="hello world",
        estimated_duration_seconds=1.0,
    )


def _music_req() -> AssetRequirement:
    return AssetRequirement(
        requirement_id="scene_1:music:0",
        asset_kind="music",
        scene_id="scene_1",
        scene_name="Room",
        scene_index=0,
        track_id="music",
        clip_index=0,
        descriptor="tension_low",
    )


def test_resolve_exact_match_single_file(tmp_path: Path):
    req = _music_req()
    folder = make_asset_folder_name(req.scene_index, req.scene_name, req.descriptor)
    _write_wav(tmp_path / "music" / folder / f"{folder}.wav")

    result = resolve_from_library([req], tmp_path)
    assert len(result.resolved) == 1
    assert req.resolution_status == ResolutionStatus.RESOLVED
    assert req.resolved_file is not None
    assert req.metadata is not None and req.metadata["confidence"] == 1.0


def test_resolve_multiple_files_uses_alphabetical(tmp_path: Path):
    req = _music_req()
    folder = make_asset_folder_name(req.scene_index, req.scene_name, req.descriptor)
    _write_wav(tmp_path / "music" / folder / "b.wav")
    _write_wav(tmp_path / "music" / folder / "a.wav")

    resolve_from_library([req], tmp_path)
    assert req.resolved_file is not None
    assert req.resolved_file.endswith("a.wav")
    assert req.metadata is not None and req.metadata["confidence"] == 0.8


def test_missing_voice_becomes_placeholder(tmp_path: Path):
    req = _voice_req()
    # Folder exists but no audio files.
    voice_folder = make_voice_folder_name(req.scene_index, req.scene_name, req.track_id)
    (tmp_path / "voice" / voice_folder / "clip_000").mkdir(parents=True)

    result = resolve_from_library([req], tmp_path)
    assert len(result.placeholders) == 1
    assert req.resolution_status == ResolutionStatus.PLACEHOLDER
    assert req.resolved_file is None


def test_missing_music_is_skipped(tmp_path: Path):
    req = _music_req()

    result = resolve_from_library([req], tmp_path)
    assert len(result.skipped) == 1
    assert len(result.missing) == 1
    assert req.resolution_status == ResolutionStatus.SKIPPED

def test_music_catalog_resolves_when_scaffold_missing(tmp_path: Path):
    req = _music_req()
    audio_root = tmp_path / "audio_library"
    music_file = audio_root / "music" / "underscore" / "tense" / "tense.wav"
    _write_wav(music_file)

    catalog_path = tmp_path / "music_catalog.json"
    catalog_path.write_text(
        '{"tracks": [{"path": "music/underscore/tense/tense.wav", "role": "underscore", "emotion": ["tension"], "energy": 0.5, "loopable": true, "duration_s": 30}]}',
        encoding="utf-8",
    )

    from asset_engine.resolvers.library_resolver import ResolveOptions

    options = ResolveOptions(
        audio_library_root=audio_root,
        music_catalog_path=catalog_path,
        score_threshold=0.1,
    )
    result = resolve_from_library([req], tmp_path / "project_assets", options=options)
    assert len(result.resolved) == 1
    assert req.resolved_file is not None and req.resolved_file.endswith("tense.wav")
    assert req.metadata is not None and req.metadata.get("source") == "music_catalog"


def test_clap_index_resolves_sfx_when_scaffold_missing(tmp_path: Path):
    req = AssetRequirement(
        requirement_id="scene_1:sfx:0",
        asset_kind="sfx",
        scene_id="scene_1",
        scene_name="Room",
        scene_index=0,
        track_id="sfx",
        clip_index=0,
        descriptor="door creak",
        sfx_hint="door creak",
        semantic_role="interaction",
    )

    audio_root = tmp_path / "audio_library"
    sfx_file = audio_root / "sfx" / "door_creak.wav"
    _write_wav(sfx_file)
    index_dir = audio_root / "index"
    index_dir.mkdir(parents=True, exist_ok=True)
    (index_dir / "sfx_index.json").write_text(
        '{"kind":"sfx","version":"v1-token","entries":[{"path":"sfx/door_creak.wav","tags":"door creak old"}]}',
        encoding="utf-8",
    )

    from asset_engine.resolvers.library_resolver import ResolveOptions

    options = ResolveOptions(audio_library_root=audio_root, use_clap=True, score_threshold=0.1)
    result = resolve_from_library([req], tmp_path / "project_assets", options=options)
    assert len(result.resolved) == 1
    assert req.metadata is not None and req.metadata.get("source") == "clap_index"

def test_freesound_flag_without_api_key_is_nonfatal(tmp_path: Path):
    req = AssetRequirement(
        requirement_id="scene_1:sfx:0",
        asset_kind="sfx",
        scene_id="scene_1",
        scene_name="Room",
        scene_index=0,
        track_id="sfx",
        clip_index=0,
        descriptor="glass break",
        sfx_hint="glass break",
    )
    from asset_engine.resolvers.library_resolver import ResolveOptions

    result = resolve_from_library(
        [req],
        tmp_path / "project_assets",
        options=ResolveOptions(use_freesound=True),
    )
    assert len(result.missing) == 1
