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
Light utility functions for Raven Framework.

This module provides color conversion utilities and string transformation functions
that don't require heavy dependencies like OpenCV or NumPy.
"""

import json
import os
import re
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QCursor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from .logger import get_logger

log = get_logger("UtilsLight")

HEX_COLOR_REGEX = re.compile(r"^#?([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$")


def load_config() -> dict:
    """
    Load configuration from config.json file.

    Returns:
        dict: Configuration dictionary loaded from config.json.
    """
    config_path = Path(__file__).parent.parent / "config.json"
    with open(config_path, "r") as f:
        return json.load(f)


# Marker file that signals we are running on a real Raven device.
# Stored in /data (persistent across reboots) rather than /run (tmpfs).
# Written once by manager.py at startup and by deploy.sh on each deploy.
_ipc_config = load_config().get("ipc", {})
_ravend_socket_dir = _ipc_config.get("RAVEND_SOCKET_DIR", "/run/ravend")
RAVEN_DEVICE_MARKER_PATH = Path(
    _ipc_config.get("RAVEN_DEVICE_MARKER_PATH", "/data/raven/.is_raven_device")
)


def hex_to_qcolor(hex_code: str) -> QColor:
    """
    Convert a hex color string to a QColor object.

    Handles 3-digit and 6-digit hex codes, with or without '#' prefix.
    Returns white (#FFFFFF) on error.

    Args:
        hex_code (str): Hex color string (e.g., "#FF0000", "FF0000", "#F00", "F00").

    Returns:
        QColor: QColor object representing the hex color, or white on error.
    """
    if not isinstance(hex_code, str):
        log.error(f"hex_to_qcolor: Expected string, got {type(hex_code)}")
        return QColor(255, 255, 255)

    # Remove '#' if present
    hex_code = hex_code.lstrip("#")

    # Validate length before processing
    if not hex_code or len(hex_code) not in (3, 6):
        log.error(
            f"hex_to_qcolor: Invalid hex color length: {len(hex_code) if hex_code else 0}",
            extra={"console": True},
        )
        return QColor(255, 255, 255)

    if not HEX_COLOR_REGEX.match("#" + hex_code):
        log.error(f"hex_to_qcolor: Invalid hex color format: {hex_code}")
        return QColor(255, 255, 255)

    # Handle 3-digit hex
    if len(hex_code) == 3:
        hex_code = "".join([c * 2 for c in hex_code])

    # Convert to RGB
    try:
        r = int(hex_code[0:2], 16)
        g = int(hex_code[2:4], 16)
        b = int(hex_code[4:6], 16)
        return QColor(r, g, b)
    except ValueError:
        log.error(f"hex_to_qcolor: Failed to parse hex color: {hex_code}")
        return QColor(255, 255, 255)


def qcolor_to_hex(qcolor: QColor) -> str:
    """
    Convert a QColor object to a hex color string.

    Args:
        qcolor (QColor): QColor object to convert.

    Returns:
        str: Hex color string in format "#RRGGBB", or "#FFFFFF" on error.
    """
    if not isinstance(qcolor, QColor):
        log.error(f"qcolor_to_hex: Expected QColor, got {type(qcolor)}")
        return "#FFFFFF"

    r = qcolor.red()
    g = qcolor.green()
    b = qcolor.blue()
    return f"#{r:02x}{g:02x}{b:02x}"


def snake_to_pascal_case(snake_str: str) -> str:
    """
    Convert snake_case to PascalCase.

    Args:
        snake_str (str): String in snake_case format (e.g., "hello_world").

    Returns:
        str: String in PascalCase format (e.g., "HelloWorld").
    """
    return "".join(word.capitalize() for word in snake_str.split("_"))


def pascal_to_snake(word: str) -> str:
    """
    Convert PascalCase to snake_case.

    Args:
        word (str): String in PascalCase format (e.g., "HelloWorld").

    Returns:
        str: String in snake_case format (e.g., "hello_world").
    """
    return re.sub(r"(?<!^)(?=[A-Z])", "_", word).lower()


def spaced_pascal_to_snake(word: str) -> str:
    """
    Convert 'Spaced Pascal' to snake_case.

    Args:
        word (str): String in spaced PascalCase format (e.g., "Hello World").

    Returns:
        str: String in snake_case format (e.g., "hello_world").
    """
    return word.lower().replace(" ", "_")


def snake_to_spaced_pascal(snake_str: str) -> str:
    """
    Convert snake_case to 'Spaced Pascal'.

    Args:
        snake_str (str): String in snake_case format (e.g., "hello_world").

    Returns:
        str: String in spaced PascalCase format (e.g., "Hello World").
    """
    return " ".join(word.capitalize() for word in snake_str.split("_"))


def css_color(color: Any) -> str:
    """
    Convert various color formats to CSS-compatible hex string.

    Handles QColor objects, hex strings (with or without '#'), and common color names.
    Returns white (#FFFFFF) on error.

    Args:
        color: Color in any supported format (QColor, hex string, color name).

    Returns:
        str: CSS-compatible hex color string (e.g., "#FFFFFF").
    """
    if isinstance(color, QColor):
        return qcolor_to_hex(color)
    elif isinstance(color, str):
        if color.startswith("#"):
            return color
        else:
            # Handle common color names
            color_map = {
                "transparent": "rgba(0,0,0,0)",
                "black": "#000000",
                "white": "#FFFFFF",
                "red": "#FF0000",
                "green": "#00FF00",
                "blue": "#0000FF",
            }
            if color.lower() in color_map:
                return color_map[color.lower()]
            # Assume it's a hex color without #
            return f"#{color}"
    else:
        log.error(f"css_color: Unsupported color type: {type(color)}")
        return "#FFFFFF"


def to_qcolor(color: Any) -> QColor:
    """
    Convert various color formats to QColor.

    Handles hex strings (with or without '#'), QColor objects, and common color names.
    Returns white QColor on error.

    Args:
        color: Color in any supported format (QColor, hex string, color name).

    Returns:
        QColor: QColor object representing the color, or white on error.
    """
    if isinstance(color, QColor):
        return color
    elif isinstance(color, str):
        color_map = {
            "transparent": QColor(0, 0, 0, 0),
            "black": QColor(0, 0, 0),
            "white": QColor(255, 255, 255),
            "red": QColor(255, 0, 0),
            "green": QColor(0, 255, 0),
            "blue": QColor(0, 0, 255),
        }
        if color.lower() in color_map:
            return color_map[color.lower()]
        return hex_to_qcolor(color)
    else:
        log.error(f"to_qcolor: Unsupported color type: {type(color)}")
        return QColor(255, 255, 255)


_GAZE_MARKER_MODES = frozenset({"circle", "hidden"})


def get_gaze_marker_mode() -> str:
    """
    Return the configured gaze marker cursor mode.

    Reads ``display.GAZE_MARKER_MODE`` from config (``"circle"`` or ``"hidden"``).
    Falls back to legacy ``display.ENABLE_GAZE_MARKER`` boolean when the mode key
    is absent.

    Returns:
        str: ``"circle"`` or ``"hidden"``.
    """
    display = load_config().get("display", {})
    mode = display.get("GAZE_MARKER_MODE")
    if mode in _GAZE_MARKER_MODES:
        return mode
    if mode is not None:
        log.warning(
            f"Invalid GAZE_MARKER_MODE '{mode}', expected 'circle' or 'hidden'. "
            "Using 'hidden'."
        )
        return "hidden"
    if display.get("ENABLE_GAZE_MARKER", True):
        return "circle"
    return "hidden"


def _draw_circle_cursor(
    self_widget: QWidget, size: int = 32, circle_radius: int = 12, pen_width: int = 2
) -> None:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor("white"))
    pen.setWidth(pen_width)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    top_left = (size - circle_radius) // 2
    painter.drawEllipse(top_left, top_left, circle_radius, circle_radius)
    painter.end()
    self_widget.setCursor(QCursor(pixmap, size // 2, size // 2))


def set_custom_circle_cursor(self_widget: QWidget, mode: str | None = None) -> None:
    """
    Apply the gaze marker cursor for the specified widget.

    Uses ``display.GAZE_MARKER_MODE`` from config when *mode* is not provided
    (``"circle"`` for a white ring, ``"hidden"`` to hide the cursor).

    Args:
        self_widget (QWidget): Widget to update the cursor for.
        mode (str | None): ``"circle"``, ``"hidden"``, or None to read from config.
    """
    if mode is None:
        mode = get_gaze_marker_mode()
    if mode == "circle":
        _draw_circle_cursor(self_widget)
    elif mode == "hidden":
        self_widget.setCursor(Qt.CursorShape.BlankCursor)
    else:
        log.warning(
            f"Invalid gaze marker mode '{mode}', expected 'circle' or 'hidden'. "
            "Using 'hidden'."
        )
        self_widget.setCursor(Qt.CursorShape.BlankCursor)


def is_raven_device() -> bool:
    """
    Return True iff running on a real Raven device (hardware marker file).

    The marker lives at RAVEN_DEVICE_MARKER_PATH (default
    /data/raven/.is_raven_device), written by deploy.sh on each deploy.
    """
    try:
        return RAVEN_DEVICE_MARKER_PATH.exists()
    except Exception:
        return False


def uses_ravend_ipc() -> bool:
    """
    Return True when code should route peripherals through ravend Unix sockets.

    True if the hardware marker file exists OR RAVEN_DEVICE=1 (set in the
    dev-app Docker container, which cannot read /data/raven/.is_raven_device).
    """
    try:
        if os.environ.get("RAVEN_DEVICE") == "1":
            return True
        return RAVEN_DEVICE_MARKER_PATH.exists()
    except Exception:
        return False
