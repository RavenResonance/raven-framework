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

import importlib
import importlib.metadata
import json
import sys
import tomllib
from pathlib import Path
from unittest.mock import patch

import pytest
from pytestqt.qtbot import QtBot

import raven_framework
from raven_framework.core import deploy_app as deploy_app_module
from raven_framework.core.deploy_app import (
    _load_ravignore,
    _should_ignore_path,
    compile_app,
    copy_assets,
    copy_python_source,
)
from raven_framework.core.raven_app import RavenApp
from raven_framework.core.run_app import RunApp

# =============================================================================
# raven_framework package (__init__ exports & lazy attrs)
# =============================================================================


def test_package_exports_core_symbols() -> None:
    assert hasattr(raven_framework, "RavenApp")
    assert hasattr(raven_framework, "RunApp")
    assert hasattr(raven_framework, "TextBox")


def test_raven_framework_lazy_heavy_utils() -> None:
    fn = getattr(raven_framework, "convert_ndarray_to_base64_image")
    assert callable(fn)


def test_raven_framework_lazy_media_viewer() -> None:
    cls = getattr(raven_framework, "MediaViewer")
    assert cls.__name__ == "MediaViewer"


def test_raven_framework_unknown_attr_raises() -> None:
    # Arbitrary name not in __all__ — exercises lazy __getattr__ fallback.
    with pytest.raises(AttributeError):
        getattr(raven_framework, "not_a_real_export_ever")


@pytest.mark.parametrize("name", raven_framework.__all__)
def test_raven_framework_package_export_names_resolve(name: str) -> None:
    try:
        obj = getattr(raven_framework, name)
    except ImportError:
        if name == "HandGestureDetector":
            pytest.skip("HandGestureDetector requires optional admin/cvzone deps")
        raise
    assert obj is not None


# =============================================================================
# RavenApp
# =============================================================================


def test_raven_app_constructible(qtbot: QtBot) -> None:
    app = RavenApp(enable_gaze_marker=False)
    qtbot.addWidget(app)
    app.show()
    qtbot.waitExposed(app)
    assert app.app.width() > 0 and app.app.height() > 0


def test_raven_app_set_background_colors(qtbot: QtBot) -> None:
    app = RavenApp(enable_gaze_marker=False)
    app.set_app_background_color("#0D0D0D")
    app.set_env_background_color("#000000")
    qtbot.addWidget(app)
    app.show()
    qtbot.waitExposed(app)


# =============================================================================
# core package (reexports, RunApp, submodule import)
# =============================================================================


def test_core_package_reexports() -> None:
    from raven_framework.core import RavenApp as RA
    from raven_framework.core import RunApp as RU
    from raven_framework.core import SimulatorBackgroundPreset, SimulatorRunApp

    assert RA is RavenApp
    assert RU is RunApp
    assert SimulatorBackgroundPreset.__name__ == "SimulatorBackgroundPreset"
    assert SimulatorRunApp.__name__ == "SimulatorRunApp"


def test_core_simulator_symbols_importable() -> None:
    from raven_framework.core import (
        SimulatorBackgroundPreset,
        SimulatorBackgroundWidget,
        SimulatorRunApp,
    )

    assert SimulatorBackgroundPreset.DAY.value == "day"
    assert SimulatorBackgroundWidget.__name__ == "SimulatorBackgroundWidget"
    assert SimulatorRunApp.__name__ == "SimulatorRunApp"


def test_run_app_static_run_exists() -> None:
    assert callable(RunApp.run)


def test_core_submodule_imports() -> None:
    importlib.import_module("raven_framework.core")


# =============================================================================
# deploy_app
# =============================================================================


def test_should_ignore_path_prefix() -> None:
    assert _should_ignore_path("foo/bar.txt", ["foo"]) is True
    assert _should_ignore_path("foo", ["foo"]) is True
    assert _should_ignore_path("other/foo", ["foo"]) is False


def test_load_ravignore(tmp_path: Path) -> None:
    (tmp_path / ".ravignore").write_text(
        "*.pyc\n# comment\nignored/\n", encoding="utf-8"
    )
    patterns = _load_ravignore(str(tmp_path))
    assert "*.pyc" in patterns
    assert "ignored/" in patterns


def test_compile_app_minimal_project(tmp_path: Path) -> None:
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "main.py").write_text("# test\nx = 1\n", encoding="utf-8")
    out_dir = tmp_path / "out_compile"
    assert compile_app(str(app_dir), str(out_dir)) is True
    assert (out_dir / "main.pyc").is_file()


def test_copy_python_source_minimal_project(tmp_path: Path) -> None:
    app_dir = tmp_path / "app2"
    app_dir.mkdir()
    (app_dir / "app.py").write_text("y = 2\n", encoding="utf-8")
    out_dir = tmp_path / "out_src"
    assert copy_python_source(str(app_dir), str(out_dir)) is True
    assert (out_dir / "app.py").read_text() == "y = 2\n"


def test_copy_assets_minimal_project(tmp_path: Path) -> None:
    from PIL import Image

    app_dir = tmp_path / "app3"
    app_dir.mkdir()
    Image.new("RGB", (2, 2), color=(1, 2, 3)).save(app_dir / "photo.png")
    out_dir = tmp_path / "out_assets"
    assert copy_assets(str(app_dir), str(out_dir)) is True
    assert (out_dir / "photo.png").is_file()


def test_deploy_app_aborts_on_python_version_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A version mismatch previously only logged FATAL ERROR and kept packaging."""
    monkeypatch.setattr(deploy_app_module, "PYTHON_VERSION_ON_RAVEN_DEVICE", "9.9.9")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")

    result = deploy_app_module.deploy_app(app_name="test")

    assert result is None
    assert list(tmp_path.glob("*.rav")) == []


def test_handle_cli_deploy_upload_failure_does_not_raise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The upload request previously had no timeout or exception handling."""
    import requests

    build_path = tmp_path / "build.rav"
    build_path.write_bytes(b"fake-package")

    monkeypatch.setattr(deploy_app_module, "ACCEPTING_DEPLOYMENTS", True)
    monkeypatch.setattr(
        deploy_app_module, "deploy_app", lambda compile_pyc=True: str(build_path)
    )

    with patch(
        "requests.post", side_effect=requests.exceptions.ConnectionError("boom")
    ):
        deploy_app_module.handle_cli_deploy(
            ["deploy"], app_id="test_app", app_key="test_key"
        )


# =============================================================================
# packaging / project metadata
# =============================================================================


def test_pyproject_version_matches_distribution() -> None:
    root = Path(__file__).resolve().parent.parent
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    declared: str = pyproject["project"]["version"]

    try:
        installed = importlib.metadata.version("raven_framework")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip(
            "raven_framework is not installed; run `pip install -e .` before tests"
        )
    assert installed == declared


def test_config_json_readable() -> None:
    root = Path(__file__).resolve().parent.parent
    path = root / "config.json"
    assert path.is_file(), "config.json must be present in the framework tree"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "resolution" in data and "deployment" in data
    # ipc section is load-critical: drives is_raven_device() and all socket paths
    assert "ipc" in data, "config.json missing 'ipc' section"
    assert (
        "RAVEND_SOCKET_DIR" in data["ipc"]
    ), "config.json missing ipc.RAVEND_SOCKET_DIR"
    assert data["ipc"]["RAVEND_SOCKET_DIR"].startswith(
        "/"
    ), "RAVEND_SOCKET_DIR must be an absolute path"


def test_python_version_meets_project_requires() -> None:
    root = Path(__file__).resolve().parent.parent
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["requires-python"].strip().startswith(">=")
    assert sys.version_info >= (3, 10)
