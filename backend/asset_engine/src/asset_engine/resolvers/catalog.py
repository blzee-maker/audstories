"""Catalog indexing and deterministic asset matching."""

from __future__ import annotations

from pathlib import Path
import re

from asset_engine.contracts.requirements_models import AssetKind

_AUDIO_EXTS = {".wav", ".mp3", ".ogg", ".flac", ".m4a"}


def _tokenize(value: str) -> set[str]:
    return set(t for t in re.split(r"[^a-z0-9]+", value.lower()) if t)


class AssetCatalog:
    """Index local library paths by asset kind."""

    def __init__(self, library_root: Path | None):
        self.library_root = library_root
        self._by_kind: dict[AssetKind, list[Path]] = {
            "voice": [],
            "music": [],
            "ambience": [],
            "sfx": [],
        }
        if library_root and library_root.exists():
            self._index_library()

    def _index_library(self) -> None:
        assert self.library_root is not None
        for file_path in self.library_root.rglob("*"):
            if not file_path.is_file() or file_path.suffix.lower() not in _AUDIO_EXTS:
                continue
            kind = self._infer_kind(file_path)
            self._by_kind[kind].append(file_path)
        for kind in self._by_kind:
            self._by_kind[kind].sort(key=lambda p: str(p).lower())

    @staticmethod
    def _infer_kind(path: Path) -> AssetKind:
        parts = {p.lower() for p in path.parts}
        if "voice" in parts or "dialogue" in parts or "tts" in parts:
            return "voice"
        if "ambience" in parts or "ambient" in parts:
            return "ambience"
        if "sfx" in parts or "fx" in parts:
            return "sfx"
        return "music"

    def find_best(self, kind: AssetKind, descriptor: str) -> Path | None:
        candidates = self._by_kind[kind]
        if not candidates:
            return None

        desc_tokens = _tokenize(descriptor)
        scored: list[tuple[int, str, Path]] = []
        for candidate in candidates:
            stem_tokens = _tokenize(candidate.stem)
            score = len(desc_tokens.intersection(stem_tokens))
            scored.append((score, str(candidate).lower(), candidate))

        scored.sort(key=lambda item: (-item[0], item[1]))
        best_score, _, best_path = scored[0]
        if best_score == 0:
            return None
        return best_path

