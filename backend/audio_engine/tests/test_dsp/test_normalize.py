from pathlib import Path

from pydub import AudioSegment
from audio_engine.dsp.normalization import normalize_peak

repo_root = Path(__file__).resolve().parents[2]
audio = AudioSegment.from_file(repo_root / "audio" / "voice" / "Scene - 1.wav")

quiet = audio - 12
loud = audio + 6

normalize_quiet = normalize_peak(quiet)
normalize_loud = normalize_peak(loud)

normalize_quiet.export(repo_root / "output" / "test_norm_quiet.wav", format="wav")
normalize_loud.export(repo_root / "output" / "test_norm_loud.wav", format="wav")

print("Quiet max dBFS:", normalize_quiet.max_dBFS)
print("Loud max dBFS:", normalize_loud.max_dBFS)
