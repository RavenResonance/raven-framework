#!/usr/bin/env python3
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
Platform lib — authenticated socket client for ravend's platform daemon.

Separate from Sensorlib (ipc/sensorlib.py) because identity isn't a
hardware peripheral: there's no sensor to open/close, just a single
read-only lookup against a cached, non-secret value.

Wire protocol (inline — no dependency on the ravend package):
  [4-byte big-endian payload length][UTF-8 JSON payload]

This module is only used when uses_ravend_ipc() returns True.
"""

import json
import socket
import struct
from typing import Any, Optional

from ..helpers.logger import get_logger
from ..helpers.utils_light import load_config

log = get_logger("PlatformLib")

# ---------------------------------------------------------------------------
# Daemon socket path  (must match ravend/protocol.py)
# ---------------------------------------------------------------------------

_SOCKET_DIR = load_config().get("ipc", {}).get("RAVEND_SOCKET_DIR", "/run/ravend")
_PLATFORM_SOCKET = f"{_SOCKET_DIR}/platform.sock"

_CONNECT_TIMEOUT_S = 3.0
_MAX_MESSAGE_BYTES = 32 * 1024 * 1024  # 32 MB

# ---------------------------------------------------------------------------
# Low-level socket helpers (inlined to avoid cross-package imports)
# ---------------------------------------------------------------------------


def _recvall(sock: socket.socket, n: int) -> bytes:
    buf = bytearray(n)
    view = memoryview(buf)
    received = 0
    while received < n:
        chunk = sock.recv_into(view[received:], n - received)
        if chunk == 0:
            raise ConnectionError("Socket closed before all bytes were received")
        received += chunk
    return bytes(buf)


def _send_msg(sock: socket.socket, payload: dict[str, Any]) -> None:
    data = json.dumps(payload).encode("utf-8")
    sock.sendall(struct.pack(">I", len(data)) + data)


def _recv_msg(sock: socket.socket) -> dict[str, Any]:
    header = _recvall(sock, 4)
    msg_len = struct.unpack(">I", header)[0]
    if msg_len > _MAX_MESSAGE_BYTES:
        raise ValueError(f"Response too large: {msg_len} bytes")
    raw = _recvall(sock, msg_len)
    return json.loads(raw.decode("utf-8"))


def get_username(app_id: str = "", app_key: str = "") -> Optional[str]:
    """
    Return the Raven account username this device is authenticated as, or
    None on failure / if the device hasn't authenticated yet.

    Opens a fresh Unix-domain connection to the platform daemon, sends a
    "whoami" command with app_id + token for auth, and reads the response.
    """
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.settimeout(_CONNECT_TIMEOUT_S)
    try:
        conn.connect(_PLATFORM_SOCKET)
        conn.settimeout(None)  # blocking I/O once connected
        _send_msg(
            conn,
            {"app_id": app_id, "token": app_key, "command": "whoami", "params": {}},
        )
        resp = _recv_msg(conn)
    except Exception as exc:
        log.error(f"PlatformLib.get_username: {exc}")
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass

    status = resp.get("status")
    if status == "ok":
        return (resp.get("data") or {}).get("username")
    if status == "denied":
        log.error(f"PlatformLib: access denied for app_id={app_id!r}")
    else:
        log.error(f"PlatformLib.get_username: {resp}")
    return None
