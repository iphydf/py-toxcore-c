# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""Immutable client state and domain models for PyTox."""
from __future__ import annotations

import enum
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Callable
from typing import IO
from typing import Mapping
from typing import Optional

import pytox.toxcore.tox as core

SHORT_KEY = 8
PUBLIC_KEY_HEX = 64

IMAGE_EXTENSIONS: frozenset[str] = frozenset(
    {"png", "jpg", "jpeg", "gif", "webp", "bmp"})


def shown_text(text: str, hide_after_zero: bool) -> str:
    """Message text as it's shown.

    Labels stop at a zero byte, so each one shows as ``\\0``. With
    ``hide_after_zero``, what follows the first one shows as its size:
    ``hi\\0[12 bytes]``.
    """
    if hide_after_zero:
        head, zero, rest = text.partition("\0")
        if zero:
            return f"{head}\\0[{len(rest.encode())} bytes]"
    return text.replace("\0", "\\0")


@dataclass(frozen=True)
class Node:
    """A bootstrap node: host/IP, UDP port, TCP relay ports, and DHT key."""

    host: str
    port: int
    tcp_ports: tuple[int, ...]
    key: str


@dataclass(frozen=True)
class Picture:
    """A picture file and its content hash, which changes when the picture does."""

    path: Path
    hash: str


class FileState(enum.IntEnum):
    """Where a file transfer is. Values are stored in chats.db."""

    OFFERED = 0
    ACTIVE = 1
    DONE = 2
    CANCELLED = 3


@dataclass(frozen=True)
class FileTransfer:
    """A file sent or received in a chat."""

    name: str
    size: int
    state: FileState
    done: int
    path: Path

    @property
    def is_image(self) -> bool:
        """Whether this file can be displayed inline as an image."""
        if "." not in self.name:
            return False
        ext = self.name.rsplit(".", 1)[-1].lower()
        return ext in IMAGE_EXTENSIONS


class CallOutcome(enum.IntEnum):
    """How a call ended. Values are stored in chats.db."""

    ANSWERED = 0
    # Nobody answered: the caller gave up, or we were in another call.
    MISSED = 1
    # The one called said no.
    DECLINED = 2


@dataclass(frozen=True)
class CallNote:
    """A call that ended, as its chat shows it."""

    video: bool
    outcome: CallOutcome
    # How long it lasted, if answered.
    seconds: int


def duration(seconds: int) -> str:
    """A call's length, like a phone shows it: 0:42, 3:21, 1:02:03."""
    seconds = max(0, seconds)
    if seconds >= 3600:
        return f"{seconds // 3600}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"
    return f"{seconds // 60}:{seconds % 60:02d}"


@dataclass(frozen=True)
class Message:
    """A single text, action, file, or call message stored in chats.db."""

    id: int
    friend: str
    outgoing: bool
    action: bool
    text: str
    time: int
    delivered: bool
    file: Optional[FileTransfer] = None
    # A call instead of text: who called is ``outgoing``.
    call: Optional[CallNote] = None

    def preview(self, hide_after_zero: bool) -> str:
        """Single-line message summary for lists and notifications."""
        if self.file is not None:
            return f"[file] {self.file.name}"
        if self.call is not None:
            return self.call_text
        return shown_text(self.text, hide_after_zero)

    @property
    def call_text(self) -> str:
        """A call in a chat: "Call, 3:21", "Missed call" and so on."""
        call = self.call
        if call is None:
            return self.text
        what = "Video call" if call.video else "Call"
        if call.outcome == CallOutcome.ANSWERED:
            return f"{what}, {duration(call.seconds)}"
        if call.outcome == CallOutcome.MISSED:
            return f"{what}, not answered" if self.outgoing else f"Missed {what.lower()}"
        return f"{what}, declined" if self.outgoing else f"Declined {what.lower()}"


@dataclass(frozen=True)
class Profile:
    """The local user's Tox profile snapshot."""

    address: str = ""
    name: str = ""
    status_message: str = ""
    status: core.UserStatus = core.UserStatus.NONE
    connection: core.Connection = core.Connection.NONE
    avatar: Optional[Picture] = None


@dataclass(frozen=True)
class Friend:
    """A friend's snapshot, combining toxcore status and persisted details."""

    key: str
    name: str
    status_message: str
    status: core.UserStatus
    connection: core.Connection
    typing: bool
    unread: int
    last: Optional[Message]
    avatar: Optional[Picture]
    # Show what follows a zero byte in their messages as its size.
    hide_after_zero: bool

    @property
    def display_name(self) -> str:
        """Name or short public-key prefix when unnamed."""
        return self.name if self.name else self.key[:SHORT_KEY]

    @property
    def online(self) -> bool:
        """Whether the friend is currently connected via UDP or TCP."""
        return self.connection != core.Connection.NONE


@dataclass(frozen=True)
class FriendRequest:
    """A pending incoming friend request."""

    key: str
    message: str
    time: int


@dataclass(frozen=True)
class Settings:
    """User-configurable client and network settings."""

    udp: bool = True
    ipv6: bool = True
    local_discovery: bool = True
    stay_connected: bool = True
    theme: str = "system"

    def same_network(self, other: Settings) -> bool:
        """Whether Tox networking options match (changes require restart)."""
        return (self.udp == other.udp and self.ipv6 == other.ipv6
                and self.local_discovery == other.local_discovery)


@dataclass(frozen=True)
class Chat:
    """The currently open chat's loaded messages, oldest first."""

    friend: str
    messages: tuple[Message, ...]
    has_older: bool


@dataclass(frozen=True)
class Peer:
    """Someone in a group. Their key is the one they have in this group only."""

    key: str
    name: str
    role: core.GroupRole
    status: core.UserStatus
    is_self: bool

    @property
    def display_name(self) -> str:
        return self.name if self.name else self.key[:SHORT_KEY]


@dataclass(frozen=True)
class GroupMessage:
    """A message in a group chat, stored in chats.db."""

    id: int
    group: str
    peer_key: str
    peer_name: str
    outgoing: bool
    action: bool
    # Sent to one person only.
    private: bool
    text: str
    time: int
    # For ours: whether toxcore took it. Groups have no read receipts.
    sent: bool


@dataclass(frozen=True)
class Group:
    """A group (NGC) chat we're in, as toxcore and the store know it."""

    id: str
    name: str
    topic: str
    privacy: core.GroupPrivacyState
    # Whether we're in: False while joining, or after losing the connection.
    connected: bool
    # Everyone there, us too, moderators first.
    peers: tuple[Peer, ...]
    self_role: core.GroupRole
    password: str
    peer_limit: int
    topic_locked: bool
    unread: int
    last: Optional[GroupMessage]
    # Why joining failed, if it did.
    problem: Optional[str]

    @property
    def display_name(self) -> str:
        return self.name if self.name else self.id[:SHORT_KEY]

    @property
    def moderator(self) -> bool:
        return self.self_role in (core.GroupRole.FOUNDER,
                                  core.GroupRole.MODERATOR)

    @property
    def can_set_topic(self) -> bool:
        return self.moderator or (not self.topic_locked and
                                  self.self_role != core.GroupRole.OBSERVER)


@dataclass(frozen=True)
class GroupInvite:
    """A pending invite to a group from a friend."""

    friend: str
    name: str
    # toxcore's invite data in hex: it's what accepting needs.
    data: str
    time: int


@dataclass(frozen=True)
class GroupChat:
    """The currently open group's loaded messages, oldest first."""

    group: str
    messages: tuple[GroupMessage, ...]
    has_older: bool


@dataclass(frozen=True)
class Call:
    """The one call there can be at a time."""

    friend: str
    # We called. An incoming call rings until the user answers.
    outgoing: bool
    # Whether it was a video call when it started ringing.
    video_call: bool
    # Both sides are in the call, since ``started`` (ms).
    answered: bool = False
    started: int = 0
    # What the friend sends now; while it rings, what they offer.
    friend_audio: bool = True
    friend_video: bool = False
    muted: bool = False
    # Whether we send video.
    video: bool = False
    front_camera: bool = True
    # On phones: the loudspeaker rather than the earpiece.
    speaker: bool = False
    # What doesn't work on our side, for the user.
    problem: Optional[str] = None

    @property
    def ringing(self) -> bool:
        return not self.answered


@dataclass(frozen=True)
class ClientState:
    """Immutable snapshot published by ToxClient to the UI."""

    profile: Profile = field(default_factory=Profile)
    friends: tuple[Friend, ...] = ()
    requests: tuple[FriendRequest, ...] = ()
    settings: Settings = field(default_factory=Settings)
    chat: Optional[Chat] = None
    progress: Mapping[int, int] = field(default_factory=dict)
    groups: tuple[Group, ...] = ()
    invites: tuple[GroupInvite, ...] = ()
    group_chat: Optional[GroupChat] = None
    call: Optional[Call] = None


@dataclass
class PickedFile:
    """A file the user picked to send or use as an avatar."""

    name: str
    open_stream: Callable[[], IO[bytes]]


def from_path(path: Path) -> PickedFile:
    """Create a PickedFile backed by a local filesystem path."""
    return PickedFile(
        name=path.name,
        open_stream=lambda: path.open("rb"),
    )
