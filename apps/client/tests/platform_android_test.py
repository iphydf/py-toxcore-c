# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""Unit tests for AndroidPlatform window/inset JNI calls via stubbed pyjnius."""
from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Optional
from unittest.mock import patch

from pytox_client.model import Call
from pytox_client.platform_android import AndroidPlatform
from pytox_client.platform_android import request_notification_permission


class _InsetsRect:

    def __init__(self, left: int, top: int, right: int, bottom: int) -> None:
        self.left = left
        self.top = top
        self.right = right
        self.bottom = bottom


class _FakeWindowInsets:

    def __init__(
        self,
        modern: Optional[_InsetsRect] = None,
        legacy: tuple[int, int, int, int] = (0, 0, 0, 0),
    ) -> None:
        self._modern = modern or _InsetsRect(0, 0, 0, 0)
        self._legacy = legacy
        self.requested_masks: list[int] = []

    def getInsets(self, mask: int) -> _InsetsRect:
        self.requested_masks.append(mask)
        return self._modern

    def getSystemWindowInsetLeft(self) -> int:
        return self._legacy[0]

    def getSystemWindowInsetTop(self) -> int:
        return self._legacy[1]

    def getSystemWindowInsetRight(self) -> int:
        return self._legacy[2]

    def getSystemWindowInsetBottom(self) -> int:
        return self._legacy[3]


class _FakeInsetsController:

    def __init__(self) -> None:
        self.calls: list[tuple[int, int]] = []

    def setSystemBarsAppearance(self, appearance: int, mask: int) -> None:
        self.calls.append((appearance, mask))


class _FakeDecorView:

    def __init__(self, insets: Optional[_FakeWindowInsets]) -> None:
        self._insets = insets
        self.system_ui_visibility: list[int] = []

    def getRootWindowInsets(self) -> Optional[_FakeWindowInsets]:
        return self._insets

    def setSystemUiVisibility(self, flags: int) -> None:
        self.system_ui_visibility.append(flags)


class _FakeWindow:

    def __init__(
        self,
        decor: _FakeDecorView,
        controller: Optional[_FakeInsetsController],
    ) -> None:
        self._decor = decor
        self._controller = controller
        self.soft_input_modes: list[int] = []
        self.decor_fits: list[bool] = []
        self.status_bar_colors: list[int] = []
        self.nav_bar_colors: list[int] = []

    def getDecorView(self) -> _FakeDecorView:
        return self._decor

    def getInsetsController(self) -> Optional[_FakeInsetsController]:
        return self._controller

    def setSoftInputMode(self, mode: int) -> None:
        self.soft_input_modes.append(mode)

    def setDecorFitsSystemWindows(self, fits: bool) -> None:
        self.decor_fits.append(fits)

    def setStatusBarColor(self, color: int) -> None:
        self.status_bar_colors.append(color)

    def setNavigationBarColor(self, color: int) -> None:
        self.nav_bar_colors.append(color)


class _FakeSurface:

    def __init__(self) -> None:
        self.focus_highlights: list[bool] = []
        self.insets_listeners: list[Any] = []

    def setDefaultFocusHighlightEnabled(self, enabled: bool) -> None:
        self.focus_highlights.append(enabled)

    def setOnApplyWindowInsetsListener(self, listener: Any) -> None:
        self.insets_listeners.append(listener)


class _FakeBackDispatcher:

    def __init__(self) -> None:
        self.registered: list[tuple[int, Any]] = []
        self.unregistered: list[Any] = []

    def registerOnBackInvokedCallback(self, priority: int, cb: Any) -> None:
        self.registered.append((priority, cb))

    def unregisterOnBackInvokedCallback(self, cb: Any) -> None:
        self.unregistered.append(cb)


class _FakeNotificationManager:

    def __init__(self) -> None:
        self.channels: list[Any] = []

    def createNotificationChannel(self, channel: Any) -> None:
        self.channels.append(channel)


class _FakeActivity:
    NOTIFICATION_SERVICE = "notification"

    def __init__(self, window: _FakeWindow) -> None:
        self._window = window
        self.back_dispatcher = _FakeBackDispatcher()
        self.notification_manager = _FakeNotificationManager()

    def getWindow(self) -> _FakeWindow:
        return self._window

    def getPackageName(self) -> str:
        return "chat.tox.pytox"

    def getSystemService(self, _name: str) -> _FakeNotificationManager:
        return self.notification_manager

    def getOnBackInvokedDispatcher(self) -> _FakeBackDispatcher:
        return self.back_dispatcher


class _WindowInsetsType:
    SYSTEM_BARS = 0x07
    DISPLAY_CUTOUT = 0x80
    IME = 0x08

    @staticmethod
    def systemBars() -> int:
        return _WindowInsetsType.SYSTEM_BARS

    @staticmethod
    def displayCutout() -> int:
        return _WindowInsetsType.DISPLAY_CUTOUT

    @staticmethod
    def ime() -> int:
        return _WindowInsetsType.IME


class _LayoutParams:
    SOFT_INPUT_ADJUST_RESIZE = 16


class _ViewConstants:
    SYSTEM_UI_FLAG_LAYOUT_STABLE = 0x00000100
    SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION = 0x00000200
    SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN = 0x00000400


class _ColorConstants:
    TRANSPARENT = 0


class _WindowInsetsControllerConstants:
    APPEARANCE_LIGHT_STATUS_BARS = 1 << 3
    APPEARANCE_LIGHT_NAVIGATION_BARS = 1 << 4


class _BackDispatcherConstants:
    PRIORITY_DEFAULT = 0


class _NotificationManagerConstants:
    IMPORTANCE_HIGH = 4
    IMPORTANCE_DEFAULT = 3
    IMPORTANCE_MIN = 1


class _FakePythonJavaClass:
    pass


def _fake_java_method(_sig: str) -> Callable[[Any], Any]:
    return lambda fn: fn


class _AndroidEnv:
    """Builds stub ``jnius`` and ``android.runnable`` modules for a given API."""

    def __init__(
        self,
        sdk: int,
        *,
        insets: Optional[_FakeWindowInsets] = None,
        has_surface: bool = True,
        has_insets_controller: bool = True,
    ) -> None:
        self.sdk = sdk
        self.decor = _FakeDecorView(insets)
        self.controller = (
            _FakeInsetsController() if has_insets_controller else None)
        self.window = _FakeWindow(self.decor, self.controller)
        self.activity = _FakeActivity(self.window)
        self.surface: Optional[_FakeSurface] = (
            _FakeSurface() if has_surface else None)

        build_ver = type("VERSION", (), {"SDK_INT": sdk})
        surface_ref = self.surface
        activity_cls = type(
            "PythonActivity",
            (),
            {
                "mActivity": self.activity,
                "getSurface": staticmethod(lambda: surface_ref),
            },
        )
        dummy_cls = type("Stub", (), {})
        classes: dict[str, Any] = {
            "org.kivy.android.PythonActivity": activity_cls,
            "org.kivy.android.PythonService": dummy_cls,
            "chat.tox.pytox.ServiceTox": dummy_cls,
            "chat.tox.pytox.support.CallCamera": dummy_cls,
            "chat.tox.pytox.support.CallNotices": dummy_cls,
            "chat.tox.pytox.support.CallReceiver": dummy_cls,
            "chat.tox.pytox.support.CallSound": dummy_cls,
            "chat.tox.pytox.support.FileHelper": dummy_cls,
            "android.app.NotificationChannel": lambda *a: a,
            "android.app.NotificationManager": _NotificationManagerConstants,
            "android.os.Build$VERSION": build_ver,
            "android.view.WindowInsets$Type": _WindowInsetsType,
            "android.view.WindowManager$LayoutParams": _LayoutParams,
            "android.view.View": _ViewConstants,
            "android.graphics.Color": _ColorConstants,
            "android.view.WindowInsetsController":
                _WindowInsetsControllerConstants,
            "android.window.OnBackInvokedDispatcher": _BackDispatcherConstants,
        }
        self._classes = classes

        jnius_mod = types.ModuleType("jnius")
        jnius_mod.__dict__["autoclass"] = self._autoclass
        jnius_mod.__dict__["PythonJavaClass"] = _FakePythonJavaClass
        jnius_mod.__dict__["java_method"] = _fake_java_method

        android_mod = types.ModuleType("android")
        runnable_mod = types.ModuleType("android.runnable")
        runnable_mod.__dict__["run_on_ui_thread"] = lambda fn: fn
        android_mod.__dict__["runnable"] = runnable_mod

        self.modules: dict[str, types.ModuleType] = {
            "jnius": jnius_mod,
            "android": android_mod,
            "android.runnable": runnable_mod,
        }

    def _autoclass(self, name: str) -> Any:
        if name not in self._classes:
            raise KeyError(f"unexpected autoclass lookup: {name}")
        return self._classes[name]

    def replace_window(self, insets: Optional[_FakeWindowInsets] = None) -> None:
        """Simulate Android giving the Activity a fresh Window after resume."""
        self.decor = _FakeDecorView(insets)
        self.controller = _FakeInsetsController()
        self.window = _FakeWindow(self.decor, self.controller)
        self.activity._window = self.window


class AndroidPlatformWindowTest(unittest.TestCase):

    def test_window_insets_api_30_plus_includes_ime_and_cutout(self) -> None:
        fake_insets = _FakeWindowInsets(modern=_InsetsRect(0, 63, 0, 812))
        env = _AndroidEnv(sdk=36, insets=fake_insets)
        with patch.dict(sys.modules, env.modules):
            platform = AndroidPlatform()
            self.assertEqual(platform.window_insets(), (0, 63, 0, 812))
        expected_mask = (
            _WindowInsetsType.SYSTEM_BARS
            | _WindowInsetsType.DISPLAY_CUTOUT
            | _WindowInsetsType.IME
        )
        self.assertEqual(fake_insets.requested_masks, [expected_mask])

    def test_window_insets_api_29_uses_legacy_getters(self) -> None:
        fake_insets = _FakeWindowInsets(legacy=(4, 48, 4, 600))
        env = _AndroidEnv(sdk=29, insets=fake_insets)
        with patch.dict(sys.modules, env.modules):
            platform = AndroidPlatform()
            self.assertEqual(platform.window_insets(), (4, 48, 4, 600))
        self.assertEqual(fake_insets.requested_masks, [])

    def test_window_insets_none_or_missing_jnius_returns_zero(self) -> None:
        env = _AndroidEnv(sdk=36, insets=None)
        with patch.dict(sys.modules, env.modules):
            platform = AndroidPlatform()
            self.assertEqual(platform.window_insets(), (0, 0, 0, 0))
        with patch.dict(sys.modules, {"jnius": None}):
            self.assertEqual(platform.window_insets(), (0, 0, 0, 0))

    def test_prepare_window_api_36_edge_to_edge_and_surface(self) -> None:
        env = _AndroidEnv(sdk=36)
        calls: list[int] = []
        with patch.dict(sys.modules, env.modules):
            platform = AndroidPlatform()
            platform.prepare_window(lambda: calls.append(1))
        self.assertEqual(
            env.window.soft_input_modes,
            [_LayoutParams.SOFT_INPUT_ADJUST_RESIZE],
        )
        self.assertEqual(env.window.decor_fits, [False])
        # API 35+ deprecates bar colors and enforces edge-to-edge natively.
        self.assertEqual(env.window.status_bar_colors, [])
        self.assertEqual(env.window.nav_bar_colors, [])
        assert env.surface is not None
        # Disable the grey focus highlight shown when leaving touch mode.
        self.assertEqual(env.surface.focus_highlights, [False])
        self.assertEqual(len(env.surface.insets_listeners), 1)
        listener = env.surface.insets_listeners[0]
        # Must stay referenced on the Python object so Java holds a live ref.
        self.assertIs(platform._insets_listener, listener)
        sentinel = object()
        self.assertIs(listener.onApplyWindowInsets(None, sentinel), sentinel)
        self.assertEqual(calls, [1])

    def test_prepare_window_api_30_to_34_clears_bar_colors(self) -> None:
        for sdk in (30, 34):
            env = _AndroidEnv(sdk=sdk)
            with patch.dict(sys.modules, env.modules):
                platform = AndroidPlatform()
                platform.prepare_window(lambda: None)
            self.assertEqual(env.window.decor_fits, [False])
            self.assertEqual(
                env.window.status_bar_colors, [_ColorConstants.TRANSPARENT])
            self.assertEqual(
                env.window.nav_bar_colors, [_ColorConstants.TRANSPARENT])
            self.assertEqual(env.decor.system_ui_visibility, [])

    def test_prepare_window_api_29_uses_legacy_edge_to_edge_flags(self) -> None:
        env = _AndroidEnv(sdk=29)
        with patch.dict(sys.modules, env.modules):
            platform = AndroidPlatform()
            platform.prepare_window(lambda: None)
        self.assertEqual(
            env.window.soft_input_modes,
            [_LayoutParams.SOFT_INPUT_ADJUST_RESIZE],
        )
        self.assertEqual(env.window.decor_fits, [])
        expected_flags = (
            _ViewConstants.SYSTEM_UI_FLAG_LAYOUT_STABLE
            | _ViewConstants.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
            | _ViewConstants.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
        )
        self.assertEqual(env.decor.system_ui_visibility, [expected_flags])
        self.assertEqual(
            env.window.status_bar_colors, [_ColorConstants.TRANSPARENT])
        self.assertEqual(
            env.window.nav_bar_colors, [_ColorConstants.TRANSPARENT])

    def test_prepare_window_without_surface_does_not_fail(self) -> None:
        env = _AndroidEnv(sdk=36, has_surface=False)
        with patch.dict(sys.modules, env.modules):
            platform = AndroidPlatform()
            platform.prepare_window(lambda: None)
        self.assertEqual(
            env.window.soft_input_modes,
            [_LayoutParams.SOFT_INPUT_ADJUST_RESIZE],
        )
        self.assertIsNone(platform._insets_listener)

    def test_prepare_window_reapplies_after_window_replaced(self) -> None:
        env = _AndroidEnv(sdk=36)
        with patch.dict(sys.modules, env.modules):
            platform = AndroidPlatform()
            platform.prepare_window(lambda: None)
            env.replace_window()
            platform.prepare_window(lambda: None)
        self.assertEqual(
            env.window.soft_input_modes,
            [_LayoutParams.SOFT_INPUT_ADJUST_RESIZE],
        )
        self.assertEqual(env.window.decor_fits, [False])

    def test_set_light_system_bars(self) -> None:
        mask = (
            _WindowInsetsControllerConstants.APPEARANCE_LIGHT_STATUS_BARS
            | _WindowInsetsControllerConstants.APPEARANCE_LIGHT_NAVIGATION_BARS
        )
        env = _AndroidEnv(sdk=30)
        with patch.dict(sys.modules, env.modules):
            platform = AndroidPlatform()
            platform.set_light_system_bars(True)
            platform.set_light_system_bars(False)
        assert env.controller is not None
        self.assertEqual(env.controller.calls, [(mask, mask), (0, mask)])

        old_env = _AndroidEnv(sdk=29)
        with patch.dict(sys.modules, old_env.modules):
            old_platform = AndroidPlatform()
            old_platform.set_light_system_bars(True)
        assert old_env.controller is not None
        self.assertEqual(old_env.controller.calls, [])

    def test_set_back_handler_registers_and_unregisters(self) -> None:
        env = _AndroidEnv(sdk=33)
        invoked: list[str] = []
        with patch.dict(sys.modules, env.modules):
            platform = AndroidPlatform()
            platform.set_back_handler(lambda: invoked.append("first"))
            self.assertEqual(len(env.activity.back_dispatcher.registered), 1)
            _, first_cb = env.activity.back_dispatcher.registered[0]
            first_cb.onBackInvoked()
            self.assertEqual(invoked, ["first"])

            platform.set_back_handler(None)
            self.assertEqual(
                env.activity.back_dispatcher.unregistered, [first_cb])
            self.assertIsNone(platform._back_callback)

        old_env = _AndroidEnv(sdk=32)
        with patch.dict(sys.modules, old_env.modules):
            old_platform = AndroidPlatform()
            old_platform.set_back_handler(lambda: invoked.append("ignored"))
        self.assertEqual(old_env.activity.back_dispatcher.registered, [])

    def test_stay_connected_flag_file_overrides_cached_prefs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = _AndroidEnv(sdk=36)
            with patch.dict(sys.modules, env.modules), patch.object(
                AndroidPlatform, "default_profile_dir", return_value=root
            ):
                platform = AndroidPlatform()
                platform.set_stay_connected(False)
                self.assertFalse(platform.is_stay_connected_pref())
                platform.set_stay_connected(True)
                self.assertTrue(platform.is_stay_connected_pref())

    def test_request_notification_permission_skips_below_api_33(self) -> None:
        env = _AndroidEnv(sdk=32)
        asked: list[Any] = []
        perms_mod = types.ModuleType("android.permissions")
        perms_mod.__dict__["check_permission"] = lambda _p: False
        perms_mod.__dict__["request_permissions"] = asked.append
        modules = {**env.modules, "android.permissions": perms_mod}
        with patch.dict(sys.modules, modules):
            request_notification_permission()
        self.assertEqual(asked, [])

    def test_listen_for_hang_up_clears_and_call_changed_retries_on_error(
            self) -> None:
        env = _AndroidEnv(sdk=36)
        listeners: list[Any] = []
        env._classes["chat.tox.pytox.support.CallReceiver"] = type(
            "CallReceiver", (), {
                "setListener": staticmethod(listeners.append),
            })
        should_fail = [True]

        class _FakeNotices:
            @staticmethod
            def ring(*_args: Any) -> None:
                if should_fail[0]:
                    raise RuntimeError("transient notification failure")

            @staticmethod
            def stopRinging(*_args: Any) -> None:
                pass

        env._classes["chat.tox.pytox.support.CallNotices"] = _FakeNotices
        with patch.dict(sys.modules, env.modules):
            platform = AndroidPlatform()
            platform.listen_for_hang_up(lambda: None)
            self.assertEqual(len(listeners), 1)
            self.assertIsNotNone(listeners[0])
            platform.listen_for_hang_up(None)
            self.assertIsNone(listeners[-1])
            self.assertIsNone(platform._hang_up)

            call = Call(friend="AA" * 32, outgoing=False, video_call=False)
            platform.call_changed("1", call, None)
            # Failure must NOT cache the notice key so a retry can succeed.
            self.assertIsNone(platform._call_notice)
            should_fail[0] = False
            platform.call_changed("1", call, None)
            self.assertIsNotNone(platform._call_notice)


if __name__ == "__main__":
    unittest.main()
