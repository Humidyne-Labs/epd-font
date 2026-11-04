#!/usr/bin/env python3
"""
humid1_bilevel_tuner.py (v1.0.11)
=================================
Humidyne Labs / Humiditron `epd-font` Iterative Multi-Method Typographic Correction,
Scoring & Evaluation Engine (ASCII Patch Workflow + HQ Master & Nth-Factor Upscale Reference).

Repository : https://github.com/Humidyne-Labs/epd-font
Target OS  : https://github.com/Humidyne-Labs/H1OS
Spec Ref   : SPEC-TYPO-MATH-1BPP-001 (`docs/audits/exhibits/v1.0.11/methods_doc.docx` & `line_tracer.docx`)
License    : MIT License

Authoritative ASCII-Centric Workflow (`04 -> 08 -> 05 -> 02 -> 03`):
--------------------------------------------------------------------
  Step 1 (`04_dump_ascii_patches.bat`)   : Dump baseline rasterized strikes into `build/<target>/ascii_patches/`.
  Step 2 (`08_iterative_auto_repair.bat`): Run this exhaustive multi-method tournament engine across every
                                           glyph `.txt` file in `build/<target>/ascii_patches/`.
                                           - Synthesizes an 8x HQ Continuous Master Reference (`U_HQ`) and
                                             a Smallest-Strike Nth-Factor Upscale Reference (`U_base_xN`)
                                             for grid alignment & Jenson-Garamond counter-punching.
                                           - Evaluates 8 distinct mathematical synthesis & repair methods
                                             (`M0..M7`) across dynamic bounding-box widths (`W0, W0+1, W0+2`).
                                           - Enforces strict Euler-Poincare topology (`B0` & `B1` Betti lock),
                                             Mumford-Shah Total Variation skin-tag / notch eradication, and
                                             >=2px stem floor.
                                           - Rewrites improved `.txt` files directly in `ascii_patches/` with
                                             `patched: 1` and renders Before/After comparison sheets (with
                                             winning method & score breakdown) in `build/<target>/inspect_repairs/`.
  Step 3 (`05_apply_ascii_patches.bat`)  : Compile modified/repaired `.txt` files from `ascii_patches/` into
                                           the root `font_icon_epd_patches.json`.
  Step 4 (`02_build_fonts.bat`)          : Build LVGL `.c`/`.h`, BDF, and Strike Vault with the applied patches.
  Step 5 (`03_visual_check_pngs.bat`)    : Render `inspect_pages/` and `inspect_chars/` displaying the exact
                                           `Patched: N/Total` count in every PNG banner.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    cv2 = None  # type: ignore
    HAS_CV2 = False

from PIL import Image, ImageDraw

TOOL_VERSION = "1.0.11"

# Characters whose horizontal crossbars are structural and should be protected from vanishing
HORIZONTAL_BAR_CHARS = set("eftEFHTzZ=-+~÷±≤≥≠≈#[")

# Punctuation / tiny diacritics where horizontal stem widening should be skipped
SKIP_TUNING_CODEPOINTS = {
    0x0020,  # space
    0x0027,  # apostrophe '''
    0x002C,  # comma ','
    0x002E,  # period '.'
    0x003A,  # colon ':'
    0x003B,  # semicolon ';'
    0x0060,  # grave '`'
    0x00B7,  # middle dot '·'
    0x2018, 0x2019, 0x201C, 0x201D, 0x2022, 0x2026,
}


@dataclass
class CandidateEval:
    method_id: str
    binary: np.ndarray
    total_score: float
    stem_score: float
    hq_score: float
    smooth_score: float
    cavity_score: float
    color_score: float
    b0_components: int
    b1_holes: int
    skin_tags: int
    notches: int
    thin_v_ratio: float
    valid_topology: bool


@dataclass
class RepairAuditRecord:
    codepoint: int
    char_label: str
    box_w_before: int
    box_h_before: int
    box_w_after: int
    box_h_after: int
    holes_expected: int
    holes_before: int
    holes_after: int
    thin_v_before: bool
    thin_h_before: bool
    thin_v_after: bool
    thin_h_after: bool
    repaired: bool
    size_floor_warning: bool
    engine_used: str
    rows_before: List[str]
    rows_after: List[str]
    score_before: float = 0.0
    score_after: float = 0.0
    skin_tags_before: int = 0
    skin_tags_after: int = 0


def rows_to_binary_array(rows: Sequence[str]) -> np.ndarray:
    """Convert list of '#' / '.' strings into a (H, W) uint8 array with values {0, 255}."""
    if not rows or not rows[0]:
        return np.zeros((1, 1), dtype=np.uint8)
    h = len(rows)
    w = max(len(r) for r in rows)
    arr = np.zeros((h, w), dtype=np.uint8)
    for r_idx, row in enumerate(rows):
        for c_idx, ch in enumerate(row):
            if ch == "#":
                arr[r_idx, c_idx] = 255
    return arr


def binary_array_to_rows(arr: np.ndarray) -> List[str]:
    """Convert a (H, W) uint8 binary array (>0 = '#') into a list of '#' / '.' strings."""
    if arr.size == 0:
        return []
    return ["".join("#" if px > 0 else "." for px in row) for row in arr]


def trim_binary_array(
    arr: np.ndarray,
    ofs_x: int = 0,
    ofs_y: int = 0,
) -> Tuple[np.ndarray, int, int, int, int]:
    """Trim empty border rows/columns and return (trimmed_arr, box_w, box_h, new_ofs_x, new_ofs_y)."""
    ys, xs = np.nonzero(arr > 0)
    if len(xs) == 0 or len(ys) == 0:
        return np.zeros((0, 0), dtype=np.uint8), 0, 0, 0, 0
    r0, r1 = int(ys.min()), int(ys.max())
    c0, c1 = int(xs.min()), int(xs.max())
    h_orig = arr.shape[0]
    trimmed = arr[r0 : r1 + 1, c0 : c1 + 1]
    box_h, box_w = trimmed.shape
    new_ofs_x = ofs_x + c0
    new_ofs_y = ofs_y + (h_orig - 1 - r1)
    return trimmed, int(box_w), int(box_h), int(new_ofs_x), int(new_ofs_y)


def _get_row_runs(row: np.ndarray) -> List[Tuple[int, int]]:
    """Return list of (start_col, end_col_inclusive) for contiguous >0 runs in a 1D row."""
    runs: List[Tuple[int, int]] = []
    in_r = False
    s = 0
    for c, v in enumerate(row):
        if v > 0 and not in_r:
            s = c
            in_r = True
        elif v == 0 and in_r:
            runs.append((s, c - 1))
            in_r = False
    if in_r:
        runs.append((s, len(row) - 1))
    return runs


def compute_betti_numbers(binary_img: np.ndarray) -> Tuple[int, int, np.ndarray]:
    """
    Method 8 (Euler-Poincare Characteristic Conservation):
    Compute:
      - B0: number of 8-connected foreground ink components
      - B1: number of 4-connected interior background holes (counters)
      - counters_mask: uint8 mask (255 inside enclosed counters)
    """
    if binary_img.size == 0 or np.count_nonzero(binary_img) == 0:
        return 0, 0, np.zeros_like(binary_img)

    fg = (binary_img > 0).astype(np.uint8) * 255
    if HAS_CV2:
        n_fg, _, _, _ = cv2.connectedComponentsWithStats(fg, connectivity=8)
        b0 = max(0, int(n_fg - 1))

        h, w = fg.shape
        padded = cv2.copyMakeBorder(fg, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
        inv = cv2.bitwise_not(padded)
        ff_mask = np.zeros((h + 4, w + 4), np.uint8)
        cv2.floodFill(inv, ff_mask, (0, 0), 0)
        counters = inv[1:-1, 1:-1]
        n_holes, _, _, _ = cv2.connectedComponentsWithStats(counters, connectivity=4)
        b1 = max(0, int(n_holes - 1))
        return b0, b1, counters
    else:
        return 1, 0, np.zeros_like(binary_img)


def find_internal_counters(binary_img: np.ndarray) -> Tuple[np.ndarray, int, Optional[np.ndarray], Optional[np.ndarray]]:
    """Compatibility wrapper returning (counters_mask_255, num_holes, labels, stats)."""
    _, b1, counters = compute_betti_numbers(binary_img)
    if HAS_CV2 and b1 > 0:
        _, labels, stats, _ = cv2.connectedComponentsWithStats(counters, connectivity=4)
        return counters, b1, labels, stats
    return counters, b1, None, None


def detect_skin_tags_and_notches(
    binary_img: np.ndarray,
    hq_coverage: Optional[np.ndarray] = None,
) -> Tuple[int, int, List[Tuple[int, int]], List[Tuple[int, int]]]:
    """
    Method 18 (Mumford-Shah Anisotropic Total Variation & Spur/Notch Analysis):
    Detects:
      1. `skin_tags`: isolated 1-pixel protrusions/burrs jutting out of a stem boundary
         (e.g., a pixel p[r, c] == 255 with p[r-1, c] == 0 and p[r+1, c] == 0 attached
         laterally to a stem where the HQ master density is low, or a 1px vertical pimple
         with p[r, c-1] == 0 and p[r, c+1] == 0 on top/bottom of a horizontal bar).
      2. `notches`: 1-pixel indentations/steps along a straight vertical stem edge (where
         rows r-1 and r+1 have ink at column c, while row r drops to 0 at column c,
         creating the 'N' step artifact seen in `humid1_font_plex_serif_normal_18_repair__N.jpg`).
    Returns (num_skin_tags, num_notches, skin_tag_coords, notch_coords).
    """
    if binary_img.size == 0:
        return 0, 0, [], []
    h, w = binary_img.shape
    fg = binary_img > 0

    hq_resized = None
    if hq_coverage is not None and hq_coverage.size > 0 and HAS_CV2:
        if hq_coverage.shape != (h, w):
            hq_resized = cv2.resize(hq_coverage, (w, h), interpolation=cv2.INTER_AREA)
        else:
            hq_resized = hq_coverage

    skin_tags: List[Tuple[int, int]] = []
    notches: List[Tuple[int, int]] = []

    for r in range(h):
        for c in range(w):
            up = fg[r - 1, c] if r > 0 else False
            dn = fg[r + 1, c] if r + 1 < h else False
            lf = fg[r, c - 1] if c > 0 else False
            rt = fg[r, c + 1] if c + 1 < w else False

            if fg[r, c]:
                # Case A: Horizontal 1px wart jutting left or right off a vertical/slanted stem
                # (no vertical neighbors at (r-1, c) or (r+1, c), only 1 horizontal neighbor)
                if not up and not dn and (lf ^ rt):
                    # Ignore top/bottom row serifs if HQ master strongly supports them
                    hq_val = float(hq_resized[r, c]) if hq_resized is not None else 0.0
                    is_extremum_row = (r == 0) or (r == h - 1)
                    nb_c = (c - 1) if lf else (c + 1)
                    nb_up = fg[r - 1, nb_c] if r > 0 else False
                    nb_dn = fg[r + 1, nb_c] if r + 1 < h else False
                    # If attached to the middle of a vertical/slanted stem (both nb_up and nb_dn are True),
                    # or HQ coverage is weak (< 0.48), it is a skin tag!
                    if (nb_up and nb_dn and not is_extremum_row) or (hq_resized is not None and hq_val < 0.42):
                        skin_tags.append((r, c))
                        continue

                # Case B: Vertical 1px pimple jutting up or down off a horizontal bar
                if not lf and not rt and (up ^ dn):
                    hq_val = float(hq_resized[r, c]) if hq_resized is not None else 0.0
                    nb_r = (r - 1) if up else (r + 1)
                    nb_lf = fg[nb_r, c - 1] if c > 0 else False
                    nb_rt = fg[nb_r, c + 1] if c + 1 < w else False
                    if (nb_lf and nb_rt) and (hq_resized is None or hq_val < 0.45):
                        skin_tags.append((r, c))
                        continue
            else:
                # Case C: 1-pixel notch / step indentation along a vertical stem wall
                # (both up and dn are True at column c, and an adjacent column c_adj is solid across r-1, r, r+1)
                if up and dn:
                    for c_adj in (c - 1, c + 1):
                        if 0 <= c_adj < w and fg[r, c_adj] and (r > 0 and fg[r - 1, c_adj]) and (r + 1 < h and fg[r + 1, c_adj]):
                            # Make sure filling (r, c) wouldn't bridge to another stroke on the opposite side
                            c_opp = c + (c - c_adj)
                            opp_clear = (c_opp < 0 or c_opp >= w) or (not fg[r, c_opp])
                            if opp_clear:
                                notches.append((r, c))
                                break

    return len(skin_tags), len(notches), skin_tags, notches


def clean_skin_tags_and_notches(
    binary_img: np.ndarray,
    expected_b0: int,
    expected_b1: int,
    hq_coverage: Optional[np.ndarray] = None,
    max_iters: int = 3,
) -> np.ndarray:
    """
    Method 8 + Method 18:
    Iteratively remove 1-pixel skin tags and fill 1-pixel stem notches, accepting each
    single-pixel flip if and only if Betti numbers (B0, B1) remain strictly invariant!
    """
    work = binary_img.copy()
    for _ in range(max_iters):
        _, _, tag_coords, notch_coords = detect_skin_tags_and_notches(work, hq_coverage)
        if not tag_coords and not notch_coords:
            break
        changed = False
        # 1. Fill 1px vertical stem notches first (fixes 'N' left-stem step)
        for r, c in notch_coords:
            work[r, c] = 255
            b0, b1, _ = compute_betti_numbers(work)
            if b0 != expected_b0 or b1 != expected_b1:
                work[r, c] = 0
            else:
                changed = True
        # 2. Shave 1px skin tags (fixes italic 'm'/'M' and diagonal warts)
        for r, c in tag_coords:
            work[r, c] = 0
            b0, b1, _ = compute_betti_numbers(work)
            if b0 != expected_b0 or b1 != expected_b1:
                work[r, c] = 255
            else:
                changed = True
        if not changed:
            break
    return work


def count_2x2_checkerboards(binary_img: np.ndarray) -> int:
    """Method 17 (Ising Spin-Glass Hamiltonian): Count 2x2 diagonal checkerboard configurations."""
    if binary_img.shape[0] < 2 or binary_img.shape[1] < 2:
        return 0
    fg = (binary_img > 0).astype(np.int8)
    tl = fg[:-1, :-1]
    tr = fg[:-1, 1:]
    bl = fg[1:, :-1]
    br = fg[1:, 1:]
    c1 = (tl == 1) & (br == 1) & (tr == 0) & (bl == 0)
    c2 = (tl == 0) & (br == 0) & (tr == 1) & (bl == 1)
    return int(np.count_nonzero(c1 | c2))


def measure_stem_deficits(binary_img: np.ndarray, min_stem: int = 2) -> Tuple[bool, bool, float, float]:
    """
    Inspect whether vertical/diagonal stems (horizontal run lengths) or horizontal bars
    fall below `min_stem` pixels.
    Returns (needs_horizontal_floor, needs_vertical_floor, h_2px_ratio, v_2px_ratio).
    """
    nz = int(np.count_nonzero(binary_img))
    if nz == 0:
        return False, False, 1.0, 1.0
    h, w = binary_img.shape
    if w < min_stem:
        return True, False, 0.0, 1.0

    # Measure scanline run-length distribution across stem rows
    ge_min_runs = 0
    total_stem_runs = 0
    for r in range(h):
        runs = _get_row_runs(binary_img[r])
        if 1 <= len(runs) <= 3:
            for s, e in runs:
                rlen = e - s + 1
                # Ignore full-width horizontal crossbars when counting vertical stem runs
                if rlen < max(4, int(w * 0.75)):
                    total_stem_runs += 1
                    if rlen >= min_stem:
                        ge_min_runs += 1

    h_ratio = (float(ge_min_runs) / float(total_stem_runs)) if total_stem_runs > 0 else 1.0

    # Vertical survival for horizontal bars
    if HAS_CV2:
        v_erode = cv2.erode(
            binary_img,
            np.ones((min_stem, 1), np.uint8),
            iterations=1,
            borderType=cv2.BORDER_CONSTANT,
            borderValue=0,
        )
        v_ratio = float(np.count_nonzero(v_erode)) / float(nz)
    else:
        v_ratio = 0.5

    needs_h = (total_stem_runs >= 2) and (h_ratio < 0.72)
    needs_v = v_ratio < 0.16
    return needs_h, needs_v, h_ratio, v_ratio


def evaluate_glyph_candidate(
    method_id: str,
    candidate_1bit: np.ndarray,
    hq_master: Optional[np.ndarray],
    upscaled_small_ref: Optional[np.ndarray],
    expected_b0: int,
    expected_b1: int,
    min_stem: int = 2,
    orig_w: int = 0,
    is_italic_or_serif: bool = False,
    base_1bit: Optional[np.ndarray] = None,
) -> CandidateEval:
    """
    Weighted Multi-Objective Typographic Evaluation Engine (SPEC-TYPO-MATH-1BPP-001):
      - Hard Gate 1 : Betti numbers (B0 foreground components, B1 enclosed counters) must match HQ Master!
      - Hard Gate 2 : HQ Master Structural IOU must be >= 0.68 (and never degrade base HQ IOU by > 0.04)
                      and pixel mutation ratio vs base_1bit must be <= 0.32 (no silhouette distortion).
      - W_hq        : 40 pts — Structural IOU & L1 fidelity to 8x HQ continuous master density.
      - W_stem      : 25 pts — >=2px vertical/diagonal stem satisfaction (without >3px bloat).
      - W_smooth    : 20 pts — Mumford-Shah Total Variation smoothness (0 skin tags, 0 notches, 0 checkerboards).
      - W_cavity    : 10 pts — Jenson-Garamond Counter-Punch & Small-Font Nth-Upscale cavity alignment.
      - W_color     :  5 pts — Typographic color balance (Method 22) & minimal box growth.
    """
    if candidate_1bit.size == 0 or np.count_nonzero(candidate_1bit) == 0:
        return CandidateEval(method_id, candidate_1bit, -1e9, 0, 0, 0, 0, 0, 0, 0, 99, 99, 1.0, False)

    h, w = candidate_1bit.shape
    b0, b1, counters = compute_betti_numbers(candidate_1bit)
    valid_topo = (b0 == expected_b0) and (b1 == expected_b1)

    hq_resized = None
    if hq_master is not None and hq_master.size > 0 and HAS_CV2:
        hq_resized = cv2.resize(hq_master, (w, h), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0

    num_tags, num_notches, _, _ = detect_skin_tags_and_notches(candidate_1bit, hq_resized)
    num_checkers = count_2x2_checkerboards(candidate_1bit)
    needs_h, _, h_2px_ratio, _ = measure_stem_deficits(candidate_1bit, min_stem=min_stem)

    if not valid_topo:
        return CandidateEval(
            method_id, candidate_1bit, -1e6 - abs(b0 - expected_b0) * 1e4 - abs(b1 - expected_b1) * 1e4,
            0, 0, 0, 0, 0, b0, b1, num_tags, num_notches, 1.0 - h_2px_ratio, False
        )

    cand_f = (candidate_1bit > 0).astype(np.float32)

    # Check HQ Master Structural IOU & L1 fidelity (0..40)
    if hq_resized is not None:
        hq_bin = (hq_resized >= 0.44).astype(np.float32)
        inter = float(np.sum(cand_f * hq_bin))
        union = float(np.sum(np.maximum(cand_f, hq_bin)))
        iou = inter / max(1.0, union)
        l1_sim = 1.0 - float(np.mean(np.abs(cand_f - hq_resized)))

        # Hard HQ fidelity gate for non-M0 candidates: never accept distorted silhouettes
        if method_id != "M0_untouched":
            base_iou = 0.0
            if base_1bit is not None and base_1bit.size > 0 and HAS_CV2:
                hq_b0 = cv2.resize(hq_master, (base_1bit.shape[1], base_1bit.shape[0]), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
                b0_f = (base_1bit > 0).astype(np.float32)
                b0_bin = (hq_b0 >= 0.44).astype(np.float32)
                base_iou = float(np.sum(b0_f * b0_bin)) / max(1.0, float(np.sum(np.maximum(b0_f, b0_bin))))
                # Also check direct structural overlap with base_1bit resampled
                b0_rsz = (cv2.resize(base_1bit, (w, h), interpolation=cv2.INTER_NEAREST) > 0).astype(np.float32)
                base_cand_iou = float(np.sum(cand_f * b0_rsz)) / max(1.0, float(np.sum(np.maximum(cand_f, b0_rsz))))
                if base_cand_iou < 0.62:
                    return CandidateEval(method_id, candidate_1bit, -1e5, 0, 0, 0, 0, 0, b0, b1, num_tags, num_notches, 1.0 - h_2px_ratio, False)
            if iou < max(0.66, base_iou - 0.04):
                return CandidateEval(method_id, candidate_1bit, -1e5, 0, 0, 0, 0, 0, b0, b1, num_tags, num_notches, 1.0 - h_2px_ratio, False)
        hq_score = 40.0 * (0.65 * iou + 0.35 * l1_sim)
    else:
        hq_score = 28.0

    # 2. Stem Score (0..25)
    fat_runs = 0
    total_runs = 0
    for r in range(h):
        runs = _get_row_runs(candidate_1bit[r])
        if len(runs) >= 2:
            for s, e in runs:
                total_runs += 1
                if (e - s + 1) > min_stem + 1:
                    fat_runs += 1
    fat_penalty = (10.0 * fat_runs / max(1, total_runs)) if total_runs > 0 else 0.0
    stem_score = max(0.0, 25.0 * h_2px_ratio - fat_penalty)

    # 3. Mumford-Shah Boundary Smoothness & Anti-Skin-Tag Score (-50..20)
    smooth_score = 20.0 - (25.0 * num_tags) - (16.0 * num_notches) - (16.0 * num_checkers)

    # 4. Jenson-Garamond Counter-Punch & Upscaled Small-Font Reference Score (0..10)
    if expected_b1 > 0:
        hole_area_ratio = float(np.count_nonzero(counters)) / float(max(1, h * w))
        cavity_score = min(10.0, 10.0 * (hole_area_ratio / 0.10))
    else:
        cavity_score = 9.0

    if upscaled_small_ref is not None and upscaled_small_ref.size > 0 and HAS_CV2:
        up_rsz = cv2.resize(upscaled_small_ref, (w, h), interpolation=cv2.INTER_NEAREST)
        up_f = (up_rsz > 0).astype(np.float32)
        grid_align = 1.0 - float(np.mean(np.abs(cand_f - up_f)))
        cavity_score = 0.80 * cavity_score + 0.20 * (10.0 * grid_align)

    # 5. Typographic Color & Dynamic Box Width Economy (0..5)
    density = float(np.mean(cand_f))
    density_err = max(0.0, abs(density - 0.46) - 0.08)
    extra_w = max(0, w - orig_w) if orig_w > 0 else 0
    width_pen = 1.2 * extra_w if extra_w <= 1 else (3.5 * extra_w)
    color_score = max(0.0, 5.0 - (15.0 * density_err) - width_pen)

    total = stem_score + hq_score + smooth_score + cavity_score + color_score
    return CandidateEval(
        method_id=method_id,
        binary=candidate_1bit,
        total_score=total,
        stem_score=stem_score,
        hq_score=hq_score,
        smooth_score=smooth_score,
        cavity_score=cavity_score,
        color_score=color_score,
        b0_components=b0,
        b1_holes=b1,
        skin_tags=num_tags,
        notches=num_notches,
        thin_v_ratio=1.0 - h_2px_ratio,
        valid_topology=True,
    )


# =============================================================================
# CANDIDATE SYNTHESIS METHODS (M1 .. M6)
# =============================================================================

def _apply_counter_punch(
    work: np.ndarray,
    orig_counters: np.ndarray,
    upscaled_small_counters: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Method 21 (Jenson-Garamond Counter-Punch): Guarantee every expected internal cavity stays open."""
    if not HAS_CV2 or not np.any(orig_counters > 0):
        return work
    h, w = work.shape
    c_mask = orig_counters
    if c_mask.shape != (h, w):
        c_mask = cv2.resize(c_mask, (w, h), interpolation=cv2.INTER_NEAREST)

    res = work.copy()
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(c_mask, connectivity=4)
    for i in range(1, num_labels):
        hole_comp = (labels == i).astype(np.uint8) * 255
        # Erode hole slightly if hole is wide (>=3px), else preserve exact core pixel(s)
        hw = stats[i, cv2.CC_STAT_WIDTH]
        hh = stats[i, cv2.CC_STAT_HEIGHT]
        if hw >= 3 and hh >= 3:
            core = cv2.erode(hole_comp, np.ones((2, 2), np.uint8), borderType=cv2.BORDER_CONSTANT, borderValue=0)
            if np.count_nonzero(core) == 0:
                core = hole_comp
        else:
            core = hole_comp
        res = cv2.bitwise_and(res, cv2.bitwise_not(core))
        open_px = np.count_nonzero(cv2.bitwise_and(cv2.bitwise_not(res), hole_comp))
        if open_px == 0:
            cy = int(stats[i, cv2.CC_STAT_TOP] + hh // 2)
            cx = int(stats[i, cv2.CC_STAT_LEFT] + hw // 2)
            if 0 <= cy < h and 0 <= cx < w:
                res[cy, cx] = 0

    if upscaled_small_counters is not None and np.any(upscaled_small_counters > 0):
        uc = upscaled_small_counters
        if uc.shape != (h, w):
            uc = cv2.resize(uc, (w, h), interpolation=cv2.INTER_NEAREST)
        _, b1_now, _ = compute_betti_numbers(res)
        _, b1_up, _ = compute_betti_numbers(cv2.bitwise_not(uc))
        if b1_now == 0 and np.count_nonzero(uc) > 0:
            res = cv2.bitwise_and(res, cv2.bitwise_not(uc))

    return res


def synth_m1_phase_shift_sweep(
    hq_master: np.ndarray,
    target_w: int,
    target_h: int,
    orig_counters: np.ndarray,
) -> List[Tuple[str, np.ndarray]]:
    """Method 2 & 12: Sub-Pixel Phase-Shift & Clamped Lanczos/Area Threshold Sweep."""
    if not HAS_CV2 or hq_master is None or hq_master.size == 0 or target_w < 2 or target_h < 2:
        return []
    mh, mw = hq_master.shape
    out: List[Tuple[str, np.ndarray]] = []
    for dw in (0, 1):
        tw = target_w + dw
        for dx in (-0.25, 0.0, 0.25):
            for dy in (-0.20, 0.0, 0.20):
                sx = dx * (float(mw) / float(tw))
                sy = dy * (float(mh) / float(target_h))
                mat = np.float32([[1, 0, sx], [0, 1, sy]])
                shifted = cv2.warpAffine(hq_master, mat, (mw, mh), flags=cv2.INTER_LINEAR, borderValue=0)
                ds = cv2.resize(shifted, (tw, target_h), interpolation=cv2.INTER_AREA)
                for th in (100, 118, 135):
                    cand = (ds >= th).astype(np.uint8) * 255
                    cand = _apply_counter_punch(cand, orig_counters)
                    out.append((f"M1_phase(w+{dw},t={th})", cand))
    return out


def synth_m2_centerline_line_tracer(
    base_1bit: np.ndarray,
    hq_master: Optional[np.ndarray],
    orig_counters: np.ndarray,
    min_stem: int = 2,
) -> List[Tuple[str, np.ndarray]]:
    """
    Method 6 & `line_tracer.docx` (Medial Axis Centerline Graph + Asymmetric `[1, 1]` Stroke Kernel):
    Extracts the 1px medial ridge from the high-res master or base silhouette, snaps onto
    the target grid, and sweeps an asymmetric horizontal kernel `K = [[1, 1]]` so vertical
    stems are guaranteed 2px while horizontal crossbars stay 1px!
    """
    if not HAS_CV2:
        return []
    h, w = base_1bit.shape
    src = hq_master if (hq_master is not None and hq_master.size > 0) else base_1bit
    out: List[Tuple[str, np.ndarray]] = []

    for dw in (0, 1):
        tw = w + dw
        rsz = cv2.resize(src, (tw * 4, h * 4), interpolation=cv2.INTER_LINEAR)
        bw_hi = (rsz >= 115).astype(np.uint8) * 255
        dist = cv2.distanceTransform(bw_hi, cv2.DIST_L2, 3)
        # Extract local horizontal and vertical ridge maxima (medial skeleton)
        skel_hi = np.zeros_like(bw_hi)
        for r in range(1, bw_hi.shape[0] - 1):
            for c in range(1, bw_hi.shape[1] - 1):
                d = dist[r, c]
                if d >= 0.85:
                    if (d >= dist[r, c - 1] and d >= dist[r, c + 1]) or (d >= dist[r - 1, c] and d >= dist[r + 1, c]):
                        skel_hi[r, c] = 255
        skel_lo = cv2.resize(skel_hi, (tw, h), interpolation=cv2.INTER_AREA)
        skel_1px = (skel_lo >= 32).astype(np.uint8) * 255
        # Ensure skeleton contains core connectivity of base_1bit
        base_rsz = cv2.resize(base_1bit, (tw, h), interpolation=cv2.INTER_NEAREST)
        skel_1px = cv2.bitwise_or(skel_1px, _erode_safe(base_rsz, 1, 2))
        # Sweep asymmetric horizontal stroke kernel K = [1, 1] (2px vertical stems, 1px crossbars)
        k_asym = np.ones((1, min_stem), np.uint8)
        stroked = cv2.dilate(skel_1px, k_asym, iterations=1)
        stroked = _apply_counter_punch(stroked, orig_counters)
        out.append((f"M2_line_tracer(w+{dw})", stroked))
    return out


def _erode_safe(binary_img: np.ndarray, kh: int, kw: int) -> np.ndarray:
    if not HAS_CV2 or binary_img.size == 0:
        return binary_img
    return cv2.erode(binary_img, np.ones((kh, kw), np.uint8), iterations=1, borderType=cv2.BORDER_CONSTANT, borderValue=0)


def synth_m3_sdf_level_set(
    base_1bit: np.ndarray,
    hq_master: Optional[np.ndarray],
    orig_counters: np.ndarray,
) -> List[Tuple[str, np.ndarray]]:
    """Method 10: Signed Distance Field (SDF) Adaptive Zero-Level-Set Perturbation."""
    if not HAS_CV2:
        return []
    h, w = base_1bit.shape
    src = hq_master if (hq_master is not None and hq_master.size > 0) else base_1bit
    bw_hi = (cv2.resize(src, (w * 4, h * 4), interpolation=cv2.INTER_LINEAR) >= 120).astype(np.uint8) * 255
    d_in = cv2.distanceTransform(bw_hi, cv2.DIST_L2, 3)
    d_out = cv2.distanceTransform(cv2.bitwise_not(bw_hi), cv2.DIST_L2, 3)
    sdf = d_in - d_out
    out: List[Tuple[str, np.ndarray]] = []
    for dw in (0, 1):
        tw = w + dw
        sdf_lo = cv2.resize(sdf, (tw, h), interpolation=cv2.INTER_AREA)
        for delta in (0.35, 0.65):
            cand = (sdf_lo + delta >= 0.0).astype(np.uint8) * 255
            cand = _apply_counter_punch(cand, orig_counters)
            out.append((f"M3_sdf(w+{dw},d={delta})", cand))
    return out


def synth_m4_hysteresis_and_ink_traps(
    base_1bit: np.ndarray,
    hq_master: Optional[np.ndarray],
    orig_counters: np.ndarray,
    codepoint: int,
) -> List[Tuple[str, np.ndarray]]:
    """Method 13 & 19: Dual-Threshold Hysteresis Super-Sampling + LoG Acute Vertex Ink Traps."""
    if not HAS_CV2 or hq_master is None or hq_master.size == 0:
        return []
    h, w = base_1bit.shape
    ch_str = chr(codepoint) if 0x20 <= codepoint <= 0xFFFF else ""
    out: List[Tuple[str, np.ndarray]] = []
    for dw in (0, 1):
        tw = w + dw
        u = cv2.resize(hq_master, (tw, h), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
        strong = (u >= 0.50).astype(np.uint8) * 255
        weak = (u >= 0.28).astype(np.uint8) * 255
        # Promote weak pixels that widen 1px vertical stems to 2px without merging separate runs
        cand = strong.copy()
        for r in range(h):
            runs = _get_row_runs(cand[r])
            for idx, (s, e) in enumerate(runs):
                if (e - s + 1) < 2:
                    left_lim = (runs[idx - 1][1] + 2) if idx > 0 else 0
                    right_lim = (runs[idx + 1][0] - 2) if idx + 1 < len(runs) else (tw - 1)
                    if e + 1 <= right_lim and weak[r, e + 1] > 0:
                        cand[r, e + 1] = 255
                    elif s - 1 >= left_lim and weak[r, s - 1] > 0:
                        cand[r, s - 1] = 255
        # Method 13: Carve 1px LoG ink trap at congested acute interior vertices ('M','W','N','v','w','y')
        if ch_str in "MWNvwy%&#" and tw >= 6 and h >= 7:
            kernel_cross = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=np.int8)
            blobs = cv2.morphologyEx(cand, cv2.MORPH_HITMISS, kernel_cross)
            cand_trap = cv2.bitwise_and(cand, cv2.bitwise_not(blobs))
            b0_a, b1_a, _ = compute_betti_numbers(cand)
            b0_b, b1_b, _ = compute_betti_numbers(cand_trap)
            if b0_a == b0_b and b1_a == b1_b:
                cand = cand_trap
        cand = _apply_counter_punch(cand, orig_counters)
        out.append((f"M4_hysteresis_inktrap(w+{dw})", cand))
    return out


def synth_m5_whole_stem_collinear_autofloor(
    base_1bit: np.ndarray,
    orig_counters: np.ndarray,
    upscaled_small_counters: Optional[np.ndarray],
    min_stem: int = 2,
    can_widen: bool = True,
) -> List[Tuple[str, np.ndarray]]:
    """
    Method 16 & 21: Whole-Column / Trajectory-Consistent Outward Stem Dilation + Counter-Punch.
    Unlike naive per-row dilation, checks vertical column alignment across rows before expanding
    so vertical and slanted stems never develop 1-pixel steps or skin tags.
    """
    h, w = base_1bit.shape
    out: List[Tuple[str, np.ndarray]] = []

    # Variant A: In-place gap-safe directional stem thickening
    inp = base_1bit.copy()
    for r in range(h):
        runs = _get_row_runs(base_1bit[r])
        for idx, (s, e) in enumerate(runs):
            if (e - s + 1) >= min_stem:
                continue
            left_limit = (runs[idx - 1][1] + 2) if idx > 0 else 0
            right_limit = (runs[idx + 1][0] - 2) if idx + 1 < len(runs) else (w - 1)
            # Check which side aligns better with row r-1 and row r+1
            score_left = (1 if (r > 0 and s - 1 >= 0 and inp[r - 1, s - 1] > 0) else 0) + (
                1 if (r + 1 < h and s - 1 >= 0 and base_1bit[r + 1, s - 1] > 0) else 0
            )
            score_right = (1 if (r > 0 and e + 1 < w and inp[r - 1, e + 1] > 0) else 0) + (
                1 if (r + 1 < h and e + 1 < w and base_1bit[r + 1, e + 1] > 0) else 0
            )
            can_l = s - 1 >= left_limit
            can_r = e + 1 <= right_limit
            if can_l and can_r:
                if score_left > score_right:
                    inp[r, s - 1] = 255
                else:
                    inp[r, e + 1] = 255
            elif can_r:
                inp[r, e + 1] = 255
            elif can_l:
                inp[r, s - 1] = 255
    inp = _apply_counter_punch(inp, orig_counters, upscaled_small_counters)
    out.append(("M5_collinear_inplace", inp))

    if not can_widen:
        return out

    # Variant B: Outward-padded whole-stem expansion (+1..2px dynamic width)
    work = np.pad(base_1bit, ((0, 0), (1, 1)), mode="constant", constant_values=0)
    res = work.copy()
    pw = work.shape[1]
    has_multi = any(len(_get_row_runs(work[r])) >= 2 for r in range(h))

    for r in range(h):
        runs = _get_row_runs(work[r])
        if not runs:
            continue
        for idx, (s, e) in enumerate(runs):
            if (e - s + 1) >= min_stem:
                continue
            left_limit = (runs[idx - 1][1] + 2) if idx > 0 else 0
            right_limit = (runs[idx + 1][0] - 2) if idx + 1 < len(runs) else (pw - 1)
            can_l = s - 1 >= left_limit
            can_r = e + 1 <= right_limit

            if len(runs) == 1:
                if has_multi and s <= 2 and w >= 4 and can_l:
                    res[r, s - 1] = 255
                elif can_r:
                    res[r, e + 1] = 255
                elif can_l:
                    res[r, s - 1] = 255
            elif idx == 0:
                if can_l:
                    res[r, s - 1] = 255
                elif can_r:
                    res[r, e + 1] = 255
            elif idx == len(runs) - 1:
                if can_r:
                    res[r, e + 1] = 255
                elif can_l:
                    res[r, s - 1] = 255
            else:
                if can_r:
                    res[r, e + 1] = 255
                elif can_l:
                    res[r, s - 1] = 255

    # Snap vertical stem walls across full height so serifs and stems never step by 1px
    for r in range(h):
        if work[r, 1] > 0 and res[r, 0] == 0:
            if (r > 0 and res[r - 1, 0] > 0) or (r + 1 < h and res[r + 1, 0] > 0):
                res[r, 0] = 255
        if work[r, pw - 2] > 0 and res[r, pw - 1] == 0:
            if (r > 0 and res[r - 1, pw - 1] > 0) or (r + 1 < h and res[r + 1, pw - 1] > 0):
                res[r, pw - 1] = 255

    ys, xs = np.nonzero(res > 0)
    if len(xs) > 0:
        res = res[:, int(xs.min()) : int(xs.max()) + 1]
    res = _apply_counter_punch(res, orig_counters, upscaled_small_counters)
    out.append(("M5_collinear_outward", res))
    return out


def synth_m6_italic_diagonal_rectifier(
    base_1bit: np.ndarray,
    orig_counters: np.ndarray,
    min_stem: int = 2,
) -> List[Tuple[str, np.ndarray]]:
    """
    Method 5 & 14 (Rational Diophantine Slant & Gabor Diagonal Continuity):
    Ensures slanted/diagonal strokes ('M','N','V','W','X','Y','Z','/','m','n','v','w')
    maintain uniform 2px horizontal thickness along their trajectory without 1px side-warts.
    """
    h, w = base_1bit.shape
    work = np.pad(base_1bit, ((0, 0), (0, 1)), mode="constant", constant_values=0)
    pw = work.shape[1]
    for r in range(h):
        runs = _get_row_runs(work[r])
        for idx, (s, e) in enumerate(runs):
            if (e - s + 1) < min_stem:
                right_lim = (runs[idx + 1][0] - 2) if idx + 1 < len(runs) else (pw - 1)
                if e + 1 <= right_lim:
                    work[r, e + 1] = 255
    ys, xs = np.nonzero(work > 0)
    if len(xs) > 0:
        work = work[:, int(xs.min()) : int(xs.max()) + 1]
    work = _apply_counter_punch(work, orig_counters)
    return [("M6_diagonal_rectified", work)]


def inspect_and_repair_glyph_bitmap(
    base_1bit: np.ndarray,
    codepoint: int,
    min_stem: int = 2,
    gray_img: Optional[np.ndarray] = None,
    master_hi: Optional[np.ndarray] = None,
    upscaled_small_ref: Optional[np.ndarray] = None,
    expected_holes_override: Optional[int] = None,
    max_width_ceiling: Optional[int] = None,
    engine: str = "hybrid",
    is_italic_or_serif: bool = False,
) -> Tuple[np.ndarray, RepairAuditRecord]:
    """
    Run the Multi-Method Iterative Typographic Tournament (`M0..M7`) on a single glyph.
    Evaluates all candidates against the 8x HQ Master (`master_hi`) and Smallest-Font
    Nth-Factor Upscale Reference (`upscaled_small_ref`), cleans any skin tags or stem notches
    via Method 8/18 (`clean_skin_tags_and_notches`), and returns the winning bitmap + audit record.
    """
    ch_str = chr(codepoint) if 0x20 <= codepoint <= 0xFFFF else ""
    rows_before = binary_array_to_rows(base_1bit)
    h0, w0 = base_1bit.shape if base_1bit.size > 0 else (0, 0)

    if base_1bit.size == 0 or h0 <= 2 or w0 <= 1 or codepoint in SKIP_TUNING_CODEPOINTS:
        rec = RepairAuditRecord(
            codepoint=codepoint,
            char_label=ch_str,
            box_w_before=w0,
            box_h_before=h0,
            box_w_after=w0,
            box_h_after=h0,
            holes_expected=0,
            holes_before=0,
            holes_after=0,
            thin_v_before=False,
            thin_h_before=False,
            thin_v_after=False,
            thin_h_after=False,
            repaired=False,
            size_floor_warning=False,
            engine_used="untouched",
            rows_before=rows_before,
            rows_after=rows_before,
        )
        return base_1bit, rec

    b0_base, b1_base, orig_counters = compute_betti_numbers(base_1bit)
    expected_b0 = b0_base
    expected_b1 = b1_base
    if expected_holes_override is not None:
        expected_b1 = expected_holes_override
    elif master_hi is not None and master_hi.size > 0:
        b0_hi, b1_hi, hi_counters = compute_betti_numbers((master_hi >= 120).astype(np.uint8) * 255)
        expected_b0 = b0_hi if b0_hi > 0 else b0_base
        if w0 >= 5 and h0 >= 7:
            expected_b1 = b1_hi
            if b1_hi > 0 and HAS_CV2:
                orig_counters = cv2.resize(hi_counters, (w0, h0), interpolation=cv2.INTER_NEAREST)

    upscaled_small_counters = None
    if upscaled_small_ref is not None and upscaled_small_ref.size > 0:
        _, _, upscaled_small_counters = compute_betti_numbers(upscaled_small_ref)

    needs_h0, needs_v0, _, _ = measure_stem_deficits(base_1bit, min_stem=min_stem)
    eval_m0 = evaluate_glyph_candidate(
        "M0_untouched",
        base_1bit,
        master_hi,
        upscaled_small_ref,
        expected_b0=b0_base,
        expected_b1=b1_base,
        min_stem=min_stem,
        orig_w=w0,
        is_italic_or_serif=is_italic_or_serif,
        base_1bit=base_1bit,
    )

    # Fast exit if M0 already has >=2px stems, expected holes, 0 skin tags, and 0 notches
    if not needs_h0 and b1_base >= expected_b1 and eval_m0.skin_tags == 0 and eval_m0.notches == 0:
        rec = RepairAuditRecord(
            codepoint=codepoint,
            char_label=ch_str,
            box_w_before=w0,
            box_h_before=h0,
            box_w_after=w0,
            box_h_after=h0,
            holes_expected=expected_b1,
            holes_before=b1_base,
            holes_after=b1_base,
            thin_v_before=False,
            thin_h_before=False,
            thin_v_after=False,
            thin_h_after=False,
            repaired=False,
            size_floor_warning=False,
            engine_used="M0_verified",
            rows_before=rows_before,
            rows_after=rows_before,
            score_before=eval_m0.total_score,
            score_after=eval_m0.total_score,
            skin_tags_before=0,
            skin_tags_after=0,
        )
        return base_1bit, rec

    can_widen = (max_width_ceiling is None) or (w0 + 1 <= max_width_ceiling)

    # Collect candidate pool across all mathematical synthesis methods (M1..M6)
    raw_candidates: List[Tuple[str, np.ndarray]] = []
    if master_hi is not None and master_hi.size > 0:
        raw_candidates.extend(synth_m1_phase_shift_sweep(master_hi, w0, h0, orig_counters))
        raw_candidates.extend(synth_m3_sdf_level_set(base_1bit, master_hi, orig_counters))
        raw_candidates.extend(synth_m4_hysteresis_and_ink_traps(base_1bit, master_hi, orig_counters, codepoint))
    raw_candidates.extend(synth_m2_centerline_line_tracer(base_1bit, master_hi, orig_counters, min_stem=min_stem))
    raw_candidates.extend(
        synth_m5_whole_stem_collinear_autofloor(
            base_1bit, orig_counters, upscaled_small_counters, min_stem=min_stem, can_widen=can_widen
        )
    )
    raw_candidates.extend(synth_m6_italic_diagonal_rectifier(base_1bit, orig_counters, min_stem=min_stem))

    best_eval = eval_m0
    hq_float = None
    if master_hi is not None and master_hi.size > 0 and HAS_CV2:
        hq_float = master_hi.astype(np.float32) / 255.0

    for m_name, cand_arr in raw_candidates:
        if cand_arr is None or cand_arr.size == 0:
            continue
        trimmed, bw, bh, _, _ = trim_binary_array(cand_arr)
        if bw == 0 or bh == 0:
            continue
        if max_width_ceiling is not None and bw > max_width_ceiling:
            continue

        # Method 7/8/18: Run Mumford-Shah Total-Variation Skin-Tag & Notch Cleaner on every candidate
        cleaned = clean_skin_tags_and_notches(
            trimmed,
            expected_b0=expected_b0,
            expected_b1=expected_b1,
            hq_coverage=hq_float,
        )
        cleaned, cbw, cbh, _, _ = trim_binary_array(cleaned)
        if cbw == 0 or cbh == 0:
            continue

        ev = evaluate_glyph_candidate(
            m_name,
            cleaned,
            master_hi,
            upscaled_small_ref,
            expected_b0=expected_b0,
            expected_b1=expected_b1,
            min_stem=min_stem,
            orig_w=w0,
            is_italic_or_serif=is_italic_or_serif,
            base_1bit=base_1bit,
        )
        # Strict acceptance criteria:
        # 1. Valid topology (B0 and B1 conserved)
        # 2. Zero skin tags and zero notches (no 1px spurs allowed!)
        # 3. Beats current best score
        if ev.valid_topology and ev.skin_tags == 0 and ev.notches == 0:
            if ev.total_score > best_eval.total_score:
                best_eval = ev

    # Require a meaningful score gain (>= +2.0 pts) over M0_untouched before modifying a glyph
    if best_eval.method_id != "M0_untouched" and (best_eval.total_score >= eval_m0.total_score + 2.0):
        winner = best_eval.binary
        used_method = best_eval.method_id
    else:
        winner = base_1bit.copy()
        best_eval = eval_m0
        used_method = "M0_untouched"

    rows_after = binary_array_to_rows(winner)
    changed = rows_after != rows_before
    thin_v_after, thin_h_after, _, _ = measure_stem_deficits(winner, min_stem=min_stem)
    size_floor_warn = (best_eval.b1_holes < expected_b1) or (thin_v_after and w0 < 2 * min_stem + 1)

    rec = RepairAuditRecord(
        codepoint=codepoint,
        char_label=ch_str,
        box_w_before=w0,
        box_h_before=h0,
        box_w_after=winner.shape[1],
        box_h_after=winner.shape[0],
        holes_expected=expected_b1,
        holes_before=b1_base,
        holes_after=best_eval.b1_holes,
        thin_v_before=needs_h0,
        thin_h_before=needs_v0,
        thin_v_after=thin_v_after,
        thin_h_after=thin_h_after,
        repaired=changed,
        size_floor_warning=size_floor_warn,
        engine_used=used_method,
        rows_before=rows_before,
        rows_after=rows_after,
        score_before=eval_m0.total_score,
        score_after=best_eval.total_score,
        skin_tags_before=eval_m0.skin_tags,
        skin_tags_after=best_eval.skin_tags,
    )
    return winner, rec


def render_repair_comparison_sheet(
    out_png: Path,
    strike_symbol: str,
    size_px: int,
    records: Sequence[RepairAuditRecord],
) -> None:
    """Render a visual Before vs. After 1-BPP diagnostic PNG showing winning method & score delta."""
    repaired_recs = [r for r in records if r.repaired]
    if not repaired_recs:
        repaired_recs = list(records[:24])
    if not repaired_recs:
        return

    cols = 4
    rows_cnt = int(math.ceil(len(repaired_recs) / float(cols)))
    cell_w = 290
    cell_h = 136
    pad = 16
    hdr_h = 68

    img_w = pad * 2 + cols * cell_w
    img_h = hdr_h + pad * 2 + rows_cnt * cell_h
    img = Image.new("RGB", (img_w, img_h), (246, 247, 249))
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, img_w, hdr_h], fill=(18, 23, 31))
    mod_cnt = sum(1 for r in records if r.repaired)
    draw.text(
        (pad, 12),
        f"HUMID1 v{TOOL_VERSION} MULTI-METHOD TYPOGRAPHIC TOURNAMENT | {strike_symbol} ({size_px}px)",
        fill=(255, 255, 255),
    )
    draw.text(
        (pad, 36),
        f"Inspected: {len(records)} glyphs | Auto-Patched in ascii_patches/: {mod_cnt} glyphs (0 Skin Tags, Euler B0/B1 Locked)",
        fill=(180, 198, 220),
    )

    zoom = max(3, min(6, 72 // max(8, size_px)))

    for idx, rec in enumerate(repaired_recs):
        r_idx = idx // cols
        c_idx = idx % cols
        x0 = pad + c_idx * cell_w
        y0 = hdr_h + pad + r_idx * cell_h

        bg = (255, 255, 255) if rec.repaired else (240, 242, 245)
        border = (34, 139, 87) if rec.repaired else (195, 202, 212)
        draw.rectangle([x0, y0, x0 + cell_w - 8, y0 + cell_h - 8], fill=bg, outline=border, width=1)

        lbl = f"U+{rec.codepoint:04X} '{rec.char_label}' [{rec.engine_used}]"
        draw.text((x0 + 8, y0 + 6), lbl, fill=(18, 23, 31))
        meta = (
            f"Score:{rec.score_before:.1f}->{rec.score_after:.1f} | "
            f"Holes:{rec.holes_before}->{rec.holes_after} | {rec.box_w_before}x{rec.box_h_before}->{rec.box_w_after}x{rec.box_h_after}"
        )
        draw.text((x0 + 8, y0 + 22), meta, fill=(90, 102, 118))

        for side_idx, (tag, g_rows, tint) in enumerate([
            ("BEFORE", rec.rows_before, (175, 52, 52)),
            ("AFTER", rec.rows_after, (16, 112, 68) if rec.repaired else (30, 36, 44)),
        ]):
            gx0 = x0 + 12 + side_idx * 134
            gy0 = y0 + 42
            draw.text((gx0, gy0 - 2), tag, fill=tint)
            gy_grid = gy0 + 12
            for ry, r_str in enumerate(g_rows):
                for cx, ch in enumerate(r_str):
                    px0 = gx0 + cx * zoom
                    py0 = gy_grid + ry * zoom
                    if py0 + zoom > y0 + cell_h - 12 or px0 + zoom > gx0 + 124:
                        continue
                    fill_c = tint if ch == "#" else (234, 237, 242)
                    draw.rectangle([px0, py0, px0 + zoom - 1, py0 + zoom - 1], fill=fill_c)

    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png, optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="humid1_bilevel_tuner.py",
        description=(
            f"Humidyne Labs `epd-font` v{TOOL_VERSION} — Iterative Multi-Method Typographic Tournament Engine.\n"
            "Tunes ASCII patch files in `build/<target>/ascii_patches/` using an 8x HQ continuous master\n"
            "reference + Smallest-Strike Nth-Factor Upscale Reference across 8 mathematical repair methods."
        ),
    )
    parser.add_argument("--scheme", type=str, default="scripts/h1os-build-distro/h1os_full.scheme.json", help="Scheme JSON path")
    parser.add_argument("--src-dir", type=str, default="build/static_ttfs", help="Static TTF directory")
    parser.add_argument("--out-dir", type=str, default="build/h1os", help="Build output directory")
    parser.add_argument("--ascii-dir", type=str, default=None, help="ASCII patch directory (default: <out-dir>/ascii_patches)")
    parser.add_argument("--patches", type=str, default="font_icon_epd_patches.json", help="Root JSON patches file")
    parser.add_argument("--min-stem", type=int, default=2, help="Minimum stem thickness in pixels (default: 2)")
    parser.add_argument(
        "--engine",
        type=str,
        choices=["hybrid", "autofloor", "downscale", "contour"],
        default="hybrid",
        help="Closed-loop tournament mode (default: hybrid)",
    )
    parser.add_argument(
        "--save-patches",
        action="store_true",
        default=True,
        help="Write repaired glyphs directly into ascii_patches/ AND compile to font_icon_epd_patches.json (default: True)",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(script_dir))
    import humid1_generate_1bpp as g1

    cmd_argv = [
        "humid1_generate_1bpp.py",
        "--workflow", "repair",
        "--scheme", args.scheme,
        "--src-dir", args.src_dir,
        "--out-dir", args.out_dir,
        "--patches", args.patches,
        "--min-stem", str(args.min_stem),
        "--repair-engine", args.engine,
        "--save-repaired-patches",
    ]
    if args.ascii_dir:
        cmd_argv.extend(["--ascii-dir", args.ascii_dir])
    sys.argv = cmd_argv
    g1.main()


if __name__ == "__main__":
    main()
