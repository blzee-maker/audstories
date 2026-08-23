"""
ClipScheduler: compute which clips are active in a given time window.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

from pydub.utils import mediainfo

from audio_engine.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ClipSlice:
    track_id: str
    clip: Dict
    file_path: str
    source_start_sec: float
    duration_sec: float
    output_start_sec: float


class ClipScheduler:
    """
    Determines which clips overlap each time chunk, including looped clips.
    """

    def __init__(self, timeline: Dict):
        self.timeline = timeline
        self._duration_cache: Dict[str, float] = {}
        self.project_duration = float(timeline.get("project", {}).get("duration", 0.0))
        self.tracks = timeline.get("tracks", [])

    def _get_audio_duration(self, file_path: str) -> float:
        if file_path in self._duration_cache:
            return self._duration_cache[file_path]

        try:
            info = mediainfo(file_path)
            duration = float(info.get("duration", 0.0))
        except Exception as exc:
            logger.warning(f"Failed to probe duration for {file_path}: {exc}")
            duration = 0.0

        self._duration_cache[file_path] = duration
        return duration

    def get_active_clips(
        self,
        chunk_start: float,
        chunk_end: float,
    ) -> Dict[str, List[ClipSlice]]:
        """
        Return a mapping of track_id -> list of ClipSlice overlapping this chunk.
        """
        active: Dict[str, List[ClipSlice]] = {}

        for track in self.tracks:
            track_id = track.get("id", "unknown")
            for clip in track.get("clips", []):
                file_path = clip.get("file")
                start = float(clip.get("start", 0.0))

                if not file_path:
                    continue

                if clip.get("loop", False):
                    loop_until = float(clip.get("loop_until", self.project_duration))
                    self._add_looped_slices(
                        active,
                        track_id,
                        clip,
                        file_path,
                        start,
                        loop_until,
                        chunk_start,
                        chunk_end,
                    )
                else:
                    duration = self._get_audio_duration(file_path)
                    end = start + duration
                    if end <= chunk_start or start >= chunk_end:
                        continue

                    overlap_start = max(start, chunk_start)
                    overlap_end = min(end, chunk_end)
                    slice_duration = max(0.0, overlap_end - overlap_start)
                    if slice_duration <= 0:
                        continue

                    source_start = overlap_start - start
                    active.setdefault(track_id, []).append(
                        ClipSlice(
                            track_id=track_id,
                            clip=clip,
                            file_path=file_path,
                            source_start_sec=source_start,
                            duration_sec=slice_duration,
                            output_start_sec=overlap_start,
                        )
                    )

        return active

    def _add_looped_slices(
        self,
        active: Dict[str, List[ClipSlice]],
        track_id: str,
        clip: Dict,
        file_path: str,
        clip_start: float,
        loop_until: float,
        chunk_start: float,
        chunk_end: float,
    ) -> None:
        duration = self._get_audio_duration(file_path)
        if duration <= 0:
            return

        window_start = max(chunk_start, clip_start)
        window_end = min(chunk_end, loop_until)
        if window_end <= window_start:
            return

        current_pos = window_start
        while current_pos < window_end:
            offset_in_loop = (current_pos - clip_start) % duration
            remaining_in_loop = duration - offset_in_loop
            slice_end = min(current_pos + remaining_in_loop, window_end)
            slice_duration = slice_end - current_pos

            if slice_duration > 0:
                active.setdefault(track_id, []).append(
                    ClipSlice(
                        track_id=track_id,
                        clip=clip,
                        file_path=file_path,
                        source_start_sec=offset_in_loop,
                        duration_sec=slice_duration,
                        output_start_sec=current_pos,
                    )
                )

            current_pos = slice_end
