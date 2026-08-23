from pathlib import Path

from pydub import AudioSegment
from audio_engine.dsp.loudness import measure_integrated_lufs, apply_lufs_target

repo_root = Path(__file__).resolve().parents[2]
audio = AudioSegment.from_file(repo_root / "audio" / "voice" / "Scene - 1.wav")

before = measure_integrated_lufs(audio)
print(f"Before: {before:.2f} LUFS")

corrected = apply_lufs_target(audio, target_lufs=-18.0)

after = measure_integrated_lufs(corrected)
print(f"After: {after:.2f} LUFS")

corrected.export(repo_root / "output" / "scene1_lufs_corrected.wav", format="wav")