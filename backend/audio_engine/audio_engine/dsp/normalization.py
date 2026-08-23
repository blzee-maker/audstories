from pydub import AudioSegment


def normalize_peak(audio: AudioSegment, target_dbfs: float=-1.0)->AudioSegment:
    """
    Peak normalization.
    Raises or lowers gain so max peak reaches target_dbfs.
    """

    if audio.max_dBFS == float("-inf"):
        return audio # silent audio

    gain_needed = target_dbfs - audio.max_dBFS
    return audio.apply_gain(gain_needed)