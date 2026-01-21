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
Font utilities for Raven Framework.

This module provides font loading, device detection, and scaling functionality
for consistent typography across different platforms and devices.
"""

import json
import os
import platform
from enum import Enum
from pathlib import Path
from typing import Dict

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from .logger import get_logger

log = get_logger("FontUtils")


def load_config() -> dict:
    """
    Load configuration from config.json file.

    Returns:
        dict: Configuration dictionary loaded from config.json.
    """
    config_path = Path(__file__).parent.parent / "config.json"
    with open(config_path, "r") as f:
        return json.load(f)


# Load configuration
_config = load_config()
STANDARD_DPI = _config["display"]["STANDARD_DPI"]

_loaded_fonts: Dict[str, bool] = {}

_font_family_names: Dict[str, str] = {}

_font_cache: Dict[tuple, QFont] = {}


class DeviceType(str, Enum):
    """Device type enumeration for font scaling."""

    DARWIN = "darwin"
    LINUX = "linux"
    WINDOWS = "windows"
    DEFAULT = "default"


# Device-specific font scaling factors, to be updated based on the actual display size and DPI
_device_font_scales = {
    DeviceType.DARWIN: 1.0,  # Darwin/macOS (reference)
    DeviceType.LINUX: 0.8,  # Linux (scale down for consistent appearance)
    DeviceType.WINDOWS: 1.0,  # Windows
    DeviceType.DEFAULT: 1.0,
}


def detect_device_type() -> DeviceType:
    """
    Detect the current device type for font scaling.

    Returns:
        DeviceType: Device type enum value
    """
    try:
        system = platform.system().lower()
        system_to_device = {
            "linux": DeviceType.LINUX,
            "darwin": DeviceType.DARWIN,
            "windows": DeviceType.WINDOWS,
        }
        return system_to_device.get(system, DeviceType.DEFAULT)

    except Exception as e:
        log.warning(f"Error detecting device type: {e}, using default")
        return DeviceType.DEFAULT


def get_device_font_scale() -> float:
    """
    Get the font scaling factor for the current device.

    Returns:
        float: Font scaling factor (1.0 = no scaling)
    """
    device_type = detect_device_type()
    scale = _device_font_scales.get(
        device_type, _device_font_scales[DeviceType.DEFAULT]
    )
    return scale


def get_dpi_scale() -> float:
    """
    Get DPI-based scaling factor from Qt.

    Returns:
        float: DPI scaling factor
    """
    try:
        if QApplication.instance() is not None:
            screen = QApplication.primaryScreen()
            if screen:
                dpi = screen.logicalDotsPerInch()
                if dpi == 0:
                    error_msg = "Division by zero: dpi is 0, cannot calculate DPI scale"
                    log.error(error_msg, extra={"console": True})
                    raise ValueError(error_msg)
                return dpi / STANDARD_DPI
    except Exception as e:
        log.warning(f"Error getting DPI scale: {e}")

    return 1.0


def get_combined_font_scale() -> float:
    """
    Get the combined scaling factor (device + DPI).
    On Mac, only use device scaling to maintain reference appearance.

    Returns:
        float: Combined font scaling factor
    """
    device_scale = get_device_font_scale()
    device_type = detect_device_type()

    if device_type == DeviceType.DARWIN:
        combined_scale = device_scale
    else:
        dpi_scale = get_dpi_scale()
        combined_scale = device_scale * dpi_scale

    return combined_scale


def load_font_family(font_name: str) -> bool:
    """
    Load a font family into QFontDatabase.

    Args:
        font_name (str): Name of the font family ('libre_franklin', 'inter').

    Returns:
        bool: True if fonts loaded successfully, False otherwise.
    """
    if font_name in _loaded_fonts:
        return _loaded_fonts[font_name]

    try:
        # Get the raven_framework directory (parent of helpers)
        current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        if font_name == "libre_franklin":
            font_dir = os.path.join(current_dir, "fonts", "Libre Franklin")
            font_files = [
                "LibreFranklin-Thin.ttf",
                "LibreFranklin-ExtraLight.ttf",
                "LibreFranklin-Light.ttf",
                "LibreFranklin-Regular.ttf",
                "LibreFranklin-Medium.ttf",
                "LibreFranklin-SemiBold.ttf",
                "LibreFranklin-Bold.ttf",
                "LibreFranklin-ExtraBold.ttf",
                "LibreFranklin-Black.ttf",
            ]
            family_name = "Libre Franklin"
        elif font_name == "inter":
            font_dir = os.path.join(current_dir, "fonts", "Inter", "static")
            font_files = [
                "Inter_24pt-Thin.ttf",
                "Inter_24pt-ExtraLight.ttf",
                "Inter_24pt-Light.ttf",
                "Inter_24pt-Regular.ttf",
                "Inter_24pt-Medium.ttf",
                "Inter_24pt-SemiBold.ttf",
                "Inter_24pt-Bold.ttf",
                "Inter_24pt-ExtraBold.ttf",
                "Inter_24pt-Black.ttf",
            ]
            family_name = "Inter"
        else:
            log.error(f"Unknown font family: {font_name}")
            return False

        if not os.path.exists(font_dir):
            log.warning(
                f"{family_name} font directory not found: {font_dir}, will use default fonts"
            )
            return False

        loaded_count = 0
        actual_family_name = None
        font_db = QFontDatabase()

        for font_file in font_files:
            font_path = os.path.join(font_dir, font_file)
            if os.path.exists(font_path):
                font_id = QFontDatabase.addApplicationFont(font_path)
                if font_id != -1:
                    loaded_count += 1
                    families = QFontDatabase.applicationFontFamilies(font_id)
                    if families and not actual_family_name:
                        actual_family_name = families[0]
                        log.info(
                            f"Registered {family_name} font family as: {actual_family_name}"
                        )
                else:
                    log.warning(f"Failed to load font: {font_file}")
            else:
                log.warning(f"Font file not found: {font_path}")

        if loaded_count > 0:
            if loaded_count < len(font_files):
                log.warning(
                    f"Loaded {loaded_count}/{len(font_files)} {family_name} font variants"
                )

            if actual_family_name:
                _font_family_names[font_name] = actual_family_name
            else:
                _font_family_names[font_name] = family_name
                log.warning(
                    f"Could not determine actual font family name for {font_name}, using expected name: {family_name}"
                )

            _loaded_fonts[font_name] = True
            log.info(
                f"Loaded {font_name} font family as: {actual_family_name}",
                extra={"console": True},
            )
            return True
        else:
            log.error(
                f"Failed to load any {family_name} fonts", extra={"console": True}
            )
            _loaded_fonts[font_name] = False
            return False

    except Exception as e:
        log.error(f"Error loading {font_name} fonts: {e}", exc_info=True)
        _loaded_fonts[font_name] = False
        return False


def get_system_default_font_family() -> str:
    """
    Get the system default font family name.
    Queries Qt for the actual system default font to avoid font alias resolution overhead.

    Returns:
        str: The actual system default font family name (e.g., "Helvetica" on macOS)
    """
    try:
        system_font = QFont()
        font_family = system_font.family()
        if font_family:
            log.info(
                f"System default font family: {font_family}", extra={"console": True}
            )
            return font_family
    except Exception as e:
        log.warning(
            f"Error getting system default font: {e}, falling back to Helvetica",
            extra={"console": True},
        )


def get_font_family_name(font_name: str) -> str:
    """
    Get the actual font family name for Qt font creation.
    Uses the cached family name that Qt actually registered after loading.

    Args:
        font_name (str): Font name ('libre_franklin', 'inter').

    Returns:
        str: The actual font family name for Qt.
    """
    # Check if we have the actual registered family name
    if font_name in _font_family_names:
        return _font_family_names[font_name]

    # Fallback to expected names if not yet loaded
    if font_name == "libre_franklin":
        return "Libre Franklin"
    elif font_name == "inter":
        return "Inter"
    else:
        log.warning(f"Unknown font family: {font_name}, falling back to system default")
        return get_system_default_font_family()


def set_device_font_scale(device_type: DeviceType, scale: float) -> None:
    """
    Override the font scaling factor for a specific device type.

    Args:
        device_type (DeviceType): Device type enum value
        scale (float): Font scaling factor
    """
    if device_type in _device_font_scales:
        _device_font_scales[device_type] = scale
        log.info(f"Set font scale for {device_type.value} to {scale}")
    else:
        log.warning(f"Unknown device type: {device_type}")


def get_current_device_info() -> dict:
    """
    Get information about the current device and scaling factors.

    Returns:
        dict: Device information including type, scales, and DPI
    """
    device_type = detect_device_type()
    device_scale = get_device_font_scale()
    dpi_scale = get_dpi_scale()
    combined_scale = get_combined_font_scale()

    return {
        "device_type": device_type.value,
        "device_scale": device_scale,
        "dpi_scale": dpi_scale,
        "combined_scale": combined_scale,
        "platform": platform.system(),
        "machine": platform.machine(),
    }


def preload_fonts() -> None:
    """
    Preload all available fonts to avoid loading during paint events.
    This should be called once at application startup for best performance.
    """
    load_font_family("libre_franklin")
    load_font_family("inter")


def create_font(font: str, font_size: int, font_weight: str = "normal") -> QFont:
    """
    Create a QFont object with the specified font family, size, and weight.
    Automatically applies device-specific scaling for consistent appearance across platforms.

    Args:
        font (str): Font family name ('libre_franklin', 'inter').
        font_size (int): Font size in points (will be scaled for device).
        font_weight (str): Font weight ('light', 'normal', 'medium', 'bold', 'black').

    Returns:
        QFont: Configured QFont object with device-appropriate scaling.
    """
    # Apply device-specific scaling
    scale_factor = get_combined_font_scale()
    scaled_font_size = int(font_size * scale_factor)

    # Check cache first (use scaled size for cache key)
    cache_key = (font, scaled_font_size, font_weight)
    if cache_key in _font_cache:
        return _font_cache[cache_key]

    # Validate font
    valid_fonts = ["libre_franklin", "inter"]
    if font not in valid_fonts:
        log.warning(
            f"Font '{font}' not available. Valid options are: {valid_fonts}. Using system default."
        )
        font_family_name = get_system_default_font_family()
    else:
        # Load the specified font family
        font_loaded = load_font_family(font)
        if not font_loaded:
            log.warning(
                f"Failed to load font '{font}'. Falling back to system default."
            )
            font_family_name = get_system_default_font_family()
        else:
            font_family_name = get_font_family_name(font)

    # Map font weight strings to QFont constants
    weight_map = {
        "light": QFont.Light,
        "normal": QFont.Normal,
        "medium": QFont.Medium,
        "bold": QFont.Bold,
        "black": QFont.Black,
    }
    weight_value = weight_map.get(font_weight.lower(), QFont.Normal)

    # Create font with the scaled size
    font_obj = QFont(font_family_name, scaled_font_size, weight_value)

    # Cache the font object
    _font_cache[cache_key] = font_obj
    return font_obj


# Export the new functions for external use
__all__ = [
    "DeviceType",
    "load_font_family",
    "get_font_family_name",
    "create_font",
    "preload_fonts",
    "detect_device_type",
    "get_device_font_scale",
    "get_dpi_scale",
    "get_combined_font_scale",
    "set_device_font_scale",
    "get_current_device_info",
]
