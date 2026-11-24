# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""What calls send and play: sound frames, pictures, and the ringing tones.

Sound is 16-bit little-endian PCM in ``bytes``, as Android's ``byte[]`` and
toxav's ``array("h")`` turn into it cheaply. Pictures are I420 in ``bytes``,
so a frame can go to other threads (and processes) as it is.
"""
from __future__ import annotations

import enum
import math
import threading
import time
from array import array
from collections import deque
from dataclasses import dataclass
from dataclasses import replace
from typing import Optional

# What calls record: 20 ms frames of 48 kHz mono.
AUDIO_RATE = 48000
AUDIO_FRAME = AUDIO_RATE // 50

# What cameras are asked for: phones turn it to 480 × 640.
VIDEO_WIDTH = 640
VIDEO_HEIGHT = 480

# At most this many pictures a second go out: each one takes the Tox thread a
# while to encode.
VIDEO_FPS = 24


@dataclass(frozen=True)
class VideoFrame:
    """A picture in I420.

    ``y`` has ``width`` × ``height`` samples, ``u`` and ``v`` half as many each
    way, in rows of the given strides. The pictures we send have even sizes.
    """

    width: int
    height: int
    y: bytes
    u: bytes
    v: bytes
    y_stride: int
    u_stride: int
    v_stride: int
    # Shown mirrored: the user's own front camera, so it moves the way a
    # mirror does.
    mirrored: bool = False

    @staticmethod
    def packed(width: int, height: int, data: bytes) -> VideoFrame:
        """A frame from its three planes one after the other, without gaps."""
        luma = width * height
        chroma = luma // 4
        return VideoFrame(width, height, data[:luma],
                          data[luma:luma + chroma],
                          data[luma + chroma:luma + 2 * chroma], width,
                          width // 2, width // 2)

    def mirror(self) -> VideoFrame:
        return replace(self, mirrored=True)


def yuyv_to_i420(data: bytes, width: int, height: int,
                 stride: int) -> VideoFrame:
    """A YUYV picture (Y0 U Y1 V for each two pixels) as I420.

    An odd last column or row is left out. Each chroma sample is the top row's
    of the two it covers: slicing does it at C speed, where averaging would
    take a Python loop over every sample.
    """
    w = width & ~1
    h = height & ~1
    if stride == 2 * w:
        y = data[:2 * w * h:2]
    else:
        y = b"".join(data[j * stride:j * stride + 2 * w:2] for j in range(h))
    rows = [data[j * stride:j * stride + 2 * w] for j in range(0, h, 2)]
    u = b"".join(row[1::4] for row in rows)
    v = b"".join(row[3::4] for row in rows)
    return VideoFrame(w, h, y, u, v, w, w // 2, w // 2)


class FrameGate:
    """Lets through at most ``fps`` pictures a second, evenly.

    A 30 a second camera gives 24, not every other one.
    """

    def __init__(self, fps: int = VIDEO_FPS) -> None:
        if fps <= 0:
            raise ValueError("fps must be positive")
        self._interval = 1.0 / fps
        self._next: Optional[float] = None

    def open(self, now: Optional[float] = None) -> bool:
        now = time.monotonic() if now is None else now
        if self._next is None:
            self._next = now + self._interval
            return True
        if now < self._next:
            return False
        self._next = max(self._next + self._interval, now)
        return True


@dataclass(frozen=True)
class SoundFrame:
    """One frame of sound to play."""

    pcm: bytes
    channels: int
    rate: int

    @property
    def seconds(self) -> float:
        if self.channels <= 0 or self.rate <= 0:
            return 0.0
        return len(self.pcm) / 2 / self.channels / self.rate


def silence(samples: int = AUDIO_FRAME,
            channels: int = 1,
            rate: int = AUDIO_RATE) -> SoundFrame:
    return SoundFrame(bytes(2 * samples * channels), channels, rate)


class Tone(enum.Enum):
    """The tones while a call rings, at :data:`AUDIO_RATE`.

    Each is its frequencies and its cadence: milliseconds on and off, over and
    over.
    """

    # The caller hears this until the friend answers: Europe's 425 Hz, a
    # second on and four off.
    RINGBACK = ((425.0, ), (1000, 4000))
    # The desktop rings with this: two short chimes, then a pause.
    RING = ((660.0, 880.0), (300, 150, 300, 2000))

    def samples(self) -> bytes:
        """One whole cadence: it plays round and round."""
        cached = _TONES.get(self)
        if cached is not None:
            return cached
        hertz, cadence = self.value
        pcm = array("h")
        for i, length in enumerate(cadence):
            count = length * AUDIO_RATE // 1000
            if i % 2 == 1:
                pcm.frombytes(bytes(2 * count))
                continue
            hz = hertz[i // 2 % len(hertz)]
            step = 2 * math.pi * hz / AUDIO_RATE
            pcm.extend(
                int(math.sin(step * n) * _TONE_VOLUME) for n in range(count))
        _TONES[self] = array_to_pcm(pcm)
        return _TONES[self]


_TONE_VOLUME = 6000
_TONES: dict[Tone, bytes] = {}


class Playout:
    """The friend's sound on its way to the speaker.

    Frames come in bursts (the Tox thread also encodes video), so it keeps a
    few in hand and plays silence while it fills up again. The speaker's
    thread calls :meth:`next` each time it has room for a frame; its device's
    buffer sets the pace.
    """

    # In frames of 20 ms: start once 60 ms are here, and keep at most 200.
    START_FRAMES = 3
    TARGET_FRAMES = 4
    MAX_FRAMES = 10

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frames: deque[SoundFrame] = deque()
        self._filling = True
        self._tone: Optional[Tone] = None
        self._tone_at = 0

    def set_tone(self, tone: Optional[Tone]) -> None:
        """The tone to play instead, while a call rings."""
        with self._lock:
            self._tone = tone
            self._tone_at = 0

    def clear(self) -> None:
        """Drop buffered audio frames and any active tone (between calls)."""
        with self._lock:
            self._frames.clear()
            self._filling = True
            self._tone = None
            self._tone_at = 0

    def add(self, frame: SoundFrame) -> None:
        with self._lock:
            self._frames.append(frame)
            # Too far behind: drop the oldest, so the delay doesn't grow.
            if len(self._frames) > self.MAX_FRAMES:
                for _ in range(len(self._frames) - self.TARGET_FRAMES):
                    self._frames.popleft()

    def next(self) -> SoundFrame:
        """The next frame to play: the friend's sound, a tone, or silence."""
        with self._lock:
            if self._tone is not None:
                cycle = self._tone.samples()
                start = self._tone_at
                end = start + 2 * AUDIO_FRAME
                pcm = cycle[start:end]
                if end > len(cycle):
                    end -= len(cycle)
                    pcm += cycle[:end]
                self._tone_at = end
                return SoundFrame(pcm, 1, AUDIO_RATE)
            if self._filling and len(self._frames) >= self.START_FRAMES:
                self._filling = False
            if self._filling or not self._frames:
                self._filling = True
                like = self._frames[0] if self._frames else None
                if like is None:
                    return silence()
                return SoundFrame(bytes(len(like.pcm)), like.channels,
                                  like.rate)
            return self._frames.popleft()


def pcm_to_array(pcm: bytes) -> array[int]:
    """Sound bytes as toxav takes them."""
    samples = array("h")
    samples.frombytes(pcm)
    if _BIG_ENDIAN:
        samples.byteswap()
    return samples


def array_to_pcm(samples: array[int]) -> bytes:
    """Sound from toxav as bytes."""
    if _BIG_ENDIAN:
        samples = array("h", samples)
        samples.byteswap()
    return samples.tobytes()


_BIG_ENDIAN = array("h", [1]).tobytes() != b"\x01\x00"
