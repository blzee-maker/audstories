"""Minimal audiobook narrative plan — no full story pipeline."""

import orjson

from dsl.compiler import compile_timeline
from story_processing.audiobook_minimal_plan import (
    build_minimal_narrative_plan_dict,
    split_into_narration_sentences,
    text_metrics_for_chapter,
)


def test_text_metrics():
    m = text_metrics_for_chapter("Hello world.\n")
    assert m["source_character_count"] == 12  # "Hello world."
    assert m["source_word_count"] == 2
    assert m["estimated_narration_seconds"] >= 0.5


def test_single_chapter_block():
    s = split_into_narration_sentences("First. Second! Third?")
    assert len(s) == 1
    assert "First" in s[0] and "Third" in s[0]


def test_minimal_plan_assembles_and_compiles():
    text = "Line one. Line two."
    plan = build_minimal_narrative_plan_dict(text)
    assert plan["schema_version"] == "1.0"
    assert len(plan["scenes"]) == 1
    metrics = text_metrics_for_chapter(text)
    draft = compile_timeline(
        plan,
        project_type="audiobook",
        narration_only=True,
        source_text_metrics=metrics,
    )
    assert draft["settings"]["narration_only"] is True
    assert draft["settings"]["source_word_count"] == 4
    assert draft["settings"]["estimated_narration_seconds"] is not None
    tracks = [t["id"] for t in draft["tracks"]]
    assert tracks == ["narrator"]
    scene = draft["scenes"][0]
    assert len(scene["tracks"]["narrator"]) == 1


def test_cli_run_single_file_fast_path_no_llm(tmp_path, monkeypatch):
    """run_single_file skips process_story_json when audiobook + narration_only."""
    from cli import run_single_file

    inp = tmp_path / "ch.txt"
    inp.write_text("A short tale. The end.", encoding="utf-8")
    out = tmp_path / "out"
    calls: list[str] = []

    def boom(*_a, **_k):
        calls.append("process_story_json")
        raise AssertionError("full pipeline should not run")

    monkeypatch.setattr(
        "story_processing.pipeline.process_story_json",
        boom,
    )
    run_single_file(
        inp, out, None,
        project_type="audiobook",
        narration_only=True,
    )
    assert not calls
    assert (out / "narrative_plan.json").is_file()
    assert (out / "draft_timeline.json").is_file()
    data = orjson.loads((out / "draft_timeline.json").read_bytes())
    assert data["settings"]["source_character_count"] > 0
    assert data["settings"]["source_word_count"] == 5
