import json
import os
import time
from typing import Optional, Dict, List, Tuple

from pydub.effects import compress_dynamic_range
from pydub import AudioSegment


from audio_engine.utils import dialogue_density
from audio_engine.utils.logger import get_logger
from audio_engine.utils.audio_probe import probe_duration
from audio_engine.validation import validate_timeline
from audio_engine.scene_preprocessor import preprocess_scenes
from audio_engine.autofix import auto_fix_overlaps
from audio_engine.exceptions import FileError, AudioProcessingError, DSPError
from audio_engine.config import RenderConfig

logger = get_logger(__name__)

# DSP features
from audio_engine.dsp.ducking import apply_envelope_ducking
from audio_engine.dsp.compression import apply_dialogue_compression
from audio_engine.dsp.normalization import normalize_peak
from audio_engine.dsp.fades import apply_fade_in, apply_fade_out
from audio_engine.dsp.loudness import apply_lufs_target
from audio_engine.dsp.balance import apply_role_loudness
from audio_engine.dsp.eq import apply_eq_preset, get_preset_for_role

# Utils
from audio_engine.utils.debug import debug_print_timeline
from audio_engine.utils.energy import energy_to_music_gain
from audio_engine.utils.energy_ramp import interpolate_gain, apply_energy_ramp


def load_timeline(path: str) -> Dict:
    """Load timeline JSON from file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"Timeline file not found: {path}")
        raise FileError(f"Timeline file not found: {path}")
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in timeline file {path}: {e}")
        raise FileError(f"Invalid JSON in timeline file {path}: {e}")
    except Exception as e:
        logger.error(f"Failed to load timeline file {path}: {e}")
        raise FileError(f"Failed to load timeline file {path}: {e}")


def create_canvas(duration_seconds: float) -> AudioSegment:
    """Create a silent audio canvas of specified duration."""
    return AudioSegment.silent(duration=int(duration_seconds * 1000))


def get_role_ranges(tracks: List[Dict]) -> Dict[str, List[Tuple[float, float]]]:
    """
    Extract role ranges from tracks for ducking calculations.
    Supports both mix roles (voice, background, etc.) and SFX semantic roles (sfx:impact, etc.).
    
    Returns:
        Dictionary mapping role names to lists of (start, end) tuples.
        Role names can be mix roles (e.g., "voice") or semantic roles (e.g., "sfx:impact").
    """
    role_ranges: Dict[str, List[Tuple[float, float]]] = {}

    for track in tracks:
        role = track.get("role")  # mix_role
        if not role:
            continue
        
        # Get track-level semantic_role (if present)
        track_semantic_role = track.get("semantic_role")

        for clip in track.get("clips", []):
            if "file" not in clip or "start" not in clip:
                logger.warning(f"Skipping clip without file or start time in track role '{role}'")
                continue
            
            try:
                start = clip.get("start", 0)
                duration = clip.get("duration_seconds")
                if not duration:
                    duration = probe_duration(clip["file"])
                end = start + duration

                # Add mix role range
                role_ranges.setdefault(role, []).append((start, end))
                
                # If SFX track with semantic role, also add semantic role range
                if role == "sfx":
                    # Clip-level semantic_role overrides track-level
                    clip_semantic_role = clip.get("semantic_role", track_semantic_role)
                    if clip_semantic_role:
                        semantic_role_key = f"sfx:{clip_semantic_role}"
                        role_ranges.setdefault(semantic_role_key, []).append((start, end))
                        
            except FileNotFoundError:
                logger.warning(f"Audio file not found for role range calculation: {clip['file']}")
                continue
            except Exception as e:
                logger.warning(f"Failed to load audio file for role range: {clip.get('file', 'unknown')}: {e}")
                continue

    return role_ranges


def apply_clip(
    canvas: AudioSegment,
    clip: Dict,
    track_gain: float,
    project_duration: float,
    role_ranges: Optional[Dict[str, List[Tuple[float, float]]]] = None,
    track_role: Optional[str] = None,
    default_ducking: Optional[Dict] = None,
    default_compression: Optional[Dict] = None,
    track_semantic_role: Optional[str] = None,
    track_eq_preset: Optional[str] = None,
) -> AudioSegment:
    """Apply a clip to the canvas with all processing effects."""
    # Validate canvas is not None
    if canvas is None:
        logger.error("Canvas is None in apply_clip, cannot process clip")
        raise AudioProcessingError("Canvas is None")
    
    # Load audio file with error handling
    if "file" not in clip:
        logger.error(f"Clip missing 'file' field: {clip}")
        raise AudioProcessingError(f"Clip missing 'file' field")
    
    try:
        audio = AudioSegment.from_file(clip["file"])
        # Validate audio was loaded successfully
        if audio is None:
            logger.error(f"Failed to load audio file {clip['file']}: returned None")
            raise AudioProcessingError(f"Failed to load audio file {clip['file']}: returned None")
    except FileNotFoundError:
        logger.error(f"Audio file not found: {clip['file']}")
        raise FileError(f"Audio file not found: {clip['file']}")
    except Exception as e:
        logger.error(f"Failed to load audio file {clip['file']}: {e}")
        raise AudioProcessingError(f"Failed to load audio file {clip['file']}: {e}")

    clip_rules = clip.get("_rules",{})

    dialogue_density = clip_rules.get("dialogue_density_label")

    scene_energy = clip_rules.get("scene_energy", 0.5)
    prev_energy = clip_rules.get("prev_scene_energy")

    ducking_cfg = clip_rules.get("ducking", default_ducking)
    compression_cfg = clip_rules.get(
        "dialogue_compression", default_compression
    )

    # Gain Handling
    audio = audio + track_gain
    if "gain" in clip:
        audio = audio + clip["gain"]

    # EQ Presets (clip > track > role default)
    semantic_role = clip.get("semantic_role", track_semantic_role)
    eq_preset = clip.get("eq_preset") or track_eq_preset or get_preset_for_role(track_role, semantic_role)
    if eq_preset and not clip.get("_skip_eq"):
        try:
            audio = apply_eq_preset(audio, eq_preset)
            if audio is None:
                logger.error(f"apply_eq_preset returned None for clip {clip.get('file', 'unknown')}")
                raise AudioProcessingError("apply_eq_preset returned None")
            logger.debug(f"Applied EQ preset '{eq_preset}' to clip {clip.get('file', 'unknown')}")
        except ValueError as e:
            logger.warning(f"Unknown EQ preset '{eq_preset}' for clip {clip.get('file', 'unknown')}: {e}")
        except Exception as e:
            logger.warning(f"Failed to apply EQ preset for clip {clip.get('file', 'unknown')}: {e}")

    # Scene Energy -> music intensity (using extracted function)
    ramp_duration_ms = int(clip_rules.get("energy_ramp_duration", 3000))
    try:
        audio = apply_energy_ramp(
            audio=audio,
            scene_energy=scene_energy,
            prev_energy=prev_energy,
            ramp_duration_ms=ramp_duration_ms,
            track_role=track_role
        )
        # Validate energy ramp returned valid audio
        if audio is None:
            logger.error(f"apply_energy_ramp returned None for clip {clip.get('file', 'unknown')}")
            raise AudioProcessingError(f"apply_energy_ramp returned None")
    except Exception as e:
        logger.error(f"Failed to apply energy ramp for clip {clip.get('file', 'unknown')}: {e}")
        raise AudioProcessingError(f"Failed to apply energy ramp: {e}")
    
    # Dialogue density adjustments for background/music
    if track_role in ("background", "music") and dialogue_density:
        if dialogue_density == "high":
            audio = audio - 6     # strong pullback
        elif dialogue_density == "medium":
            audio = audio - 3     # gentle support
        elif dialogue_density == "low":
            audio = audio + 0     # let music breathe

            
    # 🎤 Dialogue Compression
    if track_role == "voice" and compression_cfg and compression_cfg.get("enabled"):
        try:
            audio = apply_dialogue_compression(audio, compression_cfg)
        except Exception as e:
            logger.error(f"Failed to apply dialogue compression: {e}")
            raise DSPError(f"Failed to apply dialogue compression: {e}")

    start_sec = clip["start"]
    start_ms = int(start_sec * 1000)

    # Looping Logic
    if clip.get("loop", False):
        loop_until = clip.get("loop_until", project_duration)
        loop_duration_ms = int((loop_until - start_sec)*1000)

        if loop_duration_ms > 0:
            loops = audio * ((loop_duration_ms // len(audio))+1)
            audio = loops[:loop_duration_ms]

        # Ducking (Audacity-style or fallback)
    if ducking_cfg and role_ranges:
        for rule in ducking_cfg.get("rules", []):
            when_role = rule["when"]

            if when_role in role_ranges and track_role in rule["duck"]:
                try:
                    if ducking_cfg.get("mode") == "audacity":
                        audio = apply_envelope_ducking(
                            audio=audio,
                            clip_start_sec=start_sec,
                            dialogue_ranges=role_ranges[when_role],
                            cfg=ducking_cfg
                        )
                    
                    if ducking_cfg.get("mode") == "scene":
                        audio = audio + ducking_cfg["duck_amount"]
                except Exception as e:
                    logger.warning(f"Failed to apply ducking for clip {clip.get('file', 'unknown')}: {e}")
                    # Continue without ducking rather than failing completely

    # Validate audio is not None before overlay
    if audio is None:
        logger.error(f"Audio is None before overlay for clip {clip.get('file', 'unknown')}")
        raise AudioProcessingError(f"Audio is None before overlay")
    
    try:
        canvas = canvas.overlay(audio, position=start_ms)
        # Validate overlay returned valid canvas
        if canvas is None:
            logger.error(f"Canvas overlay returned None for clip {clip.get('file', 'unknown')}")
            raise AudioProcessingError(f"Canvas overlay returned None")
    except Exception as e:
        logger.error(f"Failed to overlay audio for clip {clip.get('file', 'unknown')}: {e}")
        raise AudioProcessingError(f"Failed to overlay audio: {e}")

    # Fade In
    if "fade_in" in clip:
        try:
            canvas = apply_fade_in(
                canvas=canvas,
                start_ms=start_ms,
                fade_ms=int(clip["fade_in"] * 1000)
            )
            # Validate fade_in returned valid canvas
            if canvas is None:
                logger.warning(f"apply_fade_in returned None for clip {clip.get('file', 'unknown')}, skipping fade")
        except Exception as e:
            logger.warning(f"Failed to apply fade_in for clip {clip.get('file', 'unknown')}: {e}")
    
    # Fade Out
    if "fade_out" in clip:
        try:
            canvas = apply_fade_out(
                canvas=canvas,
                clip_start_ms=start_ms,
                clip_len_ms=len(audio),
                project_len_ms=int(project_duration * 1000),
                fade_ms=int(clip["fade_out"] * 1000)
            )
            # Validate fade_out returned valid canvas
            if canvas is None:
                logger.warning(f"apply_fade_out returned None for clip {clip.get('file', 'unknown')}, skipping fade")
        except Exception as e:
            logger.warning(f"Failed to apply fade_out for clip {clip.get('file', 'unknown')}: {e}")

    # Final validation before returning
    if canvas is None:
        logger.error(f"Canvas is None after processing clip {clip.get('file', 'unknown')}")
        raise AudioProcessingError(f"Canvas is None after processing clip")
    
    return canvas
    

# Currently not in use - because of scenes but use full for timelines without scenes
# def process_clips(track, default_silence):
#     processed=[]
#     current_time = 0.0

#     for clip in track["clips"]:
#         clip = clip.copy()

#         if "start" not in clip:
#             clip["start"]= current_time
    
#         processed.append(clip)

#         if "start" not in clip:

#             audio = AudioSegment.from_file(clip["file"])
#             duration = len(audio)/1000.0

#             current_time = clip["start"] + duration + default_silence

#     # sort by start time

#     processed.sort(key=lambda c:c["start"])
#     return processed


def render_timeline(timeline_path: str, output_path: str) -> None:
    """Main rendering function that processes timeline and generates output audio."""
    import warnings
    warnings.warn(
        "render_timeline is deprecated and will be removed in v0.3. "
        "Use audio_engine.renderer.TimelineRenderer instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    logger.info(f"Starting render: {timeline_path} -> {output_path}")
    
    try:
        timeline = load_timeline(timeline_path)
        logger.debug("Timeline loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load timeline: {e}")
        raise

    # Scene Preprocessing
    try:
        timeline = preprocess_scenes(timeline)
        logger.debug("Scene preprocessing completed")
    except Exception as e:
        logger.error(f"Scene preprocessing failed: {e}")
        raise

    # Auto-fix overlaps (per track)
    settings = timeline.get("settings", {})
    min_gap = settings.get("default_silence", 0.0)

    for track in timeline.get("tracks", []):
        try:
            auto_fix_overlaps(track, min_gap=min_gap)
        except Exception as e:
            logger.warning(f"Failed to auto-fix overlaps for track {track.get('id', 'unknown')}: {e}")

    # validate
    warnings = validate_timeline(timeline)
    for w in warnings:
        logger.warning(f"⚠ {w}")

    
    if settings.get("debug", False):
        debug_print_timeline(timeline)

    duration = timeline["project"]["duration"]
    settings = timeline.get("settings",{})
    
    role_ranges = None

    default_ducking = settings.get("ducking")
    default_silence = settings.get("default_silence",0)
    default_compression = settings.get("dialogue_compression")

    
    if default_ducking and default_ducking.get("enabled"):
        try:
            role_ranges = get_role_ranges(timeline["tracks"])
            logger.debug("Role ranges calculated for ducking")
        except Exception as e:
            logger.warning(f"Failed to calculate role ranges, ducking may not work: {e}")
            role_ranges = None

    canvas = create_canvas(duration)
    logger.debug(f"Created canvas of {duration}s duration")

    for track in timeline["tracks"]:
        track_id = track.get("id", "unknown")
        track_gain = track.get("gain", 0)
        track_role = track.get("role")
        track_semantic_role = track.get("semantic_role")
        track_eq_preset = track.get("eq_preset")
        clips = track.get("clips", [])
        
        logger.debug(f"Processing track '{track_id}' (role: {track_role}, clips: {len(clips)})")

        track_buffer = create_canvas(duration)

        for clip in clips:
            try:
                # Ensure track_buffer is valid before processing
                if track_buffer is None:
                    logger.warning(f"Track buffer is None, recreating for track '{track_id}'")
                    track_buffer = create_canvas(duration)
                
                track_buffer = apply_clip(
                    track_buffer, 
                    clip, 
                    track_gain,
                    duration,
                    role_ranges=role_ranges,
                    track_role=track_role,
                    default_ducking=default_ducking,
                    default_compression=default_compression,
                    track_semantic_role=track_semantic_role,
                    track_eq_preset=track_eq_preset,
                )
                
                # Validate that apply_clip returned a valid AudioSegment
                if track_buffer is None:
                    logger.error(f"apply_clip returned None for clip {clip.get('file', 'unknown')}, recreating track buffer")
                    track_buffer = create_canvas(duration)
            except (FileError, AudioProcessingError) as e:
                logger.error(f"Skipping clip {clip.get('file', 'unknown')} due to error: {e}")
                continue  # Skip this clip but continue processing others
            except Exception as e:
                logger.error(f"Unexpected error processing clip {clip.get('file', 'unknown')}: {e}")
                # Ensure track_buffer remains valid after exception
                if track_buffer is None:
                    track_buffer = create_canvas(duration)
                continue

        # Apply role-based loudness only if track_buffer is valid
        if track_buffer is not None:
            try:
                track_buffer = apply_role_loudness(track_buffer, track_role)
                # Validate that apply_role_loudness returned a valid AudioSegment
                if track_buffer is None:
                    logger.warning(f"apply_role_loudness returned None for track '{track_id}', recreating track buffer")
                    track_buffer = create_canvas(duration)
            except Exception as e:
                logger.warning(f"Failed to apply role loudness to track '{track_id}': {e}")
                # Ensure track_buffer remains valid after exception
                if track_buffer is None:
                    track_buffer = create_canvas(duration)
        else:
            logger.warning(f"Track buffer is None for track '{track_id}', skipping role loudness")

        # Only overlay if track_buffer is valid
        if track_buffer is not None:
            canvas = canvas.overlay(track_buffer)
        else:
            logger.warning(f"Skipping overlay for track '{track_id}' due to None track_buffer")
        logger.debug(f"Track '{track_id}' mixed into canvas")

    # Master Gain
    master_gain = settings.get("master_gain", 0)
    if master_gain != 0:
        canvas = canvas + master_gain
        logger.debug(f"Applied master gain: {master_gain}dB")

    # LUFS Correction
    loudness_cfg = settings.get("loudness")
    if loudness_cfg and loudness_cfg.get("enabled"):
        try:
            target_lufs = loudness_cfg.get("target_lufs", -20.0)
            canvas = apply_lufs_target(audio=canvas, target_lufs=target_lufs)
            logger.debug(f"Applied LUFS normalization to {target_lufs} LUFS")
        except Exception as e:
            logger.warning(f"Failed to apply LUFS normalization: {e}")

    # Normalization
    if settings.get("normalize", False):
        try:
            canvas = normalize_peak(canvas, target_dbfs=-1.0)
            logger.debug("Applied peak normalization")
        except Exception as e:
            logger.warning(f"Failed to apply peak normalization: {e}")

    # 🎬 Master Fade Out (end of story)
    fade_cfg = RenderConfig.merge_master_fade_out(settings)
    if fade_cfg:
        try:
            fade_duration_sec = fade_cfg.get("duration", 10.0)
            fade_ms = int(fade_duration_sec * 1000)
            fade_ms = min(fade_ms, len(canvas))
            canvas = canvas.fade_out(fade_ms)
            logger.debug(f"Applied master fade-out: {fade_duration_sec}s")
        except Exception as e:
            logger.warning(f"Failed to apply master fade-out: {e}")


    # Export final audio
    try:
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        canvas.export(output_path, format="wav")
        logger.info(f"Audio exported successfully to {output_path}")
    except Exception as e:
        logger.error(f"Failed to export audio to {output_path}: {e}")
        raise FileError(f"Failed to export audio to {output_path}: {e}")

