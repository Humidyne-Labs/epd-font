#!/usr/bin/env python3
"""
humid1_generate_1bpp.py (v1.0.16)
=================================
Humidyne Labs / Humiditron `epd-font` Modular 1-BPP Font Foundry Orchestrator.

Repository : https://github.com/Humidyne-Labs/epd-font
Target OS  : https://github.com/Humidyne-Labs/H1OS
License    : MIT License

Modular Architecture (v1.0.16):
-------------------------------
- `humid1_ft_raster.py`     : FreeType 2 ctypes bindings, glyph strike model, kerning & 1-BPP rasterizer.
- `humid1_bilevel_tuner.py` : Iterative Multi-Method Typographic Tournament (`M0..M8`) + Bilateral Mirror Sync.
- `humid1_ascii_patches.py` : Full-canvas 1:1 spaced ASCII patch dumper, parser & JSON compiler.
- `humid1_visual_check.py`  : Diagnostic page sheets, char-by-char blueprints & 188 DPI e-ink specimen renderer.
- `humid1_fw_emit.py`       : LVGL v9 C/H emitter, Adobe BDF 2.1 exporter, Strike Vault & ROM/disk auditor.
- `humid1_font_eval.py`     : Multi-typeface & multi-weight legibility benchmark & size-floor evaluator.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import ctypes
import gzip
import json
import math
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from humid1_ft_raster import (
    open_ttfont_safe,
    FT_Bitmap,
    FT_BBox,
    FT_FaceRec,
    FT_Glyph_Metrics,
    FT_GlyphSlotRec,
    FT_LOAD_FORCE_AUTOHINT,
    FT_LOAD_MONOCHROME,
    FT_LOAD_NO_HINTING,
    FT_LOAD_RENDER,
    FT_LOAD_TARGET_MONO,
    FT_LOAD_TARGET_NORMAL,
    FT_Vector,
    GlyphStrike,
    HOMOGLYPH_EQUIVALENTS,
    ICON_NAME_REGISTRY,
    RANGE_MATH_STR,
    RANGE_UI_STR,
    TROUBLE_15_CODEPOINTS,
    _synthesize_new_line_glyph,
    extract_kerning_pairs_fp4,
    format_strike_symbol,
    get_semantic_glyph_name,
    load_freetype,
    load_icon_name_registry,
    parse_unicode_range,
    rasterize_font_strike,
    resolve_freetype_flags,
    safe_glyph_filename,
)
from humid1_ascii_patches import (
    build_patches_json_from_ascii_root,
    dump_strike_to_ascii_folder,
    parse_ascii_glyph_folder,
)
from humid1_visual_check import (
    _load_ui_fonts,
    _render_single_page_inspection_png,
    render_char_by_char_folder,
    render_full_font_inspection_png,
    render_single_char_inspection_png,
    render_specimen_sheet,
)
from humid1_lvgl_bdf_export import (
    build_cmaps_partitions,
    copy_licenses,
    emit_lvgl_c_file,
    export_bdf_strike,
    export_metric_csvs,
    generate_headers,
    measure_lvgl_string_px,
    run_screen_width_audit,
    write_total_disk_size_report,
)

TOOL_VERSION = "1.0.16"

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


def get_family_roles(normal_weight: int = 500, bold_weight: int = 800, italic_weight: int = 600) -> Dict[str, Dict[str, str]]:
    """
    Map semantic roles (thin, extralight, light, normal, text, medium, semibold, bold, extrabold, italic, bold_italic)
    to instantiated static TTF filenames.
    In v1.0.16, the Tri-Role Visual Contrast Hierarchy enforces:
      - `normal` : `Medium (500)` (`~2.17px` stem, `1.00x` baseline ink)
      - `bold`   : `ExtraBold (800)` (`~3.13px` stem, `+35.7%` to `+40.1%` ink punch over `normal`!)
      - `italic` : `SemiBoldItalic (600)` on Sans/Cond (`+1.3%` iso-weight ink vs `normal`, `96.7%` >=2px stems)
                   and `MediumItalic (500)` on Mono/Serif (`-3.1%` iso-weight ink vs `normal`) so Italic
                   remains a subtle cursive emphasis (`>=25%` lighter than Bold!).
    """
    tag = {100: "Thin", 200: "ExtraLight", 300: "Light", 400: "Regular", 450: "Text", 500: "Medium", 600: "SemiBold", 700: "Bold", 800: "ExtraBold"}.get(normal_weight, "Medium")
    b_tag = {600: "SemiBold", 700: "Bold", 800: "ExtraBold"}.get(bold_weight, "ExtraBold" if normal_weight >= 500 else "Bold")
    b_ital_tag = "ExtraBoldItalic" if b_tag == "ExtraBold" else "BoldItalic"
    ital_tag = {400: "Italic", 450: "TextItalic", 500: "MediumItalic", 600: "SemiBoldItalic", 700: "BoldItalic", 800: "ExtraBoldItalic"}.get(italic_weight, "SemiBoldItalic")
    cond_ital_tag = {400: "Italic", 500: "MedItal", 600: "SemiBoldItalic", 700: "BoldItalic", 800: "ExtraBoldItalic"}.get(italic_weight, "SemiBoldItalic")
    mono_ital_tag = {400: "Italic", 500: "MediumItalic", 600: "MediumItalic", 700: "BoldItalic", 800: "ExtraBoldItalic"}.get(italic_weight, "MediumItalic")
    serif_ital_tag = {400: "Italic", 500: "MediumItalic", 600: "SemiBoldItalic", 700: "BoldItalic", 800: "ExtraBoldItalic"}.get(italic_weight, "SemiBoldItalic")

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
            "bold": f"IBMPlexSans-{b_tag}.ttf",
            "bold_700": "IBMPlexSans-Bold.ttf",
            "extrabold": "IBMPlexSans-ExtraBold.ttf",
            "italic": f"IBMPlexSans-{ital_tag}.ttf",
            "bold_italic": f"IBMPlexSans-{b_ital_tag}.ttf",
        },
        "mono": {
            "light": "IBMPlexMono-Light.ttf",
            "normal": f"IBMPlexMono-{tag}.ttf",
            "regular": "IBMPlexMono-Regular.ttf",
            "text": "IBMPlexMono-Text.ttf",
            "medium": "IBMPlexMono-Medium.ttf",
            "semibold": "IBMPlexMono-SemiBold.ttf",
            "bold": f"IBMPlexMono-{b_tag}.ttf",
            "bold_700": "IBMPlexMono-Bold.ttf",
            "extrabold": "IBMPlexMono-ExtraBold.ttf",
            "italic": f"IBMPlexMono-{mono_ital_tag}.ttf",
            "bold_italic": f"IBMPlexMono-{b_ital_tag}.ttf",
        },
        "cond": {
            "light": "IBMPlexSansCondensed-Light.ttf",
            "normal": f"IBMPlexSansCondensed-{tag}.ttf",
            "regular": "IBMPlexSansCondensed-Regular.ttf",
            "text": "IBMPlexSansCondensed-Text.ttf",
            "medium": "IBMPlexSansCondensed-Medium.ttf",
            "semibold": "IBMPlexSansCondensed-SemiBold.ttf",
            "bold": f"IBMPlexSansCondensed-{b_tag}.ttf",
            "bold_700": "IBMPlexSansCondensed-Bold.ttf",
            "extrabold": "IBMPlexSansCondensed-ExtraBold.ttf",
            "italic": f"IBMPlexSansCondensed-{cond_ital_tag}.ttf",
            "bold_italic": f"IBMPlexSansCondensed-{b_ital_tag}.ttf",
        },
        "serif": {
            "light": "IBMPlexSerif-Light.ttf",
            "normal": f"IBMPlexSerif-{tag}.ttf",
            "regular": "IBMPlexSerif-Regular.ttf",
            "text": "IBMPlexSerif-Text.ttf",
            "medium": "IBMPlexSerif-Medium.ttf",
            "semibold": "IBMPlexSerif-SemiBold.ttf",
            "bold": f"IBMPlexSerif-{b_tag}.ttf",
            "bold_700": "IBMPlexSerif-Bold.ttf",
            "extrabold": "IBMPlexSerif-ExtraBold.ttf",
            "italic": f"IBMPlexSerif-{serif_ital_tag}.ttf",
            "bold_italic": f"IBMPlexSerif-{b_ital_tag}.ttf",
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
            fa_tt = open_ttfont_safe(woff_cand)
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
                tt = open_ttfont_safe(src_path)
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
# 12. UNIFIED CLI, JSON SCHEME LOADER & 4-WORKFLOW PIPELINE ORCHESTRATION (v1.0.16)
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
            "Humidyne Labs / Humiditron `epd-font` v1.0.16 — General-Purpose 1-BPP Font & Modular Icon Studio.\n"
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
        help="OpenType weight for 'normal' slot (default: 500 Medium for ~2.15px EPD stem legibility)",
    )
    parser.add_argument(
        "--bold-weight",
        type=int,
        choices=[600, 700, 800],
        default=800,
        help="OpenType weight for 'bold' slot (default: 800 ExtraBold for +35%%..+40%% ink punch over normal)",
    )
    parser.add_argument(
        "--italic-weight",
        type=int,
        choices=[400, 450, 500, 600, 700, 800],
        default=600,
        help="OpenType weight for 'italic' slot (default: 600 SemiBoldItalic iso-weight subtle emphasis)",
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
        "--tune-mode",
        choices=["off", "wart-only", "surgical", "full"],
        default="surgical",
        help="Auto-tune intervention level: off (native weights only), wart-only (4-dir wart shaving + mirror sync), surgical (default), or full",
    )
    parser.add_argument(
        "--save-repaired-patches",
        action="store_true",
        help="Save auto-repaired glyphs into --patches JSON during --workflow repair",
    )
    parser.add_argument(
        "--raster-mode",
        choices=["autohint-mono", "bytecode-mono", "gray-threshold", "dynamic-threshold"],
        default="autohint-mono",
        help="FreeType 1-bpp rasterizer mode (default: autohint-mono)",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=128,
        help="Grayscale threshold (1-255, or 0 for weight/size/Otsu dynamic threshold)",
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

    # Rasterize strike (ingesting existing patches unless running a fresh repair tournament)
    is_repair_run = bool(task.get("inspect_repairs_root"))
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
        patch_dict={} if is_repair_run else task["strike_patches"],
        ascii_override_dir=None if is_repair_run else strike_ascii_dir,
        enable_kerning=task["enable_kern"],
        prune_noop_kern=task["prune_noop_kern"],
        auto_floor=False,
        min_stem=task.get("min_stem", 2),
        repair_engine=task.get("repair_engine", "hybrid"),
    )

    repair_sheet_written = 0
    repaired_glyph_cnt = 0
    orig_sigs_map: Dict[int, str] = {}
    for g0 in glyphs:
        m_lines = g0.rows if (g0.box_w > 0 and g0.box_h > 0 and g0.rows) else []
        orig_sigs_map[g0.codepoint] = f"{g0.box_w},{g0.box_h},{g0.ofs_x},{g0.ofs_y}|" + ("/".join(m_lines) if m_lines else ".")

    # Execute Multi-Method Iterative Typographic Tournament when `--workflow repair` (08) is active
    # Skip hand-authored pixel fonts (`terminus`) and icon fonts (`icon_*`) so native pixel art is never distorted
    if is_repair_run and family not in ("terminus", "unifont") and not family.startswith("icon_"):
        try:
            import humid1_bilevel_tuner as _bt
            import numpy as _np

            # Open 8x HQ Continuous Grayscale Master Face + 12px Smallest-Strike Base Reference Face
            hq_face = ctypes.POINTER(FT_FaceRec)()
            base12_face = ctypes.POINTER(FT_FaceRec)()
            has_hq = (_WORKER_FT.FT_New_Face(_WORKER_FT_LIB, str(ttf_path).encode("utf-8"), 0, ctypes.byref(hq_face)) == 0)
            if has_hq:
                _WORKER_FT.FT_Set_Pixel_Sizes(hq_face, 0, sz * 8)
            has_b12 = (_WORKER_FT.FT_New_Face(_WORKER_FT_LIB, str(ttf_path).encode("utf-8"), 0, ctypes.byref(base12_face)) == 0)
            if has_b12:
                _WORKER_FT.FT_Set_Pixel_Sizes(base12_face, 0, 12)

            def _render_hq_gray(cp_val: int) -> Optional[_np.ndarray]:
                if not has_hq:
                    return None
                gidx = _WORKER_FT.FT_Get_Char_Index(hq_face, cp_val)
                if gidx == 0 and cp_val in HOMOGLYPH_EQUIVALENTS:
                    for alt_c in HOMOGLYPH_EQUIVALENTS[cp_val]:
                        gidx = _WORKER_FT.FT_Get_Char_Index(hq_face, alt_c)
                        if gidx != 0:
                            break
                if gidx == 0:
                    return None
                if _WORKER_FT.FT_Load_Glyph(hq_face, gidx, FT_LOAD_RENDER | FT_LOAD_NO_HINTING | FT_LOAD_TARGET_NORMAL) != 0:
                    return None
                slot = hq_face.contents.glyph.contents
                bmp = slot.bitmap
                if bmp.rows <= 0 or bmp.width <= 0:
                    return None
                arr = _np.zeros((bmp.rows, bmp.width), dtype=_np.uint8)
                for r_i in range(bmp.rows):
                    for c_i in range(bmp.width):
                        arr[r_i, c_i] = bmp.buffer[r_i * bmp.pitch + c_i]
                ys, xs = _np.nonzero(arr > 16)
                if len(xs) == 0:
                    return None
                return arr[int(ys.min()):int(ys.max())+1, int(xs.min()):int(xs.max())+1]

            def _render_base12_upscaled(cp_val: int, target_w: int, target_h: int) -> Optional[_np.ndarray]:
                if not has_b12 or not _bt.HAS_CV2:
                    return None
                gidx = _WORKER_FT.FT_Get_Char_Index(base12_face, cp_val)
                if gidx == 0:
                    return None
                flags12 = FT_LOAD_RENDER | FT_LOAD_FORCE_AUTOHINT | FT_LOAD_TARGET_MONO | FT_LOAD_MONOCHROME
                if _WORKER_FT.FT_Load_Glyph(base12_face, gidx, flags12) != 0:
                    return None
                slot = base12_face.contents.glyph.contents
                bmp = slot.bitmap
                if bmp.rows <= 0 or bmp.width <= 0:
                    return None
                arr12 = _np.zeros((bmp.rows, bmp.width), dtype=_np.uint8)
                for r_i in range(bmp.rows):
                    for c_i in range(bmp.width):
                        byte_v = bmp.buffer[r_i * bmp.pitch + (c_i >> 3)]
                        if (byte_v >> (7 - (c_i & 7))) & 1:
                            arr12[r_i, c_i] = 255
                ys, xs = _np.nonzero(arr12 > 0)
                if len(xs) == 0:
                    return None
                cropped12 = arr12[int(ys.min()):int(ys.max())+1, int(xs.min()):int(xs.max())+1]
                return _bt.cv2.resize(cropped12, (max(1, target_w), max(1, target_h)), interpolation=_bt.cv2.INTER_NEAREST)

            recs = []
            is_mono_f = family in ("mono", "terminus", "unifont")
            is_ital_or_ser = ("italic" in role.lower()) or (family == "serif")

            for g_item in glyphs:
                if not g_item.rows or g_item.codepoint <= 0x0020:
                    continue
                w_orig = g_item.box_w
                arr_bef = _bt.rows_to_binary_array(g_item.rows)
                hq_img = _render_hq_gray(g_item.codepoint)
                up12_img = _render_base12_upscaled(g_item.codepoint, g_item.box_w, g_item.box_h)
                max_w = (g_item.adv_w_fp4 >> 4) if is_mono_f else ((g_item.adv_w_fp4 >> 4) + 1)

                rep_arr, rec = _bt.inspect_and_repair_glyph_bitmap(
                    arr_bef,
                    codepoint=g_item.codepoint,
                    min_stem=task.get("min_stem", 2),
                    master_hi=hq_img,
                    upscaled_small_ref=up12_img,
                    max_width_ceiling=max_w,
                    engine=task.get("repair_engine", "hybrid"),
                    is_italic_or_serif=is_ital_or_ser,
                    is_bold_role=("bold" in role.lower()),
                    tune_mode=task.get("tune_mode", "surgical"),
                )
                recs.append(rec)
                if rec.repaired:
                    trimmed, bw, bh, nox, noy = _bt.trim_binary_array(rep_arr, g_item.ofs_x, g_item.ofs_y)
                    if bw > 0 and bh > 0:
                        g_item.rows = _bt.binary_array_to_rows(trimmed)
                        g_item.box_w = bw
                        g_item.box_h = bh
                        g_item.ofs_x = nox
                        g_item.ofs_y = noy
                        g_item.patched = True
                        if not is_mono_f and bw > w_orig:
                            g_item.adv_w_fp4 += (bw - w_orig) * 16
                        repaired_glyph_cnt += 1

            # Enforce Bilateral Mirror-Pair Synchronization across upright strikes (`(` <-> `)`, `[` <-> `]`, `{` <-> `}`, `<` <-> `>`, `/` <-> `\`, arrows)
            repaired_glyph_cnt += _bt.synchronize_mirror_glyph_pairs(
                glyphs,
                recs,
                is_italic=("italic" in role.lower()),
                is_monospace=is_mono_f,
            )

            if has_hq:
                _WORKER_FT.FT_Done_Face(hq_face)
            if has_b12:
                _WORKER_FT.FT_Done_Face(base12_face)

            rep_png = Path(task["inspect_repairs_root"]) / f"{sym_name}_repair.png"
            _bt.render_repair_comparison_sheet(rep_png, sym_name, sz, recs)
            repair_sheet_written = 1
        except Exception as e:
            print(f"[!] Repair tournament warning on {sym_name}: {e}", file=sys.stderr)

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
        if is_repair_run and s_dump_dir.is_dir():
            shutil.rmtree(s_dump_dir)
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
            orig_signatures=orig_sigs_map,
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

    # 1. Resolve unified --src-dir (Static TTFs live in <repo>/build/static_ttfs by default in v1.0.16)
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
    if args.workflow == "gen-assets" or not (font_dir / "IBMPlexSans-Regular.ttf").is_file() or not (font_dir / "IBMPlexSans-ExtraBold.ttf").is_file():
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
    do_build_c = args.workflow in ("build", "all") or (args.out_dir is not None and args.workflow not in ("check", "patch", "repair"))
    do_check_png = args.workflow in ("check", "all") or (args.inspect_png_dir is not None)
    do_dump_ascii = args.dump or (args.workflow in ("all", "repair")) or (args.dump_ascii_dir is not None)
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
        normal_w = int(rcfg.get("normal_weight", args.normal_weight))
        bold_w = int(rcfg.get("bold_weight", args.bold_weight))
        italic_w = int(rcfg.get("italic_weight", args.italic_weight))
        raster_m = rcfg.get("raster_mode", args.raster_mode)
        print(f"[+] Loaded declarative font scheme: {scheme_path.name} ({scheme_cfg.get('project_brand', '')})")
    else:
        normal_w = args.normal_weight
        bold_w = args.bold_weight
        italic_w = args.italic_weight
        raster_m = args.raster_mode
        raw_plan = [
            (fam, role, szs, r_str, False, fb_pat, "")
            for (fam, role, szs, r_str, _, fb_pat) in PROFILES[args.profile]
        ]

    family_roles = get_family_roles(normal_w, bold_w, italic_w)
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
        "vault_version": "1.0.16",
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
                "tune_mode": str(scheme_cfg.get("raster_config", {}).get("tune_mode", args.tune_mode)) if scheme_cfg else args.tune_mode,
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
        if (args.workflow == "repair" or getattr(args, "save_repaired_patches", False)) and dump_ascii_root.is_dir():
            comp_cnt = build_patches_json_from_ascii_root(dump_ascii_root, patches_path, only_modified=True)
            print(f"[+] Compiled {comp_cnt:,} auto-repaired ASCII glyph patches from {dump_ascii_root} -> {patches_path}")

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
