from pathlib import Path

from pydub import AudioSegment
from audio_engine.dsp.loudness import measure_integrated_lufs

repo_root = Path(__file__).resolve().parents[1]
final_audio = AudioSegment.from_file(repo_root / "output" / "final.wav")

lufs = measure_integrated_lufs(final_audio)
print(f"Final Integrated LUFS: {lufs:.2f}")
