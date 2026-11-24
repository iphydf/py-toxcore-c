# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""Left-pane / root chat list view (profile bar, friend requests, chats)."""
from __future__ import annotations

import datetime
from functools import partial
from typing import Any
from typing import Callable
from typing import Optional
from typing import Union

from kivy.clock import Clock
from kivy.graphics import Color
from kivy.graphics import RoundedRectangle
from kivy.metrics import dp
from kivy.metrics import sp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget

from pytox_client.model import ClientState
from pytox_client.model import Friend
from pytox_client.model import FriendRequest
from pytox_client.model import Group
from pytox_client.model import GroupInvite
from pytox_client.model import SHORT_KEY
from pytox_client.platform_base import Platform
from pytox_client.ui.formatting import friend_row_preview
from pytox_client.ui.formatting import group_row_preview
from pytox_client.ui.formatting import grouped_id
from pytox_client.ui.formatting import self_connection_text
from pytox_client.ui.formatting import short_time
from pytox_client.ui.navigator import AddRoute
from pytox_client.ui.navigator import ChatRoute
from pytox_client.ui.navigator import GroupRoute
from pytox_client.ui.navigator import Navigator
from pytox_client.ui.navigator import ProfileRoute
from pytox_client.ui.theme import ThemeColors
from pytox_client.ui.theme import with_alpha
from pytox_client.ui.widgets import AvatarWidget
from pytox_client.ui.widgets import ClickableBox
from pytox_client.ui.widgets import GroupAvatarWidget
from pytox_client.ui.widgets import IconButton
from pytox_client.ui.widgets import KeyedColumn
from pytox_client.ui.widgets import PillButton
from pytox_client.ui.widgets import RoundedBox
from pytox_client.ui.widgets import Row
from pytox_client.ui.widgets import TopBar
from pytox_client.ui.widgets import auto_label
from pytox_client.ui.widgets import set_bg_color


class UnreadBadge(Label):  # type: ignore[misc]
    """Compact pill badge showing unread message count."""

    def __init__(self, count: int, theme: ThemeColors) -> None:
        super().__init__(
            text=str(count),
            color=theme.on_primary,
            font_size=sp(11),
            bold=True,
            size_hint=(None, None),
            height=dp(20),
            width=dp(max(20, 12 + len(str(count)) * 7)),
            halign="center",
            valign="middle",
        )
        self._bg = theme.primary
        self.bind(pos=self._redraw, size=self._redraw)
        self._redraw()

    def _redraw(self, *_args: Any) -> None:
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*self._bg)
            RoundedRectangle(
                pos=self.pos, size=self.size, radius=[self.height / 2.0])


class ChatListView(BoxLayout):  # type: ignore[misc]
    """Profile top bar, friend request cards, friend rows, or welcome state."""

    def __init__(
        self,
        client: Any,
        platform: Platform,
        navigator: Navigator,
        theme: ThemeColors,
        open_menu: Callable[[], None],
        mono_font: Optional[str] = None,
    ) -> None:
        super().__init__(orientation="vertical")
        self._client = client
        self._platform = platform
        self._navigator = navigator
        self._theme = theme
        self._mono_font = mono_font
        self._last_sig: Any = None
        self._wide = False
        self._selected: Optional[str] = None
        self._copy_reset_ev: Any = None

        set_bg_color(self, theme.surface)

        # Top app bar with clickable self profile chip + action icons.
        self._topbar = TopBar(theme)
        self._profile_btn = ClickableBox(
            on_press_cb=lambda: self._navigator.show(ProfileRoute()),
            bg=(0, 0, 0, 0),
            pressed_bg=with_alpha(theme.on_surface, 0.08),
            radius=[dp(10)],
            orientation="horizontal",
            padding=(dp(6), dp(4), dp(8), dp(4)),
            spacing=dp(10),
            size_hint=(1, 1),
        )
        self._self_avatar = AvatarWidget(
            key_hex="", name="Me", theme=theme, size_dp=38)
        av_wrap = AnchorLayout(
            anchor_x="center", anchor_y="center",
            size_hint=(None, 1), width=dp(40),
        )
        av_wrap.add_widget(self._self_avatar)
        self._profile_btn.add_widget(av_wrap)

        name_col = BoxLayout(
            orientation="vertical", size_hint=(1, 1),
            padding=(0, dp(3), 0, dp(3)),
        )
        self._self_name = Label(
            text="Set your name",
            color=theme.primary,
            font_size=sp(15),
            bold=True,
            halign="left",
            valign="bottom",
            shorten=True,
            shorten_from="right",
        )
        self._self_name.bind(
            size=lambda i, s: setattr(i, "text_size", s))
        self._self_conn = Label(
            text="Connecting...",
            color=theme.on_surface_variant,
            font_size=sp(11.5),
            halign="left",
            valign="top",
            shorten=True,
            shorten_from="right",
        )
        self._self_conn.bind(
            size=lambda i, s: setattr(i, "text_size", s))
        name_col.add_widget(self._self_name)
        name_col.add_widget(self._self_conn)
        self._profile_btn.add_widget(name_col)

        self._add_btn = IconButton(
            "add",
            fg=theme.on_surface_variant,
            on_click=lambda: self._navigator.show(AddRoute()),
            size_dp=40,
            icon_dp=20,
        )
        # The profiles to switch between, and the settings.
        self._menu_btn = IconButton(
            "menu",
            fg=theme.on_surface_variant,
            on_click=open_menu,
            size_dp=40,
            icon_dp=20,
        )
        menu_wrap = AnchorLayout(size_hint=(None, 1), width=dp(42))
        menu_wrap.add_widget(self._menu_btn)
        self._topbar.row.add_widget(menu_wrap)
        self._topbar.row.add_widget(self._profile_btn)
        add_wrap = AnchorLayout(size_hint=(None, 1), width=dp(42))
        add_wrap.add_widget(self._add_btn)
        self._topbar.row.add_widget(add_wrap)
        self.add_widget(self._topbar)

        # Scrollable body container (swaps between empty Welcome & list).
        self._body = BoxLayout(orientation="vertical", size_hint=(1, 1))
        self.add_widget(self._body)

        self._scroll = ScrollView(do_scroll_x=False, bar_width=dp(4))
        self._list_box = BoxLayout(
            orientation="vertical",
            size_hint=(1, None),
            padding=(dp(8), dp(6), dp(8), dp(12)),
            spacing=dp(4),
        )
        self._list_box.bind(minimum_height=self._list_box.setter("height"))
        self._scroll.add_widget(self._list_box)
        self._rows = KeyedColumn(self._list_box)

    def close(self) -> None:
        if self._copy_reset_ev is not None:
            self._copy_reset_ev.cancel()
            self._copy_reset_ev = None

    def update(
        self,
        state: ClientState,
        theme: ThemeColors,
        wide: bool,
        selected: Optional[str],
        force: bool = False,
        selected_group: Optional[str] = None,
    ) -> None:
        theme_changed = theme != self._theme
        self._theme = theme
        self._wide = wide
        self._selected = selected

        if theme_changed:
            set_bg_color(self, theme.surface)
            self._topbar.set_theme(theme)
            self._profile_btn.set_colors(
                (0, 0, 0, 0),
                pressed_bg=with_alpha(theme.on_surface, 0.08),
            )
            self._add_btn.set_colors(theme.on_surface_variant)
            self._menu_btn.set_colors(theme.on_surface_variant)

        # Always refresh profile chip cleanly.
        p = state.profile
        self._self_avatar.update(
            key_hex=p.address,
            name=p.name or "Me",
            theme=theme,
            connection=p.connection,
            status=p.status,
            picture=p.avatar,
            ring_color=theme.surface,
        )
        if p.name:
            self._self_name.text = p.name
            self._self_name.color = theme.on_surface
        else:
            self._self_name.text = "Set your name"
            self._self_name.color = theme.primary
        self._self_conn.text = self_connection_text(p.connection)
        self._self_conn.color = theme.on_surface_variant

        sig = (
            theme.is_dark,
            wide,
            selected,
            selected_group,
            datetime.date.today(),
            p.address,
            state.requests,
            state.friends,
            state.groups,
            state.invites,
        )
        if not force and not theme_changed and sig == self._last_sig:
            return
        self._last_sig = sig

        if (not state.friends and not state.requests and not state.groups
                and not state.invites):
            self._body.clear_widgets()
            self._body.add_widget(self._build_welcome(state, theme))
            return

        rows: list[Row] = []
        for req in state.requests:
            rows.append((
                ("request", req.key),
                (req, theme),
                partial(self._build_request_card, req, theme),
            ))
        for invite in state.invites:
            rows.append((
                ("invite", invite.friend, invite.data),
                (invite, self._invite_sender(invite, state), theme),
                partial(self._build_invite_card, invite, state, theme),
            ))
        # Friends and groups together, the latest chats first.
        chats: list[tuple[int, Union[Friend, Group]]] = [
            (f.last.time if f.last is not None else 0, f)
            for f in state.friends
        ] + [
            (g.last.time if g.last is not None else 0, g)
            for g in state.groups
        ]
        chats.sort(key=lambda c: -c[0])
        for _, chat in chats:
            if isinstance(chat, Friend):
                is_sel = wide and chat.key == selected
                rows.append((
                    ("friend", chat.key),
                    (chat, is_sel, theme),
                    partial(self._build_friend_row, chat, is_sel, theme),
                ))
            else:
                is_sel = wide and chat.id == selected_group
                rows.append((
                    ("group", chat.id),
                    (chat, is_sel, theme),
                    partial(self._build_group_row, chat, is_sel, theme),
                ))
        self._rows.show(rows)
        if self._scroll.parent is not self._body:
            self._body.clear_widgets()
            self._body.add_widget(self._scroll)

    @staticmethod
    def _invite_sender(invite: GroupInvite, state: ClientState) -> str:
        friend = next(
            (f for f in state.friends if f.key == invite.friend), None)
        return (friend.display_name
                if friend is not None else invite.friend[:SHORT_KEY])

    def _build_invite_card(
        self,
        invite: GroupInvite,
        state: ClientState,
        theme: ThemeColors,
    ) -> Widget:
        sender = self._invite_sender(invite, state)
        card = RoundedBox(
            bg=theme.tertiary_container,
            radius=[dp(14)],
            orientation="vertical",
            size_hint=(1, None),
            padding=(dp(14), dp(12), dp(14), dp(12)),
            spacing=dp(6),
        )
        card.bind(minimum_height=card.setter("height"))
        card.add_widget(
            auto_label(f"Group invite from {sender}",
                       color=theme.on_tertiary_container, font_size_sp=13.5,
                       bold=True))
        card.add_widget(
            auto_label(invite.name or "A group",
                       color=theme.on_tertiary_container, font_size_sp=15))
        actions = BoxLayout(
            orientation="horizontal", size_hint=(1, None), height=dp(36),
            spacing=dp(8))
        actions.add_widget(Widget())

        def _decline(i: GroupInvite = invite) -> None:
            self._client.decline_invite(i)

        def _join(i: GroupInvite = invite) -> None:
            self._client.accept_invite(i)

        actions.add_widget(
            PillButton(
                text="Decline", bg=(0, 0, 0, 0),
                fg=theme.on_tertiary_container,
                border=with_alpha(theme.on_tertiary_container, 0.4),
                height_dp=34, pad_x_dp=14, font_size_sp=12.5,
                on_click=_decline))
        actions.add_widget(
            PillButton(
                text="Join", bg=theme.primary, fg=theme.on_primary,
                height_dp=34, pad_x_dp=16, font_size_sp=12.5,
                on_click=_join))
        card.add_widget(actions)
        return card

    def _build_group_row(
        self,
        group: Group,
        selected: bool,
        theme: ThemeColors,
    ) -> Widget:
        row_bg = theme.secondary_container if selected else theme.surface
        pressed_bg = (theme.secondary_container
                      if selected else theme.surface_container_high)

        def _open(gid: str = group.id) -> None:
            self._navigator.show(GroupRoute(gid))

        row = ClickableBox(
            on_press_cb=_open,
            bg=row_bg,
            pressed_bg=pressed_bg,
            radius=[dp(14)],
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(66),
            padding=(dp(12), dp(8), dp(12), dp(8)),
            spacing=dp(12),
        )
        av_wrap = AnchorLayout(size_hint=(None, 1), width=dp(44))
        av_wrap.add_widget(
            GroupAvatarWidget(group.id, group.display_name, size_dp=44))
        row.add_widget(av_wrap)
        last_time = group.last.time if group.last is not None else None
        row.add_widget(
            self._row_text(
                group.display_name,
                last_time,
                group_row_preview(group).replace("\n", " "),
                group.unread,
                selected,
                False,
                theme,
            ))
        return row

    def _row_text(
        self,
        title: str,
        last_time: Optional[int],
        preview: str,
        unread: int,
        selected: bool,
        highlight: bool,
        theme: ThemeColors,
    ) -> Widget:
        text_col = BoxLayout(
            orientation="vertical",
            size_hint=(1, 1),
            padding=(0, dp(4), 0, dp(4)),
            spacing=dp(2),
        )
        top_line = BoxLayout(orientation="horizontal", size_hint=(1, 0.52))
        name_lbl = Label(
            text=title,
            color=(theme.on_secondary_container
                   if selected else theme.on_surface),
            font_size=sp(15),
            bold=unread > 0 or selected,
            halign="left",
            valign="middle",
            shorten=True,
            shorten_from="right",
        )
        name_lbl.bind(size=lambda i, s: setattr(i, "text_size", s))
        top_line.add_widget(name_lbl)
        if last_time is not None:
            time_str = short_time(last_time)
            t_lbl = Label(
                text=time_str,
                color=theme.on_surface_variant,
                font_size=sp(11),
                size_hint=(None, 1),
                width=dp(max(44, len(time_str) * 7.5)),
                halign="right",
                valign="middle",
            )
            t_lbl.bind(size=lambda i, s: setattr(i, "text_size", s))
            top_line.add_widget(t_lbl)
        text_col.add_widget(top_line)

        bot_line = BoxLayout(
            orientation="horizontal", size_hint=(1, 0.48), spacing=dp(6))
        prev_lbl = Label(
            text=preview,
            color=theme.primary if highlight else theme.on_surface_variant,
            font_size=sp(12.8),
            italic=highlight,
            halign="left",
            valign="middle",
            shorten=True,
            shorten_from="right",
        )
        prev_lbl.bind(size=lambda i, s: setattr(i, "text_size", s))
        bot_line.add_widget(prev_lbl)
        if unread > 0:
            badge_wrap = AnchorLayout(
                size_hint=(None, 1),
                width=dp(max(22, 12 + len(str(unread)) * 7)),
            )
            badge_wrap.add_widget(UnreadBadge(unread, theme))
            bot_line.add_widget(badge_wrap)
        text_col.add_widget(bot_line)
        return text_col

    def _build_welcome(
        self,
        state: ClientState,
        theme: ThemeColors,
    ) -> Widget:
        wrap = AnchorLayout(anchor_x="center", anchor_y="center")
        col = BoxLayout(
            orientation="vertical",
            size_hint=(0.86, None),
            spacing=dp(12),
            padding=(dp(12), 0, dp(12), 0),
        )
        col.bind(minimum_height=col.setter("height"))

        title = auto_label(
            "No chats yet",
            color=theme.on_surface,
            font_size_sp=21,
            bold=True,
            halign="center",
        )
        subtitle = auto_label(
            "Add a friend with their Tox ID, or give them yours.",
            color=theme.on_surface_variant,
            font_size_sp=14,
            halign="center",
        )
        col.add_widget(title)
        col.add_widget(subtitle)
        col.add_widget(Widget(size_hint=(1, None), height=dp(10)))

        add_wrap = AnchorLayout(
            anchor_x="center", size_hint=(1, None), height=dp(42))
        add_wrap.add_widget(
            PillButton(
                text="Add a friend",
                bg=theme.primary,
                fg=theme.on_primary,
                height_dp=42,
                pad_x_dp=22,
                on_click=lambda: self._navigator.show(AddRoute()),
            )
        )
        col.add_widget(add_wrap)

        addr = state.profile.address
        short = f"{addr[:SHORT_KEY]}..." if addr else "..."
        copy_label = f"Copy my Tox ID ({short})"
        copy_btn = PillButton(
            text=copy_label,
            bg=theme.secondary_container,
            fg=theme.on_secondary_container,
            height_dp=38,
            pad_x_dp=18,
            disabled=not bool(addr),
        )

        def _do_copy() -> None:
            if not addr:
                return
            self._platform.copy(addr)
            copy_btn.set_text("Copied Tox ID!")
            if self._copy_reset_ev is not None:
                self._copy_reset_ev.cancel()
            self._copy_reset_ev = Clock.schedule_once(
                lambda _dt: copy_btn.set_text(copy_label), 2.0)

        copy_btn.bind(on_release=lambda *_: _do_copy())
        copy_wrap = AnchorLayout(
            anchor_x="center", size_hint=(1, None), height=dp(40))
        copy_wrap.add_widget(copy_btn)
        col.add_widget(copy_wrap)

        wrap.add_widget(col)
        return wrap

    def _build_request_card(
        self,
        req: FriendRequest,
        theme: ThemeColors,
    ) -> Widget:
        card = RoundedBox(
            bg=theme.primary_container,
            radius=[dp(14)],
            orientation="vertical",
            size_hint=(1, None),
            padding=(dp(14), dp(12), dp(14), dp(12)),
            spacing=dp(8),
        )
        card.bind(minimum_height=card.setter("height"))

        hdr = BoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(40),
            spacing=dp(10),
        )
        av_wrap = AnchorLayout(size_hint=(None, 1), width=dp(36))
        av_wrap.add_widget(
            AvatarWidget(
                key_hex=req.key,
                name=req.key,
                theme=theme,
                size_dp=36,
                ring_color=theme.primary_container,
            )
        )
        hdr.add_widget(av_wrap)

        meta = BoxLayout(orientation="vertical", size_hint=(1, 1))
        t_lbl = Label(
            text="Friend request",
            color=theme.on_primary_container,
            font_size=sp(13.5),
            bold=True,
            halign="left",
            valign="bottom",
        )
        t_lbl.bind(size=lambda i, s: setattr(i, "text_size", s))
        key_text = grouped_id(req.key[:16]) + "..."
        k_lbl = Label(
            text=key_text,
            color=with_alpha(theme.on_primary_container, 0.8),
            font_size=sp(11.5),
            halign="left",
            valign="top",
        )
        if self._mono_font:
            k_lbl.font_name = self._mono_font
        k_lbl.bind(size=lambda i, s: setattr(i, "text_size", s))
        meta.add_widget(t_lbl)
        meta.add_widget(k_lbl)
        hdr.add_widget(meta)
        card.add_widget(hdr)

        if req.message.strip():
            msg_lbl = auto_label(
                req.message,
                color=theme.on_primary_container,
                font_size_sp=13.5,
            )
            card.add_widget(msg_lbl)

        actions = BoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(36),
            spacing=dp(8),
        )
        actions.add_widget(Widget())
        def _decline(r: FriendRequest = req) -> None:
            self._client.decline(r)

        def _accept(r: FriendRequest = req) -> None:
            self._client.accept(r)

        actions.add_widget(
            PillButton(
                text="Decline",
                bg=(0, 0, 0, 0),
                fg=theme.on_primary_container,
                border=with_alpha(theme.on_primary_container, 0.4),
                height_dp=34,
                pad_x_dp=14,
                font_size_sp=12.5,
                on_click=_decline,
            )
        )
        actions.add_widget(
            PillButton(
                text="Accept",
                bg=theme.primary,
                fg=theme.on_primary,
                height_dp=34,
                pad_x_dp=16,
                font_size_sp=12.5,
                on_click=_accept,
            )
        )
        card.add_widget(actions)
        return card

    def _build_friend_row(
        self,
        friend: Friend,
        selected: bool,
        theme: ThemeColors,
    ) -> Widget:
        row_bg = theme.secondary_container if selected else theme.surface
        pressed_bg = (theme.secondary_container
                      if selected else theme.surface_container_high)

        def _open(key: str = friend.key) -> None:
            self._navigator.show(ChatRoute(key))

        row = ClickableBox(
            on_press_cb=_open,
            bg=row_bg,
            pressed_bg=pressed_bg,
            radius=[dp(14)],
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(66),
            padding=(dp(12), dp(8), dp(12), dp(8)),
            spacing=dp(12),
        )
        av_wrap = AnchorLayout(size_hint=(None, 1), width=dp(44))
        av_wrap.add_widget(
            AvatarWidget(
                key_hex=friend.key,
                name=friend.display_name,
                theme=theme,
                size_dp=44,
                connection=friend.connection,
                status=friend.status,
                picture=friend.avatar,
                ring_color=row_bg,
            )
        )
        row.add_widget(av_wrap)
        last_time = friend.last.time if friend.last is not None else None
        row.add_widget(
            self._row_text(
                friend.display_name,
                last_time,
                friend_row_preview(friend).replace("\n", " "),
                friend.unread,
                selected,
                friend.typing,
                theme,
            ))
        return row
