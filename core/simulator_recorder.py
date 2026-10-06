"""Simulator screen recording."""

import os
import queue
import shutil
import tempfile
import time
from datetime import datetime

import numpy as np
from PySide6.QtCore import QObject, QSettings, QStandardPaths, Signal
from PySide6.QtGui import QImage

from ..helpers.logger import get_logger

log = get_logger("RunApp")

_FOURCC_PREFERENCE = ("avc1", "mp4v")
_QUEUE_MAX_FRAMES = 60
_TEMP_FOLDER_NAME = "raven-simulator-recordings"
_SETTINGS_ORG = "Raven"
_SETTINGS_APP = "Simulator"
_SETTINGS_LAST_DIR_KEY = "recording/last_dir"
_SETTINGS_LAST_SCREENSHOT_DIR_KEY = "screenshot/last_dir"
STALE_RECORDING_AGE_S = 60


def _temp_folder() -> str:
    return os.path.join(tempfile.gettempdir(), _TEMP_FOLDER_NAME)


def temp_recording_path() -> str:
    return os.path.join(_temp_folder(), f"raven-sim-{datetime.now():%Y%m%d-%H%M%S}.mp4")


def clear_stale_recordings() -> None:
    """Delete crash leftovers."""
    folder = _temp_folder()
    if not os.path.isdir(folder):
        return
    cutoff = time.time() - STALE_RECORDING_AGE_S
    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        try:
            if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                os.remove(path)
                log.info(f"Removed leftover simulator recording: {path}")
        except OSError as e:
            log.warning(f"Failed to remove leftover recording {path}: {e}")


def last_recordings_dir() -> str:
    saved = QSettings(_SETTINGS_ORG, _SETTINGS_APP).value(_SETTINGS_LAST_DIR_KEY)
    if saved and os.path.isdir(saved):
        return saved
    movies = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.MoviesLocation
    )
    return movies or os.path.expanduser("~")


def save_recording(temp_path: str, dest_path: str) -> bool:
    try:
        os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
        shutil.move(temp_path, dest_path)
    except OSError as e:
        log.error(f"Failed to save recording to {dest_path}: {e}")
        return False
    QSettings(_SETTINGS_ORG, _SETTINGS_APP).setValue(
        _SETTINGS_LAST_DIR_KEY, os.path.dirname(dest_path)
    )
    return True


def screenshot_filename() -> str:
    return f"raven-sim-{datetime.now():%Y%m%d-%H%M%S}.png"


def last_screenshots_dir() -> str:
    saved = QSettings(_SETTINGS_ORG, _SETTINGS_APP).value(
        _SETTINGS_LAST_SCREENSHOT_DIR_KEY
    )
    if saved and os.path.isdir(saved):
        return saved
    pictures = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.PicturesLocation
    )
    return pictures or os.path.expanduser("~")


def save_screenshot(image: QImage, dest_path: str) -> bool:
    try:
        os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    except OSError as e:
        log.error(f"Failed to create folder for screenshot {dest_path}: {e}")
        return False
    if not image.save(dest_path, "PNG"):
        log.error(f"Failed to save screenshot to {dest_path}")
        return False
    QSettings(_SETTINGS_ORG, _SETTINGS_APP).setValue(
        _SETTINGS_LAST_SCREENSHOT_DIR_KEY, os.path.dirname(dest_path)
    )
    return True


def discard_recording(temp_path: str) -> None:
    try:
        os.remove(temp_path)
    except FileNotFoundError:
        pass
    except OSError as e:
        log.warning(f"Failed to remove discarded recording {temp_path}: {e}")


class SimulatorRecordWorker(QObject):
    """Recording thread."""

    finished = Signal(str, bool)  # path, success

    def __init__(
        self,
        path: str,
        size: tuple[int, int],
        fps: int,
        fill_rgb: tuple[int, int, int],
    ) -> None:
        super().__init__()
        self.path = path
        self._size = size
        self._fps = fps
        self._fill_rgb = fill_rgb
        self._queue: queue.Queue = queue.Queue(maxsize=_QUEUE_MAX_FRAMES)
        self._start_time = time.perf_counter()

    def add_frame(
        self,
        frame_bytes: bytes,
        w: int,
        h: int,
        place_w: int,
        place_h: int,
        channels: int = 3,
    ) -> None:
        """Thread-safe."""
        try:
            self._queue.put_nowait(
                (frame_bytes, w, h, place_w, place_h, channels, time.perf_counter())
            )
        except queue.Full:
            log.debug("SimulatorRecordWorker: queue full, dropping frame")

    def stop(self) -> None:
        """Thread-safe, non-blocking."""
        sentinel = (None, time.perf_counter())
        while True:
            try:
                self._queue.put_nowait(sentinel)
                return
            except queue.Full:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    pass

    def run(self) -> None:
        import cv2

        writer = self._open_writer(cv2)
        if writer is None:
            self.finished.emit(self.path, False)
            return

        width, height = self._size
        held = np.full((height, width, 3), self._fill_rgb[::-1], dtype=np.uint8)
        written = 0
        try:
            while True:
                item = self._queue.get()
                if item[0] is None:
                    end_time = item[1]
                    break
                frame_bytes, w, h, place_w, place_h, channels, t = item
                frame = self._fit(cv2, frame_bytes, w, h, place_w, place_h, channels)
                due = int((t - self._start_time) * self._fps)
                while written < due:
                    writer.write(held)
                    written += 1
                held = frame
            due = max(int((end_time - self._start_time) * self._fps), written + 1)
            while written < due:
                writer.write(held)
                written += 1
        except Exception as e:
            log.error(f"Simulator recording failed: {e}", exc_info=True)
            writer.release()
            self.finished.emit(self.path, False)
            return
        writer.release()
        self.finished.emit(self.path, True)

    def _open_writer(self, cv2):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
        except OSError as e:
            log.error(f"Cannot create recordings folder for {self.path}: {e}")
            return None
        for fourcc in _FOURCC_PREFERENCE:
            writer = cv2.VideoWriter(
                self.path, cv2.VideoWriter_fourcc(*fourcc), self._fps, self._size
            )
            if writer.isOpened():
                return writer
            writer.release()
        log.error(f"No usable video encoder for {self.path}")
        return None

    def _fit(
        self, cv2, frame_bytes, w: int, h: int, place_w: int, place_h: int, channels
    ):
        frame = np.frombuffer(frame_bytes, dtype=np.uint8).reshape((h, w, channels))
        if (w, h) != (place_w, place_h):
            frame = cv2.resize(frame, (place_w, place_h), interpolation=cv2.INTER_AREA)
        if channels == 4:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        width, height = self._size
        if (place_w, place_h) == (width, height):
            return frame
        canvas = np.full((height, width, 3), self._fill_rgb[::-1], dtype=np.uint8)
        left, top = (width - place_w) // 2, (height - place_h) // 2
        x0, y0 = max(0, left), max(0, top)
        x1, y1 = min(width, left + place_w), min(height, top + place_h)
        canvas[y0:y1, x0:x1] = frame[y0 - top : y1 - top, x0 - left : x1 - left]
        return canvas
