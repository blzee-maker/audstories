def energy_to_music_gain(energy: float) -> float:
    """
    Maps scene energy (0.0–1.0) to music gain offset in dB.

    0.0 → very restrained
    0.5 → neutral
    1.0 → full presence
    """
    energy = max(0.0, min(1.0, energy))

    min_gain = -8.0   # calm scenes
    max_gain = 0.0    # intense scenes

    return min_gain + (max_gain - min_gain) * energy
