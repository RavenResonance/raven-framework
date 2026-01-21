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
Vertical container widget for Raven Framework.

This module provides a vertical layout container widget with customizable background,
rounded corners, borders, and configurable margins.
"""

from typing import Optional, Tuple, Union

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QRegion,
    QResizeEvent,
)
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ..helpers.logger import get_logger
from ..helpers.themes import RAVEN_CORE
from ..helpers.utils_light import css_color, to_qcolor

theme = RAVEN_CORE

log = get_logger("VerticalContainer")


class VerticalContainer(QWidget):
    """
    A vertical layout container widget with customizable background color,
    border, rounded corners, and inner margins.

    Args:
        parent (Optional[QWidget]): Optional parent widget. Defaults to None.
        background_color (str): CSS color string or QColor-compatible background.
            Defaults to theme.basic_palette.transparent, or theme.colors.background_color if is_main_container is True.
        background_image (Optional[str]): Path to background image file. Defaults to None.
        corner_radius (int): Radius of rounded corners in pixels. Defaults to theme.borders.corner_radius.
        border_width (int): Width of the border in pixels. Defaults to 0, or theme.borders.width if is_main_container is True.
        border_color (str): CSS color string or QColor-compatible border color. Defaults to theme.borders.color.
        width (Optional[int]): Optional fixed width in pixels. Defaults to None.
        height (Optional[int]): Optional fixed height in pixels. Defaults to None.
        inner_margin (Union[int, Tuple[int, int], Tuple[int, int, int, int]]):
            Margin(s) inside the container. Defaults to 0.
            - int: uniform margin on all sides
            - Tuple[int, int]: (horizontal, vertical) margins
            - Tuple[int, int, int, int]: (left, top, right, bottom) margins
        spacing (int): Spacing between widgets in the layout. Defaults to 10.
        is_main_container (bool): If True, sets background_color to theme.colors.background_color and
            border_width to theme.borders.width when defaults are used. Defaults to False.
        use_gradient_border (bool): If True, renders border with gradient instead of solid color. Defaults to True.
        border_gradient_start_color (Optional[str]): Start color for gradient border as string. Defaults to "#FFFFFF".
        border_gradient_end_color (Optional[str]): End color for gradient border as string. Defaults to "#C8C8C8".
        border_gradient_direction (str): Gradient direction: 'horizontal', 'vertical', or 'diagonal'. Defaults to 'diagonal'.
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        background_color: str = theme.basic_palette.transparent,
        background_image: Optional[str] = None,
        corner_radius: int = 0,
        border_width: int = 0,
        border_color: str = theme.borders.color,
        width: Optional[int] = None,
        height: Optional[int] = None,
        inner_margin: Union[int, Tuple[int, int], Tuple[int, int, int, int]] = 0,
        spacing: int = 0,
        is_main_container: bool = False,
        use_gradient_border: bool = theme.borders.use_gradient_border,
        border_gradient_start_color: Optional[
            str
        ] = theme.borders.border_gradient_start_color,
        border_gradient_end_color: Optional[
            str
        ] = theme.borders.border_gradient_end_color,
        border_gradient_direction: str = theme.borders.border_gradient_direction,
    ) -> None:
        """
        Initialize the VerticalContainer widget.

        See class docstring for parameter descriptions.
        """
        try:
            super().__init__(parent)

            # Apply main container defaults if is_main_container is True and defaults are used
            if is_main_container:
                background_color = theme.basic_palette.transparent
                border_width = theme.borders.width
                corner_radius = theme.borders.corner_radius

            # Cast sizes explicitly to int if provided
            if width is not None and height is not None:
                self.setFixedSize(int(width), int(height))
            elif width is not None:
                self.setFixedWidth(int(width))
            elif height is not None:
                self.setFixedHeight(int(height))

            # Background label for styling
            self._background = QLabel(self)
            self._background.setAttribute(Qt.WA_TransparentForMouseEvents)
            self._background.setGeometry(0, 0, self.width(), self.height())
            self._background.lower()
            self.background_image = background_image

            # Gradient border properties
            self.use_gradient_border: bool = use_gradient_border
            if border_gradient_start_color is None:
                border_gradient_start_color = (
                    border_color
                    if border_color != theme.basic_palette.transparent
                    else theme.basic_palette.white
                )
            if border_gradient_end_color is None:
                border_gradient_end_color = (
                    border_color
                    if border_color != theme.basic_palette.transparent
                    else theme.basic_palette.light_gray
                )
            self.border_gradient_start_color: QColor = to_qcolor(
                border_gradient_start_color
            )
            self.border_gradient_end_color: QColor = to_qcolor(
                border_gradient_end_color
            )
            self.border_gradient_direction: str = border_gradient_direction
            self._border_width = int(border_width)
            self._border_color = border_color

            style = ""
            if background_color:
                style += f"background-color: {css_color(background_color)};"
            if background_image:
                style += f"background-image: url('{background_image}'); background-position: center; background-repeat: no-repeat;"
            if corner_radius > 0:
                style += f"border-radius: {int(corner_radius)}px;"
            # Only add border to CSS if not using gradient
            if border_width > 0 and not self.use_gradient_border:
                style += (
                    f"border: {int(border_width)}px solid {css_color(border_color)};"
                )
            if style:
                self._background.setStyleSheet(style)

            self._corner_radius = int(corner_radius)

            # Main vertical layout
            self.layout = QVBoxLayout(self)
            if isinstance(inner_margin, int):
                margin = int(inner_margin)
                self.layout.setContentsMargins(margin, margin, margin, margin)
            elif isinstance(inner_margin, tuple):
                if len(inner_margin) == 2:
                    horizontal, vertical = map(int, inner_margin)
                    self.layout.setContentsMargins(
                        horizontal, vertical, horizontal, vertical
                    )
                elif len(inner_margin) == 4:
                    left, top, right, bottom = map(int, inner_margin)
                    self.layout.setContentsMargins(left, top, right, bottom)

            self.layout.setSpacing(int(spacing))
            self.layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            self.setLayout(self.layout)
        except Exception as e:
            log.error(f"Error initializing VerticalContainer: {e}", exc_info=True)
            raise

    def resizeEvent(self, event: QResizeEvent) -> None:
        """
        Handle resize event to update background geometry and apply rounded corner mask.

        Args:
            event: Resize event from Qt.
        """
        try:
            self._background.setGeometry(0, 0, self.width(), self.height())

            if self._corner_radius > 0:
                path = QPainterPath()
                path.addRoundedRect(
                    QRectF(self.rect()), self._corner_radius, self._corner_radius
                )
                region = QRegion(path.toFillPolygon().toPolygon())
                self.setMask(region)
            else:
                self.setMask(QRegion(self.rect()))

            super().resizeEvent(event)
        except Exception as e:
            log.error(f"Error during resizeEvent: {e}", exc_info=True)

    def paintEvent(self, event: QPaintEvent) -> None:
        """
        Override paintEvent to draw gradient border if enabled.

        Args:
            event: Paint event from Qt.
        """
        super().paintEvent(event)

        if (
            self.use_gradient_border
            and self._border_width > 0
            and self.width() > 0
            and self.height() > 0
        ):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)

            # Create outer and inner rectangles for border path
            outer_rect = QRectF(0, 0, self.width(), self.height())
            inner_width = self.width() - 2 * self._border_width
            inner_height = self.height() - 2 * self._border_width

            # Validate inner dimensions
            if inner_width <= 0 or inner_height <= 0:
                error_msg = (
                    f"Invalid inner dimensions: width={inner_width}, height={inner_height}. "
                    f"Container size: {self.width()}x{self.height()}, "
                    f"border_width={self._border_width}"
                )
                log.error(error_msg, extra={"console": True})
                raise ValueError(error_msg)

            inner_rect = QRectF(
                self._border_width,
                self._border_width,
                inner_width,
                inner_height,
            )

            # Create paths
            outer_path = QPainterPath()
            outer_path.addRoundedRect(
                outer_rect, self._corner_radius, self._corner_radius
            )
            inner_path = QPainterPath()
            inner_path.addRoundedRect(
                inner_rect, self._corner_radius, self._corner_radius
            )

            # Subtract inner from outer to get border shape
            border_path = outer_path - inner_path

            # Create gradient based on direction
            if self.border_gradient_direction == "vertical":
                gradient = QLinearGradient(
                    outer_rect.left(),
                    outer_rect.top(),
                    outer_rect.left(),
                    outer_rect.bottom(),
                )
            elif self.border_gradient_direction == "diagonal":
                gradient = QLinearGradient(
                    outer_rect.left(),
                    outer_rect.top(),
                    outer_rect.right(),
                    outer_rect.bottom(),
                )
            else:  # horizontal (default)
                gradient = QLinearGradient(
                    outer_rect.left(),
                    outer_rect.top(),
                    outer_rect.right(),
                    outer_rect.top(),
                )

            gradient.setColorAt(0.0, self.border_gradient_start_color)
            gradient.setColorAt(1.0, self.border_gradient_end_color)

            # Draw border with gradient
            painter.setPen(Qt.NoPen)
            painter.setBrush(gradient)
            painter.drawPath(border_path)

    def add(self, *widgets: QWidget) -> None:
        """
        Add one or multiple widgets to the vertical layout with top alignment.

        Widgets are added from top to bottom in the order provided.

        Args:
            *widgets: One or more QWidget instances to add vertically.

        Raises:
            RuntimeError: If adding widgets fails.
        """
        try:
            for widget in widgets:
                self.layout.addWidget(widget, alignment=Qt.AlignTop)
        except Exception as e:
            log.error(f"Failed to add widgets to VerticalContainer: {e}", exc_info=True)
            raise

    def clear(self) -> None:
        """
        Clear all widgets from the vertical layout except the background label.

        Removes all widgets from the layout and properly deletes them to prevent memory leaks.
        The layout structure and background remain intact.
        """
        try:
            while self.layout.count():
                item = self.layout.takeAt(0)
                if item and item.widget():
                    widget = item.widget()
                    if widget is not self._background:
                        widget.setParent(None)
                        widget.deleteLater()
                        log.debug(f"Removed widget from VerticalContainer: {widget}")
            log.info("VerticalContainer cleared.")
        except Exception as e:
            log.error(f"Error clearing VerticalContainer: {e}", exc_info=True)
