import unittest
from typing import Callable
from typing import cast
from typing import TypeVar

import pytox.toxav.toxav as av
from pytox.toxcore import tox

T = TypeVar("T")


class AvTest(unittest.TestCase):

    @staticmethod
    def _tolerant(fn: Callable[[], T]) -> None:
        # Call-dependent operations fail without an active call; the binding
        # code path is still exercised.
        try:
            fn()
        except av.ApiException:
            pass

    def test_version(self) -> None:
        with self.assertRaises(av.ApiException) as ex:
            av.ToxAV_Ptr(cast(tox.Tox_Ptr, None))
        self.assertEqual(ex.exception.code,
                         av.Toxav_Err_New.TOXAV_ERR_NEW_NULL)

    def test_iterate(self) -> None:
        with tox.Tox_Ptr() as t:
            with av.ToxAV_Ptr(t) as toxav:
                self.assertGreaterEqual(toxav.iteration_interval, 0)
                self.assertGreaterEqual(toxav.audio_iteration_interval, 0)
                self.assertGreaterEqual(toxav.video_iteration_interval, 0)
                toxav.iterate()
                toxav.audio_iterate()
                toxav.video_iterate()


if __name__ == "__main__":
    unittest.main()
