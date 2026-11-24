# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""Live two-client integration tests for ToxClient (matching kTox ToxClientTest)."""
from __future__ import annotations

import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Callable
from typing import Optional

import pytox.toxcore.tox as core

from pytox_client.calls import FRIEND
from pytox_client.client import ToxClient
from pytox_client.media import AUDIO_FRAME
from pytox_client.media import Playout
from pytox_client.media import Tone
from pytox_client.media import VideoFrame
from pytox_client.model import ClientState
from pytox_client.model import FileState
from pytox_client.model import Friend
from pytox_client.model import Node
from pytox_client.model import Settings
from pytox_client.model import from_path
from pytox_client.platform_base import NoopPlatform
from pytox_client.profiles import CallLine

class _Ticker:
    """Calls ``tick`` every ``seconds`` on a thread, like a device would."""

    def __init__(self, seconds: float, tick: Callable[[], None]) -> None:
        self._stop = threading.Event()

        def run() -> None:
            while not self._stop.wait(seconds):
                tick()

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        self._thread.join()


class _FakeSound:
    """A microphone playing the ring tone, and a speaker that listens."""

    def __init__(self, recorded: Callable[[bytes], None], playout: Playout,
                 heard: list[bytes]) -> None:
        tone = Tone.RING.samples()
        at = [0]

        def tick() -> None:
            start = at[0] % (len(tone) - 2 * AUDIO_FRAME)
            at[0] = start + 2 * AUDIO_FRAME
            recorded(tone[start:at[0]])
            frame = playout.next()
            if any(frame.pcm):
                heard.append(frame.pcm)

        self._ticker = _Ticker(0.02, tick)

    def set_speaker(self, on: bool) -> None:
        del on

    def close(self) -> None:
        self._ticker.close()


class _MediaPlatform(NoopPlatform):
    """A platform with a microphone, a speaker and a small camera."""

    def __init__(self) -> None:
        super().__init__()
        self.heard: list[bytes] = []
        self.seen: list[VideoFrame] = []

    def open_sound(self, recorded: Callable[[bytes], None],
                   playout: Playout) -> _FakeSound:
        return _FakeSound(recorded, playout, self.heard)

    @property
    def cameras(self) -> int:
        return 1

    def open_camera(self, front: bool,
                    frame: Callable[[VideoFrame], None]) -> _Ticker:
        picture = VideoFrame.packed(64, 48, bytes(range(256)) * 18)
        return _Ticker(1 / 24, lambda: frame(picture))


_LOCAL_SETTINGS = Settings(udp=True, ipv6=False, local_discovery=False)


def _pair_dir(base: Path, name: str) -> Path:
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def _start_client(
    directory: Path,
    nodes: tuple[Node, ...] = (),
    platform: Optional[NoopPlatform] = None,
    call_line: Optional[CallLine] = None,
) -> ToxClient:
    c = ToxClient(
        directory,
        platform or NoopPlatform(),
        nodes=nodes,
        initial_settings=_LOCAL_SETTINGS,
        call_line=call_line,
    )
    c.start()
    c.wait_for(lambda s: bool(s.profile.address), timeout=10.0)
    return c


def _connect_pair(
    tmp: Path,
    alice_platform: Optional[NoopPlatform] = None,
    bob_platform: Optional[NoopPlatform] = None,
    bob_line: Optional[CallLine] = None,
) -> tuple[ToxClient, ToxClient, Node, str, str]:
    alice = _start_client(_pair_dir(tmp, "alice"), platform=alice_platform)
    alice.set_name("Alice")
    alice_node = alice.local_node().result(timeout=5.0)
    bob = _start_client(_pair_dir(tmp, "bob"), nodes=(alice_node, ),
                        platform=bob_platform, call_line=bob_line)
    bob.set_name("Bob")

    alice_addr = alice.state.profile.address
    bob_key = bob.state.profile.address[:64]
    alice_key = alice_addr[:64]

    err = bob.add_friend(alice_addr, "Hello from Bob").result(timeout=5.0)
    if err is not None:
        raise AssertionError(f"add_friend failed: {err}")

    st = alice.wait_for(lambda s: len(s.requests) == 1, timeout=25.0)
    alice.accept(st.requests[0])

    alice.wait_for(
        lambda s: any(f.key == bob_key and f.online for f in s.friends),
        timeout=25.0,
    )
    bob.wait_for(
        lambda s: any(f.key == alice_key and f.online for f in s.friends),
        timeout=25.0,
    )
    return alice, bob, alice_node, alice_key, bob_key


def _group_of_two(
    test: unittest.TestCase,
    alice: ToxClient,
    bob: ToxClient,
    bob_key: str,
    private: bool,
) -> str:
    """Alice starts a group, Bob joins from an invite; both are in it after."""
    test.assertIsNone(alice.create_group("Team", private).result(timeout=5.0))
    gid = alice.wait_for(
        lambda s: len(s.groups) == 1 and s.groups[0].connected,
        timeout=30.0,
    ).groups[0].id
    alice.invite_friend(gid, bob_key)
    invite = bob.wait_for(lambda s: len(s.invites) == 1,
                          timeout=30.0).invites[0]
    test.assertEqual(invite.name, "Team")
    bob.accept_invite(invite)
    alice.wait_for(lambda s: len(s.groups[0].peers) == 2, timeout=90.0)
    bob.wait_for(
        lambda s: len(s.groups) == 1 and len(s.groups[0].peers) == 2,
        timeout=90.0,
    )
    test.assertEqual(bob.state.invites, ())
    return gid


class ToxClientTest(unittest.TestCase):

    def test_handshake_message_action_and_read_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            alice, bob, _, alice_key, bob_key = _connect_pair(root)
            try:
                bob.send(alice_key, "hello alice")
                alice.wait_for(
                    lambda s: any(
                        f.key == bob_key and f.last is not None
                        and f.last.text == "hello alice" for f in s.friends),
                    timeout=15.0,
                )
                bob.open_chat(alice_key)
                bob.wait_for(
                    lambda s: s.chat is not None and any(
                        m.text == "hello alice" and m.delivered
                        for m in s.chat.messages),
                    timeout=15.0,
                )

                # Friend unread increments while chat isn't open/visible.
                alice_friend = next(
                    f for f in alice.state.friends if f.key == bob_key)
                self.assertEqual(alice_friend.unread, 1)

                alice.set_visible(True)
                alice.open_chat(bob_key)
                alice.wait_for(
                    lambda s: next(
                        f for f in s.friends if f.key == bob_key).unread == 0,
                    timeout=5.0,
                )

                # Action message round-trip.
                alice.send(bob_key, "waves", action=True)
                bob.wait_for(
                    lambda s: s.chat is not None and any(
                        m.action and m.text == "waves"
                        for m in s.chat.messages),
                    timeout=15.0,
                )
            finally:
                bob.close()
                alice.close()

    def test_file_transfer_and_avatar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            alice, bob, _, alice_key, bob_key = _connect_pair(root)
            try:
                # 1. File transfer.
                payload = os.urandom(64 * 1024)
                src = root / "sample.bin"
                src.write_bytes(payload)

                alice.open_chat(bob_key)
                bob.open_chat(alice_key)
                alice.send_file(bob_key, from_path(src))

                st_bob = bob.wait_for(
                    lambda s: s.chat is not None and any(
                        m.file is not None and m.file.name == "sample.bin"
                        for m in s.chat.messages),
                    timeout=20.0,
                )
                assert st_bob.chat is not None
                offer = next(m for m in st_bob.chat.messages
                             if m.file is not None)
                bob.accept_file(offer.id)

                st_done_bob = bob.wait_for(
                    lambda s: s.chat is not None and any(
                        m.id == offer.id and m.file is not None
                        and m.file.state == FileState.DONE
                        for m in s.chat.messages),
                    timeout=25.0,
                )
                assert st_done_bob.chat is not None
                got = next(m for m in st_done_bob.chat.messages
                           if m.id == offer.id)
                assert got.file is not None
                self.assertEqual(got.file.path.read_bytes(), payload)

                alice.wait_for(
                    lambda s: s.chat is not None and any(
                        m.file is not None and m.file.state == FileState.DONE
                        for m in s.chat.messages),
                    timeout=15.0,
                )

                # 2. Avatar send and removal.
                avatar_bytes = b"\x89PNG\r\n\x1a\nfake-avatar-bytes"
                self.assertTrue(alice.set_avatar(avatar_bytes).result(timeout=5.0))
                st_av = bob.wait_for(
                    lambda s: any(
                        f.key == alice_key and f.avatar is not None
                        for f in s.friends),
                    timeout=20.0,
                )
                fr_alice = next(
                    f for f in st_av.friends if f.key == alice_key)
                assert fr_alice.avatar is not None
                self.assertEqual(fr_alice.avatar.path.read_bytes(), avatar_bytes)

                self.assertTrue(alice.set_avatar(None).result(timeout=5.0))
                bob.wait_for(
                    lambda s: any(
                        f.key == alice_key and f.avatar is None
                        for f in s.friends),
                    timeout=20.0,
                )
            finally:
                bob.close()
                alice.close()

    def test_file_resume_after_receiver_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            alice, bob, alice_node, alice_key, bob_key = _connect_pair(root)
            bob_dir = _pair_dir(root, "bob")
            try:
                payload = os.urandom(2 * 1024 * 1024)
                src = root / "big.bin"
                src.write_bytes(payload)

                bob.open_chat(alice_key)
                alice.send_file(bob_key, from_path(src))

                st = bob.wait_for(
                    lambda s: s.chat is not None and any(
                        m.file is not None and m.file.name == "big.bin"
                        for m in s.chat.messages),
                    timeout=20.0,
                )
                assert st.chat is not None
                offer = next(
                    m for m in st.chat.messages if m.file is not None)
                bob.accept_file(offer.id)

                def _started(s: ClientState) -> bool:
                    if offer.id in s.progress and s.progress[offer.id] > 0:
                        return True
                    if s.chat is None:
                        return False
                    return any(
                        m.id == offer.id and m.file is not None
                        and (m.file.done > 0
                             or m.file.state == FileState.DONE)
                        for m in s.chat.messages)

                bob.wait_for(_started, timeout=20.0)
                bob.close()

                # Restart bob using the same profile dir; transfer must resume.
                bob = _start_client(bob_dir, nodes=(alice_node, ))
                bob.open_chat(alice_key)
                st_done = bob.wait_for(
                    lambda s: s.chat is not None and any(
                        m.file is not None and m.file.name == "big.bin"
                        and m.file.state == FileState.DONE
                        for m in s.chat.messages),
                    timeout=40.0,
                )
                assert st_done.chat is not None
                done_msg = next(
                    m for m in st_done.chat.messages
                    if m.file is not None and m.file.name == "big.bin")
                assert done_msg.file is not None
                self.assertEqual(done_msg.file.path.read_bytes(), payload)
            finally:
                bob.close()
                alice.close()

    def test_group_invited_friend_chats(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            alice, bob, _, _, bob_key = _connect_pair(Path(tmp))
            try:
                gid = _group_of_two(self, alice, bob, bob_key, private=True)
                self.assertEqual(bob.state.groups[0].id, gid)
                self.assertEqual(alice.state.groups[0].self_role,
                                 core.GroupRole.FOUNDER)

                bob.send_group_message(gid, "hi team")
                st = alice.wait_for(
                    lambda s: s.groups[0].last is not None
                    and s.groups[0].last.text == "hi team",
                    timeout=30.0,
                )
                arrived = st.groups[0]
                self.assertEqual(arrived.unread, 1)
                assert arrived.last is not None
                self.assertFalse(arrived.last.outgoing)
                self.assertEqual(arrived.last.peer_name, "Bob")

                alice.send_group_message(gid, "welcome")
                bob.wait_for(
                    lambda s: s.groups[0].last is not None
                    and s.groups[0].last.text == "welcome",
                    timeout=30.0,
                )
            finally:
                bob.close()
                alice.close()

    def test_group_stays_after_founder_restarts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            alice, bob, _, _, bob_key = _connect_pair(root)
            try:
                gid = _group_of_two(self, alice, bob, bob_key, private=True)
                alice.close()
                bob_node = bob.local_node().result(timeout=5.0)
                alice = _start_client(
                    _pair_dir(root, "alice"), nodes=(bob_node, ))
                st = alice.wait_for(
                    lambda s: len(s.groups) == 1
                    and len(s.groups[0].peers) == 2,
                    timeout=90.0,
                )
                self.assertEqual(st.groups[0].id, gid)
                self.assertEqual(st.groups[0].self_role,
                                 core.GroupRole.FOUNDER)
            finally:
                bob.close()
                alice.close()

    def test_group_public_joins_by_chat_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            alice, bob, _, _, _ = _connect_pair(Path(tmp))
            try:
                self.assertIsNone(
                    alice.create_group("Open", private=False).result(
                        timeout=5.0))
                gid = alice.wait_for(
                    lambda s: len(s.groups) == 1 and s.groups[0].connected,
                    timeout=30.0,
                ).groups[0].id
                self.assertIsNotNone(
                    bob.join_group("not hex", "").result(timeout=5.0))
                self.assertIsNone(bob.join_group(gid, "").result(timeout=5.0))
                self.assertEqual(
                    bob.join_group(gid, "").result(timeout=5.0),
                    "You're in this group already.")
                st = bob.wait_for(
                    lambda s: len(s.groups) == 1
                    and len(s.groups[0].peers) == 2,
                    timeout=90.0,
                )
                self.assertEqual(st.groups[0].name, "Open")

                bob.leave_group(gid)
                bob.wait_for(lambda s: not s.groups, timeout=10.0)
            finally:
                bob.close()
                alice.close()

    def test_offline_message_and_friend_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            alice = _start_client(_pair_dir(root, "alice"))
            alice_node = alice.local_node().result(timeout=5.0)
            bob = _start_client(_pair_dir(root, "bob"), nodes=(alice_node, ))
            try:
                alice_addr = alice.state.profile.address
                alice_key = alice_addr[:64]
                bob_key = bob.state.profile.address[:64]

                self.assertIsNone(
                    bob.add_friend(alice_addr, "offline test").result(
                        timeout=5.0))
                # Queue a message before alice accepts / goes online.
                bob.send(alice_key, "queued while offline")

                req = alice.wait_for(
                    lambda s: len(s.requests) == 1, timeout=25.0).requests[0]
                alice.accept(req)
                alice.open_chat(bob_key)
                alice.wait_for(
                    lambda s: s.chat is not None and any(
                        m.text == "queued while offline"
                        for m in s.chat.messages),
                    timeout=25.0,
                )

                # Delete friend removes both memory and DB entries.
                alice.delete(bob_key)
                alice.wait_for(
                    lambda s: not any(f.key == bob_key for f in s.friends),
                    timeout=5.0,
                )
            finally:
                bob.close()
                alice.close()

    def test_video_call_answered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            alice_media = _MediaPlatform()
            bob_media = _MediaPlatform()
            alice, bob, _, alice_key, bob_key = _connect_pair(
                Path(tmp), alice_media, bob_media)
            try:
                seen = bob_media.seen

                def watch(who: str, frame: Optional[VideoFrame]) -> None:
                    if who == FRIEND and frame is not None:
                        seen.append(frame)

                bob.watch_video(watch)
                bob.open_chat(alice_key)
                alice.call(bob_key, video=True)
                st = bob.wait_for(lambda s: s.call is not None, timeout=20.0)
                assert st.call is not None
                self.assertEqual((st.call.friend, st.call.outgoing,
                                  st.call.video_call, st.call.ringing),
                                 (alice_key, False, True, True))

                bob.answer(video=True)
                alice.wait_for(
                    lambda s: s.call is not None and s.call.answered,
                    timeout=20.0)
                deadline = time.monotonic() + 30.0
                while not (bob_media.heard and alice_media.heard and seen):
                    self.assertLess(time.monotonic(), deadline,
                                    "no sound or pictures")
                    time.sleep(0.1)
                self.assertEqual((seen[-1].width, seen[-1].height), (64, 48))

                alice.hang_up()
                st = bob.wait_for(
                    lambda s: s.call is None and s.chat is not None and bool(
                        s.chat.messages),
                    timeout=20.0)
                assert st.chat is not None
                note = st.chat.messages[-1]
                self.assertFalse(note.outgoing)
                self.assertTrue(note.preview(False).startswith("Video call, 0:"))
                st = alice.wait_for(lambda s: s.call is None, timeout=5.0)
                friend = next(f for f in st.friends if f.key == bob_key)
                assert friend.last is not None
                self.assertTrue(friend.last.outgoing)
                self.assertTrue(friend.last.preview(False).startswith("Video call, 0:"))
            finally:
                bob.close()
                alice.close()

    def test_calls_declined_and_missed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            alice, bob, _, alice_key, bob_key = _connect_pair(
                Path(tmp), _MediaPlatform(), _MediaPlatform())
            try:
                alice.call(bob_key, video=False)
                bob.wait_for(lambda s: s.call is not None, timeout=20.0)
                bob.hang_up()
                text, unread, bob_last = _call_note(bob, alice_key)
                self.assertEqual((text, unread), ("Declined call", 0))
                text, unread, alice_last = _call_note(alice, bob_key)
                self.assertEqual((text, unread), ("Call, declined", 0))

                alice.call(bob_key, video=False)
                bob.wait_for(lambda s: s.call is not None, timeout=20.0)
                alice.hang_up()
                text, unread, _ = _call_note(alice, bob_key, alice_last)
                self.assertEqual((text, unread), ("Call, not answered", 0))
                text, unread, _ = _call_note(bob, alice_key, bob_last)
                self.assertEqual((text, unread), ("Missed call", 1))
            finally:
                bob.close()
                alice.close()

    def test_call_while_another_profile_has_one_is_missed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            line = CallLine()
            alice, bob, _, alice_key, bob_key = _connect_pair(
                Path(tmp), _MediaPlatform(), _MediaPlatform(), bob_line=line)
            try:
                # Another of Bob's profiles is in a call.
                line.take("2")
                alice.call(bob_key, video=False)
                text, unread, _ = _call_note(bob, alice_key)
                self.assertEqual((text, unread), ("Missed call", 1))
                alice.wait_for(lambda s: s.call is None, timeout=20.0)
            finally:
                bob.close()
                alice.close()


def _call_note(client: ToxClient,
               key: str,
               after: int = 0) -> tuple[str, int, int]:
    """Wait for a call note newer than ``after`` in a chat.

    Its text, the chat's unread count, and its id.
    """

    def friend(s: ClientState) -> Friend:
        return next(f for f in s.friends if f.key == key)

    def noted(s: ClientState) -> bool:
        last = friend(s).last
        return (s.call is None and last is not None and last.call is not None
                and last.id > after)

    f = friend(client.wait_for(noted, timeout=20.0))
    assert f.last is not None
    return f.last.preview(False), f.unread, f.last.id


def _run_sharded() -> None:
    status_file = os.environ.get("TEST_SHARD_STATUS_FILE")
    if status_file:
        Path(status_file).touch()
    loader = unittest.defaultTestLoader
    names = sorted(loader.getTestCaseNames(ToxClientTest))
    only = os.environ.get("TESTBRIDGE_TEST_ONLY")
    if only:
        names = [n for n in names if only in f"ToxClientTest.{n}"]
    total = int(os.environ.get("TEST_TOTAL_SHARDS", "1"))
    index = int(os.environ.get("TEST_SHARD_INDEX", "0"))
    selected = [n for i, n in enumerate(names) if i % total == index]
    suite = unittest.TestSuite(ToxClientTest(n) for n in selected)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)


if __name__ == "__main__":
    _run_sharded()
