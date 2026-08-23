from pydub import AudioSegment
from pydub.effects import compress_dynamic_range



def apply_dialogue_compression(audio:AudioSegment,cfg:dict)->AudioSegment:
    
    """
    Apply dialogue compression using pydub's dynamic range compressor.
    This is DSP-only: AudioSegment -> AudioSegment
    """

    return compress_dynamic_range(
        audio,
        threshold=cfg.get("threshold",-18.0),
        ratio=cfg.get("ratio",4.0),
        attack=cfg.get("attack_ms",10),
        release=cfg.get("release_ms", 120)
    ) + cfg.get("makeup_gain",0)
