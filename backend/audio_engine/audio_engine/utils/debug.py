import os

def _fmt_time(seconds: float) -> str:
    return f"{seconds:.2f}s"


def _clip_end(clip: dict) -> float:
    if "loop_until" in clip:
        return clip["loop_until"]
    if "start" in clip and "duration" in clip:
        return clip["start"] + clip["duration"]
    return None


def debug_print_timeline(timeline: dict) -> None:
    print("\n" + "=" * 60)
    print("📊 TIMELINE DEBUG VIEW")
    print("=" * 60)

    project = timeline.get("project", {})
    duration = project.get("duration", "unknown")

    print(f"Project Duration: {_fmt_time(duration)}\n")

    tracks = timeline.get("tracks", [])
    if not tracks:
        print("⚠ No tracks found.")
        return

    for track in tracks:
        track_id = track.get("id", "<unnamed>")
        role = track.get("role", "none")
        gain = track.get("gain", 0)

        print(f"🎚️ Track: {track_id}")
        print(f"   Role: {role} | Gain: {gain} dB")

        clips = track.get("clips", [])
        if not clips:
            print("   (no clips)")
            print()
            continue

        safe_clips = [c for c in clips if "start" in c]
        safe_clips.sort(key=lambda c: c["start"])

        for clip in safe_clips:
            file = os.path.basename(clip.get("file", "<unknown>"))
            start = clip.get("start")
            end = clip.get("loop_until", None)

            print(f"   ├─ {file}")
            if end:
                print(f"   │   {_fmt_time(start)} → {_fmt_time(end)} (loop)")
            else:
                print(f"   │   Start: {_fmt_time(start)}")

            if "fade_in" in clip:
                print(f"   │   Fade In: {clip['fade_in']}s")
            if "fade_out" in clip:
                print(f"   │   Fade Out: {clip['fade_out']}s")

            rules = clip.get("_rules", {})
            duck = rules.get("ducking")
            comp = rules.get("dialogue_compression")

            if duck:
                print(f"   │   Ducking: {duck.get('duck_amount', '?')} dB")
            if comp:
                print(f"   │   Compression Threshold: {comp.get('threshold', '?')} dB")

        print()

    print("=" * 60)
