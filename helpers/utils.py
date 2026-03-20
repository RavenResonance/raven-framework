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
from typing import Optional, Tuple

import cv2
import numpy as np
from PySide6.QtGui import QImage, QPixmap

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


def is_qimage_mostly_black(image: QImage, threshold: float) -> bool:
    """
    Return True if image is null or mean pixel value (0-255) is below threshold.
    """
    result = qimage_to_rgb_bytes(image)
    if result is None:
        return True
    try:
        rgb_bytes, w, h = result
        arr = np.frombuffer(rgb_bytes, dtype=np.uint8)
        return float(arr.mean()) < threshold
    except Exception:
        return True


def qimage_to_rgb_bytes(image: QImage) -> Optional[Tuple[bytes, int, int]]:
    """
    Convert QImage to contiguous RGB bytes (width * height * 3).
    Uses memoryview when contiguous; otherwise scanline copy.

    Returns:
        (bytes, width, height) or None if conversion failed.
    """
    if image.isNull():
        return None
    w, h = image.width(), image.height()
    if w <= 0 or h <= 0:
        return None
    if image.format() != QImage.Format.Format_RGB888:
        image = image.convertToFormat(QImage.Format.Format_RGB888)

    ptr = image.bits()
    bpl = image.bytesPerLine()
    row_bytes = w * 3

    # Fast path: contiguous buffer (PySide6 returns memoryview)
    if ptr is not None and bpl == row_bytes:
        try:
            buf = np.asarray(ptr, dtype=np.uint8)
            arr = buf[: h * row_bytes].reshape((h, w, 3)).copy()
            return (arr.tobytes(), w, h)
        except Exception as e:
            log.warning(
                f"qimage_to_rgb_bytes: Error converting QImage to RGB bytes: {e}. Using fallback method."
            )
            pass

    # Fallback: row-by-row via constScanLine
    try:
        arr = np.empty((h, w, 3), dtype=np.uint8)
        for i in range(h):
            line = image.constScanLine(i)
            if line is not None:
                arr[i] = np.asarray(line[:row_bytes], dtype=np.uint8).reshape(w, 3)
            else:
                for x in range(w):
                    rgb = image.pixel(x, i)
                    arr[i, x, 0] = (rgb >> 16) & 0xFF
                    arr[i, x, 1] = (rgb >> 8) & 0xFF
                    arr[i, x, 2] = rgb & 0xFF
        return (arr.tobytes(), w, h)
    except Exception:
        pass
    return None


def rgb_bytes_to_png_bytes(
    rgb_bytes: bytes,
    width: int,
    height: int,
    size: Tuple[int, int],
) -> Optional[bytes]:
    """
    Resize RGB bytes to target size and encode as PNG.

    Args:
        rgb_bytes: Contiguous RGB (width * height * 3).
        width, height: Source dimensions.
        size: (target_w, target_h).

    Returns:
        PNG bytes or None on failure.
    """
    if width <= 0 or height <= 0 or len(rgb_bytes) < width * height * 3:
        return None
    try:
        arr = np.frombuffer(rgb_bytes, dtype=np.uint8).reshape((height, width, 3))
        scaled = cv2.resize(arr, size, interpolation=cv2.INTER_LINEAR)
        bgr = cv2.cvtColor(scaled, cv2.COLOR_RGB2BGR)
        ok, png_buf = cv2.imencode(".png", bgr)
        if not ok or png_buf is None:
            return None
        return png_buf.tobytes()
    except Exception:
        return None


def rgb_bytes_to_jpeg_bytes(
    rgb_bytes: bytes,
    width: int,
    height: int,
    size: Tuple[int, int],
    quality: int,
) -> Optional[bytes]:
    """
    Resize RGB bytes to target size and encode as JPEG.

    Args:
        rgb_bytes: Contiguous RGB (width * height * 3).
        width, height: Source dimensions.
        size: (target_w, target_h).
        quality: JPEG quality 1-100.

    Returns:
        JPEG bytes or None on failure.
    """
    if width <= 0 or height <= 0 or len(rgb_bytes) < width * height * 3:
        return None
    try:
        arr = np.frombuffer(rgb_bytes, dtype=np.uint8).reshape((height, width, 3))
        scaled = cv2.resize(arr, size, interpolation=cv2.INTER_LINEAR)
        bgr = cv2.cvtColor(scaled, cv2.COLOR_RGB2BGR)
        ok, jpeg_buf = cv2.imencode(
            ".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, max(1, min(100, quality))]
        )
        if not ok or jpeg_buf is None:
            return None
        return jpeg_buf.tobytes()
    except Exception:
        return None


def qimage_to_resized_jpeg_bytes(
    image: QImage, size: Tuple[int, int], quality: int
) -> Optional[bytes]:
    """
    Resize QImage to target size and encode as JPEG bytes.
    """
    result = qimage_to_rgb_bytes(image)
    if result is None:
        return None
    rgb_bytes, w, h = result
    return rgb_bytes_to_jpeg_bytes(rgb_bytes, w, h, size, quality)


def qimage_to_resized_png_bytes(
    image: QImage, size: Tuple[int, int]
) -> Optional[bytes]:
    """
    Resize QImage to target size and encode as PNG bytes.
    """
    result = qimage_to_rgb_bytes(image)
    if result is None:
        return None
    rgb_bytes, w, h = result
    return rgb_bytes_to_png_bytes(rgb_bytes, w, h, size)
