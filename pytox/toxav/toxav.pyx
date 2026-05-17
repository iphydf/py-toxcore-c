# cython: language_level=3, linetrace=True
from array import array
from pytox import common
from types import TracebackType
from typing import Optional
from typing import TypeVar
from pytox.toxcore.tox cimport Tox_Ptr
T = TypeVar("T")


class ApiException(common.ApiException):
    pass


cdef:
    cdef void py_handle_call(self: ToxAV_Ptr, friend_number: int, audio_enabled: bool, video_enabled: bool) except *:
        self.handle_call(friend_number, audio_enabled, video_enabled)
    cdef void handle_call(ToxAV* av, uint32_t friend_number, bool audio_enabled, bool video_enabled, void* user_data) except *:
        py_handle_call(<ToxAV_Ptr> user_data, friend_number, audio_enabled, video_enabled)
    cdef void py_handle_call_state(self: ToxAV_Ptr, friend_number: int, state: int) except *:
        self.handle_call_state(friend_number, state)
    cdef void handle_call_state(ToxAV* av, uint32_t friend_number, uint32_t state, void* user_data) except *:
        py_handle_call_state(<ToxAV_Ptr> user_data, friend_number, state)
    cdef void py_handle_audio_bit_rate(self: ToxAV_Ptr, friend_number: int, audio_bit_rate: int) except *:
        self.handle_audio_bit_rate(friend_number, audio_bit_rate)
    cdef void handle_audio_bit_rate(ToxAV* av, uint32_t friend_number, uint32_t audio_bit_rate, void* user_data) except *:
        py_handle_audio_bit_rate(<ToxAV_Ptr> user_data, friend_number, audio_bit_rate)
    cdef void py_handle_video_bit_rate(self: ToxAV_Ptr, friend_number: int, video_bit_rate: int) except *:
        self.handle_video_bit_rate(friend_number, video_bit_rate)
    cdef void handle_video_bit_rate(ToxAV* av, uint32_t friend_number, uint32_t video_bit_rate, void* user_data) except *:
        py_handle_video_bit_rate(<ToxAV_Ptr> user_data, friend_number, video_bit_rate)
    cdef void py_handle_audio_receive_frame(self: ToxAV_Ptr, friend_number: int, pcm: array, sample_count: int, channels: int, sampling_rate: int) except *:
        self.handle_audio_receive_frame(friend_number, pcm, sample_count, channels, sampling_rate)
    cdef void handle_audio_receive_frame(ToxAV* av, uint32_t friend_number, const int16_t* pcm, size_t sample_count, uint8_t channels, uint32_t sampling_rate, void* user_data) except *:
        py_handle_audio_receive_frame(<ToxAV_Ptr> user_data, friend_number, array("h", [pcm[i] for i in range(sample_count * channels)]), sample_count, channels, sampling_rate)
    cdef void py_handle_video_receive_frame(self: ToxAV_Ptr, friend_number: int, width: int, height: int, y: bytes, u: bytes, v: bytes, ystride: int, ustride: int, vstride: int) except *:
        self.handle_video_receive_frame(friend_number, width, height, y, u, v, ystride, ustride, vstride)
    cdef void handle_video_receive_frame(ToxAV* av, uint32_t friend_number, uint16_t width, uint16_t height, const uint8_t* y, const uint8_t* u, const uint8_t* v, int32_t ystride, int32_t ustride, int32_t vstride, void* user_data) except *:
        py_handle_video_receive_frame(<ToxAV_Ptr> user_data, friend_number, width, height, y[:max(width, abs(ystride)) * height], u[:max(width // 2, abs(ustride)) * (height // 2)], v[:max(width // 2, abs(vstride)) * (height // 2)], ystride, ustride, vstride)
    cdef void install_handlers(ToxAV_Ptr self, ToxAV* ptr):
        toxav_callback_call(ptr, handle_call, <void*> self)
        toxav_callback_call_state(ptr, handle_call_state, <void*> self)
        toxav_callback_audio_bit_rate(ptr, handle_audio_bit_rate, <void*> self)
        toxav_callback_video_bit_rate(ptr, handle_video_bit_rate, <void*> self)
        toxav_callback_audio_receive_frame(ptr, handle_audio_receive_frame, <void*> self)
        toxav_callback_video_receive_frame(ptr, handle_video_receive_frame, <void*> self)


cdef class ToxAV_Ptr:
    cdef ToxAV* _get(self) except *:
        if self._ptr is NULL:
            raise common.UseAfterFreeException()
        return self._ptr

    def __del__(self) -> None:
        self.__exit__(None, None, None)

    def __enter__(self: T) -> T:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None, exc_traceback: TracebackType | None) -> None:
        toxav_kill(self._ptr)
        self._ptr = NULL

    cdef ToxAV* _new(self, Tox_Ptr tox):
        cdef Toxav_Err_New error = TOXAV_ERR_NEW_OK
        cdef ToxAV* ptr = toxav_new(tox._ptr if tox else NULL, &error)
        if error:
            raise ApiException(Toxav_Err_New(error))
        return ptr

    def __init__(self, tox: Optional[Tox_Ptr] = None) -> None:
        """Create new ToxAV object."""
        self._ptr = self._new(tox)
        install_handlers(self, self._get())

    @property
    def iteration_interval(self) -> int:
        return toxav_iteration_interval(self._get())

    def iterate(self) -> None:
        toxav_iterate(self._get())

    @property
    def audio_iteration_interval(self) -> int:
        return toxav_audio_iteration_interval(self._get())

    def audio_iterate(self) -> None:
        toxav_audio_iterate(self._get())

    @property
    def video_iteration_interval(self) -> int:
        return toxav_video_iteration_interval(self._get())

    def video_iterate(self) -> None:
        toxav_video_iterate(self._get())

    def call(self, friend_number: Tox_Friend_Number, audio_bit_rate: int, video_bit_rate: int) -> bool:
        cdef Toxav_Err_Call err = TOXAV_ERR_CALL_OK
        cdef bool res = toxav_call(self._get(), friend_number, audio_bit_rate, video_bit_rate, &err)
        if err:
            raise ApiException(Toxav_Err_Call(err))
        return res

    def answer(self, friend_number: Tox_Friend_Number, audio_bit_rate: int, video_bit_rate: int) -> bool:
        cdef Toxav_Err_Answer err = TOXAV_ERR_ANSWER_OK
        cdef bool res = toxav_answer(self._get(), friend_number, audio_bit_rate, video_bit_rate, &err)
        if err:
            raise ApiException(Toxav_Err_Answer(err))
        return res

    def call_control(self, friend_number: Tox_Friend_Number, control: Toxav_Call_Control) -> bool:
        cdef Toxav_Err_Call_Control err = TOXAV_ERR_CALL_CONTROL_OK
        cdef bool res = toxav_call_control(self._get(), friend_number, control, &err)
        if err:
            raise ApiException(Toxav_Err_Call_Control(err))
        return res

    def audio_send_frame(self, friend_number: Tox_Friend_Number, pcm: array, sample_count: int, channels: int, sampling_rate: int) -> bool:
        cdef const int16_t[:] pcm_arr = pcm
        cdef Toxav_Err_Send_Frame err = TOXAV_ERR_SEND_FRAME_OK
        cdef bool res = toxav_audio_send_frame(self._get(), friend_number, &pcm_arr[0], sample_count, channels, sampling_rate, &err)
        if err:
            raise ApiException(Toxav_Err_Send_Frame(err))
        return res

    def audio_set_bit_rate(self, friend_number: Tox_Friend_Number, bit_rate: int) -> bool:
        cdef Toxav_Err_Bit_Rate_Set err = TOXAV_ERR_BIT_RATE_SET_OK
        cdef bool res = toxav_audio_set_bit_rate(self._get(), friend_number, bit_rate, &err)
        if err:
            raise ApiException(Toxav_Err_Bit_Rate_Set(err))
        return res

    def video_send_frame(self, friend_number: Tox_Friend_Number, width: int, height: int, y: bytes, u: bytes, v: bytes) -> bool:
        common.check_len("y", y, width * height)
        common.check_len("u", u, width // 2 * height // 2)
        common.check_len("v", v, width // 2 * height // 2)
        cdef Toxav_Err_Send_Frame err = TOXAV_ERR_SEND_FRAME_OK
        cdef bool res = toxav_video_send_frame(self._get(), friend_number, width, height, y, u, v, &err)
        if err:
            raise ApiException(Toxav_Err_Send_Frame(err))
        return res

    def video_set_bit_rate(self, friend_number: Tox_Friend_Number, bit_rate: int) -> bool:
        cdef Toxav_Err_Bit_Rate_Set err = TOXAV_ERR_BIT_RATE_SET_OK
        cdef bool res = toxav_video_set_bit_rate(self._get(), friend_number, bit_rate, &err)
        if err:
            raise ApiException(Toxav_Err_Bit_Rate_Set(err))
        return res

    def handle_call(self, friend_number: int, audio_enabled: bool, video_enabled: bool) -> None: pass

    def handle_call_state(self, friend_number: int, state: int) -> None: pass

    def handle_audio_bit_rate(self, friend_number: int, audio_bit_rate: int) -> None: pass

    def handle_video_bit_rate(self, friend_number: int, video_bit_rate: int) -> None: pass

    def handle_audio_receive_frame(self, friend_number: int, pcm: array, sample_count: int, channels: int, sampling_rate: int) -> None: pass

    def handle_video_receive_frame(self, friend_number: int, width: int, height: int, y: bytes, u: bytes, v: bytes, ystride: int, ustride: int, vstride: int) -> None: pass
