"""
Custom exception classes for the audio engine.
"""
from audio_engine.validation import ValidationError


class AudioEngineError(Exception):
    """Base exception for all audio engine errors."""
    pass


class AudioProcessingError(AudioEngineError):
    """Raised when audio processing operations fail."""
    pass


class DSPError(AudioEngineError):
    """Raised when DSP (Digital Signal Processing) operations fail."""
    pass


class TimelineError(AudioEngineError):
    """Raised when timeline-related operations fail."""
    pass


class FileError(AudioEngineError):
    """Raised when file operations fail."""
    pass


# Re-export ValidationError for consistency
__all__ = ['AudioEngineError', 'AudioProcessingError', 'DSPError', 'TimelineError', 'FileError', 'ValidationError']
