"""Tests for Fountain subset parser."""

from story_processing.fountain.parser import parse_fountain


def test_scene_headings_and_dialogue_blocks():
    script = """
SCENE ONE
NOWHERE/EVERYWHERE
The sounds of an underwater world.

EVA (V.O.)
They say that in the dark, the eyes begin to see.

INT. EVA GRAFF'S QUARTERS
EVA
Jesus...
""".strip()
    ast = parse_fountain(script)

    assert len(ast.scenes) == 2
    assert ast.scenes[0].heading == "NOWHERE/EVERYWHERE"
    assert ast.scenes[1].heading == "INT. EVA GRAFF'S QUARTERS"

    first_dialogue = next(b for b in ast.scenes[0].blocks if hasattr(b, "cue"))
    assert first_dialogue.cue.name == "EVA"
    assert "V.O." in first_dialogue.cue.extensions


def test_parenthetical_attaches_to_following_dialogue():
    script = """
INT. TEST ROOM
EVA
(then)
We should keep moving.
""".strip()
    ast = parse_fountain(script)
    block = ast.scenes[0].blocks[0]
    assert hasattr(block, "parenthetical")
    assert block.parenthetical == "then"
    assert "We should keep moving." in block.lines


def test_dialogue_continues_across_blank_lines_and_beats():
    script = """
INT. STREET - NIGHT
PRIYA
(V.O., quiet, to herself)
Twenty minutes.

(beat)

Still nothing.
""".strip()
    ast = parse_fountain(script)
    block = ast.scenes[0].blocks[0]
    assert hasattr(block, "lines")
    assert block.parenthetical == "V.O., quiet, to herself"
    assert "Twenty minutes." in block.lines
    assert "Still nothing." in block.lines
    assert "(beat)" not in block.lines


def test_mid_dialogue_parenthetical_is_not_spoken_text():
    script = """
INT. TEST ROOM
PRIYA
That's why I'm calling.

(silence)

He asked me to.
""".strip()
    ast = parse_fountain(script)
    block = ast.scenes[0].blocks[0]
    assert block.lines == ("That's why I'm calling.", "He asked me to.")


def test_notes_and_boneyards_are_removed():
    script = """
Title: Example
Author: Someone

INT. LAB
/* this should be removed */
[[remove this note]]
EVA
We're late.
""".strip()
    ast = parse_fountain(script)
    assert ast.title_page["title"] == "Example"
    assert len(ast.scenes) == 1
    block = ast.scenes[0].blocks[0]
    assert "We're late." in block.lines


def test_forced_elements_and_action_blocks():
    script = """
.INT FORCED HALLWAY
!Door slams hard.
@EVA
Run!
""".strip()
    ast = parse_fountain(script)
    assert ast.scenes[0].heading == "INT FORCED HALLWAY"
    action = ast.scenes[0].blocks[0]
    assert action.forced is True
    dialogue = ast.scenes[0].blocks[1]
    assert dialogue.cue.forced is True


def test_unsupported_syntax_emits_warnings():
    script = """
INT. HALLWAY
CUT TO:
# Section
= Synopsis
EVA^
Hi.
""".strip()
    ast = parse_fountain(script)
    joined = " | ".join(ast.warnings).lower()
    assert "unsupported" in joined
    assert "dual dialogue" in joined
    assert len(ast.diagnostics) >= 2
    first = ast.diagnostics[0]
    assert first.line >= 1
    assert first.column == 1
    assert first.severity == "warning"
    assert first.code


def test_malformed_script_is_recoverable():
    script = """
INT. ????
@EVA

!Door slams
EVA (V.O.)

EXT. STREET
Rushing traffic and footsteps.
""".strip()
    ast = parse_fountain(script)
    assert len(ast.scenes) >= 1
    assert isinstance(ast.warnings, tuple)
    assert len(ast.diagnostics) >= 1


def test_advanced_markers_and_directives_are_structured():
    script = """
TRAILER BEGINS
SFX: Temple bells begin, distant.
  Single strike, then silence.
TITLE CARD - AUDIO ONLY:
>THE TRAIL OF BELLS<
CUT TO:
INT. SHRINE CHAMBER - NIGHT
MANAS (O.S.)
Did you hear that?
""".strip()
    ast = parse_fountain(script)
    assert ast.scenes[0].heading == "TRAILER BEGINS"
    action_kinds = [getattr(b, "kind", "") for b in ast.scenes[0].blocks]
    assert "sfx" in action_kinds
    assert "title_card" in action_kinds
    assert "transition" in action_kinds
    assert all(d.code != "cue_no_dialogue_lines" for d in ast.diagnostics)
