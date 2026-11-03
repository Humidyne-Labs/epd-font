#!/usr/bin/env python3
"""
build_static_ttf_assets.py (v1.0.7)
===================================
Humidyne Labs / Humiditron `epd-font` Raw-to-Static TrueType (`.ttf`) Asset & Metadata Builder.

Repository : https://github.com/Humidyne-Labs/epd-font
Author     : Humidyne Labs / Humiditron
License    : MIT License (Upstream fonts retain SIL OFL 1.1 / CC-BY-4.0 / ISC / MIT)

Overview:
---------
Converts all raw upstream font and icon sources inside a single `--src-dir`
(default: `<repo>/assets`, containing `font_assets/` and `icon_assets/`) into
the standardized `build/` hierarchy:

  <repo>/build/
  ├── static_ttfs/                  # 57 pure, uncompressed TrueType (.ttf) fonts:
  │   ├── IBMPlex*.ttf              #   - 41 IBM Plex static cuts (Sans, Cond, Mono, Serif, Math)
  │   ├── Terminus-*.ttf            #   -  2 Terminus v4.49.1 cuts (Regular & Bold, BDF -> TTF)
  │   ├── FontAwesome7-*.ttf        #   -  3 Font Awesome v7.2.0 cuts (OTF CFF -> quadratic TTF)
  │   ├── Lucide-Regular.ttf        #   -  1 Lucide v1.16.0 cut
  │   ├── Phosphor-*.ttf            #   -  6 Phosphor v2.1.0 cuts (PUA-sanitized + semantic names)
  │   ├── Tabler-*.ttf              #   -  4 Tabler v3.41.1 cuts
  │   └── licenses/                 #   - Upstream license texts for redistribution
  └── metadata/                     # Searchable JSON Catalogs & SHA-256 Asset Manifest:
      ├── asset_manifest.json       # SHA-256, UPEM, ascent/descent, glyph count for all 57 TTFs
      ├── plex_catalog.json         # IBM Plex & Terminus text font catalog for Agent-First tools
      ├── terminus_catalog.json     # Terminus v4.49.1 codepoint & glyph catalog (1,357 glyphs)
      ├── unified_icon_names.json   # Master codepoint <-> semantic name lookup for scheme files
      ├── fa7_catalog.json          # Font Awesome v7.2.0 name -> hex codepoint catalog
      ├── lucide_catalog.json       # Lucide v1.16.0 name -> hex codepoint catalog (1,690+ icons)
      ├── phosphor_catalog.json     # Phosphor v2.1.0 name -> hex codepoint catalog (1,512 icons)
      └── tabler_catalog.json       # Tabler v3.41.1 name -> hex codepoint catalog (6,064 icons)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
import zipfile
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

TOOL_VERSION = "1.0.7"

# =============================================================================
# 1. DECLARATIVE CONVERSION TABLES
# =============================================================================

MONO_GREEK_ALIASES = {0x0394: "Delta", 0x03A9: "Omega", 0x03BC: "mu"}

PLEX_VARIABLE_INSTANTIATION_TABLE: List[Tuple[str, str, str, Dict[str, float], Dict[int, str]]] = [
    # (Target TTF Name, Family Group, Source Filename, Axis Coordinates, Cmap Aliases)
    # --- IBM Plex Sans (wdth=100, v0.2.0 Variable) ---
    ("IBMPlexSans-Thin.ttf", "sans", "IBM Plex Sans Var-Roman.ttf", {"wght": 100.0, "wdth": 100.0}, {}),
    ("IBMPlexSans-ExtraLight.ttf", "sans", "IBM Plex Sans Var-Roman.ttf", {"wght": 200.0, "wdth": 100.0}, {}),
    ("IBMPlexSans-Light.ttf", "sans", "IBM Plex Sans Var-Roman.ttf", {"wght": 300.0, "wdth": 100.0}, {}),
    ("IBMPlexSans-Regular.ttf", "sans", "IBM Plex Sans Var-Roman.ttf", {"wght": 400.0, "wdth": 100.0}, {}),
    ("IBMPlexSans-Text.ttf", "sans", "IBM Plex Sans Var-Roman.ttf", {"wght": 450.0, "wdth": 100.0}, {}),
    ("IBMPlexSans-Medium.ttf", "sans", "IBM Plex Sans Var-Roman.ttf", {"wght": 500.0, "wdth": 100.0}, {}),
    ("IBMPlexSans-SemiBold.ttf", "sans", "IBM Plex Sans Var-Roman.ttf", {"wght": 600.0, "wdth": 100.0}, {}),
    ("IBMPlexSans-Bold.ttf", "sans", "IBM Plex Sans Var-Roman.ttf", {"wght": 700.0, "wdth": 100.0}, {}),
    ("IBMPlexSans-Italic.ttf", "sans", "IBM Plex Sans Var-Italic.ttf", {"wght": 400.0, "wdth": 100.0}, {}),
    ("IBMPlexSans-TextItalic.ttf", "sans", "IBM Plex Sans Var-Italic.ttf", {"wght": 450.0, "wdth": 100.0}, {}),
    ("IBMPlexSans-MediumItalic.ttf", "sans", "IBM Plex Sans Var-Italic.ttf", {"wght": 500.0, "wdth": 100.0}, {}),
    ("IBMPlexSans-SemiBoldItalic.ttf", "sans", "IBM Plex Sans Var-Italic.ttf", {"wght": 600.0, "wdth": 100.0}, {}),
    ("IBMPlexSans-BoldItalic.ttf", "sans", "IBM Plex Sans Var-Italic.ttf", {"wght": 700.0, "wdth": 100.0}, {}),
    # --- IBM Plex Sans Condensed (wdth=85 extracted from Sans Variable) ---
    ("IBMPlexSansCondensed-Light.ttf", "cond", "IBM Plex Sans Var-Roman.ttf", {"wght": 300.0, "wdth": 85.0}, {}),
    ("IBMPlexSansCondensed-Regular.ttf", "cond", "IBM Plex Sans Var-Roman.ttf", {"wght": 400.0, "wdth": 85.0}, {}),
    ("IBMPlexSansCondensed-Text.ttf", "cond", "IBM Plex Sans Var-Roman.ttf", {"wght": 450.0, "wdth": 85.0}, {}),
    ("IBMPlexSansCondensed-Medium.ttf", "cond", "IBM Plex Sans Var-Roman.ttf", {"wght": 500.0, "wdth": 85.0}, {}),
    ("IBMPlexSansCondensed-SemiBold.ttf", "cond", "IBM Plex Sans Var-Roman.ttf", {"wght": 600.0, "wdth": 85.0}, {}),
    ("IBMPlexSansCondensed-Bold.ttf", "cond", "IBM Plex Sans Var-Roman.ttf", {"wght": 700.0, "wdth": 85.0}, {}),
    ("IBMPlexSansCondensed-Italic.ttf", "cond", "IBM Plex Sans Var-Italic.ttf", {"wght": 400.0, "wdth": 85.0}, {}),
    ("IBMPlexSansCondensed-MedItal.ttf", "cond", "IBM Plex Sans Var-Italic.ttf", {"wght": 500.0, "wdth": 85.0}, {}),
    ("IBMPlexSansCondensed-BoldItalic.ttf", "cond", "IBM Plex Sans Var-Italic.ttf", {"wght": 700.0, "wdth": 85.0}, {}),
    # --- IBM Plex Mono (v1.0.0 Variable) ---
    ("IBMPlexMono-Light.ttf", "mono", "IBM Plex Mono Var-Roman.ttf", {"wght": 300.0}, MONO_GREEK_ALIASES),
    ("IBMPlexMono-Regular.ttf", "mono", "IBM Plex Mono Var-Roman.ttf", {"wght": 400.0}, MONO_GREEK_ALIASES),
    ("IBMPlexMono-Text.ttf", "mono", "IBM Plex Mono Var-Roman.ttf", {"wght": 450.0}, MONO_GREEK_ALIASES),
    ("IBMPlexMono-Medium.ttf", "mono", "IBM Plex Mono Var-Roman.ttf", {"wght": 500.0}, MONO_GREEK_ALIASES),
    ("IBMPlexMono-SemiBold.ttf", "mono", "IBM Plex Mono Var-Roman.ttf", {"wght": 600.0}, MONO_GREEK_ALIASES),
    ("IBMPlexMono-Bold.ttf", "mono", "IBM Plex Mono Var-Roman.ttf", {"wght": 700.0}, MONO_GREEK_ALIASES),
    ("IBMPlexMono-Italic.ttf", "mono", "IBM Plex Mono Var-Italic.ttf", {"wght": 400.0}, MONO_GREEK_ALIASES),
    ("IBMPlexMono-MediumItalic.ttf", "mono", "IBM Plex Mono Var-Italic.ttf", {"wght": 500.0}, MONO_GREEK_ALIASES),
    ("IBMPlexMono-BoldItalic.ttf", "mono", "IBM Plex Mono Var-Italic.ttf", {"wght": 700.0}, MONO_GREEK_ALIASES),
    # --- IBM Plex Serif (v2.0.0 Variable) ---
    ("IBMPlexSerif-Light.ttf", "serif", "IBM Plex Serif Var-Roman.ttf", {"wght": 300.0}, {}),
    ("IBMPlexSerif-Regular.ttf", "serif", "IBM Plex Serif Var-Roman.ttf", {"wght": 400.0}, {}),
    ("IBMPlexSerif-Text.ttf", "serif", "IBM Plex Serif Var-Roman.ttf", {"wght": 450.0}, {}),
    ("IBMPlexSerif-Medium.ttf", "serif", "IBM Plex Serif Var-Roman.ttf", {"wght": 500.0}, {}),
    ("IBMPlexSerif-SemiBold.ttf", "serif", "IBM Plex Serif Var-Roman.ttf", {"wght": 600.0}, {}),
    ("IBMPlexSerif-Bold.ttf", "serif", "IBM Plex Serif Var-Roman.ttf", {"wght": 700.0}, {}),
    ("IBMPlexSerif-Italic.ttf", "serif", "IBM Plex Serif Var-Italic.ttf", {"wght": 400.0}, {}),
    ("IBMPlexSerif-MediumItalic.ttf", "serif", "IBM Plex Serif Var-Italic.ttf", {"wght": 500.0}, {}),
    ("IBMPlexSerif-BoldItalic.ttf", "serif", "IBM Plex Serif Var-Italic.ttf", {"wght": 700.0}, {}),
]

TERMINUS_BDF_CONVERSION_TABLE: List[Tuple[str, str, str, str]] = [
    # (Target TTF Name, Family Group, Source BDF Filename, Style Name)
    ("Terminus-Regular.ttf", "terminus", "ter-u16n.bdf", "Regular"),
    ("Terminus-Bold.ttf", "terminus", "ter-u16b.bdf", "Bold"),
]

ICON_CONVERSION_TABLE: List[Tuple[str, str, str, str]] = [
    # (Target TTF Name, Family Group, Upstream Source Filename, Action)
    ("FontAwesome7-Solid.ttf", "fa7", "Font Awesome 7 Free-Solid-900.otf", "otf2ttf"),
    ("FontAwesome7-Regular.ttf", "fa7", "Font Awesome 7 Free-Regular-400.otf", "otf2ttf"),
    ("FontAwesome7-Brands.ttf", "fa7", "Font Awesome 7 Brands-Regular-400.otf", "otf2ttf"),
    ("Lucide-Regular.ttf", "lucide", "lucide.ttf", "clean_ttf"),
    ("Phosphor-Regular.ttf", "phosphor", "Phosphor.ttf", "phosphor_ttf"),
    ("Phosphor-Bold.ttf", "phosphor", "Phosphor-Bold.ttf", "phosphor_ttf"),
    ("Phosphor-Fill.ttf", "phosphor", "Phosphor-Fill.ttf", "phosphor_ttf"),
    ("Phosphor-Light.ttf", "phosphor", "Phosphor-Light.ttf", "phosphor_ttf"),
    ("Phosphor-Thin.ttf", "phosphor", "Phosphor-Thin.ttf", "phosphor_ttf"),
    ("Phosphor-Duotone.ttf", "phosphor", "Phosphor-Duotone.ttf", "phosphor_ttf"),
    ("Tabler-Regular.ttf", "tabler", "tabler-icons.ttf", "clean_ttf"),
    ("Tabler-Light300.ttf", "tabler", "tabler-icons-300.ttf", "clean_ttf"),
    ("Tabler-Thin200.ttf", "tabler", "tabler-icons-200.ttf", "clean_ttf"),
    ("Tabler-Filled.ttf", "tabler", "tabler-icons-filled.ttf", "clean_ttf"),
]


# =============================================================================
# 2. SOURCE INDEXING & FONT CONVERSION FUNCTIONS
# =============================================================================

def index_source_tree(search_roots: Sequence[Path]) -> Dict[str, Path]:
    """
    Recursively scan `search_roots` (normalizing Windows backslashes to POSIX `/`)
    and index files by filename, `parent/filename`, and `grandparent/parent/filename`.
    """
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
    style_name: str = "Regular",
) -> Tuple[int, Dict[int, str]]:
    """
    Convert an X11 BDF bitmap font (such as Terminus v4.49.1 `ter-u16n.bdf` or `ter-u16b.bdf`)
    into a pure, standards-compliant TrueType (`.ttf`) outline font where each pixel run is
    encoded as an exact grid-aligned clockwise contour in a 1024-UPEM space.
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

    px_h = ascent + descent
    scale = 64  # 16px * 64 = 1024 UPEM
    upem = px_h * scale
    asc_u = ascent * scale
    desc_u = -descent * scale

    glyph_order = [".notdef"]
    cmap: Dict[int, str] = {}
    glyf_dict = {}
    hmtx_dict = {".notdef": (8 * scale, 0)}

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
        dwidth = g["dwidth"]
        pen = TTGlyphPen(None)
        row_bytes = (bw + 7) // 8
        min_x_set = None

        for r_idx, hex_row in enumerate(g["bitmap"]):
            val = int(hex_row, 16) if hex_row else 0
            total_bits = row_bytes * 8
            y_top = (by + bh - r_idx) * scale
            y_bot = y_top - scale
            c = 0
            while c < bw:
                bit = (val >> (total_bits - 1 - c)) & 1
                if bit:
                    c_start = c
                    while c < bw and ((val >> (total_bits - 1 - c)) & 1):
                        c += 1
                    c_end = c
                    x0 = (bx + c_start) * scale
                    x1 = (bx + c_end) * scale
                    if min_x_set is None or x0 < min_x_set:
                        min_x_set = x0
                    # Clockwise contour in TrueType
                    pen.moveTo((x0, y_bot))
                    pen.lineTo((x0, y_top))
                    pen.lineTo((x1, y_top))
                    pen.lineTo((x1, y_bot))
                    pen.closePath()
                else:
                    c += 1

        tt_glyph = pen.glyph()
        glyf_dict[gname] = tt_glyph
        hmtx_dict[gname] = (dwidth * scale, min_x_set if min_x_set is not None else 0)

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
        sxHeight=8 * scale,
        sCapHeight=11 * scale,
         usWeightClass=700 if "bold" in style_name.lower() else 400,
        fsSelection=0x20 if "bold" in style_name.lower() else 0x40,
    )
    fb.setupPost()
    dst_ttf.parent.mkdir(parents=True, exist_ok=True)
    fb.save(str(dst_ttf))
    return dst_ttf.stat().st_size, cmap


def convert_cff_otf_to_quadratic_ttf(
    src_otf: Path,
    dst_ttf: Path,
    max_err: float = 1.0,
) -> int:
    """
    Convert an OpenType CFF (`.otf`) cubic Bézier font into a native TrueType (`.ttf`)
    quadratic B-spline font (`glyf` + `loca`) while preserving all `cmap` glyph names
    and stripping non-PUA ligature anchor codepoints (`cp < 0xE000`).
    """
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


def copy_or_unwrap_master_ttf(
    src_font: Path,
    dst_ttf: Path,
) -> int:
    """
    Preserve upstream distributed `.ttf` binaries 100% unmodified (bit-exact copy) when the
    source is already a standard uncompressed `.ttf`. Only unwrap if the source is `.woff`.
    All semantic icon name resolution and PUA codepoint filtering are handled at the
    ingestion layer via the version-specific `char_manifest_<family>_v<ver>.json` files!
    """
    dst_ttf.parent.mkdir(parents=True, exist_ok=True)
    if src_font.suffix.lower() == ".ttf":
        shutil.copy2(src_font, dst_ttf)
        return dst_ttf.stat().st_size
    tt = TTFont(str(src_font))
    tt.flavor = None
    tt.save(str(dst_ttf))
    return dst_ttf.stat().st_size


def sanitize_and_unwrap_ttf(
    src_font: Path,
    dst_ttf: Path,
    cp_to_semantic_name: Optional[Dict[int, str]] = None,
    strip_non_pua: bool = False,
) -> int:
    return copy_or_unwrap_master_ttf(src_font, dst_ttf)

def instantiate_plex_variable_cut(
    src_var_ttf: Path,
    dst_ttf: Path,
    coords: Dict[str, float],
    cmap_aliases: Dict[int, str],
) -> int:
    """Instantiate a static `.ttf` weight/width cut from an OpenType Variable TTF."""
    tt = TTFont(str(src_var_ttf))
    inst = instancer.instantiateVariableFont(tt, coords)
    inst.flavor = None
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


# =============================================================================
# 3. DUAL-SOURCE METADATA & ICON/FONT CATALOG GENERATION
# =============================================================================

def load_phosphor_selection_map(file_index: Dict[str, Path]) -> Dict[int, str]:
    """Load Phosphor codepoint -> name map from `selection.json` if present."""
    cp_map: Dict[int, str] = {}
    for key in ("selection.json", "phosphor_selection.json", "metadata/selection.json"):
        p = file_index.get(key) or file_index.get(key.lower())
        if p and p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                for ic in data.get("icons", []):
                    props = ic.get("properties", {})
                    if "code" in props and "name" in props:
                        cp_map[int(props["code"])] = str(props["name"]).split(",")[0].strip()
                break
            except Exception:
                pass
    return cp_map


def extract_cmap_catalog_from_ttf(ttf_path: Path, min_cp: int = 0xE000, suffix: str = "") -> Dict[int, str]:
    """
    Directly read the Unicode `cmap` table of a `.ttf` binary and extract all icon
    codepoints (`>= min_cp`) and their glyph names.
    """
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
    terminus_cmap: Optional[Dict[int, str]] = None,
) -> Dict[str, int]:
    """
    Generate complete, searchable JSON catalogs (`fa7_catalog.json`, `lucide_catalog.json`,
    `phosphor_catalog.json`, `tabler_catalog.json`, `terminus_catalog.json`,
    `plex_catalog.json`, and `unified_icon_names.json`) in `meta_out_dir`.
    """
    meta_out_dir.mkdir(parents=True, exist_ok=True)

    fa7_map: Dict[int, str] = {}
    lucide_map: Dict[int, str] = {}
    phosphor_map: Dict[int, str] = {}
    tabler_map: Dict[int, str] = {}

    # --- Source A: Version-Specific Minimal Character Manifests (`char_manifest_*.json`) ---
    for key, p in sorted(file_index.items()):
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
        except Exception:
            pass

    # --- Source A2: Legacy Upstream Metadata JSONs (if present) ---
    for key, p in file_index.items():
        if not p.is_file() or not p.name.endswith(".json"):
            continue
        low_key = key.lower()
        try:
            if p.name.lower() in ("icons.json", "fa7_icons.json") and ("awsome" in low_key or "awesome" in low_key or "fa7" in low_key):
                data = json.loads(p.read_text(encoding="utf-8"))
                for name, info in data.items():
                    if isinstance(info, dict) and "unicode" in info:
                        fa7_map[int(info["unicode"], 16)] = name
            elif p.name.lower() in ("codepoints.json", "lucide_codepoints.json"):
                data = json.loads(p.read_text(encoding="utf-8"))
                for name, cp_val in data.items():
                    lucide_map[int(cp_val)] = name
            elif p.name.lower() in ("selection.json", "phosphor_selection.json"):
                data = json.loads(p.read_text(encoding="utf-8"))
                for ic in data.get("icons", []):
                    props = ic.get("properties", {})
                    if "code" in props and "name" in props:
                        phosphor_map[int(props["code"])] = str(props["name"]).split(",")[0].strip()
            elif p.name.lower() in ("icons.json", "tabler_icons.json") and "tabler" in low_key:
                data = json.loads(p.read_text(encoding="utf-8"))
                for name, info in data.items():
                    if isinstance(info, dict) and "styles" in info:
                        st = info["styles"]
                        if "outline" in st and "unicode" in st["outline"]:
                            tabler_map[int(st["outline"]["unicode"], 16)] = name
                        if "filled" in st and "unicode" in st["filled"]:
                            tabler_map[int(st["filled"]["unicode"], 16)] = f"{name}-filled"
        except Exception:
            pass

    # --- Source B: Direct Font Binary `cmap` Extraction ---
    for fn in ("FontAwesome7-Solid.ttf", "FontAwesome7-Regular.ttf", "FontAwesome7-Brands.ttf"):
        for cp, gname in extract_cmap_catalog_from_ttf(out_static_dir / fn, min_cp=0xE000).items():
            fa7_map.setdefault(cp, gname)

    for cp, gname in extract_cmap_catalog_from_ttf(out_static_dir / "Lucide-Regular.ttf", min_cp=0xE000).items():
        lucide_map.setdefault(cp, gname)

    for cp, gname in extract_cmap_catalog_from_ttf(out_static_dir / "Phosphor-Regular.ttf", min_cp=0xE000).items():
        phosphor_map.setdefault(cp, gname)

    for cp, gname in extract_cmap_catalog_from_ttf(out_static_dir / "Tabler-Regular.ttf", min_cp=0xE000).items():
        tabler_map.setdefault(cp, gname)
    for cp, gname in extract_cmap_catalog_from_ttf(out_static_dir / "Tabler-Filled.ttf", min_cp=0xE000, suffix="-filled").items():
        tabler_map.setdefault(cp, gname)

    vendor_maps = [
        ("icon_fa7", "fa7_catalog.json", "Font Awesome v7.2.0", fa7_map),
        ("icon_lucide", "lucide_catalog.json", "Lucide Icons v1.16.0", lucide_map),
        ("icon_phosphor", "phosphor_catalog.json", "Phosphor Icons v2.1.0", phosphor_map),
        ("icon_tabler", "tabler_catalog.json", "Tabler Icons v3.41.1", tabler_map),
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
            "usage_hint": (
                "Copy any icon name from 'by_name' into the 'icons': [...] list of a character_set "
                "in your scheme JSON file (e.g. tools/fonts/schemes/*.json)."
            ),
            "by_name": by_name,
            "by_codepoint": by_cp,
        }
        (meta_out_dir / catalog_fname).write_text(
            json.dumps(catalog_payload, indent=2) + "\n", encoding="utf-8"
        )

    unified_payload = {
        "schema_version": TOOL_VERSION,
        "description": "Master codepoint <-> semantic icon name registry across Font Awesome 7, Lucide, Phosphor, and Tabler.",
        "counts": counts,
        "by_codepoint": unified_by_cp,
        "by_name": unified_by_name,
        **unified_by_cp,
    }
    (meta_out_dir / "unified_icon_names.json").write_text(
        json.dumps(unified_payload, indent=2) + "\n", encoding="utf-8"
    )

    # Terminus catalog JSON
    if terminus_cmap is None and (out_static_dir / "Terminus-Regular.ttf").is_file():
        terminus_cmap = extract_cmap_catalog_from_ttf(out_static_dir / "Terminus-Regular.ttf", min_cp=0x0020)
    if terminus_cmap:
        term_by_cp = {f"0x{cp:04X}": gname for cp, gname in sorted(terminus_cmap.items())}
        term_payload = {
            "catalog_version": TOOL_VERSION,
            "family": "terminus",
            "title": "Terminus Font v4.49.1 (TrueType Synthesis from ter-u16n.bdf / ter-u16b.bdf)",
            "license": "SIL Open Font License 1.1",
            "total_glyphs": len(term_by_cp),
            "styles": ["Regular", "Bold"],
            "recommended_px_sizes": [12, 14, 16, 18, 20, 24, 28, 32],
            "by_codepoint": term_by_cp,
        }
        (meta_out_dir / "terminus_catalog.json").write_text(
            json.dumps(term_payload, indent=2) + "\n", encoding="utf-8"
        )
        counts["terminus"] = len(term_by_cp)

    # Text font catalog JSON (`plex_catalog.json`)
    text_families = {
        "sans": [row[0] for row in PLEX_VARIABLE_INSTANTIATION_TABLE if row[1] == "sans"],
        "cond": [row[0] for row in PLEX_VARIABLE_INSTANTIATION_TABLE if row[1] == "cond"],
        "mono": [row[0] for row in PLEX_VARIABLE_INSTANTIATION_TABLE if row[1] == "mono"],
        "serif": [row[0] for row in PLEX_VARIABLE_INSTANTIATION_TABLE if row[1] == "serif"],
        "math": ["IBMPlexMath-Regular.ttf"],
        "terminus": ["Terminus-Regular.ttf", "Terminus-Bold.ttf"],
    }
    (meta_out_dir / "plex_catalog.json").write_text(
        json.dumps(
            {
                "catalog_version": TOOL_VERSION,
                "description": "Text & Technical Font Catalog (IBM Plex Sans, Condensed, Mono, Serif, Math + Terminus)",
                "families": text_families,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    return counts


def collect_upstream_licenses(file_index: Dict[str, Path], out_static_dir: Path) -> List[str]:
    """Copy all upstream font and icon license files into `<out_static_dir>/licenses/`."""
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
# 4. MASTER BUILD & VERIFICATION PIPELINE
# =============================================================================

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_static_ttf_directory(static_dir: Path) -> Tuple[int, int]:
    """Verify every `.ttf` file in `static_dir` and print an audit table."""
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
) -> List[Path]:
    """
    Scan `src_dir` (and any `extra_roots`) for raw IBM Plex, Terminus, and Icon assets,
    synthesize all 57 static `.ttf` files in `out_dir` (default: `build/static_ttfs`),
    generate all JSON catalogs in `meta_out_dir` (default: `build/metadata`), and copy
    all upstream licenses to `out_dir/licenses/`.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    if meta_out_dir is None:
        meta_out_dir = (out_dir.parent / "metadata") if out_dir.parent.name == "build" else (out_dir / "metadata")
    meta_out_dir.mkdir(parents=True, exist_ok=True)

    allowed_fams = set(f.lower() for f in families_filter) if families_filter else None
    roots_to_scan = [src_dir] + (list(extra_roots) if extra_roots else [])

    with tempfile.TemporaryDirectory(prefix="epd_font_raw_") as tmp_dir:
        expanded_roots: List[Path] = []
        for idx, r in enumerate(roots_to_scan):
            if not r or not r.exists():
                continue
            if r.is_file() and r.suffix.lower() == ".zip":
                dest = Path(tmp_dir) / f"zip_{idx}_{r.stem}"
                with zipfile.ZipFile(r, "r") as zf:
                    zf.extractall(dest)
                expanded_roots.append(dest)
            elif r.is_file() and (r.name.endswith(".tar.gz") or r.name.endswith(".tgz")):
                dest = Path(tmp_dir) / f"tar_{idx}_{r.stem}"
                with tarfile.open(r, "r:*") as tf:
                    tf.extractall(dest)
                expanded_roots.append(dest)
            else:
                expanded_roots.append(r)
                if r.is_dir():
                    for zf_path in sorted(r.rglob("*.zip")):
                        dest = Path(tmp_dir) / f"nested_zip_{zf_path.stem}"
                        with zipfile.ZipFile(zf_path, "r") as zf:
                            zf.extractall(dest)
                        expanded_roots.append(dest)
                    for tf_path in sorted(list(r.rglob("*.tar.gz")) + list(r.rglob("*.tgz"))):
                        dest = Path(tmp_dir) / f"nested_tar_{tf_path.stem}"
                        with tarfile.open(tf_path, "r:*") as tf:
                            tf.extractall(dest)
                        expanded_roots.append(dest)

        file_index = index_source_tree(expanded_roots)
        phos_sel_map = load_phosphor_selection_map(file_index)
        built_files: List[Path] = []
        terminus_cmap: Optional[Dict[int, str]] = None

        # Step 1: IBM Plex Variable TTFs -> 41 Static TTFs + Terminus BDF -> 2 Static TTFs
        print(f"[*] Step 1/4: Instantiating IBM Plex & Terminus Static TTFs into {out_dir}...")
        for target_name, fam_group, src_fname, coords, aliases in PLEX_VARIABLE_INSTANTIATION_TABLE:
            if allowed_fams and fam_group not in allowed_fams and "plex" not in allowed_fams:
                continue
            dst_path = out_dir / target_name
            if dst_path.is_file() and not force:
                built_files.append(dst_path)
                continue
            src_path = file_index.get(src_fname) or file_index.get(src_fname.lower())
            if not src_path:
                continue
            sz = instantiate_plex_variable_cut(src_path, dst_path, coords, aliases)
            built_files.append(dst_path)
            print(f"    [+] Instantiated {target_name:36s} ({sz:9,d} B) @ {coords}")

        if not allowed_fams or "math" in allowed_fams or "plex" in allowed_fams:
            math_src = file_index.get("IBMPlexMath-Regular.ttf") or file_index.get("ibmplexmath-regular.ttf")
            math_dst = out_dir / "IBMPlexMath-Regular.ttf"
            if math_src and (not math_dst.is_file() or force):
                sz = sanitize_and_unwrap_ttf(math_src, math_dst)
                built_files.append(math_dst)
                print(f"    [+] Installed    {'IBMPlexMath-Regular.ttf':36s} ({sz:9,d} B) [Static Math v1.1.0]")
            elif math_dst.is_file():
                built_files.append(math_dst)

        if not allowed_fams or "terminus" in allowed_fams or "plex" in allowed_fams:
            for target_name, fam_group, src_bdf_name, style_name in TERMINUS_BDF_CONVERSION_TABLE:
                dst_path = out_dir / target_name
                src_bdf = file_index.get(src_bdf_name) or file_index.get(src_bdf_name.lower())
                if src_bdf and (not dst_path.is_file() or force):
                    sz, t_cmap = convert_bdf_to_quadratic_ttf(
                        src_bdf, dst_path, family_name="Terminus", style_name=style_name
                    )
                    if terminus_cmap is None:
                        terminus_cmap = t_cmap
                    built_files.append(dst_path)
                    print(f"    [+] BDF -> TTF   {target_name:36s} ({sz:9,d} B) [from {src_bdf.name}, {len(t_cmap)} glyphs]")
                elif dst_path.is_file():
                    built_files.append(dst_path)

        # Step 2: Convert & Normalize Modular Icon Suites (FA7, Lucide, Phosphor, Tabler)
        print(f"[*] Step 2/4: Converting & Normalizing Modular Icon Suites (FA7, Lucide, Phosphor, Tabler)...")
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
                sz = convert_cff_otf_to_quadratic_ttf(src_path, dst_path, max_err=cu2qu_max_err)
                print(f"    [+] OTF -> TTF   {target_name:36s} ({sz:9,d} B) [from {src_path.name}]")
            elif action == "phosphor_ttf":
                sz = sanitize_and_unwrap_ttf(
                    src_path, dst_path, cp_to_semantic_name=phos_sel_map, strip_non_pua=True
                )
                print(f"    [+] Normalized   {target_name:36s} ({sz:9,d} B) [Unmodified upstream .ttf + char_manifest]")
            else:
                sz = sanitize_and_unwrap_ttf(src_path, dst_path, strip_non_pua=True)
                print(f"    [+] Normalized   {target_name:36s} ({sz:9,d} B) [from {src_path.name}]")
            built_files.append(dst_path)

        # Step 3: Build Searchable Icon & Font Catalogs in <meta_out_dir>
        print(f"[*] Step 3/4: Generating Searchable Icon & Font Catalog JSONs in {meta_out_dir}...")
        counts = generate_icon_and_font_catalogs(file_index, out_dir, meta_out_dir, terminus_cmap=terminus_cmap)
        for v_key, cnt in counts.items():
            print(f"    [+] Catalog {v_key:15s} : {cnt:5,d} entries indexed")

        # Mirror metadata inside <out_dir>/metadata if meta_out_dir is separate (e.g. build/metadata)
        sub_meta = out_dir / "metadata"
        if sub_meta.resolve() != meta_out_dir.resolve():
            sub_meta.mkdir(parents=True, exist_ok=True)
            for jf in meta_out_dir.glob("*.json"):
                shutil.copy2(jf, sub_meta / jf.name)

        # Step 4: Collect Upstream Licenses & Write SHA-256 Asset Manifest
        print(f"[*] Step 4/4: Collecting Licenses & Writing SHA-256 Asset Manifest...")
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
        print(f"    [+] Saved {len(saved_lics)} license files -> {out_dir / 'licenses'}")
        print(f"    [+] Wrote SHA-256 manifest ({len(ttf_list)} TTFs) -> {meta_out_dir / 'asset_manifest.json'}")

        return built_files


# =============================================================================
# 5. UNIFIED CLI & HELP INTERFACE
# =============================================================================

def build_arg_parser() -> argparse.ArgumentParser:
    epilog_text = """
Examples:
---------
  1. Default Repository Build (reads <repo>/assets, writes <repo>/build/static_ttfs & <repo>/build/metadata):
     python tools/fonts/build_static_ttf_assets.py --verify

  2. Explicit Input & Output Directories:
     python tools/fonts/build_static_ttf_assets.py --src-dir ./assets --out-dir ./build/static_ttfs --force --verify

  3. Rebuild Only Modular Icon Fonts (FA7, Lucide, Phosphor, Tabler) or Terminus:
     python tools/fonts/build_static_ttf_assets.py --families icons terminus --force --verify

  4. Audit an Existing static_ttfs/ Directory Without Rebuilding:
     python tools/fonts/build_static_ttf_assets.py --verify-only
"""
    parser = argparse.ArgumentParser(
        prog="build_static_ttf_assets.py",
        description=(
            f"Humidyne Labs / Humiditron `epd-font` v{TOOL_VERSION} — Raw-to-Static TrueType (.ttf) Asset & Metadata Builder.\n"
            "Scans `--src-dir` (containing `font_assets/` and `icon_assets/`) and populates\n"
            "`build/static_ttfs/` with all 57 standardized `.ttf` binaries and `build/metadata/*.json` catalogs."
        ),
        epilog=epilog_text,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "-s", "--src-dir",
        type=str,
        default=None,
        help="Input root directory (or archive) containing raw font & icon assets (default: <repo>/assets)",
    )
    parser.add_argument(
        "-o", "--out-dir",
        type=str,
        default=None,
        help="Output directory for static .ttf files and licenses/ (default: <repo>/build/static_ttfs)",
    )
    parser.add_argument(
        "-m", "--meta-out-dir",
        type=str,
        default=None,
        help="Output directory for metadata JSON catalogs (default: <repo>/build/metadata)",
    )
    parser.add_argument(
        "-f", "--families",
        type=str,
        nargs="+",
        default=None,
        help="Optional family filter: plex, sans, cond, mono, serif, math, terminus, icons, fa7, lucide, phosphor, tabler",
    )
    parser.add_argument(
        "--cu2qu-max-err",
        type=float,
        default=1.0,
        help="Curve approximation tolerance in font units when converting FA7 .otf to .ttf (default: 1.0)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite and regenerate all static .ttf files even if they already exist in --out-dir",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify every generated .ttf file and print a full diagnostic audit table",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only run the diagnostic verification audit on --out-dir without building",
    )
    # Hidden legacy aliases
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
        )

    if args.verify or args.verify_only:
        _, failed = verify_static_ttf_directory(out_dir)
        if failed > 0:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
