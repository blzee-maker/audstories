from story_processing.fountain.parser import parse_fountain
from story_processing.fountain.to_plan import script_to_narrative_plan_dict


def _turns(script: str):
    plan = script_to_narrative_plan_dict(parse_fountain(script), project_type="audio_drama")
    return plan["scenes"][0]["structure"]["dialogue_turns"]


def test_vo_line_is_tagged_internal():
    script = """
INT. ROOM - NIGHT

EVA (V.O.)
I remember this place.
""".strip()
    turns = _turns(script)
    assert turns[0]["dramatic_function"] in {"scene_entry", "scene_close", "internal"}


def test_question_followed_by_action_is_question_unanswered():
    script = """
INT. ROOM - NIGHT

EVA
Who is there?

[SFX: DOOR CREAKS]

MARCUS
Stay back.
""".strip()
    turns = _turns(script)
    assert turns[0]["dramatic_function"] == "question_unanswered"


def test_response_to_sfx_is_tagged():
    script = """
INT. ROOM - NIGHT

SFX: GLASS BREAKS

EVA
What was that!

MARCUS
Keep moving.
""".strip()
    turns = _turns(script)
    assert turns[0]["dramatic_function"] == "response_to_sfx"
