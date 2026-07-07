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
Storage manager for Raven Framework.

This module provides functionality for saving media files (images, videos) and
documents to local storage directories and uploading them to a remote server.

On Raven devices all operations are routed through the storage daemon
(/run/ravend/storage.sock) which enforces per-app sandboxing and handles
server uploads using the device bearer token directly — apps never see the
device credential.

On non-Raven devices (simulator / dev machines) the local-filesystem path
is used as before with no server upload.

Security: Only specific allowlisted file types are accepted. Hidden files,
scripts, executables, and path traversal are rejected.
"""

import base64
import json
import os
import socket
import struct
from pathlib import Path
from typing import Any, List, Optional, Tuple, Union

import cv2
import numpy as np

from ..helpers.logger import get_logger
from ..helpers.security import is_valid_app_id, resolve_under_root
from ..helpers.utils_light import is_raven_device, load_config

log = get_logger("StorageManager")

# Allowed extensions only (lowercase). No scripts, executables, or hidden files.
ALLOWED_MEDIA_EXTENSIONS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".bmp",
    ".mp4",
    ".mov",
    ".avi",
    ".webm",
)
ALLOWED_DOCUMENT_EXTENSIONS = (
    ".txt",
    ".md",
    ".pdf",
    ".json",
    ".csv",
)

# ---------------------------------------------------------------------------
# Inline IPC helpers (avoids cross-package imports; mirrors ravend/protocol.py)
# ---------------------------------------------------------------------------

_SOCKET_PATH = f"{load_config().get('ipc', {}).get('RAVEND_SOCKET_DIR', '/run/ravend')}/storage.sock"
_HEADER_SIZE = 4
_MAX_MSG_BYTES = 64 * 1024 * 1024  # 64 MB (video frames can be large)
_TIMEOUT_S = 30.0  # generous for sync which uploads files


def _recvall(sock: socket.socket, n: int) -> bytes:
    buf = bytearray(n)
    view = memoryview(buf)
    received = 0
    while received < n:
        chunk = sock.recv_into(view[received:], n - received)
        if chunk == 0:
            raise ConnectionError("Socket closed prematurely")
        received += chunk
    return bytes(buf)


def _send_msg(sock: socket.socket, payload: dict) -> None:
    data = json.dumps(payload).encode("utf-8")
    sock.sendall(struct.pack(">I", len(data)) + data)


def _recv_msg(sock: socket.socket) -> dict:
    header = _recvall(sock, _HEADER_SIZE)
    msg_len = struct.unpack(">I", header)[0]
    if msg_len > _MAX_MSG_BYTES:
        raise ValueError(f"Message too large: {msg_len}")
    return json.loads(_recvall(sock, msg_len).decode("utf-8"))


def _call(
    app_id: str,
    app_key: str,
    command: str,
    params: dict = None,
    timeout: float = _TIMEOUT_S,
) -> dict:
    """Send one command to the storage daemon and return the response."""
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.settimeout(timeout)
    try:
        conn.connect(_SOCKET_PATH)
        conn.settimeout(None)
        _send_msg(
            conn,
            {
                "app_id": app_id,
                "token": app_key,
                "command": command,
                "params": params or {},
            },
        )
        return _recv_msg(conn)
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Simulator-path helpers (unchanged behaviour for non-Raven devices)
# ---------------------------------------------------------------------------


def _strip_execute_permissions(path: Path) -> None:
    try:
        if not path.is_file():
            return
        current_mode = path.stat().st_mode
        new_mode = current_mode & ~0o111
        if new_mode != current_mode:
            os.chmod(path, new_mode)
    except Exception as e:
        log.error(f"Failed to strip execute permissions from {path}: {e}")


def _is_safe_basename(name: str) -> bool:
    if not name or name.strip() != name:
        return False
    if name.startswith("."):
        return False
    if "/" in name or "\\" in name or ".." in name:
        return False
    return True


def _is_allowed_media_filename(name: str) -> bool:
    if not _is_safe_basename(name):
        return False
    return Path(name).suffix.lower() in ALLOWED_MEDIA_EXTENSIONS


def _is_allowed_document_filename(name: str) -> bool:
    if not _is_safe_basename(name):
        return False
    return Path(name).suffix.lower() in ALLOWED_DOCUMENT_EXTENSIONS


# ---------------------------------------------------------------------------
# Remote VideoWriter proxy (used on Raven device)
# ---------------------------------------------------------------------------


class _RemoteVideoWriter:
    """Proxy that streams frames to the storage daemon's video session."""

    def __init__(self, session_id: str, app_id: str, app_key: str) -> None:
        self._session_id = session_id
        self._app_id = app_id
        self._app_key = app_key
        self._opened = True

    def isOpened(self) -> bool:
        return self._opened

    def write(self, frame: np.ndarray) -> None:
        if not self._opened:
            return
        try:
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            if not ok:
                log.error("Failed to encode video frame")
                return
            frame_b64 = base64.b64encode(buf.tobytes()).decode("ascii")
            resp = _call(
                self._app_id,
                self._app_key,
                "write_frame",
                {
                    "session_id": self._session_id,
                    "frame_b64": frame_b64,
                },
            )
            if resp.get("status") != "ok":
                log.error(f"write_frame denied/error: {resp}")
        except Exception as e:
            log.error(f"Remote write error: {e}")

    def release(self) -> None:
        if not self._opened:
            return
        self._opened = False
        try:
            _call(
                self._app_id,
                self._app_key,
                "close_video",
                {
                    "session_id": self._session_id,
                },
            )
        except Exception as e:
            log.error(f"Remote release error: {e}")


# ---------------------------------------------------------------------------
# StorageManager
# ---------------------------------------------------------------------------


class StorageManager:
    """
    Manages local file storage and remote uploads for Raven applications.

    On Raven devices all I/O is delegated to the storage daemon which
    enforces per-app sandboxing and handles server auth internally.
    On non-Raven devices the local filesystem is used directly.

    Args:
        app_uid (str): Unique identifier for the application instance.
        app_id (str): App ID for daemon authentication (Raven device only).
        app_key (str): App token for daemon authentication (Raven device only).

    Raises:
        RuntimeError: On a Raven device if the storage daemon is unreachable.
        ValueError: If app_uid is invalid (non-device path only).
    """

    def __init__(self, app_uid: str, app_id: str = "", app_key: str = "") -> None:
        self._app_id = app_id
        self._app_key = app_key
        self._on_device = is_raven_device()

        if self._on_device:
            # Validate daemon connectivity. Do NOT catch exceptions here —
            # a failed init on device must propagate as an error rather than
            # silently falling back to direct filesystem access.
            if not app_id or not app_key:
                log.warning(
                    "StorageManager: app_id/app_key not provided — "
                    "all storage requests will be denied by the daemon."
                )
            resp = _call(app_id, app_key, "list_media", timeout=5.0)
            if resp.get("status") == "denied":
                raise PermissionError(
                    f"Storage daemon denied access for app_id={app_id!r}. "
                    "Check your app_id and token."
                )
            # Any other non-ok response (error / connection failure) will
            # have already raised an exception via the socket layer.
            log.info("StorageManager: using storage daemon (Raven device)")
            return

        # ── Non-device (simulator) path ──────────────────────────────────
        # Simulator storage is only supported in the monorepo dev environment.
        # This file is at raven/raven_framework/storage/storage_manager.py,
        # so parents[2] must be the raven/ monorepo root.
        if not is_valid_app_id(app_uid):
            raise ValueError(f"Invalid app_uid: {app_uid!r}")

        _candidate = Path(__file__).resolve().parents[2]
        if _candidate.name != "raven":
            raise RuntimeError(
                "StorageManager simulator mode requires the monorepo dev environment "
                f"(expected parents[2] to be 'raven/', got '{_candidate}'). "
                "Simulator storage is not supported after pip install."
            )
        # Sandbox each app's storage under its own app_uid subdirectory so
        # apps cannot read or overwrite each other's files.
        self.data_dir = resolve_under_root(_candidate / "user_data", app_uid)
        self.media_dir = self.data_dir / "media"
        self.docs_dir = self.data_dir / "documents"
        log.info(f"[simulator] Storage root: {self.data_dir.resolve()}")

        try:
            self.media_dir.mkdir(parents=True, exist_ok=True)
            self.docs_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            log.error(f"Failed to create storage directories: {e}", exc_info=True)
            raise

        self.video_filename = ""

    # ──────────────────────────────────────────────────────────────────────
    # Media
    # ──────────────────────────────────────────────────────────────────────

    def save_media(self, frame: np.ndarray, filename: str) -> Optional[str]:
        """
        Save an image frame to the media directory.

        Args:
            frame: BGR image as a NumPy array.
            filename: Target filename (must have an allowed extension).

        Returns:
            Path string on success, None on failure.
        """
        basename = os.path.basename(filename)
        if not _is_allowed_media_filename(basename):
            log.error(f"Rejected save_media: disallowed filename {filename!r}")
            return None

        if self._on_device:
            try:
                ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
                if not ok:
                    log.error("save_media: failed to encode frame")
                    return None
                image_b64 = base64.b64encode(buf.tobytes()).decode("ascii")
                resp = _call(
                    self._app_id,
                    self._app_key,
                    "save_media",
                    {
                        "filename": basename,
                        "image_b64": image_b64,
                    },
                )
                if resp.get("status") == "ok":
                    return resp["data"].get("path")
                log.error(f"save_media daemon error: {resp}")
                return None
            except Exception as e:
                log.error(f"save_media error: {e}")
                return None

        # Simulator path
        try:
            filepath = self.media_dir / basename
            success = cv2.imwrite(str(filepath), frame)
            if success:
                _strip_execute_permissions(filepath)
                return str(filepath)
            raise Exception("cv2.imwrite returned False")
        except Exception as e:
            log.error(f"Failed to save media: {e}")
            return None

    # ──────────────────────────────────────────────────────────────────────
    # Video recording
    # ──────────────────────────────────────────────────────────────────────

    def open_video_writer(
        self, filename: str, fps: int, frame_size: Tuple[int, int], codec: str
    ) -> Optional[Any]:
        """
        Open a video writer that saves into the media directory.

        On Raven devices returns a proxy object with the same interface
        as cv2.VideoWriter (.write(), .isOpened(), .release()).

        Args:
            filename: Video filename (must have an allowed extension).
            fps: Frames per second.
            frame_size: (width, height) tuple.
            codec: FourCC codec string (e.g. "mp4v").

        Returns:
            VideoWriter-compatible object, or None on failure.
        """
        basename = os.path.basename(filename)
        if not _is_allowed_media_filename(basename):
            log.error(f"Rejected open_video_writer: disallowed filename {filename!r}")
            return None

        if self._on_device:
            try:
                resp = _call(
                    self._app_id,
                    self._app_key,
                    "open_video",
                    {
                        "filename": basename,
                        "fps": fps,
                        "width": frame_size[0],
                        "height": frame_size[1],
                        "codec": codec,
                    },
                )
                if resp.get("status") == "ok":
                    session_id = resp["data"]["session_id"]
                    return _RemoteVideoWriter(session_id, self._app_id, self._app_key)
                log.error(f"open_video daemon error: {resp}")
                return None
            except Exception as e:
                log.error(f"open_video_writer error: {e}")
                return None

        # Simulator path
        try:
            filepath = self.media_dir / basename
            fourcc = cv2.VideoWriter_fourcc(*codec)
            writer = cv2.VideoWriter(str(filepath), fourcc, fps, frame_size)
            self.video_filename = filepath
            if not writer.isOpened():
                raise Exception("Failed to open VideoWriter")
            return writer
        except Exception as e:
            log.error(f"Failed to open video writer: {e}")
            return None

    def close_video_writer(self, writer: Any) -> None:
        """
        Release the video writer safely.

        Accepts both the native cv2.VideoWriter (simulator) and the
        _RemoteVideoWriter proxy (Raven device).
        """
        try:
            writer.release()
            if not self._on_device and self.video_filename:
                _strip_execute_permissions(Path(self.video_filename))
        except Exception as e:
            log.error(f"Error closing video writer: {e}")

    # ──────────────────────────────────────────────────────────────────────
    # Documents
    # ──────────────────────────────────────────────────────────────────────

    def save_document(self, content: Union[str, bytes], filename: str) -> str:
        """
        Save text or binary content to the documents directory.

        Args:
            content: String (text) or bytes (binary).
            filename: Target filename (must have an allowed extension).

        Returns:
            Path string on success.

        Raises:
            ValueError: If filename is disallowed.
            Exception: On Raven device if daemon returns an error.
        """
        basename = os.path.basename(filename)
        if not _is_allowed_document_filename(basename):
            raise ValueError(
                f"Disallowed document filename: {filename!r}. "
                f"Allowed extensions: {ALLOWED_DOCUMENT_EXTENSIONS}"
            )

        if self._on_device:
            raw = content.encode("utf-8") if isinstance(content, str) else content
            content_b64 = base64.b64encode(raw).decode("ascii")
            resp = _call(
                self._app_id,
                self._app_key,
                "save_document",
                {
                    "filename": basename,
                    "content_b64": content_b64,
                },
            )
            if resp.get("status") == "ok":
                return resp["data"]["path"]
            raise RuntimeError(f"save_document daemon error: {resp}")

        # Simulator path
        filepath = self.docs_dir / basename
        mode = "w" if isinstance(content, str) else "wb"
        with open(filepath, mode) as f:
            f.write(content)
        _strip_execute_permissions(filepath)
        return str(filepath)

    # ──────────────────────────────────────────────────────────────────────
    # Listing
    # ──────────────────────────────────────────────────────────────────────

    def list_media_files(
        self, extensions: Tuple[str, ...] = ALLOWED_MEDIA_EXTENSIONS
    ) -> List[str]:
        """Return filenames in the media directory matching given extensions."""
        if self._on_device:
            resp = _call(self._app_id, self._app_key, "list_media")
            files = (
                resp.get("data", {}).get("files", [])
                if resp.get("status") == "ok"
                else []
            )
            ext_set = set(extensions)
            return [f for f in files if Path(f).suffix.lower() in ext_set]

        return [
            f.name
            for f in self.media_dir.iterdir()
            if f.is_file()
            and not f.name.startswith(".")
            and f.suffix.lower() in extensions
        ]

    # ──────────────────────────────────────────────────────────────────────
    # Sync (on-device only — see camera app for simulator upload)
    # ──────────────────────────────────────────────────────────────────────

    def sync_data(self) -> None:
        """
        Ask the storage daemon to upload all files to the remote server.

        Only meaningful on a Raven device — the daemon holds the device bearer
        token so apps never see it. On simulator this is a no-op; the camera
        app handles uploads directly using AdminClient when needed.
        """
        if self._on_device:
            resp = _call(self._app_id, self._app_key, "sync", timeout=120.0)
            if resp.get("status") == "ok":
                log.info(
                    f"sync_data: uploaded {resp['data'].get('uploaded', 0)} file(s)"
                )
            else:
                log.error(f"sync_data daemon error: {resp}")
            return
        log.info("sync_data: server sync not available in simulator mode")
