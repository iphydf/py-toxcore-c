import collections
import time
import unittest
from dataclasses import dataclass
from typing import Callable

import pytox.toxcore.tox as core
from pytox.toxcore import events


@dataclass
class TestException(Exception):
    status: core.Connection


@dataclass
class FriendInfo:
    connection_status: core.Connection = core.Connection.NONE
    request_message: bytes = b""


class TestTox(core.Tox):
    index: int
    connection_status_from_cb = core.Connection.NONE
    friends: dict[int, FriendInfo]

    def __init__(self, index: int) -> None:
        with core.Options() as options:
            options.local_discovery_enabled = False
            super(TestTox, self).__init__(options)
        self.index = index
        self.friends = collections.defaultdict(FriendInfo)

    def handle(self, event: events.Event) -> None:
        match event:
            case events.SelfConnectionStatusEvent(connection_status=status):
                self.connection_status_from_cb = status
                raise TestException(status)
            case events.FriendConnectionStatusEvent(
                    friend_number=n, connection_status=status):
                self.friends[n].connection_status = status
            case events.FriendRequestEvent(public_key=public_key,
                                           message=message):
                n = self.friend_add_norequest(public_key)
                self.friends[n].request_message = message


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

    def test_connection_status_cb(self) -> None:
        for tox in (self.tox1, self.tox2, self.tox3):
            # A handler's exception comes out of the loop.
            with self.assertRaises(TestException) as ex:
                self._wait_for_self_online()
                self.assertEqual(tox.connection_status,
                                 tox.connection_status_from_cb)
            self.assertEqual(ex.exception.status, tox.connection_status)

    def test_friend_add(self) -> None:
        self.tox1.friend_add(self.tox2.address,
                             b"are you gonna be my best friend?")
        self.tox2.friend_add(self.tox3.address,
                             b"lala lala lala la I'm Mr. Happy Face")
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


if __name__ == "__main__":
    unittest.main()
