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

Centralizes animation curve types and property-animation helpers used across UI components.
"""

from enum import Enum
from typing import Any, Optional, Union

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QObject,
    QPauseAnimation,
    QPropertyAnimation,
    QTimer,
    qInstallMessageHandler,
)
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget

from .utils_light import load_config

_painter_warning_logged: bool = False
_qt_default_message_handler = None


class RavenCurve(Enum):
    """Qt animation curves exposed as a stable Raven API."""

    LINEAR = QEasingCurve.Type.Linear
    IN_QUAD = QEasingCurve.Type.InQuad
    OUT_QUAD = QEasingCurve.Type.OutQuad
    IN_OUT_QUAD = QEasingCurve.Type.InOutQuad
    IN_CUBIC = QEasingCurve.Type.InCubic
    OUT_CUBIC = QEasingCurve.Type.OutCubic
    IN_OUT_CUBIC = QEasingCurve.Type.InOutCubic
    IN_QUART = QEasingCurve.Type.InQuart
    OUT_QUART = QEasingCurve.Type.OutQuart
    IN_OUT_QUART = QEasingCurve.Type.InOutQuart
    IN_QUINT = QEasingCurve.Type.InQuint
    OUT_QUINT = QEasingCurve.Type.OutQuint
    IN_OUT_QUINT = QEasingCurve.Type.InOutQuint
    IN_SINE = QEasingCurve.Type.InSine
    OUT_SINE = QEasingCurve.Type.OutSine
    IN_OUT_SINE = QEasingCurve.Type.InOutSine
    IN_EXPO = QEasingCurve.Type.InExpo
    OUT_EXPO = QEasingCurve.Type.OutExpo
    IN_OUT_EXPO = QEasingCurve.Type.InOutExpo
    IN_CIRC = QEasingCurve.Type.InCirc
    OUT_CIRC = QEasingCurve.Type.OutCirc
    IN_OUT_CIRC = QEasingCurve.Type.InOutCirc
    IN_ELASTIC = QEasingCurve.Type.InElastic
    OUT_ELASTIC = QEasingCurve.Type.OutElastic
    IN_OUT_ELASTIC = QEasingCurve.Type.InOutElastic
    IN_BACK = QEasingCurve.Type.InBack
    OUT_BACK = QEasingCurve.Type.OutBack
    IN_OUT_BACK = QEasingCurve.Type.InOutBack
    IN_BOUNCE = QEasingCurve.Type.InBounce
    OUT_BOUNCE = QEasingCurve.Type.OutBounce
    IN_OUT_BOUNCE = QEasingCurve.Type.InOutBounce

    def to_qt(self) -> QEasingCurve.Type:
        return self.value

    @classmethod
    def from_name(
        cls, name: str, *, default: "RavenCurve" = IN_OUT_SINE
    ) -> "RavenCurve":
        key = name.strip().upper().replace("-", "_").replace(" ", "_")
        return cls.__members__.get(key, default)


RavenCurveLike = Union[RavenCurve, str]

_anim_cfg = load_config()["animation"]
DEFAULT_CURVE = RavenCurve.from_name(_anim_cfg["DEFAULT_CURVE"])
_fade_cfg = _anim_cfg["fade"]
DEFAULT_FADE_CURVE = RavenCurve.from_name(_fade_cfg["CURVE"], default=DEFAULT_CURVE)
DEFAULT_FADE_DURATION_MS = int(_fade_cfg["DURATION_MS"])


def resolve_curve(
    curve: RavenCurveLike,
    *,
    default: RavenCurve = DEFAULT_CURVE,
) -> RavenCurve:
    if isinstance(curve, RavenCurve):
        return curve
    return RavenCurve.from_name(curve, default=default)


def apply_curve(animation: QAbstractAnimation, curve: RavenCurveLike) -> None:
    resolved = resolve_curve(curve)
    if isinstance(animation, QPropertyAnimation):
        animation.setEasingCurve(resolved.to_qt())


def make_property_animation(
    target: QObject,
    property_name: bytes,
    start_value: Any,
    end_value: Any,
    duration_ms: int,
    curve: RavenCurveLike = DEFAULT_CURVE,
    parent: Optional[QObject] = None,
) -> QPropertyAnimation:
    """Create a configured QPropertyAnimation."""
    anim = QPropertyAnimation(target, property_name, parent or target)
    anim.setDuration(max(0, int(duration_ms)))
    anim.setStartValue(start_value)
    anim.setEndValue(end_value)
    apply_curve(anim, curve)
    return anim


def configure_property_animation(
    animation: QPropertyAnimation,
    start_value: Any,
    end_value: Any,
    duration_ms: int,
    curve: RavenCurveLike = DEFAULT_CURVE,
) -> QPropertyAnimation:
    """Reconfigure an existing QPropertyAnimation."""
    animation.setDuration(max(0, int(duration_ms)))
    animation.setStartValue(start_value)
    animation.setEndValue(end_value)
    apply_curve(animation, curve)
    return animation


def make_pause_animation(
    duration_ms: int,
    parent: Optional[QObject] = None,
) -> QPauseAnimation:
    """Create a pause step for sequential animation groups."""
    return QPauseAnimation(max(0, int(duration_ms)), parent)


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
    duration_ms: int,
    curve: RavenCurveLike = DEFAULT_FADE_CURVE,
) -> None:
    if widget is None:
        raise ValueError("Widget cannot be None")

    if not (0.0 <= start_value <= 1.0):
        raise ValueError(f"start_value must be between 0.0 and 1.0, got {start_value}")
    if not (0.0 <= end_value <= 1.0):
        raise ValueError(f"end_value must be between 0.0 and 1.0, got {end_value}")
    if duration_ms < 0:
        raise ValueError(f"duration_ms must be non-negative, got {duration_ms}")

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
    resolved_curve = resolve_curve(curve)

    def start_animation() -> None:
        fade_anim = make_property_animation(
            effect,
            b"opacity",
            start_value,
            end_value,
            duration_ms,
            resolved_curve,
            widget,
        )
        fade_anim.start()
        widget._fade_animation = fade_anim

    QTimer.singleShot(0, start_animation)


def fade_in(
    widget: QWidget,
    start_value: float = 0.0,
    end_value: float = 1.0,
    duration: int = DEFAULT_FADE_DURATION_MS,
    curve: RavenCurveLike = DEFAULT_FADE_CURVE,
) -> None:
    """Fade in a widget from transparent to opaque."""
    _fade_widget(widget, start_value, end_value, duration, curve)


def fade_out(
    widget: QWidget,
    start_value: float = 1.0,
    end_value: float = 0.0,
    duration: int = DEFAULT_FADE_DURATION_MS,
    curve: RavenCurveLike = DEFAULT_FADE_CURVE,
) -> None:
    """Fade out a widget from opaque to transparent."""
    _fade_widget(widget, start_value, end_value, duration, curve)
