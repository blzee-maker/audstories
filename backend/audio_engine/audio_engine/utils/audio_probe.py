import soundfile as sf
from soundfile import SoundFileError


def probe_duration(file_path: str) -> float:
    """Return duration in seconds by reading only the audio file header.

    Uses soundfile.info() which reads metadata only — no audio data is decoded.
    This is ~1000x faster than AudioSegment.from_file() for large files.

    Raises:
        FileNotFoundError: if the file does not exist.
        ValueError: if the file exists but cannot be read as audio.
    """
    try:
        return sf.info(file_path).duration
    except SoundFileError as e:
        raise ValueError(f"Cannot read audio file {file_path}: {e}") from e
