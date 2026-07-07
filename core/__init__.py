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
from .raven_simulator import (
    SimulatorBackgroundPreset,
    SimulatorBackgroundWidget,
    SimulatorRunApp,
)
from .run_app import RunApp

__all__ = [
    "RavenApp",
    "RunApp",
    "SimulatorBackgroundPreset",
    "SimulatorBackgroundWidget",
    "SimulatorRunApp",
]
