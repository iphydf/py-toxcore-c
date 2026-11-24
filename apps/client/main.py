#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""Entry point for PyTox (both desktop and Android / buildozer)."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any
from typing import Optional
from typing import Sequence

from pytox_client.platform_android import is_android


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pytox",
        description="PyTox — cross-platform Tox chat client.",
    )
    parser.add_argument(
        "--profile",
        type=Path,
        default=None,
        help="Profile directory (default: ~/.local/share/pytox on Linux).",
    )
    parser.add_argument(
        "--theme",
        choices=("system", "light", "dark"),
        default=None,
        help="Override the UI theme for this run.",
    )
    args, _unknown = parser.parse_known_args(argv)
    return args


def _configure_kivy(mobile: bool) -> None:
    # Stop Kivy from parsing our CLI flags like ``--profile``.
    os.environ.setdefault("KIVY_NO_ARGS", "1")
    from kivy.config import Config
    if not mobile:
        Config.set("graphics", "width", "1000")
        Config.set("graphics", "height", "700")
        Config.set("graphics", "resizable", "1")
        Config.set("input", "mouse", "mouse,multitouch_on_demand")
    Config.set("kivy", "exit_on_escape", "0")


def _use_emoji_fonts() -> None:
    """Roboto with emoji, if assets/fonts/make_fonts.py made it.

    Kivy draws text in one font, with no fallback: these take the place of
    its default one, so every label and text field has emoji.
    """
    fonts = Path(__file__).resolve().parent / "assets" / "fonts"
    styles = [
        fonts / f"PyToxSans-{style}.ttf"
        for style in ("Regular", "Italic", "Bold", "BoldItalic")
    ]
    if all(path.is_file() for path in styles):
        from kivy.core.text import DEFAULT_FONT
        from kivy.core.text import LabelBase
        LabelBase.register(DEFAULT_FONT, *map(str, styles))
        LabelBase.register("Roboto-Italic", str(styles[1]))


def _android_extra_from_intent(name: str) -> Optional[str]:
    try:
        from jnius import autoclass
        act = autoclass("org.kivy.android.PythonActivity").mActivity
        intent = act.getIntent()
        if intent is None:
            return None
        val = intent.getStringExtra(name)
        return str(val) if val else None
    except Exception:  # noqa: BLE001
        return None


# What a call's notification asks the app (CallNotices.java): answer, with
# video or not, or only show the call, which the app does by itself.
_CALL_EXTRA = "pytox_call"


def _call_from_notice(app: Any, what: Optional[str]) -> None:
    if what == "answer":
        app.answer_call(False)
    elif what == "answer_video":
        app.answer_call(True)


# How long the splash screen waits for the profile, so the UI doesn't start
# empty. A slow service only means the UI fills in a moment later.
_PROFILE_WAIT_S = 3.0


def main(argv: Optional[Sequence[str]] = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    args = _parse_args(raw_argv)
    mobile = is_android()
    _configure_kivy(mobile)
    _use_emoji_fonts()

    from pytox_client.client import ToxClient
    from pytox_client.platform_base import Platform
    from pytox_client.profiles import CallLine
    from pytox_client.profiles import Profiles
    from pytox_client.profiles import ShownClient
    from pytox_client.ui.app import PyToxApp

    platform: Platform
    initial_profile: Optional[str] = None
    initial_friend: Optional[str] = None
    initial_group: Optional[str] = None
    profiles: Profiles
    # The one call there can be, for the profiles running in this process.
    line = CallLine()

    mobile_platform: Any = None
    if mobile:
        from pytox_client.handover import HandoverClient
        from pytox_client.platform_android import AndroidPlatform
        from pytox_client.platform_android import dump_threads_on_signal
        from pytox_client.platform_android import request_notification_permission

        android_platform = AndroidPlatform()
        mobile_platform = android_platform
        platform = android_platform
        profile_dir = args.profile or platform.default_profile_dir()
        dump_threads_on_signal(profile_dir, "app")
        request_notification_permission()
        initial_profile = _android_extra_from_intent("profile")
        initial_friend = _android_extra_from_intent("friend")
        initial_group = _android_extra_from_intent("group")

        handovers: dict[str, HandoverClient] = {}

        def handover(directory: Path, name: str) -> HandoverClient:
            made = HandoverClient(
                directory, android_platform,
                in_service=android_platform.is_stay_connected_pref(),
                make_local=lambda: ToxClient(
                    directory, android_platform, profile=name,
                    call_line=line))
            handovers[name] = made
            return made

        profiles = Profiles(profile_dir, handover)
        profiles.start()
        for made in list(handovers.values()):
            made.wait_ready(_PROFILE_WAIT_S)

        def hang_up() -> None:
            caller = profiles.caller
            if caller is not None and caller in handovers:
                handovers[caller].hang_up()

        # A call's notification hangs up through this while the app runs.
        android_platform.listen_for_hang_up(hang_up)
    else:
        from pytox_client.platform_desktop import DesktopPlatform

        platform = DesktopPlatform()
        profile_dir = args.profile or platform.default_profile_dir()
        desktop = platform
        profiles = Profiles(
            profile_dir,
            lambda directory, name: ToxClient(
                directory, desktop, initial_theme=args.theme, profile=name,
                call_line=line))
        profiles.start()
    if initial_profile:
        profiles.show(initial_profile)
    client = ShownClient(profiles)

    try:
        icon_path = Path(__file__).resolve().parent / "assets" / "icon.png"
        app = PyToxApp(
            client=client,
            profiles=profiles,
            platform=platform,
            icon_path=icon_path,
            initial_friend=initial_friend,
            is_mobile=mobile,
            initial_group=initial_group,
        )

        if mobile and args.theme is not None:
            from dataclasses import replace
            client.update_settings(
                replace(client.state.settings, theme=args.theme))

        if mobile:
            _call_from_notice(app, _android_extra_from_intent(_CALL_EXTRA))
            try:
                from android import activity

                def _on_new_intent(intent: Any) -> None:
                    if not intent:
                        return
                    profile = intent.getStringExtra("profile")
                    friend = intent.getStringExtra("friend")
                    group = intent.getStringExtra("group")
                    call = intent.getStringExtra(_CALL_EXTRA)
                    if profile:
                        app.show_profile(str(profile))
                    if call:
                        _call_from_notice(app, str(call))
                    elif friend:
                        app.open_friend_chat(str(friend))
                    elif group:
                        app.open_group_chat(str(group))

                activity.bind(on_new_intent=_on_new_intent)
            except Exception:  # noqa: BLE001
                pass

        app.run()
    finally:
        if mobile_platform is not None:
            mobile_platform.listen_for_hang_up(None)
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
