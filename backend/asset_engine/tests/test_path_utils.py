from pathlib import Path

from asset_engine.utils.path_utils import (
    is_audio_file,
    make_asset_folder_name,
    make_voice_folder_name,
    resolve_asset_folder,
    slugify,
)


def test_slugify_basic():
    assert slugify("Dark Interior") == "dark_interior"


def test_slugify_unsafe_chars():
    assert slugify("scene/one:two") == "sceneonetwo"


def test_slugify_multi_underscore():
    assert slugify("tension  low") == "tension_low"


def test_slugify_truncation():
    long_value = "a" * 100
    assert len(slugify(long_value)) <= 80


def test_folder_name_format():
    name = make_asset_folder_name(0, "The Abandoned House", "tension_low")
    assert name == "scene_000_the_abandoned_house_tension_low"


def test_folder_name_windows_safe():
    name = make_asset_folder_name(1, "Scene: Two", "dark/exterior")
    assert ":" not in name
    assert "/" not in name


def test_make_voice_folder_name():
    name = make_voice_folder_name(0, "Abandoned House", "character_ayaan")
    assert name == "scene_000_abandoned_house_character_ayaan"


def test_resolve_asset_folder():
    path = resolve_asset_folder(Path("assets"), "music", "scene_000_x_tension_low")
    assert path == Path("assets/music/scene_000_x_tension_low")


def test_is_audio_file():
    assert is_audio_file(Path("test.wav"))
    assert is_audio_file(Path("test.MP3"))
    assert not is_audio_file(Path("notes.txt"))
