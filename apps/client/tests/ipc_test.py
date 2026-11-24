# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""Tests for Unix-socket IPC serialization and ServiceServer/RemoteClient."""
from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

import pytox.toxcore.tox as core

from pytox_client.calls import FRIEND
from pytox_client.calls import SELF
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
from pytox_client.model import Picture
from pytox_client.model import Profile
from pytox_client.model import Settings
from pytox_client.platform_base import NoopPlatform
from pytox_client.service_ipc import RemoteClient
from pytox_client.service_ipc import SOCKET_NAME
from pytox_client.service_ipc import ServiceServer
from pytox_client.service_ipc import state_from_dict
from pytox_client.service_ipc import state_to_dict
from pytox_client.service_ipc import VIDEO_SOCKET_NAME
from pytox_client.service_ipc import VideoServer
from pytox_client.service_ipc import serve


class IpcTest(unittest.TestCase):

    def test_state_round_trip(self) -> None:
        ft = FileTransfer(
            name="doc.pdf",
            size=1024,
            state=FileState.ACTIVE,
            done=512,
            path=Path("/tmp/doc.pdf"),
        )
        msg = Message(
            id=7,
            friend="AA" * 32,
            outgoing=True,
            action=False,
            text="",
            time=123456789,
            delivered=False,
            file=ft,
        )
        gmsg = GroupMessage(
            id=11, group="CC" * 32, peer_key="EE" * 32, peer_name="Bob",
            outgoing=False, action=True, private=True, text="waves",
            time=42, sent=True)
        state = ClientState(
            profile=Profile(
                address="01" * 38,
                name="Alice",
                status_message="Ready",
                status=core.UserStatus.AWAY,
                connection=core.Connection.UDP,
                avatar=Picture(path=Path("/tmp/a.png"), hash="CAFE"),
            ),
            friends=(
                Friend(
                    key="AA" * 32,
                    name="Bob",
                    status_message="hi",
                    status=core.UserStatus.BUSY,
                    connection=core.Connection.TCP,
                    typing=True,
                    unread=2,
                    last=msg,
                    avatar=Picture(path=Path("/tmp/b.png"), hash="BEEF"),
                    hide_after_zero=True,
                ),
            ),
            requests=(FriendRequest(key="BB" * 32, message="add me", time=99),),
            settings=Settings(
                udp=False,
                ipv6=True,
                local_discovery=False,
                stay_connected=True,
                theme="dark",
            ),
            chat=Chat(friend="AA" * 32, messages=(msg,), has_older=True),
            progress={7: 512},
            groups=(
                Group(
                    id="CC" * 32,
                    name="Team",
                    topic="Release",
                    privacy=core.GroupPrivacyState.PRIVATE,
                    connected=True,
                    peers=(
                        Peer(key="DD" * 32, name="Me",
                             role=core.GroupRole.FOUNDER,
                             status=core.UserStatus.NONE, is_self=True),
                        Peer(key="EE" * 32, name="Bob",
                             role=core.GroupRole.OBSERVER,
                             status=core.UserStatus.AWAY, is_self=False),
                    ),
                    self_role=core.GroupRole.FOUNDER,
                    password="pw",
                    peer_limit=100,
                    topic_locked=True,
                    unread=3,
                    last=gmsg,
                    problem=None,
                ),
            ),
            invites=(GroupInvite(friend="AA" * 32, name="Open",
                                 data="0A0B", time=5),),
            group_chat=GroupChat(group="CC" * 32, messages=(gmsg,),
                                 has_older=False),
        )
        restored = state_from_dict(state_to_dict(state))
        self.assertEqual(restored, state)

    def test_call_round_trip(self) -> None:
        note = Message(id=8, friend="AA" * 32, outgoing=False, action=False,
                       text="", time=5, delivered=True,
                       call=CallNote(True, CallOutcome.MISSED, 0))
        state = ClientState(
            chat=Chat(friend="AA" * 32, messages=(note, ), has_older=False),
            call=Call(friend="AA" * 32, outgoing=True, video_call=True,
                      answered=True, started=99, friend_video=True,
                      muted=True, video=True, front_camera=False,
                      speaker=True, problem="no camera"))
        self.assertEqual(state_from_dict(state_to_dict(state)), state)

    def test_server_and_remote_client(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            client = ToxClient(
                root,
                NoopPlatform(),
                nodes=(),
                initial_settings=Settings(
                    udp=True,
                    ipv6=False,
                    local_discovery=False,
                ),
            )
            client.start()
            try:
                client.wait_for(lambda s: bool(s.profile.address), timeout=10.0)
                sock = root / SOCKET_NAME
                server = ServiceServer(client, sock)
                server.start()
                remote = RemoteClient(root, sock)
                try:
                    self.assertTrue(remote.connect(timeout=5.0))
                    # Verify RPC commands update server and broadcast state.
                    remote.set_name("RemoteAlice")
                    client.wait_for(
                        lambda s: s.profile.name == "RemoteAlice",
                        timeout=5.0,
                    )
                    err = remote.add_friend("not-a-tox-id", "hi").result(
                        timeout=5.0)
                    self.assertIsNotNone(err)

                    ok = remote.set_avatar(b"fake-png").result(timeout=5.0)
                    self.assertTrue(ok)
                    client.wait_for(
                        lambda s: s.profile.avatar is not None, timeout=5.0)

                    remote.update_settings(
                        Settings(
                            udp=True,
                            ipv6=False,
                            local_discovery=False,
                            theme="dark",
                        ))
                    client.wait_for(
                        lambda s: s.settings.theme == "dark", timeout=5.0)
                finally:
                    remote.close()
                    server.stop()
            finally:
                client.close()

    def test_pictures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            client = ToxClient(root, NoopPlatform(), nodes=(),
                               initial_settings=Settings(
                                   udp=True, ipv6=False,
                                   local_discovery=False))
            client.start()
            client.wait_for(lambda s: bool(s.profile.address), timeout=10.0)
            server = ServiceServer(client, root / SOCKET_NAME)
            video = VideoServer(client, root / VIDEO_SOCKET_NAME)
            video.start()
            server.start()
            remote = RemoteClient(root, root / SOCKET_NAME)
            got: list[tuple[str, object]] = []
            arrived = threading.Condition()

            def watch(who: str, frame: object) -> None:
                with arrived:
                    got.append((who, frame))
                    arrived.notify_all()

            try:
                self.assertTrue(remote.connect(timeout=5.0))
                remote.watch_video(watch)
                friend = VideoFrame(6, 4, bytes(range(32)), b"uvwxyz",
                                    b"UVWXYZ", 8, 3, 3)
                own = VideoFrame.packed(4, 2, bytes(range(12))).mirror()
                shown = client._calls.video
                deadline = 10.0
                # The picture socket may still be connecting: show until seen.
                with arrived:
                    while (FRIEND, friend) not in got:
                        shown.show(FRIEND, friend)
                        self.assertTrue(arrived.wait(deadline))
                    shown.show(SELF, own)
                    shown.show(FRIEND, None)
                    self.assertTrue(
                        arrived.wait_for(lambda: got[-2:] == [
                            (SELF, own), (FRIEND, None)
                        ], deadline))
            finally:
                remote.close()
                server.stop()
                video.stop()
                client.close()

    def test_bad_request_and_lost_service(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            client = ToxClient(
                root, NoopPlatform(), nodes=(),
                initial_settings=Settings(ipv6=False, local_discovery=False))
            client.start()
            try:
                client.wait_for(
                    lambda s: bool(s.profile.address), timeout=10.0)
                sock = root / SOCKET_NAME
                server = ServiceServer(client, sock)
                server.start()
                closed = threading.Event()
                remote = RemoteClient(root, sock, on_closed=closed.set)
                try:
                    self.assertTrue(remote.connect(timeout=5.0))
                    # A request the service can't do fails alone.
                    with self.assertRaises(RuntimeError):
                        remote._rpc({"cmd": "add_friend"}).result(timeout=5.0)
                    # Unknown command fails instead of hanging.
                    with self.assertRaises(RuntimeError):
                        remote._rpc({"cmd": "no_such_cmd"}).result(timeout=5.0)
                    # send_file_path must not escape staging/.
                    outside = root / "secret.txt"
                    outside.write_text("do-not-read", encoding="utf-8")
                    with self.assertRaises(RuntimeError):
                        remote._rpc({
                            "cmd": "send_file_path",
                            "friend": "AA" * 32,
                            "name": "secret.txt",
                            "path": str(outside),
                        }).result(timeout=5.0)
                    # update_settings rejects unknown theme names.
                    with self.assertRaises(RuntimeError):
                        remote._rpc({
                            "cmd": "update_settings",
                            "settings": {
                                "udp": True,
                                "ipv6": False,
                                "local_discovery": False,
                                "stay_connected": False,
                                "theme": "neon",
                            },
                        }).result(timeout=5.0)
                    remote.set_name("StillThere")
                    client.wait_for(
                        lambda s: s.profile.name == "StillThere", timeout=5.0)

                    server.stop()
                    self.assertTrue(closed.wait(timeout=5.0))
                    self.assertFalse(remote.connected)
                    with self.assertRaises(ConnectionError):
                        remote.add_friend("00", "hi").result(timeout=5.0)
                finally:
                    remote.close()
                    server.stop()
            finally:
                client.close()

    def test_profile_lock_retries_until_released(self) -> None:
        import fcntl
        import os
        import time

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fd = os.open(root / ".lock", os.O_CREAT | os.O_RDWR, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            released = False
            try:
                client = ToxClient(
                    root, NoopPlatform(), nodes=(),
                    initial_settings=Settings(
                        ipv6=False, local_discovery=False),
                    lock_timeout=5.0,
                )
                client.start()
                try:
                    def _release() -> None:
                        time.sleep(0.15)
                        os.close(fd)

                    t = threading.Thread(target=_release, daemon=True)
                    t.start()
                    t.join(timeout=5.0)
                    released = True
                    st = client.wait_for(
                        lambda s: bool(s.profile.address), timeout=5.0)
                    self.assertTrue(st.profile.address)
                    self.assertFalse(client.closed)
                finally:
                    client.close()
            finally:
                if not released:
                    os.close(fd)

    def test_profile_lock_timeout_marks_client_closed(self) -> None:
        import fcntl
        import os
        import time

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fd = os.open(root / ".lock", os.O_CREAT | os.O_RDWR, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                client = ToxClient(
                    root, NoopPlatform(), nodes=(),
                    initial_settings=Settings(
                        ipv6=False, local_discovery=False),
                    lock_timeout=0.15,
                )
                client.start()
                start = time.monotonic()
                with self.assertRaises(RuntimeError) as ctx:
                    client.wait_for(
                        lambda s: bool(s.profile.address), timeout=10.0)
                self.assertLess(time.monotonic() - start, 3.0)
                self.assertIn("already open", str(ctx.exception))
                self.assertTrue(client.closed)
                # Subsequent calls fail fast instead of hanging forever.
                with self.assertRaises(RuntimeError):
                    client.add_friend("00", "hi").result(timeout=1.0)
                client.close()

                # serve() exits quickly with RuntimeError instead of hanging 60s.
                svc_client = ToxClient(
                    root, NoopPlatform(), nodes=(), lock_timeout=0.1)
                start = time.monotonic()
                with self.assertRaises(RuntimeError):
                    serve(svc_client, root / SOCKET_NAME, threading.Event())
                self.assertLess(time.monotonic() - start, 3.0)
            finally:
                os.close(fd)

    def test_save_failure_still_runs_cleanup_and_releases_lock(self) -> None:
        import fcntl
        import os

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            client = ToxClient(
                root, NoopPlatform(), nodes=(),
                initial_settings=Settings(ipv6=False, local_discovery=False),
            )
            client.start()
            client.wait_for(lambda s: bool(s.profile.address), timeout=10.0)

            def _boom() -> None:
                raise OSError("No space left on device")

            client._save = _boom  # type: ignore[method-assign]
            # Trigger a save on the Tox thread, which raises both inside the
            # loop and again inside finally -> _shutdown_tox() -> _save().
            client._post(lambda: setattr(client, "_unsaved", True))
            with self.assertRaises(RuntimeError):
                client.wait_for(lambda _s: False, timeout=10.0)
            self.assertTrue(client.closed)
            client.close()

            # Verify the .lock file descriptor was actually closed/released.
            fd = os.open(root / ".lock", os.O_CREAT | os.O_RDWR, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                os.close(fd)

    def test_restart_save_failure_closes_client_visibly(self) -> None:
        import fcntl
        import os

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            client = ToxClient(
                root, NoopPlatform(), nodes=(),
                initial_settings=Settings(
                    udp=True, ipv6=False, local_discovery=False),
            )
            client.start()
            client.wait_for(lambda s: bool(s.profile.address), timeout=10.0)

            def _boom() -> None:
                raise OSError("No space left on device")

            client._save = _boom  # type: ignore[method-assign]
            # Trigger a network-settings restart so the loop exits straight to
            # _shutdown_tox() -> _save() instead of ticking line 1536 first.
            client.update_settings(
                Settings(udp=False, ipv6=False, local_discovery=False))
            with self.assertRaises(RuntimeError) as ctx:
                client.wait_for(lambda _s: False, timeout=10.0)
            self.assertIn("No space left on device", str(ctx.exception))
            self.assertTrue(client.closed)
            client.close()

            fd = os.open(root / ".lock", os.O_CREAT | os.O_RDWR, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                os.close(fd)


if __name__ == "__main__":
    unittest.main()
