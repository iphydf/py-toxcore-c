# cython: language_level=3, linetrace=True
cimport cython
from array import array
from cpython cimport array as c_array
from cpython.bytes cimport PyBytes_FromStringAndSize, PyBytes_AS_STRING
from enum import IntEnum, IntFlag
from libc.string cimport memcpy
from pytox import common
from pytox.toxav import events
from cpython.pythread cimport PyThread_allocate_lock, PyThread_free_lock, PyThread_acquire_lock, PyThread_release_lock, WAIT_LOCK
from types import TracebackType
from typing import TypeVar
from pytox.toxcore.tox cimport CTox, Tox
T = TypeVar("T")

cdef bytes _copy_plane(const uint8_t* ptr, size_t width, size_t height, int32_t stride):
    if ptr is NULL or width == 0 or height == 0:
        return b""
    if stride == <Py_ssize_t> width:
        return PyBytes_FromStringAndSize(<const char*> ptr, width * height)
    cdef bytes out = PyBytes_FromStringAndSize(NULL, width * height)
    cdef char* dst = PyBytes_AS_STRING(out)
    cdef size_t row
    for row in range(height):
        memcpy(dst + row * width, ptr + (<Py_ssize_t> row) * stride, width)
    return out

cdef c_array.array _copy_int16_t(const int16_t* data, size_t count):
    cdef c_array.array out = c_array.clone(array("h"), count, zero=False)
    if count != 0:
        memcpy(out.data.as_voidptr, data, count * sizeof(int16_t))
    return out


class ApiException(common.ApiException):
    pass

AvCallControl = IntEnum("AvCallControl", [
    ("RESUME", TOXAV_CALL_CONTROL_RESUME),
    ("PAUSE", TOXAV_CALL_CONTROL_PAUSE),
    ("CANCEL", TOXAV_CALL_CONTROL_CANCEL),
    ("MUTE_AUDIO", TOXAV_CALL_CONTROL_MUTE_AUDIO),
    ("UNMUTE_AUDIO", TOXAV_CALL_CONTROL_UNMUTE_AUDIO),
    ("HIDE_VIDEO", TOXAV_CALL_CONTROL_HIDE_VIDEO),
    ("SHOW_VIDEO", TOXAV_CALL_CONTROL_SHOW_VIDEO),
], module=__name__)

class AvAnswerError(ApiException):
    Code = IntEnum("Code", [
        ("SYNC", TOXAV_ERR_ANSWER_SYNC),
        ("CODEC_INITIALIZATION", TOXAV_ERR_ANSWER_CODEC_INITIALIZATION),
        ("FRIEND_NOT_FOUND", TOXAV_ERR_ANSWER_FRIEND_NOT_FOUND),
        ("FRIEND_NOT_CALLING", TOXAV_ERR_ANSWER_FRIEND_NOT_CALLING),
        ("INVALID_BIT_RATE", TOXAV_ERR_ANSWER_INVALID_BIT_RATE),
    ], module=__name__, qualname="AvAnswerError.Code")

class AvBitRateSetError(ApiException):
    Code = IntEnum("Code", [
        ("SYNC", TOXAV_ERR_BIT_RATE_SET_SYNC),
        ("INVALID_BIT_RATE", TOXAV_ERR_BIT_RATE_SET_INVALID_BIT_RATE),
        ("FRIEND_NOT_FOUND", TOXAV_ERR_BIT_RATE_SET_FRIEND_NOT_FOUND),
        ("FRIEND_NOT_IN_CALL", TOXAV_ERR_BIT_RATE_SET_FRIEND_NOT_IN_CALL),
    ], module=__name__, qualname="AvBitRateSetError.Code")

class AvCallError(ApiException):
    Code = IntEnum("Code", [
        ("MALLOC", TOXAV_ERR_CALL_MALLOC),
        ("SYNC", TOXAV_ERR_CALL_SYNC),
        ("FRIEND_NOT_FOUND", TOXAV_ERR_CALL_FRIEND_NOT_FOUND),
        ("FRIEND_NOT_CONNECTED", TOXAV_ERR_CALL_FRIEND_NOT_CONNECTED),
        ("FRIEND_ALREADY_IN_CALL", TOXAV_ERR_CALL_FRIEND_ALREADY_IN_CALL),
        ("INVALID_BIT_RATE", TOXAV_ERR_CALL_INVALID_BIT_RATE),
    ], module=__name__, qualname="AvCallError.Code")

class AvCallControlError(ApiException):
    Code = IntEnum("Code", [
        ("SYNC", TOXAV_ERR_CALL_CONTROL_SYNC),
        ("FRIEND_NOT_FOUND", TOXAV_ERR_CALL_CONTROL_FRIEND_NOT_FOUND),
        ("FRIEND_NOT_IN_CALL", TOXAV_ERR_CALL_CONTROL_FRIEND_NOT_IN_CALL),
        ("INVALID_TRANSITION", TOXAV_ERR_CALL_CONTROL_INVALID_TRANSITION),
    ], module=__name__, qualname="AvCallControlError.Code")

class AvNewError(ApiException):
    Code = IntEnum("Code", [
        ("NULL", TOXAV_ERR_NEW_NULL),
        ("MALLOC", TOXAV_ERR_NEW_MALLOC),
        ("MULTIPLE", TOXAV_ERR_NEW_MULTIPLE),
    ], module=__name__, qualname="AvNewError.Code")

class AvSendFrameError(ApiException):
    Code = IntEnum("Code", [
        ("NULL", TOXAV_ERR_SEND_FRAME_NULL),
        ("FRIEND_NOT_FOUND", TOXAV_ERR_SEND_FRAME_FRIEND_NOT_FOUND),
        ("FRIEND_NOT_IN_CALL", TOXAV_ERR_SEND_FRAME_FRIEND_NOT_IN_CALL),
        ("SYNC", TOXAV_ERR_SEND_FRAME_SYNC),
        ("INVALID", TOXAV_ERR_SEND_FRAME_INVALID),
        ("PAYLOAD_TYPE_DISABLED", TOXAV_ERR_SEND_FRAME_PAYLOAD_TYPE_DISABLED),
        ("RTP_FAILED", TOXAV_ERR_SEND_FRAME_RTP_FAILED),
    ], module=__name__, qualname="AvSendFrameError.Code")

AvFriendCallState = IntFlag("AvFriendCallState", [
    ("NONE", TOXAV_FRIEND_CALL_STATE_NONE),
    ("ERROR", TOXAV_FRIEND_CALL_STATE_ERROR),
    ("FINISHED", TOXAV_FRIEND_CALL_STATE_FINISHED),
    ("SENDING_A", TOXAV_FRIEND_CALL_STATE_SENDING_A),
    ("SENDING_V", TOXAV_FRIEND_CALL_STATE_SENDING_V),
    ("ACCEPTING_A", TOXAV_FRIEND_CALL_STATE_ACCEPTING_A),
    ("ACCEPTING_V", TOXAV_FRIEND_CALL_STATE_ACCEPTING_V),
], module=__name__)


cdef:
    cdef void handle_call(ToxAV* av, Tox_Friend_Number friend_number, bool audio_enabled, bool video_enabled, void* user_data) noexcept with gil:
        event = events.CallEvent(friend_number, audio_enabled, video_enabled)
        (<ToxAv> user_data)._events.append(event)
    cdef void handle_call_state(ToxAV* av, Tox_Friend_Number friend_number, uint32_t state, void* user_data) noexcept with gil:
        event = events.CallStateEvent(friend_number, AvFriendCallState(state))
        (<ToxAv> user_data)._events.append(event)
    cdef void handle_audio_bit_rate(ToxAV* av, Tox_Friend_Number friend_number, uint32_t audio_bit_rate, void* user_data) noexcept with gil:
        event = events.AudioBitRateEvent(friend_number, audio_bit_rate)
        (<ToxAv> user_data)._events.append(event)
    cdef void handle_video_bit_rate(ToxAV* av, Tox_Friend_Number friend_number, uint32_t video_bit_rate, void* user_data) noexcept with gil:
        event = events.VideoBitRateEvent(friend_number, video_bit_rate)
        (<ToxAv> user_data)._events.append(event)
    cdef void handle_audio_receive_frame(ToxAV* av, Tox_Friend_Number friend_number, const int16_t* pcm, size_t sample_count, uint8_t channels, uint32_t sampling_rate, void* user_data) noexcept with gil:
        event = events.AudioReceiveFrameEvent(friend_number, _copy_int16_t(pcm, sample_count * channels), channels, sampling_rate)
        (<ToxAv> user_data)._events.append(event)
    cdef void handle_video_receive_frame(ToxAV* av, Tox_Friend_Number friend_number, uint16_t width, uint16_t height, const uint8_t* y, const uint8_t* u, const uint8_t* v, int32_t ystride, int32_t ustride, int32_t vstride, void* user_data) noexcept with gil:
        event = events.VideoReceiveFrameEvent(friend_number, width, height, _copy_plane(y, width, height, ystride), _copy_plane(u, (width + 1) // 2, (height + 1) // 2, ustride), _copy_plane(v, (width + 1) // 2, (height + 1) // 2, vstride))
        (<ToxAv> user_data)._events.append(event)
    cdef void install_handlers(ToxAv self, ToxAV* ptr) noexcept:
        toxav_callback_call(ptr, handle_call, <void*> self)
        toxav_callback_call_state(ptr, handle_call_state, <void*> self)
        toxav_callback_audio_bit_rate(ptr, handle_audio_bit_rate, <void*> self)
        toxav_callback_video_bit_rate(ptr, handle_video_bit_rate, <void*> self)
        toxav_callback_audio_receive_frame(ptr, handle_audio_receive_frame, <void*> self)
        toxav_callback_video_receive_frame(ptr, handle_video_receive_frame, <void*> self)


@cython.no_gc_clear
cdef class ToxAv:
    cdef ToxAV* _get(self) except *:
        if self._ptr is NULL:
            raise common.UseAfterFreeException()
        return self._ptr

    def __cinit__(self):
        self._lock = PyThread_allocate_lock()
        if self._lock is NULL:
            raise MemoryError()
        self._events = []

    cdef int _acquire(self) except -1 nogil:
        PyThread_acquire_lock(self._lock, WAIT_LOCK)
        if self._ptr is NULL:
            PyThread_release_lock(self._lock)
            with gil:
                raise common.UseAfterFreeException()
        return 0

    cdef void _release(self) noexcept nogil:
        PyThread_release_lock(self._lock)

    cdef void _close(self) except *:
        if self._lock is NULL:
            return
        cdef ToxAV* ptr = NULL
        cdef Tox parent = self._tox
        cdef PyThread_type_lock parent_lock = NULL
        self._tox = None
        if parent is not None:
            parent._av = None
            parent_lock = parent._lock
        with nogil:
            if parent_lock is not NULL:
                PyThread_acquire_lock(parent_lock, WAIT_LOCK)
            PyThread_acquire_lock(self._lock, WAIT_LOCK)
            ptr = self._ptr
            self._ptr = NULL
            PyThread_release_lock(self._lock)
            if ptr is not NULL:
                toxav_kill(ptr)
            if parent_lock is not NULL:
                PyThread_release_lock(parent_lock)

    def __dealloc__(self) -> None:
        self._close()
        if self._lock is not NULL:
            PyThread_free_lock(self._lock)
            self._lock = NULL

    def __enter__(self: T) -> T:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None, exc_traceback: TracebackType | None) -> None:
        self._close()

    cdef ToxAV* _new(self, Tox tox):
        cdef Toxav_Err_New error = TOXAV_ERR_NEW_OK
        cdef CTox* tox_ptr = NULL
        cdef ToxAV* ptr = NULL
        with nogil:
            PyThread_acquire_lock(tox._lock, WAIT_LOCK)
            tox_ptr = tox._ptr
            if tox_ptr is not NULL:
                ptr = toxav_new(tox_ptr, &error)
                if ptr is not NULL:
                    self._ptr = ptr
                    with gil:
                        self._tox = tox
                        tox._av = self
                        install_handlers(self, self._ptr)
            PyThread_release_lock(tox._lock)
        if tox_ptr is NULL:
            raise common.UseAfterFreeException()
        if error:
            raise AvNewError(AvNewError.Code(error))
        return ptr

    def __init__(self, tox: Tox) -> None:
        if self._ptr is not NULL:
            raise RuntimeError("ToxAv can't be initialised twice")
        self._new(tox)

    @property
    def iteration_interval(self) -> int:
        cdef uint32_t res = <uint32_t> 0
        with nogil:
            self._acquire()
            res = toxav_iteration_interval(self._ptr)
            self._release()
        return res

    def iterate(self) -> list[events.Event]:
        with nogil:
            self._acquire()
            toxav_iterate(self._ptr)
            self._release()
        cdef object result = self._events
        self._events = []
        return result

    def call(self, friend_number: Tox_Friend_Number, audio_bit_rate: int, video_bit_rate: int) -> None:
        cdef uint32_t audio_bit_rate_c = audio_bit_rate
        cdef uint32_t video_bit_rate_c = video_bit_rate
        cdef Toxav_Err_Call err = TOXAV_ERR_CALL_OK
        with nogil:
            self._acquire()
            toxav_call(self._ptr, friend_number, audio_bit_rate_c, video_bit_rate_c, &err)
            self._release()
        if err:
            raise AvCallError(AvCallError.Code(err))

    def answer(self, friend_number: Tox_Friend_Number, audio_bit_rate: int, video_bit_rate: int) -> None:
        cdef uint32_t audio_bit_rate_c = audio_bit_rate
        cdef uint32_t video_bit_rate_c = video_bit_rate
        cdef Toxav_Err_Answer err = TOXAV_ERR_ANSWER_OK
        with nogil:
            self._acquire()
            toxav_answer(self._ptr, friend_number, audio_bit_rate_c, video_bit_rate_c, &err)
            self._release()
        if err:
            raise AvAnswerError(AvAnswerError.Code(err))

    def call_control(self, friend_number: Tox_Friend_Number, control: AvCallControl) -> None:
        cdef int control_val = AvCallControl(control)
        cdef Toxav_Err_Call_Control err = TOXAV_ERR_CALL_CONTROL_OK
        with nogil:
            self._acquire()
            toxav_call_control(self._ptr, friend_number, <Toxav_Call_Control> control_val, &err)
            self._release()
        if err:
            raise AvCallControlError(AvCallControlError.Code(err))

    def audio_send_frame(self, friend_number: Tox_Friend_Number, pcm: array, channels: int, sampling_rate: int) -> None:
        cdef uint8_t channels_c = channels
        cdef size_t sample_count_c = common.count_of("pcm", pcm, channels)
        cdef const int16_t[::1] pcm_arr = pcm
        cdef const int16_t* pcm_ptr = &pcm_arr[0] if pcm_arr.shape[0] > 0 else NULL
        cdef uint32_t sampling_rate_c = sampling_rate
        cdef Toxav_Err_Send_Frame err = TOXAV_ERR_SEND_FRAME_OK
        with nogil:
            self._acquire()
            toxav_audio_send_frame(self._ptr, friend_number, pcm_ptr, sample_count_c, channels_c, sampling_rate_c, &err)
            self._release()
        if err:
            raise AvSendFrameError(AvSendFrameError.Code(err))

    def audio_set_bit_rate(self, friend_number: Tox_Friend_Number, bit_rate: int) -> None:
        cdef uint32_t bit_rate_c = bit_rate
        cdef Toxav_Err_Bit_Rate_Set err = TOXAV_ERR_BIT_RATE_SET_OK
        with nogil:
            self._acquire()
            toxav_audio_set_bit_rate(self._ptr, friend_number, bit_rate_c, &err)
            self._release()
        if err:
            raise AvBitRateSetError(AvBitRateSetError.Code(err))

    def video_send_frame(self, friend_number: Tox_Friend_Number, width: int, height: int, y: bytes, u: bytes, v: bytes) -> None:
        cdef uint16_t width_c = width
        cdef uint16_t height_c = height
        common.check_len("y", y, width * height)
        common.check_len("u", u, (width // 2) * (height // 2))
        common.check_len("v", v, (width // 2) * (height // 2))
        cdef const uint8_t* y_ptr = y
        cdef const uint8_t* u_ptr = u
        cdef const uint8_t* v_ptr = v
        cdef Toxav_Err_Send_Frame err = TOXAV_ERR_SEND_FRAME_OK
        with nogil:
            self._acquire()
            toxav_video_send_frame(self._ptr, friend_number, width_c, height_c, y_ptr, u_ptr, v_ptr, &err)
            self._release()
        if err:
            raise AvSendFrameError(AvSendFrameError.Code(err))

    def video_set_bit_rate(self, friend_number: Tox_Friend_Number, bit_rate: int) -> None:
        cdef uint32_t bit_rate_c = bit_rate
        cdef Toxav_Err_Bit_Rate_Set err = TOXAV_ERR_BIT_RATE_SET_OK
        with nogil:
            self._acquire()
            toxav_video_set_bit_rate(self._ptr, friend_number, bit_rate_c, &err)
            self._release()
        if err:
            raise AvBitRateSetError(AvBitRateSetError.Code(err))
