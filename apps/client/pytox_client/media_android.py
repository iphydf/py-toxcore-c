# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""Sound and cameras for calls on Android, through PyTox's Java support.

The Java side (android_support/aar) waits for the microphone, the speaker and
the camera; Python threads wait in it, and pyjnius lets go of the GIL while
they do.
"""
from __future__ import annotations

import logging
import struct
import threading
from typing import Any
from typing import Callable
from typing import Optional

from pytox_client.media import Playout
from pytox_client.media import VideoFrame

_LOG = logging.getLogger("pytox")


def support(name: str) -> Any:
    """One of PyTox's Java support classes."""
    from jnius import autoclass
    return autoclass(f"chat.tox.pytox.support.{name}")


class AndroidSound:
    """A call's sound: the microphone, and the earpiece or loudspeaker."""

    def __init__(self, context: Any, recorded: Callable[[bytes], None],
                 playout: Playout) -> None:
        self._java = support("CallSound")(context)
        self._running = True
        self._threads = [
            threading.Thread(target=self._record,
                             args=(recorded, ),
                             name="pytox-microphone",
                             daemon=True),
            threading.Thread(target=self._play,
                             args=(playout, ),
                             name="pytox-speaker",
                             daemon=True),
        ]
        for thread in self._threads:
            thread.start()

    def _record(self, recorded: Callable[[bytes], None]) -> None:
        try:
            while self._running:
                pcm = self._java.record()
                if pcm is None:
                    return
                recorded(pcm.tostring())
        except Exception:  # noqa: BLE001
            if self._running:
                _LOG.exception("microphone thread failed")

    def _play(self, playout: Playout) -> None:
        try:
            while self._running:
                frame = playout.next()
                self._java.play(frame.pcm, frame.rate, frame.channels)
        except Exception:  # noqa: BLE001
            if self._running:
                _LOG.exception("speaker thread failed")

    def set_speaker(self, on: bool) -> None:
        self._java.setSpeaker(on)

    def close(self) -> None:
        self._running = False
        self._java.close()
        for thread in self._threads:
            thread.join(timeout=2.0)
        self._java.release()


class AndroidCamera:
    """A phone camera, giving upright pictures on a thread of its own."""

    def __init__(self, java: Any, frame: Callable[[VideoFrame], None]) -> None:
        self._java = java
        self._thread = threading.Thread(target=self._run,
                                        args=(frame, ),
                                        name="pytox-camera",
                                        daemon=True)
        self._thread.start()

    @staticmethod
    def open(context: Any, front: bool,
             frame: Callable[[VideoFrame], None]) -> Optional[AndroidCamera]:
        java = support("CallCamera").open(context, front)
        if java is None:
            return None
        return AndroidCamera(java, frame)

    def _run(self, frame: Callable[[VideoFrame], None]) -> None:
        try:
            while True:
                picture = self._java.take()
                if picture is None:
                    return
                data = picture.tostring()
                if len(data) < 8:
                    continue
                width, height = struct.unpack_from(">ii", data)
                if width <= 0 or height <= 0:
                    continue
                needed = width * height + (width * height) // 2
                if len(data) - 8 < needed:
                    continue
                frame(VideoFrame.packed(width, height, data[8:]))
        except Exception:  # noqa: BLE001
            _LOG.exception("camera thread failed")

    def close(self) -> None:
        self._java.close()
        self._thread.join(timeout=2.0)


def camera_count(context: Any) -> int:
    return int(support("CallCamera").count(context))


def has_earpiece(context: Any) -> bool:
    return bool(support("CallSound").hasEarpiece(context))
