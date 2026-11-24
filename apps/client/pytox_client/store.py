# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""SQLite store for chats, friends, requests, and settings.

Uses the exact same schema versions and tables as kTox's ``chats.db`` so a
profile directory can be shared between kTox and PyTox.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
from typing import Any
from typing import Iterator
from typing import Optional

from pytox_client.model import CallNote
from pytox_client.model import CallOutcome
from pytox_client.model import FileState
from pytox_client.model import FileTransfer
from pytox_client.model import FriendRequest
from pytox_client.model import GroupInvite
from pytox_client.model import GroupMessage
from pytox_client.model import Message
from pytox_client.model import Settings

SCHEMA_VERSION = 3

_SELECT_MESSAGE = (
    "SELECT id, friend, outgoing, action, text, time, delivered, "
    "file_name, file_size, file_state, file_done, file_path, "
    "call_video, call_outcome, call_seconds FROM messages"
)

_SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE friends (
        key TEXT PRIMARY KEY,
        name TEXT NOT NULL DEFAULT '',
        status_message TEXT NOT NULL DEFAULT '',
        unread INTEGER NOT NULL DEFAULT 0,
        avatar_hash TEXT NOT NULL DEFAULT '',
        hide_after_zero INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE messages (
        id INTEGER PRIMARY KEY,
        friend TEXT NOT NULL,
        outgoing INTEGER NOT NULL,
        action INTEGER NOT NULL,
        text TEXT NOT NULL,
        time INTEGER NOT NULL,
        delivered INTEGER NOT NULL,
        file_name TEXT,
        file_size INTEGER,
        file_state INTEGER,
        file_done INTEGER,
        file_id TEXT,
        file_path TEXT,
        -- Set for calls only.
        call_video INTEGER,
        call_outcome INTEGER,
        call_seconds INTEGER
    )
    """,
    "CREATE INDEX messages_by_friend ON messages (friend, id)",
    """
    CREATE TABLE requests (
        key TEXT PRIMARY KEY,
        message TEXT NOT NULL,
        time INTEGER NOT NULL
    )
    """,
    "CREATE TABLE groups (chat_id TEXT PRIMARY KEY, unread INTEGER NOT NULL DEFAULT 0)",
    """
    CREATE TABLE group_messages (
        id INTEGER PRIMARY KEY,
        chat_id TEXT NOT NULL,
        peer_key TEXT NOT NULL,
        peer_name TEXT NOT NULL,
        outgoing INTEGER NOT NULL,
        action INTEGER NOT NULL,
        private INTEGER NOT NULL,
        text TEXT NOT NULL,
        time INTEGER NOT NULL,
        sent INTEGER NOT NULL
    )
    """,
    "CREATE INDEX group_messages_by_group ON group_messages (chat_id, id)",
    """
    CREATE TABLE group_invites (
        friend TEXT NOT NULL,
        name TEXT NOT NULL,
        data TEXT NOT NULL,
        time INTEGER NOT NULL,
        PRIMARY KEY (friend, data)
    )
    """,
    "CREATE TABLE settings (name TEXT PRIMARY KEY, value TEXT NOT NULL)",
)

# What takes each version to the next: the first takes 1 to 2. _SCHEMA makes
# the newest at once. Each is (table, "column TYPE") to add, as kTox has them.
_MIGRATIONS: tuple[tuple[tuple[str, str], ...], ...] = (
    (
        ("messages", "call_video INTEGER"),
        ("messages", "call_outcome INTEGER"),
        ("messages", "call_seconds INTEGER"),
    ),
    (("friends", "hide_after_zero INTEGER NOT NULL DEFAULT 0"), ),
)

_SELECT_GROUP_MESSAGE = (
    "SELECT id, chat_id, peer_key, peer_name, outgoing, action, private, "
    "text, time, sent FROM group_messages"
)


def _row_to_group_message(row: tuple[Any, ...]) -> GroupMessage:
    return GroupMessage(
        id=int(row[0]),
        group=str(row[1]),
        peer_key=str(row[2]),
        peer_name=str(row[3]),
        outgoing=bool(row[4]),
        action=bool(row[5]),
        private=bool(row[6]),
        text=str(row[7]),
        time=int(row[8]),
        sent=bool(row[9]),
    )


@dataclass(frozen=True)
class StoredFriend:
    """Persisted metadata for a friend (toxcore save omits names/history)."""

    name: str
    status_message: str
    unread: int
    avatar_hash: str = ""
    hide_after_zero: bool = False


def _parse_bool(value: Optional[str], default: bool) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    return default


def _row_to_message(row: tuple[Any, ...]) -> Message:
    file_transfer: Optional[FileTransfer]
    if row[7] is None:
        file_transfer = None
    else:
        file_transfer = FileTransfer(
            name=str(row[7]),
            size=int(row[8]) if row[8] is not None else 0,
            state=FileState(int(row[9]))
            if row[9] is not None else FileState.CANCELLED,
            done=int(row[10]) if row[10] is not None else 0,
            path=Path(str(row[11] or "")),
        )
    call: Optional[CallNote] = None
    if row[13] is not None:
        call = CallNote(
            video=bool(row[12]),
            outcome=CallOutcome(int(row[13])),
            seconds=int(row[14]) if row[14] is not None else 0,
        )
    return Message(
        id=int(row[0]),
        friend=str(row[1]),
        outgoing=bool(row[2]),
        action=bool(row[3]),
        text=str(row[4]),
        time=int(row[5]),
        delivered=bool(row[6]),
        file=file_transfer,
        call=call,
    )


class Store:
    """Chats, friend details, friend requests, and settings in SQLite.

    Only the Tox thread should call methods on an instance.
    """

    def __init__(self, path: str | Path) -> None:
        db_str = str(path)
        self._conn = sqlite3.connect(db_str, isolation_level=None)
        if db_str != ":memory:" and not db_str.startswith("file:"):
            try:
                os.chmod(db_str, 0o600)
            except OSError:
                pass
        try:
            self._conn.execute("PRAGMA journal_mode = WAL")
            cur = self._conn.execute("PRAGMA user_version")
            version = int(cur.fetchone()[0])
            if version == 0:
                with self._tx():
                    for stmt in _SCHEMA:
                        self._conn.execute(stmt)
                    self._conn.execute(
                        f"PRAGMA user_version = {SCHEMA_VERSION}")
            elif version < SCHEMA_VERSION:
                with self._tx():
                    for step in _MIGRATIONS[version - 1:]:
                        for table, column in step:
                            self._add_column(table, column)
                    self._conn.execute(
                        f"PRAGMA user_version = {SCHEMA_VERSION}")
            elif version != SCHEMA_VERSION:
                raise RuntimeError(
                    f"chats.db has schema {version}, this PyTox knows up to "
                    f"{SCHEMA_VERSION}")
        except BaseException:
            self._conn.close()
            raise

    @contextmanager
    def _tx(self) -> Iterator[None]:
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            if self._conn.in_transaction:
                self._conn.execute("ROLLBACK")
            raise
        if self._conn.in_transaction:
            self._conn.execute("COMMIT")

    def _add_column(self, table: str, column: str) -> None:
        """Add a column ("name TYPE") to ``table`` unless it's there."""
        name = column.split(" ", 1)[0]
        have = {
            str(row[0]) for row in self._conn.execute(
                f"SELECT name FROM pragma_table_info('{table}')")
        }
        if name not in have:
            self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column}")

    def close(self) -> None:
        self._conn.close()

    def friends(self) -> dict[str, StoredFriend]:
        rows = self._conn.execute(
            "SELECT key, name, status_message, unread, avatar_hash, "
            "hide_after_zero FROM friends").fetchall()
        return {
            str(row[0]): StoredFriend(
                name=str(row[1]),
                status_message=str(row[2]),
                unread=int(row[3]),
                avatar_hash=str(row[4]),
                hide_after_zero=bool(row[5]),
            )
            for row in rows
        }

    def add_friend(self, key: str) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO friends (key) VALUES (?)",
            (key, ),
        )

    def set_friend_name(self, key: str, name: str) -> None:
        self._conn.execute(
            "UPDATE friends SET name = ? WHERE key = ?",
            (name, key),
        )

    def set_friend_status_message(self, key: str, status_message: str) -> None:
        self._conn.execute(
            "UPDATE friends SET status_message = ? WHERE key = ?",
            (status_message, key),
        )

    def set_unread(self, key: str, unread: int) -> None:
        self._conn.execute(
            "UPDATE friends SET unread = ? WHERE key = ?",
            (unread, key),
        )

    def set_hide_after_zero(self, key: str, hide: bool) -> None:
        self._conn.execute(
            "UPDATE friends SET hide_after_zero = ? WHERE key = ?",
            (int(hide), key),
        )

    def set_avatar_hash(self, key: str, avatar_hash: str) -> None:
        self._conn.execute(
            "UPDATE friends SET avatar_hash = ? WHERE key = ?",
            (avatar_hash, key),
        )

    def files(self, friend: str) -> list[Path]:
        """Paths of all files in ``friend``'s chat."""
        rows = self._conn.execute(
            "SELECT file_path FROM messages "
            "WHERE friend = ? AND file_path IS NOT NULL",
            (friend, ),
        ).fetchall()
        return [Path(str(row[0])) for row in rows]

    def delete_friend(self, key: str) -> None:
        with self._tx():
            self._conn.execute("DELETE FROM friends WHERE key = ?", (key, ))
            self._conn.execute("DELETE FROM messages WHERE friend = ?",
                               (key, ))
            self._conn.execute("DELETE FROM group_invites WHERE friend = ?",
                               (key, ))

    def add_message(
        self,
        friend: str,
        outgoing: bool,
        action: bool,
        text: str,
        time_ms: int,
        delivered: bool,
    ) -> Message:
        row = self._conn.execute(
            "INSERT INTO messages "
            "(friend, outgoing, action, text, time, delivered) "
            "VALUES (?, ?, ?, ?, ?, ?) RETURNING id",
            (friend, int(outgoing), int(action), text, time_ms,
             int(delivered)),
        ).fetchone()
        msg_id = int(row[0])
        return Message(
            id=msg_id,
            friend=friend,
            outgoing=outgoing,
            action=action,
            text=text,
            time=time_ms,
            delivered=delivered,
        )

    def add_call(
        self,
        friend: str,
        outgoing: bool,
        note: CallNote,
        time_ms: int,
    ) -> Message:
        """A call that ended, in the chat: ``outgoing`` if we called."""
        row = self._conn.execute(
            "INSERT INTO messages "
            "(friend, outgoing, action, text, time, delivered, call_video, "
            "call_outcome, call_seconds) "
            "VALUES (?, ?, 0, '', ?, 1, ?, ?, ?) RETURNING id",
            (friend, int(outgoing), time_ms, int(note.video),
             int(note.outcome), note.seconds),
        ).fetchone()
        return self.message_by_id(int(row[0]))

    def add_file(
        self,
        friend: str,
        outgoing: bool,
        name: str,
        size: int,
        file_id: str,
        path: Path,
        time_ms: int,
    ) -> Message:
        row = self._conn.execute(
            "INSERT INTO messages "
            "(friend, outgoing, action, text, time, delivered, file_name, "
            "file_size, file_state, file_done, file_id, file_path) "
            "VALUES (?, ?, 0, '', ?, ?, ?, ?, ?, 0, ?, ?) RETURNING id",
            (
                friend,
                int(outgoing),
                time_ms,
                int(not outgoing),
                name,
                size,
                int(FileState.OFFERED),
                file_id,
                str(path),
            ),
        ).fetchone()
        return self.message_by_id(int(row[0]))

    def message_by_id(self, message_id: int) -> Message:
        row = self._conn.execute(
            f"{_SELECT_MESSAGE} WHERE id = ?",
            (message_id, ),
        ).fetchone()
        if row is None:
            raise KeyError(f"no message with id {message_id}")
        return _row_to_message(row)

    def set_file_state(
        self,
        message_id: int,
        state: FileState,
        done: int,
    ) -> None:
        self._conn.execute(
            "UPDATE messages SET file_state = ?, file_done = ? WHERE id = ?",
            (int(state), done, message_id),
        )

    def file_id(self, message_id: int) -> str:
        """Persistent 64-hex-char Tox file ID used across reconnections."""
        row = self._conn.execute(
            "SELECT file_id FROM messages WHERE id = ?",
            (message_id, ),
        ).fetchone()
        if row is None or row[0] is None:
            raise KeyError(f"no file_id for message {message_id}")
        return str(row[0])

    def unfinished_files(self, friend: str, outgoing: bool) -> list[Message]:
        """Files not yet done or cancelled, oldest first."""
        rows = self._conn.execute(
            f"{_SELECT_MESSAGE} WHERE friend = ? AND outgoing = ? "
            "AND file_state IN (?, ?) ORDER BY id",
            (friend, int(outgoing), int(FileState.OFFERED),
             int(FileState.ACTIVE)),
        ).fetchall()
        return [_row_to_message(row) for row in rows]

    def incoming_file(self, friend: str, file_id: str) -> Optional[Message]:
        """Unfinished incoming file matching ``file_id``, if any."""
        for message in self.unfinished_files(friend, outgoing=False):
            if self.file_id(message.id) == file_id:
                return message
        return None

    def mark_delivered(self, message_id: int) -> None:
        self._conn.execute(
            "UPDATE messages SET delivered = 1 WHERE id = ?",
            (message_id, ),
        )

    def undelivered(self, friend: str) -> list[Message]:
        """Outgoing text messages awaiting a read receipt, oldest first."""
        rows = self._conn.execute(
            f"{_SELECT_MESSAGE} WHERE friend = ? AND outgoing = 1 "
            "AND delivered = 0 AND file_name IS NULL ORDER BY id",
            (friend, ),
        ).fetchall()
        return [_row_to_message(row) for row in rows]

    def messages(
        self,
        friend: str,
        before: Optional[int],
        limit: int,
    ) -> list[Message]:
        """Up to ``limit`` messages before ``before`` (or newest), oldest first."""
        if before is None:
            rows = self._conn.execute(
                f"{_SELECT_MESSAGE} WHERE friend = ? ORDER BY id DESC LIMIT ?",
                (friend, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                f"{_SELECT_MESSAGE} WHERE friend = ? AND id < ? "
                "ORDER BY id DESC LIMIT ?",
                (friend, before, limit),
            ).fetchall()
        rows.reverse()
        return [_row_to_message(row) for row in rows]

    def last_message(self, friend: str) -> Optional[Message]:
        items = self.messages(friend, None, 1)
        return items[0] if items else None

    def groups(self) -> dict[str, int]:
        """The groups we're in and how many of their messages are unread."""
        rows = self._conn.execute(
            "SELECT chat_id, unread FROM groups").fetchall()
        return {str(r[0]): int(r[1]) for r in rows}

    def add_group(self, chat_id: str) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO groups (chat_id) VALUES (?)", (chat_id, ))

    def set_group_unread(self, chat_id: str, unread: int) -> None:
        self._conn.execute(
            "UPDATE groups SET unread = ? WHERE chat_id = ?",
            (unread, chat_id),
        )

    def delete_group(self, chat_id: str) -> None:
        with self._tx():
            self._conn.execute(
                "DELETE FROM groups WHERE chat_id = ?", (chat_id, ))
            self._conn.execute(
                "DELETE FROM group_messages WHERE chat_id = ?", (chat_id, ))

    def add_group_message(self, message: GroupMessage) -> GroupMessage:
        row = self._conn.execute(
            "INSERT INTO group_messages (chat_id, peer_key, peer_name, "
            "outgoing, action, private, text, time, sent) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id",
            (
                message.group,
                message.peer_key,
                message.peer_name,
                int(message.outgoing),
                int(message.action),
                int(message.private),
                message.text,
                message.time,
                int(message.sent),
            ),
        ).fetchone()
        return replace(message, id=int(row[0]))

    def group_messages(
        self,
        chat_id: str,
        before: Optional[int],
        limit: int,
    ) -> list[GroupMessage]:
        """Up to ``limit`` group messages before ``before``, oldest first."""
        if before is None:
            rows = self._conn.execute(
                f"{_SELECT_GROUP_MESSAGE} WHERE chat_id = ? "
                "ORDER BY id DESC LIMIT ?",
                (chat_id, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                f"{_SELECT_GROUP_MESSAGE} WHERE chat_id = ? AND id < ? "
                "ORDER BY id DESC LIMIT ?",
                (chat_id, before, limit),
            ).fetchall()
        rows.reverse()
        return [_row_to_group_message(row) for row in rows]

    def last_group_message(self, chat_id: str) -> Optional[GroupMessage]:
        items = self.group_messages(chat_id, None, 1)
        return items[0] if items else None

    def invites(self) -> list[GroupInvite]:
        rows = self._conn.execute(
            "SELECT friend, name, data, time FROM group_invites ORDER BY time"
        ).fetchall()
        return [
            GroupInvite(friend=str(r[0]), name=str(r[1]), data=str(r[2]),
                        time=int(r[3]))
            for r in rows
        ]

    def add_invite(self, invite: GroupInvite) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO group_invites (friend, name, data, time) "
            "VALUES (?, ?, ?, ?)",
            (invite.friend, invite.name, invite.data, invite.time),
        )

    def delete_invite(self, invite: GroupInvite) -> None:
        self._conn.execute(
            "DELETE FROM group_invites WHERE friend = ? AND data = ?",
            (invite.friend, invite.data),
        )

    def requests(self) -> list[FriendRequest]:
        rows = self._conn.execute(
            "SELECT key, message, time FROM requests ORDER BY time"
        ).fetchall()
        return [
            FriendRequest(key=str(r[0]), message=str(r[1]), time=int(r[2]))
            for r in rows
        ]

    def add_request(self, request: FriendRequest) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO requests (key, message, time) "
            "VALUES (?, ?, ?)",
            (request.key, request.message, request.time),
        )

    def delete_request(self, key: str) -> None:
        self._conn.execute("DELETE FROM requests WHERE key = ?", (key, ))

    def settings(self) -> Settings:
        rows = self._conn.execute(
            "SELECT name, value FROM settings"
        ).fetchall()
        values = {str(r[0]): str(r[1]) for r in rows}
        defaults = Settings()
        theme = values.get("theme", defaults.theme)
        if theme not in ("system", "light", "dark"):
            theme = defaults.theme
        return Settings(
            udp=_parse_bool(values.get("udp"), defaults.udp),
            ipv6=_parse_bool(values.get("ipv6"), defaults.ipv6),
            local_discovery=_parse_bool(
                values.get("local_discovery"), defaults.local_discovery),
            stay_connected=_parse_bool(
                values.get("stay_connected"), defaults.stay_connected),
            theme=theme,
        )

    def save_settings(self, settings: Settings) -> None:
        pairs = (
            ("udp", "true" if settings.udp else "false"),
            ("ipv6", "true" if settings.ipv6 else "false"),
            ("local_discovery",
             "true" if settings.local_discovery else "false"),
            ("stay_connected", "true" if settings.stay_connected else "false"),
            ("theme", settings.theme),
        )
        with self._tx():
            self._conn.executemany(
                "INSERT OR REPLACE INTO settings (name, value) VALUES (?, ?)",
                pairs,
            )
