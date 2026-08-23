"""Tests for optional Audio Director enrichment."""

from __future__ import annotations

import json

from story_processing.fountain.audio_director import (
    merge_director_enrichment,
    run_audio_director,
)
from story_processing.fountain.parser import parse_fountain
from story_processing.fountain.to_plan import script_to_narrative_plan_dict


class _FakeClient:
    def __init__(self, payload: str) -> None:
        self.payload = payload

    def complete(self, prompt: str, *, system: str = "") -> str:  # noqa: ARG002
        return self.payload


def test_director_merge_enriches_scene_and_dialogue():
    script = """
INT. SHRINE
MANAS
We need to move.
""".strip()
    ast = parse_fountain(script)
    plan = script_to_narrative_plan_dict(ast, project_type="audio_drama")
    response = json.dumps(
        {
            "scene_enrichment": [
                {
                    "scene_index": 0,
                    "primary_emotion": "anxiety",
                    "energy_level": 8,
                    "emotion_intensity": 8,
                    "music_strategy": "low drones rising in pulses",
                    "ambience_layers": ["stone_room", "distant_bells"],
                    "sfx_additions": [
                        {
                            "label": "bell_strike_close",
                            "intensity": "strong",
                            "semantic_role": "impact",
                            "timing": "short",
                        }
                    ],
                    "delivery_by_speaker": {"MANAS": "urgent"},
                }
            ],
            "global_notes": [],
        }
    )
    payload = run_audio_director(ast=ast, llm_client=_FakeClient(response))
    merged = merge_director_enrichment(plan, payload)
    scene = merged["scenes"][0]
    assert scene["interpretation"]["primary_emotion"] == "anxiety"
    assert scene["interpretation"]["music_strategy"]
    assert scene["structure"]["dialogue_turns"][0]["delivery_hint"] == "urgent"
    assert any(s["sfx_label"] == "bell_strike_close" for s in scene["structure"]["sfx_events"])


def test_director_bad_payload_can_be_ignored():
    script = "INT. ROOM\nEVA\nHello."
    ast = parse_fountain(script)
    plan = script_to_narrative_plan_dict(ast, project_type="audio_drama")
    original_energy = plan["scenes"][0]["interpretation"]["energy_level"]
    merged = merge_director_enrichment(plan, {"scene_enrichment": ["bad"]})
    assert merged["scenes"][0]["interpretation"]["energy_level"] == original_energy
