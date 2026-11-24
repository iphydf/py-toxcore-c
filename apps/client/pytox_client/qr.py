# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""Pure-Python QR code helper backed by ``segno`` (with PNG fallback)."""
from __future__ import annotations

from io import BytesIO
from typing import Optional


def make_qr_matrix(text: str) -> Optional[list[list[bool]]]:
    """Return a boolean matrix (with quiet border) for ``text`` using segno."""
    try:
        import segno
    except ImportError:
        return None
    qr = segno.make(text, error="m")
    border = 2
    rows = [[bool(cell) for cell in row] for row in qr.matrix]
    width = len(rows[0]) + 2 * border
    out: list[list[bool]] = [[False] * width for _ in range(border)]
    for row in rows:
        out.append([False] * border + row + [False] * border)
    for _ in range(border):
        out.append([False] * width)
    return out


def make_qr_png(text: str, scale: int = 8) -> Optional[bytes]:
    """Encode ``text`` as a black-on-white QR PNG."""
    try:
        import segno
    except ImportError:
        return None
    buf = BytesIO()
    qr = segno.make(text, error="m")
    qr.save(buf, kind="png", scale=scale, border=2, dark="#000000",
            light="#ffffff")
    return buf.getvalue()
