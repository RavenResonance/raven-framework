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
Spacer widget for adding empty space in layouts.

This module provides a simple spacer widget that can be used to add
empty space in layouts or containers.
"""

from typing import Optional

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QWidget

from ..helpers.logger import get_logger

log = get_logger("Spacer")


class Spacer(QWidget):
    """
    A simple spacer widget to add empty space in a layout or container.

    This widget provides a way to add empty space in layouts without
    using complex layout management. It's particularly useful for
    creating consistent spacing between UI elements.

    Args:
        width (int): Width of the spacer in pixels. Must be non-negative. Defaults to 0.
        height (int): Height of the spacer in pixels. Must be non-negative. Defaults to 0.
        parent (Optional[QWidget]): Parent widget. Defaults to None.

    Raises:
        ValueError: If width or height is negative.
    """

    def __init__(
        self, width: int = 0, height: int = 0, parent: Optional[QWidget] = None
    ) -> None:
        """
        Initialize the spacer widget.

        Args:
            width (int): Width of the spacer in pixels. Must be non-negative. Defaults to 0.
            height (int): Height of the spacer in pixels. Must be non-negative. Defaults to 0.
            parent (Optional[QWidget]): Parent widget. Defaults to None.

        Raises:
            ValueError: If width or height is negative.
        """
        try:
            super().__init__(parent)
            self._width = int(width)
            self._height = int(height)
            self.setFixedSize(self._width, self._height)
        except Exception as e:
            log.error(f"Failed to initialize Spacer: {e}", exc_info=True)
            raise

    def sizeHint(self) -> QSize:
        """
        Return the preferred size of the spacer.

        Returns:
            QSize: The preferred size of the spacer.
        """
        try:
            size = QSize(self._width, self._height)
            return size
        except Exception as e:
            log.error(f"Error getting spacer size hint: {e}")
            return QSize(0, 0)
