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
Hardware peripherals and sensors for the Raven Framework.
Import from here for a cleaner API, e.g.:
  from raven_framework.peripherals import Camera, Microphone, Speaker, EyeTracker, IMU, ClickButton
"""

from .camera import Camera
from .click_button import ClickButton
from .eye_tracker import EyeTracker
from .imu import IMU
from .microphone import Microphone
from .sensor_utils import SensorType, initialize_sensorlib_client
from .speaker import Speaker

__all__ = [
    "Camera",
    "ClickButton",
    "EyeTracker",
    "IMU",
    "Microphone",
    "SensorType",
    "Speaker",
    "initialize_sensorlib_client",
]
