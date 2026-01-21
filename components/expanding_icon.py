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
Expanding icon widget for Raven Framework.

This module provides a customizable clickable widget with animated scaling, optional
background images, and embedded content widgets.
"""

import json
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QEvent, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QEnterEvent,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPixmap,
    QRegion,
)
from PySide6.QtWidgets import QWidget

from ..helpers.font_utils import create_font
from ..helpers.logger import get_logger
from ..helpers.themes import RAVEN_CORE
from ..helpers.utils_light import load_config, to_qcolor

theme = RAVEN_CORE

# Load configuration
_config = load_config()
ICON_FPS = _config["fps"]["UI_FPS"]

log = get_logger("ExpandingIcon")


class ExpandingIcon(QWidget):
    """
    A customizable clickable widget with animated scaling and optional background image or embedded content.

    Signals:
        clicked: Emitted when the widget is clicked or dwell-clicked.

    Args:
        size (int): Width and height of the icon (square). Defaults to 80.
        background_color (str): Background fill color (CSS color string or name). Defaults to theme.colors.background_color.
        scale_by (float): Scale offset for hover animation (fractional). Defaults to 0.2.
        scale_step (float): Increment step size for scale animation per frame. Defaults to 0.02.
        fps (int): Animation frames per second.
        background_image_path (str): File path for optional background image. Defaults to "".
        text_size (int): Font size for text. Defaults to theme.fonts.body.size.
        text_color (str): Color for bottom text rendering (CSS color string or name). Defaults to theme.fonts.body.color.
        font (str): Font family ('libre_franklin'). Defaults to theme.fonts.body.family.
        font_weight (str): Font weight, one of 'light', 'normal', 'medium', 'bold', or 'black'. Defaults to theme.fonts.body.weight.
        margin (int): Margin padding around content. Defaults to 20.
        content_widget (Optional[QWidget]): Optional widget to embed inside the expanding icon. Defaults to None.
        bottom_text (str): Optional text to display below the icon. Defaults to "".
        main_widget (Optional[QWidget]): Alternative main widget to embed, replaces background image. Defaults to None.
    """

    clicked = Signal()

    def __init__(
        self,
        size: int = 80,
        background_color: str = theme.colors.background_color,
        scale_by: float = 0.2,
        scale_step: float = 0.02,
        fps: int = ICON_FPS,
        background_image_path: str = "",
        text_size: int = theme.fonts.body.size,
        text_color: str = theme.fonts.body.color,
        font: str = theme.fonts.body.family,
        font_weight: str = theme.fonts.body.weight,
        margin: int = 20,
        content_widget: Optional[QWidget] = None,
        bottom_text: str = "",
        main_widget: Optional[QWidget] = None,
    ) -> None:
        """
        Initialize the ExpandingIcon widget.

        See class docstring for parameter descriptions.
        """
        super().__init__()
        log.info("Initializing ExpandingIcon.")
        self.radius: int = int(size // 2)
        self.color: QColor = to_qcolor(background_color)
        self.start_scale: float = 1.0 - float(scale_by)
        self.scale: float = self.start_scale
        self.target_scale: float = 1.0
        self.scale_step: float = float(scale_step)
        self.fps: int = int(fps)
        self.margin: int = int(margin)
        self.text_color: QColor = to_qcolor(text_color)
        self.text_size: int = int(text_size)
        self.font: str = font
        self.font_weight: str = font_weight
        self.bottom_text: str = bottom_text
        self.bottom_text_visible: bool = bool(bottom_text)

        self.main_widget: Optional[QWidget] = main_widget

        if main_widget:
            try:
                log.info("Main widget set.")
                main_widget.setParent(self)
                main_widget.show()
            except Exception as e:
                log.error(f"Error setting main_widget: {e}", exc_info=True)
        else:
            try:
                self.bg_image: Optional[QPixmap] = (
                    QPixmap(background_image_path) if background_image_path else None
                )
            except Exception as e:
                self.bg_image = None
                log.error(f"Error loading background image: {e}", exc_info=True)

        self.content_widget: Optional[QWidget] = content_widget
        if content_widget:
            try:
                log.info("Embedded content widget.")
                content_widget.setParent(self)
                content_widget.hide()
            except Exception as e:
                log.error(f"Error setting content_widget: {e}", exc_info=True)

        self.scale_timer: QTimer = QTimer()
        if self.fps == 0:
            error_msg = "Division by zero: fps is 0, cannot calculate timer interval"
            log.error(error_msg, extra={"console": True})
            raise ValueError(error_msg)
        timer_interval = int(1000 / self.fps)
        self.scale_timer.setInterval(timer_interval)
        self.scale_timer.timeout.connect(self.animate_scale)

        extra_height: int = 30 if bottom_text else 0
        self.setFixedSize(int(self.radius * 2), int(self.radius * 2 + extra_height))
        self.setMouseTracking(True)

        self.icon_image = None

        log.info("ExpandingIcon initialized successfully.")

    def enterEvent(self, event: QEnterEvent) -> None:
        """
        Handle mouse entering the widget area.

        Starts the scaling animation and hides bottom text.

        Args:
            event: Enter event from Qt.
        """
        log.debug("Enter event detected")
        self.bottom_text_visible = False
        self.scale_timer.start()
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        """
        Handle mouse leaving the widget area.

        Resets scale and hides embedded content widget.

        Args:
            event: Leave event from Qt.
        """
        log.debug("Leave event detected")
        self.bottom_text_visible = True
        self.scale = self.start_scale
        if self.content_widget:
            try:
                self.content_widget.hide()
            except Exception as e:
                log.error(
                    f"Error hiding content_widget on leaveEvent: {e}", exc_info=True
                )
        self.update()
        super().leaveEvent(event)

    def animate_scale(self) -> None:
        """
        Incrementally animate the scaling of the widget.

        Shows embedded content widget when scale animation completes.
        Called automatically by the scale timer when active.
        """
        try:
            if abs(self.scale - self.target_scale) < 0.005:
                self.scale = self.target_scale
                log.debug("Scaling animation complete.")
                self.scale_timer.stop()
                if self.content_widget:
                    self.content_widget.show()
            else:
                self.scale += self.scale_step
            self.update()
        except Exception as e:
            log.error(f"Error during animate_scale: {e}", exc_info=True)

    def paintEvent(self, event) -> None:
        """
        Paint the widget including background, scaling animation, embedded widgets, and optional bottom text.

        Args:
            event: Paint event from Qt.
        """
        try:

            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)

            scaled_diameter: float = 2 * self.radius * self.scale
            x: float = (self.width() - scaled_diameter) / 2
            y: float = (self.height() - scaled_diameter) / 2
            rect: QRectF = QRectF(x, y, scaled_diameter, scaled_diameter)
            corner_radius: float = (
                float(self.radius) if self.scale < 1.0 else scaled_diameter / 4
            )

            painter.setPen(Qt.NoPen)
            painter.setBrush(self.color)
            painter.drawRoundedRect(rect, int(corner_radius), int(corner_radius))

            if self.bottom_text and self.bottom_text_visible:
                self._paint_bottom_text(painter)

            if self.main_widget:
                self.main_widget.setGeometry(0, 0, self.width(), self.height())
                mask_path = QPainterPath()
                mask_path.addRoundedRect(
                    QRectF(0, 0, self.width(), self.height()),
                    corner_radius,
                    corner_radius,
                )
                region = QRegion(mask_path.toFillPolygon().toPolygon())
                self.main_widget.setMask(region)
                self.main_widget.show()

            else:
                if self.bg_image and self.scale < 1.0:
                    path = QPainterPath()
                    path.addRoundedRect(rect, corner_radius, corner_radius)
                    painter.setClipPath(path)
                    img = self.bg_image.scaled(
                        int(scaled_diameter),
                        int(scaled_diameter),
                        Qt.KeepAspectRatioByExpanding,
                        Qt.SmoothTransformation,
                    )
                    painter.drawPixmap(int(x), int(y), img)
                    painter.setClipping(False)

            if self.content_widget and self.scale == 1.0:
                self.content_widget.setGeometry(0, 10, self.width(), self.height() - 20)
                mask_path = QPainterPath()
                mask_path.addRoundedRect(
                    QRectF(0, 0, self.width(), self.height()),
                    corner_radius,
                    corner_radius,
                )
                region = QRegion(mask_path.toFillPolygon().toPolygon())
                self.content_widget.setMask(region)

        except Exception as e:
            log.error(f"Error during paintEvent: {e}", exc_info=True)

    def _paint_bottom_text(self, painter: QPainter) -> None:
        """
        Draws optional text below the icon with proper font and alignment.

        Args:
            painter (QPainter): Painter object used for drawing.
        """
        try:
            painter.setClipping(False)
            painter.setPen(self.text_color)
            font = create_font(self.font, self.text_size - 2, self.font_weight)
            painter.setFont(font)

            fm = QFontMetrics(font)
            text_width = fm.horizontalAdvance(self.bottom_text)
            x = (self.width() - text_width) / 2
            y = self.height() - 2
            painter.drawText(int(x), int(y), self.bottom_text)
        except Exception as e:
            log.error(f"Error painting bottom text: {e}", exc_info=True)

    def closeEvent(self, event: QEvent) -> None:
        """
        Clean up animation timers and resources when the widget is closed.

        Args:
            event: Close event from Qt.
        """
        try:
            if hasattr(self, "scale_timer") and self.scale_timer:
                self.scale_timer.stop()
                self.scale_timer.deleteLater()
                log.debug("Cleaned up scale_timer.")
        except Exception as e:
            log.error(f"Error during closeEvent: {e}", exc_info=True)
        super().closeEvent(event)
