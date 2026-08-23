# DSP Module exports
from .eq import (
    apply_eq_preset,
    apply_scene_tonal_shaping,
    apply_high_pass,
    apply_low_pass,
    apply_primary_band,
    apply_shelf,
    get_preset_for_role,
)
from .eq_presets import (
    EQ_PRESETS,
    PRESET_ALIASES,
    ROLE_DEFAULT_PRESETS,
    resolve_preset_version,
    get_preset_config,
)
