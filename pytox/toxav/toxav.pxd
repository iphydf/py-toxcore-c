# cython: language_level=3, linetrace=True
from libcpp cimport bool
from libc.stdint cimport uint8_t, uint16_t, uint32_t, uint64_t, int16_t, int32_t, int64_t
from libc.stdlib cimport malloc, free
from typing import Optional
from pytox.toxcore.tox cimport Tox, Tox_Ptr, Tox_Conference_Number, Tox_Conference_Offline_Peer_Number, Tox_Conference_Peer_Number, Tox_File_Number, Tox_Friend_Message_Id, Tox_Friend_Number, Tox_Group_Message_Id, Tox_Group_Number, Tox_Group_Peer_Number


cdef extern from "tox/toxav.h":
    cpdef enum Toxav_Call_Control:
        TOXAV_CALL_CONTROL_RESUME
        TOXAV_CALL_CONTROL_PAUSE
        TOXAV_CALL_CONTROL_CANCEL
        TOXAV_CALL_CONTROL_MUTE_AUDIO
        TOXAV_CALL_CONTROL_UNMUTE_AUDIO
        TOXAV_CALL_CONTROL_HIDE_VIDEO
        TOXAV_CALL_CONTROL_SHOW_VIDEO
    cpdef enum Toxav_Err_Answer:
        TOXAV_ERR_ANSWER_OK
        TOXAV_ERR_ANSWER_SYNC
        TOXAV_ERR_ANSWER_CODEC_INITIALIZATION
        TOXAV_ERR_ANSWER_FRIEND_NOT_FOUND
        TOXAV_ERR_ANSWER_FRIEND_NOT_CALLING
        TOXAV_ERR_ANSWER_INVALID_BIT_RATE
    cpdef enum Toxav_Err_Bit_Rate_Set:
        TOXAV_ERR_BIT_RATE_SET_OK
        TOXAV_ERR_BIT_RATE_SET_SYNC
        TOXAV_ERR_BIT_RATE_SET_INVALID_BIT_RATE
        TOXAV_ERR_BIT_RATE_SET_FRIEND_NOT_FOUND
        TOXAV_ERR_BIT_RATE_SET_FRIEND_NOT_IN_CALL
    cpdef enum Toxav_Err_Call:
        TOXAV_ERR_CALL_OK
        TOXAV_ERR_CALL_MALLOC
        TOXAV_ERR_CALL_SYNC
        TOXAV_ERR_CALL_FRIEND_NOT_FOUND
        TOXAV_ERR_CALL_FRIEND_NOT_CONNECTED
        TOXAV_ERR_CALL_FRIEND_ALREADY_IN_CALL
        TOXAV_ERR_CALL_INVALID_BIT_RATE
    cpdef enum Toxav_Err_Call_Control:
        TOXAV_ERR_CALL_CONTROL_OK
        TOXAV_ERR_CALL_CONTROL_SYNC
        TOXAV_ERR_CALL_CONTROL_FRIEND_NOT_FOUND
        TOXAV_ERR_CALL_CONTROL_FRIEND_NOT_IN_CALL
        TOXAV_ERR_CALL_CONTROL_INVALID_TRANSITION
    cpdef enum Toxav_Err_New:
        TOXAV_ERR_NEW_OK
        TOXAV_ERR_NEW_NULL
        TOXAV_ERR_NEW_MALLOC
        TOXAV_ERR_NEW_MULTIPLE
    cpdef enum Toxav_Err_Send_Frame:
        TOXAV_ERR_SEND_FRAME_OK
        TOXAV_ERR_SEND_FRAME_NULL
        TOXAV_ERR_SEND_FRAME_FRIEND_NOT_FOUND
        TOXAV_ERR_SEND_FRAME_FRIEND_NOT_IN_CALL
        TOXAV_ERR_SEND_FRAME_SYNC
        TOXAV_ERR_SEND_FRAME_INVALID
        TOXAV_ERR_SEND_FRAME_PAYLOAD_TYPE_DISABLED
        TOXAV_ERR_SEND_FRAME_RTP_FAILED
    ctypedef struct ToxAV
    ctypedef void toxav_audio_bit_rate_cb(ToxAV* av, uint32_t friend_number, uint32_t audio_bit_rate, void* user_data) except *
    ctypedef void toxav_audio_data_cb(void* tox, Tox_Conference_Number conference_number, Tox_Conference_Peer_Number peer_number, const int16_t* pcm, uint32_t samples, uint8_t channels, uint32_t sample_rate, void* userdata) except *
    ctypedef void toxav_audio_receive_frame_cb(ToxAV* av, uint32_t friend_number, const int16_t* pcm, size_t sample_count, uint8_t channels, uint32_t sampling_rate, void* user_data) except *
    ctypedef void toxav_call_cb(ToxAV* av, uint32_t friend_number, bool audio_enabled, bool video_enabled, void* user_data) except *
    ctypedef void toxav_call_state_cb(ToxAV* av, uint32_t friend_number, uint32_t state, void* user_data) except *
    ctypedef void toxav_video_bit_rate_cb(ToxAV* av, uint32_t friend_number, uint32_t video_bit_rate, void* user_data) except *
    ctypedef void toxav_video_receive_frame_cb(ToxAV* av, uint32_t friend_number, uint16_t width, uint16_t height, const uint8_t* y, const uint8_t* u, const uint8_t* v, int32_t ystride, int32_t ustride, int32_t vstride, void* user_data) except *
    cdef ToxAV* toxav_new(Tox* tox, Toxav_Err_New* error)
    cdef void toxav_kill(ToxAV* self)
    cdef uint32_t toxav_iteration_interval(const ToxAV* self)
    cdef void toxav_iterate(ToxAV* self)
    cdef uint32_t toxav_audio_iteration_interval(const ToxAV* self)
    cdef void toxav_audio_iterate(ToxAV* self)
    cdef uint32_t toxav_video_iteration_interval(const ToxAV* self)
    cdef void toxav_video_iterate(ToxAV* self)
    cdef bool toxav_call(ToxAV* self, Tox_Friend_Number friend_number, uint32_t audio_bit_rate, uint32_t video_bit_rate, Toxav_Err_Call* error)
    cdef bool toxav_answer(ToxAV* self, Tox_Friend_Number friend_number, uint32_t audio_bit_rate, uint32_t video_bit_rate, Toxav_Err_Answer* error)
    cdef bool toxav_call_control(ToxAV* self, Tox_Friend_Number friend_number, Toxav_Call_Control control, Toxav_Err_Call_Control* error)
    cdef bool toxav_audio_send_frame(ToxAV* self, Tox_Friend_Number friend_number, const int16_t* pcm, size_t sample_count, uint8_t channels, uint32_t sampling_rate, Toxav_Err_Send_Frame* error)
    cdef bool toxav_audio_set_bit_rate(ToxAV* self, Tox_Friend_Number friend_number, uint32_t bit_rate, Toxav_Err_Bit_Rate_Set* error)
    cdef bool toxav_video_send_frame(ToxAV* self, Tox_Friend_Number friend_number, uint16_t width, uint16_t height, const uint8_t* y, const uint8_t* u, const uint8_t* v, Toxav_Err_Send_Frame* error)
    cdef bool toxav_video_set_bit_rate(ToxAV* self, Tox_Friend_Number friend_number, uint32_t bit_rate, Toxav_Err_Bit_Rate_Set* error)
    cdef void toxav_callback_call(ToxAV* self, toxav_call_cb* callback, void* user_data)
    cdef void toxav_callback_call_state(ToxAV* self, toxav_call_state_cb* callback, void* user_data)
    cdef void toxav_callback_audio_bit_rate(ToxAV* self, toxav_audio_bit_rate_cb* callback, void* user_data)
    cdef void toxav_callback_video_bit_rate(ToxAV* self, toxav_video_bit_rate_cb* callback, void* user_data)
    cdef void toxav_callback_audio_receive_frame(ToxAV* self, toxav_audio_receive_frame_cb* callback, void* user_data)
    cdef void toxav_callback_video_receive_frame(ToxAV* self, toxav_video_receive_frame_cb* callback, void* user_data)


cdef class ToxAV_Ptr:
    cdef ToxAV* _ptr
    cdef ToxAV* _get(self) except *
    cdef ToxAV* _new(self, Tox_Ptr tox)
