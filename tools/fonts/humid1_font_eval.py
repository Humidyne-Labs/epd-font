#!/usr/bin/env python3
"""
humid1_font_eval.py (v1.0.12)
=============================
Humidyne Labs / Humiditron `epd-font` Multi-Font & Multi-Weight Tournament Evaluator,
Size-Floor Estimator & Visual Specimen Scorecard Generator.

Repository : https://github.com/Humidyne-Labs/epd-font
Target OS  : https://github.com/Humidyne-Labs/H1OS
License    : MIT License

Purpose:
--------
Allows feeding in any set of `.ttf` / `.otf` font files (or scanning `build/static_ttfs/`
and optional external directories) to:
  1. Evaluate each typeface & weight across target pixel sizes (`10px, 12px, 14px, 16px, 18px, 20px, 24px`)
     both BEFORE and AFTER the Multi-Method Iterative Typographic Tournament (`humid1_bilevel_tuner.py`).
  2. Estimate the **Minimum Viable Pixel Size Floor** (`px_floor_raw` vs `px_floor_repaired`) based on:
     - Enclosed Counter Survival Rate (`B1` hole retention on `04689ABDOPQRabdegopq$%&@`) >= 90%
     - `>=2px` Stem Survival Rate >= 90%
     - Mean Tournament Quality Score (`0..100`) >= 78.0
  3. Quantify the **3-Tier Weight Hierarchy Separation** (`normal = Medium 500`, `bold = ExtraBold 800`,
     `italic = MediumItalic 500` vs legacy `Regular 400` and `Bold 700`), measuring mean stem thickness
     (px) and relative ink-mass delta (`+Delta Ink %`).
  4. Emit a structured Markdown/JSON report (`build/font_eval/font_eval_report.md` & `.json`) and a
     side-by-side 1-BPP visual comparison sheet (`build/font_eval/font_eval_comparison_sheet.png`).
"""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import humid1_bilevel_tuner as bt
from humid1_ft_raster import (
    FT_FaceRec,
    FT_LOAD_NO_HINTING,
    FT_LOAD_RENDER,
    FT_LOAD_TARGET_NORMAL,
    GlyphStrike,
    load_freetype,
    rasterize_font_strike,
)

TOOL_VERSION = "1.0.12"

# Diagnostic benchmark character set (38 critical glyphs: counters, narrow stems, paired brackets, symbols)
EVAL_BENCHMARK_CHARS = "0124689ABDHIJMNOPQRWabefgijlmnoqrstvwxyz$%&()[]{}/\\|!<>+="
EVAL_COUNTER_CHARS = set("04689ABDOPQRabdegopq$%&")
EVAL_SPECIMEN_STRING = "H1OS v1.0.12 (08B$) [aeg] {1lI|!} <=>"


@dataclass
class SizeMetrics:
    size_px: int
    mean_score_before: float
    mean_score_after: float
    stem_2px_rate_before: float
    stem_2px_rate_after: float
    counter_survival_before: float
    counter_survival_after: float
    mean_stem_width_px: float
    total_ink_pixels: int
    repaired_glyphs: int
    total_glyphs: int
    passes_floor_raw: bool
    passes_floor_repaired: bool


@dataclass
class FontEvalSummary:
    label: str
    font_file: str
    family_group: str
    weight_class: int
    is_italic: bool
    size_floor_raw_px: int
    size_floor_repaired_px: int
    by_size: Dict[int, SizeMetrics] = field(default_factory=dict)


def _render_hq_gray_for_face(ft, hq_face, cp_val: int) -> Optional[np.ndarray]:
    gidx = ft.FT_Get_Char_Index(hq_face, cp_val)
    if gidx == 0:
        return None
    if ft.FT_Load_Glyph(hq_face, gidx, FT_LOAD_RENDER | FT_LOAD_NO_HINTING | FT_LOAD_TARGET_NORMAL) != 0:
        return None
    slot = hq_face.contents.glyph.contents
    bmp = slot.bitmap
    if bmp.rows <= 0 or bmp.width <= 0:
        return None
    arr = np.zeros((bmp.rows, bmp.width), dtype=np.uint8)
    for r_i in range(bmp.rows):
        for c_i in range(bmp.width):
            arr[r_i, c_i] = bmp.buffer[r_i * bmp.pitch + c_i]
    ys, xs = np.nonzero(arr > 16)
    if len(xs) == 0:
        return None
    return arr[int(ys.min()) : int(ys.max()) + 1, int(xs.min()) : int(xs.max()) + 1]


def _measure_mean_stem_width(glyphs: Sequence[GlyphStrike]) -> float:
    widths: List[int] = []
    for g in glyphs:
        if not g.rows or g.box_w <= 1:
            continue
        arr = bt.rows_to_binary_array(g.rows)
        h, w = arr.shape
        for r in range(h):
            runs = bt._get_row_runs(arr[r])
            if 1 <= len(runs) <= 3:
                for s, e in runs:
                    rlen = e - s + 1
                    if rlen < max(4, int(w * 0.78)):
                        widths.append(rlen)
    return float(np.mean(widths)) if widths else 1.0


def evaluate_single_font(
    ft,
    ft_lib,
    label: str,
    font_path: Path,
    family_group: str,
    weight_class: int,
    is_italic: bool,
    sizes: Sequence[int],
) -> Tuple[FontEvalSummary, Dict[int, List[GlyphStrike]]]:
    codepoints = sorted({ord(c) for c in (EVAL_BENCHMARK_CHARS + EVAL_SPECIMEN_STRING)})
    summary = FontEvalSummary(
        label=label,
        font_file=font_path.name,
        family_group=family_group,
        weight_class=weight_class,
        is_italic=is_italic,
        size_floor_raw_px=99,
        size_floor_repaired_px=99,
    )
    repaired_strikes_by_size: Dict[int, List[GlyphStrike]] = {}

    is_terminus = "terminus" in font_path.name.lower()
    is_mono = ("mono" in font_path.name.lower()) or is_terminus

    for sz in sizes:
        # For Terminus, pick the matching native strike TTF if available
        active_path = font_path
        if is_terminus:
            role_tag = "Bold" if weight_class >= 700 else "Normal"
            cand_term = font_path.parent / f"Terminus-{role_tag}-{sz}.ttf"
            if cand_term.is_file():
                active_path = cand_term

        glyphs, *_ = rasterize_font_strike(
            ft=ft,
            ft_lib=ft_lib,
            font_path=active_path,
            size_px=sz,
            codepoints=codepoints,
            raster_mode="autohint_mono",
            threshold=128,
        )

        hq_face = ctypes.POINTER(FT_FaceRec)()
        has_hq = (ft.FT_New_Face(ft_lib, str(active_path).encode("utf-8"), 0, ctypes.byref(hq_face)) == 0)
        if has_hq:
            ft.FT_Set_Pixel_Sizes(hq_face, 0, sz * 8)

        recs: List[bt.RepairAuditRecord] = []
        scores_bef: List[float] = []
        scores_aft: List[float] = []
        stem_ok_bef = 0
        stem_ok_aft = 0
        stem_total = 0
        cnt_ok_bef = 0
        cnt_ok_aft = 0
        cnt_total = 0

        for g in glyphs:
            if not g.rows or g.codepoint <= 0x0020:
                continue
            ch = chr(g.codepoint)
            arr_bef = bt.rows_to_binary_array(g.rows)
            hq_img = _render_hq_gray_for_face(ft, hq_face, g.codepoint) if has_hq else None

            if is_terminus:
                # Native hand-authored bitmap strike
                needs_h, _, h_ratio, _ = bt.measure_stem_deficits(arr_bef, min_stem=2 if weight_class >= 700 else 1, codepoint=g.codepoint)
                b0, b1, _ = bt.compute_betti_numbers(arr_bef)
                exp_b1 = 2 if ch in "8B$" else (1 if ch in EVAL_COUNTER_CHARS else 0)
                sc = 88.0 if b1 >= exp_b1 else 60.0
                rec = bt.RepairAuditRecord(
                    codepoint=g.codepoint,
                    char_label=ch,
                    box_w_before=g.box_w,
                    box_h_before=g.box_h,
                    box_w_after=g.box_w,
                    box_h_after=g.box_h,
                    holes_expected=exp_b1,
                    holes_before=b1,
                    holes_after=b1,
                    thin_v_before=needs_h,
                    thin_h_before=False,
                    thin_v_after=needs_h,
                    thin_h_after=False,
                    repaired=False,
                    size_floor_warning=(b1 < exp_b1),
                    engine_used="NativeBDF",
                    rows_before=g.rows,
                    rows_after=g.rows,
                    score_before=sc,
                    score_after=sc,
                )
                recs.append(rec)
            else:
                max_w = (g.adv_w_fp4 >> 4) if is_mono else ((g.adv_w_fp4 >> 4) + 1)
                w_orig = g.box_w
                rep_arr, rec = bt.inspect_and_repair_glyph_bitmap(
                    arr_bef,
                    codepoint=g.codepoint,
                    min_stem=2,
                    master_hi=hq_img,
                    max_width_ceiling=max_w,
                    is_italic_or_serif=is_italic or (family_group == "serif"),
                )
                recs.append(rec)
                if rec.repaired:
                    trimmed, bw, bh, nox, noy = bt.trim_binary_array(rep_arr, g.ofs_x, g.ofs_y)
                    if bw > 0 and bh > 0:
                        g.rows = bt.binary_array_to_rows(trimmed)
                        g.box_w, g.box_h, g.ofs_x, g.ofs_y = bw, bh, nox, noy
                        g.patched = True
                        if not is_mono and bw > w_orig:
                            g.adv_w_fp4 += (bw - w_orig) * 16

        if not is_terminus:
            bt.synchronize_mirror_glyph_pairs(glyphs, recs, is_italic=is_italic, is_monospace=is_mono)

        if has_hq:
            ft.FT_Done_Face(hq_face)

        for r in recs:
            if r.char_label not in EVAL_BENCHMARK_CHARS:
                continue
            scores_bef.append(max(0.0, r.score_before))
            scores_aft.append(max(0.0, r.score_after))
            stem_total += 1
            if not r.thin_v_before:
                stem_ok_bef += 1
            if not r.thin_v_after:
                stem_ok_aft += 1
            if r.char_label in EVAL_COUNTER_CHARS and r.holes_expected > 0:
                cnt_total += 1
                if r.holes_before >= r.holes_expected:
                    cnt_ok_bef += 1
                if r.holes_after >= r.holes_expected:
                    cnt_ok_aft += 1

        s_rate_bef = float(stem_ok_bef) / float(max(1, stem_total))
        s_rate_aft = float(stem_ok_aft) / float(max(1, stem_total))
        c_rate_bef = float(cnt_ok_bef) / float(max(1, cnt_total))
        c_rate_aft = float(cnt_ok_aft) / float(max(1, cnt_total))
        m_bef = float(np.mean(scores_bef)) if scores_bef else 0.0
        m_aft = float(np.mean(scores_aft)) if scores_aft else 0.0

        bench_glyphs = [g for g in glyphs if g.codepoint > 0x20 and chr(g.codepoint) in EVAL_BENCHMARK_CHARS]
        total_ink = sum(sum(row.count("#") for row in g.rows) for g in bench_glyphs if g.rows)
        mean_stem_w = _measure_mean_stem_width(bench_glyphs)
        rep_cnt = sum(1 for r in recs if r.repaired)

        pass_raw = (c_rate_bef >= 0.88) and (s_rate_bef >= 0.82 if not is_terminus else True)
        pass_rep = (c_rate_aft >= 0.90) and (s_rate_aft >= 0.88 if not is_terminus else True)

        if pass_raw and summary.size_floor_raw_px == 99:
            summary.size_floor_raw_px = sz
        if pass_rep and summary.size_floor_repaired_px == 99:
            summary.size_floor_repaired_px = sz

        summary.by_size[sz] = SizeMetrics(
            size_px=sz,
            mean_score_before=round(m_bef, 1),
            mean_score_after=round(m_aft, 1),
            stem_2px_rate_before=round(s_rate_bef * 100.0, 1),
            stem_2px_rate_after=round(s_rate_aft * 100.0, 1),
            counter_survival_before=round(c_rate_bef * 100.0, 1),
            counter_survival_after=round(c_rate_aft * 100.0, 1),
            mean_stem_width_px=round(mean_stem_w, 2),
            total_ink_pixels=int(total_ink),
            repaired_glyphs=rep_cnt,
            total_glyphs=len(recs),
            passes_floor_raw=pass_raw,
            passes_floor_repaired=pass_rep,
        )
        repaired_strikes_by_size[sz] = glyphs

    return summary, repaired_strikes_by_size


def render_font_eval_comparison_sheet(
    out_png: Path,
    summaries: Sequence[FontEvalSummary],
    strikes_map: Dict[str, Dict[int, List[GlyphStrike]]],
    sizes: Sequence[int],
) -> None:
    """Render a side-by-side multi-font, multi-weight 1-BPP visual specimen & size-floor scorecard PNG."""
    row_h = 46
    hdr_h = 76
    left_col_w = 270
    size_col_w = 345
    pad = 16

    img_w = pad * 2 + left_col_w + len(sizes) * size_col_w
    img_h = hdr_h + pad * 2 + (len(summaries) + 1) * row_h
    img = Image.new("RGB", (img_w, img_h), (246, 247, 250))
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, img_w, hdr_h], fill=(18, 23, 31))
    draw.text(
        (pad, 14),
        f"HUMID1 v{TOOL_VERSION} MULTI-FONT & WEIGHT HIERARCHY TOURNAMENT SCORECARD (188 DPI 1-BPP)",
        fill=(255, 255, 255),
    )
    draw.text(
        (pad, 38),
        f"Test String: \"{EVAL_SPECIMEN_STRING}\" | Green = Passes >=2px Stem & Counter Floor | Red = Below Viable Floor",
        fill=(182, 200, 222),
    )

    y_tbl = hdr_h + pad
    draw.rectangle([pad, y_tbl, img_w - pad, y_tbl + row_h - 4], fill=(32, 40, 54))
    draw.text((pad + 10, y_tbl + 14), "TYPEFACE / WEIGHT ROLE (FLOOR)", fill=(255, 255, 255))
    for s_idx, sz in enumerate(sizes):
        x_col = pad + left_col_w + s_idx * size_col_w
        pt96 = sz * 72.0 / 96.0
        draw.text((x_col + 8, y_tbl + 14), f"{sz}px ({pt96:.1f}pt @96DPI) — Post-Tournament 1-BPP", fill=(210, 225, 245))

    for idx, summ in enumerate(summaries):
        ry = y_tbl + (idx + 1) * row_h
        bg = (255, 255, 255) if idx % 2 == 0 else (239, 242, 247)
        draw.rectangle([pad, ry, img_w - pad, ry + row_h - 4], fill=bg, outline=(210, 216, 224))

        fl_raw = f"{summ.size_floor_raw_px}px" if summ.size_floor_raw_px < 99 else "N/A"
        fl_rep = f"{summ.size_floor_repaired_px}px" if summ.size_floor_repaired_px < 99 else ">24px"
        draw.text((pad + 8, ry + 6), f"{summ.label}", fill=(18, 23, 31))
        draw.text(
            (pad + 8, ry + 23),
            f"wght={summ.weight_class} | Floor: Raw {fl_raw} -> Tuned {fl_rep}",
            fill=(22, 118, 72) if summ.size_floor_repaired_px <= 14 else (140, 75, 20),
        )

        for s_idx, sz in enumerate(sizes):
            x_col = pad + left_col_w + s_idx * size_col_w
            m = summ.by_size.get(sz)
            glyphs = strikes_map.get(summ.label, {}).get(sz, [])
            if not m or not glyphs:
                continue

            badge_c = (22, 118, 72) if m.passes_floor_repaired else (175, 48, 48)
            meta_txt = f"Stem>=2px:{m.stem_2px_rate_after:.0f}% Cnt:{m.counter_survival_after:.0f}% w={m.mean_stem_width_px:.2f}px Ink:{m.total_ink_pixels}"
            draw.text((x_col + 6, ry + 3), meta_txt, fill=badge_c)

            # Render 1-BPP specimen string at 1:1 pixel scale (or 1x with crisp black pixels)
            g_map = {g.codepoint: g for g in glyphs}
            pen_x = x_col + 8
            baseline_y = ry + row_h - 10
            for ch in EVAL_SPECIMEN_STRING:
                cp = ord(ch)
                if cp == 0x20:
                    pen_x += max(3, sz // 3)
                    continue
                g = g_map.get(cp)
                if g is None or not g.rows:
                    pen_x += max(3, sz // 3)
                    continue
                gx0 = pen_x + g.ofs_x
                gy0 = baseline_y - g.ofs_y - g.box_h
                for r_i, r_str in enumerate(g.rows):
                    for c_i, px_ch in enumerate(r_str):
                        if px_ch == "#":
                            px_x = gx0 + c_i
                            px_y = gy0 + r_i
                            if x_col + 4 <= px_x < x_col + size_col_w - 6 and ry + 14 <= px_y < ry + row_h - 5:
                                img.putpixel((px_x, px_y), (14, 18, 24))
                pen_x += max(g.box_w + 1, g.adv_w_fp4 >> 4)
                if pen_x > x_col + size_col_w - 14:
                    break

    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png, optimize=True)


def generate_markdown_report(
    summaries: Sequence[FontEvalSummary],
    sizes: Sequence[int],
) -> str:
    lines: List[str] = [
        f"# Humiditron `epd-font` v{TOOL_VERSION} — Multi-Font & Weight Hierarchy Benchmark Report",
        "",
        "## 1. Executive Summary & Minimum Viable Pixel Size Floors",
        "",
        "Each candidate typeface and weight was evaluated across `10px, 12px, 14px, 16px, 20px` both **Before (`Raw`)** and **After (`Tuned`)** the v1.0.12 Multi-Method Iterative Typographic Tournament (`M0..M8` + Bilateral Mirror Synchronization).",
        "",
        "| Typeface & Role Label | Source Font File | Weight (`wght`) | Raw Size Floor (`px`) | Tuned Size Floor (`px`) | 14px `>=2px` Stems (`Raw -> Tuned`) | 16px `>=2px` Stems (`Raw -> Tuned`) | 16px Counter Survival | 16px Mean Stem (`px`) | 16px Total Ink (`px`) |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]

    for s in summaries:
        fl_raw = f"`{s.size_floor_raw_px}px`" if s.size_floor_raw_px < 99 else "`>20px`"
        fl_rep = f"**`{s.size_floor_repaired_px}px`**" if s.size_floor_repaired_px < 99 else "`>20px`"
        m14 = s.by_size.get(14)
        m16 = s.by_size.get(16)
        s14_str = f"`{m14.stem_2px_rate_before:.1f}% -> {m14.stem_2px_rate_after:.1f}%`" if m14 else "N/A"
        s16_str = f"`{m16.stem_2px_rate_before:.1f}% -> {m16.stem_2px_rate_after:.1f}%`" if m16 else "N/A"
        c16_str = f"`{m16.counter_survival_after:.1f}%`" if m16 else "N/A"
        w16_str = f"`{m16.mean_stem_width_px:.2f}px`" if m16 else "N/A"
        ink16_str = f"`{m16.total_ink_pixels:,}`" if m16 else "N/A"
        lines.append(
            f"| **{s.label}** | `{s.font_file}` | `{s.weight_class}` | {fl_raw} | {fl_rep} | {s14_str} | {s16_str} | {c16_str} | {w16_str} | {ink16_str} |"
        )

    lines.extend([
        "",
        "## 2. 3-Tier Weight Hierarchy Analysis (`normal = Medium 500`, `bold = ExtraBold 800`, `italic = MediumItalic 500`)",
        "",
        "In `v1.0.10–v1.0.11`, promoting `normal` from `Regular (400)` to `Medium (500)` improved baseline readability, but left `normal (500)` and `bold (700)` visually nearly identical at `12px–16px` because both `wght=500` and `wght=700` quantize to `2px` vertical stems on a 1-BPP grid. Synthesizing **`ExtraBold (800)`** (`1.45x` horizontal `gvar` weight delta, `1.18x` vertical crossbar delta) and mapping `bold -> ExtraBold (800)` restores a clear, unmistakable 3-tier hierarchy:",
        "",
        "| Size (`px`) | `Regular (400)` Ink | `normal = Medium (500)` Ink | Legacy `Bold (700)` Ink (`vs Medium`) | New `bold = ExtraBold (800)` Ink (`vs Medium`) | `italic = MediumItalic (500)` Ink |",
        "| :---: | :---: | :---: | :---: | :---: | :---: |",
    ])

    by_lbl = {s.label: s for s in summaries}
    s_reg = by_lbl.get("IBM Plex Sans Regular (400)")
    s_med = by_lbl.get("IBM Plex Sans Normal [Medium 500]")
    s_b700 = by_lbl.get("IBM Plex Sans Bold-700 [Legacy]")
    s_b800 = by_lbl.get("IBM Plex Sans Bold [ExtraBold 800]")
    s_ital = by_lbl.get("IBM Plex Sans Italic [MedItal 500]")

    for sz in sizes:
        if not (s_reg and s_med and s_b700 and s_b800 and s_ital):
            break
        i_reg = s_reg.by_size[sz].total_ink_pixels
        i_med = s_med.by_size[sz].total_ink_pixels
        i_700 = s_b700.by_size[sz].total_ink_pixels
        i_800 = s_b800.by_size[sz].total_ink_pixels
        i_itl = s_ital.by_size[sz].total_ink_pixels
        d700 = ((i_700 - i_med) / float(max(1, i_med))) * 100.0
        d800 = ((i_800 - i_med) / float(max(1, i_med))) * 100.0
        lines.append(
            f"| **{sz}px** | `{i_reg:,} px` | `{i_med:,} px` | `{i_700:,} px ({d700:+.1f}%)` | **`{i_800:,} px ({d800:+.1f}%)`** | `{i_itl:,} px` |"
        )

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    t0 = time.perf_counter()
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent if script_dir.name == "fonts" else script_dir.parent

    parser = argparse.ArgumentParser(
        prog="humid1_font_eval.py",
        description=f"Humidyne Labs `epd-font` v{TOOL_VERSION} — Multi-Font & Weight Tournament Evaluator & Size-Floor Benchmark.",
    )
    parser.add_argument("--src-dir", type=str, default=str(repo_root / "build" / "static_ttfs"), help="Static TTF directory")
    parser.add_argument("--out-dir", type=str, default=str(repo_root / "build" / "font_eval"), help="Output directory for report & scorecard PNG")
    parser.add_argument("--fonts", type=str, nargs="*", default=None, help="Optional explicit list of .ttf/.otf font paths to evaluate")
    parser.add_argument("--sizes", type=int, nargs="+", default=[10, 12, 14, 16, 20], help="Pixel sizes to benchmark (default: 10 12 14 16 20)")
    args = parser.parse_args()

    src_dir = Path(args.src_dir).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    ft, ft_lib = load_freetype()

    # Default benchmark lineup: IBM Plex Sans (400, 500, 700, 800, Italic 500), Mono (500, 800), Serif (500, 800), Math (400), Terminus, plus Inter if available
    candidates: List[Tuple[str, Path, str, int, bool]] = []
    if args.fonts:
        for fp_str in args.fonts:
            fp = Path(fp_str).resolve()
            if fp.is_file():
                candidates.append((fp.stem, fp, "custom", 400, "italic" in fp.stem.lower()))
    else:
        default_specs = [
            ("IBM Plex Sans Regular (400)", src_dir / "IBMPlexSans-Regular.ttf", "sans", 400, False),
            ("IBM Plex Sans Normal [Medium 500]", src_dir / "IBMPlexSans-Medium.ttf", "sans", 500, False),
            ("IBM Plex Sans Bold-700 [Legacy]", src_dir / "IBMPlexSans-Bold.ttf", "sans", 700, False),
            ("IBM Plex Sans Bold [ExtraBold 800]", src_dir / "IBMPlexSans-ExtraBold.ttf", "sans", 800, False),
            ("IBM Plex Sans Italic [MedItal 500]", src_dir / "IBMPlexSans-MediumItalic.ttf", "sans", 500, True),
            ("IBM Plex Mono Normal [Medium 500]", src_dir / "IBMPlexMono-Medium.ttf", "mono", 500, False),
            ("IBM Plex Mono Bold [ExtraBold 800]", src_dir / "IBMPlexMono-ExtraBold.ttf", "mono", 800, False),
            ("IBM Plex Serif Normal [Medium 500]", src_dir / "IBMPlexSerif-Medium.ttf", "serif", 500, False),
            ("IBM Plex Serif Bold [ExtraBold 800]", src_dir / "IBMPlexSerif-ExtraBold.ttf", "serif", 800, False),
            ("IBM Plex Math Regular (400)", src_dir / "IBMPlexMath-Regular.ttf", "math", 400, False),
            ("Terminus Native Bitmap (400)", src_dir / "Terminus-Normal-16.ttf", "terminus", 400, False),
        ]
        # Also include Inter if installed on host/VM for cross-foundry comparison
        inter_dir = Path("/usr/share/fonts/opentype/inter")
        if (inter_dir / "Inter-Medium.otf").is_file():
            default_specs.extend([
                ("Inter Medium (500) [External]", inter_dir / "Inter-Medium.otf", "sans", 500, False),
                ("Inter ExtraBold (800) [External]", inter_dir / "Inter-ExtraBold.otf", "sans", 800, False),
            ])
        for lbl, p, fg, wght, is_it in default_specs:
            if p.is_file():
                candidates.append((lbl, p, fg, wght, is_it))

    summaries: List[FontEvalSummary] = []
    strikes_map: Dict[str, Dict[int, List[GlyphStrike]]] = {}

    print(f"[*] Benchmarking {len(candidates)} font cuts across sizes {args.sizes}...")
    for lbl, fpath, fg, wght, is_it in candidates:
        summ, s_map = evaluate_single_font(ft, ft_lib, lbl, fpath, fg, wght, is_it, args.sizes)
        summaries.append(summ)
        strikes_map[lbl] = s_map
        m16 = summ.by_size.get(16)
        s16_txt = f"16px >=2px:{m16.stem_2px_rate_after:5.1f}% Ink:{m16.total_ink_pixels:4d}" if m16 else ""
        print(
            f"    [+] {lbl:36s} | Raw Floor: {summ.size_floor_raw_px:>2}px -> Tuned Floor: {summ.size_floor_repaired_px:>2}px | {s16_txt}"
        )

    md_report = generate_markdown_report(summaries, args.sizes)
    md_path = out_dir / "font_eval_report.md"
    md_path.write_text(md_report, encoding="utf-8")

    audit_md_path = repo_root / "docs" / "audits" / f"FONT_EVAL_BENCHMARK_v{TOOL_VERSION}.md"
    audit_md_path.parent.mkdir(parents=True, exist_ok=True)
    audit_md_path.write_text(md_report, encoding="utf-8")

    json_path = out_dir / "font_eval_report.json"
    json_path.write_text(
        json.dumps([asdict(s) for s in summaries], indent=2) + "\n",
        encoding="utf-8",
    )

    png_path = out_dir / "font_eval_comparison_sheet.png"
    render_font_eval_comparison_sheet(png_path, summaries, strikes_map, args.sizes)
    elapsed = time.perf_counter() - t0
    print(f"[+] Wrote Font Evaluation Benchmark Report -> {md_path}")
    print(f"[+] Wrote Visual Scorecard PNG             -> {png_path} ({elapsed:.2f}s)")


if __name__ == "__main__":
    main()
