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
Click button sensor for Raven Framework.

This module provides functionality for reading physical button state and
waiting for button presses. Only available on Raven devices via sensorlib.
"""

# Standard library imports
from typing import Optional

# Local imports
from ..helpers.logger import get_logger
from .sensor_utils import SensorType, initialize_sensorlib_client

log = get_logger("ClickButton")


class ClickButton:
    """ClickButton class for reading physical button state."""

    def __init__(self, app_id: str = "", app_key: str = "") -> None:
        """Initialize ClickButton with optional app_id and app_key for entitlement verification."""
        self.sensorlib_client = initialize_sensorlib_client(
            app_id, app_key, SensorType.BUTTON
        )
        if not self.sensorlib_client:
            log.info("ClickButton: Using simulator mode (not available)")

    def is_pressed(self) -> bool:
        """Check if ClickButton is currently pressed."""
        if self.sensorlib_client:
            try:
                return self.sensorlib_client.is_button_pressed()
            except Exception as e:
                log.error(
                    f"Error checking ClickButton state via sensorlib: {e}",
                    exc_info=True,
                )
                return False
        else:
            log.warning(
                "ClickButton: Cannot simulate ClickButton state, returning False"
            )
            return False

    def wait_for_press(self, timeout: Optional[float] = None) -> bool:
        """Wait for ClickButton press with optional timeout in seconds."""
        if self.sensorlib_client:
            try:
                return self.sensorlib_client.wait_for_button_press(timeout)
            except Exception as e:
                log.error(
                    f"Error waiting for ClickButton press via sensorlib: {e}",
                    exc_info=True,
                )
                return False
        else:
            log.warning(
                "ClickButton: Cannot simulate ClickButton press, returning False"
            )
            return False
