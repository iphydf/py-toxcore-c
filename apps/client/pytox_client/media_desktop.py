# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""Sound and cameras for calls on desktops.

Sound goes through PortAudio (``sounddevice``); cameras are Linux V4L2
devices, read straight from the kernel in YUYV.
"""
from __future__ import annotations

import glob
import logging
import mmap
import os
import re
import select
import struct
import sys
import threading
from typing import Any
from typing import Callable
from typing import Optional

try:
    import fcntl as _fcntl
except ImportError:  # Windows has no fcntl.
    _fcntl = None  # type: ignore[assignment]

from pytox_client.media import AUDIO_FRAME
from pytox_client.media import AUDIO_RATE
from pytox_client.media import FrameGate
from pytox_client.media import Playout
from pytox_client.media import SoundFrame
from pytox_client.media import Tone
from pytox_client.media import VIDEO_HEIGHT
from pytox_client.media import VIDEO_WIDTH
from pytox_client.media import VideoFrame
from pytox_client.media import yuyv_to_i420

_LOG = logging.getLogger("pytox")


def _sounddevice() -> Any:
    """PortAudio, if it's here and has a device."""
    try:
        import sounddevice
    except (ImportError, OSError) as exc:
        _LOG.info("no sound: %s", exc)
        return None
    return sounddevice


class _Speaker:
    """Plays what a :class:`Playout` gives, on a thread of its own."""

    def __init__(self, sd: Any, playout: Playout) -> None:
        self._sd = sd
        self._playout = playout
        self._running = True
        self._stop_ev = threading.Event()
        self._stream_lock = threading.Lock()
        self._stream: Any = None
        self._thread = threading.Thread(target=self._run,
                                        name="pytox-speaker",
                                        daemon=True)
        self._thread.start()

    def _run(self) -> None:
        stream: Any = None
        shape = (0, 0)
        try:
            while self._running:
                frame = self._playout.next()
                if (frame.rate, frame.channels) != shape:
                    self._close_stream(stream)
                    shape = (frame.rate, frame.channels)
                    stream = self._open(frame)
                    with self._stream_lock:
                        self._stream = stream
                if stream is None:
                    delay = frame.seconds if frame.seconds > 0 else 0.02
                    self._stop_ev.wait(delay)
                    continue
                # Blocks until the device has room: its buffer sets the pace.
                try:
                    stream.write(frame.pcm)
                except Exception as exc:  # noqa: BLE001
                    if self._running:
                        _LOG.info("speaker write failed: %s", exc)
                    self._close_stream(stream)
                    stream = None
                    with self._stream_lock:
                        self._stream = None
                    shape = (0, 0)
                    self._stop_ev.wait(0.05)
        finally:
            self._close_stream(stream)
            with self._stream_lock:
                self._stream = None

    @staticmethod
    def _close_stream(stream: Any) -> None:
        if stream is None:
            return
        try:
            stream.close()
        except Exception:  # noqa: BLE001
            pass

    def _open(self, frame: SoundFrame) -> Any:
        try:
            stream = self._sd.RawOutputStream(samplerate=frame.rate,
                                              channels=frame.channels,
                                              dtype="int16",
                                              latency="low")
            stream.start()
            return stream
        except Exception as exc:  # noqa: BLE001
            _LOG.info("no speaker for %d Hz, %d channels: %s", frame.rate,
                      frame.channels, exc)
            return None

    def close(self) -> None:
        self._running = False
        self._stop_ev.set()
        with self._stream_lock:
            stream = self._stream
        if stream is not None:
            try:
                stream.abort()
            except Exception:  # noqa: BLE001
                pass
        self._thread.join(timeout=2.0)


class DesktopSound:
    """A call's sound: the default microphone (optional) and speaker."""

    def __init__(self, sd: Any, recorded: Callable[[bytes], None],
                 playout: Playout) -> None:
        self._recorded = recorded
        self._running = True
        self._mic: Any = None
        self._thread: Optional[threading.Thread] = None
        try:
            mic = sd.RawInputStream(samplerate=AUDIO_RATE,
                                    channels=1,
                                    dtype="int16",
                                    blocksize=AUDIO_FRAME,
                                    latency="low")
            try:
                mic.start()
            except Exception:
                mic.close()
                raise
            self._mic = mic
            self._thread = threading.Thread(target=self._record,
                                            name="pytox-microphone",
                                            daemon=True)
            self._thread.start()
        except Exception as exc:  # noqa: BLE001
            _LOG.info("no microphone (speaker only): %s", exc)
        self._speaker = _Speaker(sd, playout)

    @staticmethod
    def open(recorded: Callable[[bytes], None],
             playout: Playout) -> Optional[DesktopSound]:
        sd = _sounddevice()
        if sd is None:
            return None
        try:
            return DesktopSound(sd, recorded, playout)
        except Exception as exc:  # noqa: BLE001
            _LOG.info("no sound device: %s", exc)
            return None

    def _record(self) -> None:
        mic = self._mic
        while self._running and mic is not None:
            try:
                data, _overflowed = mic.read(AUDIO_FRAME)
            except Exception:  # noqa: BLE001
                return
            if not self._running:
                return
            self._recorded(bytes(data))

    def set_speaker(self, on: bool) -> None:
        del on

    def close(self) -> None:
        self._running = False
        mic, self._mic = self._mic, None
        if mic is not None:
            try:
                mic.abort()
            except Exception:  # noqa: BLE001
                pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if mic is not None:
            try:
                mic.close()
            except Exception:  # noqa: BLE001
                pass
        self._speaker.close()


class Ringer:
    """Rings the speaker while a call comes in."""

    def __init__(self) -> None:
        self._speaker: Optional[_Speaker] = None

    def ring(self, on: bool) -> None:
        if on and self._speaker is None:
            sd = _sounddevice()
            if sd is not None:
                playout = Playout()
                playout.set_tone(Tone.RING)
                self._speaker = _Speaker(sd, playout)
        elif not on and self._speaker is not None:
            self._speaker.close()
            self._speaker = None


# From linux/videodev2.h, for 64-bit Linux.
_VIDIOC_QUERYCAP = 0x80685600
_VIDIOC_S_FMT = 0xC0D05605
_VIDIOC_REQBUFS = 0xC0145608
_VIDIOC_QUERYBUF = 0xC0585609
_VIDIOC_QBUF = 0xC058560F
_VIDIOC_DQBUF = 0xC0585611
_VIDIOC_STREAMON = 0x40045612
_VIDIOC_STREAMOFF = 0x40045613
_CAPABILITY_SIZE = 104
_CAPS_AT = 84
_DEVICE_CAPS_AT = 88
_CAP_VIDEO_CAPTURE = 0x1
_CAP_STREAMING = 0x4000000
_CAP_DEVICE_CAPS = 0x80000000
_FORMAT_SIZE = 208
_PIX_AT = 8
_BUFFER_SIZE = 88
_BYTESUSED_AT = 8
_MEMORY_AT = 60
_OFFSET_AT = 64
_LENGTH_AT = 72
_BUF_TYPE_VIDEO_CAPTURE = 1
_MEMORY_MMAP = 1
_PIX_FMT_YUYV = 0x56595559
_BUFFERS = 4


# V4L2 ioctl structs/codes below match 64-bit little-endian Linux only.
_V4L2_SUPPORTED = (
    _fcntl is not None
    and sys.platform.startswith("linux")
    and struct.calcsize("P") == 8
    and sys.byteorder == "little"
)


def _video_sort_key(path: str) -> tuple[int, str]:
    match = re.search(r"(\d+)$", path)
    return (int(match.group(1)) if match else 1 << 30, path)


def _can_film(path: str) -> bool:
    if not _V4L2_SUPPORTED or _fcntl is None:
        return False
    try:
        fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
    except OSError:
        return False
    try:
        cap = bytearray(_CAPABILITY_SIZE)
        _fcntl.ioctl(fd, _VIDIOC_QUERYCAP, cap)
        caps, device_caps = struct.unpack_from("<II", cap, _CAPS_AT)
        if caps & _CAP_DEVICE_CAPS:
            caps = device_caps
        return bool(caps & _CAP_VIDEO_CAPTURE and caps & _CAP_STREAMING)
    except OSError:
        return False
    finally:
        os.close(fd)


def camera_paths() -> list[str]:
    """The devices that film, in order (a webcam often has two nodes)."""
    if not _V4L2_SUPPORTED:
        return []
    paths = sorted(glob.glob("/dev/video*"), key=_video_sort_key)
    return [p for p in paths if _can_film(p)]


def _buffer(index: int = 0) -> bytearray:
    buf = bytearray(_BUFFER_SIZE)
    struct.pack_into("<III", buf, 0, index, _BUF_TYPE_VIDEO_CAPTURE, 0)
    struct.pack_into("<I", buf, _MEMORY_AT, _MEMORY_MMAP)
    return buf


class V4l2Camera:
    """A V4L2 camera filming YUYV, giving I420 pictures on its thread."""

    def __init__(self, path: str, frame: Callable[[VideoFrame], None]) -> None:
        if not _V4L2_SUPPORTED or _fcntl is None:
            raise OSError("V4L2 cameras require 64-bit little-endian Linux")
        self._fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
        self._maps: list[mmap.mmap] = []
        self._closed = False
        try:
            self._start()
        except BaseException:
            self._stop()
            raise
        self._frame = frame
        self._gate = FrameGate()
        self._running = True
        self._thread = threading.Thread(target=self._run,
                                        name="pytox-camera",
                                        daemon=True)
        self._thread.start()

    def _start(self) -> None:
        assert _fcntl is not None
        fmt = bytearray(_FORMAT_SIZE)
        struct.pack_into("<I", fmt, 0, _BUF_TYPE_VIDEO_CAPTURE)
        struct.pack_into("<IIII", fmt, _PIX_AT, VIDEO_WIDTH, VIDEO_HEIGHT,
                         _PIX_FMT_YUYV, 0)
        _fcntl.ioctl(self._fd, _VIDIOC_S_FMT, fmt)
        (self._width, self._height, pixels, _field,
         stride) = struct.unpack_from("<IIIII", fmt, _PIX_AT)
        if pixels != _PIX_FMT_YUYV:
            raise OSError("the camera doesn't film YUYV")
        self._stride = stride if stride >= self._width * 2 else self._width * 2
        req = bytearray(20)
        struct.pack_into("<III", req, 0, _BUFFERS, _BUF_TYPE_VIDEO_CAPTURE,
                         _MEMORY_MMAP)
        _fcntl.ioctl(self._fd, _VIDIOC_REQBUFS, req)
        count = struct.unpack_from("<I", req, 0)[0]
        if count == 0:
            raise OSError("the camera has no buffers")
        for i in range(count):
            buf = _buffer(i)
            _fcntl.ioctl(self._fd, _VIDIOC_QUERYBUF, buf)
            offset = struct.unpack_from("<I", buf, _OFFSET_AT)[0]
            length = struct.unpack_from("<I", buf, _LENGTH_AT)[0]
            self._maps.append(
                mmap.mmap(self._fd, length, mmap.MAP_SHARED,
                          mmap.PROT_READ, offset=offset))
            _fcntl.ioctl(self._fd, _VIDIOC_QBUF, buf)
        _fcntl.ioctl(self._fd, _VIDIOC_STREAMON,
                     struct.pack("<I", _BUF_TYPE_VIDEO_CAPTURE))

    def _run(self) -> None:
        assert _fcntl is not None
        poller = select.poll()
        poller.register(self._fd, select.POLLIN)
        while self._running:
            try:
                ready = poller.poll(200)
            except OSError:
                return
            if not ready:
                continue
            buf = _buffer()
            try:
                _fcntl.ioctl(self._fd, _VIDIOC_DQBUF, buf)
            except BlockingIOError:
                continue
            except OSError as exc:
                _LOG.info("camera stopped: %s", exc)
                return
            index = struct.unpack_from("<I", buf, 0)[0]
            used = struct.unpack_from("<I", buf, _BYTESUSED_AT)[0]
            if index >= len(self._maps):
                continue
            data = self._maps[index][:used] if self._gate.open() else None
            try:
                _fcntl.ioctl(self._fd, _VIDIOC_QBUF, buf)
            except OSError:
                return
            if data is not None and len(data) >= self._stride * self._height:
                self._frame(
                    yuyv_to_i420(data, self._width, self._height,
                                 self._stride))

    def _stop(self) -> None:
        if self._fd < 0:
            return
        fd, self._fd = self._fd, -1
        if _fcntl is not None:
            try:
                _fcntl.ioctl(fd, _VIDIOC_STREAMOFF,
                             struct.pack("<I", _BUF_TYPE_VIDEO_CAPTURE))
            except OSError:
                pass
        for m in self._maps:
            m.close()
        self._maps = []
        os.close(fd)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._running = False
        self._thread.join(timeout=2.0)
        self._stop()

    @staticmethod
    def open(front: bool,
             frame: Callable[[VideoFrame], None]) -> Optional[V4l2Camera]:
        """The first camera: desktops have one, facing the user."""
        del front
        for path in camera_paths():
            try:
                return V4l2Camera(path, frame)
            except OSError as exc:
                _LOG.info("camera %s: %s", path, exc)
        return None
