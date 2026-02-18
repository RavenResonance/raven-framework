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
Theme system for Raven Framework.

This module defines the theme structure and default theme instance (RAVEN_CORE)
for consistent styling across Raven Framework applications.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Palette:
    """
    Generic color palette with basic color tokens.

    Args:
        black (str): Black color hex code. Defaults to "#000000".
        transparent (str): Transparent color value. Defaults to "transparent".
        white (str): White color hex code. Defaults to "#FFFFFF".
        gray (str): Gray color hex code. Defaults to "#B4B4B4".
        light_gray (str): Light gray color hex code. Defaults to "#C8C8C8".
        blue (str): Blue color hex code. Defaults to "#0A84FF".
        red (str): Red color hex code. Defaults to "#FF453A".
        green (str): Green color hex code. Defaults to "#30D158".
        yellow (str): Yellow color hex code. Defaults to "#FFD60A".
    """

    black: str = "#000000"
    transparent: str = "transparent"
    white: str = "#FFFFFF"
    gray: str = "#B4B4B4"
    light_gray: str = "#C8C8C8"
    blue: str = "#0A84FF"
    red: str = "#FF453A"
    green: str = "#30D158"
    yellow: str = "#FFD60A"


@dataclass(frozen=True)
class FontSizes:
    """
    Generic font size palette with common font size tokens (in pixels).

    Args:
        display (int): Display font size in pixels. Defaults to 45.
        title (int): Title font size in pixels. Defaults to 38.
        headline (int): Headline font size in pixels. Defaults to 33.
        body (int): Body font size in pixels. Defaults to 28.
        small (int): Small font size in pixels. Defaults to 18.
    """

    display: int
    title: int
    headline: int
    body: int
    small: int


@dataclass(frozen=True)
class BrandColors:
    """
    Brand color scheme with primary, secondary, tertiary, and surface background colors.

    Args:
        primary (str): Primary color hex code (typically white for text).
        secondary (str): Secondary color hex code (for buttons).
        tertiary (str): Tertiary color hex code (for highlights/outlines).
        surface_background (str): Surface background color hex code.
    """

    primary: str
    secondary: str
    tertiary: str
    surface_background: str


@dataclass(frozen=True)
class Colors:
    """
    Theme color scheme with accent and UI colors.

    Args:
        accent (str): Accent color hex code (neon green).
        background_color (str): Background color hex code (Umbra Black). Defaults to "#0D0D0D".
        button_background_color (str): Button background color hex code (Umbra Black). Defaults to "#0D0D0D".
        button_background_dwell_fill_color (str): Button background dwell fill color hex code (Moon Silver). Defaults to "#DADDE5".
    """

    accent: str
    background_color: str
    button_background_color: str
    button_background_dwell_fill_color: str


@dataclass(frozen=True)
class Font:
    """
    Font configuration with size, weight, family, and color.

    Args:
        size (int): Font size in points.
        weight (str): Font weight ('light', 'normal', 'medium', 'bold', 'black').
        family (str): Font family ('libre_franklin').
        color (str): Font color hex code.
    """

    size: int
    weight: str
    family: str
    color: str


@dataclass(frozen=True)
class Fonts:
    """
    Collection of font configurations for different text styles.

    Args:
        display (Font): Display font configuration (largest, bold).
        title (Font): Title font configuration.
        headline (Font): Headline font configuration.
        body (Font): Body text font configuration.
        small (Font): Small text font configuration.
    """

    display: Font
    title: Font
    headline: Font
    body: Font
    small: Font


@dataclass(frozen=True)
class Borders:
    """
    Border configuration for UI elements.

    Args:
        corner_radius (int): Corner radius in pixels.
        width (int): Border width in pixels.
        color (str): Border color hex code.
        highlight_width (int): Highlight border width in pixels.
        highlight_color_icon (str): Primary highlight color hex code.
        highlight_color_button (str): Secondary highlight color hex code.
        highlight_quad_dwell_outline_color_button (str): Highlight background color hex code.
        use_gradient_border (bool): If True, renders border with gradient instead of solid color. Defaults to False.
        use_fill_dwell (bool): If True, uses fill dwell for buttons. Defaults to False.
        border_gradient_start_color (Optional[str]): Start color for gradient border as string. Defaults to None.
        border_gradient_end_color (Optional[str]): End color for gradient border as string. Defaults to None.
        border_gradient_direction (str): Gradient direction: 'horizontal', 'vertical', or 'diagonal'. Defaults to 'horizontal'.
    """

    corner_radius: int
    width: int
    color: str
    highlight_width: int
    highlight_color_icon: str
    highlight_color_button: str
    highlight_quad_dwell_outline_color_button: str
    use_gradient_border: bool = False
    use_fill_dwell: bool = False
    border_gradient_start_color: Optional[str] = None
    border_gradient_end_color: Optional[str] = None
    border_gradient_direction: str = "horizontal"


@dataclass(frozen=True)
class RavenTheme:
    """
    Unified theme configuration for Raven Framework.

    Args:
        brand_colors (BrandColors): Brand color scheme configuration.
        colors (Colors): Color scheme configuration.
        fonts (Fonts): Font configuration collection.
        borders (Borders): Border configuration.
        basic_palette (Palette): Basic color palette.
        font_sizes (FontSizes): Font size palette.
    """

    brand_colors: BrandColors
    colors: Colors
    fonts: Fonts
    borders: Borders
    basic_palette: Palette


color_pack = BrandColors(
    primary="#FFFFFF",  # White
    secondary="#DADDE5",  # Moon Silver (button bgs)
    tertiary="#D05BE8",  # Iridescent Pink (highlights/outlines)
    surface_background="#0D0D0D",  # Umbra Black
)

RAVEN_CORE = RavenTheme(
    basic_palette=Palette(),
    brand_colors=color_pack,
    colors=Colors(
        accent=color_pack.tertiary,
        background_color=color_pack.surface_background,
        button_background_color=(color_pack.surface_background),
        button_background_dwell_fill_color=color_pack.secondary,
    ),
    fonts=Fonts(
        display=Font(
            size=45,  # 1.33°
            weight="bold",
            family="inter",
            color=color_pack.primary,
        ),
        title=Font(
            size=38,  # 1.12°
            weight="bold",
            family="inter",
            color=color_pack.primary,
        ),
        headline=Font(
            size=33,  # 0.97°
            weight="bold",
            family="inter",
            color=color_pack.primary,
        ),
        body=Font(
            size=28,  # 0.83°
            weight="normal",
            family="inter",
            color=color_pack.primary,
        ),
        small=Font(
            size=18,  # 0.53°
            weight="normal",
            family="inter",
            color=color_pack.primary,
        ),
    ),
    borders=Borders(
        corner_radius=20,
        width=3,
        color=color_pack.primary,
        highlight_width=3,
        highlight_color_icon=color_pack.primary,
        highlight_color_button=color_pack.tertiary,
        highlight_quad_dwell_outline_color_button=color_pack.tertiary,
        use_gradient_border=True,
        use_fill_dwell=True,
        border_gradient_start_color=color_pack.primary,
        border_gradient_end_color=color_pack.secondary,
        border_gradient_direction="diagonal",
    ),
)
