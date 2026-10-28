from pytox import common
from pytox.toxcore import events
from types import TracebackType
from typing import NewType
from typing import Optional
from typing import Self
import enum

class ConferenceType(enum.IntEnum):
    TEXT = 0
    AV = 1

class Connection(enum.IntEnum):
    NONE = 0
    TCP = 1
    UDP = 2

class BootstrapError(ApiException):
    class Code(enum.IntEnum):
        NULL = 1
        BAD_HOST = 2
        BAD_PORT = 3
    code: BootstrapError.Code

class ConferenceByIdError(ApiException):
    class Code(enum.IntEnum):
        NULL = 1
        NOT_FOUND = 2
    code: ConferenceByIdError.Code

class ConferenceDeleteError(ApiException):
    class Code(enum.IntEnum):
        CONFERENCE_NOT_FOUND = 1
    code: ConferenceDeleteError.Code

class ConferenceGetTypeError(ApiException):
    class Code(enum.IntEnum):
        CONFERENCE_NOT_FOUND = 1
    code: ConferenceGetTypeError.Code

class ConferenceInviteError(ApiException):
    class Code(enum.IntEnum):
        CONFERENCE_NOT_FOUND = 1
        FAIL_SEND = 2
        NO_CONNECTION = 3
    code: ConferenceInviteError.Code

class ConferenceJoinError(ApiException):
    class Code(enum.IntEnum):
        INVALID_LENGTH = 1
        WRONG_TYPE = 2
        FRIEND_NOT_FOUND = 3
        DUPLICATE = 4
        INIT_FAIL = 5
        FAIL_SEND = 6
        NULL = 7
    code: ConferenceJoinError.Code

class ConferenceNewError(ApiException):
    class Code(enum.IntEnum):
        INIT = 1
    code: ConferenceNewError.Code

class ConferencePeerQueryError(ApiException):
    class Code(enum.IntEnum):
        CONFERENCE_NOT_FOUND = 1
        PEER_NOT_FOUND = 2
        NO_CONNECTION = 3
    code: ConferencePeerQueryError.Code

class ConferenceSendMessageError(ApiException):
    class Code(enum.IntEnum):
        CONFERENCE_NOT_FOUND = 1
        TOO_LONG = 2
        NO_CONNECTION = 3
        FAIL_SEND = 4
    code: ConferenceSendMessageError.Code

class ConferenceSetMaxOfflineError(ApiException):
    class Code(enum.IntEnum):
        CONFERENCE_NOT_FOUND = 1
    code: ConferenceSetMaxOfflineError.Code

class ConferenceTitleError(ApiException):
    class Code(enum.IntEnum):
        CONFERENCE_NOT_FOUND = 1
        INVALID_LENGTH = 2
        FAIL_SEND = 3
    code: ConferenceTitleError.Code

class FileByIdError(ApiException):
    class Code(enum.IntEnum):
        NULL = 1
        FRIEND_NOT_FOUND = 2
        NOT_FOUND = 3
    code: FileByIdError.Code

class FileControlError(ApiException):
    class Code(enum.IntEnum):
        FRIEND_NOT_FOUND = 1
        FRIEND_NOT_CONNECTED = 2
        NOT_FOUND = 3
        NOT_PAUSED = 4
        DENIED = 5
        ALREADY_PAUSED = 6
        SENDQ = 7
    code: FileControlError.Code

class FileGetError(ApiException):
    class Code(enum.IntEnum):
        NULL = 1
        FRIEND_NOT_FOUND = 2
        NOT_FOUND = 3
    code: FileGetError.Code

class FileSeekError(ApiException):
    class Code(enum.IntEnum):
        FRIEND_NOT_FOUND = 1
        FRIEND_NOT_CONNECTED = 2
        NOT_FOUND = 3
        DENIED = 4
        INVALID_POSITION = 5
        SENDQ = 6
    code: FileSeekError.Code

class FileSendError(ApiException):
    class Code(enum.IntEnum):
        NULL = 1
        FRIEND_NOT_FOUND = 2
        FRIEND_NOT_CONNECTED = 3
        NAME_TOO_LONG = 4
        TOO_MANY = 5
    code: FileSendError.Code

class FileSendChunkError(ApiException):
    class Code(enum.IntEnum):
        NULL = 1
        FRIEND_NOT_FOUND = 2
        FRIEND_NOT_CONNECTED = 3
        NOT_FOUND = 4
        NOT_TRANSFERRING = 5
        INVALID_LENGTH = 6
        SENDQ = 7
        WRONG_POSITION = 8
    code: FileSendChunkError.Code

class FriendAddError(ApiException):
    class Code(enum.IntEnum):
        NULL = 1
        TOO_LONG = 2
        NO_MESSAGE = 3
        OWN_KEY = 4
        ALREADY_SENT = 5
        BAD_CHECKSUM = 6
        SET_NEW_NOSPAM = 7
        MALLOC = 8
    code: FriendAddError.Code

class FriendByPublicKeyError(ApiException):
    class Code(enum.IntEnum):
        NULL = 1
        NOT_FOUND = 2
    code: FriendByPublicKeyError.Code

class FriendCustomPacketError(ApiException):
    class Code(enum.IntEnum):
        NULL = 1
        FRIEND_NOT_FOUND = 2
        FRIEND_NOT_CONNECTED = 3
        INVALID = 4
        EMPTY = 5
        TOO_LONG = 6
        SENDQ = 7
    code: FriendCustomPacketError.Code

class FriendDeleteError(ApiException):
    class Code(enum.IntEnum):
        FRIEND_NOT_FOUND = 1
    code: FriendDeleteError.Code

class FriendGetLastOnlineError(ApiException):
    class Code(enum.IntEnum):
        FRIEND_NOT_FOUND = 1
    code: FriendGetLastOnlineError.Code

class FriendGetPublicKeyError(ApiException):
    class Code(enum.IntEnum):
        FRIEND_NOT_FOUND = 1
    code: FriendGetPublicKeyError.Code

class FriendQueryError(ApiException):
    class Code(enum.IntEnum):
        NULL = 1
        FRIEND_NOT_FOUND = 2
    code: FriendQueryError.Code

class FriendSendMessageError(ApiException):
    class Code(enum.IntEnum):
        NULL = 1
        FRIEND_NOT_FOUND = 2
        FRIEND_NOT_CONNECTED = 3
        SENDQ = 4
        TOO_LONG = 5
        EMPTY = 6
    code: FriendSendMessageError.Code

class GetPortError(ApiException):
    class Code(enum.IntEnum):
        NOT_BOUND = 1
    code: GetPortError.Code

class GroupByIdError(ApiException):
    class Code(enum.IntEnum):
        NULL = 1
        NOT_FOUND = 2
    code: GroupByIdError.Code

class GroupDisconnectError(ApiException):
    class Code(enum.IntEnum):
        GROUP_NOT_FOUND = 1
        ALREADY_DISCONNECTED = 2
    code: GroupDisconnectError.Code

class GroupInviteAcceptError(ApiException):
    class Code(enum.IntEnum):
        BAD_INVITE = 1
        INIT_FAILED = 2
        TOO_LONG = 3
        EMPTY = 4
        PASSWORD = 5
        FRIEND_NOT_FOUND = 6
        FAIL_SEND = 7
        NULL = 8
    code: GroupInviteAcceptError.Code

class GroupInviteFriendError(ApiException):
    class Code(enum.IntEnum):
        GROUP_NOT_FOUND = 1
        FRIEND_NOT_FOUND = 2
        INVITE_FAIL = 3
        FAIL_SEND = 4
        DISCONNECTED = 5
    code: GroupInviteFriendError.Code

class GroupIsConnectedError(ApiException):
    class Code(enum.IntEnum):
        GROUP_NOT_FOUND = 1
    code: GroupIsConnectedError.Code

class GroupJoinError(ApiException):
    class Code(enum.IntEnum):
        INIT = 1
        BAD_CHAT_ID = 2
        EMPTY = 3
        TOO_LONG = 4
        PASSWORD = 5
        CORE = 6
    code: GroupJoinError.Code

class GroupKickPeerError(ApiException):
    class Code(enum.IntEnum):
        GROUP_NOT_FOUND = 1
        PEER_NOT_FOUND = 2
        PERMISSIONS = 3
        FAIL_ACTION = 4
        FAIL_SEND = 5
        SELF = 6
    code: GroupKickPeerError.Code

class GroupLeaveError(ApiException):
    class Code(enum.IntEnum):
        GROUP_NOT_FOUND = 1
        TOO_LONG = 2
        FAIL_SEND = 3
    code: GroupLeaveError.Code

class GroupNewError(ApiException):
    class Code(enum.IntEnum):
        TOO_LONG = 1
        EMPTY = 2
        INIT = 3
        STATE = 4
        ANNOUNCE = 5
    code: GroupNewError.Code

class GroupPeerQueryError(ApiException):
    class Code(enum.IntEnum):
        GROUP_NOT_FOUND = 1
        PEER_NOT_FOUND = 2
    code: GroupPeerQueryError.Code

class GroupSelfNameSetError(ApiException):
    class Code(enum.IntEnum):
        GROUP_NOT_FOUND = 1
        TOO_LONG = 2
        INVALID = 3
        FAIL_SEND = 4
    code: GroupSelfNameSetError.Code

class GroupSelfQueryError(ApiException):
    class Code(enum.IntEnum):
        GROUP_NOT_FOUND = 1
    code: GroupSelfQueryError.Code

class GroupSelfStatusSetError(ApiException):
    class Code(enum.IntEnum):
        GROUP_NOT_FOUND = 1
        FAIL_SEND = 2
    code: GroupSelfStatusSetError.Code

class GroupSendCustomPacketError(ApiException):
    class Code(enum.IntEnum):
        GROUP_NOT_FOUND = 1
        TOO_LONG = 2
        EMPTY = 3
        DISCONNECTED = 4
        FAIL_SEND = 5
    code: GroupSendCustomPacketError.Code

class GroupSendCustomPrivatePacketError(ApiException):
    class Code(enum.IntEnum):
        GROUP_NOT_FOUND = 1
        TOO_LONG = 2
        EMPTY = 3
        PEER_NOT_FOUND = 4
        FAIL_SEND = 5
        DISCONNECTED = 6
    code: GroupSendCustomPrivatePacketError.Code

class GroupSendMessageError(ApiException):
    class Code(enum.IntEnum):
        GROUP_NOT_FOUND = 1
        TOO_LONG = 2
        EMPTY = 3
        BAD_TYPE = 4
        PERMISSIONS = 5
        FAIL_SEND = 6
        DISCONNECTED = 7
    code: GroupSendMessageError.Code

class GroupSendPrivateMessageError(ApiException):
    class Code(enum.IntEnum):
        GROUP_NOT_FOUND = 1
        PEER_NOT_FOUND = 2
        TOO_LONG = 3
        EMPTY = 4
        BAD_TYPE = 5
        PERMISSIONS = 6
        FAIL_SEND = 7
        DISCONNECTED = 8
    code: GroupSendPrivateMessageError.Code

class GroupSetIgnoreError(ApiException):
    class Code(enum.IntEnum):
        GROUP_NOT_FOUND = 1
        PEER_NOT_FOUND = 2
        SELF = 3
    code: GroupSetIgnoreError.Code

class GroupSetPasswordError(ApiException):
    class Code(enum.IntEnum):
        GROUP_NOT_FOUND = 1
        PERMISSIONS = 2
        TOO_LONG = 3
        FAIL_SEND = 4
        MALLOC = 5
        DISCONNECTED = 6
    code: GroupSetPasswordError.Code

class GroupSetPeerLimitError(ApiException):
    class Code(enum.IntEnum):
        GROUP_NOT_FOUND = 1
        PERMISSIONS = 2
        FAIL_SET = 3
        FAIL_SEND = 4
        DISCONNECTED = 5
    code: GroupSetPeerLimitError.Code

class GroupSetPrivacyStateError(ApiException):
    class Code(enum.IntEnum):
        GROUP_NOT_FOUND = 1
        PERMISSIONS = 2
        FAIL_SET = 3
        FAIL_SEND = 4
        DISCONNECTED = 5
    code: GroupSetPrivacyStateError.Code

class GroupSetRoleError(ApiException):
    class Code(enum.IntEnum):
        GROUP_NOT_FOUND = 1
        PEER_NOT_FOUND = 2
        PERMISSIONS = 3
        ASSIGNMENT = 4
        FAIL_ACTION = 5
        SELF = 6
    code: GroupSetRoleError.Code

class GroupSetTopicLockError(ApiException):
    class Code(enum.IntEnum):
        GROUP_NOT_FOUND = 1
        INVALID = 2
        PERMISSIONS = 3
        FAIL_SET = 4
        FAIL_SEND = 5
        DISCONNECTED = 6
    code: GroupSetTopicLockError.Code

class GroupSetVoiceStateError(ApiException):
    class Code(enum.IntEnum):
        GROUP_NOT_FOUND = 1
        PERMISSIONS = 2
        FAIL_SET = 3
        FAIL_SEND = 4
        DISCONNECTED = 5
    code: GroupSetVoiceStateError.Code

class GroupStateQueryError(ApiException):
    class Code(enum.IntEnum):
        GROUP_NOT_FOUND = 1
    code: GroupStateQueryError.Code

class GroupTopicSetError(ApiException):
    class Code(enum.IntEnum):
        GROUP_NOT_FOUND = 1
        TOO_LONG = 2
        PERMISSIONS = 3
        FAIL_CREATE = 4
        FAIL_SEND = 5
        DISCONNECTED = 6
    code: GroupTopicSetError.Code

class NewError(ApiException):
    class Code(enum.IntEnum):
        NULL = 1
        MALLOC = 2
        PORT_ALLOC = 3
        PROXY_BAD_TYPE = 4
        PROXY_BAD_HOST = 5
        PROXY_BAD_PORT = 6
        PROXY_NOT_FOUND = 7
        LOAD_ENCRYPTED = 8
        LOAD_BAD_FORMAT = 9
    code: NewError.Code

class OptionsNewError(ApiException):
    class Code(enum.IntEnum):
        MALLOC = 1
    code: OptionsNewError.Code

class SetInfoError(ApiException):
    class Code(enum.IntEnum):
        NULL = 1
        TOO_LONG = 2
    code: SetInfoError.Code

class SetTypingError(ApiException):
    class Code(enum.IntEnum):
        FRIEND_NOT_FOUND = 1
    code: SetTypingError.Code

class FileControl(enum.IntEnum):
    RESUME = 0
    PAUSE = 1
    CANCEL = 2

class FileKind(enum.IntEnum):
    DATA = 0
    AVATAR = 1
    STICKER = 2
    SHA1 = 3
    SHA256 = 4

class GroupExitType(enum.IntEnum):
    QUIT = 0
    TIMEOUT = 1
    DISCONNECTED = 2
    SELF_DISCONNECTED = 3
    KICK = 4
    SYNC_ERROR = 5

class GroupJoinFail(enum.IntEnum):
    PEER_LIMIT = 0
    INVALID_PASSWORD = 1
    UNKNOWN = 2

class GroupModEvent(enum.IntEnum):
    KICK = 0
    OBSERVER = 1
    USER = 2
    MODERATOR = 3

class GroupPrivacyState(enum.IntEnum):
    PUBLIC = 0
    PRIVATE = 1

class GroupRole(enum.IntEnum):
    FOUNDER = 0
    MODERATOR = 1
    USER = 2
    OBSERVER = 3

class GroupTopicLock(enum.IntEnum):
    ENABLED = 0
    DISABLED = 1

class GroupVoiceState(enum.IntEnum):
    ALL = 0
    MODERATOR = 1
    FOUNDER = 2

class LogLevel(enum.IntEnum):
    TRACE = 0
    DEBUG = 1
    INFO = 2
    WARNING = 3
    ERROR = 4

class MessageType(enum.IntEnum):
    NORMAL = 0
    ACTION = 1

class ProxyType(enum.IntEnum):
    NONE = 0
    HTTP = 1
    SOCKS5 = 2

class SavedataType(enum.IntEnum):
    NONE = 0
    TOX_SAVE = 1
    SECRET_KEY = 2

class UserStatus(enum.IntEnum):
    NONE = 0
    AWAY = 1
    BUSY = 2
ConferenceNumber = NewType("ConferenceNumber", int)
ConferenceOfflinePeerNumber = NewType("ConferenceOfflinePeerNumber", int)
ConferencePeerNumber = NewType("ConferencePeerNumber", int)
FileNumber = NewType("FileNumber", int)
FriendMessageId = NewType("FriendMessageId", int)
FriendNumber = NewType("FriendNumber", int)
GroupMessageId = NewType("GroupMessageId", int)
GroupNumber = NewType("GroupNumber", int)
GroupPeerNumber = NewType("GroupPeerNumber", int)

class ApiException(common.ApiException): ...

class Options:
    def __enter__(self) -> Self: ...
    def __exit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None, exc_traceback: TracebackType | None) -> None: ...
    def __init__(self) -> None: ...
    def default(self) -> None: ...
    def copy(self, src: Options) -> None: ...
    @property
    def ipv6_enabled(self) -> bool: ...
    @ipv6_enabled.setter
    def ipv6_enabled(self, ipv6_enabled: bool) -> None: ...
    @property
    def udp_enabled(self) -> bool: ...
    @udp_enabled.setter
    def udp_enabled(self, udp_enabled: bool) -> None: ...
    @property
    def local_discovery_enabled(self) -> bool: ...
    @local_discovery_enabled.setter
    def local_discovery_enabled(self, local_discovery_enabled: bool) -> None: ...
    @property
    def dht_announcements_enabled(self) -> bool: ...
    @dht_announcements_enabled.setter
    def dht_announcements_enabled(self, dht_announcements_enabled: bool) -> None: ...
    @property
    def proxy_type(self) -> ProxyType: ...
    @proxy_type.setter
    def proxy_type(self, proxy_type: ProxyType) -> None: ...
    @property
    def proxy_host(self) -> str: ...
    @proxy_host.setter
    def proxy_host(self, proxy_host: str) -> None: ...
    @property
    def proxy_port(self) -> int: ...
    @proxy_port.setter
    def proxy_port(self, proxy_port: int) -> None: ...
    @property
    def start_port(self) -> int: ...
    @start_port.setter
    def start_port(self, start_port: int) -> None: ...
    @property
    def end_port(self) -> int: ...
    @end_port.setter
    def end_port(self, end_port: int) -> None: ...
    @property
    def tcp_port(self) -> int: ...
    @tcp_port.setter
    def tcp_port(self, tcp_port: int) -> None: ...
    @property
    def hole_punching_enabled(self) -> bool: ...
    @hole_punching_enabled.setter
    def hole_punching_enabled(self, hole_punching_enabled: bool) -> None: ...
    @property
    def savedata_type(self) -> SavedataType: ...
    @savedata_type.setter
    def savedata_type(self, savedata_type: SavedataType) -> None: ...
    @property
    def savedata(self) -> bytes: ...
    @savedata.setter
    def savedata(self, savedata: bytes) -> None: ...
    @property
    def experimental_groups_persistence(self) -> bool: ...
    @experimental_groups_persistence.setter
    def experimental_groups_persistence(self, experimental_groups_persistence: bool) -> None: ...
    @property
    def experimental_disable_dns(self) -> bool: ...
    @experimental_disable_dns.setter
    def experimental_disable_dns(self, experimental_disable_dns: bool) -> None: ...

class Tox:
    def __enter__(self) -> Self: ...
    def __exit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None, exc_traceback: TracebackType | None) -> None: ...
    def __init__(self, options: Optional[Options] = ...) -> None: ...
    def bootstrap(self, host: str, port: int, public_key: bytes) -> None: ...
    def add_tcp_relay(self, host: str, port: int, public_key: bytes) -> None: ...
    @property
    def iteration_interval(self) -> int: ...
    def iterate(self) -> list[events.Event]: ...
    def set_typing(self, friend_number: FriendNumber, typing: bool) -> None: ...
    def file_control(self, friend_number: FriendNumber, file_number: FileNumber, control: FileControl) -> None: ...
    def file_seek(self, friend_number: FriendNumber, file_number: FileNumber, position: int) -> None: ...
    def file_get_file_id(self, friend_number: FriendNumber, file_number: FileNumber) -> bytes: ...
    def file_send_chunk(self, friend_number: FriendNumber, file_number: FileNumber, position: int, data: bytes) -> None: ...
    def conference_invite(self, friend_number: FriendNumber, conference_number: ConferenceNumber) -> None: ...
    @property
    def savedata(self) -> bytes: ...
    @property
    def connection_status(self) -> Connection: ...
    @property
    def address(self) -> bytes: ...
    @property
    def nospam(self) -> int: ...
    @nospam.setter
    def nospam(self, nospam: int) -> None: ...
    @property
    def public_key(self) -> bytes: ...
    @property
    def secret_key(self) -> bytes: ...
    @property
    def name(self) -> bytes: ...
    @name.setter
    def name(self, name: bytes) -> None: ...
    @property
    def status_message(self) -> bytes: ...
    @status_message.setter
    def status_message(self, status_message: bytes) -> None: ...
    @property
    def status(self) -> UserStatus: ...
    @status.setter
    def status(self, status: UserStatus) -> None: ...
    @property
    def friend_list(self) -> list[FriendNumber]: ...
    @property
    def conference_chatlist(self) -> list[ConferenceNumber]: ...
    @property
    def dht_id(self) -> bytes: ...
    @property
    def udp_port(self) -> int: ...
    @property
    def tcp_port(self) -> int: ...
    @property
    def group_list(self) -> list[GroupNumber]: ...
    def conference_new(self) -> ConferenceNumber: ...
    def conference_delete(self, conference_number: ConferenceNumber) -> None: ...
    def conference_peer_count(self, conference_number: ConferenceNumber) -> int: ...
    def conference_offline_peer_count(self, conference_number: ConferenceNumber) -> int: ...
    def conference_join(self, friend_number: FriendNumber, cookie: bytes) -> ConferenceNumber: ...
    def conference_send_message(self, conference_number: ConferenceNumber, type: MessageType, message: bytes) -> None: ...
    def conference_by_id(self, id: bytes) -> ConferenceNumber: ...
    def conference_get_id(self, conference_number: ConferenceNumber) -> bytes: ...
    def conference_set_max_offline(self, conference_number: ConferenceNumber, max_offline: int) -> None: ...
    def conference_get_title(self, conference_number: ConferenceNumber) -> bytes: ...
    def conference_set_title(self, conference_number: ConferenceNumber, title: bytes) -> None: ...
    def conference_get_type(self, conference_number: ConferenceNumber) -> ConferenceType: ...
    def conference_offline_peer_get_name(self, conference_number: ConferenceNumber, conference_offline_peer_number: ConferenceOfflinePeerNumber) -> bytes: ...
    def conference_offline_peer_get_public_key(self, conference_number: ConferenceNumber, conference_offline_peer_number: ConferenceOfflinePeerNumber) -> bytes: ...
    def conference_offline_peer_get_last_active(self, conference_number: ConferenceNumber, conference_offline_peer_number: ConferenceOfflinePeerNumber) -> int: ...
    def conference_peer_number_is_ours(self, conference_number: ConferenceNumber, conference_peer_number: ConferencePeerNumber) -> bool: ...
    def conference_peer_get_name(self, conference_number: ConferenceNumber, conference_peer_number: ConferencePeerNumber) -> bytes: ...
    def conference_peer_get_public_key(self, conference_number: ConferenceNumber, conference_peer_number: ConferencePeerNumber) -> bytes: ...
    def file_by_id(self, friend_number: FriendNumber, file_id: bytes) -> FileNumber: ...
    def file_send(self, friend_number: FriendNumber, kind: int, file_size: int, file_id: Optional[bytes], filename: bytes) -> FileNumber: ...
    def friend_add(self, address: bytes, message: bytes) -> FriendNumber: ...
    def friend_add_norequest(self, public_key: bytes) -> FriendNumber: ...
    def friend_delete(self, friend_number: FriendNumber) -> None: ...
    def friend_by_public_key(self, public_key: bytes) -> FriendNumber: ...
    def friend_exists(self, friend_number: FriendNumber) -> bool: ...
    def friend_send_message(self, friend_number: FriendNumber, type: MessageType, message: bytes) -> FriendMessageId: ...
    def friend_send_lossy_packet(self, friend_number: FriendNumber, data: bytes) -> None: ...
    def friend_send_lossless_packet(self, friend_number: FriendNumber, data: bytes) -> None: ...
    def friend_get_public_key(self, friend_number: FriendNumber) -> bytes: ...
    def friend_get_last_online(self, friend_number: FriendNumber) -> int: ...
    def friend_get_name(self, friend_number: FriendNumber) -> bytes: ...
    def friend_get_status_message(self, friend_number: FriendNumber) -> bytes: ...
    def friend_get_status(self, friend_number: FriendNumber) -> UserStatus: ...
    def friend_get_connection_status(self, friend_number: FriendNumber) -> Connection: ...
    def friend_get_typing(self, friend_number: FriendNumber) -> bool: ...
    def group_new(self, privacy_state: GroupPrivacyState, group_name: bytes, name: bytes) -> GroupNumber: ...
    def group_join(self, chat_id: bytes, name: bytes, password: bytes) -> GroupNumber: ...
    def group_is_connected(self, group_number: GroupNumber) -> bool: ...
    def group_disconnect(self, group_number: GroupNumber) -> None: ...
    def group_leave(self, group_number: GroupNumber, part_message: bytes) -> None: ...
    def group_by_id(self, chat_id: bytes) -> GroupNumber: ...
    def group_send_message(self, group_number: GroupNumber, message_type: MessageType, message: bytes) -> GroupMessageId: ...
    def group_send_private_message(self, group_number: GroupNumber, peer_id: GroupPeerNumber, message_type: MessageType, message: bytes) -> GroupMessageId: ...
    def group_send_custom_packet(self, group_number: GroupNumber, lossless: bool, data: bytes) -> None: ...
    def group_send_custom_private_packet(self, group_number: GroupNumber, peer_id: GroupPeerNumber, lossless: bool, data: bytes) -> None: ...
    def group_invite_friend(self, group_number: GroupNumber, friend_number: FriendNumber) -> None: ...
    def group_invite_accept(self, friend_number: FriendNumber, invite_data: bytes, name: bytes, password: bytes) -> GroupNumber: ...
    def group_set_ignore(self, group_number: GroupNumber, peer_id: GroupPeerNumber, ignore: bool) -> None: ...
    def group_set_role(self, group_number: GroupNumber, peer_id: GroupPeerNumber, role: GroupRole) -> None: ...
    def group_kick_peer(self, group_number: GroupNumber, peer_id: GroupPeerNumber) -> None: ...
    def group_get_chat_id(self, group_number: GroupNumber) -> bytes: ...
    def group_get_self_name(self, group_number: GroupNumber) -> bytes: ...
    def group_set_self_name(self, group_number: GroupNumber, name: bytes) -> None: ...
    def group_get_self_status(self, group_number: GroupNumber) -> UserStatus: ...
    def group_set_self_status(self, group_number: GroupNumber, status: UserStatus) -> None: ...
    def group_get_self_role(self, group_number: GroupNumber) -> GroupRole: ...
    def group_get_self_peer_id(self, group_number: GroupNumber) -> GroupPeerNumber: ...
    def group_get_self_public_key(self, group_number: GroupNumber) -> bytes: ...
    def group_get_topic(self, group_number: GroupNumber) -> bytes: ...
    def group_set_topic(self, group_number: GroupNumber, topic: bytes) -> None: ...
    def group_get_name(self, group_number: GroupNumber) -> bytes: ...
    def group_get_privacy_state(self, group_number: GroupNumber) -> GroupPrivacyState: ...
    def group_set_privacy_state(self, group_number: GroupNumber, privacy_state: GroupPrivacyState) -> None: ...
    def group_get_voice_state(self, group_number: GroupNumber) -> GroupVoiceState: ...
    def group_set_voice_state(self, group_number: GroupNumber, voice_state: GroupVoiceState) -> None: ...
    def group_get_topic_lock(self, group_number: GroupNumber) -> GroupTopicLock: ...
    def group_set_topic_lock(self, group_number: GroupNumber, topic_lock: GroupTopicLock) -> None: ...
    def group_get_peer_limit(self, group_number: GroupNumber) -> int: ...
    def group_set_peer_limit(self, group_number: GroupNumber, peer_limit: int) -> None: ...
    def group_get_password(self, group_number: GroupNumber) -> bytes: ...
    def group_set_password(self, group_number: GroupNumber, password: bytes) -> None: ...
    def group_peer_get_public_key(self, group_number: GroupNumber, group_peer_number: GroupPeerNumber) -> bytes: ...
    def group_peer_get_name(self, group_number: GroupNumber, group_peer_number: GroupPeerNumber) -> bytes: ...
    def group_peer_get_status(self, group_number: GroupNumber, group_peer_number: GroupPeerNumber) -> UserStatus: ...
    def group_peer_get_role(self, group_number: GroupNumber, group_peer_number: GroupPeerNumber) -> GroupRole: ...
    def group_peer_get_connection_status(self, group_number: GroupNumber, group_peer_number: GroupPeerNumber) -> Connection: ...
VERSION: str
PUBLIC_KEY_SIZE: int
SECRET_KEY_SIZE: int
DHT_ID_SIZE: int
NOSPAM_SIZE: int
ADDRESS_SIZE: int
MAX_NAME_LENGTH: int
MAX_STATUS_MESSAGE_LENGTH: int
MAX_FRIEND_REQUEST_LENGTH: int
MAX_MESSAGE_LENGTH: int
MAX_CUSTOM_PACKET_SIZE: int
HASH_LENGTH: int
MAX_FILENAME_LENGTH: int
MAX_HOSTNAME_LENGTH: int

def version_is_compatible(major: int, minor: int, patch: int) -> bool: ...

def hash(data: bytes) -> bytes: ...
