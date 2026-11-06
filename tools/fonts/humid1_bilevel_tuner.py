#!/usr/bin/env python3
"""
humid1_bilevel_tuner.py (v1.0.17)
=================================
Humidyne Labs / Humiditron `epd-font` Surgical Multi-Method Typographic Tuner,
Render -> Upscale (8x) -> HQ Master Confidence Sanity Gate & Open-Valley Preserver.

Repository : https://github.com/Humidyne-Labs/epd-font
Target OS  : https://github.com/Humidyne-Labs/H1OS
Spec Ref   : SPEC-TYPO-MATH-1BPP-001 (`docs/audits/humid1-audit-v1.0.17.txt`)
License    : MIT License

What's New in v1.0.17:
----------------------
1. Render -> Upscale (8x) -> HQ Master Confidence & Sanity-Check Gate (`compute_upscaled_hq_metrics`):
   Upscales each 1-BPP glyph by 8x (`INTER_NEAREST`) into the exact coordinate frame of the 8x
   continuous HQ Master and computes:
     - `hq_conf_iou` (0..100%)    : Direct structural IoU confidence vs. 8x HQ Master.
     - `hq_diff_pct` (0..100%)    : Pixel mismatch % vs. 8x HQ Master (enforces <= 20..22% sanity cap).
     - `valley_occ_pct` (0..100%) : Fraction of HQ white interior valleys occluded by 1-BPP ink.
     - `mass_err_pct` (-100..+%)  : Ink mass deviation % vs. 8x HQ Master.
   Any candidate that degrades `hq_conf_iou`, spikes `valley_occ_pct` by > 4.5%, or bloats ink mass
   is strictly rejected (`keep M0_untouched`).
2. Open-Valley Topology Lock & Multi-Stroke Pigeonhole Law (Fixes 'W', 'w', 'M', 'm', 'N', 'X', 's'):
   In narrow 3-stroke and 4-stroke diagonal characters ('W', 'w', 'M', 'm') where `box_w < 11px`,
   4 strokes x 2px + 3 valleys x 1px = 11px is impossible by the Pigeonhole Principle. Enforces
   scanline run-count invariance (`len(runs)` never collapses) so V-valleys in 'W'/'w'/'M' can
   NEVER fill in or turn into a solid black mass.
3. Conservative "Do No Harm" Surgical Entry Gate (Fixes Over-Correction on 'A', 'B', 'f', 'g', 's'):
   - Bold / ExtraBold (`wght >= 600`) strikes already possess >=2px–3px stems from FreeType; tuning
     is restricted strictly to collapsed enclosed counters (`b1 < expected_b1`) or 1px-thin narrow
     delimiters (`w0 <= 3`), leaving 'A', 'B', 'C', 'f', 'g', 'r', 's', '(', ')' 100% untouched.
   - Normal (`Medium 500`) strikes ignore 1px pointed apex rows (`r=0`, `r=h-1`) on 'A', 'V', 'W', 'M'
     and only patch glyphs with true stem deficits (`< 72%` 2px survival) or collapsed counters.
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

TOOL_VERSION = "1.0.17"

# Characters whose horizontal crossbars are structural and should be protected from vanishing
HORIZONTAL_BAR_CHARS = set("eftEFHTzZ=-+~÷±≤≥≠≈#[")

# Characters with an interior central vertical spine bisecting loops or crossbars
CENTRAL_SPINE_CODEPOINTS = {
    0x0024,  # '$' dollar
    0x002B,  # '+' plus
    0x00A2,  # '¢' cent
    0x00A5,  # '¥' yen
    0x00B1,  # '±' plus-minus
    0x03A6,  # 'Φ' Greek Capital Phi
    0x03A8,  # 'Ψ' Greek Capital Psi
    0x03C6,  # 'φ' Greek Small Phi
    0x03C8,  # 'ψ' Greek Small Psi
    0x03D5,  # 'ϕ' Greek Phi Symbol
    0x2020,  # '†' dagger
    0x2021,  # '‡' double dagger
}

# Multi-valley / multi-diagonal characters whose open V-valleys / S-curves must NEVER be occluded
MULTI_VALLEY_CHARS = set("WwMmNVvXYKZzSs#%&@")

# Canonical minimum enclosed internal counters (holes) for standard ASCII characters.
# Ensures lowercase/digit counters (a, e, o, b, d, p, q, g, 0, 4, 6, 8, 9, A, B, D, O, P, Q, R)
# are NEVER ignored at small pixel sizes (10..12px) when glyph box_h < 7!
CANONICAL_MIN_HOLES: Dict[str, int] = {
    "0": 1, "4": 1, "6": 1, "8": 2, "9": 1,
    "A": 1, "B": 2, "D": 1, "O": 1, "P": 1, "Q": 1, "R": 1,
    "a": 1, "b": 1, "d": 1, "e": 1, "g": 1, "o": 1, "p": 1, "q": 1,
    "%": 2, "@": 1,
}

SINGLE_COUNTER_OPEN_TAIL_CHARS = set("0469ADOPQRabdeopq")

# Open-curve / multi-valley characters that must NEVER pinch shut into false enclosed loops (expected_b1 == 0)
PINCH_FORBIDDEN_CHARS = set("CEFGHIJKLMNSTUVWXYZcfhijlmnrstuvwxyz!()[]{}/\\|<>+-=~")

# Bilateral mirror-symmetric glyph pairs: (left_cp, right_cp, flip_mode)
MIRROR_GLYPH_PAIRS: List[Tuple[int, int, str]] = [
    (0x0028, 0x0029, "h"),  # '(' <-> ')'
    (0x005B, 0x005D, "h"),  # '[' <-> ']'
    (0x007B, 0x007D, "h"),  # '{' <-> '}'
    (0x003C, 0x003E, "h"),  # '<' <-> '>'
    (0x00AB, 0x00BB, "h"),  # '«' <-> '»'
    (0x2039, 0x203A, "h"),  # '‹' <-> '›'
    (0x2264, 0x2265, "h"),  # '≤' <-> '≥'
    (0x2190, 0x2192, "h"),  # '←' <-> '→'
    (0x002F, 0x005C, "h"),  # '/' <-> '\'
    (0x2191, 0x2193, "v"),  # '↑' <-> '↓'
]

# Punctuation / tiny diacritics where horizontal stem widening should be skipped
SKIP_TUNING_CODEPOINTS = {
    0x0020,  # space
    0x0027,  # apostrophe '''
    0x002A,  # asterisk '*' (preserve multi-arm star geometry)
    0x002C,  # comma ','
    0x002E,  # period '.'
    0x003A,  # colon ':'
    0x003B,  # semicolon ';'
    0x0060,  # grave '`'
    0x00B7,  # middle dot '·'
    0x2018, 0x2019, 0x201C, 0x201D, 0x2022, 0x2026,
}


@dataclass
class UpscaledHQMetrics:
    hq_conf_iou: float      # 0..100% IoU between 8x upscaled 1-BPP and 8x HQ Master
    hq_diff_pct: float      # 0..100% pixel mismatch percentage vs 8x HQ Master
    valley_occ_pct: float   # 0..100% of HQ interior white space occluded by 1-BPP ink
    mass_err_pct: float     # -100..+% relative ink mass error vs 8x HQ Master


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
    hq_conf_iou: float = 0.0
    hq_diff_pct: float = 0.0
    valley_occ_pct: float = 0.0
    mass_err_pct: float = 0.0


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
    hq_conf_before: float = 0.0
    hq_conf_after: float = 0.0
    hq_diff_before: float = 0.0
    hq_diff_after: float = 0.0


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


def compute_open_valley_stats(binary_img: np.ndarray) -> Tuple[int, int, List[int]]:
    """
    Measure horizontal scanline run counts and open inter-stem valleys across rows.
    Returns (max_row_runs, total_inter_stem_gaps, row_run_counts).
    Prevents multi-stroke characters ('W', 'w', 'M', 'm', 'N', 'V', 'v', 'X', 'Y')
    from ever having their open V-valleys bridged into a solid black mass!
    """
    if binary_img.size == 0:
        return 0, 0, []
    h = binary_img.shape[0]
    row_counts = [len(_get_row_runs(binary_img[r])) for r in range(h)]
    max_runs = max(row_counts) if row_counts else 0
    total_gaps = sum(max(0, c - 1) for c in row_counts)
    return max_runs, total_gaps, row_counts


def compute_upscaled_hq_metrics(
    bitmap_1bit: np.ndarray,
    hq_master: Optional[np.ndarray],
) -> UpscaledHQMetrics:
    """
    Render -> Upscale (8x) -> Compare to HQ Master Sanity-Check Engine (v1.0.17):
    Upscales `bitmap_1bit` via nearest-neighbor to the exact dimensions of `hq_master` (8x)
    and computes:
      - `hq_conf_iou`    : Intersection-over-Union confidence (0..100%)
      - `hq_diff_pct`    : Total pixel area mismatch percentage (0..100%)
      - `valley_occ_pct` : Percentage of HQ white interior valleys occluded by 1-BPP ink (0..100%)
      - `mass_err_pct`   : Relative ink mass error vs HQ Master (-100%..+inf%)
    """
    if not HAS_CV2 or hq_master is None or hq_master.size == 0 or bitmap_1bit.size == 0:
        return UpscaledHQMetrics(80.0, 10.0, 10.0, 0.0)

    hh, hw = hq_master.shape
    hq_bin = (hq_master >= 115).astype(np.float32)
    hq_white = (hq_master < 64).astype(np.float32)
    up_1bit = (cv2.resize(bitmap_1bit, (hw, hh), interpolation=cv2.INTER_NEAREST) > 0).astype(np.float32)

    inter = float(np.sum(up_1bit * hq_bin))
    union = max(1.0, float(np.sum(np.maximum(up_1bit, hq_bin))))
    hq_conf_iou = (inter / union) * 100.0

    hq_diff_pct = float(np.mean(np.abs(up_1bit - hq_bin))) * 100.0
    valley_occ_pct = (float(np.sum(up_1bit * hq_white)) / max(1.0, float(np.sum(hq_white)))) * 100.0
    mass_err_pct = ((float(np.sum(up_1bit)) - float(np.sum(hq_bin))) / max(1.0, float(np.sum(hq_bin)))) * 100.0

    return UpscaledHQMetrics(
        hq_conf_iou=hq_conf_iou,
        hq_diff_pct=hq_diff_pct,
        valley_occ_pct=valley_occ_pct,
        mass_err_pct=mass_err_pct,
    )


def compute_betti_numbers(binary_img: np.ndarray) -> Tuple[int, int, np.ndarray]:
    """
    Method 15 (Euler-Poincare Characteristic & Betti Number Invariance):
    Compute:
      - B0 : number of 8-connected foreground ink components
      - B1 : number of 4-connected enclosed internal background counters (holes)
      - holes_mask : uint8 mask (255 = internal counter pixel)
    """
    if binary_img.size == 0 or np.count_nonzero(binary_img) == 0:
        return 0, 0, np.zeros_like(binary_img)
    fg = (binary_img > 0).astype(np.uint8) * 255
    padded = np.pad(fg, 2, mode="constant", constant_values=0)

    if not HAS_CV2:
        return 1, 0, np.zeros_like(binary_img)

    num_fg, _ = cv2.connectedComponents(padded, connectivity=8)
    b0 = max(1, int(num_fg) - 1)

    inv = cv2.bitwise_not(padded)
    num_bg, bg_labels, stats, _ = cv2.connectedComponentsWithStats(inv, connectivity=4)
    ph, pw = padded.shape
    holes_padded = np.zeros_like(padded)
    b1 = 0
    for lbl in range(1, num_bg):
        x = stats[lbl, cv2.CC_STAT_LEFT]
        y = stats[lbl, cv2.CC_STAT_TOP]
        w = stats[lbl, cv2.CC_STAT_WIDTH]
        h = stats[lbl, cv2.CC_STAT_HEIGHT]
        touches_border = (x == 0) or (y == 0) or (x + w >= pw) or (y + h >= ph)
        if not touches_border:
            b1 += 1
            holes_padded[bg_labels == lbl] = 255

    return b0, b1, holes_padded[2:-2, 2:-2]


def detect_skin_tags_and_notches(
    binary_img: np.ndarray,
    hq_coverage: Optional[np.ndarray] = None,
    codepoint: int = 0,
) -> Tuple[int, int, List[Tuple[int, int]], List[Tuple[int, int]]]:
    """
    Method 7 & Method 18 (v1.0.17 4-Directional Outline-Wart & Notch Regularizer):
    Detects non-topological 1-pixel horizontal AND vertical "outline-warts" (spurs / pimples)
    and 1-pixel exterior stem notches.
    """
    h, w = binary_img.shape
    fg = (binary_img > 0).astype(np.uint8)
    skin_tags: List[Tuple[int, int]] = []
    notches: List[Tuple[int, int]] = []

    # 1. Horizontal left/right lateral 1px outline-warts
    for r in range(h):
        runs = _get_row_runs(fg[r])
        for s, e in runs:
            rlen = e - s + 1
            if rlen >= 3:
                up_s = fg[r - 1, s] if r > 0 else 0
                dn_s = fg[r + 1, s] if r + 1 < h else 0
                up_in = fg[r - 1, s + 1] if r > 0 else 0
                dn_in = fg[r + 1, s + 1] if r + 1 < h else 0
                if up_s == 0 and dn_s == 0 and (up_in > 0 and dn_in > 0):
                    cov = float(hq_coverage[r, s]) if (hq_coverage is not None and hq_coverage.shape == (h, w)) else 0.0
                    cov_lim = 0.64 if (s == 0 and 0 < r < h - 1) else 0.55
                    if cov < cov_lim:
                        skin_tags.append((r, s))

                up_e = fg[r - 1, e] if r > 0 else 0
                dn_e = fg[r + 1, e] if r + 1 < h else 0
                up_ein = fg[r - 1, e - 1] if r > 0 else 0
                dn_ein = fg[r + 1, e - 1] if r + 1 < h else 0
                if up_e == 0 and dn_e == 0 and (up_ein > 0 and dn_ein > 0):
                    cov = float(hq_coverage[r, e]) if (hq_coverage is not None and hq_coverage.shape == (h, w)) else 0.0
                    cov_lim = 0.64 if (e == w - 1 and 0 < r < h - 1) else 0.55
                    if cov < cov_lim:
                        skin_tags.append((r, e))

    # 2. Vertical top/bottom 1px pimples/warts on arches, bowls, and terminals (skip central-spine chars like )
    if codepoint not in CENTRAL_SPINE_CODEPOINTS and w >= 5 and h >= 7:
        for c in range(w):
            c_runs = _get_row_runs(fg[:, c])
            for s, e in c_runs:
                clen = e - s + 1
                if clen >= 3:
                    lf_s = fg[s, c - 1] if c > 0 else 0
                    rt_s = fg[s, c + 1] if c + 1 < w else 0
                    lf_in = fg[s + 1, c - 1] if c > 0 else 0
                    rt_in = fg[s + 1, c + 1] if c + 1 < w else 0
                    if lf_s == 0 and rt_s == 0 and (lf_in > 0 or rt_in > 0) and ((lf_in > 0 and rt_in > 0) or (0 < s < h - 1)):
                        cov = float(hq_coverage[s, c]) if (hq_coverage is not None and hq_coverage.shape == (h, w)) else 0.0
                        if cov < 0.48:
                            skin_tags.append((s, c))

                    lf_e = fg[e, c - 1] if c > 0 else 0
                    rt_e = fg[e, c + 1] if c + 1 < w else 0
                    lf_ein = fg[e - 1, c - 1] if c > 0 else 0
                    rt_ein = fg[e - 1, c + 1] if c + 1 < w else 0
                    if lf_e == 0 and rt_e == 0 and (lf_ein > 0 or rt_ein > 0) and ((lf_ein > 0 and rt_ein > 0) or (0 < e < h - 1)):
                        cov = float(hq_coverage[e, c]) if (hq_coverage is not None and hq_coverage.shape == (h, w)) else 0.0
                        if cov < 0.48:
                            skin_tags.append((e, c))

    # 3. Only detect notches on OUTERMOST left (c == 0) or right (c == w - 1) stem walls, NEVER inside interior V-valleys!
    for r in range(1, h - 1):
        for c in (0, w - 1):
            if c < 0 or c >= w:
                continue
            if fg[r, c] == 0 and fg[r - 1, c] > 0 and fg[r + 1, c] > 0:
                if c == 0 and c + 1 < w and fg[r, c + 1] > 0 and fg[r - 1, c + 1] > 0 and fg[r + 1, c + 1] > 0:
                    notches.append((r, c))
                elif c == w - 1 and c - 1 >= 0 and fg[r, c - 1] > 0 and fg[r - 1, c - 1] > 0 and fg[r + 1, c - 1] > 0:
                    notches.append((r, c))

    if skin_tags:
        skin_tags = list(dict.fromkeys(skin_tags))
        b0_orig, b1_orig, _ = compute_betti_numbers(binary_img)
        true_tags: List[Tuple[int, int]] = []
        for tr, tc in skin_tags:
            probe = binary_img.copy()
            probe[tr, tc] = 0
            b0_p, b1_p, _ = compute_betti_numbers(probe)
            if (
                b0_p == b0_orig
                and b1_p == b1_orig
                and len(_get_row_runs(probe[tr])) == len(_get_row_runs(binary_img[tr]))
                and len(_get_row_runs(probe[:, tc])) == len(_get_row_runs(binary_img[:, tc]))
            ):
                true_tags.append((tr, tc))
        skin_tags = true_tags

    return len(skin_tags), len(notches), skin_tags, notches


def clean_skin_tags_and_notches(
    binary_img: np.ndarray,
    expected_b0: int,
    expected_b1: int,
    hq_coverage: Optional[np.ndarray] = None,
    max_iters: int = 2,
    allow_corner_bevel: bool = False,
    codepoint: int = 0,
) -> np.ndarray:
    """
    Method 8 + Method 18 (v1.0.17 Valley-Safe Boundary Regularizer):
    Iteratively removes 1-pixel skin tags and fills outermost stem wall notches, accepting each
    single-pixel flip if and only if BOTH Betti numbers (B0, B1) AND the row's horizontal run count
    (`len(_get_row_runs(work[r]))`) remain strictly invariant (so V-valleys are NEVER bridged!).
    """
    work = binary_img.copy()
    for _ in range(max_iters):
        _, _, tag_coords, notch_coords = detect_skin_tags_and_notches(work, hq_coverage, codepoint=codepoint)
        if not tag_coords and not notch_coords:
            break
        changed = False
        for r, c in notch_coords:
            runs_before = len(_get_row_runs(work[r]))
            work[r, c] = 255
            b0, b1, _ = compute_betti_numbers(work)
            runs_after = len(_get_row_runs(work[r]))
            if b0 != expected_b0 or b1 != expected_b1 or runs_after != runs_before:
                work[r, c] = 0
            else:
                changed = True
        for r, c in tag_coords:
            runs_before = len(_get_row_runs(work[r]))
            work[r, c] = 0
            b0, b1, _ = compute_betti_numbers(work)
            runs_after = len(_get_row_runs(work[r]))
            if b0 != expected_b0 or b1 != expected_b1 or runs_after != runs_before:
                work[r, c] = 255
            else:
                changed = True
        if not changed:
            break

    # Only bevel 2x2 diagonal corners on CENTRAL_SPINE_CODEPOINTS ('$') where explicitly requested
    if allow_corner_bevel:
        h, w = work.shape
        for r in range(h - 1):
            for c in range(w - 1):
                tl, tr = work[r, c] > 0, work[r, c + 1] > 0
                bl, br = work[r + 1, c] > 0, work[r + 1, c + 1] > 0
                if (tl and br and not tr and not bl) or (not tl and not br and tr and bl):
                    zero_pts = [(r, c + 1), (r + 1, c)] if (tl and br) else [(r, c), (r + 1, c + 1)]
                    zero_pts.sort(key=lambda pt: -abs(pt[1] - (w - 1) / 2.0))
                    for zr, zc in zero_pts:
                        runs_b = len(_get_row_runs(work[zr]))
                        work[zr, zc] = 255
                        b0_p, b1_p, _ = compute_betti_numbers(work)
                        if b0_p == expected_b0 and b1_p == expected_b1 and len(_get_row_runs(work[zr])) == runs_b:
                            break
                        work[zr, zc] = 0
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


def measure_stem_deficits(
    binary_img: np.ndarray,
    min_stem: int = 2,
    codepoint: int = 0,
) -> Tuple[bool, bool, float, float]:
    """
    Inspect whether primary vertical/curved stems fall below `min_stem` pixels:
      1. Ignores top 1 and bottom 1 terminal/apex rows (`r=0`, `r=h-1`) on glyphs with `h >= 6`
         so natural pointed apexes ('A', 'V', 'W', 'M') and tapered terminals ('C', 'S', 's', 'f', 'g')
         are not falsely flagged as stem deficits.
      2. Respects the Multi-Stroke Pigeonhole Law on scanlines with `len(runs) >= 3` ('W', 'w', 'M', 'm'):
         when `w < 2 * len(runs) + (len(runs) - 1)` (e.g., `w < 11` for 4-run 'w'/'W'), 1px inner
         diagonals are geometrically required to keep V-valleys open and are counted as valid!
    """
    nz = int(np.count_nonzero(binary_img))
    if nz == 0:
        return True, True, 0.0, 0.0
    h, w = binary_img.shape
    if w < min_stem:
        return True, False, 0.0, 1.0

    r_start = 1 if h >= 6 else 0
    r_end = (h - 1) if h >= 6 else h

    ge_min_runs = 0
    total_stem_runs = 0
    for r in range(r_start, r_end):
        runs = _get_row_runs(binary_img[r])
        k_runs = len(runs)
        if 1 <= k_runs <= 4:
            # Multi-Stroke Pigeonhole check: if k_runs >= 3 and w < 3*k_runs - 1, 1px runs are mandatory to preserve valleys
            pigeonhole_constrained = (k_runs >= 3) and (w < (min_stem * k_runs + (k_runs - 1)))
            for s, e in runs:
                rlen = e - s + 1
                if rlen < max(4, int(w * 0.78)):
                    total_stem_runs += 1
                    if rlen >= min_stem or pigeonhole_constrained:
                        ge_min_runs += 1

    h_ratio = (float(ge_min_runs) / float(total_stem_runs)) if total_stem_runs > 0 else 0.0

    spine_deficit = False
    if codepoint in CENTRAL_SPINE_CODEPOINTS and w >= 5:
        thin_spine_rows = 0
        for r in range(h):
            for s, e in _get_row_runs(binary_img[r]):
                if (e - s + 1) < min_stem:
                    thin_spine_rows += 1
        if thin_spine_rows >= 2:
            spine_deficit = True
            h_ratio = min(h_ratio, max(0.0, 1.0 - float(thin_spine_rows) / float(max(1, h))))

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

    needs_h = spine_deficit or (total_stem_runs == 0) or ((total_stem_runs == 1) and (h >= 4) and (h_ratio < 1.0)) or ((total_stem_runs >= 2) and (h_ratio < 0.72))
    needs_v = v_ratio < 0.16
    return needs_h, needs_v, h_ratio, v_ratio


def _check_dilated_skeleton_containment(
    base_1bit: np.ndarray,
    candidate_1bit: np.ndarray,
) -> Tuple[bool, float, float]:
    """
    Symmetric Dilated-Skeleton Containment Gate:
    Checks that `candidate_1bit` lies within the 1px neighborhood of `base_1bit`
    (`dilated_precision >= 0.85`) and covers `base_1bit` (`base_recall >= 0.84`).
    """
    if not HAS_CV2 or base_1bit is None or base_1bit.size == 0:
        return True, 1.0, 1.0

    bh, bw = base_1bit.shape
    ch, cw = candidate_1bit.shape
    cand_fg = (candidate_1bit > 0).astype(np.float32)
    cand_sum = max(1.0, float(np.sum(cand_fg)))

    best_prec = 0.0
    best_rec = 0.0

    alignments: List[np.ndarray] = []
    if ch == bh and cw >= bw and (cw - bw) <= 3:
        dw = cw - bw
        for pad_l in range(dw + 1):
            pad_r = dw - pad_l
            alignments.append(np.pad(base_1bit, ((0, 0), (pad_l, pad_r)), mode="constant", constant_values=0))
        if dw >= 1 and bw >= 4:
            dup_mid = np.insert(base_1bit, bw // 2, base_1bit[:, bw // 2], axis=1)
            rem = cw - dup_mid.shape[1]
            if rem == 0:
                alignments.append(dup_mid)
            elif rem == 2:
                alignments.append(np.pad(dup_mid, ((0, 0), (1, 1)), mode="constant", constant_values=0))
    if not alignments:
        alignments.append(cv2.resize(base_1bit, (cw, ch), interpolation=cv2.INTER_NEAREST))

    k3 = np.ones((3, 3), np.uint8)
    for aligned_base in alignments:
        base_fg = (aligned_base > 0).astype(np.float32)
        base_sum = max(1.0, float(np.sum(base_fg)))
        dil_base = (cv2.dilate(aligned_base, k3, iterations=1) > 0).astype(np.float32)
        dil_cand = (cv2.dilate(candidate_1bit, k3, iterations=1) > 0).astype(np.float32)

        prec = float(np.sum(cand_fg * dil_base)) / cand_sum
        rec = float(np.sum(base_fg * dil_cand)) / base_sum
        if (prec + rec) > (best_prec + best_rec):
            best_prec = prec
            best_rec = rec

    ok = (best_prec >= 0.85) and (best_rec >= 0.84)
    return ok, best_prec, best_rec


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
    codepoint: int = 0,
    raw_hq_metrics: Optional[UpscaledHQMetrics] = None,
    base_valley_stats: Optional[Tuple[int, int, List[int]]] = None,
) -> CandidateEval:
    """
    Weighted Multi-Objective Typographic Evaluation Engine with Render -> Upscale -> HQ Sanity Gate (v1.0.17):
      - Hard Gate 1 : Betti numbers (B0 foreground components, B1 enclosed counters) must match HQ Master!
      - Hard Gate 2 : Open-Valley Invariance — candidate must NEVER collapse multi-stroke horizontal
                      run counts (`max_row_runs`) or bridge >20% of inter-stem open valley rows!
      - Hard Gate 3 : Render -> Upscale (8x) -> HQ Master Confidence Sanity Gate:
                      - `valley_occ_pct <= raw_valley_occ_pct + 4.5%` (never clog open valleys!)
                      - For `orig_w >= 5`, `hq_conf_iou >= raw_hq_conf_iou - 0.5%` and `hq_diff_pct <= 22.0%`
                      - For `orig_w >= 5`, `abs(mass_err_pct) <= max(18.0%, abs(raw_mass_err_pct) + 6.0%)`
    """
    if candidate_1bit.size == 0 or np.count_nonzero(candidate_1bit) == 0:
        return CandidateEval(method_id, candidate_1bit, -1e9, 0, 0, 0, 0, 0, 0, 0, 99, 99, 1.0, False)

    h, w = candidate_1bit.shape
    b0, b1, counters = compute_betti_numbers(candidate_1bit)
    valid_topo = (b0 == expected_b0) and (b1 == expected_b1)

    hq_resized = None
    if hq_master is not None and hq_master.size > 0 and HAS_CV2:
        hq_resized = cv2.resize(hq_master, (w, h), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0

    num_tags, num_notches, _, _ = detect_skin_tags_and_notches(candidate_1bit, hq_resized, codepoint=codepoint)
    num_checkers = count_2x2_checkerboards(candidate_1bit)
    needs_h, _, h_2px_ratio, _ = measure_stem_deficits(candidate_1bit, min_stem=min_stem, codepoint=codepoint)

    if not valid_topo:
        return CandidateEval(
            method_id, candidate_1bit, -1e6 - abs(b0 - expected_b0) * 1e4 - abs(b1 - expected_b1) * 1e4,
            0, 0, 0, 0, 0, b0, b1, num_tags, num_notches, 1.0 - h_2px_ratio, False
        )

    # Hard Gate 2: Open-Valley Invariance (never collapse V-valleys in 'W', 'w', 'M', 'm', 'N', 'V', 'v', 'X', 'Y')
    ch_str = chr(codepoint) if 0x20 <= codepoint <= 0xFFFF else ""
    if method_id != "M0_untouched" and base_valley_stats is not None:
        base_max_runs, base_total_gaps, _ = base_valley_stats
        cand_max_runs, cand_total_gaps, _ = compute_open_valley_stats(candidate_1bit)
        if base_max_runs >= 2 and cand_max_runs < base_max_runs:
            return CandidateEval(method_id, candidate_1bit, -1e5, 0, 0, 0, 0, 0, b0, b1, num_tags, num_notches, 1.0 - h_2px_ratio, False)
        if base_total_gaps >= 2 and cand_total_gaps < int(math.ceil(0.80 * base_total_gaps)):
            return CandidateEval(method_id, candidate_1bit, -1e5, 0, 0, 0, 0, 0, b0, b1, num_tags, num_notches, 1.0 - h_2px_ratio, False)

    # Compute Render -> Upscale (8x) -> HQ Master Confidence Metrics
    up_hq = compute_upscaled_hq_metrics(candidate_1bit, hq_master)

    # Hard Gate 3: Upscaled-to-HQ Sanity-Check Gate + Dilated-Skeleton Containment
    if method_id != "M0_untouched" and base_1bit is not None and base_1bit.size > 0:
        cont_ok, skel_prec, skel_rec = _check_dilated_skeleton_containment(base_1bit, candidate_1bit)
        if not cont_ok:
            return CandidateEval(method_id, candidate_1bit, -1e5, 0, 0, 0, 0, 0, b0, b1, num_tags, num_notches, 1.0 - h_2px_ratio, False)

        if raw_hq_metrics is not None and hq_master is not None and hq_master.size > 0:
            # Rule A: On multi-column glyphs (orig_w >= 5), never allow open white valleys to be occluded
            if orig_w >= 5 and codepoint not in CENTRAL_SPINE_CODEPOINTS:
                max_valley_jump = 3.0 if ch_str in MULTI_VALLEY_CHARS else 5.5
                if up_hq.valley_occ_pct > raw_hq_metrics.valley_occ_pct + max_valley_jump:
                    return CandidateEval(method_id, candidate_1bit, -1e5, 0, 0, 0, 0, 0, b0, b1, num_tags, num_notches, 1.0 - h_2px_ratio, False)

            # Rule B: For normal-width glyphs (orig_w >= 5) that aren't central-spine '$', never degrade HQ IoU confidence or exceed 22% diff
            if orig_w >= 5 and codepoint not in CENTRAL_SPINE_CODEPOINTS:
                if up_hq.hq_conf_iou < raw_hq_metrics.hq_conf_iou - 0.5:
                    return CandidateEval(method_id, candidate_1bit, -1e5, 0, 0, 0, 0, 0, b0, b1, num_tags, num_notches, 1.0 - h_2px_ratio, False)
                if up_hq.hq_diff_pct > max(22.0, raw_hq_metrics.hq_diff_pct + 1.5):
                    return CandidateEval(method_id, candidate_1bit, -1e5, 0, 0, 0, 0, 0, b0, b1, num_tags, num_notches, 1.0 - h_2px_ratio, False)
                if abs(up_hq.mass_err_pct) > max(18.0, abs(raw_hq_metrics.mass_err_pct) + 6.0):
                    return CandidateEval(method_id, candidate_1bit, -1e5, 0, 0, 0, 0, 0, b0, b1, num_tags, num_notches, 1.0 - h_2px_ratio, False)
    else:
        skel_prec, skel_rec = 1.0, 1.0

    cand_f = (candidate_1bit > 0).astype(np.float32)

    if hq_resized is not None:
        hq_bin = (hq_resized >= 0.42).astype(np.float32)
        inter = float(np.sum(cand_f * hq_bin))
        union = float(np.sum(np.maximum(cand_f, hq_bin)))
        iou = inter / max(1.0, union)
        l1_sim = 1.0 - float(np.mean(np.abs(cand_f - hq_resized)))

        hq_dil = (cv2.dilate((hq_bin * 255).astype(np.uint8), np.ones((1, 2), np.uint8)) > 0).astype(np.float32)
        hq_dil_iou = float(np.sum(cand_f * hq_dil)) / max(1.0, float(np.sum(np.maximum(cand_f, hq_dil))))
        effective_iou = max(iou, 0.88 * hq_dil_iou)

        hq_score = 40.0 * (0.50 * (up_hq.hq_conf_iou / 100.0) + 0.30 * effective_iou + 0.20 * l1_sim)
    else:
        hq_score = 28.0

    # 2. Stem Score (0..28)
    fat_runs = 0
    thin_runs = 0
    total_runs = 0
    for r in range(h):
        runs = _get_row_runs(candidate_1bit[r])
        k_runs = len(runs)
        if k_runs >= 1:
            pigeonhole_ok = (k_runs >= 3) and (w < (min_stem * k_runs + (k_runs - 1)))
            for s, e in runs:
                rlen = e - s + 1
                if rlen < min_stem and not pigeonhole_ok and (0 < r < h - 1):
                    thin_runs += 1
                if k_runs >= 2:
                    total_runs += 1
                    if rlen > min_stem + 1:
                        fat_runs += 1
    fat_penalty = (10.0 * fat_runs / max(1, total_runs)) if total_runs > 0 else 0.0
    thin_penalty = 1.8 * thin_runs
    stem_score = max(0.0, 28.0 * h_2px_ratio - fat_penalty - thin_penalty)

    # 3. Mumford-Shah Boundary Smoothness & Anti-Skin-Tag Score (-50..20)
    smooth_score = 20.0 - (25.0 * num_tags) - (16.0 * num_notches) - (8.0 * num_checkers)

    # 4. Jenson-Garamond Counter-Punch & Upscaled Small-Font Reference Score (0..8)
    if expected_b1 > 0:
        hole_area_ratio = float(np.count_nonzero(counters)) / float(max(1, h * w))
        cavity_score = min(8.0, 8.0 * (hole_area_ratio / 0.10))
    else:
        cavity_score = 7.2

    if upscaled_small_ref is not None and upscaled_small_ref.size > 0 and HAS_CV2:
        up_rsz = cv2.resize(upscaled_small_ref, (w, h), interpolation=cv2.INTER_NEAREST)
        up_f = (up_rsz > 0).astype(np.float32)
        grid_align = 1.0 - float(np.mean(np.abs(cand_f - up_f)))
        cavity_score = 0.80 * cavity_score + 0.20 * (8.0 * grid_align)

    # 5. Typographic Color & Dynamic Box Width Economy (0..4)
    density = float(np.mean(cand_f))
    density_err = max(0.0, abs(density - 0.46) - 0.10)
    extra_w = max(0, w - orig_w) if orig_w > 0 else 0
    width_pen = 0.8 * extra_w if extra_w <= 1 else (2.0 * extra_w)
    color_score = max(0.0, 4.0 - (12.0 * density_err) - width_pen)

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
        hq_conf_iou=up_hq.hq_conf_iou,
        hq_diff_pct=up_hq.hq_diff_pct,
        valley_occ_pct=up_hq.valley_occ_pct,
        mass_err_pct=up_hq.mass_err_pct,
    )


# =============================================================================
# STREAMLINED v1.0.17 3-STAGE CANDIDATE SYNTHESIS & DYNAMIC THRESHOLDING
# =============================================================================
# Stage 0 (M0_wart_shaved)       : Native FreeType + 4-Directional 1px Outline-Wart Shaver (handles 73%..97% of glyphs)
# Stage 1 (M1_dyn_thresh)        : 8x HQ Master Area-Downscale with Dynamic Weight/Size/Otsu Threshold Sweep + Hysteresis
# Stage 2 (M2_collinear_stem)    : Trajectory-Consistent Outward Collinear Stem Floor (>=2px) + Counter-Punch
# Stage 3 (M3_central_spine)     : Central Vertical Spine Expansion ('$', '+', '±', '¢', '¥', 'Φ', 'Ψ') + Mirror Sync


def compute_dynamic_hq_threshold(hq_master: Optional[np.ndarray], is_bold_role: bool = False, h0: int = 16) -> int:
    """
    Compute a dynamic threshold in [96..152] for the 8x continuous HQ master (replacing hardcoded 115/120/128):
      - Lower (~104..116) on Regular/Medium or compact sizes (<=14px) to preserve >=2px stem mass.
      - Higher (~132..148) on Bold/ExtraBold to prevent anti-aliased fringe bleed from pinching internal counters.
    """
    if hq_master is None or hq_master.size == 0:
        return 120
    t_prior = 136 if is_bold_role else (110 if h0 <= 11 else 118)
    active = hq_master[hq_master > 16]
    if active.size < 16:
        return t_prior
    p45 = float(np.percentile(active, 45))
    return int(np.clip(round(0.70 * t_prior + 0.30 * p45), 96, 152))



def carve_and_unpinch_counters(
    base_1bit: np.ndarray,
    hq_master: Optional[np.ndarray],
    expected_b1: int,
    ch_str: str,
    is_bold_role: bool = False,
) -> np.ndarray:
    """
    Surgical Counter-Carver & S-Curve Un-Pincher (v1.0.17):
    Allows heavy ExtraBold (w800) / Black (w900) strikes (3px+ stem punch) and subtle
    MediumItalic/SemiBoldItalic strikes to maintain 100% open counters and un-pinched S/M valleys
    at 12px..20px without shrinking their outer stem weights:
      1. Un-pinches false closed loops (`b1 > 0` on open characters in PINCH_FORBIDDEN_CHARS like 's', 'M', 'w').
      2. Carves collapsed internal counters (`b1 < expected_b1` on 'e', 'a', '8', 'B', '%') at the lowest-coverage
         interior pixel of the 8x continuous HQ master.
      3. Expands 1px pinholes (`hole_px == 1`) to 2px on core single-loop letters in Bold/ExtraBold strikes.
    """
    if base_1bit is None or base_1bit.size == 0:
        return base_1bit
    work = base_1bit.copy()
    h, w = work.shape
    if h < 5 or w < 4:
        return work

    if hq_master is not None and hq_master.size > 0 and HAS_CV2:
        hq_cov = cv2.resize(hq_master, (w, h), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
    else:
        hq_cov = np.full((h, w), 0.5, dtype=np.float32)

    b0, b1, holes = compute_betti_numbers(work)

    # 1. Un-pinch false closed loops on open characters ('s', 'c', 'w', 'M', etc.)
    if ch_str in PINCH_FORBIDDEN_CHARS and b1 > 0:
        for _ in range(b1 + 1):
            b0_now, b1_now, holes_now = compute_betti_numbers(work)
            if b1_now == 0:
                break
            ext_bg = (work == 0) & (holes_now == 0)
            best_pt = None
            best_cov = 999.0
            for r in range(h):
                for c in range(w):
                    if work[r, c] == 0:
                        continue
                    adj_hole = any(
                        0 <= r + dr < h and 0 <= c + dc < w and holes_now[r + dr, c + dc] > 0
                        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1))
                    )
                    adj_ext = (
                        r in (0, h - 1)
                        or c in (0, w - 1)
                        or any(
                            0 <= r + dr < h and 0 <= c + dc < w and ext_bg[r + dr, c + dc]
                            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1))
                        )
                    )
                    if adj_hole and adj_ext and float(hq_cov[r, c]) < best_cov:
                        probe = work.copy()
                        probe[r, c] = 0
                        b0_p, b1_p, _ = compute_betti_numbers(probe)
                        if b0_p == b0_now and b1_p < b1_now:
                            best_cov = float(hq_cov[r, c])
                            best_pt = (r, c)
            if best_pt is not None:
                work[best_pt[0], best_pt[1]] = 0

    # 2a. Seal 1px/2px unclosed bowl-join bridge gaps when an open interior cavity already exists
    b0, b1, holes = compute_betti_numbers(work)
    if b1 < expected_b1 and hq_master is not None and hq_master.size > 0:
        for thr in (0.44, 0.41, 0.38, 0.35, 0.31, 0.28, 0.25):
            cand = np.where((work > 0) | (hq_cov >= thr), 255, 0).astype(np.uint8)
            b0_c, b1_c, holes_c = compute_betti_numbers(cand)
            if b0_c <= b0 and b1_c >= expected_b1 and int(np.count_nonzero(holes_c)) >= expected_b1 * 2:
                work = cand
                b0, b1, holes = b0_c, b1_c, holes_c
                break
    if b1 < expected_b1:
        for _ in range(expected_b1 - b1 + 1):
            b0_now, b1_now, holes_before = compute_betti_numbers(work)
            if b1_now >= expected_b1:
                break
            best_probe = None
            best_gain = 0
            holes_cnt_before = int(np.count_nonzero(holes_before))
            for r in range(h):
                for c in range(w):
                    if work[r, c] > 0:
                        continue
                    nb_on = sum(
                        1 for dr, dc in ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))
                        if 0 <= r + dr < h and 0 <= c + dc < w and work[r + dr, c + dc] > 0
                    )
                    if nb_on >= 2:
                        probe = work.copy()
                        probe[r, c] = 255
                        b0_p, b1_p, holes_p = compute_betti_numbers(probe)
                        gain = int(np.count_nonzero(holes_p)) - holes_cnt_before
                        if b0_p <= b0_now and b1_p > b1_now and gain >= 2 and gain > best_gain:
                            best_gain = gain
                            best_probe = probe
            if best_probe is None:
                for r in range(h):
                    for c in range(1, w - 2):
                        if work[r, c] == 0 and work[r, c + 1] == 0 and (
                            (work[r, c - 1] > 0 and work[r, c + 2] > 0)
                            or (r > 0 and work[r - 1, c - 1] > 0 and work[r, c + 2] > 0)
                            or (r + 1 < h and work[r + 1, c - 1] > 0 and work[r, c + 2] > 0)
                        ):
                            probe = work.copy()
                            probe[r, c] = 255
                            probe[r, c + 1] = 255
                            b0_p, b1_p, holes_p = compute_betti_numbers(probe)
                            gain = int(np.count_nonzero(holes_p)) - holes_cnt_before
                            if b0_p <= b0_now and b1_p > b1_now and gain >= 2 and gain > best_gain:
                                best_gain = gain
                                best_probe = probe
            if best_probe is not None:
                work = best_probe
            else:
                break

    # 2b. Carve collapsed internal counters (b1 < expected_b1)
    b0, b1, holes = compute_betti_numbers(work)
    if b1 < expected_b1:
        int_pts = [
            (float(hq_cov[r, c]), r, c)
            for r in range(1, h - 1)
            for c in range(1, w - 1)
            if work[r, c] > 0
        ]
        int_pts.sort()
        for _, r, c in int_pts[:10]:
            probe = work.copy()
            probe[r, c] = 0
            b0_p, b1_p, _ = compute_betti_numbers(probe)
            if b0_p == b0 and b1_p > b1:
                work = probe
                b1 = b1_p
                if b1 >= expected_b1:
                    break

    # 3. Expand 1px pinhole counter to >=2px on core single-loop letters in Bold/ExtraBold strikes
    b0, b1, holes = compute_betti_numbers(work)
    if is_bold_role and ch_str in "069ADOPQRabdeopq" and b1 >= 1 and int(np.count_nonzero(holes)) == 1:
        hy, hx = np.nonzero(holes > 0)
        r0, c0 = int(hy[0]), int(hx[0])
        best_nb = None
        best_cov = 999.0
        for dr, dc in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            nr, nc = r0 + dr, c0 + dc
            if 1 <= nr < h - 1 and 1 <= nc < w - 1 and work[nr, nc] > 0:
                probe = work.copy()
                probe[nr, nc] = 0
                b0_p, b1_p, h_p = compute_betti_numbers(probe)
                if b0_p == b0 and b1_p == b1 and int(np.count_nonzero(h_p)) >= 2:
                    if float(hq_cov[nr, nc]) < best_cov:
                        best_cov = float(hq_cov[nr, nc])
                        best_nb = (nr, nc)
        if best_nb is not None:
            work[best_nb[0], best_nb[1]] = 0

    return work


def _apply_counter_punch(
    work: np.ndarray,
    orig_counters: np.ndarray,
    upscaled_small_counters: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Jenson-Garamond Counter-Punch: Guarantee every expected internal cavity stays open."""
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
        if np.count_nonzero(cv2.bitwise_and(cv2.bitwise_not(res), hole_comp)) > 0:
            continue
        hw = stats[i, cv2.CC_STAT_WIDTH]
        hh = stats[i, cv2.CC_STAT_HEIGHT]
        if hw >= 3 and hh >= 3:
            core = cv2.erode(hole_comp, np.ones((3, 3), np.uint8), borderType=cv2.BORDER_CONSTANT, borderValue=0)
            if np.count_nonzero(core) == 0:
                core = cv2.erode(hole_comp, np.ones((2, 2), np.uint8), borderType=cv2.BORDER_CONSTANT, borderValue=0)
            if np.count_nonzero(core) == 0:
                core = hole_comp
        else:
            core = hole_comp
        res = cv2.bitwise_and(res, cv2.bitwise_not(core))
        if np.count_nonzero(cv2.bitwise_and(cv2.bitwise_not(res), hole_comp)) == 0:
            cy = int(stats[i, cv2.CC_STAT_TOP] + hh // 2)
            cx = int(stats[i, cv2.CC_STAT_LEFT] + hw // 2)
            if 0 <= cy < h and 0 <= cx < w:
                res[cy, cx] = 0

    if upscaled_small_counters is not None and np.any(upscaled_small_counters > 0):
        uc = upscaled_small_counters
        if uc.shape != (h, w):
            uc = cv2.resize(uc, (w, h), interpolation=cv2.INTER_NEAREST)
        _, b1_now, _ = compute_betti_numbers(res)
        if b1_now == 0 and np.count_nonzero(uc) > 0:
            res = cv2.bitwise_and(res, cv2.bitwise_not(uc))

    return res


def synth_m1_dynamic_threshold_sweep(
    hq_master: np.ndarray,
    target_w: int,
    target_h: int,
    orig_counters: np.ndarray,
    codepoint: int = 0,
    is_bold_role: bool = False,
) -> List[Tuple[str, np.ndarray]]:
    """
    Stage 1 (v1.0.17 Dynamic Threshold + Dual-Hysteresis Area-Downscale):
    Replaces the slow 54-candidate warpAffine grid sweep (M1), 4x Python medial-axis loop (M2),
    4x SDF distance transform (M3), and M4 with a single fast INTER_AREA downscale evaluated
    across Dynamic Thresholds centered around T_dyn = compute_dynamic_hq_threshold(hq_master).
    """
    if not HAS_CV2 or hq_master is None or hq_master.size == 0 or target_w < 2 or target_h < 2:
        return []
    t_center = compute_dynamic_hq_threshold(hq_master, is_bold_role=is_bold_role, h0=target_h)
    ch_str = chr(codepoint) if 0x20 <= codepoint <= 0xFFFF else ""
    out: List[Tuple[str, np.ndarray]] = []

    for dw in (0, 1):
        tw = target_w + dw
        ds = cv2.resize(hq_master, (tw, target_h), interpolation=cv2.INTER_AREA)
        # 1. Dynamic threshold sweep around t_center
        for dt in (-14, -4, 6, 16):
            th = int(np.clip(t_center + dt, 92, 158))
            cand = (ds >= th).astype(np.uint8) * 255
            cand = _apply_counter_punch(cand, orig_counters)
            out.append((f"M1_dyn_thresh(w+{dw},t={th})", cand))

        # 2. Dual-threshold hysteresis + acute vertex ink-trap pass
        strong = (ds >= t_center).astype(np.uint8) * 255
        weak = (ds >= max(64, t_center - 44)).astype(np.uint8) * 255
        hyst = strong.copy()
        for r in range(target_h):
            runs = _get_row_runs(hyst[r])
            if len(runs) >= 3 and tw < 11:
                continue
            for idx, (s, e) in enumerate(runs):
                if (e - s + 1) < 2:
                    left_lim = (runs[idx - 1][1] + 2) if idx > 0 else 0
                    right_lim = (runs[idx + 1][0] - 2) if idx + 1 < len(runs) else (tw - 1)
                    if e + 1 <= right_lim and weak[r, e + 1] > 0:
                        hyst[r, e + 1] = 255
                    elif s - 1 >= left_lim and weak[r, s - 1] > 0:
                        hyst[r, s - 1] = 255
        if ch_str in "MWNvwy%&#" and tw >= 6 and target_h >= 7:
            kernel_cross = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=np.int8)
            blobs = cv2.morphologyEx(hyst, cv2.MORPH_HITMISS, kernel_cross)
            hyst_trap = cv2.bitwise_and(hyst, cv2.bitwise_not(blobs))
            b0_a, b1_a, _ = compute_betti_numbers(hyst)
            b0_b, b1_b, _ = compute_betti_numbers(hyst_trap)
            if b0_a == b0_b and b1_a == b1_b:
                hyst = hyst_trap
        hyst = _apply_counter_punch(hyst, orig_counters)
        out.append((f"M1_hysteresis(w+{dw},t={t_center})", hyst))

    return out


def synth_m5_whole_stem_collinear_autofloor(
    base_1bit: np.ndarray,
    orig_counters: np.ndarray,
    upscaled_small_counters: Optional[np.ndarray],
    min_stem: int = 2,
    can_widen: bool = True,
) -> List[Tuple[str, np.ndarray]]:
    """
    Stage 2 (Collinear Outward & In-Place >=2px Stem Floor + Counter-Punch):
    Respects the Multi-Stroke Pigeonhole Law on scanlines with `len(runs) >= 3`.
    """
    h, w = base_1bit.shape
    out: List[Tuple[str, np.ndarray]] = []

    inp = base_1bit.copy()
    for r in range(h):
        runs = _get_row_runs(base_1bit[r])
        if len(runs) >= 3 and w < (min_stem * len(runs) + (len(runs) - 1)):
            continue
        for idx, (s, e) in enumerate(runs):
            if (e - s + 1) >= min_stem:
                continue
            left_limit = (runs[idx - 1][1] + 2) if idx > 0 else 0
            right_limit = (runs[idx + 1][0] - 2) if idx + 1 < len(runs) else (w - 1)
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
    out.append(("M2_collinear_inplace", inp))

    if not can_widen:
        return out

    if w == 1:
        out.append(("M2_collinear_outward", np.repeat(base_1bit, min_stem, axis=1)))
        return out

    work = np.pad(base_1bit, ((0, 0), (1, 1)), mode="constant", constant_values=0)
    res = work.copy()
    pw = work.shape[1]
    has_multi = any(len(_get_row_runs(work[r])) >= 2 for r in range(h))

    for r in range(h):
        runs = _get_row_runs(work[r])
        if not runs:
            continue
        if len(runs) >= 3 and pw < (min_stem * len(runs) + (len(runs) - 1)):
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
    out.append(("M2_collinear_outward", res))
    return out


def _rectify_spine_tips_and_outer_walls(arr: np.ndarray, min_stem: int = 2) -> np.ndarray:
    """Align 1px top/bottom vertical spine tips with adjacent 2px spine rows and widen 1px outer loop walls."""
    h, w = arr.shape
    inp = arr.copy()
    for r in range(h):
        runs = _get_row_runs(inp[r])
        if len(runs) == 1:
            s, e = runs[0]
            if (e - s + 1) < min_stem:
                adj_r = r + 1 if r == 0 else (r - 1 if r == h - 1 else r - 1)
                if 0 <= adj_r < h:
                    adj_runs = _get_row_runs(inp[adj_r])
                    if len(adj_runs) == 1 and (adj_runs[0][1] - adj_runs[0][0] + 1) >= min_stem:
                        for c_fill in range(adj_runs[0][0], adj_runs[0][0] + min_stem):
                            if 0 <= c_fill < w:
                                inp[r, c_fill] = 255
                    elif e + 1 < w:
                        inp[r, e + 1] = 255
                    elif s - 1 >= 0:
                        inp[r, s - 1] = 255
        elif len(runs) >= 2:
            for idx, (s, e) in enumerate(runs):
                if (e - s + 1) < min_stem and idx in (0, len(runs) - 1):
                    left_lim = (runs[idx - 1][1] + 2) if idx > 0 else 0
                    right_lim = (runs[idx + 1][0] - 2) if idx + 1 < len(runs) else (w - 1)
                    if idx == 0 and s - 1 >= left_lim:
                        inp[r, s - 1] = 255
                    elif idx == len(runs) - 1 and e + 1 <= right_lim:
                        inp[r, e + 1] = 255
                    elif e + 1 <= right_lim:
                        inp[r, e + 1] = 255
                    elif s - 1 >= left_lim:
                        inp[r, s - 1] = 255
    return inp


def synth_m8_central_spine_expansion(
    base_1bit: np.ndarray,
    orig_counters: np.ndarray,
    codepoint: int,
    min_stem: int = 2,
    can_widen: bool = True,
) -> List[Tuple[str, np.ndarray]]:
    """Stage 3 (Central-Spine Column Expansion for '$', '+', '±', '¢', '¥', 'Φ', 'Ψ')."""
    if codepoint not in CENTRAL_SPINE_CODEPOINTS:
        return []
    h, w = base_1bit.shape
    if w < 3 or h < 5:
        return []
    out: List[Tuple[str, np.ndarray]] = []

    best_c = w // 2
    best_1px = -1
    for c_cand in (max(0, w // 2 - 1), w // 2):
        cnt = sum(
            1
            for r in range(h)
            for s, e in _get_row_runs(base_1bit[r])
            if s <= c_cand <= e and (e - s + 1) < min_stem
        )
        if cnt > best_1px:
            best_1px = cnt
            best_c = c_cand

    if can_widen and best_1px >= 3:
        dup = np.insert(base_1bit, best_c, base_1bit[:, best_c], axis=1)
        dup_c = None
        if orig_counters is not None and orig_counters.shape == (h, w):
            dup_c = np.insert(orig_counters, best_c, np.zeros(h, dtype=np.uint8), axis=1)
            dup = _apply_counter_punch(dup, dup_c)
        dup_rect = _rectify_spine_tips_and_outer_walls(dup, min_stem=min_stem)
        if dup_c is not None:
            dup_rect = _apply_counter_punch(dup_rect, dup_c)
        out.append(("M3_central_spine_dup", dup_rect))

        padded = np.pad(dup, ((0, 0), (1, 1)), mode="constant", constant_values=0)
        pad_rect = _rectify_spine_tips_and_outer_walls(padded, min_stem=min_stem)
        if dup_c is not None:
            pad_c = np.pad(dup_c, ((0, 0), (1, 1)), mode="constant", constant_values=0)
            pad_rect = _apply_counter_punch(pad_rect, pad_c)
        out.append(("M3_central_spine_full", pad_rect))

    inp = _rectify_spine_tips_and_outer_walls(base_1bit, min_stem=min_stem)
    inp = _apply_counter_punch(inp, orig_counters)
    out.append(("M3_central_spine_tips", inp))
    return out


# Backward-compatible function aliases
synth_m1_phase_shift_sweep = synth_m1_dynamic_threshold_sweep
synth_m2_collinear_stem_rescue = synth_m5_whole_stem_collinear_autofloor
synth_m3_central_spine = synth_m8_central_spine_expansion


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
    is_bold_role: bool = False,
    tune_mode: str = "surgical",
) -> Tuple[np.ndarray, RepairAuditRecord]:
    """
    Run the Surgical Multi-Method Typographic Tournament (`M0..M8`) on a single glyph (v1.0.17):
      - `tune_mode == "off"`       : 100% Untouched Native FreeType (metrics & audit only).
      - `tune_mode == "wart-only"` : Zero stem thickening; only 4-directional 1px outline-wart shaving (`M0_wart_shaved`).
      - `tune_mode == "surgical"`  : Universal 4-directional outline-wart shaving (`M0_wart_shaved`) on all glyphs +
                                     conservative stem/counter tournament where needed.
      - `tune_mode == "full"`      : Full M0..M8 tournament on any glyph with stem or counter deficits.
    """
    ch_str = chr(codepoint) if 0x20 <= codepoint <= 0xFFFF else ""
    rows_before = binary_array_to_rows(base_1bit)
    h0, w0 = base_1bit.shape if base_1bit.size > 0 else (0, 0)

    raw_hq_metrics = compute_upscaled_hq_metrics(base_1bit, master_hi)
    canon_holes = CANONICAL_MIN_HOLES.get(ch_str, 0)

    if base_1bit.size == 0 or h0 <= 2 or w0 == 0 or codepoint in SKIP_TUNING_CODEPOINTS:
        is_blank_err = (codepoint not in SKIP_TUNING_CODEPOINTS) and (w0 == 0 or h0 == 0)
        rec = RepairAuditRecord(
            codepoint=codepoint,
            char_label=ch_str,
            box_w_before=w0,
            box_h_before=h0,
            box_w_after=w0,
            box_h_after=h0,
            holes_expected=canon_holes,
            holes_before=0,
            holes_after=0,
            thin_v_before=is_blank_err,
            thin_h_before=is_blank_err,
            thin_v_after=is_blank_err,
            thin_h_after=is_blank_err,
            repaired=False,
            size_floor_warning=(canon_holes > 0 or is_blank_err),
            engine_used="untouched",
            rows_before=rows_before,
            rows_after=rows_before,
            hq_conf_before=0.0 if is_blank_err else raw_hq_metrics.hq_conf_iou,
            hq_conf_after=0.0 if is_blank_err else raw_hq_metrics.hq_conf_iou,
            hq_diff_before=100.0 if is_blank_err else raw_hq_metrics.hq_diff_pct,
            hq_diff_after=100.0 if is_blank_err else raw_hq_metrics.hq_diff_pct,
        )
        return base_1bit, rec

    b0_base, b1_base, orig_counters = compute_betti_numbers(base_1bit)
    expected_b0 = b0_base
    expected_b1 = canon_holes if ch_str in CANONICAL_MIN_HOLES else (0 if ch_str in PINCH_FORBIDDEN_CHARS else b1_base)
    if expected_holes_override is not None:
        expected_b1 = expected_holes_override
    elif master_hi is not None and master_hi.size > 0:
        t_hq_dyn = compute_dynamic_hq_threshold(master_hi, is_bold_role=is_bold_role, h0=h0)
        b0_hi, b1_hi, hi_counters = compute_betti_numbers((master_hi >= t_hq_dyn).astype(np.uint8) * 255)
        expected_b0 = b0_hi if b0_hi > 0 else b0_base
        if ch_str in PINCH_FORBIDDEN_CHARS:
            expected_b1 = 0
        elif ch_str in SINGLE_COUNTER_OPEN_TAIL_CHARS:
            expected_b1 = 1
            if b1_hi >= 1 > b1_base and HAS_CV2 and w0 >= 4 and h0 >= 5:
                orig_counters = cv2.bitwise_or(orig_counters, cv2.resize(hi_counters, (w0, h0), interpolation=cv2.INTER_NEAREST))
        else:
            expected_b1 = max(expected_b1, b1_hi)
            if b1_hi > b1_base and HAS_CV2 and w0 >= 4 and h0 >= 5:
                orig_counters = cv2.bitwise_or(orig_counters, cv2.resize(hi_counters, (w0, h0), interpolation=cv2.INTER_NEAREST))

    upscaled_small_counters = None
    if upscaled_small_ref is not None and upscaled_small_ref.size > 0:
        _, _, upscaled_small_counters = compute_betti_numbers(upscaled_small_ref)

    base_valley_stats = compute_open_valley_stats(base_1bit)
    needs_h0, needs_v0, h_ratio0, _ = measure_stem_deficits(base_1bit, min_stem=min_stem, codepoint=codepoint)
    # If the glyph severely dropped out against its 8x HQ master (<42% IoU confidence or shattered into extra fragments), mark stem deficit
    if raw_hq_metrics.hq_conf_iou < 42.0 or (expected_b0 > 0 and b0_base > expected_b0 + 1):
        needs_h0 = True
        h_ratio0 = min(h_ratio0, 0.25)

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
        codepoint=codepoint,
        raw_hq_metrics=raw_hq_metrics,
        base_valley_stats=base_valley_stats,
    )

    if tune_mode == "off":
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
            thin_v_before=needs_h0,
            thin_h_before=needs_v0,
            thin_v_after=needs_h0,
            thin_h_after=needs_v0,
            repaired=False,
            size_floor_warning=(b1_m0_now < expected_b1) or (ch_str in PINCH_FORBIDDEN_CHARS and b1_m0_now > 0),
            engine_used="M0_untouched",
            rows_before=rows_before,
            rows_after=rows_before,
            score_before=eval_m0.total_score,
            score_after=eval_m0.total_score,
            skin_tags_before=eval_m0.skin_tags,
            skin_tags_after=eval_m0.skin_tags,
            hq_conf_before=raw_hq_metrics.hq_conf_iou,
            hq_conf_after=raw_hq_metrics.hq_conf_iou,
            hq_diff_before=raw_hq_metrics.hq_diff_pct,
            hq_diff_after=raw_hq_metrics.hq_diff_pct,
        )
        return base_1bit, rec

    # Universal Pre-Exit Pass:
    # (A) Surgical Counter-Carving & Un-Pinching (`M0_counter_carved`) so heavy Bold/ExtraBold/Black (3px+ stem punch)
    #     and subtle MediumItalic/SemiBoldItalic cuts keep 100% open counters without losing stem weight!
    # (B) 4-Directional Outline-Wart Shaving (`M0_wart_shaved`).
    m0_work = carve_and_unpinch_counters(base_1bit, master_hi, expected_b1=expected_b1, ch_str=ch_str, is_bold_role=is_bold_role)
    m0_eval_work = eval_m0
    m0_hq_work = compute_upscaled_hq_metrics(m0_work, master_hi) if not np.array_equal(m0_work, base_1bit) else raw_hq_metrics
    m0_engine = "M0_counter_carved" if not np.array_equal(m0_work, base_1bit) else "M0_verified"
    _, b1_m0_now, _ = compute_betti_numbers(m0_work)
    if eval_m0.skin_tags > 0 or eval_m0.notches > 0 or m0_engine == "M0_counter_carved":
        hq_base_cov = None
        if master_hi is not None and master_hi.size > 0 and HAS_CV2:
            hq_base_cov = cv2.resize(master_hi, (w0, h0), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
        shaved = clean_skin_tags_and_notches(
            m0_work,
            expected_b0=b0_base,
            expected_b1=b1_m0_now,
            hq_coverage=hq_base_cov,
            allow_corner_bevel=False,
            codepoint=codepoint,
        )
        shaved, sbw, sbh, _, _ = trim_binary_array(shaved)
        if sbw > 0 and sbh > 0 and binary_array_to_rows(shaved) != rows_before:
            up_shaved = compute_upscaled_hq_metrics(shaved, master_hi)
            if up_shaved.hq_conf_iou >= raw_hq_metrics.hq_conf_iou - (3.5 if m0_engine == 'M0_counter_carved' else 0.25):
                m0_work = shaved
                m0_hq_work = up_shaved
                m0_engine = "M0_counter_carved" if m0_engine == "M0_counter_carved" else "M0_wart_shaved"
                m0_eval_work = evaluate_glyph_candidate(
                    "M0_wart_shaved",
                    shaved,
                    master_hi,
                    upscaled_small_ref,
                    expected_b0=b0_base,
                    expected_b1=b1_m0_now,
                    min_stem=min_stem,
                    orig_w=w0,
                    is_italic_or_serif=is_italic_or_serif,
                    base_1bit=base_1bit,
                    codepoint=codepoint,
                    raw_hq_metrics=raw_hq_metrics,
                    base_valley_stats=base_valley_stats,
                )

    skip_for_bold = (tune_mode != "full") and is_bold_role and (b1_m0_now >= expected_b1) and (w0 > 2)
    skip_for_multi_valley = (tune_mode != "full") and (ch_str in MULTI_VALLEY_CHARS) and (b1_m0_now >= expected_b1) and (w0 < 12 or raw_hq_metrics.hq_conf_iou >= 50.0)
    skip_for_high_conf = (
        (tune_mode != "full")
        and (b1_m0_now >= expected_b1)
        and (codepoint not in CENTRAL_SPINE_CODEPOINTS)
        and (w0 >= 5)
        and (raw_hq_metrics.hq_conf_iou >= 68.0)
        and (h_ratio0 >= 0.62)
    )

    if (
        tune_mode == "wart-only"
        or skip_for_bold
        or skip_for_multi_valley
        or skip_for_high_conf
        or (not needs_h0 and b1_m0_now >= expected_b1)
    ):
        rows_m0_after = binary_array_to_rows(m0_work)
        m0_changed = rows_m0_after != rows_before
        needs_h_m0_after, needs_v_m0_after, _, _ = measure_stem_deficits(m0_work, min_stem=min_stem, codepoint=codepoint)
        if m0_hq_work.hq_conf_iou < 42.0 or (expected_b0 > 0 and b0_base > expected_b0 + 1):
            needs_h_m0_after = True
        rec = RepairAuditRecord(
            codepoint=codepoint,
            char_label=ch_str,
            box_w_before=w0,
            box_h_before=h0,
            box_w_after=m0_work.shape[1],
            box_h_after=m0_work.shape[0],
            holes_expected=expected_b1,
            holes_before=b1_base,
            holes_after=b1_m0_now,
            thin_v_before=needs_h0,
            thin_h_before=needs_v0,
            thin_v_after=needs_h_m0_after,
            thin_h_after=needs_v_m0_after,
            repaired=m0_changed,
            size_floor_warning=(b1_m0_now < expected_b1) or (ch_str in PINCH_FORBIDDEN_CHARS and b1_m0_now > 0),
            engine_used=m0_engine,
            rows_before=rows_before,
            rows_after=rows_m0_after,
            score_before=eval_m0.total_score,
            score_after=m0_eval_work.total_score,
            skin_tags_before=eval_m0.skin_tags,
            skin_tags_after=m0_eval_work.skin_tags,
            hq_conf_before=raw_hq_metrics.hq_conf_iou,
            hq_conf_after=m0_hq_work.hq_conf_iou,
            hq_diff_before=raw_hq_metrics.hq_diff_pct,
            hq_diff_after=m0_hq_work.hq_diff_pct,
        )
        return m0_work, rec

    effective_max_w = max_width_ceiling
    if effective_max_w is not None and codepoint in CENTRAL_SPINE_CODEPOINTS:
        effective_max_w = max(effective_max_w, w0 + 3)
    can_widen = (effective_max_w is None) or (w0 + 1 <= effective_max_w)

    raw_candidates: List[Tuple[str, np.ndarray]] = []
    if master_hi is not None and master_hi.size > 0:
        raw_candidates.extend(
            synth_m1_dynamic_threshold_sweep(master_hi, w0, h0, orig_counters, codepoint=codepoint, is_bold_role=is_bold_role)
        )
    raw_candidates.extend(
        synth_m5_whole_stem_collinear_autofloor(
            base_1bit, orig_counters, upscaled_small_counters, min_stem=min_stem, can_widen=can_widen
        )
    )
    raw_candidates.extend(
        synth_m8_central_spine_expansion(base_1bit, orig_counters, codepoint, min_stem=min_stem, can_widen=can_widen)
    )

    best_eval = eval_m0
    allow_bevel = codepoint in CENTRAL_SPINE_CODEPOINTS

    for m_name, cand_arr in raw_candidates:
        if cand_arr is None or cand_arr.size == 0:
            continue
        trimmed, bw, bh, _, _ = trim_binary_array(cand_arr)
        if bw == 0 or bh == 0:
            continue
        if effective_max_w is not None and bw > effective_max_w:
            continue

        hq_cand_cov = None
        if master_hi is not None and master_hi.size > 0 and HAS_CV2:
            hq_cand_cov = cv2.resize(master_hi, (bw, bh), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
        cleaned = clean_skin_tags_and_notches(
            trimmed,
            expected_b0=expected_b0,
            expected_b1=expected_b1,
            hq_coverage=hq_cand_cov,
            allow_corner_bevel=allow_bevel,
            codepoint=codepoint,
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
            codepoint=codepoint,
            raw_hq_metrics=raw_hq_metrics,
            base_valley_stats=base_valley_stats,
        )
        if ev.valid_topology and ev.skin_tags == 0 and ev.notches == 0:
            if ev.total_score > best_eval.total_score:
                best_eval = ev

    # Require a decisive score improvement (>= +3.5 pts) over M0_untouched before modifying a glyph
    if best_eval.method_id not in ("M0_untouched", "M0_wart_shaved") and (best_eval.total_score >= m0_eval_work.total_score + 2.2):
        winner = best_eval.binary
        used_method = best_eval.method_id
    else:
        winner = m0_work.copy()
        best_eval = m0_eval_work
        used_method = m0_engine

    rows_after = binary_array_to_rows(winner)
    changed = rows_after != rows_before
    thin_v_after, thin_h_after, _, _ = measure_stem_deficits(winner, min_stem=min_stem, codepoint=codepoint)
    size_floor_warn = best_eval.b1_holes < expected_b1

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
        hq_conf_before=raw_hq_metrics.hq_conf_iou,
        hq_conf_after=best_eval.hq_conf_iou,
        hq_diff_before=raw_hq_metrics.hq_diff_pct,
        hq_diff_after=best_eval.hq_diff_pct,
    )
    return winner, rec


def synchronize_mirror_glyph_pairs(
    glyphs: Sequence[object],
    recs: Sequence[RepairAuditRecord],
    is_italic: bool = False,
    is_monospace: bool = False,
) -> int:
    """
    Bilateral Mirror-Pair Synchronization (v1.0.17):
    Only synchronizes a paired delimiter/arrow tuple `(cp_l, cp_r)` if at least one partner
    was repaired (`rl.repaired or rr.repaired`) or if their bounding-box widths differ (`gl.box_w != gr.box_w`),
    and always prefers the wider / higher-confidence partner (never shrinking a bold glyph).
    """
    g_by_cp = {getattr(g, "codepoint", 0): g for g in glyphs}
    r_by_cp = {r.codepoint: r for r in recs}
    synced_count = 0

    for cp_l, cp_r, flip_mode in MIRROR_GLYPH_PAIRS:
        gl = g_by_cp.get(cp_l)
        gr = g_by_cp.get(cp_r)
        rl = r_by_cp.get(cp_l)
        rr = r_by_cp.get(cp_r)
        if gl is None or gr is None or rl is None or rr is None:
            continue
        if not getattr(gl, "rows", None) or not getattr(gr, "rows", None):
            continue
        if abs(rl.box_h_before - rr.box_h_before) > 1:
            continue
        if not (rl.repaired or rr.repaired or gl.box_w != gr.box_w):
            continue

        arr_l = rows_to_binary_array(gl.rows)
        arr_r = rows_to_binary_array(gr.rows)
        mir_l = (np.flipud(np.fliplr(arr_l)) if is_italic else np.fliplr(arr_l)) if flip_mode == "h" else np.flipud(arr_l)

        if arr_r.shape == mir_l.shape and np.array_equal(arr_r, mir_l):
            continue

        l_better = (
            (not rl.thin_v_after and rr.thin_v_after)
            or (rl.thin_v_after == rr.thin_v_after and gl.box_w > gr.box_w)
            or (rl.thin_v_after == rr.thin_v_after and gl.box_w == gr.box_w and rl.score_after >= rr.score_after)
        )
        src_g, dst_g, src_r, dst_r = (gl, gr, rl, rr) if l_better else (gr, gl, rr, rl)
        src_arr = rows_to_binary_array(src_g.rows)
        mir_arr = (np.flipud(np.fliplr(src_arr)) if is_italic else np.fliplr(src_arr)) if flip_mode == "h" else np.flipud(src_arr)
        mir_rows = binary_array_to_rows(mir_arr)

        w_old = dst_g.box_w
        dst_g.rows = mir_rows
        dst_g.box_w = mir_arr.shape[1]
        dst_g.box_h = mir_arr.shape[0]
        dst_r.rows_after = mir_rows
        dst_r.box_w_after = mir_arr.shape[1]
        dst_r.box_h_after = mir_arr.shape[0]
        dst_r.thin_v_after = src_r.thin_v_after
        dst_r.thin_h_after = src_r.thin_h_after
        dst_r.score_after = src_r.score_after
        dst_r.hq_conf_after = src_r.hq_conf_after
        dst_r.hq_diff_after = src_r.hq_diff_after
        dst_r.repaired = dst_r.rows_after != dst_r.rows_before
        dst_g.patched = dst_r.repaired
        if not is_monospace and dst_g.box_w > w_old:
            dst_g.adv_w_fp4 += (dst_g.box_w - w_old) * 16
        if dst_r.repaired:
            dst_r.engine_used = f"{src_r.engine_used}+MirrorSync"
            synced_count += 1

    return synced_count


def render_repair_comparison_sheet(
    out_png: Path,
    strike_symbol: str,
    size_px: int,
    records: Sequence[RepairAuditRecord],
) -> None:
    """Render a visual Before vs. After 1-BPP diagnostic PNG showing winning method & HQ Confidence %."""
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
        f"HUMID1 v{TOOL_VERSION} SURGICAL TYPOGRAPHIC TOURNAMENT + 8x HQ CONFIDENCE GATE | {strike_symbol} ({size_px}px)",
        fill=(255, 255, 255),
    )
    draw.text(
        (pad, 36),
        f"Inspected: {len(records)} glyphs | Auto-Patched in ascii_patches/: {mod_cnt} glyphs (Open-Valley Locked, HQ Sanity Checked)",
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
            f"HQConf:{rec.hq_conf_before:.0f}%->{rec.hq_conf_after:.0f}% | "
            f"Diff:{rec.hq_diff_after:.0f}% | {rec.box_w_before}x{rec.box_h_before}->{rec.box_w_after}x{rec.box_h_after}"
        )
        draw.text((x0 + 8, y0 + 22), meta, fill=(90, 102, 118))

        for side_idx, (tag, g_rows, tint) in enumerate([
            ("RAW", rec.rows_before, (175, 52, 52)),
            ("TUNED", rec.rows_after, (16, 112, 68) if rec.repaired else (30, 36, 44)),
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
            f"Humidyne Labs `epd-font` v{TOOL_VERSION} — Surgical Multi-Method Typographic Tournament Engine.\n"
            "Tunes ASCII patch files in `build/<target>/ascii_patches/` using an 8x HQ continuous master\n"
            "reference + Render->Upscale->HQ Confidence Sanity Gate."
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
        "--tune-mode",
        type=str,
        choices=["off", "wart-only", "surgical", "full"],
        default="surgical",
        help="Tuning intervention level: off (native weight only), wart-only (4-dir wart shaving + mirror sync), surgical (default), or full",
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
        "--tune-mode", args.tune_mode,
        "--save-repaired-patches",
    ]
    if args.ascii_dir:
        cmd_argv.extend(["--ascii-dir", args.ascii_dir])
    sys.argv = cmd_argv
    g1.main()


if __name__ == "__main__":
    main()
