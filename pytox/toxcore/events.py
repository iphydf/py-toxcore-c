from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import Union

if TYPE_CHECKING:
    from pytox.toxcore.tox import ConferenceNumber
    from pytox.toxcore.tox import ConferencePeerNumber
    from pytox.toxcore.tox import ConferenceType
    from pytox.toxcore.tox import Connection
    from pytox.toxcore.tox import FileControl
    from pytox.toxcore.tox import FileNumber
    from pytox.toxcore.tox import FriendMessageId
    from pytox.toxcore.tox import FriendNumber
    from pytox.toxcore.tox import GroupExitType
    from pytox.toxcore.tox import GroupJoinFail
    from pytox.toxcore.tox import GroupMessageId
    from pytox.toxcore.tox import GroupModEvent
    from pytox.toxcore.tox import GroupNumber
    from pytox.toxcore.tox import GroupPeerNumber
    from pytox.toxcore.tox import GroupPrivacyState
    from pytox.toxcore.tox import GroupTopicLock
    from pytox.toxcore.tox import GroupVoiceState
    from pytox.toxcore.tox import MessageType
    from pytox.toxcore.tox import UserStatus


@dataclass(frozen=True, slots=True)
class SelfConnectionStatusEvent:
    connection_status: Connection


@dataclass(frozen=True, slots=True)
class FriendNameEvent:
    friend_number: FriendNumber
    name: bytes


@dataclass(frozen=True, slots=True)
class FriendStatusMessageEvent:
    friend_number: FriendNumber
    message: bytes


@dataclass(frozen=True, slots=True)
class FriendStatusEvent:
    friend_number: FriendNumber
    status: UserStatus


@dataclass(frozen=True, slots=True)
class FriendConnectionStatusEvent:
    friend_number: FriendNumber
    connection_status: Connection


@dataclass(frozen=True, slots=True)
class FriendTypingEvent:
    friend_number: FriendNumber
    typing: bool


@dataclass(frozen=True, slots=True)
class FriendReadReceiptEvent:
    friend_number: FriendNumber
    message_id: FriendMessageId


@dataclass(frozen=True, slots=True)
class FriendRequestEvent:
    public_key: bytes
    message: bytes


@dataclass(frozen=True, slots=True)
class FriendMessageEvent:
    friend_number: FriendNumber
    type: MessageType
    message: bytes


@dataclass(frozen=True, slots=True)
class FileRecvControlEvent:
    friend_number: FriendNumber
    file_number: FileNumber
    control: FileControl


@dataclass(frozen=True, slots=True)
class FileChunkRequestEvent:
    friend_number: FriendNumber
    file_number: FileNumber
    position: int
    length: int


@dataclass(frozen=True, slots=True)
class FileRecvEvent:
    friend_number: FriendNumber
    file_number: FileNumber
    kind: int
    file_size: int
    filename: bytes


@dataclass(frozen=True, slots=True)
class FileRecvChunkEvent:
    friend_number: FriendNumber
    file_number: FileNumber
    position: int
    data: bytes


@dataclass(frozen=True, slots=True)
class ConferenceInviteEvent:
    friend_number: FriendNumber
    type: ConferenceType
    cookie: bytes


@dataclass(frozen=True, slots=True)
class ConferenceConnectedEvent:
    conference_number: ConferenceNumber


@dataclass(frozen=True, slots=True)
class ConferenceMessageEvent:
    conference_number: ConferenceNumber
    peer_number: ConferencePeerNumber
    type: MessageType
    message: bytes


@dataclass(frozen=True, slots=True)
class ConferenceTitleEvent:
    conference_number: ConferenceNumber
    peer_number: ConferencePeerNumber
    title: bytes


@dataclass(frozen=True, slots=True)
class ConferencePeerNameEvent:
    conference_number: ConferenceNumber
    peer_number: ConferencePeerNumber
    name: bytes


@dataclass(frozen=True, slots=True)
class ConferencePeerListChangedEvent:
    conference_number: ConferenceNumber


@dataclass(frozen=True, slots=True)
class FriendLossyPacketEvent:
    friend_number: FriendNumber
    data: bytes


@dataclass(frozen=True, slots=True)
class FriendLosslessPacketEvent:
    friend_number: FriendNumber
    data: bytes


@dataclass(frozen=True, slots=True)
class GroupPeerNameEvent:
    group_number: GroupNumber
    peer_id: GroupPeerNumber
    name: bytes


@dataclass(frozen=True, slots=True)
class GroupPeerStatusEvent:
    group_number: GroupNumber
    peer_id: GroupPeerNumber
    status: UserStatus


@dataclass(frozen=True, slots=True)
class GroupTopicEvent:
    group_number: GroupNumber
    peer_id: GroupPeerNumber
    topic: bytes


@dataclass(frozen=True, slots=True)
class GroupPrivacyStateEvent:
    group_number: GroupNumber
    privacy_state: GroupPrivacyState


@dataclass(frozen=True, slots=True)
class GroupVoiceStateEvent:
    group_number: GroupNumber
    voice_state: GroupVoiceState


@dataclass(frozen=True, slots=True)
class GroupTopicLockEvent:
    group_number: GroupNumber
    topic_lock: GroupTopicLock


@dataclass(frozen=True, slots=True)
class GroupPeerLimitEvent:
    group_number: GroupNumber
    peer_limit: int


@dataclass(frozen=True, slots=True)
class GroupPasswordEvent:
    group_number: GroupNumber
    password: bytes


@dataclass(frozen=True, slots=True)
class GroupMessageEvent:
    group_number: GroupNumber
    peer_id: GroupPeerNumber
    message_type: MessageType
    message: bytes
    message_id: GroupMessageId


@dataclass(frozen=True, slots=True)
class GroupPrivateMessageEvent:
    group_number: GroupNumber
    peer_id: GroupPeerNumber
    message_type: MessageType
    message: bytes
    message_id: GroupMessageId


@dataclass(frozen=True, slots=True)
class GroupCustomPacketEvent:
    group_number: GroupNumber
    peer_id: GroupPeerNumber
    data: bytes


@dataclass(frozen=True, slots=True)
class GroupCustomPrivatePacketEvent:
    group_number: GroupNumber
    peer_id: GroupPeerNumber
    data: bytes


@dataclass(frozen=True, slots=True)
class GroupInviteEvent:
    friend_number: FriendNumber
    invite_data: bytes
    group_name: bytes


@dataclass(frozen=True, slots=True)
class GroupPeerJoinEvent:
    group_number: GroupNumber
    peer_id: GroupPeerNumber


@dataclass(frozen=True, slots=True)
class GroupPeerExitEvent:
    group_number: GroupNumber
    peer_id: GroupPeerNumber
    exit_type: GroupExitType
    name: bytes
    part_message: bytes


@dataclass(frozen=True, slots=True)
class GroupSelfJoinEvent:
    group_number: GroupNumber


@dataclass(frozen=True, slots=True)
class GroupJoinFailEvent:
    group_number: GroupNumber
    fail_type: GroupJoinFail


@dataclass(frozen=True, slots=True)
class GroupModerationEvent:
    group_number: GroupNumber
    source_peer_id: GroupPeerNumber
    target_peer_id: GroupPeerNumber
    mod_type: GroupModEvent


Event = Union[
    SelfConnectionStatusEvent,
    FriendNameEvent,
    FriendStatusMessageEvent,
    FriendStatusEvent,
    FriendConnectionStatusEvent,
    FriendTypingEvent,
    FriendReadReceiptEvent,
    FriendRequestEvent,
    FriendMessageEvent,
    FileRecvControlEvent,
    FileChunkRequestEvent,
    FileRecvEvent,
    FileRecvChunkEvent,
    ConferenceInviteEvent,
    ConferenceConnectedEvent,
    ConferenceMessageEvent,
    ConferenceTitleEvent,
    ConferencePeerNameEvent,
    ConferencePeerListChangedEvent,
    FriendLossyPacketEvent,
    FriendLosslessPacketEvent,
    GroupPeerNameEvent,
    GroupPeerStatusEvent,
    GroupTopicEvent,
    GroupPrivacyStateEvent,
    GroupVoiceStateEvent,
    GroupTopicLockEvent,
    GroupPeerLimitEvent,
    GroupPasswordEvent,
    GroupMessageEvent,
    GroupPrivateMessageEvent,
    GroupCustomPacketEvent,
    GroupCustomPrivatePacketEvent,
    GroupInviteEvent,
    GroupPeerJoinEvent,
    GroupPeerExitEvent,
    GroupSelfJoinEvent,
    GroupJoinFailEvent,
    GroupModerationEvent,
]
