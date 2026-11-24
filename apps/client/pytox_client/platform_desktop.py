# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""Desktop (Linux / macOS / Windows) platform implementation."""
from __future__ import annotations

import html
import os
import shutil
import subprocess
import sys
import threading
import unicodedata
from io import BytesIO
from pathlib import Path
from typing import Callable
from typing import Optional

from pytox_client.media import Playout
from pytox_client.media import VideoFrame
from pytox_client.media_desktop import camera_paths
from pytox_client.media_desktop import DesktopSound
from pytox_client.media_desktop import Ringer
from pytox_client.media_desktop import V4l2Camera
from pytox_client.model import Call
from pytox_client.model import Friend
from pytox_client.model import FriendRequest
from pytox_client.model import Group
from pytox_client.model import GroupInvite
from pytox_client.model import GroupMessage
from pytox_client.model import Message
from pytox_client.model import PickedFile
from pytox_client.model import from_path
from pytox_client.model import shown_text
from pytox_client.platform_base import CallSound
from pytox_client.platform_base import Closeable
from pytox_client.platform_base import Platform


# Cap input pixel count before decoding an avatar image to block decompression bombs.
_MAX_AVATAR_INPUT_PIXELS = 40_000_000


def _sanitize_download_name(name: str) -> str:
    """Keep a download filename safe inside the target Downloads folder."""
    if "/" in name:
        name = name.rsplit("/", 1)[-1]
    if "\\" in name:
        name = name.rsplit("\\", 1)[-1]
    cleaned = "".join(
        ch for ch in name
        if unicodedata.category(ch) not in ("Cc", "Cf")
        and ch not in '<>:"|?*\x00'
    )
    cleaned = cleaned.strip().rstrip(". ").lstrip(".")
    return cleaned[:120] if cleaned else "file"


def encode_avatar_png(image: bytes, size: int) -> Optional[bytes]:
    """Center-crop and downscale ``image`` to a square PNG via Pillow."""
    try:
        from PIL import Image
        from PIL import ImageOps
    except ImportError:
        return None
    try:
        with Image.open(BytesIO(image)) as raw:
            rw, rh = raw.size
            if rw <= 0 or rh <= 0 or rw * rh > _MAX_AVATAR_INPUT_PIXELS:
                return None
            oriented = ImageOps.exif_transpose(raw)
            if oriented is None:
                return None
            img = oriented.convert("RGBA")
            w, h = img.size
            if w <= 0 or h <= 0:
                return None
            side = min(w, h)
            left = (w - side) // 2
            top = (h - side) // 2
            cropped = img.crop((left, top, left + side, top + side))
            out_side = min(side, size)
            if out_side < side:
                resample = getattr(Image, "Resampling", Image).LANCZOS
                cropped = cropped.resize((out_side, out_side), resample)
            buf = BytesIO()
            cropped.save(buf, format="PNG")
            return buf.getvalue()
    except (OSError, ValueError, SyntaxError, EOFError,
            Image.DecompressionBombError):
        return None


def unique_download_path(downloads: Path, name: str) -> Path:
    """Return a non-existing path inside ``downloads``, adding ``(N)`` if needed."""
    safe = _sanitize_download_name(name)
    candidate = downloads / safe
    if not candidate.exists() and not candidate.is_symlink():
        return candidate
    if "." in safe:
        stem, ext = safe.rsplit(".", 1)
        dot_ext = f".{ext}"
    else:
        stem, dot_ext = safe, ""
    index = 1
    while True:
        candidate = downloads / f"{stem} ({index}){dot_ext}"
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
        index += 1


class DesktopPlatform(Platform):
    """Platform integration for Linux, macOS, and Windows."""

    def __init__(
        self,
        fallback_picker: Optional[
            Callable[[bool, Callable[[PickedFile], None]], None]
        ] = None,
    ) -> None:
        self._fallback_picker = fallback_picker
        self._ringer = Ringer()
        self._ringing_for: Optional[str] = None
        # Cameras are counted once: desktops seldom gain one while running.
        self._cameras = len(camera_paths()) if sys.platform.startswith(
            "linux") else 0

    def open_sound(
        self,
        recorded: Callable[[bytes], None],
        playout: Playout,
    ) -> Optional[CallSound]:
        return DesktopSound.open(recorded, playout)

    @property
    def cameras(self) -> int:
        return self._cameras

    def open_camera(
        self,
        front: bool,
        frame: Callable[[VideoFrame], None],
    ) -> Optional[Closeable]:
        return V4l2Camera.open(front, frame)

    def call_changed(self, profile: str, call: Optional[Call],
                     friend: Optional[Friend]) -> None:
        incoming = call is not None and not call.outgoing and call.ringing
        self._ringer.ring(incoming)
        if incoming and call is not None and self._ringing_for != call.friend:
            name = friend.display_name if friend is not None else "Someone"
            what = "video call" if call.video_call else "call"
            self._desktop_notify(f"Incoming {what}", f"{name} is calling.")
        self._ringing_for = call.friend if incoming and call else None

    def set_fallback_picker(
        self,
        picker: Callable[[bool, Callable[[PickedFile], None]], None],
    ) -> None:
        self._fallback_picker = picker

    def default_profile_dir(self) -> Path:
        if sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / "PyTox"
        if sys.platform == "win32":
            appdata = os.environ.get("LOCALAPPDATA")
            if appdata:
                return Path(appdata) / "PyTox"
            return Path.home() / "AppData" / "Local" / "PyTox"
        xdg = os.environ.get("XDG_DATA_HOME", "").strip()
        base = Path(xdg) if xdg else Path.home() / ".local" / "share"
        return base / "pytox"

    def copy(self, text: str) -> None:
        try:
            from kivy.core.clipboard import Clipboard
            Clipboard.copy(text)
            return
        except Exception:  # noqa: BLE001
            pass
        for cmd in (
            ["wl-copy"],
            ["xclip", "-selection", "clipboard"],
            ["xsel", "--clipboard", "--input"],
            ["pbcopy"],
        ):
            if shutil.which(cmd[0]):
                try:
                    subprocess.run(
                        cmd, input=text.encode("utf-8"), check=False)
                    return
                except OSError:
                    pass

    def notify_message(self, profile: str, friend: Friend,
                       message: Message) -> None:
        self._desktop_notify(
            friend.display_name, message.preview(friend.hide_after_zero))

    def notify_request(self, profile: str, request: FriendRequest) -> None:
        body = request.message.strip() or request.key[:8]
        self._desktop_notify("Friend request", body)

    def notify_invite(self, profile: str, friend: Friend,
                      invite: GroupInvite) -> None:
        self._desktop_notify(
            f"Group invite from {friend.display_name}",
            invite.name or "A group")

    def notify_group_message(self, profile: str, group: Group,
                             message: GroupMessage) -> None:
        self._desktop_notify(
            group.display_name,
            f"{message.peer_name}: {shown_text(message.text, False)}")

    @staticmethod
    def _desktop_notify(title: str, body: str) -> None:
        # Strip embedded NUL bytes; pass untrusted strings as argv (never interpolated).
        clean_title = title.replace("\x00", "")
        clean_body = body.replace("\x00", "")

        def _send() -> None:
            if sys.platform.startswith("linux") and shutil.which("notify-send"):
                try:
                    # Escape Pango/HTML markup characters used by notification daemons.
                    escaped_body = html.escape(clean_body, quote=False)
                    subprocess.run(
                        ["notify-send", "-a", "PyTox", "--", clean_title,
                         escaped_body],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=5.0,
                        check=False,
                    )
                except (OSError, subprocess.SubprocessError):
                    pass
            elif sys.platform == "darwin" and shutil.which("osascript"):
                script = (
                    "on run argv\n"
                    "  display notification (item 2 of argv) with title (item 1 of argv)\n"
                    "end run"
                )
                try:
                    subprocess.run(
                        ["osascript", "-e", script, "--", clean_title,
                         clean_body],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=5.0,
                        check=False,
                    )
                except (OSError, subprocess.SubprocessError):
                    pass

        threading.Thread(target=_send, daemon=True).start()

    def pick_file(
        self,
        images: bool,
        on_picked: Callable[[PickedFile], None],
    ) -> None:
        def _native_linux() -> Optional[Path]:
            title = "Choose a picture" if images else "Send a file"
            if shutil.which("zenity"):
                cmd = ["zenity", "--file-selection", f"--title={title}"]
                if images:
                    cmd.append(
                        "--file-filter=Images | *.png *.jpg *.jpeg *.gif *.webp *.bmp"
                    )
                proc = subprocess.run(cmd, capture_output=True, text=True)
                out = proc.stdout.strip()
                if proc.returncode == 0 and out:
                    return Path(out)
                if proc.returncode in (0, 1):
                    return None
            if shutil.which("kdialog"):
                args = ["kdialog", "--getopenfilename", str(Path.home())]
                if images:
                    args.append("*.png *.jpg *.jpeg *.gif *.webp *.bmp|Images")
                proc = subprocess.run(args, capture_output=True, text=True)
                out = proc.stdout.strip()
                if proc.returncode == 0 and out:
                    return Path(out)
                return None
            return None

        if sys.platform.startswith("linux") and (shutil.which("zenity")
                                                 or shutil.which("kdialog")):
            def _worker() -> None:
                chosen = _native_linux()
                if chosen is not None and chosen.is_file():
                    on_picked(from_path(chosen))

            threading.Thread(target=_worker, daemon=True).start()
            return

        if sys.platform == "darwin" and shutil.which("osascript"):
            def _mac_worker() -> None:
                prompt = "Choose a picture" if images else "Send a file"
                script = (
                    f'POSIX path of (choose file with prompt "{prompt}")'
                )
                proc = subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True,
                    text=True,
                )
                out = proc.stdout.strip()
                if proc.returncode == 0 and out and Path(out).is_file():
                    on_picked(from_path(Path(out)))

            threading.Thread(target=_mac_worker, daemon=True).start()
            return

        if self._fallback_picker is not None:
            self._fallback_picker(images, on_picked)

    def open_file(self, path: Path, name: str) -> None:
        del name

        def _launch() -> None:
            try:
                resolved = path.resolve()
                if not resolved.is_file():
                    return
                if sys.platform.startswith("linux"):
                    proc = subprocess.Popen(
                        ["xdg-open", str(resolved)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    proc.wait()
                elif sys.platform == "darwin":
                    proc = subprocess.Popen(
                        ["open", "--", str(resolved)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    proc.wait()
                elif sys.platform == "win32":
                    startfile = getattr(os, "startfile", None)
                    if startfile is not None:
                        startfile(str(resolved))
            except OSError:
                pass

        threading.Thread(target=_launch, daemon=True).start()

    def save_to_downloads(self, path: Path, name: str) -> Optional[str]:
        downloads = Path.home() / "Downloads"
        try:
            downloads.mkdir(parents=True, exist_ok=True)
            target = unique_download_path(downloads, name)
            shutil.copy2(path, target)
            return f"Downloads as {target.name}"
        except OSError:
            return None

    def avatar_png(self, image: bytes, size: int) -> Optional[bytes]:
        return encode_avatar_png(image, size)

    def is_dark_mode(self) -> bool:
        if sys.platform.startswith("linux"):
            if shutil.which("gsettings"):
                try:
                    proc = subprocess.run(
                        [
                            "gsettings",
                            "get",
                            "org.gnome.desktop.interface",
                            "color-scheme",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=1.0,
                    )
                    if "dark" in proc.stdout.lower():
                        return True
                except (OSError, subprocess.SubprocessError):
                    pass
            gtk_theme = os.environ.get("GTK_THEME", "").lower()
            if "dark" in gtk_theme:
                return True
        elif sys.platform == "darwin":
            try:
                proc = subprocess.run(
                    ["defaults", "read", "-g", "AppleInterfaceStyle"],
                    capture_output=True,
                    text=True,
                    timeout=1.0,
                )
                return "dark" in proc.stdout.lower()
            except (OSError, subprocess.SubprocessError):
                pass
        return False
