"""Tests for dsl.validator."""

from dsl.validator import (
    _clamp_float,
    _clamp_int,
    _fix_order_continuity,
    _is_empty_rules,
    validate_draft_timeline,
)


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------

def _minimal_timeline(**overrides):
    """Build a minimal valid Draft Timeline dict."""
    base = {
        "project": {"name": "test", "sample_rate": 48000, "bit_depth": 16},
        "settings": {
            "default_silence": 0.5,
            "normalize": True,
            "master_gain": 0,
            "ducking": {
                "enabled": True,
                "mode": "audacity",
                "duck_amount": -6,
                "fade_down_ms": 500,
                "fade_up_ms": 500,
                "min_pause_ms": 300,
                "onset_delay_ms": 120,
                "rules": [],
            },
            "dialogue_compression": {
                "enabled": True,
                "threshold": -22,
                "ratio": 2.5,
                "attack_ms": 20,
                "release_ms": 180,
                "makeup_gain": 1,
            },
            "scene_crossfade": {"enabled": False, "duration": 1.5},
            "loudness": {"enabled": True, "target_lufs": -20.0},
        },
        "tracks": [
            {"id": "narrator", "type": "voice", "role": "voice", "gain": 0},
            {"id": "music", "type": "music", "role": "background", "gain": -9},
        ],
        "scenes": [
            {
                "id": "scene_001",
                "name": "Scene 1",
                "energy": 0.5,
                "tracks": {
                    "narrator": [
                        {"tts_text": "Hello world.", "order": 0},
                    ],
                },
            },
        ],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Clamp helpers
# ---------------------------------------------------------------------------

class TestDSLClampInt:
    def test_normal(self):
        assert _clamp_int(0, -30, 6) == 0

    def test_below(self):
        assert _clamp_int(-50, -30, 6) == -30

    def test_above(self):
        assert _clamp_int(20, -30, 6) == 6

    def test_non_numeric(self):
        assert _clamp_int("bad", -30, 6) == -12  # midpoint


class TestDSLClampFloat:
    def test_normal(self):
        assert _clamp_float(0.5, 0.0, 1.0) == 0.5

    def test_below(self):
        assert _clamp_float(-0.5, 0.0, 1.0) == 0.0


# ---------------------------------------------------------------------------
# _is_empty_rules
# ---------------------------------------------------------------------------

class TestIsEmptyRules:
    def test_all_none(self):
        assert _is_empty_rules({"eq": None, "ducking": None}) is True

    def test_eq_with_none_values(self):
        assert _is_empty_rules({"eq": {"tilt": None}, "ducking": None}) is True

    def test_eq_with_value(self):
        assert _is_empty_rules({"eq": {"tilt": "warm"}, "ducking": None}) is False


# ---------------------------------------------------------------------------
# _fix_order_continuity
# ---------------------------------------------------------------------------

class TestFixOrderContinuity:
    def test_gaps_renumbered(self):
        scene_tracks = {
            "narrator": [
                {"tts_text": "A", "order": 0},
                {"tts_text": "B", "order": 5},
                {"tts_text": "C", "order": 10},
            ],
        }
        track_type_map = {"narrator": "voice"}
        _fix_order_continuity(scene_tracks, track_type_map)
        orders = [c["order"] for c in scene_tracks["narrator"]]
        assert orders == [0, 1, 2]

    def test_out_of_order_sorted(self):
        scene_tracks = {
            "narrator": [
                {"tts_text": "A", "order": 3},
                {"tts_text": "B", "order": 1},
            ],
        }
        track_type_map = {"narrator": "voice"}
        _fix_order_continuity(scene_tracks, track_type_map)
        # After fixing, orders should be 0 and 1 based on original order sort
        orders = [c["order"] for c in scene_tracks["narrator"]]
        assert sorted(orders) == [0, 1]

    def test_non_voice_tracks_ignored(self):
        scene_tracks = {
            "music": [{"mood": "neutral", "order": 99}],
        }
        track_type_map = {"music": "music"}
        _fix_order_continuity(scene_tracks, track_type_map)
        assert scene_tracks["music"][0]["order"] == 99

    def test_empty_tracks(self):
        _fix_order_continuity({}, {})  # should not raise


# ---------------------------------------------------------------------------
# validate_draft_timeline (full)
# ---------------------------------------------------------------------------

class TestValidateDraftTimeline:
    def test_valid_timeline_passes(self):
        raw = _minimal_timeline()
        result = validate_draft_timeline(raw)
        assert "tracks" in result
        assert "scenes" in result

    def test_unknown_track_removed_from_scene(self):
        raw = _minimal_timeline()
        raw["scenes"][0]["tracks"]["nonexistent_track"] = [{"tts_text": "X"}]
        result = validate_draft_timeline(raw)
        scene_track_ids = set(result["scenes"][0]["tracks"].keys())
        assert "nonexistent_track" not in scene_track_ids

    def test_gain_clamped(self):
        raw = _minimal_timeline()
        raw["tracks"][0]["gain"] = 100  # way above max (6)
        result = validate_draft_timeline(raw)
        assert result["tracks"][0]["gain"] <= 6

    def test_invalid_eq_preset_removed(self):
        raw = _minimal_timeline()
        raw["tracks"][0]["eq_preset"] = "INVALID_PRESET"
        result = validate_draft_timeline(raw)
        narrator_track = next(t for t in result["tracks"] if t["id"] == "narrator")
        assert narrator_track.get("eq_preset") is None

    def test_energy_clamped(self):
        raw = _minimal_timeline()
        raw["scenes"][0]["energy"] = 5.0  # above 1.0
        result = validate_draft_timeline(raw)
        assert result["scenes"][0]["energy"] <= 1.0

    def test_scene_order_continuity_fixed(self):
        raw = _minimal_timeline()
        raw["scenes"][0]["tracks"]["narrator"] = [
            {"tts_text": "A", "order": 0},
            {"tts_text": "B", "order": 7},
        ]
        result = validate_draft_timeline(raw)
        orders = [c["order"] for c in result["scenes"][0]["tracks"]["narrator"]]
        assert orders == [0, 1]
