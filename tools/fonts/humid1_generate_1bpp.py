#!/usr/bin/env python3
"""
humid1_generate_1bpp.py (v1.0.10)
==============================
Humidyne Labs / Humiditron `epd-font` General-Purpose 1-BPP Bilevel Font & Modular Icon Studio
(IBM Plex + Terminus + Font Awesome 7, Lucide, Phosphor, Tabler + Custom TrueType Fonts).

Repository : https://github.com/Humidyne-Labs/epd-font
Author     : Humidyne Labs / Humiditron
License    : MIT License (Upstream fonts retain SIL OFL 1.1 / CC-BY-4.0 / ISC / MIT)

Target Hardware (Configurable via CLI `--dpi`, `--screen-width`, `--screen-height` or Scheme JSON):
  - Any 1-bit monochrome E-Paper (EPD), OLED, Sharp Memory LCD, or TFT display
  - Default Reference Profile: 200x200 px @ 188.3 DPI (1-bit monochrome, LV_COLOR_FORMAT_I1)

Four Integrated Workflows (Subcommands or Flat CLI Flags):
  1. gen-assets : Synthesize static weighted .ttf files (Regular 400, Text 450, Medium 500,
                  Bold 700, Italic, Condensed wdth=85) from upstream IBM Plex Variable TTFs
                  and convert FontAwesome5 WOFF to a native .ttf so 100% of static_assets/
                  are consistent TrueType (.ttf) binaries.
  2. patch      : Dump rasterized strikes into named folders of human-editable ASCII .txt
                  glyph files (ascii_patches/<strike_symbol>/U+XXXX_<name>.txt), and compile
                  edited ASCII .txt folders back into font_icon_epd_patches.json.
  3. check      : Generate full-font visual inspection PNG sheets for every individual strike
                  (inspect_pngs/<strike_symbol>.png showing every glyph at 1x and 4x grid zoom),
                  render multi-mode rasterization comparison sheets, and run the 200x200 SSD1681
                  horizontal string-width audit across all 5 H1OS screens.
  4. build      : Automated CMake / CLI firmware code generator producing LVGL v9 1-bpp .c
                  files, plex_fonts.h, backward-compatible h1os_fonts.h, Adobe BDF 2.1 strikes,
                  and CSV metric tables (with automatic ingestion of both font_icon_epd_patches.json
                  and ascii_patches/ folders).

Author: Humidyne Labs Typography Toolchain
License: MIT License (Toolchain) / SIL OFL-1.1 (IBM Plex & Terminus) / ISC (Lucide) / MIT (Phosphor & Tabler)
"""

from __future__ import annotations

import argparse
import csv
import concurrent.futures
import ctypes
import time

FT_LOAD_NO_HINTING = 1 << 1


def format_strike_symbol(family: str, role: str, size_px: int) -> str:
    """
    Canonical v1.0.10 `humid1_` symbol naming convention:
      - IBM Plex families (sans, cond, mono, serif, math) -> humid1_font_plex_<family>_<role>_<size>
      - Terminus family (terminus)                        -> humid1_font_terminus_<role>_<size>
      - Modular Icon families (icon_fa7, icon_lucide...)  -> humid1_<family>_<role>_<size>
      - Custom font families                              -> humid1_font_<family>_<role>_<size>
    """
    if family in ("sans", "cond", "mono", "serif", "math"):
        return f"humid1_font_plex_{family}_{role}_{size_px}"
    elif family == "terminus":
        return f"humid1_font_terminus_{role}_{size_px}"
    elif family.startswith("icon_"):
        return f"humid1_{family}_{role}_{size_px}"
    return f"humid1_font_{family}_{role}_{size_px}"
import ctypes.util
import json
import math
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

# =============================================================================
# 1. UNICODE RANGE PROFILES, TROUBLE-15 SET & FONTAWESOME 5 ICON DEFINITIONS
# =============================================================================

RANGE_UI_STR = (
    "0x20-0x7E,0xB0,0xB1,0xB2,0xB3,0xB5,0x0394,"
    "0x2010-0x2014,0x2022,0x2190-0x2193"
)

# Note: U+03A2 is an unassigned Unicode codepoint in the Greek uppercase block
# and is explicitly excluded by splitting 0x0391-0x03A1,0x03A3-0x03A9.
RANGE_MATH_STR = (
    "0x20-0x7E,0xB0,0xB1,0xB2,0xB3,0xB5,"
    "0x0391-0x03A1,0x03A3-0x03A9,0x03B1-0x03C9,"
    "0x2126,0x2190-0x2193,0x2200,0x2202,0x2203,0x2205,0x2206,"
    "0x2208,0x2209,0x2211,0x221A,0x221E,0x2248,0x2260,0x2264,0x2265"
)

DEFAULT_FONTAWESOME_ICONS = (
    "61441,61448,61451,61452,61453,61457,61459,61461,61465,61468,"
    "61473,61478,61479,61480,61502,61507,61512,61515,61516,61517,"
    "61521,61522,61523,61524,61543,61544,61550,61552,61553,61556,"
    "61559,61560,61561,61563,61587,61589,61636,61637,61639,61641,"
    "61664,61671,61674,61683,61724,61732,61787,61931,62016,62017,"
    "62018,62019,62020,62087,62099,62212,62189,62810,63426,63650"
)

TROUBLE_15_CODEPOINTS = {
    0x0023,  # '#'
    0x0024,  # '$'
    0x0025,  # '%'
    0x0026,  # '&'
    0x0030,  # '0'
    0x0034,  # '4'
    0x0038,  # '8'
    0x003F,  # '?'
    0x0040,  # '@'
    0x0061,  # 'a'
    0x0063,  # 'c'
    0x0065,  # 'e'
    0x0067,  # 'g'
    0x0073,  # 's'
    0x0079,  # 'y'
}

SAFE_CHAR_NAMES = {
    0x0020: "space",
    0x0021: "exclam",
    0x0022: "quotedbl",
    0x0023: "numbersign",
    0x0024: "dollar",
    0x0025: "percent",
    0x0026: "ampersand",
    0x0027: "quotesingle",
    0x0028: "parenleft",
    0x0029: "parenright",
    0x002A: "asterisk",
    0x002B: "plus",
    0x002C: "comma",
    0x002D: "hyphen",
    0x002E: "period",
    0x002F: "slash",
    0x003A: "colon",
    0x003B: "semicolon",
    0x003C: "less",
    0x003D: "equal",
    0x003E: "greater",
    0x003F: "question",
    0x0040: "at",
    0x005B: "bracketleft",
    0x005C: "backslash",
    0x005D: "bracketright",
    0x005E: "asciicircum",
    0x005F: "underscore",
    0x0060: "grave",
    0x007B: "braceleft",
    0x007C: "bar",
    0x007D: "braceright",
    0x007E: "asciitilde",
    0x00B0: "degree",
    0x00B1: "plusminus",
    0x00B2: "twosuperior",
    0x00B3: "threesuperior",
    0x00B5: "micro",
    0x0394: "Delta",
    0x2010: "hyphen_uni",
    0x2013: "endash",
    0x2014: "emdash",
    0x2022: "bullet",
    0x2190: "arrowleft",
    0x2191: "arrowup",
    0x2192: "arrowright",
    0x2193: "arrowdown",
}


ICON_NAME_REGISTRY: Dict[str, Dict[str, str]] = {}

def load_icon_name_registry(static_dir: Path) -> None:
    global ICON_NAME_REGISTRY
    if ICON_NAME_REGISTRY:
        return
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent if script_dir.name == "fonts" else script_dir.parent
    for cand in [
        repo_root / "build" / "metadata" / "unified_icon_names.json",
        static_dir.parent / "metadata" / "unified_icon_names.json",
        static_dir / "metadata" / "unified_icon_names.json",
        static_dir.parent / "static_ttfs" / "metadata" / "unified_icon_names.json",
        script_dir / "icon_metadata" / "unified_icon_names.json",
        repo_root / "assets" / "static_ttfs" / "metadata" / "unified_icon_names.json",
    ]:
        if cand.is_file():
            try:
                ICON_NAME_REGISTRY = json.loads(cand.read_text(encoding="utf-8"))
                return
            except Exception:
                pass

def get_semantic_glyph_name(code: int, family: str = "") -> str:
    hex_k = f"0x{code:04X}"
    if family == "icon_tabler" and "icon_tabler_filled" in ICON_NAME_REGISTRY:
        if hex_k in ICON_NAME_REGISTRY["icon_tabler_filled"]:
            raw = ICON_NAME_REGISTRY["icon_tabler_filled"][hex_k]
            return re.sub(r"[^A-Za-z0-9_-]+", "_", raw).strip("_")
    if family and family in ICON_NAME_REGISTRY:
        if hex_k in ICON_NAME_REGISTRY[family]:
            raw = ICON_NAME_REGISTRY[family][hex_k]
            return re.sub(r"[^A-Za-z0-9_-]+", "_", raw).strip("_")
    if code in SAFE_CHAR_NAMES:
        return SAFE_CHAR_NAMES[code]
    elif 0x30 <= code <= 0x39 or 0x41 <= code <= 0x5A or 0x61 <= code <= 0x7A:
        return chr(code)
    return f"uni{code:04X}"

def safe_glyph_filename(code: int, family: str = "") -> str:
    """Return a filesystem-safe, human-readable filename for a codepoint (e.g. `U+0040_at.txt` or `U+E053_battery.txt`)."""
    suffix = get_semantic_glyph_name(code, family)
    return f"U+{code:04X}_{suffix}.txt"


# =============================================================================
# 2. SUB-FAMILY REGISTRY, SIZE FLOORS & BUILD PROFILES
# =============================================================================

SUBFAMILY_FLOORS = {
    "sans": 10,
    "mono": 10,
    "cond": 12,
    "serif": 16,
    "math": 14,
    "terminus": 10,
    "unifont": 16,
    "custom": 10,
    "icon_fa7": 12,
    "icon_lucide": 12,
    "icon_phosphor": 12,
    "icon_tabler": 12,
}

# Upstream Variable -> Static instantiation table (includes Regular 400, Text 450, Medium 500, Bold 700)
VARIABLE_INSTANTIATION_MAP = [
    # Sans (wdth=100) — Full Weight Ladder (100..700) + Italics
    ("IBMPlexSans-Thin.ttf", "sans/IBM Plex Sans Var-Roman.ttf", {"wght": 100.0, "wdth": 100.0}, {}),
    ("IBMPlexSans-ExtraLight.ttf", "sans/IBM Plex Sans Var-Roman.ttf", {"wght": 200.0, "wdth": 100.0}, {}),
    ("IBMPlexSans-Light.ttf", "sans/IBM Plex Sans Var-Roman.ttf", {"wght": 300.0, "wdth": 100.0}, {}),
    ("IBMPlexSans-Regular.ttf", "sans/IBM Plex Sans Var-Roman.ttf", {"wght": 400.0, "wdth": 100.0}, {}),
    ("IBMPlexSans-Text.ttf", "sans/IBM Plex Sans Var-Roman.ttf", {"wght": 450.0, "wdth": 100.0}, {}),
    ("IBMPlexSans-Medium.ttf", "sans/IBM Plex Sans Var-Roman.ttf", {"wght": 500.0, "wdth": 100.0}, {}),
    ("IBMPlexSans-SemiBold.ttf", "sans/IBM Plex Sans Var-Roman.ttf", {"wght": 600.0, "wdth": 100.0}, {}),
    ("IBMPlexSans-Bold.ttf", "sans/IBM Plex Sans Var-Roman.ttf", {"wght": 700.0, "wdth": 100.0}, {}),
    ("IBMPlexSans-Italic.ttf", "sans/IBM Plex Sans Var-Italic.ttf", {"wght": 400.0, "wdth": 100.0}, {}),
    ("IBMPlexSans-TextItalic.ttf", "sans/IBM Plex Sans Var-Italic.ttf", {"wght": 450.0, "wdth": 100.0}, {}),
    ("IBMPlexSans-MediumItalic.ttf", "sans/IBM Plex Sans Var-Italic.ttf", {"wght": 500.0, "wdth": 100.0}, {}),
    ("IBMPlexSans-SemiBoldItalic.ttf", "sans/IBM Plex Sans Var-Italic.ttf", {"wght": 600.0, "wdth": 100.0}, {}),
    ("IBMPlexSans-BoldItalic.ttf", "sans/IBM Plex Sans Var-Italic.ttf", {"wght": 700.0, "wdth": 100.0}, {}),
    # Condensed (wdth=85 extracted from Sans Var)
    ("IBMPlexSansCondensed-Light.ttf", "sans/IBM Plex Sans Var-Roman.ttf", {"wght": 300.0, "wdth": 85.0}, {}),
    ("IBMPlexSansCondensed-Regular.ttf", "sans/IBM Plex Sans Var-Roman.ttf", {"wght": 400.0, "wdth": 85.0}, {}),
    ("IBMPlexSansCondensed-Text.ttf", "sans/IBM Plex Sans Var-Roman.ttf", {"wght": 450.0, "wdth": 85.0}, {}),
    ("IBMPlexSansCondensed-Medium.ttf", "sans/IBM Plex Sans Var-Roman.ttf", {"wght": 500.0, "wdth": 85.0}, {}),
    ("IBMPlexSansCondensed-SemiBold.ttf", "sans/IBM Plex Sans Var-Roman.ttf", {"wght": 600.0, "wdth": 85.0}, {}),
    ("IBMPlexSansCondensed-Bold.ttf", "sans/IBM Plex Sans Var-Roman.ttf", {"wght": 700.0, "wdth": 85.0}, {}),
    ("IBMPlexSansCondensed-Italic.ttf", "sans/IBM Plex Sans Var-Italic.ttf", {"wght": 400.0, "wdth": 85.0}, {}),
    ("IBMPlexSansCondensed-MedItal.ttf", "sans/IBM Plex Sans Var-Italic.ttf", {"wght": 500.0, "wdth": 85.0}, {}),
    ("IBMPlexSansCondensed-BoldItalic.ttf", "sans/IBM Plex Sans Var-Italic.ttf", {"wght": 700.0, "wdth": 85.0}, {}),
    # Mono (with cmap normalization for U+0394 Delta, U+03A9 Omega, U+03BC mu)
    ("IBMPlexMono-Light.ttf", "mono/IBM Plex Mono Var-Roman.ttf", {"wght": 300.0}, {0x0394: "Delta", 0x03A9: "Omega", 0x03BC: "mu"}),
    ("IBMPlexMono-Regular.ttf", "mono/IBM Plex Mono Var-Roman.ttf", {"wght": 400.0}, {0x0394: "Delta", 0x03A9: "Omega", 0x03BC: "mu"}),
    ("IBMPlexMono-Text.ttf", "mono/IBM Plex Mono Var-Roman.ttf", {"wght": 450.0}, {0x0394: "Delta", 0x03A9: "Omega", 0x03BC: "mu"}),
    ("IBMPlexMono-Medium.ttf", "mono/IBM Plex Mono Var-Roman.ttf", {"wght": 500.0}, {0x0394: "Delta", 0x03A9: "Omega", 0x03BC: "mu"}),
    ("IBMPlexMono-SemiBold.ttf", "mono/IBM Plex Mono Var-Roman.ttf", {"wght": 600.0}, {0x0394: "Delta", 0x03A9: "Omega", 0x03BC: "mu"}),
    ("IBMPlexMono-Bold.ttf", "mono/IBM Plex Mono Var-Roman.ttf", {"wght": 700.0}, {0x0394: "Delta", 0x03A9: "Omega", 0x03BC: "mu"}),
    ("IBMPlexMono-Italic.ttf", "mono/IBM Plex Mono Var-Italic.ttf", {"wght": 400.0}, {0x0394: "Delta", 0x03A9: "Omega", 0x03BC: "mu"}),
    ("IBMPlexMono-MediumItalic.ttf", "mono/IBM Plex Mono Var-Italic.ttf", {"wght": 500.0}, {0x0394: "Delta", 0x03A9: "Omega", 0x03BC: "mu"}),
    ("IBMPlexMono-BoldItalic.ttf", "mono/IBM Plex Mono Var-Italic.ttf", {"wght": 700.0}, {0x0394: "Delta", 0x03A9: "Omega", 0x03BC: "mu"}),
    # Serif
    ("IBMPlexSerif-Light.ttf", "serif/IBM Plex Serif Var-Roman.ttf", {"wght": 300.0}, {}),
    ("IBMPlexSerif-Regular.ttf", "serif/IBM Plex Serif Var-Roman.ttf", {"wght": 400.0}, {}),
    ("IBMPlexSerif-Text.ttf", "serif/IBM Plex Serif Var-Roman.ttf", {"wght": 450.0}, {}),
    ("IBMPlexSerif-Medium.ttf", "serif/IBM Plex Serif Var-Roman.ttf", {"wght": 500.0}, {}),
    ("IBMPlexSerif-SemiBold.ttf", "serif/IBM Plex Serif Var-Roman.ttf", {"wght": 600.0}, {}),
    ("IBMPlexSerif-Bold.ttf", "serif/IBM Plex Serif Var-Roman.ttf", {"wght": 700.0}, {}),
    ("IBMPlexSerif-Italic.ttf", "serif/IBM Plex Serif Var-Italic.ttf", {"wght": 400.0}, {}),
    ("IBMPlexSerif-MediumItalic.ttf", "serif/IBM Plex Serif Var-Italic.ttf", {"wght": 500.0}, {}),
    ("IBMPlexSerif-BoldItalic.ttf", "serif/IBM Plex Serif Var-Italic.ttf", {"wght": 700.0}, {}),
]


def get_family_roles(normal_weight: int = 500) -> Dict[str, Dict[str, str]]:
    """
    Map semantic roles (thin, extralight, light, normal, text, medium, semibold, bold, italic, bold_italic)
    to instantiated static TTF filenames.
    """
    tag = {100: "Thin", 200: "ExtraLight", 300: "Light", 400: "Regular", 450: "Text", 500: "Medium", 600: "SemiBold", 700: "Bold"}.get(normal_weight, "Regular")
    ital_tag = {400: "Italic", 450: "TextItalic", 500: "MediumItalic", 600: "SemiBoldItalic", 700: "BoldItalic"}.get(normal_weight, "Italic")
    cond_ital_tag = "Italic" if normal_weight == 400 else "MedItal"
    mono_ital_tag = "Italic" if normal_weight == 400 else "MediumItalic"
    serif_ital_tag = "Italic" if normal_weight == 400 else "MediumItalic"

    return {
        "sans": {
            "thin": "IBMPlexSans-Thin.ttf",
            "extralight": "IBMPlexSans-ExtraLight.ttf",
            "light": "IBMPlexSans-Light.ttf",
            "normal": f"IBMPlexSans-{tag}.ttf",
            "regular": "IBMPlexSans-Regular.ttf",
            "text": "IBMPlexSans-Text.ttf",
            "medium": "IBMPlexSans-Medium.ttf",
            "semibold": "IBMPlexSans-SemiBold.ttf",
            "bold": "IBMPlexSans-Bold.ttf",
            "italic": f"IBMPlexSans-{ital_tag}.ttf",
            "bold_italic": "IBMPlexSans-BoldItalic.ttf",
        },
        "mono": {
            "light": "IBMPlexMono-Light.ttf",
            "normal": f"IBMPlexMono-{tag}.ttf",
            "regular": "IBMPlexMono-Regular.ttf",
            "text": "IBMPlexMono-Text.ttf",
            "medium": "IBMPlexMono-Medium.ttf",
            "semibold": "IBMPlexMono-SemiBold.ttf",
            "bold": "IBMPlexMono-Bold.ttf",
            "italic": f"IBMPlexMono-{mono_ital_tag}.ttf",
            "bold_italic": "IBMPlexMono-BoldItalic.ttf",
        },
        "cond": {
            "light": "IBMPlexSansCondensed-Light.ttf",
            "normal": f"IBMPlexSansCondensed-{tag}.ttf",
            "regular": "IBMPlexSansCondensed-Regular.ttf",
            "text": "IBMPlexSansCondensed-Text.ttf",
            "medium": "IBMPlexSansCondensed-Medium.ttf",
            "semibold": "IBMPlexSansCondensed-SemiBold.ttf",
            "bold": "IBMPlexSansCondensed-Bold.ttf",
            "italic": f"IBMPlexSansCondensed-{cond_ital_tag}.ttf",
            "bold_italic": "IBMPlexSansCondensed-BoldItalic.ttf",
        },
        "serif": {
            "light": "IBMPlexSerif-Light.ttf",
            "normal": f"IBMPlexSerif-{tag}.ttf",
            "regular": "IBMPlexSerif-Regular.ttf",
            "text": "IBMPlexSerif-Text.ttf",
            "medium": "IBMPlexSerif-Medium.ttf",
            "semibold": "IBMPlexSerif-SemiBold.ttf",
            "bold": "IBMPlexSerif-Bold.ttf",
            "italic": f"IBMPlexSerif-{serif_ital_tag}.ttf",
            "bold_italic": "IBMPlexSerif-BoldItalic.ttf",
        },
        "math": {
            "regular": "IBMPlexMath-Regular.ttf",
            "normal": "IBMPlexMath-Regular.ttf",
        },
        "icon_fa7": {
            "solid": "FontAwesome7-Solid.ttf",
            "regular": "FontAwesome7-Regular.ttf",
            "brands": "FontAwesome7-Brands.ttf",
            "normal": "FontAwesome7-Solid.ttf",
        },
        "icon_lucide": {
            "regular": "Lucide-Regular.ttf",
            "normal": "Lucide-Regular.ttf",
        },
        "terminus": {
            "regular": "Terminus-Regular.ttf",
            "normal": "Terminus-Regular.ttf",
            "bold": "Terminus-Bold.ttf",
        },
        "unifont": {
            "regular": "Unifont-Regular.ttf",
            "normal": "Unifont-Regular.ttf",
        },
        "icon_phosphor": {
            "thin": "Phosphor-Thin.ttf",
            "light": "Phosphor-Light.ttf",
            "regular": "Phosphor-Regular.ttf",
            "normal": "Phosphor-Regular.ttf",
            "bold": "Phosphor-Bold.ttf",
            "fill": "Phosphor-Fill.ttf",
            "duotone": "Phosphor-Duotone.ttf",
        },
        "icon_tabler": {
            "thin": "Tabler-Thin200.ttf",
            "light": "Tabler-Light300.ttf",
            "regular": "Tabler-Regular.ttf",
            "normal": "Tabler-Regular.ttf",
            "filled": "Tabler-Filled.ttf",
        },
    }


PROFILES = {
    "h1os": [
        ("sans", "normal", [14, 16, 18, 20, 24, 32], RANGE_UI_STR, True, None),
        ("sans", "bold",   [14, 16, 18, 20, 24, 32], RANGE_UI_STR, True, "plex_sans_normal_{size}"),
        ("mono", "normal", [14, 16, 20, 24],         RANGE_UI_STR, False, "plex_sans_normal_{size}"),
        ("mono", "bold",   [14, 16, 20, 24, 32],     RANGE_UI_STR, False, "plex_sans_bold_{size}"),
        ("math", "regular", [16],                    RANGE_MATH_STR, False, "plex_sans_normal_{size}"),
    ],
    "humid1": [
        ("sans", "normal", [12, 14, 16, 18, 20, 24, 32], RANGE_UI_STR, True, None),
        ("sans", "bold",   [12, 14, 16, 18, 20, 24, 32], RANGE_UI_STR, True, "plex_sans_normal_{size}"),
        ("sans", "italic", [12, 14, 16, 18],             RANGE_UI_STR, False, "plex_sans_normal_{size}"),
        ("mono", "normal", [12, 14, 16, 18, 20, 24, 32], RANGE_UI_STR, False, "plex_sans_normal_{size}"),
        ("mono", "bold",   [12, 14, 16, 18, 20, 24, 32], RANGE_UI_STR, False, "plex_sans_bold_{size}"),
        ("mono", "italic", [12, 14, 16],                 RANGE_UI_STR, False, "plex_sans_normal_{size}"),
        ("cond", "normal", [16, 18, 20, 24],             RANGE_UI_STR, False, "plex_sans_normal_{size}"),
        ("cond", "bold",   [16, 18, 20, 24],             RANGE_UI_STR, False, "plex_sans_bold_{size}"),
        ("serif", "normal", [18, 20, 24],                RANGE_UI_STR, False, "plex_sans_normal_{size}"),
        ("serif", "bold",   [18, 20, 24],                RANGE_UI_STR, False, "plex_sans_bold_{size}"),
        ("math", "regular", [16, 20, 24],                RANGE_MATH_STR, False, "plex_sans_normal_{size}"),
    ],
    "full": [
        ("sans", "normal", [12, 14, 16, 18, 20, 24, 28, 32, 36], RANGE_UI_STR, True, None),
        ("sans", "bold",   [12, 14, 16, 18, 20, 24, 28, 32, 36], RANGE_UI_STR, True, "plex_sans_normal_{size}"),
        ("sans", "italic", [12, 14, 16, 18, 20, 24, 28, 32, 36], RANGE_UI_STR, False, "plex_sans_normal_{size}"),
        ("mono", "normal", [12, 14, 16, 18, 20, 24, 28, 32, 36], RANGE_UI_STR, False, "plex_sans_normal_{size}"),
        ("mono", "bold",   [12, 14, 16, 18, 20, 24, 28, 32, 36], RANGE_UI_STR, False, "plex_sans_bold_{size}"),
        ("mono", "italic", [12, 14, 16, 18, 20, 24, 28, 32, 36], RANGE_UI_STR, False, "plex_sans_normal_{size}"),
        ("cond", "normal", [16, 18, 20, 24, 28, 32],             RANGE_UI_STR, False, "plex_sans_normal_{size}"),
        ("cond", "bold",   [16, 18, 20, 24, 28, 32],             RANGE_UI_STR, False, "plex_sans_bold_{size}"),
        ("cond", "italic", [16, 18, 20, 24, 28, 32],             RANGE_UI_STR, False, "plex_sans_normal_{size}"),
        ("serif", "normal", [18, 20, 24, 28, 32, 36],            RANGE_UI_STR, False, "plex_sans_normal_{size}"),
        ("serif", "bold",   [18, 20, 24, 28, 32, 36],            RANGE_UI_STR, False, "plex_sans_bold_{size}"),
        ("serif", "italic", [18, 20, 24, 28, 32, 36],            RANGE_UI_STR, False, "plex_sans_normal_{size}"),
        ("math", "regular", [16, 20, 24, 32],                    RANGE_MATH_STR, False, "plex_sans_normal_{size}"),
    ],
}


def parse_unicode_range(range_str: str) -> List[int]:
    """Parse an lv_font_conv-style range string into a sorted list of unique codepoints."""
    codes = set()
    for part in range_str.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            for c in range(int(a, 0), int(b, 0) + 1):
                codes.add(c)
        else:
            codes.add(int(part, 0))
    return sorted(codes)


# =============================================================================
# 3. FREETYPE 2 CTYPES BINDING (WITH NATIVE 1-BIT MONOCHROME SCANLINE CONVERTER)
# =============================================================================

class FT_Vector(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class FT_BBox(ctypes.Structure):
    _fields_ = [
        ("xMin", ctypes.c_long),
        ("yMin", ctypes.c_long),
        ("xMax", ctypes.c_long),
        ("yMax", ctypes.c_long),
    ]


class FT_Bitmap(ctypes.Structure):
    _fields_ = [
        ("rows", ctypes.c_uint),
        ("width", ctypes.c_uint),
        ("pitch", ctypes.c_int),
        ("buffer", ctypes.POINTER(ctypes.c_ubyte)),
        ("num_grays", ctypes.c_ushort),
        ("pixel_mode", ctypes.c_ubyte),
        ("palette_mode", ctypes.c_ubyte),
        ("palette", ctypes.c_void_p),
    ]


class FT_Glyph_Metrics(ctypes.Structure):
    _fields_ = [
        ("width", ctypes.c_long),
        ("height", ctypes.c_long),
        ("horiBearingX", ctypes.c_long),
        ("horiBearingY", ctypes.c_long),
        ("horiAdvance", ctypes.c_long),
        ("vertBearingX", ctypes.c_long),
        ("vertBearingY", ctypes.c_long),
        ("vertAdvance", ctypes.c_long),
    ]


class FT_GlyphSlotRec(ctypes.Structure):
    _fields_ = [
        ("library", ctypes.c_void_p),
        ("face", ctypes.c_void_p),
        ("next", ctypes.c_void_p),
        ("glyph_index", ctypes.c_uint),
        ("generic_data", ctypes.c_void_p),
        ("generic_finalizer", ctypes.c_void_p),
        ("metrics", FT_Glyph_Metrics),
        ("linearHoriAdvance", ctypes.c_long),
        ("linearVertAdvance", ctypes.c_long),
        ("advance", FT_Vector),
        ("format", ctypes.c_int),
        ("bitmap", FT_Bitmap),
        ("bitmap_left", ctypes.c_int),
        ("bitmap_top", ctypes.c_int),
    ]


class FT_FaceRec(ctypes.Structure):
    _fields_ = [
        ("num_faces", ctypes.c_long),
        ("face_index", ctypes.c_long),
        ("face_flags", ctypes.c_long),
        ("style_flags", ctypes.c_long),
        ("num_glyphs", ctypes.c_long),
        ("family_name", ctypes.c_char_p),
        ("style_name", ctypes.c_char_p),
        ("num_fixed_sizes", ctypes.c_int),
        ("available_sizes", ctypes.c_void_p),
        ("num_charmaps", ctypes.c_int),
        ("charmaps", ctypes.c_void_p),
        ("generic_data", ctypes.c_void_p),
        ("generic_finalizer", ctypes.c_void_p),
        ("bbox", FT_BBox),
        ("units_per_EM", ctypes.c_ushort),
        ("ascender", ctypes.c_short),
        ("descender", ctypes.c_short),
        ("height", ctypes.c_short),
        ("max_advance_width", ctypes.c_short),
        ("max_advance_height", ctypes.c_short),
        ("underline_position", ctypes.c_short),
        ("underline_thickness", ctypes.c_short),
        ("glyph", ctypes.POINTER(FT_GlyphSlotRec)),
    ]


# FreeType <freetype/freetype.h> exact bit-flags:
# FT_RENDER_MODE_NORMAL = 0, FT_RENDER_MODE_LIGHT = 1, FT_RENDER_MODE_MONO = 2
# FT_LOAD_TARGET_(x) = ((x & 15) << 16)
FT_LOAD_RENDER = 1 << 2
FT_LOAD_NO_HINTING = 1 << 1
FT_LOAD_FORCE_AUTOHINT = 1 << 5
FT_LOAD_MONOCHROME = 1 << 12
FT_LOAD_NO_AUTOHINT = 1 << 15
FT_LOAD_TARGET_NORMAL = 0 << 16
FT_LOAD_TARGET_LIGHT = 1 << 16
FT_LOAD_TARGET_MONO = 2 << 16
FT_PIXEL_MODE_MONO = 1
FT_PIXEL_MODE_GRAY = 2


def load_freetype() -> Tuple[ctypes.CDLL, ctypes.c_void_p]:
    """Locate and initialize system libfreetype."""
    lib_name = ctypes.util.find_library("freetype") or "libfreetype.so.6"
    ft = ctypes.CDLL(lib_name)
    lib = ctypes.c_void_p()
    if ft.FT_Init_FreeType(ctypes.byref(lib)) != 0:
        raise RuntimeError("Failed to initialize FreeType2 library")
    return ft, lib


@dataclass
class GlyphStrike:
    codepoint: int
    glyph_id: int
    adv_w_fp4: int  # 1/16th pixel units (LVGL adv_w)
    box_w: int
    box_h: int
    ofs_x: int
    ofs_y: int
    rows: List[str] = field(default_factory=list)  # List of '#' / '.' strings of length box_w
    patched: bool = False

    def pack_1bpp_bytes(self) -> List[int]:
        """Pack rows of '#' (1) and '.' (0) continuously MSB-first into bytes (LVGL stride=0)."""
        if self.box_w == 0 or self.box_h == 0 or not self.rows:
            return []
        bits: List[int] = []
        for r in self.rows:
            for ch in r:
                bits.append(1 if ch == "#" else 0)
        rem = len(bits) % 8
        if rem != 0:
            bits.extend([0] * (8 - rem))
        out: List[int] = []
        for i in range(0, len(bits), 8):
            byte_val = 0
            for b in range(8):
                byte_val = (byte_val << 1) | bits[i + b]
            out.append(byte_val)
        return out


# =============================================================================
# 4. WORKFLOW 1: GEN-ASSETS (VARIABLE TTF INSTANTIATION & WOFF->TTF CONVERSION)
# =============================================================================

def ensure_static_plex_assets(
    plex_dir: Optional[Path],
    static_dir: Path,
    fa_woff_src: Optional[Path] = None,
    force: bool = False,
) -> Path:
    """
    Ensure all static IBM Plex TTFs AND FontAwesome5-Solid+Brands+Regular.ttf exist in static_dir.
    Standardizes 100% of source assets in static_dir to native TrueType (.ttf) format.
    Returns path to FontAwesome5-Solid+Brands+Regular.ttf (or .woff fallback).
    """
    static_dir.mkdir(parents=True, exist_ok=True)

    # 1. Convert FontAwesome5 WOFF -> native TTF so all source binaries are consistent .ttf files
    fa_ttf_dst = static_dir / "FontAwesome5-Solid+Brands+Regular.ttf"
    fa_woff_dst = static_dir / "FontAwesome5-Solid+Brands+Regular.woff"
    if not fa_ttf_dst.is_file() or force:
        woff_cand = fa_woff_src if (fa_woff_src and fa_woff_src.is_file()) else (
            fa_woff_dst if fa_woff_dst.is_file() else None
        )
        if woff_cand:
            fa_tt = TTFont(str(woff_cand))
            fa_tt.flavor = None  # Strip WOFF wrapper -> pure uncompressed TrueType (.ttf)
            fa_tt.save(str(fa_ttf_dst))
            print(f"    [+] Converted {woff_cand.name} -> {fa_ttf_dst.name} ({fa_ttf_dst.stat().st_size:,} B, pure TTF)")

    # 2. Instantiate static IBM Plex cuts from Variable TTFs
    all_exist = all((static_dir / item[0]).is_file() for item in VARIABLE_INSTANTIATION_MAP) and (
        static_dir / "IBMPlexMath-Regular.ttf"
    ).is_file()

    if not all_exist or force:
        if plex_dir is not None and plex_dir.is_dir():
            print(f"[*] Synthesizing static TTF cuts from Variable TTFs in {plex_dir}...")
            for target_name, rel_src, coords, cmap_aliases in VARIABLE_INSTANTIATION_MAP:
                dst_path = static_dir / target_name
                if dst_path.is_file() and not force:
                    continue
                src_path = plex_dir / rel_src
                if not src_path.is_file():
                    continue
                tt = TTFont(str(src_path))
                inst = instancer.instantiateVariableFont(tt, coords)
                if cmap_aliases and "cmap" in inst:
                    for table in inst["cmap"].tables:
                        if table.isUnicode():
                            for codepoint, glyph_name in cmap_aliases.items():
                                if codepoint not in table.cmap and glyph_name in inst.getGlyphOrder():
                                    table.cmap[codepoint] = glyph_name
                inst.save(str(dst_path))
                print(f"    [+] Instantiated {target_name:<34} ({dst_path.stat().st_size:>7,} B) @ {coords}")

            math_src = plex_dir / "math/IBMPlexMath-Regular.ttf"
            math_dst = static_dir / "IBMPlexMath-Regular.ttf"
            if math_src.is_file() and (not math_dst.is_file() or force):
                shutil.copy2(math_src, math_dst)
                print(f"    [+] Copied IBMPlexMath-Regular.ttf              ({math_dst.stat().st_size:>7,} B)")

    return fa_ttf_dst if fa_ttf_dst.is_file() else fa_woff_dst


# =============================================================================
# 5. KERNING EXTRACTION & LVGL v9 DEAD-PAIR ELIMINATION
# =============================================================================

def extract_kerning_pairs_fp4(
    tt: TTFont,
    size_px: int,
    code_to_gid: Dict[int, int],
    code_to_adv_fp4: Dict[int, int],
    prune_noop: bool = True,
) -> List[Tuple[int, int, int, int, int]]:
    """
    Extract kerning pairs from TrueType 'kern' and OpenType 'GPOS' tables,
    pruning sub-pixel FP4 pairs where ((adv_w + kv + 8) >> 4) == ((adv_w + 8) >> 4).
    """
    upem = tt["head"].unitsPerEm
    cmap = tt.getBestCmap() or {}
    gname_to_codes: Dict[str, List[int]] = {}
    for code in code_to_gid:
        gname = cmap.get(code)
        if gname:
            gname_to_codes.setdefault(gname, []).append(code)

    raw_pairs: Dict[Tuple[str, str], int] = {}

    if "kern" in tt:
        for subtable in tt["kern"].kernTables:
            if hasattr(subtable, "kernTable"):
                for (l_name, r_name), val in subtable.kernTable.items():
                    if val != 0:
                        raw_pairs[(l_name, r_name)] = val

    if "GPOS" in tt and hasattr(tt["GPOS"].table, "LookupList") and tt["GPOS"].table.LookupList:
        active_gnames = set(gname_to_codes.keys())
        for lookup in tt["GPOS"].table.LookupList.Lookup:
            if lookup.LookupType not in (2, 9):
                continue
            for sub in lookup.SubTable:
                actual = sub
                if lookup.LookupType == 9 and hasattr(sub, "ExtSubTable"):
                    actual = sub.ExtSubTable
                if getattr(actual, "LookupType", 2) != 2 and not hasattr(actual, "Format"):
                    continue
                cov = getattr(actual, "Coverage", None)
                if not cov or not hasattr(cov, "glyphs"):
                    continue
                if actual.Format == 1:
                    for l_idx, l_name in enumerate(cov.glyphs):
                        if l_name not in active_gnames or l_idx >= len(actual.PairSet):
                            continue
                        pset = actual.PairSet[l_idx]
                        for pvr in pset.PairValueRecord:
                            r_name = pvr.SecondGlyph
                            if r_name in active_gnames and pvr.Value1 and getattr(pvr.Value1, "XAdvance", 0):
                                raw_pairs[(l_name, r_name)] = pvr.Value1.XAdvance
                elif actual.Format == 2:
                    cdef1 = getattr(actual.ClassDef1, "classDefs", {})
                    cdef2 = getattr(actual.ClassDef2, "classDefs", {})
                    active_l = [g for g in cov.glyphs if g in active_gnames]
                    active_r = list(active_gnames)
                    for l_name in active_l:
                        c1 = cdef1.get(l_name, 0)
                        if c1 >= len(actual.Class1Record):
                            continue
                        c1_rec = actual.Class1Record[c1]
                        for r_name in active_r:
                            c2 = cdef2.get(r_name, 0)
                            if c2 >= len(c1_rec.Class2Record):
                                continue
                            v1 = c1_rec.Class2Record[c2].Value1
                            if v1 and getattr(v1, "XAdvance", 0):
                                raw_pairs[(l_name, r_name)] = v1.XAdvance

    pair_map: Dict[Tuple[int, int], Tuple[int, int, int]] = {}
    scale = (size_px * 16.0) / float(upem)
    for (l_name, r_name), fval in raw_pairs.items():
        k_fp4 = int(round(fval * scale))
        if k_fp4 == 0:
            continue
        k_fp4 = max(-127, min(127, k_fp4))
        for l_code in gname_to_codes.get(l_name, []):
            l_adv = code_to_adv_fp4.get(l_code, 0)
            if prune_noop and ((l_adv + k_fp4 + 8) >> 4) == ((l_adv + 8) >> 4):
                continue
            for r_code in gname_to_codes.get(r_name, []):
                l_gid = code_to_gid[l_code]
                r_gid = code_to_gid[r_code]
                pair_map[(l_gid, r_gid)] = (l_code, r_code, k_fp4)

    return [
        (l_gid, r_gid, l_code, r_code, k_fp4)
        for (l_gid, r_gid), (l_code, r_code, k_fp4) in sorted(pair_map.items())
    ]


# =============================================================================
# 6. NATIVE 1-BPP RASTERIZER (AUTOHINT-MONO / BYTECODE-MONO / GRAY-THRESHOLD)
# =============================================================================

def resolve_freetype_flags(raster_mode: str, size_px: int) -> int:
    """
    Resolve FreeType load flags for the selected rasterization engine:
      - 'autohint-mono' (DEFAULT v2.0): FT_LOAD_RENDER | FT_LOAD_FORCE_AUTOHINT | FT_LOAD_TARGET_MONO | FT_LOAD_MONOCHROME
        Symmetric Latin stem grid-fitting + FreeType 1-bit dropout-control scanline converter.
      - 'bytecode-mono': FT_LOAD_RENDER | FT_LOAD_TARGET_MONO | FT_LOAD_MONOCHROME
        Executes embedded TrueType bytecode instructions (fpgm/prep/cvt) + 1-bit dropout control.
      - 'gray-threshold': Legacy 8-bit grayscale thresholding (autohint <= 18px, unhinted > 18px).
    """
    if raster_mode == "exact-mono":
        return FT_LOAD_RENDER | FT_LOAD_NO_HINTING | FT_LOAD_TARGET_MONO | FT_LOAD_MONOCHROME
    if raster_mode == "autohint-mono":
        return FT_LOAD_RENDER | FT_LOAD_FORCE_AUTOHINT | FT_LOAD_TARGET_MONO | FT_LOAD_MONOCHROME
    if raster_mode == "bytecode-mono":
        return FT_LOAD_RENDER | FT_LOAD_TARGET_MONO | FT_LOAD_MONOCHROME
    # gray-threshold fallback
    if size_px <= 18:
        return FT_LOAD_RENDER | FT_LOAD_FORCE_AUTOHINT | FT_LOAD_TARGET_NORMAL
    return FT_LOAD_RENDER | FT_LOAD_NO_AUTOHINT | FT_LOAD_TARGET_NORMAL


HOMOGLYPH_EQUIVALENTS: Dict[int, List[int]] = {
    0x0394: [0x2206],        # Greek Capital Delta <-> Math Increment
    0x2206: [0x0394],
    0x03A9: [0x2126],        # Greek Capital Omega <-> Ohm Sign
    0x2126: [0x03A9],
    0x03BC: [0x00B5],        # Greek Small Mu <-> Micro Sign
    0x00B5: [0x03BC],
    0x2212: [0x002D, 0x2013],# Minus Sign -> Hyphen-Minus / En-Dash
    0x2010: [0x002D],        # Hyphen -> Hyphen-Minus
    0x2011: [0x002D],        # Non-Breaking Hyphen -> Hyphen-Minus
}


def _synthesize_new_line_glyph(size_px: int, gid: int) -> GlyphStrike:
    """Synthesize a crisp 1-BPP LV_SYMBOL_NEW_LINE (U+F8A2, return arrow '↵') glyph at `size_px`."""
    w = max(8, int(round(size_px * 0.75)))
    h = max(8, int(round(size_px * 0.75)))
    stem = 2 if size_px >= 12 else 1
    grid = [["." for _ in range(w)] for _ in range(h)]
    # Vertical right shaft from top (r=0) down to mid-bottom (r=h-3)
    for r in range(0, h - 2):
        for c in range(w - stem, w):
            grid[r][c] = "#"
    # Horizontal bottom bar going left to arrowhead
    bar_r0 = max(2, h - 3 - stem + 1)
    for r in range(bar_r0, bar_r0 + stem):
        for c in range(2, w):
            grid[r][c] = "#"
    # Left-pointing arrowhead at left end of horizontal bar
    mid_r = bar_r0 + (stem // 2)
    arm = max(2, h // 4)
    for d in range(arm + 1):
        for sc in range(stem):
            c_pos = d + sc
            if 0 <= c_pos < w:
                if 0 <= mid_r - d < h:
                    grid[mid_r - d][c_pos] = "#"
                if 0 <= mid_r + d < h:
                    grid[mid_r + d][c_pos] = "#"
    rows = ["".join(r) for r in grid if "#" in r]
    non_empty_c = [c for c in range(len(rows[0])) if any(row[c] == "#" for row in rows)]
    c0, c1 = min(non_empty_c), max(non_empty_c)
    rows = [row[c0 : c1 + 1] for row in rows]
    bw, bh = len(rows[0]), len(rows)
    return GlyphStrike(
        codepoint=0xF8A2,
        glyph_id=gid,
        adv_w_fp4=(bw + 2) * 16,
        box_w=bw,
        box_h=bh,
        ofs_x=1,
        ofs_y=0,
        rows=rows,
        patched=False,
    )


def rasterize_font_strike(
    ft: ctypes.CDLL,
    ft_lib: ctypes.c_void_p,
    font_path: Path,
    size_px: int,
    codepoints: Sequence[int],
    raster_mode: str = "autohint-mono",
    threshold: int = 128,
    fa_path: Optional[Path] = None,
    fa_codepoints: Optional[Sequence[int]] = None,
    patch_dict: Optional[Dict[str, dict]] = None,
    ascii_override_dir: Optional[Path] = None,
    enable_kerning: bool = True,
    prune_noop_kern: bool = True,
    auto_floor: bool = True,
    min_stem: int = 2,
    repair_engine: str = "hybrid",
) -> Tuple[List[GlyphStrike], int, int, int, int, List[Tuple[int, int, int, int, int]]]:
    """
    Rasterize a 1-bpp font strike using FreeType2 + fontTools with optional FontAwesome 5 merge,
    JSON patch manifest overrides, and direct ASCII .txt folder overrides.
    """
    face_ptr = ctypes.POINTER(FT_FaceRec)()
    if ft.FT_New_Face(ft_lib, str(font_path).encode("utf-8"), 0, ctypes.byref(face_ptr)) != 0:
        raise RuntimeError(f"FT_New_Face failed for {font_path}")
    ft.FT_Set_Pixel_Sizes(face_ptr, 0, size_px)

    tt = TTFont(str(font_path))
    cmap = tt.getBestCmap() or {}
    hmtx = tt["hmtx"].metrics
    upem = tt["head"].unitsPerEm
    os2_asc = tt["hhea"].ascent
    os2_desc = tt["hhea"].descent

    ascent_px = int(math.ceil(os2_asc * size_px / float(upem)))
    descent_px = int(math.floor(os2_desc * size_px / float(upem)))
    line_height = ascent_px - descent_px
    base_line = -descent_px

    post_upos = getattr(tt.get("post"), "underlinePosition", -100) if "post" in tt else -100
    post_uthk = getattr(tt.get("post"), "underlineThickness", 50) if "post" in tt else 50
    underline_pos = int(round(post_upos * size_px / float(upem)))
    underline_thick = max(1, int(round(post_uthk * size_px / float(upem))))

    load_flags = resolve_freetype_flags(raster_mode, size_px)

    # Merge any ASCII .txt overrides from ascii_override_dir into effective patch dict
    effective_patches: Dict[str, dict] = {}
    if patch_dict:
        for k, v in patch_dict.items():
            if not isinstance(v, dict):
                continue
            norm_k = ("0x" + k[2:].upper()) if k.upper().startswith("U+") else k
            if norm_k.lower().startswith("0x"):
                norm_k = f"0x{int(norm_k, 16):04X}"
            v_copy = dict(v)
            if "rows" in v_copy and "bitmap" not in v_copy:
                v_copy["bitmap"] = v_copy["rows"]
            if "adv_w" in v_copy and "adv_w_fp4" not in v_copy:
                v_copy["adv_w_fp4"] = int(v_copy["adv_w"]) * 16
            effective_patches[norm_k] = v_copy
    if ascii_override_dir and ascii_override_dir.is_dir():
        parsed_ascii = parse_ascii_glyph_folder(ascii_override_dir, only_modified=True)
        effective_patches.update(parsed_ascii)

    glyphs: List[GlyphStrike] = []
    code_to_gid: Dict[int, int] = {}

    def render_single(f_ptr, t_cmap, t_hmtx, t_upem, code: int, flags: int, gid: int) -> Optional[GlyphStrike]:
        gname = t_cmap.get(code)
        if not gname:
            return None
        gidx = ft.FT_Get_Char_Index(f_ptr, code)
        if gidx == 0:
            return None
        if ft.FT_Load_Glyph(f_ptr, gidx, flags) != 0:
            return None
        slot = f_ptr.contents.glyph.contents
        bmp = slot.bitmap
        adv_fp4 = int(round(t_hmtx[gname][0] * size_px * 16.0 / float(t_upem)))

        raw_rows: List[str] = []
        if bmp.pixel_mode == FT_PIXEL_MODE_MONO:
            for r in range(bmp.rows):
                row_chars = []
                for c in range(bmp.width):
                    byte_val = bmp.buffer[r * bmp.pitch + (c >> 3)]
                    bit = (byte_val >> (7 - (c & 7))) & 1
                    row_chars.append("#" if bit else ".")
                raw_rows.append("".join(row_chars))
        else:
            for r in range(bmp.rows):
                row_chars = []
                for c in range(bmp.width):
                    val = bmp.buffer[r * bmp.pitch + c]
                    row_chars.append("#" if val >= threshold else ".")
                raw_rows.append("".join(row_chars))

        non_empty_r = [i for i, r in enumerate(raw_rows) if "#" in r]
        if not non_empty_r:
            box_w, box_h, ofs_x, ofs_y, trimmed_rows = 0, 0, 0, 0, []
        else:
            r0, r1 = min(non_empty_r), max(non_empty_r)
            trimmed_rows = raw_rows[r0 : r1 + 1]
            non_empty_c = [c for c in range(len(trimmed_rows[0])) if any(row[c] == "#" for row in trimmed_rows)]
            c0, c1 = min(non_empty_c), max(non_empty_c)
            trimmed_rows = [row[c0 : c1 + 1] for row in trimmed_rows]
            box_w = len(trimmed_rows[0])
            box_h = len(trimmed_rows)
            ofs_x = slot.bitmap_left + c0
            ofs_y = (slot.bitmap_top - bmp.rows) + (bmp.rows - 1 - r1)

        is_patched = False
        hex_key = f"0x{code:04X}"
        if hex_key in effective_patches:
            p = effective_patches[hex_key]
            p_rows = list(p["bitmap"])
            if not p_rows or p_rows == ["."]:
                box_w, box_h, ofs_x, ofs_y, trimmed_rows = 0, 0, 0, 0, []
            else:
                box_w = int(p.get("box_w", len(p_rows[0])))
                box_h = int(p.get("box_h", len(p_rows)))
                ofs_x = int(p.get("ofs_x", ofs_x))
                ofs_y = int(p.get("ofs_y", ofs_y))
                if "adv_w_fp4" in p:
                    adv_fp4 = int(p["adv_w_fp4"])
                trimmed_rows = p_rows
            is_patched = True

        # Skip empty 0x0 ligature-anchor stubs on non-space codepoints
        if code != 0x0020 and box_w == 0 and box_h == 0 and not is_patched:
            return None

        return GlyphStrike(
            codepoint=code,
            glyph_id=gid,
            adv_w_fp4=adv_fp4,
            box_w=box_w,
            box_h=box_h,
            ofs_x=ofs_x,
            ofs_y=ofs_y,
            rows=trimmed_rows,
            patched=is_patched,
        )

    # Open optional secondary faces for missing glyphs:
    # - For FontAwesome7-Solid.ttf: fall back to FontAwesome7-Brands.ttf and FontAwesome7-Regular.ttf
    # - For IBMPlexMono / Condensed / Serif: fall back to IBMPlexMath-Regular.ttf and IBMPlexSans-Medium.ttf
    secondary_faces = []
    fdir = font_path.parent
    fname_low = font_path.name.lower()
    is_mono_font = ("mono" in fname_low) or ("terminus" in fname_low) or ("unifont" in fname_low)
    mono_cell_adv_fp4 = None
    if is_mono_font and 0x0030 in cmap:
        mono_cell_adv_fp4 = int(round(hmtx[cmap[0x0030]][0] * size_px * 16.0 / float(upem)))

    sec_candidates: List[Path] = []
    if fname_low.startswith("fontawesome7-"):
        for s_name in ("FontAwesome7-Brands.ttf", "FontAwesome7-Regular.ttf", "FontAwesome7-Solid.ttf"):
            sp = fdir / s_name
            if sp.is_file() and sp.resolve() != font_path.resolve():
                sec_candidates.append(sp)
    elif fname_low.startswith("ibmplex"):
        for s_name in ("IBMPlexSans-Medium.ttf", "IBMPlexMath-Regular.ttf", "IBMPlexSans-Regular.ttf"):
            sp = fdir / s_name
            if sp.is_file() and sp.resolve() != font_path.resolve():
                sec_candidates.append(sp)

    for sp in sec_candidates:
        s_ptr = ctypes.POINTER(FT_FaceRec)()
        if ft.FT_New_Face(ft_lib, str(sp).encode("utf-8"), 0, ctypes.byref(s_ptr)) == 0:
            ft.FT_Set_Pixel_Sizes(s_ptr, 0, size_px)
            s_tt = TTFont(str(sp))
            secondary_faces.append((s_ptr, s_tt.getBestCmap() or {}, s_tt["hmtx"].metrics, s_tt["head"].unitsPerEm))

    # Optional closed-loop auto-floor tuner import
    tuner_mod = None
    if auto_floor and min_stem >= 2 and not fname_low.startswith("terminus-"):
        try:
            import humid1_bilevel_tuner as _bt
            tuner_mod = _bt
        except Exception:
            tuner_mod = None

    next_gid = 1
    for code in sorted(set(codepoints)):
        gs = render_single(face_ptr, cmap, hmtx, upem, code, load_flags, next_gid)
        # 1. Check homoglyph equivalents in primary face if missing
        if gs is None and code in HOMOGLYPH_EQUIVALENTS:
            for alt_cp in HOMOGLYPH_EQUIVALENTS[code]:
                gs_alt = render_single(face_ptr, cmap, hmtx, upem, alt_cp, load_flags, next_gid)
                if gs_alt is not None:
                    gs_alt.codepoint = code
                    gs = gs_alt
                    break
        # 2. Check secondary fallback faces (e.g. FA7 Brands for 0xF287 USB / 0xF294 Bluetooth, or Plex Math/Sans for Mono Greek)
        if gs is None and secondary_faces:
            for s_ptr, s_cmap, s_hmtx, s_upem in secondary_faces:
                gs_sec = render_single(s_ptr, s_cmap, s_hmtx, s_upem, code, load_flags, next_gid)
                if gs_sec is None and code in HOMOGLYPH_EQUIVALENTS:
                    for alt_cp in HOMOGLYPH_EQUIVALENTS[code]:
                        gs_sec = render_single(s_ptr, s_cmap, s_hmtx, s_upem, alt_cp, load_flags, next_gid)
                        if gs_sec is not None:
                            gs_sec.codepoint = code
                            break
                if gs_sec is not None:
                    if mono_cell_adv_fp4 is not None and gs_sec.box_w <= (mono_cell_adv_fp4 >> 4):
                        gs_sec.adv_w_fp4 = mono_cell_adv_fp4
                        cell_px = mono_cell_adv_fp4 >> 4
                        gs_sec.ofs_x = max(0, (cell_px - gs_sec.box_w) // 2)
                    gs = gs_sec
                    break
        # 3. Synthesize LV_SYMBOL_NEW_LINE (0xF8A2) for FontAwesome 7 if requested
        if gs is None and code == 0xF8A2 and fname_low.startswith("fontawesome7-"):
            gs = _synthesize_new_line_glyph(size_px, next_gid)

        # 4. Closed-Loop Auto-Floor (min_stem >= 2px) for <=13px unpatched text glyphs that still have 1px stems
        # (At >=14px, IBMPlex*-Medium wght=500 already renders native 2px stems; at 12px it drops to 1px and is auto-floored here)
        if (
            gs is not None
            and tuner_mod is not None
            and not gs.patched
            and gs.rows
            and size_px <= 13
            and 0x0021 <= code <= 0x03FF
            and not fname_low.startswith(("fontawesome", "lucide", "phosphor", "tabler"))
        ):
            w_orig = gs.box_w
            arr = tuner_mod.rows_to_binary_array(gs.rows)
            max_w = (gs.adv_w_fp4 >> 4) if is_mono_font else ((gs.adv_w_fp4 >> 4) + 2)
            rep_arr, rec = tuner_mod.inspect_and_repair_glyph_bitmap(
                arr,
                codepoint=code,
                min_stem=min_stem,
                max_width_ceiling=max_w,
                engine=repair_engine,
            )
            if rec.repaired and not rec.size_floor_warning:
                trimmed, bw, bh, nox, noy = tuner_mod.trim_binary_array(rep_arr, gs.ofs_x, gs.ofs_y)
                if bw > 0 and bh > 0:
                    gs.rows = tuner_mod.binary_array_to_rows(trimmed)
                    gs.box_w = bw
                    gs.box_h = bh
                    gs.ofs_x = nox
                    gs.ofs_y = noy
                    if not is_mono_font and bw > w_orig:
                        gs.adv_w_fp4 += (bw - w_orig) * 16

        if gs is not None:
            glyphs.append(gs)
            code_to_gid[code] = next_gid
            next_gid += 1

    for s_ptr, _, _, _ in secondary_faces:
        ft.FT_Done_Face(s_ptr)

    if fa_path and fa_path.is_file() and fa_codepoints:
        fa_face_ptr = ctypes.POINTER(FT_FaceRec)()
        if ft.FT_New_Face(ft_lib, str(fa_path).encode("utf-8"), 0, ctypes.byref(fa_face_ptr)) == 0:
            ft.FT_Set_Pixel_Sizes(fa_face_ptr, 0, size_px)
            fa_tt = TTFont(str(fa_path))
            fa_cmap = fa_tt.getBestCmap() or {}
            fa_hmtx = fa_tt["hmtx"].metrics
            fa_upem = fa_tt["head"].unitsPerEm
            fa_flags = FT_LOAD_RENDER | FT_LOAD_FORCE_AUTOHINT | FT_LOAD_TARGET_MONO | FT_LOAD_MONOCHROME
            for code in sorted(set(fa_codepoints)):
                if code in code_to_gid:
                    continue
                gs = render_single(fa_face_ptr, fa_cmap, fa_hmtx, fa_upem, code, fa_flags, next_gid)
                if gs is not None:
                    glyphs.append(gs)
                    code_to_gid[code] = next_gid
                    next_gid += 1
            ft.FT_Done_Face(fa_face_ptr)

    glyphs.sort(key=lambda g: g.codepoint)
    code_to_gid.clear()
    code_to_adv: Dict[int, int] = {}
    for idx, g in enumerate(glyphs, start=1):
        g.glyph_id = idx
        code_to_gid[g.codepoint] = idx
        code_to_adv[g.codepoint] = g.adv_w_fp4

    max_top = ascent_px
    min_bot = descent_px
    for g in glyphs:
        if g.box_h > 0:
            max_top = max(max_top, g.ofs_y + g.box_h)
            min_bot = min(min_bot, g.ofs_y)
    line_height = max_top - min_bot
    base_line = -min_bot

    kern_pairs = (
        extract_kerning_pairs_fp4(tt, size_px, code_to_gid, code_to_adv, prune_noop=prune_noop_kern)
        if enable_kerning
        else []
    )
    ft.FT_Done_Face(face_ptr)

    return glyphs, line_height, base_line, underline_pos, underline_thick, kern_pairs


# =============================================================================
# 7. WORKFLOW 2: PATCH (FULL-CANVAS 1:1 SPACED ASCII + UNICODE PREVIEW <-> JSON)
# =============================================================================

def dump_strike_to_ascii_folder(
    strike_dir: Path,
    font_symbol_name: str,
    glyphs: Sequence[GlyphStrike],
    size_px: int = 16,
    line_height: int = 22,
    base_line: int = 5,
    trouble_only: bool = False,
    unicode_preview: bool = False,
    family: str = "",
) -> int:
    """
    Export glyphs of a strike into a named folder (`strike_dir`) of named ASCII .txt files
    using the v3.0 Full-Canvas 1:1 Spaced ASCII + UTF-8 Unicode Silhouette format:
      1. Plots the glyph inside its full vertical (y = +ascender down to y = descender)
         and horizontal (x = min(0, ofs_x) .. max(adv_px, ofs_x + box_w)) cell canvas
         so characters like '_' (underscore), '.' (period), '-' (hyphen), and quote
         show their exact visual position relative to CAP_HEIGHT, X_HEIGHT, and BASELINE (y=0).
      2. Includes a UTF-8 Unicode 1:1 Block Preview ('██' for ink, '··' for canvas, '──' for baseline)
         in the header comment block for instant visual recognition in Notepad++, VS Code, and Windows Notepad.
      3. Uses 2-character-per-pixel horizontal spacing ('# ' for ink ON, '. ' for canvas OFF,
         '- ' for empty baseline pixels) in the editable grid below '---' so monospace editors
         render the editable ASCII grid at a true 1:1 square aspect ratio.
    """
    strike_dir.mkdir(parents=True, exist_ok=True)
    exported = 0
    asc_y = line_height - base_line
    desc_y = -base_line
    cap_y = int(round(size_px * 0.698))
    xh_y = int(round(size_px * 0.516))

    for g in glyphs:
        if g.codepoint == 0:
            continue
        if trouble_only and g.codepoint not in TROUBLE_15_CODEPOINTS:
            continue
        fname = safe_glyph_filename(g.codepoint, family)
        fpath = strike_dir / fname
        char_disp = chr(g.codepoint) if 0x20 <= g.codepoint <= 0x7E else f"U+{g.codepoint:04X}"
        adv_px = max(1, (g.adv_w_fp4 + 8) >> 4)

        matrix_lines = g.rows if (g.box_w > 0 and g.box_h > 0 and g.rows) else []
        orig_sig = f"{g.box_w},{g.box_h},{g.ofs_x},{g.ofs_y}|" + ("/".join(matrix_lines) if matrix_lines else ".")

        # Full canvas horizontal and vertical span
        canvas_x0 = min(0, g.ofs_x) if g.box_w > 0 else 0
        canvas_x1 = max(adv_px, (g.ofs_x + g.box_w) if g.box_w > 0 else adv_px, 1)
        canvas_w = canvas_x1 - canvas_x0

        glyph_y_top = (g.ofs_y + g.box_h - 1) if g.box_h > 0 else -9999
        glyph_y_bot = g.ofs_y if g.box_h > 0 else 9999
        y_top = max(asc_y, glyph_y_top if g.box_h > 0 else asc_y)
        y_bot = min(desc_y, glyph_y_bot if g.box_h > 0 else desc_y)

        # Build column ruler header:
        # Note: "# x: " is exactly 5 characters, so each grid row below starts with
        #       exactly 5 spaces ("     ") so column 0 aligns to the exact character column!
        col_nums = " ".join(f"{abs(canvas_x0 + c) % 10}" for c in range(canvas_w))

        unicode_preview_lines: List[str] = [
            f"# x: {col_nums}"
        ]
        editable_canvas_lines: List[str] = []
        if canvas_x0 < 0:
            sign_marks = " ".join("-" if (canvas_x0 + c) < 0 else " " for c in range(canvas_w))
            editable_canvas_lines.append(f"# ±: {sign_marks}")
        editable_canvas_lines.append(f"# x: {col_nums}")

        for y in range(y_top, y_bot - 1, -1):
            u_row: List[str] = []
            a_row: List[str] = []
            for c in range(canvas_w):
                x = canvas_x0 + c
                is_ink = False
                if g.box_w > 0 and g.box_h > 0:
                    if g.ofs_x <= x < (g.ofs_x + g.box_w) and glyph_y_bot <= y <= glyph_y_top:
                        r_idx = glyph_y_top - y
                        c_idx = x - g.ofs_x
                        if 0 <= r_idx < len(g.rows) and 0 <= c_idx < len(g.rows[r_idx]):
                            is_ink = (g.rows[r_idx][c_idx] == "#")
                if is_ink:
                    u_row.append("██")
                    a_row.append("# ")
                elif y == 0:
                    u_row.append("──")
                    a_row.append("- ")
                else:
                    u_row.append("··")
                    a_row.append(". ")

            # Right-hand typographic landmark tag
            tags: List[str] = []
            if y == 0:
                tags.append("<-- BASELINE (y=0)")
            elif y == cap_y:
                tags.append("(CAP_HEIGHT)")
            elif y == xh_y:
                tags.append("(X_HEIGHT)")
            elif y == asc_y:
                tags.append("(ASCENDER)")
            elif y == desc_y:
                tags.append("(DESCENDER)")
            tag_str = (" " + " ".join(tags)) if tags else ""

            unicode_preview_lines.append(f"#    {''.join(u_row)} | y={y:+03d}{tag_str}")
            editable_canvas_lines.append(f"     {''.join(a_row)} | y={y:+03d}{tag_str}")

        opt_unicode_block = (
            [
                "# UNICODE 1:1 SILHOUETTE PREVIEW (Opt-in via --unicode-preview):",
                *unicode_preview_lines,
                "# ==============================================================================",
            ]
            if unicode_preview
            else []
        )
        lines = [
            "# ==============================================================================",
            "# Humidyne Labs — 1-BPP Full-Canvas ASCII Glyph Patch File (v4.0)",
            f"# Strike Symbol : {font_symbol_name} ({size_px}px, line_height={line_height}, base_line={base_line})",
            f"# Codepoint     : 0x{g.codepoint:04X} ({char_disp}) [{fname[:-4]}]",
            f"# Metrics       : adv_w={adv_px}px (fp4={g.adv_w_fp4}) | bbox: w={g.box_w}, h={g.box_h}, ofs_x={g.ofs_x}, ofs_y={g.ofs_y}",
            f"# Patched State : {'YES' if g.patched else 'BASELINE'}",
            f"# orig_signature: {orig_sig}",
            "# ==============================================================================",
            *opt_unicode_block,
            "# EDITABLE 1:1 SPACED ASCII CANVAS",
            "# Legend: '# ' = Ink ON  |  '. ' = Canvas OFF  |  '- ' = Baseline (y=0) OFF",
            "# Note  : Place '#' anywhere on the canvas! box_w, box_h, ofs_x, and ofs_y",
            "#         auto-recalculate relative to x=0 and BASELINE (y=0) on compile.",
            "# ==============================================================================",
            "grid_mode: full_canvas",
            f"canvas_x0: {canvas_x0}",
            f"canvas_y_top: {y_top}",
            f"canvas_y_bot: {y_bot}",
            f"adv_w_fp4: {g.adv_w_fp4}",
            f"box_w: {g.box_w}",
            f"box_h: {g.box_h}",
            f"ofs_x: {g.ofs_x}",
            f"ofs_y: {g.ofs_y}",
            "---",
            *editable_canvas_lines,
        ]
        fpath.write_text("\n".join(lines) + "\n", encoding="utf-8")
        exported += 1
    return exported


def parse_ascii_glyph_folder(strike_dir: Path, only_modified: bool = False) -> Dict[str, dict]:
    """
    Parse all `U+*.txt` ASCII glyph files inside `strike_dir` and return a dict keyed by `"0xXXXX"`.
    Supports both v3.0 `grid_mode: full_canvas` (2-char spaced '# ' / '. ' / '- ' with auto-bounding-box
    extraction relative to x=0 and y=0) and legacy v2.0 cropped matrices.
    """
    patches: Dict[str, dict] = {}
    if not strike_dir.is_dir():
        return patches

    for tf in sorted(strike_dir.glob("U+*.txt")):
        m = re.search(r"U\+([0-9A-Fa-f]{4,6})", tf.name)
        if not m:
            continue
        code = int(m.group(1), 16)
        hex_key = f"0x{code:04X}"
        raw_lines = tf.read_text(encoding="utf-8").splitlines()

        meta: Dict[str, str] = {}
        orig_sig: Optional[str] = None
        was_patched = False
        grid_raw_lines: List[str] = []
        in_matrix = False

        for raw_line in raw_lines:
            s = raw_line.strip()
            if not s:
                continue
            if not in_matrix:
                if s == "---":
                    in_matrix = True
                    continue
                if s.startswith("#"):
                    if s.startswith("# orig_signature:"):
                        orig_sig = s.split(":", 1)[1].strip()
                    elif s.startswith("# Patched State :") and "YES" in s:
                        was_patched = True
                    continue
                if ":" in s:
                    k, v = s.split(":", 1)
                    meta[k.strip().lower()] = v.strip()
            else:
                if raw_line.startswith("#") or s.startswith("# x:") or s.startswith("# ±:"):
                    continue
                grid_raw_lines.append(raw_line)

        if not grid_raw_lines:
            continue

        grid_mode = meta.get("grid_mode", "cropped").lower()
        canvas_x0 = int(meta.get("canvas_x0", "0"))
        canvas_y_top = int(meta.get("canvas_y_top", "0"))

        parsed_rows: List[str] = []
        row_y_coords: List[int] = []

        for idx, rline in enumerate(grid_raw_lines):
            y_val = canvas_y_top - idx
            if "|" in rline:
                left_part, right_part = rline.split("|", 1)
                m_y = re.search(r"y=\s*([+-]?\d+)", right_part)
                if m_y:
                    y_val = int(m_y.group(1))
            else:
                left_part = rline

            chars = left_part.strip()
            bits: List[str] = []
            if " " in chars:
                for tok in chars.split():
                    if tok.startswith("#") or tok.startswith("█") or tok == "1":
                        bits.append("#")
                    elif tok.startswith(".") or tok.startswith("-") or tok.startswith("·") or tok.startswith("─") or tok == "0":
                        bits.append(".")
            else:
                for ch in chars:
                    if ch in ("#", "█", "1"):
                        bits.append("#")
                    elif ch in (".", "-", "·", "─", "0"):
                        bits.append(".")
            if bits:
                parsed_rows.append("".join(bits))
                row_y_coords.append(y_val)

        if not parsed_rows:
            continue

        if grid_mode == "full_canvas":
            min_c, max_c = 999999, -1
            min_r, max_r = 999999, -1
            for r_i, r_str in enumerate(parsed_rows):
                for c_i, ch in enumerate(r_str):
                    if ch == "#":
                        if c_i < min_c: min_c = c_i
                        if c_i > max_c: max_c = c_i
                        if r_i < min_r: min_r = r_i
                        if r_i > max_r: max_r = r_i
            if max_c < 0:
                box_w, box_h, ofs_x, ofs_y = 0, 0, 0, 0
                cropped_matrix: List[str] = ["."]
            else:
                box_w = (max_c - min_c) + 1
                box_h = (max_r - min_r) + 1
                ofs_x = canvas_x0 + min_c
                ofs_y = row_y_coords[max_r]
                cropped_matrix = [parsed_rows[r][min_c : max_c + 1] for r in range(min_r, max_r + 1)]
        else:
            if parsed_rows == ["."]:
                box_w, box_h = 0, 0
                cropped_matrix = ["."]
            else:
                box_w = len(parsed_rows[0])
                box_h = len(parsed_rows)
                cropped_matrix = parsed_rows
            ofs_x = int(meta.get("ofs_x", "0"))
            ofs_y = int(meta.get("ofs_y", "0"))

        sig_rows = "." if cropped_matrix == ["."] else "/".join(cropped_matrix)
        curr_sig = f"{box_w},{box_h},{ofs_x},{ofs_y}|{sig_rows}"
        if only_modified and orig_sig is not None and curr_sig == orig_sig and not was_patched:
            continue

        entry: dict = {
            "char": chr(code) if 0x20 <= code <= 0x7E else f"U+{code:04X}",
            "box_w": box_w,
            "box_h": box_h,
            "ofs_x": ofs_x,
            "ofs_y": ofs_y,
            "bitmap": [] if cropped_matrix == ["."] else cropped_matrix,
        }
        if "adv_w_fp4" in meta:
            entry["adv_w_fp4"] = int(meta["adv_w_fp4"])
        patches[hex_key] = entry

    return patches


def build_patches_json_from_ascii_root(
    ascii_root_dir: Path,
    out_json_path: Path,
    only_modified: bool = True,
) -> int:
    """
    Scan all `<ascii_root_dir>/<strike_symbol>/` subdirectories, compile modified (or all)
    `U+*.txt` files, and merge them into `out_json_path` (`font_icon_epd_patches.json`).
    """
    manifest: dict = {
        "$schema": "https://humidyne-labs.github.io/schemas/plex_epd_patches_v3.json",
        "version": "3.0.0",
        "description": "Declarative 1-bpp optical bitmap overrides compiled from v3.0 Full-Canvas ASCII glyph folders.",
        "patches": {},
    }
    if out_json_path.is_file():
        try:
            loaded = json.loads(out_json_path.read_text(encoding="utf-8"))
            if "patches" in loaded:
                manifest = loaded
            else:
                # Normalize top-level strike keys into manifest["patches"]
                for k, v in loaded.items():
                    if not k.startswith("_") and isinstance(v, dict):
                        manifest["patches"][k] = v
        except Exception:
            pass

    total_compiled = 0
    if not ascii_root_dir.is_dir():
        return 0

    subdirs = [d for d in sorted(ascii_root_dir.iterdir()) if d.is_dir()]
    if not subdirs and list(ascii_root_dir.glob("U+*.txt")):
        subdirs = [ascii_root_dir]

    for sdir in subdirs:
        sym_name = sdir.name
        parsed = parse_ascii_glyph_folder(sdir, only_modified=only_modified)
        if parsed:
            manifest["patches"].setdefault(sym_name, {}).update(parsed)
            total_compiled += len(parsed)

    out_json_path.parent.mkdir(parents=True, exist_ok=True)
    out_json_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return total_compiled


# =============================================================================
# 8. WORKFLOW 3: CHECK (AUTO-WRAPPED PAGE CHECK PNGS & CHAR-BY-CHAR BLUEPRINTS)
# =============================================================================

_UI_FONTS_CACHE: Dict[str, dict] = {}

def _load_ui_fonts(static_dir: Optional[Path] = None):
    """Load crisp TrueType UI fonts from static_ttfs/ (cached in memory per worker process)."""
    cache_key = str(static_dir) if static_dir else "default"
    if cache_key in _UI_FONTS_CACHE:
        return _UI_FONTS_CACHE[cache_key]
    from PIL import ImageFont
    candidates = []
    if static_dir:
        candidates.append(static_dir)
    candidates.append(Path("/tmp/plex_v2_extracted/ibm_plex_epd_toolchain_v2.0/tools/fonts/static_assets"))

    sans_bold = None
    sans_reg = None
    mono_reg = None
    for d in candidates:
        if (d / "IBMPlexSans-Bold.ttf").is_file():
            sans_bold = str(d / "IBMPlexSans-Bold.ttf")
            sans_reg = str(d / "IBMPlexSans-Regular.ttf")
            mono_reg = str(d / "IBMPlexMono-Regular.ttf")
            break

    try:
        if sans_bold and mono_reg:
            res = {
                "title": ImageFont.truetype(sans_bold, 18),
                "subtitle": ImageFont.truetype(sans_reg, 13),
                "section": ImageFont.truetype(sans_bold, 14),
                "label": ImageFont.truetype(sans_bold, 13),
                "mono": ImageFont.truetype(mono_reg, 12),
                "mono_sm": ImageFont.truetype(mono_reg, 11),
                "mono_lg": ImageFont.truetype(mono_reg, 14),
            }
            _UI_FONTS_CACHE[cache_key] = res
            return res
    except Exception:
        pass
    default_f = ImageFont.load_default()
    return {k: default_f for k in ("title", "subtitle", "section", "label", "mono", "mono_sm", "mono_lg")}


MAX_GLYPHS_PER_PNG_PAGE = 256

def render_full_font_inspection_png(
    out_png: Path,
    font_symbol_name: str,
    family: str,
    role: str,
    size_px: int,
    raster_mode: str,
    line_height: int,
    base_line: int,
    glyphs: Sequence[GlyphStrike],
    rom_bytes: int,
    static_dir: Optional[Path] = None,
) -> int:
    valid_all = [g for g in glyphs if g.codepoint > 0]
    if len(valid_all) > MAX_GLYPHS_PER_PNG_PAGE:
        total_pages = int(math.ceil(len(valid_all) / float(MAX_GLYPHS_PER_PNG_PAGE)))
        for p_idx in range(total_pages):
            chunk = valid_all[p_idx * MAX_GLYPHS_PER_PNG_PAGE : (p_idx + 1) * MAX_GLYPHS_PER_PNG_PAGE]
            cp_start = chunk[0].codepoint
            cp_end = chunk[-1].codepoint
            page_png = out_png.parent / f"{font_symbol_name}_p{p_idx+1:02d}_of_{total_pages:02d}_U+{cp_start:04X}-U+{cp_end:04X}.png"
            _render_single_page_inspection_png(
                out_png=page_png,
                font_symbol_name=f"{font_symbol_name} [Page {p_idx+1}/{total_pages}: U+{cp_start:04X}..U+{cp_end:04X}]",
                family=family,
                role=role,
                size_px=size_px,
                raster_mode=raster_mode,
                line_height=line_height,
                base_line=base_line,
                glyphs=chunk,
                rom_bytes=rom_bytes,
                static_dir=static_dir,
            )
        return total_pages
    _render_single_page_inspection_png(
        out_png=out_png,
        font_symbol_name=font_symbol_name,
        family=family,
        role=role,
        size_px=size_px,
        raster_mode=raster_mode,
        line_height=line_height,
        base_line=base_line,
        glyphs=valid_all,
        rom_bytes=rom_bytes,
        static_dir=static_dir,
    )
    return 1


def _render_single_page_inspection_png(
    out_png: Path,
    font_symbol_name: str,
    family: str,
    role: str,
    size_px: int,
    raster_mode: str,
    line_height: int,
    base_line: int,
    glyphs: Sequence[GlyphStrike],
    rom_bytes: int,
    static_dir: Optional[Path] = None,
) -> None:
    """
    Render a crisp, minimal, auto-wrapped Page Check PNG (`inspect_pages/<strike_symbol>.png`):
      1. Specimen strings automatically word-wrap within the safe page width so large fonts
         (24px, 32px, 36px, 48px) never clip off the right edge or collide with the status badge.
      2. Uses crisp TrueType vector typography for all cell headers and metric tags (zero bitmap blur).
      3. Renders each glyph cell at high integer pixel zoom (6x for <=16px, 5x for 18-20px, 4x for 24-32px)
         inside its full vertical frame with color-coded Cap-Height, X-Height, and Baseline guides.
    """
    from PIL import Image, ImageDraw

    ui_fonts = _load_ui_fonts(static_dir)
    valid_glyphs = [g for g in glyphs if g.codepoint > 0]
    n_glyphs = len(valid_glyphs)

    zoom = 6 if size_px <= 16 else (5 if size_px <= 20 else (4 if size_px <= 28 else 3))
    cols = 10 if size_px <= 20 else 8
    grid_rows = int(math.ceil(n_glyphs / float(cols)))

    cell_w = max(136, size_px * zoom + 44)
    cell_h = max(128, line_height * zoom + 56)
    W = max(1420, cols * cell_w + 48)

    gmap = {g.codepoint: g for g in valid_glyphs}
    asc_y = line_height - base_line
    cap_y = int(round(size_px * 0.698))
    xh_y = int(round(size_px * 0.516))

    def measure_strike_word(word: str, scale: int = 1) -> int:
        w = 0
        for ch in word:
            g = gmap.get(ord(ch))
            w += (((g.adv_w_fp4 + 8) >> 4) if g else (size_px // 2)) * scale
        return w

    def wrap_strike_lines(text: str, max_w: int, scale: int = 1) -> List[str]:
        words = text.split(" ")
        lines_out: List[str] = []
        cur = ""
        for word in words:
            cand = (cur + " " + word).strip() if cur else word
            if measure_strike_word(cand, scale) <= max_w:
                cur = cand
            else:
                if cur:
                    lines_out.append(cur)
                # If a single word is wider than max_w, split character-by-character
                if measure_strike_word(word, scale) > max_w:
                    chunk = ""
                    for ch in word:
                        if measure_strike_word(chunk + ch, scale) <= max_w:
                            chunk += ch
                        else:
                            if chunk:
                                lines_out.append(chunk)
                            chunk = ch
                    cur = chunk
                else:
                    cur = word
        if cur:
            lines_out.append(cur)
        return lines_out

    is_icon_strike = family.startswith("icon_") or (ord("A") not in gmap)
    if is_icon_strike:
        icon_chars = [chr(g.codepoint) for g in valid_glyphs]
        s1_text = " ".join(icon_chars[:32])
        s2_text = " ".join(icon_chars[:18])
        pill_sample = " ".join(icon_chars[:6])
        pill_w = max(210, measure_strike_word(pill_sample, scale=1) + 32)
    else:
        s1_text = "ABCDEFGHIJKLM abcdefghijklm 0123456789 @%#$&80_easy | 72.4°F 46.8%RH 9.3g/m³ ΔT+0.1°C"
        s2_text = "HUMIDYNE 72.4°F 46.8% @%#$&80_easy"
        pill_sample = "AWAKE 1/5 • 99%"
        pill_w = max(210, measure_strike_word(pill_sample, scale=1) + 28)
    safe_s1_w = W - 260 - pill_w - 36
    safe_s2_w = W - 260 - 24

    s1_lines = wrap_strike_lines(s1_text, safe_s1_w, scale=1)
    s2_lines = wrap_strike_lines(s2_text, safe_s2_w, scale=2)

    s1_block_h = max(32, len(s1_lines) * (line_height + 4))
    s2_block_h = max(44, len(s2_lines) * (line_height * 2 + 6))
    header_h = 84 + s1_block_h + s2_block_h + 38
    H = header_h + grid_rows * cell_h + 36

    img = Image.new("RGB", (W, H), (244, 246, 250))
    draw = ImageDraw.Draw(img)

    def draw_strike_line(x0: int, y0: int, text: str, scale: int = 1, fg=(12, 16, 22)) -> int:
        cx = x0
        by = y0 + (line_height - base_line) * scale
        for ch in text:
            g = gmap.get(ord(ch))
            if not g:
                cx += (size_px // 2) * scale
                continue
            if g.box_w > 0 and g.box_h > 0:
                gx0 = cx + g.ofs_x * scale
                gy0 = by - (g.ofs_y + g.box_h) * scale
                for r_i, r_s in enumerate(g.rows):
                    for c_i, px in enumerate(r_s):
                        if px == "#":
                            if scale == 1:
                                draw.point((gx0 + c_i, gy0 + r_i), fill=fg)
                            else:
                                draw.rectangle(
                                    [
                                        gx0 + c_i * scale,
                                        gy0 + r_i * scale,
                                        gx0 + (c_i + 1) * scale - 1,
                                        gy0 + (r_i + 1) * scale - 1,
                                    ],
                                    fill=fg,
                                )
            cx += ((g.adv_w_fp4 + 8) >> 4) * scale
        return cx

    # Top Title Bar
    draw.rectangle([0, 0, W, 60], fill=(16, 22, 31))
    draw.text(
        (24, 10),
        f"HUMIDYNE LABS PAGE CHECK  |  {font_symbol_name}  ({family.upper()} {role.upper()} {size_px}px)",
        fill=(255, 255, 255),
        font=ui_fonts["title"],
    )
    patched_cnt = sum(1 for g in valid_glyphs if g.patched)
    pt_96 = size_px * 72.0 / 96.0
    pt_188 = size_px * 72.0 / 188.3
    draw.text(
        (24, 34),
        f"Em: {size_px}px ({pt_96:.1f}pt@96dpi / {pt_188:.1f}pt@188dpi)  |  LineHt: {line_height}px (Asc:+{asc_y} Base:-{base_line})  |  Glyphs: {n_glyphs} ({patched_cnt} patched)  |  Mode: {raster_mode}  |  ROM: {rom_bytes:,} B ({rom_bytes/1024:.2f} KB)",
        fill=(176, 196, 218),
        font=ui_fonts["subtitle"],
    )

    # Auto-Wrapped Specimen Strip Card
    draw.rectangle([24, 72, W - 24, header_h - 14], fill=(255, 255, 255), outline=(202, 210, 222), width=1)
    y_cursor = 84
    draw.text((38, y_cursor + 2), "1:1 Native (188 DPI):", fill=(85, 98, 114), font=ui_fonts["label"])

    # Inverted EPD Badge on top-right (never overlapped because safe_s1_w reserves space)
    pill_h = max(30, line_height + 10)
    px0, py0 = W - 24 - pill_w - 14, 82
    draw.rectangle([px0, py0, px0 + pill_w, py0 + pill_h], fill=(14, 18, 24))
    draw_strike_line(px0 + 12, py0 + 5, pill_sample, scale=1, fg=(255, 255, 255))

    for ln in s1_lines:
        draw_strike_line(220, y_cursor, ln, scale=1, fg=(12, 16, 22))
        y_cursor += line_height + 4

    y_cursor += 8
    draw.line([(38, y_cursor - 4), (W - 38, y_cursor - 4)], fill=(232, 236, 242), width=1)
    draw.text((38, y_cursor + 4), "2x Nearest-Neighbor:", fill=(85, 98, 114), font=ui_fonts["label"])
    for ln in s2_lines:
        draw_strike_line(220, y_cursor, ln, scale=2, fg=(12, 16, 22))
        y_cursor += line_height * 2 + 6

    # Glyph Cell Matrix Grid
    for idx, g in enumerate(valid_glyphs):
        r_idx = idx // cols
        c_idx = idx % cols
        cx0 = 24 + c_idx * cell_w
        cy0 = header_h + r_idx * cell_h
        cx1 = cx0 + cell_w - 8
        cy1 = cy0 + cell_h - 8

        border_col = (20, 135, 95) if g.patched else (206, 214, 224)
        bg_col = (242, 252, 248) if g.patched else (255, 255, 255)
        draw.rectangle([cx0, cy0, cx1, cy1], fill=bg_col, outline=border_col, width=2 if g.patched else 1)

        if 0x20 <= g.codepoint <= 0x7E:
            ch_label = chr(g.codepoint)
        else:
            sem_n = get_semantic_glyph_name(g.codepoint, family)
            ch_label = sem_n[:8] if not sem_n.startswith("uni") else ""
        draw.text((cx0 + 7, cy0 + 5), f"U+{g.codepoint:04X} {ch_label}", fill=(24, 32, 44), font=ui_fonts["label"])
        adv_px = (g.adv_w_fp4 + 8) >> 4
        draw.text(
            (cx0 + 7, cy1 - 19),
            f"w{g.box_w}x{g.box_h} o({g.ofs_x},{g.ofs_y}) a{adv_px}",
            fill=(95, 108, 124),
            font=ui_fonts["mono_sm"],
        )

        # 1:1 native preview in top-right of cell
        if g.box_w > 0 and g.box_h > 0:
            nx0 = cx1 - g.box_w - 8
            ny0 = cy0 + 7
            for rr, r_str in enumerate(g.rows):
                for cc, px in enumerate(r_str):
                    if px == "#":
                        draw.point((nx0 + cc, ny0 + rr), fill=(12, 16, 22))

        # Full em-cell reference lines inside cell
        grid_top = cy0 + 26
        baseline_y = grid_top + asc_y * zoom
        cap_line_y = baseline_y - cap_y * zoom
        xh_line_y = baseline_y - xh_y * zoom

        if cy0 + 24 < cap_line_y < cy1 - 22:
            draw.line([(cx0 + 6, cap_line_y), (cx1 - 6, cap_line_y)], fill=(215, 232, 242), width=1)
        if cy0 + 24 < xh_line_y < cy1 - 22:
            draw.line([(cx0 + 6, xh_line_y), (cx1 - 6, xh_line_y)], fill=(228, 220, 242), width=1)
        if cy0 + 24 < baseline_y < cy1 - 22:
            draw.line([(cx0 + 6, baseline_y), (cx1 - 6, baseline_y)], fill=(225, 130, 130), width=1)

        if g.box_w > 0 and g.box_h > 0:
            gx0 = cx0 + max(8, (cell_w - 8 - g.box_w * zoom) // 2)
            gy0 = baseline_y - (g.ofs_y + g.box_h) * zoom
            gy0 = max(cy0 + 24, min(cy1 - 22 - g.box_h * zoom, gy0))
            for rr, r_str in enumerate(g.rows):
                for cc, px in enumerate(r_str):
                    rx = gx0 + cc * zoom
                    ry = gy0 + rr * zoom
                    if px == "#":
                        draw.rectangle([rx, ry, rx + zoom - 1, ry + zoom - 1], fill=(14, 18, 24))
                    elif zoom >= 4:
                        draw.rectangle([rx, ry, rx + zoom - 1, ry + zoom - 1], outline=(234, 238, 244))

    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out_png))


def render_single_char_inspection_png(
    out_png: Path,
    font_symbol_name: str,
    family: str,
    role: str,
    size_px: int,
    raster_mode: str,
    line_height: int,
    base_line: int,
    g: GlyphStrike,
    gmap: Dict[int, GlyphStrike],
    static_dir: Optional[Path] = None,
) -> None:
    """
    Render a dedicated, high-resolution Char-by-Char Engineering Blueprint PNG
    (`inspect_chars/<strike_symbol>/U+XXXX_<name>.png`):
      - Uses 18x-22x integer pixel zoom on the full coordinate grid so viewing at 100%
        in Windows Photos / macOS Preview has ZERO bilinear blur.
      - Plots the glyph inside its full vertical (y = +ascender .. -descender) and
        horizontal (x = min(0, ofs_x)-1 .. max(adv_px, ofs_x+box_w)+1) coordinate grid
        with explicit X/Y pixel rulers and color-coded typographic reference lines:
          * ASCENDER (slate)
          * CAP_HEIGHT (teal)
          * X_HEIGHT (purple)
          * BASELINE y=0 (crimson, 2px)
          * DESCENDER (amber)
          * ORIGIN x=0 & ADVANCE WIDTH x=adv_w (blue vertical markers)
      - Right sidebar includes:
          1. 1:1, 2x, and 4x solid previews (Normal White-Paper & Inverted Black-Paper).
          2. Live 4x Context Word Preview ('H [char] p' and '0 [char] 0') on the baseline
             so punctuation like '_' (underscore), '.' (period), and '-' (hyphen) are
             visually anchored against capital H, lowercase p descender, and digits.
          3. Complete LVGL v9 `lv_font_fmt_txt_glyph_dsc_t` metric & C hex byte dump table.
    """
    from PIL import Image, ImageDraw

    ui_fonts = _load_ui_fonts(static_dir)
    asc_y = line_height - base_line
    desc_y = -base_line
    cap_y = int(round(size_px * 0.698))
    xh_y = int(round(size_px * 0.516))
    adv_px = max(1, (g.adv_w_fp4 + 8) >> 4)

    glyph_y_top = (g.ofs_y + g.box_h - 1) if g.box_h > 0 else -9999
    glyph_y_bot = g.ofs_y if g.box_h > 0 else 9999
    y_top = max(asc_y + 1, (glyph_y_top + 1) if g.box_h > 0 else asc_y + 1)
    y_bot = min(desc_y - 1, (glyph_y_bot - 1) if g.box_h > 0 else desc_y - 1)
    total_rows = y_top - y_bot + 1

    x_left = min(-1, g.ofs_x - 1) if g.box_w > 0 else -1
    x_right = max(adv_px + 1, (g.ofs_x + g.box_w) if g.box_w > 0 else adv_px + 1)
    total_cols = x_right - x_left + 1

    # Choose integer pixel zoom so grid fits cleanly in ~560x620 px
    zoom = max(12, min(24, int(min(520 // max(total_cols, 1), 580 // max(total_rows, 1)))))

    grid_w = total_cols * zoom
    grid_h = total_rows * zoom
    left_panel_w = max(640, grid_w + 180)
    right_panel_w = 440
    W = left_panel_w + right_panel_w + 36
    H = max(760, grid_h + 150)

    img = Image.new("RGB", (W, H), (244, 246, 250))
    draw = ImageDraw.Draw(img)

    char_disp = chr(g.codepoint) if 0x20 <= g.codepoint <= 0x7E else f"U+{g.codepoint:04X}"
    gname = get_semantic_glyph_name(g.codepoint, family)

    # Top Title Banner
    draw.rectangle([0, 0, W, 62], fill=(16, 22, 31))
    draw.text(
        (24, 10),
        f"CHAR-BY-CHAR DEEP INSPECTOR  |  {font_symbol_name}  |  U+{g.codepoint:04X} ({char_disp!r}) [{gname}]",
        fill=(255, 255, 255),
        font=ui_fonts["title"],
    )
    state_str = "PATCHED (Custom Override)" if g.patched else "BASELINE (FreeType2 autohint-mono)"
    draw.text(
        (24, 35),
        f"State: {state_str}   |   Strike: {size_px}px (LineHeight: {line_height}px, Base: {base_line}px)   |   Grid Scale: {zoom}x Integer Zoom (Zero Blur)",
        fill=(176, 196, 218),
        font=ui_fonts["subtitle"],
    )

    # Left Card: Full Em-Canvas Coordinate Grid
    lx0, ly0 = 20, 76
    lx1, ly1 = left_panel_w, H - 20
    draw.rectangle([lx0, ly0, lx1, ly1], fill=(255, 255, 255), outline=(202, 210, 222), width=1)

    gx0 = lx0 + 62
    gy0 = ly0 + 44

    # Draw X coordinate ruler along top
    for c_i in range(total_cols):
        x_val = x_left + c_i
        cx = gx0 + c_i * zoom
        col_txt = f"{x_val}"
        col_color = (200, 30, 45) if x_val == 0 else ((25, 95, 200) if x_val == adv_px else (110, 120, 135))
        draw.text((cx + max(1, zoom // 2 - 4), gy0 - 20), col_txt, fill=col_color, font=ui_fonts["mono_sm"])

    # Draw grid cells & Y coordinate ruler
    for r_i in range(total_rows):
        y_val = y_top - r_i
        ry = gy0 + r_i * zoom

        # Y coordinate label on left
        y_color = (200, 30, 45) if y_val == 0 else (95, 108, 124)
        draw.text((lx0 + 12, ry + max(0, zoom // 2 - 7)), f"y={y_val:+03d}", fill=y_color, font=ui_fonts["mono_sm"])

        for c_i in range(total_cols):
            x_val = x_left + c_i
            rx = gx0 + c_i * zoom

            is_ink = False
            in_bbox = False
            if g.box_w > 0 and g.box_h > 0:
                if g.ofs_x <= x_val < (g.ofs_x + g.box_w) and glyph_y_bot <= y_val <= glyph_y_top:
                    in_bbox = True
                    br = glyph_y_top - y_val
                    bc = x_val - g.ofs_x
                    if 0 <= br < len(g.rows) and 0 <= bc < len(g.rows[br]):
                        is_ink = (g.rows[br][bc] == "#")

            if is_ink:
                draw.rectangle([rx, ry, rx + zoom - 1, ry + zoom - 1], fill=(14, 18, 24), outline=(45, 55, 68))
                if zoom >= 16:
                    # Subtle center crosshair dot on active pixels
                    mcx, mcy = rx + zoom // 2, ry + zoom // 2
                    draw.point((mcx, mcy), fill=(90, 105, 125))
            else:
                cell_bg = (252, 246, 246) if y_val == 0 else ((246, 250, 255) if (0 <= x_val < adv_px and 0 <= y_val <= cap_y) else (255, 255, 255))
                if in_bbox:
                    cell_bg = (242, 252, 246)
                draw.rectangle([rx, ry, rx + zoom - 1, ry + zoom - 1], fill=cell_bg, outline=(226, 232, 240))

    # Draw Horizontal Typographic Landmark Lines (at bottom edge of the respective y row, except baseline which is bottom of y=0 row)
    def draw_h_guide(y_target: int, color: Tuple[int, int, int], label_text: str, width: int = 2, top_edge: bool = False):
        if y_bot <= y_target <= y_top:
            r_idx = y_top - y_target
            ly = gy0 + r_idx * zoom + (0 if top_edge else zoom - 1)
            draw.line([(gx0, ly), (gx0 + grid_w, ly)], fill=color, width=width)
            draw.text((gx0 + grid_w + 8, ly - 8), label_text, fill=color, font=ui_fonts["mono_sm"])

    draw_h_guide(asc_y, (70, 110, 155), f"ASC (+{asc_y})", width=1, top_edge=True)
    draw_h_guide(cap_y, (20, 140, 140), f"CAP (+{cap_y})", width=2, top_edge=True)
    draw_h_guide(xh_y, (130, 80, 170), f"XH (+{xh_y})", width=2, top_edge=True)
    draw_h_guide(0, (210, 35, 45), "BASE (y=0)", width=3, top_edge=False)
    draw_h_guide(desc_y, (195, 120, 25), f"DESC ({desc_y})", width=1, top_edge=False)

    # Draw Vertical Origin (x=0) and Advance Width (x=adv_px) Lines
    if x_left <= 0 <= x_right:
        ox_px = gx0 + (0 - x_left) * zoom
        draw.line([(ox_px, gy0 - 4), (ox_px, gy0 + grid_h + 4)], fill=(210, 35, 45), width=2)
    if x_left <= adv_px <= x_right:
        ax_px = gx0 + (adv_px - x_left) * zoom
        draw.line([(ax_px, gy0 - 4), (ax_px, gy0 + grid_h + 4)], fill=(25, 95, 210), width=2)
        draw.text((ax_px - 18, gy0 + grid_h + 6), f"adv={adv_px}px", fill=(25, 95, 210), font=ui_fonts["mono_sm"])

    # Highlight tight bounding box (ofs_x, ofs_y, box_w, box_h) in emerald green
    if g.box_w > 0 and g.box_h > 0:
        bx0 = gx0 + (g.ofs_x - x_left) * zoom
        by0 = gy0 + (y_top - glyph_y_top) * zoom
        bx1 = bx0 + g.box_w * zoom - 1
        by1 = by0 + g.box_h * zoom - 1
        draw.rectangle([bx0, by0, bx1, by1], outline=(16, 160, 95), width=2)

    # Right Sidebar Panels
    rx0 = left_panel_w + 16
    rx1 = W - 20

    # Panel 1: Multi-Scale Solid Previews (1:1, 2x, 4x on Paper & Inverted)
    p1_y0, p1_y1 = 76, 256
    draw.rectangle([rx0, p1_y0, rx1, p1_y1], fill=(255, 255, 255), outline=(202, 210, 222), width=1)
    draw.text((rx0 + 14, p1_y0 + 10), "1. MULTI-SCALE SOLID PREVIEWS", fill=(24, 32, 44), font=ui_fonts["section"])

    def draw_single_glyph_at(px_x: int, px_y: int, target_g: GlyphStrike, sc: int, fg=(14, 18, 24)):
        by = px_y + asc_y * sc
        if target_g.box_w > 0 and target_g.box_h > 0:
            ox = px_x + target_g.ofs_x * sc
            oy = by - (target_g.ofs_y + target_g.box_h) * sc
            for rr, r_s in enumerate(target_g.rows):
                for cc, px in enumerate(r_s):
                    if px == "#":
                        if sc == 1:
                            draw.point((ox + cc, oy + rr), fill=fg)
                        else:
                            draw.rectangle([ox + cc * sc, oy + rr * sc, ox + (cc + 1) * sc - 1, oy + (rr + 1) * sc - 1], fill=fg)

    # Normal Paper Previews
    draw.text((rx0 + 16, p1_y0 + 38), "1:1 (188 DPI)", fill=(95, 108, 124), font=ui_fonts["mono_sm"])
    draw_single_glyph_at(rx0 + 36, p1_y0 + 62, g, 1, fg=(14, 18, 24))

    draw.text((rx0 + 130, p1_y0 + 38), "2x Scale", fill=(95, 108, 124), font=ui_fonts["mono_sm"])
    draw_single_glyph_at(rx0 + 142, p1_y0 + 58, g, 2, fg=(14, 18, 24))

    # Inverted Dark Badge Previews
    inv_x0 = rx0 + 245
    draw.rectangle([inv_x0, p1_y0 + 34, rx1 - 14, p1_y1 - 14], fill=(14, 18, 24))
    draw.text((inv_x0 + 10, p1_y0 + 40), "Inverted 1:1 & 2x", fill=(180, 195, 215), font=ui_fonts["mono_sm"])
    draw_single_glyph_at(inv_x0 + 24, p1_y0 + 66, g, 1, fg=(255, 255, 255))
    draw_single_glyph_at(inv_x0 + 84, p1_y0 + 62, g, 2, fg=(255, 255, 255))

    # Panel 2: Context Word Alignment Preview ("H [char] p" and "0 [char] 0")
    p2_y0, p2_y1 = 272, 468
    draw.rectangle([rx0, p2_y0, rx1, p2_y1], fill=(255, 255, 255), outline=(202, 210, 222), width=1)
    draw.text((rx0 + 14, p2_y0 + 10), "2. BASELINE & NEIGHBOR CONTEXT (3x)", fill=(24, 32, 44), font=ui_fonts["section"])
    draw.text((rx0 + 14, p2_y0 + 30), "Shows position relative to Cap 'H', Descender 'p', and '0':", fill=(95, 108, 124), font=ui_fonts["mono_sm"])

    ctx_scale = 3 if size_px <= 20 else 2
    ctx_base_y = p2_y0 + 56 + asc_y * ctx_scale
    draw.line([(rx0 + 16, ctx_base_y), (rx1 - 16, ctx_base_y)], fill=(225, 140, 140), width=1)
    draw.line([(rx0 + 16, ctx_base_y - cap_y * ctx_scale), (rx1 - 16, ctx_base_y - cap_y * ctx_scale)], fill=(210, 230, 240), width=1)

    cx_cursor = rx0 + 24
    for ch_code, is_target in [(ord("H"), False), (g.codepoint, True), (ord("p"), False), (ord(" "), False), (ord("0"), False), (g.codepoint, True), (ord("0"), False)]:
        cg = g if is_target else gmap.get(ch_code)
        if not cg:
            cx_cursor += (size_px // 2) * ctx_scale
            continue
        c_adv = ((cg.adv_w_fp4 + 8) >> 4) * ctx_scale
        if is_target:
            draw.rectangle(
                [cx_cursor, ctx_base_y - asc_y * ctx_scale, cx_cursor + c_adv, ctx_base_y - desc_y * ctx_scale],
                fill=(235, 246, 255),
                outline=(130, 180, 235),
            )
        if cg.box_w > 0 and cg.box_h > 0:
            ox = cx_cursor + cg.ofs_x * ctx_scale
            oy = ctx_base_y - (cg.ofs_y + cg.box_h) * ctx_scale
            fg_c = (200, 25, 40) if is_target else (40, 50, 65)
            for rr, r_s in enumerate(cg.rows):
                for cc, px in enumerate(r_s):
                    if px == "#":
                        draw.rectangle(
                            [ox + cc * ctx_scale, oy + rr * ctx_scale, ox + (cc + 1) * ctx_scale - 1, oy + (rr + 1) * ctx_scale - 1],
                            fill=fg_c,
                        )
        cx_cursor += c_adv

    # Panel 3: Complete LVGL v9 Descriptor & Hex Dump Table
    p3_y0, p3_y1 = 484, H - 20
    draw.rectangle([rx0, p3_y0, rx1, p3_y1], fill=(255, 255, 255), outline=(202, 210, 222), width=1)
    draw.text((rx0 + 14, p3_y0 + 10), "3. LVGL v9 GLYPH DESCRIPTOR & HEX BITMAP", fill=(24, 32, 44), font=ui_fonts["section"])

    packed_bytes = g.pack_1bpp_bytes()
    hex_dump = ", ".join(f"0x{b:02X}" for b in packed_bytes) if packed_bytes else "0x00 (Empty)"

    kv_rows = [
        ("Codepoint / Name", f"U+{g.codepoint:04X} ({char_disp!r}) [{gname}]"),
        ("Advance Width", f"{adv_px} px  (adv_w_fp4 = {g.adv_w_fp4})"),
        ("Bounding Box (w x h)", f"box_w = {g.box_w} px,  box_h = {g.box_h} px"),
        ("Bearing Offsets", f"ofs_x = {g.ofs_x:+d} px,  ofs_y = {g.ofs_y:+d} px"),
        ("Vertical Y Span", f"y = {glyph_y_bot:+d} .. {glyph_y_top:+d}  (rel to Baseline y=0)" if g.box_h > 0 else "Empty"),
        ("1-BPP Packed Size", f"{len(packed_bytes)} bytes ({g.box_w * g.box_h} bits)"),
        ("Patch Status", "PATCHED" if g.patched else "UNMODIFIED BASELINE"),
    ]
    ty = p3_y0 + 38
    for k_label, v_val in kv_rows:
        draw.text((rx0 + 16, ty), f"{k_label:20s}:", fill=(95, 108, 124), font=ui_fonts["mono"])
        draw.text((rx0 + 185, ty), v_val, fill=(16, 22, 31), font=ui_fonts["mono"])
        ty += 22

    ty += 6
    draw.line([(rx0 + 14, ty - 4), (rx1 - 14, ty - 4)], fill=(228, 232, 240), width=1)
    draw.text((rx0 + 16, ty), "Packed 1-BPP C Hex Array:", fill=(95, 108, 124), font=ui_fonts["mono"])
    ty += 20
    # Wrap hex dump across lines of 48 chars
    for i in range(0, len(hex_dump), 48):
        if ty < p3_y1 - 18:
            draw.text((rx0 + 16, ty), hex_dump[i : i + 48], fill=(20, 90, 160), font=ui_fonts["mono_sm"])
            ty += 16

    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out_png))


def render_char_by_char_folder(
    strike_char_dir: Path,
    font_symbol_name: str,
    family: str,
    role: str,
    size_px: int,
    raster_mode: str,
    line_height: int,
    base_line: int,
    glyphs: Sequence[GlyphStrike],
    char_filter: str = "trouble",
    static_dir: Optional[Path] = None,
) -> int:
    """
    Render Char-by-Char Deep Inspection PNG cards into `strike_char_dir/U+XXXX_<name>.png`.
    `char_filter` can be:
      - 'trouble' : Trouble 15 + key punctuation ('_', '.', '-', '0', '8', '@', '%', '#', '$', '&', 'a', 'e', 'g', 's', 'B')
      - 'patched' : Only patched glyphs
      - 'ascii'   : All printable ASCII (0x20..0x7E)
      - 'all'     : Every glyph in the strike
    """
    gmap = {g.codepoint: g for g in glyphs if g.codepoint > 0}
    diagnostic_set = set(TROUBLE_15_CODEPOINTS) | {
        ord("_"), ord("."), ord("-"), ord(":"), ord(";"), ord("/"), ord("("), ord(")"),
        ord("0"), ord("1"), ord("8"), ord("A"), ord("H"), ord("M"), ord("U"), ord("p"),
    }
    count = 0
    is_icon_fam = family.startswith("icon_")
    valid_list = [g for g in glyphs if g.codepoint > 0]
    # For full-catalog icon strikes (> 300 glyphs), select up to 150 representative icons unless 'full' is requested
    icon_cap_cps = {g.codepoint for g in valid_list[:150]} if (is_icon_fam and len(valid_list) > 300) else {g.codepoint for g in valid_list}
    for g in valid_list:
        if char_filter == "patched" and not g.patched:
            continue
        elif char_filter in ("all", "trouble"):
            if is_icon_fam and len(valid_list) > 300 and g.codepoint not in icon_cap_cps and not g.patched:
                continue
            elif char_filter == "trouble" and not is_icon_fam and family != "terminus":
                if g.codepoint not in diagnostic_set and not g.patched:
                    continue
        elif char_filter == "ascii" and not (0x20 <= g.codepoint <= 0x7E):
            continue

        fname = safe_glyph_filename(g.codepoint, family).replace(".txt", ".png")
        out_png = strike_char_dir / fname
        render_single_char_inspection_png(
            out_png=out_png,
            font_symbol_name=font_symbol_name,
            family=family,
            role=role,
            size_px=size_px,
            raster_mode=raster_mode,
            line_height=line_height,
            base_line=base_line,
            g=g,
            gmap=gmap,
            static_dir=static_dir,
        )
        count += 1
    return count


# 9. ADOBE BDF 2.1 EXPORTER & LVGL v9 C SOURCE GENERATOR
# =============================================================================

def export_bdf_strike(
    bdf_path: Path,
    font_symbol_name: str,
    size_px: int,
    dpi: int,
    line_height: int,
    base_line: int,
    glyphs: Sequence[GlyphStrike],
) -> None:
    """Export a 1-bpp strike to standard Adobe BDF 2.1 format for FontForge / Bits'n'Picas editing."""
    bdf_path.parent.mkdir(parents=True, exist_ok=True)
    ascent = line_height - base_line
    descent = base_line
    lines = [
        "STARTFONT 2.1",
        f"COMMENT Generated by Humidyne Labs humid1_generate_1bpp.py ({font_symbol_name})",
        f"FONT -Humidyne-{font_symbol_name}-R-Normal--{size_px}-{size_px*10}-{dpi}-{dpi}-P-0-ISO10646-1",
        f"SIZE {size_px} {dpi} {dpi}",
        f"FONTBOUNDINGBOX {size_px} {line_height} 0 {-descent}",
        "STARTPROPERTIES 4",
        f"FONT_ASCENT {ascent}",
        f"FONT_DESCENT {descent}",
        f"PIXEL_SIZE {size_px}",
        f"RESOLUTION_Y {dpi}",
        "ENDPROPERTIES",
        f"CHARS {len(glyphs)}",
    ]

    for g in glyphs:
        dwidth = int(round(g.adv_w_fp4 / 16.0))
        lines.extend([
            f"STARTCHAR U+{g.codepoint:04X}",
            f"ENCODING {g.codepoint}",
            f"SWIDTH {int(round(dwidth * 72000.0 / (size_px * dpi)))} 0",
            f"DWIDTH {dwidth} 0",
            f"BBX {g.box_w} {g.box_h} {g.ofs_x} {g.ofs_y}",
            "BITMAP",
        ])
        if g.box_w == 0 or g.box_h == 0:
            lines.append("00")
        else:
            row_bytes = (g.box_w + 7) // 8
            for r in g.rows:
                bits = r.ljust(row_bytes * 8, ".")
                hex_row = ""
                for b in range(row_bytes):
                    chunk = bits[b * 8 : (b + 1) * 8]
                    val = int(chunk.replace("#", "1").replace(".", "0"), 2)
                    hex_row += f"{val:02X}"
                lines.append(hex_row)
        lines.append("ENDCHAR")

    lines.append("ENDFONT")
    bdf_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_cmaps_partitions(glyphs: Sequence[GlyphStrike]) -> List[dict]:
    """Partition sorted glyphs into contiguous FORMAT0_TINY ranges and SPARSE_TINY subtables."""
    if not glyphs:
        return []
    subtables: List[dict] = []
    i = 0
    n = len(glyphs)
    while i < n:
        j = i
        while j + 1 < n and glyphs[j + 1].codepoint == glyphs[j].codepoint + 1:
            j += 1
        run_len = j - i + 1
        if run_len >= 8:
            subtables.append({
                "type": "LV_FONT_FMT_TXT_CMAP_FORMAT0_TINY",
                "range_start": glyphs[i].codepoint,
                "range_length": run_len,
                "glyph_id_start": glyphs[i].glyph_id,
                "codes": [],
            })
            i = j + 1
        else:
            sparse_codes: List[int] = []
            start_gid = glyphs[i].glyph_id
            start_code = glyphs[i].codepoint
            while i < n:
                k = i
                while k + 1 < n and glyphs[k + 1].codepoint == glyphs[k].codepoint + 1:
                    k += 1
                if (k - i + 1) >= 8:
                    break
                if glyphs[i].codepoint - start_code > 0xFFFF:
                    break
                sparse_codes.append(glyphs[i].codepoint)
                i += 1
            subtables.append({
                "type": "LV_FONT_FMT_TXT_CMAP_SPARSE_TINY",
                "range_start": start_code,
                "range_length": sparse_codes[-1] - start_code + 1,
                "glyph_id_start": start_gid,
                "codes": sparse_codes,
            })
    return subtables


def emit_lvgl_c_file(
    out_file: Path,
    font_symbol_name: str,
    size_px: int,
    family: str,
    role: str,
    raster_mode: str,
    glyphs: Sequence[GlyphStrike],
    line_height: int,
    base_line: int,
    underline_pos: int,
    underline_thick: int,
    kern_pairs: Sequence[Tuple[int, int, int, int, int]],
    fallback_symbol: Optional[str] = None,
) -> int:
    """Write an LVGL v9 compliant 1-bpp C font file and return the compiled ROM/Flash byte footprint."""
    guard_macro = font_symbol_name.upper()

    lines = [
        "/*******************************************************************************",
        f" * Font: {font_symbol_name} ({family} {role})",
        f" * Size: {size_px} px @ 188.3 DPI (SSD1681 1-bit E-Paper Display)",
        " * Bpp: 1 (Uncompressed Bilevel Monochrome)",
        f" * Raster Mode: {raster_mode} (FT_LOAD_TARGET_MONO + Closed-Loop Stem Floor)",
        " * License: MIT AND OFL-1.1",
        " ******************************************************************************/",
        "",
        "#if defined(LV_LVGL_H_INCLUDE_SIMPLE)",
        '#include "lvgl.h"',
        "#elif defined(__has_include)",
        '#if __has_include("lvgl.h")',
        '#include "lvgl.h"',
        '#elif __has_include("lvgl/lvgl.h")',
        '#include "lvgl/lvgl.h"',
        "#else",
        '#include "lvgl.h"',
        "#endif",
        "#else",
        '#include "lvgl.h"',
        "#endif",
        "",
        f"#ifndef {guard_macro}",
        f"#define {guard_macro} 1",
        "#endif",
        "",
        f"#if {guard_macro}",
        "",
    ]

    if fallback_symbol:
        lines.extend([f"extern const lv_font_t {fallback_symbol};", ""])

    lines.extend([
        "/*-----------------",
        " *    BITMAPS",
        " *----------------*/",
        "",
        "static LV_ATTRIBUTE_LARGE_CONST const uint8_t glyph_bitmap[] = {",
    ])

    bitmap_offsets: List[int] = []
    total_bitmap_bytes = 0
    for g in glyphs:
        bitmap_offsets.append(total_bitmap_bytes)
        packed = g.pack_1bpp_bytes()
        char_disp = chr(g.codepoint) if 0x20 <= g.codepoint <= 0x7E and chr(g.codepoint) not in ('\\', '"', '*') else ""
        lines.append(f"    /* U+{g.codepoint:04X} \"{char_disp}\" ({g.box_w}x{g.box_h}) */")
        if packed:
            for i in range(0, len(packed), 12):
                chunk = ", ".join(f"0x{b:02x}" for b in packed[i : i + 12])
                lines.append(f"    {chunk},")
        total_bitmap_bytes += len(packed)

    if total_bitmap_bytes == 0:
        lines.append("    0x00")
    lines.extend(["};", ""])

    lines.extend([
        "/*---------------------",
        " *  GLYPH DESCRIPTION",
        " *--------------------*/",
        "",
        "static const lv_font_fmt_txt_glyph_dsc_t glyph_dsc[] = {",
        "    {.bitmap_index = 0, .adv_w = 0, .box_w = 0, .box_h = 0, .ofs_x = 0, .ofs_y = 0} /* id = 0 reserved */,",
    ])

    for idx, g in enumerate(glyphs):
        b_idx = bitmap_offsets[idx]
        comma = "," if idx + 1 < len(glyphs) else ""
        lines.append(
            f"    {{.bitmap_index = {b_idx}, .adv_w = {g.adv_w_fp4}, "
            f".box_w = {g.box_w}, .box_h = {g.box_h}, .ofs_x = {g.ofs_x}, .ofs_y = {g.ofs_y}}}{comma}"
        )
    lines.extend(["};", ""])

    cmaps = build_cmaps_partitions(glyphs)
    lines.extend([
        "/*---------------------",
        " *  CHARACTER MAPPING",
        " *--------------------*/",
        "",
    ])

    for c_idx, cm in enumerate(cmaps):
        if cm["type"] == "LV_FONT_FMT_TXT_CMAP_SPARSE_TINY":
            offsets = [f"0x{c - cm['range_start']:04x}" for c in cm["codes"]]
            lines.append(f"static const uint16_t unicode_list_{c_idx}[] = {{")
            for i in range(0, len(offsets), 10):
                lines.append("    " + ", ".join(offsets[i : i + 10]) + ",")
            lines.extend(["};", ""])

    lines.append("static const lv_font_fmt_txt_cmap_t cmaps[] = {")
    for c_idx, cm in enumerate(cmaps):
        comma = "," if c_idx + 1 < len(cmaps) else ""
        if cm["type"] == "LV_FONT_FMT_TXT_CMAP_FORMAT0_TINY":
            lines.extend([
                "    {",
                f"        .range_start = {cm['range_start']}, .range_length = {cm['range_length']}, .glyph_id_start = {cm['glyph_id_start']},",
                "        .unicode_list = NULL, .glyph_id_ofs_list = NULL, .list_length = 0, .type = LV_FONT_FMT_TXT_CMAP_FORMAT0_TINY",
                f"    }}{comma}",
            ])
        else:
            lines.extend([
                "    {",
                f"        .range_start = {cm['range_start']}, .range_length = {cm['range_length']}, .glyph_id_start = {cm['glyph_id_start']},",
                f"        .unicode_list = unicode_list_{c_idx}, .glyph_id_ofs_list = NULL, .list_length = {len(cm['codes'])}, .type = LV_FONT_FMT_TXT_CMAP_SPARSE_TINY",
                f"    }}{comma}",
            ])
    lines.extend(["};", ""])

    has_kern = len(kern_pairs) > 0 and len(glyphs) < 255
    if has_kern:
        lines.extend([
            "/*-----------------",
            " *    KERNING",
            " *----------------*/",
            "",
            "static const uint8_t kern_pair_glyph_ids[] = {",
        ])
        for i in range(0, len(kern_pairs), 8):
            chunk = ", ".join(f"{l_gid}, {r_gid}" for l_gid, r_gid, _, _, _ in kern_pairs[i : i + 8])
            lines.append(f"    {chunk},")
        lines.extend([
            "};",
            "",
            "static const int8_t kern_pair_values[] = {",
        ])
        for i in range(0, len(kern_pairs), 16):
            chunk = ", ".join(str(k_val) for _, _, _, _, k_val in kern_pairs[i : i + 16])
            lines.append(f"    {chunk},")
        lines.extend([
            "};",
            "",
            "static const lv_font_fmt_txt_kern_pair_t kern_pairs = {",
            "    .glyph_ids = kern_pair_glyph_ids,",
            "    .values = kern_pair_values,",
            f"    .pair_cnt = {len(kern_pairs)},",
            "    .glyph_ids_size = 0",
            "};",
            "",
        ])

    kern_ptr = "&kern_pairs" if has_kern else "NULL"
    kern_scale = 16 if has_kern else 0
    fallback_ptr = f"&{fallback_symbol}" if fallback_symbol else "NULL"

    lines.extend([
        "/*--------------------",
        " *  ALL CUSTOM DATA",
        " *--------------------*/",
        "",
        "#if LVGL_VERSION_MAJOR == 8",
        "static lv_font_fmt_txt_glyph_cache_t cache;",
        "#endif",
        "",
        "#if LVGL_VERSION_MAJOR >= 8",
        "static const lv_font_fmt_txt_dsc_t font_dsc = {",
        "#else",
        "static lv_font_fmt_txt_dsc_t font_dsc = {",
        "#endif",
        "    .glyph_bitmap = glyph_bitmap,",
        "    .glyph_dsc = glyph_dsc,",
        "    .cmaps = cmaps,",
        f"    .kern_dsc = {kern_ptr},",
        f"    .kern_scale = {kern_scale},",
        f"    .cmap_num = {len(cmaps)},",
        "    .bpp = 1,",
        "    .kern_classes = 0,",
        "    .bitmap_format = 0,",
        "#if LVGL_VERSION_MAJOR == 8",
        "    .cache = &cache",
        "#endif",
        "};",
        "",
        "/*-----------------",
        " *  PUBLIC FONT",
        " *----------------*/",
        "",
        "#if LVGL_VERSION_MAJOR >= 8",
        f"const lv_font_t {font_symbol_name} = {{",
        "#else",
        f"lv_font_t {font_symbol_name} = {{",
        "#endif",
        "    .get_glyph_dsc = lv_font_get_glyph_dsc_fmt_txt,",
        "    .get_glyph_bitmap = lv_font_get_bitmap_fmt_txt,",
        f"    .line_height = {line_height},",
        f"    .base_line = {base_line},",
        "#if !(LVGL_VERSION_MAJOR == 6 && LVGL_VERSION_MINOR == 0)",
        "    .subpx = LV_FONT_SUBPX_NONE,",
        "#endif",
        "#if LV_VERSION_CHECK(7, 4, 0) || LVGL_VERSION_MAJOR >= 8",
        f"    .underline_position = {underline_pos},",
        f"    .underline_thickness = {underline_thick},",
        "#endif",
        "    .dsc = &font_dsc,",
        "#if LV_VERSION_CHECK(8, 2, 0) || LVGL_VERSION_MAJOR >= 9",
        f"    .fallback = {fallback_ptr},",
        "#endif",
        "    .user_data = NULL,",
        "};",
        "",
        f"#endif /* #if {guard_macro} */",
        "",
    ])

    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text("\n".join(lines), encoding="utf-8")

    sparse_bytes = sum(len(cm["codes"]) * 2 for cm in cmaps if cm["type"] == "LV_FONT_FMT_TXT_CMAP_SPARSE_TINY")
    kern_bytes = (len(kern_pairs) * 3 + 16) if has_kern else 0
    rom_bytes = total_bitmap_bytes + (len(glyphs) + 1) * 8 + len(cmaps) * 20 + sparse_bytes + kern_bytes + 60
    return rom_bytes


# =============================================================================
# 10. METRIC CSV EXPORTER, HEADER GENERATOR & SCREEN WIDTH AUDITOR
# =============================================================================

def export_metric_csvs(
    metrics_dir: Path,
    font_symbol_name: str,
    glyphs: Sequence[GlyphStrike],
    kern_pairs: Sequence[Tuple[int, int, int, int, int]],
) -> None:
    """Export char_widths_<symbol>.csv and kern_pairs_<symbol>.csv matching H1OS schema."""
    metrics_dir.mkdir(parents=True, exist_ok=True)
    cw_path = metrics_dir / f"char_widths_{font_symbol_name}.csv"
    with cw_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "char", "unicode_hex", "unicode_dec", "adv_w_raw",
            "width_px", "box_w", "box_h", "ofs_x", "ofs_y"
        ])
        for g in glyphs:
            ch_label = "<SPACE>" if g.codepoint == 0x20 else chr(g.codepoint)
            writer.writerow([
                ch_label,
                f"0x{g.codepoint:04X}",
                g.codepoint,
                g.adv_w_fp4,
                round(g.adv_w_fp4 / 16.0, 4),
                g.box_w,
                g.box_h,
                g.ofs_x,
                g.ofs_y,
            ])

    kp_path = metrics_dir / f"kern_pairs_{font_symbol_name}.csv"
    with kp_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["left_char", "left_code", "right_char", "right_code", "kern_raw_16th", "kern_px"])
        for _, _, l_code, r_code, k_fp4 in kern_pairs:
            l_ch = "<SPACE>" if l_code == 0x20 else chr(l_code)
            r_ch = "<SPACE>" if r_code == 0x20 else chr(r_code)
            writer.writerow([
                l_ch,
                f"0x{l_code:04X}",
                r_ch,
                f"0x{r_code:04X}",
                k_fp4,
                round(k_fp4 / 16.0, 4),
            ])


def measure_lvgl_string_px(
    text: str,
    glyph_map: Dict[int, GlyphStrike],
    kern_map: Dict[Tuple[int, int], int],
    fallback_glyph_map: Optional[Dict[int, GlyphStrike]] = None,
) -> int:
    """Compute exact LVGL v9 rendered string width in integer pixels."""
    codes = [ord(c) for c in text]
    total_px = 0
    for i, c in enumerate(codes):
        g = glyph_map.get(c) or (fallback_glyph_map.get(c) if fallback_glyph_map else None)
        if not g:
            continue
        adv = g.adv_w_fp4
        if i + 1 < len(codes):
            c_next = codes[i + 1]
            k_fp4 = kern_map.get((c, c_next), 0)
            adv += k_fp4
        total_px += (adv + 8) >> 4
    return total_px


def generate_headers(
    out_dir: Path,
    compiled_symbols: Sequence[Tuple[str, str, str, int, int]],
    scheme_cfg: Optional[dict] = None,
) -> None:
    """
    Generate drop-in-ready `humid1_fonts.h`, `plex_fonts.h`, `epd_fonts.h`, and `h1os_fonts.h`
    with circular-include guards (`struct _lv_font_t`, `#ifndef LV_FONT_DECLARE`), universal
    `__has_include("lvgl.h")` detection, and complete `HUMID1_FONT_*`, `PLEX_FONT_*`,
    `HUMID1_ICON_*`, and `H1OS_FONT_*` semantic aliases.
    """
    sym_set = {item[0] for item in compiled_symbols}

    def pick_sym(preferred: str, fallback: str = "humid1_font_plex_sans_normal_14") -> str:
        for cand in (
            preferred,
            f"humid1_font_{preferred}",
            f"humid1_{preferred}",
            fallback,
            f"humid1_font_{fallback}",
            "humid1_font_plex_sans_normal_14",
            "humid1_font_plex_sans_bold_14",
        ):
            if cand in sym_set:
                return cand
        return compiled_symbols[0][0] if compiled_symbols else "humid1_font_plex_sans_normal_14"

    def build_primary_header_text(header_filename: str) -> str:
        lines = [
            "/**",
            f" * @file {header_filename}",
            " * @brief Humidyne Labs / Humiditron 1-BPP Bilevel EPD Typography & Iconography Suite",
            " *",
            " * Drop-in ready for H1OS & humid1-os (safe for direct inclusion in lv_conf.h or app code).",
            " * Auto-generated by tools/fonts/humid1_generate_1bpp.py (v1.0.10)",
            " * SPDX-License-Identifier: MIT AND OFL-1.1",
            " */",
            "",
            "#pragma once",
            "",
            "#if defined(LV_LVGL_H_INCLUDE_SIMPLE)",
            '#include "lvgl.h"',
            "#elif defined(__has_include)",
            '#if __has_include("lvgl.h")',
            '#include "lvgl.h"',
            '#elif __has_include("lvgl/lvgl.h")',
            '#include "lvgl/lvgl.h"',
            "#else",
            '#include "lvgl.h"',
            "#endif",
            "#else",
            '#include "lvgl.h"',
            "#endif",
            "",
            "#ifdef __cplusplus",
            'extern "C" {',
            "#endif",
            "",
            "struct _lv_font_t;",
            "#ifndef LV_FONT_T_DEFINED",
            "typedef struct _lv_font_t lv_font_t;",
            "#define LV_FONT_T_DEFINED",
            "#endif",
            "",
            "#ifndef LV_FONT_DECLARE",
            "#define LV_FONT_DECLARE(font_name) extern const lv_font_t font_name",
            "#endif",
            "",
            "/* =========================================================================",
            " * 1. Base LVGL v8/v9 1-BPP Font & Modular Icon Strike Declarations",
            " * ========================================================================= */",
        ]
        for sym, fam, role, sz, rom_b in compiled_symbols:
            lines.append(f"LV_FONT_DECLARE({sym}); /* {fam} {role} {sz}px (~{rom_b:,} B ROM) */")

        role_pairs = [
            ("UI_MICRO",         pick_sym("plex_sans_normal_12", "plex_sans_normal_14")),
            ("UI_BODY",          pick_sym("plex_sans_normal_14")),
            ("UI_BODY_MD",       pick_sym("plex_sans_normal_16", "plex_sans_normal_14")),
            ("UI_SUBTITLE",      pick_sym("plex_sans_bold_14")),
            ("UI_TITLE",         pick_sym("plex_sans_bold_16", "plex_sans_bold_14")),
            ("UI_HEADER",        pick_sym("plex_sans_bold_20", "plex_sans_bold_18")),
            ("UI_META_ITALIC",   pick_sym("plex_sans_italic_14", "plex_sans_normal_14")),
            ("TELEMETRY_SM",     pick_sym("plex_mono_normal_14")),
            ("TELEMETRY_SMALL",  pick_sym("plex_mono_normal_14")),
            ("TELEMETRY_BODY",   pick_sym("plex_mono_normal_16", "plex_mono_normal_14")),
            ("TELEMETRY_MD",     pick_sym("plex_mono_bold_20", "plex_mono_normal_20")),
            ("TELEMETRY_VALUE",  pick_sym("plex_mono_bold_20", "plex_mono_normal_20")),
            ("TELEMETRY_LG",     pick_sym("plex_mono_bold_24", "plex_sans_bold_24")),
            ("TELEMETRY_HERO",   pick_sym("plex_mono_bold_24", "plex_sans_bold_24")),
            ("TELEMETRY_XL",     pick_sym("plex_mono_bold_32", "plex_sans_bold_32")),
            ("TELEMETRY_JUMBO",  pick_sym("plex_mono_bold_32", "plex_sans_bold_32")),
            ("RIBBON_COND",      pick_sym("plex_cond_normal_16", "plex_sans_normal_16")),
            ("BANNER_COND",      pick_sym("plex_cond_bold_18", "plex_sans_bold_18")),
            ("EDITORIAL_BODY",   pick_sym("plex_serif_normal_18", "plex_sans_normal_18")),
            ("EDITORIAL_TITLE",  pick_sym("plex_serif_bold_24", "plex_sans_bold_24")),
            ("FORMULA",          pick_sym("plex_math_regular_16", "plex_sans_normal_16")),
            ("TERMINAL",         pick_sym("terminus_bold_16", "terminus_normal_16")),
            ("TERMINAL_SM",      pick_sym("terminus_normal_12", "plex_mono_normal_12")),
        ]

        lines.extend([
            "",
            "/* =========================================================================",
            " * 2. Canonical HUMID1_FONT_* Semantic UI & Telemetry Role Macros (H1OS)",
            " * ========================================================================= */",
        ])
        emitted_macros = set()
        for suffix, target in role_pairs:
            m_name = f"HUMID1_FONT_{suffix}"
            lines.append(f"#define {m_name:<28} (&{target})")
            emitted_macros.add(m_name)

        # Include any custom semantic_roles from scheme JSON
        if scheme_cfg:
            sem_roles = scheme_cfg.get("output_branding", {}).get("semantic_roles", {})
            for m_name, raw_target in sem_roles.items():
                if m_name not in emitted_macros:
                    resolved_t = pick_sym(raw_target)
                    lines.append(f"#define {m_name:<28} (&{resolved_t})")
                    emitted_macros.add(m_name)

        # Modular Icon Default Macros
        icon_defaults = [
            ("HUMID1_ICON_FA7_DEFAULT",      pick_sym("icon_fa7_solid_16", "icon_fa7_solid_14")),
            ("HUMID1_ICON_LUCIDE_DEFAULT",   pick_sym("icon_lucide_regular_16", "icon_lucide_regular_14")),
            ("HUMID1_ICON_PHOSPHOR_DEFAULT", pick_sym("icon_phosphor_regular_16", "icon_phosphor_regular_14")),
            ("HUMID1_ICON_TABLER_DEFAULT",   pick_sym("icon_tabler_regular_16", "icon_tabler_regular_14")),
        ]
        for m_name, target in icon_defaults:
            if m_name not in emitted_macros:
                lines.append(f"#define {m_name:<28} (&{target})")
                emitted_macros.add(m_name)

        lines.extend([
            "",
            "/* =========================================================================",
            " * 3. Backward-Compatible PLEX_FONT_* Role Aliases",
            " * ========================================================================= */",
        ])
        for suffix, target in role_pairs:
            lines.append(f"#define PLEX_FONT_{suffix:<18} (&{target})")

        lines.extend([
            "",
            "#ifdef __cplusplus",
            "}",
            "#endif",
            "",
        ])
        return "\n".join(lines)

    for hdr_name in ("humid1_fonts.h", "plex_fonts.h", "epd_fonts.h"):
        (out_dir / hdr_name).write_text(build_primary_header_text(hdr_name), encoding="utf-8")

    h1os_h = out_dir / "h1os_fonts.h"
    default_sym = pick_sym("plex_sans_normal_14")
    h_lines = [
        "/**",
        " * @file h1os_fonts.h",
        " * @brief H1OS Build-Time Generated 1-BPP Bilevel Typography Suite (IBM Plex EPD)",
        " *",
        " * Drop-in backward-compatible header for H1OS & humid1-os.",
        " * Auto-generated by tools/fonts/humid1_generate_1bpp.py (v1.0.10)",
        " * SPDX-License-Identifier: MIT AND OFL-1.1",
        " */",
        "",
        "#pragma once",
        "",
        '#include "humid1_fonts.h"',
        "",
        "#ifdef __cplusplus",
        'extern "C" {',
        "#endif",
        "",
        "#ifndef LV_FONT_CUSTOM_DECLARE",
        f"#define LV_FONT_CUSTOM_DECLARE LV_FONT_DECLARE({default_sym});",
        "#endif",
        "",
        "#ifndef LV_FONT_DEFAULT",
        f"#define LV_FONT_DEFAULT (&{default_sym})",
        "#endif",
        "",
        "/* =========================================================================",
        " * Backward-Compatible H1OS_FONT_<sz> & Legacy Symbol Aliases",
        " * ========================================================================= */",
    ]
    for sz in [12, 14, 16, 18, 20, 22, 24, 28, 32, 36, 40]:
        pref = f"plex_sans_bold_{sz}" if sz >= 20 else f"plex_sans_normal_{sz}"
        target = pick_sym(pref, f"plex_sans_normal_{sz}")
        s_bold = pick_sym(f"plex_sans_bold_{sz}", target)
        m_norm = pick_sym(f"plex_mono_normal_{sz}", target)
        m_bold = pick_sym(f"plex_mono_bold_{sz}", s_bold)
        h_lines.append(f"#define H1OS_FONT_{sz} (&{target})")
        h_lines.append(f"#define H1OS_FONT_BOLD_{sz} (&{s_bold})")
        h_lines.append(f"#define H1OS_FONT_MONO_{sz} (&{m_norm})")
        h_lines.append(f"#define H1OS_FONT_MONO_BOLD_{sz} (&{m_bold})")
        h_lines.append(f"#define h1os_font_montserrat_{sz}_1bpp {target}")

    h_lines.extend(["", "#ifdef __cplusplus", "}", "#endif", ""])
    h1os_h.write_text("\n".join(h_lines), encoding="utf-8")


def copy_licenses(plex_dir: Optional[Path], font_dir: Path, out_dir: Path) -> None:
    """Copy all upstream font & icon license files into `<out_dir>/licenses/`."""
    lic_dst = out_dir / "licenses"
    lic_dst.mkdir(parents=True, exist_ok=True)
    for src_sub in (font_dir / "licenses", font_dir / "font_license", font_dir.parent.parent / "LICENSES"):
        if src_sub.is_dir():
            for lf in sorted(src_sub.glob("*.txt")):
                shutil.copy2(lf, lic_dst / lf.name)
    if (font_dir / "OFL.txt").is_file():
        shutil.copy2(font_dir / "OFL.txt", lic_dst / "IBMPlex_OFL.txt")


H1OS_CANONICAL_SCREEN_ROWS = [
    ("Screen 1: Env Dash", "Header (Title + 36px Badge)", "HUMIDYNE LABS", "1/5", "plex_sans_bold_14", "plex_mono_bold_14", 12),
    ("Screen 1: Env Dash", "Hero Telemetry Row (Y=32)", "104.8°F", "\uf043 99.9%", "plex_sans_bold_20", "plex_mono_bold_20", 10),
    ("Screen 1: Env Dash", "Row 1: Settling Status", "Status", "SETTLED (100%)", "plex_sans_normal_14", "plex_mono_normal_14", 8),
    ("Screen 1: Env Dash", "Row 2: Vapor Pressure", "Vapor Pressure", "42.8 hPa", "plex_sans_normal_14", "plex_mono_normal_14", 8),
    ("Screen 2: Psychrometrics", "Row 1: Dew Point", "Dew Point", "78.4°F (25.8°C)", "plex_sans_normal_14", "plex_mono_normal_14", 8),
    ("Screen 2: Psychrometrics", "Row 2: Abs Humidity", "Abs Humidity", "24.2 g/m³", "plex_sans_normal_14", "plex_mono_normal_14", 8),
    ("Screen 3: Thermal Nodes", "Row 4: TriNode Delta T", "TriNode ΔT", "+0.4°C", "plex_sans_normal_14", "plex_mono_normal_14", 8),
    ("Screen 4: System Health", "Row 1: Battery Voltage/SoC", "Battery", "\uf240 4.18V (100%)", "plex_sans_normal_14", "plex_mono_normal_14", 8),
    ("Screen 5: Diagnostics", "Row 4: Heap Watermark", "Heap", "342K (Min 298K)", "plex_sans_normal_14", "plex_mono_normal_14", 8),
    ("Screen 5: Diagnostics", "Row 6: Wake & Ring Count", "Wakes", "9999 (Ring 32/32)", "plex_sans_normal_14", "plex_mono_normal_14", 8),
    ("Screen 5: Diagnostics", "Row 7: CPU & SHTC3 State", "CPU", "240MHz • SHT:OK", "plex_sans_normal_14", "plex_mono_normal_14", 8),
]


def run_screen_width_audit(
    strike_cache: Dict[str, Tuple[Dict[int, GlyphStrike], int, int]],
    kern_cache: Dict[str, Dict[Tuple[int, int], int]],
    montserrat_metrics_dir: Optional[Path] = None,
    screen_width: int = 200,
    screen_height: int = 200,
    safe_margin: int = 6,
    dpi: float = 188.3,
    panel_name: str = "Humiditron / humid1 Reference EPD",
    custom_rows: Optional[List[dict]] = None,
) -> List[dict]:
    """Audit horizontal string widths against the target display's usable pixel width budget."""
    mont_widths: Dict[int, Dict[int, float]] = {14: {}, 20: {}}
    if montserrat_metrics_dir and montserrat_metrics_dir.is_dir():
        for sz in (14, 20):
            p = montserrat_metrics_dir / f"char_widths_montserrat_{sz}.csv"
            if p.is_file():
                with p.open("r", encoding="utf-8-sig") as f:
                    for row in csv.DictReader(f):
                        mont_widths[sz][int(row["unicode_dec"])] = float(row["width_px"])

    def measure_mont(text: str, sz: int) -> int:
        if not mont_widths.get(sz):
            return 0
        return int(round(sum(mont_widths[sz].get(ord(c), 8.0) for c in text)))

    usable_budget = max(32, screen_width - (2 * safe_margin))
    x_max = screen_width - safe_margin
    fb_gmap = strike_cache.get("plex_sans_normal_14", ({}, 0, 0))[0]
    results = []
    print("\n" + "=" * 106)
    print(
        f"{panel_name.upper()} {screen_width}x{screen_height} ({dpi:.1f} DPI) SCREEN WIDTH AUDIT "
        f"(MAX BUDGET: {usable_budget} px [X={safe_margin}..{x_max}])"
    )
    print("=" * 106)
    print(f"{'Screen / Row':<34} | {'Legacy Mont':>11} | {'Plex Sans':>9} | {'Sans+Mono':>9} | {'Plex Cond':>9} | {'Sans Clr':>8} | {'Status'}")
    print("-" * 106)

    rows_to_run = H1OS_CANONICAL_SCREEN_ROWS
    if custom_rows:
        rows_to_run = [
            (
                r.get("screen", "Screen"),
                r.get("row", "Row"),
                r.get("left", ""),
                r.get("right", ""),
                r.get("left_font", "plex_sans_normal_14"),
                r.get("right_font", "plex_mono_normal_14"),
                int(r.get("min_gap_px", 8)),
            )
            for r in custom_rows
        ]

    for scr_name, row_desc, l_str, r_str, sans_sym, mono_sym, min_gap in rows_to_run:
        if sans_sym not in strike_cache and f"humid1_font_{sans_sym}" in strike_cache:
            sans_sym = f"humid1_font_{sans_sym}"
        if mono_sym not in strike_cache and f"humid1_font_{mono_sym}" in strike_cache:
            mono_sym = f"humid1_font_{mono_sym}"
        s_gmap = strike_cache.get(sans_sym, ({}, 0, 0))[0]
        m_gmap = strike_cache.get(mono_sym, s_gmap if not strike_cache.get(mono_sym) else ({}, 0, 0))
        if isinstance(m_gmap, tuple):
            m_gmap = m_gmap[0]
        s_kmap = kern_cache.get(sans_sym, {})
        m_kmap = kern_cache.get(mono_sym, {})

        l_sans_px = measure_lvgl_string_px(l_str, s_gmap, s_kmap, fb_gmap)
        r_sans_px = measure_lvgl_string_px(r_str, s_gmap, s_kmap, fb_gmap)
        r_mono_px = measure_lvgl_string_px(r_str, m_gmap, m_kmap, fb_gmap)

        total_sans = l_sans_px + r_sans_px
        total_mixed = l_sans_px + r_mono_px

        cond_gmap = strike_cache["plex_cond_normal_16"][0] if "plex_cond_normal_16" in strike_cache else s_gmap
        cond_kmap = kern_cache.get("plex_cond_normal_16", {})
        total_cond = (
            measure_lvgl_string_px(l_str, cond_gmap, cond_kmap, fb_gmap)
            + measure_lvgl_string_px(r_str, cond_gmap, cond_kmap, fb_gmap)
        )

        mont_sz = 20 if "20" in sans_sym else 14
        total_mont = measure_mont(l_str, mont_sz) + measure_mont(r_str, mont_sz)

        clearance = usable_budget - total_sans
        status = "PASS" if clearance >= min_gap else "WARN (TIGHT)"
        label = f"{scr_name.split(':')[0]} - {row_desc[:22]}"
        print(
            f"{label:<34} | {total_mont:>9}px | {total_sans:>7}px | {total_mixed:>7}px | {total_cond:>7}px | {clearance:>+6}px | {status}"
        )
        results.append({
            "screen": scr_name,
            "row": row_desc,
            "left_text": l_str,
            "right_text": r_str,
            "montserrat_px": total_mont,
            "plex_sans_px": total_sans,
            "plex_mixed_px": total_mixed,
            "plex_cond_16_px": total_cond,
            "clearance_px": clearance,
            "status": status,
        })
    print("=" * 106 + "\n")
    return results


def write_total_disk_size_report(
    c_out_dir: Path,
    root_out: Path,
    dist_root: Optional[Path],
    compiled_details: Sequence[dict],
    vault_path: Optional[Path],
    scheme_id: str,
    dpi: float = 188.3,
) -> Path:
    """
    Generate `total_disk_size.txt` alongside the generated `.c`/`.h` font assets so firmware
    engineers can immediately see:
      1. Expected MCU Flash (`.rodata` ROM) footprint per strike, per family, and grand total.
      2. Host `.c` + `.h` source file disk size on the filesystem.
      3. Em-square pixel size (`px` / `ppem`) vs Desktop 96-DPI Point Size (`pt@96dpi`) vs
         Physical Target-DPI Point Size (`pt@target_dpi`) and actual Line Height (`lh px`).
      4. MCU Flash partition budget utilization across 64KB, 128KB, 256KB, 512KB, 1MB, 4MB, and 8MB.
    """
    total_rom_b = sum(int(d["rom_b"]) for d in compiled_details)
    total_c_disk_b = 0
    if c_out_dir.is_dir():
        for f in c_out_dir.glob("*.c"):
            total_c_disk_b += f.stat().st_size
        for f in c_out_dir.glob("*.h"):
            total_c_disk_b += f.stat().st_size
    vault_b = vault_path.stat().st_size if (vault_path and vault_path.is_file()) else 0

    lines = [
        "=" * 116,
        f"HUMIDYNE LABS / HUMIDITRON `epd-font` v1.0.10 — FLASH ROM & DISK SIZE REPORT (total_disk_size.txt)",
        "=" * 116,
        f"  Scheme ID                    : {scheme_id}",
        f"  Target Display DPI           : {dpi:.1f} DPI (1 typographic pt = 1/72 inch = {dpi/72.0:.3f} px @ {dpi:.1f} DPI)",
        f"  Total Compiled Strikes       : {len(compiled_details)} strikes",
        f"  Expected MCU Flash (.rodata) : {total_rom_b:12,d} bytes  ({total_rom_b / 1024.0:8.2f} KB  /  {total_rom_b / (1024.0 * 1024.0):6.3f} MB)",
        f"  Host .c + .h Source Disk Size: {total_c_disk_b:12,d} bytes  ({total_c_disk_b / 1024.0:8.2f} KB  /  {total_c_disk_b / (1024.0 * 1024.0):6.3f} MB)",
        f"  Compressed Strike Vault Size : {vault_b:12,d} bytes  ({vault_b / 1024.0:8.2f} KB)",
        "-" * 116,
        "  NOTE ON SIZE UNITS (PIXELS vs TYPOGRAPHIC POINTS):",
        "    - Strike suffix numbers (e.g. `_14`, `_20`, `_32`) denote the Em-Square Height in PIXELS (`ppem`),",
        "      matching LVGL (`lv_font_montserrat_14`) and X11 BDF (`ter-u16n.bdf` = 16px) conventions.",
        f"    - Points conversion:  pt = px * 72 / DPI   (At 96 DPI: 12pt=16px, 18pt=24px, 24pt=32px; at {dpi:.1f} DPI: 16px={16*72.0/dpi:.1f}pt).",
        "    - Line Height (`lh`) = ceil(ascent * size_px / UPEM) - floor(descent * size_px / UPEM).",
        "      * Lucide Icons (`UPEM=1000, asc=+1000, desc=0`) -> lh = 1.00 * size_px (32px -> lh=32px).",
        "      * IBM Plex (`UPEM=1000, asc=+1025, desc=-275`)  -> lh = 1.30 * size_px (32px -> lh=42px).",
        "=" * 116,
        "",
        "1. MCU FLASH PARTITION BUDGET UTILIZATION (.rodata ROM)",
        "-" * 116,
        f"  {'Target Flash Budget':<30} | {'Budget Bytes':>14} | {'Used (.rodata)':>14} | {'Remaining Free':>16} | {'Utilization':>11} | {'Status'}",
        "-" * 116,
    ]

    budgets = [
        ("64 KB (Ultra-Compact MCU)", 64 * 1024),
        ("128 KB (Small Cortex-M0+/M3)", 128 * 1024),
        ("256 KB (Standard Cortex-M4)", 256 * 1024),
        ("512 KB (ESP32 UI Partition)", 512 * 1024),
        ("1 MB (1,024 KB App Flash)", 1024 * 1024),
        ("4 MB (ESP32-S3 Standard)", 4 * 1024 * 1024),
        ("8 MB (ESP32-S3-PICO-1-N8R8)", 8 * 1024 * 1024),
    ]
    for b_label, b_bytes in budgets:
        rem = b_bytes - total_rom_b
        pct = (total_rom_b * 100.0) / b_bytes
        status = "FITS" if rem >= 0 else "EXCEEDS BUDGET!"
        rem_str = f"{rem / 1024.0:+,.1f} KB"
        lines.append(
            f"  {b_label:<30} | {b_bytes:>12,d} B | {total_rom_b:>12,d} B | {rem_str:>16} | {pct:>10.2f}% | {status}"
        )

    lines.extend([
        "",
        "2. SUBTOTALS BY FONT / ICON FAMILY",
        "-" * 116,
        f"  {'Family':<18} | {'Strikes':>7} | {'Total Glyphs':>12} | {'MCU Flash (.rodata)':>22} | {'Host .c Disk Size':>22} | {'% of Flash'}",
        "-" * 116,
    ])
    fam_groups: Dict[str, List[dict]] = {}
    for d in compiled_details:
        fam_groups.setdefault(d["family"], []).append(d)
    for fam, items in fam_groups.items():
        f_rom = sum(int(x["rom_b"]) for x in items)
        f_disk = sum(int(x["c_disk_b"]) for x in items)
        f_glyphs = sum(int(x["glyph_count"]) for x in items)
        f_pct = (f_rom * 100.0 / total_rom_b) if total_rom_b > 0 else 0.0
        lines.append(
            f"  {fam:<18} | {len(items):>7d} | {f_glyphs:>12,d} | {f_rom:>10,d} B ({f_rom/1024.0:6.1f} KB) | "
            f"{f_disk:>10,d} B ({f_disk/1024.0:6.1f} KB) | {f_pct:>9.2f}%"
        )

    lines.extend([
        "",
        "3. PER-STRIKE DETAILED FLASH & DISK FOOTPRINT TABLE",
        "-" * 116,
        f"  {'Strike Symbol Name':<36} | {'Em(px)':>6} | {'pt@96':>6} | {'pt@DPI':>6} | {'LineHt':>6} | {'Glyphs':>6} | {'Kern':>5} | {'MCU Flash (.rodata)':>20} | {'Host .c Disk Size':>18}",
        "-" * 116,
    ])
    for d in compiled_details:
        sz = int(d["sz"])
        pt96 = sz * 72.0 / 96.0
        pt_dpi = sz * 72.0 / dpi
        rom_b = int(d["rom_b"])
        c_b = int(d["c_disk_b"])
        lines.append(
            f"  {d['sym_name']:<36} | {sz:>4d}px | {pt96:>4.1f}pt | {pt_dpi:>4.1f}pt | {int(d['line_h']):>4d}px | "
            f"{int(d['glyph_count']):>6,d} | {int(d['kern_count']):>5,d} | {rom_b:>9,d} B ({rom_b/1024.0:6.2f} KB) | {c_b:>8,d} B ({c_b/1024.0:5.1f} KB)"
        )
    lines.append("=" * 116)
    report_text = "\n".join(lines) + "\n"

    out_paths = [c_out_dir / "total_disk_size.txt", root_out / "total_disk_size.txt"]
    if dist_root:
        out_paths.append(dist_root / "total_disk_size.txt")
        if (dist_root / "fonts").is_dir():
            out_paths.append(dist_root / "fonts" / "total_disk_size.txt")

    for p in out_paths:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(report_text, encoding="utf-8")

    return out_paths[0]


def render_specimen_sheet(
    preview_path: Path,
    strike_cache: Dict[str, Tuple[Dict[int, GlyphStrike], int, int]],
) -> None:
    """Render master 188-DPI 1-bpp specimen contact sheet & simulated 200x200 SSD1681 panel."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return

    W, H = 1420, 1020
    img = Image.new("RGB", (W, H), (246, 247, 249))
    draw = ImageDraw.Draw(img)

    def _resolve_sym(s: str) -> Optional[str]:
        if not s:
            return next(iter(strike_cache.keys()), None)
        cands = [
            s,
            f"humid1_font_{s}",
            f"humid1_{s}",
            f"humid1_font_plex_{s}",
            s.replace("_bold_", "_normal_"),
            f"humid1_font_{s.replace('_bold_', '_normal_')}",
            "humid1_font_plex_sans_normal_14",
            "humid1_font_plex_sans_normal_12",
            "humid1_font_terminus_normal_16",
            "humid1_font_terminus_normal_12",
            "plex_sans_normal_14",
        ]
        for c in cands:
            if c in strike_cache:
                return c
        return next(iter(strike_cache.keys()), None)

    icon_fb_14: Dict[int, GlyphStrike] = {}
    icon_fb_20: Dict[int, GlyphStrike] = {}
    for k_sym, (k_gmap, _, _) in sorted(strike_cache.items()):
        if "icon_" in k_sym:
            if any(sz_tag in k_sym for sz_tag in ("_12", "_14", "_16")):
                for cp_i, g_i in k_gmap.items():
                    icon_fb_14.setdefault(cp_i, g_i)
            if any(sz_tag in k_sym for sz_tag in ("_18", "_20", "_24")):
                for cp_i, g_i in k_gmap.items():
                    icon_fb_20.setdefault(cp_i, g_i)
    if not icon_fb_14 and icon_fb_20:
        icon_fb_14 = icon_fb_20
    if not icon_fb_20 and icon_fb_14:
        icon_fb_20 = icon_fb_14

    def draw_strike_text(
        x0: int,
        y0: int,
        text: str,
        sym: str,
        fg: Tuple[int, int, int] = (15, 20, 25),
        scale: int = 1,
        fallback_sym: str = "humid1_font_plex_sans_normal_14",
    ) -> int:
        r_sym = _resolve_sym(sym)
        if not r_sym or r_sym not in strike_cache:
            return x0
        gmap, line_h, base_l = strike_cache[r_sym]
        r_fb = _resolve_sym(fallback_sym)
        fb_gmap = strike_cache.get(r_fb, ({}, 0, 0))[0] if r_fb else {}
        icon_map = icon_fb_20 if "20" in r_sym or "24" in r_sym else icon_fb_14
        cx = x0
        baseline_y = y0 + (line_h - base_l) * scale
        for ch in text:
            code = ord(ch)
            g = gmap.get(code) or fb_gmap.get(code) or icon_map.get(code)
            if not g:
                continue
            if g.box_w > 0 and g.box_h > 0:
                gx0 = cx + g.ofs_x * scale
                gy0 = baseline_y - (g.ofs_y + g.box_h) * scale
                for r_idx, row_str in enumerate(g.rows):
                    for c_idx, px in enumerate(row_str):
                        if px == "#":
                            if scale == 1:
                                draw.point((gx0 + c_idx, gy0 + r_idx), fill=fg)
                            else:
                                draw.rectangle(
                                    [
                                        gx0 + c_idx * scale,
                                        gy0 + r_idx * scale,
                                        gx0 + (c_idx + 1) * scale - 1,
                                        gy0 + (r_idx + 1) * scale - 1,
                                    ],
                                    fill=fg,
                                )
            cx += ((g.adv_w_fp4 + 8) >> 4) * scale
        return cx

    draw.rectangle([0, 0, W, 68], fill=(18, 22, 28))
    draw_strike_text(28, 16, "HUMIDYNE LABS / HUMIDITRON  |  1-BPP BILEVEL EPD TYPOGRAPHY SUITE v1.0.10 (188 DPI)", "humid1_font_plex_sans_bold_20", fg=(255, 255, 255))
    draw_strike_text(28, 44, "Engine: FreeType 1-BPP + Terminus Exact-Mono + Full-Canvas ASCII Patch Pipeline  •  200x200 Reference Panel", "humid1_font_plex_mono_normal_14", fg=(180, 195, 210))

    panel_x, panel_y = 28, 90
    draw.rectangle([panel_x - 4, panel_y - 4, panel_x + 404, panel_y + 404], fill=(40, 45, 52), outline=(18, 22, 28), width=2)
    epd = Image.new("RGB", (200, 200), (255, 255, 255))
    epd_draw = ImageDraw.Draw(epd)

    def draw_epd_text(x0: int, y0: int, text: str, sym: str, fg=(0, 0, 0), align_right_x: Optional[int] = None):
        r_sym = _resolve_sym(sym)
        if not r_sym:
            return
        gmap, line_h, base_l = strike_cache[r_sym]
        fb_sym_r = _resolve_sym("humid1_font_plex_sans_normal_14")
        fb_gmap = strike_cache.get(fb_sym_r, ({}, 0, 0))[0] if fb_sym_r else {}
        icon_map = icon_fb_20 if "20" in r_sym else icon_fb_14
        if align_right_x is not None:
            w = sum(
                (((gmap.get(ord(c)) or fb_gmap.get(ord(c)) or icon_map.get(ord(c))).adv_w_fp4 + 8) >> 4)
                for c in text
                if (gmap.get(ord(c)) or fb_gmap.get(ord(c)) or icon_map.get(ord(c)))
            )
            x0 = align_right_x - w
        cx = x0
        baseline_y = y0 + (line_h - base_l)
        for ch in text:
            code = ord(ch)
            g = gmap.get(code) or fb_gmap.get(code) or icon_map.get(code)
            if not g:
                continue
            if g.box_w > 0 and g.box_h > 0:
                gx0 = cx + g.ofs_x
                gy0 = baseline_y - (g.ofs_y + g.box_h)
                for r_idx, row_str in enumerate(g.rows):
                    for c_idx, px in enumerate(row_str):
                        if px == "#":
                            epd_draw.point((gx0 + c_idx, gy0 + r_idx), fill=fg)
            cx += (g.adv_w_fp4 + 8) >> 4

    # Simulated 200x200 SSD1681 Panel: Crisp 1px Normal stems + 2px Bold stems!
    draw_epd_text(6, 4, "HUMIDYNE LABS", "humid1_font_plex_sans_bold_14")
    epd_draw.rectangle([200 - 4 - 36, 2, 200 - 4, 2 + 17], fill=(0, 0, 0))
    draw_epd_text(200 - 4 - 28, 3, "1/5", "humid1_font_plex_mono_bold_14", fg=(255, 255, 255))
    epd_draw.line([(4, 22), (196, 22)], fill=(0, 0, 0), width=1)

    draw_epd_text(6, 30, "72.4°F", "humid1_font_plex_sans_bold_20")
    draw_epd_text(0, 30, " 46.8%", "humid1_font_plex_sans_bold_20", align_right_x=194)
    draw_epd_text(6, 58, "(22.4°C ambient • Td 10.4°C)", "humid1_font_plex_sans_normal_14")
    epd_draw.line([(4, 84), (196, 84)], fill=(0, 0, 0), width=1)

    draw_epd_text(6, 94, "TriNode ΔT", "humid1_font_plex_sans_normal_14")
    draw_epd_text(0, 94, "+0.1°C (99%)", "humid1_font_plex_sans_bold_14", align_right_x=194)
    draw_epd_text(6, 116, "Abs Humidity", "humid1_font_plex_sans_normal_14")
    draw_epd_text(0, 116, "9.3 g/m³", "humid1_font_plex_sans_bold_14", align_right_x=194)
    draw_epd_text(6, 138, "Vapor Pressure", "humid1_font_plex_sans_normal_14")
    draw_epd_text(0, 138, "12.6 hPa", "humid1_font_plex_sans_bold_14", align_right_x=194)

    epd_draw.line([(4, 166), (196, 166)], fill=(0, 0, 0), width=1)
    draw_epd_text(6, 174, "Cycle #142", "humid1_font_plex_sans_normal_14")
    draw_epd_text(0, 174, " 4.12V • 18:52", "humid1_font_plex_sans_normal_14", align_right_x=194)

    epd_zoomed = epd.resize((400, 400), resample=Image.NEAREST)
    img.paste(epd_zoomed, (panel_x, panel_y))
    draw_strike_text(panel_x, panel_y + 412, "Simulated 200x200 SSD1681 Panel (2x Nearest-Neighbor Zoom)", "humid1_font_plex_sans_bold_14")
    draw_strike_text(panel_x, panel_y + 432, "Keys: Sans Normal 14 (1px stems)  |  Values: Sans Bold 14 (2px stems)  |  Hero: Bold 20", "humid1_font_plex_sans_normal_12", fg=(70, 80, 95))

    # Bottom Left: 6x Zoomed Micro-Glyph Grid Verification
    box_y = 552
    draw.rectangle([28, box_y, 642, 992], fill=(255, 255, 255), outline=(200, 208, 218), width=1)
    draw_strike_text(44, box_y + 14, "1-BIT MONOCHROME ENGINE + ASCII PATCH VERIFICATION (6x Pixel Grid)", "humid1_font_plex_sans_bold_14")
    draw_strike_text(44, box_y + 36, "FT_LOAD_TARGET_MONO + font_icon_epd_patches.json resolve counter-fill and preserve 1px/2px hierarchy:", "humid1_font_plex_sans_normal_12", fg=(70, 80, 95))

    showcase_glyphs = [
        ("humid1_font_plex_sans_normal_14", 0x0040, "Sans 14 '@'"),
        ("humid1_font_plex_sans_normal_14", 0x0025, "Sans 14 '%'"),
        ("humid1_font_plex_sans_normal_14", 0x0065, "Sans 14 'e'"),
        ("humid1_font_plex_sans_normal_14", 0x0061, "Sans 14 'a'"),
        ("humid1_font_plex_mono_normal_14", 0x0030, "Mono 14 '0'"),
        ("humid1_font_plex_mono_normal_14", 0x0025, "Mono 14 '%'"),
        ("humid1_font_terminus_normal_16", 0x0041, "Term 16 'A'"),
    ]
    px_x = 44
    for sym_key, code_c, label in showcase_glyphs:
        r_sk = _resolve_sym(sym_key)
        g_obj = strike_cache.get(r_sk, ({}, 0, 0))[0].get(code_c) if r_sk else None
        if not g_obj:
            continue
        draw_strike_text(px_x, box_y + 64, label, "humid1_font_plex_sans_bold_12")
        cell = 7
        gy0 = box_y + 86
        for r_i, r_s in enumerate(g_obj.rows):
            for c_i, ch_p in enumerate(r_s):
                rx = px_x + c_i * cell
                ry = gy0 + r_i * cell
                fill_c = (15, 20, 25) if ch_p == "#" else (238, 242, 246)
                draw.rectangle([rx, ry, rx + cell - 2, ry + cell - 2], fill=fill_c)
        px_x += 83

    draw_strike_text(44, box_y + 196, "1:1 Native 188 DPI Readout (>=2px Medium Stems + Closed-Loop Auto-Floor):", "humid1_font_plex_sans_bold_14")
    draw_strike_text(44, box_y + 222, "Sans 12px:  Sphinx of black quartz, judge my vow  |  0123456789  @ % # $ & 8 0 e a s g y ± µ °", "humid1_font_plex_sans_normal_12")
    draw_strike_text(44, box_y + 246, "Sans 14px:  Sphinx of black quartz, judge my vow  |  0123456789  @ % # $ & 8 0 e a s g y", "humid1_font_plex_sans_normal_14")
    draw_strike_text(44, box_y + 272, "Term 12px:  0123456789  72.4°F  46.8% RH  9.3 g/m³  @ % # $ & 8 0 e a s g y", "humid1_font_terminus_normal_12")
    draw_strike_text(44, box_y + 296, "Mono 14px:  0123456789  72.4°F  46.8% RH  9.3 g/m³  @ % # $ & 8 0 e a s", "humid1_font_plex_mono_normal_14")
    draw_strike_text(44, box_y + 324, "Math 16px:  ΔT = +0.15°C  •  ∀x ∈ ℝ : ∑ f(x) ≈ √π ± ∞  •  α β γ δ ε θ λ μ π σ ω Ω", "humid1_font_plex_math_regular_16")

    icon_strip_str = "               "
    icon_strip_sym = "humid1_icon_fa7_solid_16"
    if icon_strip_sym not in strike_cache:
        for cand_ic in ("humid1_icon_phosphor_regular_16", "humid1_icon_lucide_regular_16", "humid1_icon_tabler_regular_16"):
            if cand_ic in strike_cache:
                icon_strip_sym = cand_ic
                sample_cps = sorted(c for c in strike_cache[cand_ic][0].keys() if c >= 0xE000)[:16]
                icon_strip_str = " ".join(chr(c) for c in sample_cps)
                break
    draw_strike_text(44, box_y + 354, "Icons 16px:", "humid1_font_plex_sans_bold_14")
    draw_strike_text(132, box_y + 354, icon_strip_str, icon_strip_sym)

    # Right Column: Complete Sub-Family & Size Ladder Showcase
    rx0 = 664
    draw.rectangle([rx0, 90, 1392, 992], fill=(255, 255, 255), outline=(200, 208, 218), width=1)
    draw_strike_text(rx0 + 20, 106, "HUMID1 1-BPP SUB-FAMILY & SIZE LADDER (1:1 NATIVE PIXELS @ 188 DPI)", "humid1_font_plex_sans_bold_16")

    ladder_rows = [
        ("Sans Normal 12px (4.6pt@188dpi, >=2px Auto-Floored)", "humid1_font_plex_sans_normal_12", "Humidyne humid1  •  22.4°C  48.2% RH  9.3 g/m³  @%#&80"),
        ("Sans Normal 14px (5.4pt@188dpi, Default UI)", "humid1_font_plex_sans_normal_14", "Humidyne humid1  •  22.4°C  48.2% RH  9.3 g/m³  @%#&80"),
        ("Sans Bold 14px (5.4pt@188dpi, 2px stems)", "humid1_font_plex_sans_bold_14", "PSYCHROMETRICS  •  SYSTEM HEALTH  •  SETTLED (99%)"),
        ("Sans Italic 14px (Metadata)", "humid1_font_plex_sans_italic_14", "(22.4°C ambient  •  TriNode thermal equilibrium active)"),
        ("Sans Normal 16px (6.1pt@188dpi, Body MD)", "humid1_font_plex_sans_normal_16", "TriNode ΔT: +0.1°C  |  Vapor Pressure: 12.6 hPa"),
        ("Sans Bold 16px (6.1pt@188dpi, Modal Title)", "humid1_font_plex_sans_bold_16", "ENVIRONMENTAL TELEMETRY & DEW POINT"),
        ("Sans Bold 20px (7.6pt@188dpi, Section Hero)", "humid1_font_plex_sans_bold_20", "72.4°F    46.8% RH    4.12V"),
        ("Sans Bold 24px (9.2pt@188dpi, Primary Readout)", "humid1_font_plex_sans_bold_24", "72.4°F  |  46.8% RH  |  Td 50.7°F"),
        ("Sans Bold 32px (12.2pt@188dpi, Jumbo Metric)", "humid1_font_plex_sans_bold_32", "72.4°F   46.8%"),
        ("Terminus Normal 12px (6x12 Native Console)", "humid1_font_terminus_normal_12", "boot: humid1-os v1.0.10  |  SPI0 40MHz  |  0x0040 @%#08"),
        ("Terminus Normal 16px (8x16 Native Console)", "humid1_font_terminus_normal_16", "root@humid1:~# dmesg | grep epd -> 200x200 OK"),
        ("Mono Normal 14px (Telemetry Log)", "humid1_font_plex_mono_normal_14", "2026-11-03 20:24:55  |  328K Free  |  @%#08"),
        ("Mono Bold 20px (Tabular Readout)", "humid1_font_plex_mono_bold_20", "72.4°F   46.8% RH   12.6 hPa"),
        ("Mono Bold 24px (Tabular Hero)", "humid1_font_plex_mono_bold_24", "72.4°F  |  46.8% RH"),
        ("Condensed Normal 16px (Narrow Dock)", "humid1_font_plex_cond_normal_16", "NARROW DOCK:  SHTC3 22.4°C  |  SSD1681 22.5°C  |  MCU 22.6°C"),
        ("Serif Normal 18px (Editorial Body)", "humid1_font_plex_serif_normal_18", "Thermodynamic water vapor pressure & dew point invariants."),
        ("Math Regular 16px (Scientific Formula)", "humid1_font_plex_math_regular_16", "e_s(T) = 6.1094 · exp(17.625·T / (T + 243.04))   [ΔT ≤ 0.15°C]"),
    ]

    label_font_sym = _resolve_sym("humid1_font_plex_mono_normal_12") or _resolve_sym("humid1_font_terminus_normal_12") or _resolve_sym("humid1_font_plex_sans_normal_12")
    cy = 136
    for label, sym, sample in ladder_rows:
        if sym not in strike_cache:
            continue
        if cy > 945:
            break
        draw_strike_text(rx0 + 20, cy, label, label_font_sym, fg=(100, 112, 128))
        cy += 15
        _, lh, _ = strike_cache[sym]
        draw_strike_text(rx0 + 20, cy, sample, sym, fg=(10, 14, 18))
        cy += lh + 7
        draw.line([(rx0 + 20, cy - 3), (1372, cy - 3)], fill=(232, 236, 242), width=1)

    preview_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(preview_path))
    print(f"[+] Rendered master 188-DPI visual specimen sheet to {preview_path}")


# =============================================================================
# 12. UNIFIED CLI, JSON SCHEME LOADER & 4-WORKFLOW PIPELINE ORCHESTRATION (v0.0.6)
# =============================================================================

def resolve_charset_spec_to_range_str(cs_entry: dict, default_vendor: str = "", style: str = "") -> str:
    """
    Convert a character_set entry from a scheme JSON into a comma-separated hex/dec range string.
    Supports three ways of scoping characters/icons in `schemes/*.json`:
      1. `"ranges": "0x0020-0x007E,0x00B0"` (hex/decimal codepoints or ranges)
      2. `"icons": ["wifi", "battery-full", "thermometer"]` (human-readable semantic icon names!)
      3. `"scope": "all"` (includes every icon in the vendor catalog)
    """
    parts: List[str] = []
    if "ranges" in cs_entry and cs_entry["ranges"]:
        parts.append(str(cs_entry["ranges"]).strip())

    vendor = cs_entry.get("vendor", default_vendor)
    if vendor == "icon_tabler" and style == "filled" and "icon_tabler_filled" in ICON_NAME_REGISTRY.get("by_name", {}):
        vendor = "icon_tabler_filled"
    by_name_map = ICON_NAME_REGISTRY.get("by_name", {}).get(vendor, {})
    if not by_name_map and vendor in ICON_NAME_REGISTRY and isinstance(ICON_NAME_REGISTRY[vendor], dict):
        # Build reverse name -> hex lookup from cp -> name map
        by_name_map = {v: k for k, v in ICON_NAME_REGISTRY[vendor].items()}

    if cs_entry.get("scope", "").lower() == "all" and by_name_map:
        parts.extend(sorted(set(by_name_map.values())))

    if "icons" in cs_entry and isinstance(cs_entry["icons"], list):
        for icon_name in cs_entry["icons"]:
            iname = str(icon_name).strip()
            if iname.startswith("0x") or iname.isdigit():
                parts.append(iname)
            elif iname in by_name_map:
                parts.append(by_name_map[iname])
            else:
                # Case-insensitive fallback
                iname_low = iname.lower()
                for k, hex_v in by_name_map.items():
                    if k.lower() == iname_low:
                        parts.append(hex_v)
                        break

    return ",".join(p for p in parts if p)


DEFAULT_ICON_FALLBACK_RANGES = {
    "icon_fa7": "0xF00C,0xF00D,0xF013,0xF015,0xF017,0xF021,0xF023,0xF043,0xF058,0xF071,0xF0E7,0xF1EB,0xF240-0xF244,0xF2C9,0xF2DB",
    "icon_lucide": "0xE01D,0xE053,0xE054,0xE070,0xE0B4,0xE17C,0xE1A1,0xE1AA,0xE1D8,0xE1FB",
    "icon_phosphor": "0xE002,0xE026,0xE06A,0xE094,0xE13E,0xE14E,0xE1F4,0xE208,0xE270,0xE482,0xE4EA,0xE60C",
    "icon_tabler": "0xEA02,0xEA08,0xEA30,0xEA31,0xEA32,0xEA34,0xEA38,0xEA52,0xEB3D,0xEB52",
    "icon_tabler_filled": "0xEE80,0xF327,0xF667,0xF668,0xF669,0xF66A,0xF66B,0xF66C,0xF66D,0xF66E",
}

def load_plan_from_scheme_json(scheme_path: Path) -> Tuple[dict, List[Tuple[str, str, List[int], str, bool, Optional[str], str]]]:
    """
    Parse a declarative JSON scheme file (`schemes/*.json`) into a normalized strike plan.
    Supports both hex `ranges` and human-readable `icons` name lists, and prevents `icon_*`
    families from ever falling back to ASCII `RANGE_UI_STR`.
    """
    scheme = json.loads(scheme_path.read_text(encoding="utf-8"))
    char_sets = scheme.get("character_sets", {})
    plan_out = []
    for entry in scheme.get("strikes", []):
        fam = entry["family"]
        style = entry.get("style", "normal")
        if "ttf_file" in entry and entry["ttf_file"]:
            style = f"custom:{entry['ttf_file']}"
        sizes = list(entry["sizes"])
        cset_names = entry.get("char_sets", [] if fam.startswith("icon_") else ["ascii_printable"])
        iset_names = entry.get("icon_sets", [])

        u_ranges = []
        for cn in cset_names:
            if cn in char_sets:
                r_str = resolve_charset_spec_to_range_str(char_sets[cn], default_vendor=fam, style=style)
                if r_str:
                    u_ranges.append(r_str)
        if u_ranges:
            combined_u_range = ",".join(u_ranges)
        elif fam.startswith("icon_"):
            combined_u_range = DEFAULT_ICON_FALLBACK_RANGES.get(fam, "0xE000-0xE03F")
        else:
            combined_u_range = RANGE_UI_STR

        fa_ranges = []
        for iname in iset_names:
            if iname in char_sets:
                r_str = resolve_charset_spec_to_range_str(char_sets[iname], default_vendor="icon_fa7")
                if r_str:
                    fa_ranges.append(r_str)
        combined_fa_range = ",".join(fa_ranges)
        inc_fa = len(fa_ranges) > 0

        fb_pat = entry.get("fallback", None)
        plan_out.append((fam, style, sizes, combined_u_range, inc_fa, fb_pat, combined_fa_range))
    return scheme, plan_out


def export_strike_vault(vault_path: Path, vault_data: dict) -> int:
    """Export pre-rasterized, patch-applied Strike Vault (.json.gz or .json) for humid1_fw_emit.py."""
    import gzip
    vault_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(vault_data, separators=(",", ":"))
    if vault_path.name.endswith(".gz"):
        with gzip.open(vault_path, "wt", encoding="utf-8", compresslevel=9) as f:
            f.write(payload)
    else:
        vault_path.write_text(payload, encoding="utf-8")
    return vault_path.stat().st_size


def build_arg_parser() -> argparse.ArgumentParser:
    epilog_text = """
Unified Directory Architecture (1 Input Dir, 1 Output Dir):
-----------------------------------------------------------
  --src-dir <dir> : Points to your static TTF folder (default: <repo>/assets/static_ttfs).
                    If <repo>/assets is passed, it automatically locates `static_ttfs/`
                    (or invokes `build_static_ttf_assets.py` if not yet built).
  --out-dir <dir> : Single root output directory (default: <repo>/build).
                    Automatically organizes generated outputs into clean subfolders:
                      <out-dir>/fonts/          -> LVGL v9 .c modules, plex_fonts.h, h1os_fonts.h, licenses/
                      <out-dir>/dist/           -> Pre-rasterized Strike Vault (humid1_epd_vault.json.gz)
                      <out-dir>/bdf/            -> Adobe BDF 2.1 bitmap font strikes
                      <out-dir>/metrics/        -> Per-strike glyph width & kerning CSV tables
                      <out-dir>/inspect_pages/  -> Auto-wrapped Page Check PNGs + 188-DPI Specimen PNG
                      <out-dir>/inspect_chars/  -> 18x-24x Char-by-Char Deep-Check Blueprint PNGs

Examples:
---------
  1. Build C/H Fonts, BDFs, CSVs, and Strike Vault into `<repo>/build`:
     python tools/fonts/humid1_generate_1bpp.py --workflow build

  2. Run Visual Check (Page Check PNGs + Char Blueprint PNGs + 200x200 Screen Audit):
     python tools/fonts/humid1_generate_1bpp.py --workflow check

  3. Dump Editable Full-Canvas 1:1 Spaced ASCII Patch Files:
     python tools/fonts/humid1_generate_1bpp.py --workflow patch --dump

  4. Compile Edited ASCII Patch Files into `font_icon_epd_patches.json`:
     python tools/fonts/humid1_generate_1bpp.py --workflow patch --apply

  5. Execute Entire Pipeline End-to-End (`all`):
     python tools/fonts/humid1_generate_1bpp.py --workflow all
"""
    parser = argparse.ArgumentParser(
        prog="humid1_generate_1bpp.py",
        description=(
            "Humidyne Labs / Humiditron `epd-font` v1.0.10 — General-Purpose 1-BPP Font & Modular Icon Studio.\n"
            "Supports 4 workflows: 'gen-assets', 'patch', 'check', and 'build' (plus 'all')."
        ),
        epilog=epilog_text,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "-w", "--workflow",
        choices=["gen-assets", "patch", "check", "build", "repair", "all"],
        default="build",
        help=(
            "Select workflow stage (default: build):\n"
            "  gen-assets : Build static .ttf files & metadata JSONs from raw assets\n"
            "  patch      : Dump (--dump) or compile (--apply) Full-Canvas 1:1 ASCII .txt glyph patches\n"
            "  repair     : Closed-loop OpenCV auto-floor (>=2px stem) & counter-protection repair + diff PNGs\n"
            "  check      : Render Page Check PNGs, Char-by-Char Blueprint PNGs & 200x200 screen audit\n"
            "  build      : Emit LVGL v9 1-bpp .c/.h files, BDFs, CSV metrics & Strike Vault\n"
            "  all        : Run gen-assets -> repair -> patch -> build -> check in sequence"
        ),
    )
    parser.add_argument(
        "-S", "--scheme",
        type=str,
        default=None,
        help="Path to declarative JSON scheme file (default: tools/fonts/schemes/h1os_epd_scheme.json)",
    )
    parser.add_argument(
        "-s", "--src-dir",
        type=str,
        default=None,
        help="Single input directory containing static .ttf assets (default: <repo>/assets/static_ttfs)",
    )
    parser.add_argument(
        "-o", "--out-dir",
        type=str,
        default=None,
        help="Single output root directory for all generated artifacts (default: <repo>/build)",
    )
    parser.add_argument(
        "-p", "--patches",
        type=str,
        default=None,
        help="Path to JSON optical patch manifest (default: tools/fonts/font_icon_epd_patches.json)",
    )
    parser.add_argument(
        "-a", "--ascii-dir",
        type=str,
        default=None,
        help="Directory for Full-Canvas 1:1 Spaced ASCII .txt glyph folders (default: tools/fonts/ascii_patches)",
    )
    parser.add_argument(
        "--dump",
        action="store_true",
        help="In '--workflow patch', dump strikes to Full-Canvas 1:1 Spaced ASCII .txt folders",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="In '--workflow patch', compile modified ASCII .txt files into --patches JSON",
    )
    parser.add_argument(
        "--trouble-only",
        action="store_true",
        help="When dumping ASCII .txt files, export only the 15 high-density 'trouble' characters per strike",
    )
    parser.add_argument(
        "--unicode-preview",
        action="store_true",
        help="Opt-in flag to include the UTF-8 Unicode 1:1 block preview header in dumped ASCII .txt files",
    )
    parser.add_argument(
        "--inspect-chars-filter",
        choices=["all", "trouble", "patched", "ascii", "none"],
        default="all",
        help="Which characters to render in <out-dir>/inspect_chars/ (default: all)",
    )
    parser.add_argument(
        "--sizes",
        type=int,
        nargs="+",
        default=None,
        help="Optional pixel sizes filter (e.g. --sizes 14 16 20 24)",
    )
    parser.add_argument(
        "--families",
        type=str,
        nargs="+",
        default=None,
        help="Optional families filter (e.g. --families sans mono icon_lucide)",
    )
    parser.add_argument(
        "--normal-weight",
        type=int,
        choices=[100, 200, 300, 400, 450, 500, 600, 700],
        default=500,
        help="OpenType weight for 'normal' slot (default: 500 Medium for >=2px EPD stem legibility)",
    )
    parser.add_argument(
        "--min-stem",
        type=int,
        default=2,
        help="Minimum stem thickness in pixels enforced by closed-loop auto-floor (default: 2)",
    )
    parser.add_argument(
        "--auto-floor",
        dest="auto_floor",
        action="store_true",
        default=True,
        help="Enable closed-loop OpenCV >=2px stem auto-floor & counter protection (default: enabled)",
    )
    parser.add_argument(
        "--no-auto-floor",
        dest="auto_floor",
        action="store_false",
        help="Disable closed-loop morphological stem auto-floor",
    )
    parser.add_argument(
        "--repair-engine",
        choices=["hybrid", "autofloor", "downscale", "contour"],
        default="hybrid",
        help="Closed-loop glyph repair engine (default: hybrid)",
    )
    parser.add_argument(
        "--save-repaired-patches",
        action="store_true",
        help="Save auto-repaired glyphs into --patches JSON during --workflow repair",
    )
    parser.add_argument(
        "--raster-mode",
        choices=["autohint-mono", "bytecode-mono", "gray-threshold"],
        default="autohint-mono",
        help="FreeType 1-bpp rasterizer mode (default: autohint-mono)",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=128,
        help="Grayscale threshold (0-255) when --raster-mode=gray-threshold",
    )
    parser.add_argument(
        "--audit-screens",
        action="store_true",
        help="Run automated horizontal screen width budget audit using target display geometry",
    )
    parser.add_argument(
        "--dpi",
        type=float,
        default=None,
        help="Target display pixel density in DPI (default: from scheme JSON or 188.3)",
    )
    parser.add_argument(
        "--screen-width",
        type=int,
        default=None,
        help="Target display horizontal width in pixels (default: from scheme JSON or 200)",
    )
    parser.add_argument(
        "--screen-height",
        type=int,
        default=None,
        help="Target display vertical height in pixels (default: from scheme JSON or 200)",
    )
    parser.add_argument(
        "--safe-margin",
        type=int,
        default=None,
        help="Horizontal safe margin in pixels on each side (default: from scheme JSON or 6)",
    )
    parser.add_argument(
        "--dist-dir",
        type=str,
        default=None,
        help="Output directory for distributable Strike Vault & firmware bundle (default: <repo>/dist)",
    )
    parser.add_argument(
        "--keep-noop-kern",
        action="store_true",
        help="Retain sub-pixel GPOS kerning pairs that round to 0px at target strike size",
    )
    parser.add_argument(
        "-j", "--jobs",
        type=int,
        default=None,
        help="Number of parallel CPU worker processes (default: all host CPU cores)",
    )

    # Hidden legacy flags for 100% backward compatibility with older scripts/commands
    parser.add_argument("--profile", choices=["h1os", "humid1", "full"], default="h1os", help=argparse.SUPPRESS)
    parser.add_argument("--plex-dir", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--font-dir", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--dump-ascii-dir", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--build-ascii-dir", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--ascii-patch-dir", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--inspect-png-dir", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--inspect-chars-dir", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--export-vault", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--export-bdf", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--metrics-dir", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--render-preview", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--montserrat-metrics-dir", type=str, default=None, help=argparse.SUPPRESS)
    return parser



_WORKER_FT = None
_WORKER_FT_LIB = None
_WORKER_FONT_DIR = None


def _execute_strike_worker_task(task: dict) -> dict:
    """ProcessPoolExecutor worker that rasterizes and emits all artifacts for a single strike."""
    global _WORKER_FT, _WORKER_FT_LIB, _WORKER_FONT_DIR
    font_dir = Path(task["font_dir"])
    if _WORKER_FT is None:
        _WORKER_FT, _WORKER_FT_LIB = load_freetype()
    if _WORKER_FONT_DIR != task["font_dir"]:
        load_icon_name_registry(font_dir)
        _WORKER_FONT_DIR = task["font_dir"]

    sym_name = task["sym_name"]
    family = task["family"]
    role = task["role"]
    sz = task["sz"]
    ttf_path = Path(task["ttf_path"])
    effective_raster_m = task["effective_raster_m"]
    strike_ascii_dir = Path(task["strike_ascii_dir"]) if task["strike_ascii_dir"] else None

    # If inspect_repairs_root is active, first rasterize without auto_floor to capture before/after diff records
    repair_sheet_written = 0
    if task.get("inspect_repairs_root") and not family.startswith("icon_"):
        raw_glyphs, _, _, _, _, _ = rasterize_font_strike(
            ft=_WORKER_FT,
            ft_lib=_WORKER_FT_LIB,
            font_path=ttf_path,
            size_px=sz,
            codepoints=task["codepoints"],
            raster_mode=effective_raster_m,
            threshold=task["threshold"],
            fa_path=None,
            fa_codepoints=None,
            patch_dict=task["strike_patches"],
            ascii_override_dir=strike_ascii_dir,
            enable_kerning=False,
            prune_noop_kern=True,
            auto_floor=False,
        )
    else:
        raw_glyphs = []

    glyphs, line_h, base_l, upos, uthk, kern_pairs = rasterize_font_strike(
        ft=_WORKER_FT,
        ft_lib=_WORKER_FT_LIB,
        font_path=ttf_path,
        size_px=sz,
        codepoints=task["codepoints"],
        raster_mode=effective_raster_m,
        threshold=task["threshold"],
        fa_path=None,
        fa_codepoints=None,
        patch_dict=task["strike_patches"],
        ascii_override_dir=strike_ascii_dir,
        enable_kerning=task["enable_kern"],
        prune_noop_kern=task["prune_noop_kern"],
        auto_floor=task.get("auto_floor", True),
        min_stem=task.get("min_stem", 2),
        repair_engine=task.get("repair_engine", "hybrid"),
    )

    if task.get("inspect_repairs_root") and raw_glyphs:
        try:
            import humid1_bilevel_tuner as _bt
            recs = []
            for g_bef in raw_glyphs:
                if not g_bef.rows:
                    continue
                arr_bef = _bt.rows_to_binary_array(g_bef.rows)
                is_m = family in ("mono", "terminus", "unifont")
                max_w = (g_bef.adv_w_fp4 >> 4) if is_m else ((g_bef.adv_w_fp4 >> 4) + 1)
                _, rec = _bt.inspect_and_repair_glyph_bitmap(
                    arr_bef,
                    codepoint=g_bef.codepoint,
                    min_stem=task.get("min_stem", 2),
                    max_width_ceiling=max_w,
                    engine=task.get("repair_engine", "hybrid"),
                )
                recs.append(rec)
            rep_png = Path(task["inspect_repairs_root"]) / f"{sym_name}_repair.png"
            _bt.render_repair_comparison_sheet(rep_png, sym_name, sz, recs)
            repair_sheet_written = 1
        except Exception:
            pass

    if task["do_build_c"] and task["c_out_dir"]:
        out_file = Path(task["c_out_dir"]) / f"{sym_name}.c"
        rom_b = emit_lvgl_c_file(
            out_file=out_file,
            font_symbol_name=sym_name,
            size_px=sz,
            family=family,
            role=role,
            raster_mode=effective_raster_m,
            glyphs=glyphs,
            line_height=line_h,
            base_line=base_l,
            underline_pos=upos,
            underline_thick=uthk,
            kern_pairs=kern_pairs,
            fallback_symbol=task["fb_sym"],
        )
    else:
        rom_b = sum(len(g.pack_1bpp_bytes()) for g in glyphs) + (len(glyphs) + 1) * 8 + len(kern_pairs) * 3 + 120

    ascii_dumped = 0
    if task["dump_ascii_root"]:
        s_dump_dir = Path(task["dump_ascii_root"]) / sym_name
        ascii_dumped = dump_strike_to_ascii_folder(
            s_dump_dir,
            sym_name,
            glyphs,
            size_px=sz,
            line_height=line_h,
            base_line=base_l,
            trouble_only=task["trouble_only"],
            unicode_preview=task["unicode_preview"],
            family=family,
        )

    png_pages = 0
    if task["inspect_png_root"]:
        png_file = Path(task["inspect_png_root"]) / f"{sym_name}.png"
        png_pages = render_full_font_inspection_png(
            out_png=png_file,
            font_symbol_name=sym_name,
            family=family,
            role=role,
            size_px=sz,
            raster_mode=effective_raster_m,
            line_height=line_h,
            base_line=base_l,
            glyphs=glyphs,
            rom_bytes=rom_b,
            static_dir=font_dir,
        )

    char_pngs = 0
    if task["inspect_chars_root"]:
        s_char_dir = Path(task["inspect_chars_root"]) / sym_name
        char_pngs = render_char_by_char_folder(
            strike_char_dir=s_char_dir,
            font_symbol_name=sym_name,
            family=family,
            role=role,
            size_px=sz,
            raster_mode=effective_raster_m,
            line_height=line_h,
            base_line=base_l,
            glyphs=glyphs,
            char_filter=task["inspect_chars_filter"],
            static_dir=font_dir,
        )

    if task["bdf_out_dir"]:
        bdf_path = Path(task["bdf_out_dir"]) / f"{sym_name}.bdf"
        export_bdf_strike(bdf_path, sym_name, sz, 188, line_h, base_l, glyphs)

    if task["metrics_out_dir"]:
        export_metric_csvs(Path(task["metrics_out_dir"]), sym_name, glyphs, kern_pairs)

    vault_entry = {
        "family": family,
        "style": role,
        "size_px": sz,
        "source_ttf": task["ttf_name"],
        "line_height": line_h,
        "base_line": base_l,
        "glyphs": [
            {
                "cp": g.codepoint,
                "name": get_semantic_glyph_name(g.codepoint, family),
                "gid": g.glyph_id,
                "adv_w_fp4": g.adv_w_fp4,
                "box_w": g.box_w,
                "box_h": g.box_h,
                "ofs_x": g.ofs_x,
                "ofs_y": g.ofs_y,
                "rows": g.rows,
                "patched": g.patched,
            }
            for g in glyphs
            if g.codepoint > 0
        ],
        "kern_pairs": [[l_gid, r_gid, kv] for (l_gid, r_gid, _, _, kv) in kern_pairs],
    }

    c_disk_b = 0
    if task["do_build_c"] and task["c_out_dir"]:
        cf = Path(task["c_out_dir"]) / f"{sym_name}.c"
        if cf.is_file():
            c_disk_b = cf.stat().st_size

    pt96 = sz * 72.0 / 96.0
    patched_cnt = sum(1 for g in glyphs if g.patched)
    patch_tag = f" [+{patched_cnt} patches]" if patched_cnt else ""
    log_line = (
        f"    [+] {sym_name:<36} | {len(glyphs):>4} glyphs | {len(kern_pairs):>4} kern | "
        f"em={sz:>2}px ({pt96:>4.1f}pt) lh={line_h:>2}px | {effective_raster_m:<13} | ~{rom_b:>7,} B ({rom_b/1024:.2f} KB){patch_tag}"
    )
    return {
        "sym_name": sym_name,
        "c_disk_b": c_disk_b,
        "family": family,
        "role": role,
        "sz": sz,
        "rom_b": rom_b,
        "glyphs": glyphs,
        "line_h": line_h,
        "base_l": base_l,
        "kern_pairs": kern_pairs,
        "ascii_dumped": ascii_dumped,
        "png_pages": png_pages,
        "char_pngs": char_pngs,
        "vault_entry": vault_entry,
        "log_line": log_line,
    }


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent if script_dir.name == "fonts" else script_dir.parent
    parser = build_arg_parser()
    args = parser.parse_args()

    # 1. Resolve unified --src-dir (Static TTFs live in <repo>/build/static_ttfs by default in v1.0.10)
    raw_src_arg = args.src_dir or args.font_dir
    if raw_src_arg:
        cand_src = Path(raw_src_arg).resolve()
        if (cand_src / "static_ttfs").is_dir():
            font_dir = (cand_src / "static_ttfs").resolve()
        else:
            font_dir = cand_src
    else:
        font_dir = (repo_root / "build" / "static_ttfs").resolve()

    # If workflow is gen-assets or build/static_ttfs is missing, invoke build_static_ttf_assets.py
    if args.workflow == "gen-assets" or not (font_dir / "IBMPlexSans-Regular.ttf").is_file():
        sys.path.insert(0, str(script_dir))
        import build_static_ttf_assets as bsta
        raw_assets_root = Path(args.plex_dir).resolve() if args.plex_dir else (repo_root / "assets").resolve()
        bsta.build_all_static_assets(
            src_dir=raw_assets_root,
            out_dir=font_dir,
            meta_out_dir=(repo_root / "build" / "metadata").resolve(),
            force=(args.workflow == "gen-assets"),
        )
        if args.workflow == "gen-assets":
            bsta.verify_static_ttf_directory(font_dir)
            return

    # 2. Resolve unified --out-dir (inside <repo>/build) and --dist-dir (inside <repo>/dist)
    base_out = Path(args.out_dir).resolve() if args.out_dir else (repo_root / "build").resolve()
    if base_out.name == "fonts" and base_out.parent.name == "assets":
        c_out_dir = base_out
        root_out = base_out.parent.parent
    else:
        root_out = base_out
        c_out_dir = root_out / "fonts"

    dist_root = Path(args.dist_dir).resolve() if args.dist_dir else (repo_root / "dist").resolve()

    # Root-tracked patch manifest (`<repo>/font_icon_epd_patches.json` with fallback to `tools/fonts/font_icon_epd_patches.json`)
    if args.patches:
        patches_path = Path(args.patches).resolve()
    elif (repo_root / "font_icon_epd_patches.json").is_file():
        patches_path = (repo_root / "font_icon_epd_patches.json").resolve()
    else:
        patches_path = (script_dir / "font_icon_epd_patches.json").resolve()

    # `ascii_patches` MUST exist inside `build/` (`<root_out>/ascii_patches`)
    default_ascii_dir = Path(args.ascii_dir).resolve() if args.ascii_dir else (root_out / "ascii_patches").resolve()

    # Determine active sub-operations from --workflow + any explicit legacy overrides
    do_build_c = args.workflow in ("build", "all") or (args.out_dir is not None and args.workflow not in ("check", "patch"))
    do_check_png = args.workflow in ("check", "all") or (args.inspect_png_dir is not None)
    do_dump_ascii = args.dump or (args.workflow == "all") or (args.dump_ascii_dir is not None)
    do_apply_ascii = args.apply or (args.build_ascii_dir is not None) or (args.workflow == "patch" and not args.dump)

    dump_ascii_root = Path(args.dump_ascii_dir).resolve() if args.dump_ascii_dir else (default_ascii_dir if do_dump_ascii else None)
    apply_ascii_root = Path(args.build_ascii_dir).resolve() if args.build_ascii_dir else (default_ascii_dir if do_apply_ascii else None)
    ascii_ingest_root = Path(args.ascii_patch_dir).resolve() if args.ascii_patch_dir else (default_ascii_dir if default_ascii_dir.is_dir() else None)

    inspect_png_root = Path(args.inspect_png_dir).resolve() if args.inspect_png_dir else ((root_out / "inspect_pages") if do_check_png else None)
    inspect_chars_root = (
        Path(args.inspect_chars_dir).resolve()
        if args.inspect_chars_dir
        else ((root_out / "inspect_chars") if (do_check_png and args.inspect_chars_filter != "none") else None)
    )
    bdf_out_dir = Path(args.export_bdf).resolve() if args.export_bdf else ((root_out / "bdf") if do_build_c else None)
    metrics_out_dir = Path(args.metrics_dir).resolve() if args.metrics_dir else ((root_out / "metrics") if (do_build_c or do_check_png) else None)
    vault_out_path = Path(args.export_vault).resolve() if args.export_vault else ((dist_root / "humid1_epd_vault.json.gz") if do_build_c else None)
    specimen_out_path = Path(args.render_preview).resolve() if args.render_preview else ((root_out / "inspect_pages" / "humid1_epd_specimen_188dpi.png") if do_check_png else None)

    # Step 2: Compile ASCII .txt edits into patches_path JSON if requested
    if apply_ascii_root and apply_ascii_root.is_dir():
        cnt = build_patches_json_from_ascii_root(apply_ascii_root, patches_path, only_modified=True)
        print(f"[+] Compiled {cnt} modified ASCII glyph patch(es) from {apply_ascii_root} -> {patches_path}")
        if args.workflow == "patch" and not do_dump_ascii:
            return

    patch_manifest: dict = {"patches": {}}
    if patches_path.is_file():
        loaded_p = json.loads(patches_path.read_text(encoding="utf-8"))
        if "patches" in loaded_p:
            patch_manifest = loaded_p
        else:
            for k, v in loaded_p.items():
                if not k.startswith("_") and isinstance(v, dict):
                    patch_manifest["patches"][k] = v
        print(f"[+] Loaded optical micro-strike patch manifest: {patches_path}")

    load_icon_name_registry(font_dir)
    ft, ft_lib = load_freetype()

    # Load scheme JSON (defaults to tools/fonts/schemes/humid1_reference.scheme.json or first available scheme)
    if args.scheme:
        scheme_path = Path(args.scheme).resolve()
    elif (script_dir / "schemes" / "humid1_reference.scheme.json").is_file():
        scheme_path = (script_dir / "schemes" / "humid1_reference.scheme.json").resolve()
    else:
        scheme_path = (script_dir / "schemes" / "h1os_epd_scheme.json").resolve()
    scheme_cfg: Optional[dict] = None
    if scheme_path.is_file():
        scheme_cfg, raw_plan = load_plan_from_scheme_json(scheme_path)
        rcfg = scheme_cfg.get("raster_config", {})
        normal_w = rcfg.get("normal_weight", args.normal_weight)
        raster_m = rcfg.get("raster_mode", args.raster_mode)
        print(f"[+] Loaded declarative font scheme: {scheme_path.name} ({scheme_cfg.get('project_brand', '')})")
    else:
        normal_w = args.normal_weight
        raster_m = args.raster_mode
        raw_plan = [
            (fam, role, szs, r_str, False, fb_pat, "")
            for (fam, role, szs, r_str, _, fb_pat) in PROFILES[args.profile]
        ]

    family_roles = get_family_roles(normal_w)
    if args.families:
        allowed_fams = set(args.families)
        raw_plan = [item for item in raw_plan if item[0] in allowed_fams]

    if do_build_c:
        c_out_dir.mkdir(parents=True, exist_ok=True)

    compiled_symbols: List[Tuple[str, str, str, int, int]] = []
    compiled_details: List[dict] = []
    strike_cache: Dict[str, Tuple[Dict[int, GlyphStrike], int, int]] = {}
    kern_cache: Dict[str, Dict[Tuple[int, int], int]] = {}
    vault_data: dict = {
        "vault_version": "1.0.10",
        "raster_mode": raster_m,
        "normal_weight": normal_w,
        "strikes": {},
    }
    total_rom_bytes = 0
    total_ascii_dumped = 0
    total_png_inspected = 0
    total_char_pngs = 0

    # Build list of strike tasks and execute across all host CPU cores via ProcessPoolExecutor!
    t_start = time.perf_counter()
    max_workers = args.jobs if (args.jobs and args.jobs > 0) else (os.cpu_count() or 4)
    strike_tasks: List[dict] = []
    do_repair_wf = args.workflow in ("repair", "all")
    inspect_repairs_root = (root_out / "inspect_repairs") if do_repair_wf else None

    # Pre-compute all planned strike symbols so `.fallback` pointers are guaranteed to resolve
    planned_symbols_set = set()
    for _fam, _role, _psizes, _, _, _, _ in raw_plan:
        _r = Path(_role.split("custom:", 1)[1]).stem.lower().replace("-", "_") if _role.startswith("custom:") else _role
        _szs = args.sizes if args.sizes is not None else _psizes
        _fl = SUBFAMILY_FLOORS.get(_fam, 10)
        for _s in _szs:
            if _s >= _fl or scheme_cfg is not None:
                planned_symbols_set.add(format_strike_symbol(_fam, _r, _s))

    def _resolve_smart_fallback(fb_pat: Optional[str], cur_sz: int, cur_sym: str, all_syms: set) -> Optional[str]:
        if not fb_pat:
            return None
        cand = fb_pat.format(size=cur_sz)
        if not cand.startswith("humid1_"):
            if cand.startswith(("plex_sans_", "plex_mono_", "plex_cond_", "plex_serif_", "plex_math_")):
                cand = f"humid1_font_{cand}"
            elif cand.startswith("plex_terminus_"):
                cand = f"humid1_font_{cand[5:]}"
        if cand == cur_sym:
            return None
        if cand in all_syms:
            return cand
        # Find nearest size in the same fallback family prefix
        m = re.match(r"^(.+_)(\d+)$", cand)
        if m:
            prefix = m.group(1)
            avail_sizes = []
            for s_item in all_syms:
                if s_item.startswith(prefix) and s_item != cur_sym:
                    tail = s_item[len(prefix):]
                    if tail.isdigit():
                        avail_sizes.append((int(tail), s_item))
            if avail_sizes:
                # Prefer largest size <= cur_sz, else smallest size > cur_sz
                le = [x for x in avail_sizes if x[0] <= cur_sz]
                if le:
                    return max(le, key=lambda x: x[0])[1]
                return min(avail_sizes, key=lambda x: abs(x[0] - cur_sz))[1]
        return None

    for family, role, prof_sizes, range_str, inc_fa5, fb_pattern, fa_range_str in raw_plan:
        if role.startswith("custom:"):
            ttf_name = role.split("custom:", 1)[1]
            role = Path(ttf_name).stem.lower().replace("-", "_")
        else:
            fam_map = family_roles.get(family, family_roles["sans"])
            ttf_name = fam_map.get(role, fam_map.get("normal", "IBMPlexSans-Regular.ttf"))

        sizes_to_build = args.sizes if args.sizes is not None else prof_sizes
        floor_px = SUBFAMILY_FLOORS.get(family, 10)
        valid_sizes = [s for s in sizes_to_build if s >= floor_px or scheme_cfg is not None]

        codepoints = parse_unicode_range(range_str)
        if family.startswith("icon_"):
            codepoints = [cp for cp in codepoints if cp >= 0xE000]
            if family == "icon_tabler" and role == "filled" and not codepoints:
                codepoints = parse_unicode_range(DEFAULT_ICON_FALLBACK_RANGES["icon_tabler_filled"])
        enable_kern = family in ("sans", "cond", "serif")

        for sz in valid_sizes:
            # For Terminus, select the exact size-specific native .ttf (Terminus-Normal-<sz>.ttf / Terminus-Bold-<sz>.ttf)
            strike_ttf_name = ttf_name
            if family == "terminus":
                if "bold" in role.lower() and (font_dir / f"Terminus-Bold-{sz}.ttf").is_file():
                    strike_ttf_name = f"Terminus-Bold-{sz}.ttf"
                elif "vga" in role.lower() and (font_dir / f"Terminus-VGA-{sz}.ttf").is_file():
                    strike_ttf_name = f"Terminus-VGA-{sz}.ttf"
                elif (font_dir / f"Terminus-Normal-{sz}.ttf").is_file():
                    strike_ttf_name = f"Terminus-Normal-{sz}.ttf"

            ttf_path = font_dir / strike_ttf_name
            if not ttf_path.is_file():
                print(f"[!] Missing static TTF binary: {ttf_path}\n    Run `01_build_static_ttfs.bat` first.", file=sys.stderr)
                sys.exit(1)

            sym_name = format_strike_symbol(family, role, sz)
            legacy_sym_name = f"plex_{family}_{role}_{sz}"
            fb_sym = _resolve_smart_fallback(fb_pattern, sz, sym_name, planned_symbols_set)

            strike_patches = (
                patch_manifest.get("patches", {}).get(sym_name)
                or patch_manifest.get("patches", {}).get(legacy_sym_name)
                or {}
            )
            strike_ascii_dir = (ascii_ingest_root / sym_name) if ascii_ingest_root else None
            effective_raster_m = "exact-mono" if family in ("terminus", "unifont") else raster_m

            strike_tasks.append({
                "sym_name": sym_name,
                "family": family,
                "role": role,
                "sz": sz,
                "ttf_name": strike_ttf_name,
                "ttf_path": str(ttf_path),
                "font_dir": str(font_dir),
                "codepoints": codepoints,
                "effective_raster_m": effective_raster_m,
                "threshold": args.threshold,
                "strike_patches": strike_patches,
                "strike_ascii_dir": str(strike_ascii_dir) if strike_ascii_dir else None,
                "enable_kern": enable_kern,
                "prune_noop_kern": not args.keep_noop_kern,
                "do_build_c": do_build_c,
                "c_out_dir": str(c_out_dir) if do_build_c else None,
                "fb_sym": fb_sym,
                "dump_ascii_root": str(dump_ascii_root) if dump_ascii_root else None,
                "trouble_only": args.trouble_only,
                "unicode_preview": args.unicode_preview,
                "inspect_png_root": str(inspect_png_root) if inspect_png_root else None,
                "inspect_chars_root": str(inspect_chars_root) if inspect_chars_root else None,
                "inspect_chars_filter": args.inspect_chars_filter,
                "bdf_out_dir": str(bdf_out_dir) if (bdf_out_dir and sz <= 32) else None,
                "metrics_out_dir": str(metrics_out_dir) if metrics_out_dir else None,
                "auto_floor": bool(scheme_cfg.get("raster_config", {}).get("auto_floor", args.auto_floor)) if scheme_cfg else args.auto_floor,
                "min_stem": int(scheme_cfg.get("raster_config", {}).get("min_stem_px", args.min_stem)) if scheme_cfg else args.min_stem,
                "repair_engine": str(scheme_cfg.get("raster_config", {}).get("repair_engine", args.repair_engine)) if scheme_cfg else args.repair_engine,
                "inspect_repairs_root": str(inspect_repairs_root) if inspect_repairs_root else None,
            })

    print(f"[*] Processing {len(strike_tasks)} font/icon strikes in parallel across {max_workers} CPU worker processes...")
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as pool:
        for res in pool.map(_execute_strike_worker_task, strike_tasks):
            sym_name = res["sym_name"]
            family = res["family"]
            role = res["role"]
            sz = res["sz"]
            rom_b = res["rom_b"]
            glyphs = res["glyphs"]
            line_h = res["line_h"]
            base_l = res["base_l"]
            kern_pairs = res["kern_pairs"]

            total_rom_bytes += rom_b
            total_ascii_dumped += res["ascii_dumped"]
            total_png_inspected += res["png_pages"]
            total_char_pngs += res["char_pngs"]
            compiled_symbols.append((sym_name, family, role, sz, rom_b))
            compiled_details.append({
                "sym_name": sym_name,
                "family": family,
                "role": role,
                "sz": sz,
                "line_h": line_h,
                "glyph_count": len(glyphs),
                "kern_count": len(kern_pairs),
                "rom_b": rom_b,
                "c_disk_b": res.get("c_disk_b", 0),
            })

            gmap = {g.codepoint: g for g in glyphs}
            strike_cache[sym_name] = (gmap, line_h, base_l)
            kern_cache[sym_name] = {(lc, rc): kv for _, _, lc, rc, kv in kern_pairs}

            if vault_out_path:
                vault_data["strikes"][sym_name] = res["vault_entry"]

            print(res["log_line"])

    elapsed_s = time.perf_counter() - t_start
    print(f"[+] Completed {len(strike_tasks)} strikes in {elapsed_s:.2f}s using {max_workers} CPU cores.")

    if do_build_c:
        generate_headers(c_out_dir, compiled_symbols, scheme_cfg=scheme_cfg)
        copy_licenses(None, font_dir, c_out_dir)

    if vault_out_path:
        v_bytes = export_strike_vault(vault_out_path, vault_data)
        print(f"[+] Exported pre-rasterized Strike Vault ({len(vault_data['strikes'])} strikes) -> {vault_out_path} ({v_bytes:,} B)")

    if do_build_c and compiled_details:
        tdisp_d = (scheme_cfg or {}).get("target_display", {})
        rep_dpi = args.dpi if args.dpi is not None else float(tdisp_d.get("dpi", 188.3))
        rep_scheme = scheme_cfg.get("scheme_id", args.profile) if scheme_cfg else args.profile
        sz_rep_path = write_total_disk_size_report(
            c_out_dir=c_out_dir,
            root_out=root_out,
            dist_root=dist_root,
            compiled_details=compiled_details,
            vault_path=vault_out_path,
            scheme_id=rep_scheme,
            dpi=rep_dpi,
        )
        print(f"[+] Generated Flash ROM & Disk Size Report -> {sz_rep_path}")

    if dump_ascii_root:
        print(f"[+] Dumped {total_ascii_dumped:,} Full-Canvas 1:1 Spaced ASCII .txt files across {len(compiled_symbols)} folders in {dump_ascii_root}")

    if inspect_png_root:
        print(f"[+] Rendered {total_png_inspected} Auto-Wrapped Page Check PNG sheets in {inspect_png_root}")

    if inspect_chars_root:
        print(f"[+] Rendered {total_char_pngs:,} Char-by-Char Deep-Check Blueprint PNG cards in {inspect_chars_root}")

    label_mode = scheme_cfg.get("scheme_id", args.profile) if scheme_cfg else args.profile
    print(
        f"\n[+] Scheme '{label_mode}' ({raster_m}, normal={normal_w}) complete: "
        f"{len(compiled_symbols)} strikes, total ROM = {total_rom_bytes:,} bytes ({total_rom_bytes/1024:.1f} KB)."
    )

    if (args.audit_screens or do_check_png) and strike_cache:
        mont_dir = Path(args.montserrat_metrics_dir).resolve() if args.montserrat_metrics_dir else None
        tdisp = (scheme_cfg or {}).get("target_display", {})
        s_dpi = args.dpi if args.dpi is not None else float(tdisp.get("dpi", 188.3))
        s_w = args.screen_width if args.screen_width is not None else int(tdisp.get("width_px", 200))
        s_h = args.screen_height if args.screen_height is not None else int(tdisp.get("height_px", 200))
        s_m = args.safe_margin if args.safe_margin is not None else int(tdisp.get("safe_margin_px", 6))
        p_label = tdisp.get("panel", (scheme_cfg or {}).get("project_brand", "Humiditron Reference EPD"))
        c_rows = (scheme_cfg or {}).get("screen_audit_rows", None)
        run_screen_width_audit(
            strike_cache,
            kern_cache,
            mont_dir,
            screen_width=s_w,
            screen_height=s_h,
            safe_margin=s_m,
            dpi=s_dpi,
            panel_name=p_label,
            custom_rows=c_rows,
        )

    if specimen_out_path and strike_cache:
        render_specimen_sheet(specimen_out_path, strike_cache)


if __name__ == "__main__":
    main()
