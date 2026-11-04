#!/usr/bin/env python3
"""
humid1_bilevel_tuner.py (v1.0.10)
=================================
Humidyne Labs / Humiditron `epd-font` Closed-Loop Iterative Bi-Level Font & Icon
Auto-Floor, Sub-Pixel Downscale & Morphological Topology Repair Engine.

Repository : https://github.com/Humidyne-Labs/epd-font
Target OS  : https://github.com/Humidyne-Labs/H1OS
License    : MIT License

Overview:
---------
Solves the 1-BPP electrophoretic display (EPD) hairline stem problem (where strokes <= 1px
wide wash out under ambient reflection at 188.3 DPI) without clogging internal counters/holes
('a', 'b', 'd', 'e', 'g', 'o', 'p', 'q', '0', '4', '6', '8', '9', '@', '%', '&', '#').

Implements three deterministic, closed-loop repair engines (selectable via `--engine`):
  1. `autofloor` : Progressive Bi-Level Morphological Stem-Floor (`min_stem >= 2px`) with
                   Exterior Flood-Fill Counter Discovery, Protected Cavity Re-Punching,
                   Centroid Carve Fallback, and Hit-or-Miss Acute Junction Pruning.
  2. `downscale` : High-Resolution Master (`256x256` / `1024x1024`) Continuous Area Sampler
                   that sweeps a 4x4 sub-pixel spatial phase grid (dx, dy in [0.0, 0.25, 0.5, 0.75])
                   and binarization thresholds (T in [80..180]), scored by a deterministic fitness
                   function enforcing Euler genus (hole count) invariance + >=2px stem preservation
                   + structural IOU fidelity.
  3. `contour`   : OpenCV Vector Contour / Polygon Re-Tracing (`cv2.findContours` with `RETR_CCOMP`
                   two-level hierarchy + `approxPolyDP` staircase smoothing + stroke floor enforcement).
  4. `hybrid`    : (DEFAULT) Combines `downscale` sub-pixel phase alignment with `autofloor`
                   directional stem dilation, cavity protection, and junction pruning.

Can be invoked standalone via CLI or imported directly by `humid1_generate_1bpp.py`.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import os
import sys
from dataclasses import dataclass
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

TOOL_VERSION = "1.0.10"

# Characters whose horizontal crossbars or arms are critical for recognition and often drop at <=16px
HORIZONTAL_BAR_CHARS = set("eftEFHTzZ=-+~÷±≤≥≠≈#[")
# Characters that naturally consist of a single thin punctuation dot/tick or diagonal where 2px horizontal dilation is unwanted
SKIP_HORIZONTAL_DILATION_CODEPOINTS = {
    0x0020,  # space
    0x002C,  # comma ','
    0x002E,  # period '.'
    0x003A,  # colon ':'
    0x003B,  # semicolon ';'
}


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
    # ofs_y is bottom-referenced in LVGL/BDF: trimming bottom rows (h_orig - 1 - r1) raises ofs_y
    new_ofs_y = ofs_y + (h_orig - 1 - r1)
    return trimmed, int(box_w), int(box_h), int(new_ofs_x), int(new_ofs_y)


def find_internal_counters(binary_img: np.ndarray) -> Tuple[np.ndarray, int, Optional[np.ndarray], Optional[np.ndarray]]:
    """
    Isolate internal closed loops (counters/holes) via exterior flood-fill from (0, 0).
    Returns (counters_mask_255, num_holes, labels, stats).
    """
    if binary_img.size == 0 or binary_img.shape[0] < 3 or binary_img.shape[1] < 3:
        z = np.zeros_like(binary_img)
        return z, 0, None, None

    if HAS_CV2:
        h, w = binary_img.shape
        padded = cv2.copyMakeBorder(binary_img, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
        inv = cv2.bitwise_not(padded)
        ff_mask = np.zeros((h + 4, w + 4), np.uint8)
        cv2.floodFill(inv, ff_mask, (0, 0), 0)
        counters = inv[1:-1, 1:-1]
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(counters, connectivity=4)
        return counters, max(0, int(num_labels - 1)), labels, stats
    else:
        # Pure-NumPy BFS fallback if OpenCV is unavailable
        h, w = binary_img.shape
        padded = np.pad(binary_img > 0, 1, mode="constant", constant_values=False)
        visited = np.zeros_like(padded, dtype=bool)
        queue = [(0, 0)]
        visited[0, 0] = True
        while queue:
            cy, cx = queue.pop()
            for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                if 0 <= ny < h + 2 and 0 <= nx < w + 2 and not visited[ny, nx] and not padded[ny, nx]:
                    visited[ny, nx] = True
                    queue.append((ny, nx))
        holes = (~padded & ~visited)[1:-1, 1:-1]
        counters = (holes.astype(np.uint8)) * 255
        return counters, (1 if np.any(counters > 0) else 0), None, None


def _erode_zero_border(binary_img: np.ndarray, kh: int, kw: int) -> np.ndarray:
    """Erode binary_img with a (kh, kw) ones kernel using strict 0-valued exterior border."""
    if binary_img.size == 0:
        return binary_img
    if HAS_CV2:
        return cv2.erode(
            binary_img,
            np.ones((kh, kw), np.uint8),
            iterations=1,
            borderType=cv2.BORDER_CONSTANT,
            borderValue=0,
        )
    padded = np.pad(binary_img > 0, ((0, kh - 1), (0, kw - 1)), mode="constant", constant_values=False)
    out = np.ones(binary_img.shape, dtype=bool)
    for dy in range(kh):
        for dx in range(kw):
            out &= padded[dy : dy + binary_img.shape[0], dx : dx + binary_img.shape[1]]
    return (out.astype(np.uint8)) * 255



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


def dilate_horizontal_preserving_gaps(
    binary_img: np.ndarray,
    min_stem: int = 2,
    can_widen: bool = True,
) -> np.ndarray:
    """
    Consistently thicken 1px vertical/diagonal stems to `min_stem` (2px) by expanding
    OUTWARD (leftmost stem expands left, rightmost stem expands right) so interior
    counters ('0','6','8','9','O','d','p','q','e','a') and arches ('Ω','u','n','h','m')
    are NEVER narrowed or pinched, and vertical stems remain 100% collinear across rows.
    """
    h, w = binary_img.shape
    if not can_widen:
        # In-place gap-safe horizontal dilation when width ceiling is reached
        out = binary_img.copy()
        for r in range(h):
            runs = _get_row_runs(binary_img[r])
            for idx, (s, e) in enumerate(runs):
                if (e - s + 1) >= min_stem:
                    continue
                left_limit = (runs[idx - 1][1] + 2) if idx > 0 else 0
                right_limit = (runs[idx + 1][0] - 2) if idx + 1 < len(runs) else (w - 1)
                if e + 1 <= right_limit:
                    out[r, e + 1] = 255
                elif s - 1 >= left_limit:
                    out[r, s - 1] = 255
        return out

    work = np.pad(binary_img, ((0, 0), (1, 1)), mode="constant", constant_values=0)
    out = work.copy()
    pw = work.shape[1]
    has_multi_runs = any(len(_get_row_runs(work[r])) >= 2 for r in range(h))

    for r in range(h):
        runs = _get_row_runs(work[r])
        if not runs:
            continue
        for idx, (s, e) in enumerate(runs):
            rlen = e - s + 1
            if rlen >= min_stem:
                continue
            left_limit = (runs[idx - 1][1] + 2) if idx > 0 else 0
            right_limit = (runs[idx + 1][0] - 2) if idx + 1 < len(runs) else (pw - 1)
            can_left = (s - 1 >= left_limit)
            can_right = (e + 1 <= right_limit)

            if len(runs) == 1:
                if has_multi_runs and s <= 2 and w >= 4:
                    if can_left:
                        out[r, s - 1] = 255
                    elif can_right:
                        out[r, e + 1] = 255
                else:
                    if can_right:
                        out[r, e + 1] = 255
                    elif can_left:
                        out[r, s - 1] = 255
            elif idx == 0:
                if can_left:
                    out[r, s - 1] = 255
                elif can_right:
                    out[r, e + 1] = 255
            elif idx == len(runs) - 1:
                if can_right:
                    out[r, e + 1] = 255
                elif can_left:
                    out[r, s - 1] = 255
            else:
                if can_right:
                    out[r, e + 1] = 255
                elif can_left:
                    out[r, s - 1] = 255

    # Vertical stem collinearity snap: if a crossbar row had s==1 while both neighbor rows expanded to col 0, snap col 0
    for r in range(h):
        if work[r, 1] > 0 and out[r, 0] == 0:
            if (r > 0 and out[r - 1, 0] > 0 and work[r - 1, 1] > 0) or (r + 1 < h and out[r + 1, 0] > 0 and work[r + 1, 1] > 0):
                out[r, 0] = 255
        if work[r, pw - 2] > 0 and out[r, pw - 1] == 0:
            if (r > 0 and out[r - 1, pw - 1] > 0 and work[r - 1, pw - 2] > 0) or (r + 1 < h and out[r + 1, pw - 1] > 0 and work[r + 1, pw - 2] > 0):
                out[r, pw - 1] = 255

    ys, xs = np.nonzero(out > 0)
    if len(xs) == 0:
        return binary_img
    return out[:, int(xs.min()) : int(xs.max()) + 1]


def measure_stem_deficits(binary_img: np.ndarray, min_stem: int = 2) -> Tuple[bool, bool, float, float]:
    """
    Inspect whether dominant vertical stems (horizontal thickness) or horizontal bars
    (vertical thickness) fall below `min_stem` pixels.
    Returns (needs_horizontal_floor, needs_vertical_floor, h_survival_ratio, v_survival_ratio).
    """
    nz = int(np.count_nonzero(binary_img))
    if nz == 0:
        return False, False, 1.0, 1.0
    h, w = binary_img.shape
    if w < min_stem:
        return True, False, 0.0, 1.0

    h_erode = _erode_zero_border(binary_img, 1, min_stem)
    v_erode = _erode_zero_border(binary_img, min_stem, 1)

    h_ratio = float(np.count_nonzero(h_erode)) / float(nz)
    v_ratio = float(np.count_nonzero(v_erode)) / float(nz)

    # Also check row-by-row run lengths on rows that have vertical stems (1 or 2 runs)
    one_px_runs = 0
    total_stem_runs = 0
    for r in range(h):
        row = binary_img[r]
        in_run = False
        run_len = 0
        runs = []
        for c in range(w):
            if row[c] > 0:
                run_len += 1
                in_run = True
            elif in_run:
                runs.append(run_len)
                run_len = 0
                in_run = False
        if in_run:
            runs.append(run_len)
        # Rows with 1, 2, or 3 distinct stroke crossings represent vertical/diagonal stems
        if 1 <= len(runs) <= 3 and max(runs) <= 3:
            for rl in runs:
                total_stem_runs += 1
                if rl < min_stem:
                    one_px_runs += 1

    run_deficit = (total_stem_runs >= 3) and (one_px_runs / float(max(1, total_stem_runs)) >= 0.45)
    needs_h = (h_ratio < 0.25) or run_deficit
    needs_v = (v_ratio < 0.18)
    return needs_h, needs_v, h_ratio, v_ratio


def score_candidate(
    candidate_1bit: np.ndarray,
    master_reference: np.ndarray,
    expected_holes: int,
    min_stem: int = 2,
) -> float:
    """
    Deterministic fitness function from `downscale.docx`:
      1. Hard topological constraint: Euler hole count must match `expected_holes` (-1e9 if violated).
      2. Minimum stem floor preservation (`>= min_stem` px).
      3. Structural IOU against area-downscaled master reference.
    """
    if candidate_1bit.size == 0:
        return -1e9
    h, w = candidate_1bit.shape
    _, actual_holes, _, _ = find_internal_counters(candidate_1bit)
    if actual_holes != expected_holes:
        return -1e9

    total_on = int(np.count_nonzero(candidate_1bit))
    if total_on == 0:
        return -1e9

    h_eroded = _erode_zero_border(candidate_1bit, 1, min_stem)
    v_eroded = _erode_zero_border(candidate_1bit, min_stem, 1)
    stem_preservation = (np.count_nonzero(h_eroded) + np.count_nonzero(v_eroded)) / (2.0 * total_on)

    if HAS_CV2 and master_reference.size > 0:
        ref_downscaled = cv2.resize(master_reference, (w, h), interpolation=cv2.INTER_AREA)
        ref_binary = (ref_downscaled > 120).astype(np.uint8) * 255
        inter = np.count_nonzero(cv2.bitwise_and(candidate_1bit, ref_binary))
        union = np.count_nonzero(cv2.bitwise_or(candidate_1bit, ref_binary))
        iou = float(inter) / float(max(1, union))
    else:
        iou = 0.5

    return (stem_preservation * 100.0) + (iou * 50.0)


def render_optimal_bilevel_from_master(
    master_hi: np.ndarray,
    target_w: int,
    target_h: int,
    expected_holes: int,
    min_stem: int = 2,
) -> Optional[np.ndarray]:
    """
    Sweep sub-pixel spatial phase offsets (4x4 grid) and binarization cutoffs
    on a high-resolution master glyph raster to find the highest-scoring 1-bit matrix.
    """
    if not HAS_CV2 or master_hi.size == 0 or target_w <= 1 or target_h <= 1:
        return None

    mh, mw = master_hi.shape
    best_score = -1e9
    best_bitmap: Optional[np.ndarray] = None

    shifts = [0.0, 0.25, 0.5, 0.75]
    thresholds = [85, 105, 125, 145, 165]

    for dx in shifts:
        for dy in shifts:
            shift_x_master = dx * (float(mw) / float(target_w))
            shift_y_master = dy * (float(mh) / float(target_h))
            mat = np.float32([[1, 0, shift_x_master], [0, 1, shift_y_master]])
            shifted = cv2.warpAffine(
                master_hi,
                mat,
                (mw, mh),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=0,
            )
            downscaled = cv2.resize(shifted, (target_w, target_h), interpolation=cv2.INTER_AREA)
            for t in thresholds:
                cand = (downscaled > t).astype(np.uint8) * 255
                sc = score_candidate(cand, master_hi, expected_holes, min_stem)
                if sc > best_score:
                    best_score = sc
                    best_bitmap = cand

    return best_bitmap


def repair_via_contour_retrace(
    base_1bit: np.ndarray,
    expected_holes: int,
    min_stem: int = 2,
) -> np.ndarray:
    """
    OpenCV Vector Contour / Polygon Re-Tracing (`RETR_CCOMP` two-level hole hierarchy):
    Extracts outer and inner hole polygons, renders outer contour with stroke thickness
    `min_stem`, and re-carves inner hole contours.
    """
    if not HAS_CV2 or base_1bit.size == 0:
        return base_1bit
    h, w = base_1bit.shape
    scale = 4
    up = cv2.resize(base_1bit, (w * scale, h * scale), interpolation=cv2.INTER_NEAREST)
    contours, hierarchy = cv2.findContours(up, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None or len(contours) == 0:
        return base_1bit

    canvas = np.zeros_like(up)
    hier = hierarchy[0]
    # Draw outer contours (parent < 0) filled + thickened
    for idx, cnt in enumerate(contours):
        if hier[idx][3] < 0:
            eps = 0.35 * scale
            poly = cv2.approxPolyDP(cnt, eps, True)
            cv2.drawContours(canvas, [poly], -1, 255, thickness=cv2.FILLED)
            cv2.drawContours(canvas, [poly], -1, 255, thickness=max(1, (min_stem - 1) * scale))
    # Carve inner hole contours (parent >= 0)
    for idx, cnt in enumerate(contours):
        if hier[idx][3] >= 0:
            cv2.drawContours(canvas, [cnt], -1, 0, thickness=cv2.FILLED)

    down = cv2.resize(canvas, (w, h), interpolation=cv2.INTER_AREA)
    res = (down > 115).astype(np.uint8) * 255
    return res


def inspect_and_repair_glyph_bitmap(
    base_1bit: np.ndarray,
    codepoint: int,
    min_stem: int = 2,
    gray_img: Optional[np.ndarray] = None,
    master_hi: Optional[np.ndarray] = None,
    expected_holes_override: Optional[int] = None,
    max_width_ceiling: Optional[int] = None,
    engine: str = "hybrid",
) -> Tuple[np.ndarray, RepairAuditRecord]:
    """
    Inspect a 1-bit glyph matrix and deterministically enforce `min_stem` (default 2px)
    while preserving internal counters/holes and preventing acute corner bloat.
    """
    ch_str = chr(codepoint) if 0x20 <= codepoint <= 0xFFFF else ""
    rows_before = binary_array_to_rows(base_1bit)
    h0, w0 = base_1bit.shape if base_1bit.size > 0 else (0, 0)

    if base_1bit.size == 0 or h0 == 0 or w0 == 0 or codepoint in SKIP_HORIZONTAL_DILATION_CODEPOINTS:
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
            engine_used="none",
            rows_before=rows_before,
            rows_after=rows_before,
        )
        return base_1bit, rec

    orig_counters, holes_before, orig_labels, orig_stats = find_internal_counters(base_1bit)
    if expected_holes_override is not None:
        expected_holes = max(holes_before, expected_holes_override)
    elif master_hi is not None and master_hi.size > 0:
        _, master_holes, _, _ = find_internal_counters((master_hi > 127).astype(np.uint8) * 255)
        expected_holes = max(holes_before, master_holes)
    else:
        expected_holes = holes_before

    needs_h, needs_v, _, _ = measure_stem_deficits(base_1bit, min_stem=min_stem)
    bar_char = ch_str in HORIZONTAL_BAR_CHARS

    # If the glyph already satisfies the stem floor and hole count, emit untouched
    if not needs_h and not (needs_v and bar_char) and holes_before >= expected_holes:
        rec = RepairAuditRecord(
            codepoint=codepoint,
            char_label=ch_str,
            box_w_before=w0,
            box_h_before=h0,
            box_w_after=w0,
            box_h_after=h0,
            holes_expected=expected_holes,
            holes_before=holes_before,
            holes_after=holes_before,
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

    repaired = base_1bit.copy()
    used_engine = engine

    # Stage A: Try sub-pixel phase-shift downscale from hi-res master if requested
    if engine in ("downscale", "hybrid") and master_hi is not None and master_hi.size > 0:
        cand_ds = render_optimal_bilevel_from_master(master_hi, w0, h0, expected_holes, min_stem=min_stem)
        if cand_ds is not None:
            ds_needs_h, ds_needs_v, _, _ = measure_stem_deficits(cand_ds, min_stem=min_stem)
            if not ds_needs_h and not (ds_needs_v and bar_char):
                repaired = cand_ds
                used_engine = "downscale"

    # Stage B: If contour re-tracing was specifically requested
    if engine == "contour":
        repaired = repair_via_contour_retrace(repaired, expected_holes, min_stem=min_stem)
        used_engine = "contour"

    # Stage C: Morphological Stem-Floor Dilation + Cavity Re-Punching + Hit-or-Miss Thinning
    cur_needs_h, cur_needs_v, _, _ = measure_stem_deficits(repaired, min_stem=min_stem)
    if cur_needs_h or (cur_needs_v and bar_char) or engine == "autofloor":
        used_engine = "autofloor" if engine == "autofloor" else f"{used_engine}+autofloor"
        work = repaired.copy()

        # Use scanline-run-invariant horizontal stem dilation so 1px channels never merge
        can_widen = (max_width_ceiling is None) or (work.shape[1] + 1 <= max_width_ceiling)
        if cur_needs_h:
            work = dilate_horizontal_preserving_gaps(work, min_stem=min_stem, can_widen=can_widen)
            if orig_counters.shape != work.shape:
                dw = work.shape[1] - orig_counters.shape[1]
                if dw > 0:
                    orig_counters = np.pad(orig_counters, ((0, 0), (0, dw)), mode="constant", constant_values=0)

        if cur_needs_v and bar_char and work.shape[0] >= 4:
            if HAS_CV2:
                kernel_v = np.ones((min_stem, 1), np.uint8)
                work = cv2.dilate(work, kernel_v, iterations=1)

        # Step 5: Hole / Counter Protection — re-punch original counters
        if np.any(orig_counters > 0):
            if HAS_CV2:
                work = cv2.bitwise_and(work, cv2.bitwise_not(orig_counters))
                num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(orig_counters, connectivity=4)
                for i in range(1, num_labels):
                    hole_comp = (labels == i).astype(np.uint8) * 255
                    open_px = np.count_nonzero(cv2.bitwise_and(cv2.bitwise_not(work), hole_comp))
                    if open_px == 0:
                        cy = int(stats[i, cv2.CC_STAT_TOP] + stats[i, cv2.CC_STAT_HEIGHT] // 2)
                        cx = int(stats[i, cv2.CC_STAT_LEFT] + stats[i, cv2.CC_STAT_WIDTH] // 2)
                        if 0 <= cy < work.shape[0] and 0 <= cx < work.shape[1]:
                            work[cy, cx] = 0
            else:
                work[orig_counters > 0] = 0

        # Also if master had a hole that base_1bit lost (e.g., 'e' or 'a' or '8' pinched at 12px),
        # check grayscale local minima inside the bounding box
        _, work_holes, _, _ = find_internal_counters(work)
        if work_holes < expected_holes and gray_img is not None and gray_img.shape == work.shape:
            # Find interior pixel with lowest grayscale intensity not on the outer border
            if work.shape[0] >= 5 and work.shape[1] >= 4:
                interior = gray_img[1:-1, 1:-1]
                min_idx = np.unravel_index(int(np.argmin(interior)), interior.shape)
                cy, cx = int(min_idx[0] + 1), int(min_idx[1] + 1)
                if gray_img[cy, cx] < 180:
                    work[cy, cx] = 0

        # Step 6: Diagonal / Acute Junction Pruning via Hit-or-Miss
        if HAS_CV2 and work.shape[0] >= 5 and work.shape[1] >= 5 and ch_str in "vwVWMyY%&#4":
            corner_kernel = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=np.int8)
            inner_dots = cv2.morphologyEx(work, cv2.MORPH_HITMISS, corner_kernel)
            # Only prune if it doesn't break connectivity or open an unintended hole
            cand_prune = cv2.bitwise_and(work, cv2.bitwise_not(inner_dots))
            _, prune_holes, _, _ = find_internal_counters(cand_prune)
            if prune_holes == expected_holes:
                work = cand_prune

        repaired = work

    _, holes_after, _, _ = find_internal_counters(repaired)
    if holes_after < holes_before:
        repaired = base_1bit.copy()
        holes_after = holes_before
    thin_v_after, thin_h_after, _, _ = measure_stem_deficits(repaired, min_stem=min_stem)
    size_floor_warn = (holes_after < expected_holes) or (thin_v_after and w0 < 2 * min_stem + 1)
    rows_after = binary_array_to_rows(repaired)
    changed = rows_after != rows_before

    rec = RepairAuditRecord(
        codepoint=codepoint,
        char_label=ch_str,
        box_w_before=w0,
        box_h_before=h0,
        box_w_after=repaired.shape[1],
        box_h_after=repaired.shape[0],
        holes_expected=expected_holes,
        holes_before=holes_before,
        holes_after=holes_after,
        thin_v_before=needs_h,
        thin_h_before=needs_v,
        thin_v_after=thin_v_after,
        thin_h_after=thin_h_after,
        repaired=changed,
        size_floor_warning=size_floor_warn,
        engine_used=used_engine if changed else "verified",
        rows_before=rows_before,
        rows_after=rows_after,
    )
    return repaired, rec


def render_repair_comparison_sheet(
    out_png: Path,
    strike_symbol: str,
    size_px: int,
    records: Sequence[RepairAuditRecord],
) -> None:
    """Render a visual Before vs. After 1-BPP diagnostic PNG for all repaired glyphs in a strike."""
    repaired_recs = [r for r in records if r.repaired]
    if not repaired_recs:
        repaired_recs = list(records[:24])
    if not repaired_recs:
        return

    cols = 4
    rows_cnt = int(math.ceil(len(repaired_recs) / float(cols)))
    cell_w = 270
    cell_h = 128
    pad = 16
    hdr_h = 64

    img_w = pad * 2 + cols * cell_w
    img_h = hdr_h + pad * 2 + rows_cnt * cell_h
    img = Image.new("RGB", (img_w, img_h), (246, 247, 249))
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, img_w, hdr_h], fill=(18, 23, 31))
    mod_cnt = sum(1 for r in records if r.repaired)
    draw.text(
        (pad, 12),
        f"HUMID1 CLOSED-LOOP 1-BPP AUTO-FLOOR & TOPOLOGY REPAIR | {strike_symbol} ({size_px}px)",
        fill=(255, 255, 255),
    )
    draw.text(
        (pad, 34),
        f"Total Inspected: {len(records)} glyphs | Auto-Repaired (min_stem >= 2px + Counter Guard): {mod_cnt} glyphs",
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
        meta = f"Holes:{rec.holes_before}->{rec.holes_after} | {rec.box_w_before}x{rec.box_h_before}->{rec.box_w_after}x{rec.box_h_after}"
        draw.text((x0 + 8, y0 + 22), meta, fill=(90, 102, 118))

        # Draw BEFORE grid on left, AFTER grid on right
        for side_idx, (tag, g_rows, tint) in enumerate([
            ("BEFORE", rec.rows_before, (175, 52, 52)),
            ("AFTER", rec.rows_after, (16, 112, 68) if rec.repaired else (30, 36, 44)),
        ]):
            gx0 = x0 + 12 + side_idx * 124
            gy0 = y0 + 40
            draw.text((gx0, gy0 - 2), tag, fill=tint)
            gy_grid = gy0 + 12
            for ry, r_str in enumerate(g_rows):
                for cx, ch in enumerate(r_str):
                    px0 = gx0 + cx * zoom
                    py0 = gy_grid + ry * zoom
                    if py0 + zoom > y0 + cell_h - 12 or px0 + zoom > gx0 + 116:
                        continue
                    fill_c = tint if ch == "#" else (234, 237, 242)
                    draw.rectangle([px0, py0, px0 + zoom - 1, py0 + zoom - 1], fill=fill_c)

    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png, optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="humid1_bilevel_tuner.py",
        description=(
            f"Humidyne Labs `epd-font` v{TOOL_VERSION} — Closed-Loop Bi-Level Font Auto-Floor & Repair CLI.\n"
            "Enforces >=2px minimum stem width while preserving internal counters/holes using OpenCV."
        ),
    )
    parser.add_argument("--scheme", type=str, default="scripts/h1os-build-distro/h1os_full.scheme.json", help="Scheme JSON path")
    parser.add_argument("--src-dir", type=str, default="build/static_ttfs", help="Static TTF directory")
    parser.add_argument("--out-dir", type=str, default="build/h1os", help="Build output directory")
    parser.add_argument("--patches", type=str, default="font_icon_epd_patches.json", help="Root JSON patches file")
    parser.add_argument("--min-stem", type=int, default=2, help="Minimum stem thickness in pixels (default: 2)")
    parser.add_argument(
        "--engine",
        type=str,
        choices=["hybrid", "autofloor", "downscale", "contour"],
        default="hybrid",
        help="Closed-loop repair engine (default: hybrid)",
    )
    parser.add_argument("--save-patches", action="store_true", help="Persist repaired glyphs into --patches JSON")
    args = parser.parse_args()

    # Delegate full scheme sweep to humid1_generate_1bpp.py --workflow repair
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
    ]
    if args.save_patches:
        cmd_argv.append("--save-repaired-patches")
    sys.argv = cmd_argv
    g1.main()


if __name__ == "__main__":
    main()
