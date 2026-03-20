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
Helper utilities for the Raven Framework.
Import from here for a cleaner API, e.g.:
  from raven_framework.helpers import Routine, get_logger, fade_in, fade_out, RAVEN_CORE
"""

from typing import Any

from .animation_utils import fade_in, fade_out
from .async_runner import AsyncRunner
from .logger import get_logger
from .routine import Routine
from .themes import (
    RAVEN_CORE,
    Borders,
    BrandColors,
    Colors,
    Font,
    Fonts,
    FontSizes,
    Palette,
    RavenTheme,
)
from .utils_light import (
    css_color,
    hex_to_qcolor,
    is_raven_device,
    load_config,
    pascal_to_snake,
    qcolor_to_hex,
    set_custom_circle_cursor,
    snake_to_pascal_case,
    snake_to_spaced_pascal,
    spaced_pascal_to_snake,
    to_qcolor,
)


def __getattr__(name: str) -> Any:
    """Lazy load heavy helpers (OpenAiHelper, utils with OpenCV/NumPy) on first access."""
    if name == "OpenAiHelper":
        from .open_ai_helper import OpenAiHelper

        return OpenAiHelper
    heavy_utils = [
        "convert_ndarray_to_pixmap_image",
        "convert_ndarray_to_base64_image",
        "get_frame_from_video",
        "base64_to_image",
        "image_to_base64",
    ]
    if name in heavy_utils:
        from . import utils

        return getattr(utils, name)
    if name in (
        "load_font_family",
        "get_system_default_font_family",
        "get_font_family_name",
        "preload_fonts",
        "create_font",
    ):
        from . import font_utils

        return getattr(font_utils, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    "AsyncRunner",
    "Borders",
    "BrandColors",
    "Colors",
    "Font",
    "FontSizes",
    "Fonts",
    "Palette",
    "RAVEN_CORE",
    "RavenTheme",
    "Routine",
    "css_color",
    "fade_in",
    "fade_out",
    "get_logger",
    "hex_to_qcolor",
    "is_raven_device",
    "load_config",
    "pascal_to_snake",
    "qcolor_to_hex",
    "set_custom_circle_cursor",
    "snake_to_pascal_case",
    "snake_to_spaced_pascal",
    "spaced_pascal_to_snake",
    "to_qcolor",
    "OpenAiHelper",
    "convert_ndarray_to_pixmap_image",
    "convert_ndarray_to_base64_image",
    "get_frame_from_video",
    "base64_to_image",
    "image_to_base64",
]
