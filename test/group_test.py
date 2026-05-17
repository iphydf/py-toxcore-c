import unittest
from typing import Callable
from typing import TypeVar

import pytox.toxcore.tox as c

T = TypeVar("T")


class GroupTest(unittest.TestCase):
    """Exercises the NGC group API on a locally-created group."""

    @staticmethod
    def _tolerant(fn: Callable[[], T]) -> None:
        # Some group operations depend on connection state; calling them still
        # exercises the binding even when the core rejects them.
        try:
            fn()
        except c.ApiException:
            pass

    @staticmethod
    def _new_group(tox: c.Tox_Ptr) -> int:
        return tox.group_new(
            c.Tox_Group_Privacy_State.TOX_GROUP_PRIVACY_STATE_PRIVATE,
            b"test group",
            b"me",
        )

    def test_group_new(self) -> None:
        with c.Tox_Ptr() as tox:
            group_number = self._new_group(tox)
            self.assertIn(group_number, tox.group_group_list)

    def test_group_query(self) -> None:
        with c.Tox_Ptr() as tox:
            g = self._new_group(tox)
            self.assertEqual(tox.group_get_name(g), b"test group")
            self.assertEqual(tox.group_get_self_name(g), b"me")
            self.assertEqual(len(tox.group_get_chat_id(g)), 32)
            self.assertEqual(len(tox.group_get_self_public_key(g)), 32)
            tox.group_get_self_peer_id(g)
            tox.group_get_self_role(g)
            tox.group_get_self_status(g)
            tox.group_get_privacy_state(g)
            tox.group_get_voice_state(g)
            tox.group_get_topic_lock(g)
            tox.group_get_topic(g)
            tox.group_get_password(g)
            tox.group_get_peer_limit(g)
            tox.group_is_connected(g)

    def test_group_self_status(self) -> None:
        with c.Tox_Ptr() as tox:
            g = self._new_group(tox)
            tox.group_set_self_name(g, b"renamed")
            self.assertEqual(tox.group_get_self_name(g), b"renamed")
            tox.group_set_self_status(g,
                                      c.Tox_User_Status.TOX_USER_STATUS_AWAY)
            self.assertEqual(tox.group_get_self_status(g),
                             c.Tox_User_Status.TOX_USER_STATUS_AWAY)

    def test_group_founder_settings(self) -> None:
        with c.Tox_Ptr() as tox:
            g = self._new_group(tox)
            self._tolerant(lambda: tox.group_set_topic(g, b"the topic"))
            self._tolerant(lambda: tox.group_set_peer_limit(g, 10))
            self._tolerant(lambda: tox.group_set_voice_state(
                g, c.Tox_Group_Voice_State.TOX_GROUP_VOICE_STATE_MODERATOR))
            self._tolerant(lambda: tox.group_set_topic_lock(
                g, c.Tox_Group_Topic_Lock.TOX_GROUP_TOPIC_LOCK_DISABLED))
            self._tolerant(lambda: tox.group_set_privacy_state(
                g, c.Tox_Group_Privacy_State.TOX_GROUP_PRIVACY_STATE_PUBLIC))
            self._tolerant(lambda: tox.group_set_password(g, b"secret"))

    def test_group_send_message(self) -> None:
        with c.Tox_Ptr() as tox:
            g = self._new_group(tox)
            self._tolerant(lambda: tox.group_send_message(
                g, c.Tox_Message_Type.TOX_MESSAGE_TYPE_NORMAL, b"hello"))
            self._tolerant(
                lambda: tox.group_send_custom_packet(g, True, b"\x01custom"))

    def test_group_disconnect_and_leave(self) -> None:
        with c.Tox_Ptr() as tox:
            self._tolerant(lambda: tox.group_disconnect(self._new_group(tox)))
            tox.group_leave(self._new_group(tox), b"bye")


if __name__ == "__main__":
    unittest.main()
