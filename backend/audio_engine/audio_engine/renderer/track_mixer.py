"""
TrackMixer handles track-level operations and mixing.
"""
from typing import Optional, Dict, List, Tuple
from pydub import AudioSegment

from audio_engine.utils.logger import get_logger
from audio_engine.renderer.clip_processor import ClipProcessor
from audio_engine.exceptions import FileError, AudioProcessingError
from audio_engine.dsp.eq import apply_scene_tonal_shaping

logger = get_logger(__name__)


class TrackMixer:
    """Mixes multiple clips on a track and applies track-level effects."""
    
    def __init__(self, clip_processor: ClipProcessor):
        """
        Initialize TrackMixer with a ClipProcessor.
        
        Args:
            clip_processor: ClipProcessor instance for processing individual clips
        """
        self.clip_processor = clip_processor
    
    def process_track(
        self,
        track: Dict,
        project_duration: float,
        role_ranges: Optional[Dict[str, List[Tuple[float, float]]]] = None,
        default_ducking: Optional[Dict] = None,
        default_compression: Optional[Dict] = None
    ) -> AudioSegment:
        """
        Process all clips on a track and return mixed track buffer.
        
        Args:
            track: Track dictionary with clips and settings
            project_duration: Total project duration in seconds
            role_ranges: Dictionary of role ranges for ducking
            default_ducking: Default ducking configuration
            default_compression: Default compression configuration
        
        Returns:
            Mixed audio segment for the track
        """
        track_id = track.get("id", "unknown")
        track_gain = track.get("gain", 0)
        track_role = track.get("role")  # mix_role
        track_type = track.get("type")
        track_semantic_role = track.get("semantic_role")  # semantic_role
        track_eq_preset = track.get("eq_preset")  # track-level EQ preset override
        clips = track.get("clips", [])
        
        logger.debug(f"Processing track '{track_id}' (role: {track_role}, semantic_role: {track_semantic_role}, eq_preset: {track_eq_preset}, clips: {len(clips)})")
        
        # Create track buffer
        track_buffer = AudioSegment.silent(duration=int(project_duration * 1000))
        
        # Process each clip
        for clip in clips:
            try:
                # Ensure track_buffer is valid before processing
                if track_buffer is None:
                    logger.warning(f"Track buffer is None, recreating for track '{track_id}'")
                    track_buffer = AudioSegment.silent(duration=int(project_duration * 1000))
                
                track_buffer = self.clip_processor.process_clip(
                    canvas=track_buffer,
                    clip=clip,
                    track_gain=track_gain,
                    project_duration=project_duration,
                    role_ranges=role_ranges,
                    track_role=track_role,
                    track_type=track_type,
                    default_ducking=default_ducking,
                    default_compression=default_compression,
                    track_semantic_role=track_semantic_role,
                    track_eq_preset=track_eq_preset
                )
                
                # Validate that process_clip returned a valid AudioSegment
                if track_buffer is None:
                    logger.error(f"process_clip returned None for clip {clip.get('file', 'unknown')}, recreating track buffer")
                    track_buffer = AudioSegment.silent(duration=int(project_duration * 1000))
            except (FileError, AudioProcessingError) as e:
                logger.error(f"Skipping clip {clip.get('file', 'unknown')} due to error: {e}")
                # Ensure track_buffer remains valid after exception
                if track_buffer is None:
                    track_buffer = AudioSegment.silent(duration=int(project_duration * 1000))
                continue
            except Exception as e:
                logger.error(f"Unexpected error processing clip {clip.get('file', 'unknown')}: {e}")
                # Ensure track_buffer remains valid after exception
                if track_buffer is None:
                    track_buffer = AudioSegment.silent(duration=int(project_duration * 1000))
                continue
        
        # Apply role-based loudness only if track_buffer is valid
        # Note: For SFX tracks, semantic role loudness is already applied per-clip in ClipProcessor
        # This is a fallback for non-SFX tracks or if per-clip processing was skipped
        if track_buffer is not None and track_role != "sfx":
            try:
                from audio_engine.dsp.balance import apply_role_loudness
                track_buffer = apply_role_loudness(track_buffer, track_role)
                # Validate that apply_role_loudness returned a valid AudioSegment
                if track_buffer is None:
                    logger.warning(f"apply_role_loudness returned None for track '{track_id}', recreating track buffer")
                    track_buffer = AudioSegment.silent(duration=int(project_duration * 1000))
            except Exception as e:
                logger.warning(f"Failed to apply role loudness to track '{track_id}': {e}")
                # Ensure track_buffer remains valid after exception
                if track_buffer is None:
                    track_buffer = AudioSegment.silent(duration=int(project_duration * 1000))
        elif track_buffer is None:
            logger.warning(f"Track buffer is None for track '{track_id}', skipping role loudness")
            track_buffer = AudioSegment.silent(duration=int(project_duration * 1000))
        
        logger.debug(f"Track '{track_id}' processed successfully")
        return track_buffer
    
    @staticmethod
    def apply_tonal_shaping(
        audio: AudioSegment,
        scene_eq: Dict
    ) -> AudioSegment:
        """
        Apply scene-level tonal shaping to audio.
        
        This is a convenience method that wraps the EQ module's
        apply_scene_tonal_shaping function.
        
        Scene-level EQ is restricted to broad tonal shaping only:
        - tilt: "warm", "neutral", or "bright"
        - high_shelf: dB adjustment above ~4kHz
        - low_shelf: dB adjustment below ~200Hz
        
        Args:
            audio: Audio segment to process
            scene_eq: Scene EQ configuration dict
        
        Returns:
            Tonally shaped audio segment
        """
        if audio is None:
            logger.warning("Cannot apply tonal shaping: audio is None")
            return audio
        
        if not scene_eq:
            return audio
        
        try:
            return apply_scene_tonal_shaping(audio, scene_eq)
        except Exception as e:
            logger.warning(f"Failed to apply scene tonal shaping: {e}")
            return audio