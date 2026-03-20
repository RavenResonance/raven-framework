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

from __future__ import annotations

"""
Media viewer widget for Raven Framework.

This module provides a widget for displaying images, GIFs, and videos with
rounded corners, auto-scaling, and playback controls.
"""

import os
import re
import tempfile
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    import numpy as np

from PySide6.QtCore import QRectF, QSize, Qt, QTimer
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

from ..helpers.async_runner import AsyncRunner
from ..helpers.logger import get_logger
from ..helpers.themes import RAVEN_CORE
from ..helpers.utils_light import load_config

_QT_FORMAT_BGR = getattr(QImage, "Format_BGR888", None) or getattr(
    getattr(QImage, "Format", None), "Format_BGR888", None
)

theme = RAVEN_CORE
log = get_logger("MediaViewer")

# Load configuration
_config = load_config()

# Constants
# Calculate interval from FPS: 1000ms / fps
DEFAULT_VIDEO_INTERVAL_MS = int(1000 / _config["fps"]["UI_FPS"])
HTTP_USER_AGENT = _config["http"]["USER_AGENT"]
DEFAULT_MOVIE_SPEED = 100  # Percentage: 100 = normal speed
DOWNLOAD_CHUNK_SIZE = 256 * 1024  # 256 KB for streaming URL downloads
FPS_REPORT_INTERVAL_SEC = 5  # seconds between FPS reports when show_fps_report is True


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
        show_fps_report (bool): Whether to print FPS for debugging. Defaults to False.
        scale_mode (str): "cover" = fill widget and crop; "fit" = fit inside with letterbox. Defaults to "cover".
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
        show_fps_report: bool = False,
        scale_mode: str = "cover",
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

        requested_w, requested_h = width, height
        width = max(4, round(width / 4) * 4)
        height = max(4, round(height / 4) * 4)
        if requested_w != width or requested_h != height:
            msg = f"""
            ================ MediaViewer Size Requirement ================
                    MediaViewer width and height must be a multiple
                    of 4. Requested {requested_w}x{requested_h} has been
                    adjusted to {width}x{height}. Use multiples of 4 
                    (e.g. 384, 388, 400) to avoid video corruption 
                    and this warning.
            ================================================================
            """
            log.warning(msg, extra={"console": True})

        self.setFixedSize(width, height)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)

        self.corner_radius = corner_radius
        self.media_path = media_path
        self.loop_video = loop_video
        self._show_fps_report = show_fps_report
        self._scale_mode: str = "cover" if scale_mode != "fit" else "fit"

        self.media_layout = QVBoxLayout(self)
        self.media_layout.setContentsMargins(0, 0, 0, 0)

        self.media_widget = QLabel()
        self.media_widget.setAlignment(Qt.AlignCenter)
        self.media_layout.addWidget(self.media_widget)

        self.movie = None
        self.is_video = False
        self.cap = None
        self.timer = None
        self._frame_count = 0
        self._fps_report_timer: Optional[QTimer] = None
        self._frame_busy = False
        self._display_buffer = (
            None  # reused for same-size video path (numpy BGR when _QT_FORMAT_BGR)
        )
        self.pixmap_provided = pixmap_provided
        self._async_runner = AsyncRunner()
        self._load_request_id = 0
        self._temp_download_path: Optional[str] = None
        if pixmap_provided:
            scaled_pixmap = self._scaled_pixmap(
                pixmap_provided, self.media_widget.width(), self.media_widget.height()
            )
            self.media_widget.setPixmap(scaled_pixmap)
        elif media_path:
            self.load_media(media_path)

    def _is_http_url(self, value: str) -> bool:
        """
        Returns True if value looks like an http(s) URL.

        Note: We intentionally keep this conservative to avoid misclassifying local paths.
        """
        if not value or not isinstance(value, str):
            return False
        return re.match(r"^https?://", value.strip(), flags=re.IGNORECASE) is not None

    def _cleanup_temp_download(self) -> None:
        """
        Remove any temp file created for URL media.
        """
        try:
            if self._temp_download_path and os.path.exists(self._temp_download_path):
                os.remove(self._temp_download_path)
        except Exception as e:
            log.warning(f"Failed to delete temp media file: {e}", exc_info=True)
        finally:
            self._temp_download_path = None

    def _download_url_to_tempfile(self, url: str, *, suffix: str) -> str:
        """
        Download a URL to a local temporary file and return the file path.
        """
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp_path = tmp.name
        try:
            # Prefer requests if installed (used elsewhere in this repo), fall back to urllib.
            try:
                import requests  # type: ignore

                headers = {"User-Agent": HTTP_USER_AGENT}
                with requests.get(
                    url, headers=headers, timeout=15, allow_redirects=True, stream=True
                ) as res:
                    res.raise_for_status()
                    for chunk in res.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                        if chunk:
                            tmp.write(chunk)
            except Exception:
                from urllib.request import Request, urlopen

                headers = {"User-Agent": HTTP_USER_AGENT}
                req = Request(url, headers=headers)
                with urlopen(req, timeout=15) as resp:  # nosec - user-provided URL
                    while True:
                        chunk = resp.read(DOWNLOAD_CHUNK_SIZE)
                        if not chunk:
                            break
                        tmp.write(chunk)

            tmp.flush()
            return tmp_path
        except Exception:
            # Ensure temp file isn't leaked on failure.
            try:
                tmp.close()
            finally:
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except Exception:
                    pass
            raise
        finally:
            try:
                tmp.close()
            except Exception:
                pass

    def _load_media_from_url(self, url: str) -> None:
        """
        Download URL media in a background thread then load it as a local file.
        """
        url = (url or "").strip()
        if not url:
            return

        # New request; invalidate any in-flight callbacks.
        self._load_request_id += 1
        request_id = self._load_request_id

        # Clear any previous download outcome to avoid stale state.
        self._download_result_path = None  # type: ignore[attr-defined]
        self._download_error = None  # type: ignore[attr-defined]

        # Clean up existing state first.
        try:
            self.cleanup_video_resources()
            self.cleanup_gif_resources()
        except Exception as e:
            log.error(f"Error stopping previous media playback: {e}", exc_info=True)
        self._cleanup_temp_download()

        # Lightweight UI hint while downloading.
        self.is_video = False
        self.media_widget.clear()
        self.media_widget.setText("Loading…")

        from urllib.parse import urlparse

        parsed = urlparse(url)
        ext = os.path.splitext(parsed.path)[1].lower()
        # If URL has no extension, still download; try to treat as image by default.
        suffix = ext if ext else ".bin"

        def run_download() -> None:
            try:
                tmp_path = self._download_url_to_tempfile(url, suffix=suffix)
                # Stash result for callback on main thread.
                self._download_result_path = tmp_path  # type: ignore[attr-defined]
            except Exception as e:
                self._download_error = e  # type: ignore[attr-defined]

        def on_complete() -> None:
            # If a newer request started since this one, discard.
            if request_id != self._load_request_id:
                tmp_path = getattr(self, "_download_result_path", None)
                if isinstance(tmp_path, str) and os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass
                return

            err = getattr(self, "_download_error", None)
            if err is not None:
                log.error(f"Failed to download media URL: {url}. Error: {err}")
                self.media_widget.setText("Failed to load media")
                return

            tmp_path = getattr(self, "_download_result_path", None)
            if not isinstance(tmp_path, str) or not os.path.exists(tmp_path):
                log.error("Download completed but temp file is missing.")
                self.media_widget.setText("Failed to load media")
                return

            # Keep temp file around for resizeEvent reloads / video playback.
            self._temp_download_path = tmp_path
            self.media_path = tmp_path
            # Load as a local file path.
            self.load_media(tmp_path)

        self._async_runner.run(run_download, on_complete=on_complete)

    def _load_video_opencv(self, path: str) -> None:
        """Load video with OpenCV (FFMPEG backend)."""
        import cv2
        import numpy as np

        self._cv2 = cv2
        self._np = np
        self.is_video = True
        self.cap = cv2.VideoCapture(path)
        if not self.cap.isOpened():
            log.error("Failed to open video file.")
            self.cap = None
            return

        # Reusable buffer for same-size path (avoid per-frame alloc)
        tw, th = self.media_widget.width(), self.media_widget.height()
        self._display_buffer = np.empty((th, tw, 3), dtype=np.uint8)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.next_frame)
        fps = self.cap.get(cv2.CAP_PROP_FPS)
        interval = int(1000 / fps) if fps > 0 else DEFAULT_VIDEO_INTERVAL_MS
        self._frame_count = 0
        if self._show_fps_report:
            self._start_fps_report_timer()
        self.timer.start(interval)

    def _start_fps_report_timer(self) -> None:
        """Start timer that every FPS_REPORT_INTERVAL_SEC seconds prints actual fps."""
        self._stop_fps_report_timer()
        self._fps_report_timer = QTimer(self)
        self._fps_report_timer.timeout.connect(self._report_actual_fps)
        self._fps_report_timer.start(FPS_REPORT_INTERVAL_SEC * 1000)

    def _stop_fps_report_timer(self) -> None:
        """Stop the FPS report timer."""
        if self._fps_report_timer is not None:
            self._fps_report_timer.stop()
            self._fps_report_timer.deleteLater()
            self._fps_report_timer = None

    def _report_actual_fps(self) -> None:
        """Report frames displayed in the past FPS_REPORT_INTERVAL_SEC seconds (actual fps). Only runs when show_fps_report is True."""
        if not self._show_fps_report or self._frame_count == 0:
            self._frame_count = 0
            return
        fps = self._frame_count / float(FPS_REPORT_INTERVAL_SEC)
        msg = (
            f"MediaViewer actual fps (past {FPS_REPORT_INTERVAL_SEC} sec): {fps:.1f} "
            f"(frames={self._frame_count})"
        )
        log.debug(msg, extra={"console": True})
        print(msg)
        self._frame_count = 0

    def load_media(self, path: str) -> None:
        """
        Load and display media from a local path or a web URL.

        Supported inputs:
        - Local filesystem paths to images (.jpg, .jpeg, .png, .bmp, .webp), GIFs (.gif),
          and videos (.mp4, .avi, .mov, .mkv)
        - http(s) URLs pointing to those file types

        For URLs, the media is downloaded asynchronously to a temporary file and then loaded
        using the same local-file code paths. The temporary file is cleaned up when new media
        is loaded (or when the widget is closed).

        Args:
            path (str): Local path or http(s) URL to image, GIF, or video media.
        """
        log.info(f"Loading media: {path}")

        if self._is_http_url(path):
            self._load_media_from_url(path)
            return

        # If we previously downloaded URL media, drop it when switching to a different local path.
        try:
            if self._temp_download_path and os.path.abspath(path) != os.path.abspath(
                self._temp_download_path
            ):
                self._cleanup_temp_download()
        except Exception:
            log.warning("Error cleaning up previous media download", exc_info=True)
            pass

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
                scaled_pixmap = self._scaled_pixmap(
                    pixmap, self.media_widget.width(), self.media_widget.height()
                )
                self.media_widget.setPixmap(scaled_pixmap)

            elif ext == ".gif":
                self.is_video = False
                self.movie = QMovie(path)
                if self.movie.isValid():
                    self.media_widget.setFixedSize(self.width(), self.height())
                    fr = self.movie.frameRect()
                    sw, sh = self._scale_dimensions(
                        fr.width(),
                        fr.height(),
                        self.media_widget.width(),
                        self.media_widget.height(),
                    )
                    self.movie.setScaledSize(QSize(sw, sh))
                    self.movie.setCacheMode(QMovie.CacheAll)
                    self.movie.setSpeed(DEFAULT_MOVIE_SPEED)
                    self.media_widget.setMovie(self.movie)
                    self.movie.start()
                else:
                    log.error("Invalid GIF file or failed to load.")

            elif ext in [".mp4", ".avi", ".mov", ".mkv"]:
                self._load_video_opencv(path)
            else:
                log.warning(f"Unsupported media type: {ext}")
        except Exception as e:
            log.error(f"Error loading media {path}: {e}", exc_info=True)

    def next_frame(self) -> None:
        """
        Called periodically by timer to fetch and display the next video frame.

        Automatically handles video looping if loop_video is enabled. Skips if still
        processing the previous frame to avoid piling up work.
        """
        if not self.cap:
            return
        if self._frame_busy:
            return

        cv2 = self._cv2
        np = self._np

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

        self._frame_busy = True
        try:
            if _QT_FORMAT_BGR is None:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            target_w = self.media_widget.width()
            target_h = self.media_widget.height()
            frame_h, frame_w, _ = frame.shape
            qt_fmt = (
                _QT_FORMAT_BGR if _QT_FORMAT_BGR is not None else QImage.Format_RGB888
            )
            use_cover = self._scale_mode == "cover"

            if use_cover and frame_w == target_w and frame_h == target_h:
                # Same size (cover): copy into reusable buffer
                if self._display_buffer is not None and self._display_buffer.shape == (
                    target_h,
                    target_w,
                    3,
                ):
                    np.copyto(self._display_buffer, frame)
                    qt_image = QImage(
                        self._display_buffer.data,
                        target_w,
                        target_h,
                        3 * target_w,
                        qt_fmt,
                    )
                else:
                    out = np.ascontiguousarray(frame)
                    qt_image = QImage(
                        out.data,
                        target_w,
                        target_h,
                        3 * target_w,
                        qt_fmt,
                    )
                pixmap = QPixmap.fromImage(qt_image)
            else:
                # Scale by mode: cover = fill and crop, fit = fit inside
                new_w, new_h = self._scale_dimensions(
                    frame_w, frame_h, target_w, target_h
                )
                resized = cv2.resize(
                    frame, (new_w, new_h), interpolation=cv2.INTER_AREA
                )
                if use_cover and (new_w > target_w or new_h > target_h):
                    x_start = (new_w - target_w) // 2
                    y_start = (new_h - target_h) // 2
                    cropped = resized[
                        y_start : y_start + target_h, x_start : x_start + target_w
                    ]
                    out = np.ascontiguousarray(cropped)
                    qt_image = QImage(
                        out.data, target_w, target_h, 3 * target_w, qt_fmt
                    )
                else:
                    out = np.ascontiguousarray(resized)
                    qt_image = QImage(out.data, new_w, new_h, 3 * new_w, qt_fmt)
                pixmap = QPixmap.fromImage(qt_image)

            self.media_widget.setPixmap(pixmap)

            if self._show_fps_report:
                self._frame_count += 1

        except Exception as e:
            log.error(f"Error processing video frame: {e}", exc_info=True)
        finally:
            self._frame_busy = False

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
                        (
                            Qt.KeepAspectRatio
                            if self._scale_mode == "fit"
                            else Qt.KeepAspectRatioByExpanding
                        ),
                        Qt.SmoothTransformation,
                    )
                    if self._scale_mode == "cover" and (
                        scaled.width() > self.media_widget.width()
                        or scaled.height() > self.media_widget.height()
                    ):
                        x = (scaled.width() - self.media_widget.width()) // 2
                        y = (scaled.height() - self.media_widget.height()) // 2
                        scaled = scaled.copy(
                            x, y, self.media_widget.width(), self.media_widget.height()
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
                    scaled_pixmap = self._scaled_pixmap(
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
            self._frame_busy = False
            self._display_buffer = None
            self._stop_fps_report_timer()
            self._frame_count = 0
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
            self._cleanup_temp_download()

            # Clear the media widget
            if self.media_widget:
                self.media_widget.clear()
                self.media_widget.setPixmap(QPixmap())

            log.info("MediaViewer cleanup completed")
        except Exception as e:
            log.error(f"Error during closeEvent cleanup: {e}", exc_info=True)
        super().closeEvent(event)

    def _scale_dimensions(
        self,
        src_w: int,
        src_h: int,
        target_w: int,
        target_h: int,
    ) -> tuple[int, int]:
        """
        Return (width, height) to scale source to target using current scale_mode.
        cover: fill target, may be larger (then crop). fit: fit inside target.
        """
        if src_w <= 0 or src_h <= 0:
            return (target_w, target_h)
        if self._scale_mode == "fit":
            scale = min(target_w / src_w, target_h / src_h)
        else:
            scale = max(target_w / src_w, target_h / src_h)
        return (max(1, int(src_w * scale)), max(1, int(src_h * scale)))

    def _scaled_pixmap(
        self, pixmap: QPixmap, target_width: int, target_height: int
    ) -> QPixmap:
        """
        Scale pixmap to target size using current scale_mode (cover or fit).
        """
        if self._scale_mode == "fit":
            return self._scaled_pixmap_fit(pixmap, target_width, target_height)
        return self._scaled_pixmap_cover(pixmap, target_width, target_height)

    def _scaled_pixmap_cover(
        self, pixmap: QPixmap, target_width: int, target_height: int
    ) -> QPixmap:
        """
        Scales and crops a pixmap to fill the target dimensions (cover).
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

    def _scaled_pixmap_fit(
        self, pixmap: QPixmap, target_width: int, target_height: int
    ) -> QPixmap:
        """
        Scales a pixmap to fit inside target dimensions (letterbox/pillarbox).
        """
        try:
            return pixmap.scaled(
                target_width,
                target_height,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        except Exception as e:
            log.error(f"Error scaling pixmap: {e}", exc_info=True)
            return pixmap

    def scaled_pixmap_cover(
        self, pixmap: QPixmap, target_width: int, target_height: int
    ) -> QPixmap:
        """
        Scales and crops a pixmap to fill the target dimensions without distortion.
        Prefer using the widget's scale_mode via _scaled_pixmap for consistency.

        Args:
            pixmap (QPixmap): Original image.
            target_width (int): Desired width.
            target_height (int): Desired height.

        Returns:
            QPixmap: Cropped and scaled pixmap.
        """
        return self._scaled_pixmap_cover(pixmap, target_width, target_height)

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

        if not hasattr(self, "_np"):
            import cv2
            import numpy as np

            self._cv2 = cv2
            self._np = np
        cv2 = self._cv2
        np = self._np

        try:
            qt_fmt = (
                _QT_FORMAT_BGR if _QT_FORMAT_BGR is not None else QImage.Format_RGB888
            )
            if _QT_FORMAT_BGR is None:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            target_w = self.media_widget.width()
            target_h = self.media_widget.height()
            frame_h, frame_w, _ = frame.shape

            new_w, new_h = self._scale_dimensions(frame_w, frame_h, target_w, target_h)
            resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)

            if self._scale_mode == "cover" and (new_w > target_w or new_h > target_h):
                x_start = (new_w - target_w) // 2
                y_start = (new_h - target_h) // 2
                cropped = resized[
                    y_start : y_start + target_h, x_start : x_start + target_w
                ]
                out = np.ascontiguousarray(cropped)
                qt_image = QImage(out.data, target_w, target_h, 3 * target_w, qt_fmt)
            else:
                out = np.ascontiguousarray(resized)
                qt_image = QImage(out.data, new_w, new_h, 3 * new_w, qt_fmt)

            self.media_widget.setPixmap(QPixmap.fromImage(qt_image))

        except Exception as e:
            log.error(f"Error in set_frame: {e}", exc_info=True)
