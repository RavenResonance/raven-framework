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
Raven Framework - A comprehensive UI framework and API for
building applications for Raven with PySide6.

This module provides a complete set of UI components, utilities, and tools for creating
interactive applications with support for gaze tracking, voice input, and modern UI patterns.


"""

from typing import Any

from .components.button import Button
from .components.container import Container
from .components.expanding_icon import ExpandingIcon
from .components.horizontal_container import HorizontalContainer
from .components.icon import Icon
from .components.scroll_view import ScrollView
from .components.spacer import Spacer
from .components.text_box import TextBox
from .components.vertical_container import VerticalContainer
from .core.raven_app import RavenApp
from .core.run_app import RunApp
from .helpers import themes

# Essential UI components (always loaded - lightweight)
from .helpers.animation_utils import fade_in, fade_out
from .helpers.async_runner import AsyncRunner
from .helpers.logger import *
from .helpers.routine import Routine
from .helpers.themes import *
from .helpers.utils_light import *


def __getattr__(name: str) -> Any:
    """
    Lazy load heavy components and utilities on first access.

    This function implements lazy loading for components that have heavy dependencies
    (like OpenCV, NumPy, WebKit) or require network access. Components are only imported
    when they are first accessed, improving initial import time.

    Args:
        name (str): Name of the attribute to load.

    Returns:
        Any: The requested component or utility function.

    Raises:
        AttributeError: If the requested attribute is not available.

    Lazy-loaded components:
        - Heavy utilities: convert_ndarray_to_pixmap_image, convert_ndarray_to_base64_image,
          get_frame_from_video, base64_to_image, image_to_base64
        - Heavy UI components: WebViewer, OpenAiHelper, MediaViewer, ModelViewer
        - Peripherals: Camera, Microphone, Speaker, IMU, EyeTracker, ClickButton
    """
    # Heavy utilities (OpenCV/NumPy functions only)
    heavy_utils = [
        "convert_ndarray_to_pixmap_image",
        "convert_ndarray_to_base64_image",
        "get_frame_from_video",
        "base64_to_image",
        "image_to_base64",
    ]
    if name in heavy_utils:
        from .helpers import utils

        return getattr(utils, name)

    # Heavy UI components - lazy loaded
    if name == "WebViewer":
        from .components.web_viewer import WebViewer

        return WebViewer
    elif name == "OpenAiHelper":
        from .helpers.open_ai_helper import OpenAiHelper

        return OpenAiHelper
    elif name == "MediaViewer":
        from .components.media_viewer import MediaViewer

        return MediaViewer
    elif name == "ModelViewer":
        from .components.model_viewer import ModelViewer

        return ModelViewer

    # Peripherals - lazy loaded for performance
    elif name == "Camera":
        from .peripherals.camera import Camera

        return Camera
    elif name == "Microphone":
        from .peripherals.microphone import Microphone

        return Microphone

    elif name == "Speaker":
        from .peripherals.speaker import Speaker

        return Speaker
    elif name == "IMU":
        from .peripherals.imu import IMU

        return IMU
    elif name == "EyeTracker":
        from .peripherals.eye_tracker import EyeTracker

        return EyeTracker
    elif name == "ClickButton":
        from .peripherals.click_button import ClickButton

        return ClickButton

    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    # Core UI components (always loaded)
    "AsyncRunner",
    "fade_in",
    "fade_out",
    "Button",
    "Container",
    "ExpandingIcon",
    "HorizontalContainer",
    "Icon",
    "RavenApp",
    "Routine",
    "RunApp",
    "ScrollView",
    "Spacer",
    "TextBox",
    "VerticalContainer",
    # Lazy loaded components
    "Camera",
    "EyeTracker",
    "IMU",
    "MediaViewer",
    "Microphone",
    "ModelViewer",
    "OpenAiHelper",
    "ClickButton",
    "Speaker",
    "WebViewer",
    "convert_ndarray_to_pixmap_image",
    "convert_ndarray_to_base64_image",
    "get_frame_from_video",
    "base64_to_image",
    "image_to_base64",
]
