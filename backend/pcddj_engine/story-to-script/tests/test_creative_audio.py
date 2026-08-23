"""Tests for creative audio intelligence fixes.

Covers:
    1. narration_segments wiring in build_voice_clips
    2. Knowledge-base extraction from raw sentences
    3. SFX anchor matching logic
    4. SFX fallback with has_sound_event from voice clips
"""

import pytest

from dsl.builders.clips import (
    _build_segment_index,
    _lookup_segment,
    _match_sfx_anchor,
    build_sfx_clips,
    build_voice_clips,
)
from dsl.schema import DraftClip


# ===================================================================
# 1. Narration segments wiring
# ===================================================================

class TestNarrationSegmentsWiring:
    """build_voice_clips() should attach segment_type and has_sound_event."""

    def test_segment_metadata_attached_to_pure_narration(self):
        scene = {
            "structure": {
                "sentences": ["The door slammed shut.", "Silence filled the room."],
                "dialogue_turns": [],
                "narration_segments": [
                    {"text": "The door slammed shut.", "segment_type": "action", "has_sound_event": True},
                    {"text": "Silence filled the room.", "segment_type": "description", "has_sound_event": False},
                ],
            },
        }
        clips = build_voice_clips(scene, {})
        narrator_clips = clips["narrator"]
        assert narrator_clips[0].segment_type == "action"
        assert narrator_clips[0].has_sound_event is True
        assert narrator_clips[1].segment_type == "description"
        assert narrator_clips[1].has_sound_event is False

    def test_no_narration_segments_leaves_none(self):
        scene = {
            "structure": {
                "sentences": ["The sun rose."],
                "dialogue_turns": [],
            },
        }
        clips = build_voice_clips(scene, {})
        assert clips["narrator"][0].segment_type is None
        assert clips["narrator"][0].has_sound_event is None

    def test_empty_narration_segments_leaves_none(self):
        scene = {
            "structure": {
                "sentences": ["A quiet day."],
                "dialogue_turns": [],
                "narration_segments": [],
            },
        }
        clips = build_voice_clips(scene, {})
        assert clips["narrator"][0].segment_type is None

    def test_partial_match_via_substring(self):
        scene = {
            "structure": {
                "sentences": ["He ran quickly through the forest."],
                "dialogue_turns": [],
                "narration_segments": [
                    {"text": "ran quickly through the forest", "segment_type": "action", "has_sound_event": True},
                ],
            },
        }
        clips = build_voice_clips(scene, {})
        assert clips["narrator"][0].segment_type == "action"
        assert clips["narrator"][0].has_sound_event is True

    def test_indirect_speech_gets_segment_metadata(self):
        scene = {
            "structure": {
                "sentences": ["She said that she was afraid."],
                "dialogue_turns": [
                    {"speaker": "She", "text": "she was afraid", "start_char": 14, "end_char": 28, "quote_style": "indirect"},
                ],
                "narration_segments": [
                    {"text": "She said that she was afraid.", "segment_type": "inner_thought", "has_sound_event": False},
                ],
            },
        }
        clips = build_voice_clips(scene, {})
        assert clips["narrator"][0].segment_type == "inner_thought"


# ===================================================================
# 2. Segment index helpers
# ===================================================================

class TestSegmentIndex:
    def test_build_segment_index_valid(self):
        segs = [
            {"text": "The door slammed.", "segment_type": "action", "has_sound_event": True},
            {"text": "It was dark.", "segment_type": "description", "has_sound_event": False},
        ]
        idx = _build_segment_index(segs)
        assert len(idx) == 2
        assert idx[0] == ("The door slammed.", "action", True)

    def test_build_segment_index_invalid_type_becomes_none(self):
        segs = [{"text": "Hello", "segment_type": "nonexistent_type", "has_sound_event": False}]
        idx = _build_segment_index(segs)
        assert idx[0][1] is None

    def test_build_segment_index_empty_text_skipped(self):
        segs = [{"text": "", "segment_type": "action", "has_sound_event": True}]
        idx = _build_segment_index(segs)
        assert len(idx) == 0

    def test_lookup_segment_exact_match(self):
        idx = [("the door slammed.", "action", True)]
        seg_type, has_sound = _lookup_segment("The door slammed.", idx)
        assert seg_type == "action"
        assert has_sound is True

    def test_lookup_segment_no_match(self):
        idx = [("unrelated text", "description", False)]
        seg_type, has_sound = _lookup_segment("The door slammed.", idx)
        assert seg_type is None
        assert has_sound is None


# ===================================================================
# 3. Knowledge base extraction
# ===================================================================

class TestKnowledgeBaseExtraction:
    """extract_sound_cues_from_nlp with doc_span=None (raw sentence fallback)."""

    def test_running_in_park(self):
        from story_processing.nlp.sound_knowledge_base import extract_sound_cues_from_nlp

        sentences = ["A man was running in a park, breathing heavy."]
        sfx, ambience = extract_sound_cues_from_nlp(None, sentences)

        sfx_labels = {e["sfx_label"] for e in sfx}
        assert "footsteps_fast" in sfx_labels
        assert "breathing_heavy" in sfx_labels or "breathing" in sfx_labels

        assert "birds_chirping" in ambience

    def test_door_slam(self):
        from story_processing.nlp.sound_knowledge_base import extract_sound_cues_from_nlp

        sentences = ["He slammed the door shut."]
        sfx, ambience = extract_sound_cues_from_nlp(None, sentences)

        sfx_labels = {e["sfx_label"] for e in sfx}
        assert "slam_heavy" in sfx_labels

    def test_kitchen_ambience(self):
        from story_processing.nlp.sound_knowledge_base import extract_sound_cues_from_nlp

        sentences = ["She was cooking in the kitchen."]
        sfx, ambience = extract_sound_cues_from_nlp(None, sentences)

        assert "kitchen_ambience" in ambience or "fridge_hum" in ambience

    def test_forest_scene(self):
        from story_processing.nlp.sound_knowledge_base import extract_sound_cues_from_nlp

        sentences = ["They walked through the dark forest."]
        sfx, ambience = extract_sound_cues_from_nlp(None, sentences)

        sfx_labels = {e["sfx_label"] for e in sfx}
        assert "footsteps_slow" in sfx_labels
        assert "birds_forest" in ambience or "wind_trees" in ambience

    def test_no_sounds_in_abstract_text(self):
        from story_processing.nlp.sound_knowledge_base import extract_sound_cues_from_nlp

        sentences = ["The idea was important."]
        sfx, ambience = extract_sound_cues_from_nlp(None, sentences)
        assert len(sfx) == 0
        assert len(ambience) == 0

    def test_sfx_event_has_correct_schema(self):
        from story_processing.nlp.sound_knowledge_base import extract_sound_cues_from_nlp

        sentences = ["He punched the wall."]
        sfx, _ = extract_sound_cues_from_nlp(None, sentences)
        assert len(sfx) > 0
        evt = sfx[0]
        assert "source_text" in evt
        assert "sfx_label" in evt
        assert "sfx_description" in evt
        assert "intensity" in evt
        assert "semantic_role" in evt
        assert "timing" in evt
        assert "order_hint" in evt

    def test_deduplication(self):
        from story_processing.nlp.sound_knowledge_base import extract_sound_cues_from_nlp

        sentences = ["He ran fast.", "She ran faster."]
        sfx, _ = extract_sound_cues_from_nlp(None, sentences)

        labels = [e["sfx_label"] for e in sfx]
        assert len(labels) == len(set(labels)), "SFX labels should be deduplicated"


# ===================================================================
# 4. SFX anchor matching
# ===================================================================

class TestSFXAnchorMatching:
    def test_source_text_match(self):
        voice = [
            DraftClip(tts_text="The door slammed shut.", order=0),
            DraftClip(tts_text="He walked away.", order=1),
        ]
        event = {
            "source_text": "door slammed shut",
            "sfx_label": "door_slam",
            "semantic_role": "impact",
            "order_hint": 0,
        }
        order, position = _match_sfx_anchor(event, voice, "impact")
        assert order == 0
        assert position == "after"

    def test_order_hint_fallback(self):
        voice = [
            DraftClip(tts_text="First line.", order=0),
            DraftClip(tts_text="Second line.", order=1),
            DraftClip(tts_text="Third line.", order=2),
        ]
        event = {
            "source_text": "nonexistent text",
            "sfx_label": "crash",
            "semantic_role": "movement",
            "order_hint": 2,
        }
        order, position = _match_sfx_anchor(event, voice, "movement")
        assert order == 2
        assert position == "under"

    def test_order_hint_clamps_to_last(self):
        voice = [DraftClip(tts_text="Only line.", order=0)]
        event = {"source_text": "nope", "order_hint": 99}
        order, position = _match_sfx_anchor(event, voice, "texture")
        assert order == 0

    def test_empty_voice_clips(self):
        event = {"source_text": "something", "order_hint": 0}
        order, position = _match_sfx_anchor(event, [], "impact")
        assert order is None
        assert position is None

    def test_impact_gets_after_position(self):
        voice = [DraftClip(tts_text="He punched the wall.", order=0)]
        event = {"source_text": "punched the wall", "order_hint": 0}
        _, position = _match_sfx_anchor(event, voice, "impact")
        assert position == "after"

    def test_movement_gets_under_position(self):
        voice = [DraftClip(tts_text="He ran across the field.", order=0)]
        event = {"source_text": "ran across", "order_hint": 0}
        _, position = _match_sfx_anchor(event, voice, "movement")
        assert position == "under"

    def test_interaction_gets_after_position(self):
        voice = [DraftClip(tts_text="She grabbed the handle.", order=0)]
        event = {"source_text": "grabbed the handle", "order_hint": 0}
        _, position = _match_sfx_anchor(event, voice, "interaction")
        assert position == "after"


# ===================================================================
# 5. SFX fallback with has_sound_event
# ===================================================================

class TestSFXFallbackWithSoundEvent:
    def test_action_segments_generate_sfx(self):
        """When no SFX events and no numeric threshold hit,
        voice clips with has_sound_event=True should produce SFX."""
        voice_clips = {
            "narrator": [
                DraftClip(tts_text="He slammed the door.", order=0, segment_type="action", has_sound_event=True),
                DraftClip(tts_text="Silence fell.", order=1, segment_type="description", has_sound_event=False),
            ],
        }
        scene = {
            "structure": {"sfx_events": []},
            "signals": {"short_sentence_streak": 0, "punctuation_score": 0.0},
            "interpretation": {"silence_intent": "none"},
        }
        clips = build_sfx_clips(scene, 0.3, has_sfx_track=True, voice_clips=voice_clips)
        assert "sfx" in clips
        assert any(c.sfx_hint == "action_sfx" for c in clips["sfx"])
        assert clips["sfx"][0].anchor_order == 0

    def test_no_action_segments_no_sfx(self):
        voice_clips = {
            "narrator": [
                DraftClip(tts_text="It was quiet.", order=0, segment_type="description", has_sound_event=False),
            ],
        }
        scene = {
            "structure": {"sfx_events": []},
            "signals": {"short_sentence_streak": 0, "punctuation_score": 0.0},
            "interpretation": {"silence_intent": "none"},
        }
        clips = build_sfx_clips(scene, 0.3, has_sfx_track=True, voice_clips=voice_clips)
        assert clips == {}

    def test_numeric_threshold_takes_priority_over_segments(self):
        """The legacy numeric threshold path runs first in the fallback."""
        voice_clips = {
            "narrator": [
                DraftClip(tts_text="Bang!", order=0, segment_type="action", has_sound_event=True),
            ],
        }
        scene = {
            "structure": {"sfx_events": []},
            "signals": {"short_sentence_streak": 5, "punctuation_score": 2.0},
            "interpretation": {"silence_intent": "none"},
        }
        clips = build_sfx_clips(scene, 0.3, has_sfx_track=True, voice_clips=voice_clips)
        assert "sfx" in clips
        assert clips["sfx"][0].sfx_hint == "impact_accent"
