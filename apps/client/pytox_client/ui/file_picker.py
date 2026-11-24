# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""Fallback Kivy file chooser modal for environments without native dialogs."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from kivy.metrics import dp
from kivy.metrics import sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.widget import Widget

from pytox_client.model import PickedFile
from pytox_client.model import from_path
from pytox_client.ui.theme import ThemeColors
from pytox_client.ui.widgets import PillButton
from pytox_client.ui.widgets import RoundedBox


_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")


def _is_image_file(_folder: str, filename: str) -> bool:
    return filename.lower().endswith(_IMAGE_EXTS)


def _initial_dir() -> str:
    try:
        return str(Path.home())
    except (OSError, RuntimeError):
        try:
            return str(Path.cwd())
        except OSError:
            return "."


def show_file_picker(
    images: bool,
    theme: ThemeColors,
    on_picked: Callable[[PickedFile], None],
) -> ModalView:
    """Open an in-app Kivy file picker modal."""
    modal = ModalView(
        size_hint=(0.86, 0.8),
        background="",
        background_color=(0, 0, 0, 0),
        overlay_color=(0, 0, 0, 0.55),
    )
    card = RoundedBox(
        bg=theme.surface_container,
        radius=[dp(18)],
        orientation="vertical",
        padding=(dp(18), dp(16), dp(18), dp(16)),
        spacing=dp(10),
    )
    title = Label(
        text="Choose a picture" if images else "Send a file",
        color=theme.on_surface,
        font_size=sp(17),
        bold=True,
        halign="left",
        valign="middle",
        size_hint=(1, None),
        height=dp(28),
    )
    title.bind(width=lambda i, w: setattr(i, "text_size", (w, None)))
    card.add_widget(title)

    filters: list[object] = [_is_image_file] if images else ["*"]
    chooser = FileChooserListView(
        path=_initial_dir(),
        filters=filters,
        size_hint=(1, 1),
    )
    # Kivy's default FileChooserListView draws white entry labels regardless
    # of app theme; put it on a dark surface so entries stay readable in light mode.
    chooser_box = RoundedBox(
        bg=(0.13, 0.14, 0.17, 1.0),
        radius=[dp(10)],
        padding=(dp(6), dp(6), dp(6), dp(6)),
        size_hint=(1, 1),
    )
    chooser_box.add_widget(chooser)
    card.add_widget(chooser_box)

    picked_once = False

    def _confirm() -> None:
        nonlocal picked_once
        if picked_once or not chooser.selection:
            return
        selected = Path(chooser.selection[0])
        try:
            is_file = selected.is_file()
        except OSError:
            is_file = False
        if is_file:
            picked_once = True
            modal.dismiss()
            on_picked(from_path(selected))

    chooser.bind(on_submit=lambda *_: _confirm())

    bar = BoxLayout(
        orientation="horizontal",
        size_hint=(1, None),
        height=dp(40),
        spacing=dp(8),
    )
    bar.add_widget(Widget())
    bar.add_widget(
        PillButton(
            text="Cancel",
            bg=(0, 0, 0, 0),
            fg=theme.on_surface_variant,
            on_click=modal.dismiss,
            height_dp=36,
        )
    )
    bar.add_widget(
        PillButton(
            text="Choose",
            bg=theme.primary,
            fg=theme.on_primary,
            on_click=_confirm,
            height_dp=36,
        )
    )
    card.add_widget(bar)
    modal.add_widget(card)
    modal.open()
    return modal
