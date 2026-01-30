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

import asyncio
import atexit
import glob
import json
import os
import py_compile
import shutil
import signal
import sys
import threading
import time
import traceback
import zipfile
from enum import Enum
from pathlib import Path
from typing import Callable, List, Optional

import requests
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent, QImage, QPainterPath, QPixmap, QRegion
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..helpers.font_utils import preload_fonts
from ..helpers.logger import get_logger
from ..helpers.utils_light import is_raven_device, load_config, set_custom_circle_cursor

log = get_logger("RunApp")

# Load configuration
_config = load_config()

# Extract constants from config
BASE_API_URL = _config["deployment"]["BASE_API_URL"]
ACCEPTING_DEPLOYMENTS = _config["deployment"].get("ACCEPTING_DEPLOYMENTS", True)
OVERLAY_FRAME_RATE = _config["fps"]["SIMULATOR_FPS"]
BACKGROUND_VIDEO_FRAME_RATE = _config["fps"]["SIMULATOR_FPS"]
DISPLAY_RESOLUTION = tuple(_config["resolution"]["DISPLAY_RESOLUTION"])
APP_RESOLUTION = tuple(_config["resolution"]["APP_RESOLUTION"])
APP_WINDOW_RESOLUTION = (DISPLAY_RESOLUTION[0], DISPLAY_RESOLUTION[1] + 60)
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
RIGHT_WINDOW_OFFSET = 0


class OverlayBackgroundPreset(Enum):
    """Enum for overlay background presets."""

    NIGHT = "night"
    DAY = "day"
    OUTDOORS = "outdoors"
    CAMERA = "camera"


OVERLAY_BACKGROUND_PRESETS = [preset.value for preset in OverlayBackgroundPreset]


class OverlayWidget(QMainWindow):
    """
    A widget that displays a background image with a snapshot overlaid on top.

    This widget shows a background image as full screen and composites
    assets/widget_snapshot.png centered on top using additive blending with OpenCV.
    Includes buttons at the bottom to switch between background presets.
    """

    def __init__(
        self,
        snapshot_path: str,
        framework_dir: str,
        resolution: tuple[int, int] = OVERLAY_RESOLUTION,
        brightness: float = DEFAULT_OVERLAY_BRIGHTNESS,
    ) -> None:
        """
        Initialize the OverlayWidget.

        Args:
            snapshot_path (str): Path to the snapshot image file to display.
            framework_dir (str): Path to the framework directory containing overlay_backgrounds.
            resolution (tuple[int, int]): Resolution of the overlay window (width, height).
                Defaults to OVERLAY_RESOLUTION.
            brightness (float): Brightness multiplier for the snapshot (0.0 to 2.0+).
                1.0 = normal, <1.0 = dimmer, >1.0 = brighter. Defaults to 1.0.
        """
        super().__init__()
        # Set window title
        self.setWindowTitle("Simulated Preview - Non Interactable (alpha v0.1)")
        self.snapshot_path = snapshot_path
        self.framework_dir = framework_dir
        self.resolution = resolution
        self.brightness = brightness
        self.current_preset = OverlayBackgroundPreset.NIGHT
        self.camera_capture = None  # Used when camera mode is selected in simulator
        self.video_capture = None  # Used when specific video is selected in simulator

        try:
            container = QWidget(self)
            container.setFixedSize(self.resolution[0], self.resolution[1])

            self.composite_label = QLabel(container)
            self.composite_label.setGeometry(
                0, 0, self.resolution[0], self.resolution[1]
            )
            self.composite_label.setAlignment(Qt.AlignCenter)
            self.composite_label.setScaledContents(True)

            self.background_buttons = []
            button_width = 100
            button_height = 45
            button_spacing = 12
            total_buttons_width = (button_width * len(OVERLAY_BACKGROUND_PRESETS)) + (
                button_spacing * (len(OVERLAY_BACKGROUND_PRESETS) - 1)
            )
            start_x = (self.resolution[0] - total_buttons_width) // 2
            bottom_margin = 20
            button_y = self.resolution[1] - button_height - bottom_margin

            button_style = """
                QPushButton {
                    background-color: rgba(30, 30, 30, 200);
                    color: white;
                    border: 2px solid rgba(255, 255, 255, 255);
                    border-radius: 22px;
                    font-size: 14px;
                    font-weight: 600;
                    padding: 8px 16px;
                }
                QPushButton:hover {
                    background-color: rgba(50, 50, 50, 220);
                    border: 2px solid rgba(255, 255, 255, 255);
                }
                QPushButton:pressed {
                    background-color: rgba(70, 70, 70, 240);
                    border: 2px solid rgba(255, 255, 255, 255);
                }
            """

            for i, preset_enum in enumerate(OverlayBackgroundPreset):
                preset_str = preset_enum.value
                button = QPushButton(preset_str.capitalize(), container)
                button_x = start_x + i * (button_width + button_spacing)
                button.setGeometry(button_x, button_y, button_width, button_height)
                button.setStyleSheet(button_style)
                button.clicked.connect(
                    lambda checked, p=preset_str: self.change_background(p)
                )
                button.hide()
                self.background_buttons.append(button)

            self.setCentralWidget(container)

            self.setFixedSize(self.resolution[0], self.resolution[1])

            # self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)

            self.update_timer = QTimer()
            self.update_timer.timeout.connect(self.update_composite)
            if OVERLAY_FRAME_RATE <= 0:
                error_msg = (
                    f"OVERLAY_FRAME_RATE must be positive, got {OVERLAY_FRAME_RATE}"
                )
                log.error(error_msg, extra={"console": True})
                raise ValueError(error_msg)
            timer_interval = int(1000 / BACKGROUND_VIDEO_FRAME_RATE)
            self.update_timer.start(timer_interval)

            self.update_background_path()
            video_presets = [
                OverlayBackgroundPreset.DAY,
                OverlayBackgroundPreset.NIGHT,
                OverlayBackgroundPreset.OUTDOORS,
            ]
            if self.current_preset in video_presets:
                if self.open_video():
                    import cv2

                    fps = self.video_capture.get(cv2.CAP_PROP_FPS)
                    if fps > 0:
                        timer_interval = int(1000 / fps)
                        self.update_timer.setInterval(timer_interval)
            self.update_composite()

            log.info("OverlayWidget initialized successfully.")
        except Exception as e:
            log.error(f"Failed to initialize OverlayWidget: {e}", exc_info=True)
            raise

    def update_background_path(self) -> None:
        """Update the background path based on current preset."""
        if self.current_preset == OverlayBackgroundPreset.CAMERA:
            self.background_path = None
        elif self.current_preset == OverlayBackgroundPreset.DAY:
            self.background_path = os.path.join(
                self.framework_dir,
                OVERLAY_BACKGROUND_VIDEO_DAY_PATH,
            )
        elif self.current_preset == OverlayBackgroundPreset.NIGHT:
            self.background_path = os.path.join(
                self.framework_dir,
                OVERLAY_BACKGROUND_VIDEO_NIGHT_PATH,
            )
        elif self.current_preset == OverlayBackgroundPreset.OUTDOORS:
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

    def open_camera(self) -> bool:
        """
        Open the camera for video capture.

        Returns:
            bool: True if camera opened successfully, False otherwise.
        """
        if self.camera_capture is not None:
            return True

        try:
            import cv2

            self.camera_capture = cv2.VideoCapture(0)
            if not self.camera_capture.isOpened():
                log.error("Could not open camera")
                self.camera_capture = None
                return False
            # Discard initial frames to allow camera to stabilize
            for _ in range(INITIAL_CAMERA_FRAMES_TO_DISCARD):
                self.camera_capture.read()
            log.info("Camera opened successfully")
            return True
        except Exception as e:
            log.error(f"Error opening camera: {e}", exc_info=True)
            self.camera_capture = None
            return False

    def close_camera(self) -> None:
        """Close the camera and release resources."""
        if self.camera_capture is not None:
            try:
                self.camera_capture.release()
                self.camera_capture = None
                log.info("Camera closed")
            except Exception as e:
                log.error(f"Error closing camera: {e}", exc_info=True)

    def open_video(self) -> bool:
        """
        Open the video file for playback using MediaViewer's video handling pattern.

        Returns:
            bool: True if video opened successfully, False otherwise.
        """
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

    def close_video(self) -> None:
        """Close the video and release resources using MediaViewer's cleanup pattern."""
        if self.video_capture is not None:
            try:
                self.video_capture.release()
                self.video_capture = None
                log.info("Video closed")
            except Exception as e:
                log.error(f"Error closing video: {e}", exc_info=True)

    def change_background(self, preset: str) -> None:
        """
        Change the background preset.

        Args:
            preset (str): Background preset name ("day", "night", "outdoors", or "camera").
        """
        try:
            preset_enum = OverlayBackgroundPreset(preset.lower())
        except ValueError:
            log.warning(f"Invalid background preset: {preset}")
            return

        video_presets = [
            OverlayBackgroundPreset.DAY,
            OverlayBackgroundPreset.NIGHT,
            OverlayBackgroundPreset.OUTDOORS,
        ]

        if (
            self.current_preset == OverlayBackgroundPreset.CAMERA
            and preset_enum != OverlayBackgroundPreset.CAMERA
        ):
            self.close_camera()
            timer_interval = int(1000 / BACKGROUND_VIDEO_FRAME_RATE)
            self.update_timer.setInterval(timer_interval)

        if self.current_preset in video_presets and preset_enum not in video_presets:
            self.close_video()
            timer_interval = int(1000 / BACKGROUND_VIDEO_FRAME_RATE)
            self.update_timer.setInterval(timer_interval)

        if (
            self.current_preset in video_presets
            and preset_enum in video_presets
            and self.current_preset != preset_enum
        ):
            self.close_video()

        if (
            preset_enum == OverlayBackgroundPreset.CAMERA
            and self.current_preset != OverlayBackgroundPreset.CAMERA
        ):
            if not self.open_camera():
                log.error("Failed to open camera, keeping current preset")
                return
            timer_interval = int(1000 / BACKGROUND_VIDEO_FRAME_RATE)
            self.update_timer.setInterval(timer_interval)

        if preset_enum in video_presets and (
            self.current_preset not in video_presets
            or self.current_preset != preset_enum
        ):
            self.current_preset = preset_enum
            self.update_background_path()
            if not self.open_video():
                log.error("Failed to open video, keeping current preset")
                return
            import cv2

            fps = self.video_capture.get(cv2.CAP_PROP_FPS)
            if fps > 0:
                timer_interval = int(1000 / fps)
            else:
                log.warning("Video FPS not found, using camera frame rate")
                timer_interval = int(1000 / BACKGROUND_VIDEO_FRAME_RATE)  # Fallback
            self.update_timer.setInterval(timer_interval)
        else:
            self.current_preset = preset_enum
            self.update_background_path()

        self.update_composite()
        log.info(f"Background changed to: {preset}")

    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle widget close event to cleanup camera, video, and timer."""
        if self.update_timer and self.update_timer.isActive():
            self.update_timer.stop()
        self.close_camera()
        self.close_video()
        super().closeEvent(event)

    def update_composite(self) -> None:
        """Update the composited image using additive blending with OpenCV."""
        # Skip updates if window is not visible to save resources
        if not self.isVisible():
            return

        import cv2  # load here so it's not loaded every time an app runs

        try:
            composite_width = self.resolution[0]
            composite_height = self.resolution[1]

            if self.current_preset == OverlayBackgroundPreset.CAMERA:
                if self.camera_capture is None or not self.camera_capture.isOpened():
                    log.warning("Camera not available")
                    return
                ret, background = self.camera_capture.read()
                if not ret or background is None:
                    log.warning("Failed to read frame from camera")
                    return

                cam_height, cam_width = background.shape[:2]
                target_aspect = composite_width / composite_height
                cam_aspect = cam_width / cam_height

                if cam_aspect > target_aspect:
                    new_height = composite_height
                    new_width = int(cam_width * (composite_height / cam_height))
                    background = cv2.resize(
                        background,
                        (new_width, new_height),
                        interpolation=cv2.INTER_LINEAR,
                    )
                    crop_x = (new_width - composite_width) // 2
                    background = background[:, crop_x : crop_x + composite_width]
                else:
                    new_width = composite_width
                    new_height = int(cam_height * (composite_width / cam_width))
                    background = cv2.resize(
                        background,
                        (new_width, new_height),
                        interpolation=cv2.INTER_LINEAR,
                    )
                    crop_y = (new_height - composite_height) // 2
                    background = background[crop_y : crop_y + composite_height, :]
            elif self.current_preset in [
                OverlayBackgroundPreset.DAY,
                OverlayBackgroundPreset.NIGHT,
                OverlayBackgroundPreset.OUTDOORS,
            ]:
                if self.video_capture is None or not self.video_capture.isOpened():
                    log.warning("Video not available")
                    return
                ret, background = self.video_capture.read()
                if not ret or background is None:
                    log.debug("Video ended, looping back to start")
                    self.video_capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, background = self.video_capture.read()
                    if not ret or background is None:
                        log.warning("Failed to read frame from video after looping")
                        return

                video_height, video_width = background.shape[:2]
                target_aspect = composite_width / composite_height
                video_aspect = video_width / video_height

                if video_aspect > target_aspect:
                    new_height = composite_height
                    new_width = int(video_width * (composite_height / video_height))
                    background = cv2.resize(
                        background,
                        (new_width, new_height),
                        interpolation=cv2.INTER_LINEAR,
                    )
                    crop_x = (new_width - composite_width) // 2
                    background = background[:, crop_x : crop_x + composite_width]
                else:
                    new_width = composite_width
                    new_height = int(video_height * (composite_width / video_width))
                    background = cv2.resize(
                        background,
                        (new_width, new_height),
                        interpolation=cv2.INTER_LINEAR,
                    )
                    crop_y = (new_height - composite_height) // 2
                    background = background[crop_y : crop_y + composite_height, :]
            else:
                if self.background_path is None or not os.path.exists(
                    self.background_path
                ):
                    log.warning(f"Background image not found: {self.background_path}")
                    return

                background = cv2.imread(self.background_path)
                if background is None:
                    log.warning(
                        f"Failed to load background image: {self.background_path}"
                    )
                    return

                background = cv2.resize(
                    background,
                    (composite_width, composite_height),
                    interpolation=cv2.INTER_LINEAR,
                )

            snapshot = None
            if os.path.exists(self.snapshot_path):
                snapshot = cv2.imread(self.snapshot_path)
                if snapshot is not None:
                    snapshot = cv2.resize(
                        snapshot,
                        (APP_RESOLUTION[0], APP_RESOLUTION[1]),
                        interpolation=cv2.INTER_LINEAR,
                    )

                    x = (composite_width - APP_RESOLUTION[0]) // 2 + RIGHT_WINDOW_OFFSET
                    y = (composite_height - APP_RESOLUTION[1]) // 2

                    ### BLENDING LOGIC ###

                    # Apply brightness adjustment to snapshot
                    if self.brightness != 1.0:
                        snapshot_adjusted = cv2.convertScaleAbs(
                            snapshot, alpha=self.brightness, beta=0
                        )
                    else:
                        snapshot_adjusted = snapshot

                    # Extract the region where snapshot will be placed
                    roi = background[
                        y : y + APP_RESOLUTION[1], x : x + APP_RESOLUTION[0]
                    ]

                    # Apply additive blending: add snapshot to background region
                    blended_roi = cv2.add(roi, snapshot_adjusted)

                    # Place the blended region back (modify background in place)
                    background[y : y + APP_RESOLUTION[1], x : x + APP_RESOLUTION[0]] = (
                        blended_roi
                    )

                    composite = background

                    ### END BLENDING LOGIC ###
                else:
                    composite = background
                    log.debug(f"Snapshot not available, using background only")
            else:
                composite = background
                log.debug(f"Snapshot file not found: {self.snapshot_path}")

            composite_rgb = cv2.cvtColor(composite, cv2.COLOR_BGR2RGB)

            height, width, channel = composite_rgb.shape
            bytes_per_line = 3 * width
            q_image = QImage(
                composite_rgb.data, width, height, bytes_per_line, QImage.Format_RGB888
            )
            q_image = q_image.copy()
            pixmap = QPixmap.fromImage(q_image)

            self.composite_label.setPixmap(pixmap)

        except Exception as e:
            log.error(f"Failed to update composite: {e}", exc_info=True)


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
        try:
            self.setWindowTitle("Raven App (alpha v0.1)")
            self.setFixedSize(
                int(APP_WINDOW_RESOLUTION[0]), int(APP_WINDOW_RESOLUTION[1])
            )
            self.overlay_window = None  # Will be set later

            container = QWidget(self)
            layout = QVBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            app_widget.set_env_background_color("black")
            app_widget.set_app_background_color("black")
            app_widget.move(0, 0)

            layout.addWidget(app_widget, 1)  # Stretch factor 1 to take available space

            button_container = QWidget(container)
            button_layout = QHBoxLayout(button_container)
            button_layout.setContentsMargins(10, 5, 10, 5)
            button_layout.setSpacing(10)

            self.simulator_button = QPushButton("Show Simulator", button_container)
            self.simulator_button.setFixedHeight(40)
            self.simulator_button.setMinimumWidth(150)
            self.simulator_button.setAutoFillBackground(False)
            self.simulator_button.setStyleSheet(
                """
                QPushButton {
                    background-color: #2a2a2a;
                    color: white;
                    border: 2px solid #555;
                    border-radius: 10px;
                    font-size: 14px;
                    font-weight: 600;
                    padding: 5px 15px;
                }
                QPushButton:hover {
                    background-color: #3a3a3a;
                    border: 2px solid #777;
                }
                QPushButton:pressed {
                    background-color: #1a1a1a;
                    border: 2px solid #555;
                }
            """
            )
            self.simulator_button.setFlat(False)

            def apply_rounded_mask():
                path = QPainterPath()
                path.addRoundedRect(self.simulator_button.rect(), 10, 10)
                region = QRegion(path.toFillPolygon().toPolygon())
                self.simulator_button.setMask(region)

            self._apply_simulator_mask = apply_rounded_mask
            self.simulator_button.clicked.connect(self.toggle_simulator)
            QTimer.singleShot(0, apply_rounded_mask)
            button_layout.addWidget(self.simulator_button)

            self.background_buttons = []
            button_style = """
                QPushButton {
                    background-color: rgba(30, 30, 30, 200);
                    color: white;
                    border: 2px solid rgba(255, 255, 255, 255);
                    border-radius: 10px;
                    font-size: 14px;
                    font-weight: 600;
                    padding: 5px 15px;
                }
                QPushButton:hover {
                    background-color: rgba(50, 50, 50, 220);
                    border: 2px solid rgba(255, 255, 255, 255);
                }
                QPushButton:pressed {
                    background-color: rgba(70, 70, 70, 240);
                    border: 2px solid rgba(255, 255, 255, 255);
                }
            """

            for preset_enum in OverlayBackgroundPreset:
                preset_str = preset_enum.value
                button = QPushButton(preset_str.capitalize(), button_container)
                button.setFixedSize(100, 40)
                button.setAutoFillBackground(False)
                button.setStyleSheet(button_style)
                button.setFlat(False)

                def apply_rounded_mask():
                    path = QPainterPath()
                    path.addRoundedRect(button.rect(), 10, 10)
                    region = QRegion(path.toFillPolygon().toPolygon())
                    button.setMask(region)

                QTimer.singleShot(0, apply_rounded_mask)
                button.clicked.connect(
                    lambda checked, p=preset_str: self.change_background(p)
                )
                button.hide()
                self.background_buttons.append(button)
                button_layout.addWidget(button)

            button_layout.addStretch()
            button_container.setFixedHeight(60)
            layout.addWidget(button_container)

            self.setCentralWidget(container)
            set_custom_circle_cursor(app_widget)

            log.info("RunApp initialized successfully.")
        except Exception as e:
            log.error(f"Failed to initialize RunApp: {e}", exc_info=True)
            raise

    def set_overlay_window(self, overlay_window) -> None:
        """Set the overlay window reference for the simulator button."""
        self.overlay_window = overlay_window
        if overlay_window:
            original_close_event = overlay_window.closeEvent

            def close_event_handler(event):
                # Stop the timer when window is closed
                if (
                    hasattr(overlay_window, "update_timer")
                    and overlay_window.update_timer.isActive()
                ):
                    overlay_window.update_timer.stop()
                self.simulator_button.setText("Show Simulator")
                for button in self.background_buttons:
                    button.hide()
                original_close_event(event)

            overlay_window.closeEvent = close_event_handler

    def change_background(self, preset: str) -> None:
        """Change the background preset of the overlay window."""
        if self.overlay_window is None:
            return
        self.overlay_window.change_background(preset)

    def toggle_simulator(self) -> None:
        """Toggle the visibility of the simulator overlay window."""
        if self.overlay_window is None:
            return

        if self.overlay_window.isVisible():
            self.overlay_window.hide()
            # Pause the timer when simulator is hidden
            if (
                hasattr(self.overlay_window, "update_timer")
                and self.overlay_window.update_timer.isActive()
            ):
                self.overlay_window.update_timer.stop()
            self.simulator_button.setText("Show Simulator")
            for button in self.background_buttons:
                button.hide()
        else:
            self.overlay_window.show()
            # Resume the timer when simulator is shown
            if (
                hasattr(self.overlay_window, "update_timer")
                and not self.overlay_window.update_timer.isActive()
            ):
                self.overlay_window.update_timer.start()
            self.simulator_button.setText("Hide Simulator")
            for button in self.background_buttons:
                button.show()

    def _sync_button_state(self) -> None:
        """Update button text and visibility to match window state."""
        self.simulator_button.setText("Show Simulator")
        for button in self.background_buttons:
            button.hide()

    @staticmethod
    def run(
        app_widget_fn: Callable[[], QWidget],
        app_id: str = "",
        app_key: str = "",
        use_async_loop: bool = False,
        show_overlayed_window: bool = True,
        overlay_resolution: tuple[int, int] = OVERLAY_RESOLUTION,
        overlay_brightness: float = DEFAULT_OVERLAY_BRIGHTNESS,
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
            overlay_resolution (tuple[int, int]): Resolution of the overlay window (width, height).
                Defaults to OVERLAY_RESOLUTION (800, 900).
            overlay_brightness (float): Brightness multiplier for the snapshot in additive blending.
                1.0 = normal, <1.0 = dimmer, >1.0 = brighter. Defaults to 1.0.
            should_preload_fonts (bool): If True, preloads fonts after QApplication is created.
                Defaults to False.
        """

        args = sys.argv[1:]
        log.info(f"Command-line args: {args}")
        if len(args) > 0 and (args[0] == "deploy" or args[0] == "deploy-pyc"):
            if not ACCEPTING_DEPLOYMENTS:
                error_msg = "Not accepting deployments right now, contact Raven team to get access"
                log.warning(error_msg)
                print(f"{error_msg}", file=sys.stdout)
                return
            if app_id == "":
                error_msg = "Please add app_id to function call"
                log.error(error_msg)
                print(f"ERROR: {error_msg}", file=sys.stderr)
                return
            elif app_key == "":
                error_msg = "Please add app_key to function call"
                log.error(error_msg)
                print(f"ERROR: {error_msg}", file=sys.stderr)
                return
            else:
                compile_pyc = args[0] == "deploy-pyc"
                log.info(
                    f"Deployment mode: {'compiled (.pyc)' if compile_pyc else 'source (.py)'}"
                )

                build_path = RunApp.deploy_app(compile_pyc=compile_pyc)
                if build_path:
                    log.info(f"Build path: {build_path}")
                    print(f"Build path: {build_path}", file=sys.stdout)
                else:
                    error_msg = "Failed to create build package, cannot upload"
                    log.error(error_msg)
                    print(f"ERROR: {error_msg}", file=sys.stderr)
                    return

                data = {"app_id": app_id, "app_key": app_key}

                developer_end_point = f"{BASE_API_URL}/rest/api/developer/run/app/"
                print("Uploading package...", file=sys.stdout)
                with open(build_path, "rb") as build_file:
                    files = {"rav_build": build_file}
                    response = requests.post(
                        url=developer_end_point, data=data, files=files
                    )

                upload_msg = f"Upload response status: {response.status_code}"
                log.info(upload_msg)
                if response.status_code == 200:
                    print(f"{upload_msg} - Upload successful!", file=sys.stdout)
                else:
                    print(f"{upload_msg} - Upload failed!", file=sys.stderr)
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

            # Set up Qt exception handler to catch unhandled exceptions in Qt slots/callbacks
            def qt_exception_handler(exc_type, exc_value, exc_traceback):
                """Handle unhandled exceptions in Qt event loop."""
                if issubclass(exc_type, KeyboardInterrupt):
                    sys.__excepthook__(exc_type, exc_value, exc_traceback)
                    return

                error_msg = "".join(
                    traceback.format_exception(exc_type, exc_value, exc_traceback)
                )
                print("\n" + "=" * 80, file=sys.stderr)
                print(
                    "ERROR: Unhandled exception in your application!", file=sys.stderr
                )
                print("=" * 80, file=sys.stderr)
                print(error_msg, file=sys.stderr)
                print("=" * 80 + "\n", file=sys.stderr)
                log.error(
                    f"Unhandled exception in application: {exc_value}", exc_info=True
                )
                sys.exit(1)

            # Install exception handler
            sys.excepthook = qt_exception_handler

            if should_preload_fonts:
                try:
                    preload_fonts()
                except Exception as e:
                    error_msg = f"Failed to preload fonts: {e}"
                    print(f"ERROR: {error_msg}", file=sys.stderr)
                    traceback.print_exc()
                    log.error(error_msg, exc_info=True)
                    raise

            # Call app widget function with error handling
            try:
                app_widget = app_widget_fn()
            except Exception as e:
                error_msg = f"Failed to create app widget: {e}"
                print("\n" + "=" * 80, file=sys.stderr)
                print("ERROR: Failed to create your application!", file=sys.stderr)
                print("=" * 80, file=sys.stderr)
                print(f"Exception: {type(e).__name__}: {e}", file=sys.stderr)
                print("\nFull traceback:", file=sys.stderr)
                traceback.print_exc()
                print("=" * 80 + "\n", file=sys.stderr)
                log.error(error_msg, exc_info=True)
                raise

            if app_widget is None:
                error_msg = "App widget function returned None"
                print(f"ERROR: {error_msg}", file=sys.stderr)
                log.error(error_msg, extra={"console": True})
                raise ValueError(error_msg)

            log.info("RAVEN APP READY LAUNCH SIGNAL", extra={"console": True})

            # Create window with error handling
            try:
                window = RunApp(app_widget)
            except Exception as e:
                error_msg = f"Failed to create RunApp window: {e}"
                print("\n" + "=" * 80, file=sys.stderr)
                print(
                    "ERROR: Failed to initialize application window!", file=sys.stderr
                )
                print("=" * 80, file=sys.stderr)
                print(f"Exception: {type(e).__name__}: {e}", file=sys.stderr)
                print("\nFull traceback:", file=sys.stderr)
                traceback.print_exc()
                print("=" * 80 + "\n", file=sys.stderr)
                log.error(error_msg, exc_info=True)
                raise

            if is_raven_device():
                window.setWindowFlags(Qt.FramelessWindowHint)
            window.show()
            window.move(0, 0)
            log.info("Application started.")

            if not is_raven_device() and show_overlayed_window:
                widget_name = app_widget.__class__.__name__
                snapshot_filename = f"{widget_name}_{SNAPSHOT_FILENAME}"

                assets_dir = os.path.join(os.path.dirname(__file__), "..", "assets")
                os.makedirs(assets_dir, exist_ok=True)

                tmp_dir = os.path.join(assets_dir, SNAPSHOT_TMP_DIR)
                os.makedirs(tmp_dir, exist_ok=True)
                snapshot_path = os.path.join(tmp_dir, snapshot_filename)

                def cleanup_snapshot_tmp():
                    """Remove the snapshot file on process exit, and tmp dir if empty."""
                    try:
                        if os.path.exists(snapshot_path):
                            os.remove(snapshot_path)
                            log.info(f"Cleaned up snapshot file: {snapshot_path}")

                        if os.path.exists(tmp_dir):
                            try:
                                if not os.listdir(tmp_dir):
                                    os.rmdir(tmp_dir)
                                    log.info(f"Removed empty tmp directory: {tmp_dir}")
                            except OSError:
                                pass
                    except Exception as e:
                        log.warning(f"Failed to cleanup snapshot file: {e}")

                atexit.register(cleanup_snapshot_tmp)

                def signal_handler(signum, frame):
                    """Handle termination signals."""
                    cleanup_snapshot_tmp()
                    sys.exit(0)

                signal.signal(signal.SIGTERM, signal_handler)
                signal.signal(signal.SIGINT, signal_handler)

                snapshot_thread_active = False

                def save_snapshot_in_background(pixmap: QPixmap, path: str):
                    """Save the pixmap to disk in a background thread."""
                    nonlocal snapshot_thread_active
                    try:
                        # Convert pixmap to image for thread-safe saving
                        image = pixmap.toImage()
                        # Write to temporary file first, then atomically rename
                        # Prevent race conditions when OverlayWidget reads the file
                        temp_path = path + ".tmp"
                        image.save(temp_path, "PNG")
                        # Atomic rename to prevent reading partial files
                        os.replace(temp_path, path)
                    except Exception as e:
                        log.error(f"Failed to save widget snapshot: {e}")
                        # Clean up temp file if it exists
                        temp_path = path + ".tmp"
                        if os.path.exists(temp_path):
                            try:
                                os.remove(temp_path)
                            except Exception:
                                pass
                    finally:
                        snapshot_thread_active = False

                def capture_widget_snapshot():
                    """Capture the widget and queue it for background saving."""
                    nonlocal snapshot_thread_active
                    try:
                        # grab() must be called on main thread
                        pixmap = app_widget.grab()

                        # Skip this frame if previous save is still in progress
                        if snapshot_thread_active:
                            return

                        # Start save operation in background thread
                        snapshot_thread_active = True
                        thread = threading.Thread(
                            target=save_snapshot_in_background,
                            args=(pixmap, snapshot_path),
                            daemon=True,
                        )
                        thread.start()

                    except Exception as e:
                        log.error(f"Failed to capture widget snapshot: {e}")
                        snapshot_thread_active = False

                snapshot_timer = QTimer()
                snapshot_timer.timeout.connect(capture_widget_snapshot)
                if OVERLAY_FRAME_RATE <= 0:
                    error_msg = (
                        f"OVERLAY_FRAME_RATE must be positive, got {OVERLAY_FRAME_RATE}"
                    )
                    log.error(error_msg, extra={"console": True})
                    raise ValueError(error_msg)
                timer_interval = int(1000 / OVERLAY_FRAME_RATE)
                snapshot_timer.start(timer_interval)
                capture_widget_snapshot()
                log.info(f"Widget snapshot capture enabled (every {timer_interval}ms)")

                framework_dir = os.path.dirname(os.path.dirname(__file__))

                overlay_window = OverlayWidget(
                    snapshot_path,
                    framework_dir,
                    overlay_resolution,
                    overlay_brightness,
                )
                overlay_window.move(
                    SIMULATOR_WINDOW_POSITION[0], SIMULATOR_WINDOW_POSITION[1]
                )  # Position it next to the main window
                window.set_overlay_window(overlay_window)
                overlay_window.hide()  # Start hidden, user can show it with the button
                log.info(
                    "Overlay window created (hidden by default, use 'Show Simulator' button to display)"
                )

            if use_async_loop:
                from qasync import QEventLoop

                loop = QEventLoop(app)
                asyncio.set_event_loop(loop)
                log.info("Using async event loop")
                try:
                    with loop:
                        loop.run_forever()
                except Exception as e:
                    error_msg = f"Error in async event loop: {e}"
                    print("\n" + "=" * 80, file=sys.stderr)
                    print("ERROR: Exception in async event loop!", file=sys.stderr)
                    print("=" * 80, file=sys.stderr)
                    print(f"Exception: {type(e).__name__}: {e}", file=sys.stderr)
                    print("\nFull traceback:", file=sys.stderr)
                    traceback.print_exc()
                    print("=" * 80 + "\n", file=sys.stderr)
                    log.error(error_msg, exc_info=True)
                    raise
            else:
                log.info("About to start app.exec()")
                try:
                    ret = app.exec()
                    log.info(f"Qt event loop exited with code: {ret}")
                    sys.exit(ret)
                except Exception as e:
                    error_msg = f"Error during Qt event loop execution: {e}"
                    print("\n" + "=" * 80, file=sys.stderr)
                    print(
                        "ERROR: Exception during application execution!",
                        file=sys.stderr,
                    )
                    print("=" * 80, file=sys.stderr)
                    print(f"Exception: {type(e).__name__}: {e}", file=sys.stderr)
                    print("\nFull traceback:", file=sys.stderr)
                    traceback.print_exc()
                    print("=" * 80 + "\n", file=sys.stderr)
                    log.error(error_msg, exc_info=True)
                    raise
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

    @staticmethod
    def _load_ravignore(app_path: str) -> List[str]:
        """
        Load patterns from .ravignore file.

        Args:
            app_path (str): Path to the app directory.

        Returns:
            List[str]: List of ignore patterns (empty list if file doesn't exist).
        """
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
        """
        Check if a relative path should be ignored based on .ravignore patterns.
        Also filters directories during os.walk.

        Simple matching: path is ignored if it starts with any pattern or equals it.

        Args:
            rel_path (str): Relative path from app root (e.g., "examples/hello.py").
            ignore_patterns (List[str]): List of ignore patterns from .ravignore.

        Returns:
            bool: True if path should be ignored, False otherwise.
        """
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
        """
        Filter directories during os.walk iteration and check if current root should be skipped.

        Modifies dirs list in place to remove ignored directories.

        Args:
            root (str): Current root directory from os.walk.
            dirs (List[str]): List of directory names (modified in place).
            app_path (str): Base app path for calculating relative paths.
            ignore_patterns (List[str]): List of ignore patterns from .ravignore.

        Returns:
            bool: True if current root directory should be skipped, False otherwise.
        """
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
        """
        Compile a Python app into .pyc bytecode files.

        Args:
            app_path (str): Path to the app directory containing Python source files.
            output_dir (str): Path to the output directory where .pyc files will be written.

        Returns:
            bool: True if compilation successful, False otherwise.

        Raises:
            OSError: If output directory cannot be created.
            py_compile.PyCompileError: If any Python file fails to compile (handled internally).
        """
        log.info(f"Compiling app at: {app_path}")

        # Create output directory
        os.makedirs(output_dir, exist_ok=True)

        # Load .ravignore patterns
        ignore_patterns = RunApp._load_ravignore(app_path)

        # Find all Python files
        python_files = []
        for root, dirs, files in os.walk(app_path):
            # Filter directories and check if current root should be skipped
            if RunApp._filter_walk_iteration(root, dirs, app_path, ignore_patterns):
                continue

            for file in files:
                if file.endswith(".py"):
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, app_path)

                    # Check if file should be ignored
                    if not RunApp._should_ignore_path(rel_path, ignore_patterns):
                        python_files.append(file_path)

        log.info(f"Found {len(python_files)} Python files to compile")

        # Compile each file
        compiled_files = []
        for py_file in python_files:
            try:
                # Get relative path from app directory
                rel_path = os.path.relpath(py_file, app_path)
                output_file = os.path.join(output_dir, rel_path + "c")  # .py -> .pyc

                # Create output directory structure
                os.makedirs(os.path.dirname(output_file), exist_ok=True)

                # Compile the file
                py_compile.compile(py_file, output_file, doraise=True)
                compiled_files.append(output_file)
                log.debug(f"Compiled: {rel_path} -> {rel_path}c")

            except py_compile.PyCompileError as e:
                log.error(f"Failed to compile {py_file}: {e}")
                return False

        log.info(f"Successfully compiled {len(compiled_files)} files")
        return True

    @staticmethod
    def copy_python_source(app_path: str, output_dir: str) -> bool:
        """
        Copy Python source files (.py) without compilation.

        Args:
            app_path (str): Path to the app directory containing Python source files.
            output_dir (str): Path to the output directory where .py files will be copied.

        Returns:
            bool: True if copy successful, False otherwise.

        Raises:
            OSError: If output directory cannot be created.
        """
        log.info(f"Copying Python source files from: {app_path}")

        # Create output directory
        os.makedirs(output_dir, exist_ok=True)

        # Load .ravignore patterns
        ignore_patterns = RunApp._load_ravignore(app_path)

        # Find all Python files
        python_files = []
        for root, dirs, files in os.walk(app_path):
            # Filter directories and check if current root should be skipped
            if RunApp._filter_walk_iteration(root, dirs, app_path, ignore_patterns):
                continue

            for file in files:
                if file.endswith(".py"):
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, app_path)

                    # Check if file should be ignored
                    if not RunApp._should_ignore_path(rel_path, ignore_patterns):
                        python_files.append(file_path)

        log.info(f"Found {len(python_files)} Python files to copy")

        # Copy each file
        copied_files = []
        for py_file in python_files:
            try:
                # Get relative path from app directory
                rel_path = os.path.relpath(py_file, app_path)
                output_file = os.path.join(output_dir, rel_path)

                # Create output directory structure
                os.makedirs(os.path.dirname(output_file), exist_ok=True)

                # Copy the file
                shutil.copy2(py_file, output_file)
                copied_files.append(output_file)
                log.debug(f"Copied: {rel_path}")

            except Exception as e:
                log.error(f"Failed to copy {py_file}: {e}")
                return False

        log.info(f"Successfully copied {len(copied_files)} Python source files")
        return True

    @staticmethod
    def copy_assets(app_path: str, output_dir: str) -> bool:
        """
        Copy non-Python asset files from the application directory.

        Supported asset types include images (.png, .jpg, .jpeg, .gif, .svg),
        audio (.wav, .mp3), video (.mp4), and data files (.json, .txt, .md).

        Args:
            app_path (str): Path to the app directory containing asset files.
            output_dir (str): Path to the output directory where assets will be copied.

        Returns:
            bool: True if assets were copied successfully, False otherwise.

        Raises:
            OSError: If output directory structure cannot be created or files cannot be copied.
        """
        log.info("Copying assets...")

        # Load .ravignore patterns
        ignore_patterns = RunApp._load_ravignore(app_path)

        # Files to copy (non-Python)
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
        ]

        assets_copied = 0
        for root, dirs, files in os.walk(app_path):
            # Filter directories and check if current root should be skipped
            if RunApp._filter_walk_iteration(root, dirs, app_path, ignore_patterns):
                continue

            for file in files:
                if any(file.endswith(ext) for ext in asset_extensions):
                    src_path = os.path.join(root, file)
                    rel_path = os.path.relpath(src_path, app_path)

                    # Check if file should be ignored
                    if RunApp._should_ignore_path(rel_path, ignore_patterns):
                        continue

                    dst_path = os.path.join(output_dir, rel_path)

                    # Create directory structure
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
        """
        Create a .rav package (zip archive) from an application.

        This function either compiles Python files to .pyc or copies .py source files,
        copies assets, includes requirements.txt if present, and packages everything
        into a .rav zip file. The temporary build directory is cleaned up after package creation.

        Args:
            app_path (str): Path to the application directory to package.
            output_path (str): File path where the .rav package will be created.
            compile_pyc (bool): If True, compile Python files to .pyc. If False, copy .py source files.
                Defaults to True for backward compatibility.

        Returns:
            bool: True if package creation succeeded, False otherwise.

        Raises:
            OSError: If temporary directory cannot be created or cleaned up.
            zipfile.BadZipFile: If zip file creation fails.
        """
        log.info(f"Creating .rav package: {output_path} (compile_pyc={compile_pyc})")

        # Create temporary directory for build
        temp_dir = f"/tmp/raven_deploy_{int(time.time())}"
        os.makedirs(temp_dir, exist_ok=True)

        try:
            # Compile the app or copy Python source files
            if compile_pyc:
                if not RunApp.compile_app(app_path, temp_dir):
                    return False
            else:
                if not RunApp.copy_python_source(app_path, temp_dir):
                    return False

            # Copy assets
            if not RunApp.copy_assets(app_path, temp_dir):
                return False

            # Copy requirements.txt if it exists
            requirements_path = os.path.join(app_path, "requirements.txt")
            if os.path.exists(requirements_path):
                shutil.copy2(requirements_path, temp_dir)
                log.info("Copied requirements.txt")
            
            # Copy default run.sh if one is not provided by the app
            build_run_sh_path = os.path.join(temp_dir, "run.sh")
            if not os.path.exists(build_run_sh_path):
                default_run_sh_path = os.path.join(os.path.dirname(__file__), "run.sh")
                if os.path.exists(default_run_sh_path):
                    shutil.copy2(default_run_sh_path, build_run_sh_path)
                    log.info("Added default run.sh")
                else:
                    log.warning(
                        f"Default run.sh not found at {default_run_sh_path}; skipping"
                    )

            # Create .rav zip file and collect package structure details
            package_stats = {
                "python_files": 0,
                "assets": {"images": 0, "audio": 0, "video": 0, "data": 0, "other": 0},
                "requirements": False,
                "directories": set(),
                "total_files": 0,
                "file_list": [],
            }

            with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(temp_dir):
                    # Skip any directory named "raven_framework"
                    if "raven_framework" in root:
                        log.info("Found raven_framework in source, ignoring")
                        continue
                    for file in files:
                        file_path = os.path.join(root, file)
                        arc_path = os.path.relpath(file_path, temp_dir)
                        zipf.write(file_path, arc_path)
                        log.debug(f"Added to package: {arc_path}")

                        # Collect file list
                        package_stats["file_list"].append(arc_path)

                        # Collect statistics
                        package_stats["total_files"] += 1
                        dir_name = os.path.dirname(arc_path)
                        if dir_name:
                            package_stats["directories"].add(dir_name)

                        # Categorize files
                        if file.endswith((".pyc", ".py")):
                            package_stats["python_files"] += 1
                        elif file.endswith((".png", ".jpg", ".jpeg", ".gif", ".svg")):
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

            # Build detailed log message
            package_size = os.path.getsize(output_path)
            size_mb = package_size / (1024 * 1024)

            details = [
                f"Package: {os.path.basename(output_path)}",
                f"Size: {size_mb:.2f} MB",
                f"Total files: {package_stats['total_files']}",
                f"Python files: {package_stats['python_files']}",
            ]

            # Add asset breakdown
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

            # Print file list
            if package_stats["file_list"]:
                print("\nFiles in package:", file=sys.stdout)
                for file_path in sorted(package_stats["file_list"]):
                    print(f"  - {file_path}", file=sys.stdout)
            print()  # Empty line for spacing

            return True

        finally:
            # Clean up temporary directory
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                log.info("Cleaned up temporary files")

    @staticmethod
    def deploy_app(app_name: str = "dev", compile_pyc: bool = True) -> Optional[str]:
        """
        Deploy the current app as a .rav package.

        Validates Python version, cleans up old .rav files, checks for main.py,
        and creates a new .rav package with a timestamp.

        Args:
            app_name (str): Name for the app package. Defaults to "dev".
            compile_pyc (bool): If True, compile Python files to .pyc. If False, copy .py source files.
                Defaults to True for backward compatibility.

        Returns:
            Optional[str]: Path to the created .rav package if successful, None otherwise.

        Raises:
            SystemExit: If Python version is not 3.12.12 or main.py is not found.
        """
        # Get actual Python version from the running interpreter
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

        # Clean up old .rav files
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
