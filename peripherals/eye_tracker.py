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
Eye tracker sensor for Raven Framework.

This module provides eye tracking functionality for reading gaze position
coordinates. Only available on Raven devices via sensorlib.
"""

# Standard library imports
from typing import Optional, Tuple

# Qt imports
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication

# Local imports
from ..helpers.logger import get_logger
from ..helpers.utils_light import load_config
from .sensor_utils import SensorType, initialize_sensorlib_client

log = get_logger("EyeTracker")

# Load configuration
_config = load_config()
DISPLAY_RESOLUTION = tuple(_config["resolution"]["DISPLAY_RESOLUTION"])


class EyeTracker:
    """Eye tracker class for reading gaze position."""

    def __init__(self, app_id: str = "", app_key: str = "") -> None:
        """Initialize eye tracker with optional app_id and app_key for entitlement verification."""
        self.sensorlib_client = initialize_sensorlib_client(
            app_id, app_key, SensorType.EYE_TRACKER
        )
        if not self.sensorlib_client:
            log.info("EyeTracker: Using simulator mode (not available)")

    def get_gaze_position(self) -> Optional[Tuple[int, int]]:
        """Get current gaze position as (x, y) coordinates."""
        if self.sensorlib_client:
            try:
                return self.sensorlib_client.get_gaze_position()
            except Exception as e:
                log.error(
                    f"Error getting gaze position via sensorlib: {e}", exc_info=True
                )
                return None
        else:
            try:
                app = QApplication.instance()
                if app is None:
                    log.warning("EyeTracker: QApplication not available, returning None")
                    return None
                
                global_pos = QCursor.pos()
                
                target_widget = None
                for widget in app.allWidgets():
                    if widget.isVisible():
                        if hasattr(widget, 'width') and hasattr(widget, 'height'):
                            if widget.width() == DISPLAY_RESOLUTION[0] and widget.height() == DISPLAY_RESOLUTION[1]:
                                target_widget = widget
                                break
                        if widget.isWindow():
                            if hasattr(widget, 'windowTitle') and 'Raven App' in widget.windowTitle():
                                target_widget = widget
                                break
                
                if target_widget:
                    local_pos = target_widget.mapFromGlobal(global_pos)
                    x, y = local_pos.x(), local_pos.y()
                    return (x, y)
                else:
                    x, y = global_pos.x(), global_pos.y()
                    return (x, y)
            except Exception as e:
                log.error(
                    f"Error getting cursor position in simulator mode: {e}", exc_info=True
                )
                return None
