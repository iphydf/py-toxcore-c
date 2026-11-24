# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""Tests for moving Tox between the app and the background service."""
from __future__ import annotations

import io
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Callable
from typing import IO
from typing import Optional

from pytox_client.client import ToxClient
from pytox_client.handover import HandoverClient
from pytox_client.model import PickedFile
from pytox_client.model import Settings
from pytox_client.platform_base import NoopPlatform
from pytox_client.service_ipc import SOCKET_NAME
from pytox_client.service_ipc import serve


class _CountedClient(ToxClient):
    """Counts the clients that have the profile open at once."""

    lock = threading.Lock()
    running = 0
    most = 0

    def start(self) -> None:
        with _CountedClient.lock:
            _CountedClient.running += 1
            _CountedClient.most = max(_CountedClient.most,
                                      _CountedClient.running)
        super().start()

    def close(self) -> None:
        super().close()
        with _CountedClient.lock:
            _CountedClient.running -= 1


class _ServicePlatform(NoopPlatform):
    """Runs the "service" on a thread, like Android runs it in a process."""

    def __init__(self, directory: Path) -> None:
        super().__init__()
        self._dir = directory
        self.thread: Optional[threading.Thread] = None
        self.stop = threading.Event()
        self.starts = 0

    def start_service(self) -> None:
        if self.thread is not None and self.thread.is_alive():
            return
        self.starts += 1
        self.stop = threading.Event()
        client = _CountedClient(self._dir, self, nodes=())
        self.thread = threading.Thread(
            target=serve, args=(client, self._dir / SOCKET_NAME, self.stop))
        self.thread.start()


def _until(ok: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 20.0
    while not ok():
        if time.monotonic() > deadline:
            raise TimeoutError("timed out")
        time.sleep(0.05)


class HandoverTest(unittest.TestCase):

    def setUp(self) -> None:
        _CountedClient.running = 0
        _CountedClient.most = 0
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.platform = _ServicePlatform(self.dir)
        first = [True]

        def make_local() -> ToxClient:
            settings = (Settings(ipv6=False, local_discovery=False,
                                 stay_connected=False) if first[0] else None)
            first[0] = False
            return _CountedClient(
                self.dir, self.platform, nodes=(), initial_settings=settings)

        self.client = HandoverClient(
            self.dir, self.platform, in_service=False, make_local=make_local)
        self.client.start()
        self.addCleanup(self._stop)

    def _stop(self) -> None:
        self.client.close()
        self.platform.stop.set()
        if self.platform.thread is not None:
            self.platform.thread.join(timeout=20.0)

    def _set_name(self, name: str) -> None:
        self.client.set_name(name)
        _until(lambda: self.client.state.profile.name == name)

    def _service_runs(self) -> bool:
        thread = self.platform.thread
        return thread is not None and thread.is_alive()

    def _stay_connected(self, on: bool) -> None:
        self.client.update_settings(
            replace(self.client.state.settings, stay_connected=on))

    def test_one_tox_at_a_time_both_ways(self) -> None:
        self.assertTrue(self.client.wait_ready(20.0))
        self._set_name("Alice")

        self._stay_connected(True)
        # Sent while switching: it reaches the service in the end.
        self._set_name("Bob")
        _until(self._service_runs)
        self._set_name("Carol")

        self._stay_connected(False)
        _until(lambda: not self._service_runs())
        self._set_name("Dave")
        self.assertFalse(self.client.state.settings.stay_connected)

        self.assertEqual(_CountedClient.most, 1)

    def test_service_starts_again_after_it_dies(self) -> None:
        self.assertTrue(self.client.wait_ready(20.0))
        self._stay_connected(True)
        _until(self._service_runs)
        self._set_name("Alice")

        self.platform.stop.set()
        _until(lambda: self.platform.starts == 2)
        self._set_name("Bob")

        self.assertEqual(self.platform.starts, 2)
        self.assertEqual(_CountedClient.most, 1)

    def test_send_file_survives_handover_during_copy(self) -> None:
        self.assertTrue(self.client.wait_ready(20.0))
        self._stay_connected(True)
        _until(self._service_runs)

        friend_key = "AA" * 32
        self.client.open_chat(friend_key)
        payload = b"hello across handover!"
        copy_started = threading.Event()
        allow_finish = threading.Event()

        def open_slow() -> IO[bytes]:
            copy_started.set()
            allow_finish.wait(timeout=10.0)
            return io.BytesIO(payload)

        sender = threading.Thread(
            target=self.client.send_file,
            args=(friend_key, PickedFile(name="report.bin",
                                         open_stream=open_slow)),
        )
        sender.start()
        self.assertTrue(copy_started.wait(timeout=10.0))

        # Hand back from the background service to local ToxClient while
        # send_file is still blocked reading the source stream.
        self._stay_connected(False)
        _until(lambda: not self._service_runs())
        _until(lambda: isinstance(self.client._backend, ToxClient))

        # Let the stream read finish and confirm the file lands on the new
        # local backend instead of being silently dropped.
        allow_finish.set()
        sender.join(timeout=10.0)
        _until(
            lambda: self.client.state.chat is not None
            and any(
                m.file is not None and m.file.name == "report.bin"
                and m.file.path.read_bytes() == payload
                for m in self.client.state.chat.messages
            )
        )
        staging = self.dir / "staging"
        if staging.exists():
            _until(lambda: not list(staging.iterdir()))

    def test_send_file_survives_service_death_during_copy(self) -> None:
        self.assertTrue(self.client.wait_ready(20.0))
        self._stay_connected(True)
        _until(self._service_runs)

        friend_key = "BB" * 32
        self.client.open_chat(friend_key)
        payload = b"hello after restart!"
        copy_started = threading.Event()
        allow_finish = threading.Event()

        def open_slow() -> IO[bytes]:
            copy_started.set()
            allow_finish.wait(timeout=10.0)
            return io.BytesIO(payload)

        sender = threading.Thread(
            target=self.client.send_file,
            args=(friend_key, PickedFile(name="retry.bin",
                                         open_stream=open_slow)),
        )
        sender.start()
        self.assertTrue(copy_started.wait(timeout=10.0))

        # Kill the running service mid-copy so it restarts and reconnects.
        old_thread = self.platform.thread
        self.platform.stop.set()
        if old_thread is not None:
            old_thread.join(timeout=10.0)
        allow_finish.set()
        sender.join(timeout=10.0)

        _until(
            lambda: self.platform.starts == 2
            and self.client.state.chat is not None
            and any(
                m.file is not None and m.file.name == "retry.bin"
                and m.file.path.read_bytes() == payload
                for m in self.client.state.chat.messages
            )
        )
        staging = self.dir / "staging"
        if staging.exists():
            _until(lambda: not list(staging.iterdir()))

    def test_local_client_recovers_after_lock_timeout(self) -> None:
        import fcntl
        import os

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        fd = os.open(root / ".lock", os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_open = True
        created = 0

        def make_local() -> ToxClient:
            nonlocal created
            created += 1
            return ToxClient(
                root,
                _ServicePlatform(root),
                nodes=(),
                initial_settings=Settings(
                    ipv6=False, local_discovery=False, stay_connected=False),
                lock_timeout=0.05,
            )

        hc = HandoverClient(
            root, _ServicePlatform(root), in_service=False,
            make_local=make_local)
        try:
            hc.start()
            # Wait until the first local client gives up on the lock and closes,
            # proving HandoverClient detects the death and spawns another try.
            _until(lambda: created >= 2)
            os.close(fd)
            lock_open = False
            self.assertTrue(hc.wait_ready(10.0))
            _until(lambda: bool(hc.state.profile.address))
            hc.set_name("Recovered")
            _until(lambda: hc.state.profile.name == "Recovered")
        finally:
            hc.close()
            if lock_open:
                os.close(fd)


if __name__ == "__main__":
    unittest.main()
