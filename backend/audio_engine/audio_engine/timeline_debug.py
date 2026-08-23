import os

from pydub import AudioSegment

def debug_print_timeline(timeline: dict):
    print("\n" + "=" * 60)
    print("📊 TIMELINE DEBUG VIEW")
    print("=" * 60)

    duration = timeline["project"]["duration"]
    print(f"Project Duration: {duration:.2f}s\n")

    for track in timeline.get("tracks", []):
        print(f"🎚️ Track: {track['id']}")
        print(f"   Role: {track.get('role')} | Gain: {track.get('gain', 0)} dB")

        clips = [
            c for c in track.get("clips", [])
            if "start" in c
        ]

        clips = sorted(clips, key = lambda c: c["start"])

        if not clips:
            print("   (no clips)\n")
            continue

        for clip in clips:
            start = clip["start"]

            if clip.get("loop"):
                end = clip.get("loop_until", start)
                end_label = f"{end:.2f}s (loop)"
            else:
                audio = AudioSegment.from_file(clip["file"])
                end = start + (len(audio) / 1000.0)
                end_label = f"{end:.2f}s"

            print(f"   ├─ {os.path.basename(clip['file'])}")
            print(f"   │   {start:.2f}s → {end_label}")

            if "fade_in" in clip:
                print(f"   │   Fade In: {clip['fade_in']}s")
            if "fade_out" in clip:
                print(f"   │   Fade Out: {clip['fade_out']}s")

            # Show scene overrides (only if present)
            if "_rules" in clip:
                rules = clip["_rules"]
                duck = rules.get("ducking", {})
                comp = rules.get("dialogue_compression", {})

                if duck:
                    print(f"   │   Ducking: {duck.get('duck_amount')} dB")
                if comp:
                    print(f"   │   Compression Threshold: {comp.get('threshold')} dB")

        print()

    print("=" * 60 + "\n")
