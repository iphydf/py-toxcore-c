# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""Kivy application shell hosting PyTox's responsive two-pane/single-pane UI."""
from __future__ import annotations

import threading
from dataclasses import replace
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Optional

from kivy.app import App
from kivy.clock import Clock
from kivy.clock import mainthread
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.metrics import sp
from kivy.resources import resource_find
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

from pytox_client.media import VideoFrame
from pytox_client.model import Call
from pytox_client.model import ClientState
from pytox_client.platform_base import Platform
from pytox_client.platform_desktop import DesktopPlatform
from pytox_client.profiles import Profiles
from pytox_client.ui.call_page import CallBar
from pytox_client.ui.call_page import CallPageView
from pytox_client.ui.chat_list import ChatListView
from pytox_client.ui.chat_page import ChatPageView
from pytox_client.ui.file_picker import show_file_picker
from pytox_client.ui.menu import show_menu
from pytox_client.ui.group_page import GroupPageView
from pytox_client.ui.group_pages import build_group_info_page
from pytox_client.ui.navigator import AddRoute
from pytox_client.ui.navigator import CallRoute
from pytox_client.ui.navigator import ChatRoute
from pytox_client.ui.navigator import ChatsPage
from pytox_client.ui.navigator import FriendRoute
from pytox_client.ui.navigator import GroupInfoRoute
from pytox_client.ui.navigator import GroupRoute
from pytox_client.ui.navigator import Navigator
from pytox_client.ui.navigator import Page
from pytox_client.ui.navigator import ProfileRoute
from pytox_client.ui.navigator import SettingsRoute
from pytox_client.ui.pages import PageEdits
from pytox_client.ui.pages import build_add_page
from pytox_client.ui.pages import build_friend_page
from pytox_client.ui.pages import build_profile_page
from pytox_client.ui.pages import build_settings_page
from pytox_client.ui.theme import DARK_THEME
from pytox_client.ui.theme import LIGHT_THEME
from pytox_client.ui.theme import LIST_WIDTH_DP
from pytox_client.ui.theme import TWO_PANES_DP
from pytox_client.ui.theme import ThemeColors
from pytox_client.ui.widgets import HairlineDivider
from pytox_client.ui.widgets import set_bg_color


def _find_mono_font() -> Optional[str]:
    """Locate a monospace font file if installed; fall back cleanly."""
    candidates = (
        "RobotoMono-Regular.ttf",
        "DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
        "/System/Library/Fonts/Menlo.ttc",
    )
    for name in candidates:
        path = Path(name)
        if path.is_file():
            return str(path)
        found = resource_find(name)
        if found:
            return str(found)
    return None


def _build_placeholder(theme: ThemeColors) -> AnchorLayout:
    wrap = AnchorLayout(anchor_x="center", anchor_y="center")
    set_bg_color(wrap, theme.surface)
    col = BoxLayout(
        orientation="vertical",
        size_hint=(None, None),
        size=(dp(280), dp(90)),
        spacing=dp(6),
    )
    col.add_widget(
        Label(
            text="PyTox",
            color=theme.primary,
            font_size=sp(34),
            bold=True,
        )
    )
    col.add_widget(
        Label(
            text="Pick a chat on the left.",
            color=theme.on_surface_variant,
            font_size=sp(14.5),
        )
    )
    wrap.add_widget(col)
    return wrap


class PyToxApp(App):  # type: ignore[misc]
    """Kivy app on :class:`ToxClient` or, on phones, :class:`HandoverClient`."""

    title = "PyTox"

    def __init__(
        self,
        client: Any,
        profiles: Profiles,
        platform: Platform,
        icon_path: Optional[Path] = None,
        initial_friend: Optional[str] = None,
        is_mobile: bool = False,
        initial_group: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        # The shown profile's client; ``profiles`` has them all.
        self._client = client
        self._profiles = profiles
        self._unlisten_profiles: Optional[Callable[[], None]] = None
        # The profile whose call was brought up, so a call shows itself once.
        self._followed_caller: Optional[str] = None
        self._platform = platform
        self._is_mobile = is_mobile
        self._system_dark = platform.is_dark_mode()
        self._theme: ThemeColors = (
            DARK_THEME if self._system_dark else LIGHT_THEME)
        self._state: ClientState = client.state
        self._state_lock = threading.Lock()
        self._pending_state: Optional[ClientState] = None
        self._pending_ev: Any = None
        self._rendering = False
        self._rerender_needed = False
        self._rerender_force = False
        self._unsub: Optional[Callable[[], None]] = None
        self._mono_font = _find_mono_font()
        self._drafts: dict[str, str] = {}
        self._invited: dict[str, set[str]] = {}
        self._page_edits = PageEdits()
        self._current_detail_sig: Any = None
        self._is_wide: Optional[bool] = None
        self._takes_back = False

        if icon_path is not None and icon_path.is_file():
            self.icon = str(icon_path)

        self.navigator = Navigator()
        if initial_friend:
            self.navigator.show(ChatRoute(initial_friend))
        elif initial_group:
            self.navigator.show(GroupRoute(initial_group))
        self._last_page: Page = self.navigator.current
        self._last_non_call_page: Optional[Page] = (
            None if isinstance(self._last_page, CallRoute)
            else self._last_page
        )

        if isinstance(platform, DesktopPlatform):
            platform.set_fallback_picker(
                lambda images, cb: Clock.schedule_once(
                    lambda _dt: show_file_picker(images, self._theme, cb), 0
                )
            )

        # The call bar above the panes, while there's a call elsewhere.
        self._outer: Optional[BoxLayout] = None
        self._root_layout: Optional[BoxLayout] = None
        self._call_bar: Optional[CallBar] = None
        self._call_page: Optional[CallPageView] = None
        self._call_key: Any = None
        self._shown_call: Optional[Call] = None
        # The newest pictures not shown yet, from the client's threads.
        self._pictures_lock = threading.Lock()
        self._pictures: dict[str, Optional[VideoFrame]] = {}
        self._show_pictures = Clock.create_trigger(self._flush_pictures)
        self._unwatch: Optional[Callable[[], None]] = None
        self._left_pane: Optional[BoxLayout] = None
        self._divider: Optional[HairlineDivider] = None
        self._right_pane: Optional[BoxLayout] = None
        self._chat_list: Optional[ChatListView] = None
        self._chat_page: Optional[ChatPageView] = None
        self._group_page: Optional[GroupPageView] = None

    def _resolve_theme(self, state: ClientState) -> ThemeColors:
        mode = state.settings.theme
        if mode == "dark":
            return DARK_THEME
        if mode == "light":
            return LIGHT_THEME
        return DARK_THEME if self._system_dark else LIGHT_THEME

    def build(self) -> BoxLayout:
        self._theme = self._resolve_theme(self._state)
        Window.clearcolor = self._theme.surface
        if self._is_mobile:
            # The UI pads itself by the keyboard's inset (see _refresh_insets)
            # so the top bar stays and the page shrinks above the keyboard.
            Window.softinput_mode = ""
        else:
            Window.minimum_width = int(dp(360))
            Window.minimum_height = int(dp(480))

        self._outer = BoxLayout(orientation="vertical")
        self._root_layout = BoxLayout(orientation="horizontal")
        set_bg_color(self._root_layout, self._theme.surface)
        self._outer.add_widget(self._root_layout)
        self._call_bar = CallBar(self._back_to_call)
        self._call_page = CallPageView(self._client, self._platform,
                                       self.navigator)

        self._chat_list = ChatListView(
            client=self._client,
            platform=self._platform,
            navigator=self.navigator,
            theme=self._theme,
            open_menu=self._open_menu,
            mono_font=self._mono_font,
        )
        self._chat_page = ChatPageView(
            client=self._client,
            platform=self._platform,
            navigator=self.navigator,
            theme=self._theme,
            drafts=self._drafts,
            desktop_enter_sends=not self._is_mobile,
        )
        self._group_page = GroupPageView(
            client=self._client,
            navigator=self.navigator,
            theme=self._theme,
            drafts=self._drafts,
            desktop_enter_sends=not self._is_mobile,
        )
        self._left_pane = BoxLayout(
            orientation="vertical", size_hint=(None, 1), width=dp(LIST_WIDTH_DP))
        self._divider = HairlineDivider(
            self._theme.outline_variant, vertical=True)
        self._right_pane = BoxLayout(orientation="vertical", size_hint=(1, 1))

        self.navigator.set_listener(self._on_route_changed)
        Window.bind(size=self._on_window_resize)
        Window.bind(on_keyboard=self._on_keyboard)
        Window.bind(focus=self._on_window_focus)

        self._unsub = self._client.subscribe(
            self._on_client_state, emit_current=True)
        self._unlisten_profiles = self._profiles.listen(
            lambda: Clock.schedule_once(self._on_profiles, 0))
        self._unwatch = self._client.watch_video(self._on_picture)
        self._client.set_visible(True)
        self._sync_open_chat(self.navigator.current)
        self._sync_back()
        self._apply_layout(force=True)
        self._platform.set_light_system_bars(not self._theme.is_dark)
        self._platform.prepare_window(self._on_insets_changed)
        # The bars' sizes are known once the window is laid out.
        Clock.schedule_once(self._refresh_insets, 0)
        Clock.schedule_once(self._refresh_insets, 0.5)
        return self._outer

    def _refresh_insets(self, _dt: float = 0.0) -> None:
        """Keep the UI out from under the system bars and the keyboard."""
        if self._outer is None:
            return
        left, top, right, bottom = self._platform.window_insets()
        padding = [left, top, right, bottom]
        if list(self._outer.padding) == padding:
            return
        self._outer.padding = padding
        if bottom > 0:
            Clock.schedule_once(self._reveal_focused_input, 0.05)

    def _on_insets_changed(self) -> None:
        """On Android's UI thread: the keyboard came or went."""
        Clock.schedule_once(self._refresh_insets, 0)
        Clock.schedule_once(self._refresh_insets, 0.3)

    def _reveal_focused_input(self, _dt: float) -> None:
        """Scroll the focused field back into view above the keyboard."""
        if self._outer is None:
            return
        for widget in self._outer.walk(restrict=True):
            if isinstance(widget, TextInput) and widget.focus:
                parent = widget.parent
                while parent is not None and parent is not self._outer:
                    if isinstance(parent, ScrollView):
                        parent.scroll_to(widget, padding=dp(16))
                        break
                    parent = parent.parent
                return

    @staticmethod
    def _unfocus_children(root: Optional[Widget]) -> None:
        if root is None:
            return
        for widget in root.walk(restrict=True):
            if isinstance(widget, TextInput) and widget.focus:
                widget.focus = False

    def on_pause(self) -> bool:
        self._client.set_visible(False)
        if self._chat_page is not None:
            self._chat_page.clear_typing()
        # Android hides the keyboard; a field keeping the focus would think
        # it's still up, and a tap wouldn't bring it back after resuming.
        self._unfocus_children(self._outer)
        return True

    def on_resume(self) -> None:
        self._system_dark = self._platform.is_dark_mode()
        self._client.set_visible(True)
        self._render_state()
        # Android may give the activity a new window while the app lives on;
        # it comes with the default soft-input mode and bars again.
        self._platform.prepare_window(self._on_insets_changed)
        self._platform.set_light_system_bars(not self._theme.is_dark)
        self._refresh_insets()
        Clock.schedule_once(self._refresh_insets, 0.3)

    def on_stop(self) -> None:
        if self._unlisten_profiles is not None:
            self._unlisten_profiles()
            self._unlisten_profiles = None
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        if self._unwatch is not None:
            self._unwatch()
            self._unwatch = None
        with self._state_lock:
            if self._pending_ev is not None:
                self._pending_ev.cancel()
                self._pending_ev = None
            self._pending_state = None
        self._show_pictures.cancel()
        if self._call_bar is not None:
            self._call_bar.close()
        if self._call_page is not None:
            self._call_page.close()
        if self._chat_list is not None:
            self._chat_list.close()
        if self._chat_page is not None:
            self._chat_page.close()
        if self._group_page is not None:
            self._group_page.close()
        Window.unbind(
            size=self._on_window_resize,
            on_keyboard=self._on_keyboard,
            focus=self._on_window_focus,
        )
        if self._takes_back:
            self._takes_back = False
            self._platform.set_back_handler(None)
        if self._shown_call is not None:
            self._shown_call = None
            self._platform.call_on_screen(None)
        self._client.close()

    def _on_picture(self, who: str, frame: Optional[VideoFrame]) -> None:
        """On the client's threads: keep the newest, show it on the UI's."""
        with self._pictures_lock:
            self._pictures[who] = frame
        self._show_pictures()

    def _flush_pictures(self, _dt: float) -> None:
        with self._pictures_lock:
            pictures, self._pictures = self._pictures, {}
        if self._call_page is not None:
            for who, frame in pictures.items():
                self._call_page.show_picture(who, frame)

    def open_friend_chat(self, friend_key: str) -> None:
        """Open a friend's chat (called e.g. from Android notification tap)."""
        Clock.schedule_once(
            lambda _dt: self.navigator.show(ChatRoute(friend_key)), 0)

    def show_profile(self, name: str) -> None:
        """Show a profile's chats (e.g. from an Android notification tap)."""
        Clock.schedule_once(lambda _dt: self._show_profile(name), 0)

    def _show_profile(self, name: str) -> None:
        self._profiles.show(name)
        self.navigator.show(ChatsPage())

    def _open_menu(self) -> None:
        show_menu(
            self._profiles, self._theme, self._platform.window_insets(),
            on_show=self._show_profile,
            on_add=self._add_profile,
            on_settings=lambda: self.navigator.show(SettingsRoute()),
        )

    def _add_profile(self) -> None:
        self._profiles.add()
        self.navigator.show(ChatsPage())

    def _delete_profile(self, name: str) -> None:
        self._profiles.delete(name)
        self.navigator.show(ChatsPage())

    def _on_profiles(self, _dt: float) -> None:
        """A call in another profile shows itself there, once."""
        caller = self._profiles.caller
        if caller == self._followed_caller:
            return
        self._followed_caller = caller
        if caller is not None and caller != self._profiles.shown:
            self._profiles.show(caller)
        self._render_state()

    def _back_to_call(self) -> None:
        caller = self._profiles.caller
        if caller is not None:
            self._profiles.show(caller)
        self.navigator.push(CallRoute())

    def answer_call(self, video: bool) -> None:
        """Answer the call that rings (e.g. from its Android notification)."""

        def answer(_dt: float) -> None:
            caller = self._profiles.caller
            if caller is not None:
                self._profiles.show(caller)
            self._platform.ask_call_permissions(
                video, lambda: self._client.answer(video))

        Clock.schedule_once(answer, 0)

    def open_group_chat(self, group_id: str) -> None:
        """Open a group's chat (called e.g. from Android notification tap)."""
        Clock.schedule_once(
            lambda _dt: self.navigator.show(GroupRoute(group_id)), 0)

    def _on_window_focus(self, _win: Any, focused: bool) -> None:
        self._client.set_visible(bool(focused))

    def _on_window_resize(self, _win: Any, _size: Any) -> None:
        # Rotation moves the bars; re-read them after Android lays out.
        Clock.schedule_once(self._refresh_insets, 0.1)
        wide = Window.width >= dp(TWO_PANES_DP)
        if wide != self._is_wide:
            self._apply_layout(force=True)

    @staticmethod
    def _dismiss_top_modal() -> bool:
        for child in list(Window.children):
            if isinstance(child, ModalView):
                child.dismiss(animation=False)
                return True
        return False

    def _on_keyboard(
        self,
        _window: Any,
        key: int,
        *_args: Any,
    ) -> bool:
        # 27 is Escape on desktop and the hardware Back button on Android.
        if key == 27:
            if self._dismiss_top_modal():
                return True
            if self.navigator.back():
                return True
        return False

    def _sync_back(self) -> None:
        """Back goes to the page before, and leaves the app from the list."""
        takes_back = self.navigator.can_go_back
        if takes_back != self._takes_back:
            self._takes_back = takes_back
            self._platform.set_back_handler(
                self._system_back if takes_back else None)

    @mainthread  # type: ignore[misc]
    def _system_back(self) -> None:
        if self._dismiss_top_modal():
            return
        self.navigator.back()

    def _on_route_changed(self, page: Page) -> None:
        prev = self._last_page
        self._last_page = page
        if (isinstance(prev, ChatRoute)
                and not (isinstance(page, ChatRoute)
                         and page.friend == prev.friend)
                and self._chat_page is not None):
            self._chat_page.clear_typing()
        self._sync_open_chat(page)
        self._sync_back()
        self._current_detail_sig = None
        if not isinstance(page, CallRoute):
            # Keep pending form edits across incoming/outgoing call push+pop.
            if page != self._last_non_call_page:
                self._page_edits = PageEdits()
            self._last_non_call_page = page
        if self._rendering:
            self._rerender_needed = True
            self._rerender_force = True
            return
        self._render_state(force=True)

    def _sync_open_chat(self, page: Page) -> None:
        if isinstance(page, ChatRoute):
            self._client.open_chat(page.friend)
        else:
            self._client.open_chat(None)
        if isinstance(page, GroupRoute):
            self._client.open_group(page.group)
        else:
            self._client.open_group(None)

    def _on_client_state(self, state: ClientState) -> None:
        with self._state_lock:
            self._pending_state = state
            if self._pending_ev is None:
                self._pending_ev = Clock.schedule_once(self._flush_state, 0)

    def _flush_state(self, _dt: float) -> None:
        with self._state_lock:
            self._pending_ev = None
            state = self._pending_state
            self._pending_state = None
        if state is None:
            return
        self._state = state
        self._render_state()

    def _follow_call(self) -> None:
        """A new call gets its page; the page goes when the call ends."""
        call = self._state.call
        if call != self._shown_call:
            self._shown_call = call
            self._platform.call_on_screen(call)
        key = None if call is None else (call.friend, call.outgoing)
        if key == self._call_key:
            return
        self._call_key = key
        if call is None:
            self.navigator.drop(CallRoute())
        else:
            self.navigator.push(CallRoute())

    def _render_state(self, force: bool = False) -> None:
        if self._rendering:
            self._rerender_needed = True
            self._rerender_force = self._rerender_force or force
            return
        self._rendering = True
        try:
            cur_force = force
            while True:
                self._rerender_needed = False
                self._rerender_force = False
                self._follow_call()
                if self._call_page is not None:
                    self._call_page.update(self._state)
                if self._call_bar is not None and self._outer is not None:
                    call_state = self._caller_state()
                    bar = (call_state is not None
                           and not isinstance(self.navigator.current, CallRoute))
                    if bar and self._call_bar.parent is None:
                        self._outer.add_widget(self._call_bar, index=1)
                    elif not bar and self._call_bar.parent is not None:
                        self._outer.remove_widget(self._call_bar)
                    if call_state is not None:
                        self._call_bar.update(call_state)
                new_theme = self._resolve_theme(self._state)
                theme_changed = new_theme != self._theme
                self._theme = new_theme
                if theme_changed:
                    Window.clearcolor = new_theme.surface
                    self._platform.set_light_system_bars(not new_theme.is_dark)
                    if self._root_layout is not None:
                        set_bg_color(self._root_layout, new_theme.surface)
                    if self._divider is not None:
                        self._divider.set_color(new_theme.outline_variant)
                self._apply_layout(
                    force=cur_force or self._rerender_force or theme_changed)
                if not self._rerender_needed:
                    break
                cur_force = self._rerender_force
        finally:
            self._rendering = False

    def _caller_state(self) -> Optional[ClientState]:
        """The state of the profile with the call, the shown one or not."""
        if self._state.call is not None:
            return self._state
        caller = self._profiles.caller
        client = None if caller is None else self._profiles.client(caller)
        return None if client is None else client.state

    def _apply_layout(self, force: bool = False) -> None:
        if (self._root_layout is None or self._chat_list is None
                or self._chat_page is None or self._left_pane is None
                or self._divider is None or self._right_pane is None
                or self._group_page is None):
            return

        wide = Window.width >= dp(TWO_PANES_DP)
        page = self.navigator.current
        selected = page.friend if isinstance(page, ChatRoute) else None
        selected_group = page.group if isinstance(page, GroupRoute) else None
        layout_changed = wide != self._is_wide
        self._is_wide = wide

        if layout_changed:
            self._root_layout.clear_widgets()
            self._left_pane.clear_widgets()
            self._right_pane.clear_widgets()
            if wide:
                self._left_pane.add_widget(self._chat_list)
                self._root_layout.add_widget(self._left_pane)
                self._root_layout.add_widget(self._divider)
                self._root_layout.add_widget(self._right_pane)
            else:
                self._root_layout.add_widget(self._right_pane)
            self._current_detail_sig = None

        self._chat_list.update(
            self._state, self._theme, wide=wide, selected=selected,
            force=force or layout_changed, selected_group=selected_group,
        )

        sig: Any
        if isinstance(page, ChatsPage):
            if wide:
                sig = ("placeholder", self._theme.is_dark)
                if force or sig != self._current_detail_sig:
                    self._current_detail_sig = sig
                    self._show_page(_build_placeholder(self._theme))
            else:
                sig = ("list", self._theme.is_dark)
                if force or sig != self._current_detail_sig:
                    self._current_detail_sig = sig
                    self._show_page(self._chat_list)
        elif isinstance(page, ChatRoute):
            sig = ("chat", page.friend)
            if self._current_detail_sig != sig or (
                    self._chat_page.parent is not self._right_pane):
                self._current_detail_sig = sig
                self._show_page(self._chat_page)
            self._chat_page.update(
                page.friend, self._state, self._theme, wide=wide, force=force)
        elif isinstance(page, GroupRoute):
            sig = ("group", page.group)
            if self._current_detail_sig != sig or (
                    self._group_page.parent is not self._right_pane):
                self._current_detail_sig = sig
                self._show_page(self._group_page)
            self._group_page.update(
                page.group, self._state, self._theme, wide=wide, force=force)
        elif isinstance(page, GroupInfoRoute):
            grp = next(
                (g for g in self._state.groups if g.id == page.group), None)
            # Not built again for each message: the page doesn't show them.
            shown = (replace(grp, last=None, unread=0)
                     if grp is not None else None)
            online = tuple(
                (f.key, f.display_name, f.avatar)
                for f in self._state.friends if f.online
            )
            sig = ("group-info", self._theme.is_dark, page.group, shown,
                   online)
            if force or sig != self._current_detail_sig:
                self._current_detail_sig = sig
                self._show_page(
                    build_group_info_page(
                        page.group, self._state, self._client, self._platform,
                        self.navigator, self._theme, self._invited,
                        self._page_edits, mono_font=self._mono_font,
                    )
                )
        elif isinstance(page, ProfileRoute):
            p = self._state.profile
            this = self._profiles.shown
            # The last profile stays, as does one in a call.
            deletable = (len(self._profiles.names) > 1
                         and self._profiles.caller != this)
            sig = ("profile", self._theme.is_dark, p.address, p.connection,
                   p.status, p.avatar, p.name, p.status_message, this,
                   deletable)
            if force or sig != self._current_detail_sig:
                self._current_detail_sig = sig
                self._show_page(
                    build_profile_page(
                        self._state, self._client, self._platform,
                        self.navigator, self._theme, self._page_edits,
                        mono_font=self._mono_font,
                        on_delete=(lambda: self._delete_profile(this))
                        if deletable else None,
                    )
                )
        elif isinstance(page, AddRoute):
            sig = ("add", self._theme.is_dark, self._state.profile.address)
            if force or sig != self._current_detail_sig:
                self._current_detail_sig = sig
                self._show_page(
                    build_add_page(
                        self._state, self._client, self._platform,
                        self.navigator, self._theme, self._page_edits,
                        mono_font=self._mono_font,
                    )
                )
        elif isinstance(page, SettingsRoute):
            sig = ("settings", self._theme.is_dark, self._state.settings)
            if force or sig != self._current_detail_sig:
                self._current_detail_sig = sig
                self._show_page(
                    build_settings_page(
                        self._state, self._client, self._platform,
                        self.navigator, self._theme,
                        self._profiles.set_stay_connected,
                    )
                )
        elif isinstance(page, CallRoute):
            assert self._call_page is not None
            if self._call_page.parent is not self._right_pane:
                self._current_detail_sig = "call"
                self._show_page(self._call_page)
        elif isinstance(page, FriendRoute):
            fr = next(
                (f for f in self._state.friends if f.key == page.friend),
                None,
            )
            shown_fr = (
                replace(fr, typing=False, last=None, unread=0)
                if fr is not None else None
            )
            sig = ("friend", self._theme.is_dark, page.friend, shown_fr)
            if force or sig != self._current_detail_sig:
                self._current_detail_sig = sig
                self._show_page(
                    build_friend_page(
                        page.friend, self._state, self._client, self._platform,
                        self.navigator, self._theme, mono_font=self._mono_font,
                    )
                )

    def _show_page(self, page: Widget) -> None:
        """Swap ``page`` in, built while the old one still had the focus."""
        assert self._right_pane is not None
        self._unfocus_children(self._right_pane)
        self._right_pane.clear_widgets()
        self._right_pane.add_widget(page)
