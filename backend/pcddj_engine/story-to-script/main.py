"""Example usage of the Story Processing Pipeline + DSL Compiler.

Runs the full pipeline on an inline sample story using Google Gemini
for AI classification and audio cue extraction.

Requires the GEMINI_API_KEY environment variable to be set.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from dsl.compiler import compile_timeline, compile_timeline_json
from story_processing.pipeline import process_story, process_story_json

# Load .env file (picks up GEMINI_API_KEY, etc.)
load_dotenv()


# ---------------------------------------------------------------------------
# Sample story (short, ~200 words)
# ---------------------------------------------------------------------------
SAMPLE_STORY = """
The cabin shuddered as thunder cracked overhead, and Elena pressed her back against the door, her breath shallow and quick.

"We can't stay here," Marcus whispered, his voice barely rising above the storm.

She didn't move.

"Elena, please — they're coming."
"""


def _get_llm_client():
    """Create a Gemini client (reads GEMINI_API_KEY from env)."""
    try:
        from story_processing.ai.llm_client import GeminiClient

        client = GeminiClient(model="gemini-2.0-flash")
        print(f"  [info] Gemini client ready (model={client.model}).")
        return client
    except Exception as exc:
        print(f"  [warn] Could not create GeminiClient: {exc}")
        print("  [info] Falling back to heuristic-only mode.")
        return None


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    root = Path(__file__).parent
    llm_client = _get_llm_client()

    # ==================================================================
    # Phase 1: Narrative Plan (AI + NLP)
    # ==================================================================
    print("=" * 60)
    print("  Phase 1 — Narrative Plan")
    print("=" * 60)
    print()

    plan = process_story(SAMPLE_STORY, llm_client=llm_client)
    plan_json = process_story_json(SAMPLE_STORY, llm_client=llm_client)

    print(plan_json.decode("utf-8"))

    plan_path = root / "example_output.json"
    plan_path.write_bytes(plan_json)
    print(f"\nNarrative Plan written to: {plan_path}")

    # ==================================================================
    # Phase 2: Draft Timeline (DSL Compiler)
    # ==================================================================
    print()
    print("=" * 60)
    print("  Phase 2 — Draft Timeline (DSL)")
    print("=" * 60)
    print()

    draft_timeline = compile_timeline(plan)
    draft_json = compile_timeline_json(plan)

    print(draft_json.decode("utf-8"))

    draft_path = root / "example_draft_timeline.json"
    draft_path.write_bytes(draft_json)
    print(f"\nDraft Timeline written to: {draft_path}")


if __name__ == "__main__":
    main()
