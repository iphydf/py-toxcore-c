import collections
import time
import unittest
from dataclasses import dataclass
from dataclasses import field
from typing import Callable

import pytox.toxcore.tox as core
from pytox.toxcore import events


@dataclass
class FriendInfo:
    connection_status: core.Connection = core.Connection.NONE
    status: core.UserStatus = core.UserStatus.NONE
    status_message: bytes = b""
    name: bytes = b""
    request_message: bytes = b""
    typing: bool = False
    messages: list[tuple[core.MessageType,
                         bytes]] = field(default_factory=list)
    # message_id -> read receipt
    messages_sent: dict[int, bool] = field(
        default_factory=lambda: collections.defaultdict(bool))
    lossy_packets: list[bytes] = field(default_factory=list)
    lossless_packets: list[bytes] = field(default_factory=list)


@dataclass
class ConferencePeerInfo:
    name: bytes = b""


@dataclass
class ConferenceInfo:
    title: tuple[int, bytes] = (0, b"")
    inviter: int = -1
    connected: bool = False
    peers: dict[int, ConferencePeerInfo] = field(
        default_factory=lambda: collections.defaultdict(ConferencePeerInfo))
    messages: list[tuple[int, core.MessageType,
                         bytes]] = field(default_factory=list)


class TestTox(core.Tox):
    index: int
    connection_status = core.Connection.NONE
    friends: dict[int, FriendInfo]
    conferences: dict[int, ConferenceInfo]

    def __init__(self, index: int) -> None:
        with core.Options() as options:
            options.local_discovery_enabled = False
            super(TestTox, self).__init__(options)
        self.index = index
        self.friends = collections.defaultdict(FriendInfo)
        self.conferences = collections.defaultdict(ConferenceInfo)
        self.name = f"tox{index}".encode("utf-8")

    def handle(self, event: events.Event) -> None:
        match event:
            case events.SelfConnectionStatusEvent(connection_status=status):
                self.connection_status = status
            case events.FriendNameEvent(friend_number=n, name=name):
                self.friends[n].name = name
            case events.FriendStatusMessageEvent(friend_number=n,
                                                 message=message):
                self.friends[n].status_message = message
            case events.FriendStatusEvent(friend_number=n, status=status):
                self.friends[n].status = status
            case events.FriendConnectionStatusEvent(
                    friend_number=n, connection_status=status):
                self.friends[n].connection_status = status
            case events.FriendTypingEvent(friend_number=n, typing=typing):
                self.friends[n].typing = typing
            case events.FriendReadReceiptEvent(friend_number=n,
                                               message_id=message_id):
                assert self.friends[n].messages_sent[message_id] is False
                self.friends[n].messages_sent[message_id] = True
            case events.FriendRequestEvent(public_key=public_key,
                                           message=message):
                n = self.friend_add_norequest(public_key)
                self.friends[n].request_message = message
            case events.FriendMessageEvent(friend_number=n,
                                           type=type_,
                                           message=message):
                self.friends[n].messages.append((type_, message))
            case events.FriendLossyPacketEvent(friend_number=n, data=data):
                self.friends[n].lossy_packets.append(data)
            case events.FriendLosslessPacketEvent(friend_number=n, data=data):
                self.friends[n].lossless_packets.append(data)
            case events.ConferencePeerNameEvent(conference_number=c,
                                                peer_number=peer,
                                                name=name):
                self.conferences[c].peers[peer].name = name
            case events.ConferenceInviteEvent(friend_number=n,
                                              type=type_,
                                              cookie=cookie):
                assert type_ == core.ConferenceType.TEXT
                c = self.conference_join(n, cookie)
                self.conferences[c].inviter = n
            case events.ConferenceConnectedEvent(conference_number=c):
                self.conferences[c].connected = True
            case events.ConferenceMessageEvent(conference_number=c,
                                               peer_number=peer,
                                               type=type_,
                                               message=message):
                self.conferences[c].messages.append((peer, type_, message))
            case events.ConferenceTitleEvent(conference_number=c,
                                             peer_number=peer,
                                             title=title):
                self.conferences[c].title = (peer, title)


class AutoTest(unittest.TestCase):

    # TODO(iphydf): Use per-test toxes. Use Tox_Time to speed this up.
    tox1 = TestTox(1)
    tox2 = TestTox(2)
    tox3 = TestTox(3)

    def _iterate(self, max_iterate: int, cond: Callable[[], bool]) -> None:
        for _ in range(0, max_iterate):
            if not cond():
                return
            for event in self.tox1.iterate():
                self.tox1.handle(event)
            for event in self.tox2.iterate():
                self.tox2.handle(event)
            for event in self.tox3.iterate():
                self.tox3.handle(event)
            time.sleep(self.tox1.iteration_interval / 1000)
        self.fail(f"condition not met after {max_iterate} iterations")

    def _wait_for_self_online(self) -> None:
        self.tox2.bootstrap("127.0.0.1", self.tox1.udp_port, self.tox1.dht_id)
        self.tox3.bootstrap("127.0.0.1", self.tox1.udp_port, self.tox1.dht_id)

        def is_online() -> bool:
            return bool(self.tox1.connection_status
                        == core.Connection.NONE
                        or self.tox2.connection_status
                        == core.Connection.NONE
                        or self.tox3.connection_status
                        == core.Connection.NONE)

        # At most 20 seconds.
        self._iterate(
            1000,
            is_online,
        )

    def _wait_for_friend_online(self) -> None:
        self._wait_for_self_online()
        if not self.tox1.friend_list:
            self.tox1.friend_add(self.tox2.address,
                                 b"are you gonna be my best friend?")
            self.tox2.friend_add(self.tox3.address,
                                 b"lala lala lala la I'm Mr. Happy Face")

        def is_online() -> bool:
            return (self.tox1.friends[0].connection_status
                    == core.Connection.NONE
                    or self.tox2.friends[0].connection_status
                    == core.Connection.NONE
                    or self.tox2.friends[1].connection_status
                    == core.Connection.NONE
                    or self.tox3.friends[0].connection_status
                    == core.Connection.NONE)

        # At most 5 seconds.
        self._iterate(250, is_online)

    def test_friend_add(self) -> None:
        self._wait_for_friend_online()
        self.assertEqual(
            self.tox2.friends[self.tox2.friend_by_public_key(
                self.tox1.public_key)].request_message,
            b"are you gonna be my best friend?",
        )
        self.assertEqual(
            self.tox3.friends[self.tox3.friend_by_public_key(
                self.tox2.public_key)].request_message,
            b"lala lala lala la I'm Mr. Happy Face",
        )

    def test_friend_by_public_key(self) -> None:
        with self.assertRaises(core.FriendByPublicKeyError) as ex:
            # We're not our own friend.
            self.tox1.friend_by_public_key(self.tox1.public_key)
        self.assertEqual(
            ex.exception.code,
            core.FriendByPublicKeyError.Code.NOT_FOUND,
        )

    def test_send_message(self) -> None:
        self._wait_for_friend_online()
        self.tox1.friend_send_message(
            core.FriendNumber(0), core.MessageType.NORMAL, b"hello there!")
        friend = self.tox2.friends[self.tox2.friend_by_public_key(
            self.tox1.public_key)]
        self._iterate(100, lambda: not friend.messages)
        self.assertEqual(
            friend.messages[0],
            (core.MessageType.NORMAL, b"hello there!"),
        )

    def test_send_lossy_packet(self) -> None:
        self._wait_for_friend_online()
        self.tox1.friend_send_lossy_packet(core.FriendNumber(0), b"\xc8hello there!")
        friend = self.tox2.friends[self.tox2.friend_by_public_key(
            self.tox1.public_key)]
        self._iterate(100, lambda: not friend.lossy_packets)
        self.assertEqual(friend.lossy_packets[0], b"\xc8hello there!")

    def test_send_lossless_packet(self) -> None:
        self._wait_for_friend_online()
        self.tox1.friend_send_lossless_packet(core.FriendNumber(0), b"\xa0general kenobi.")
        friend = self.tox2.friends[self.tox2.friend_by_public_key(
            self.tox1.public_key)]
        self._iterate(100, lambda: not friend.lossless_packets)
        self.assertEqual(friend.lossless_packets[0], b"\xa0general kenobi.")

    def test_status(self) -> None:
        self._wait_for_friend_online()
        friend_number = self.tox2.friend_by_public_key(self.tox1.public_key)
        friend = self.tox2.friends[friend_number]
        self.assertEqual(self.tox1.status,
                         core.UserStatus.NONE)
        self.tox1.status = core.UserStatus.AWAY
        self.assertEqual(self.tox1.status,
                         core.UserStatus.AWAY)
        self._iterate(
            100,
            lambda: friend.status == core.UserStatus.NONE)
        self.assertEqual(friend.status,
                         core.UserStatus.AWAY)
        self.assertEqual(
            self.tox2.friend_get_status(friend_number),
            core.UserStatus.AWAY,
        )

    def test_name(self) -> None:
        self._wait_for_friend_online()
        friend_number = self.tox2.friend_by_public_key(self.tox1.public_key)
        friend = self.tox2.friends[friend_number]
        self.assertEqual(self.tox1.name, b"tox1")
        self.tox1.name = b"Now that's a name I haven't heard in a long time"
        self.assertEqual(self.tox1.name,
                         b"Now that's a name I haven't heard in a long time")
        self._iterate(100, lambda: friend.name == b"tox1")
        self.assertEqual(friend.name,
                         b"Now that's a name I haven't heard in a long time")
        self.assertEqual(
            self.tox2.friend_get_name(friend_number),
            b"Now that's a name I haven't heard in a long time",
        )

    def test_status_message(self) -> None:
        self._wait_for_friend_online()
        friend_number = self.tox2.friend_by_public_key(self.tox1.public_key)
        friend = self.tox2.friends[friend_number]
        self.assertEqual(self.tox1.status_message, b"")
        self.tox1.status_message = b"Python rocks!"
        self.assertEqual(self.tox1.status_message, b"Python rocks!")
        self._iterate(100, lambda: friend.status_message == b"")
        self.assertEqual(friend.status_message, b"Python rocks!")
        self.assertEqual(self.tox2.friend_get_status_message(friend_number),
                         b"Python rocks!")

    def test_typing(self) -> None:
        self._wait_for_friend_online()
        friend_number = self.tox2.friend_by_public_key(self.tox1.public_key)
        friend = self.tox2.friends[friend_number]
        self.assertFalse(friend.typing)
        self.assertFalse(self.tox2.friend_get_typing(friend_number))
        self.tox1.set_typing(core.FriendNumber(0), True)
        self._iterate(100, lambda: not friend.typing)
        self.assertTrue(self.tox2.friend_get_typing(friend_number))

    def test_read_receipt(self) -> None:
        self._wait_for_friend_online()
        friend_number = self.tox1.friend_by_public_key(self.tox2.public_key)
        friend = self.tox1.friends[friend_number]
        msg_id = self.tox1.friend_send_message(
            friend_number,
            core.MessageType.NORMAL,
            b"hello there!",
        )
        self.assertFalse(friend.messages_sent[msg_id])
        self._iterate(100, lambda: not friend.messages_sent[msg_id])

    def test_conference_invite(self) -> None:
        self._wait_for_friend_online()
        # tox1 creates conference.
        cnum1 = self.tox1.conference_new()
        self.assertListEqual(self.tox1.conference_chatlist, [cnum1])
        # tox1 invites tox2 to conference.
        self.tox1.conference_invite(
            self.tox1.friend_by_public_key(self.tox2.public_key), cnum1)
        # wait for tox2 to join conference.
        self._iterate(100, lambda: not self.tox2.conference_chatlist)
        self.assertEqual(len(self.tox2.conference_chatlist), 1)
        # wait for group connection.
        cnum2 = self.tox2.conference_chatlist[0]
        self._iterate(100, lambda: not self.tox2.conferences[cnum2].connected)
        # tox2 invites tox3 to conference.
        self.tox2.conference_invite(
            self.tox2.friend_by_public_key(self.tox3.public_key), cnum2)
        # wait for tox3 to join conference.
        self._iterate(100, lambda: not self.tox3.conference_chatlist)
        self.assertEqual(len(self.tox3.conference_chatlist), 1)
        # test conference_by_id.
        self.assertEqual(
            self.tox1.conference_by_id(self.tox1.conference_get_id(cnum1)),
            cnum1)
        self.assertEqual(
            self.tox1.conference_get_type(cnum1),
            core.ConferenceType.TEXT,
        )

    def test_conference_message(self) -> None:
        self._wait_for_friend_online()
        cnum1 = self.tox1.conference_chatlist[0]
        cnum2 = self.tox2.conference_chatlist[0]
        cnum3 = self.tox3.conference_chatlist[0]
        # wait for all toxes to see all 3 peers.
        self._iterate(
            100,
            lambda: any(
                len(tox.conferences[tox.conference_chatlist[0]].peers) < 2
                for tox in (self.tox1, self.tox2, self.tox3)),
        )
        # wait for group connection.
        self._iterate(100, lambda: not self.tox2.conferences[cnum2].connected)
        # check that none of the toxes have messages, yet.
        self.assertFalse(self.tox1.conferences[cnum1].messages)
        self.assertFalse(self.tox2.conferences[cnum2].messages)
        self.assertFalse(self.tox3.conferences[cnum3].messages)
        # tox2 sends message to conference.
        self.tox2.conference_send_message(
            cnum2, core.MessageType.NORMAL,
            b"hello there!")
        # wait for toxes to receive message.
        self._iterate(
            100,
            lambda: any(not tox.conferences[tox.conference_chatlist[0]].
                        messages for tox in (self.tox1, self.tox2, self.tox3)),
        )
        # check message contents.
        self.assertEqual(
            self.tox1.conferences[cnum1].messages[0],
            (1, core.MessageType.NORMAL,
             b"hello there!"),
        )
        self.assertEqual(
            self.tox2.conferences[cnum2].messages[0],
            (1, core.MessageType.NORMAL,
             b"hello there!"),
        )
        self.assertEqual(
            self.tox3.conferences[cnum3].messages[0],
            (1, core.MessageType.NORMAL,
             b"hello there!"),
        )

    def test_conference_peer_name(self) -> None:
        self._wait_for_friend_online()
        cnum1 = self.tox1.conference_chatlist[0]
        cnum2 = self.tox2.conference_chatlist[0]
        cnum3 = self.tox3.conference_chatlist[0]
        # check peer names.
        self.assertEqual(self.tox1.conferences[cnum1].peers[1].name, b"tox2")
        self.assertEqual(self.tox2.conferences[cnum2].peers[1].name, b"tox2")
        self.assertEqual(self.tox2.conferences[cnum2].peers[2].name, b"tox3")
        self.assertEqual(self.tox3.conferences[cnum3].peers[1].name, b"tox2")

    def test_conference_title(self) -> None:
        self._wait_for_friend_online()
        cnum1 = self.tox1.conference_chatlist[0]
        cnum2 = self.tox2.conference_chatlist[0]
        cnum3 = self.tox3.conference_chatlist[0]
        # check title isn't set yet.
        self.assertEqual(self.tox1.conferences[cnum1].title, (0, b""))
        self.assertEqual(self.tox2.conferences[cnum2].title, (0, b""))
        self.assertEqual(self.tox3.conferences[cnum3].title, (0, b""))
        # tox2 sets title.
        self.tox2.conference_set_title(cnum1, b"TokTok dev chat")
        # wait for title to be set for tox1 and tox3.
        self._iterate(
            100,
            lambda: any(tox.conferences[tox.conference_chatlist[0]].title[1] ==
                        b"" for tox in (self.tox1, self.tox3)),
        )
        self.assertEqual(self.tox1.conferences[cnum2].title,
                         (1, b"TokTok dev chat"))
        self.assertEqual(self.tox3.conferences[cnum3].title,
                         (1, b"TokTok dev chat"))


if __name__ == "__main__":
    unittest.main()
