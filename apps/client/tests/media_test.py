# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""Tests for avatars, QR codes, Kivy imports, and calls' sound and pictures."""
from __future__ import annotations

import os
import unittest
from io import BytesIO

from pytox_client.media import AUDIO_FRAME
from pytox_client.media import FrameGate
from pytox_client.media import Playout
from pytox_client.media import SoundFrame
from pytox_client.media import Tone
from pytox_client.media import yuyv_to_i420
from pytox_client.platform_desktop import encode_avatar_png
from pytox_client.qr import make_qr_matrix
from pytox_client.qr import make_qr_png


class MediaTest(unittest.TestCase):

    def test_encode_avatar_png_crops_and_downscales(self) -> None:
        from PIL import Image

        src = Image.new("RGB", (600, 400), color=(43, 106, 143))
        buf = BytesIO()
        src.save(buf, format="JPEG")
        encoded = encode_avatar_png(buf.getvalue(), size=256)
        self.assertIsNotNone(encoded)
        assert encoded is not None
        out = Image.open(BytesIO(encoded))
        self.assertEqual(out.format, "PNG")
        self.assertEqual(out.size, (256, 256))

        self.assertIsNone(encode_avatar_png(b"not an image", size=256))

    def test_qr_matrix_and_png(self) -> None:
        tox_uri = "tox:" + "A" * 76
        matrix = make_qr_matrix(tox_uri)
        self.assertIsNotNone(matrix)
        assert matrix is not None
        size = len(matrix)
        self.assertGreater(size, 25)
        self.assertTrue(all(len(row) == size for row in matrix))
        # Quiet border is all light (False).
        self.assertFalse(any(matrix[0]))
        self.assertFalse(any(matrix[-1]))

        png = make_qr_png(tox_uri, scale=4)
        self.assertIsNotNone(png)
        assert png is not None
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_kivy_importable_without_display(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["KIVY_HOME"] = tmp
            os.environ.setdefault("KIVY_NO_ARGS", "1")
            os.environ.setdefault("KIVY_NO_CONSOLELOG", "1")
            os.environ.setdefault("KIVY_NO_FILELOG", "1")
            import kivy
            self.assertTrue(hasattr(kivy, "__version__"))

    def test_yuyv_to_i420(self) -> None:
        # 4 × 2 pixels, rows padded to 10 bytes: Y0 U Y1 V for each two.
        rows = [bytes([1, 50, 2, 60, 3, 51, 4, 61, 0, 0]),
                bytes([5, 70, 6, 80, 7, 71, 8, 81, 0, 0])]
        frame = yuyv_to_i420(b"".join(rows), 4, 2, 10)
        self.assertEqual((frame.width, frame.height), (4, 2))
        self.assertEqual(frame.y, bytes([1, 2, 3, 4, 5, 6, 7, 8]))
        self.assertEqual((frame.u, frame.v), (bytes([50, 51]), bytes([60, 61])))
        # An odd last column and row are left out.
        odd = yuyv_to_i420(bytes(range(5 * 2 * 3)), 5, 3, 10)
        self.assertEqual((odd.width, odd.height, len(odd.y)), (4, 2, 8))

    def test_playout(self) -> None:
        playout = Playout()
        frame = SoundFrame(b"\x01\x00" * AUDIO_FRAME, 1, 48000)
        # It waits for a few frames before it plays, then plays them in turn.
        for _ in range(Playout.START_FRAMES - 1):
            playout.add(frame)
            self.assertFalse(any(playout.next().pcm))
        playout.add(frame)
        self.assertEqual(playout.next(), frame)
        # Too far behind: the oldest go.
        behind = Playout()
        for _ in range(Playout.MAX_FRAMES + 1):
            behind.add(frame)
        played = 0
        while any(behind.next().pcm):
            played += 1
        self.assertEqual(played, Playout.TARGET_FRAMES)
        # A tone goes round and round, a frame at a time.
        playout.set_tone(Tone.RING)
        cycle = Tone.RING.samples()
        heard = b"".join(playout.next().pcm
                         for _ in range(len(cycle) // (2 * AUDIO_FRAME) + 1))
        self.assertEqual(heard[:len(cycle)], cycle)
        self.assertEqual(heard[len(cycle):], cycle[:len(heard) - len(cycle)])
        playout.clear()
        self.assertFalse(any(playout.next().pcm))

    def test_frame_gate_and_sound_frame_edge_cases(self) -> None:
        with self.assertRaises(ValueError):
            FrameGate(0)
        with self.assertRaises(ValueError):
            FrameGate(-10)
        gate = FrameGate(10)
        self.assertTrue(gate.open(1.0))
        self.assertFalse(gate.open(1.05))
        self.assertTrue(gate.open(1.11))
        self.assertEqual(SoundFrame(b"", 0, 48000).seconds, 0.0)
        self.assertEqual(SoundFrame(b"", 1, 0).seconds, 0.0)


if __name__ == "__main__":
    unittest.main()
