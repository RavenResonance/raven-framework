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
Scroll view widget for Raven Framework.

This module provides a scrollable widget with support for gaze-based dwell scrolling,
continuous scroll while hovering, and auto-scroll (teleprompter style).
"""

from typing import Optional

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPropertyAnimation,
    QRect,
    Qt,
    QTimer,
)
from PySide6.QtGui import QEnterEvent, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget

from ..helpers.logger import get_logger
from ..helpers.themes import RAVEN_CORE
from ..helpers.utils_light import to_qcolor
from .icon import Icon

log = get_logger("ScrollView")

DEFAULT_WIDTH = 480
DEFAULT_HEIGHT = 720
DEFAULT_MARGIN = 50


theme = RAVEN_CORE


class PaginationContainer(QWidget):
    """Container widget for pagination indicators with outline and hover effects."""

    def __init__(
        self,
        parent=None,
        initial_hover_scale: float = 1.5,
        dwell_hover_scale: float = 3.5,
        dwell_time: int = 500,
        outline_width: int = 2,
        outline_color: str = "white",
        base_corner_radius_percent: float = 0.5,
        hover_corner_radius_percent: float = 0.5,
        animation_duration: int = 200,
    ):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)

        self.base_width = 40
        self.base_height = 0
        self.initial_hover_scale = initial_hover_scale
        self.dwell_hover_scale = dwell_hover_scale
        self.hover_scale = self.initial_hover_scale
        self.current_scale = 1.0
        self.target_scale = 1.0
        self.is_dwelling = False

        self.outline_width = outline_width
        self.outline_color = outline_color
        self.base_corner_radius_percent = base_corner_radius_percent
        self.hover_corner_radius_percent = hover_corner_radius_percent
        self.current_corner_radius = 0

        self.icons = []
        self.original_padding = 0
        self.original_spacing = 0

        self.dwell_timer = QTimer(self)
        self.dwell_timer.setSingleShot(True)
        self.dwell_timer.timeout.connect(self._on_dwell_complete)
        self.dwell_time = dwell_time

        self.scale_animation = QPropertyAnimation(self, b"geometry", self)
        self.scale_animation.setDuration(animation_duration)
        self.scale_animation.setEasingCurve(QEasingCurve.OutCubic)

        def on_value_changed(value):
            if isinstance(value, QRect):
                if self.base_width > 0 and self.base_height > 0:
                    width_scale = value.width() / self.base_width
                    height_scale = value.height() / self.base_height
                    self.current_scale = (width_scale + height_scale) / 2

                    scale_factor = (self.current_scale - 1.0) / (
                        self.dwell_hover_scale - 1.0
                    )
                    scale_factor = max(0.0, min(1.0, scale_factor))

                    current_radius_percent = (
                        self.base_corner_radius_percent
                        + (
                            self.hover_corner_radius_percent
                            - self.base_corner_radius_percent
                        )
                        * scale_factor
                    )

                    current_width = value.width()
                    current_height = value.height()
                    smaller_dimension = min(current_width, current_height)
                    self.current_corner_radius = int(
                        smaller_dimension * current_radius_percent
                    )

                    icon_scale = 1.0 + (self.dwell_hover_scale - 1.0) * scale_factor
                    self._update_icon_sizes(icon_scale)
                    self._update_icon_positions(scale_factor)
                    self.update()

        self.scale_animation.valueChanged.connect(on_value_changed)

        self.container_x = 5
        self.container_y = 0
        self.container_width = self.base_width
        self.container_height = 0

    def set_container_bounds(self, x, y, width, height):
        """Set the bounds of the container area."""
        self.container_x = x
        self.container_y = y
        self.container_width = width
        self.container_height = height
        self.base_width = width
        self.base_height = height

        smaller_dimension = min(self.base_width, self.base_height)
        self.current_corner_radius = int(
            smaller_dimension * self.base_corner_radius_percent
        )

        self._update_geometry()

    def _update_geometry(self):
        """Update the container geometry based on current scale."""
        scaled_width = int(self.base_width * self.current_scale)
        scaled_height = int(self.base_height * self.current_scale)

        x = self.container_x - (scaled_width - self.base_width) // 2
        y = self.container_y - (scaled_height - self.base_height) // 2

        self.setGeometry(x, y, scaled_width, scaled_height)

    def set_icons(self, icons, padding, spacing):
        """Store reference to icons for scaling and original spacing/padding."""
        self.icons = icons
        self.original_padding = padding
        self.original_spacing = spacing
        for icon in icons:
            if not hasattr(icon, "_original_pos"):
                icon._original_pos = None

    def _update_icon_sizes(self, scale):
        """Update icon sizes based on scale factor."""
        for icon in self.icons:
            if hasattr(icon, "size") and hasattr(icon, "_original_size"):
                new_size = int(icon._original_size * scale)
                icon.size = new_size
                icon.full_diameter = new_size
                icon.setFixedSize(new_size, new_size)
                icon.update()

    def _update_icon_positions(self, scale_factor):
        """Update icon positions with scaled spacing and padding."""
        if not self.icons or self.original_padding == 0:
            return

        scaled_padding = int(
            self.original_padding
            * (1.0 + (self.dwell_hover_scale - 1.0) * scale_factor)
        )
        scaled_spacing = int(
            self.original_spacing
            * (1.0 + (self.dwell_hover_scale - 1.0) * scale_factor)
        )

        current_width = int(self.base_width * self.current_scale)

        icon_start_y = scaled_padding
        for idx, icon in enumerate(self.icons):
            if hasattr(icon, "size") and hasattr(icon, "_original_size"):
                x = (current_width - icon.size) // 2
                y = icon_start_y
                for i in range(idx):
                    if i < len(self.icons):
                        prev_icon = self.icons[i]
                        if hasattr(prev_icon, "size"):
                            y += prev_icon.size + scaled_spacing
                icon.move(x, y)

    def enterEvent(self, event: QEnterEvent) -> None:
        """Handle mouse enter - scale to initial hover scale, then start dwell timer."""
        self.is_dwelling = True
        self.hover_scale = self.initial_hover_scale
        self.target_scale = self.initial_hover_scale
        self._animate_scale()
        self.dwell_timer.start(self.dwell_time)
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        """Handle mouse leave - scale down the container and stop dwell timer."""
        self.is_dwelling = False
        self.dwell_timer.stop()
        self.target_scale = 1.0
        self.hover_scale = self.initial_hover_scale
        self._animate_scale()
        super().leaveEvent(event)

    def _on_dwell_complete(self):
        """Handle dwell timer completion - scale to final hover scale."""
        if self.is_dwelling:
            self.hover_scale = self.dwell_hover_scale
            self.target_scale = self.dwell_hover_scale
            self._animate_scale()

    def _animate_scale(self):
        """Animate the scale change."""
        start_width = int(self.base_width * self.current_scale)
        start_height = int(self.base_height * self.current_scale)
        end_width = int(self.base_width * self.target_scale)
        end_height = int(self.base_height * self.target_scale)

        start_x = self.container_x - (start_width - self.base_width) // 2
        start_y = self.container_y - (start_height - self.base_height) // 2
        end_x = self.container_x - (end_width - self.base_width) // 2
        end_y = self.container_y - (end_height - self.base_height) // 2

        start_rect = QRect(start_x, start_y, start_width, start_height)
        end_rect = QRect(end_x, end_y, end_width, end_height)

        self.scale_animation.setStartValue(start_rect)
        self.scale_animation.setEndValue(end_rect)

        def on_animation_finished():
            self.current_scale = self.target_scale
            if self.current_scale >= self.dwell_hover_scale:
                current_width = int(self.base_width * self.current_scale)
                current_height = int(self.base_height * self.current_scale)
                smaller_dimension = min(current_width, current_height)
                self.current_corner_radius = int(
                    smaller_dimension * self.hover_corner_radius_percent
                )
                scale_factor = (self.current_scale - 1.0) / (
                    self.dwell_hover_scale - 1.0
                )
                scale_factor = max(0.0, min(1.0, scale_factor))
                self._update_icon_sizes(
                    1.0 + (self.dwell_hover_scale - 1.0) * scale_factor
                )
                self._update_icon_positions(scale_factor)
            elif self.current_scale >= self.initial_hover_scale:
                current_width = int(self.base_width * self.current_scale)
                current_height = int(self.base_height * self.current_scale)
                smaller_dimension = min(current_width, current_height)
                scale_factor = (self.current_scale - 1.0) / (
                    self.dwell_hover_scale - 1.0
                )
                scale_factor = max(0.0, min(1.0, scale_factor))
                radius_percent = (
                    self.base_corner_radius_percent
                    + (
                        self.hover_corner_radius_percent
                        - self.base_corner_radius_percent
                    )
                    * scale_factor
                )
                self.current_corner_radius = int(smaller_dimension * radius_percent)
                self._update_icon_sizes(self.current_scale)
                self._update_icon_positions(scale_factor)
            else:
                smaller_dimension = min(self.base_width, self.base_height)
                self.current_corner_radius = int(
                    smaller_dimension * self.base_corner_radius_percent
                )
                self._update_icon_sizes(1.0)
                self._update_icon_positions(0.0)
            self.update()

        self.scale_animation.finished.connect(on_animation_finished)
        self.scale_animation.start()

    def paintEvent(self, event: QPaintEvent) -> None:
        """Draw the container with black background and white outline with rounded corners."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        background_rect = self.rect()
        painter.setBrush(to_qcolor("black"))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(
            background_rect, self.current_corner_radius, self.current_corner_radius
        )

        pen = QPen(to_qcolor(self.outline_color), self.outline_width)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        rect = self.rect().adjusted(
            self.outline_width // 2,
            self.outline_width // 2,
            -self.outline_width // 2,
            -self.outline_width // 2,
        )
        painter.drawRoundedRect(
            rect, self.current_corner_radius, self.current_corner_radius
        )


class ScrollView(QWidget):
    """
    A generic scrollable widget supporting:
    - Gaze-based dwell scrolling (top/bottom zones)
    - Continuous scroll while hovering
    - Auto-scroll (teleprompter style)

    Note:
        Minimum margin is recommended to be 50 pixels. To ensure proper spacing,
        the scroll view width and height should be at least +100 pixels larger than
        the content widget's width and height. If width and height are not explicitly
        provided (using defaults), they will be automatically calculated as
        content_widget dimensions + 100.

    Args:
        content_widget (Optional[QWidget]): Widget to place inside the scrollable area. Defaults to None.
        width (int): Width of the widget in pixels. Defaults to 480. If content_widget is provided
                     and default value is used, will be calculated as content_widget.width() + 100.
        height (int): Height of the widget in pixels. Defaults to 720. If content_widget is provided
                      and default value is used, will be calculated as content_widget.height() + 100.
        scroll_step (int): Number of pages to scroll on dwell. Defaults to 1.
        animation_duration (int): Duration (ms) of scroll animation. Defaults to 400.
        parent (Optional[QWidget]): Optional parent widget. Defaults to None.
        scroll_start_dwell_time (int): Delay (ms) before starting dwell scroll. Defaults to 1500.
        scroll_continue_swell_time (int): Interval (ms) between repeated scrolls during dwell. Defaults to 1200.
        show_pagination (bool): Whether to show pagination indicators. Defaults to True.
        enable_continuous_scroll (bool): Enable slow continuous scrolling while hovering. Defaults to False.
        continuous_scroll_speed (int): Pixels to scroll per continuous scroll interval. Defaults to 5.
        continuous_scroll_interval (int): Interval (ms) between continuous scroll steps. Defaults to 500.
        disable_manual_scroll (bool): If True, disables manual scrolling on mouse move. Defaults to False.
        zone_height (int): Height of the zone for dwell detection if continuous scroll is enabled. Defaults to 50.
        pagination_circle_indicator_width (int): Width of pagination circle indicator icons. Defaults to 10.
        pagination_circle_indicator_height (int): Height of pagination circle indicator icons. Defaults to 10.
        pagination_spacing_between (int): Spacing between pagination indicators. Defaults to 10.
        pagination_container_horizontal_padding (int): Horizontal padding inside pagination container. Defaults to 10.
        pagination_container_vertical_padding (int): Vertical padding above and below circles in pagination container. Defaults to 10.
        pagination_indicator_color (str): Color of inactive pagination indicators. Defaults to "#3C3C3C".
        pagination_initial_hover_scale (float): First scale on hover (before dwell). Defaults to 1.5.
        pagination_dwell_hover_scale (float): Final scale after dwell time. Defaults to 3.5.
        pagination_dwell_time (int): Time (ms) before scaling to final hover scale. Defaults to 500.
        pagination_outline_width (int): Width of pagination container outline. Defaults to 2.
        pagination_outline_color (str): Color of pagination container outline. Defaults to "white".
        pagination_corner_radius_percent (float): Corner radius as percentage (0.0-1.0). Defaults to 0.5.
        pagination_animation_duration (int): Duration (ms) of pagination hover animation. Defaults to 200.
    """

    def __init__(
        self,
        content_widget: Optional[QWidget] = None,
        width: int = 480,
        height: int = 720,
        scroll_step: int = 1,
        animation_duration: int = 400,
        parent: Optional[QWidget] = None,
        scroll_start_dwell_time: int = 1500,
        scroll_continue_swell_time: int = 1200,
        show_pagination: bool = True,
        enable_continuous_scroll: bool = False,
        continuous_scroll_speed: int = 20,
        continuous_scroll_interval: int = 50,
        disable_manual_scroll: bool = False,
        zone_height: int = 50,
        pagination_circle_indicator_width: int = 20,
        pagination_circle_indicator_height: int = 20,
        pagination_spacing_between: int = 10,
        pagination_container_horizontal_padding: int = 10,
        pagination_container_vertical_padding: int = 30,
        pagination_indicator_color: str = theme.basic_palette.gray,
        pagination_initial_hover_scale: float = 1.2,
        pagination_dwell_hover_scale: float = 3.5,
        pagination_dwell_time: int = 500,
        pagination_outline_width: int = 2,
        pagination_outline_color: str = theme.borders.color,
        pagination_corner_radius_percent: float = 0.5,
        pagination_animation_duration: int = 300,
    ) -> None:
        """
        Initialize the ScrollView widget.

        See class docstring for parameter descriptions.
        """
        super().__init__(parent)
        self.setMouseTracking(True)

        self.setFixedSize(width, height)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setStyleSheet("background-color: transparent;")

        self.zone_height = int(zone_height)
        self.bar_width = 150
        self.bar_height = 7
        self.scroll_step = int(scroll_step)
        self.animation_duration = int(animation_duration)
        self.scroll_start_dwell_time = int(scroll_start_dwell_time)
        self.enable_continuous_scroll = enable_continuous_scroll
        self.continuous_scroll_speed = int(continuous_scroll_speed)
        self.disable_manual_scroll = disable_manual_scroll
        self.show_pagination = show_pagination

        # Pagination parameters
        self.pagination_circle_indicator_width = pagination_circle_indicator_width
        self.pagination_circle_indicator_height = pagination_circle_indicator_height
        self.pagination_spacing_between = pagination_spacing_between
        self.pagination_container_horizontal_padding = (
            pagination_container_horizontal_padding
        )
        self.pagination_container_vertical_padding = (
            pagination_container_vertical_padding
        )
        self.pagination_indicator_color = pagination_indicator_color
        self.pagination_initial_hover_scale = pagination_initial_hover_scale
        self.pagination_dwell_hover_scale = pagination_dwell_hover_scale
        self.pagination_dwell_time = pagination_dwell_time
        self.pagination_outline_width = pagination_outline_width
        self.pagination_outline_color = pagination_outline_color
        self.pagination_corner_radius_percent = pagination_corner_radius_percent
        self.pagination_animation_duration = pagination_animation_duration
        self.page_dots = []
        self.current_page = 0

        self.mouse_pos = QPoint()
        self.last_zone: Optional[str] = None
        self.current_page = 0
        self.is_auto_scrolling = False
        self.auto_scroll_speed = 0

        # Timers for various scroll behaviors
        self.dwell_timer = QTimer(self)
        self.dwell_timer.setSingleShot(True)
        self.dwell_timer.timeout.connect(self.on_primary_dwell)

        self.auto_scroll_timer = QTimer(self)
        self.auto_scroll_timer.setInterval(scroll_continue_swell_time)
        self.auto_scroll_timer.timeout.connect(self.on_auto_scroll)

        self.continuous_scroll_timer = QTimer(self)
        self.continuous_scroll_timer.setInterval(continuous_scroll_interval)
        self.continuous_scroll_timer.timeout.connect(self.on_continuous_scroll)

        self.teleprompter_timer = QTimer(self)
        self.teleprompter_timer.timeout.connect(self._on_auto_scroll_tick)

        # Scroll area setup
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setMouseTracking(True)
        if content_widget:
            self.scroll_area.setWidget(content_widget)
            content_widget.setMouseTracking(True)

        # Zones for top and bottom dwell detection (only for continuous scroll)
        self.top_zone = self._create_zone()
        self.bottom_zone = self._create_zone()

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        if self.enable_continuous_scroll:
            layout.addWidget(self.top_zone)
        else:
            self.top_zone.hide()
        layout.addWidget(self.scroll_area)
        if self.enable_continuous_scroll:
            layout.addWidget(self.bottom_zone)
        else:
            self.bottom_zone.hide()

        # Initialize total_pages - always set it to prevent AttributeError
        if not self.enable_continuous_scroll:
            if content_widget is not None:
                viewport_height = self.height()
                self.total_pages = int((content_widget.height() // viewport_height) + 1)
                self.setup_pagination()
            else:
                self.total_pages = 0
        else:
            self.total_pages = 0

        log.info("ScrollView widget initialized.")

    def setup_pagination(self) -> None:
        """
        Create pagination indicators on the left side as page indicators.

        Creates circular indicators for each page and positions them vertically
        on the left side of the widget.
        """
        if self.total_pages <= 1:
            self.pagination_container = PaginationContainer(
                self,
                initial_hover_scale=self.pagination_initial_hover_scale,
                dwell_hover_scale=self.pagination_dwell_hover_scale,
                dwell_time=self.pagination_dwell_time,
                outline_width=self.pagination_outline_width,
                outline_color=self.pagination_outline_color,
                base_corner_radius_percent=self.pagination_corner_radius_percent,
                hover_corner_radius_percent=self.pagination_corner_radius_percent,
                animation_duration=self.pagination_animation_duration,
            )
            self.pagination_container.hide()
            self.indicators = []
            log.info("Skipping pagination setup - only 1 page or less")
            return

        self.pagination_container = PaginationContainer(
            self,
            initial_hover_scale=self.pagination_initial_hover_scale,
            dwell_hover_scale=self.pagination_dwell_hover_scale,
            dwell_time=self.pagination_dwell_time,
            outline_width=self.pagination_outline_width,
            outline_color=self.pagination_outline_color,
            base_corner_radius_percent=self.pagination_corner_radius_percent,
            hover_corner_radius_percent=self.pagination_corner_radius_percent,
            animation_duration=self.pagination_animation_duration,
        )

        self.indicators = []
        log.info(f"Setting up pagination with {self.total_pages} pages")
        for i in range(self.total_pages):
            circle_icon = Icon(
                is_square=False,
                size=self.pagination_circle_indicator_width,
                background_color=self.pagination_indicator_color,
            )
            circle_icon.setParent(self.pagination_container)
            circle_icon.on_clicked(self._on_pagination_click, i)
            circle_icon.show()
            self.indicators.append(circle_icon)
        log.info(f"Created {len(self.indicators)} pagination indicators")

        def position_circles():
            if not self.indicators:
                return
            scroll_area_rect = self.scroll_area.geometry()

            total_height = (
                len(self.indicators) * self.pagination_circle_indicator_height
                + (len(self.indicators) - 1) * self.pagination_spacing_between
            )
            start_y_absolute = (self.height() - total_height) // 2

            container_padding = self.pagination_container_horizontal_padding
            container_vertical_padding = self.pagination_container_vertical_padding
            container_width = self.pagination_circle_indicator_width + (
                container_padding * 2
            )

            max_scaled_width = container_width * self.pagination_dwell_hover_scale

            scroll_area_right = scroll_area_rect.x() + scroll_area_rect.width()
            container_x = scroll_area_right - (container_width + max_scaled_width) / 2
            container_y = start_y_absolute - container_vertical_padding
            container_height = total_height + (container_vertical_padding * 2)

            self.pagination_container.set_container_bounds(
                container_x, container_y, container_width, container_height
            )

            self.pagination_container.set_icons(
                self.indicators,
                container_vertical_padding,
                self.pagination_spacing_between,
            )

            icon_start_y = container_vertical_padding
            for idx, circle in enumerate(self.indicators):
                x = (container_width - self.pagination_circle_indicator_width) // 2
                y = icon_start_y + idx * (
                    self.pagination_circle_indicator_height
                    + self.pagination_spacing_between
                )
                circle.move(x, y)
                if not hasattr(circle, "_original_size"):
                    circle._original_size = self.pagination_circle_indicator_width
                circle._original_pos = (x, y, self.pagination_circle_indicator_width)
            log.debug(f"Positioned {len(self.indicators)} pagination indicators")

        original_resize = self.resizeEvent

        def new_resize(event):
            position_circles()
            if original_resize:
                original_resize(event)

        self.resizeEvent = new_resize

        self.pagination_container.show()
        self.pagination_container.raise_()
        position_circles()
        self.update_pagination_colors()

    def update_pagination_colors(self) -> None:
        """
        Update the color of pagination circles based on current page.

        Sets the current page indicator to white and all others to gray.
        """
        for idx, circle in enumerate(self.indicators):
            if idx == self.current_page:
                circle.color = to_qcolor(theme.basic_palette.white)
            else:
                circle.color = to_qcolor(self.pagination_indicator_color)
            circle.update()  # Trigger repaint

    def _on_pagination_click(self, page: int) -> None:
        """
        Handle click on pagination circle to jump to a specific page.

        Args:
            page (int): Page index to jump to (0-based).
        """
        if 0 <= page < self.total_pages:
            self.current_page = page
            log.info(f"Jumping to page: {page}")
            self.scroll_to_page(page)

    def _create_zone(self) -> QWidget:
        """
        Create a zone with a centered rounded rectangle bar that reacts to hover.

        Returns:
            QWidget: A zone widget with a scroll bar indicator that changes color on hover.
        """
        zone = QFrame(self)
        zone.setFixedHeight(self.zone_height)
        zone.setMouseTracking(True)
        zone.setStyleSheet("background-color: transparent;")

        # Inner slim bar
        bar = QWidget(zone)
        bar.setObjectName("scroll_bar")
        bar.setStyleSheet(
            """
            QWidget#scroll_bar {
                background-color: lightgray;
                border-radius: 3px;
            }
        """
        )

        def center_bar():
            bar_w = self.bar_width
            bar_h = self.bar_height
            bar.setFixedSize(bar_w, bar_h)
            bar.move((zone.width() - bar_w) // 2, (zone.height() - bar_h) // 2)

        zone.resizeEvent = lambda e: center_bar()
        center_bar()

        # Hover handlers for the entire zone (not just the bar)
        def on_enter(event):
            bar.setStyleSheet(
                """
                QWidget#scroll_bar {
                    background-color: white;
                    border-radius: 3px;
                }
            """
            )

        def on_leave(event):
            bar.setStyleSheet(
                """
                QWidget#scroll_bar {
                    background-color: lightgray;
                    border-radius: 3px;
                }
            """
            )

        zone.enterEvent = on_enter
        zone.leaveEvent = on_leave

        zone.scroll_bar = bar
        return zone

    def on_primary_dwell(self) -> None:
        """
        Handle the initial dwell trigger after the dwell time in a scroll zone.

        Starts continuous scroll timer if enabled, otherwise performs a single scroll
        and starts the auto-scroll timer for repeated scrolling.
        """
        log.debug(f"Dwell triggered in zone: {self.last_zone}")
        if self.enable_continuous_scroll:
            self.continuous_scroll_timer.start()
            log.info("Started continuous scroll timer.")
        else:
            if self.last_zone == "bottom":
                self.scroll_next()
            elif self.last_zone == "top":
                self.scroll_prev()
            self.auto_scroll_timer.start()

    def on_auto_scroll(self) -> None:
        """
        Handle repeated scrolling while hovering after initial dwell.

        Called repeatedly by the auto-scroll timer to continue scrolling in the
        direction of the dwell zone (top or bottom).
        """
        if self.last_zone == "bottom":
            self.scroll_next()
        elif self.last_zone == "top":
            self.scroll_prev()
        else:
            self.auto_scroll_timer.stop()

    def on_continuous_scroll(self) -> None:
        """
        Perform slow continuous scrolling while dwell zone is active.

        Called periodically by the continuous scroll timer to slowly advance
        the scroll position in the direction of the active zone.
        """
        zone = self.get_zone(self.mouse_pos)
        if zone != self.last_zone:
            log.debug(
                f"Exited dwell zone: {self.last_zone}, now in: {zone}. Stopping continuous scroll."
            )
            self.stop_all_scroll()
            return

        bar = self.scroll_area.verticalScrollBar()
        if self.last_zone == "bottom":
            bar.setValue(bar.value() + self.continuous_scroll_speed)
        elif self.last_zone == "top":
            bar.setValue(bar.value() - self.continuous_scroll_speed)
        else:
            self.continuous_scroll_timer.stop()

    def scroll_next(self) -> None:
        """
        Scroll to the next page.

        Advances the current page by scroll_step and animates to the new position.
        """
        if self.current_page < self.total_pages - 1:
            self.current_page += self.scroll_step
            log.info(f"Scrolling to next page: {self.current_page}")
            self.scroll_to_page(self.current_page)

    def scroll_prev(self) -> None:
        """
        Scroll to the previous page.

        Decrements the current page by scroll_step and animates to the new position.
        """
        self.current_page = max(0, self.current_page - self.scroll_step)
        log.info(f"Scrolling to previous page: {self.current_page}")
        self.scroll_to_page(self.current_page)

    def scroll_to_page(self, page: int) -> None:
        """
        Animate scrolling to the given page index.

        Args:
            page (int): Page index to scroll to (0-based).
        """
        viewport_height = self.scroll_area.viewport().height()
        target_pos = page * viewport_height
        log.debug(f"Animating scroll to position: {target_pos}")

        anim = QPropertyAnimation(self.scroll_area.verticalScrollBar(), b"value", self)
        anim.setDuration(self.animation_duration)
        anim.setStartValue(self.scroll_area.verticalScrollBar().value())
        anim.setEndValue(target_pos)
        anim.setEasingCurve(QEasingCurve.InOutQuad)
        anim.start()

        self.anim = anim  # Keep reference alive

        self.update_pagination_colors()

    def start_auto_scroll(
        self, direction: str = "down", speed: int = 2, interval: int = 30
    ) -> None:
        """
        Starts automatic scrolling like a teleprompter.

        Args:
            direction (str): 'down' or 'up'
            speed (int): Pixels per interval
            interval (int): Time between scroll steps (ms)
        """
        self.stop_all_scroll()
        self.is_auto_scrolling = True
        self.auto_scroll_speed = abs(speed) if direction == "down" else -abs(speed)
        self.teleprompter_timer.start(interval)
        log.info(
            f"Started auto scroll: direction={direction}, speed={speed}, interval={interval}ms"
        )

    def stop_auto_scroll(self) -> None:
        """
        Stop the auto-scroll mode.

        Stops the teleprompter-style automatic scrolling.
        """
        self.is_auto_scrolling = False
        self.teleprompter_timer.stop()
        log.info("Auto scroll stopped.")

    def _on_auto_scroll_tick(self) -> None:
        """
        Timer tick function for auto scroll.

        Called periodically by the teleprompter timer to advance the scroll position.
        """
        bar = self.scroll_area.verticalScrollBar()
        bar.setValue(bar.value() + self.auto_scroll_speed)

    def stop_all_scroll(self) -> None:
        """
        Stop all scrolling timers.

        Stops dwell, auto-scroll, continuous scroll, and teleprompter timers.
        """
        self.dwell_timer.stop()
        self.auto_scroll_timer.stop()
        self.continuous_scroll_timer.stop()
        self.teleprompter_timer.stop()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """
        Detect cursor position and manage dwell timers for scrolling.

        Args:
            event (QMouseEvent): Mouse move event from Qt.
        """
        if self.is_auto_scrolling or self.disable_manual_scroll:
            return

        # Only handle zone-based scrolling if continuous scroll is enabled
        if not self.enable_continuous_scroll:
            super().mouseMoveEvent(event)
            return

        self.mouse_pos = event.pos()
        zone = self.get_zone(self.mouse_pos)

        if zone == "middle":
            self.stop_all_scroll()

        if zone != self.last_zone:
            self.last_zone = zone
            self.stop_all_scroll()

            if zone in ("top", "bottom"):
                zone_widget = self.top_zone if zone == "top" else self.bottom_zone
                bar = zone_widget.scroll_bar

                # Convert global mouse pos -> zone -> bar coordinates
                local_to_zone = zone_widget.mapFromGlobal(
                    self.mapToGlobal(self.mouse_pos)
                )
                local_to_bar = bar.mapFromParent(local_to_zone)

                self.dwell_timer.start(self.scroll_start_dwell_time)
                log.debug(f"Entered {zone} zone. Dwell timer started.")

        super().mouseMoveEvent(event)

    def get_zone(self, pos: QPoint) -> str:
        """
        Get the scroll zone based on the cursor position.

        Args:
            pos (QPoint): Cursor position relative to the widget.

        Returns:
            str: 'top', 'middle', or 'bottom' depending on vertical position.
        """
        if pos.y() < self.zone_height:
            return "top"
        elif pos.y() > self.height() - self.zone_height:
            return "bottom"
        return "middle"

    def scroll_to(self, pixel_offset: int) -> None:
        """
        Instantly scroll to a specific vertical pixel offset without animation.

        Args:
            pixel_offset (int): Vertical pixel position to scroll to.
        """
        bar = self.scroll_area.verticalScrollBar()
        bar.setValue(pixel_offset)
        log.info(f"Instant scroll to pixel offset: {pixel_offset}")

    def clear(self) -> None:
        """
        Clears all content from the scroll view and resets state.

        This method:
        - Stops all timers
        - Removes the content widget
        - Clears pagination indicators
        - Resets scroll position and page state
        """
        try:
            log.info("Clearing scroll view content")

            # Stop all timers
            self.stop_all_scroll()

            # Remove content widget if it exists
            if self.scroll_area.widget():
                content_widget = self.scroll_area.widget()
                self.scroll_area.setWidget(None)
                content_widget.deleteLater()
                log.debug("Content widget removed")

            # Clear pagination indicators
            if hasattr(self, "indicators"):
                for indicator in self.indicators:
                    indicator.deleteLater()
                self.indicators.clear()
                self.page_dots.clear()
                log.debug("Pagination indicators cleared")

            # Reset state
            self.current_page = 0
            self.last_zone = None
            self.is_auto_scrolling = False
            self.auto_scroll_speed = 0

            # Reset scroll position
            bar = self.scroll_area.verticalScrollBar()
            bar.setValue(0)

            log.info("Scroll view cleared successfully")

        except Exception as e:
            log.error(f"Error clearing scroll view: {e}", exc_info=True)
