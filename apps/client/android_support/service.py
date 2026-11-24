# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""Android python-for-android foreground service keeping Tox connected."""
from __future__ import annotations

import signal
import threading

from pytox_client.client import ToxClient
from pytox_client.platform_android import AndroidPlatform
from pytox_client.platform_android import dump_threads_on_signal
from pytox_client.platform_android import promote_service
from pytox_client.profiles import CallLine
from pytox_client.profiles import profile_dir
from pytox_client.profiles import profile_names
from pytox_client.service_ipc import SOCKET_NAME
from pytox_client.service_ipc import serve


# How often to look for new profiles, which the app adds.
_RESCAN_S = 1.0


def _keep_going() -> None:
    """Restart when Android stops the service, until the user says not to."""
    try:
        from jnius import autoclass
        service = autoclass("org.kivy.android.PythonService").mService
        service.setAutoRestartService(True)
    except Exception:  # noqa: BLE001
        pass


def _stop_restarting() -> None:
    """Let the service end for good: p4a starts it again otherwise."""
    try:
        from jnius import autoclass
        service = autoclass("org.kivy.android.PythonService").mService
        service.setAutoRestartService(False)
    except Exception:  # noqa: BLE001
        pass


def main() -> None:
    _keep_going()
    promote_service()
    platform = AndroidPlatform()
    root = platform.default_profile_dir()
    dump_threads_on_signal(root, "service")
    line = CallLine()
    stopping = threading.Event()
    # Each profile's stop, and the thread serving it.
    served: dict[str, tuple[threading.Event, threading.Thread]] = {}

    def _on_signal(_signum: int, _frame: object) -> None:
        stopping.set()
        for stop, _thread in served.values():
            stop.set()

    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGTERM, _on_signal)
        signal.signal(signal.SIGINT, _on_signal)

    try:
        while not stopping.is_set():
            wanted = platform.is_stay_connected_pref()
            for name in profile_names(root):
                running = served.get(name)
                if not wanted or (running is not None
                                  and running[1].is_alive()):
                    continue
                # New, or it stopped without being deleted: serve it again.
                directory = profile_dir(root, name)
                client = ToxClient(directory, platform, profile=name,
                                   call_line=line)
                stop = threading.Event()
                thread = threading.Thread(
                    target=serve, args=(client, directory / SOCKET_NAME, stop),
                    name=f"pytox-serve-{name}", daemon=True)
                served[name] = (stop, thread)
                thread.start()
            if not wanted and not any(
                    thread.is_alive() for _stop, thread in served.values()):
                break
            stopping.wait(_RESCAN_S)
    finally:
        for stop, thread in served.values():
            stop.set()
            thread.join()
        if not platform.is_stay_connected_pref():
            _stop_restarting()


if __name__ == "__main__":
    main()
