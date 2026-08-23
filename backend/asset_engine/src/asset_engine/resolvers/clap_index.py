"""Optional CLAP index adapter.

This v1 module keeps CLAP fully optional. If model dependencies are not installed,
runtime matching returns ``None`` and resolvers fall back to deterministic folder-first logic.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re


_TOKEN_RE = re.compile(r"[^a-z0-9]+")


def _tokenize(text: str) -> set[str]:
    return {tok for tok in _TOKEN_RE.split(text.lower()) if tok}


@dataclass(frozen=True)
class ClapCandidate:
    file_path: Path
    score: float
    note: str


@dataclass(frozen=True)
class ClapIndex:
    kind: str
    metadata_path: Path
    entries: tuple[dict, ...]

    @classmethod
    def load(cls, metadata_path: Path, kind: str) -> "ClapIndex":
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        entries = payload.get("entries")
        if not isinstance(entries, list):
            raise ValueError(f"invalid CLAP metadata at {metadata_path}: missing entries list")
        return cls(kind=kind, metadata_path=metadata_path, entries=tuple(entries))

    def query(self, query_text: str, *, top_k: int = 5) -> list[ClapCandidate]:
        q = _tokenize(query_text)
        if not q:
            return []

        scored: list[ClapCandidate] = []
        for item in self.entries:
            path = Path(str(item.get("path", "")))
            tags = str(item.get("tags", ""))
            tokens = _tokenize(f"{path.stem} {tags}")
            if not tokens:
                continue
            overlap = len(q.intersection(tokens))
            if overlap == 0:
                continue
            score = overlap / max(len(q), 1)
            scored.append(ClapCandidate(file_path=path, score=score, note=f"token_overlap={overlap}"))

        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]


def build_index(kind: str, audio_library_root: Path, output_path: Path) -> Path:
    """Build a lightweight metadata index.

    v1 intentionally stores token metadata only; true embedding-backed CLAP can replace
    this format later while preserving CLI contracts.
    """
    if kind not in {"sfx", "ambience"}:
        raise ValueError("kind must be 'sfx' or 'ambience'")

    src_dir = audio_library_root / kind
    if not src_dir.exists():
        raise FileNotFoundError(f"audio library directory not found: {src_dir}")

    entries: list[dict[str, str]] = []
    for file_path in sorted(src_dir.rglob("*")):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in {".wav", ".mp3", ".ogg", ".flac", ".m4a"}:
            continue
        rel = file_path.relative_to(audio_library_root).as_posix()
        entries.append({"path": rel, "tags": file_path.stem.replace("_", " ")})

    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "kind": kind,
        "version": "v1-token",
        "entries": entries,
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output_path
