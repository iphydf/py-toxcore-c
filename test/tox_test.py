import unittest
from typing import cast

import pytox.toxcore.tox as c
from pytox.toxcore import events
from pytox import common


class ToxTest(unittest.TestCase):

    def test_version(self) -> None:
        self.assertEqual(len(c.VERSION.split(".")), 3)

    def test_use_after_free(self) -> None:
        opts = c.Options()
        with c.Tox(opts) as tox:
            saved_tox = tox
        with self.assertRaises(common.UseAfterFreeException):
            print(saved_tox.address)

    def test_pass_invalid_type(self) -> None:
        with self.assertRaises(TypeError):
            with c.Tox(cast(c.Options, "hello")):
                pass

    def test_pass_none(self) -> None:
        with c.Tox(None):
            pass

    def test_pass_invalid_options(self) -> None:
        opts = c.Options()
        opts.proxy_type = c.ProxyType.SOCKS5
        opts.proxy_host = "invalid-host"
        opts.proxy_port = 1234
        with self.assertRaises(c.NewError) as e:
            c.Tox(opts)
        self.assertEqual(e.exception.code,
                         c.NewError.Code.PROXY_BAD_HOST)

    def test_address(self) -> None:
        opts = c.Options()
        with c.Tox(opts) as tox:
            self.assertEqual(tox.address, tox.address)

    def test_nospam(self) -> None:
        with c.Tox(None) as tox:
            tox.nospam = 0x12345678
            self.assertEqual(tox.nospam, 0x12345678)
            self.assertEqual(tox.address[-6:-2].hex(), "12345678")

    def test_public_key_is_address_prefix(self) -> None:
        opts = c.Options()
        with c.Tox(opts) as tox:
            self.assertEqual(
                tox.public_key.hex()[:72] + format(tox.nospam, "08x"),
                tox.address[:36].hex(),
            )

    def test_public_key_is_not_secret_key(self) -> None:
        opts = c.Options()
        with c.Tox(opts) as tox:
            self.assertNotEqual(tox.public_key, tox.secret_key)

    def test_savedata_contains_secret_key(self) -> None:
        with c.Tox() as tox:
            self.assertIn(tox.secret_key, tox.savedata)

    def test_set_name(self) -> None:
        with c.Tox() as tox:
            self.assertEqual(tox.name, b"")
            tox.name = b"iphy"
            self.assertEqual(tox.name, b"iphy")

            tox.name = b"x" * c.MAX_NAME_LENGTH
            with self.assertRaises(c.ApiException):
                tox.name = b"x" * (c.MAX_NAME_LENGTH + 1)

    def test_set_status_message(self) -> None:
        with c.Tox() as tox:
            self.assertEqual(tox.status_message, b"")
            tox.status_message = b"pytox is cool now"
            self.assertEqual(tox.status_message, b"pytox is cool now")

            tox.status_message = b"x" * c.MAX_STATUS_MESSAGE_LENGTH
            with self.assertRaises(c.ApiException):
                tox.status_message = b"x" * (c.MAX_STATUS_MESSAGE_LENGTH + 1)

    def test_set_status(self) -> None:
        with c.Tox() as tox:
            self.assertEqual(tox.status,
                             c.UserStatus.NONE)
            tox.status = c.UserStatus.AWAY
            self.assertEqual(tox.status,
                             c.UserStatus.AWAY)
            # There is no invalid status to set.
            with self.assertRaises(ValueError):
                c.UserStatus(50)

    def test_friend_add(self) -> None:
        with c.Tox() as tox1:
            with c.Tox() as tox2:
                tox1.friend_add(tox2.address, b"hello there!")
                tox2.friend_add_norequest(tox1.public_key)
                with self.assertRaises(common.LengthException):
                    tox2.friend_add(tox1.public_key, b"oh no!")

    def test_invalid_bootstrap(self) -> None:
        with c.Tox() as tox:
            with self.assertRaises(c.BootstrapError) as e:
                tox.bootstrap("invalid-host", 1234, bytes(c.PUBLIC_KEY_SIZE))
            self.assertEqual(e.exception.code,
                             c.BootstrapError.Code.BAD_HOST)

    def test_bootstrap_checks_key_length(self) -> None:
        with c.Tox() as tox:
            with self.assertRaises(common.LengthException):
                tox.bootstrap("localhost", 1234, bytes(c.PUBLIC_KEY_SIZE - 1))

    def test_friend_delete(self) -> None:
        with c.Tox() as tox1:
            with c.Tox() as tox2:
                friend = tox1.friend_add(tox2.address, b"hello there!")
                tox1.friend_delete(friend)
                with self.assertRaises(c.ApiException):
                    # Deleting again: we don't have that friend anymore.
                    tox1.friend_delete(friend)

    def test_udp_port_fails_when_udp_disabled(self) -> None:
        with c.Options() as opts:
            opts.udp_enabled = False
            with c.Tox(opts) as tox:
                with self.assertRaises(c.GetPortError) as e:
                    print(tox.udp_port)
                self.assertEqual(e.exception.code,
                                 c.GetPortError.Code.NOT_BOUND)

    def test_tcp_port_fails_when_tcp_disabled(self) -> None:
        with c.Options() as opts:
            opts.tcp_port = 0
            with c.Tox(opts) as tox:
                with self.assertRaises(c.GetPortError) as e:
                    print(tox.tcp_port)
                self.assertEqual(e.exception.code,
                                 c.GetPortError.Code.NOT_BOUND)

    def test_tcp_port(self) -> None:
        with c.Options() as opts:
            opts.tcp_port = 1234
            with c.Tox(opts) as tox:
                self.assertEqual(tox.tcp_port, 1234)

    def test_freed_options_raises_uaf(self) -> None:
        with c.Options() as opts:
            pass
        with self.assertRaises(common.UseAfterFreeException):
            c.Tox(opts)

    def test_double_init_rejected(self) -> None:
        with c.Tox() as tox:
            with self.assertRaises(RuntimeError):
                tox.__init__()  # type: ignore[misc]

    def test_exact_key_lengths_and_nul_host(self) -> None:
        with c.Tox() as tox:
            with self.assertRaises(common.LengthException):
                tox.bootstrap("localhost", 1234, bytes(c.PUBLIC_KEY_SIZE + 1))
            with self.assertRaises(ValueError):
                tox.bootstrap("bad\x00host", 1234, bytes(c.PUBLIC_KEY_SIZE))
            with self.assertRaises(ValueError):
                tox.add_tcp_relay("bad\x00host", 1234, bytes(c.PUBLIC_KEY_SIZE))
            with self.assertRaises(common.LengthException):
                tox.friend_by_public_key(bytes(c.PUBLIC_KEY_SIZE + 1))

    def test_invalid_enum_rejected(self) -> None:
        with c.Tox() as tox:
            with self.assertRaises(ValueError):
                tox.status = 99  # type: ignore[assignment]
            with self.assertRaises(ValueError):
                tox.file_control(0, 0, 99)  # type: ignore[arg-type]
            with self.assertRaises(ValueError):
                tox.friend_send_message(0, 99, b"hi")  # type: ignore[arg-type]

    def test_conference_get_id_missing_raises(self) -> None:
        with c.Tox() as tox:
            with self.assertRaises(KeyError):
                tox.conference_get_id(c.ConferenceNumber(999))

    def test_file_kind_enum(self) -> None:
        self.assertEqual(int(c.FileKind.DATA), 0)
        self.assertEqual(int(c.FileKind.AVATAR), 1)

    def test_events_match(self) -> None:
        event: events.Event = events.FriendMessageEvent(
            c.FriendNumber(1), c.MessageType.NORMAL, b"hi")
        match event:
            case events.FriendMessageEvent(friend_number=n, message=message):
                self.assertEqual((n, message), (1, b"hi"))
            case _:
                self.fail(f"not a message: {event}")
        with c.Tox() as t:
            self.assertEqual(t.iterate(), [])

if __name__ == "__main__":
    unittest.main()
