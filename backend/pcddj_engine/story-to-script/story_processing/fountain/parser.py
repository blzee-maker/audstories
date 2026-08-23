"""Deterministic parser for a practical Fountain subset."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Literal

from .ast import ActionBlock, CharacterCue, DialogueBlock, Scene, ScriptAST, ScriptDiagnostic

_TITLE_PAGE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 _-]*\s*:\s*.+$")
_SCENE_HEADING_RE = re.compile(r"^(?:INT\.|EXT\.|INT/EXT\.|INT\./EXT\.)", re.IGNORECASE)
_SCENE_MARKER_RE = re.compile(
    r"^(?:SCENE\s+(?:\d+|[IVXLCDM]+|ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN)|ACT\s+\d+|TEASER|TRAILER\s+BEGINS)$",
    re.IGNORECASE,
)
_CUSTOM_SLUG_RE = re.compile(r"^[A-Z0-9][A-Z0-9 '/&-]*$")
_CUE_LINE_RE = re.compile(r"^(?P<name>[A-Z0-9 .'\-]+?)(?:\s+\((?P<ext>[^)]+)\))?$")
_PAREN_RE = re.compile(r"^\([^)]+\)$")
_TRANSITION_RE = re.compile(r"^[A-Z ]+TO:$")
_TITLE_CARD_RE = re.compile(r"^TITLE\s+CARD\b", re.IGNORECASE)
_CENTERED_RE = re.compile(r"^>\s*(.*?)\s*<$")
_ACTION_PREFIX_RE = re.compile(r"^(SFX|AMBIENCE)\s*:\s*(.*)$", re.IGNORECASE)


def _strip_boneyards_and_notes(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"\[\[.*?\]\]", "", text, flags=re.DOTALL)
    return text


def _split_lines(text: str) -> list[str]:
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _parse_title_page(lines: list[str]) -> tuple[dict[str, str], int]:
    title_page: dict[str, str] = {}
    idx = 0
    while idx < len(lines):
        line = lines[idx].strip()
        if not line:
            idx += 1
            if title_page:
                return title_page, idx
            continue
        if not _TITLE_PAGE_RE.match(line):
            return title_page, idx
        key, value = line.split(":", 1)
        title_page[key.strip().lower().replace(" ", "_")] = value.strip()
        idx += 1
    return title_page, idx


def _is_scene_heading(line: str) -> bool:
    if not line:
        return False
    if line.startswith("."):
        return True
    if _SCENE_HEADING_RE.match(line):
        return True
    if _SCENE_MARKER_RE.match(line):
        return True
    if "/" in line and _CUSTOM_SLUG_RE.match(line):
        return True
    return False


def _is_unsupported_syntax(line: str) -> str | None:
    if line.startswith("#"):
        return "sections are unsupported in v1"
    if line.startswith("="):
        return "synopses are unsupported in v1"
    return None


def _normalize_scene_heading(line: str) -> str:
    if line.startswith("."):
        return line[1:].strip() or "Scene"
    return line.strip()


def _classify_action_line(line: str) -> tuple[
    Literal["action", "sfx", "ambience", "transition", "title_card"], str | None, str
]:
    """Classify special action directives and prefixed blocks."""
    centered = _CENTERED_RE.match(line)
    if centered:
        text = centered.group(1).strip()
        return "title_card", "centered", text

    m = _ACTION_PREFIX_RE.match(line)
    if m:
        marker = m.group(1).upper()
        body = (m.group(2) or "").strip()
        if marker == "SFX":
            return "sfx", marker, body
        return "ambience", marker, body

    if _TITLE_CARD_RE.match(line):
        return "title_card", "TITLE_CARD", line
    if _TRANSITION_RE.match(line) or line.upper().startswith("FADE TO "):
        return "transition", "TRANSITION", line
    return "action", None, line


def _consume_prefixed_block(lines: list[str], start_idx: int) -> tuple[str, int] | None:
    """Consume multiline SFX/AMBIENCE blocks."""
    first = lines[start_idx].strip()
    matched = _ACTION_PREFIX_RE.match(first.lstrip("!").strip())
    if not matched:
        return None
    body = (matched.group(2) or "").strip()
    parts: list[str] = [body] if body else []
    idx = start_idx + 1
    while idx < len(lines):
        nxt = lines[idx].strip()
        if not nxt:
            idx += 1
            break
        if _is_scene_heading(nxt):
            break
        if _parse_cue(nxt.rstrip("^").strip()) is not None:
            break
        if _ACTION_PREFIX_RE.match(nxt):
            break
        if _TITLE_CARD_RE.match(nxt) or _TRANSITION_RE.match(nxt):
            break
        parts.append(nxt)
        idx += 1
    return " ".join(parts).strip(), idx


def _parse_cue(line: str) -> CharacterCue | None:
    forced = False
    raw = line.strip()
    if raw.startswith("@"):
        forced = True
        raw = raw[1:].strip()

    if "/" in raw:
        return None

    m = _CUE_LINE_RE.match(raw)
    if not m:
        return None

    name = m.group("name").strip()
    if len(name.split()) > 5:
        return None
    if name.endswith(":"):
        return None

    ext_raw = (m.group("ext") or "").strip()
    extensions = tuple(ext_raw.split()) if ext_raw else ()
    return CharacterCue(name=name, extensions=extensions, forced=forced)


def _iter_nonempty_from(lines: list[str], start: int) -> Iterable[tuple[int, str]]:
    for i in range(start, len(lines)):
        text = lines[i].strip()
        if text:
            yield i, text


def _next_nonempty(lines: list[str], start: int) -> tuple[int, str] | None:
    for i in range(start, len(lines)):
        text = lines[i].strip()
        if text:
            return i, text
    return None


def _ends_dialogue_block(line: str) -> bool:
    """Hard boundaries that always terminate a dialogue block."""
    if _is_scene_heading(line):
        return True
    if _parse_cue(line.rstrip("^").strip()) is not None:
        return True
    if line.startswith("!"):
        return True
    if _ACTION_PREFIX_RE.match(line):
        return True
    if _TITLE_CARD_RE.match(line) or _TRANSITION_RE.match(line):
        return True
    return False


def _looks_like_dialogue_continuation(line: str) -> bool:
    """Does *line*, seen across a blank line, continue the current dialogue?

    In Fountain a blank line ends dialogue. The case worth spanning is the
    parenthetical-beat convention, where "(then)" / "(beat)" / "(silence)"
    separated by blank lines punctuates one character's speech.

    This used to default to True for anything that was not a hard boundary,
    which swallowed ordinary stage directions into the preceding dialogue: the
    SFX cues inside them were never extracted, and the TTS spoke the stage
    direction aloud as if it were a spoken line. Only a parenthetical continues
    a block on its own; prose resumes a block only when a parenthetical
    interrupted it, which the caller tracks.
    """
    if _ends_dialogue_block(line):
        return False
    return bool(_PAREN_RE.match(line))


def parse_fountain(text: str) -> ScriptAST:
    """Parse a Fountain subset script into an AST."""
    cleaned = _strip_boneyards_and_notes(text)
    lines = _split_lines(cleaned)
    title_page, idx = _parse_title_page(lines)

    scenes: list[Scene] = []
    warnings: list[str] = []
    diagnostics: list[ScriptDiagnostic] = []

    def _warn(line_no: int, code: str, message: str, *, column: int = 1) -> None:
        diagnostics.append(
            ScriptDiagnostic(
                line=line_no,
                column=column,
                code=code,
                severity="warning",
                message=message,
            )
        )
        warnings.append(f"line {line_no}: {message}")

    current_heading = "Scene 1"
    current_blocks: list[DialogueBlock | ActionBlock] = []

    def flush_scene() -> None:
        if current_blocks or current_heading:
            scenes.append(Scene(heading=current_heading, blocks=tuple(current_blocks)))

    while idx < len(lines):
        raw = lines[idx]
        line = raw.strip()
        idx += 1

        if not line:
            continue

        unsupported = _is_unsupported_syntax(line)
        if unsupported:
            _warn(idx, "unsupported_syntax", unsupported)
            continue

        if _is_scene_heading(line):
            if current_blocks:
                flush_scene()
                current_blocks = []
            current_heading = _normalize_scene_heading(line)
            continue

        cue = _parse_cue(line.rstrip("^").strip())
        if line.endswith("^"):
            _warn(
                idx,
                "dual_dialogue_unsupported",
                "dual dialogue unsupported, treating as normal cue",
            )
        if cue is not None:
            next_items = list(_iter_nonempty_from(lines, idx))
            if not next_items:
                _warn(idx, "cue_without_dialogue", "cue without dialogue")
                continue

            parenthetical: str | None = None
            dialogue_lines: list[str] = []
            inner_idx = idx
            # True when the last thing consumed was a parenthetical beat such as
            # "(beat)" / "(then)" / "(silence)". Speech resumes after one of those
            # across a blank line; plain prose after a blank line with no
            # intervening parenthetical is a stage direction, not more dialogue.
            after_parenthetical = False
            while inner_idx < len(lines):
                candidate = lines[inner_idx].strip()
                if not candidate:
                    peeked = _next_nonempty(lines, inner_idx + 1)
                    if peeked is None:
                        inner_idx += 1
                        break
                    _, nxt = peeked
                    if _looks_like_dialogue_continuation(nxt) or (
                        after_parenthetical and not _ends_dialogue_block(nxt)
                    ):
                        inner_idx += 1
                        continue
                    inner_idx += 1
                    break
                if _is_scene_heading(candidate):
                    break
                if _parse_cue(candidate) is not None and dialogue_lines:
                    break
                if _PAREN_RE.match(candidate) and not dialogue_lines and parenthetical is None:
                    parenthetical = candidate.strip("() ").strip() or None
                    after_parenthetical = True
                elif _PAREN_RE.match(candidate):
                    # Mid-dialogue parentheticals (e.g. "(beat)", "(silence)") are
                    # stage directions and should not become spoken text.
                    after_parenthetical = True
                elif candidate.startswith("!"):
                    consumed = _consume_prefixed_block(lines, inner_idx)
                    if consumed:
                        merged, new_idx = consumed
                        kind, marker, _ = _classify_action_line(candidate[1:].strip())
                        current_blocks.append(
                            ActionBlock(
                                text=merged,
                                forced=True,
                                kind=kind,
                                marker=marker,
                            )
                        )
                        inner_idx = new_idx
                        continue
                    kind, marker, body = _classify_action_line(candidate[1:].strip())
                    current_blocks.append(
                        ActionBlock(
                            text=body,
                            forced=True,
                            kind=kind,
                            marker=marker,
                        )
                    )
                else:
                    dialogue_lines.append(candidate)
                    after_parenthetical = False
                inner_idx += 1

            if dialogue_lines:
                current_blocks.append(
                    DialogueBlock(
                        cue=cue,
                        lines=tuple(dialogue_lines),
                        parenthetical=parenthetical,
                    ),
                )
            else:
                _warn(
                    idx,
                    "cue_no_dialogue_lines",
                    "cue parsed but no dialogue lines found",
                )
            idx = inner_idx
            continue

        if line.startswith("!"):
            consumed = _consume_prefixed_block(lines, idx - 1)
            if consumed:
                merged, new_idx = consumed
                kind, marker, _ = _classify_action_line(line[1:].strip())
                current_blocks.append(
                    ActionBlock(
                        text=merged,
                        forced=True,
                        kind=kind,
                        marker=marker,
                    )
                )
                idx = new_idx
                continue
            kind, marker, body = _classify_action_line(line[1:].strip())
            current_blocks.append(
                ActionBlock(
                    text=body,
                    forced=True,
                    kind=kind,  # type: ignore[arg-type]
                    marker=marker,
                )
            )
            continue

        consumed = _consume_prefixed_block(lines, idx - 1)
        if consumed:
            merged, new_idx = consumed
            kind, marker, _ = _classify_action_line(line)
            current_blocks.append(
                ActionBlock(
                    text=merged,
                    forced=False,
                    kind=kind,
                    marker=marker,
                )
            )
            idx = new_idx
            continue

        kind, marker, body = _classify_action_line(line)
        current_blocks.append(
            ActionBlock(
                text=body,
                forced=False,
                kind=kind,  # type: ignore[arg-type]
                marker=marker,
            )
        )

    flush_scene()
    if not scenes:
        scenes = [Scene(heading="Scene 1", blocks=tuple())]

    return ScriptAST(
        scenes=tuple(scenes),
        title_page=title_page,
        warnings=tuple(warnings),
        diagnostics=tuple(diagnostics),
    )
