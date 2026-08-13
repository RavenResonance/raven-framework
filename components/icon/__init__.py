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
Icon components for Raven Framework.

Three sibling icon widgets:

- ``Icon`` — the classic dwell icon: hover scales it up and a visible
  progress indicator fills over ``dwell_time`` before ``clicked`` fires.
- ``RevealIcon`` — the launch treatment: hover grows the icon and shows a
  halo, a breath pulse acts as the dwell timer, and completion expands the
  icon (optionally sweeping a fullscreen blackout — see
  ``LaunchBlackoutOverlay``).
- ``ExpandingIcon`` — a clickable scaling container for embedded content
  widgets.

This package replaced the single ``components/icon.py`` module; importing
``Icon`` (and ``SCALE_THRESHOLD``) from ``components.icon`` keeps working
unchanged.
"""

from .expanding import ExpandingIcon
from .icon import SCALE_THRESHOLD, Icon
from .reveal import (
    DEFAULT_BOTTOM_TEXT_SPACING,
    DEFAULT_EXTRA_WIDTH,
    LaunchBlackoutOverlay,
    RevealIcon,
)

__all__ = [
    "DEFAULT_BOTTOM_TEXT_SPACING",
    "DEFAULT_EXTRA_WIDTH",
    "ExpandingIcon",
    "Icon",
    "LaunchBlackoutOverlay",
    "RevealIcon",
    "SCALE_THRESHOLD",
]
