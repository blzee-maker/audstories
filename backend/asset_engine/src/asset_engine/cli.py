"""CLI for asset engine."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from asset_engine.config import ResolverConfig
from asset_engine.contracts.draft_models import DraftTimeline
from asset_engine.pipeline import run_asset_pipeline, run_scaffold_phase
from asset_engine.requirements import extract_requirements
from asset_engine.resolvers.clap_index import build_index
from asset_engine.resolvers.library_resolver import ResolveOptions, resolve_from_library


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="asset-engine",
        description="Library-first asset engine for scaffold/resolve workflow.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    scaffold = subparsers.add_parser("scaffold", help="Generate required asset folders.")
    scaffold.add_argument("--draft", required=True, help="Path to draft_timeline.json")
    scaffold.add_argument("--library", required=True, help="Project assets root (scaffold folders)")

    resolve = subparsers.add_parser("resolve", help="Resolve assets and write output timelines.")
    resolve.add_argument("--draft", required=True, help="Path to draft_timeline.json")
    resolve.add_argument("--library", required=True, help="Project assets root (scaffold folders)")
    resolve.add_argument("--out", required=True, help="Output directory")
    resolve.add_argument("--dry-run", action="store_true", help="Only report status, do not write files")
    _add_resolver_flags(resolve)

    status = subparsers.add_parser("status", help="Print current asset readiness report.")
    status.add_argument("--draft", required=True, help="Path to draft_timeline.json")
    status.add_argument("--library", required=True, help="Project assets root (scaffold folders)")
    _add_resolver_flags(status)

    run = subparsers.add_parser("run", help="Run scaffold then resolve.")
    run.add_argument("--draft", required=True, help="Path to draft_timeline.json")
    run.add_argument("--library", required=True, help="Project assets root (scaffold folders)")
    run.add_argument("--out", required=True, help="Output directory")
    run.add_argument("--dry-run", action="store_true", help="Only report status, do not write files")
    _add_resolver_flags(run)

    lib = subparsers.add_parser("library", help="Build or validate shared library indexes.")
    lib_sub = lib.add_subparsers(dest="library_command", required=True)

    index = lib_sub.add_parser("index", help="Build lightweight CLAP-style metadata index.")
    index.add_argument("--kind", required=True, choices=["sfx", "ambience"], help="Asset kind to index")
    index.add_argument("--audio-library", required=True, help="Shared audio library root")
    index.add_argument(
        "--output",
        default=None,
        help="Optional output path (default: <audio-library>/index/<kind>_index.json)",
    )

    validate = lib_sub.add_parser("validate-music", help="Validate music catalog file.")
    validate.add_argument("--music-catalog", required=True, help="Path to music_catalog.json")

    return parser


def _add_resolver_flags(cmd: argparse.ArgumentParser) -> None:
    cmd.add_argument("--audio-library", default=None, help="Shared audio library root")
    cmd.add_argument("--music-catalog", default=None, help="Path to music_catalog.json")
    cmd.add_argument("--use-clap", action="store_true", help="Enable optional CLAP index matching")
    cmd.add_argument("--use-freesound", action="store_true", help="Enable optional Freesound fallback")
    cmd.add_argument("--require-voice", action="store_true", help="Fail if any voice clip is unresolved")
    cmd.add_argument(
        "--score-threshold",
        type=float,
        default=0.45,
        help="Minimum score for catalog/CLAP matches (default: 0.45)",
    )


def _read_draft(path: Path) -> DraftTimeline:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return DraftTimeline(**payload)


def _resolve_options_from_args(args: argparse.Namespace) -> ResolveOptions:
    cfg = ResolverConfig.from_paths(
        audio_library_root=getattr(args, "audio_library", None),
        music_catalog_path=getattr(args, "music_catalog", None),
        use_clap=bool(getattr(args, "use_clap", False)),
        use_freesound=bool(getattr(args, "use_freesound", False)),
        require_voice=bool(getattr(args, "require_voice", False)),
        score_threshold=float(getattr(args, "score_threshold", 0.45)),
    )
    return ResolveOptions(
        audio_library_root=cfg.audio_library_root,
        music_catalog_path=cfg.music_catalog_path,
        use_clap=cfg.use_clap,
        use_freesound=cfg.use_freesound,
        require_voice=cfg.require_voice,
        score_threshold=cfg.score_threshold,
    )


def _print_status(draft: DraftTimeline, requirements: list, resolution, *, require_voice: bool) -> bool:
    resolved = len(resolution.resolved)
    missing = len(resolution.missing)
    skipped = len(resolution.skipped)

    counts = {"voice": 0, "music": 0, "ambience": 0, "sfx": 0}
    for req in requirements:
        counts[str(req.asset_kind)] += 1

    print("Asset Status")
    print("============")
    print(f"Project : {draft.project.name}")
    print(f"Draft   : {len(draft.scenes)} scenes")
    print()
    print("Assets required:")
    print(f"  Voice    : {counts['voice']}")
    print(f"  Music    : {counts['music']}")
    print(f"  Ambience : {counts['ambience']}")
    print(f"  SFX      : {counts['sfx']}")
    print("  -------------")
    print(f"  Total    : {len(requirements)}")
    print()
    print("Resolution status:")
    print(f"  resolved : {resolved}")
    print(f"  missing  : {missing}")
    print(f"  skipped  : {skipped}")
    if require_voice:
        unresolved_voice = [
            req
            for req in requirements
            if str(req.asset_kind) == "voice" and req.resolution_status.value != "resolved"
        ]
        print(f"  unresolved voice (strict): {len(unresolved_voice)}")
    print()
    ready = missing == 0
    if require_voice:
        ready = ready and all(
            req.resolution_status.value == "resolved"
            for req in requirements
            if str(req.asset_kind) == "voice"
        )
    print(f"READY TO RESOLVE: {'YES' if ready else 'NO'}")
    return ready


def _run_status_only(draft_path: Path, library_root: Path, options: ResolveOptions) -> bool:
    draft = _read_draft(draft_path)
    requirements = extract_requirements(draft)
    resolution = resolve_from_library(requirements, library_root, options=options)
    return _print_status(draft, requirements, resolution, require_voice=options.require_voice)


def _run_scaffold_cmd(draft_path: Path, library_root: Path) -> None:
    draft = _read_draft(draft_path)
    requirements = extract_requirements(draft)
    result = run_scaffold_phase(draft=draft, requirements=requirements, library_root=library_root)
    print(f"Scaffold root: {result['root_path']}")
    print(f"Folders created: {result['folders_created']}")
    print(f"Folders unchanged: {result['folders_unchanged']}")


def _run_resolve_cmd(
    draft_path: Path,
    library_root: Path,
    out_dir: Path,
    dry_run: bool,
    options: ResolveOptions,
) -> int:
    if dry_run:
        _run_status_only(draft_path, library_root, options)
        return 0

    result = run_asset_pipeline(
        draft_timeline_path=draft_path,
        output_dir=out_dir,
        library_root=library_root,
        voice_mode="auto",
        resolve_options=options,
    )
    print(f"Final timeline: {result['final_timeline_path']}")
    print(f"Asset manifest: {result['manifest_path']}")
    print(f"Voice status: {result['voice_status_path']}")
    if result["warnings"]:
        print("Warnings:")
        for warning in result["warnings"]:
            print(f"  - {warning}")
    return 0


def _run_library_index(kind: str, audio_library_root: Path, output: Path | None) -> int:
    target = output or (audio_library_root / "index" / f"{kind}_index.json")
    out = build_index(kind=kind, audio_library_root=audio_library_root, output_path=target)
    print(f"Index written: {out}")
    return 0


def _run_library_validate_music(catalog_path: Path) -> int:
    from asset_engine.resolvers.music_catalog import MusicCatalog

    catalog = MusicCatalog.load(catalog_path)
    print(f"Music catalog valid: {catalog_path}")
    print(f"Tracks: {len(catalog.tracks)}")
    return 0


def main() -> None:
    args = _build_parser().parse_args()
    try:
        if args.command == "library":
            if args.library_command == "index":
                raise SystemExit(
                    _run_library_index(
                        kind=str(args.kind),
                        audio_library_root=Path(args.audio_library),
                        output=Path(args.output) if args.output else None,
                    ),
                )
            if args.library_command == "validate-music":
                raise SystemExit(_run_library_validate_music(Path(args.music_catalog)))
            raise SystemExit(2)

        options = _resolve_options_from_args(args)

        if args.command == "scaffold":
            _run_scaffold_cmd(Path(args.draft), Path(args.library))
            return

        if args.command == "status":
            ready = _run_status_only(Path(args.draft), Path(args.library), options)
            if not ready:
                raise SystemExit(1)
            return

        if args.command == "resolve":
            exit_code = _run_resolve_cmd(
                Path(args.draft),
                Path(args.library),
                Path(args.out),
                bool(args.dry_run),
                options,
            )
            raise SystemExit(exit_code)

        if args.command == "run":
            _run_scaffold_cmd(Path(args.draft), Path(args.library))
            if not args.dry_run:
                _run_resolve_cmd(Path(args.draft), Path(args.library), Path(args.out), False, options)
            ready = _run_status_only(Path(args.draft), Path(args.library), options)
            if not ready:
                print("Assets missing. Fill folders and run again.")
                raise SystemExit(1)
            print("Render ready.")
            return
    except ValueError as exc:
        print(f"Error: {exc}")
        raise SystemExit(1) from exc
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        raise SystemExit(1) from exc
    except Exception as exc:  # pragma: no cover - defensive fallback
        print(f"Unexpected error: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
