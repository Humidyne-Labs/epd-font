#!/usr/bin/env python3
"""
humid1_fw_emit.py (v1.0.10)
========================
Portable, Zero-Dependency Firmware Build-Time Font Emitter for H1OS & humid1-os.

Repository : https://github.com/Humidyne-Labs/epd-font
Target OS  : https://github.com/Humidyne-Labs/H1OS
License    : MIT License

Overview:
---------
`humid1_fw_emit.py` uses **100% pure Python 3 standard library** (`json`, `gzip`,
`pathlib`, `argparse`, `shutil`, `re`) and executes in < 0.15 seconds during
ESP-IDF CMake (`idf.py build`). It requires ZERO `pip` packages, ZERO `libfreetype`,
and ZERO `Node.js / npx lv_font_conv`.

It reads:
  1. A declarative JSON scheme (`--scheme`, default: `schemes/h1os_epd_scheme.json`),
  2. The pre-rasterized Strike Vault (`--vault`, default: `dist/humid1_epd_vault.json.gz`), and
  3. Optional local Full-Canvas ASCII `.txt` glyph overrides (`--ascii-dir`),
and emits tailored LVGL v9 1-bpp `.c` modules, `plex_fonts.h`, `h1os_fonts.h`,
and `licenses/` directly into `--out-dir` (e.g. `${CMAKE_CURRENT_BINARY_DIR}/generated_fonts`).
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

TOOL_VERSION = "1.0.10"


@dataclass
class GlyphRecord:
    codepoint: int
    glyph_id: int
    adv_w_fp4: int
    box_w: int
    box_h: int
    ofs_x: int
    ofs_y: int
    rows: List[str]
    patched: bool = False
    name: str = ""


def parse_unicode_range_spec(spec_str: str) -> List[int]:
    """Parse comma-separated hex/dec ranges ('0x20-0x7E,0xB0,61441') into sorted codepoints."""
    cps: Set[int] = set()
    for part in spec_str.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo_s, hi_s = part.split("-", 1)
            lo = int(lo_s.strip(), 0)
            hi = int(hi_s.strip(), 0)
            for c in range(lo, hi + 1):
                cps.add(c)
        else:
            cps.add(int(part, 0))
    return sorted(cps)


def resolve_charset_allowed_filter(
    cs_entry: dict,
    icon_registry: dict,
    default_vendor: str = "",
) -> Tuple[Set[int], Set[str], bool]:
    """
    Return `(allowed_codepoints, allowed_icon_names_lower, allow_all)` for a `character_sets`
    entry in a scheme JSON. Supports:
      1. `"ranges": "0x0020-0x007E,0x00B0"`
      2. `"icons": ["wifi", "battery-full", "thermometer"]`
      3. `"scope": "all"`
    """
    cps: Set[int] = set()
    names_low: Set[str] = set()
    allow_all = cs_entry.get("scope", "").lower() == "all"

    if "ranges" in cs_entry and cs_entry["ranges"]:
        cps.update(parse_unicode_range_spec(str(cs_entry["ranges"])))

    vendor = cs_entry.get("vendor", default_vendor)
    by_name_map = icon_registry.get("by_name", {}).get(vendor, {})

    if "icons" in cs_entry and isinstance(cs_entry["icons"], list):
        for item in cs_entry["icons"]:
            s = str(item).strip()
            if not s:
                continue
            if s.startswith("0x") or s.isdigit():
                cps.add(int(s, 0))
            else:
                names_low.add(s.lower())
                if s in by_name_map:
                    cps.add(int(by_name_map[s], 0))

    return cps, names_low, allow_all


def parse_ascii_glyph_file(txt_path: Path) -> Optional[Tuple[int, Dict[str, object]]]:
    """
    Parse a Full-Canvas 1:1 Spaced ASCII glyph file (or legacy cropped grid).
    Automatically calculates tight bounding box (`box_w`, `box_h`, `ofs_x`, `ofs_y`)
    when `grid_mode: full_canvas` is active.
    """
    text = txt_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    meta: Dict[str, str] = {}
    grid_lines: List[str] = []
    in_grid = False

    for line in lines:
        s = line.strip()
        if not in_grid:
            if s == "---":
                in_grid = True
                continue
            if not s or s.startswith("#"):
                m_cp = re.search(r"Codepoint\s*:\s*(0x[0-9A-Fa-f]+|U\+[0-9A-Fa-f]+)", s)
                if m_cp:
                    val = m_cp.group(1)
                    if val.upper().startswith("U+"):
                        val = "0x" + val[2:]
                    meta["codepoint"] = val
                m_sig = re.search(r"orig_signature:\s*(.+)$", s)
                if m_sig:
                    meta["orig_signature"] = m_sig.group(1).strip()
                continue
            if ":" in s:
                k, v = s.split(":", 1)
                meta[k.strip().lower()] = v.strip()
        else:
            if not s or line.startswith("#") or s.startswith("# x:") or s.startswith("# ±:"):
                continue
            grid_lines.append(line)

    if "codepoint" not in meta:
        m_fn = re.match(r"U\+([0-9A-Fa-f]{4,6})", txt_path.name)
        if not m_fn:
            return None
        cp = int(m_fn.group(1), 16)
    else:
        cp_s = meta["codepoint"]
        if cp_s.upper().startswith("U+"):
            cp_s = "0x" + cp_s[2:]
        cp = int(cp_s, 0)

    grid_mode = meta.get("grid_mode", "cropped").lower()
    adv_w_fp4 = int(meta["adv_w_fp4"]) if "adv_w_fp4" in meta else int(meta.get("adv_w", "8")) * 16

    parsed_rows: List[str] = []
    row_y_coords: List[int] = []
    canvas_y_top = int(meta.get("canvas_y_top", "0"))
    canvas_x0 = int(meta.get("canvas_x0", "0"))

    for idx, raw_line in enumerate(grid_lines):
        y_coord = canvas_y_top - idx
        if "|" in raw_line:
            left_part, right_part = raw_line.split("|", 1)
            m_y = re.search(r"y=\s*([+-]?\d+)", right_part)
            if m_y:
                y_coord = int(m_y.group(1))
        else:
            left_part = raw_line.split("#  row", 1)[0]

        clean_bits: List[str] = []
        chars = left_part.strip()
        if " " in chars:
            for tok in chars.split():
                if tok.startswith("#") or tok.startswith("█") or tok == "1":
                    clean_bits.append("#")
                elif tok.startswith(".") or tok.startswith("-") or tok.startswith("·") or tok.startswith("─") or tok == "0":
                    clean_bits.append(".")
        else:
            for ch in chars:
                if ch in ("#", "█", "1"):
                    clean_bits.append("#")
                elif ch in (".", "-", "·", "─", "0"):
                    clean_bits.append(".")
        if clean_bits:
            parsed_rows.append("".join(clean_bits))
            row_y_coords.append(y_coord)

    if grid_mode == "full_canvas":
        min_c, max_c = 999999, -1
        min_r, max_r = 999999, -1
        for r_idx, row_str in enumerate(parsed_rows):
            for c_idx, ch in enumerate(row_str):
                if ch == "#":
                    if c_idx < min_c: min_c = c_idx
                    if c_idx > max_c: max_c = c_idx
                    if r_idx < min_r: min_r = r_idx
                    if r_idx > max_r: max_r = r_idx
        if max_c < 0:
            box_w, box_h, ofs_x, ofs_y = 0, 0, 0, 0
            cropped_rows: List[str] = []
        else:
            box_w = (max_c - min_c) + 1
            box_h = (max_r - min_r) + 1
            ofs_x = canvas_x0 + min_c
            ofs_y = row_y_coords[max_r]
            cropped_rows = [parsed_rows[r][min_c : max_c + 1] for r in range(min_r, max_r + 1)]
    else:
        cropped_rows = parsed_rows
        box_h = len(cropped_rows)
        box_w = max((len(r) for r in cropped_rows), default=0)
        ofs_x = int(meta.get("ofs_x", "0"))
        ofs_y = int(meta.get("ofs_y", "0"))

    cur_sig = f"{box_w},{box_h},{ofs_x},{ofs_y}|{'/'.join(cropped_rows)}"
    orig_sig = meta.get("orig_signature", "")
    is_modified = (orig_sig != "" and cur_sig != orig_sig) or meta.get("patched", "0") in ("1", "true", "patched")

    return cp, {
        "adv_w_fp4": adv_w_fp4,
        "box_w": box_w,
        "box_h": box_h,
        "ofs_x": ofs_x,
        "ofs_y": ofs_y,
        "rows": cropped_rows,
        "is_modified": is_modified,
    }


def build_cmaps_partitions(glyphs: Sequence[GlyphRecord]) -> List[dict]:
    """Partition sorted glyphs (excluding gid 0) into LVGL cmap subtables."""
    valid = [g for g in glyphs if g.codepoint > 0]
    if not valid:
        return []
    subtables: List[dict] = []
    idx = 0
    n = len(valid)
    while idx < n:
        run_end = idx
        while run_end + 1 < n and valid[run_end + 1].codepoint == valid[run_end].codepoint + 1:
            run_end += 1
        run_len = run_end - idx + 1
        if run_len >= 4:
            subtables.append({
                "type": "FORMAT0_TINY",
                "range_start": valid[idx].codepoint,
                "range_length": run_len,
                "glyph_id_start": valid[idx].glyph_id,
                "entries": valid[idx : run_end + 1],
            })
            idx = run_end + 1
        else:
            sparse_entries = [valid[idx]]
            idx += 1
            while idx < n:
                r_end = idx
                while r_end + 1 < n and valid[r_end + 1].codepoint == valid[r_end].codepoint + 1:
                    r_end += 1
                if (r_end - idx + 1) >= 4:
                    break
                if valid[idx].codepoint - sparse_entries[0].codepoint > 65530:
                    break
                sparse_entries.append(valid[idx])
                idx += 1
            subtables.append({
                "type": "SPARSE_TINY",
                "range_start": sparse_entries[0].codepoint,
                "range_length": sparse_entries[-1].codepoint - sparse_entries[0].codepoint + 1,
                "glyph_id_start": sparse_entries[0].glyph_id,
                "entries": sparse_entries,
            })
    return subtables


def emit_lvgl_c_file(
    out_path: Path,
    symbol_name: str,
    size_px: int,
    line_height: int,
    base_line: int,
    glyphs: Sequence[GlyphRecord],
    kern_pairs: Sequence[Tuple[int, int, int]],
    source_desc: str,
    fallback_symbol: Optional[str] = None,
) -> int:
    """Emit a self-contained LVGL v8/v9 1-bpp C font file and return estimated ROM bytes."""
    bitmap_bytes: List[int] = []
    glyph_dsc_lines: List[str] = [
        "    {.bitmap_index = 0, .adv_w = 0, .box_w = 0, .box_h = 0, .ofs_x = 0, .ofs_y = 0} /* id = 0 reserved */"
    ]
    bitmap_comment_blocks: List[str] = []

    for g in glyphs[1:]:
        b_idx = len(bitmap_bytes)
        bits: List[int] = []
        for row in g.rows:
            for ch in row:
                bits.append(1 if ch == "#" else 0)
        while len(bits) % 8 != 0:
            bits.append(0)
        g_bytes: List[int] = []
        for i in range(0, len(bits), 8):
            byte_val = 0
            for b in range(8):
                byte_val = (byte_val << 1) | bits[i + b]
            g_bytes.append(byte_val)
        bitmap_bytes.extend(g_bytes)

        ch_disp = g.name if g.name else (chr(g.codepoint) if 0x20 <= g.codepoint <= 0x7E else f"U+{g.codepoint:04X}")
        hex_str = ", ".join(f"0x{b:02x}" for b in g_bytes) if g_bytes else "/* empty */"
        patch_tag = " [PATCHED]" if g.patched else ""
        bitmap_comment_blocks.append(f"    /* U+{g.codepoint:04X} ({ch_disp}) w={g.box_w} h={g.box_h}{patch_tag} */\n    {hex_str},")
        glyph_dsc_lines.append(
            f"    {{.bitmap_index = {b_idx}, .adv_w = {g.adv_w_fp4}, .box_w = {g.box_w}, "
            f".box_h = {g.box_h}, .ofs_x = {g.ofs_x}, .ofs_y = {g.ofs_y}}}"
        )

    subtables = build_cmaps_partitions(glyphs)
    cmap_arrays: List[str] = []
    cmap_struct_lines: List[str] = []
    cmap_rom_bytes = len(subtables) * 24

    for i, st in enumerate(subtables):
        if st["type"] == "FORMAT0_TINY":
            cmap_struct_lines.append(
                f"    {{\n"
                f"        .range_start = {st['range_start']}, .range_length = {st['range_length']}, "
                f".glyph_id_start = {st['glyph_id_start']},\n"
                f"        .unicode_list = NULL, .glyph_id_ofs_list = NULL, .list_length = 0, "
                f".type = LV_FONT_FMT_TXT_CMAP_FORMAT0_TINY\n"
                f"    }}"
            )
        else:
            offsets = ", ".join(str(e.codepoint - st["range_start"]) for e in st["entries"])
            cmap_arrays.append(f"static const uint16_t unicode_list_{i}[] = {{\n    {offsets}\n}};")
            cmap_rom_bytes += len(st["entries"]) * 2
            cmap_struct_lines.append(
                f"    {{\n"
                f"        .range_start = {st['range_start']}, .range_length = {st['range_length']}, "
                f".glyph_id_start = {st['glyph_id_start']},\n"
                f"        .unicode_list = unicode_list_{i}, .glyph_id_ofs_list = NULL, "
                f".list_length = {len(st['entries'])}, .type = LV_FONT_FMT_TXT_CMAP_SPARSE_TINY\n"
                f"    }}"
            )

    has_kern = len(kern_pairs) > 0
    max_gid = max((g.glyph_id for g in glyphs), default=0)
    gid_size = 0 if max_gid < 255 else 1
    kern_rom_bytes = 0
    kern_block = ""
    if has_kern:
        gid_ctype = "uint8_t" if gid_size == 0 else "uint16_t"
        pair_items = [f"{l}, {r}" for (l, r, _) in kern_pairs]
        val_items = [str(v) for (_, _, v) in kern_pairs]
        pair_lines = [", ".join(pair_items[i : i + 16]) for i in range(0, len(pair_items), 16)]
        val_lines = [", ".join(val_items[i : i + 24]) for i in range(0, len(val_items), 24)]
        kern_rom_bytes = len(kern_pairs) * (2 if gid_size == 0 else 4) + len(kern_pairs) + 16
        kern_block = (
            f"/*-----------------*\n *    KERNING\n *-----------------*/\n"
            f"static const {gid_ctype} kern_pair_glyph_ids[] = {{\n    "
            + ",\n    ".join(pair_lines)
            + "\n};\n\n"
            f"static const int8_t kern_pair_values[] = {{\n    "
            + ",\n    ".join(val_lines)
            + "\n};\n\n"
            f"static const lv_font_fmt_txt_kern_pair_t kern_pairs = {{\n"
            f"    .glyph_ids = kern_pair_glyph_ids,\n"
            f"    .values = kern_pair_values,\n"
            f"    .pair_cnt = {len(kern_pairs)},\n"
            f"    .glyph_ids_size = {gid_size}\n"
            f"}};\n"
        )

    total_rom = len(bitmap_bytes) + len(glyphs) * 8 + cmap_rom_bytes + kern_rom_bytes + 64
    c_Name = symbol_name.upper()

    lines = [
        "/*******************************************************************************",
        f" * Size: {size_px} px | Bpp: 1 (Uncompressed Monochrome EPD)",
        f" * Symbol: {symbol_name}",
        f" * Source: {source_desc}",
        f" * Estimated Flash Footprint: {total_rom:,} bytes ({total_rom / 1024.0:.2f} KB)",
        f" * Generated by: Humidyne Labs humid1_fw_emit.py (v{TOOL_VERSION})",
        " * SPDX-License-Identifier: MIT AND OFL-1.1",
        " ******************************************************************************/",
        "",
        '#if defined(LV_LVGL_H_INCLUDE_SIMPLE)',
        '#include "lvgl.h"',
        '#elif defined(__has_include)',
        '#if __has_include("lvgl.h")',
        '#include "lvgl.h"',
        '#elif __has_include("lvgl/lvgl.h")',
        '#include "lvgl/lvgl.h"',
        '#else',
        '#include "lvgl.h"',
        '#endif',
        '#else',
        '#include "lvgl.h"',
        '#endif',
        "",
        f"#ifndef {c_Name}",
        f"#define {c_Name} 1",
        "#endif",
        "",
        f"#if {c_Name}",
        "",
        *( [f"extern const lv_font_t {fallback_symbol};", ""] if fallback_symbol else [] ),
        "/*-----------------",
        " *    BITMAPS",
        " *----------------*/",
        "static LV_ATTRIBUTE_LARGE_CONST const uint8_t glyph_bitmap[] = {",
        "\n".join(bitmap_comment_blocks) if bitmap_comment_blocks else "    0x00",
        "};",
        "",
        "/*---------------------",
        " *  GLYPH DESCRIPTION",
        " *--------------------*/",
        "static const lv_font_fmt_txt_glyph_dsc_t glyph_dsc[] = {",
        ",\n".join(glyph_dsc_lines),
        "};",
        "",
        "/*---------------------",
        " *  CHARACTER MAPPING",
        " *--------------------*/",
        "\n\n".join(cmap_arrays),
        "",
        "static const lv_font_fmt_txt_cmap_t cmaps[] = {",
        ",\n".join(cmap_struct_lines),
        "};",
        "",
        kern_block,
        "/*--------------------",
        " *  ALL CUSTOM DATA",
        " *--------------------*/",
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
        f"    .kern_dsc = {'&kern_pairs' if has_kern else 'NULL'},",
        f"    .kern_scale = {'16' if has_kern else '0'},",
        f"    .cmap_num = {len(subtables)},",
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
        "#if LVGL_VERSION_MAJOR >= 8",
        f"const lv_font_t {symbol_name} = {{",
        "#else",
        f"lv_font_t {symbol_name} = {{",
        "#endif",
        "    .get_glyph_dsc = lv_font_get_glyph_dsc_fmt_txt,",
        "    .get_glyph_bitmap = lv_font_get_bitmap_fmt_txt,",
        f"    .line_height = {line_height},",
        f"    .base_line = {base_line},",
        "#if !(LVGL_VERSION_MAJOR == 6 && LVGL_VERSION_MINOR == 0)",
        "    .subpx = LV_FONT_SUBPX_NONE,",
        "#endif",
        "#if LV_VERSION_CHECK(7, 4, 0) || LVGL_VERSION_MAJOR >= 8",
        "    .underline_position = -1,",
        "    .underline_thickness = 1,",
        "#endif",
        "    .dsc = &font_dsc,",
        "#if LV_VERSION_CHECK(8, 2, 0) || LVGL_VERSION_MAJOR >= 9",
        f"    .fallback = {'&' + fallback_symbol if fallback_symbol else 'NULL'},",
        "#endif",
        "    .user_data = NULL,",
        "};",
        "",
        f"#endif /* #if {c_Name} */",
        "",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return total_rom


def generate_scheme_headers(
    out_dir: Path,
    emitted_symbols: Sequence[str],
    scheme: dict,
) -> None:
    """Emit drop-in-ready humid1_fonts.h, plex_fonts.h, epd_fonts.h, and h1os_fonts.h from scheme config."""
    branding = scheme.get("output_branding", {})
    default_font = branding.get("default_font", branding.get("default_lvgl_font", "humid1_font_plex_sans_normal_14"))
    semantic_roles = branding.get("semantic_roles", {})
    emitted_set = set(emitted_symbols)

    def pick_sym(preferred: str, fallback: str = "humid1_font_plex_sans_normal_14") -> str:
        for cand in (
            preferred,
            f"humid1_font_{preferred}",
            f"humid1_{preferred}",
            fallback,
            f"humid1_font_{fallback}",
            "humid1_font_plex_sans_normal_14",
        ):
            if cand in emitted_set:
                return cand
        return emitted_symbols[0] if emitted_symbols else "humid1_font_plex_sans_normal_14"

    def build_hdr(hdr_name: str) -> str:
        p_lines = [
            "/**",
            f" * @file {hdr_name}",
            f" * @brief {scheme.get('project_brand', 'Humidyne Labs 1-BPP EPD Typography & Iconography Suite')}",
            f" * Auto-generated by Humidyne Labs humid1_fw_emit.py v{TOOL_VERSION}",
            f" * SPDX-License-Identifier: {scheme.get('spdx_license', 'MIT AND OFL-1.1')}",
            " */",
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
            "/* ==========================================================================",
            " * 1. Direct LVGL Font Strike Declarations",
            " * ========================================================================== */",
        ]
        for sym in emitted_symbols:
            p_lines.append(f"LV_FONT_DECLARE({sym});")

        p_lines.extend([
            "",
            "/* ==========================================================================",
            " * 2. Semantic UI, Telemetry & Modular Icon Role Macros",
            " * ========================================================================== */",
        ])
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
        emitted_m = set()
        for suffix, target in role_pairs:
            m_name = f"HUMID1_FONT_{suffix}"
            p_lines.append(f"#define {m_name:32s} (&{target})")
            emitted_m.add(m_name)
        for macro_name, target_sym in semantic_roles.items():
            if macro_name not in emitted_m:
                p_lines.append(f"#define {macro_name:32s} (&{pick_sym(target_sym)})")
                emitted_m.add(macro_name)
        for suffix, target in role_pairs:
            p_lines.append(f"#define PLEX_FONT_{suffix:22s} (&{target})")
        p_lines.extend(["", "#ifdef __cplusplus", "}", "#endif", ""])
        return "\n".join(p_lines)

    for hname in ("humid1_fonts.h", "plex_fonts.h", "epd_fonts.h"):
        (out_dir / hname).write_text(build_hdr(hname), encoding="utf-8")

    def_sym = pick_sym(default_font)
    c_lines = [
        "/**",
        " * @file h1os_fonts.h",
        " * @brief Zero-Code-Change H1OS & humid1-os Drop-In Compatibility Header",
        " */",
        "#pragma once",
        "",
        '#include "humid1_fonts.h"',
        "",
        "#ifdef __cplusplus",
        'extern "C" {',
        "#endif",
        "",
        "#ifndef LV_FONT_CUSTOM_DECLARE",
        f"#define LV_FONT_CUSTOM_DECLARE LV_FONT_DECLARE({def_sym});",
        "#endif",
        "",
        "#ifndef LV_FONT_DEFAULT",
        f"#define LV_FONT_DEFAULT (&{def_sym})",
        "#endif",
        "",
        "/* Backward-Compatible H1OS_FONT_<sz> Aliases */",
    ]
    for sz in (12, 14, 16, 18, 20, 22, 24, 28, 32, 36, 40):
        pref = f"plex_sans_bold_{sz}" if sz >= 20 else f"plex_sans_normal_{sz}"
        s_norm = pick_sym(pref, f"plex_sans_normal_{sz}")
        s_bold = pick_sym(f"plex_sans_bold_{sz}", s_norm)
        m_norm = pick_sym(f"plex_mono_normal_{sz}", s_norm)
        m_bold = pick_sym(f"plex_mono_bold_{sz}", s_bold)
        c_lines.append(f"#define H1OS_FONT_{sz} (&{s_norm})")
        c_lines.append(f"#define H1OS_FONT_BOLD_{sz} (&{s_bold})")
        c_lines.append(f"#define H1OS_FONT_MONO_{sz} (&{m_norm})")
        c_lines.append(f"#define H1OS_FONT_MONO_BOLD_{sz} (&{m_bold})")
        c_lines.append(f"#define h1os_font_montserrat_{sz}_1bpp {s_norm}")

    c_lines.extend(["", "#ifdef __cplusplus", "}", "#endif", ""])
    (out_dir / "h1os_fonts.h").write_text("\n".join(c_lines), encoding="utf-8")


def load_vault(vault_path: Path) -> dict:
    if vault_path.name.endswith(".gz"):
        with gzip.open(vault_path, "rt", encoding="utf-8") as f:
            return json.load(f)
    return json.loads(vault_path.read_text(encoding="utf-8"))


def build_arg_parser() -> argparse.ArgumentParser:
    epilog_text = """
Examples:
---------
  1. Standard H1OS CMake Build-Time Invocation:
     python tools/fonts/humid1_fw_emit.py --out-dir build/generated_fonts --sizes 14 16 18 20 24 32

  2. Emit Using a Custom Scheme & Local ASCII Patch Overrides:
     python tools/fonts/humid1_fw_emit.py --scheme tools/fonts/schemes/h1os_epd_scheme.json \\
       --vault tools/fonts/dist/humid1_epd_vault.json.gz --ascii-dir tools/fonts/ascii_patches \\
       --out-dir build/generated_fonts
"""
    parser = argparse.ArgumentParser(
        prog="humid1_fw_emit.py",
        description=(
            f"Humidyne Labs `epd-font` v{TOOL_VERSION} — Portable Zero-Dependency Firmware Font Emitter.\n"
            "Reads a declarative JSON scheme and pre-rasterized Strike Vault to emit LVGL v9 1-bpp\n"
            ".c and .h files in < 0.15s using 100% pure Python 3 standard library."
        ),
        epilog=epilog_text,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "-S", "--scheme",
        type=str,
        default=None,
        help="Path to declarative JSON font scheme (default: schemes/h1os_epd_scheme.json)",
    )
    parser.add_argument(
        "-v", "--vault",
        type=str,
        default=None,
        help="Path to pre-rasterized Strike Vault (default: dist/humid1_epd_vault.json.gz)",
    )
    parser.add_argument(
        "-o", "--out-dir",
        type=str,
        required=True,
        help="Target output directory for generated .c, .h, and licenses/ files",
    )
    parser.add_argument(
        "-a", "--ascii-dir", "--ascii-patch-dir",
        dest="ascii_dir",
        type=str,
        default=None,
        help="Optional path to local ascii_patches/ folder to live-override glyphs during build",
    )
    parser.add_argument(
        "--sizes",
        type=int,
        nargs="+",
        default=None,
        help="Optional pixel size filter (e.g. --sizes 14 16 18 20 24 32)",
    )
    parser.add_argument(
        "--emit-legacy-c-wrappers",
        action="store_true",
        help="Also emit h1os_font_montserrat_<sz>_1bpp.c wrapper files for legacy CMake targets",
    )
    return parser


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent if script_dir.name == "fonts" else script_dir.parent
    parser = build_arg_parser()
    args = parser.parse_args()

    scheme_path = Path(args.scheme).resolve() if args.scheme else (script_dir / "schemes" / "h1os_epd_scheme.json").resolve()
    if args.vault:
        vault_path = Path(args.vault).resolve()
    else:
        for cand in [
            script_dir / "dist" / "humid1_epd_vault.json.gz",
            repo_root / "dist" / "humid1_epd_vault.json.gz",
            repo_root / "build" / "dist" / "humid1_epd_vault.json.gz",
        ]:
            if cand.is_file():
                vault_path = cand.resolve()
                break
        else:
            vault_path = (script_dir / "dist" / "humid1_epd_vault.json.gz").resolve()

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if not scheme_path.is_file():
        print(f"[!] Scheme file not found: {scheme_path}", file=sys.stderr)
        sys.exit(1)
    if not vault_path.is_file():
        print(f"[!] Strike Vault not found: {vault_path}", file=sys.stderr)
        sys.exit(1)

    scheme = json.loads(scheme_path.read_text(encoding="utf-8"))
    vault = load_vault(vault_path)
    vault_strikes: Dict[str, dict] = vault.get("strikes", {})

    # Optional unified_icon_names.json lookup if present
    icon_registry: dict = {}
    for cand_reg in [
        repo_root / "build" / "metadata" / "unified_icon_names.json",
        script_dir / "metadata" / "unified_icon_names.json",
        script_dir / "icon_metadata" / "unified_icon_names.json",
        repo_root / "assets" / "static_ttfs" / "metadata" / "unified_icon_names.json",
    ]:
        if cand_reg.is_file():
            try:
                icon_registry = json.loads(cand_reg.read_text(encoding="utf-8"))
                break
            except Exception:
                pass

    char_sets_cfg = scheme.get("character_sets", {})
    prefix = scheme.get("output_branding", {}).get("symbol_prefix", "plex_")
    size_filter = set(args.sizes) if args.sizes else None
    ascii_root = Path(args.ascii_dir).resolve() if args.ascii_dir else None

    emitted_symbols: List[str] = []
    total_rom = 0

    for group in scheme.get("strikes", []):
        fam = group["family"]
        style = group["style"]
        csets = group.get("char_sets", [])
        isets = group.get("icon_sets", [])
        use_kern = group.get("kerning", True)
        fb_pat = group.get("fallback", None)

        allowed_cps: Set[int] = {0}
        allowed_names_low: Set[str] = set()
        allow_all = False

        for cs_name in csets + isets:
            if cs_name in char_sets_cfg:
                c_cps, c_names, c_all = resolve_charset_allowed_filter(
                    char_sets_cfg[cs_name], icon_registry, default_vendor=fam
                )
                allowed_cps.update(c_cps)
                allowed_names_low.update(c_names)
                if c_all:
                    allow_all = True

        for sz in group.get("sizes", []):
            if size_filter and sz not in size_filter:
                continue
            sym = (f"humid1_font_plex_{fam}_{style}_{sz}" if fam in ("sans", "cond", "mono", "serif", "math") else (f"humid1_font_terminus_{style}_{sz}" if fam == "terminus" else (f"humid1_{fam}_{style}_{sz}" if fam.startswith("icon_") else f"{prefix}{fam}_{style}_{sz}")))
            if sym not in vault_strikes:
                continue

            v_strike = vault_strikes[sym]
            line_h = int(v_strike["line_height"])
            base_l = int(v_strike["base_line"])
            source_ttf = v_strike.get("source_ttf", f"{fam}-{style}")

            local_overrides: Dict[int, dict] = {}
            if ascii_root and (ascii_root / sym).is_dir():
                for txt_f in sorted((ascii_root / sym).glob("U+*.txt")):
                    res = parse_ascii_glyph_file(txt_f)
                    if res and res[1]["is_modified"]:
                        local_overrides[res[0]] = res[1]

            raw_glyphs = v_strike["glyphs"]
            filtered_glyphs: List[GlyphRecord] = [
                GlyphRecord(0, 0, 0, 0, 0, 0, 0, [], False, "")
            ]
            old_gid_to_new_gid: Dict[int, int] = {}

            for g_dict in raw_glyphs:
                cp = int(g_dict["cp"])
                g_name = str(g_dict.get("name", ""))
                if cp == 0:
                    continue
                if not allow_all and cp not in allowed_cps and g_name.lower() not in allowed_names_low:
                    continue

                new_gid = len(filtered_glyphs)
                old_gid_to_new_gid[int(g_dict["gid"])] = new_gid

                if cp in local_overrides:
                    ov = local_overrides[cp]
                    filtered_glyphs.append(
                        GlyphRecord(
                            codepoint=cp,
                            glyph_id=new_gid,
                            adv_w_fp4=int(ov["adv_w_fp4"]),
                            box_w=int(ov["box_w"]),
                            box_h=int(ov["box_h"]),
                            ofs_x=int(ov["ofs_x"]),
                            ofs_y=int(ov["ofs_y"]),
                            rows=list(ov["rows"]),
                            patched=True,
                            name=g_name,
                        )
                    )
                else:
                    filtered_glyphs.append(
                        GlyphRecord(
                            codepoint=cp,
                            glyph_id=new_gid,
                            adv_w_fp4=int(g_dict["adv_w_fp4"]),
                            box_w=int(g_dict["box_w"]),
                            box_h=int(g_dict["box_h"]),
                            ofs_x=int(g_dict["ofs_x"]),
                            ofs_y=int(g_dict["ofs_y"]),
                            rows=list(g_dict["rows"]),
                            patched=bool(g_dict.get("patched", False)),
                            name=g_name,
                        )
                    )

            remapped_kern: List[Tuple[int, int, int]] = []
            if use_kern:
                for l_gid, r_gid, val in v_strike.get("kern_pairs", []):
                    if l_gid in old_gid_to_new_gid and r_gid in old_gid_to_new_gid:
                        remapped_kern.append((old_gid_to_new_gid[l_gid], old_gid_to_new_gid[r_gid], int(val)))
                remapped_kern.sort(key=lambda x: (x[0], x[1]))

            c_path = out_dir / f"{sym}.c"
            fb_sym = fb_pat.format(size=sz) if fb_pat else None
            rom_b = emit_lvgl_c_file(
                c_path,
                sym,
                sz,
                line_h,
                base_l,
                filtered_glyphs,
                remapped_kern,
                source_ttf,
                fallback_symbol=fb_sym,
            )
            emitted_symbols.append(sym)
            total_rom += rom_b
            print(
                f"    [+] Emitted {sym:26s} | {len(filtered_glyphs)-1:3d} glyphs | "
                f"{len(remapped_kern):4d} kern | ~{rom_b:6,d} B ({rom_b/1024.0:.2f} KB)"
            )

            if args.emit_legacy_c_wrappers and fam == "sans" and style == "normal":
                leg_sym = f"h1os_font_montserrat_{sz}_1bpp"
                leg_path = out_dir / f"{leg_sym}.c"
                emit_lvgl_c_file(
                    leg_path,
                    leg_sym,
                    sz,
                    line_h,
                    base_l,
                    filtered_glyphs,
                    remapped_kern,
                    f"{source_ttf} (H1OS Legacy Alias)",
                    fallback_symbol=fb_sym,
                )

    generate_scheme_headers(out_dir, emitted_symbols, scheme)

    # Emit total_disk_size.txt in out_dir
    total_c_disk = sum(f.stat().st_size for f in out_dir.glob("*.c")) + sum(f.stat().st_size for f in out_dir.glob("*.h"))
    sz_lines = [
        "=" * 96,
        "HUMIDYNE LABS / HUMIDITRON `epd-font` v1.0.10 — FIRMWARE EMITTER FLASH & DISK SIZE REPORT",
        "=" * 96,
        f"  Scheme ID                    : {scheme.get('scheme_id', 'custom')}",
        f"  Total Emitted Strikes        : {len(emitted_symbols)}",
        f"  Expected MCU Flash (.rodata) : {total_rom:12,d} bytes  ({total_rom / 1024.0:8.2f} KB)",
        f"  Host .c + .h Source Disk Size: {total_c_disk:12,d} bytes  ({total_c_disk / 1024.0:8.2f} KB)",
        "=" * 96,
    ]
    (out_dir / "total_disk_size.txt").write_text("\n".join(sz_lines) + "\n", encoding="utf-8")

    lic_dir = out_dir / "licenses"
    lic_dir.mkdir(parents=True, exist_ok=True)
    for cand_lic_dir in (script_dir / "licenses", repo_root / "LICENSES", repo_root / "build" / "static_ttfs" / "licenses"):
        if cand_lic_dir.is_dir():
            for lf in sorted(cand_lic_dir.glob("*.txt")):
                shutil.copy2(lf, lic_dir / lf.name)
    (lic_dir / "README.md").write_text(
        "# H1OS / humid1-os 1-BPP Typography & Iconography Licenses\n\n"
        "- **IBM Plex Typography Suite**: SIL Open Font License 1.1 (`IBMPlex_*_OFL.txt`)\n"
        "- **Font Awesome v7.3.1*: CC BY 4.0 / SIL OFL 1.1 (`FontAwesome7_LICENSE.txt`)\n"
        "- **Lucide Icons v1.67.0**: ISC License (`Lucide_ISC_LICENSE.txt`)\n"
        "- **Phosphor Icons v2.1.0**: MIT License (`Phosphor_MIT_LICENSE.txt`)\n"
        "- **Tabler Icons v3.50.0**: MIT License (`Tabler_MIT_LICENSE.txt`)\n",
        encoding="utf-8",
    )
    print(
        f"[+] plex_fw_emit v{TOOL_VERSION} complete: {len(emitted_symbols)} strikes emitted to {out_dir} "
        f"(total ROM = {total_rom:,} B / {total_rom/1024.0:.1f} KB)"
    )


if __name__ == "__main__":
    main()
