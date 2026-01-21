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
Web viewer component for displaying web content in Raven SDK applications.

This module provides a wrapper around QWebEngineView for easy integration
with Raven SDK applications.
"""

from typing import Optional

from PySide6.QtCore import QSize, QUrl
from PySide6.QtWidgets import QWidget

from ..helpers.logger import get_logger

log = get_logger("WebViewer")

# Try to import QWebEngineView, handle ImportError if not available
try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
except ImportError as e:
    log.error(
        f"QWebEngineView not available: {e}. WebViewer functionality will be limited."
    )
    QWebEngineView = None  # type: ignore


class WebViewer(QWidget):
    """
    Wrapper for QWebEngineView to embed web content with optional fixed size.

    Provides a simple interface for displaying web content within Raven SDK
    applications with customizable dimensions and URL loading.

    Args:
        url (str): The URL to load in the web view. Must be a non-empty string.
        width (int, optional): Fixed width in pixels. Defaults to 300.
        height (int, optional): Fixed height in pixels. Defaults to 200.
        parent (Optional[QWidget]): Parent widget. Defaults to None.
    """

    def __init__(
        self,
        url: str,
        width: int = 300,
        height: int = 200,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Initialize the web viewer with the specified URL and dimensions.

        See class docstring for parameter descriptions.
        """
        try:
            if not url or not isinstance(url, str) or not url.strip():
                error_msg = (
                    f"url must be a non-empty string, got {type(url).__name__}: {url!r}"
                )
                log.error(error_msg, extra={"console": True})
                raise ValueError(error_msg)

            if QWebEngineView is None:
                error_msg = "QWebEngineView is not available. PySide6.QtWebEngineWidgets may not be installed."
                log.error(error_msg, extra={"console": True})
                raise ImportError(error_msg)

            super().__init__(parent)
            log.info(f"Initializing WebViewer with URL: {url}, size: {width}x{height}")

            self.web_view = QWebEngineView(self)
            self.web_view.setUrl(QUrl(url))
            self.web_view.setFixedSize(width, height)
            self.setFixedSize(width, height)

            log.info("WebViewer initialized successfully")
        except Exception as e:
            log.error(f"Failed to initialize WebViewer: {e}", exc_info=True)
            raise

    def sizeHint(self) -> QSize:
        """
        Return the preferred size of the web viewer.

        Returns:
            QSize: The preferred size of the web viewer.
        """
        if not hasattr(self, "web_view") or self.web_view is None:
            return QSize(300, 200)
        try:
            size = QSize(self.web_view.width(), self.web_view.height())
            log.debug(f"WebViewer size hint: {size}")
            return size
        except Exception as e:
            log.error(f"Error getting size hint: {e}")
            return QSize(300, 200)
