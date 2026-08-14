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

import numpy as np
import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

import raven_framework.components as components_pkg
from raven_framework.components.button import Button
from raven_framework.components.cards import (
    HorizontalTextCard,
    HorizontalTextCardWithButton,
    MediaCard,
    MediaCardWithButton,
    MediaCardWithTwoButtons,
    ScrollableListCard,
    TextCardWithButton,
    TextCardWithTwoButtons,
)
from raven_framework.components.container import Container
from raven_framework.components.expanding_icon import ExpandingIcon
from raven_framework.components.horizontal_container import HorizontalContainer
from raven_framework.components.icon import Icon, RevealIcon
from raven_framework.components.media_viewer import MediaViewer
from raven_framework.components.model_viewer import ModelViewer, load_obj_mesh
from raven_framework.components.scroll_view import ScrollView
from raven_framework.components.spacer import Spacer
from raven_framework.components.text_box import TextBox
from raven_framework.components.vertical_container import VerticalContainer

# =============================================================================
# raven_framework.components package
# =============================================================================


@pytest.mark.parametrize("name", components_pkg.__all__)
def test_components_package_export_names_resolve(name: str) -> None:
    obj = getattr(components_pkg, name)
    assert obj is not None


# =============================================================================
# Button
# =============================================================================


def test_button_on_clicked_invoked_via_signal(qtbot: QtBot) -> None:
    seen: list[str] = []

    def on_click() -> None:
        seen.append("ok")

    b = Button(center_text="T", width=120, height=50)
    b.on_clicked(on_click)
    qtbot.addWidget(b)
    b.clicked.emit()
    assert seen == ["ok"]


def test_button_set_text(qtbot: QtBot) -> None:
    b = Button(center_text="A", width=100, height=44)
    qtbot.addWidget(b)
    b.set_text("Updated")
    b.show()
    qtbot.waitExposed(b)


def test_button_disabled_state(qtbot: QtBot) -> None:
    b = Button(center_text="d", width=100, height=44)
    assert b.is_disabled() is False
    b.set_disabled(True)
    assert b.is_disabled() is True
    b.set_enabled(True)
    assert b.is_disabled() is False
    qtbot.addWidget(b)


def test_button_on_clicked_with_extra_args(qtbot: QtBot) -> None:
    out: list[int] = []

    def cb(n: int) -> None:
        out.append(n)

    b = Button(center_text="x", width=80, height=40)
    b.on_clicked(cb, 42)
    qtbot.addWidget(b)
    b.clicked.emit()
    assert out == [42]


# =============================================================================
# TextBox
# =============================================================================


def test_text_box_set_text_and_size_hint(qtbot: QtBot) -> None:
    tb = TextBox("a", width=200)
    tb.set_text("updated")
    assert tb.text() == "updated"
    sh = tb.sizeHint()
    assert sh.width() > 0 and sh.height() > 0
    qtbot.addWidget(tb)


def test_text_box_font_type_title(qtbot: QtBot) -> None:
    tb = TextBox("T", font_type="title", width=250)
    qtbot.addWidget(tb)
    tb.show()
    qtbot.waitExposed(tb)


def test_text_box_invalid_font_type_raises() -> None:
    with pytest.raises(ValueError, match="Invalid font_type"):
        TextBox("x", font_type="not_a_valid_type")


def test_text_box_alignment_center(qtbot: QtBot) -> None:
    tb = TextBox("c", alignment="center", width=180)
    qtbot.addWidget(tb)
    tb.show()


# =============================================================================
# Icon
# =============================================================================


def test_icon_smoke(qtbot: QtBot) -> None:
    ic = Icon(size=48, center_text="i")
    qtbot.addWidget(ic)
    ic.show()
    qtbot.waitExposed(ic)


def test_reveal_icon_smoke(qtbot: QtBot) -> None:
    ic = RevealIcon(size=48)
    qtbot.addWidget(ic)
    ic.show()
    qtbot.waitExposed(ic)


def test_pagination_dwell_grace_gates_indicator_icons(qtbot: QtBot) -> None:
    """Page indicators must not register dwells until the bar has expanded
    and the grace period has elapsed — a cursor already parked on an
    indicator during the expand animation used to click the moment its own
    dwell timer ran out."""
    from PySide6.QtCore import QEvent

    from raven_framework.components.scroll_view import PaginationContainer

    parent = QWidget()
    qtbot.addWidget(parent)
    pc = PaginationContainer(parent)
    icons = [Icon(size=10) for _ in range(3)]
    for ic in icons:
        ic.setParent(pc)
    pc.set_icons(icons, 5, 5)

    # Collapsed bar: indicators disarmed.
    assert all(not ic.isEnabled() for ic in icons)

    # Grace timer fires while still hovered/expanded -> armed.
    pc.is_dwelling = True
    pc._arm_icon_dwell()
    assert all(ic.isEnabled() for ic in icons)

    # Leaving collapses the bar and disarms immediately.
    pc.leaveEvent(QEvent(QEvent.Type.Leave))
    assert all(not ic.isEnabled() for ic in icons)

    # A stale grace timeout after collapse must NOT re-arm.
    pc._arm_icon_dwell()
    assert all(not ic.isEnabled() for ic in icons)


@pytest.mark.parametrize("bottom_text", ["", "Home"])
def test_reveal_icon_expanded_circle_fits_within_widget(
    qtbot: QtBot, bottom_text: str
) -> None:
    """The fully-expanded dwell circle must fit inside the widget rect.

    Qt clips painting to the widget, so any overflow shows as the circle's
    edge getting cut off mid-expand. The no-label (home button) case used to
    overflow the bottom by ~scale_pad because the height only carried one
    pad of slack.
    """
    ic = RevealIcon(size=80, bottom_text=bottom_text)
    qtbot.addWidget(ic)
    radius = (ic.size / 2) * ic.expand_max_scale
    cx, cy = ic._icon_center_x(), ic._icon_center_y()
    assert cy + radius <= ic.height(), "circle bottom clips the widget rect"
    assert cy - radius >= 0, "circle top clips the widget rect"
    assert cx - radius >= 0, "circle left clips the widget rect"
    assert cx + radius <= ic.width(), "circle right clips the widget rect"


def test_icon_clicked_and_set_text(qtbot: QtBot) -> None:
    seen: list[str] = []

    def h() -> None:
        seen.append("x")

    ic = Icon(size=40, center_text="0")
    ic.on_clicked(h)
    ic.clicked.emit()
    assert seen == ["x"]
    ic.set_text("ok")
    qtbot.addWidget(ic)


def test_icon_wrap_with_hyphenation() -> None:
    ic = Icon(size=40)
    s = ic.wrap_with_hyphenation("supercalifragilistic", max_word_len=8)
    assert "-" in s or len(s) > 0


def test_icon_set_disabled(qtbot: QtBot) -> None:
    ic = Icon(size=44)
    ic.set_disabled(True)
    assert ic.is_disabled() is True
    ic.set_enabled(True)
    assert ic.is_disabled() is False
    qtbot.addWidget(ic)


# =============================================================================
# Spacer
# =============================================================================


def test_spacer_size_hint(qtbot: QtBot) -> None:
    s = Spacer(width=10, height=20)
    qtbot.addWidget(s)
    sh = s.sizeHint()
    assert sh.width() == 10 and sh.height() == 20


# =============================================================================
# ExpandingIcon
# =============================================================================


def test_expanding_icon_smoke(qtbot: QtBot) -> None:
    e = ExpandingIcon(size=60, bottom_text="")
    qtbot.addWidget(e)
    e.show()
    qtbot.waitExposed(e)


def test_expanding_icon_clicked_emits(qtbot: QtBot) -> None:
    hit: list[bool] = []

    def h() -> None:
        hit.append(True)

    e = ExpandingIcon(size=50)
    e.clicked.connect(h)
    qtbot.addWidget(e)
    e.clicked.emit()
    assert hit == [True]


# =============================================================================
# Container
# =============================================================================


def test_container_with_textbox_shows_and_has_text(qtbot: QtBot) -> None:
    container = Container(width=240, height=200)
    text = TextBox(text="qt-test", width=100)
    container.add(text)
    qtbot.addWidget(container)
    container.show()
    qtbot.waitExposed(container)
    assert text.text() == "qt-test"


def test_container_clear(qtbot: QtBot) -> None:
    c = Container(width=200, height=200)
    c.add(TextBox("x"))
    c.clear()
    qtbot.addWidget(c)


def test_container_add_absolute_position(qtbot: QtBot) -> None:
    c = Container(width=300, height=300)
    t = TextBox("abs", width=50, height=24)
    c.add(t, x=100, y=50)
    qtbot.addWidget(c)
    c.show()
    assert t.pos().x() == 100 and t.pos().y() == 50


def test_container_add_none_raises() -> None:
    c = Container(width=100, height=100)
    with pytest.raises(ValueError, match="Cannot add None"):
        c.add(None)  # type: ignore[arg-type]


def test_container_update_background_style(qtbot: QtBot) -> None:
    c = Container(width=120, height=80, corner_radius=4, border_width=1)
    c.update_background_style(
        background_color="#1a1a1a",
        background_image=None,
        corner_radius=8,
        border_width=2,
        border_color="#FFFFFF",
    )
    qtbot.addWidget(c)
    c.show()
    qtbot.waitExposed(c)


def test_container_clear_removes_children(qtbot: QtBot) -> None:
    c = Container(width=200, height=200)
    c.add(TextBox("a"))
    c.add(TextBox("b"))
    c.clear()
    qtbot.addWidget(c)
    kids = [ch for ch in c.findChildren(TextBox)]
    assert len(kids) == 0


class _CloseTrackingWidget(QWidget):
    """Minimal widget that records whether closeEvent actually ran."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.close_event_fired = False

    def closeEvent(self, event) -> None:
        self.close_event_fired = True
        super().closeEvent(event)


def test_container_clear_fires_close_event(qtbot: QtBot) -> None:
    """clear() previously used deleteLater() only, which never triggers
    closeEvent — so closeEvent-based cleanup (timers, camera/media handles,
    temp files) silently never ran when a widget was removed this way."""
    c = Container(width=200, height=200)
    tracked = _CloseTrackingWidget()
    c.add(tracked)
    c.clear()
    qtbot.addWidget(c)
    assert tracked.close_event_fired is True


# =============================================================================
# HorizontalContainer / VerticalContainer
# =============================================================================


def test_horizontal_container_add(qtbot: QtBot) -> None:
    h = HorizontalContainer(width=300, spacing=5, inner_margin=5)
    h.add(TextBox("a"), TextBox("b"))
    qtbot.addWidget(h)
    h.show()
    qtbot.waitExposed(h)


def test_horizontal_container_clear(qtbot: QtBot) -> None:
    h = HorizontalContainer(width=400, spacing=4)
    h.add(TextBox("1"), TextBox("2"))
    h.clear()
    qtbot.addWidget(h)
    assert len(h.findChildren(TextBox)) == 0


def test_horizontal_container_clear_fires_close_event(qtbot: QtBot) -> None:
    h = HorizontalContainer(width=400, spacing=4)
    tracked = _CloseTrackingWidget()
    h.add(tracked)
    h.clear()
    qtbot.addWidget(h)
    assert tracked.close_event_fired is True


def test_vertical_container_main_flags(qtbot: QtBot) -> None:
    v = VerticalContainer(
        width=300,
        spacing=10,
        inner_margin=(10, 10),
        is_main_container=True,
    )
    v.add(TextBox("line"))
    qtbot.addWidget(v)
    v.show()
    qtbot.waitExposed(v)


def test_vertical_container_page_smoke(qtbot: QtBot) -> None:
    page = VerticalContainer(
        width=320,
        spacing=10,
        inner_margin=10,
        is_main_container=True,
    )
    page.add(TextBox("smoke", width=300))
    qtbot.addWidget(page)
    page.show()
    qtbot.waitExposed(page)


def test_vertical_container_multi_add_and_clear(qtbot: QtBot) -> None:
    v = VerticalContainer(width=200, spacing=2)
    v.add(TextBox("u1"), TextBox("u2"), TextBox("u3"))
    assert len(v.findChildren(TextBox)) == 3
    v.clear()
    qtbot.addWidget(v)
    assert len(v.findChildren(TextBox)) == 0


def test_vertical_container_clear_fires_close_event(qtbot: QtBot) -> None:
    v = VerticalContainer(width=200, spacing=2)
    tracked = _CloseTrackingWidget()
    v.add(tracked)
    v.clear()
    qtbot.addWidget(v)
    assert tracked.close_event_fired is True


# =============================================================================
# Cards
# =============================================================================


def test_components_cards_module_exports_documented_classes() -> None:
    import raven_framework.components.cards as cards

    expected = (
        "TextCardWithButton",
        "TextCardWithTwoButtons",
        "HorizontalTextCardWithButton",
        "HorizontalTextCard",
        "MediaCard",
        "MediaCardWithButton",
        "MediaCardWithTwoButtons",
        "ScrollableListCard",
    )
    for name in expected:
        assert hasattr(cards, name), f"missing {name}"
        assert getattr(cards, name).__name__ == name


def test_text_card_with_button(qtbot: QtBot) -> None:
    seen: list[str] = []

    def on_click() -> None:
        seen.append("go")

    c = TextCardWithButton(
        text="Hi",
        container_width=320,
        button_text="Go",
        on_button_click=on_click,
    )
    qtbot.addWidget(c)
    c.show()
    qtbot.waitExposed(c)
    assert c.text_box.text() == "Hi"
    assert c.button.text == "Go"
    assert c.width() > 0 and c.height() > 0
    c.button.clicked.emit()
    assert seen == ["go"]


def test_text_card_with_two_buttons(qtbot: QtBot) -> None:
    seen: list[str] = []

    c = TextCardWithTwoButtons(
        text="Hi",
        container_width=320,
        button_text_1="A",
        button_text_2="B",
        on_button_1_click=lambda: seen.append("a"),
        on_button_2_click=lambda: seen.append("b"),
    )
    qtbot.addWidget(c)
    c.show()
    qtbot.waitExposed(c)
    assert c.text_box.text() == "Hi"
    buttons = c.findChildren(Button)
    assert len(buttons) == 2
    buttons[0].clicked.emit()
    buttons[1].clicked.emit()
    assert seen == ["a", "b"]


def test_text_card_with_button_auto_height(qtbot: QtBot) -> None:
    c = TextCardWithButton(
        text="short",
        container_width=300,
        button_text="OK",
        auto_height=True,
    )
    qtbot.addWidget(c)
    c.show()
    qtbot.waitExposed(c)
    assert c.height() > 0


def test_horizontal_text_card_with_button(qtbot: QtBot) -> None:
    seen: list[str] = []
    c = HorizontalTextCardWithButton(
        text="Wide",
        container_width=400,
        button_text="OK",
        on_button_click=lambda: seen.append("ok"),
    )
    qtbot.addWidget(c)
    c.show()
    qtbot.waitExposed(c)
    assert c.text_box.text() == "Wide"
    button = c.findChild(Button)
    assert button is not None
    assert button.text == "OK"
    button.clicked.emit()
    assert seen == ["ok"]


def test_horizontal_text_card(qtbot: QtBot) -> None:
    c = HorizontalTextCard(text="Only text", container_width=380)
    qtbot.addWidget(c)
    c.show()
    qtbot.waitExposed(c)
    assert c.text_box.text() == "Only text"
    assert c.width() == 380


def test_media_card_no_image(qtbot: QtBot) -> None:
    c = MediaCard(title_text="T", container_width=360)
    qtbot.addWidget(c)
    c.show()
    qtbot.waitExposed(c)
    assert c.width() == 360 and c.height() > 0


def test_media_card_with_image(qtbot: QtBot, tiny_png_path: str) -> None:
    c = MediaCard(
        title_text="T",
        image_path=tiny_png_path,
        image_height=120,
        container_width=360,
    )
    qtbot.addWidget(c)
    c.show()
    qtbot.waitExposed(c)


def test_media_card_with_button(qtbot: QtBot, tiny_png_path: str) -> None:
    c = MediaCardWithButton(
        title_text="T",
        button_text="Go",
        image_path=tiny_png_path,
        image_height=100,
        container_width=360,
    )
    qtbot.addWidget(c)
    c.show()
    qtbot.waitExposed(c)


def test_media_card_with_two_buttons(qtbot: QtBot, tiny_png_path: str) -> None:
    c = MediaCardWithTwoButtons(
        title_text="T",
        button_text_1="A",
        button_text_2="B",
        image_path=tiny_png_path,
        image_height=100,
        container_width=380,
    )
    qtbot.addWidget(c)
    c.show()
    qtbot.waitExposed(c)


def test_scrollable_list_card_small(qtbot: QtBot) -> None:
    c = ScrollableListCard(
        title_text="List",
        info_strings=["one", "two"],
        button_strings=["v", "v"],
        card_width=400,
        card_height=500,
    )
    qtbot.addWidget(c)
    c.show()
    qtbot.waitExposed(c)


def test_scrollable_list_card_item_callbacks(qtbot: QtBot) -> None:
    seen: list[str] = []

    def pick(name: str) -> None:
        seen.append(name)

    c = ScrollableListCard(
        title_text="Pick",
        info_strings=["apple", "berry"],
        on_item_click=[(pick, "apple"), (pick, "berry")],
        card_width=420,
        card_height=480,
    )
    qtbot.addWidget(c)
    c.show()
    qtbot.waitExposed(c)
    row_buttons = c.findChildren(Button)
    assert len(row_buttons) >= 2
    row_buttons[0].clicked.emit()
    row_buttons[1].clicked.emit()
    assert seen == ["apple", "berry"]


# =============================================================================
# ScrollView
# =============================================================================


def test_scroll_view_with_tall_content(qtbot: QtBot) -> None:
    inner = VerticalContainer(width=200, spacing=4)
    for i in range(8):
        inner.add(TextBox(f"Line {i}", width=180))
    sv = ScrollView(
        content_widget=inner,
        width=280,
        height=180,
        show_pagination=False,
    )
    qtbot.addWidget(sv)
    sv.show()
    qtbot.waitExposed(sv)
    sv.scroll_next()
    sv.scroll_prev()


def test_scroll_view_get_zone_and_scroll_to(qtbot: QtBot) -> None:
    inner = VerticalContainer(width=180, spacing=2)
    inner.add(TextBox("only"))
    sv = ScrollView(
        content_widget=inner,
        width=200,
        height=220,
        show_pagination=False,
        zone_height=20,
    )
    qtbot.addWidget(sv)
    sv.show()
    qtbot.waitExposed(sv)
    assert sv.get_zone(QPoint(5, 5)) == "top"
    assert sv.get_zone(QPoint(5, 100)) == "middle"
    assert sv.get_zone(QPoint(5, 210)) == "bottom"
    sv.scroll_to(10)
    sv.scroll_to_page(0)


def test_scroll_view_auto_scroll_start_stop(qtbot: QtBot) -> None:
    inner = VerticalContainer(width=180, spacing=2)
    for i in range(6):
        inner.add(TextBox(f"L{i}"))
    sv = ScrollView(
        content_widget=inner,
        width=200,
        height=150,
        show_pagination=True,
    )
    qtbot.addWidget(sv)
    sv.show()
    qtbot.waitExposed(sv)
    sv.update_pagination_colors()
    sv.start_auto_scroll(direction="down", speed=1, interval=40)
    qtbot.wait(80)
    sv.stop_auto_scroll()
    sv.stop_all_scroll()


def test_scroll_view_clear(qtbot: QtBot) -> None:
    inner = TextBox("gone")
    sv = ScrollView(content_widget=inner, width=200, height=120, show_pagination=False)
    qtbot.addWidget(sv)
    sv.show()
    sv.clear()


def test_scroll_view_clear_fires_content_widget_close_event(qtbot: QtBot) -> None:
    """clear() previously removed the content widget via deleteLater() only,
    which never triggers closeEvent — so a MediaViewer/WebViewer used as
    content would silently skip its own resource cleanup."""
    tracked = _CloseTrackingWidget()
    sv = ScrollView(
        content_widget=tracked, width=200, height=120, show_pagination=False
    )
    qtbot.addWidget(sv)
    sv.show()
    sv.clear()
    assert tracked.close_event_fired is True


def test_scroll_view_close_event_stops_timers(qtbot: QtBot) -> None:
    """ScrollView had no closeEvent, so its 4 timers kept running past close()."""
    inner = TextBox("content")
    sv = ScrollView(content_widget=inner, width=200, height=120, show_pagination=False)
    qtbot.addWidget(sv)
    sv.show()
    sv.start_auto_scroll(direction="down", speed=1, interval=20)
    assert sv.teleprompter_timer.isActive()

    sv.close()

    assert not sv.teleprompter_timer.isActive()
    assert not sv.dwell_timer.isActive()
    assert not sv.auto_scroll_timer.isActive()
    assert not sv.continuous_scroll_timer.isActive()


# =============================================================================
# MediaViewer
# =============================================================================


def test_media_viewer_static_image(qtbot: QtBot, tiny_png_path: str) -> None:
    mv = MediaViewer(media_path=tiny_png_path, width=64, height=64)
    qtbot.addWidget(mv)
    mv.show()
    qtbot.waitExposed(mv)


def test_media_viewer_load_media_idempotent(qtbot: QtBot, tiny_png_path: str) -> None:
    mv = MediaViewer(media_path=tiny_png_path, width=64, height=64)
    mv.load_media(tiny_png_path)
    mv.play_video()
    mv.pause_video()
    mv.cleanup_video_resources()
    mv.cleanup_gif_resources()
    qtbot.addWidget(mv)


def test_media_viewer_scaled_pixmap_cover(qtbot: QtBot, tiny_png_path: str) -> None:
    mv = MediaViewer(media_path=tiny_png_path, width=64, height=64)
    pm = QPixmap(tiny_png_path)
    out = mv.scaled_pixmap_cover(pm, 32, 32)
    assert not out.isNull()
    qtbot.addWidget(mv)


def test_media_viewer_set_frame_bgr_array(qtbot: QtBot) -> None:
    mv = MediaViewer(media_path="", width=64, height=64)
    frame = np.zeros((16, 16, 3), dtype=np.uint8)
    frame[:, :] = (0, 255, 0)
    mv.set_frame(frame)
    qtbot.addWidget(mv)


# =============================================================================
# ModelViewer / load_obj_mesh
# =============================================================================


def test_load_obj_mesh_minimal(tiny_obj_path: str) -> None:
    vertices, material_groups, vertex_colors, texcoords = load_obj_mesh(tiny_obj_path)
    assert vertices.size > 0
    assert isinstance(material_groups, list)


def test_model_viewer_widget(qtbot: QtBot, tiny_obj_path: str) -> None:
    try:
        mv = ModelViewer(tiny_obj_path, width=128, height=128, is_rotating=False)
    except Exception as exc:
        pytest.skip(f"ModelViewer / OpenGL init failed: {exc}")
    qtbot.addWidget(mv)
    mv.show()
    qtbot.waitExposed(mv)
    mv.set_rotation(10.0)


# =============================================================================
# WebViewer
# =============================================================================


def test_web_viewer_construct_if_engine_available(qtbot: QtBot) -> None:
    wv_mod = importlib.import_module("raven_framework.components.web_viewer")
    if wv_mod.QWebEngineView is None:
        pytest.skip("Qt WebEngine not available")
    w = wv_mod.WebViewer("https://example.com", width=120, height=80)
    qtbot.addWidget(w)
    w.show()
    qtbot.waitExposed(w)
    assert w.web_view.url().host() == "example.com"
    with qtbot.waitSignal(w.web_view.loadFinished, timeout=30_000) as blocker:
        w.web_view.reload()
    assert blocker.args[0] is True


def test_web_viewer_blocks_unsafe_url() -> None:
    """WebViewer previously accepted any URL with no safety check at all."""
    wv_mod = importlib.import_module("raven_framework.components.web_viewer")
    with pytest.raises(ValueError, match="blocked"):
        wv_mod.WebViewer("http://127.0.0.1/admin")


# =============================================================================
# components package __getattr__
# =============================================================================


def test_components_lazy_model_viewer() -> None:
    import raven_framework.components as c

    cls = getattr(c, "ModelViewer")
    assert cls.__name__ == "ModelViewer"


def test_components_unknown_raises() -> None:
    import raven_framework.components as c

    with pytest.raises(AttributeError):
        getattr(c, "NotAComponent")


def test_components_lazy_webviewer_class() -> None:
    import raven_framework.components as c

    cls = getattr(c, "WebViewer")
    assert cls.__name__ == "WebViewer"


def test_components_lazy_mediaviewer_class() -> None:
    import raven_framework.components as c

    cls = getattr(c, "MediaViewer")
    assert cls.__name__ == "MediaViewer"
