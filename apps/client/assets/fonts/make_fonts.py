#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""Make PyTox's fonts: Kivy's Roboto with emoji from Noto Emoji.

Kivy draws each label and text field in one font, with no fallback for the
characters it lacks, so emoji go into the font itself. Noto Emoji's are
outlines in the text's colour: Kivy can't draw colour emoji.

The fonts are made at build time, like Go Tox's, not kept in git. Needs
fontTools. Writes PyToxSans-{Regular,Italic,Bold,BoldItalic}.ttf and Noto
Emoji's licence next to this script.

Usage: make_fonts.py [--cache DIR]
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import urllib.request
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
from fontTools.ttLib.tables._g_l_y_f import Glyph
from fontTools.varLib import instancer

HERE = Path(__file__).resolve().parent
_NOTO = ("https://github.com/google/fonts/raw/"
         "8b0a1d0f5983c89bc2b93f1b5fb55f9e252744b5/ofl/notoemoji/")
_KIVY = "https://raw.githubusercontent.com/kivy/kivy/2.3.1/kivy/data/fonts/"
# What's fetched, and its sha256.
_FILES = {
    "NotoEmoji.ttf": (
        _NOTO + "NotoEmoji%5Bwght%5D.ttf",
        "de6c18832938afc99caf132b39d6a30a19bac7f2e812e28db2535b4608d27551"),
    "OFL.txt": (_NOTO + "OFL.txt", None),
    "Roboto-Regular.ttf": (
        _KIVY + "Roboto-Regular.ttf",
        "f0e5a21bf5c95e4c1bce2be98a3656ebcc6d42a21f41c4e3ebf69dd815702e54"),
    "Roboto-Italic.ttf": (
        _KIVY + "Roboto-Italic.ttf",
        "044d2e3e3a17da487da46fc38cbd0a729deb9af044e563f66f8cdbc57421277e"),
    "Roboto-Bold.ttf": (
        _KIVY + "Roboto-Bold.ttf",
        "ef2ab0e402d5cb9de893e263a2c44e57f57fec3974b0d981bfe84dec3dae83a1"),
    "Roboto-BoldItalic.ttf": (
        _KIVY + "Roboto-BoldItalic.ttf",
        "3157773ff81c4eb0883936e27054c05ed342beeef83a430a1d998213822d3da1"),
}
_SKIN_TONES = range(0x1F3FB, 0x1F400)
# Each style, and the emoji weight that goes with it.
_STYLES = {"Regular": 400, "Italic": 400, "Bold": 700, "BoldItalic": 700}


def _fetch(cache: Path, name: str) -> Path:
    url, sha256 = _FILES[name]
    path = cache / name
    if not path.exists():
        cache.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url) as response:
            path.write_bytes(response.read())
    if sha256 is not None:
        got = hashlib.sha256(path.read_bytes()).hexdigest()
        if got != sha256:
            path.unlink()
            raise SystemExit(f"{name}: sha256 {got}, expected {sha256}")
    return path


def _add_emoji(base: TTFont, emoji: TTFont) -> None:
    """Copy in the emoji glyphs for the characters ``base`` lacks.

    Roboto keeps its own digits, ``#``, ``*`` and space, which Noto Emoji has
    for keycaps.
    """
    have = base.getBestCmap()
    take = {
        cp: name
        for cp, name in emoji.getBestCmap().items() if cp not in have
    }
    order = base.getGlyphOrder()
    glyf = base["glyf"]
    hmtx = base["hmtx"]
    copied: dict[str, str] = {}

    def copy_glyph(name: str) -> str:
        if name in copied:
            return copied[name]
        new = f"emoji.{name}"
        copied[name] = new
        glyph = copy.deepcopy(emoji["glyf"][name])
        if glyph.isComposite():
            for component in glyph.components:
                component.glyphName = copy_glyph(component.glyphName)
        order.append(new)
        glyf.glyphs[new] = glyph
        hmtx.metrics[new] = emoji["hmtx"][name]
        return new

    mapping = {cp: copy_glyph(name) for cp, name in take.items()}
    # Kivy doesn't shape text, so a skin tone would show as a swatch after
    # the hand: it shows nothing instead.
    blank = "emoji.blank"
    order.append(blank)
    glyf.glyphs[blank] = Glyph()
    hmtx.metrics[blank] = (0, 0)
    for cp in _SKIN_TONES:
        mapping[cp] = blank
    base.setGlyphOrder(order)
    glyf.glyphOrder = order
    for name in copied.values():
        glyf[name].recalcBounds(glyf)

    cmap = base["cmap"]
    full = dict(have)
    full.update(mapping)
    for table in cmap.tables:
        if table.isUnicode():
            table.cmap.update(
                {cp: g for cp, g in mapping.items() if cp <= 0xFFFF})
    # Emoji beyond the first 65536 characters need a format 12 table.
    wide = CmapSubtable.newSubtable(12)
    wide.platformID, wide.platEncID, wide.language = 3, 10, 0
    wide.cmap = full
    cmap.tables = [
        t for t in cmap.tables if (t.platformID, t.platEncID) != (3, 10)
    ] + [wide]
    # Per-size tables made for the old glyphs only.
    for tag in ("hdmx", "LTSH", "VDMX"):
        if tag in base:
            del base[tag]


def _rename(font: TTFont, style: str) -> None:
    """Our own family, so no system Roboto is taken for it."""
    names = font["name"]
    for record in names.names:
        if record.nameID in (1, 16):
            record.string = "PyTox Sans"
        elif record.nameID == 4:
            record.string = f"PyTox Sans {style}"
        elif record.nameID == 6:
            record.string = f"PyToxSans-{style}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache",
                        type=Path,
                        default=Path.home() / ".cache" / "pytox-fonts")
    args = parser.parse_args()
    noto = _fetch(args.cache, "NotoEmoji.ttf")
    emoji = {
        weight: instancer.instantiateVariableFont(TTFont(noto),
                                                  {"wght": weight})
        for weight in set(_STYLES.values())
    }
    for style, weight in _STYLES.items():
        base = TTFont(_fetch(args.cache, f"Roboto-{style}.ttf"))
        _add_emoji(base, emoji[weight])
        _rename(base, style)
        out = HERE / f"PyToxSans-{style}.ttf"
        base.save(out)
        print(out)
    (HERE / "LICENSE-NotoEmoji.txt").write_bytes(
        _fetch(args.cache, "OFL.txt").read_bytes())


if __name__ == "__main__":
    main()
