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
import threading
import time
from enum import Enum
from pathlib import Path
from typing import List, Optional

import numpy as np
from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..helpers.animation_utils import fade_in, fade_out
from ..helpers.logger import get_logger
from ..helpers.utils import qpixmap_to_rgb_bytes
from ..helpers.utils_light import load_config, set_custom_circle_cursor

log = get_logger("RunApp")
_config = load_config()

# Constants from config (used by SimulatorBackgroundWidget)
OVERLAY_FRAME_RATE = _config["fps"]["SIMULATOR_FPS"]
BACKGROUND_VIDEO_FRAME_RATE = _config["fps"]["SIMULATOR_FPS"]
DISPLAY_RESOLUTION = tuple(_config["resolution"]["DISPLAY_RESOLUTION"])
INITIAL_CAMERA_FRAMES_TO_DISCARD = _config["peripherals"][
    "INITIAL_CAMERA_FRAMES_TO_DISCARD"
]
OVERLAY_BACKGROUND_VIDEO_DAY_PATH = _config["simulator"][
    "OVERLAY_BACKGROUND_VIDEO_DAY_PATH"
]
OVERLAY_BACKGROUND_VIDEO_NIGHT_PATH = _config["simulator"][
    "OVERLAY_BACKGROUND_VIDEO_NIGHT_PATH"
]
OVERLAY_BACKGROUND_VIDEO_OUTDOORS_PATH = _config["simulator"][
    "OVERLAY_BACKGROUND_VIDEO_OUTDOORS_PATH"
]
DEFAULT_OVERLAY_BRIGHTNESS = _config["simulator"]["DEFAULT_OVERLAY_BRIGHTNESS"]
APP_WINDOW_RESOLUTION = (DISPLAY_RESOLUTION[0], DISPLAY_RESOLUTION[1])
CLIENT_DEVICE_ADDITIONAL_WINDOW_HEIGHT = 60
RAW_MODE_TOOLTIP_TEXT = _config["simulator"]["RAW_MODE_TOOLTIP_TEXT"]
PRINT_SIMULATOR_PERFORMANCE = _config["simulator"]["PRINT_SIMULATOR_PERFORMANCE"]
SIMULATOR_CALIBRATION_FILENAME = _config["simulator"]["SIMULATOR_CALIBRATION_FILENAME"]

USE_SIMPLE_ADDITIVE_BLEND = False
DEFAULT_SIMULATOR_BACKGROUND_RGB = (40, 40, 40)

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


_LUT_SRGB_TO_LIN, _LUT_LIN_TO_SRGB = _build_srgb_linear_luts()
_LUT_LIN_TO_SRGB_BYTE = _build_lin_to_srgb_byte()
_LUT_SRGB_TO_LIN_BYTE = _build_srgb_to_lin_byte()
_LUT_D_3D = _build_lut_d_3d()
_LUT_D_3D_LINEAR = _build_lut_d_3d_linear()
_LUT_OUT_3D = _build_lut_out_3d()


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

    if CONSIDER_POINT_SPREAD:
        # Step 2 & 3
        si = cv2.filter2D(si, -1, POINT_SPREAD_KERNEL)
        d = _LUT_D_3D_LINEAR[si[:, :, 0], si[:, :, 1], si[:, :, 2]]
    else:
        # Step 3
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


class SimulatorBackgroundPreset(Enum):
    """Enum for simulator background presets."""

    NIGHT = "night"
    DAY = "day"
    OUTDOORS = "outdoors"
    CAMERA = "camera"


class _BackgroundWorker(QObject):
    """Runs in a QThread; reads camera/video/image, writes latest frame to widget, emits for setPixmap."""

    frame_ready = Signal(object, int, int)  # (rgb_bytes, width, height)

    def __init__(self, widget: "SimulatorBackgroundWidget") -> None:
        super().__init__()
        self._widget = widget
        self._stop = False

    def process_loop(self) -> None:
        import cv2

        interval = (
            1.0 / BACKGROUND_VIDEO_FRAME_RATE
            if BACKGROUND_VIDEO_FRAME_RATE > 0
            else 1.0 / 5.0
        )
        while not self._stop:
            try:
                w, h = self._widget.resolution[0], self._widget.resolution[1]
                background = None
                with self._widget._capture_lock:
                    preset = self._widget.current_preset
                    cam = self._widget.camera_capture
                    vid = self._widget.video_capture
                    path = self._widget.background_path

                if (
                    preset == SimulatorBackgroundPreset.CAMERA
                    and cam is not None
                    and cam.isOpened()
                ):
                    ret, background = cam.read()
                    if not ret or background is None:
                        continue
                    cam_height, cam_width = background.shape[:2]
                    target_aspect = w / h
                    cam_aspect = cam_width / cam_height
                    if cam_aspect > target_aspect:
                        new_height = h
                        new_width = int(cam_width * (h / cam_height))
                        background = cv2.resize(
                            background,
                            (new_width, new_height),
                            interpolation=cv2.INTER_LINEAR,
                        )
                        crop_x = (new_width - w) // 2
                        background = background[:, crop_x : crop_x + w]
                    else:
                        new_width = w
                        new_height = int(cam_height * (w / cam_width))
                        background = cv2.resize(
                            background,
                            (new_width, new_height),
                            interpolation=cv2.INTER_LINEAR,
                        )
                        crop_y = (new_height - h) // 2
                        background = background[crop_y : crop_y + h, :]
                elif (
                    preset
                    in [
                        SimulatorBackgroundPreset.DAY,
                        SimulatorBackgroundPreset.NIGHT,
                        SimulatorBackgroundPreset.OUTDOORS,
                    ]
                    and vid is not None
                    and vid.isOpened()
                ):
                    ret, background = vid.read()
                    if not ret or background is None:
                        vid.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        ret, background = vid.read()
                        if not ret or background is None:
                            continue
                    video_height, video_width = background.shape[:2]
                    target_aspect = w / h
                    video_aspect = video_width / video_height
                    if video_aspect > target_aspect:
                        new_height = h
                        new_width = int(video_width * (h / video_height))
                        background = cv2.resize(
                            background,
                            (new_width, new_height),
                            interpolation=cv2.INTER_LINEAR,
                        )
                        crop_x = (new_width - w) // 2
                        background = background[:, crop_x : crop_x + w]
                    else:
                        new_width = w
                        new_height = int(video_height * (w / video_width))
                        background = cv2.resize(
                            background,
                            (new_width, new_height),
                            interpolation=cv2.INTER_LINEAR,
                        )
                        crop_y = (new_height - h) // 2
                        background = background[crop_y : crop_y + h, :]
                elif path is not None and os.path.exists(path):
                    background = cv2.imread(path)
                    if background is not None:
                        background = cv2.resize(
                            background, (w, h), interpolation=cv2.INTER_LINEAR
                        )

                if background is not None:
                    composite_rgb = cv2.cvtColor(background, cv2.COLOR_BGR2RGB)
                    height, width = composite_rgb.shape[:2]
                    with self._widget._frame_lock:
                        self._widget._latest_frame = composite_rgb.copy()
                    self.frame_ready.emit(composite_rgb.tobytes(), width, height)
            except Exception as e:
                log.debug(f"BackgroundWorker: {e}")
            time.sleep(interval)

    def stop(self) -> None:
        self._stop = True


class SimulatorBackgroundWidget(QWidget):
    """
    A widget that displays only the simulator background (video/camera/image).
    Used as the bottom layer in the merged window; the transparent app widget is drawn on top.
    """

    def __init__(
        self,
        framework_dir: str,
        resolution: tuple[int, int] = (DISPLAY_RESOLUTION[0], DISPLAY_RESOLUTION[1]),
    ) -> None:
        super().__init__()
        self.framework_dir = framework_dir
        self.resolution = resolution
        self.current_preset = SimulatorBackgroundPreset.NIGHT
        self.camera_capture = None
        self.video_capture = None
        self.background_path = None

        self.setFixedSize(self.resolution[0], self.resolution[1])
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        self._capture_lock = threading.Lock()
        self._frame_lock = threading.Lock()
        self._latest_frame = None

        self.background_label = QLabel(self)
        self.background_label.setGeometry(0, 0, self.resolution[0], self.resolution[1])
        self.background_label.setAlignment(Qt.AlignCenter)
        self.background_label.setScaledContents(True)

        if OVERLAY_FRAME_RATE <= 0:
            raise ValueError(
                f"OVERLAY_FRAME_RATE must be positive, got {OVERLAY_FRAME_RATE}"
            )

        self._bg_worker = _BackgroundWorker(self)
        self._bg_worker.frame_ready.connect(self._on_background_frame)
        self._bg_thread = QThread(self)
        self._bg_worker.moveToThread(self._bg_thread)
        self._bg_thread.started.connect(self._bg_worker.process_loop)
        self._bg_thread.start()

        self._update_background_path()
        video_presets = [
            SimulatorBackgroundPreset.DAY,
            SimulatorBackgroundPreset.NIGHT,
            SimulatorBackgroundPreset.OUTDOORS,
        ]
        if self.current_preset in video_presets:
            with self._capture_lock:
                if not self._open_video():
                    log.warning("Failed to open background simulator video")

        log.info("SimulatorBackgroundWidget initialized successfully.")

    def _on_background_frame(self, rgb_bytes: object, w: int, h: int) -> None:
        """Main-thread slot: set background label pixmap from worker."""
        try:
            q_img = QImage(
                rgb_bytes,
                w,
                h,
                3 * w,
                QImage.Format.Format_RGB888,
            )
            self.background_label.setPixmap(QPixmap.fromImage(q_img.copy()))
        except Exception as e:
            log.debug(f"Background frame apply: {e}")

    def get_latest_background(self):
        """Return a copy of the latest background frame (RGB numpy) or None. Thread-safe."""
        import numpy as np

        with self._frame_lock:
            if self._latest_frame is not None:
                return self._latest_frame.copy()
        return None

    def _update_background_path(self) -> None:
        if self.current_preset == SimulatorBackgroundPreset.CAMERA:
            self.background_path = None
        elif self.current_preset == SimulatorBackgroundPreset.DAY:
            self.background_path = os.path.join(
                self.framework_dir,
                OVERLAY_BACKGROUND_VIDEO_DAY_PATH,
            )
        elif self.current_preset == SimulatorBackgroundPreset.NIGHT:
            self.background_path = os.path.join(
                self.framework_dir,
                OVERLAY_BACKGROUND_VIDEO_NIGHT_PATH,
            )
        elif self.current_preset == SimulatorBackgroundPreset.OUTDOORS:
            self.background_path = os.path.join(
                self.framework_dir,
                OVERLAY_BACKGROUND_VIDEO_OUTDOORS_PATH,
            )
        else:
            self.background_path = os.path.join(
                self.framework_dir,
                "overlay_backgrounds",
                f"{self.current_preset.value}.png",
            )

    def _open_camera(self) -> bool:
        if self.camera_capture is not None:
            return True
        try:
            import cv2

            self.camera_capture = cv2.VideoCapture(0)
            if not self.camera_capture.isOpened():
                log.error("Could not open camera")
                self.camera_capture = None
                return False
            for _ in range(INITIAL_CAMERA_FRAMES_TO_DISCARD):
                self.camera_capture.read()
            log.info("Camera opened successfully")
            return True
        except Exception as e:
            log.error(f"Error opening camera: {e}", exc_info=True)
            self.camera_capture = None
            return False

    def _close_camera(self) -> None:
        if self.camera_capture is not None:
            try:
                self.camera_capture.release()
                self.camera_capture = None
                log.info("Camera closed")
            except Exception as e:
                log.error(f"Error closing camera: {e}", exc_info=True)

    def _open_video(self) -> bool:
        if self.video_capture is not None:
            return True
        try:
            import cv2

            if self.background_path is None or not os.path.exists(self.background_path):
                log.error(f"Video file not found: {self.background_path}")
                return False
            self.video_capture = cv2.VideoCapture(self.background_path)
            if not self.video_capture.isOpened():
                log.error(f"Could not open video: {self.background_path}")
                self.video_capture = None
                return False
            log.info(f"Video opened successfully: {self.background_path}")
            return True
        except Exception as e:
            log.error(f"Error opening video: {e}", exc_info=True)
            self.video_capture = None
            return False

    def _close_video(self) -> None:
        if self.video_capture is not None:
            try:
                self.video_capture.release()
                self.video_capture = None
                log.info("Video closed")
            except Exception as e:
                log.error(f"Error closing video: {e}", exc_info=True)

    def change_background(self, preset: str) -> None:
        try:
            preset_enum = SimulatorBackgroundPreset(preset.lower())
        except ValueError:
            log.warning(f"Invalid background preset: {preset}")
            return

        video_presets = [
            SimulatorBackgroundPreset.DAY,
            SimulatorBackgroundPreset.NIGHT,
            SimulatorBackgroundPreset.OUTDOORS,
        ]

        with self._capture_lock:
            if (
                self.current_preset == SimulatorBackgroundPreset.CAMERA
                and preset_enum != SimulatorBackgroundPreset.CAMERA
            ):
                self._close_camera()

            if (
                self.current_preset in video_presets
                and preset_enum not in video_presets
            ):
                self._close_video()

            if (
                self.current_preset in video_presets
                and preset_enum in video_presets
                and self.current_preset != preset_enum
            ):
                self._close_video()

            if (
                preset_enum == SimulatorBackgroundPreset.CAMERA
                and self.current_preset != SimulatorBackgroundPreset.CAMERA
            ):
                if not self._open_camera():
                    log.error("Failed to open camera, keeping current preset")
                    return

            if preset_enum in video_presets and (
                self.current_preset not in video_presets
                or self.current_preset != preset_enum
            ):
                self.current_preset = preset_enum
                self._update_background_path()
                if not self._open_video():
                    log.error("Failed to open video, keeping current preset")
                    return
            else:
                self.current_preset = preset_enum
                self._update_background_path()

        log.info(f"Background changed to: {preset}")

    def stop(self) -> None:
        """Stop background worker and release camera/video. Call when window is closed or no longer needed."""
        if hasattr(self, "_bg_worker") and self._bg_worker is not None:
            self._bg_worker.stop()
        if hasattr(self, "_bg_thread") and self._bg_thread.isRunning():
            self._bg_thread.quit()
            self._bg_thread.wait(3000)
        with self._capture_lock:
            self._close_camera()
            self._close_video()


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
                    background-color: rgba(255, 255, 255, 0.12);
                    color: rgba(255, 255, 255, 0.95);
                    border: 1px solid rgba(255, 255, 255, 0.25);
                    border-radius: 12px;
                    font-size: 13px;
                    font-weight: 600;
                    padding: 6px 14px;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.18);
                    border: 1px solid rgba(255, 255, 255, 0.35);
                }
                QPushButton:pressed {
                    background-color: rgba(255, 255, 255, 0.22);
                    border: 1px solid rgba(255, 255, 255, 0.4);
                }
            """
            self._mode_buttons_active = """
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.28);
                    color: white;
                    border: 1px solid rgba(255, 255, 255, 0.6);
                    border-radius: 12px;
                    font-size: 13px;
                    font-weight: 600;
                    padding: 6px 14px;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.32);
                    border: 1px solid rgba(255, 255, 255, 0.7);
                }
                QPushButton:pressed {
                    background-color: rgba(255, 255, 255, 0.35);
                    border: 1px solid rgba(255, 255, 255, 0.8);
                }
            """

            self._active_mode = "night"
            self._mode_buttons = []

            button_layout.addStretch()
            raw_button = QPushButton("Raw", button_container)
            raw_button.setFixedSize(92, 42)
            raw_button.setProperty("mode_id", "raw")
            raw_button.clicked.connect(self._on_raw_button_clicked)
            self._mode_buttons.append(("raw", raw_button))
            button_layout.addWidget(raw_button)

            self._raw_tooltip = self._make_raw_tooltip()
            self._raw_tooltip_button = raw_button
            raw_button.installEventFilter(self)

            self.background_buttons = []
            for preset_enum in SimulatorBackgroundPreset:
                preset_str = preset_enum.value
                button = QPushButton(preset_str.capitalize(), button_container)
                button.setFixedSize(92, 42)
                button.setProperty("mode_id", preset_str)
                button.clicked.connect(
                    lambda checked, p=preset_str: self.change_background(p)
                )
                self.background_buttons.append(button)
                self._mode_buttons.append((preset_str, button))
                button_layout.addWidget(button)

            button_layout.addStretch()
            button_container.setFixedHeight(58)
            layout.addWidget(button_container)

            self._update_mode_button_styles()

            self.setCentralWidget(container)
            set_custom_circle_cursor(self._app_widget)

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
            interval = int(1000 / OVERLAY_FRAME_RATE) if OVERLAY_FRAME_RATE > 0 else 33
            self._composite_timer.start(interval)
            QTimer.singleShot(0, self._update_composite)
            self._composite_label.update()
            QApplication.processEvents()

    def _toggle_raw_view(self) -> None:
        self._set_raw_view(not self._raw_mode)

    def _make_raw_tooltip(self) -> QFrame:
        tip = QFrame(self)
        tip.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        tip.setAttribute(Qt.WA_TranslucentBackground, True)
        tip.setStyleSheet(
            """
            QFrame {
                background-color: rgba(30, 30, 30, 0.85);
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: 12px;
            }
        """
        )
        tip_label = QLabel(tip)
        tip_label.setWordWrap(True)
        tip_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tip_label.setText(RAW_MODE_TOOLTIP_TEXT)
        tip_label.setStyleSheet(
            """
            QLabel {
                color: rgba(255, 255, 255, 0.92);
                font-size: 14px;
                line-height: 1.35;
                padding: 18px 12px;
            }
        """
        )
        tip_label.setMinimumWidth(260)
        tip_label.setMaximumWidth(320)
        tip_layout = QVBoxLayout(tip)
        tip_layout.setContentsMargins(0, 0, 0, 0)
        tip_layout.addWidget(tip_label)
        tip.adjustSize()
        tip.hide()
        return tip

    def eventFilter(self, obj, event) -> bool:
        if obj is getattr(self, "_raw_tooltip_button", None):
            if event.type() == QEvent.Type.Enter:
                tip = getattr(self, "_raw_tooltip", None)
                if tip is not None:
                    tip.adjustSize()
                    btn = self._raw_tooltip_button
                    global_pos = btn.mapToGlobal(QPoint(0, 0))
                    x = global_pos.x() + (btn.width() - tip.width()) // 2
                    y = global_pos.y() - tip.height() - 0.1
                    tip.move(x, y)
                    tip.show()
                    tip.raise_()
            elif event.type() == QEvent.Type.Leave:
                tip = getattr(self, "_raw_tooltip", None)
                if tip is not None:
                    tip.hide()
        return super().eventFilter(obj, event)

    def _update_mode_button_styles(self) -> None:
        if not hasattr(self, "_mode_buttons"):
            return
        for mode_id, btn in self._mode_buttons:
            style = (
                self._mode_buttons_active
                if mode_id == self._active_mode
                else self._mode_buttons_glass
            )
            btn.setStyleSheet(style)
            btn.setAutoFillBackground(False)
            btn.setFlat(False)

    def _on_raw_button_clicked(self) -> None:
        self._active_mode = "raw"
        self._update_mode_button_styles()
        self._toggle_raw_view()

    def change_background(self, preset: str) -> None:
        if hasattr(self, "_raw_mode") and self._raw_mode:
            self._set_raw_view(False)
        self._active_mode = preset
        self._update_mode_button_styles()
        if self.background_widget is not None:
            self.background_widget.change_background(preset)

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
        super().closeEvent(event)
