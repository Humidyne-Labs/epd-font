#!/usr/bin/env python3
"""
humid1_ft_raster.py (v1.0.19c)
=============================
A 1-bit EPD font generator and asset pipeline for embedded displays.
Repository : https://github.com/Humidyne-Labs/epd-font
Authors    : Humiditron (https://github.com/humiditron) & AI/LLM Development Partner
License    : MIT License

FreeType 2 Ctypes Binding, Semantic Glyph Registry, Kerning Extractor,
and Multi-Pipeline 1-BPP Rasterizer Module (`raw-unhinted`, `raw-hinted`,
`svg-potrace`, `mdf`, `msdf`, `sdf-smoothstep`, `adf-biquadratic`, `otsu-adaptive`,
and `exact-mono`).
"""

from __future__ import annotations

import ctypes
import ctypes.util
import hashlib
import json
import numpy as np
import logging
import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from fontTools.ttLib import TTFont, TTLibFileIsCollectionError

from humid1_bilevel_pipelines import (
    CANONICAL_PIPELINES,
    FT_LOAD_FORCE_AUTOHINT,
    FT_LOAD_MONOCHROME,
    FT_LOAD_NO_AUTOHINT,
    FT_LOAD_NO_HINTING,
    FT_LOAD_RENDER,
    FT_LOAD_TARGET_LIGHT,
    FT_LOAD_TARGET_MONO,
    FT_LOAD_TARGET_NORMAL,
    FT_PIXEL_MODE_GRAY,
    FT_PIXEL_MODE_MONO,
    normalize_pipeline_name,
    render_glyph_via_pipeline,
    save_debug_stage_artifacts,
)
from humid1_runtime import resolve_font_file_recursive

logging.getLogger("fontTools").setLevel(logging.ERROR)

TOOL_VERSION = "1.0.19c"


def _convert_bdf_to_cached_ttf(bdf_path: Path) -> Path:
    """Convert a .bdf bitmap font on-the-fly to a cached .ttf inside build/cache/bdf_ttfs/."""
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent if script_dir.name == "fonts" else script_dir.parent
    cache_dir = repo_root / "build" / "cache" / "bdf_ttfs"
    cache_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(f"{bdf_path.resolve()}|{bdf_path.stat().st_size}".encode("utf-8")).hexdigest()[:12]
    dst_ttf = cache_dir / f"{bdf_path.stem}_{digest}.ttf"
    if not dst_ttf.is_file():
        import build_static_ttf_assets as bsta
        bsta.convert_bdf_to_ttf(bdf_path, dst_ttf, family_name=bdf_path.stem, style_name="Regular", px_mult=1)
    return dst_ttf


def open_ttfont_safe(font_path: Path | str, font_number: int = 0, lazy: bool = False) -> TTFont:
    """
    Safely open a `.ttf`, `.otf`, `.ttc`/`.otc`, `.woff`, or `.bdf` font file via fontTools.
    Automatically converts `.bdf` bitmap fonts into a cached quadratic `.ttf` in `build/cache/`.
    """
    p = Path(font_path)
    if p.suffix.lower() == ".bdf":
        p = _convert_bdf_to_cached_ttf(p)
    fp_str = str(p)
    is_ttc = fp_str.lower().endswith((".ttc", ".otc"))
    try:
        return TTFont(fp_str, fontNumber=font_number if is_ttc else None, lazy=lazy)
    except TTLibFileIsCollectionError:
        return TTFont(fp_str, fontNumber=font_number, lazy=lazy)


def format_strike_symbol(family: str, role: str, size_px: int) -> str:
    """
    Canonical v1.0.19c `humid1_` symbol naming convention:
      - Core UI/Telemetry families (sans, cond, mono, serif, math) -> humid1_font_plex_<family>_<role>_<size>
      - Explicit Noto families (noto_sans, noto_cond, noto_mono, noto_serif, noto_math) -> humid1_font_<family>_<role>_<size>
      - Explicit Plex families (plex_sans, plex_cond, plex_mono, plex_serif, plex_math) -> humid1_font_<family>_<role>_<size>
      - Terminus family (terminus)                        -> humid1_font_terminus_<role>_<size>
      - Modular Icon families (icon_fa7, icon_lucide...)  -> humid1_<family>_<role>_<size>
      - Custom font families                              -> humid1_font_<family>_<role>_<size>
    """
    if family in ("sans", "cond", "mono", "serif", "math"):
        return f"humid1_font_plex_{family}_{role}_{size_px}"
    elif family.startswith(("noto_", "plex_")):
        return f"humid1_font_{family}_{role}_{size_px}"
    elif family == "terminus":
        return f"humid1_font_terminus_{role}_{size_px}"
    elif family.startswith("icon_"):
        return f"humid1_{family}_{role}_{size_px}"
    return f"humid1_font_{family}_{role}_{size_px}"


# =============================================================================
# 1. UNICODE RANGE PROFILES & COMPLEX GLYPH DIAGNOSTIC SET
# =============================================================================

RANGE_UI_STR = (
    "0x20-0x7E,0xB0,0xB1,0xB2,0xB3,0xB5,0x0394,"
    "0x2010-0x2014,0x2022,0x2190-0x2193"
)

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

COMPLEX_15_CODEPOINTS = {
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
TROUBLE_15_CODEPOINTS = COMPLEX_15_CODEPOINTS

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

ICON_NAME_REGISTRY: Dict[str, Any] = {}
_TT_META_CACHE: Dict[Tuple[str, int], dict] = {}


def load_icon_name_registry(static_dir: Path) -> None:
    """
    Load `unified_icon_names.json` into `ICON_NAME_REGISTRY` in place (`clear()` + `update()`)
    so all modules importing `ICON_NAME_REGISTRY` share the populated dictionary reference.
    """
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
    ]:
        if cand.is_file():
            try:
                loaded = json.loads(cand.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    ICON_NAME_REGISTRY.clear()
                    ICON_NAME_REGISTRY.update(loaded)
                    return
            except Exception:
                pass


def get_semantic_glyph_name(code: int, family: str = "") -> str:
    hex_k = f"0x{code:04X}"
    by_cp = ICON_NAME_REGISTRY.get("by_codepoint", {})
    if family == "icon_tabler":
        tf_map = ICON_NAME_REGISTRY.get("icon_tabler_filled") or by_cp.get("icon_tabler_filled") or {}
        if hex_k in tf_map:
            raw = str(tf_map[hex_k])
            return re.sub(r"[^A-Za-z0-9_-]+", "_", raw).strip("_")
    if family:
        f_map = ICON_NAME_REGISTRY.get(family) or by_cp.get(family) or {}
        if isinstance(f_map, dict) and hex_k in f_map:
            raw = str(f_map[hex_k])
            return re.sub(r"[^A-Za-z0-9_-]+", "_", raw).strip("_")
    if code in SAFE_CHAR_NAMES:
        return SAFE_CHAR_NAMES[code]
    elif 0x30 <= code <= 0x39 or 0x41 <= code <= 0x5A or 0x61 <= code <= 0x7A:
        return chr(code)
    return f"uni{code:04X}"


def safe_glyph_filename(code: int, family: str = "") -> str:
    """Return a filesystem-safe, human-readable filename for a codepoint."""
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
# 2. FREETYPE 2 CTYPES STRUCTURES & LOADER
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
        ("face_flags", ctypes.c_long),
        ("face_index", ctypes.c_long),
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


def load_freetype() -> Tuple[ctypes.CDLL, ctypes.c_void_p]:
    """
    Locate and initialize libfreetype across Windows and Linux hosts, checking:
      1. `freetype-py` bundled shared library (`import freetype`) if installed via pip
      2. `ctypes.util.find_library("freetype")`
      3. Standard OS library names (`libfreetype-6.dll`, `freetype.dll`, `libfreetype.so.6`)
    """
    candidates: List[str] = []
    try:
        import freetype  # type: ignore
        ft_pkg_dir = Path(freetype.__file__).resolve().parent
        for dll_cand in ft_pkg_dir.rglob("*freetype*"):
            if dll_cand.suffix.lower() in (".dll", ".so") or ".so." in dll_cand.name:
                candidates.append(str(dll_cand))
    except Exception:
        pass

    found_sys = ctypes.util.find_library("freetype")
    if found_sys:
        candidates.append(found_sys)

    if os.name == "nt":
        candidates.extend(["libfreetype-6.dll", "freetype.dll", "libfreetype.dll"])
    else:
        candidates.extend(["libfreetype.so.6", "libfreetype.so"])

    ft = None
    last_err = None
    for cand in candidates:
        try:
            ft = ctypes.CDLL(cand)
            break
        except Exception as exc:
            last_err = exc

    if ft is None:
        raise RuntimeError(f"Failed to locate FreeType2 shared library (tried {candidates}): {last_err}")

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
    rows: List[str] = field(default_factory=list)
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
# 3. CACHED FONTTOOLS METADATA & KERNING EXTRACTION (ZERO FILE-HANDLE LEAKS)
# =============================================================================

def _extract_raw_kerning_dict(tt: TTFont) -> Dict[Tuple[str, str], int]:
    """Extract raw glyph-name kerning pairs from `kern` and `GPOS` once per font and close TTFont."""
    raw_pairs: Dict[Tuple[str, str], int] = {}
    if "kern" in tt:
        for subtable in tt["kern"].kernTables:
            if hasattr(subtable, "kernTable"):
                for (l_name, r_name), val in subtable.kernTable.items():
                    if val != 0:
                        raw_pairs[(l_name, r_name)] = int(val)

    if "GPOS" in tt and hasattr(tt["GPOS"].table, "LookupList") and tt["GPOS"].table.LookupList:
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
                        if l_idx >= len(actual.PairSet):
                            continue
                        pset = actual.PairSet[l_idx]
                        for pvr in pset.PairValueRecord:
                            r_name = pvr.SecondGlyph
                            if pvr.Value1 and getattr(pvr.Value1, "XAdvance", 0):
                                raw_pairs[(l_name, r_name)] = int(pvr.Value1.XAdvance)
                elif actual.Format == 2:
                    cdef1 = getattr(actual.ClassDef1, "classDefs", {})
                    cdef2 = getattr(actual.ClassDef2, "classDefs", {})
                    class2_Reverse: Dict[int, List[str]] = {}
                    for g_n, c_idx in cdef2.items():
                        class2_Reverse.setdefault(c_idx, []).append(g_n)
                    for l_name in cov.glyphs:
                        c1 = cdef1.get(l_name, 0)
                        if c1 >= len(actual.Class1Record):
                            continue
                        c1_rec = actual.Class1Record[c1]
                        for c2, c2_rec in enumerate(c1_rec.Class2Record):
                            v1 = c2_rec.Value1
                            xadv = getattr(v1, "XAdvance", 0) if v1 else 0
                            if xadv:
                                for r_name in class2_Reverse.get(c2, ()):
                                    raw_pairs[(l_name, r_name)] = int(xadv)
    return raw_pairs


def _get_cached_tt_meta(font_path: Path, font_number: int = 0, need_kern: bool = False) -> dict:
    """
    Load font metadata via `open_ttfont_safe`, store pure Python dicts in `_TT_META_CACHE`,
    and IMMEDIATELY call `tt.close()` so worker processes never leak open file descriptors.
    """
    cache_k = (str(font_path.resolve()), int(font_number))
    entry = _TT_META_CACHE.get(cache_k)
    if entry is not None and (not need_kern or entry.get("raw_kern") is not None):
        return entry

    tt = open_ttfont_safe(font_path, font_number=font_number)
    try:
        cmap = dict(tt.getBestCmap() or {})
        hmtx = dict(tt["hmtx"].metrics)
        upem = int(tt["head"].unitsPerEm)
        has_bc = ("fpgm" in tt) or ("prep" in tt)
        asc = int(tt["hhea"].ascent)
        desc = int(tt["hhea"].descent)
        upos = int(getattr(tt.get("post"), "underlinePosition", -100) if "post" in tt else -100)
        uthk = int(getattr(tt.get("post"), "underlineThickness", 50) if "post" in tt else 50)
        raw_kern = _extract_raw_kerning_dict(tt) if need_kern else (entry.get("raw_kern") if entry else None)
    finally:
        tt.close()

    res = {
        "cmap": cmap,
        "hmtx": hmtx,
        "upem": upem,
        "has_bytecode": has_bc,
        "asc": asc,
        "desc": desc,
        "upos": upos,
        "uthk": uthk,
        "raw_kern": raw_kern,
    }
    _TT_META_CACHE[cache_k] = res
    return res


def extract_kerning_pairs_from_meta(
    meta: dict,
    size_px: int,
    code_to_gid: Dict[int, int],
    code_to_adv_fp4: Dict[int, int],
    prune_noop: bool = True,
) -> List[Tuple[int, int, int, int, int]]:
    """Compute scaled FP4 kerning pairs from cached font metadata without re-opening TTFont."""
    raw_pairs = meta.get("raw_kern") or {}
    if not raw_pairs:
        return []
    upem = meta["upem"]
    cmap = meta["cmap"]
    gname_to_codes: Dict[str, List[int]] = {}
    for code in code_to_gid:
        gname = cmap.get(code)
        if gname:
            gname_to_codes.setdefault(gname, []).append(code)

    pair_map: Dict[Tuple[int, int], Tuple[int, int, int]] = {}
    scale = (size_px * 16.0) / float(upem)
    for (l_name, r_name), fval in raw_pairs.items():
        if l_name not in gname_to_codes or r_name not in gname_to_codes:
            continue
        k_fp4 = int(round(fval * scale))
        if k_fp4 == 0:
            continue
        k_fp4 = max(-127, min(127, k_fp4))
        for l_code in gname_to_codes[l_name]:
            l_adv = code_to_adv_fp4.get(l_code, 0)
            if prune_noop and ((l_adv + k_fp4 + 8) >> 4) == ((l_adv + 8) >> 4):
                continue
            for r_code in gname_to_codes[r_name]:
                l_gid = code_to_gid[l_code]
                r_gid = code_to_gid[r_code]
                pair_map[(l_gid, r_gid)] = (l_code, r_code, k_fp4)

    return [
        (l_gid, r_gid, l_code, r_code, k_fp4)
        for (l_gid, r_gid), (l_code, r_code, k_fp4) in sorted(pair_map.items())
    ]


def resolve_freetype_flags(raster_mode: str, size_px: int) -> int:
    """Resolve FreeType load flags for direct FreeType rasterization modes."""
    rm = normalize_pipeline_name(raster_mode)
    if rm == "exact-mono":
        return FT_LOAD_RENDER | FT_LOAD_NO_HINTING | FT_LOAD_TARGET_MONO | FT_LOAD_MONOCHROME
    if rm == "raw-unhinted":
        return FT_LOAD_RENDER | FT_LOAD_NO_HINTING | FT_LOAD_TARGET_NORMAL
    return FT_LOAD_RENDER | FT_LOAD_FORCE_AUTOHINT | FT_LOAD_TARGET_NORMAL


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
    """Synthesize a crisp 1-BPP LV_SYMBOL_NEW_LINE (U+F8A2, return arrow) glyph at `size_px`."""
    w = max(8, int(round(size_px * 0.75)))
    h = max(8, int(round(size_px * 0.75)))
    stem = 2 if size_px >= 12 else 1
    grid = [["." for _ in range(w)] for _ in range(h)]
    for r in range(0, h - 2):
        for c in range(w - stem, w):
            grid[r][c] = "#"
    bar_r0 = max(2, h - 3 - stem + 1)
    for r in range(bar_r0, bar_r0 + stem):
        for c in range(2, w):
            grid[r][c] = "#"
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
    raster_mode: str = "raw-hinted",
    threshold: int = 128,
    gamma: float = 1.0,
    fa_path: Optional[Path] = None,
    fa_codepoints: Optional[Sequence[int]] = None,
    patch_dict: Optional[Dict[str, dict]] = None,
    ascii_override_dir: Optional[Path] = None,
    enable_kerning: bool = True,
    prune_noop_kern: bool = True,
    font_number: int = 0,
    debug_stages_dir: Optional[Path] = None,
    strike_symbol: str = "",
    family: str = "",
    verbose: bool = False,
) -> Tuple[List[GlyphStrike], int, int, int, int, List[Tuple[int, int, int, int, int]]]:
    """
    Rasterize a 1-bpp font strike using one of the 8 v1.0.19c resolution-reduction conversion pipelines
    (`raw-unhinted`, `raw-hinted`, `svg-potrace`, `mdf`, `msdf`, `sdf-smoothstep`, `adf-biquadratic`,
    `otsu-adaptive`, or `exact-mono`) with linear grayscale conversion and optional gamma factor.
    """
    eff_font_path = _convert_bdf_to_cached_ttf(font_path) if font_path.suffix.lower() == ".bdf" else font_path
    face_ptr = ctypes.POINTER(FT_FaceRec)()
    if ft.FT_New_Face(ft_lib, str(eff_font_path).encode("utf-8"), int(font_number), ctypes.byref(face_ptr)) != 0:
        raise RuntimeError(f"FT_New_Face failed for {eff_font_path}")
    ft.FT_Set_Pixel_Sizes(face_ptr, 0, size_px)

    meta = _get_cached_tt_meta(eff_font_path, font_number=font_number, need_kern=enable_kerning)
    cmap = meta["cmap"]
    hmtx = meta["hmtx"]
    upem = meta["upem"]
    has_bytecode = meta["has_bytecode"]
    os2_asc = meta["asc"]
    os2_desc = meta["desc"]
    post_upos = meta["upos"]
    post_uthk = meta["uthk"]

    ascent_px = int(math.ceil(os2_asc * size_px / float(upem)))
    descent_px = int(math.floor(os2_desc * size_px / float(upem)))
    line_height = ascent_px - descent_px
    base_line = -descent_px

    underline_pos = int(round(post_upos * size_px / float(upem)))
    underline_thick = max(1, int(round(post_uthk * size_px / float(upem))))

    norm_pipe = normalize_pipeline_name(raster_mode)
    eff_thresh = int(np.clip(threshold if threshold > 0 else 128, 1, 254))

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
    debug_emitted_count = 0

    def render_single(f_ptr, f_path: Path, t_cmap, t_hmtx, t_upem, t_has_bc: bool, code: int, p_mode: str, gid: int) -> Optional[GlyphStrike]:
        nonlocal debug_emitted_count
        gname = t_cmap.get(code)
        if not gname or gname not in t_hmtx:
            return None
        gidx = ft.FT_Get_Char_Index(f_ptr, code)
        if gidx == 0:
            return None
        adv_fp4 = int(round(t_hmtx[gname][0] * size_px * 16.0 / float(t_upem)))

        bw_arr, b_left, b_top, _ = render_glyph_via_pipeline(
            ft=ft,
            face_ptr=f_ptr,
            font_path=f_path,
            ft_lib=ft_lib,
            codepoint=code,
            gidx=gidx,
            size_px=size_px,
            pipeline=p_mode,
            threshold=eff_thresh,
            gamma=gamma,
            has_bytecode_hints=t_has_bc,
            capture_debug=False,
        )

        if (
            debug_stages_dir is not None
            and debug_emitted_count < 8
            and (code in COMPLEX_15_CODEPOINTS or code in (0x0041, 0x0048, 0x004D, 0x0057) or debug_emitted_count < 3)
        ):
            sym_lbl = strike_symbol or f"{f_path.stem}_{size_px}"
            save_debug_stage_artifacts(
                debug_dir=debug_stages_dir,
                strike_symbol=sym_lbl,
                codepoint=code,
                glyph_name=get_semantic_glyph_name(code, family),
                ft=ft,
                face_ptr=f_ptr,
                font_path=f_path,
                ft_lib=ft_lib,
                gidx=gidx,
                size_px=size_px,
                threshold=eff_thresh,
                gamma=gamma,
            )
            debug_emitted_count += 1

        raw_h, raw_w = bw_arr.shape if bw_arr.size > 0 else (0, 0)
        raw_rows = ["".join("#" if bw_arr[r, c] else "." for c in range(raw_w)) for r in range(raw_h)]

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
            ofs_x = b_left + c0
            ofs_y = (b_top - raw_h) + (raw_h - 1 - r1)

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

    secondary_faces = []
    fdir = eff_font_path.parent
    fname_low = eff_font_path.name.lower()
    is_mono_font = ("mono" in fname_low) or ("terminus" in fname_low) or ("unifont" in fname_low)
    mono_cell_adv_fp4 = None
    if is_mono_font and 0x0030 in cmap and cmap[0x0030] in hmtx:
        mono_cell_adv_fp4 = int(round(hmtx[cmap[0x0030]][0] * size_px * 16.0 / float(upem)))

    sec_candidates: List[Path] = []
    if fname_low.startswith("fontawesome7-"):
        for s_name in ("FontAwesome7-Brands.ttf", "FontAwesome7-Regular.ttf", "FontAwesome7-Solid.ttf"):
            sp = resolve_font_file_recursive(s_name, [fdir])
            if sp and sp.is_file() and sp.resolve() != eff_font_path.resolve():
                sec_candidates.append(sp)
    elif fname_low.startswith(("ibmplex", "noto", "literata")):
        for s_name in (
            "NotoSans-Medium.ttf",
            "NotoSansMath-Regular.ttf",
            "IBMPlexSans-Medium.ttf",
            "IBMPlexMath-Regular.ttf",
            "IBMPlexSans-Regular.ttf",
            "NotoSans-Regular.ttf",
        ):
            sp = resolve_font_file_recursive(s_name, [fdir])
            if sp and sp.is_file() and sp.resolve() != eff_font_path.resolve():
                sec_candidates.append(sp)

    for sp in sec_candidates:
        s_ptr = ctypes.POINTER(FT_FaceRec)()
        if ft.FT_New_Face(ft_lib, str(sp).encode("utf-8"), 0, ctypes.byref(s_ptr)) == 0:
            ft.FT_Set_Pixel_Sizes(s_ptr, 0, size_px)
            s_meta = _get_cached_tt_meta(sp, font_number=0, need_kern=False)
            secondary_faces.append((s_ptr, sp, s_meta["cmap"], s_meta["hmtx"], s_meta["upem"], s_meta["has_bytecode"]))

    try:
        next_gid = 1
        for code in sorted(set(codepoints)):
            gs = render_single(face_ptr, eff_font_path, cmap, hmtx, upem, has_bytecode, code, norm_pipe, next_gid)
            if gs is None and code in HOMOGLYPH_EQUIVALENTS:
                for alt_cp in HOMOGLYPH_EQUIVALENTS[code]:
                    gs_alt = render_single(face_ptr, eff_font_path, cmap, hmtx, upem, has_bytecode, alt_cp, norm_pipe, next_gid)
                    if gs_alt is not None:
                        gs_alt.codepoint = code
                        gs = gs_alt
                        break
            if gs is None and secondary_faces:
                for s_ptr, s_path, s_cmap, s_hmtx, s_upem, s_bc in secondary_faces:
                    gs_sec = render_single(s_ptr, s_path, s_cmap, s_hmtx, s_upem, s_bc, code, norm_pipe, next_gid)
                    if gs_sec is None and code in HOMOGLYPH_EQUIVALENTS:
                        for alt_cp in HOMOGLYPH_EQUIVALENTS[code]:
                            gs_sec = render_single(s_ptr, s_path, s_cmap, s_hmtx, s_upem, s_bc, alt_cp, norm_pipe, next_gid)
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
            if gs is None and code == 0xF8A2 and fname_low.startswith("fontawesome7-"):
                gs = _synthesize_new_line_glyph(size_px, next_gid)

            if gs is not None:
                glyphs.append(gs)
                code_to_gid[code] = next_gid
                next_gid += 1

        if fa_path and fa_path.is_file() and fa_codepoints:
            fa_face_ptr = ctypes.POINTER(FT_FaceRec)()
            if ft.FT_New_Face(ft_lib, str(fa_path).encode("utf-8"), 0, ctypes.byref(fa_face_ptr)) == 0:
                try:
                    ft.FT_Set_Pixel_Sizes(fa_face_ptr, 0, size_px)
                    fa_meta = _get_cached_tt_meta(fa_path, font_number=0, need_kern=False)
                    for code in sorted(set(fa_codepoints)):
                        if code in code_to_gid:
                            continue
                        gs = render_single(fa_face_ptr, fa_path, fa_meta["cmap"], fa_meta["hmtx"], fa_meta["upem"], False, code, norm_pipe, next_gid)
                        if gs is not None:
                            glyphs.append(gs)
                            code_to_gid[code] = next_gid
                            next_gid += 1
                finally:
                    ft.FT_Done_Face(fa_face_ptr)
    finally:
        for s_ptr, _, _, _, _, _ in secondary_faces:
            ft.FT_Done_Face(s_ptr)
        ft.FT_Done_Face(face_ptr)

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
        extract_kerning_pairs_from_meta(meta, size_px, code_to_gid, code_to_adv, prune_noop=prune_noop_kern)
        if enable_kerning
        else []
    )

    if verbose:
        import sys
        sys.stdout.write(
            f"    [verbose] Rasterized {strike_symbol or eff_font_path.name} @ {size_px}px "
            f"(pipeline={norm_pipe}, threshold={eff_thresh}, gamma={gamma:.2f}): {len(glyphs)} glyphs, {len(kern_pairs)} kern pairs\n"
        )

    return glyphs, line_height, base_line, underline_pos, underline_thick, kern_pairs
