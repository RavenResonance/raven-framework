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

import importlib
from unittest.mock import MagicMock

import numpy as np
import pytest
from PySide6.QtGui import QColor, QFont, QImage, QPixmap
from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

import raven_framework.helpers as helpers_module
from raven_framework.helpers import utils
from raven_framework.helpers.animation_utils import fade_in, fade_out
from raven_framework.helpers.async_runner import AsyncRunner
from raven_framework.helpers.font_utils import (
    create_font,
    get_font_family_name,
    get_system_default_font_family,
    load_font_family,
)
from raven_framework.helpers.logger import get_logger
from raven_framework.helpers.open_ai_helper import OpenAiHelper
from raven_framework.helpers.routine import Routine
from raven_framework.helpers.themes import RAVEN_CORE, Palette, RavenTheme
from raven_framework.helpers.utils_light import (
    css_color,
    hex_to_qcolor,
    is_raven_device,
    load_config,
    pascal_to_snake,
    qcolor_to_hex,
    set_custom_circle_cursor,
    snake_to_pascal_case,
    snake_to_spaced_pascal,
    spaced_pascal_to_snake,
    to_qcolor,
)

# =============================================================================
# helpers package — __all__
# =============================================================================


@pytest.mark.parametrize("name", helpers_module.__all__)
def test_helpers_package_export_names_resolve(name: str) -> None:
    obj = getattr(helpers_module, name)
    assert obj is not None


# =============================================================================
# utils_light — naming
# =============================================================================


def test_snake_to_pascal_case() -> None:
    assert snake_to_pascal_case("hello_world") == "HelloWorld"
    assert snake_to_pascal_case("a") == "A"


def test_pascal_to_snake() -> None:
    assert pascal_to_snake("HelloWorld") == "hello_world"


def test_snake_spaced_round_trip() -> None:
    assert spaced_pascal_to_snake("Hello World") == "hello_world"
    assert snake_to_spaced_pascal("hello_world") == "Hello World"


# =============================================================================
# utils_light — colors & config
# =============================================================================


def test_hex_to_qcolor_six_digit() -> None:
    c = hex_to_qcolor("#ff0000")
    assert c.red() == 255 and c.green() == 0 and c.blue() == 0


def test_hex_to_qcolor_three_digit() -> None:
    c = hex_to_qcolor("#f00")
    assert c.red() == 255 and c.green() == 0 and c.blue() == 0


def test_qcolor_to_hex_round_trip() -> None:
    original = QColor(10, 20, 30)
    assert qcolor_to_hex(hex_to_qcolor(qcolor_to_hex(original))) == qcolor_to_hex(
        original
    )


def test_load_config_has_expected_keys() -> None:
    cfg = load_config()
    assert "resolution" in cfg
    assert "fps" in cfg
    assert "DISPLAY_RESOLUTION" in cfg["resolution"]


def test_is_raven_device_returns_bool() -> None:
    assert isinstance(is_raven_device(), bool)


def test_is_raven_device_false_when_marker_absent(tmp_path) -> None:
    from unittest.mock import patch

    from raven_framework.helpers import utils_light

    absent = tmp_path / ".is_raven_device"  # does not exist
    with patch.object(utils_light, "RAVEN_DEVICE_MARKER_PATH", absent):
        assert utils_light.is_raven_device() is False


def test_is_raven_device_true_when_marker_present(tmp_path) -> None:
    from unittest.mock import patch

    from raven_framework.helpers import utils_light

    marker = tmp_path / ".is_raven_device"
    marker.touch()
    with patch.object(utils_light, "RAVEN_DEVICE_MARKER_PATH", marker):
        assert utils_light.is_raven_device() is True


def test_hex_to_qcolor_invalid_returns_white() -> None:
    c = hex_to_qcolor("not-a-color")
    assert c.red() == 255 and c.green() == 255 and c.blue() == 255


def test_hex_to_qcolor_non_string_returns_white() -> None:
    c = hex_to_qcolor(123)  # type: ignore[arg-type]
    assert c.red() == 255


def test_css_color_unsupported_type_returns_white() -> None:
    assert css_color(42) == "#FFFFFF"  # type: ignore[arg-type]


def test_qcolor_to_hex_non_qcolor_returns_white_hex() -> None:
    assert qcolor_to_hex("not") == "#FFFFFF"  # type: ignore[arg-type]


# =============================================================================
# themes / css / cursor
# =============================================================================


def test_raven_core_theme_structure() -> None:
    t: RavenTheme = RAVEN_CORE
    assert isinstance(t.basic_palette, Palette)
    assert t.colors.background_color.startswith("#")
    assert t.fonts.body.size > 0
    assert t.borders.corner_radius >= 0


def test_css_color_qcolor_and_names() -> None:
    assert css_color(QColor(255, 0, 0)).startswith("#")
    assert css_color("#aabbcc") == "#aabbcc"
    assert "rgba" in css_color("transparent")
    assert css_color("white") == "#FFFFFF"


def test_to_qcolor_variants() -> None:
    assert to_qcolor("black").black() is True or to_qcolor("black").red() == 0
    qc = to_qcolor("#00FF00")
    assert qc.green() == 255


def test_set_custom_circle_cursor(qtbot: QtBot) -> None:
    from PySide6.QtCore import Qt

    w = QWidget()
    qtbot.addWidget(w)
    set_custom_circle_cursor(w, mode="circle")
    cursor = w.cursor()
    assert cursor.shape() == Qt.CursorShape.BitmapCursor
    assert not cursor.pixmap().isNull()


# =============================================================================
# animation_utils
# =============================================================================


def test_fade_validation_errors(qtbot: QtBot) -> None:
    w = QWidget()
    qtbot.addWidget(w)
    with pytest.raises(ValueError, match="Widget cannot be None"):
        fade_in(None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="start_value"):
        fade_in(w, start_value=-1.0)
    with pytest.raises(ValueError, match="duration"):
        fade_in(w, duration=-1)


def test_fade_out_schedules(qtbot: QtBot) -> None:
    from PySide6.QtWidgets import QGraphicsOpacityEffect

    w = QWidget()
    qtbot.addWidget(w)
    fade_out(w, duration=100)
    qtbot.wait(150)
    effect = w.graphicsEffect()
    assert isinstance(effect, QGraphicsOpacityEffect)
    assert effect.opacity() < 1.0
    assert hasattr(w, "_fade_animation")


# =============================================================================
# routine / async_runner
# =============================================================================


def test_routine_delay_fires_once(qtbot: QtBot) -> None:
    hits: list[int] = []

    def tick() -> None:
        hits.append(1)

    r = Routine(interval_ms=50, invoke=tick, mode="delay")
    qtbot.wait(150)
    r.stop()
    assert len(hits) == 1


def test_routine_repeat_then_stop(qtbot: QtBot) -> None:
    hits: list[int] = []

    def tick() -> None:
        hits.append(1)

    r = Routine(interval_ms=30, invoke=tick, mode="repeat")
    qtbot.wait(120)
    r.stop()
    assert len(hits) >= 2
    assert not r.is_active()


def test_routine_bad_mode() -> None:
    with pytest.raises(ValueError, match="mode"):
        Routine(interval_ms=10, invoke=lambda: None, mode="invalid")  # type: ignore[arg-type]


def test_routine_rejects_zero_interval() -> None:
    """interval_ms=0 makes QTimer fire as fast as the event loop allows — must be rejected."""
    with pytest.raises(ValueError, match="positive"):
        Routine(interval_ms=0, invoke=lambda: None, mode="delay")


def test_routine_is_active_after_start(qtbot: QtBot) -> None:
    r = Routine(interval_ms=200, invoke=lambda: None, mode="repeat")
    assert r.is_active() is True
    r.stop()
    qtbot.wait(50)
    assert r.is_active() is False


def test_routine_double_stop_is_safe() -> None:
    r = Routine(interval_ms=400, invoke=lambda: None, mode="delay")
    r.stop()
    r.stop()


def test_async_runner_runs(qtbot: QtBot) -> None:
    done: list[bool] = []

    def work() -> None:
        pass

    def on_done() -> None:
        done.append(True)

    runner = AsyncRunner()
    runner.run(work, on_complete=on_done)
    qtbot.waitUntil(lambda: len(done) > 0, timeout=5000)
    assert done == [True]


def test_async_runner_rejects_non_callable() -> None:
    runner = AsyncRunner()
    with pytest.raises(TypeError, match="callable"):
        runner.run(123)  # type: ignore[arg-type]


# =============================================================================
# font_utils
# =============================================================================


def test_get_font_family_name_known() -> None:
    n = get_font_family_name("inter")
    assert isinstance(n, str) and len(n) > 0


def test_load_font_family_returns_bool() -> None:
    assert isinstance(load_font_family("inter"), bool)


def test_create_font_returns_qfont() -> None:
    f = create_font("inter", 28, "normal")
    assert isinstance(f, QFont)
    assert f.pixelSize() == 28


def test_create_font_unknown_uses_system() -> None:
    f = create_font("not_a_real_font_name", 12, "bold")
    assert isinstance(f, QFont)


def test_get_system_default_font_family() -> None:
    fam = get_system_default_font_family()
    assert fam is None or isinstance(fam, str)


def test_preload_fonts_runs() -> None:
    from raven_framework.helpers.font_utils import preload_fonts

    preload_fonts()


# =============================================================================
# logger
# =============================================================================


def test_get_logger_returns_logger() -> None:
    log = get_logger("TestLogger")
    assert "TestLogger" in log.name


# =============================================================================
# helpers.utils (OpenCV / NumPy / QImage)
# =============================================================================


def test_convert_ndarray_to_pixmap_image() -> None:
    frame = np.zeros((40, 60, 3), dtype=np.uint8)
    frame[:, :] = (0, 128, 255)
    pm = utils.convert_ndarray_to_pixmap_image(frame, 60, 40)
    assert pm is not None
    assert not pm.isNull()


def test_convert_ndarray_to_base64_and_back() -> None:
    img = np.zeros((20, 30, 3), dtype=np.uint8)
    img[:, :] = (10, 20, 30)
    b64 = utils.convert_ndarray_to_base64_image(img)
    assert b64
    back = utils.base64_to_image(b64)
    assert back is not None
    assert back.shape[0] == 20


def test_image_to_base64_alias() -> None:
    img = np.zeros((5, 5, 3), dtype=np.uint8)
    assert utils.image_to_base64(img) == utils.convert_ndarray_to_base64_image(img)


def test_qimage_to_rgb_bytes_roundtrip() -> None:
    img = QImage(4, 4, QImage.Format.Format_RGB888)
    img.fill(42)
    out = utils.qimage_to_rgb_bytes(img)
    assert out is not None
    raw, w, h = out
    assert w == 4 and h == 4
    assert len(raw) == 4 * 4 * 3


def test_qimage_to_rgb_bytes_null() -> None:
    img = QImage()
    assert utils.qimage_to_rgb_bytes(img) is None


def test_is_qimage_mostly_black() -> None:
    dark = QImage(2, 2, QImage.Format.Format_RGB888)
    dark.fill(0)
    assert utils.is_qimage_mostly_black(dark, threshold=10.0) is True
    bright = QImage(2, 2, QImage.Format.Format_RGB888)
    bright.fill(255)
    assert utils.is_qimage_mostly_black(bright, threshold=10.0) is False


def test_qpixmap_to_rgb_bytes() -> None:
    pm = QPixmap(8, 8)
    pm.fill(0xFFFFFF)
    out = utils.qpixmap_to_rgb_bytes(pm)
    assert out is not None
    assert len(out[0]) == 8 * 8 * 3


def test_rgb_bytes_to_png_and_jpeg() -> None:
    w, h = 8, 8
    raw = bytes([128, 64, 32] * (w * h))
    png = utils.rgb_bytes_to_png_bytes(raw, w, h, (4, 4))
    assert png is not None and png.startswith(b"\x89PNG")
    jpg = utils.rgb_bytes_to_jpeg_bytes(raw, w, h, (4, 4), quality=90)
    assert jpg is not None and jpg.startswith(b"\xff\xd8")


def test_rgb_bytes_invalid_returns_none() -> None:
    assert utils.rgb_bytes_to_png_bytes(b"", 10, 10, (4, 4)) is None


def test_qimage_resized_encodings() -> None:
    img = QImage(16, 16, QImage.Format.Format_RGB888)
    img.fill(100)
    jpeg = utils.qimage_to_resized_jpeg_bytes(img, (8, 8), quality=85)
    assert jpeg is not None
    png = utils.qimage_to_resized_png_bytes(img, (8, 8))
    assert png is not None


def test_get_frame_from_video_missing_file() -> None:
    assert utils.get_frame_from_video("/nonexistent/path/video.mp4") is None


# =============================================================================
# open_ai_helper
# =============================================================================


def test_open_ai_helper_empty_key_has_no_client() -> None:
    h = OpenAiHelper("")
    assert h.client is None


def test_transcribe_returns_empty_without_client() -> None:
    h = OpenAiHelper("")
    assert h.transcribe_audio(b"fake") == ""


def test_generate_tts_returns_bytes_not_string() -> None:
    """generate_tts previously returned an f-string like 'TTS generation successful: ...'."""
    h = OpenAiHelper("fake-key")
    fake_response = MagicMock()
    fake_response.read.return_value = b"RIFF-fake-wav-bytes"
    h.client.audio.speech.create = MagicMock(return_value=fake_response)
    result = h.generate_tts("hello")
    assert isinstance(result, bytes)
    assert result == b"RIFF-fake-wav-bytes"


def test_generate_tts_returns_empty_bytes_on_error() -> None:
    h = OpenAiHelper("fake-key")
    h.client.audio.speech.create = MagicMock(side_effect=RuntimeError("boom"))
    assert h.generate_tts("hello") == b""


def test_transcribe_audio_returns_empty_string_on_error() -> None:
    """Errors must return "", not an "Error:..." string mixed into the content channel."""
    h = OpenAiHelper("fake-key")
    h.client.audio.transcriptions.create = MagicMock(side_effect=RuntimeError("boom"))
    assert h.transcribe_audio(b"fake-wav") == ""


def test_get_text_response_returns_empty_string_on_error() -> None:
    h = OpenAiHelper("fake-key")
    h.client.chat.completions.create = MagicMock(side_effect=RuntimeError("boom"))
    assert h.get_text_response("hi") == ""


# =============================================================================
# helpers package lazy __getattr__
# =============================================================================


def test_helpers_lazy_openai() -> None:
    helpers = importlib.import_module("raven_framework.helpers")
    cls = getattr(helpers, "OpenAiHelper")
    assert cls.__name__ == "OpenAiHelper"


def test_helpers_lazy_font_utils() -> None:
    helpers = importlib.import_module("raven_framework.helpers")
    preload = getattr(helpers, "preload_fonts")
    assert callable(preload)


def test_helpers_lazy_heavy_utils_convert_pixmap() -> None:
    helpers = importlib.import_module("raven_framework.helpers")
    fn = getattr(helpers, "convert_ndarray_to_pixmap_image")
    assert callable(fn)
