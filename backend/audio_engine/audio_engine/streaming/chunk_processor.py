"""
ChunkProcessor: process a time window using parallel track workers.
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

from pydub import AudioSegment

from audio_engine.dsp.loudness import audiosegment_to_float
from audio_engine.dsp.streaming_compressor import StreamingCompressor
from audio_engine.dsp.streaming_eq import StreamingHighPass, StreamingLowPass, StreamingPeakEQ
from audio_engine.dsp.eq import _numpy_to_audiosegment, get_preset_config, get_preset_for_role
from audio_engine.renderer.clip_processor import ClipProcessor
from audio_engine.streaming.clip_scheduler import ClipScheduler, ClipSlice
from audio_engine.streaming.chunk_loader import ChunkLoader
from audio_engine.utils.logger import get_logger

logger = get_logger(__name__)


class ChunkProcessor:
    """
    Process a single chunk window with parallel per-track workers.
    """

    def __init__(
        self,
        clip_processor: Optional[ClipProcessor] = None,
        max_workers: int = 4,
        sample_rate: Optional[int] = None,
        channels: Optional[int] = None,
        sample_width: Optional[int] = None,
    ):
        self.clip_processor = clip_processor or ClipProcessor()
        self.max_workers = max_workers
        self.sample_rate = sample_rate
        self.channels = channels
        self.sample_width = sample_width
        self._streaming_compressors: Dict[str, StreamingCompressor] = {}
        self._streaming_eq_chains: Dict[str, List] = {}
        self._chunk_loaders: Dict[str, ChunkLoader] = {}

    def reset_streaming_state(self) -> None:
        self._streaming_compressors.clear()
        self._streaming_eq_chains.clear()
        self._chunk_loaders.clear()

    def _get_streaming_compressor(
        self,
        track_id: str,
        compression_cfg: Dict,
        sample_rate: int,
    ) -> StreamingCompressor:
        compressor = self._streaming_compressors.get(track_id)
        if compressor is None:
            compressor = StreamingCompressor(
                sample_rate=sample_rate,
                threshold_db=float(compression_cfg.get("threshold", -18.0)),
                ratio=float(compression_cfg.get("ratio", 4.0)),
                attack_ms=float(compression_cfg.get("attack_ms", 10.0)),
                release_ms=float(compression_cfg.get("release_ms", 120.0)),
                makeup_gain_db=float(compression_cfg.get("makeup_gain", 0.0)),
            )
            self._streaming_compressors[track_id] = compressor
        return compressor

    def _get_streaming_eq_chain(
        self,
        chain_key: str,
        preset_name: str,
        sample_rate: int,
    ) -> Optional[List]:
        chain = self._streaming_eq_chains.get(chain_key)
        if chain is not None:
            return chain

        try:
            config = get_preset_config(preset_name)
        except ValueError as exc:
            logger.warning(f"Unknown EQ preset '{preset_name}', skipping streaming EQ: {exc}")
            return None

        chain = []
        if "high_pass" in config:
            chain.append(StreamingHighPass(config["high_pass"], sample_rate))
        if "low_pass" in config:
            chain.append(StreamingLowPass(config["low_pass"], sample_rate))
        if "primary" in config:
            primary = config["primary"]
            chain.append(
                StreamingPeakEQ(
                    freq_hz=primary.get("freq", 1000),
                    gain_db=primary.get("gain", 0),
                    q=primary.get("q", 1.0),
                    sample_rate=sample_rate,
                )
            )

        self._streaming_eq_chains[chain_key] = chain
        return chain

    def _get_chunk_loader(self, file_path: str) -> ChunkLoader:
        loader = self._chunk_loaders.get(file_path)
        if loader is None:
            loader = ChunkLoader(file_path)
            self._chunk_loaders[file_path] = loader
        return loader

    def process_chunk(
        self,
        clip_scheduler: ClipScheduler,
        chunk_start: float,
        chunk_end: float,
        role_ranges: Optional[Dict[str, List]] = None,
        default_ducking: Optional[Dict] = None,
        default_compression: Optional[Dict] = None,
    ) -> AudioSegment:
        """
        Process all tracks within a time chunk and return mixed AudioSegment.
        """
        chunk_duration = max(0.0, chunk_end - chunk_start)
        chunk_ms = int(chunk_duration * 1000)
        if chunk_ms <= 0:
            return AudioSegment.silent(duration=0)

        active = clip_scheduler.get_active_clips(chunk_start, chunk_end)
        tracks = {track.get("id", "unknown"): track for track in clip_scheduler.tracks}

        def process_track(track_id: str, slices: List[ClipSlice]) -> AudioSegment:
            track = tracks.get(track_id, {})
            track_gain = track.get("gain", 0.0)
            track_role = track.get("role")
            track_type = track.get("type")
            track_semantic_role = track.get("semantic_role")
            track_eq_preset = track.get("eq_preset")
            track_streaming_compression = (
                track_role == "voice"
                and default_compression
                and default_compression.get("enabled")
            )

            buffer = AudioSegment.silent(duration=chunk_ms, frame_rate=self.sample_rate or 44100)
            if self.channels and buffer.channels != self.channels:
                buffer = buffer.set_channels(self.channels)
            if self.sample_width and buffer.sample_width != self.sample_width:
                buffer = buffer.set_sample_width(self.sample_width)
            for clip_slice in slices:
                try:
                    loader = self._get_chunk_loader(clip_slice.file_path)
                    samples, meta = loader.get_chunk(
                        start_sec=clip_slice.source_start_sec,
                        duration_sec=clip_slice.duration_sec,
                        target_sample_rate=self.sample_rate,
                        target_channels=self.channels,
                        target_sample_width=self.sample_width,
                    )
                    audio = _numpy_to_audiosegment(
                        samples,
                        sample_rate=meta.sample_rate,
                        sample_width=meta.sample_width,
                        channels=meta.channels,
                    )

                    clip_semantic_role = clip_slice.clip.get("semantic_role", track_semantic_role)
                    eq_preset = (
                        clip_slice.clip.get("eq_preset")
                        or track_eq_preset
                        or get_preset_for_role(track_role, clip_semantic_role)
                    )
                    chain = None
                    if eq_preset:
                        chain_key = f"{track_id}:{clip_slice.clip.get('id') or clip_slice.file_path}:{clip_slice.clip.get('start', 0)}:{eq_preset}"
                        chain = self._get_streaming_eq_chain(
                            chain_key=chain_key,
                            preset_name=eq_preset,
                            sample_rate=audio.frame_rate,
                        )
                        if chain:
                            samples = audiosegment_to_float(audio)
                            for eq_filter in chain:
                                samples = eq_filter.process_chunk(samples)
                            audio = _numpy_to_audiosegment(
                                samples,
                                sample_rate=audio.frame_rate,
                                sample_width=audio.sample_width,
                                channels=audio.channels,
                            )

                    clip_copy = dict(clip_slice.clip)
                    clip_copy["_audio_override"] = audio
                    clip_copy["_timeline_start"] = clip_slice.output_start_sec
                    clip_copy["_overlay_start"] = clip_slice.output_start_sec - chunk_start
                    if track_streaming_compression:
                        clip_copy["_skip_compression"] = True
                    if eq_preset and chain:
                        clip_copy["_skip_eq"] = True

                    buffer = self.clip_processor.process_clip(
                        canvas=buffer,
                        clip=clip_copy,
                        track_gain=track_gain,
                        project_duration=clip_scheduler.project_duration,
                        role_ranges=role_ranges,
                        track_role=track_role,
                        track_type=track_type,
                        default_ducking=default_ducking,
                        default_compression=default_compression,
                        track_semantic_role=track_semantic_role,
                        track_eq_preset=track_eq_preset,
                    )
                except Exception as exc:
                    logger.warning(f"Failed to process clip slice in track {track_id}: {exc}")
                    continue

            if track_role != "sfx":
                try:
                    from audio_engine.dsp.balance import apply_role_loudness
                    buffer = apply_role_loudness(buffer, track_role)
                except Exception as exc:
                    logger.warning(f"Failed to apply role loudness for track {track_id}: {exc}")

            if track_streaming_compression:
                try:
                    compressor = self._get_streaming_compressor(
                        track_id=track_id,
                        compression_cfg=default_compression,
                        sample_rate=buffer.frame_rate,
                    )
                    samples = audiosegment_to_float(buffer)
                    processed = compressor.process_chunk(samples)
                    buffer = _numpy_to_audiosegment(
                        processed,
                        sample_rate=buffer.frame_rate,
                        sample_width=buffer.sample_width,
                        channels=buffer.channels,
                    )
                except Exception as exc:
                    logger.warning(f"Failed to apply streaming compression for track {track_id}: {exc}")

            return buffer

        # Stage 1: parallel track processing
        track_buffers: Dict[str, AudioSegment] = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(process_track, track_id, slices): track_id
                for track_id, slices in active.items()
            }
            for future in futures:
                track_id = futures[future]
                track_buffers[track_id] = future.result()

        # Stage 2: bus mixing (controlled)
        mixed = AudioSegment.silent(duration=chunk_ms, frame_rate=self.sample_rate or 44100)
        if self.channels and mixed.channels != self.channels:
            mixed = mixed.set_channels(self.channels)
        if self.sample_width and mixed.sample_width != self.sample_width:
            mixed = mixed.set_sample_width(self.sample_width)
        for track_id in sorted(track_buffers.keys()):
            try:
                mixed = mixed.overlay(track_buffers[track_id])
            except Exception as exc:
                logger.warning(f"Failed to mix track {track_id}: {exc}")

        return mixed
