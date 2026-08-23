"""Path and filename helpers for deterministic cross-platform folders."""

from __future__ import annotations

from pathlib import Path
import re

_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_MULTI_UNDERSCORE = re.compile(r"_+")
_AUDIO_EXTS = {".wav", ".mp3", ".flac", ".aiff", ".ogg", ".m4a"}
MAX_FOLDER_NAME_LENGTH = 80


def slugify(text: str) -> str:
    """Convert arbitrary text into a filesystem-safe slug."""
    value = text.lower().replace(" ", "_").replace("-", "_")
    value = _UNSAFE_CHARS.sub("", value)
    value = _MULTI_UNDERSCORE.sub("_", value)
    value = value.strip("_")
    return value[:MAX_FOLDER_NAME_LENGTH] or "untitled"


def make_asset_folder_name(scene_index: int, scene_name: str, descriptor: str) -> str:
    """Build deterministic folder name for non-voice assets."""
    scene_slug = slugify(scene_name)
    descriptor_slug = slugify(descriptor)
    return f"scene_{scene_index:03d}_{scene_slug}_{descriptor_slug}"


def make_voice_folder_name(scene_index: int, scene_name: str, track_id: str) -> str:
    """Build deterministic folder name for voice assets."""
    scene_slug = slugify(scene_name)
    track_slug = slugify(track_id)
    return f"scene_{scene_index:03d}_{scene_slug}_{track_slug}"


def resolve_asset_folder(assets_root: Path, track_type: str, folder_name: str) -> Path:
    """Return full path for an asset folder."""
    return assets_root / track_type / folder_name


def is_audio_file(path: Path) -> bool:
    """True if file path looks like supported audio media."""
    return path.suffix.lower() in _AUDIO_EXTS
