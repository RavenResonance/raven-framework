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
# Tests for raven_framework/storage/ and its filename-security helpers.
# ================================================================

from __future__ import annotations

import importlib
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

REQUIRED_FRAMEWORK_MODULES = [
    "raven_framework.storage.storage_manager",
]

OPTIONAL_FRAMEWORK_MODULES = [
    ("raven_framework.helpers.hand_gesture", "cvzone"),
]

# =============================================================================
# Submodule import smoke — required
# =============================================================================


@pytest.mark.parametrize("name", REQUIRED_FRAMEWORK_MODULES)
def test_required_submodule_imports(name: str) -> None:
    importlib.import_module(name)


# =============================================================================
# Submodule import smoke — optional (skip if heavy dep missing)
# =============================================================================


@pytest.mark.parametrize("name,reason", OPTIONAL_FRAMEWORK_MODULES)
def test_optional_submodule_imports(name: str, reason: str) -> None:
    try:
        importlib.import_module(name)
    except ImportError as e:
        pytest.skip(f"{name} not available ({reason}): {e}")


# =============================================================================
# storage_manager
# =============================================================================


def test_storage_manager_allowlists_non_empty() -> None:
    storage = importlib.import_module("raven_framework.storage.storage_manager")
    assert len(storage.ALLOWED_MEDIA_EXTENSIONS) > 0
    assert len(storage.ALLOWED_DOCUMENT_EXTENSIONS) > 0
    assert all(x.startswith(".") for x in storage.ALLOWED_MEDIA_EXTENSIONS)


# =============================================================================
# filename security validators (_is_allowed_media_filename / _is_safe_basename)
# =============================================================================

from raven_framework.storage.storage_manager import (
    _is_allowed_document_filename,
    _is_allowed_media_filename,
    _is_safe_basename,
)


def test_allowed_media_accepts_image_extensions() -> None:
    for name in ("photo.jpg", "snap.png", "clip.mp4", "vid.mov"):
        assert _is_allowed_media_filename(name), f"expected {name!r} to be allowed"


def test_allowed_media_rejects_scripts_and_executables() -> None:
    for name in ("evil.py", "run.sh", "bin.exe", "hack.rb", "x.php"):
        assert not _is_allowed_media_filename(name), f"expected {name!r} to be rejected"


def test_allowed_document_accepts_doc_extensions() -> None:
    for name in ("notes.txt", "report.pdf", "data.csv", "info.json", "readme.md"):
        assert _is_allowed_document_filename(name)


def test_allowed_document_rejects_media_extensions() -> None:
    assert not _is_allowed_document_filename("photo.jpg")
    assert not _is_allowed_document_filename("clip.mp4")


def test_safe_basename_rejects_path_traversal() -> None:
    assert not _is_safe_basename("../etc/passwd")
    assert not _is_safe_basename("subdir/photo.jpg")
    assert not _is_safe_basename(".hidden")


def test_safe_basename_accepts_plain_filename() -> None:
    assert _is_safe_basename("photo.jpg")
    assert _is_safe_basename("my_video.mp4")


# =============================================================================
# StorageManager — simulator construction + basic operations
# =============================================================================

from raven_framework.storage.storage_manager import StorageManager


def _make_simulator_storage_manager(tmp_path: Path) -> StorageManager:
    """Construct a StorageManager with its data root redirected to tmp_path."""
    with patch(
        "raven_framework.storage.storage_manager.is_raven_device", return_value=False
    ):
        sm = StorageManager.__new__(StorageManager)
        sm._on_device = False
        sm._app_id = ""
        sm._app_key = ""
        sm.data_dir = tmp_path / "user_data"
        sm.media_dir = sm.data_dir / "media"
        sm.docs_dir = sm.data_dir / "documents"
        sm.media_dir.mkdir(parents=True, exist_ok=True)
        sm.docs_dir.mkdir(parents=True, exist_ok=True)
        sm.video_filename = ""
        return sm


def test_storage_manager_save_media_creates_file(tmp_path: Path) -> None:
    sm = _make_simulator_storage_manager(tmp_path)
    frame = np.zeros((8, 8, 3), dtype=np.uint8)
    result = sm.save_media(frame, "test.jpg")
    assert result is not None
    assert Path(result).is_file()


def test_storage_manager_save_media_rejects_bad_extension(tmp_path: Path) -> None:
    sm = _make_simulator_storage_manager(tmp_path)
    frame = np.zeros((4, 4, 3), dtype=np.uint8)
    result = sm.save_media(frame, "evil.py")
    assert result is None


def test_storage_manager_list_media_files(tmp_path: Path) -> None:
    sm = _make_simulator_storage_manager(tmp_path)
    frame = np.zeros((4, 4, 3), dtype=np.uint8)
    sm.save_media(frame, "a.jpg")
    sm.save_media(frame, "b.png")
    files = sm.list_media_files()
    assert len(files) == 2
    assert all(f.endswith((".jpg", ".png")) for f in files)


def test_storage_manager_sync_data_simulator_no_crash(tmp_path: Path) -> None:
    sm = _make_simulator_storage_manager(tmp_path)
    sm.sync_data()  # must not raise — logs a message and returns


def test_storage_manager_save_document(tmp_path: Path) -> None:
    sm = _make_simulator_storage_manager(tmp_path)
    result = sm.save_document(b"hello world", "notes.txt")
    assert result is not None
    assert Path(result).read_bytes() == b"hello world"


def test_storage_manager_save_document_rejects_bad_extension(tmp_path: Path) -> None:
    sm = _make_simulator_storage_manager(tmp_path)
    with pytest.raises(ValueError):
        sm.save_document(b"data", "config.yaml")


# =============================================================================
# StorageManager.__init__ — app_uid validation and per-app sandboxing
# =============================================================================


def test_storage_manager_rejects_invalid_app_uid() -> None:
    """app_uid was previously accepted and never validated or used at all."""
    with patch(
        "raven_framework.storage.storage_manager.is_raven_device", return_value=False
    ):
        with pytest.raises(ValueError, match="Invalid app_uid"):
            StorageManager(app_uid="../escape")


def test_storage_manager_sandboxes_by_app_uid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two apps must get separate storage directories, not one shared tree."""
    import raven_framework.storage.storage_manager as sm_module

    # __init__ requires its own file to resolve to a .../raven/raven_framework/storage/
    # layout (the monorepo dev environment check) before it will use
    # resolve_under_root at all. Fake __file__ so this test doesn't depend on
    # where the real checkout happens to live on disk.
    fake_file = (
        tmp_path / "raven" / "raven_framework" / "storage" / "storage_manager.py"
    )
    monkeypatch.setattr(sm_module, "__file__", str(fake_file))

    with patch.object(sm_module, "is_raven_device", return_value=False):
        sm_a = StorageManager(app_uid="pytest_sandbox_a")
        sm_b = StorageManager(app_uid="pytest_sandbox_b")

    assert sm_a.data_dir == tmp_path / "raven" / "user_data" / "pytest_sandbox_a"
    assert sm_b.data_dir == tmp_path / "raven" / "user_data" / "pytest_sandbox_b"
    assert sm_a.data_dir != sm_b.data_dir
