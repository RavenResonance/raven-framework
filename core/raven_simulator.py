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
from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QEnterEvent,
    QImage,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPixmap,
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
    QVBoxLayout,
    QWidget,
)

from ..helpers.animation_utils import fade_in, fade_out
from ..helpers.logger import get_logger
from ..helpers.utils import qpixmap_to_rgb_bytes
from ..helpers.utils_light import load_config, set_custom_circle_cursor
from .waveguide_halo import apply_waveguide_halo
from .simulator_background import (
    SimulatorBackgroundPreset,
    SimulatorBackgroundWidget,
    _BackgroundUploadWorker,
    _list_uploaded_backgrounds,
)

# Feature flags
USE_SIMPLE_ADDITIVE_BLEND = False
ENABLE_TINT = False
ENABLE_UI_SHRINK = True
ENABLE_SIMULATE_BACKLIGHT = True

log = get_logger("RunApp")
_config = load_config()


OVERLAY_FRAME_RATE = _config["fps"]["SIMULATOR_FPS"]
DISPLAY_RESOLUTION = tuple(_config["resolution"]["DISPLAY_RESOLUTION"])
DEFAULT_OVERLAY_BRIGHTNESS = _config["simulator"]["DEFAULT_OVERLAY_BRIGHTNESS"]
APP_WINDOW_RESOLUTION = (DISPLAY_RESOLUTION[0], DISPLAY_RESOLUTION[1])
CLIENT_DEVICE_ADDITIONAL_WINDOW_HEIGHT = 60
RAW_MODE_TOOLTIP_TEXT = _config["simulator"]["RAW_MODE_TOOLTIP_TEXT"]
PRINT_SIMULATOR_PERFORMANCE = _config["simulator"]["PRINT_SIMULATOR_PERFORMANCE"]
SIMULATOR_CALIBRATION_FILENAME = _config["simulator"]["SIMULATOR_CALIBRATION_FILENAME"]
FIXED_BACKGROUND_TINT_FACTOR = _config["simulator"]["FIXED_BACKGROUND_TINT_FACTOR"]
UI_SHRINK_WIDTH = _config["simulator"]["UI_SHRINK_WIDTH"]
UI_SHRINK_HEIGHT = _config["simulator"]["UI_SHRINK_HEIGHT"]
UI_SHRINK_OFFSET_X = _config["simulator"]["UI_SHRINK_OFFSET_X"]
UI_SHRINK_OFFSET_Y = _config["simulator"]["UI_SHRINK_OFFSET_Y"]

DEFAULT_SIMULATOR_BACKGROUND_RGB = (40, 40, 40)
BACKLIGHT_COLOR_RGB = (7, 7, 15)
_BACKLIGHT_COLOR_BGR = BACKLIGHT_COLOR_RGB[::-1]
_BACKLIGHT_LAYER_BGR = np.full(
    (UI_SHRINK_HEIGHT, UI_SHRINK_WIDTH, 3), _BACKLIGHT_COLOR_BGR, dtype=np.uint8
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
CONSIDER_POINT_SPREAD = False
CONSIDER_WAVEGUIDE_HALO = _config["simulator"]["CONSIDER_WAVEGUIDE_HALO"]
HALO_RADIUS = _config["simulator"]["HALO_RADIUS"]
HALO_STRENGTH = _config["simulator"]["HALO_STRENGTH"]


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
    #    Step 3 (math step 3): Demand d from _LUT_D_3D_LINEAR(lin_hud) if PSF, else _LUT_D_3D(sRGB snapshot).
    #    Step 4 (math steps 4 and 5): Blended output via _LUT_OUT_3D(bg_lin_byte, hud_lin_byte, d) per channel;
    #    each entry = out_lin = bg_lin*(1-d)+hud_lin then linear→sRGB byte.
    # -------------------------------------------------------------------------
    import cv2

    # Step 1
    bi = cv2.LUT(bg_bgr, _LUT_SRGB_TO_LIN_BYTE)
    si = cv2.LUT(snapshot_bgr, _LUT_SRGB_TO_LIN_BYTE)

    # Raven's current calibrated PSF remains untouched and disabled by default.
    # The optional halo below is a separate perceptual approximation: sharp HUD
    # core + broad low-energy light leak, applied in linear-light byte space.
    use_linear_demand = False
    if CONSIDER_POINT_SPREAD:
        si = cv2.filter2D(si, -1, POINT_SPREAD_KERNEL)
        use_linear_demand = True

    if CONSIDER_WAVEGUIDE_HALO:
        si = apply_waveguide_halo(si, HALO_RADIUS, HALO_STRENGTH)
        use_linear_demand = True

    if use_linear_demand:
        d = _LUT_D_3D_LINEAR[si[:, :, 0], si[:, :, 1], si[:, :, 2]]
    else:
        d = _LUT_D_3D[
            snapshot_bgr[:, :, 0],
            snapshot_bgr[:, :, 1],
            snapshot_bgr[:, :, 2],
        ]

    # Step 4
    blended = np.empty_like(bg_bgr)
    for i in range(3):
        blended[:, :, i] = _LUT_OUT_3D[bi[:, :, i], si[:, :, i], d]
    return blended


class SimulatorBlendWorker(QObject):
    """Runs in a QThread; blends app RGBA grab with background via ``blend_frame``."""

    result_ready = Signal(object, int, int, int)  # (rgb_bytes, width, height, sequence)

    def __init__(self, blend_queue: queue.Queue, get_bg_fn) -> None:
        super().__init__()
        self._queue = blend_queue
        self._get_bg = get_bg_fn

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
                app_bytes, w, h, seq, brightness = item
                snapshot_rgb = np.frombuffer(app_bytes, dtype=np.uint8).reshape(
                    (h, w, 3)
                )
                bg_rgb = self._get_bg()
                if bg_rgb is None:
                    log.warning(
                        "SimulatorBlendWorker: No background passed to blend worker, using default background"
                    )
                    bg_rgb = np.full(
                        (h, w, 3), DEFAULT_SIMULATOR_BACKGROUND_RGB, dtype=np.uint8
                    )
                if ENABLE_TINT:
                    bg_bgr = _LUT_TINT[bg_rgb[..., ::-1]]
                else:
                    bg_bgr = cv2.cvtColor(bg_rgb, cv2.COLOR_RGB2BGR)
                snapshot_bgr = cv2.cvtColor(snapshot_rgb, cv2.COLOR_RGB2BGR)
                if snapshot_bgr.shape[:2] != bg_bgr.shape[:2]:
                    snapshot_bgr = cv2.resize(
                        snapshot_bgr,
                        (bg_bgr.shape[1], bg_bgr.shape[0]),
                        interpolation=cv2.INTER_LINEAR,
                    )
                if brightness != 1.0:
                    snapshot_bgr = cv2.convertScaleAbs(
                        snapshot_bgr, alpha=brightness, beta=0
                    )
                if ENABLE_UI_SHRINK:
                    snapshot_bgr = _shrink_and_letterbox(
                        snapshot_bgr,
                        UI_SHRINK_WIDTH,
                        UI_SHRINK_HEIGHT,
                        UI_SHRINK_OFFSET_X,
                        UI_SHRINK_OFFSET_Y,
                    )
                    if ENABLE_SIMULATE_BACKLIGHT:
                        _apply_backlight_in_place(
                            snapshot_bgr,
                            UI_SHRINK_OFFSET_X,
                            UI_SHRINK_OFFSET_Y,
                            UI_SHRINK_WIDTH,
                            UI_SHRINK_HEIGHT,
                        )
                if USE_SIMPLE_ADDITIVE_BLEND:
                    blended = cv2.add(bg_bgr, snapshot_bgr)
                else:
                    blended = blend_frame(bg_bgr, snapshot_bgr)
                blended_rgb = np.ascontiguousarray(
                    cv2.cvtColor(blended, cv2.COLOR_BGR2RGB)
                )
                out_h, out_w = blended_rgb.shape[:2]
                self.result_ready.emit(blended_rgb.tobytes(), out_w, out_h, seq)
            except Exception as e:
                log.debug(f"SimulatorBlendWorker: {e}")


def _shrink_and_letterbox(
    frame, shrink_w: int, shrink_h: int, offset_x: int, offset_y: int
):
    """Downscale frame to (shrink_w, shrink_h) and place it at (offset_x, offset_y) on a black canvas."""
    import cv2
    import numpy as np

    shrunk = cv2.resize(frame, (shrink_w, shrink_h), interpolation=cv2.INTER_AREA)
    canvas = np.zeros_like(frame)
    canvas[offset_y : offset_y + shrink_h, offset_x : offset_x + shrink_w] = shrunk
    return canvas


def _apply_backlight_in_place(
    frame, offset_x: int, offset_y: int, width: int, height: int
) -> None:
    """Lift pure-black pixels within the given rect to _BACKLIGHT_COLOR_BGR, in place."""
    import cv2

    region = frame[offset_y : offset_y + height, offset_x : offset_x + width]
    black_mask = cv2.inRange(region, (0, 0, 0), (0, 0, 0))
    kept = cv2.bitwise_and(region, region, mask=cv2.bitwise_not(black_mask))
    lit = cv2.bitwise_and(_BACKLIGHT_LAYER_BGR, _BACKLIGHT_LAYER_BGR, mask=black_mask)
    region[:] = cv2.bitwise_or(kept, lit)


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
            self.setWindowTitle("Raven App (alpha v0.1)")
            total_window_width = APP_WINDOW_RESOLUTION[0]
            total_window_height = (
                APP_WINDOW_RESOLUTION[1] + CLIENT_DEVICE_ADDITIONAL_WINDOW_HEIGHT
            )
            self.setFixedSize(int(total_window_width), int(total_window_height))
            container = QWidget(self)
            container.setStyleSheet("background-color: #1E1E1E;")
            layout = QVBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            content_w = APP_WINDOW_RESOLUTION[0]
            content_h = APP_WINDOW_RESOLUTION[1]
            content_area = QWidget(container)
            content_area.setFixedSize(content_w, content_h)
            content_area.setAutoFillBackground(False)

            framework_dir = os.path.dirname(os.path.dirname(__file__))
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
            opacity = QGraphicsOpacityEffect(app_widget)
            opacity.setOpacity(0.0)
            app_widget.setGraphicsEffect(opacity)

            self._composite_label = QLabel(content_area)
            self._composite_label.setGeometry(0, 0, content_w, content_h)
            self._composite_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._composite_label.setScaledContents(True)
            self._composite_label.setAttribute(Qt.WA_TransparentForMouseEvents)
            self._composite_label.raise_()

            self._gaze_overlay = _GazeRemapOverlay(app_widget, content_area)
            self._gaze_overlay.setGeometry(0, 0, content_w, content_h)
            self._gaze_overlay.set_transform(
                UI_SHRINK_WIDTH / content_w,
                UI_SHRINK_HEIGHT / content_h,
                QPoint(UI_SHRINK_OFFSET_X, UI_SHRINK_OFFSET_Y),
            )
            self._gaze_overlay.set_active(ENABLE_UI_SHRINK)
            self._gaze_overlay.raise_()

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
                self.background_widget.get_latest_background()
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

            button_container = QWidget(container)
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
                    background-color: rgba(40, 40, 40, 0.92);
                }
                QPushButton::menu-indicator {
                    image: none;
                    width: 0px;
                }
            """
            self._mode_buttons_active = """
                QPushButton {
                    background-color: rgba(48, 48, 48, 0.94);
                    color: white;
                    border: none;
                    border-radius: 8px;
                    font-size: 13px;
                    font-weight: 700;
                    padding: 6px 14px;
                }
                QPushButton:hover {
                    background-color: rgba(62, 62, 62, 0.94);
                }
                QPushButton::menu-indicator {
                    image: none;
                    width: 0px;
                }
            """
            self._active_mode = "night"

            tint_button = QPushButton("Tint", button_container)
            tint_button.setFixedSize(70, 38)
            tint_button.setStyleSheet(self._mode_buttons_glass)
            tint_button.clicked.connect(self._on_tint_toggle_clicked)
            self._tint_button = tint_button
            self._tint_button_hidden_for_raw = False
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

            button_layout.addStretch()
            button_layout.addWidget(tint_button)
            button_layout.addWidget(background_button)
            button_container.setFixedHeight(58)
            layout.addWidget(button_container)

            self._update_mode_button_styles()

            self.setCentralWidget(container)
            set_custom_circle_cursor(self._app_widget)
            set_custom_circle_cursor(self._gaze_overlay)

            log.info("SimulatorRunApp initialized successfully.")
        except Exception as e:
            log.error(f"Failed to initialize SimulatorRunApp: {e}", exc_info=True)
            raise

    def _app_grab_to_bytes(self, app_pix: QPixmap):
        if app_pix.isNull():
            print("[SimulatorRunApp] _app_grab_to_bytes: app_pix.isNull()", flush=True)
            log.error("_app_grab_to_bytes: app_pix is null", extra={"console": True})
            return None
        result = qpixmap_to_rgb_bytes(app_pix)
        if result is None:
            img = app_pix.toImage()
            print(
                f"[SimulatorRunApp] _app_grab_to_bytes: invalid size w={img.width()} h={img.height()}",
                flush=True,
            )
            log.error(
                f"_app_grab_to_bytes: invalid size w={img.width()} h={img.height()}",
                extra={"console": True},
            )
            return None
        return result

    def start_hidden(self) -> None:
        """Make the visible surface transparent until revealed (handoff)."""
        surface = (
            self._app_widget
            if getattr(self, "_raw_mode", False)
            else getattr(self, "_composite_label", None)
        )
        if surface is not None:
            effect = QGraphicsOpacityEffect(surface)
            effect.setOpacity(0.0)
            surface.setGraphicsEffect(effect)

    def reveal(self, duration_ms: int) -> None:
        """Fade the visible surface in (handoff cross-fade with the launcher)."""
        if getattr(self, "_raw_mode", False):
            fade_in(self._app_widget, duration=duration_ms)
        elif hasattr(self, "_composite_label"):
            fade_in(self._composite_label, duration=duration_ms)

    def conceal(self, duration_ms: int) -> None:
        """Fade the visible surface out (mirror of reveal, for app exit)."""
        if getattr(self, "_raw_mode", False):
            fade_out(self._app_widget, duration=duration_ms)
        elif hasattr(self, "_composite_label"):
            fade_out(self._composite_label, duration=duration_ms)

    def sleep_app_ui(self, duration_ms: int, curve: str) -> None:
        """Fade the visible simulator UI out (composite label or raw app widget)."""
        self._app_ui_asleep = True
        if getattr(self, "_raw_mode", False):
            if hasattr(self, "_raw_update_timer"):
                self._raw_update_timer.stop()
            fade_out(self._app_widget, duration=duration_ms, curve=curve)
        else:
            if hasattr(self, "_composite_timer"):
                self._composite_timer.stop()
            self._composite_label.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents, False
            )
            fade_out(self._composite_label, duration=duration_ms, curve=curve)

    def wake_app_ui(self, duration_ms: int, curve: str) -> None:
        """Fade the visible simulator UI back in."""
        self._app_ui_asleep = False
        interval = int(1000 / OVERLAY_FRAME_RATE) if OVERLAY_FRAME_RATE > 0 else 33
        if getattr(self, "_raw_mode", False):
            fade_in(self._app_widget, duration=duration_ms, curve=curve)
            if hasattr(self, "_raw_update_timer"):
                self._raw_update_timer.start(interval)
                QTimer.singleShot(0, self._update_raw_composite)
        else:
            fade_in(self._composite_label, duration=duration_ms, curve=curve)
            self._composite_label.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
            )
            if hasattr(self, "_composite_timer"):
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
        self._app_widget.setGraphicsEffect(None)
        try:
            app_pix = self._app_widget.grab()
        finally:
            opacity = QGraphicsOpacityEffect(self._app_widget)
            opacity.setOpacity(0.0)
            self._app_widget.setGraphicsEffect(opacity)
        result = self._app_grab_to_bytes(app_pix)
        if result is None:
            log.debug("_deferred_composite_grab: _app_grab_to_bytes returned None")
            return
        app_bytes, w, h = result
        try:
            seq = self._blend_sequence
            self._blend_sequence += 1
            self._last_put_time = time.perf_counter()
            self._blend_queue.put_nowait(
                (app_bytes, w, h, seq, DEFAULT_OVERLAY_BRIGHTNESS)
            )
            self._blend_last_sent = seq
        except queue.Full:
            pass

    def _on_blend_result(self, rgb_bytes: bytes, w: int, h: int, seq: int) -> None:
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
            q_img = QImage(
                rgb_bytes,
                w,
                h,
                3 * w,
                QImage.Format.Format_RGB888,
            )
            self._composite_label.setPixmap(QPixmap.fromImage(q_img.copy()))
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
        self._app_widget.setGraphicsEffect(None)
        try:
            app_pix = self._app_widget.grab()
        finally:
            opacity = QGraphicsOpacityEffect(self._app_widget)
            opacity.setOpacity(1.0)
            self._app_widget.setGraphicsEffect(opacity)
        if not app_pix.isNull():
            self._composite_label.setPixmap(app_pix)

    def _set_raw_view(self, raw: bool) -> None:
        if not hasattr(self, "_raw_mode"):
            return
        self._raw_mode = raw
        content_area = self._app_widget.parent()
        if raw:
            self._active_mode = "raw"
            self._update_mode_button_styles()
            self._composite_timer.stop()
            self._composite_label.setPixmap(QPixmap())
            self._composite_label.clear()
            self.background_widget.stackUnder(self._app_widget)
            self._composite_label.stackUnder(self._app_widget)
            raw_opacity = QGraphicsOpacityEffect(self._app_widget)
            raw_opacity.setOpacity(1.0)
            self._app_widget.setGraphicsEffect(raw_opacity)
            if content_area is not None:
                content_area.setAutoFillBackground(True)
                content_area.setStyleSheet("background-color: #282936;")
            self._app_widget.raise_()
            self._composite_label.raise_()
            gaze_overlay = getattr(self, "_gaze_overlay", None)
            if gaze_overlay is not None:
                gaze_overlay.set_active(False)
            self._app_widget.show()
            interval = int(1000 / OVERLAY_FRAME_RATE) if OVERLAY_FRAME_RATE > 0 else 33
            self._raw_update_timer.start(interval)
            QTimer.singleShot(0, self._update_raw_composite)
            QApplication.processEvents()
        else:
            self._raw_update_timer.stop()
            self._active_mode = (
                self.background_widget.current_preset.value
                if self.background_widget is not None
                else "night"
            )
            self._update_mode_button_styles()
            if content_area is not None:
                content_area.setAutoFillBackground(False)
                content_area.setStyleSheet("")
            opacity = QGraphicsOpacityEffect(self._app_widget)
            opacity.setOpacity(0.0)
            self._app_widget.setGraphicsEffect(opacity)
            self.background_widget.show()
            self._composite_label.show()
            self._composite_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self._composite_label.setPixmap(QPixmap())
            self.background_widget.stackUnder(self._app_widget)
            self._app_widget.stackUnder(self._composite_label)
            self._composite_label.raise_()
            gaze_overlay = getattr(self, "_gaze_overlay", None)
            if gaze_overlay is not None:
                gaze_overlay.set_active(ENABLE_UI_SHRINK)
                gaze_overlay.raise_()
            interval = int(1000 / OVERLAY_FRAME_RATE) if OVERLAY_FRAME_RATE > 0 else 33
            self._composite_timer.start(interval)
            QTimer.singleShot(0, self._update_composite)
            self._composite_label.update()
            QApplication.processEvents()

    def _update_mode_button_styles(self) -> None:
        is_raw = self._active_mode == "raw"
        background_button = getattr(self, "_background_button", None)
        if background_button is not None:
            background_button.setStyleSheet(
                self._mode_buttons_glass if is_raw else self._mode_buttons_active
            )
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

    def _on_delete_uploaded_background(self, mode_id: str, path: str) -> None:
        self._background_popup.hide()
        if self._active_mode == mode_id:
            # Switch away first so any open video capture releases the file
            # before we unlink it (required on Windows; harmless elsewhere).
            self._active_mode = SimulatorBackgroundPreset.NIGHT.value
            if self.background_widget is not None:
                self.background_widget.change_background(self._active_mode)
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
        resolution = self.background_widget.resolution

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
        super().closeEvent(event)
