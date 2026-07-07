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

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from pytestqt.qtbot import QtBot

import raven_framework.peripherals as peripherals_pkg
from raven_framework.peripherals.camera import Camera
from raven_framework.peripherals.click_button import ClickButton
from raven_framework.peripherals.eye_control import EyeControl
from raven_framework.peripherals.imu import IMU
from raven_framework.peripherals.microphone import Microphone
from raven_framework.peripherals.sensor_utils import (
    SensorType,
    initialize_sensorlib_client,
)
from raven_framework.peripherals.speaker import Speaker

# =============================================================================
# raven_framework.peripherals package
# =============================================================================


@pytest.mark.parametrize("name", peripherals_pkg.__all__)
def test_peripherals_package_export_names_resolve(name: str) -> None:
    obj = getattr(peripherals_pkg, name)
    assert obj is not None


# =============================================================================
# sensor_utils / SensorType
# =============================================================================


def test_sensor_type_values() -> None:
    assert SensorType.CAMERA.value == "camera"
    assert SensorType.IMU.value == "imu"


def test_sensor_type_enum_values() -> None:
    assert {m.value for m in SensorType} >= {
        "camera",
        "microphone",
        "speaker",
        "imu",
        "eye_control",
        "button",
    }


def test_initialize_sensorlib_off_device_returns_none() -> None:
    assert initialize_sensorlib_client("id", "key", SensorType.CAMERA) is None


# =============================================================================
# Camera
# =============================================================================


def test_camera_init_simulator_mode() -> None:
    cam = Camera()
    assert cam.sensorlib_client is None


@patch("raven_framework.peripherals.camera.cv2.VideoCapture")
def test_camera_opencv_path(mock_cap: MagicMock) -> None:
    instance = MagicMock()
    instance.isOpened.return_value = True
    instance.read.return_value = (
        True,
        __import__("numpy").zeros((10, 10, 3), dtype="uint8"),
    )
    mock_cap.return_value = instance
    cam = Camera()
    cap = cam.open_camera()
    assert cap is not None or cam.cap is not None
    cam.close_camera()


@patch("raven_framework.peripherals.camera.cv2.VideoCapture")
def test_camera_capture_image_and_close(mock_cap: MagicMock) -> None:
    instance = MagicMock()
    instance.isOpened.return_value = True
    frame = np.zeros((4, 4, 3), dtype=np.uint8)
    instance.read.return_value = (True, frame)
    mock_cap.return_value = instance
    cam = Camera()
    out = cam.capture_camera_image_and_close()
    assert out is not None
    assert cam.cap is None


@patch("raven_framework.peripherals.camera.cv2.VideoCapture")
def test_camera_capture_and_save_image(mock_cap: MagicMock, tmp_path) -> None:
    instance = MagicMock()
    instance.isOpened.return_value = True
    frame = np.zeros((8, 8, 3), dtype=np.uint8)
    instance.read.return_value = (True, frame)
    mock_cap.return_value = instance
    cam = Camera()
    cam.open_camera()
    img = cam.capture_camera_image()
    assert img is not None
    out = tmp_path / "out.jpg"
    cam.save_image(str(out), img)
    assert out.is_file()
    cam.close_camera()


@patch("raven_framework.peripherals.camera.cv2.QRCodeDetector")
@patch("raven_framework.peripherals.camera.cv2.VideoCapture")
def test_look_for_qr_code_closes_camera_on_miss(
    mock_cap: MagicMock, mock_detector: MagicMock
) -> None:
    """look_for_qr_code previously left the camera open when no QR code was found."""
    instance = MagicMock()
    instance.isOpened.return_value = True
    frame = np.zeros((20, 20, 3), dtype=np.uint8)
    instance.read.return_value = (True, frame)
    mock_cap.return_value = instance
    mock_detector.return_value.detectAndDecode.return_value = ("", None, None)

    cam = Camera()
    result = cam.look_for_qr_code()

    assert result is None
    assert cam.cap is None
    instance.release.assert_called_once()


def test_is_camera_open_reflects_sensorlib_state() -> None:
    cam = Camera()
    cam.sensorlib_client = MagicMock()
    cam.sensorlib_client.start_camera.return_value = True
    cam.sensorlib_client.stop_camera.return_value = True

    assert cam.is_camera_open() is False
    cam.open_camera()
    assert cam.is_camera_open() is True
    cam.close_camera()
    assert cam.is_camera_open() is False


# =============================================================================
# IMU
# =============================================================================


def test_imu_simulated_reading(qtbot: QtBot) -> None:
    imu = IMU()
    r = imu.get_reading()
    assert r is not None
    assert "accelerometer" in r


# =============================================================================
# Microphone
# =============================================================================


def test_microphone_is_qobject() -> None:
    mic = Microphone()
    assert isinstance(mic.level, float)
    assert 0.0 <= mic.level <= 1.0


def test_microphone_start_recording_cleans_up_on_failure() -> None:
    """A mid-start exception previously left audio_source running with recording=False."""
    mic = Microphone()
    mic.audio_source = MagicMock()
    mic.audio_source.start.side_effect = RuntimeError("boom")

    result = mic.start_recording()

    assert result is None
    assert mic.recording is False
    assert mic.audio_device is None
    mic.audio_source.stop.assert_called_once()


def test_microphone_create_wav_uses_configured_sample_rate() -> None:
    """_create_wav_from_raw previously hardcoded 44100Hz regardless of negotiated format."""
    import io
    import wave

    mic = Microphone()
    mic._sample_rate = 22050
    wav_bytes = mic._create_wav_from_raw(b"\x00\x00" * 100)
    assert wav_bytes is not None
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        assert wf.getframerate() == 22050


# =============================================================================
# Speaker
# =============================================================================


def test_speaker_init() -> None:
    sp = Speaker()
    assert sp is not None


def test_speaker_play_stop_no_crash() -> None:
    sp = Speaker()
    sp.play_audio(b"")
    sp.stop_audio()


def test_speaker_play_audio_rejects_non_bytes(qtbot: QtBot) -> None:
    """Feeding a string (e.g. the old buggy generate_tts return) must not crash —
    on_finished should fire immediately instead of attempting to play it."""
    sp = Speaker()
    called: list[bool] = []
    sp.play_audio("not-bytes", on_finished=lambda: called.append(True))  # type: ignore[arg-type]
    assert called == [True]


def test_wav_duration_seconds_computes_correctly() -> None:
    import io
    import wave

    from raven_framework.peripherals.speaker import _wav_duration_seconds

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 16000)  # exactly 1 second of silence
    assert _wav_duration_seconds(buf.getvalue()) == pytest.approx(1.0, rel=0.01)


def test_wav_duration_seconds_invalid_bytes_returns_zero() -> None:
    from raven_framework.peripherals.speaker import _wav_duration_seconds

    assert _wav_duration_seconds(b"not a wav file") == 0.0


# =============================================================================
# EyeControl
# =============================================================================


def test_eye_control_gaze_returns_tuple_or_none(qtbot: QtBot) -> None:
    ec = EyeControl()
    pos = ec.get_gaze_position()
    assert pos is None or (isinstance(pos, tuple) and len(pos) == 2)


# =============================================================================
# ClickButton
# =============================================================================


def test_click_button_simulator_is_not_clicked() -> None:
    cb = ClickButton()
    assert cb.is_button_clicked() is False


def test_click_button_simulator_is_not_double_clicked() -> None:
    cb = ClickButton()
    assert cb.is_button_double_clicked() is False
