"""Optional LLM enrichment pass for Fountain-derived narrative plans."""

from __future__ import annotations

import json
from typing import Any

from story_processing.ai.llm_client import call_with_backoff

from .ast import ActionBlock, DialogueBlock, ScriptAST

_SYSTEM = """You are an audio drama director assistant.
Return strict JSON only. Do not include markdown fences.
Prioritize practical production guidance for music, ambience, SFX, and delivery.
"""


def _scene_payload(ast: ScriptAST) -> list[dict[str, Any]]:
    scenes: list[dict[str, Any]] = []
    for idx, scene in enumerate(ast.scenes):
        dialogue: list[dict[str, str]] = []
        actions: list[dict[str, str]] = []
        for block in scene.blocks:
            if isinstance(block, DialogueBlock):
                text = " ".join(x.strip() for x in block.lines if x.strip()).strip()
                if text:
                    dialogue.append(
                        {
                            "speaker": block.cue.name,
                            "text": text,
                            "parenthetical": block.parenthetical or "",
                        }
                    )
            elif isinstance(block, ActionBlock):
                if block.text.strip():
                    actions.append(
                        {
                            "kind": block.kind,
                            "text": block.text.strip(),
                            "marker": block.marker or "",
                        }
                    )
        scenes.append(
            {
                "index": idx,
                "heading": scene.heading,
                "dialogue": dialogue,
                "actions": actions,
            }
        )
    return scenes


def _prompt(ast: ScriptAST) -> str:
    payload = {"scenes": _scene_payload(ast)}
    return (
        "Enrich these scenes with production-focused guidance.\n"
        "Output JSON with this shape:\n"
        "{"
        '"scene_enrichment":[{"scene_index":0,"primary_emotion":"...","energy_level":1-10,'
        '"emotion_intensity":1-10,"music_strategy":"...","ambience_layers":["..."],'
        '"sfx_additions":[{"label":"...","intensity":"subtle|moderate|strong|dramatic","semantic_role":"impact|movement|ambience|interaction|texture","timing":"instant|short|sustained"}],'
        '"delivery_by_speaker":{"SPEAKER":"hint"},"voice_treatment_by_speaker":{"SPEAKER":"hint"}}],'
        '"global_notes":["..."]}\n'
        "Use concise strings and avoid inventing named IP/music titles.\n"
        f"{json.dumps(payload, ensure_ascii=True)}"
    )


def merge_director_enrichment(
    plan: dict[str, Any],
    director_payload: dict[str, Any],
) -> dict[str, Any]:
    """Merge director result into narrative plan safely."""
    scenes = plan.get("scenes")
    if not isinstance(scenes, list):
        return plan
    by_index: dict[int, dict[str, Any]] = {}
    for item in director_payload.get("scene_enrichment", []):
        if not isinstance(item, dict):
            continue
        idx = item.get("scene_index")
        if isinstance(idx, int):
            by_index[idx] = item

    for idx, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            continue
        enrich = by_index.get(idx)
        if not enrich:
            continue
        interpretation = scene.get("interpretation")
        structure = scene.get("structure")
        if not isinstance(interpretation, dict) or not isinstance(structure, dict):
            continue

        for key in ("primary_emotion", "energy_level", "emotion_intensity"):
            if key in enrich:
                interpretation[key] = enrich[key]
        if isinstance(enrich.get("music_strategy"), str):
            interpretation["music_strategy"] = enrich["music_strategy"]

        layers = enrich.get("ambience_layers")
        if isinstance(layers, list) and layers:
            cue = structure.get("ambience_cue")
            if not isinstance(cue, dict):
                cue = {
                    "primary_atmosphere": str(layers[0]),
                    "atmosphere_description": "",
                    "intensity": "moderate",
                    "evolves": False,
                }
            cue["atmosphere_description"] = ", ".join(str(x) for x in layers if str(x).strip())
            structure["ambience_cue"] = cue

        add_sfx = enrich.get("sfx_additions")
        if isinstance(add_sfx, list):
            sfx_events = structure.get("sfx_events")
            if not isinstance(sfx_events, list):
                sfx_events = []
                structure["sfx_events"] = sfx_events
            order_hint = len(sfx_events)
            for item in add_sfx:
                if not isinstance(item, dict):
                    continue
                label = str(item.get("label", "")).strip()
                if not label:
                    continue
                sfx_events.append(
                    {
                        "source_text": "audio_director",
                        "sfx_label": label[:48],
                        "sfx_description": "",
                        "intensity": str(item.get("intensity", "moderate")),
                        "semantic_role": str(item.get("semantic_role", "interaction")),
                        "timing": str(item.get("timing", "short")),
                        "order_hint": order_hint,
                    }
                )
                order_hint += 1

        delivery = enrich.get("delivery_by_speaker")
        if isinstance(delivery, dict):
            for turn in structure.get("dialogue_turns", []):
                if not isinstance(turn, dict):
                    continue
                speaker = str(turn.get("speaker", "")).strip()
                if speaker and speaker in delivery and not turn.get("delivery_hint"):
                    turn["delivery_hint"] = str(delivery[speaker])[:40]
    return plan


def run_audio_director(
    *,
    ast: ScriptAST,
    llm_client: object | None,
) -> dict[str, Any]:
    """Run audio director prompt and parse JSON response."""
    if llm_client is None:
        raise RuntimeError("audio director requested but llm_client is None")
    prompt = _prompt(ast)
    raw = call_with_backoff(llm_client, prompt, system=_SYSTEM, max_retries=2)
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("audio director response must be a JSON object")
    return payload
