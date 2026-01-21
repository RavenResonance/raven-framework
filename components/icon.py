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
Icon widget for Raven Framework.

This module provides a customizable icon widget with dwell-to-click functionality,
scaling animations, support for circular and rounded-rectangular shapes, and
optional bottom text display.
"""

# Standard library imports
import json
import math
import os
import platform
from functools import partial
from pathlib import Path
from typing import Any, Callable, Optional

# PySide6 imports
from PySide6.QtCore import QEvent, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QEnterEvent,
    QFontMetrics,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QWidget

# Local imports
from ..helpers.font_utils import create_font
from ..helpers.logger import get_logger
from ..helpers.themes import RAVEN_CORE
from ..helpers.utils_light import load_config, to_qcolor

theme = RAVEN_CORE

log = get_logger("Icon")

# Load configuration
_config = load_config()

# Constants
DEFAULT_EXTRA_HEIGHT = 140  # Max height in pixels for bottom text area
DEFAULT_EXTRA_WIDTH = 10  # Max width in pixels for bottom text area
SCALE_THRESHOLD = 0.005  # Threshold for scale animation completion
DEFAULT_MAX_WORD_LEN = 8  # Maximum word length before hyphenation
QT_DEGREES_TO_UNITS = _config["display"]["QT_DEGREES_TO_UNITS"]
MAX_PROGRESS = 100.0  # Maximum progress value for dwell-click (percentage)
ICON_FPS = _config["fps"]["UI_FPS"]


class Icon(QWidget):
    """
    A customizable UI widget that displays a circular or rounded-rect icon with
    dwell-click interaction, background image, scaling animation, and optional bottom text.

    Signals:
        clicked: Emitted when the icon is clicked or dwell-clicked.

    Args:
        background_image_path (Optional[str]): Path to a background image rendered inside the icon. Defaults to None.
        size (int): Width and height of the icon (square). Defaults to 80.
        background_color (str): Fill color of the icon background as string. Defaults to theme.basic_palette.gray.
        center_text (str): Text to display in the center of the icon. Defaults to "".
        text_size (int): Font size of the center text. Defaults to theme.fonts.body.size.
        text_color (str): Color of the center text as string. Defaults to theme.fonts.body.color.
        font (str): Font family ('libre_franklin'). Defaults to theme.fonts.body.family.
        font_weight (str): Font weight, one of 'light', 'normal', 'medium', 'bold', or 'black'. Defaults to theme.fonts.body.weight.
        corner_radius (int): Corner curvature for rounded-rect mode. Defaults to theme.borders.corner_radius.
        outline_width (int): Width of the circular/rectangular outline stroke. Defaults to 6.
        outline_color (str): Color of the circular/rectangular outline stroke as string. Defaults to theme.borders.highlight_color_icon.
        scale_by (float): Scaling offset used for hover animation (e.g., 0.1 for 10% shrinkage). Defaults to 0.1.
        scale_step (float): Increment step of scaling per frame. Defaults to 0.01.
        fps (int): Frames per second for animation timers.
        delay_time (int): Delay time in milliseconds before starting animations. Defaults to 500.
        dwell_time (int): Time in milliseconds required to trigger a click on hover. Defaults to 1500.
        background_outline_color (str): Outline color shown on hover (rounded rect mode) as string. Defaults to theme.basic_palette.gray.
        is_square (bool): Whether to use a rounded rectangle (True) or circle (False). Defaults to False.
        enable_click (bool): Whether to allow dwell-based clicking. Defaults to True.
        enable_hover_sound (bool): Enable audio feedback on hover. Defaults to True. Disabled on Linux.
        enable_click_sound (bool): Enable audio feedback on click. Defaults to True. Disabled on Linux.
        bottom_text (str): Optional text displayed below the icon. Defaults to "".
        disabled (bool): If True, icon is disabled and won't respond to clicks or hover. Defaults to False.
    """

    clicked = Signal()

    def __init__(
        self,
        background_image_path: Optional[str] = None,
        size: int = 80,
        background_color: str = theme.basic_palette.black,
        center_text: str = "",
        text_size: int = theme.fonts.body.size,
        text_color: str = theme.fonts.body.color,
        font: str = theme.fonts.body.family,
        font_weight: str = theme.fonts.body.weight,
        corner_radius: int = theme.borders.corner_radius,
        outline_width: int = theme.borders.highlight_width + 2,
        outline_color: str = theme.borders.highlight_color_icon,
        scale_by: float = 0.1,
        scale_step: float = 0.01,
        fps: int = ICON_FPS,
        delay_time: int = 500,
        dwell_time: int = 1500,
        background_outline_color: str = theme.basic_palette.gray,
        is_square: bool = False,
        enable_click: bool = True,
        enable_hover_sound: bool = False,
        enable_click_sound: bool = False,
        bottom_text: str = "",
        disabled: bool = False,
    ) -> None:
        """
        Initialize the Icon widget.

        See class docstring for parameter descriptions.
        """
        super().__init__()

        self.is_square: bool = is_square
        self.size: int = int(size)
        self.corner_radius: float = (
            float(corner_radius) if corner_radius is not None else self.size / 4
        )
        self.full_diameter: int = self.size
        self.enable_click: bool = enable_click
        self.enable_hover_sound: bool = enable_hover_sound
        self.enable_click_sound: bool = enable_click_sound
        self.disabled: bool = disabled

        # Visual properties
        self.color: QColor = to_qcolor(background_color)
        self.text: str = center_text
        self.text_size: int = int(text_size)
        self.text_color: QColor = to_qcolor(text_color)
        self.font: str = font
        self.font_weight: str = font_weight
        self.outline_width: int = int(outline_width)
        self.outline_color: QColor = to_qcolor(outline_color)
        self.outline_color_bg: QColor = to_qcolor(background_outline_color)
        self.bottom_text: str = bottom_text
        self.bottom_text_visible: bool = bool(bottom_text)
        self.delay_time = delay_time

        # Image loading
        try:
            self.bg_image: Optional[QPixmap] = (
                QPixmap(background_image_path) if background_image_path else None
            )
        except Exception as e:
            self.bg_image = None
            log.error(f"Error loading background image: {e}")

        # Scaling properties
        self.start_at_scale: float = 1.0 - scale_by
        self.scale: float = self.start_at_scale
        self.target_scale: float = self.start_at_scale
        self.scale_step: float = scale_step

        # Set fixed size considering optional bottom text height
        extra_height = DEFAULT_EXTRA_HEIGHT if self.bottom_text else 0
        extra_width = DEFAULT_EXTRA_WIDTH if self.bottom_text else 0
        self.setFixedSize(self.size + extra_width, self.size + extra_height)

        # Timing and progress
        self.fps: int = int(fps)
        if self.fps == 0:
            error_msg = "Division by zero: fps is 0, cannot calculate timer interval"
            log.error(error_msg, extra={"console": True})
            raise ValueError(error_msg)
        self.progress: float = 0.0
        self.max_progress: float = MAX_PROGRESS
        if fps > 0 and dwell_time > 0:
            self.progress_increment: float = self.max_progress / (
                dwell_time / (1000.0 / fps)
            )
        else:
            log.warning("Invalid fps or dwell_time, setting progress_increment to 1.0")
            self.progress_increment = 1.0

        self.delay_progress = 0.0
        self.max_delay_progress = MAX_PROGRESS

        if fps > 0 and self.delay_time > 0:
            self.delay_progress_increment = self.max_delay_progress / (
                self.delay_time / (1000.0 / self.fps)
            )
        else:
            log.warning(
                "Invalid fps or delay_time, setting delay_progress_increment to 1.0"
            )
            self.delay_progress_increment = 1.0

        # Timers
        timer_interval = int(1000 / self.fps)
        self.delay_timer = QTimer(self)
        self.delay_timer.setInterval(timer_interval)
        self.delay_timer.timeout.connect(self.update_delay_progress)

        self.progress_timer = QTimer(self)
        self.progress_timer.setInterval(timer_interval)
        self.progress_timer.timeout.connect(self.update_progress)

        self.scale_timer = QTimer(self)
        self.scale_timer.setInterval(timer_interval)
        self.scale_timer.timeout.connect(self.animate_scale)

        self.setMouseTracking(True)
        self.speaker = None
        self.hover_sound = None
        self.click_sound = None
        if self.enable_click_sound or self.enable_hover_sound:
            from ..peripherals.speaker import Speaker

            self.speaker = Speaker()
            current_dir = os.path.dirname(os.path.abspath(__file__))
            audio_dir = os.path.join(
                os.path.dirname(current_dir), _config["asset_paths"]["AUDIO_CLICK_PATH"]
            )
            with open(audio_dir, "rb") as f:
                raven_click = f.read()
            self.hover_sound = raven_click
            self.click_sound = raven_click

    def closeEvent(self, event: QEvent) -> None:
        """
        Clean up animation timers and resources when the widget is closed.

        Args:
            event: Close event from Qt.
        """
        try:
            log.debug("Icon closing - cleaning up timers")

            # Stop all timers
            if hasattr(self, "delay_timer") and self.delay_timer.isActive():
                self.delay_timer.stop()
                self.delay_timer.deleteLater()

            if hasattr(self, "progress_timer") and self.progress_timer.isActive():
                self.progress_timer.stop()
                self.progress_timer.deleteLater()

            if hasattr(self, "scale_timer") and self.scale_timer.isActive():
                self.scale_timer.stop()
                self.scale_timer.deleteLater()

            log.debug("Icon timers cleaned up")
        except Exception as e:
            log.error(f"Error cleaning up icon timers: {e}", exc_info=True)

        super().closeEvent(event)

    def enterEvent(self, event: QEnterEvent) -> None:
        """
        Handle mouse enter event.

        Starts scaling animation to full size when mouse enters the icon.

        Args:
            event: Mouse enter event from Qt.
        """
        if self.disabled:
            super().enterEvent(event)
            return
        self.target_scale = 1.0
        if not self.scale_timer.isActive():
            self.scale_timer.start()
        if self.enable_hover_sound and self.speaker and self.hover_sound:
            self.speaker.play_audio(self.hover_sound)
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        """
        Handle mouse leave event.

        Resets dwell progress, shows bottom text, and scales the icon down when mouse leaves.

        Args:
            event: Mouse leave event from Qt.
        """
        if self.disabled:
            super().leaveEvent(event)
            return
        self.bottom_text_visible = True
        self.target_scale = self.start_at_scale
        self.progress_timer.stop()
        self.progress = 0.0
        self.delay_timer.stop()
        self.delay_progress = 0.0
        self.update()
        if not self.scale_timer.isActive():
            self.scale_timer.start()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """
        Handle mouse press event.

        Manually triggers click on left mouse button press, resetting progress
        and hiding bottom text. Immediately emits the clicked signal.

        Args:
            event: Mouse press event from Qt.
        """
        if self.disabled:
            super().mousePressEvent(event)
            return
        if self.enable_click and event.button() == Qt.LeftButton:
            self.progress = 0.0
            self.progress_timer.stop()
            self.bottom_text_visible = False
            self.clicked.emit()
            if self.enable_click_sound and self.speaker and self.click_sound:
                self.speaker.play_audio(self.click_sound)
            self.update()
        super().mousePressEvent(event)

    def animate_scale(self) -> None:
        """
        Handle hover scaling animation logic.

        Called on scale_timer timeout. Smoothly animates the icon scale towards
        the target scale. When scale reaches 1.0 and mouse is over the icon,
        starts delay timer or progress timer.
        """
        if self.disabled:
            return
        if abs(self.scale - self.target_scale) < SCALE_THRESHOLD:
            self.scale = self.target_scale
            self.scale_timer.stop()
            if self.scale == 1.0 and self.underMouse():
                self.delay_progress = 0.0
                if self.delay_time > 0:
                    self.delay_timer.start()
                else:
                    self.progress_timer.start()
        else:
            direction = 1 if self.target_scale > self.scale else -1
            self.scale += direction * self.scale_step
        self.update()

    def update_delay_progress(self) -> None:
        """
        Run delay countdown before dwell progress starts.

        Called on delay_timer timeout. When delay completes and mouse is still
        over the icon, starts the progress timer for dwell-click functionality.
        """
        if self.disabled:
            return
        self.delay_progress += self.delay_progress_increment
        if self.delay_progress >= self.max_delay_progress:
            self.delay_timer.stop()
            self.delay_progress = 0.0
            if self.underMouse():
                self.progress_timer.start()
        self.update()

    def update_progress(self) -> None:
        """
        Increment dwell progress and emit clicked signal once threshold reached.

        Called on progress_timer timeout. When progress reaches maximum,
        triggers dwell click and hides bottom text.
        """
        if self.disabled or not self.enable_click:
            return
        self.progress += self.progress_increment
        if self.progress >= self.max_progress:
            log.info("Dwell click triggered.")
            self.progress_timer.stop()
            self.bottom_text_visible = False
            self.progress = 0.0
            self.clicked.emit()
        if self.enable_click_sound and self.speaker and self.click_sound:
            self.speaker.play_audio(self.click_sound)
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        """
        Paint the icon widget.

        Handles rendering of the icon background, outline, progress indicator,
        center text, and optional bottom text. Supports benchmark timing if enabled.

        Args:
            event: Paint event from Qt.
        """

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self.disabled:
            painter.setOpacity(0.5)

        if self.is_square:
            self._paint_rounded_rect(painter)
        else:
            self._paint_circle(painter)

        self.paint_center_text(painter)
        if self.bottom_text and self.bottom_text_visible:
            self.paint_bottom_text(painter)

        if self.disabled:
            painter.setOpacity(1.0)

    def paint_bottom_text(self, painter: QPainter) -> None:
        """
        Draw wrapped text below the icon with hyphenation.

        Args:
            painter: QPainter instance for drawing.
        """
        if not self.bottom_text:
            return

        painter.setClipping(False)
        painter.setPen(self.text_color)
        font = create_font(self.font, max(self.text_size - 2, 1), self.font_weight)
        painter.setFont(font)

        # Hyphenate before wrapping
        processed_text = self.wrap_with_hyphenation(
            self.bottom_text, max_word_len=DEFAULT_MAX_WORD_LEN
        )

        y_offset = self.size
        text_rect = QRectF(0, y_offset, self.width(), self.height() - y_offset)

        painter.drawText(
            text_rect, Qt.TextWordWrap | Qt.AlignHCenter | Qt.AlignTop, processed_text
        )

    def _paint_rounded_rect(self, painter: QPainter) -> None:
        """
        Paint a rounded rectangle icon with optional image and progress.

        Args:
            painter: QPainter instance for drawing.
        """
        w = self.size * self.scale
        h = self.size * self.scale
        radius = self.corner_radius

        x = (self.width() - w) / 2
        y = 0 if self.bottom_text else (self.height() - h) / 2
        rect = QRectF(x, y, w, h)

        painter.setPen(Qt.NoPen)
        painter.setBrush(self.color)
        painter.drawRoundedRect(rect, radius, radius)

        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        painter.setClipPath(path)

        if self.bg_image:
            image = self.bg_image.scaled(
                int(w), int(h), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            painter.drawPixmap(int(x), int(y), image)

        if (
            self.enable_click and self.delay_progress == self.max_delay_progress
        ) or not self.enable_click:
            painter.setPen(QPen(self.outline_color_bg, self.outline_width))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect, radius, radius)

        if self.progress > 0:
            self.draw_quad_progress(painter, rect, radius)

    def _paint_circle(self, painter: QPainter) -> None:
        """
        Paint a circular icon with optional image and progress arc.

        Args:
            painter: QPainter instance for drawing.
        """
        diameter = self.size * self.scale
        x = (self.width() - diameter) / 2
        y = 0 if self.bottom_text else (self.height() - diameter) / 2
        rect = QRectF(x, y, diameter, diameter)

        painter.setPen(Qt.NoPen)
        painter.setBrush(self.color)
        painter.drawEllipse(rect)

        path = QPainterPath()
        path.addEllipse(rect)
        painter.setClipPath(path)

        if self.bg_image:
            image = self.bg_image.scaled(
                int(diameter),
                int(diameter),
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )
            painter.drawPixmap(int(x), int(y), image)

        if self.progress > 0:
            pen = QPen(self.outline_color, self.outline_width)
            painter.setPen(pen)
            angle_span = int((self.progress / MAX_PROGRESS) * 360 * QT_DEGREES_TO_UNITS)
            painter.drawArc(rect, 90 * QT_DEGREES_TO_UNITS, -angle_span)

        if not self.enable_click:
            pen = QPen(self.outline_color, self.outline_width)
            painter.setPen(pen)
            angle_span = int(360 * QT_DEGREES_TO_UNITS)
            painter.drawArc(rect, 90 * QT_DEGREES_TO_UNITS, -angle_span)

    def paint_center_text(self, painter: QPainter) -> None:
        """
        Paint the center text of the icon.

        Args:
            painter: QPainter instance for drawing.
        """
        painter.setClipping(False)
        painter.setPen(self.text_color)
        font = create_font(self.font, self.text_size, self.font_weight)
        painter.setFont(font)

        fm = QFontMetrics(font)
        text_width = fm.horizontalAdvance(self.text)
        text_height = fm.height()

        painter.drawText(
            int((self.width() - text_width) / 2),
            int((self.height() + text_height) / 2 - fm.descent()),
            self.text,
        )

    def draw_quad_progress(
        self, painter: QPainter, rect: QRectF, corner_radius: float
    ) -> None:
        """
        Draw progress path around the rounded rectangle.

        Progress follows the rectangle perimeter clockwise starting from top-left corner.

        Args:
            painter: QPainter instance for drawing.
            rect: Rectangle bounding box for the icon.
            corner_radius: Radius for rounded corners.
        """
        painter.setPen(QPen(self.outline_color, self.outline_width))

        top_len = rect.width() - 2 * corner_radius
        side_len = rect.height() - 2 * corner_radius
        arc_len = (math.pi / 2) * corner_radius
        side_top_bottom = top_len + arc_len
        side_left_right = side_len + arc_len
        ratio = self.progress / MAX_PROGRESS

        # Top side
        top_prog = side_top_bottom * ratio
        x_start = rect.left() + corner_radius
        y_top = rect.top()
        if top_prog <= top_len:
            painter.drawLine(x_start, y_top, x_start + top_prog, y_top)
        else:
            painter.drawLine(x_start, y_top, x_start + top_len, y_top)
            arc_prog = min(top_prog - top_len, arc_len)
            arc_rect = QRectF(
                rect.right() - 2 * corner_radius,
                rect.top(),
                2 * corner_radius,
                2 * corner_radius,
            )
            painter.drawArc(
                arc_rect,
                90 * QT_DEGREES_TO_UNITS,
                -arc_prog / arc_len * 90 * QT_DEGREES_TO_UNITS,
            )

        # Right side
        right_prog = side_left_right * ratio
        x_right = rect.right()
        y_start = rect.top() + corner_radius
        if right_prog <= side_len:
            painter.drawLine(x_right, y_start, x_right, y_start + right_prog)
        else:
            painter.drawLine(x_right, y_start, x_right, y_start + side_len)
            arc_prog = min(right_prog - side_len, arc_len)
            arc_rect = QRectF(
                rect.right() - 2 * corner_radius,
                rect.bottom() - 2 * corner_radius,
                2 * corner_radius,
                2 * corner_radius,
            )
            painter.drawArc(arc_rect, 0, -arc_prog / arc_len * 90 * QT_DEGREES_TO_UNITS)

        # Bottom side
        bottom_prog = side_top_bottom * ratio
        y_bottom = rect.bottom()
        x_start = rect.right() - corner_radius
        if bottom_prog <= top_len:
            painter.drawLine(x_start, y_bottom, x_start - bottom_prog, y_bottom)
        else:
            painter.drawLine(x_start, y_bottom, x_start - top_len, y_bottom)
            arc_prog = min(bottom_prog - top_len, arc_len)
            arc_rect = QRectF(
                rect.left(),
                rect.bottom() - 2 * corner_radius,
                2 * corner_radius,
                2 * corner_radius,
            )
            painter.drawArc(
                arc_rect,
                270 * QT_DEGREES_TO_UNITS,
                -arc_prog / arc_len * 90 * QT_DEGREES_TO_UNITS,
            )

        # Left side
        left_prog = side_left_right * ratio
        x_left = rect.left()
        y_start = rect.bottom() - corner_radius
        if left_prog <= side_len:
            painter.drawLine(x_left, y_start, x_left, y_start - left_prog)
        else:
            painter.drawLine(x_left, y_start, x_left, y_start - side_len)
            arc_prog = min(left_prog - side_len, arc_len)
            arc_rect = QRectF(
                rect.left(), rect.top(), 2 * corner_radius, 2 * corner_radius
            )
            painter.drawArc(
                arc_rect,
                180 * QT_DEGREES_TO_UNITS,
                -arc_prog / arc_len * 90 * QT_DEGREES_TO_UNITS,
            )

    def set_text(self, new_text: str) -> None:
        """
        Update the center text and repaint the widget.

        Args:
            new_text (str): New text to display centered in the icon.
        """
        self.text = new_text
        self.update()

    def on_clicked(self, callback: Callable[..., Any], *args, **kwargs) -> None:
        """
        Connect a callback function to the clicked signal, with optional arguments.

        Args:
            callback (Callable): Function to call when clicked.
            *args: Positional arguments to pass to the callback.
            **kwargs: Keyword arguments to pass to the callback.
        """
        self.clicked.connect(partial(callback, *args, **kwargs))

    def set_background_image(self, image_path: Optional[str]) -> None:
        """
        Dynamically set or update the background image of the icon.

        Args:
            image_path (str | None): Path to the new image file.
                                     Pass None to remove the image.
        """
        try:
            if image_path:
                self.bg_image = QPixmap(image_path)
                if self.bg_image.isNull():
                    log.warning(f"Failed to load image: {image_path}")
                    self.bg_image = None
            else:
                self.bg_image = None
            self.update()
        except Exception as e:
            log.error(f"Error setting background image: {e}")

    def wrap_with_hyphenation(self, text: str, max_word_len: int = 8) -> str:
        """
        Insert hyphen breaks for words longer than max_word_len.

        Example: "incredible" -> "incredi-\nble"

        Args:
            text: Text to process.
            max_word_len: Maximum word length before hyphenation.

        Returns:
            Text with hyphenated long words.
        """
        words = text.split()
        wrapped_words = []

        for word in words:
            if len(word) > max_word_len:
                # break into chunks and add hyphens
                parts = [
                    word[i : i + max_word_len]
                    for i in range(0, len(word), max_word_len)
                ]
                hyphenated = "-\n".join(parts[:-1]) + (
                    "-\n" + parts[-1] if len(parts) > 1 else ""
                )
                wrapped_words.append(hyphenated)
            else:
                wrapped_words.append(word)

        return " ".join(wrapped_words)

    def set_disabled(self, disabled: bool) -> None:
        """
        Enable or disable the icon.

        When disabled, the icon won't respond to clicks or hover events,
        and will be rendered with reduced opacity.

        Args:
            disabled (bool): True to disable the icon, False to enable it.
        """
        if self.disabled == disabled:
            return

        self.disabled = disabled

        # Stop any active timers when disabling
        if disabled:
            self.progress_timer.stop()
            self.delay_timer.stop()
            self.progress = 0.0
            self.delay_progress = 0.0
            # Reset to start scale when disabled
            self.target_scale = self.start_at_scale
            if not self.scale_timer.isActive():
                self.scale_timer.start()

        self.update()

    def set_enabled(self, enabled: bool) -> None:
        """
        Enable or disable the icon (convenience method).

        Args:
            enabled (bool): True to enable the icon, False to disable it.
        """
        self.set_disabled(not enabled)

    def is_disabled(self) -> bool:
        """
        Check if the icon is currently disabled.

        Returns:
            bool: True if the icon is disabled, False otherwise.
        """
        return self.disabled
