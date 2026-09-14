"""Checks for the simulator's head movement.

Run with pytest alongside the rest of the suite, or directly for a quick
look in a bare checkout:  python tests/test_head_pose.py
"""

import math
import sys
import time

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

# Import through the installed package, never by file path: loading the
# module standalone would create a second copy with its own tracker(), so
# the simulator and the IMU would each be reading a different head.
from raven_framework.core import head_pose

HeadPose = head_pose.HeadPose
HeadTracker = head_pose.HeadTracker
PanoramaRenderer = head_pose.PanoramaRenderer

VIEW = 720
_app = QApplication.instance() or QApplication([])


def scene(width=800, height=820):
    """A frame with no symmetry of its own, so a mirror is detectable."""
    rng = np.random.default_rng(7)
    img = rng.integers(0, 200, (height, width, 3), dtype=np.uint8)
    # A bright marker off to one side, and a gradient, so left and right
    # are told apart even after resampling.
    img[:, :] = (img * 0.3).astype(np.uint8)
    img += (np.linspace(0, 55, width, dtype=np.uint8)[None, :, None]).astype(np.uint8)
    img[300:420, 620:700] = 255
    return img


# ---------------------------------------------------------------- pose ---


def test_pitch_is_limited():
    assert HeadPose(pitch=400.0).clamped().pitch == head_pose.PITCH_LIMIT
    assert HeadPose(pitch=-400.0).clamped().pitch == -head_pose.PITCH_LIMIT


def test_yaw_wraps_instead_of_growing():
    assert abs(HeadPose(yaw=370.0).clamped().yaw - 10.0) < 1e-6
    assert abs(HeadPose(yaw=-190.0).clamped().yaw - 170.0) < 1e-6


# ------------------------------------------------------------- strip ----


def test_strip_is_one_turn_wide_and_closes_on_itself():
    r = PanoramaRenderer()
    strip = r._build_strip(scene())
    assert strip.shape[1] == 800 * head_pose.TILES

    # The wrap joins the last column to the first. They must nearly match,
    # or a seam appears at the back of the room.
    gap = np.abs(strip[:, -1].astype(int) - strip[:, 0].astype(int)).mean()
    inside = np.abs(strip[:, 400].astype(int) - strip[:, 401].astype(int)).mean()
    assert gap <= inside + 1.0, f"seam at the wrap: {gap:.1f} vs {inside:.1f} inside"


def test_strip_buffer_is_reused():
    r = PanoramaRenderer()
    first = r._build_strip(scene())
    second = r._build_strip(scene())
    assert first is second, "a new 10 MB buffer per video frame is the slow path"


# ------------------------------------------------------------ render ----


def test_looking_forward_shows_the_real_frame_not_a_mirror():
    """The first thing the wearer sees must not be the mirror seam."""
    view = PanoramaRenderer().render(scene(), HeadPose(), VIEW, VIEW)
    folded = np.abs(view.astype(int) - view[:, ::-1].astype(int)).mean()
    assert folded > 12.0, (
        f"the forward view is nearly its own mirror ({folded:.1f}); "
        "the seam has landed on yaw 0"
    )


def test_a_full_turn_comes_back_to_the_same_view():
    r = PanoramaRenderer()
    img = scene()
    start = r.render(img, HeadPose(yaw=0.0), VIEW, VIEW)
    around = r.render(img, HeadPose(yaw=360.0), VIEW, VIEW)
    assert np.abs(start.astype(int) - around.astype(int)).mean() < 0.5


def test_turning_right_brings_in_what_was_on_the_right():
    r = PanoramaRenderer()
    img = scene()
    ahead = r.render(img, HeadPose(), VIEW, VIEW)
    turned = r.render(img, HeadPose(yaw=10.0), VIEW, VIEW)

    # What sat on the right of the forward view should now sit nearer the
    # middle. Correlate a right-hand band against both.
    band = ahead[:, 500:640]
    here = np.abs(turned[:, 500:640].astype(int) - band.astype(int)).mean()
    shifted = np.abs(turned[:, 320:460].astype(int) - band.astype(int)).mean()
    assert shifted < here, "turning right does not pan the scene leftwards"


def test_looking_up_reaches_the_top_of_the_frame():
    r = PanoramaRenderer()
    img = scene()
    img[:60, :] = 250  # a bright ceiling
    level = r.render(img, HeadPose(), VIEW, VIEW).mean()
    up = r.render(img, HeadPose(pitch=head_pose.PITCH_LIMIT), VIEW, VIEW).mean()
    assert up > level, "looking up does not reach the top of the frame"


def test_looking_backwards_does_not_tear():
    """The arctan2 branch cut sits behind the wearer; it must be unwrapped.

    Leaving it in corrupts only about four columns, which an average over
    the whole view hides completely. So this compares against the
    full-resolution tables column by column: those build no scaled-up map,
    so they cannot smear across the cut whatever longitude does.
    """
    img = scene()
    for yaw in (175.0, 179.0, 180.0, -178.0):
        pose = HeadPose(yaw=yaw)
        quick = PanoramaRenderer().render(img, pose, VIEW, VIEW)

        saved = head_pose.MAP_DIVISOR
        head_pose.MAP_DIVISOR = 1
        try:
            full = PanoramaRenderer().render(img, pose, VIEW, VIEW)
        finally:
            head_pose.MAP_DIVISOR = saved

        columns = np.abs(quick.astype(int) - full.astype(int)).mean(axis=(0, 2))

        # The outermost column on each side is cv2.resize extrapolating
        # past its last sample, not a tear. It is one pixel wide and
        # measures about 3 levels on real footage (45 on the pathological
        # noise used here, which no camera produces). The tear being hunted
        # is four columns near the middle of the view, so leaving the
        # border out costs this check nothing.
        interior = columns[1:-1]
        assert interior.max() < 8.0, (
            f"yaw {yaw}: column {interior.argmax() + 1} is {interior.max():.1f} "
            f"levels off while the view averages {interior.mean():.2f} "
            "-- a tear at the branch cut"
        )


def test_quarter_resolution_tables_match_full_resolution():
    img = scene()
    for yaw, pitch in ((0, 0), (25, 0), (45, 0), (90, -20), (180, 0), (-140, 25)):
        pose = HeadPose(yaw, pitch)

        fast = PanoramaRenderer()
        quick = fast.render(img, pose, VIEW, VIEW)

        exact = PanoramaRenderer()
        strip = exact._build_strip(img)
        saved = head_pose.MAP_DIVISOR
        head_pose.MAP_DIVISOR = 1
        try:
            full = exact.render(img, pose, VIEW, VIEW)
        finally:
            head_pose.MAP_DIVISOR = saved

        error = np.abs(quick.astype(float) - full.astype(float)).mean()
        assert error < 0.5, f"yaw {yaw} pitch {pitch}: {error:.2f} levels off"
        assert strip.shape[1] > 0


def test_render_fits_the_frame_budget():
    r = PanoramaRenderer()
    img = scene()
    r.render(img, HeadPose(), VIEW, VIEW)

    start = time.perf_counter()
    for step in range(15):
        r.render(img, HeadPose(yaw=step * 2.0, pitch=step * 0.5), VIEW, VIEW)
    each = (time.perf_counter() - start) / 15 * 1000
    assert each < 30.0, f"{each:.1f} ms per moving frame, budget is 50 ms total"
    print(f"      ({each:.1f} ms per frame while turning)")


def test_narrowing_the_field_of_view_magnifies():
    r = PanoramaRenderer()
    img = scene()
    wide = r.render(img, HeadPose(), VIEW, VIEW)
    r.set_view_fov(21.0)
    narrow = r.render(img, HeadPose(), VIEW, VIEW)
    # Halving the field of view doubles the scale, so detail spreads out
    # and neighbouring pixels differ less.
    assert (
        np.abs(np.diff(narrow.astype(int), axis=1)).mean()
        < np.abs(np.diff(wide.astype(int), axis=1)).mean()
    )


# ----------------------------------------------------------- tracker ----


def _key(tracker, key, press=True):
    kind = QKeyEvent.Type.KeyPress if press else QKeyEvent.Type.KeyRelease
    return tracker.eventFilter(
        None, QKeyEvent(kind, key, Qt.KeyboardModifier.NoModifier)
    )


def test_keys_are_observed_but_not_swallowed():
    """Consuming keys would take input away from the app under test."""
    t = HeadTracker()
    t.set_enabled(True)
    assert _key(t, Qt.Key.Key_W) is False
    assert _key(t, Qt.Key.Key_W, press=False) is False
    t.set_enabled(False)


def test_d_turns_right_and_a_turns_left():
    for key, expected in ((Qt.Key.Key_D, 1), (Qt.Key.Key_A, -1)):
        t = HeadTracker()
        t.set_enabled(True)
        _key(t, key)
        for _ in range(20):
            t._advance()
            time.sleep(0.005)
        yaw = t.pose().yaw
        t.set_enabled(False)
        assert yaw * expected > 0.5, f"{key} moved yaw to {yaw:.2f}"


def test_w_looks_up_and_s_looks_down():
    for key, expected in ((Qt.Key.Key_W, 1), (Qt.Key.Key_S, -1)):
        t = HeadTracker()
        t.set_enabled(True)
        _key(t, key)
        for _ in range(20):
            t._advance()
            time.sleep(0.005)
        pitch = t.pose().pitch
        t.set_enabled(False)
        assert pitch * expected > 0.3, f"{key} moved pitch to {pitch:.2f}"


def test_keys_do_nothing_while_the_mode_is_off():
    t = HeadTracker()
    _key(t, Qt.Key.Key_D)
    for _ in range(20):
        t._advance()
    assert t.pose().is_centred()


def test_releasing_the_key_stops_the_turn():
    t = HeadTracker()
    t.set_enabled(True)
    _key(t, Qt.Key.Key_D)
    for _ in range(10):
        t._advance()
        time.sleep(0.005)
    _key(t, Qt.Key.Key_D, press=False)
    for _ in range(40):
        t._advance()
        time.sleep(0.005)
    settled = t.pose().yaw
    for _ in range(20):
        t._advance()
        time.sleep(0.005)
    t.set_enabled(False)
    assert abs(t.pose().yaw - settled) < 0.5, "the view keeps drifting after release"


def test_recentre_returns_to_looking_forward():
    t = HeadTracker()
    t.set_enabled(True)
    _key(t, Qt.Key.Key_D)
    for _ in range(20):
        t._advance()
        time.sleep(0.005)
    t.recentre()
    t.set_enabled(False)
    assert t.pose().is_centred()


def test_disabling_forgets_held_keys():
    """Otherwise the view flies off the moment the mode is switched back on."""
    t = HeadTracker()
    t.set_enabled(True)
    _key(t, Qt.Key.Key_D)
    t.set_enabled(False)
    t.set_enabled(True)
    for _ in range(20):
        t._advance()
        time.sleep(0.005)
    yaw = t.pose().yaw
    t.set_enabled(False)
    assert abs(yaw) < 0.5, f"a key held across the toggle kept turning: {yaw:.2f}"


def test_a_long_stall_does_not_fling_the_view():
    t = HeadTracker()
    t.set_enabled(True)
    _key(t, Qt.Key.Key_D)
    for _ in range(6):
        t._advance()
    t._last_tick -= 30.0  # as if the process were suspended for half a minute
    t._advance()
    yaw = t.pose().yaw
    t.set_enabled(False)
    assert abs(yaw) < 45.0, f"a stall threw the view to {yaw:.1f} degrees"


def test_sensitivity_scales_the_turn():
    def turn(sensitivity):
        t = HeadTracker()
        t.set_enabled(True)
        t.sensitivity = sensitivity
        _key(t, Qt.Key.Key_D)
        for _ in range(15):
            t._advance()
            time.sleep(0.005)
        t.set_enabled(False)
        return abs(t.pose().yaw)

    assert turn(2.0) > turn(0.5) * 1.5


# ------------------------------------------------- the flat path holds --


def _original_fit(frame, w, h):
    """The crop-and-fill exactly as the camera and video paths each had it.

    Both branches were byte-for-byte duplicates apart from variable names.
    They were merged into one method so head movement had a single place to
    hook into, and this is the check that the merge changed nothing.
    """
    import cv2

    src_h, src_w = frame.shape[:2]
    if src_w / src_h > w / h:
        new_height = h
        new_width = int(src_w * (h / src_h))
        out = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_LINEAR)
        crop_x = (new_width - w) // 2
        return out[:, crop_x : crop_x + w]
    new_width = w
    new_height = int(src_h * (w / src_w))
    out = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_LINEAR)
    crop_y = (new_height - h) // 2
    return out[crop_y : crop_y + h, :]


def test_flat_fit_is_byte_for_byte_what_it_always_was():
    from raven_framework.core.raven_simulator import SimulatorBackgroundWidget

    widget = SimulatorBackgroundWidget.__new__(SimulatorBackgroundWidget)
    widget.head_motion_enabled = False

    rng = np.random.default_rng(3)
    sizes = [(820, 800), (480, 640), (720, 1280), (1080, 1080), (600, 900)]
    for src_h, src_w in sizes:
        frame = rng.integers(0, 255, (src_h, src_w, 3), dtype=np.uint8)
        mine = widget.fit_frame(frame, VIEW, VIEW)
        theirs = _original_fit(frame, VIEW, VIEW)
        assert (
            mine.shape == theirs.shape == (VIEW, VIEW, 3)
        ), f"{src_w}x{src_h} produced {mine.shape}"
        assert np.array_equal(mine, theirs), f"{src_w}x{src_h} changed"


def test_a_broken_render_falls_back_instead_of_freezing():
    """A scene that stops updating looks like a hung simulator."""
    from raven_framework.core.raven_simulator import SimulatorBackgroundWidget

    class Broken:
        def render(self, *_a, **_k):
            raise RuntimeError("boom")

    widget = SimulatorBackgroundWidget.__new__(SimulatorBackgroundWidget)
    widget.head_motion_enabled = True
    widget._panorama = Broken()

    frame = scene()
    out = widget.fit_frame(frame, VIEW, VIEW)
    assert out.shape == (VIEW, VIEW, 3)
    assert np.array_equal(out, _original_fit(frame, VIEW, VIEW))


# --------------------------------------------------------- the sensor --


def _imu():
    from raven_framework.peripherals.imu import IMU

    return IMU()


def _fresh_head():
    """The tracker is a singleton shared with the IMU, so tests must not
    inherit a pose from whichever test ran before them."""
    head = head_pose.tracker()
    head.set_enabled(False)
    head.recentre()
    return head


def test_the_sensor_is_unchanged_while_the_mode_is_off():
    _fresh_head()
    reading = _imu().get_reading()
    assert reading["accelerometer"]["z"] == 9.8
    assert reading["accelerometer"]["y"] == 0.0
    assert reading["gyroscope"] == {"x": 0.0, "y": 0.0, "z": 0.0}


def test_tilting_the_head_swings_gravity_into_the_y_axis():
    """What a real accelerometer reports when the head pitches."""
    head = _fresh_head()
    head.set_enabled(True)
    try:
        with head._lock:
            head._pose = HeadPose(pitch=30.0)
        accelerometer = _imu().get_reading()["accelerometer"]
        assert abs(accelerometer["y"] - (-9.8 * math.sin(math.radians(30)))) < 0.01
        assert abs(accelerometer["z"] - (9.8 * math.cos(math.radians(30)))) < 0.01

        total = math.hypot(accelerometer["y"], accelerometer["z"])
        assert abs(total - 9.8) < 0.01, "tilting must not invent or lose gravity"
    finally:
        head.set_enabled(False)
        head.recentre()


def test_turning_shows_up_on_the_gyroscope_not_the_accelerometer():
    head = _fresh_head()
    head.set_enabled(True)
    try:
        _key(head, Qt.Key.Key_D)
        for _ in range(20):
            head._advance()
            time.sleep(0.005)
        reading = _imu().get_reading()
        assert reading["gyroscope"]["z"] > 0.1, "a turn left no trace on the gyroscope"
        # Yaw does not move gravity, so the accelerometer must not react.
        assert (
            abs(reading["accelerometer"]["z"] - 9.8) < 0.01
        ), "a turn moved gravity; only a tilt should"
    finally:
        _key(head, Qt.Key.Key_D, press=False)
        head.set_enabled(False)
        head.recentre()


def test_arrow_keys_still_drive_the_sensor():
    """The mode adds head motion; it must not take the old control away."""
    from raven_framework.peripherals import imu as imu_module

    _fresh_head()
    imu_module._key_states[Qt.Key.Key_Left] = True
    try:
        assert _imu().get_reading()["accelerometer"]["x"] > 0.0
    finally:
        imu_module._key_states[Qt.Key.Key_Left] = False


if __name__ == "__main__":
    tests = [
        (n, f)
        for n, f in sorted(globals().items())
        if n.startswith("test_") and callable(f)
    ]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"  ok    {name}")
        except AssertionError as exc:
            failed.append(name)
            print(f"  FAIL  {name}\n          {exc}")
        except Exception as exc:  # noqa: BLE001
            failed.append(name)
            print(f"  ERROR {name}\n          {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - len(failed)}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
