#!/usr/bin/env python3
"""
humid1_font_eval.py (v1.0.17)
=============================
Humidyne Labs / Humiditron `epd-font` Multi-Core Font & Weight Evaluation Suite,
Tri-Role Visual Contrast Triad Scorer (`Normal` + `Bold Punch` + `Subtle Italic`),
Pre-Tune vs. Post-Tune Traceability Engine & Per-Font Visual Sheet Generator.

Repository : https://github.com/Humidyne-Labs/epd-font
Target OS  : https://github.com/Humidyne-Labs/H1OS
License    : MIT License

What's New in v1.0.17:
----------------------
1. Tri-Role Visual Contrast Triad Scorer (`evaluate_family_triads`):
   Fixes the v1.0.15 single-font isolated scoring bias that caused `Normal (w600)`,
   `Bold (w700)`, and `Italic (w800)` to converge to visually indistinguishable `~2.3px–2.5px`
   stems (`+6.5%` Bold delta, with Italic heavier than Bold).
   In v1.0.17, typefaces are scored both per-role (`compute_role_aware_epd_score`) and as
   **3-Role Family Triads (`Normal` + `Bold Punch` + `Subtle Iso-Weight Italic`)**:
     - `NORMAL (BODY)`   : Clean `2.00px–2.25px` stem (`w400–w500`), leaving headroom for Bold.
     - `BOLD (PUNCH)`    : True `2.90px–3.45px` stem (`w800 ExtraBold` / `w900 Black`), delivering
                           `+35% to +65%` more ink mass and a `+0.85px to +1.45px` integer stem jump
                           over `Normal` while maintaining `>=95%` open counters.
     - `ITALIC (SUBTLE)` : Iso-weight slanted cursive emphasis (`w500 MediumItalic` / `w600 SemiBoldItalic`),
                           within `[-10% .. +12%]` of `Normal` ink mass and `>=25%` lighter than `Bold`
                           so Italic whispers nuance while Bold punches attention!
2. Dedicated Tri-Role Visual Contrast Sheet (`build/font_eval/font_eval_triad_contrast_sheet.png`):
   Stacks `NORMAL (BODY)`, `BOLD (PUNCH)`, and `ITALIC (SUBTLE)` directly on top of one another
   for every evaluated family across `14px`, `16px`, and `20px` with live Ink-Punch (`+%`),
   Stem-Jump (`+px`), and 2x-zoomed glyph triad strips (`H B a e g s w $`).
3. Multi-Corpus JSON Re-Digest Mode (`--re-digest-json`):
   Can directly ingest and re-evaluate existing `font_eval_report.json` datasets (e.g., 425-font
   multi-archive runs) under the v1.0.17 Tri-Role Visual Contrast Triad Scorer.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import ctypes
import json
import math
import os
import re
import sys
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from fontTools.ttLib import TTFont
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
    open_ttfont_safe,
    rasterize_font_strike,
)

TOOL_VERSION = "1.0.17"

# Diagnostic benchmark character set (57 critical glyphs: counters, multi-valley diagonals, paired brackets, symbols)
EVAL_BENCHMARK_CHARS = "0124689ABCDHIJMNOPQRWabcefghijlmnoqrstvwxyz$%&()[]{}/\\|!<>+="
EVAL_COUNTER_CHARS = set("04689ABDOPQRabdegopq$%&")
EVAL_SPECIMEN_STRING = "H1OS v1.0.17 (08B$) [aeg] {WwMm} <=>"
EVAL_ZOOM_STRIP_CHARS = "WwMmABCfgrs$()[]08"
TRIAD_ZOOM_CHARS = "HBaegsw$"


@dataclass
class SizeMetrics:
    size_px: int
    raw_hq_conf_pct: float
    tuned_hq_conf_pct: float
    raw_hq_diff_pct: float
    tuned_hq_diff_pct: float
    raw_stem_2px_pct: float
    tuned_stem_2px_pct: float
    raw_counter_pct: float
    tuned_counter_pct: float
    mean_stem_width_raw_px: float
    mean_stem_width_tuned_px: float
    raw_ink_pixels: int
    tuned_ink_pixels: int
    repaired_glyphs: int
    total_glyphs: int
    tuning_burden_pct: float
    passes_floor_raw: bool
    passes_floor_tuned: bool


@dataclass
class FontEvalSummary:
    label: str
    font_file: str
    family_group: str
    weight_class: int
    is_italic: bool
    size_floor_raw_px: int
    size_floor_tuned_px: int
    mean_16px_tuning_burden_pct: float
    mean_16px_raw_hq_conf_pct: float
    mean_16px_tuned_hq_conf_pct: float
    recommendation_tier: str
    intended_role: str = "NORMAL (BODY)"
    role_fit_score: float = 0.0
    sheet_png: str = ""
    by_size: Dict[int, SizeMetrics] = field(default_factory=dict)


@dataclass
class FamilyTriadSummary:
    family_stem: str
    family_group: str
    normal_label: str
    normal_file: str
    normal_weight: int
    normal_stem_16px: float
    normal_ink_16px: int
    normal_hq_16px: float
    bold_label: str
    bold_file: str
    bold_weight: int
    bold_stem_16px: float
    bold_ink_16px: int
    bold_cnt_16px: float
    italic_label: str
    italic_file: str
    italic_weight: int
    italic_stem_16px: float
    italic_ink_16px: int
    italic_cnt_16px: float
    bold_ink_jump_pct: float
    bold_stem_jump_px: float
    italic_ink_delta_pct: float
    bold_over_italic_pct: float
    triad_contrast_score: float
    triad_verdict: str


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


def _clone_glyph(g: GlyphStrike) -> GlyphStrike:
    c = GlyphStrike(
        codepoint=g.codepoint,
        glyph_id=g.glyph_id,
        adv_w_fp4=g.adv_w_fp4,
        box_w=g.box_w,
        box_h=g.box_h,
        ofs_x=g.ofs_x,
        ofs_y=g.ofs_y,
        rows=list(g.rows) if g.rows else [],
    )
    c.patched = g.patched
    return c


def inspect_font_metadata(font_path: Path) -> Optional[Tuple[str, str, int, bool]]:
    """
    Inspect a `.ttf`, `.otf`, or `.ttc` file to verify it contains ASCII Latin glyphs ('A'..'z')
    and extract `(display_label, family_group, weight_class, is_italic)`.
    Returns `None` for pure PUA icon fonts or unreadable files.
    """
    fname_low = font_path.name.lower()
    if any(ic in fname_low for ic in ("fontawesome", "lucide", "phosphor", "tabler")):
        return None
    if fname_low.startswith("terminus-") and not any(
        fname_low.startswith(p) for p in ("terminus-normal-16", "terminus-bold-16")
    ):
        return None

    weight_class = 400
    is_italic = ("italic" in fname_low) or fname_low.endswith("it.ttf") or fname_low.endswith("it.otf")
    family_name = font_path.stem

    try:
        tt = open_ttfont_safe(font_path, font_number=0, lazy=True)
        cmap = tt.getBestCmap() or {}
        if not (0x0041 in cmap and 0x0057 in cmap and 0x0061 in cmap):
            tt.close()
            return None
        if "OS/2" in tt:
            weight_class = int(getattr(tt["OS/2"], "usWeightClass", 400) or 400)
            fs_sel = int(getattr(tt["OS/2"], "fsSelection", 0) or 0)
            if fs_sel & 0x01:
                is_italic = True
        if "name" in tt:
            fam_rec = tt["name"].getDebugName(1) or ""
            sub_rec = tt["name"].getDebugName(2) or ""
            full_rec = tt["name"].getDebugName(4) or ""
            if full_rec:
                family_name = full_rec.strip()
            elif fam_rec:
                family_name = f"{fam_rec.strip()} {sub_rec.strip()}".strip()
        tt.close()
    except Exception:
        return None

    if weight_class == 400:
        if "extrabold" in fname_low or "xbd" in fname_low or "extrabd" in fname_low:
            weight_class = 800
        elif "black" in fname_low or "heavy" in fname_low or "xblk" in fname_low or "blk" in fname_low:
            weight_class = 900
        elif "semibold" in fname_low or "smbd" in fname_low or "semibd" in fname_low:
            weight_class = 600
        elif "bold" in fname_low or "-bd" in fname_low:
            weight_class = 700
        elif "medium" in fname_low or "-med" in fname_low:
            weight_class = 500
        elif "extralight" in fname_low:
            weight_class = 200
        elif "light" in fname_low or "-lt" in fname_low:
            weight_class = 300
        elif "thin" in fname_low:
            weight_class = 100

    if "mono" in fname_low or "iosevka" in fname_low:
        fam_group = "mono"
    elif "serif" in fname_low or "literata" in fname_low or "etoile" in fname_low:
        fam_group = "serif"
    elif "cond" in fname_low:
        fam_group = "cond"
    elif "math" in fname_low:
        fam_group = "math"
    elif "terminus" in fname_low:
        fam_group = "terminus"
    else:
        fam_group = "sans"

    label = f"{font_path.stem} (w{weight_class})"
    return label, fam_group, weight_class, is_italic


def discover_candidate_fonts(
    src_dir: Path,
    explicit_fonts: Optional[Sequence[str]] = None,
) -> List[Tuple[str, Path, str, int, bool]]:
    """
    Discover candidate fonts to benchmark:
      - If `explicit_fonts` is provided, evaluates those exact font files.
      - If `src_dir` is `build/static_ttfs` (the internal foundry asset dir), evaluates the
        canonical Humid1 Tri-Role benchmark suite (including Normal, Bold Punch, and Subtle Italic
        cuts across Sans, Condensed, Mono, Serif, Math, Terminus, and Inter).
      - If `src_dir` is an external directory (such as `eval_fonts`), recursively scans all
        `.ttf`, `.otf`, and `.ttc` files inside `src_dir`.
    """
    candidates: List[Tuple[str, Path, str, int, bool]] = []
    if explicit_fonts:
        for fp_str in explicit_fonts:
            fp = Path(fp_str).resolve()
            if fp.is_file():
                meta = inspect_font_metadata(fp)
                if meta:
                    lbl, fg, wght, is_it = meta
                    candidates.append((lbl, fp, fg, wght, is_it))
        return candidates

    is_internal_static = (src_dir / "IBMPlexSans-ExtraBold.ttf").is_file() and (src_dir / "Terminus-Normal-16.ttf").is_file()
    if is_internal_static:
        default_specs = [
            # Sans Tri-Role Candidates
            ("IBM Plex Sans Regular (w400)", src_dir / "IBMPlexSans-Regular.ttf", "sans", 400, False),
            ("IBM Plex Sans Normal [Medium w500]", src_dir / "IBMPlexSans-Medium.ttf", "sans", 500, False),
            ("IBM Plex Sans SemiBold (w600)", src_dir / "IBMPlexSans-SemiBold.ttf", "sans", 600, False),
            ("IBM Plex Sans Bold-700 [Legacy w700]", src_dir / "IBMPlexSans-Bold.ttf", "sans", 700, False),
            ("IBM Plex Sans Bold [ExtraBold w800]", src_dir / "IBMPlexSans-ExtraBold.ttf", "sans", 800, False),
            ("IBM Plex Sans Italic [MedItal w500]", src_dir / "IBMPlexSans-MediumItalic.ttf", "sans", 500, True),
            ("IBM Plex Sans Italic [SemiBoldItal w600]", src_dir / "IBMPlexSans-SemiBoldItalic.ttf", "sans", 600, True),
            ("IBM Plex Sans Bold Italic (w700)", src_dir / "IBMPlexSans-BoldItalic.ttf", "sans", 700, True),
            # Condensed Tri-Role Candidates
            ("IBM Plex Sans Cond Normal [Medium w500]", src_dir / "IBMPlexSansCondensed-Medium.ttf", "cond", 500, False),
            ("IBM Plex Sans Cond Bold [ExtraBold w800]", src_dir / "IBMPlexSansCondensed-ExtraBold.ttf", "cond", 800, False),
            ("IBM Plex Sans Cond Italic [MedItal w500]", src_dir / "IBMPlexSansCondensed-MedItal.ttf", "cond", 500, True),
            ("IBM Plex Sans Cond Italic [SemiBoldItal w600]", src_dir / "IBMPlexSansCondensed-SemiBoldItalic.ttf", "cond", 600, True),
            # Mono Tri-Role Candidates
            ("IBM Plex Mono Normal [Medium w500]", src_dir / "IBMPlexMono-Medium.ttf", "mono", 500, False),
            ("IBM Plex Mono Bold [ExtraBold w800]", src_dir / "IBMPlexMono-ExtraBold.ttf", "mono", 800, False),
            ("IBM Plex Mono Italic [MedItal w500]", src_dir / "IBMPlexMono-MediumItalic.ttf", "mono", 500, True),
            ("IBM Plex Mono Italic [SemiBoldItal w600]", src_dir / "IBMPlexMono-SemiBoldItalic.ttf", "mono", 600, True),
            # Serif Tri-Role Candidates
            ("IBM Plex Serif Normal [Medium w500]", src_dir / "IBMPlexSerif-Medium.ttf", "serif", 500, False),
            ("IBM Plex Serif Bold [ExtraBold w800]", src_dir / "IBMPlexSerif-ExtraBold.ttf", "serif", 800, False),
            ("IBM Plex Serif Italic [MedItal w500]", src_dir / "IBMPlexSerif-MediumItalic.ttf", "serif", 500, True),
            ("IBM Plex Serif Italic [SemiBoldItal w600]", src_dir / "IBMPlexSerif-SemiBoldItalic.ttf", "serif", 600, True),
            # Hinted Google Noto Sans & Width Specialists (v1.0.17)
            ("Noto Sans Normal [Medium w500]", src_dir / "NotoSans-Medium.ttf", "sans", 500, False),
            ("Noto Sans Bold [ExtraBold w800]", src_dir / "NotoSans-ExtraBold.ttf", "sans", 800, False),
            ("Noto Sans Black [Black w900]", src_dir / "NotoSans-Black.ttf", "sans", 900, False),
            ("Noto Sans Italic [MedItal w500]", src_dir / "NotoSans-MediumItalic.ttf", "sans", 500, True),
            ("Noto Sans Italic [SemiBoldItal w600]", src_dir / "NotoSans-SemiBoldItalic.ttf", "sans", 600, True),
            ("Noto Sans SemiCond Normal [Medium w500]", src_dir / "NotoSans-SemiCondensedMedium.ttf", "cond", 500, False),
            ("Noto Sans SemiCond Bold [ExtraBold w800]", src_dir / "NotoSans-SemiCondensedExtraBold.ttf", "cond", 800, False),
            ("Noto Sans SemiCond Black [Black w900]", src_dir / "NotoSans-SemiCondensedBlack.ttf", "cond", 900, False),
            ("Noto Sans SemiCond Italic [SemiBoldItal w600]", src_dir / "NotoSans-SemiCondensedSemiBoldItalic.ttf", "cond", 600, True),
            ("Noto Sans Cond Normal [SemiBold w600]", src_dir / "NotoSans-CondensedSemiBold.ttf", "cond", 600, False),
            ("Noto Sans Cond Bold [Black w900]", src_dir / "NotoSans-CondensedBlack.ttf", "cond", 900, False),
            ("Noto Sans Cond Italic [SemiBoldItal w600]", src_dir / "NotoSans-CondensedSemiBoldItalic.ttf", "cond", 600, True),
            ("Noto Sans Mono Normal [Medium w500]", src_dir / "NotoSansMono-Medium.ttf", "mono", 500, False),
            ("Noto Sans Mono Bold [ExtraBold w800]", src_dir / "NotoSansMono-ExtraBold.ttf", "mono", 800, False),
            ("Noto Sans Mono Black [Black w900]", src_dir / "NotoSansMono-Black.ttf", "mono", 900, False),
            ("Noto Serif Normal [Medium w500]", src_dir / "NotoSerif-Medium.ttf", "serif", 500, False),
            ("Noto Serif Bold [Black w900]", src_dir / "NotoSerif-Black.ttf", "serif", 900, False),
            ("Noto Serif Italic [MedItal w500]", src_dir / "NotoSerif-MediumItalic.ttf", "serif", 500, True),
            ("Noto Serif Italic [SemiBoldItal w600]", src_dir / "NotoSerif-SemiBoldItalic.ttf", "serif", 600, True),
            # Math & Terminus
            ("Noto Sans Math Regular (w400)", src_dir / "NotoSansMath-Regular.ttf", "math", 400, False),
            ("IBM Plex Math Regular (w400)", src_dir / "IBMPlexMath-Regular.ttf", "math", 400, False),
            ("Terminus Native Bitmap (w400)", src_dir / "Terminus-Normal-16.ttf", "terminus", 400, False),
            ("Terminus Bold Bitmap (w700)", src_dir / "Terminus-Bold-16.ttf", "terminus", 700, False),
        ]
        inter_dir = Path("/usr/share/fonts/opentype/inter")
        if (inter_dir / "Inter-Medium.otf").is_file():
            default_specs.extend([
                ("Inter Regular (w400) [External]", inter_dir / "Inter-Regular.otf", "sans", 400, False),
                ("Inter Medium (w500) [External]", inter_dir / "Inter-Medium.otf", "sans", 500, False),
                ("Inter SemiBold (w600) [External]", inter_dir / "Inter-SemiBold.otf", "sans", 600, False),
                ("Inter Bold (w700) [External]", inter_dir / "Inter-Bold.otf", "sans", 700, False),
                ("Inter ExtraBold (w800) [External]", inter_dir / "Inter-ExtraBold.otf", "sans", 800, False),
                ("Inter Black (w900) [External]", inter_dir / "Inter-Black.otf", "sans", 900, False),
                ("Inter MediumItalic (w500) [External]", inter_dir / "Inter-MediumItalic.otf", "sans", 500, True),
                ("Inter SemiBoldItalic (w600) [External]", inter_dir / "Inter-SemiBoldItalic.otf", "sans", 600, True),
            ])
        for lbl, p, fg, wght, is_it in default_specs:
            if p.is_file():
                candidates.append((lbl, p, fg, wght, is_it))
        return candidates

    if not src_dir.exists():
        print(f"[!] Warning: Source font directory does not exist: {src_dir}", file=sys.stderr)
        return []

    all_files: List[Path] = []
    for ext in ("*.ttf", "*.otf", "*.ttc", "*.TTF", "*.OTF", "*.TTC"):
        all_files.extend(src_dir.rglob(ext))
    seen_paths = set()
    for fp in sorted(all_files, key=lambda x: x.name.lower()):
        rp = fp.resolve()
        if rp in seen_paths:
            continue
        seen_paths.add(rp)
        meta = inspect_font_metadata(rp)
        if meta:
            lbl, fg, wght, is_it = meta
            candidates.append((lbl, rp, fg, wght, is_it))
    return candidates


def classify_font_role_and_score(d: FontEvalSummary) -> Tuple[str, float]:
    """
    Classify a font's optimal role in a 3-way 1-BPP hierarchy (`NORMAL (BODY)`, `BOLD (PUNCH)`,
    `ITALIC (SUBTLE)`, `ITALIC (HEAVY)`, `MICRO (1PX BITMAP)`, or `SUB-FLOOR`) and compute its
    role-aware fitness score (`0..100+`).
    """
    m16 = d.by_size.get(16)
    m14 = d.by_size.get(14)
    if not m16:
        return ("UNSCORED", 0.0)

    is_terminus = "terminus" in d.font_file.lower() or d.family_group == "terminus"
    if is_terminus:
        role = "BOLD (2PX BITMAP)" if d.weight_class >= 650 else "MICRO (1PX BITMAP)"
        score = 92.0 if m16.tuned_counter_pct >= 95.0 else 80.0
        return (role, round(score, 1))

    w_stem = m16.mean_stem_width_tuned_px
    cnt16 = m16.tuned_counter_pct
    cnt14 = m14.tuned_counter_pct if m14 else cnt16
    hq16 = m16.tuned_hq_conf_pct
    hq14 = m14.tuned_hq_conf_pct if m14 else hq16
    st16 = m16.tuned_stem_2px_pct
    burden16 = m16.tuning_burden_pct

    if d.weight_class <= 250 or w_stem < 1.65 or hq16 < 50.0:
        return ("SUB-FLOOR (DO NOT USE)", round(max(0.0, hq16 * 0.5), 1))

    if d.is_italic:
        # Subtle Italic role wants iso-weight stems (~2.00px..2.38px, w400..w600) so it whispers emphasis
        # rather than impersonating Bold!
        if d.weight_class <= 600 and 1.95 <= w_stem <= 2.42:
            role = "ITALIC (SUBTLE)"
            stem_ideal_pen = abs(w_stem - 2.20) * 18.0
            score = (
                0.40 * hq16
                + 0.15 * hq14
                + 0.25 * cnt16
                + 0.15 * st16
                - 0.12 * burden16
                + 12.0
                - stem_ideal_pen
            )
        else:
            role = "ITALIC (HEAVY/BLUDGEON)"
            # Penalize heavy BoldItalic/ExtraBoldItalic for standard UI italic role because it collides with Bold
            score = 0.35 * hq16 + 0.20 * cnt16 + 0.15 * st16 - 0.12 * burden16 - 8.0
        return (role, round(score, 1))

    # Upright cuts: distinguish NORMAL (BODY) vs BOLD (PUNCH) vs MID-WEIGHT (HOMOGENEOUS)
    if d.weight_class >= 750 or w_stem >= 2.85:
        role = "BOLD (PUNCH)"
        # Reward true 2.95px..3.45px stem punch + 100% open counters
        punch_bonus = min(18.0, max(0.0, (w_stem - 2.65) * 24.0))
        cnt_pen = max(0.0, (100.0 - cnt16) * 1.5 + (100.0 - cnt14) * 1.0)
        score = (
            0.35 * hq16
            + 0.15 * hq14
            + 0.20 * cnt16
            + 0.15 * st16
            - 0.10 * burden16
            + punch_bonus
            - cnt_pen
        )
    elif 400 <= d.weight_class <= 550 and 1.95 <= w_stem <= 2.30:
        role = "NORMAL (BODY)"
        # Reward clean ~2.12px stem that leaves plenty of contrast headroom for Bold (3.0px+)
        stem_ideal_pen = abs(w_stem - 2.12) * 20.0
        score = (
            0.35 * hq16
            + 0.20 * hq14
            + 0.20 * cnt16
            + 0.15 * st16
            - 0.12 * burden16
            + 14.0
            - stem_ideal_pen
        )
    else:
        # w600 SemiBold / w700 Bold sitting in the ~2.35px..2.65px "Dead Zone" (too heavy for Normal, too light for Bold punch)
        role = "MID-WEIGHT (LOW CONTRAST)"
        score = (
            0.35 * hq16
            + 0.15 * hq14
            + 0.20 * cnt16
            + 0.15 * st16
            - 0.12 * burden16
            - 4.0
        )
    return (role, round(score, 1))


def extract_base_family_stem(font_file: str, family_group: str) -> str:
    """Group font filenames into canonical family stems (preserving width sub-families like SemiCondensed/Condensed) for Tri-Role Triad pairing."""
    stem = Path(font_file).stem
    if stem.lower().startswith("terminus-"):
        return "Terminus"
    m_width = re.match(
        r"^([A-Za-z0-9_]+?-(?:SemiCondensed|ExtraCondensed|Condensed))(?:Thin|ExtraLight|Light|Regular|Text|Medium|SemiBold|Bold|ExtraBold|Black|Heavy|Italic|MedItal|Roman|Normal|VGA)",
        stem,
    )
    if m_width:
        return m_width.group(1)
    m = re.match(
        r"^([A-Za-z0-9_]+?)-(?:Thin|ExtraLight|Light|Regular|Text|Medium|SemiBold|Bold|ExtraBold|Black|Heavy|Italic|MedItal|Roman|Normal|VGA)",
        stem,
    )
    if m:
        return m.group(1)
    return stem.split("-")[0]


def evaluate_family_triads(
    summaries: Sequence[FontEvalSummary],
    ref_sz: int = 16,
) -> List[FamilyTriadSummary]:
    """
    Evaluate and rank complete **Tri-Role Font Family Triads (`Normal` + `Bold Punch` + `Subtle Italic`)**
    so `Normal`, `Bold`, and `Italic` are guaranteed to have unmistakable visual distinction:
      - `Bold` vs `Normal`   : Targets `+35% to +65%` ink mass jump and `+0.80px to +1.45px` stem jump.
      - `Italic` vs `Normal` : Targets `[-10% to +12%]` iso-weight ink mass (subtle slant emphasis)
                               and `>= 25%` lighter than `Bold`!
    """
    by_fam: Dict[str, List[FontEvalSummary]] = defaultdict(list)
    for s in summaries:
        if ref_sz not in s.by_size:
            continue
        fstem = extract_base_family_stem(s.font_file, s.family_group)
        by_fam[fstem].append(s)

    triads: List[FamilyTriadSummary] = []
    for fstem, cuts in sorted(by_fam.items()):
        uprights = [c for c in cuts if not c.is_italic and c.by_size[ref_sz].tuned_ink_pixels > 0]
        italics = [c for c in cuts if c.is_italic and c.by_size[ref_sz].tuned_ink_pixels > 0]
        if len(uprights) < 2:
            continue

        normal_cands = [
            c for c in uprights
            if 380 <= c.weight_class <= 560
            and c.by_size[ref_sz].tuned_counter_pct >= 94.0
            and c.by_size[ref_sz].tuned_stem_2px_pct >= 72.0
        ]
        if not normal_cands:
            normal_cands = [c for c in uprights if c.weight_class <= 600 and c.by_size[ref_sz].tuned_counter_pct >= 90.0]
        if not normal_cands:
            continue

        # Pick Normal closest to ideal ~2.12px stem (or w500 Medium)
        best_norm = max(
            normal_cands,
            key=lambda c: (
                c.by_size[ref_sz].tuned_counter_pct * 0.4
                + c.by_size[ref_sz].tuned_hq_conf_pct * 0.4
                - abs(c.by_size[ref_sz].mean_stem_width_tuned_px - 2.12) * 28.0
                + (4.0 if c.weight_class == 500 else 0.0)
            ),
        )
        m_norm = best_norm.by_size[ref_sz]

        bold_cands = [
            c for c in uprights
            if c.weight_class > best_norm.weight_class
            and c.by_size[ref_sz].tuned_counter_pct >= 94.0
        ]
        if not bold_cands:
            continue

        def _score_bold_pair(b_cut: FontEvalSummary) -> float:
            mb = b_cut.by_size[ref_sz]
            ink_jump = (mb.tuned_ink_pixels - m_norm.tuned_ink_pixels) / float(max(1, m_norm.tuned_ink_pixels)) * 100.0
            stem_jump = mb.mean_stem_width_tuned_px - m_norm.mean_stem_width_tuned_px
            # Ideal Bold Punch: +35%..+62% ink jump, +0.85px..+1.35px stem jump, 100% counters
            if ink_jump < 18.0 or stem_jump < 0.40:
                punch_score = ink_jump * 0.6 + stem_jump * 15.0 - 25.0
            else:
                punch_score = 42.0 - abs(ink_jump - 46.0) * 0.45 + min(18.0, stem_jump * 15.0)
            return punch_score + mb.tuned_counter_pct * 0.35 + mb.tuned_hq_conf_pct * 0.25 - mb.tuning_burden_pct * 0.15

        best_bold = max(bold_cands, key=_score_bold_pair)
        m_bold = best_bold.by_size[ref_sz]
        bold_ink_jump = (m_bold.tuned_ink_pixels - m_norm.tuned_ink_pixels) / float(max(1, m_norm.tuned_ink_pixels)) * 100.0
        bold_stem_jump = m_bold.mean_stem_width_tuned_px - m_norm.mean_stem_width_tuned_px

        # Pick Subtle Iso-Weight Italic: closest to Normal ink mass ([-10%..+12%]) and >=25% lighter than Bold
        best_ital: Optional[FontEvalSummary] = None
        if italics:
            viable_itals = [c for c in italics if c.by_size[ref_sz].tuned_counter_pct >= 90.0]
            if not viable_itals:
                viable_itals = italics

            def _score_ital_pair(i_cut: FontEvalSummary) -> float:
                mi = i_cut.by_size[ref_sz]
                i_delta = (mi.tuned_ink_pixels - m_norm.tuned_ink_pixels) / float(max(1, m_norm.tuned_ink_pixels)) * 100.0
                b_over_i = (m_bold.tuned_ink_pixels - mi.tuned_ink_pixels) / float(max(1, mi.tuned_ink_pixels)) * 100.0
                iso_pen = abs(i_delta - 1.0) * 1.4
                if b_over_i < 20.0:
                    iso_pen += (20.0 - b_over_i) * 2.2
                return (
                    35.0
                    - iso_pen
                    + mi.tuned_counter_pct * 0.30
                    + mi.tuned_hq_conf_pct * 0.25
                    + mi.tuned_stem_2px_pct * 0.15
                    - mi.tuning_burden_pct * 0.15
                )

            best_ital = max(viable_itals, key=_score_ital_pair)

        if best_ital is not None:
            m_ital = best_ital.by_size[ref_sz]
            ital_ink_delta = (m_ital.tuned_ink_pixels - m_norm.tuned_ink_pixels) / float(max(1, m_norm.tuned_ink_pixels)) * 100.0
            bold_over_ital = (m_bold.tuned_ink_pixels - m_ital.tuned_ink_pixels) / float(max(1, m_ital.tuned_ink_pixels)) * 100.0
            ital_label = best_ital.label
            ital_file = best_ital.font_file
            ital_w = best_ital.weight_class
            ital_stem = m_ital.mean_stem_width_tuned_px
            ital_ink = m_ital.tuned_ink_pixels
            ital_cnt = m_ital.tuned_counter_pct
        else:
            ital_ink_delta = 0.0
            bold_over_ital = bold_ink_jump
            ital_label = "N/A (Upright Pair Only)"
            ital_file = "-"
            ital_w = 0
            ital_stem = 0.0
            ital_ink = 0
            ital_cnt = 0.0

        # Compute overall Tri-Role Visual Contrast Score
        punch_component = min(40.0, max(0.0, bold_ink_jump * 0.72 + bold_stem_jump * 12.0))
        if bold_ink_jump < 25.0:
            punch_component -= (25.0 - bold_ink_jump) * 1.2
        iso_ital_component = 25.0 - min(25.0, abs(ital_ink_delta - 1.0) * 1.3) if best_ital else 8.0
        if best_ital and bold_over_ital < 22.0:
            iso_ital_component -= (22.0 - bold_over_ital) * 1.5
        quality_component = (
            0.15 * m_norm.tuned_hq_conf_pct
            + 0.10 * m_bold.tuned_hq_conf_pct
            + 0.10 * m_bold.tuned_counter_pct
        )
        triad_score = round(punch_component + iso_ital_component + quality_component, 1)

        if bold_ink_jump >= 32.0 and bold_stem_jump >= 0.75 and (not best_ital or (-12.0 <= ital_ink_delta <= 14.0 and bold_over_ital >= 24.0)):
            verdict = "TIER 1 TRIAD: HIGH-PUNCH BOLD + ISO-WEIGHT SUBTLE ITALIC"
        elif bold_ink_jump >= 24.0 and bold_stem_jump >= 0.55:
            verdict = "TIER 2 TRIAD: MODERATE BOLD CONTRAST"
        else:
            verdict = "TIER 3 TRIAD: LOW WEIGHT CONTRAST (HOMOGENEOUS)"

        triads.append(
            FamilyTriadSummary(
                family_stem=fstem,
                family_group=best_norm.family_group,
                normal_label=best_norm.label,
                normal_file=best_norm.font_file,
                normal_weight=best_norm.weight_class,
                normal_stem_16px=m_norm.mean_stem_width_tuned_px,
                normal_ink_16px=m_norm.tuned_ink_pixels,
                normal_hq_16px=m_norm.tuned_hq_conf_pct,
                bold_label=best_bold.label,
                bold_file=best_bold.font_file,
                bold_weight=best_bold.weight_class,
                bold_stem_16px=m_bold.mean_stem_width_tuned_px,
                bold_ink_16px=m_bold.tuned_ink_pixels,
                bold_cnt_16px=m_bold.tuned_counter_pct,
                italic_label=ital_label,
                italic_file=ital_file,
                italic_weight=ital_w,
                italic_stem_16px=ital_stem,
                italic_ink_16px=ital_ink,
                italic_cnt_16px=ital_cnt,
                bold_ink_jump_pct=round(bold_ink_jump, 1),
                bold_stem_jump_px=round(bold_stem_jump, 2),
                italic_ink_delta_pct=round(ital_ink_delta, 1),
                bold_over_italic_pct=round(bold_over_ital, 1),
                triad_contrast_score=triad_score,
                triad_verdict=verdict,
            )
        )

    triads.sort(key=lambda t: t.triad_contrast_score, reverse=True)
    return triads


def render_triad_contrast_sheet(
    out_png: Path,
    triads: Sequence[FamilyTriadSummary],
    tuned_strikes_map: Dict[str, Dict[int, List[GlyphStrike]]],
    sizes: Sequence[int],
) -> Optional[Path]:
    """
    Render the v1.0.17 Tri-Role Visual Contrast Sheet (`font_eval_triad_contrast_sheet.png`)
    stacking `NORMAL (BODY)`, `BOLD (PUNCH)`, and `ITALIC (SUBTLE)` directly on top of one
    another per family so pattern-recognition contrast is immediately visible at a glance.
    """
    valid_triads = [
        t for t in triads
        if t.normal_label in tuned_strikes_map and t.bold_label in tuned_strikes_map
    ]
    if not valid_triads:
        return None

    disp_sizes = [s for s in (14, 16, 20) if s in sizes]
    if not disp_sizes:
        disp_sizes = list(sizes[:3])

    pad = 16
    hdr_h = 92
    card_h = 164
    left_w = 340
    sz_col_w = 335
    zoom_col_w = 290
    img_w = pad * 2 + left_w + len(disp_sizes) * sz_col_w + zoom_col_w
    img_h = hdr_h + pad * 2 + len(valid_triads) * card_h + 12

    img = Image.new("RGB", (img_w, img_h), (244, 246, 250))
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, img_w, hdr_h], fill=(16, 21, 30))
    draw.text(
        (pad, 12),
        f"HUMID1 v{TOOL_VERSION} TRI-ROLE VISUAL CONTRAST SHEET | NORMAL (BODY) vs. BOLD (PUNCH) vs. ITALIC (SUBTLE EMPHASIS)",
        fill=(255, 255, 255),
    )
    draw.text(
        (pad, 36),
        "Pattern-Recognition Hierarchy: NORMAL = 2.0-2.2px Stems (1.00x Baseline) | BOLD = 2.9-3.2px Stems (+35%..+60% Ink Punch) | ITALIC = Iso-Weight Slant (-9%..+11% Ink)",
        fill=(115, 232, 172),
    )
    draw.text(
        (pad, 60),
        f"Specimen: \"{EVAL_SPECIMEN_STRING}\" | Right Column: 2x-Zoomed 16px Triad Overlay Strip (\"{TRIAD_ZOOM_CHARS}\")",
        fill=(185, 202, 224),
    )

    for idx, tr in enumerate(valid_triads):
        cy = hdr_h + pad + idx * card_h
        draw.rectangle([pad, cy, img_w - pad, cy + card_h - 10], fill=(255, 255, 255), outline=(202, 210, 222), width=1)
        draw.rectangle([pad, cy, pad + left_w, cy + card_h - 10], fill=(235, 240, 247), outline=(202, 210, 222), width=1)

        # Left summary card
        draw.text((pad + 10, cy + 8), f"{tr.family_stem} [{tr.family_group.upper()}]", fill=(16, 21, 30))
        v_col = (16, 122, 72) if "TIER 1" in tr.triad_verdict else (155, 85, 18)
        draw.text((pad + 10, cy + 28), f"Triad Score: {tr.triad_contrast_score:.1f} | {tr.triad_verdict.split(':')[0]}", fill=v_col)
        draw.text(
            (pad + 10, cy + 50),
            f"1. NORMAL : w{tr.normal_weight} ({tr.normal_stem_16px:.2f}px, {tr.normal_ink_16px}px ink)",
            fill=(30, 42, 58),
        )
        draw.text(
            (pad + 10, cy + 72),
            f"2. BOLD   : w{tr.bold_weight} ({tr.bold_stem_16px:.2f}px, +{tr.bold_ink_jump_pct:.1f}% INK PUNCH!)",
            fill=(165, 28, 28),
        )
        if tr.italic_weight > 0:
            draw.text(
                (pad + 10, cy + 94),
                f"3. ITALIC : w{tr.italic_weight} ({tr.italic_stem_16px:.2f}px, {tr.italic_ink_delta_pct:+.1f}% vs Norm)",
                fill=(24, 92, 165),
            )
            draw.text(
                (pad + 10, cy + 116),
                f"Contrast  : Bold is +{tr.bold_over_italic_pct:.1f}% heavier than Italic",
                fill=(65, 78, 96),
            )
        else:
            draw.text((pad + 10, cy + 94), "3. ITALIC : (None / Upright Pair Only)", fill=(110, 118, 130))

        role_rows = [
            ("NORMAL", tr.normal_label, (20, 26, 36), (248, 250, 252)),
            ("BOLD  ", tr.bold_label, (145, 18, 18), (255, 245, 245)),
            ("ITALIC", tr.italic_label, (20, 78, 148), (244, 249, 255)),
        ]

        for r_i, (r_tag, r_lbl, px_col, row_bg) in enumerate(role_rows):
            ry = cy + 6 + r_i * 48
            draw.rectangle([pad + left_w + 1, ry, img_w - pad - 1, ry + 45], fill=row_bg)
            if r_i > 0:
                draw.line([pad + left_w + 1, ry, img_w - pad - 1, ry], fill=(218, 224, 232), width=1)

            for s_i, sz in enumerate(disp_sizes):
                x0 = pad + left_w + s_i * sz_col_w + 8
                draw.text((x0, ry + 2), f"{sz}px {r_tag}", fill=px_col)
                g_list = tuned_strikes_map.get(r_lbl, {}).get(sz, [])
                if not g_list:
                    continue
                g_map = {g.codepoint: g for g in g_list}
                pen_x = x0 + 78
                base_y = ry + 34
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
                    gy0 = base_y - g.ofs_y - g.box_h
                    for ri_b, r_str in enumerate(g.rows):
                        for ci_b, px_ch in enumerate(r_str):
                            if px_ch == "#":
                                px_x = gx0 + ci_b
                                px_y = gy0 + ri_b
                                if x0 + 74 <= px_x < x0 + sz_col_w - 8 and ry + 6 <= px_y < ry + 43:
                                    img.putpixel((px_x, px_y), px_col)
                    pen_x += max(g.box_w + 1, g.adv_w_fp4 >> 4)
                    if pen_x > x0 + sz_col_w - 14:
                        break

            # Right column: 2x-zoomed 16px glyph strip for direct stem-thickness inspection
            zx0 = pad + left_w + len(disp_sizes) * sz_col_w + 8
            g16_list = tuned_strikes_map.get(r_lbl, {}).get(16, [])
            if g16_list:
                g16_map = {g.codepoint: g for g in g16_list}
                zx = zx0
                zy_base = ry + 38
                zoom = 2
                for ch in TRIAD_ZOOM_CHARS:
                    g = g16_map.get(ord(ch))
                    if g is None or not g.rows:
                        continue
                    gw_z = g.box_w * zoom
                    if zx + gw_z + 4 > img_w - pad - 6:
                        break
                    gy0 = max(ry + 5, zy_base - (g.ofs_y + g.box_h) * zoom)
                    for ri_b, r_str in enumerate(g.rows):
                        for ci_b, px_ch in enumerate(r_str):
                            if px_ch == "#":
                                px0 = zx + ci_b * zoom
                                py0 = gy0 + ri_b * zoom
                                if py0 + zoom <= ry + 44:
                                    draw.rectangle([px0, py0, px0 + zoom - 1, py0 + zoom - 1], fill=px_col)
                    zx += gw_z + 6

    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png, optimize=True)
    return out_png


def render_single_font_eval_sheet(
    out_png: Path,
    summary: FontEvalSummary,
    raw_strikes_by_size: Dict[int, List[GlyphStrike]],
    tuned_strikes_by_size: Dict[int, List[GlyphStrike]],
    sizes: Sequence[int],
) -> None:
    """
    Render a dedicated, high-contrast Pre-Tune (RAW) vs. Post-Tune (TUNED) visual evaluation
    PNG sheet (`build/font_eval/sheets/<font_stem>_eval.png`) for a single font across all sizes.
    """
    pad = 16
    hdr_h = 84
    size_block_h = 128
    img_w = 1360
    img_h = hdr_h + pad * 2 + len(sizes) * size_block_h

    img = Image.new("RGB", (img_w, img_h), (245, 247, 250))
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, img_w, hdr_h], fill=(18, 23, 31))
    fl_raw = f"{summary.size_floor_raw_px}px" if summary.size_floor_raw_px < 99 else ">24px"
    fl_tun = f"{summary.size_floor_tuned_px}px" if summary.size_floor_tuned_px < 99 else ">24px"

    draw.text(
        (pad, 12),
        f"HUMID1 v{TOOL_VERSION} FONT EVALUATION & PRE/POST-TUNE SHEET | {summary.label} [{summary.font_file}]",
        fill=(255, 255, 255),
    )
    draw.text(
        (pad, 36),
        f"Role: {summary.intended_role} (Score: {summary.role_fit_score:.1f}) | {summary.recommendation_tier} | "
        f"Raw Floor: {fl_raw} -> Tuned Floor: {fl_tun}",
        fill=(110, 230, 165) if "TIER 1" in summary.recommendation_tier else (240, 200, 110),
    )
    draw.text(
        (pad, 58),
        f"16px HQ Confidence (Render->8x Upscale->Compare to HQ): Raw {summary.mean_16px_raw_hq_conf_pct:.1f}% -> "
        f"Tuned {summary.mean_16px_tuned_hq_conf_pct:.1f}% | 16px Tuning Burden: {summary.mean_16px_tuning_burden_pct:.1f}%",
        fill=(182, 200, 222),
    )

    for s_idx, sz in enumerate(sizes):
        by = hdr_h + pad + s_idx * size_block_h
        m = summary.by_size.get(sz)
        raw_glyphs = raw_strikes_by_size.get(sz, [])
        tun_glyphs = tuned_strikes_by_size.get(sz, [])
        if not m or not raw_glyphs or not tun_glyphs:
            continue

        draw.rectangle([pad, by, img_w - pad, by + size_block_h - 8], fill=(255, 255, 255), outline=(205, 212, 222), width=1)
        pt96 = sz * 72.0 / 96.0

        draw.rectangle([pad, by, pad + 215, by + size_block_h - 8], fill=(236, 240, 246), outline=(205, 212, 222), width=1)
        draw.text((pad + 10, by + 10), f"{sz}px ({pt96:.1f}pt)", fill=(18, 23, 31))
        draw.text(
            (pad + 10, by + 32),
            f"Raw Floor: {'PASS' if m.passes_floor_raw else 'BELOW'}",
            fill=(20, 120, 70) if m.passes_floor_raw else (175, 48, 48),
        )
        draw.text(
            (pad + 10, by + 52),
            f"Tuned Floor: {'PASS' if m.passes_floor_tuned else 'BELOW'}",
            fill=(20, 120, 70) if m.passes_floor_tuned else (175, 48, 48),
        )
        draw.text(
            (pad + 10, by + 74),
            f"Patched: {m.repaired_glyphs}/{m.total_glyphs} ({m.tuning_burden_pct:.0f}%)",
            fill=(65, 78, 96),
        )
        draw.text(
            (pad + 10, by + 94),
            f"Stem w: {m.mean_stem_width_raw_px:.2f}->{m.mean_stem_width_tuned_px:.2f}px",
            fill=(65, 78, 96),
        )

        for sub_idx, (tag_lbl, g_list, hq_c, hq_d, st_r, cnt_r, ink_px, tag_col) in enumerate([
            ("PRE-TUNE (RAW)", raw_glyphs, m.raw_hq_conf_pct, m.raw_hq_diff_pct, m.raw_stem_2px_pct, m.raw_counter_pct, m.raw_ink_pixels, (40, 82, 145)),
            ("POST-TUNE (TUNED)", tun_glyphs, m.tuned_hq_conf_pct, m.tuned_hq_diff_pct, m.tuned_stem_2px_pct, m.tuned_counter_pct, m.tuned_ink_pixels, (18, 118, 72)),
        ]):
            sy = by + 6 + sub_idx * 56
            if sub_idx == 1:
                draw.line([pad + 216, sy - 3, img_w - pad - 2, sy - 3], fill=(224, 228, 235), width=1)

            draw.text((pad + 225, sy + 2), f"{tag_lbl}", fill=tag_col)
            stats_line = f"HQConf:{hq_c:4.1f}% (Diff:{hq_d:4.1f}%) | >=2px:{st_r:4.0f}% | Cnt:{cnt_r:4.0f}% | Ink:{ink_px}"
            draw.text((pad + 365, sy + 2), stats_line, fill=(80, 92, 108))

            g_map = {g.codepoint: g for g in g_list}
            pen_x = pad + 225
            base_y = sy + 44
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
                gy0 = base_y - g.ofs_y - g.box_h
                px_color = (16, 112, 68) if (sub_idx == 1 and g.patched) else (14, 18, 24)
                for r_i, r_str in enumerate(g.rows):
                    for c_i, px_ch in enumerate(r_str):
                        if px_ch == "#":
                            px_x = gx0 + c_i
                            px_y = gy0 + r_i
                            if pad + 220 <= px_x < pad + 740 and sy + 16 <= px_y < sy + 53:
                                img.putpixel((px_x, px_y), px_color)
                pen_x += max(g.box_w + 1, g.adv_w_fp4 >> 4)
                if pen_x > pad + 725:
                    break

            zoom = 2 if sz <= 18 else 1
            zx = pad + 750
            zy_base = sy + 45
            for ch in EVAL_ZOOM_STRIP_CHARS:
                cp = ord(ch)
                g = g_map.get(cp)
                if g is None or not g.rows:
                    continue
                gw_z = g.box_w * zoom
                gh_z = g.box_h * zoom
                if zx + gw_z + 6 > img_w - pad - 8:
                    break
                gy0 = max(sy + 16, zy_base - (g.ofs_y + g.box_h) * zoom)
                if sub_idx == 1 and g.patched:
                    draw.rectangle(
                        [zx - 2, sy + 15, zx + gw_z + 1, sy + 52],
                        fill=(232, 248, 238),
                        outline=(40, 155, 95),
                        width=1,
                    )
                px_col = (14, 105, 62) if (sub_idx == 1 and g.patched) else (20, 25, 34)
                for r_i, r_str in enumerate(g.rows):
                    for c_i, px_ch in enumerate(r_str):
                        if px_ch == "#":
                            px0 = zx + c_i * zoom
                            py0 = gy0 + r_i * zoom
                            if py0 + zoom <= sy + 53:
                                draw.rectangle([px0, py0, px0 + zoom - 1, py0 + zoom - 1], fill=px_col)
                zx += gw_z + max(5, sz // 3)

    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png, optimize=True)


CORE_SINGLE_LOOP_CHARS = set("069ADOPQRabdeopq")


def _check_counter_cavity_viable(rows: Sequence[str], ch: str, sz: int, weight_class: int, is_terminus: bool) -> bool:
    """
    Verify that enclosed counters are not pinched into 1px pinholes on Bold/ExtraBold strikes,
    open-tail characters ('6', '9', 'e') did not pinch into 2-hole figure-8s,
    and open-curve characters ('s', 'c', 'w', 'M') did not pinch shut into false loops.
    """
    if not rows:
        return False
    arr = bt.rows_to_binary_array(rows)
    _, b1, holes_mask = bt.compute_betti_numbers(arr)
    if ch in bt.PINCH_FORBIDDEN_CHARS:
        return b1 == 0
    exp_b1 = bt.CANONICAL_MIN_HOLES.get(ch, 1 if ch in EVAL_COUNTER_CHARS else 0)
    if b1 < exp_b1:
        return False
    if not is_terminus and sz >= 10 and ch in CORE_SINGLE_LOOP_CHARS and weight_class >= 650:
        hole_px = int(np.count_nonzero(holes_mask))
        if hole_px < 2:
            return False
    return True


def _worker_evaluate_font(task: dict) -> Tuple[FontEvalSummary, Dict[int, List[GlyphStrike]], Dict[int, List[GlyphStrike]]]:
    """ProcessPoolExecutor worker that evaluates a single font (both Raw and Tuned) and renders its PNG sheet."""
    label = task["label"]
    font_path = Path(task["font_path"])
    family_group = task["family_group"]
    weight_class = task["weight_class"]
    is_italic = task["is_italic"]
    sizes = task["sizes"]
    tune_mode = task.get("tune_mode", "surgical")
    sheets_dir = Path(task["sheets_dir"]) if task.get("sheets_dir") else None

    summary = FontEvalSummary(
        label=label,
        font_file=font_path.name,
        family_group=family_group,
        weight_class=weight_class,
        is_italic=is_italic,
        size_floor_raw_px=99,
        size_floor_tuned_px=99,
        mean_16px_tuning_burden_pct=0.0,
        mean_16px_raw_hq_conf_pct=0.0,
        mean_16px_tuned_hq_conf_pct=0.0,
        recommendation_tier="TIER 2: VIABLE WITH SURGICAL TUNE",
    )

    raw_strikes_by_size: Dict[int, List[GlyphStrike]] = {}
    tuned_strikes_by_size: Dict[int, List[GlyphStrike]] = {}

    try:
        ft, ft_lib = load_freetype()
        codepoints = sorted({ord(c) for c in (EVAL_BENCHMARK_CHARS + EVAL_SPECIMEN_STRING + EVAL_ZOOM_STRIP_CHARS)})

        is_terminus = "terminus" in font_path.name.lower()
        is_mono = (family_group == "mono") or is_terminus
        is_bold_role = weight_class >= 650

        for sz in sizes:
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
                raster_mode=task.get("raster_mode", "autohint-mono"),
                threshold=int(task.get("threshold", 128)),
                font_number=0,
            )
            raw_glyphs = [_clone_glyph(g) for g in glyphs]
            raw_strikes_by_size[sz] = raw_glyphs

            hq_face = ctypes.POINTER(FT_FaceRec)()
            has_hq = (ft.FT_New_Face(ft_lib, str(active_path).encode("utf-8"), 0, ctypes.byref(hq_face)) == 0)
            if has_hq:
                ft.FT_Set_Pixel_Sizes(hq_face, 0, sz * 8)

            recs: List[bt.RepairAuditRecord] = []
            raw_confs: List[float] = []
            tun_confs: List[float] = []
            raw_diffs: List[float] = []
            tun_diffs: List[float] = []

            for g in glyphs:
                if not g.rows or g.codepoint <= 0x0020:
                    continue
                ch = chr(g.codepoint)
                arr_bef = bt.rows_to_binary_array(g.rows)
                hq_img = _render_hq_gray_for_face(ft, hq_face, g.codepoint) if has_hq else None

                if is_terminus:
                    up_m = bt.compute_upscaled_hq_metrics(arr_bef, hq_img)
                    b0, b1, _ = bt.compute_betti_numbers(arr_bef)
                    exp_b1 = 2 if ch in "8B%" else (1 if ch in EVAL_COUNTER_CHARS else 0)
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
                        thin_v_before=False,
                        thin_h_before=False,
                        thin_v_after=False,
                        thin_h_after=False,
                        repaired=False,
                        size_floor_warning=(b1 < exp_b1),
                        engine_used="NativeBDF",
                        rows_before=g.rows,
                        rows_after=g.rows,
                        score_before=88.0,
                        score_after=88.0,
                        hq_conf_before=up_m.hq_conf_iou,
                        hq_conf_after=up_m.hq_conf_iou,
                        hq_diff_before=up_m.hq_diff_pct,
                        hq_diff_after=up_m.hq_diff_pct,
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
                        is_bold_role=is_bold_role,
                        tune_mode=tune_mode,
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

            if not is_terminus and tune_mode != "off":
                bt.synchronize_mirror_glyph_pairs(glyphs, recs, is_italic=is_italic, is_monospace=is_mono)

            if has_hq:
                ft.FT_Done_Face(hq_face)

            rec_by_ch = {r.char_label: r for r in recs if r.char_label in EVAL_BENCHMARK_CHARS}
            stem_total = len(EVAL_BENCHMARK_CHARS)
            stem_ok_raw = 0
            stem_ok_tun = 0
            cnt_total = 0
            cnt_ok_raw = 0
            cnt_ok_tun = 0
            missing_bench = 0
            pinched_or_pinhole_raw = 0
            pinched_or_pinhole_tun = 0

            for ch in EVAL_BENCHMARK_CHARS:
                r = rec_by_ch.get(ch)
                if r is None:
                    missing_bench += 1
                    raw_confs.append(0.0)
                    tun_confs.append(0.0)
                    raw_diffs.append(100.0)
                    tun_diffs.append(100.0)
                    if ch in EVAL_COUNTER_CHARS:
                        cnt_total += 1
                    continue

                raw_confs.append(r.hq_conf_before)
                tun_confs.append(r.hq_conf_after)
                raw_diffs.append(r.hq_diff_before)
                tun_diffs.append(r.hq_diff_after)

                if not r.thin_v_before and r.hq_conf_before >= 42.0:
                    stem_ok_raw += 1
                if not r.thin_v_after and r.hq_conf_after >= 42.0:
                    stem_ok_tun += 1

                if ch in EVAL_COUNTER_CHARS and r.holes_expected > 0:
                    cnt_total += 1
                    raw_cav_ok = _check_counter_cavity_viable(r.rows_before, ch, sz, weight_class, is_terminus)
                    tun_cav_ok = _check_counter_cavity_viable(r.rows_after, ch, sz, weight_class, is_terminus)
                    if r.holes_before >= r.holes_expected and raw_cav_ok:
                        cnt_ok_raw += 1
                    elif ch in CORE_SINGLE_LOOP_CHARS or ch in "8B":
                        pinched_or_pinhole_raw += 1
                    if r.holes_after >= r.holes_expected and tun_cav_ok:
                        cnt_ok_tun += 1
                    elif ch in CORE_SINGLE_LOOP_CHARS or ch in "8B":
                        pinched_or_pinhole_tun += 1
                elif ch in "scwM":
                    if not _check_counter_cavity_viable(r.rows_before, ch, sz, weight_class, is_terminus):
                        pinched_or_pinhole_raw += 1
                    if not _check_counter_cavity_viable(r.rows_after, ch, sz, weight_class, is_terminus):
                        pinched_or_pinhole_tun += 1

            s_raw = (float(stem_ok_raw) / float(max(1, stem_total))) * 100.0
            s_tun = (float(stem_ok_tun) / float(max(1, stem_total))) * 100.0
            c_raw = (float(cnt_ok_raw) / float(max(1, cnt_total))) * 100.0
            c_tun = (float(cnt_ok_tun) / float(max(1, cnt_total))) * 100.0

            raw_bench = [g for g in raw_glyphs if g.codepoint > 0x20 and chr(g.codepoint) in EVAL_BENCHMARK_CHARS]
            tun_bench = [g for g in glyphs if g.codepoint > 0x20 and chr(g.codepoint) in EVAL_BENCHMARK_CHARS]
            raw_ink = sum(sum(row.count("#") for row in g.rows) for g in raw_bench if g.rows)
            tun_ink = sum(sum(row.count("#") for row in g.rows) for g in tun_bench if g.rows)
            w_raw = _measure_mean_stem_width(raw_bench) if missing_bench < (stem_total // 2) else 0.0
            w_tun = _measure_mean_stem_width(tun_bench) if missing_bench < (stem_total // 2) else 0.0

            rep_cnt = sum(1 for r in recs if r.repaired and r.char_label in EVAL_BENCHMARK_CHARS)
            tot_cnt = max(1, stem_total)
            burden_pct = (float(rep_cnt) / float(tot_cnt)) * 100.0

            mean_raw_conf = float(np.mean(raw_confs)) if raw_confs else 0.0
            mean_tun_conf = float(np.mean(tun_confs)) if tun_confs else 0.0

            # Size- and slant-aware viable floor gate (v1.0.17):
            # Accounts for 1-BPP diagonal staircase quantization on slanted Italics and 14px grid rounding
            min_raw_hq = (64.0 if is_italic else 68.5) if sz <= 14 else (67.0 if is_italic else 72.0)
            min_tun_hq = (65.0 if is_italic else 69.5) if sz <= 14 else (68.0 if is_italic else 73.0)
            min_raw_st = (65.0 if is_italic else 76.0) if sz <= 14 else (75.0 if is_italic else 82.0)
            min_tun_st = (74.0 if is_italic else 82.0) if sz <= 14 else (80.0 if is_italic else 85.0)

            if is_terminus:
                pass_raw = (missing_bench == 0) and (c_raw >= 88.0)
                pass_tun = (missing_bench == 0) and (c_tun >= 88.0)
            else:
                pass_raw = (
                    (missing_bench == 0)
                    and (pinched_or_pinhole_raw == 0)
                    and (mean_raw_conf >= min_raw_hq)
                    and (c_raw >= 94.0)
                    and (s_raw >= min_raw_st)
                    and (w_raw >= 1.62)
                )
                pass_tun = (
                    (missing_bench == 0)
                    and (pinched_or_pinhole_tun == 0)
                    and (mean_tun_conf >= min_tun_hq)
                    and (c_tun >= 94.0)
                    and (s_tun >= min_tun_st)
                    and (w_tun >= 1.68)
                    and (burden_pct <= 48.0)
                )

            if pass_raw and summary.size_floor_raw_px == 99:
                summary.size_floor_raw_px = sz
            if pass_tun and summary.size_floor_tuned_px == 99:
                summary.size_floor_tuned_px = sz

            summary.by_size[sz] = SizeMetrics(
                size_px=sz,
                raw_hq_conf_pct=round(mean_raw_conf, 1),
                tuned_hq_conf_pct=round(mean_tun_conf, 1),
                raw_hq_diff_pct=round(float(np.mean(raw_diffs)) if raw_diffs else 100.0, 1),
                tuned_hq_diff_pct=round(float(np.mean(tun_diffs)) if tun_diffs else 100.0, 1),
                raw_stem_2px_pct=round(s_raw, 1),
                tuned_stem_2px_pct=round(s_tun, 1),
                raw_counter_pct=round(c_raw, 1),
                tuned_counter_pct=round(c_tun, 1),
                mean_stem_width_raw_px=round(w_raw, 2),
                mean_stem_width_tuned_px=round(w_tun, 2),
                raw_ink_pixels=int(raw_ink),
                tuned_ink_pixels=int(tun_ink),
                repaired_glyphs=rep_cnt,
                total_glyphs=tot_cnt,
                tuning_burden_pct=round(burden_pct, 1),
                passes_floor_raw=pass_raw,
                passes_floor_tuned=pass_tun,
            )
            tuned_strikes_by_size[sz] = glyphs

        ref_sz = 16 if 16 in summary.by_size else (sizes[len(sizes) // 2] if sizes else 16)
        m_ref = summary.by_size.get(ref_sz)
        if m_ref:
            summary.mean_16px_tuning_burden_pct = m_ref.tuning_burden_pct
            summary.mean_16px_raw_hq_conf_pct = m_ref.raw_hq_conf_pct
            summary.mean_16px_tuned_hq_conf_pct = m_ref.tuned_hq_conf_pct
            min_t1_hq = 68.0 if is_italic else 72.0
            if summary.size_floor_raw_px <= 16 and m_ref.tuning_burden_pct <= 22.0 and m_ref.raw_hq_conf_pct >= min_t1_hq:
                summary.recommendation_tier = "TIER 1: NATIVE READY (Minimal/Zero Tune Needed)"
            elif summary.size_floor_tuned_px <= 16 and m_ref.tuning_burden_pct <= 48.0 and m_ref.tuned_hq_conf_pct >= min_t1_hq:
                summary.recommendation_tier = "TIER 2: VIABLE WITH SURGICAL TUNE"
            elif m_ref.raw_hq_conf_pct < 45.0 or weight_class <= 250:
                summary.recommendation_tier = "TIER 4: DO NOT USE ON 1-BPP EPD (Sub-Pixel Hairline Dropout)"
            else:
                summary.recommendation_tier = "TIER 3: HIGH TUNE BURDEN / LARGE SIZES (>=20px) ONLY"

        role_lbl, role_sc = classify_font_role_and_score(summary)
        summary.intended_role = role_lbl
        summary.role_fit_score = role_sc

        if sheets_dir is not None and raw_strikes_by_size:
            safe_slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", font_path.stem)
            sheet_path = sheets_dir / f"{safe_slug}_eval.png"
            render_single_font_eval_sheet(sheet_path, summary, raw_strikes_by_size, tuned_strikes_by_size, sizes)
            summary.sheet_png = f"sheets/{sheet_path.name}"
    except Exception as exc:
        print(f"[!] Warning: Worker skipped malformed/unreadable font {font_path.name}: {exc}", file=sys.stderr)
        summary.recommendation_tier = f"SKIPPED / ERROR ({type(exc).__name__})"

    return summary, raw_strikes_by_size, tuned_strikes_by_size


def compute_composite_epd_score(d: FontEvalSummary) -> float:
    """Return the role-aware 1-BPP fitness score (`d.role_fit_score`)."""
    if d.role_fit_score != 0.0:
        return d.role_fit_score
    _, sc = classify_font_role_and_score(d)
    return sc


def _render_master_sheet_page(
    out_png: Path,
    shown: Sequence[FontEvalSummary],
    raw_strikes_map: Dict[str, Dict[int, List[GlyphStrike]]],
    tuned_strikes_map: Dict[str, Dict[int, List[GlyphStrike]]],
    sizes: Sequence[int],
    page_subtitle: str = "",
) -> None:
    row_h = 74
    hdr_h = 80
    left_col_w = 310
    size_col_w = 345
    pad = 16

    img_w = pad * 2 + left_col_w + len(sizes) * size_col_w
    img_h = hdr_h + pad * 2 + len(shown) * row_h + 44
    img = Image.new("RGB", (img_w, img_h), (246, 247, 250))
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, img_w, hdr_h], fill=(18, 23, 31))
    draw.text(
        (pad, 14),
        f"HUMID1 v{TOOL_VERSION} PRE-TUNE (RAW) vs. POST-TUNE (TUNED) ROLE-AWARE SCORECARD (188 DPI 1-BPP)",
        fill=(255, 255, 255),
    )
    draw.text(
        (pad, 38),
        "Each Font Row Shows: Top = PRE-TUNE (RAW FreeType) | Bottom = POST-TUNE (Counter-Carving + Surgical Tournament)",
        fill=(182, 200, 222),
    )
    draw.text(
        (pad, 58),
        f"Specimen: \"{EVAL_SPECIMEN_STRING}\" | Tri-Role Triad Sheet: build/font_eval/font_eval_triad_contrast_sheet.png",
        fill=(140, 215, 175),
    )

    y_tbl = hdr_h + pad
    draw.rectangle([pad, y_tbl, img_w - pad, y_tbl + 38], fill=(32, 40, 54))
    draw.text((pad + 10, y_tbl + 11), "TYPEFACE / ROLE / TIER & FLOORS", fill=(255, 255, 255))
    for s_idx, sz in enumerate(sizes):
        x_col = pad + left_col_w + s_idx * size_col_w
        pt96 = sz * 72.0 / 96.0
        draw.text((x_col + 8, y_tbl + 11), f"{sz}px ({pt96:.1f}pt) | RAW (Top) vs TUNED (Bottom)", fill=(210, 225, 245))

    for idx, summ in enumerate(shown):
        ry = y_tbl + 42 + idx * row_h
        bg = (255, 255, 255) if idx % 2 == 0 else (239, 242, 247)
        draw.rectangle([pad, ry, img_w - pad, ry + row_h - 4], fill=bg, outline=(210, 216, 224))

        fl_raw = f"{summ.size_floor_raw_px}px" if summ.size_floor_raw_px < 99 else ">24px"
        fl_tun = f"{summ.size_floor_tuned_px}px" if summ.size_floor_tuned_px < 99 else ">24px"
        m16 = summ.by_size.get(16)
        w16_s = f"{m16.mean_stem_width_tuned_px:.2f}px" if m16 else "N/A"
        draw.text((pad + 8, ry + 6), f"{summ.label}", fill=(18, 23, 31))
        draw.text(
            (pad + 8, ry + 24),
            f"{summ.intended_role} | Stem:{w16_s} | Fl:{fl_raw}->{fl_tun}",
            fill=(20, 118, 72) if "TIER 1" in summ.recommendation_tier else (140, 75, 20),
        )
        draw.text(
            (pad + 8, ry + 42),
            f"RoleScore:{summ.role_fit_score:.1f} | 16px HQ:{summ.mean_16px_raw_hq_conf_pct:.0f}%->{summ.mean_16px_tuned_hq_conf_pct:.0f}% | B:{summ.mean_16px_tuning_burden_pct:.0f}%",
            fill=(75, 88, 105),
        )

        for s_idx, sz in enumerate(sizes):
            x_col = pad + left_col_w + s_idx * size_col_w
            m = summ.by_size.get(sz)
            r_glyphs = raw_strikes_map.get(summ.label, {}).get(sz, [])
            t_glyphs = tuned_strikes_map.get(summ.label, {}).get(sz, [])
            if not m or not r_glyphs or not t_glyphs:
                continue

            for sub_i, (sub_tag, g_list, hc, st_p, brd) in enumerate([
                ("RAW", r_glyphs, m.raw_hq_conf_pct, m.raw_stem_2px_pct, ""),
                ("TUN", t_glyphs, m.tuned_hq_conf_pct, m.tuned_stem_2px_pct, f" [{m.repaired_glyphs}p]"),
            ]):
                sy = ry + 3 + sub_i * 34
                badge_c = (40, 82, 145) if sub_i == 0 else ((20, 118, 72) if m.passes_floor_tuned else (175, 48, 48))
                draw.text(
                    (x_col + 6, sy),
                    f"{sub_tag}: HQ:{hc:.0f}% >=2px:{st_p:.0f}% W:{m.mean_stem_width_tuned_px:.2f}{brd}",
                    fill=badge_c,
                )
                g_map = {g.codepoint: g for g in g_list}
                pen_x = x_col + 6
                base_y = sy + 29
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
                    gy0 = base_y - g.ofs_y - g.box_h
                    px_c = (16, 112, 68) if (sub_i == 1 and g.patched) else (14, 18, 24)
                    for r_i, r_str in enumerate(g.rows):
                        for c_i, px_ch in enumerate(r_str):
                            if px_ch == "#":
                                px_x = gx0 + c_i
                                px_y = gy0 + r_i
                                if x_col + 4 <= px_x < x_col + size_col_w - 6 and sy + 11 <= px_y < sy + 33:
                                    img.putpixel((px_x, px_y), px_c)
                    pen_x += max(g.box_w + 1, g.adv_w_fp4 >> 4)
                    if pen_x > x_col + size_col_w - 14:
                        break

    if page_subtitle:
        draw.text((img_w - pad - 420, 14), page_subtitle, fill=(110, 230, 165))
    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png, optimize=True)


def render_font_eval_comparison_sheet(
    out_png: Path,
    summaries: Sequence[FontEvalSummary],
    raw_strikes_map: Dict[str, Dict[int, List[GlyphStrike]]],
    tuned_strikes_map: Dict[str, Dict[int, List[GlyphStrike]]],
    sizes: Sequence[int],
    max_rows_per_page: int = 75,
) -> List[Path]:
    written_paths: List[Path] = []
    total = len(summaries)
    if total == 0:
        return written_paths

    if max_rows_per_page <= 0 or total <= max_rows_per_page:
        _render_master_sheet_page(
            out_png,
            summaries,
            raw_strikes_map,
            tuned_strikes_map,
            sizes,
            page_subtitle=f"ALL {total} FONTS PLOTTED (Page 1/1)",
        )
        written_paths.append(out_png)
        return written_paths

    num_pages = int(math.ceil(total / float(max_rows_per_page)))
    for p_idx in range(num_pages):
        start_i = p_idx * max_rows_per_page
        end_i = min(total, start_i + max_rows_per_page)
        chunk = summaries[start_i:end_i]
        page_path = out_png.parent / f"{out_png.stem}_p{p_idx + 1:02d}_of_{num_pages:02d}{out_png.suffix}"
        _render_master_sheet_page(
            page_path,
            chunk,
            raw_strikes_map,
            tuned_strikes_map,
            sizes,
            page_subtitle=f"PAGE {p_idx + 1}/{num_pages} (Fonts {start_i + 1}..{end_i} of {total})",
        )
        written_paths.append(page_path)

    ranked = sorted(summaries, key=compute_composite_epd_score, reverse=True)[:max_rows_per_page]
    _render_master_sheet_page(
        out_png,
        ranked,
        raw_strikes_map,
        tuned_strikes_map,
        sizes,
        page_subtitle=f"TOP {len(ranked)} ROLE-AWARE CONTENDERS (of {total} Total; Full Set in _p01..p{num_pages:02d})",
    )
    written_paths.insert(0, out_png)
    return written_paths


def generate_markdown_report(
    summaries: Sequence[FontEvalSummary],
    triads: Sequence[FamilyTriadSummary],
    sizes: Sequence[int],
) -> str:
    ref_sz = 16 if 16 in sizes else (sizes[len(sizes) // 2] if sizes else 16)
    lines: List[str] = [
        f"# Humiditron `epd-font` v{TOOL_VERSION} — Tri-Role Visual Contrast & Pre/Post-Tune Evaluation Report",
        "",
        "## 1. Tri-Role Family Triad Leaderboard (`NORMAL` vs. `BOLD PUNCH` vs. `SUBTLE ITALIC`)",
        "",
        "Why single-font isolated scoring failed in v1.0.15: ranking individual cuts by raw 8x HQ IoU rewarded fonts whose stems landed on `~2.3px–2.5px` (`w600 SemiBold` for Normal, `w700 Bold` for Bold with only `+6.5%` ink difference, and `w800 ExtraBoldItalic` with more ink than Bold!).",
        "",
        "In **v1.0.17**, `humid1_font_eval.py` evaluates **3-Role Visual Contrast Triads** designed for instant human pattern recognition on a 1-BPP display:",
        "- **`NORMAL (BODY)`**: `~2.00px–2.20px` stem (`Medium w500` / `Regular w400`) — crisp, open counters with contrast headroom.",
        "- **`BOLD (PUNCH)`**: `~2.90px–3.40px` stem (`ExtraBold w800` / `Black w900`) — **`+35% to +65%` more ink mass** and a **`+0.85px to +1.45px` integer stem jump** over `Normal`.",
        "- **`ITALIC (SUBTLE)`**: `~2.05px–2.30px` stem (`MediumItalic w500` / `SemiBoldItalic w600`) — **`[-10% to +12%]` iso-weight ink mass relative to `Normal`** and **`>=25%` lighter than `Bold`**, signaling nuance via slant and cursive terminals (`a`, `e`, `f`, `g`) without bold bloat.",
        "",
        "| Rank | Family (`Group`) | `NORMAL` (`Stem`, `Ink`) | `BOLD PUNCH` (`Stem`, `Ink Jump`, `Stem Jump`) | `SUBTLE ITALIC` (`Stem`, `Ink vs Normal`, `Lighter vs Bold`) | Triad Score | Verdict |",
        "| :---: | :--- | :--- | :--- | :--- | :---: | :--- |",
    ]

    for idx, t in enumerate(triads, 1):
        norm_s = f"`w{t.normal_weight}` (`{t.normal_stem_16px:.2f}px`, `{t.normal_ink_16px:,}`)"
        bold_s = f"**`w{t.bold_weight}`** (`{t.bold_stem_16px:.2f}px`, **`+{t.bold_ink_jump_pct:.1f}%`**, **`+{t.bold_stem_jump_px:.2f}px`**)"
        if t.italic_weight > 0:
            ital_s = f"`w{t.italic_weight}` (`{t.italic_stem_16px:.2f}px`, **`{t.italic_ink_delta_pct:+.1f}%`** vs Norm, **`-{t.bold_over_italic_pct:.1f}%`** vs Bold)"
        else:
            ital_s = "N/A (Upright Pair)"
        lines.append(
            f"| **{idx}** | **{t.family_stem}** (`{t.family_group}`) | {norm_s} | {bold_s} | {ital_s} | **`{t.triad_contrast_score:.1f}`** | {t.triad_verdict} |"
        )

    lines.extend([
        "",
        "## 2. Per-Font Role-Aware & Pre/Post-Tune Scorecard",
        "",
        f"| Typeface & Weight Label | Font File | `wght` | Assigned Role (`Score`) | Recommendation Tier | Raw->Tuned Floor | {ref_sz}px Stem (`Raw->Tun`) | {ref_sz}px Ink (`Tun`) | {ref_sz}px HQ Conf (`Raw->Tun`) | {ref_sz}px Counters | {ref_sz}px Burden |",
        "| :--- | :--- | :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ])

    for s in summaries:
        fl_raw = f"{s.size_floor_raw_px}px" if s.size_floor_raw_px < 99 else ">24px"
        fl_tun = f"**{s.size_floor_tuned_px}px**" if s.size_floor_tuned_px < 99 else ">24px"
        m = s.by_size.get(ref_sz)
        w_str = f"`{m.mean_stem_width_raw_px:.2f}->{m.mean_stem_width_tuned_px:.2f}px`" if m else "N/A"
        ink_str = f"`{m.tuned_ink_pixels:,}`" if m else "N/A"
        hq_str = f"`{m.raw_hq_conf_pct:.1f}%->{m.tuned_hq_conf_pct:.1f}%`" if m else "N/A"
        cnt_str = f"`{m.tuned_counter_pct:.1f}%`" if m else "N/A"
        bd_str = f"`{m.repaired_glyphs}/{m.total_glyphs} ({m.tuning_burden_pct:.1f}%)`" if m else "N/A"
        lines.append(
            f"| **{s.label}** | `{s.font_file}` | `{s.weight_class}` | **{s.intended_role}** (`{s.role_fit_score:.1f}`) | {s.recommendation_tier} | `{fl_raw}` -> {fl_tun} | {w_str} | {ink_str} | {hq_str} | {cnt_str} | {bd_str} |"
        )

    lines.append("")
    return "\n".join(lines)


def load_summaries_from_json_files(json_paths: Sequence[str]) -> List[FontEvalSummary]:
    """Load and deduplicate `FontEvalSummary` records from existing JSON evaluation reports."""
    loaded: List[FontEvalSummary] = []
    seen_files = set()
    for jp in json_paths:
        p = Path(jp).resolve()
        if not p.is_file():
            continue
        raw_list = json.loads(p.read_text(encoding="utf-8"))
        for item in raw_list:
            ff = item.get("font_file", "")
            if ff in seen_files:
                continue
            seen_files.add(ff)
            by_sz: Dict[int, SizeMetrics] = {}
            for k, v in item.get("by_size", {}).items():
                by_sz[int(k)] = SizeMetrics(**v)
            summ = FontEvalSummary(
                label=item["label"],
                font_file=ff,
                family_group=item["family_group"],
                weight_class=int(item["weight_class"]),
                is_italic=bool(item["is_italic"]),
                size_floor_raw_px=int(item["size_floor_raw_px"]),
                size_floor_tuned_px=int(item["size_floor_tuned_px"]),
                mean_16px_tuning_burden_pct=float(item["mean_16px_tuning_burden_pct"]),
                mean_16px_raw_hq_conf_pct=float(item["mean_16px_raw_hq_conf_pct"]),
                mean_16px_tuned_hq_conf_pct=float(item["mean_16px_tuned_hq_conf_pct"]),
                recommendation_tier=item["recommendation_tier"],
                sheet_png=item.get("sheet_png", ""),
                by_size=by_sz,
            )
            role_lbl, role_sc = classify_font_role_and_score(summ)
            summ.intended_role = role_lbl
            summ.role_fit_score = role_sc
            loaded.append(summ)
    return loaded


def main() -> None:
    t0 = time.perf_counter()
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent if script_dir.name == "fonts" else script_dir.parent

    parser = argparse.ArgumentParser(
        prog="humid1_font_eval.py",
        description=(
            f"Humidyne Labs `epd-font` v{TOOL_VERSION} — Multi-Core Font & Weight Evaluation Suite\n"
            "with Tri-Role Visual Contrast Triad Scorer (Normal + Bold Punch + Subtle Italic)."
        ),
    )
    parser.add_argument("--src-dir", type=str, default=str(repo_root / "build" / "static_ttfs"), help="Directory containing .ttf/.otf/.ttc/.bdf fonts to evaluate")
    parser.add_argument("--out-dir", type=str, default=str(repo_root / "build" / "font_eval"), help="Output directory for reports & PNG sheets")
    parser.add_argument("--fonts", type=str, nargs="*", default=None, help="Optional explicit list of .ttf/.otf/.ttc font paths to evaluate")
    parser.add_argument("--re-digest-json", type=str, nargs="+", default=None, help="Re-evaluate existing font_eval_report.json file(s) with the v1.0.17 Tri-Role Triad Scorer")
    parser.add_argument("--sizes", type=int, nargs="+", default=[12, 14, 16, 20, 24], help="Pixel sizes to benchmark (default: 12 14 16 20 24)")
    parser.add_argument(
        "--tune-mode",
        type=str,
        choices=["off", "wart-only", "surgical", "full"],
        default="surgical",
        help="Auto-tune intervention level: off, wart-only, surgical (default), or full",
    )
    parser.add_argument("--raster-mode", type=str, choices=["autohint-mono", "bytecode-mono", "autohint-1bit", "bytecode-1bit"], default="autohint-mono", help="FreeType rasterization mode (default: autohint-mono)")
    parser.add_argument("--threshold", type=int, default=128, help="Grayscale threshold (1..254, or 0 for dynamic; default: 128)")
    parser.add_argument("--max-rows-per-page", type=int, default=75, help="Max font rows per master comparison PNG page (default: 75)")
    parser.add_argument("-j", "--jobs", type=int, default=None, help="Number of parallel CPU worker processes (default: all CPU cores)")
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    sheets_dir = out_dir / "sheets"
    out_dir.mkdir(parents=True, exist_ok=True)
    sheets_dir.mkdir(parents=True, exist_ok=True)

    ref_sz = 16 if 16 in args.sizes else args.sizes[len(args.sizes) // 2]

    if args.re_digest_json:
        summaries = load_summaries_from_json_files(args.re_digest_json)
        triads = evaluate_family_triads(summaries, ref_sz=ref_sz)
        md_report = generate_markdown_report(summaries, triads, args.sizes)
        md_path = out_dir / "font_eval_triad_digest.md"
        md_path.write_text(md_report, encoding="utf-8")
        triad_json_path = out_dir / "font_eval_triads.json"
        triad_json_path.write_text(json.dumps([asdict(t) for t in triads], indent=2) + "\n", encoding="utf-8")
        print(f"[+] Re-digested {len(summaries)} font cuts across {len(triads)} family triads -> {md_path}")
        return

    src_dir = Path(args.src_dir).resolve()
    candidates = discover_candidate_fonts(src_dir, args.fonts)
    if not candidates:
        print(f"[!] No evaluable Latin .ttf/.otf/.ttc fonts found in {src_dir}.", file=sys.stderr)
        raise SystemExit(1)

    max_workers = args.jobs if (args.jobs and args.jobs > 0) else (os.cpu_count() or 4)
    print(f"[*] Benchmarking {len(candidates)} font cuts across sizes {args.sizes} using {max_workers} CPU cores (Role-Aware + Tri-Role Triad Scorer)...")

    tasks = [
        {
            "label": lbl,
            "font_path": str(fpath),
            "family_group": fg,
            "weight_class": wght,
            "is_italic": is_it,
            "sizes": list(args.sizes),
            "tune_mode": args.tune_mode,
            "raster_mode": args.raster_mode,
            "threshold": args.threshold,
            "sheets_dir": str(sheets_dir),
        }
        for (lbl, fpath, fg, wght, is_it) in candidates
    ]

    summaries: List[FontEvalSummary] = []
    raw_strikes_map: Dict[str, Dict[int, List[GlyphStrike]]] = {}
    tuned_strikes_map: Dict[str, Dict[int, List[GlyphStrike]]] = {}

    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as pool:
        for idx, (summ, r_map, t_map) in enumerate(pool.map(_worker_evaluate_font, tasks), 1):
            summaries.append(summ)
            raw_strikes_map[summ.label] = r_map
            tuned_strikes_map[summ.label] = t_map
            m_ref = summ.by_size.get(ref_sz)
            info = (
                f"{summ.intended_role:16s} ({summ.role_fit_score:4.1f}) | "
                f"{ref_sz}px Stem:{m_ref.mean_stem_width_tuned_px:.2f}px Ink:{m_ref.tuned_ink_pixels:4d} Cnt:{m_ref.tuned_counter_pct:5.1f}%"
            ) if m_ref else ""
            print(
                f"    [{idx:>3}/{len(tasks):<3}] {summ.label:42s} | Fl:{summ.size_floor_raw_px:>2}->{summ.size_floor_tuned_px:>2}px | {info}"
            )

    triads = evaluate_family_triads(summaries, ref_sz=ref_sz)
    md_report = generate_markdown_report(summaries, triads, args.sizes)
    md_path = out_dir / "font_eval_report.md"
    md_path.write_text(md_report, encoding="utf-8")

    audit_md_path = repo_root / "docs" / "audits" / f"FONT_EVAL_BENCHMARK_v{TOOL_VERSION}.md"
    audit_md_path.parent.mkdir(parents=True, exist_ok=True)
    audit_md_path.write_text(md_report, encoding="utf-8")

    csv_path = out_dir / "font_eval_report.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as cf:
        writer = csv.writer(cf)
        writer.writerow([
            "label", "font_file", "family_group", "weight_class", "is_italic",
            "intended_role", "role_fit_score", "recommendation_tier",
            "size_floor_raw_px", "size_floor_tuned_px",
            f"stem_width_{ref_sz}px", f"ink_pixels_{ref_sz}px",
            f"raw_hq_conf_{ref_sz}px", f"tuned_hq_conf_{ref_sz}px",
            f"raw_stem_2px_{ref_sz}px", f"tuned_stem_2px_{ref_sz}px",
            f"tuned_counter_{ref_sz}px", f"tuning_burden_{ref_sz}px_pct", "sheet_png"
        ])
        for s in summaries:
            m = s.by_size.get(ref_sz)
            writer.writerow([
                s.label, s.font_file, s.family_group, s.weight_class, s.is_italic,
                s.intended_role, s.role_fit_score, s.recommendation_tier,
                s.size_floor_raw_px, s.size_floor_tuned_px,
                m.mean_stem_width_tuned_px if m else 0.0, m.tuned_ink_pixels if m else 0,
                m.raw_hq_conf_pct if m else 0.0, m.tuned_hq_conf_pct if m else 0.0,
                m.raw_stem_2px_pct if m else 0.0, m.tuned_stem_2px_pct if m else 0.0,
                m.tuned_counter_pct if m else 0.0, m.tuning_burden_pct if m else 0.0, s.sheet_png
            ])

    json_path = out_dir / "font_eval_report.json"
    json_path.write_text(
        json.dumps([asdict(s) for s in summaries], indent=2) + "\n",
        encoding="utf-8",
    )
    triads_json_path = out_dir / "font_eval_triads.json"
    triads_json_path.write_text(
        json.dumps([asdict(t) for t in triads], indent=2) + "\n",
        encoding="utf-8",
    )

    png_path = out_dir / "font_eval_comparison_sheet.png"
    written_master_pngs = render_font_eval_comparison_sheet(
        png_path, summaries, raw_strikes_map, tuned_strikes_map, args.sizes, max_rows_per_page=args.max_rows_per_page
    )
    triad_png_path = out_dir / "font_eval_triad_contrast_sheet.png"
    render_triad_contrast_sheet(triad_png_path, triads, tuned_strikes_map, args.sizes)

    elapsed = time.perf_counter() - t0
    print(f"[+] Wrote {len(summaries)} Per-Font PNG Evaluation Sheets -> {sheets_dir}")
    print(f"[+] Wrote Tri-Role Visual Contrast Sheet          -> {triad_png_path}")
    print(f"[+] Wrote Font Evaluation Markdown & CSV Reports  -> {md_path}")
    print(f"[+] Wrote {len(written_master_pngs)} Master Pre/Post Visual Scorecard PNG(s) -> {png_path} ({elapsed:.2f}s)")


if __name__ == "__main__":
    main()
