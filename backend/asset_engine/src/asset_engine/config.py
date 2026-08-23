"""Asset engine runtime configuration helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ResolverConfig:
    audio_library_root: Path | None = None
    music_catalog_path: Path | None = None
    use_clap: bool = False
    use_freesound: bool = False
    require_voice: bool = False
    score_threshold: float = 0.45

    @classmethod
    def from_paths(
        cls,
        *,
        audio_library_root: str | None,
        music_catalog_path: str | None,
        use_clap: bool,
        use_freesound: bool,
        require_voice: bool,
        score_threshold: float,
    ) -> "ResolverConfig":
        return cls(
            audio_library_root=Path(audio_library_root) if audio_library_root else None,
            music_catalog_path=Path(music_catalog_path) if music_catalog_path else None,
            use_clap=bool(use_clap),
            use_freesound=bool(use_freesound),
            require_voice=bool(require_voice),
            score_threshold=float(score_threshold),
        )
