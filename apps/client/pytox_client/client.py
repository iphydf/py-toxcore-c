# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""Dedicated single-thread Tox engine behind PyTox.

One Tox profile lives in ``directory``:
  * ``profile.tox`` — toxcore save data (written atomically)
  * ``chats.db``    — SQLite store (schema-compatible with kTox)
  * ``files/``      — sent & received files (one random subdirectory per file)
  * ``avatars/``    — received friend avatar PNGs
  * ``avatar.png``  — our own avatar PNG

All ``toxcore`` and SQLite calls happen strictly on one daemon thread. The UI
reads immutable :class:`ClientState` snapshots via :meth:`subscribe` or
:attr:`state`, and posts actions via the thread-safe methods on
:class:`ToxClient`.
"""
from __future__ import annotations

import errno
import logging
import os
import queue
import random
import secrets
import shutil
import threading
import time
import unicodedata
from concurrent.futures import Future
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
from typing import Callable
from typing import IO
from typing import Optional
from typing import Sequence
from typing import TypeVar

try:
    import fcntl as _fcntl
except ImportError:  # Windows has no fcntl.
    _fcntl = None  # type: ignore[assignment]

import pytox.toxcore.tox as core
from pytox.toxcore import events as tox_events

from pytox_client.calls import Calls
from pytox_client.calls import VideoListener
from pytox_client.model import Call
from pytox_client.model import CallNote
from pytox_client.model import CallOutcome
from pytox_client.model import Chat
from pytox_client.model import ClientState
from pytox_client.model import FileState
from pytox_client.model import Friend
from pytox_client.model import FriendRequest
from pytox_client.model import Group
from pytox_client.model import GroupChat
from pytox_client.model import GroupInvite
from pytox_client.model import GroupMessage
from pytox_client.model import Message
from pytox_client.model import Node
from pytox_client.model import Peer
from pytox_client.model import PickedFile
from pytox_client.model import Picture
from pytox_client.profiles import CallLine
from pytox_client.model import Profile
from pytox_client.model import Settings
from pytox_client.nodes import BUILT_IN_NODES
from pytox_client.platform_base import Platform
from pytox_client.store import Store
from pytox_client.store import StoredFriend

_T = TypeVar("_T")

FILE_KIND_DATA = int(core.FileKind.DATA)
FILE_KIND_AVATAR = int(core.FileKind.AVATAR)
FILE_ID_LENGTH = 32
_MAX_SQLITE_INT64 = (1 << 63) - 1
_LOG = logging.getLogger("pytox")

_WINDOWS_RESERVED_NAMES = frozenset({
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
})

# NGC limits from c-toxcore's tox.h (TOX_GROUP_*), which the binding doesn't
# export as module constants.
GROUP_MAX_TOPIC_LENGTH = 512
GROUP_MAX_MESSAGE_LENGTH = 1372
GROUP_MAX_GROUP_NAME_LENGTH = 48
GROUP_MAX_PASSWORD_SIZE = 32
GROUP_CHAT_ID_SIZE = 32

_DEFAULT_GROUP_NAME = "Tox user"

_PROFILE_FILENAME = "profile.tox"
_PAGE_SIZE = 100
_BOOTSTRAP_NODES = 4
_BOOTSTRAP_INTERVAL_MS = 10_000
_PROGRESS_INTERVAL_MS = 250
_DEFAULT_REQUEST = "Hi, I'd like to add you as a friend."
_DIR_ID_BYTES = 8
_AVATAR_PIXELS = 256
_MAX_AVATAR_SIZE = 1 << 20
_AVATAR_NAME = b"avatar.png"
_MAX_FILE_NAME = 120
_DEFAULT_LOCK_TIMEOUT_S = 15.0


def _now_ms() -> int:
    return int(time.time() * 1000)


def _mono_ms() -> int:
    return int(time.monotonic() * 1000)


def _to_hex(data: bytes) -> str:
    return data.hex().upper()


def _from_hex(value: str) -> Optional[bytes]:
    if len(value) % 2 != 0:
        return None
    try:
        return bytes.fromhex(value)
    except ValueError:
        return None


def _decode_utf8(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def _fsync_dir(directory: Path) -> None:
    if not hasattr(os, "O_DIRECTORY"):
        return
    try:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        dfd = os.open(directory, flags)
    except OSError:
        return
    try:
        os.fsync(dfd)
    except OSError:
        pass
    finally:
        os.close(dfd)


def _write_atomically(path: Path, data: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = path.parent / f"{path.name}.{os.getpid()}.{secrets.token_hex(6)}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(tmp, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        _fsync_dir(path.parent)
    except BaseException:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def truncate_utf8(text: str, max_bytes: int) -> str:
    """Truncate ``text`` so its UTF-8 encoding is at most ``max_bytes`` long."""
    if max_bytes <= 0:
        return ""
    raw_full = text.encode("utf-8")
    if len(raw_full) <= max_bytes:
        return text
    raw = raw_full[:max_bytes]
    while raw:
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raw = raw[:exc.start]
    return ""


def safe_name(name: str) -> str:
    """Sanitize a friend-provided filename so it cannot escape a directory."""
    if "/" in name:
        name = name.rsplit("/", 1)[-1]
    if "\\" in name:
        name = name.rsplit("\\", 1)[-1]
    cleaned = "".join(
        ch for ch in name
        if unicodedata.category(ch) not in ("Cc", "Cf")
        and ch not in '<>:"|?*'
    )
    cleaned = cleaned.strip().rstrip(". ").lstrip(".")
    cleaned = truncate_utf8(cleaned, _MAX_FILE_NAME).rstrip(". ")
    if not cleaned:
        return "file"
    stem = cleaned.split(".", 1)[0].upper()
    if stem in _WINDOWS_RESERVED_NAMES:
        cleaned = truncate_utf8(f"_{cleaned}", _MAX_FILE_NAME)
    return cleaned


def split_message(
    text: str,
    max_bytes: int = core.MAX_MESSAGE_LENGTH,
) -> list[str]:
    """Split text into UTF-8 chunks at most ``max_bytes`` long.

    Prefers breaking after a space or newline in the second half of the slice,
    and never cuts inside a multi-byte UTF-8 character. Runs in O(len(text)).
    """
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    if not text:
        return [""]
    parts: list[str] = []
    start = 0
    length = len(text)
    while start < length:
        end = start
        byte_count = 0
        while end < length:
            cp = ord(text[end])
            ch_len = (1 if cp < 0x80 else
                      2 if cp < 0x800 else
                      3 if cp < 0x10000 else 4)
            if byte_count + ch_len > max_bytes:
                break
            byte_count += ch_len
            end += 1
        if end == length:
            parts.append(text[start:])
            break
        if end == start:
            # Single character larger than max_bytes: emit to guarantee progress.
            end = start + 1
        span = end - start
        space = max(text.rfind(" ", start, end), text.rfind("\n", start, end))
        cut = space + 1 if space > start + span // 2 else end
        parts.append(text[start:cut])
        start = cut
    return parts


@dataclass
class _Transfer:
    """Active file transfer (a chat file, or an avatar when message_id is None)."""

    message_id: Optional[int]
    outgoing: bool
    path: Path
    size: int
    done: int
    handle: Optional[IO[bytes]] = None
    expected_hash: str = ""

    def close(self) -> None:
        if self.handle is not None:
            try:
                self.handle.close()
            finally:
                self.handle = None


class ToxClient:
    """Thread-safe controller owning one Tox profile and SQLite chat store."""

    def __init__(
        self,
        directory: Path,
        platform: Platform,
        nodes: Sequence[Node] = BUILT_IN_NODES,
        initial_settings: Optional[Settings] = None,
        initial_theme: Optional[str] = None,
        *,
        profile: str = "1",
        call_line: Optional[CallLine] = None,
        lock_timeout: float = _DEFAULT_LOCK_TIMEOUT_S,
        on_closed: Optional[Callable[[], None]] = None,
    ) -> None:
        """``profile`` names it for notifications; ``call_line`` is the one
        call there can be, shared by the profiles in this process."""
        self._dir = Path(directory)
        self._profile_name = profile
        self._platform = platform
        self._nodes = tuple(nodes)
        self._initial_settings = initial_settings
        self._initial_theme = initial_theme
        self._lock_timeout = max(0.0, lock_timeout)
        self._on_closed: Optional[Callable[[], None]] = on_closed
        self._notified_closed = False

        self._files_dir = self._dir / "files"
        self._avatars_dir = self._dir / "avatars"
        self._own_avatar = self._dir / "avatar.png"

        self._commands: queue.Queue[Callable[[], None]] = queue.Queue()
        self._wake = threading.Event()
        self._stop_event = threading.Event()
        self._lifecycle_lock = threading.Lock()
        self._pending_futures: list[Future[object]] = []
        self._stopping = False
        self._started = False
        self._closed = False
        self._stop_reason: Optional[str] = None
        self._thread: Optional[threading.Thread] = None
        self._io_pool = ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="pytox-io",
        )

        self._state_lock = threading.Lock()
        self._state_cond = threading.Condition(self._state_lock)
        self._state = ClientState()
        self._listeners: list[Callable[[ClientState], None]] = []

        # Everything below belongs exclusively to the Tox thread.
        self._store: Optional[Store] = None
        self._tox: Optional[core.Tox] = None
        self._settings = Settings()
        self._profile = Profile()
        self._friends: dict[str, Friend] = {}
        self._numbers: dict[str, core.FriendNumber] = {}
        self._keys: dict[core.FriendNumber, str] = {}
        self._requests: list[FriendRequest] = []
        self._chat: Optional[Chat] = None
        self._visible = False

        self._receipts: dict[str, dict[int, int]] = {}
        self._transfers: dict[tuple[str, core.FileNumber], _Transfer] = {}
        self._progress_changed = False
        self._last_progress_ms = 0

        self._groups: dict[str, Group] = {}
        self._group_numbers: dict[str, core.GroupNumber] = {}
        self._group_ids: dict[core.GroupNumber, str] = {}
        # Who's in each group now, by peer number. Re-sent after each (re)join.
        self._peers: dict[str, dict[core.GroupPeerNumber, Peer]] = {}
        self._invites: list[GroupInvite] = []
        self._group_chat: Optional[GroupChat] = None

        self._unsaved = False
        self._restart = False
        self._last_bootstrap_ms = 0

        self._calls = Calls(
            platform,
            profile=profile,
            line=call_line or CallLine(),
            post=self._post,
            number=self._numbers.get,
            key=self._keys.get,
            friend=self._friends.get,
            changed=self._publish,
            ended=self._note_call,
        )

    @property
    def directory(self) -> Path:
        return self._dir

    @property
    def state(self) -> ClientState:
        with self._state_lock:
            return self._state

    @property
    def closed(self) -> bool:
        with self._lifecycle_lock:
            return self._closed

    def set_on_closed(
        self, callback: Optional[Callable[[], None]]
    ) -> None:
        """Set a one-shot callback invoked when the client becomes closed."""
        fire_now = False
        with self._lifecycle_lock:
            self._on_closed = callback
            if callback is not None and self._closed and not self._notified_closed:
                self._notified_closed = True
                fire_now = True
        if fire_now and callback is not None:
            try:
                callback()
            except Exception:  # noqa: BLE001
                _LOG.exception("on_closed callback failed")

    def subscribe(
        self,
        listener: Callable[[ClientState], None],
        emit_current: bool = True,
    ) -> Callable[[], None]:
        """Register a listener called whenever :attr:`state` updates."""
        with self._state_lock:
            self._listeners.append(listener)
            current = self._state
        if emit_current:
            listener(current)

        def unsubscribe() -> None:
            with self._state_lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return unsubscribe

    def wait_for(
        self,
        predicate: Callable[[ClientState], bool],
        timeout: float = 30.0,
    ) -> ClientState:
        """Block until ``predicate(state)`` holds, or raise ``TimeoutError``."""
        deadline = time.monotonic() + timeout
        with self._state_cond:
            while not predicate(self._state):
                if self._closed:
                    raise RuntimeError(
                        self._stop_reason or "ToxClient is closed")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Timed out waiting for client state")
                self._state_cond.wait(timeout=remaining)
            return self._state

    def start(self) -> None:
        with self._lifecycle_lock:
            if self._started or self._closed:
                return
            self._started = True
            self._thread = threading.Thread(
                target=self._run_loop,
                name="pytox-core",
                daemon=True,
            )
            thread = self._thread
        thread.start()

    def _finish_closed(self, reason: Optional[str] = None) -> None:
        cb: Optional[Callable[[], None]] = None
        with self._lifecycle_lock:
            if reason is not None and self._stop_reason is None:
                self._stop_reason = reason
            self._closed = True
            self._stopping = True
            err_msg = self._stop_reason or "ToxClient is closed"
            pending, self._pending_futures = self._pending_futures, []
            if self._on_closed is not None and not self._notified_closed:
                self._notified_closed = True
                cb = self._on_closed
        for fut in pending:
            if not fut.done():
                fut.set_exception(RuntimeError(err_msg))
        with self._state_cond:
            self._state_cond.notify_all()
        if cb is not None:
            try:
                cb()
            except Exception:  # noqa: BLE001
                _LOG.exception("on_closed callback failed")

    def close(self) -> None:
        """Save, stop all transfers, free Tox, and close the SQLite store."""
        with self._lifecycle_lock:
            already_stopping = self._stopping
            self._closed = True
            self._stopping = True
            thread = self._thread if self._started else None
        if not already_stopping:
            self._stop_event.set()
            self._wake.set()
        if thread is not None and threading.current_thread() is not thread:
            thread.join(timeout=10.0)
        self._io_pool.shutdown(wait=False)
        self._finish_closed()

    def delete_profile(self) -> None:
        """Close, then delete the profile with its chats and files."""
        self.close()
        shutil.rmtree(self._dir, ignore_errors=True)

    def _enqueue(self, fn: Callable[[], None]) -> bool:
        with self._lifecycle_lock:
            if self._closed:
                return False
            self._commands.put(fn)
        self._wake.set()
        return True

    def _post(self, fn: Callable[[], None]) -> None:
        self._enqueue(fn)

    def _submit_io(self, fn: Callable[[], None]) -> bool:
        with self._lifecycle_lock:
            if self._closed:
                return False
            try:
                self._io_pool.submit(fn)
                return True
            except RuntimeError:
                return False

    def _call(self, fn: Callable[[], _T]) -> Future[_T]:
        fut: Future[_T] = Future()
        with self._lifecycle_lock:
            if self._closed:
                fut.set_exception(
                    RuntimeError(self._stop_reason or "ToxClient is closed"))
                return fut
            self._pending_futures.append(fut)  # type: ignore[arg-type]

        def run_call() -> None:
            try:
                fut.set_result(fn())
            except BaseException as exc:  # noqa: BLE001
                if not fut.done():
                    fut.set_exception(exc)
            finally:
                with self._lifecycle_lock:
                    try:
                        self._pending_futures.remove(fut)  # type: ignore[arg-type]
                    except ValueError:
                        pass

        if not self._enqueue(run_call):
            if not fut.done():
                fut.set_exception(
                    RuntimeError(self._stop_reason or "ToxClient is closed"))
        return fut

    def local_node(self) -> Future[Node]:
        """Return this client's loopback Node for test bootstrapping."""

        def _get() -> Node:
            assert self._tox is not None
            return Node(
                host="127.0.0.1",
                port=self._tox.udp_port,
                tcp_ports=(),
                key=_to_hex(self._tox.dht_id),
            )

        return self._call(_get)

    def send(self, friend_key: str, text: str, action: bool = False) -> None:
        """Store and send a text (or ``/me`` action) message."""

        def _do() -> None:
            if not text.strip():
                return
            assert self._store is not None
            for part in split_message(text):
                msg = self._store.add_message(
                    friend=friend_key,
                    outgoing=True,
                    action=action,
                    text=part,
                    time_ms=_now_ms(),
                    delivered=False,
                )
                self._add_to_chat(msg)
                self._send_to_tox(msg)

        self._post(_do)

    def add_friend(
        self,
        tox_id: str,
        message: str = "",
    ) -> Future[Optional[str]]:
        """Add a friend by Tox ID. Resolves to an error message or ``None``."""

        def _do() -> Optional[str]:
            assert self._tox is not None
            cleaned = "".join(tox_id.split())
            if cleaned.lower().startswith("tox:"):
                cleaned = cleaned[4:]
            raw = _from_hex(cleaned)
            if raw is None or len(raw) != core.ADDRESS_SIZE:
                return f"A Tox ID is {core.ADDRESS_SIZE * 2} hex digits."
            msg_text = message if message else _DEFAULT_REQUEST
            try:
                number = self._tox.friend_add(raw, msg_text.encode("utf-8"))
            except core.FriendAddError as exc:
                code = exc.code
                if code == core.FriendAddError.Code.OWN_KEY:
                    return "That's your own Tox ID."
                if code == core.FriendAddError.Code.ALREADY_SENT:
                    return "You've already added this friend."
                if code == core.FriendAddError.Code.BAD_CHECKSUM:
                    return "That Tox ID has a typo in it."
                if code == core.FriendAddError.Code.SET_NEW_NOSPAM:
                    self._unsaved = True
                    return "Your friend has a new Tox ID now: sent again."
                if code == core.FriendAddError.Code.TOO_LONG:
                    return "The message is too long."
                return f"Couldn't add the friend: {code.name}."
            self._add_friend_number(number)
            return None

        return self._call(_do)

    def accept(self, request: FriendRequest) -> None:
        def _do() -> None:
            assert self._tox is not None
            raw_key = bytes.fromhex(request.key)
            try:
                number = self._tox.friend_add_norequest(raw_key)
            except core.FriendAddError as exc:
                if exc.code != core.FriendAddError.Code.ALREADY_SENT:
                    raise
                number = self._tox.friend_by_public_key(raw_key)
            if number not in self._keys:
                self._add_friend_number(number)
            self._decline_key(request.key)

        self._post(_do)

    def decline(self, request: FriendRequest) -> None:
        self._post(lambda: self._decline_key(request.key))

    def delete(self, friend_key: str) -> None:
        def _do() -> None:
            assert self._tox is not None
            assert self._store is not None
            if (self._calls.call is not None
                    and self._calls.call.friend == friend_key):
                self._calls.hang_up()
            self._stop_transfers(friend_key)
            number = self._numbers.pop(friend_key, None)
            if number is not None:
                try:
                    self._tox.friend_delete(number)
                except core.ApiException:
                    pass
                self._keys.pop(number, None)
            removed = self._friends.pop(friend_key, None)
            if removed is not None and removed.avatar is not None:
                try:
                    removed.avatar.path.unlink(missing_ok=True)
                except OSError:
                    pass
            self._receipts.pop(friend_key, None)
            files_root = self._files_dir.resolve()
            for file_path in self._store.files(friend_key):
                try:
                    resolved = file_path.resolve()
                    parent = resolved.parent
                except OSError:
                    continue
                if parent != files_root and parent.is_relative_to(files_root):
                    shutil.rmtree(parent, ignore_errors=True)
            self._invites = [
                inv for inv in self._invites if inv.friend != friend_key
            ]
            self._store.delete_friend(friend_key)
            if self._chat is not None and self._chat.friend == friend_key:
                self._chat = None
            self._unsaved = True
            self._publish()

        self._post(_do)

    def set_name(self, name: str) -> None:
        def _do() -> None:
            assert self._tox is not None
            encoded = name.encode("utf-8")
            if len(encoded) > core.MAX_NAME_LENGTH:
                return
            self._tox.name = encoded
            self._profile = replace(self._profile, name=name)
            for gid, number in list(self._group_numbers.items()):
                try:
                    self._tox.group_set_self_name(number, self._group_self_name())
                except core.ApiException:
                    pass
                self._publish_peers(gid, emit=False)
            self._unsaved = True
            self._publish()

        self._post(_do)

    def set_status_message(self, message: str) -> None:
        def _do() -> None:
            assert self._tox is not None
            encoded = message.encode("utf-8")
            if len(encoded) > core.MAX_STATUS_MESSAGE_LENGTH:
                return
            self._tox.status_message = encoded
            self._profile = replace(self._profile, status_message=message)
            self._unsaved = True
            self._publish()

        self._post(_do)

    def set_status(self, status: core.UserStatus) -> None:
        def _do() -> None:
            assert self._tox is not None
            self._tox.status = status
            self._profile = replace(self._profile, status=status)
            for gid, number in list(self._group_numbers.items()):
                try:
                    self._tox.group_set_self_status(number, status)
                except core.ApiException:
                    pass
                self._publish_peers(gid, emit=False)
            self._unsaved = True
            self._publish()

        self._post(_do)

    def open_chat(self, friend_key: Optional[str]) -> None:
        def _do() -> None:
            assert self._store is not None
            if friend_key is None:
                self._chat = None
            else:
                msgs = self._store.messages(friend_key, None, _PAGE_SIZE)
                self._chat = Chat(
                    friend=friend_key,
                    messages=tuple(msgs),
                    has_older=len(msgs) == _PAGE_SIZE,
                )
            self._mark_read()
            self._publish()

        self._post(_do)

    def load_older(self) -> None:
        def _do() -> None:
            if self._chat is None:
                return
            assert self._store is not None
            before = (self._chat.messages[0].id
                      if self._chat.messages else None)
            older = self._store.messages(self._chat.friend, before, _PAGE_SIZE)
            self._chat = replace(
                self._chat,
                messages=tuple(older) + self._chat.messages,
                has_older=len(older) == _PAGE_SIZE,
            )
            self._publish()

        self._post(_do)

    def set_visible(self, visible: bool) -> None:
        def _do() -> None:
            self._visible = visible
            self._mark_read()
            self._publish()

        self._post(_do)

    def set_typing(self, friend_key: str, typing: bool) -> None:
        def _do() -> None:
            assert self._tox is not None
            number = self._numbers.get(friend_key)
            friend = self._friends.get(friend_key)
            if number is None or friend is None or not friend.online:
                return
            try:
                self._tox.set_typing(number, typing)
            except core.ApiException:
                pass

        self._post(_do)

    def set_hide_after_zero(self, friend_key: str, hide: bool) -> None:
        def _do() -> None:
            assert self._store is not None
            if friend_key not in self._friends:
                return
            self._store.set_hide_after_zero(friend_key, hide)
            self._update_friend(
                friend_key, lambda f: replace(f, hide_after_zero=hide))

        self._post(_do)

    def update_settings(self, settings: Settings) -> None:
        def _do() -> None:
            assert self._store is not None
            if settings == self._settings:
                return
            self._store.save_settings(settings)
            if settings.stay_connected != self._settings.stay_connected:
                self._platform.set_stay_connected(settings.stay_connected)
            if not settings.same_network(self._settings):
                self._restart = True
            self._settings = settings
            self._publish()

        self._post(_do)

    def send_file(self, friend_key: str, picked: PickedFile) -> None:
        """Copy the picked file on a background thread, then offer via Tox."""
        if self._closed:
            return

        def _copy_and_offer() -> None:
            name = safe_name(picked.name)
            dest_dir = self._files_dir / secrets.token_hex(_DIR_ID_BYTES).upper()
            dest = dest_dir / name
            try:
                dest_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
                with picked.open_stream() as src, dest.open("wb") as out:
                    shutil.copyfileobj(src, out)
                size = dest.stat().st_size
            except Exception as exc:  # noqa: BLE001
                _LOG.warning("failed to stage file %r: %s", picked.name, exc)
                shutil.rmtree(dest_dir, ignore_errors=True)
                return
            file_id = secrets.token_hex(FILE_ID_LENGTH).upper()

            def _record() -> None:
                assert self._store is not None
                msg = self._store.add_file(
                    friend=friend_key,
                    outgoing=True,
                    name=name,
                    size=size,
                    file_id=file_id,
                    path=dest,
                    time_ms=_now_ms(),
                )
                self._add_to_chat(msg)
                self._offer_file(msg)

            if not self._enqueue(_record):
                shutil.rmtree(dest_dir, ignore_errors=True)

        self._submit_io(_copy_and_offer)

    def send_file_path(self, friend_key: str, path: Path, name: str = "") -> None:
        """Send a file already on disk (used by desktop picker and IPC)."""
        label = name if name else path.name
        self.send_file(
            friend_key,
            PickedFile(name=label, open_stream=lambda: path.open("rb")),
        )

    def accept_file(self, message_id: int) -> None:
        def _do() -> None:
            assert self._store is not None
            live = self._live_transfer(message_id)
            if live is not None:
                key, _ = live
                self._start_receiving(key[0], key[1])
            else:
                try:
                    msg = self._store.message_by_id(message_id)
                except KeyError:
                    return
                if msg.file is None or msg.file.state in (
                        FileState.DONE, FileState.CANCELLED):
                    return
                self._store.set_file_state(
                    message_id, FileState.ACTIVE, msg.file.done)
                self._refresh(message_id)

        self._post(_do)

    def cancel_file(self, message_id: int) -> None:
        def _do() -> None:
            assert self._tox is not None
            assert self._store is not None
            live = self._live_transfer(message_id)
            if live is not None:
                (friend_key, file_num), _ = live
                friend_num = self._numbers.get(friend_key)
                if friend_num is not None:
                    try:
                        self._tox.file_control(
                            friend_num, file_num, core.FileControl.CANCEL)
                    except core.ApiException:
                        pass
                self._finish(friend_key, file_num, FileState.CANCELLED)
            else:
                try:
                    msg = self._store.message_by_id(message_id)
                except KeyError:
                    return
                if msg.file is not None and msg.file.state == FileState.DONE:
                    return
                if not msg.outgoing and msg.file is not None:
                    msg.file.path.unlink(missing_ok=True)
                done = msg.file.done if msg.file is not None else 0
                self._store.set_file_state(
                    message_id, FileState.CANCELLED, done)
                self._refresh(message_id)

        self._post(_do)

    def set_avatar(self, image: Optional[bytes]) -> Future[bool]:
        """Set or remove our own avatar PNG. Returns ``False`` on bad image."""
        result: Future[bool] = Future()
        with self._lifecycle_lock:
            if self._closed:
                result.set_result(False)
                return result
            self._pending_futures.append(result)  # type: ignore[arg-type]

        def _finish_fut(value: Optional[bool] = None,
                        exc: Optional[BaseException] = None) -> None:
            try:
                if not result.done():
                    if exc is not None:
                        result.set_exception(exc)
                    else:
                        result.set_result(bool(value))
            finally:
                with self._lifecycle_lock:
                    try:
                        self._pending_futures.remove(
                            result)  # type: ignore[arg-type]
                    except ValueError:
                        pass

        def _prepare() -> None:
            try:
                png: Optional[bytes]
                if image is None:
                    png = None
                else:
                    png = self._platform.avatar_png(image, _AVATAR_PIXELS)
                    if png is None:
                        _finish_fut(False)
                        return
            except BaseException as exc:  # noqa: BLE001
                _finish_fut(exc=exc)
                return

            def _apply() -> None:
                try:
                    if png is None:
                        self._own_avatar.unlink(missing_ok=True)
                    else:
                        _write_atomically(self._own_avatar, png)
                    self._profile = replace(
                        self._profile, avatar=self._picture(self._own_avatar))
                    self._publish()
                    for friend in list(self._friends.values()):
                        if friend.online:
                            self._cancel_outgoing_avatar(friend.key)
                            self._send_avatar(friend.key)
                    _finish_fut(True)
                except BaseException as exc:  # noqa: BLE001
                    _finish_fut(exc=exc)

            if not self._enqueue(_apply):
                _finish_fut(False)

        if not self._submit_io(_prepare):
            _finish_fut(False)
        return result

    # ------------------------------------------------------------------
    # Groups (NGC)
    # ------------------------------------------------------------------

    def create_group(self, name: str, private: bool) -> Future[Optional[str]]:
        """Start a group. Resolves to an error message or ``None``."""

        def _do() -> Optional[str]:
            assert self._tox is not None
            privacy = (core.GroupPrivacyState.PRIVATE
                       if private else core.GroupPrivacyState.PUBLIC)
            try:
                number = self._tox.group_new(
                    privacy, name.encode("utf-8"), self._group_self_name())
            except core.ApiException as exc:
                return f"Couldn't start the group: {exc.code.name}."
            self._group_of(number)
            self._unsaved = True
            self._publish()
            return None

        return self._call(_do)

    def join_group(self, chat_id: str, password: str) -> Future[Optional[str]]:
        """Join a public group by chat ID. Resolves to an error or ``None``."""

        def _do() -> Optional[str]:
            assert self._tox is not None
            raw = _from_hex(chat_id.strip())
            if raw is None or len(raw) != GROUP_CHAT_ID_SIZE:
                return f"A chat ID is {GROUP_CHAT_ID_SIZE * 2} hex digits."
            if _to_hex(raw) in self._groups:
                return "You're in this group already."
            try:
                number = self._tox.group_join(
                    raw, self._group_self_name(), password.encode("utf-8"))
            except core.ApiException as exc:
                return f"Couldn't join the group: {exc.code.name}."
            self._group_of(number)
            self._unsaved = True
            self._publish()
            return None

        return self._call(_do)

    def accept_invite(self, invite: GroupInvite) -> None:
        def _do() -> None:
            assert self._tox is not None
            friend = self._numbers.get(invite.friend)
            if friend is None:
                return
            data = _from_hex(invite.data)
            if data is not None:
                try:
                    number = self._tox.group_invite_accept(
                        friend, data, self._group_self_name(), b"")
                    self._group_of(number)
                    self._unsaved = True
                except core.GroupInviteAcceptError as exc:
                    if exc.code == core.GroupInviteAcceptError.Code.FAIL_SEND:
                        # Transient network failure: keep the invite to retry.
                        return
                except core.ApiException:
                    pass
            self._decline_invite(invite)

        self._post(_do)

    def decline_invite(self, invite: GroupInvite) -> None:
        self._post(lambda: self._decline_invite(invite))

    def invite_friend(self, group_id: str, friend_key: str) -> None:
        def _do() -> None:
            assert self._tox is not None
            number = self._group_numbers.get(group_id)
            friend = self._numbers.get(friend_key)
            if number is None or friend is None:
                return
            try:
                self._tox.group_invite_friend(number, friend)
            except core.ApiException:
                # Offline friends can't be invited: the page offers online ones.
                pass

        self._post(_do)

    def leave_group(self, group_id: str) -> None:
        def _do() -> None:
            assert self._tox is not None
            assert self._store is not None
            number = self._group_numbers.pop(group_id, None)
            if number is not None:
                try:
                    self._tox.group_leave(number, b"")
                except core.ApiException:
                    pass
                self._group_ids.pop(number, None)
            self._groups.pop(group_id, None)
            self._peers.pop(group_id, None)
            self._store.delete_group(group_id)
            if (self._group_chat is not None
                    and self._group_chat.group == group_id):
                self._group_chat = None
            self._unsaved = True
            self._publish()

        self._post(_do)

    def send_group_message(
        self,
        group_id: str,
        text: str,
        action: bool = False,
    ) -> None:
        def _do() -> None:
            assert self._tox is not None
            assert self._store is not None
            if not text.strip():
                return
            number = self._group_numbers.get(group_id)
            group = self._groups.get(group_id)
            if number is None or group is None:
                return
            me = next((p for p in group.peers if p.is_self), None)
            msg_type = (core.MessageType.ACTION
                        if action else core.MessageType.NORMAL)
            for part in split_message(text, GROUP_MAX_MESSAGE_LENGTH):
                try:
                    self._tox.group_send_message(
                        number, msg_type, part.encode("utf-8"))
                    sent = True
                except core.ApiException:
                    sent = False
                stored = self._store.add_group_message(
                    GroupMessage(
                        id=0,
                        group=group_id,
                        peer_key=me.key if me is not None else "",
                        peer_name=(me.name if me is not None
                                   else self._profile.name),
                        outgoing=True,
                        action=action,
                        private=False,
                        text=part,
                        time=_now_ms(),
                        sent=sent,
                    ))
                self._add_to_group_chat(stored)

        self._post(_do)

    def _group_setting(
        self,
        group_id: str,
        apply: Callable[[core.GroupNumber], None],
    ) -> None:
        """Run a group setting; toxcore refuses what isn't allowed."""

        def _do() -> None:
            number = self._group_numbers.get(group_id)
            if number is None:
                return
            try:
                apply(number)
            except core.ApiException:
                pass
            self._unsaved = True
            self._refresh_group(group_id)

        self._post(_do)

    def _on_event(self, event: tox_events.Event) -> None:
        match event:
            case tox_events.SelfConnectionStatusEvent(connection_status=status):
                self._on_self_connection_status(status)
            case tox_events.FriendRequestEvent(public_key=public_key,
                                               message=message):
                self._on_friend_request(public_key, message)
            case tox_events.FriendMessageEvent(friend_number=n,
                                               type=type_,
                                               message=message):
                self._on_friend_message(n, type_, message)
            case tox_events.FriendNameEvent(friend_number=n, name=name):
                self._on_friend_name(n, name)
            case tox_events.FriendStatusMessageEvent(friend_number=n,
                                                     message=message):
                self._on_friend_status_message(n, message)
            case tox_events.FriendStatusEvent(friend_number=n, status=status):
                self._on_friend_status(n, status)
            case tox_events.FriendConnectionStatusEvent(
                    friend_number=n, connection_status=status):
                self._on_friend_connection_status(n, status)
            case tox_events.FriendTypingEvent(friend_number=n, typing=typing):
                self._on_friend_typing(n, typing)
            case tox_events.FriendReadReceiptEvent(friend_number=n,
                                                   message_id=message_id):
                self._on_friend_read_receipt(n, message_id)
            case tox_events.FileRecvEvent(friend_number=n,
                                          file_number=f,
                                          kind=kind,
                                          file_size=size,
                                          filename=filename):
                self._on_file_recv(n, f, kind, size, filename)
            case tox_events.FileRecvChunkEvent(friend_number=n,
                                               file_number=f,
                                               position=position,
                                               data=data):
                self._on_file_recv_chunk(n, f, position, data)
            case tox_events.FileRecvControlEvent(friend_number=n,
                                                 file_number=f,
                                                 control=control):
                self._on_file_recv_control(n, f, control)
            case tox_events.FileChunkRequestEvent(friend_number=n,
                                                  file_number=f,
                                                  position=position,
                                                  length=length):
                self._on_file_chunk_request(n, f, position, length)
            case tox_events.GroupInviteEvent(friend_number=n,
                                             invite_data=invite_data,
                                             group_name=group_name):
                self._on_group_invite(n, invite_data, group_name)
            case tox_events.GroupSelfJoinEvent(group_number=g):
                self._on_group_self_join(g)
            case tox_events.GroupJoinFailEvent(group_number=g,
                                               fail_type=fail_type):
                self._on_group_join_fail(g, fail_type)
            case tox_events.GroupPeerJoinEvent(group_number=g, peer_id=peer):
                self._on_group_peer_join(g, peer)
            case tox_events.GroupPeerExitEvent(group_number=g,
                                               peer_id=peer,
                                               exit_type=exit_type):
                self._on_group_peer_exit(g, peer, exit_type)
            case (tox_events.GroupPeerNameEvent(group_number=g, peer_id=peer)
                  | tox_events.GroupPeerStatusEvent(group_number=g,
                                                    peer_id=peer)):
                self._group_peer_changed(g, peer)
            case tox_events.GroupModerationEvent(group_number=g,
                                                 target_peer_id=peer,
                                                 mod_type=mod_type):
                self._on_group_moderation(g, peer, mod_type)
            case tox_events.GroupMessageEvent(group_number=g,
                                              peer_id=peer,
                                              message_type=type_,
                                              message=message):
                self._on_group_message(g, peer, type_, message, private=False)
            case tox_events.GroupPrivateMessageEvent(group_number=g,
                                                     peer_id=peer,
                                                     message_type=type_,
                                                     message=message):
                self._on_group_message(g, peer, type_, message, private=True)
            case (tox_events.GroupTopicEvent(group_number=g)
                  | tox_events.GroupPrivacyStateEvent(group_number=g)
                  | tox_events.GroupPasswordEvent(group_number=g)
                  | tox_events.GroupPeerLimitEvent(group_number=g)
                  | tox_events.GroupTopicLockEvent(group_number=g)
                  | tox_events.GroupVoiceStateEvent(group_number=g)):
                self._group_changed(g)

    def _tox_or_fail(self) -> core.Tox:
        assert self._tox is not None
        return self._tox

    def set_topic(self, group_id: str, topic: str) -> None:
        self._group_setting(
            group_id,
            lambda n: self._tox_or_fail().group_set_topic(
                n, topic.encode("utf-8")))

    def set_group_privacy(self, group_id: str, private: bool) -> None:
        state = (core.GroupPrivacyState.PRIVATE
                 if private else core.GroupPrivacyState.PUBLIC)
        self._group_setting(
            group_id,
            lambda n: self._tox_or_fail().group_set_privacy_state(n, state))

    def set_group_password(self, group_id: str, password: str) -> None:
        self._group_setting(
            group_id,
            lambda n: self._tox_or_fail().group_set_password(
                n, password.encode("utf-8")))

    def set_peer_limit(self, group_id: str, limit: int) -> None:
        if limit < 1 or limit > 0xFFFF:
            return
        self._group_setting(
            group_id,
            lambda n: self._tox_or_fail().group_set_peer_limit(n, limit))

    def set_topic_lock(self, group_id: str, locked: bool) -> None:
        lock = (core.GroupTopicLock.ENABLED
                if locked else core.GroupTopicLock.DISABLED)
        self._group_setting(
            group_id,
            lambda n: self._tox_or_fail().group_set_topic_lock(n, lock))

    def _peer_number(self, group_id: str, peer_key: str) -> Optional[core.GroupPeerNumber]:
        for number, peer in self._peers.get(group_id, {}).items():
            if peer.key == peer_key:
                return number
        return None

    def set_role(
        self,
        group_id: str,
        peer_key: str,
        role: core.GroupRole,
    ) -> None:
        def _apply(n: core.GroupNumber) -> None:
            peer = self._peer_number(group_id, peer_key)
            if peer is not None:
                self._tox_or_fail().group_set_role(n, peer, role)

        self._group_setting(group_id, _apply)

    def kick(self, group_id: str, peer_key: str) -> None:
        def _apply(n: core.GroupNumber) -> None:
            peer = self._peer_number(group_id, peer_key)
            if peer is not None:
                self._tox_or_fail().group_kick_peer(n, peer)

        self._group_setting(group_id, _apply)

    def open_group(self, group_id: Optional[str]) -> None:
        """Show ``group_id``'s chat, or none."""

        def _do() -> None:
            assert self._store is not None
            if group_id is None:
                self._group_chat = None
            else:
                msgs = self._store.group_messages(group_id, None, _PAGE_SIZE)
                self._group_chat = GroupChat(
                    group=group_id,
                    messages=tuple(msgs),
                    has_older=len(msgs) == _PAGE_SIZE,
                )
            self._mark_read()
            self._publish()

        self._post(_do)

    def load_older_group_messages(self) -> None:
        def _do() -> None:
            if self._group_chat is None:
                return
            assert self._store is not None
            open_chat = self._group_chat
            before = (open_chat.messages[0].id
                      if open_chat.messages else None)
            older = self._store.group_messages(
                open_chat.group, before, _PAGE_SIZE)
            self._group_chat = replace(
                open_chat,
                messages=tuple(older) + open_chat.messages,
                has_older=len(older) == _PAGE_SIZE,
            )
            self._publish()

        self._post(_do)

    # ------------------------------------------------------------------
    # Calls
    # ------------------------------------------------------------------

    def call(self, friend_key: str, video: bool) -> None:
        """Call a friend; calling one who is calling us answers them."""
        self._post(lambda: self._calls.start_call(friend_key, video))

    def answer(self, video: bool) -> None:
        self._post(lambda: self._calls.answer(video))

    def hang_up(self) -> None:
        """End the call, or say no to one that rings."""
        self._post(self._calls.hang_up)

    def set_muted(self, muted: bool) -> None:
        self._post(lambda: self._calls.set_muted(muted))

    def set_video(self, on: bool) -> None:
        self._post(lambda: self._calls.set_video(on))

    def switch_camera(self) -> None:
        self._post(self._calls.switch_camera)

    def set_speaker(self, on: bool) -> None:
        self._post(lambda: self._calls.set_speaker(on))

    def watch_video(self, listener: VideoListener) -> Callable[[], None]:
        """Get the call's pictures as they come: see :class:`CallVideo`."""
        return self._calls.video.watch(listener)

    # ------------------------------------------------------------------
    # Tox thread lifecycle
    # ------------------------------------------------------------------

    def _acquire_profile_lock(self) -> Optional[int]:
        if _fcntl is None:
            return None
        lock_path = self._dir / ".lock"
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        deadline = time.monotonic() + self._lock_timeout
        delay = 0.05
        try:
            while True:
                try:
                    _fcntl.flock(fd, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
                    return fd
                except OSError as exc:
                    if exc.errno == errno.EINTR:
                        continue
                    if exc.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
                        raise
                    if self._stopping:
                        os.close(fd)
                        return None
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise
                    if self._stop_event.wait(timeout=min(delay, remaining)):
                        os.close(fd)
                        return None
                    delay = min(delay * 2.0, 0.25)
        except BaseException:
            try:
                os.close(fd)
            except OSError:
                pass
            raise

    def _run_loop(self) -> None:
        lock_fd: Optional[int] = None
        store: Optional[Store] = None
        failure_reason: Optional[str] = None
        try:
            self._dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            try:
                lock_fd = self._acquire_profile_lock()
            except OSError as exc:
                failure_reason = f"Profile {self._dir} is already open: {exc}"
                _LOG.error("%s", failure_reason)
                return
            if self._stopping:
                return
            store = Store(self._dir / "chats.db")
            self._store = store
            if self._initial_settings is not None:
                self._settings = self._initial_settings
                store.save_settings(self._settings)
            else:
                self._settings = store.settings()
            if self._initial_theme in ("system", "light", "dark"):
                self._settings = replace(
                    self._settings, theme=self._initial_theme)
                store.save_settings(self._settings)
            if (self._platform.can_stay_connected
                    and self._settings.stay_connected
                    != self._platform.is_stay_connected_pref()):
                # Staying connected is the app's, for every profile.
                self._settings = replace(
                    self._settings,
                    stay_connected=self._platform.is_stay_connected_pref())
                store.save_settings(self._settings)
            self._requests = store.requests()
            self._invites = store.invites()

            while not self._stopping:
                self._open_tox()
                self._restart = False
                while not self._stopping and not self._restart:
                    self._drain_commands()
                    if self._stopping or self._restart:
                        break
                    assert self._tox is not None
                    try:
                        for event in self._tox.iterate():
                            self._on_event(event)
                    except Exception:  # noqa: BLE001
                        _LOG.exception("tox.iterate() callback failed")
                    try:
                        self._calls.iterate()
                    except Exception:  # noqa: BLE001
                        _LOG.exception("calls.iterate() failed")
                    self._bootstrap()
                    if self._unsaved:
                        self._save()
                    now = _mono_ms()
                    if (self._progress_changed
                            and now - self._last_progress_ms >= _PROGRESS_INTERVAL_MS):
                        self._publish()
                    # toxav says 0 while decoding falls behind: then what's
                    # posted (sound, pictures, the user's taps) goes first,
                    # as each turn of the loop runs it.
                    wait_ms = min(self._tox.iteration_interval,
                                  self._calls.iteration_interval)
                    if wait_ms > 0:
                        self._wake.wait(timeout=wait_ms / 1000.0)
                        self._wake.clear()
                self._drain_commands()
                self._shutdown_tox()
        except Exception as exc:  # noqa: BLE001
            failure_reason = f"ToxClient failed: {exc}"
            _LOG.exception("pytox-core loop aborted")
        finally:
            try:
                self._shutdown_tox()
            except Exception as exc:  # noqa: BLE001
                if failure_reason is None:
                    failure_reason = f"ToxClient shutdown failed: {exc}"
                _LOG.exception("tox shutdown failed")
            if store is not None:
                try:
                    store.close()
                except Exception:  # noqa: BLE001
                    _LOG.exception("store close failed")
                self._store = None
            if lock_fd is not None:
                try:
                    os.close(lock_fd)
                except OSError:
                    pass
            try:
                self._io_pool.shutdown(wait=False)
            except Exception:  # noqa: BLE001
                _LOG.exception("io pool shutdown failed")
            self._stop_event.set()
            self._finish_closed(failure_reason)

    def _drain_commands(self) -> None:
        # Only what was posted before this turn: during a call, the microphone
        # and camera post all the time, and Tox has to iterate in between.
        for _ in range(self._commands.qsize()):
            try:
                cmd = self._commands.get_nowait()
            except queue.Empty:
                return
            try:
                cmd()
            except Exception:  # noqa: BLE001
                _LOG.exception("command on Tox thread failed")

    def _open_tox(self) -> None:
        assert self._store is not None
        profile_path = self._dir / _PROFILE_FILENAME
        has_savedata = profile_path.exists()
        with core.Options() as opts:
            opts.ipv6_enabled = self._settings.ipv6
            opts.udp_enabled = self._settings.udp
            opts.local_discovery_enabled = self._settings.local_discovery
            # Like toxic and kTox: a group we founded keeps its founder key
            # across restarts this way.
            opts.experimental_groups_persistence = True
            if has_savedata:
                opts.savedata_type = core.SavedataType.TOX_SAVE
                opts.savedata = profile_path.read_bytes()
            self._tox = core.Tox(opts)

        if not has_savedata:
            self._save()
        self._calls.start(self._tox)

        self._profile = Profile(
            address=_to_hex(self._tox.address),
            name=_decode_utf8(self._tox.name),
            status_message=_decode_utf8(self._tox.status_message),
            status=self._tox.status,
            connection=core.Connection.NONE,
            avatar=self._picture(self._own_avatar),
        )
        stored = self._store.friends()
        self._friends.clear()
        self._numbers.clear()
        self._keys.clear()
        self._receipts.clear()
        self._transfers.clear()
        for num in self._tox.friend_list:
            key = _to_hex(self._tox.friend_get_public_key(num))
            self._store.add_friend(key)
            self._numbers[key] = num
            self._keys[num] = key
            meta = stored.get(key, StoredFriend("", "", 0))
            self._friends[key] = self._make_friend(key, meta)
        self._load_groups()
        self._last_bootstrap_ms = _mono_ms() - _BOOTSTRAP_INTERVAL_MS
        self._publish()

    def _shutdown_tox(self) -> None:
        if self._tox is None:
            return
        save_exc: Optional[Exception] = None
        try:
            try:
                self._calls.stop()
            except Exception:  # noqa: BLE001
                _LOG.exception("calls.stop() failed during shutdown")
            try:
                self._save()
            except Exception as exc:  # noqa: BLE001
                save_exc = exc
            for key in list(self._friends.keys()):
                try:
                    self._stop_transfers(key)
                except Exception:  # noqa: BLE001
                    _LOG.exception("stopping file transfers failed for %s", key)
        finally:
            tox = self._tox
            self._tox = None
            tox.__exit__(None, None, None)
        if save_exc is not None:
            raise save_exc

    def _make_friend(self, key: str, stored: StoredFriend) -> Friend:
        assert self._store is not None
        avatar: Optional[Picture] = None
        if stored.avatar_hash:
            path = self._avatar_file(key)
            if path.exists():
                avatar = Picture(path=path, hash=stored.avatar_hash)
        return Friend(
            key=key,
            name=stored.name,
            status_message=stored.status_message,
            status=core.UserStatus.NONE,
            connection=core.Connection.NONE,
            typing=False,
            unread=stored.unread,
            last=self._store.last_message(key),
            avatar=avatar,
            hide_after_zero=stored.hide_after_zero,
        )

    def _avatar_file(self, friend_key: str) -> Path:
        return self._avatars_dir / f"{friend_key}.png"

    def _picture(self, path: Path) -> Optional[Picture]:
        if not path.exists():
            return None
        return Picture(path=path, hash=_to_hex(core.hash(path.read_bytes())))

    def _bootstrap(self) -> None:
        if self._tox is None or not self._nodes:
            return
        now = _mono_ms()
        if (self._profile.connection != core.Connection.NONE
                or now - self._last_bootstrap_ms < _BOOTSTRAP_INTERVAL_MS):
            return
        self._last_bootstrap_ms = now
        sample = list(self._nodes)
        random.shuffle(sample)
        for node in sample[:_BOOTSTRAP_NODES]:
            pub = bytes.fromhex(node.key)
            try:
                self._tox.bootstrap(node.host, node.port, pub)
                for tcp_port in node.tcp_ports:
                    self._tox.add_tcp_relay(node.host, tcp_port, pub)
            except core.ApiException:
                # The next round tries other nodes.
                pass

    def _save(self) -> None:
        if self._tox is None:
            return
        _write_atomically(self._dir / _PROFILE_FILENAME, self._tox.savedata)
        self._unsaved = False

    def _publish(self) -> None:
        sorted_friends = tuple(
            sorted(
                self._friends.values(),
                key=lambda f: (-(f.last.time if f.last is not None else 0),
                               f.display_name.lower()),
            )
        )
        progress = {
            t.message_id: t.done
            for t in self._transfers.values()
            if t.message_id is not None
        }
        snapshot = ClientState(
            profile=self._profile,
            friends=sorted_friends,
            requests=tuple(self._requests),
            settings=self._settings,
            chat=self._chat,
            progress=progress,
            groups=tuple(self._groups.values()),
            invites=tuple(self._invites),
            group_chat=self._group_chat,
            call=self._calls.call,
        )
        self._progress_changed = False
        self._last_progress_ms = _mono_ms()
        with self._state_cond:
            self._state = snapshot
            listeners = list(self._listeners)
            self._state_cond.notify_all()
        for listener in listeners:
            try:
                listener(snapshot)
            except Exception:  # noqa: BLE001
                _LOG.exception("state listener failed")

    def _update_friend(
        self,
        key: str,
        change: Callable[[Friend], Friend],
    ) -> None:
        current = self._friends.get(key)
        if current is not None:
            self._friends[key] = change(current)
        self._publish()

    # ------------------------------------------------------------------
    # Tox callbacks (always on Tox thread)
    # ------------------------------------------------------------------

    def _on_self_connection_status(self, status: core.Connection) -> None:
        self._profile = replace(self._profile, connection=status)
        self._publish()

    def _on_friend_request(self, public_key: bytes, message: bytes) -> None:
        assert self._store is not None
        req = FriendRequest(
            key=_to_hex(public_key),
            message=_decode_utf8(message),
            time=_now_ms(),
        )
        self._store.add_request(req)
        self._requests = [r for r in self._requests if r.key != req.key]
        self._requests.append(req)
        self._publish()
        self._platform.notify_request(self._profile_name, req)

    def _on_friend_message(
        self,
        friend_number: core.FriendNumber,
        msg_type: core.MessageType,
        message: bytes,
    ) -> None:
        assert self._store is not None
        key = self._keys.get(friend_number)
        if key is None:
            return
        msg = self._store.add_message(
            friend=key,
            outgoing=False,
            action=msg_type == core.MessageType.ACTION,
            text=_decode_utf8(message),
            time_ms=_now_ms(),
            delivered=True,
        )
        self._received(msg)

    def _on_friend_name(self, friend_number: core.FriendNumber, name: bytes) -> None:
        assert self._store is not None
        key = self._keys.get(friend_number)
        if key is None:
            return
        decoded = _decode_utf8(name)
        self._store.set_friend_name(key, decoded)
        self._update_friend(key, lambda f: replace(f, name=decoded))

    def _on_friend_status_message(
        self,
        friend_number: core.FriendNumber,
        message: bytes,
    ) -> None:
        assert self._store is not None
        key = self._keys.get(friend_number)
        if key is None:
            return
        decoded = _decode_utf8(message)
        self._store.set_friend_status_message(key, decoded)
        self._update_friend(key, lambda f: replace(f, status_message=decoded))

    def _on_friend_status(
        self,
        friend_number: core.FriendNumber,
        status: core.UserStatus,
    ) -> None:
        key = self._keys.get(friend_number)
        if key is None:
            return
        self._update_friend(key, lambda f: replace(f, status=status))

    def _on_friend_connection_status(
        self,
        friend_number: core.FriendNumber,
        connection_status: core.Connection,
    ) -> None:
        assert self._store is not None
        key = self._keys.get(friend_number)
        if key is None:
            return
        existing = self._friends.get(key)
        was_online = existing is not None and existing.online
        self._update_friend(
            key,
            lambda f: replace(f, connection=connection_status, typing=False),
        )
        if connection_status == core.Connection.NONE:
            self._receipts.pop(key, None)
            self._stop_transfers(key)
            self._calls.friend_gone(key)
        elif not was_online:
            for msg in self._store.undelivered(key):
                self._send_to_tox(msg)
            for msg in self._store.unfinished_files(key, outgoing=True):
                self._offer_file(msg)
            self._send_avatar(key)

    def _on_friend_typing(self, friend_number: core.FriendNumber, typing: bool) -> None:
        key = self._keys.get(friend_number)
        if key is None:
            return
        self._update_friend(key, lambda f: replace(f, typing=typing))

    def _on_friend_read_receipt(
        self,
        friend_number: core.FriendNumber,
        message_id: int,
    ) -> None:
        assert self._store is not None
        key = self._keys.get(friend_number)
        if key is None:
            return
        pending = self._receipts.get(key)
        if pending is None:
            return
        row_id = pending.pop(message_id, None)
        if row_id is None:
            return
        self._store.mark_delivered(row_id)
        self._refresh(row_id)

    def _on_file_recv(
        self,
        friend_number: core.FriendNumber,
        file_number: core.FileNumber,
        kind: int,
        file_size: int,
        filename: bytes,
    ) -> None:
        assert self._tox is not None
        key = self._keys.get(friend_number)
        if key is None:
            return
        file_id = _to_hex(
            self._tox.file_get_file_id(friend_number, file_number))
        if kind == FILE_KIND_AVATAR:
            self._receive_avatar(key, file_number, file_size, file_id)
        else:
            self._receive_file(
                key,
                file_number,
                file_size,
                file_id,
                safe_name(_decode_utf8(filename)),
            )

    def _on_file_recv_chunk(
        self,
        friend_number: core.FriendNumber,
        file_number: core.FileNumber,
        position: int,
        data: bytes,
    ) -> None:
        key = self._keys.get(friend_number)
        if key is None:
            return
        transfer = self._transfers.get((key, file_number))
        if transfer is None:
            return
        if not data:
            self._finish(key, file_number, FileState.DONE)
            return
        end = position + len(data)
        max_size = transfer.size
        if transfer.message_id is None:
            max_size = min(max_size, _MAX_AVATAR_SIZE)
        if position < 0 or end > max_size:
            self._cancel_transfer(key, friend_number, file_number)
            return
        if transfer.handle is not None:
            try:
                transfer.handle.seek(position)
                transfer.handle.write(data)
            except OSError as exc:
                _LOG.warning("file write failed: %s", exc)
                self._cancel_transfer(key, friend_number, file_number)
                return
        transfer.done = max(transfer.done, end)
        self._progress_changed = True

    def _on_file_recv_control(
        self,
        friend_number: core.FriendNumber,
        file_number: core.FileNumber,
        control: core.FileControl,
    ) -> None:
        assert self._store is not None
        key = self._keys.get(friend_number)
        if key is None:
            return
        transfer = self._transfers.get((key, file_number))
        if transfer is None:
            return
        if control == core.FileControl.CANCEL:
            self._finish(key, file_number, FileState.CANCELLED)
        elif control == core.FileControl.RESUME:
            if transfer.message_id is not None:
                self._store.set_file_state(
                    transfer.message_id, FileState.ACTIVE, transfer.done)
                self._refresh(transfer.message_id)

    def _on_file_chunk_request(
        self,
        friend_number: core.FriendNumber,
        file_number: core.FileNumber,
        position: int,
        length: int,
    ) -> None:
        assert self._tox is not None
        key = self._keys.get(friend_number)
        if key is None:
            return
        transfer = self._transfers.get((key, file_number))
        if transfer is None:
            return
        if length == 0:
            self._finish(key, file_number, FileState.DONE)
            return
        if transfer.handle is None:
            return
        try:
            transfer.handle.seek(position)
            chunk = transfer.handle.read(length)
        except OSError as exc:
            _LOG.warning("file read failed: %s", exc)
            self._cancel_transfer(key, friend_number, file_number)
            return
        try:
            self._tox.file_send_chunk(friend_number, file_number, position,
                                      chunk)
            transfer.done = max(transfer.done, position + len(chunk))
            self._progress_changed = True
        except core.ApiException:
            # toxcore asks for the chunk again.
            pass

    # ------------------------------------------------------------------
    # Internal state & transfer helpers
    # ------------------------------------------------------------------

    def _reading(self, friend_key: str) -> bool:
        return (self._visible and self._chat is not None
                and self._chat.friend == friend_key)

    def _received(self, message: Message) -> None:
        assert self._store is not None
        key = message.friend
        if self._chat is not None and self._chat.friend == key:
            self._chat = replace(
                self._chat,
                messages=self._chat.messages + (message, ),
            )
        if self._reading(key):
            self._update_friend(key, lambda f: replace(f, last=message))
            return
        friend = self._friends.get(key)
        unread = (friend.unread if friend is not None else 0) + 1
        self._store.set_unread(key, unread)
        self._update_friend(
            key, lambda f: replace(f, last=message, unread=unread))
        updated = self._friends.get(key)
        if updated is not None:
            self._platform.notify_message(self._profile_name, updated, message)

    def _note_call(self, call: Call, note: CallNote) -> None:
        """A call that ended goes in its chat; one we missed is unread."""
        assert self._store is not None
        message = self._store.add_call(call.friend, call.outgoing, note,
                                       _now_ms())
        if not call.outgoing and note.outcome == CallOutcome.MISSED:
            self._received(message)
        else:
            self._add_to_chat(message)

    def _add_to_chat(self, message: Message) -> None:
        if self._chat is not None and self._chat.friend == message.friend:
            self._chat = replace(
                self._chat,
                messages=self._chat.messages + (message, ),
            )
        self._update_friend(message.friend, lambda f: replace(f, last=message))

    def _refresh(self, message_id: int) -> None:
        assert self._store is not None
        message = self._store.message_by_id(message_id)
        if self._chat is not None and self._chat.friend == message.friend:
            self._chat = replace(
                self._chat,
                messages=tuple(
                    message if m.id == message_id else m
                    for m in self._chat.messages
                ),
            )
        self._update_friend(
            message.friend,
            lambda f: replace(
                f,
                last=(message if f.last is not None and f.last.id == message_id
                      else f.last),
            ),
        )

    def _send_to_tox(self, message: Message) -> None:
        assert self._tox is not None
        number = self._numbers.get(message.friend)
        friend = self._friends.get(message.friend)
        if number is None or friend is None or not friend.online:
            return
        if message.file is not None:
            return
        msg_type = (core.MessageType.ACTION
                    if message.action else core.MessageType.NORMAL)
        try:
            tox_msg_id = self._tox.friend_send_message(
                number, msg_type, message.text.encode("utf-8"))
            self._receipts.setdefault(message.friend,
                                      {})[tox_msg_id] = message.id
        except core.ApiException:
            # Remains undelivered in store; retried on reconnect.
            pass

    def _cancel_transfer(
        self,
        key: str,
        friend_number: core.FriendNumber,
        file_number: core.FileNumber,
    ) -> None:
        if self._tox is not None:
            try:
                self._tox.file_control(
                    friend_number, file_number, core.FileControl.CANCEL)
            except core.ApiException:
                pass
        self._finish(key, file_number, FileState.CANCELLED)

    def _cancel_outgoing_avatar(self, key: str) -> None:
        number = self._numbers.get(key)
        stale = [
            fn for (fk, fn), tr in self._transfers.items()
            if fk == key and tr.message_id is None and tr.outgoing
        ]
        for file_num in stale:
            if number is not None and self._tox is not None:
                try:
                    self._tox.file_control(
                        number, file_num, core.FileControl.CANCEL)
                except core.ApiException:
                    pass
            transfer = self._transfers.pop((key, file_num), None)
            if transfer is not None:
                transfer.close()

    def _offer_file(self, message: Message) -> None:
        assert self._tox is not None
        assert self._store is not None
        ft = message.file
        if ft is None or not ft.path.exists():
            return
        number = self._numbers.get(message.friend)
        friend = self._friends.get(message.friend)
        if number is None or friend is None or not friend.online:
            return
        fh: Optional[IO[bytes]] = None
        try:
            fid_bytes = bytes.fromhex(self._store.file_id(message.id))
            fh = ft.path.open("rb")
            file_num = self._tox.file_send(
                number,
                FILE_KIND_DATA,
                ft.size,
                fid_bytes,
                ft.name.encode("utf-8"),
            )
        except (core.ApiException, OSError, KeyError, ValueError):
            if fh is not None:
                fh.close()
            return
        self._transfers[(message.friend, file_num)] = _Transfer(
            message_id=message.id,
            outgoing=True,
            path=ft.path,
            size=ft.size,
            done=ft.done,
            handle=fh,
        )

    def _receive_file(
        self,
        key: str,
        file_number: core.FileNumber,
        size: int,
        file_id: str,
        name: str,
    ) -> None:
        assert self._store is not None
        friend_num = self._numbers.get(key)
        # Reject unknown/streaming (UINT64_MAX) or oversize offers exceeding SQLite INT64.
        if size < 0 or size > _MAX_SQLITE_INT64:
            if friend_num is not None and self._tox is not None:
                try:
                    self._tox.file_control(
                        friend_num, file_number, core.FileControl.CANCEL)
                except core.ApiException:
                    pass
            return
        known = self._store.incoming_file(key, file_id)
        if known is not None and (
            known.file is None
            or known.file.size != size
            or self._live_transfer(known.id) is not None
        ):
            known = None
        if known is None:
            dest = (self._files_dir /
                    secrets.token_hex(_DIR_ID_BYTES).upper() / name)
            message = self._store.add_file(
                friend=key,
                outgoing=False,
                name=name,
                size=size,
                file_id=file_id,
                path=dest,
                time_ms=_now_ms(),
            )
        else:
            message = known
        assert message.file is not None
        self._transfers[(key, file_number)] = _Transfer(
            message_id=message.id,
            outgoing=False,
            path=message.file.path,
            size=size,
            done=message.file.done,
        )
        if known is None:
            self._received(message)
        elif message.file.state == FileState.ACTIVE:
            self._start_receiving(key, file_number)

    def _start_receiving(self, key: str, file_number: core.FileNumber) -> None:
        assert self._tox is not None
        assert self._store is not None
        transfer = self._transfers.get((key, file_number))
        number = self._numbers.get(key)
        if transfer is None or number is None:
            return
        try:
            transfer.close()
            transfer.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            exists = transfer.path.exists()
            existing_size = transfer.path.stat().st_size if exists else 0
            mode = "r+b" if exists else "w+b"
            transfer.handle = transfer.path.open(mode)
        except OSError as exc:
            _LOG.warning("cannot open incoming file %s: %s", transfer.path, exc)
            self._cancel_transfer(key, number, file_number)
            return
        have = min(transfer.done, existing_size)
        try:
            if have > 0:
                self._tox.file_seek(number, file_number, have)
            transfer.done = have
            self._tox.file_control(number, file_number,
                                   core.FileControl.RESUME)
        except core.ApiException:
            pass
        if transfer.message_id is not None:
            self._store.set_file_state(
                transfer.message_id, FileState.ACTIVE, have)
            self._refresh(transfer.message_id)

    def _finish(self, key: str, file_number: core.FileNumber, state: FileState) -> None:
        assert self._store is not None
        transfer = self._transfers.pop((key, file_number), None)
        if transfer is None:
            return
        transfer.close()
        msg_id = transfer.message_id
        if msg_id is None:
            if not transfer.outgoing:
                self._avatar_arrived(key, transfer, state == FileState.DONE)
            return
        if state == FileState.CANCELLED and not transfer.outgoing:
            transfer.path.unlink(missing_ok=True)
        done = transfer.size if state == FileState.DONE else transfer.done
        self._store.set_file_state(msg_id, state, done)
        self._refresh(msg_id)

    def _stop_transfers(self, key: str) -> None:
        assert self._store is not None
        gone = [tk for tk in self._transfers if tk[0] == key]
        for tk in gone:
            transfer = self._transfers.pop(tk)
            transfer.close()
            if transfer.message_id is not None:
                try:
                    msg = self._store.message_by_id(transfer.message_id)
                except KeyError:
                    continue
                if msg.file is not None:
                    self._store.set_file_state(
                        transfer.message_id, msg.file.state, transfer.done)
        if gone:
            self._publish()

    def _live_transfer(
        self,
        message_id: int,
    ) -> Optional[tuple[tuple[str, core.FileNumber], _Transfer]]:
        for tk, transfer in self._transfers.items():
            if transfer.message_id == message_id:
                return tk, transfer
        return None

    def _send_avatar(self, key: str) -> None:
        assert self._tox is not None
        number = self._numbers.get(key)
        if number is None:
            return
        avatar = self._profile.avatar
        fh: Optional[IO[bytes]] = None
        try:
            if avatar is None or not avatar.path.exists():
                self._tox.file_send(
                    number,
                    FILE_KIND_AVATAR,
                    0,
                    b"\x00" * FILE_ID_LENGTH,
                    b"",
                )
                return
            size = avatar.path.stat().st_size
            fh = avatar.path.open("rb")
            file_num = self._tox.file_send(
                number,
                FILE_KIND_AVATAR,
                size,
                bytes.fromhex(avatar.hash),
                _AVATAR_NAME,
            )
            self._transfers[(key, file_num)] = _Transfer(
                message_id=None,
                outgoing=True,
                path=avatar.path,
                size=size,
                done=0,
                handle=fh,
            )
        except (core.ApiException, OSError):
            if fh is not None:
                fh.close()

    def _receive_avatar(
        self,
        key: str,
        file_number: core.FileNumber,
        size: int,
        file_hash: str,
    ) -> None:
        assert self._tox is not None
        assert self._store is not None
        number = self._numbers.get(key)
        if number is None:
            return
        friend = self._friends.get(key)
        current = friend.avatar if friend is not None else None
        if (size == 0 or size > _MAX_AVATAR_SIZE
                or (current is not None and current.hash == file_hash)):
            if size == 0 and current is not None:
                current.path.unlink(missing_ok=True)
                self._store.set_avatar_hash(key, "")
                self._update_friend(key, lambda f: replace(f, avatar=None))
            try:
                self._tox.file_control(
                    number, file_number, core.FileControl.CANCEL)
            except core.ApiException:
                pass
            return
        self._avatars_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        tmp = self._avatars_dir / f"{key}.{file_number}.tmp"
        try:
            fh = tmp.open("wb")
        except OSError as exc:
            _LOG.warning("cannot open avatar tmp %s: %s", tmp, exc)
            try:
                self._tox.file_control(
                    number, file_number, core.FileControl.CANCEL)
            except core.ApiException:
                pass
            return
        transfer = _Transfer(
            message_id=None,
            outgoing=False,
            path=tmp,
            size=size,
            done=0,
            handle=fh,
            expected_hash=file_hash,
        )
        self._transfers[(key, file_number)] = transfer
        try:
            self._tox.file_control(
                number, file_number, core.FileControl.RESUME)
        except core.ApiException:
            self._transfers.pop((key, file_number), None)
            transfer.close()
            tmp.unlink(missing_ok=True)

    def _avatar_arrived(
        self,
        key: str,
        transfer: _Transfer,
        complete: bool,
    ) -> None:
        assert self._store is not None
        if (not complete or not transfer.path.exists()
                or transfer.path.stat().st_size != transfer.size):
            transfer.path.unlink(missing_ok=True)
            return
        data = transfer.path.read_bytes()
        actual_hash = _to_hex(core.hash(data))
        if transfer.expected_hash and actual_hash != transfer.expected_hash:
            transfer.path.unlink(missing_ok=True)
            return
        dest = self._avatar_file(key)
        os.replace(transfer.path, dest)
        pic = Picture(path=dest, hash=actual_hash)
        self._store.set_avatar_hash(key, pic.hash)
        self._update_friend(key, lambda f: replace(f, avatar=pic))

    def _add_friend_number(self, number: core.FriendNumber) -> None:
        assert self._tox is not None
        assert self._store is not None
        key = _to_hex(self._tox.friend_get_public_key(number))
        self._store.add_friend(key)
        self._numbers[key] = number
        self._keys[number] = key
        self._friends[key] = self._make_friend(key, StoredFriend("", "", 0))
        self._unsaved = True
        self._publish()

    def _decline_key(self, key: str) -> None:
        assert self._store is not None
        self._store.delete_request(key)
        self._requests = [r for r in self._requests if r.key != key]
        self._publish()

    def _mark_read(self) -> None:
        assert self._store is not None
        if not self._visible:
            return
        if self._group_chat is not None:
            gid = self._group_chat.group
            self._platform.clear_group_notifications(self._profile_name, gid)
            group = self._groups.get(gid)
            if group is not None and group.unread > 0:
                self._groups[gid] = replace(group, unread=0)
            self._store.set_group_unread(gid, 0)
        if self._chat is None:
            return
        key = self._chat.friend
        self._platform.clear_notifications(self._profile_name, key)
        friend = self._friends.get(key)
        if friend is None or friend.unread == 0:
            return
        self._store.set_unread(key, 0)
        self._friends[key] = replace(friend, unread=0)

    # ------------------------------------------------------------------
    # Group internals (always on Tox thread)
    # ------------------------------------------------------------------

    def _group_self_name(self) -> bytes:
        """Our name in groups: groups need a non-empty one."""
        name = self._profile.name if self._profile.name.strip() else (
            _DEFAULT_GROUP_NAME)
        return name.encode("utf-8")

    def _load_groups(self) -> None:
        """The groups from the save, which toxcore lists for us."""
        assert self._tox is not None
        assert self._store is not None
        self._groups.clear()
        self._group_numbers.clear()
        self._group_ids.clear()
        self._peers.clear()
        unread = self._store.groups()
        for number in self._tox.group_list:
            try:
                gid = _to_hex(self._tox.group_get_chat_id(number))
            except core.ApiException:
                continue
            self._add_group(number, gid, unread.get(gid, 0))

    def _add_group(self, number: core.GroupNumber, gid: str, unread: int) -> None:
        assert self._store is not None
        self._store.add_group(gid)
        self._group_numbers[gid] = number
        self._group_ids[number] = gid
        self._peers[gid] = {}
        self._groups[gid] = Group(
            id=gid,
            name="",
            topic="",
            privacy=core.GroupPrivacyState.PUBLIC,
            connected=False,
            peers=(),
            self_role=core.GroupRole.USER,
            password="",
            peer_limit=0,
            topic_locked=False,
            unread=unread,
            last=self._store.last_group_message(gid),
            problem=None,
        )
        self._refresh_group(gid)

    def _group_of(self, number: core.GroupNumber) -> Optional[str]:
        """Our id for a group event's number; learns groups toxcore made."""
        gid = self._group_ids.get(number)
        if gid is not None:
            return gid
        assert self._tox is not None
        try:
            gid = _to_hex(self._tox.group_get_chat_id(number))
        except core.ApiException:
            return None
        self._add_group(number, gid, 0)
        return gid

    def _refresh_group(self, gid: str) -> None:
        """Read what toxcore knows about a group now."""
        assert self._tox is not None
        number = self._group_numbers.get(gid)
        group = self._groups.get(gid)
        if number is None or group is None:
            return
        tox = self._tox
        try:
            self._groups[gid] = replace(
                group,
                name=_decode_utf8(tox.group_get_name(number)),
                topic=_decode_utf8(tox.group_get_topic(number)),
                privacy=tox.group_get_privacy_state(number),
                connected=tox.group_is_connected(number),
                self_role=tox.group_get_self_role(number),
                password=_decode_utf8(tox.group_get_password(number)),
                peer_limit=tox.group_get_peer_limit(number),
                topic_locked=(tox.group_get_topic_lock(number)
                              == core.GroupTopicLock.ENABLED),
            )
        except core.ApiException:
            pass
        self._publish_peers(gid)

    def _publish_peers(self, gid: str, emit: bool = True) -> None:
        """Show a group's people, us among them, moderators first."""
        assert self._tox is not None
        number = self._group_numbers.get(gid)
        group = self._groups.get(gid)
        if number is None or group is None:
            return
        everyone = list(self._peers.get(gid, {}).values())
        if group.connected:
            tox = self._tox
            try:
                everyone.append(
                    Peer(
                        key=_to_hex(tox.group_get_self_public_key(number)),
                        name=_decode_utf8(tox.group_get_self_name(number)),
                        role=tox.group_get_self_role(number),
                        status=tox.group_get_self_status(number),
                        is_self=True,
                    ))
            except core.ApiException:
                pass
        everyone.sort(key=lambda p: (int(p.role), p.display_name.lower()))
        self._groups[gid] = replace(group, peers=tuple(everyone))
        if emit:
            self._publish()

    def _peer(self, gid: str, number: core.GroupNumber, peer_id: core.GroupPeerNumber) -> Optional[Peer]:
        assert self._tox is not None
        tox = self._tox
        try:
            peer = Peer(
                key=_to_hex(tox.group_peer_get_public_key(number, peer_id)),
                name=_decode_utf8(tox.group_peer_get_name(number, peer_id)),
                role=tox.group_peer_get_role(number, peer_id),
                status=tox.group_peer_get_status(number, peer_id),
                is_self=False,
            )
        except core.ApiException:
            return None
        self._peers.setdefault(gid, {})[peer_id] = peer
        return peer

    def _decline_invite(self, invite: GroupInvite) -> None:
        assert self._store is not None
        self._store.delete_invite(invite)
        self._invites = [i for i in self._invites if i != invite]
        self._publish()

    def _add_to_group_chat(self, message: GroupMessage) -> None:
        if (self._group_chat is not None
                and self._group_chat.group == message.group):
            self._group_chat = replace(
                self._group_chat,
                messages=self._group_chat.messages + (message, ),
            )
        group = self._groups.get(message.group)
        if group is not None:
            self._groups[message.group] = replace(group, last=message)
        self._publish()

    def _on_group_invite(
        self,
        friend_number: core.FriendNumber,
        invite_data: bytes,
        group_name: bytes,
    ) -> None:
        assert self._store is not None
        friend_key = self._keys.get(friend_number)
        if friend_key is None:
            return
        invite = GroupInvite(
            friend=friend_key,
            name=_decode_utf8(group_name),
            data=_to_hex(invite_data),
            time=_now_ms(),
        )
        self._store.add_invite(invite)
        self._invites = [
            i for i in self._invites
            if not (i.friend == friend_key and i.data == invite.data)
        ] + [invite]
        self._publish()
        friend = self._friends.get(friend_key)
        if friend is not None:
            self._platform.notify_invite(self._profile_name, friend, invite)

    def _on_group_self_join(self, number: core.GroupNumber) -> None:
        gid = self._group_of(number)
        if gid is None:
            return
        group = self._groups.get(gid)
        if group is not None:
            self._groups[gid] = replace(group, problem=None)
        self._unsaved = True
        self._refresh_group(gid)

    def _on_group_join_fail(
        self,
        number: core.GroupNumber,
        fail_type: core.GroupJoinFail,
    ) -> None:
        gid = self._group_of(number)
        if gid is None:
            return
        if fail_type == core.GroupJoinFail.PEER_LIMIT:
            problem = "The group is full."
        elif fail_type == core.GroupJoinFail.INVALID_PASSWORD:
            problem = "The password is wrong."
        else:
            problem = "Couldn't join the group."
        group = self._groups.get(gid)
        if group is not None:
            self._groups[gid] = replace(group, problem=problem)
        self._publish()

    def _on_group_peer_join(self, number: core.GroupNumber, peer_id: core.GroupPeerNumber) -> None:
        gid = self._group_of(number)
        if gid is None:
            return
        self._peer(gid, number, peer_id)
        self._publish_peers(gid)

    def _on_group_peer_exit(
        self,
        number: core.GroupNumber,
        peer_id: core.GroupPeerNumber,
        exit_type: core.GroupExitType,
    ) -> None:
        gid = self._group_of(number)
        if gid is None:
            return
        if exit_type == core.GroupExitType.SELF_DISCONNECTED:
            self._peers.get(gid, {}).clear()
            self._refresh_group(gid)
            return
        self._peers.get(gid, {}).pop(peer_id, None)
        self._publish_peers(gid)

    def _group_peer_changed(self, number: core.GroupNumber, peer_id: core.GroupPeerNumber) -> None:
        gid = self._group_of(number)
        if gid is None:
            return
        self._peer(gid, number, peer_id)
        self._publish_peers(gid)

    def _on_group_moderation(
        self,
        number: core.GroupNumber,
        target_peer_id: core.GroupPeerNumber,
        mod_type: core.GroupModEvent,
    ) -> None:
        assert self._tox is not None
        gid = self._group_of(number)
        if gid is None:
            return
        # A kick also arrives as the peer leaving; anything else changes a
        # role, possibly ours. Skip inserting ourselves into _peers[gid] since
        # _publish_peers already appends the local user entry.
        if mod_type != core.GroupModEvent.KICK:
            try:
                self_peer = self._tox.group_get_self_peer_id(number)
            except core.ApiException:
                self_peer = None
            if target_peer_id != self_peer:
                self._peer(gid, number, target_peer_id)
        self._unsaved = True
        self._refresh_group(gid)

    def _group_changed(self, number: core.GroupNumber) -> None:
        gid = self._group_of(number)
        if gid is not None:
            self._unsaved = True
            self._refresh_group(gid)

    def _on_group_message(
        self,
        number: core.GroupNumber,
        peer_id: core.GroupPeerNumber,
        msg_type: core.MessageType,
        message: bytes,
        private: bool,
    ) -> None:
        assert self._store is not None
        gid = self._group_of(number)
        if gid is None:
            return
        peer = self._peers.get(gid, {}).get(peer_id)
        if peer is None:
            peer = self._peer(gid, number, peer_id)
        if peer is None:
            return
        stored = self._store.add_group_message(
            GroupMessage(
                id=0,
                group=gid,
                peer_key=peer.key,
                peer_name=peer.name,
                outgoing=False,
                action=msg_type == core.MessageType.ACTION,
                private=private,
                text=_decode_utf8(message),
                time=_now_ms(),
                sent=True,
            ))
        reading = (self._visible and self._group_chat is not None
                   and self._group_chat.group == gid)
        if self._group_chat is not None and self._group_chat.group == gid:
            self._group_chat = replace(
                self._group_chat,
                messages=self._group_chat.messages + (stored, ),
            )
        group = self._groups.get(gid)
        if group is None:
            return
        unread = group.unread if reading else group.unread + 1
        updated = replace(group, last=stored, unread=unread)
        self._groups[gid] = updated
        self._publish()
        if reading:
            return
        self._store.set_group_unread(gid, unread)
        # Groups can be busy: only messages that mention us, or are for us
        # alone, notify.
        name = self._profile.name
        if private or (name.strip()
                       and name.lower() in stored.text.lower()):
            self._platform.notify_group_message(
                self._profile_name, updated, stored)
