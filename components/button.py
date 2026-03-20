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
Button widget for Raven Framework.

This module provides a customizable button widget with dwell-to-click functionality,
scaling animations, and support for embedded content widgets.
"""

# Standard library imports
import math
import os
from functools import partial
from typing import Any, Callable, Optional

# PySide6 imports
from PySide6.QtCore import QEvent, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFontMetrics,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPixmap,
    QRegion,
)
from PySide6.QtWidgets import QVBoxLayout, QWidget

# Local imports
from ..helpers.font_utils import create_font
from ..helpers.logger import get_logger
from ..helpers.themes import RAVEN_CORE
from ..helpers.utils_light import load_config, to_qcolor

theme = RAVEN_CORE

log = get_logger("Button")

# Load configuration
_config = load_config()

# Preset size tuples: (width, height)
SMALL_SIZE = (110, 45)
MEDIUM_SIZE = (150, 70)
LARGE_SIZE = (200, 70)
DISABLED_OPACITY = 0.9

# Animation constants
SCALE_THRESHOLD = 0.005  # Threshold for scale animation completion
FILL_DWELL_OFFSET = 0.1  # Offset for fill dwell progress ratio mapping
HORIZONTAL_PADDING_1 = 3  # Horizontal padding for fill dwell rect
HORIZONTAL_PADDING_2 = 3  # Horizontal padding for fill dwell clip path
BUTTON_FPS = _config["fps"]["UI_FPS"]

# Qt arc drawing constants
QT_DEGREES_TO_UNITS = _config["display"]["QT_DEGREES_TO_UNITS"]


class Button(QWidget):
    """
    A customizable rectangular or rounded-rect button widget with
    dwell-to-click functionality, scaling animation, and optional
    embedded content widget.

    Signals:
        clicked: Emitted when the button is clicked or dwell-clicked.

    Args:
        preset_size (str): Preset size option: 'small', 'medium', 'large', or '' for custom. Defaults to ''.
        width (int): Width of the widget in pixels. Defaults to 150.
        height (int): Height of the widget in pixels. Defaults to 60.
        background_color (str): Background fill color as string (e.g., '#FF0000' or color name). Defaults to theme.colors.button_background_color.
        center_text (str): Text displayed centered in the button. Defaults to "Click Me".
        text_size (int): Font size for the center text. Defaults to theme.fonts.body.size.
        text_color (str): Color of the center text as string. Defaults to theme.fonts.body.color.
        font (str): Font family ('libre_franklin'). Defaults to theme.fonts.body.family.
        font_weight (str): Font weight, one of 'light', 'normal', 'medium', 'bold', or 'black'. Defaults to theme.fonts.body.weight.
        corner_radius (int): Radius for rounded corners. Defaults to theme.borders.corner_radius.
        outline_width (int): Width of the outline stroke. Defaults to 4.
        outline_color (str): Color of the outline stroke as string. Defaults to theme.borders.highlight_color_button.
        scale_by (float): Amount to shrink the widget when not hovered (e.g., 0.1 for 10% shrinkage). Defaults to 0.1.
        scale_step (float): Scale animation step per frame. Defaults to 0.01.
        fps (int): Frames per second for animation updates.
        delay_time (int): Delay time in milliseconds before starting animations. Defaults to 500.
        dwell_time (int): Time in milliseconds required to trigger dwell-click. Defaults to 1500.
        content_widget (Optional[QWidget]): Optional child widget to embed inside button. Defaults to None.
        background_image_path (Optional[str]): File path to background image. Defaults to None.
        enable_quad_dwell (bool): Enables quad (rounded rect) dwell UI. Defaults to False.
        enable_click (bool): Enables dwell-click functionality. Defaults to True.
        enable_hover_sound (bool): Enable audio feedback on hover. Defaults to True. Disabled on Linux.
        enable_click_sound (bool): Enable audio feedback on click. Defaults to True. Disabled on Linux.
        dwell_background_outline_color (str): Outline color for quad dwell background as string. Defaults to theme.borders.highlight_quad_dwell_outline_color_button.
        use_gradient_border (bool): If True, renders border with gradient instead of solid color. Defaults to False.
        border_gradient_start_color (str): Start color for gradient border as string. Defaults to outline_color_bg.
        border_gradient_end_color (str): End color for gradient border as string. Defaults to outline_color_bg.
        border_gradient_direction (str): Gradient direction: 'horizontal', 'vertical', or 'diagonal'. Defaults to 'horizontal'.
        use_fill_dwell (bool): If True, fills background from left to right on dwell instead of outline progress. Defaults to True.
        disabled (bool): If True, button is disabled and won't respond to clicks or hover. Defaults to False.
        padding (int): Additional padding in pixels to add around text when auto-sizing. Defaults to 20.
        icon_path (Optional[str]): File path to icon image to display to the left of text. Defaults to None.
        icon_height (int): Height of the icon in pixels. Width will be scaled proportionally. Defaults to 24.
        icon_text_gap (int): Spacing in pixels between icon and text. Defaults to 8.
        action_icon_path (Optional[str]): File path to action icon image to display to the right of text. Defaults to None.
        action_icon_height (int): Height of the action icon in pixels. Width will be scaled proportionally. Defaults to 24.
        action_icon_side_padding (int): Side padding for action icon (40 = 20px on each side). The gap between text and action icon is calculated dynamically to fill remaining space. Defaults to 40.
        show_action_icon (bool): If True, uses default action icon from assets/icons/action_button.png. Defaults to False.
    """

    clicked = Signal()

    def __init__(
        self,
        preset_size: str = "",
        width: int = 150,
        height: int = 60,
        background_color: str = theme.colors.button_background_color,
        center_text: str = "Click Me",
        text_size: int = theme.fonts.body.size,
        text_color: str = theme.fonts.body.color,
        font: str = theme.fonts.body.family,
        font_weight: str = theme.fonts.body.weight,
        corner_radius: int = theme.borders.corner_radius,
        outline_width: int = theme.borders.highlight_width,
        outline_color: str = theme.borders.highlight_color_button,
        scale_by: float = 0.1,
        scale_step: float = 0.01,
        fps: int = BUTTON_FPS,
        delay_time: int = 500,
        dwell_time: int = 1500,
        content_widget: Optional[QWidget] = None,
        background_image_path: Optional[str] = None,
        enable_quad_dwell: bool = False,
        enable_click: bool = True,
        enable_hover_sound: bool = False,
        enable_click_sound: bool = False,
        dwell_background_outline_color: str = theme.borders.color,
        use_gradient_border: bool = theme.borders.use_gradient_border,
        border_gradient_start_color: Optional[
            str
        ] = theme.borders.border_gradient_start_color,
        border_gradient_end_color: Optional[
            str
        ] = theme.borders.border_gradient_end_color,
        border_gradient_direction: str = theme.borders.border_gradient_direction,
        use_fill_dwell: bool = theme.borders.use_fill_dwell,
        disabled: bool = False,
        padding: int = 10,
        icon_path: Optional[str] = None,
        icon_height: int = 35,
        icon_text_gap: int = 10,
        action_icon_path: Optional[str] = None,
        action_icon_height: int = 35,
        action_icon_side_padding: int = 50,
        show_action_icon: bool = False,
    ):
        """
        Initialize the Button widget.

        See class docstring for parameter descriptions.
        """
        super().__init__()

        # Set default action icon path if show_action_icon is True
        if show_action_icon and action_icon_path is None:
            action_icon_path = os.path.join(
                os.path.dirname(__file__),
                "..",
                _config["asset_paths"]["ACTION_BUTTON_ICON_PATH"],
            )

        # Cast critical numeric parameters explicitly
        width = int(width)
        height = int(height)
        corner_radius = int(corner_radius)
        outline_width = int(outline_width)
        text_size = int(text_size)
        fps = int(fps)
        dwell_time = int(dwell_time)

        self.enable_quad_dwell: bool = enable_quad_dwell
        self.enable_click: bool = enable_click
        self.enable_hover_sound: bool = enable_hover_sound
        self.enable_click_sound: bool = enable_click_sound
        self.use_fill_dwell: bool = use_fill_dwell
        self.disabled: bool = disabled

        padding = int(padding)

        # If preset size, width, or height are default values, then they are auto-sized based on the text, icon, and action icon.
        if (
            preset_size == ""
            and content_widget is None
            and width == 150  # Default width
            and height == 60  # Default height
        ):
            auto_size = self.calculate_text_based_size(
                center_text,
                text_size,
                font,
                font_weight,
                outline_width,
                padding,
                icon_path,
                icon_height,
                icon_text_gap,
                action_icon_path,
                action_icon_height,
                action_icon_side_padding,
            )
            if auto_size:
                width, height = auto_size

        if preset_size != "":
            preset_size_tup = (-1, -1)
            if preset_size == "small":
                preset_size_tup = SMALL_SIZE
            elif preset_size == "medium":
                preset_size_tup = MEDIUM_SIZE
            elif preset_size == "large":
                preset_size_tup = LARGE_SIZE
            else:
                log.warning(f"Unknown preset_size '{preset_size}', using default size")
                preset_size_tup = (width, height)
            self.setFixedSize(preset_size_tup[0], preset_size_tup[1])
        else:
            self.setFixedSize(width, height)

        if self.use_fill_dwell:
            outline_color = theme.borders.color

        self.text: str = center_text
        self.text_size: int = text_size
        self.text_color: QColor = to_qcolor(text_color)
        self.font: str = font
        self.font_weight: str = font_weight
        self.corner_radius: int = corner_radius
        self.outline_width: int = outline_width
        self.outline_color: QColor = (
            to_qcolor(outline_color) if outline_color else QColor(255, 255, 255)
        )
        if self.use_fill_dwell:
            background_color = theme.colors.button_background_dwell_fill_color
        self.background_color: QColor = to_qcolor(background_color)
        self.delay_time = delay_time

        # Animation properties
        self.fps: int = fps
        self.start_scale: float = 1.0 - float(scale_by)
        self.scale: float = self.start_scale
        self.target_scale: float = 1.0
        self.scale_step: float = float(scale_step)

        # Dwell progress tracking
        self.progress: float = 0.0
        self.max_progress: float = 100.0
        # Protect against division by zero
        if fps > 0 and dwell_time > 0:
            self.progress_increment: float = self.max_progress / (
                dwell_time / (1000.0 / fps)
            )
        else:
            log.warning("Invalid fps or dwell_time, setting progress_increment to 1.0")
            self.progress_increment = 1.0

        # Quad dwell specific outline color
        self.outline_color_bg: QColor = to_qcolor(dwell_background_outline_color)

        # Gradient border properties
        self.use_gradient_border: bool = use_gradient_border
        # Use provided colors or fallback to dwell_background_outline_color if explicitly None
        if border_gradient_start_color is None:
            border_gradient_start_color = dwell_background_outline_color
        if border_gradient_end_color is None:
            border_gradient_end_color = dwell_background_outline_color
        self.border_gradient_start_color: QColor = to_qcolor(
            border_gradient_start_color
        )
        self.border_gradient_end_color: QColor = to_qcolor(border_gradient_end_color)
        self.border_gradient_direction: str = border_gradient_direction

        # Optional embedded widget
        self.content_widget: Optional[QWidget] = content_widget
        if self.content_widget:
            self.content_widget.setParent(self)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setAlignment(Qt.AlignCenter)
            layout.addWidget(self.content_widget)
            log.info("Loaded embedded content widget.")

        # Load background image if provided
        self.bg_image: Optional[QPixmap] = None
        if background_image_path:
            try:
                self.bg_image = QPixmap(background_image_path)
                if self.bg_image.isNull():
                    log.warning(
                        f"Background image at '{background_image_path}' failed to load (pixmap is null)."
                    )
                    self.bg_image = None
            except Exception as e:
                self.bg_image = None
                log.error(
                    f"Error loading background image '{background_image_path}': {e}"
                )

        # Load icon if provided
        self.icon: Optional[QPixmap] = None
        self.icon_height: int = int(icon_height)
        self.icon_text_gap: int = int(icon_text_gap)
        if icon_path:
            try:
                icon_pixmap = QPixmap(icon_path)
                if icon_pixmap.isNull():
                    log.warning(
                        f"Icon at '{icon_path}' failed to load (pixmap is null)."
                    )
                    self.icon = None
                else:
                    # Scale icon to specified height while maintaining aspect ratio
                    if icon_pixmap.height() == 0:
                        error_msg = (
                            f"Division by zero: icon height is 0 for '{icon_path}'"
                        )
                        log.error(error_msg, extra={"console": True})
                        raise ValueError(error_msg)
                    aspect_ratio = icon_pixmap.width() / icon_pixmap.height()
                    icon_width = int(self.icon_height * aspect_ratio)
                    self.icon = icon_pixmap.scaled(
                        icon_width,
                        self.icon_height,
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    )
                    log.info(
                        f"Loaded icon from '{icon_path}' with size {icon_width}x{self.icon_height}"
                    )
            except Exception as e:
                self.icon = None
                log.error(f"Error loading icon '{icon_path}': {e}")

        # Load action icon if provided
        self.action_icon: Optional[QPixmap] = None
        self.action_icon_height: int = int(action_icon_height)
        self.action_icon_side_padding: int = int(action_icon_side_padding)
        self.action_icon_text_gap: int = 0  # Will be calculated dynamically
        if action_icon_path:
            try:
                action_icon_pixmap = QPixmap(action_icon_path)
                if action_icon_pixmap.isNull():
                    log.warning(
                        f"Action icon at '{action_icon_path}' failed to load (pixmap is null)."
                    )
                    self.action_icon = None
                else:
                    # Scale action icon to specified height while maintaining aspect ratio
                    if action_icon_pixmap.height() == 0:
                        error_msg = f"Division by zero: action icon height is 0 for '{action_icon_path}'"
                        log.error(error_msg, extra={"console": True})
                        raise ValueError(error_msg)
                    aspect_ratio = (
                        action_icon_pixmap.width() / action_icon_pixmap.height()
                    )
                    action_icon_width = int(self.action_icon_height * aspect_ratio)
                    self.action_icon = action_icon_pixmap.scaled(
                        action_icon_width,
                        self.action_icon_height,
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    )
                    log.info(
                        f"Loaded action icon from '{action_icon_path}' with size {action_icon_width}x{self.action_icon_height}"
                    )
            except Exception as e:
                self.action_icon = None
                log.error(f"Error loading action icon '{action_icon_path}': {e}")

        # Calculate action_icon_text_gap dynamically if action icon is present
        # This fills the remaining space: button_width - icon - icon_gap - text - action_icon - side_padding
        if self.action_icon:
            try:
                font_obj = create_font(font, text_size, font_weight)
                fm = QFontMetrics(font_obj)
                # Don't account for text width if center_text is empty
                text_width = fm.horizontalAdvance(center_text) if center_text else 0

                icon_width = self.icon.width() if self.icon else 0
                action_icon_width = self.action_icon.width()

                # Get the actual button width (after size is set)
                button_width = self.width()

                # Calculate remaining space: button_width - icon - icon_gap - text - action_icon - side_padding
                used_width = (
                    icon_width
                    + (self.icon_text_gap if icon_width > 0 else 0)
                    + text_width
                    + action_icon_width
                    + (2 * self.action_icon_side_padding)
                )
                calculated_gap = button_width - used_width

                # Only use calculated gap if it's positive, otherwise keep it at 0
                if calculated_gap > 0:
                    self.action_icon_text_gap = calculated_gap
                    log.debug(f"Calculated action_icon_text_gap: {calculated_gap}px")
            except Exception as e:
                log.warning(f"Error calculating action_icon_text_gap: {e}")

        self.delay_progress = 0.0
        self.max_delay_progress = 100.0

        if fps > 0 and self.delay_time > 0:
            self.delay_progress_increment = self.max_delay_progress / (
                self.delay_time / (1000.0 / self.fps)
            )
        else:
            log.warning(
                "Invalid fps or delay_time, setting delay_progress_increment to 1.0"
            )
            self.delay_progress_increment = 1.0

        # Timers for animation and dwell progress
        if self.fps == 0:
            error_msg = "Division by zero: fps is 0, cannot calculate timer interval"
            log.error(error_msg, extra={"console": True})
            raise ValueError(error_msg)
        timer_interval = int(1000 / self.fps)
        self.delay_timer = QTimer(self)
        self.delay_timer.setInterval(timer_interval)
        self.delay_timer.timeout.connect(self.update_delay_progress)

        self.progress_timer: QTimer = QTimer(self)
        self.progress_timer.setInterval(timer_interval)
        self.progress_timer.timeout.connect(self.update_progress)

        self.scale_timer: QTimer = QTimer(self)
        self.scale_timer.setInterval(timer_interval)
        self.scale_timer.timeout.connect(self.update_scale)

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
            log.debug("Button closing - cleaning up timers")

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

            log.debug("Button timers cleaned up")
        except Exception as e:
            log.error(f"Error cleaning up button timers: {e}", exc_info=True)

        super().closeEvent(event)

    def update_progress(self) -> None:
        """
        Increment dwell progress and emit clicked signal once threshold reached.
        Called on progress_timer timeout.
        """
        if self.disabled or not self.enable_click:
            return
        self.progress += self.progress_increment
        if self.progress >= self.max_progress:
            log.info("Dwell click triggered.")
            self.progress_timer.stop()
            self.progress = 0.0
            self.clicked.emit()
            if self.enable_click_sound and self.speaker and self.click_sound:
                self.speaker.play_audio(self.click_sound)
        self.update()  # Trigger repaint to update progress UI

    def update_delay_progress(self) -> None:
        """
        Run delay countdown before dwell progress starts.

        Called on delay_timer timeout. When delay completes and mouse is still
        over the button, starts the progress timer for dwell-click functionality.
        """
        if self.disabled:
            return
        self.delay_progress += self.delay_progress_increment
        if self.delay_progress >= self.max_delay_progress:
            log.info("Delay complete. Starting dwell progress.")
            self.delay_timer.stop()
            self.delay_progress = 0.0
            if self.underMouse():
                self.progress_timer.start()
        self.update()

    def update_scale(self) -> None:
        """
        Animate scaling towards the target scale with smooth stepping.
        Called on scale_timer timeout.
        """
        if abs(self.scale - self.target_scale) < SCALE_THRESHOLD:
            self.scale = self.target_scale
            self.scale_timer.stop()
            log.debug("Scaling animation complete.")
            if self.scale == 1.0:
                self.delay_progress = 0.0
                if self.delay_time > 0:
                    self.delay_timer.start()
                else:
                    self.progress_timer.start()
        else:
            direction = 1 if self.target_scale > self.scale else -1
            self.scale += direction * self.scale_step
            # Clamp scale within [start_scale, 1.0]
            self.scale = max(min(self.scale, 1.0), self.start_scale)
        self.update()

    def enterEvent(self, event: QEvent) -> None:
        """
        Handle mouse enter event.

        Starts scaling animation to full size when mouse enters the button.

        Args:
            event: Mouse enter event from Qt.
        """
        if self.disabled:
            super().enterEvent(event)
            return
        log.debug("Mouse enter event detected.")
        self.target_scale = 1.0
        if not self.scale_timer.isActive():
            self.scale_timer.start()
        if self.enable_hover_sound and self.speaker and self.hover_sound:
            self.speaker.play_audio(self.hover_sound)
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        """
        Handle mouse leave event.

        Resets dwell progress and scales the button down when mouse leaves.

        Args:
            event: Mouse leave event from Qt.
        """
        if self.disabled:
            super().leaveEvent(event)
            return
        log.debug("Mouse leave event detected.")
        self.target_scale = self.start_scale
        self.progress_timer.stop()
        self.progress = 0.0
        if not self.scale_timer.isActive():
            self.scale_timer.start()
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """
        Handle mouse press event.

        Manually triggers click on left mouse button press, resetting scale
        and progress. Immediately emits the clicked signal.

        Args:
            event: Mouse press event from Qt.
        """
        if self.disabled:
            super().mousePressEvent(event)
            return
        if self.enable_click and event.button() == Qt.LeftButton:
            log.debug("Mouse press event detected: Left button.")
            self.scale = self.start_scale
            self.target_scale = 1.0
            if self.progress_timer.isActive():
                self.progress_timer.stop()
            self.progress = 0.0
            self.clicked.emit()
            if self.enable_click_sound and self.speaker and self.click_sound:
                self.speaker.play_audio(self.click_sound)
            self.update()
        super().mousePressEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        """
        Paint the button widget.

        Handles rendering of the button background, outline, progress indicator,
        and center content/text. Supports benchmark timing if enabled.

        Args:
            event: Paint event from Qt.
        """

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self.enable_quad_dwell:
            self._paint_quad_button(painter)
        else:
            self._paint_radial_button(painter)

    def _paint_quad_button(self, painter: QPainter) -> None:
        """
        Paint the rounded rectangle (quad) button with optional dwell progress.

        Args:
            painter (QPainter): The QPainter used for drawing.
        """
        # Apply disabled opacity
        if self.disabled:
            painter.setOpacity(DISABLED_OPACITY)

        base_width: float = float(self.width())
        base_height: float = float(self.height())
        width: float = base_width * self.scale
        height: float = base_height * self.scale
        corner_radius: int = self.corner_radius
        outline_width: int = self.outline_width
        outline_color: QColor = self.outline_color_bg
        highlight_color: QColor = self.outline_color

        x_offset: float = (self.width() - width) / 2
        y_offset: float = (self.height() - height) / 2
        rect = QRectF(x_offset, y_offset, width, height)

        # Background
        painter.setPen(Qt.NoPen)
        if self.bg_image:
            scaled_img = self.bg_image.scaled(
                int(width),
                int(height),
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )
            painter.drawPixmap(int(x_offset), int(y_offset), scaled_img)
        else:
            painter.setBrush(self.background_color)
            painter.drawRoundedRect(rect, corner_radius, corner_radius)

        # Draw static border (gradient or solid) - only when progress is not active
        if not self.progress_timer.isActive() and self.outline_width > 0:
            if self.use_gradient_border:
                # Create outer and inner rectangles for border path
                outer_rect = QRectF(x_offset, y_offset, width, height)
                inner_rect = QRectF(
                    x_offset + self.outline_width,
                    y_offset + self.outline_width,
                    width - 2 * self.outline_width,
                    height - 2 * self.outline_width,
                )

                # Create paths
                outer_path = QPainterPath()
                outer_path.addRoundedRect(outer_rect, corner_radius, corner_radius)
                inner_path = QPainterPath()
                inner_path.addRoundedRect(inner_rect, corner_radius, corner_radius)

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
            else:
                # Solid color border
                painter.setPen(QPen(self.outline_color_bg, self.outline_width))
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(rect, corner_radius, corner_radius)

        # Outline progress ring background
        if self.progress_timer.isActive():
            painter.setPen(QPen(outline_color, outline_width))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect, corner_radius, corner_radius)

        # Outline progress ring foreground
        if self.progress_timer.isActive():
            painter.setPen(QPen(highlight_color, outline_width))

            top_line_len = width - 2 * corner_radius
            right_line_len = height - 2 * corner_radius
            arc_len = (math.pi / 2) * corner_radius

            side_total_len_tb = top_line_len + arc_len
            side_total_len_lr = right_line_len + arc_len
            progress_ratio = self.progress / 100.0

            # Top line + arc
            top_progress = side_total_len_tb * progress_ratio
            x_start = x_offset + corner_radius
            y_top = y_offset

            if top_progress <= top_line_len:
                painter.drawLine(x_start, y_top, x_start + top_progress, y_top)
            else:
                painter.drawLine(x_start, y_top, x_start + top_line_len, y_top)
                arc_prog = top_progress - top_line_len
                arc_rect = QRectF(
                    rect.right() - 2 * corner_radius,
                    rect.top(),
                    2 * corner_radius,
                    2 * corner_radius,
                )
                if arc_len == 0:
                    error_msg = "Division by zero: arc_len is 0 in _paint_quad_button"
                    log.error(error_msg, extra={"console": True})
                    raise ValueError(error_msg)
                angle_span = (arc_prog / arc_len) * 90
                painter.drawArc(
                    arc_rect,
                    90 * QT_DEGREES_TO_UNITS,
                    -angle_span * QT_DEGREES_TO_UNITS,
                )

            # Right line + arc
            right_progress = side_total_len_lr * progress_ratio
            x_right = rect.right()
            y_start = rect.top() + corner_radius

            if right_progress <= right_line_len:
                painter.drawLine(x_right, y_start, x_right, y_start + right_progress)
            else:
                painter.drawLine(x_right, y_start, x_right, y_start + right_line_len)
                arc_prog = right_progress - right_line_len
                arc_rect = QRectF(
                    rect.right() - 2 * corner_radius,
                    rect.bottom() - 2 * corner_radius,
                    2 * corner_radius,
                    2 * corner_radius,
                )
                if arc_len == 0:
                    error_msg = "Division by zero: arc_len is 0 in _paint_quad_button"
                    log.error(error_msg, extra={"console": True})
                    raise ValueError(error_msg)
                angle_span = (arc_prog / arc_len) * 90
                painter.drawArc(arc_rect, 0, -angle_span * QT_DEGREES_TO_UNITS)

            # Bottom line + arc
            bottom_progress = side_total_len_tb * progress_ratio
            x_start = rect.right() - corner_radius
            y_bottom = rect.bottom()

            if bottom_progress <= top_line_len:
                painter.drawLine(x_start, y_bottom, x_start - bottom_progress, y_bottom)
            else:
                painter.drawLine(x_start, y_bottom, x_start - top_line_len, y_bottom)
                arc_prog = bottom_progress - top_line_len
                arc_rect = QRectF(
                    rect.left(),
                    rect.bottom() - 2 * corner_radius,
                    2 * corner_radius,
                    2 * corner_radius,
                )
                if arc_len == 0:
                    error_msg = "Division by zero: arc_len is 0 in _paint_quad_button"
                    log.error(error_msg, extra={"console": True})
                    raise ValueError(error_msg)
                angle_span = (arc_prog / arc_len) * 90
                painter.drawArc(
                    arc_rect,
                    270 * QT_DEGREES_TO_UNITS,
                    -angle_span * QT_DEGREES_TO_UNITS,
                )

            # Left line + arc
            left_progress = side_total_len_lr * progress_ratio
            x_left = rect.left()
            y_start = rect.bottom() - corner_radius

            if left_progress <= right_line_len:
                painter.drawLine(x_left, y_start, x_left, y_start - left_progress)
            else:
                painter.drawLine(x_left, y_start, x_left, y_start - right_line_len)
                arc_prog = left_progress - right_line_len
                arc_rect = QRectF(
                    rect.left(), rect.top(), 2 * corner_radius, 2 * corner_radius
                )
                if arc_len == 0:
                    error_msg = "Division by zero: arc_len is 0 in _paint_quad_button"
                    log.error(error_msg, extra={"console": True})
                    raise ValueError(error_msg)
                angle_span = (arc_prog / arc_len) * 90
                painter.drawArc(
                    arc_rect,
                    180 * QT_DEGREES_TO_UNITS,
                    -angle_span * QT_DEGREES_TO_UNITS,
                )

        # Position and scale content widget if present
        if self.content_widget:
            full_width = float(self.width())
            full_height = float(self.height())

            scaled_width = (full_width * self.scale) - self.outline_width
            scaled_height = (full_height * self.scale) - self.outline_width

            x = (self.width() - scaled_width) / 2
            y = (self.height() - scaled_height) / 2

            self.content_widget.setGeometry(
                int(x), int(y), int(scaled_width), int(scaled_height)
            )

            mask_path = QPainterPath()
            mask_path.addRoundedRect(
                QRectF(0, 0, scaled_width, scaled_height), corner_radius, corner_radius
            )
            region = QRegion(mask_path.toFillPolygon().toPolygon())
            self.content_widget.setMask(region)

        else:
            painter.setPen(self.text_color)
            font = create_font(self.font, self.text_size, self.font_weight)
            painter.setFont(font)

            fm = QFontMetrics(font)
            # Don't account for text width if text is empty
            text_width = fm.horizontalAdvance(self.text) if self.text else 0
            text_height = fm.height()

            # Calculate widths of icons if present
            icon_width = self.icon.width() if self.icon else 0
            action_icon_width = self.action_icon.width() if self.action_icon else 0

            # Calculate total width: icon + gap + text + gap + action_icon
            left_gap = self.icon_text_gap if icon_width > 0 else 0
            right_gap = self.action_icon_text_gap if action_icon_width > 0 else 0
            total_width = (
                icon_width + left_gap + text_width + right_gap + action_icon_width
            )

            # Calculate starting x position to center the entire content
            start_x = (self.width() - total_width) / 2
            center_y = (self.height() + text_height) / 2 - fm.descent()

            # Draw icon if present (left side)
            if self.icon:
                icon_y = (self.height() - self.icon_height) / 2
                painter.drawPixmap(int(start_x), int(icon_y), self.icon)
                start_x += icon_width + self.icon_text_gap

            # Draw text only if not empty
            text_x = start_x
            if self.text:
                painter.drawText(int(text_x), int(center_y), self.text)
                text_x += text_width

            # Draw action icon if present (right side)
            if self.action_icon:
                text_x += self.action_icon_text_gap
                action_icon_y = (self.height() - self.action_icon_height) / 2
                painter.drawPixmap(int(text_x), int(action_icon_y), self.action_icon)

    def _paint_radial_button(self, painter: QPainter) -> None:
        """
        Paint the rectangular button with rounded corners and a dwell progress arc.

        Args:
            painter (QPainter): The QPainter used for drawing.
        """
        # Apply disabled opacity
        if self.disabled:
            painter.setOpacity(DISABLED_OPACITY)

        outline_width: int = self.outline_width
        outline_color: QColor = self.outline_color
        width: float = float(self.width()) * self.scale
        height: float = float(self.height()) * self.scale
        r: float = float(self.corner_radius) * self.scale

        x_offset: float = (self.width() - width) / 2
        y_offset: float = (self.height() - height) / 2
        half_pen: int = int(outline_width / 2)
        rect = QRectF(
            x_offset + half_pen,
            y_offset + half_pen,
            width - outline_width,
            height - outline_width,
        )

        painter.setPen(Qt.NoPen)
        if self.use_fill_dwell:
            full_rect = QRectF(x_offset, y_offset, width, height)
            painter.setBrush(QColor(0, 0, 0))
            painter.drawRoundedRect(full_rect, r, r)

            if self.progress > 0:
                progress_ratio = self.progress / 100.0

                # since there is a delay, ratio goes from 0.1 to 1.0. We need to map it to 0.0 to 1.0
                offset = FILL_DWELL_OFFSET
                denominator = 1.0 - offset
                if denominator == 0:
                    error_msg = f"Division by zero: (1.0 - offset) is 0 in fill dwell calculation"
                    log.error(error_msg, extra={"console": True})
                    raise ValueError(error_msg)
                progress_ratio = (progress_ratio - offset) / denominator

                inner_width = width - 2 * outline_width
                inner_height = height - 2 * outline_width
                inner_x = x_offset + outline_width
                inner_y = y_offset + outline_width
                # Add protection for both dimensions
                if inner_width > 0 and inner_height > 0:
                    fill_start_ratio = r / inner_width
                    fill_range = 1.0 - fill_start_ratio
                    fill_ratio = fill_start_ratio + (fill_range * progress_ratio)
                    fill_width = inner_width * fill_ratio
                else:
                    # Fallback if dimensions are invalid
                    log.warning(
                        f"Invalid button dimensions: inner_width={inner_width}, "
                        f"inner_height={inner_height}"
                    )
                    fill_width = 0
                    fill_ratio = 0.0
                    fill_start_ratio = 0.0
                    fill_range = 1.0
                horizontal_padding_1 = HORIZONTAL_PADDING_1
                fill_rect = QRectF(
                    inner_x - horizontal_padding_1,
                    inner_y,
                    inner_width + (2 * horizontal_padding_1),
                    inner_height,
                )
                painter.setBrush(self.background_color)

                clip_path = QPainterPath()
                horizontal_padding_2 = HORIZONTAL_PADDING_2
                clip_path.addRoundedRect(
                    inner_x - horizontal_padding_2,
                    inner_y,
                    fill_width + (2 * horizontal_padding_2),
                    inner_height,
                    0,
                    0,
                )
                painter.setClipPath(clip_path)
                painter.drawRoundedRect(fill_rect, r, r)
                painter.setClipping(False)
        elif self.bg_image:
            scaled_img = self.bg_image.scaled(
                int(width),
                int(height),
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )
            painter.drawPixmap(int(x_offset), int(y_offset), scaled_img)
        else:
            painter.setBrush(self.background_color)
            painter.drawRoundedRect(rect, r, r)

        # Draw static border (gradient or solid)
        if self.use_gradient_border and self.outline_width > 0:
            # Create outer and inner rectangles for border path
            outer_rect = QRectF(x_offset, y_offset, width, height)
            inner_rect = QRectF(
                x_offset + self.outline_width,
                y_offset + self.outline_width,
                width - 2 * self.outline_width,
                height - 2 * self.outline_width,
            )

            # Create paths
            outer_path = QPainterPath()
            outer_path.addRoundedRect(outer_rect, r, r)
            inner_path = QPainterPath()
            inner_path.addRoundedRect(
                inner_rect, r - self.outline_width, r - self.outline_width
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
        else:
            # Solid color border
            painter.setPen(QPen(self.outline_color_bg, self.outline_width))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect, r, r)

        if self.progress > 0 and not self.use_fill_dwell:
            painter.setPen(
                QPen(outline_color, outline_width, Qt.SolidLine, Qt.RoundCap)
            )

            arc_len = (math.pi / 2) * r
            side_lengths = {
                "top": width - 2 * r,
                "right": height - 2 * r,
                "bottom": width - 2 * r,
                "left": height - 2 * r,
            }
            perimeter = 2 * (side_lengths["top"] + side_lengths["right"]) + 4 * arc_len
            progress_len = (self.progress / 100.0) * perimeter
            length_left = progress_len

            def draw_line(
                x1: float, y1: float, x2: float, y2: float, length_left: float
            ) -> float:
                full_len = math.hypot(x2 - x1, y2 - y1)
                if length_left <= 0:
                    return 0.0
                if length_left >= full_len:
                    painter.drawLine(x1, y1, x2, y2)
                    return length_left - full_len
                if full_len == 0:
                    error_msg = "Division by zero: full_len is 0 in draw_line"
                    log.error(error_msg, extra={"console": True})
                    raise ValueError(error_msg)
                ratio = length_left / full_len
                painter.drawLine(x1, y1, x1 + (x2 - x1) * ratio, y1 + (y2 - y1) * ratio)
                return 0.0

            def draw_arc(
                x: float, y: float, radius: float, start_deg: float, length_left: float
            ) -> float:
                arc_circum = arc_len
                if length_left <= 0:
                    return 0.0
                if length_left >= arc_circum:
                    painter.drawArc(
                        QRectF(x, y, 2 * radius, 2 * radius),
                        int(start_deg * QT_DEGREES_TO_UNITS),
                        int(-90 * QT_DEGREES_TO_UNITS),
                    )
                    return length_left - arc_circum
                if arc_circum == 0:
                    error_msg = "Division by zero: arc_circum is 0 in draw_arc"
                    log.error(error_msg, extra={"console": True})
                    raise ValueError(error_msg)
                span_deg = (length_left / arc_circum) * 90
                painter.drawArc(
                    QRectF(x, y, 2 * radius, 2 * radius),
                    int(start_deg * QT_DEGREES_TO_UNITS),
                    int(-span_deg * QT_DEGREES_TO_UNITS),
                )
                return 0.0

            # Draw top side and corner arc
            length_left = draw_line(
                rect.left() + r, rect.top(), rect.right() - r, rect.top(), length_left
            )
            length_left = draw_arc(rect.right() - 2 * r, rect.top(), r, 90, length_left)

            # Draw right side and corner arc
            length_left = draw_line(
                rect.right(),
                rect.top() + r,
                rect.right(),
                rect.bottom() - r,
                length_left,
            )
            length_left = draw_arc(
                rect.right() - 2 * r, rect.bottom() - 2 * r, r, 0, length_left
            )

            # Draw bottom side and corner arc
            length_left = draw_line(
                rect.right() - r,
                rect.bottom(),
                rect.left() + r,
                rect.bottom(),
                length_left,
            )
            length_left = draw_arc(
                rect.left(), rect.bottom() - 2 * r, r, 270, length_left
            )

            # Draw left side and corner arc
            length_left = draw_line(
                rect.left(), rect.bottom() - r, rect.left(), rect.top() + r, length_left
            )
            length_left = draw_arc(rect.left(), rect.top(), r, 180, length_left)

        # Position and scale content widget if present
        if self.content_widget:
            full_width: float = float(self.width())
            full_height: float = float(self.height())

            scaled_width = (full_width * self.scale) - self.outline_width
            scaled_height = (full_height * self.scale) - self.outline_width

            x = (self.width() - scaled_width) / 2
            y = (self.height() - scaled_height) / 2

            self.content_widget.setGeometry(
                int(x), int(y), int(scaled_width), int(scaled_height)
            )
            mask_path = QPainterPath()
            mask_path.addRoundedRect(
                QRectF(
                    half_pen,
                    half_pen,
                    scaled_width - outline_width,
                    scaled_height - outline_width,
                ),
                r,
                r,
            )
            region = QRegion(mask_path.toFillPolygon().toPolygon())
            self.content_widget.setMask(region)
        else:
            painter.setPen(self.text_color)
            font = create_font(self.font, self.text_size, self.font_weight)
            painter.setFont(font)

            fm = painter.fontMetrics()
            # Don't account for text width if text is empty
            text_width = fm.horizontalAdvance(self.text) if self.text else 0
            text_height = fm.height()

            # Calculate widths of icons if present
            icon_width = self.icon.width() if self.icon else 0
            action_icon_width = self.action_icon.width() if self.action_icon else 0

            # Calculate total width: icon + gap + text + gap + action_icon
            left_gap = self.icon_text_gap if icon_width > 0 else 0
            right_gap = self.action_icon_text_gap if action_icon_width > 0 else 0
            total_width = (
                icon_width + left_gap + text_width + right_gap + action_icon_width
            )

            # Calculate starting x position to center the entire content
            start_x = (self.width() - total_width) / 2
            center_y = (self.height() + text_height) / 2 - fm.descent()

            # Draw icon if present (left side)
            if self.icon:
                icon_y = (self.height() - self.icon_height) / 2
                painter.drawPixmap(int(start_x), int(icon_y), self.icon)
                start_x += icon_width + self.icon_text_gap

            # Draw text only if not empty
            text_x = start_x
            if self.text:
                painter.drawText(int(text_x), int(center_y), self.text)
                text_x += text_width

            # Draw action icon if present (right side)
            if self.action_icon:
                text_x += self.action_icon_text_gap
                action_icon_y = (self.height() - self.action_icon_height) / 2
                painter.drawPixmap(int(text_x), int(action_icon_y), self.action_icon)

    def calculate_text_based_size(
        self,
        text: str,
        text_size: int,
        font: str,
        font_weight: str,
        outline_width: int,
        padding: int,
        icon_path: Optional[str] = None,
        icon_height: int = 35,
        icon_text_gap: int = 20,
        action_icon_path: Optional[str] = None,
        action_icon_height: int = 35,
        action_icon_side_padding: int = 50,
    ) -> Optional[tuple[int, int]]:
        """
        Calculate button size based on text width and optional icons.

        Tries to fit text (and icons if provided) into preset sizes. If content is too large,
        uses large height and calculates custom width.

        Args:
            text: The button text
            text_size: Font size
            font: Font family
            font_weight: Font weight
            outline_width: Width of outline for padding calculation
            padding: Additional padding in pixels to add around text
            icon_path: Optional path to icon image file (left side)
            icon_height: Height of the icon in pixels
            icon_text_gap: Spacing between icon and text in pixels
            action_icon_path: Optional path to action icon image file (right side)
            action_icon_height: Height of the action icon in pixels
            action_icon_side_padding: Side padding for action icon (40 = 20px on each side). Defaults to 40.

        Returns:
            Tuple of (width, height) or None if auto-sizing shouldn't be used
        """
        font_obj = create_font(font, text_size, font_weight)
        fm = QFontMetrics(font_obj)
        # Don't account for text width if text is empty
        text_width = fm.horizontalAdvance(text) if text else 0

        # Calculate icon width if icon is provided
        icon_width = 0
        if icon_path:
            try:
                icon_pixmap = QPixmap(icon_path)
                if not icon_pixmap.isNull() and icon_pixmap.height() > 0:
                    # Calculate width based on aspect ratio
                    aspect_ratio = icon_pixmap.width() / icon_pixmap.height()
                    icon_width = int(icon_height * aspect_ratio)
            except Exception:
                # If icon fails to load, ignore it for size calculation
                pass

        # Calculate action icon width if action icon is provided
        action_icon_width = 0
        if action_icon_path:
            try:
                action_icon_pixmap = QPixmap(action_icon_path)
                if not action_icon_pixmap.isNull() and action_icon_pixmap.height() > 0:
                    # Calculate width based on aspect ratio
                    aspect_ratio = (
                        action_icon_pixmap.width() / action_icon_pixmap.height()
                    )
                    action_icon_width = int(action_icon_height * aspect_ratio)
            except Exception:
                # If action icon fails to load, ignore it for size calculation
                pass

        # Calculate total content width: icon + gap + text + action_icon + side_padding
        # Note: action_icon_text_gap is calculated dynamically, so we use side_padding for size estimation
        left_gap = icon_text_gap if icon_width > 0 else 0
        content_width = (
            icon_width
            + left_gap
            + text_width
            + action_icon_width
            + action_icon_side_padding
        )
        total_padding = (outline_width * 2) + (padding * 2)
        required_width = content_width + total_padding

        # Fit into preset sizes
        if required_width <= SMALL_SIZE[0]:
            return SMALL_SIZE
        elif required_width <= MEDIUM_SIZE[0]:
            return MEDIUM_SIZE
        elif required_width <= LARGE_SIZE[0]:
            return LARGE_SIZE
        else:
            # Content is too big for large, using large height and custom width
            return (required_width, LARGE_SIZE[1])

    def set_text(self, new_text: str) -> None:
        """
        Update the center text and repaint the widget.

        Args:
            new_text (str): New text to display centered in the button.
        """
        self.text = new_text
        self.update()  # Triggers paintEvent to redraw with new text

    def on_clicked(self, callback: Callable[..., Any], *args, **kwargs) -> None:
        """
        Connect a callback function to the clicked signal, with optional arguments.

        Args:
            callback (Callable): Function to call when clicked.
            *args: Positional arguments to pass to the callback.
            **kwargs: Keyword arguments to pass to the callback.
        """
        self.clicked.connect(partial(callback, *args, **kwargs))

    def set_disabled(self, disabled: bool) -> None:
        """
        Enable or disable the button.

        When disabled, the button won't respond to clicks or hover events,
        and will be rendered with reduced opacity.

        Args:
            disabled (bool): True to disable the button, False to enable it.
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
            self.target_scale = self.start_scale
            if not self.scale_timer.isActive():
                self.scale_timer.start()

        self.update()

    def set_enabled(self, enabled: bool) -> None:
        """
        Enable or disable the button (convenience method).

        Args:
            enabled (bool): True to enable the button, False to disable it.
        """
        self.set_disabled(not enabled)

    def is_disabled(self) -> bool:
        """
        Check if the button is currently disabled.

        Returns:
            bool: True if the button is disabled, False otherwise.
        """
        return self.disabled
