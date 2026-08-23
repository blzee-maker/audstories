"""Folder-first resolver with optional catalog/CLAP/freesound layers."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import shutil

from asset_engine.contracts.requirements_models import (
    AssetRequirement,
    ResolutionStatus,
    ResolveResult,
    TrackType,
)
from asset_engine.resolvers.clap_index import ClapIndex
from asset_engine.resolvers.freesound_client import cache_hit, search_top_hit
from asset_engine.resolvers.music_catalog import MusicCatalog
from asset_engine.timing.duration_probe import probe_duration_seconds
from asset_engine.utils.constants import (
    CONFIDENCE_EXACT,
    CONFIDENCE_FALLBACK,
    CONFIDENCE_MISSING,
    MISSING_AMBIENCE_POLICY,
    MISSING_MUSIC_POLICY,
    MISSING_SFX_POLICY,
    MISSING_VOICE_POLICY,
)
from asset_engine.utils.path_utils import (
    is_audio_file,
    make_asset_folder_name,
    make_voice_folder_name,
    resolve_asset_folder,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolveOptions:
    audio_library_root: Path | None = None
    music_catalog_path: Path | None = None
    use_clap: bool = False
    use_freesound: bool = False
    require_voice: bool = False
    score_threshold: float = 0.45
    freesound_max_downloads_per_run: int = 3
    cache_dir: Path | None = None


def _voice_folder_name(req: AssetRequirement) -> str:
    scene_folder = make_voice_folder_name(req.scene_index, req.scene_name, req.track_id)
    return f"{scene_folder}/clip_{req.clip_index:03d}"


def _asset_folder_name(req: AssetRequirement) -> str:
    return make_asset_folder_name(req.scene_index, req.scene_name, req.descriptor)


def _select_best_file(folder: Path, expected_stem: str) -> tuple[Path | None, float, str]:
    if not folder.exists():
        return None, CONFIDENCE_MISSING, "folder not found - scaffold may need re-run"

    files = sorted(
        [item for item in folder.iterdir() if item.is_file() and is_audio_file(item)],
        key=lambda p: p.name.lower(),
    )
    if not files:
        return None, CONFIDENCE_MISSING, "folder exists but has no audio files"

    exact = [f for f in files if f.stem.lower() == expected_stem.lower()]
    if exact:
        return exact[0], CONFIDENCE_EXACT, "exact match"

    if len(files) == 1:
        return files[0], CONFIDENCE_EXACT, "exact match"

    selected = files[0]
    note = f"multiple files found ({len(files)}), used first alphabetically: {selected.name}"
    return selected, CONFIDENCE_FALLBACK, note


def _mark_resolved(
    req: AssetRequirement,
    *,
    file_path: Path,
    confidence: float,
    note: str,
    source: str,
    score: float | None = None,
    details: dict | None = None,
) -> None:
    req.resolution_note = note
    req.resolved_file = str(file_path)
    req.resolution_status = ResolutionStatus.RESOLVED
    req.resolved_duration_seconds = probe_duration_seconds(file_path)
    req.metadata = dict(req.metadata or {})
    req.metadata["confidence"] = confidence
    req.metadata["source"] = source
    if score is not None:
        req.metadata["score"] = float(score)
    if details:
        req.metadata["details"] = dict(details)


def _mark_missing(req: AssetRequirement, kind: TrackType, result: ResolveResult, *, require_voice: bool) -> None:
    if kind == TrackType.VOICE and not require_voice:
        req.resolution_status = ResolutionStatus.PLACEHOLDER
        req.resolution_note = f"missing voice - {MISSING_VOICE_POLICY}"
        req.resolved_duration_seconds = req.estimated_duration_seconds
        result.placeholders.append(req)
    elif kind == TrackType.VOICE:
        req.resolution_status = ResolutionStatus.MISSING
        req.resolution_note = "missing voice - require_voice enabled"
    elif kind == TrackType.MUSIC:
        req.resolution_status = ResolutionStatus.SKIPPED
        req.resolution_note = f"missing music - {MISSING_MUSIC_POLICY}"
        result.skipped.append(req)
    elif kind == TrackType.AMBIENCE:
        req.resolution_status = ResolutionStatus.SKIPPED
        req.resolution_note = f"missing ambience - {MISSING_AMBIENCE_POLICY}"
        result.skipped.append(req)
    else:
        req.resolution_status = ResolutionStatus.SKIPPED
        req.resolution_note = f"missing sfx - {MISSING_SFX_POLICY}"
        result.skipped.append(req)

    req.metadata = dict(req.metadata or {})
    req.metadata.setdefault("confidence", CONFIDENCE_MISSING)
    req.metadata.setdefault("source", "missing")
    result.missing.append(req)


def _try_music_catalog(req: AssetRequirement, options: ResolveOptions) -> tuple[Path, float, str, float, dict] | None:
    if options.music_catalog_path is None or options.audio_library_root is None:
        return None
    if not options.music_catalog_path.is_file():
        return None

    try:
        catalog = MusicCatalog.load(options.music_catalog_path)
        match = catalog.find_best(req, options.audio_library_root)
    except Exception as exc:
        logger.warning("music catalog lookup failed: %s", exc)
        return None

    if match is None:
        return None
    if match.score < options.score_threshold:
        return None
    return (
        match.file_path,
        max(CONFIDENCE_FALLBACK, min(0.98, match.score)),
        f"music catalog match ({match.reason})",
        match.score,
        {"role": match.role, "tags": list(match.tags)},
    )


def _try_clap_lookup(req: AssetRequirement, options: ResolveOptions) -> tuple[Path, float, str, float, dict] | None:
    if not options.use_clap or options.audio_library_root is None:
        return None

    kind = str(req.asset_kind)
    if kind not in {"sfx", "ambience"}:
        return None

    index_path = options.audio_library_root / "index" / f"{kind}_index.json"
    if not index_path.is_file():
        return None

    query = " ".join(
        p
        for p in [req.descriptor, req.semantic_role, req.mood, req.atmosphere, req.sfx_hint]
        if p
    ).strip()
    if not query:
        return None

    try:
        idx = ClapIndex.load(index_path, kind=kind)
        candidates = idx.query(query, top_k=5)
    except Exception as exc:
        logger.warning("CLAP lookup failed (%s): %s", kind, exc)
        return None

    if not candidates:
        return None

    best = candidates[0]
    source = (options.audio_library_root / best.file_path).resolve()
    if not source.is_file():
        return None
    if best.score < options.score_threshold:
        return None

    return (
        source,
        max(CONFIDENCE_FALLBACK, min(0.95, best.score)),
        f"clap match ({best.note})",
        best.score,
        {"query": query, "index": str(index_path)},
    )


def _try_freesound(
    req: AssetRequirement,
    folder: Path,
    options: ResolveOptions,
    state: dict[str, int],
) -> tuple[Path, float, str, float, dict] | None:
    if not options.use_freesound:
        return None
    if state["downloads"] >= options.freesound_max_downloads_per_run:
        return None

    query = " ".join(p for p in [req.descriptor, req.semantic_role, req.sfx_hint, req.atmosphere] if p).strip()
    if not query:
        return None

    hit = search_top_hit(query)
    if hit is None:
        return None

    out_name = f"{folder.name}_freesound.mp3"
    cache_root = options.cache_dir or folder
    cache_file = cache_root / out_name
    downloaded = cache_hit(hit, cache_file)
    if downloaded is None or not downloaded.is_file():
        return None

    target = folder / out_name
    target.parent.mkdir(parents=True, exist_ok=True)
    if downloaded.resolve() != target.resolve():
        shutil.copy2(downloaded, target)

    state["downloads"] += 1
    return (
        target,
        CONFIDENCE_FALLBACK,
        f"freesound fallback ({hit.license})",
        0.6,
        {"source_url": hit.source_url, "license": hit.license, "author": hit.username},
    )


def resolve_from_library(
    requirements: list[AssetRequirement],
    library_root: Path,
    options: ResolveOptions | None = None,
) -> ResolveResult:
    """Resolve requirement files from scaffolded folders.

    Resolution order:
    - voice/sfx/ambience: project scaffold folder first
    - music: optional music catalog first, then project scaffold folder
    - optional CLAP for sfx/ambience if unresolved
    - optional Freesound fallback if unresolved
    """
    opts = options or ResolveOptions()
    logger.info("Resolving %d requirements from %s", len(requirements), library_root)
    result = ResolveResult()
    state = {"downloads": 0}

    for req in requirements:
        kind = TrackType(str(req.asset_kind))
        folder_name = _voice_folder_name(req) if kind == TrackType.VOICE else _asset_folder_name(req)
        folder = resolve_asset_folder(library_root, kind.value, folder_name)

        req.metadata = dict(req.metadata or {})
        req.metadata["folder"] = str(folder)

        resolved: tuple[Path, float, str, float | None, dict | None] | None = None

        if kind == TrackType.MUSIC:
            music_pick = _try_music_catalog(req, opts)
            if music_pick is not None:
                path, conf, note, score, details = music_pick
                resolved = (path, conf, note, score, details)

        if resolved is None:
            selected, confidence, confidence_note = _select_best_file(folder, expected_stem=folder.name)
            if selected is not None:
                resolved = (selected, confidence, confidence_note, None, {"resolver": "folder"})

        if resolved is None and kind in {TrackType.SFX, TrackType.AMBIENCE}:
            clap_pick = _try_clap_lookup(req, opts)
            if clap_pick is not None:
                path, conf, note, score, details = clap_pick
                resolved = (path, conf, note, score, details)

        if resolved is None and kind in {TrackType.SFX, TrackType.AMBIENCE}:
            free_pick = _try_freesound(req, folder, opts, state)
            if free_pick is not None:
                path, conf, note, score, details = free_pick
                resolved = (path, conf, note, score, details)

        if resolved is not None:
            picked, confidence, note, score, details = resolved
            source = str((details or {}).get("resolver") or (req.metadata.get("source") if req.metadata else "library"))
            if source == "folder":
                source = "project_scaffold"
            elif "source_url" in (details or {}):
                source = "freesound"
            elif "query" in (details or {}):
                source = "clap_index"
            elif kind == TrackType.MUSIC and score is not None:
                source = "music_catalog"
            else:
                source = "library"

            _mark_resolved(
                req,
                file_path=picked,
                confidence=confidence,
                note=note,
                source=source,
                score=score,
                details=details,
            )
            result.resolved.append(req)
            logger.debug("Resolved %s -> %s", req.requirement_id, picked)
            continue

        _mark_missing(req, kind, result, require_voice=opts.require_voice)
        logger.warning("Missing %s (%s): %s", req.requirement_id, kind.value, req.resolution_note)

    logger.info(
        "Resolution complete: resolved=%d placeholders=%d skipped=%d missing=%d",
        len(result.resolved),
        len(result.placeholders),
        len(result.skipped),
        len(result.missing),
    )
    return result
