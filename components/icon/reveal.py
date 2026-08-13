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
Reveal icon widget for Raven Framework.

``RevealIcon`` is the launch-treatment sibling of the classic ``Icon``
(see ``icon.py`` in this package): hover grows the icon and reveals a halo
sampled from the image's rim colors, a slow breath pulse acts as the dwell
timer, and dwell completion expands the icon in place — optionally sweeping
a fullscreen blackout from the icon center that reveals whatever the click
triggers (the treatment used by the system app launcher and the RavenApp
home button).

Supports circular and rounded-rectangular shapes, background images, center
text, and optional bottom text, like the classic ``Icon``.
"""

# Standard library imports
import math
from functools import partial
from typing import Any, Callable, Optional

# PySide6 imports
from PySide6.QtCore import (
    Property,
    QAbstractAnimation,
    QEvent,
    QParallelAnimationGroup,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QSequentialAnimationGroup,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QEnterEvent,
    QFont,
    QFontMetrics,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QWidget

# Local imports
from ...helpers.animation_utils import (
    RavenCurveLike,
    configure_property_animation,
    make_pause_animation,
    make_property_animation,
    resolve_curve,
)
from ...helpers.font_utils import create_font
from ...helpers.logger import get_logger
from ...helpers.themes import RAVEN_CORE
from ...helpers.utils_light import load_config, to_qcolor

theme = RAVEN_CORE

log = get_logger("RevealIcon")

# Load configuration
_config = load_config()
_icon_cfg = _config["icon"]
_pulse_cfg = _config["animation"]["reveal_icon"]

# Constants
DEFAULT_ICON_SIZE = _icon_cfg["DEFAULT_ICON_SIZE"]
DEFAULT_EXTRA_WIDTH = _icon_cfg["DEFAULT_EXTRA_WIDTH"]
LABEL_FONT_SIZE_OFFSET = _icon_cfg["LABEL_FONT_SIZE_OFFSET"]
SQUARE_CORNER_RADIUS_RATIO = _icon_cfg["SQUARE_CORNER_RADIUS_RATIO"]
SCALE_THRESHOLD = _icon_cfg["SCALE_THRESHOLD"]
DEFAULT_MAX_WORD_LEN = _icon_cfg["DEFAULT_MAX_WORD_LEN"]
DEFAULT_BOTTOM_TEXT_SPACING = _icon_cfg["DEFAULT_BOTTOM_TEXT_SPACING"]

# Layout constants. Grid tuning (row spacing, margins) is
# NOT defined here — it belongs to the screen laying out the grid (e.g.
# the launcher's config); the grid_* statics take those as arguments.
LABEL_ROW_BASE_PADDING = 20
NO_LABEL_ROW_EXTRA = 10
BLACKOUT_RADIUS_EPSILON = 1.0
MIN_BLACKOUT_START_RADIUS = 1.0
# How long a generic (non-launch) reveal icon stays hidden after a dwell click
# before fading back in at rest and accepting hovers again.
DEFAULT_REARM_DELAY_MS = 1000

DEFAULT_BASE_SCALE = _pulse_cfg["HOVER_GROW_FROM_SCALE"]
DEFAULT_PULSE_PEAK_SCALE = _pulse_cfg["HOVER_GROW_TO_SCALE"]
DEFAULT_PULSE_DIP_SCALE = _pulse_cfg["PULSE_DIP_SCALE"]
DEFAULT_EXPAND_MAX_SCALE = _pulse_cfg["EXPAND_TO_SCALE"]
DEFAULT_PULSE_COUNT = _pulse_cfg["PULSE_COUNT"]
DEFAULT_HOVER_GROW_MS = _pulse_cfg["HOVER_GROW_MS"]
DEFAULT_HOVER_HOLD_MS = _pulse_cfg["HOVER_HOLD_MS"]
DEFAULT_BREATH_DIP_MS = _pulse_cfg["BREATH_DIP_MS"]
DEFAULT_BREATH_RETURN_MS = _pulse_cfg["BREATH_RETURN_MS"]
DEFAULT_FINAL_DIP_MS = _pulse_cfg["FINAL_DIP_MS"]
DEFAULT_EXPAND_MS = _pulse_cfg["EXPAND_MS"]
DEFAULT_BLACKOUT_MS = _pulse_cfg["BLACKOUT_MS"]
DEFAULT_RESET_ON_LEAVE_MS = _pulse_cfg["RESET_ON_LEAVE_MS"]
DEFAULT_HOVER_GROW_CURVE = resolve_curve(_pulse_cfg["HOVER_GROW_CURVE"])
DEFAULT_BREATH_DIP_CURVE = resolve_curve(_pulse_cfg["BREATH_DIP_CURVE"])
DEFAULT_BREATH_RETURN_CURVE = resolve_curve(_pulse_cfg["BREATH_RETURN_CURVE"])
DEFAULT_FINAL_DIP_CURVE = resolve_curve(_pulse_cfg["FINAL_DIP_CURVE"])
DEFAULT_EXPAND_CURVE = resolve_curve(_pulse_cfg["EXPAND_CURVE"])
DEFAULT_BLACKOUT_CURVE = resolve_curve(_pulse_cfg["BLACKOUT_CURVE"])
DEFAULT_RESET_ON_LEAVE_CURVE = resolve_curve(_pulse_cfg["RESET_ON_LEAVE_CURVE"])

_BLACKOUT_QCOLOR = QColor(0, 0, 0)  # pure black for waveguide occlusion


def _smoothstep(t: float) -> float:
    """Ease a 0..1 fraction with a smooth (zero-slope at both ends) curve —
    used to soften the halo's blurred-ring opacity ramps."""
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def _label_row_padding(label_spacing: int) -> int:
    return LABEL_ROW_BASE_PADDING + label_spacing


class LaunchBlackoutOverlay(QWidget):
    """Fullscreen black overlay that grows from the launching icon center.

    ``hold_ms`` keeps the full-black cover up for that long after the sweep
    completes (on_complete still fires immediately), so whatever the click
    triggers — e.g. the app's exit fade — plays out hidden behind it.
    """

    def __init__(
        self,
        parent: QWidget,
        origin: QPointF,
        width: int,
        height: int,
        start_radius: float,
        duration_ms: int,
        curve: RavenCurveLike,
        on_complete: Callable[[], None],
        occlusion_targets: Optional[list] = None,
        hold_ms: int = 0,
    ) -> None:
        super().__init__(parent)
        self._origin = origin
        self._max_radius = math.hypot(float(width), float(height))
        self._radius = float(start_radius)
        self._on_complete = on_complete
        self._hold_ms = max(0, int(hold_ms))
        # (widget, hide_radius) pairs: hide each widget whole once the circle's
        # edge reaches it, rather than clipping it as the circle sweeps past.
        self._occlusion_targets = occlusion_targets or []
        self.setGeometry(0, 0, width, height)
        self.setAutoFillBackground(False)

        self._anim = make_property_animation(
            self,
            b"radius",
            float(start_radius),
            self._max_radius + BLACKOUT_RADIUS_EPSILON,
            duration_ms,
            curve,
            self,
        )
        self._anim.finished.connect(self._handle_finished)

    def get_radius(self) -> float:
        return self._radius

    def set_radius(self, value: float) -> None:
        self._radius = float(value)
        for widget, hide_radius in self._occlusion_targets:
            if self._radius >= hide_radius and widget.isVisible():
                widget.hide()
        self.update()

    radius = Property(float, get_radius, set_radius)

    def start(self) -> None:
        self.show()
        self.raise_()
        self._anim.start()

    def _handle_finished(self) -> None:
        callback = self._on_complete
        if self._hold_ms > 0:
            self.raise_()
            QTimer.singleShot(self._hold_ms, self.deleteLater)
        else:
            self.deleteLater()
        callback()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_BLACKOUT_QCOLOR)
        if self._radius >= self._max_radius:
            painter.fillRect(self.rect(), _BLACKOUT_QCOLOR)
        else:
            painter.drawEllipse(self._origin, self._radius, self._radius)


class RevealIcon(QWidget):
    """
    A customizable UI widget that displays a circular or rounded-rect icon with
    breath-pulse dwell interaction, background image, halo, and optional
    center/bottom text.

    Hover grows the icon and shows a halo sampled from the image's rim colors;
    a slow breath pulse acts as the dwell timer, and dwell completion expands
    the icon in place before emitting ``clicked``. When ``overlay_parent`` is
    provided, a fullscreen blackout sweeps from the icon center first,
    revealing whatever the click triggers (app-launch treatment).

    For the classic hover-scale + progress-arc dwell icon, use ``Icon`` from
    this package instead.

    Signals:
        clicked: Emitted when the icon is clicked or dwell-clicked.

    Args:
        background_image_path (Optional[str]): Path to a background image rendered inside the icon. Defaults to None.
        size (int): Width and height of the icon (square). Defaults to 80.
        background_color (str): Fill color of the icon background as string. Defaults to theme.basic_palette.black.
        center_text (str): Text to display in the center of the icon. Defaults to "".
        text_size (int): Font size of the center text. Defaults to theme.fonts.body.size.
        text_color (str): Color of the center text as string. Defaults to theme.fonts.body.color.
        font (str): Font family (e.g. 'inter'). Defaults to theme.fonts.body.family.
        font_weight (str): Font weight, one of 'light', 'normal', 'medium', 'bold', or 'black'. Defaults to theme.fonts.body.weight.
        corner_radius (Optional[int]): Corner curvature for rounded-rect mode.
            Defaults to size * SQUARE_CORNER_RADIUS_RATIO.
        outline_width (int): Width of the circular/rectangular outline stroke. Defaults to theme.borders.highlight_width + 2.
        outline_color (str): Color of the circular/rectangular outline stroke as string. Defaults to theme.borders.highlight_color_icon.
        scale_by (Optional[float]): Sets the hover peak scale to 1 + scale_by
            (config HOVER_GROW_TO_SCALE when omitted).
        is_square (bool): Whether to use a rounded rectangle (True) or circle (False). Defaults to False.
        enable_click (bool): Whether to allow dwell-based clicking. Defaults to True.
        bottom_text (str): Optional text displayed below the icon. Defaults to "".
        bottom_text_spacing (Optional[int]): Vertical spacing in pixels between the icon and bottom text.
            Defaults to 13 (config DEFAULT_BOTTOM_TEXT_SPACING).
        disabled (bool): If True, icon is disabled and won't respond to clicks or hover. Defaults to False.

    Dwell/launch args (all defaults come from config ``animation.reveal_icon``):
        pulse_count (int): Number of breath pulses in the dwell sequence.
        base_scale / pulse_dip_scale / pulse_peak_scale / expand_max_scale (float): Scale keyframes.
        hover_grow_ms / hover_hold_ms / breath_dip_ms / breath_return_ms / final_dip_ms /
            expand_ms / blackout_ms / reset_on_leave_ms (int): Phase durations.
        curve / hover_grow_curve / breath_dip_curve / breath_return_curve / final_dip_curve /
            expand_curve / blackout_curve / reset_on_leave_curve: Easing curves per phase.
        overlay_parent (Optional[QWidget]): Parent for the fullscreen launch blackout; when set,
            dwell completion latches the icon and sweeps the blackout before emitting clicked.
        screen_width / screen_height (Optional[int]): Blackout coverage (overlay_parent size when omitted).
        skip_expand (bool): Emit clicked after the final dip without the in-place expand.
        launch_on_scale_complete (bool): Emit clicked when the expand scale finishes (not the full morph).
        layout_expand_max_scale (Optional[float]): Layout padding scale override.
        occlusion_icons_provider (Optional[Callable]): Returns sibling icons the blackout hides as it grows.
        halo_* : Halo fill/border/blur tuning (see attributes of the same name).
        rearm_delay_ms (int): Generic icons (no overlay_parent) disappear after a dwell click and
            fade back in at rest after this delay, re-armed for the next dwell. Defaults to 1000.
        blackout_hold_ms (int): How long the launch blackout stays fully black after its sweep
            completes (clicked fires immediately), hiding whatever the click triggers — e.g. the
            app's exit fade. Defaults to 0 (remove as soon as the sweep ends).
    """

    clicked = Signal()

    # ------------------------------------------------------------------
    # Grid layout helpers (used by the system app launcher)
    # ------------------------------------------------------------------

    @staticmethod
    def layout_slot_size(size: int) -> int:
        return int(size) + DEFAULT_EXTRA_WIDTH

    @staticmethod
    def layout_row_height(size: int, show_names: bool, label_spacing: int = 0) -> int:
        return RevealIcon.layout_content_height(size, show_names, label_spacing)

    @staticmethod
    def scale_overflow_pad(
        size: int, expand_max_scale: float = DEFAULT_EXPAND_MAX_SCALE
    ) -> int:
        return int((size * (expand_max_scale - 1.0) + 1) // 2)

    @staticmethod
    def layout_content_height(
        size: int, show_names: bool, label_spacing: int = 0
    ) -> int:
        if show_names:
            return int(size) + _label_row_padding(label_spacing)
        return int(size) + NO_LABEL_ROW_EXTRA

    @staticmethod
    def grid_origin_x(slot_x: int, scale_pad: int, margin_x: int) -> int:
        return margin_x + slot_x - scale_pad

    @staticmethod
    def grid_origin_y(slot_y: int, scale_pad: int, margin_y: int) -> int:
        return margin_y + slot_y - scale_pad

    @staticmethod
    def grid_slot_x_two_app(
        app_size: int,
        horizontal_padding: int,
        row_spacing: int,
    ) -> tuple[int, int]:
        pitch = app_size + DEFAULT_EXTRA_WIDTH + 2 * row_spacing
        start = horizontal_padding + row_spacing
        return start, start + pitch

    @staticmethod
    def grid_slot_x_three_app(app_size: int, row_spacing: int) -> tuple[int, int, int]:
        pitch = app_size + DEFAULT_EXTRA_WIDTH + 2 * row_spacing
        return 0, pitch, 2 * pitch

    def circle_bounds_in_widget(self) -> tuple[int, int, int, int]:
        """
        Pixel bounds (left, top, right, bottom) of the drawable icon circle
        in this widget's local coordinates (base scale, no expand).
        """
        half = self.size / 2
        cx = self._icon_center_x()
        cy = self._icon_center_y()
        return (
            int(round(cx - half)),
            int(round(cy - half)),
            int(round(cx + half)),
            int(round(cy + half)),
        )

    def __init__(
        self,
        background_image_path: Optional[str] = None,
        size: int = DEFAULT_ICON_SIZE,
        background_color: str = theme.basic_palette.black,
        center_text: str = "",
        text_size: int = theme.fonts.body.size,
        text_color: str = theme.fonts.body.color,
        font: str = theme.fonts.body.family,
        font_weight: str = theme.fonts.body.weight,
        corner_radius: Optional[int] = None,
        outline_width: int = theme.borders.highlight_width + 2,
        outline_color: str = theme.borders.highlight_color_icon,
        scale_by: Optional[float] = None,
        is_square: bool = False,
        enable_click: bool = True,
        bottom_text: str = "",
        bottom_text_spacing: Optional[int] = None,
        disabled: bool = False,
        # ------- dwell/launch parameters -------
        pulse_count: int = DEFAULT_PULSE_COUNT,
        base_scale: float = DEFAULT_BASE_SCALE,
        pulse_dip_scale: float = DEFAULT_PULSE_DIP_SCALE,
        pulse_peak_scale: float = DEFAULT_PULSE_PEAK_SCALE,
        expand_max_scale: float = DEFAULT_EXPAND_MAX_SCALE,
        initial_hover_ms: Optional[int] = None,
        hover_grow_ms: Optional[int] = None,
        hover_hold_ms: int = DEFAULT_HOVER_HOLD_MS,
        pulse_ms: Optional[int] = None,
        breath_dip_ms: Optional[int] = None,
        breath_return_ms: Optional[int] = None,
        final_dip_ms: Optional[int] = None,
        expand_ms: Optional[int] = None,
        reset_ms: Optional[int] = None,
        reset_on_leave_ms: Optional[int] = None,
        overlay_parent: Optional[QWidget] = None,
        screen_width: Optional[int] = None,
        screen_height: Optional[int] = None,
        blackout_ms: int = DEFAULT_BLACKOUT_MS,
        blackout_hold_ms: int = 0,
        curve: RavenCurveLike = DEFAULT_HOVER_GROW_CURVE,
        hover_grow_curve: Optional[RavenCurveLike] = None,
        breath_dip_curve: Optional[RavenCurveLike] = None,
        breath_return_curve: Optional[RavenCurveLike] = None,
        final_dip_curve: Optional[RavenCurveLike] = None,
        expand_curve: Optional[RavenCurveLike] = None,
        blackout_curve: Optional[RavenCurveLike] = None,
        reset_curve: Optional[RavenCurveLike] = None,
        reset_on_leave_curve: Optional[RavenCurveLike] = None,
        skip_expand: bool = False,
        launch_on_scale_complete: bool = False,
        layout_expand_max_scale: Optional[float] = None,
        occlusion_icons_provider: Optional[Callable[[], list]] = None,
        halo_color: str = theme.basic_palette.white,
        halo_max_scale: Optional[float] = None,
        halo_fill_opacity: float = 0.5,
        halo_border_peak_opacity: float = 0.9,
        halo_border_width_ratio: float = 1.0 / 280.0,  # fraction of size, not px
        halo_blur_px: float = 4.0,
        halo_blur_steps: int = 24,
        halo_border_sample_band_px: float = 10.0,
        halo_border_samples: int = 32,
        rearm_delay_ms: int = DEFAULT_REARM_DELAY_MS,
        **_: Any,
    ) -> None:
        """
        Initialize the RevealIcon widget.

        See class docstring for parameter descriptions.
        """
        super().__init__()

        self.is_square: bool = is_square
        self.size: int = int(size)
        self.full_diameter: int = self.size
        self.enable_click: bool = enable_click
        self.disabled: bool = disabled

        self.text: str = center_text
        self.text_size: int = int(text_size)
        self.text_color: QColor = to_qcolor(text_color)
        self.font: str = font
        self.font_weight: str = font_weight
        self.color: QColor = to_qcolor(background_color)
        self.background_color: QColor = self.color
        self.outline_width: int = int(outline_width)
        self.outline_color: QColor = to_qcolor(outline_color)
        self.bottom_text: str = bottom_text
        self.bottom_text_visible: bool = bool(bottom_text)

        self.corner_radius: float = (
            float(corner_radius)
            if corner_radius is not None
            else self.size * SQUARE_CORNER_RADIUS_RATIO
        )
        self.bottom_text_spacing: int = int(
            bottom_text_spacing
            if bottom_text_spacing is not None
            else DEFAULT_BOTTOM_TEXT_SPACING
        )

        # Returns the sibling launcher icons; the launch blackout circle hides
        # each of them whole the moment its growing edge reaches them.
        self._occlusion_icons_provider = occlusion_icons_provider
        self.hover_grow_curve = resolve_curve(
            hover_grow_curve or curve, default=DEFAULT_HOVER_GROW_CURVE
        )
        self.breath_dip_curve = resolve_curve(
            breath_dip_curve or curve, default=DEFAULT_BREATH_DIP_CURVE
        )
        self.breath_return_curve = resolve_curve(
            breath_return_curve or curve, default=DEFAULT_BREATH_RETURN_CURVE
        )
        self.final_dip_curve = resolve_curve(
            final_dip_curve or curve, default=DEFAULT_FINAL_DIP_CURVE
        )
        self.expand_curve = resolve_curve(
            expand_curve or curve, default=DEFAULT_EXPAND_CURVE
        )
        self.blackout_curve = resolve_curve(
            blackout_curve or curve, default=DEFAULT_BLACKOUT_CURVE
        )
        self.reset_curve = resolve_curve(
            reset_on_leave_curve or reset_curve or curve,
            default=DEFAULT_RESET_ON_LEAVE_CURVE,
        )

        self.pulse_count = max(1, int(pulse_count))
        self.base_scale = float(base_scale)
        if scale_by is not None:
            self.hover_scale = 1.0 + float(scale_by)
        else:
            self.hover_scale = float(pulse_peak_scale)
        self.pulse_dip_scale = float(pulse_dip_scale)
        self.expand_max_scale = float(expand_max_scale)

        self.halo_color = to_qcolor(halo_color)  # fallback fill if no pixmap/gradient
        self.halo_max_scale = (
            float(halo_max_scale) if halo_max_scale is not None else self.hover_scale
        )
        self.halo_fill_opacity = float(halo_fill_opacity)
        self.halo_border_peak_opacity = float(halo_border_peak_opacity)
        self.halo_border_width = float(halo_border_width_ratio) * self.size
        self.halo_blur_px = max(1.0, float(halo_blur_px))
        self.halo_blur_steps = max(2, int(halo_blur_steps))
        self.halo_border_sample_band_px = float(halo_border_sample_band_px)
        self.halo_border_samples = max(3, int(halo_border_samples))
        self._halo_border_gradient: Optional[QConicalGradient] = None
        self._halo_active = False
        self._halo_scale = self.halo_max_scale  # animatable; see halo_scale Property

        legacy_pulse_ms = max(1, int(pulse_ms)) if pulse_ms is not None else None
        self.initial_hover_ms = max(
            0,
            int(
                hover_grow_ms
                if hover_grow_ms is not None
                else (
                    initial_hover_ms
                    if initial_hover_ms is not None
                    else DEFAULT_HOVER_GROW_MS
                )
            ),
        )
        self.hover_hold_ms = max(0, int(hover_hold_ms))
        self.breath_dip_ms = max(
            1,
            int(
                breath_dip_ms
                if breath_dip_ms is not None
                else (
                    legacy_pulse_ms
                    if legacy_pulse_ms is not None
                    else DEFAULT_BREATH_DIP_MS
                )
            ),
        )
        self.breath_return_ms = max(
            1,
            int(
                breath_return_ms
                if breath_return_ms is not None
                else (
                    legacy_pulse_ms
                    if legacy_pulse_ms is not None
                    else DEFAULT_BREATH_RETURN_MS
                )
            ),
        )
        self.final_dip_ms = max(
            1,
            int(
                final_dip_ms
                if final_dip_ms is not None
                else (
                    legacy_pulse_ms
                    if legacy_pulse_ms is not None
                    else DEFAULT_FINAL_DIP_MS
                )
            ),
        )
        self.reset_ms = max(
            0,
            int(
                reset_on_leave_ms
                if reset_on_leave_ms is not None
                else (reset_ms if reset_ms is not None else DEFAULT_RESET_ON_LEAVE_MS)
            ),
        )
        if expand_ms is not None:
            self.expand_ms = max(1, int(expand_ms))
        else:
            self.expand_ms = max(1, int(DEFAULT_EXPAND_MS))

        self._skip_expand = bool(skip_expand)
        self._launch_on_scale_complete = bool(launch_on_scale_complete)
        self._scale = self.base_scale
        self._morph = 0.0
        self._expanding = False
        self._dwell_launched = False
        self._overlay_parent = overlay_parent
        self._screen_width = screen_width
        self._screen_height = screen_height
        self._blackout_ms = max(0, int(blackout_ms))
        self._blackout_hold_ms = max(0, int(blackout_hold_ms))
        self._blackout_overlay: Optional[LaunchBlackoutOverlay] = None
        # Post-dwell disappearance on generic icons: hidden, then revealed and
        # re-armed after this delay.
        self._rearm_delay_ms = max(0, int(rearm_delay_ms))
        self._hidden_for_rearm = False
        self._rearm_timer = QTimer(self)
        self._rearm_timer.setSingleShot(True)
        self._rearm_timer.timeout.connect(self._begin_rearm_reveal)

        self._pixmap: Optional[QPixmap] = None
        self._load_pulse_pixmap(background_image_path)
        self._halo_border_gradient = self._build_halo_border_gradient()

        extra_width = DEFAULT_EXTRA_WIDTH if self.bottom_text else 0
        pad_scale = (
            float(layout_expand_max_scale)
            if layout_expand_max_scale is not None
            else self.expand_max_scale
        )
        self._scale_pad = self.scale_overflow_pad(self.size, pad_scale)
        self.scale_pad = self._scale_pad
        layout_width = self.size + extra_width
        content_height = self.layout_content_height(
            self.size, bool(self.bottom_text), self.bottom_text_spacing
        )
        # Pad the height on BOTH sides of the content, like the width. With a
        # single pad the no-label layout leaves only ~5px of slack below the
        # circle, so the dwell expand (size/2 * (expand_max_scale - 1) ≈ one
        # full pad) painted past the widget rect and Qt clipped the circle's
        # bottom edge for the instant before the blackout covered it.
        self.setFixedSize(
            layout_width + 2 * self._scale_pad,
            content_height + 2 * self._scale_pad,
        )
        self.setAttribute(Qt.WA_Hover, True)
        self.setAutoFillBackground(False)

        self._bottom_font: Optional[QFont] = None
        if self.bottom_text:
            self._bottom_font = create_font(
                self.font,
                max(self.text_size - LABEL_FONT_SIZE_OFFSET, 1),
                self.font_weight,
            )

        self._hover_sequence = self._build_hover_sequence()
        self._reset_scale_anim = QPropertyAnimation(self, b"scale")
        self._reset_morph_anim = QPropertyAnimation(self, b"morph")
        self._reset_halo_scale_anim = QPropertyAnimation(self, b"halo_scale")

    def _load_pulse_pixmap(self, background_image_path: Optional[str]) -> None:
        """Load and pre-scale the icon image for painting."""
        self._pixmap = None
        self.bg_image = None
        if not background_image_path:
            return
        try:
            source = QPixmap(background_image_path)
        except Exception as e:
            log.error(f"Error loading background image: {e}")
            return
        if source.isNull():
            log.warning(f"Failed to load image: {background_image_path}")
            return
        self.bg_image = source
        self._pixmap = source.scaled(
            self.size,
            self.size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    # ------------------------------------------------------------------
    # Qt event handlers
    # ------------------------------------------------------------------

    def enterEvent(self, event: QEnterEvent) -> None:
        """
        Handle mouse enter event.

        Starts the hover grow and the breath-pulse dwell sequence.

        Args:
            event: Mouse enter event from Qt.
        """
        if self.disabled or not self.isEnabled():
            super().enterEvent(event)
            return

        if self._dwell_launched or not self.enable_click:
            super().enterEvent(event)
            return
        self._stop_all_animations()
        self._reset_expand_state()
        self._hover_sequence.start()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        """
        Handle mouse leave event.

        Resets dwell progress and returns the icon to its resting scale.

        Args:
            event: Mouse leave event from Qt.
        """
        if self.disabled or not self.isEnabled():
            super().leaveEvent(event)
            return

        if self._dwell_launched or not self.enable_click:
            super().leaveEvent(event)
            return
        self._stop_all_animations()
        if self._expanding:
            self._animate_reset_to_base(self._reset_expand_state)
        else:
            self._animate_reset_to_base()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """
        Handle mouse press event.

        Manually triggers click on left mouse button press. Immediately emits
        the clicked signal.

        Args:
            event: Mouse press event from Qt.
        """
        if self.disabled or not self.isEnabled():
            super().mousePressEvent(event)
            return

        if self.enable_click and event.button() == Qt.LeftButton:
            self._stop_all_animations()
            self.clicked.emit()
        super().mousePressEvent(event)

    # ------------------------------------------------------------------
    # Dwell animation (property-animation driven)
    # ------------------------------------------------------------------

    def _build_hover_sequence(self) -> QSequentialAnimationGroup:
        group = QSequentialAnimationGroup(self)

        initial_grow = make_property_animation(
            self,
            b"scale",
            self.base_scale,
            self.hover_scale,
            self.initial_hover_ms,
            self.hover_grow_curve,
            self,
        )
        initial_grow.finished.connect(self._on_initial_grow_finished)
        group.addAnimation(initial_grow)
        group.addAnimation(make_pause_animation(self.hover_hold_ms, self))

        for _ in range(self.pulse_count - 1):
            group.addAnimation(self._make_breath_dip())
            group.addAnimation(self._make_breath_return())

        final_dip = self._make_final_dip()
        group.addAnimation(final_dip)
        if self._skip_expand:
            final_dip.finished.connect(self._on_dwell_complete)
        else:
            expand = self._make_expand_transition()
            if self._launch_on_scale_complete:
                self._expand_scale_anim.finished.connect(self._on_dwell_complete)
            else:
                expand.finished.connect(self._on_dwell_complete)
            group.addAnimation(expand)
        return group

    def _make_breath_dip(self) -> QPropertyAnimation:
        return make_property_animation(
            self,
            b"scale",
            self.hover_scale,
            self.pulse_dip_scale,
            self.breath_dip_ms,
            self.breath_dip_curve,
            self,
        )

    def _make_breath_return(self) -> QPropertyAnimation:
        return make_property_animation(
            self,
            b"scale",
            self.pulse_dip_scale,
            self.hover_scale,
            self.breath_return_ms,
            self.breath_return_curve,
            self,
        )

    def _make_final_dip(self) -> QPropertyAnimation:
        return make_property_animation(
            self,
            b"scale",
            self.hover_scale,
            self.pulse_dip_scale,
            self.final_dip_ms,
            self.final_dip_curve,
            self,
        )

    def _make_expand_transition(self) -> QParallelAnimationGroup:
        group = QParallelAnimationGroup(self)
        group.stateChanged.connect(self._on_expand_transition_state)

        self._expand_scale_anim = make_property_animation(
            self,
            b"scale",
            self.pulse_dip_scale,
            self.expand_max_scale,
            self.expand_ms,
            self.expand_curve,
            self,
        )
        group.addAnimation(self._expand_scale_anim)
        group.addAnimation(
            make_property_animation(
                self,
                b"morph",
                0.0,
                1.0,
                self.expand_ms,
                self.expand_curve,
                self,
            )
        )
        return group

    def _on_expand_transition_state(self, state: QAbstractAnimation.State) -> None:
        if state == QAbstractAnimation.State.Running:
            self._begin_expand()

    def _begin_expand(self) -> None:
        if self._expanding:
            return
        self._expanding = True
        self._scale = self.pulse_dip_scale
        self._morph = 0.0
        self.update()

    def _reset_expand_state(self) -> None:
        self._expanding = False
        self._morph = 0.0
        self._scale = self.base_scale
        self._halo_active = False
        self._halo_scale = self.halo_max_scale
        self.update()

    def _rearm_after_dwell(self) -> None:
        """Return a latched generic icon to rest and make it clickable again."""
        self._reset_expand_state()
        self._dwell_launched = False
        self._hidden_for_rearm = False

    def _begin_rearm_reveal(self) -> None:
        """Bring a hidden post-dwell icon back: show it at rest fully black,
        then fade it in (morph 1 -> 0) and clear the latch."""
        if self._overlay_parent is not None:
            return
        self._stop_all_animations()
        self._scale = self.base_scale
        self._morph = 1.0
        self._expanding = True
        self._halo_active = False
        self._halo_scale = self.halo_max_scale
        self.show()
        self._animate_reset_to_base(self._rearm_after_dwell)

    def _on_initial_grow_finished(self) -> None:
        self._halo_active = True
        self._halo_scale = self.halo_max_scale
        self.update()

    def _on_dwell_complete(self) -> None:
        if self._dwell_launched:
            return
        # Latch NOW, not in _finish_launch: the blackout overlay appearing
        # under the cursor sends this widget a synthetic Leave, and an
        # unlatched leaveEvent would run the reset path — scaling the icon
        # back down and raise_()-ing it above the blackout mid-sweep.
        self._dwell_launched = True
        self._stop_all_animations()
        if (
            self._blackout_ms > 0
            and self._overlay_parent is not None
            and self.enable_click
        ):
            self._start_launch_blackout()
        else:
            self._finish_launch()

    def _start_launch_blackout(self) -> None:
        parent = self._overlay_parent
        if parent is None:
            self._finish_launch()
            return

        width = self._screen_width or parent.width()
        height = self._screen_height or parent.height()
        icon_global = self.mapToGlobal(
            QPoint(int(self._icon_center_x()), int(self._icon_center_y()))
        )
        origin = QPointF(parent.mapFromGlobal(icon_global))
        start_radius = max((self.size / 2) * self._scale, MIN_BLACKOUT_START_RADIUS)

        # Each sibling icon hides whole once the circle's edge reaches its near
        # side (distance to its center minus its own radius).
        occlusion_targets = []
        if self._occlusion_icons_provider is not None:
            for other in self._occlusion_icons_provider():
                if other is self or not other.isVisible():
                    continue
                center_global = other.mapToGlobal(
                    QPoint(other.width() // 2, other.height() // 2)
                )
                center = QPointF(parent.mapFromGlobal(center_global))
                dist = math.hypot(center.x() - origin.x(), center.y() - origin.y())
                other_radius = getattr(other, "size", other.width()) / 2.0
                occlusion_targets.append((other, max(0.0, dist - other_radius)))

        self.raise_()
        self._blackout_overlay = LaunchBlackoutOverlay(
            parent,
            origin,
            width,
            height,
            start_radius,
            self._blackout_ms,
            self.blackout_curve,
            self._finish_launch,
            occlusion_targets,
            hold_ms=self._blackout_hold_ms,
        )
        if hasattr(parent, "add"):
            parent.add(self._blackout_overlay, 0, 0)
        self._blackout_overlay.raise_()
        self._blackout_overlay.start()

    def _finish_launch(self) -> None:
        # Already latched (_dwell_launched) since _on_dwell_complete, so a
        # lingering gaze can't re-trigger and leave events can't reset the
        # completed state.
        if self._blackout_overlay is not None:
            self._blackout_overlay = None
        if self._overlay_parent is not None:
            # Launch context (e.g. the app launcher): stay latched until the
            # owner rebuilds the icon.
            self.clicked.emit()
            return
        # Generic icon: it's fully black already (invisible on the waveguide);
        # hide the widget so it's gone on the simulator too, stay gone for a
        # beat, then quietly fade back in at rest and re-arm (_rearm_timer).
        log.info("Dwell click triggered.")
        self.clicked.emit()
        self._hidden_for_rearm = True
        self.hide()
        self._rearm_timer.start(self._rearm_delay_ms)

    def _stop_all_animations(self) -> None:
        self._hover_sequence.stop()
        self._reset_scale_anim.stop()
        self._reset_morph_anim.stop()
        self._reset_halo_scale_anim.stop()

    def _animate_reset_to_base(
        self, on_done: Optional[Callable[[], None]] = None
    ) -> None:
        configure_property_animation(
            self._reset_scale_anim,
            self._scale,
            self.base_scale,
            self.reset_ms,
            self.reset_curve,
        )

        if self._expanding:
            configure_property_animation(
                self._reset_morph_anim,
                self._morph,
                0.0,
                self.reset_ms,
                self.reset_curve,
            )
            self._reset_morph_anim.start()

        halo_was_active = self._halo_active and not self._expanding
        if halo_was_active:
            configure_property_animation(
                self._reset_halo_scale_anim,
                self._halo_scale,
                1.0,
                self.reset_ms,
                self.reset_curve,
            )
            self._reset_halo_scale_anim.start()

        def _on_reset_scale_finished() -> None:
            self._reset_scale_anim.finished.disconnect(_on_reset_scale_finished)
            if halo_was_active:
                self._halo_active = False
                self._halo_scale = self.halo_max_scale
            if on_done is not None:
                on_done()

        self._reset_scale_anim.finished.connect(_on_reset_scale_finished)
        self._reset_scale_anim.start()

    # ------------------------------------------------------------------
    # Animatable properties
    # ------------------------------------------------------------------

    def get_scale(self) -> float:
        return self._scale

    def set_scale(self, value: float) -> None:
        self._scale = float(value)
        if (
            not self._dwell_launched  # never climb above the blackout
            and value > self.base_scale + SCALE_THRESHOLD
        ):
            self.raise_()
        self.update()

    scale = Property(float, get_scale, set_scale)

    def get_morph(self) -> float:
        return self._morph

    def set_morph(self, value: float) -> None:
        self._morph = value
        self.update()

    morph = Property(float, get_morph, set_morph)

    def get_halo_scale(self) -> float:
        return self._halo_scale

    def set_halo_scale(self, value: float) -> None:
        self._halo_scale = value
        self.update()

    halo_scale = Property(float, get_halo_scale, set_halo_scale)

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:
        """
        Paint the icon widget.

        Handles rendering of the icon background, halo/outline, center text,
        and optional bottom text.

        Args:
            event: Paint event from Qt.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self._paint_pulse(painter)

    def _paint_pulse(self, painter: QPainter) -> None:
        if self.disabled:
            painter.setOpacity(0.5)

        if self._expanding or self._morph > 0:
            painter.save()
            self._paint_expand(painter)
            painter.restore()
            if self.bottom_text and self._bottom_font and self._morph < 1.0:
                painter.setClipping(False)
                painter.setPen(self.text_color)
                painter.setFont(self._bottom_font)
                base_opacity = 0.5 if self.disabled else 1.0
                painter.setOpacity(base_opacity * (1.0 - self._morph))
                self._draw_pulse_bottom_text(painter)
            return

        center_x = self._icon_center_x()
        center_y = self._icon_center_y()

        if self._halo_active:
            self._paint_halo(painter, center_x, center_y)

        painter.save()
        painter.translate(center_x, center_y)
        painter.scale(self._scale, self._scale)
        self._draw_icon(painter)
        if not self.enable_click:
            painter.setPen(QPen(self.outline_color, self.outline_width))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self._icon_clip_path())
        painter.restore()

        if self.bottom_text and self._bottom_font and self.bottom_text_visible:
            painter.setClipping(False)
            painter.setPen(self.text_color)
            painter.setFont(self._bottom_font)
            self._draw_pulse_bottom_text(painter)

    def _draw_pulse_bottom_text(self, painter: QPainter) -> None:
        """Draw wrapped bottom text below the icon (pulse type)."""
        processed_text = self.wrap_with_hyphenation(
            self.bottom_text, max_word_len=DEFAULT_MAX_WORD_LEN
        )
        text_y = self._label_top_y()
        painter.drawText(
            0,
            text_y,
            self.width(),
            self.height() - text_y,
            Qt.TextWordWrap | Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            processed_text,
        )

    def _paint_pulse_center_text(self, painter: QPainter) -> None:
        """Paint the center text at the icon center (pulse type). The painter
        is already translated to the icon center and scaled, so the text
        scales with the icon."""
        if not self.text:
            return
        painter.setClipping(False)
        painter.setPen(self.text_color)
        font = create_font(self.font, self.text_size, self.font_weight)
        painter.setFont(font)
        fm = QFontMetrics(font)
        painter.drawText(
            int(-fm.horizontalAdvance(self.text) / 2),
            int(fm.height() / 2 - fm.descent()),
            self.text,
        )

    # ------------------------------------------------------------------
    # Painting internals
    # ------------------------------------------------------------------

    def _icon_center_x(self) -> float:
        extra_width = DEFAULT_EXTRA_WIDTH if self.bottom_text else 0
        return self._scale_pad + (self.size + extra_width) / 2

    def _icon_center_y(self) -> float:
        if self.bottom_text:
            return self._scale_pad + self.size / 2
        # Center within the content area (widget height minus the pad above
        # and below it) — same visible position as before the height gained
        # its bottom pad.
        return self._scale_pad + (self.height() - 2 * self._scale_pad) / 2

    def _label_top_y(self) -> int:
        return self._scale_pad + self.size + self.bottom_text_spacing

    def _build_halo_border_gradient(self) -> Optional[QConicalGradient]:
        """Builds a conical gradient from the icon's own rim colors.

        Uses -sin, not +sin, for y — QConicalGradient sweeps opposite to
        plain cos/sin in y-down pixel space; +sin renders mirrored."""
        if self._pixmap is None or self._pixmap.isNull():
            return None

        image = self._pixmap.toImage()
        w, h = image.width(), image.height()
        cx, cy = w / 2.0, h / 2.0
        sample_radius = max(
            1.0, self.size / 2.0 - self.halo_border_sample_band_px / 2.0
        )

        gradient = QConicalGradient(0.0, 0.0, 0.0)
        n = self.halo_border_samples
        for i in range(n + 1):  # +1 closes the loop back to the same color at 1.0
            frac = i / n
            angle = 2.0 * math.pi * frac
            x = max(0, min(w - 1, int(round(cx + sample_radius * math.cos(angle)))))
            y = max(0, min(h - 1, int(round(cy - sample_radius * math.sin(angle)))))
            gradient.setColorAt(frac, image.pixelColor(x, y))
        return gradient

    def _paint_halo(self, painter: QPainter, center_x: float, center_y: float) -> None:
        """Backdrop circle sized to halo_scale; peeks out when the icon is smaller."""
        radius = (self.size / 2) * self._halo_scale
        brush = (
            QBrush(self._halo_border_gradient)
            if self._halo_border_gradient is not None
            else QBrush(self.halo_color)
        )

        painter.save()
        painter.translate(center_x, center_y)
        painter.setPen(Qt.PenStyle.NoPen)

        painter.setOpacity(self.halo_fill_opacity)
        painter.setBrush(brush)
        painter.drawEllipse(QPointF(0.0, 0.0), radius, radius)

        half_blur = self.halo_blur_px / 2.0
        pen = QPen(brush, self.halo_border_width)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for i in range(self.halo_blur_steps):
            t = i / (self.halo_blur_steps - 1)
            r = radius - half_blur + t * self.halo_blur_px
            if r <= 0.0:
                continue
            if t <= 0.5:
                # ramp up: halo_fill_opacity (blends into the fill) ->
                # halo_border_peak_opacity
                eased = _smoothstep(t / 0.5)
                opacity = (
                    self.halo_fill_opacity
                    + (self.halo_border_peak_opacity - self.halo_fill_opacity) * eased
                )
            else:
                # ramp down: halo_border_peak_opacity -> fully transparent
                # (blends into background)
                eased = _smoothstep((t - 0.5) / 0.5)
                opacity = self.halo_border_peak_opacity * (1.0 - eased)
            painter.setOpacity(max(0.0, min(1.0, opacity)))
            painter.setPen(pen)
            painter.drawEllipse(QPointF(0.0, 0.0), r, r)
        painter.restore()

    def _draw_icon(self, painter: QPainter) -> None:
        """Draw the icon body (background shape, image, center text) with the
        painter already translated to the icon center and scaled (pulse type)."""
        path = self._icon_clip_path()
        half = self.size / 2

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.background_color)
        painter.drawPath(path)
        if self._pixmap:
            painter.setClipPath(path)
            painter.drawPixmap(-half, -half, self._pixmap)
        self._paint_pulse_center_text(painter)

    def _icon_clip_path(self) -> QPainterPath:
        half = self.size / 2
        rect = -half, -half, self.size, self.size
        path = QPainterPath()
        if self.is_square:
            path.addRoundedRect(*rect, self.corner_radius, self.corner_radius)
        else:
            path.addEllipse(*rect)
        return path

    def _paint_expand(self, painter: QPainter) -> None:
        center_x = self._icon_center_x()
        center_y = self._icon_center_y()
        painter.translate(center_x, center_y)
        painter.scale(self._scale, self._scale)

        clip_path = self._icon_clip_path()
        morph = min(1.0, max(0.0, self._morph))

        painter.save()
        painter.setClipPath(clip_path)
        painter.setOpacity(morph)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_BLACKOUT_QCOLOR)
        painter.drawPath(clip_path)
        painter.restore()

        if morph < 1.0:
            painter.save()
            painter.setClipPath(clip_path)
            painter.setOpacity(1.0 - morph)
            self._draw_icon(painter)
            painter.restore()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_text(self, new_text: str) -> None:
        """
        Update the center text and repaint the widget.

        Args:
            new_text (str): New text to display centered in the icon.
        """
        try:
            self.text = new_text
            self.update()
        except Exception as e:
            log.error(f"Failed to set text on Icon: {e}", exc_info=True)
            raise

    def on_clicked(self, callback: Callable[..., Any], *args, **kwargs) -> None:
        """
        Connect a callback function to the clicked signal, with optional arguments.

        Args:
            callback (Callable): Function to call when clicked.
            *args: Positional arguments to pass to the callback.
            **kwargs: Keyword arguments to pass to the callback.
        """
        self.clicked.connect(partial(callback, *args, **kwargs))

    def set_background_image(self, image_path: Optional[str]) -> None:
        """
        Dynamically set or update the background image of the icon.

        Args:
            image_path (str | None): Path to the new image file.
                                     Pass None to remove the image.
        """
        try:
            self._load_pulse_pixmap(image_path)
            self._halo_border_gradient = self._build_halo_border_gradient()
            self.update()
        except Exception as e:
            log.error(f"Error setting background image: {e}")

    def wrap_with_hyphenation(self, text: str, max_word_len: int = 8) -> str:
        """
        Insert hyphen breaks for words longer than max_word_len.

        Example: "incredible" -> "incredi-\nble"

        Args:
            text: Text to process.
            max_word_len: Maximum word length before hyphenation.

        Returns:
            Text with hyphenated long words.
        """
        words = text.split()
        wrapped_words = []

        for word in words:
            if len(word) > max_word_len:
                # break into chunks and add hyphens
                parts = [
                    word[i : i + max_word_len]
                    for i in range(0, len(word), max_word_len)
                ]
                hyphenated = "-\n".join(parts[:-1]) + (
                    "-\n" + parts[-1] if len(parts) > 1 else ""
                )
                wrapped_words.append(hyphenated)
            else:
                wrapped_words.append(word)

        return " ".join(wrapped_words)

    def set_interaction_enabled(self, enabled: bool) -> None:
        """Enable or disable hover, dwell, and click (e.g. while shell is asleep)."""
        if enabled:
            self.setEnabled(True)
            return

        self._stop_all_animations()
        if self._blackout_overlay is not None:
            self._blackout_overlay.deleteLater()
            self._blackout_overlay = None
        self._reset_expand_state()
        if self._overlay_parent is None:
            # Clear the post-dwell latch (and un-hide) so a generic icon
            # isn't stuck black or gone when re-enabled.
            self._rearm_timer.stop()
            if self._hidden_for_rearm:
                self.show()
            self._hidden_for_rearm = False
            self._dwell_launched = False
        self.setEnabled(False)

    def set_disabled(self, disabled: bool) -> None:
        """
        Enable or disable the icon.

        When disabled, the icon won't respond to clicks or hover events,
        and will be rendered with reduced opacity.

        Args:
            disabled (bool): True to disable the icon, False to enable it.
        """
        if self.disabled == disabled:
            return

        self.disabled = disabled

        if disabled:
            self._stop_all_animations()
            self._reset_expand_state()
            if self._overlay_parent is None:
                self._rearm_timer.stop()
                if self._hidden_for_rearm:
                    self.show()
                self._hidden_for_rearm = False
                self._dwell_launched = False
        self.update()

    def set_enabled(self, enabled: bool) -> None:
        """
        Enable or disable the icon (convenience method).

        Args:
            enabled (bool): True to enable the icon, False to disable it.
        """
        self.set_disabled(not enabled)

    def is_disabled(self) -> bool:
        """
        Check if the icon is currently disabled.

        Returns:
            bool: True if the icon is disabled, False otherwise.
        """
        return self.disabled
