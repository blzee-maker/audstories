"""Asset engine orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import logging
import struct
import wave

from asset_engine.assembly import build_manifest, validate_final_timeline
from asset_engine.contracts.draft_models import DraftTimeline
from asset_engine.contracts.requirements_models import TrackType
from asset_engine.requirements import extract_requirements
from asset_engine.resolvers import ResolveOptions, resolve_from_library
from asset_engine.scaffold import build_scaffold
from asset_engine.timing import compute_project_duration, compute_project_timing, compute_scene_timing
from asset_engine.pacing import apply_pacing
from asset_engine.utils.constants import MIN_CLIP_DURATION_SECONDS

logger = logging.getLogger(__name__)


def _write_silence_wav(path: Path, duration: float, sample_rate: int = 22050) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    total_frames = int(max(duration, MIN_CLIP_DURATION_SECONDS) * sample_rate)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for _ in range(total_frames):
            wav.writeframesraw(struct.pack("<h", 0))


def _build_voice_status(requirements: list, library_root: Path) -> dict[str, Any]:
    resolved: list[dict[str, Any]] = []
    placeholders: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []

    for req in requirements:
        if TrackType(str(req.asset_kind)) != TrackType.VOICE:
            continue
        item = {
            "requirement_id": req.requirement_id,
            "scene_id": req.scene_id,
            "scene_name": req.scene_name,
            "speaker": req.track_id,
            "clip_index": req.clip_index,
            "folder": str((req.metadata or {}).get("folder", "")),
            "line_text": req.tts_text or req.descriptor,
            "status": req.resolution_status.value,
            "file": req.resolved_file,
            "note": req.resolution_note,
        }
        if req.resolution_status.value == "resolved":
            resolved.append(item)
        elif req.resolution_status.value == "placeholder":
            placeholders.append(item)
        else:
            missing.append(item)

    return {
        "library_root": str(library_root),
        "summary": {
            "total_voice_requirements": len(resolved) + len(placeholders) + len(missing),
            "resolved": len(resolved),
            "placeholders": len(placeholders),
            "missing": len(missing),
        },
        "resolved": resolved,
        "placeholders": placeholders,
        "missing": missing,
    }


def run_scaffold_phase(
    *,
    draft: DraftTimeline,
    requirements: list,
    library_root: Path,
) -> dict[str, Any]:
    logger.info("Running scaffold phase for project '%s'", draft.project.name)
    scaffold = build_scaffold(
        requirements=requirements,
        library_root=library_root,
        project_name=draft.project.name,
        project_type=str(draft.settings.get("project_type", "audio_drama")),
    )
    return {
        "folders_created": scaffold.folders_created,
        "folders_unchanged": scaffold.folders_unchanged,
        "requirements_written": scaffold.requirements_written,
        "root_path": scaffold.root_path,
    }


def run_resolve_phase(
    *,
    draft: DraftTimeline,
    requirements: list,
    library_root: Path,
    output_dir: Path,
    resolve_options: ResolveOptions | None = None,
) -> dict[str, Any]:
    logger.info("Running resolve phase for project '%s'", draft.project.name)
    options = resolve_options or ResolveOptions()
    resolution = resolve_from_library(requirements, library_root, options=options)
    generated_root = output_dir / "generated" / "voice"
    default_silence = float(draft.settings.get("default_silence", 0.5))

    # Missing voice clips become generated silence placeholders.
    for req in resolution.placeholders:
        out_file = generated_root / f"{req.requirement_id.replace(':', '_')}_silence.wav"
        duration = req.estimated_duration_seconds or MIN_CLIP_DURATION_SECONDS
        _write_silence_wav(out_file, duration=duration)
        req.resolved_file = str(out_file)
        req.resolved_duration_seconds = duration
        logger.info("Generated silence placeholder for %s at %s", req.requirement_id, out_file)

    if options.require_voice:
        unresolved_voice = [
            req
            for req in requirements
            if TrackType(str(req.asset_kind)) == TrackType.VOICE and req.resolution_status.value != "resolved"
        ]
        if unresolved_voice:
            labels = ", ".join(req.requirement_id for req in unresolved_voice[:5])
            more = "..." if len(unresolved_voice) > 5 else ""
            raise ValueError(
                f"Voice required but {len(unresolved_voice)} clip(s) unresolved: {labels}{more}",
            )

    scenes_payload: list[dict[str, Any]] = []
    for scene in draft.scenes:
        scene_reqs = [req for req in requirements if req.scene_id == scene.id]
        clips, scene_duration = compute_scene_timing(scene_reqs, default_silence=default_silence)
        scene_tracks: dict[str, list[dict[str, Any]]] = {}
        for clip in clips:
            if clip.get("file") is None:
                continue
            scene_tracks.setdefault(clip["track"], []).append(
                {
                    "file": clip["file"],
                    "offset": clip["offset"],
                    "loop": clip.get("loop"),
                    "semantic_role": clip.get("semantic_role"),
                    "timing_source": clip.get("timing_source"),
                }
            )

        scenes_payload.append(
            {
                "id": scene.id,
                "name": scene.name,
                "duration": max(scene_duration, MIN_CLIP_DURATION_SECONDS),
                "energy": scene.energy,
                "rules": scene.rules,
                "tracks": scene_tracks,
            }
        )

    scenes_payload = compute_project_timing(scenes_payload)
    project_duration = compute_project_duration(scenes_payload)

    final_payload = {
        "project": {
            "name": draft.project.name,
            "duration": project_duration,
            "sample_rate": draft.project.sample_rate,
            "bit_depth": draft.project.bit_depth,
        },
        "settings": draft.settings,
        "tracks": [
            {
                "id": track.id,
                "type": track.type,
                "role": track.role,
                "gain": track.gain,
                "eq_preset": track.eq_preset,
                "semantic_role": track.semantic_role,
                "clips": [],
            }
            for track in draft.tracks
        ],
        "scenes": scenes_payload,
    }

    issues = validate_final_timeline(final_payload)
    hard_errors = [issue for issue in issues if issue.severity == "error"]
    warnings = [f"{issue.location}: {issue.message}" for issue in issues if issue.severity == "warning"]

    if hard_errors:
        messages = "\n".join(
            f"{issue.location}: {issue.message} ({issue.action})" for issue in hard_errors
        )
        raise ValueError(f"Final timeline validation failed:\n{messages}")

    manifest = build_manifest(requirements, project_name=draft.project.name)
    voice_status = _build_voice_status(requirements, library_root)
    return {
        "final_payload": final_payload,
        "manifest": manifest,
        "warnings": warnings,
        "voice_status": voice_status,
    }


def run_asset_pipeline(
    *,
    draft_timeline_path: Path,
    output_dir: Path,
    library_root: Path | None = None,
    voice_mode: str = "auto",
    voice_map_path: Path | None = None,
    resolve_options: ResolveOptions | None = None,
) -> dict[str, Any]:
    """Run full draft->final transformation and persist outputs."""
    logger.info("Starting asset pipeline: draft=%s output=%s", draft_timeline_path, output_dir)
    if library_root is None:
        raise ValueError("library_root is required for library-only pipeline mode.")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir.joinpath("generated").mkdir(parents=True, exist_ok=True)

    with draft_timeline_path.open("r", encoding="utf-8") as handle:
        draft_payload = json.load(handle)
    draft = DraftTimeline(**draft_payload)

    requirements = extract_requirements(draft)

    overrides_payload: dict[str, Any] | None = None
    overrides_path = output_dir / "pacing_overrides.json"
    if overrides_path.is_file():
        try:
            with overrides_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if isinstance(payload, dict):
                overrides_payload = payload
        except (json.JSONDecodeError, OSError):
            overrides_payload = None

    gita_pacing: dict[str, Any] | None = None
    gita_path = output_dir.parent / "gita.json"
    if gita_path.is_file():
        try:
            with gita_path.open("r", encoding="utf-8") as handle:
                gita_payload = json.load(handle)
            audio_cfg = gita_payload.get("audio") if isinstance(gita_payload, dict) else None
            pacing_cfg = audio_cfg.get("pacing") if isinstance(audio_cfg, dict) else None
            if isinstance(pacing_cfg, dict):
                gita_pacing = pacing_cfg
        except (json.JSONDecodeError, OSError):
            gita_pacing = None

    apply_pacing(
        requirements,
        draft,
        overrides=overrides_payload,
        gita_pacing=gita_pacing,
    )

    run_scaffold_phase(draft=draft, requirements=requirements, library_root=library_root)
    resolve_result = run_resolve_phase(
        draft=draft,
        requirements=requirements,
        library_root=library_root,
        output_dir=output_dir,
        resolve_options=resolve_options,
    )
    final_payload = resolve_result["final_payload"]
    manifest = resolve_result["manifest"]
    warnings = resolve_result["warnings"]
    voice_status = resolve_result["voice_status"]

    final_path = output_dir / "final_timeline.json"
    manifest_path = output_dir / "asset_manifest.json"
    voice_status_path = output_dir / "voice_status.json"

    with final_path.open("w", encoding="utf-8") as handle:
        json.dump(final_payload, handle, indent=2)
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest.model_dump(mode="json", exclude_none=True), handle, indent=2)
    with voice_status_path.open("w", encoding="utf-8") as handle:
        json.dump(voice_status, handle, indent=2)
    logger.info("Pipeline complete: final=%s manifest=%s voice_status=%s", final_path, manifest_path, voice_status_path)

    return {
        "final_timeline_path": str(final_path),
        "manifest_path": str(manifest_path),
        "voice_status_path": str(voice_status_path),
        "warnings": warnings,
    }
