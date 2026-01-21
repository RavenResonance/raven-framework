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
Card components for Raven Framework.

This module provides reusable card components with various layouts and button configurations.
"""

from typing import Callable, List, Optional, Tuple, Union

from PySide6.QtWidgets import QWidget

from ..helpers.themes import RAVEN_CORE
from .button import Button
from .container import Container
from .horizontal_container import HorizontalContainer
from .media_viewer import MediaViewer
from .scroll_view import ScrollView
from .spacer import Spacer
from .text_box import TextBox
from .vertical_container import VerticalContainer

theme = RAVEN_CORE


class TextCardWithButton(Container):
    """
    Card with text content and a single button.

    Args:
        text: Text content to display. Defaults to placeholder text.
        container_width: Width of the card container. Defaults to 400.
        left_margin: Left margin. Defaults to 30.
        right_margin: Right margin. Defaults to 30.
        top_margin: Top margin. Defaults to 50.
        bottom_margin: Bottom margin. Defaults to 50.
        button_text: Text for the button. Defaults to "Click Me".
        on_button_click: Optional callback function for button click.
        text_alignment: Text alignment. Defaults to "left".
        text_font_size: Font size for the text. Defaults to theme.fonts.body.size.
    """

    def __init__(
        self,
        text: str = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
        container_width: int = 400,
        left_margin: int = 30,
        right_margin: int = 30,
        top_margin: int = 50,
        bottom_margin: int = 50,
        button_text: str = "Click Me",
        on_button_click: Optional[Callable] = None,
        text_alignment: str = "left",
        text_font_size: Optional[int] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent, width=container_width)

        main_container = VerticalContainer(
            width=container_width,
            is_main_container=True,
            inner_margin=(left_margin, top_margin, right_margin, bottom_margin),
            spacing=10,
        )
        text_box_kwargs = {
            "text": text,
            "width": container_width - (left_margin + right_margin),
            "alignment": text_alignment,
        }
        if text_font_size is not None:
            text_box_kwargs["font_size"] = text_font_size
        self.text_box = TextBox(**text_box_kwargs)
        main_container.add(self.text_box)

        self.button = Button(center_text=button_text)
        if on_button_click:
            self.button.on_clicked(on_button_click)

        self.add(main_container)
        self.add(
            self.button,
            (container_width / 2) - (self.button.width() / 2),
            main_container.height() - (self.button.height() / 3),
        )


class TextCardWithTwoButtons(Container):
    """
    Card with text content and two buttons.

    Args:
        text: Text content to display. Defaults to placeholder text.
        container_width: Width of the card container. Defaults to 450.
        left_margin: Left margin. Defaults to 30.
        right_margin: Right margin. Defaults to 30.
        top_margin: Top margin. Defaults to 50.
        bottom_margin: Bottom margin. Defaults to 50.
        button_spacing: Spacing between buttons. Defaults to 20.
        button_text_1: Text for the first button. Defaults to "Cancel".
        button_text_2: Text for the second button. Defaults to "Confirm".
        on_button_1_click: Optional callback function for first button click.
        on_button_2_click: Optional callback function for second button click.
        text_alignment: Text alignment. Defaults to "left".
        text_font_size: Font size for the text. Defaults to theme.fonts.body.size.
    """

    def __init__(
        self,
        text: str = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
        container_width: int = 500,
        left_margin: int = 30,
        right_margin: int = 30,
        top_margin: int = 50,
        bottom_margin: int = 50,
        button_spacing: int = 20,
        button_text_1: str = "Cancel",
        button_text_2: str = "Confirm",
        on_button_1_click: Optional[Callable] = None,
        on_button_2_click: Optional[Callable] = None,
        text_alignment: str = "left",
        text_font_size: Optional[int] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent, width=container_width)

        main_container = VerticalContainer(
            width=container_width,
            is_main_container=True,
            inner_margin=(left_margin, top_margin, right_margin, bottom_margin),
            spacing=10,
        )
        text_box_kwargs = {
            "text": text,
            "width": container_width - (left_margin + right_margin),
            "alignment": text_alignment,
        }
        if text_font_size is not None:
            text_box_kwargs["font_size"] = text_font_size
        self.text_box = TextBox(**text_box_kwargs)
        main_container.add(self.text_box)

        button1 = Button(center_text=button_text_1)
        button2 = Button(center_text=button_text_2)

        if on_button_1_click:
            button1.on_clicked(on_button_1_click)
        if on_button_2_click:
            button2.on_clicked(on_button_2_click)

        # Calculate total width of both buttons plus spacing
        total_buttons_width = button1.width() + button2.width() + button_spacing
        # Calculate starting x position to center both buttons
        start_x = (container_width / 2) - (total_buttons_width / 2)

        self.add(main_container)
        self.add(button1, start_x, main_container.height() - (button1.height() / 3))
        self.add(
            button2,
            start_x + button1.width() + button_spacing,
            main_container.height() - (button2.height() / 3),
        )


class HorizontalTextCardWithButton(Container):
    """
    Horizontal card with text and a button.

    Args:
        text: Text content to display. Defaults to placeholder text.
        container_width: Width of the card container. Defaults to 640.
        left_margin: Left margin. Defaults to 30.
        right_margin: Right margin. Defaults to 30.
        top_margin: Top margin. Defaults to 50.
        bottom_margin: Bottom margin. Defaults to 50.
        center_space: Spacing between text and button. Defaults to 30.
        button_text: Text for the button. Defaults to "Turn on Airplay".
        on_button_click: Optional callback function for button click.
        text_alignment: Text alignment. Defaults to "left".
        text_font_size: Font size for the text. Defaults to theme.fonts.body.size.
    """

    def __init__(
        self,
        text: str = "This is a horizontal card with text and a button. You can customize this as needed.",
        container_width: int = 640,
        left_margin: int = 30,
        right_margin: int = 30,
        top_margin: int = 50,
        bottom_margin: int = 50,
        center_space: int = 30,
        button_text: str = "Click Me",
        on_button_click: Optional[Callable] = None,
        text_alignment: str = "left",
        text_font_size: Optional[int] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent, width=container_width)

        main_container = HorizontalContainer(
            width=container_width,
            is_main_container=True,
            inner_margin=(left_margin, top_margin, right_margin, bottom_margin),
            spacing=10,
        )

        button = Button(center_text=button_text)
        if on_button_click:
            button.on_clicked(on_button_click)

        text_box_kwargs = {
            "text": text,
            "width": container_width
            - (left_margin + right_margin)
            - center_space
            - button.width(),
            "alignment": text_alignment,
        }
        if text_font_size is not None:
            text_box_kwargs["font_size"] = text_font_size
        self.text_box = TextBox(**text_box_kwargs)
        main_container.add(self.text_box, Spacer(width=center_space), button)

        self.add(main_container)


class HorizontalTextCard(Container):
    """
    Horizontal card with text only (no button).

    Args:
        text: Text content to display. Defaults to placeholder text.
        container_width: Width of the card container. Defaults to 640.
        left_margin: Left margin. Defaults to 30.
        right_margin: Right margin. Defaults to 30.
        top_margin: Top margin. Defaults to 50.
        bottom_margin: Bottom margin. Defaults to 50.
        text_alignment: Text alignment. Defaults to "left".
        text_font_size: Font size for the text. Defaults to theme.fonts.body.size.
    """

    def __init__(
        self,
        text: str = "This is a horizontal card with text only. You can customize the text content as needed.",
        container_width: int = 640,
        left_margin: int = 30,
        right_margin: int = 30,
        top_margin: int = 50,
        bottom_margin: int = 50,
        text_alignment: str = "left",
        text_font_size: Optional[int] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent, width=container_width)

        main_container = HorizontalContainer(
            width=container_width,
            is_main_container=True,
            inner_margin=(left_margin, top_margin, right_margin, bottom_margin),
            spacing=10,
        )
        text_box_kwargs = {
            "text": text,
            "width": container_width - (left_margin + right_margin),
            "alignment": text_alignment,
        }
        if text_font_size is not None:
            text_box_kwargs["font_size"] = text_font_size
        self.text_box = TextBox(**text_box_kwargs)
        main_container.add(self.text_box)

        self.add(main_container)


class MediaCard(Container):
    """
    Card with media viewer, title, subtitle, and body text (no button).

    Args:
        title_text: Title text. Defaults to placeholder.
        subtitle_text: Subtitle text. Defaults to placeholder.
        body_text: Body text. Defaults to placeholder.
        image_path: Path to the image. Defaults to empty string.
        image_height: Height of the image. Defaults to 100.
        container_width: Width of the card container. Defaults to 450.
        left_margin: Left margin. Defaults to 30.
        right_margin: Right margin. Defaults to 30.
        top_margin: Top margin. Defaults to 50.
        bottom_margin: Bottom margin. Defaults to 50.
        title_alignment: Title text alignment. Defaults to "left".
        title_font_size: Font size for title. Defaults to theme.fonts.title.size.
        subtitle_alignment: Subtitle text alignment. Defaults to "left".
        subtitle_font_size: Font size for subtitle. Defaults to theme.fonts.body.size.
        body_alignment: Body text alignment. Defaults to "left".
        body_font_size: Font size for body text. Defaults to theme.fonts.body.size.
    """

    def __init__(
        self,
        title_text: str = "Card Title",
        subtitle_text: str = "Card Subtitle",
        body_text: str = "This is the body text of the card. It can contain multiple lines of information.",
        image_path: str = "",
        image_height: int = 200,
        container_width: int = 450,
        left_margin: int = 30,
        right_margin: int = 30,
        top_margin: int = 50,
        bottom_margin: int = 50,
        title_alignment: str = "left",
        title_font_size: Optional[int] = None,
        subtitle_alignment: str = "left",
        subtitle_font_size: Optional[int] = None,
        body_alignment: str = "left",
        body_font_size: Optional[int] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent, width=container_width)

        main_container = VerticalContainer(
            width=container_width,
            is_main_container=True,
            inner_margin=(left_margin, top_margin, right_margin, bottom_margin),
            spacing=10,
        )

        title_box = TextBox(
            title_text,
            width=container_width - (left_margin + right_margin),
            font_size=(
                title_font_size
                if title_font_size is not None
                else theme.fonts.title.size
            ),
            font_weight=theme.fonts.title.weight,
            alignment=title_alignment,
        )
        subtitle_box = TextBox(
            subtitle_text,
            width=container_width - (left_margin + right_margin),
            font_size=(
                subtitle_font_size
                if subtitle_font_size is not None
                else theme.fonts.body.size
            ),
            font_weight=theme.fonts.title.weight,
            alignment=subtitle_alignment,
        )
        body_box = TextBox(
            body_text,
            width=container_width - (left_margin + right_margin),
            font_size=(
                body_font_size if body_font_size is not None else theme.fonts.body.size
            ),
            font_weight=theme.fonts.body.weight,
            alignment=body_alignment,
        )

        # Only add media viewer if image_path is provided
        if image_path:
            media_viewer = MediaViewer(
                media_path=image_path,
                width=container_width - (left_margin + right_margin),
                height=image_height,
            )
            main_container.add(media_viewer, title_box, subtitle_box, body_box)
        else:
            main_container.add(title_box, subtitle_box, body_box)

        self.add(main_container)


class MediaCardWithButton(Container):
    """
    Card with media viewer, title, subtitle, body text, and a single button.

    Args:
        title_text: Title text. Defaults to placeholder.
        subtitle_text: Subtitle text. Defaults to placeholder.
        body_text: Body text. Defaults to placeholder.
        button_text: Text for the button. Defaults to "Click Me".
        image_path: Path to the image. Defaults to empty string.
        image_height: Height of the image. Defaults to 100.
        container_width: Width of the card container. Defaults to 400.
        left_margin: Left margin. Defaults to 30.
        right_margin: Right margin. Defaults to 30.
        top_margin: Top margin. Defaults to 50.
        bottom_margin: Bottom margin. Defaults to 50.
        on_button_click: Optional callback function for button click.
        title_alignment: Title text alignment. Defaults to "left".
        title_font_size: Font size for title. Defaults to theme.fonts.title.size.
        subtitle_alignment: Subtitle text alignment. Defaults to "left".
        subtitle_font_size: Font size for subtitle. Defaults to theme.fonts.body.size.
        body_alignment: Body text alignment. Defaults to "left".
        body_font_size: Font size for body text. Defaults to theme.fonts.body.size.
    """

    def __init__(
        self,
        title_text: str = "Card Title",
        subtitle_text: str = "Card Subtitle",
        body_text: str = "This is the body text of the card. It can contain multiple lines of information.",
        button_text: str = "Click Me",
        image_path: str = "",
        image_height: int = 200,
        container_width: int = 400,
        left_margin: int = 30,
        right_margin: int = 30,
        top_margin: int = 50,
        bottom_margin: int = 50,
        on_button_click: Optional[Callable] = None,
        title_alignment: str = "left",
        title_font_size: Optional[int] = None,
        subtitle_alignment: str = "left",
        subtitle_font_size: Optional[int] = None,
        body_alignment: str = "left",
        body_font_size: Optional[int] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent, width=container_width)

        main_container = VerticalContainer(
            width=container_width,
            is_main_container=True,
            inner_margin=(left_margin, top_margin, right_margin, bottom_margin),
            spacing=10,
        )

        title_box = TextBox(
            title_text,
            width=container_width - (left_margin + right_margin),
            font_size=(
                title_font_size
                if title_font_size is not None
                else theme.fonts.title.size
            ),
            font_weight=theme.fonts.title.weight,
            alignment=title_alignment,
        )
        subtitle_box = TextBox(
            subtitle_text,
            width=container_width - (left_margin + right_margin),
            font_size=(
                subtitle_font_size
                if subtitle_font_size is not None
                else theme.fonts.body.size
            ),
            font_weight=theme.fonts.title.weight,
            alignment=subtitle_alignment,
        )
        body_box = TextBox(
            body_text,
            width=container_width - (left_margin + right_margin),
            font_size=(
                body_font_size if body_font_size is not None else theme.fonts.body.size
            ),
            font_weight=theme.fonts.body.weight,
            alignment=body_alignment,
        )

        # Only add media viewer if image_path is provided
        if image_path:
            media_viewer = MediaViewer(
                media_path=image_path,
                width=container_width - (left_margin + right_margin),
                height=image_height,
            )
            main_container.add(media_viewer, title_box, subtitle_box, body_box)
        else:
            main_container.add(title_box, subtitle_box, body_box)

        button = Button(center_text=button_text)
        if on_button_click:
            button.on_clicked(on_button_click)

        self.add(main_container)
        self.add(
            button,
            (container_width / 2) - (button.width() / 2),
            main_container.height() - (button.height() / 3),
        )


class MediaCardWithTwoButtons(Container):
    """
    Card with media viewer, title, subtitle, body text, and two buttons.

    Args:
        title_text: Title text. Defaults to placeholder.
        subtitle_text: Subtitle text. Defaults to placeholder.
        body_text: Body text. Defaults to placeholder.
        button_text_1: Text for the first button. Defaults to "Cancel".
        button_text_1: Text for the first button. Defaults to "Cancel".
        button_text_2: Text for the second button. Defaults to "Confirm".
        image_path: Path to the image. Defaults to empty string.
        image_height: Height of the image. Defaults to 100.
        container_width: Width of the card container. Defaults to 450.
        left_margin: Left margin. Defaults to 30.
        right_margin: Right margin. Defaults to 30.
        top_margin: Top margin. Defaults to 50.
        bottom_margin: Bottom margin. Defaults to 50.
        button_spacing: Spacing between buttons. Defaults to 20.
        on_button_1_click: Optional callback function for first button click.
        on_button_2_click: Optional callback function for second button click.
        title_alignment: Title text alignment. Defaults to "left".
        title_font_size: Font size for title. Defaults to theme.fonts.title.size.
        subtitle_alignment: Subtitle text alignment. Defaults to "left".
        subtitle_font_size: Font size for subtitle. Defaults to theme.fonts.body.size.
        body_alignment: Body text alignment. Defaults to "left".
        body_font_size: Font size for body text. Defaults to theme.fonts.body.size.
    """

    def __init__(
        self,
        title_text: str = "Card Title",
        subtitle_text: str = "Card Subtitle",
        body_text: str = "This is the body text of the card. It can contain multiple lines of information.",
        button_text_1: str = "Cancel",
        button_text_2: str = "Confirm",
        image_path: str = "",
        image_height: int = 200,
        container_width: int = 500,
        left_margin: int = 30,
        right_margin: int = 30,
        top_margin: int = 50,
        bottom_margin: int = 50,
        button_spacing: int = 20,
        on_button_1_click: Optional[Callable] = None,
        on_button_2_click: Optional[Callable] = None,
        title_alignment: str = "left",
        title_font_size: Optional[int] = None,
        subtitle_alignment: str = "left",
        subtitle_font_size: Optional[int] = None,
        body_alignment: str = "left",
        body_font_size: Optional[int] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent, width=container_width)

        main_container = VerticalContainer(
            width=container_width,
            is_main_container=True,
            inner_margin=(left_margin, top_margin, right_margin, bottom_margin),
            spacing=10,
        )

        title_box = TextBox(
            title_text,
            width=container_width - (left_margin + right_margin),
            font_size=(
                title_font_size
                if title_font_size is not None
                else theme.fonts.title.size
            ),
            font_weight=theme.fonts.title.weight,
            alignment=title_alignment,
        )
        subtitle_box = TextBox(
            subtitle_text,
            width=container_width - (left_margin + right_margin),
            font_size=(
                subtitle_font_size
                if subtitle_font_size is not None
                else theme.fonts.body.size
            ),
            font_weight=theme.fonts.title.weight,
            alignment=subtitle_alignment,
        )
        body_box = TextBox(
            body_text,
            width=container_width - (left_margin + right_margin),
            font_size=(
                body_font_size if body_font_size is not None else theme.fonts.body.size
            ),
            font_weight=theme.fonts.body.weight,
            alignment=body_alignment,
        )

        # Only add media viewer if image_path is provided
        if image_path:
            media_viewer = MediaViewer(
                media_path=image_path,
                width=container_width - (left_margin + right_margin),
                height=image_height,
            )
            main_container.add(media_viewer, title_box, subtitle_box, body_box)
        else:
            main_container.add(title_box, subtitle_box, body_box)

        button1 = Button(center_text=button_text_1)
        button2 = Button(center_text=button_text_2)

        if on_button_1_click:
            button1.on_clicked(on_button_1_click)
        if on_button_2_click:
            button2.on_clicked(on_button_2_click)

        # Calculate total width of both buttons plus spacing
        total_buttons_width = button1.width() + button2.width() + button_spacing
        # Calculate starting x position to center both buttons
        start_x = (container_width / 2) - (total_buttons_width / 2)

        self.add(main_container)
        self.add(button1, start_x, main_container.height() - (button1.height() / 3))
        self.add(
            button2,
            start_x + button1.width() + button_spacing,
            main_container.height() - (button2.height() / 3),
        )


class ScrollableListCard(Container):
    """
    Card with a scrollable list of items, each with a button.

    Args:
        title_text: Title text. Defaults to "Top News".
        info_strings: List of strings to display. Defaults to placeholder list.
        button_strings: List of button texts. Defaults to ["View"] for each item.
        card_width: Width of the card container. Defaults to 640.
        card_height: Height of the card container. Defaults to 640.
        left_margin: Left margin. Defaults to 30.
        right_margin: Right margin. Defaults to 30.
        top_margin: Top margin. Defaults to 40.
        bottom_margin: Bottom margin. Defaults to 40.
        vertical_spacing: Vertical spacing between title and list. Defaults to 10.
        on_item_click: Optional callback for item button clicks. Can be:
            - A single Callable that receives (index, item_text) as arguments
            - A list of tuples [(callback, *args), ...] where each tuple contains a callback and its arguments
              (e.g., [(self.view_painting, "Apple"), (self.view_painting, "Pear"), ...])
        title_alignment: Title text alignment. Defaults to "center".
        title_font_size: Font size for title. Defaults to theme.fonts.title.size.
        item_alignment: Item text alignment. Defaults to "left".
        item_font_size: Font size for item text. Defaults to theme.fonts.body.size.
    """

    def __init__(
        self,
        title_text: str = "My List",
        info_strings: Optional[List[str]] = None,
        button_strings: Optional[List[str]] = None,
        card_width: int = 640,
        card_height: int = 640,
        left_margin: int = 25,
        right_margin: int = 25,
        top_margin: int = 35,
        bottom_margin: int = 35,
        vertical_spacing: int = 5,
        on_item_click: Optional[Union[Callable, List[Tuple[Callable, ...]]]] = None,
        title_alignment: str = "center",
        title_font_size: Optional[int] = None,
        item_alignment: str = "left",
        item_font_size: Optional[int] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent, width=card_width, height=card_height)

        if info_strings is None:
            info_strings = [
                "Item 1",
                "Item 2",
                "Item 3",
                "Item 4",
                "Item 5",
                "Item 6",
                "Item 7",
                "Item 8",
                "Item 9",
                "Item 10",
                "Item 11",
                "Item 12",
                "Item 13",
            ]

        if button_strings is None:
            button_strings = ["View"] * len(info_strings)
        elif len(button_strings) != len(info_strings):
            # Pad or truncate button_strings to match info_strings length
            if len(button_strings) < len(info_strings):
                button_strings.extend(
                    ["View"] * (len(info_strings) - len(button_strings))
                )
            else:
                button_strings = button_strings[: len(info_strings)]

        main_container = VerticalContainer(
            width=card_width,
            is_main_container=True,
            inner_margin=(left_margin, top_margin, right_margin, bottom_margin),
            spacing=10,
        )

        # Title
        text = TextBox(
            title_text,
            font_size=(
                title_font_size
                if title_font_size is not None
                else theme.fonts.title.size
            ),
            font_weight="bold",
        )
        title_box = HorizontalContainer(
            width=card_width - (left_margin + right_margin),
            height=title_font_size,
            spacing=10,
        )
        title_box.add(Spacer(width=left_margin), text, Spacer(width=right_margin))

        # List with scroll view
        list_container = VerticalContainer(
            width=card_width - (left_margin + right_margin), spacing=10
        )
        for i in range(len(info_strings)):
            item_button = Button(
                center_text=info_strings[i],
                show_action_icon=True,
                width=list_container.width() - 100,
            )

            # Connect button click callback
            if on_item_click:
                if isinstance(on_item_click, list):
                    # on_item_click is a list of (callback, *args) tuples
                    if i < len(on_item_click):
                        callback_tuple = on_item_click[i]
                        if (
                            isinstance(callback_tuple, tuple)
                            and len(callback_tuple) > 0
                        ):
                            callback = callback_tuple[0]
                            args = callback_tuple[1:] if len(callback_tuple) > 1 else ()
                            item_button.on_clicked(callback, *args)
                else:
                    # on_item_click is a single Callable that receives (index, item_text)
                    # Use default arguments to capture loop variables correctly
                    item_button.on_clicked(
                        lambda idx=i, txt=info_strings[i]: on_item_click(idx, txt)
                    )

            list_container.add(item_button)

        scroll_container = ScrollView(
            content_widget=list_container,
            width=card_width - (left_margin + right_margin),
            height=card_height - (top_margin + bottom_margin) - 200,
        )
        main_container.add(title_box, Spacer(height=vertical_spacing), scroll_container)

        self.add(main_container)
