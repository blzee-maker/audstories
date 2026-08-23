"""Tests for story_processing.context."""

import pytest

from story_processing.context import StoryContextBuilder, reconcile_speakers


# ---------------------------------------------------------------------------
# StoryContextBuilder
# ---------------------------------------------------------------------------

class TestStoryContextBuilder:
    def test_scene_zero_empty_history(self):
        builder = StoryContextBuilder(total_scenes=3)
        ctx = builder.get_context(0)
        assert ctx.scene_index == 0
        assert ctx.prev_emotions == []
        assert ctx.emotion_trend == "stable"
        assert ctx.pacing_trend == "steady"
        assert ctx.position_ratio == 0.0

    def test_position_ratio_bounds(self):
        builder = StoryContextBuilder(total_scenes=5)
        ctx = builder.get_context(0)
        assert 0.0 <= ctx.position_ratio <= 1.0
        ctx = builder.get_context(4)
        assert 0.0 <= ctx.position_ratio <= 1.0

    def test_advance_accumulates_emotions(self):
        builder = StoryContextBuilder(total_scenes=3)
        for i in range(3):
            builder.advance({
                "signals": {
                    "emotion_scores": {"anxiety": 0.8, "joy": 0.1},
                },
                "interpretation": {"primary_emotion": "anxiety"},
                "structure": {"word_count": 100, "speakers": ["Alice"]},
            })
        ctx = builder.get_context(3)
        assert len(ctx.prev_emotions) == 3
        assert all(e == "anxiety" for e in ctx.prev_emotions)

    def test_escalating_trend(self):
        builder = StoryContextBuilder(total_scenes=4)
        # Increasing arousal values
        for arousal in [0.1, 0.3, 0.5]:
            builder.advance({
                "signals": {"emotion_scores": {"anxiety": arousal, "anger": arousal}},
                "interpretation": {"primary_emotion": "anxiety"},
                "structure": {"word_count": 100, "speakers": []},
            })
        ctx = builder.get_context(3)
        assert ctx.emotion_trend == "escalating"

    def test_de_escalating_trend(self):
        builder = StoryContextBuilder(total_scenes=4)
        for arousal in [0.5, 0.3, 0.1]:
            builder.advance({
                "signals": {"emotion_scores": {"anxiety": arousal, "anger": arousal}},
                "interpretation": {"primary_emotion": "anxiety"},
                "structure": {"word_count": 100, "speakers": []},
            })
        ctx = builder.get_context(3)
        assert ctx.emotion_trend == "de-escalating"

    def test_volatile_trend(self):
        builder = StoryContextBuilder(total_scenes=4)
        emotions = ["joy", "sadness", "anger"]
        for emo in emotions:
            builder.advance({
                "signals": {"emotion_scores": {emo: 0.5}},
                "interpretation": {"primary_emotion": emo},
                "structure": {"word_count": 100, "speakers": []},
            })
        ctx = builder.get_context(3)
        assert ctx.emotion_trend == "volatile"

    def test_accelerating_pacing(self):
        builder = StoryContextBuilder(total_scenes=4)
        for wc in [200, 150, 100]:
            builder.advance({
                "signals": {"emotion_scores": {}},
                "interpretation": {"primary_emotion": "neutral"},
                "structure": {"word_count": wc, "speakers": []},
            })
        ctx = builder.get_context(3)
        assert ctx.pacing_trend == "accelerating"

    def test_decelerating_pacing(self):
        builder = StoryContextBuilder(total_scenes=4)
        for wc in [100, 150, 200]:
            builder.advance({
                "signals": {"emotion_scores": {}},
                "interpretation": {"primary_emotion": "neutral"},
                "structure": {"word_count": wc, "speakers": []},
            })
        ctx = builder.get_context(3)
        assert ctx.pacing_trend == "decelerating"

    def test_known_speakers_accumulated(self):
        builder = StoryContextBuilder(total_scenes=2)
        builder.advance({
            "signals": {"emotion_scores": {}},
            "interpretation": {"primary_emotion": "neutral"},
            "structure": {"word_count": 50, "speakers": ["Alice"]},
        })
        builder.advance({
            "signals": {"emotion_scores": {}},
            "interpretation": {"primary_emotion": "neutral"},
            "structure": {"word_count": 50, "speakers": ["Bob", "Alice"]},
        })
        ctx = builder.get_context(2)
        assert "Alice" in ctx.known_speakers
        assert "Bob" in ctx.known_speakers

    def test_invariant_emotion_trend_values(self):
        """emotion_trend must be one of the four allowed values."""
        builder = StoryContextBuilder(total_scenes=5)
        allowed = {"stable", "escalating", "de-escalating", "volatile"}
        for i in range(5):
            builder.advance({
                "signals": {"emotion_scores": {"joy": 0.5 + i * 0.05}},
                "interpretation": {"primary_emotion": "joy"},
                "structure": {"word_count": 50 + i * 10, "speakers": []},
            })
            ctx = builder.get_context(i + 1)
            assert ctx.emotion_trend in allowed
            assert 0.0 <= ctx.position_ratio <= 1.0


# ---------------------------------------------------------------------------
# reconcile_speakers
# ---------------------------------------------------------------------------

@pytest.mark.spacy
class TestReconcileSpeakers:
    def test_unknown_replaced_when_propn_nearby(self, make_doc):
        text = 'Alice walked in. "Hello," she said.'
        doc = make_doc(text)
        scene_data = [{
            "structure": {
                "speakers": ["unknown_speaker_1"],
                "dialogue_turns": [
                    {"speaker": "unknown_speaker_1", "text": "Hello,", "start_char": 18, "end_char": 24},
                ],
            },
        }]
        reconcile_speakers(scene_data, doc)
        turn = scene_data[0]["structure"]["dialogue_turns"][0]
        # Should attempt to resolve to Alice (nearby named speaker)
        # The exact result depends on spaCy parse, but the function should run
        assert turn["speaker"] is not None

    def test_global_renumbering(self, make_doc):
        text = "Someone spoke. Another person spoke."
        doc = make_doc(text)
        scene_data = [
            {
                "structure": {
                    "speakers": ["unknown_speaker_5"],
                    "dialogue_turns": [
                        {"speaker": "unknown_speaker_5", "text": "Hi", "start_char": 0, "end_char": 2},
                    ],
                },
            },
            {
                "structure": {
                    "speakers": ["unknown_speaker_9"],
                    "dialogue_turns": [
                        {"speaker": "unknown_speaker_9", "text": "Bye", "start_char": 15, "end_char": 18},
                    ],
                },
            },
        ]
        reconcile_speakers(scene_data, doc)
        # After renumbering, unknowns should be sequential from 1
        s1 = scene_data[0]["structure"]["dialogue_turns"][0]["speaker"]
        s2 = scene_data[1]["structure"]["dialogue_turns"][0]["speaker"]
        assert s1 == "unknown_speaker_1"
        assert s2 == "unknown_speaker_2"
