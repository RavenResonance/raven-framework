"""Wide additive halo approximation for Raven simulator HUD light leakage.

Keeps the sharp HUD core and adds one broad, low-energy Gaussian halo in
linear-light byte space before the blend. Does not touch Raven's PSF.

Computed at reduced resolution and scaled back up: a wide halo is
low-frequency, so this costs a fraction of a full-resolution blur for the
same result -- the simulator discards any frame slower than the queue.

The blurred layer is rescaled so its own peak is `strength` of the source
peak, not the energy the blur spread out (a Gaussian blur preserves energy,
so a thin line blurred wide returns much dimmer). Scaled against the frame's
brightest pixel, matching a HUD drawn at one brightness.
"""

from __future__ import annotations

import cv2
import numpy as np

# Blur at 1/DOWNSCALE resolution -- see module docstring.
DOWNSCALE = 4

# Below this radius the downscale-and-blur round trip costs more than it
# saves, and the halo is tight enough that resampling would show.
MIN_RADIUS_FOR_DOWNSCALE = 8


def _blur(linear_u8: np.ndarray, radius: int) -> np.ndarray:
    """A broad Gaussian, blurred in float so faint energy doesn't quantise to zero."""
    if radius < MIN_RADIUS_FOR_DOWNSCALE:
        return cv2.GaussianBlur(
            linear_u8.astype(np.float32),
            (0, 0),
            sigmaX=float(radius),
            sigmaY=float(radius),
            borderType=cv2.BORDER_REFLECT_101,
        )

    height, width = linear_u8.shape[:2]
    small = cv2.resize(
        linear_u8,
        (max(1, width // DOWNSCALE), max(1, height // DOWNSCALE)),
        interpolation=cv2.INTER_AREA,
    ).astype(np.float32)

    sigma = max(0.5, float(radius) / DOWNSCALE)
    small = cv2.GaussianBlur(
        small,
        (0, 0),
        sigmaX=sigma,
        sigmaY=sigma,
        borderType=cv2.BORDER_REFLECT_101,
    )

    # Linear interpolation back up is enough: what is being resampled has
    # already had everything above the sampling frequency blurred out of it.
    return cv2.resize(small, (width, height), interpolation=cv2.INTER_LINEAR)


def apply_waveguide_halo(
    hud_linear_u8: np.ndarray,
    radius: int,
    strength: float,
) -> np.ndarray:
    """Sharp HUD + one additive halo, uint8 in/out.

    radius/strength are the fixed config.json values; only called when
    CONSIDER_WAVEGUIDE_HALO is on.
    """
    if strength == 0.0:
        return hud_linear_u8

    source_peak = float(hud_linear_u8.max())
    if source_peak <= 0.0:
        return hud_linear_u8

    layer = _blur(hud_linear_u8, radius)
    layer_peak = float(layer.max())
    if layer_peak <= 0.0:
        return hud_linear_u8

    # Peak-normalise -- see module docstring.
    out = (
        hud_linear_u8.astype(np.float32) + layer * (source_peak / layer_peak) * strength
    )
    return np.clip(out, 0.0, 255.0).astype(np.uint8)
