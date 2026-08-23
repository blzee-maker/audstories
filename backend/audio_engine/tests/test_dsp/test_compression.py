from pathlib import Path

from pydub import AudioSegment
from audio_engine.dsp.compression import apply_dialogue_compression

# Load raw dialogue
repo_root = Path(__file__).resolve().parents[2]
audio = AudioSegment.from_file(repo_root / "audio" / "voice" / "Scene - 1.wav")

# Compression config
cfg = {
    "enabled": True,
    "threshold": -30,
    "ratio": 8,
    "attack_ms": 5,
    "release_ms": 200,
    "makeup_gain": 6
}

# Apply compression
compressed = apply_dialogue_compression(audio, cfg)

# Export result
compressed.export(repo_root / "output" / "test_compression.wav", format="wav")

print("Original:")
print("  Avg dBFS:", audio.dBFS)
print("  Peak dBFS:", audio.max_dBFS)

print("Compressed:")
print("  Avg dBFS:", compressed.dBFS)
print("  Peak dBFS:", compressed.max_dBFS)


print("Compression test exported.")
