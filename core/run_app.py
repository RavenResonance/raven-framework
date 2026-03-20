# ================================================================
# Raven Framework
#
# Copyright (c) 2026 Raven Resonance, Inc.
# All Rights Reserved.
#
# This file is part of the Raven Framework and is proprietary
# to Raven Resonance, Inc. Unauthorized copying, modification,
# or distribution is prohibited without prior written permission.
#
# ================================================================

"""
Application runner for Raven Framework.

This module provides the main entry point for running Raven applications,
with support for deployment and remote upload functionality.
"""

import atexit
import glob
import os
import py_compile
import queue
import shutil
import signal
import sys
import threading
import time
import traceback
import zipfile
from typing import Callable, List, Optional

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
    QVBoxLayout,
    QWidget,
)

from ..helpers.font_utils import preload_fonts
from ..helpers.logger import get_logger
from ..helpers.routine import Routine
from ..helpers.utils_light import is_raven_device, load_config, set_custom_circle_cursor

log = get_logger("RunApp")
_config = load_config()

# Extract constants from config
BASE_API_URL = _config["deployment"]["BASE_API_URL"]
ACCEPTING_DEPLOYMENTS = _config["deployment"].get("ACCEPTING_DEPLOYMENTS", True)
OVERLAY_FRAME_RATE = _config["fps"]["SIMULATOR_FPS"]
BACKGROUND_VIDEO_FRAME_RATE = _config["fps"]["SIMULATOR_FPS"]
DISPLAY_RESOLUTION = tuple(_config["resolution"]["DISPLAY_RESOLUTION"])
APP_RESOLUTION = tuple(_config["resolution"]["APP_RESOLUTION"])
APP_WINDOW_RESOLUTION = (DISPLAY_RESOLUTION[0], DISPLAY_RESOLUTION[1])
OVERLAY_RESOLUTION = (DISPLAY_RESOLUTION[0] + 80, DISPLAY_RESOLUTION[1] + 20)
SIMULATOR_WINDOW_POSITION = (DISPLAY_RESOLUTION[0], 0)
DEFAULT_OVERLAY_BRIGHTNESS = _config["simulator"]["DEFAULT_OVERLAY_BRIGHTNESS"]
INITIAL_CAMERA_FRAMES_TO_DISCARD = _config["peripherals"][
    "INITIAL_CAMERA_FRAMES_TO_DISCARD"
]
SNAPSHOT_TMP_DIR = _config["simulator"]["SNAPSHOT_TMP_DIR"]
SNAPSHOT_FILENAME = _config["simulator"]["SNAPSHOT_FILENAME"]
PYTHON_VERSION_ON_RAVEN_DEVICE = _config["deployment"]["PYTHON_VERSION_ON_RAVEN_DEVICE"]
OVERLAY_BACKGROUND_VIDEO_DAY_PATH = _config["simulator"][
    "OVERLAY_BACKGROUND_VIDEO_DAY_PATH"
]
OVERLAY_BACKGROUND_VIDEO_NIGHT_PATH = _config["simulator"][
    "OVERLAY_BACKGROUND_VIDEO_NIGHT_PATH"
]
OVERLAY_BACKGROUND_VIDEO_OUTDOORS_PATH = _config["simulator"][
    "OVERLAY_BACKGROUND_VIDEO_OUTDOORS_PATH"
]
RAW_MODE_TOOLTIP_TEXT = _config["simulator"]["RAW_MODE_TOOLTIP_TEXT"]

RIGHT_WINDOW_OFFSET = 0
CLIENT_DEVICE_ADDITIONAL_WINDOW_HEIGHT = 60  # To show button for simulator

_IS_RAVEN_DEVICE = is_raven_device()

USE_SIMPLE_ADDITIVE_BLEND = False
PRINT_SIMULATOR_PERFORMANCE = False


def _cleanup_snapshot_tmp(snapshot_path: str, tmp_dir: str) -> None:
    """Remove the snapshot file, any in-progress .tmp file, and tmp dir if empty."""
    try:
        if os.path.exists(snapshot_path):
            os.remove(snapshot_path)
            log.info(f"Cleaned up snapshot file: {snapshot_path}")
        tmp_file = snapshot_path + ".tmp"
        if os.path.exists(tmp_file):
            try:
                os.remove(tmp_file)
                log.info(f"Cleaned up snapshot temp file: {tmp_file}")
            except OSError as e:
                log.warning(f"Failed to remove snapshot temp file {tmp_file}: {e}")
        if os.path.exists(tmp_dir):
            try:
                if not os.listdir(tmp_dir):
                    os.rmdir(tmp_dir)
                    log.info(f"Removed empty tmp directory: {tmp_dir}")
            except OSError:
                pass
    except Exception as e:
        log.warning(f"Failed to cleanup snapshot file: {e}")


def _save_snapshot_in_background(
    image: QImage,
    path: str,
    thread_active_ref: List[bool],
) -> None:
    """Save image to disk in background (for simulator overlay only)."""
    try:
        image = image.copy()
        temp_path = path + ".tmp"
        image.save(temp_path, "PNG")
        os.replace(temp_path, path)
    except Exception as e:
        log.error(f"Failed to save widget snapshot: {e}")
        temp_path = path + ".tmp"
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
    finally:
        thread_active_ref[0] = False


def _handle_deploy(args: List[str], app_id: str, app_key: str) -> None:
    """
    If deploy or deploy-pyc was requested, run build+upload and return.
    Caller should return after calling this when deploy was requested.
    """
    if len(args) == 0 or args[0] not in ("deploy", "deploy-pyc"):
        return
    if is_raven_device():
        log.info("Deploy not available on device.")
        return
    if not ACCEPTING_DEPLOYMENTS:
        error_msg = "Not accepting deployments right now, contact Raven Resonance team to get access"
        log.warning(error_msg)
        print(f"{error_msg}", file=sys.stdout)
        return
    if app_id == "":
        error_msg = "Please add app_id to function call"
        log.error(error_msg)
        print(f"ERROR: {error_msg}", file=sys.stderr)
        return
    if app_key == "":
        error_msg = "Please add app_key to function call"
        log.error(error_msg)
        print(f"ERROR: {error_msg}", file=sys.stderr)
        return
    compile_pyc = args[0] == "deploy-pyc"
    log.info(f"Deployment mode: {'compiled (.pyc)' if compile_pyc else 'source (.py)'}")
    build_path = RunApp.deploy_app(compile_pyc=compile_pyc)
    if not build_path:
        error_msg = "Failed to create build package, cannot upload"
        log.error(error_msg)
        print(f"ERROR: {error_msg}", file=sys.stderr)
        return
    log.info(f"Build path: {build_path}")
    print(f"Build path: {build_path}", file=sys.stdout)
    data = {"app_id": app_id, "app_key": app_key}
    developer_end_point = f"{BASE_API_URL}/rest/api/developer/run/app/"
    print("Uploading package...", file=sys.stdout)
    import requests

    with open(build_path, "rb") as build_file:
        files = {"rav_build": build_file}
        response = requests.post(url=developer_end_point, data=data, files=files)
    upload_msg = f"Upload response status: {response.status_code}"
    log.info(upload_msg)
    if response.status_code == 200:
        print(f"{upload_msg} - Upload successful!", file=sys.stdout)
    else:
        print(f"{upload_msg} - Upload failed!", file=sys.stderr)


def _qt_exception_handler(exc_type, exc_value, exc_traceback) -> None:
    """Handle unhandled exceptions in Qt event loop."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    print("\n" + "=" * 80, file=sys.stderr)
    print("ERROR: Unhandled exception in your application!", file=sys.stderr)
    print("=" * 80, file=sys.stderr)
    print(error_msg, file=sys.stderr)
    print("=" * 80 + "\n", file=sys.stderr)
    log.error(f"Unhandled exception in application: {exc_value}", exc_info=True)
    sys.exit(1)


def _make_snapshot_signal_handler(snapshot_path: str, tmp_dir: str):
    """Return a signal handler that cleans up snapshot and exits."""

    def handler(signum, frame):
        _cleanup_snapshot_tmp(snapshot_path, tmp_dir)
        sys.exit(0)

    return handler


def _capture_widget_snapshot(
    app_widget: QWidget,
    snapshot_path: str,
    thread_active_ref: List[bool],
) -> None:
    """Grab widget on main thread, then save to disk in background (simulator overlay only)."""
    try:
        if thread_active_ref[0]:
            return
        pixmap = app_widget.grab()
        image = pixmap.toImage()
        thread_active_ref[0] = True
        threading.Thread(
            target=_save_snapshot_in_background,
            args=(image, snapshot_path, thread_active_ref),
            daemon=True,
        ).start()
    except Exception as e:
        log.error(f"Failed to capture widget snapshot: {e}")
        thread_active_ref[0] = False


class _BlendWorker(QObject):
    """Runs in a QThread; reads (app_bytes, w, h, seq, brightness) from queue, gets bg from get_bg(), blends, emits result."""

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
                    bg_rgb = np.full((h, w, 3), (40, 40, 40), dtype=np.uint8)
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
                log.debug(f"BlendWorker: {e}")


# Simulator lives in raven_simulator; import only when not on device
if not _IS_RAVEN_DEVICE:
    from .raven_simulator import (
        SimulatorBackgroundPreset,
        SimulatorBackgroundWidget,
        blend_frame,
    )
else:
    SimulatorBackgroundWidget = None
    SimulatorBackgroundPreset = None


class RunApp(QMainWindow):
    """
    A simple QMainWindow wrapper to host an app widget with optional background colors.

    Args:
        app_widget (QWidget): The widget to host inside the main window.
    """

    def __init__(self, app_widget: QWidget) -> None:
        """
        Initialize the RunApp window with the specified app widget.

        Args:
            app_widget (QWidget): The widget to host inside the main window. Must not be None.

        Raises:
            ValueError: If app_widget is None.
        """
        if app_widget is None:
            error_msg = "app_widget cannot be None"
            log.error(error_msg, extra={"console": True})
            raise ValueError(error_msg)

        super().__init__()
        self.background_widget = None
        try:
            self.setWindowTitle("Raven App (alpha v0.1)")
            total_window_width = APP_WINDOW_RESOLUTION[0]
            total_window_height = APP_WINDOW_RESOLUTION[1]
            total_window_height += (
                CLIENT_DEVICE_ADDITIONAL_WINDOW_HEIGHT if not is_raven_device() else 0
            )
            self.setFixedSize(int(total_window_width), int(total_window_height))
            container = QWidget(self)
            container.setStyleSheet("background-color: #1E1E1E;")
            layout = QVBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            if not _IS_RAVEN_DEVICE:
                # Merged window: additive blend of background + app (waveguide-style)
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
                # Keep background widget shown so its timer updates the label; composite covers it

                app_widget.set_env_background_color("black")
                app_widget.set_app_background_color("black")
                self._app_widget = app_widget
                app_widget.setParent(content_area)
                app_widget.setGeometry(0, 0, content_w, content_h)
                # Invisible but receives events and repaints (for grab); clicks pass through composite to here
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
                interval = (
                    int(1000 / OVERLAY_FRAME_RATE) if OVERLAY_FRAME_RATE > 0 else 33
                )
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
                self._blend_worker = _BlendWorker(self._blend_queue, get_bg_fn)
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
            else:
                self.background_buttons = []
                app_widget.set_env_background_color("black")
                app_widget.set_app_background_color("black")
                app_widget.move(0, 0)
                layout.addWidget(app_widget, 1)

            self.setCentralWidget(container)
            if not _IS_RAVEN_DEVICE:
                set_custom_circle_cursor(self._app_widget)
            else:
                set_custom_circle_cursor(app_widget)

            log.info("RunApp initialized successfully.")
        except Exception as e:
            log.error(f"Failed to initialize RunApp: {e}", exc_info=True)
            raise

    def _app_grab_to_bytes(self, app_pix: QPixmap):
        """Copy app pixmap to RGB bytes. Uses shared utils.qimage_to_rgb_bytes (no PNG)."""
        if app_pix.isNull():
            print("[RunApp] _app_grab_to_bytes: app_pix.isNull()", flush=True)
            log.error("_app_grab_to_bytes: app_pix is null", extra={"console": True})
            return None
        img = app_pix.toImage()
        if img.width() <= 0 or img.height() <= 0:
            print(
                f"[RunApp] _app_grab_to_bytes: invalid size w={img.width()} h={img.height()}",
                flush=True,
            )
            log.error(
                f"_app_grab_to_bytes: invalid size w={img.width()} h={img.height()}",
                extra={"console": True},
            )
            return None
        from ..helpers.utils import qimage_to_rgb_bytes

        result = qimage_to_rgb_bytes(img)
        if result is None:
            log.error(
                "_app_grab_to_bytes: qimage_to_rgb_bytes failed",
                extra={"console": True},
            )
            return None
        return result

    def _update_composite(self) -> None:
        """Request a composite update: defer grab to next event loop tick to avoid QPainter re-entry when switching background."""
        if self.background_widget is None or not hasattr(self, "_composite_label"):
            return
        if getattr(self, "_raw_mode", False):
            return
        if getattr(self, "_composite_grab_pending", False):
            return
        self._composite_grab_pending = True
        QTimer.singleShot(0, self._deferred_composite_grab)

    def _deferred_composite_grab(self) -> None:
        """Run in next event loop tick: grab app UI and enqueue for blend. Avoids painting while device is busy (e.g. after background switch)."""
        self._composite_grab_pending = False
        if self.background_widget is None or not hasattr(self, "_composite_label"):
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
        """Main-thread slot: apply blended image only if it matches latest sent (discard stale)."""
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
        """Print total time and expected fps/ms per frame every 3s (simulator mode only)."""
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
        """Grab app widget and show it on the composite label (raw mode only; no blend)."""
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
        """Show only the app UI (raw) or the blended overlay (simulator)."""
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
        """Toggle between raw app UI and blended simulator overlay."""
        self._set_raw_view(not self._raw_mode)

    def _make_raw_tooltip(self) -> QFrame:
        """Styled tooltip for Raw button: appears above, bigger, glass-style."""
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
        """Show Raw tooltip above button on hover; hide on leave."""
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
        """Apply glass style; highlight the button matching _active_mode."""
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
        """Raw button: set active mode and toggle raw view."""
        self._active_mode = "raw"
        self._update_mode_button_styles()
        self._toggle_raw_view()

    def change_background(self, preset: str) -> None:
        """Change the background preset of the embedded simulator background."""
        if hasattr(self, "_raw_mode") and self._raw_mode:
            self._set_raw_view(False)
        self._active_mode = preset
        self._update_mode_button_styles()
        if self.background_widget is not None:
            self.background_widget.change_background(preset)

    def closeEvent(self, event) -> None:
        """Stop timers and worker threads gracefully before closing the window."""
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

    @staticmethod
    def run(
        app_widget_fn: Callable[[], QWidget],
        app_id: str = "",
        app_key: str = "",
        use_async_loop: bool = False,
        show_overlayed_window: bool = True,
        should_preload_fonts: bool = False,
    ) -> None:
        """
        Run a QApplication with the RunApp window hosting the created app widget.

        If the first command-line argument is "deploy", this will build and upload
        the application package instead of running it.

        Args:
            app_widget_fn (Callable[[], QWidget]): Callable returning the widget instance
                (called after QApplication is created).
            app_id (str): App ID for the application. Required for deployment. Defaults to "".
            app_key (str): App key for the application. Required for deployment. Defaults to "".
            use_async_loop (bool): If True, sets up an async event loop using qasync.QEventLoop
                to support async/await operations. Defaults to False.
            show_overlayed_window (bool): If True, captures the widget every second and saves
                it to assets/widget_snapshot.png. Defaults to True.
            should_preload_fonts (bool): If True, preloads fonts after QApplication is created.
                Defaults to False.
        """

        args = sys.argv[1:]
        log.info(f"Command-line args: {args}")

        if len(args) > 0 and args[0] in ("deploy", "deploy-pyc"):
            _handle_deploy(args, app_id, app_key)
            return

        try:
            if app_widget_fn is None:
                error_msg = "app_widget_fn cannot be None"
                log.error(error_msg, extra={"console": True})
                raise ValueError(error_msg)
            if not callable(app_widget_fn):
                error_msg = f"app_widget_fn must be callable, got {type(app_widget_fn).__name__}"
                log.error(error_msg, extra={"console": True})
                raise ValueError(error_msg)

            app = QApplication(sys.argv)
            sys.excepthook = _qt_exception_handler

            if should_preload_fonts:
                preload_fonts()

            app_widget = app_widget_fn()
            if app_widget is None:
                error_msg = "App widget function returned None"
                print(f"ERROR: {error_msg}", file=sys.stderr)
                log.error(error_msg, extra={"console": True})
                raise ValueError(error_msg)

            window = RunApp(app_widget)
            if is_raven_device():
                window.setWindowFlags(Qt.FramelessWindowHint)
            window.show()
            window.move(0, 0)
            log.info("Application started.")

            if not is_raven_device() and show_overlayed_window:
                snapshot_filename = f"{app_id}_{SNAPSHOT_FILENAME}"
                assets_dir = os.path.join(os.path.dirname(__file__), "..", "assets")
                os.makedirs(assets_dir, exist_ok=True)
                tmp_dir = os.path.join(assets_dir, SNAPSHOT_TMP_DIR)
                os.makedirs(tmp_dir, exist_ok=True)
                snapshot_path = os.path.join(tmp_dir, snapshot_filename)
                _cleanup_snapshot_tmp(snapshot_path, tmp_dir)

                from functools import partial

                atexit.register(partial(_cleanup_snapshot_tmp, snapshot_path, tmp_dir))
                signal.signal(
                    signal.SIGTERM,
                    _make_snapshot_signal_handler(snapshot_path, tmp_dir),
                )
                signal.signal(
                    signal.SIGINT,
                    _make_snapshot_signal_handler(snapshot_path, tmp_dir),
                )

                snapshot_thread_active_ref: List[bool] = [False]
                overlay_fps = OVERLAY_FRAME_RATE if OVERLAY_FRAME_RATE > 0 else 15
                timer_interval = int(1000 / overlay_fps)
                snapshot_timer = QTimer()
                snapshot_timer.timeout.connect(
                    partial(
                        _capture_widget_snapshot,
                        app_widget,
                        snapshot_path,
                        snapshot_thread_active_ref,
                    )
                )
                snapshot_timer.start(timer_interval)
                _capture_widget_snapshot(
                    app_widget,
                    snapshot_path,
                    snapshot_thread_active_ref,
                )

                log.info(f"Widget snapshot capture enabled (every {timer_interval}ms)")
                log.info(
                    "Merged window: display background with transparent app on top (use preset buttons to change background)"
                )

            if use_async_loop:
                import asyncio

                from qasync import QEventLoop

                loop = QEventLoop(app)
                asyncio.set_event_loop(loop)
                log.info("Using async event loop")
                with loop:
                    loop.run_forever()
            else:
                log.info("About to start app.exec()")
                ret = app.exec()
                log.info(f"Qt event loop exited with code: {ret}")
                sys.exit(ret)
        except KeyboardInterrupt:
            log.info("Application interrupted by user")
            print("\nApplication interrupted by user (Ctrl+C)", file=sys.stderr)
            sys.exit(0)
        except Exception as e:
            error_msg = f"Application run failed: {e}"
            print("\n" + "=" * 80, file=sys.stderr)
            print("ERROR: Application failed to run!", file=sys.stderr)
            print("=" * 80, file=sys.stderr)
            print(f"Exception: {type(e).__name__}: {e}", file=sys.stderr)
            print("\nFull traceback:", file=sys.stderr)
            traceback.print_exc()
            print("=" * 80 + "\n", file=sys.stderr)
            log.error(error_msg, exc_info=True)
            sys.exit(1)

    if not _IS_RAVEN_DEVICE:

        @staticmethod
        def _load_ravignore(app_path: str) -> List[str]:
            ravignore_path = os.path.join(app_path, ".ravignore")
            if not os.path.exists(ravignore_path):
                return []
            patterns = []
            with open(ravignore_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        patterns.append(line)
            if patterns:
                log.info(f"Loaded {len(patterns)} patterns from .ravignore")
            return patterns

        @staticmethod
        def _should_ignore_path(rel_path: str, ignore_patterns: List[str]) -> bool:
            if not ignore_patterns:
                return False
            rel_path = rel_path.replace("\\", "/")
            if rel_path.startswith("./"):
                rel_path = rel_path[2:]
            for pattern in ignore_patterns:
                pattern = pattern.replace("\\", "/")
                if pattern.startswith("./"):
                    pattern = pattern[2:]
                pattern_clean = pattern.rstrip("/")
                rel_path_clean = rel_path.rstrip("/")
                if rel_path_clean == pattern_clean or rel_path_clean.startswith(
                    pattern_clean + "/"
                ):
                    return True
            return False

        @staticmethod
        def _filter_walk_iteration(
            root: str, dirs: List[str], app_path: str, ignore_patterns: List[str]
        ) -> bool:
            rel_root = os.path.relpath(root, app_path)
            if rel_root == ".":
                rel_root = ""
            filtered_dirs = []
            for d in dirs:
                if d == "__pycache__":
                    continue
                dir_rel_path = (
                    os.path.join(rel_root, d).replace("\\", "/") if rel_root else d
                )
                if not RunApp._should_ignore_path(dir_rel_path, ignore_patterns):
                    filtered_dirs.append(d)
            dirs[:] = filtered_dirs
            return rel_root and RunApp._should_ignore_path(rel_root, ignore_patterns)

        @staticmethod
        def compile_app(app_path: str, output_dir: str) -> bool:
            log.info(f"Compiling app at: {app_path}")
            os.makedirs(output_dir, exist_ok=True)
            ignore_patterns = RunApp._load_ravignore(app_path)
            python_files = []
            for root, dirs, files in os.walk(app_path):
                if RunApp._filter_walk_iteration(root, dirs, app_path, ignore_patterns):
                    continue
                for file in files:
                    if file.endswith(".py"):
                        file_path = os.path.join(root, file)
                        rel_path = os.path.relpath(file_path, app_path)
                        if not RunApp._should_ignore_path(rel_path, ignore_patterns):
                            python_files.append(file_path)
            log.info(f"Found {len(python_files)} Python files to compile")
            for py_file in python_files:
                try:
                    rel_path = os.path.relpath(py_file, app_path)
                    output_file = os.path.join(output_dir, rel_path + "c")
                    os.makedirs(os.path.dirname(output_file), exist_ok=True)
                    py_compile.compile(py_file, output_file, doraise=True)
                    log.debug(f"Compiled: {rel_path} -> {rel_path}c")
                except py_compile.PyCompileError as e:
                    log.error(f"Failed to compile {py_file}: {e}")
                    return False
            log.info("Successfully compiled files")
            return True

        @staticmethod
        def copy_python_source(app_path: str, output_dir: str) -> bool:
            log.info(f"Copying Python source files from: {app_path}")
            os.makedirs(output_dir, exist_ok=True)
            ignore_patterns = RunApp._load_ravignore(app_path)
            python_files = []
            for root, dirs, files in os.walk(app_path):
                if RunApp._filter_walk_iteration(root, dirs, app_path, ignore_patterns):
                    continue
                for file in files:
                    if file.endswith(".py"):
                        file_path = os.path.join(root, file)
                        rel_path = os.path.relpath(file_path, app_path)
                        if not RunApp._should_ignore_path(rel_path, ignore_patterns):
                            python_files.append(file_path)
            log.info(f"Found {len(python_files)} Python files to copy")
            for py_file in python_files:
                try:
                    rel_path = os.path.relpath(py_file, app_path)
                    output_file = os.path.join(output_dir, rel_path)
                    os.makedirs(os.path.dirname(output_file), exist_ok=True)
                    shutil.copy2(py_file, output_file)
                    log.debug(f"Copied: {rel_path}")
                except Exception as e:
                    log.error(f"Failed to copy {py_file}: {e}")
                    return False
            log.info("Successfully copied Python source files")
            return True

        @staticmethod
        def copy_assets(app_path: str, output_dir: str) -> bool:
            log.info("Copying assets...")
            ignore_patterns = RunApp._load_ravignore(app_path)
            asset_extensions = [
                ".png",
                ".jpg",
                ".jpeg",
                ".gif",
                ".svg",
                ".wav",
                ".mp3",
                ".mp4",
                ".json",
                ".txt",
                ".md",
                ".sh",
            ]
            assets_copied = 0
            for root, dirs, files in os.walk(app_path):
                if RunApp._filter_walk_iteration(root, dirs, app_path, ignore_patterns):
                    continue
                for file in files:
                    if any(file.endswith(ext) for ext in asset_extensions):
                        src_path = os.path.join(root, file)
                        rel_path = os.path.relpath(src_path, app_path)
                        if RunApp._should_ignore_path(rel_path, ignore_patterns):
                            continue
                        dst_path = os.path.join(output_dir, rel_path)
                        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                        shutil.copy2(src_path, dst_path)
                        assets_copied += 1
                        log.debug(f"Copied asset: {rel_path}")
            log.info(f"Copied {assets_copied} assets")
            return True

        @staticmethod
        def create_rav_package(
            app_path: str, output_path: str, compile_pyc: bool = True
        ) -> bool:
            log.info(
                f"Creating .rav package: {output_path} (compile_pyc={compile_pyc})"
            )
            temp_dir = f"/tmp/raven_deploy_{int(time.time())}"
            os.makedirs(temp_dir, exist_ok=True)
            try:
                if compile_pyc:
                    if not RunApp.compile_app(app_path, temp_dir):
                        return False
                else:
                    if not RunApp.copy_python_source(app_path, temp_dir):
                        return False
                if not RunApp.copy_assets(app_path, temp_dir):
                    return False
                requirements_path = os.path.join(app_path, "requirements.txt")
                if os.path.exists(requirements_path):
                    shutil.copy2(requirements_path, temp_dir)
                    log.info("Copied requirements.txt")
                build_run_sh_path = os.path.join(temp_dir, "run.sh")
                if not os.path.exists(build_run_sh_path):
                    default_run_sh_path = os.path.join(
                        os.path.dirname(__file__), "run.sh"
                    )
                    if os.path.exists(default_run_sh_path):
                        shutil.copy2(default_run_sh_path, build_run_sh_path)
                        log.info("Added default run.sh")
                    else:
                        log.warning(
                            f"Default run.sh not found at {default_run_sh_path}; skipping"
                        )
                package_stats = {
                    "python_files": 0,
                    "assets": {
                        "images": 0,
                        "audio": 0,
                        "video": 0,
                        "data": 0,
                        "other": 0,
                    },
                    "requirements": False,
                    "directories": set(),
                    "total_files": 0,
                    "file_list": [],
                }
                with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                    for root, dirs, files in os.walk(temp_dir):
                        if "raven_framework" in root:
                            log.info("Found raven_framework in source, ignoring")
                            continue
                        for file in files:
                            file_path = os.path.join(root, file)
                            arc_path = os.path.relpath(file_path, temp_dir)
                            zipf.write(file_path, arc_path)
                            log.debug(f"Added to package: {arc_path}")
                            package_stats["file_list"].append(arc_path)
                            package_stats["total_files"] += 1
                            dir_name = os.path.dirname(arc_path)
                            if dir_name:
                                package_stats["directories"].add(dir_name)
                            if file.endswith((".pyc", ".py")):
                                package_stats["python_files"] += 1
                            elif file.endswith(
                                (".png", ".jpg", ".jpeg", ".gif", ".svg")
                            ):
                                package_stats["assets"]["images"] += 1
                            elif file.endswith((".wav", ".mp3")):
                                package_stats["assets"]["audio"] += 1
                            elif file.endswith(".mp4"):
                                package_stats["assets"]["video"] += 1
                            elif file.endswith((".json", ".txt", ".md")):
                                if file == "requirements.txt":
                                    package_stats["requirements"] = True
                                else:
                                    package_stats["assets"]["data"] += 1
                            else:
                                package_stats["assets"]["other"] += 1
                package_size = os.path.getsize(output_path)
                size_mb = package_size / (1024 * 1024)
                details = [
                    f"Package: {os.path.basename(output_path)}",
                    f"Size: {size_mb:.2f} MB",
                    f"Total files: {package_stats['total_files']}",
                    f"Python files: {package_stats['python_files']}",
                ]
                asset_counts = [
                    f"{k}: {v}" for k, v in package_stats["assets"].items() if v > 0
                ]
                if asset_counts:
                    details.append(f"Assets ({', '.join(asset_counts)})")
                if package_stats["requirements"]:
                    details.append("Includes requirements.txt")
                if package_stats["directories"]:
                    dir_list = sorted(package_stats["directories"])
                    if len(dir_list) <= 5:
                        details.append(f"Directories: {', '.join(dir_list)}")
                    else:
                        details.append(
                            f"Directories: {len(dir_list)} total ({', '.join(dir_list[:3])}...)"
                        )
                package_summary = (
                    f"Successfully created .rav package: {' | '.join(details)}"
                )
                log.info(package_summary)
                print(f"\n{package_summary}", file=sys.stdout)
                if package_stats["file_list"]:
                    print("\nFiles in package:", file=sys.stdout)
                    for file_path in sorted(package_stats["file_list"]):
                        print(f"  - {file_path}", file=sys.stdout)
                print()
                return True
            finally:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
                    log.info("Cleaned up temporary files")

        @staticmethod
        def deploy_app(
            app_name: str = "dev", compile_pyc: bool = True
        ) -> Optional[str]:
            version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            if version != PYTHON_VERSION_ON_RAVEN_DEVICE:
                error_msg = f"FATAL ERROR: Make sure python version is {PYTHON_VERSION_ON_RAVEN_DEVICE}"
                log.error(error_msg)
                print(f"ERROR: {error_msg}", file=sys.stderr)
                print(f"Current Python version: {version}", file=sys.stderr)
            if compile_pyc:
                log.info(
                    f"Deploying app with Python version: {version} and compiling to .pyc"
                )
                print(f"Using Python version: {version}", file=sys.stdout)
            old_files = glob.glob(os.path.join(".", "*.rav"))
            for f in old_files:
                filename = os.path.basename(f)
                try:
                    os.remove(f)
                    log.info(f"Deleted old file: {filename}")
                except Exception as e:
                    log.warning(f"Could not delete old file {filename}: {e}")
            if not os.path.exists("main.py"):
                log.error("main.py not found in current directory")
                log.error("Please run this script from the same directory as main.py")
                return None
            timestamp = int(time.time())
            output_path = f"{app_name}_{version}_{timestamp}.rav"
            if RunApp.create_rav_package(".", output_path, compile_pyc=compile_pyc):
                log.info(f"Package created: {os.path.abspath(output_path)}")
                log.info("=" * 50)
                log.info("DEPLOYMENT SUCCESSFUL!")
                return output_path
            else:
                log.error(f"Failed to create package for Python {version}")
                return None
