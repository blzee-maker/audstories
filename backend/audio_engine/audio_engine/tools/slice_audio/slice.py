import os
from pydub import AudioSegment
from audio_engine.dsp.fades import apply_fade_in, apply_fade_out

# TODO: Update the code to print the duration of the audio and ask for the duration to be sliced.

def save_audio_from_start(
    input_audio_path,
    duration_seconds,
    output_folder="trim_audio"
):
    # Create output folder if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)

    # Load audio file
    audio = AudioSegment.from_file(input_audio_path)

    # Convert seconds to milliseconds
    duration_ms = duration_seconds * 1000

    # Trim audio from start
    trimmed_audio = audio[:duration_ms]

    # Apply fade in
    trimmed_audio = apply_fade_in(trimmed_audio, start_ms=0, fade_ms=1000)

    # Apply fade out
    trimmed_audio = apply_fade_out(trimmed_audio, clip_start_ms=0, clip_len_ms=duration_ms, project_len_ms=len(audio), fade_ms=1000)

    # Output file name
    base_name = os.path.basename(input_audio_path)
    name, ext = os.path.splitext(base_name)
    output_path = os.path.join(
        output_folder,
        f"{name}_{duration_seconds}s{ext}"
    )

    # Export trimmed audio
    trimmed_audio.export(output_path, format=ext.replace(".", ""))

    print(f"Saved trimmed audio to: {output_path}")


def get_audio_duration(input_audio_path):
    audio = AudioSegment.from_file(input_audio_path)
    return len(audio) / 1000.0

def get_user_input():
    duration = float(input("Enter the duration to slice the audio in seconds: "))
    return duration

if __name__ == "__main__":
    input_audio_path = "audio/ambience/shadowless/lake_water.mp3"
    duration = get_audio_duration(input_audio_path)
    print(f"The duration of the audio is: {duration} seconds")
    user_input = get_user_input()
    print(f"The user input is: {user_input}")
    save_audio_from_start(input_audio_path, user_input)
    print(f"The audio has been sliced and saved to the output folder.")
