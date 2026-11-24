# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""Unit tests for message splitting, filename sanitization, formatting, and navigation."""
from __future__ import annotations

import datetime
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import pytox.toxcore.tox as core

from pytox_client.client import safe_name
from pytox_client.client import split_message
from pytox_client.client import truncate_utf8
from pytox_client.model import FileState
from pytox_client.model import FileTransfer
from pytox_client.model import Friend
from pytox_client.model import Group
from pytox_client.model import GroupMessage
from pytox_client.model import Message
from pytox_client.model import Peer
from pytox_client.model import duration
from pytox_client.platform_desktop import unique_download_path
from pytox_client.ui.formatting import BubbleItem
from pytox_client.ui.formatting import DayItem
from pytox_client.ui.formatting import GroupBubbleItem
from pytox_client.ui.formatting import avatar_rgba
from pytox_client.ui.formatting import chat_items
from pytox_client.ui.formatting import clock_time
from pytox_client.ui.formatting import day_heading
from pytox_client.ui.formatting import day_of
from pytox_client.ui.formatting import file_size
from pytox_client.ui.formatting import friend_row_preview
from pytox_client.ui.formatting import group_chat_items
from pytox_client.ui.formatting import group_row_preview
from pytox_client.ui.formatting import group_subtitle
from pytox_client.ui.formatting import grouped_id
from pytox_client.ui.formatting import presence_text
from pytox_client.ui.formatting import role_label
from pytox_client.ui.formatting import self_connection_text
from pytox_client.ui.formatting import short_time
from pytox_client.ui.navigator import AddRoute
from pytox_client.ui.navigator import ChatRoute
from pytox_client.ui.navigator import ChatsPage
from pytox_client.ui.navigator import FriendRoute
from pytox_client.ui.navigator import GroupInfoRoute
from pytox_client.ui.navigator import GroupRoute
from pytox_client.ui.navigator import Navigator
from pytox_client.ui.navigator import ProfileRoute


class SplitMessageTest(unittest.TestCase):

    def test_short_message_stays_whole(self) -> None:
        self.assertEqual(split_message("hello", max_bytes=10), ["hello"])
        self.assertEqual(split_message("", max_bytes=10), [""])

    def test_exact_limit_not_split(self) -> None:
        text = "a" * 10
        self.assertEqual(split_message(text, max_bytes=10), [text])

    def test_prefers_breaking_on_space_or_newline(self) -> None:
        text = "alpha beta gamma delta"
        parts = split_message(text, max_bytes=12)
        self.assertEqual("".join(parts), text)
        for part in parts:
            self.assertLessEqual(len(part.encode("utf-8")), 12)
        self.assertEqual(parts[0], "alpha beta ")

    def test_respects_utf8_boundaries(self) -> None:
        # 4-byte emoji + 3-byte CJK chars.
        text = "\U0001f680" * 5 + "\u4e16\u754c" * 4
        parts = split_message(text, max_bytes=7)
        self.assertEqual("".join(parts), text)
        for part in parts:
            self.assertLessEqual(len(part.encode("utf-8")), 7)
            # Round-trip strictly valid UTF-8.
            self.assertEqual(part.encode("utf-8").decode("utf-8"), part)

    def test_single_codepoint_over_limit_still_progresses(self) -> None:
        text = "\U0001f600ab"
        parts = split_message(text, max_bytes=2)
        self.assertEqual("".join(parts), text)
        self.assertEqual(parts[0], "\U0001f600")

    def test_default_tox_limit_round_trips(self) -> None:
        long_text = "word " * 1000
        parts = split_message(long_text)
        self.assertGreater(len(parts), 1)
        self.assertEqual("".join(parts), long_text)
        for part in parts:
            self.assertLessEqual(
                len(part.encode("utf-8")),
                core.MAX_MESSAGE_LENGTH,
            )


class SafeNameTest(unittest.TestCase):

    def test_strips_paths_dots_and_control_chars(self) -> None:
        self.assertEqual(safe_name("../../etc/passwd"), "passwd")
        self.assertEqual(safe_name("C:\\temp\\notes.txt"), "notes.txt")
        self.assertEqual(safe_name("..hidden"), "hidden")
        self.assertEqual(safe_name("bad\x00name\n.bin"), "badname.bin")
        self.assertEqual(safe_name("..."), "file")
        self.assertEqual(safe_name(""), "file")
        self.assertLessEqual(len(safe_name("x" * 200)), 120)

    def test_unique_download_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p1 = unique_download_path(root, "photo.png")
            self.assertEqual(p1.name, "photo.png")
            p1.write_bytes(b"1")
            p2 = unique_download_path(root, "photo.png")
            self.assertEqual(p2.name, "photo (1).png")
            p2.write_bytes(b"2")
            p3 = unique_download_path(root, "photo.png")
            self.assertEqual(p3.name, "photo (2).png")
            # Path traversal and broken symlinks must not escape or overwrite.
            escaped = unique_download_path(root, "../../evil.png")
            self.assertEqual(escaped.parent, root)
            self.assertEqual(escaped.name, "evil.png")
            broken = root / "link.txt"
            broken.symlink_to(root / "missing-target")
            next_link = unique_download_path(root, "link.txt")
            self.assertEqual(next_link.name, "link (1).txt")

    def test_strips_bidi_reserved_names_and_utf8_bytes(self) -> None:
        # Unicode RLO spoofing char must be stripped.
        self.assertEqual(safe_name("report\u202egnp.exe"), "reportgnp.exe")
        # Windows reserved device names get prefixed safely.
        self.assertEqual(safe_name("CON"), "_CON")
        self.assertEqual(safe_name("nul.txt"), "_nul.txt")
        self.assertEqual(safe_name("COM1"), "_COM1")
        # Multi-byte UTF-8 name is capped by bytes, not characters.
        long_cjk = "\u4e16" * 100
        self.assertLessEqual(len(safe_name(long_cjk).encode("utf-8")), 120)
        self.assertEqual(truncate_utf8("\U0001f680ab", 0), "")
        self.assertEqual(truncate_utf8("\U0001f680ab", 3), "")
        self.assertEqual(truncate_utf8("\U0001f680ab", 4), "\U0001f680")
        self.assertEqual(truncate_utf8("\U0001f680ab", 5), "\U0001f680a")


class FormattingTest(unittest.TestCase):

    def test_grouped_id_and_file_size(self) -> None:
        self.assertEqual(grouped_id("AABBCCDD1122"), "AABB CCDD 1122")
        self.assertEqual(file_size(0), "0 B")
        self.assertEqual(file_size(512), "512 B")
        self.assertEqual(file_size(1536), "1.5 KB")
        self.assertEqual(file_size(2 * 1024 * 1024), "2.0 MB")

    def test_dates_and_chat_items(self) -> None:
        today = datetime.date(2026, 11, 22)
        self.assertEqual(day_heading(today, today), "Today")
        self.assertEqual(
            day_heading(datetime.date(2026, 11, 21), today), "Yesterday")
        self.assertEqual(
            day_heading(datetime.date(2026, 10, 1), today), "Oct 01, 2026")

        ts_day1 = int(
            datetime.datetime(2026, 11, 20, 9, 15).timestamp() * 1000)
        ts_day1_b = int(
            datetime.datetime(2026, 11, 20, 9, 16).timestamp() * 1000)
        ts_day2 = int(
            datetime.datetime(2026, 11, 22, 14, 5).timestamp() * 1000)
        self.assertEqual(short_time(ts_day2, today), "14:05")
        self.assertEqual(short_time(ts_day1, today), "Fri")

        m1 = Message(1, "K", True, False, "a", ts_day1, True)
        m2 = Message(2, "K", True, False, "b", ts_day1_b, True)
        m3 = Message(3, "K", True, False, "c", ts_day2, True)
        items = chat_items([m1, m2, m3])
        self.assertEqual(len(items), 5)
        self.assertIsInstance(items[0], DayItem)
        self.assertIsInstance(items[1], BubbleItem)
        self.assertFalse(items[1].is_last)  # type: ignore[union-attr]
        self.assertTrue(items[2].is_last)  # type: ignore[union-attr]
        self.assertIsInstance(items[3], DayItem)
        self.assertTrue(items[4].is_last)  # type: ignore[union-attr]

    def test_presence_and_preview(self) -> None:
        self.assertEqual(
            presence_text(core.Connection.NONE, core.UserStatus.NONE),
            "offline")
        self.assertEqual(
            presence_text(core.Connection.UDP, core.UserStatus.AWAY),
            "away")
        self.assertEqual(
            presence_text(core.Connection.TCP, core.UserStatus.BUSY),
            "busy")
        self.assertEqual(
            self_connection_text(core.Connection.TCP, long=True),
            "Online through a TCP relay")

        ft = FileTransfer("pic.png", 10, FileState.DONE, 10, Path("pic.png"))
        msg = Message(1, "AA" * 32, True, False, "", 0, True, ft)
        friend = Friend(
            key="AA" * 32,
            name="Alice",
            status_message="",
            status=core.UserStatus.NONE,
            connection=core.Connection.UDP,
            typing=False,
            unread=0,
            last=msg,
            avatar=None,
            hide_after_zero=False,
        )
        self.assertEqual(friend_row_preview(friend), "You: [file] pic.png")
        text = Message(2, "AA" * 32, False, False, "hi\0\xe9!\0", 0, True)
        self.assertEqual(
            friend_row_preview(replace(friend, last=text)), "hi\\0\xe9!\\0")
        self.assertEqual(
            friend_row_preview(
                replace(friend, last=text, hide_after_zero=True)),
            "hi\\0[4 bytes]")
        r, g, b, a = avatar_rgba("FF0000")
        self.assertEqual(a, 1.0)
        self.assertTrue(all(0.0 <= c <= 1.0 for c in (r, g, b)))


class GroupFormattingTest(unittest.TestCase):

    @staticmethod
    def _gm(mid: int, peer: str, outgoing: bool, ts: int) -> GroupMessage:
        return GroupMessage(
            id=mid, group="G" * 64, peer_key=peer, peer_name=peer[:3],
            outgoing=outgoing, action=False, private=False, text=f"m{mid}",
            time=ts, sent=True)

    def test_group_chat_items_group_by_sender_and_day(self) -> None:
        day1 = int(datetime.datetime(2026, 11, 20, 9, 0).timestamp() * 1000)
        day2 = int(datetime.datetime(2026, 11, 21, 9, 0).timestamp() * 1000)
        msgs = [
            self._gm(1, "AAA" * 4, False, day1),
            self._gm(2, "AAA" * 4, False, day1 + 1000),
            self._gm(3, "BBB" * 4, False, day1 + 2000),
            self._gm(4, "", True, day1 + 3000),
            self._gm(5, "", True, day2),
        ]
        items = group_chat_items(msgs)
        bubbles = [i for i in items if isinstance(i, GroupBubbleItem)]
        self.assertEqual(sum(isinstance(i, DayItem) for i in items), 2)
        self.assertEqual(
            [(b.is_first, b.is_last) for b in bubbles],
            [(True, False), (False, True), (True, True), (True, True),
             (True, True)],
        )

    def test_group_subtitle_preview_and_roles(self) -> None:
        me = Peer(key="11" * 32, name="Me", role=core.GroupRole.FOUNDER,
                  status=core.UserStatus.NONE, is_self=True)
        bob = Peer(key="22" * 32, name="", role=core.GroupRole.OBSERVER,
                   status=core.UserStatus.NONE, is_self=False)
        group = Group(
            id="AB" * 32, name="", topic="Release", privacy=(
                core.GroupPrivacyState.PUBLIC),
            connected=True, peers=(me, bob), self_role=core.GroupRole.FOUNDER,
            password="", peer_limit=10, topic_locked=True, unread=0,
            last=None, problem=None)
        self.assertEqual(group.display_name, "ABABABAB")
        self.assertEqual(bob.display_name, "22222222")
        self.assertTrue(group.moderator)
        self.assertTrue(group.can_set_topic)
        self.assertEqual(group_subtitle(group), "2 people - Release")
        self.assertEqual(group_row_preview(group), "2 people - Release")
        self.assertEqual(
            group_subtitle(replace(group, connected=False)), "Connecting...")
        self.assertEqual(
            group_subtitle(replace(group, problem="The group is full.")),
            "The group is full.")
        self.assertEqual(
            group_subtitle(replace(group, peers=(me, ))),
            "Looking for the group...")
        self.assertEqual(
            group_subtitle(replace(group, name="Team", peers=(me, ),
                                   topic="")),
            "1 person")
        observer = replace(group, self_role=core.GroupRole.OBSERVER)
        self.assertFalse(observer.can_set_topic)
        self.assertTrue(
            replace(observer, self_role=core.GroupRole.USER,
                    topic_locked=False).can_set_topic)
        last = replace(self._gm(1, "22" * 32, False, 0), peer_name="Bob")
        self.assertEqual(
            group_row_preview(replace(group, last=last)), "Bob: m1")
        self.assertEqual(
            group_row_preview(replace(group, last=replace(
                last, outgoing=True, action=True))), "* You m1")
        self.assertEqual(role_label(core.GroupRole.FOUNDER), "Founder")
        self.assertEqual(role_label(core.GroupRole.USER), "")
        self.assertEqual(role_label(core.GroupRole.OBSERVER), "Can only read")
        nameless = replace(last, peer_name="", peer_key="ABCD1234" + "00" * 28)
        self.assertEqual(
            group_row_preview(replace(group, last=nameless)), "ABCD1234: m1")

    def test_backward_timestamps_produce_unique_day_keys_and_safe_dates(
            self) -> None:
        self.assertEqual(duration(-5), "0:00")
        self.assertEqual(day_of(1 << 62), datetime.date(1970, 1, 1))
        self.assertEqual(clock_time(-(1 << 62)), "00:00")

        d1 = int(datetime.datetime(2026, 11, 20, 9, 0).timestamp() * 1000)
        d2 = int(datetime.datetime(2026, 11, 21, 9, 0).timestamp() * 1000)
        msgs = [
            Message(1, "K", True, False, "a", d1, True),
            Message(2, "K", True, False, "b", d2, True),
            Message(3, "K", True, False, "c", d1 + 1000, True),
        ]
        day_keys = [i.key for i in chat_items(msgs) if isinstance(i, DayItem)]
        self.assertEqual(len(day_keys), 3)
        self.assertEqual(len(set(day_keys)), 3)

        gmsgs = [
            self._gm(1, "AA" * 32, False, d1),
            self._gm(2, "AA" * 32, False, d2),
            self._gm(3, "AA" * 32, False, d1 + 1000),
        ]
        g_keys = [
            i.key for i in group_chat_items(gmsgs) if isinstance(i, DayItem)
        ]
        self.assertEqual(len(g_keys), 3)
        self.assertEqual(len(set(g_keys)), 3)


class NavigatorTest(unittest.TestCase):

    def test_group_routes(self) -> None:
        nav = Navigator()
        nav.show(GroupRoute("G1"))
        nav.push(GroupInfoRoute("G1"))
        self.assertEqual(nav.current, GroupInfoRoute("G1"))
        self.assertTrue(nav.back())
        self.assertEqual(nav.current, GroupRoute("G1"))

    def test_show_push_and_back(self) -> None:
        seen: list[object] = []
        nav = Navigator(on_change=seen.append)
        self.assertIsInstance(nav.current, ChatsPage)
        self.assertFalse(nav.back())

        nav.show(ChatRoute("A"))
        nav.push(FriendRoute("A"))
        nav.push(FriendRoute("A"))  # duplicate ignored
        self.assertEqual(nav.current, FriendRoute("A"))
        self.assertTrue(nav.back())
        self.assertEqual(nav.current, ChatRoute("A"))
        nav.show(AddRoute())
        self.assertEqual(nav.current, AddRoute())
        nav.show(ProfileRoute())
        self.assertTrue(nav.back())
        self.assertIsInstance(nav.current, ChatsPage)
        self.assertEqual(len(seen), 6)


if __name__ == "__main__":
    unittest.main()
