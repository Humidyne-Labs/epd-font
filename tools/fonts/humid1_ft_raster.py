#!/usr/bin/env python3
"""
humid1_ft_raster.py (v1.0.15)
=============================
Humidyne Labs / Humiditron `epd-font` FreeType 2 Ctypes Binding, Semantic Glyph Registry,
Kerning Extractor & 1-BPP Scanline Rasterizer Module.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import json
import math
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import logging
import os
import shutil
from dataclasses import dataclass, field
import numpy as np
from fontTools.ttLib import TTFont, TTLibFileIsCollectionError
from fontTools.varLib import instancer

logging.getLogger("fontTools").setLevel(logging.ERROR)


def open_ttfont_safe(font_path: Path | str, font_number: int = 0, lazy: bool = False) -> TTFont:
    """
    Safely open a `.ttf`, `.otf`, or `.ttc`/`.otc` TrueType Collection file via fontTools.
    Fixes the v1.0.15 crash (`TTLibFileIsCollectionError: specify a font number between 0 and N`)
    when scanning or rasterizing `.ttc` font collections (such as `IosevkaAile-Bold.ttc`).
    """
    fp_str = str(font_path)
    is_ttc = fp_str.lower().endswith((".ttc", ".otc"))
    try:
        return TTFont(fp_str, fontNumber=font_number if is_ttc else None, lazy=lazy)
    except TTLibFileIsCollectionError:
        return TTFont(fp_str, fontNumber=font_number, lazy=lazy)

TOOL_VERSION = "1.0.15"

FT_LOAD_NO_HINTING = 1 << 1


def format_strike_symbol(family: str, role: str, size_px: int) -> str:
    """
    Canonical v1.0.15 `humid1_` symbol naming convention:
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


def compute_dynamic_threshold(
    gray_arr: np.ndarray,
    weight_class: int = 500,
    size_px: int = 16,
    codepoint: int = 0,
) -> int:
    """
    Compute a Weight-, Size-, and Histogram/Topology-Adaptive Binarization Threshold T* in [88..164] (v1.0.15):
      - Why fixed 128 is suboptimal:
        * On light/medium weights (w300..w500) or small sizes (10..14px), 1.5px stems split across adjacent
          columns at ~42%..48% coverage (val 107..122) and drop to 1px under a fixed 128 threshold.
        * On heavy weights (w700..w900) at 12..16px, interior counter walls bleed gray anti-aliased fringe
          pixels (val 128..145) into enclosed counters ('a', 'e', '8', 'B'), pinching them shut at 128.
      - Combines a weight/size prior T_base with Otsu bimodal variance on active pixels (>16) and selects
        the candidate threshold in {T0-12, T0-6, T0, T0+6, T0+12} that preserves enclosed counters and >=2px stems.
    """
    if gray_arr is None or gray_arr.size == 0:
        return 128
    t_prior = int(np.clip(128 + round(0.065 * (weight_class - 550)) - max(0, 16 - size_px) * 2, 92, 160))
    active = gray_arr[gray_arr > 16]
    if active.size < 6:
        return t_prior

    # Compute fast 1D Otsu threshold on active ink/edge pixels
    hist, _ = np.histogram(active, bins=32, range=(16, 256))
    hist = hist.astype(np.float64)
    total = float(active.size)
    bin_centers = np.linspace(20.0, 252.0, 32)
    sum_all = float(np.sum(hist * bin_centers))
    w_bg = 0.0
    sum_bg = 0.0
    best_var = -1.0
    t_otsu = float(t_prior)
    for i in range(32):
        w_bg += hist[i]
        if w_bg <= 0.0 or w_bg >= total:
            continue
        w_fg = total - w_bg
        sum_bg += hist[i] * bin_centers[i]
        m_bg = sum_bg / w_bg
        m_fg = (sum_all - sum_bg) / w_fg
        var_between = w_bg * w_fg * ((m_bg - m_fg) ** 2)
        if var_between > best_var:
            best_var = var_between
            t_otsu = float(bin_centers[i])

    t0 = int(np.clip(round(0.65 * t_prior + 0.35 * t_otsu), 90, 162))
    ch = chr(codepoint) if 0x20 <= codepoint <= 0xFFFF else ""
    canon_holes = {"0": 1, "4": 1, "6": 1, "8": 2, "9": 1, "A": 1, "B": 2, "D": 1, "O": 1, "P": 1, "Q": 1, "R": 1, "a": 1, "b": 1, "d": 1, "e": 1, "g": 1, "o": 1, "p": 1, "q": 1, "%": 2}.get(ch, 0)
    pinch_forbid = ch in set("CEFGHIJKLMNSTUVWXYZcfhijlmnrstuvwxyz!()[]{}/\|<>+-=~")

    best_t = t0
    best_sc = -1e9
    for dt in (-12, -6, 0, 6, 12):
        tc = int(np.clip(t0 + dt, 88, 164))
        bw = (gray_arr >= tc).astype(np.uint8)
        if np.count_nonzero(bw) == 0:
            continue
        # Measure >=2px horizontal run survival
        h, w = bw.shape
        ge2 = 0
        tot_r = 0
        for r in range(h):
            in_r = False
            s = 0
            for c in range(w):
                if bw[r, c] and not in_r:
                    s = c
                    in_r = True
                elif not bw[r, c] and in_r:
                    tot_r += 1
                    if (c - s) >= 2:
                        ge2 += 1
                    in_r = False
            if in_r:
                tot_r += 1
                if (w - s) >= 2:
                    ge2 += 1
        stem_ratio = (float(ge2) / float(tot_r)) if tot_r > 0 else 0.0
        sc = 25.0 * stem_ratio - 0.15 * abs(dt)
        # Quick interior zero-pocket check for counter characters
        if canon_holes > 0 and h >= 5 and w >= 4:
            interior = bw[1:-1, 1:-1]
            zero_px = int(np.sum(interior == 0))
            if zero_px < canon_holes * 2:
                sc -= 40.0
        elif pinch_forbid and weight_class >= 650 and tc < t_prior:
            sc -= 5.0
        if sc > best_sc:
            best_sc = sc
            best_t = tc
    return best_t


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
    auto_floor: bool = False,
    min_stem: int = 2,
    repair_engine: str = "hybrid",
    font_number: int = 0,
) -> Tuple[List[GlyphStrike], int, int, int, int, List[Tuple[int, int, int, int, int]]]:
    """
    Rasterize a 1-bpp font strike using FreeType2 + fontTools with optional FontAwesome 5 merge,
    JSON patch manifest overrides, and direct ASCII .txt folder overrides.
    """
    face_ptr = ctypes.POINTER(FT_FaceRec)()
    if ft.FT_New_Face(ft_lib, str(font_path).encode("utf-8"), int(font_number), ctypes.byref(face_ptr)) != 0:
        raise RuntimeError(f"FT_New_Face failed for {font_path}")
    ft.FT_Set_Pixel_Sizes(face_ptr, 0, size_px)

    tt = open_ttfont_safe(font_path, font_number=font_number)
    cmap = tt.getBestCmap() or {}
    hmtx = tt["hmtx"].metrics
    upem = tt["head"].unitsPerEm
    os2_weight_class = int(getattr(tt["OS/2"], "usWeightClass", 500) or 500) if "OS/2" in tt else 500
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
        from humid1_ascii_patches import parse_ascii_glyph_folder
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
            gray_np = np.zeros((bmp.rows, bmp.width), dtype=np.uint8)
            for r in range(bmp.rows):
                for c in range(bmp.width):
                    gray_np[r, c] = bmp.buffer[r * bmp.pitch + c]
            eff_thresh = (
                compute_dynamic_threshold(gray_np, weight_class=os2_weight_class, size_px=size_px, codepoint=code)
                if (threshold <= 0 or "dynamic" in raster_mode.lower())
                else threshold
            )
            for r in range(bmp.rows):
                raw_rows.append("".join("#" if gray_np[r, c] >= eff_thresh else "." for c in range(bmp.width)))

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
            s_tt = open_ttfont_safe(sp, font_number=0)
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
            fa_tt = open_ttfont_safe(fa_path, font_number=0)
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


