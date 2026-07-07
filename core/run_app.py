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
Application runner for Raven Framework.

Provides ``run()`` to start the Qt event loop with the appropriate host window
(device ``RunApp`` or desktop ``SimulatorRunApp``), plus deployment hooks.
"""

import os
import sys
import traceback
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

from ..helpers.font_utils import preload_fonts
from ..helpers.logger import get_logger
from ..helpers.routine import Routine
from ..helpers.utils_light import (
    is_raven_device,
    load_config,
    set_custom_circle_cursor,
    uses_ravend_ipc,
)
from .deploy_app import deploy_app, handle_cli_deploy
from .raven_app import RavenApp

log = get_logger("RunApp")
_config = load_config()

# Extract constants from config
DISPLAY_RESOLUTION = tuple(_config["resolution"]["DISPLAY_RESOLUTION"])
APP_WINDOW_RESOLUTION = (DISPLAY_RESOLUTION[0], DISPLAY_RESOLUTION[1])
APP_LAUNCHED_SIGNAL_DELAY_MS = _config["ipc"]["APP_LAUNCHED_SIGNAL_DELAY_MS"]
_IS_RAVEN_DEVICE = is_raven_device()


def _qt_exception_handler(exc_type, exc_value, exc_traceback) -> None:
    """Handle unhandled exceptions in Qt event loop."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    print("\n" + "=" * 80, file=sys.stderr)
    print("ERROR: Unhandled exception in your application!", file=sys.stderr)
    print("=" * 80, file=sys.stderr)
    print(error_msg, file=sys.stderr)
    print("=" * 80 + "\n", file=sys.stderr)
    log.error(f"Unhandled exception in application: {exc_value}", exc_info=True)
    sys.exit(1)


def _send_app_launched_signal(app_id: str = "", pid: Optional[int] = None) -> None:
    """Notify the launcher (GSHELL) that the app has launched. No-op when not on a Raven device."""
    log.info("RAVEN APP READY LAUNCH SIGNAL", extra={"console": True})
    if not uses_ravend_ipc():
        return
    try:
        from ..ipc.app_launch import send_app_launched

        send_app_launched(app_id=app_id, pid=pid or os.getpid())
    except Exception as e:
        log.warning(f"Failed to notify launcher that app launched: {e}")


def run(
    app_widget_fn: Callable[[], QWidget],
    app_id: str = "",
    app_key: str = "",
    use_async_loop: bool = False,
    show_overlayed_window: bool = True,
    should_preload_fonts: bool = False,
) -> None:
    """
    Run a QApplication with the host window for the app widget.

    If the first command-line argument is ``deploy`` or ``deploy-pyc``, builds and
    uploads the application package instead of running the UI.

    Args:
        app_widget_fn: Callable returning the widget instance (after QApplication exists).
        app_id: App ID (required for deployment).
        app_key: App key (required for deployment).
        use_async_loop: If True, use qasync.QEventLoop for async/await.
        show_overlayed_window: Unused — kept for backward compatibility with
            existing callers. The widget-snapshot overlay this used to enable
            was removed (it never worked; see git history for details).
        should_preload_fonts: If True, preload fonts after QApplication is created.
    """
    args = sys.argv[1:]
    if args:
        # Never log full argv — deploy keys or secrets may be passed on the CLI.
        if len(args) == 1:
            log.info("Command-line arg: %s", args[0])
        else:
            log.info("Command-line args: %d items (first: %s)", len(args), args[0])

    try:
        if len(args) > 0 and args[0] in ("deploy", "deploy-pyc"):
            handle_cli_deploy(args, app_id, app_key)
            return

        if app_widget_fn is None:
            error_msg = "app_widget_fn cannot be None"
            log.error(error_msg, extra={"console": True})
            raise ValueError(error_msg)
        if not callable(app_widget_fn):
            error_msg = (
                f"app_widget_fn must be callable, got {type(app_widget_fn).__name__}"
            )
            log.error(error_msg, extra={"console": True})
            raise ValueError(error_msg)

        app = QApplication(sys.argv)
        sys.excepthook = _qt_exception_handler

        if should_preload_fonts:
            preload_fonts()

        app_widget = app_widget_fn()
        if app_widget is None:
            error_msg = "App widget function returned None"
            print(f"ERROR: {error_msg}", file=sys.stderr)
            log.error(error_msg, extra={"console": True})
            raise ValueError(error_msg)

        if isinstance(app_widget, RavenApp):
            app_widget.bind_sleep_wake(app_id=app_id, app_key=app_key)

        if uses_ravend_ipc():
            window: QMainWindow = RunApp(app_widget)
            window.setWindowFlags(Qt.FramelessWindowHint)
        else:
            from .raven_simulator import SimulatorRunApp

            window = SimulatorRunApp(app_widget)

        window.show()
        window.move(0, 0)
        log.info("Application started.")

        Routine(
            interval_ms=APP_LAUNCHED_SIGNAL_DELAY_MS,
            invoke=lambda aid=app_id: _send_app_launched_signal(app_id=aid),
            mode="delay",
            parent=app,
        )
        if use_async_loop:
            import asyncio

            from qasync import QEventLoop

            loop = QEventLoop(app)
            asyncio.set_event_loop(loop)
            log.info("Using async event loop")
            with loop:
                loop.run_forever()
        else:
            log.info("About to start app.exec()")
            ret = app.exec()
            log.info(f"Qt event loop exited with code: {ret}")
            sys.exit(ret)
    except KeyboardInterrupt:
        log.info("Application interrupted by user")
        print("\nApplication interrupted by user (Ctrl+C)", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        error_msg = f"Application run failed: {e}"
        print("\n" + "=" * 80, file=sys.stderr)
        print("ERROR: Application failed to run!", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        print(f"Exception: {type(e).__name__}: {e}", file=sys.stderr)
        print("\nFull traceback:", file=sys.stderr)
        traceback.print_exc()
        print("=" * 80 + "\n", file=sys.stderr)
        log.error(error_msg, exc_info=True)
        sys.exit(1)


class RunApp(QMainWindow):
    """
    Hosts a Raven app widget on device: simple full-area layout (no desktop simulator).
    """

    def __init__(self, app_widget: QWidget) -> None:
        if app_widget is None:
            error_msg = "app_widget cannot be None"
            log.error(error_msg, extra={"console": True})
            raise ValueError(error_msg)

        super().__init__()
        self.background_buttons = []
        try:
            self.setWindowTitle("Raven App (alpha v0.1)")
            total_window_width = APP_WINDOW_RESOLUTION[0]
            total_window_height = APP_WINDOW_RESOLUTION[1]
            self.setFixedSize(int(total_window_width), int(total_window_height))
            container = QWidget(self)
            container.setStyleSheet("background-color: #1E1E1E;")
            layout = QVBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            app_widget.set_env_background_color("black")
            app_widget.set_app_background_color("black")
            app_widget.move(0, 0)
            layout.addWidget(app_widget, 1)

            self.setCentralWidget(container)
            set_custom_circle_cursor(app_widget)

            log.info("RunApp initialized successfully.")
        except Exception as e:
            log.error(f"Failed to initialize RunApp: {e}", exc_info=True)
            raise

    def closeEvent(self, event) -> None:
        """Clean up before the host window closes on a Raven device."""
        log.info("RunApp closing.")
        super().closeEvent(event)


RunApp.run = staticmethod(run)

if not _IS_RAVEN_DEVICE:
    RunApp.deploy_app = staticmethod(deploy_app)
