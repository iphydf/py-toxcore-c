# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 The TokTok team
"""Material-3 inspired light and dark color schemes matching kTox."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

RGBA = Tuple[float, float, float, float]


def hex_color(value: str, alpha: float = 1.0) -> RGBA:
    """Convert a ``#RRGGBB`` string into normalized Kivy RGBA floats."""
    h = value.lstrip("#")
    return (
        int(h[0:2], 16) / 255.0,
        int(h[2:4], 16) / 255.0,
        int(h[4:6], 16) / 255.0,
        alpha,
    )


def with_alpha(color: RGBA, alpha: float) -> RGBA:
    return (color[0], color[1], color[2], alpha)


@dataclass(frozen=True)
class ThemeColors:
    """Color roles matching ``jvm-toxcore-c/apps/client/.../Theme.kt``."""

    is_dark: bool
    primary: RGBA
    on_primary: RGBA
    primary_container: RGBA
    on_primary_container: RGBA
    secondary: RGBA
    secondary_container: RGBA
    on_secondary_container: RGBA
    # PyTox's own tones around kTox's tertiary (#65587B / #CFBFE8), used for
    # group invite cards.
    tertiary_container: RGBA
    on_tertiary_container: RGBA
    background: RGBA
    surface: RGBA
    surface_container_lowest: RGBA
    surface_container_low: RGBA
    surface_container: RGBA
    surface_container_high: RGBA
    surface_container_highest: RGBA
    on_surface: RGBA
    on_surface_variant: RGBA
    outline: RGBA
    outline_variant: RGBA
    error: RGBA
    on_error: RGBA


LIGHT_THEME = ThemeColors(
    is_dark=False,
    primary=hex_color("#2B6A8F"),
    on_primary=hex_color("#FFFFFF"),
    primary_container=hex_color("#C9E6FF"),
    on_primary_container=hex_color("#001E2F"),
    secondary=hex_color("#50606E"),
    secondary_container=hex_color("#D3E5F5"),
    on_secondary_container=hex_color("#0C1D29"),
    tertiary_container=hex_color("#E9DEF8"),
    on_tertiary_container=hex_color("#21182E"),
    background=hex_color("#F7F9FC"),
    surface=hex_color("#F7F9FC"),
    surface_container_lowest=hex_color("#FFFFFF"),
    surface_container_low=hex_color("#F1F4F8"),
    surface_container=hex_color("#EBEEF3"),
    surface_container_high=hex_color("#E5E8ED"),
    surface_container_highest=hex_color("#DFE3E7"),
    on_surface=hex_color("#181C20"),
    on_surface_variant=hex_color("#4A5560"),
    outline=hex_color("#8A95A0"),
    outline_variant=hex_color("#D4DAE0"),
    error=hex_color("#BA1A1A"),
    on_error=hex_color("#FFFFFF"),
)

DARK_THEME = ThemeColors(
    is_dark=True,
    primary=hex_color("#97CCF8"),
    on_primary=hex_color("#00344E"),
    primary_container=hex_color("#0B4D6F"),
    on_primary_container=hex_color("#C9E6FF"),
    secondary=hex_color("#B7C9D9"),
    secondary_container=hex_color("#384956"),
    on_secondary_container=hex_color("#D3E5F5"),
    tertiary_container=hex_color("#4C4062"),
    on_tertiary_container=hex_color("#EBDDFF"),
    background=hex_color("#0F1418"),
    surface=hex_color("#0F1418"),
    surface_container_lowest=hex_color("#0A0F12"),
    surface_container_low=hex_color("#171C20"),
    surface_container=hex_color("#1B2024"),
    surface_container_high=hex_color("#262A2F"),
    surface_container_highest=hex_color("#30353A"),
    on_surface=hex_color("#E2E6EA"),
    on_surface_variant=hex_color("#9AA5B0"),
    outline=hex_color("#6E7882"),
    outline_variant=hex_color("#2B3137"),
    error=hex_color("#FFB4AB"),
    on_error=hex_color("#690005"),
)

# Presence dots, shared across light and dark themes.
ONLINE: RGBA = hex_color("#3DBB5D")
AWAY: RGBA = hex_color("#F2B33D")
BUSY: RGBA = hex_color("#E5484D")

TWO_PANES_DP = 720
LIST_WIDTH_DP = 340
