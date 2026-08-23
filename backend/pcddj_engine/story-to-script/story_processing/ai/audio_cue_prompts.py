"""Prompt templates for Gemini-powered audio cue extraction.

The prompt instructs the LLM to act as an audio sound designer
analyzing story text, extracting SFX events, ambience cues,
and classifying each clause of narration.
"""

from __future__ import annotations

import json

# ---------------------------------------------------------------------------
# System prompt — shared across all audio cue extraction calls
# ---------------------------------------------------------------------------
AUDIO_CUE_SYSTEM_PROMPT: str = (
    "You are an expert audio sound designer for story podcasts and audiobooks. "
    "Your job is to analyze story text and extract every audio production cue "
    "needed to bring the scene to life. You think in terms of: narration "
    "(voice-over), dialogue (character speech), sound effects (SFX), and "
    "ambience/atmosphere layers. "
    "Return ONLY valid JSON. No explanation, no markdown."
)

AUDIO_CUE_SYSTEM_PROMPT_DRAMA: str = (
    "You are an expert audio sound designer for narrative audio dramas "
    "(radio plays). CRITICAL: There is NO narrator in this production. "
    "The listener understands the scene ONLY through character dialogue, "
    "ambience (where they are), sound effects (what is happening physically), "
    "and music (emotional state). Your extractions must be maximally specific "
    "because sound design is the ONLY way the listener understands the scene. "
    "Return ONLY valid JSON. No explanation, no markdown."
)

# ---------------------------------------------------------------------------
# Audio cue extraction prompt template
# ---------------------------------------------------------------------------
AUDIO_CUE_EXTRACTION_TEMPLATE: str = """\
Analyze the following story text as an audio sound designer. Break it down \
into its production elements.

STORY TEXT:
---
{scene_text}
---

ALREADY EXTRACTED DIALOGUE (do NOT re-extract these — they are handled separately):
{dialogue_json}

For the NON-DIALOGUE portions of the text, analyze each clause and extract:

1. **SFX events**: Any action, event, or described sound that should have a \
sound effect.
   - Think about what the LISTENER would hear if this were a movie scene.
   - "The power cut out" → the listener hears an electrical switch / power \
failure sound.
   - "the old clock stopped ticking" → the listener hears clock ticking that \
abruptly stops.
   - "The door slammed" → a door slam SFX.
   - Be specific about what the sound IS, not just what happens in the story.

2. **Ambience / Atmosphere**: The overall environmental soundscape the scene \
implies.
   - Consider what the listener should hear in the background throughout.
   - "sudden darkness" + "silence" → eerie, quiet room tone.
   - A forest scene → birds, wind, rustling leaves.
   - Think about what fills the SILENCE between dialogue and narration.

3. **Narration segments**: Classify each non-dialogue clause as one of:
   - "action" — something physically happens (produces or implies sound)
   - "description" — visual/sensory description (sets the scene but no \
distinct sound)
   - "scene_setting" — establishes location, time, or atmosphere
   - "transition" — time skip, scene change, or bridging text
   - "inner_thought" — character's internal monologue (not spoken aloud)

Return a JSON object with EXACTLY this structure:

{{
  "sfx_events": [
    {{
      "source_text": "<the exact clause from the text that triggers this SFX>",
      "sfx_label": "<short snake_case label like 'power_outage', 'clock_stops', \
'door_slam'>",
      "sfx_description": "<what the actual sound should be, e.g. 'electrical \
buzzing followed by abrupt silence'>",
      "intensity": "<one of: 'subtle', 'moderate', 'strong', 'dramatic'>",
      "semantic_role": "<one of: 'impact', 'movement', 'ambience', \
'interaction', 'texture'>",
      "timing": "<one of: 'instant', 'short', 'sustained'>",
      "order_hint": <integer — relative order in the scene, starting from 0>
    }}
  ],
  "ambience": {{
    "primary_atmosphere": "<short snake_case label like 'eerie_silence', \
'dark_room', 'forest_night'>",
    "atmosphere_description": "<describe the ambient sound bed, e.g. 'very \
quiet room with occasional creaking'>",
    "intensity": "<one of: 'minimal', 'subtle', 'moderate', 'rich'>",
    "evolves": <true if the ambience should change during the scene, false \
if static>
  }},
  "narration_segments": [
    {{
      "text": "<the clause text>",
      "segment_type": "<one of: 'action', 'description', 'scene_setting', \
'transition', 'inner_thought'>",
      "has_sound_event": <true if this clause implies a sound the listener \
should hear>
    }}
  ]
}}

CONSTRAINTS:
- Extract EVERY distinct sound event. If a sentence has two actions, extract \
two SFX.
- Do NOT include dialogue as narration_segments (dialogue is handled \
separately).
- sfx_label must be unique snake_case identifiers.
- semantic_role MUST be one of: "impact", "movement", "ambience", \
"interaction", "texture"
- Return ONLY the JSON object. No explanation. No markdown."""


_DRAMA_MODE_ADDENDUM: str = """

ADDITIONAL AUDIO DRAMA CONSTRAINTS (NO NARRATOR):
- There is NO narrator voice. Scene descriptions are conveyed ONLY through \
sound design.
- Extract ambience with MAXIMUM specificity. 'outdoor' is NOT specific enough. \
Use 'rain_heavy_train_station' or 'quiet_suburban_night_crickets' instead.
- Every physical action mentioned MUST have a corresponding SFX event.
- Every location MUST have a layered, specific ambience description.
- Think about what fills the silence between character lines — the listener \
needs environmental audio to understand where they are."""


def build_audio_cue_prompt(
    scene_text: str,
    dialogue_turns: list[dict],
    *,
    project_type: str = "audio_drama",
) -> str:
    """Build the audio cue extraction prompt for a scene.

    Parameters
    ----------
    scene_text:
        The full text of the scene.
    dialogue_turns:
        Already-extracted dialogue turns (so the LLM skips them).
    project_type:
        ``"audiobook"`` or ``"audio_drama"``.  Audio drama mode appends
        additional instructions for aggressive extraction.

    Returns
    -------
    str — the fully rendered prompt.
    """
    dialogue_json = json.dumps(
        [
            {"speaker": d.get("speaker", "unknown"), "text": d.get("text", "")}
            for d in dialogue_turns
        ],
        indent=2,
    )
    base = AUDIO_CUE_EXTRACTION_TEMPLATE.format(
        scene_text=scene_text,
        dialogue_json=dialogue_json,
    )
    if project_type == "audio_drama":
        base += _DRAMA_MODE_ADDENDUM
    return base


def get_system_prompt(project_type: str = "audio_drama") -> str:
    """Return the appropriate system prompt for the given project type."""
    if project_type == "audio_drama":
        return AUDIO_CUE_SYSTEM_PROMPT_DRAMA
    return AUDIO_CUE_SYSTEM_PROMPT
