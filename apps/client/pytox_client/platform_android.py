# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""Android platform implementation built on ``pyjnius`` / ``python-for-android``."""
from __future__ import annotations

import io
import logging
import mimetypes
import os
import secrets
import threading
import zlib
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Optional

from pytox_client.media import Playout
from pytox_client.media import VideoFrame
from pytox_client.media_android import AndroidCamera
from pytox_client.media_android import AndroidSound
from pytox_client.media_android import camera_count
from pytox_client.media_android import has_earpiece
from pytox_client.media_android import support
from pytox_client.model import Call
from pytox_client.model import Friend
from pytox_client.model import FriendRequest
from pytox_client.model import Group
from pytox_client.model import GroupInvite
from pytox_client.model import GroupMessage
from pytox_client.model import Message
from pytox_client.model import PickedFile
from pytox_client.model import SHORT_KEY
from pytox_client.model import shown_text
from pytox_client.platform_base import CallSound
from pytox_client.platform_base import Closeable
from pytox_client.platform_base import Platform
from pytox_client.platform_desktop import encode_avatar_png
from pytox_client.profiles import profile_dir

CHANNEL_MESSAGES = "messages"
CHANNEL_REQUESTS = "requests"
CHANNEL_CONNECTED = "connected"
_MESSAGE_NOTIFY_ID = 1
_REQUEST_NOTIFY_ID = 2
_PICK_REQUEST_CODE = 0x5401
# The service's notification, which keeps it in the foreground.
SERVICE_NOTIFY_ID = 100
_PREFS_NAME = "pytox"
_KEY_STAY_CONNECTED = "stay_connected"
_STAY_CONNECTED_FLAG = ".stay_connected"
# Android 13 has OnBackInvokedCallback. From Android 16, apps targeting it
# don't get the Back key any more: Back leaves the app unless one is set.
_BACK_CALLBACK_SDK = 33
# service_ipc.SOCKET_NAME, which imports far more than this needs.
_SOCKET_NAME = "pytox.sock"
_RECORD_AUDIO = "android.permission.RECORD_AUDIO"
_CAMERA = "android.permission.CAMERA"

_LOG = logging.getLogger("pytox")


def _tag(profile: str, about: str) -> str:
    """A notification's tag: what it's about, in ``profile``."""
    return f"{profile}:{about}"


def is_android() -> bool:
    """Whether PyTox is currently running inside python-for-android."""
    return "ANDROID_ARGUMENT" in os.environ or "ANDROID_PRIVATE" in os.environ


def _in_service() -> bool:
    return "PYTHON_SERVICE_ARGUMENT" in os.environ


def _android_context() -> Any:
    """Return either the foreground Service context or PythonActivity."""
    from jnius import autoclass
    if _in_service():
        return autoclass("org.kivy.android.PythonService").mService
    return autoclass("org.kivy.android.PythonActivity").mActivity


# PyTox's own classes and python-for-android's, which the other threads use.
_APP_CLASSES = (
    "org.kivy.android.PythonActivity",
    "org.kivy.android.PythonService",
    "chat.tox.pytox.support.CallCamera",
    "chat.tox.pytox.support.CallNotices",
    "chat.tox.pytox.support.CallReceiver",
    "chat.tox.pytox.support.CallSound",
    "chat.tox.pytox.support.FileHelper",
)


def _load_app_classes() -> None:
    """Find the app's classes on this thread, the one Android started.

    pyjnius looks classes up with JNI's FindClass, which on threads Python
    started only sees Android's own classes. It keeps what it found, so the
    Tox thread, the switch to the service and the calls' threads use these.
    """
    from jnius import autoclass
    for name in _APP_CLASSES:
        autoclass(name)
    ctx = _android_context()
    autoclass(f"{ctx.getPackageName()}.ServiceTox")


_THREAD_DUMP_FILES: list[Any] = []


def dump_threads_on_signal(directory: Path, name: str) -> None:
    """On SIGUSR2, write where each Python thread is to threads-NAME.txt.

    Uses SIGUSR2 instead of SIGUSR1 to avoid clashing with ART's SignalCatcher.
    For reports: ``adb shell run-as chat.tox.pytox kill -USR2 PID``. Android's
    stderr here is a Python stream, which faulthandler can't write to.
    """
    try:
        import faulthandler
        import signal
        directory.mkdir(parents=True, exist_ok=True)
        out = (directory / f"threads-{name}.txt").open("w")
        # Keep the open file referenced so GC does not close it underneath faulthandler.
        _THREAD_DUMP_FILES.append(out)
        faulthandler.register(signal.SIGUSR2, file=out, all_threads=True)
    except Exception:  # noqa: BLE001
        _LOG.exception("no thread dumps")


def promote_service() -> None:
    """Put the service in the foreground, showing it keeps PyTox connected."""
    try:
        from jnius import autoclass
        service = autoclass("org.kivy.android.PythonService").mService
        ensure_notification_channels(service)
        intent_cls = autoclass("android.content.Intent")
        pending_cls = autoclass("android.app.PendingIntent")
        act_cls = autoclass("org.kivy.android.PythonActivity")
        open_intent = intent_cls(service, act_cls)
        open_intent.setFlags(intent_cls.FLAG_ACTIVITY_NEW_TASK
                             | intent_cls.FLAG_ACTIVITY_SINGLE_TOP)
        pi = pending_cls.getActivity(
            service,
            0,
            open_intent,
            pending_cls.FLAG_IMMUTABLE | pending_cls.FLAG_UPDATE_CURRENT,
        )
        builder_cls = autoclass("android.app.Notification$Builder")
        notif = (builder_cls(service, CHANNEL_CONNECTED)
                 .setSmallIcon(service.getApplicationInfo().icon)
                 .setContentTitle("PyTox is connected")
                 .setContentIntent(pi)
                 .setOngoing(True)
                 .build())
        support("CallNotices").foreground(service, SERVICE_NOTIFY_ID, notif,
                                          False, False)
    except Exception:  # noqa: BLE001
        _LOG.exception("couldn't go to the foreground")


def android_files_dir() -> Path:
    ctx = _android_context()
    return Path(str(ctx.getFilesDir().getAbsolutePath()))


def ensure_notification_channels(ctx: Any) -> None:
    """Create Android 8+ notification channels (matching kTox)."""
    from jnius import autoclass
    build_ver = autoclass("android.os.Build$VERSION").SDK_INT
    if build_ver < 26:
        return
    nm = ctx.getSystemService(ctx.NOTIFICATION_SERVICE)
    chan_cls = autoclass("android.app.NotificationChannel")
    nm_cls = autoclass("android.app.NotificationManager")
    nm.createNotificationChannel(
        chan_cls(CHANNEL_MESSAGES, "Messages", nm_cls.IMPORTANCE_HIGH))
    nm.createNotificationChannel(
        chan_cls(CHANNEL_REQUESTS, "Friend requests",
                 nm_cls.IMPORTANCE_DEFAULT))
    nm.createNotificationChannel(
        chan_cls(CHANNEL_CONNECTED, "Staying connected",
                 nm_cls.IMPORTANCE_MIN))


def request_notification_permission() -> None:
    """Prompt for POST_NOTIFICATIONS on Android 13+ when needed."""
    try:
        from jnius import autoclass
        if autoclass("android.os.Build$VERSION").SDK_INT < 33:
            return
        from android.permissions import check_permission
        from android.permissions import request_permissions
        perm = "android.permission.POST_NOTIFICATIONS"
        if not check_permission(perm):
            request_permissions([perm])
    except Exception:  # noqa: BLE001
        pass


class AndroidPlatform(Platform):
    """Android platform integration via ``pyjnius``."""

    def __init__(self) -> None:
        self._pending_pick: Optional[Callable[[PickedFile], None]] = None
        self._activity_bound = False
        # Only touched on Android's UI thread. Kept here, or Java would hold a
        # callback whose Python half is gone.
        self._back_callback: Any = None
        self._insets_listener: Any = None
        self._hang_up: Any = None
        self._proximity: Any = None
        self._cameras: Optional[int] = None
        self._earpiece: Optional[bool] = None
        # What the call's notification shows now, so it changes only then.
        self._call_notice: Any = None
        try:
            _load_app_classes()
            ensure_notification_channels(_android_context())
        except Exception:  # noqa: BLE001
            _LOG.exception("Android's classes")

    @property
    def can_stay_connected(self) -> bool:
        return True

    def default_profile_dir(self) -> Path:
        try:
            return android_files_dir()
        except Exception:  # noqa: BLE001
            return Path(os.environ.get("ANDROID_PRIVATE", "."))

    def is_stay_connected_pref(self) -> bool:
        try:
            flag = self.default_profile_dir() / _STAY_CONNECTED_FLAG
            if flag.is_file():
                return flag.read_text(encoding="utf-8").strip() == "1"
        except OSError:
            pass
        try:
            ctx = _android_context()
            prefs = ctx.getSharedPreferences(_PREFS_NAME, 0)
            return bool(prefs.getBoolean(_KEY_STAY_CONNECTED, True))
        except Exception:  # noqa: BLE001
            return True

    def set_stay_connected(self, enabled: bool) -> None:
        # Never stopService: python-for-android kills the process in
        # onDestroy, in the middle of saving, and restarts it if asked to.
        # Write a cross-process flag file atomically alongside SharedPreferences
        # because SharedPreferences caches across processes (:service_tox vs UI).
        value = bool(enabled)
        try:
            base = self.default_profile_dir()
            base.mkdir(parents=True, exist_ok=True)
            tmp = base / f"{_STAY_CONNECTED_FLAG}.{os.getpid()}.tmp"
            tmp.write_text("1" if value else "0", encoding="utf-8")
            os.replace(tmp, base / _STAY_CONNECTED_FLAG)
        except OSError:
            pass
        try:
            ctx = _android_context()
            prefs = ctx.getSharedPreferences(_PREFS_NAME, 0)
            prefs.edit().putBoolean(_KEY_STAY_CONNECTED, value).commit()
        except Exception:  # noqa: BLE001
            pass

    def start_service(self) -> None:
        from jnius import autoclass
        ctx = _android_context()
        pkg = str(ctx.getPackageName())
        service_cls = autoclass(f"{pkg}.ServiceTox")
        service_cls.start(ctx, "")

    def copy(self, text: str) -> None:
        try:
            from jnius import autoclass
            ctx = _android_context()
            clip_data = autoclass("android.content.ClipData")
            mgr = ctx.getSystemService(ctx.CLIPBOARD_SERVICE)
            mgr.setPrimaryClip(clip_data.newPlainText("Tox ID", text))
        except Exception:  # noqa: BLE001
            from kivy.core.clipboard import Clipboard
            Clipboard.copy(text)

    def _open_intent(
        self,
        profile: str,
        friend_key: Optional[str],
        group_id: Optional[str] = None,
    ) -> Any:
        """Opens ``profile`` at the friend's or group's chat, if given."""
        from jnius import autoclass
        ctx = _android_context()
        intent_cls = autoclass("android.content.Intent")
        pending_cls = autoclass("android.app.PendingIntent")
        act_cls = autoclass("org.kivy.android.PythonActivity")
        intent = intent_cls(ctx, act_cls)
        intent.setFlags(
            intent_cls.FLAG_ACTIVITY_NEW_TASK
            | intent_cls.FLAG_ACTIVITY_SINGLE_TOP
        )
        intent.putExtra("profile", profile)
        if friend_key is not None:
            intent.putExtra("friend", friend_key)
        if group_id is not None:
            intent.putExtra("group", group_id)
        flags = (pending_cls.FLAG_IMMUTABLE
                 | pending_cls.FLAG_UPDATE_CURRENT)
        target = _tag(profile, friend_key or group_id or "")
        req_code = zlib.crc32(target.encode()) & 0x7FFFFFFF
        return pending_cls.getActivity(ctx, req_code, intent, flags)

    def notify_invite(self, profile: str, friend: Friend,
                      invite: GroupInvite) -> None:
        try:
            from jnius import autoclass
            ctx = _android_context()
            nm = ctx.getSystemService(ctx.NOTIFICATION_SERVICE)
            builder_cls = autoclass("android.app.Notification$Builder")
            notif_cls = autoclass("android.app.Notification")
            icon = ctx.getApplicationInfo().icon
            notif = (
                builder_cls(ctx, CHANNEL_REQUESTS)
                .setSmallIcon(icon)
                .setContentTitle(f"Group invite from {friend.display_name}")
                .setContentText(invite.name)
                .setCategory(notif_cls.CATEGORY_SOCIAL)
                .setAutoCancel(True)
                .setContentIntent(self._open_intent(profile, None))
                .build()
            )
            nm.notify(_tag(profile, invite.data), _REQUEST_NOTIFY_ID, notif)
        except Exception:  # noqa: BLE001
            pass

    def notify_group_message(self, profile: str, group: Group,
                             message: GroupMessage) -> None:
        try:
            from jnius import autoclass
            ctx = _android_context()
            nm = ctx.getSystemService(ctx.NOTIFICATION_SERVICE)
            builder_cls = autoclass("android.app.Notification$Builder")
            style_cls = autoclass("android.app.Notification$BigTextStyle")
            notif_cls = autoclass("android.app.Notification")
            icon = ctx.getApplicationInfo().icon
            body = f"{message.peer_name}: {shown_text(message.text, False)}"
            notif = (
                builder_cls(ctx, CHANNEL_MESSAGES)
                .setSmallIcon(icon)
                .setContentTitle(group.display_name)
                .setContentText(body)
                .setStyle(style_cls().bigText(body))
                .setWhen(message.time)
                .setShowWhen(True)
                .setCategory(notif_cls.CATEGORY_MESSAGE)
                .setAutoCancel(True)
                .setContentIntent(self._open_intent(profile, None, group.id))
                .build()
            )
            nm.notify(_tag(profile, group.id), _MESSAGE_NOTIFY_ID, notif)
        except Exception:  # noqa: BLE001
            pass

    def clear_group_notifications(self, profile: str, group_id: str) -> None:
        try:
            ctx = _android_context()
            nm = ctx.getSystemService(ctx.NOTIFICATION_SERVICE)
            nm.cancel(_tag(profile, group_id), _MESSAGE_NOTIFY_ID)
        except Exception:  # noqa: BLE001
            pass

    def notify_message(self, profile: str, friend: Friend,
                       message: Message) -> None:
        try:
            from jnius import autoclass
            ctx = _android_context()
            nm = ctx.getSystemService(ctx.NOTIFICATION_SERVICE)
            builder_cls = autoclass("android.app.Notification$Builder")
            style_cls = autoclass("android.app.Notification$BigTextStyle")
            notif_cls = autoclass("android.app.Notification")
            text = message.preview(friend.hide_after_zero)
            icon = ctx.getApplicationInfo().icon
            notif = (
                builder_cls(ctx, CHANNEL_MESSAGES)
                .setSmallIcon(icon)
                .setContentTitle(friend.display_name)
                .setContentText(text)
                .setStyle(style_cls().bigText(text))
                .setWhen(message.time)
                .setShowWhen(True)
                .setCategory(notif_cls.CATEGORY_MESSAGE)
                .setAutoCancel(True)
                .setContentIntent(self._open_intent(profile, friend.key))
                .build()
            )
            nm.notify(_tag(profile, friend.key), _MESSAGE_NOTIFY_ID, notif)
        except Exception:  # noqa: BLE001
            pass

    def notify_request(self, profile: str, request: FriendRequest) -> None:
        try:
            from jnius import autoclass
            ctx = _android_context()
            nm = ctx.getSystemService(ctx.NOTIFICATION_SERVICE)
            builder_cls = autoclass("android.app.Notification$Builder")
            notif_cls = autoclass("android.app.Notification")
            icon = ctx.getApplicationInfo().icon
            body = request.message.strip() or request.key[:SHORT_KEY]
            notif = (
                builder_cls(ctx, CHANNEL_REQUESTS)
                .setSmallIcon(icon)
                .setContentTitle("Friend request")
                .setContentText(body)
                .setCategory(notif_cls.CATEGORY_SOCIAL)
                .setAutoCancel(True)
                .setContentIntent(self._open_intent(profile, None))
                .build()
            )
            nm.notify(_tag(profile, request.key), _REQUEST_NOTIFY_ID, notif)
        except Exception:  # noqa: BLE001
            pass

    def clear_notifications(self, profile: str, friend_key: str) -> None:
        try:
            ctx = _android_context()
            nm = ctx.getSystemService(ctx.NOTIFICATION_SERVICE)
            nm.cancel(_tag(profile, friend_key), _MESSAGE_NOTIFY_ID)
        except Exception:  # noqa: BLE001
            pass

    def clear_profile(self, profile: str) -> None:
        try:
            ctx = _android_context()
            nm = ctx.getSystemService(ctx.NOTIFICATION_SERVICE)
            for notice in nm.getActiveNotifications():
                tag = notice.getTag()
                if tag is not None and str(tag).startswith(_tag(profile, "")):
                    nm.cancel(tag, notice.getId())
        except Exception:  # noqa: BLE001
            pass

    def pick_file(
        self,
        images: bool,
        on_picked: Callable[[PickedFile], None],
    ) -> None:
        try:
            from android import activity
            from jnius import autoclass
            if not self._activity_bound:
                activity.bind(on_activity_result=self._on_activity_result)
                self._activity_bound = True
            self._pending_pick = on_picked
            intent_cls = autoclass("android.content.Intent")
            intent = intent_cls(intent_cls.ACTION_OPEN_DOCUMENT)
            intent.addCategory(intent_cls.CATEGORY_OPENABLE)
            intent.setType("image/*" if images else "*/*")
            act = autoclass("org.kivy.android.PythonActivity").mActivity
            act.startActivityForResult(intent, _PICK_REQUEST_CODE)
        except Exception:  # noqa: BLE001
            pass

    def _on_activity_result(
        self,
        request_code: int,
        result_code: int,
        intent: Any,
    ) -> None:
        if request_code != _PICK_REQUEST_CODE:
            return
        callback = self._pending_pick
        self._pending_pick = None
        if callback is None or result_code != -1 or intent is None:
            return
        uri = intent.getData()
        if uri is None:
            return
        ctx = _android_context()
        resolver = ctx.getContentResolver()
        name = _query_display_name(resolver, uri)
        staging = self.default_profile_dir() / "staging"

        def _copy() -> None:
            staged: Optional[Path] = None
            try:
                staging.mkdir(mode=0o700, parents=True, exist_ok=True)
                staged = staging / f"pick-{os.getpid()}-{secrets.token_hex(12)}.bin"
                ok = bool(support("FileHelper").copyUriToFile(
                    resolver, uri, str(staged)))
                if not ok:
                    staged.unlink(missing_ok=True)
                    return
                picked_path = staged
                staged = None

                def _open_picked(p: Path = picked_path) -> Any:
                    return _UnlinkFileReader(p)

                callback(PickedFile(name=name, open_stream=_open_picked))
            except Exception:  # noqa: BLE001
                _LOG.exception("failed to read picked URI")
                if staged is not None:
                    staged.unlink(missing_ok=True)

        threading.Thread(target=_copy, name="pytox-pick", daemon=True).start()

    def open_file(self, path: Path, name: str) -> None:
        try:
            from jnius import autoclass
            ctx = _android_context()
            java_file = autoclass("java.io.File")(str(path))
            fp = autoclass("androidx.core.content.FileProvider")
            authority = f"{ctx.getPackageName()}.files"
            uri = fp.getUriForFile(ctx, authority, java_file)
            mime, _ = mimetypes.guess_type(name)
            intent_cls = autoclass("android.content.Intent")
            view = intent_cls(intent_cls.ACTION_VIEW)
            view.setDataAndType(uri, mime or "*/*")
            view.addFlags(
                intent_cls.FLAG_GRANT_READ_URI_PERMISSION
                | intent_cls.FLAG_ACTIVITY_NEW_TASK
            )
            chooser = intent_cls.createChooser(view, name)
            chooser.addFlags(intent_cls.FLAG_ACTIVITY_NEW_TASK)
            ctx.startActivity(chooser)
        except Exception:  # noqa: BLE001
            pass

    def save_to_downloads(self, path: Path, name: str) -> Optional[str]:
        uri: Any = None
        resolver: Any = None
        try:
            from jnius import autoclass
            ctx = _android_context()
            resolver = ctx.getContentResolver()
            values = autoclass("android.content.ContentValues")()
            downloads_cls = autoclass("android.provider.MediaStore$Downloads")
            java_int = autoclass("java.lang.Integer")
            mime, _ = mimetypes.guess_type(name)
            values.put(downloads_cls.DISPLAY_NAME, name)
            values.put(downloads_cls.MIME_TYPE,
                       mime or "application/octet-stream")
            values.put(downloads_cls.IS_PENDING, java_int(1))
            uri = resolver.insert(downloads_cls.EXTERNAL_CONTENT_URI, values)
            if uri is None:
                return None
            ok = bool(support("FileHelper").copyFileToUri(
                resolver, str(path), uri))
            if not ok:
                resolver.delete(uri, None, None)
                return None
            done_vals = autoclass("android.content.ContentValues")()
            done_vals.put(downloads_cls.IS_PENDING, java_int(0))
            resolver.update(uri, done_vals, None, None)
            uri = None
            return "Downloads"
        except Exception:  # noqa: BLE001
            _LOG.exception("couldn't save %r to Downloads", name)
            if uri is not None and resolver is not None:
                try:
                    resolver.delete(uri, None, None)
                except Exception:  # noqa: BLE001
                    pass
            return None

    def avatar_png(self, image: bytes, size: int) -> Optional[bytes]:
        return encode_avatar_png(image, size)

    def window_insets(self) -> tuple[int, int, int, int]:
        try:
            from jnius import autoclass
            act = autoclass("org.kivy.android.PythonActivity").mActivity
            insets = act.getWindow().getDecorView().getRootWindowInsets()
            if insets is None:
                return (0, 0, 0, 0)
            sdk = autoclass("android.os.Build$VERSION").SDK_INT
            if sdk >= 30:
                types = autoclass("android.view.WindowInsets$Type")
                # The union: the bars, the cutout and, when it's up, the
                # keyboard, which covers the navigation bar at the bottom.
                bars = insets.getInsets(
                    types.systemBars() | types.displayCutout() | types.ime())
                return (bars.left, bars.top, bars.right, bars.bottom)
            return (
                insets.getSystemWindowInsetLeft(),
                insets.getSystemWindowInsetTop(),
                insets.getSystemWindowInsetRight(),
                insets.getSystemWindowInsetBottom(),
            )
        except Exception:  # noqa: BLE001
            return (0, 0, 0, 0)

    def prepare_window(self, insets_changed: Callable[[], None]) -> None:
        try:
            from android.runnable import run_on_ui_thread
            from jnius import autoclass
        except ImportError:
            return

        @run_on_ui_thread  # type: ignore[misc]
        def _apply() -> None:
            try:
                act = autoclass("org.kivy.android.PythonActivity").mActivity
                window = act.getWindow()
                params = autoclass("android.view.WindowManager$LayoutParams")
                # Drawn edge-to-edge on every version (Android 15 enforces
                # it), so the UI pads itself by window_insets(), the
                # keyboard's included. Resize mode, as edge-to-edge, keeps
                # Android from panning the window to a text field it can't
                # see (Kivy draws them).
                window.setSoftInputMode(params.SOFT_INPUT_ADJUST_RESIZE)
                sdk = autoclass("android.os.Build$VERSION").SDK_INT
                if sdk >= 30:
                    window.setDecorFitsSystemWindows(False)
                else:
                    view = autoclass("android.view.View")
                    window.getDecorView().setSystemUiVisibility(
                        view.SYSTEM_UI_FLAG_LAYOUT_STABLE
                        | view.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                        | view.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION)
                if sdk < 35:
                    color = autoclass("android.graphics.Color")
                    window.setStatusBarColor(color.TRANSPARENT)
                    window.setNavigationBarColor(color.TRANSPARENT)
                surface = autoclass(
                    "org.kivy.android.PythonActivity").getSurface()
                if surface is not None:
                    # SDL's surface keeps the focus. Once a hardware key
                    # leaves touch mode, Android greys the whole focused view
                    # with its default highlight, and it stays.
                    surface.setDefaultFocusHighlightEnabled(False)
                    # Edge-to-edge, the keyboard only changes the insets.
                    self._insets_listener = _insets_listener(insets_changed)
                    surface.setOnApplyWindowInsetsListener(
                        self._insets_listener)
            except Exception:  # noqa: BLE001
                _LOG.exception("can't prepare the window")

        _apply()

    def set_light_system_bars(self, light: bool) -> None:
        try:
            from android.runnable import run_on_ui_thread
            from jnius import autoclass
        except ImportError:
            return

        @run_on_ui_thread  # type: ignore[misc]
        def _apply() -> None:
            try:
                if autoclass("android.os.Build$VERSION").SDK_INT < 30:
                    return
                act = autoclass("org.kivy.android.PythonActivity").mActivity
                ctrl = act.getWindow().getInsetsController()
                if ctrl is None:
                    return
                wic = autoclass("android.view.WindowInsetsController")
                mask = (wic.APPEARANCE_LIGHT_STATUS_BARS
                        | wic.APPEARANCE_LIGHT_NAVIGATION_BARS)
                ctrl.setSystemBarsAppearance(mask if light else 0, mask)
            except Exception:  # noqa: BLE001
                pass

        _apply()

    def set_back_handler(self, on_back: Optional[Callable[[], None]]) -> None:
        try:
            from android.runnable import run_on_ui_thread
            from jnius import autoclass
            sdk = autoclass("android.os.Build$VERSION").SDK_INT
            if sdk < _BACK_CALLBACK_SDK:
                # The Back key still comes, as Escape.
                return
        except ImportError:
            return

        @run_on_ui_thread  # type: ignore[misc]
        def _apply() -> None:
            try:
                act = autoclass("org.kivy.android.PythonActivity").mActivity
                dispatcher = act.getOnBackInvokedDispatcher()
                if self._back_callback is not None:
                    dispatcher.unregisterOnBackInvokedCallback(
                        self._back_callback)
                    self._back_callback = None
                if on_back is not None:
                    self._back_callback = _back_callback(on_back)
                    dispatcher.registerOnBackInvokedCallback(
                        autoclass("android.window.OnBackInvokedDispatcher")
                        .PRIORITY_DEFAULT,
                        self._back_callback,
                    )
            except Exception:  # noqa: BLE001
                _LOG.exception("can't update back handler")

        _apply()

    def log(self, message: str) -> None:
        try:
            from jnius import autoclass
            autoclass("android.util.Log").i("PyTox", message)
        except Exception:  # noqa: BLE001
            super().log(message)

    def open_sound(
        self,
        recorded: Callable[[bytes], None],
        playout: Playout,
    ) -> Optional[CallSound]:
        try:
            return AndroidSound(_android_context(), recorded, playout)
        except Exception:  # noqa: BLE001
            _LOG.exception("no sound")
            return None

    @property
    def cameras(self) -> int:
        if self._cameras is None:
            try:
                self._cameras = camera_count(_android_context())
            except Exception:  # noqa: BLE001
                self._cameras = 0
        return self._cameras

    def open_camera(
        self,
        front: bool,
        frame: Callable[[VideoFrame], None],
    ) -> Optional[Closeable]:
        try:
            return AndroidCamera.open(_android_context(), front, frame)
        except Exception:  # noqa: BLE001
            _LOG.exception("no camera")
            return None

    @property
    def has_earpiece(self) -> bool:
        if self._earpiece is None:
            try:
                self._earpiece = has_earpiece(_android_context())
            except Exception:  # noqa: BLE001
                self._earpiece = False
        return self._earpiece

    def call_changed(self, profile: str, call: Optional[Call],
                     friend: Optional[Friend]) -> None:
        name = (friend.display_name if friend is not None else
                call.friend[:SHORT_KEY] if call is not None else "")
        if call is None:
            notice: Any = None
        elif call.ringing and not call.outgoing:
            notice = ("ringing", name, call.video_call)
        else:
            notice = ("on", name, call.video_call, call.video, call.answered,
                      call.started)
        if notice == self._call_notice:
            return
        try:
            ctx = _android_context()
            notices = support("CallNotices")
            directory = profile_dir(self.default_profile_dir(), profile)
            socket = str(directory / _SOCKET_NAME)
            if call is not None and notice[0] == "ringing":
                notices.ring(ctx, name, call.video_call, socket)
                self._call_notice = notice
                return
            notices.stopRinging(ctx)
            if not _in_service():
                # The app is on screen: it shows the call itself.
                self._call_notice = notice
                return
            if call is None:
                promote_service()
            else:
                # Only request camera FGS type when actually sending video.
                started_ms = call.started if call.answered else 0
                notices.foreground(
                    ctx, SERVICE_NOTIFY_ID,
                    notices.ongoing(ctx, name, call.video_call, started_ms,
                                    socket),
                    True, bool(call.video))
            self._call_notice = notice
        except Exception:  # noqa: BLE001
            _LOG.exception("couldn't show the call")

    def ask_call_permissions(self, video: bool, then: Callable[[],
                                                               None]) -> None:
        try:
            from android.permissions import check_permission
            from android.permissions import request_permissions
            from kivy.clock import Clock
        except ImportError:
            then()
            return
        wanted = [_RECORD_AUDIO] + ([_CAMERA] if video else [])
        missing = [p for p in wanted if not check_permission(p)]
        if not missing:
            then()
            return

        def answered(_permissions: Any, _grants: Any) -> None:
            # On Android's thread: the UI's goes on.
            Clock.schedule_once(lambda _dt: then(), 0)

        request_permissions(missing, answered)

    def call_on_screen(self, call: Optional[Call]) -> None:
        try:
            from android.runnable import run_on_ui_thread
            from jnius import autoclass
        except ImportError:
            return
        # Held to the ear: the screen goes off, so a cheek doesn't tap it.
        ear = call is not None and not call.speaker and not call.video

        @run_on_ui_thread  # type: ignore[misc]
        def _apply() -> None:
            try:
                act = autoclass("org.kivy.android.PythonActivity").mActivity
                params = autoclass("android.view.WindowManager$LayoutParams")
                window = act.getWindow()
                if call is not None:
                    window.addFlags(params.FLAG_KEEP_SCREEN_ON)
                else:
                    window.clearFlags(params.FLAG_KEEP_SCREEN_ON)
                if ear and self._proximity is None:
                    pm_cls = autoclass("android.os.PowerManager")
                    power = act.getSystemService(act.POWER_SERVICE)
                    level = pm_cls.PROXIMITY_SCREEN_OFF_WAKE_LOCK
                    if power.isWakeLockLevelSupported(level):
                        lock = power.newWakeLock(level, "pytox:call")
                        lock.acquire()
                        self._proximity = lock
                elif not ear and self._proximity is not None:
                    lock, self._proximity = self._proximity, None
                    if lock.isHeld():
                        lock.release()
            except Exception:  # noqa: BLE001
                _LOG.exception("couldn't keep the screen for the call")

        _apply()

    def listen_for_hang_up(
        self, hang_up: Optional[Callable[[], None]]
    ) -> None:
        """Register or clear the notification hang-up listener."""
        try:
            if hang_up is None:
                support("CallReceiver").setListener(None)
                self._hang_up = None
            else:
                self._hang_up = _hang_up_listener(hang_up)
                support("CallReceiver").setListener(self._hang_up)
        except Exception:  # noqa: BLE001
            _LOG.exception("no hanging up from notifications")

    def is_dark_mode(self) -> bool:
        try:
            from jnius import autoclass
            ctx = _android_context()
            cfg = ctx.getResources().getConfiguration()
            cfg_cls = autoclass("android.content.res.Configuration")
            mask = cfg.uiMode & cfg_cls.UI_MODE_NIGHT_MASK
            return bool(mask == cfg_cls.UI_MODE_NIGHT_YES)
        except Exception:  # noqa: BLE001
            return False


def _back_callback(on_back: Callable[[], None]) -> Any:
    """An ``OnBackInvokedCallback`` calling ``on_back``."""
    from jnius import PythonJavaClass
    from jnius import java_method

    class _BackCallback(PythonJavaClass):  # type: ignore[misc]
        __javainterfaces__ = ["android/window/OnBackInvokedCallback"]
        __javacontext__ = "app"

        @java_method("()V")  # type: ignore[misc]
        def onBackInvoked(self) -> None:
            on_back()

    return _BackCallback()


def _insets_listener(changed: Callable[[], None]) -> Any:
    """An ``OnApplyWindowInsetsListener`` calling ``changed``."""
    from jnius import PythonJavaClass
    from jnius import java_method

    class _Insets(PythonJavaClass):  # type: ignore[misc]
        __javainterfaces__ = ["android/view/View$OnApplyWindowInsetsListener"]
        __javacontext__ = "app"

        @java_method("(Landroid/view/View;Landroid/view/WindowInsets;)"
                     "Landroid/view/WindowInsets;")  # type: ignore[misc]
        def onApplyWindowInsets(self, _view: Any, insets: Any) -> Any:
            changed()
            return insets

    return _Insets()


def _hang_up_listener(hang_up: Callable[[], None]) -> Any:
    """A ``CallReceiver.Listener`` calling ``hang_up``."""
    from jnius import PythonJavaClass
    from jnius import java_method

    class _HangUp(PythonJavaClass):  # type: ignore[misc]
        __javainterfaces__ = ["chat/tox/pytox/support/CallReceiver$Listener"]
        __javacontext__ = "app"

        @java_method("()V")  # type: ignore[misc]
        def onHangUp(self) -> None:
            hang_up()

    return _HangUp()


def _query_display_name(resolver: Any, uri: Any) -> str:
    try:
        from jnius import autoclass
        cols = autoclass("android.provider.OpenableColumns")
        cursor = resolver.query(uri, [cols.DISPLAY_NAME], None, None, None)
        if cursor is not None:
            try:
                if cursor.moveToFirst():
                    val = cursor.getString(0)
                    if val:
                        return str(val)
            finally:
                cursor.close()
    except Exception:  # noqa: BLE001
        pass
    seg = uri.getLastPathSegment()
    return str(seg) if seg else "file"


class _UnlinkFileReader(io.BufferedReader):
    """Readable binary file stream that deletes a staged pick file on close."""

    def __init__(self, path: Path) -> None:
        super().__init__(io.FileIO(path, "rb"))
        self._path = path

    def close(self) -> None:
        try:
            super().close()
        finally:
            self._path.unlink(missing_ok=True)
