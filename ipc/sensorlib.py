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
Sensorlib — authenticated socket client for the Raven daemon layer (ravend).

On a Raven device every peripheral call is routed through a corresponding
daemon in /usr/lib/ravend/.  Each request is authenticated by the auth
daemon before the hardware operation is performed.

Wire protocol (inline — no dependency on the ravend package):
  [4-byte big-endian payload length][UTF-8 JSON payload]
Binary data (camera frames, audio) is base64-encoded inside the JSON.

This module is only instantiated when is_raven_device() returns True.
"""

import base64
import json
import socket
import struct
from typing import Any, Optional

from ..helpers.logger import get_logger
from ..helpers.utils_light import load_config

log = get_logger("Sensorlib")

# ---------------------------------------------------------------------------
# Daemon socket paths  (must match ravend/protocol.py)
# ---------------------------------------------------------------------------

_SOCKET_DIR = load_config().get("ipc", {}).get("RAVEND_SOCKET_DIR", "/run/ravend")
_AUTH_SOCKET = f"{_SOCKET_DIR}/auth.sock"
_CAMERA_SOCKET = f"{_SOCKET_DIR}/camera.sock"
_MICROPHONE_SOCKET = f"{_SOCKET_DIR}/microphone.sock"
_SPEAKER_SOCKET = f"{_SOCKET_DIR}/speaker.sock"
_IMU_SOCKET = f"{_SOCKET_DIR}/imu.sock"
_CLICK_BUTTON_SOCKET = f"{_SOCKET_DIR}/click_button.sock"

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


# ---------------------------------------------------------------------------
# Sensorlib
# ---------------------------------------------------------------------------


class Sensorlib:
    """
    Authenticated client for all Raven peripheral daemons.

    Each method opens a fresh Unix-domain connection to the relevant daemon,
    sends a JSON command (with app_id + token for auth), reads the response,
    and returns the result.  The auth daemon validates credentials against
    the Raven web server with a 5-minute in-process cache.
    """

    def __init__(self, app_id: str = "", app_key: str = "") -> None:
        """Initialise with app credentials used for every daemon request."""
        if not app_id or not app_key:
            log.warning(
                "Sensorlib: app_id or app_key is empty — all peripheral "
                "requests will be denied by the auth daemon"
            )
        self.app_id = app_id
        self.app_key = app_key
        log.info(f"Sensorlib initialised for app_id={app_id!r}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _call(
        self,
        socket_path: str,
        command: str,
        params: Optional[dict] = None,
    ) -> dict[str, Any]:
        """
        Send a command to a daemon and return the response dict.

        Raises on connection or protocol errors; callers handle exceptions.
        """
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.settimeout(_CONNECT_TIMEOUT_S)
        try:
            conn.connect(socket_path)
            conn.settimeout(None)  # blocking I/O once connected
            _send_msg(
                conn,
                {
                    "app_id": self.app_id,
                    "token": self.app_key,
                    "command": command,
                    "params": params or {},
                },
            )
            return _recv_msg(conn)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _call_ok(
        self,
        socket_path: str,
        command: str,
        params: Optional[dict] = None,
    ) -> Optional[dict[str, Any]]:
        """
        Like _call but returns the 'data' field on success, or None on failure.
        Auth-denied responses are logged as errors.
        """
        try:
            resp = self._call(socket_path, command, params)
        except Exception as exc:
            log.error(f"Sensorlib._call({command!r}): {exc}")
            return None

        status = resp.get("status")
        if status == "ok":
            return resp.get("data")
        if status == "denied":
            log.error(
                f"Sensorlib: access denied for command={command!r} "
                f"app_id={self.app_id!r} — check app_id and token"
            )
        else:
            log.error(
                f"Sensorlib: daemon error for command={command!r}: "
                f"{resp.get('message', 'unknown error')}"
            )
        return None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Verify connectivity by pinging the auth daemon."""
        try:
            conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            conn.settimeout(_CONNECT_TIMEOUT_S)
            conn.connect(_AUTH_SOCKET)
            # Send a minimal valid request — auth daemon replies with valid=False
            # for empty credentials, which is still a successful connection test.
            _send_msg(conn, {"app_id": "", "token": ""})
            _recv_msg(conn)
            conn.close()
            log.info("Sensorlib: connected (auth daemon reachable)")
            return True
        except Exception as exc:
            log.error(f"Sensorlib.connect: auth daemon unreachable: {exc}")
            return False

    def disconnect(self) -> None:
        """No-op — connections are stateless (one per call)."""

    def ping(self) -> bool:
        """Return True if the auth daemon is reachable."""
        return self.connect()

    # ------------------------------------------------------------------
    # Camera
    # ------------------------------------------------------------------

    def start_camera(self) -> bool:
        data = self._call_ok(_CAMERA_SOCKET, "start_camera")
        return bool(data and data.get("success"))

    def stop_camera(self) -> bool:
        data = self._call_ok(_CAMERA_SOCKET, "stop_camera")
        return bool(data and data.get("success"))

    def capture_image(self) -> Optional[Any]:
        """
        Capture one frame and return it as a numpy ndarray, or None on failure.
        Requires cv2 and numpy (already present on the Raven device).
        """
        data = self._call_ok(_CAMERA_SOCKET, "capture_image")
        if data is None:
            return None
        img_b64 = data.get("image_b64")
        if not img_b64:
            return None
        try:
            import cv2
            import numpy as np

            jpeg_bytes = base64.b64decode(img_b64)
            arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            return frame
        except Exception as exc:
            log.error(f"Sensorlib.capture_image: decode error: {exc}")
            return None

    # ------------------------------------------------------------------
    # Microphone
    # ------------------------------------------------------------------

    def start_microphone(self) -> bool:
        data = self._call_ok(_MICROPHONE_SOCKET, "start_microphone")
        return bool(data and data.get("success"))

    def stop_microphone(self) -> bytes:
        """Stop recording and return WAV bytes."""
        data = self._call_ok(_MICROPHONE_SOCKET, "stop_microphone")
        if data is None:
            return b""
        wav_b64 = data.get("wav_b64", "")
        if not wav_b64:
            return b""
        try:
            return base64.b64decode(wav_b64)
        except Exception as exc:
            log.error(f"Sensorlib.stop_microphone: decode error: {exc}")
            return b""

    def get_microphone_level(self) -> float:
        """Return current RMS audio level (0.0–1.0)."""
        data = self._call_ok(_MICROPHONE_SOCKET, "get_level")
        if data is None:
            return 0.0
        return float(data.get("level", 0.0))

    # ------------------------------------------------------------------
    # Speaker
    # ------------------------------------------------------------------

    def play_speaker(self, wav_bytes: bytes) -> bool:
        if not wav_bytes:
            return False
        wav_b64 = base64.b64encode(wav_bytes).decode("ascii")
        data = self._call_ok(_SPEAKER_SOCKET, "play_audio", {"wav_b64": wav_b64})
        return bool(data and data.get("success"))

    def stop_speaker(self) -> bool:
        data = self._call_ok(_SPEAKER_SOCKET, "stop_audio")
        return bool(data and data.get("success"))

    # ------------------------------------------------------------------
    # IMU
    # ------------------------------------------------------------------

    def get_imu_reading(self) -> Optional[dict]:
        """Return IMU snapshot dict or None."""
        return self._call_ok(_IMU_SOCKET, "get_imu_reading")

    # ------------------------------------------------------------------
    # Click button
    # ------------------------------------------------------------------

    def is_click_button_pressed(self) -> bool:
        data = self._call_ok(_CLICK_BUTTON_SOCKET, "is_button_pressed")
        return bool(data and data.get("pressed"))

    def wait_for_click_button_press(self, timeout: Optional[float] = None) -> bool:
        params = {"timeout": float(timeout) if timeout is not None else 5.0}
        data = self._call_ok(_CLICK_BUTTON_SOCKET, "wait_for_press", params)
        return bool(data and data.get("pressed"))

    # ------------------------------------------------------------------
    # Gaze / eye control  (routed to click_button daemon for now;
    # a dedicated eye-control daemon will replace this)
    # ------------------------------------------------------------------

    def get_gaze_position(self) -> Optional[tuple]:
        """
        Gaze data is delivered by the native eye_control binary via a
        separate DGRAM socket (see shared/eye_control_manager.py).
        This method is a pass-through stub that always returns None here;
        the EyeControl peripheral falls back to that reader on device.
        """
        return None

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> "Sensorlib":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.disconnect()
