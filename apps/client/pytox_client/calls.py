# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""Calls with friends, one at a time, over toxav.

They belong to the Tox thread like the rest of :class:`ToxClient`: the
platform records and films on threads of its own and hands the frames over
with ``post``.
"""
from __future__ import annotations

import threading
import time
from array import array
from dataclasses import replace
from typing import Callable
from typing import Optional

import pytox.toxav.toxav as av
from pytox.toxav import events as av_events
import pytox.toxcore.tox as core

from pytox_client.media import array_to_pcm
from pytox_client.media import AUDIO_RATE
from pytox_client.media import pcm_to_array
from pytox_client.media import Playout
from pytox_client.media import SoundFrame
from pytox_client.media import Tone
from pytox_client.media import VideoFrame
from pytox_client.model import Call
from pytox_client.model import CallNote
from pytox_client.model import CallOutcome
from pytox_client.model import Friend
from pytox_client.model import SHORT_KEY
from pytox_client.platform_base import CallSound
from pytox_client.platform_base import Closeable
from pytox_client.platform_base import Platform
from pytox_client.profiles import CallLine

# In kbit/s: Opus speech is clear at this; VP8 starts at 1000 and follows
# toxav between the others.
AUDIO_BIT_RATE = 48
START_VIDEO_BIT_RATE = 1000
MIN_VIDEO_BIT_RATE = 150
MAX_VIDEO_BIT_RATE = 1500

# The video bit rate goes up a tenth each time it has gone this long without
# toxav asking for less.
_RAISE_EVERY_MS = 5_000
_LOG_EVERY_MS = 5_000

# An unanswered call stops ringing after a minute.
RING_TIMEOUT_MS = 60_000

# 200 ms of sound.
_MAX_QUEUED_SOUND = 10

FRIEND = "friend"
SELF = "self"

VideoListener = Callable[[str, Optional[VideoFrame]], None]


def _now_ms() -> int:
    return int(time.time() * 1000)


def _mono_ms() -> int:
    return int(time.monotonic() * 1000)


class CallVideo:
    """The pictures of the call: the friend's newest, and ours as it goes out.

    They change too often for the client's state, so they have listeners of
    their own: each gets ``(FRIEND or SELF, frame or None)``, on whichever
    thread the picture came on, and should only keep it.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frames: dict[str, Optional[VideoFrame]] = {
            FRIEND: None,
            SELF: None
        }
        self._listeners: list[VideoListener] = []

    def watch(self, listener: VideoListener) -> Callable[[], None]:
        with self._lock:
            self._listeners.append(listener)
            frames = dict(self._frames)
        for who, frame in frames.items():
            if frame is not None:
                listener(who, frame)

        def unwatch() -> None:
            with self._lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return unwatch

    def show(self, who: str, frame: Optional[VideoFrame]) -> None:
        with self._lock:
            if frame is None and self._frames[who] is None:
                return
            self._frames[who] = frame
            listeners = list(self._listeners)
        for listener in listeners:
            listener(who, frame)


class _Stats:
    """How a call goes, for the log.

    What went out and came in, how long encoding took, and how long the Tox
    thread kept frames waiting. ``filmed`` and ``sound_dropped`` are counted
    on the platform's threads (under the lock), the rest on the Tox thread.
    """

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.filmed = 0
        self.sound_dropped = 0
        self.sound_received = 0
        self.pictures_received = 0
        self.pictures_sent = 0
        self.sound_sent = 0
        self.encoding = 0.0
        self.longest_encoding = 0.0
        self.longest_picture_wait = 0.0
        self.longest_sound_wait = 0.0
        self.since = time.monotonic()

    def take(self, video_bit_rate: int) -> str:
        """The line for the time since the last one; counting starts again."""
        sent = self.pictures_sent
        with self.lock:
            filmed, self.filmed = self.filmed, 0
            dropped, self.sound_dropped = self.sound_dropped, 0
        line = (f"call {time.monotonic() - self.since:.0f} s: sent {sent} of "
                f"{filmed} pictures ({video_bit_rate} kbit/s), encoding "
                f"{self.encoding / sent * 1000 if sent else 0:.0f} ms each, "
                f"at most {self.longest_encoding * 1000:.0f}, waited at most "
                f"{self.longest_picture_wait * 1000:.0f} ms; sent "
                f"{self.sound_sent} sound frames, dropped {dropped}, waited "
                f"at most {self.longest_sound_wait * 1000:.0f} ms; got "
                f"{self.pictures_received} pictures, {self.sound_received} "
                f"sound frames")
        self.sound_received = 0
        self.pictures_received = 0
        self.pictures_sent = 0
        self.sound_sent = 0
        self.encoding = 0.0
        self.longest_encoding = 0.0
        self.longest_picture_wait = 0.0
        self.longest_sound_wait = 0.0
        self.since = time.monotonic()
        return line


class Calls:
    """Calls over toxav, one at a time over all profiles in the process.

    Everything but the frame hand-overs is Tox thread.
    """

    def __init__(
        self,
        platform: Platform,
        profile: str,
        line: CallLine,
        post: Callable[[Callable[[], None]], None],
        number: Callable[[str], Optional[core.FriendNumber]],
        key: Callable[[core.FriendNumber], Optional[str]],
        friend: Callable[[str], Optional[Friend]],
        changed: Callable[[], None],
        ended: Callable[[Call, CallNote], None],
    ) -> None:
        """``post`` runs a function on the Tox thread; a call takes ``line``
        for ``profile`` while it lasts.

        ``changed`` says the call changed, for the client to show it;
        ``ended`` that one ended, for the client to note it in the chat.
        """
        self._platform = platform
        self._profile = profile
        self._line = line
        self._post = post
        self._number = number
        self._key = key
        self._friend = friend
        self._changed = changed
        self._ended = ended
        self._av: Optional[av.ToxAv] = None
        self.call: Optional[Call] = None
        self.video = CallVideo()
        # Counts calls, so frames recorded for one that ended don't go into
        # the next.
        self._session = 0
        self._sound: Optional[CallSound] = None
        self._camera: Optional[Closeable] = None
        self._playout = Playout()
        self._ringing_since = 0
        self._answered_mono_ms = 0
        # The video bit rate now, which follows what toxav says the network
        # takes, and since when.
        self._video_bit_rate = START_VIDEO_BIT_RATE
        self._video_bit_rate_since = 0
        self._stats = _Stats()
        self._last_log = 0
        # Frames recorded and not sent yet: when the Tox thread falls behind,
        # newer ones are dropped.
        self._handover = threading.Lock()
        self._queued_sound = 0
        # The newest picture to send and when it was filmed, while the Tox
        # thread hasn't sent it: older ones are dropped.
        self._next_picture: Optional[tuple[int, VideoFrame, float]] = None

    @property
    def iteration_interval(self) -> int:
        """Milliseconds until toxav wants to run again."""
        return self._av.iteration_interval if self._av is not None else 1 << 30

    def start(self, tox: core.Tox) -> None:
        self._av = av.ToxAv(tox)

    def stop(self) -> None:
        """Before Tox stops: the call can't go on without it."""
        try:
            self.hang_up()
        finally:
            if self._av is not None:
                toxav, self._av = self._av, None
                toxav.__exit__(None, None, None)

    def _on_event(self, event: av_events.Event) -> None:
        match event:
            case av_events.CallEvent(friend_number=n,
                                     audio_enabled=audio,
                                     video_enabled=video):
                self._on_call(n, audio, video)
            case av_events.CallStateEvent(friend_number=n, state=state):
                self._on_call_state(n, state)
            case av_events.VideoBitRateEvent(friend_number=n,
                                             video_bit_rate=bit_rate):
                self._on_video_bit_rate(n, bit_rate)
            case av_events.AudioReceiveFrameEvent(friend_number=n,
                                                  pcm=pcm,
                                                  channels=channels,
                                                  sampling_rate=rate):
                self._on_sound(n, pcm, channels, rate)
            case av_events.VideoReceiveFrameEvent(
                    friend_number=n, width=width, height=height, y=y, u=u,
                    v=v):
                # The planes come packed.
                if width > 0 and height > 0:
                    self._on_picture(
                        n,
                        VideoFrame(width, height, y, u, v, width,
                                   (width + 1) // 2, (width + 1) // 2))

    def iterate(self) -> None:
        if self._av is None:
            return
        for event in self._av.iterate():
            self._on_event(event)
        call = self.call
        if call is None:
            return
        now = _mono_ms()
        if call.ringing and now - self._ringing_since > RING_TIMEOUT_MS:
            self._cancel(call.friend)
            self._end(CallOutcome.MISSED)
            return
        if (call.answered and call.video
                and self._video_bit_rate < MAX_VIDEO_BIT_RATE
                and now - self._video_bit_rate_since >= _RAISE_EVERY_MS):
            # Back up slowly once the network has kept up for a while.
            next_rate = (MIN_VIDEO_BIT_RATE if self._video_bit_rate == 0
                         else max(self._video_bit_rate + 1,
                                  self._video_bit_rate * 11 // 10))
            self._set_video_bit_rate(min(MAX_VIDEO_BIT_RATE, next_rate))
        if call.answered and now - self._last_log >= _LOG_EVERY_MS:
            if self._last_log:
                self._platform.log(self._stats.take(self._video_bit_rate))
            self._last_log = now

    def start_call(self, friend: str, video: bool) -> None:
        current = self.call
        if current is not None:
            # Calling back someone who is calling us answers them.
            if (current.friend == friend and not current.outgoing
                    and current.ringing):
                self.answer(video)
            return
        number = self._number(friend)
        if (number is None or self._av is None
                or not self._line.take(self._profile)):
            return
        try:
            self._av.call(number, AUDIO_BIT_RATE,
                          START_VIDEO_BIT_RATE if video else 0)
        except av.ApiException as exc:
            self._line.release(self._profile)
            self._platform.log(f"couldn't call {friend[:SHORT_KEY]}: {exc}")
            return
        self._begin(
            Call(friend, outgoing=True, video_call=video, video=video,
                 speaker=video))
        self._playout.set_tone(Tone.RINGBACK)
        self._start_sound()
        if video:
            self._start_camera()

    def answer(self, video: bool) -> None:
        current = self.call
        if current is None or current.outgoing or not current.ringing:
            return
        number = self._number(current.friend)
        if number is None or self._av is None:
            return
        try:
            self._av.answer(number, AUDIO_BIT_RATE,
                            START_VIDEO_BIT_RATE if video else 0)
        except av.ApiException:
            self._end(CallOutcome.MISSED)
            return
        self._playout.set_tone(None)
        self._answered_mono_ms = _mono_ms()
        self._update(
            replace(current, answered=True, started=_now_ms(), video=video,
                    speaker=video))
        self._start_sound()
        if video:
            self._start_camera()

    def hang_up(self) -> None:
        """End the call, or say no to one that rings."""
        current = self.call
        if current is None:
            return
        self._cancel(current.friend)
        if current.answered:
            self._end(CallOutcome.ANSWERED)
        elif current.outgoing:
            self._end(CallOutcome.MISSED)
        else:
            self._end(CallOutcome.DECLINED)

    def set_muted(self, muted: bool) -> None:
        current = self.call
        if current is None:
            return
        self._update(replace(current, muted=muted))
        if current.answered:
            self._set_bit_rates()

    def set_video(self, on: bool) -> None:
        current = self.call
        if current is None or current.video == on:
            return
        self._update(replace(current, video=on, problem=None))
        if on:
            self._start_camera()
        else:
            self._stop_camera()
        if current.answered:
            self._set_bit_rates()

    def switch_camera(self) -> None:
        current = self.call
        if current is None:
            return
        self._update(replace(current, front_camera=not current.front_camera))
        if self._camera is not None:
            self._stop_camera()
            self._start_camera()

    def set_speaker(self, on: bool) -> None:
        current = self.call
        if current is None:
            return
        if self._sound is not None:
            self._sound.set_speaker(on)
        self._update(replace(current, speaker=on))

    def friend_gone(self, friend: str) -> None:
        """The friend went offline: toxav may not say so for a while."""
        current = self.call
        if current is None or current.friend != friend:
            return
        self._cancel(friend)
        self._end(CallOutcome.ANSWERED if current.answered else CallOutcome.
                  MISSED)

    def _begin(self, call: Call) -> None:
        self._session += 1
        self._ringing_since = _mono_ms()
        self._answered_mono_ms = 0
        self._video_bit_rate = START_VIDEO_BIT_RATE
        self._video_bit_rate_since = self._ringing_since
        self._last_log = 0
        self._stats.take(self._video_bit_rate)
        self._platform.log(
            f"call {'to' if call.outgoing else 'from'} "
            f"{call.friend[:SHORT_KEY]}, video {call.video_call}")
        self._update(call)

    def _update(self, call: Call) -> None:
        self.call = call
        self._platform.call_changed(
            self._profile, call, self._friend(call.friend))
        self._changed()

    def _set_bit_rates(self) -> None:
        """Tell toxav what we send now: none of what's muted or off."""
        current = self.call
        if current is None or self._av is None:
            return
        number = self._number(current.friend)
        if number is None:
            return
        try:
            self._av.audio_set_bit_rate(
                number, 0 if current.muted else AUDIO_BIT_RATE)
        except av.ApiException:
            pass
        try:
            self._av.video_set_bit_rate(
                number, self._video_bit_rate if current.video else 0)
        except av.ApiException:
            # The call is ending: toxav says so next.
            pass

    def _set_video_bit_rate(self, rate: int) -> None:
        self._video_bit_rate = rate
        self._video_bit_rate_since = _mono_ms()
        current = self.call
        if (current is None or not current.answered or not current.video
                or self._av is None):
            return
        number = self._number(current.friend)
        if number is None:
            return
        try:
            self._av.video_set_bit_rate(number, rate)
        except av.ApiException:
            # The call is ending: toxav says so next.
            pass

    def _cancel(self, friend: str) -> None:
        number = self._number(friend)
        if number is None or self._av is None:
            return
        try:
            self._av.call_control(number, av.AvCallControl.CANCEL)
        except av.ApiException:
            # Gone already.
            pass

    def _end(self, outcome: CallOutcome) -> None:
        current = self.call
        if current is None:
            return
        self.call = None
        self._line.release(self._profile)
        self._session += 1
        if self._sound is not None:
            self._sound.close()
            self._sound = None
        self._stop_camera()
        self._playout.clear()
        self.video.show(FRIEND, None)
        seconds = (max(0, (_mono_ms() - self._answered_mono_ms) // 1000)
                   if current.answered else 0)
        if current.answered:
            self._platform.log(self._stats.take(self._video_bit_rate))
        self._platform.log(f"call ended: {outcome.name} after {seconds} s")
        self._ended(current, CallNote(current.video_call, outcome, seconds))
        self._platform.call_changed(self._profile, None, None)
        self._changed()

    def _start_sound(self) -> None:
        session = self._session

        def recorded(pcm: bytes) -> None:
            self._recorded(session, pcm)

        self._sound = self._platform.open_sound(recorded, self._playout)
        call = self.call
        if call is None:
            return
        if self._sound is None:
            self._update(
                replace(call,
                        problem="There's no microphone or speaker the app "
                        "can use."))
        else:
            self._sound.set_speaker(call.speaker)

    def _start_camera(self) -> None:
        call = self.call
        if call is None:
            return
        session = self._session
        front = call.front_camera

        def filmed(frame: VideoFrame) -> None:
            self._filmed(session, frame, front)

        self._camera = self._platform.open_camera(front, filmed)
        if self._camera is None:
            self._update(
                replace(call, video=False,
                        problem="There's no camera the app can use."))
            if call.answered:
                self._set_bit_rates()

    def _stop_camera(self) -> None:
        if self._camera is not None:
            self._camera.close()
            self._camera = None
        with self._handover:
            self._next_picture = None
        self.video.show(SELF, None)

    def _recorded(self, session: int, pcm: bytes) -> None:
        """On the microphone's thread."""
        with self._handover:
            if self._queued_sound >= _MAX_QUEUED_SOUND:
                with self._stats.lock:
                    self._stats.sound_dropped += 1
                return
            self._queued_sound += 1
        recorded_at = time.monotonic()

        def send() -> None:
            with self._handover:
                self._queued_sound -= 1
            call = self.call
            if (call is None or session != self._session or not call.answered
                    or call.muted or self._av is None):
                return
            number = self._number(call.friend)
            if number is None:
                return
            stats = self._stats
            stats.sound_sent += 1
            stats.longest_sound_wait = max(stats.longest_sound_wait,
                                           time.monotonic() - recorded_at)
            samples = pcm_to_array(pcm)
            try:
                self._av.audio_send_frame(number, samples, 1, AUDIO_RATE)
            except av.ApiException:
                # The friend doesn't take sound now.
                pass

        self._post(send)

    def _filmed(self, session: int, frame: VideoFrame, front: bool) -> None:
        """On the camera's thread."""
        if session != self._session:
            return
        self.video.show(SELF, frame.mirror() if front else frame)
        with self._stats.lock:
            self._stats.filmed += 1
        with self._handover:
            waiting = self._next_picture is not None
            self._next_picture = (session, frame, time.monotonic())
        if not waiting:
            self._post(self._send_picture)

    def _send_picture(self) -> None:
        with self._handover:
            picture, self._next_picture = self._next_picture, None
        if picture is None:
            return
        session, frame, filmed_at = picture
        call = self.call
        if (call is None or session != self._session or not call.answered
                or not call.video or self._av is None):
            return
        number = self._number(call.friend)
        if number is None:
            return
        start = time.monotonic()
        try:
            self._av.video_send_frame(number, frame.width, frame.height,
                                      frame.y, frame.u, frame.v)
        except av.ApiException:
            # The friend doesn't take video now.
            pass
        encoded = time.monotonic() - start
        stats = self._stats
        stats.pictures_sent += 1
        stats.encoding += encoded
        stats.longest_encoding = max(stats.longest_encoding, encoded)
        stats.longest_picture_wait = max(stats.longest_picture_wait,
                                         start - filmed_at)

    # toxav's events, on the Tox thread.

    def _on_call(self, friend_number: core.FriendNumber, audio: bool, video: bool) -> None:
        friend = self._key(friend_number)
        if friend is None:
            return
        if self.call is not None and self.call.friend == friend:
            # Call glare with the same friend: keep our outgoing attempt alive
            # instead of cancelling our own call slot.
            return
        if self.call is not None or not self._line.take(self._profile):
            # One call at a time, here or in another profile: they hear that
            # it wasn't answered.
            self._cancel(friend)
            self._ended(Call(friend, outgoing=False, video_call=video),
                        CallNote(video, CallOutcome.MISSED, 0))
            return
        self._begin(
            Call(friend, outgoing=False, video_call=video, friend_audio=audio,
                 friend_video=video))

    def _on_call_state(self, friend_number: core.FriendNumber, state: int) -> None:
        current = self.call
        if current is None or current.friend != self._key(friend_number):
            return
        flags = av.AvFriendCallState(state)
        if flags & (av.AvFriendCallState.FINISHED | av.AvFriendCallState.ERROR):
            if current.answered:
                self._end(CallOutcome.ANSWERED)
            elif current.outgoing and (flags & av.AvFriendCallState.FINISHED):
                self._end(CallOutcome.DECLINED)
            else:
                self._end(CallOutcome.MISSED)
            return
        sending = replace(
            current,
            friend_audio=bool(flags & av.AvFriendCallState.SENDING_A),
            friend_video=bool(flags & av.AvFriendCallState.SENDING_V),
        )
        if not sending.friend_video:
            self.video.show(FRIEND, None)
        if current.answered:
            self._update(sending)
            return
        # Only transition ringing -> answered automatically for outgoing calls
        # when the peer answers; incoming calls require our explicit answer().
        if not current.outgoing:
            self._update(sending)
            return
        # They answered ours.
        self._playout.set_tone(None)
        self._answered_mono_ms = _mono_ms()
        self._update(replace(sending, answered=True, started=_now_ms()))
        self._set_bit_rates()

    def _on_video_bit_rate(self, friend_number: core.FriendNumber, rate: int) -> None:
        """The network can't keep up: toxav asks for less."""
        if self.call is None or self.call.friend != self._key(friend_number):
            return
        self._platform.log(f"toxav asks for {rate} kbit/s of video")
        if rate <= 0:
            self._set_video_bit_rate(0)
            return
        self._set_video_bit_rate(
            min(max(rate, MIN_VIDEO_BIT_RATE), MAX_VIDEO_BIT_RATE))

    def _on_sound(self, friend_number: core.FriendNumber, pcm: array[int], channels: int,
                  rate: int) -> None:
        if self.call is None or self.call.friend != self._key(friend_number):
            return
        self._stats.sound_received += 1
        self._playout.add(SoundFrame(array_to_pcm(pcm), channels, rate))

    def _on_picture(self, friend_number: core.FriendNumber, frame: VideoFrame) -> None:
        if self.call is None or self.call.friend != self._key(friend_number):
            return
        self._stats.pictures_received += 1
        self.video.show(FRIEND, frame)
