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
UI components for the Raven Framework.
Import from here for a cleaner API, e.g.:
  from raven_framework.components import VerticalContainer, Container, TextBox, ScrollView, MediaViewer
"""

from typing import Any

from .button import Button
from .container import Container
from .expanding_icon import ExpandingIcon
from .horizontal_container import HorizontalContainer
from .icon import Icon
from .scroll_view import ScrollView
from .spacer import Spacer
from .text_box import TextBox
from .vertical_container import VerticalContainer


def __getattr__(name: str) -> Any:
    """Lazy load heavy components (MediaViewer, WebViewer, ModelViewer) on first access."""
    if name == "MediaViewer":
        from .media_viewer import MediaViewer

        return MediaViewer
    if name == "WebViewer":
        from .web_viewer import WebViewer

        return WebViewer
    if name == "ModelViewer":
        from .model_viewer import ModelViewer

        return ModelViewer
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    "Button",
    "Container",
    "ExpandingIcon",
    "HorizontalContainer",
    "Icon",
    "MediaViewer",
    "ModelViewer",
    "ScrollView",
    "Spacer",
    "TextBox",
    "VerticalContainer",
    "WebViewer",
]
