from typing import Dict
from pydub import AudioSegment


def auto_fix_overlaps(track: Dict, min_gap: float = 0.0) -> None:
    """
    Shifts overlapping clips forward on the same track.
    min_gap: optional silence (seconds) to keep between clips.
    """

    clips = track.get("clips",[])
    if not clips:
        return

    clips = [c for c in clips if "start" in c]

    if len(clips) < 2:
        return
    
    #sort by time
    clips.sort(key=lambda c:c["start"])

    prev_end = None

    for clip in clips:
        start = clip["start"]

        #Determine clip end
        if clip.get("loop"):
            end = clip.get("loop_until", start)
        
        else:
            audio = AudioSegment.from_file(clip["file"])
            end = start + (len(audio) / 1000.0)

        # If overlap, shift this clip forward

        if prev_end is not None and start < prev_end + min_gap:
            shift_to = prev_end + min_gap
            delta = shift_to - start
            clip["start"] = shift_to

            #If looped, preserve length
            if clip.get("loop") and "loop_until" in clip:
                clip["loop_until"] += delta

        
        prev_end = max(prev_end or 0, clip["start"] + (end - start))