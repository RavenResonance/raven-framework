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
IMU (Inertial Measurement Unit) sensor for Raven Framework.

This module provides IMU functionality for reading accelerometer, gyroscope,
and magnetometer data. Only available on Raven devices via sensorlib.
"""

# Standard library imports
from typing import Optional

# Local imports
from ..helpers.logger import get_logger
from .sensor_utils import SensorType, initialize_sensorlib_client

log = get_logger("IMU")


class IMU:
    """IMU class for reading accelerometer, gyroscope, and magnetometer data."""

    def __init__(self, app_id: str = "", app_key: str = "") -> None:
        """Initialize IMU with optional app_id and app_key for entitlement verification."""
        self.sensorlib_client = initialize_sensorlib_client(
            app_id, app_key, SensorType.IMU
        )
        if not self.sensorlib_client:
            log.info("IMU: Using simulator mode (not available)")

    def get_reading(self) -> Optional[dict]:
        """Get IMU reading with accelerometer, gyroscope, and magnetometer data."""
        if self.sensorlib_client:
            try:
                return self.sensorlib_client.get_imu_reading()
            except Exception as e:
                log.error(
                    f"Error getting IMU reading via sensorlib: {e}", exc_info=True
                )
                return None
        else:
            log.warning("IMU: Cannot simulate IMU data, returning None")
            return None
