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
Camera sensor for Raven Framework.

This module provides camera functionality for capturing images from either
a physical camera via sensorlib (on Raven devices) or OpenCV (in simulator mode).
Supports QR code detection and gaze annotation.
"""

# Standard library imports
import json
from pathlib import Path
from typing import Optional, Tuple

# Third-party imports
import cv2
import numpy as np

# Local imports
from ..helpers.logger import get_logger
from ..helpers.utils_light import load_config
from .sensor_utils import SensorType, initialize_sensorlib_client

log = get_logger("Camera")

# Load configuration
_config = load_config()

# Constants
DEFAULT_CAMERA_INDEX = _config["peripherals"]["DEFAULT_CAMERA_INDEX"]
INITIAL_FRAMES_TO_DISCARD = _config["peripherals"]["INITIAL_CAMERA_FRAMES_TO_DISCARD"]
GAZE_CIRCLE_RADIUS = 10


class Camera:
    """Camera class for capturing images from camera or sensorlib."""

    def __init__(self, app_id: str = "", app_key: str = "") -> None:
        """Initialize camera with optional app_id and app_key for entitlement verification."""
        self.cap: Optional[cv2.VideoCapture] = None
        self.sensorlib_client = initialize_sensorlib_client(
            app_id, app_key, SensorType.CAMERA
        )
        if not self.sensorlib_client:
            log.info("Camera: Using simulator mode (OpenCV)")

    def open_camera(self) -> Optional[cv2.VideoCapture]:
        """Open camera and return VideoCapture object or None."""
        if self.sensorlib_client:
            try:
                success = self.sensorlib_client.start_camera()
                if success:
                    log.info("Camera opened (sensorlib)")
                    return None
                return None
            except Exception as e:
                log.error(f"Error opening camera via sensorlib: {e}", exc_info=True)
                return None
        else:
            try:
                self.cap = cv2.VideoCapture(DEFAULT_CAMERA_INDEX)
                if not self.cap.isOpened():
                    log.error("Could not open camera")
                    self.cap = None
                    return None
                for _ in range(INITIAL_FRAMES_TO_DISCARD):
                    self.cap.read()
                return self.cap
            except Exception as e:
                log.error(f"Error opening camera: {e}", exc_info=True)
                return None

    def close_camera(self) -> None:
        """Close camera and release resources."""
        if self.sensorlib_client:
            try:
                self.sensorlib_client.stop_camera()
            except Exception as e:
                log.error(f"Error closing camera via sensorlib: {e}", exc_info=True)
        else:
            if self.cap:
                self.cap.release()
                self.cap = None

    def capture_camera_image(self) -> Optional[np.ndarray]:
        """Capture image from camera and return as numpy array."""
        if self.sensorlib_client:
            try:
                return self.sensorlib_client.capture_image()
            except Exception as e:
                log.error(f"Error capturing image via sensorlib: {e}", exc_info=True)
                return None
        else:
            if not self.cap:
                self.open_camera()
            if not self.cap:
                return None
            ret, frame = self.cap.read()
            if not ret or frame is None:
                return None
            return frame

    ## Utils ##
    ## ===== ##
    def capture_camera_image_and_close(self) -> Optional[np.ndarray]:
        """Capture image and close camera in one operation."""
        frame = self.capture_camera_image()
        self.close_camera()
        return frame

    def look_for_qr_code(self) -> Optional[Tuple[np.ndarray, str]]:
        """Capture image and detect QR code, returning frame and data if found."""
        frame = self.capture_camera_image()
        if frame is None:
            return None
        qr_detector = cv2.QRCodeDetector()
        data, _, _ = qr_detector.detectAndDecode(frame)
        if data:
            self.close_camera()
            return frame, data
        return None

    def get_annotate_image_with_gaze(
        self, gaze_coordinates: Tuple[int, int]
    ) -> Optional[np.ndarray]:
        """Annotate image with red circle at gaze coordinates."""
        x, y = gaze_coordinates
        annotated = self.capture_camera_image_and_close()
        if annotated is None:
            return None
        height, width = annotated.shape[:2]
        if 0 <= x < width and 0 <= y < height:
            cv2.circle(
                annotated,
                (x, y),
                radius=GAZE_CIRCLE_RADIUS,
                color=(0, 0, 255),
                thickness=-1,
            )
        return annotated

    def save_image(self, path: str, image: np.ndarray) -> None:
        """Save image to file at specified path."""
        success = cv2.imwrite(path, image)
        if not success:
            log.error(f"Failed to save image to {path}")
