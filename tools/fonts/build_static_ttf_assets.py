#!/usr/bin/env python3
"""
build_static_ttf_assets.py (v1.0.16)
===================================
Humidyne Labs / Humiditron `epd-font` Multi-Core Raw-to-Static TrueType (`.ttf`) Asset & Metadata Builder.

Repository : https://github.com/Humidyne-Labs/epd-font
Author     : Humidyne Labs / Humiditron
License    : MIT License (Upstream fonts retain SIL OFL 1.1 / CC-BY-4.0 / ISC / MIT)

What's New in v1.0.16:
---------------------
1. Anisotropic `ExtraBold` (`wght=800`) Synthesis from IBM Plex Variable Masters:
   Upstream IBM Plex Variable TTFs cap `fvar.wght` at `700.0`, which quantizes to the same `2px`
   stem thickness as `Medium` (`wght=500.0`) at `12px–16px`. In v1.0.16, `instantiate_plex_variable_cut()`
   synthesizes true `ExtraBold` (`wght=800.0`, `IBMPlex*-ExtraBold.ttf` & `IBMPlex*-ExtraBoldItalic.ttf`)
   via anisotropic `gvar` positive-weight delta extrapolation (`1.45x` horizontal stem weight,
   `1.18x` vertical bar weight to keep internal counters open), restoring a distinct 3-tier hierarchy:
   `normal = Medium (500)`, `bold = ExtraBold (800)`, `italic = MediumItalic (500)`.
2. Multi-Core Parallel Execution (`ProcessPoolExecutor`):
   Saturates all available CPU cores (`os.cpu_count()`, configurable via `-j/--jobs`)
   to instantiate Variable TTFs, convert CFF OTFs, and synthesize Terminus TTFs concurrently.
3. 24 Native & Exact-2x Terminus v4.49.1 `.ttf` Strikes + Unified 2D Polygon Contours:
   Converts all 20 upstream Terminus `.bdf` files (`12, 14, 16, 18, 20, 22, 24, 28, 32` Normal/Bold + VGA)
   plus exact 2x native strikes for `36` (from `18`) and `40` (from `20`) into 24+ individual `.ttf` files.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import shutil
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

try:
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.cu2quPen import Cu2QuPen
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.ttLib import TTFont, newTable
    from fontTools.varLib import instancer
except ImportError as exc:
    print(
        "[!] Error: Missing required Python package 'fonttools'.\n"
        "    Run `pip install \"fonttools>=4.40.0\"`.",
        file=sys.stderr,
    )
    raise SystemExit(1) from exc

TOOL_VERSION = "1.0.16"

# =============================================================================
# 1. DECLARATIVE CONVERSION TABLES
# =============================================================================

MONO_GREEK_ALIASES = {0x0394: "Delta", 0x03A9: "Omega", 0x03BC: "mu"}

PLEX_VARIABLE_INSTANTIATION_TABLE: List[Tuple[str, str, str, Dict[str, float], Dict[int, str]]] = [
    # --- IBM Plex Sans (wdth=100, v0.2.0 Variable, wght=100..800) ---
    ("IBMPlexSans-Thin.ttf", "sans", "IBM Plex Sans Var-Roman.ttf", {"wght": 100.0, "wdth": 100.0}, {}),
    ("IBMPlexSans-ExtraLight.ttf", "sans", "IBM Plex Sans Var-Roman.ttf", {"wght": 200.0, "wdth": 100.0}, {}),
    ("IBMPlexSans-Light.ttf", "sans", "IBM Plex Sans Var-Roman.ttf", {"wght": 300.0, "wdth": 100.0}, {}),
    ("IBMPlexSans-Regular.ttf", "sans", "IBM Plex Sans Var-Roman.ttf", {"wght": 400.0, "wdth": 100.0}, {}),
    ("IBMPlexSans-Text.ttf", "sans", "IBM Plex Sans Var-Roman.ttf", {"wght": 450.0, "wdth": 100.0}, {}),
    ("IBMPlexSans-Medium.ttf", "sans", "IBM Plex Sans Var-Roman.ttf", {"wght": 500.0, "wdth": 100.0}, {}),
    ("IBMPlexSans-SemiBold.ttf", "sans", "IBM Plex Sans Var-Roman.ttf", {"wght": 600.0, "wdth": 100.0}, {}),
    ("IBMPlexSans-Bold.ttf", "sans", "IBM Plex Sans Var-Roman.ttf", {"wght": 700.0, "wdth": 100.0}, {}),
    ("IBMPlexSans-ExtraBold.ttf", "sans", "IBM Plex Sans Var-Roman.ttf", {"wght": 800.0, "wdth": 100.0}, {}),
    ("IBMPlexSans-Italic.ttf", "sans", "IBM Plex Sans Var-Italic.ttf", {"wght": 400.0, "wdth": 100.0}, {}),
    ("IBMPlexSans-TextItalic.ttf", "sans", "IBM Plex Sans Var-Italic.ttf", {"wght": 450.0, "wdth": 100.0}, {}),
    ("IBMPlexSans-MediumItalic.ttf", "sans", "IBM Plex Sans Var-Italic.ttf", {"wght": 500.0, "wdth": 100.0}, {}),
    ("IBMPlexSans-SemiBoldItalic.ttf", "sans", "IBM Plex Sans Var-Italic.ttf", {"wght": 600.0, "wdth": 100.0}, {}),
    ("IBMPlexSans-BoldItalic.ttf", "sans", "IBM Plex Sans Var-Italic.ttf", {"wght": 700.0, "wdth": 100.0}, {}),
    ("IBMPlexSans-ExtraBoldItalic.ttf", "sans", "IBM Plex Sans Var-Italic.ttf", {"wght": 800.0, "wdth": 100.0}, {}),
    # --- IBM Plex Sans Condensed (wdth=85 extracted from Sans Variable, wght=300..800) ---
    ("IBMPlexSansCondensed-Light.ttf", "cond", "IBM Plex Sans Var-Roman.ttf", {"wght": 300.0, "wdth": 85.0}, {}),
    ("IBMPlexSansCondensed-Regular.ttf", "cond", "IBM Plex Sans Var-Roman.ttf", {"wght": 400.0, "wdth": 85.0}, {}),
    ("IBMPlexSansCondensed-Text.ttf", "cond", "IBM Plex Sans Var-Roman.ttf", {"wght": 450.0, "wdth": 85.0}, {}),
    ("IBMPlexSansCondensed-Medium.ttf", "cond", "IBM Plex Sans Var-Roman.ttf", {"wght": 500.0, "wdth": 85.0}, {}),
    ("IBMPlexSansCondensed-SemiBold.ttf", "cond", "IBM Plex Sans Var-Roman.ttf", {"wght": 600.0, "wdth": 85.0}, {}),
    ("IBMPlexSansCondensed-Bold.ttf", "cond", "IBM Plex Sans Var-Roman.ttf", {"wght": 700.0, "wdth": 85.0}, {}),
    ("IBMPlexSansCondensed-ExtraBold.ttf", "cond", "IBM Plex Sans Var-Roman.ttf", {"wght": 800.0, "wdth": 85.0}, {}),
    ("IBMPlexSansCondensed-Italic.ttf", "cond", "IBM Plex Sans Var-Italic.ttf", {"wght": 400.0, "wdth": 85.0}, {}),
    ("IBMPlexSansCondensed-MedItal.ttf", "cond", "IBM Plex Sans Var-Italic.ttf", {"wght": 500.0, "wdth": 85.0}, {}),
    ("IBMPlexSansCondensed-SemiBoldItalic.ttf", "cond", "IBM Plex Sans Var-Italic.ttf", {"wght": 600.0, "wdth": 85.0}, {}),
    ("IBMPlexSansCondensed-BoldItalic.ttf", "cond", "IBM Plex Sans Var-Italic.ttf", {"wght": 700.0, "wdth": 85.0}, {}),
    ("IBMPlexSansCondensed-ExtraBoldItalic.ttf", "cond", "IBM Plex Sans Var-Italic.ttf", {"wght": 800.0, "wdth": 85.0}, {}),
    # --- IBM Plex Mono (v1.0.0 Variable, wght=300..800) ---
    ("IBMPlexMono-Light.ttf", "mono", "IBM Plex Mono Var-Roman.ttf", {"wght": 300.0}, MONO_GREEK_ALIASES),
    ("IBMPlexMono-Regular.ttf", "mono", "IBM Plex Mono Var-Roman.ttf", {"wght": 400.0}, MONO_GREEK_ALIASES),
    ("IBMPlexMono-Text.ttf", "mono", "IBM Plex Mono Var-Roman.ttf", {"wght": 450.0}, MONO_GREEK_ALIASES),
    ("IBMPlexMono-Medium.ttf", "mono", "IBM Plex Mono Var-Roman.ttf", {"wght": 500.0}, MONO_GREEK_ALIASES),
    ("IBMPlexMono-SemiBold.ttf", "mono", "IBM Plex Mono Var-Roman.ttf", {"wght": 600.0}, MONO_GREEK_ALIASES),
    ("IBMPlexMono-Bold.ttf", "mono", "IBM Plex Mono Var-Roman.ttf", {"wght": 700.0}, MONO_GREEK_ALIASES),
    ("IBMPlexMono-ExtraBold.ttf", "mono", "IBM Plex Mono Var-Roman.ttf", {"wght": 800.0}, MONO_GREEK_ALIASES),
    ("IBMPlexMono-Italic.ttf", "mono", "IBM Plex Mono Var-Italic.ttf", {"wght": 400.0}, MONO_GREEK_ALIASES),
    ("IBMPlexMono-MediumItalic.ttf", "mono", "IBM Plex Mono Var-Italic.ttf", {"wght": 500.0}, MONO_GREEK_ALIASES),
    ("IBMPlexMono-SemiBoldItalic.ttf", "mono", "IBM Plex Mono Var-Italic.ttf", {"wght": 600.0}, MONO_GREEK_ALIASES),
    ("IBMPlexMono-BoldItalic.ttf", "mono", "IBM Plex Mono Var-Italic.ttf", {"wght": 700.0}, MONO_GREEK_ALIASES),
    ("IBMPlexMono-ExtraBoldItalic.ttf", "mono", "IBM Plex Mono Var-Italic.ttf", {"wght": 800.0}, MONO_GREEK_ALIASES),
    # --- IBM Plex Serif (v2.0.0 Variable, wght=300..800) ---
    ("IBMPlexSerif-Light.ttf", "serif", "IBM Plex Serif Var-Roman.ttf", {"wght": 300.0}, {}),
    ("IBMPlexSerif-Regular.ttf", "serif", "IBM Plex Serif Var-Roman.ttf", {"wght": 400.0}, {}),
    ("IBMPlexSerif-Text.ttf", "serif", "IBM Plex Serif Var-Roman.ttf", {"wght": 450.0}, {}),
    ("IBMPlexSerif-Medium.ttf", "serif", "IBM Plex Serif Var-Roman.ttf", {"wght": 500.0}, {}),
    ("IBMPlexSerif-SemiBold.ttf", "serif", "IBM Plex Serif Var-Roman.ttf", {"wght": 600.0}, {}),
    ("IBMPlexSerif-Bold.ttf", "serif", "IBM Plex Serif Var-Roman.ttf", {"wght": 700.0}, {}),
    ("IBMPlexSerif-ExtraBold.ttf", "serif", "IBM Plex Serif Var-Roman.ttf", {"wght": 800.0}, {}),
    ("IBMPlexSerif-Italic.ttf", "serif", "IBM Plex Serif Var-Italic.ttf", {"wght": 400.0}, {}),
    ("IBMPlexSerif-MediumItalic.ttf", "serif", "IBM Plex Serif Var-Italic.ttf", {"wght": 500.0}, {}),
    ("IBMPlexSerif-SemiBoldItalic.ttf", "serif", "IBM Plex Serif Var-Italic.ttf", {"wght": 600.0}, {}),
    ("IBMPlexSerif-BoldItalic.ttf", "serif", "IBM Plex Serif Var-Italic.ttf", {"wght": 700.0}, {}),
    ("IBMPlexSerif-ExtraBoldItalic.ttf", "serif", "IBM Plex Serif Var-Italic.ttf", {"wght": 800.0}, {}),
]

# All 24 individual Terminus v4.49.1 BDF-to-TTF cuts (11 sizes x Normal/Bold + VGA 14/16)
TERMINUS_BDF_CONVERSION_TABLE: List[Tuple[str, str, str, str, int]] = [
    ("Terminus-Normal-12.ttf", "terminus", "ter-u12n.bdf", "Normal-12", 1),
    ("Terminus-Bold-12.ttf",   "terminus", "ter-u12b.bdf", "Bold-12",   1),
    ("Terminus-Normal-14.ttf", "terminus", "ter-u14n.bdf", "Normal-14", 1),
    ("Terminus-Bold-14.ttf",   "terminus", "ter-u14b.bdf", "Bold-14",   1),
    ("Terminus-VGA-14.ttf",    "terminus", "ter-u14v.bdf", "VGA-14",    1),
    ("Terminus-Normal-16.ttf", "terminus", "ter-u16n.bdf", "Normal-16", 1),
    ("Terminus-Bold-16.ttf",   "terminus", "ter-u16b.bdf", "Bold-16",   1),
    ("Terminus-VGA-16.ttf",    "terminus", "ter-u16v.bdf", "VGA-16",    1),
    ("Terminus-Normal-18.ttf", "terminus", "ter-u18n.bdf", "Normal-18", 1),
    ("Terminus-Bold-18.ttf",   "terminus", "ter-u18b.bdf", "Bold-18",   1),
    ("Terminus-Normal-20.ttf", "terminus", "ter-u20n.bdf", "Normal-20", 1),
    ("Terminus-Bold-20.ttf",   "terminus", "ter-u20b.bdf", "Bold-20",   1),
    ("Terminus-Normal-22.ttf", "terminus", "ter-u22n.bdf", "Normal-22", 1),
    ("Terminus-Bold-22.ttf",   "terminus", "ter-u22b.bdf", "Bold-22",   1),
    ("Terminus-Normal-24.ttf", "terminus", "ter-u24n.bdf", "Normal-24", 1),
    ("Terminus-Bold-24.ttf",   "terminus", "ter-u24b.bdf", "Bold-24",   1),
    ("Terminus-Normal-28.ttf", "terminus", "ter-u28n.bdf", "Normal-28", 1),
    ("Terminus-Bold-28.ttf",   "terminus", "ter-u28b.bdf", "Bold-28",   1),
    ("Terminus-Normal-32.ttf", "terminus", "ter-u32n.bdf", "Normal-32", 1),
    ("Terminus-Bold-32.ttf",   "terminus", "ter-u32b.bdf", "Bold-32",   1),
    # Exact 2x integer pixel-doubled strikes for 36px (2x18) and 40px (2x20):
    ("Terminus-Normal-36.ttf", "terminus", "ter-u18n.bdf", "Normal-36", 2),
    ("Terminus-Bold-36.ttf",   "terminus", "ter-u18b.bdf", "Bold-36",   2),
    ("Terminus-Normal-40.ttf", "terminus", "ter-u20n.bdf", "Normal-40", 2),
    ("Terminus-Bold-40.ttf",   "terminus", "ter-u20b.bdf", "Bold-40",   2),
]

ICON_CONVERSION_TABLE: List[Tuple[str, str, str, str]] = [
    ("FontAwesome7-Solid.ttf", "fa7", "Font Awesome 7 Free-Solid-900.otf", "otf2ttf"),
    ("FontAwesome7-Regular.ttf", "fa7", "Font Awesome 7 Free-Regular-400.otf", "otf2ttf"),
    ("FontAwesome7-Brands.ttf", "fa7", "Font Awesome 7 Brands-Regular-400.otf", "otf2ttf"),
    ("Lucide-Regular.ttf", "lucide", "lucide.ttf", "clean_ttf"),
    ("Phosphor-Regular.ttf", "phosphor", "Phosphor.ttf", "clean_ttf"),
    ("Phosphor-Bold.ttf", "phosphor", "Phosphor-Bold.ttf", "clean_ttf"),
    ("Phosphor-Fill.ttf", "phosphor", "Phosphor-Fill.ttf", "clean_ttf"),
    ("Phosphor-Light.ttf", "phosphor", "Phosphor-Light.ttf", "clean_ttf"),
    ("Phosphor-Thin.ttf", "phosphor", "Phosphor-Thin.ttf", "clean_ttf"),
    ("Tabler-Regular.ttf", "tabler", "tabler-icons.ttf", "clean_ttf"),
    ("Tabler-Light300.ttf", "tabler", "tabler-icons-300.ttf", "clean_ttf"),
    ("Tabler-Thin200.ttf", "tabler", "tabler-icons-200.ttf", "clean_ttf"),
    ("Tabler-Filled.ttf", "tabler", "tabler-icons-filled.ttf", "clean_ttf"),
]


# =============================================================================
# 2. SOURCE INDEXING & FONT CONVERSION FUNCTIONS
# =============================================================================

def index_source_tree(search_roots: Sequence[Path]) -> Dict[str, Path]:
    file_index: Dict[str, Path] = {}
    for root in search_roots:
        if not root or not root.exists():
            continue
        if root.is_file():
            file_index[root.name] = root
            file_index[root.name.lower()] = root
            continue
        for dirpath, _, filenames in os.walk(root):
            dp = Path(dirpath)
            for fn in filenames:
                full = dp / fn
                file_index.setdefault(fn, full)
                file_index.setdefault(fn.lower(), full)
                rel1 = f"{dp.name}/{fn}"
                file_index.setdefault(rel1, full)
                file_index.setdefault(rel1.lower(), full)
                if dp.parent != dp:
                    rel2 = f"{dp.parent.name}/{dp.name}/{fn}"
                    file_index.setdefault(rel2, full)
                    file_index.setdefault(rel2.lower(), full)
    return file_index


def convert_bdf_to_quadratic_ttf(
    src_bdf: Path,
    dst_ttf: Path,
    family_name: str = "Terminus",
    style_name: str = "Normal-16",
    px_mult: int = 1,
) -> Tuple[int, Dict[int, str]]:
    """
    Convert an X11 BDF bitmap font into a pure TrueType (`.ttf`) outline font using
    a 2D connected rectilinear polygon contour tracer.
    """
    lines = src_bdf.read_text(encoding="utf-8", errors="replace").splitlines()
    ascent = 12
    descent = 4
    glyphs_data = []
    cur = None
    in_bitmap = False

    for line in lines:
        line = line.strip()
        if line.startswith("FONT_ASCENT "):
            ascent = int(line.split()[1])
        elif line.startswith("FONT_DESCENT "):
            descent = int(line.split()[1])
        elif line.startswith("STARTCHAR "):
            cur = {
                "name": line.split(None, 1)[1],
                "encoding": -1,
                "dwidth": 8,
                "bbx": (8, 16, 0, -4),
                "bitmap": [],
            }
            in_bitmap = False
        elif cur is not None:
            if line.startswith("ENCODING "):
                cur["encoding"] = int(line.split()[1])
            elif line.startswith("DWIDTH "):
                cur["dwidth"] = int(line.split()[1])
            elif line.startswith("BBX "):
                parts = [int(x) for x in line.split()[1:5]]
                cur["bbx"] = tuple(parts)
            elif line == "BITMAP":
                in_bitmap = True
            elif line == "ENDCHAR":
                if cur["encoding"] >= 0:
                    glyphs_data.append(cur)
                cur = None
                in_bitmap = False
            elif in_bitmap:
                cur["bitmap"].append(line)

    px_h = (ascent + descent) * px_mult
    scale = 64
    upem = px_h * scale
    asc_u = ascent * px_mult * scale
    desc_u = -descent * px_mult * scale

    glyph_order = [".notdef"]
    cmap: Dict[int, str] = {}
    glyf_dict = {}
    hmtx_dict = {".notdef": (8 * px_mult * scale, 0)}

    pen0 = TTGlyphPen(None)
    glyf_dict[".notdef"] = pen0.glyph()

    used_names = {".notdef"}
    for g in glyphs_data:
        cp = g["encoding"]
        raw_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", g["name"]) or f"uni{cp:04X}"
        gname = raw_name if raw_name not in used_names else f"{raw_name}_{cp:04X}"
        used_names.add(gname)
        glyph_order.append(gname)
        cmap[cp] = gname

        bw, bh, bx, by = g["bbx"]
        dwidth = g["dwidth"] * px_mult
        row_bytes = (bw + 7) // 8
        total_bits = row_bytes * 8
        directed_edges = set()

        for r_idx, hex_row in enumerate(g["bitmap"]):
            val = int(hex_row, 16) if hex_row else 0
            if val == 0:
                continue
            y1 = (by + bh - r_idx) * px_mult
            y0 = y1 - px_mult
            for c in range(bw):
                if (val >> (total_bits - 1 - c)) & 1:
                    x0 = (bx + c) * px_mult
                    x1 = x0 + px_mult
                    for u, v in (
                        ((x0, y0), (x0, y1)),
                        ((x0, y1), (x1, y1)),
                        ((x1, y1), (x1, y0)),
                        ((x1, y0), (x0, y0)),
                    ):
                        if (v, u) in directed_edges:
                            directed_edges.remove((v, u))
                        else:
                            directed_edges.add((u, v))

        pen = TTGlyphPen(None)
        min_x_set = None
        if directed_edges:
            adj = defaultdict(list)
            for u, v in directed_edges:
                adj[u].append(v)
                if min_x_set is None or u[0] * scale < min_x_set:
                    min_x_set = u[0] * scale

            while adj:
                start = min(adj.keys())
                curr = start
                loop = [curr]
                prev_dx, prev_dy = 0, 1
                while True:
                    cands = adj.get(curr)
                    if not cands:
                        adj.pop(curr, None)
                        break
                    if len(cands) == 1:
                        nxt = cands.pop()
                    else:
                        right_turn = (prev_dy, -prev_dx)
                        chosen_idx = 0
                        for idx_c, cand in enumerate(cands):
                            cdx = 1 if cand[0] > curr[0] else (-1 if cand[0] < curr[0] else 0)
                            cdy = 1 if cand[1] > curr[1] else (-1 if cand[1] < curr[1] else 0)
                            if (cdx, cdy) == right_turn:
                                chosen_idx = idx_c
                                break
                        nxt = cands.pop(chosen_idx)
                    if not cands:
                        del adj[curr]
                    prev_dx = 1 if nxt[0] > curr[0] else (-1 if nxt[0] < curr[0] else 0)
                    prev_dy = 1 if nxt[1] > curr[1] else (-1 if nxt[1] < curr[1] else 0)
                    if nxt == start:
                        break
                    loop.append(nxt)
                    curr = nxt

                n = len(loop)
                pts = []
                for i in range(n):
                    p_prev = loop[(i - 1) % n]
                    p_curr = loop[i]
                    p_next = loop[(i + 1) % n]
                    if (p_curr[0] - p_prev[0]) * (p_next[1] - p_curr[1]) != (p_curr[1] - p_prev[1]) * (p_next[0] - p_curr[0]):
                        pts.append((p_curr[0] * scale, p_curr[1] * scale))
                if len(pts) >= 3:
                    pen.moveTo(pts[0])
                    for pt in pts[1:]:
                        pen.lineTo(pt)
                    pen.closePath()

        tt_glyph = pen.glyph()
        glyf_dict[gname] = tt_glyph
        hmtx_dict[gname] = (dwidth * scale, min_x_set if min_x_set is not None else 0)

    is_bold = "bold" in style_name.lower()
    fb = FontBuilder(upem, isTTF=True)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyf_dict)
    fb.setupHorizontalMetrics(hmtx_dict)
    fb.setupHorizontalHeader(ascent=asc_u, descent=desc_u)
    fb.setupNameTable(
        {
            "familyName": family_name,
            "styleName": style_name,
            "uniqueFontIdentifier": f"{family_name}-{style_name}-v4.49.1",
            "fullName": f"{family_name} {style_name}",
            "psName": f"{family_name}-{style_name}",
            "version": "Version 4.49.1",
        }
    )
    fb.setupOS2(
        sTypoAscender=asc_u,
        sTypoDescender=desc_u,
        sTypoLineGap=0,
        usWinAscent=asc_u,
        usWinDescent=-desc_u,
        sxHeight=(ascent * px_mult * 2 // 3) * scale,
        sCapHeight=max(1, ascent * px_mult - 1) * scale,
        usWeightClass=700 if is_bold else 400,
        fsSelection=0x20 if is_bold else 0x40,
    )
    fb.font["head"].macStyle = 0x01 if is_bold else 0x00
    fb.setupPost()
    dst_ttf.parent.mkdir(parents=True, exist_ok=True)
    fb.save(str(dst_ttf))
    return dst_ttf.stat().st_size, cmap


def convert_cff_otf_to_quadratic_ttf(
    src_otf: Path,
    dst_ttf: Path,
    max_err: float = 1.0,
) -> int:
    tt = TTFont(str(src_otf))
    if "CFF " in tt:
        glyph_order = tt.getGlyphOrder()
        glyph_set = tt.getGlyphSet()
        glyf_table = newTable("glyf")
        glyf_table.glyphs = {}
        glyf_table.glyphOrder = glyph_order

        for gname in glyph_order:
            pen = TTGlyphPen(glyph_set)
            cu2qu_pen = Cu2QuPen(pen, max_err=max_err, reverse_direction=True)
            glyph_set[gname].draw(cu2qu_pen)
            glyf_table.glyphs[gname] = pen.glyph()

        del tt["CFF "]
        if "VORG" in tt:
            del tt["VORG"]

        tt.sfntVersion = "\x00\x01\x00\x00"
        tt["loca"] = newTable("loca")
        tt["glyf"] = glyf_table
        tt["head"].glyphDataFormat = 0

        tt["maxp"].tableVersion = 0x00010000
        tt["maxp"].maxZones = 1
        tt["maxp"].maxTwilightPoints = 0
        tt["maxp"].maxStorage = 0
        tt["maxp"].maxFunctionDefs = 0
        tt["maxp"].maxInstructionDefs = 0
        tt["maxp"].maxStackElements = 0
        tt["maxp"].maxSizeOfInstructions = 0
        tt["maxp"].maxComponentElements = 0
        tt["maxp"].maxComponentDepth = 0

    tt.flavor = None
    if "post" in tt:
        tt["post"].formatType = 2.0
        tt["post"].extraNames = []
        tt["post"].mapping = {}

    dst_ttf.parent.mkdir(parents=True, exist_ok=True)
    tt.save(str(dst_ttf))
    return dst_ttf.stat().st_size


def copy_or_unwrap_master_ttf(src_font: Path, dst_ttf: Path) -> int:
    dst_ttf.parent.mkdir(parents=True, exist_ok=True)
    if src_font.suffix.lower() == ".ttf":
        shutil.copy2(src_font, dst_ttf)
        return dst_ttf.stat().st_size
    tt = TTFont(str(src_font))
    tt.flavor = None
    tt.save(str(dst_ttf))
    return dst_ttf.stat().st_size


def instantiate_plex_variable_cut(
    src_var_ttf: Path,
    dst_ttf: Path,
    coords: Dict[str, float],
    cmap_aliases: Dict[int, str],
) -> int:
    """
    Instantiate a static TrueType (`.ttf`) cut from an upstream IBM Plex Variable TTF.
    When `wght > 700.0` (e.g., `ExtraBold` at `wght = 800.0`), extrapolates positive
    `wght` `gvar` deltas anisotropically (`1.45x` horizontal stem weight, `1.18x`
    vertical crossbar weight) before instantiating at the `700.0` axis boundary so
    `ExtraBold` (`800`) achieves heavier `2px–3px` stems while keeping internal counters open.
    """
    tt = TTFont(str(src_var_ttf))
    req_wght = float(coords.get("wght", 400.0))
    inst_coords = dict(coords)

    if req_wght > 700.0 and "gvar" in tt:
        kx = 1.0 + (req_wght - 700.0) * 0.0045  # 1.45x at wght=800
        ky = 1.0 + (req_wght - 700.0) * 0.0018  # 1.18x at wght=800
        gvar = tt["gvar"]
        for _, variations in gvar.variations.items():
            for tv in variations:
                if "wght" in tv.axes and tv.axes["wght"][1] > 0:
                    tv.coordinates = [
                        (int(round(c[0] * kx)), int(round(c[1] * ky))) if c is not None else None
                        for c in tv.coordinates
                    ]
        inst_coords["wght"] = 700.0

    inst = instancer.instantiateVariableFont(tt, inst_coords)
    inst.flavor = None
    if req_wght > 700.0 and "OS/2" in inst:
        inst["OS/2"].usWeightClass = int(round(req_wght))

    if cmap_aliases and "cmap" in inst:
        glyph_names = set(inst.getGlyphOrder())
        for table in inst["cmap"].tables:
            if table.isUnicode():
                for cp, gname in cmap_aliases.items():
                    if cp not in table.cmap and gname in glyph_names:
                        table.cmap[cp] = gname
    dst_ttf.parent.mkdir(parents=True, exist_ok=True)
    inst.save(str(dst_ttf))
    return dst_ttf.stat().st_size


def _worker_build_task(task: dict) -> Tuple[str, str, int, str]:
    """ProcessPoolExecutor worker function for parallel static TTF synthesis."""
    kind = task["kind"]
    target_name = task["target_name"]
    src_path = Path(task["src_path"])
    dst_path = Path(task["dst_path"])

    if kind == "plex_var":
        sz = instantiate_plex_variable_cut(src_path, dst_path, task["coords"], task["aliases"])
        return (target_name, str(dst_path), sz, f"Instantiated @ {task['coords']}")
    elif kind == "copy_ttf":
        sz = copy_or_unwrap_master_ttf(src_path, dst_path)
        return (target_name, str(dst_path), sz, f"Unmodified master .ttf [{src_path.name}]")
    elif kind == "otf2ttf":
        sz = convert_cff_otf_to_quadratic_ttf(src_path, dst_path, max_err=task["max_err"])
        return (target_name, str(dst_path), sz, f"OTF -> TTF [{src_path.name}]")
    elif kind == "bdf2ttf":
        sz, cmap = convert_bdf_to_quadratic_ttf(
            src_path,
            dst_path,
            family_name="Terminus",
            style_name=task["style_name"],
            px_mult=task.get("px_mult", 1),
        )
        return (target_name, str(dst_path), sz, f"BDF -> TTF [{src_path.name} x{task.get('px_mult', 1)}, {len(cmap)} glyphs]")
    raise ValueError(f"Unknown task kind: {kind}")


# =============================================================================
# 3. DUAL-SOURCE METADATA & ICON/FONT CATALOG GENERATION
# =============================================================================

def extract_cmap_catalog_from_ttf(ttf_path: Path, min_cp: int = 0xE000, suffix: str = "") -> Dict[int, str]:
    out: Dict[int, str] = {}
    if not ttf_path.is_file():
        return out
    try:
        tt = TTFont(str(ttf_path))
        cmap = tt.getBestCmap() or {}
        for cp, gname in sorted(cmap.items()):
            if cp >= min_cp and not gname.startswith("."):
                clean_name = gname
                if clean_name.startswith("ph-"):
                    clean_name = clean_name[3:]
                if suffix and not clean_name.endswith(suffix):
                    clean_name = f"{clean_name}{suffix}"
                out[int(cp)] = clean_name
    except Exception:
        pass
    return out


def generate_icon_and_font_catalogs(
    file_index: Dict[str, Path],
    out_static_dir: Path,
    meta_out_dir: Path,
) -> Dict[str, int]:
    meta_out_dir.mkdir(parents=True, exist_ok=True)

    fa7_map: Dict[int, str] = {}
    lucide_map: Dict[int, str] = {}
    phosphor_map: Dict[int, str] = {}
    tabler_map: Dict[int, str] = {}
    tabler_filled_map: Dict[int, str] = {}
    terminus_map: Dict[int, str] = {}

    for _, p in sorted(file_index.items()):
        if not p.is_file() or not p.name.startswith("char_manifest_") or not p.name.endswith(".json"):
            continue
        try:
            mdata = json.loads(p.read_text(encoding="utf-8"))
            shutil.copy2(p, meta_out_dir / p.name)
            fam_id = mdata.get("family_id", "")
            by_cp_raw = mdata.get("by_codepoint", {})
            if fam_id == "icon_fa7":
                for hk, nm in by_cp_raw.items():
                    fa7_map[int(hk, 16)] = nm
            elif fam_id == "icon_lucide":
                for hk, nm in by_cp_raw.items():
                    lucide_map[int(hk, 16)] = nm
            elif fam_id == "icon_phosphor":
                for hk, nm in by_cp_raw.items():
                    phosphor_map[int(hk, 16)] = nm
            elif fam_id == "icon_tabler":
                for hk, nm in by_cp_raw.items():
                    tabler_map[int(hk, 16)] = nm
            elif fam_id == "terminus":
                for hk, nm in by_cp_raw.items():
                    terminus_map[int(hk, 16)] = nm
        except Exception:
            pass

    for fn in ("FontAwesome7-Solid.ttf", "FontAwesome7-Regular.ttf", "FontAwesome7-Brands.ttf"):
        for cp, gname in extract_cmap_catalog_from_ttf(out_static_dir / fn, min_cp=0xE000).items():
            fa7_map.setdefault(cp, gname)

    for cp, gname in extract_cmap_catalog_from_ttf(out_static_dir / "Lucide-Regular.ttf", min_cp=0xE000).items():
        lucide_map.setdefault(cp, gname)

    for cp, gname in extract_cmap_catalog_from_ttf(out_static_dir / "Phosphor-Regular.ttf", min_cp=0xE000).items():
        phosphor_map.setdefault(cp, gname)

    for cp, gname in extract_cmap_catalog_from_ttf(out_static_dir / "Tabler-Regular.ttf", min_cp=0xE000).items():
        tabler_map.setdefault(cp, gname)

    for cp, gname in extract_cmap_catalog_from_ttf(out_static_dir / "Tabler-Filled.ttf", min_cp=0xE000).items():
        base_n = gname[:-7] if gname.endswith("-filled") else gname
        tabler_filled_map[cp] = base_n
        tabler_map.setdefault(cp, f"{base_n}-filled")

    if not terminus_map and (out_static_dir / "Terminus-Normal-16.ttf").is_file():
        terminus_map = extract_cmap_catalog_from_ttf(out_static_dir / "Terminus-Normal-16.ttf", min_cp=0x0020)

    vendor_maps = [
        ("icon_fa7", "fa7_catalog.json", "Font Awesome v7.3.1", fa7_map),
        ("icon_lucide", "lucide_catalog.json", "Lucide Icons v1.67.0", lucide_map),
        ("icon_phosphor", "phosphor_catalog.json", "Phosphor Icons v2.1.0", phosphor_map),
        ("icon_tabler", "tabler_catalog.json", "Tabler Icons v3.50.0 (Outline + Filled)", tabler_map),
        ("icon_tabler_filled", "tabler_filled_catalog.json", "Tabler Icons v3.50.0 (Filled Only)", tabler_filled_map),
    ]

    unified_by_cp: Dict[str, Dict[str, str]] = {}
    unified_by_name: Dict[str, Dict[str, str]] = {}
    counts: Dict[str, int] = {}

    for vendor_key, catalog_fname, title, vmap in vendor_maps:
        by_cp = {f"0x{cp:04X}": name for cp, name in sorted(vmap.items())}
        by_name = {name: f"0x{cp:04X}" for cp, name in sorted(vmap.items(), key=lambda x: x[1])}
        unified_by_cp[vendor_key] = by_cp
        unified_by_name[vendor_key] = by_name
        counts[vendor_key] = len(by_cp)

        catalog_payload = {
            "catalog_version": TOOL_VERSION,
            "vendor": vendor_key,
            "title": title,
            "total_icons": len(by_cp),
            "by_name": by_name,
            "by_codepoint": by_cp,
        }
        (meta_out_dir / catalog_fname).write_text(
            json.dumps(catalog_payload, indent=2) + "\n", encoding="utf-8"
        )

    unified_payload = {
        "schema_version": TOOL_VERSION,
        "description": "Master codepoint <-> semantic icon name registry across Font Awesome 7.3.1, Lucide, Phosphor, and Tabler.",
        "counts": counts,
        "by_codepoint": unified_by_cp,
        "by_name": unified_by_name,
        **unified_by_cp,
    }
    (meta_out_dir / "unified_icon_names.json").write_text(
        json.dumps(unified_payload, indent=2) + "\n", encoding="utf-8"
    )

    if terminus_map:
        term_by_cp = {f"0x{cp:04X}": gname for cp, gname in sorted(terminus_map.items())}
        term_payload = {
            "catalog_version": TOOL_VERSION,
            "family": "terminus",
            "title": "Terminus Font v4.49.1 (24 Native & Exact-2x TrueType Strikes from BDF Masters)",
            "license": "SIL Open Font License 1.1",
            "total_glyphs": len(term_by_cp),
            "ttf_strikes": [row[0] for row in TERMINUS_BDF_CONVERSION_TABLE],
            "by_codepoint": term_by_cp,
        }
        (meta_out_dir / "terminus_catalog.json").write_text(
            json.dumps(term_payload, indent=2) + "\n", encoding="utf-8"
        )
        counts["terminus"] = len(term_by_cp)

    text_families = {
        "sans": [row[0] for row in PLEX_VARIABLE_INSTANTIATION_TABLE if row[1] == "sans"],
        "cond": [row[0] for row in PLEX_VARIABLE_INSTANTIATION_TABLE if row[1] == "cond"],
        "mono": [row[0] for row in PLEX_VARIABLE_INSTANTIATION_TABLE if row[1] == "mono"],
        "serif": [row[0] for row in PLEX_VARIABLE_INSTANTIATION_TABLE if row[1] == "serif"],
        "math": ["IBMPlexMath-Regular.ttf"],
        "terminus": [row[0] for row in TERMINUS_BDF_CONVERSION_TABLE],
    }
    for cat_name in ("humid1_font_catalog.json", "plex_catalog.json"):
        (meta_out_dir / cat_name).write_text(
            json.dumps(
                {
                    "catalog_version": TOOL_VERSION,
                    "description": "Humiditron / humid1 Text & Technical Font Catalog (IBM Plex wght 100..800 + 24 Terminus Strikes)",
                    "families": text_families,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    return counts


def collect_upstream_licenses(file_index: Dict[str, Path], out_static_dir: Path) -> List[str]:
    lic_dir = out_static_dir / "licenses"
    lic_dir.mkdir(parents=True, exist_ok=True)
    saved: List[str] = []

    for _, path in sorted(file_index.items()):
        if not path.is_file():
            continue
        low = path.name.lower()
        p_str = path.as_posix().lower()
        if low in ("license.txt", "license", "ofl.txt"):
            target_name = None
            if "terminus" in p_str and low == "ofl.txt":
                target_name = "Terminus_OFL.txt"
            elif "math" in p_str:
                target_name = "IBMPlex_Math_OFL.txt"
            elif "mono" in p_str:
                target_name = "IBMPlex_Mono_OFL.txt"
            elif "sans" in p_str:
                target_name = "IBMPlex_Sans_OFL.txt"
            elif "serif" in p_str:
                target_name = "IBMPlex_Serif_OFL.txt"
            elif "awsome" in p_str or "awesome" in p_str:
                target_name = "FontAwesome7_LICENSE.txt"
            elif "lucide" in p_str:
                target_name = "Lucide_ISC_LICENSE.txt"
            elif "phosphor" in p_str:
                target_name = "Phosphor_MIT_LICENSE.txt"
            elif "tabler" in p_str:
                target_name = "Tabler_MIT_LICENSE.txt"

            if target_name and target_name not in saved:
                shutil.copy2(path, lic_dir / target_name)
                saved.append(target_name)
                if target_name.startswith("IBMPlex_Sans"):
                    shutil.copy2(path, out_static_dir / "OFL.txt")
    return sorted(saved)


# =============================================================================
# 4. MASTER PARALLEL BUILD & VERIFICATION PIPELINE
# =============================================================================

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_static_ttf_directory(static_dir: Path) -> Tuple[int, int]:
    ttf_files = sorted(static_dir.glob("*.ttf"))
    print("\n" + "=" * 108)
    print(f"STATIC TRUETYPE (.TTF) ASSET VERIFICATION REPORT — {static_dir}")
    print("=" * 108)
    print(f"{'TTF Filename':38s} | {'Format':8s} | {'UPEM':4s} | {'Asc/Desc':10s} | {'Glyphs':6s} | {'Cmap':6s} | {'Size (Bytes)':12s} | {'Status'}")
    print("-" * 108)

    passed = 0
    failed = 0
    for fpath in ttf_files:
        try:
            tt = TTFont(str(fpath))
            has_glyf = "glyf" in tt and "loca" in tt
            is_uncompressed = tt.flavor is None
            upem = tt["head"].unitsPerEm
            asc = tt["hhea"].ascent
            desc = tt["hhea"].descent
            nglyphs = len(tt.getGlyphOrder())
            ncmap = len(tt.getBestCmap() or {})
            fsize = fpath.stat().st_size
            ok = has_glyf and is_uncompressed and nglyphs > 0 and ncmap > 0
            status = "PASS" if ok else "FAIL"
            if ok:
                passed += 1
            else:
                failed += 1
            fmt_str = "TTF/glyf" if has_glyf else "OTF/CFF"
            print(
                f"{fpath.name:38s} | {fmt_str:8s} | {upem:4d} | {asc:+4d}/{desc:+4d} | "
                f"{nglyphs:6d} | {ncmap:6d} | {fsize:12,d} | {status}"
            )
        except Exception as exc:
            failed += 1
            print(f"{fpath.name:38s} | ERROR: {exc}")

    print("=" * 108)
    print(f"[+] Verification Summary: {passed} PASSED, {failed} FAILED (Total: {len(ttf_files)} .ttf files)\n")
    return passed, failed


def build_all_static_assets(
    src_dir: Path,
    out_dir: Path,
    meta_out_dir: Optional[Path] = None,
    families_filter: Optional[Sequence[str]] = None,
    cu2qu_max_err: float = 1.0,
    force: bool = False,
    extra_roots: Optional[Sequence[Path]] = None,
    jobs: Optional[int] = None,
) -> List[Path]:
    t0 = time.perf_counter()
    out_dir.mkdir(parents=True, exist_ok=True)
    if meta_out_dir is None:
        meta_out_dir = (out_dir.parent / "metadata") if out_dir.parent.name == "build" else (out_dir / "metadata")
    meta_out_dir.mkdir(parents=True, exist_ok=True)

    max_workers = jobs if (jobs and jobs > 0) else (os.cpu_count() or 4)
    allowed_fams = set(f.lower() for f in families_filter) if families_filter else None
    roots_to_scan = [src_dir] + (list(extra_roots) if extra_roots else [])

    file_index = index_source_tree(roots_to_scan)
    tasks: List[dict] = []
    built_files: List[Path] = []

    for target_name, fam_group, src_fname, coords, aliases in PLEX_VARIABLE_INSTANTIATION_TABLE:
        if allowed_fams and fam_group not in allowed_fams and "plex" not in allowed_fams:
            continue
        dst_path = out_dir / target_name
        if dst_path.is_file() and not force:
            built_files.append(dst_path)
            continue
        src_path = file_index.get(src_fname) or file_index.get(src_fname.lower())
        if src_path:
            tasks.append({
                "kind": "plex_var",
                "target_name": target_name,
                "src_path": str(src_path),
                "dst_path": str(dst_path),
                "coords": coords,
                "aliases": aliases,
            })

    if not allowed_fams or "math" in allowed_fams or "plex" in allowed_fams:
        math_src = file_index.get("IBMPlexMath-Regular.ttf") or file_index.get("ibmplexmath-regular.ttf")
        math_dst = out_dir / "IBMPlexMath-Regular.ttf"
        if math_src and (not math_dst.is_file() or force):
            tasks.append({
                "kind": "copy_ttf",
                "target_name": "IBMPlexMath-Regular.ttf",
                "src_path": str(math_src),
                "dst_path": str(math_dst),
            })
        elif math_dst.is_file():
            built_files.append(math_dst)

    if not allowed_fams or "terminus" in allowed_fams or "plex" in allowed_fams:
        for target_name, fam_group, src_bdf_name, style_name, px_mult in TERMINUS_BDF_CONVERSION_TABLE:
            dst_path = out_dir / target_name
            src_bdf = file_index.get(src_bdf_name) or file_index.get(src_bdf_name.lower())
            if src_bdf and (not dst_path.is_file() or force):
                tasks.append({
                    "kind": "bdf2ttf",
                    "target_name": target_name,
                    "src_path": str(src_bdf),
                    "dst_path": str(dst_path),
                    "style_name": style_name,
                    "px_mult": px_mult,
                })
            elif dst_path.is_file():
                built_files.append(dst_path)

    for target_name, fam_group, src_fname, action in ICON_CONVERSION_TABLE:
        if allowed_fams and fam_group not in allowed_fams and "icons" not in allowed_fams:
            continue
        dst_path = out_dir / target_name
        if dst_path.is_file() and not force:
            built_files.append(dst_path)
            continue
        src_path = file_index.get(src_fname) or file_index.get(src_fname.lower())
        if not src_path:
            continue
        if action == "otf2ttf":
            tasks.append({
                "kind": "otf2ttf",
                "target_name": target_name,
                "src_path": str(src_path),
                "dst_path": str(dst_path),
                "max_err": cu2qu_max_err,
            })
        else:
            tasks.append({
                "kind": "copy_ttf",
                "target_name": target_name,
                "src_path": str(src_path),
                "dst_path": str(dst_path),
            })

    if tasks:
        print(f"[*] Executing {len(tasks)} font conversion tasks across {max_workers} CPU worker processes...")
        with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as pool:
            for target_name, dst_str, sz, desc in pool.map(_worker_build_task, tasks):
                built_files.append(Path(dst_str))
                print(f"    [+] {target_name:36s} ({sz:9,d} B) — {desc}")

    if (out_dir / "Terminus-Normal-16.ttf").is_file():
        shutil.copy2(out_dir / "Terminus-Normal-16.ttf", out_dir / "Terminus-Regular.ttf")
    if (out_dir / "Terminus-Bold-16.ttf").is_file():
        shutil.copy2(out_dir / "Terminus-Bold-16.ttf", out_dir / "Terminus-Bold.ttf")

    print(f"[*] Generating Searchable Icon & Font Catalog JSONs in {meta_out_dir}...")
    counts = generate_icon_and_font_catalogs(file_index, out_dir, meta_out_dir)
    for v_key, cnt in counts.items():
        print(f"    [+] Catalog {v_key:18s} : {cnt:5,d} entries indexed")

    sub_meta = out_dir / "metadata"
    if sub_meta.resolve() != meta_out_dir.resolve():
        sub_meta.mkdir(parents=True, exist_ok=True)
        for jf in meta_out_dir.glob("*.json"):
            shutil.copy2(jf, sub_meta / jf.name)

    saved_lics = collect_upstream_licenses(file_index, out_dir)
    ttf_list = sorted(out_dir.glob("*.ttf"))
    manifest = {
        "manifest_version": TOOL_VERSION,
        "repository": "https://github.com/Humidyne-Labs/epd-font",
        "license": "MIT",
        "generator": "build_static_ttf_assets.py",
        "cu2qu_max_err": cu2qu_max_err,
        "total_ttf_files": len(ttf_list),
        "catalog_counts": counts,
        "licenses": saved_lics,
        "assets": [
            {
                "filename": p.name,
                "size_bytes": p.stat().st_size,
                "sha256": sha256_file(p),
            }
            for p in ttf_list
        ],
    }
    (meta_out_dir / "asset_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "asset_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    elapsed = time.perf_counter() - t0
    print(f"[+] Built & indexed {len(ttf_list)} static .ttf files in {elapsed:.2f}s using {max_workers} CPU cores.")
    return built_files


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="build_static_ttf_assets.py",
        description=(
            f"Humidyne Labs / Humiditron `epd-font` v{TOOL_VERSION} — Multi-Core Static TrueType (.ttf) Asset & Metadata Builder."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("-s", "--src-dir", type=str, default=None, help="Input root directory (default: <repo>/assets)")
    parser.add_argument("-o", "--out-dir", type=str, default=None, help="Output directory for static .ttf files (default: <repo>/build/static_ttfs)")
    parser.add_argument("-m", "--meta-out-dir", type=str, default=None, help="Output directory for metadata JSON catalogs (default: <repo>/build/metadata)")
    parser.add_argument("-f", "--families", type=str, nargs="+", default=None, help="Optional family filter: plex, sans, cond, mono, serif, math, terminus, icons, fa7, lucide, phosphor, tabler")
    parser.add_argument("-j", "--jobs", type=int, default=None, help="Number of parallel CPU worker processes (default: all CPU cores)")
    parser.add_argument("--cu2qu-max-err", type=float, default=1.0, help="Curve approximation tolerance for FA7 .otf -> .ttf (default: 1.0)")
    parser.add_argument("--force", action="store_true", help="Overwrite and regenerate all static .ttf files")
    parser.add_argument("--verify", action="store_true", help="Verify every generated .ttf file and print audit table")
    parser.add_argument("--verify-only", action="store_true", help="Only run diagnostic verification on --out-dir")
    parser.add_argument("--plex-src", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--icons-src", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--raw-root", type=str, nargs="+", default=None, help=argparse.SUPPRESS)
    return parser


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent if script_dir.name == "fonts" else script_dir.parent
    parser = build_arg_parser()
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve() if args.out_dir else (repo_root / "build" / "static_ttfs").resolve()
    meta_out_dir = Path(args.meta_out_dir).resolve() if args.meta_out_dir else (repo_root / "build" / "metadata").resolve()
    src_dir = Path(args.src_dir).resolve() if args.src_dir else (repo_root / "assets").resolve()

    extra_roots: List[Path] = []
    if args.plex_src:
        extra_roots.append(Path(args.plex_src).resolve())
    if args.icons_src:
        extra_roots.append(Path(args.icons_src).resolve())
    if args.raw_root:
        for r in args.raw_root:
            extra_roots.append(Path(r).resolve())

    if not args.verify_only:
        build_all_static_assets(
            src_dir=src_dir,
            out_dir=out_dir,
            meta_out_dir=meta_out_dir,
            families_filter=args.families,
            cu2qu_max_err=args.cu2qu_max_err,
            force=args.force,
            extra_roots=extra_roots,
            jobs=args.jobs,
        )

    if args.verify or args.verify_only:
        _, failed = verify_static_ttf_directory(out_dir)
        if failed > 0:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
