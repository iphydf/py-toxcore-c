import unittest
from typing import cast

import pytox.toxcore.tox as c
from pytox import common


class ToxOptionsTest(unittest.TestCase):

    def test_options(self) -> None:
        opts = c.Options()

        self.assertTrue(opts.ipv6_enabled)
        opts.ipv6_enabled = False
        self.assertFalse(opts.ipv6_enabled)

        self.assertTrue(opts.udp_enabled)
        opts.udp_enabled = False
        self.assertFalse(opts.udp_enabled)

        self.assertTrue(opts.local_discovery_enabled)
        opts.local_discovery_enabled = False
        self.assertFalse(opts.local_discovery_enabled)

        self.assertTrue(opts.dht_announcements_enabled)
        opts.dht_announcements_enabled = False
        self.assertFalse(opts.dht_announcements_enabled)

        self.assertTrue(opts.hole_punching_enabled)
        opts.hole_punching_enabled = False
        self.assertFalse(opts.hole_punching_enabled)

        self.assertEqual(opts.proxy_type, c.ProxyType.NONE)
        opts.proxy_type = c.ProxyType.SOCKS5
        self.assertEqual(opts.proxy_type,
                         c.ProxyType.SOCKS5)

        opts.proxy_host = "localhost"
        self.assertEqual(opts.proxy_host, "localhost")

        opts.proxy_port = 1234
        self.assertEqual(opts.proxy_port, 1234)

        opts.start_port = 1235
        self.assertEqual(opts.start_port, 1235)

        opts.end_port = 1236
        self.assertEqual(opts.end_port, 1236)

        opts.tcp_port = 1237
        self.assertEqual(opts.tcp_port, 1237)

        opts.savedata_type = c.SavedataType.TOX_SAVE
        self.assertEqual(opts.savedata_type,
                         c.SavedataType.TOX_SAVE)

        opts.savedata = b"test"
        self.assertEqual(opts.savedata, b"test")

        self.assertFalse(opts.experimental_groups_persistence)
        opts.experimental_groups_persistence = True
        self.assertTrue(opts.experimental_groups_persistence)

    def test_use_after_free(self) -> None:
        with c.Options() as opts:
            pass
        with self.assertRaises(common.UseAfterFreeException):
            print(opts.ipv6_enabled)
        self.assertTrue(
            issubclass(common.UseAfterFreeException, common.PytoxException))

    def test_savedata_empty_and_default(self) -> None:
        with c.Options() as opts:
            self.assertEqual(opts.savedata, b"")
            opts.savedata = b"abc"
            self.assertEqual(opts.savedata, b"abc")
            opts.savedata = b""
            self.assertEqual(opts.savedata, b"")

    def test_copy_and_validation(self) -> None:
        with c.Options() as src, c.Options() as dst:
            src.proxy_host = "localhost"
            src.proxy_type = c.ProxyType.SOCKS5
            src.savedata = b"hello"
            dst.proxy_host = "old-host"
            dst.savedata = b"old-data"
            dst.copy(src)
            self.assertEqual(dst.proxy_host, "localhost")
            self.assertEqual(dst.savedata, b"hello")
            # Self-copy keeps owned buffers intact.
            dst.copy(dst)
            self.assertEqual(dst.proxy_host, "localhost")
            self.assertEqual(dst.savedata, b"hello")
        with c.Options() as dst:
            with self.assertRaises(common.UseAfterFreeException):
                dst.copy(src)
            with self.assertRaises(TypeError):
                dst.copy(cast(c.Options, None))
            with self.assertRaises(ValueError):
                dst.proxy_host = "bad\x00host"
            with self.assertRaises(ValueError):
                dst.proxy_type = 999  # type: ignore[assignment]
            with self.assertRaises(ValueError):
                dst.savedata_type = 999  # type: ignore[assignment]
            with self.assertRaises(RuntimeError):
                dst.__init__()  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
