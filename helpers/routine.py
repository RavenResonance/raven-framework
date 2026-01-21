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
Routine timer wrapper for Raven Framework.

This module provides a simplified interface for QTimer-based routines that can
run periodically or as a single-shot delay.
"""

from typing import Callable, Optional

from PySide6.QtCore import QObject, QTimer

from .logger import get_logger

log = get_logger("Routine")


class Routine:
    """
    Routine wraps QTimer for easy timing behavior.

    Supports both periodic ("repeat") and single-shot ("delay") timer modes.

    Args:
        interval_ms (int): Time interval in milliseconds. Must be positive (> 0).
        invoke (Callable): Function to call on timer timeout. Must be callable.
        mode (str): "repeat" for periodic calls or "delay" for single shot. Defaults to "repeat".
        parent (Optional[QObject]): Optional Qt parent object. Defaults to None.

    Raises:
        ValueError: If mode is not "repeat" or "delay", or if interval_ms is not positive.
        TypeError: If invoke is not callable.
    """

    def __init__(
        self,
        *,
        interval_ms: int,
        invoke: Callable,
        mode: str = "repeat",
        parent: Optional[QObject] = None,
    ) -> None:
        """
        Initialize the Routine timer.

        See class docstring for parameter descriptions.
        """
        try:
            interval_ms = int(interval_ms)  # Explicit cast to int
            if interval_ms < 0:
                error_msg = f"interval_ms must be positive, got {interval_ms}"
                log.error(error_msg, extra={"console": True})
                raise ValueError(error_msg)

            if not callable(invoke):
                error_msg = f"invoke must be callable, got {type(invoke).__name__}"
                log.error(error_msg, extra={"console": True})
                raise TypeError(error_msg)

            self.timer = QTimer(parent)
            self.timer.timeout.connect(invoke)

            if mode == "repeat":
                self.timer.setSingleShot(False)
                self.timer.start(interval_ms)
            elif mode == "delay":
                self.timer.setSingleShot(True)
                self.timer.start(interval_ms)
            else:
                raise ValueError("mode must be either 'repeat' or 'delay'")
        except Exception as e:
            log.error(f"Failed to initialize Routine: {e}", exc_info=True)
            raise

    def stop(self) -> None:
        """
        Stop the routine.

        Stops the timer and prevents further invocations of the callback function.
        """
        if not hasattr(self, "timer"):
            log.warning("Attempted to stop Routine before initialization")
            return
        try:
            self.timer.stop()
        except Exception as e:
            log.error(f"Failed to stop Routine: {e}", exc_info=True)

    def is_active(self) -> bool:
        """
        Check if the routine is currently active.

        Returns:
            bool: True if the routine is currently active, False otherwise.
        """
        if not hasattr(self, "timer"):
            return False
        try:
            return self.timer.isActive()
        except Exception as e:
            log.error(f"Failed to check Routine active state: {e}", exc_info=True)
            return False
