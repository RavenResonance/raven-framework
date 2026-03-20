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
Core application and runner for the Raven Framework.
Import from here for a cleaner API, e.g.:
  from raven_framework.core import RavenApp, RunApp
  from raven_framework.core import SimulatorBackgroundWidget, SimulatorBackgroundPreset
"""

from .raven_app import RavenApp
from .raven_simulator import SimulatorBackgroundPreset, SimulatorBackgroundWidget
from .run_app import RunApp

__all__ = [
    "RavenApp",
    "RunApp",
    "SimulatorBackgroundPreset",
    "SimulatorBackgroundWidget",
]
