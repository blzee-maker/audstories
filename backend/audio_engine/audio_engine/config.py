"""
Configuration dataclass for render settings.
"""
from dataclasses import dataclass
from typing import Any, Dict, Optional

# Applied when timelines omit ``master_fade_out`` or set only partial fields,
# unless ``master_fade_out.enabled`` is explicitly False.
DEFAULT_MASTER_FADE_OUT: Dict[str, Any] = {
    "enabled": True,
    "duration": 2.0,
    "curve": "logarithmic",
}


@dataclass
class RenderConfig:
    """Configuration for rendering operations."""
    target_lufs: float = -20.0
    normalize_peak: bool = False
    peak_target_dbfs: float = -1.0
    master_gain: float = 0.0
    master_fade_out: Optional[Dict[str, Any]] = None
    loudness: Optional[Dict[str, Any]] = None
    default_silence: float = 0.0
    streaming_enabled: bool = False
    chunk_size_sec: float = 1.0
    streaming_max_workers: int = 4
    streaming_two_pass_lufs: bool = True
    streaming_sample_rate: int = 44100
    streaming_channels: int = 2
    streaming_sample_width: int = 2
    debug: bool = False

    @staticmethod
    def merge_master_fade_out(settings: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Effective master fade-out: default on unless ``enabled`` is explicitly false."""
        raw = settings.get("master_fade_out")
        if isinstance(raw, dict) and raw.get("enabled") is False:
            return None
        overlay: Dict[str, Any] = dict(raw) if isinstance(raw, dict) else {}
        merged: Dict[str, Any] = {**DEFAULT_MASTER_FADE_OUT, **overlay}
        if merged.get("enabled") is False:
            return None
        return merged

    @classmethod
    def from_timeline_settings(cls, settings: Dict[str, Any]) -> 'RenderConfig':
        """Create RenderConfig from timeline settings dictionary."""
        loudness_cfg = settings.get("loudness", {})
        streaming_cfg = settings.get("streaming", {})

        return cls(
            target_lufs=loudness_cfg.get("target_lufs", -20.0) if loudness_cfg.get("enabled") else -20.0,
            normalize_peak=settings.get("normalize", False),
            peak_target_dbfs=float(settings.get("peak_target_dbfs", -1.0)),
            master_gain=settings.get("master_gain", 0.0),
            master_fade_out=cls.merge_master_fade_out(settings),
            loudness=loudness_cfg if loudness_cfg.get("enabled") else None,
            default_silence=settings.get("default_silence", 0.0),
            streaming_enabled=bool(streaming_cfg.get("enabled", False)),
            chunk_size_sec=float(streaming_cfg.get("chunk_size_sec", 1.0)),
            streaming_max_workers=int(streaming_cfg.get("max_workers", 4)),
            streaming_two_pass_lufs=bool(streaming_cfg.get("two_pass_lufs", True)),
            streaming_sample_rate=int(streaming_cfg.get("sample_rate", 44100)),
            streaming_channels=int(streaming_cfg.get("channels", 2)),
            streaming_sample_width=int(streaming_cfg.get("sample_width", 2)),
            debug=bool(settings.get("debug", False)),
        )
