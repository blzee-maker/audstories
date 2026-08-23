#!/usr/bin/env python3
"""Interactive book project CLI — metadata capture, chapter text, pipeline steps.

Projects store ``chapters`` (title, slug, file) and ``active_chapter_slug`` in
``book_metadata.json``. Legacy single-chapter fields are still read and merged
on load; new writes keep legacy fields in sync with the active chapter.

Audiobook credits (optional overrides in ``book_metadata.json`` under ``credits``)::

    "credits": {
      "voice_name": "…",
      "tts_provider": "google",
      "provider_line": "Google AI",
      "opening_text": null,
      "closing_text": null
    }

Set ``opening_text`` / ``closing_text`` to a string to replace the default templates;
omit or null uses built-in wording from book title, writer, and provider.

Examples::

    python book_cli.py init
    python book_cli.py credits --project-id my_book   # opening_credits.wav + ending_credits.wav
    python book_cli.py add-chapter --project-id my_book
    python book_cli.py list-chapters --project-id my_book
    python book_cli.py set-chapter --project-id my_book --chapter ch_02
    python book_cli.py stage1 --project-id my_book
    python book_cli.py stage1 --project-id my_book --chapter ch_02
    python book_cli.py synthesize --project-id my_book
    python book_cli.py resume --project-id my_book
    python book_cli.py run --project-id my_book   # stage1 + synthesize + resume
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv


_REPO_ROOT = Path(__file__).resolve().parent
_DEFAULT_PROJECTS = _REPO_ROOT / "workspace" / "projects"
_SAFE_PROJECT_ID = re.compile(r"[^a-zA-Z0-9_-]+")


def _sanitize_project_id(project_id: str) -> str:
    cleaned = _SAFE_PROJECT_ID.sub("_", project_id.strip())
    cleaned = cleaned.strip("._-")
    # Lower-cased so slugs are stable on case-sensitive filesystems: a project
    # created as "Episode Two" must resolve identically on Windows and Linux.
    # All three copies of this helper (book_cli, drama_cli, run_pipeline) must
    # agree, or a project created by one will not be found by another.
    return cleaned.lower() or "untitled_project"


def _ensure_import_path() -> None:
    # Shared engine-path shim (see engine_paths.py for why it is required).
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from engine_paths import ensure_engine_paths

    ensure_engine_paths()


def _project_paths(project_id: str, projects_root: Path) -> tuple[Path, Path, Path, Path]:
    safe = _sanitize_project_id(project_id)
    root = (projects_root / safe).resolve()
    return root, root / "assets", root / "output", root / "chapters"


def _read_book_metadata(project_root: Path) -> dict:
    p = project_root / "book_metadata.json"
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _write_book_metadata(project_root: Path, meta: dict) -> None:
    (project_root / "book_metadata.json").write_text(
        json.dumps(meta, indent=2),
        encoding="utf-8",
    )


def _sync_legacy_chapter_fields(meta: dict) -> None:
    """Mirror the active chapter into legacy ``chapter_*`` keys for older readers."""
    active = str(meta.get("active_chapter_slug", "")).strip()
    chapters = meta.get("chapters")
    if not isinstance(chapters, list) or not chapters or not active:
        return
    for c in chapters:
        if isinstance(c, dict) and str(c.get("slug", "")).strip() == active:
            meta["chapter_title"] = c.get("title")
            meta["chapter_slug"] = c.get("slug")
            meta["chapter_file"] = str(c.get("file", "")).replace("\\", "/")
            return


def _normalize_book_metadata(meta: dict) -> dict:
    """Return a copy with ``chapters`` + ``active_chapter_slug`` populated."""
    out = dict(meta)
    chapters_in = out.get("chapters")
    if not isinstance(chapters_in, list) or not chapters_in:
        cf = str(out.get("chapter_file") or "").strip().replace("\\", "/")
        ct = str(out.get("chapter_title") or "").strip()
        cs = str(out.get("chapter_slug") or "").strip()
        if not cs and cf:
            cs = Path(cf).stem
        if not cs:
            cs = "chapter_01"
        if not ct:
            ct = cs
        rel = cf if cf else f"chapters/{cs}.txt"
        out["chapters"] = [{"title": ct, "slug": cs, "file": rel}]
    else:
        fixed: list[dict] = []
        for c in chapters_in:
            if not isinstance(c, dict):
                continue
            title = str(c.get("title") or "").strip()
            slug = str(c.get("slug") or "").strip()
            file = str(c.get("file") or "").strip().replace("\\", "/")
            if not slug and file:
                slug = Path(file).stem
            if not slug:
                continue
            if not title:
                title = slug
            if not file:
                file = f"chapters/{slug}.txt"
            fixed.append({"title": title, "slug": slug, "file": file})
        out["chapters"] = fixed

    if not out["chapters"]:
        cf = str(out.get("chapter_file") or "").strip().replace("\\", "/")
        ct = str(out.get("chapter_title") or "").strip()
        cs = str(out.get("chapter_slug") or "").strip()
        if not cs and cf:
            cs = Path(cf).stem
        if not cs:
            cs = "chapter_01"
        if not ct:
            ct = cs
        rel = cf if cf else f"chapters/{cs}.txt"
        out["chapters"] = [{"title": ct, "slug": cs, "file": rel}]

    slugs = {str(c["slug"]) for c in out["chapters"]}
    active = str(out.get("active_chapter_slug", "")).strip()
    if not active or active not in slugs:
        out["active_chapter_slug"] = out["chapters"][0]["slug"]
    _sync_legacy_chapter_fields(out)
    return out


def _resolve_chapter_story(
    meta: dict,
    project_root: Path,
    chapter_slug: str | None,
) -> tuple[Path, str]:
    """Return absolute story path and resolved slug. ``meta`` must be normalized."""
    chapters = meta.get("chapters") or []
    if not chapters:
        raise ValueError("book_metadata has no chapters")

    want = (chapter_slug or "").strip() or str(meta.get("active_chapter_slug", "")).strip()
    if not want:
        want = str(chapters[0].get("slug", "")).strip()

    for c in chapters:
        if str(c.get("slug", "")).strip() == want:
            rel = str(c.get("file", "")).strip().replace("\\", "/")
            story = (project_root / rel).resolve()
            return story, want

    known = ", ".join(sorted(str(c.get("slug", "")) for c in chapters))
    raise ValueError(f"unknown chapter slug {want!r}; known: {known}")


def _load_normalized_metadata(project_root: Path) -> dict:
    raw = _read_book_metadata(project_root)
    if not raw:
        raise ValueError(f"missing book_metadata.json under {project_root}")
    return _normalize_book_metadata(raw)


def cmd_init(args: argparse.Namespace) -> int:
    """Interactive wizard: book name, format, writer, chapter title, chapter text."""
    print("=== New book project ===\n")
    book_name = input("Project name (book title): ").strip() or "Untitled"
    fmt = input("Format — [a] Audiobook  [b] Audio Drama (default a): ").strip().lower()
    project_type = "audio_drama" if fmt.startswith("b") else "audiobook"
    writer = input("Writer name: ").strip() or "Unknown"
    chapter_title = input("Chapter 1 name: ").strip() or "Chapter 1"
    chapter_slug = _sanitize_project_id(chapter_title)[:60]

    project_id = _sanitize_project_id(book_name)
    # Honour --projects-root rather than always writing to the real workspace.
    projects_root = Path(getattr(args, "projects_root", None) or _DEFAULT_PROJECTS)
    project_root, assets, out_dir, chapters = _project_paths(project_id, projects_root)

    if project_root.exists() and any(project_root.iterdir()):
        if getattr(args, "yes", False):
            print(f"Folder already exists: {project_root}\nOverwriting metadata (--yes).")
        elif not sys.stdin.isatty():
            print(
                f"Folder already exists: {project_root}\n"
                "Refusing to overwrite in non-interactive mode. Re-run with --yes to overwrite.",
                file=sys.stderr,
            )
            return 1
        else:
            overwrite = input(
                f"Folder already exists: {project_root}\nOverwrite metadata only? [y/N]: ",
            ).strip().lower()
            if overwrite != "y":
                print("Aborted.")
                return 1

    narration_only = project_type == "audiobook"
    print(
        "\nPaste chapter text below. Finish with a line containing only END "
        "(then press Enter).\n",
    )
    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "END":
            break
        lines.append(line)
    body = "\n".join(lines).strip()
    if not body:
        print("error: no chapter text provided.", file=sys.stderr)
        return 1

    chapters.mkdir(parents=True, exist_ok=True)
    assets.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    chapter_rel = f"chapters/{chapter_slug}.txt"
    chapter_path = project_root / chapter_rel
    chapter_path.write_text(body, encoding="utf-8")

    chapter_rel_norm = chapter_rel.replace("\\", "/")
    delivery_profile = "audiobook_retail" if project_type == "audiobook" else "audio_drama_default"
    meta: dict = {
        "book_title": book_name,
        "project_id": project_id,
        "writer_name": writer,
        "project_type": project_type,
        "narration_only": narration_only,
        "delivery_profile": delivery_profile,
        "chapters": [
            {
                "title": chapter_title,
                "slug": chapter_slug,
                "file": chapter_rel_norm,
            },
        ],
        "active_chapter_slug": chapter_slug,
        "chapter_title": chapter_title,
        "chapter_slug": chapter_slug,
        "chapter_file": chapter_rel_norm,
    }
    if project_type == "audiobook":
        voice_credits = (
            input("Narrator name for ending credits (display only, Enter=AI Narrator): ").strip()
            or "AI Narrator"
        )
        meta["credits"] = {
            "voice_name": voice_credits,
            "tts_provider": "google",
        }
    (project_root / "book_metadata.json").write_text(
        json.dumps(meta, indent=2),
        encoding="utf-8",
    )
    print(f"\nCreated project at: {project_root}")
    print(f"  Chapter file: {chapter_path}")
    print("  Next: python book_cli.py stage1 --project-id", project_id)
    if narration_only:
        print("            python book_cli.py synthesize --project-id", project_id)
        print("            python book_cli.py credits --project-id", project_id)
    print("            python book_cli.py resume --project-id", project_id)
    return 0


def cmd_add_chapter(_args: argparse.Namespace) -> int:
    """Append a chapter file and metadata entry; sets it active."""
    project_root, _, _, chapters_dir = _project_paths(
        _args.project_id,
        Path(_args.projects_root),
    )
    if not (project_root / "book_metadata.json").is_file():
        print(f"error: no book_metadata.json at {project_root}", file=sys.stderr)
        return 1

    meta = _load_normalized_metadata(project_root)
    existing = {str(c["slug"]) for c in meta["chapters"]}

    title = input("Chapter title: ").strip() or "Untitled"
    slug_in = input(f"Slug (default from title, e.g. {_sanitize_project_id(title)[:60]}): ").strip()
    slug = _sanitize_project_id(slug_in or title)[:60] or "chapter"
    if slug in existing:
        print(f"error: chapter slug already exists: {slug}", file=sys.stderr)
        return 1

    print(
        "\nPaste chapter text below. Finish with a line containing only END "
        "(then press Enter).\n",
    )
    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "END":
            break
        lines.append(line)
    body = "\n".join(lines).strip()
    if not body:
        print("error: no chapter text provided.", file=sys.stderr)
        return 1

    chapters_dir.mkdir(parents=True, exist_ok=True)
    chapter_rel = f"chapters/{slug}.txt"
    chapter_path = project_root / chapter_rel
    chapter_path.write_text(body, encoding="utf-8")

    meta["chapters"].append({"title": title, "slug": slug, "file": chapter_rel.replace("\\", "/")})
    meta["active_chapter_slug"] = slug
    _sync_legacy_chapter_fields(meta)
    _write_book_metadata(project_root, meta)
    print(f"Added chapter {slug!r} at {chapter_path}")
    print("  Next: python book_cli.py stage1 --project-id", _sanitize_project_id(_args.project_id))
    return 0


def cmd_list_chapters(_args: argparse.Namespace) -> int:
    project_root, _, _, _ = _project_paths(_args.project_id, Path(_args.projects_root))
    if not (project_root / "book_metadata.json").is_file():
        print(f"error: no book_metadata.json at {project_root}", file=sys.stderr)
        return 1
    meta = _load_normalized_metadata(project_root)
    active = str(meta.get("active_chapter_slug", "")).strip()
    print(f"Project: {meta.get('project_id', '')} - active: {active or '(none)'}")
    for c in meta["chapters"]:
        mark = " *" if str(c.get("slug")) == active else ""
        print(f"  {c.get('slug')}: {c.get('title')}  ({c.get('file')}){mark}")
    return 0


def cmd_set_chapter(args: argparse.Namespace) -> int:
    project_root, _, _, _ = _project_paths(args.project_id, Path(args.projects_root))
    if not (project_root / "book_metadata.json").is_file():
        print(f"error: no book_metadata.json at {project_root}", file=sys.stderr)
        return 1
    meta = _load_normalized_metadata(project_root)
    want = str(args.chapter).strip()
    slugs = {str(c["slug"]) for c in meta["chapters"]}
    if want not in slugs:
        print(
            f"error: no chapter with slug {want!r}; known: {', '.join(sorted(slugs))}",
            file=sys.stderr,
        )
        return 1
    meta["active_chapter_slug"] = want
    _sync_legacy_chapter_fields(meta)
    _write_book_metadata(project_root, meta)
    print(f"Active chapter set to {want!r}.")
    return 0


def _run_pipeline(argv: list[str]) -> int:
    script = _REPO_ROOT / "run_pipeline.py"
    cmd = [sys.executable, str(script), *argv]
    return subprocess.call(cmd, cwd=str(_REPO_ROOT))


def cmd_stage1(args: argparse.Namespace) -> int:
    project_root, _, _, _ = _project_paths(args.project_id, Path(args.projects_root))
    try:
        meta = _load_normalized_metadata(project_root)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    ch_arg = getattr(args, "chapter", None)
    chapter_slug = str(ch_arg).strip() if ch_arg else None
    try:
        story, resolved_slug = _resolve_chapter_story(meta, project_root, chapter_slug)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not story.is_file():
        print(f"error: chapter file not found: {story}", file=sys.stderr)
        return 1

    argv = [
        "--story",
        str(story),
        "--project-id",
        _sanitize_project_id(args.project_id),
        "--project-type",
        str(meta.get("project_type", "audiobook")),
        "--projects-root",
        str(Path(args.projects_root).resolve()),
    ]
    if meta.get("narration_only") or args.narration_only:
        argv.append("--narration-only")
    rc = _run_pipeline(argv)
    if rc == 0:
        meta["active_chapter_slug"] = resolved_slug
        _sync_legacy_chapter_fields(meta)
        _write_book_metadata(project_root, meta)
    return rc


def cmd_synthesize(args: argparse.Namespace) -> int:
    _ensure_import_path()
    from narration_tts.google_tts import fill_voice_requirements_from_draft

    project_root, library_root, out_dir, _ = _project_paths(
        args.project_id,
        Path(args.projects_root),
    )
    draft = out_dir / "draft_timeline.json"
    if not draft.is_file():
        print(f"error: run stage1 first — missing {draft}", file=sys.stderr)
        return 1
    try:
        n = fill_voice_requirements_from_draft(
            draft,
            library_root,
            skip_existing=not args.force,
        )
    except Exception as exc:
        print(f"error: TTS failed: {exc}", file=sys.stderr)
        return 1
    print(f"Synthesized {n} new voice clip(s).")
    if n > 0:
        print(
            f"Clip WAVs live under {library_root / 'voice'} (not output/generated). "
            "Run resume to render the full mix to output/generated/<chapter>.wav.",
        )
    if n == 0 and not args.force:
        print(
            "Hint: after a new chapter or re-run stage1, clip folders may still contain "
            "an older narration_tts.wav; use synthesize --force to regenerate.",
        )
    return 0


def cmd_credits(args: argparse.Namespace) -> int:
    """Synthesize opening_credits.wav and ending_credits.wav from book_metadata (audiobook only)."""
    _ensure_import_path()
    from narration_tts.credits_text import (
        closing_credits_text,
        ensure_credits_defaults,
        opening_credits_text,
    )
    from narration_tts.google_tts import synthesize_text_to_linear16_wav

    project_root, _, out_dir, _ = _project_paths(
        args.project_id,
        Path(args.projects_root),
    )
    try:
        meta = _load_normalized_metadata(project_root)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if str(meta.get("project_type", "")).lower() != "audiobook":
        print(
            "error: credits apply only to audiobook projects (project_type=audiobook).",
            file=sys.stderr,
        )
        return 1

    ensure_credits_defaults(meta)
    gen = out_dir / "generated"
    gen.mkdir(parents=True, exist_ok=True)
    opening_wav = gen / "opening_credits.wav"
    ending_wav = gen / "ending_credits.wav"

    force = bool(args.force)
    skip_open = (
        not force
        and opening_wav.is_file()
        and opening_wav.stat().st_size > 0
    )
    skip_end = (
        not force
        and ending_wav.is_file()
        and ending_wav.stat().st_size > 0
    )
    if skip_open and skip_end:
        print(
            "Opening and ending credits WAVs already exist — skipping TTS. "
            "Applying audiobook_retail preset and analysis. Use --force to re-synthesize speech.",
        )

    open_text = opening_credits_text(meta)
    close_text = closing_credits_text(meta)

    if not (skip_open and skip_end):
        try:
            if not skip_open:
                synthesize_text_to_linear16_wav(open_text, opening_wav)
                print(f"Wrote {opening_wav}")
            else:
                print(f"Skipped (exists): {opening_wav}")
            if not skip_end:
                synthesize_text_to_linear16_wav(close_text, ending_wav)
                print(f"Wrote {ending_wav}")
            else:
                print(f"Skipped (exists): {ending_wav}")
        except Exception as exc:
            print(f"error: credits TTS failed: {exc}", file=sys.stderr)
            return 1

    try:
        from narration_tts.audiobook_delivery_wav import apply_audiobook_retail_to_wav

        for path in (opening_wav, ending_wav):
            if path.is_file() and path.stat().st_size > 0:
                apply_audiobook_retail_to_wav(path, repo_root=_REPO_ROOT)
                print(f"Applied audiobook_retail preset (48 kHz, LUFS, peak): {path.name}")
    except Exception as exc:
        print(f"error: credits delivery mastering failed: {exc}", file=sys.stderr)
        return 1

    _ensure_import_path()
    from run_pipeline import print_wav_output_analysis

    sep = "=" * 60
    print(f"\n{sep}")
    print("  CREDITS — OUTPUT AUDIO ANALYSIS")
    print(sep)
    for path, label in (
        (opening_wav, "Opening credits"),
        (ending_wav, "Ending credits"),
    ):
        if path.is_file() and path.stat().st_size > 0:
            print()
            print_wav_output_analysis(
                path,
                section_title=f"{label}",
                include_publish_notes=True,
            )
    print(sep)
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    argv = [
        "--resume",
        "--project-id",
        _sanitize_project_id(args.project_id),
        "--projects-root",
        str(Path(args.projects_root).resolve()),
    ]
    meta = _read_book_metadata(_project_paths(args.project_id, Path(args.projects_root))[0])
    if meta.get("project_type"):
        argv.extend(["--project-type", str(meta["project_type"])])
    if meta.get("narration_only") or args.narration_only:
        argv.append("--narration-only")
    return _run_pipeline(argv)


def cmd_run(args: argparse.Namespace) -> int:
    rc = cmd_stage1(args)
    if rc != 0:
        return rc
    meta = _read_book_metadata(_project_paths(args.project_id, Path(args.projects_root))[0])
    if meta.get("narration_only") or args.narration_only:
        rc = cmd_synthesize(args)
        if rc != 0:
            return rc
    return cmd_resume(args)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="book_cli",
        description="Interactive book project helper for the AS pipeline.",
    )
    p.add_argument(
        "--projects-root",
        default=str(_DEFAULT_PROJECTS),
        help="Path to workspace/projects (default: <repo>/workspace/projects).",
    )
    sub = p.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Prompt for book metadata and chapter text.")
    p_init.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Overwrite an existing project's metadata without prompting.",
    )
    p_init.set_defaults(func=cmd_init)

    def add_pid(sp: argparse.ArgumentParser) -> None:
        sp.add_argument(
            "--project-id",
            required=True,
            help="Filesystem-safe project id (same as after init).",
        )
        sp.add_argument(
            "--narration-only",
            action="store_true",
            help="Force --narration-only for pipeline steps.",
        )

    p_add = sub.add_parser(
        "add-chapter",
        help="Add another chapter (text file + metadata); sets it as active.",
    )
    add_pid(p_add)
    p_add.set_defaults(func=cmd_add_chapter)

    p_list = sub.add_parser("list-chapters", help="List chapters and the active slug.")
    add_pid(p_list)
    p_list.set_defaults(func=cmd_list_chapters)

    p_set = sub.add_parser("set-chapter", help="Set active chapter slug for stage1/resume output naming.")
    add_pid(p_set)
    p_set.add_argument(
        "--chapter",
        required=True,
        metavar="SLUG",
        help="Chapter slug as shown by list-chapters.",
    )
    p_set.set_defaults(func=cmd_set_chapter)

    p_s1 = sub.add_parser("stage1", help="Run Engine 1 + asset scaffold.")
    add_pid(p_s1)
    p_s1.add_argument(
        "--chapter",
        metavar="SLUG",
        help="Chapter slug (default: active chapter in book_metadata.json).",
    )
    p_s1.set_defaults(func=cmd_stage1)

    p_syn = sub.add_parser("synthesize", help="Google TTS for voice clips (audiobook).")
    add_pid(p_syn)
    p_syn.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing narration_tts.wav (use after stage1 for a new chapter; same clip paths skip by default).",
    )
    p_syn.set_defaults(func=cmd_synthesize)

    p_cr = sub.add_parser(
        "credits",
        help="TTS for opening_credits.wav + ending_credits.wav (audiobook; text from book_metadata templates or overrides).",
    )
    add_pid(p_cr)
    p_cr.add_argument(
        "--force",
        action="store_true",
        help="Regenerate even when credit WAVs already exist.",
    )
    p_cr.set_defaults(func=cmd_credits)

    p_res = sub.add_parser(
        "resume",
        help="Run Stage 2: resolve + render (output/generated/<chapter>.wav when book_metadata exists).",
    )
    add_pid(p_res)
    p_res.set_defaults(func=cmd_resume)

    p_run = sub.add_parser("run", help="stage1, then synthesize (if narration-only), then resume.")
    add_pid(p_run)
    p_run.add_argument(
        "--chapter",
        metavar="SLUG",
        help="Chapter slug for stage1 (default: active chapter in book_metadata.json).",
    )
    p_run.add_argument("--force", action="store_true", help="Passed to synthesize.")
    p_run.set_defaults(func=cmd_run)

    return p


def main() -> int:
    load_dotenv(_REPO_ROOT / ".env")
    parser = _build_parser()
    args = parser.parse_args()
    # Normalize projects root to .../workspace/projects
    pr = Path(args.projects_root)
    if pr.name != "projects":
        args.projects_root = str((pr / "projects").resolve())
    else:
        args.projects_root = str(pr.resolve())
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
