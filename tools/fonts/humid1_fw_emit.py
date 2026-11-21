#!/usr/bin/env python3
"""
humid1_fw_emit.py (v1.0.23)
===========================
A 1-bit EPD font generator and asset pipeline for embedded displays.
Repository : https://github.com/Humidyne-Labs/epd-font
Authors    : Humiditron (https://github.com/humiditron) & AI/LLM Development Partner
License    : MIT License

Portable, Zero-Dependency Firmware Build-Time Font Emitter for ESP-IDF CMake,
H1OS & humid1-os (LVGL >= 9.6.0 Ready).

Overview:
---------
`humid1_fw_emit.py` uses 100% pure Python 3 standard library (`json`, `gzip`,
`pathlib`, `argparse`, `shutil`, `re`, `signal`) and executes in < 0.15 seconds
during ESP-IDF CMake (`idf.py build`).
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import shutil
import signal
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from humid1_runtime import TOOL_VERSION, load_and_validate_hardware_scheme


def _install_sigint() -> None:
    if sys.platform == "darwin":
        sys.stderr.write("[!] Platform Error: unsupported Apple OS is not supported. Use Windows or Linux.\n")
        sys.exit(2)
    def _handler(signum, frame):
        sys.stderr.write("\n[!] Execution stopped cleanly via Ctrl-C.\n")
        sys.exit(130)
    try:
        signal.signal(signal.SIGINT, _handler)
    except Exception:
        pass


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

    orig_sig = meta.get("orig_signature", "")
    rows_sig = "/".join(cropped_rows) if cropped_rows else "."
    if orig_sig and orig_sig.count("|") >= 2:
        cur_sig = f"{adv_w_fp4}|{box_w},{box_h},{ofs_x},{ofs_y}|{rows_sig}"
    else:
        cur_sig = f"{box_w},{box_h},{ofs_x},{ofs_y}|{rows_sig}"
        if orig_sig and orig_sig.endswith("|") and rows_sig == ".":
            cur_sig = f"{box_w},{box_h},{ofs_x},{ofs_y}|"
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


def resolve_validated_fallback(
    fb_pattern: Optional[str],
    cur_sz: int,
    cur_sym: str,
    planned_symbols: Set[str],
) -> Optional[str]:
    """
    Resolve and validate an LVGL >= 9.6.0 fallback font symbol against the planned symbol set.
    Prevents missing extern symbols and self-referential cycles.
    """
    if not fb_pattern:
        return None
    cand = fb_pattern.format(size=cur_sz)
    for norm_cand in (
        cand,
        f"humid1_font_{cand}" if not cand.startswith("humid1_") else cand,
        f"humid1_{cand}" if not cand.startswith("humid1_") else cand,
    ):
        if norm_cand != cur_sym and norm_cand in planned_symbols:
            return norm_cand

    norm_base = cand if cand.startswith("humid1_") else f"humid1_font_{cand}"
    m = re.match(r"^(.+_)(\d+)$", norm_base)
    if m:
        prefix = m.group(1)
        avail = []
        for s_item in planned_symbols:
            if s_item.startswith(prefix) and s_item != cur_sym:
                tail = s_item[len(prefix):]
                if tail.isdigit():
                    avail.append((int(tail), s_item))
        if avail:
            le = [x for x in avail if x[0] <= cur_sz]
            if le:
                return max(le, key=lambda x: x[0])[1]
            return min(avail, key=lambda x: abs(x[0] - cur_sz))[1]
    return None


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
    underline_pos: int = -1,
    underline_thick: int = 1,
) -> int:
    """Emit a self-contained LVGL >= 9.6.0 1-bpp C font file."""
    valid_fb = fallback_symbol if (fallback_symbol and fallback_symbol != symbol_name) else None
    bitmap_bytes: List[int] = []
    glyph_dsc_lines: List[str] = [
        "    {.bitmap_index = 0, .adv_w = 0, .box_w = 0, .box_h = 0, .ofs_x = 0, .ofs_y = 0} /* id = 0 reserved */"
    ]
    bitmap_comment_blocks: List[str] = []
    needs_large_fmt = False

    cp_map = {g.codepoint: g for g in glyphs}
    g_cap = cp_map.get(0x48)
    cap_height = g_cap.box_h if (g_cap and g_cap.box_h > 0) else max(1, int(round(size_px * 0.70)))
    g_xh = cp_map.get(0x78)
    x_height = g_xh.box_h if (g_xh and g_xh.box_h > 0) else max(1, int(round(size_px * 0.52)))

    for g in glyphs[1:]:
        b_idx = len(bitmap_bytes)
        if (
            b_idx >= (1 << 20)
            or g.adv_w_fp4 >= (1 << 12)
            or g.box_w > 255
            or g.box_h > 255
            or g.ofs_x < -128
            or g.ofs_x > 127
            or g.ofs_y < -128
            or g.ofs_y > 127
        ):
            needs_large_fmt = True
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
        ch_disp = ch_disp.replace("/*", "/ *").replace("*/", "* /")
        patch_tag = " [PATCHED]" if g.patched else ""
        if g_bytes:
            hex_str = ", ".join(f"0x{b:02x}" for b in g_bytes)
            bitmap_comment_blocks.append(f"    /* U+{g.codepoint:04X} ({ch_disp}) w={g.box_w} h={g.box_h}{patch_tag} */\n    {hex_str},")
        else:
            bitmap_comment_blocks.append(f"    /* U+{g.codepoint:04X} ({ch_disp}) w={g.box_w} h={g.box_h}{patch_tag} (empty) */")
        glyph_dsc_lines.append(
            f"    {{.bitmap_index = {b_idx}, .adv_w = {g.adv_w_fp4}, .box_w = {g.box_w}, "
            f".box_h = {g.box_h}, .ofs_x = {g.ofs_x}, .ofs_y = {g.ofs_y}}}"
        )

    if len(bitmap_bytes) == 0:
        bitmap_comment_blocks.append("    0x00 /* empty font guard for ISO C */")

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

    sorted_kern = sorted(kern_pairs, key=lambda x: (x[0], x[1]))
    has_kern = len(sorted_kern) > 0
    max_gid = max((g.glyph_id for g in glyphs), default=0)
    gid_size = 0 if max_gid < 255 else 1
    kern_rom_bytes = 0
    kern_block = ""
    if has_kern:
        gid_ctype = "uint8_t" if gid_size == 0 else "uint16_t"
        pair_items = [f"{l}, {r}" for (l, r, _) in sorted_kern]
        val_items = [str(v) for (_, _, v) in sorted_kern]
        pair_lines = [", ".join(pair_items[i : i + 16]) for i in range(0, len(pair_items), 16)]
        val_lines = [", ".join(val_items[i : i + 24]) for i in range(0, len(val_items), 24)]
        kern_rom_bytes = len(sorted_kern) * (2 if gid_size == 0 else 4) + len(sorted_kern) + 16
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
            f"    .pair_cnt = {len(sorted_kern)},\n"
            f"    .glyph_ids_size = {gid_size}\n"
            f"}};\n"
        )

    total_rom = len(bitmap_bytes) + len(glyphs) * 8 + cmap_rom_bytes + kern_rom_bytes + 64
    c_Name = symbol_name.upper()

    large_guard_lines = (
        [
            "#if !defined(LV_FONT_FMT_TXT_LARGE) || !LV_FONT_FMT_TXT_LARGE",
            '#error "This font requires LV_FONT_FMT_TXT_LARGE=1 in lv_conf.h"',
            "#endif",
            "",
        ]
        if needs_large_fmt
        else []
    )
    cmaps_decl_lines = (
        [
            "static const lv_font_fmt_txt_cmap_t cmaps[] = {",
            ",\n".join(cmap_struct_lines),
            "};",
        ]
        if cmap_struct_lines
        else []
    )

    lines = [
        "/*******************************************************************************",
        f" * Size: {size_px} px | Bpp: 1 (Uncompressed Monochrome EPD)",
        f" * Symbol: {symbol_name}",
        f" * Source: {source_desc}",
        f" * LVGL Fallback Pointer: {'&' + valid_fb if valid_fb else 'NULL'} (LVGL >= 9.6.0 Ready)",
        f" * Estimated Flash Footprint: {total_rom:,} bytes ({total_rom / 1024.0:.2f} KB)",
        f" * Generated by: Humidyne Labs / Humiditron humid1_fw_emit.py (v{TOOL_VERSION})",
        " * SPDX-License-Identifier: MIT AND OFL-1.1",
        " ******************************************************************************/",
        "",
        "#ifdef __has_include",
        '    #if __has_include("lvgl.h")',
        "        #ifndef LV_LVGL_H_INCLUDE_SIMPLE",
        "            #define LV_LVGL_H_INCLUDE_SIMPLE",
        "        #endif",
        "    #endif",
        "#endif",
        "",
        "#ifdef LV_LVGL_H_INCLUDE_SIMPLE",
        '    #include "lvgl.h"',
        "#else",
        '    #include "lvgl/lvgl.h"',
        "#endif",
        "",
        f"#ifndef {c_Name}",
        f"#define {c_Name} 1",
        "#endif",
        "",
        f"#if {c_Name}",
        "",
        *large_guard_lines,
        *(
            [
                f"extern const lv_font_t {valid_fb};",
                "",
            ]
            if valid_fb
            else []
        ),
        "/*-----------------",
        " *    BITMAPS",
        " *----------------*/",
        "static LV_ATTRIBUTE_LARGE_CONST const uint8_t glyph_bitmap[] = {",
        "\n".join(bitmap_comment_blocks),
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
        *cmaps_decl_lines,
        "",
        kern_block,
        "/*--------------------",
        " *  ALL CUSTOM DATA",
        " *--------------------*/",
        "static const lv_font_fmt_txt_dsc_t font_dsc = {",
        "    .glyph_bitmap = glyph_bitmap,",
        "    .glyph_dsc = glyph_dsc,",
        f"    .cmaps = {'cmaps' if cmap_struct_lines else 'NULL'},",
        f"    .kern_dsc = {'&kern_pairs' if has_kern else 'NULL'},",
        f"    .kern_scale = {'16' if has_kern else '0'},",
        f"    .cmap_num = {len(subtables)},",
        "    .bpp = 1,",
        "    .kern_classes = 0,",
        "    .bitmap_format = 0,",
        "};",
        "",
        "/*-----------------",
        " *  PUBLIC FONT (LVGL >= 9.6.0)",
        " *----------------*/",
        f"const lv_font_t {symbol_name} = {{",
        "    .get_glyph_dsc = lv_font_get_glyph_dsc_fmt_txt,",
        "    .get_glyph_bitmap = lv_font_get_bitmap_fmt_txt,",
        f"    .line_height = {line_height},",
        f"    .base_line = {base_line},",
        "#if LV_VERSION_CHECK(9, 6, 0) || LVGL_VERSION_MAJOR >= 10",
        f"    .cap_height = {cap_height},",
        f"    .x_height = {x_height},",
        "#endif",
        "    .subpx = LV_FONT_SUBPX_NONE,",
        f"    .underline_position = {underline_pos},",
        f"    .underline_thickness = {underline_thick},",
        "#if LV_VERSION_CHECK(9, 3, 0) || (LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 3) || LVGL_VERSION_MAJOR > 9",
        "    .static_bitmap = 0,",
        "#endif",
        "    .dsc = &font_dsc,",
        "#if LVGL_VERSION_MAJOR >= 9",
        f"    .fallback = {'&' + valid_fb if valid_fb else 'NULL'},",
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
    """Emit drop-in-ready humid1_fonts.h (and optional compat_header / h1os_fonts.h) from scheme config."""
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
            f" * Auto-generated by Humidyne Labs / Humiditron humid1_fw_emit.py v{TOOL_VERSION}",
            f" * SPDX-License-Identifier: {scheme.get('spdx_license', 'MIT AND OFL-1.1')}",
            " */",
            "#pragma once",
            "",
            "#if !defined(LV_CONF_INTERNAL_H)",
            "#ifdef __has_include",
            '    #if __has_include("lvgl.h")',
            "        #ifndef LV_LVGL_H_INCLUDE_SIMPLE",
            "            #define LV_LVGL_H_INCLUDE_SIMPLE",
            "        #endif",
            "    #endif",
            "#endif",
            "#if defined(LV_LVGL_H_INCLUDE_SIMPLE)",
            '    #include "lvgl.h"',
            "#elif defined(__has_include)",
            '    #if __has_include("lvgl/lvgl.h")',
            '        #include "lvgl/lvgl.h"',
            "    #endif",
            "#else",
            '    #include "lvgl/lvgl.h"',
            "#endif",
            "#endif",
            "",
            "#ifdef __cplusplus",
            'extern "C" {',
            "#endif",
            "",
            "struct _lv_font_t;",
            "",
            "#ifdef LV_ATTRIBUTE_EXTERN_DATA",
            "#define EPD_FONT_EXTERN_DECLARE(font_name) LV_ATTRIBUTE_EXTERN_DATA extern const struct _lv_font_t font_name",
            "#else",
            "#define EPD_FONT_EXTERN_DECLARE(font_name) extern const struct _lv_font_t font_name",
            "#endif",
            "",
            "/* ==========================================================================",
            " * 1. Direct LVGL >= 9.6.0 Font Strike Declarations",
            " * ========================================================================== */",
        ]
        for sym in emitted_symbols:
            p_lines.append(f"EPD_FONT_EXTERN_DECLARE({sym});")

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
            resolved_t = pick_sym(semantic_roles[m_name], target) if m_name in semantic_roles else target
            p_lines.append(f"#define {m_name:32s} (&{resolved_t})")
            emitted_m.add(m_name)
        for macro_name, target_sym in semantic_roles.items():
            if macro_name not in emitted_m:
                p_lines.append(f"#define {macro_name:32s} (&{pick_sym(target_sym)})")
                emitted_m.add(macro_name)
        icon_defaults = [
            ("HUMID1_ICON_FA7_DEFAULT",      pick_sym("icon_fa7_solid_16", "icon_fa7_solid_14")),
            ("HUMID1_ICON_LUCIDE_DEFAULT",   pick_sym("icon_lucide_regular_16", "icon_lucide_regular_14")),
            ("HUMID1_ICON_PHOSPHOR_DEFAULT", pick_sym("icon_phosphor_regular_16", "icon_phosphor_regular_14")),
            ("HUMID1_ICON_TABLER_DEFAULT",   pick_sym("icon_tabler_regular_16", "icon_tabler_regular_14")),
        ]
        for m_name, target in icon_defaults:
            if m_name not in emitted_m:
                p_lines.append(f"#define {m_name:32s} (&{target})")
                emitted_m.add(m_name)
        p_lines.extend(["", "#ifdef __cplusplus", "}", "#endif", ""])
        return "\n".join(p_lines)

    primary_h = str(branding.get("primary_header", "humid1_fonts.h") or "humid1_fonts.h")
    compat_h = str(branding.get("compat_header", "") or "").strip()
    keep_headers = {primary_h, "humid1_fonts.h"}
    (out_dir / primary_h).write_text(build_hdr(primary_h), encoding="utf-8")
    if primary_h != "humid1_fonts.h":
        (out_dir / "humid1_fonts.h").write_text(build_hdr("humid1_fonts.h"), encoding="utf-8")
    if compat_h and compat_h not in (primary_h, "humid1_fonts.h", "h1os_fonts.h"):
        keep_headers.add(compat_h)
        shim_txt = (
            "/**\n"
            f" * @file {compat_h}\n"
            f" * @brief Compatibility forwarding header -> {primary_h}\n"
            " */\n"
            "#pragma once\n"
            f'#include "{primary_h}"\n'
        )
        (out_dir / compat_h).write_text(shim_txt, encoding="utf-8")

    if compat_h == "h1os_fonts.h" or "h1os" in str(scheme.get("scheme_id", "")).lower():
        keep_headers.add("h1os_fonts.h")
        def_sym = pick_sym(default_font)
        c_lines = [
            "/**",
            " * @file h1os_fonts.h",
            " * @brief H1OS & humid1-os Integration Font Header",
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
            f"#define LV_FONT_CUSTOM_DECLARE LV_FONT_DECLARE({def_sym})",
            "#endif",
            "",
            "#ifndef LV_FONT_DEFAULT",
            f"#define LV_FONT_DEFAULT (&{def_sym})",
            "#endif",
            "",
            f"#define HUMID1_DEFAULT_FONT (&{def_sym})",
            "",
            "/* H1OS_FONT_<sz> Size/Role Aliases */",
        ]
        sem_roles_h1os = branding.get("semantic_roles", {})

        def _extract_family_prefix(sym_str: str, fallback_prefix: str) -> str:
            m_fam = re.match(r"^(?:humid1_font_)?(.+?)_(?:normal|bold|italic|regular|medium|semibold|extrabold)_\d+$", sym_str.strip())
            return m_fam.group(1) if m_fam else fallback_prefix

        sans_prefix = _extract_family_prefix(str(sem_roles_h1os.get("HUMID1_FONT_UI_BODY", default_font)), "plex_sans")
        mono_prefix = _extract_family_prefix(str(sem_roles_h1os.get("HUMID1_FONT_TELEMETRY_BODY", "")), "plex_mono")

        for sz in range(10, 42, 2):
            pref = f"{sans_prefix}_bold_{sz}" if sz >= 20 else f"{sans_prefix}_normal_{sz}"
            s_norm = pick_sym(pref, f"{sans_prefix}_normal_{sz}")
            s_bold = pick_sym(f"{sans_prefix}_bold_{sz}", s_norm)
            m_norm = pick_sym(f"{mono_prefix}_normal_{sz}", s_norm)
            m_bold = pick_sym(f"{mono_prefix}_bold_{sz}", s_bold)
            c_lines.append(f"#define H1OS_FONT_{sz} (&{s_norm})")
            c_lines.append(f"#define H1OS_FONT_BOLD_{sz} (&{s_bold})")
            c_lines.append(f"#define H1OS_FONT_MONO_{sz} (&{m_norm})")
            c_lines.append(f"#define H1OS_FONT_MONO_BOLD_{sz} (&{m_bold})")

        c_lines.extend(["", "#ifdef __cplusplus", "}", "#endif", ""])
        (out_dir / "h1os_fonts.h").write_text("\n".join(c_lines), encoding="utf-8")

    for old_h in out_dir.glob("*.h"):
        if old_h.name not in keep_headers:
            old_h.unlink()


def load_vault(vault_path: Path) -> dict:
    if vault_path.name.endswith(".gz"):
        with gzip.open(vault_path, "rt", encoding="utf-8") as f:
            return json.load(f)
    return json.loads(vault_path.read_text(encoding="utf-8"))


def build_arg_parser() -> argparse.ArgumentParser:
    epilog_text = """
Examples:
---------
  1. Standard ESP-IDF / H1OS CMake Build-Time Invocation:
     python tools/fonts/humid1_fw_emit.py \\
       --scheme scripts/h1os-build-distro/h1os_full.scheme.json \\
       --vault dist/h1os_distro/humid1_epd_vault.json.gz \\
       --out-dir build/generated_fonts

  2. Emit Using Local ASCII Patch Overrides:
     python tools/fonts/humid1_fw_emit.py \\
       --scheme scripts/h1os-build-distro/h1os_full.scheme.json \\
       --vault dist/h1os_distro/humid1_epd_vault.json.gz \\
       --ascii-dir build/h1os/ascii_patches \\
       --out-dir build/generated_fonts
"""
    parser = argparse.ArgumentParser(
        prog="humid1_fw_emit.py",
        description=(
            f"Humidyne Labs / Humiditron `epd-font` v{TOOL_VERSION} — Portable Zero-Dependency Firmware Font Emitter.\n"
            "A 1-bit EPD font generator and asset pipeline for embedded displays.\n"
            "Reads a declarative JSON scheme and pre-rasterized Strike Vault to emit LVGL >= 9.6.0 1-bpp\n"
            ".c and .h files in < 0.15s using 100% pure Python 3 standard library."
        ),
        epilog=epilog_text,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "-S", "--scheme",
        type=str,
        required=True,
        help="Path to declarative .scheme.json file (required)",
    )
    parser.add_argument(
        "-v", "--vault",
        type=str,
        required=True,
        help="Path to pre-rasterized Strike Vault .json.gz (required)",
    )
    parser.add_argument(
        "-o", "--out-dir",
        type=str,
        required=True,
        help="Target output directory for generated .c, .h, and licenses/ files (required)",
    )
    parser.add_argument(
        "-a", "--ascii-dir",
        dest="ascii_dir",
        type=str,
        default=None,
        help="Optional path to local ascii_patches/ folder to live-override glyphs during build",
    )
    return parser


def main() -> None:
    _install_sigint()
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent if script_dir.name == "fonts" else script_dir.parent
    parser = build_arg_parser()
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.stderr.write("\n[!] Error: Missing required arguments (--scheme, --vault, --out-dir).\n")
        sys.exit(1)
    args = parser.parse_args()

    scheme_path = Path(args.scheme).expanduser().resolve()
    vault_path = Path(args.vault).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()

    if not scheme_path.is_file():
        sys.stderr.write(f"[!] Configuration Error: Scheme file not found: {scheme_path}\n")
        sys.exit(1)
    if not vault_path.is_file():
        sys.stderr.write(f"[!] Configuration Error: Strike Vault not found: {vault_path}\n")
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)
    scheme = json.loads(scheme_path.read_text(encoding="utf-8"))
    vault = load_vault(vault_path)
    vault_strikes: Dict[str, dict] = vault.get("strikes", {})

    icon_registry: dict = {}
    for cand_reg in [
        vault_path.parent / "metadata" / "unified_icon_names.json",
        repo_root / "build" / "metadata" / "unified_icon_names.json",
        script_dir / "metadata" / "unified_icon_names.json",
    ]:
        if cand_reg.is_file():
            try:
                icon_registry = json.loads(cand_reg.read_text(encoding="utf-8"))
                break
            except Exception:
                pass

    char_sets_cfg = scheme.get("character_sets", {})
    ascii_root = Path(args.ascii_dir).expanduser().resolve() if args.ascii_dir else None

    # Pre-compute planned symbols so LVGL >= 9.6.0 fallback pointers are guaranteed valid
    planned_symbols: Set[str] = set()
    for group in scheme.get("strikes", []):
        fam = group["family"]
        style = group.get("style", "normal")
        if "ttf_file" in group and group["ttf_file"]:
            style = Path(group["ttf_file"]).stem.lower().replace("-", "_")
        for sz in group.get("sizes", []):
            sym = (
                f"humid1_font_plex_{fam}_{style}_{sz}"
                if fam in ("sans", "cond", "mono", "serif", "math")
                else (
                    f"humid1_font_terminus_{style}_{sz}"
                    if fam == "terminus"
                    else (
                        f"humid1_{fam}_{style}_{sz}"
                        if fam.startswith("icon_")
                        else f"humid1_font_{fam}_{style}_{sz}"
                    )
                )
            )
            if sym in vault_strikes:
                planned_symbols.add(sym)

    emitted_symbols: List[str] = []
    pair_stats: Dict[Tuple[str, int], Dict[str, int]] = {}
    total_rom = 0

    for group in scheme.get("strikes", []):
        fam = group["family"]
        style = group.get("style", "normal")
        if "ttf_file" in group and group["ttf_file"]:
            style = Path(group["ttf_file"]).stem.lower().replace("-", "_")
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
            sym = (
                f"humid1_font_plex_{fam}_{style}_{sz}"
                if fam in ("sans", "cond", "mono", "serif", "math")
                else (
                    f"humid1_font_terminus_{style}_{sz}"
                    if fam == "terminus"
                    else (
                        f"humid1_{fam}_{style}_{sz}"
                        if fam.startswith("icon_")
                        else f"humid1_font_{fam}_{style}_{sz}"
                    )
                )
            )
            if sym not in vault_strikes:
                continue

            v_strike = vault_strikes[sym]
            line_h = int(v_strike["line_height"])
            base_l = int(v_strike["base_line"])
            upos = int(v_strike.get("underline_position", -1))
            uthk = int(v_strike.get("underline_thickness", 1))
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
            fb_sym = resolve_validated_fallback(fb_pat, sz, sym, planned_symbols)
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
                underline_pos=upos,
                underline_thick=uthk,
            )
            emitted_symbols.append(sym)
            pair_stats.setdefault((fam, sz), {})[style] = rom_b
            total_rom += rom_b
            print(
                f"    [+] Emitted {sym:34s} | {len(filtered_glyphs)-1:3d} glyphs | "
                f"{len(remapped_kern):4d} kern | fb={fb_sym or 'NULL':<32} | ~{rom_b:6,d} B ({rom_b/1024.0:.2f} KB)"
            )

    generate_scheme_headers(out_dir, emitted_symbols, scheme)

    # Validate hardware partition budget strictly from scheme's hardware_scheme (zero assumed defaults)
    hw_search_root = (
        vault_path.parent
        if str(scheme.get("hardware_scheme", "")) and (vault_path.parent / str(scheme.get("hardware_scheme", ""))).is_file()
        else repo_root
    )
    hw_spec = load_and_validate_hardware_scheme(
        scheme_cfg=scheme,
        hw_scheme_cli=None,
        repo_root=hw_search_root,
        scheme_path=scheme_path,
    )
    part_bytes = hw_spec.partition_bytes
    chip_name = hw_spec.chip_name
    part_label = hw_spec.partition_label

    total_c_disk = sum(f.stat().st_size for f in out_dir.glob("*.c")) + sum(f.stat().st_size for f in out_dir.glob("*.h"))
    pct_3mb = (total_rom * 100.0) / float(part_bytes)
    sz_lines = [
        "=" * 108,
        f"HUMIDYNE LABS / HUMIDITRON `epd-font` v{TOOL_VERSION} — FIRMWARE EMITTER FLASH (.rodata) & DISK SIZE REPORT",
        "=" * 108,
        f"  Scheme ID                    : {scheme.get('scheme_id', 'custom')}",
        f"  Hardware Target & Partition  : {chip_name} | partition = {part_label} ({part_bytes:,d} bytes / {part_bytes / 1024.0:,.1f} KB)",
        f"  Total Emitted Strikes        : {len(emitted_symbols)}",
        f"  Expected MCU Flash (.rodata) : {total_rom:12,d} bytes  ({total_rom / 1024.0:8.2f} KB)",
        f"  3 MByte (3,072 KB) Partition : {pct_3mb:8.2f}% utilized ({(part_bytes - total_rom)/1024.0:+,.1f} KB free) [{chip_name}]",
        f"  Host .c + .h Source Disk Size: {total_c_disk:12,d} bytes  ({total_c_disk / 1024.0:8.2f} KB)",
        "-" * 108,
        "  PER-FONT-PAIR (.rodata) BREAKDOWN (NORMAL + BOLD):",
    ]
    for (fam, sz), rmap in sorted(pair_stats.items()):
        nb = rmap.get("normal", rmap.get("regular", 0))
        bb = rmap.get("bold", 0)
        sz_lines.append(
            f"    {fam:<14} {sz:>2d}px : Normal={nb:>7,d} B + Bold={bb:>7,d} B -> Pair Total={(nb+bb):>8,d} B ({(nb+bb)/1024.0:5.2f} KB)"
        )
    sz_lines.append("=" * 108)
    rep_txt = "\n".join(sz_lines) + "\n"
    (out_dir / "total_disk_size.txt").write_text(rep_txt, encoding="utf-8")
    (out_dir / "rom_space_estimate.txt").write_text(rep_txt, encoding="utf-8")

    lic_dir = out_dir / "licenses"
    lic_dir.mkdir(parents=True, exist_ok=True)
    for cand_lic_dir in (
        vault_path.parent / "licenses",
        script_dir / "licenses",
        repo_root / "LICENSES",
        repo_root / "build" / "static_ttfs" / "licenses",
    ):
        if cand_lic_dir.is_dir():
            for lf in sorted(cand_lic_dir.glob("*.txt")):
                shutil.copy2(lf, lic_dir / lf.name)
    if (repo_root / "LICENSE").is_file():
        shutil.copy2(repo_root / "LICENSE", lic_dir / "epd-font_MIT_LICENSE.txt")

    print(
        f"[+] humid1_fw_emit v{TOOL_VERSION} complete: {len(emitted_symbols)} strikes emitted to {out_dir} "
        f"(total ROM = {total_rom:,} B / {total_rom/1024.0:.1f} KB)"
    )


if __name__ == "__main__":
    main()
