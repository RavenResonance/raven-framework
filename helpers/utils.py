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
Heavy utility functions for Raven Framework.

This module provides image and video processing utilities that require
OpenCV and NumPy. Light utilities are imported from utils_light.
"""

import base64
from typing import Optional

import cv2
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPixmap

from .logger import get_logger

# Import light functions from utils_light (no OpenCV/numpy)
from .utils_light import (
    css_color,
    hex_to_qcolor,
    pascal_to_snake,
    qcolor_to_hex,
    snake_to_pascal_case,
    snake_to_spaced_pascal,
    spaced_pascal_to_snake,
    to_qcolor,
)

log = get_logger("Utils")


def convert_ndarray_to_pixmap_image(
    frame: np.ndarray, width: int, height: int
) -> Optional[QPixmap]:
    """
    Convert numpy array (OpenCV frame) to QPixmap for display.

    Automatically resizes the frame if dimensions don't match and converts
    from BGR to RGB format.

    Args:
        frame (np.ndarray): Image frame as NumPy array in BGR format from OpenCV.
        width (int): Target width in pixels.
        height (int): Target height in pixels.

    Returns:
        Optional[QPixmap]: QPixmap object for display, or None on error.
    """
    try:
        # Resize frame if needed
        if frame.shape[1] != width or frame.shape[0] != height:
            frame = cv2.resize(frame, (width, height))

        # Convert BGR to RGB
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Convert to QImage
        height, width, channel = rgb_frame.shape
        bytes_per_line = 3 * width
        q_image = QImage(
            rgb_frame.data, width, height, bytes_per_line, QImage.Format_RGB888
        )

        # Convert to QPixmap
        return QPixmap.fromImage(q_image)
    except Exception as e:
        log.error(f"convert_ndarray_to_pixmap_image: Error converting frame: {e}")
        return None


def convert_ndarray_to_base64_image(image: np.ndarray) -> str:
    """
    Convert numpy array (OpenCV image) to base64-encoded JPEG string.

    Args:
        image (np.ndarray): Image as NumPy array in BGR format from OpenCV.

    Returns:
        str: Base64-encoded JPEG string, or empty string on error.
    """
    try:
        _, buffer = cv2.imencode(".jpg", image)
        image_base64 = base64.b64encode(buffer).decode("utf-8")
        return image_base64
    except Exception as e:
        log.error(f"convert_ndarray_to_base64_image: Error converting image: {e}")
        return ""


def get_frame_from_video(
    path: str, max_width: int = 260, frame_number: int = 10
) -> Optional[QPixmap]:
    """
    Extract a frame from video file and convert to QPixmap.

    Args:
        path (str): Path to the video file.
        max_width (int): Maximum width for the extracted frame. Height is calculated
            to maintain aspect ratio. Defaults to 260.
        frame_number (int): Frame number to extract (0-based). Defaults to 10.

    Returns:
        Optional[QPixmap]: QPixmap of the extracted frame, or None on error.
    """
    try:
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            log.error(f"get_frame_from_video: Could not open video: {path}")
            return None

        # Set frame position
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_pos = min(frame_number, total_frames - 1)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)

        # Read frame
        ret, frame = cap.read()
        cap.release()

        if not ret:
            log.error(f"get_frame_from_video: Could not read frame from: {path}")
            return None

        # Calculate height maintaining aspect ratio
        height = int((max_width * frame.shape[0]) / frame.shape[1])

        # Convert to QPixmap
        return convert_ndarray_to_pixmap_image(frame, max_width, height)

    except Exception as e:
        log.error(f"get_frame_from_video: Error processing video {path}: {e}")
        return None


def base64_to_image(base64_string: str) -> Optional[np.ndarray]:
    """
    Convert base64 string back to numpy array (OpenCV image).

    Args:
        base64_string (str): Base64-encoded image string.

    Returns:
        Optional[np.ndarray]: Image as NumPy array in BGR format, or None on error.
    """
    try:
        image_data = base64.b64decode(base64_string)
        nparr = np.frombuffer(image_data, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return image
    except Exception as e:
        log.error(f"base64_to_image: Error converting base64 to image: {e}")
        return None


def image_to_base64(image: np.ndarray) -> str:
    """
    Convert numpy array (OpenCV image) to base64-encoded JPEG string.

    This is a convenience wrapper around convert_ndarray_to_base64_image.

    Args:
        image (np.ndarray): Image as NumPy array in BGR format from OpenCV.

    Returns:
        str: Base64-encoded JPEG string, or empty string on error.
    """
    return convert_ndarray_to_base64_image(image)
