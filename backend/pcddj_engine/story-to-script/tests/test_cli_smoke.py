"""CLI smoke test — subprocess test of the audstories entry point.

Runs the actual CLI via subprocess and verifies:
- Exit code 0
- Output files created
- Output JSON is parseable
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from tests.conftest import SAMPLE_STORY

pytestmark = pytest.mark.slow


class TestCLISmoke:
    def test_process_no_llm(self):
        """audstories process --no-llm should succeed end-to-end."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write sample story to a temp file
            story_file = Path(tmpdir) / "story.txt"
            story_file.write_text(SAMPLE_STORY, encoding="utf-8")

            output_dir = Path(tmpdir) / "output"

            result = subprocess.run(
                [
                    sys.executable, "-m", "cli",
                    "process",
                    "--input", str(story_file),
                    "--output", str(output_dir),
                    "--no-llm",
                ],
                capture_output=True,
                text=True,
                timeout=180,
                cwd=str(Path(__file__).resolve().parent.parent),
            )

            assert result.returncode == 0, (
                f"CLI failed with code {result.returncode}.\n"
                f"STDOUT: {result.stdout}\n"
                f"STDERR: {result.stderr}"
            )

            # Check output files exist
            plan_path = output_dir / "narrative_plan.json"
            timeline_path = output_dir / "draft_timeline.json"
            assert plan_path.exists(), "narrative_plan.json not created"
            assert timeline_path.exists(), "draft_timeline.json not created"

            # Verify JSON is parseable
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            assert "scenes" in plan

            timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
            assert "tracks" in timeline
            assert "scenes" in timeline
