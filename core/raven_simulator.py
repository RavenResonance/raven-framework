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
import threading
import time
from enum import Enum
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

from ..helpers.logger import get_logger
from ..helpers.utils_light import load_config

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
SIMULATOR_CALIBRATION_FILENAME = _config["simulator"]["SIMULATOR_CALIBRATION_FILENAME"]


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
