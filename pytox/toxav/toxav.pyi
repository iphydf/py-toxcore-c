from array import array
from pytox import common
from pytox.toxav import events
from pytox.toxcore.tox import FriendNumber
from pytox.toxcore.tox import Tox
from types import TracebackType
from typing import Self
import enum

class AvCallControl(enum.IntEnum):
    RESUME = 0
    PAUSE = 1
    CANCEL = 2
    MUTE_AUDIO = 3
    UNMUTE_AUDIO = 4
    HIDE_VIDEO = 5
    SHOW_VIDEO = 6

class AvAnswerError(ApiException):
    class Code(enum.IntEnum):
        SYNC = 1
        CODEC_INITIALIZATION = 2
        FRIEND_NOT_FOUND = 3
        FRIEND_NOT_CALLING = 4
        INVALID_BIT_RATE = 5
    code: AvAnswerError.Code

class AvBitRateSetError(ApiException):
    class Code(enum.IntEnum):
        SYNC = 1
        INVALID_BIT_RATE = 2
        FRIEND_NOT_FOUND = 3
        FRIEND_NOT_IN_CALL = 4
    code: AvBitRateSetError.Code

class AvCallError(ApiException):
    class Code(enum.IntEnum):
        MALLOC = 1
        SYNC = 2
        FRIEND_NOT_FOUND = 3
        FRIEND_NOT_CONNECTED = 4
        FRIEND_ALREADY_IN_CALL = 5
        INVALID_BIT_RATE = 6
    code: AvCallError.Code

class AvCallControlError(ApiException):
    class Code(enum.IntEnum):
        SYNC = 1
        FRIEND_NOT_FOUND = 2
        FRIEND_NOT_IN_CALL = 3
        INVALID_TRANSITION = 4
    code: AvCallControlError.Code

class AvNewError(ApiException):
    class Code(enum.IntEnum):
        NULL = 1
        MALLOC = 2
        MULTIPLE = 3
    code: AvNewError.Code

class AvSendFrameError(ApiException):
    class Code(enum.IntEnum):
        NULL = 1
        FRIEND_NOT_FOUND = 2
        FRIEND_NOT_IN_CALL = 3
        SYNC = 4
        INVALID = 5
        PAYLOAD_TYPE_DISABLED = 6
        RTP_FAILED = 7
    code: AvSendFrameError.Code

class AvFriendCallState(enum.IntFlag):
    NONE = 0
    ERROR = 1
    FINISHED = 2
    SENDING_A = 4
    SENDING_V = 8
    ACCEPTING_A = 16
    ACCEPTING_V = 32

class ApiException(common.ApiException): ...

class ToxAv:
    def __enter__(self) -> Self: ...
    def __exit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None, exc_traceback: TracebackType | None) -> None: ...
    def __init__(self, tox: Tox) -> None: ...
    @property
    def iteration_interval(self) -> int: ...
    def iterate(self) -> list[events.Event]: ...
    def call(self, friend_number: FriendNumber, audio_bit_rate: int, video_bit_rate: int) -> None: ...
    def answer(self, friend_number: FriendNumber, audio_bit_rate: int, video_bit_rate: int) -> None: ...
    def call_control(self, friend_number: FriendNumber, control: AvCallControl) -> None: ...
    def audio_send_frame(self, friend_number: FriendNumber, pcm: array[int], channels: int, sampling_rate: int) -> None: ...
    def audio_set_bit_rate(self, friend_number: FriendNumber, bit_rate: int) -> None: ...
    def video_send_frame(self, friend_number: FriendNumber, width: int, height: int, y: bytes, u: bytes, v: bytes) -> None: ...
    def video_set_bit_rate(self, friend_number: FriendNumber, bit_rate: int) -> None: ...
