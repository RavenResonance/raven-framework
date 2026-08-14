# ================================================================
# Raven Framework — utils_light device detection tests
# ================================================================

from __future__ import annotations

from pathlib import Path

import pytest

from raven_framework.helpers import utils_light as ul


def test_is_raven_device_false_without_marker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    marker = tmp_path / ".is_raven_device"
    monkeypatch.setattr(ul, "RAVEN_DEVICE_MARKER_PATH", marker)
    monkeypatch.delenv("RAVEN_DEVICE", raising=False)
    assert ul.is_raven_device() is False


def test_is_raven_device_true_with_marker_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    marker = tmp_path / ".is_raven_device"
    marker.touch()
    monkeypatch.setattr(ul, "RAVEN_DEVICE_MARKER_PATH", marker)
    monkeypatch.delenv("RAVEN_DEVICE", raising=False)
    assert ul.is_raven_device() is True


def test_is_raven_device_ignores_raven_device_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    marker = tmp_path / ".is_raven_device"
    monkeypatch.setattr(ul, "RAVEN_DEVICE_MARKER_PATH", marker)
    monkeypatch.setenv("RAVEN_DEVICE", "1")
    assert ul.is_raven_device() is False


def test_uses_ravend_ipc_with_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    marker = tmp_path / ".is_raven_device"
    monkeypatch.setattr(ul, "RAVEN_DEVICE_MARKER_PATH", marker)
    monkeypatch.setenv("RAVEN_DEVICE", "1")
    assert ul.uses_ravend_ipc() is True


def test_uses_ravend_ipc_with_marker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    marker = tmp_path / ".is_raven_device"
    marker.touch()
    monkeypatch.setattr(ul, "RAVEN_DEVICE_MARKER_PATH", marker)
    monkeypatch.delenv("RAVEN_DEVICE", raising=False)
    assert ul.uses_ravend_ipc() is True


def test_hex_to_qcolor_invalid_returns_white() -> None:
    from PySide6.QtGui import QColor

    c = ul.hex_to_qcolor("not-a-color")
    assert c.red() == 255 and c.green() == 255 and c.blue() == 255
