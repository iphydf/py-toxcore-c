# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""Tests for the profiles on disk and the shown one, without Tox."""
from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any
from typing import Callable

from pytox_client.model import Call
from pytox_client.model import ClientState
from pytox_client.model import Profile
from pytox_client.model import Settings
from pytox_client.profiles import Profiles
from pytox_client.profiles import ShownClient


class _FakeClient:
    """A profile's client that only keeps its state."""

    def __init__(self, directory: Path, name: str) -> None:
        self.directory = directory
        self._state = ClientState(profile=Profile(name=f"profile {name}"))
        self._listeners: list[Callable[[ClientState], None]] = []
        self.visible = False
        self.deleted = False

    @property
    def state(self) -> ClientState:
        return self._state

    def set_state(self, state: ClientState) -> None:
        self._state = state
        for listener in list(self._listeners):
            listener(state)

    def start(self) -> None:
        pass

    def close(self) -> None:
        pass

    def subscribe(self, listener: Callable[[ClientState], None],
                  emit_current: bool = True) -> Callable[[], None]:
        self._listeners.append(listener)
        if emit_current:
            listener(self._state)
        return lambda: self._listeners.remove(listener)

    def watch_video(self, listener: Callable[..., None]) -> Callable[[], None]:
        return lambda: None

    def set_visible(self, visible: bool) -> None:
        self.visible = visible

    def update_settings(self, settings: Settings) -> None:
        self.set_state(replace(self._state, settings=settings))

    def delete_profile(self) -> None:
        self.deleted = True


class ProfilesTest(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.made: dict[str, _FakeClient] = {}

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _profiles(self) -> Profiles:

        def make(directory: Path, name: str) -> Any:
            self.made[name] = _FakeClient(directory, name)
            return self.made[name]

        return Profiles(self.root, make)

    def test_old_profile_becomes_the_first(self) -> None:
        (self.root / "profile.tox").write_text("tox")
        (self.root / "chats.db").write_text("db")
        (self.root / "files").mkdir()
        profiles = self._profiles()
        self.assertEqual(profiles.names, ["1"])
        first = self.root / "profiles" / "1"
        self.assertEqual((first / "profile.tox").read_text(), "tox")
        self.assertEqual((first / "chats.db").read_text(), "db")
        self.assertTrue((first / "files").is_dir())
        self.assertFalse((self.root / "profile.tox").exists())

    def test_added_is_shown_and_stays_shown(self) -> None:
        profiles = self._profiles()
        profiles.add()
        self.assertEqual(profiles.names, ["1", "2"])
        self.assertEqual(profiles.shown, "2")
        again = self._profiles()
        self.assertEqual(again.names, ["1", "2"])
        self.assertEqual(again.shown, "2")

    def test_delete_keeps_the_last_and_one_in_a_call(self) -> None:
        profiles = self._profiles()
        profiles.delete("1")
        self.assertEqual(profiles.names, ["1"])
        profiles.add()
        self.made["1"].set_state(
            replace(self.made["1"].state,
                    call=Call("ab" * 32, outgoing=False, video_call=False)))
        profiles.delete("1")
        self.assertEqual(profiles.names, ["1", "2"])
        self.made["1"].set_state(replace(self.made["1"].state, call=None))
        profiles.delete("1")
        self.assertEqual(profiles.names, ["2"])
        self.assertTrue(self.made["1"].deleted)

    def test_stay_connected_is_every_profiles(self) -> None:
        profiles = self._profiles()
        profiles.add()
        profiles.set_stay_connected(False)
        self.assertFalse(self.made["1"].state.settings.stay_connected)
        self.assertFalse(self.made["2"].state.settings.stay_connected)

    def test_shown_client_follows_the_shown_profile(self) -> None:
        profiles = self._profiles()
        profiles.add()
        profiles.show("1")
        shown = ShownClient(profiles)
        heard: list[str] = []
        shown.subscribe(lambda s: heard.append(s.profile.name),
                        emit_current=False)
        shown.set_visible(True)
        profiles.show("2")
        self.assertEqual(heard, ["profile 2"])
        self.assertEqual(shown.state.profile.name, "profile 2")
        self.assertFalse(self.made["1"].visible)
        self.assertTrue(self.made["2"].visible)


if __name__ == "__main__":
    unittest.main()
