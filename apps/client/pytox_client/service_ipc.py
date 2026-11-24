# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""Local Unix-socket IPC bridge between the Android background service and UI.

On Android, a ``python-for-android`` foreground service executes in its own
process so Tox stays connected when the user closes the UI activity.  Rather
than two processes racing on ``profile.tox`` / ``chats.db``, the service owns
the single :class:`ToxClient` and publishes JSON-encoded :class:`ClientState`
snapshots over a private Unix domain socket inside the app's files directory.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import secrets
import socket
import struct
import threading
from collections import deque
from concurrent.futures import Future
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Optional

import pytox.toxcore.tox as core

from pytox_client.calls import FRIEND
from pytox_client.calls import SELF
from pytox_client.calls import VideoListener
from pytox_client.client import ToxClient
from pytox_client.media import VideoFrame
from pytox_client.model import Call
from pytox_client.model import CallNote
from pytox_client.model import CallOutcome
from pytox_client.model import Chat
from pytox_client.model import ClientState
from pytox_client.model import FileState
from pytox_client.model import FileTransfer
from pytox_client.model import Friend
from pytox_client.model import FriendRequest
from pytox_client.model import Group
from pytox_client.model import GroupChat
from pytox_client.model import GroupInvite
from pytox_client.model import GroupMessage
from pytox_client.model import Message
from pytox_client.model import Peer
from pytox_client.model import PickedFile
from pytox_client.model import Picture
from pytox_client.model import Profile
from pytox_client.model import Settings

SOCKET_NAME = "pytox.sock"
# The call's pictures go on a socket of their own, in binary: each is a header
# and the three planes. A picture that's gone sends only the header.
VIDEO_SOCKET_NAME = "pytox-video.sock"
_PICTURE = struct.Struct("<BBHHIIIIII")
_WHO = (FRIEND, SELF)
_SHOWN = 1
_MIRRORED = 2
_MAX_LINE_BYTES = 16 * 1024 * 1024
_MAX_VIDEO_BYTES = 16 * 1024 * 1024
_MAX_WRITER_REPLIES = 256
_VALID_THEMES = ("system", "light", "dark")

_LOG = logging.getLogger(__name__)


def _read_line_bounded(reader: io.BufferedReader) -> Optional[str]:
    """Read a UTF-8 JSON line up to :data:`_MAX_LINE_BYTES`, or None at EOF."""
    raw = reader.readline(_MAX_LINE_BYTES + 1)
    if not raw:
        return None
    if len(raw) > _MAX_LINE_BYTES:
        raise ValueError("IPC frame exceeds maximum allowed size")
    return raw.decode("utf-8")


def _read_exact(reader: io.BufferedReader, size: int) -> Optional[bytes]:
    if size == 0:
        return b""
    buf = bytearray()
    while len(buf) < size:
        chunk = reader.read(size - len(buf))
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)


def _pic_to_dict(pic: Optional[Picture]) -> Optional[dict[str, str]]:
    if pic is None:
        return None
    return {"path": str(pic.path), "hash": pic.hash}


def _pic_from_dict(data: Optional[dict[str, Any]]) -> Optional[Picture]:
    if data is None:
        return None
    return Picture(path=Path(str(data["path"])), hash=str(data["hash"]))


def _msg_to_dict(msg: Message) -> dict[str, Any]:
    file_dict: Optional[dict[str, Any]] = None
    if msg.file is not None:
        file_dict = {
            "name": msg.file.name,
            "size": msg.file.size,
            "state": int(msg.file.state),
            "done": msg.file.done,
            "path": str(msg.file.path),
        }
    return {
        "id": msg.id,
        "friend": msg.friend,
        "outgoing": msg.outgoing,
        "action": msg.action,
        "text": msg.text,
        "time": msg.time,
        "delivered": msg.delivered,
        "file": file_dict,
        "call": None if msg.call is None else {
            "video": msg.call.video,
            "outcome": int(msg.call.outcome),
            "seconds": msg.call.seconds,
        },
    }


def _msg_from_dict(data: dict[str, Any]) -> Message:
    ft_data = data.get("file")
    ft: Optional[FileTransfer] = None
    if ft_data is not None:
        ft = FileTransfer(
            name=str(ft_data["name"]),
            size=int(ft_data["size"]),
            state=FileState(int(ft_data["state"])),
            done=int(ft_data["done"]),
            path=Path(str(ft_data["path"])),
        )
    call_data = data.get("call")
    call: Optional[CallNote] = None
    if call_data is not None:
        call = CallNote(
            video=bool(call_data["video"]),
            outcome=CallOutcome(int(call_data["outcome"])),
            seconds=int(call_data["seconds"]),
        )
    return Message(
        id=int(data["id"]),
        friend=str(data["friend"]),
        outgoing=bool(data["outgoing"]),
        action=bool(data["action"]),
        text=str(data["text"]),
        time=int(data["time"]),
        delivered=bool(data["delivered"]),
        file=ft,
        call=call,
    )


def _gmsg_to_dict(msg: GroupMessage) -> dict[str, Any]:
    return {
        "id": msg.id,
        "group": msg.group,
        "peer_key": msg.peer_key,
        "peer_name": msg.peer_name,
        "outgoing": msg.outgoing,
        "action": msg.action,
        "private": msg.private,
        "text": msg.text,
        "time": msg.time,
        "sent": msg.sent,
    }


def _gmsg_from_dict(data: dict[str, Any]) -> GroupMessage:
    return GroupMessage(
        id=int(data["id"]),
        group=str(data["group"]),
        peer_key=str(data["peer_key"]),
        peer_name=str(data["peer_name"]),
        outgoing=bool(data["outgoing"]),
        action=bool(data["action"]),
        private=bool(data["private"]),
        text=str(data["text"]),
        time=int(data["time"]),
        sent=bool(data["sent"]),
    )


def _group_to_dict(group: Group) -> dict[str, Any]:
    return {
        "id": group.id,
        "name": group.name,
        "topic": group.topic,
        "privacy": int(group.privacy),
        "connected": group.connected,
        "peers": [
            {
                "key": p.key,
                "name": p.name,
                "role": int(p.role),
                "status": int(p.status),
                "is_self": p.is_self,
            } for p in group.peers
        ],
        "self_role": int(group.self_role),
        "password": group.password,
        "peer_limit": group.peer_limit,
        "topic_locked": group.topic_locked,
        "unread": group.unread,
        "last": _gmsg_to_dict(group.last) if group.last is not None else None,
        "problem": group.problem,
    }


def _group_from_dict(data: dict[str, Any]) -> Group:
    problem = data.get("problem")
    return Group(
        id=str(data["id"]),
        name=str(data["name"]),
        topic=str(data["topic"]),
        privacy=core.GroupPrivacyState(int(data["privacy"])),
        connected=bool(data["connected"]),
        peers=tuple(
            Peer(
                key=str(p["key"]),
                name=str(p["name"]),
                role=core.GroupRole(int(p["role"])),
                status=core.UserStatus(int(p["status"])),
                is_self=bool(p["is_self"]),
            ) for p in data["peers"]),
        self_role=core.GroupRole(int(data["self_role"])),
        password=str(data["password"]),
        peer_limit=int(data["peer_limit"]),
        topic_locked=bool(data["topic_locked"]),
        unread=int(data["unread"]),
        last=(_gmsg_from_dict(data["last"])
              if data.get("last") is not None else None),
        problem=str(problem) if problem is not None else None,
    )


def _invite_to_dict(invite: GroupInvite) -> dict[str, Any]:
    return {
        "friend": invite.friend,
        "name": invite.name,
        "data": invite.data,
        "time": invite.time,
    }


def _invite_from_dict(data: dict[str, Any]) -> GroupInvite:
    return GroupInvite(
        friend=str(data["friend"]),
        name=str(data["name"]),
        data=str(data["data"]),
        time=int(data["time"]),
    )


def _call_to_dict(call: Optional[Call]) -> Optional[dict[str, Any]]:
    if call is None:
        return None
    return {
        "friend": call.friend,
        "outgoing": call.outgoing,
        "video_call": call.video_call,
        "answered": call.answered,
        "started": call.started,
        "friend_audio": call.friend_audio,
        "friend_video": call.friend_video,
        "muted": call.muted,
        "video": call.video,
        "front_camera": call.front_camera,
        "speaker": call.speaker,
        "problem": call.problem,
    }


def _call_from_dict(data: Optional[dict[str, Any]]) -> Optional[Call]:
    if data is None:
        return None
    problem = data.get("problem")
    return Call(
        friend=str(data["friend"]),
        outgoing=bool(data["outgoing"]),
        video_call=bool(data["video_call"]),
        answered=bool(data["answered"]),
        started=int(data["started"]),
        friend_audio=bool(data["friend_audio"]),
        friend_video=bool(data["friend_video"]),
        muted=bool(data["muted"]),
        video=bool(data["video"]),
        front_camera=bool(data["front_camera"]),
        speaker=bool(data["speaker"]),
        problem=str(problem) if problem is not None else None,
    )


def state_to_dict(state: ClientState) -> dict[str, Any]:
    """Serialize an immutable :class:`ClientState` to a JSON-safe dict."""
    chat_data: Optional[dict[str, Any]] = None
    if state.chat is not None:
        chat_data = {
            "friend": state.chat.friend,
            "messages": [_msg_to_dict(m) for m in state.chat.messages],
            "has_older": state.chat.has_older,
        }
    group_chat_data: Optional[dict[str, Any]] = None
    if state.group_chat is not None:
        group_chat_data = {
            "group": state.group_chat.group,
            "messages": [_gmsg_to_dict(m) for m in state.group_chat.messages],
            "has_older": state.group_chat.has_older,
        }
    return {
        "groups": [_group_to_dict(g) for g in state.groups],
        "invites": [_invite_to_dict(i) for i in state.invites],
        "group_chat": group_chat_data,
        "profile": {
            "address": state.profile.address,
            "name": state.profile.name,
            "status_message": state.profile.status_message,
            "status": int(state.profile.status),
            "connection": int(state.profile.connection),
            "avatar": _pic_to_dict(state.profile.avatar),
        },
        "friends": [
            {
                "key": f.key,
                "name": f.name,
                "status_message": f.status_message,
                "status": int(f.status),
                "connection": int(f.connection),
                "typing": f.typing,
                "unread": f.unread,
                "last": _msg_to_dict(f.last) if f.last is not None else None,
                "avatar": _pic_to_dict(f.avatar),
                "hide_after_zero": f.hide_after_zero,
            } for f in state.friends
        ],
        "requests": [
            {
                "key": r.key,
                "message": r.message,
                "time": r.time,
            } for r in state.requests
        ],
        "settings": {
            "udp": state.settings.udp,
            "ipv6": state.settings.ipv6,
            "local_discovery": state.settings.local_discovery,
            "stay_connected": state.settings.stay_connected,
            "theme": state.settings.theme,
        },
        "chat": chat_data,
        "progress": {str(k): v for k, v in state.progress.items()},
        "call": _call_to_dict(state.call),
    }


def state_from_dict(data: dict[str, Any]) -> ClientState:
    """Deserialize a :class:`ClientState` produced by :func:`state_to_dict`."""
    p = data["profile"]
    profile = Profile(
        address=str(p["address"]),
        name=str(p["name"]),
        status_message=str(p["status_message"]),
        status=core.UserStatus(int(p["status"])),
        connection=core.Connection(int(p["connection"])),
        avatar=_pic_from_dict(p.get("avatar")),
    )
    friends = tuple(
        Friend(
            key=str(f["key"]),
            name=str(f["name"]),
            status_message=str(f["status_message"]),
            status=core.UserStatus(int(f["status"])),
            connection=core.Connection(int(f["connection"])),
            typing=bool(f["typing"]),
            unread=int(f["unread"]),
            last=(_msg_from_dict(f["last"])
                  if f.get("last") is not None else None),
            avatar=_pic_from_dict(f.get("avatar")),
            hide_after_zero=bool(f["hide_after_zero"]),
        ) for f in data["friends"]
    )
    requests = tuple(
        FriendRequest(
            key=str(r["key"]),
            message=str(r["message"]),
            time=int(r["time"]),
        ) for r in data["requests"]
    )
    s = data["settings"]
    theme = str(s.get("theme", "system"))
    if theme not in _VALID_THEMES:
        theme = "system"
    settings = Settings(
        udp=bool(s["udp"]),
        ipv6=bool(s["ipv6"]),
        local_discovery=bool(s["local_discovery"]),
        stay_connected=bool(s["stay_connected"]),
        theme=theme,
    )
    c = data.get("chat")
    chat: Optional[Chat] = None
    if c is not None:
        chat = Chat(
            friend=str(c["friend"]),
            messages=tuple(_msg_from_dict(m) for m in c["messages"]),
            has_older=bool(c["has_older"]),
        )
    progress = {int(k): int(v) for k, v in data.get("progress", {}).items()}
    gc = data.get("group_chat")
    group_chat: Optional[GroupChat] = None
    if gc is not None:
        group_chat = GroupChat(
            group=str(gc["group"]),
            messages=tuple(_gmsg_from_dict(m) for m in gc["messages"]),
            has_older=bool(gc["has_older"]),
        )
    return ClientState(
        profile=profile,
        friends=friends,
        requests=requests,
        settings=settings,
        chat=chat,
        progress=progress,
        groups=tuple(_group_from_dict(g) for g in data.get("groups", [])),
        invites=tuple(_invite_from_dict(i) for i in data.get("invites", [])),
        group_chat=group_chat,
        call=_call_from_dict(data.get("call")),
    )


def _send_frame(conn: socket.socket, payload: dict[str, Any]) -> None:
    line = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
    conn.sendall(line)


class _AutoUnlinkIO(io.BufferedReader):
    """Readable binary file stream that deletes a staged file on close."""

    def __init__(self, path: Path, unlink: bool) -> None:
        super().__init__(io.FileIO(path, "rb"))
        self._path = path
        self._unlink = unlink

    def close(self) -> None:
        try:
            super().close()
        finally:
            if self._unlink:
                self._path.unlink(missing_ok=True)


def stage_picked_file(directory: Path, picked: PickedFile) -> Path:
    """Copy ``picked`` into a unique file inside ``directory / 'staging'``."""
    staging = directory / "staging"
    staging.mkdir(mode=0o700, parents=True, exist_ok=True)
    staged = staging / f"{os.getpid()}-{secrets.token_hex(12)}.bin"
    try:
        with picked.open_stream() as src, staged.open("wb") as out:
            while True:
                buf = src.read(65536)
                if not buf:
                    break
                out.write(buf)
    except BaseException:
        staged.unlink(missing_ok=True)
        raise
    return staged


def staged_picked_file(staged: Path, name: str) -> PickedFile:
    """Wrap an already-staged file so it unlinks itself once read and closed."""

    def _open(p: Path = staged) -> io.BufferedReader:
        return _AutoUnlinkIO(p, True)

    return PickedFile(name=name, open_stream=_open)


class _ConnWriter:
    """Non-blocking per-connection writer that never stalls the Tox thread.

    RPC replies are queued FIFO (bounded); state snapshots coalesce so a slow
    or backgrounded UI always receives the latest state without blocking.
    """

    def __init__(self, conn: socket.socket,
                 on_dead: Callable[[socket.socket], None]) -> None:
        self._conn = conn
        self._on_dead = on_dead
        self._cond = threading.Condition()
        self._replies: deque[bytes] = deque()
        self._latest_state: Optional[bytes] = None
        self._closed = False
        self._thread = threading.Thread(
            target=self._run, name="pytox-ipc-wr", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def send_state(self, raw: bytes) -> None:
        with self._cond:
            if self._closed:
                return
            self._latest_state = raw
            self._cond.notify()

    def send_reply(self, raw: bytes) -> None:
        with self._cond:
            if self._closed:
                return
            if len(self._replies) >= _MAX_WRITER_REPLIES:
                self._replies.popleft()
            self._replies.append(raw)
            self._cond.notify()

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify_all()
        try:
            self._conn.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self._conn.close()
        except OSError:
            pass

    def _run(self) -> None:
        while True:
            with self._cond:
                while (not self._closed and not self._replies
                       and self._latest_state is None):
                    self._cond.wait()
                if self._closed:
                    return
                frame: Optional[bytes]
                if self._replies:
                    frame = self._replies.popleft()
                else:
                    frame = self._latest_state
                    self._latest_state = None
            if frame is None:
                continue
            try:
                self._conn.sendall(frame)
            except OSError:
                with self._cond:
                    self._closed = True
                self._on_dead(self._conn)
                return


class ServiceServer:
    """Exposes a :class:`ToxClient` over a private ``AF_UNIX`` stream socket."""

    def __init__(self, client: ToxClient, socket_path: Path) -> None:
        self._client = client
        self._path = socket_path
        self._sock: Optional[socket.socket] = None
        self._clients_lock = threading.Lock()
        self._conns: dict[socket.socket, _ConnWriter] = {}
        self._running = False
        self._unsub: Optional[Callable[[], None]] = None

    def start(self) -> None:
        self._path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._path.unlink(missing_ok=True)
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            srv.bind(str(self._path))
            os.chmod(self._path, 0o600)
            srv.listen(4)
        except BaseException:
            srv.close()
            raise
        self._sock = srv
        self._running = True
        self._unsub = self._client.subscribe(self._broadcast, emit_current=False)
        threading.Thread(
            target=self._accept_loop, name="pytox-ipc-srv", daemon=True
        ).start()

    def stop(self) -> None:
        self._running = False
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        srv, self._sock = self._sock, None
        if srv is not None:
            try:
                srv.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                srv.close()
            except OSError:
                pass
        with self._clients_lock:
            writers = list(self._conns.values())
            self._conns.clear()
        for writer in writers:
            writer.close()
        self._path.unlink(missing_ok=True)

    def _drop_conn(self, conn: socket.socket) -> None:
        with self._clients_lock:
            writer = self._conns.pop(conn, None)
        if writer is not None:
            writer.close()

    def _reply(self, conn: socket.socket, payload: dict[str, Any]) -> None:
        raw = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
        with self._clients_lock:
            writer = self._conns.get(conn)
        if writer is not None:
            writer.send_reply(raw)

    def _broadcast(self, state: ClientState) -> None:
        msg = {"type": "state", "state": state_to_dict(state)}
        raw = (json.dumps(msg, separators=(",", ":")) + "\n").encode("utf-8")
        with self._clients_lock:
            writers = list(self._conns.values())
        for writer in writers:
            writer.send_state(raw)

    def _accept_loop(self) -> None:
        srv = self._sock
        if srv is None:
            return
        while self._running:
            try:
                conn, _ = srv.accept()
            except OSError:
                break
            writer = _ConnWriter(conn, self._drop_conn)
            with self._clients_lock:
                if not self._running:
                    conn.close()
                    break
                # Capture and queue the initial state while holding _clients_lock
                # so no subsequent _broadcast() can overtake it.
                init_raw = (json.dumps(
                    {"type": "state",
                     "state": state_to_dict(self._client.state)},
                    separators=(",", ":"),
                ) + "\n").encode("utf-8")
                writer.send_state(init_raw)
                self._conns[conn] = writer
            writer.start()
            threading.Thread(
                target=self._reader_loop,
                args=(conn, ),
                name="pytox-ipc-conn",
                daemon=True,
            ).start()

    def _reader_loop(self, conn: socket.socket) -> None:
        try:
            with conn.makefile("rb") as reader:
                while self._running:
                    line = _read_line_bounded(reader)
                    if line is None:
                        break
                    line = line.strip()
                    if line:
                        self._handle_line(conn, line)
        except (OSError, ValueError, UnicodeDecodeError):
            pass
        finally:
            with self._clients_lock:
                writer = self._conns.pop(conn, None)
                last = not self._conns
            if writer is not None:
                writer.close()
            else:
                try:
                    conn.close()
                except OSError:
                    pass
            if last and self._running:
                # A UI that died while showing a chat never says it's gone.
                self._client.set_visible(False)

    def _handle_line(self, conn: socket.socket, line: str) -> None:
        """Run one request: a bad one fails alone, not the whole connection."""
        req_id: Any = None
        cmd_name: Any = None
        try:
            req = json.loads(line)
            if not isinstance(req, dict):
                raise ValueError("IPC request must be a JSON object")
            req_id = req.get("id")
            cmd_name = req.get("cmd")
            self._handle(conn, req)
        except Exception as exc:  # noqa: BLE001
            # Do not log raw payload so passwords / avatar blobs aren't logged.
            _LOG.exception("IPC request failed (cmd=%r)", cmd_name)
            if req_id is not None:
                self._reply_error(conn, req_id, exc)

    def _reply_error(
        self,
        conn: socket.socket,
        req_id: Any,
        exc: BaseException,
    ) -> None:
        self._reply(conn, {"type": "reply", "id": req_id, "error": repr(exc)})

    def _reply_later(
        self,
        conn: socket.socket,
        req_id: Any,
        fut: Future[Any],
    ) -> None:
        """Answer when the Tox thread has done it, without holding up reads."""

        def _done(f: Future[Any]) -> None:
            try:
                value = f.result()
            except Exception as exc:  # noqa: BLE001
                self._reply_error(conn, req_id, exc)
                return
            self._reply(conn, {"type": "reply", "id": req_id, "value": value})

        fut.add_done_callback(_done)

    def _handle(self, conn: socket.socket, req: dict[str, Any]) -> None:
        cmd = str(req["cmd"])
        req_id = req.get("id")
        if cmd == "send":
            self._client.send(
                str(req["friend"]), str(req["text"]), bool(req["action"]))
        elif cmd == "add_friend":
            self._reply_later(
                conn, req_id,
                self._client.add_friend(
                    str(req["tox_id"]), str(req["message"])))
        elif cmd == "accept":
            r = req["request"]
            self._client.accept(
                FriendRequest(
                    key=str(r["key"]),
                    message=str(r["message"]),
                    time=int(r["time"]),
                ))
        elif cmd == "decline":
            r = req["request"]
            self._client.decline(
                FriendRequest(
                    key=str(r["key"]),
                    message=str(r["message"]),
                    time=int(r["time"]),
                ))
        elif cmd == "delete":
            self._client.delete(str(req["friend"]))
        elif cmd == "delete_profile":
            self._client.delete_profile()
        elif cmd == "set_name":
            self._client.set_name(str(req["name"]))
        elif cmd == "set_status_message":
            self._client.set_status_message(str(req["message"]))
        elif cmd == "set_status":
            self._client.set_status(core.UserStatus(int(req["status"])))
        elif cmd == "open_chat":
            friend = req.get("friend")
            self._client.open_chat(str(friend) if friend is not None else None)
        elif cmd == "load_older":
            self._client.load_older()
        elif cmd == "set_visible":
            self._client.set_visible(bool(req["visible"]))
        elif cmd == "set_typing":
            self._client.set_typing(str(req["friend"]), bool(req["typing"]))
        elif cmd == "set_hide_after_zero":
            self._client.set_hide_after_zero(
                str(req["friend"]), bool(req["hide"]))
        elif cmd == "update_settings":
            s = req["settings"]
            theme = str(s.get("theme", "system"))
            if theme not in _VALID_THEMES:
                raise ValueError(f"invalid theme: {theme!r}")
            self._client.update_settings(
                Settings(
                    udp=bool(s["udp"]),
                    ipv6=bool(s["ipv6"]),
                    local_discovery=bool(s["local_discovery"]),
                    stay_connected=bool(s["stay_connected"]),
                    theme=theme,
                ))
        elif cmd == "send_file_path":
            staging_root = (self._client.directory / "staging").resolve()
            staged = Path(str(req["path"])).resolve()
            if not staged.is_relative_to(staging_root) or staged == staging_root:
                raise ValueError("staged path must reside inside staging directory")
            unlink_after = bool(req.get("unlink", False))

            def _open_staged(
                p: Path = staged, u: bool = unlink_after
            ) -> io.BufferedReader:
                return _AutoUnlinkIO(p, u)

            self._client.send_file(
                str(req["friend"]),
                PickedFile(
                    name=str(req["name"]),
                    open_stream=_open_staged,
                ),
            )
        elif cmd == "accept_file":
            self._client.accept_file(int(req["message_id"]))
        elif cmd == "cancel_file":
            self._client.cancel_file(int(req["message_id"]))
        elif cmd == "set_avatar":
            raw_b64 = req.get("image")
            data = (base64.b64decode(raw_b64)
                    if raw_b64 is not None else None)
            self._reply_later(conn, req_id, self._client.set_avatar(data))
        elif cmd == "create_group":
            self._reply_later(
                conn, req_id,
                self._client.create_group(
                    str(req["name"]), bool(req["private"])))
        elif cmd == "join_group":
            self._reply_later(
                conn, req_id,
                self._client.join_group(
                    str(req["chat_id"]), str(req["password"])))
        elif cmd == "accept_invite":
            self._client.accept_invite(_invite_from_dict(req["invite"]))
        elif cmd == "decline_invite":
            self._client.decline_invite(_invite_from_dict(req["invite"]))
        elif cmd == "invite_friend":
            self._client.invite_friend(str(req["group"]), str(req["friend"]))
        elif cmd == "leave_group":
            self._client.leave_group(str(req["group"]))
        elif cmd == "send_group_message":
            self._client.send_group_message(
                str(req["group"]), str(req["text"]), bool(req["action"]))
        elif cmd == "set_topic":
            self._client.set_topic(str(req["group"]), str(req["topic"]))
        elif cmd == "set_group_privacy":
            self._client.set_group_privacy(
                str(req["group"]), bool(req["private"]))
        elif cmd == "set_group_password":
            self._client.set_group_password(
                str(req["group"]), str(req["password"]))
        elif cmd == "set_peer_limit":
            self._client.set_peer_limit(str(req["group"]), int(req["limit"]))
        elif cmd == "set_topic_lock":
            self._client.set_topic_lock(str(req["group"]), bool(req["locked"]))
        elif cmd == "set_role":
            self._client.set_role(
                str(req["group"]), str(req["peer"]),
                core.GroupRole(int(req["role"])))
        elif cmd == "kick":
            self._client.kick(str(req["group"]), str(req["peer"]))
        elif cmd == "open_group":
            group = req.get("group")
            self._client.open_group(str(group) if group is not None else None)
        elif cmd == "load_older_group_messages":
            self._client.load_older_group_messages()
        elif cmd == "call":
            self._client.call(str(req["friend"]), bool(req["video"]))
        elif cmd == "answer":
            self._client.answer(bool(req["video"]))
        elif cmd == "hang_up":
            self._client.hang_up()
        elif cmd == "set_muted":
            self._client.set_muted(bool(req["muted"]))
        elif cmd == "set_video":
            self._client.set_video(bool(req["on"]))
        elif cmd == "switch_camera":
            self._client.switch_camera()
        elif cmd == "set_speaker":
            self._client.set_speaker(bool(req["on"]))
        else:
            raise ValueError(f"unknown IPC command: {cmd!r}")


def _encode_picture(who: str, frame: Optional[VideoFrame]) -> bytes:
    if frame is None:
        return _PICTURE.pack(_WHO.index(who), 0, 0, 0, 0, 0, 0, 0, 0, 0)
    flags = _SHOWN | (_MIRRORED if frame.mirrored else 0)
    return b"".join((
        _PICTURE.pack(_WHO.index(who), flags, frame.width, frame.height,
                      frame.y_stride, frame.u_stride, frame.v_stride,
                      len(frame.y), len(frame.u), len(frame.v)),
        frame.y,
        frame.u,
        frame.v,
    ))


def _read_picture(
        reader: io.BufferedReader) -> Optional[tuple[str, Optional[VideoFrame]]]:
    """The next picture, or None at the end."""
    header = _read_exact(reader, _PICTURE.size)
    if header is None:
        return None
    (who, flags, width, height, y_stride, u_stride, v_stride, y_len, u_len,
     v_len) = _PICTURE.unpack(header)
    if who >= len(_WHO):
        raise ValueError(f"invalid video source index: {who}")
    total = y_len + u_len + v_len
    if total > _MAX_VIDEO_BYTES:
        raise ValueError(f"video frame exceeds max size: {total}")
    planes = _read_exact(reader, total)
    if planes is None:
        return None
    if not flags & _SHOWN:
        return _WHO[who], None
    cw = (width + 1) // 2
    ch = (height + 1) // 2
    if (width == 0 or height == 0
            or y_stride < width or u_stride < cw or v_stride < cw
            or y_len < y_stride * height
            or u_len < u_stride * ch or v_len < v_stride * ch):
        raise ValueError("invalid video frame dimensions/planes")
    return _WHO[who], VideoFrame(width, height, planes[:y_len],
                                 planes[y_len:y_len + u_len],
                                 planes[y_len + u_len:], y_stride, u_stride,
                                 v_stride, bool(flags & _MIRRORED))


class _PictureSender:
    """Sends one UI the call's pictures: the newest of each, as it can."""

    def __init__(self, conn: socket.socket) -> None:
        self._conn = conn
        self._cond = threading.Condition()
        self._waiting: dict[str, Optional[VideoFrame]] = {}
        self._open = True

    def offer(self, who: str, frame: Optional[VideoFrame]) -> None:
        with self._cond:
            self._waiting[who] = frame
            self._cond.notify()

    def close(self) -> None:
        with self._cond:
            self._open = False
            self._cond.notify()
        try:
            self._conn.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self._conn.close()

    def wait_for_end(self) -> None:
        try:
            while self._conn.recv(1):
                pass
        except OSError:
            pass
        with self._cond:
            self._open = False
            self._cond.notify()

    def run(self) -> None:
        while True:
            with self._cond:
                while self._open and not self._waiting:
                    self._cond.wait()
                if not self._open:
                    return
                waiting, self._waiting = self._waiting, {}
            try:
                for who, frame in waiting.items():
                    self._conn.sendall(_encode_picture(who, frame))
            except OSError:
                return


class VideoServer:
    """Sends the call's pictures to the UIs on :data:`VIDEO_SOCKET_NAME`."""

    def __init__(self, client: ToxClient, socket_path: Path) -> None:
        self._client = client
        self._path = socket_path
        self._sock: Optional[socket.socket] = None
        self._running = False
        self._lock = threading.Lock()
        self._senders: list[_PictureSender] = []

    def start(self) -> None:
        self._path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._path.unlink(missing_ok=True)
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            srv.bind(str(self._path))
            os.chmod(self._path, 0o600)
            srv.listen(4)
        except BaseException:
            srv.close()
            raise
        self._sock = srv
        self._running = True
        threading.Thread(target=self._accept_loop,
                         name="pytox-video-srv",
                         daemon=True).start()

    def stop(self) -> None:
        self._running = False
        srv, self._sock = self._sock, None
        if srv is not None:
            try:
                srv.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                srv.close()
            except OSError:
                pass
        with self._lock:
            senders, self._senders = self._senders, []
        for sender in senders:
            sender.close()
        self._path.unlink(missing_ok=True)

    def _accept_loop(self) -> None:
        srv = self._sock
        if srv is None:
            return
        while self._running:
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            sender = _PictureSender(conn)
            with self._lock:
                if not self._running:
                    sender.close()
                    return
                self._senders.append(sender)
            threading.Thread(target=self._serve,
                             args=(sender, ),
                             name="pytox-video-conn",
                             daemon=True).start()

    def _serve(self, sender: _PictureSender) -> None:
        unwatch = self._client.watch_video(sender.offer)
        # UIs send nothing here: reading ends when the UI goes, even while
        # there are no pictures to send.
        threading.Thread(target=sender.wait_for_end,
                         name="pytox-video-end",
                         daemon=True).start()
        try:
            sender.run()
        finally:
            unwatch()
            sender.close()
            with self._lock:
                if sender in self._senders:
                    self._senders.remove(sender)


def serve(client: ToxClient, socket_path: Path, stop: threading.Event) -> None:
    """Run ``client`` for UIs until staying connected is off, ``stop``, or
    the profile is deleted.

    UIs can connect once the profile is open, so the first state they get is
    the profile's. Tox is closed before the socket: when a UI sees the
    connection end, the profile is free for it to open.
    """

    def _watch(state: ClientState) -> None:
        if not state.settings.stay_connected:
            stop.set()

    unsubscribe = client.subscribe(_watch, emit_current=False)
    client.set_on_closed(stop.set)
    server = ServiceServer(client, socket_path)
    video = VideoServer(client, socket_path.parent / VIDEO_SOCKET_NAME)
    server_started = False
    video_started = False
    client.start()
    try:
        client.wait_for(lambda s: bool(s.profile.address), timeout=60.0)
        video.start()
        video_started = True
        server.start()
        server_started = True
        stop.wait()
    finally:
        unsubscribe()
        client.close()
        if server_started:
            server.stop()
        if video_started:
            video.stop()


class RemoteClient:
    """UI-side proxy matching :class:`ToxClient`'s public API over IPC."""

    def __init__(
        self,
        directory: Path,
        socket_path: Path,
        on_closed: Optional[Callable[[], None]] = None,
    ) -> None:
        self._dir = directory
        self._path = socket_path
        self._on_closed = on_closed
        self._sock: Optional[socket.socket] = None
        self._reader: Optional[io.BufferedReader] = None
        self._send_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._state = ClientState()
        self._listeners: list[Callable[[ClientState], None]] = []
        self._pending: dict[int, Future[Any]] = {}
        self._next_id = 1
        self._running = False
        self._video_lock = threading.Lock()
        self._video_sock: Optional[socket.socket] = None
        self._video_listeners: list[VideoListener] = []

    def connect(self, timeout: float = 2.0) -> bool:
        """Connect, then wait for the service's state to fill ``state``."""
        if not self._path.exists():
            return False
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        reader: Optional[io.BufferedReader] = None
        try:
            sock.connect(str(self._path))
            reader = sock.makefile("rb")
            line = _read_line_bounded(reader)
            if line is None:
                raise OSError("service closed before sending initial state")
            first = json.loads(line)
            if not isinstance(first, dict) or first.get("type") != "state":
                raise OSError("the service didn't send its state first")
            self._state = state_from_dict(first["state"])
        except (OSError, ValueError, KeyError, TypeError, UnicodeDecodeError):
            if reader is not None:
                reader.close()
            sock.close()
            return False
        sock.settimeout(None)
        self._sock = sock
        self._reader = reader
        self._running = True
        threading.Thread(
            target=self._reader_loop, name="pytox-ipc-cli", daemon=True
        ).start()
        return True

    @property
    def connected(self) -> bool:
        return self._running

    @property
    def state(self) -> ClientState:
        with self._state_lock:
            return self._state

    def subscribe(
        self,
        listener: Callable[[ClientState], None],
        emit_current: bool = True,
    ) -> Callable[[], None]:
        with self._state_lock:
            self._listeners.append(listener)
            cur = self._state
        if emit_current:
            listener(cur)

        def unsub() -> None:
            with self._state_lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return unsub

    def close(self) -> None:
        self._fail_pending()
        with self._video_lock:
            video, self._video_sock = self._video_sock, None
        for sock in (self._sock, video):
            if sock is None:
                continue
            try:
                # Wakes the reader thread.
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()

    def watch_video(self, listener: VideoListener) -> Callable[[], None]:
        """The call's pictures, from the service's picture socket."""
        with self._video_lock:
            self._video_listeners.append(listener)
            if self._video_sock is None and self._running:
                self._open_video()

        def unwatch() -> None:
            with self._video_lock:
                if listener in self._video_listeners:
                    self._video_listeners.remove(listener)

        return unwatch

    def _open_video(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(str(self._path.parent / VIDEO_SOCKET_NAME))
        except OSError:
            sock.close()
            return
        self._video_sock = sock
        threading.Thread(target=self._video_loop,
                         args=(sock, ),
                         name="pytox-video-cli",
                         daemon=True).start()

    def _video_loop(self, sock: socket.socket) -> None:
        try:
            with sock.makefile("rb") as reader:
                while True:
                    picture = _read_picture(reader)
                    if picture is None:
                        break
                    with self._video_lock:
                        listeners = list(self._video_listeners)
                    for listener in listeners:
                        listener(*picture)
        except (OSError, ValueError):
            pass
        finally:
            try:
                sock.close()
            except OSError:
                pass
            with self._video_lock:
                if self._video_sock is sock:
                    self._video_sock = None
                listeners = list(self._video_listeners)
            # The pictures stop with the service.
            for listener in listeners:
                for who in _WHO:
                    listener(who, None)

    def _fail_pending(self) -> None:
        # Under the lock with _rpc's check, so no call waits after this.
        with self._state_lock:
            self._running = False
            pending = list(self._pending.values())
            self._pending.clear()
        for fut in pending:
            if not fut.done():
                fut.set_exception(ConnectionError("The service has gone."))

    def _emit(self, payload: dict[str, Any]) -> bool:
        sock = self._sock
        if sock is None:
            return False
        with self._send_lock:
            try:
                _send_frame(sock, payload)
                return True
            except OSError:
                return False

    def _rpc(self, payload: dict[str, Any]) -> Future[Any]:
        fut: Future[Any] = Future()
        with self._state_lock:
            if not self._running:
                fut.set_exception(ConnectionError("The service has gone."))
                return fut
            req_id = self._next_id
            self._next_id += 1
            self._pending[req_id] = fut
        payload["id"] = req_id
        if not self._emit(payload):
            with self._state_lock:
                self._pending.pop(req_id, None)
            if not fut.done():
                fut.set_exception(ConnectionError("The service has gone."))
        return fut

    def _reader_loop(self) -> None:
        assert self._reader is not None
        try:
            with self._reader as reader:
                while self._running:
                    line = _read_line_bounded(reader)
                    if line is None:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    msg = json.loads(line)
                    if not isinstance(msg, dict):
                        continue
                    if msg.get("type") == "state":
                        snap = state_from_dict(msg["state"])
                        with self._state_lock:
                            self._state = snap
                            listeners = list(self._listeners)
                        for fn in listeners:
                            try:
                                fn(snap)
                            except Exception:  # noqa: BLE001
                                _LOG.exception("remote state listener failed")
                    elif msg.get("type") == "reply":
                        req_id = int(msg["id"])
                        with self._state_lock:
                            fut = self._pending.pop(req_id, None)
                        if fut is None or fut.done():
                            continue
                        if "error" in msg:
                            fut.set_exception(RuntimeError(str(msg["error"])))
                        else:
                            fut.set_result(msg.get("value"))
        except (OSError, ValueError, KeyError, TypeError, UnicodeDecodeError):
            pass
        finally:
            self._fail_pending()
            sock, self._sock = self._sock, None
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
            if self._on_closed is not None:
                self._on_closed()

    def send(self, friend_key: str, text: str, action: bool = False) -> None:
        self._emit({
            "cmd": "send",
            "friend": friend_key,
            "text": text,
            "action": action,
        })

    def add_friend(
        self,
        tox_id: str,
        message: str = "",
    ) -> Future[Optional[str]]:
        return self._rpc({
            "cmd": "add_friend",
            "tox_id": tox_id,
            "message": message,
        })

    def accept(self, request: FriendRequest) -> None:
        self._emit({
            "cmd": "accept",
            "request": {
                "key": request.key,
                "message": request.message,
                "time": request.time,
            },
        })

    def decline(self, request: FriendRequest) -> None:
        self._emit({
            "cmd": "decline",
            "request": {
                "key": request.key,
                "message": request.message,
                "time": request.time,
            },
        })

    def delete(self, friend_key: str) -> None:
        self._emit({"cmd": "delete", "friend": friend_key})

    def delete_profile(self) -> None:
        """The service closes the profile and deletes it."""
        self._emit({"cmd": "delete_profile"})

    def set_name(self, name: str) -> None:
        self._emit({"cmd": "set_name", "name": name})

    def set_status_message(self, message: str) -> None:
        self._emit({"cmd": "set_status_message", "message": message})

    def set_status(self, status: core.UserStatus) -> None:
        self._emit({"cmd": "set_status", "status": int(status)})

    def open_chat(self, friend_key: Optional[str]) -> None:
        self._emit({"cmd": "open_chat", "friend": friend_key})

    def load_older(self) -> None:
        self._emit({"cmd": "load_older"})

    def set_visible(self, visible: bool) -> None:
        self._emit({"cmd": "set_visible", "visible": visible})

    def set_typing(self, friend_key: str, typing: bool) -> None:
        self._emit({
            "cmd": "set_typing",
            "friend": friend_key,
            "typing": typing,
        })

    def set_hide_after_zero(self, friend_key: str, hide: bool) -> None:
        self._emit({
            "cmd": "set_hide_after_zero",
            "friend": friend_key,
            "hide": hide,
        })

    def update_settings(self, settings: Settings) -> None:
        self._emit({
            "cmd": "update_settings",
            "settings": {
                "udp": settings.udp,
                "ipv6": settings.ipv6,
                "local_discovery": settings.local_discovery,
                "stay_connected": settings.stay_connected,
                "theme": settings.theme,
            },
        })

    def send_staged_file(
        self,
        friend_key: str,
        staged: Path,
        name: str,
    ) -> bool:
        """Send an already-staged file under ``staging/``. Keeps file on False."""
        return self._emit({
            "cmd": "send_file_path",
            "friend": friend_key,
            "path": str(staged),
            "name": name,
            "unlink": True,
        })

    def send_file(self, friend_key: str, picked: PickedFile) -> None:
        # Stage picked bytes into profile cache so the service process can read them.
        staged = stage_picked_file(self._dir, picked)
        if not self.send_staged_file(friend_key, staged, picked.name):
            staged.unlink(missing_ok=True)

    def accept_file(self, message_id: int) -> None:
        self._emit({"cmd": "accept_file", "message_id": message_id})

    def cancel_file(self, message_id: int) -> None:
        self._emit({"cmd": "cancel_file", "message_id": message_id})

    def set_avatar(self, image: Optional[bytes]) -> Future[bool]:
        encoded = (base64.b64encode(image).decode("ascii")
                   if image is not None else None)
        return self._rpc({"cmd": "set_avatar", "image": encoded})

    def create_group(self, name: str, private: bool) -> Future[Optional[str]]:
        return self._rpc({
            "cmd": "create_group", "name": name, "private": private})

    def join_group(self, chat_id: str, password: str) -> Future[Optional[str]]:
        return self._rpc({
            "cmd": "join_group", "chat_id": chat_id, "password": password})

    def accept_invite(self, invite: GroupInvite) -> None:
        self._emit({"cmd": "accept_invite", "invite": _invite_to_dict(invite)})

    def decline_invite(self, invite: GroupInvite) -> None:
        self._emit({"cmd": "decline_invite", "invite": _invite_to_dict(invite)})

    def invite_friend(self, group_id: str, friend_key: str) -> None:
        self._emit({
            "cmd": "invite_friend", "group": group_id, "friend": friend_key})

    def leave_group(self, group_id: str) -> None:
        self._emit({"cmd": "leave_group", "group": group_id})

    def send_group_message(
        self,
        group_id: str,
        text: str,
        action: bool = False,
    ) -> None:
        self._emit({
            "cmd": "send_group_message",
            "group": group_id,
            "text": text,
            "action": action,
        })

    def set_topic(self, group_id: str, topic: str) -> None:
        self._emit({"cmd": "set_topic", "group": group_id, "topic": topic})

    def set_group_privacy(self, group_id: str, private: bool) -> None:
        self._emit({
            "cmd": "set_group_privacy", "group": group_id, "private": private})

    def set_group_password(self, group_id: str, password: str) -> None:
        self._emit({
            "cmd": "set_group_password",
            "group": group_id,
            "password": password,
        })

    def set_peer_limit(self, group_id: str, limit: int) -> None:
        self._emit({"cmd": "set_peer_limit", "group": group_id, "limit": limit})

    def set_topic_lock(self, group_id: str, locked: bool) -> None:
        self._emit({
            "cmd": "set_topic_lock", "group": group_id, "locked": locked})

    def set_role(
        self,
        group_id: str,
        peer_key: str,
        role: core.GroupRole,
    ) -> None:
        self._emit({
            "cmd": "set_role",
            "group": group_id,
            "peer": peer_key,
            "role": int(role),
        })

    def kick(self, group_id: str, peer_key: str) -> None:
        self._emit({"cmd": "kick", "group": group_id, "peer": peer_key})

    def open_group(self, group_id: Optional[str]) -> None:
        self._emit({"cmd": "open_group", "group": group_id})

    def load_older_group_messages(self) -> None:
        self._emit({"cmd": "load_older_group_messages"})

    def call(self, friend_key: str, video: bool) -> None:
        self._emit({"cmd": "call", "friend": friend_key, "video": video})

    def answer(self, video: bool) -> None:
        self._emit({"cmd": "answer", "video": video})

    def hang_up(self) -> None:
        self._emit({"cmd": "hang_up"})

    def set_muted(self, muted: bool) -> None:
        self._emit({"cmd": "set_muted", "muted": muted})

    def set_video(self, on: bool) -> None:
        self._emit({"cmd": "set_video", "on": on})

    def switch_camera(self) -> None:
        self._emit({"cmd": "switch_camera"})

    def set_speaker(self, on: bool) -> None:
        self._emit({"cmd": "set_speaker", "on": on})
