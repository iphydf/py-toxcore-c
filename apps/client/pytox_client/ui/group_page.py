# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""Group (NGC) chat screen: sender-coloured bubbles, day headers, composer."""
from __future__ import annotations

import datetime
from functools import partial
from typing import Any
from typing import Optional

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.metrics import sp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.widget import Widget

from pytox_client.model import ClientState
from pytox_client.model import GroupMessage
from pytox_client.model import SHORT_KEY
from pytox_client.model import shown_text
from pytox_client.ui.chat_page import ComposerInput
from pytox_client.ui.formatting import DayItem
from pytox_client.ui.formatting import GroupBubbleItem
from pytox_client.ui.formatting import clock_time
from pytox_client.ui.formatting import day_heading
from pytox_client.ui.formatting import group_chat_items
from pytox_client.ui.formatting import group_subtitle
from pytox_client.ui.formatting import peer_rgba
from pytox_client.ui.navigator import GroupInfoRoute
from pytox_client.ui.navigator import Navigator
from pytox_client.ui.theme import RGBA
from pytox_client.ui.theme import ThemeColors
from pytox_client.ui.theme import with_alpha
from pytox_client.ui.widgets import ClickableBox
from pytox_client.ui.widgets import GroupAvatarWidget
from pytox_client.ui.widgets import HairlineDivider
from pytox_client.ui.widgets import HistoryView
from pytox_client.ui.widgets import IconButton
from pytox_client.ui.widgets import PillButton
from pytox_client.ui.widgets import RoundedBox
from pytox_client.ui.widgets import Row
from pytox_client.ui.widgets import SelectableText
from pytox_client.ui.widgets import TopBar
from pytox_client.ui.widgets import auto_label
from pytox_client.ui.widgets import set_bg_color

_BUBBLE_MAX_DP = 520.0


def _fit_label(
    text: str,
    color: RGBA,
    max_w: float,
    font_size_sp: float = 14.5,
    bold: bool = False,
    italic: bool = False,
) -> Label:
    """A label as wide as its text, wrapping at ``max_w``."""
    lbl = Label(
        text=text,
        color=color,
        font_size=sp(font_size_sp),
        bold=bold,
        italic=italic,
        halign="left",
        valign="top",
        size_hint=(None, None),
    )
    lbl.texture_update()
    width = min(lbl.texture_size[0], max_w)
    lbl.text_size = (width, None)
    lbl.texture_update()
    lbl.size = (width, lbl.texture_size[1])
    return lbl


class GroupPageView(BoxLayout):  # type: ignore[misc]
    """Single group chat pane: header, history, connection banner, composer."""

    def __init__(
        self,
        client: Any,
        navigator: Navigator,
        theme: ThemeColors,
        drafts: dict[str, str],
        desktop_enter_sends: bool = True,
    ) -> None:
        super().__init__(orientation="vertical")
        self._client = client
        self._navigator = navigator
        self._theme = theme
        self._drafts = drafts
        self._group_id = ""
        self._wide = False
        self._suppress_draft_event = False
        self._last_sig: Any = None
        self._first_id: Optional[int] = None
        self._loading_older = False
        self._state_cache: Optional[ClientState] = None
        self._width_bucket = 0
        self._resize_ev: Any = None

        set_bg_color(self, theme.surface)

        self._topbar = TopBar(theme)
        self._back_wrap = AnchorLayout(size_hint=(None, 1), width=dp(40))

        def _go_back() -> None:
            self._navigator.back()

        self._back_btn = IconButton(
            "back", fg=theme.on_surface_variant, on_click=_go_back,
            size_dp=40, icon_dp=20)
        self._back_wrap.add_widget(self._back_btn)

        self._title_btn = ClickableBox(
            on_press_cb=self._open_info,
            bg=(0, 0, 0, 0),
            pressed_bg=with_alpha(theme.on_surface, 0.08),
            radius=[dp(10)],
            orientation="horizontal",
            padding=(dp(4), dp(4), dp(8), dp(4)),
            spacing=dp(10),
            size_hint=(1, 1),
        )
        self._avatar = GroupAvatarWidget(group_id="", name="#", size_dp=38)
        av_wrap = AnchorLayout(size_hint=(None, 1), width=dp(40))
        av_wrap.add_widget(self._avatar)
        self._title_btn.add_widget(av_wrap)
        name_col = BoxLayout(
            orientation="vertical", size_hint=(1, 1),
            padding=(0, dp(3), 0, dp(3)))
        self._name_lbl = Label(
            text="", color=theme.on_surface, font_size=sp(15.5), bold=True,
            halign="left", valign="bottom", shorten=True,
            shorten_from="right")
        self._name_lbl.bind(size=lambda i, s: setattr(i, "text_size", s))
        self._sub_lbl = Label(
            text="", color=theme.on_surface_variant, font_size=sp(12),
            halign="left", valign="top", shorten=True, shorten_from="right")
        self._sub_lbl.bind(size=lambda i, s: setattr(i, "text_size", s))
        name_col.add_widget(self._name_lbl)
        name_col.add_widget(self._sub_lbl)
        self._title_btn.add_widget(name_col)

        self._info_btn = IconButton(
            "info", fg=theme.on_surface_variant, on_click=self._open_info,
            size_dp=40, icon_dp=20)
        info_wrap = AnchorLayout(size_hint=(None, 1), width=dp(42))
        info_wrap.add_widget(self._info_btn)
        self._topbar.row.add_widget(self._back_wrap)
        self._topbar.row.add_widget(self._title_btn)
        self._topbar.row.add_widget(info_wrap)
        self.add_widget(self._topbar)

        self._history = HistoryView(
            desktop=desktop_enter_sends, on_near_top=self._near_top)
        self._history.bind(width=self._on_width)
        self.add_widget(self._history)

        self._banner = auto_label(
            "", color=theme.on_surface_variant, font_size_sp=12.5)
        self._banner_box = BoxLayout(
            size_hint=(1, None), height=0,
            padding=(dp(14), dp(8), dp(14), dp(8)))
        self._banner_box.add_widget(self._banner)
        self._banner_box.opacity = 0.0
        self.add_widget(self._banner_box)

        self._composer_div = HairlineDivider(theme.outline_variant)
        self.add_widget(self._composer_div)
        self._composer_bar = BoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(60),
            padding=(dp(10), dp(8), dp(10), dp(8)),
            spacing=dp(8),
        )
        set_bg_color(self._composer_bar, theme.surface)
        self._input_box = RoundedBox(
            bg=theme.surface_container_low,
            radius=[dp(22)],
            border_color=theme.outline_variant,
            border_width=dp(1),
            size_hint=(1, 1),
            padding=(dp(14), dp(8), dp(14), dp(8)),
        )
        self._input = ComposerInput(
            on_send=self._send,
            desktop_enter_sends=desktop_enter_sends,
            hint_text="Message the group",
            multiline=True,
            background_normal="",
            background_active="",
            background_color=(0, 0, 0, 0),
            foreground_color=theme.on_surface,
            hint_text_color=theme.on_surface_variant,
            cursor_color=theme.primary,
            selection_color=with_alpha(theme.primary, 0.28),
            font_size=sp(14.5),
            padding=(0, dp(3), 0, dp(3)),
            write_tab=False,
        )
        self._input.bind(text=self._on_text_changed)
        self._input.bind(focus=self._on_input_focus)
        self._input_box.add_widget(self._input)
        self._composer_bar.add_widget(self._input_box)
        self._send_btn = IconButton(
            "send", fg=theme.on_primary, bg=theme.primary,
            size_dp=44, icon_dp=19, on_click=self._send)
        self._send_btn.disabled = True
        send_wrap = AnchorLayout(
            anchor_y="bottom", size_hint=(None, 1), width=dp(44))
        send_wrap.add_widget(self._send_btn)
        self._composer_bar.add_widget(send_wrap)
        self.add_widget(self._composer_bar)

    def close(self) -> None:
        if self._resize_ev is not None:
            self._resize_ev.cancel()
            self._resize_ev = None
        self._history.close()

    def _on_input_focus(self, _inst: Any, focused: bool) -> None:
        border = (self._theme.primary
                  if focused else self._theme.outline_variant)
        self._input_box.set_style(self._theme.surface_container_low, border)

    def _open_info(self) -> None:
        if self._group_id:
            self._navigator.push(GroupInfoRoute(self._group_id))

    def _on_text_changed(self, _inst: Any, value: str) -> None:
        if self._suppress_draft_event:
            return
        if self._group_id:
            self._drafts[f"group {self._group_id}"] = value
        self._send_btn.disabled = not value.strip()
        lines = min(5, max(1, value.count("\n") + 1))
        self._composer_bar.height = dp(60 + (lines - 1) * 20)

    def _send(self) -> None:
        text = self._input.text
        if not self._group_id or not text.strip():
            return
        action = text.startswith("/me ")
        body = text[4:] if action else text
        self._client.send_group_message(self._group_id, body, action=action)
        self._suppress_draft_event = True
        self._input.text = ""
        self._suppress_draft_event = False
        self._drafts[f"group {self._group_id}"] = ""
        self._composer_bar.height = dp(60)
        self._send_btn.disabled = True
        Clock.schedule_once(lambda _dt: setattr(self._input, "focus", True), 0)

    def _near_top(self) -> None:
        state = self._state_cache
        if state is None:
            return
        chat = state.group_chat
        if (chat is not None and chat.group == self._group_id
                and chat.has_older and not self._loading_older):
            self._loading_older = True
            self._client.load_older_group_messages()

    def _on_width(self, _inst: Any, width: float) -> None:
        bucket = int(width // dp(40))
        if bucket != self._width_bucket and self._state_cache is not None:
            self._width_bucket = bucket
            if self._resize_ev is not None:
                self._resize_ev.cancel()
            self._resize_ev = Clock.schedule_once(
                lambda _dt: self._reflow(), 0.05)

    def _reflow(self) -> None:
        self._resize_ev = None
        if self._state_cache is not None and self._group_id:
            self.update(
                self._group_id, self._state_cache, self._theme,
                self._wide, force=True)

    def update(
        self,
        group_id: str,
        state: ClientState,
        theme: ThemeColors,
        wide: bool,
        force: bool = False,
    ) -> None:
        self._state_cache = state
        theme_changed = theme != self._theme
        group_changed = group_id != self._group_id
        self._theme = theme
        self._wide = wide

        if group_changed:
            self._group_id = group_id
            self._first_id = None
            self._loading_older = False
            draft = self._drafts.get(f"group {group_id}", "")
            self._suppress_draft_event = True
            self._input.text = draft
            self._suppress_draft_event = False
            self._send_btn.disabled = not draft.strip()
            lines = min(5, max(1, draft.count("\n") + 1))
            self._composer_bar.height = dp(60 + (lines - 1) * 20)

        if theme_changed:
            set_bg_color(self, theme.surface)
            self._topbar.set_theme(theme)
            self._back_btn.set_colors(theme.on_surface_variant)
            self._info_btn.set_colors(theme.on_surface_variant)
            self._title_btn.set_colors(
                (0, 0, 0, 0),
                pressed_bg=with_alpha(theme.on_surface, 0.08),
            )
            self._composer_div.set_color(theme.outline_variant)
            set_bg_color(self._composer_bar, theme.surface)
            border = (theme.primary
                      if self._input.focus else theme.outline_variant)
            self._input_box.set_style(theme.surface_container_low, border)
            self._input.foreground_color = theme.on_surface
            self._input.hint_text_color = theme.on_surface_variant
            self._input.cursor_color = theme.primary
            self._input.selection_color = with_alpha(theme.primary, 0.28)
            self._send_btn.set_colors(theme.on_primary, theme.primary)

        self._back_wrap.width = 0 if wide else dp(40)
        self._back_wrap.opacity = 0.0 if wide else 1.0
        self._back_btn.disabled = wide

        group = next((g for g in state.groups if g.id == group_id), None)
        name = group.display_name if group is not None else group_id[:SHORT_KEY]
        self._avatar.update(group_id, name)
        self._name_lbl.text = name
        self._name_lbl.color = theme.on_surface
        self._sub_lbl.text = group_subtitle(group) if group is not None else ""
        self._sub_lbl.color = theme.on_surface_variant

        if group is not None and not group.connected:
            self._banner.text = (
                group.problem or
                "Connecting to the group: messages can't go out yet.")
            self._banner.color = (theme.error if group.problem is not None
                                  else theme.on_surface_variant)
            set_bg_color(self._banner_box, theme.surface_container_high)
            self._banner_box.opacity = 1.0
            self._banner_box.height = dp(40)
        else:
            self._banner.text = ""
            self._banner_box.opacity = 0.0
            self._banner_box.height = 0

        chat = (state.group_chat if state.group_chat is not None
                and state.group_chat.group == group_id else None)
        msgs = chat.messages if chat is not None else ()
        has_older = chat.has_older if chat is not None else False
        viewport_w = max(self._history.width, Window.width * 0.55)
        max_w = float(
            round(min(dp(_BUBBLE_MAX_DP), max(dp(220), viewport_w * 0.78))))
        today = datetime.date.today()
        sig = (group_id, theme, has_older, max_w, today, msgs)
        if not force and not theme_changed and sig == self._last_sig:
            return
        follow = group_changed or self._last_sig is None
        self._last_sig = sig
        first_id = msgs[0].id if msgs else None
        if first_id != self._first_id:
            # The older page arrived.
            self._first_id = first_id
            self._loading_older = False

        rows: list[Row] = []
        if chat is not None and not msgs:
            rows.append(("empty", theme, partial(self._empty, theme)))
        if has_older:
            rows.append(("older", theme, partial(self._older, theme)))
        for item in group_chat_items(msgs):
            if isinstance(item, DayItem):
                heading = day_heading(item.date, today=today)
                rows.append((
                    item.key,
                    (heading, theme),
                    partial(self._day_heading, heading, theme),
                ))
            elif isinstance(item, GroupBubbleItem):
                rows.append((
                    item.key,
                    (item, max_w, theme),
                    partial(self._bubble, item.message, item.is_first,
                            item.is_last, max_w, theme),
                ))
        self._history.show(rows, follow=follow)

    def _empty(self, theme: ThemeColors) -> Widget:
        spacer = AnchorLayout(
            size_hint=(1, None),
            height=max(dp(200), self._history.height - dp(20)))
        spacer.add_widget(
            Label(text="No messages yet.",
                  color=theme.on_surface_variant, font_size=sp(14.5)))
        return spacer

    def _older(self, theme: ThemeColors) -> Widget:
        older_wrap = AnchorLayout(
            anchor_x="center", size_hint=(1, None), height=dp(42))
        older_wrap.add_widget(
            PillButton(
                text="Load older messages",
                bg=theme.surface_container_high,
                fg=theme.on_surface_variant,
                height_dp=30, pad_x_dp=14, font_size_sp=12, bold=False,
                on_click=self._client.load_older_group_messages,
            ))
        return older_wrap

    @staticmethod
    def _day_heading(text: str, theme: ThemeColors) -> Widget:
        row = AnchorLayout(
            anchor_x="center", anchor_y="center",
            size_hint=(1, None), height=dp(38))
        pill = RoundedBox(
            bg=theme.surface_container_high, radius=[dp(12)],
            size_hint=(None, None), height=dp(24),
            padding=(dp(12), 0, dp(12), 0))
        lbl = Label(
            text=text, color=theme.on_surface_variant, font_size=sp(11.5),
            bold=True, halign="center", valign="middle")
        lbl.texture_update()
        pill.width = lbl.texture_size[0] + dp(24)
        pill.add_widget(lbl)
        row.add_widget(pill)
        return row

    def _bubble(
        self,
        msg: GroupMessage,
        is_first: bool,
        is_last: bool,
        max_w: float,
        theme: ThemeColors,
    ) -> Widget:
        outgoing = msg.outgoing
        bg = theme.primary if outgoing else theme.surface_container_high
        fg = theme.on_primary if outgoing else theme.on_surface
        corner = dp(18)
        tail = dp(4) if is_last else corner
        radius = ([corner, corner, tail, corner] if outgoing
                  else [corner, corner, corner, tail])
        pad_l, pad_r, pad_t, pad_b = dp(14), dp(12), dp(8), dp(6)
        inner_max = max(dp(80), max_w - pad_l - pad_r)
        spacing = dp(3)

        parts: list[Widget] = []
        if is_first and not outgoing:
            parts.append(
                _fit_label(
                    msg.peer_name or msg.peer_key[:SHORT_KEY],
                    peer_rgba(msg.peer_key, theme.is_dark),
                    inner_max, font_size_sp=13, bold=True))
        if msg.private:
            parts.append(
                _fit_label(
                    "Only to them" if outgoing else "Only to you",
                    with_alpha(fg, 0.7), inner_max, font_size_sp=11))
        who = "You" if outgoing else (
            msg.peer_name or msg.peer_key[:SHORT_KEY])
        text = shown_text(msg.text, False)
        body = f"* {who} {text}" if msg.action else text
        parts.append(
            SelectableText(
                body, fg, inner_max,
                selection=with_alpha(
                    theme.on_primary if outgoing else theme.primary, 0.3),
                italic=msg.action))
        stamp_text = ("Not sent" if outgoing and not msg.sent
                      else clock_time(msg.time))
        stamp = _fit_label(
            stamp_text, with_alpha(fg, 0.72), inner_max, font_size_sp=10.5)

        content_w = max([p.width for p in parts] + [stamp.width])
        bubble = RoundedBox(
            bg=bg, radius=radius, orientation="vertical",
            size_hint=(None, None), spacing=spacing,
            padding=(pad_l, pad_t, pad_r, pad_b))
        for p in parts:
            bubble.add_widget(p)
        stamp_row = BoxLayout(
            orientation="horizontal", size_hint=(None, None),
            size=(content_w, stamp.height))
        stamp_row.add_widget(Widget())
        stamp_row.add_widget(stamp)
        bubble.add_widget(stamp_row)
        bubble.width = content_w + pad_l + pad_r
        bubble.height = (sum(p.height for p in parts) + stamp.height
                         + spacing * len(parts) + pad_t + pad_b)

        row_pad_b = dp(6) if is_last else dp(1)
        row = BoxLayout(
            orientation="horizontal", size_hint=(1, None),
            height=bubble.height + row_pad_b, padding=(0, 0, 0, row_pad_b))
        if outgoing:
            row.add_widget(Widget(size_hint=(1, 1)))
            row.add_widget(bubble)
        else:
            row.add_widget(bubble)
            row.add_widget(Widget(size_hint=(1, 1)))
        return row
