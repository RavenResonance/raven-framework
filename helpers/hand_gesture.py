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

from typing import Optional

import cv2
import numpy as np
from cvzone.HandTrackingModule import HandDetector
from PySide6.QtCore import QThread, Signal

from ..helpers.logger import get_logger
from ..helpers.utils_light import is_raven_device
from ..peripherals.camera import Camera

log = get_logger("HandGesture")

# Mirror frames horizontally when running on a dev machine (laptop webcam is mirrored)
SIMULATOR_MODE = not is_raven_device()
# Frame rate for hand gesture processing
CAMERA_FPS = 15


class HandGestureDetector(QThread):
    """
    Hand gesture thread using OpenCV (cvzone) for pinch gesture detection. It will be expanded to include more capabilities.

    Locates hand landmarks using OpenCV-based hand detection and detects pinch gestures between
    thumb and index finger. Emits horizontal position (0.0 to 1.0) when a pinch
    is detected, where 0.0 is left edge and 1.0 is right edge of the camera view.

    Args:
        parent (Optional[QObject]): Parent QObject. Defaults to None.

    Signals:
        finger_position_updated (float): Emitted when a pinch gesture is detected.
            Value is horizontal position from 0.0 (left) to 1.0 (right).

    Attributes:
        running (bool): Whether the gesture thread is running.
        detector: OpenCV-based hand detector (cvzone HandDetector).
        camera: Camera sensor instance for capturing frames.
        pinch_threshold (float): Distance threshold for pinch detection (in pixels, normalized by image width).

    """

    finger_position_updated = Signal(
        float
    )  # Signal to emit horizontal position (0.0 to 1.0)

    def __init__(self, parent: Optional[QThread] = None):
        super().__init__(parent)
        self.running = False
        self.detector = None
        self.camera = Camera()
        self.pinch_threshold = 0.05  # Normalized distance threshold (0.0 to 1.0)

    def run(self) -> None:
        """
        Main gesture loop running in a separate thread.

        Opens camera, initializes OpenCV hand detection, and continuously
        processes frames to detect pinch gestures. Emits signals when pinches
        are detected.

        Note:
            This method runs in a separate thread. Use stop() to gracefully
            terminate the loop.
        """
        self.running = True

        try:
            self.detector = HandDetector(detectionCon=0.5, maxHands=1)
        except Exception as e:
            log.error(f"Failed to initialize OpenCV hand detector: {e}", exc_info=True)
            return

        try:
            self.camera.open_camera()
            if not self.camera.cap or not self.camera.cap.isOpened():
                log.error("Could not open camera (index 0)")
                return
        except Exception as e:
            log.error(f"Failed to open camera: {e}", exc_info=True)
            return

        log.info(
            "Hand gesture detection started — pinch position (thumb + index finger)"
        )

        while self.running:
            frame = self.camera.capture_camera_image()

            if frame is None:
                self.msleep(int(1000 / CAMERA_FPS))
                continue

            if SIMULATOR_MODE:
                # Flip frame horizontally for mirror effect
                frame = cv2.flip(frame, 1)

            # Detect hands using OpenCV-based detector
            hands, _ = self.detector.findHands(frame, draw=False)

            if hands:
                for hand in hands:
                    lmList = hand["lmList"]  # List of 21 landmarks

                    if len(lmList) >= 9:
                        # Get thumb tip (landmark 4) and index finger tip (landmark 8)
                        # cvzone uses pixel coordinates, not normalized
                        thumb_tip = lmList[4]  # [x, y, z]
                        index_tip = lmList[8]  # [x, y, z]

                        # Calculate distance between thumb and index finger tips
                        dx = thumb_tip[0] - index_tip[0]
                        dy = thumb_tip[1] - index_tip[1]
                        distance_pixels = np.sqrt(dx * dx + dy * dy)

                        # Normalize distance by image width
                        img_width = frame.shape[1]
                        normalized_distance = (
                            distance_pixels / img_width if img_width > 0 else 1.0
                        )

                        if normalized_distance < self.pinch_threshold:
                            # Use midpoint position, normalized to 0.0-1.0
                            pinch_x = (
                                (thumb_tip[0] + index_tip[0]) / (2.0 * img_width)
                                if img_width > 0
                                else 0.5
                            )
                            log.debug(
                                f"Pinch detected - horizontal position: {pinch_x:.3f} (distance: {normalized_distance:.3f})"
                            )
                            self.finger_position_updated.emit(pinch_x)

            self.msleep(int(1000 / CAMERA_FPS))

        # Cleanup resources
        self._cleanup_resources()
        log.info("Hand gesture detection stopped")

    def _cleanup_resources(self) -> None:
        """
        Clean up camera and OpenCV hand detector resources.
        """
        try:
            if self.camera is not None:
                self.camera.close_camera()
                self.camera = None
                log.debug("Camera released")
        except Exception as e:
            log.error(f"Error releasing camera: {e}", exc_info=True)

        try:
            if self.detector is not None:
                self.detector = None
                log.debug("OpenCV hand detector closed")
        except Exception as e:
            log.error(f"Error closing OpenCV hand detector: {e}", exc_info=True)

    def stop(self) -> None:
        """
        Stop the hand gesture thread gracefully.

        Sets the running flag to False and waits for the thread to finish.
        Should be called before destroying the HandGestureDetector instance.
        """
        if self.running:
            log.info("Stopping hand gesture detection...")
            self.running = False
            self.wait()
            log.debug("Hand gesture thread stopped")
