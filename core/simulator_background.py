# ================================================================
# Raven Framework
#
# Copyright (c) 2026 Raven Resonance, Inc.
# All Rights Reserved.
#
# ================================================================

"""
Background source management for the simulator (non-device only).
Presets, camera/video/image capture, and user-uploaded background compression.
"""

import os
import re
import threading
import time
from enum import Enum

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

from ..helpers.logger import get_logger
from ..helpers.utils_light import load_config

log = get_logger("RunApp")
_config = load_config()

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


class SimulatorBackgroundPreset(Enum):
    """Enum for simulator background presets."""

    NIGHT = "night"
    DAY = "day"
    OUTDOORS = "outdoors"
    CAMERA = "camera"
    CUSTOM = "custom"


_VIDEO_PRESETS = (
    SimulatorBackgroundPreset.DAY,
    SimulatorBackgroundPreset.NIGHT,
    SimulatorBackgroundPreset.OUTDOORS,
)

_UPLOAD_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
_UPLOAD_MAX_FPS = 15.0
_UPLOAD_JPEG_QUALITY = 80
_UPLOAD_VERSION_RE = re.compile(r"^v(\d+)\.(mp4|jpg)$")


def _list_uploaded_backgrounds(upload_dir: str) -> list[tuple[int, str, bool]]:
    """Return (version, path, is_video) for every uploaded background, sorted oldest-first."""
    if not os.path.isdir(upload_dir):
        return []
    versions = []
    for name in os.listdir(upload_dir):
        match = _UPLOAD_VERSION_RE.match(name)
        if not match:
            continue
        versions.append(
            (int(match.group(1)), os.path.join(upload_dir, name), match.group(2) == "mp4")
        )
    versions.sort(key=lambda item: item[0])
    return versions


def _next_upload_version(upload_dir: str) -> int:
    existing = _list_uploaded_backgrounds(upload_dir)
    return existing[-1][0] + 1 if existing else 1


def _resize_cover(frame, target_w: int, target_h: int):
    """Resize+center-crop frame to exactly (target_w, target_h), preserving aspect ratio."""
    import cv2

    src_h, src_w = frame.shape[:2]
    target_aspect = target_w / target_h
    src_aspect = src_w / src_h
    if src_aspect > target_aspect:
        new_h = target_h
        new_w = int(src_w * (target_h / src_h))
        resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        crop_x = (new_w - target_w) // 2
        return resized[:, crop_x : crop_x + target_w]
    new_w = target_w
    new_h = int(src_h * (target_w / src_w))
    resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    crop_y = (new_h - target_h) // 2
    return resized[crop_y : crop_y + target_h, :]


def _compress_background_video(
    src_path: str, dest_path: str, resolution: tuple[int, int]
) -> bool:
    """Re-encode src_path to dest_path: strip audio, downscale/crop to resolution, cap frame rate.

    cv2.VideoWriter has no audio support, so re-encoding through it drops the audio
    track for free. Returns True on success.
    """
    import cv2

    cap = cv2.VideoCapture(src_path)
    if not cap.isOpened():
        return False
    try:
        src_fps = cap.get(cv2.CAP_PROP_FPS)
        out_fps = min(src_fps, _UPLOAD_MAX_FPS) if src_fps > 0 else _UPLOAD_MAX_FPS
        frame_stride = max(1, round(src_fps / out_fps)) if src_fps > 0 else 1
        writer = cv2.VideoWriter(
            dest_path, cv2.VideoWriter_fourcc(*"mp4v"), out_fps, resolution
        )
        if not writer.isOpened():
            return False
        try:
            frame_index = 0
            wrote_any = False
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                if frame_index % frame_stride == 0:
                    writer.write(_resize_cover(frame, resolution[0], resolution[1]))
                    wrote_any = True
                frame_index += 1
            return wrote_any
        finally:
            writer.release()
    finally:
        cap.release()


def _compress_background_image(
    src_path: str, dest_path: str, resolution: tuple[int, int]
) -> bool:
    """Downscale/crop src_path to resolution and re-save as a compressed JPEG."""
    import cv2

    image = cv2.imread(src_path)
    if image is None:
        return False
    resized = _resize_cover(image, resolution[0], resolution[1])
    return bool(
        cv2.imwrite(dest_path, resized, [cv2.IMWRITE_JPEG_QUALITY, _UPLOAD_JPEG_QUALITY])
    )


class _BackgroundUploadWorker(QObject):
    """Runs in a QThread; compresses an uploaded image/video into a simulator-ready background."""

    finished = Signal(str, int, bool, bool)  # (dest_path, version, is_video, success)

    def __init__(self, src_path: str, dest_dir: str, resolution: tuple[int, int]) -> None:
        super().__init__()
        self._src_path = src_path
        self._dest_dir = dest_dir
        self._resolution = resolution

    def run(self) -> None:
        ext = os.path.splitext(self._src_path)[1].lower()
        is_video = ext in _UPLOAD_VIDEO_EXTENSIONS
        success = False
        version = 1
        dest_path = ""
        try:
            os.makedirs(self._dest_dir, exist_ok=True)
            version = _next_upload_version(self._dest_dir)
            dest_path = os.path.join(
                self._dest_dir, f"v{version}.{'mp4' if is_video else 'jpg'}"
            )
            if is_video:
                success = _compress_background_video(
                    self._src_path, dest_path, self._resolution
                )
            else:
                success = _compress_background_image(
                    self._src_path, dest_path, self._resolution
                )
        except Exception as e:
            log.error(f"Background upload compression failed: {e}", exc_info=True)
            success = False
        self.finished.emit(dest_path, version, is_video, success)


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
                    custom_is_video = self._widget.custom_is_video

                is_video_preset = preset in _VIDEO_PRESETS or (
                    preset == SimulatorBackgroundPreset.CUSTOM and custom_is_video
                )

                if (
                    preset == SimulatorBackgroundPreset.CAMERA
                    and cam is not None
                    and cam.isOpened()
                ):
                    ret, background = cam.read()
                    if not ret or background is None:
                        continue
                    background = _resize_cover(background, w, h)
                elif is_video_preset and vid is not None and vid.isOpened():
                    ret, background = vid.read()
                    if not ret or background is None:
                        vid.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        ret, background = vid.read()
                        if not ret or background is None:
                            continue
                    background = _resize_cover(background, w, h)
                elif path is not None and os.path.exists(path):
                    background = cv2.imread(path)
                    if background is not None:
                        background = _resize_cover(background, w, h)

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
        self.custom_is_video = False

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
        if self.current_preset in _VIDEO_PRESETS:
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
        elif self.current_preset == SimulatorBackgroundPreset.CUSTOM:
            pass
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

        with self._capture_lock:
            current_is_video = self.current_preset in _VIDEO_PRESETS or (
                self.current_preset == SimulatorBackgroundPreset.CUSTOM
                and self.custom_is_video
            )
            switching_video_source = current_is_video and (
                preset_enum not in _VIDEO_PRESETS or preset_enum != self.current_preset
            )

            if (
                self.current_preset == SimulatorBackgroundPreset.CAMERA
                and preset_enum != SimulatorBackgroundPreset.CAMERA
            ):
                self._close_camera()

            if switching_video_source:
                self._close_video()

            if (
                preset_enum == SimulatorBackgroundPreset.CAMERA
                and self.current_preset != SimulatorBackgroundPreset.CAMERA
            ):
                if not self._open_camera():
                    log.error("Failed to open camera, keeping current preset")
                    return

            self.custom_is_video = False
            self.current_preset = preset_enum
            self._update_background_path()
            if preset_enum in _VIDEO_PRESETS and not self._open_video():
                log.error("Failed to open video, keeping current preset")
                return

        log.info(f"Background changed to: {preset}")

    def set_custom_background(self, path: str, is_video: bool) -> None:
        """Switch to a user-uploaded custom background (already compressed by the caller)."""
        with self._capture_lock:
            current_is_video = self.current_preset in _VIDEO_PRESETS or (
                self.current_preset == SimulatorBackgroundPreset.CUSTOM
                and self.custom_is_video
            )
            if self.current_preset == SimulatorBackgroundPreset.CAMERA:
                self._close_camera()
            if current_is_video:
                self._close_video()

            self.current_preset = SimulatorBackgroundPreset.CUSTOM
            self.background_path = path
            self.custom_is_video = is_video
            if is_video and not self._open_video():
                log.error(f"Failed to open uploaded video: {path}")
                return

        log.info(f"Custom background set: {path} (video={is_video})")

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
