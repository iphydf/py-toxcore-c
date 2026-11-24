# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""Secondary pages: Profile, Add friend, Settings, Friend info."""
from __future__ import annotations

import threading
from dataclasses import replace
from typing import Any
from typing import Callable
from typing import Optional

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.metrics import sp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

import pytox.toxcore.tox as core

from pytox_client.client import GROUP_MAX_GROUP_NAME_LENGTH
from pytox_client.client import GROUP_MAX_PASSWORD_SIZE
from pytox_client.client import truncate_utf8
from pytox_client.model import ClientState
from pytox_client.model import PickedFile
from pytox_client.model import SHORT_KEY
from pytox_client.platform_base import Platform
from pytox_client.ui.formatting import grouped_id
from pytox_client.ui.formatting import presence_text
from pytox_client.ui.formatting import self_connection_text
from pytox_client.ui.navigator import AddRoute
from pytox_client.ui.navigator import ChatsPage
from pytox_client.ui.navigator import Navigator
from pytox_client.ui.theme import ThemeColors
from pytox_client.ui.widgets import AvatarWidget
from pytox_client.ui.widgets import ClickableBox
from pytox_client.ui.widgets import HairlineDivider
from pytox_client.ui.widgets import IconButton
from pytox_client.ui.widgets import PillButton
from pytox_client.ui.widgets import QrCodeWidget
from pytox_client.ui.widgets import SectionCard
from pytox_client.ui.widgets import SegmentedRow
from pytox_client.ui.widgets import StyledTextInput
from pytox_client.ui.widgets import ToggleSwitch
from pytox_client.ui.widgets import TopBar
from pytox_client.ui.widgets import auto_label
from pytox_client.ui.widgets import set_bg_color
from pytox_client.ui.widgets import show_confirm_dialog


_MAX_AVATAR_UPLOAD_BYTES = 32 << 20


class PageEdits:
    """What someone did on a page, so the page built again keeps it.

    Pages are built again when what they show changes, such as the
    connection, a group's people, or the window's size: the text typed,
    the field being typed in and the scroll position stay.
    """

    def __init__(self) -> None:
        self._texts: dict[str, str] = {}
        self._flags: dict[str, bool] = {}
        self._focused: Optional[str] = None
        self._focused_widget: Optional[TextInput] = None
        self._cursor: tuple[int, int] = (0, 0)
        self.scroll_y = 1.0

    def flag(self, name: str, default: bool = False) -> bool:
        return self._flags.get(name, default)

    def set_flag(self, name: str, value: bool) -> None:
        self._flags[name] = value

    def field(self, name: str, field: TextInput, value: str) -> None:
        """Show ``value`` in ``field``, or what was typed in it before."""
        field.text = self._texts.get(name, value)

        def _typed(_inst: Any, text: str) -> None:
            self._texts[name] = text

        def _focus(inst: Any, focused: bool) -> None:
            if focused:
                self._focused = name
                self._focused_widget = inst
            elif self._focused == name and self._focused_widget is inst:
                self._focused = None
                self._focused_widget = None

        def _moved(inst: Any, cursor: tuple[int, int]) -> None:
            if self._focused == name and self._focused_widget is inst:
                self._cursor = cursor

        field.bind(text=_typed, focus=_focus, cursor=_moved)
        if self._focused == name:
            self._focused_widget = field
            cursor = self._cursor

            def _refocus(_dt: float) -> None:
                if field.parent is not None:
                    field.focus = True
                    field.cursor = cursor

            Clock.schedule_once(_refocus, 0)


class _PageScaffold(BoxLayout):  # type: ignore[misc]
    """Top bar with back arrow and title + centered scrollable column."""

    def __init__(
        self,
        title: str,
        navigator: Navigator,
        theme: ThemeColors,
        edits: Optional[PageEdits] = None,
    ) -> None:
        super().__init__(orientation="vertical")
        set_bg_color(self, theme.surface)

        self.topbar = TopBar(theme)
        back_wrap = AnchorLayout(size_hint=(None, 1), width=dp(42))
        def _go_back() -> None:
            navigator.back()

        back_btn = IconButton(
            "back",
            fg=theme.on_surface_variant,
            on_click=_go_back,
            size_dp=40,
            icon_dp=20,
        )
        back_wrap.add_widget(back_btn)
        self.title_lbl = Label(
            text=title,
            color=theme.on_surface,
            font_size=sp(18),
            bold=True,
            halign="left",
            valign="middle",
            shorten=True,
        )
        self.title_lbl.bind(size=lambda i, s: setattr(i, "text_size", s))
        self.topbar.row.add_widget(back_wrap)
        self.topbar.row.add_widget(self.title_lbl)
        self.add_widget(self.topbar)

        scroll = ScrollView(do_scroll_x=False, bar_width=dp(5))
        outer = AnchorLayout(
            anchor_x="center",
            anchor_y="top",
            size_hint=(1, None),
        )
        self.body = BoxLayout(
            orientation="vertical",
            size_hint=(None, None),
            padding=(dp(20), dp(18), dp(20), dp(28)),
            spacing=dp(16),
        )
        def _sync_height(_inst: Any, height: float) -> None:
            self.body.height = height
            outer.height = height

        self.body.bind(minimum_height=_sync_height)

        def _fit_width(_inst: Any, width: float) -> None:
            self.body.width = min(dp(600), width)

        scroll.bind(width=_fit_width)
        self.body.width = dp(520)
        outer.add_widget(self.body)
        scroll.add_widget(outer)
        self.add_widget(scroll)
        if edits is not None:
            scroll.scroll_y = edits.scroll_y
            scroll.bind(scroll_y=lambda _i, y: setattr(edits, "scroll_y", y))


def _key_block(
    parent: BoxLayout,
    value: str,
    platform: Platform,
    theme: ThemeColors,
    mono_font: Optional[str] = None,
) -> None:
    grouped = grouped_id(value) if value else "..."
    lbl = auto_label(
        grouped,
        color=theme.on_surface,
        font_size_sp=13,
        font_name=mono_font,
    )
    parent.add_widget(lbl)

    row = BoxLayout(
        orientation="horizontal",
        size_hint=(1, None),
        height=dp(38),
    )
    btn = PillButton(
        text="Copy",
        bg=theme.secondary_container,
        fg=theme.on_secondary_container,
        height_dp=36,
        pad_x_dp=18,
        disabled=not bool(value),
    )

    def _copy() -> None:
        if not value:
            return
        platform.copy(value)
        btn.set_text("Copied!")
        Clock.schedule_once(lambda _dt: btn.set_text("Copy"), 2.0)

    btn.bind(on_release=lambda *_: _copy())
    row.add_widget(btn)
    row.add_widget(Widget())
    parent.add_widget(row)


def build_profile_page(
    state: ClientState,
    client: Any,
    platform: Platform,
    navigator: Navigator,
    theme: ThemeColors,
    edits: PageEdits,
    mono_font: Optional[str] = None,
    on_delete: Optional[Callable[[], None]] = None,
) -> BoxLayout:
    """Edit own avatar, name, status message, online status, and share QR code.

    ``on_delete`` deletes the profile, where that's allowed.
    """
    profile = state.profile
    page = _PageScaffold("Me", navigator, theme, edits)

    # Header avatar + buttons
    header = BoxLayout(
        orientation="vertical",
        size_hint=(1, None),
        spacing=dp(8),
    )
    header.bind(minimum_height=header.setter("height"))

    problem_lbl = auto_label(
        "", color=theme.error, font_size_sp=12.5, halign="center")
    problem_lbl.height = 0
    problem_lbl.opacity = 0.0

    def _pick_picture() -> None:
        def _got(picked: PickedFile) -> None:
            def _load() -> None:
                err: Optional[str] = None
                try:
                    with picked.open_stream() as fh:
                        raw = fh.read(_MAX_AVATAR_UPLOAD_BYTES + 1)
                    if len(raw) > _MAX_AVATAR_UPLOAD_BYTES:
                        err = "That picture is too large."
                    else:
                        ok = client.set_avatar(raw).result(timeout=30.0)
                        if not ok:
                            err = "That isn't a picture PyTox can read."
                except Exception:  # noqa: BLE001
                    err = "Could not load that picture."

                def _report(_dt: float) -> None:
                    _set_error(problem_lbl, err)

                Clock.schedule_once(_report, 0)

            threading.Thread(target=_load, daemon=True).start()

        platform.pick_file(images=True, on_picked=_got)

    av_btn = ClickableBox(
        on_press_cb=_pick_picture,
        size_hint=(None, None),
        size=(dp(96), dp(96)),
        radius=[dp(48)],
    )
    av_btn.add_widget(
        AvatarWidget(
            key_hex=profile.address,
            name=profile.name or "Me",
            theme=theme,
            size_dp=96,
            connection=profile.connection,
            status=profile.status,
            picture=profile.avatar,
            ring_color=theme.surface,
        )
    )
    av_wrap = AnchorLayout(size_hint=(1, None), height=dp(96))
    av_wrap.add_widget(av_btn)
    header.add_widget(av_wrap)

    btn_row_wrap = AnchorLayout(size_hint=(1, None), height=dp(36))
    btn_row = BoxLayout(
        orientation="horizontal",
        size_hint=(None, 1),
        spacing=dp(8),
    )
    btn_row.bind(minimum_width=btn_row.setter("width"))
    btn_row.add_widget(
        PillButton(
            text="Change picture" if profile.avatar else "Add a picture",
            bg=(0, 0, 0, 0),
            fg=theme.primary,
            height_dp=34,
            pad_x_dp=12,
            on_click=_pick_picture,
        )
    )
    if profile.avatar is not None:
        btn_row.add_widget(
            PillButton(
                text="Remove",
                bg=(0, 0, 0, 0),
                fg=theme.error,
                height_dp=34,
                pad_x_dp=12,
                on_click=lambda: client.set_avatar(None),
            )
        )
    btn_row_wrap.add_widget(btn_row)
    header.add_widget(btn_row_wrap)
    header.add_widget(problem_lbl)

    conn_lbl = auto_label(
        self_connection_text(profile.connection, long=True),
        color=theme.on_surface_variant,
        font_size_sp=13,
        halign="center",
    )
    header.add_widget(conn_lbl)
    page.body.add_widget(header)

    # Name and status section
    sec_info = SectionCard("Name and status", theme)
    sec_info.add_widget(
        auto_label("Name", color=theme.on_surface_variant, font_size_sp=12))
    name_in = StyledTextInput(theme, hint="Your display name", height_dp=42)
    sec_info.add_widget(name_in)

    sec_info.add_widget(
        auto_label("Status message", color=theme.on_surface_variant,
                   font_size_sp=12))
    status_in = StyledTextInput(
        theme, hint="What are you up to?", multiline=True, height_dp=68)
    sec_info.add_widget(status_in)

    save_row = BoxLayout(
        orientation="horizontal", size_hint=(1, None), height=dp(40))
    save_btn = PillButton(
        text="Save",
        bg=theme.primary,
        fg=theme.on_primary,
        height_dp=38,
        pad_x_dp=22,
        disabled=True,
    )

    def _clamp_bytes(field: Any, limit: int) -> None:
        val = truncate_utf8(field.text, limit)
        if val != field.text:
            field.text = val

    def _sync_save(*_args: Any) -> None:
        _clamp_bytes(name_in.field, core.MAX_NAME_LENGTH)
        _clamp_bytes(status_in.field, core.MAX_STATUS_MESSAGE_LENGTH)
        dirty = (name_in.field.text != profile.name
                 or status_in.field.text != profile.status_message)
        save_btn.disabled = not dirty

    def _on_save() -> None:
        n_val = name_in.field.text
        s_val = status_in.field.text
        if n_val != profile.name:
            client.set_name(n_val)
        if s_val != profile.status_message:
            client.set_status_message(s_val)
        save_btn.disabled = True

    edits.field("name", name_in.field, profile.name)
    edits.field("status", status_in.field, profile.status_message)
    name_in.field.bind(text=_sync_save)
    status_in.field.bind(text=_sync_save)
    _sync_save()
    save_btn.bind(on_release=lambda *_: _on_save())
    save_row.add_widget(save_btn)
    save_row.add_widget(Widget())
    sec_info.add_widget(save_row)

    statuses = (
        (core.UserStatus.NONE, "Online"),
        (core.UserStatus.AWAY, "Away"),
        (core.UserStatus.BUSY, "Busy"),
    )
    seg = SegmentedRow(
        options=statuses,
        selected=profile.status,
        theme=theme,
        on_select=lambda st: client.set_status(st),
    )
    sec_info.add_widget(seg)
    page.body.add_widget(sec_info)

    # My Tox ID + QR code
    sec_id = SectionCard("My Tox ID", theme)
    sec_id.add_widget(
        auto_label(
            "Friends add you with this. It's safe to share.",
            color=theme.on_surface_variant,
            font_size_sp=13,
        )
    )
    if profile.address:
        qr_wrap = AnchorLayout(size_hint=(1, None), height=dp(212))
        qr_wrap.add_widget(QrCodeWidget(f"tox:{profile.address}", size_dp=204))
        sec_id.add_widget(qr_wrap)
    _key_block(sec_id, profile.address, platform, theme, mono_font=mono_font)
    page.body.add_widget(sec_id)

    if on_delete is not None:
        sec_delete = SectionCard("Delete", theme)
        sec_delete.add_widget(
            auto_label(
                "Deletes this profile, its Tox ID and its chats from this "
                "device. Your other profiles stay.",
                color=theme.on_surface_variant,
                font_size_sp=13.5,
            )
        )
        delete_row = BoxLayout(
            orientation="horizontal", size_hint=(1, None), height=dp(40))

        def _ask_delete() -> None:
            show_confirm_dialog(
                title=f"Delete {profile.name or 'this profile'}?",
                body=("Its friends can't reach this Tox ID again. "
                      "Its chats go too."),
                confirm_label="Delete",
                theme=theme,
                danger=True,
                on_confirm=on_delete,
            )

        delete_row.add_widget(
            PillButton(
                text="Delete this profile",
                bg=(0, 0, 0, 0),
                fg=theme.error,
                border=theme.error,
                height_dp=38,
                pad_x_dp=18,
                on_click=_ask_delete,
            )
        )
        delete_row.add_widget(Widget())
        sec_delete.add_widget(delete_row)
        page.body.add_widget(sec_delete)

    return page


def build_add_page(
    state: ClientState,
    client: Any,
    platform: Platform,
    navigator: Navigator,
    theme: ThemeColors,
    edits: PageEdits,
    mono_font: Optional[str] = None,
) -> BoxLayout:
    """Add a friend by Tox ID, start a group, or join a public group."""
    page = _PageScaffold("Add", navigator, theme, edits)

    sec_add = SectionCard("Their Tox ID", theme)
    sec_add.add_widget(
        auto_label("Tox ID", color=theme.on_surface_variant, font_size_sp=12))
    id_in = StyledTextInput(
        theme, hint="76-character hex ID (or tox:...)",
        font_name=mono_font, multiline=True, height_dp=68,
        suggestions=False,
    )
    sec_add.add_widget(id_in)

    err_lbl = auto_label("", color=theme.error, font_size_sp=12.5)
    err_lbl.height = 0
    err_lbl.opacity = 0.0
    sec_add.add_widget(err_lbl)

    sec_add.add_widget(
        auto_label(
            "Message (optional)",
            color=theme.on_surface_variant,
            font_size_sp=12,
        )
    )
    msg_in = StyledTextInput(
        theme,
        hint="Hi, I'd like to add you as a friend.",
        multiline=True,
        height_dp=68,
    )
    sec_add.add_widget(msg_in)

    send_row = BoxLayout(
        orientation="horizontal", size_hint=(1, None), height=dp(42))
    send_btn = PillButton(
        text="Send friend request",
        bg=theme.primary,
        fg=theme.on_primary,
        height_dp=40,
        pad_x_dp=20,
        disabled=True,
    )

    def _on_id_change(_inst: Any, text: str) -> None:
        stripped = "".join(text.split())
        if stripped != text:
            id_in.field.text = stripped
            return
        err_lbl.text = ""
        err_lbl.opacity = 0.0
        err_lbl.height = 0
        id_in.set_theme(theme, error=False)
        send_btn.disabled = not bool(stripped)

    def _on_msg_change(_inst: Any, text: str) -> None:
        val = truncate_utf8(text, core.MAX_FRIEND_REQUEST_LENGTH)
        if val != text:
            msg_in.field.text = val

    def _submit() -> None:
        tox_id = id_in.field.text.strip()
        if not tox_id:
            return
        send_btn.disabled = True
        msg_text = msg_in.field.text
        fut = client.add_friend(tox_id, msg_text)

        def _done(f: Any) -> None:
            try:
                problem: Optional[str] = f.result()
            except Exception as exc:  # noqa: BLE001
                problem = str(exc)

            def _apply(_dt: float) -> None:
                if problem is None:
                    if isinstance(navigator.current, AddRoute):
                        navigator.show(ChatsPage())
                else:
                    _set_error(err_lbl, problem)
                    id_in.set_theme(theme, error=True)
                    send_btn.disabled = False

            Clock.schedule_once(_apply, 0)

        fut.add_done_callback(_done)

    edits.field("tox id", id_in.field, "")
    edits.field("request", msg_in.field, "")
    id_in.field.bind(text=_on_id_change)
    msg_in.field.bind(text=_on_msg_change)
    send_btn.disabled = not id_in.field.text
    send_btn.bind(on_release=lambda *_: _submit())
    send_row.add_widget(send_btn)
    send_row.add_widget(Widget())
    sec_add.add_widget(send_row)
    page.body.add_widget(sec_add)

    sec_mine = SectionCard("Or give them yours", theme)
    _key_block(sec_mine, state.profile.address, platform, theme,
               mono_font=mono_font)
    page.body.add_widget(sec_mine)
    page.body.add_widget(_new_group_section(client, navigator, theme, edits))
    page.body.add_widget(
        _join_group_section(client, navigator, theme, edits, mono_font))
    return page


def _error_label(theme: ThemeColors) -> Label:
    lbl = auto_label("", color=theme.error, font_size_sp=12.5)
    lbl.height = 0
    lbl.opacity = 0.0
    return lbl


def _set_error(lbl: Label, problem: Optional[str]) -> None:
    if problem is None:
        lbl.text = ""
        lbl.opacity = 0.0
        lbl.height = 0
        return
    lbl.text = problem
    lbl.opacity = 1.0
    lbl.text_size = (lbl.width, None)
    lbl.texture_update()
    lbl.height = max(dp(20), lbl.texture_size[1] + dp(4))


def _on_result(
    fut: Any,
    err_lbl: Label,
    button: PillButton,
    navigator: Navigator,
) -> None:
    """Show a client call's error, or go back to the chat list on success."""

    def _done(f: Any) -> None:
        try:
            problem: Optional[str] = f.result()
        except Exception as exc:  # noqa: BLE001
            problem = str(exc)

        def _apply(_dt: float) -> None:
            if problem is None:
                if isinstance(navigator.current, AddRoute):
                    navigator.show(ChatsPage())
            else:
                _set_error(err_lbl, problem)
                button.disabled = False

        Clock.schedule_once(_apply, 0)

    fut.add_done_callback(_done)


def _new_group_section(
    client: Any,
    navigator: Navigator,
    theme: ThemeColors,
    edits: PageEdits,
) -> SectionCard:
    sec = SectionCard("Start a group", theme)
    sec.add_widget(
        auto_label("Group name", color=theme.on_surface_variant,
                   font_size_sp=12))
    name_in = StyledTextInput(theme, hint="Group name")
    sec.add_widget(name_in)
    err_lbl = _error_label(theme)
    sec.add_widget(err_lbl)
    sec.add_widget(
        _toggle_row(
            "Private",
            "Only people you invite can join. Public groups can be joined "
            "with their chat ID.",
            edits.flag("group private", False),
            theme,
            lambda on: edits.set_flag("group private", on),
        ))
    btn = PillButton(
        text="Start the group", bg=theme.primary, fg=theme.on_primary,
        height_dp=40, pad_x_dp=20, disabled=True)

    def _on_name(_inst: Any, text: str) -> None:
        clamped = truncate_utf8(text, GROUP_MAX_GROUP_NAME_LENGTH)
        if clamped != text:
            name_in.field.text = clamped
            return
        _set_error(err_lbl, None)
        btn.disabled = not text.strip()

    def _submit() -> None:
        btn.disabled = True
        fut = client.create_group(
            name_in.field.text.strip(), edits.flag("group private", False))
        _on_result(fut, err_lbl, btn, navigator)

    edits.field("group name", name_in.field, "")
    name_in.field.bind(text=_on_name)
    btn.disabled = not name_in.field.text.strip()
    btn.bind(on_release=lambda *_: _submit())
    row = BoxLayout(orientation="horizontal", size_hint=(1, None),
                    height=dp(42))
    row.add_widget(btn)
    row.add_widget(Widget())
    sec.add_widget(row)
    return sec


def _join_group_section(
    client: Any,
    navigator: Navigator,
    theme: ThemeColors,
    edits: PageEdits,
    mono_font: Optional[str],
) -> SectionCard:
    sec = SectionCard("Join a public group", theme)
    sec.add_widget(
        auto_label("Chat ID", color=theme.on_surface_variant, font_size_sp=12))
    id_in = StyledTextInput(
        theme, hint="64-character hex chat ID", font_name=mono_font,
        multiline=True, height_dp=60, suggestions=False)
    sec.add_widget(id_in)
    err_lbl = _error_label(theme)
    sec.add_widget(err_lbl)
    sec.add_widget(
        auto_label("Password, if it has one", color=theme.on_surface_variant,
                   font_size_sp=12))
    pw_in = StyledTextInput(theme, hint="Password", suggestions=False)
    sec.add_widget(pw_in)
    btn = PillButton(
        text="Join", bg=theme.primary, fg=theme.on_primary, height_dp=40,
        pad_x_dp=22, disabled=True)

    def _on_id(_inst: Any, text: str) -> None:
        stripped = "".join(text.split())
        if stripped != text:
            id_in.field.text = stripped
            return
        _set_error(err_lbl, None)
        id_in.set_theme(theme, error=False)
        btn.disabled = not stripped

    def _on_pw(_inst: Any, text: str) -> None:
        clamped = truncate_utf8(text, GROUP_MAX_PASSWORD_SIZE)
        if clamped != text:
            pw_in.field.text = clamped

    def _submit() -> None:
        btn.disabled = True
        fut = client.join_group(id_in.field.text, pw_in.field.text)
        _on_result(fut, err_lbl, btn, navigator)

    edits.field("chat id", id_in.field, "")
    edits.field("join password", pw_in.field, "")
    id_in.field.bind(text=_on_id)
    pw_in.field.bind(text=_on_pw)
    btn.disabled = not id_in.field.text
    btn.bind(on_release=lambda *_: _submit())
    row = BoxLayout(orientation="horizontal", size_hint=(1, None),
                    height=dp(42))
    row.add_widget(btn)
    row.add_widget(Widget())
    sec.add_widget(row)
    return sec


def _toggle_row(
    title: str,
    description: str,
    checked: bool,
    theme: ThemeColors,
    on_change: Callable[[bool], None],
) -> BoxLayout:
    row = BoxLayout(
        orientation="horizontal",
        size_hint=(1, None),
        spacing=dp(12),
    )
    txt_col = BoxLayout(
        orientation="vertical", size_hint=(1, None), spacing=dp(2))
    txt_col.bind(minimum_height=txt_col.setter("height"))
    txt_col.add_widget(
        auto_label(title, color=theme.on_surface, font_size_sp=15, bold=True))
    txt_col.add_widget(
        auto_label(description, color=theme.on_surface_variant,
                   font_size_sp=12.5))
    sw = ToggleSwitch(checked=checked, theme=theme, on_toggle=on_change)
    sw_wrap = AnchorLayout(
        anchor_x="right", anchor_y="center", size_hint=(None, 1), width=dp(52))
    sw_wrap.add_widget(sw)
    row.add_widget(txt_col)
    row.add_widget(sw_wrap)
    txt_col.bind(height=lambda _i, h: setattr(row, "height", max(dp(44), h)))
    row.height = dp(52)
    return row


def build_settings_page(
    state: ClientState,
    client: Any,
    platform: Platform,
    navigator: Navigator,
    theme: ThemeColors,
    set_stay_connected: Callable[[bool], None],
) -> BoxLayout:
    """Network toggles, appearance theme picker, and Android service toggle.

    The network is the shown profile's; staying connected is every profile's.
    """
    s = state.settings
    page = _PageScaffold("Settings", navigator, theme)

    sec_net = SectionCard("Network", theme)
    sec_net.add_widget(
        auto_label(
            "Changes reconnect to the Tox network.",
            color=theme.on_surface_variant,
            font_size_sp=13,
        )
    )
    sec_net.add_widget(
        _toggle_row(
            "UDP",
            "Faster. Off: all traffic goes through TCP relays.",
            s.udp,
            theme,
            lambda on: client.update_settings(
                replace(client.state.settings, udp=on)),
        )
    )
    sec_net.add_widget(HairlineDivider(theme.outline_variant))
    sec_net.add_widget(
        _toggle_row(
            "IPv6",
            "Also connect over IPv6.",
            s.ipv6,
            theme,
            lambda on: client.update_settings(
                replace(client.state.settings, ipv6=on)),
        )
    )
    sec_net.add_widget(HairlineDivider(theme.outline_variant))
    sec_net.add_widget(
        _toggle_row(
            "Local discovery",
            "Find Tox users on the same network directly.",
            s.local_discovery,
            theme,
            lambda on: client.update_settings(
                replace(client.state.settings, local_discovery=on)),
        )
    )
    page.body.add_widget(sec_net)

    sec_theme = SectionCard("Appearance", theme)
    sec_theme.add_widget(
        SegmentedRow(
            options=(
                ("system", "System"),
                ("light", "Light"),
                ("dark", "Dark"),
            ),
            selected=s.theme,
            theme=theme,
            on_select=lambda val: client.update_settings(
                replace(client.state.settings, theme=val)),
        )
    )
    page.body.add_widget(sec_theme)

    if platform.can_stay_connected:
        sec_phone = SectionCard("Phone", theme)
        sec_phone.add_widget(
            _toggle_row(
                "Stay connected",
                "Messages keep arriving for every profile while PyTox is "
                "closed. Shows a notification while connected.",
                s.stay_connected,
                theme,
                set_stay_connected,
            )
        )
        page.body.add_widget(sec_phone)

    return page


def build_friend_page(
    friend_key: str,
    state: ClientState,
    client: Any,
    platform: Platform,
    navigator: Navigator,
    theme: ThemeColors,
    mono_font: Optional[str] = None,
) -> BoxLayout:
    """Friend details, full public key, and remove-friend confirmation."""
    friend = next((f for f in state.friends if f.key == friend_key), None)
    name = friend.display_name if friend is not None else friend_key[:SHORT_KEY]
    page = _PageScaffold(name, navigator, theme)

    head = BoxLayout(
        orientation="vertical", size_hint=(1, None), spacing=dp(6))
    head.bind(minimum_height=head.setter("height"))
    av_wrap = AnchorLayout(size_hint=(1, None), height=dp(96))
    av_wrap.add_widget(
        AvatarWidget(
            key_hex=friend_key,
            name=name,
            theme=theme,
            size_dp=96,
            connection=friend.connection if friend is not None else None,
            status=(friend.status
                    if friend is not None else core.UserStatus.NONE),
            picture=friend.avatar if friend is not None else None,
            ring_color=theme.surface,
        )
    )
    head.add_widget(av_wrap)
    head.add_widget(
        auto_label(name, color=theme.on_surface, font_size_sp=22,
                   bold=True, halign="center")
    )
    if friend is not None:
        head.add_widget(
            auto_label(
                presence_text(friend.connection, friend.status),
                color=theme.on_surface_variant,
                font_size_sp=13.5,
                halign="center",
            )
        )
        if friend.status_message.strip():
            head.add_widget(
                auto_label(
                    friend.status_message,
                    color=theme.on_surface,
                    font_size_sp=14,
                    halign="center",
                )
            )
    page.body.add_widget(head)

    sec_pk = SectionCard("Public key", theme)
    _key_block(sec_pk, friend_key, platform, theme, mono_font=mono_font)
    page.body.add_widget(sec_pk)

    if friend is not None:
        sec_msgs = SectionCard("Messages", theme)
        sec_msgs.add_widget(
            _toggle_row(
                "Hide after a zero byte",
                'Shows "\\0[12 bytes]" in place of the rest of a message.',
                friend.hide_after_zero,
                theme,
                lambda on: client.set_hide_after_zero(friend_key, on),
            )
        )
        page.body.add_widget(sec_msgs)

    sec_rm = SectionCard("Remove", theme)
    sec_rm.add_widget(
        auto_label(
            f"Removes {name} and your chat with them from this device.",
            color=theme.on_surface_variant,
            font_size_sp=13.5,
        )
    )
    rm_row = BoxLayout(
        orientation="horizontal", size_hint=(1, None), height=dp(40))

    def _confirm_remove() -> None:
        client.delete(friend_key)
        navigator.show(ChatsPage())

    def _ask_remove() -> None:
        show_confirm_dialog(
            title=f"Remove {name}?",
            body=("Your chat with them goes too. "
                  "They can send you a friend request again."),
            confirm_label="Remove",
            theme=theme,
            danger=True,
            on_confirm=_confirm_remove,
        )

    rm_row.add_widget(
        PillButton(
            text="Remove friend",
            bg=(0, 0, 0, 0),
            fg=theme.error,
            border=theme.error,
            height_dp=38,
            pad_x_dp=18,
            on_click=_ask_remove,
        )
    )
    rm_row.add_widget(Widget())
    sec_rm.add_widget(rm_row)
    page.body.add_widget(sec_rm)
    return page
