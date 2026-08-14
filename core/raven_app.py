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
Raven app container widget for Raven Framework.

This module provides the main application container widget with header controls
(close), clock display, and a main app container.
"""

import os
import sys
from typing import Optional

from PySide6.QtCore import QDateTime, Qt, QTimer
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QWidget

from ..components.container import Container
from ..components.icon import RevealIcon
from ..components.text_box import TextBox
from ..helpers.animation_utils import fade_in, fade_out, resolve_curve
from ..helpers.logger import get_logger
from ..helpers.themes import RAVEN_CORE
from ..helpers.utils_light import (
    css_color,
    is_raven_device,
    load_config,
    set_custom_circle_cursor,
)
from ..peripherals.click_button import ClickButton

theme = RAVEN_CORE

log = get_logger("RavenApp")

# Load configuration
_config = load_config()

# Constants for container dimensions
DISPLAY_RESOLUTION = tuple(_config["resolution"]["DISPLAY_RESOLUTION"])
APP_RESOLUTION = tuple(_config["resolution"]["APP_RESOLUTION"])
RAVEN_APP_WIDTH = DISPLAY_RESOLUTION[0]
RAVEN_APP_HEIGHT = DISPLAY_RESOLUTION[1]
APP_CONTAINER_WIDTH = APP_RESOLUTION[0]
APP_CONTAINER_HEIGHT = APP_RESOLUTION[1]

# Constants for timer intervals
TIME_UPDATE_INTERVAL_MS = 1000  # milliseconds
ENABLE_TIME_DISPLAY = False

APP_EXIT_FADE_MS = _config["animation"]["app_launch"]["APP_EXIT_FADE_MS"]

# How long the home button's launch blackout stays fully black after its
# sweep, so the exit fade underneath finishes out of sight.
HOME_BLACKOUT_HOLD_MS = _config["animation"]["app_launch"]["HOME_BLACKOUT_HOLD_MS"]

_wake_cfg = _config["animation"]["wake"]


class RavenApp(Container):
    """
    A container page with header icons (close),
    clock display, and a main app container.

    Args:
        parent (Optional[QWidget]): Parent widget. Defaults to None.
        enable_gaze_marker (bool): Apply gaze marker cursor from config when True.
            When False, the cursor is hidden. Defaults to True.
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        enable_gaze_marker: bool = True,
    ) -> None:
        """
        Initialize the RavenApp container.

        Args:
            parent (Optional[QWidget]): Parent widget. Defaults to None.
            enable_gaze_marker (bool): Apply gaze marker cursor from config when True.
                When False, the cursor is hidden. Defaults to True.
        """
        super().__init__(
            parent=parent,
            background_color=theme.basic_palette.transparent,
            border_width=0,
            border_color=theme.basic_palette.black,
            width=RAVEN_APP_WIDTH,
            height=RAVEN_APP_HEIGHT,
            spacing=0,
            corner_radius=0,
        )
        if enable_gaze_marker:
            set_custom_circle_cursor(self)
        else:
            self.setCursor(Qt.CursorShape.BlankCursor)

        self.app = Container(
            parent=parent,
            background_color=theme.colors.background_color,
            corner_radius=0,
            border_width=theme.borders.width,
            border_color=theme.basic_palette.black,
            width=APP_CONTAINER_WIDTH,
            height=APP_CONTAINER_HEIGHT,
            spacing=10,
        )
        self.add(
            self.app,
            (RAVEN_APP_WIDTH - APP_CONTAINER_WIDTH) / 2,
            ((RAVEN_APP_HEIGHT - APP_CONTAINER_HEIGHT) / 2) + 10,
        )

        here = os.path.dirname(__file__)
        home_icon_path = os.path.join(
            here, "..", _config["asset_paths"]["APPS_ICON_PATH"]
        )

        close_icon_size = 80
        # Reveal home button: the dwell expands it to black and sweeps the
        # launch blackout across the entire app before on_home_clicked fires.
        # The blackout then holds full-black long enough for the app's exit
        # fade to play out hidden behind it — a dwell exit cuts straight to
        # black, while a plain click (no expand/blackout) keeps the visible
        # exit fade.
        self.close_icon = RevealIcon(
            is_square=False,
            background_image_path=home_icon_path,
            size=close_icon_size,
            overlay_parent=self,
            screen_width=RAVEN_APP_WIDTH,
            screen_height=RAVEN_APP_HEIGHT,
            blackout_hold_ms=HOME_BLACKOUT_HOLD_MS,
        )
        self.close_icon.on_clicked(self.on_home_clicked)
        # Reveal icons pad their widget for scale overflow; offset by the
        # circle's position inside the widget so the visible icon lands where
        # the unpadded icon used to.
        icon_left, icon_top, _, _ = self.close_icon.circle_bounds_in_widget()
        self.add(
            self.close_icon,
            RAVEN_APP_WIDTH - close_icon_size - 13 - icon_left,
            15 - icon_top,
        )
        self.close_icon.raise_()

        # Catches gaze/mouse while asleep (simulator composite is mouse-transparent)
        self._sleep_overlay = Container(
            width=RAVEN_APP_WIDTH,
            height=RAVEN_APP_HEIGHT,
            background_color=theme.basic_palette.transparent,
            border_width=0,
            border_color=theme.basic_palette.black,
            spacing=0,
            corner_radius=0,
        )
        self.add(self._sleep_overlay, 0, 0)
        self._sleep_overlay.hide()

        if ENABLE_TIME_DISPLAY:
            self.time = TextBox("00:00", font_size=18, text_color="white")
            self.add(self.time, APP_CONTAINER_WIDTH - self.close_icon.width() - 20, 20)
            self.update_time()
            self._timer = QTimer(self)
            self._timer.timeout.connect(self.update_time)
            self._timer.start(TIME_UPDATE_INTERVAL_MS)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # Explicitly request focus rather than relying on Qt/the compositor
        # to hand it to us automatically on window activation — StrongFocus
        # alone doesn't guarantee that, especially once this widget is
        # rechilded into RunApp's layout (see RunApp.__init__, which
        # re-asserts this after embedding).
        self.setFocus()

        self.app_id = ""
        self.is_awake = True
        self._fade_ms = (
            _wake_cfg["FADE_MS_RAVEN_DEVICE"]
            if is_raven_device()
            else _wake_cfg["FADE_MS_SIMULATOR"]
        )
        self._fade_curve = resolve_curve(_wake_cfg["FADE_CURVE"])
        self._wake_brightness_gain = _wake_cfg["WAKE_BRIGHTNESS_GAIN"]
        self._sleep_brightness_gain = _wake_cfg["SLEEP_BRIGHTNESS_GAIN"]

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Enter/Return exits the app via the same path as the close icon.

        Framework-level so any RavenApp-based dev app gets an exit key for
        free, without the app author needing to wire up their own key
        handling or call bind_sleep_wake().

        Logs every key (not just Enter/Return) — if this widget isn't
        actually receiving keyboard focus, nothing here fires at all, so an
        unconditional log is what lets that be diagnosed from the console
        output rather than assumed.
        """
        log.info("RavenApp keyPressEvent: key=%s", event.key(), extra={"console": True})
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            log.info("Enter pressed — exiting app", extra={"console": True})
            self.on_home_clicked()
        super().keyPressEvent(event)

    def bind_sleep_wake(self, app_id: str = "", app_key: str = "") -> None:
        """Wire double-click (Enter in simulator) to fade the UI in and out."""
        self.app_id = app_id
        self.click_button = ClickButton(app_id=app_id, app_key=app_key)
        self._click_button_routine = self.click_button.on_button_double_clicked(
            self._toggle_sleep_wake, parent=self
        )

    def _toggle_sleep_wake(self) -> None:
        if self.is_awake:
            self.sleep()
        else:
            self.wake()

    def _set_ui_interaction_blocked(self, blocked: bool) -> None:
        """Block all in-app UI while asleep; wake remains on double-click only."""
        if blocked:
            self.close_icon.set_disabled(True)
            self.app.setEnabled(False)
            self._sleep_overlay.show()
            self._sleep_overlay.raise_()
            return
        self._sleep_overlay.hide()
        self.app.setEnabled(True)
        self.close_icon.set_disabled(False)

    def _fade_ui_for_sleep_wake(self, *, sleeping: bool) -> None:
        """Fade the visible UI; simulator composites on a label, not the live
        widget. On device the window is always ``RunApp``, so skip (and never
        import) the simulator — it's heavy to load."""
        if not is_raven_device():
            from .raven_simulator import SimulatorRunApp

            win = self.window()
            if isinstance(win, SimulatorRunApp):
                if sleeping:
                    win.sleep_app_ui(self._fade_ms, self._fade_curve)
                else:
                    win.wake_app_ui(self._fade_ms, self._fade_curve)
                return
        if sleeping:
            fade_out(self, duration=self._fade_ms, curve=self._fade_curve)
        else:
            fade_in(self, duration=self._fade_ms, curve=self._fade_curve)

    def _change_brightness_gain(self, brightness_gain: int) -> None:
        if is_raven_device():
            try:
                from sys_utils.subprocess_manager import (
                    run_lightengine_gain,
                )  # type: ignore

                run_lightengine_gain(brightness_gain)
            except ImportError:
                log.debug("subprocess_manager not available — brightness unchanged")
            log.info(
                f"Running lightengine --gain {brightness_gain}",
                extra={"console": True},
            )

    def sleep(self) -> None:
        """Fade out the entire app UI."""
        if not self.is_awake:
            return
        self._set_ui_interaction_blocked(True)
        self._fade_ui_for_sleep_wake(sleeping=True)
        self._change_brightness_gain(self._sleep_brightness_gain)
        self.is_awake = False
        log.info("RavenApp UI asleep", extra={"console": True})

    def wake(self) -> None:
        """Fade in the entire app UI."""
        if self.is_awake:
            return
        self._fade_ui_for_sleep_wake(sleeping=False)
        self._change_brightness_gain(self._wake_brightness_gain)
        self.is_awake = True
        self._set_ui_interaction_blocked(False)
        log.info("RavenApp UI awake", extra={"console": True})

    def on_home_clicked(self) -> None:
        """
        Handle home button click event.

        Fades the app content out (the exit mirror of the launch reveal), then
        closes the window and quits so RunApp.closeEvent can stop timers and
        worker threads. The exit signal is sent after the fade, so the launcher
        fades back in only once the app has faded out.
        """
        if getattr(self, "_exiting", False):
            return
        self._exiting = True
        try:
            log.info("Close button clicked - fading out...", extra={"console": True})
            self._set_ui_interaction_blocked(True)
            win = self.window()
            if win is not None and hasattr(win, "conceal"):
                win.conceal(APP_EXIT_FADE_MS)
                QTimer.singleShot(APP_EXIT_FADE_MS, self._finalize_exit)
            else:
                self._finalize_exit()
        except Exception as e:
            log.error(
                f"Error starting app shutdown: {e}",
                exc_info=True,
                extra={"console": True},
            )
            self._finalize_exit()

    def _finalize_exit(self) -> None:
        """After the exit fade: signal the launcher, close the window, quit."""
        try:
            log.info("RAVEN APP READY EXITED SIGNAL", extra={"console": True})
            if is_raven_device():
                try:
                    from ..ipc.app_launch import send_app_exited

                    send_app_exited(app_id=self.app_id, pid=os.getpid())
                except Exception as e:
                    log.debug(f"Failed to send app_exited IPC: {e}")
            win = self.window()
            if win is not None:
                win.close()
            app = QApplication.instance()
            if app is not None:
                app.quit()
        except Exception as e:
            log.error(
                f"Error during app shutdown: {e}",
                exc_info=True,
                extra={"console": True},
            )
            try:
                if QApplication.instance() is not None:
                    QApplication.instance().quit()
            except Exception:
                pass
            # sys.exit (not os._exit) so atexit handlers and log flushing
            # still run during shutdown.
            sys.exit(1)

    def update_time(self) -> None:
        """Update the displayed time on the TextBox."""
        try:
            current = QDateTime.currentDateTime()
            self.time.setText(current.toString("HH:mm"))
        except Exception as e:
            log.error(f"Error updating time: {e}", exc_info=True)

    def set_app_background_color(self, color: str) -> None:
        """
        Change the background color of the main app container.

        Args:
            color (str): CSS color string.
        """
        try:
            background_color = css_color(color)
            self.app.update_background_style(
                background_color=background_color,
                background_image=None,
                corner_radius=None,
                border_color=None,
                border_width=None,
            )
        except Exception as e:
            log.error(f"Error setting app background color: {e}", exc_info=True)

    def set_env_background_color(self, color: str) -> None:
        """
        Change the background color of this Page container.

        Args:
            color (str): CSS color string.
        """
        try:
            background_color = css_color(color)
            self.update_background_style(
                background_color=background_color,
                background_image=None,
                corner_radius=None,
                border_color=None,
                border_width=None,
            )
        except Exception as e:
            log.error(f"Error setting env background color: {e}", exc_info=True)
