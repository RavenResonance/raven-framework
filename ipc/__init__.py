from .app_launch import (
    DEFAULT_APP_LAUNCH_SOCKET_PATH,
    AppLaunchServer,
    create_app_launch_server,
    send_app_exited,
    send_app_launched,
)


def __getattr__(name: str):
    """Lazy-load Sensorlib (stub) only when accessed."""
    if name == "Sensorlib":
        from .sensorlib import Sensorlib

        return Sensorlib
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "AppLaunchServer",
    "DEFAULT_APP_LAUNCH_SOCKET_PATH",
    "create_app_launch_server",
    "send_app_exited",
    "send_app_launched",
    "Sensorlib",
]
