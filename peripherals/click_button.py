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

The physical click button reaches Qt as an Enter key event on Raven devices,
and the simulator maps Enter the same way — so one mechanism serves both:
an app-wide event filter that turns a double Enter press into a double-click.
"""

import time
from typing import Callable, Optional

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from ..helpers.logger import get_logger
from ..helpers.routine import Routine

log = get_logger("ClickButton")

_DEFAULT_POLL_INTERVAL_MS = 50
_DEFAULT_DOUBLE_CLICK_INTERVAL_MS = 400
# One physical Enter can deliver both Key_Return and Key_Enter; debounce those.
_ENTER_PRESS_DEBOUNCE_S = 0.1

# Shared state (one Enter-key filter for the whole app)
_double_click_pending = False
_event_filter_installed = False
_key_monitor: Optional["_ClickButtonKeyMonitor"] = None

_ENTER_KEYS = frozenset({Qt.Key.Key_Return, Qt.Key.Key_Enter})


class _ClickButtonKeyMonitor(QObject):
    """Event filter that counts debounced Enter presses toward a double-click."""

    def __init__(
        self, parent: Optional[QObject] = None, *, double_click_interval_s: float
    ) -> None:
        super().__init__(parent)
        self._double_click_interval_s = double_click_interval_s
        self._last_press_time: Optional[float] = None
        self._last_key_event_time: Optional[float] = None

    def _register_press(self) -> None:
        """Count a debounced Enter press toward a double-click."""
        global _double_click_pending

        now = time.monotonic()
        if (
            self._last_press_time is not None
            and (now - self._last_press_time) <= self._double_click_interval_s
        ):
            _double_click_pending = True
            self._last_press_time = None
        else:
            self._last_press_time = now

    def eventFilter(self, obj, event) -> bool:
        if isinstance(event, QKeyEvent) and event.key() in _ENTER_KEYS:
            if event.type() == QKeyEvent.Type.KeyPress and not event.isAutoRepeat():
                now = time.monotonic()
                if (
                    self._last_key_event_time is not None
                    and (now - self._last_key_event_time) < _ENTER_PRESS_DEBOUNCE_S
                ):
                    return False
                self._last_key_event_time = now
                self._register_press()
        return False


def _setup_key_monitoring(double_click_interval_s: float) -> None:
    """Install a single app-wide Enter key filter."""
    global _event_filter_installed, _key_monitor

    try:
        app = QApplication.instance()
        if app is None:
            log.warning(
                "ClickButton: No QApplication instance available for key monitoring"
            )
            return

        if not _event_filter_installed:
            _key_monitor = _ClickButtonKeyMonitor(
                app, double_click_interval_s=double_click_interval_s
            )
            app.installEventFilter(_key_monitor)
            _event_filter_installed = True
            log.info("ClickButton: Enter key double-press monitoring enabled")
    except Exception as e:
        log.error(f"Error setting up key monitoring: {e}", exc_info=True)


class ClickButton:
    """Physical click button; poll or register for double-click.

    The button arrives as an Enter key event on device and simulator alike,
    so detection is one shared Qt event filter — no daemon round-trips.
    """

    def __init__(
        self,
        app_id: str = "",
        app_key: str = "",
        *,
        double_click_interval_ms: int = _DEFAULT_DOUBLE_CLICK_INTERVAL_MS,
    ) -> None:
        """Initialize; app_id and app_key are kept for API compatibility."""
        self._double_click_interval_s = max(
            0.05, int(double_click_interval_ms) / 1000.0
        )
        self._poll_routine: Optional[Routine] = None

        _setup_key_monitoring(self._double_click_interval_s)
        self.key_monitor: Optional[_ClickButtonKeyMonitor] = _key_monitor

    def is_button_double_clicked(self) -> bool:
        """Return True once per double-click since the last call."""
        global _double_click_pending
        if _double_click_pending:
            _double_click_pending = False
            return True
        return False

    def is_button_clicked(self) -> bool:
        """Alias for :meth:`is_button_double_clicked`."""
        return self.is_button_double_clicked()

    def on_button_double_clicked(
        self,
        callback: Callable[[], None],
        *,
        interval_ms: int = _DEFAULT_POLL_INTERVAL_MS,
        parent: Optional[QObject] = None,
    ) -> Routine:
        """Poll for double-clicks and invoke callback on each."""

        def _poll() -> None:
            if self.is_button_double_clicked():
                callback()

        self._poll_routine = Routine(
            interval_ms=interval_ms, invoke=_poll, mode="repeat", parent=parent
        )
        return self._poll_routine

    def on_button_clicked(
        self,
        callback: Callable[[], None],
        *,
        interval_ms: int = _DEFAULT_POLL_INTERVAL_MS,
        parent: Optional[QObject] = None,
    ) -> Routine:
        """Alias for :meth:`on_button_double_clicked`."""
        return self.on_button_double_clicked(
            callback, interval_ms=interval_ms, parent=parent
        )
