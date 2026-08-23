"""Contract tests — cross-layer invariant validation.

Runs the real pipeline end-to-end with no LLM on a short story
and asserts that the output satisfies all downstream contracts.
"""

import pytest

from dsl.compiler import compile_timeline
from dsl.schema import DraftTimeline
from story_processing.pipeline import process_story
from story_processing.validation.schema import NarrativePlan
from story_processing.validation.validator import validate_interpretation

from tests.conftest import SAMPLE_STORY

pytestmark = [pytest.mark.contract, pytest.mark.spacy]


@pytest.fixture(scope="module")
def narrative_plan():
    """Run the pipeline once for the module and cache the result."""
    return process_story(SAMPLE_STORY, llm_client=None, model_name="en_core_web_sm")


@pytest.fixture(scope="module")
def draft_timeline(narrative_plan):
    """Compile the narrative plan into a draft timeline."""
    return compile_timeline(narrative_plan)


class TestNarrativePlanContract:
    def test_pydantic_validation(self, narrative_plan):
        """Narrative Plan must pass Pydantic schema validation."""
        validated = NarrativePlan(**narrative_plan)
        assert validated.schema_version == "1.0"
        assert len(validated.scenes) > 0

    def test_all_scenes_have_required_keys(self, narrative_plan):
        for scene in narrative_plan["scenes"]:
            assert "scene_id" in scene
            assert "structure" in scene
            assert "signals" in scene
            assert "interpretation" in scene

    def test_interpretation_already_valid(self, narrative_plan):
        """validate_interpretation should be a no-op on already-valid data."""
        for scene in narrative_plan["scenes"]:
            original = dict(scene["interpretation"])
            result = validate_interpretation(
                structure=scene["structure"],
                signals=scene["signals"],
                interpretation=dict(scene["interpretation"]),
            )
            # All values should remain unchanged (already valid)
            assert result["primary_emotion"] == original["primary_emotion"]
            assert result["energy_level"] == original["energy_level"]
            assert result["scene_style"] == original["scene_style"]

    def test_energy_level_bounds(self, narrative_plan):
        """All energy levels must be in [1, 10]."""
        for scene in narrative_plan["scenes"]:
            energy = scene["interpretation"]["energy_level"]
            assert 1 <= energy <= 10, f"energy_level {energy} out of bounds"

    def test_confidence_score_bounds(self, narrative_plan):
        """All confidence scores must be in [0.0, 1.0]."""
        for scene in narrative_plan["scenes"]:
            conf = scene["interpretation"]["confidence_score"]
            assert 0.0 <= conf <= 1.0, f"confidence_score {conf} out of bounds"

    def test_emotion_intensity_bounds(self, narrative_plan):
        for scene in narrative_plan["scenes"]:
            intensity = scene["interpretation"]["emotion_intensity"]
            assert 1 <= intensity <= 10


class TestDraftTimelineContract:
    def test_pydantic_validation(self, draft_timeline):
        """Draft Timeline must pass Pydantic schema validation."""
        validated = DraftTimeline(**draft_timeline)
        assert len(validated.tracks) > 0

    def test_compile_succeeds(self, draft_timeline):
        """compile_timeline must succeed without exceptions."""
        assert draft_timeline is not None
        assert "tracks" in draft_timeline
        assert "scenes" in draft_timeline

    def test_every_scene_has_audio(self, draft_timeline):
        """Every scene must produce audio on at least one track.

        Note this is deliberately weaker than "every scene has a voice clip".
        In audio drama, narration is silent by design - only dialogue becomes
        voice clips (see _build_audiodrama_voice_clips). A scene of pure
        description therefore has no voice at all, and carries its meaning
        through SFX and ambience instead. Requiring a voice clip per scene
        would forbid that legitimate output.
        """
        for scene in draft_timeline["scenes"]:
            has_audio = any(len(clips) > 0 for clips in scene["tracks"].values())
            assert has_audio, f"Scene {scene['id']} has no clips on any track"

    def test_scene_track_ids_exist(self, draft_timeline):
        """All track IDs referenced in scenes must exist in top-level tracks."""
        top_level_ids = {t["id"] for t in draft_timeline["tracks"]}
        for scene in draft_timeline["scenes"]:
            for tid in scene["tracks"]:
                assert tid in top_level_ids, (
                    f"Scene {scene['id']} references unknown track '{tid}'"
                )

    def test_energy_bounds(self, draft_timeline):
        for scene in draft_timeline["scenes"]:
            assert 0.0 <= scene["energy"] <= 1.0
