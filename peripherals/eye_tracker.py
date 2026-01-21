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

# Local imports
from ..helpers.logger import get_logger
from .sensor_utils import SensorType, initialize_sensorlib_client

log = get_logger("EyeTracker")


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
            log.warning("EyeTracker: Cannot simulate gaze data, returning None")
            return None
