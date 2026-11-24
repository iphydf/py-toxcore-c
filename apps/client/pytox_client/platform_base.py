# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""Platform integration interface shared by desktop, Android, and tests."""
from __future__ import annotations

import logging
from abc import ABC
from abc import abstractmethod
from pathlib import Path
from typing import Callable
from typing import Optional
from typing import Protocol

from pytox_client.media import Playout
from pytox_client.media import VideoFrame
from pytox_client.model import Call
from pytox_client.model import Friend
from pytox_client.model import FriendRequest
from pytox_client.model import Group
from pytox_client.model import GroupInvite
from pytox_client.model import GroupMessage
from pytox_client.model import Message
from pytox_client.model import PickedFile


_LOG = logging.getLogger("pytox")


class Closeable(Protocol):

    def close(self) -> None:
        ...


class CallSound(Protocol):
    """The sound side of a call, which the platform runs.

    The microphone, and the speaker playing a :class:`Playout`.
    """

    def set_speaker(self, on: bool) -> None:
        """On phones: the loudspeaker, or the earpiece held to the ear."""

    def close(self) -> None:
        ...


class Platform(ABC):
    """OS-specific operations (notification calls arrive on the Tox thread)."""

    @abstractmethod
    def copy(self, text: str) -> None:
        """Copy text to the system clipboard."""

    # The notifications are for the profile they name, whose Tox thread
    # calls them.

    def notify_message(self, profile: str, friend: Friend,
                       message: Message) -> None:
        """Show a notification for an incoming message."""

    def notify_request(self, profile: str, request: FriendRequest) -> None:
        """Show a notification for an incoming friend request."""

    def notify_invite(self, profile: str, friend: Friend,
                      invite: GroupInvite) -> None:
        """Show a notification for an incoming group invite."""

    def notify_group_message(self, profile: str, group: Group,
                             message: GroupMessage) -> None:
        """Show a group message that mentions us or is for us alone."""

    def clear_notifications(self, profile: str, friend_key: str) -> None:
        """Dismiss unread notifications for a friend's chat."""

    def clear_group_notifications(self, profile: str, group_id: str) -> None:
        """Dismiss unread notifications for a group's chat."""

    def clear_profile(self, profile: str) -> None:
        """The profile was deleted: its notifications go too."""

    @abstractmethod
    def pick_file(
        self,
        images: bool,
        on_picked: Callable[[PickedFile], None],
    ) -> None:
        """Prompt the user for a file (or image), calling ``on_picked``."""

    @abstractmethod
    def open_file(self, path: Path, name: str) -> None:
        """Open a file with the user's preferred application."""

    @abstractmethod
    def save_to_downloads(self, path: Path, name: str) -> Optional[str]:
        """Copy ``path`` to Downloads as ``name``. Return label or None."""

    @abstractmethod
    def avatar_png(self, image: bytes, size: int) -> Optional[bytes]:
        """Center-crop and downscale ``image`` to a square PNG (<= size px)."""

    @property
    def can_stay_connected(self) -> bool:
        """Whether this platform supports staying connected in the background."""
        return False

    def is_stay_connected_pref(self) -> bool:
        """Whether every profile stays connected, as last set."""
        return False

    def set_stay_connected(self, enabled: bool) -> None:
        """Remember the setting where the app finds it before Tox starts.

        It only records it: :class:`HandoverClient` moves Tox between the app
        and the service, and the service stops itself.
        """

    def start_service(self) -> None:
        """Start the background service that runs Tox to stay connected."""

    def set_back_handler(self, on_back: Optional[Callable[[], None]]) -> None:
        """While ``on_back`` is set, Back calls it instead of leaving the app.

        It's called on the system's thread. Without it, Back leaves the app.
        """

    def log(self, message: str) -> None:
        """Note how things go, for whoever reads the logs."""
        _LOG.info("%s", message)

    def open_sound(
        self,
        recorded: Callable[[bytes], None],
        playout: Playout,
    ) -> Optional[CallSound]:
        """Start the microphone and the speaker for a call.

        The microphone gives ``recorded`` frames of :data:`AUDIO_FRAME`
        samples, mono at :data:`AUDIO_RATE`, on a thread of its own; the
        speaker plays what ``playout`` gives. None if there's no sound here.
        """
        del recorded, playout
        return None

    @property
    def cameras(self) -> int:
        """How many cameras there are: phones have a front and a back one."""
        return 0

    def open_camera(
        self,
        front: bool,
        frame: Callable[[VideoFrame], None],
    ) -> Optional[Closeable]:
        """Start a camera, giving ``frame`` upright pictures on its thread.

        None if it can't.
        """
        del front, frame
        return None

    @property
    def has_earpiece(self) -> bool:
        """Whether there's an earpiece as well as a loudspeaker."""
        return False

    def call_changed(self, profile: str, call: Optional[Call],
                     friend: Optional[Friend]) -> None:
        """The profile's call rang, started, changed or ended (None).

        Phones show it outside the app and keep it going. It's called on the
        Tox thread, in the process that runs Tox.
        """

    def ask_call_permissions(self, video: bool, then: Callable[[],
                                                               None]) -> None:
        """Ask for the microphone (and the camera, for video), then go on.

        The UI calls this before calling or answering. Without them the call
        still goes ahead, and says what doesn't work.
        """
        del video
        then()

    def call_on_screen(self, call: Optional[Call]) -> None:
        """The UI shows this call, or none.

        Phones keep the screen on, and turn it off at the ear.
        """

    def is_dark_mode(self) -> bool:
        """Best-effort OS dark-theme detection."""
        return False

    def window_insets(self) -> tuple[int, int, int, int]:
        """Pixels the system bars cover: (left, top, right, bottom).

        Android draws apps edge-to-edge under the status and navigation bars;
        the UI pads itself by these. The bottom includes the on-screen
        keyboard while it's up. Desktops have none.
        """
        return (0, 0, 0, 0)

    def prepare_window(self, insets_changed: Callable[[], None]) -> None:
        """Set up the native window once the UI is built (Android only).

        ``insets_changed`` is called, on any thread, when window_insets()
        may have changed, e.g. as the keyboard comes and goes.
        """

    def set_light_system_bars(self, light: bool) -> None:
        """Dark system-bar icons (for a light UI behind them), or light ones."""

    def default_profile_dir(self) -> Path:
        """Default directory for profile.tox, chats.db, files/, avatars/."""
        return Path.home() / ".local" / "share" / "pytox"


class NoopPlatform(Platform):
    """Minimal headless Platform used in tests."""

    def __init__(self, passthrough_avatar: bool = True) -> None:
        self._passthrough_avatar = passthrough_avatar
        self.copied: list[str] = []
        self.message_notifications: list[tuple[Friend, Message]] = []
        self.request_notifications: list[FriendRequest] = []
        self.invite_notifications: list[tuple[Friend, GroupInvite]] = []
        self.group_notifications: list[tuple[Group, GroupMessage]] = []
        self.cleared: list[str] = []
        self.cleared_groups: list[str] = []

    def copy(self, text: str) -> None:
        self.copied.append(text)

    def notify_message(self, profile: str, friend: Friend,
                       message: Message) -> None:
        self.message_notifications.append((friend, message))

    def notify_request(self, profile: str, request: FriendRequest) -> None:
        self.request_notifications.append(request)

    def notify_invite(self, profile: str, friend: Friend,
                      invite: GroupInvite) -> None:
        self.invite_notifications.append((friend, invite))

    def notify_group_message(self, profile: str, group: Group,
                             message: GroupMessage) -> None:
        self.group_notifications.append((group, message))

    def clear_notifications(self, profile: str, friend_key: str) -> None:
        self.cleared.append(friend_key)

    def clear_group_notifications(self, profile: str, group_id: str) -> None:
        self.cleared_groups.append(group_id)

    def pick_file(
        self,
        images: bool,
        on_picked: Callable[[PickedFile], None],
    ) -> None:
        del images, on_picked

    def open_file(self, path: Path, name: str) -> None:
        del path, name

    def save_to_downloads(self, path: Path, name: str) -> Optional[str]:
        del path, name
        return None

    def avatar_png(self, image: bytes, size: int) -> Optional[bytes]:
        del size
        return image if self._passthrough_avatar else None
