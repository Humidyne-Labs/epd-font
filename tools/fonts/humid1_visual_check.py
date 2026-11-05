#!/usr/bin/env python3
"""
humid1_visual_check.py (v1.0.13)
================================
Humidyne Labs / Humiditron `epd-font` Visual Diagnostic Inspection Sheet,
Single-Character Blueprint & 188 DPI E-Ink Specimen Renderer Module.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

from humid1_ft_raster import (
    GlyphStrike,
    TROUBLE_15_CODEPOINTS,
    get_semantic_glyph_name,
    safe_glyph_filename,
)

TOOL_VERSION = "1.0.13"

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
    patched_cnt = sum(1 for g in valid_glyphs if g.patched)
    draw.text(
        (24, 10),
        f"HUMIDYNE LABS PAGE CHECK  |  {font_symbol_name}  ({family.upper()} {role.upper()} {size_px}px)  |  PATCHED: {patched_cnt}/{n_glyphs}",
        fill=(255, 255, 255),
        font=ui_fonts["title"],
    )
    if patched_cnt > 0:
        badge_txt = f"PATCHED OVERRIDES ACTIVE: {patched_cnt} / {n_glyphs} GLYPHS"
        bx0 = W - 360
        draw.rectangle([bx0, 12, W - 24, 48], fill=(18, 128, 82), outline=(88, 224, 162), width=1)
        draw.text((bx0 + 14, 21), badge_txt, fill=(255, 255, 255), font=ui_fonts["label"])
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
    draw_strike_text(28, 16, "HUMIDYNE LABS / HUMIDITRON  |  1-BPP BILEVEL EPD TYPOGRAPHY SUITE v1.0.13 (188 DPI)", "humid1_font_plex_sans_bold_20", fg=(255, 255, 255))
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
        ("Terminus Normal 12px (6x12 Native Console)", "humid1_font_terminus_normal_12", "boot: humid1-os v1.0.13  |  SPI0 40MHz  |  0x0040 @%#08"),
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


