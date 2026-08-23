from copy import deepcopy
from typing import Dict, List, Optional

from audio_engine.utils.dialogue_density import compute_dialogue_density, classify_dialogue_density
from audio_engine.utils.logger import get_logger

logger = get_logger(__name__)

def merge_rules(global_rules: Dict, scene_rules: Dict) -> Dict:
    """
    Scene rules override global rules(shallow merge).
    """
    global_rules = global_rules or {}
    scene_rules = scene_rules or {}

    merged={}

    for key, value in global_rules.items():
        merged[key]=value.copy() if isinstance(value, dict) else value
    
    for key, value in scene_rules.items():
        if key in merged and isinstance(merged[key],dict):
            merged[key].update(value)
        else:
            merged[key]=value

    return merged


def apply_scene_crossfades(track_clips: List[Dict], default_duration: float) -> None:
    
    """
    Adds fade_out to clip[i] and fade_in to clip[i+1]
    when they touch (or nearly touch) in time.
    """

    # sort by start time
    track_clips = [c for c in track_clips if "start" in c]
    
    if len(track_clips) < 2:
        return

    track_clips.sort(key=lambda c: c["start"])

    for i in range(len(track_clips)-1):
        a = track_clips[i]
        b = track_clips[i+1]

        # only crossfade scene-generated clips
        if "_rules" not in a or "_rules" not in b:
            continue
        
        end_a = a.get("loop_until", a["start"])
        start_b =  b["start"]

        #if they touch(or are very close), crossfade

        if abs(end_a - start_b)< 0.05:
            # scene override > global default
            scene_rules = b.get("_rules", {})
            cf = scene_rules.get("scene_crossfade",{})
            duration = cf.get("duration", default_duration)

            # inject fades
            a["fade_out"] = max(a.get("fade_out",0),duration)
            b["fade_in"] = max(b.get("fade_in",0), duration)

            b["start"] -= duration

            if b["start"] < 0:
                b["start"] = 0

def preprocess_scenes(timeline: Dict) -> Dict:
    """
    Convert scene blocks into normal track clips.
    Mutates and returns timeline.
    """

    scenes = timeline.get("scenes",[])
    if not scenes:
        return timeline 
    
    global_settings = timeline.get("settings",{})

    # building a map

    track_map = {}
    for track in timeline.get("tracks",[]):
        track.setdefault("clips",[])
        track_map[track["id"]] = track

        # 🔊 Collect all dialogue ranges (once)
    dialogue_ranges = []

    for track in timeline.get("tracks", []):
        if track.get("role") != "voice":
            continue

        for clip in track.get("clips", []):
            if "start" not in clip:
                continue

            start = clip["start"]
            end = clip.get("loop_until", start)

            dialogue_ranges.append((start, end))


    prev_scene_energy = None

    for scene in scenes:
        scene_start = scene["start"]
        scene_end = scene_start + scene["duration"]

        # 🧠 Dialogue Density (scene-level)
        density_ratio = compute_dialogue_density(
            dialogue_ranges,
            scene_start,
            scene_end
        )

        density_label = classify_dialogue_density(density_ratio)


        scene_tracks = scene.get("tracks",{})
        scene_rules =  scene.get("rules",{})
        current_energy = scene.get("energy", 0.5)

        # merge global + scene rules

        effective_rules = merge_rules(global_settings, scene_rules)

        for track_id, clips in scene_tracks.items():
            if track_id not in track_map:
                raise ValueError(
                    f"Scene references unknown track '{track_id}"
                )

            # Get track-level semantic_role (if present)
            track = track_map[track_id]
            track_semantic_role = track.get("semantic_role")

            for clip in clips:
                new_clip = deepcopy(clip)

                new_clip["start"] = scene_start + clip.get("offset",0)

                # Preserve semantic_role: clip-level overrides track-level
                # If clip doesn't have semantic_role, inherit from track
                if "semantic_role" not in new_clip and track_semantic_role is not None:
                    new_clip["semantic_role"] = track_semantic_role

                #Auto-loop till scene end

                if new_clip.get("loop"):
                    new_clip["loop_until"] = scene_end

                # attach merged rules to clip
                new_clip["_rules"] = effective_rules.copy()
                
                #Dialogue density
                new_clip["_rules"]["dialogue_density"] = density_ratio
                new_clip["_rules"]["dialogue_density_label"] = density_label

                # scene energy (current + previous)
                new_clip["_rules"]["scene_energy"] = current_energy
                new_clip["_rules"]["prev_scene_energy"] = prev_scene_energy

                # energy ramp duration (ms)
                new_clip["_rules"]["energy_ramp_duration"] = (
                    timeline.get("settings", {})
                            .get("energy_ramp", {})
                            .get("duration", 3.0) * 1000
                )
                
                track_map[track_id]["clips"].append(new_clip)
                logger.debug(f"Added clip to track '{track_id}': {new_clip.get('file', 'unknown')}")

        prev_scene_energy = current_energy

    # Scene Crossfades (Per track)

    settings = timeline.get("settings",{})
    sc_cfg = settings.get("scene_crossfade",{})

    if sc_cfg.get("enabled", False):
        default_duration = sc_cfg.get("duration",1.5)

        for track in timeline.get("tracks",[]):
            clips = track.get("clips",[])
            apply_scene_crossfades(clips, default_duration)

    return timeline