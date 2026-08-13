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

from __future__ import annotations

import os
import socket
import tempfile
from unittest.mock import patch

import pytest

import raven_framework.ipc as ipc_pkg
from raven_framework.ipc import app_launch
from raven_framework.ipc.app_launch import (
    DEFAULT_APP_LAUNCH_SOCKET_PATH,
    AppLaunchServer,
)
from raven_framework.ipc.sensorlib import Sensorlib

# =============================================================================
# raven_framework.ipc package
# =============================================================================


@pytest.mark.parametrize("name", ipc_pkg.__all__)
def test_ipc_package_export_names_resolve(name: str) -> None:
    obj = getattr(ipc_pkg, name)
    assert obj is not None


# =============================================================================
# app_launch — constants
# =============================================================================


def test_default_app_launch_socket_path_is_str() -> None:
    assert isinstance(DEFAULT_APP_LAUNCH_SOCKET_PATH, str)


# =============================================================================
# app_launch — create_app_launch_server / AppLaunchServer
# =============================================================================


def test_app_launch_server_dataclass_fields() -> None:
    if not hasattr(socket, "AF_UNIX"):
        pytest.skip("AF_UNIX not available")
    p = os.path.join(tempfile.gettempdir(), f"rfw_fields_{os.getpid()}.sock")
    try:
        srv = app_launch.create_app_launch_server(path=p)
    except PermissionError:
        pytest.skip("Unix socket bind not permitted in this environment")
    assert isinstance(srv, AppLaunchServer)
    assert srv.path == p
    srv.close()


def test_create_app_launch_server_unix_only() -> None:
    if not hasattr(socket, "AF_UNIX"):
        pytest.skip("AF_UNIX not available")
    sock_path = os.path.join(tempfile.gettempdir(), f"rfw_{os.getpid()}.sock")
    try:
        server = app_launch.create_app_launch_server(path=sock_path)
    except PermissionError:
        pytest.skip("Unix socket bind not permitted in this environment")
    assert server.sock.fileno() >= 0
    server.close()


# =============================================================================
# app_launch — send_app_launched / send_app_exited (no server)
# =============================================================================


def test_send_app_launched_connect_fails_without_server() -> None:
    if not hasattr(socket, "AF_UNIX"):
        pytest.skip("AF_UNIX not available")
    with pytest.raises((FileNotFoundError, ConnectionError, OSError)):
        app_launch.send_app_launched(app_id="test")


def test_send_app_exited_connect_fails_without_server() -> None:
    if not hasattr(socket, "AF_UNIX"):
        pytest.skip("AF_UNIX not available")
    with pytest.raises((FileNotFoundError, ConnectionError, OSError)):
        app_launch.send_app_exited(app_id="test")


def test_send_app_launched_roundtrip() -> None:
    if not hasattr(socket, "AF_UNIX"):
        pytest.skip("AF_UNIX not available")
    sock_path = os.path.join(tempfile.gettempdir(), f"rfw_rt_{os.getpid()}.sock")
    try:
        server = app_launch.create_app_launch_server(path=sock_path)
    except PermissionError:
        pytest.skip("Unix socket bind not permitted in this environment")

    import json
    import threading

    received = {}

    def reader() -> None:
        conn, _ = server.sock.accept()
        with conn:
            data = conn.recv(4096).decode("utf-8").strip()
            received.update(json.loads(data))

    t = threading.Thread(target=reader, daemon=True)
    t.start()

    # Point sender at our test socket
    with patch.object(app_launch, "DEFAULT_APP_LAUNCH_SOCKET_PATH", sock_path):
        app_launch.send_app_launched(app_id="test_app", pid=12345)

    t.join(timeout=2.0)
    server.close()
    assert received.get("type") == "app_launched"
    assert received.get("app_id") == "test_app"
    assert received.get("pid") == 12345


# =============================================================================
# Sensorlib — off-device behaviour (all tests run without daemons)
#
# Sensorlib is a real Unix-socket client. When no daemons are running (i.e.
# every laptop CI run) every socket call fails and the method returns a safe
# sentinel value. These tests confirm that safe-return behaviour — they are
# regression guards for "does the off-device path degrade gracefully".
# =============================================================================


def test_sensorlib_stores_credentials() -> None:
    s = Sensorlib(app_id="a", app_key="b")
    assert s.app_id == "a" and s.app_key == "b"


def test_sensorlib_off_device_connect_returns_false() -> None:
    assert Sensorlib().connect() is False


def test_sensorlib_off_device_ping_returns_false() -> None:
    assert Sensorlib().ping() is False


def test_sensorlib_off_device_camera_methods_safe() -> None:
    s = Sensorlib()
    assert s.capture_image() is None
    assert s.start_camera() is False
    assert s.stop_camera() is False


def test_sensorlib_off_device_microphone_methods_safe() -> None:
    s = Sensorlib()
    assert s.start_microphone() is False
    assert s.stop_microphone() == b""


def test_sensorlib_off_device_speaker_methods_safe() -> None:
    s = Sensorlib()
    assert s.play_speaker(b"x") is False
    assert s.stop_speaker() is False


def test_sensorlib_off_device_imu_and_eye_safe() -> None:
    s = Sensorlib()
    assert s.get_imu_reading() is None
    assert s.get_gaze_position() is None


def test_sensorlib_off_device_button_safe() -> None:
    s = Sensorlib()
    assert s.is_click_button_pressed() is False
    assert s.wait_for_click_button_press(timeout=0.01) is False


def test_sensorlib_disconnect_is_safe() -> None:
    s = Sensorlib()
    s.disconnect()  # must not raise when never connected


def test_sensorlib_context_manager_exits_cleanly() -> None:
    with Sensorlib() as s:
        assert s is not None
