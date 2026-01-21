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
Media viewer widget for Raven Framework.

This module provides a widget for displaying images, GIFs, and videos with
rounded corners, auto-scaling, and playback controls.
"""

import json
import os
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QImage,
    QMovie,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPixmap,
    QRegion,
    QResizeEvent,
)
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ..helpers.logger import get_logger
from ..helpers.themes import RAVEN_CORE
from ..helpers.utils_light import load_config

theme = RAVEN_CORE

log = get_logger("MediaViewer")

# Load configuration
_config = load_config()

# Constants
# Calculate interval from FPS: 1000ms / fps
DEFAULT_VIDEO_INTERVAL_MS = int(1000 / _config["fps"]["UI_FPS"])
DEFAULT_MOVIE_SPEED = 100  # Percentage: 100 = normal speed


class MediaViewer(QWidget):
    """
    A QWidget subclass that displays images, GIFs, or videos (MP4, AVI, etc.)
    with rounded corners, auto-scaling, and playback controls.

    Args:
        media_path (Optional[str]): Path to the media file to load. Defaults to None.
        corner_radius (int): Radius for rounded corners in pixels. Defaults to theme.borders.corner_radius.
        parent (Optional[QWidget]): Parent widget. Defaults to None.
        width (int): Width of the viewer in pixels. Defaults to 400.
        height (int): Height of the viewer in pixels. Defaults to 400.
        loop_video (bool): Whether to loop video playback. Defaults to False.
        pixmap_provided (Optional[QPixmap]): Optional QPixmap to display directly. Defaults to None.
    """

    def __init__(
        self,
        media_path: Optional[str] = None,
        corner_radius: int = theme.borders.corner_radius,
        parent: Optional[QWidget] = None,
        width: int = 400,
        height: int = 400,
        loop_video: bool = False,
        pixmap_provided: Optional[QPixmap] = None,
    ) -> None:
        """
        Initialize the MediaViewer widget.

        See class docstring for parameter descriptions.
        """
        super().__init__(parent)
        log.info("Initializing MediaViewer")

        try:
            width = int(width)
            height = int(height)
            corner_radius = int(corner_radius)
        except (ValueError, TypeError) as e:
            log.error(f"Invalid width/height/corner_radius: {e}")
            raise

        self.setFixedSize(width, height)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)

        self.corner_radius = corner_radius
        self.media_path = media_path
        self.loop_video = loop_video

        self.media_layout = QVBoxLayout(self)
        self.media_layout.setContentsMargins(0, 0, 0, 0)

        self.media_widget = QLabel()
        self.media_widget.setAlignment(Qt.AlignCenter)
        self.media_layout.addWidget(self.media_widget)

        self.movie = None
        self.is_video = False
        self.cap = None
        self.timer = None
        self.pixmap_provided = pixmap_provided
        if pixmap_provided:
            scaled_pixmap = self.scaled_pixmap_cover(
                pixmap_provided, self.media_widget.width(), self.media_widget.height()
            )
            self.media_widget.setPixmap(scaled_pixmap)
        elif media_path:
            self.load_media(media_path)

    def load_media(self, path: str) -> None:
        """
        Load and display the media from the given path.

        Supports images (.jpg, .jpeg, .png, .bmp, .webp), GIFs (.gif),
        and videos (.mp4, .avi, .mov, .mkv).

        Args:
            path (str): Path to image, GIF, or video file.

        Raises:
            FileNotFoundError: If the media file does not exist (handled internally).
        """
        log.info(f"Loading media: {path}")

        if not os.path.exists(path):
            log.error(f"File not found: {path}")
            return

        ext = os.path.splitext(path)[1].lower()
        log.info(f"File extension detected: {ext}")

        # Stop any existing playback and clean up resources
        try:
            self.cleanup_video_resources()
            self.cleanup_gif_resources()
        except Exception as e:
            log.error(f"Error stopping previous media playback: {e}", exc_info=True)

        try:
            if ext in [".jpg", ".jpeg", ".png", ".bmp", ".webp"]:
                self.is_video = False
                pixmap = QPixmap(path)
                if pixmap.isNull():
                    log.error(f"Failed to load image: {path}")
                    return
                scaled_pixmap = self.scaled_pixmap_cover(
                    pixmap, self.media_widget.width(), self.media_widget.height()
                )
                self.media_widget.setPixmap(scaled_pixmap)

            elif ext == ".gif":
                self.is_video = False
                self.movie = QMovie(path)
                if self.movie.isValid():
                    self.media_widget.setFixedSize(self.width(), self.height())
                    self.movie.setScaledSize(self.media_widget.size())
                    self.movie.setCacheMode(QMovie.CacheAll)
                    self.movie.setSpeed(DEFAULT_MOVIE_SPEED)
                    self.media_widget.setMovie(self.movie)
                    self.movie.start()
                else:
                    log.error("Invalid GIF file or failed to load.")

            elif ext in [".mp4", ".avi", ".mov", ".mkv"]:
                self.is_video = True
                self.cap = cv2.VideoCapture(path)
                if not self.cap.isOpened():
                    log.error("Failed to open video file.")
                    self.cap = None
                    return

                self.timer = QTimer()
                self.timer.timeout.connect(self.next_frame)
                fps = self.cap.get(cv2.CAP_PROP_FPS)
                interval = int(1000 / fps) if fps > 0 else DEFAULT_VIDEO_INTERVAL_MS
                self.timer.start(interval)
            else:
                log.warning(f"Unsupported media type: {ext}")
        except Exception as e:
            log.error(f"Error loading media {path}: {e}", exc_info=True)

    def next_frame(self) -> None:
        """
        Called periodically by timer to fetch and display the next video frame.

        Automatically handles video looping if loop_video is enabled, and cleans up
        resources when video playback ends.
        """
        if not self.cap:
            return

        ret, frame = self.cap.read()
        if not ret:
            log.info("Video ended or cannot read frame.")
            if self.loop_video:
                log.info("Looping video...")
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                return
            else:
                self.cleanup_video_resources()
                return

        try:
            # Convert BGR to RGB
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            target_w = self.media_widget.width()
            target_h = self.media_widget.height()
            frame_h, frame_w, _ = frame.shape

            scale = max(target_w / frame_w, target_h / frame_h)
            new_w, new_h = int(frame_w * scale), int(frame_h * scale)

            resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
            x_start = (new_w - target_w) // 2
            y_start = (new_h - target_h) // 2
            cropped = resized[
                y_start : y_start + target_h, x_start : x_start + target_w
            ]

            # Ensure contiguous array for QImage
            cropped = np.ascontiguousarray(cropped)

            qt_image = QImage(
                cropped.data, target_w, target_h, 3 * target_w, QImage.Format_RGB888
            )
            pixmap = QPixmap.fromImage(qt_image)
            self.media_widget.setPixmap(pixmap)

            # Explicitly delete the frame to free memory
            del frame, resized, cropped, qt_image, pixmap

        except Exception as e:
            log.error(f"Error processing video frame: {e}", exc_info=True)

    def paintEvent(self, event: QPaintEvent) -> None:
        """
        Custom paint event to draw rounded background.

        Args:
            event: Paint event from Qt.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(0, 0, 0))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), self.corner_radius, self.corner_radius)

    def resizeEvent(self, event: QResizeEvent) -> None:
        """
        Handle resize event to maintain aspect ratio and update clipping mask.

        Args:
            event: Resize event from Qt.
        """
        super().resizeEvent(event)
        try:
            path = QPainterPath()
            path.addRoundedRect(
                QRectF(self.rect()), self.corner_radius, self.corner_radius
            )
            self.setMask(QRegion(path.toFillPolygon().toPolygon()))

            pixmap = self.media_widget.pixmap()
            if pixmap is not None and not pixmap.isNull():
                if self.is_video:
                    scaled = pixmap.scaled(
                        self.media_widget.size(),
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    )
                    self.media_widget.setPixmap(scaled)
                else:
                    if self.pixmap_provided:
                        source_pixmap = self.pixmap_provided
                    else:
                        if not self.media_path:
                            log.error("media_path is None or empty, cannot load pixmap")
                            return
                        source_pixmap = QPixmap(self.media_path)
                        if source_pixmap.isNull():
                            log.error(f"Failed to load pixmap from: {self.media_path}")
                            return
                    scaled_pixmap = self.scaled_pixmap_cover(
                        source_pixmap,
                        self.media_widget.width(),
                        self.media_widget.height(),
                    )
                    self.media_widget.setPixmap(scaled_pixmap)
        except Exception as e:
            log.error(f"Error during resizeEvent: {e}", exc_info=True)

    def cleanup_video_resources(self) -> None:
        """
        Clean up video-related resources to prevent memory leaks.
        """
        try:
            if self.timer and self.timer.isActive():
                self.timer.stop()
                self.timer.deleteLater()
                self.timer = None
            if self.cap:
                self.cap.release()
                self.cap = None
            log.debug("Video resources cleaned up")
        except Exception as e:
            log.error(f"Error cleaning up video resources: {e}", exc_info=True)

    def cleanup_gif_resources(self) -> None:
        """
        Clean up GIF-related resources to prevent memory leaks.
        """
        try:
            if self.movie:
                self.movie.stop()
                self.movie.deleteLater()
                self.movie = None
            log.debug("GIF resources cleaned up")
        except Exception as e:
            log.error(f"Error cleaning up GIF resources: {e}", exc_info=True)

    def closeEvent(self, event: QCloseEvent) -> None:
        """
        Clean up resources when the widget is closed.

        Stops video/GIF playback and releases all media resources to prevent memory leaks.

        Args:
            event: Close event from Qt.
        """
        try:
            log.info("MediaViewer closing - cleaning up resources")
            self.cleanup_video_resources()
            self.cleanup_gif_resources()

            # Clear the media widget
            if self.media_widget:
                self.media_widget.clear()
                self.media_widget.setPixmap(QPixmap())

            log.info("MediaViewer cleanup completed")
        except Exception as e:
            log.error(f"Error during closeEvent cleanup: {e}", exc_info=True)
        super().closeEvent(event)

    def scaled_pixmap_cover(
        self, pixmap: QPixmap, target_width: int, target_height: int
    ) -> QPixmap:
        """
        Scales and crops a pixmap to fill the target dimensions without distortion.

        Args:
            pixmap (QPixmap): Original image.
            target_width (int): Desired width.
            target_height (int): Desired height.

        Returns:
            QPixmap: Cropped and scaled pixmap.
        """
        try:
            scaled = pixmap.scaled(
                target_width,
                target_height,
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )
            x = (scaled.width() - target_width) // 2
            y = (scaled.height() - target_height) // 2
            return scaled.copy(x, y, target_width, target_height)
        except Exception as e:
            log.error(f"Error scaling pixmap: {e}", exc_info=True)
            return pixmap

    def play_video(self) -> None:
        """
        Resume video or GIF playback.

        Starts the video timer or unpauses the GIF animation.
        """
        try:
            if self.is_video and self.cap and self.timer and not self.timer.isActive():
                self.timer.start()
            elif self.movie:
                self.movie.setPaused(False)
        except Exception as e:
            log.error(f"Error in play_video: {e}", exc_info=True)

    def pause_video(self) -> None:
        """
        Pause video or GIF playback.

        Stops the video timer or pauses the GIF animation.
        """
        try:
            if self.is_video and self.cap and self.timer and self.timer.isActive():
                self.timer.stop()
            elif self.movie:
                self.movie.setPaused(True)
        except Exception as e:
            log.error(f"Error in pause_video: {e}", exc_info=True)

    def set_frame(self, frame: Optional[np.ndarray]) -> None:
        """
        Display a single frame from a numpy array.

        Args:
            frame (Optional[np.ndarray]): Video frame as a NumPy array in BGR format from OpenCV.
                If None, the method returns without doing anything.
        """
        if frame is None:
            return

        try:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            target_w = self.media_widget.width()
            target_h = self.media_widget.height()
            frame_h, frame_w, _ = frame.shape

            scale = max(target_w / frame_w, target_h / frame_h)
            new_w, new_h = int(frame_w * scale), int(frame_h * scale)

            resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
            x_start = (new_w - target_w) // 2
            y_start = (new_h - target_h) // 2
            cropped = resized[
                y_start : y_start + target_h, x_start : x_start + target_w
            ]

            cropped = np.ascontiguousarray(cropped)

            qt_image = QImage(
                cropped.data, target_w, target_h, 3 * target_w, QImage.Format_RGB888
            )
            self.media_widget.setPixmap(QPixmap.fromImage(qt_image))

        except Exception as e:
            log.error(f"Error in set_frame: {e}", exc_info=True)
