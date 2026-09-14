"""Head movement for the simulator: WASD turns the wearer, the scene follows.

Why this exists
---------------
Raven Prism has an IMU, so on the real glasses the scene moves when the
wearer's head moves while the HUD stays where it is. On the desktop
simulator the background was a flat clip that never moved, so nothing ever
tested how the HUD reads while the world slides underneath it. This module
adds that motion.

What is real and what is not
----------------------------
The three scene clips are fixed-viewpoint footage: the camera never moves,
so they carry no information about what is behind it. A real 360 view
cannot be recovered from them, and this does not pretend otherwise. What it
builds is a plausible environment: straight ahead is the real frame,
untouched, and the rest of the turn is that frame mirrored around the
wearer. Looking forward is honest; looking behind is a stand-in.

The mirroring is what makes it seamless. Two tiles, one flipped, share their
outer column, so a strip of them repeats with no visible join and OpenCV's
BORDER_WRAP closes the horizon on its own.

How it stays fast
-----------------
The simulator has a 50 ms budget per frame and the blend already spends most
of it. Remapping a frame costs under a millisecond; it was the trigonometry
behind the remap that cost 40. So the tables are built at a quarter of the
view's resolution and scaled up. They describe a smooth surface, so scaling
them up loses almost nothing -- measurably 0.03 grey levels out of 255. Two
details matter for that to hold, and both are silent when wrong:

  * the low-resolution grid must sample at the coordinates cv2.resize reads
    back from, or the whole scene lands two pixels off;
  * longitude has to be unwrapped around the view centre, or the arctan2
    branch cut tears the view in half when the wearer looks backwards.

Nothing here touches Raven's display maths. The head pose only decides which
part of the scene is in front of the wearer; the blend is unchanged.
"""

# Standard library imports
import math
import threading
import time
from dataclasses import dataclass
from typing import Optional, Tuple

# Third-party imports
import cv2
import numpy as np
from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

# The frame is taken to cover this much of the turn. It must divide 360 a
# whole number of times or the mirrored strip will not close on itself.
SOURCE_FOV = 90.0
TILES = int(round(360.0 / SOURCE_FOV))

DEFAULT_VIEW_FOV = 42.0
VIEW_FOV_RANGE = (20.0, 80.0)

# How far the wearer can look up or down. Beyond this there is only the
# faded extension of the frame's top and bottom rows, so there is nothing
# to gain by allowing more.
PITCH_LIMIT = 35.0

# Degrees per second at sensitivity 1.0, and the blend that ramps the turn
# up and down instead of starting and stopping dead.
YAW_RATE = 90.0
PITCH_RATE = 60.0
RATE_SMOOTHING = 0.25
BOOST = 2.5  # while Shift is held

TICK_MS = 16  # the pose advances at ~60 Hz, independent of the frame rate

MAP_DIVISOR = 4  # tables are built this much smaller than the view
POSE_QUANTUM = 0.25  # degrees; poses this close reuse the same tables
MAP_CACHE_LIMIT = 64


@dataclass(frozen=True)
class HeadPose:
    """Where the wearer is looking. Yaw right is positive, pitch up is positive."""

    yaw: float = 0.0
    pitch: float = 0.0

    def clamped(self) -> "HeadPose":
        yaw = (self.yaw + 180.0) % 360.0 - 180.0
        pitch = max(-PITCH_LIMIT, min(PITCH_LIMIT, self.pitch))
        return HeadPose(yaw=yaw, pitch=pitch)

    def is_centred(self) -> bool:
        return abs(self.yaw) < 0.05 and abs(self.pitch) < 0.05


class PanoramaRenderer:
    """Renders the view from a head pose, given one flat scene frame.

    Both the mirrored strip and the lookup tables are reused between calls:
    the strip only changes when the scene frame does, and the tables only
    when the pose does.
    """

    def __init__(self, view_fov: float = DEFAULT_VIEW_FOV) -> None:
        self.view_fov = view_fov
        self._strip: Optional[np.ndarray] = None
        self._strip_source_shape: Optional[Tuple[int, int]] = None
        self._maps: dict = {}
        self._maps_key: Optional[tuple] = None

    # -- the strip -------------------------------------------------------

    @staticmethod
    def _padding(width: int, height: int) -> int:
        """Rows to add above and below so the reachable pitch is covered.

        Only what the wearer can turn towards is worth building. Padding out
        to the poles would more than double the strip for sky nobody sees.
        """
        reach = PITCH_LIMIT + DEFAULT_VIEW_FOV / 2 + 2.0
        per_degree = width / SOURCE_FOV
        return max(1, int(reach * per_degree - height / 2) + 1)

    def _build_strip(self, frame_bgr: np.ndarray) -> np.ndarray:
        height, width = frame_bgr.shape[:2]
        pad = self._padding(width, height)
        shape = (height + 2 * pad, width * TILES, 3)

        if self._strip is None or self._strip.shape != shape:
            self._strip = np.empty(shape, np.uint8)
        strip = self._strip

        # Above and below the frame, its edge rows continue and fade out.
        # A hard edge there reads as a bug; a fade reads as a dim ceiling.
        fade = (np.linspace(1.0, 0.0, pad, dtype=np.float32) ** 1.6)[:, None, None]
        strip[:pad, :width] = frame_bgr[0][None, :, :] * fade[::-1]
        strip[pad : pad + height, :width] = frame_bgr
        strip[pad + height :, :width] = frame_bgr[-1][None, :, :] * fade

        # A tile and its mirror share their outer column, so a run of them
        # repeats with no join. Two pairs put the real frame at yaw 0.
        strip[:, width : 2 * width] = strip[:, :width][:, ::-1]
        strip[:, 2 * width :] = strip[:, : 2 * width]
        return strip

    # -- the lookup tables -----------------------------------------------

    def _lonlat(
        self, width: int, height: int, pose: HeadPose, columns: int, rows: int
    ) -> Tuple[np.ndarray, np.ndarray]:
        focal = (width / 2.0) / math.tan(math.radians(self.view_fov / 2.0))

        # Sample at the view coordinates cv2.resize will read back from.
        # A plain low-resolution grid sits half a low-resolution pixel off,
        # which scales up into a two-pixel shift of the entire scene.
        def axis(count: int, extent: int) -> np.ndarray:
            step = extent / count
            return (
                (np.arange(count, dtype=np.float32) + 0.5) * step - 0.5 - extent / 2.0
            ) / focal

        x, y = np.meshgrid(axis(columns, width), axis(rows, height), indexing="xy")

        pitch = math.radians(pose.pitch)
        yaw = math.radians(pose.yaw)
        up = y * math.cos(pitch) - math.sin(pitch)
        forward = y * math.sin(pitch) + math.cos(pitch)
        right = x * math.cos(yaw) + forward * math.sin(yaw)
        ahead = -x * math.sin(yaw) + forward * math.cos(yaw)

        lon = np.degrees(np.arctan2(right, ahead))
        lat = np.degrees(np.arctan2(up, np.hypot(right, ahead)))

        # arctan2 cuts at +/-180. A view this narrow spans nowhere near a
        # turn, so pulling every value onto the branch nearest the centre
        # removes the cut with no ambiguity. Without it, looking backwards
        # tears the view down the middle.
        lon -= 360.0 * np.round((lon - lon[rows // 2, columns // 2]) / 360.0)
        return lon, lat

    def _maps_for(
        self, strip_shape: tuple, width: int, height: int, pose: HeadPose
    ) -> Tuple[np.ndarray, np.ndarray]:
        key = (
            strip_shape,
            width,
            height,
            round(self.view_fov, 2),
            round(pose.yaw / POSE_QUANTUM),
            round(pose.pitch / POSE_QUANTUM),
        )
        cached = self._maps.get(key)
        if cached is not None:
            return cached

        strip_h, strip_w = strip_shape[:2]
        per_degree = (strip_w / TILES) / SOURCE_FOV

        columns = max(8, width // MAP_DIVISOR)
        rows = max(8, height // MAP_DIVISOR)
        lon, lat = self._lonlat(width, height, pose, columns, rows)

        # The strip is exactly one turn wide, so BORDER_WRAP does the
        # wrapping and longitude needs no wrapping of its own here.
        map_x = lon * per_degree + strip_w / (2.0 * TILES)
        map_y = lat * per_degree + strip_h / 2.0

        if (columns, rows) != (width, height):
            map_x = cv2.resize(map_x, (width, height), interpolation=cv2.INTER_LINEAR)
            map_y = cv2.resize(map_y, (width, height), interpolation=cv2.INTER_LINEAR)

        maps = (
            np.ascontiguousarray(map_x, np.float32),
            np.ascontiguousarray(map_y, np.float32),
        )
        if len(self._maps) >= MAP_CACHE_LIMIT:
            self._maps.clear()
        self._maps[key] = maps
        return maps

    # -- rendering -------------------------------------------------------

    def set_view_fov(self, degrees: float) -> None:
        degrees = max(VIEW_FOV_RANGE[0], min(VIEW_FOV_RANGE[1], float(degrees)))
        if abs(degrees - self.view_fov) > 1e-6:
            self.view_fov = degrees
            self._maps.clear()

    def render(
        self, frame_bgr: np.ndarray, pose: HeadPose, width: int, height: int
    ) -> np.ndarray:
        """The view from `pose`, as a `height` x `width` BGR image."""
        if frame_bgr is None or frame_bgr.size == 0:
            raise ValueError("frame_bgr is empty")

        strip = self._build_strip(frame_bgr)
        map_x, map_y = self._maps_for(strip.shape, width, height, pose.clamped())
        return cv2.remap(
            strip, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP
        )


class HeadTracker(QObject):
    """Turns held WASD keys into a head pose.

    The pose advances on its own timer rather than on the frame clock, so
    turning feels the same whether the simulator is keeping up or not. Key
    events are observed and passed on, never swallowed -- the same thing the
    IMU's own arrow-key monitor does, so neither steals input from the app.
    """

    KEYS = {
        Qt.Key.Key_W: "up",
        Qt.Key.Key_S: "down",
        Qt.Key.Key_A: "left",
        Qt.Key.Key_D: "right",
    }

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._pose = HeadPose()
        self._held = {name: False for name in self.KEYS.values()}
        self._boost = False
        self._yaw_rate = 0.0
        self._pitch_rate = 0.0
        self._enabled = False
        self.sensitivity = 1.0

        self._last_tick = time.monotonic()
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._advance)

        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    # -- state -----------------------------------------------------------

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)
        if self._enabled:
            self._last_tick = time.monotonic()
            self._timer.start()
        else:
            self._timer.stop()
            self._release_all()

    def pose(self) -> HeadPose:
        with self._lock:
            return self._pose

    def recentre(self) -> None:
        with self._lock:
            self._pose = HeadPose()
        self._yaw_rate = 0.0
        self._pitch_rate = 0.0

    def is_moving(self) -> bool:
        return abs(self._yaw_rate) > 0.5 or abs(self._pitch_rate) > 0.5

    def yaw_rate(self) -> float:
        """Degrees per second the wearer is currently turning."""
        return self._yaw_rate

    def pitch_rate(self) -> float:
        """Degrees per second the wearer is currently looking up or down."""
        return self._pitch_rate

    def _release_all(self) -> None:
        for name in self._held:
            self._held[name] = False
        self._boost = False
        self._yaw_rate = 0.0
        self._pitch_rate = 0.0

    # -- input -----------------------------------------------------------

    def eventFilter(self, obj, event) -> bool:
        if self._enabled and isinstance(event, QKeyEvent):
            pressed = event.type() == QKeyEvent.Type.KeyPress
            if event.type() in (QKeyEvent.Type.KeyPress, QKeyEvent.Type.KeyRelease):
                name = self.KEYS.get(event.key())
                if name is not None and not event.isAutoRepeat():
                    self._held[name] = pressed
                elif event.key() == Qt.Key.Key_Shift:
                    self._boost = pressed
        return False  # observe only; never consume

    # -- integration -----------------------------------------------------

    def _advance(self) -> None:
        now = time.monotonic()
        elapsed = min(0.1, now - self._last_tick)  # a stall must not fling the view
        self._last_tick = now

        scale = self.sensitivity * (BOOST if self._boost else 1.0)
        target_yaw = (self._held["right"] - self._held["left"]) * YAW_RATE * scale
        target_pitch = (self._held["up"] - self._held["down"]) * PITCH_RATE * scale

        self._yaw_rate += (target_yaw - self._yaw_rate) * RATE_SMOOTHING
        self._pitch_rate += (target_pitch - self._pitch_rate) * RATE_SMOOTHING

        if abs(self._yaw_rate) < 0.01 and abs(self._pitch_rate) < 0.01:
            return

        with self._lock:
            self._pose = HeadPose(
                yaw=self._pose.yaw + self._yaw_rate * elapsed,
                pitch=self._pose.pitch + self._pitch_rate * elapsed,
            ).clamped()


_tracker: Optional[HeadTracker] = None


def tracker() -> HeadTracker:
    """The one head tracker, shared by the simulator and the IMU.

    Created on first use. Call it from the main thread first -- its timer
    belongs to whichever thread builds it.
    """
    global _tracker
    if _tracker is None:
        _tracker = HeadTracker()
    return _tracker
