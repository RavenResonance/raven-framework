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
and magnetometer data. On Raven devices, uses sensorlib. In simulator mode,
arrow keys can be used to simulate accelerometer readings.
"""

# Standard library imports
import math
from typing import Optional

# Third-party imports
from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

# Local imports
from ..helpers.logger import get_logger
from ..helpers.utils_light import load_config
from .sensor_utils import SensorType, initialize_sensorlib_client

log = get_logger("IMU")

# Load configuration
_config = load_config()

# Simulator constants
SIMULATOR_ACCEL_SCALE = _config["peripherals"]["SIMULATOR_ACCEL_SCALE"]

# Global arrow-key state for simulator mode
_key_states = {
    Qt.Key.Key_Up: False,
    Qt.Key.Key_Down: False,
    Qt.Key.Key_Left: False,
    Qt.Key.Key_Right: False,
}

# Whether the event filter is already installed
_event_filter_installed = False


class IMUKeyMonitor(QObject):
    """Event filter to observe arrow key presses for IMU simulation."""

    def eventFilter(self, obj, event) -> bool:
        """Filter key events to update arrow key states."""
        if isinstance(event, QKeyEvent):
            key = event.key()
            if key in _key_states:
                if event.type() == QKeyEvent.Type.KeyPress:
                    _key_states[key] = True
                elif event.type() == QKeyEvent.Type.KeyRelease:
                    _key_states[key] = False
        return False


class IMU:
    """IMU class for reading accelerometer, gyroscope, and magnetometer data."""

    def __init__(self, app_id: str = "", app_key: str = "") -> None:
        """Initialize IMU with optional app_id and app_key for entitlement verification."""
        self.sensorlib_client = initialize_sensorlib_client(
            app_id, app_key, SensorType.IMU
        )
        self.key_monitor: Optional[IMUKeyMonitor] = None
        if not self.sensorlib_client:
            log.info("IMU: Using simulator mode (arrow keys for simulation)")
            self._setup_key_monitoring()

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
            return self._get_simulated_reading()

    def _setup_key_monitoring(self) -> None:
        """Set up arrow-key monitoring for simulator mode."""
        global _event_filter_installed

        try:
            app = QApplication.instance()
            if app is None:
                log.warning(
                    "IMU: No QApplication instance available for key monitoring"
                )
                return

            if not _event_filter_installed:
                self.key_monitor = IMUKeyMonitor()
                app.installEventFilter(self.key_monitor)
                _event_filter_installed = True
                log.info("IMU: Arrow key monitoring enabled for simulation")
        except Exception as e:
            log.error(f"Error setting up key monitoring: {e}", exc_info=True)

    @staticmethod
    def _head_pose_reading():
        """Gravity and turn rate for the simulator's current head pose.

        Returns (accel_y, accel_z, gyro_x, gyro_z), or None when head
        movement is off -- in which case the reading is left exactly as it
        was before this existed.

        Tilting the head by a pitch angle swings gravity out of the sensor's
        z axis and into its y axis, which is what a real accelerometer
        reports. Yaw does not move gravity at all, so a turn shows up only
        as rotation on the gyroscope, again as it would on the device.
        """
        try:
            from ..core.head_pose import tracker

            head = tracker()
            if not head.enabled:
                return None

            pitch = math.radians(head.pose().pitch)
            gyro_x = math.radians(head.pitch_rate())
            gyro_z = math.radians(head.yaw_rate())
            return (-9.8 * math.sin(pitch), 9.8 * math.cos(pitch), gyro_x, gyro_z)
        except Exception as e:
            log.debug(f"IMU: no simulator head pose available ({e})")
            return None

    def _get_simulated_reading(self) -> Optional[dict]:
        """Get simulated IMU reading based on arrow key presses.

        When the simulator's head movement is switched on, the wearer's
        pose is folded in as well, so an app reading the IMU sees the same
        motion the scene is showing. Without this the background would turn
        while the sensor insisted the head was still. Arrow keys keep
        working exactly as before, on top of it.
        """
        try:
            # Z axis defaults to gravity (9.8 m/s² pointing down)
            accel_x = 0.0
            accel_y = 0.0
            accel_z = 9.8
            gyro_x = 0.0
            gyro_y = 0.0
            gyro_z = 0.0

            head = self._head_pose_reading()
            if head is not None:
                accel_y, accel_z, gyro_x, gyro_z = head

            if _key_states[Qt.Key.Key_Left]:
                accel_x += SIMULATOR_ACCEL_SCALE

            # Right arrow: negative X acceleration (tilt right)
            if _key_states[Qt.Key.Key_Right]:
                accel_x -= SIMULATOR_ACCEL_SCALE

            # Up arrow: positive Y acceleration (tilt forward/up)
            if _key_states[Qt.Key.Key_Up]:
                accel_y += SIMULATOR_ACCEL_SCALE

            # Down arrow: negative Y acceleration (tilt backward/down)
            if _key_states[Qt.Key.Key_Down]:
                accel_y -= SIMULATOR_ACCEL_SCALE

            reading = {
                "accelerometer": {
                    "x": accel_x,
                    "y": accel_y,
                    "z": accel_z,
                },
                "gyroscope": {
                    "x": gyro_x,
                    "y": gyro_y,
                    "z": gyro_z,
                },
                "magnetometer": {
                    "x": 0.0,
                    "y": 0.0,
                    "z": 0.0,
                },
            }

            return reading
        except Exception as e:
            log.error(f"Error getting simulated IMU reading: {e}", exc_info=True)
            return None
