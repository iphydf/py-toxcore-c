from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import Union

if TYPE_CHECKING:
    from array import array
    from pytox.toxav.toxav import AvFriendCallState
    from pytox.toxcore.tox import FriendNumber


@dataclass(frozen=True, slots=True)
class CallEvent:
    friend_number: FriendNumber
    audio_enabled: bool
    video_enabled: bool


@dataclass(frozen=True, slots=True)
class CallStateEvent:
    friend_number: FriendNumber
    state: AvFriendCallState


@dataclass(frozen=True, slots=True)
class AudioBitRateEvent:
    friend_number: FriendNumber
    audio_bit_rate: int


@dataclass(frozen=True, slots=True)
class VideoBitRateEvent:
    friend_number: FriendNumber
    video_bit_rate: int


@dataclass(frozen=True, slots=True)
class AudioReceiveFrameEvent:
    friend_number: FriendNumber
    pcm: array[int]
    channels: int
    sampling_rate: int


@dataclass(frozen=True, slots=True)
class VideoReceiveFrameEvent:
    friend_number: FriendNumber
    width: int
    height: int
    y: bytes
    u: bytes
    v: bytes


Event = Union[
    CallEvent,
    CallStateEvent,
    AudioBitRateEvent,
    VideoBitRateEvent,
    AudioReceiveFrameEvent,
    VideoReceiveFrameEvent,
]
