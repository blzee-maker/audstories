"""Determinism test — ensures identical output for identical input.

Protects: scene ID hashing, speaker reconciliation, context trend
logic, and energy momentum rules.
"""

import pytest

from dsl.compiler import compile_timeline
from story_processing.pipeline import process_story

from tests.conftest import SAMPLE_STORY

pytestmark = [pytest.mark.contract, pytest.mark.spacy]


class TestDeterminism:
    def test_narrative_plan_deterministic(self):
        """Two identical process_story runs must produce identical output."""
        result1 = process_story(
            SAMPLE_STORY, llm_client=None, model_name="en_core_web_sm"
        )
        result2 = process_story(
            SAMPLE_STORY, llm_client=None, model_name="en_core_web_sm"
        )
        assert result1 == result2

    def test_draft_timeline_deterministic(self):
        """compile_timeline on the same plan must produce identical output."""
        plan = process_story(
            SAMPLE_STORY, llm_client=None, model_name="en_core_web_sm"
        )
        timeline1 = compile_timeline(plan)
        timeline2 = compile_timeline(plan)
        assert timeline1 == timeline2

    def test_full_pipeline_deterministic(self):
        """End-to-end: process + compile must be deterministic."""
        plan1 = process_story(
            SAMPLE_STORY, llm_client=None, model_name="en_core_web_sm"
        )
        timeline1 = compile_timeline(plan1)

        plan2 = process_story(
            SAMPLE_STORY, llm_client=None, model_name="en_core_web_sm"
        )
        timeline2 = compile_timeline(plan2)

        assert timeline1 == timeline2
