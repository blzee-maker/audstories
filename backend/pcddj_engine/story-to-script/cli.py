"""Aud-Stories CLI — process stories into audio-storytelling timelines.

Usage examples::

    audstories process --input story.txt --output out/
    audstories process --input story.txt --no-llm
    audstories process --input story.txt --model gpt-4
    audstories batch  --input ./stories/ --output ./out/
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

try:
    import orjson  # type: ignore[import-not-found]
except ImportError:
    class _OrjsonFallback:
        OPT_INDENT_2 = None

        @staticmethod
        def dumps(value, option=None):  # noqa: ARG004
            return json.dumps(value, indent=2, ensure_ascii=False).encode("utf-8")

        @staticmethod
        def loads(value):
            if isinstance(value, (bytes, bytearray)):
                value = value.decode("utf-8")
            return json.loads(value)

    orjson = _OrjsonFallback()
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------

def run_single_file(
    input_path: Path,
    output_dir: Path,
    llm_client: object | None,
    *,
    project_type: str = "audio_drama",
    narration_only: bool = False,
    use_director: bool = False,
    gita_path: Path | None = None,
    update_gita: bool = False,
) -> None:
    """Read a story file, run the full pipeline, and write JSON outputs.

    Writes two files into *output_dir*:
        - ``narrative_plan.json``  (from story-processing layer)
        - ``draft_timeline.json`` (from DSL compiler)

    Raises on any failure — callers are responsible for catching and
    reporting errors.
    """
    story_text = input_path.read_text(encoding="utf-8")
    if not story_text.strip():
        raise ValueError(f"Input file is empty: {input_path}")

    fast_audiobook = project_type == "audiobook" and narration_only

    is_script = input_path.suffix.lower() == ".fountain"

    script_diagnostics: list[dict[str, object]] = []
    director_payload: dict[str, object] | None = None
    director_warning: str | None = None
    gita_warning: str | None = None

    if fast_audiobook:
        from dsl.compiler import compile_timeline_json
        from story_processing.audiobook_minimal_plan import (
            build_minimal_narrative_plan_dict,
            text_metrics_for_chapter,
        )
        from story_processing.narrative_plan import serialize

        # Narration-only audiobook: skip NLP/LLM/scene pipeline; one scene, metrics only.
        metrics = text_metrics_for_chapter(story_text)
        plan_dict = build_minimal_narrative_plan_dict(story_text)
        plan_bytes = serialize(plan_dict)
        timeline_bytes = compile_timeline_json(
            plan_dict,
            project_type=project_type,
            narration_only=narration_only,
            source_text_metrics=metrics,
        )
    elif project_type == "audio_drama" and is_script:
        from dsl.compiler import compile_timeline_json
        from story_processing.fountain.audio_director import (
            merge_director_enrichment,
            run_audio_director,
        )
        from story_processing.fountain.gita import (
            apply_gita_to_plan,
            load_gita,
            save_gita,
            update_gita_from_plan,
        )
        from story_processing.fountain.to_plan import process_script_bundle

        plan_bytes, ast = process_script_bundle(story_text, project_type=project_type)
        script_diagnostics = [
            {
                "line": d.line,
                "column": d.column,
                "code": d.code,
                "severity": d.severity,
                "message": d.message,
            }
            for d in ast.diagnostics
        ]
        plan_dict = orjson.loads(plan_bytes)
        if gita_path is not None and gita_path.is_file():
            try:
                gita_payload = load_gita(gita_path)
                plan_dict = apply_gita_to_plan(plan_dict, gita_payload)
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"failed to load/apply gita continuity: {exc}") from exc
        if use_director:
            try:
                director_payload = run_audio_director(ast=ast, llm_client=llm_client)
                plan_dict = merge_director_enrichment(plan_dict, director_payload)
            except Exception as exc:  # noqa: BLE001
                director_warning = f"director enrichment skipped: {exc}"
                print(f"  [warn] {director_warning}")
        if gita_path is not None and update_gita:
            try:
                gita_base = load_gita(gita_path) if gita_path.is_file() else {}
                gita_next = update_gita_from_plan(
                    gita_base,
                    plan_dict,
                    chapter_slug=input_path.stem,
                )
                save_gita(gita_path, gita_next)
                print(f"  Gita Continuity -> {gita_path}")
            except Exception as exc:  # noqa: BLE001
                gita_warning = f"gita update skipped: {exc}"
                print(f"  [warn] {gita_warning}")
        timeline_bytes = compile_timeline_json(
            plan_dict,
            project_type=project_type,
            narration_only=False,
        )
    else:
        from dsl.compiler import compile_timeline_json
        from story_processing.pipeline import process_story_json

        # Phase 1 — Narrative Plan (JSON bytes)
        plan_bytes = process_story_json(
            story_text, llm_client=llm_client, project_type=project_type,
        )
        plan_dict = orjson.loads(plan_bytes)
        timeline_bytes = compile_timeline_json(
            plan_dict,
            project_type=project_type,
            narration_only=narration_only,
        )

    # Write outputs
    output_dir.mkdir(parents=True, exist_ok=True)

    plan_path = output_dir / "narrative_plan.json"
    if project_type == "audio_drama" and is_script and use_director:
        plan_path.write_bytes(orjson.dumps(plan_dict, option=orjson.OPT_INDENT_2))
    else:
        plan_path.write_bytes(plan_bytes)

    timeline_path = output_dir / "draft_timeline.json"
    timeline_path.write_bytes(timeline_bytes)

    if project_type == "audio_drama" and is_script:
        by_severity: dict[str, int] = {}
        by_code: dict[str, int] = {}
        for item in script_diagnostics:
            sev = str(item.get("severity", "warning"))
            code = str(item.get("code", "unknown"))
            by_severity[sev] = by_severity.get(sev, 0) + 1
            by_code[code] = by_code.get(code, 0) + 1
        warnings_payload = {
            "summary": {
                "count": len(script_diagnostics),
                "by_severity": by_severity,
                "by_code": by_code,
            },
            "diagnostics": script_diagnostics,
        }
        if director_warning:
            warnings_payload["director_warning"] = director_warning
        if gita_warning:
            warnings_payload["gita_warning"] = gita_warning
        warnings_path = output_dir / "script_warnings.json"
        warnings_path.write_text(
            json.dumps(warnings_payload, indent=2),
            encoding="utf-8",
        )
        print(f"  Script Warnings -> {warnings_path}")
        if use_director:
            director_path = output_dir / "audio_director.json"
            director_path.write_text(
                json.dumps(director_payload or {"scene_enrichment": [], "global_notes": []}, indent=2),
                encoding="utf-8",
            )
            print(f"  Audio Director  -> {director_path}")

    print(f"  Narrative Plan  -> {plan_path}")
    print(f"  Draft Timeline  -> {timeline_path}")
    if fast_audiobook:
        tl = orjson.loads(timeline_bytes)
        st = tl.get("settings", {})
        print(
            "  [audiobook fast-path] "
            f"chars={st.get('source_character_count')} "
            f"words={st.get('source_word_count')} "
            f"est_narration_s~{st.get('estimated_narration_seconds')}",
        )


# ---------------------------------------------------------------------------
# LLM client resolution
# ---------------------------------------------------------------------------

_OPENAI_PREFIXES = ("gpt-", "o1-", "o3-", "o4-", "o1", "o3", "o4")


def _build_single_client(model: str) -> object:
    """Instantiate one LLM client based on model-name prefix."""
    import os

    if model.startswith(_OPENAI_PREFIXES):
        from story_processing.ai.llm_client import OpenAIClient

        api_key = os.environ.get("OPENAI_API_KEY", "")
        return OpenAIClient(api_key=api_key, model=model)

    if model.startswith("gemini"):
        from story_processing.ai.llm_client import GeminiClient

        return GeminiClient(model=model)

    from story_processing.ai.llm_client import LocalLLMClient

    return LocalLLMClient(model=model)


def resolve_llm_client(
    model: str | None,
    no_llm: bool,
    fallback_model: str | None = None,
) -> object | None:
    """Map CLI flags to the appropriate :class:`LLMClient` (or *None*).

    Returns ``None`` when *no_llm* is ``True``.
    Otherwise selects the backend by model-name prefix:

    - ``gpt-*`` / ``o1*`` / ``o3*`` / ``o4*`` → :class:`OpenAIClient`
    - ``gemini*``                               → :class:`GeminiClient`
    - anything else                             → :class:`LocalLLMClient`

    When *fallback_model* is given, wraps the primary in a
    :class:`FallbackLLMClient` that tries a secondary provider on failure.
    """
    if no_llm:
        print("  [info] --no-llm: running heuristic-only mode.")
        return None

    model = model or "gemini-2.0-flash"
    primary = _build_single_client(model)
    print(f"  [info] Primary LLM client ready ({type(primary).__name__}, model={model}).")

    if fallback_model:
        from story_processing.ai.llm_client import FallbackLLMClient

        fallback = _build_single_client(fallback_model)
        print(f"  [info] Fallback LLM client ready ({type(fallback).__name__}, model={fallback_model}).")
        return FallbackLLMClient(primary, fallback)

    return primary


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_process(args: argparse.Namespace) -> int:
    """Handle ``audstories process``."""
    input_path = Path(args.input)
    if not input_path.is_file():
        print(f"error: input file not found: {input_path}", file=sys.stderr)
        return 1

    output_dir = Path(args.output)

    project_type = getattr(args, "project_type", "audio_drama")
    narration_only = bool(getattr(args, "narration_only", False))
    use_director = bool(getattr(args, "director", False) and not getattr(args, "no_director", False))
    gita_path = Path(args.gita).resolve() if getattr(args, "gita", None) else None
    update_gita = bool(getattr(args, "update_gita", False))
    fast_audiobook = project_type == "audiobook" and narration_only

    llm_client = None
    if not fast_audiobook:
        try:
            llm_client = resolve_llm_client(
                args.model, args.no_llm,
                fallback_model=getattr(args, "fallback_model", None),
            )
        except Exception as exc:
            print(f"error: failed to initialise LLM client: {exc}", file=sys.stderr)
            return 1
    else:
        print("  [info] narration-only audiobook: skipping LLM / NLP story pipeline.")
    print(
        f"\nProcessing: {input_path}  "
        f"[project_type={project_type}, narration_only={narration_only}]",
    )
    try:
        run_single_file(
            input_path, output_dir, llm_client,
            project_type=project_type,
            narration_only=narration_only,
            use_director=use_director,
            gita_path=gita_path,
            update_gita=update_gita,
        )
    except Exception as exc:
        print(f"error: processing failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if llm_client is not None and hasattr(llm_client, "close"):
            llm_client.close()

    print("\nDone.")
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    """Handle ``audstories batch``."""
    input_dir = Path(args.input)
    if not input_dir.is_dir():
        print(f"error: input directory not found: {input_dir}", file=sys.stderr)
        return 1

    if getattr(args, "project_type", "audio_drama") == "audio_drama":
        files = sorted([*input_dir.glob("*.fountain"), *input_dir.glob("*.txt")])
    else:
        files = sorted(input_dir.glob("*.txt"))
    if not files:
        print(f"error: no input files found in {input_dir}", file=sys.stderr)
        return 1

    output_root = Path(args.output)

    project_type = getattr(args, "project_type", "audio_drama")
    narration_only = bool(getattr(args, "narration_only", False))
    use_director = bool(getattr(args, "director", False) and not getattr(args, "no_director", False))
    gita_path = Path(args.gita).resolve() if getattr(args, "gita", None) else None
    update_gita = bool(getattr(args, "update_gita", False))
    fast_audiobook = project_type == "audiobook" and narration_only

    llm_client = None
    if not fast_audiobook:
        try:
            llm_client = resolve_llm_client(
                args.model, args.no_llm,
                fallback_model=getattr(args, "fallback_model", None),
            )
        except Exception as exc:
            print(f"error: failed to initialise LLM client: {exc}", file=sys.stderr)
            return 1
    else:
        print("  [info] narration-only audiobook batch: skipping LLM / NLP pipeline.")

    print(f"\nBatch processing {len(files)} file(s) from: {input_dir}\n")

    succeeded: list[str] = []
    failed: list[tuple[str, str]] = []

    try:
        for file_path in files:
            stem = file_path.stem
            file_output_dir = output_root / stem

            print(f"  [{len(succeeded) + len(failed) + 1}/{len(files)}] {file_path.name}")
            try:
                run_single_file(
                    file_path, file_output_dir, llm_client,
                    project_type=project_type,
                    narration_only=narration_only,
                    use_director=use_director,
                    gita_path=gita_path,
                    update_gita=update_gita,
                )
                succeeded.append(file_path.name)
            except Exception as exc:
                print(f"    FAILED: {exc}", file=sys.stderr)
                failed.append((file_path.name, str(exc)))
    finally:
        if llm_client is not None and hasattr(llm_client, "close"):
            llm_client.close()

    # Summary
    print(f"\n{'=' * 50}")
    print(f"  Batch complete: {len(succeeded)} succeeded, {len(failed)} failed")
    if failed:
        print("\n  Failed files:")
        for name, reason in failed:
            print(f"    - {name}: {reason}")
    print()

    return 1 if failed else 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="audstories",
        description="Aud-Stories: convert stories into audio-storytelling timelines.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # -- process -------------------------------------------------------------
    p_process = subparsers.add_parser(
        "process",
        help="Process a single story file.",
    )
    p_process.add_argument(
        "--input", required=True,
        help="Path to the input story text file.",
    )
    p_process.add_argument(
        "--output", default=".",
        help="Output directory for JSON results (default: current directory).",
    )

    model_group = p_process.add_mutually_exclusive_group()
    model_group.add_argument(
        "--model", default=None,
        help="LLM model name (default: gemini-2.0-flash). "
             "Prefix determines backend: gpt-*/o1/o3/o4 -> OpenAI, "
             "gemini* -> Gemini, other -> local Ollama.",
    )
    model_group.add_argument(
        "--no-llm", action="store_true", default=False,
        help="Run in heuristic-only mode (no LLM calls).",
    )
    p_process.add_argument(
        "--fallback-model", default=None,
        help="Secondary LLM model used when the primary fails "
             "(e.g. --model gemini-2.0-flash --fallback-model gpt-4o-mini).",
    )
    p_process.add_argument(
        "--project-type", default="audio_drama",
        choices=["audiobook", "audio_drama"],
        help="AudioBook (1 narrator, no SFX) or AudioDrama (characters, SFX). "
             "Default: audio_drama.",
    )
    p_process.add_argument(
        "--narration-only",
        action="store_true",
        default=False,
        help="With --project-type audiobook: voice track only in the draft "
             "(no music, ambience, or SFX). Ignored for audio_drama.",
    )
    p_process.add_argument(
        "--director",
        action="store_true",
        default=False,
        help="Enable optional LLM Audio Director enrichment for .fountain drama scripts.",
    )
    p_process.add_argument(
        "--no-director",
        action="store_true",
        default=False,
        help="Explicitly disable director enrichment even if defaults change later.",
    )
    p_process.add_argument(
        "--gita",
        default=None,
        help="Optional path to gita.json continuity file.",
    )
    p_process.add_argument(
        "--update-gita",
        action="store_true",
        default=False,
        help="Update gita continuity from the generated narrative plan.",
    )

    p_process.set_defaults(func=cmd_process)

    # -- batch ---------------------------------------------------------------
    p_batch = subparsers.add_parser(
        "batch",
        help="Batch-process all .txt files in a directory.",
    )
    p_batch.add_argument(
        "--input", required=True,
        help="Directory containing .txt story files.",
    )
    p_batch.add_argument(
        "--output", default="./out",
        help="Root output directory (default: ./out). "
             "Each story gets a sub-directory named after its file stem.",
    )

    batch_model_group = p_batch.add_mutually_exclusive_group()
    batch_model_group.add_argument(
        "--model", default=None,
        help="LLM model name (default: gemini-2.0-flash).",
    )
    batch_model_group.add_argument(
        "--no-llm", action="store_true", default=False,
        help="Run in heuristic-only mode (no LLM calls).",
    )
    p_batch.add_argument(
        "--fallback-model", default=None,
        help="Secondary LLM model used when the primary fails.",
    )
    p_batch.add_argument(
        "--project-type", default="audio_drama",
        choices=["audiobook", "audio_drama"],
        help="AudioBook (1 narrator, no SFX) or AudioDrama (characters, SFX). "
             "Default: audio_drama.",
    )
    p_batch.add_argument(
        "--narration-only",
        action="store_true",
        default=False,
        help="With --project-type audiobook: fast text-only path per file.",
    )
    p_batch.add_argument(
        "--director",
        action="store_true",
        default=False,
        help="Enable optional LLM Audio Director enrichment for .fountain drama scripts.",
    )
    p_batch.add_argument(
        "--no-director",
        action="store_true",
        default=False,
        help="Explicitly disable director enrichment.",
    )
    p_batch.add_argument(
        "--gita",
        default=None,
        help="Optional path to gita.json continuity file.",
    )
    p_batch.add_argument(
        "--update-gita",
        action="store_true",
        default=False,
        help="Update gita continuity from generated narrative plans.",
    )

    p_batch.set_defaults(func=cmd_batch)

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entry point — registered as ``audstories`` console script."""
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = _build_parser()
    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
