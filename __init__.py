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
interactive applications with support for gaze-based input, voice input, and modern UI patterns.


"""

from importlib import import_module
from typing import Any

# Only the truly light (no-Qt) helpers are eager. Everything that pulls in
# PySide6 — the UI components, RavenApp/RunApp, animation_utils, AsyncRunner,
# Routine — is loaded lazily via __getattr__ so that importing raven_framework
# (or its light helpers) does NOT load Qt. This keeps non-UI consumers
# (manager, subprocess_manager, admin_client) Qt-free and their memory small.
from .helpers import themes
from .helpers.logger import *
from .helpers.themes import *
from .helpers.utils_light import *

# name -> component submodule (under .components), loaded on first access
_COMPONENTS = {
    "Button": "button",
    "Container": "container",
    "ExpandingIcon": "icon",
    "HorizontalContainer": "horizontal_container",
    "Icon": "icon",
    "RevealIcon": "icon",
    "ScrollView": "scroll_view",
    "Spacer": "spacer",
    "TextBox": "text_box",
    "VerticalContainer": "vertical_container",
}
_ANIMATION_EXPORTS = {
    "RavenCurve",
    "fade_in",
    "fade_out",
    "make_property_animation",
    "resolve_curve",
}


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
        - Peripherals: Camera, Microphone, Speaker, IMU, EyeControl, ClickButton, HandGestureDetector
    """
    # UI components (Qt-backed) — deferred so the light import path stays Qt-free
    if name in _COMPONENTS:
        module = import_module(f".components.{_COMPONENTS[name]}", __name__)
        return getattr(module, name)
    if name == "RavenApp":
        from .core.raven_app import RavenApp

        return RavenApp
    if name == "RunApp":
        from .core.run_app import RunApp

        return RunApp
    if name in _ANIMATION_EXPORTS:
        from .helpers import animation_utils

        return getattr(animation_utils, name)
    if name == "AsyncRunner":
        from .helpers.async_runner import AsyncRunner

        return AsyncRunner
    if name == "Routine":
        from .helpers.routine import Routine

        return Routine

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
    elif name == "EyeControl":
        from .peripherals.eye_control import EyeControl

        return EyeControl
    elif name == "HandGestureDetector":
        from .helpers.hand_gesture import HandGestureDetector

        return HandGestureDetector
    elif name == "ClickButton":
        from .peripherals.click_button import ClickButton

        return ClickButton
    elif name == "StorageManager":
        from .storage import StorageManager

        return StorageManager

    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    # Core UI components (always loaded)
    "AsyncRunner",
    "RavenCurve",
    "fade_in",
    "fade_out",
    "make_property_animation",
    "resolve_curve",
    "Button",
    "Container",
    "ExpandingIcon",
    "HorizontalContainer",
    "Icon",
    "RavenApp",
    "RevealIcon",
    "Routine",
    "RunApp",
    "ScrollView",
    "Spacer",
    "TextBox",
    "VerticalContainer",
    # Lazy loaded components
    "Camera",
    "EyeControl",
    "HandGestureDetector",
    "IMU",
    "MediaViewer",
    "Microphone",
    "ModelViewer",
    "OpenAiHelper",
    "ClickButton",
    "Speaker",
    "StorageManager",
    "WebViewer",
    "convert_ndarray_to_pixmap_image",
    "convert_ndarray_to_base64_image",
    "get_frame_from_video",
    "base64_to_image",
    "image_to_base64",
]
