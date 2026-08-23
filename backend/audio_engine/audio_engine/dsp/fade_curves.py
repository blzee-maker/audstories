"""
Fade curve types and generation functions for advanced fade curves.
"""
from enum import Enum
from typing import Union
import numpy as np
import math


class FadeCurve(Enum):
    """Enumeration of available fade curve types."""
    LINEAR = "linear"
    LOGARITHMIC = "logarithmic"
    EXPONENTIAL = "exponential"
    
    @classmethod
    def from_string(cls, curve_str: Union[str, None]) -> 'FadeCurve':
        """
        Convert string to FadeCurve enum, defaulting to LINEAR if None or invalid.
        
        Args:
            curve_str: String representation of curve type
            
        Returns:
            FadeCurve enum value, defaults to LINEAR
        """
        if curve_str is None:
            return cls.LINEAR
        
        curve_str_lower = curve_str.lower().strip()
        for curve in cls:
            if curve.value == curve_str_lower:
                return curve
        
        # Default to linear if invalid
        return cls.LINEAR


def generate_fade_curve(
    curve_type: FadeCurve,
    num_samples: int,
    fade_in: bool = True
) -> np.ndarray:
    """
    Generate gain multipliers for fade curve.
    
    Args:
        curve_type: Type of fade curve (LINEAR, LOGARITHMIC, EXPONENTIAL)
        num_samples: Number of samples in the fade
        fade_in: If True, fade from 0.0 to 1.0; if False, fade from 1.0 to 0.0
        
    Returns:
        Array of gain multipliers (0.0 to 1.0 for fade-in, 1.0 to 0.0 for fade-out)
    """
    if num_samples <= 0:
        return np.array([])
    
    # Generate progress array from 0.0 to 1.0
    progress = np.linspace(0.0, 1.0, num_samples)
    
    if curve_type == FadeCurve.LINEAR:
        # Linear: gain = progress
        gain = progress.copy()
    
    elif curve_type == FadeCurve.LOGARITHMIC:
        # Logarithmic: gain = log10(1 + 9 * progress) / log10(10)
        # This creates a curve that starts slow and accelerates
        # Maps [0, 1] to [0, 1] using logarithmic scale
        gain = np.log10(1.0 + 9.0 * progress) / math.log10(10.0)
    
    elif curve_type == FadeCurve.EXPONENTIAL:
        # Exponential: gain = (10^progress - 1) / 9
        # This creates a curve that starts fast and decelerates
        # Maps [0, 1] to [0, 1] using exponential scale
        gain = (np.power(10.0, progress) - 1.0) / 9.0
    
    else:
        # Fallback to linear
        gain = progress.copy()
    
    # For fade-out, reverse the curve (1.0 to 0.0)
    if not fade_in:
        gain = 1.0 - gain
    
    # Ensure values are in valid range [0.0, 1.0]
    gain = np.clip(gain, 0.0, 1.0)
    
    return gain
