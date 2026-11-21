#!/usr/bin/env python3
"""
humid1_visual_check.py (v1.0.23)
================================
Humidyne Labs / Humiditron `epd-font` Visual Diagnostic Inspection Sheet,
Multi-Method Comparison Sheet, Single-Character Blueprint & 188.15 DPI E-Ink Specimen Renderer Module.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

from humid1_bilevel_pipelines import PIPELINE_LABELS
from humid1_ft_raster import (
    GlyphStrike,
    TROUBLE_15_CODEPOINTS,
    get_semantic_glyph_name,
    safe_glyph_filename,
)

TOOL_VERSION = "1.0.23"

_UI_FONTS_CACHE: Dict[str, dict] = {}


def _load_ui_fonts(static_dir: Optional[Path] = None):
    """Load crisp TrueType UI fonts from static_ttfs/ (cached in memory per worker process)."""
    cache_key = str(static_dir) if static_dir else "default"
    if cache_key in _UI_FONTS_CACHE:
        return _UI_FONTS_CACHE[cache_key]
    candidates = []
    if static_dir:
        candidates.append(static_dir)

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
    pipeline: str,
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
                pipeline=pipeline,
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
        pipeline=pipeline,
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
    pipeline: str,
    line_height: int,
    base_line: int,
    glyphs: Sequence[GlyphStrike],
    rom_bytes: int,
    static_dir: Optional[Path] = None,
) -> None:
    """
    Render a crisp, minimal, auto-wrapped Page Check PNG (`inspect_pages/<strike_symbol>.png`):
      1. Specimen strings automatically word-wrap within the safe page width so large fonts
         (24px, 32px, 36px, 40px) never clip off the right edge or collide with the status badge.
      2. Uses crisp TrueType vector typography for all cell headers and metric tags (zero bitmap blur).
      3. Renders each glyph cell at high integer pixel zoom (6x for <=16px, 5x for 18-20px, 4x for 24-32px)
         inside its full vertical frame with color-coded Cap-Height, X-Height, and Baseline guides.
    """
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
    pt_188 = size_px * 72.0 / 188.15
    draw.text(
        (24, 34),
        f"Em: {size_px}px ({pt_96:.1f}pt@96dpi / {pt_188:.1f}pt@188.15dpi)  |  LineHt: {line_height}px (Asc:+{asc_y} Base:-{base_line})  |  Glyphs: {n_glyphs} ({patched_cnt} patched)  |  Pipeline: {pipeline}  |  ROM: {rom_bytes:,} B ({rom_bytes/1024:.2f} KB)",
        fill=(176, 196, 218),
        font=ui_fonts["subtitle"],
    )

    draw.rectangle([24, 72, W - 24, header_h - 14], fill=(255, 255, 255), outline=(202, 210, 222), width=1)
    y_cursor = 84
    draw.text((38, y_cursor + 2), "1:1 Native (188.15 DPI):", fill=(85, 98, 114), font=ui_fonts["label"])

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

        if g.box_w > 0 and g.box_h > 0:
            nx0 = cx1 - g.box_w - 8
            ny0 = cy0 + 7
            for rr, r_str in enumerate(g.rows):
                for cc, px in enumerate(r_str):
                    if px == "#":
                        draw.point((nx0 + cc, ny0 + rr), fill=(12, 16, 22))

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


def render_multi_method_comparison_sheet_png(
    out_png: Path,
    font_symbol_name: str,
    family: str,
    role: str,
    size_px: int,
    threshold: int,
    gamma: float,
    method_strikes: Dict[str, Tuple[Sequence[GlyphStrike], int, int]],
    method_stats: Dict[str, dict],
    static_dir: Optional[Path] = None,
    hi_size_px: int = 38,
    hi_method_strikes: Optional[Dict[str, Tuple[Sequence[GlyphStrike], int, int]]] = None,
    hi_method_stats: Optional[Dict[str, dict]] = None,
) -> Path:
    """
    Render a side-by-side Dual-Detail (`16px` Low-Detail & `38px` High-Detail) Multi-Method Comparison Sheet
    (`inspect_pages/compare_methods/<font_stem>.png`) across all 9 resolution-reduction conversion pipelines:
      - Left Column (`x = 24..950`) : `16px` Low-Detail strike (1:1 & 2x specimen + 4x pixel grid + stem/counter stats)
      - Right Column (`x = 970..1936`): `38px` High-Detail strike (1:1 specimen + 2x pixel grid + stem/counter stats)
    """
    ui_fonts = _load_ui_fonts(static_dir)
    methods = list(method_strikes.keys())
    n_methods = len(methods)
    has_hi = bool(hi_method_strikes)
    row_h = max(158, 74 + (hi_size_px * 2 if has_hi else size_px * 2) + 12)
    W = 1960 if has_hi else 1560
    H = 104 + n_methods * row_h + 28
    img = Image.new("RGB", (W, H), (244, 246, 250))
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, W, 76], fill=(16, 22, 31))
    title_str = (
        f"HUMIDYNE LABS 9-PIPELINE COMPARISON  |  {font_symbol_name} ({family.upper()} {role.upper()})  |  "
        f"LOW-DETAIL ({size_px}px) vs HIGH-DETAIL ({hi_size_px}px)"
        if has_hi
        else f"HUMIDYNE LABS MULTI-METHOD COMPARISON  |  {font_symbol_name} ({family.upper()} {role.upper()} {size_px}px)  |  {n_methods} PIPELINES"
    )
    draw.text((24, 14), title_str, fill=(255, 255, 255), font=ui_fonts["title"])
    draw.text(
        (24, 42),
        f"Side-by-side comparison across all {n_methods} resolution-reduction conversion methods (Threshold={threshold}, Gamma={gamma:.2f})",
        fill=(176, 196, 218),
        font=ui_fonts["subtitle"],
    )

    def _draw_panel(
        x_left: int,
        x_right: int,
        y_top: int,
        sz_val: int,
        detail_tag: str,
        glyphs_seq: Sequence[GlyphStrike],
        lh_val: int,
        bl_val: int,
        st_dict: dict,
    ) -> None:
        gmap = {g.codepoint: g for g in glyphs_seq if g.codepoint > 0}
        is_icon = family.startswith("icon_") or (ord("A") not in gmap)
        if is_icon:
            sample_cps = [g.codepoint for g in glyphs_seq if g.codepoint > 0][:14]
            sample_str = " ".join(chr(c) for c in sample_cps)
            zoom_cps = sample_cps[:6]
        else:
            sample_str = "HUMIDYNE 72.4F 46.8% @%#$&80_easy AaBbGgQqWw"
            zoom_cps = [ord(c) for c in ("@", "%", "8", "0", "a", "e", "g", "W")]

        stat_str = (
            f"[{detail_tag}: {sz_val}px]  Stem: {st_dict.get('mean_stem_px', 0.0):.2f}px  |  "
            f">=2px: {st_dict.get('stem_2px_pct', 0.0):.1f}%  |  "
            f"Counters: {st_dict.get('counter_pct', 100.0):.1f}%  |  Ink: {st_dict.get('ink_px', 0)}px"
        )
        draw.text((x_left, y_top + 32), stat_str, fill=(75, 88, 106), font=ui_fonts["mono_sm"])

        spec_max_x = x_left + int((x_right - x_left) * 0.54)

        def _draw_line(px_x: int, px_y: int, txt: str, sc: int) -> None:
            cx = px_x
            by = px_y + (lh_val - bl_val) * sc
            for ch in txt:
                g = gmap.get(ord(ch))
                if not g:
                    cx += max(4, (sz_val // 3)) * sc
                    continue
                if g.box_w > 0 and g.box_h > 0 and cx + g.box_w * sc < spec_max_x:
                    gx0 = cx + g.ofs_x * sc
                    gy0 = by - (g.ofs_y + g.box_h) * sc
                    for rr, r_s in enumerate(g.rows):
                        for cc, px in enumerate(r_s):
                            if px == "#":
                                if sc == 1:
                                    draw.point((gx0 + cc, gy0 + rr), fill=(12, 16, 22))
                                else:
                                    draw.rectangle(
                                        [gx0 + cc * sc, gy0 + rr * sc, gx0 + (cc + 1) * sc - 1, gy0 + (rr + 1) * sc - 1],
                                        fill=(12, 16, 22),
                                    )
                cx += ((g.adv_w_fp4 + 8) >> 4) * sc

        _draw_line(x_left, y_top + 54, sample_str, 1)
        if sz_val <= 20:
            _draw_line(x_left, y_top + 60 + lh_val, sample_str[:22], 2)

        zx = spec_max_x + 14
        z_scale = 4 if sz_val <= 18 else 2
        for cp in zoom_cps:
            g = gmap.get(cp)
            if not g or g.box_w <= 0 or g.box_h <= 0:
                continue
            if zx + g.box_w * z_scale + 12 > x_right - 8:
                break
            ch_lbl = chr(cp) if 0x20 <= cp <= 0x7E else f"U+{cp:04X}"
            draw.text((zx, y_top + 50), ch_lbl, fill=(65, 78, 94), font=ui_fonts["mono_sm"])
            gy0 = y_top + 66
            for rr, r_s in enumerate(g.rows):
                for cc, px in enumerate(r_s):
                    rx = zx + cc * z_scale
                    ry = gy0 + rr * z_scale
                    if ry + z_scale < y_top + row_h - 10:
                        col = (14, 18, 24) if px == "#" else (232, 236, 242)
                        draw.rectangle([rx, ry, rx + z_scale - 1, ry + z_scale - 1], fill=col)
            zx += max(38, g.box_w * z_scale + 10)

    y = 90
    for idx, m_key in enumerate(methods):
        glyphs_lo, lh_lo, bl_lo = method_strikes[m_key]
        st_lo = method_stats.get(m_key, {})
        bg = (255, 255, 255) if (idx % 2 == 0) else (248, 250, 254)
        draw.rectangle([20, y, W - 20, y + row_h - 8], fill=bg, outline=(206, 214, 224), width=1)

        m_label = PIPELINE_LABELS.get(m_key, m_key)
        draw.text((34, y + 8), m_label, fill=(20, 28, 40), font=ui_fonts["section"])

        if has_hi and hi_method_strikes and m_key in hi_method_strikes:
            mid_x = W // 2
            draw.line([(mid_x, y + 6), (mid_x, y + row_h - 14)], fill=(210, 218, 228), width=1)
            _draw_panel(34, mid_x - 12, y, size_px, "LOW-DETAIL", glyphs_lo, lh_lo, bl_lo, st_lo)
            glyphs_hi, lh_hi, bl_hi = hi_method_strikes[m_key]
            st_hi = (hi_method_stats or {}).get(m_key, {})
            draw.text((mid_x + 16, y + 8), f"{m_label} @ {hi_size_px}px", fill=(20, 28, 40), font=ui_fonts["section"])
            _draw_panel(mid_x + 16, W - 28, y, hi_size_px, "HIGH-DETAIL", glyphs_hi, lh_hi, bl_hi, st_hi)
        else:
            _draw_panel(34, W - 28, y, size_px, "STRIKE", glyphs_lo, lh_lo, bl_lo, st_lo)

        y += row_h

    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out_png))
    return out_png


def render_single_char_inspection_png(
    out_png: Path,
    font_symbol_name: str,
    family: str,
    size_px: int,
    pipeline: str,
    line_height: int,
    base_line: int,
    g: GlyphStrike,
    gmap: Dict[int, GlyphStrike],
    static_dir: Optional[Path] = None,
) -> None:
    """
    Render a dedicated, high-resolution Char-by-Char Technical Design Blueprint PNG
    (`inspect_chars/<strike_symbol>/U+XXXX_<name>.png`).
    """
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

    draw.rectangle([0, 0, W, 62], fill=(16, 22, 31))
    draw.text(
        (24, 10),
        f"CHAR-BY-CHAR DEEP INSPECTOR  |  {font_symbol_name}  |  U+{g.codepoint:04X} ({char_disp!r}) [{gname}]",
        fill=(255, 255, 255),
        font=ui_fonts["title"],
    )
    state_str = "PATCHED (Custom Override)" if g.patched else f"PIPELINE ({pipeline})"
    draw.text(
        (24, 35),
        f"State: {state_str}   |   Strike: {size_px}px (LineHeight: {line_height}px, Base: {base_line}px)   |   Grid Scale: {zoom}x Integer Zoom (Zero Blur)",
        fill=(176, 196, 218),
        font=ui_fonts["subtitle"],
    )

    lx0, ly0 = 20, 76
    lx1, ly1 = left_panel_w, H - 20
    draw.rectangle([lx0, ly0, lx1, ly1], fill=(255, 255, 255), outline=(202, 210, 222), width=1)

    gx0 = lx0 + 62
    gy0 = ly0 + 44

    for c_i in range(total_cols):
        x_val = x_left + c_i
        cx = gx0 + c_i * zoom
        col_txt = f"{x_val}"
        col_color = (200, 30, 45) if x_val == 0 else ((25, 95, 200) if x_val == adv_px else (110, 120, 135))
        draw.text((cx + max(1, zoom // 2 - 4), gy0 - 20), col_txt, fill=col_color, font=ui_fonts["mono_sm"])

    for r_i in range(total_rows):
        y_val = y_top - r_i
        ry = gy0 + r_i * zoom

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
                    mcx, mcy = rx + zoom // 2, ry + zoom // 2
                    draw.point((mcx, mcy), fill=(90, 105, 125))
            else:
                cell_bg = (252, 246, 246) if y_val == 0 else ((246, 250, 255) if (0 <= x_val < adv_px and 0 <= y_val <= cap_y) else (255, 255, 255))
                if in_bbox:
                    cell_bg = (242, 252, 246)
                draw.rectangle([rx, ry, rx + zoom - 1, ry + zoom - 1], fill=cell_bg, outline=(226, 232, 240))

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

    if x_left <= 0 <= x_right:
        ox_px = gx0 + (0 - x_left) * zoom
        draw.line([(ox_px, gy0 - 4), (ox_px, gy0 + grid_h + 4)], fill=(210, 35, 45), width=2)
    if x_left <= adv_px <= x_right:
        ax_px = gx0 + (adv_px - x_left) * zoom
        draw.line([(ax_px, gy0 - 4), (ax_px, gy0 + grid_h + 4)], fill=(25, 95, 210), width=2)
        draw.text((ax_px - 18, gy0 + grid_h + 6), f"adv={adv_px}px", fill=(25, 95, 210), font=ui_fonts["mono_sm"])

    if g.box_w > 0 and g.box_h > 0:
        bx0 = gx0 + (g.ofs_x - x_left) * zoom
        by0 = gy0 + (y_top - glyph_y_top) * zoom
        bx1 = bx0 + g.box_w * zoom - 1
        by1 = by0 + g.box_h * zoom - 1
        draw.rectangle([bx0, by0, bx1, by1], outline=(16, 160, 95), width=2)

    rx0 = left_panel_w + 16
    rx1 = W - 20

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

    draw.text((rx0 + 16, p1_y0 + 38), "1:1 (188.15 DPI)", fill=(95, 108, 124), font=ui_fonts["mono_sm"])
    draw_single_glyph_at(rx0 + 36, p1_y0 + 62, g, 1, fg=(14, 18, 24))

    draw.text((rx0 + 130, p1_y0 + 38), "2x Scale", fill=(95, 108, 124), font=ui_fonts["mono_sm"])
    draw_single_glyph_at(rx0 + 142, p1_y0 + 58, g, 2, fg=(14, 18, 24))

    inv_x0 = rx0 + 245
    draw.rectangle([inv_x0, p1_y0 + 34, rx1 - 14, p1_y1 - 14], fill=(14, 18, 24))
    draw.text((inv_x0 + 10, p1_y0 + 40), "Inverted 1:1 & 2x", fill=(180, 195, 215), font=ui_fonts["mono_sm"])
    draw_single_glyph_at(inv_x0 + 24, p1_y0 + 66, g, 1, fg=(255, 255, 255))
    draw_single_glyph_at(inv_x0 + 84, p1_y0 + 62, g, 2, fg=(255, 255, 255))

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
    pipeline: str,
    line_height: int,
    base_line: int,
    glyphs: Sequence[GlyphStrike],
    char_filter: str = "trouble",
    static_dir: Optional[Path] = None,
) -> int:
    """Render Char-by-Char Deep Inspection PNG cards into `strike_char_dir/U+XXXX_<name>.png`."""
    if char_filter == "none":
        return 0
    gmap = {g.codepoint: g for g in glyphs if g.codepoint > 0}
    diagnostic_set = set(TROUBLE_15_CODEPOINTS) | {
        ord("_"), ord("."), ord("-"), ord(":"), ord(";"), ord("/"), ord("("), ord(")"),
        ord("0"), ord("1"), ord("8"), ord("A"), ord("H"), ord("M"), ord("U"), ord("p"),
    }
    count = 0
    is_icon_fam = family.startswith("icon_")
    valid_list = [g for g in glyphs if g.codepoint > 0]
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
            size_px=size_px,
            pipeline=pipeline,
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
    static_dir: Optional[Path] = None,
    scheme_cfg: Optional[dict] = None,
) -> None:
    """Render master 188.15-DPI 1-bpp specimen contact sheet & simulated 200x200 SSD1681 panel."""
    ui_fonts = _load_ui_fonts(static_dir)
    W, H = 1420, 1020
    img = Image.new("RGB", (W, H), (246, 247, 249))
    draw = ImageDraw.Draw(img)

    branding = (scheme_cfg or {}).get("output_branding", {})
    sem_roles = branding.get("semantic_roles", {})
    default_font_cfg = str(branding.get("default_font", "")).strip()

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
            default_font_cfg,
            "humid1_font_plex_sans_normal_14",
            "humid1_font_plex_sans_normal_12",
            "humid1_font_terminus_bold_16",
            "humid1_font_terminus_normal_16",
        ]
        for c in cands:
            if c and c in strike_cache:
                return c
        return next(iter(strike_cache.keys()), None)

    def _role_sym(macro_name: str, fallback: str) -> str:
        raw = sem_roles.get(macro_name, fallback)
        return _resolve_sym(str(raw)) or _resolve_sym(fallback) or fallback

    sym_ui_micro = _role_sym("HUMID1_FONT_UI_MICRO", "humid1_font_terminus_normal_12")
    sym_ui_body = _role_sym("HUMID1_FONT_UI_BODY", default_font_cfg or "humid1_font_plex_sans_normal_14")
    sym_ui_body_md = _role_sym("HUMID1_FONT_UI_BODY_MD", "humid1_font_plex_sans_normal_16")
    sym_ui_sub = _role_sym("HUMID1_FONT_UI_SUBTITLE", "humid1_font_plex_sans_bold_14")
    sym_ui_title = _role_sym("HUMID1_FONT_UI_TITLE", "humid1_font_plex_sans_bold_16")
    sym_ui_header = _role_sym("HUMID1_FONT_UI_HEADER", "humid1_font_plex_sans_bold_20")
    sym_ui_italic = _role_sym("HUMID1_FONT_UI_META_ITALIC", "humid1_font_plex_sans_italic_14")
    sym_tele_sm = _role_sym("HUMID1_FONT_TELEMETRY_SM", "humid1_font_plex_mono_normal_14")
    sym_tele_body = _role_sym("HUMID1_FONT_TELEMETRY_BODY", "humid1_font_plex_mono_normal_16")
    sym_tele_md = _role_sym("HUMID1_FONT_TELEMETRY_MD", "humid1_font_plex_mono_bold_20")
    sym_tele_lg = _role_sym("HUMID1_FONT_TELEMETRY_LG", "humid1_font_plex_mono_bold_24")
    sym_tele_xl = _role_sym("HUMID1_FONT_TELEMETRY_XL", "humid1_font_plex_mono_bold_32")
    sym_cond_norm = _role_sym("HUMID1_FONT_RIBBON_COND", "humid1_font_plex_cond_normal_16")
    sym_cond_bold = _role_sym("HUMID1_FONT_BANNER_COND", "humid1_font_plex_cond_bold_18")
    sym_serif_body = _role_sym("HUMID1_FONT_EDITORIAL_BODY", "humid1_font_plex_serif_normal_18")
    sym_serif_title = _role_sym("HUMID1_FONT_EDITORIAL_TITLE", "humid1_font_plex_serif_bold_24")
    sym_formula = _role_sym("HUMID1_FONT_FORMULA", "humid1_font_plex_math_regular_16")
    sym_term = _role_sym("HUMID1_FONT_TERMINAL", "humid1_font_terminus_bold_16")

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

    # Ensure droplet (0xF043) and battery (0xF240) on the 200x200 panel always map to a valid icon
    # even when the active scheme only builds Phosphor, Lucide, or Tabler
    for cp_target, alt_candidates in [
        (0xF043, [0xF043, 0xE20A, 0xE1B4, 0xE073, 0xEA98, 0xEE80]),
        (0xF240, [0xF240, 0xE0DA, 0xE14E, 0xE053, 0xEA2F, 0xF668]),
    ]:
        for imap in (icon_fb_14, icon_fb_20):
            if cp_target not in imap and imap:
                for alt in alt_candidates:
                    if alt in imap:
                        imap[cp_target] = imap[alt]
                        break
                if cp_target not in imap:
                    imap[cp_target] = next(iter(imap.values()))

    def draw_strike_text(
        x0: int,
        y0: int,
        text: str,
        sym: str,
        fg: Tuple[int, int, int] = (15, 20, 25),
        scale: int = 1,
        fallback_sym: str = "humid1_font_plex_sans_normal_14",
        max_x: Optional[int] = None,
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
            adv = ((g.adv_w_fp4 + 8) >> 4) * scale
            if max_x is not None and cx + max(adv, (g.ofs_x + g.box_w) * scale) > max_x:
                break
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
            cx += adv
        return cx

    draw.rectangle([0, 0, W, 68], fill=(18, 22, 28))
    draw.text(
        (28, 14),
        f"HUMIDYNE LABS / HUMIDITRON  |  1-BPP BILEVEL EPD TYPOGRAPHY SUITE v{TOOL_VERSION} (188.15 DPI)",
        fill=(255, 255, 255),
        font=ui_fonts["title"],
    )
    draw.text(
        (28, 42),
        "Engine: 9-Pipeline Resolution-Reduction + Linear Grayscale + Full-Canvas ASCII Patching  •  200x200 Panel",
        fill=(180, 195, 210),
        font=ui_fonts["subtitle"],
    )

    panel_x, panel_y = 28, 90
    draw.rectangle([panel_x - 4, panel_y - 4, panel_x + 404, panel_y + 404], fill=(40, 45, 52), outline=(18, 22, 28), width=2)
    epd = Image.new("RGB", (200, 200), (255, 255, 255))
    epd_draw = ImageDraw.Draw(epd)

    def draw_epd_text(
        x0: int,
        y0: int,
        text: str,
        sym: str,
        fg=(0, 0, 0),
        align_right_x: Optional[int] = None,
        max_x: Optional[int] = None,
    ):
        r_sym = _resolve_sym(sym)
        if not r_sym:
            return
        gmap, line_h, base_l = strike_cache[r_sym]
        fb_gmap = strike_cache.get(sym_ui_body, ({}, 0, 0))[0]
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
            adv = (g.adv_w_fp4 + 8) >> 4
            if max_x is not None and cx + max(adv, g.ofs_x + g.box_w) > max_x:
                break
            if g.box_w > 0 and g.box_h > 0:
                gx0 = cx + g.ofs_x
                gy0 = baseline_y - (g.ofs_y + g.box_h)
                for r_idx, row_str in enumerate(g.rows):
                    for c_idx, px in enumerate(row_str):
                        if px == "#":
                            epd_draw.point((gx0 + c_idx, gy0 + r_idx), fill=fg)
            cx += adv

    draw_epd_text(6, 3, "HUMIDYNE LABS", sym_ui_sub, max_x=156)
    epd_draw.rectangle([200 - 4 - 36, 2, 200 - 4, 2 + 17], fill=(0, 0, 0))
    draw_epd_text(200 - 4 - 30, 3, "1/5", sym_tele_sm, fg=(255, 255, 255), max_x=196)
    epd_draw.line([(4, 22), (196, 22)], fill=(0, 0, 0), width=1)

    draw_epd_text(6, 28, "72.4°F", sym_ui_header, max_x=115)
    draw_epd_text(0, 28, "\uf043 46.8%", sym_ui_header, align_right_x=194)
    draw_epd_text(6, 56, "(22.4°C ambient • Td 10.4°C)", sym_cond_norm, max_x=194)
    epd_draw.line([(4, 82), (196, 82)], fill=(0, 0, 0), width=1)

    draw_epd_text(6, 91, "TriNode ΔT", sym_ui_body, max_x=110)
    draw_epd_text(0, 91, "+0.1°C (99%)", sym_ui_sub, align_right_x=194)
    draw_epd_text(6, 114, "Abs Humidity", sym_ui_body, max_x=125)
    draw_epd_text(0, 114, "9.3 g/m³", sym_ui_sub, align_right_x=194)
    draw_epd_text(6, 137, "Vapor Pressure", sym_ui_body, max_x=125)
    draw_epd_text(0, 137, "12.6 hPa", sym_ui_sub, align_right_x=194)

    epd_draw.line([(4, 164), (196, 164)], fill=(0, 0, 0), width=1)
    draw_epd_text(6, 172, "Cycle #142", sym_cond_norm, max_x=88)
    draw_epd_text(0, 172, "\uf240 4.12V • 18:52", sym_cond_norm, align_right_x=194)

    epd_zoomed = epd.resize((400, 400), resample=Image.NEAREST)
    img.paste(epd_zoomed, (panel_x, panel_y))
    draw_strike_text(panel_x, panel_y + 412, "Simulated 200x200 SSD1681 Panel (2x Nearest-Neighbor Zoom)", sym_ui_sub, fallback_sym=sym_ui_body)
    draw_strike_text(panel_x, panel_y + 432, "Keys: UI Body | Values: UI Subtitle | Hero: UI Header + Icons", sym_tele_sm, fg=(70, 80, 95), fallback_sym=sym_ui_body)

    box_y = 552
    draw.rectangle([28, box_y, 642, 992], fill=(255, 255, 255), outline=(200, 208, 218), width=1)
    draw_strike_text(44, box_y + 14, "1-BIT MONOCHROME ENGINE + ASCII PATCH VERIFICATION (6x Pixel Grid)", sym_ui_sub, fallback_sym=sym_ui_body, max_x=632)
    draw_strike_text(44, box_y + 36, "Resolution-Reduction + font_icon_epd_patches.json:", sym_tele_sm, fg=(70, 80, 95), fallback_sym=sym_ui_body, max_x=632)

    showcase_glyphs = [
        (sym_ui_body, 0x0040, "Body '@'"),
        (sym_ui_body, 0x0025, "Body '%'"),
        (sym_ui_body, 0x0065, "Body 'e'"),
        (sym_ui_body, 0x0061, "Body 'a'"),
        (sym_tele_body, 0x0030, "Mono '0'"),
        (sym_tele_body, 0x0025, "Mono '%'"),
        (sym_term, 0x0041, "Term 'A'"),
    ]
    px_x = 44
    for sym_key, code_c, label in showcase_glyphs:
        r_sk = _resolve_sym(sym_key)
        g_obj = strike_cache.get(r_sk, ({}, 0, 0))[0].get(code_c) if r_sk else None
        if not g_obj:
            continue
        cell = min(7, max(3, 64 // max(1, g_obj.box_w, g_obj.box_h)))
        grid_px_w = max(1, g_obj.box_w) * cell
        step_w = max(82, grid_px_w + 14)
        if px_x + grid_px_w > 630:
            break
        draw.text((px_x, box_y + 62), label, fill=(24, 32, 44), font=ui_fonts["mono_sm"])
        gy0 = box_y + 86
        for r_i, r_s in enumerate(g_obj.rows):
            for c_i, ch_p in enumerate(r_s):
                rx = px_x + c_i * cell
                ry = gy0 + r_i * cell
                fill_c = (15, 20, 25) if ch_p == "#" else (238, 242, 246)
                draw.rectangle([rx, ry, rx + max(1, cell - 2), ry + max(1, cell - 2)], fill=fill_c)
        px_x += step_w

    draw_strike_text(44, box_y + 196, "1:1 Native 188.15 DPI Readout (Primary Roles):", sym_ui_sub, fallback_sym=sym_ui_body, max_x=632)
    draw_strike_text(44, box_y + 222, "UI Body:    Sphinx of black quartz, judge my vow  |  0123456789 @%#$&80", sym_ui_body, fallback_sym=sym_ui_body, max_x=632)
    draw_strike_text(44, box_y + 248, "UI Sub:     Sphinx of black quartz, judge my vow  |  0123456789 @%#$&80", sym_ui_sub, fallback_sym=sym_ui_body, max_x=632)
    draw_strike_text(44, box_y + 274, "Term Sm:    0123456789  72.4°F  46.8% RH  9.3 g/m³  @ % # $ & 8 0 e a s", sym_tele_sm, fallback_sym=sym_ui_body, max_x=632)
    draw_strike_text(44, box_y + 298, "Mono Body:  0123456789  72.4°F  46.8% RH  9.3 g/m³  @ % # $ & 8 0 e a s", sym_tele_body, fallback_sym=sym_ui_body, max_x=632)
    draw_strike_text(44, box_y + 324, "Math 16px:  ΔT = +0.15°C  •  ∀x ∈ ℝ : ∑ f(x) ≈ √π ± ∞  •  α β γ δ ε θ λ μ π σ ω Ω", sym_formula, fallback_sym=sym_ui_body, max_x=632)

    icon_strip_str = "\uf043 \uf021 \uf240 \uf241 \uf242 \uf243 \uf244 \uf287 \uf0e7 \uf013 \uf071 \uf058 \uf00c \uf00d \uf1eb \uf2db"
    icon_strip_sym = "humid1_icon_fa7_solid_16"
    if icon_strip_sym not in strike_cache:
        for cand_ic in (
            "humid1_icon_tabler_filled_16",
            "humid1_icon_phosphor_fill_16",
            "humid1_icon_phosphor_fill_20",
            "humid1_icon_phosphor_regular_16",
            "humid1_icon_lucide_regular_16",
            "humid1_icon_tabler_regular_16",
        ):
            if cand_ic in strike_cache and strike_cache[cand_ic][0]:
                icon_strip_sym = cand_ic
                sample_cps = sorted(c for c in strike_cache[cand_ic][0].keys() if c >= 0xE000)[:16]
                icon_strip_str = " ".join(chr(c) for c in sample_cps)
                break
    draw_strike_text(44, box_y + 354, "Icons 16px:", sym_ui_sub, fallback_sym=sym_ui_body)
    draw_strike_text(142, box_y + 354, icon_strip_str, icon_strip_sym, fallback_sym=sym_ui_body, max_x=632)

    # Also render Filled Icon Showcase Strip if Tabler-Filled or Phosphor-Fill is in strike_cache
    for filled_cand in ("humid1_icon_tabler_filled_16", "humid1_icon_phosphor_fill_16", "humid1_icon_phosphor_fill_20"):
        if filled_cand in strike_cache and strike_cache[filled_cand][0]:
            f_cps = sorted(c for c in strike_cache[filled_cand][0].keys() if c >= 0xE000)[:16]
            f_str = " ".join(chr(c) for c in f_cps)
            draw_strike_text(44, box_y + 382, "Filled Icons:", sym_ui_sub, fallback_sym=sym_ui_body)
            draw_strike_text(146, box_y + 382, f_str, filled_cand, fallback_sym=sym_ui_body, max_x=632)
            break

    rx0 = 664
    draw.rectangle([rx0, 90, 1392, 992], fill=(255, 255, 255), outline=(200, 208, 218), width=1)
    draw.text((rx0 + 20, 104), "HUMID1 1-BPP SUB-FAMILY & SIZE LADDER (1:1 NATIVE PIXELS @ 188.15 DPI)", fill=(24, 32, 44), font=ui_fonts["section"])

    ladder_rows = [
        (f"UI Micro / Small ({sym_ui_micro})", sym_ui_micro, f"boot: humid1-os v{TOOL_VERSION}  |  SPI0 40MHz  |  0x0040 @%#08"),
        (f"UI Body ({sym_ui_body})", sym_ui_body, "Humidyne humid1  •  22.4°C  48.2% RH  9.3 g/m³  @%#&80"),
        (f"UI Body MD ({sym_ui_body_md})", sym_ui_body_md, "TriNode ΔT: +0.1°C  |  Vapor Pressure: 12.6 hPa"),
        (f"UI Subtitle ({sym_ui_sub})", sym_ui_sub, "PSYCHROMETRICS  •  SYSTEM HEALTH  •  SETTLED (99%)"),
        (f"UI Italic ({sym_ui_italic})", sym_ui_italic, "(22.4°C ambient  •  TriNode thermal equilibrium active)"),
        (f"UI Title ({sym_ui_title})", sym_ui_title, "ENVIRONMENTAL TELEMETRY & DEW POINT"),
        (f"UI Header ({sym_ui_header})", sym_ui_header, "72.4°F   \uf043 46.8% RH   \uf240 4.12V"),
        (f"Telemetry Hero ({sym_tele_lg})", sym_tele_lg, "72.4°F  |  46.8% RH  |  Td 50.7°F"),
        (f"Telemetry Jumbo ({sym_tele_xl})", sym_tele_xl, "72.4°F   46.8%"),
        (f"Terminal ({sym_term})", sym_term, "root@humid1:~# dmesg | grep epd -> 200x200 OK"),
        (f"Telemetry Body ({sym_tele_body})", sym_tele_body, "2026-11-21 01:20:00  |  328K Free  |  @%#08"),
        (f"Telemetry MD ({sym_tele_md})", sym_tele_md, "72.4°F   46.8% RH   12.6 hPa"),
        (f"Condensed Ribbon ({sym_cond_norm})", sym_cond_norm, "NARROW DOCK:  SHTC3 22.4°C  |  SSD1681 22.5°C  |  MCU 22.6°C"),
        (f"Condensed Banner ({sym_cond_bold})", sym_cond_bold, "CONDENSED BANNER:  THERMAL EQUILIBRIUM ACTIVE"),
        (f"Editorial Body ({sym_serif_body})", sym_serif_body, "Thermodynamic water vapor pressure & dew point invariants."),
        (f"Editorial Title ({sym_serif_title})", sym_serif_title, "Psychrometric Reference"),
        (f"Formula ({sym_formula})", sym_formula, "e_s(T) = 6.1094 · exp(17.625·T / (T + 243.04))   [ΔT ≤ 0.15°C]"),
    ]

    matched_rows = []
    seen_ladder_syms = set()
    for lbl, sym, smp in ladder_rows:
        if sym in strike_cache and sym not in seen_ladder_syms:
            matched_rows.append((lbl, sym, smp))
            seen_ladder_syms.add(sym)
    if len(matched_rows) < 6:
        seen_syms = {row[1] for row in matched_rows}
        for sym_k in sorted(strike_cache.keys()):
            if sym_k in seen_syms:
                continue
            gmap_k, lh_k, _ = strike_cache[sym_k]
            if "icon_" in sym_k:
                ic_cps = sorted(c for c in gmap_k.keys() if c >= 0xE000)[:16]
                s_txt = " ".join(chr(c) for c in ic_cps) if ic_cps else "0123456789"
            else:
                s_txt = "0123456789 AaBbCcGgQqWw @%#&$80 72.4°F 46.8%"
            matched_rows.append((f"{sym_k} (lh={lh_k}px, {len(gmap_k)} glyphs)", sym_k, s_txt))
            seen_syms.add(sym_k)
            if len(matched_rows) >= 8:
                break

    cy = 136
    for label, sym, sample in matched_rows:
        _, lh, _ = strike_cache[sym]
        if cy + lh + 20 > 980:
            break
        draw.text((rx0 + 20, cy), label, fill=(100, 112, 128), font=ui_fonts["mono_sm"])
        cy += 16
        draw_strike_text(rx0 + 20, cy, sample, sym, fg=(10, 14, 18), max_x=1376)
        cy += lh + 7
        draw.line([(rx0 + 20, cy - 3), (1372, cy - 3)], fill=(232, 236, 242), width=1)

    preview_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(preview_path))
    print(f"[+] Rendered master 188.15-DPI visual specimen sheet to {preview_path}")


def render_master_char_icon_map_png(
    out_png: Path,
    strike_cache: Dict[str, Tuple[Dict[int, GlyphStrike], int, int]],
    scheme_id: str = "epd-font",
    pipeline_name: str = "raw-hinted",
    static_dir: Optional[Path] = None,
) -> Path:
    """
    Render a combined full-scheme Master Character & Icon Map PNG (`master_char_icon_map.png`)
    summarizing all built font and icon strikes in a single overview sheet.
    """
    ui_fonts = _load_ui_fonts(static_dir)
    strikes_sorted = sorted(strike_cache.items(), key=lambda x: x[0])
    row_heights = [max(44, lh + 14) for _, (_, lh, _) in strikes_sorted]
    W = 1480
    H = max(360, 110 + sum(row_heights) + 32)
    img = Image.new("RGB", (W, H), (246, 248, 252))
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, W, 68], fill=(18, 24, 34))
    draw.text(
        (24, 14),
        f"HUMIDYNE LABS / HUMIDITRON epd-font v{TOOL_VERSION}  |  MASTER CHARACTER & ICON MAP ({scheme_id})",
        fill=(255, 255, 255),
        font=ui_fonts["title"],
    )
    draw.text(
        (24, 40),
        f"A 1-bit EPD font generator and asset pipeline for embedded displays  •  Pipeline: {pipeline_name}  •  Total Strikes: {len(strikes_sorted)}",
        fill=(180, 198, 220),
        font=ui_fonts["subtitle"],
    )

    y = 84
    for idx, (sym, (gmap, lh, bl)) in enumerate(strikes_sorted):
        row_h = row_heights[idx]
        bg = (255, 255, 255) if (idx % 2 == 0) else (240, 244, 250)
        draw.rectangle([20, y, W - 20, y + row_h - 4], fill=bg, outline=(216, 224, 234), width=1)
        draw.text((32, y + max(10, (row_h - 18) // 2)), f"{sym:<40} ({len(gmap):>4d} glyphs, lh={lh}px)", fill=(24, 32, 44), font=ui_fonts["mono"])

        cx = 540
        by = y + 6 + (lh - bl)
        sample_cps = sorted(c for c in gmap.keys() if c > 0x20)[:36]
        for cp in sample_cps:
            g = gmap[cp]
            if g.box_w > 0 and g.box_h > 0 and cx + g.box_w < W - 36:
                gx0 = cx + max(0, g.ofs_x)
                gy0 = by - (g.ofs_y + g.box_h)
                gy0 = max(y + 4, min(y + row_h - 6 - g.box_h, gy0))
                for rr, r_str in enumerate(g.rows):
                    for cc, px in enumerate(r_str):
                        if px == "#":
                            draw.point((gx0 + cc, gy0 + rr), fill=(12, 16, 22))
            cx += max(g.box_w + 4, ((g.adv_w_fp4 + 8) >> 4) + 2)
        y += row_h

    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out_png))
    return out_png
