# ================================================================
# Import smoke: framework submodules (storage tests live in test_storage.py)
# ================================================================

from __future__ import annotations

import importlib

import pytest

REQUIRED_MODULES = [
    "raven_framework",
    "raven_framework.components",
    "raven_framework.core",
    "raven_framework.peripherals",
    "raven_framework.ipc",
    "raven_framework.components.button",
    "raven_framework.components.cards",
    "raven_framework.components.container",
    "raven_framework.components.expanding_icon",
    "raven_framework.components.horizontal_container",
    "raven_framework.components.icon",
    "raven_framework.components.media_viewer",
    "raven_framework.components.model_viewer",
    "raven_framework.components.scroll_view",
    "raven_framework.components.spacer",
    "raven_framework.components.text_box",
    "raven_framework.components.vertical_container",
    "raven_framework.components.web_viewer",
    "raven_framework.core.deploy_app",
    "raven_framework.core.raven_app",
    "raven_framework.core.raven_simulator",
    "raven_framework.core.run_app",
    "raven_framework.helpers",
    "raven_framework.helpers.animation_utils",
    "raven_framework.helpers.async_runner",
    "raven_framework.helpers.font_utils",
    "raven_framework.helpers.logger",
    "raven_framework.helpers.open_ai_helper",
    "raven_framework.helpers.routine",
    "raven_framework.helpers.themes",
    "raven_framework.helpers.utils",
    "raven_framework.helpers.utils_light",
    "raven_framework.peripherals.camera",
    "raven_framework.peripherals.click_button",
    "raven_framework.peripherals.eye_control",
    "raven_framework.peripherals.imu",
    "raven_framework.peripherals.microphone",
    "raven_framework.peripherals.sensor_utils",
    "raven_framework.peripherals.speaker",
    "raven_framework.ipc.app_launch",
    "raven_framework.ipc.sensorlib",
]


@pytest.mark.parametrize("name", REQUIRED_MODULES)
def test_required_submodule_imports(name: str) -> None:
    # Any uncaught ImportError (or other exception) fails the parametrized case.
    mod = importlib.import_module(name)
    assert mod is not None


def test_ipc_package_lazy_sensorlib() -> None:
    import raven_framework.ipc as sm

    cls = getattr(sm, "Sensorlib")
    assert cls.__name__ == "Sensorlib"


def test_ipc_unknown_attribute_raises() -> None:
    import raven_framework.ipc as sm

    with pytest.raises(AttributeError):
        getattr(sm, "NotAnExport")
