# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""The UI's client on phones: Tox runs in the app or in the background service.

While "stay connected" is on, the service owns the profile and the UI talks to
it over :mod:`service_ipc`; while it's off, the app runs its own
:class:`ToxClient`. Only one of them has the profile open at a time: a switch
closes one before the other starts, and calls made in between wait for the new
one.
"""
from __future__ import annotations

import shutil
import threading
from concurrent.futures import Future
from dataclasses import replace
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Optional
from typing import Union

import pytox.toxcore.tox as core

from pytox_client.calls import FRIEND
from pytox_client.calls import SELF
from pytox_client.calls import VideoListener
from pytox_client.client import ToxClient
from pytox_client.media import VideoFrame
from pytox_client.model import ClientState
from pytox_client.model import PickedFile
from pytox_client.platform_base import Platform
from pytox_client.service_ipc import RemoteClient
from pytox_client.service_ipc import SOCKET_NAME
from pytox_client.service_ipc import stage_picked_file
from pytox_client.service_ipc import staged_picked_file

_Backend = Union[ToxClient, RemoteClient]

# Calls the new client has to hear again: it starts with nothing open.
_REMEMBERED = ("open_chat", "open_group", "set_visible")

# Waits between tries to reach the service while it starts.
_RETRY_FIRST_S = 0.1
_RETRY_MAX_S = 2.0


def _offline(state: ClientState) -> ClientState:
    """What the UI shows while no Tox is running for it."""
    return replace(
        state,
        profile=replace(state.profile, connection=core.Connection.NONE),
        friends=tuple(
            replace(f, connection=core.Connection.NONE, typing=False)
            for f in state.friends),
        call=None,
    )


def _copy_result(source: Future[Any], target: Future[Any]) -> None:
    try:
        target.set_result(source.result())
    except BaseException as exc:  # noqa: BLE001
        target.set_exception(exc)


class HandoverClient:
    """Runs Tox where "stay connected" says, with :class:`ToxClient`'s API."""

    def __init__(
        self,
        directory: Path,
        platform: Platform,
        in_service: bool,
        make_local: Optional[Callable[[], ToxClient]] = None,
    ) -> None:
        """``in_service`` is where to start, until a state says otherwise."""
        self._dir = Path(directory)
        self._platform = platform
        self._make_local = make_local or (
            lambda: ToxClient(directory, platform))
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._ready = threading.Event()
        self._closing = False
        self._in_service = in_service
        self._local_retry_delay = _RETRY_FIRST_S
        self._backend: Optional[_Backend] = None
        self._unsubscribe: Optional[Callable[[], None]] = None
        self._unwatch: Optional[Callable[[], None]] = None
        self._state = ClientState()
        self._listeners: list[Callable[[ClientState], None]] = []
        self._video_listeners: list[VideoListener] = []
        self._remembered: dict[
            str, tuple[tuple[Any, ...], dict[str, Any]]] = {}
        self._waiting: list[
            tuple[str, tuple[Any, ...], dict[str, Any], Future[Any]]] = []
        self._thread = threading.Thread(
            target=self._run, name="pytox-handover", daemon=True)

    @property
    def directory(self) -> Path:
        return self._dir

    @property
    def state(self) -> ClientState:
        with self._lock:
            return self._state

    def start(self) -> None:
        self._thread.start()

    def wait_ready(self, timeout: float) -> bool:
        """Wait for the profile's first state, so the UI starts with it."""
        return self._ready.wait(timeout)

    def subscribe(
        self,
        listener: Callable[[ClientState], None],
        emit_current: bool = True,
    ) -> Callable[[], None]:
        with self._lock:
            self._listeners.append(listener)
            current = self._state
        if emit_current:
            listener(current)

        def unsubscribe() -> None:
            with self._lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return unsubscribe

    def watch_video(self, listener: VideoListener) -> Callable[[], None]:
        """The call's pictures, from whichever client runs now."""
        with self._lock:
            self._video_listeners.append(listener)

        def unwatch() -> None:
            with self._lock:
                if listener in self._video_listeners:
                    self._video_listeners.remove(listener)

        return unwatch

    def _on_video(self, who: str, frame: Optional[VideoFrame]) -> None:
        with self._lock:
            listeners = list(self._video_listeners)
        for listener in listeners:
            listener(who, frame)

    def close(self) -> None:
        """Close what runs here: a running service keeps running."""
        with self._lock:
            self._closing = True
            waiting, self._waiting = self._waiting, []
        for name, args, _kwargs, fut in waiting:
            if name == "_send_staged":
                staged: Path = args[1]
                staged.unlink(missing_ok=True)
            if not fut.done():
                fut.set_exception(ConnectionError("Client closed."))
        self._wake.set()
        if self._thread.is_alive():
            self._thread.join(timeout=15.0)

    def delete_profile(self) -> None:
        """Delete the profile where it runs, and stop here."""
        with self._lock:
            backend = self._live_backend_locked()
        if backend is not None:
            backend.delete_profile()
        self.close()
        if backend is None:
            # In the middle of a switch nothing has it open.
            shutil.rmtree(self._dir, ignore_errors=True)

    def send_file(self, friend_key: str, picked: PickedFile) -> None:
        """Stage a file without stalling ``_lock`` on remote I/O or losing handovers."""
        with self._lock:
            if self._closing:
                return
            backend = self._live_backend_locked()
            if backend is None:
                self._waiting.append(
                    ("send_file", (friend_key, picked), {}, Future()))
                if self._backend is not None:
                    self._wake.set()
                return
            if isinstance(backend, ToxClient):
                backend.send_file(friend_key, picked)
                return
        # Remote backend: copy picked stream into staging/ without holding _lock,
        # then hand the staged file under _lock to whichever backend is live so a
        # handover (or service crash) during the copy never drops the file.
        staged = stage_picked_file(self._dir, picked)
        with self._lock:
            if self._closing:
                staged.unlink(missing_ok=True)
                return
            backend = self._live_backend_locked()
            if isinstance(backend, RemoteClient):
                if backend.send_staged_file(friend_key, staged, picked.name):
                    return
                self._waiting.append(
                    ("_send_staged", (friend_key, staged, picked.name), {},
                     Future()))
                self._wake.set()
                return
            if isinstance(backend, ToxClient):
                backend.send_file(
                    friend_key, staged_picked_file(staged, picked.name))
                return
            self._waiting.append(
                ("_send_staged", (friend_key, staged, picked.name), {},
                 Future()))
            if self._backend is not None:
                self._wake.set()

    def _live_backend_locked(self) -> Optional[_Backend]:
        backend = self._backend
        if isinstance(backend, RemoteClient) and not backend.connected:
            return None
        if isinstance(backend, ToxClient) and backend.closed:
            return None
        return backend

    def __getattr__(self, name: str) -> Callable[..., Any]:
        """Every other :class:`ToxClient` call, on the client running now."""
        if name.startswith("_"):
            raise AttributeError(name)

        def call(*args: Any, **kwargs: Any) -> Any:
            # Under the lock, so a switch can't close this backend before
            # the call reaches it.
            with self._lock:
                fut: Future[Any] = Future()
                if self._closing:
                    fut.set_exception(ConnectionError("Client closed."))
                    return fut
                backend = self._live_backend_locked()
                if name in _REMEMBERED:
                    self._remembered[name] = (args, kwargs)
                    if backend is None:
                        if self._backend is not None:
                            self._wake.set()
                        fut.set_result(None)
                        return fut
                elif backend is None:
                    self._waiting.append((name, args, kwargs, fut))
                    if self._backend is not None:
                        self._wake.set()
                    return fut
                return getattr(backend, name)(*args, **kwargs)

        return call

    def _run(self) -> None:
        try:
            while self._step():
                pass
        finally:
            with self._lock:
                backend = self._backend
            if backend is not None:
                self._detach(backend)

    def _step(self) -> bool:
        """Take the next step of a switch, or wait: False when closing."""
        self._wake.clear()
        with self._lock:
            if self._closing:
                return False
            backend = self._backend
            in_service = self._in_service
        if isinstance(backend, RemoteClient):
            if not backend.connected:
                # The service closed its Tox: on purpose if staying connected
                # went off, otherwise it died and starts again below.
                self._detach(backend)
                return True
        elif isinstance(backend, ToxClient):
            if in_service:
                # Saves and frees the profile before the service opens it.
                self._local_retry_delay = _RETRY_FIRST_S
                self._detach(backend)
                return True
            if backend.closed:
                # Local client exited unexpectedly (e.g. profile lock timed out
                # behind a slow service shutdown); back off and try again.
                delay = self._local_retry_delay
                self._local_retry_delay = min(delay * 2, _RETRY_MAX_S)
                self._detach(backend)
                self._wake.wait(delay)
                return True
        elif in_service:
            remote = self._reach_service()
            if remote is not None:
                self._attach(remote)
            return True
        else:
            local = self._make_local()
            local.set_on_closed(self._wake.set)
            # Listening before it starts: its first state is the profile.
            if self._attach(local):
                local.start()
            return True
        self._wake.wait()
        return True

    def _reach_service(self) -> Optional[RemoteClient]:
        delay = _RETRY_FIRST_S
        while True:
            with self._lock:
                if self._closing:
                    return None
            try:
                self._platform.start_service()
            except Exception:  # noqa: BLE001
                # Android doesn't let an app in the background start one: the
                # next try may be in the foreground again.
                pass
            remote = RemoteClient(
                self._dir, self._dir / SOCKET_NAME, on_closed=self._wake.set)
            if remote.connect(timeout=1.0):
                return remote
            self._wake.wait(delay)
            self._wake.clear()
            delay = min(delay * 2, _RETRY_MAX_S)

    def _attach(self, backend: _Backend) -> bool:
        """Make ``backend`` the one the UI uses: False if closing instead."""
        replay_unstaged: list[
            tuple[str, PickedFile, Future[Any]]] = []
        with self._lock:
            if self._closing:
                closing = True
            else:
                # Under the lock: the calls that waited go first, in order.
                closing = False
                self._backend = backend
                for name, (rargs, rkwargs) in self._remembered.items():
                    getattr(backend, name)(*rargs, **rkwargs)
                waiting, self._waiting = self._waiting, []
                for name, args, kwargs, fut in waiting:
                    if name == "_send_staged":
                        fk, staged_path, fname = args
                        if isinstance(backend, RemoteClient):
                            if backend.send_staged_file(fk, staged_path, fname):
                                fut.set_result(None)
                            else:
                                self._waiting.append((name, args, kwargs, fut))
                                self._wake.set()
                        else:
                            backend.send_file(
                                fk, staged_picked_file(staged_path, fname))
                            fut.set_result(None)
                    elif (name == "send_file"
                          and isinstance(backend, RemoteClient)):
                        fk_u: str = args[0] if args else kwargs["friend_key"]
                        pf_u: PickedFile = (
                            args[1] if len(args) > 1 else kwargs["picked"])
                        replay_unstaged.append((fk_u, pf_u, fut))
                    else:
                        self._replay(backend, name, args, kwargs, fut)
        if closing:
            backend.close()
            return False
        for fk_u, pf_u, fut in replay_unstaged:
            try:
                staged_u = stage_picked_file(self._dir, pf_u)
            except Exception as exc:  # noqa: BLE001
                if not fut.done():
                    fut.set_exception(exc)
                continue
            with self._lock:
                if self._closing:
                    staged_u.unlink(missing_ok=True)
                    if not fut.done():
                        fut.set_exception(ConnectionError("Client closed."))
                    continue
                if isinstance(backend, RemoteClient) and backend.send_staged_file(
                        fk_u, staged_u, pf_u.name):
                    fut.set_result(None)
                else:
                    self._waiting.append(
                        ("_send_staged", (fk_u, staged_u, pf_u.name), {}, fut))
                    self._wake.set()
        # A remote one has the service's state since connecting; a local one
        # has none until it starts.
        unsubscribe = backend.subscribe(
            lambda s: self._on_state(backend, s),
            emit_current=isinstance(backend, RemoteClient))
        unwatch = backend.watch_video(self._on_video)
        with self._lock:
            self._unsubscribe = unsubscribe
            self._unwatch = unwatch
        return True

    @staticmethod
    def _replay(
        backend: _Backend,
        name: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        fut: Future[Any],
    ) -> None:
        try:
            result = getattr(backend, name)(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            fut.set_exception(exc)
            return
        if isinstance(result, Future):

            def _done(source: Future[Any]) -> None:
                _copy_result(source, fut)

            result.add_done_callback(_done)
        else:
            fut.set_result(result)

    def _detach(self, backend: _Backend) -> None:
        with self._lock:
            unsubscribe, self._unsubscribe = self._unsubscribe, None
            unwatch, self._unwatch = self._unwatch, None
            self._backend = None
            self._state = _offline(self._state)
            state = self._state
            listeners = list(self._listeners)
        if unsubscribe is not None:
            unsubscribe()
        if unwatch is not None:
            unwatch()
        if isinstance(backend, ToxClient):
            backend.set_on_closed(None)
        backend.close()
        for fn in listeners:
            fn(state)
        for who in (FRIEND, SELF):
            self._on_video(who, None)

    def _on_state(self, backend: _Backend, state: ClientState) -> None:
        with self._lock:
            if backend is not self._backend:
                return
            self._state = state
            if isinstance(backend, ToxClient) and state.profile.address:
                self._local_retry_delay = _RETRY_FIRST_S
            moved = state.settings.stay_connected != self._in_service
            self._in_service = state.settings.stay_connected
            listeners = list(self._listeners)
        if moved:
            self._wake.set()
        self._ready.set()
        for fn in listeners:
            fn(state)
