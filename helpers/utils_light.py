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
import re
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QCursor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from .logger import get_logger

log = get_logger("UtilsLight")

HEX_COLOR_REGEX = re.compile(r"^#?([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$")
RAVEN_DEVICE_MARKER_PATH = Path("/data/raven/.is_raven_device")


def load_config() -> dict:
    """
    Load configuration from config.json file.

    Returns:
        dict: Configuration dictionary loaded from config.json.
    """
    config_path = Path(__file__).parent.parent / "config.json"
    with open(config_path, "r") as f:
        return json.load(f)


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


def set_custom_circle_cursor(
    self_widget: QWidget, size: int = 32, circle_radius: int = 12, pen_width: int = 2
) -> None:
    """
    Set a custom circular cursor for the specified widget.

    Creates a white circular cursor with a transparent background and applies it
    to the widget. The cursor is centered at the hotspot.

    Args:
        self_widget (QWidget): Widget to set the custom cursor for. Must not be None.
        size (int): Size of the cursor pixmap in pixels. Defaults to 32.
        circle_radius (int): Radius of the circular cursor in pixels. Defaults to 12.
        pen_width (int): Width of the cursor pen in pixels. Defaults to 2.

    Raises:
        ValueError: If self_widget is None, or if size, circle_radius, or pen_width are not positive.
    """

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
    cursor = QCursor(pixmap, size // 2, size // 2)
    self_widget.setCursor(cursor)


def is_raven_device() -> bool:
    """
    Check if running on a Raven device by checking for marker file.

    Returns:
        bool: True if running on a Raven device, False otherwise.
    """
    try:
        return RAVEN_DEVICE_MARKER_PATH.exists()
    except Exception as e:
        log.info(f"Raven device marker file not found. Not a Raven device.")
        return False
