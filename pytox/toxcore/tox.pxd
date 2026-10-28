# cython: language_level=3, linetrace=True
from libcpp cimport bool
from libc.stdint cimport uint8_t, uint16_t, uint32_t, uint64_t, int16_t, int32_t, int64_t
from libc.stdlib cimport malloc, free
from typing import Optional
from cpython.pythread cimport PyThread_type_lock


cdef extern from "tox/tox.h":
    ctypedef enum Tox_Conference_Type:
        TOX_CONFERENCE_TYPE_TEXT
        TOX_CONFERENCE_TYPE_AV
    ctypedef enum Tox_Connection:
        TOX_CONNECTION_NONE
        TOX_CONNECTION_TCP
        TOX_CONNECTION_UDP
    ctypedef enum Tox_Err_Bootstrap:
        TOX_ERR_BOOTSTRAP_OK
        TOX_ERR_BOOTSTRAP_NULL
        TOX_ERR_BOOTSTRAP_BAD_HOST
        TOX_ERR_BOOTSTRAP_BAD_PORT
    ctypedef enum Tox_Err_Conference_By_Id:
        TOX_ERR_CONFERENCE_BY_ID_OK
        TOX_ERR_CONFERENCE_BY_ID_NULL
        TOX_ERR_CONFERENCE_BY_ID_NOT_FOUND
    ctypedef enum Tox_Err_Conference_Delete:
        TOX_ERR_CONFERENCE_DELETE_OK
        TOX_ERR_CONFERENCE_DELETE_CONFERENCE_NOT_FOUND
    ctypedef enum Tox_Err_Conference_Get_Type:
        TOX_ERR_CONFERENCE_GET_TYPE_OK
        TOX_ERR_CONFERENCE_GET_TYPE_CONFERENCE_NOT_FOUND
    ctypedef enum Tox_Err_Conference_Invite:
        TOX_ERR_CONFERENCE_INVITE_OK
        TOX_ERR_CONFERENCE_INVITE_CONFERENCE_NOT_FOUND
        TOX_ERR_CONFERENCE_INVITE_FAIL_SEND
        TOX_ERR_CONFERENCE_INVITE_NO_CONNECTION
    ctypedef enum Tox_Err_Conference_Join:
        TOX_ERR_CONFERENCE_JOIN_OK
        TOX_ERR_CONFERENCE_JOIN_INVALID_LENGTH
        TOX_ERR_CONFERENCE_JOIN_WRONG_TYPE
        TOX_ERR_CONFERENCE_JOIN_FRIEND_NOT_FOUND
        TOX_ERR_CONFERENCE_JOIN_DUPLICATE
        TOX_ERR_CONFERENCE_JOIN_INIT_FAIL
        TOX_ERR_CONFERENCE_JOIN_FAIL_SEND
        TOX_ERR_CONFERENCE_JOIN_NULL
    ctypedef enum Tox_Err_Conference_New:
        TOX_ERR_CONFERENCE_NEW_OK
        TOX_ERR_CONFERENCE_NEW_INIT
    ctypedef enum Tox_Err_Conference_Peer_Query:
        TOX_ERR_CONFERENCE_PEER_QUERY_OK
        TOX_ERR_CONFERENCE_PEER_QUERY_CONFERENCE_NOT_FOUND
        TOX_ERR_CONFERENCE_PEER_QUERY_PEER_NOT_FOUND
        TOX_ERR_CONFERENCE_PEER_QUERY_NO_CONNECTION
    ctypedef enum Tox_Err_Conference_Send_Message:
        TOX_ERR_CONFERENCE_SEND_MESSAGE_OK
        TOX_ERR_CONFERENCE_SEND_MESSAGE_CONFERENCE_NOT_FOUND
        TOX_ERR_CONFERENCE_SEND_MESSAGE_TOO_LONG
        TOX_ERR_CONFERENCE_SEND_MESSAGE_NO_CONNECTION
        TOX_ERR_CONFERENCE_SEND_MESSAGE_FAIL_SEND
    ctypedef enum Tox_Err_Conference_Set_Max_Offline:
        TOX_ERR_CONFERENCE_SET_MAX_OFFLINE_OK
        TOX_ERR_CONFERENCE_SET_MAX_OFFLINE_CONFERENCE_NOT_FOUND
    ctypedef enum Tox_Err_Conference_Title:
        TOX_ERR_CONFERENCE_TITLE_OK
        TOX_ERR_CONFERENCE_TITLE_CONFERENCE_NOT_FOUND
        TOX_ERR_CONFERENCE_TITLE_INVALID_LENGTH
        TOX_ERR_CONFERENCE_TITLE_FAIL_SEND
    ctypedef enum Tox_Err_File_By_Id:
        TOX_ERR_FILE_BY_ID_OK
        TOX_ERR_FILE_BY_ID_NULL
        TOX_ERR_FILE_BY_ID_FRIEND_NOT_FOUND
        TOX_ERR_FILE_BY_ID_NOT_FOUND
    ctypedef enum Tox_Err_File_Control:
        TOX_ERR_FILE_CONTROL_OK
        TOX_ERR_FILE_CONTROL_FRIEND_NOT_FOUND
        TOX_ERR_FILE_CONTROL_FRIEND_NOT_CONNECTED
        TOX_ERR_FILE_CONTROL_NOT_FOUND
        TOX_ERR_FILE_CONTROL_NOT_PAUSED
        TOX_ERR_FILE_CONTROL_DENIED
        TOX_ERR_FILE_CONTROL_ALREADY_PAUSED
        TOX_ERR_FILE_CONTROL_SENDQ
    ctypedef enum Tox_Err_File_Get:
        TOX_ERR_FILE_GET_OK
        TOX_ERR_FILE_GET_NULL
        TOX_ERR_FILE_GET_FRIEND_NOT_FOUND
        TOX_ERR_FILE_GET_NOT_FOUND
    ctypedef enum Tox_Err_File_Seek:
        TOX_ERR_FILE_SEEK_OK
        TOX_ERR_FILE_SEEK_FRIEND_NOT_FOUND
        TOX_ERR_FILE_SEEK_FRIEND_NOT_CONNECTED
        TOX_ERR_FILE_SEEK_NOT_FOUND
        TOX_ERR_FILE_SEEK_DENIED
        TOX_ERR_FILE_SEEK_INVALID_POSITION
        TOX_ERR_FILE_SEEK_SENDQ
    ctypedef enum Tox_Err_File_Send:
        TOX_ERR_FILE_SEND_OK
        TOX_ERR_FILE_SEND_NULL
        TOX_ERR_FILE_SEND_FRIEND_NOT_FOUND
        TOX_ERR_FILE_SEND_FRIEND_NOT_CONNECTED
        TOX_ERR_FILE_SEND_NAME_TOO_LONG
        TOX_ERR_FILE_SEND_TOO_MANY
    ctypedef enum Tox_Err_File_Send_Chunk:
        TOX_ERR_FILE_SEND_CHUNK_OK
        TOX_ERR_FILE_SEND_CHUNK_NULL
        TOX_ERR_FILE_SEND_CHUNK_FRIEND_NOT_FOUND
        TOX_ERR_FILE_SEND_CHUNK_FRIEND_NOT_CONNECTED
        TOX_ERR_FILE_SEND_CHUNK_NOT_FOUND
        TOX_ERR_FILE_SEND_CHUNK_NOT_TRANSFERRING
        TOX_ERR_FILE_SEND_CHUNK_INVALID_LENGTH
        TOX_ERR_FILE_SEND_CHUNK_SENDQ
        TOX_ERR_FILE_SEND_CHUNK_WRONG_POSITION
    ctypedef enum Tox_Err_Friend_Add:
        TOX_ERR_FRIEND_ADD_OK
        TOX_ERR_FRIEND_ADD_NULL
        TOX_ERR_FRIEND_ADD_TOO_LONG
        TOX_ERR_FRIEND_ADD_NO_MESSAGE
        TOX_ERR_FRIEND_ADD_OWN_KEY
        TOX_ERR_FRIEND_ADD_ALREADY_SENT
        TOX_ERR_FRIEND_ADD_BAD_CHECKSUM
        TOX_ERR_FRIEND_ADD_SET_NEW_NOSPAM
        TOX_ERR_FRIEND_ADD_MALLOC
    ctypedef enum Tox_Err_Friend_By_Public_Key:
        TOX_ERR_FRIEND_BY_PUBLIC_KEY_OK
        TOX_ERR_FRIEND_BY_PUBLIC_KEY_NULL
        TOX_ERR_FRIEND_BY_PUBLIC_KEY_NOT_FOUND
    ctypedef enum Tox_Err_Friend_Custom_Packet:
        TOX_ERR_FRIEND_CUSTOM_PACKET_OK
        TOX_ERR_FRIEND_CUSTOM_PACKET_NULL
        TOX_ERR_FRIEND_CUSTOM_PACKET_FRIEND_NOT_FOUND
        TOX_ERR_FRIEND_CUSTOM_PACKET_FRIEND_NOT_CONNECTED
        TOX_ERR_FRIEND_CUSTOM_PACKET_INVALID
        TOX_ERR_FRIEND_CUSTOM_PACKET_EMPTY
        TOX_ERR_FRIEND_CUSTOM_PACKET_TOO_LONG
        TOX_ERR_FRIEND_CUSTOM_PACKET_SENDQ
    ctypedef enum Tox_Err_Friend_Delete:
        TOX_ERR_FRIEND_DELETE_OK
        TOX_ERR_FRIEND_DELETE_FRIEND_NOT_FOUND
    ctypedef enum Tox_Err_Friend_Get_Last_Online:
        TOX_ERR_FRIEND_GET_LAST_ONLINE_OK
        TOX_ERR_FRIEND_GET_LAST_ONLINE_FRIEND_NOT_FOUND
    ctypedef enum Tox_Err_Friend_Get_Public_Key:
        TOX_ERR_FRIEND_GET_PUBLIC_KEY_OK
        TOX_ERR_FRIEND_GET_PUBLIC_KEY_FRIEND_NOT_FOUND
    ctypedef enum Tox_Err_Friend_Query:
        TOX_ERR_FRIEND_QUERY_OK
        TOX_ERR_FRIEND_QUERY_NULL
        TOX_ERR_FRIEND_QUERY_FRIEND_NOT_FOUND
    ctypedef enum Tox_Err_Friend_Send_Message:
        TOX_ERR_FRIEND_SEND_MESSAGE_OK
        TOX_ERR_FRIEND_SEND_MESSAGE_NULL
        TOX_ERR_FRIEND_SEND_MESSAGE_FRIEND_NOT_FOUND
        TOX_ERR_FRIEND_SEND_MESSAGE_FRIEND_NOT_CONNECTED
        TOX_ERR_FRIEND_SEND_MESSAGE_SENDQ
        TOX_ERR_FRIEND_SEND_MESSAGE_TOO_LONG
        TOX_ERR_FRIEND_SEND_MESSAGE_EMPTY
    ctypedef enum Tox_Err_Get_Port:
        TOX_ERR_GET_PORT_OK
        TOX_ERR_GET_PORT_NOT_BOUND
    ctypedef enum Tox_Err_Group_By_Id:
        TOX_ERR_GROUP_BY_ID_OK
        TOX_ERR_GROUP_BY_ID_NULL
        TOX_ERR_GROUP_BY_ID_NOT_FOUND
    ctypedef enum Tox_Err_Group_Disconnect:
        TOX_ERR_GROUP_DISCONNECT_OK
        TOX_ERR_GROUP_DISCONNECT_GROUP_NOT_FOUND
        TOX_ERR_GROUP_DISCONNECT_ALREADY_DISCONNECTED
    ctypedef enum Tox_Err_Group_Invite_Accept:
        TOX_ERR_GROUP_INVITE_ACCEPT_OK
        TOX_ERR_GROUP_INVITE_ACCEPT_BAD_INVITE
        TOX_ERR_GROUP_INVITE_ACCEPT_INIT_FAILED
        TOX_ERR_GROUP_INVITE_ACCEPT_TOO_LONG
        TOX_ERR_GROUP_INVITE_ACCEPT_EMPTY
        TOX_ERR_GROUP_INVITE_ACCEPT_PASSWORD
        TOX_ERR_GROUP_INVITE_ACCEPT_FRIEND_NOT_FOUND
        TOX_ERR_GROUP_INVITE_ACCEPT_FAIL_SEND
        TOX_ERR_GROUP_INVITE_ACCEPT_NULL
    ctypedef enum Tox_Err_Group_Invite_Friend:
        TOX_ERR_GROUP_INVITE_FRIEND_OK
        TOX_ERR_GROUP_INVITE_FRIEND_GROUP_NOT_FOUND
        TOX_ERR_GROUP_INVITE_FRIEND_FRIEND_NOT_FOUND
        TOX_ERR_GROUP_INVITE_FRIEND_INVITE_FAIL
        TOX_ERR_GROUP_INVITE_FRIEND_FAIL_SEND
        TOX_ERR_GROUP_INVITE_FRIEND_DISCONNECTED
    ctypedef enum Tox_Err_Group_Is_Connected:
        TOX_ERR_GROUP_IS_CONNECTED_OK
        TOX_ERR_GROUP_IS_CONNECTED_GROUP_NOT_FOUND
    ctypedef enum Tox_Err_Group_Join:
        TOX_ERR_GROUP_JOIN_OK
        TOX_ERR_GROUP_JOIN_INIT
        TOX_ERR_GROUP_JOIN_BAD_CHAT_ID
        TOX_ERR_GROUP_JOIN_EMPTY
        TOX_ERR_GROUP_JOIN_TOO_LONG
        TOX_ERR_GROUP_JOIN_PASSWORD
        TOX_ERR_GROUP_JOIN_CORE
    ctypedef enum Tox_Err_Group_Kick_Peer:
        TOX_ERR_GROUP_KICK_PEER_OK
        TOX_ERR_GROUP_KICK_PEER_GROUP_NOT_FOUND
        TOX_ERR_GROUP_KICK_PEER_PEER_NOT_FOUND
        TOX_ERR_GROUP_KICK_PEER_PERMISSIONS
        TOX_ERR_GROUP_KICK_PEER_FAIL_ACTION
        TOX_ERR_GROUP_KICK_PEER_FAIL_SEND
        TOX_ERR_GROUP_KICK_PEER_SELF
    ctypedef enum Tox_Err_Group_Leave:
        TOX_ERR_GROUP_LEAVE_OK
        TOX_ERR_GROUP_LEAVE_GROUP_NOT_FOUND
        TOX_ERR_GROUP_LEAVE_TOO_LONG
        TOX_ERR_GROUP_LEAVE_FAIL_SEND
    ctypedef enum Tox_Err_Group_New:
        TOX_ERR_GROUP_NEW_OK
        TOX_ERR_GROUP_NEW_TOO_LONG
        TOX_ERR_GROUP_NEW_EMPTY
        TOX_ERR_GROUP_NEW_INIT
        TOX_ERR_GROUP_NEW_STATE
        TOX_ERR_GROUP_NEW_ANNOUNCE
    ctypedef enum Tox_Err_Group_Peer_Query:
        TOX_ERR_GROUP_PEER_QUERY_OK
        TOX_ERR_GROUP_PEER_QUERY_GROUP_NOT_FOUND
        TOX_ERR_GROUP_PEER_QUERY_PEER_NOT_FOUND
    ctypedef enum Tox_Err_Group_Self_Name_Set:
        TOX_ERR_GROUP_SELF_NAME_SET_OK
        TOX_ERR_GROUP_SELF_NAME_SET_GROUP_NOT_FOUND
        TOX_ERR_GROUP_SELF_NAME_SET_TOO_LONG
        TOX_ERR_GROUP_SELF_NAME_SET_INVALID
        TOX_ERR_GROUP_SELF_NAME_SET_FAIL_SEND
    ctypedef enum Tox_Err_Group_Self_Query:
        TOX_ERR_GROUP_SELF_QUERY_OK
        TOX_ERR_GROUP_SELF_QUERY_GROUP_NOT_FOUND
    ctypedef enum Tox_Err_Group_Self_Status_Set:
        TOX_ERR_GROUP_SELF_STATUS_SET_OK
        TOX_ERR_GROUP_SELF_STATUS_SET_GROUP_NOT_FOUND
        TOX_ERR_GROUP_SELF_STATUS_SET_FAIL_SEND
    ctypedef enum Tox_Err_Group_Send_Custom_Packet:
        TOX_ERR_GROUP_SEND_CUSTOM_PACKET_OK
        TOX_ERR_GROUP_SEND_CUSTOM_PACKET_GROUP_NOT_FOUND
        TOX_ERR_GROUP_SEND_CUSTOM_PACKET_TOO_LONG
        TOX_ERR_GROUP_SEND_CUSTOM_PACKET_EMPTY
        TOX_ERR_GROUP_SEND_CUSTOM_PACKET_DISCONNECTED
        TOX_ERR_GROUP_SEND_CUSTOM_PACKET_FAIL_SEND
    ctypedef enum Tox_Err_Group_Send_Custom_Private_Packet:
        TOX_ERR_GROUP_SEND_CUSTOM_PRIVATE_PACKET_OK
        TOX_ERR_GROUP_SEND_CUSTOM_PRIVATE_PACKET_GROUP_NOT_FOUND
        TOX_ERR_GROUP_SEND_CUSTOM_PRIVATE_PACKET_TOO_LONG
        TOX_ERR_GROUP_SEND_CUSTOM_PRIVATE_PACKET_EMPTY
        TOX_ERR_GROUP_SEND_CUSTOM_PRIVATE_PACKET_PEER_NOT_FOUND
        TOX_ERR_GROUP_SEND_CUSTOM_PRIVATE_PACKET_FAIL_SEND
        TOX_ERR_GROUP_SEND_CUSTOM_PRIVATE_PACKET_DISCONNECTED
    ctypedef enum Tox_Err_Group_Send_Message:
        TOX_ERR_GROUP_SEND_MESSAGE_OK
        TOX_ERR_GROUP_SEND_MESSAGE_GROUP_NOT_FOUND
        TOX_ERR_GROUP_SEND_MESSAGE_TOO_LONG
        TOX_ERR_GROUP_SEND_MESSAGE_EMPTY
        TOX_ERR_GROUP_SEND_MESSAGE_BAD_TYPE
        TOX_ERR_GROUP_SEND_MESSAGE_PERMISSIONS
        TOX_ERR_GROUP_SEND_MESSAGE_FAIL_SEND
        TOX_ERR_GROUP_SEND_MESSAGE_DISCONNECTED
    ctypedef enum Tox_Err_Group_Send_Private_Message:
        TOX_ERR_GROUP_SEND_PRIVATE_MESSAGE_OK
        TOX_ERR_GROUP_SEND_PRIVATE_MESSAGE_GROUP_NOT_FOUND
        TOX_ERR_GROUP_SEND_PRIVATE_MESSAGE_PEER_NOT_FOUND
        TOX_ERR_GROUP_SEND_PRIVATE_MESSAGE_TOO_LONG
        TOX_ERR_GROUP_SEND_PRIVATE_MESSAGE_EMPTY
        TOX_ERR_GROUP_SEND_PRIVATE_MESSAGE_BAD_TYPE
        TOX_ERR_GROUP_SEND_PRIVATE_MESSAGE_PERMISSIONS
        TOX_ERR_GROUP_SEND_PRIVATE_MESSAGE_FAIL_SEND
        TOX_ERR_GROUP_SEND_PRIVATE_MESSAGE_DISCONNECTED
    ctypedef enum Tox_Err_Group_Set_Ignore:
        TOX_ERR_GROUP_SET_IGNORE_OK
        TOX_ERR_GROUP_SET_IGNORE_GROUP_NOT_FOUND
        TOX_ERR_GROUP_SET_IGNORE_PEER_NOT_FOUND
        TOX_ERR_GROUP_SET_IGNORE_SELF
    ctypedef enum Tox_Err_Group_Set_Password:
        TOX_ERR_GROUP_SET_PASSWORD_OK
        TOX_ERR_GROUP_SET_PASSWORD_GROUP_NOT_FOUND
        TOX_ERR_GROUP_SET_PASSWORD_PERMISSIONS
        TOX_ERR_GROUP_SET_PASSWORD_TOO_LONG
        TOX_ERR_GROUP_SET_PASSWORD_FAIL_SEND
        TOX_ERR_GROUP_SET_PASSWORD_MALLOC
        TOX_ERR_GROUP_SET_PASSWORD_DISCONNECTED
    ctypedef enum Tox_Err_Group_Set_Peer_Limit:
        TOX_ERR_GROUP_SET_PEER_LIMIT_OK
        TOX_ERR_GROUP_SET_PEER_LIMIT_GROUP_NOT_FOUND
        TOX_ERR_GROUP_SET_PEER_LIMIT_PERMISSIONS
        TOX_ERR_GROUP_SET_PEER_LIMIT_FAIL_SET
        TOX_ERR_GROUP_SET_PEER_LIMIT_FAIL_SEND
        TOX_ERR_GROUP_SET_PEER_LIMIT_DISCONNECTED
    ctypedef enum Tox_Err_Group_Set_Privacy_State:
        TOX_ERR_GROUP_SET_PRIVACY_STATE_OK
        TOX_ERR_GROUP_SET_PRIVACY_STATE_GROUP_NOT_FOUND
        TOX_ERR_GROUP_SET_PRIVACY_STATE_PERMISSIONS
        TOX_ERR_GROUP_SET_PRIVACY_STATE_FAIL_SET
        TOX_ERR_GROUP_SET_PRIVACY_STATE_FAIL_SEND
        TOX_ERR_GROUP_SET_PRIVACY_STATE_DISCONNECTED
    ctypedef enum Tox_Err_Group_Set_Role:
        TOX_ERR_GROUP_SET_ROLE_OK
        TOX_ERR_GROUP_SET_ROLE_GROUP_NOT_FOUND
        TOX_ERR_GROUP_SET_ROLE_PEER_NOT_FOUND
        TOX_ERR_GROUP_SET_ROLE_PERMISSIONS
        TOX_ERR_GROUP_SET_ROLE_ASSIGNMENT
        TOX_ERR_GROUP_SET_ROLE_FAIL_ACTION
        TOX_ERR_GROUP_SET_ROLE_SELF
    ctypedef enum Tox_Err_Group_Set_Topic_Lock:
        TOX_ERR_GROUP_SET_TOPIC_LOCK_OK
        TOX_ERR_GROUP_SET_TOPIC_LOCK_GROUP_NOT_FOUND
        TOX_ERR_GROUP_SET_TOPIC_LOCK_INVALID
        TOX_ERR_GROUP_SET_TOPIC_LOCK_PERMISSIONS
        TOX_ERR_GROUP_SET_TOPIC_LOCK_FAIL_SET
        TOX_ERR_GROUP_SET_TOPIC_LOCK_FAIL_SEND
        TOX_ERR_GROUP_SET_TOPIC_LOCK_DISCONNECTED
    ctypedef enum Tox_Err_Group_Set_Voice_State:
        TOX_ERR_GROUP_SET_VOICE_STATE_OK
        TOX_ERR_GROUP_SET_VOICE_STATE_GROUP_NOT_FOUND
        TOX_ERR_GROUP_SET_VOICE_STATE_PERMISSIONS
        TOX_ERR_GROUP_SET_VOICE_STATE_FAIL_SET
        TOX_ERR_GROUP_SET_VOICE_STATE_FAIL_SEND
        TOX_ERR_GROUP_SET_VOICE_STATE_DISCONNECTED
    ctypedef enum Tox_Err_Group_State_Query:
        TOX_ERR_GROUP_STATE_QUERY_OK
        TOX_ERR_GROUP_STATE_QUERY_GROUP_NOT_FOUND
    ctypedef enum Tox_Err_Group_Topic_Set:
        TOX_ERR_GROUP_TOPIC_SET_OK
        TOX_ERR_GROUP_TOPIC_SET_GROUP_NOT_FOUND
        TOX_ERR_GROUP_TOPIC_SET_TOO_LONG
        TOX_ERR_GROUP_TOPIC_SET_PERMISSIONS
        TOX_ERR_GROUP_TOPIC_SET_FAIL_CREATE
        TOX_ERR_GROUP_TOPIC_SET_FAIL_SEND
        TOX_ERR_GROUP_TOPIC_SET_DISCONNECTED
    ctypedef enum Tox_Err_New:
        TOX_ERR_NEW_OK
        TOX_ERR_NEW_NULL
        TOX_ERR_NEW_MALLOC
        TOX_ERR_NEW_PORT_ALLOC
        TOX_ERR_NEW_PROXY_BAD_TYPE
        TOX_ERR_NEW_PROXY_BAD_HOST
        TOX_ERR_NEW_PROXY_BAD_PORT
        TOX_ERR_NEW_PROXY_NOT_FOUND
        TOX_ERR_NEW_LOAD_ENCRYPTED
        TOX_ERR_NEW_LOAD_BAD_FORMAT
    ctypedef enum Tox_Err_Options_New:
        TOX_ERR_OPTIONS_NEW_OK
        TOX_ERR_OPTIONS_NEW_MALLOC
    ctypedef enum Tox_Err_Set_Info:
        TOX_ERR_SET_INFO_OK
        TOX_ERR_SET_INFO_NULL
        TOX_ERR_SET_INFO_TOO_LONG
    ctypedef enum Tox_Err_Set_Typing:
        TOX_ERR_SET_TYPING_OK
        TOX_ERR_SET_TYPING_FRIEND_NOT_FOUND
    ctypedef enum Tox_File_Control:
        TOX_FILE_CONTROL_RESUME
        TOX_FILE_CONTROL_PAUSE
        TOX_FILE_CONTROL_CANCEL
    ctypedef enum Tox_File_Kind:
        TOX_FILE_KIND_DATA
        TOX_FILE_KIND_AVATAR
        TOX_FILE_KIND_STICKER
        TOX_FILE_KIND_SHA1
        TOX_FILE_KIND_SHA256
    ctypedef enum Tox_Group_Exit_Type:
        TOX_GROUP_EXIT_TYPE_QUIT
        TOX_GROUP_EXIT_TYPE_TIMEOUT
        TOX_GROUP_EXIT_TYPE_DISCONNECTED
        TOX_GROUP_EXIT_TYPE_SELF_DISCONNECTED
        TOX_GROUP_EXIT_TYPE_KICK
        TOX_GROUP_EXIT_TYPE_SYNC_ERROR
    ctypedef enum Tox_Group_Join_Fail:
        TOX_GROUP_JOIN_FAIL_PEER_LIMIT
        TOX_GROUP_JOIN_FAIL_INVALID_PASSWORD
        TOX_GROUP_JOIN_FAIL_UNKNOWN
    ctypedef enum Tox_Group_Mod_Event:
        TOX_GROUP_MOD_EVENT_KICK
        TOX_GROUP_MOD_EVENT_OBSERVER
        TOX_GROUP_MOD_EVENT_USER
        TOX_GROUP_MOD_EVENT_MODERATOR
    ctypedef enum Tox_Group_Privacy_State:
        TOX_GROUP_PRIVACY_STATE_PUBLIC
        TOX_GROUP_PRIVACY_STATE_PRIVATE
    ctypedef enum Tox_Group_Role:
        TOX_GROUP_ROLE_FOUNDER
        TOX_GROUP_ROLE_MODERATOR
        TOX_GROUP_ROLE_USER
        TOX_GROUP_ROLE_OBSERVER
    ctypedef enum Tox_Group_Topic_Lock:
        TOX_GROUP_TOPIC_LOCK_ENABLED
        TOX_GROUP_TOPIC_LOCK_DISABLED
    ctypedef enum Tox_Group_Voice_State:
        TOX_GROUP_VOICE_STATE_ALL
        TOX_GROUP_VOICE_STATE_MODERATOR
        TOX_GROUP_VOICE_STATE_FOUNDER
    ctypedef enum Tox_Log_Level:
        TOX_LOG_LEVEL_TRACE
        TOX_LOG_LEVEL_DEBUG
        TOX_LOG_LEVEL_INFO
        TOX_LOG_LEVEL_WARNING
        TOX_LOG_LEVEL_ERROR
    ctypedef enum Tox_Message_Type:
        TOX_MESSAGE_TYPE_NORMAL
        TOX_MESSAGE_TYPE_ACTION
    ctypedef enum Tox_Proxy_Type:
        TOX_PROXY_TYPE_NONE
        TOX_PROXY_TYPE_HTTP
        TOX_PROXY_TYPE_SOCKS5
    ctypedef enum Tox_Savedata_Type:
        TOX_SAVEDATA_TYPE_NONE
        TOX_SAVEDATA_TYPE_TOX_SAVE
        TOX_SAVEDATA_TYPE_SECRET_KEY
    ctypedef enum Tox_User_Status:
        TOX_USER_STATUS_NONE
        TOX_USER_STATUS_AWAY
        TOX_USER_STATUS_BUSY
    ctypedef struct Tox_Options
    ctypedef struct CTox "Tox"
    ctypedef uint32_t Tox_Conference_Number
    ctypedef uint32_t Tox_Conference_Offline_Peer_Number
    ctypedef uint32_t Tox_Conference_Peer_Number
    ctypedef uint32_t Tox_File_Number
    ctypedef uint32_t Tox_Friend_Message_Id
    ctypedef uint32_t Tox_Friend_Number
    ctypedef uint32_t Tox_Group_Message_Id
    ctypedef uint32_t Tox_Group_Number
    ctypedef uint32_t Tox_Group_Peer_Number
    ctypedef void tox_conference_connected_cb(CTox* tox, Tox_Conference_Number conference_number, void* user_data) noexcept
    ctypedef void tox_conference_invite_cb(CTox* tox, Tox_Friend_Number friend_number, Tox_Conference_Type type, const uint8_t* cookie, size_t cookie_length, void* user_data) noexcept
    ctypedef void tox_conference_message_cb(CTox* tox, Tox_Conference_Number conference_number, Tox_Conference_Peer_Number peer_number, Tox_Message_Type type, const uint8_t* message, size_t message_length, void* user_data) noexcept
    ctypedef void tox_conference_peer_list_changed_cb(CTox* tox, Tox_Conference_Number conference_number, void* user_data) noexcept
    ctypedef void tox_conference_peer_name_cb(CTox* tox, Tox_Conference_Number conference_number, Tox_Conference_Peer_Number peer_number, const uint8_t* name, size_t name_length, void* user_data) noexcept
    ctypedef void tox_conference_title_cb(CTox* tox, Tox_Conference_Number conference_number, Tox_Conference_Peer_Number peer_number, const uint8_t* title, size_t title_length, void* user_data) noexcept
    ctypedef void tox_file_chunk_request_cb(CTox* tox, Tox_Friend_Number friend_number, Tox_File_Number file_number, uint64_t position, size_t length, void* user_data) noexcept
    ctypedef void tox_file_recv_cb(CTox* tox, Tox_Friend_Number friend_number, Tox_File_Number file_number, uint32_t kind, uint64_t file_size, const uint8_t* filename, size_t filename_length, void* user_data) noexcept
    ctypedef void tox_file_recv_chunk_cb(CTox* tox, Tox_Friend_Number friend_number, Tox_File_Number file_number, uint64_t position, const uint8_t* data, size_t data_length, void* user_data) noexcept
    ctypedef void tox_file_recv_control_cb(CTox* tox, Tox_Friend_Number friend_number, Tox_File_Number file_number, Tox_File_Control control, void* user_data) noexcept
    ctypedef void tox_friend_connection_status_cb(CTox* tox, Tox_Friend_Number friend_number, Tox_Connection connection_status, void* user_data) noexcept
    ctypedef void tox_friend_lossless_packet_cb(CTox* tox, Tox_Friend_Number friend_number, const uint8_t* data, size_t data_length, void* user_data) noexcept
    ctypedef void tox_friend_lossy_packet_cb(CTox* tox, Tox_Friend_Number friend_number, const uint8_t* data, size_t data_length, void* user_data) noexcept
    ctypedef void tox_friend_message_cb(CTox* tox, Tox_Friend_Number friend_number, Tox_Message_Type type, const uint8_t* message, size_t message_length, void* user_data) noexcept
    ctypedef void tox_friend_name_cb(CTox* tox, Tox_Friend_Number friend_number, const uint8_t* name, size_t name_length, void* user_data) noexcept
    ctypedef void tox_friend_read_receipt_cb(CTox* tox, Tox_Friend_Number friend_number, Tox_Friend_Message_Id message_id, void* user_data) noexcept
    ctypedef void tox_friend_request_cb(CTox* tox, const uint8_t* public_key, const uint8_t* message, size_t message_length, void* user_data) noexcept
    ctypedef void tox_friend_status_cb(CTox* tox, Tox_Friend_Number friend_number, Tox_User_Status status, void* user_data) noexcept
    ctypedef void tox_friend_status_message_cb(CTox* tox, Tox_Friend_Number friend_number, const uint8_t* message, size_t message_length, void* user_data) noexcept
    ctypedef void tox_friend_typing_cb(CTox* tox, Tox_Friend_Number friend_number, bool typing, void* user_data) noexcept
    ctypedef void tox_group_custom_packet_cb(CTox* tox, Tox_Group_Number group_number, Tox_Group_Peer_Number peer_id, const uint8_t* data, size_t data_length, void* user_data) noexcept
    ctypedef void tox_group_custom_private_packet_cb(CTox* tox, Tox_Group_Number group_number, Tox_Group_Peer_Number peer_id, const uint8_t* data, size_t data_length, void* user_data) noexcept
    ctypedef void tox_group_invite_cb(CTox* tox, Tox_Friend_Number friend_number, const uint8_t* invite_data, size_t invite_data_length, const uint8_t* group_name, size_t group_name_length, void* user_data) noexcept
    ctypedef void tox_group_join_fail_cb(CTox* tox, Tox_Group_Number group_number, Tox_Group_Join_Fail fail_type, void* user_data) noexcept
    ctypedef void tox_group_message_cb(CTox* tox, Tox_Group_Number group_number, Tox_Group_Peer_Number peer_id, Tox_Message_Type message_type, const uint8_t* message, size_t message_length, Tox_Group_Message_Id message_id, void* user_data) noexcept
    ctypedef void tox_group_moderation_cb(CTox* tox, Tox_Group_Number group_number, Tox_Group_Peer_Number source_peer_id, Tox_Group_Peer_Number target_peer_id, Tox_Group_Mod_Event mod_type, void* user_data) noexcept
    ctypedef void tox_group_password_cb(CTox* tox, Tox_Group_Number group_number, const uint8_t* password, size_t password_length, void* user_data) noexcept
    ctypedef void tox_group_peer_exit_cb(CTox* tox, Tox_Group_Number group_number, Tox_Group_Peer_Number peer_id, Tox_Group_Exit_Type exit_type, const uint8_t* name, size_t name_length, const uint8_t* part_message, size_t part_message_length, void* user_data) noexcept
    ctypedef void tox_group_peer_join_cb(CTox* tox, Tox_Group_Number group_number, Tox_Group_Peer_Number peer_id, void* user_data) noexcept
    ctypedef void tox_group_peer_limit_cb(CTox* tox, Tox_Group_Number group_number, uint32_t peer_limit, void* user_data) noexcept
    ctypedef void tox_group_peer_name_cb(CTox* tox, Tox_Group_Number group_number, Tox_Group_Peer_Number peer_id, const uint8_t* name, size_t name_length, void* user_data) noexcept
    ctypedef void tox_group_peer_status_cb(CTox* tox, Tox_Group_Number group_number, Tox_Group_Peer_Number peer_id, Tox_User_Status status, void* user_data) noexcept
    ctypedef void tox_group_privacy_state_cb(CTox* tox, Tox_Group_Number group_number, Tox_Group_Privacy_State privacy_state, void* user_data) noexcept
    ctypedef void tox_group_private_message_cb(CTox* tox, Tox_Group_Number group_number, Tox_Group_Peer_Number peer_id, Tox_Message_Type message_type, const uint8_t* message, size_t message_length, Tox_Group_Message_Id message_id, void* user_data) noexcept
    ctypedef void tox_group_self_join_cb(CTox* tox, Tox_Group_Number group_number, void* user_data) noexcept
    ctypedef void tox_group_topic_cb(CTox* tox, Tox_Group_Number group_number, Tox_Group_Peer_Number peer_id, const uint8_t* topic, size_t topic_length, void* user_data) noexcept
    ctypedef void tox_group_topic_lock_cb(CTox* tox, Tox_Group_Number group_number, Tox_Group_Topic_Lock topic_lock, void* user_data) noexcept
    ctypedef void tox_group_voice_state_cb(CTox* tox, Tox_Group_Number group_number, Tox_Group_Voice_State voice_state, void* user_data) noexcept
    ctypedef void tox_log_cb(CTox* tox, Tox_Log_Level level, const char* file, uint32_t line, const char* func, const char* message, void* user_data) noexcept
    ctypedef void tox_self_connection_status_cb(CTox* tox, Tox_Connection connection_status, void* user_data) noexcept
    cdef uint32_t tox_conference_id_size() noexcept nogil
    cdef Tox_Conference_Number tox_conference_new(CTox* tox, Tox_Err_Conference_New* error) noexcept nogil
    cdef bool tox_conference_delete(CTox* tox, Tox_Conference_Number conference_number, Tox_Err_Conference_Delete* error) noexcept nogil
    cdef uint32_t tox_conference_peer_count(const CTox* tox, Tox_Conference_Number conference_number, Tox_Err_Conference_Peer_Query* error) noexcept nogil
    cdef uint32_t tox_conference_offline_peer_count(const CTox* tox, Tox_Conference_Number conference_number, Tox_Err_Conference_Peer_Query* error) noexcept nogil
    cdef bool tox_conference_set_max_offline(CTox* tox, Tox_Conference_Number conference_number, uint32_t max_offline, Tox_Err_Conference_Set_Max_Offline* error) noexcept nogil
    cdef Tox_Conference_Number tox_conference_join(CTox* tox, Tox_Friend_Number friend_number, const uint8_t* cookie, size_t cookie_len, Tox_Err_Conference_Join* error) noexcept nogil
    cdef bool tox_conference_send_message(CTox* tox, Tox_Conference_Number conference_number, Tox_Message_Type type, const uint8_t* message, size_t message_len, Tox_Err_Conference_Send_Message* error) noexcept nogil
    cdef size_t tox_conference_get_title_size(const CTox* tox, Tox_Conference_Number conference_number, Tox_Err_Conference_Title* error) noexcept nogil
    cdef bool tox_conference_get_title(const CTox* tox, Tox_Conference_Number conference_number, uint8_t* title, Tox_Err_Conference_Title* error) noexcept nogil
    cdef bool tox_conference_set_title(CTox* tox, Tox_Conference_Number conference_number, const uint8_t* title, size_t title_len, Tox_Err_Conference_Title* error) noexcept nogil
    cdef Tox_Conference_Type tox_conference_get_type(const CTox* tox, Tox_Conference_Number conference_number, Tox_Err_Conference_Get_Type* error) noexcept nogil
    cdef bool tox_conference_get_id(const CTox* tox, Tox_Conference_Number conference_number, uint8_t* id) noexcept nogil
    cdef Tox_Conference_Number tox_conference_by_id(const CTox* tox, const uint8_t* id, Tox_Err_Conference_By_Id* error) noexcept nogil
    cdef size_t tox_conference_offline_peer_get_name_size(const CTox* tox, Tox_Conference_Number conference_number, Tox_Conference_Offline_Peer_Number conference_offline_peer_number, Tox_Err_Conference_Peer_Query* error) noexcept nogil
    cdef bool tox_conference_offline_peer_get_name(const CTox* tox, Tox_Conference_Number conference_number, Tox_Conference_Offline_Peer_Number conference_offline_peer_number, uint8_t* name, Tox_Err_Conference_Peer_Query* error) noexcept nogil
    cdef bool tox_conference_offline_peer_get_public_key(const CTox* tox, Tox_Conference_Number conference_number, Tox_Conference_Offline_Peer_Number conference_offline_peer_number, uint8_t* public_key, Tox_Err_Conference_Peer_Query* error) noexcept nogil
    cdef uint64_t tox_conference_offline_peer_get_last_active(const CTox* tox, Tox_Conference_Number conference_number, Tox_Conference_Offline_Peer_Number conference_offline_peer_number, Tox_Err_Conference_Peer_Query* error) noexcept nogil
    cdef size_t tox_conference_peer_get_name_size(const CTox* tox, Tox_Conference_Number conference_number, Tox_Conference_Peer_Number conference_peer_number, Tox_Err_Conference_Peer_Query* error) noexcept nogil
    cdef bool tox_conference_peer_get_name(const CTox* tox, Tox_Conference_Number conference_number, Tox_Conference_Peer_Number conference_peer_number, uint8_t* name, Tox_Err_Conference_Peer_Query* error) noexcept nogil
    cdef bool tox_conference_peer_get_public_key(const CTox* tox, Tox_Conference_Number conference_number, Tox_Conference_Peer_Number conference_peer_number, uint8_t* public_key, Tox_Err_Conference_Peer_Query* error) noexcept nogil
    cdef bool tox_conference_peer_number_is_ours(const CTox* tox, Tox_Conference_Number conference_number, Tox_Conference_Peer_Number conference_peer_number, Tox_Err_Conference_Peer_Query* error) noexcept nogil
    cdef uint32_t tox_file_id_length() noexcept nogil
    cdef Tox_File_Number tox_file_by_id(const CTox* tox, Tox_Friend_Number friend_number, const uint8_t* file_id, Tox_Err_File_By_Id* error) noexcept nogil
    cdef Tox_File_Number tox_file_send(CTox* tox, Tox_Friend_Number friend_number, uint32_t kind, uint64_t file_size, const uint8_t* file_id, const uint8_t* filename, size_t filename_len, Tox_Err_File_Send* error) noexcept nogil
    cdef Tox_Friend_Number tox_friend_add(CTox* tox, const uint8_t* address, const uint8_t* message, size_t message_len, Tox_Err_Friend_Add* error) noexcept nogil
    cdef Tox_Friend_Number tox_friend_add_norequest(CTox* tox, const uint8_t* public_key, Tox_Err_Friend_Add* error) noexcept nogil
    cdef bool tox_friend_delete(CTox* tox, Tox_Friend_Number friend_number, Tox_Err_Friend_Delete* error) noexcept nogil
    cdef Tox_Friend_Number tox_friend_by_public_key(const CTox* tox, const uint8_t* public_key, Tox_Err_Friend_By_Public_Key* error) noexcept nogil
    cdef bool tox_friend_exists(const CTox* tox, Tox_Friend_Number friend_number) noexcept nogil
    cdef bool tox_friend_get_public_key(const CTox* tox, Tox_Friend_Number friend_number, uint8_t* public_key, Tox_Err_Friend_Get_Public_Key* error) noexcept nogil
    cdef uint64_t tox_friend_get_last_online(const CTox* tox, Tox_Friend_Number friend_number, Tox_Err_Friend_Get_Last_Online* error) noexcept nogil
    cdef size_t tox_friend_get_name_size(const CTox* tox, Tox_Friend_Number friend_number, Tox_Err_Friend_Query* error) noexcept nogil
    cdef bool tox_friend_get_name(const CTox* tox, Tox_Friend_Number friend_number, uint8_t* name, Tox_Err_Friend_Query* error) noexcept nogil
    cdef size_t tox_friend_get_status_message_size(const CTox* tox, Tox_Friend_Number friend_number, Tox_Err_Friend_Query* error) noexcept nogil
    cdef bool tox_friend_get_status_message(const CTox* tox, Tox_Friend_Number friend_number, uint8_t* status_message, Tox_Err_Friend_Query* error) noexcept nogil
    cdef Tox_User_Status tox_friend_get_status(const CTox* tox, Tox_Friend_Number friend_number, Tox_Err_Friend_Query* error) noexcept nogil
    cdef Tox_Connection tox_friend_get_connection_status(const CTox* tox, Tox_Friend_Number friend_number, Tox_Err_Friend_Query* error) noexcept nogil
    cdef bool tox_friend_get_typing(const CTox* tox, Tox_Friend_Number friend_number, Tox_Err_Friend_Query* error) noexcept nogil
    cdef Tox_Friend_Message_Id tox_friend_send_message(CTox* tox, Tox_Friend_Number friend_number, Tox_Message_Type type, const uint8_t* message, size_t message_len, Tox_Err_Friend_Send_Message* error) noexcept nogil
    cdef bool tox_friend_send_lossy_packet(CTox* tox, Tox_Friend_Number friend_number, const uint8_t* data, size_t data_len, Tox_Err_Friend_Custom_Packet* error) noexcept nogil
    cdef bool tox_friend_send_lossless_packet(CTox* tox, Tox_Friend_Number friend_number, const uint8_t* data, size_t data_len, Tox_Err_Friend_Custom_Packet* error) noexcept nogil
    cdef uint32_t tox_group_max_topic_length() noexcept nogil
    cdef uint32_t tox_group_max_part_length() noexcept nogil
    cdef uint32_t tox_group_max_message_length() noexcept nogil
    cdef uint32_t tox_group_max_custom_lossy_packet_length() noexcept nogil
    cdef uint32_t tox_group_max_custom_lossless_packet_length() noexcept nogil
    cdef uint32_t tox_group_max_group_name_length() noexcept nogil
    cdef uint32_t tox_group_max_password_size() noexcept nogil
    cdef uint32_t tox_group_chat_id_size() noexcept nogil
    cdef Tox_Group_Number tox_group_new(CTox* tox, Tox_Group_Privacy_State privacy_state, const uint8_t* group_name, size_t group_name_len, const uint8_t* name, size_t name_len, Tox_Err_Group_New* error) noexcept nogil
    cdef Tox_Group_Number tox_group_join(CTox* tox, const uint8_t* chat_id, const uint8_t* name, size_t name_len, const uint8_t* password, size_t password_len, Tox_Err_Group_Join* error) noexcept nogil
    cdef bool tox_group_is_connected(const CTox* tox, Tox_Group_Number group_number, Tox_Err_Group_Is_Connected* error) noexcept nogil
    cdef bool tox_group_disconnect(const CTox* tox, Tox_Group_Number group_number, Tox_Err_Group_Disconnect* error) noexcept nogil
    cdef bool tox_group_leave(CTox* tox, Tox_Group_Number group_number, const uint8_t* part_message, size_t part_message_len, Tox_Err_Group_Leave* error) noexcept nogil
    cdef bool tox_group_self_set_name(CTox* tox, Tox_Group_Number group_number, const uint8_t* name, size_t name_len, Tox_Err_Group_Self_Name_Set* error) noexcept nogil
    cdef size_t tox_group_self_get_name_size(const CTox* tox, Tox_Group_Number group_number, Tox_Err_Group_Self_Query* error) noexcept nogil
    cdef bool tox_group_self_get_name(const CTox* tox, Tox_Group_Number group_number, uint8_t* name, Tox_Err_Group_Self_Query* error) noexcept nogil
    cdef bool tox_group_self_set_status(CTox* tox, Tox_Group_Number group_number, Tox_User_Status status, Tox_Err_Group_Self_Status_Set* error) noexcept nogil
    cdef Tox_User_Status tox_group_self_get_status(const CTox* tox, Tox_Group_Number group_number, Tox_Err_Group_Self_Query* error) noexcept nogil
    cdef Tox_Group_Role tox_group_self_get_role(const CTox* tox, Tox_Group_Number group_number, Tox_Err_Group_Self_Query* error) noexcept nogil
    cdef Tox_Group_Peer_Number tox_group_self_get_peer_id(const CTox* tox, Tox_Group_Number group_number, Tox_Err_Group_Self_Query* error) noexcept nogil
    cdef bool tox_group_self_get_public_key(const CTox* tox, Tox_Group_Number group_number, uint8_t* public_key, Tox_Err_Group_Self_Query* error) noexcept nogil
    cdef bool tox_group_set_topic(CTox* tox, Tox_Group_Number group_number, const uint8_t* topic, size_t topic_len, Tox_Err_Group_Topic_Set* error) noexcept nogil
    cdef size_t tox_group_get_topic_size(const CTox* tox, Tox_Group_Number group_number, Tox_Err_Group_State_Query* error) noexcept nogil
    cdef bool tox_group_get_topic(const CTox* tox, Tox_Group_Number group_number, uint8_t* topic, Tox_Err_Group_State_Query* error) noexcept nogil
    cdef size_t tox_group_get_name_size(const CTox* tox, Tox_Group_Number group_number, Tox_Err_Group_State_Query* error) noexcept nogil
    cdef bool tox_group_get_name(const CTox* tox, Tox_Group_Number group_number, uint8_t* name, Tox_Err_Group_State_Query* error) noexcept nogil
    cdef bool tox_group_get_chat_id(const CTox* tox, Tox_Group_Number group_number, uint8_t* chat_id, Tox_Err_Group_State_Query* error) noexcept nogil
    cdef Tox_Group_Number tox_group_by_id(const CTox* tox, const uint8_t* chat_id, Tox_Err_Group_By_Id* error) noexcept nogil
    cdef Tox_Group_Privacy_State tox_group_get_privacy_state(const CTox* tox, Tox_Group_Number group_number, Tox_Err_Group_State_Query* error) noexcept nogil
    cdef Tox_Group_Voice_State tox_group_get_voice_state(const CTox* tox, Tox_Group_Number group_number, Tox_Err_Group_State_Query* error) noexcept nogil
    cdef Tox_Group_Topic_Lock tox_group_get_topic_lock(const CTox* tox, Tox_Group_Number group_number, Tox_Err_Group_State_Query* error) noexcept nogil
    cdef uint16_t tox_group_get_peer_limit(const CTox* tox, Tox_Group_Number group_number, Tox_Err_Group_State_Query* error) noexcept nogil
    cdef size_t tox_group_get_password_size(const CTox* tox, Tox_Group_Number group_number, Tox_Err_Group_State_Query* error) noexcept nogil
    cdef bool tox_group_get_password(const CTox* tox, Tox_Group_Number group_number, uint8_t* password, Tox_Err_Group_State_Query* error) noexcept nogil
    cdef Tox_Group_Message_Id tox_group_send_message(const CTox* tox, Tox_Group_Number group_number, Tox_Message_Type message_type, const uint8_t* message, size_t message_len, Tox_Err_Group_Send_Message* error) noexcept nogil
    cdef Tox_Group_Message_Id tox_group_send_private_message(const CTox* tox, Tox_Group_Number group_number, Tox_Group_Peer_Number peer_id, Tox_Message_Type message_type, const uint8_t* message, size_t message_len, Tox_Err_Group_Send_Private_Message* error) noexcept nogil
    cdef bool tox_group_send_custom_packet(const CTox* tox, Tox_Group_Number group_number, bool lossless, const uint8_t* data, size_t data_len, Tox_Err_Group_Send_Custom_Packet* error) noexcept nogil
    cdef bool tox_group_send_custom_private_packet(const CTox* tox, Tox_Group_Number group_number, Tox_Group_Peer_Number peer_id, bool lossless, const uint8_t* data, size_t data_len, Tox_Err_Group_Send_Custom_Private_Packet* error) noexcept nogil
    cdef bool tox_group_invite_friend(const CTox* tox, Tox_Group_Number group_number, Tox_Friend_Number friend_number, Tox_Err_Group_Invite_Friend* error) noexcept nogil
    cdef Tox_Group_Number tox_group_invite_accept(CTox* tox, Tox_Friend_Number friend_number, const uint8_t* invite_data, size_t invite_data_len, const uint8_t* name, size_t name_len, const uint8_t* password, size_t password_len, Tox_Err_Group_Invite_Accept* error) noexcept nogil
    cdef bool tox_group_set_password(CTox* tox, Tox_Group_Number group_number, const uint8_t* password, size_t password_len, Tox_Err_Group_Set_Password* error) noexcept nogil
    cdef bool tox_group_set_topic_lock(CTox* tox, Tox_Group_Number group_number, Tox_Group_Topic_Lock topic_lock, Tox_Err_Group_Set_Topic_Lock* error) noexcept nogil
    cdef bool tox_group_set_voice_state(CTox* tox, Tox_Group_Number group_number, Tox_Group_Voice_State voice_state, Tox_Err_Group_Set_Voice_State* error) noexcept nogil
    cdef bool tox_group_set_privacy_state(CTox* tox, Tox_Group_Number group_number, Tox_Group_Privacy_State privacy_state, Tox_Err_Group_Set_Privacy_State* error) noexcept nogil
    cdef bool tox_group_set_peer_limit(CTox* tox, Tox_Group_Number group_number, uint16_t peer_limit, Tox_Err_Group_Set_Peer_Limit* error) noexcept nogil
    cdef bool tox_group_set_ignore(CTox* tox, Tox_Group_Number group_number, Tox_Group_Peer_Number peer_id, bool ignore, Tox_Err_Group_Set_Ignore* error) noexcept nogil
    cdef bool tox_group_set_role(CTox* tox, Tox_Group_Number group_number, Tox_Group_Peer_Number peer_id, Tox_Group_Role role, Tox_Err_Group_Set_Role* error) noexcept nogil
    cdef bool tox_group_kick_peer(const CTox* tox, Tox_Group_Number group_number, Tox_Group_Peer_Number peer_id, Tox_Err_Group_Kick_Peer* error) noexcept nogil
    cdef uint32_t tox_group_peer_public_key_size() noexcept nogil
    cdef size_t tox_group_peer_get_name_size(const CTox* tox, Tox_Group_Number group_number, Tox_Group_Peer_Number group_peer_number, Tox_Err_Group_Peer_Query* error) noexcept nogil
    cdef bool tox_group_peer_get_name(const CTox* tox, Tox_Group_Number group_number, Tox_Group_Peer_Number group_peer_number, uint8_t* name, Tox_Err_Group_Peer_Query* error) noexcept nogil
    cdef Tox_User_Status tox_group_peer_get_status(const CTox* tox, Tox_Group_Number group_number, Tox_Group_Peer_Number group_peer_number, Tox_Err_Group_Peer_Query* error) noexcept nogil
    cdef Tox_Group_Role tox_group_peer_get_role(const CTox* tox, Tox_Group_Number group_number, Tox_Group_Peer_Number group_peer_number, Tox_Err_Group_Peer_Query* error) noexcept nogil
    cdef Tox_Connection tox_group_peer_get_connection_status(const CTox* tox, Tox_Group_Number group_number, Tox_Group_Peer_Number group_peer_number, Tox_Err_Group_Peer_Query* error) noexcept nogil
    cdef bool tox_group_peer_get_public_key(const CTox* tox, Tox_Group_Number group_number, Tox_Group_Peer_Number group_peer_number, uint8_t* public_key, Tox_Err_Group_Peer_Query* error) noexcept nogil
    cdef bool tox_options_get_ipv6_enabled(const Tox_Options* self) noexcept nogil
    cdef void tox_options_set_ipv6_enabled(Tox_Options* self, bool ipv6_enabled) noexcept nogil
    cdef bool tox_options_get_udp_enabled(const Tox_Options* self) noexcept nogil
    cdef void tox_options_set_udp_enabled(Tox_Options* self, bool udp_enabled) noexcept nogil
    cdef bool tox_options_get_local_discovery_enabled(const Tox_Options* self) noexcept nogil
    cdef void tox_options_set_local_discovery_enabled(Tox_Options* self, bool local_discovery_enabled) noexcept nogil
    cdef bool tox_options_get_dht_announcements_enabled(const Tox_Options* self) noexcept nogil
    cdef void tox_options_set_dht_announcements_enabled(Tox_Options* self, bool dht_announcements_enabled) noexcept nogil
    cdef Tox_Proxy_Type tox_options_get_proxy_type(const Tox_Options* self) noexcept nogil
    cdef void tox_options_set_proxy_type(Tox_Options* self, Tox_Proxy_Type proxy_type) noexcept nogil
    cdef const char* tox_options_get_proxy_host(const Tox_Options* self) noexcept nogil
    cdef bool tox_options_set_proxy_host(Tox_Options* self, const char* proxy_host) noexcept nogil
    cdef uint16_t tox_options_get_proxy_port(const Tox_Options* self) noexcept nogil
    cdef void tox_options_set_proxy_port(Tox_Options* self, uint16_t proxy_port) noexcept nogil
    cdef uint16_t tox_options_get_start_port(const Tox_Options* self) noexcept nogil
    cdef void tox_options_set_start_port(Tox_Options* self, uint16_t start_port) noexcept nogil
    cdef uint16_t tox_options_get_end_port(const Tox_Options* self) noexcept nogil
    cdef void tox_options_set_end_port(Tox_Options* self, uint16_t end_port) noexcept nogil
    cdef uint16_t tox_options_get_tcp_port(const Tox_Options* self) noexcept nogil
    cdef void tox_options_set_tcp_port(Tox_Options* self, uint16_t tcp_port) noexcept nogil
    cdef bool tox_options_get_hole_punching_enabled(const Tox_Options* self) noexcept nogil
    cdef void tox_options_set_hole_punching_enabled(Tox_Options* self, bool hole_punching_enabled) noexcept nogil
    cdef Tox_Savedata_Type tox_options_get_savedata_type(const Tox_Options* self) noexcept nogil
    cdef void tox_options_set_savedata_type(Tox_Options* self, Tox_Savedata_Type savedata_type) noexcept nogil
    cdef const uint8_t* tox_options_get_savedata_data(const Tox_Options* self) noexcept nogil
    cdef bool tox_options_set_savedata_data(Tox_Options* self, const uint8_t* savedata_data, size_t savedata_data_len) noexcept nogil
    cdef size_t tox_options_get_savedata_length(const Tox_Options* self) noexcept nogil
    cdef void tox_options_set_savedata_length(Tox_Options* self, size_t savedata_length) noexcept nogil
    cdef tox_log_cb* tox_options_get_log_callback(const Tox_Options* self) noexcept nogil
    cdef void tox_options_set_log_callback(Tox_Options* self, tox_log_cb* log_callback) noexcept nogil
    cdef void* tox_options_get_log_user_data(const Tox_Options* self) noexcept nogil
    cdef void tox_options_set_log_user_data(Tox_Options* self, void* log_user_data) noexcept nogil
    cdef bool tox_options_get_experimental_owned_data(const Tox_Options* self) noexcept nogil
    cdef void tox_options_set_experimental_owned_data(Tox_Options* self, bool experimental_owned_data) noexcept nogil
    cdef bool tox_options_get_experimental_thread_safety(const Tox_Options* self) noexcept nogil
    cdef void tox_options_set_experimental_thread_safety(Tox_Options* self, bool experimental_thread_safety) noexcept nogil
    cdef bool tox_options_get_experimental_groups_persistence(const Tox_Options* self) noexcept nogil
    cdef void tox_options_set_experimental_groups_persistence(Tox_Options* self, bool experimental_groups_persistence) noexcept nogil
    cdef bool tox_options_get_experimental_disable_dns(const Tox_Options* self) noexcept nogil
    cdef void tox_options_set_experimental_disable_dns(Tox_Options* self, bool experimental_disable_dns) noexcept nogil
    cdef void tox_options_default(Tox_Options* self) noexcept nogil
    cdef void tox_options_copy(Tox_Options* self, const Tox_Options* src) noexcept nogil
    cdef Tox_Options* tox_options_new(Tox_Err_Options_New* error) noexcept nogil
    cdef void tox_options_free(Tox_Options* self) noexcept nogil
    cdef uint32_t tox_version_major() noexcept nogil
    cdef uint32_t tox_version_minor() noexcept nogil
    cdef uint32_t tox_version_patch() noexcept nogil
    cdef bool tox_version_is_compatible(uint32_t major, uint32_t minor, uint32_t patch) noexcept nogil
    cdef uint32_t tox_public_key_size() noexcept nogil
    cdef uint32_t tox_secret_key_size() noexcept nogil
    cdef uint32_t tox_dht_id_size() noexcept nogil
    cdef uint32_t tox_nospam_size() noexcept nogil
    cdef uint32_t tox_address_size() noexcept nogil
    cdef uint32_t tox_max_name_length() noexcept nogil
    cdef uint32_t tox_max_status_message_length() noexcept nogil
    cdef uint32_t tox_max_friend_request_length() noexcept nogil
    cdef uint32_t tox_max_message_length() noexcept nogil
    cdef uint32_t tox_max_custom_packet_size() noexcept nogil
    cdef uint32_t tox_hash_length() noexcept nogil
    cdef uint32_t tox_max_filename_length() noexcept nogil
    cdef uint32_t tox_max_hostname_length() noexcept nogil
    cdef CTox* tox_new(const Tox_Options* options, Tox_Err_New* error) noexcept nogil
    cdef void tox_kill(CTox* self) noexcept nogil
    cdef size_t tox_get_savedata_size(const CTox* self) noexcept nogil
    cdef void tox_get_savedata(const CTox* self, uint8_t* savedata) noexcept nogil
    cdef bool tox_bootstrap(CTox* self, const char* host, uint16_t port, const uint8_t* public_key, Tox_Err_Bootstrap* error) noexcept nogil
    cdef bool tox_add_tcp_relay(CTox* self, const char* host, uint16_t port, const uint8_t* public_key, Tox_Err_Bootstrap* error) noexcept nogil
    cdef Tox_Connection tox_self_get_connection_status(const CTox* self) noexcept nogil
    cdef uint32_t tox_iteration_interval(const CTox* self) noexcept nogil
    cdef void tox_iterate(CTox* self, void* user_data) noexcept nogil
    cdef void tox_self_get_address(const CTox* self, uint8_t* address) noexcept nogil
    cdef void tox_self_set_nospam(CTox* self, uint32_t nospam) noexcept nogil
    cdef uint32_t tox_self_get_nospam(const CTox* self) noexcept nogil
    cdef void tox_self_get_public_key(const CTox* self, uint8_t* public_key) noexcept nogil
    cdef void tox_self_get_secret_key(const CTox* self, uint8_t* secret_key) noexcept nogil
    cdef bool tox_self_set_name(CTox* self, const uint8_t* name, size_t name_len, Tox_Err_Set_Info* error) noexcept nogil
    cdef size_t tox_self_get_name_size(const CTox* self) noexcept nogil
    cdef void tox_self_get_name(const CTox* self, uint8_t* name) noexcept nogil
    cdef bool tox_self_set_status_message(CTox* self, const uint8_t* status_message, size_t status_message_len, Tox_Err_Set_Info* error) noexcept nogil
    cdef size_t tox_self_get_status_message_size(const CTox* self) noexcept nogil
    cdef void tox_self_get_status_message(const CTox* self, uint8_t* status_message) noexcept nogil
    cdef void tox_self_set_status(CTox* self, Tox_User_Status status) noexcept nogil
    cdef Tox_User_Status tox_self_get_status(const CTox* self) noexcept nogil
    cdef size_t tox_self_get_friend_list_size(const CTox* self) noexcept nogil
    cdef void tox_self_get_friend_list(const CTox* self, Tox_Friend_Number* friend_list) noexcept nogil
    cdef bool tox_self_set_typing(CTox* self, Tox_Friend_Number friend_number, bool typing, Tox_Err_Set_Typing* error) noexcept nogil
    cdef bool tox_hash(uint8_t* hash, const uint8_t* data, size_t data_len) noexcept nogil
    cdef bool tox_file_control(CTox* self, Tox_Friend_Number friend_number, Tox_File_Number file_number, Tox_File_Control control, Tox_Err_File_Control* error) noexcept nogil
    cdef bool tox_file_seek(CTox* self, Tox_Friend_Number friend_number, Tox_File_Number file_number, uint64_t position, Tox_Err_File_Seek* error) noexcept nogil
    cdef bool tox_file_get_file_id(const CTox* self, Tox_Friend_Number friend_number, Tox_File_Number file_number, uint8_t* file_id, Tox_Err_File_Get* error) noexcept nogil
    cdef bool tox_file_send_chunk(CTox* self, Tox_Friend_Number friend_number, Tox_File_Number file_number, uint64_t position, const uint8_t* data, size_t data_len, Tox_Err_File_Send_Chunk* error) noexcept nogil
    cdef bool tox_conference_invite(CTox* self, Tox_Friend_Number friend_number, Tox_Conference_Number conference_number, Tox_Err_Conference_Invite* error) noexcept nogil
    cdef size_t tox_conference_get_chatlist_size(const CTox* self) noexcept nogil
    cdef void tox_conference_get_chatlist(const CTox* self, Tox_Conference_Number* chatlist) noexcept nogil
    cdef void tox_self_get_dht_id(const CTox* self, uint8_t* dht_id) noexcept nogil
    cdef uint16_t tox_self_get_udp_port(const CTox* self, Tox_Err_Get_Port* error) noexcept nogil
    cdef uint16_t tox_self_get_tcp_port(const CTox* self, Tox_Err_Get_Port* error) noexcept nogil
    cdef uint32_t tox_group_get_group_list_size(const CTox* self) noexcept nogil
    cdef void tox_group_get_group_list(const CTox* self, Tox_Group_Number* group_list) noexcept nogil
    cdef void tox_callback_self_connection_status(CTox* self, tox_self_connection_status_cb* callback) noexcept nogil
    cdef void tox_callback_friend_name(CTox* self, tox_friend_name_cb* callback) noexcept nogil
    cdef void tox_callback_friend_status_message(CTox* self, tox_friend_status_message_cb* callback) noexcept nogil
    cdef void tox_callback_friend_status(CTox* self, tox_friend_status_cb* callback) noexcept nogil
    cdef void tox_callback_friend_connection_status(CTox* self, tox_friend_connection_status_cb* callback) noexcept nogil
    cdef void tox_callback_friend_typing(CTox* self, tox_friend_typing_cb* callback) noexcept nogil
    cdef void tox_callback_friend_read_receipt(CTox* self, tox_friend_read_receipt_cb* callback) noexcept nogil
    cdef void tox_callback_friend_request(CTox* self, tox_friend_request_cb* callback) noexcept nogil
    cdef void tox_callback_friend_message(CTox* self, tox_friend_message_cb* callback) noexcept nogil
    cdef void tox_callback_file_recv_control(CTox* self, tox_file_recv_control_cb* callback) noexcept nogil
    cdef void tox_callback_file_chunk_request(CTox* self, tox_file_chunk_request_cb* callback) noexcept nogil
    cdef void tox_callback_file_recv(CTox* self, tox_file_recv_cb* callback) noexcept nogil
    cdef void tox_callback_file_recv_chunk(CTox* self, tox_file_recv_chunk_cb* callback) noexcept nogil
    cdef void tox_callback_conference_invite(CTox* self, tox_conference_invite_cb* callback) noexcept nogil
    cdef void tox_callback_conference_connected(CTox* self, tox_conference_connected_cb* callback) noexcept nogil
    cdef void tox_callback_conference_message(CTox* self, tox_conference_message_cb* callback) noexcept nogil
    cdef void tox_callback_conference_title(CTox* self, tox_conference_title_cb* callback) noexcept nogil
    cdef void tox_callback_conference_peer_name(CTox* self, tox_conference_peer_name_cb* callback) noexcept nogil
    cdef void tox_callback_conference_peer_list_changed(CTox* self, tox_conference_peer_list_changed_cb* callback) noexcept nogil
    cdef void tox_callback_friend_lossy_packet(CTox* self, tox_friend_lossy_packet_cb* callback) noexcept nogil
    cdef void tox_callback_friend_lossless_packet(CTox* self, tox_friend_lossless_packet_cb* callback) noexcept nogil
    cdef void tox_callback_group_peer_name(CTox* self, tox_group_peer_name_cb* callback) noexcept nogil
    cdef void tox_callback_group_peer_status(CTox* self, tox_group_peer_status_cb* callback) noexcept nogil
    cdef void tox_callback_group_topic(CTox* self, tox_group_topic_cb* callback) noexcept nogil
    cdef void tox_callback_group_privacy_state(CTox* self, tox_group_privacy_state_cb* callback) noexcept nogil
    cdef void tox_callback_group_voice_state(CTox* self, tox_group_voice_state_cb* callback) noexcept nogil
    cdef void tox_callback_group_topic_lock(CTox* self, tox_group_topic_lock_cb* callback) noexcept nogil
    cdef void tox_callback_group_peer_limit(CTox* self, tox_group_peer_limit_cb* callback) noexcept nogil
    cdef void tox_callback_group_password(CTox* self, tox_group_password_cb* callback) noexcept nogil
    cdef void tox_callback_group_message(CTox* self, tox_group_message_cb* callback) noexcept nogil
    cdef void tox_callback_group_private_message(CTox* self, tox_group_private_message_cb* callback) noexcept nogil
    cdef void tox_callback_group_custom_packet(CTox* self, tox_group_custom_packet_cb* callback) noexcept nogil
    cdef void tox_callback_group_custom_private_packet(CTox* self, tox_group_custom_private_packet_cb* callback) noexcept nogil
    cdef void tox_callback_group_invite(CTox* self, tox_group_invite_cb* callback) noexcept nogil
    cdef void tox_callback_group_peer_join(CTox* self, tox_group_peer_join_cb* callback) noexcept nogil
    cdef void tox_callback_group_peer_exit(CTox* self, tox_group_peer_exit_cb* callback) noexcept nogil
    cdef void tox_callback_group_self_join(CTox* self, tox_group_self_join_cb* callback) noexcept nogil
    cdef void tox_callback_group_join_fail(CTox* self, tox_group_join_fail_cb* callback) noexcept nogil
    cdef void tox_callback_group_moderation(CTox* self, tox_group_moderation_cb* callback) noexcept nogil


cdef class Options:
    cdef Tox_Options* _ptr
    cdef Tox_Options* _get(self) except *
    cdef void _close(self) except *
    cdef Tox_Options* _new(self)


cdef class Tox:
    cdef CTox* _ptr
    cdef object _av
    cdef PyThread_type_lock _lock
    cdef object _events
    cdef CTox* _get(self) except *
    cdef void _close(self) except *
    cdef CTox* _new(self, Options options)
    cdef int _acquire(self) except -1 nogil
    cdef void _release(self) noexcept nogil
