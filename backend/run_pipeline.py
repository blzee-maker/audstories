"""Two-stage pipeline orchestrator.

Chains Engine 1 (story -> draft), Engine 2 (asset scaffold/resolve),
and Engine 3 (audio render) into a two-stage workflow with a human
pause in between for asset sourcing.

Stage 1 â€” Analyse story and scaffold asset folders:
    python run_pipeline.py --story story.txt --project-id demo_project

Stage 2 â€” Resolve assets and render audio:
    python run_pipeline.py --resume --project-id demo_project

Narration-only audiobook (no music/ambience/SFX beds, no shared library preflight):
    python run_pipeline.py --story ch.txt --project-id demo --project-type audiobook --narration-only

Check readiness at any time:
    python run_pipeline.py --status --project-id demo_project
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import soundfile as sf


# ---------------------------------------------------------------------------
# Project path resolution
# ---------------------------------------------------------------------------

_SAFE_PROJECT_ID = re.compile(r"[^a-zA-Z0-9_-]+")
_DEFAULT_PROJECTS_ROOT = Path("workspace") / "projects"
_REPO_ROOT = Path(__file__).resolve().parent
_DELIVERY_PRESETS_DIR = _REPO_ROOT / "delivery_presets"


def _deep_merge_dict(base: dict, overlay: dict) -> dict:
    """Recursively merge *overlay* into a copy of *base* (dict values only)."""
    out = dict(base)
    for key, val in overlay.items():
        if key in out and isinstance(out[key], dict) and isinstance(val, dict):
            out[key] = _deep_merge_dict(out[key], val)
        else:
            out[key] = val
    return out


def _read_book_metadata_light(project_root: Path) -> dict:
    p = project_root / "book_metadata.json"
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _default_delivery_profile_id(project_type: str, narration_only: bool) -> str:
    if project_type == "audiobook" and narration_only:
        return "audiobook_retail"
    return "audio_drama_default"


def _resolve_delivery_profile_id(
    project_root: Path | None,
    project_type: str,
    narration_only: bool,
) -> str:
    if project_root is not None:
        explicit = str(_read_book_metadata_light(project_root).get("delivery_profile", "")).strip()
        if explicit:
            return explicit
    return _default_delivery_profile_id(project_type, narration_only)


def _apply_delivery_preset_to_draft(
    draft_path: Path,
    project_root: Path | None,
    project_type: str,
    narration_only: bool,
) -> None:
    """Merge delivery preset into draft_timeline.json (peak ceiling, sample rate, etc.)."""
    if project_root is not None:
        meta = _read_book_metadata_light(project_root)
        pt = meta.get("project_type")
        if pt in ("audiobook", "audio_drama"):
            project_type = pt
        if "narration_only" in meta:
            narration_only = bool(meta.get("narration_only"))

    profile_id = _resolve_delivery_profile_id(project_root, project_type, narration_only)
    preset_path = _DELIVERY_PRESETS_DIR / f"{profile_id}.json"
    if not preset_path.is_file():
        print(
            f"  [warn] delivery preset not found: {preset_path} "
            f"(expected under delivery_presets/)",
            file=sys.stderr,
        )
        return

    try:
        preset_raw = json.loads(preset_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"  [warn] could not read delivery preset {preset_path}: {exc}", file=sys.stderr)
        return

    fragment = {k: preset_raw[k] for k in ("project", "settings") if k in preset_raw}
    if not fragment:
        return

    try:
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"  [warn] could not merge delivery preset â€” invalid draft: {exc}", file=sys.stderr)
        return

    merged = dict(draft)
    if "project" in fragment:
        merged["project"] = _deep_merge_dict(dict(merged.get("project", {})), fragment["project"])
    if "settings" in fragment:
        merged["settings"] = _deep_merge_dict(dict(merged.get("settings", {})), fragment["settings"])

    draft_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    peak = merged.get("settings", {}).get("peak_target_dbfs")
    sr = merged.get("project", {}).get("sample_rate")
    print(
        f"  [delivery] Applied preset {profile_id!r} "
        f"(peak_target_dbfs={peak}, project.sample_rate={sr} Hz)",
    )


def _sanitize_project_id(project_id: str) -> str:
    """Normalize a project ID to a deterministic filesystem-safe value."""
    cleaned = _SAFE_PROJECT_ID.sub("_", project_id.strip())
    cleaned = cleaned.strip("._-")
    # Lower-cased so slugs are stable on case-sensitive filesystems: a project
    # created as "Episode Two" must resolve identically on Windows and Linux.
    # All three copies of this helper (book_cli, drama_cli, run_pipeline) must
    # agree, or a project created by one will not be found by another.
    return cleaned.lower() or "untitled_project"


def _resolve_projects_root(projects_root_arg: str, repo_root: Path) -> Path:
    """Resolve projects root as absolute path, relative to repo when needed."""
    raw = Path(projects_root_arg)
    return raw if raw.is_absolute() else (repo_root / raw)


def _resolve_project_paths(project_id: str, projects_root: Path) -> tuple[str, Path, Path, Path]:
    """Resolve canonical per-project roots."""
    safe_project_id = _sanitize_project_id(project_id)
    project_root = (projects_root / safe_project_id).resolve()
    assets_root = (project_root / "assets").resolve()
    output_root = (project_root / "output").resolve()
    return safe_project_id, project_root, assets_root, output_root


def _project_context_path(project_root: Path) -> Path:
    """Return the project metadata file path."""
    return project_root / "project_context.json"


def _persist_project_context(
    project_root: Path,
    *,
    project_id: str,
    projects_root: Path,
    library_root: Path,
    out_dir: Path,
    project_type: str = "audio_drama",
    narration_only: bool = False,
    book_title: str = "",
    writer_name: str = "",
    chapter_slug: str = "",
) -> None:
    """Persist project path metadata for orchestration consistency."""
    project_root.mkdir(parents=True, exist_ok=True)
    library_root.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    meta_title = book_title
    meta_writer = writer_name
    meta_chapter = chapter_slug
    meta_narration = narration_only
    meta_path = _book_metadata_path(project_root)
    if meta_path.is_file():
        try:
            disk_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            disk_meta = {}
        else:
            meta_title = meta_title or str(disk_meta.get("book_title", "") or "")
            meta_writer = meta_writer or str(disk_meta.get("writer_name", "") or "")
            meta_chapter = meta_chapter or str(disk_meta.get("chapter_slug", "") or "")
            if not narration_only and disk_meta.get("narration_only"):
                meta_narration = True

    payload = {
        "project_id": project_id,
        "project_type": project_type,
        "narration_only": bool(meta_narration),
        "book_title": meta_title,
        "writer_name": meta_writer,
        "chapter_slug": meta_chapter,
        "project_root": str(project_root),
        "projects_root": str(projects_root),
        "assets_root": str(library_root),
        "output_root": str(out_dir),
    }
    _project_context_path(project_root).write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


def _load_project_context(project_root: Path) -> dict[str, str] | None:
    """Load project metadata if it already exists."""
    context_path = _project_context_path(project_root)
    if not context_path.is_file():
        return None
    with context_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return {str(k): str(v) for k, v in data.items()}


def _build_path_args(args) -> str:
    """Build command-line path args for copy/paste instructions."""
    if getattr(args, "project_id", None):
        parts = [f"--project-id {args.project_id}"]
        if args.projects_root != str(_DEFAULT_PROJECTS_ROOT):
            parts.append(f"--projects-root {args.projects_root}")
        return " ".join(parts)
    return f"--library {args.library} --out {args.out}"


def _guard_shared_root_paths(
    *,
    repo_root: Path,
    library_root: Path,
    out_dir: Path,
    allow_shared_roots: bool,
) -> None:
    """Block legacy shared roots unless explicitly allowed."""
    if allow_shared_roots:
        return

    shared_assets = (repo_root / "assets").resolve()
    shared_output = (repo_root / "output").resolve()
    if library_root == shared_assets or out_dir == shared_output:
        _fail(
            stage="Path Guard",
            what_happened=(
                "Shared root paths are disabled. "
                f"Received library={library_root} out={out_dir}."
            ),
            next_step=(
                "Use project-scoped paths (recommended: --project-id <id>) "
                "or pass --allow-shared-roots only for local legacy workflows."
            ),
            diagnose_cmd=(
                "python run_pipeline.py --story <story.txt> --project-id <project_id>"
            ),
        )


# ---------------------------------------------------------------------------
# Stage failure helpers
# ---------------------------------------------------------------------------

def _fail(stage: str, what_happened: str, next_step: str, diagnose_cmd: str) -> None:
    """Print a structured failure message and exit with code 1."""
    print(f"\n[{stage}] {what_happened}", file=sys.stderr)
    print(f"Next step : {next_step}", file=sys.stderr)
    print(f"Diagnose  : {diagnose_cmd}", file=sys.stderr)
    sys.exit(1)


def _run(cmd: list[str], *, cwd: Path | None = None) -> int:
    """Run a subprocess, relay its stdout/stderr live, and return its exit code."""
    result = subprocess.run(cmd, cwd=str(cwd) if cwd else None)
    return result.returncode


def _run_with_env(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    extra_pythonpath: list[Path] | None = None,
) -> int:
    """Run subprocess with optional PYTHONPATH extensions."""
    env = os.environ.copy()
    if extra_pythonpath:
        sep = os.pathsep
        existing = env.get("PYTHONPATH", "")
        extra = sep.join(str(p) for p in extra_pythonpath)
        env["PYTHONPATH"] = f"{extra}{sep}{existing}" if existing else extra
    result = subprocess.run(cmd, cwd=str(cwd) if cwd else None, env=env)
    return result.returncode


def _ensure_local_import_paths(repo_root: Path) -> None:
    """Allow local package imports without pip-installing each engine.

    Delegates to the shared shim (see engine_paths.py for why it is required).
    """
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from engine_paths import ensure_engine_paths

    ensure_engine_paths()
def _asset_engine_resolver_args(args) -> list[str]:
    """Build optional resolver args forwarded to asset_engine.cli."""
    out: list[str] = []
    if getattr(args, "audio_library", None):
        out.extend(["--audio-library", str(args.audio_library)])
    if getattr(args, "music_catalog", None):
        out.extend(["--music-catalog", str(args.music_catalog)])
    if getattr(args, "use_clap", False):
        out.append("--use-clap")
    if getattr(args, "use_freesound", False):
        out.append("--use-freesound")
    if getattr(args, "require_voice", False):
        out.append("--require-voice")
    score = getattr(args, "score_threshold", None)
    if score is not None:
        out.extend(["--score-threshold", str(score)])
    return out


# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------

_AUDIO_EXTS = {".wav", ".mp3", ".ogg", ".flac", ".m4a"}


def _count_audio_files(folder: Path) -> int:
    if not folder.exists():
        return 0
    return sum(1 for f in folder.rglob("*") if f.is_file() and f.suffix.lower() in _AUDIO_EXTS)


def _preflight_audio_library(audio_root: Path) -> None:
    """Fail fast if any audio category folder has zero files."""
    for category in ("music", "ambience", "sfx"):
        cat_path = audio_root / category
        count = _count_audio_files(cat_path)
        if count == 0:
            _fail(
                stage="Preflight â€” Audio Library",
                what_happened=(
                    f"No audio files found in {cat_path}. "
                    "At least 2-3 WAV files are required per category."
                ),
                next_step=(
                    f"Add WAV files to {cat_path} whose filenames include "
                    "keywords matching the mood/atmosphere/SFX descriptors in your story."
                ),
                diagnose_cmd=f"Get-ChildItem \"{cat_path}\" -Recurse",
            )


def _preflight_story_file(story_path: Path) -> None:
    if not story_path.is_file():
        _fail(
            stage="Preflight â€” Story File",
            what_happened=f"Story file not found: {story_path}",
            next_step="Provide the correct path to a .txt story file.",
            diagnose_cmd="python run_pipeline.py --story <path> --project-id <project_id>",
        )


def _preflight_env(engine1_dir: Path) -> None:
    """Warn if .env is missing; fail if GEMINI_API_KEY is not set at runtime."""
    import os
    from dotenv import load_dotenv  # type: ignore[import]
    load_dotenv(engine1_dir / ".env")
    if not os.environ.get("GEMINI_API_KEY"):
        _fail(
            stage="Preflight â€” Environment",
            what_happened="GEMINI_API_KEY is not set.",
            next_step=(
                f"Copy {engine1_dir / '.env.example'} to {engine1_dir / '.env'} "
                "and fill in your Gemini API key. "
                "Then rotate the key at https://aistudio.google.com/app/apikey if not already done."
            ),
            diagnose_cmd=f"cat \"{engine1_dir / '.env.example'}\"",
        )


# ---------------------------------------------------------------------------
# Stage runners
# ---------------------------------------------------------------------------

def _stage1_engine1(
    story_path: Path,
    out_dir: Path,
    engine1_dir: Path,
    no_llm: bool,
    model: str | None,
    fallback_model: str | None,
    director: bool = False,
    gita: str | None = None,
    update_gita: bool = False,
    project_type: str = "audio_drama",
    narration_only: bool = False,
) -> Path:
    """Run Engine 1: story -> draft_timeline.json."""
    print("\n" + "=" * 60)
    print(f"[Stage 1 â€” Engine 1] Story -> Draft Timeline  [{project_type}]")
    print("=" * 60)

    cmd = [sys.executable, "cli.py", "process", "--input", str(story_path), "--output", str(out_dir)]
    cmd.extend(["--project-type", project_type])
    if narration_only:
        cmd.append("--narration-only")
    if no_llm:
        cmd.append("--no-llm")
    elif model:
        cmd.extend(["--model", model])
        if fallback_model:
            cmd.extend(["--fallback-model", fallback_model])
    if director:
        cmd.append("--director")
    if gita:
        cmd.extend(["--gita", gita])
    if update_gita:
        cmd.append("--update-gita")

    rc = _run(cmd, cwd=engine1_dir)
    if rc != 0:
        _fail(
            stage="Stage 1 â€” Engine 1",
            what_happened="audstories process failed. The story could not be compiled to a draft timeline.",
            next_step="Check that your story file is valid UTF-8 text and that the Gemini key is active.",
            diagnose_cmd=(
                f"cd \"{engine1_dir}\" && python cli.py process "
                f"--input \"{story_path}\" --output \"{out_dir}\""
            ),
        )

    draft_path = out_dir / "draft_timeline.json"
    if not draft_path.is_file():
        _fail(
            stage="Stage 1 â€” Engine 1",
            what_happened=f"Engine 1 exited cleanly but draft_timeline.json was not written to {out_dir}.",
            next_step="Run Engine 1 manually and check its output directory.",
            diagnose_cmd=(
                f"cd \"{engine1_dir}\" && python cli.py process "
                f"--input \"{story_path}\" --output \"{out_dir}\""
            ),
        )

    print(f"\n  draft_timeline.json -> {draft_path}")
    return draft_path


def _stage2_engine2_scaffold(draft_path: Path, library_root: Path) -> None:
    """Run Engine 2 scaffold to create required asset folders."""
    print("\n" + "=" * 60)
    print("[Stage 1 â€” Asset Engine] Scaffold")
    print("=" * 60)

    rc = _run_with_env([
        sys.executable, "-m", "asset_engine.cli",
        "scaffold",
        "--draft", str(draft_path),
        "--library", str(library_root),
    ], cwd=Path(__file__).parent.resolve() / "asset_engine", extra_pythonpath=[
        Path(__file__).parent.resolve() / "asset_engine" / "src",
    ])
    if rc != 0:
        _fail(
            stage="Stage 1 â€” Asset Engine (scaffold)",
            what_happened="asset-engine scaffold failed.",
            next_step="Ensure asset_engine is installed and the draft_timeline.json is valid.",
            diagnose_cmd=f"asset-engine scaffold --draft \"{draft_path}\" --library \"{library_root}\"",
        )


def _stage2_engine2_resolve(args, draft_path: Path, library_root: Path, out_dir: Path) -> Path:
    """Run Engine 2 resolve to produce final_timeline.json and asset_manifest.json."""
    print("\n" + "=" * 60)
    print("[Stage 2 â€” Asset Engine] Resolve")
    print("=" * 60)

    cmd = [
        sys.executable, "-m", "asset_engine.cli",
        "run",
        "--draft", str(draft_path),
        "--library", str(library_root),
        "--out", str(out_dir),
    ]
    cmd.extend(_asset_engine_resolver_args(args))
    rc = _run_with_env(cmd, cwd=Path(__file__).parent.resolve() / "asset_engine", extra_pythonpath=[
        Path(__file__).parent.resolve() / "asset_engine" / "src",
    ])
    if rc != 0:
        _fail(
            stage="Stage 2 â€” Asset Engine (resolve)",
            what_happened="asset-engine run failed. Assets could not be resolved to a final timeline.",
            next_step="Check warnings above. Ensure all descriptor tokens have at least one matching library file.",
            diagnose_cmd=f"asset-engine run --draft \"{draft_path}\" --library \"{library_root}\" --out \"{out_dir}\"",
        )

    manifest_path = out_dir / "asset_manifest.json"
    final_timeline_path = out_dir / "final_timeline.json"

    for expected in (manifest_path, final_timeline_path):
        if not expected.is_file():
            _fail(
                stage="Stage 2 â€” Asset Engine (resolve)",
                what_happened=f"asset-engine run exited cleanly but {expected.name} was not written.",
                next_step="Run asset-engine manually with the same arguments and check for errors.",
                diagnose_cmd=f"asset-engine run --draft \"{draft_path}\" --library \"{library_root}\" --out \"{out_dir}\"",
            )

    return final_timeline_path


def _timeline_has_non_wav_assets(final_timeline_path: Path) -> bool:
    """Return True when final timeline references any non-WAV audio clips."""
    try:
        payload = json.loads(final_timeline_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    for scene in payload.get("scenes", []):
        tracks = scene.get("tracks", {})
        if not isinstance(tracks, dict):
            continue
        for clips in tracks.values():
            if not isinstance(clips, list):
                continue
            for clip in clips:
                if not isinstance(clip, dict):
                    continue
                path = str(clip.get("file", "")).strip()
                if not path:
                    continue
                if Path(path).suffix.lower() != ".wav":
                    return True
    return False


def _preflight_audio_engine_runtime(final_timeline_path: Path) -> None:
    """Fail early with actionable hints for common Stage 2 runtime dependency issues."""
    try:
        import pydub  # noqa: F401
    except Exception as exc:
        msg = str(exc)
        if "audioop" in msg.lower():
            _fail(
                stage="Preflight â€” Audio Engine Runtime",
                what_happened=(
                    "pydub could not import audioop on this Python runtime "
                    f"({exc})."
                ),
                next_step=(
                    "Install audioop compatibility for Python 3.13+:\n"
                    "  python -m pip install audioop-lts\n"
                    "Then restart the API worker/server."
                ),
                diagnose_cmd='python -c "import audioop, pydub; print(\'ok\')"',
            )
        _fail(
            stage="Preflight â€” Audio Engine Runtime",
            what_happened=f"pydub import failed: {exc}",
            next_step="Install audio engine dependencies: python -m pip install -r audio_engine/requirements.txt",
            diagnose_cmd='python -c "import pydub; print(pydub.__version__)"',
        )

    needs_ffmpeg = _timeline_has_non_wav_assets(final_timeline_path)
    if needs_ffmpeg and shutil.which("ffmpeg") is None:
        _fail(
            stage="Preflight â€” Audio Engine Runtime",
            what_happened=(
                "final_timeline.json contains non-WAV clips but ffmpeg is not available in PATH."
            ),
            next_step=(
                "Install ffmpeg and add it to PATH, or convert referenced assets to WAV."
            ),
            diagnose_cmd="ffmpeg -version",
        )


def _stage3_engine3(final_timeline_path: Path, output_wav: Path, audio_engine_dir: Path) -> None:
    """Run Engine 3: final_timeline.json -> rendered WAV."""
    print("\n" + "=" * 60)
    print("[Stage 2 â€” Audio Engine] Render")
    print("=" * 60)

    _preflight_audio_engine_runtime(final_timeline_path)
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    rc = _run(
        [sys.executable, "audio_engine/main.py", str(final_timeline_path), str(output_wav)],
        cwd=audio_engine_dir,
    )
    if rc != 0:
        _fail(
            stage="Stage 2 â€” Audio Engine",
            what_happened="Audio render failed. The final timeline could not be mixed to WAV.",
            next_step="Verify all file paths in final_timeline.json exist and are readable WAV files.",
            diagnose_cmd=(
                f"cd \"{audio_engine_dir}\" && "
                f"python audio_engine/main.py \"{final_timeline_path}\" \"{output_wav}\""
            ),
        )

    if not output_wav.is_file() or output_wav.stat().st_size == 0:
        _fail(
            stage="Stage 2 â€” Audio Engine",
            what_happened=f"Render exited cleanly but {output_wav} is missing or empty.",
            next_step="Run the audio engine manually and capture full output.",
            diagnose_cmd=(
                f"cd \"{audio_engine_dir}\" && "
                f"python audio_engine/main.py \"{final_timeline_path}\" \"{output_wav}\""
            ),
        )


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def _verify_wav_header(wav_path: Path) -> None:
    """Confirm the output file is a valid WAV via soundfile (supports all sub-formats)."""
    try:
        info = sf.info(str(wav_path))
        if info.frames == 0 or info.samplerate == 0:
            raise ValueError("WAV has zero frames or zero sample rate.")
    except Exception as exc:
        _fail(
            stage="Verification",
            what_happened=f"Output WAV failed header check: {exc}",
            next_step="Inspect the rendered file and re-run Stage 2.",
            diagnose_cmd=f"python -c \"import soundfile as sf; print(sf.info('{wav_path}'))\"",
        )


def _verify_manifest_unresolved(manifest_path: Path) -> None:
    """Fail if asset_manifest.json reports any unresolved assets."""
    with manifest_path.open("r", encoding="utf-8") as fh:
        manifest = json.load(fh)

    unresolved = manifest.get("unresolved", [])
    if unresolved:
        count = len(unresolved)
        ids = ", ".join(str(u.get("requirement_id", u)) for u in unresolved[:5])
        _fail(
            stage="Verification",
            what_happened=f"asset_manifest.json reports {count} unresolved asset(s): {ids}{'...' if count > 5 else ''}",
            next_step=(
                "Add library files that match the descriptors above and re-run the pipeline. "
                "File names drive matching â€” include descriptor keywords in the filename."
            ),
            diagnose_cmd=f"python -c \"import json; m=json.load(open('{manifest_path}')); print(m.get('unresolved', []))\"",
        )


def _verify_duration(wav_path: Path, final_timeline_path: Path) -> None:
    """Check rendered WAV duration is within +/-10% of the estimated project duration."""
    info = sf.info(str(wav_path))
    actual_duration = info.duration

    with final_timeline_path.open("r", encoding="utf-8") as fh:
        timeline = json.load(fh)

    estimated = timeline.get("project", {}).get("duration")
    if estimated is None or estimated <= 0:
        print("  [warn] Cannot verify duration: project.duration not set in final_timeline.json")
        return

    settings = timeline.get("settings") or {}
    op = settings.get("output_padding")
    if (
        isinstance(op, dict)
        and op.get("enabled")
        and str(settings.get("project_type", "")).lower() == "audiobook"
    ):
        head = float(op.get("head_seconds", 0) or 0)
        tmin = float(op.get("tail_seconds_min", 0) or 0)
        tmax = float(op.get("tail_seconds_max", tmin) or 0)
        lo = min(tmin, tmax)
        hi = max(tmin, tmax)
        low = 0.9 * float(estimated) + head + lo
        high = 1.1 * float(estimated) + head + hi
        if not (low <= actual_duration <= high):
            _fail(
                stage="Verification",
                what_happened=(
                    f"Output WAV duration {actual_duration:.1f}s is outside expected range "
                    f"[{low:.1f}s, {high:.1f}s] (mix estimate {estimated:.1f}s + audiobook padding)."
                ),
                next_step=(
                    "Check output_padding settings, missing clips, or mismatched sample rates."
                ),
                diagnose_cmd=(
                    f"python -c \"import soundfile as sf; print(sf.info('{wav_path}').duration, 'seconds')\""
                ),
            )
        print(
            f"  Duration check passed: {actual_duration:.1f}s "
            f"(mix ~{estimated:.1f}s + head {head:.1f}s + tail {lo:.1f}â€“{hi:.1f}s)",
        )
        return

    ratio = actual_duration / estimated
    if not (0.9 <= ratio <= 1.1):
        _fail(
            stage="Verification",
            what_happened=(
                f"Output WAV duration {actual_duration:.1f}s is outside +/-10% of "
                f"estimated {estimated:.1f}s (ratio={ratio:.2f})."
            ),
            next_step=(
                "Check for silent padding, missing clips, or mismatched sample rates in the final timeline."
            ),
            diagnose_cmd=(
                f"python -c \"import soundfile as sf; print(sf.info('{wav_path}').duration, 'seconds')\""
            ),
        )

    print(f"  Duration check passed: {actual_duration:.1f}s (estimated {estimated:.1f}s, ratio {ratio:.2f})")


# ---------------------------------------------------------------------------
# Stage 1 completion report
# ---------------------------------------------------------------------------

def _load_draft(draft_path: Path):
    """Load draft timeline and extract requirements using asset engine API."""
    from asset_engine.contracts.draft_models import DraftTimeline
    from asset_engine.requirements import extract_requirements

    with draft_path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    draft = DraftTimeline(**payload)
    requirements = extract_requirements(draft)
    return draft, requirements


def _compute_folder_path(req, library_root: Path) -> Path:
    """Compute the scaffold folder path for a requirement."""
    from asset_engine.utils.path_utils import (
        make_asset_folder_name,
        make_voice_folder_name,
        resolve_asset_folder,
    )

    kind = str(req.asset_kind)
    if kind == "voice":
        scene_folder = make_voice_folder_name(req.scene_index, req.scene_name, req.track_id)
        folder_name = f"{scene_folder}/clip_{req.clip_index:03d}"
    else:
        folder_name = make_asset_folder_name(req.scene_index, req.scene_name, req.descriptor)
    return resolve_asset_folder(library_root, kind, folder_name)


def _estimate_project_duration(requirements) -> float:
    """Estimate total project duration from voice clip word counts."""
    from asset_engine.requirements import estimate_voice_duration

    total = 0.0
    for req in requirements:
        if str(req.asset_kind) == "voice" and req.tts_text:
            total += estimate_voice_duration(req.tts_text)
    return total


def _print_stage1_report(
    draft_path: Path,
    library_root: Path,
    story_path: Path,
    path_args: str,
) -> None:
    """Print the Stage 1 completion report with asset shopping list."""
    draft, requirements = _load_draft(draft_path)

    by_kind: dict[str, list] = {"voice": [], "music": [], "ambience": [], "sfx": []}
    for req in requirements:
        by_kind[str(req.asset_kind)].append(req)

    est_duration = _estimate_project_duration(requirements)
    est_min = int(est_duration // 60)
    est_sec = int(est_duration % 60)

    total = len(requirements)
    sep = "=" * 60
    thin = "-" * 60

    print(f"\n{sep}")
    print("  STAGE 1 COMPLETE â€” Story Analysed")
    print(sep)
    print()
    print(f"  Story    : {story_path.name}")
    print(f"  Scenes   : {len(draft.scenes)}")
    print(f"  Duration : ~{est_min}m {est_sec}s (estimated from voice text)")
    print()
    print(thin)
    print("  ASSETS REQUIRED")
    print(thin)

    # Voice clips
    voice_reqs = by_kind["voice"]
    if voice_reqs:
        print()
        print("  VOICE (record these lines)")
        print("  " + "-" * 40)
        shown = min(3, len(voice_reqs))
        for req in voice_reqs[:shown]:
            folder = _compute_folder_path(req, library_root)
            folder_rel = folder.relative_to(library_root.parent) if library_root.parent in folder.parents else folder
            text = req.tts_text or req.descriptor
            print(f"  {folder_rel}/")
            print(f'    -> "{text}"')
            print()
        if len(voice_reqs) > shown:
            remaining = len(voice_reqs) - shown
            print(f"  ... ({remaining} more â€” see {library_root / 'REQUIREMENTS.md'} for full list)")
            print()

    # Music
    music_reqs = by_kind["music"]
    if music_reqs:
        print("  MUSIC (place matching WAV files)")
        print("  " + "-" * 40)
        for req in music_reqs:
            folder = _compute_folder_path(req, library_root)
            folder_rel = folder.relative_to(library_root.parent) if library_root.parent in folder.parents else folder
            energy = f" Energy: {req.energy_hint:.1f}." if req.energy_hint is not None else ""
            loop = " Loop required." if req.loop else ""
            print(f"  {folder_rel}/")
            print(f"    -> Mood: {req.descriptor}.{energy}{loop}")
            print()

    # Ambience
    amb_reqs = by_kind["ambience"]
    if amb_reqs:
        print("  AMBIENCE (place matching WAV files)")
        print("  " + "-" * 40)
        for req in amb_reqs:
            folder = _compute_folder_path(req, library_root)
            folder_rel = folder.relative_to(library_root.parent) if library_root.parent in folder.parents else folder
            loop = " Loop required." if req.loop else ""
            print(f"  {folder_rel}/")
            print(f"    -> Atmosphere: {req.descriptor}.{loop}")
            print()

    # SFX
    sfx_reqs = by_kind["sfx"]
    if sfx_reqs:
        print("  SFX (place matching WAV files)")
        print("  " + "-" * 40)
        for req in sfx_reqs:
            folder = _compute_folder_path(req, library_root)
            folder_rel = folder.relative_to(library_root.parent) if library_root.parent in folder.parents else folder
            role = f" ({req.semantic_role})" if req.semantic_role else ""
            print(f"  {folder_rel}/")
            print(f"    -> {req.descriptor}{role}")
            print()

    # Summary
    print(thin)
    print("  SUMMARY")
    print(thin)
    print(f"  Voice clips   : {len(voice_reqs):>3}  (record using SCRIPT.txt in each folder)")
    print(f"  Music         : {len(music_reqs):>3}  (place WAV files in folders above)")
    print(f"  Ambience      : {len(amb_reqs):>3}  (place WAV files in folders above)")
    print(f"  SFX           : {len(sfx_reqs):>3}  (place WAV files in folders above)")
    print(f"  Total         : {total:>3}")
    print()
    print(thin)
    print("  NEXT STEP")
    print(thin)
    print("  Fill the folders above with audio files, then run:")
    print()
    print(f"    python run_pipeline.py --resume {path_args}")
    print()
    print("  To check readiness at any time:")
    print()
    print(f"    python run_pipeline.py --status {path_args}")
    print(sep)
    print()


# ---------------------------------------------------------------------------
# Stage 2 gate â€” readiness check
# ---------------------------------------------------------------------------

def _verify_stage1_complete(out_dir: Path, path_args: str) -> Path:
    """Confirm draft_timeline.json exists from a prior Stage 1 run."""
    draft_path = out_dir / "draft_timeline.json"
    if not draft_path.is_file():
        print("error: draft_timeline.json not found in output directory.", file=sys.stderr)
        print("Stage 1 has not been run yet. Run without --resume first:", file=sys.stderr)
        print(
            f"  python run_pipeline.py --story <story.txt> {path_args}",
            file=sys.stderr,
        )
        sys.exit(1)
    return draft_path


def _check_asset_readiness(draft_path: Path, library_root: Path, path_args: str) -> None:
    """Gate: check all required assets are present. Exit with report if not."""
    from asset_engine.resolvers.library_resolver import resolve_from_library

    _draft, requirements = _load_draft(draft_path)
    resolution = resolve_from_library(requirements, library_root)

    if not resolution.missing:
        return

    sep = "=" * 60
    print(f"\n{sep}")
    print("  NOT READY â€” Missing Assets")
    print(sep)
    print()
    print(f"  MISSING ({len(resolution.missing)} items):")
    print()

    for req in resolution.missing:
        folder = _compute_folder_path(req, library_root)
        kind = str(req.asset_kind)
        if kind == "voice":
            text = req.tts_text or req.descriptor
            print(f"  x {folder}/")
            print(f'    -> Record: "{text}"')
        elif kind == "music":
            print(f"  x {folder}/")
            print(f"    -> No WAV file found. Place a {req.descriptor} music file here.")
        elif kind == "ambience":
            print(f"  x {folder}/")
            print(f"    -> No WAV file found. Place a {req.descriptor} ambience file here.")
        else:
            print(f"  x {folder}/")
            print(f"    -> No WAV file found. Place a {req.descriptor} sound effect here.")
        print()

    print("  Fill these folders and run again:")
    print(f"    python run_pipeline.py --resume {path_args}")
    print(sep)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Stage 2 completion report
# ---------------------------------------------------------------------------

def _subtype_pretty(info) -> str:
    """Human-readable WAV subtype (e.g. PCM 16-bit) from soundfile info."""
    s = str(info.subtype)
    if "[" in s:
        s = s.split("[", 1)[1].rstrip("]")
    return s


def _format_sample_rate_label(hz: int) -> str:
    if hz <= 0:
        return "unknown"
    if hz % 1000 == 0:
        return f"{hz // 1000} kHz"
    return f"{hz / 1000:.1f} kHz"


def _channel_layout_label(channels: int) -> str:
    if channels == 1:
        return "Mono"
    if channels == 2:
        return "Stereo"
    return f"{channels} channels"


def _bits_per_sample_from_sf_info(info) -> int | None:
    """Infer PCM bit depth from soundfile subtype string (e.g. PCM_16)."""
    st = str(info.subtype).upper()
    for bits in (32, 24, 16, 8):
        if f"PCM_{bits}" in st or f"{bits} BIT" in st:
            return bits
    if "FLOAT" in st or "FLOAT32" in st:
        return 32
    if "PCM" in st:
        return 16
    return None


def _pcm_bit_rate_kbps(info) -> float | None:
    """Uncompressed PCM bit rate: sample_rate * bits * channels / 1000."""
    bits = _bits_per_sample_from_sf_info(info)
    if bits is None:
        return None
    sr = int(info.samplerate)
    ch = int(info.channels)
    if sr <= 0 or ch <= 0:
        return None
    return (sr * bits * ch) / 1000.0


def _measure_wav_output_metrics(wav_path: Path) -> dict:
    """Peak/RMS (dBFS) and optional integrated loudness (LUFS) for the rendered file."""
    info = sf.info(str(wav_path))
    out: dict = {
        "info": info,
        "peak_dbfs": None,
        "rms_dbfs": None,
        "lufs_integrated": None,
    }
    try:
        import numpy as np

        data, _ = sf.read(str(wav_path), always_2d=True, dtype="float64")
        sr = int(info.samplerate)
        peak_lin = float(np.max(np.abs(data)))
        if peak_lin > 0:
            out["peak_dbfs"] = float(20.0 * math.log10(peak_lin))
        else:
            out["peak_dbfs"] = -120.0
        rms = float(np.sqrt(np.mean(np.square(data))))
        if rms > 0:
            out["rms_dbfs"] = float(20.0 * math.log10(rms))
        else:
            out["rms_dbfs"] = -120.0
        try:
            import pyloudnorm as pyln

            out["lufs_integrated"] = float(pyln.Meter(sr).integrated_loudness(data))
        except Exception:
            pass
    except Exception:
        pass
    return out


def _publish_readiness_notes(peak_dbfs: float | None, lufs: float | None) -> list[str]:
    """Informal hints only â€” platform requirements differ (ACX, Spotify, etc.)."""
    notes: list[str] = []
    if peak_dbfs is not None:
        if peak_dbfs >= -0.05:
            notes.append("True peak is at or very near 0 dBFS â€” risk of clipping; consider lowering gain.")
        elif peak_dbfs >= -1.0:
            notes.append("Peak is hot â€” confirm headroom for your distributorâ€™s peak limits.")
    if lufs is not None:
        if lufs > -13.0:
            notes.append("Louder than typical long-form speech (-18 to -23 LUFS); verify store/platform specs.")
        if lufs < -26.0:
            notes.append("Fairly quiet overall â€” listeners may need more volume; check noise floor.")
    if not notes:
        notes.append("No obvious level issues flagged; confirm against your distributorâ€™s specifications.")
    return notes


def print_wav_output_analysis(
    wav_path: Path,
    *,
    section_title: str = "Output audio analysis",
    include_publish_notes: bool = True,
) -> None:
    """Print the same technical block used after Stage 2 (format, rate, bitrate, levels, LUFS).

    Safe to call from ``book_cli`` or other tools for credits WAVs, etc.
    """
    info = sf.info(str(wav_path))
    duration_s = info.duration
    dur_min = int(duration_s // 60)
    dur_sec = int(duration_s % 60)

    metrics = _measure_wav_output_metrics(wav_path)
    peak_dbfs = metrics.get("peak_dbfs")
    rms_dbfs = metrics.get("rms_dbfs")
    lufs = metrics.get("lufs_integrated")

    ext = wav_path.suffix.lower().lstrip(".") or "unknown"
    fmt_outer = str(info.format)
    if "[" in fmt_outer:
        fmt_outer = fmt_outer.split("[", 1)[1].rstrip("]")
    subtype = _subtype_pretty(info)
    br_kbps = _pcm_bit_rate_kbps(info)

    print(f"  --- {section_title} ---")
    print(f"  File           : {wav_path}")
    print(f"  File format    : {ext.upper()} ({fmt_outer}, {subtype})")
    print(f"  Sample rate    : {_format_sample_rate_label(int(info.samplerate))} ({int(info.samplerate)} Hz)")
    if br_kbps is not None:
        print(
            f"  Bit rate       : {br_kbps:.0f} kbps (PCM uncompressed; not MP3/AAC bitrate)",
        )
    else:
        print("  Bit rate       : â€” (could not infer from subtype; compressed formats differ)")
    print(f"  Channels       : {_channel_layout_label(info.channels)}")
    print(f"  Duration       : {dur_min}m {dur_sec:02d}s ({duration_s:.2f} s total)")
    if peak_dbfs is not None:
        print(f"  Peak level     : {peak_dbfs:.2f} dBFS (sample peak)")
    else:
        print("  Peak level     : (could not measure â€” install numpy for level metrics)")
    if rms_dbfs is not None:
        print(f"  RMS level      : {rms_dbfs:.2f} dBFS (full-mix RMS)")
    else:
        print("  RMS level      : â€”")
    if lufs is not None:
        print(f"  Loudness (LUFS): {lufs:.1f} LUFS integrated (ITU-R BS.1770-style meter)")
    elif rms_dbfs is not None:
        print("  Loudness (LUFS): not computed â€” install pyloudnorm for integrated loudness")
    else:
        print("  Loudness (LUFS): â€”")
    print()
    if include_publish_notes:
        print("  --- Publish readiness (informal) ---")
        for line in _publish_readiness_notes(peak_dbfs, lufs):
            print(f"  â€¢ {line}")
        print()


def _print_stage2_report(
    output_wav: Path,
    manifest_path: Path,
    final_timeline_path: Path,
) -> None:
    """Print the render-complete report with output audio analysis."""
    with manifest_path.open("r", encoding="utf-8") as fh:
        manifest = json.load(fh)
    resolved_count = len(manifest.get("resolved", []))
    unresolved_count = len(manifest.get("unresolved", []))
    total_assets = resolved_count + unresolved_count

    sep = "=" * 60

    print(f"\n{sep}")
    print("  RENDER COMPLETE")
    print(sep)
    print()
    print(f"  Output     : {output_wav}")
    print(f"  Manifest   : {manifest_path}")
    print()
    print_wav_output_analysis(output_wav, section_title="Output audio analysis", include_publish_notes=True)
    if unresolved_count == 0 and total_assets > 0:
        print(f"  All {total_assets} assets resolved at full confidence.")
    elif unresolved_count > 0:
        print(f"  {resolved_count}/{total_assets} assets resolved. {unresolved_count} unresolved â€” check manifest.")
    print(sep)
    print()


# ---------------------------------------------------------------------------
# Flow orchestrators
# ---------------------------------------------------------------------------

def _book_metadata_path(project_root: Path) -> Path:
    return project_root / "book_metadata.json"


def _chapter_wav_stem_from_book_metadata(meta: dict) -> str:
    """Pick filesystem stem for ``generated/<stem>.wav`` from book metadata."""
    chapters = meta.get("chapters")
    if isinstance(chapters, list) and chapters:
        active = str(meta.get("active_chapter_slug", "")).strip()
        for c in chapters:
            if not isinstance(c, dict):
                continue
            if active and c.get("slug") == active:
                title = str(c.get("title") or c.get("slug") or "").strip()
                if title:
                    stem = _sanitize_project_id(title)
                    return stem if stem != "untitled_project" else "final"
        # fallback: first chapter
        c0 = chapters[0]
        if isinstance(c0, dict):
            title = str(c0.get("title") or c0.get("slug") or "").strip()
            if title:
                stem = _sanitize_project_id(title)
                return stem if stem != "untitled_project" else "final"
    title = str(meta.get("chapter_title") or meta.get("chapter_slug") or "").strip()
    if title:
        stem = _sanitize_project_id(title)
        return stem if stem != "untitled_project" else "final"
    return "final"


def _final_render_wav_path(out_dir: Path, project_root: Path | None) -> Path:
    """Write rendered mix to ``output/generated/<chapter>.wav`` when book metadata exists.

    Uses ``chapters`` + ``active_chapter_slug`` when present; else legacy ``chapter_title``.
    Falls back to ``generated/final.wav``. Always under ``out_dir/generated/``.
    """
    gen_dir = out_dir / "generated"
    stem = "final"
    if project_root is not None:
        meta_path = _book_metadata_path(project_root)
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                meta = {}
            else:
                stem = _chapter_wav_stem_from_book_metadata(meta)
    gen_dir.mkdir(parents=True, exist_ok=True)
    return gen_dir / f"{stem}.wav"


def _narration_only_from_context_or_args(args, project_root: Path | None) -> bool:
    """Resolve narration_only from CLI or persisted project/book metadata."""
    if getattr(args, "narration_only", False):
        return True
    if project_root is None:
        return False
    ctx = _load_project_context(project_root)
    if ctx and str(ctx.get("narration_only", "")).lower() in ("true", "1", "yes"):
        return True
    meta_path = _book_metadata_path(project_root)
    if not meta_path.is_file():
        return False
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    return bool(meta.get("narration_only", False))


def _flow_stage1(
    args,
    story_path: Path,
    library_root: Path,
    out_dir: Path,
    engine1_dir: Path,
    project_root: Path | None = None,
) -> None:
    """Stage 1: analyse story, scaffold asset folders, print shopping list."""
    print("\n" + "=" * 60)
    print("[Preflight] Checking story file and environment")
    print("=" * 60)

    _preflight_story_file(story_path)
    project_type = getattr(args, "project_type", "audio_drama")
    narration_only = _narration_only_from_context_or_args(args, project_root)
    effective_no_llm = bool(args.no_llm or narration_only)
    if narration_only and not args.no_llm:
        print("  [info] Narration-only: skipping GEMINI preflight (Engine 1 uses fast text path).")
    if not effective_no_llm:
        _preflight_env(engine1_dir)
    print("  Preflight passed.")

    draft_path = _stage1_engine1(
        story_path,
        out_dir,
        engine1_dir,
        effective_no_llm,
        args.model,
        args.fallback_model,
        director=bool(getattr(args, "director", False) and not getattr(args, "no_director", False)),
        gita=getattr(args, "gita", None),
        update_gita=bool(getattr(args, "update_gita", False)),
        project_type=project_type,
        narration_only=narration_only,
    )
    _apply_delivery_preset_to_draft(draft_path, project_root, project_type, narration_only)
    _stage2_engine2_scaffold(draft_path, library_root)
    _print_stage1_report(draft_path, library_root, story_path, _build_path_args(args))


def _flow_stage2(
    args,
    library_root: Path,
    out_dir: Path,
    audio_engine_dir: Path,
    audio_library_root: Path,
    project_root: Path | None = None,
) -> None:
    """Stage 2: readiness gate, resolve, render, verify."""
    path_args = _build_path_args(args)
    draft_path = _verify_stage1_complete(out_dir, path_args)
    project_type = getattr(args, "project_type", "audio_drama")
    narration_only = _narration_only_from_context_or_args(args, project_root)
    _apply_delivery_preset_to_draft(draft_path, project_root, project_type, narration_only)

    if not narration_only:
        print("\n" + "=" * 60)
        print("[Preflight] Checking audio library")
        print("=" * 60)
        _preflight_audio_library(audio_library_root)
        print("  Preflight passed.")
    else:
        print("\n" + "=" * 60)
        print("[Preflight] Narration-only project â€” skipping shared audio library check")
        print("=" * 60)

    _check_asset_readiness(draft_path, library_root, path_args)

    final_timeline_path = _stage2_engine2_resolve(args, draft_path, library_root, out_dir)
    output_wav = _final_render_wav_path(out_dir, project_root)
    _stage3_engine3(final_timeline_path, output_wav, audio_engine_dir)

    print("\n" + "=" * 60)
    print("[Verification] Checking output quality")
    print("=" * 60)

    manifest_path = out_dir / "asset_manifest.json"
    _verify_manifest_unresolved(manifest_path)
    _verify_wav_header(output_wav)
    _verify_duration(output_wav, final_timeline_path)

    _print_stage2_report(output_wav, manifest_path, final_timeline_path)


def _flow_status(
    args,
    library_root: Path,
    out_dir: Path,
) -> None:
    """Status check: print current asset readiness without triggering anything."""
    draft_path = _verify_stage1_complete(out_dir, _build_path_args(args))

    status_cmd = [
        sys.executable, "-m", "asset_engine.cli",
        "status",
        "--draft", str(draft_path),
        "--library", str(library_root),
    ]
    status_cmd.extend(_asset_engine_resolver_args(args))
    rc = _run_with_env(status_cmd, cwd=Path(__file__).parent.resolve() / "asset_engine", extra_pythonpath=[
        Path(__file__).parent.resolve() / "asset_engine" / "src",
    ])
    sys.exit(rc)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

_EPILOG = """\
Two-stage workflow:

  Stage 1 â€” Analyse your story and create asset folders:
    python run_pipeline.py --story story.txt --project-id demo_project

  Stage 2 â€” After filling folders with audio, resolve and render (WAV under output/generated/):
    python run_pipeline.py --resume --project-id demo_project

  Narration-only audiobook (voice-only draft; Stage 2 skips shared audio/ library check):
    python run_pipeline.py --story ch.txt --project-id demo --project-type audiobook --narration-only
    python run_pipeline.py --resume --project-id demo --project-type audiobook --narration-only

  Check readiness at any time:
    python run_pipeline.py --status --project-id demo_project
"""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_pipeline",
        description="Two-stage audio-story pipeline: analyse story, source assets, render WAV.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--story",
        help="Path to the input story .txt file (required for Stage 1).",
    )
    parser.add_argument(
        "--project-id",
        default=None,
        help="Project identifier for isolated workspace paths (recommended).",
    )
    parser.add_argument(
        "--projects-root",
        default=str(_DEFAULT_PROJECTS_ROOT),
        help="Root folder containing per-project subfolders (default: workspace/projects).",
    )
    parser.add_argument(
        "--library",
        default=None,
        help="Asset library root directory (legacy/manual mode).",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output directory for generated files (legacy/manual mode).",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        default=False,
        help="Stage 2: skip story analysis, resolve assets and render.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        default=False,
        help="Print current asset readiness without running anything.",
    )
    parser.add_argument(
        "--no-llm", action="store_true", default=False,
        help="Run Engine 1 in heuristic-only mode (no LLM calls).",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Engine 1 model override (e.g. gemini-2.5-flash).",
    )
    parser.add_argument(
        "--fallback-model",
        default=None,
        help="Optional Engine 1 fallback model used if primary fails.",
    )
    parser.add_argument(
        "--director",
        action="store_true",
        default=False,
        help="Enable optional LLM Audio Director enrichment for Fountain drama scripts.",
    )
    parser.add_argument(
        "--no-director",
        action="store_true",
        default=False,
        help="Explicitly disable audio director enrichment.",
    )
    parser.add_argument(
        "--gita",
        default=None,
        help="Optional path to gita.json continuity file for Stage 1.",
    )
    parser.add_argument(
        "--update-gita",
        action="store_true",
        default=False,
        help="Update gita continuity file during Stage 1.",
    )
    parser.add_argument(
        "--allow-shared-roots",
        action="store_true",
        default=False,
        help="Allow legacy shared root folders (repo assets/ and output/).",
    )
    parser.add_argument(
        "--project-type",
        default="audio_drama",
        choices=["audiobook", "audio_drama"],
        help="AudioBook (1 narrator, no SFX) or AudioDrama (characters, SFX). "
             "Default: audio_drama.",
    )
    parser.add_argument(
        "--narration-only",
        action="store_true",
        default=False,
        help="With --project-type audiobook: voice-only draft and skip shared "
             "music/ambience/SFX library preflight on Stage 2. "
             "May also be set via book_metadata.json for a project.",
    )
    parser.add_argument(
        "--audio-library",
        default=None,
        help="Optional shared audio library root for advanced resolvers.",
    )
    parser.add_argument(
        "--music-catalog",
        default=None,
        help="Optional path to music_catalog.json for tag-based music matching.",
    )
    parser.add_argument(
        "--use-clap",
        action="store_true",
        default=False,
        help="Enable optional CLAP index lookups for SFX/ambience.",
    )
    parser.add_argument(
        "--use-freesound",
        action="store_true",
        default=False,
        help="Enable optional Freesound fallback for unresolved SFX/ambience.",
    )
    parser.add_argument(
        "--require-voice",
        action="store_true",
        default=False,
        help="Fail Stage 2 when any voice clip is unresolved.",
    )
    parser.add_argument(
        "--score-threshold",
        type=float,
        default=0.45,
        help="Minimum confidence threshold for advanced resolver matches.",
    )
    return parser
    return parser


def main() -> None:
    args = _build_parser().parse_args()

    if getattr(args, "narration_only", False) and args.project_type != "audiobook":
        print(
            "error: --narration-only is only valid with --project-type audiobook",
            file=sys.stderr,
        )
        sys.exit(2)

    repo_root = Path(__file__).parent.resolve()

    if args.project_id and (args.library or args.out):
        print(
            "error: use either --project-id or (--library and --out), not both",
            file=sys.stderr,
        )
        sys.exit(2)

    if not args.project_id and (not args.library or not args.out):
        print(
            "error: provide --project-id OR both --library and --out",
            file=sys.stderr,
        )
        sys.exit(2)

    if not args.resume and not args.status and not args.story:
        print(
            "error: --story is required when not using --resume or --status",
            file=sys.stderr,
        )
        print(
            "usage: python run_pipeline.py --story story.txt --project-id <project_id>",
            file=sys.stderr,
        )
        sys.exit(2)

    _ensure_local_import_paths(repo_root)
    engine1_dir = repo_root / "pcddj_engine" / "story-to-script"
    audio_engine_dir = repo_root / "audio_engine"
    audio_library_root = audio_engine_dir / "audio"
    project_root: Path | None = None
    if args.project_id:
        projects_root = _resolve_projects_root(args.projects_root, repo_root)
        safe_project_id, project_root, library_root, out_dir = _resolve_project_paths(
            args.project_id,
            projects_root,
        )
        args.project_id = safe_project_id
        context = _load_project_context(project_root)
        if context:
            expected_library = Path(context.get("assets_root", "")).resolve()
            expected_output = Path(context.get("output_root", "")).resolve()
            if expected_library != library_root or expected_output != out_dir:
                _fail(
                    stage="Project Context",
                    what_happened="Project context paths do not match resolved roots.",
                    next_step="Use the same --project-id and --projects-root as prior runs.",
                    diagnose_cmd=f"type \"{_project_context_path(project_root)}\"",
                )
        _persist_project_context(
            project_root,
            project_id=safe_project_id,
            projects_root=projects_root,
            library_root=library_root,
            out_dir=out_dir,
            project_type=getattr(args, "project_type", "audio_drama"),
            narration_only=bool(getattr(args, "narration_only", False)),
        )
    else:
        library_root = Path(args.library).resolve()
        out_dir = Path(args.out).resolve()

    _guard_shared_root_paths(
        repo_root=repo_root,
        library_root=library_root,
        out_dir=out_dir,
        allow_shared_roots=args.allow_shared_roots,
    )

    if args.status:
        _flow_status(args, library_root, out_dir)
    elif args.resume:
        _flow_stage2(
            args,
            library_root,
            out_dir,
            audio_engine_dir,
            audio_library_root,
            project_root=project_root,
        )
    else:
        story_path = Path(args.story).resolve()
        _flow_stage1(
            args,
            story_path,
            library_root,
            out_dir,
            engine1_dir,
            project_root=project_root,
        )


if __name__ == "__main__":
    main()







