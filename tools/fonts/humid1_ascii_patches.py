#!/usr/bin/env python3
"""
humid1_ascii_patches.py (v1.0.13)
=================================
Humidyne Labs / Humiditron `epd-font` Full-Canvas 1:1 Spaced Editable ASCII Patch
Dumper, Parser & JSON Patch Compiler Module.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from humid1_ft_raster import (
    GlyphStrike,
    TROUBLE_15_CODEPOINTS,
    get_semantic_glyph_name,
    safe_glyph_filename,
)

TOOL_VERSION = "1.0.13"

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
    orig_signatures: Optional[Dict[int, str]] = None,
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
        cur_sig = f"{g.box_w},{g.box_h},{g.ofs_x},{g.ofs_y}|" + ("/".join(matrix_lines) if matrix_lines else ".")
        orig_sig = orig_signatures.get(g.codepoint, cur_sig) if orig_signatures else cur_sig

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
            f"patched: {1 if g.patched else 0}",
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

        if meta.get("patched", "0").strip().lower() in ("1", "true", "yes"):
            was_patched = True
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
            manifest["patches"][sym_name] = parsed
            total_compiled += len(parsed)
        else:
            manifest["patches"].pop(sym_name, None)

    out_json_path.parent.mkdir(parents=True, exist_ok=True)
    out_json_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return total_compiled


