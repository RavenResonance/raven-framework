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

Font loading and creation with pixel-based sizes (no DPI or device scaling).
"""

import os
from typing import Dict

from PySide6.QtGui import QFont, QFontDatabase

from .logger import get_logger

log = get_logger("FontUtils")

_loaded_fonts: Dict[str, bool] = {}

_font_family_names: Dict[str, str] = {}

_font_cache: Dict[tuple, QFont] = {}


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


def preload_fonts() -> None:
    """
    Preload all available fonts to avoid loading during paint events.
    This should be called once at application startup for best performance.
    """
    load_font_family("libre_franklin")
    load_font_family("inter")


def create_font(font: str, font_size: int, font_weight: str = "normal") -> QFont:
    """
    Create a QFont with the given family, pixel size, and weight.
    Size is in pixels; no DPI or device scaling is applied so 28 means 28px.

    Args:
        font (str): Font family name ('libre_franklin', 'inter').
        font_size (int): Font size in pixels.
        font_weight (str): Font weight ('light', 'normal', 'medium', 'bold', 'black').

    Returns:
        QFont: Configured QFont with the requested pixel size.
    """
    cache_key = (font, font_size, font_weight)
    if cache_key in _font_cache:
        return _font_cache[cache_key]

    valid_fonts = ["libre_franklin", "inter"]
    if font not in valid_fonts:
        log.warning(
            f"Font '{font}' not available. Valid options are: {valid_fonts}. Using system default."
        )
        font_family_name = get_system_default_font_family()
    else:
        font_loaded = load_font_family(font)
        if not font_loaded:
            log.warning(
                f"Failed to load font '{font}'. Falling back to system default."
            )
            font_family_name = get_system_default_font_family()
        else:
            font_family_name = get_font_family_name(font)

    weight_map = {
        "light": QFont.Light,
        "normal": QFont.Normal,
        "medium": QFont.Medium,
        "bold": QFont.Bold,
        "black": QFont.Black,
    }
    weight_value = weight_map.get(font_weight.lower(), QFont.Normal)

    font_obj = QFont(font_family_name)
    font_obj.setPixelSize(font_size)
    font_obj.setWeight(weight_value)

    _font_cache[cache_key] = font_obj
    return font_obj


__all__ = [
    "load_font_family",
    "get_font_family_name",
    "create_font",
    "preload_fonts",
]
