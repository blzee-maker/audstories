from pathlib import Path

from pydub import AudioSegment
from audio_engine.dsp.loudness import measure_integrated_lufs

repo_root = Path(__file__).resolve().parents[2]
audio = AudioSegment.from_file(repo_root / "audio" / "voice" / "Scene - 1.wav")

lufs = measure_integrated_lufs(audio)

print(f"Intergrated LUFS: {lufs:.2f}")