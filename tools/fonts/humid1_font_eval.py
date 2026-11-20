#!/usr/bin/env python3
"""
humid1_font_eval.py (v1.0.23)
=============================
A 1-bit EPD font generator and asset pipeline for embedded displays.
Repository : https://github.com/Humidyne-Labs/epd-font
Authors    : Humiditron (https://github.com/humiditron) & AI/LLM Development Partner
License    : MIT License

Multi-Core 9-Pipeline Font & Weight Evaluation Suite (v1.0.23):
  - Evaluates ALL NINE bilevel resolution-reduction pipelines per font and per pixel size:
      1. `raw-unhinted`    : Raw Threshold Pipeline without Hinting (Linear Grayscale + Gamma)
      2. `raw-hinted`      : Raw Threshold Pipeline with Hinting (Linear Grayscale + Gamma)
      3. `svg-potrace`     : Custom SVG / Potrace Vector Pipeline (RETR_TREE Hierarchical Contours)
      4. `svg-potrace-jfa` : SVG / Potrace + 3D 1+JFA Marching Squares Sub-Pixel Vectorization
      5. `mdf`             : MDF (Median-Filtered + Signed Distance Field) Pipeline
      6. `msdf`            : Multi-Channel Signed Distance Field (Chlumsky/msdfgen 3-Channel R,G,B Median)
      7. `sdf-smoothstep`  : Supersampled Signed Distance Field + Hermite Smoothstep Reconstruction
      8. `adf-biquadratic` : Adaptive Distance Field (Quadtree Biquadratic Surface Reconstruction)
      9. `otsu-adaptive`   : Linear-Luminance Otsu + Sauvola Local Adaptive Thresholding
  - Recursively discovers `.ttf`, `.otf`, `.ttc`, and `.bdf` font files in `--src-dir`.
  - Computes per-pipeline and per-size optical metrics (`8x` HQ IoU Confidence, `>=2px` Stem
    Survival, Enclosed Counter Topology Survival via Betti number B1, Mean Stem Width, Ink Mass,
    and Viable Pixel Size Floor).
  - Generates per-font 9-pipeline visual comparison sheets (`<out_dir>/sheets/<font>_eval.png`),
    paginated master comparison sheets (`<out_dir>/font_eval_comparison_sheet.png`), and
    structured Markdown, CSV, and JSON evaluation reports inside `<out_dir>/` (under `build/`).
"""

from __future__ import annotations

import argparse
import csv
import ctypes
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# Early CLI scan to set EPD_FONT_ACCEL and disable OpenCV OpenCL before any math backends load
def _early_accel_scan() -> None:
    accel = os.environ.get("EPD_FONT_ACCEL", "").strip().lower()
    if not accel:
        for idx, arg in enumerate(sys.argv):
            if arg == "--accel" and idx + 1 < len(sys.argv):
                accel = sys.argv[idx + 1].strip().lower()
                break
            elif arg.startswith("--accel="):
                accel = arg.split("=", 1)[1].strip().lower()
                break
    if accel == "cpu":
        os.environ["EPD_FONT_ACCEL"] = "cpu"
        os.environ["OPENCV_OPENCL_RUNTIME"] = "disabled"
        try:
            import cv2
            if hasattr(cv2, "ocl"):
                cv2.ocl.setUseOpenCL(False)
        except Exception:
            pass

_early_accel_scan()

from math_backends import describe_math_backend, select_math_backend, teardown_math_backends
from humid1_bilevel_pipelines import (
    CANONICAL_MIN_HOLES,
    CANONICAL_PIPELINES,
    FT_LOAD_NO_HINTING,
    FT_LOAD_RENDER,
    FT_LOAD_TARGET_NORMAL,
    compute_betti_numbers,
    compute_upscaled_hq_metrics,
    measure_stem_metrics,
    rows_to_binary_array,
)
from humid1_ft_raster import (
    FT_FaceRec,
    GlyphStrike,
    load_freetype,
    open_ttfont_safe,
    rasterize_font_strike,
)
from humid1_runtime import (
    PROJECT_TAGLINE,
    TOOL_VERSION,
    detect_host_hardware,
    fail_gracefully,
    install_clean_signal_handlers,
    load_and_validate_hardware_scheme,
    require_valid_path,
    run_parallel_tasks,
)

EVAL_BENCHMARK_CHARS = "0124689ABCDHIJMNOPQRWabcefghijlmnoqrstvwxyz$%&()[]{}/\\|!<>+="
EVAL_SPECIMEN_STRING = "H1OS v1.0.23 (08B$) [aeg] {WwMm} <=>"


@dataclass
class PipelineSizeMetrics:
    pipeline: str
    size_px: int
    threshold: int
    gamma: float
    hq_conf_pct: float
    hq_diff_pct: float
    stem_2px_pct: float
    counter_pct: float
    mean_stem_width_px: float
    ink_pixels: int
    total_glyphs: int
    passes_floor: bool
    composite_score: float


@dataclass
class FontEvalSummary:
    label: str
    font_file: str
    file_type: str
    family_group: str
    weight_class: int
    is_italic: bool
    threshold: int
    gamma: float
    best_pipeline: str
    best_pipeline_score_16px: float
    floor_by_pipeline: Dict[str, int] = field(default_factory=dict)
    score_16px_by_pipeline: Dict[str, float] = field(default_factory=dict)
    by_pipeline_size: Dict[str, Dict[int, PipelineSizeMetrics]] = field(default_factory=dict)
    sheet_png: str = ""


def discover_candidate_fonts(src_dir: Path, explicit_fonts: Optional[Sequence[str]] = None) -> List[Tuple[str, Path, str, int, bool]]:
    """
    Recursively discover evaluable `.ttf`, `.otf`, `.ttc`, and `.bdf` font files in `src_dir`
    (or from `explicit_fonts`), returning `(label, font_path, family_group, weight_class, is_italic)`.
    """
    raw_paths: List[Path] = []
    if explicit_fonts:
        for f in explicit_fonts:
            p = require_valid_path(f, "--fonts", must_exist=True, expect_dir=False)
            raw_paths.append(p)
    else:
        for dirpath, _, filenames in os.walk(src_dir):
            dp = Path(dirpath)
            if "cache" in dp.parts or "metadata" in dp.parts:
                continue
            for fn in sorted(filenames):
                if fn.lower().endswith((".ttf", ".otf", ".ttc", ".bdf")):
                    raw_paths.append((dp / fn).resolve())

    candidates: List[Tuple[str, Path, str, int, bool]] = []
    seen_stems = set()
    for p in sorted(raw_paths, key=lambda x: x.name.lower()):
        low = p.name.lower()
        if any(ic in low for ic in ("fontawesome", "lucide", "phosphor", "tabler")):
            continue
        stem = p.stem
        if stem in seen_stems:
            continue
        tt = None
        try:
            tt = open_ttfont_safe(p, font_number=0, lazy=False)
            cmap = tt.getBestCmap() or {}
            if ord("A") not in cmap and ord("a") not in cmap and ord("0") not in cmap:
                continue
            wght = int(getattr(tt["OS/2"], "usWeightClass", 400) or 400) if "OS/2" in tt else 400
            is_ital = ("italic" in low) or ("ital" in low)
            fam_grp = re.sub(r"[-_].*$", "", stem)
            candidates.append((stem, p, fam_grp, wght, is_ital))
            seen_stems.add(stem)
        except Exception:
            continue
        finally:
            if tt is not None:
                try:
                    tt.close()
                except Exception:
                    pass
    return candidates


def _render_hq_reference_map(ft: ctypes.CDLL, ft_lib: ctypes.c_void_p, font_path: Path, size_px: int, codepoints: Sequence[int]) -> Dict[int, np.ndarray]:
    """Render 8x unhinted grayscale reference masters for structural IoU evaluation."""
    from humid1_ft_raster import _convert_bdf_to_cached_ttf
    eff_path = _convert_bdf_to_cached_ttf(font_path) if font_path.suffix.lower() == ".bdf" else font_path
    hq_face = ctypes.POINTER(FT_FaceRec)()
    out: Dict[int, np.ndarray] = {}
    if ft.FT_New_Face(ft_lib, str(eff_path).encode("utf-8"), 0, ctypes.byref(hq_face)) != 0:
        return out
    ft.FT_Set_Pixel_Sizes(hq_face, 0, int(size_px * 8))
    flags = FT_LOAD_RENDER | FT_LOAD_NO_HINTING | FT_LOAD_TARGET_NORMAL
    for cp in codepoints:
        gidx = ft.FT_Get_Char_Index(hq_face, cp)
        if gidx == 0 or ft.FT_Load_Glyph(hq_face, gidx, flags) != 0:
            continue
        slot = hq_face.contents.glyph.contents
        bmp = slot.bitmap
        if bmp.rows <= 0 or bmp.width <= 0:
            continue
        pitch = abs(int(bmp.pitch))
        raw_b = ctypes.string_at(bmp.buffer, bmp.rows * pitch)
        arr = np.frombuffer(raw_b, dtype=np.uint8).reshape((bmp.rows, pitch))[:, :bmp.width].copy()
        ys, xs = np.nonzero(arr > 16)
        if len(xs) > 0:
            out[cp] = arr[int(ys.min()) : int(ys.max()) + 1, int(xs.min()) : int(xs.max()) + 1]
    ft.FT_Done_Face(hq_face)
    return out


def _render_per_font_9pipeline_sheet(
    sheet_path: Path,
    summary: FontEvalSummary,
    strikes_by_pipe_sz: Dict[str, Dict[int, List[GlyphStrike]]],
    sizes: Sequence[int],
) -> None:
    """Render a visual comparison sheet showing all 9 conversion pipelines across all evaluated sizes."""
    W = 1560
    pipe_row_heights = {sz: max(28, sz + 8) for sz in sizes}
    size_block_heights = {sz: 44 + len(CANONICAL_PIPELINES) * pipe_row_heights[sz] + 14 for sz in sizes}
    H = 114 + sum(size_block_heights.values()) + 30
    img = Image.new("RGB", (W, H), (246, 248, 252))
    draw = ImageDraw.Draw(img)
    f_default = ImageFont.load_default()

    draw.rectangle([0, 0, W, 78], fill=(18, 24, 34))
    draw.text(
        (24, 14),
        f"EPD-FONT v{TOOL_VERSION} 9-PIPELINE EVALUATION  |  {summary.label} ({summary.font_file}, wght={summary.weight_class}, gamma={summary.gamma:.2f})",
        fill=(255, 255, 255),
        font=f_default,
    )
    floors_str = " | ".join(
        f"{p}:{summary.floor_by_pipeline.get(p, 24)}px({summary.score_16px_by_pipeline.get(p, 0):.1f})"
        for p in CANONICAL_PIPELINES
    )
    draw.text(
        (24, 44),
        f"Best @ 16px: {summary.best_pipeline} ({summary.best_pipeline_score_16px:.1f})  •  {floors_str}",
        fill=(180, 200, 224),
        font=f_default,
    )

    y = 92
    for sz in sizes:
        size_block_h = size_block_heights[sz]
        pipe_row_h = pipe_row_heights[sz]
        draw.rectangle([20, y, W - 20, y + size_block_h - 10], fill=(255, 255, 255), outline=(208, 216, 226), width=1)
        draw.rectangle([20, y, W - 20, y + 26], fill=(234, 240, 248))
        draw.text((32, y + 6), f"STRIKE SIZE: {sz} px   |   Specimen: \"{EVAL_SPECIMEN_STRING}\"", fill=(20, 28, 40), font=f_default)

        ry = y + 34
        for p_name in CANONICAL_PIPELINES:
            pm = summary.by_pipeline_size.get(p_name, {}).get(sz)
            glist = strikes_by_pipe_sz.get(p_name, {}).get(sz, [])
            gmap = {g.codepoint: g for g in glist}

            status_col = (18, 128, 78) if (pm and pm.passes_floor) else (175, 55, 45)
            m_txt = (
                f"{p_name:<15} | Score:{pm.composite_score:5.1f} | HQ:{pm.hq_conf_pct:5.1f}% | "
                f"Stem:{pm.mean_stem_width_px:4.2f}px (>=2px:{pm.stem_2px_pct:5.1f}%) | Cnt:{pm.counter_pct:5.1f}%"
                if pm else f"{p_name:<15}"
            )
            draw.text((32, ry + max(4, (pipe_row_h - 12) // 2)), m_txt, fill=status_col, font=f_default)

            # Render 1:1 specimen string at x=590
            cx = 590
            by = ry + max(14, int(sz * 0.85))
            for ch in EVAL_SPECIMEN_STRING:
                g = gmap.get(ord(ch))
                if not g:
                    cx += max(3, sz // 3)
                    continue
                if g.box_w > 0 and g.box_h > 0 and cx + g.box_w < W - 36:
                    gx0 = cx + g.ofs_x
                    gy0 = by - (g.ofs_y + g.box_h)
                    for rr, r_str in enumerate(g.rows):
                        for cc, px in enumerate(r_str):
                            if px == "#":
                                draw.point((gx0 + cc, gy0 + rr), fill=(12, 16, 22))
                cx += max(1, (g.adv_w_fp4 + 8) >> 4)

            ry += pipe_row_h
        y += size_block_h

    sheet_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(sheet_path))


def _worker_evaluate_font(task: dict) -> FontEvalSummary:
    """ProcessPoolExecutor worker that evaluates a single font across ALL 9 pipelines and all sizes."""
    ft, ft_lib = load_freetype()
    font_path = Path(task["font_path"])
    label = task["label"]
    family_group = task["family_group"]
    weight_class = int(task["weight_class"])
    is_italic = bool(task["is_italic"])
    sizes: List[int] = list(task["sizes"])
    threshold = int(task["threshold"])
    gamma = float(task.get("gamma", 1.0))
    sheets_dir = Path(task["sheets_dir"])

    bench_cps = sorted(set(ord(c) for c in (EVAL_BENCHMARK_CHARS + " ")))
    by_pipeline_size: Dict[str, Dict[int, PipelineSizeMetrics]] = {p: {} for p in CANONICAL_PIPELINES}
    strikes_by_pipe_sz: Dict[str, Dict[int, List[GlyphStrike]]] = {p: {} for p in CANONICAL_PIPELINES}

    for sz in sizes:
        hq_map = _render_hq_reference_map(ft, ft_lib, font_path, sz, bench_cps)
        for p_name in CANONICAL_PIPELINES:
            glyphs, _, _, _, _, _ = rasterize_font_strike(
                ft=ft,
                ft_lib=ft_lib,
                font_path=font_path,
                size_px=sz,
                codepoints=bench_cps,
                pipeline=p_name,
                threshold=threshold,
                gamma=gamma,
                enable_kerning=False,
            )
            strikes_by_pipe_sz[p_name][sz] = glyphs
            gmap = {g.codepoint: g for g in glyphs}

            hq_confs: List[float] = []
            hq_diffs: List[float] = []
            stem_ge2_list: List[float] = []
            stem_widths: List[float] = []
            ink_total = 0
            cnt_ok = 0
            cnt_tot = 0

            for ch in EVAL_BENCHMARK_CHARS:
                cp = ord(ch)
                g = gmap.get(cp)
                if g is None or g.box_w == 0 or g.box_h == 0 or not g.rows:
                    hq_confs.append(0.0)
                    hq_diffs.append(100.0)
                    stem_ge2_list.append(0.0)
                    stem_widths.append(0.0)
                    if ch in CANONICAL_MIN_HOLES:
                        cnt_tot += 1
                    continue

                arr = rows_to_binary_array(g.rows)
                ink_total += int(np.count_nonzero(arr))
                _, _, mw, gr = measure_stem_metrics(arr)
                stem_ge2_list.append(gr * 100.0)
                stem_widths.append(mw)

                hq_c, hq_d, _, _ = compute_upscaled_hq_metrics(arr, hq_map.get(cp))
                hq_confs.append(hq_c)
                hq_diffs.append(hq_d)

                if ch in CANONICAL_MIN_HOLES:
                    cnt_tot += 1
                    _, b1 = compute_betti_numbers(arr)
                    exp_b1 = CANONICAL_MIN_HOLES[ch]
                    if b1 >= exp_b1:
                        cnt_ok += 1

            mean_hq = float(np.mean(hq_confs)) if hq_confs else 0.0
            mean_diff = float(np.mean(hq_diffs)) if hq_diffs else 100.0
            mean_ge2 = float(np.mean(stem_ge2_list)) if stem_ge2_list else 0.0
            mean_sw = float(np.mean(stem_widths)) if stem_widths else 0.0
            cnt_pct = (float(cnt_ok) / float(max(1, cnt_tot))) * 100.0

            is_bitmap_f = "terminus" in label.lower()
            passes = (cnt_pct >= 88.0 and (mean_ge2 >= 65.0 or is_bitmap_f) and mean_hq >= 62.0)
            comp_score = 0.40 * mean_hq + 0.35 * cnt_pct + 0.25 * mean_ge2

            by_pipeline_size[p_name][sz] = PipelineSizeMetrics(
                pipeline=p_name,
                size_px=sz,
                threshold=threshold,
                gamma=gamma,
                hq_conf_pct=round(mean_hq, 2),
                hq_diff_pct=round(mean_diff, 2),
                stem_2px_pct=round(mean_ge2, 2),
                counter_pct=round(cnt_pct, 2),
                mean_stem_width_px=round(mean_sw, 2),
                ink_pixels=ink_total,
                total_glyphs=len(glyphs),
                passes_floor=passes,
                composite_score=round(comp_score, 2),
            )

    ref_sz = 16 if 16 in sizes else sizes[len(sizes) // 2]
    floor_by_pipe: Dict[str, int] = {}
    score_16_by_pipe: Dict[str, float] = {}
    for p_name in CANONICAL_PIPELINES:
        passing_szs = [s for s in sorted(sizes) if by_pipeline_size[p_name][s].passes_floor]
        floor_by_pipe[p_name] = passing_szs[0] if passing_szs else (max(sizes) + 2)
        score_16_by_pipe[p_name] = by_pipeline_size[p_name][ref_sz].composite_score

    best_pipe = max(CANONICAL_PIPELINES, key=lambda p: score_16_by_pipe[p])
    sheet_png_path = sheets_dir / f"{label}_eval.png"

    summary = FontEvalSummary(
        label=label,
        font_file=font_path.name,
        file_type=font_path.suffix.lower(),
        family_group=family_group,
        weight_class=weight_class,
        is_italic=is_italic,
        threshold=threshold,
        gamma=gamma,
        best_pipeline=best_pipe,
        best_pipeline_score_16px=score_16_by_pipe[best_pipe],
        floor_by_pipeline=floor_by_pipe,
        score_16px_by_pipeline=score_16_by_pipe,
        by_pipeline_size=by_pipeline_size,
        sheet_png=str(sheet_png_path.name),
    )
    _render_per_font_9pipeline_sheet(sheet_png_path, summary, strikes_by_pipe_sz, sizes)
    return summary


def render_master_comparison_sheet(
    out_png: Path,
    summaries: Sequence[FontEvalSummary],
    sizes: Sequence[int],
) -> Path:
    """Render the master 9-pipeline comparison scorecard PNG."""
    ref_sz = 16 if 16 in sizes else sizes[len(sizes) // 2]
    row_h = 34
    W = 1920
    H = max(320, 110 + len(summaries) * row_h + 30)
    img = Image.new("RGB", (W, H), (246, 248, 252))
    draw = ImageDraw.Draw(img)
    f_def = ImageFont.load_default()

    draw.rectangle([0, 0, W, 72], fill=(18, 24, 34))
    draw.text(
        (24, 14),
        f"HUMIDYNE LABS / HUMIDITRON epd-font v{TOOL_VERSION}  |  MASTER 9-PIPELINE FONT EVALUATION SCORECARD (@ {ref_sz}px)",
        fill=(255, 255, 255),
        font=f_def,
    )
    draw.text(
        (24, 40),
        f"Comparing {', '.join(CANONICAL_PIPELINES)} across {len(summaries)} evaluated font cuts & sizes {list(sizes)}",
        fill=(180, 200, 224),
        font=f_def,
    )

    y = 84
    for idx, s in enumerate(sorted(summaries, key=lambda x: -x.best_pipeline_score_16px)):
        bg = (255, 255, 255) if (idx % 2 == 0) else (238, 243, 250)
        draw.rectangle([20, y, W - 20, y + row_h - 4], fill=bg, outline=(212, 220, 232), width=1)
        cols_txt = " | ".join(
            f"{p}:{s.score_16px_by_pipeline.get(p, 0):4.1f}({s.floor_by_pipeline.get(p, 24)}px)"
            for p in CANONICAL_PIPELINES
        )
        draw.text(
            (30, y + 9),
            f"#{idx+1:>2d} {s.label:<30} [{s.file_type:<4} w{s.weight_class:<3d}] | Best:{s.best_pipeline:<15}({s.best_pipeline_score_16px:5.1f}) | {cols_txt}",
            fill=(20, 28, 40),
            font=f_def,
        )
        y += row_h

    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out_png))
    return out_png


def generate_markdown_report(summaries: Sequence[FontEvalSummary], sizes: Sequence[int], threshold: int, gamma: float) -> str:
    ref_sz = 16 if 16 in sizes else sizes[len(sizes) // 2]
    pipe_headers = " | ".join(f"`{p}` (`Score` / `Floor` / `Cnt%`)" for p in CANONICAL_PIPELINES)
    pipe_align = " | ".join(":---" for _ in CANONICAL_PIPELINES)
    lines = [
        f"# `epd-font` v{TOOL_VERSION} — 9-Pipeline Multi-Font & Multi-Size Evaluation Report",
        "",
        f"- **Project**: {PROJECT_TAGLINE}",
        f"- **Repository**: [Humidyne-Labs/epd-font](https://github.com/Humidyne-Labs/epd-font) (`v{TOOL_VERSION}`)",
        "- **Authors**: [Humiditron](https://github.com/humiditron) & AI/LLM Collaborative Development Partner",
        f"- **Evaluated Pixel Sizes**: `{list(sizes)}` px",
        f"- **Binarization Threshold & Gamma**: `threshold={threshold}`, `gamma={gamma:.2f}` (Linear Grayscale)",
        f"- **Evaluated Resolution-Reduction Pipelines**: `{', '.join(CANONICAL_PIPELINES)}`",
        "",
        f"## 1. Master 9-Pipeline Scorecard Summary (`@ {ref_sz} px` & Viable Size Floors)",
        "",
        f"| Rank | Font Cut (`File Type`) | Weight | Best Pipeline (`@ {ref_sz}px`) | {pipe_headers} |",
        f"| ---: | :--- | ---: | :--- | {pipe_align} |",
    ]

    for idx, s in enumerate(sorted(summaries, key=lambda x: -x.best_pipeline_score_16px), 1):
        cells = []
        for p in CANONICAL_PIPELINES:
            pm = s.by_pipeline_size.get(p, {}).get(ref_sz)
            cnt_s = f"{pm.counter_pct:.1f}%" if pm else "N/A"
            cells.append(f"`{s.score_16px_by_pipeline.get(p, 0):.1f}` / `{s.floor_by_pipeline.get(p, 24)}px` / `{cnt_s}`")
        lines.append(
            f"| {idx} | `{s.font_file}` (`{s.file_type}`) | `{s.weight_class}` | **`{s.best_pipeline}` (`{s.best_pipeline_score_16px:.1f}`)** | {' | '.join(cells)} |"
        )

    lines.extend([
        "",
        "## 2. Per-Font, Per-Size Detailed 9-Pipeline Breakdown",
        "",
        "| Font Cut | Size (`px`) | Pipeline | Composite Score | 8x HQ IoU (`%`) | `>=2px` Stems (`%`) | Mean Stem (`px`) | Open Counters (`%`) | Ink Pixels | Floor Status |",
        "| :--- | ---: | :--- | ---: | ---: | ---: | ---: | ---: | ---: | :--- |",
    ])
    for s in summaries:
        for sz in sizes:
            for p in CANONICAL_PIPELINES:
                pm = s.by_pipeline_size.get(p, {}).get(sz)
                if not pm:
                    continue
                st_lbl = "PASS" if pm.passes_floor else "BELOW_FLOOR"
                lines.append(
                    f"| `{s.label}` | `{sz}px` | `{p}` | `{pm.composite_score:.2f}` | `{pm.hq_conf_pct:.1f}%` | "
                    f"`{pm.stem_2px_pct:.1f}%` | `{pm.mean_stem_width_px:.2f}px` | `{pm.counter_pct:.1f}%` | "
                    f"`{pm.ink_pixels}` | `{st_lbl}` |"
                )
    return "\n".join(lines) + "\n"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="humid1_font_eval.py",
        description=(
            f"Humidyne Labs / Humiditron `epd-font` v{TOOL_VERSION} — 9-Pipeline Multi-Font & Multi-Size Evaluator.\n"
            f"Evaluates all 9 bilevel conversion methods ({', '.join(CANONICAL_PIPELINES)})\n"
            "per font and per pixel size."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--src-dir", type=str, default=None, help="Directory containing .ttf/.otf/.ttc/.bdf fonts to evaluate (searched recursively)")
    parser.add_argument("--out-dir", type=str, required=True, help="Output directory inside build/ for evaluation reports & PNG sheets (required)")
    parser.add_argument("--fonts", type=str, nargs="*", default=None, help="Optional explicit list of .ttf/.otf/.ttc/.bdf font paths to evaluate")
    parser.add_argument("--sizes", type=int, nargs="+", default=[10, 12, 14, 16, 20, 24], help="Pixel sizes to benchmark (default: 10 12 14 16 20 24)")
    parser.add_argument("--threshold", type=int, default=128, help="Binarization threshold 1..254 (default: 128)")
    parser.add_argument("--gamma", type=float, default=1.0, help="Linear grayscale gamma factor in [0.1..5.0] (default: 1.0)")
    parser.add_argument("-H", "--hw-scheme", type=str, default=None, help="Optional hardware scheme JSON file (e.g. esp32s3-N8R8-hw_scheme.json or generic_hw.json)")
    parser.add_argument("--accel", choices=["auto", "cpu", "gpu", "hybrid", "sync"], default=None, help="Hardware math acceleration backend (default: auto or from EPD_FONT_ACCEL)")
    parser.add_argument("-j", "--jobs", type=int, default=None, help="Number of parallel CPU worker processes")
    parser.add_argument("--update-docs", action="store_true", help="Also write a versioned FONT_EVAL_BENCHMARK_v*.md copy inside --out-dir")
    return parser


def main() -> None:
    install_clean_signal_handlers()
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent if script_dir.name == "fonts" else script_dir.parent
    parser = build_arg_parser()

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        fail_gracefully("Missing required arguments (`--src-dir` or `--fonts`, and `--out-dir`).")

    args = parser.parse_args()
    if not args.src_dir and not args.fonts:
        fail_gracefully("Provide either `--src-dir <directory>` or `--fonts <file1> <file2> ...`.")
    if not (1 <= args.threshold <= 254):
        fail_gracefully(f"Invalid `--threshold {args.threshold}`. Must be in [1..254].")
    if not (0.1 <= args.gamma <= 5.0):
        fail_gracefully(f"Invalid `--gamma {args.gamma}`. Must be in [0.1..5.0].")

    src_dir = require_valid_path(args.src_dir, "--src-dir", must_exist=True, expect_dir=True) if args.src_dir else repo_root
    out_dir = Path(args.out_dir).expanduser().resolve()
    sheets_dir = out_dir / "sheets"
    out_dir.mkdir(parents=True, exist_ok=True)
    sheets_dir.mkdir(parents=True, exist_ok=True)

    candidates = discover_candidate_fonts(src_dir, args.fonts)
    if not candidates:
        fail_gracefully(f"No evaluable Latin .ttf/.otf/.ttc/.bdf fonts found in `{src_dir}`.")

    if args.hw_scheme:
        hw_spec = load_and_validate_hardware_scheme(
            scheme_cfg={},
            hw_scheme_cli=args.hw_scheme,
            repo_root=repo_root,
            scheme_path=None,
        )
        print(f"[+] Loaded hardware scheme: {hw_spec.hw_scheme_id} ({hw_spec.chip_name}, {hw_spec.partition_label} partition)")

    eff_accel = getattr(args, "accel", None) or os.environ.get("EPD_FONT_ACCEL") or "auto"
    os.environ["EPD_FONT_ACCEL"] = eff_accel
    if eff_accel == "cpu":
        os.environ["OPENCV_OPENCL_RUNTIME"] = "disabled"
        try:
            import cv2
            if hasattr(cv2, "ocl"):
                cv2.ocl.setUseOpenCL(False)
        except Exception:
            pass
    select_math_backend("auto" if eff_accel == "sync" else eff_accel)
    hw_info = detect_host_hardware(args.jobs)
    print(f"[*] Active Mathematical Backend: {describe_math_backend()}")
    max_workers = 1 if eff_accel == "sync" else hw_info.recommended_workers
    print(
        f"[*] Evaluating {len(candidates)} font cuts across sizes {args.sizes} and ALL {len(CANONICAL_PIPELINES)} pipelines "
        f"({', '.join(CANONICAL_PIPELINES)} @ threshold={args.threshold}, gamma={args.gamma:.2f}) using {max_workers} worker(s)..."
    )

    t0 = time.perf_counter()
    max_eval_sz = max(args.sizes) if args.sizes else 24
    tasks = [
        {
            "label": lbl,
            "font_path": str(fpath),
            "family_group": fg,
            "weight_class": wght,
            "is_italic": is_it,
            "sizes": list(args.sizes),
            "sz": max_eval_sz,
            "run_all_methods": True,
            "threshold": args.threshold,
            "gamma": args.gamma,
            "sheets_dir": str(sheets_dir),
        }
        for (lbl, fpath, fg, wght, is_it) in candidates
    ]

    summaries: List[FontEvalSummary] = run_parallel_tasks(_worker_evaluate_font, tasks, max_workers=max_workers, math_backend=eff_accel)
    for idx, s in enumerate(summaries, 1):
        scores_str = " | ".join(f"{p}={s.score_16px_by_pipeline.get(p, 0):.1f}(fl:{s.floor_by_pipeline.get(p, 24)}px)" for p in CANONICAL_PIPELINES)
        print(f"    [{idx:>3}/{len(summaries):<3}] {s.label:34s} [{s.file_type:<4}] | Best: {s.best_pipeline:<15} | {scores_str}")

    md_report = generate_markdown_report(summaries, args.sizes, args.threshold, args.gamma)
    md_path = out_dir / "font_eval_report.md"
    md_path.write_text(md_report, encoding="utf-8")

    if args.update_docs:
        audit_md_path = out_dir / f"FONT_EVAL_BENCHMARK_v{TOOL_VERSION}.md"
        audit_md_path.write_text(md_report, encoding="utf-8")

    csv_path = out_dir / "font_eval_report.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as cf:
        writer = csv.writer(cf)
        writer.writerow([
            "label", "font_file", "file_type", "family_group", "weight_class", "is_italic",
            "size_px", "pipeline", "threshold", "gamma", "composite_score", "hq_conf_pct", "hq_diff_pct",
            "stem_2px_pct", "mean_stem_width_px", "counter_pct", "ink_pixels", "passes_floor",
        ])
        for s in summaries:
            for sz in args.sizes:
                for p in CANONICAL_PIPELINES:
                    pm = s.by_pipeline_size.get(p, {}).get(sz)
                    if pm:
                        writer.writerow([
                            s.label, s.font_file, s.file_type, s.family_group, s.weight_class, s.is_italic,
                            sz, p, pm.threshold, pm.gamma, pm.composite_score, pm.hq_conf_pct, pm.hq_diff_pct,
                            pm.stem_2px_pct, pm.mean_stem_width_px, pm.counter_pct, pm.ink_pixels, pm.passes_floor,
                        ])

    json_path = out_dir / "font_eval_report.json"
    json_path.write_text(json.dumps([asdict(s) for s in summaries], indent=2) + "\n", encoding="utf-8")

    comp_png = out_dir / "font_eval_comparison_sheet.png"
    render_master_comparison_sheet(comp_png, summaries, args.sizes)

    elapsed = time.perf_counter() - t0
    print(f"[+] Wrote {len(summaries)} Per-Font 9-Pipeline PNG Sheets -> {sheets_dir}")
    print(f"[+] Wrote Master 9-Pipeline Scorecard PNG         -> {comp_png}")
    print(f"[+] Wrote Evaluation Markdown, CSV & JSON Reports -> {md_path} ({elapsed:.2f}s)")


if __name__ == "__main__":
    try:
        main()
    finally:
        teardown_math_backends()
