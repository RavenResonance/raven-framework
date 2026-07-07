from __future__ import annotations

import json
import os
import socket
import tempfile
from dataclasses import dataclass
from typing import Any, Optional

from ..helpers.utils_light import load_config

_config = load_config()
DEFAULT_APP_LAUNCH_SOCKET_PATH = _config.get("ipc", {}).get(
    "APP_LAUNCH_SOCKET_PATH",
    os.path.join(tempfile.gettempdir(), "raven_app_launch.sock"),
)


@dataclass(frozen=True)
class AppLaunchServer:
    """Unix socket server that waits for a single 'app launched' message."""

    sock: socket.socket
    path: str

    def close(self) -> None:
        try:
            self.sock.close()
        finally:
            try:
                os.unlink(self.path)
            except FileNotFoundError:
                pass


def create_app_launch_server(
    *, path: str = DEFAULT_APP_LAUNCH_SOCKET_PATH
) -> AppLaunchServer:
    """Create a one-shot Unix domain socket server for app launch IPC."""
    if not hasattr(socket, "AF_UNIX"):
        raise RuntimeError(
            "Unix domain sockets (AF_UNIX) not supported on this platform"
        )

    try:
        os.unlink(path)
    except FileNotFoundError:
        pass

    server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server_sock.bind(path)
    server_sock.listen(1)
    return AppLaunchServer(sock=server_sock, path=path)


def send_app_launched(*, app_id: str = "", pid: Optional[int] = None) -> None:
    """
    Send a one-shot "app launched" message to the launcher (GSHELL).

    This is intentionally a no-op on platforms without Unix sockets.
    """
    if not hasattr(socket, "AF_UNIX"):
        return

    payload: dict[str, Any] = {
        "type": "app_launched",
        "app_id": app_id,
    }
    if pid is not None:
        payload["pid"] = pid

    msg = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")

    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.settimeout(1.0)
        client.connect(DEFAULT_APP_LAUNCH_SOCKET_PATH)
        client.sendall(msg)
    finally:
        try:
            client.close()
        except Exception:
            pass


def send_app_exited(*, app_id: str = "", pid: Optional[int] = None) -> None:
    """
    Send a one-shot "app exited" message to the launcher (GSHELL).

    Call this before exiting (e.g. from home button) so the launcher can switch state.
    No-op on platforms without Unix sockets.
    """
    if not hasattr(socket, "AF_UNIX"):
        return

    payload: dict[str, Any] = {
        "type": "app_exited",
        "app_id": app_id,
    }
    if pid is not None:
        payload["pid"] = pid

    msg = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")

    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.settimeout(1.0)
        client.connect(DEFAULT_APP_LAUNCH_SOCKET_PATH)
        client.sendall(msg)
    finally:
        try:
            client.close()
        except Exception:
            pass
