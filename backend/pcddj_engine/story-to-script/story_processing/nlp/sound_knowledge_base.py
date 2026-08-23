"""Action-to-Sound Knowledge Base — spaCy-driven audio cue extraction.

Maps verb lemmas to SFX labels and noun/entity tokens to ambience
layers.  Provides a **deterministic fallback** that works without any
LLM, producing scene-aware audio cues from the spaCy dependency parse.

Public API:
    ``extract_sound_cues_from_nlp(doc_span, sentences) -> (sfx_events, ambience_labels)``
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from spacy.tokens import Span

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Action → SFX mapping
# ---------------------------------------------------------------------------
# Each key is a verb lemma.  Values are tuples of
# ``(sfx_label, semantic_role, timing)`` so the output matches the
# structured schema used by the LLM path.

_SFXEntry = tuple[str, str, str]  # (sfx_label, semantic_role, timing)

ACTION_SOUND_MAP: dict[str, list[_SFXEntry]] = {
    # -- Physical movement ---------------------------------------------------
    "run": [("footsteps_fast", "movement", "sustained"), ("breathing_heavy", "texture", "sustained")],
    "sprint": [("footsteps_sprint", "movement", "sustained"), ("breathing_heavy", "texture", "sustained")],
    "dash": [("footsteps_fast", "movement", "short")],
    "race": [("footsteps_fast", "movement", "sustained")],
    "rush": [("footsteps_fast", "movement", "short")],
    "bolt": [("footsteps_sprint", "movement", "short")],
    "charge": [("footsteps_fast", "movement", "short"), ("body_movement_heavy", "impact", "instant")],
    "flee": [("footsteps_fast", "movement", "sustained"), ("breathing_panicked", "texture", "sustained")],
    "chase": [("footsteps_fast", "movement", "sustained")],
    "walk": [("footsteps_slow", "movement", "sustained")],
    "stroll": [("footsteps_slow", "movement", "sustained")],
    "wander": [("footsteps_slow", "movement", "sustained")],
    "pace": [("footsteps_slow", "movement", "sustained")],
    "tiptoe": [("footsteps_quiet", "movement", "sustained")],
    "sneak": [("footsteps_quiet", "movement", "sustained")],
    "crawl": [("crawling", "movement", "sustained")],
    "stumble": [("stumble", "movement", "instant")],
    "trip": [("stumble", "movement", "instant")],
    "fall": [("body_fall", "impact", "instant")],
    "collapse": [("body_fall", "impact", "instant")],
    "tumble": [("body_fall", "impact", "instant")],
    "climb": [("climbing", "movement", "sustained")],
    "leap": [("jump_land", "movement", "instant")],
    "jump": [("jump_land", "movement", "instant")],
    "dive": [("body_movement_heavy", "movement", "instant")],
    "dodge": [("body_movement_quick", "movement", "instant")],
    "lunge": [("body_movement_heavy", "impact", "instant")],
    "tackle": [("body_impact", "impact", "instant")],
    "swim": [("water_swimming", "movement", "sustained")],
    "slide": [("sliding", "movement", "short")],

    # -- Combat / force ------------------------------------------------------
    "hit": [("punch_impact", "impact", "instant")],
    "punch": [("punch_impact", "impact", "instant")],
    "kick": [("kick_impact", "impact", "instant")],
    "strike": [("strike_impact", "impact", "instant")],
    "slam": [("slam_heavy", "impact", "instant")],
    "smash": [("smash_impact", "impact", "instant"), ("glass_shatter", "impact", "instant")],
    "crash": [("crash_impact", "impact", "instant")],
    "shatter": [("glass_shatter", "impact", "instant")],
    "break": [("breaking", "impact", "instant")],
    "tear": [("ripping", "impact", "instant")],
    "rip": [("ripping", "impact", "instant")],
    "fight": [("fight_scuffle", "impact", "sustained")],
    "attack": [("attack_impact", "impact", "instant")],
    "shoot": [("gunshot", "impact", "instant")],
    "fire": [("gunshot", "impact", "instant")],
    "stab": [("stab", "impact", "instant")],
    "swing": [("whoosh", "movement", "instant")],
    "whip": [("whip_crack", "impact", "instant")],
    "throw": [("whoosh", "movement", "instant")],
    "grab": [("grab_rustle", "interaction", "instant")],
    "pull": [("pulling", "interaction", "short")],
    "push": [("pushing", "interaction", "instant")],
    "shove": [("pushing", "impact", "instant")],
    "drag": [("dragging", "movement", "sustained")],

    # -- Explosive / dramatic ------------------------------------------------
    "explode": [("explosion", "impact", "instant")],
    "burst": [("explosion_small", "impact", "instant")],
    "blast": [("explosion", "impact", "instant")],
    "erupt": [("eruption", "impact", "instant")],
    "detonate": [("explosion", "impact", "instant")],
    "ignite": [("fire_ignite", "impact", "instant")],

    # -- Rapid / urgent ------------------------------------------------------
    "hurry": [("footsteps_fast", "movement", "short")],
    "scramble": [("scrambling", "movement", "short")],
    "snatch": [("grab_rustle", "interaction", "instant")],
    "seize": [("grab_rustle", "interaction", "instant")],
    "wrench": [("metal_wrench", "interaction", "instant")],
    "yank": [("yank", "interaction", "instant")],
    "hurl": [("whoosh", "movement", "instant")],
    "plunge": [("water_splash", "impact", "instant")],
    "surge": [("rushing", "movement", "short")],
    "storm": [("footsteps_fast", "movement", "short")],

    # -- Sound-producing actions ---------------------------------------------
    "breathe": [("breathing", "texture", "sustained")],
    "pant": [("breathing_heavy", "texture", "sustained")],
    "gasp": [("gasp", "impact", "instant")],
    "sigh": [("sigh", "texture", "instant")],
    "cough": [("cough", "impact", "instant")],
    "sneeze": [("sneeze", "impact", "instant")],
    "whisper": [("whispering", "texture", "short")],
    "shout": [("shout", "impact", "instant")],
    "scream": [("scream", "impact", "instant")],
    "yell": [("yell", "impact", "instant")],
    "cry": [("crying", "texture", "sustained")],
    "sob": [("sobbing", "texture", "sustained")],
    "laugh": [("laughter", "texture", "short")],
    "chuckle": [("chuckle", "texture", "instant")],
    "giggle": [("giggle", "texture", "instant")],
    "groan": [("groan", "texture", "instant")],
    "moan": [("moan", "texture", "short")],
    "grunt": [("grunt", "impact", "instant")],
    "hum": [("humming", "texture", "sustained")],
    "sing": [("singing", "texture", "sustained")],
    "whistle": [("whistling", "texture", "short")],
    "clap": [("clap", "impact", "instant")],
    "snap": [("snap", "impact", "instant")],
    "knock": [("knocking", "interaction", "short")],

    # -- Door / object interactions ------------------------------------------
    "open": [("door_open", "interaction", "instant")],
    "close": [("door_close", "interaction", "instant")],
    "shut": [("door_close", "interaction", "instant")],
    "lock": [("lock_click", "interaction", "instant")],
    "unlock": [("lock_click", "interaction", "instant")],
    "creak": [("creaking", "texture", "short")],

    # -- Vehicle / transport -------------------------------------------------
    "drive": [("car_engine", "ambience", "sustained")],
    "ride": [("vehicle_motion", "ambience", "sustained")],
    "fly": [("wind_rushing", "movement", "sustained")],

    # -- Water / nature ------------------------------------------------------
    "rain": [("rain_drops", "ambience", "sustained")],
    "pour": [("water_pouring", "interaction", "short")],
    "drip": [("water_drip", "texture", "sustained")],
    "splash": [("water_splash", "impact", "instant")],
    "drown": [("water_bubbles", "texture", "sustained")],

    # -- Cooking / domestic --------------------------------------------------
    "cook": [("sizzle", "texture", "sustained")],
    "fry": [("sizzle", "texture", "sustained")],
    "boil": [("bubbling", "texture", "sustained")],
    "chop": [("chopping", "interaction", "short")],
    "slice": [("knife_slice", "interaction", "instant")],
    "stir": [("stirring", "interaction", "sustained")],
    "eat": [("eating", "texture", "short")],
    "drink": [("drinking", "texture", "short")],
    "sip": [("sipping", "texture", "instant")],
    "swallow": [("swallowing", "texture", "instant")],

    # -- Writing / object manipulation ---------------------------------------
    "write": [("pen_writing", "texture", "sustained")],
    "type": [("typing", "texture", "sustained")],
    "tap": [("tapping", "interaction", "short")],
    "click": [("click", "interaction", "instant")],
    "ring": [("ringing", "impact", "short")],
    "buzz": [("buzzing", "texture", "sustained")],
    "tick": [("clock_ticking", "texture", "sustained")],
}


# ---------------------------------------------------------------------------
# Location / noun → Ambience mapping
# ---------------------------------------------------------------------------
# Each key is a noun lemma or location name.  Values are lists of
# ambience layer labels (first entry is the primary atmosphere tag).

LOCATION_AMBIENCE_MAP: dict[str, list[str]] = {
    # -- Nature / outdoor ----------------------------------------------------
    "park": ["birds_chirping", "wind_leaves", "distant_activity"],
    "garden": ["birds_chirping", "wind_leaves", "insects_soft"],
    "forest": ["birds_forest", "wind_trees", "insects", "creek_distant"],
    "wood": ["birds_forest", "wind_trees", "leaves_rustling"],
    "woods": ["birds_forest", "wind_trees", "leaves_rustling"],
    "jungle": ["jungle_birds", "insects_tropical", "rain_canopy"],
    "meadow": ["wind_grass", "birds_chirping", "insects_soft"],
    "field": ["wind_open", "birds_distant", "grass_rustling"],
    "mountain": ["wind_mountain", "birds_distant", "echo_natural"],
    "hill": ["wind_open", "birds_distant"],
    "valley": ["wind_gentle", "river_distant", "birds_chirping"],
    "cliff": ["wind_strong", "waves_crashing"],
    "cave": ["cave_drip", "echo_cave", "wind_hollow"],
    "desert": ["wind_desert", "sand_shifting", "heat_hum"],
    "swamp": ["insects_buzzing", "water_bubbling", "frogs"],
    "marsh": ["insects_buzzing", "water_bubbling", "birds_marsh"],

    # -- Water ---------------------------------------------------------------
    "ocean": ["ocean_waves", "seagulls", "wind_coastal"],
    "sea": ["ocean_waves", "seagulls", "wind_coastal"],
    "beach": ["ocean_waves", "seagulls", "sand_footsteps"],
    "lake": ["water_lapping", "birds_water", "wind_gentle"],
    "river": ["river_flowing", "birds_water", "insects_soft"],
    "stream": ["stream_babbling", "birds_chirping"],
    "pond": ["water_still", "frogs", "insects_soft"],
    "waterfall": ["waterfall_roar", "mist_spray", "birds_distant"],
    "pool": ["water_still", "echo_indoor"],
    "harbor": ["water_lapping", "boats_creaking", "seagulls"],
    "dock": ["water_lapping", "boats_creaking", "chains_rattling"],

    # -- Urban / city --------------------------------------------------------
    "city": ["traffic_distant", "pedestrians", "urban_hum"],
    "town": ["traffic_light", "distant_voices", "birds_urban"],
    "village": ["distant_voices", "birds_chirping", "wind_gentle"],
    "street": ["traffic_close", "footsteps_crowd", "urban_hum"],
    "road": ["traffic_passing", "wind_road"],
    "highway": ["highway_traffic", "wind_rushing"],
    "alley": ["distant_traffic", "echo_narrow", "dripping"],
    "market": ["crowd_busy", "vendors_calling", "market_clatter"],
    "plaza": ["crowd_outdoor", "fountain", "birds_urban"],
    "square": ["crowd_outdoor", "fountain", "birds_urban"],

    # -- Indoor / residential ------------------------------------------------
    "room": ["room_tone_quiet"],
    "house": ["house_ambience", "clock_ticking"],
    "home": ["house_ambience", "clock_ticking"],
    "apartment": ["apartment_ambience", "muffled_traffic"],
    "bedroom": ["room_tone_quiet", "clock_ticking"],
    "bathroom": ["bathroom_echo", "water_drip"],
    "kitchen": ["kitchen_ambience", "fridge_hum", "clock_ticking"],
    "basement": ["basement_hum", "pipes_drip", "echo_low"],
    "attic": ["wind_attic", "creaking_wood"],
    "hallway": ["footsteps_echo", "room_tone_quiet"],
    "corridor": ["footsteps_echo", "room_tone_quiet"],
    "cellar": ["dripping", "echo_stone", "basement_hum"],
    "cabin": ["wood_creaking", "wind_outside", "fire_crackling"],
    "tent": ["canvas_flapping", "wind_outside"],

    # -- Commercial / public -------------------------------------------------
    "office": ["office_ambience", "typing_distant", "air_conditioning"],
    "hospital": ["hospital_ambience", "beeping", "intercom_distant"],
    "school": ["school_ambience", "children_distant", "bell_distant"],
    "church": ["church_ambience", "echo_reverb"],
    "library": ["library_quiet", "page_turning", "whispers_distant"],
    "restaurant": ["restaurant_ambience", "cutlery_clinking", "murmur"],
    "cafe": ["cafe_ambience", "coffee_machine", "murmur_soft"],
    "bar": ["bar_ambience", "glasses_clinking", "murmur"],
    "pub": ["bar_ambience", "glasses_clinking", "murmur"],
    "club": ["club_music", "crowd_loud"],
    "store": ["store_ambience", "muzak_distant"],
    "shop": ["store_ambience", "door_bell"],
    "station": ["station_announcement", "crowd_moving", "train_distant"],
    "airport": ["airport_ambience", "announcements", "crowd_moving"],
    "factory": ["factory_machinery", "metal_clanking", "ventilation"],
    "warehouse": ["echo_large", "ventilation", "distant_machinery"],
    "prison": ["metal_doors", "echo_concrete", "distant_voices"],
    "jail": ["metal_doors", "echo_concrete"],

    # -- Transport -----------------------------------------------------------
    "car": ["car_interior", "engine_hum", "road_noise"],
    "bus": ["bus_engine", "crowd_quiet", "road_noise"],
    "train": ["train_rhythm", "metal_wheels", "train_horn_distant"],
    "plane": ["airplane_cabin", "engine_drone"],
    "airplane": ["airplane_cabin", "engine_drone"],
    "ship": ["ship_engine", "waves_hull", "creaking_metal"],
    "boat": ["boat_rocking", "water_lapping", "wind_gentle"],
    "subway": ["subway_rumble", "brakes_screech", "crowd_underground"],

    # -- Weather / time of day -----------------------------------------------
    "rain": ["rain_steady", "thunder_distant"],
    "storm": ["storm_wind", "thunder", "rain_heavy"],
    "thunder": ["thunder_rumble"],
    "snow": ["wind_cold", "silence_winter"],
    "wind": ["wind_blowing"],
    "fog": ["fog_muted", "wind_gentle"],
    "night": ["night_crickets", "wind_gentle", "owl_distant"],
    "morning": ["birds_morning", "wind_gentle"],
    "dawn": ["birds_dawn", "wind_gentle"],
    "dusk": ["crickets_early", "birds_evening"],
    "evening": ["crickets_early", "distant_activity"],

    # -- Misc environments ---------------------------------------------------
    "graveyard": ["wind_eerie", "crows", "gate_creaking"],
    "cemetery": ["wind_eerie", "crows", "gate_creaking"],
    "castle": ["wind_castle", "echo_stone", "torch_crackling"],
    "dungeon": ["dripping", "echo_stone", "chains_rattling"],
    "tower": ["wind_high", "echo_stone"],
    "bridge": ["wind_bridge", "traffic_distant", "water_below"],
    "tunnel": ["echo_tunnel", "wind_tunnel", "dripping"],
    "rooftop": ["wind_high", "city_below"],
    "balcony": ["wind_gentle", "city_below"],
    "playground": ["children_playing", "swings_creaking", "birds_chirping"],
    "stadium": ["crowd_stadium", "echo_large"],
    "arena": ["crowd_arena", "echo_large"],
    "battlefield": ["distant_explosions", "wind_desolate"],
    "ruins": ["wind_ruins", "crumbling_stone", "birds_distant"],
    "temple": ["echo_stone", "wind_gentle", "chimes"],
}


# ---------------------------------------------------------------------------
# Semantic role inference from SFX timing
# ---------------------------------------------------------------------------

_TIMING_TO_ROLE_DEFAULT: dict[str, str] = {
    "instant": "impact",
    "short": "interaction",
    "sustained": "texture",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_sound_cues_from_nlp(
    doc_span: Span | None,
    sentences: list[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Extract SFX events and ambience labels from a spaCy Span.

    Uses verb lemmas → :data:`ACTION_SOUND_MAP` for SFX and
    noun lemmas / NER-LOC entities → :data:`LOCATION_AMBIENCE_MAP`
    for ambience.

    Parameters
    ----------
    doc_span:
        A spaCy ``Span`` covering the scene text.  If ``None``,
        falls back to a simple whitespace token scan of *sentences*.
    sentences:
        The scene's sentence list (used for ``source_text`` and
        ``order_hint`` on each SFX event).

    Returns
    -------
    tuple of (sfx_events, ambience_labels):
        ``sfx_events`` is a list of dicts matching the
        ``SFXEvent`` schema (``source_text``, ``sfx_label``,
        ``sfx_description``, ``intensity``, ``semantic_role``,
        ``timing``, ``order_hint``).
        ``ambience_labels`` is a deduplicated list of atmosphere
        tag strings (first entry = primary).
    """
    sfx_events: list[dict[str, Any]] = []
    ambience_labels: list[str] = []
    seen_sfx: set[str] = set()
    seen_ambience: set[str] = set()

    if doc_span is not None:
        _extract_from_span(doc_span, sentences, sfx_events, ambience_labels, seen_sfx, seen_ambience)
    else:
        _extract_from_raw_sentences(sentences, sfx_events, ambience_labels, seen_sfx, seen_ambience)

    return sfx_events, ambience_labels


# ---------------------------------------------------------------------------
# Internal extractors
# ---------------------------------------------------------------------------

def _sent_index_for_token(token_idx: int, sent_spans: list[tuple[int, int]]) -> int:
    """Return the sentence index containing *token_idx*."""
    for i, (start, end) in enumerate(sent_spans):
        if start <= token_idx < end:
            return i
    return 0


def _extract_from_span(
    span: Span,
    sentences: list[str],
    sfx_out: list[dict[str, Any]],
    amb_out: list[str],
    seen_sfx: set[str],
    seen_amb: set[str],
) -> None:
    """Walk spaCy tokens for verb→SFX and noun/entity→ambience matches."""
    sent_spans = [(s.start, s.end) for s in span.sents]

    for token in span:
        lemma = token.lemma_.lower()

        # Verb → SFX
        if token.pos_ == "VERB" and lemma in ACTION_SOUND_MAP:
            sent_idx = _sent_index_for_token(token.i, sent_spans)
            source = sentences[sent_idx] if sent_idx < len(sentences) else token.sent.text
            for sfx_label, role, timing in ACTION_SOUND_MAP[lemma]:
                if sfx_label in seen_sfx:
                    continue
                seen_sfx.add(sfx_label)
                sfx_out.append({
                    "source_text": source.strip(),
                    "sfx_label": sfx_label,
                    "sfx_description": f"{sfx_label.replace('_', ' ')} sound",
                    "intensity": "moderate",
                    "semantic_role": role,
                    "timing": timing,
                    "order_hint": sent_idx,
                })

        # Noun / PROPN → ambience
        if token.pos_ in ("NOUN", "PROPN") and lemma in LOCATION_AMBIENCE_MAP:
            for label in LOCATION_AMBIENCE_MAP[lemma]:
                if label not in seen_amb:
                    seen_amb.add(label)
                    amb_out.append(label)

    # NER entities (GPE, LOC, FAC) → ambience
    for ent in span.ents:
        if ent.label_ in ("GPE", "LOC", "FAC"):
            ent_lower = ent.text.lower()
            if ent_lower in LOCATION_AMBIENCE_MAP:
                for label in LOCATION_AMBIENCE_MAP[ent_lower]:
                    if label not in seen_amb:
                        seen_amb.add(label)
                        amb_out.append(label)


def _crude_lemma(word: str) -> str:
    """Best-effort lemmatization without spaCy — strip common English suffixes."""
    if word.endswith("ing") and len(word) > 5:
        # running -> run, breathing -> breath, cooking -> cook
        base = word[:-3]
        if base in ACTION_SOUND_MAP or base in LOCATION_AMBIENCE_MAP:
            return base
        # doubled consonant: slamming -> slam, running -> run
        if len(base) > 2 and base[-1] == base[-2]:
            shorter = base[:-1]
            if shorter in ACTION_SOUND_MAP or shorter in LOCATION_AMBIENCE_MAP:
                return shorter
        # trailing 'e' dropped: sliding -> slid+e, cooking -> cook
        with_e = base + "e"
        if with_e in ACTION_SOUND_MAP or with_e in LOCATION_AMBIENCE_MAP:
            return with_e
    if word.endswith("ed") and len(word) > 4:
        base = word[:-2]
        if base in ACTION_SOUND_MAP or base in LOCATION_AMBIENCE_MAP:
            return base
        # doubled consonant: slammed -> slam
        if len(base) > 2 and base[-1] == base[-2]:
            shorter = base[:-1]
            if shorter in ACTION_SOUND_MAP or shorter in LOCATION_AMBIENCE_MAP:
                return shorter
        # trailing 'e' dropped: walked -> walk? (walk+ed = walked, base=walk)
        with_e = base + "e"
        if with_e in ACTION_SOUND_MAP or with_e in LOCATION_AMBIENCE_MAP:
            return with_e
        # base+d: sliced -> slice
        base_d = word[:-1]
        if base_d in ACTION_SOUND_MAP or base_d in LOCATION_AMBIENCE_MAP:
            return base_d
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        base = word[:-1]
        if base in ACTION_SOUND_MAP or base in LOCATION_AMBIENCE_MAP:
            return base
    return word


def _extract_from_raw_sentences(
    sentences: list[str],
    sfx_out: list[dict[str, Any]],
    amb_out: list[str],
    seen_sfx: set[str],
    seen_amb: set[str],
) -> None:
    """Fallback: simple whitespace tokenization when no spaCy Span is available."""
    for sent_idx, sent in enumerate(sentences):
        words = sent.lower().split()
        for word in words:
            cleaned = word.strip(".,!?;:\"'()-")
            lemma = _crude_lemma(cleaned)

            if lemma in ACTION_SOUND_MAP:
                for sfx_label, role, timing in ACTION_SOUND_MAP[lemma]:
                    if sfx_label in seen_sfx:
                        continue
                    seen_sfx.add(sfx_label)
                    sfx_out.append({
                        "source_text": sent.strip(),
                        "sfx_label": sfx_label,
                        "sfx_description": f"{sfx_label.replace('_', ' ')} sound",
                        "intensity": "moderate",
                        "semantic_role": role,
                        "timing": timing,
                        "order_hint": sent_idx,
                    })

            if lemma in LOCATION_AMBIENCE_MAP:
                for label in LOCATION_AMBIENCE_MAP[lemma]:
                    if label not in seen_amb:
                        seen_amb.add(label)
                        amb_out.append(label)
