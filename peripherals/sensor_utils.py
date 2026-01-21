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
Sensor utilities for Raven framework.

Provides utility functions for sensor operations, including device detection.
"""

from enum import Enum
from typing import Optional

from ..helpers.logger import get_logger
from ..helpers.utils_light import is_raven_device

log = get_logger("SensorUtils")


class SensorType(Enum):
    """Enum for sensor types."""

    CAMERA = "camera"
    MICROPHONE = "microphone"
    SPEAKER = "speaker"
    IMU = "imu"
    EYE_TRACKER = "eye_tracker"
    BUTTON = "button"


def initialize_sensorlib_client(
    app_id: str, app_key: str, sensor_type: SensorType
) -> Optional[object]:
    """Initialize sensorlib client with app credentials, return client or None."""
    if not is_raven_device():
        return None

    try:
        from ..socket_managers.sensorlib import Sensorlib

        sensorlib_client = Sensorlib(app_id=app_id, app_key=app_key)
        log.info(f"{sensor_type.value.capitalize()}: Using sensorlib (Raven device)")
        return sensorlib_client
    except Exception as e:
        log.error(f"Failed to initialize sensorlib: {e}")
        return None
