# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""1-on-1 chat screen: message bubbles, day headers, inline images, files, composer."""
from __future__ import annotations

import datetime
import threading
from functools import partial
from pathlib import Path
from typing import Any
from typing import Optional

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color
from kivy.graphics import RoundedRectangle
from kivy.metrics import dp
from kivy.metrics import sp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

import pytox.toxcore.tox as core

from pytox_client.model import CallOutcome
from pytox_client.model import ClientState
from pytox_client.model import FileState
from pytox_client.model import FileTransfer
from pytox_client.model import Message
from pytox_client.model import SHORT_KEY
from pytox_client.model import shown_text
from pytox_client.platform_base import Platform
from pytox_client.ui.formatting import BubbleItem
from pytox_client.ui.formatting import DayItem
from pytox_client.ui.formatting import chat_items
from pytox_client.ui.formatting import clock_time
from pytox_client.ui.formatting import day_heading
from pytox_client.ui.formatting import file_size
from pytox_client.ui.formatting import friend_subtitle
from pytox_client.ui.navigator import FriendRoute
from pytox_client.ui.navigator import Navigator
from pytox_client.ui.theme import RGBA
from pytox_client.ui.theme import ThemeColors
from pytox_client.ui.theme import with_alpha
from pytox_client.ui.widgets import AvatarWidget
from pytox_client.ui.widgets import ClickableBox
from pytox_client.ui.widgets import HairlineDivider
from pytox_client.ui.widgets import HistoryView
from pytox_client.ui.widgets import IMAGES
from pytox_client.ui.widgets import IconButton
from pytox_client.ui.widgets import PathIcon
from pytox_client.ui.widgets import PillButton
from pytox_client.ui.widgets import ProgressBarView
from pytox_client.ui.widgets import RoundedBox
from pytox_client.ui.widgets import Row
from pytox_client.ui.widgets import SelectableText
from pytox_client.ui.widgets import TopBar
from pytox_client.ui.widgets import VectorIcon
from pytox_client.ui.widgets import set_bg_color

_PICTURE_MAX_DP = 260.0
_PICTURE_DECODE_PX = 720
_BUBBLE_MAX_DP = 520.0


class _PictureButton(ButtonBehavior, Widget):  # type: ignore[misc]
    """Clickable inline image preview decoded once via ``IMAGES``."""

    def __init__(
        self,
        transfer: FileTransfer,
        platform: Platform,
    ) -> None:
        super().__init__(size_hint=(None, None))
        tex_info = IMAGES.get_image(
            transfer.path, str(transfer.path), _PICTURE_DECODE_PX)
        if tex_info is not None:
            tex, tw, th = tex_info
            max_side = dp(_PICTURE_MAX_DP)
            scale = min(1.0, max_side / float(max(tw, th)))
            w = max(dp(48), tw * scale)
            h = max(dp(48), th * scale)
            self.size = (w, h)
            with self.canvas:
                Color(1, 1, 1, 1)
                self._rect = RoundedRectangle(
                    pos=self.pos, size=self.size, texture=tex, radius=[dp(10)])
        else:
            self.size = (dp(200), dp(140))
            with self.canvas:
                Color(0.5, 0.5, 0.5, 0.25)
                self._rect = RoundedRectangle(
                    pos=self.pos, size=self.size, radius=[dp(10)])
        self.bind(pos=self._sync, size=self._sync)
        self.bind(
            on_release=lambda *_: platform.open_file(
                transfer.path, transfer.name))

    def _sync(self, *_args: Any) -> None:
        self._rect.pos = self.pos
        self._rect.size = self.size


class ComposerInput(TextInput):  # type: ignore[misc]
    """TextInput where Enter sends on desktop and Shift+Enter inserts newline."""

    def __init__(
        self,
        on_send: Any,
        desktop_enter_sends: bool = True,
        **kwargs: Any,
    ) -> None:
        # Not Kivy's "null": phone keyboards then can't swipe or suggest.
        kwargs.setdefault("input_type", "text")
        super().__init__(**kwargs)
        self._on_send = on_send
        self._desktop_enter_sends = desktop_enter_sends

    def keyboard_on_key_down(
        self,
        window: Any,
        keycode: tuple[int, str],
        text: str,
        modifiers: list[str],
    ) -> bool:
        if (self._desktop_enter_sends
                and keycode[1] in ("enter", "numpadenter")
                and "shift" not in modifiers):
            self._on_send()
            return True
        return bool(super().keyboard_on_key_down(
            window, keycode, text, modifiers))


class _FileProgressHandles:
    """Mutable handles allowing smooth in-place progress updates."""

    def __init__(
        self,
        subtitle: Label,
        bar: ProgressBarView,
        total: int,
    ) -> None:
        self.subtitle = subtitle
        self.bar = bar
        self.total = total

    def update(self, done: int) -> None:
        self.subtitle.text = f"{file_size(done)} of {file_size(self.total)}"
        frac = done / float(self.total) if self.total > 0 else 0.0
        self.bar.set_progress(frac)


class ChatPageView(BoxLayout):  # type: ignore[misc]
    """Single friend chat pane: header, scrollable history, composer."""

    def __init__(
        self,
        client: Any,
        platform: Platform,
        navigator: Navigator,
        theme: ThemeColors,
        drafts: dict[str, str],
        desktop_enter_sends: bool = True,
    ) -> None:
        super().__init__(orientation="vertical")
        self._client = client
        self._platform = platform
        self._navigator = navigator
        self._theme = theme
        self._drafts = drafts
        self._friend_key = ""
        self._wide = False
        self._typing_sent = False
        self._suppress_draft_event = False
        self._last_msg_sig: Any = None
        self._last_width_bucket: int = 0
        self._progress_handles: dict[int, _FileProgressHandles] = {}
        self._saved_labels: dict[int, str] = {}
        self._first_id: Optional[int] = None
        self._loading_older = False

        set_bg_color(self, theme.surface)

        # Header bar
        self._topbar = TopBar(theme)
        self._back_wrap = AnchorLayout(size_hint=(None, 1), width=dp(40))
        def _go_back() -> None:
            self._navigator.back()

        self._back_btn = IconButton(
            "back",
            fg=theme.on_surface_variant,
            on_click=_go_back,
            size_dp=40,
            icon_dp=20,
        )
        self._back_wrap.add_widget(self._back_btn)

        self._title_btn = ClickableBox(
            on_press_cb=self._open_friend_info,
            bg=(0, 0, 0, 0),
            pressed_bg=with_alpha(theme.on_surface, 0.08),
            radius=[dp(10)],
            orientation="horizontal",
            padding=(dp(4), dp(4), dp(8), dp(4)),
            spacing=dp(10),
            size_hint=(1, 1),
        )
        self._avatar = AvatarWidget(
            key_hex="", name="?", theme=theme, size_dp=38)
        av_wrap = AnchorLayout(size_hint=(None, 1), width=dp(40))
        av_wrap.add_widget(self._avatar)
        self._title_btn.add_widget(av_wrap)

        name_col = BoxLayout(
            orientation="vertical", size_hint=(1, 1),
            padding=(0, dp(3), 0, dp(3)),
        )
        self._name_lbl = Label(
            text="",
            color=theme.on_surface,
            font_size=sp(15.5),
            bold=True,
            halign="left",
            valign="bottom",
            shorten=True,
            shorten_from="right",
        )
        self._name_lbl.bind(size=lambda i, s: setattr(i, "text_size", s))
        self._sub_lbl = Label(
            text="",
            color=theme.on_surface_variant,
            font_size=sp(12),
            halign="left",
            valign="top",
            shorten=True,
            shorten_from="right",
        )
        self._sub_lbl.bind(size=lambda i, s: setattr(i, "text_size", s))
        name_col.add_widget(self._name_lbl)
        name_col.add_widget(self._sub_lbl)
        self._title_btn.add_widget(name_col)

        self._info_btn = IconButton(
            "info",
            fg=theme.on_surface_variant,
            on_click=self._open_friend_info,
            size_dp=40,
            icon_dp=20,
        )
        self._info_wrap = AnchorLayout(size_hint=(None, 1), width=dp(42))
        self._info_wrap.add_widget(self._info_btn)

        self._call_btn = IconButton(
            "call",
            fg=theme.on_surface_variant,
            on_click=lambda: self._call(False),
            size_dp=40,
            icon_dp=22,
        )
        self._video_btn = IconButton(
            "videocam",
            fg=theme.on_surface_variant,
            on_click=lambda: self._call(True),
            size_dp=40,
            icon_dp=22,
        )
        self._calls_wrap = BoxLayout(orientation="horizontal",
                                     size_hint=(None, 1))
        # Centred like the info button, whatever the top bar's height.
        buttons = [self._call_btn]
        if platform.cameras > 0:
            buttons.append(self._video_btn)
        for button in buttons:
            wrap = AnchorLayout(size_hint=(None, 1), width=dp(40))
            wrap.add_widget(button)
            self._calls_wrap.add_widget(wrap)
        self._calls_wrap.width = dp(40) * len(buttons)

        self._topbar.row.add_widget(self._back_wrap)
        self._topbar.row.add_widget(self._title_btn)
        self._topbar.row.add_widget(self._calls_wrap)
        self._topbar.row.add_widget(self._info_wrap)
        self.add_widget(self._topbar)

        self._history = HistoryView(
            desktop=desktop_enter_sends, on_near_top=self._near_top)
        self._history.bind(width=self._on_viewport_resize)
        self.add_widget(self._history)

        # Composer area
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

        self._attach_btn = IconButton(
            "attach",
            fg=theme.on_surface_variant,
            size_dp=44,
            icon_dp=22,
            on_click=self._pick_and_send_file,
        )
        attach_wrap = AnchorLayout(
            anchor_y="bottom", size_hint=(None, 1), width=dp(44))
        attach_wrap.add_widget(self._attach_btn)
        self._composer_bar.add_widget(attach_wrap)

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
            hint_text="Message",
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
            "send",
            fg=theme.on_primary,
            bg=theme.primary,
            size_dp=44,
            icon_dp=19,
            on_click=self._send,
        )
        self._send_btn.disabled = True
        send_wrap = AnchorLayout(
            anchor_y="bottom", size_hint=(None, 1), width=dp(44))
        send_wrap.add_widget(self._send_btn)
        self._composer_bar.add_widget(send_wrap)
        self.add_widget(self._composer_bar)

        self._state_cache: Optional[ClientState] = None
        self._resize_ev: Any = None

    def clear_typing(self) -> None:
        if self._friend_key and self._typing_sent:
            self._typing_sent = False
            self._client.set_typing(self._friend_key, False)

    def close(self) -> None:
        self.clear_typing()
        if self._resize_ev is not None:
            self._resize_ev.cancel()
            self._resize_ev = None
        self._history.close()

    def _call(self, video: bool) -> None:
        friend = self._friend_key
        self._platform.ask_call_permissions(
            video, lambda: self._client.call(friend, video))

    def _open_friend_info(self) -> None:
        if self._friend_key:
            self._navigator.push(FriendRoute(self._friend_key))

    def _pick_and_send_file(self) -> None:
        key = self._friend_key
        if not key:
            return
        self._platform.pick_file(
            images=False,
            on_picked=lambda picked: self._client.send_file(key, picked),
        )

    def _on_input_focus(self, _inst: Any, focused: bool) -> None:
        border = (self._theme.primary
                  if focused else self._theme.outline_variant)
        self._input_box.set_style(self._theme.surface_container_low, border)

    def _on_text_changed(self, _inst: Any, value: str) -> None:
        if self._suppress_draft_event:
            return
        if self._friend_key:
            self._drafts[self._friend_key] = value
        non_blank = bool(value.strip())
        self._send_btn.disabled = not non_blank
        # Auto-grow composer box from 1 up to ~5 lines.
        lines = min(5, max(1, value.count("\n") + 1))
        self._composer_bar.height = dp(60 + (lines - 1) * 20)
        typing_now = bool(value)
        if self._friend_key and typing_now != self._typing_sent:
            self._typing_sent = typing_now
            self._client.set_typing(self._friend_key, typing_now)

    def _send(self) -> None:
        text = self._input.text
        if not self._friend_key or not text.strip():
            return
        action = text.startswith("/me ")
        body = text[4:] if action else text
        self._client.send(self._friend_key, body, action=action)
        self._suppress_draft_event = True
        self._input.text = ""
        self._suppress_draft_event = False
        self._drafts[self._friend_key] = ""
        self._composer_bar.height = dp(60)
        self._send_btn.disabled = True
        if self._typing_sent:
            self._typing_sent = False
            self._client.set_typing(self._friend_key, False)
        Clock.schedule_once(lambda _dt: setattr(self._input, "focus", True), 0)

    def _near_top(self) -> None:
        if self._state_cache is not None:
            chat = self._state_cache.chat
            if (chat is not None and chat.friend == self._friend_key
                    and chat.has_older and not self._loading_older):
                self._loading_older = True
                self._client.load_older()

    def _on_viewport_resize(self, _inst: Any, width: float) -> None:
        bucket = int(width // dp(40))
        if bucket != self._last_width_bucket and self._state_cache is not None:
            self._last_width_bucket = bucket
            if self._resize_ev is not None:
                self._resize_ev.cancel()
            self._resize_ev = Clock.schedule_once(
                lambda _dt: self._reflow(), 0.05)

    def _reflow(self) -> None:
        if self._state_cache is not None and self._friend_key:
            self.update(
                self._friend_key,
                self._state_cache,
                self._theme,
                self._wide,
                force=True,
            )

    def update(
        self,
        friend_key: str,
        state: ClientState,
        theme: ThemeColors,
        wide: bool,
        force: bool = False,
    ) -> None:
        self._state_cache = state
        theme_changed = theme != self._theme
        friend_changed = friend_key != self._friend_key
        wide_changed = wide != self._wide
        self._theme = theme
        self._wide = wide

        if friend_changed:
            if self._friend_key and self._typing_sent:
                self._client.set_typing(self._friend_key, False)
                self._typing_sent = False
            self._friend_key = friend_key
            self._first_id = None
            self._loading_older = False
            draft = self._drafts.get(friend_key, "")
            self._suppress_draft_event = True
            self._input.text = draft
            self._suppress_draft_event = False
            self._send_btn.disabled = not bool(draft.strip())
            lines = min(5, max(1, draft.count("\n") + 1))
            self._composer_bar.height = dp(60 + (lines - 1) * 20)

        if theme_changed:
            set_bg_color(self, theme.surface)
            self._topbar.set_theme(theme)
            self._back_btn.set_colors(theme.on_surface_variant)
            self._info_btn.set_colors(theme.on_surface_variant)
            self._call_btn.set_colors(theme.on_surface_variant)
            self._video_btn.set_colors(theme.on_surface_variant)
            self._title_btn.set_colors(
                (0, 0, 0, 0),
                pressed_bg=with_alpha(theme.on_surface, 0.08),
            )
            self._composer_div.set_color(theme.outline_variant)
            set_bg_color(self._composer_bar, theme.surface)
            self._attach_btn.set_colors(theme.on_surface_variant)
            border = (theme.primary
                      if self._input.focus else theme.outline_variant)
            self._input_box.set_style(theme.surface_container_low, border)
            self._input.foreground_color = theme.on_surface
            self._input.hint_text_color = theme.on_surface_variant
            self._input.cursor_color = theme.primary
            self._input.selection_color = with_alpha(theme.primary, 0.28)
            self._send_btn.set_colors(theme.on_primary, theme.primary)

        if wide_changed or friend_changed or force:
            self._back_wrap.width = 0 if wide else dp(40)
            self._back_wrap.opacity = 0.0 if wide else 1.0
            self._back_btn.disabled = wide

        friend = next(
            (f for f in state.friends if f.key == friend_key), None)
        display_name = (friend.display_name
                        if friend is not None else friend_key[:SHORT_KEY])
        self._avatar.update(
            key_hex=friend_key,
            name=display_name,
            theme=theme,
            connection=friend.connection if friend is not None else None,
            status=(friend.status
                    if friend is not None else core.UserStatus.NONE),
            picture=friend.avatar if friend is not None else None,
            ring_color=theme.surface,
        )
        self._name_lbl.text = display_name
        self._name_lbl.color = theme.on_surface
        # A call goes to a friend who's online, one at a time; calling back
        # one who calls us answers them.
        call = state.call
        can_call = friend is not None and friend.online and (
            call is None or
            (call.friend == friend_key and not call.outgoing and call.ringing))
        self._call_btn.disabled = not can_call
        self._video_btn.disabled = not can_call
        if friend is not None:
            self._sub_lbl.text = friend_subtitle(friend)
            self._sub_lbl.color = (theme.primary if friend.typing
                                   else theme.on_surface_variant)
        else:
            self._sub_lbl.text = ""

        # Live progress update without rebuilding the message list.
        for msg_id, done in state.progress.items():
            handle = self._progress_handles.get(msg_id)
            if handle is not None:
                handle.update(done)

        chat = (state.chat if state.chat is not None
                and state.chat.friend == friend_key else None)
        msgs = chat.messages if chat is not None else ()
        has_older = chat.has_older if chat is not None else False
        hide = friend.hide_after_zero if friend is not None else False
        viewport_w = max(self._history.width, Window.width * 0.55)
        max_bubble_w = float(
            round(min(dp(_BUBBLE_MAX_DP), max(dp(220), viewport_w * 0.78))))
        today = datetime.date.today()
        sig = (
            friend_key,
            theme,
            display_name,
            hide,
            has_older,
            max_bubble_w,
            today,
            msgs,
        )
        if not force and not theme_changed and sig == self._last_msg_sig:
            return
        follow = friend_changed or self._last_msg_sig is None
        self._last_msg_sig = sig
        first_id = msgs[0].id if msgs else None
        if first_id != self._first_id:
            # The older page arrived.
            self._first_id = first_id
            self._loading_older = False

        rows: list[Row] = []
        if chat is not None and not msgs:
            rows.append((
                ("hello", display_name),
                theme,
                partial(self._build_hello, display_name, theme),
            ))
        if has_older:
            rows.append((
                "older",
                theme,
                partial(self._build_older, theme),
            ))
        for item in chat_items(msgs):
            if isinstance(item, DayItem):
                heading = day_heading(item.date, today=today)
                rows.append((
                    item.key,
                    (heading, theme),
                    partial(self._build_day_heading, heading, theme),
                ))
            elif isinstance(item, BubbleItem):
                rows.append((
                    item.key,
                    (item, display_name, hide, max_bubble_w, theme),
                    partial(
                        self._build_bubble,
                        item.message,
                        item.is_last,
                        display_name,
                        hide,
                        state.progress.get(item.message.id),
                        max_bubble_w,
                        theme,
                    ),
                ))
        self._history.show(rows, follow=follow)
        shown = {m.id for m in msgs}
        self._progress_handles = {
            k: v for k, v in self._progress_handles.items() if k in shown}

    def _build_hello(self, display_name: str, theme: ThemeColors) -> Widget:
        spacer = AnchorLayout(
            size_hint=(1, None),
            height=max(dp(200), self._history.height - dp(20)),
        )
        spacer.add_widget(
            Label(
                text=f"Say hello to {display_name}.",
                color=theme.on_surface_variant,
                font_size=sp(14.5),
            )
        )
        return spacer

    def _build_older(self, theme: ThemeColors) -> Widget:
        older_wrap = AnchorLayout(
            anchor_x="center", size_hint=(1, None), height=dp(42))
        older_wrap.add_widget(
            PillButton(
                text="Load older messages",
                bg=theme.surface_container_high,
                fg=theme.on_surface_variant,
                height_dp=30,
                pad_x_dp=14,
                font_size_sp=12,
                bold=False,
                on_click=lambda: self._client.load_older(),
            )
        )
        return older_wrap

    def _build_day_heading(self, text: str, theme: ThemeColors) -> Widget:
        row = AnchorLayout(
            anchor_x="center",
            anchor_y="center",
            size_hint=(1, None),
            height=dp(38),
        )
        pill = RoundedBox(
            bg=theme.surface_container_high,
            radius=[dp(12)],
            size_hint=(None, None),
            height=dp(24),
            padding=(dp(12), 0, dp(12), 0),
        )
        lbl = Label(
            text=text,
            color=theme.on_surface_variant,
            font_size=sp(11.5),
            bold=True,
            halign="center",
            valign="middle",
        )
        lbl.texture_update()
        pill.width = lbl.texture_size[0] + dp(24)
        pill.add_widget(lbl)
        row.add_widget(pill)
        return row

    def _build_bubble(
        self,
        msg: Message,
        is_last: bool,
        friend_name: str,
        hide_after_zero: bool,
        live_done: Optional[int],
        max_bubble_w: float,
        theme: ThemeColors,
    ) -> Widget:
        # A file card built below takes over the live progress.
        self._progress_handles.pop(msg.id, None)
        outgoing = msg.outgoing
        bg = theme.primary if outgoing else theme.surface_container_high
        fg = theme.on_primary if outgoing else theme.on_surface
        corner = dp(18)
        tail = dp(4) if is_last else corner
        radius = ([corner, corner, tail, corner] if outgoing
                  else [corner, corner, corner, tail])

        if msg.call is not None:
            return self._build_call_note(msg, is_last, bg, fg, radius, theme)

        ft = msg.file
        is_picture = (ft is not None and ft.state == FileState.DONE
                      and ft.is_image)

        bubble = RoundedBox(
            bg=bg,
            radius=radius,
            orientation="vertical",
            size_hint=(None, None),
            spacing=dp(3),
        )

        if ft is None:
            text = shown_text(msg.text, hide_after_zero)
            body_text = (
                f"* {'You' if outgoing else friend_name} {text}"
                if msg.action else text
            )
            pad_x_l = dp(14)
            pad_x_r = dp(12)
            bubble.padding = (pad_x_l, dp(8), pad_x_r, dp(6))
            inner_max = max(dp(80), max_bubble_w - pad_x_l - pad_x_r)

            txt = SelectableText(
                body_text,
                fg,
                inner_max,
                selection=with_alpha(
                    theme.on_primary if outgoing else theme.primary, 0.3),
                italic=msg.action,
            )
            txt_w = txt.width
            bubble.add_widget(txt)

            meta_row, meta_w = self._build_meta_row(msg, fg, outgoing, False)
            content_w = max(txt_w, meta_w)
            meta_wrap = BoxLayout(
                orientation="horizontal",
                size_hint=(None, None),
                size=(content_w, dp(16)),
            )
            meta_wrap.add_widget(Widget())
            meta_wrap.add_widget(meta_row)
            bubble.add_widget(meta_wrap)
            bubble.width = content_w + pad_x_l + pad_x_r
            bubble.height = txt.height + dp(16) + dp(17)
        elif is_picture:
            pad = dp(6)
            bubble.padding = (pad, pad, pad, pad)
            pic_btn = _PictureButton(ft, self._platform)
            bubble.add_widget(pic_btn)
            meta_row, meta_w = self._build_meta_row(msg, fg, outgoing, True)
            content_w = max(pic_btn.width, meta_w)
            meta_wrap = BoxLayout(
                orientation="horizontal",
                size_hint=(None, None),
                size=(content_w, dp(16)),
            )
            meta_wrap.add_widget(Widget())
            meta_wrap.add_widget(meta_row)
            bubble.add_widget(meta_wrap)
            bubble.width = content_w + pad * 2
            bubble.height = pic_btn.height + dp(16) + pad * 2 + dp(3)
        else:
            pad = dp(12)
            bubble.padding = (pad, dp(10), pad, dp(8))
            card_w = min(max_bubble_w - pad * 2, max(dp(230), dp(270)))
            card = self._build_file_card(
                msg, ft, live_done if live_done is not None else ft.done,
                fg, card_w,
            )
            bubble.add_widget(card)
            meta_row, _ = self._build_meta_row(msg, fg, outgoing, True)
            meta_wrap = BoxLayout(
                orientation="horizontal",
                size_hint=(None, None),
                size=(card_w, dp(15)),
            )
            meta_wrap.add_widget(Widget())
            meta_wrap.add_widget(meta_row)
            bubble.add_widget(meta_wrap)
            bubble.width = card_w + pad * 2
            bubble.height = card.height + dp(15) + dp(21)

        row_pad_b = dp(6) if is_last else dp(1)
        row = BoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=bubble.height + row_pad_b,
            padding=(0, 0, 0, row_pad_b),
        )
        if outgoing:
            row.add_widget(Widget(size_hint=(1, 1)))
            row.add_widget(bubble)
        else:
            row.add_widget(bubble)
            row.add_widget(Widget(size_hint=(1, 1)))
        return row

    def _build_call_note(
        self,
        msg: Message,
        is_last: bool,
        bg: RGBA,
        fg: RGBA,
        radius: list[float],
        theme: ThemeColors,
    ) -> Widget:
        """A call in the chat: what kind, how it went, and when."""
        assert msg.call is not None
        missed = (not msg.outgoing and msg.call.outcome == CallOutcome.MISSED)
        bubble = RoundedBox(
            bg=bg,
            radius=radius,
            orientation="horizontal",
            size_hint=(None, None),
            height=dp(44),
            padding=(dp(12), 0, dp(12), 0),
            spacing=dp(8),
        )
        icon_wrap = AnchorLayout(size_hint=(None, 1), width=dp(20))
        icon_wrap.add_widget(
            PathIcon("videocam" if msg.call.video else "call",
                     theme.error if missed else fg, size_dp=18))
        bubble.add_widget(icon_wrap)
        text = Label(text=msg.call_text,
                     color=theme.error if missed else fg,
                     font_size=sp(14),
                     bold=missed,
                     size_hint=(None, 1))
        text.texture_update()
        text.width = text.texture_size[0]
        bubble.add_widget(text)
        when = Label(text=clock_time(msg.time),
                     color=with_alpha(fg, 0.7),
                     font_size=sp(11),
                     size_hint=(None, 1))
        when.texture_update()
        when.width = when.texture_size[0]
        bubble.add_widget(when)
        bubble.width = dp(20) + text.width + when.width + dp(16) + dp(24)
        row_pad_b = dp(6) if is_last else dp(1)
        row = BoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=bubble.height + row_pad_b,
            padding=(0, 0, 0, row_pad_b),
        )
        if msg.outgoing:
            row.add_widget(Widget(size_hint=(1, 1)))
            row.add_widget(bubble)
        else:
            row.add_widget(bubble)
            row.add_widget(Widget(size_hint=(1, 1)))
        return row

    def _build_meta_row(
        self,
        msg: Message,
        fg: RGBA,
        outgoing: bool,
        is_file: bool,
    ) -> tuple[BoxLayout, float]:
        t_str = clock_time(msg.time)
        t_lbl = Label(
            text=t_str,
            color=with_alpha(fg, 0.72),
            font_size=sp(10.5),
            size_hint=(None, 1),
            halign="right",
            valign="middle",
        )
        t_lbl.texture_update()
        t_lbl.width = t_lbl.texture_size[0] + dp(2)
        total_w = t_lbl.width

        row = BoxLayout(
            orientation="horizontal",
            size_hint=(None, None),
            height=dp(15),
            spacing=dp(3),
        )
        row.add_widget(t_lbl)
        if outgoing and not is_file:
            if msg.delivered:
                chk = VectorIcon("check", with_alpha(fg, 0.85), size_dp=13)
                chk_wrap = AnchorLayout(size_hint=(None, 1), width=dp(13))
                chk_wrap.add_widget(chk)
                row.add_widget(chk_wrap)
                total_w += dp(16)
            else:
                pend = Label(
                    text="...",
                    color=with_alpha(fg, 0.72),
                    font_size=sp(10.5),
                    size_hint=(None, 1),
                    width=dp(14),
                )
                row.add_widget(pend)
                total_w += dp(17)
        row.width = total_w
        return row, total_w

    def _build_file_card(
        self,
        msg: Message,
        ft: FileTransfer,
        done: int,
        fg: RGBA,
        width: float,
    ) -> BoxLayout:
        col = BoxLayout(
            orientation="vertical",
            size_hint=(None, None),
            width=width,
            spacing=dp(6),
        )
        top = BoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(42),
            spacing=dp(10),
        )
        ext = (ft.name.rsplit(".", 1)[-1][:4].upper()
               if "." in ft.name else "FILE")
        badge = RoundedBox(
            bg=with_alpha(fg, 0.16),
            radius=[dp(8)],
            size_hint=(None, None),
            size=(dp(40), dp(40)),
        )
        badge.add_widget(
            Label(
                text=ext or "FILE",
                color=fg,
                font_size=sp(10.5),
                bold=True,
                halign="center",
                valign="middle",
            )
        )
        top.add_widget(badge)

        info = BoxLayout(orientation="vertical", size_hint=(1, 1))
        name_lbl = Label(
            text=ft.name,
            color=fg,
            font_size=sp(13.5),
            bold=True,
            halign="left",
            valign="bottom",
            shorten=True,
            shorten_from="right",
        )
        name_lbl.bind(size=lambda i, s: setattr(i, "text_size", s))
        if ft.state == FileState.OFFERED:
            sub_txt = (f"{file_size(ft.size)}, waiting"
                       if msg.outgoing else file_size(ft.size))
        elif ft.state == FileState.ACTIVE:
            sub_txt = f"{file_size(done)} of {file_size(ft.size)}"
        elif ft.state == FileState.DONE:
            saved = self._saved_labels.get(msg.id)
            sub_txt = f"Saved in {saved}" if saved else file_size(ft.size)
        else:
            sub_txt = f"{file_size(ft.size)}, cancelled"
        sub_lbl = Label(
            text=sub_txt,
            color=with_alpha(fg, 0.78),
            font_size=sp(11.5),
            halign="left",
            valign="top",
            shorten=True,
            shorten_from="right",
        )
        sub_lbl.bind(size=lambda i, s: setattr(i, "text_size", s))
        info.add_widget(name_lbl)
        info.add_widget(sub_lbl)
        top.add_widget(info)
        col.add_widget(top)

        total_h = dp(42)
        if ft.state == FileState.ACTIVE:
            frac = done / float(ft.size) if ft.size > 0 else 0.0
            bar = ProgressBarView(
                fg=fg, track=with_alpha(fg, 0.24), fraction=frac)
            col.add_widget(bar)
            total_h += dp(11)
            self._progress_handles[msg.id] = _FileProgressHandles(
                sub_lbl, bar, ft.size)

        actions = BoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(30),
            spacing=dp(6),
        )
        actions.add_widget(Widget())
        has_btns = False
        def _cancel_cb(mid: int = msg.id) -> None:
            self._client.cancel_file(mid)

        def _accept_cb(mid: int = msg.id) -> None:
            self._client.accept_file(mid)

        def _open_cb(path: Path = ft.path, fname: str = ft.name) -> None:
            self._platform.open_file(path, fname)

        if ft.state == FileState.OFFERED and not msg.outgoing:
            has_btns = True
            actions.add_widget(
                PillButton(
                    text="Decline",
                    bg=(0, 0, 0, 0),
                    fg=fg,
                    height_dp=28,
                    pad_x_dp=10,
                    font_size_sp=12,
                    on_click=_cancel_cb,
                )
            )
            actions.add_widget(
                PillButton(
                    text="Accept",
                    bg=with_alpha(fg, 0.2),
                    fg=fg,
                    height_dp=28,
                    pad_x_dp=12,
                    font_size_sp=12,
                    on_click=_accept_cb,
                )
            )
        elif ft.state in (FileState.OFFERED, FileState.ACTIVE):
            has_btns = True
            actions.add_widget(
                PillButton(
                    text="Cancel",
                    bg=with_alpha(fg, 0.14),
                    fg=fg,
                    height_dp=26,
                    pad_x_dp=12,
                    font_size_sp=12,
                    on_click=_cancel_cb,
                )
            )
        elif ft.state == FileState.DONE:
            has_btns = True
            if not msg.outgoing:
                save_btn = PillButton(
                    text="Save",
                    bg=(0, 0, 0, 0),
                    fg=fg,
                    height_dp=28,
                    pad_x_dp=10,
                    font_size_sp=12,
                )

                def _save(
                    mid: int = msg.id,
                    path: Any = ft.path,
                    fname: str = ft.name,
                    lbl: Label = sub_lbl,
                    btn: PillButton = save_btn,
                ) -> None:
                    btn.disabled = True
                    lbl.text = "Saving..."

                    def _worker() -> None:
                        try:
                            dest = self._platform.save_to_downloads(
                                path, fname)
                        except Exception:  # noqa: BLE001
                            dest = None

                        def _done(_dt: float) -> None:
                            btn.disabled = False
                            if dest:
                                self._saved_labels[mid] = dest
                                lbl.text = f"Saved in {dest}"
                            else:
                                lbl.text = "Couldn't save file"

                        Clock.schedule_once(_done, 0)

                    threading.Thread(target=_worker, daemon=True).start()

                save_btn.bind(on_release=lambda *_a, f=_save: f())
                actions.add_widget(save_btn)
            actions.add_widget(
                PillButton(
                    text="Open",
                    bg=with_alpha(fg, 0.2),
                    fg=fg,
                    height_dp=28,
                    pad_x_dp=12,
                    font_size_sp=12,
                    on_click=_open_cb,
                )
            )
        if has_btns:
            col.add_widget(actions)
            total_h += dp(32)
        col.height = total_h
        return col
