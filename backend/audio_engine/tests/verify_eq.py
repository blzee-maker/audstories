"""
Quick verification that EQ system is working.
"""
from pathlib import Path

from pydub import AudioSegment
from audio_engine.dsp.eq import apply_eq_preset, apply_scene_tonal_shaping, get_preset_for_role

def main():
    # Load a test audio
    repo_root = Path(__file__).resolve().parents[1]
    audio = AudioSegment.from_file(repo_root / "audio" / "voice" / "Scene - 1.wav")
    print(f'Original audio: {len(audio)}ms, {audio.dBFS:.2f} dBFS')

    # Test role-based preset lookup
    preset = get_preset_for_role('voice')
    print(f'Voice default preset: {preset}')
    
    preset_music = get_preset_for_role('music')
    print(f'Music default preset: {preset_music}')
    
    preset_sfx = get_preset_for_role('sfx', 'impact')
    print(f'SFX impact default preset: {preset_sfx}')

    # Apply dialogue_clean preset
    eq_audio = apply_eq_preset(audio, 'dialogue_clean')
    print(f'After dialogue_clean EQ: {len(eq_audio)}ms, {eq_audio.dBFS:.2f} dBFS')

    # Apply dialogue_warm preset
    warm_eq = apply_eq_preset(audio, 'dialogue_warm')
    print(f'After dialogue_warm EQ: {len(warm_eq)}ms, {warm_eq.dBFS:.2f} dBFS')

    # Test tonal shaping with tilt
    warm_audio = apply_scene_tonal_shaping(audio, {'tilt': 'warm'})
    print(f'After warm tilt: {len(warm_audio)}ms, {warm_audio.dBFS:.2f} dBFS')

    bright_audio = apply_scene_tonal_shaping(audio, {'tilt': 'bright'})
    print(f'After bright tilt: {len(bright_audio)}ms, {bright_audio.dBFS:.2f} dBFS')

    # Test high shelf
    shelf_audio = apply_scene_tonal_shaping(audio, {'high_shelf': -3})
    print(f'After high_shelf -3dB: {len(shelf_audio)}ms, {shelf_audio.dBFS:.2f} dBFS')

    # Test low shelf
    low_shelf_audio = apply_scene_tonal_shaping(audio, {'low_shelf': 2})
    print(f'After low_shelf +2dB: {len(low_shelf_audio)}ms, {low_shelf_audio.dBFS:.2f} dBFS')

    print()
    print('=' * 50)
    print('EQ system verification complete!')
    print('=' * 50)

if __name__ == '__main__':
    main()
