"""Shared fixtures for the audstories test suite."""

from __future__ import annotations

import pytest
import spacy


# ---------------------------------------------------------------------------
# Sample story text (multi-scene, with dialogue)
# ---------------------------------------------------------------------------

SAMPLE_STORY = (
    'The old house stood at the end of the lane. Rain hammered the windows.\n'
    'Eleanor pushed the door open. "Is anyone here?" she called.\n'
    '"Over here," whispered Marcus from the shadows.\n'
    'She stepped inside cautiously.\n'
    '\n\n\n'
    'The next morning, sunlight flooded the room. Birds sang outside.\n'
    'Eleanor smiled. "We made it through the night," she said.\n'
    'Marcus nodded. "Barely," he replied with a grin.\n'
    'They packed their bags and left the house behind.\n'
)


# ---------------------------------------------------------------------------
# spaCy session-scoped fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def nlp():
    """Load en_core_web_sm once for the entire test session."""
    return spacy.load("en_core_web_sm")


@pytest.fixture(scope="session")
def make_doc(nlp):
    """Factory fixture: returns a callable that creates a parsed Doc."""

    def _make(text: str):
        return nlp(text)

    return _make


# ---------------------------------------------------------------------------
# Mock LLM client
# ---------------------------------------------------------------------------

class MockLLMClient:
    """Minimal mock for ``story_processing.ai.llm_client.LLMClient``.

    Only ``.complete()`` is mocked.  The return value is configurable
    via the constructor so that classifier logic executes fully.
    """

    def __init__(self, response: str = "{}"):
        self.response = response
        self.call_count = 0

    def complete(self, prompt: str, *, system: str = "") -> str:
        self.call_count += 1
        return self.response
