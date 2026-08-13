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
Backward-compatible import path for ``ExpandingIcon``.

The implementation moved to ``components/icon/expanding.py`` when the icon
family became a package; import from ``raven_framework.components.icon``
(or ``raven_framework.components``) in new code.
"""

from .icon.expanding import ExpandingIcon

__all__ = ["ExpandingIcon"]
