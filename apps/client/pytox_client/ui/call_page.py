# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""The call, on a dark page of its own, and the bar back to it from elsewhere.

The friend's video or picture fills the page, ours sits in a corner, and the
buttons are along the bottom, as in kTox.
"""
from __future__ import annotations

import time
from typing import Any
from typing import Callable
from typing import Optional

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.metrics import sp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label

from pytox_client.calls import FRIEND
from pytox_client.media import VideoFrame
from pytox_client.model import Call
from pytox_client.model import ClientState
from pytox_client.model import SHORT_KEY
from pytox_client.platform_base import Platform
from pytox_client.ui.formatting import call_status
from pytox_client.ui.navigator import Navigator
from pytox_client.ui.theme import DARK_THEME
from pytox_client.ui.theme import RGBA
from pytox_client.ui.theme import with_alpha
from pytox_client.ui.video import VideoView
from pytox_client.ui.widgets import AvatarWidget
from pytox_client.ui.widgets import ClickableBox
from pytox_client.ui.widgets import IconButton
from pytox_client.ui.widgets import set_bg_color

CALL_BACKGROUND: RGBA = (0.07, 0.08, 0.10, 1.0)
WHITE: RGBA = (1.0, 1.0, 1.0, 1.0)
RED: RGBA = (0.86, 0.22, 0.20, 1.0)
GREEN: RGBA = (0.16, 0.66, 0.36, 1.0)
_PROBLEM: RGBA = (1.0, 0.77, 0.24, 1.0)
_SELF_WIDTH_DP = 108


def _now_ms() -> int:
    return int(time.time() * 1000)


def _label(text: str, size: float, color: RGBA = WHITE, **kwargs: Any) -> Label:
    lbl = Label(text=text, color=color, font_size=sp(size), **kwargs)
    lbl.bind(size=lambda i, s: setattr(i, "text_size", (s[0], None)))
    return lbl


class _CallButton(BoxLayout):  # type: ignore[misc]
    """A round button with its name under it."""

    def __init__(
        self,
        kind: str,
        label: str,
        fg: RGBA,
        bg: RGBA,
        on_click: Callable[[], None],
        slot_dp: float = 76.0,
        circle_dp: float = 60.0,
    ) -> None:
        super().__init__(orientation="vertical",
                         size_hint=(None, None),
                         size=(dp(slot_dp), dp(84)),
                         spacing=dp(6))
        self._wrap = AnchorLayout(size_hint=(1, None), height=dp(60))
        self._btn = IconButton(
            kind, fg=fg, bg=bg, size_dp=circle_dp,
            icon_dp=circle_dp * (28.0 / 60.0), on_click=on_click)
        self._wrap.add_widget(self._btn)
        self.add_widget(self._wrap)
        self.add_widget(
            _label(label, 12, with_alpha(WHITE, 0.9), halign="center",
                   size_hint=(1, None), height=dp(18),
                   shorten=True, shorten_from="right"))

    def set_slot_width(self, slot_px: float) -> None:
        self.width = slot_px


def _action(kind: str, label: str, bg: RGBA,
            on_click: Callable[[], None]) -> _CallButton:
    return _CallButton(kind, label, WHITE, bg, on_click)


def _toggle(kind: str, label: str, on: bool,
            on_click: Callable[[], None]) -> _CallButton:
    """Lit while ``on``."""
    if on:
        return _CallButton(kind, label, CALL_BACKGROUND, WHITE, on_click)
    return _CallButton(kind, label, WHITE, with_alpha(WHITE, 0.18), on_click)


class CallPageView(FloatLayout):  # type: ignore[misc]
    """The call: built once, then shown again with each state."""

    def __init__(self, client: Any, platform: Platform,
                 navigator: Navigator) -> None:
        super().__init__()
        self._client = client
        self._platform = platform
        self._navigator = navigator
        self._call: Optional[Call] = None
        self._controls_sig: Any = None
        set_bg_color(self, CALL_BACKGROUND)

        self._friend_video = VideoView(size_hint=(1, 1),
                                       pos_hint={
                                           "x": 0,
                                           "y": 0
                                       })
        self.add_widget(self._friend_video)

        page = BoxLayout(orientation="vertical",
                         size_hint=(1, 1),
                         pos_hint={
                             "x": 0,
                             "y": 0
                         })
        top = BoxLayout(orientation="horizontal",
                        size_hint=(1, None),
                        height=dp(56),
                        padding=(dp(8), dp(8), dp(16), dp(8)),
                        spacing=dp(8))
        self._top = top
        top.add_widget(
            IconButton("back", fg=WHITE, size_dp=40, icon_dp=20,
                       on_click=self._back))
        small = BoxLayout(orientation="vertical")
        self._small_name = _label("", 15, bold=True, halign="left",
                                  shorten=True, shorten_from="right")
        self._small_status = _label("", 12, with_alpha(WHITE, 0.8),
                                    halign="left")
        small.add_widget(self._small_name)
        small.add_widget(self._small_status)
        self._small = small
        top.add_widget(small)
        page.add_widget(top)

        middle = FloatLayout()
        about = BoxLayout(orientation="vertical",
                          size_hint=(0.9, None),
                          height=dp(240),
                          pos_hint={
                              "center_x": 0.5,
                              "center_y": 0.55
                          },
                          spacing=dp(12))
        avatar_wrap = AnchorLayout(size_hint=(1, None), height=dp(128))
        self._avatar = AvatarWidget(key_hex="", name="?",
                                    theme=DARK_THEME, size_dp=128)
        avatar_wrap.add_widget(self._avatar)
        about.add_widget(avatar_wrap)
        self._name = _label("", 26, halign="center", size_hint=(1, None),
                            height=dp(40), shorten=True, shorten_from="right")
        about.add_widget(self._name)
        self._status = _label("", 16, with_alpha(WHITE, 0.8),
                              halign="center", size_hint=(1, None),
                              height=dp(24))
        about.add_widget(self._status)
        self._about = about
        middle.add_widget(about)
        self._self_video = VideoView(fill=True,
                                     size_hint=(None, None),
                                     size=(dp(_SELF_WIDTH_DP),
                                           dp(_SELF_WIDTH_DP * 4 / 3)),
                                     pos_hint={
                                         "right": 0.97,
                                         "top": 0.98
                                     })
        middle.add_widget(self._self_video)
        page.add_widget(middle)

        self._problem = _label("", 14, _PROBLEM, halign="center",
                               size_hint=(1, None), height=0)
        page.add_widget(self._problem)
        self._controls = BoxLayout(orientation="horizontal",
                                   size_hint=(None, None),
                                   height=dp(84),
                                   spacing=dp(12))
        bottom = AnchorLayout(size_hint=(1, None),
                              height=dp(84 + 16 + 32),
                              padding=(0, dp(32), 0, dp(16)))
        bottom.add_widget(self._controls)
        page.add_widget(bottom)
        self.add_widget(page)
        self._control_buttons: list[_CallButton] = []
        self._ticker: Any = None
        self.bind(width=self._fit_controls)

    def _set_ticker(self, active: bool) -> None:
        if active and self._ticker is None:
            self._ticker = Clock.schedule_interval(self._tick, 1.0)
        elif not active and self._ticker is not None:
            self._ticker.cancel()
            self._ticker = None

    def close(self) -> None:
        self._set_ticker(False)

    def _fit_controls(self, *_args: Any) -> None:
        count = len(self._control_buttons)
        if count == 0:
            return
        avail = max(dp(240), self.width - dp(16)) if self.width > 1 else dp(344)
        spacing = dp(12)
        slot = dp(76)
        needed = count * slot + (count - 1) * spacing
        if needed > avail:
            spacing = dp(4) if count >= 5 else dp(8)
            slot = max(dp(56), (avail - (count - 1) * spacing) / count)
        self._controls.spacing = spacing
        for button in self._control_buttons:
            button.set_slot_width(slot)
        self._controls.width = count * slot + (count - 1) * spacing

    def _back(self) -> None:
        self._navigator.back()

    def show_picture(self, who: str, frame: Optional[VideoFrame]) -> None:
        """On the UI thread: the newest picture of the friend, or ours."""
        view = self._friend_video if who == FRIEND else self._self_video
        view.show(frame)
        self._arrange()

    def update(self, state: ClientState) -> None:
        call = state.call
        self._call = call
        if call is None:
            self._set_ticker(False)
            self._controls_sig = None
            self._friend_video.show(None)
            self._self_video.show(None)
            self._arrange()
            return
        self._set_ticker(True)
        friend = next((f for f in state.friends if f.key == call.friend), None)
        name = (friend.display_name
                if friend is not None else call.friend[:SHORT_KEY])
        self._avatar.update(key_hex=call.friend, name=name,
                            theme=DARK_THEME,
                            picture=friend.avatar if friend else None)
        self._name.text = name
        self._small_name.text = name
        if call.problem:
            self._problem.text = call.problem
            self._problem.height = dp(40)
        else:
            self._problem.text = ""
            self._problem.height = 0
        self._tick()
        self._show_controls(call)
        self._arrange()

    def _arrange(self) -> None:
        """The friend's video, or their picture and name."""
        call = self._call
        video = (call is not None and call.answered and call.friend_video
                 and self._friend_video.showing)
        self._about.opacity = 0.0 if video else 1.0
        self._small.opacity = 1.0 if video else 0.0
        self._friend_video.opacity = 1.0 if video else 0.0
        set_bg_color(self._top,
                     with_alpha((0, 0, 0, 1), 0.45) if video else (0, 0, 0, 0))
        self._self_video.opacity = (1.0 if call is not None and call.video
                                    and self._self_video.showing else 0.0)

    def _tick(self, *_args: Any) -> None:
        if self._call is None:
            return
        status = call_status(self._call, _now_ms())
        self._status.text = status
        self._small_status.text = status

    def _show_controls(self, call: Call) -> None:
        cameras = self._platform.cameras
        earpiece = self._platform.has_earpiece
        incoming = not call.outgoing and call.ringing
        sig = (incoming, call.ringing, call.muted, call.video, call.speaker,
               cameras, earpiece)
        if sig == self._controls_sig:
            return
        self._controls_sig = sig
        client = self._client
        ask = self._platform.ask_call_permissions
        buttons: list[_CallButton] = []
        if incoming:
            buttons.append(_action("call_end", "Decline", RED, client.hang_up))
            buttons.append(
                _action("call", "Answer", GREEN,
                        lambda: ask(False, lambda: client.answer(False))))
            if cameras > 0:
                buttons.append(
                    _action("videocam", "With video", GREEN,
                            lambda: ask(True, lambda: client.answer(True))))
        else:
            buttons.append(
                _toggle("mic_off" if call.muted else "mic",
                        "Unmute" if call.muted else "Mute", call.muted,
                        lambda: client.set_muted(not call.muted)))
            if cameras > 0:

                def video() -> None:
                    if call.video:
                        client.set_video(False)
                    else:
                        ask(True, lambda: client.set_video(True))

                buttons.append(
                    _toggle("videocam" if call.video else "videocam_off",
                            "Video", call.video, video))
            if call.video and cameras > 1:
                buttons.append(
                    _toggle("switch_camera", "Flip", False,
                            client.switch_camera))
            if earpiece:
                buttons.append(
                    _toggle("volume_up", "Speaker", call.speaker,
                            lambda: client.set_speaker(not call.speaker)))
            buttons.append(
                _action("call_end", "Cancel" if call.ringing else "Hang up",
                        RED, client.hang_up))
        self._controls.clear_widgets()
        self._control_buttons = buttons
        for button in buttons:
            self._controls.add_widget(button)
        self._fit_controls()


class CallBar(ClickableBox):
    """The call, above the other pages: tapping it goes back to the call."""

    def __init__(self, back_to_call: Callable[[], None]) -> None:
        super().__init__(on_press_cb=back_to_call,
                         bg=GREEN,
                         pressed_bg=with_alpha(GREEN, 0.8),
                         radius=[0],
                         orientation="horizontal",
                         size_hint=(1, None),
                         height=dp(40),
                         padding=(dp(16), 0, dp(16), 0),
                         spacing=dp(12))
        self._what = _label("", 14, halign="left", shorten=True,
                            shorten_from="right")
        self.add_widget(self._what)
        back = _label("Back to the call", 14, bold=True, halign="right",
                      size_hint=(None, 1), width=dp(140))
        self.add_widget(back)
        self._call: Optional[Call] = None
        self._name = ""
        self._ticker: Any = None

    def close(self) -> None:
        if self._ticker is not None:
            self._ticker.cancel()
            self._ticker = None

    def update(self, state: ClientState) -> None:
        self._call = state.call
        if self._call is not None:
            friend = next(
                (f for f in state.friends if f.key == self._call.friend), None)
            self._name = (friend.display_name if friend is not None else
                          self._call.friend[:SHORT_KEY])
            if self._ticker is None:
                self._ticker = Clock.schedule_interval(self._tick, 1.0)
        else:
            if self._ticker is not None:
                self._ticker.cancel()
                self._ticker = None
            self._what.text = ""
        self._tick()

    def _tick(self, *_args: Any) -> None:
        if self._call is not None:
            self._what.text = (
                f"{self._name} · {call_status(self._call, _now_ms())}")
