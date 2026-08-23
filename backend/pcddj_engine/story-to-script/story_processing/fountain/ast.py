"""AST models for the Fountain subset parser."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True, slots=True)
class CharacterCue:
    """Character cue metadata (name + cue extensions)."""

    name: str
    extensions: tuple[str, ...] = ()
    forced: bool = False


@dataclass(frozen=True, slots=True)
class DialogueBlock:
    """Dialogue block spoken by one character cue."""

    cue: CharacterCue
    lines: tuple[str, ...]
    parenthetical: str | None = None


@dataclass(frozen=True, slots=True)
class ActionBlock:
    """Non-dialogue action line(s)."""

    text: str
    forced: bool = False
    kind: Literal["action", "sfx", "ambience", "transition", "title_card"] = "action"
    marker: str | None = None


@dataclass(frozen=True, slots=True)
class Scene:
    """One parsed scene with heading and mixed blocks."""

    heading: str
    blocks: tuple[DialogueBlock | ActionBlock, ...]


@dataclass(frozen=True, slots=True)
class ScriptAST:
    """Top-level parsed script."""

    scenes: tuple[Scene, ...]
    title_page: dict[str, str] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    diagnostics: tuple["ScriptDiagnostic", ...] = ()


@dataclass(frozen=True, slots=True)
class ScriptDiagnostic:
    """Structured parser diagnostic."""

    line: int
    column: int
    code: str
    severity: str
    message: str
