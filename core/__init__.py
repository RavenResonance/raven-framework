# ================================================================
# Raven Framework - Core
#
# Copyright (c) 2026 Raven Resonance, Inc.
# All Rights Reserved.
#
# ================================================================

"""
Core application and runner for the Raven Framework.
Import from here for a cleaner API, e.g.:
  from raven_framework.core import RavenApp, RunApp
  from raven_framework.core import SimulatorRunApp, SimulatorBackgroundWidget, SimulatorBackgroundPreset
"""

from .raven_app import RavenApp
from .run_app import RunApp

_SIMULATOR_EXPORTS = {
    "SimulatorBackgroundPreset",
    "SimulatorBackgroundWidget",
    "SimulatorRunApp",
}


def __getattr__(name: str):
    if name in _SIMULATOR_EXPORTS:
        from . import raven_simulator

        return getattr(raven_simulator, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "RavenApp",
    "RunApp",
    "SimulatorBackgroundPreset",
    "SimulatorBackgroundWidget",
    "SimulatorRunApp",
]
