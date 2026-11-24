# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""Several profiles, each with its own Tox, all online at once."""
from __future__ import annotations

import os
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Optional
from typing import Protocol

from pytox_client.model import ClientState
from pytox_client.model import Settings

PROFILES = "profiles"
_SHOWN = "shown"

# What a profile's directory has that isn't made again by itself: PyTox kept
# its one profile in the root directory before it had several.
_OLD_PROFILE = (
    "profile.tox", "chats.db", "chats.db-wal", "chats.db-shm",
    "chats.db-journal", "files", "avatars", "avatar.png", "staging",
)


class CallLine:
    """Who has the one call there can be.

    One microphone and one speaker go to one profile at a time: a profile
    takes the line for its call, on its own Tox thread.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._holder: Optional[str] = None

    def take(self, profile: str) -> bool:
        """Takes the line for ``profile``, unless another profile has it."""
        with self._lock:
            if self._holder is None:
                self._holder = profile
            return self._holder == profile

    def release(self, profile: str) -> None:
        with self._lock:
            if self._holder == profile:
                self._holder = None


def profile_dir(root: Path, profile: str) -> Path:
    return root / PROFILES / profile


def profile_names(root: Path) -> list[str]:
    """The profiles under ``root``, oldest first, after moving an old one."""
    base = root / PROFILES
    base.mkdir(parents=True, exist_ok=True)
    old = [root / name for name in _OLD_PROFILE if (root / name).exists()]
    if old:
        first = profile_dir(root, "1")
        first.mkdir(exist_ok=True)
        for path in old:
            os.replace(path, first / path.name)
    numbers = sorted(int(p.name) for p in base.iterdir()
                     if p.is_dir() and p.name.isdigit())
    return [str(n) for n in numbers]


class ProfileClient(Protocol):
    """What :class:`Profiles` needs of a :class:`ToxClient` or stand-in."""

    @property
    def state(self) -> ClientState: ...

    def start(self) -> None: ...

    def close(self) -> None: ...

    def subscribe(
        self,
        listener: Callable[[ClientState], None],
        emit_current: bool = ...,
    ) -> Callable[[], None]: ...

    def set_visible(self, visible: bool) -> Any: ...

    def update_settings(self, settings: Settings) -> Any: ...

    def watch_video(
        self, listener: Callable[..., None]) -> Callable[[], None]: ...

    def delete_profile(self) -> Any: ...


class Profiles:
    """Every profile under ``root`` and the one the UI shows.

    ``make`` makes the client for a profile's directory and name. Listeners
    hear about profiles coming, going and being shown, and every state of
    every profile, on the threads that give them.
    """

    def __init__(
        self,
        root: Path,
        make: Callable[[Path, str], ProfileClient],
    ) -> None:
        self._root = Path(root)
        self._make = make
        self._lock = threading.Lock()
        self._listeners: list[Callable[[], None]] = []
        self._clients: dict[str, ProfileClient] = {}
        self._unsubscribe: dict[str, Callable[[], None]] = {}
        names = profile_names(self._root) or ["1"]
        for name in names:
            self._add_client(name)
        shown_path = self._root / PROFILES / _SHOWN
        shown = (shown_path.read_text(encoding="utf-8").strip()
                 if shown_path.is_file() else "")
        self._shown = shown if shown in self._clients else names[0]

    def _add_client(self, name: str) -> ProfileClient:
        directory = profile_dir(self._root, name)
        directory.mkdir(parents=True, exist_ok=True)
        client = self._make(directory, name)
        with self._lock:
            self._clients[name] = client
        self._unsubscribe[name] = client.subscribe(
            lambda _state: self._changed(), emit_current=False)
        return client

    @property
    def names(self) -> list[str]:
        """Oldest first."""
        with self._lock:
            return sorted(self._clients, key=int)

    @property
    def shown(self) -> str:
        with self._lock:
            return self._shown

    def client(self, name: str) -> Optional[ProfileClient]:
        with self._lock:
            return self._clients.get(name)

    @property
    def caller(self) -> Optional[str]:
        """The profile with a call, ringing, calling out or talking."""
        for name in self.names:
            client = self.client(name)
            if client is not None and client.state.call is not None:
                return name
        return None

    def listen(self, listener: Callable[[], None]) -> Callable[[], None]:
        with self._lock:
            self._listeners.append(listener)

        def unlisten() -> None:
            with self._lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return unlisten

    def _changed(self) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            listener()

    def start(self) -> None:
        for name in self.names:
            client = self.client(name)
            if client is not None:
                client.start()

    def close(self) -> None:
        """Saves and stops them all."""
        for name in self.names:
            self._unsubscribe.pop(name, lambda: None)()
            client = self.client(name)
            if client is not None:
                client.close()

    def show(self, name: str) -> None:
        with self._lock:
            if name not in self._clients or name == self._shown:
                return
            self._shown = name
        (self._root / PROFILES / _SHOWN).write_text(name, encoding="utf-8")
        self._changed()

    def add(self) -> str:
        """Makes a new profile, starts it and shows it."""
        name = str(max(int(n) for n in self.names) + 1)
        self._add_client(name).start()
        self.show(name)
        return name

    def set_stay_connected(self, on: bool) -> None:
        """Staying connected is every profile's."""
        for name in self.names:
            client = self.client(name)
            if (client is not None
                    and client.state.settings.stay_connected != on):
                client.update_settings(
                    replace(client.state.settings, stay_connected=on))

    def delete(self, name: str) -> None:
        """Deletes ``name`` with its chats. The last one stays, as does one in
        a call.

        The profile's Tox deletes its own directory, in the process that has
        it open, then it's closed here.
        """
        names = self.names
        client = self.client(name)
        if client is None or len(names) == 1 or self.caller == name:
            return
        if self.shown == name:
            self.show(next(n for n in names if n != name))
        with self._lock:
            del self._clients[name]
        self._unsubscribe.pop(name, lambda: None)()
        client.delete_profile()
        client.close()
        self._changed()


class ShownClient:
    """The shown profile's client, for the UI.

    Calls go to the profile shown now. Listeners hear its states, and after
    a switch the new one's; only the shown profile counts as visible.
    """

    def __init__(self, profiles: Profiles) -> None:
        self._profiles = profiles
        self._lock = threading.Lock()
        self._listeners: list[Callable[[ClientState], None]] = []
        self._video_listeners: list[Callable[..., None]] = []
        self._visible = False
        self._name = profiles.shown
        self._unsubscribe = self._current().subscribe(
            self._on_state, emit_current=False)
        self._unwatch = self._current().watch_video(self._on_video)
        self._unlisten = profiles.listen(self._follow)

    def _current(self) -> ProfileClient:
        client = self._profiles.client(self._name)
        assert client is not None
        return client

    @property
    def profile(self) -> str:
        """Which profile it is now."""
        return self._name

    @property
    def state(self) -> ClientState:
        return self._current().state

    def _follow(self) -> None:
        """Moves to the profile shown now, if it changed."""
        with self._lock:
            name = self._profiles.shown
            if name == self._name:
                return
            old = self._profiles.client(self._name)
            self._name = name
            visible = self._visible
        self._unsubscribe()
        self._unwatch()
        if old is not None:
            old.set_visible(False)
        client = self._current()
        client.set_visible(visible)
        self._unwatch = client.watch_video(self._on_video)
        self._unsubscribe = client.subscribe(self._on_state, emit_current=True)

    def _on_state(self, state: ClientState) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            listener(state)

    def _on_video(self, *args: Any) -> None:
        with self._lock:
            listeners = list(self._video_listeners)
        for listener in listeners:
            listener(*args)

    def subscribe(
        self,
        listener: Callable[[ClientState], None],
        emit_current: bool = True,
    ) -> Callable[[], None]:
        with self._lock:
            self._listeners.append(listener)
        if emit_current:
            listener(self.state)

        def unsubscribe() -> None:
            with self._lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return unsubscribe

    def watch_video(self, listener: Callable[..., None]) -> Callable[[], None]:
        with self._lock:
            self._video_listeners.append(listener)

        def unwatch() -> None:
            with self._lock:
                if listener in self._video_listeners:
                    self._video_listeners.remove(listener)

        return unwatch

    def set_visible(self, visible: bool) -> None:
        with self._lock:
            self._visible = visible
        self._current().set_visible(visible)

    def close(self) -> None:
        """Closes every profile: the app is going."""
        self._unlisten()
        self._unsubscribe()
        self._unwatch()
        self._profiles.close()

    def __getattr__(self, name: str) -> Any:
        """Every other :class:`ToxClient` call, on the shown profile."""
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._current(), name)
