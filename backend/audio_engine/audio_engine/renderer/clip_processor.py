"""
ClipProcessor handles individual clip processing with all effects.
"""
from typing import Optional, Dict, List, Tuple, Union
from pydub import AudioSegment

from audio_engine.utils.logger import get_logger
from audio_engine.utils.energy_ramp import apply_energy_ramp
from audio_engine.exceptions import FileError, AudioProcessingError, DSPError
from audio_engine.dsp.fade_curves import FadeCurve
from audio_engine.dsp.sfx_processor import apply_sfx_processing, get_sfx_fade_behavior
from audio_engine.dsp.balance import apply_role_loudness
from audio_engine.dsp.eq import apply_eq_preset, get_preset_for_role

logger = get_logger(__name__)


def clip_matches_duck_target(
    duck_target: str,
    track_role: Optional[str],
    track_type: Optional[str],
    clip_semantic_role: Optional[str],
) -> bool:
    """Return True if this clip should be ducked when the rule fires."""
    if duck_target == track_role:
        return True
    if duck_target == "music" and track_type == "music":
        return True
    if duck_target.startswith("sfx:") and track_role == "sfx":
        target_semantic_role = duck_target.split(":", 1)[1]
        return clip_semantic_role == target_semantic_role
    return False


class ClipProcessor:
    """Processes individual audio clips with gain, compression, ducking, and effects."""
    
    def __init__(
        self,
        ducking_func=None,
        compression_func=None,
        fade_in_func=None,
        fade_out_func=None
    ):
        """
        Initialize ClipProcessor with optional DSP function dependencies.
        
        Args:
            ducking_func: Function to apply ducking (default: None, will import if needed)
            compression_func: Function to apply compression (default: None, will import if needed)
            fade_in_func: Function to apply fade-in (default: None, will import if needed)
            fade_out_func: Function to apply fade-out (default: None, will import if needed)
        """
        self.ducking_func = ducking_func
        self.compression_func = compression_func
        self.fade_in_func = fade_in_func
        self.fade_out_func = fade_out_func
        
        # Lazy import if not provided
        if self.ducking_func is None:
            from audio_engine.dsp.ducking import apply_envelope_ducking
            self.ducking_func = apply_envelope_ducking
        
        if self.compression_func is None:
            from audio_engine.dsp.compression import apply_dialogue_compression
            self.compression_func = apply_dialogue_compression
        
        if self.fade_in_func is None:
            from audio_engine.dsp.fades import apply_fade_in
            self.fade_in_func = apply_fade_in
        
        if self.fade_out_func is None:
            from audio_engine.dsp.fades import apply_fade_out
            self.fade_out_func = apply_fade_out
    
    def process_clip(
        self,
        canvas: AudioSegment,
        clip: Dict,
        track_gain: float,
        project_duration: float,
        role_ranges: Optional[Dict[str, List[Tuple[float, float]]]] = None,
        track_role: Optional[str] = None,
        track_type: Optional[str] = None,
        default_ducking: Optional[Dict] = None,
        default_compression: Optional[Dict] = None,
        track_semantic_role: Optional[str] = None,
        track_eq_preset: Optional[str] = None
    ) -> AudioSegment:
        """
        Process a single clip and apply it to the canvas.
        
        Processing order (critical for reliable ducking math):
        1. Load audio
        2. Apply track/clip gain
        3. Apply EQ (role preset or explicit) ← shapes frequencies before other processing
        4. Apply SFX processing (semantic loudness, fade defaults, micro-timing)
        5. Apply energy ramp (if applicable)
        6. Apply ducking (lighter now due to EQ separation)
        7. Apply dialogue compression (if voice)
        8. Overlay to canvas
        9. Apply canvas-level fades
        
        Args:
            canvas: Audio canvas to apply clip to
            clip: Clip dictionary with file, start, and optional effects
            track_gain: Base gain for the track
            project_duration: Total project duration in seconds
            role_ranges: Dictionary of role ranges for ducking
            track_role: Mix role of the track (voice, music, background, sfx) - where it sits in mix
            track_type: Timeline track type (e.g. music); used so duck rules can target the music bed explicitly
            default_ducking: Default ducking configuration
            default_compression: Default compression configuration
            track_semantic_role: Optional track-level semantic role (what sound represents)
            track_eq_preset: Optional track-level EQ preset override
        
        Returns:
            Updated canvas with clip applied
        """
        # Validate canvas is not None
        if canvas is None:
            logger.error("Canvas is None in process_clip, cannot process clip")
            raise AudioProcessingError("Canvas is None")
        
        # Load audio file (allow internal override for streaming chunks)
        if "_audio_override" in clip and clip["_audio_override"] is not None:
            audio = clip["_audio_override"]
        else:
            if "file" not in clip:
                logger.error(f"Clip missing 'file' field: {clip}")
                raise AudioProcessingError("Clip missing 'file' field")
            
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
        
        clip_rules = clip.get("_rules", {})
        dialogue_density = clip_rules.get("dialogue_density_label")
        scene_energy = clip_rules.get("scene_energy", 0.5)
        prev_energy = clip_rules.get("prev_scene_energy")

        ducking_cfg = clip_rules.get("ducking", default_ducking)
        compression_cfg = clip_rules.get("dialogue_compression", default_compression)

        # Get semantic role: clip-level overrides track-level
        semantic_role = clip.get("semantic_role", track_semantic_role)

        # Step 2: Gain Handling
        audio = audio + track_gain
        if "gain" in clip:
            audio = audio + clip["gain"]

        # Step 3: Apply EQ (role preset or explicit)
        # EQ shapes frequencies early, enabling lighter ducking later
        # Priority: clip eq_preset > track eq_preset > role-based default
        eq_preset = clip.get("eq_preset") or track_eq_preset or get_preset_for_role(track_role, semantic_role)
        if eq_preset and not clip.get("_skip_eq"):
            try:
                audio = apply_eq_preset(audio, eq_preset)
                if audio is None:
                    logger.error(f"apply_eq_preset returned None for clip {clip.get('file', 'unknown')}")
                    raise AudioProcessingError(f"apply_eq_preset returned None")
                logger.debug(f"Applied EQ preset '{eq_preset}' to clip {clip.get('file', 'unknown')}")
            except ValueError as e:
                logger.warning(f"Unknown EQ preset '{eq_preset}' for clip {clip.get('file', 'unknown')}: {e}")
            except Exception as e:
                logger.warning(f"Failed to apply EQ preset for clip {clip.get('file', 'unknown')}: {e}")

        # Step 4/5: Apply SFX processing (semantic loudness, fade defaults, micro-timing)
        # SFX semantics must be resolved before ducking for reliable ducking math
        if track_role == "sfx" and semantic_role:
            try:
                audio = apply_sfx_processing(
                    audio=audio,
                    semantic_role=semantic_role,
                    scene_energy=scene_energy,
                    clip_rules=clip_rules
                )
                if audio is None:
                    logger.error(f"apply_sfx_processing returned None for clip {clip.get('file', 'unknown')}")
                    raise AudioProcessingError(f"apply_sfx_processing returned None")
            except Exception as e:
                logger.error(f"Failed to apply SFX processing for clip {clip.get('file', 'unknown')}: {e}")
                raise AudioProcessingError(f"Failed to apply SFX processing: {e}")
            
            # Apply semantic role-based loudness
            try:
                audio = apply_role_loudness(audio, track_role, semantic_role)
                if audio is None:
                    logger.error(f"apply_role_loudness returned None for clip {clip.get('file', 'unknown')}")
                    raise AudioProcessingError(f"apply_role_loudness returned None")
            except Exception as e:
                logger.error(f"Failed to apply role loudness for clip {clip.get('file', 'unknown')}: {e}")
                raise AudioProcessingError(f"Failed to apply role loudness: {e}")

        # Step 5: Scene Energy -> music intensity
        ramp_duration_ms = int(clip_rules.get("energy_ramp_duration", 3000))
        try:
            audio = apply_energy_ramp(
                audio=audio,
                scene_energy=scene_energy,
                prev_energy=prev_energy,
                ramp_duration_ms=ramp_duration_ms,
                track_role=track_role or ""
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
                audio = audio - 6  # strong pullback
            elif dialogue_density == "medium":
                audio = audio - 3  # gentle support
            elif dialogue_density == "low":
                audio = audio + 0  # let music breathe

        timeline_start_sec = clip.get("_timeline_start", clip["start"])
        overlay_start_sec = clip.get("_overlay_start", clip["start"])
        start_sec = timeline_start_sec
        start_ms = int(start_sec * 1000)
        overlay_start_ms = int(overlay_start_sec * 1000)

        # Looping Logic
        if clip.get("loop", False):
            loop_until = clip.get("loop_until", project_duration)
            loop_duration_ms = int((loop_until - start_sec) * 1000)
            
            if loop_duration_ms > 0:
                loops = audio * ((loop_duration_ms // len(audio)) + 1)
                audio = loops[:loop_duration_ms]

        # Step 6: Ducking (SFX semantics resolved before ducking)
        # Rules: "when" selects dialogue_ranges key (e.g. voice activity); "duck" lists mix roles / music / sfx:semantic to lower.
        # Note: EQ applied earlier enables lighter ducking due to frequency separation
        if ducking_cfg and role_ranges:
            clip_semantic_role = clip.get("semantic_role", track_semantic_role)

            for rule in ducking_cfg.get("rules", []):
                when_role = rule["when"]
                if when_role not in role_ranges:
                    continue

                duck_targets = rule.get("duck", [])
                should_duck = any(
                    clip_matches_duck_target(dt, track_role, track_type, clip_semantic_role)
                    for dt in duck_targets
                )

                if should_duck:
                    try:
                        if ducking_cfg.get("mode") == "audacity":
                            audio = self.ducking_func(
                                audio=audio,
                                clip_start_sec=start_sec,
                                dialogue_ranges=role_ranges[when_role],
                                cfg=ducking_cfg
                            )

                        if ducking_cfg.get("mode") == "scene":
                            audio = audio + ducking_cfg["duck_amount"]
                    except Exception as e:
                        logger.warning(f"Failed to apply ducking for clip {clip.get('file', 'unknown')}: {e}")

        # Step 7: Dialogue Compression (if voice)
        skip_compression = bool(clip.get("_skip_compression"))
        if not skip_compression and track_role == "voice" and compression_cfg and compression_cfg.get("enabled"):
            try:
                audio = self.compression_func(audio, compression_cfg)
            except Exception as e:
                logger.error(f"Failed to apply dialogue compression: {e}")
                raise DSPError(f"Failed to apply dialogue compression: {e}")
        
        # Validate audio is not None before overlay
        if audio is None:
            logger.error(f"Audio is None before overlay for clip {clip.get('file', 'unknown')}")
            raise AudioProcessingError(f"Audio is None before overlay")
        
        # Apply clip to canvas (overlay can be relative to chunk window)
        try:
            overlay_start_ms = int(overlay_start_sec * 1000)
            canvas = canvas.overlay(audio, position=overlay_start_ms)
            # Validate overlay returned valid canvas
            if canvas is None:
                logger.error(f"Canvas overlay returned None for clip {clip.get('file', 'unknown')}")
                raise AudioProcessingError(f"Canvas overlay returned None")
        except Exception as e:
            logger.error(f"Failed to overlay audio for clip {clip.get('file', 'unknown')}: {e}")
            raise AudioProcessingError(f"Failed to overlay audio: {e}")
        
        # Step 9: Apply canvas-level fades
        # Apply SFX fade defaults if not explicitly specified
        fade_behavior = None
        if track_role == "sfx" and semantic_role:
            fade_behavior = get_sfx_fade_behavior(semantic_role)
        
        # Fade In
        if "fade_in" in clip:
            try:
                fade_in_config = clip["fade_in"]
                fade_ms, curve = extract_fade_config(fade_in_config)
                canvas = self.fade_in_func(
                    canvas=canvas,
                    start_ms=overlay_start_ms,
                    fade_ms=fade_ms,
                    curve=curve
                )
                # Validate fade_in returned valid canvas
                if canvas is None:
                    logger.warning(f"apply_fade_in returned None for clip {clip.get('file', 'unknown')}, skipping fade")
            except Exception as e:
                logger.warning(f"Failed to apply fade_in for clip {clip.get('file', 'unknown')}: {e}")
        elif fade_behavior and fade_behavior.get("fade_in_ms", 0) > 0:
            # Apply SFX fade default
            try:
                fade_ms = fade_behavior["fade_in_ms"]
                curve = fade_behavior.get("fade_in_curve", FadeCurve.LINEAR)
                canvas = self.fade_in_func(
                    canvas=canvas,
                    start_ms=overlay_start_ms,
                    fade_ms=fade_ms,
                    curve=curve
                )
                if canvas is None:
                    logger.warning(f"apply_fade_in returned None for clip {clip.get('file', 'unknown')}, skipping fade")
            except Exception as e:
                logger.warning(f"Failed to apply SFX fade_in default for clip {clip.get('file', 'unknown')}: {e}")

        # Fade Out
        if "fade_out" in clip:
            try:
                fade_out_config = clip["fade_out"]
                fade_ms, curve = extract_fade_config(fade_out_config)
                canvas = self.fade_out_func(
                    canvas=canvas,
                    clip_start_ms=overlay_start_ms,
                    clip_len_ms=len(audio),
                    project_len_ms=int(project_duration * 1000),
                    fade_ms=fade_ms,
                    curve=curve
                )
                # Validate fade_out returned valid canvas
                if canvas is None:
                    logger.warning(f"apply_fade_out returned None for clip {clip.get('file', 'unknown')}, skipping fade")
            except Exception as e:
                logger.warning(f"Failed to apply fade_out for clip {clip.get('file', 'unknown')}: {e}")
        elif fade_behavior and fade_behavior.get("fade_out_ms", 0) > 0:
            # Apply SFX fade default
            try:
                fade_ms = fade_behavior["fade_out_ms"]
                curve = fade_behavior.get("fade_out_curve", FadeCurve.LINEAR)
                canvas = self.fade_out_func(
                    canvas=canvas,
                    clip_start_ms=overlay_start_ms,
                    clip_len_ms=len(audio),
                    project_len_ms=int(project_duration * 1000),
                    fade_ms=fade_ms,
                    curve=curve
                )
                if canvas is None:
                    logger.warning(f"apply_fade_out returned None for clip {clip.get('file', 'unknown')}, skipping fade")
            except Exception as e:
                logger.warning(f"Failed to apply SFX fade_out default for clip {clip.get('file', 'unknown')}: {e}")
        
        # Final validation before returning
        if canvas is None:
            logger.error(f"Canvas is None after processing clip {clip.get('file', 'unknown')}")
            raise AudioProcessingError(f"Canvas is None after processing clip")
        
        return canvas


def extract_fade_config(fade_config: Union[float, Dict]) -> Tuple[int, FadeCurve]:
    """
    Extract fade duration and curve from fade configuration.
    Supports both backward-compatible number format and new object format.
    
    Args:
        fade_config: Either a number (seconds) or dict with 'duration' and optional 'curve'
        
    Returns:
        Tuple of (fade_ms, FadeCurve)
    """
    if isinstance(fade_config, (int, float)):
        # Backward compatible: just a number (seconds)
        fade_ms = int(fade_config * 1000)
        curve = FadeCurve.LINEAR
    elif isinstance(fade_config, dict):
        # New format: object with duration and optional curve
        duration = fade_config.get("duration", 0.0)
        fade_ms = int(duration * 1000)
        curve_str = fade_config.get("curve", None)
        curve = FadeCurve.from_string(curve_str)
    else:
        # Invalid format, default to linear
        fade_ms = 0
        curve = FadeCurve.LINEAR
    
    return fade_ms, curve
