# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""Simple page stack navigator matching kTox's ``Navigator.kt``."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from typing import Union


@dataclass(frozen=True)
class ChatsPage:
    """Root chat list page."""


@dataclass(frozen=True)
class ChatRoute:
    """Open 1-on-1 chat page for a friend."""

    friend: str


@dataclass(frozen=True)
class FriendRoute:
    """Details / public key / remove page for a friend."""

    friend: str


@dataclass(frozen=True)
class GroupRoute:
    """Open group chat page."""

    group: str


@dataclass(frozen=True)
class GroupInfoRoute:
    """Topic, invites, people, settings, and leave page for a group."""

    group: str


@dataclass(frozen=True)
class AddRoute:
    """Add a friend by Tox ID."""


@dataclass(frozen=True)
class ProfileRoute:
    """Local profile, avatar, status, and QR code page."""


@dataclass(frozen=True)
class SettingsRoute:
    """Network, theme, and Android background-service settings page."""


@dataclass(frozen=True)
class CallRoute:
    """The call, on a page of its own while there is one."""


Page = Union[
    ChatsPage,
    ChatRoute,
    FriendRoute,
    GroupRoute,
    GroupInfoRoute,
    AddRoute,
    ProfileRoute,
    SettingsRoute,
    CallRoute,
]


class Navigator:
    """Page back stack: always starts at :class:`ChatsPage`."""

    def __init__(self, on_change: Callable[[Page], None] | None = None) -> None:
        self._stack: list[Page] = [ChatsPage()]
        self._on_change = on_change

    def set_listener(self, on_change: Callable[[Page], None]) -> None:
        self._on_change = on_change

    @property
    def current(self) -> Page:
        return self._stack[-1]

    @property
    def can_go_back(self) -> bool:
        return len(self._stack) > 1

    def show(self, page: Page) -> None:
        """Jump to ``page`` directly on top of the root chat list."""
        prev = self._stack[-1]
        self._stack = [ChatsPage()]
        if not isinstance(page, ChatsPage):
            self._stack.append(page)
        if self._stack[-1] != prev and self._on_change is not None:
            self._on_change(self._stack[-1])

    def push(self, page: Page) -> None:
        """Push ``page`` onto the stack if it isn't already current."""
        if self._stack[-1] == page:
            return
        self._stack.append(page)
        if self._on_change is not None:
            self._on_change(page)

    def drop(self, page: Page) -> None:
        """Take ``page`` out of the stack, wherever it is."""
        if page not in self._stack[1:]:
            return
        top = self._stack[-1]
        self._stack = [p for p in self._stack if p != page]
        if self._stack[-1] != top and self._on_change is not None:
            self._on_change(self._stack[-1])

    def back(self) -> bool:
        """Pop the top page; return False if already at the root."""
        if not self.can_go_back:
            return False
        self._stack.pop()
        if self._on_change is not None:
            self._on_change(self._stack[-1])
        return True
