import gc
import threading
import time
import unittest
import weakref
from array import array
from typing import Callable
from typing import cast
from typing import TypeVar

import pytox.toxav.toxav as av
from pytox import common
from pytox.toxcore import tox

T = TypeVar("T")


# Subclasses take weak references.
class _Tox(tox.Tox):
    pass


class _Av(av.ToxAv):
    pass


class AvTest(unittest.TestCase):

    @staticmethod
    def _tolerant(fn: Callable[[], T]) -> None:
        # Call-dependent operations fail without an active call; the binding
        # code path is still exercised.
        try:
            fn()
        except av.ApiException:
            pass

    def test_needs_tox(self) -> None:
        with self.assertRaises(TypeError):
            av.ToxAv(cast(tox.Tox, None))

    def test_iterate(self) -> None:
        with tox.Tox() as t:
            with av.ToxAv(t) as toxav:
                self.assertGreaterEqual(toxav.iteration_interval, 0)
                self.assertEqual(toxav.iterate(), [])

    def test_exit_tox_closes_attached_toxav(self) -> None:
        # Exiting Tox before ToxAv must close ToxAv first instead of aborting.
        t = tox.Tox()
        a = av.ToxAv(t)
        t.__exit__(None, None, None)
        with self.assertRaises(common.UseAfterFreeException):
            a.iterate()
        a.__exit__(None, None, None)

    def test_gc_order_keeps_tox_alive(self) -> None:
        a = av.ToxAv(tox.Tox())
        gc.collect()
        a.iterate()
        a.__exit__(None, None, None)

    def test_toxav_lives_until_tox_closes_it(self) -> None:
        # Dropped, it isn't freed in one of Tox's callbacks, under Tox's lock.
        t = tox.Tox()
        a = weakref.ref(_Av(t))
        gc.collect()
        self.assertIsNotNone(a())
        t.__exit__(None, None, None)
        self.assertIsNone(a())

    def test_gc_frees_toxav_with_its_tox(self) -> None:
        t = _Tox()
        a = weakref.ref(_Av(t))
        w = weakref.ref(t)
        del t
        gc.collect()
        self.assertIsNone(a())
        self.assertIsNone(w())

    def test_freed_tox_raises_uaf(self) -> None:
        with tox.Tox() as t:
            pass
        with self.assertRaises(common.UseAfterFreeException):
            av.ToxAv(t)

    def test_send_frame_validation(self) -> None:
        with tox.Tox() as t:
            with av.ToxAv(t) as a:
                with self.assertRaises(ValueError):
                    a.call_control(tox.FriendNumber(0), 99)  # type: ignore[arg-type]
                with self.assertRaises(av.ApiException):
                    a.audio_send_frame(tox.FriendNumber(0), array("h"), 1, 48000)
                # Whole frames only: 3 samples can't be stereo.
                with self.assertRaises(common.LengthException):
                    a.audio_send_frame(tox.FriendNumber(0), array("h", [0] * 3), 2, 48000)
                with self.assertRaises(common.LengthException):
                    a.audio_send_frame(tox.FriendNumber(0), array("h"), 0, 48000)
                with self.assertRaises(common.LengthException):
                    a.video_send_frame(tox.FriendNumber(0), 4, 4, b"", b"", b"")
                with self.assertRaises(OverflowError):
                    a.video_send_frame(tox.FriendNumber(0), 70000, 4, b"", b"", b"")
                # Odd sizes round down, as C reads them: 2x2 for 5x5.
                with self.assertRaises(common.LengthException):
                    a.video_send_frame(tox.FriendNumber(0), 5, 5, bytes(25),
                                       bytes(3), bytes(4))
                with self.assertRaises(av.ApiException):
                    a.video_send_frame(tox.FriendNumber(0), 5, 5, bytes(25),
                                       bytes(4), bytes(4))
                with self.assertRaises(RuntimeError):
                    a.__init__(t)  # type: ignore[misc]

    def test_friend_call_state_flags(self) -> None:
        self.assertEqual(int(av.AvFriendCallState.NONE), 0)
        self.assertEqual(int(av.AvFriendCallState.ERROR), 1)
        self.assertEqual(int(av.AvFriendCallState.FINISHED), 2)
        self.assertEqual(int(av.AvFriendCallState.SENDING_A), 4)
        self.assertEqual(int(av.AvFriendCallState.SENDING_V), 8)

    def test_threads_share_tox_and_toxav(self) -> None:
        # The loops, calls and getters each on a thread of their own; closing
        # Tox from another ends them all.
        t = tox.Tox()
        a = av.ToxAv(t)
        errors: list[BaseException] = []

        def run(step: Callable[[], object]) -> None:
            try:
                while True:
                    step()
            except common.UseAfterFreeException:
                pass
            except BaseException as e:  # noqa: BLE001
                errors.append(e)

        steps: list[Callable[[], object]] = [
            t.iterate,
            a.iterate,
            lambda: self._tolerant(lambda: a.call(tox.FriendNumber(0), 48, 0)),
            lambda: t.name,
        ]
        threads = [threading.Thread(target=run, args=(s, )) for s in steps]
        for th in threads:
            th.start()
        time.sleep(0.2)
        t.__exit__(None, None, None)
        for th in threads:
            th.join(5)
        self.assertEqual([th for th in threads if th.is_alive()], [])
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
