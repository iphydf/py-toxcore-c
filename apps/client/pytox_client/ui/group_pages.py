# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""Group info page: topic, invites, chat ID, people, founder settings, leave."""
from __future__ import annotations

from typing import Any
from typing import Callable
from typing import Optional

import pytox.toxcore.tox as core
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.modalview import ModalView
from kivy.uix.widget import Widget

from pytox_client.client import GROUP_MAX_PASSWORD_SIZE
from pytox_client.client import GROUP_MAX_TOPIC_LENGTH
from pytox_client.client import truncate_utf8
from pytox_client.model import ClientState
from pytox_client.model import Group
from pytox_client.model import Peer
from pytox_client.platform_base import Platform
from pytox_client.ui.formatting import group_subtitle
from pytox_client.ui.formatting import role_label
from pytox_client.ui.navigator import ChatsPage
from pytox_client.ui.navigator import Navigator
from pytox_client.ui.pages import PageEdits
from pytox_client.ui.pages import _PageScaffold
from pytox_client.ui.pages import _key_block
from pytox_client.ui.pages import _toggle_row
from pytox_client.ui.theme import ThemeColors
from pytox_client.ui.widgets import AvatarWidget
from pytox_client.ui.widgets import GroupAvatarWidget
from pytox_client.ui.widgets import HairlineDivider
from pytox_client.ui.widgets import PillButton
from pytox_client.ui.widgets import RoundedBox
from pytox_client.ui.widgets import SectionCard
from pytox_client.ui.widgets import StyledTextInput
from pytox_client.ui.widgets import auto_label
from pytox_client.ui.widgets import show_confirm_dialog

# The peer limit is 16 bits (1..65535).
_PEER_LIMIT_DIGITS = 5
_MAX_PEER_LIMIT = 65535


def _button_row(*buttons: Widget) -> BoxLayout:
    row = BoxLayout(
        orientation="horizontal", size_hint=(1, None), height=dp(40),
        spacing=dp(8))
    for b in buttons:
        row.add_widget(b)
    row.add_widget(Widget())
    return row


def _manageable(group: Group, peer: Peer) -> bool:
    """Founders manage everyone else; moderators manage users and observers."""
    if peer.is_self:
        return False
    if group.self_role == core.GroupRole.FOUNDER:
        return peer.role != core.GroupRole.FOUNDER
    if group.self_role == core.GroupRole.MODERATOR:
        return peer.role in (core.GroupRole.USER, core.GroupRole.OBSERVER)
    return False


def _show_peer_menu(
    group: Group,
    peer: Peer,
    client: Any,
    theme: ThemeColors,
) -> None:
    modal = ModalView(
        size_hint=(None, None),
        width=min(dp(300), max(dp(200), Window.width - dp(32))),
        background="",
        background_color=(0, 0, 0, 0),
        overlay_color=(0, 0, 0, 0.55),
    )
    card = RoundedBox(
        bg=theme.surface_container,
        radius=[dp(20)],
        orientation="vertical",
        padding=(dp(18), dp(16), dp(18), dp(12)),
        spacing=dp(6),
        size_hint=(1, None),
    )
    card.add_widget(
        auto_label(peer.display_name, theme.on_surface, font_size_sp=17,
                   bold=True))
    if group.self_role == core.GroupRole.FOUNDER:
        roles = [
            (core.GroupRole.MODERATOR, "Make moderator"),
            (core.GroupRole.USER, "Make user"),
            (core.GroupRole.OBSERVER, "Only let them read"),
        ]
    else:
        roles = [
            (core.GroupRole.USER, "Let them write"),
            (core.GroupRole.OBSERVER, "Only let them read"),
        ]

    def _action(fn: Callable[[], None]) -> Callable[[], None]:
        def _run() -> None:
            modal.dismiss()
            fn()

        return _run

    def _set_role(role: core.GroupRole) -> Callable[[], None]:
        return lambda: client.set_role(group.id, peer.key, role)

    for role, label in roles:
        if role == peer.role:
            continue
        card.add_widget(
            _button_row(
                PillButton(
                    text=label, bg=(0, 0, 0, 0), fg=theme.primary,
                    height_dp=36, pad_x_dp=8,
                    on_click=_action(_set_role(role)))))
    card.add_widget(
        _button_row(
            PillButton(
                text="Remove from the group", bg=(0, 0, 0, 0), fg=theme.error,
                height_dp=36, pad_x_dp=8,
                on_click=_action(lambda: client.kick(group.id, peer.key)))))
    card.add_widget(
        _button_row(
            Widget(),
            PillButton(
                text="Cancel", bg=(0, 0, 0, 0), fg=theme.on_surface_variant,
                height_dp=34, pad_x_dp=12, on_click=modal.dismiss)))
    card.bind(minimum_height=card.setter("height"))
    card.bind(height=lambda _i, h: setattr(modal, "height", h))
    modal.add_widget(card)
    modal.open()


def _peer_row(
    group: Group,
    peer: Peer,
    client: Any,
    theme: ThemeColors,
) -> BoxLayout:
    row = BoxLayout(
        orientation="horizontal", size_hint=(1, None), height=dp(52),
        spacing=dp(12))
    av_wrap = AnchorLayout(size_hint=(None, 1), width=dp(36))
    av_wrap.add_widget(
        AvatarWidget(key_hex=peer.key, name=peer.display_name, theme=theme,
                     size_dp=36))
    row.add_widget(av_wrap)
    col = BoxLayout(orientation="vertical", size_hint=(1, None))
    col.bind(minimum_height=col.setter("height"))
    name = f"{peer.display_name} (you)" if peer.is_self else peer.display_name
    col.add_widget(auto_label(name, theme.on_surface, font_size_sp=14.5))
    label = role_label(peer.role)
    if label:
        col.add_widget(auto_label(label, theme.primary, font_size_sp=12))
    col_wrap = AnchorLayout(anchor_y="center", size_hint=(1, 1))
    col_wrap.add_widget(col)
    row.add_widget(col_wrap)
    if _manageable(group, peer):
        manage = PillButton(
            text="Manage", bg=theme.secondary_container,
            fg=theme.on_secondary_container, height_dp=32, pad_x_dp=12,
            font_size_sp=12.5,
            on_click=lambda: _show_peer_menu(group, peer, client, theme))
        m_wrap = AnchorLayout(size_hint=(None, 1), width=manage.width)
        m_wrap.add_widget(manage)
        row.add_widget(m_wrap)
    return row


def build_group_info_page(
    group_id: str,
    state: ClientState,
    client: Any,
    platform: Platform,
    navigator: Navigator,
    theme: ThemeColors,
    invited: dict[str, set[str]],
    edits: PageEdits,
    mono_font: Optional[str] = None,
) -> BoxLayout:
    """Everything about a group, and what we're allowed to change in it."""
    group = next((g for g in state.groups if g.id == group_id), None)
    page = _PageScaffold(
        group.display_name if group is not None else "Group", navigator, theme,
        edits)
    if group is None:
        return page

    header = BoxLayout(
        orientation="vertical", size_hint=(1, None), spacing=dp(6))
    header.bind(minimum_height=header.setter("height"))
    av_wrap = AnchorLayout(size_hint=(1, None), height=dp(96))
    av_wrap.add_widget(
        GroupAvatarWidget(group.id, group.display_name, size_dp=96))
    header.add_widget(av_wrap)
    header.add_widget(
        auto_label(group.display_name, theme.on_surface, font_size_sp=21,
                   bold=True, halign="center"))
    kind = ("Private" if group.privacy == core.GroupPrivacyState.PRIVATE
            else "Public")
    header.add_widget(
        auto_label(f"{kind} group - {group_subtitle(group)}",
                   theme.on_surface_variant, font_size_sp=13.5,
                   halign="center"))
    page.body.add_widget(header)

    # Topic.
    sec_topic = SectionCard("Topic", theme)
    if not group.can_set_topic:
        sec_topic.add_widget(
            auto_label(group.topic or "No topic.", theme.on_surface,
                       font_size_sp=14))
    else:
        topic_in = StyledTextInput(
            theme, hint="Topic", multiline=True, height_dp=68)
        set_btn = PillButton(
            text="Set the topic", bg=theme.primary, fg=theme.on_primary,
            height_dp=38, pad_x_dp=18, disabled=True)

        def _on_topic(_inst: Any, text: str) -> None:
            clamped = truncate_utf8(text, GROUP_MAX_TOPIC_LENGTH)
            if clamped != text:
                topic_in.field.text = clamped
                return
            set_btn.disabled = text == group.topic or not group.connected

        edits.field("topic", topic_in.field, group.topic)
        topic_in.field.bind(text=_on_topic)
        _on_topic(None, topic_in.field.text)
        set_btn.bind(on_release=lambda *_: client.set_topic(
            group.id, topic_in.field.text))
        sec_topic.add_widget(topic_in)
        sec_topic.add_widget(_button_row(set_btn))
    page.body.add_widget(sec_topic)

    # Invite friends: only online friends can get an invite.
    sec_inv = SectionCard("Invite friends", theme)
    online = [f for f in state.friends if f.online]
    if not online:
        sec_inv.add_widget(
            auto_label("Friends who are online show up here.",
                       theme.on_surface_variant, font_size_sp=13.5))
    sent_to = invited.setdefault(group.id, set())
    for friend in online:
        row = BoxLayout(
            orientation="horizontal", size_hint=(1, None), height=dp(48),
            spacing=dp(12))
        av = AnchorLayout(size_hint=(None, 1), width=dp(36))
        av.add_widget(
            AvatarWidget(key_hex=friend.key, name=friend.display_name,
                         theme=theme, size_dp=36, picture=friend.avatar))
        row.add_widget(av)
        name_wrap = AnchorLayout(anchor_y="center", size_hint=(1, 1))
        name_wrap.add_widget(
            auto_label(friend.display_name, theme.on_surface,
                       font_size_sp=14.5))
        row.add_widget(name_wrap)
        was_sent = friend.key in sent_to
        btn = PillButton(
            text="Invited" if was_sent else "Invite",
            bg=theme.secondary_container, fg=theme.on_secondary_container,
            height_dp=34, pad_x_dp=14, font_size_sp=12.5,
            disabled=was_sent or not group.connected)

        b_wrap = AnchorLayout(size_hint=(None, 1), width=btn.width)
        b_wrap.add_widget(btn)

        def _invite(
            key: str = friend.key,
            b: PillButton = btn,
            wrap: AnchorLayout = b_wrap,
        ) -> None:
            client.invite_friend(group.id, key)
            sent_to.add(key)
            b.set_text("Invited")
            wrap.width = b.width
            b.disabled = True

        btn.bind(on_release=lambda *_a, f=_invite: f())
        row.add_widget(b_wrap)
        sec_inv.add_widget(row)
    page.body.add_widget(sec_inv)

    # Chat ID for public groups.
    if group.privacy == core.GroupPrivacyState.PUBLIC:
        sec_id = SectionCard("Chat ID", theme)
        sec_id.add_widget(
            auto_label("Anyone can join with this.", theme.on_surface_variant,
                       font_size_sp=13.5))
        _key_block(sec_id, group.id, platform, theme, mono_font=mono_font)
        page.body.add_widget(sec_id)

    # People.
    sec_people = SectionCard("People", theme)
    for i, peer in enumerate(group.peers):
        if i > 0:
            sec_people.add_widget(HairlineDivider(theme.outline_variant))
        sec_people.add_widget(_peer_row(group, peer, client, theme))
    page.body.add_widget(sec_people)

    # Founder settings.
    if group.self_role == core.GroupRole.FOUNDER:
        sec_set = SectionCard("Settings", theme)
        sec_set.add_widget(
            _toggle_row(
                "Private", "Only invited friends can join.",
                group.privacy == core.GroupPrivacyState.PRIVATE, theme,
                lambda on: client.set_group_privacy(group.id, on)))
        sec_set.add_widget(HairlineDivider(theme.outline_variant))
        sec_set.add_widget(
            _toggle_row(
                "Lock the topic", "Only moderators can change it.",
                group.topic_locked, theme,
                lambda on: client.set_topic_lock(group.id, on)))
        sec_set.add_widget(HairlineDivider(theme.outline_variant))
        sec_set.add_widget(
            auto_label("Password: empty for none", theme.on_surface_variant,
                       font_size_sp=12))
        pw_in = StyledTextInput(theme, hint="No password", suggestions=False)
        sec_set.add_widget(pw_in)
        sec_set.add_widget(
            auto_label("Most people at once", theme.on_surface_variant,
                       font_size_sp=12))
        limit_in = StyledTextInput(
            theme, hint="Peer limit", input_type="number")
        sec_set.add_widget(limit_in)
        save_btn = PillButton(
            text="Save", bg=theme.primary, fg=theme.on_primary, height_dp=38,
            pad_x_dp=20, disabled=True)

        def _changed(*_args: Any) -> None:
            pw = truncate_utf8(pw_in.field.text, GROUP_MAX_PASSWORD_SIZE)
            if pw != pw_in.field.text:
                pw_in.field.text = pw
                return
            digits = "".join(
                ch for ch in limit_in.field.text if "0" <= ch <= "9")
            digits = digits[:_PEER_LIMIT_DIGITS]
            if digits != limit_in.field.text:
                limit_in.field.text = digits
                return
            limit_val = int(digits) if digits else None
            limit_changed = (
                limit_val is not None
                and 1 <= limit_val <= _MAX_PEER_LIMIT
                and limit_val != group.peer_limit
            )
            limit_invalid = (
                bool(digits)
                and (limit_val is None or not 1 <= limit_val <= _MAX_PEER_LIMIT)
            )
            pw_changed = pw != group.password
            save_btn.disabled = (
                not group.connected
                or limit_invalid
                or (not pw_changed and not limit_changed)
            )

        def _save() -> None:
            if pw_in.field.text != group.password:
                client.set_group_password(group.id, pw_in.field.text)
            text = limit_in.field.text
            if text and all("0" <= ch <= "9" for ch in text):
                limit = int(text)
                if 1 <= limit <= _MAX_PEER_LIMIT and limit != group.peer_limit:
                    client.set_peer_limit(group.id, limit)

        edits.field("password", pw_in.field, group.password)
        edits.field("peer limit", limit_in.field, str(group.peer_limit))
        pw_in.field.bind(text=_changed)
        limit_in.field.bind(text=_changed)
        _changed()
        save_btn.bind(on_release=lambda *_: _save())
        sec_set.add_widget(_button_row(save_btn))
        page.body.add_widget(sec_set)

    # Leave.
    sec_leave = SectionCard("Leave", theme)

    def _confirm_leave() -> None:
        client.leave_group(group.id)
        navigator.show(ChatsPage())

    def _ask_leave() -> None:
        show_confirm_dialog(
            title=f"Leave {group.display_name}?",
            body="The chat goes from this device too.",
            confirm_label="Leave",
            theme=theme,
            danger=True,
            on_confirm=_confirm_leave,
        )

    sec_leave.add_widget(
        _button_row(
            PillButton(
                text="Leave the group", bg=(0, 0, 0, 0), fg=theme.error,
                border=theme.error, height_dp=38, pad_x_dp=18,
                on_click=_ask_leave)))
    page.body.add_widget(sec_leave)
    return page
