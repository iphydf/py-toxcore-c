# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""Call pictures on screen: the GPU turns I420 into colours."""
from __future__ import annotations

import logging
from typing import Any
from typing import Optional

from kivy.graphics import BindTexture
from kivy.graphics import Color
from kivy.graphics import Rectangle
from kivy.graphics import RenderContext
from kivy.graphics.opengl import GL_UNPACK_ALIGNMENT
from kivy.graphics.opengl import glPixelStorei
from kivy.graphics.texture import Texture
from kivy.uix.widget import Widget

from pytox_client.media import VideoFrame

_LOG = logging.getLogger("pytox")

# BT.601 limited range, which VP8 and cameras use.
_I420_TO_RGB = """
$HEADER$
uniform sampler2D tex_u;
uniform sampler2D tex_v;

void main(void) {
    float y = 1.1643 * (texture2D(texture0, tex_coord0).r - 0.0625);
    float u = texture2D(tex_u, tex_coord0).r - 0.5;
    float v = texture2D(tex_v, tex_coord0).r - 0.5;
    vec3 rgb = clamp(vec3(
        y + 1.5958 * v,
        y - 0.39173 * u - 0.81290 * v,
        y + 2.017 * u), 0.0, 1.0);
    gl_FragColor = vec4(rgb, 1.0) * frag_color;
}
"""


def _rows(plane: bytes, width: int, height: int, stride: int) -> bytes:
    """A plane without the padding at the end of its rows."""
    if stride == width:
        return plane[:width * height]
    return b"".join(plane[j * stride:j * stride + width] for j in range(height))


def _valid_plane(plane: bytes, width: int, height: int, stride: int) -> bool:
    if width <= 0 or height <= 0 or stride < width:
        return False
    return len(plane) >= (height - 1) * stride + width


class VideoView(Widget):  # type: ignore[misc]
    """Shows the newest picture of a call.

    ``fill`` crops it to fill the widget (our own small picture); otherwise
    all of it shows, as large as fits (the friend's).
    """

    def __init__(self, fill: bool = False, **kwargs: Any) -> None:
        self.canvas = RenderContext(use_parent_projection=True,
                                    use_parent_modelview=True,
                                    use_parent_frag_modelview=True)
        self.canvas.shader.fs = _I420_TO_RGB
        self._shader_ok = bool(self.canvas.shader.success)
        if not self._shader_ok:
            _LOG.warning("VideoView shader failed to compile")
        super().__init__(**kwargs)
        self._fill = fill
        self._frame: Optional[VideoFrame] = None
        self._textures: list[Texture] = []
        with self.canvas:
            self._bind_u = BindTexture(index=1)
            self._bind_v = BindTexture(index=2)
            Color(1, 1, 1, 1)
            self._rect = Rectangle(size=(0, 0))
        self.canvas["tex_u"] = 1
        self.canvas["tex_v"] = 2
        self.bind(pos=self._place, size=self._place)

    @property
    def showing(self) -> bool:
        return self._frame is not None

    def show(self, frame: Optional[VideoFrame]) -> None:
        """On the UI thread: show ``frame``, or nothing."""
        if frame is None:
            self._frame = None
            self._rect.size = (0, 0)
            self._rect.texture = None
            self._bind_u.texture = None
            self._bind_v.texture = None
            self._textures = []
            return
        if not self._shader_ok:
            return
        w, h = frame.width, frame.height
        if w <= 0 or h <= 0:
            return
        cw, ch = (w + 1) // 2, (h + 1) // 2
        sizes = ((w, h), (cw, ch), (cw, ch))
        planes = ((frame.y, frame.y_stride), (frame.u, frame.u_stride),
                  (frame.v, frame.v_stride))
        if not all(
                _valid_plane(plane, pw, ph, stride)
                for (plane, stride), (pw, ph) in zip(planes, sizes)):
            return
        self._frame = frame
        if [tuple(t.size) for t in self._textures] != list(sizes):
            self._textures = [
                Texture.create(size=s, colorfmt="luminance") for s in sizes
            ]
            self._rect.texture = self._textures[0]
            self._bind_u.texture = self._textures[1]
            self._bind_v.texture = self._textures[2]
        # Rows of odd widths aren't 4-byte aligned.
        glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
        for texture, (plane, stride), (pw, ph) in zip(self._textures, planes,
                                                      sizes):
            texture.blit_buffer(_rows(plane, pw, ph, stride),
                                colorfmt="luminance",
                                bufferfmt="ubyte")
        self._place()

    def _place(self, *_args: Any) -> None:
        frame = self._frame
        if frame is None or self.width <= 0 or self.height <= 0:
            return
        aspect = frame.width / frame.height
        # The part of the picture that shows, in texture coordinates.
        u0, u1, v0, v1 = 0.0, 1.0, 0.0, 1.0
        if self._fill:
            if self.width / self.height > aspect:
                keep = (frame.width / self.width * self.height) / frame.height
                v0 = (1 - keep) / 2
                v1 = 1 - v0
            else:
                keep = (frame.height / self.height * self.width) / frame.width
                u0 = (1 - keep) / 2
                u1 = 1 - u0
            self._rect.pos = self.pos
            self._rect.size = self.size
        else:
            w = min(self.width, self.height * aspect)
            h = w / aspect
            self._rect.pos = (self.x + (self.width - w) / 2,
                              self.y + (self.height - h) / 2)
            self._rect.size = (w, h)
        if frame.mirrored:
            u0, u1 = u1, u0
        # Rows come top first; textures start at the bottom.
        self._rect.tex_coords = (u0, v1, u1, v1, u1, v0, u0, v0)
