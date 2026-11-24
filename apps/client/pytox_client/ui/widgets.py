# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""Reusable Material-3 styled Kivy widgets with vector canvas icons."""
from __future__ import annotations

import math
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Hashable
from typing import Optional
from typing import Sequence
from typing import Tuple

from kivy.graphics import Color
from kivy.graphics import Ellipse
from kivy.graphics import Line
from kivy.graphics import PopMatrix
from kivy.graphics import PushMatrix
from kivy.graphics import Rectangle
from kivy.graphics import RoundedRectangle
from kivy.graphics import Scale
from kivy.graphics import Translate
from kivy.graphics import Triangle
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Mesh
from kivy.graphics.tesselator import Tesselator
from kivy.graphics.tesselator import TYPE_POLYGONS
from kivy.graphics.tesselator import WINDING_NONZERO
from kivy.graphics.texture import Texture
from kivy.metrics import dp
from kivy.metrics import sp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

import pytox.toxcore.tox as core

from pytox_client.model import Picture
from pytox_client.qr import make_qr_matrix
from pytox_client.ui.formatting import avatar_rgba
from pytox_client.ui.formatting import group_rgba
from pytox_client.ui.theme import AWAY
from pytox_client.ui.theme import BUSY
from pytox_client.ui.theme import ONLINE
from pytox_client.ui.theme import RGBA
from pytox_client.ui.theme import ThemeColors
from pytox_client.ui.theme import with_alpha

_MAX_CACHE = 100
_MAX_IMAGE_PIXELS = 40_000_000


class _TextureCache:
    """Bounded LRU cache for decoded Pillow -> Kivy GL textures."""

    def __init__(self, limit: int = _MAX_CACHE) -> None:
        self._limit = limit
        self._items: OrderedDict[
            str, Optional[Tuple[Texture, int, int]]] = OrderedDict()

    def get_image(
        self,
        path: Path,
        version: str,
        max_px: int,
        circle: bool = False,
    ) -> Optional[Tuple[Texture, int, int]]:
        key = f"{path}|{version}|{max_px}|{int(circle)}"
        if key in self._items:
            self._items.move_to_end(key)
            return self._items[key]
        try:
            exists = path.exists()
        except OSError:
            return None
        if not exists:
            return None
        loaded = _load_texture(path, max_px, circle=circle)
        # Cache both successful textures and corrupt-image misses so scrolling
        # does not retry decoding broken files on every redraw.
        self._items[key] = loaded
        while len(self._items) > self._limit:
            self._items.popitem(last=False)
        return loaded


def _load_texture(
    path: Path,
    max_px: int,
    circle: bool = False,
) -> Optional[Tuple[Texture, int, int]]:
    try:
        from PIL import Image
        from PIL import ImageDraw
        from PIL import ImageOps
    except ImportError:
        return None
    try:
        with Image.open(path) as raw:
            rw, rh = raw.size
            if rw <= 0 or rh <= 0 or rw * rh > _MAX_IMAGE_PIXELS:
                return None
            oriented = ImageOps.exif_transpose(raw)
            if oriented is None:
                return None
            img = oriented.convert("RGBA")
            w, h = img.size
            if w <= 0 or h <= 0:
                return None
            if circle:
                side = min(w, h)
                left = (w - side) // 2
                top = (h - side) // 2
                img = img.crop((left, top, left + side, top + side))
                target = min(side, max_px)
                resample = getattr(Image, "Resampling", Image).LANCZOS
                if target != side:
                    img = img.resize((target, target), resample)
                # Anti-aliased supersampled circle mask so edges stay smooth.
                scale = 2
                mask = Image.new("L", (target * scale, target * scale), 0)
                draw = ImageDraw.Draw(mask)
                draw.ellipse(
                    (0, 0, target * scale - 1, target * scale - 1),
                    fill=255,
                )
                mask = mask.resize((target, target), resample)
                alpha = img.getchannel("A")
                out_alpha = Image.composite(alpha, Image.new("L", alpha.size, 0), mask)
                img.putalpha(out_alpha)
                w = h = target
            else:
                if max(w, h) > max_px:
                    scale_f = max_px / float(max(w, h))
                    w = max(1, int(round(w * scale_f)))
                    h = max(1, int(round(h * scale_f)))
                    resample = getattr(Image, "Resampling", Image).LANCZOS
                    img = img.resize((w, h), resample)
            tex = Texture.create(size=(w, h), colorfmt="rgba")
            tex.flip_vertical()
            tex.blit_buffer(img.tobytes(), colorfmt="rgba", bufferfmt="ubyte")
            return tex, w, h
    except (OSError, ValueError, SyntaxError, EOFError,
            Image.DecompressionBombError):
        return None


IMAGES = _TextureCache()


def set_bg_color(widget: Widget, rgba: RGBA, radius: float = 0.0) -> None:
    """Bind a solid or rounded-rect background drawn on ``canvas.before``."""
    existing_color = getattr(widget, "_bg_color_instr", None)
    existing_radius = getattr(widget, "_bg_radius", None)
    if (existing_color is not None and existing_radius == radius
            and existing_color in widget.canvas.before.children):
        existing_color.rgba = rgba
        return
    old_sync = getattr(widget, "_bg_sync_cb", None)
    if old_sync is not None:
        widget.unbind(pos=old_sync, size=old_sync)
    widget.canvas.before.clear()
    with widget.canvas.before:
        color_instr = Color(*rgba)
        if radius > 0:
            rect: Any = RoundedRectangle(
                pos=widget.pos, size=widget.size, radius=[radius])
        else:
            rect = Rectangle(pos=widget.pos, size=widget.size)

    def _sync(inst: Widget, *_args: Any) -> None:
        rect.pos = inst.pos
        rect.size = inst.size

    setattr(widget, "_bg_color_instr", color_instr)
    setattr(widget, "_bg_rect_instr", rect)
    setattr(widget, "_bg_radius", radius)
    setattr(widget, "_bg_sync_cb", _sync)
    widget.bind(pos=_sync, size=_sync)


class HairlineDivider(Widget):  # type: ignore[misc]
    """1-dp horizontal or vertical subtle divider line."""

    def __init__(
        self,
        color: RGBA,
        vertical: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._vertical = vertical
        self.size_hint = (None, 1) if vertical else (1, None)
        if vertical:
            self.width = dp(1)
        else:
            self.height = dp(1)
        with self.canvas:
            self._col = Color(*color)
            self._rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._sync, size=self._sync)

    def set_color(self, color: RGBA) -> None:
        self._col.rgba = color

    def _sync(self, *_args: Any) -> None:
        self._rect.pos = self.pos
        self._rect.size = self.size


class RoundedBox(BoxLayout):  # type: ignore[misc]
    """A BoxLayout with a rounded filled background and optional border."""

    def __init__(
        self,
        bg: RGBA,
        radius: Any = None,
        border_color: Optional[RGBA] = None,
        border_width: float = 1.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._bg = bg
        self._radius = radius if radius is not None else [dp(14)]
        self._border_color = border_color
        self._border_width = border_width
        self.bind(pos=self._redraw, size=self._redraw)
        self._redraw()

    def set_style(
        self,
        bg: RGBA,
        border_color: Optional[RGBA] = None,
    ) -> None:
        self._bg = bg
        self._border_color = border_color
        self._redraw()

    def _redraw(self, *_args: Any) -> None:
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*self._bg)
            RoundedRectangle(
                pos=self.pos, size=self.size, radius=self._radius)
            if self._border_color is not None:
                Color(*self._border_color)
                r = (self._radius[0]
                     if isinstance(self._radius, (list, tuple))
                     else float(self._radius))
                Line(
                    rounded_rectangle=(
                        self.x, self.y, self.width, self.height, r),
                    width=self._border_width,
                )


class ClickableBox(ButtonBehavior, RoundedBox):  # type: ignore[misc]
    """Pressable rounded container (for friend rows, header profile, etc.)."""

    def __init__(
        self,
        on_press_cb: Optional[Callable[[], None]] = None,
        bg: RGBA = (0, 0, 0, 0),
        pressed_bg: Optional[RGBA] = None,
        radius: Any = None,
        border_color: Optional[RGBA] = None,
        **kwargs: Any,
    ) -> None:
        self._base_bg = bg
        self._pressed_bg = pressed_bg
        super().__init__(bg=bg, radius=radius, border_color=border_color,
                         **kwargs)
        if on_press_cb is not None:
            self.bind(on_release=lambda *_: on_press_cb())

    def set_colors(
        self,
        bg: RGBA,
        pressed_bg: Optional[RGBA] = None,
        border_color: Optional[RGBA] = None,
    ) -> None:
        self._base_bg = bg
        self._pressed_bg = pressed_bg
        self.set_style(bg, border_color)

    def on_state(self, _inst: Any, value: str) -> None:
        if value == "down" and self._pressed_bg is not None:
            self.set_style(self._pressed_bg, self._border_color)
        else:
            self.set_style(self._base_bg, self._border_color)


class PillButton(ButtonBehavior, BoxLayout):  # type: ignore[misc]
    """Crisp Material-3-style button (filled, tonal, outlined, or text)."""

    def __init__(
        self,
        text: str,
        bg: RGBA,
        fg: RGBA,
        border: Optional[RGBA] = None,
        on_click: Optional[Callable[[], None]] = None,
        height_dp: float = 38.0,
        min_width_dp: float = 0.0,
        pad_x_dp: float = 18.0,
        font_size_sp: float = 13.5,
        bold: bool = True,
        radius_dp: Optional[float] = None,
        disabled: bool = False,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("size_hint", (None, None))
        super().__init__(**kwargs)
        self._bg = bg
        self._fg = fg
        self._border = border
        self._radius_dp = radius_dp
        self._pad_x = dp(pad_x_dp)
        self._min_w = dp(min_width_dp)
        self.height = dp(height_dp)
        self.disabled = disabled
        self.padding = (self._pad_x, 0, self._pad_x, 0)
        self._label = Label(
            text=text,
            color=fg,
            font_size=sp(font_size_sp),
            bold=bold,
            halign="center",
            valign="middle",
        )
        self._label.bind(texture_size=self._sync_width)
        self.add_widget(self._label)
        self.bind(pos=self._redraw, size=self._redraw,
                  state=self._redraw, disabled=self._redraw)
        if on_click is not None:
            self.bind(on_release=lambda *_: on_click())
        self._label.texture_update()
        self._sync_width()
        self._redraw()

    def set_text(self, text: str) -> None:
        self._label.text = text
        self._label.texture_update()
        self._sync_width()

    def _sync_width(self, *_args: Any) -> None:
        if self.size_hint_x is None:
            self.width = max(self._min_w,
                             self._label.texture_size[0] + self._pad_x * 2)

    def _redraw(self, *_args: Any) -> None:
        self.canvas.before.clear()
        is_down = self.state == "down" and not self.disabled
        alpha_mul = 0.45 if self.disabled else (0.82 if is_down else 1.0)
        bg = with_alpha(self._bg, self._bg[3] * alpha_mul)
        fg_mul = (0.78 if self._bg[3] > 0 else 0.45) if self.disabled else 1.0
        fg = with_alpha(self._fg, self._fg[3] * fg_mul)
        self._label.color = fg
        rad = dp(self._radius_dp) if self._radius_dp is not None else self.height / 2.0
        with self.canvas.before:
            if bg[3] > 0:
                Color(*bg)
                RoundedRectangle(pos=self.pos, size=self.size, radius=[rad])
            elif is_down:
                Color(*with_alpha(self._fg, 0.12))
                RoundedRectangle(pos=self.pos, size=self.size, radius=[rad])
            if self._border is not None:
                b_alpha = self._border[3] * (0.4 if self.disabled else 1.0)
                Color(*with_alpha(self._border, b_alpha))
                Line(
                    rounded_rectangle=(
                        self.x, self.y, self.width, self.height, rad),
                    width=dp(1),
                )


class VectorIcon(Widget):  # type: ignore[misc]
    """Crisp vector icon drawn with Kivy canvas primitives (no emoji font deps)."""

    def __init__(
        self,
        kind: str,
        color: RGBA,
        size_dp: float = 20.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(size_hint=(None, None),
                         size=(dp(size_dp), dp(size_dp)), **kwargs)
        self._kind = kind
        self._color = color
        self.bind(pos=self._redraw, size=self._redraw)
        self._redraw()

    def set_color(self, color: RGBA) -> None:
        self._color = color
        self._redraw()

    def _redraw(self, *_args: Any) -> None:
        self.canvas.clear()
        cx, cy = self.center_x, self.center_y
        r = min(self.width, self.height) * 0.36
        sw = max(1.4, min(self.width, self.height) * 0.085)
        with self.canvas:
            Color(*self._color)
            if self._kind == "add":
                Line(points=[cx - r, cy, cx + r, cy], width=sw, cap="round")
                Line(points=[cx, cy - r, cx, cy + r], width=sw, cap="round")
            elif self._kind == "menu":
                for dy in (r * 0.7, 0.0, -r * 0.7):
                    Line(points=[cx - r, cy + dy, cx + r, cy + dy],
                         width=sw, cap="round")
            elif self._kind == "back":
                Line(
                    points=[cx + r * 0.2, cy + r * 0.78,
                            cx - r * 0.65, cy,
                            cx + r * 0.2, cy - r * 0.78],
                    width=sw,
                    cap="round",
                    joint="round",
                )
                Line(
                    points=[cx - r * 0.55, cy, cx + r * 0.85, cy],
                    width=sw,
                    cap="round",
                )
            elif self._kind == "settings":
                # Clean sliders icon (3 horizontal tracks with knob circles).
                for dy, kx in ((r * 0.65, -0.25), (0.0, 0.35), (-r * 0.65, -0.15)):
                    y = cy + dy
                    Line(points=[cx - r * 0.9, y, cx + r * 0.9, y],
                         width=sw * 0.85, cap="round")
                    kr = r * 0.25
                    Ellipse(pos=(cx + kx * r - kr, y - kr),
                            size=(kr * 2, kr * 2))
            elif self._kind == "info":
                Line(circle=(cx, cy, r * 1.05), width=sw * 0.85)
                Line(points=[cx, cy - r * 0.48, cx, cy + r * 0.02],
                     width=sw * 0.95, cap="round")
                dot_r = sw * 0.65
                Ellipse(pos=(cx - dot_r, cy + r * 0.42 - dot_r),
                        size=(dot_r * 2, dot_r * 2))
            elif self._kind == "send":
                Triangle(points=[
                    cx - r * 0.65, cy + r * 0.72,
                    cx + r * 0.85, cy,
                    cx - r * 0.65, cy - r * 0.72,
                ])
            elif self._kind == "check":
                Line(
                    points=[
                        cx - r * 0.75, cy - r * 0.05,
                        cx - r * 0.2, cy - r * 0.6,
                        cx + r * 0.85, cy + r * 0.55,
                    ],
                    width=sw * 1.05,
                    cap="round",
                    joint="round",
                )
            elif self._kind == "attach":
                Line(points=[cx - r * 0.65, cy, cx + r * 0.65, cy],
                     width=sw, cap="round")
                Line(points=[cx, cy - r * 0.65, cx, cy + r * 0.65],
                     width=sw, cap="round")
            elif self._kind == "sun":
                Line(circle=(cx, cy, r * 0.45), width=sw)
                for k in range(8):
                    ang = k * math.pi / 4.0
                    Line(points=[
                        cx + math.cos(ang) * r * 0.68,
                        cy + math.sin(ang) * r * 0.68,
                        cx + math.cos(ang) * r * 0.95,
                        cy + math.sin(ang) * r * 0.95,
                    ], width=sw * 0.75, cap="round")


# Material icons for calls, in 24 × 24 (Apache 2.0, from Google's Material
# Icons, as kTox has them).
ICON_PATHS: dict[str, str] = {
    "call": (
        "M20.01 15.38c-1.23 0-2.42-.2-3.53-.56-.35-.12-.74-.03-1.01.24l-1.57 "
        "1.97c-2.83-1.35-5.48-3.9-6.89-6.83l1.95-1.66c.27-.28.35-.67.24-1.02"
        "-.37-1.11-.56-2.3-.56-3.53 0-.54-.45-.99-.99-.99H4.19C3.65 3 3 3.24 3"
        " 3.99 3 13.28 10.73 21 20.01 21c.71 0 .99-.63.99-1.18v-3.45c0-.54-.45"
        "-.99-.99-.99z"),
    "videocam": (
        "M17 10.5V7c0-.55-.45-1-1-1H4c-.55 0-1 .45-1 1v10c0 .55.45 1 1 1h12c"
        ".55 0 1-.45 1-1v-3.5l4 4v-11l-4 4z"),
    "videocam_off": (
        "M21 6.5l-4 4V7c0-.55-.45-1-1-1H9.82L21 17.18V6.5zM3.27 2L2 3.27 4.73"
        " 6H4c-.55 0-1 .45-1 1v10c0 .55.45 1 1 1h12c.21 0 .39-.08.54-.18L19.73"
        " 21 21 19.73 3.27 2z"),
    "mic": (
        "M12 14c1.66 0 2.99-1.34 2.99-3L15 5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0"
        " 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 "
        "2.72 6.23 6 6.72V21h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z"),
    "mic_off": (
        "M19 11h-1.7c0 .74-.16 1.43-.43 2.05l1.23 1.23c.56-.98.9-2.09.9-3.28z"
        "m-4.02.17c0-.06.02-.11.02-.17V5c0-1.66-1.34-3-3-3S9 3.34 9 5v.18l5.98"
        " 5.99zM4.27 3L3 4.27l6.01 6.01V11c0 1.66 1.33 3 2.99 3 .22 0 .44-.03"
        ".65-.08l1.66 1.66c-.71.33-1.5.52-2.31.52-2.76 0-5.3-2.1-5.3-5.1H5c0 "
        "3.41 2.72 6.23 6 6.72V21h2v-3.28c.91-.13 1.77-.45 2.54-.9L19.73 21 21"
        " 19.73 4.27 3z"),
    "call_end": (
        "M12 9c-1.6 0-3.15.25-4.6.72v3.1c0 .39-.23.74-.56.9-.98.49-1.87 1.12"
        "-2.66 1.85-.18.18-.43.28-.7.28-.28 0-.53-.11-.71-.29L.29 13.08c-.18"
        "-.17-.29-.42-.29-.7 0-.28.11-.53.29-.71C3.34 8.78 7.46 7 12 7s8.66 "
        "1.78 11.71 4.67c.18.18.29.43.29.71 0 .28-.11.53-.29.71l-2.48 2.48c"
        "-.18.18-.43.29-.71.29-.27 0-.52-.11-.7-.28-.79-.74-1.69-1.36-2.67"
        "-1.85-.33-.16-.56-.5-.56-.9v-3.1C15.15 9.25 13.6 9 12 9z"),
    "volume_up": (
        "M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73"
        " 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 "
        "6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"),
    # A camera between two turning arrows.
    "switch_camera": (
        "M20 4h-3.17L15 2H9L7.17 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 "
        "0 2-.9 2-2V6c0-1.1-.9-2-2-2zm-5 11.5V13H9v2.5L5.5 12 9 8.5V11h6V8.5l"
        "3.5 3.5-3.5 3.5z"),
}


_PATH_TOKEN = re.compile(r"[A-Za-z]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_PATH_ARGS = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Z": 0}


# Straight pieces each curve of an icon becomes.
_CURVE_STEPS = 8


def path_outlines(path: str) -> list[list[float]]:
    """An SVG path's outlines, as flat x, y lists with y going up.

    Curves become short straight lines. Paths in M, L, H, V, C, S and Z, as
    Material icons have them.
    """
    tokens = _PATH_TOKEN.findall(path)
    outlines: list[list[float]] = []
    out: list[float] = []
    x = y = start_x = start_y = 0.0
    # The last curve's second control point, for a smooth one after it.
    ctrl: Optional[tuple[float, float]] = None
    i = 0
    cmd = ""
    while i < len(tokens):
        if tokens[i].isalpha():
            cmd = tokens[i]
            i += 1
        upper = cmd.upper()
        if upper not in _PATH_ARGS:
            raise ValueError(f"unsupported path command {cmd}")
        n = _PATH_ARGS[upper]
        args = [float(t) for t in tokens[i:i + n]]
        i += n
        rel = cmd.islower()
        if upper == "Z":
            x, y = start_x, start_y
            ctrl = None
            continue
        if upper in ("M", "L"):
            nx, ny = (x + args[0], y + args[1]) if rel else (args[0], args[1])
            if upper == "M":
                if len(out) > 4:
                    outlines.append(out)
                out = []
                start_x, start_y = nx, ny
                # More coordinates after a move are lines.
                cmd = "l" if rel else "L"
            x, y = nx, ny
            out += [x, 24 - y]
            ctrl = None
        elif upper in ("H", "V"):
            if upper == "H":
                x = x + args[0] if rel else args[0]
            else:
                y = y + args[0] if rel else args[0]
            out += [x, 24 - y]
            ctrl = None
        else:
            if upper == "S":
                c1 = (2 * x - ctrl[0], 2 * y - ctrl[1]) if ctrl else (x, y)
                rest = args
            else:
                c1 = (x + args[0], y + args[1]) if rel else (args[0], args[1])
                rest = args[2:]
            pts = [(x + rest[k], y + rest[k + 1]) if rel else
                   (rest[k], rest[k + 1]) for k in (0, 2)]
            (x2, y2), (x3, y3) = pts
            for k in range(1, _CURVE_STEPS + 1):
                t = k / _CURVE_STEPS
                u = 1 - t
                px = (u**3 * x + 3 * u * u * t * c1[0] + 3 * u * t * t * x2 +
                      t**3 * x3)
                py = (u**3 * y + 3 * u * u * t * c1[1] + 3 * u * t * t * y2 +
                      t**3 * y3)
                out += [px, 24 - py]
            ctrl = pts[0]
            x, y = x3, y3
    if len(out) > 4:
        outlines.append(out)
    return outlines


def _icon_meshes(kind: str) -> list[tuple[list[float], list[int]]]:
    """An icon as triangle fans in 24 × 24, filled as SVG fills: nonzero."""
    meshes = _MESHES.get(kind)
    if meshes is None:
        tess = Tesselator()
        for outline in path_outlines(ICON_PATHS[kind]):
            tess.add_contour(outline)
        tess.tesselate(WINDING_NONZERO, TYPE_POLYGONS)
        meshes = [(list(vertices), list(range(len(vertices) // 4)))
                  for vertices, _ in tess.meshes]
        _MESHES[kind] = meshes
    return meshes


_MESHES: dict[str, list[tuple[list[float], list[int]]]] = {}


class PathIcon(Widget):  # type: ignore[misc]
    """One of :data:`ICON_PATHS`, drawn from its path at any size."""

    def __init__(
        self,
        kind: str,
        color: RGBA,
        size_dp: float = 20.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(size_hint=(None, None),
                         size=(dp(size_dp), dp(size_dp)), **kwargs)
        self._kind = kind
        self._color = color
        self.bind(pos=self._redraw, size=self._redraw)
        self._redraw()

    def set_color(self, color: RGBA) -> None:
        if color != self._color:
            self._color = color
            self._redraw()

    def _redraw(self, *_args: Any) -> None:
        side = min(self.width, self.height)
        self.canvas.clear()
        with self.canvas:
            Color(*self._color)
            PushMatrix()
            Translate(self.center_x - side / 2, self.center_y - side / 2)
            Scale(side / 24, side / 24, 1)
            for vertices, indices in _icon_meshes(self._kind):
                Mesh(vertices=vertices, indices=indices, mode="triangle_fan")
            PopMatrix()


class IconButton(ButtonBehavior, BoxLayout):  # type: ignore[misc]
    """Circular icon button with subtle pressed feedback."""

    def __init__(
        self,
        kind: str,
        fg: RGBA,
        bg: Optional[RGBA] = None,
        size_dp: float = 40.0,
        icon_dp: float = 20.0,
        on_click: Optional[Callable[[], None]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            size_hint=(None, None),
            size=(dp(size_dp), dp(size_dp)),
            **kwargs,
        )
        self._fg = fg
        self._bg = bg
        self._icon: VectorIcon | PathIcon = (
            PathIcon(kind, fg, size_dp=icon_dp)
            if kind in ICON_PATHS else VectorIcon(kind, fg, size_dp=icon_dp))
        pad = (dp(size_dp) - dp(icon_dp)) / 2.0
        self.padding = (pad, pad, pad, pad)
        self.add_widget(self._icon)
        self.bind(pos=self._redraw, size=self._redraw,
                  state=self._redraw, disabled=self._redraw)
        if on_click is not None:
            self.bind(on_release=lambda *_: on_click())
        self._redraw()

    def set_colors(self, fg: RGBA, bg: Optional[RGBA] = None) -> None:
        self._fg = fg
        self._bg = bg
        self._redraw()

    def _redraw(self, *_args: Any) -> None:
        self.canvas.before.clear()
        if self.disabled:
            fg = with_alpha(self._fg, 0.35)
            bg = (with_alpha(self._bg, self._bg[3] * 0.35)
                  if self._bg is not None else None)
        else:
            fg = self._fg
            bg = self._bg
        self._icon.set_color(fg)
        with self.canvas.before:
            if bg is not None and bg[3] > 0:
                Color(*with_alpha(bg, bg[3] * (0.8 if self.state == "down" else 1.0)))
                Ellipse(pos=self.pos, size=self.size)
            elif self.state == "down" and not self.disabled:
                Color(*with_alpha(self._fg, 0.14))
                Ellipse(pos=self.pos, size=self.size)


class AvatarWidget(Widget):  # type: ignore[misc]
    """Circular avatar picture (or deterministic colored initial) + presence dot."""

    def __init__(
        self,
        key_hex: str,
        name: str,
        theme: ThemeColors,
        size_dp: float = 44.0,
        connection: Optional[core.Connection] = None,
        status: core.UserStatus = core.UserStatus.NONE,
        picture: Optional[Picture] = None,
        ring_color: Optional[RGBA] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            size_hint=(None, None),
            size=(dp(size_dp), dp(size_dp)),
            **kwargs,
        )
        self._size_dp = size_dp
        self._key_hex = key_hex
        self._name = name
        self._theme = theme
        self._connection = connection
        self._status = status
        self._picture = picture
        self._ring_color = ring_color
        self._letter_label = Label(
            text="",
            color=(1, 1, 1, 1),
            bold=True,
            halign="center",
            valign="middle",
        )
        self.add_widget(self._letter_label)
        self.bind(pos=self._redraw, size=self._redraw)
        self._redraw()

    def update(
        self,
        key_hex: str,
        name: str,
        theme: ThemeColors,
        connection: Optional[core.Connection] = None,
        status: core.UserStatus = core.UserStatus.NONE,
        picture: Optional[Picture] = None,
        ring_color: Optional[RGBA] = None,
    ) -> None:
        self._key_hex = key_hex
        self._name = name
        self._theme = theme
        self._connection = connection
        self._status = status
        self._picture = picture
        self._ring_color = ring_color
        self._redraw()

    def _redraw(self, *_args: Any) -> None:
        self.canvas.before.clear()
        self.canvas.after.clear()
        d = min(self.width, self.height)
        x = self.center_x - d / 2.0
        y = self.center_y - d / 2.0
        tex_entry = None
        if self._picture is not None:
            tex_entry = IMAGES.get_image(
                self._picture.path, self._picture.hash, 256, circle=True)
        with self.canvas.before:
            if tex_entry is not None:
                Color(1, 1, 1, 1)
                Rectangle(pos=(x, y), size=(d, d), texture=tex_entry[0])
                self._letter_label.text = ""
            else:
                Color(*avatar_rgba(self._key_hex))
                Ellipse(pos=(x, y), size=(d, d))
                letter = self._name[0].upper() if self._name else "?"
                self._letter_label.text = letter
                self._letter_label.font_size = max(sp(11), d * 0.42)
                self._letter_label.size = (d, d)
                self._letter_label.pos = (x, y)

        if self._connection is not None:
            dot_d = max(dp(9), d * 0.30)
            border = max(dp(1.8), dot_d * 0.16)
            ring = (self._ring_color
                    if self._ring_color is not None else self._theme.surface)
            if self._connection == core.Connection.NONE:
                dot_col = self._theme.outline
            elif self._status == core.UserStatus.AWAY:
                dot_col = AWAY
            elif self._status == core.UserStatus.BUSY:
                dot_col = BUSY
            else:
                dot_col = ONLINE
            dx = x + d - dot_d
            dy = y
            with self.canvas.after:
                Color(*ring)
                Ellipse(
                    pos=(dx - border, dy - border),
                    size=(dot_d + border * 2, dot_d + border * 2),
                )
                Color(*dot_col)
                Ellipse(pos=(dx, dy), size=(dot_d, dot_d))


class GroupAvatarWidget(Widget):  # type: ignore[misc]
    """A group's first letter on a rounded square, so groups look apart."""

    def __init__(
        self,
        group_id: str,
        name: str,
        size_dp: float = 44.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            size_hint=(None, None),
            size=(dp(size_dp), dp(size_dp)),
            **kwargs,
        )
        self._group_id = group_id
        self._name = name
        self._label = Label(
            text="", color=(1, 1, 1, 1), bold=True,
            halign="center", valign="middle")
        self.add_widget(self._label)
        self.bind(pos=self._redraw, size=self._redraw)
        self._redraw()

    def update(self, group_id: str, name: str) -> None:
        self._group_id = group_id
        self._name = name
        self._redraw()

    def _redraw(self, *_args: Any) -> None:
        self.canvas.before.clear()
        d = min(self.width, self.height)
        x = self.center_x - d / 2.0
        y = self.center_y - d / 2.0
        with self.canvas.before:
            Color(*group_rgba(self._group_id))
            RoundedRectangle(pos=(x, y), size=(d, d), radius=[d * 0.3])
        self._label.text = self._name[0].upper() if self._name else "#"
        self._label.font_size = max(sp(11), d * 0.42)
        self._label.size = (d, d)
        self._label.pos = (x, y)


class ToggleSwitch(ButtonBehavior, Widget):  # type: ignore[misc]
    """Material-3 pill toggle switch drawn with Kivy canvas primitives."""

    def __init__(
        self,
        checked: bool,
        theme: ThemeColors,
        on_toggle: Callable[[bool], None],
        **kwargs: Any,
    ) -> None:
        super().__init__(
            size_hint=(None, None),
            size=(dp(48), dp(28)),
            **kwargs,
        )
        self._checked = checked
        self._theme = theme
        self._on_toggle = on_toggle
        self.bind(pos=self._redraw, size=self._redraw)
        self.bind(on_release=self._handle_press)
        self._redraw()

    def _handle_press(self, *_args: Any) -> None:
        self._checked = not self._checked
        self._redraw()
        self._on_toggle(self._checked)

    def set_checked(self, checked: bool, theme: ThemeColors) -> None:
        self._checked = checked
        self._theme = theme
        self._redraw()

    def _redraw(self, *_args: Any) -> None:
        self.canvas.clear()
        w, h = self.size
        rad = h / 2.0
        with self.canvas:
            if self._checked:
                Color(*self._theme.primary)
                RoundedRectangle(pos=self.pos, size=self.size, radius=[rad])
                knob = h * 0.72
                pad = (h - knob) / 2.0
                Color(*self._theme.on_primary)
                Ellipse(pos=(self.right - knob - pad, self.y + pad),
                        size=(knob, knob))
            else:
                Color(*self._theme.surface_container_highest)
                RoundedRectangle(pos=self.pos, size=self.size, radius=[rad])
                Color(*self._theme.outline)
                Line(
                    rounded_rectangle=(self.x, self.y, w, h, rad),
                    width=dp(1.4),
                )
                knob = h * 0.56
                pad = (h - knob) / 2.0
                Color(*self._theme.outline)
                Ellipse(pos=(self.x + pad + dp(1), self.y + pad),
                        size=(knob, knob))


class SegmentedRow(BoxLayout):  # type: ignore[misc]
    """Single-choice segmented button strip (e.g. Online / Away / Busy)."""

    def __init__(
        self,
        options: Sequence[Tuple[Any, str]],
        selected: Any,
        theme: ThemeColors,
        on_select: Callable[[Any], None],
        **kwargs: Any,
    ) -> None:
        super().__init__(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(38),
            spacing=dp(6),
            **kwargs,
        )
        self._options = list(options)
        self._selected = selected
        self._theme = theme
        self._on_select = on_select
        self._rebuild()

    def set_selected(self, selected: Any, theme: ThemeColors) -> None:
        self._selected = selected
        self._theme = theme
        self._rebuild()

    def _rebuild(self) -> None:
        self.clear_widgets()
        for value, label in self._options:
            is_sel = value == self._selected
            bg = (self._theme.secondary_container
                  if is_sel else (0, 0, 0, 0))
            fg = (self._theme.on_secondary_container
                  if is_sel else self._theme.on_surface_variant)
            border = (None if is_sel else self._theme.outline_variant)
            def _make_select(val: Any) -> Callable[[], None]:
                return lambda: self._on_select(val)

            btn = PillButton(
                text=label,
                bg=bg,
                fg=fg,
                border=border,
                size_hint=(1, 1),
                height_dp=38,
                pad_x_dp=8,
                font_size_sp=13,
                bold=is_sel,
                radius_dp=10,
                on_click=_make_select(value),
            )
            self.add_widget(btn)


class StyledTextInput(RoundedBox):
    """Single or multi-line outlined field matching Material-3 look."""

    def __init__(
        self,
        theme: ThemeColors,
        hint: str = "",
        text: str = "",
        multiline: bool = False,
        font_name: Optional[str] = None,
        radius_dp: float = 12.0,
        font_size_sp: float = 14.5,
        height_dp: float = 44.0,
        input_type: str = "text",
        suggestions: bool = True,
        **kwargs: Any,
    ) -> None:
        self._theme = theme
        super().__init__(
            bg=theme.surface_container_lowest,
            radius=[dp(radius_dp)],
            border_color=theme.outline_variant,
            border_width=dp(1.2),
            size_hint=(1, None),
            height=dp(height_dp),
            padding=(dp(12), dp(8), dp(12), dp(8)),
            **kwargs,
        )
        self.field = TextInput(
            text=text,
            hint_text=hint,
            multiline=multiline,
            background_normal="",
            background_active="",
            background_color=(0, 0, 0, 0),
            foreground_color=theme.on_surface,
            hint_text_color=theme.on_surface_variant,
            cursor_color=theme.primary,
            selection_color=with_alpha(theme.primary, 0.28),
            font_size=sp(font_size_sp),
            padding=(0, dp(4), 0, dp(4)),
            write_tab=False,
            # Kivy's default, "null", gives Android's raw-key keyboard:
            # no gesture typing, suggestions or autocorrect.
            input_type=input_type,
            keyboard_suggestions=suggestions,
        )
        if font_name:
            self.field.font_name = font_name
        self.field.bind(focus=self._on_focus)
        self.add_widget(self.field)

    def _on_focus(self, _inst: Any, focused: bool) -> None:
        border = (self._theme.primary
                  if focused else self._theme.outline_variant)
        self._border_width = dp(1.8 if focused else 1.2)
        self.set_style(self._theme.surface_container_lowest, border)

    def set_theme(self, theme: ThemeColors, error: bool = False) -> None:
        self._theme = theme
        border = (theme.error if error else
                  (theme.primary if self.field.focus
                   else theme.outline_variant))
        self.set_style(theme.surface_container_lowest, border)
        self.field.foreground_color = theme.on_surface
        self.field.hint_text_color = theme.on_surface_variant
        self.field.cursor_color = theme.primary
        self.field.selection_color = with_alpha(theme.primary, 0.28)


class ProgressBarView(Widget):  # type: ignore[misc]
    """Linear rounded progress bar."""

    def __init__(
        self,
        fg: RGBA,
        track: RGBA,
        fraction: float = 0.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(size_hint=(1, None), height=dp(5), **kwargs)
        self._fg = fg
        self._track = track
        self._fraction = max(0.0, min(1.0, fraction))
        self.bind(pos=self._redraw, size=self._redraw)
        self._redraw()

    def set_progress(self, fraction: float) -> None:
        self._fraction = max(0.0, min(1.0, fraction))
        self._redraw()

    def _redraw(self, *_args: Any) -> None:
        self.canvas.clear()
        rad = self.height / 2.0
        with self.canvas:
            Color(*self._track)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[rad])
            fw = self.width * self._fraction
            if fw > 0:
                Color(*self._fg)
                RoundedRectangle(
                    pos=self.pos, size=(max(self.height, fw), self.height),
                    radius=[rad],
                )


class QrCodeWidget(Widget):  # type: ignore[misc]
    """Black-on-white crisp QR code drawn directly onto the Kivy canvas."""

    def __init__(
        self,
        text: str,
        size_dp: float = 200.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            size_hint=(None, None),
            size=(dp(size_dp), dp(size_dp)),
            **kwargs,
        )
        self._matrix: Optional[list[list[bool]]] = None
        self._text = ""
        self.bind(pos=self._redraw, size=self._redraw)
        self.set_text(text)

    def set_text(self, text: str) -> None:
        if text == self._text:
            return
        self._text = text
        self._matrix = make_qr_matrix(text) if text else None
        self._redraw()

    def _redraw(self, *_args: Any) -> None:
        self.canvas.clear()
        side = min(self.width, self.height)
        ox = self.center_x - side / 2.0
        oy = self.center_y - side / 2.0
        with self.canvas:
            Color(1, 1, 1, 1)
            RoundedRectangle(pos=(ox, oy), size=(side, side), radius=[dp(10)])
            if self._matrix:
                n = len(self._matrix)
                cell = side / float(n)
                Color(0.05, 0.07, 0.09, 1)
                for r, row in enumerate(self._matrix):
                    # Flip vertically: Kivy y=0 is at the bottom.
                    py = oy + (n - 1 - r) * cell
                    for c, dark in enumerate(row):
                        if dark:
                            px = ox + c * cell
                            Rectangle(pos=(px, py), size=(cell + 0.3, cell + 0.3))


class TopBar(BoxLayout):  # type: ignore[misc]
    """56dp top app bar with hairline bottom divider."""

    def __init__(
        self,
        theme: ThemeColors,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            orientation="vertical",
            size_hint=(1, None),
            height=dp(60),
            **kwargs,
        )
        self.row = BoxLayout(
            orientation="horizontal",
            padding=(dp(8), dp(6), dp(8), dp(6)),
            spacing=dp(6),
        )
        self.divider = HairlineDivider(theme.outline_variant)
        self.add_widget(self.row)
        self.add_widget(self.divider)
        set_bg_color(self, theme.surface)

    def set_theme(self, theme: ThemeColors) -> None:
        set_bg_color(self, theme.surface)
        self.divider.set_color(theme.outline_variant)


class SectionCard(RoundedBox):
    """Titled Material-3 card section used on Profile, Add, Settings, Friend."""

    def __init__(
        self,
        title: str,
        theme: ThemeColors,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            bg=theme.surface_container_low,
            radius=[dp(16)],
            orientation="vertical",
            size_hint=(1, None),
            padding=(dp(18), dp(16), dp(18), dp(16)),
            spacing=dp(12),
            **kwargs,
        )
        self.bind(minimum_height=self.setter("height"))
        lbl = Label(
            text=title,
            color=theme.primary,
            font_size=sp(13),
            bold=True,
            halign="left",
            valign="middle",
            size_hint=(1, None),
            height=dp(20),
        )
        lbl.bind(width=lambda inst, w: setattr(inst, "text_size", (w, None)))
        self.add_widget(lbl)


class SelectableText(TextInput):  # type: ignore[misc]
    """Read-only, selectable message text sized to fit its content.

    Kivy labels can't be selected, so chat text uses a borderless read-only
    TextInput: drag (desktop) or long-press (phones) selects, and Copy works.
    """

    def __init__(
        self,
        text: str,
        color: RGBA,
        max_width: float,
        selection: RGBA,
        font_size_sp: float = 14.5,
        italic: bool = False,
    ) -> None:
        font = "Roboto-Italic" if italic else "Roboto"
        super().__init__(
            text=text,
            readonly=True,
            multiline=True,
            background_normal="",
            background_active="",
            background_color=(0, 0, 0, 0),
            foreground_color=color,
            cursor_color=(0, 0, 0, 0),
            cursor_width=0,
            selection_color=selection,
            font_size=sp(font_size_sp),
            font_name=font,
            padding=(0, 0, 0, 0),
            size_hint=(None, None),
            write_tab=False,
        )
        # Measure the unwrapped width with the same font, so short messages
        # stay compact; skip probing huge texts so we never allocate an
        # oversized unwrapped GL texture.
        if len(text) > 500 or text.count("\n") > 12:
            self.width = max_width
        else:
            probe = Label(text=text, font_size=sp(font_size_sp), font_name=font)
            probe.texture_update()
            self.width = min(max_width, probe.texture_size[0] + dp(2))
        # Apply the font options and lay the lines out now: TextInput defers
        # both to the next frame, and the bubble around this is sized from
        # this height straight away.
        self._refresh_line_options()
        self.height = self.minimum_height
        self.bind(minimum_height=self.setter("height"))


# A row of a KeyedColumn: (key, look, build). It's built again only when its
# look changes.
Row = Tuple[Hashable, Any, Callable[[], Widget]]


class KeyedColumn:
    """A box's children kept in step with keyed rows, building only new ones.

    Chats show a row per message: building all of them again for each
    receipt or new message is what makes long chats slow.
    """

    def __init__(self, box: BoxLayout) -> None:
        self._box = box
        self._rows: dict[Hashable, tuple[Any, Widget]] = {}

    def show(self, rows: Sequence[Row]) -> None:
        kept: dict[Hashable, tuple[Any, Widget]] = {}
        widgets: list[Widget] = []
        for key, look, build in rows:
            old = self._rows.get(key)
            widget = old[1] if old is not None and old[0] == look else build()
            kept[key] = (look, widget)
            widgets.append(widget)
        self._rows = kept
        shown = self._box.children[::-1]
        same = 0
        while (same < min(len(shown), len(widgets))
               and shown[same] is widgets[same]):
            same += 1
        if same == 0:
            self._box.clear_widgets()
        else:
            for widget in shown[same:]:
                self._box.remove_widget(widget)
        for widget in widgets[same:]:
            self._box.add_widget(widget)


# Closer than this to the end counts as reading the newest messages.
_AT_BOTTOM_DP = 48.0


class HistoryView(ScrollView):  # type: ignore[misc]
    """Chat history that keeps its place while rows come and go.

    The rows in view stay put when older messages arrive above them or new
    ones below; at the bottom, it follows the new ones.
    """

    # Kivy's property, typed for mypy.
    scroll_y: float

    def __init__(
        self,
        desktop: bool,
        on_near_top: Callable[[], None],
    ) -> None:
        # On desktop, mouse drags select text and the wheel or scroll bar
        # scrolls; on phones, swipes scroll.
        super().__init__(
            do_scroll_x=False,
            bar_width=dp(8) if desktop else dp(5),
            scroll_type=["bars"] if desktop else ["content"],
            size_hint=(1, 1),
        )
        self.box = BoxLayout(
            orientation="vertical",
            size_hint=(1, None),
            padding=(dp(14), dp(10), dp(14), dp(10)),
            spacing=dp(2),
        )
        self.box.bind(minimum_height=self.box.setter("height"))
        self.add_widget(self.box)
        self._column = KeyedColumn(self.box)
        self._on_near_top = on_near_top
        self._last_height = float(self.height)
        # Whether the newest row is in view, as the reader left it; resizes
        # (the keyboard) keep it so, whatever Kivy does to scroll_y meanwhile.
        self._at_bottom = True
        self._resizing: Any = None
        self._keep_ev: Any = None
        self._to_bottom_evs: list[Any] = []
        self.bind(scroll_y=self._scrolled, height=self._resized)

    def _cancel_to_bottom(self) -> None:
        for ev in self._to_bottom_evs:
            ev.cancel()
        self._to_bottom_evs.clear()

    def close(self) -> None:
        if self._resizing is not None:
            self._resizing.cancel()
            self._resizing = None
        if self._keep_ev is not None:
            self._keep_ev.cancel()
            self._keep_ev = None
        self._cancel_to_bottom()

    def _room(self, height: Optional[float] = None) -> float:
        view = self.height if height is None else height
        return max(0.0, float(self.box.height) - float(view))

    def _resized(self, _inst: Any, height: float) -> None:
        """Keep the bottom in place, e.g. as the keyboard comes and goes.

        Kivy keeps the top, which hides the newest messages under the
        keyboard.
        """
        from_bottom = (0.0 if self._at_bottom
                       else self.scroll_y * self._room(self._last_height))
        self._last_height = float(height)
        if self._resizing is not None:
            self._resizing.cancel()
        self._resizing = Clock.schedule_once(self._resize_done, 0.5)
        self._keep_from_bottom(from_bottom)
        # Kivy lays out and updates its scroll effect after us; again then.
        if self._keep_ev is not None:
            self._keep_ev.cancel()
        self._keep_ev = Clock.schedule_once(
            lambda _dt: self._keep_from_bottom(from_bottom))

    def _sync_scroll_effect(self) -> None:
        # Kivy's scroll effect holds its own position and overscroll spring;
        # clear velocity/overscroll so a resize across the fit/overflow boundary
        # cannot bounce or restore the previous position.
        self._update_effect_y_bounds()
        if self.effect_y is not None:
            self.effect_y.velocity = 0.0
            self.effect_y.overscroll = 0.0
            self.effect_y.scroll = self.effect_y.value

    def _keep_from_bottom(self, from_bottom: float) -> None:
        room = self._room()
        self.scroll_y = min(1.0, from_bottom / room) if room > 0 else 1.0
        self._sync_scroll_effect()

    def _resize_done(self, _dt: float) -> None:
        self._resizing = None

    def _scrolled(self, _inst: Any, scroll_y: float) -> None:
        room = self._room()
        if self._resizing is None:
            self._at_bottom = scroll_y * room <= dp(_AT_BOTTOM_DP)
        if (1.0 - scroll_y) * room < self.height / 2.0:
            self._on_near_top()

    def _tops(self) -> tuple[dict[Widget, float], float]:
        """Each row's distance below the top, and the whole height.

        Rows have fixed heights, so this is known before Kivy lays them out.
        """
        spacing = float(self.box.spacing)
        top = float(self.box.padding[1])
        tops: dict[Widget, float] = {}
        for widget in reversed(self.box.children):
            tops[widget] = top
            top += widget.height + spacing
        if tops:
            top -= spacing
        return tops, top + float(self.box.padding[3])

    def show(self, rows: Sequence[Row], follow: bool) -> None:
        """Show ``rows``; ``follow`` goes to the newest, as for a new chat."""
        tops, height = self._tops()
        room = max(0.0, height - self.height)
        view_top = (1.0 - self.scroll_y) * room
        at_bottom = room - view_top <= dp(_AT_BOTTOM_DP)
        # The rows in view, from the top: the first one still shown after
        # the update stays where it is on the screen.
        anchors = [(w, t - view_top) for w, t in tops.items()
                   if t + w.height > view_top]

        self._column.show(rows)

        self._cancel_to_bottom()
        if follow or at_bottom:
            self._at_bottom = True
            self._to_bottom_evs.append(Clock.schedule_once(self._to_bottom, 0))
            self._to_bottom_evs.append(
                Clock.schedule_once(self._to_bottom, 0.05))
            return
        tops, height = self._tops()
        room = max(0.0, height - self.height)
        for widget, offset in anchors:
            if widget in tops:
                view_top = tops[widget] - offset
                break
        self.scroll_y = (min(1.0, max(0.0, 1.0 - view_top / room))
                         if room > 0 else 1.0)
        self._sync_scroll_effect()

    def _to_bottom(self, _dt: float) -> None:
        self.update_from_scroll()
        self.scroll_y = 0.0
        self._sync_scroll_effect()


def auto_label(
    text: str,
    color: RGBA,
    font_size_sp: float = 14.0,
    bold: bool = False,
    italic: bool = False,
    halign: str = "left",
    font_name: Optional[str] = None,
) -> Label:
    """Wrapped multi-line Kivy Label that auto-sizes its height to fit text."""
    lbl = Label(
        text=text,
        color=color,
        font_size=sp(font_size_sp),
        bold=bold,
        italic=italic,
        halign=halign,
        valign="top",
        size_hint=(1, None),
    )
    if font_name:
        lbl.font_name = font_name

    def _fit(inst: Label, *_args: Any) -> None:
        if not inst.text:
            inst.height = 0
            return
        inst.text_size = (inst.width, None)
        inst.texture_update()
        inst.height = max(dp(18), inst.texture_size[1] + dp(2))

    lbl.bind(width=_fit, text=_fit)
    return lbl


def show_confirm_dialog(
    title: str,
    body: str,
    confirm_label: str,
    theme: ThemeColors,
    on_confirm: Callable[[], None],
    danger: bool = False,
) -> ModalView:
    """Display a centered confirmation modal matching kTox's AlertDialog."""
    modal = ModalView(
        size_hint=(None, None),
        width=min(dp(360), max(dp(200), Window.width - dp(32))),
        background="",
        background_color=(0, 0, 0, 0),
        overlay_color=(0, 0, 0, 0.55),
    )
    card = RoundedBox(
        bg=theme.surface_container,
        radius=[dp(20)],
        orientation="vertical",
        padding=(dp(22), dp(20), dp(22), dp(16)),
        spacing=dp(12),
        size_hint=(1, None),
    )
    t_lbl = auto_label(title, theme.on_surface, font_size_sp=18, bold=True)
    b_lbl = auto_label(body, theme.on_surface_variant, font_size_sp=14)
    card.add_widget(t_lbl)
    card.add_widget(b_lbl)

    btns = BoxLayout(
        orientation="horizontal",
        size_hint=(1, None),
        height=dp(40),
        spacing=dp(8),
    )
    btns.add_widget(Widget())
    btns.add_widget(
        PillButton(
            text="Cancel",
            bg=(0, 0, 0, 0),
            fg=theme.on_surface_variant,
            on_click=modal.dismiss,
            height_dp=36,
            pad_x_dp=14,
        )
    )

    def _ok() -> None:
        modal.dismiss()
        on_confirm()

    ok_fg = theme.on_error if danger else theme.on_primary
    ok_bg = theme.error if danger else theme.primary
    btns.add_widget(
        PillButton(
            text=confirm_label,
            bg=ok_bg,
            fg=ok_fg,
            on_click=_ok,
            height_dp=36,
            pad_x_dp=16,
        )
    )
    card.add_widget(btns)
    def _sync_dialog_height(_inst: Any, height: float) -> None:
        card.height = height
        modal.height = height

    card.bind(minimum_height=_sync_dialog_height)
    card.height = dp(170)
    modal.height = dp(170)
    modal.add_widget(card)
    modal.open()
    return modal
