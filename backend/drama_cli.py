#!/usr/bin/env python3
"""Interactive audio-drama project CLI.

This CLI mirrors the existing book workflow but keeps commands focused on
audio-drama setup and pipeline orchestration.

Examples::

    python drama_cli.py init
    python drama_cli.py stage1 --project-id my_drama
    python drama_cli.py resume --project-id my_drama
    python drama_cli.py run --project-id my_drama
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
_FOUNTAIN_TEMPLATE = """SCENE ONE
INT. APARTMENT - NIGHT
Room tone. Distant city traffic.

PROTAGONIST (V.O.)
I should not have come back here.

PROTAGONIST
Hello?

A door creaks open.
"""


def _ensure_story_import_path() -> None:
    # Shared engine-path shim (see engine_paths.py for why it is required).
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from engine_paths import ensure_engine_paths

    ensure_engine_paths()


def _sanitize_project_id(project_id: str) -> str:
    cleaned = _SAFE_PROJECT_ID.sub("_", project_id.strip())
    cleaned = cleaned.strip("._-")
    return cleaned or "untitled_project"


def _project_paths(project_id: str, projects_root: Path) -> tuple[Path, Path, Path, Path]:
    safe = _sanitize_project_id(project_id)
    root = (projects_root / safe).resolve()
    return root, root / "assets", root / "output", root / "chapters"


def _read_project_metadata(project_root: Path) -> dict:
    path = project_root / "book_metadata.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_project_metadata(project_root: Path, payload: dict) -> None:
    (project_root / "book_metadata.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


def _gita_path(project_root: Path) -> Path:
    return project_root / "gita.json"


def _ensure_gita_for_project(project_root: Path, meta: dict) -> Path:
    _ensure_story_import_path()
    from story_processing.fountain.gita import default_gita, save_gita

    gita_path = _gita_path(project_root)
    if not gita_path.is_file():
        payload = default_gita(
            project_id=str(meta.get("project_id") or project_root.name),
            title=str(meta.get("book_title") or project_root.name),
            writer=str(meta.get("writer_name") or ""),
        )
        save_gita(gita_path, payload)
    return gita_path


def _normalize_project_metadata(meta: dict) -> dict:
    """Ensure drama metadata has chapters + active_chapter_slug."""
    out = dict(meta)
    chapters = out.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        cf = str(out.get("chapter_file") or "").strip().replace("\\", "/")
        ct = str(out.get("chapter_title") or "").strip() or "Episode 1"
        cs = str(out.get("chapter_slug") or "").strip() or _sanitize_project_id(ct)
        if not cs:
            cs = "episode_01"
        rel = cf if cf else f"chapters/{cs}.fountain"
        out["chapters"] = [{"title": ct, "slug": cs, "file": rel}]

    fixed: list[dict] = []
    for c in out.get("chapters", []):
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
            file = f"chapters/{slug}.fountain"
        if not file.lower().endswith(".fountain"):
            file = f"chapters/{slug}.fountain"
        fixed.append({"title": title, "slug": slug, "file": file})
    if not fixed:
        fixed = [{"title": "Episode 1", "slug": "episode_01", "file": "chapters/episode_01.fountain"}]
    out["chapters"] = fixed
    active = str(out.get("active_chapter_slug", "")).strip()
    slugs = {str(c["slug"]) for c in fixed}
    if not active or active not in slugs:
        out["active_chapter_slug"] = fixed[0]["slug"]
    for c in fixed:
        if c["slug"] == out["active_chapter_slug"]:
            out["chapter_title"] = c["title"]
            out["chapter_slug"] = c["slug"]
            out["chapter_file"] = c["file"]
            break
    return out


def _load_normalized_metadata(project_root: Path) -> dict:
    meta = _read_project_metadata(project_root)
    if not meta:
        raise ValueError(f"missing book_metadata.json under {project_root}")
    return _normalize_project_metadata(meta)


def _run_pipeline(argv: list[str]) -> int:
    cmd = [sys.executable, str(_REPO_ROOT / "run_pipeline.py"), *argv]
    return subprocess.call(cmd, cwd=str(_REPO_ROOT))


def cmd_init(args: argparse.Namespace) -> int:
    print("=== New audio drama project ===\n")
    title = input("Project name: ").strip() or "Untitled Drama"
    writer = input("Writer name: ").strip() or "Unknown"
    chapter_title = input("Episode/Chapter 1 title: ").strip() or "Episode 1"
    chapter_slug = _sanitize_project_id(chapter_title)[:60]
    project_id = _sanitize_project_id(title)

    # Honour --projects-root. This previously hardcoded _DEFAULT_PROJECTS, which
    # meant `init` always wrote to the real workspace even when the caller asked
    # for somewhere else - so the test suite created projects in workspace/projects
    # and then tripped over them on the next run.
    projects_root = Path(getattr(args, "projects_root", None) or _DEFAULT_PROJECTS)
    project_root, assets_root, out_root, chapters_root = _project_paths(project_id, projects_root)
    if project_root.exists() and any(project_root.iterdir()):
        if getattr(args, "yes", False):
            print(f"Folder already exists: {project_root}\nOverwriting metadata/chapter (--yes).")
        elif not sys.stdin.isatty():
            # Non-interactive (test, CI, or the API worker's subprocess): fail with a
            # usable message rather than blocking on a prompt nobody can answer.
            print(
                f"Folder already exists: {project_root}\n"
                "Refusing to overwrite in non-interactive mode. Re-run with --yes to overwrite.",
                file=sys.stderr,
            )
            return 1
        else:
            overwrite = input(
                f"Folder already exists: {project_root}\nOverwrite metadata/chapter only? [y/N]: ",
            ).strip().lower()
            if overwrite != "y":
                print("Aborted.")
                return 1

    if getattr(_args, "template", False):
        body = _FOUNTAIN_TEMPLATE.strip()
        print("Using built-in Fountain starter template.")
    else:
        print(
            "\nPaste your audio-drama script (Fountain format; "
            "see doc/AUDIO_DRAMA_SCRIPT_SPEC.md). "
            "End input with a line containing only END.\n",
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
        print("error: no text provided.", file=sys.stderr)
        return 1

    chapters_root.mkdir(parents=True, exist_ok=True)
    assets_root.mkdir(parents=True, exist_ok=True)
    out_root.mkdir(parents=True, exist_ok=True)

    chapter_rel = f"chapters/{chapter_slug}.fountain"
    chapter_path = project_root / chapter_rel
    chapter_path.write_text(body, encoding="utf-8")

    meta = {
        "book_title": title,
        "project_id": project_id,
        "writer_name": writer,
        "project_type": "audio_drama",
        "narration_only": False,
        "delivery_profile": "audio_drama_default",
        "chapters": [
            {
                "title": chapter_title,
                "slug": chapter_slug,
                "file": chapter_rel.replace("\\", "/"),
            },
        ],
        "active_chapter_slug": chapter_slug,
        "chapter_title": chapter_title,
        "chapter_slug": chapter_slug,
        "chapter_file": chapter_rel.replace("\\", "/"),
    }
    _write_project_metadata(project_root, meta)
    gita_path = _ensure_gita_for_project(project_root, meta)

    print(f"\nCreated audio drama project at: {project_root}")
    print(f"  Chapter file: {chapter_path}")
    print(f"  Gita file: {gita_path}")
    print("  Next:")
    print(f"    python drama_cli.py stage1 --project-id {project_id}")
    print(f"    python drama_cli.py resume --project-id {project_id}")
    return 0


def _resolve_story_from_metadata(project_root: Path, chapter_slug: str | None) -> tuple[Path, str]:
    meta = _load_normalized_metadata(project_root)
    chapters = meta.get("chapters", [])

    active = str(meta.get("active_chapter_slug", "")).strip()
    want = (chapter_slug or "").strip() or active or str(chapters[0].get("slug", "")).strip()
    for c in chapters:
        if not isinstance(c, dict):
            continue
        slug = str(c.get("slug", "")).strip()
        if slug != want:
            continue
        rel = str(c.get("file", "")).strip().replace("\\", "/")
        if not rel:
            rel = f"chapters/{slug}.fountain"
        return (project_root / rel).resolve(), slug
    known = ", ".join(sorted(str(c.get("slug", "")) for c in chapters if isinstance(c, dict)))
    raise ValueError(f"unknown chapter slug {want!r}; known: {known}")


def cmd_add_chapter(args: argparse.Namespace) -> int:
    project_root, _, _, chapters_dir = _project_paths(args.project_id, Path(args.projects_root))
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

    if getattr(args, "template", False):
        body = _FOUNTAIN_TEMPLATE.strip()
        print("Using built-in Fountain starter template.")
    else:
        print("\nPaste chapter script. Finish with a line containing only END.\n")
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
        print("error: no chapter script provided.", file=sys.stderr)
        return 1

    chapters_dir.mkdir(parents=True, exist_ok=True)
    chapter_rel = f"chapters/{slug}.fountain"
    chapter_path = project_root / chapter_rel
    chapter_path.write_text(body, encoding="utf-8")

    meta["chapters"].append({"title": title, "slug": slug, "file": chapter_rel.replace("\\", "/")})
    meta["active_chapter_slug"] = slug
    meta = _normalize_project_metadata(meta)
    _write_project_metadata(project_root, meta)
    print(f"Added chapter {slug!r} at {chapter_path}")
    return 0


def cmd_list_chapters(args: argparse.Namespace) -> int:
    project_root, _, _, _ = _project_paths(args.project_id, Path(args.projects_root))
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
        print(f"error: no chapter with slug {want!r}; known: {', '.join(sorted(slugs))}", file=sys.stderr)
        return 1
    meta["active_chapter_slug"] = want
    meta = _normalize_project_metadata(meta)
    _write_project_metadata(project_root, meta)
    print(f"Active chapter set to {want!r}.")
    return 0


def cmd_dry_run_parse(args: argparse.Namespace) -> int:
    project_root, _, _, _ = _project_paths(args.project_id, Path(args.projects_root))
    try:
        story, resolved_slug = _resolve_story_from_metadata(project_root, getattr(args, "chapter", None))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if not story.is_file():
        print(f"error: chapter file not found: {story}", file=sys.stderr)
        return 1

    _ensure_story_import_path()
    from story_processing.fountain.to_plan import process_script_bundle

    script_text = story.read_text(encoding="utf-8")
    plan_bytes, ast = process_script_bundle(script_text, project_type="audio_drama")
    plan = json.loads(plan_bytes.decode("utf-8"))
    scenes = plan.get("scenes", [])
    speakers = sorted(
        {
            sp
            for sc in scenes
            for sp in sc.get("structure", {}).get("speakers", [])
        }
    )
    preview = {
        "project_id": _sanitize_project_id(args.project_id),
        "chapter_slug": resolved_slug,
        "chapter_file": str(story),
        "scene_count": len(scenes),
        "speaker_count": len(speakers),
        "speakers": speakers,
        "warnings_count": len(ast.warnings),
        "diagnostics_count": len(ast.diagnostics),
        "scenes": [
            {
                "scene_id": sc.get("scene_id"),
                "heading": sc.get("structure", {}).get("scene_title"),
                "energy_level": sc.get("interpretation", {}).get("energy_level"),
                "primary_emotion": sc.get("interpretation", {}).get("primary_emotion"),
                "dialogue_turn_count": sc.get("signals", {}).get("dialogue_turn_count"),
                "sfx_count": len(sc.get("structure", {}).get("sfx_events", [])),
                "ambience": (sc.get("structure", {}).get("ambience_cue") or {}).get("primary_atmosphere"),
            }
            for sc in scenes
        ],
        "diagnostics": [
            {
                "line": d.line,
                "column": d.column,
                "code": d.code,
                "severity": d.severity,
                "message": d.message,
            }
            for d in ast.diagnostics
        ],
    }

    if args.json:
        print(json.dumps(preview, indent=2))
    else:
        print(f"Dry-run parse for project={preview['project_id']} chapter={preview['chapter_slug']}")
        print(
            f"  scenes={preview['scene_count']} speakers={preview['speaker_count']} "
            f"warnings={preview['warnings_count']}"
        )
        for sc in preview["scenes"]:
            print(
                f"  - {sc['heading']} | emotion={sc['primary_emotion']} "
                f"energy={sc['energy_level']} dialogue={sc['dialogue_turn_count']} "
                f"sfx={sc['sfx_count']} ambience={sc['ambience']}"
            )
    return 0


def cmd_gita_init(args: argparse.Namespace) -> int:
    project_root, _, _, _ = _project_paths(args.project_id, Path(args.projects_root))
    if not (project_root / "book_metadata.json").is_file():
        print(f"error: no book_metadata.json at {project_root}", file=sys.stderr)
        return 1
    meta = _load_normalized_metadata(project_root)
    gita_path = _ensure_gita_for_project(project_root, meta)
    print(f"Gita initialized at {gita_path}")
    return 0


def cmd_gita_show(args: argparse.Namespace) -> int:
    project_root, _, _, _ = _project_paths(args.project_id, Path(args.projects_root))
    if not (project_root / "book_metadata.json").is_file():
        print(f"error: no book_metadata.json at {project_root}", file=sys.stderr)
        return 1
    meta = _load_normalized_metadata(project_root)
    gita_path = _ensure_gita_for_project(project_root, meta)
    _ensure_story_import_path()
    from story_processing.fountain.gita import load_gita

    payload = load_gita(gita_path)
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0
    print(f"Gita: {gita_path}")
    print(f"  project_id={payload.get('project_id')} series={payload.get('series_title')}")
    print(f"  characters={len(payload.get('characters', {}))}")
    print(f"  locations={len(payload.get('locations', {}))}")
    print(f"  motifs={len(payload.get('sfx_motifs', {}))}")
    print(f"  episodes={len(payload.get('episodes', []))}")
    return 0


def cmd_gita_update(args: argparse.Namespace) -> int:
    project_root, _, _, _ = _project_paths(args.project_id, Path(args.projects_root))
    try:
        story, resolved_slug = _resolve_story_from_metadata(project_root, getattr(args, "chapter", None))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if not story.is_file():
        print(f"error: chapter file not found: {story}", file=sys.stderr)
        return 1
    meta = _load_normalized_metadata(project_root)
    gita_path = _ensure_gita_for_project(project_root, meta)
    _ensure_story_import_path()
    from story_processing.fountain.gita import load_gita, save_gita, update_gita_from_plan
    from story_processing.fountain.to_plan import process_script_json

    plan = json.loads(process_script_json(story.read_text(encoding="utf-8"), project_type="audio_drama").decode("utf-8"))
    gita = load_gita(gita_path)
    updated = update_gita_from_plan(gita, plan, chapter_slug=resolved_slug)
    save_gita(gita_path, updated)
    print(f"Gita updated from chapter {resolved_slug!r}: {gita_path}")
    return 0


def _ensure_narration_tts_import_path() -> None:
    # Shared engine-path shim (see engine_paths.py for why it is required).
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from engine_paths import ensure_engine_paths

    ensure_engine_paths()


def _draft_path_for_project(project_root: Path) -> Path:
    return project_root / "output" / "draft_timeline.json"


def cmd_voice_map(args: argparse.Namespace) -> int:
    project_root, assets_root, _, _ = _project_paths(args.project_id, Path(args.projects_root))
    if not (project_root / "book_metadata.json").is_file():
        print(f"error: no book_metadata.json at {project_root}", file=sys.stderr)
        return 1
    draft_path = _draft_path_for_project(project_root)
    if not draft_path.is_file():
        print(
            f"error: draft_timeline.json not found at {draft_path}; run stage1 first.",
            file=sys.stderr,
        )
        return 1

    meta = _load_normalized_metadata(project_root)
    gita_path = _ensure_gita_for_project(project_root, meta)

    _ensure_story_import_path()
    _ensure_narration_tts_import_path()
    from story_processing.fountain.gita import load_gita
    from narration_tts.drama_tts import plan_voice_packages, voice_map_from_gita
    from narration_tts.drama_prompt import build_drama_prompt

    gita = load_gita(gita_path)
    voice_map = voice_map_from_gita(gita)
    default_voice_arg = str(getattr(args, "default_voice", "") or "").strip()
    default_voice = default_voice_arg or None
    packages = plan_voice_packages(
        draft_path,
        voice_map=voice_map,
        default_voice=default_voice,
    )

    show_prompt_for = (getattr(args, "show_prompt", None) or "").strip()
    if show_prompt_for:
        narrative_plan: dict | None = None
        plan_path = project_root / "output" / "narrative_plan.json"
        if plan_path.is_file():
            try:
                narrative_plan = json.loads(plan_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                print(f"warning: failed to load {plan_path}: {exc}", file=sys.stderr)

        norm_target = "".join(c for c in show_prompt_for.upper() if c.isalnum())
        match: tuple[str, str, str, int] | None = None  # speaker, voice, line, scene_index
        for pkg in packages:
            speaker_norm = "".join(c for c in pkg.speaker.upper() if c.isalnum())
            if not (speaker_norm == norm_target or norm_target in speaker_norm):
                continue
            for req in pkg.requirements:
                line = (req.tts_text or req.descriptor or "").strip()
                if line:
                    match = (pkg.speaker, pkg.voice, line, req.scene_index)
                    break
            if match:
                break
        if not match:
            print(
                f"error: no clip found for speaker '{show_prompt_for}'.",
                file=sys.stderr,
            )
            return 1

        speaker, voice, line, scene_idx = match
        prompt = build_drama_prompt(
            line_text=line,
            speaker=speaker,
            gita=gita,
            narrative_plan=narrative_plan,
            scene_index=scene_idx,
        )
        if getattr(args, "json", False):
            print(json.dumps({
                "speaker": speaker,
                "voice": voice,
                "scene_index": scene_idx,
                "line": line,
                "prompt": prompt,
            }, indent=2))
        else:
            print(f"# Sample prompt for {speaker} (voice={voice}, scene={scene_idx})")
            print(prompt)
        return 0

    if getattr(args, "json", False):
        payload = {
            "draft": str(draft_path),
            "default_voice": default_voice,
            "characters": [
                {
                    "speaker": pkg.speaker,
                    "voice": pkg.voice,
                    "clip_count": len(pkg.requirements),
                }
                for pkg in packages
            ],
        }
        print(json.dumps(payload, indent=2))
        return 0

    print(f"Voice map for project {args.project_id}")
    print(f"  draft: {draft_path}")
    print(f"  default_voice: {default_voice_arg or '(auto by role: male=Charon, female=Achernar, narrator=Algieba)'}")
    if not packages:
        print("  (no voice clips found)")
        return 0
    for pkg in packages:
        print(f"  {pkg.speaker} -> {pkg.voice} ({len(pkg.requirements)} clips)")
    return 0


def cmd_tts_generate(args: argparse.Namespace) -> int:
    project_root, assets_root, output_root, _ = _project_paths(args.project_id, Path(args.projects_root))
    if not (project_root / "book_metadata.json").is_file():
        print(f"error: no book_metadata.json at {project_root}", file=sys.stderr)
        return 1
    draft_path = _draft_path_for_project(project_root)
    if not draft_path.is_file():
        print(
            f"error: draft_timeline.json not found at {draft_path}; run stage1 first.",
            file=sys.stderr,
        )
        return 1

    meta = _load_normalized_metadata(project_root)
    gita_path = _ensure_gita_for_project(project_root, meta)

    _ensure_story_import_path()
    _ensure_narration_tts_import_path()
    from story_processing.fountain.gita import load_gita
    from narration_tts.drama_tts import (
        fill_drama_voice_requirements,
        voice_map_from_gita,
    )

    gita = load_gita(gita_path)
    voice_map = voice_map_from_gita(gita)
    default_voice_arg = str(getattr(args, "default_voice", "") or "").strip()
    default_voice = default_voice_arg or None

    use_prompt = not bool(getattr(args, "no_prompt", False))
    sample_context_arg = getattr(args, "sample_context", None)
    sample_context = (
        str(sample_context_arg).strip() if sample_context_arg else None
    )

    narrative_plan_arg = getattr(args, "narrative_plan", None)
    narrative_plan_path: Path | None = None
    if narrative_plan_arg:
        narrative_plan_path = Path(narrative_plan_arg)
    else:
        candidate = output_root / "narrative_plan.json"
        if candidate.is_file():
            narrative_plan_path = candidate

    narrative_plan: dict | None = None
    if use_prompt and narrative_plan_path is not None and narrative_plan_path.is_file():
        try:
            narrative_plan = json.loads(narrative_plan_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(
                f"warning: failed to load narrative_plan {narrative_plan_path}: {exc}",
                file=sys.stderr,
            )

    if use_prompt and narrative_plan is None:
        print(
            "note: no narrative_plan.json found; prompts will use Gita-only context.",
            file=sys.stderr,
        )

    summary_path = output_root / "tts_summary.json"
    try:
        result = fill_drama_voice_requirements(
            draft_path,
            assets_root,
            voice_map=voice_map,
            default_voice=default_voice,
            only_speaker=getattr(args, "character", None),
            skip_existing=not bool(getattr(args, "regenerate", False)),
            pause_between_clips_s=float(getattr(args, "pause_between_clips", 1.5)),
            pause_between_characters_s=float(getattr(args, "pause_between_characters", 5.0)),
            max_clips_per_character_per_minute=int(
                getattr(args, "max_clips_per_minute", 10) or 0,
            ),
            summary_path=summary_path,
            dry_run=bool(getattr(args, "dry_run", False)),
            gita=gita,
            narrative_plan=narrative_plan,
            use_prompt=use_prompt,
            sample_context=sample_context,
        )
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if getattr(args, "json", False):
        print(json.dumps(result.to_summary_dict(), indent=2))
        return 0

    if getattr(args, "dry_run", False):
        print(f"Drama TTS plan (dry-run); summary: {summary_path}")
    else:
        print(f"Drama TTS complete; summary: {summary_path}")
    print(f"  total_generated: {result.total_generated}")
    print(f"  total_failed: {result.total_failed}")
    for char in result.characters:
        suffix = []
        if char.skipped_existing:
            suffix.append(f"skipped={char.skipped_existing}")
        if char.skipped_empty:
            suffix.append(f"empty={char.skipped_empty}")
        if char.failed:
            suffix.append(f"failed={len(char.failed)}")
        extra = (" [" + ", ".join(suffix) + "]") if suffix else ""
        print(
            f"  {char.speaker} -> {char.voice} ({char.generated}/{char.total_clips} generated){extra}",
        )
    return 0 if result.total_failed == 0 else 1


def cmd_stage1(args: argparse.Namespace) -> int:
    project_root, _, _, _ = _project_paths(args.project_id, Path(args.projects_root))
    try:
        story, resolved_slug = _resolve_story_from_metadata(project_root, getattr(args, "chapter", None))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if not story.is_file():
        print(f"error: chapter file not found: {story}", file=sys.stderr)
        return 1

    cmd = [
        "--story",
        str(story),
        "--project-id",
        _sanitize_project_id(args.project_id),
        "--project-type",
        "audio_drama",
        "--projects-root",
        str(Path(args.projects_root).resolve()),
    ]
    if getattr(args, "director", False):
        cmd.append("--director")
    if getattr(args, "use_gita", False) or getattr(args, "update_gita", False):
        meta = _load_normalized_metadata(project_root)
        gita_path = _ensure_gita_for_project(project_root, meta)
        cmd.extend(["--gita", str(gita_path)])
    if getattr(args, "update_gita", False):
        cmd.append("--update-gita")
    rc = _run_pipeline(cmd)
    if rc == 0:
        meta = _read_project_metadata(project_root)
        if meta:
            meta["active_chapter_slug"] = resolved_slug
            _write_project_metadata(project_root, meta)
    return rc


def cmd_resume(args: argparse.Namespace) -> int:
    return _run_pipeline([
        "--resume",
        "--project-id",
        _sanitize_project_id(args.project_id),
        "--project-type",
        "audio_drama",
        "--projects-root",
        str(Path(args.projects_root).resolve()),
    ])


def cmd_run(args: argparse.Namespace) -> int:
    rc = cmd_stage1(args)
    if rc != 0:
        return rc
    return cmd_resume(args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="drama_cli",
        description="Interactive audio-drama helper for AS pipeline.",
    )
    parser.add_argument(
        "--projects-root",
        default=str(_DEFAULT_PROJECTS),
        help="Path to workspace/projects (default: <repo>/workspace/projects).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Create an audio-drama project and first chapter.")
    p_init.add_argument(
        "--template",
        action="store_true",
        help="Seed chapter with a Fountain starter template instead of interactive paste.",
    )
    p_init.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Overwrite an existing project's metadata/chapter without prompting.",
    )
    p_init.set_defaults(func=cmd_init)

    def add_project_id(sp: argparse.ArgumentParser) -> None:
        sp.add_argument(
            "--project-id",
            required=True,
            help="Filesystem-safe project id.",
        )

    p_add = sub.add_parser(
        "add-chapter",
        help="Add another chapter (script file + metadata); sets it active.",
    )
    add_project_id(p_add)
    p_add.add_argument(
        "--template",
        action="store_true",
        help="Seed new chapter with the Fountain starter template.",
    )
    p_add.set_defaults(func=cmd_add_chapter)

    p_list = sub.add_parser("list-chapters", help="List chapters and the active slug.")
    add_project_id(p_list)
    p_list.set_defaults(func=cmd_list_chapters)

    p_set = sub.add_parser("set-chapter", help="Set active chapter slug.")
    add_project_id(p_set)
    p_set.add_argument(
        "--chapter",
        required=True,
        metavar="SLUG",
        help="Chapter slug as shown by list-chapters.",
    )
    p_set.set_defaults(func=cmd_set_chapter)

    p_stage1 = sub.add_parser("stage1", help="Run Stage 1 (story analysis + scaffold).")
    add_project_id(p_stage1)
    p_stage1.add_argument(
        "--chapter",
        metavar="SLUG",
        help="Optional chapter slug; defaults to active chapter.",
    )
    p_stage1.add_argument(
        "--director",
        action="store_true",
        help="Enable optional LLM audio director enrichment.",
    )
    p_stage1.add_argument(
        "--use-gita",
        action="store_true",
        help="Apply project continuity from gita.json during Stage 1.",
    )
    p_stage1.add_argument(
        "--update-gita",
        action="store_true",
        help="Update gita.json from generated Stage 1 narrative plan.",
    )
    p_stage1.set_defaults(func=cmd_stage1)

    p_resume = sub.add_parser("resume", help="Run Stage 2 (resolve + render).")
    add_project_id(p_resume)
    p_resume.set_defaults(func=cmd_resume)

    p_run = sub.add_parser("run", help="Run stage1 then resume.")
    add_project_id(p_run)
    p_run.add_argument(
        "--chapter",
        metavar="SLUG",
        help="Optional chapter slug; forwarded to stage1.",
    )
    p_run.add_argument(
        "--director",
        action="store_true",
        help="Enable optional LLM audio director enrichment during stage1.",
    )
    p_run.add_argument(
        "--use-gita",
        action="store_true",
        help="Apply project continuity from gita.json during Stage 1.",
    )
    p_run.add_argument(
        "--update-gita",
        action="store_true",
        help="Update gita.json from generated Stage 1 narrative plan.",
    )
    p_run.set_defaults(func=cmd_run)

    p_gita_init = sub.add_parser("gita-init", help="Create gita.json continuity file if missing.")
    add_project_id(p_gita_init)
    p_gita_init.set_defaults(func=cmd_gita_init)

    p_gita_show = sub.add_parser("gita-show", help="Show gita.json continuity summary.")
    add_project_id(p_gita_show)
    p_gita_show.add_argument("--json", action="store_true", help="Print raw gita JSON.")
    p_gita_show.set_defaults(func=cmd_gita_show)

    p_gita_update = sub.add_parser(
        "gita-update",
        help="Update gita.json from selected chapter parse output.",
    )
    add_project_id(p_gita_update)
    p_gita_update.add_argument(
        "--chapter",
        metavar="SLUG",
        help="Optional chapter slug; defaults to active chapter.",
    )
    p_gita_update.set_defaults(func=cmd_gita_update)

    p_preview = sub.add_parser(
        "dry-run-parse",
        help="Parse chapter and print preview (no stage/scaffold/resolve side-effects).",
    )
    add_project_id(p_preview)
    p_preview.add_argument(
        "--chapter",
        metavar="SLUG",
        help="Optional chapter slug; defaults to active chapter.",
    )
    p_preview.add_argument(
        "--json",
        action="store_true",
        help="Print structured preview JSON.",
    )
    p_preview.set_defaults(func=cmd_dry_run_parse)

    p_voice_map = sub.add_parser(
        "voice-map",
        help="Show speaker -> Gemini voice mapping resolved from gita.json.",
    )
    add_project_id(p_voice_map)
    p_voice_map.add_argument(
        "--default-voice",
        default="",
        help="Optional fallback Gemini voice override for speakers without a tts_voice in gita.json. "
        "Default auto-mapping: male=Charon, female=Achernar, narrator=Algieba.",
    )
    p_voice_map.add_argument(
        "--json",
        action="store_true",
        help="Print structured voice-map JSON.",
    )
    p_voice_map.add_argument(
        "--show-prompt",
        metavar="SPEAKER",
        help="Print the structured Gemini prompt that would be used for this speaker's first line.",
    )
    p_voice_map.set_defaults(func=cmd_voice_map)

    p_tts = sub.add_parser(
        "tts-generate",
        help="Generate per-character voice clips with Gemini Flash TTS (one character at a time).",
    )
    add_project_id(p_tts)
    p_tts.add_argument(
        "--character",
        metavar="SPEAKER",
        help="Generate only one character's package (matches track_id from the script).",
    )
    p_tts.add_argument(
        "--default-voice",
        default="",
        help="Optional fallback Gemini voice override when no tts_voice is set. "
        "Default auto-mapping: male=Charon, female=Achernar, narrator=Algieba.",
    )
    p_tts.add_argument(
        "--regenerate",
        action="store_true",
        help="Re-synthesize clips even when a WAV already exists in the folder.",
    )
    p_tts.add_argument(
        "--pause-between-clips",
        type=float,
        default=1.5,
        help="Seconds to sleep between clips inside a character package (default: 1.5).",
    )
    p_tts.add_argument(
        "--pause-between-characters",
        type=float,
        default=5.0,
        help="Seconds to sleep between character packages (default: 5.0).",
    )
    p_tts.add_argument(
        "--max-clips-per-minute",
        type=int,
        default=10,
        help="Soft per-minute cap inside a character package; 0 disables (default: 10).",
    )
    p_tts.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the per-character plan without making any TTS calls.",
    )
    p_tts.add_argument(
        "--json",
        action="store_true",
        help="Print the run summary as JSON.",
    )
    p_tts.add_argument(
        "--narrative-plan",
        metavar="PATH",
        help="Path to narrative_plan.json used for prompt context (defaults to "
        "<project>/output/narrative_plan.json when present).",
    )
    p_tts.add_argument(
        "--no-prompt",
        action="store_true",
        help="Skip the structured Director's prompt and send raw dialogue text to Gemini.",
    )
    p_tts.add_argument(
        "--sample-context",
        metavar="TEXT",
        help="Override the project-level Sample Context block (genre, tone, pacing notes).",
    )
    p_tts.set_defaults(func=cmd_tts_generate)

    return parser


def main() -> int:
    load_dotenv(_REPO_ROOT / ".env")
    parser = _build_parser()
    args = parser.parse_args()
    pr = Path(args.projects_root)
    if pr.name != "projects":
        args.projects_root = str((pr / "projects").resolve())
    else:
        args.projects_root = str(pr.resolve())
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())



