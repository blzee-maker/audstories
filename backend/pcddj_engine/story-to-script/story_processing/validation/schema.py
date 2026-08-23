"""Pydantic v2 schema models for the Narrative Plan.

Enforces enum constraints, numeric bounds, and required fields.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Allowed enum values
# ---------------------------------------------------------------------------
EmotionType = Literal[
    "anxiety", "joy", "sadness", "anger", "calm", "neutral",
    "surprise", "disgust", "love", "anticipation", "nostalgia", "confusion",
]
SceneStyleType = Literal["dialogue_driven", "narrative_heavy", "balanced", "action_heavy"]
SilenceIntentType = Literal["none", "short", "medium", "long"]

SFXIntensityType = Literal["subtle", "moderate", "strong", "dramatic"]
SFXSemanticRoleType = Literal["impact", "movement", "ambience", "interaction", "texture"]
SFXTimingType = Literal["instant", "short", "sustained"]
AmbienceIntensityType = Literal["minimal", "subtle", "moderate", "rich"]
NarrationSegmentType = Literal[
    "action", "description", "scene_setting", "transition", "inner_thought"
]


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

QuoteStyleType = Literal["double", "single", "em_dash", "indirect"]


class DialogueTurnSchema(BaseModel):
    """A single attributed dialogue turn."""
    speaker: str
    text: str
    start_char: int = Field(ge=0)
    end_char: int = Field(ge=0)
    quote_style: QuoteStyleType = "double"
    delivery_hint: str | None = None
    dramatic_function: str | None = None


class SFXEventSchema(BaseModel):
    """An extracted sound effect event from narration text."""
    source_text: str
    sfx_label: str
    sfx_description: str = ""
    intensity: SFXIntensityType = "moderate"
    semantic_role: SFXSemanticRoleType = "impact"
    timing: SFXTimingType = "instant"
    order_hint: int = Field(default=0, ge=0)


class AmbienceCueSchema(BaseModel):
    """Scene-level ambience / atmosphere extracted from text."""
    primary_atmosphere: str
    atmosphere_description: str = ""
    intensity: AmbienceIntensityType = "subtle"
    evolves: bool = False


class NarrationSegmentSchema(BaseModel):
    """A classified clause from narration text."""
    text: str
    segment_type: NarrationSegmentType = "description"
    has_sound_event: bool = False


class ActionDirectiveSchema(BaseModel):
    """Structured action directive extracted from script blocks."""

    kind: Literal["action", "sfx", "ambience", "transition", "title_card"] = "action"
    marker: str | None = None
    text: str
    forced: bool = False


class SceneStructure(BaseModel):
    """Deterministic structural facts about a scene."""
    scene_id: str
    scene_title: str | None = None
    sentence_count: int = Field(ge=0)
    word_count: int = Field(ge=0)
    sentences: list[str]
    dialogue_turns: list[DialogueTurnSchema]
    speakers: list[str]
    # Audio intelligence fields (populated by Gemini when available)
    sfx_events: list[SFXEventSchema] = Field(default_factory=list)
    ambience_cue: AmbienceCueSchema | None = None
    narration_segments: list[NarrationSegmentSchema] = Field(default_factory=list)
    action_notes: list[str] = Field(default_factory=list)
    action_blocks: list[ActionDirectiveSchema] = Field(default_factory=list)


class EmotionArcEntry(BaseModel):
    """A single entry in the per-chunk emotion arc."""
    chunk_index: int = Field(ge=0)
    text_preview: str
    dominant_emotion: str
    scores: dict[str, float]


class SceneSignals(BaseModel):
    """Numeric signals extracted from the scene."""
    avg_sentence_length: float = Field(ge=0.0)
    sentence_length_variance: float = Field(ge=0.0)
    short_sentence_streak: int = Field(ge=0)
    punctuation_score: float = Field(ge=0.0)
    action_verb_density: float = Field(ge=0.0, le=1.0)
    dialogue_ratio: float = Field(ge=0.0, le=1.0)
    dialogue_turn_count: int = Field(ge=0)
    avg_dialogue_length: float = Field(ge=0.0)
    emotion_scores: dict[str, float]
    emotion_arc: list[EmotionArcEntry] = Field(default_factory=list)


class SceneInterpretation(BaseModel):
    """AI/heuristic classification of a scene."""
    primary_emotion: EmotionType
    energy_level: int = Field(ge=1, le=10)
    emotion_intensity: int = Field(ge=1, le=10)
    scene_style: SceneStyleType
    silence_intent: SilenceIntentType
    confidence_score: float = Field(ge=0.0, le=1.0)
    music_strategy: str | None = None


class Scene(BaseModel):
    """A fully processed scene."""
    scene_id: str
    structure: SceneStructure
    signals: SceneSignals
    interpretation: SceneInterpretation


class NarrativePlan(BaseModel):
    """Top-level output schema."""
    schema_version: Literal["1.0"] = "1.0"
    scenes: list[Scene]
