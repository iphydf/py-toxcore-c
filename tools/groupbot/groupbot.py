# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2025 The TokTok team
"""A simple Tox group bot.

If someone adds this bot as a friend, it will invite them to a conference.
The conference is linked to a group chat, so messages sent to the conference
will be forwarded to the group chat and vice versa.

The bot only supports connecting through tor (or another SOCKS5 proxy running
on localhost:9050).

Usage:

    bazel run //py_toxcore_c/tools/groupbot -- \
        --savefile="$PWD/py_toxcore_c/tools/groupbot/groupbot.tox" \
        --password="$GROUPBOT_PASSWORD"

The checked-in savefile contains the tox ID
648BF2EEE794E94444B848F8FC6AD3BA029C9BC2649BA761EF556DA17F549022A8D7596E7DBA
Ask @iphydf for the password if you want to run the bot.
"""
import time
from typing import Any

from py_toxcore_c.tools.groupbot import api
from py_toxcore_c.tools.groupbot import commands
from py_toxcore_c.tools.groupbot import nodes

import pytox.toxcore.tox as core
from pytox.toxcore import events


class GroupBot(api.GroupBot):
    cmds: commands.Commands

    def __init__(self, config: api.Config) -> None:
        self.cmds = commands.Commands(config)

        data = self.load(config)

        with core.Options() as options:
            options.experimental_disable_dns = True
            options.experimental_groups_persistence = True
            options.local_discovery_enabled = False
            options.udp_enabled = False
            options.proxy_host = "127.0.0.1"
            options.proxy_port = 9050
            options.proxy_type = core.ProxyType.SOCKS5
            if data:
                options.savedata = data
                options.savedata_type = (
                    core.SavedataType.TOX_SAVE)
            super().__init__(config, options)

        # These are already set to something by self.load().
        # pylint: disable-next=access-member-before-definition
        if not self.name:
            self.name = config.nick.encode()
        # pylint: disable-next=access-member-before-definition
        if not self.status_message:
            self.status_message = config.status_message.encode()

    def handle(self, event: events.Event) -> None:
        match event:
            case events.SelfConnectionStatusEvent(connection_status=status):
                print("Connection status:", status.name)
            case events.FriendRequestEvent(public_key=public_key,
                                           message=message):
                print("Friend request:", public_key.hex(), message.decode())
                self.friend_add_norequest(public_key)
                self.save()
            case events.FriendConnectionStatusEvent(
                    friend_number=friend_number, connection_status=status):
                print("Friend connection status:", friend_number,
                      status.name)
                if status != core.Connection.NONE and self.conference_chatlist:
                    # Invite to conference.
                    self.conference_invite(friend_number,
                                           api.CONFERENCE)
            case events.FriendMessageEvent(friend_number=friend_number,
                                           type=type_,
                                           message=message):
                print("Friend message:", friend_number, type_.name,
                      message.decode())
            case events.ConferenceInviteEvent(friend_number=friend_number,
                                              type=type_,
                                              cookie=cookie):
                print("Conference invite:", friend_number, type_.name, cookie)
                if friend_number != api.ADMIN:
                    print("Ignoring")
                    return
                self.conference_join(friend_number, cookie)
            case events.GroupInviteEvent(friend_number=friend_number,
                                         invite_data=invite_data,
                                         group_name=group_name):
                print("Group invite:", friend_number, group_name)
                if friend_number != api.ADMIN:
                    print("Ignoring")
                    return
                self.group_invite_accept(friend_number, invite_data,
                                         self.name, b"")
            case events.GroupMessageEvent():
                self._group_message(event)
            case events.ConferenceMessageEvent():
                self._conference_message(event)

    def _group_message(self, event: events.GroupMessageEvent) -> None:
        print("Group message:", event.group_number, event.peer_id,
              event.message_type.name, event.message.decode())
        peer = self.group_peer_get_name(event.group_number,
                                        event.peer_id).decode()
        if not self.conference_chatlist:
            return
        if event.message.startswith(b"~"):
            return
        if event.message.startswith(b"!"):
            reply = self.cmds.handle(
                self,
                self.group_peer_get_public_key(event.group_number,
                                               event.peer_id),
                event.message_type,
                event.message[1:],
            )
            if reply:
                self.group_send_message(
                    event.group_number,
                    reply.message_type,
                    f"{peer}: {reply.text}".encode(),
                )
        else:
            self.conference_send_message(
                api.CONFERENCE, event.message_type,
                f"<{peer}> {event.message.decode()}".encode())

    def _conference_message(self,
                            event: events.ConferenceMessageEvent) -> None:
        conference = event.conference_number
        if self.conference_peer_number_is_ours(conference, event.peer_number):
            return
        print(
            "Conference message:",
            conference,
            event.peer_number,
            event.type.name,
            event.message.decode(),
        )
        if event.message.startswith(b"~"):
            return
        peer = self.conference_peer_get_name(conference,
                                             event.peer_number).decode()
        if event.message.startswith(b"!"):
            reply = self.cmds.handle(
                self,
                self.conference_peer_get_public_key(conference,
                                                    event.peer_number),
                event.type,
                event.message[1:],
            )
            if reply:
                self.conference_send_message(
                    conference,
                    reply.message_type,
                    f"{peer}: {reply.text}".encode(),
                )
        else:
            self.group_send_message(api.GROUP, event.type,
                                    f"<{peer}> {event.message.decode()}".encode())


class ToxSaver:

    def __init__(self, tox: GroupBot) -> None:
        self.tox = tox

    def __enter__(self) -> "ToxSaver":
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.tox.save()


def main(config: api.Config) -> None:
    with GroupBot(config) as bot:
        with ToxSaver(bot):
            print("Bot ID:", bot.address.hex().upper())
            for node in nodes.get_nodes(config.nodes_url, 4):
                if not node.ipv4:
                    continue
                print(f"Connecting to {node.ipv4}:{node.port}")
                bot.bootstrap(node.ipv4, node.port,
                              bytes.fromhex(node.public_key))
                if node.tcp_ports:
                    bot.add_tcp_relay(node.ipv4, node.tcp_ports[0],
                                      bytes.fromhex(node.public_key))
            while True:
                try:
                    for event in bot.iterate():
                        bot.handle(event)
                except core.ApiException as e:
                    print("Error:", e)
                time.sleep(bot.iteration_interval / 1000)


if __name__ == "__main__":
    main(api.parse_args())
