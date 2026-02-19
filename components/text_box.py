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
Text box widget for Raven Framework.

This module provides a customizable text display widget with support for
custom fonts, colors, alignment, and word wrapping.
"""

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget

from ..helpers.font_utils import create_font
from ..helpers.logger import get_logger
from ..helpers.themes import RAVEN_CORE
from ..helpers.utils_light import css_color

theme = RAVEN_CORE

log = get_logger("TextBox")


class TextBox(QLabel):
    """
    QLabel subclass with customizable font, color, alignment, word wrap, and optional fixed width.

    Args:
        text (str): Initial text content. Defaults to "".
        parent (Optional[QWidget]): Optional parent widget. Defaults to None.
        font_type (Optional[str]): Font type from theme, one of 'display', 'title', 'headline', 'body', or 'small'.
                                  If provided, automatically sets text_color, font, font_size, and font_weight from theme.
                                  Defaults to None (uses body font as default).
        text_color (str): CSS color string or QColor-compatible color for text. Defaults to theme.fonts.body.color.
        font (str): Font family ('libre_franklin'). Defaults to theme.fonts.body.family.
        font_size (int): Font size in pixels. Defaults to theme.fonts.body.size.
        font_weight (str): Font weight, one of 'light', 'normal', 'medium', 'bold', or 'black'. Defaults to theme.fonts.body.weight.
        alignment (str): Text alignment, one of 'left', 'center', or 'right'. Defaults to 'left'.
        wrap_words (bool): Whether to enable word wrapping. Defaults to True.
        width (Optional[int]): Optional fixed width in pixels. Defaults to None.
        height (Optional[int]): Optional fixed height in pixels. Defaults to None.

    Raises:
        ValueError: If font_type is invalid, font_size is not positive, font_weight is invalid, alignment is invalid,
                    or width/height are not positive when provided.
        Exception: May raise exceptions from underlying operations (create_font, css_color, etc.).
    """

    def __init__(
        self,
        text: str = "",
        parent: Optional[QWidget] = None,
        *,
        font_type: Optional[str] = None,
        text_color: str = theme.fonts.body.color,
        font: str = theme.fonts.body.family,
        font_size: int = theme.fonts.body.size,
        font_weight: str = theme.fonts.body.weight,
        alignment: str = "left",
        wrap_words: bool = True,
        width: Optional[int] = None,
        height: Optional[int] = None,
    ) -> None:
        """
        Initialize the TextBox widget.

        See class docstring for parameter descriptions.

        Raises:
            ValueError: If font_type is invalid, font_size is not positive, font_weight is invalid, alignment is invalid,
                        or width/height are not positive when provided.
            Exception: May raise exceptions from underlying operations (create_font, css_color, etc.).
        """
        try:
            super().__init__(text, parent)

            if font_type is not None:
                valid_font_types = ["display", "title", "headline", "body", "small"]
                if font_type not in valid_font_types:
                    raise ValueError(
                        f"Invalid font_type '{font_type}'. Must be one of: {', '.join(valid_font_types)}"
                    )
                theme_font = getattr(theme.fonts, font_type)
                if text_color == theme.fonts.body.color:
                    text_color = theme_font.color
                if font == theme.fonts.body.family:
                    font = theme_font.family
                if font_size == theme.fonts.body.size:
                    font_size = theme_font.size
                if font_weight == theme.fonts.body.weight:
                    font_weight = theme_font.weight

            self.setAttribute(Qt.WA_TranslucentBackground, True)
            self.setStyleSheet(
                f"""
                color: {css_color(text_color)};
                background-color: transparent;
            """
            )

            font_obj = create_font(font, font_size, font_weight)
            self.setFont(font_obj)

            align_map = {
                "left": Qt.AlignLeft,
                "center": Qt.AlignCenter,
                "right": Qt.AlignRight,
            }
            align_value = align_map.get(alignment.lower(), Qt.AlignLeft)
            self.setAlignment(align_value)

            self.setWordWrap(bool(wrap_words))

            if width is not None:
                self.setFixedWidth(int(width))
            if height is not None:
                self.setFixedHeight(int(height))
            self.adjustSize()
        except Exception as e:
            log.error(f"Error initializing TextBox: {e}", exc_info=True)
            raise

    def set_text(self, new_text: str) -> None:
        """
        Update the label's text.

        Args:
            new_text (str): The new text to display.

        Raises:
            Exception: May raise exceptions from underlying Qt operations.
        """
        try:
            self.setText(new_text)
            self.adjustSize()

        except Exception as e:
            log.error(f"Failed to set text on TextBox: {e}", exc_info=True)
            raise
