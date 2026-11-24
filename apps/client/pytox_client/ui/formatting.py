# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""Pure-Python display formatting helpers (no Kivy imports for fast testing)."""
from __future__ import annotations

import colorsys
import datetime
from dataclasses import dataclass
from typing import Optional
from typing import Sequence
from typing import Union

import pytox.toxcore.tox as core

from pytox_client.model import Call
from pytox_client.model import duration
from pytox_client.model import Friend
from pytox_client.model import Group
from pytox_client.model import GroupMessage
from pytox_client.model import Message
from pytox_client.model import SHORT_KEY
from pytox_client.model import shown_text

_KILO = 1024.0


@dataclass(frozen=True)
class DayItem:
    """Date divider inserted between messages from different days."""

    date: datetime.date
    occurrence: int = 0

    @property
    def key(self) -> str:
        if self.occurrence == 0:
            return f"day {self.date.isoformat()}"
        return f"day {self.date.isoformat()}#{self.occurrence}"


@dataclass(frozen=True)
class BubbleItem:
    """A single chat bubble with ``is_last`` controlling its corner tail."""

    message: Message
    is_last: bool

    @property
    def key(self) -> str:
        return f"message {self.message.id}"


ChatItem = Union[DayItem, BubbleItem]


def _safe_dt(time_ms: int) -> datetime.datetime:
    try:
        return datetime.datetime.fromtimestamp(time_ms / 1000.0)
    except (ValueError, OverflowError, OSError):
        return datetime.datetime(1970, 1, 1)


def day_of(time_ms: int) -> datetime.date:
    return _safe_dt(time_ms).date()


def clock_time(time_ms: int) -> str:
    return _safe_dt(time_ms).strftime("%H:%M")


def short_time(
    time_ms: int,
    today: Optional[datetime.date] = None,
) -> str:
    """Time today, weekday name within the last 7 days, or short date."""
    dt = day_of(time_ms)
    ref = today if today is not None else datetime.date.today()
    if dt == ref:
        return clock_time(time_ms)
    if dt > ref - datetime.timedelta(days=7):
        return dt.strftime("%a")
    return dt.strftime("%Y-%m-%d")


def day_heading(
    date: datetime.date,
    today: Optional[datetime.date] = None,
) -> str:
    ref = today if today is not None else datetime.date.today()
    if date == ref:
        return "Today"
    if date == ref - datetime.timedelta(days=1):
        return "Yesterday"
    return date.strftime("%b %d, %Y")


def grouped_id(hex_id: str) -> str:
    """Format a Tox ID / public key in 4-char groups for easy reading."""
    return " ".join(hex_id[i:i + 4] for i in range(0, len(hex_id), 4))


def file_size(num_bytes: int) -> str:
    """Human-readable byte count (e.g. ``512 B``, ``1.4 MB``)."""
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < _KILO or unit == "GB":
            if unit == "B":
                return f"{num_bytes} B"
            return f"{value:.1f} {unit}"
        value /= _KILO
    return f"{value:.1f} GB"


def presence_text(
    connection: core.Connection,
    status: core.UserStatus,
) -> str:
    if connection == core.Connection.NONE:
        return "offline"
    if status == core.UserStatus.AWAY:
        return "away"
    if status == core.UserStatus.BUSY:
        return "busy"
    return "online"


def self_connection_text(connection: core.Connection, long: bool = False) -> str:
    if connection == core.Connection.NONE:
        return ("Connecting to the Tox network..."
                if long else "Connecting...")
    if connection == core.Connection.TCP:
        return ("Online through a TCP relay"
                if long else "Online (TCP)")
    return "Online"


def call_status(call: Call, now_ms: int) -> str:
    """Where a call is: ringing, or how long it has lasted."""
    if call.outgoing and call.ringing:
        return "Calling…"
    if call.ringing:
        return "Incoming video call" if call.video_call else "Incoming call"
    lasted = duration(max(0, now_ms - call.started) // 1000)
    return lasted if call.friend_audio else f"{lasted} · they're muted"


def friend_subtitle(friend: Friend) -> str:
    if friend.typing:
        return "typing..."
    if friend.status_message.strip():
        return friend.status_message
    return presence_text(friend.connection, friend.status)


def friend_row_preview(friend: Friend) -> str:
    if friend.typing:
        return "typing..."
    last = friend.last
    if last is None:
        return friend_subtitle(friend)
    if last.action:
        who = "You" if last.outgoing else friend.display_name
        return f"* {who} {shown_text(last.text, friend.hide_after_zero)}"
    if last.outgoing:
        return f"You: {last.preview(friend.hide_after_zero)}"
    return last.preview(friend.hide_after_zero)


def avatar_rgba(key_hex: str) -> tuple[float, float, float, float]:
    """Deterministic HSL-derived circle background color for a friend key."""
    prefix = key_hex[:6]
    try:
        hue_deg = int(prefix, 16) % 360
    except ValueError:
        hue_deg = 0
    # colorsys.hls_to_rgb uses (H, L, S) in [0, 1].
    r, g, b = colorsys.hls_to_rgb(hue_deg / 360.0, 0.48, 0.48)
    return (r, g, b, 1.0)


def chat_items(messages: Sequence[Message]) -> list[ChatItem]:
    """Build display items oldest-first with day dividers and bubble tails."""
    items: list[ChatItem] = []
    seen_days: dict[datetime.date, int] = {}
    for i, msg in enumerate(messages):
        d = day_of(msg.time)
        if i == 0 or day_of(messages[i - 1].time) != d:
            occ = seen_days.get(d, 0)
            seen_days[d] = occ + 1
            items.append(DayItem(date=d, occurrence=occ))
        nxt = messages[i + 1] if i + 1 < len(messages) else None
        is_last = (nxt is None or nxt.outgoing != msg.outgoing
                   or day_of(nxt.time) != d)
        items.append(BubbleItem(message=msg, is_last=is_last))
    return items


@dataclass(frozen=True)
class GroupBubbleItem:
    """A group chat bubble; ``is_first`` shows the sender's name."""

    message: GroupMessage
    is_first: bool
    is_last: bool

    @property
    def key(self) -> str:
        return f"message {self.message.id}"


GroupChatItem = Union[DayItem, GroupBubbleItem]


def _sender(msg: GroupMessage) -> str:
    return "" if msg.outgoing else msg.peer_key


def group_chat_items(messages: Sequence[GroupMessage]) -> list[GroupChatItem]:
    """Day dividers plus bubbles grouped by sender within a day."""
    items: list[GroupChatItem] = []
    seen_days: dict[datetime.date, int] = {}
    for i, msg in enumerate(messages):
        d = day_of(msg.time)
        prev = messages[i - 1] if i > 0 else None
        nxt = messages[i + 1] if i + 1 < len(messages) else None
        new_day = prev is None or day_of(prev.time) != d
        if new_day:
            occ = seen_days.get(d, 0)
            seen_days[d] = occ + 1
            items.append(DayItem(date=d, occurrence=occ))
        is_first = new_day or prev is None or _sender(prev) != _sender(msg)
        is_last = (nxt is None or _sender(nxt) != _sender(msg)
                   or day_of(nxt.time) != d)
        items.append(
            GroupBubbleItem(message=msg, is_first=is_first, is_last=is_last))
    return items


def group_subtitle(group: Group) -> str:
    if group.problem is not None:
        return group.problem
    if not group.connected:
        return "Connecting..."
    # Joined by chat ID and nobody found yet: the name comes from the others.
    if not group.name and len(group.peers) <= 1:
        return "Looking for the group..."
    count = len(group.peers)
    people = "person" if count == 1 else "people"
    topic = f" - {group.topic}" if group.topic.strip() else ""
    return f"{count} {people}{topic}"


def group_row_preview(group: Group) -> str:
    last = group.last
    if last is None:
        return group_subtitle(group)
    who = "You" if last.outgoing else (
        last.peer_name or last.peer_key[:SHORT_KEY])
    if last.action:
        return f"* {who} {shown_text(last.text, False)}"
    return f"{who}: {shown_text(last.text, False)}"


def role_label(role: core.GroupRole) -> str:
    if role == core.GroupRole.FOUNDER:
        return "Founder"
    if role == core.GroupRole.MODERATOR:
        return "Moderator"
    if role == core.GroupRole.OBSERVER:
        return "Can only read"
    return ""


def group_rgba(group_id: str) -> tuple[float, float, float, float]:
    """Rounded-square background for a group's letter avatar."""
    try:
        hue_deg = int(group_id[:6], 16) % 360
    except ValueError:
        hue_deg = 0
    r, g, b = colorsys.hls_to_rgb(hue_deg / 360.0, 0.45, 0.40)
    return (r, g, b, 1.0)


def peer_rgba(key_hex: str, dark: bool) -> tuple[float, float, float, float]:
    """A colour of its own for each peer's name, readable on its bubble."""
    try:
        hue_deg = int(key_hex[:6], 16) % 360
    except ValueError:
        hue_deg = 0
    r, g, b = colorsys.hls_to_rgb(hue_deg / 360.0, 0.7 if dark else 0.4, 0.6)
    return (r, g, b, 1.0)
