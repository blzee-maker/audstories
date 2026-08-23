from pathlib import Path

from pydub import AudioSegment
from audio_engine.dsp.fades import apply_fade_in, apply_fade_out

repo_root = Path(__file__).resolve().parents[2]
canvas = AudioSegment.silent(duration=5000)
audio = AudioSegment.from_file(repo_root / "audio" / "music" / "Days.mp3")[:4000]

canvas = canvas.overlay(audio, position=500)

canvas = apply_fade_in(canvas, start_ms=500, fade_ms=1000)
canvas = apply_fade_out(
    canvas,
    clip_start_ms=500,
    clip_len_ms=len(audio),
    project_len_ms=5000,
    fade_ms=1000
)

canvas.export(repo_root / "output" / "test_fades.wav", format="wav")
print("Fade test exported.")
