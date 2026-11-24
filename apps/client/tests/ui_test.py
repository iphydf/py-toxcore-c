# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""Headless Kivy UI regression tests (run under Xvfb + software GL)."""
from __future__ import annotations

import atexit
import os
import shutil
import stat
import tempfile
import unittest
from dataclasses import replace
from typing import Any
from typing import Callable
from pathlib import Path
from typing import Optional

_KIVY_DIR = tempfile.mkdtemp(prefix="pytox-kivy-test-")


def _cleanup_kivy_dir() -> None:
    def _writable(fn: Any, path: str, _exc: Any) -> None:
        os.chmod(path, stat.S_IRWXU)
        fn(path)

    shutil.rmtree(_KIVY_DIR, onerror=_writable)


atexit.register(_cleanup_kivy_dir)

os.environ["KIVY_HOME"] = _KIVY_DIR
os.environ["KIVY_NO_ARGS"] = "1"
os.environ.setdefault("KIVY_NO_FILELOG", "1")
os.environ.setdefault("KIVY_LOG_LEVEL", "warning")

from kivy.config import Config  # noqa: E402

Config.set("graphics", "width", "400")
Config.set("graphics", "height", "800")
Config.set("graphics", "resizable", "1")

from kivy.clock import Clock  # noqa: E402
from kivy.core.window import Window  # noqa: E402
from kivy.metrics import dp  # noqa: E402
from kivy.uix.modalview import ModalView  # noqa: E402
from kivy.uix.scrollview import ScrollView  # noqa: E402
from kivy.uix.textinput import TextInput  # noqa: E402
from kivy.uix.widget import Widget  # noqa: E402

import pytox.toxcore.tox as core  # noqa: E402
from pytox_client.media import VideoFrame  # noqa: E402
from pytox_client.model import Call  # noqa: E402
from pytox_client.model import Chat  # noqa: E402
from pytox_client.model import ClientState  # noqa: E402
from pytox_client.model import Friend  # noqa: E402
from pytox_client.model import Group  # noqa: E402
from pytox_client.model import GroupChat  # noqa: E402
from pytox_client.model import GroupMessage  # noqa: E402
from pytox_client.model import Message  # noqa: E402
from pytox_client.model import Peer  # noqa: E402
from pytox_client.model import Profile  # noqa: E402
from pytox_client.model import Settings  # noqa: E402
from pytox_client.platform_base import NoopPlatform  # noqa: E402
from pytox_client.platform_base import Platform  # noqa: E402
from pytox_client.profiles import Profiles  # noqa: E402
from pytox_client.profiles import ShownClient  # noqa: E402
from pytox_client.ui.app import PyToxApp  # noqa: E402
from pytox_client.ui.call_page import CallPageView  # noqa: E402
from pytox_client.ui.chat_page import ChatPageView  # noqa: E402
from pytox_client.ui.chat_page import ComposerInput  # noqa: E402
from pytox_client.ui.group_page import GroupPageView  # noqa: E402
from pytox_client.ui.group_pages import build_group_info_page  # noqa: E402
from pytox_client.ui.navigator import AddRoute  # noqa: E402
from pytox_client.ui.navigator import CallRoute  # noqa: E402
from pytox_client.ui.navigator import ChatRoute  # noqa: E402
from pytox_client.ui.navigator import Navigator  # noqa: E402
from pytox_client.ui.pages import PageEdits  # noqa: E402
from pytox_client.ui.pages import build_add_page  # noqa: E402
from pytox_client.ui.pages import build_profile_page  # noqa: E402
from pytox_client.ui.theme import LIGHT_THEME  # noqa: E402
from pytox_client.ui.video import VideoView  # noqa: E402
from pytox_client.ui.widgets import HistoryView  # noqa: E402
from pytox_client.ui.widgets import StyledTextInput  # noqa: E402
from pytox_client.ui.widgets import set_bg_color  # noqa: E402

_FRIEND_KEY = "A1" * 32
_GROUP_ID = "5C" * 32
_MY_ADDR = "C0" * 38


class _FakePlatform(NoopPlatform):

    def __init__(self, *, cameras: int = 1) -> None:
        self._cameras = cameras
        self.insets: tuple[int, int, int, int] = (0, 63, 0, 63)
        self.prepare_calls: list[Callable[[], None]] = []
        self.light_bar_calls: list[bool] = []
        self.back_handlers: list[Optional[Callable[[], None]]] = []

    @property
    def cameras(self) -> int:
        return self._cameras

    def window_insets(self) -> tuple[int, int, int, int]:
        return self.insets

    def prepare_window(self, insets_changed: Callable[[], None]) -> None:
        self.prepare_calls.append(insets_changed)

    def set_light_system_bars(self, light: bool) -> None:
        self.light_bar_calls.append(light)

    def set_back_handler(self, on_back: Optional[Callable[[], None]]) -> None:
        self.back_handlers.append(on_back)


class _FakeClient:

    def __init__(self, state: ClientState) -> None:
        self._state = state
        self._listeners: list[Callable[[ClientState], None]] = []
        self.visible_calls: list[bool] = []

    @property
    def state(self) -> ClientState:
        return self._state

    def set_state(self, state: ClientState) -> None:
        self._state = state
        for listener in list(self._listeners):
            listener(state)

    def subscribe(
        self,
        fn: Callable[[ClientState], None],
        emit_current: bool = True,
    ) -> Callable[[], None]:
        self._listeners.append(fn)
        if emit_current:
            fn(self._state)

        def _unsub() -> None:
            if fn in self._listeners:
                self._listeners.remove(fn)

        return _unsub

    def watch_video(
        self,
        _fn: Callable[[str, Optional[VideoFrame]], None],
    ) -> Callable[[], None]:
        return lambda: None

    def start(self) -> None:
        pass

    def update_settings(self, settings: Settings) -> None:
        self.set_state(replace(self._state, settings=settings))

    def delete_profile(self) -> None:
        pass

    def set_visible(self, visible: bool) -> None:
        self.visible_calls.append(visible)

    def open_chat(self, _key: Optional[str]) -> None:
        pass

    def open_group(self, _gid: Optional[str]) -> None:
        pass

    def set_typing(self, _key: str, _typing: bool) -> None:
        pass

    def load_older(self) -> None:
        pass

    def load_older_group_messages(self) -> None:
        pass

    def hang_up(self) -> None:
        pass

    def answer(self, _video: bool) -> None:
        pass

    def set_muted(self, _muted: bool) -> None:
        pass

    def set_video(self, _video: bool) -> None:
        pass

    def switch_camera(self) -> None:
        pass

    def set_speaker(self, _speaker: bool) -> None:
        pass

    def close(self) -> None:
        pass


def _make_state(theme: str = "light") -> ClientState:
    alice = Friend(
        key=_FRIEND_KEY,
        name="Alice",
        status_message="hi",
        status=core.UserStatus.NONE,
        connection=core.Connection.UDP,
        typing=False,
        unread=0,
        last=None,
        avatar=None,
        hide_after_zero=False,
    )
    me = Peer("11" * 32, "Me", core.GroupRole.FOUNDER,
              core.UserStatus.NONE, True)
    group = Group(
        id=_GROUP_ID,
        name="TestGroup",
        topic="Topic",
        privacy=core.GroupPrivacyState.PUBLIC,
        connected=True,
        peers=(me,),
        self_role=core.GroupRole.FOUNDER,
        password="",
        peer_limit=100,
        topic_locked=False,
        unread=0,
        last=None,
        problem=None,
    )
    msgs = tuple(
        Message(
            id=i,
            friend=_FRIEND_KEY,
            outgoing=True,
            action=False,
            text=f"msg {i}",
            time=1_700_000_000_000 + i * 1000,
            delivered=True,
        )
        for i in range(1, 5)
    )
    gmsgs = tuple(
        GroupMessage(
            id=i,
            group=_GROUP_ID,
            peer_key="",
            peer_name="Me",
            outgoing=True,
            action=False,
            private=False,
            text=f"gmsg {i}",
            time=1_700_000_000_000 + i * 1000,
            sent=True,
        )
        for i in range(1, 4)
    )
    return ClientState(
        profile=Profile(
            address=_MY_ADDR,
            name="Me",
            status_message="",
            status=core.UserStatus.NONE,
            connection=core.Connection.UDP,
        ),
        friends=(alice,),
        requests=(),
        chat=Chat(friend=_FRIEND_KEY, messages=msgs, has_older=False),
        groups=(group,),
        invites=(),
        group_chat=GroupChat(group=_GROUP_ID, messages=gmsgs, has_older=False),
        settings=Settings(theme=theme),
    )


def _advance_clock(seconds: float = 0.0, frames: int = 3) -> None:
    """Drive Kivy's event scheduler across scheduled timeouts."""
    import time
    if seconds > 0:
        time.sleep(seconds)
    for _ in range(frames):
        Clock.tick()


def _editable_inputs(root: Widget) -> list[TextInput]:
    return [
        w for w in root.walk(restrict=True)
        if isinstance(w, TextInput) and not w.readonly
    ]


class UiRegressionTest(unittest.TestCase):

    def tearDown(self) -> None:
        for child in list(Window.children):
            Window.remove_widget(child)

    def test_chat_header_call_and_info_icons_aligned(self) -> None:
        for cameras in (0, 1):
            platform = _FakePlatform(cameras=cameras)
            client = _FakeClient(_make_state())
            view = ChatPageView(
                client=client,
                platform=platform,
                navigator=Navigator(),
                theme=LIGHT_THEME,
                drafts={},
                desktop_enter_sends=False,
            )
            view.size_hint = (None, None)
            view.size = (400, 800)
            Window.add_widget(view)
            # Check both default (60 dp) and taller bars where a hardcoded
            # top/bottom padding would misalign the call icons vs (i).
            for bar_height in (dp(60), dp(84), dp(104)):
                view._topbar.height = bar_height
                view.do_layout()
                view._topbar.do_layout()
                _advance_clock()
                row_center = view._topbar.row.center_y
                info_y = view._info_btn.center_y
                call_y = view._call_btn.center_y
                self.assertAlmostEqual(call_y, info_y, delta=1.0)
                self.assertAlmostEqual(info_y, row_center, delta=1.0)
                if cameras > 0:
                    self.assertAlmostEqual(
                        view._video_btn.center_y, info_y, delta=1.0)
            Window.remove_widget(view)

    def test_input_types_and_keyboard_suggestions(self) -> None:
        state = _make_state()
        client = _FakeClient(state)
        platform = _FakePlatform()
        nav = Navigator()

        # Standalone ComposerInput / StyledTextInput defaults must not leave
        # Kivy's default "null" (which disables Android swipe typing).
        composer = ComposerInput(on_send=lambda: None)
        self.assertEqual(composer.input_type, "text")
        self.assertTrue(composer.keyboard_suggestions)

        styled = StyledTextInput(LIGHT_THEME, hint="Prose")
        self.assertEqual(styled.field.input_type, "text")
        self.assertTrue(styled.field.keyboard_suggestions)

        # Chat & group composer bars.
        chat_view = ChatPageView(
            client=client, platform=platform, navigator=nav,
            theme=LIGHT_THEME, drafts={}, desktop_enter_sends=False)
        group_view = GroupPageView(
            client=client, navigator=nav, theme=LIGHT_THEME, drafts={},
            desktop_enter_sends=False)
        for view in (chat_view, group_view):
            fields = _editable_inputs(view)
            self.assertEqual(len(fields), 1)
            self.assertEqual(fields[0].input_type, "text")
            self.assertTrue(fields[0].keyboard_suggestions)

        # Profile page.
        profile_page = build_profile_page(
            state, client, platform, nav, LIGHT_THEME, PageEdits())
        by_hint = {f.hint_text: f for f in _editable_inputs(profile_page)}
        self.assertEqual(by_hint["Your display name"].input_type, "text")
        self.assertTrue(by_hint["Your display name"].keyboard_suggestions)
        self.assertEqual(by_hint["What are you up to?"].input_type, "text")
        self.assertTrue(by_hint["What are you up to?"].keyboard_suggestions)

        # Add page: hex IDs and password disable suggestions; prose enables.
        add_page = build_add_page(
            state, client, platform, nav, LIGHT_THEME, PageEdits())
        add_fields = {f.hint_text: f for f in _editable_inputs(add_page)}
        self.assertFalse(
            add_fields["76-character hex ID (or tox:...)"].keyboard_suggestions)
        self.assertEqual(
            add_fields["76-character hex ID (or tox:...)"].input_type, "text")
        self.assertTrue(
            add_fields["Hi, I'd like to add you as a friend."]
            .keyboard_suggestions)
        self.assertTrue(add_fields["Group name"].keyboard_suggestions)
        self.assertFalse(
            add_fields["64-character hex chat ID"].keyboard_suggestions)
        self.assertFalse(add_fields["Password"].keyboard_suggestions)

        # Group info page (founder settings).
        info_page = build_group_info_page(
            _GROUP_ID, state, client, platform, nav, LIGHT_THEME,
            invited={}, edits=PageEdits())
        info_fields = {f.hint_text: f for f in _editable_inputs(info_page)}
        self.assertEqual(info_fields["Topic"].input_type, "text")
        self.assertTrue(info_fields["Topic"].keyboard_suggestions)
        self.assertEqual(info_fields["No password"].input_type, "text")
        self.assertFalse(info_fields["No password"].keyboard_suggestions)
        self.assertEqual(info_fields["Peer limit"].input_type, "number")

        # Global invariant: zero editable fields left with input_type == "null".
        for page in (chat_view, group_view, profile_page, add_page, info_page):
            for field in _editable_inputs(page):
                self.assertNotEqual(
                    field.input_type, "null",
                    f"field {field.hint_text!r} left with input_type='null'",
                )

    def test_history_view_stays_at_bottom_when_shrunk_below_content(self) -> None:
        hv = HistoryView(desktop=False, on_near_top=lambda: None)
        hv.size_hint = (None, None)
        hv.size = (400, 700)
        Window.add_widget(hv)
        rows = [
            (("r", i), i, lambda i=i: Widget(size_hint=(1, None), height=60))
            for i in range(10)
        ]
        hv.show(rows, follow=True)
        hv.box.do_layout()
        _advance_clock(0.08)

        # Content fits in 700 px initially, overflows 380 px when keyboard opens.
        self.assertLess(hv.box.height, 700)
        self.assertGreater(hv.box.height, 380)

        # Stepwise shrink simulating keyboard opening animation.
        for height in (650, 520, 420, 380):
            hv.height = height
            _advance_clock(frames=3)

        self.assertAlmostEqual(hv.scroll_y, 0.0, places=4)
        # Scroll effect must be synced so Kivy's momentum/physics cannot snap
        # the viewport back to the top (causing the reported flicker).
        if hv.effect_y is not None:
            self.assertAlmostEqual(hv.effect_y.value, 0.0, places=3)
            hv._update_effect_y()
            self.assertAlmostEqual(hv.scroll_y, 0.0, places=4)

        # Closing the keyboard fits all messages again -> top / scroll_y = 1.
        hv.height = 700
        _advance_clock(frames=3)
        self.assertAlmostEqual(hv.scroll_y, 1.0, places=4)

        # Re-opening pins back to the newest message at the bottom.
        hv.height = 380
        _advance_clock(frames=3)
        self.assertAlmostEqual(hv.scroll_y, 0.0, places=4)

    def test_history_view_preserves_scroll_offset_when_scrolled_up(self) -> None:
        hv = HistoryView(desktop=False, on_near_top=lambda: None)
        hv.size_hint = (None, None)
        hv.size = (400, 500)
        Window.add_widget(hv)
        rows = [
            (("r", i), i, lambda i=i: Widget(size_hint=(1, None), height=100))
            for i in range(15)
        ]
        hv.show(rows, follow=True)
        hv.box.do_layout()
        _advance_clock(0.08)

        # Let any resize guard settle, then scroll well above the bottom.
        _advance_clock(0.55)
        old_room = hv.box.height - hv.height
        self.assertGreater(old_room, 500)
        target_from_bottom = 300.0
        hv.scroll_y = target_from_bottom / old_room
        hv._update_effect_y_bounds()
        self.assertFalse(hv._at_bottom)

        # Shrinking the viewport must keep the same distance from the bottom.
        hv.height = 300
        _advance_clock(frames=3)
        new_room = hv.box.height - hv.height
        self.assertAlmostEqual(
            hv.scroll_y * new_room, target_from_bottom, delta=2.0)

        # Switching to a new chat (follow=True) goes back to bottom tracking.
        hv.show(rows, follow=True)
        _advance_clock(0.08)
        self.assertTrue(hv._at_bottom)
        self.assertAlmostEqual(hv.scroll_y, 0.0, places=4)

    def _app(self, client: _FakeClient, platform: Platform) -> PyToxApp:
        """A phone app on ``client``, its one profile."""
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        profiles = Profiles(Path(root.name), lambda _dir, _name: client)
        return PyToxApp(client=ShownClient(profiles), profiles=profiles,
                        platform=platform, is_mobile=True)

    def test_mobile_app_insets_keyboard_and_resume_lifecycle(self) -> None:
        Window.size = (400, 800)
        platform = _FakePlatform(cameras=1)
        state = _make_state(theme="light")
        client = _FakeClient(state)
        app = self._app(client, platform)
        root = app.build()
        Window.add_widget(root)
        root.size = Window.size
        _advance_clock(frames=3)
        self.addCleanup(app.on_stop)

        # Mobile must disable Kivy's built-in window pan mode.
        self.assertEqual(Window.softinput_mode, "")
        self.assertEqual(len(platform.prepare_calls), 1)
        self.assertEqual(platform.light_bar_calls, [True])
        assert app._outer is not None
        self.assertEqual(list(app._outer.padding), [0, 63, 0, 63])

        # Open a friend chat and focus its composer field.
        app.navigator.show(ChatRoute(_FRIEND_KEY))
        _advance_clock(frames=3)
        assert app._chat_page is not None
        composer = app._chat_page._input
        composer.text = "draft kept on pause"
        composer.focus = True
        self.assertTrue(composer.focus)

        # Opening the keyboard updates bottom inset via the listener callback.
        platform.insets = (0, 63, 0, 360)
        platform.prepare_calls[-1]()
        _advance_clock(frames=3)
        self.assertEqual(list(app._outer.padding), [0, 63, 0, 360])

        # Pausing must unfocus TextInput (keeping draft text) so Android can
        # re-open the keyboard on tap after resume.
        self.assertTrue(app.on_pause())
        self.assertFalse(composer.focus)
        self.assertEqual(composer.text, "draft kept on pause")
        self.assertIs(client.visible_calls[-1], False)

        # Resuming must re-apply window setup, light bar style, and insets.
        platform.insets = (0, 63, 0, 63)
        app.on_resume()
        _advance_clock(frames=3)
        self.assertIs(client.visible_calls[-1], True)
        self.assertEqual(len(platform.prepare_calls), 2)
        self.assertEqual(platform.light_bar_calls[-1], True)
        self.assertEqual(list(app._outer.padding), [0, 63, 0, 63])

        # Switching to dark theme updates the system bar icon appearance.
        client.set_state(replace(state, settings=Settings(theme="dark")))
        _advance_clock(frames=3)
        self.assertEqual(platform.light_bar_calls[-1], False)

        # Focused input near the bottom of a scrollable page gets scrolled up.
        app.navigator.show(AddRoute())
        _advance_clock(frames=3)
        root.do_layout()
        scrolls = [
            w for w in root.walk(restrict=True)
            if isinstance(w, ScrollView)
        ]
        self.assertTrue(scrolls)
        add_scroll = scrolls[0]
        bottom_fields = [
            f for f in _editable_inputs(add_scroll)
            if f.hint_text == "Password"
        ]
        self.assertEqual(len(bottom_fields), 1)
        bottom_fields[0].focus = True
        platform.insets = (0, 63, 0, 420)
        platform.prepare_calls[-1]()
        # Fire _refresh_insets, then _reveal_focused_input (0.05s), then
        # let ScrollView.scroll_to complete its 0.2s animation.
        _advance_clock(0.02, frames=3)
        _advance_clock(0.08, frames=3)
        _advance_clock(0.30, frames=4)
        self.assertLess(add_scroll.scroll_y, 1.0)

    def test_set_bg_color_reuses_color_instruction_without_leaking(self) -> None:
        w = Widget(size=(100, 40))
        set_bg_color(w, (1, 0, 0, 1))
        first_color = getattr(w, "_bg_color_instr")
        first_cb = getattr(w, "_bg_sync_cb")
        set_bg_color(w, (0, 1, 0, 1))
        self.assertIs(getattr(w, "_bg_color_instr"), first_color)
        self.assertIs(getattr(w, "_bg_sync_cb"), first_cb)
        self.assertEqual(tuple(first_color.rgba), (0, 1, 0, 1))
        # Radius change replaces cleanly without throwing.
        set_bg_color(w, (0, 0, 1, 1), radius=8.0)
        self.assertIsNot(getattr(w, "_bg_color_instr"), first_color)

    def test_video_view_rejects_bad_frames_and_clears_textures(self) -> None:
        vv = VideoView(size=(160, 120))
        # Zero-size and truncated frames are safely ignored.
        vv.show(VideoFrame(0, 0, b"", b"", b"", 0, 0, 0))
        self.assertFalse(vv.showing)
        vv.show(VideoFrame(4, 2, b"short", b"u", b"v", 4, 2, 2))
        self.assertFalse(vv.showing)
        # Valid frame binds GL textures; None frees them.
        vv.show(VideoFrame.packed(4, 2, bytes(12)))
        self.assertTrue(vv.showing)
        self.assertEqual(len(vv._textures), 3)
        vv.show(None)
        self.assertFalse(vv.showing)
        self.assertEqual(vv._textures, [])

    def test_call_page_ticker_and_five_buttons_fit_portrait(self) -> None:
        class _TwoCamPlatform(_FakePlatform):
            @property
            def has_earpiece(self) -> bool:
                return True

        platform = _TwoCamPlatform(cameras=2)
        state = _make_state()
        client = _FakeClient(state)
        page = CallPageView(client, platform, Navigator())
        page.size_hint = (None, None)
        page.size = (dp(360), dp(640))
        # Idle: no 1 Hz background timer running.
        self.assertIsNone(page._ticker)
        active_call = Call(
            friend=_FRIEND_KEY,
            outgoing=True,
            video_call=True,
            answered=True,
            video=True,
        )
        page.update(replace(state, call=active_call))
        self.assertIsNotNone(page._ticker)
        self.assertEqual(len(page._control_buttons), 5)
        self.assertLessEqual(page._controls.width, dp(360))
        # Ending the call cancels the ticker and clears video frames.
        page.update(state)
        self.assertIsNone(page._ticker)
        page.close()

    def test_back_dismisses_modal_and_call_preserves_page_edits(self) -> None:
        Window.size = (400, 800)
        platform = _FakePlatform(cameras=1)
        state = _make_state(theme="light")
        client = _FakeClient(state)
        app = self._app(client, platform)
        root = app.build()
        Window.add_widget(root)
        self.addCleanup(app.on_stop)
        _advance_clock(frames=3)

        # Navigate to AddRoute, enter draft text & flip the Private toggle flag.
        app.navigator.show(AddRoute())
        _advance_clock(frames=2)
        app._page_edits._texts["group name"] = "My Group"
        app._page_edits.set_flag("group private", True)

        # Incoming call pushes CallRoute; hanging up returns to AddRoute with
        # edits still preserved.
        client.set_state(replace(
            state,
            call=Call(friend=_FRIEND_KEY, outgoing=False, video_call=False),
        ))
        _advance_clock(frames=2)
        self.assertIsInstance(app.navigator.current, CallRoute)
        client.set_state(state)
        _advance_clock(frames=2)
        self.assertIsInstance(app.navigator.current, AddRoute)
        self.assertTrue(app._page_edits.flag("group private"))
        self.assertEqual(app._page_edits._texts.get("group name"), "My Group")

        # Escape / Android Back dismisses an open ModalView before popping route.
        modal = ModalView(size_hint=(None, None), size=(100, 100))
        modal.open(animation=False)
        self.assertIn(modal, Window.children)
        dismissed: list[bool] = []
        modal.bind(on_dismiss=lambda *_: dismissed.append(True))
        self.assertTrue(app._on_keyboard(Window, 27))
        self.assertTrue(dismissed)
        self.assertNotIn(modal, Window.children)
        self.assertIsInstance(app.navigator.current, AddRoute)
        self.assertTrue(app._on_keyboard(Window, 27))
        self.assertNotIsInstance(app.navigator.current, AddRoute)


if __name__ == "__main__":
    unittest.main()
