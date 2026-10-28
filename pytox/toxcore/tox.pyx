# cython: language_level=3, linetrace=True
from enum import IntEnum
from pytox import common
from pytox.toxcore import events
from cpython.pythread cimport PyThread_allocate_lock, PyThread_free_lock, PyThread_acquire_lock, PyThread_release_lock, WAIT_LOCK
from types import TracebackType
from typing import Optional
from typing import TypeVar
from typing import NewType
T = TypeVar("T")
ConferenceNumber = NewType("ConferenceNumber", int)
ConferenceOfflinePeerNumber = NewType("ConferenceOfflinePeerNumber", int)
ConferencePeerNumber = NewType("ConferencePeerNumber", int)
FileNumber = NewType("FileNumber", int)
FriendMessageId = NewType("FriendMessageId", int)
FriendNumber = NewType("FriendNumber", int)
GroupMessageId = NewType("GroupMessageId", int)
GroupNumber = NewType("GroupNumber", int)
GroupPeerNumber = NewType("GroupPeerNumber", int)

cdef bytes _take_uint8_t(uint8_t* buf, size_t size):
    if buf is NULL:
        raise MemoryError()
    try:
        return buf[:size]
    finally:
        free(buf)

cdef list _take_uint32_t(uint32_t* buf, size_t size):
    if buf is NULL:
        raise MemoryError()
    try:
        return [buf[i] for i in range(size)]
    finally:
        free(buf)


class ApiException(common.ApiException):
    pass

ConferenceType = IntEnum("ConferenceType", [
    ("TEXT", TOX_CONFERENCE_TYPE_TEXT),
    ("AV", TOX_CONFERENCE_TYPE_AV),
], module=__name__)

Connection = IntEnum("Connection", [
    ("NONE", TOX_CONNECTION_NONE),
    ("TCP", TOX_CONNECTION_TCP),
    ("UDP", TOX_CONNECTION_UDP),
], module=__name__)

class BootstrapError(ApiException):
    Code = IntEnum("Code", [
        ("NULL", TOX_ERR_BOOTSTRAP_NULL),
        ("BAD_HOST", TOX_ERR_BOOTSTRAP_BAD_HOST),
        ("BAD_PORT", TOX_ERR_BOOTSTRAP_BAD_PORT),
    ], module=__name__, qualname="BootstrapError.Code")

class ConferenceByIdError(ApiException):
    Code = IntEnum("Code", [
        ("NULL", TOX_ERR_CONFERENCE_BY_ID_NULL),
        ("NOT_FOUND", TOX_ERR_CONFERENCE_BY_ID_NOT_FOUND),
    ], module=__name__, qualname="ConferenceByIdError.Code")

class ConferenceDeleteError(ApiException):
    Code = IntEnum("Code", [
        ("CONFERENCE_NOT_FOUND", TOX_ERR_CONFERENCE_DELETE_CONFERENCE_NOT_FOUND),
    ], module=__name__, qualname="ConferenceDeleteError.Code")

class ConferenceGetTypeError(ApiException):
    Code = IntEnum("Code", [
        ("CONFERENCE_NOT_FOUND", TOX_ERR_CONFERENCE_GET_TYPE_CONFERENCE_NOT_FOUND),
    ], module=__name__, qualname="ConferenceGetTypeError.Code")

class ConferenceInviteError(ApiException):
    Code = IntEnum("Code", [
        ("CONFERENCE_NOT_FOUND", TOX_ERR_CONFERENCE_INVITE_CONFERENCE_NOT_FOUND),
        ("FAIL_SEND", TOX_ERR_CONFERENCE_INVITE_FAIL_SEND),
        ("NO_CONNECTION", TOX_ERR_CONFERENCE_INVITE_NO_CONNECTION),
    ], module=__name__, qualname="ConferenceInviteError.Code")

class ConferenceJoinError(ApiException):
    Code = IntEnum("Code", [
        ("INVALID_LENGTH", TOX_ERR_CONFERENCE_JOIN_INVALID_LENGTH),
        ("WRONG_TYPE", TOX_ERR_CONFERENCE_JOIN_WRONG_TYPE),
        ("FRIEND_NOT_FOUND", TOX_ERR_CONFERENCE_JOIN_FRIEND_NOT_FOUND),
        ("DUPLICATE", TOX_ERR_CONFERENCE_JOIN_DUPLICATE),
        ("INIT_FAIL", TOX_ERR_CONFERENCE_JOIN_INIT_FAIL),
        ("FAIL_SEND", TOX_ERR_CONFERENCE_JOIN_FAIL_SEND),
        ("NULL", TOX_ERR_CONFERENCE_JOIN_NULL),
    ], module=__name__, qualname="ConferenceJoinError.Code")

class ConferenceNewError(ApiException):
    Code = IntEnum("Code", [
        ("INIT", TOX_ERR_CONFERENCE_NEW_INIT),
    ], module=__name__, qualname="ConferenceNewError.Code")

class ConferencePeerQueryError(ApiException):
    Code = IntEnum("Code", [
        ("CONFERENCE_NOT_FOUND", TOX_ERR_CONFERENCE_PEER_QUERY_CONFERENCE_NOT_FOUND),
        ("PEER_NOT_FOUND", TOX_ERR_CONFERENCE_PEER_QUERY_PEER_NOT_FOUND),
        ("NO_CONNECTION", TOX_ERR_CONFERENCE_PEER_QUERY_NO_CONNECTION),
    ], module=__name__, qualname="ConferencePeerQueryError.Code")

class ConferenceSendMessageError(ApiException):
    Code = IntEnum("Code", [
        ("CONFERENCE_NOT_FOUND", TOX_ERR_CONFERENCE_SEND_MESSAGE_CONFERENCE_NOT_FOUND),
        ("TOO_LONG", TOX_ERR_CONFERENCE_SEND_MESSAGE_TOO_LONG),
        ("NO_CONNECTION", TOX_ERR_CONFERENCE_SEND_MESSAGE_NO_CONNECTION),
        ("FAIL_SEND", TOX_ERR_CONFERENCE_SEND_MESSAGE_FAIL_SEND),
    ], module=__name__, qualname="ConferenceSendMessageError.Code")

class ConferenceSetMaxOfflineError(ApiException):
    Code = IntEnum("Code", [
        ("CONFERENCE_NOT_FOUND", TOX_ERR_CONFERENCE_SET_MAX_OFFLINE_CONFERENCE_NOT_FOUND),
    ], module=__name__, qualname="ConferenceSetMaxOfflineError.Code")

class ConferenceTitleError(ApiException):
    Code = IntEnum("Code", [
        ("CONFERENCE_NOT_FOUND", TOX_ERR_CONFERENCE_TITLE_CONFERENCE_NOT_FOUND),
        ("INVALID_LENGTH", TOX_ERR_CONFERENCE_TITLE_INVALID_LENGTH),
        ("FAIL_SEND", TOX_ERR_CONFERENCE_TITLE_FAIL_SEND),
    ], module=__name__, qualname="ConferenceTitleError.Code")

class FileByIdError(ApiException):
    Code = IntEnum("Code", [
        ("NULL", TOX_ERR_FILE_BY_ID_NULL),
        ("FRIEND_NOT_FOUND", TOX_ERR_FILE_BY_ID_FRIEND_NOT_FOUND),
        ("NOT_FOUND", TOX_ERR_FILE_BY_ID_NOT_FOUND),
    ], module=__name__, qualname="FileByIdError.Code")

class FileControlError(ApiException):
    Code = IntEnum("Code", [
        ("FRIEND_NOT_FOUND", TOX_ERR_FILE_CONTROL_FRIEND_NOT_FOUND),
        ("FRIEND_NOT_CONNECTED", TOX_ERR_FILE_CONTROL_FRIEND_NOT_CONNECTED),
        ("NOT_FOUND", TOX_ERR_FILE_CONTROL_NOT_FOUND),
        ("NOT_PAUSED", TOX_ERR_FILE_CONTROL_NOT_PAUSED),
        ("DENIED", TOX_ERR_FILE_CONTROL_DENIED),
        ("ALREADY_PAUSED", TOX_ERR_FILE_CONTROL_ALREADY_PAUSED),
        ("SENDQ", TOX_ERR_FILE_CONTROL_SENDQ),
    ], module=__name__, qualname="FileControlError.Code")

class FileGetError(ApiException):
    Code = IntEnum("Code", [
        ("NULL", TOX_ERR_FILE_GET_NULL),
        ("FRIEND_NOT_FOUND", TOX_ERR_FILE_GET_FRIEND_NOT_FOUND),
        ("NOT_FOUND", TOX_ERR_FILE_GET_NOT_FOUND),
    ], module=__name__, qualname="FileGetError.Code")

class FileSeekError(ApiException):
    Code = IntEnum("Code", [
        ("FRIEND_NOT_FOUND", TOX_ERR_FILE_SEEK_FRIEND_NOT_FOUND),
        ("FRIEND_NOT_CONNECTED", TOX_ERR_FILE_SEEK_FRIEND_NOT_CONNECTED),
        ("NOT_FOUND", TOX_ERR_FILE_SEEK_NOT_FOUND),
        ("DENIED", TOX_ERR_FILE_SEEK_DENIED),
        ("INVALID_POSITION", TOX_ERR_FILE_SEEK_INVALID_POSITION),
        ("SENDQ", TOX_ERR_FILE_SEEK_SENDQ),
    ], module=__name__, qualname="FileSeekError.Code")

class FileSendError(ApiException):
    Code = IntEnum("Code", [
        ("NULL", TOX_ERR_FILE_SEND_NULL),
        ("FRIEND_NOT_FOUND", TOX_ERR_FILE_SEND_FRIEND_NOT_FOUND),
        ("FRIEND_NOT_CONNECTED", TOX_ERR_FILE_SEND_FRIEND_NOT_CONNECTED),
        ("NAME_TOO_LONG", TOX_ERR_FILE_SEND_NAME_TOO_LONG),
        ("TOO_MANY", TOX_ERR_FILE_SEND_TOO_MANY),
    ], module=__name__, qualname="FileSendError.Code")

class FileSendChunkError(ApiException):
    Code = IntEnum("Code", [
        ("NULL", TOX_ERR_FILE_SEND_CHUNK_NULL),
        ("FRIEND_NOT_FOUND", TOX_ERR_FILE_SEND_CHUNK_FRIEND_NOT_FOUND),
        ("FRIEND_NOT_CONNECTED", TOX_ERR_FILE_SEND_CHUNK_FRIEND_NOT_CONNECTED),
        ("NOT_FOUND", TOX_ERR_FILE_SEND_CHUNK_NOT_FOUND),
        ("NOT_TRANSFERRING", TOX_ERR_FILE_SEND_CHUNK_NOT_TRANSFERRING),
        ("INVALID_LENGTH", TOX_ERR_FILE_SEND_CHUNK_INVALID_LENGTH),
        ("SENDQ", TOX_ERR_FILE_SEND_CHUNK_SENDQ),
        ("WRONG_POSITION", TOX_ERR_FILE_SEND_CHUNK_WRONG_POSITION),
    ], module=__name__, qualname="FileSendChunkError.Code")

class FriendAddError(ApiException):
    Code = IntEnum("Code", [
        ("NULL", TOX_ERR_FRIEND_ADD_NULL),
        ("TOO_LONG", TOX_ERR_FRIEND_ADD_TOO_LONG),
        ("NO_MESSAGE", TOX_ERR_FRIEND_ADD_NO_MESSAGE),
        ("OWN_KEY", TOX_ERR_FRIEND_ADD_OWN_KEY),
        ("ALREADY_SENT", TOX_ERR_FRIEND_ADD_ALREADY_SENT),
        ("BAD_CHECKSUM", TOX_ERR_FRIEND_ADD_BAD_CHECKSUM),
        ("SET_NEW_NOSPAM", TOX_ERR_FRIEND_ADD_SET_NEW_NOSPAM),
        ("MALLOC", TOX_ERR_FRIEND_ADD_MALLOC),
    ], module=__name__, qualname="FriendAddError.Code")

class FriendByPublicKeyError(ApiException):
    Code = IntEnum("Code", [
        ("NULL", TOX_ERR_FRIEND_BY_PUBLIC_KEY_NULL),
        ("NOT_FOUND", TOX_ERR_FRIEND_BY_PUBLIC_KEY_NOT_FOUND),
    ], module=__name__, qualname="FriendByPublicKeyError.Code")

class FriendCustomPacketError(ApiException):
    Code = IntEnum("Code", [
        ("NULL", TOX_ERR_FRIEND_CUSTOM_PACKET_NULL),
        ("FRIEND_NOT_FOUND", TOX_ERR_FRIEND_CUSTOM_PACKET_FRIEND_NOT_FOUND),
        ("FRIEND_NOT_CONNECTED", TOX_ERR_FRIEND_CUSTOM_PACKET_FRIEND_NOT_CONNECTED),
        ("INVALID", TOX_ERR_FRIEND_CUSTOM_PACKET_INVALID),
        ("EMPTY", TOX_ERR_FRIEND_CUSTOM_PACKET_EMPTY),
        ("TOO_LONG", TOX_ERR_FRIEND_CUSTOM_PACKET_TOO_LONG),
        ("SENDQ", TOX_ERR_FRIEND_CUSTOM_PACKET_SENDQ),
    ], module=__name__, qualname="FriendCustomPacketError.Code")

class FriendDeleteError(ApiException):
    Code = IntEnum("Code", [
        ("FRIEND_NOT_FOUND", TOX_ERR_FRIEND_DELETE_FRIEND_NOT_FOUND),
    ], module=__name__, qualname="FriendDeleteError.Code")

class FriendGetLastOnlineError(ApiException):
    Code = IntEnum("Code", [
        ("FRIEND_NOT_FOUND", TOX_ERR_FRIEND_GET_LAST_ONLINE_FRIEND_NOT_FOUND),
    ], module=__name__, qualname="FriendGetLastOnlineError.Code")

class FriendGetPublicKeyError(ApiException):
    Code = IntEnum("Code", [
        ("FRIEND_NOT_FOUND", TOX_ERR_FRIEND_GET_PUBLIC_KEY_FRIEND_NOT_FOUND),
    ], module=__name__, qualname="FriendGetPublicKeyError.Code")

class FriendQueryError(ApiException):
    Code = IntEnum("Code", [
        ("NULL", TOX_ERR_FRIEND_QUERY_NULL),
        ("FRIEND_NOT_FOUND", TOX_ERR_FRIEND_QUERY_FRIEND_NOT_FOUND),
    ], module=__name__, qualname="FriendQueryError.Code")

class FriendSendMessageError(ApiException):
    Code = IntEnum("Code", [
        ("NULL", TOX_ERR_FRIEND_SEND_MESSAGE_NULL),
        ("FRIEND_NOT_FOUND", TOX_ERR_FRIEND_SEND_MESSAGE_FRIEND_NOT_FOUND),
        ("FRIEND_NOT_CONNECTED", TOX_ERR_FRIEND_SEND_MESSAGE_FRIEND_NOT_CONNECTED),
        ("SENDQ", TOX_ERR_FRIEND_SEND_MESSAGE_SENDQ),
        ("TOO_LONG", TOX_ERR_FRIEND_SEND_MESSAGE_TOO_LONG),
        ("EMPTY", TOX_ERR_FRIEND_SEND_MESSAGE_EMPTY),
    ], module=__name__, qualname="FriendSendMessageError.Code")

class GetPortError(ApiException):
    Code = IntEnum("Code", [
        ("NOT_BOUND", TOX_ERR_GET_PORT_NOT_BOUND),
    ], module=__name__, qualname="GetPortError.Code")

class GroupByIdError(ApiException):
    Code = IntEnum("Code", [
        ("NULL", TOX_ERR_GROUP_BY_ID_NULL),
        ("NOT_FOUND", TOX_ERR_GROUP_BY_ID_NOT_FOUND),
    ], module=__name__, qualname="GroupByIdError.Code")

class GroupDisconnectError(ApiException):
    Code = IntEnum("Code", [
        ("GROUP_NOT_FOUND", TOX_ERR_GROUP_DISCONNECT_GROUP_NOT_FOUND),
        ("ALREADY_DISCONNECTED", TOX_ERR_GROUP_DISCONNECT_ALREADY_DISCONNECTED),
    ], module=__name__, qualname="GroupDisconnectError.Code")

class GroupInviteAcceptError(ApiException):
    Code = IntEnum("Code", [
        ("BAD_INVITE", TOX_ERR_GROUP_INVITE_ACCEPT_BAD_INVITE),
        ("INIT_FAILED", TOX_ERR_GROUP_INVITE_ACCEPT_INIT_FAILED),
        ("TOO_LONG", TOX_ERR_GROUP_INVITE_ACCEPT_TOO_LONG),
        ("EMPTY", TOX_ERR_GROUP_INVITE_ACCEPT_EMPTY),
        ("PASSWORD", TOX_ERR_GROUP_INVITE_ACCEPT_PASSWORD),
        ("FRIEND_NOT_FOUND", TOX_ERR_GROUP_INVITE_ACCEPT_FRIEND_NOT_FOUND),
        ("FAIL_SEND", TOX_ERR_GROUP_INVITE_ACCEPT_FAIL_SEND),
        ("NULL", TOX_ERR_GROUP_INVITE_ACCEPT_NULL),
    ], module=__name__, qualname="GroupInviteAcceptError.Code")

class GroupInviteFriendError(ApiException):
    Code = IntEnum("Code", [
        ("GROUP_NOT_FOUND", TOX_ERR_GROUP_INVITE_FRIEND_GROUP_NOT_FOUND),
        ("FRIEND_NOT_FOUND", TOX_ERR_GROUP_INVITE_FRIEND_FRIEND_NOT_FOUND),
        ("INVITE_FAIL", TOX_ERR_GROUP_INVITE_FRIEND_INVITE_FAIL),
        ("FAIL_SEND", TOX_ERR_GROUP_INVITE_FRIEND_FAIL_SEND),
        ("DISCONNECTED", TOX_ERR_GROUP_INVITE_FRIEND_DISCONNECTED),
    ], module=__name__, qualname="GroupInviteFriendError.Code")

class GroupIsConnectedError(ApiException):
    Code = IntEnum("Code", [
        ("GROUP_NOT_FOUND", TOX_ERR_GROUP_IS_CONNECTED_GROUP_NOT_FOUND),
    ], module=__name__, qualname="GroupIsConnectedError.Code")

class GroupJoinError(ApiException):
    Code = IntEnum("Code", [
        ("INIT", TOX_ERR_GROUP_JOIN_INIT),
        ("BAD_CHAT_ID", TOX_ERR_GROUP_JOIN_BAD_CHAT_ID),
        ("EMPTY", TOX_ERR_GROUP_JOIN_EMPTY),
        ("TOO_LONG", TOX_ERR_GROUP_JOIN_TOO_LONG),
        ("PASSWORD", TOX_ERR_GROUP_JOIN_PASSWORD),
        ("CORE", TOX_ERR_GROUP_JOIN_CORE),
    ], module=__name__, qualname="GroupJoinError.Code")

class GroupKickPeerError(ApiException):
    Code = IntEnum("Code", [
        ("GROUP_NOT_FOUND", TOX_ERR_GROUP_KICK_PEER_GROUP_NOT_FOUND),
        ("PEER_NOT_FOUND", TOX_ERR_GROUP_KICK_PEER_PEER_NOT_FOUND),
        ("PERMISSIONS", TOX_ERR_GROUP_KICK_PEER_PERMISSIONS),
        ("FAIL_ACTION", TOX_ERR_GROUP_KICK_PEER_FAIL_ACTION),
        ("FAIL_SEND", TOX_ERR_GROUP_KICK_PEER_FAIL_SEND),
        ("SELF", TOX_ERR_GROUP_KICK_PEER_SELF),
    ], module=__name__, qualname="GroupKickPeerError.Code")

class GroupLeaveError(ApiException):
    Code = IntEnum("Code", [
        ("GROUP_NOT_FOUND", TOX_ERR_GROUP_LEAVE_GROUP_NOT_FOUND),
        ("TOO_LONG", TOX_ERR_GROUP_LEAVE_TOO_LONG),
        ("FAIL_SEND", TOX_ERR_GROUP_LEAVE_FAIL_SEND),
    ], module=__name__, qualname="GroupLeaveError.Code")

class GroupNewError(ApiException):
    Code = IntEnum("Code", [
        ("TOO_LONG", TOX_ERR_GROUP_NEW_TOO_LONG),
        ("EMPTY", TOX_ERR_GROUP_NEW_EMPTY),
        ("INIT", TOX_ERR_GROUP_NEW_INIT),
        ("STATE", TOX_ERR_GROUP_NEW_STATE),
        ("ANNOUNCE", TOX_ERR_GROUP_NEW_ANNOUNCE),
    ], module=__name__, qualname="GroupNewError.Code")

class GroupPeerQueryError(ApiException):
    Code = IntEnum("Code", [
        ("GROUP_NOT_FOUND", TOX_ERR_GROUP_PEER_QUERY_GROUP_NOT_FOUND),
        ("PEER_NOT_FOUND", TOX_ERR_GROUP_PEER_QUERY_PEER_NOT_FOUND),
    ], module=__name__, qualname="GroupPeerQueryError.Code")

class GroupSelfNameSetError(ApiException):
    Code = IntEnum("Code", [
        ("GROUP_NOT_FOUND", TOX_ERR_GROUP_SELF_NAME_SET_GROUP_NOT_FOUND),
        ("TOO_LONG", TOX_ERR_GROUP_SELF_NAME_SET_TOO_LONG),
        ("INVALID", TOX_ERR_GROUP_SELF_NAME_SET_INVALID),
        ("FAIL_SEND", TOX_ERR_GROUP_SELF_NAME_SET_FAIL_SEND),
    ], module=__name__, qualname="GroupSelfNameSetError.Code")

class GroupSelfQueryError(ApiException):
    Code = IntEnum("Code", [
        ("GROUP_NOT_FOUND", TOX_ERR_GROUP_SELF_QUERY_GROUP_NOT_FOUND),
    ], module=__name__, qualname="GroupSelfQueryError.Code")

class GroupSelfStatusSetError(ApiException):
    Code = IntEnum("Code", [
        ("GROUP_NOT_FOUND", TOX_ERR_GROUP_SELF_STATUS_SET_GROUP_NOT_FOUND),
        ("FAIL_SEND", TOX_ERR_GROUP_SELF_STATUS_SET_FAIL_SEND),
    ], module=__name__, qualname="GroupSelfStatusSetError.Code")

class GroupSendCustomPacketError(ApiException):
    Code = IntEnum("Code", [
        ("GROUP_NOT_FOUND", TOX_ERR_GROUP_SEND_CUSTOM_PACKET_GROUP_NOT_FOUND),
        ("TOO_LONG", TOX_ERR_GROUP_SEND_CUSTOM_PACKET_TOO_LONG),
        ("EMPTY", TOX_ERR_GROUP_SEND_CUSTOM_PACKET_EMPTY),
        ("DISCONNECTED", TOX_ERR_GROUP_SEND_CUSTOM_PACKET_DISCONNECTED),
        ("FAIL_SEND", TOX_ERR_GROUP_SEND_CUSTOM_PACKET_FAIL_SEND),
    ], module=__name__, qualname="GroupSendCustomPacketError.Code")

class GroupSendCustomPrivatePacketError(ApiException):
    Code = IntEnum("Code", [
        ("GROUP_NOT_FOUND", TOX_ERR_GROUP_SEND_CUSTOM_PRIVATE_PACKET_GROUP_NOT_FOUND),
        ("TOO_LONG", TOX_ERR_GROUP_SEND_CUSTOM_PRIVATE_PACKET_TOO_LONG),
        ("EMPTY", TOX_ERR_GROUP_SEND_CUSTOM_PRIVATE_PACKET_EMPTY),
        ("PEER_NOT_FOUND", TOX_ERR_GROUP_SEND_CUSTOM_PRIVATE_PACKET_PEER_NOT_FOUND),
        ("FAIL_SEND", TOX_ERR_GROUP_SEND_CUSTOM_PRIVATE_PACKET_FAIL_SEND),
        ("DISCONNECTED", TOX_ERR_GROUP_SEND_CUSTOM_PRIVATE_PACKET_DISCONNECTED),
    ], module=__name__, qualname="GroupSendCustomPrivatePacketError.Code")

class GroupSendMessageError(ApiException):
    Code = IntEnum("Code", [
        ("GROUP_NOT_FOUND", TOX_ERR_GROUP_SEND_MESSAGE_GROUP_NOT_FOUND),
        ("TOO_LONG", TOX_ERR_GROUP_SEND_MESSAGE_TOO_LONG),
        ("EMPTY", TOX_ERR_GROUP_SEND_MESSAGE_EMPTY),
        ("BAD_TYPE", TOX_ERR_GROUP_SEND_MESSAGE_BAD_TYPE),
        ("PERMISSIONS", TOX_ERR_GROUP_SEND_MESSAGE_PERMISSIONS),
        ("FAIL_SEND", TOX_ERR_GROUP_SEND_MESSAGE_FAIL_SEND),
        ("DISCONNECTED", TOX_ERR_GROUP_SEND_MESSAGE_DISCONNECTED),
    ], module=__name__, qualname="GroupSendMessageError.Code")

class GroupSendPrivateMessageError(ApiException):
    Code = IntEnum("Code", [
        ("GROUP_NOT_FOUND", TOX_ERR_GROUP_SEND_PRIVATE_MESSAGE_GROUP_NOT_FOUND),
        ("PEER_NOT_FOUND", TOX_ERR_GROUP_SEND_PRIVATE_MESSAGE_PEER_NOT_FOUND),
        ("TOO_LONG", TOX_ERR_GROUP_SEND_PRIVATE_MESSAGE_TOO_LONG),
        ("EMPTY", TOX_ERR_GROUP_SEND_PRIVATE_MESSAGE_EMPTY),
        ("BAD_TYPE", TOX_ERR_GROUP_SEND_PRIVATE_MESSAGE_BAD_TYPE),
        ("PERMISSIONS", TOX_ERR_GROUP_SEND_PRIVATE_MESSAGE_PERMISSIONS),
        ("FAIL_SEND", TOX_ERR_GROUP_SEND_PRIVATE_MESSAGE_FAIL_SEND),
        ("DISCONNECTED", TOX_ERR_GROUP_SEND_PRIVATE_MESSAGE_DISCONNECTED),
    ], module=__name__, qualname="GroupSendPrivateMessageError.Code")

class GroupSetIgnoreError(ApiException):
    Code = IntEnum("Code", [
        ("GROUP_NOT_FOUND", TOX_ERR_GROUP_SET_IGNORE_GROUP_NOT_FOUND),
        ("PEER_NOT_FOUND", TOX_ERR_GROUP_SET_IGNORE_PEER_NOT_FOUND),
        ("SELF", TOX_ERR_GROUP_SET_IGNORE_SELF),
    ], module=__name__, qualname="GroupSetIgnoreError.Code")

class GroupSetPasswordError(ApiException):
    Code = IntEnum("Code", [
        ("GROUP_NOT_FOUND", TOX_ERR_GROUP_SET_PASSWORD_GROUP_NOT_FOUND),
        ("PERMISSIONS", TOX_ERR_GROUP_SET_PASSWORD_PERMISSIONS),
        ("TOO_LONG", TOX_ERR_GROUP_SET_PASSWORD_TOO_LONG),
        ("FAIL_SEND", TOX_ERR_GROUP_SET_PASSWORD_FAIL_SEND),
        ("MALLOC", TOX_ERR_GROUP_SET_PASSWORD_MALLOC),
        ("DISCONNECTED", TOX_ERR_GROUP_SET_PASSWORD_DISCONNECTED),
    ], module=__name__, qualname="GroupSetPasswordError.Code")

class GroupSetPeerLimitError(ApiException):
    Code = IntEnum("Code", [
        ("GROUP_NOT_FOUND", TOX_ERR_GROUP_SET_PEER_LIMIT_GROUP_NOT_FOUND),
        ("PERMISSIONS", TOX_ERR_GROUP_SET_PEER_LIMIT_PERMISSIONS),
        ("FAIL_SET", TOX_ERR_GROUP_SET_PEER_LIMIT_FAIL_SET),
        ("FAIL_SEND", TOX_ERR_GROUP_SET_PEER_LIMIT_FAIL_SEND),
        ("DISCONNECTED", TOX_ERR_GROUP_SET_PEER_LIMIT_DISCONNECTED),
    ], module=__name__, qualname="GroupSetPeerLimitError.Code")

class GroupSetPrivacyStateError(ApiException):
    Code = IntEnum("Code", [
        ("GROUP_NOT_FOUND", TOX_ERR_GROUP_SET_PRIVACY_STATE_GROUP_NOT_FOUND),
        ("PERMISSIONS", TOX_ERR_GROUP_SET_PRIVACY_STATE_PERMISSIONS),
        ("FAIL_SET", TOX_ERR_GROUP_SET_PRIVACY_STATE_FAIL_SET),
        ("FAIL_SEND", TOX_ERR_GROUP_SET_PRIVACY_STATE_FAIL_SEND),
        ("DISCONNECTED", TOX_ERR_GROUP_SET_PRIVACY_STATE_DISCONNECTED),
    ], module=__name__, qualname="GroupSetPrivacyStateError.Code")

class GroupSetRoleError(ApiException):
    Code = IntEnum("Code", [
        ("GROUP_NOT_FOUND", TOX_ERR_GROUP_SET_ROLE_GROUP_NOT_FOUND),
        ("PEER_NOT_FOUND", TOX_ERR_GROUP_SET_ROLE_PEER_NOT_FOUND),
        ("PERMISSIONS", TOX_ERR_GROUP_SET_ROLE_PERMISSIONS),
        ("ASSIGNMENT", TOX_ERR_GROUP_SET_ROLE_ASSIGNMENT),
        ("FAIL_ACTION", TOX_ERR_GROUP_SET_ROLE_FAIL_ACTION),
        ("SELF", TOX_ERR_GROUP_SET_ROLE_SELF),
    ], module=__name__, qualname="GroupSetRoleError.Code")

class GroupSetTopicLockError(ApiException):
    Code = IntEnum("Code", [
        ("GROUP_NOT_FOUND", TOX_ERR_GROUP_SET_TOPIC_LOCK_GROUP_NOT_FOUND),
        ("INVALID", TOX_ERR_GROUP_SET_TOPIC_LOCK_INVALID),
        ("PERMISSIONS", TOX_ERR_GROUP_SET_TOPIC_LOCK_PERMISSIONS),
        ("FAIL_SET", TOX_ERR_GROUP_SET_TOPIC_LOCK_FAIL_SET),
        ("FAIL_SEND", TOX_ERR_GROUP_SET_TOPIC_LOCK_FAIL_SEND),
        ("DISCONNECTED", TOX_ERR_GROUP_SET_TOPIC_LOCK_DISCONNECTED),
    ], module=__name__, qualname="GroupSetTopicLockError.Code")

class GroupSetVoiceStateError(ApiException):
    Code = IntEnum("Code", [
        ("GROUP_NOT_FOUND", TOX_ERR_GROUP_SET_VOICE_STATE_GROUP_NOT_FOUND),
        ("PERMISSIONS", TOX_ERR_GROUP_SET_VOICE_STATE_PERMISSIONS),
        ("FAIL_SET", TOX_ERR_GROUP_SET_VOICE_STATE_FAIL_SET),
        ("FAIL_SEND", TOX_ERR_GROUP_SET_VOICE_STATE_FAIL_SEND),
        ("DISCONNECTED", TOX_ERR_GROUP_SET_VOICE_STATE_DISCONNECTED),
    ], module=__name__, qualname="GroupSetVoiceStateError.Code")

class GroupStateQueryError(ApiException):
    Code = IntEnum("Code", [
        ("GROUP_NOT_FOUND", TOX_ERR_GROUP_STATE_QUERY_GROUP_NOT_FOUND),
    ], module=__name__, qualname="GroupStateQueryError.Code")

class GroupTopicSetError(ApiException):
    Code = IntEnum("Code", [
        ("GROUP_NOT_FOUND", TOX_ERR_GROUP_TOPIC_SET_GROUP_NOT_FOUND),
        ("TOO_LONG", TOX_ERR_GROUP_TOPIC_SET_TOO_LONG),
        ("PERMISSIONS", TOX_ERR_GROUP_TOPIC_SET_PERMISSIONS),
        ("FAIL_CREATE", TOX_ERR_GROUP_TOPIC_SET_FAIL_CREATE),
        ("FAIL_SEND", TOX_ERR_GROUP_TOPIC_SET_FAIL_SEND),
        ("DISCONNECTED", TOX_ERR_GROUP_TOPIC_SET_DISCONNECTED),
    ], module=__name__, qualname="GroupTopicSetError.Code")

class NewError(ApiException):
    Code = IntEnum("Code", [
        ("NULL", TOX_ERR_NEW_NULL),
        ("MALLOC", TOX_ERR_NEW_MALLOC),
        ("PORT_ALLOC", TOX_ERR_NEW_PORT_ALLOC),
        ("PROXY_BAD_TYPE", TOX_ERR_NEW_PROXY_BAD_TYPE),
        ("PROXY_BAD_HOST", TOX_ERR_NEW_PROXY_BAD_HOST),
        ("PROXY_BAD_PORT", TOX_ERR_NEW_PROXY_BAD_PORT),
        ("PROXY_NOT_FOUND", TOX_ERR_NEW_PROXY_NOT_FOUND),
        ("LOAD_ENCRYPTED", TOX_ERR_NEW_LOAD_ENCRYPTED),
        ("LOAD_BAD_FORMAT", TOX_ERR_NEW_LOAD_BAD_FORMAT),
    ], module=__name__, qualname="NewError.Code")

class OptionsNewError(ApiException):
    Code = IntEnum("Code", [
        ("MALLOC", TOX_ERR_OPTIONS_NEW_MALLOC),
    ], module=__name__, qualname="OptionsNewError.Code")

class SetInfoError(ApiException):
    Code = IntEnum("Code", [
        ("NULL", TOX_ERR_SET_INFO_NULL),
        ("TOO_LONG", TOX_ERR_SET_INFO_TOO_LONG),
    ], module=__name__, qualname="SetInfoError.Code")

class SetTypingError(ApiException):
    Code = IntEnum("Code", [
        ("FRIEND_NOT_FOUND", TOX_ERR_SET_TYPING_FRIEND_NOT_FOUND),
    ], module=__name__, qualname="SetTypingError.Code")

FileControl = IntEnum("FileControl", [
    ("RESUME", TOX_FILE_CONTROL_RESUME),
    ("PAUSE", TOX_FILE_CONTROL_PAUSE),
    ("CANCEL", TOX_FILE_CONTROL_CANCEL),
], module=__name__)

FileKind = IntEnum("FileKind", [
    ("DATA", TOX_FILE_KIND_DATA),
    ("AVATAR", TOX_FILE_KIND_AVATAR),
    ("STICKER", TOX_FILE_KIND_STICKER),
    ("SHA1", TOX_FILE_KIND_SHA1),
    ("SHA256", TOX_FILE_KIND_SHA256),
], module=__name__)

GroupExitType = IntEnum("GroupExitType", [
    ("QUIT", TOX_GROUP_EXIT_TYPE_QUIT),
    ("TIMEOUT", TOX_GROUP_EXIT_TYPE_TIMEOUT),
    ("DISCONNECTED", TOX_GROUP_EXIT_TYPE_DISCONNECTED),
    ("SELF_DISCONNECTED", TOX_GROUP_EXIT_TYPE_SELF_DISCONNECTED),
    ("KICK", TOX_GROUP_EXIT_TYPE_KICK),
    ("SYNC_ERROR", TOX_GROUP_EXIT_TYPE_SYNC_ERROR),
], module=__name__)

GroupJoinFail = IntEnum("GroupJoinFail", [
    ("PEER_LIMIT", TOX_GROUP_JOIN_FAIL_PEER_LIMIT),
    ("INVALID_PASSWORD", TOX_GROUP_JOIN_FAIL_INVALID_PASSWORD),
    ("UNKNOWN", TOX_GROUP_JOIN_FAIL_UNKNOWN),
], module=__name__)

GroupModEvent = IntEnum("GroupModEvent", [
    ("KICK", TOX_GROUP_MOD_EVENT_KICK),
    ("OBSERVER", TOX_GROUP_MOD_EVENT_OBSERVER),
    ("USER", TOX_GROUP_MOD_EVENT_USER),
    ("MODERATOR", TOX_GROUP_MOD_EVENT_MODERATOR),
], module=__name__)

GroupPrivacyState = IntEnum("GroupPrivacyState", [
    ("PUBLIC", TOX_GROUP_PRIVACY_STATE_PUBLIC),
    ("PRIVATE", TOX_GROUP_PRIVACY_STATE_PRIVATE),
], module=__name__)

GroupRole = IntEnum("GroupRole", [
    ("FOUNDER", TOX_GROUP_ROLE_FOUNDER),
    ("MODERATOR", TOX_GROUP_ROLE_MODERATOR),
    ("USER", TOX_GROUP_ROLE_USER),
    ("OBSERVER", TOX_GROUP_ROLE_OBSERVER),
], module=__name__)

GroupTopicLock = IntEnum("GroupTopicLock", [
    ("ENABLED", TOX_GROUP_TOPIC_LOCK_ENABLED),
    ("DISABLED", TOX_GROUP_TOPIC_LOCK_DISABLED),
], module=__name__)

GroupVoiceState = IntEnum("GroupVoiceState", [
    ("ALL", TOX_GROUP_VOICE_STATE_ALL),
    ("MODERATOR", TOX_GROUP_VOICE_STATE_MODERATOR),
    ("FOUNDER", TOX_GROUP_VOICE_STATE_FOUNDER),
], module=__name__)

LogLevel = IntEnum("LogLevel", [
    ("TRACE", TOX_LOG_LEVEL_TRACE),
    ("DEBUG", TOX_LOG_LEVEL_DEBUG),
    ("INFO", TOX_LOG_LEVEL_INFO),
    ("WARNING", TOX_LOG_LEVEL_WARNING),
    ("ERROR", TOX_LOG_LEVEL_ERROR),
], module=__name__)

MessageType = IntEnum("MessageType", [
    ("NORMAL", TOX_MESSAGE_TYPE_NORMAL),
    ("ACTION", TOX_MESSAGE_TYPE_ACTION),
], module=__name__)

ProxyType = IntEnum("ProxyType", [
    ("NONE", TOX_PROXY_TYPE_NONE),
    ("HTTP", TOX_PROXY_TYPE_HTTP),
    ("SOCKS5", TOX_PROXY_TYPE_SOCKS5),
], module=__name__)

SavedataType = IntEnum("SavedataType", [
    ("NONE", TOX_SAVEDATA_TYPE_NONE),
    ("TOX_SAVE", TOX_SAVEDATA_TYPE_TOX_SAVE),
    ("SECRET_KEY", TOX_SAVEDATA_TYPE_SECRET_KEY),
], module=__name__)

UserStatus = IntEnum("UserStatus", [
    ("NONE", TOX_USER_STATUS_NONE),
    ("AWAY", TOX_USER_STATUS_AWAY),
    ("BUSY", TOX_USER_STATUS_BUSY),
], module=__name__)


cdef class Options:
    cdef Tox_Options* _get(self) except *:
        if self._ptr is NULL:
            raise common.UseAfterFreeException()
        return self._ptr

    cdef void _close(self) except *:
        cdef Tox_Options* ptr = self._ptr
        self._ptr = NULL
        if ptr is not NULL:
            tox_options_free(ptr)

    def __dealloc__(self) -> None:
        self._close()

    def __enter__(self: T) -> T:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None, exc_traceback: TracebackType | None) -> None:
        self._close()

    cdef Tox_Options* _new(self):
        cdef Tox_Err_Options_New error = TOX_ERR_OPTIONS_NEW_OK
        cdef Tox_Options* ptr = tox_options_new(&error)
        if error:
            raise OptionsNewError(OptionsNewError.Code(error))
        return ptr

    def __init__(self) -> None:
        if self._ptr is not NULL:
            raise RuntimeError("Options can't be initialised twice")
        self._ptr = self._new()

    def default(self) -> None:
        tox_options_default(self._get())

    def copy(self, src: Options) -> None:
        if src._ptr is NULL:
            raise common.UseAfterFreeException()
        tox_options_copy(self._get(), src._ptr)

    @property
    def ipv6_enabled(self) -> bool:
        return tox_options_get_ipv6_enabled(self._get())

    @ipv6_enabled.setter
    def ipv6_enabled(self, ipv6_enabled: bool) -> None:
        tox_options_set_ipv6_enabled(self._get(), ipv6_enabled)

    @property
    def udp_enabled(self) -> bool:
        return tox_options_get_udp_enabled(self._get())

    @udp_enabled.setter
    def udp_enabled(self, udp_enabled: bool) -> None:
        tox_options_set_udp_enabled(self._get(), udp_enabled)

    @property
    def local_discovery_enabled(self) -> bool:
        return tox_options_get_local_discovery_enabled(self._get())

    @local_discovery_enabled.setter
    def local_discovery_enabled(self, local_discovery_enabled: bool) -> None:
        tox_options_set_local_discovery_enabled(self._get(), local_discovery_enabled)

    @property
    def dht_announcements_enabled(self) -> bool:
        return tox_options_get_dht_announcements_enabled(self._get())

    @dht_announcements_enabled.setter
    def dht_announcements_enabled(self, dht_announcements_enabled: bool) -> None:
        tox_options_set_dht_announcements_enabled(self._get(), dht_announcements_enabled)

    @property
    def proxy_type(self) -> ProxyType:
        return ProxyType(tox_options_get_proxy_type(self._get()))

    @proxy_type.setter
    def proxy_type(self, proxy_type: ProxyType) -> None:
        cdef int proxy_type_val = ProxyType(proxy_type)
        tox_options_set_proxy_type(self._get(), <Tox_Proxy_Type> proxy_type_val)

    @property
    def proxy_host(self) -> str:
        cdef const char* res = tox_options_get_proxy_host(self._get())
        return res.decode("utf-8") if res is not NULL else ""

    @proxy_host.setter
    def proxy_host(self, proxy_host: str) -> None:
        cdef bytes proxy_host_bytes = common.encode_cstr("proxy_host", proxy_host)
        tox_options_set_experimental_owned_data(self._get(), True)
        if not tox_options_set_proxy_host(self._get(), proxy_host_bytes):
            raise MemoryError()

    @property
    def proxy_port(self) -> int:
        return tox_options_get_proxy_port(self._get())

    @proxy_port.setter
    def proxy_port(self, proxy_port: int) -> None:
        tox_options_set_proxy_port(self._get(), proxy_port)

    @property
    def start_port(self) -> int:
        return tox_options_get_start_port(self._get())

    @start_port.setter
    def start_port(self, start_port: int) -> None:
        tox_options_set_start_port(self._get(), start_port)

    @property
    def end_port(self) -> int:
        return tox_options_get_end_port(self._get())

    @end_port.setter
    def end_port(self, end_port: int) -> None:
        tox_options_set_end_port(self._get(), end_port)

    @property
    def tcp_port(self) -> int:
        return tox_options_get_tcp_port(self._get())

    @tcp_port.setter
    def tcp_port(self, tcp_port: int) -> None:
        tox_options_set_tcp_port(self._get(), tcp_port)

    @property
    def hole_punching_enabled(self) -> bool:
        return tox_options_get_hole_punching_enabled(self._get())

    @hole_punching_enabled.setter
    def hole_punching_enabled(self, hole_punching_enabled: bool) -> None:
        tox_options_set_hole_punching_enabled(self._get(), hole_punching_enabled)

    @property
    def savedata_type(self) -> SavedataType:
        return SavedataType(tox_options_get_savedata_type(self._get()))

    @savedata_type.setter
    def savedata_type(self, savedata_type: SavedataType) -> None:
        cdef int savedata_type_val = SavedataType(savedata_type)
        tox_options_set_savedata_type(self._get(), <Tox_Savedata_Type> savedata_type_val)

    @property
    def savedata(self) -> bytes:
        cdef const uint8_t* data = tox_options_get_savedata_data(self._get())
        cdef size_t length = tox_options_get_savedata_length(self._get())
        if (data is NULL) or (length == 0):
            return b""
        return data[:length]

    @savedata.setter
    def savedata(self, savedata: bytes) -> None:
        tox_options_set_experimental_owned_data(self._get(), True)
        if not tox_options_set_savedata_data(self._get(), <const uint8_t*> savedata if len(savedata) != 0 else NULL, len(savedata)):
            raise MemoryError()

    @property
    def experimental_groups_persistence(self) -> bool:
        return tox_options_get_experimental_groups_persistence(self._get())

    @experimental_groups_persistence.setter
    def experimental_groups_persistence(self, experimental_groups_persistence: bool) -> None:
        tox_options_set_experimental_groups_persistence(self._get(), experimental_groups_persistence)

    @property
    def experimental_disable_dns(self) -> bool:
        return tox_options_get_experimental_disable_dns(self._get())

    @experimental_disable_dns.setter
    def experimental_disable_dns(self, experimental_disable_dns: bool) -> None:
        tox_options_set_experimental_disable_dns(self._get(), experimental_disable_dns)


cdef:
    cdef void handle_self_connection_status(CTox* tox, Tox_Connection connection_status, void* user_data) noexcept with gil:
        event = events.SelfConnectionStatusEvent(Connection(connection_status))
        (<Tox> user_data)._events.append(event)
    cdef void handle_friend_name(CTox* tox, Tox_Friend_Number friend_number, const uint8_t* name, size_t name_length, void* user_data) noexcept with gil:
        event = events.FriendNameEvent(friend_number, name[:name_length] if name is not NULL else b"")
        (<Tox> user_data)._events.append(event)
    cdef void handle_friend_status_message(CTox* tox, Tox_Friend_Number friend_number, const uint8_t* message, size_t message_length, void* user_data) noexcept with gil:
        event = events.FriendStatusMessageEvent(friend_number, message[:message_length] if message is not NULL else b"")
        (<Tox> user_data)._events.append(event)
    cdef void handle_friend_status(CTox* tox, Tox_Friend_Number friend_number, Tox_User_Status status, void* user_data) noexcept with gil:
        event = events.FriendStatusEvent(friend_number, UserStatus(status))
        (<Tox> user_data)._events.append(event)
    cdef void handle_friend_connection_status(CTox* tox, Tox_Friend_Number friend_number, Tox_Connection connection_status, void* user_data) noexcept with gil:
        event = events.FriendConnectionStatusEvent(friend_number, Connection(connection_status))
        (<Tox> user_data)._events.append(event)
    cdef void handle_friend_typing(CTox* tox, Tox_Friend_Number friend_number, bool typing, void* user_data) noexcept with gil:
        event = events.FriendTypingEvent(friend_number, typing)
        (<Tox> user_data)._events.append(event)
    cdef void handle_friend_read_receipt(CTox* tox, Tox_Friend_Number friend_number, Tox_Friend_Message_Id message_id, void* user_data) noexcept with gil:
        event = events.FriendReadReceiptEvent(friend_number, message_id)
        (<Tox> user_data)._events.append(event)
    cdef void handle_friend_request(CTox* tox, const uint8_t* public_key, const uint8_t* message, size_t message_length, void* user_data) noexcept with gil:
        event = events.FriendRequestEvent(public_key[:tox_public_key_size()] if public_key is not NULL else b"", message[:message_length] if message is not NULL else b"")
        (<Tox> user_data)._events.append(event)
    cdef void handle_friend_message(CTox* tox, Tox_Friend_Number friend_number, Tox_Message_Type type, const uint8_t* message, size_t message_length, void* user_data) noexcept with gil:
        event = events.FriendMessageEvent(friend_number, MessageType(type), message[:message_length] if message is not NULL else b"")
        (<Tox> user_data)._events.append(event)
    cdef void handle_file_recv_control(CTox* tox, Tox_Friend_Number friend_number, Tox_File_Number file_number, Tox_File_Control control, void* user_data) noexcept with gil:
        event = events.FileRecvControlEvent(friend_number, file_number, FileControl(control))
        (<Tox> user_data)._events.append(event)
    cdef void handle_file_chunk_request(CTox* tox, Tox_Friend_Number friend_number, Tox_File_Number file_number, uint64_t position, size_t length, void* user_data) noexcept with gil:
        event = events.FileChunkRequestEvent(friend_number, file_number, position, length)
        (<Tox> user_data)._events.append(event)
    cdef void handle_file_recv(CTox* tox, Tox_Friend_Number friend_number, Tox_File_Number file_number, uint32_t kind, uint64_t file_size, const uint8_t* filename, size_t filename_length, void* user_data) noexcept with gil:
        event = events.FileRecvEvent(friend_number, file_number, kind, file_size, filename[:filename_length] if filename is not NULL else b"")
        (<Tox> user_data)._events.append(event)
    cdef void handle_file_recv_chunk(CTox* tox, Tox_Friend_Number friend_number, Tox_File_Number file_number, uint64_t position, const uint8_t* data, size_t data_length, void* user_data) noexcept with gil:
        event = events.FileRecvChunkEvent(friend_number, file_number, position, data[:data_length] if data is not NULL else b"")
        (<Tox> user_data)._events.append(event)
    cdef void handle_conference_invite(CTox* tox, Tox_Friend_Number friend_number, Tox_Conference_Type type, const uint8_t* cookie, size_t cookie_length, void* user_data) noexcept with gil:
        event = events.ConferenceInviteEvent(friend_number, ConferenceType(type), cookie[:cookie_length] if cookie is not NULL else b"")
        (<Tox> user_data)._events.append(event)
    cdef void handle_conference_connected(CTox* tox, Tox_Conference_Number conference_number, void* user_data) noexcept with gil:
        event = events.ConferenceConnectedEvent(conference_number)
        (<Tox> user_data)._events.append(event)
    cdef void handle_conference_message(CTox* tox, Tox_Conference_Number conference_number, Tox_Conference_Peer_Number peer_number, Tox_Message_Type type, const uint8_t* message, size_t message_length, void* user_data) noexcept with gil:
        event = events.ConferenceMessageEvent(conference_number, peer_number, MessageType(type), message[:message_length] if message is not NULL else b"")
        (<Tox> user_data)._events.append(event)
    cdef void handle_conference_title(CTox* tox, Tox_Conference_Number conference_number, Tox_Conference_Peer_Number peer_number, const uint8_t* title, size_t title_length, void* user_data) noexcept with gil:
        event = events.ConferenceTitleEvent(conference_number, peer_number, title[:title_length] if title is not NULL else b"")
        (<Tox> user_data)._events.append(event)
    cdef void handle_conference_peer_name(CTox* tox, Tox_Conference_Number conference_number, Tox_Conference_Peer_Number peer_number, const uint8_t* name, size_t name_length, void* user_data) noexcept with gil:
        event = events.ConferencePeerNameEvent(conference_number, peer_number, name[:name_length] if name is not NULL else b"")
        (<Tox> user_data)._events.append(event)
    cdef void handle_conference_peer_list_changed(CTox* tox, Tox_Conference_Number conference_number, void* user_data) noexcept with gil:
        event = events.ConferencePeerListChangedEvent(conference_number)
        (<Tox> user_data)._events.append(event)
    cdef void handle_friend_lossy_packet(CTox* tox, Tox_Friend_Number friend_number, const uint8_t* data, size_t data_length, void* user_data) noexcept with gil:
        event = events.FriendLossyPacketEvent(friend_number, data[:data_length] if data is not NULL else b"")
        (<Tox> user_data)._events.append(event)
    cdef void handle_friend_lossless_packet(CTox* tox, Tox_Friend_Number friend_number, const uint8_t* data, size_t data_length, void* user_data) noexcept with gil:
        event = events.FriendLosslessPacketEvent(friend_number, data[:data_length] if data is not NULL else b"")
        (<Tox> user_data)._events.append(event)
    cdef void handle_group_peer_name(CTox* tox, Tox_Group_Number group_number, Tox_Group_Peer_Number peer_id, const uint8_t* name, size_t name_length, void* user_data) noexcept with gil:
        event = events.GroupPeerNameEvent(group_number, peer_id, name[:name_length] if name is not NULL else b"")
        (<Tox> user_data)._events.append(event)
    cdef void handle_group_peer_status(CTox* tox, Tox_Group_Number group_number, Tox_Group_Peer_Number peer_id, Tox_User_Status status, void* user_data) noexcept with gil:
        event = events.GroupPeerStatusEvent(group_number, peer_id, UserStatus(status))
        (<Tox> user_data)._events.append(event)
    cdef void handle_group_topic(CTox* tox, Tox_Group_Number group_number, Tox_Group_Peer_Number peer_id, const uint8_t* topic, size_t topic_length, void* user_data) noexcept with gil:
        event = events.GroupTopicEvent(group_number, peer_id, topic[:topic_length] if topic is not NULL else b"")
        (<Tox> user_data)._events.append(event)
    cdef void handle_group_privacy_state(CTox* tox, Tox_Group_Number group_number, Tox_Group_Privacy_State privacy_state, void* user_data) noexcept with gil:
        event = events.GroupPrivacyStateEvent(group_number, GroupPrivacyState(privacy_state))
        (<Tox> user_data)._events.append(event)
    cdef void handle_group_voice_state(CTox* tox, Tox_Group_Number group_number, Tox_Group_Voice_State voice_state, void* user_data) noexcept with gil:
        event = events.GroupVoiceStateEvent(group_number, GroupVoiceState(voice_state))
        (<Tox> user_data)._events.append(event)
    cdef void handle_group_topic_lock(CTox* tox, Tox_Group_Number group_number, Tox_Group_Topic_Lock topic_lock, void* user_data) noexcept with gil:
        event = events.GroupTopicLockEvent(group_number, GroupTopicLock(topic_lock))
        (<Tox> user_data)._events.append(event)
    cdef void handle_group_peer_limit(CTox* tox, Tox_Group_Number group_number, uint32_t peer_limit, void* user_data) noexcept with gil:
        event = events.GroupPeerLimitEvent(group_number, peer_limit)
        (<Tox> user_data)._events.append(event)
    cdef void handle_group_password(CTox* tox, Tox_Group_Number group_number, const uint8_t* password, size_t password_length, void* user_data) noexcept with gil:
        event = events.GroupPasswordEvent(group_number, password[:password_length] if password is not NULL else b"")
        (<Tox> user_data)._events.append(event)
    cdef void handle_group_message(CTox* tox, Tox_Group_Number group_number, Tox_Group_Peer_Number peer_id, Tox_Message_Type message_type, const uint8_t* message, size_t message_length, Tox_Group_Message_Id message_id, void* user_data) noexcept with gil:
        event = events.GroupMessageEvent(group_number, peer_id, MessageType(message_type), message[:message_length] if message is not NULL else b"", message_id)
        (<Tox> user_data)._events.append(event)
    cdef void handle_group_private_message(CTox* tox, Tox_Group_Number group_number, Tox_Group_Peer_Number peer_id, Tox_Message_Type message_type, const uint8_t* message, size_t message_length, Tox_Group_Message_Id message_id, void* user_data) noexcept with gil:
        event = events.GroupPrivateMessageEvent(group_number, peer_id, MessageType(message_type), message[:message_length] if message is not NULL else b"", message_id)
        (<Tox> user_data)._events.append(event)
    cdef void handle_group_custom_packet(CTox* tox, Tox_Group_Number group_number, Tox_Group_Peer_Number peer_id, const uint8_t* data, size_t data_length, void* user_data) noexcept with gil:
        event = events.GroupCustomPacketEvent(group_number, peer_id, data[:data_length] if data is not NULL else b"")
        (<Tox> user_data)._events.append(event)
    cdef void handle_group_custom_private_packet(CTox* tox, Tox_Group_Number group_number, Tox_Group_Peer_Number peer_id, const uint8_t* data, size_t data_length, void* user_data) noexcept with gil:
        event = events.GroupCustomPrivatePacketEvent(group_number, peer_id, data[:data_length] if data is not NULL else b"")
        (<Tox> user_data)._events.append(event)
    cdef void handle_group_invite(CTox* tox, Tox_Friend_Number friend_number, const uint8_t* invite_data, size_t invite_data_length, const uint8_t* group_name, size_t group_name_length, void* user_data) noexcept with gil:
        event = events.GroupInviteEvent(friend_number, invite_data[:invite_data_length] if invite_data is not NULL else b"", group_name[:group_name_length] if group_name is not NULL else b"")
        (<Tox> user_data)._events.append(event)
    cdef void handle_group_peer_join(CTox* tox, Tox_Group_Number group_number, Tox_Group_Peer_Number peer_id, void* user_data) noexcept with gil:
        event = events.GroupPeerJoinEvent(group_number, peer_id)
        (<Tox> user_data)._events.append(event)
    cdef void handle_group_peer_exit(CTox* tox, Tox_Group_Number group_number, Tox_Group_Peer_Number peer_id, Tox_Group_Exit_Type exit_type, const uint8_t* name, size_t name_length, const uint8_t* part_message, size_t part_message_length, void* user_data) noexcept with gil:
        event = events.GroupPeerExitEvent(group_number, peer_id, GroupExitType(exit_type), name[:name_length] if name is not NULL else b"", part_message[:part_message_length] if part_message is not NULL else b"")
        (<Tox> user_data)._events.append(event)
    cdef void handle_group_self_join(CTox* tox, Tox_Group_Number group_number, void* user_data) noexcept with gil:
        event = events.GroupSelfJoinEvent(group_number)
        (<Tox> user_data)._events.append(event)
    cdef void handle_group_join_fail(CTox* tox, Tox_Group_Number group_number, Tox_Group_Join_Fail fail_type, void* user_data) noexcept with gil:
        event = events.GroupJoinFailEvent(group_number, GroupJoinFail(fail_type))
        (<Tox> user_data)._events.append(event)
    cdef void handle_group_moderation(CTox* tox, Tox_Group_Number group_number, Tox_Group_Peer_Number source_peer_id, Tox_Group_Peer_Number target_peer_id, Tox_Group_Mod_Event mod_type, void* user_data) noexcept with gil:
        event = events.GroupModerationEvent(group_number, source_peer_id, target_peer_id, GroupModEvent(mod_type))
        (<Tox> user_data)._events.append(event)
    cdef void install_handlers(Tox self, CTox* ptr) noexcept:
        tox_callback_self_connection_status(ptr, handle_self_connection_status)
        tox_callback_friend_name(ptr, handle_friend_name)
        tox_callback_friend_status_message(ptr, handle_friend_status_message)
        tox_callback_friend_status(ptr, handle_friend_status)
        tox_callback_friend_connection_status(ptr, handle_friend_connection_status)
        tox_callback_friend_typing(ptr, handle_friend_typing)
        tox_callback_friend_read_receipt(ptr, handle_friend_read_receipt)
        tox_callback_friend_request(ptr, handle_friend_request)
        tox_callback_friend_message(ptr, handle_friend_message)
        tox_callback_file_recv_control(ptr, handle_file_recv_control)
        tox_callback_file_chunk_request(ptr, handle_file_chunk_request)
        tox_callback_file_recv(ptr, handle_file_recv)
        tox_callback_file_recv_chunk(ptr, handle_file_recv_chunk)
        tox_callback_conference_invite(ptr, handle_conference_invite)
        tox_callback_conference_connected(ptr, handle_conference_connected)
        tox_callback_conference_message(ptr, handle_conference_message)
        tox_callback_conference_title(ptr, handle_conference_title)
        tox_callback_conference_peer_name(ptr, handle_conference_peer_name)
        tox_callback_conference_peer_list_changed(ptr, handle_conference_peer_list_changed)
        tox_callback_friend_lossy_packet(ptr, handle_friend_lossy_packet)
        tox_callback_friend_lossless_packet(ptr, handle_friend_lossless_packet)
        tox_callback_group_peer_name(ptr, handle_group_peer_name)
        tox_callback_group_peer_status(ptr, handle_group_peer_status)
        tox_callback_group_topic(ptr, handle_group_topic)
        tox_callback_group_privacy_state(ptr, handle_group_privacy_state)
        tox_callback_group_voice_state(ptr, handle_group_voice_state)
        tox_callback_group_topic_lock(ptr, handle_group_topic_lock)
        tox_callback_group_peer_limit(ptr, handle_group_peer_limit)
        tox_callback_group_password(ptr, handle_group_password)
        tox_callback_group_message(ptr, handle_group_message)
        tox_callback_group_private_message(ptr, handle_group_private_message)
        tox_callback_group_custom_packet(ptr, handle_group_custom_packet)
        tox_callback_group_custom_private_packet(ptr, handle_group_custom_private_packet)
        tox_callback_group_invite(ptr, handle_group_invite)
        tox_callback_group_peer_join(ptr, handle_group_peer_join)
        tox_callback_group_peer_exit(ptr, handle_group_peer_exit)
        tox_callback_group_self_join(ptr, handle_group_self_join)
        tox_callback_group_join_fail(ptr, handle_group_join_fail)
        tox_callback_group_moderation(ptr, handle_group_moderation)


cdef class Tox:
    cdef CTox* _get(self) except *:
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
        cdef CTox* ptr = NULL
        with nogil:
            PyThread_acquire_lock(self._lock, WAIT_LOCK)
            ptr = self._ptr
            self._ptr = NULL
            PyThread_release_lock(self._lock)
        if self._av is not None:
            self._av.__exit__(None, None, None)
        with nogil:
            if ptr is not NULL:
                tox_kill(ptr)

    def __dealloc__(self) -> None:
        self._close()
        if self._lock is not NULL:
            PyThread_free_lock(self._lock)
            self._lock = NULL

    def __enter__(self: T) -> T:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None, exc_traceback: TracebackType | None) -> None:
        self._close()

    cdef CTox* _new(self, Options options):
        if options is None:
            options = Options()
        if options._ptr is NULL:
            raise common.UseAfterFreeException()
        tox_options_set_experimental_thread_safety(options._ptr, True)
        cdef Tox_Err_New error = TOX_ERR_NEW_OK
        cdef CTox* ptr = tox_new(options._ptr, &error)
        if error:
            raise NewError(NewError.Code(error))
        return ptr

    def __init__(self, options: Optional[Options] = None) -> None:
        if self._ptr is not NULL:
            raise RuntimeError("Tox can't be initialised twice")
        self._ptr = self._new(options)
        install_handlers(self, self._ptr)

    def bootstrap(self, host: str, port: int, public_key: bytes) -> None:
        common.check_exact_len("public_key", public_key, tox_dht_id_size())
        cdef bytes host_bytes = common.encode_cstr("host", host)
        cdef const char* host_cstr = host_bytes
        cdef uint16_t port_c = port
        cdef const uint8_t* public_key_ptr = public_key
        cdef Tox_Err_Bootstrap err = TOX_ERR_BOOTSTRAP_OK
        with nogil:
            self._acquire()
            tox_bootstrap(self._ptr, host_cstr, port_c, public_key_ptr, &err)
            self._release()
        if err:
            raise BootstrapError(BootstrapError.Code(err))

    def add_tcp_relay(self, host: str, port: int, public_key: bytes) -> None:
        common.check_exact_len("public_key", public_key, tox_dht_id_size())
        cdef bytes host_bytes = common.encode_cstr("host", host)
        cdef const char* host_cstr = host_bytes
        cdef uint16_t port_c = port
        cdef const uint8_t* public_key_ptr = public_key
        cdef Tox_Err_Bootstrap err = TOX_ERR_BOOTSTRAP_OK
        with nogil:
            self._acquire()
            tox_add_tcp_relay(self._ptr, host_cstr, port_c, public_key_ptr, &err)
            self._release()
        if err:
            raise BootstrapError(BootstrapError.Code(err))

    @property
    def iteration_interval(self) -> int:
        cdef uint32_t res = <uint32_t> 0
        with nogil:
            self._acquire()
            res = tox_iteration_interval(self._ptr)
            self._release()
        return res

    def iterate(self) -> list[events.Event]:
        cdef void* me = <void*> self
        with nogil:
            self._acquire()
            tox_iterate(self._ptr, me)
            self._release()
        cdef object result = self._events
        self._events = []
        return result

    def set_typing(self, friend_number: Tox_Friend_Number, typing: bool) -> None:
        cdef bool typing_c = typing
        cdef Tox_Err_Set_Typing err = TOX_ERR_SET_TYPING_OK
        with nogil:
            self._acquire()
            tox_self_set_typing(self._ptr, friend_number, typing_c, &err)
            self._release()
        if err:
            raise SetTypingError(SetTypingError.Code(err))

    def file_control(self, friend_number: Tox_Friend_Number, file_number: Tox_File_Number, control: FileControl) -> None:
        cdef int control_val = FileControl(control)
        cdef Tox_Err_File_Control err = TOX_ERR_FILE_CONTROL_OK
        with nogil:
            self._acquire()
            tox_file_control(self._ptr, friend_number, file_number, <Tox_File_Control> control_val, &err)
            self._release()
        if err:
            raise FileControlError(FileControlError.Code(err))

    def file_seek(self, friend_number: Tox_Friend_Number, file_number: Tox_File_Number, position: int) -> None:
        cdef uint64_t position_c = position
        cdef Tox_Err_File_Seek err = TOX_ERR_FILE_SEEK_OK
        with nogil:
            self._acquire()
            tox_file_seek(self._ptr, friend_number, file_number, position_c, &err)
            self._release()
        if err:
            raise FileSeekError(FileSeekError.Code(err))

    def file_get_file_id(self, friend_number: Tox_Friend_Number, file_number: Tox_File_Number) -> bytes:
        cdef Tox_Err_File_Get err = TOX_ERR_FILE_GET_OK
        cdef size_t size = 0
        cdef uint8_t* buf = NULL
        with nogil:
            self._acquire()
            size = tox_file_id_length()
            buf = <uint8_t*> malloc((size if size > 0 else 1) * sizeof(uint8_t))
            if buf is not NULL:
                tox_file_get_file_id(self._ptr, friend_number, file_number, buf, &err)
            self._release()
        if err:
            free(buf)
            raise FileGetError(FileGetError.Code(err))
        return _take_uint8_t(buf, size)

    def file_send_chunk(self, friend_number: Tox_Friend_Number, file_number: Tox_File_Number, position: int, data: bytes) -> None:
        cdef uint64_t position_c = position
        cdef const uint8_t* data_ptr = data
        cdef size_t data_len = len(data)
        cdef Tox_Err_File_Send_Chunk err = TOX_ERR_FILE_SEND_CHUNK_OK
        with nogil:
            self._acquire()
            tox_file_send_chunk(self._ptr, friend_number, file_number, position_c, data_ptr, data_len, &err)
            self._release()
        if err:
            raise FileSendChunkError(FileSendChunkError.Code(err))

    def conference_invite(self, friend_number: Tox_Friend_Number, conference_number: Tox_Conference_Number) -> None:
        cdef Tox_Err_Conference_Invite err = TOX_ERR_CONFERENCE_INVITE_OK
        with nogil:
            self._acquire()
            tox_conference_invite(self._ptr, friend_number, conference_number, &err)
            self._release()
        if err:
            raise ConferenceInviteError(ConferenceInviteError.Code(err))

    @property
    def savedata(self) -> bytes:
        cdef size_t size = 0
        cdef uint8_t* buf = NULL
        with nogil:
            self._acquire()
            size = tox_get_savedata_size(self._ptr)
            buf = <uint8_t*> malloc((size if size > 0 else 1) * sizeof(uint8_t))
            if buf is not NULL:
                tox_get_savedata(self._ptr, buf)
            self._release()
        return _take_uint8_t(buf, size)

    @property
    def connection_status(self) -> Connection:
        cdef Tox_Connection res = <Tox_Connection> 0
        with nogil:
            self._acquire()
            res = tox_self_get_connection_status(self._ptr)
            self._release()
        return Connection(res)

    @property
    def address(self) -> bytes:
        cdef size_t size = 0
        cdef uint8_t* buf = NULL
        with nogil:
            self._acquire()
            size = tox_address_size()
            buf = <uint8_t*> malloc((size if size > 0 else 1) * sizeof(uint8_t))
            if buf is not NULL:
                tox_self_get_address(self._ptr, buf)
            self._release()
        return _take_uint8_t(buf, size)

    @property
    def nospam(self) -> int:
        cdef uint32_t res = <uint32_t> 0
        with nogil:
            self._acquire()
            res = tox_self_get_nospam(self._ptr)
            self._release()
        return res

    @nospam.setter
    def nospam(self, nospam: int) -> None:
        cdef uint32_t nospam_c = nospam
        with nogil:
            self._acquire()
            tox_self_set_nospam(self._ptr, nospam_c)
            self._release()

    @property
    def public_key(self) -> bytes:
        cdef size_t size = 0
        cdef uint8_t* buf = NULL
        with nogil:
            self._acquire()
            size = tox_public_key_size()
            buf = <uint8_t*> malloc((size if size > 0 else 1) * sizeof(uint8_t))
            if buf is not NULL:
                tox_self_get_public_key(self._ptr, buf)
            self._release()
        return _take_uint8_t(buf, size)

    @property
    def secret_key(self) -> bytes:
        cdef size_t size = 0
        cdef uint8_t* buf = NULL
        with nogil:
            self._acquire()
            size = tox_secret_key_size()
            buf = <uint8_t*> malloc((size if size > 0 else 1) * sizeof(uint8_t))
            if buf is not NULL:
                tox_self_get_secret_key(self._ptr, buf)
            self._release()
        return _take_uint8_t(buf, size)

    @property
    def name(self) -> bytes:
        cdef size_t size = 0
        cdef uint8_t* buf = NULL
        with nogil:
            self._acquire()
            size = tox_self_get_name_size(self._ptr)
            buf = <uint8_t*> malloc((size if size > 0 else 1) * sizeof(uint8_t))
            if buf is not NULL:
                tox_self_get_name(self._ptr, buf)
            self._release()
        return _take_uint8_t(buf, size)

    @name.setter
    def name(self, name: bytes) -> None:
        cdef const uint8_t* name_ptr = name
        cdef size_t name_len = len(name)
        cdef Tox_Err_Set_Info err = TOX_ERR_SET_INFO_OK
        with nogil:
            self._acquire()
            tox_self_set_name(self._ptr, name_ptr, name_len, &err)
            self._release()
        if err:
            raise SetInfoError(SetInfoError.Code(err))

    @property
    def status_message(self) -> bytes:
        cdef size_t size = 0
        cdef uint8_t* buf = NULL
        with nogil:
            self._acquire()
            size = tox_self_get_status_message_size(self._ptr)
            buf = <uint8_t*> malloc((size if size > 0 else 1) * sizeof(uint8_t))
            if buf is not NULL:
                tox_self_get_status_message(self._ptr, buf)
            self._release()
        return _take_uint8_t(buf, size)

    @status_message.setter
    def status_message(self, status_message: bytes) -> None:
        cdef const uint8_t* status_message_ptr = status_message
        cdef size_t status_message_len = len(status_message)
        cdef Tox_Err_Set_Info err = TOX_ERR_SET_INFO_OK
        with nogil:
            self._acquire()
            tox_self_set_status_message(self._ptr, status_message_ptr, status_message_len, &err)
            self._release()
        if err:
            raise SetInfoError(SetInfoError.Code(err))

    @property
    def status(self) -> UserStatus:
        cdef Tox_User_Status res = <Tox_User_Status> 0
        with nogil:
            self._acquire()
            res = tox_self_get_status(self._ptr)
            self._release()
        return UserStatus(res)

    @status.setter
    def status(self, status: UserStatus) -> None:
        cdef int status_val = UserStatus(status)
        with nogil:
            self._acquire()
            tox_self_set_status(self._ptr, <Tox_User_Status> status_val)
            self._release()

    @property
    def friend_list(self) -> list[Tox_Friend_Number]:
        cdef size_t size = 0
        cdef uint32_t* buf = NULL
        with nogil:
            self._acquire()
            size = tox_self_get_friend_list_size(self._ptr)
            buf = <uint32_t*> malloc((size if size > 0 else 1) * sizeof(uint32_t))
            if buf is not NULL:
                tox_self_get_friend_list(self._ptr, buf)
            self._release()
        return _take_uint32_t(buf, size)

    @property
    def conference_chatlist(self) -> list[Tox_Conference_Number]:
        cdef size_t size = 0
        cdef uint32_t* buf = NULL
        with nogil:
            self._acquire()
            size = tox_conference_get_chatlist_size(self._ptr)
            buf = <uint32_t*> malloc((size if size > 0 else 1) * sizeof(uint32_t))
            if buf is not NULL:
                tox_conference_get_chatlist(self._ptr, buf)
            self._release()
        return _take_uint32_t(buf, size)

    @property
    def dht_id(self) -> bytes:
        cdef size_t size = 0
        cdef uint8_t* buf = NULL
        with nogil:
            self._acquire()
            size = tox_dht_id_size()
            buf = <uint8_t*> malloc((size if size > 0 else 1) * sizeof(uint8_t))
            if buf is not NULL:
                tox_self_get_dht_id(self._ptr, buf)
            self._release()
        return _take_uint8_t(buf, size)

    @property
    def udp_port(self) -> int:
        cdef Tox_Err_Get_Port err = TOX_ERR_GET_PORT_OK
        cdef uint16_t res = <uint16_t> 0
        with nogil:
            self._acquire()
            res = tox_self_get_udp_port(self._ptr, &err)
            self._release()
        if err:
            raise GetPortError(GetPortError.Code(err))
        return res

    @property
    def tcp_port(self) -> int:
        cdef Tox_Err_Get_Port err = TOX_ERR_GET_PORT_OK
        cdef uint16_t res = <uint16_t> 0
        with nogil:
            self._acquire()
            res = tox_self_get_tcp_port(self._ptr, &err)
            self._release()
        if err:
            raise GetPortError(GetPortError.Code(err))
        return res

    @property
    def group_list(self) -> list[Tox_Group_Number]:
        cdef size_t size = 0
        cdef uint32_t* buf = NULL
        with nogil:
            self._acquire()
            size = tox_group_get_group_list_size(self._ptr)
            buf = <uint32_t*> malloc((size if size > 0 else 1) * sizeof(uint32_t))
            if buf is not NULL:
                tox_group_get_group_list(self._ptr, buf)
            self._release()
        return _take_uint32_t(buf, size)

    def conference_new(self) -> Tox_Conference_Number:
        cdef Tox_Err_Conference_New err = TOX_ERR_CONFERENCE_NEW_OK
        cdef Tox_Conference_Number res = <Tox_Conference_Number> 0
        with nogil:
            self._acquire()
            res = tox_conference_new(self._ptr, &err)
            self._release()
        if err:
            raise ConferenceNewError(ConferenceNewError.Code(err))
        return res

    def conference_delete(self, conference_number: Tox_Conference_Number) -> None:
        cdef Tox_Err_Conference_Delete err = TOX_ERR_CONFERENCE_DELETE_OK
        with nogil:
            self._acquire()
            tox_conference_delete(self._ptr, conference_number, &err)
            self._release()
        if err:
            raise ConferenceDeleteError(ConferenceDeleteError.Code(err))

    def conference_peer_count(self, conference_number: Tox_Conference_Number) -> int:
        cdef Tox_Err_Conference_Peer_Query err = TOX_ERR_CONFERENCE_PEER_QUERY_OK
        cdef uint32_t res = <uint32_t> 0
        with nogil:
            self._acquire()
            res = tox_conference_peer_count(self._ptr, conference_number, &err)
            self._release()
        if err:
            raise ConferencePeerQueryError(ConferencePeerQueryError.Code(err))
        return res

    def conference_offline_peer_count(self, conference_number: Tox_Conference_Number) -> int:
        cdef Tox_Err_Conference_Peer_Query err = TOX_ERR_CONFERENCE_PEER_QUERY_OK
        cdef uint32_t res = <uint32_t> 0
        with nogil:
            self._acquire()
            res = tox_conference_offline_peer_count(self._ptr, conference_number, &err)
            self._release()
        if err:
            raise ConferencePeerQueryError(ConferencePeerQueryError.Code(err))
        return res

    def conference_join(self, friend_number: Tox_Friend_Number, cookie: bytes) -> Tox_Conference_Number:
        cdef const uint8_t* cookie_ptr = cookie
        cdef size_t cookie_len = len(cookie)
        cdef Tox_Err_Conference_Join err = TOX_ERR_CONFERENCE_JOIN_OK
        cdef Tox_Conference_Number res = <Tox_Conference_Number> 0
        with nogil:
            self._acquire()
            res = tox_conference_join(self._ptr, friend_number, cookie_ptr, cookie_len, &err)
            self._release()
        if err:
            raise ConferenceJoinError(ConferenceJoinError.Code(err))
        return res

    def conference_send_message(self, conference_number: Tox_Conference_Number, type: MessageType, message: bytes) -> None:
        cdef int type_val = MessageType(type)
        cdef const uint8_t* message_ptr = message
        cdef size_t message_len = len(message)
        cdef Tox_Err_Conference_Send_Message err = TOX_ERR_CONFERENCE_SEND_MESSAGE_OK
        with nogil:
            self._acquire()
            tox_conference_send_message(self._ptr, conference_number, <Tox_Message_Type> type_val, message_ptr, message_len, &err)
            self._release()
        if err:
            raise ConferenceSendMessageError(ConferenceSendMessageError.Code(err))

    def conference_by_id(self, id: bytes) -> Tox_Conference_Number:
        common.check_exact_len("id", id, tox_conference_id_size())
        cdef const uint8_t* id_ptr = id
        cdef Tox_Err_Conference_By_Id err = TOX_ERR_CONFERENCE_BY_ID_OK
        cdef Tox_Conference_Number res = <Tox_Conference_Number> 0
        with nogil:
            self._acquire()
            res = tox_conference_by_id(self._ptr, id_ptr, &err)
            self._release()
        if err:
            raise ConferenceByIdError(ConferenceByIdError.Code(err))
        return res

    def conference_get_id(self, conference_number: Tox_Conference_Number) -> bytes:
        cdef size_t size = 0
        cdef uint8_t* buf = NULL
        cdef bool found = False
        with nogil:
            self._acquire()
            size = tox_conference_id_size()
            buf = <uint8_t*> malloc((size if size > 0 else 1) * sizeof(uint8_t))
            if buf is not NULL:
                found = tox_conference_get_id(self._ptr, conference_number, buf)
            self._release()
        if not found:
            free(buf)
            raise KeyError(conference_number)
        return _take_uint8_t(buf, size)

    def conference_set_max_offline(self, conference_number: Tox_Conference_Number, max_offline: int) -> None:
        cdef uint32_t max_offline_c = max_offline
        cdef Tox_Err_Conference_Set_Max_Offline err = TOX_ERR_CONFERENCE_SET_MAX_OFFLINE_OK
        with nogil:
            self._acquire()
            tox_conference_set_max_offline(self._ptr, conference_number, max_offline_c, &err)
            self._release()
        if err:
            raise ConferenceSetMaxOfflineError(ConferenceSetMaxOfflineError.Code(err))

    def conference_get_title(self, conference_number: Tox_Conference_Number) -> bytes:
        cdef Tox_Err_Conference_Title err = TOX_ERR_CONFERENCE_TITLE_OK
        cdef size_t size = 0
        cdef uint8_t* buf = NULL
        with nogil:
            self._acquire()
            size = tox_conference_get_title_size(self._ptr, conference_number, &err)
            if not err:
                buf = <uint8_t*> malloc((size if size > 0 else 1) * sizeof(uint8_t))
                if buf is not NULL:
                    tox_conference_get_title(self._ptr, conference_number, buf, &err)
            self._release()
        if err:
            free(buf)
            raise ConferenceTitleError(ConferenceTitleError.Code(err))
        return _take_uint8_t(buf, size)

    def conference_set_title(self, conference_number: Tox_Conference_Number, title: bytes) -> None:
        cdef const uint8_t* title_ptr = title
        cdef size_t title_len = len(title)
        cdef Tox_Err_Conference_Title err = TOX_ERR_CONFERENCE_TITLE_OK
        with nogil:
            self._acquire()
            tox_conference_set_title(self._ptr, conference_number, title_ptr, title_len, &err)
            self._release()
        if err:
            raise ConferenceTitleError(ConferenceTitleError.Code(err))

    def conference_get_type(self, conference_number: Tox_Conference_Number) -> ConferenceType:
        cdef Tox_Err_Conference_Get_Type err = TOX_ERR_CONFERENCE_GET_TYPE_OK
        cdef Tox_Conference_Type res = <Tox_Conference_Type> 0
        with nogil:
            self._acquire()
            res = tox_conference_get_type(self._ptr, conference_number, &err)
            self._release()
        if err:
            raise ConferenceGetTypeError(ConferenceGetTypeError.Code(err))
        return ConferenceType(res)

    def conference_offline_peer_get_name(self, conference_number: Tox_Conference_Number, conference_offline_peer_number: Tox_Conference_Offline_Peer_Number) -> bytes:
        cdef Tox_Err_Conference_Peer_Query err = TOX_ERR_CONFERENCE_PEER_QUERY_OK
        cdef size_t size = 0
        cdef uint8_t* buf = NULL
        with nogil:
            self._acquire()
            size = tox_conference_offline_peer_get_name_size(self._ptr, conference_number, conference_offline_peer_number, &err)
            if not err:
                buf = <uint8_t*> malloc((size if size > 0 else 1) * sizeof(uint8_t))
                if buf is not NULL:
                    tox_conference_offline_peer_get_name(self._ptr, conference_number, conference_offline_peer_number, buf, &err)
            self._release()
        if err:
            free(buf)
            raise ConferencePeerQueryError(ConferencePeerQueryError.Code(err))
        return _take_uint8_t(buf, size)

    def conference_offline_peer_get_public_key(self, conference_number: Tox_Conference_Number, conference_offline_peer_number: Tox_Conference_Offline_Peer_Number) -> bytes:
        cdef Tox_Err_Conference_Peer_Query err = TOX_ERR_CONFERENCE_PEER_QUERY_OK
        cdef size_t size = 0
        cdef uint8_t* buf = NULL
        with nogil:
            self._acquire()
            size = tox_public_key_size()
            buf = <uint8_t*> malloc((size if size > 0 else 1) * sizeof(uint8_t))
            if buf is not NULL:
                tox_conference_offline_peer_get_public_key(self._ptr, conference_number, conference_offline_peer_number, buf, &err)
            self._release()
        if err:
            free(buf)
            raise ConferencePeerQueryError(ConferencePeerQueryError.Code(err))
        return _take_uint8_t(buf, size)

    def conference_offline_peer_get_last_active(self, conference_number: Tox_Conference_Number, conference_offline_peer_number: Tox_Conference_Offline_Peer_Number) -> int:
        cdef Tox_Err_Conference_Peer_Query err = TOX_ERR_CONFERENCE_PEER_QUERY_OK
        cdef uint64_t res = <uint64_t> 0
        with nogil:
            self._acquire()
            res = tox_conference_offline_peer_get_last_active(self._ptr, conference_number, conference_offline_peer_number, &err)
            self._release()
        if err:
            raise ConferencePeerQueryError(ConferencePeerQueryError.Code(err))
        return res

    def conference_peer_number_is_ours(self, conference_number: Tox_Conference_Number, conference_peer_number: Tox_Conference_Peer_Number) -> bool:
        cdef Tox_Err_Conference_Peer_Query err = TOX_ERR_CONFERENCE_PEER_QUERY_OK
        cdef bool res = <bool> 0
        with nogil:
            self._acquire()
            res = tox_conference_peer_number_is_ours(self._ptr, conference_number, conference_peer_number, &err)
            self._release()
        if err:
            raise ConferencePeerQueryError(ConferencePeerQueryError.Code(err))
        return res

    def conference_peer_get_name(self, conference_number: Tox_Conference_Number, conference_peer_number: Tox_Conference_Peer_Number) -> bytes:
        cdef Tox_Err_Conference_Peer_Query err = TOX_ERR_CONFERENCE_PEER_QUERY_OK
        cdef size_t size = 0
        cdef uint8_t* buf = NULL
        with nogil:
            self._acquire()
            size = tox_conference_peer_get_name_size(self._ptr, conference_number, conference_peer_number, &err)
            if not err:
                buf = <uint8_t*> malloc((size if size > 0 else 1) * sizeof(uint8_t))
                if buf is not NULL:
                    tox_conference_peer_get_name(self._ptr, conference_number, conference_peer_number, buf, &err)
            self._release()
        if err:
            free(buf)
            raise ConferencePeerQueryError(ConferencePeerQueryError.Code(err))
        return _take_uint8_t(buf, size)

    def conference_peer_get_public_key(self, conference_number: Tox_Conference_Number, conference_peer_number: Tox_Conference_Peer_Number) -> bytes:
        cdef Tox_Err_Conference_Peer_Query err = TOX_ERR_CONFERENCE_PEER_QUERY_OK
        cdef size_t size = 0
        cdef uint8_t* buf = NULL
        with nogil:
            self._acquire()
            size = tox_public_key_size()
            buf = <uint8_t*> malloc((size if size > 0 else 1) * sizeof(uint8_t))
            if buf is not NULL:
                tox_conference_peer_get_public_key(self._ptr, conference_number, conference_peer_number, buf, &err)
            self._release()
        if err:
            free(buf)
            raise ConferencePeerQueryError(ConferencePeerQueryError.Code(err))
        return _take_uint8_t(buf, size)

    def file_by_id(self, friend_number: Tox_Friend_Number, file_id: bytes) -> Tox_File_Number:
        common.check_exact_len("file_id", file_id, tox_file_id_length())
        cdef const uint8_t* file_id_ptr = file_id
        cdef Tox_Err_File_By_Id err = TOX_ERR_FILE_BY_ID_OK
        cdef Tox_File_Number res = <Tox_File_Number> 0
        with nogil:
            self._acquire()
            res = tox_file_by_id(self._ptr, friend_number, file_id_ptr, &err)
            self._release()
        if err:
            raise FileByIdError(FileByIdError.Code(err))
        return res

    def file_send(self, friend_number: Tox_Friend_Number, kind: int, file_size: int, file_id: Optional[bytes], filename: bytes) -> Tox_File_Number:
        if file_id is not None:
            common.check_exact_len("file_id", file_id, tox_file_id_length())
        cdef uint32_t kind_c = kind
        cdef uint64_t file_size_c = file_size
        cdef const uint8_t* file_id_ptr = <const uint8_t*> file_id if file_id is not None else NULL
        cdef const uint8_t* filename_ptr = filename
        cdef size_t filename_len = len(filename)
        cdef Tox_Err_File_Send err = TOX_ERR_FILE_SEND_OK
        cdef Tox_File_Number res = <Tox_File_Number> 0
        with nogil:
            self._acquire()
            res = tox_file_send(self._ptr, friend_number, kind_c, file_size_c, file_id_ptr, filename_ptr, filename_len, &err)
            self._release()
        if err:
            raise FileSendError(FileSendError.Code(err))
        return res

    def friend_add(self, address: bytes, message: bytes) -> Tox_Friend_Number:
        common.check_exact_len("address", address, tox_address_size())
        cdef const uint8_t* address_ptr = address
        cdef const uint8_t* message_ptr = message
        cdef size_t message_len = len(message)
        cdef Tox_Err_Friend_Add err = TOX_ERR_FRIEND_ADD_OK
        cdef Tox_Friend_Number res = <Tox_Friend_Number> 0
        with nogil:
            self._acquire()
            res = tox_friend_add(self._ptr, address_ptr, message_ptr, message_len, &err)
            self._release()
        if err:
            raise FriendAddError(FriendAddError.Code(err))
        return res

    def friend_add_norequest(self, public_key: bytes) -> Tox_Friend_Number:
        common.check_exact_len("public_key", public_key, tox_public_key_size())
        cdef const uint8_t* public_key_ptr = public_key
        cdef Tox_Err_Friend_Add err = TOX_ERR_FRIEND_ADD_OK
        cdef Tox_Friend_Number res = <Tox_Friend_Number> 0
        with nogil:
            self._acquire()
            res = tox_friend_add_norequest(self._ptr, public_key_ptr, &err)
            self._release()
        if err:
            raise FriendAddError(FriendAddError.Code(err))
        return res

    def friend_delete(self, friend_number: Tox_Friend_Number) -> None:
        cdef Tox_Err_Friend_Delete err = TOX_ERR_FRIEND_DELETE_OK
        with nogil:
            self._acquire()
            tox_friend_delete(self._ptr, friend_number, &err)
            self._release()
        if err:
            raise FriendDeleteError(FriendDeleteError.Code(err))

    def friend_by_public_key(self, public_key: bytes) -> Tox_Friend_Number:
        common.check_exact_len("public_key", public_key, tox_public_key_size())
        cdef const uint8_t* public_key_ptr = public_key
        cdef Tox_Err_Friend_By_Public_Key err = TOX_ERR_FRIEND_BY_PUBLIC_KEY_OK
        cdef Tox_Friend_Number res = <Tox_Friend_Number> 0
        with nogil:
            self._acquire()
            res = tox_friend_by_public_key(self._ptr, public_key_ptr, &err)
            self._release()
        if err:
            raise FriendByPublicKeyError(FriendByPublicKeyError.Code(err))
        return res

    def friend_exists(self, friend_number: Tox_Friend_Number) -> bool:
        cdef bool res = <bool> 0
        with nogil:
            self._acquire()
            res = tox_friend_exists(self._ptr, friend_number)
            self._release()
        return res

    def friend_send_message(self, friend_number: Tox_Friend_Number, type: MessageType, message: bytes) -> Tox_Friend_Message_Id:
        cdef int type_val = MessageType(type)
        cdef const uint8_t* message_ptr = message
        cdef size_t message_len = len(message)
        cdef Tox_Err_Friend_Send_Message err = TOX_ERR_FRIEND_SEND_MESSAGE_OK
        cdef Tox_Friend_Message_Id res = <Tox_Friend_Message_Id> 0
        with nogil:
            self._acquire()
            res = tox_friend_send_message(self._ptr, friend_number, <Tox_Message_Type> type_val, message_ptr, message_len, &err)
            self._release()
        if err:
            raise FriendSendMessageError(FriendSendMessageError.Code(err))
        return res

    def friend_send_lossy_packet(self, friend_number: Tox_Friend_Number, data: bytes) -> None:
        cdef const uint8_t* data_ptr = data
        cdef size_t data_len = len(data)
        cdef Tox_Err_Friend_Custom_Packet err = TOX_ERR_FRIEND_CUSTOM_PACKET_OK
        with nogil:
            self._acquire()
            tox_friend_send_lossy_packet(self._ptr, friend_number, data_ptr, data_len, &err)
            self._release()
        if err:
            raise FriendCustomPacketError(FriendCustomPacketError.Code(err))

    def friend_send_lossless_packet(self, friend_number: Tox_Friend_Number, data: bytes) -> None:
        cdef const uint8_t* data_ptr = data
        cdef size_t data_len = len(data)
        cdef Tox_Err_Friend_Custom_Packet err = TOX_ERR_FRIEND_CUSTOM_PACKET_OK
        with nogil:
            self._acquire()
            tox_friend_send_lossless_packet(self._ptr, friend_number, data_ptr, data_len, &err)
            self._release()
        if err:
            raise FriendCustomPacketError(FriendCustomPacketError.Code(err))

    def friend_get_public_key(self, friend_number: Tox_Friend_Number) -> bytes:
        cdef Tox_Err_Friend_Get_Public_Key err = TOX_ERR_FRIEND_GET_PUBLIC_KEY_OK
        cdef size_t size = 0
        cdef uint8_t* buf = NULL
        with nogil:
            self._acquire()
            size = tox_public_key_size()
            buf = <uint8_t*> malloc((size if size > 0 else 1) * sizeof(uint8_t))
            if buf is not NULL:
                tox_friend_get_public_key(self._ptr, friend_number, buf, &err)
            self._release()
        if err:
            free(buf)
            raise FriendGetPublicKeyError(FriendGetPublicKeyError.Code(err))
        return _take_uint8_t(buf, size)

    def friend_get_last_online(self, friend_number: Tox_Friend_Number) -> int:
        cdef Tox_Err_Friend_Get_Last_Online err = TOX_ERR_FRIEND_GET_LAST_ONLINE_OK
        cdef uint64_t res = <uint64_t> 0
        with nogil:
            self._acquire()
            res = tox_friend_get_last_online(self._ptr, friend_number, &err)
            self._release()
        if err:
            raise FriendGetLastOnlineError(FriendGetLastOnlineError.Code(err))
        return res

    def friend_get_name(self, friend_number: Tox_Friend_Number) -> bytes:
        cdef Tox_Err_Friend_Query err = TOX_ERR_FRIEND_QUERY_OK
        cdef size_t size = 0
        cdef uint8_t* buf = NULL
        with nogil:
            self._acquire()
            size = tox_friend_get_name_size(self._ptr, friend_number, &err)
            if not err:
                buf = <uint8_t*> malloc((size if size > 0 else 1) * sizeof(uint8_t))
                if buf is not NULL:
                    tox_friend_get_name(self._ptr, friend_number, buf, &err)
            self._release()
        if err:
            free(buf)
            raise FriendQueryError(FriendQueryError.Code(err))
        return _take_uint8_t(buf, size)

    def friend_get_status_message(self, friend_number: Tox_Friend_Number) -> bytes:
        cdef Tox_Err_Friend_Query err = TOX_ERR_FRIEND_QUERY_OK
        cdef size_t size = 0
        cdef uint8_t* buf = NULL
        with nogil:
            self._acquire()
            size = tox_friend_get_status_message_size(self._ptr, friend_number, &err)
            if not err:
                buf = <uint8_t*> malloc((size if size > 0 else 1) * sizeof(uint8_t))
                if buf is not NULL:
                    tox_friend_get_status_message(self._ptr, friend_number, buf, &err)
            self._release()
        if err:
            free(buf)
            raise FriendQueryError(FriendQueryError.Code(err))
        return _take_uint8_t(buf, size)

    def friend_get_status(self, friend_number: Tox_Friend_Number) -> UserStatus:
        cdef Tox_Err_Friend_Query err = TOX_ERR_FRIEND_QUERY_OK
        cdef Tox_User_Status res = <Tox_User_Status> 0
        with nogil:
            self._acquire()
            res = tox_friend_get_status(self._ptr, friend_number, &err)
            self._release()
        if err:
            raise FriendQueryError(FriendQueryError.Code(err))
        return UserStatus(res)

    def friend_get_connection_status(self, friend_number: Tox_Friend_Number) -> Connection:
        cdef Tox_Err_Friend_Query err = TOX_ERR_FRIEND_QUERY_OK
        cdef Tox_Connection res = <Tox_Connection> 0
        with nogil:
            self._acquire()
            res = tox_friend_get_connection_status(self._ptr, friend_number, &err)
            self._release()
        if err:
            raise FriendQueryError(FriendQueryError.Code(err))
        return Connection(res)

    def friend_get_typing(self, friend_number: Tox_Friend_Number) -> bool:
        cdef Tox_Err_Friend_Query err = TOX_ERR_FRIEND_QUERY_OK
        cdef bool res = <bool> 0
        with nogil:
            self._acquire()
            res = tox_friend_get_typing(self._ptr, friend_number, &err)
            self._release()
        if err:
            raise FriendQueryError(FriendQueryError.Code(err))
        return res

    def group_new(self, privacy_state: GroupPrivacyState, group_name: bytes, name: bytes) -> Tox_Group_Number:
        cdef int privacy_state_val = GroupPrivacyState(privacy_state)
        cdef const uint8_t* group_name_ptr = group_name
        cdef size_t group_name_len = len(group_name)
        cdef const uint8_t* name_ptr = name
        cdef size_t name_len = len(name)
        cdef Tox_Err_Group_New err = TOX_ERR_GROUP_NEW_OK
        cdef Tox_Group_Number res = <Tox_Group_Number> 0
        with nogil:
            self._acquire()
            res = tox_group_new(self._ptr, <Tox_Group_Privacy_State> privacy_state_val, group_name_ptr, group_name_len, name_ptr, name_len, &err)
            self._release()
        if err:
            raise GroupNewError(GroupNewError.Code(err))
        return res

    def group_join(self, chat_id: bytes, name: bytes, password: bytes) -> Tox_Group_Number:
        common.check_exact_len("chat_id", chat_id, tox_group_chat_id_size())
        cdef const uint8_t* chat_id_ptr = chat_id
        cdef const uint8_t* name_ptr = name
        cdef size_t name_len = len(name)
        cdef const uint8_t* password_ptr = password
        cdef size_t password_len = len(password)
        cdef Tox_Err_Group_Join err = TOX_ERR_GROUP_JOIN_OK
        cdef Tox_Group_Number res = <Tox_Group_Number> 0
        with nogil:
            self._acquire()
            res = tox_group_join(self._ptr, chat_id_ptr, name_ptr, name_len, password_ptr, password_len, &err)
            self._release()
        if err:
            raise GroupJoinError(GroupJoinError.Code(err))
        return res

    def group_is_connected(self, group_number: Tox_Group_Number) -> bool:
        cdef Tox_Err_Group_Is_Connected err = TOX_ERR_GROUP_IS_CONNECTED_OK
        cdef bool res = <bool> 0
        with nogil:
            self._acquire()
            res = tox_group_is_connected(self._ptr, group_number, &err)
            self._release()
        if err:
            raise GroupIsConnectedError(GroupIsConnectedError.Code(err))
        return res

    def group_disconnect(self, group_number: Tox_Group_Number) -> None:
        cdef Tox_Err_Group_Disconnect err = TOX_ERR_GROUP_DISCONNECT_OK
        with nogil:
            self._acquire()
            tox_group_disconnect(self._ptr, group_number, &err)
            self._release()
        if err:
            raise GroupDisconnectError(GroupDisconnectError.Code(err))

    def group_leave(self, group_number: Tox_Group_Number, part_message: bytes) -> None:
        cdef const uint8_t* part_message_ptr = part_message
        cdef size_t part_message_len = len(part_message)
        cdef Tox_Err_Group_Leave err = TOX_ERR_GROUP_LEAVE_OK
        with nogil:
            self._acquire()
            tox_group_leave(self._ptr, group_number, part_message_ptr, part_message_len, &err)
            self._release()
        if err:
            raise GroupLeaveError(GroupLeaveError.Code(err))

    def group_by_id(self, chat_id: bytes) -> Tox_Group_Number:
        common.check_exact_len("chat_id", chat_id, tox_group_chat_id_size())
        cdef const uint8_t* chat_id_ptr = chat_id
        cdef Tox_Err_Group_By_Id err = TOX_ERR_GROUP_BY_ID_OK
        cdef Tox_Group_Number res = <Tox_Group_Number> 0
        with nogil:
            self._acquire()
            res = tox_group_by_id(self._ptr, chat_id_ptr, &err)
            self._release()
        if err:
            raise GroupByIdError(GroupByIdError.Code(err))
        return res

    def group_send_message(self, group_number: Tox_Group_Number, message_type: MessageType, message: bytes) -> Tox_Group_Message_Id:
        cdef int message_type_val = MessageType(message_type)
        cdef const uint8_t* message_ptr = message
        cdef size_t message_len = len(message)
        cdef Tox_Err_Group_Send_Message err = TOX_ERR_GROUP_SEND_MESSAGE_OK
        cdef Tox_Group_Message_Id res = <Tox_Group_Message_Id> 0
        with nogil:
            self._acquire()
            res = tox_group_send_message(self._ptr, group_number, <Tox_Message_Type> message_type_val, message_ptr, message_len, &err)
            self._release()
        if err:
            raise GroupSendMessageError(GroupSendMessageError.Code(err))
        return res

    def group_send_private_message(self, group_number: Tox_Group_Number, peer_id: Tox_Group_Peer_Number, message_type: MessageType, message: bytes) -> Tox_Group_Message_Id:
        cdef int message_type_val = MessageType(message_type)
        cdef const uint8_t* message_ptr = message
        cdef size_t message_len = len(message)
        cdef Tox_Err_Group_Send_Private_Message err = TOX_ERR_GROUP_SEND_PRIVATE_MESSAGE_OK
        cdef Tox_Group_Message_Id res = <Tox_Group_Message_Id> 0
        with nogil:
            self._acquire()
            res = tox_group_send_private_message(self._ptr, group_number, peer_id, <Tox_Message_Type> message_type_val, message_ptr, message_len, &err)
            self._release()
        if err:
            raise GroupSendPrivateMessageError(GroupSendPrivateMessageError.Code(err))
        return res

    def group_send_custom_packet(self, group_number: Tox_Group_Number, lossless: bool, data: bytes) -> None:
        cdef bool lossless_c = lossless
        cdef const uint8_t* data_ptr = data
        cdef size_t data_len = len(data)
        cdef Tox_Err_Group_Send_Custom_Packet err = TOX_ERR_GROUP_SEND_CUSTOM_PACKET_OK
        with nogil:
            self._acquire()
            tox_group_send_custom_packet(self._ptr, group_number, lossless_c, data_ptr, data_len, &err)
            self._release()
        if err:
            raise GroupSendCustomPacketError(GroupSendCustomPacketError.Code(err))

    def group_send_custom_private_packet(self, group_number: Tox_Group_Number, peer_id: Tox_Group_Peer_Number, lossless: bool, data: bytes) -> None:
        cdef bool lossless_c = lossless
        cdef const uint8_t* data_ptr = data
        cdef size_t data_len = len(data)
        cdef Tox_Err_Group_Send_Custom_Private_Packet err = TOX_ERR_GROUP_SEND_CUSTOM_PRIVATE_PACKET_OK
        with nogil:
            self._acquire()
            tox_group_send_custom_private_packet(self._ptr, group_number, peer_id, lossless_c, data_ptr, data_len, &err)
            self._release()
        if err:
            raise GroupSendCustomPrivatePacketError(GroupSendCustomPrivatePacketError.Code(err))

    def group_invite_friend(self, group_number: Tox_Group_Number, friend_number: Tox_Friend_Number) -> None:
        cdef Tox_Err_Group_Invite_Friend err = TOX_ERR_GROUP_INVITE_FRIEND_OK
        with nogil:
            self._acquire()
            tox_group_invite_friend(self._ptr, group_number, friend_number, &err)
            self._release()
        if err:
            raise GroupInviteFriendError(GroupInviteFriendError.Code(err))

    def group_invite_accept(self, friend_number: Tox_Friend_Number, invite_data: bytes, name: bytes, password: bytes) -> Tox_Group_Number:
        cdef const uint8_t* invite_data_ptr = invite_data
        cdef size_t invite_data_len = len(invite_data)
        cdef const uint8_t* name_ptr = name
        cdef size_t name_len = len(name)
        cdef const uint8_t* password_ptr = password
        cdef size_t password_len = len(password)
        cdef Tox_Err_Group_Invite_Accept err = TOX_ERR_GROUP_INVITE_ACCEPT_OK
        cdef Tox_Group_Number res = <Tox_Group_Number> 0
        with nogil:
            self._acquire()
            res = tox_group_invite_accept(self._ptr, friend_number, invite_data_ptr, invite_data_len, name_ptr, name_len, password_ptr, password_len, &err)
            self._release()
        if err:
            raise GroupInviteAcceptError(GroupInviteAcceptError.Code(err))
        return res

    def group_set_ignore(self, group_number: Tox_Group_Number, peer_id: Tox_Group_Peer_Number, ignore: bool) -> None:
        cdef bool ignore_c = ignore
        cdef Tox_Err_Group_Set_Ignore err = TOX_ERR_GROUP_SET_IGNORE_OK
        with nogil:
            self._acquire()
            tox_group_set_ignore(self._ptr, group_number, peer_id, ignore_c, &err)
            self._release()
        if err:
            raise GroupSetIgnoreError(GroupSetIgnoreError.Code(err))

    def group_set_role(self, group_number: Tox_Group_Number, peer_id: Tox_Group_Peer_Number, role: GroupRole) -> None:
        cdef int role_val = GroupRole(role)
        cdef Tox_Err_Group_Set_Role err = TOX_ERR_GROUP_SET_ROLE_OK
        with nogil:
            self._acquire()
            tox_group_set_role(self._ptr, group_number, peer_id, <Tox_Group_Role> role_val, &err)
            self._release()
        if err:
            raise GroupSetRoleError(GroupSetRoleError.Code(err))

    def group_kick_peer(self, group_number: Tox_Group_Number, peer_id: Tox_Group_Peer_Number) -> None:
        cdef Tox_Err_Group_Kick_Peer err = TOX_ERR_GROUP_KICK_PEER_OK
        with nogil:
            self._acquire()
            tox_group_kick_peer(self._ptr, group_number, peer_id, &err)
            self._release()
        if err:
            raise GroupKickPeerError(GroupKickPeerError.Code(err))

    def group_get_chat_id(self, group_number: Tox_Group_Number) -> bytes:
        cdef Tox_Err_Group_State_Query err = TOX_ERR_GROUP_STATE_QUERY_OK
        cdef size_t size = 0
        cdef uint8_t* buf = NULL
        with nogil:
            self._acquire()
            size = tox_group_chat_id_size()
            buf = <uint8_t*> malloc((size if size > 0 else 1) * sizeof(uint8_t))
            if buf is not NULL:
                tox_group_get_chat_id(self._ptr, group_number, buf, &err)
            self._release()
        if err:
            free(buf)
            raise GroupStateQueryError(GroupStateQueryError.Code(err))
        return _take_uint8_t(buf, size)

    def group_get_self_name(self, group_number: Tox_Group_Number) -> bytes:
        cdef Tox_Err_Group_Self_Query err = TOX_ERR_GROUP_SELF_QUERY_OK
        cdef size_t size = 0
        cdef uint8_t* buf = NULL
        with nogil:
            self._acquire()
            size = tox_group_self_get_name_size(self._ptr, group_number, &err)
            if not err:
                buf = <uint8_t*> malloc((size if size > 0 else 1) * sizeof(uint8_t))
                if buf is not NULL:
                    tox_group_self_get_name(self._ptr, group_number, buf, &err)
            self._release()
        if err:
            free(buf)
            raise GroupSelfQueryError(GroupSelfQueryError.Code(err))
        return _take_uint8_t(buf, size)

    def group_set_self_name(self, group_number: Tox_Group_Number, name: bytes) -> None:
        cdef const uint8_t* name_ptr = name
        cdef size_t name_len = len(name)
        cdef Tox_Err_Group_Self_Name_Set err = TOX_ERR_GROUP_SELF_NAME_SET_OK
        with nogil:
            self._acquire()
            tox_group_self_set_name(self._ptr, group_number, name_ptr, name_len, &err)
            self._release()
        if err:
            raise GroupSelfNameSetError(GroupSelfNameSetError.Code(err))

    def group_get_self_status(self, group_number: Tox_Group_Number) -> UserStatus:
        cdef Tox_Err_Group_Self_Query err = TOX_ERR_GROUP_SELF_QUERY_OK
        cdef Tox_User_Status res = <Tox_User_Status> 0
        with nogil:
            self._acquire()
            res = tox_group_self_get_status(self._ptr, group_number, &err)
            self._release()
        if err:
            raise GroupSelfQueryError(GroupSelfQueryError.Code(err))
        return UserStatus(res)

    def group_set_self_status(self, group_number: Tox_Group_Number, status: UserStatus) -> None:
        cdef int status_val = UserStatus(status)
        cdef Tox_Err_Group_Self_Status_Set err = TOX_ERR_GROUP_SELF_STATUS_SET_OK
        with nogil:
            self._acquire()
            tox_group_self_set_status(self._ptr, group_number, <Tox_User_Status> status_val, &err)
            self._release()
        if err:
            raise GroupSelfStatusSetError(GroupSelfStatusSetError.Code(err))

    def group_get_self_role(self, group_number: Tox_Group_Number) -> GroupRole:
        cdef Tox_Err_Group_Self_Query err = TOX_ERR_GROUP_SELF_QUERY_OK
        cdef Tox_Group_Role res = <Tox_Group_Role> 0
        with nogil:
            self._acquire()
            res = tox_group_self_get_role(self._ptr, group_number, &err)
            self._release()
        if err:
            raise GroupSelfQueryError(GroupSelfQueryError.Code(err))
        return GroupRole(res)

    def group_get_self_peer_id(self, group_number: Tox_Group_Number) -> Tox_Group_Peer_Number:
        cdef Tox_Err_Group_Self_Query err = TOX_ERR_GROUP_SELF_QUERY_OK
        cdef Tox_Group_Peer_Number res = <Tox_Group_Peer_Number> 0
        with nogil:
            self._acquire()
            res = tox_group_self_get_peer_id(self._ptr, group_number, &err)
            self._release()
        if err:
            raise GroupSelfQueryError(GroupSelfQueryError.Code(err))
        return res

    def group_get_self_public_key(self, group_number: Tox_Group_Number) -> bytes:
        cdef Tox_Err_Group_Self_Query err = TOX_ERR_GROUP_SELF_QUERY_OK
        cdef size_t size = 0
        cdef uint8_t* buf = NULL
        with nogil:
            self._acquire()
            size = tox_public_key_size()
            buf = <uint8_t*> malloc((size if size > 0 else 1) * sizeof(uint8_t))
            if buf is not NULL:
                tox_group_self_get_public_key(self._ptr, group_number, buf, &err)
            self._release()
        if err:
            free(buf)
            raise GroupSelfQueryError(GroupSelfQueryError.Code(err))
        return _take_uint8_t(buf, size)

    def group_get_topic(self, group_number: Tox_Group_Number) -> bytes:
        cdef Tox_Err_Group_State_Query err = TOX_ERR_GROUP_STATE_QUERY_OK
        cdef size_t size = 0
        cdef uint8_t* buf = NULL
        with nogil:
            self._acquire()
            size = tox_group_get_topic_size(self._ptr, group_number, &err)
            if not err:
                buf = <uint8_t*> malloc((size if size > 0 else 1) * sizeof(uint8_t))
                if buf is not NULL:
                    tox_group_get_topic(self._ptr, group_number, buf, &err)
            self._release()
        if err:
            free(buf)
            raise GroupStateQueryError(GroupStateQueryError.Code(err))
        return _take_uint8_t(buf, size)

    def group_set_topic(self, group_number: Tox_Group_Number, topic: bytes) -> None:
        cdef const uint8_t* topic_ptr = topic
        cdef size_t topic_len = len(topic)
        cdef Tox_Err_Group_Topic_Set err = TOX_ERR_GROUP_TOPIC_SET_OK
        with nogil:
            self._acquire()
            tox_group_set_topic(self._ptr, group_number, topic_ptr, topic_len, &err)
            self._release()
        if err:
            raise GroupTopicSetError(GroupTopicSetError.Code(err))

    def group_get_name(self, group_number: Tox_Group_Number) -> bytes:
        cdef Tox_Err_Group_State_Query err = TOX_ERR_GROUP_STATE_QUERY_OK
        cdef size_t size = 0
        cdef uint8_t* buf = NULL
        with nogil:
            self._acquire()
            size = tox_group_get_name_size(self._ptr, group_number, &err)
            if not err:
                buf = <uint8_t*> malloc((size if size > 0 else 1) * sizeof(uint8_t))
                if buf is not NULL:
                    tox_group_get_name(self._ptr, group_number, buf, &err)
            self._release()
        if err:
            free(buf)
            raise GroupStateQueryError(GroupStateQueryError.Code(err))
        return _take_uint8_t(buf, size)

    def group_get_privacy_state(self, group_number: Tox_Group_Number) -> GroupPrivacyState:
        cdef Tox_Err_Group_State_Query err = TOX_ERR_GROUP_STATE_QUERY_OK
        cdef Tox_Group_Privacy_State res = <Tox_Group_Privacy_State> 0
        with nogil:
            self._acquire()
            res = tox_group_get_privacy_state(self._ptr, group_number, &err)
            self._release()
        if err:
            raise GroupStateQueryError(GroupStateQueryError.Code(err))
        return GroupPrivacyState(res)

    def group_set_privacy_state(self, group_number: Tox_Group_Number, privacy_state: GroupPrivacyState) -> None:
        cdef int privacy_state_val = GroupPrivacyState(privacy_state)
        cdef Tox_Err_Group_Set_Privacy_State err = TOX_ERR_GROUP_SET_PRIVACY_STATE_OK
        with nogil:
            self._acquire()
            tox_group_set_privacy_state(self._ptr, group_number, <Tox_Group_Privacy_State> privacy_state_val, &err)
            self._release()
        if err:
            raise GroupSetPrivacyStateError(GroupSetPrivacyStateError.Code(err))

    def group_get_voice_state(self, group_number: Tox_Group_Number) -> GroupVoiceState:
        cdef Tox_Err_Group_State_Query err = TOX_ERR_GROUP_STATE_QUERY_OK
        cdef Tox_Group_Voice_State res = <Tox_Group_Voice_State> 0
        with nogil:
            self._acquire()
            res = tox_group_get_voice_state(self._ptr, group_number, &err)
            self._release()
        if err:
            raise GroupStateQueryError(GroupStateQueryError.Code(err))
        return GroupVoiceState(res)

    def group_set_voice_state(self, group_number: Tox_Group_Number, voice_state: GroupVoiceState) -> None:
        cdef int voice_state_val = GroupVoiceState(voice_state)
        cdef Tox_Err_Group_Set_Voice_State err = TOX_ERR_GROUP_SET_VOICE_STATE_OK
        with nogil:
            self._acquire()
            tox_group_set_voice_state(self._ptr, group_number, <Tox_Group_Voice_State> voice_state_val, &err)
            self._release()
        if err:
            raise GroupSetVoiceStateError(GroupSetVoiceStateError.Code(err))

    def group_get_topic_lock(self, group_number: Tox_Group_Number) -> GroupTopicLock:
        cdef Tox_Err_Group_State_Query err = TOX_ERR_GROUP_STATE_QUERY_OK
        cdef Tox_Group_Topic_Lock res = <Tox_Group_Topic_Lock> 0
        with nogil:
            self._acquire()
            res = tox_group_get_topic_lock(self._ptr, group_number, &err)
            self._release()
        if err:
            raise GroupStateQueryError(GroupStateQueryError.Code(err))
        return GroupTopicLock(res)

    def group_set_topic_lock(self, group_number: Tox_Group_Number, topic_lock: GroupTopicLock) -> None:
        cdef int topic_lock_val = GroupTopicLock(topic_lock)
        cdef Tox_Err_Group_Set_Topic_Lock err = TOX_ERR_GROUP_SET_TOPIC_LOCK_OK
        with nogil:
            self._acquire()
            tox_group_set_topic_lock(self._ptr, group_number, <Tox_Group_Topic_Lock> topic_lock_val, &err)
            self._release()
        if err:
            raise GroupSetTopicLockError(GroupSetTopicLockError.Code(err))

    def group_get_peer_limit(self, group_number: Tox_Group_Number) -> int:
        cdef Tox_Err_Group_State_Query err = TOX_ERR_GROUP_STATE_QUERY_OK
        cdef uint16_t res = <uint16_t> 0
        with nogil:
            self._acquire()
            res = tox_group_get_peer_limit(self._ptr, group_number, &err)
            self._release()
        if err:
            raise GroupStateQueryError(GroupStateQueryError.Code(err))
        return res

    def group_set_peer_limit(self, group_number: Tox_Group_Number, peer_limit: int) -> None:
        cdef uint16_t peer_limit_c = peer_limit
        cdef Tox_Err_Group_Set_Peer_Limit err = TOX_ERR_GROUP_SET_PEER_LIMIT_OK
        with nogil:
            self._acquire()
            tox_group_set_peer_limit(self._ptr, group_number, peer_limit_c, &err)
            self._release()
        if err:
            raise GroupSetPeerLimitError(GroupSetPeerLimitError.Code(err))

    def group_get_password(self, group_number: Tox_Group_Number) -> bytes:
        cdef Tox_Err_Group_State_Query err = TOX_ERR_GROUP_STATE_QUERY_OK
        cdef size_t size = 0
        cdef uint8_t* buf = NULL
        with nogil:
            self._acquire()
            size = tox_group_get_password_size(self._ptr, group_number, &err)
            if not err:
                buf = <uint8_t*> malloc((size if size > 0 else 1) * sizeof(uint8_t))
                if buf is not NULL:
                    tox_group_get_password(self._ptr, group_number, buf, &err)
            self._release()
        if err:
            free(buf)
            raise GroupStateQueryError(GroupStateQueryError.Code(err))
        return _take_uint8_t(buf, size)

    def group_set_password(self, group_number: Tox_Group_Number, password: bytes) -> None:
        cdef const uint8_t* password_ptr = password
        cdef size_t password_len = len(password)
        cdef Tox_Err_Group_Set_Password err = TOX_ERR_GROUP_SET_PASSWORD_OK
        with nogil:
            self._acquire()
            tox_group_set_password(self._ptr, group_number, password_ptr, password_len, &err)
            self._release()
        if err:
            raise GroupSetPasswordError(GroupSetPasswordError.Code(err))

    def group_peer_get_public_key(self, group_number: Tox_Group_Number, group_peer_number: Tox_Group_Peer_Number) -> bytes:
        cdef Tox_Err_Group_Peer_Query err = TOX_ERR_GROUP_PEER_QUERY_OK
        cdef size_t size = 0
        cdef uint8_t* buf = NULL
        with nogil:
            self._acquire()
            size = tox_public_key_size()
            buf = <uint8_t*> malloc((size if size > 0 else 1) * sizeof(uint8_t))
            if buf is not NULL:
                tox_group_peer_get_public_key(self._ptr, group_number, group_peer_number, buf, &err)
            self._release()
        if err:
            free(buf)
            raise GroupPeerQueryError(GroupPeerQueryError.Code(err))
        return _take_uint8_t(buf, size)

    def group_peer_get_name(self, group_number: Tox_Group_Number, group_peer_number: Tox_Group_Peer_Number) -> bytes:
        cdef Tox_Err_Group_Peer_Query err = TOX_ERR_GROUP_PEER_QUERY_OK
        cdef size_t size = 0
        cdef uint8_t* buf = NULL
        with nogil:
            self._acquire()
            size = tox_group_peer_get_name_size(self._ptr, group_number, group_peer_number, &err)
            if not err:
                buf = <uint8_t*> malloc((size if size > 0 else 1) * sizeof(uint8_t))
                if buf is not NULL:
                    tox_group_peer_get_name(self._ptr, group_number, group_peer_number, buf, &err)
            self._release()
        if err:
            free(buf)
            raise GroupPeerQueryError(GroupPeerQueryError.Code(err))
        return _take_uint8_t(buf, size)

    def group_peer_get_status(self, group_number: Tox_Group_Number, group_peer_number: Tox_Group_Peer_Number) -> UserStatus:
        cdef Tox_Err_Group_Peer_Query err = TOX_ERR_GROUP_PEER_QUERY_OK
        cdef Tox_User_Status res = <Tox_User_Status> 0
        with nogil:
            self._acquire()
            res = tox_group_peer_get_status(self._ptr, group_number, group_peer_number, &err)
            self._release()
        if err:
            raise GroupPeerQueryError(GroupPeerQueryError.Code(err))
        return UserStatus(res)

    def group_peer_get_role(self, group_number: Tox_Group_Number, group_peer_number: Tox_Group_Peer_Number) -> GroupRole:
        cdef Tox_Err_Group_Peer_Query err = TOX_ERR_GROUP_PEER_QUERY_OK
        cdef Tox_Group_Role res = <Tox_Group_Role> 0
        with nogil:
            self._acquire()
            res = tox_group_peer_get_role(self._ptr, group_number, group_peer_number, &err)
            self._release()
        if err:
            raise GroupPeerQueryError(GroupPeerQueryError.Code(err))
        return GroupRole(res)

    def group_peer_get_connection_status(self, group_number: Tox_Group_Number, group_peer_number: Tox_Group_Peer_Number) -> Connection:
        cdef Tox_Err_Group_Peer_Query err = TOX_ERR_GROUP_PEER_QUERY_OK
        cdef Tox_Connection res = <Tox_Connection> 0
        with nogil:
            self._acquire()
            res = tox_group_peer_get_connection_status(self._ptr, group_number, group_peer_number, &err)
            self._release()
        if err:
            raise GroupPeerQueryError(GroupPeerQueryError.Code(err))
        return Connection(res)
VERSION: str = "%d.%d.%d" % (tox_version_major(), tox_version_minor(), tox_version_patch())
PUBLIC_KEY_SIZE: int = tox_public_key_size()
SECRET_KEY_SIZE: int = tox_secret_key_size()
DHT_ID_SIZE: int = tox_dht_id_size()
NOSPAM_SIZE: int = tox_nospam_size()
ADDRESS_SIZE: int = tox_address_size()
MAX_NAME_LENGTH: int = tox_max_name_length()
MAX_STATUS_MESSAGE_LENGTH: int = tox_max_status_message_length()
MAX_FRIEND_REQUEST_LENGTH: int = tox_max_friend_request_length()
MAX_MESSAGE_LENGTH: int = tox_max_message_length()
MAX_CUSTOM_PACKET_SIZE: int = tox_max_custom_packet_size()
HASH_LENGTH: int = tox_hash_length()
MAX_FILENAME_LENGTH: int = tox_max_filename_length()
MAX_HOSTNAME_LENGTH: int = tox_max_hostname_length()


def version_is_compatible(major: int, minor: int, patch: int) -> bool:
    return tox_version_is_compatible(major, minor, patch)


def hash(data: bytes) -> bytes:
    cdef const uint8_t* data_ptr = data
    cdef size_t data_len = len(data)
    cdef size_t size = tox_hash_length()
    cdef uint8_t* buf = <uint8_t*> malloc(max(size, 1) * sizeof(uint8_t))
    if buf is NULL:
        raise MemoryError()
    try:
        with nogil:
            tox_hash(buf, data_ptr, data_len)
        return buf[:size]
    finally:
        free(buf)
