# ================================================================
# Raven Framework
#
# Copyright (c) 2026 Raven Resonance, Inc.
# All Rights Reserved.
#
# ================================================================

"""
Device/user identity for Raven Framework.

On Raven devices, get_username() is read from the platform daemon (ravend),
which serves the authenticated username from a local, non-secret cache file.
Apps never receive the bearer token or any auth secret.

There is no simulator equivalent — a dev laptop has no authenticated Raven
account, so get_username() returns None off-device.
"""

from typing import Optional

from ..helpers.logger import get_logger
from ..helpers.utils_light import uses_ravend_ipc

log = get_logger("Platform")


def get_username(app_id: str = "", app_key: str = "") -> Optional[str]:
    """Return the Raven account username this device is authenticated as,
    or None off-device / not yet authenticated."""
    if not uses_ravend_ipc():
        return None
    from ..ipc.platform_lib import get_username as _get_username

    try:
        return _get_username(app_id, app_key)
    except Exception as e:
        log.error(f"Error getting username via platform_lib: {e}", exc_info=True)
        return None
