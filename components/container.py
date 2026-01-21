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
Container widget for Raven Framework.

This module provides a flexible container widget with customizable background,
rounded corners, borders, and automatic vertical stacking layout.
"""

from typing import Optional

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
from PySide6.QtWidgets import QLabel, QWidget

from ..helpers.logger import get_logger
from ..helpers.themes import RAVEN_CORE
from ..helpers.utils_light import css_color, to_qcolor

theme = RAVEN_CORE

log = get_logger("Container")


class Container(QWidget):
    """
    A QWidget subclass that acts as a container with customizable background color,
    rounded corners, border, and simple vertical stacking layout with optional margins and spacing.

    Args:
        parent (Optional[QWidget]): Parent widget. Defaults to None.
        background_color (str): Background color (any CSS compatible format or 'transparent').
            Defaults to theme.basic_palette.transparent, or theme.colors.background_color if is_main_container is True.
        background_image (Optional[str]): Path to background image file. Defaults to None.
        corner_radius (int): Radius for rounded corners in pixels. Defaults to theme.borders.corner_radius.
        border_width (int): Border width in pixels. Defaults to 0, or theme.borders.width if is_main_container is True.
        border_color (str): Border color (any CSS compatible format). Defaults to theme.basic_palette.transparent.
        width (Optional[int]): Fixed width for the container. Defaults to None.
        height (Optional[int]): Fixed height for the container. Defaults to None.
        inner_margin (int): Initial margin inside the container. Defaults to 0.
        spacing (int): Vertical spacing between added child widgets. Defaults to 10.
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
        border_color: str = theme.basic_palette.transparent,
        width: Optional[int] = None,
        height: Optional[int] = None,
        inner_margin: int = 0,
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
        Initialize the Container widget.

        See class docstring for parameter descriptions.
        """
        super().__init__(parent)

        self.inner_margin = int(inner_margin)
        self.spacing = int(spacing)
        self.next_y = self.inner_margin
        self.corner_radius = int(corner_radius)
        self.background_image = background_image

        # Apply main container defaults if is_main_container is True and defaults are used
        if is_main_container:
            background_color = theme.colors.background_color
            border_width = theme.borders.width

        # Set fixed size if specified
        try:
            if width is not None and height is not None:
                self.setFixedSize(int(width), int(height))
            elif width is not None:
                self.setFixedWidth(int(width))
            elif height is not None:
                self.setFixedHeight(int(height))
        except Exception as e:
            log.error(f"Error setting fixed size: {e}", exc_info=True)

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
        self.border_gradient_end_color: QColor = to_qcolor(border_gradient_end_color)
        self.border_gradient_direction: str = border_gradient_direction
        self._border_width = int(border_width)
        self._border_color = border_color

        # Background label used for background color and radius styling
        # Border will be drawn separately if gradient is enabled
        self._background = QLabel(self)
        self._background.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._background.lower()

        # Only add border to CSS if not using gradient
        border_width_for_css = border_width if not self.use_gradient_border else 0
        self.update_background_style(
            background_color,
            self.background_image,
            self.corner_radius,
            border_width_for_css,
            border_color,
        )

    def update_background_style(
        self,
        background_color: str,
        background_image: Optional[str],
        corner_radius: int,
        border_width: int,
        border_color: str,
    ) -> None:
        """
        Update the stylesheet of the internal background QLabel to apply
        background color, border radius, and border color/width.

        Args:
            background_color (str): Background color (CSS compatible format).
            background_image (Optional[str]): Path to background image file, or None.
            corner_radius (int): Radius for rounded corners in pixels.
            border_width (int): Border thickness in pixels.
            border_color (str): Border color (CSS compatible format).
        """
        try:
            style = ""
            if background_color:
                style += f"background-color: {css_color(background_color)};"
            if background_image:
                style += f"background-image: url('{background_image}'); background-position: center; background-repeat: no-repeat;"
            if corner_radius and corner_radius > 0:
                style += f"border-radius: {corner_radius}px;"
            if border_width and border_width > 0:
                style += (
                    f"border: {int(border_width)}px solid {css_color(border_color)};"
                )
            if style != "":
                self._background.setStyleSheet(style)
        except Exception as e:
            log.error(f"Error updating background style: {e}", exc_info=True)

    def resizeEvent(self, event: QResizeEvent) -> None:
        """
        Override resizeEvent to update background label geometry and apply rounded corner mask.

        Args:
            event: Resize event from Qt.
        """
        try:
            self._background.setGeometry(0, 0, self.width(), self.height())

            if self.corner_radius > 0:
                path = QPainterPath()
                path.addRoundedRect(
                    QRectF(self.rect()), self.corner_radius, self.corner_radius
                )
                region = QRegion(path.toFillPolygon().toPolygon())
                self.setMask(region)
            else:
                self.setMask(QRegion(self.rect()))

        except Exception as e:
            log.error(f"Error in resizeEvent: {e}", exc_info=True)

        super().resizeEvent(event)

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
            inner_rect = QRectF(
                self._border_width,
                self._border_width,
                self.width() - 2 * self._border_width,
                self.height() - 2 * self._border_width,
            )

            # Create paths
            outer_path = QPainterPath()
            outer_path.addRoundedRect(
                outer_rect, self.corner_radius, self.corner_radius
            )
            inner_path = QPainterPath()
            inner_path.addRoundedRect(
                inner_rect, self.corner_radius, self.corner_radius
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

    def add(
        self, widget: QWidget, x: Optional[int] = None, y: Optional[int] = None
    ) -> None:
        """
        Add a child widget to the container.

        Positions the widget either at (x, y) if specified, or stacks it vertically
        with spacing based on inner_margin and spacing properties.

        Args:
            widget (QWidget): The child widget to add.
            x (Optional[int]): Absolute x-coordinate to place the widget. If None, uses vertical stacking.
            y (Optional[int]): Absolute y-coordinate to place the widget. If None, uses vertical stacking.

        Raises:
            ValueError: If widget is None or invalid.
            RuntimeError: If widget addition fails.

        Note:
            - If both x and y are provided, the widget is positioned absolutely.
            - If either x or y is None, the widget is stacked vertically.
        """
        if widget is None:
            log.error(f"Cannot add None widget to container")
            raise ValueError("Cannot add None widget to container")

        try:
            widget.setParent(self)
            if x is not None and y is not None:
                widget.move(int(x), int(y))
            else:
                widget.move(self.inner_margin, self.next_y)
                self.next_y += widget.sizeHint().height() + self.spacing
            widget.show()
        except Exception as e:
            log.error(f"Error adding widget: {e}", exc_info=True)
            raise RuntimeError(f"Failed to add widget to container: {e}")

    def clear(self) -> None:
        """
        Clear all child widgets from the container except the background label.

        Resets the internal layout state (_next_y) to the initial inner_margin value.
        All widgets are properly deleted to prevent memory leaks.
        """
        try:
            for child in self.findChildren(QWidget):
                if child is not self._background:
                    child.setParent(None)
                    child.deleteLater()
            self.next_y = self.inner_margin
        except Exception as e:
            log.error(f"Error clearing container: {e}", exc_info=True)
