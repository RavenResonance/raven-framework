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
from ..helpers.utils_light import uses_ravend_ipc

log = get_logger("SensorUtils")


class SensorType(Enum):
    """Enum for sensor types."""

    CAMERA = "camera"
    MICROPHONE = "microphone"
    SPEAKER = "speaker"
    IMU = "imu"
    EYE_CONTROL = "eye_control"
    BUTTON = "button"


def initialize_sensorlib_client(
    app_id: str, app_key: str, sensor_type: SensorType
) -> Optional[object]:
    """Initialize sensorlib client with app credentials, return client or None.

    On a Raven device this always returns a Sensorlib instance — it never falls
    back to None (which would silently re-enable direct hardware access via
    OpenCV / Qt audio).  Any import or init failure on device is raised so the
    caller can handle it explicitly rather than bypassing the daemon layer.
    """
    if not uses_ravend_ipc():
        return None

    # On device: do NOT catch exceptions here.  If Sensorlib cannot be
    # initialised the error must propagate — we must never degrade silently
    # to direct hardware access on a real device.
    from ..ipc.sensorlib import Sensorlib

    sensorlib_client = Sensorlib(app_id=app_id, app_key=app_key)
    log.info(f"{sensor_type.value.capitalize()}: Using sensorlib (Raven device)")
    return sensorlib_client
