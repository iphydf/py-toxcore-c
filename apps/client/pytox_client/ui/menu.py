# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""The menu: the profiles to switch between, a new one, and the settings."""
from __future__ import annotations

from typing import Callable

from kivy.metrics import dp
from kivy.metrics import sp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.widget import Widget

from pytox_client.model import ClientState
from pytox_client.model import SHORT_KEY
from pytox_client.profiles import Profiles
from pytox_client.ui.chat_list import UnreadBadge
from pytox_client.ui.formatting import self_connection_text
from pytox_client.ui.theme import ThemeColors
from pytox_client.ui.theme import with_alpha
from pytox_client.ui.widgets import AvatarWidget
from pytox_client.ui.widgets import ClickableBox
from pytox_client.ui.widgets import HairlineDivider
from pytox_client.ui.widgets import IconButton
from pytox_client.ui.widgets import set_bg_color

_WIDTH_DP = 300
_ROW_DP = 60


def _label(text: str, color: tuple[float, ...], size: float,
           bold: bool = False) -> Label:
    label = Label(text=text, color=color, font_size=sp(size), bold=bold,
                  halign="left", valign="middle", shorten=True,
                  shorten_from="right")
    label.bind(size=lambda i, s: setattr(i, "text_size", s))
    return label


def _row(theme: ThemeColors, selected: bool,
         on_press: Callable[[], None]) -> ClickableBox:
    return ClickableBox(
        on_press_cb=on_press,
        bg=with_alpha(theme.primary, 0.14) if selected else (0, 0, 0, 0),
        pressed_bg=with_alpha(theme.on_surface, 0.08),
        radius=[dp(28)],
        orientation="horizontal",
        size_hint=(1, None),
        height=dp(_ROW_DP),
        padding=(dp(12), dp(6), dp(16), dp(6)),
        spacing=dp(12),
    )


def show_menu(
    profiles: Profiles,
    theme: ThemeColors,
    insets: tuple[int, int, int, int],
    on_show: Callable[[str], None],
    on_add: Callable[[], None],
    on_settings: Callable[[], None],
) -> ModalView:
    """Opens the menu on the left of the window; a choice closes it.

    ``insets`` are the system bars' (left, top, right, bottom), kept clear.
    """
    view = ModalView(
        size_hint=(None, 1), width=dp(_WIDTH_DP),
        pos_hint={"x": 0, "y": 0},
        background_color=(0, 0, 0, 0),
        overlay_color=with_alpha((0, 0, 0, 1), 0.32),
    )
    left, top, _right, bottom = insets
    sheet = BoxLayout(orientation="vertical", spacing=dp(4),
                      padding=(left + dp(12), top + dp(12), dp(12),
                               bottom + dp(12)))
    set_bg_color(sheet, theme.surface)

    def choose(action: Callable[[], None]) -> Callable[[], None]:
        def chosen() -> None:
            view.dismiss(animation=False)
            action()
        return chosen

    def show(name: str) -> Callable[[], None]:
        return choose(lambda: on_show(name))

    heading = _label("Profiles", theme.on_surface_variant, 13, bold=True)
    heading.size_hint_y = None
    heading.height = dp(32)
    sheet.add_widget(heading)
    shown = profiles.shown
    for name in profiles.names:
        client = profiles.client(name)
        if client is None:
            continue
        profile = client.state.profile
        unread = _unread(client.state)
        row = _row(theme, name == shown, show(name))
        avatar = AnchorLayout(size_hint=(None, 1), width=dp(40))
        avatar.add_widget(AvatarWidget(
            key_hex=profile.address, name=profile.name or "Me", theme=theme,
            size_dp=36, connection=profile.connection, status=profile.status,
            picture=profile.avatar))
        row.add_widget(avatar)
        text = BoxLayout(orientation="vertical")
        text.add_widget(_label(
            profile.name or profile.address[:SHORT_KEY] or "New profile",
            theme.on_surface, 15))
        text.add_widget(_label(self_connection_text(profile.connection),
                               theme.on_surface_variant, 12))
        row.add_widget(text)
        if unread > 0:
            badge = AnchorLayout(size_hint=(None, 1), width=dp(32))
            badge.add_widget(UnreadBadge(unread, theme))
            row.add_widget(badge)
        sheet.add_widget(row)

    sheet.add_widget(_action(theme, "add", "Add a profile", choose(on_add)))
    sheet.add_widget(HairlineDivider(theme.outline_variant))
    sheet.add_widget(_action(theme, "settings", "Settings",
                             choose(on_settings)))
    sheet.add_widget(Widget())
    view.add_widget(sheet)
    view.open(animation=False)
    return view


def _action(theme: ThemeColors, icon: str, text: str,
            on_press: Callable[[], None]) -> ClickableBox:
    row = _row(theme, False, on_press)
    row.height = dp(52)
    glyph = AnchorLayout(size_hint=(None, 1), width=dp(40))
    glyph.add_widget(IconButton(icon, fg=theme.on_surface_variant,
                                size_dp=36, icon_dp=20,
                                on_click=on_press))
    row.add_widget(glyph)
    row.add_widget(_label(text, theme.on_surface, 15))
    return row


def _unread(state: ClientState) -> int:
    return (sum(f.unread for f in state.friends)
            + sum(g.unread for g in state.groups))
