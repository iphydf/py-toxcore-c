# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""Unit tests for the SQLite Store (matching kTox's chats.db schema)."""
from __future__ import annotations

import os
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path

from pytox_client.model import CallNote
from pytox_client.model import CallOutcome
from pytox_client.model import FileState
from pytox_client.model import FriendRequest
from pytox_client.model import GroupInvite
from pytox_client.model import GroupMessage
from pytox_client.model import Settings
from pytox_client.store import SCHEMA_VERSION
from pytox_client.store import Store


class StoreTest(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "chats.db"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_schema_version_and_mismatch(self) -> None:
        store = Store(self.db_path)
        store.close()
        conn = sqlite3.connect(self.db_path)
        ver = conn.execute("PRAGMA user_version").fetchone()[0]
        self.assertEqual(ver, SCHEMA_VERSION)
        conn.execute("PRAGMA user_version = 99")
        conn.commit()
        conn.close()

        with self.assertRaises(RuntimeError):
            Store(self.db_path)

    def test_messages_paging_and_delivery(self) -> None:
        store = Store(self.db_path)
        alice = "AA" * 32
        bob = "BB" * 32
        store.add_friend(alice)
        store.add_friend(bob)

        inserted = [
            store.add_message(
                friend=alice,
                outgoing=i % 2 == 0,
                action=i == 3,
                text=f"msg {i}",
                time_ms=1000 + i,
                delivered=i % 2 == 1,
            )
            for i in range(1, 6)
        ]
        store.add_message(
            friend=bob,
            outgoing=True,
            action=False,
            text="for bob",
            time_ms=2000,
            delivered=False,
        )

        last2 = store.messages(alice, before=None, limit=2)
        self.assertEqual([m.text for m in last2], ["msg 4", "msg 5"])
        older = store.messages(alice, before=last2[0].id, limit=2)
        self.assertEqual([m.text for m in older], ["msg 2", "msg 3"])
        self.assertTrue(older[1].action)
        oldest = store.messages(alice, before=older[0].id, limit=2)
        self.assertEqual([m.text for m in oldest], ["msg 1"])
        self.assertEqual(store.last_message(alice), inserted[-1])

        pending = store.undelivered(alice)
        self.assertEqual([m.text for m in pending], ["msg 2", "msg 4"])
        store.mark_delivered(pending[0].id)
        self.assertEqual(
            [m.text for m in store.undelivered(alice)],
            ["msg 4"],
        )
        store.close()

    def test_friends_and_deletion(self) -> None:
        store = Store(self.db_path)
        key = "CC" * 32
        store.add_friend(key)
        store.add_friend(key)  # idempotent
        store.set_friend_name(key, "Carol")
        store.set_friend_status_message(key, "busy coding")
        store.set_unread(key, 3)
        store.set_avatar_hash(key, "DEAD" * 16)
        store.add_message(key, False, False, "hi", 10, True)

        friends = store.friends()
        self.assertEqual(friends[key].name, "Carol")
        self.assertEqual(friends[key].status_message, "busy coding")
        self.assertEqual(friends[key].unread, 3)
        self.assertEqual(friends[key].avatar_hash, "DEAD" * 16)

        store.delete_friend(key)
        self.assertNotIn(key, store.friends())
        self.assertEqual(store.messages(key, None, 10), [])
        store.close()

    def test_files_and_resume_lookup(self) -> None:
        store = Store(self.db_path)
        key = "DD" * 32
        store.add_friend(key)
        out_path = Path(self._tmp.name) / "out" / "photo.png"
        in_path = Path(self._tmp.name) / "in" / "report.pdf"

        out_msg = store.add_file(
            friend=key,
            outgoing=True,
            name="photo.png",
            size=4096,
            file_id="11" * 32,
            path=out_path,
            time_ms=100,
        )
        in_msg = store.add_file(
            friend=key,
            outgoing=False,
            name="report.pdf",
            size=8192,
            file_id="22" * 32,
            path=in_path,
            time_ms=200,
        )
        assert out_msg.file is not None
        assert in_msg.file is not None
        self.assertTrue(out_msg.file.is_image)
        self.assertFalse(in_msg.file.is_image)
        self.assertEqual(out_msg.file.state, FileState.OFFERED)
        self.assertEqual(store.file_id(in_msg.id), "22" * 32)
        # File rows must never appear in undelivered() text message queue.
        self.assertEqual(store.undelivered(key), [])

        self.assertEqual(
            store.incoming_file(key, "22" * 32),
            in_msg,
        )
        store.set_file_state(in_msg.id, FileState.ACTIVE, 1024)
        refetched = store.message_by_id(in_msg.id)
        assert refetched.file is not None
        self.assertEqual(refetched.file.state, FileState.ACTIVE)
        self.assertEqual(refetched.file.done, 1024)
        self.assertEqual(
            [m.id for m in store.unfinished_files(key, outgoing=True)],
            [out_msg.id],
        )
        store.set_file_state(in_msg.id, FileState.DONE, 8192)
        self.assertIsNone(store.incoming_file(key, "22" * 32))
        self.assertEqual(set(store.files(key)), {out_path, in_path})
        store.close()

    def test_requests_and_settings_persistence(self) -> None:
        store = Store(self.db_path)
        self.assertEqual(store.settings(), Settings())
        req1 = FriendRequest(key="AA" * 32, message="hello", time=500)
        req2 = FriendRequest(key="BB" * 32, message="second", time=200)
        store.add_request(req1)
        store.add_request(req2)
        self.assertEqual(store.requests(), [req2, req1])
        store.delete_request(req2.key)
        self.assertEqual(store.requests(), [req1])

        custom = Settings(
            udp=False,
            ipv6=False,
            local_discovery=False,
            stay_connected=False,
            theme="dark",
        )
        store.save_settings(custom)
        store.close()

        reopened = Store(self.db_path)
        self.assertEqual(reopened.settings(), custom)
        self.assertEqual(reopened.requests(), [req1])
        reopened.close()

    def test_groups_messages_and_invites(self) -> None:
        store = Store(self.db_path)
        gid = "AB" * 32
        store.add_group(gid)
        store.add_group(gid)  # idempotent
        store.set_group_unread(gid, 4)
        self.assertEqual(store.groups(), {gid: 4})

        sent = [
            store.add_group_message(
                GroupMessage(
                    id=0, group=gid, peer_key="CD" * 32, peer_name="Bob",
                    outgoing=i % 2 == 0, action=i == 3, private=i == 4,
                    text=f"g{i}", time=100 + i, sent=i != 2))
            for i in range(1, 6)
        ]
        self.assertTrue(all(m.id > 0 for m in sent))
        newest = store.group_messages(gid, None, 2)
        self.assertEqual([m.text for m in newest], ["g4", "g5"])
        self.assertTrue(newest[0].private)
        older = store.group_messages(gid, newest[0].id, 2)
        self.assertEqual([m.text for m in older], ["g2", "g3"])
        self.assertFalse(older[0].sent)
        self.assertTrue(older[1].action)
        self.assertEqual(store.last_group_message(gid), sent[-1])

        inv1 = GroupInvite(friend="AA" * 32, name="Team", data="0102", time=9)
        inv2 = GroupInvite(friend="BB" * 32, name="Open", data="0304", time=3)
        store.add_invite(inv1)
        store.add_invite(inv2)
        self.assertEqual(store.invites(), [inv2, inv1])
        store.delete_invite(inv2)
        self.assertEqual(store.invites(), [inv1])

        store.delete_group(gid)
        self.assertEqual(store.groups(), {})
        self.assertIsNone(store.last_group_message(gid))
        store.close()

    def test_version1_keeps_its_chats(self) -> None:
        # A version 1 store: the newest one without what came after.
        Store(self.db_path).close()
        conn = sqlite3.connect(self.db_path)
        for column in ("call_video", "call_outcome", "call_seconds"):
            conn.execute(f"ALTER TABLE messages DROP COLUMN {column}")
        conn.execute("ALTER TABLE friends DROP COLUMN hide_after_zero")
        conn.execute("INSERT INTO friends (key) VALUES ('AA')")
        conn.execute(
            "INSERT INTO messages (friend, outgoing, action, text, time, "
            "delivered) VALUES ('AA', 1, 0, 'hello', 5, 1)")
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
        conn.close()

        store = Store(self.db_path)
        [old] = store.messages("AA", None, 10)
        self.assertEqual((old.text, old.call), ("hello", None))
        self.assertFalse(store.friends()["AA"].hide_after_zero)
        store.add_call("AA", False, CallNote(True, CallOutcome.MISSED, 0), 6)
        store.set_hide_after_zero("AA", True)
        store.close()
        store = Store(self.db_path)
        self.assertEqual(
            [m.preview(False) for m in store.messages("AA", None, 10)],
            ["hello", "Missed video call"])
        self.assertTrue(store.friends()["AA"].hide_after_zero)
        store.close()

    def test_call_notes(self) -> None:
        store = Store(self.db_path)
        answered = store.add_call(
            "AA", True, CallNote(False, CallOutcome.ANSWERED, 201), 7)
        self.assertEqual(answered.call, CallNote(False, CallOutcome.ANSWERED, 201))
        self.assertTrue(answered.delivered)
        self.assertEqual(answered.preview(False), "Call, 3:21")
        declined = store.add_call(
            "AA", True, CallNote(True, CallOutcome.DECLINED, 0), 8)
        self.assertEqual(declined.preview(False), "Video call, declined")
        self.assertEqual(store.last_message("AA"), declined)
        store.close()

    def test_permissions_invite_cascade_and_null_file_id(self) -> None:
        store = Store(self.db_path)
        mode = stat.S_IMODE(os.stat(self.db_path).st_mode)
        self.assertEqual(mode, 0o600)

        alice = "AA" * 32
        bob = "BB" * 32
        store.add_friend(alice)
        store.add_friend(bob)
        txt = store.add_message(alice, True, False, "plain", 10, True)
        with self.assertRaises(KeyError):
            store.file_id(txt.id)

        inv_alice = GroupInvite(friend=alice, name="A", data="0102", time=1)
        inv_bob = GroupInvite(friend=bob, name="B", data="0304", time=2)
        store.add_invite(inv_alice)
        store.add_invite(inv_bob)
        store.delete_friend(alice)
        self.assertEqual(store.invites(), [inv_bob])
        store.close()


if __name__ == "__main__":
    unittest.main()
