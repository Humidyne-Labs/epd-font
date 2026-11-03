#!/usr/bin/env python3
"""
build_static_ttf_assets.py (v0.0.6)
===================================
Humidyne Labs `epd-font` Raw-to-Static TrueType (`.ttf`) Asset & Metadata Builder.

Repository : https://github.com/Humidyne-Labs/epd-font
Target OS  : https://github.com/Humidyne-Labs/H1OS
License    : Apache-2.0

Overview:
---------
Converts all raw upstream font and icon sources inside a single `--src-dir`
(default: `<repo>/assets`, containing `font_assets/` and `icon_assets/`) into a
single standardized `--out-dir` (default: `<repo>/assets/static_ttfs`):

  <out-dir>/
  ├── *.ttf                         # 54 pure, uncompressed TrueType (.ttf) fonts:
  │                                 #   - 41 IBM Plex static cuts (Sans, Cond, Mono, Serif, Math)
  │                                 #   -  3 Font Awesome v7.0.0 cuts (OTF CFF -> quadratic TTF)
  │                                 #   -  1 Lucide v1.67.0 cut
  │                                 #   -  5 Phosphor v2.1.0 cuts (with semantic glyph names baked in)
  │                                 #   -  4 Tabler v3.50.0 cuts
  ├── metadata/                     # Searchable JSON Icon Catalogs & SHA-256 Asset Manifest:
  │   ├── asset_manifest.json       # SHA-256, UPEM, ascent/descent, glyph count for all 54 TTFs
  │   ├── unified_icon_names.json   # Master codepoint <-> semantic name lookup for scheme files
  │   ├── fa7_catalog.json          # Font Awesome v7.0.0 name -> hex codepoint catalog
  │   ├── lucide_catalog.json       # Lucide v1.67.0 name -> hex codepoint catalog (2,061 icons)
  │   ├── phosphor_catalog.json     # Phosphor v2.1.0 name -> hex codepoint catalog (1,512 icons)
  │   └── tabler_catalog.json       # Tabler v3.50.0 name -> hex codepoint catalog (5,203 icons)
  └── licenses/                     # Standardized upstream license files for redistribution

Note on Icon Scope:
-------------------
`build_static_ttf_assets.py` retains 100% of upstream glyphs inside the static `.ttf`
files and indexes all of their semantic names in `<out-dir>/metadata/*_catalog.json`.
You control which subset of icons gets compiled into C arrays via the declarative JSON
scheme files (`tools/fonts/schemes/*.json`), where you can list icons by human-readable
name (`"icons": ["wifi", "battery-full", "thermometer"]`), hex range (`"ranges"`), or `"all"`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

try:
    from fontTools.pens.cu2quPen import Cu2QuPen
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.ttLib import TTFont, newTable
    from fontTools.varLib import instancer
except ImportError as exc:
    print(
        "[!] Error: Missing required Python package 'fonttools'.\n"
        "    Run `scripts\\00_setup_env.bat` or `pip install \"fonttools>=4.40.0\"`.",
        file=sys.stderr,
    )
    raise SystemExit(1) from exc

TOOL_VERSION = "0.0.6"

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


def convert_cff_otf_to_quadratic_ttf(
    src_otf: Path,
    dst_ttf: Path,
    max_err: float = 1.0,
) -> int:
    """
    Convert an OpenType CFF (`.otf`) cubic Bézier font into a native TrueType (`.ttf`)
    quadratic B-spline font (`glyf` + `loca`) while preserving all `cmap` glyph names.
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


def sanitize_and_unwrap_ttf(
    src_font: Path,
    dst_ttf: Path,
    cp_to_semantic_name: Optional[Dict[int, str]] = None,
) -> int:
    """
    Unwrap `.woff` containers (`flavor = None`), rebuild the `post` table (`formatType = 2.0`)
    to strip extra trailing bytes, and optionally embed semantic glyph names (e.g. for Phosphor)
    directly into `glyf`, `hmtx`, `cmap`, and `post` so the resulting `.ttf` is 100% self-describing.
    """
    tt = TTFont(str(src_font))
    tt.flavor = None

    if cp_to_semantic_name:
        for tag in list(tt.keys()):
            if tag != "GlyphOrder":
                _ = tt[tag]
        old_order = list(tt.getGlyphOrder())
        old_cmap = tt.getBestCmap() or {}
        used = {g for g in old_order if not g.startswith("uni")}
        old_to_new: Dict[str, str] = {}
        for cp, old_g in sorted(old_cmap.items()):
            if cp in cp_to_semantic_name and old_g.startswith("uni"):
                primary_name = cp_to_semantic_name[cp].split(",")[0].strip()
                primary_name = re.sub(r"[^A-Za-z0-9_-]+", "-", primary_name).strip("-")
                cand = primary_name if primary_name not in used else f"ph-{primary_name}"
                used.add(cand)
                old_to_new[old_g] = cand
        if old_to_new:
            new_order = [old_to_new.get(g, g) for g in old_order]
            tt.setGlyphOrder(new_order)
            if "glyf" in tt:
                tt["glyf"].glyphs = {old_to_new.get(k, k): v for k, v in tt["glyf"].glyphs.items()}
                tt["glyf"].glyphOrder = new_order
            if "hmtx" in tt:
                tt["hmtx"].metrics = {old_to_new.get(k, k): v for k, v in tt["hmtx"].metrics.items()}
            if "cmap" in tt:
                for table in tt["cmap"].tables:
                    table.cmap = {cp: old_to_new.get(g, g) for cp, g in table.cmap.items()}
            for ot_tag in ("GDEF", "GSUB", "GPOS"):
                if ot_tag in tt:
                    del tt[ot_tag]

    if "post" in tt:
        tt["post"].formatType = 2.0
        tt["post"].extraNames = []
        tt["post"].mapping = {}

    dst_ttf.parent.mkdir(parents=True, exist_ok=True)
    tt.save(str(dst_ttf))
    return dst_ttf.stat().st_size


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
# 3. DUAL-SOURCE METADATA & ICON CATALOG GENERATION (JSONS + FONT CMAP FALLBACK)
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
    codepoints (`>= min_cp`) and their glyph names. Ensures JSON catalogs are 100%
    populated even if upstream `metadata/*.json` files were omitted!
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


def generate_icon_catalogs_and_registry(
    file_index: Dict[str, Path],
    out_static_dir: Path,
    meta_out_dir: Path,
) -> Dict[str, int]:
    """
    Generate complete, searchable JSON icon catalogs (`fa7_catalog.json`,
    `lucide_catalog.json`, `phosphor_catalog.json`, `tabler_catalog.json`, and
    `unified_icon_names.json`) in `meta_out_dir` by combining upstream metadata
    JSONs (when available) with direct `.ttf` `cmap` table extraction.
    """
    meta_out_dir.mkdir(parents=True, exist_ok=True)

    fa7_map: Dict[int, str] = {}
    lucide_map: Dict[int, str] = {}
    phosphor_map: Dict[int, str] = {}
    tabler_map: Dict[int, str] = {}

    # --- Source A: Upstream Metadata JSONs (if present in raw assets) ---
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

    # --- Source B: Direct Font Binary `cmap` Extraction (Always runs & fills any gaps!) ---
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

    # Write individual vendor catalog JSONs (with both `by_name` and `by_codepoint` dicts)
    vendor_maps = [
        ("icon_fa7", "fa7_catalog.json", "Font Awesome v7.0.0", fa7_map),
        ("icon_lucide", "lucide_catalog.json", "Lucide Icons v1.67.0", lucide_map),
        ("icon_phosphor", "phosphor_catalog.json", "Phosphor Icons v2.1.0", phosphor_map),
        ("icon_tabler", "tabler_catalog.json", "Tabler Icons v3.50.0", tabler_map),
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
                f"To include specific icons in your build, copy any icon name from 'by_name' "
                f"into the 'icons': [...] list of a character_set in tools/fonts/schemes/*.json."
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
        # Keep top-level vendor dicts for direct backward-compatible `unified[vendor][hex_cp]` access
        **unified_by_cp,
    }
    (meta_out_dir / "unified_icon_names.json").write_text(
        json.dumps(unified_payload, indent=2) + "\n", encoding="utf-8"
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
            if "math" in p_str:
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
    families_filter: Optional[Sequence[str]] = None,
    cu2qu_max_err: float = 1.0,
    force: bool = False,
    extra_roots: Optional[Sequence[Path]] = None,
) -> List[Path]:
    """
    Scan `src_dir` (and any `extra_roots`) for raw IBM Plex and Icon assets,
    synthesize all 54 static `.ttf` files in `out_dir`, generate all JSON
    catalogs in `out_dir/metadata/`, and copy all licenses to `out_dir/licenses/`.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    meta_out_dir = out_dir / "metadata"
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
                print(f"[*] Extracting archive {r.name} -> temporary workspace...")
                with zipfile.ZipFile(r, "r") as zf:
                    zf.extractall(dest)
                expanded_roots.append(dest)
            else:
                expanded_roots.append(r)
                if r.is_dir():
                    for zf_path in sorted(r.glob("*.zip")):
                        dest = Path(tmp_dir) / f"nested_{zf_path.stem}"
                        with zipfile.ZipFile(zf_path, "r") as zf:
                            zf.extractall(dest)
                        expanded_roots.append(dest)

        file_index = index_source_tree(expanded_roots)
        phos_sel_map = load_phosphor_selection_map(file_index)
        built_files: List[Path] = []

        # Step 1: IBM Plex Variable TTFs -> 41 Static TTFs
        print(f"[*] Step 1/4: Instantiating IBM Plex Static TTFs into {out_dir}...")
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
                sz = sanitize_and_unwrap_ttf(src_path, dst_path, cp_to_semantic_name=phos_sel_map)
                print(f"    [+] Normalized   {target_name:36s} ({sz:9,d} B) [from {src_path.name}]")
            else:
                sz = sanitize_and_unwrap_ttf(src_path, dst_path)
                print(f"    [+] Normalized   {target_name:36s} ({sz:9,d} B) [from {src_path.name}]")
            built_files.append(dst_path)

        # Step 3: Build Searchable Icon Catalogs & Unified Registry in <out_dir>/metadata/
        print(f"[*] Step 3/4: Generating Searchable Icon Catalog JSONs in {meta_out_dir}...")
        counts = generate_icon_catalogs_and_registry(file_index, out_dir, meta_out_dir)
        for v_key, cnt in counts.items():
            print(f"    [+] Catalog {v_key:15s} : {cnt:5,d} semantic icons indexed")

        # Also copy unified_icon_names.json to tools/fonts/icon_metadata if running inside repo
        repo_meta_dir = out_dir.parent.parent / "tools" / "fonts" / "icon_metadata"
        if out_dir.parent.name == "assets":
            repo_meta_dir.mkdir(parents=True, exist_ok=True)
            for jf in meta_out_dir.glob("*.json"):
                shutil.copy2(jf, repo_meta_dir / jf.name)

        # Step 4: Collect Upstream Licenses & Write SHA-256 Asset Manifest
        print(f"[*] Step 4/4: Collecting Licenses & Writing SHA-256 Asset Manifest...")
        saved_lics = collect_upstream_licenses(file_index, out_dir)
        ttf_list = sorted(out_dir.glob("*.ttf"))
        manifest = {
            "manifest_version": TOOL_VERSION,
            "repository": "https://github.com/Humidyne-Labs/epd-font",
            "generator": "build_static_ttf_assets.py",
            "cu2qu_max_err": cu2qu_max_err,
            "total_ttf_files": len(ttf_list),
            "icon_catalog_counts": counts,
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
  1. Default Repository Build (reads <repo>/assets, writes <repo>/assets/static_ttfs):
     python tools/fonts/build_static_ttf_assets.py --verify

  2. Explicit Single Input & Single Output Directory:
     python tools/fonts/build_static_ttf_assets.py --src-dir ./assets --out-dir ./assets/static_ttfs --force --verify

  3. Rebuild Only Modular Icon Fonts (FA7, Lucide, Phosphor, Tabler):
     python tools/fonts/build_static_ttf_assets.py --families icons --force --verify

  4. Audit an Existing static_ttfs/ Directory Without Rebuilding:
     python tools/fonts/build_static_ttf_assets.py --verify-only
"""
    parser = argparse.ArgumentParser(
        prog="build_static_ttf_assets.py",
        description=(
            f"Humidyne Labs `epd-font` v{TOOL_VERSION} — Raw-to-Static TrueType (.ttf) Asset & Metadata Builder.\n"
            "Scans a single `--src-dir` (containing both `font_assets/` and `icon_assets/`) and populates\n"
            "a single `--out-dir` with all 54 standardized `.ttf` binaries, `metadata/*.json` icon catalogs,\n"
            "and `licenses/`."
        ),
        epilog=epilog_text,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "-s", "--src-dir",
        type=str,
        default=None,
        help="Single input root directory (or .zip) containing raw font & icon assets (default: <repo>/assets)",
    )
    parser.add_argument(
        "-o", "--out-dir",
        type=str,
        default=None,
        help="Single output directory for static .ttf files, metadata/, and licenses/ (default: <repo>/assets/static_ttfs)",
    )
    parser.add_argument(
        "-f", "--families",
        type=str,
        nargs="+",
        default=None,
        help="Optional family filter: plex, sans, cond, mono, serif, math, icons, fa7, lucide, phosphor, tabler",
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
    # Hidden legacy aliases for backward compatibility with older scripts
    parser.add_argument("--plex-src", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--icons-src", type=str, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--raw-root", type=str, nargs="+", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--meta-out-dir", type=str, default=None, help=argparse.SUPPRESS)
    return parser


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent if script_dir.name == "fonts" else script_dir.parent
    parser = build_arg_parser()
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve() if args.out_dir else (repo_root / "assets" / "static_ttfs").resolve()
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
            families_filter=args.families,
            cu2qu_max_err=args.cu2qu_max_err,
            force=args.force,
            extra_roots=extra_roots,
        )

    if args.verify or args.verify_only:
        _, failed = verify_static_ttf_directory(out_dir)
        if failed > 0:
            sys.exit(1)


if __name__ == "__main__":
    main()
