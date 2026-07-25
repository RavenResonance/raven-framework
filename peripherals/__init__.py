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
  from raven_framework.peripherals import Camera, Microphone, Speaker, EyeControl, IMU, ClickButton

Peripherals are imported lazily (PEP 562): pulling in one — or importing a
single submodule like ``peripherals.click_button`` — no longer drags in every
other peripheral. That matters because ``Camera`` imports OpenCV (~2s), which
would otherwise load on every app launch even when no camera is used.
"""

from importlib import import_module

# name -> submodule that defines it
_LAZY_EXPORTS = {
    "Camera": "camera",
    "ClickButton": "click_button",
    "EyeControl": "eye_control",
    "IMU": "imu",
    "Microphone": "microphone",
    "Speaker": "speaker",
    "SensorType": "sensor_utils",
    "initialize_sensorlib_client": "sensor_utils",
}


def __getattr__(name: str):
    submodule = _LAZY_EXPORTS.get(name)
    if submodule is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(f".{submodule}", __name__)
    return getattr(module, name)


def __dir__():
    return sorted(list(globals().keys()) + list(_LAZY_EXPORTS))


__all__ = [
    "Camera",
    "ClickButton",
    "EyeControl",
    "IMU",
    "Microphone",
    "SensorType",
    "Speaker",
    "initialize_sensorlib_client",
]
