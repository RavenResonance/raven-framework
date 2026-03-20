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
Animation utilities for Raven Framework.

This module provides simple animation utility functions for widgets.
"""

from PySide6.QtCore import QPropertyAnimation, QTimer, qInstallMessageHandler
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget

_painter_warning_logged: bool = False
_qt_default_message_handler = None


def _qt_message_handler(msg_type, context, message: str) -> None:
    global _painter_warning_logged
    if (
        "QPainter::begin" in message
        or "QPainter::translate" in message
        or "Painter not active" in message
    ):
        if not _painter_warning_logged:
            _painter_warning_logged = True
            print(message)
        return
    if _qt_default_message_handler is not None:
        _qt_default_message_handler(msg_type, context, message)
    else:
        import sys
        print(message, file=sys.stderr)


def _install_painter_warning_filter() -> None:
    global _qt_default_message_handler
    if _qt_default_message_handler is None:
        _qt_default_message_handler = qInstallMessageHandler(_qt_message_handler)


def _fade_widget(
    widget: QWidget,
    start_value: float,
    end_value: float,
    duration: int,
) -> None:
    """
    Internal helper to fade a widget between opacity values.

    Args:
        widget: The widget to animate.
        start_value: Starting opacity (0.0 to 1.0).
        end_value: Ending opacity (0.0 to 1.0).
        duration: Animation duration in milliseconds.
    """
    if widget is None:
        raise ValueError("Widget cannot be None")

    if not (0.0 <= start_value <= 1.0):
        raise ValueError(f"start_value must be between 0.0 and 1.0, got {start_value}")
    if not (0.0 <= end_value <= 1.0):
        raise ValueError(f"end_value must be between 0.0 and 1.0, got {end_value}")
    if duration < 0:
        raise ValueError(f"duration must be non-negative, got {duration}")

    _install_painter_warning_filter()

    existing_effect = widget.graphicsEffect()
    if isinstance(existing_effect, QGraphicsOpacityEffect):
        effect = existing_effect
    else:
        if existing_effect:
            existing_effect.setParent(None)
            widget.setGraphicsEffect(None)
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)

    effect.setOpacity(start_value)

    def start_animation():
        fade_anim = QPropertyAnimation(effect, b"opacity", widget)
        fade_anim.setStartValue(start_value)
        fade_anim.setEndValue(end_value)
        fade_anim.setDuration(duration)
        fade_anim.start()
        widget._fade_animation = fade_anim

    QTimer.singleShot(0, start_animation)


def fade_in(
    widget: QWidget,
    start_value: float = 0.0,
    end_value: float = 1.0,
    duration: int = 750,
) -> None:
    """
    Fade in a widget from transparent to opaque.

    Note: Call this at the end of widget initialization for best results.
    The animation is deferred to the next event loop to ensure the widget
    is fully laid out before starting.

    Args:
        widget: The widget to fade in.
        start_value: Starting opacity value (0.0 to 1.0). Defaults to 0.0.
        end_value: Ending opacity value (0.0 to 1.0). Defaults to 1.0.
        duration: Animation duration in milliseconds. Defaults to 750.
    """
    _fade_widget(widget, start_value, end_value, duration)


def fade_out(
    widget: QWidget,
    start_value: float = 1.0,
    end_value: float = 0.0,
    duration: int = 750,
) -> None:
    """
    Fade out a widget from opaque to transparent.

    Note: Call this at the end of widget initialization for best results.
    The animation is deferred to the next event loop to ensure the widget
    is fully laid out before starting.

    Args:
        widget: The widget to fade out.
        start_value: Starting opacity value (0.0 to 1.0). Defaults to 1.0.
        end_value: Ending opacity value (0.0 to 1.0). Defaults to 0.0.
        duration: Animation duration in milliseconds. Defaults to 750.
    """
    _fade_widget(widget, start_value, end_value, duration)
