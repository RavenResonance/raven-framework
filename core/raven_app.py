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
Raven app container widget for Raven Framework.

This module provides the main application container widget with header controls
(close), clock display, and a main app container.
"""

import os
import sys
from typing import Optional

from PySide6.QtCore import QDateTime, Qt, QTimer
from PySide6.QtWidgets import QWidget

from ..components.container import Container
from ..components.icon import Icon
from ..components.text_box import TextBox
from ..helpers.logger import get_logger
from ..helpers.themes import RAVEN_CORE
from ..helpers.utils_light import css_color, load_config, set_custom_circle_cursor

theme = RAVEN_CORE

log = get_logger("RavenApp")

# Load configuration
_config = load_config()

# Constants for container dimensions
DISPLAY_RESOLUTION = tuple(_config["resolution"]["DISPLAY_RESOLUTION"])
APP_RESOLUTION = tuple(_config["resolution"]["APP_RESOLUTION"])
RAVEN_APP_WIDTH = DISPLAY_RESOLUTION[0]
RAVEN_APP_HEIGHT = DISPLAY_RESOLUTION[1]
APP_CONTAINER_WIDTH = APP_RESOLUTION[0]
APP_CONTAINER_HEIGHT = APP_RESOLUTION[1]

# Constants for timer intervals
TIME_UPDATE_INTERVAL_MS = 1000  # milliseconds


class RavenApp(Container):
    """
    A container page with header icons (close),
    clock display, and a main app container.

    Args:
        parent (Optional[QWidget]): Parent widget. Defaults to None.
        enable_gaze_marker (bool): Enable the gaze marker cursor. Defaults to True.
    """

    def __init__(
        self, parent: Optional[QWidget] = None, enable_gaze_marker: bool = True
    ) -> None:
        """
        Initialize the RavenApp container.

        Args:
            parent (Optional[QWidget]): Parent widget. Defaults to None.
            enable_gaze_marker (bool): Enable the gaze marker cursor. Defaults to True.
        """
        super().__init__(
            parent=parent,
            background_color=theme.basic_palette.transparent,
            border_width=0,
            border_color=theme.basic_palette.black,
            width=RAVEN_APP_WIDTH,
            height=RAVEN_APP_HEIGHT,
            spacing=0,
            corner_radius=0,
        )
        if enable_gaze_marker:
            set_custom_circle_cursor(self)
        else:
            self.setCursor(Qt.CursorShape.BlankCursor)

        self.app = Container(
            parent=parent,
            background_color=theme.colors.background_color,
            corner_radius=0,
            border_width=theme.borders.width,
            border_color=theme.basic_palette.black,
            width=APP_CONTAINER_WIDTH,
            height=APP_CONTAINER_HEIGHT,
            spacing=10,
        )
        self.add(
            self.app,
            (RAVEN_APP_WIDTH - APP_CONTAINER_WIDTH) / 2,
            ((RAVEN_APP_HEIGHT - APP_CONTAINER_HEIGHT) / 2) + 10,
        )

        # Setup icons
        here = os.path.dirname(__file__)
        home_icon_path = os.path.join(
            here, "..", _config["asset_paths"]["HOME_ICON_PATH"]
        )

        self.close_icon = Icon(is_square=False, background_image_path=home_icon_path)
        self.close_icon.on_clicked(self.on_home_clicked)

        self.time = TextBox("00:00", font_size=18, text_color="white")

        self.add(self.close_icon, APP_CONTAINER_WIDTH - 10, 10)
        self.add(self.time, APP_CONTAINER_WIDTH - self.close_icon.width() - 20, 20)

        self.update_time()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update_time)
        self._timer.start(TIME_UPDATE_INTERVAL_MS)

    def on_home_clicked(self) -> None:
        """
        Handle home button click event.

        This method is called when the home/close button is clicked.
        It shuts down the application by calling sys.exit(0).

        Note:
            This is a hard exit and should be used carefully in production.
            Consider implementing proper cleanup before exiting.
        """
        try:
            log.info(
                "Close button clicked - shutting down app...", extra={"console": True}
            )
            # QApplication.quit()
            sys.exit(0)
        except Exception as e:
            log.error(
                f"Error during app shutdown: {e}",
                exc_info=True,
                extra={"console": True},
            )
            # Force exit even if there's an error
            os._exit(1)

    def update_time(self) -> None:
        """Update the displayed time on the TextBox."""
        try:
            current = QDateTime.currentDateTime()
            self.time.setText(current.toString("HH:mm"))
        except Exception as e:
            log.error(f"Error updating time: {e}", exc_info=True)

    def set_app_background_color(self, color: str) -> None:
        """
        Change the background color of the main app container.

        Args:
            color (str): CSS color string.
        """
        try:
            background_color = css_color(color)
            self.app.update_background_style(
                background_color=background_color,
                background_image=None,
                corner_radius=None,
                border_color=None,
                border_width=None,
            )
        except Exception as e:
            log.error(f"Error setting app background color: {e}", exc_info=True)

    def set_env_background_color(self, color: str) -> None:
        """
        Change the background color of this Page container.

        Args:
            color (str): CSS color string.
        """
        try:
            background_color = css_color(color)
            self.update_background_style(
                background_color=background_color,
                background_image=None,
                corner_radius=None,
                border_color=None,
                border_width=None,
            )
        except Exception as e:
            log.error(f"Error setting env background color: {e}", exc_info=True)
