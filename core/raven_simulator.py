# ================================================================
# Raven Framework
#
# Copyright (c) 2026 Raven Resonance, Inc.
# All Rights Reserved.
#
# ================================================================

"""
Simulator overlay for Raven apps (non-device only).
Displays a background with the app snapshot overlaid for development preview.
"""

import os
import queue
import time
from pathlib import Path
from typing import List, Optional

import numpy as np
import shiboken6
from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
    Qt,
    QThread,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QEnterEvent,
    QImage,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPixmap,
    QRegion,
)
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressDialog,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..helpers.animation_utils import fade_in, fade_out
from ..helpers.logger import get_logger
from ..helpers.utils_light import load_config, set_custom_circle_cursor
from .simulator_background import (
    DEFAULT_BACKGROUND_PRESET,
    SimulatorBackgroundPreset,
    SimulatorBackgroundWidget,
    _BackgroundUploadWorker,
    _list_uploaded_backgrounds,
    _resize_cover,
    default_background_size,
    media_size,
)
from .simulator_recorder import (
    SimulatorRecordWorker,
    clear_stale_recordings,
    discard_recording,
    last_recordings_dir,
    last_screenshots_dir,
    save_recording,
    save_screenshot,
    screenshot_filename,
    temp_recording_path,
)
from .waveguide_halo import DOWNSCALE as HALO_DOWNSCALE
from .waveguide_halo import apply_waveguide_halo

log = get_logger("RunApp")
_config = load_config()

# Feature flags
USE_SIMPLE_ADDITIVE_BLEND = _config["simulator"]["USE_SIMPLE_ADDITIVE_BLEND"]
ENABLE_UI_SHRINK = _config["simulator"]["ENABLE_UI_SHRINK"]
ENABLE_SIMULATE_BACKLIGHT = _config["simulator"]["ENABLE_SIMULATE_BACKLIGHT"]
ENABLE_TINT = _config["simulator"]["DEFAULT_ENABLE_TINT"]
OVERLAY_FRAME_RATE = _config["fps"]["SIMULATOR_FPS"]
DISPLAY_RESOLUTION = tuple(_config["resolution"]["DISPLAY_RESOLUTION"])
DEFAULT_OVERLAY_BRIGHTNESS = _config["simulator"]["DEFAULT_OVERLAY_BRIGHTNESS"]
APP_WINDOW_RESOLUTION = (DISPLAY_RESOLUTION[0], DISPLAY_RESOLUTION[1])
CLIENT_DEVICE_ADDITIONAL_WINDOW_HEIGHT = 60
WINDOW_TITLE_BAR_ALLOWANCE = 32
STAGE_BACKDROP_RGB = (30, 30, 30)
STAGE_BACKDROP_COLOR = "#{:02X}{:02X}{:02X}".format(*STAGE_BACKDROP_RGB)
RECORD_BUTTON_IDLE_TEXT = "● Record"
TINT_SLIDER_PANEL_WIDTH = 170
TINT_SLIDER_ANIM_MS = 250
BAR_REFLECTION_BLUR_SIGMA = 16
BAR_REFLECTION_DIM = 0.6
QWIDGETSIZE_MAX = 16777215  # Qt max
SIMULATOR_CV_THREADS = 1  # less CPU on macOS
RAW_MODE_TOOLTIP_TEXT = _config["simulator"]["RAW_MODE_TOOLTIP_TEXT"]
PRINT_SIMULATOR_PERFORMANCE = _config["simulator"]["PRINT_SIMULATOR_PERFORMANCE"]
SIMULATOR_CALIBRATION_FILENAME = _config["simulator"]["SIMULATOR_CALIBRATION_FILENAME"]
FIXED_BACKGROUND_TINT_FACTOR = _config["simulator"]["FIXED_BACKGROUND_TINT_FACTOR"]
TINT_DEFAULT_STRENGTH = round((1.0 - FIXED_BACKGROUND_TINT_FACTOR) * 100)
UI_SHRINK_WIDTH = _config["simulator"]["UI_SHRINK_WIDTH"]
UI_SHRINK_HEIGHT = _config["simulator"]["UI_SHRINK_HEIGHT"]
UI_SHRINK_OFFSET_X = _config["simulator"]["UI_SHRINK_OFFSET_X"]
UI_SHRINK_OFFSET_Y = _config["simulator"]["UI_SHRINK_OFFSET_Y"]
UI_RIGHT_MARGIN = DISPLAY_RESOLUTION[0] - UI_SHRINK_OFFSET_X - UI_SHRINK_WIDTH
UI_CENTER_ANCHOR_MIN_WIDTH = 2 * (UI_SHRINK_WIDTH + UI_RIGHT_MARGIN)
CONSIDER_POINT_SPREAD = _config["simulator"]["CONSIDER_POINT_SPREAD"]
CONSIDER_WAVEGUIDE_HALO = _config["simulator"]["CONSIDER_WAVEGUIDE_HALO"]
HALO_RADIUS = _config["simulator"]["HALO_RADIUS"]
HALO_STRENGTH = _config["simulator"]["HALO_STRENGTH"]


DEFAULT_SIMULATOR_BACKGROUND_RGB = (40, 40, 40)
BACKLIGHT_COLOR_RGB = (7, 7, 15)
_BACKLIGHT_LAYER_BGR = np.full(
    (UI_SHRINK_HEIGHT, UI_SHRINK_WIDTH, 3), BACKLIGHT_COLOR_RGB[::-1], dtype=np.uint8
)

_cal_path = Path(__file__).resolve().parent / SIMULATOR_CALIBRATION_FILENAME
_cal = np.load(_cal_path, allow_pickle=False)
CIE_R_Y = float(_cal["cie_r_y"])
CIE_G_Y = float(_cal["cie_g_y"])
CIE_B_Y = float(_cal["cie_b_y"])
GAMMA = float(_cal["gamma"])
SUPPRESS = float(_cal["suppress"])
DEMAND_THRESHOLD = float(_cal["demand_threshold"])
POINT_SPREAD_KERNEL = _cal["point_spread_kernel"].astype(np.float32)
_cal.close()


TOTAL_CIE_Y = CIE_R_Y + CIE_G_Y + CIE_B_Y
_WEIGHT_R = CIE_R_Y / TOTAL_CIE_Y
_WEIGHT_G = CIE_G_Y / TOTAL_CIE_Y
_WEIGHT_B = CIE_B_Y / TOTAL_CIE_Y


def _build_srgb_linear_luts():
    """No args. Returns (srgb_to_lin, lin_to_srgb): two 256 float32 LUTs for sRGB <-> linear."""
    c = np.arange(256, dtype=np.float32) / 255.0
    srgb_to_lin = np.where(
        c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4
    ).astype(np.float32)
    lin_to_srgb = np.where(
        c <= 0.0031308, c * 12.92, 1.055 * (c ** (1.0 / 2.4)) - 0.055
    )
    return srgb_to_lin, np.clip(lin_to_srgb, 0.0, 1.0).astype(np.float32)


def _build_lut_d_3d():
    """No args. Returns (256,256,256) uint8 LUT: (snp_b, snp_g, snp_r) sRGB -> demand d in [0,255]."""
    s2l = _LUT_SRGB_TO_LIN
    b = np.arange(256, dtype=np.uint8)
    g = np.arange(256, dtype=np.uint8)
    r = np.arange(256, dtype=np.uint8)
    lin_b = s2l[b].reshape(256, 1, 1)
    lin_g = s2l[g].reshape(1, 256, 1)
    lin_r = s2l[r].reshape(1, 1, 256)
    lum = _WEIGHT_B * lin_b + _WEIGHT_G * lin_g + _WEIGHT_R * lin_r
    lum_thresh = np.maximum(lum - DEMAND_THRESHOLD, 0.0)
    d = (lum_thresh**GAMMA) * SUPPRESS
    return (np.clip(d * 255.0, 0, 255)).astype(np.uint8)


def _build_lut_d_3d_linear():
    """Returns (256,256,256) uint8 LUT: (lin_b, lin_g, lin_r) linear bytes -> demand d. Used when PSF is applied in linear space."""
    b = np.arange(256, dtype=np.float32).reshape(256, 1, 1) / 255.0
    g = np.arange(256, dtype=np.float32).reshape(1, 256, 1) / 255.0
    r = np.arange(256, dtype=np.float32).reshape(1, 1, 256) / 255.0
    lum = _WEIGHT_B * b + _WEIGHT_G * g + _WEIGHT_R * r
    lum_thresh = np.maximum(lum - DEMAND_THRESHOLD, 0.0)
    d = (lum_thresh**GAMMA) * SUPPRESS
    return (np.clip(d * 255.0, 0, 255)).astype(np.uint8)


def _build_lut_out_3d():
    """No args. Returns (256,256,256) uint8 LUT: (bg_lin_byte, snp_lin_byte, d_byte) -> out_srgb_byte."""
    i = np.arange(256, dtype=np.float32).reshape(256, 1, 1) / 255.0
    j = np.arange(256, dtype=np.float32).reshape(1, 256, 1) / 255.0
    k = np.arange(256, dtype=np.float32).reshape(1, 1, 256) / 255.0
    out_lin = np.clip(i * (1.0 - k) + j, 0.0, 1.0)
    idx = (out_lin * 255.0).clip(0, 255).astype(np.uint8)
    return _LUT_LIN_TO_SRGB_BYTE[idx]


def _build_lin_to_srgb_byte():
    """Returns 256 uint8 LUT: linear index -> sRGB byte. Used in _build_lut_out_3d."""
    return (np.clip(_LUT_LIN_TO_SRGB * 255.0, 0, 255)).astype(np.uint8)


def _build_srgb_to_lin_byte():
    """uint8 LUT: sRGB index -> linear quantized 0-255. Avoids float image + quantize in hot path."""
    return (np.clip(_LUT_SRGB_TO_LIN * 255.0, 0, 255)).astype(np.uint8)


def _build_lut_tint(factor: float):
    """256-entry uint8 LUT: value -> round(value*factor) clipped to [0,255]."""
    values = np.round(np.arange(256, dtype=np.float32) * factor)
    return np.clip(values, 0, 255).astype(np.uint8)


_LUT_SRGB_TO_LIN, _LUT_LIN_TO_SRGB = _build_srgb_linear_luts()
_LUT_LIN_TO_SRGB_BYTE = _build_lin_to_srgb_byte()
_LUT_SRGB_TO_LIN_BYTE = _build_srgb_to_lin_byte()
_LUT_D_3D = _build_lut_d_3d()
_LUT_D_3D_LINEAR = _build_lut_d_3d_linear()
_LUT_OUT_3D = _build_lut_out_3d()
_LUT_TINT = _build_lut_tint(FIXED_BACKGROUND_TINT_FACTOR)
_LUT_BG_PASSTHROUGH = _LUT_OUT_3D[_LUT_SRGB_TO_LIN_BYTE, 0, 0]


def _blend_pad() -> int:
    """HUD light spread."""
    pad = POINT_SPREAD_KERNEL.shape[0] // 2 if CONSIDER_POINT_SPREAD else 0
    if CONSIDER_WAVEGUIDE_HALO and HALO_STRENGTH != 0.0:
        pad += 4 * HALO_RADIUS + 2 * HALO_DOWNSCALE
    return -(-pad // HALO_DOWNSCALE) * HALO_DOWNSCALE


_BLEND_PAD = _blend_pad()


def blend_frame(bg_bgr, snapshot_bgr):
    """Linear suppress blend: bg_bgr and snapshot_bgr (BGR uint8, same shape). Returns blended BGR uint8."""
    # -------------------------------------------------------------------------
    # FULL PIPELINE MATH
    # -------------------------------------------------------------------------
    #
    # 1. CONVERT IMAGES FROM sRGB TO LINEAR
    #    Blend math is done in linear light so that adding light is correct.
    #    We linearize bg and hud at the start:
    #      linear(c) = c/12.92                    if c ≤ 0.04045
    #                  ((c+0.055)/1.055)^2.4      otherwise
    #    This gives us bg_lin and hud_lin.
    #    Source:https://www.color.org/srgb.pdf
    #
    # 2. POINT-SPREAD (PSF) ADJUSTMENT
    #    PSF models how a point of light spreads into neighboring pixels on the waveguide.
    #    Blur is a linear operation on light, so the PSF is applied to the HUD in linear
    #    space (after linearizing the HUD). We use a single PSF for all three
    #    channels (R, G, B) for now.
    #
    # 2b. OPTIONAL WAVEGUIDE HALO
    #    A separate, purely visual effect (apply_waveguide_halo): adds one
    #    broad, low-energy blur of the linear HUD back onto itself, sharp
    #    core intact, approximating light leakage on the waveguide. Runs in
    #    the same linear-light space as the PSF step above, independently of
    #    it; either one enabled forces demand (below) to be computed from
    #    linear HUD bytes instead of the raw sRGB snapshot.
    #
    # 3. CALCULATING HUD DEMAND (FROM LUMINANCE)
    #    hud_lum = weight_r * hud_lin[0] + weight_g * hud_lin[1] + weight_b * hud_lin[2]
    #    with weight_r, weight_g, weight_b = CIE_R_Y/TOTAL_CIE_Y etc. (normalized) and hud_lin[0], hud_lin[1], hud_lin[2]
    #    are rgb of hud_lin calculated above.
    #    - Luminance is the perceived brightness of the hud in linear light.
    #    - GAMMA: exponent that shapes how hud brightness maps to demand (e.g. 0.1 compresses the curve).
    #    - SUPPRESS: a global factor in [0,1] (e.g. 0.7) that scales how strong the dimming is overall.
    #    - DEMAND_THRESHOLD: a small luminance offset so very low luminance / PSF bleed does not create demand.
    #    Physically, the real waveguide simply adds HUD photons on top of background
    #    photons at the retina — the combiner does not dim the background at all.
    #    However a real display has a fixed peak brightness ceiling —
    #    any combined light value exceeding that ceiling clips to maximum white,
    #    losing contrast information. We dim the background by (1-d) to keep
    #    the sum within the display's reproducible range.
    #    This is a perceptual approximation of the eye's local
    #    adaptation response to competing bright stimuli — not a physical property
    #    of the waveguide itself.
    #    Hence, Demand:  d = ((max(hud_lum - DEMAND_THRESHOLD, 0)) ^ GAMMA) * SUPPRESS
    #    So brighter hud → higher hud_lum → higher d → more background suppressed in the blend, while very low
    #    luminance below DEMAND_THRESHOLD does not cause suppression.
    #
    # 4. ADDITIVE BLEND
    #    Basically  out_lin = bg_lin' + hud_lin'
    #    with  bg_lin' = bg_lin * (1 - d) * transmission
    #    (transmission can be computed from many factors: glass used, pupil opening with hud brightness, etc.)
    #    and  hud_lin' = hud_lin * hud_gain + blackfloor  (constant so hud is not too dark).
    #    Note: hud_gain can be more complex (e.g. per-channel scales so R, G, B scale differently).
    #    Hence full form:  out_lin = bg_lin * (1 - d) * transmission + hud_lin * hud_gain + blackfloor
    #
    #    For simpler computation we ignore blackfloor (assume 0), transmission (assume 1), and hud_gain
    #    (assume 1). Thus the simplified formula we use is:  out_lin = bg_lin * (1 - d) + hud_lin,
    #    i.e.  out_lin = bg_lin * (1 - (hud_lum ^ GAMMA) * SUPPRESS) + hud_lin.
    #    GAMMA and SUPPRESS are constants empirically selected to match the behavior of the hud in the real world.
    #
    # 5. CONVERT RESULT BACK TO sRGB
    #    Clamp out_lin to [0,1], then encode to sRGB for display/PNG:
    #      sRGB(c) = c*12.92                     if c ≤ 0.0031308
    #                1.055*c^(1/2.4) - 0.055     otherwise
    #    Source:https://www.color.org/srgb.pdf
    #    Then clamp and convert to uint8 for PNG.
    #
    # Note: the pipeline as a whole — the linearization, LCOS-derived luminance
    # weights, demand formulation, PSF, and blend order — is designed and tuned
    # so that the simulator output matches what an observer perceives on the real
    # waveguide hardware. Individual effects visible on the real display such as
    # chromatic aberration, focal plane defocus, waveguide edge falloff, and LCOS
    # blackfloor leakage are not modeled as separate explicit steps but are
    # collectively approximated through the empirical calibration of the pipeline
    # as a whole.
    #
    # -------------------------------------------------------------------------
    #
    # HOW THIS IS COMPUTED (LUT-BASED)
    #    Step 1 (math step 1): Linearize bg and HUD via _LUT_SRGB_TO_LIN_BYTE.
    #    Step 2 (math step 2): If PSF enabled, convolve linear HUD only (cv2.filter2D).
    #    Step 2b (math step 2b): If the waveguide halo is enabled, blend it
    #    into the linear HUD too (apply_waveguide_halo).
    #    Step 3 (math step 3): Demand d from _LUT_D_3D_LINEAR(lin_hud) if
    #    either optional step ran, else _LUT_D_3D(sRGB snapshot).
    #    Step 4 (math steps 4 and 5): Blended output via _LUT_OUT_3D(bg_lin_byte, hud_lin_byte, d) per channel;
    #    each entry = out_lin = bg_lin*(1-d)+hud_lin then linear→sRGB byte.
    # -------------------------------------------------------------------------
    import cv2

    return _blend_background(bg_bgr, *_hud_stage(snapshot_bgr))


def _hud_stage(snapshot_bgr):
    """HUD half of blend_frame."""
    import cv2

    # Step 1
    si = cv2.LUT(snapshot_bgr, _LUT_SRGB_TO_LIN_BYTE)

    # Step 2
    use_linear_demand = False
    if CONSIDER_POINT_SPREAD:
        si = cv2.filter2D(si, -1, POINT_SPREAD_KERNEL)
        use_linear_demand = True

    # Step 2b
    if CONSIDER_WAVEGUIDE_HALO:
        si = apply_waveguide_halo(si, HALO_RADIUS, HALO_STRENGTH)
        use_linear_demand = True

    # Step 3
    d = _take_3d(
        _LUT_D_3D_LINEAR if use_linear_demand else _LUT_D_3D,
        si if use_linear_demand else snapshot_bgr,
    )

    return si, d


def _blend_background(bg_bgr, si, d):
    """Background half of blend_frame."""
    import cv2

    bi = cv2.LUT(bg_bgr, _LUT_SRGB_TO_LIN_BYTE)
    return _take_3d(_LUT_OUT_3D, bi, si, d[:, :, None])


def _take_3d(lut, a, b=None, c=None):
    """Fast 3D LUT lookup."""
    if b is None:
        a, b, c = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    index = a.astype(np.uint32) << 16
    index |= b.astype(np.uint32) << 8
    index |= c
    return np.take(lut.reshape(-1), index, mode="clip")


def compose_frame(bg_bgr, ui_bgr, ui_x: int, ui_y: int, hud_cache=None):
    """Blend HUD onto background."""
    import cv2

    canvas_h, canvas_w = bg_bgr.shape[:2]
    ui_h, ui_w = ui_bgr.shape[:2]
    if USE_SIMPLE_ADDITIVE_BLEND:
        out = bg_bgr.copy()
        pad = 0
    else:
        out = cv2.LUT(bg_bgr, _LUT_BG_PASSTHROUGH)
        pad = _BLEND_PAD

    x0, y0 = max(0, ui_x - pad), max(0, ui_y - pad)
    x1, y1 = min(canvas_w, ui_x + ui_w + pad), min(canvas_h, ui_y + ui_h + pad)
    if x1 <= x0 or y1 <= y0:
        return out

    key = (x0 - ui_x, y0 - ui_y, x1 - x0, y1 - y0)
    cached = hud_cache.get(key) if hud_cache is not None else None
    if cached is None:
        hud = np.zeros((y1 - y0, x1 - x0, 3), dtype=np.uint8)
        ux0, uy0 = max(ui_x, x0), max(ui_y, y0)
        ux1, uy1 = min(ui_x + ui_w, x1), min(ui_y + ui_h, y1)
        if ux1 > ux0 and uy1 > uy0:
            hud[uy0 - y0 : uy1 - y0, ux0 - x0 : ux1 - x0] = ui_bgr[
                uy0 - ui_y : uy1 - ui_y, ux0 - ui_x : ux1 - ui_x
            ]
        cached = hud if USE_SIMPLE_ADDITIVE_BLEND else _hud_stage(hud)
        if hud_cache is not None:
            hud_cache[key] = cached

    bg_window = bg_bgr[y0:y1, x0:x1]
    if USE_SIMPLE_ADDITIVE_BLEND:
        out[y0:y1, x0:x1] = cv2.add(bg_window, cached)
    else:
        out[y0:y1, x0:x1] = _blend_background(bg_window, *cached)
    return out


class SimulatorBlendWorker(QObject):
    """Runs in a QThread; blends the app's BGR render with the background via ``compose_frame``."""

    result_ready = Signal(object, int, int, int, object)

    def __init__(self, blend_queue: queue.Queue, get_bg_fn) -> None:
        super().__init__()
        self._queue = blend_queue
        self._get_bg = get_bg_fn
        self._last_ui_key = None
        self._ui_bgr = None
        self._hud_cache: dict = {}

    def process_loop(self) -> None:
        import cv2
        import numpy as np

        while True:
            try:
                item = self._queue.get()
            except Exception:
                break
            if item is None:
                break
            try:
                (
                    app_bytes,
                    w,
                    h,
                    seq,
                    brightness,
                    canvas_w,
                    canvas_h,
                    ui_x,
                    ui_y,
                ) = item
                bg_bgr = self._get_bg()
                if bg_bgr is None:
                    log.warning(
                        "SimulatorBlendWorker: No background passed to blend worker, using default background"
                    )
                    bg_bgr = np.full(
                        (canvas_h, canvas_w, 3),
                        DEFAULT_SIMULATOR_BACKGROUND_RGB[::-1],
                        dtype=np.uint8,
                    )
                elif bg_bgr.shape[:2] != (canvas_h, canvas_w):
                    bg_bgr = _resize_cover(bg_bgr, canvas_w, canvas_h)
                if ENABLE_TINT:
                    bg_bgr = cv2.LUT(bg_bgr, _LUT_TINT)
                ui_bgr = self._prepared_ui(app_bytes, w, h, brightness)
                blended = np.ascontiguousarray(
                    compose_frame(bg_bgr, ui_bgr, ui_x, ui_y, self._hud_cache)
                )
                out_h, out_w = blended.shape[:2]
                bar = _bar_reflection(blended, CLIENT_DEVICE_ADDITIONAL_WINDOW_HEIGHT)
                frame_bgra = cv2.cvtColor(blended, cv2.COLOR_BGR2BGRA)
                self.result_ready.emit(
                    frame_bgra.tobytes(), out_w, out_h, seq, bar.tobytes()
                )
            except Exception as e:
                log.debug(f"SimulatorBlendWorker: {e}")

    def _prepared_ui(self, app_bytes: bytes, w: int, h: int, brightness: float):
        """Shrunk, backlit HUD."""
        import cv2

        key = (w, h, brightness)
        if self._ui_bgr is not None and self._last_ui_key == (key, app_bytes):
            return self._ui_bgr
        ui = np.frombuffer(app_bytes, dtype=np.uint8).reshape((h, w, 4))
        if brightness != 1.0:
            ui = cv2.convertScaleAbs(ui, alpha=brightness, beta=0)
        if ENABLE_UI_SHRINK:
            ui = cv2.resize(
                ui, (UI_SHRINK_WIDTH, UI_SHRINK_HEIGHT), interpolation=cv2.INTER_AREA
            )
        ui_bgr = cv2.cvtColor(ui, cv2.COLOR_BGRA2BGR)
        if ENABLE_UI_SHRINK and ENABLE_SIMULATE_BACKLIGHT:
            _apply_backlight_in_place(ui_bgr)
        self._last_ui_key = (key, app_bytes)
        self._ui_bgr = ui_bgr
        self._hud_cache = {}
        return ui_bgr


def _apply_backlight_in_place(ui_bgr) -> None:
    import cv2

    black_mask = cv2.inRange(ui_bgr, (0, 0, 0), (0, 0, 0))
    kept = cv2.bitwise_and(ui_bgr, ui_bgr, mask=cv2.bitwise_not(black_mask))
    lit = cv2.bitwise_and(_BACKLIGHT_LAYER_BGR, _BACKLIGHT_LAYER_BGR, mask=black_mask)
    ui_bgr[:] = cv2.bitwise_or(kept, lit)


def _bar_reflection(frame, bar_h: int):
    import cv2

    strip = cv2.flip(frame[-bar_h:], 0)
    h, w = strip.shape[:2]
    small = cv2.resize(
        strip, (max(1, w // 4), max(1, h // 4)), interpolation=cv2.INTER_AREA
    )
    sigma = BAR_REFLECTION_BLUR_SIGMA / 4
    small = cv2.GaussianBlur(small, (0, 0), sigmaX=sigma, sigmaY=sigma)
    blurred = cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)
    return np.ascontiguousarray(
        cv2.convertScaleAbs(blurred, alpha=BAR_REFLECTION_DIM, beta=0)
    )


class _OpaqueBackdrop(QWidget):
    """Opaque stage fill."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self._color = QColor(*STAGE_BACKDROP_RGB)

    def paintEvent(self, event) -> None:
        QPainter(self).fillRect(event.rect(), self._color)


class _FrameView(QWidget):
    """Frame display."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._image: Optional[QImage] = None
        self._data: Optional[bytes] = None  # keeps buffer alive

    def set_frame(self, data: bytes, w: int, h: int, fmt: QImage.Format) -> None:
        bytes_per_pixel = 4 if fmt == QImage.Format.Format_RGB32 else 3
        self._data = data
        self._image = QImage(data, w, h, w * bytes_per_pixel, fmt)
        self.update()

    def current_image(self) -> Optional[QImage]:
        """Deep copy of the frame on screen, or None if nothing is shown yet."""
        return None if self._image is None else self._image.copy()

    def clear(self) -> None:
        self._image = None
        self._data = None
        self.update()

    def paintEvent(self, event) -> None:
        if self._image is None:
            return
        painter = QPainter(self)
        scale = self.width() * self.devicePixelRatioF() / max(1, self._image.width())
        if abs(scale - round(scale)) > 1e-3:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawImage(self.rect(), self._image)


class _ReflectionBar(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._reflection: Optional[QPixmap] = None

    def set_reflection(self, bgr_bytes: bytes, w: int, h: int) -> None:
        image = QImage(bgr_bytes, w, h, 3 * w, QImage.Format.Format_BGR888)
        self._reflection = QPixmap.fromImage(image.copy())
        self.update()

    def clear_reflection(self) -> None:
        self._reflection = None
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        if self._reflection is None:
            painter.fillRect(self.rect(), QColor(*STAGE_BACKDROP_RGB))
        else:
            painter.drawPixmap(self.rect(), self._reflection)
        painter.fillRect(0, 0, self.width(), 1, QColor(255, 255, 255, 28))


class _TranslucentPopup(QWidget):
    """A Qt.Popup with a hand-painted translucent rounded frame.

    QSS `background-color: rgba(...)` on a WA_TranslucentBackground
    top-level window doesn't reliably blend on this platform — it renders
    fully transparent instead. Painting the frame directly with QPainter
    (which genuinely composites the alpha channel) does. Ordinary QSS
    rgba() on non-toplevel child widgets (e.g. the popup's rows) is
    unaffected by this and works normally.
    """

    def __init__(self, fill_color: QColor, border_color: QColor, radius: int) -> None:
        super().__init__(None, Qt.Popup)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._fill_color = fill_color
        self._border_color = border_color
        self._radius = radius
        self.on_resize = None

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.on_resize is not None:
            QTimer.singleShot(0, self.on_resize)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(0, 0, -1, -1)

        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gradient.setColorAt(0.0, self._fill_color.lighter(145))
        gradient.setColorAt(0.5, self._fill_color)
        gradient.setColorAt(1.0, self._fill_color.darker(110))
        painter.setPen(self._border_color)
        painter.setBrush(gradient)
        painter.drawRoundedRect(rect, self._radius, self._radius)


class _GazeRemapOverlay(QWidget):
    """Remaps mouse ("gaze") events from the shrunk/letterboxed composite
    view back onto the real, full-size app widget underneath.
    """

    def __init__(self, app_widget: QWidget, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._app_widget = app_widget
        self._scale_x = 1.0
        self._scale_y = 1.0
        self._offset = QPoint(0, 0)
        self._gaze_target: Optional[QWidget] = None
        self._gaze_chain: list[QWidget] = []
        self.setMouseTracking(True)
        self.set_active(False)

    def set_transform(self, scale_x: float, scale_y: float, offset: QPoint) -> None:
        self._scale_x = scale_x
        self._scale_y = scale_y
        self._offset = offset

    def set_active(self, active: bool) -> None:
        self.setAttribute(Qt.WA_TransparentForMouseEvents, not active)
        if not active:
            self._clear_gaze_target()

    def _send_leave(self, target: QWidget) -> None:
        if not shiboken6.isValid(target):
            return
        QApplication.sendEvent(target, QEvent(QEvent.Type.Leave))

    def _clear_gaze_target(self) -> None:
        chain = self._gaze_chain
        self._gaze_chain = []
        self._gaze_target = None
        for widget in chain:
            self._send_leave(widget)

    def _resolve_chain(self, pos: QPoint) -> list:
        target = self._resolve_target(pos)
        if target is None:
            return []
        chain = []
        widget = target
        while widget is not None and shiboken6.isValid(widget):
            chain.append(widget)
            if widget is self._app_widget:
                break
            widget = widget.parentWidget()
        return chain

    def _real_point(self, pos: QPoint) -> QPoint:
        real_x = (pos.x() - self._offset.x()) / self._scale_x
        real_y = (pos.y() - self._offset.y()) / self._scale_y
        return QPoint(round(real_x), round(real_y))

    def _resolve_target(self, pos: QPoint) -> Optional[QWidget]:
        if not shiboken6.isValid(self._app_widget):
            return None
        real_point = self._real_point(pos)
        if not (
            0 <= real_point.x() < self._app_widget.width()
            and 0 <= real_point.y() < self._app_widget.height()
        ):
            return None
        raw_hit = self._app_widget.childAt(real_point)
        target = raw_hit or self._app_widget
        while (
            target is not self._app_widget
            and shiboken6.isValid(target)
            and not target.isEnabled()
        ):
            target = target.parentWidget()
        return target

    def _forward(self, target: QWidget, event: QMouseEvent) -> None:
        if not (shiboken6.isValid(target) and shiboken6.isValid(self._app_widget)):
            return
        real_point = self._real_point(event.position().toPoint())
        global_point = self._app_widget.mapToGlobal(real_point)
        widget = target
        while widget is not None and shiboken6.isValid(widget):
            local_point = widget.mapFrom(self._app_widget, real_point)
            forwarded = QMouseEvent(
                event.type(),
                QPointF(local_point),
                QPointF(global_point),
                event.button(),
                event.buttons(),
                event.modifiers(),
            )
            QApplication.sendEvent(widget, forwarded)
            if forwarded.isAccepted() or widget is self._app_widget:
                return
            widget = widget.parentWidget()

    def _send_enter(self, target: QWidget, real_point: QPoint) -> None:
        local_point = target.mapFrom(self._app_widget, real_point)
        global_point = self._app_widget.mapToGlobal(real_point)
        enter_event = QEnterEvent(
            QPointF(local_point), QPointF(real_point), QPointF(global_point)
        )
        QApplication.sendEvent(target, enter_event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position().toPoint()
        new_chain = self._resolve_chain(pos)
        new_target = new_chain[0] if new_chain else None
        if new_target is not self._gaze_target:
            old_chain = self._gaze_chain
            old_set = {id(w) for w in old_chain}
            new_set = {id(w) for w in new_chain}
            for widget in old_chain:
                if id(widget) not in new_set:
                    self._send_leave(widget)
            real_point = self._real_point(pos)
            for widget in reversed(new_chain):
                if id(widget) not in old_set and shiboken6.isValid(widget):
                    self._send_enter(widget, real_point)
            self._gaze_chain = new_chain
            self._gaze_target = new_target
        if new_target is not None:
            self._forward(new_target, event)

    def _forward_to_gaze_target(self, event: QMouseEvent) -> None:
        target = self._gaze_target
        if target is not None and shiboken6.isValid(target):
            self._forward(target, event)
        elif target is not None:
            self._gaze_target = None
            self._gaze_chain = []

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._forward_to_gaze_target(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._forward_to_gaze_target(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self._forward_to_gaze_target(event)

    def leaveEvent(self, event) -> None:
        self._clear_gaze_target()
        super().leaveEvent(event)


class SimulatorRunApp(QMainWindow):
    """
    Desktop simulator window: waveguide-style composite (background + blended app),
    Raw/preset controls, and blend worker thread.
    """

    def __init__(self, app_widget: QWidget) -> None:
        if app_widget is None:
            raise ValueError("app_widget cannot be None")

        super().__init__()
        self.background_widget = None
        try:
            import cv2

            cv2.setNumThreads(SIMULATOR_CV_THREADS)
            self.setWindowTitle("Raven App (alpha v1.0.6)")
            total_window_width = APP_WINDOW_RESOLUTION[0]
            total_window_height = (
                APP_WINDOW_RESOLUTION[1] + CLIENT_DEVICE_ADDITIONAL_WINDOW_HEIGHT
            )
            self._min_window_size = (int(total_window_width), int(total_window_height))
            self.setMinimumSize(*self._min_window_size)
            framework_dir = os.path.dirname(os.path.dirname(__file__))
            self._framework_dir = framework_dir
            self.resize(*self._default_window_size(framework_dir))
            container = QWidget(self)
            container.setObjectName("simulatorContainer")
            container.setStyleSheet(
                f"QWidget#simulatorContainer {{ background-color: {STAGE_BACKDROP_COLOR}; }}"
            )
            layout = QVBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            content_w = APP_WINDOW_RESOLUTION[0]
            content_h = APP_WINDOW_RESOLUTION[1]
            self._device_size = (content_w, content_h)
            content_area = QWidget(container)
            content_area.setMinimumSize(content_w, content_h)
            content_area.setAutoFillBackground(False)
            self._content_area = content_area

            self.background_widget = SimulatorBackgroundWidget(
                framework_dir, resolution=(content_w, content_h)
            )
            self.background_widget.setParent(content_area)
            self.background_widget.setGeometry(0, 0, content_w, content_h)
            self._upload_dir = os.path.join(
                framework_dir, "assets", "tmp", "background_uploads"
            )

            app_widget.set_env_background_color("black")
            app_widget.set_app_background_color("black")
            self._app_widget = app_widget
            app_widget.setParent(content_area)
            app_widget.setGeometry(0, 0, content_w, content_h)

            self.background_widget.hide()
            self.background_widget.display_frames = False
            self._stage_backdrop = _OpaqueBackdrop(content_area)

            self._composite_label = _FrameView(content_area)
            self._composite_label.setGeometry(0, 0, content_w, content_h)
            self._composite_label.setAttribute(Qt.WA_TransparentForMouseEvents)

            self._gaze_overlay = _GazeRemapOverlay(app_widget, content_area)
            self._gaze_overlay.setGeometry(0, 0, content_w, content_h)
            self._gaze_overlay.set_active(True)
            self._restack_stage()

            self._composite_timer = QTimer(self)
            self._composite_timer.timeout.connect(self._update_composite)
            interval = int(1000 / OVERLAY_FRAME_RATE) if OVERLAY_FRAME_RATE > 0 else 33
            self._composite_timer.start(interval)
            QTimer.singleShot(0, self._update_composite)

            self._blend_queue = queue.Queue(maxsize=1)
            self._blend_sequence = 0
            self._blend_last_sent = -1
            self._composite_grab_pending = False
            get_bg_fn = lambda: (
                self.background_widget.get_latest_background_bgr()
                if self.background_widget is not None
                else None
            )
            self._blend_worker = SimulatorBlendWorker(self._blend_queue, get_bg_fn)
            self._blend_thread = QThread(self)
            self._blend_worker.moveToThread(self._blend_thread)
            self._blend_thread.started.connect(self._blend_worker.process_loop)
            self._blend_worker.result_ready.connect(self._on_blend_result)
            self._blend_thread.start()

            self._timing_total_ms: List[float] = []
            self._last_put_time: Optional[float] = None
            self._timing_report_timer = QTimer(self)
            self._timing_report_timer.setInterval(3000)
            self._timing_report_timer.timeout.connect(self._print_timing_averages)
            self._timing_report_timer.start(3000)

            self._raw_mode = False
            self._app_ui_asleep = False
            self._raw_update_timer = QTimer(self)
            self._raw_update_timer.timeout.connect(self._update_raw_composite)

            layout.addWidget(content_area, 1)

            button_container = _ReflectionBar(container)
            self._button_bar = button_container
            button_layout = QHBoxLayout(button_container)
            button_layout.setContentsMargins(10, 8, 10, 8)
            button_layout.setSpacing(12)

            self._mode_buttons_glass = """
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.06);
                    color: rgba(255, 255, 255, 0.85);
                    border: none;
                    border-radius: 8px;
                    font-size: 13px;
                    font-weight: 500;
                    padding: 6px 14px;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.12);
                    color: white;
                }
                QPushButton::menu-indicator {
                    image: none;
                    width: 0px;
                }
            """
            self._mode_buttons_active = """
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.20);
                    color: white;
                    border: 1px solid rgba(255, 255, 255, 0.40);
                    border-radius: 8px;
                    font-size: 13px;
                    font-weight: 700;
                    padding: 6px 14px;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.26);
                }
                QPushButton::menu-indicator {
                    image: none;
                    width: 0px;
                }
            """
            self._active_mode = DEFAULT_BACKGROUND_PRESET.value

            tint_button = QPushButton("Tint", button_container)
            tint_button.setFixedSize(70, 38)
            tint_button.setStyleSheet(self._mode_buttons_glass)
            tint_button.clicked.connect(self._on_tint_toggle_clicked)
            self._tint_button = tint_button
            self._tint_button_hidden_for_raw = False
            self._tint_slider_panel = self._build_tint_slider_panel(button_container)
            self._update_tint_button_style()

            background_popup = _TranslucentPopup(
                fill_color=QColor(0, 0, 0, 140),
                border_color=QColor(255, 255, 255, 60),
                radius=8,
            )
            background_popup.setObjectName("backgroundPopup")
            background_popup.setMinimumWidth(150)
            popup_layout = QVBoxLayout(background_popup)
            popup_layout.setContentsMargins(4, 4, 4, 4)
            popup_layout.setSpacing(0)
            self._background_popup = background_popup
            self._background_popup_layout = popup_layout

            background_button = QPushButton("Background", button_container)
            background_button.setFixedSize(140, 38)
            background_button.setStyleSheet(self._mode_buttons_glass)
            background_button.clicked.connect(self._show_background_popup)
            self._background_button = background_button

            self._record_button_recording = """
                QPushButton {
                    background-color: rgba(218, 59, 38, 0.25);
                    color: white;
                    border: 1px solid rgba(218, 59, 38, 0.85);
                    border-radius: 8px;
                    font-size: 13px;
                    font-weight: 700;
                    padding: 6px 14px;
                }
                QPushButton:hover {
                    background-color: rgba(218, 59, 38, 0.31);
                }
            """
            record_button = QPushButton(RECORD_BUTTON_IDLE_TEXT, button_container)
            record_button.setFixedSize(110, 38)
            record_button.setStyleSheet(self._mode_buttons_glass)
            record_button.setToolTip("Record the simulator view to an mp4")
            record_button.clicked.connect(self._on_record_clicked)
            self._record_button = record_button
            self._recorder: Optional[SimulatorRecordWorker] = None
            self._record_thread: Optional[QThread] = None
            self._record_started_at = 0.0
            self._record_clock_timer = QTimer(self)
            self._record_clock_timer.setInterval(500)
            self._record_clock_timer.timeout.connect(self._update_record_button_text)
            clear_stale_recordings()

            capture_button = QPushButton("Capture", button_container)
            capture_button.setFixedSize(110, 38)
            capture_button.setStyleSheet(self._mode_buttons_glass)
            capture_button.setToolTip("Save the current simulator frame as a png")
            capture_button.clicked.connect(self._on_capture_clicked)
            self._capture_button = capture_button

            button_layout.addWidget(record_button)
            button_layout.addWidget(capture_button)
            button_layout.addStretch()
            button_layout.addWidget(self._tint_slider_panel)
            button_layout.addWidget(tint_button)
            button_layout.addWidget(background_button)
            button_container.setFixedHeight(CLIENT_DEVICE_ADDITIONAL_WINDOW_HEIGHT)
            layout.addWidget(button_container)

            self._update_mode_button_styles()

            self.setCentralWidget(container)
            set_custom_circle_cursor(self._app_widget)
            set_custom_circle_cursor(self._gaze_overlay)

            content_area.installEventFilter(self)
            self._layout_stage()

            log.info("SimulatorRunApp initialized successfully.")
        except Exception as e:
            log.error(f"Failed to initialize SimulatorRunApp: {e}", exc_info=True)
            raise

    def _default_window_size(self, framework_dir: str) -> tuple[int, int]:
        return self._window_size_for_media(default_background_size(framework_dir))

    def _window_size_for_media(
        self, size: Optional[tuple[int, int]]
    ) -> tuple[int, int]:
        min_w, min_h = self._min_window_size
        if size is None:
            return min_w, min_h
        media_w, media_h = size
        screen = self.screen().availableGeometry()
        scale = min(
            1.0,
            screen.width() / media_w,
            (
                screen.height()
                - CLIENT_DEVICE_ADDITIONAL_WINDOW_HEIGHT
                - WINDOW_TITLE_BAR_ALLOWANCE
            )
            / media_h,
        )
        return (
            max(min_w, int(media_w * scale)),
            max(min_h, int(media_h * scale) + CLIENT_DEVICE_ADDITIONAL_WINDOW_HEIGHT),
        )

    def _fit_window_to_media(self, size: Optional[tuple[int, int]]) -> None:
        if size is None or self._recorder is not None:
            return
        if self.isMaximized() or self.isFullScreen():
            return
        self.resize(*self._window_size_for_media(size))
        screen = self.screen().availableGeometry()
        frame = self.frameGeometry()
        x = min(max(frame.x(), screen.left()), screen.right() - frame.width() + 1)
        y = min(max(frame.y(), screen.top()), screen.bottom() - frame.height() + 1)
        if (x, y) != (frame.x(), frame.y()):
            self.move(max(x, screen.left()), max(y, screen.top()))

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self._content_area and event.type() == QEvent.Type.Resize:
            self._layout_stage()
        return super().eventFilter(obj, event)

    def _restack_stage(self) -> None:
        """Fix z-order."""
        self.background_widget.lower()
        self._app_widget.stackUnder(self._stage_backdrop)
        self._stage_backdrop.raise_()
        self._composite_label.raise_()
        self._gaze_overlay.raise_()

    def _ui_rect(self) -> QRect:
        """HUD rect on canvas."""
        area_w = self._content_area.width()
        area_h = self._content_area.height()
        device_w, device_h = self._device_size
        if ENABLE_UI_SHRINK:
            ui_w, ui_h = UI_SHRINK_WIDTH, UI_SHRINK_HEIGHT
            right_margin = UI_RIGHT_MARGIN
            center_anchor_min_width = UI_CENTER_ANCHOR_MIN_WIDTH
        else:
            ui_w, ui_h = device_w, device_h
            right_margin = 0
            center_anchor_min_width = 2 * device_w
        if area_w >= center_anchor_min_width:
            ui_x = area_w // 2
        else:
            ui_x = area_w - right_margin - ui_w
        return QRect(ui_x, (area_h - ui_h) // 2, ui_w, ui_h)

    def _layout_stage(self) -> None:
        area = self._content_area.rect()
        device_w, device_h = self._device_size
        self._stage_backdrop.setGeometry(area)
        self._gaze_overlay.setGeometry(area)
        self.background_widget.set_resolution((area.width(), area.height()))

        if getattr(self, "_raw_mode", False):
            left = (area.width() - device_w) // 2
            top = (area.height() - device_h) // 2
            self._composite_label.setGeometry(left, top, device_w, device_h)
            self._gaze_overlay.set_transform(1.0, 1.0, QPoint(left, top))
        else:
            ui = self._ui_rect()
            self._composite_label.setGeometry(area)
            self._gaze_overlay.set_transform(
                ui.width() / device_w, ui.height() / device_h, ui.topLeft()
            )

    def _render_app_bgra(self) -> Optional[tuple[bytes, int, int]]:
        """App frame, 1x BGRA."""
        w, h = self._app_widget.width(), self._app_widget.height()
        if w <= 0 or h <= 0:
            return None
        image = QImage(w, h, QImage.Format.Format_RGB32)
        image.setDevicePixelRatio(1.0)
        image.fill(Qt.GlobalColor.black)
        painter = QPainter(image)
        try:
            self._app_widget.render(
                painter,
                QPoint(0, 0),
                QRegion(),
                QWidget.RenderFlag.DrawWindowBackground
                | QWidget.RenderFlag.DrawChildren,
            )
        finally:
            painter.end()
        return bytes(image.constBits()), w, h

    def start_hidden(self) -> None:
        """Make the visible surface transparent until revealed (handoff)."""
        effect = QGraphicsOpacityEffect(self._composite_label)
        effect.setOpacity(0.0)
        self._composite_label.setGraphicsEffect(effect)

    def reveal(self, duration_ms: int) -> None:
        """Fade the visible surface in (handoff cross-fade with the launcher)."""
        fade_in(self._composite_label, duration=duration_ms)

    def conceal(self, duration_ms: int) -> None:
        """Fade the visible surface out (mirror of reveal, for app exit)."""
        fade_out(self._composite_label, duration=duration_ms)

    def sleep_app_ui(self, duration_ms: int, curve: str) -> None:
        """Fade the visible simulator UI out."""
        self._app_ui_asleep = True
        if getattr(self, "_raw_mode", False):
            self._raw_update_timer.stop()
        else:
            self._composite_timer.stop()
        fade_out(self._composite_label, duration=duration_ms, curve=curve)

    def wake_app_ui(self, duration_ms: int, curve: str) -> None:
        """Fade the visible simulator UI back in."""
        self._app_ui_asleep = False
        interval = int(1000 / OVERLAY_FRAME_RATE) if OVERLAY_FRAME_RATE > 0 else 33
        fade_in(self._composite_label, duration=duration_ms, curve=curve)
        if getattr(self, "_raw_mode", False):
            self._raw_update_timer.start(interval)
            QTimer.singleShot(0, self._update_raw_composite)
        else:
            self._composite_timer.start(interval)
            QTimer.singleShot(0, self._update_composite)

    def _update_composite(self) -> None:
        if self.background_widget is None or not hasattr(self, "_composite_label"):
            return
        if getattr(self, "_app_ui_asleep", False):
            return
        if getattr(self, "_raw_mode", False):
            return
        if getattr(self, "_composite_grab_pending", False):
            return
        self._composite_grab_pending = True
        QTimer.singleShot(0, self._deferred_composite_grab)

    def _deferred_composite_grab(self) -> None:
        self._composite_grab_pending = False
        if self.background_widget is None or not hasattr(self, "_composite_label"):
            return
        if getattr(self, "_app_ui_asleep", False):
            return
        if getattr(self, "_raw_mode", False):
            return
        result = self._render_app_bgra()
        if result is None:
            return
        app_bytes, w, h = result
        ui = self._ui_rect()
        try:
            seq = self._blend_sequence
            self._blend_sequence += 1
            self._last_put_time = time.perf_counter()
            self._blend_queue.put_nowait(
                (
                    app_bytes,
                    w,
                    h,
                    seq,
                    DEFAULT_OVERLAY_BRIGHTNESS,
                    self._content_area.width(),
                    self._content_area.height(),
                    ui.x(),
                    ui.y(),
                )
            )
            self._blend_last_sent = seq
        except queue.Full:
            pass

    def _on_blend_result(
        self, frame_bytes: bytes, w: int, h: int, seq: int, bar_bytes: bytes
    ) -> None:
        if not hasattr(self, "_composite_label"):
            return
        if seq != getattr(self, "_blend_last_sent", -2):
            return
        if (
            PRINT_SIMULATOR_PERFORMANCE
            and hasattr(self, "_last_put_time")
            and self._last_put_time is not None
        ):
            total_ms = (time.perf_counter() - self._last_put_time) * 1000
            self._timing_total_ms.append(total_ms)
        try:
            self._composite_label.set_frame(
                frame_bytes, w, h, QImage.Format.Format_RGB32
            )
            if not self._raw_mode:
                self._button_bar.set_reflection(
                    bar_bytes, w, CLIENT_DEVICE_ADDITIONAL_WINDOW_HEIGHT
                )
            if self._recorder is not None:
                self._recorder.add_frame(frame_bytes, w, h, w, h, channels=4)
        except Exception as e:
            log.debug(f"Blend result apply: {e}")

    def _print_timing_averages(self) -> None:
        if not PRINT_SIMULATOR_PERFORMANCE:
            return
        if getattr(self, "_raw_mode", True):
            return
        total_list = getattr(self, "_timing_total_ms", None)
        if not total_list or len(total_list) == 0:
            return
        n = len(total_list)
        avg_total_ms = sum(total_list) / n
        expected_fps = OVERLAY_FRAME_RATE
        expected_ms_per_frame = 1000.0 / expected_fps if expected_fps > 0 else 0
        print(
            f"[Simulator timing] (last 3s, n={n}) "
            f"total={avg_total_ms:.2f}ms expected_ms_per_frame={expected_ms_per_frame:.2f}ms ({expected_fps}fps)"
        )
        self._timing_total_ms.clear()

    def _update_raw_composite(self) -> None:
        if not getattr(self, "_raw_mode", False):
            return
        result = self._render_app_bgra()
        if result is None:
            return
        bgra_bytes, w, h = result
        self._composite_label.set_frame(bgra_bytes, w, h, QImage.Format.Format_RGB32)
        if self._recorder is not None:
            self._recorder.add_frame(bgra_bytes, w, h, *self._device_size, channels=4)

    def _on_record_clicked(self) -> None:
        if self._recorder is None:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self) -> None:
        self.setFixedSize(self.size())
        width = self._content_area.width() // 2 * 2  # even for H.264
        height = self._content_area.height() // 2 * 2
        fps = OVERLAY_FRAME_RATE if OVERLAY_FRAME_RATE > 0 else 20
        self._recorder = SimulatorRecordWorker(
            temp_recording_path(), (width, height), fps, STAGE_BACKDROP_RGB
        )
        self._record_thread = QThread(self)
        self._recorder.moveToThread(self._record_thread)
        self._record_thread.started.connect(self._recorder.run)
        self._recorder.finished.connect(self._on_recording_finished)
        self._record_thread.start()

        self._record_started_at = time.perf_counter()
        self._record_button.setStyleSheet(self._record_button_recording)
        self._update_record_button_text()
        self._record_clock_timer.start()
        log.info(f"Simulator recording started: {self._recorder.path}")
        QTimer.singleShot(
            0,
            self._update_raw_composite if self._raw_mode else self._update_composite,
        )

    def _stop_recording(self) -> None:
        if self._recorder is None:
            return
        self._record_clock_timer.stop()
        self._record_button.setEnabled(False)
        self._record_button.setText("Saving…")
        self._recorder.stop()

    def _update_record_button_text(self) -> None:
        elapsed = int(time.perf_counter() - self._record_started_at)
        self._record_button.setText(f"■ {elapsed // 60}:{elapsed % 60:02d}")

    def _on_recording_finished(self, path: str, success: bool) -> None:
        self._record_clock_timer.stop()
        if self._record_thread is not None:
            self._record_thread.quit()
            self._record_thread.wait(3000)
        self._record_thread = None
        self._recorder = None

        self.setMinimumSize(*self._min_window_size)
        self.setMaximumSize(QWIDGETSIZE_MAX, QWIDGETSIZE_MAX)
        self._record_button.setEnabled(True)
        self._record_button.setText(RECORD_BUTTON_IDLE_TEXT)
        self._record_button.setStyleSheet(self._mode_buttons_glass)
        if not success:
            discard_recording(path)
            log.error("Simulator recording failed", extra={"console": True})
            return

        dest_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save recording",
            os.path.join(last_recordings_dir(), os.path.basename(path)),
            "MP4 video (*.mp4)",
        )
        if not dest_path:
            discard_recording(path)
            log.info("Simulator recording discarded", extra={"console": True})
            return
        if not dest_path.lower().endswith(".mp4"):
            dest_path += ".mp4"
        if save_recording(path, dest_path):
            self._record_button.setToolTip(f"Last recording: {dest_path}")
            log.info(f"Simulator recording saved: {dest_path}", extra={"console": True})
        else:
            log.error(f"Simulator recording left at: {path}", extra={"console": True})

    def _on_capture_clicked(self) -> None:
        # Grab before the dialog opens so the shot is the frame the user clicked on.
        image = self._composite_label.current_image()
        if image is None:
            log.warning("No simulator frame to capture yet", extra={"console": True})
            return
        dest_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save screenshot",
            os.path.join(last_screenshots_dir(), screenshot_filename()),
            "PNG image (*.png)",
        )
        if not dest_path:
            return
        if not dest_path.lower().endswith(".png"):
            dest_path += ".png"
        if save_screenshot(image, dest_path):
            self._capture_button.setToolTip(f"Last screenshot: {dest_path}")
            log.info(
                f"Simulator screenshot saved: {dest_path}", extra={"console": True}
            )

    def _set_raw_view(self, raw: bool) -> None:
        if not hasattr(self, "_raw_mode"):
            return
        self._raw_mode = raw
        self._layout_stage()
        interval = int(1000 / OVERLAY_FRAME_RATE) if OVERLAY_FRAME_RATE > 0 else 33
        if raw:
            self._active_mode = "raw"
            self._update_mode_button_styles()
            self._composite_timer.stop()
            self._composite_label.clear()
            self._button_bar.clear_reflection()
            self._raw_update_timer.start(interval)
            QTimer.singleShot(0, self._update_raw_composite)
        else:
            self._raw_update_timer.stop()
            self._active_mode = (
                self.background_widget.current_preset.value
                if self.background_widget is not None
                else DEFAULT_BACKGROUND_PRESET.value
            )
            self._update_mode_button_styles()
            self._composite_label.clear()
            self._composite_timer.start(interval)
            QTimer.singleShot(0, self._update_composite)

    def _update_mode_button_styles(self) -> None:
        is_raw = self._active_mode == "raw"
        self._update_tint_button_style()
        self._update_tint_button_visibility(is_raw)

    def _update_tint_button_visibility(self, is_raw: bool) -> None:
        """Fade Tint out while Raw is active (tint has no effect in raw view)."""
        tint_button = getattr(self, "_tint_button", None)
        if tint_button is None:
            return
        previous = getattr(self, "_tint_button_hidden_for_raw", None)
        if previous == is_raw:
            return
        self._tint_button_hidden_for_raw = is_raw
        tint_button.setEnabled(not is_raw)
        if is_raw:
            fade_out(tint_button, duration=150)
        else:
            fade_in(tint_button, duration=150)

    def _on_raw_option_selected(self) -> None:
        popup = getattr(self, "_background_popup", None)
        if popup is not None:
            popup.hide()
        self._set_raw_view(True)

    def _on_tint_toggle_clicked(self) -> None:
        global ENABLE_TINT
        ENABLE_TINT = not ENABLE_TINT
        if ENABLE_TINT:
            self._tint_slider.setValue(TINT_DEFAULT_STRENGTH)
        self._update_tint_button_style()

    def _update_tint_button_style(self) -> None:
        tint_button = getattr(self, "_tint_button", None)
        if tint_button is None:
            return
        is_raw = getattr(self, "_active_mode", None) == "raw"
        tint_button.setStyleSheet(
            self._mode_buttons_active
            if (ENABLE_TINT and not is_raw)
            else self._mode_buttons_glass
        )
        self._slide_tint_slider(ENABLE_TINT and not is_raw)

    def _build_tint_slider_panel(self, parent: QWidget) -> QWidget:
        panel = QWidget(parent)
        panel.setFixedHeight(38)
        panel.setMaximumWidth(0)
        panel_layout = QHBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(8)

        slider = QSlider(Qt.Orientation.Horizontal, panel)
        slider.setMinimumWidth(TINT_SLIDER_PANEL_WIDTH - 36 - 8)
        slider.setRange(0, 100)
        slider.setValue(TINT_DEFAULT_STRENGTH)
        slider.setToolTip("Tint strength: how much the lenses darken the world")
        slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 4px;
                border-radius: 2px;
                background: rgba(255, 255, 255, 0.15);
            }
            QSlider::sub-page:horizontal {
                border-radius: 2px;
                background: rgba(255, 255, 255, 0.7);
            }
            QSlider::handle:horizontal {
                width: 14px;
                height: 14px;
                margin: -5px 0;
                border-radius: 7px;
                background: white;
            }
        """)
        slider.valueChanged.connect(self._on_tint_strength_changed)

        value_label = QLabel(panel)
        value_label.setFixedWidth(36)
        value_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        value_label.setStyleSheet(
            "color: rgba(255, 255, 255, 0.85); font-size: 13px; font-weight: 500;"
        )
        self._tint_slider = slider
        self._tint_value_label = value_label
        self._on_tint_strength_changed(slider.value())

        panel_layout.addWidget(slider, 1)
        panel_layout.addWidget(value_label)

        self._tint_slider_anim = QPropertyAnimation(panel, b"maximumWidth", self)
        self._tint_slider_anim.setDuration(TINT_SLIDER_ANIM_MS)
        self._tint_slider_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        return panel

    def _slide_tint_slider(self, visible: bool) -> None:
        panel = getattr(self, "_tint_slider_panel", None)
        if panel is None:
            return
        target = TINT_SLIDER_PANEL_WIDTH if visible else 0
        anim = self._tint_slider_anim
        if anim.endValue() == target and (
            anim.state() == QPropertyAnimation.State.Running
            or panel.maximumWidth() == target
        ):
            return
        anim.stop()
        anim.setStartValue(panel.maximumWidth())
        anim.setEndValue(target)
        anim.start()

    def _on_tint_strength_changed(self, strength: int) -> None:
        global _LUT_TINT
        _LUT_TINT = _build_lut_tint(1.0 - strength / 100.0)
        self._tint_value_label.setText(f"{strength}%")

    def change_background(self, preset: str) -> None:
        popup = getattr(self, "_background_popup", None)
        if popup is not None:
            popup.hide()
        if hasattr(self, "_raw_mode") and self._raw_mode:
            self._set_raw_view(False)
        self._active_mode = preset
        self._update_mode_button_styles()
        if self.background_widget is not None:
            self.background_widget.change_background(preset)
        if preset == SimulatorBackgroundPreset.ROOM.value:
            self._fit_window_to_media(default_background_size(self._framework_dir))

    def _show_background_popup(self) -> None:
        self._rebuild_background_popup()
        popup = self._background_popup
        button = self._background_button
        button_top = button.mapToGlobal(QPoint(0, 0))

        def anchor() -> None:
            popup.move(button_top.x(), button_top.y() - popup.height() - 4)

        popup.on_resize = anchor
        popup.layout().activate()
        popup.adjustSize()
        anchor()
        popup.show()

    def _rebuild_background_popup(self) -> None:
        """Rebuild the Background popup: fixed presets, saved uploads (v1, v2, ...), then Upload.

        Every row — presets, uploads, and Upload itself — is built by
        _make_menu_row so the whole popup shares one consistent style, and
        clicks land on plain QPushButtons with no QMenu mouse-grab involved.
        """
        layout = self._background_popup_layout
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        layout.addWidget(
            self._make_menu_row(
                "None (Raw Frames)",
                self._active_mode == "raw",
                self._on_raw_option_selected,
                tooltip=RAW_MODE_TOOLTIP_TEXT,
            )
        )
        layout.addWidget(self._make_menu_separator())

        for preset_enum in SimulatorBackgroundPreset:
            if preset_enum == SimulatorBackgroundPreset.CUSTOM:
                continue
            preset_str = preset_enum.value
            is_active = preset_str == self._active_mode
            layout.addWidget(
                self._make_menu_row(
                    preset_str.capitalize(),
                    is_active,
                    lambda p=preset_str: self.change_background(p),
                )
            )

        uploads = _list_uploaded_backgrounds(self._upload_dir)
        if uploads:
            layout.addWidget(self._make_menu_separator())
            for version, path, is_video in uploads:
                mode_id = f"custom:{version}"
                is_active = mode_id == self._active_mode
                layout.addWidget(
                    self._make_menu_row(
                        f"v{version}",
                        is_active,
                        lambda m=mode_id, p=path, v=is_video: (
                            self._on_select_uploaded_background(m, p, v)
                        ),
                        show_delete=True,
                        on_delete=lambda m=mode_id, p=path: (
                            self._on_delete_uploaded_background(m, p)
                        ),
                    )
                )

        layout.addWidget(self._make_menu_separator())
        layout.addWidget(
            self._make_menu_row("Upload...", False, self._on_upload_background_clicked)
        )

    def _make_menu_separator(self) -> QWidget:
        separator = QWidget(self._background_popup)
        separator.setAttribute(Qt.WA_StyledBackground, True)
        separator.setFixedHeight(1)
        separator.setStyleSheet("background-color: rgba(255, 255, 255, 0.15);")
        # Direct child of the translucent popup — needs its own painted
        # (nonzero-alpha) background or it's a hole through to the desktop.
        wrapper = QWidget(self._background_popup)
        wrapper.setAttribute(Qt.WA_StyledBackground, True)
        wrapper.setStyleSheet("background-color: rgba(255, 255, 255, 0.06);")
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(8, 4, 8, 4)
        wrapper_layout.addWidget(separator)
        return wrapper

    def _make_menu_row(
        self,
        label: str,
        is_active: bool,
        on_select,
        show_delete: bool = False,
        on_delete=None,
        tooltip: str = "",
    ) -> QWidget:
        """One uniformly-styled popup row: optional checkmark + label, optional '-' delete button."""
        row = QWidget(self._background_popup)
        row.setAttribute(Qt.WA_StyledBackground, True)
        row.setObjectName("menuRow")
        row.setStyleSheet("""
            QWidget#menuRow {
                background-color: rgba(255, 255, 255, 0.06);
            }
            QWidget#menuRow:hover {
                background-color: rgba(40, 40, 40, 0.92);
            }
        """)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(16, 6, 12, 6)
        row_layout.setSpacing(8)

        check_label = QLabel("✓" if is_active else "", row)
        check_label.setFixedWidth(14)
        check_label.setStyleSheet(
            "QLabel { color: white; font-weight: 700; background: transparent; }"
        )
        row_layout.addWidget(check_label)

        select_button = QPushButton(label, row)
        select_button.setFlat(True)
        select_button.setCursor(Qt.PointingHandCursor)
        if tooltip:
            select_button.setToolTip(tooltip)
        select_button.setStyleSheet(
            "QPushButton { border: none; background: transparent; text-align: left;"
            + (
                " color: white; font-weight: 700; }"
                if is_active
                else " color: rgba(255, 255, 255, 0.85); font-weight: 500; }"
            )
        )
        # QPushButton.clicked emits a bool; discard it so on_select/on_delete
        # (defined as zero-arg lambdas with bound defaults) run unmodified.
        select_button.clicked.connect(lambda checked=False: on_select())
        row_layout.addWidget(select_button, 1)

        if show_delete:
            delete_button = QPushButton("-", row)
            delete_button.setFlat(True)
            delete_button.setFixedWidth(20)
            delete_button.setCursor(Qt.PointingHandCursor)
            delete_button.setStyleSheet(
                "QPushButton { border: none; background: transparent;"
                " color: rgba(255, 255, 255, 0.5); font-weight: 700; }"
                "QPushButton:hover { color: #FF6B6B; }"
            )
            delete_button.clicked.connect(lambda checked=False: on_delete())
            row_layout.addWidget(delete_button)

        return row

    def _on_select_uploaded_background(
        self, mode_id: str, path: str, is_video: bool
    ) -> None:
        self._background_popup.hide()
        if not os.path.exists(path):
            log.warning(f"Uploaded background missing on disk: {path}")
            return
        if hasattr(self, "_raw_mode") and self._raw_mode:
            self._set_raw_view(False)
        if self.background_widget is not None:
            self.background_widget.set_custom_background(path, is_video)
        self._active_mode = mode_id
        self._update_mode_button_styles()
        self._fit_window_to_media(media_size(path, is_video))

    def _on_delete_uploaded_background(self, mode_id: str, path: str) -> None:
        self._background_popup.hide()
        if self._active_mode == mode_id:
            # Switch away first so any open video capture releases the file
            # before we unlink it (required on Windows; harmless elsewhere).
            self._active_mode = DEFAULT_BACKGROUND_PRESET.value
            if self.background_widget is not None:
                self.background_widget.change_background(self._active_mode)
            self._fit_window_to_media(default_background_size(self._framework_dir))
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError as e:
            log.error(f"Failed to delete uploaded background {path}: {e}")
            return
        self._update_mode_button_styles()

    def _on_upload_background_clicked(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose background image or video",
            "",
            "Media files (*.png *.jpg *.jpeg *.bmp *.webp *.mp4 *.mov *.avi *.mkv *.webm *.m4v)",
        )
        if not file_path:
            self._update_mode_button_styles()
            return
        self._start_background_upload(file_path)

    def _start_background_upload(self, file_path: str) -> None:
        if self.background_widget is None:
            return
        screen_size = self.screen().availableGeometry().size()
        resolution = (
            max(self._device_size[0], screen_size.width()) // 2 * 2,
            max(self._device_size[1], screen_size.height()) // 2 * 2,
        )

        self._upload_progress = QProgressDialog(
            "Compressing background…", None, 0, 0, self
        )
        self._upload_progress.setWindowModality(Qt.WindowModal)
        self._upload_progress.setCancelButton(None)
        self._upload_progress.setMinimumDuration(0)
        self._upload_progress.show()

        self._upload_thread = QThread(self)
        self._upload_worker = _BackgroundUploadWorker(
            file_path, self._upload_dir, resolution
        )
        self._upload_worker.moveToThread(self._upload_thread)
        self._upload_thread.started.connect(self._upload_worker.run)
        self._upload_worker.finished.connect(self._on_background_upload_finished)
        self._upload_thread.start()

    def _on_background_upload_finished(
        self, dest_path: str, version: int, is_video: bool, success: bool
    ) -> None:
        if getattr(self, "_upload_progress", None) is not None:
            self._upload_progress.close()
            self._upload_progress = None
        upload_thread = getattr(self, "_upload_thread", None)
        if upload_thread is not None:
            upload_thread.quit()
            upload_thread.wait(3000)
            self._upload_thread = None
        self._upload_worker = None

        if not success:
            log.error(f"Background upload failed for: {dest_path}")
            self._update_mode_button_styles()
            return

        if hasattr(self, "_raw_mode") and self._raw_mode:
            self._set_raw_view(False)
        if self.background_widget is not None:
            self.background_widget.set_custom_background(dest_path, is_video)
        self._active_mode = f"custom:{version}"
        self._update_mode_button_styles()
        self._fit_window_to_media(media_size(dest_path, is_video))

    def closeEvent(self, event) -> None:
        if hasattr(self, "_composite_timer") and self._composite_timer.isActive():
            self._composite_timer.stop()
        if hasattr(self, "_raw_update_timer") and self._raw_update_timer.isActive():
            self._raw_update_timer.stop()
        if self.background_widget is not None:
            self.background_widget.stop()
        if hasattr(self, "_blend_queue") and hasattr(self, "_blend_thread"):
            try:
                self._blend_queue.put(None, timeout=2)
            except queue.Full:
                pass
            if self._blend_thread.isRunning():
                self._blend_thread.quit()
                self._blend_thread.wait(5000)
        upload_thread = getattr(self, "_upload_thread", None)
        if upload_thread is not None and upload_thread.isRunning():
            upload_thread.quit()
            upload_thread.wait(5000)
        if self._recorder is not None and self._record_thread is not None:
            path = self._recorder.path
            self._recorder.finished.disconnect(self._on_recording_finished)
            self._recorder.stop()
            self._record_thread.quit()
            dest_path = os.path.join(last_recordings_dir(), os.path.basename(path))
            if not self._record_thread.wait(10000):
                log.error(f"Simulator recording did not finish: {path}")
            elif os.path.exists(path) and save_recording(path, dest_path):
                log.info(
                    f"Simulator recording saved: {dest_path}", extra={"console": True}
                )
        super().closeEvent(event)
