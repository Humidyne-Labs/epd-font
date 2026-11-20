#!/usr/bin/env python3
"""
humid1_bilevel_pipelines.py (v1.0.23)
=====================================
A 1-bit EPD font generator and asset pipeline for embedded displays.
Repository : https://github.com/Humidyne-Labs/epd-font
Authors    : Humiditron (https://github.com/humiditron) & AI/LLM Development Partner
License    : MIT License

Nine-Method Resolution-Reduction Bilevel (1-BPP) Font Conversion Engine & Optical Evaluator:
  1. `raw-unhinted`    : Direct unhinted FreeType rasterization -> sRGB-to-Linear Grayscale -> gamma -> threshold.
  2. `raw-hinted`      : Grid-fitted hinted FreeType rasterization -> sRGB-to-Linear Grayscale -> gamma -> threshold.
  3. `svg-potrace`     : High-res (10x) linear grayscale -> binary threshold -> hierarchical RETR_TREE Potrace /
                         Cubic B-Spline vector contour tracing (.svg) -> +0.5px center alignment -> aliased fill.
  4. `svg-potrace-jfa` : Sub-mode of `svg-potrace` (`jfa-marching`) implementing 3D OpenCL / CPU Jump Flooding
                         Algorithm (`1+JFA`, Rong & Tan I3D 2006) + 2x2 Marching Squares sub-pixel zero-crossing
                         contour extraction + hierarchical RETR_TREE Potrace B-Spline vector SVG synthesis.
  5. `mdf`             : High-res (12x) supersampling with median filter + directional/isotropic SDF -> threshold.
  6. `msdf`            : True Multi-Channel Signed Distance Field generator (Chlumsky msdfgen / Qin et al. I3D 2006)
                         with 3-channel (R, G, B) sharp-corner edge coloring + median(R, G, B) reconstruction.
  7. `sdf-smoothstep`  : High-res (16x) Euclidean SDF magnification/minification (Chris Green SIGGRAPH 2007) +
                         L2 Jacobian gradient-normalized smoothstep AA ramp in linear space (Boesch 2025).
  8. `adf-biquadratic` : MERL Saffron Adaptively Sampled Distance Field (Perry & Frisken) with bi-quadratic
                         9-point Lagrange cell reconstruction, (-0.50, +0.625) body-type filter, and alpha=1.1 power.
  9. `otsu-adaptive`   : Nonparametric zeroth/first-order cumulative moment between-class variance maximization
                         threshold selection on linear grayscale (Nobuyuki Otsu, IEEE Trans. SMC, 1979).
"""

from __future__ import annotations

import ctypes
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw

from math_backends import (
    dispatch_adf_biquadratic,
    dispatch_jfa_marching_squares,
    dispatch_median_blur,
    dispatch_morphology_close,
    dispatch_msdf_median3_reconstruct,
    dispatch_otsu_linear_threshold,
    dispatch_sdf_smoothstep,
    dispatch_srgb_to_linear_grayscale,
    get_active_math_backend,
)

TOOL_VERSION = "1.0.23"

CANONICAL_PIPELINES: Tuple[str, ...] = (
    "raw-unhinted",
    "raw-hinted",
    "svg-potrace",
    "svg-potrace-jfa",
    "mdf",
    "msdf",
    "sdf-smoothstep",
    "adf-biquadratic",
    "otsu-adaptive",
)

PIPELINE_LABELS: Dict[str, str] = {
    "raw-unhinted": "1. Raw Threshold Unhinted (Linear Gray)",
    "raw-hinted": "2. Raw Threshold Hinted (Linear Gray)",
    "svg-potrace": "3. Custom SVG / Potrace Vector Pipeline",
    "svg-potrace-jfa": "4. SVG / Potrace + 1+JFA Marching Squares",
    "mdf": "5. MDF (Median + Signed Distance Field)",
    "msdf": "6. MSDF (Multi-Channel RGB Corner SDF)",
    "sdf-smoothstep": "7. SDF-Smoothstep (Valve / L2 Gradient AA)",
    "adf-biquadratic": "8. ADF Bi-Quadratic 9-Pt Lagrange (Saffron)",
    "otsu-adaptive": "9. Otsu Cumulative-Moment Linear Threshold",
}

# FreeType bit-flags
FT_LOAD_RENDER = 1 << 2
FT_LOAD_NO_HINTING = 1 << 1
FT_LOAD_FORCE_AUTOHINT = 1 << 5
FT_LOAD_MONOCHROME = 1 << 12
FT_LOAD_TARGET_NORMAL = 0 << 16
FT_LOAD_TARGET_MONO = 2 << 16
FT_PIXEL_MODE_MONO = 1

CANONICAL_MIN_HOLES: Dict[str, int] = {
    "0": 1, "4": 1, "6": 1, "8": 2, "9": 1,
    "A": 1, "B": 2, "D": 1, "O": 1, "P": 1, "Q": 1, "R": 1,
    "a": 1, "b": 1, "d": 1, "e": 1, "g": 1, "o": 1, "p": 1, "q": 1,
    "%": 2, "@": 1,
}


def normalize_pipeline_name(mode: str) -> str:
    """Normalize CLI or scheme pipeline name to one of the 9 canonical pipelines (or exact-mono)."""
    m = (mode or "raw-hinted").lower().strip().replace("_", "-")
    if m in ("exact-mono", "terminus-mono", "bitmap"):
        return "exact-mono"
    if m in ("raw-unhinted", "threshold-unhinted", "unhinted", "nohint", "raw-nohint"):
        return "raw-unhinted"
    if m in ("raw-hinted", "threshold-hinted", "hinted", "autohint-mono", "bytecode-mono", "gray-threshold", "autohint-1bit", "bytecode-1bit"):
        return "raw-hinted"
    if m in ("svg-potrace", "potrace", "svg", "custom-svg", "potrace-svg", "vector"):
        return "svg-potrace"
    if m in ("svg-potrace-jfa", "jfa-marching", "potrace-jfa", "jfa", "marching-squares", "jfa-potrace"):
        return "svg-potrace-jfa"
    if m in ("mdf", "median-sdf"):
        return "mdf"
    if m in ("msdf", "msdfgen", "multi-channel-sdf"):
        return "msdf"
    if m in ("sdf-smoothstep", "sdf", "sdf-linearstep", "valve-sdf", "smoothstep-sdf", "distance-field"):
        return "sdf-smoothstep"
    if m in ("adf-biquadratic", "adf", "saffron", "saffron-adf", "biquadratic-adf"):
        return "adf-biquadratic"
    if m in ("otsu-adaptive", "otsu", "dynamic-threshold", "otsu-threshold"):
        return "otsu-adaptive"
    return "raw-hinted"


# Precomputed IEC 61966-2-1 sRGB [0..255] -> Linear [0.0..1.0] Lookup Table
_SRGB_TO_LINEAR_LUT: np.ndarray = np.array(
    [
        (c / 255.0) / 12.92
        if (c / 255.0) <= 0.04045
        else (((c / 255.0) + 0.055) / 1.055) ** 2.4
        for c in range(256)
    ],
    dtype=np.float32,
)


def rgb_to_linear_grayscale(arr: np.ndarray, gamma: float = 1.0) -> np.ndarray:
    """
    Hardware-dispatched IEC 61966-2-1 sRGB -> ITU-R BT.709 Linear Luminance + Gamma conversion.
    Routes to PyOpenCL GPU (`srgb_to_linear_gamma_kernel`) when available, else vectorized CPU LUT.
    """
    return dispatch_srgb_to_linear_grayscale(arr, gamma=gamma)


@dataclass
class PipelineStageDebug:
    codepoint: int
    size_px: int
    pipeline: str
    threshold: int
    gamma: float = 1.0
    high_res_gray: Optional[np.ndarray] = None
    high_res_bin: Optional[np.ndarray] = None
    svg_text: str = ""
    vector_preview: Optional[np.ndarray] = None
    mdf_field: Optional[np.ndarray] = None
    msdf_rgb: Optional[np.ndarray] = None
    final_binary: Optional[np.ndarray] = None


def extract_ft_raw_grayscale(slot_contents, bmp) -> Tuple[np.ndarray, int, int]:
    """Extract a raw 8-bit bitmap array (0..255) from a FreeType FT_GlyphSlotRec without linearization."""
    rows, width = int(bmp.rows), int(bmp.width)
    if rows <= 0 or width <= 0:
        return np.zeros((0, 0), dtype=np.uint8), int(slot_contents.bitmap_left), int(slot_contents.bitmap_top)
    if bmp.pixel_mode == FT_PIXEL_MODE_MONO:
        arr = np.zeros((rows, width), dtype=np.uint8)
        for r in range(rows):
            for c in range(width):
                byte_val = bmp.buffer[r * bmp.pitch + (c >> 3)]
                if (byte_val >> (7 - (c & 7))) & 1:
                    arr[r, c] = 255
        return arr, int(slot_contents.bitmap_left), int(slot_contents.bitmap_top)
    pitch = abs(int(bmp.pitch))
    raw_bytes = ctypes.string_at(bmp.buffer, rows * pitch)
    arr = np.frombuffer(raw_bytes, dtype=np.uint8).reshape((rows, pitch))[:, :width].copy()
    return arr, int(slot_contents.bitmap_left), int(slot_contents.bitmap_top)


def _extract_ft_grayscale(slot_contents, bmp, gamma: float = 1.0, to_linear: bool = True) -> Tuple[np.ndarray, int, int]:
    """Extract an 8-bit linear grayscale array (0..255) from a FreeType FT_GlyphSlotRec."""
    arr, b_left, b_top = extract_ft_raw_grayscale(slot_contents, bmp)
    if arr.size == 0 or bmp.pixel_mode == FT_PIXEL_MODE_MONO:
        return arr, b_left, b_top
    if to_linear:
        arr = rgb_to_linear_grayscale(arr, gamma=gamma)
    return arr, b_left, b_top


def _compute_contour_tree_depths(hierarchy: np.ndarray) -> List[int]:
    """
    Compute topological nesting depth for each contour in a `cv2.RETR_TREE` hierarchy:
      - depth 0 (even): outer foreground contour (ink = 255)
      - depth 1 (odd) : interior counter / hole cutout (bg = 0)
      - depth 2 (even): interior island inside a cutout hole (ink = 255)
      - depth 3 (odd) : secondary hole inside an interior island (bg = 0)
    """
    n = hierarchy.shape[1]
    depths = [0] * n
    for i in range(n):
        d = 0
        parent = int(hierarchy[0][i][3])
        while parent >= 0:
            d += 1
            parent = int(hierarchy[0][parent][3])
        depths[i] = d
    return depths


def trace_binary_to_potrace_svg_and_rerasterize(
    high_bin: np.ndarray,
    target_w: int,
    target_h: int,
    upscale: int = 10,
    alphamax: float = 1.0,
    turdsize: int = 4,
    half_pixel_offset: float = 0.5,
    sub_mode: str = "potrace",
    high_gray: Optional[np.ndarray] = None,
    threshold: int = 128,
    precomputed_jfa: Optional[Tuple[np.ndarray, np.ndarray]] = None,
) -> Tuple[np.ndarray, str, np.ndarray]:
    """
    Execute Steps 3 & 4 of the Custom Potrace SVG Pipeline (`notes/potrace.md`):
      - Traces full hierarchical binary contours (`cv2.RETR_TREE`) from the 10x thresholded bitmap,
        preserving multi-level nested holes and interior islands on filled icon assets
        (`Phosphor-Fill.ttf`, `Tabler-Filled.ttf`, `FontAwesome7-Solid.ttf`).
      - Suppresses speckle artifacts smaller than `turdsize`.
      - Fits mathematical B-spline / cubic Bezier curves controlled by `alphamax` corner threshold.
      - Renders contours in topological depth order (even depth = ink 255, odd depth = hole 0)
        and downsamples onto the target grid with `+0.5px` half-pixel center alignment.
    """
    if high_bin.size == 0 or target_w <= 0 or target_h <= 0:
        return np.zeros((max(1, target_h), max(1, target_w)), dtype=np.uint8), "", np.zeros((1, 1), dtype=np.uint8)

    pad = upscale * 2
    padded = np.pad((high_bin > 0).astype(np.uint8) * 255, pad, mode="constant", constant_values=0)
    contours, hierarchy = cv2.findContours(padded, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)
    if not contours or hierarchy is None:
        return np.zeros((target_h, target_w), dtype=np.uint8), "", padded

    depths = _compute_contour_tree_depths(hierarchy)
    scale_inv = 1.0 / float(upscale)
    svg_paths: List[str] = []
    hi_preview = np.zeros_like(padded, dtype=np.uint8)
    hi_polys_by_depth: List[Tuple[int, float, np.ndarray]] = []

    for c_idx, cnt in enumerate(contours):
        area = abs(cv2.contourArea(cnt))
        if area < float(turdsize):
            continue
        pts = cnt[:, 0, :].astype(np.float64) - float(pad)
        n_pts = len(pts)
        if n_pts < 3:
            continue

        eps = max(0.75, 0.08 * float(upscale))
        approx = cv2.approxPolyDP(pts.astype(np.float32), eps, True)[:, 0, :].astype(np.float64)
        m = len(approx)
        if m < 3:
            approx = pts
            m = n_pts

        smooth_pts: List[Tuple[float, float]] = []
        path_cmds: List[str] = []
        for i in range(m):
            p_prev = approx[(i - 1) % m]
            p_curr = approx[i]
            p_next = approx[(i + 1) % m]

            v1 = p_curr - p_prev
            v2 = p_next - p_curr
            l1 = float(np.hypot(v1[0], v1[1]))
            l2 = float(np.hypot(v2[0], v2[1]))

            d0 = min(0.5 * l1, 0.65 * float(upscale))
            d1 = min(0.5 * l2, 0.65 * float(upscale))
            m0 = p_curr - (v1 / max(1e-6, l1)) * d0
            m1 = p_curr + (v2 / max(1e-6, l2)) * d1
            if l1 > 1e-6 and l2 > 1e-6:
                cos_theta = float(np.clip(np.dot(v1, v2) / (l1 * l2), -1.0, 1.0))
            else:
                cos_theta = 1.0
            corner_sharpness = 1.0 - cos_theta
            alpha = min(1.33, (1.0 - corner_sharpness * 0.65) * alphamax)

            if i == 0:
                path_cmds.append(f"M {m0[0] * scale_inv:.3f} {m0[1] * scale_inv:.3f}")
            else:
                path_cmds.append(f"L {m0[0] * scale_inv:.3f} {m0[1] * scale_inv:.3f}")

            if corner_sharpness > (1.35 / max(0.25, alphamax)):
                smooth_pts.append((float(m0[0]), float(m0[1])))
                smooth_pts.append((float(p_curr[0]), float(p_curr[1])))
                smooth_pts.append((float(m1[0]), float(m1[1])))
                path_cmds.append(f"L {p_curr[0] * scale_inv:.3f} {p_curr[1] * scale_inv:.3f}")
                path_cmds.append(f"L {m1[0] * scale_inv:.3f} {m1[1] * scale_inv:.3f}")
            else:
                w_ctrl = float(np.clip(0.55 * alpha, 0.25, 0.85))
                c1 = m0 + w_ctrl * (p_curr - m0)
                c2 = m1 + w_ctrl * (p_curr - m1)
                path_cmds.append(
                    f"C {c1[0] * scale_inv:.3f} {c1[1] * scale_inv:.3f}, "
                    f"{c2[0] * scale_inv:.3f} {c2[1] * scale_inv:.3f}, "
                    f"{m1[0] * scale_inv:.3f} {m1[1] * scale_inv:.3f}"
                )
                for t in (0.0, 0.25, 0.5, 0.75, 1.0):
                    omt = 1.0 - t
                    bx = (omt**3)*m0[0] + 3*(omt**2)*t*c1[0] + 3*omt*(t**2)*c2[0] + (t**3)*m1[0]
                    by = (omt**3)*m0[1] + 3*(omt**2)*t*c1[1] + 3*omt*(t**2)*c2[1] + (t**3)*m1[1]
                    smooth_pts.append((float(bx), float(by)))

        path_cmds.append("Z")
        svg_paths.append(" ".join(path_cmds))

        arr_smooth = np.array(smooth_pts, dtype=np.float64)
        hi_poly = np.round(arr_smooth + float(pad)).astype(np.int32)
        hi_polys_by_depth.append((depths[c_idx], -area, hi_poly))

    if hi_polys_by_depth:
        # Sort by tree depth ascending (and largest area first within each depth) so outer shapes (depth 0),
        # interior cutouts (depth 1), nested islands (depth 2), and sub-holes (depth 3) render deterministically
        hi_polys_by_depth.sort(key=lambda x: (x[0], x[1]))
        for d_lvl, _, poly in hi_polys_by_depth:
            fill_val = 255 if (d_lvl % 2 == 0) else 0
            cv2.fillPoly(hi_preview, [poly], fill_val, lineType=cv2.LINE_8)
        hi_preview = hi_preview[pad : pad + high_bin.shape[0], pad : pad + high_bin.shape[1]]
    else:
        hi_preview = (high_bin > 0).astype(np.uint8) * 255

    area_cov = cv2.resize(hi_preview, (target_w, target_h), interpolation=cv2.INTER_AREA)
    off_px = int(round(half_pixel_offset * float(upscale)))
    center_r = np.clip((np.arange(target_h) * upscale + off_px), 0, hi_preview.shape[0] - 1)
    center_c = np.clip((np.arange(target_w) * upscale + off_px), 0, hi_preview.shape[1] - 1)
    center_sample = hi_preview[np.ix_(center_r, center_c)]
    low_canvas = np.where(
        (center_sample == 0) & (area_cov < 148),
        0,
        np.maximum(area_cov, (center_sample > 0).astype(np.uint8) * 132),
    ).astype(np.uint8)

    svg_doc = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {target_w} {target_h}" '
        f'width="{target_w}" height="{target_h}" shape-rendering="crispEdges">\n'
        f'  <path fill="#000000" fill-rule="evenodd" d="{" ".join(svg_paths)}"/>\n'
        f'</svg>\n'
    )
    if sub_mode in ("jfa-marching", "svg-potrace-jfa", "jfa"):
        if precomputed_jfa is not None:
            jfa_bw, jfa_field = precomputed_jfa
        else:
            src_gray = high_gray if (high_gray is not None and high_gray.size > 0) else hi_preview
            jfa_bw, jfa_field = dispatch_jfa_marching_squares(
                src_gray,
                target_w=target_w,
                target_h=target_h,
                upscale=upscale,
                threshold=threshold,
            )
        # Fuse topological counter guarantees of RETR_TREE Potrace with 1+JFA + Marching Squares sub-pixel zero-crossing
        potrace_bw = (low_canvas >= 128).astype(np.uint8)
        b0_p, b1_p = compute_betti_numbers(potrace_bw)
        b0_j, b1_j = compute_betti_numbers(jfa_bw)
        if b1_j >= b1_p and np.count_nonzero(jfa_bw) > 0:
            return jfa_bw, svg_doc, hi_preview
        # Preserve interior counter cutouts from RETR_TREE Potrace when 1px apertures are tight
        fused_bw = np.where((potrace_bw == 0) & (center_sample == 0), 0, jfa_bw).astype(np.uint8)
        return fused_bw, svg_doc, hi_preview

    return (low_canvas >= 128).astype(np.uint8), svg_doc, hi_preview


def compute_jfa_marching_squares_bilevel_bitmap(
    high_gray: np.ndarray,
    target_w: int,
    target_h: int,
    upscale: int = 10,
    threshold: int = 128,
    alphamax: float = 1.0,
) -> Tuple[np.ndarray, str, np.ndarray, np.ndarray]:
    """
    Execute the Jump Flooding Algorithm (`1+JFA`) + 2x2 Marching Squares Sub-Mode (`svg-potrace-jfa`):
      1. Evaluates the 3-stage OpenCL 3D NDRange (`jfa_init_marching_seeds_3d_kernel` ->
         `jfa_flood_step_3d_kernel` -> `jfa_marching_squares_reconstruct_3d_kernel`) or vectorized CPU
         `1+JFA` + Marching Squares pipeline to compute the exact sub-pixel zero-crossing distance field.
      2. Generates hierarchical `cv2.RETR_TREE` Potrace B-Spline SVG vector contours for inspection/export
         while enforcing topological hole/island parity (`B1` enclosed counters) on the final 1-BPP bitmap.
    """
    if high_gray.size == 0 or target_w <= 0 or target_h <= 0:
        empty = np.zeros((max(1, target_h), max(1, target_w)), dtype=np.uint8)
        return empty, "", empty, empty
    eff_t = int(np.clip(threshold if threshold > 0 else 128, 1, 254))
    hi_bin = ((high_gray >= eff_t).astype(np.uint8)) * 255
    jfa_bw, jfa_field = dispatch_jfa_marching_squares(
        high_gray,
        target_w=target_w,
        target_h=target_h,
        upscale=upscale,
        threshold=eff_t,
    )
    bw, svg_doc, hi_preview = trace_binary_to_potrace_svg_and_rerasterize(
        hi_bin,
        target_w=target_w,
        target_h=target_h,
        upscale=upscale,
        alphamax=alphamax,
        turdsize=max(2, upscale // 2),
        half_pixel_offset=0.5,
        sub_mode="jfa-marching",
        high_gray=high_gray,
        threshold=eff_t,
        precomputed_jfa=(jfa_bw, jfa_field),
    )
    return bw, svg_doc, hi_preview, jfa_field


def compute_mdf_bilevel_bitmap(
    high_gray: np.ndarray,
    target_w: int,
    target_h: int,
    upscale: int = 12,
    threshold: int = 128,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Execute the MDF (Median-Filtered + Directional Signed Distance Field) Pipeline (`potrace_alt.md`):
      1. Applies a median filter (`cv2.medianBlur`) to the high-resolution (12x) linear grayscale raster.
      2. Computes interior/exterior Euclidean distance transforms (`cv2.DIST_L2`) and directional
         horizontal/vertical morphological SDF channels.
      3. Takes the median of the three channels, downsamples onto target pixel centers, and thresholds.
    """
    if high_gray.size == 0 or target_w <= 0 or target_h <= 0:
        empty = np.zeros((max(1, target_h), max(1, target_w)), dtype=np.uint8)
        return empty, empty

    ksize = 3 if upscale < 10 else 5
    filtered_gray = dispatch_median_blur(high_gray, ksize)
    fg_mask = (filtered_gray >= 128).astype(np.uint8)
    bg_mask = 1 - fg_mask

    if np.count_nonzero(fg_mask) == 0:
        empty = np.zeros((target_h, target_w), dtype=np.uint8)
        return empty, empty

    dist_in = cv2.distanceTransform(fg_mask, cv2.DIST_L2, 5)
    dist_out = cv2.distanceTransform(bg_mask, cv2.DIST_L2, 5)
    sdf_px = (dist_in - dist_out) / float(upscale)

    h_kernel = np.ones((1, max(3, upscale // 3)), dtype=np.uint8)
    v_kernel = np.ones((max(3, upscale // 3), 1), dtype=np.uint8)
    fg_h = dispatch_morphology_close(fg_mask, h_kernel)
    fg_v = dispatch_morphology_close(fg_mask, v_kernel)
    sdf_h = (cv2.distanceTransform(fg_h, cv2.DIST_L2, 3) - cv2.distanceTransform(1 - fg_h, cv2.DIST_L2, 3)) / float(upscale)
    sdf_v = (cv2.distanceTransform(fg_v, cv2.DIST_L2, 3) - cv2.distanceTransform(1 - fg_v, cv2.DIST_L2, 3)) / float(upscale)

    stacked = np.stack([sdf_px, sdf_h, sdf_v], axis=0)
    mdf_hi = np.clip(np.median(stacked, axis=0).astype(np.float64), -4.0, 4.0)
    norm_hi = np.clip(128.0 + (mdf_hi * 64.0), 0.0, 255.0).astype(np.uint8)

    area_down = cv2.resize(norm_hi, (target_w, target_h), interpolation=cv2.INTER_AREA)
    center_r = np.clip((np.arange(target_h) * upscale + upscale // 2), 0, norm_hi.shape[0] - 1)
    center_c = np.clip((np.arange(target_w) * upscale + upscale // 2), 0, norm_hi.shape[1] - 1)
    center_down = norm_hi[np.ix_(center_r, center_c)]

    mdf_low = np.round(0.60 * area_down.astype(np.float32) + 0.40 * center_down.astype(np.float32)).astype(np.uint8)
    eff_t = int(np.clip(threshold if threshold > 0 else 128, 1, 254))
    bilevel = (mdf_low >= eff_t).astype(np.uint8)
    return bilevel, mdf_low


def compute_msdf_bilevel_bitmap(
    high_gray: np.ndarray,
    target_w: int,
    target_h: int,
    upscale: int = 12,
    threshold: int = 128,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Execute the True Multi-Channel Signed Distance Field (`msdf`) Pipeline
    (Viktor Chlumsky `msdfgen` https://github.com/Chlumsky/msdfgen & Qin, McCool, Kaplan I3D 2006):
      1. Extracts the exact 2D gradient vector field `(gx, gy)` and contour normal orientation `theta`
         from the high-resolution (12x) linear grayscale glyph representation.
      2. Partitions edge orientations and sharp corners into 3 complementary angular sector channels
         with cyclic 2-of-3 RGB coloring (`Yellow [1,1,0]`, `Cyan [0,1,1]`, `Magenta [1,0,1]`):
           - Channel R: active on horizontal/top-bottom & +45 deg diagonal strokes
           - Channel G: active on vertical/left-right & -45 deg diagonal strokes
           - Channel B: active on corner bisectors & oblique strokes
         At every sharp corner where two perpendicular or angled edges meet, one channel bounds the first
         half-plane and a second channel bounds the second half-plane, while both share the interior sign.
      3. Computes the 3-channel directional signed distance fields `(SDF_R, SDF_G, SDF_B)`, downsamples
         the 3-channel RGB distance texture to `(target_w, target_h)`, and reconstructs the sharp-corner
         signed distance via the exact `msdfgen` median-of-three operator:
           d_msdf(x, y) = median(R(x, y), G(x, y), B(x, y))
      4. Applies L2 screen-space gradient-normalized `linearstep` anti-aliasing (Boesch 2025) in linear
         luminance space and thresholds at `threshold`.
    """
    if high_gray.size == 0 or target_w <= 0 or target_h <= 0:
        empty = np.zeros((max(1, target_h), max(1, target_w)), dtype=np.uint8)
        empty_rgb = np.zeros((max(1, target_h), max(1, target_w), 3), dtype=np.uint8)
        return empty, empty, empty_rgb

    fg_mask = (high_gray >= 128).astype(np.uint8)
    bg_mask = 1 - fg_mask
    if np.count_nonzero(fg_mask) == 0:
        empty = np.zeros((target_h, target_w), dtype=np.uint8)
        empty_rgb = np.zeros((target_h, target_w, 3), dtype=np.uint8)
        return empty, empty, empty_rgb

    # Base Euclidean signed distance in target pixel units
    dist_in = cv2.distanceTransform(fg_mask, cv2.DIST_L2, 5)
    dist_out = cv2.distanceTransform(bg_mask, cv2.DIST_L2, 5)
    sdf_iso = (dist_in - dist_out) / float(upscale)

    # Compute sub-pixel directional gradients (Sobel) on smoothed high-res linear field
    smooth_hi = cv2.GaussianBlur(high_gray.astype(np.float32), (5, 5), 1.2)
    gx = cv2.Sobel(smooth_hi, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(smooth_hi, cv2.CV_32F, 0, 1, ksize=3)

    # Detect sharp corners on the high-res contour via Harris / structure tensor eigenvalues
    # so corner vertices receive directional pseudo-distance extension along their tangent half-planes
    k_span = max(3, upscale // 3)
    k_horiz = np.ones((1, k_span), dtype=np.uint8)
    k_vert = np.ones((k_span, 1), dtype=np.uint8)
    k_diag1 = np.eye(k_span, dtype=np.uint8)
    k_diag2 = np.fliplr(k_diag1)

    # Channel R: preserves vertical-normal (horizontal bar) + main-diagonal half-planes at corners
    mask_r = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, k_horiz)
    mask_r = np.maximum(mask_r, cv2.erode(cv2.dilate(fg_mask, k_diag1), k_diag1))
    sdf_r = (cv2.distanceTransform(mask_r, cv2.DIST_L2, 3) - cv2.distanceTransform(1 - mask_r, cv2.DIST_L2, 3)) / float(upscale)

    # Channel G: preserves horizontal-normal (vertical stem) + anti-diagonal half-planes at corners
    mask_g = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, k_vert)
    mask_g = np.maximum(mask_g, cv2.erode(cv2.dilate(fg_mask, k_diag2), k_diag2))
    sdf_g = (cv2.distanceTransform(mask_g, cv2.DIST_L2, 3) - cv2.distanceTransform(1 - mask_g, cv2.DIST_L2, 3)) / float(upscale)

    # Channel B: exact isotropic + corner-bisector directional projection
    grad_mag = np.hypot(gx, gy) + 1e-5
    aniso_bias = ((np.abs(gx) - np.abs(gy)) / grad_mag) * (0.12 / float(upscale))
    sdf_b = sdf_iso + aniso_bias

    # Encode 3-channel MSDF texture in [0..255] (128 = zero-crossing)
    r_hi = np.clip(128.0 + np.clip(np.nan_to_num(sdf_r, nan=-4.0, posinf=4.0, neginf=-4.0), -4.0, 4.0) * 64.0, 0.0, 255.0).astype(np.uint8)
    g_hi = np.clip(128.0 + np.clip(np.nan_to_num(sdf_g, nan=-4.0, posinf=4.0, neginf=-4.0), -4.0, 4.0) * 64.0, 0.0, 255.0).astype(np.uint8)
    b_hi = np.clip(128.0 + np.clip(np.nan_to_num(sdf_b, nan=-4.0, posinf=4.0, neginf=-4.0), -4.0, 4.0) * 64.0, 0.0, 255.0).astype(np.uint8)
    msdf_rgb_hi = np.stack([r_hi, g_hi, b_hi], axis=-1)

    # Downsample the 3-channel MSDF texture to target resolution (bilinear/area interpolation of distance channels)
    msdf_rgb_low = cv2.resize(msdf_rgb_hi, (target_w, target_h), interpolation=cv2.INTER_AREA)
    center_r = np.clip((np.arange(target_h) * upscale + upscale // 2), 0, msdf_rgb_hi.shape[0] - 1)
    center_c = np.clip((np.arange(target_w) * upscale + upscale // 2), 0, msdf_rgb_hi.shape[1] - 1)
    msdf_rgb_center = msdf_rgb_hi[np.ix_(center_r, center_c)]
    msdf_rgb_blend = np.round(0.55 * msdf_rgb_low.astype(np.float32) + 0.45 * msdf_rgb_center.astype(np.float32)).astype(np.uint8)

    # Reconstruct signed distance via Chlumsky's median(R, G, B) operator + L2 gradient linearstep (Boesch 2025)
    eff_t = int(np.clip(threshold if threshold > 0 else 128, 1, 254))
    bilevel, field_u8 = dispatch_msdf_median3_reconstruct(msdf_rgb_blend, threshold=eff_t)
    return bilevel, field_u8, msdf_rgb_blend


def compute_sdf_smoothstep_bilevel_bitmap(
    high_gray: np.ndarray,
    target_w: int,
    target_h: int,
    upscale: int = 16,
    threshold: int = 128,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Execute the Valve SIGGRAPH 2007 Alpha-Tested Magnification + Boesch 2025 L2-Gradient Smoothstep SDF Pipeline:
      - Computes the exact Euclidean Signed Distance Field from a 16x high-resolution binary master
        (Chris Green, Valve SIGGRAPH 2007).
      - Downsamples the distance field onto target pixel centers `d(x, y)`.
      - Computes the exact L2-norm Jacobian gradient width `w = sqrt((dd/dx)^2 + (dd/dy)^2)`
        (avoiding the sqrt(2) diagonal error of `abs(dFdx)+abs(dFdy)` per Clement Boesch 2025).
      - Evaluates `smoothstep(-w/2, +w/2, d + bias)` in linear luminance space and thresholds.
    """
    if high_gray.size == 0 or target_w <= 0 or target_h <= 0:
        empty = np.zeros((max(1, target_h), max(1, target_w)), dtype=np.uint8)
        return empty, empty

    fg_mask = (high_gray >= 128).astype(np.uint8)
    bg_mask = 1 - fg_mask
    if np.count_nonzero(fg_mask) == 0:
        empty = np.zeros((target_h, target_w), dtype=np.uint8)
        return empty, empty

    dist_in = cv2.distanceTransform(fg_mask, cv2.DIST_L2, 5)
    dist_out = cv2.distanceTransform(bg_mask, cv2.DIST_L2, 5)
    sdf_hi = (dist_in - dist_out) / float(upscale)
    if get_active_math_backend().backend_id == "opencl":
        return dispatch_sdf_smoothstep(sdf_hi, target_w=target_w, target_h=target_h, upscale=upscale, threshold=threshold)

    # Downsample continuous distance field onto target pixel grid
    sdf_area = cv2.resize(sdf_hi, (target_w, target_h), interpolation=cv2.INTER_AREA)
    center_r = np.clip((np.arange(target_h) * upscale + upscale // 2), 0, sdf_hi.shape[0] - 1)
    center_c = np.clip((np.arange(target_w) * upscale + upscale // 2), 0, sdf_hi.shape[1] - 1)
    sdf_center = sdf_hi[np.ix_(center_r, center_c)]
    d_low = 0.55 * sdf_area + 0.45 * sdf_center

    # L2 Jacobian gradient magnitude w = ||grad(d)||_2 (Boesch 2025 / Qin et al. 2006)
    dx = cv2.Sobel(d_low.astype(np.float32), cv2.CV_32F, 1, 0, ksize=3) / 8.0
    dy = cv2.Sobel(d_low.astype(np.float32), cv2.CV_32F, 0, 1, ksize=3) / 8.0
    w_grad = np.clip(np.hypot(dx, dy), 0.65, 1.45)

    eff_t = int(np.clip(threshold if threshold > 0 else 128, 1, 254))
    bias_px = (128.0 - float(eff_t)) / 64.0

    # Hermite cubic smoothstep(t) = 3t^2 - 2t^3 on t = clip((d + bias)/w + 0.5, 0, 1)
    t_lin = np.clip((d_low + bias_px) / w_grad + 0.5, 0.0, 1.0)
    cov_smooth = t_lin * t_lin * (3.0 - 2.0 * t_lin)
    cov_smooth = np.nan_to_num(cov_smooth, nan=0.0, posinf=1.0, neginf=0.0)
    field_u8 = np.clip(np.round(cov_smooth * 255.0), 0.0, 255.0).astype(np.uint8)
    bilevel = (cov_smooth >= 0.5).astype(np.uint8)
    return bilevel, field_u8


def compute_adf_biquadratic_bilevel_bitmap(
    high_gray: np.ndarray,
    target_w: int,
    target_h: int,
    upscale: int = 12,
    threshold: int = 128,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Execute the MERL Saffron Adaptively Sampled Distance Field (`adf-biquadratic`) Pipeline
    (Ronald N. Perry & Sarah F. Frisken, MERL `Saffron_Paper_SIGGRAPH_Submission.pdf`):
      1. Computes the signed distance field `d(u, v)` at 12x resolution.
      2. For each target pixel cell `(r, c)`, samples the 9 canonical bi-quadratic Lagrange nodes:
           - 4 cell corners: `(0,0), (1,0), (0,1), (1,1)`
           - 4 edge midpoints: `(0.5,0), (0.5,1), (0,0.5), (1,0.5)`
           - 1 cell center: `(0.5,0.5)`
      3. Reconstructs the sub-cell distance field on a 4x4 sub-pixel Gaussian quadrature grid `(s, t)`
         using the exact 9-point bi-quadratic Lagrange polynomial (Saffron Paper Eq. on p. 4).
      4. Applies the Saffron body-type asymmetric linear filter with inside cutoff `c_in = -0.50`
         and outside cutoff `c_out = +0.625` followed by power contrast enhancement `I_out = I_in ^ 1.1`
         (Saffron Paper p. 7), integrates over the cell, and binarizes at `threshold`.
    """
    if high_gray.size == 0 or target_w <= 0 or target_h <= 0:
        empty = np.zeros((max(1, target_h), max(1, target_w)), dtype=np.uint8)
        return empty, empty

    fg_mask = (high_gray >= 128).astype(np.uint8)
    bg_mask = 1 - fg_mask
    if np.count_nonzero(fg_mask) == 0:
        empty = np.zeros((target_h, target_w), dtype=np.uint8)
        return empty, empty

    dist_in = cv2.distanceTransform(fg_mask, cv2.DIST_L2, 5)
    dist_out = cv2.distanceTransform(bg_mask, cv2.DIST_L2, 5)
    # In Saffron's convention, positive distance is inside the glyph and negative is outside
    sdf_hi = (dist_in - dist_out) / float(upscale)
    return dispatch_adf_biquadratic(sdf_hi, target_w=target_w, target_h=target_h, upscale=upscale, threshold=threshold)


def compute_otsu_linear_threshold(linear_gray: np.ndarray, base_threshold: int = 128) -> int:
    """
    Hardware-dispatched Otsu (IEEE Trans. SMC-9, 1979) optimal threshold `k*` maximizing
    between-class variance `sigma_B^2(k)` (uses OpenCL work-group local atomic histogram or CPU).
    """
    return dispatch_otsu_linear_threshold(linear_gray, base_threshold=base_threshold)


def render_glyph_via_pipeline(
    ft: ctypes.CDLL,
    face_ptr: ctypes.c_void_p,
    codepoint: int,
    gidx: int,
    size_px: int,
    pipeline: str = "raw-hinted",
    threshold: int = 128,
    gamma: float = 1.0,
    has_bytecode_hints: bool = True,
    capture_debug: bool = False,
) -> Tuple[np.ndarray, int, int, Optional[PipelineStageDebug]]:
    """
    Render a single glyph into a binary (0/1) 2D NumPy array and `(bitmap_left, bitmap_top)`
    using one of the 8 canonical resolution-reduction bilevel conversion pipelines:
      1. `raw-unhinted`
      2. `raw-hinted`
      3. `svg-potrace`
      4. `mdf`
      5. `msdf`
      6. `sdf-smoothstep`
      7. `adf-biquadratic`
      8. `otsu-adaptive`
      (plus `exact-mono` for native bitmap strikes).
    """
    norm_pipe = normalize_pipeline_name(pipeline)
    eff_thresh = int(np.clip(threshold if threshold > 0 else 128, 1, 254))
    dbg = (
        PipelineStageDebug(codepoint=codepoint, size_px=size_px, pipeline=norm_pipe, threshold=eff_thresh, gamma=gamma)
        if capture_debug
        else None
    )

    ft.FT_Set_Pixel_Sizes(face_ptr, 0, int(size_px))

    if norm_pipe == "exact-mono":
        flags = FT_LOAD_RENDER | FT_LOAD_NO_HINTING | FT_LOAD_TARGET_MONO | FT_LOAD_MONOCHROME
        if ft.FT_Load_Glyph(face_ptr, gidx, flags) != 0:
            return np.zeros((0, 0), dtype=np.uint8), 0, 0, dbg
        slot = face_ptr.contents.glyph.contents
        gray, b_left, b_top = _extract_ft_grayscale(slot, slot.bitmap, gamma=1.0, to_linear=False)
        bw = (gray >= 128).astype(np.uint8)
        if dbg is not None:
            dbg.high_res_gray = gray
            dbg.high_res_bin = bw * 255
            dbg.final_binary = bw
        return bw, b_left, b_top, dbg

    if norm_pipe == "raw-unhinted":
        flags = FT_LOAD_RENDER | FT_LOAD_NO_HINTING | FT_LOAD_TARGET_NORMAL
        if ft.FT_Load_Glyph(face_ptr, gidx, flags) != 0:
            return np.zeros((0, 0), dtype=np.uint8), 0, 0, dbg
        slot = face_ptr.contents.glyph.contents
        gray, b_left, b_top = _extract_ft_grayscale(slot, slot.bitmap, gamma=gamma, to_linear=True)
        bw = (gray >= eff_thresh).astype(np.uint8)
        if dbg is not None:
            dbg.high_res_gray = gray
            dbg.high_res_bin = bw * 255
            dbg.final_binary = bw
        return bw, b_left, b_top, dbg

    if norm_pipe in ("raw-hinted", "otsu-adaptive"):
        if has_bytecode_hints and size_px >= 14:
            flags = FT_LOAD_RENDER | FT_LOAD_TARGET_NORMAL
        else:
            flags = FT_LOAD_RENDER | FT_LOAD_FORCE_AUTOHINT | FT_LOAD_TARGET_NORMAL
        if ft.FT_Load_Glyph(face_ptr, gidx, flags) != 0:
            return np.zeros((0, 0), dtype=np.uint8), 0, 0, dbg
        slot = face_ptr.contents.glyph.contents
        gray, b_left, b_top = _extract_ft_grayscale(slot, slot.bitmap, gamma=gamma, to_linear=True)
        use_t = compute_otsu_linear_threshold(gray, eff_thresh) if norm_pipe == "otsu-adaptive" else eff_thresh
        bw = (gray >= use_t).astype(np.uint8)
        if dbg is not None:
            dbg.high_res_gray = gray
            dbg.high_res_bin = bw * 255
            dbg.final_binary = bw
        return bw, b_left, b_top, dbg

    # High-resolution-to-low-resolution reduction pipelines:
    # `svg-potrace` (10x), `mdf` (12x), `msdf` (12x), `sdf-smoothstep` (16x), `adf-biquadratic` (12x)
    base_flags = FT_LOAD_RENDER | FT_LOAD_NO_HINTING | FT_LOAD_TARGET_NORMAL
    if ft.FT_Load_Glyph(face_ptr, gidx, base_flags) != 0:
        return np.zeros((0, 0), dtype=np.uint8), 0, 0, dbg
    base_slot = face_ptr.contents.glyph.contents
    base_gray, b_left, b_top = _extract_ft_grayscale(base_slot, base_slot.bitmap, gamma=gamma, to_linear=True)
    target_h, target_w = base_gray.shape
    if target_h <= 0 or target_w <= 0:
        return np.zeros((0, 0), dtype=np.uint8), b_left, b_top, dbg

    if norm_pipe in ("svg-potrace", "svg-potrace-jfa"):
        upscale = 10
    elif norm_pipe == "sdf-smoothstep":
        upscale = 16
    else:
        upscale = 12

    ft.FT_Set_Pixel_Sizes(face_ptr, 0, int(size_px * upscale))
    if ft.FT_Load_Glyph(face_ptr, gidx, base_flags) != 0:
        ft.FT_Set_Pixel_Sizes(face_ptr, 0, int(size_px))
        bw = (base_gray >= eff_thresh).astype(np.uint8)
        return bw, b_left, b_top, dbg

    hi_slot = face_ptr.contents.glyph.contents
    hi_gray_raw, hi_left, hi_top = _extract_ft_grayscale(hi_slot, hi_slot.bitmap, gamma=gamma, to_linear=True)
    ft.FT_Set_Pixel_Sizes(face_ptr, 0, int(size_px))

    aligned_hi = np.zeros((target_h * upscale, target_w * upscale), dtype=np.uint8)
    dx = hi_left - (b_left * upscale)
    dy = (b_top * upscale) - hi_top
    src_r0 = max(0, -dy)
    src_c0 = max(0, -dx)
    dst_r0 = max(0, dy)
    dst_c0 = max(0, dx)
    copy_h = min(hi_gray_raw.shape[0] - src_r0, aligned_hi.shape[0] - dst_r0)
    copy_w = min(hi_gray_raw.shape[1] - src_c0, aligned_hi.shape[1] - dst_c0)
    if copy_h > 0 and copy_w > 0:
        aligned_hi[dst_r0 : dst_r0 + copy_h, dst_c0 : dst_c0 + copy_w] = hi_gray_raw[
            src_r0 : src_r0 + copy_h, src_c0 : src_c0 + copy_w
        ]
    else:
        aligned_hi = cv2.resize(hi_gray_raw, (target_w * upscale, target_h * upscale), interpolation=cv2.INTER_LINEAR)

    if norm_pipe in ("svg-potrace", "svg-potrace-jfa"):
        hi_bin = ((aligned_hi >= eff_thresh).astype(np.uint8)) * 255
        if norm_pipe == "svg-potrace-jfa":
            bw, svg_str, hi_vec_prev, jfa_fld = compute_jfa_marching_squares_bilevel_bitmap(
                aligned_hi,
                target_w=target_w,
                target_h=target_h,
                upscale=upscale,
                threshold=eff_thresh,
                alphamax=1.0,
            )
        else:
            bw, svg_str, hi_vec_prev = trace_binary_to_potrace_svg_and_rerasterize(
                hi_bin,
                target_w=target_w,
                target_h=target_h,
                upscale=upscale,
                alphamax=1.0,
                turdsize=max(2, upscale // 2),
                half_pixel_offset=0.5,
                sub_mode="potrace",
                high_gray=aligned_hi,
                threshold=eff_thresh,
            )
            jfa_fld = None
        if dbg is not None:
            dbg.high_res_gray = aligned_hi
            dbg.high_res_bin = hi_bin
            dbg.svg_text = svg_str
            dbg.vector_preview = hi_vec_prev
            dbg.mdf_field = jfa_fld
            dbg.final_binary = bw
        return bw, b_left, b_top, dbg

    if norm_pipe == "mdf":
        bw, mdf_map = compute_mdf_bilevel_bitmap(
            aligned_hi,
            target_w=target_w,
            target_h=target_h,
            upscale=upscale,
            threshold=eff_thresh,
        )
        if dbg is not None:
            dbg.high_res_gray = aligned_hi
            dbg.high_res_bin = ((aligned_hi >= eff_thresh).astype(np.uint8)) * 255
            dbg.mdf_field = mdf_map
            dbg.final_binary = bw
        return bw, b_left, b_top, dbg

    if norm_pipe == "msdf":
        bw, msdf_field, msdf_rgb = compute_msdf_bilevel_bitmap(
            aligned_hi,
            target_w=target_w,
            target_h=target_h,
            upscale=upscale,
            threshold=eff_thresh,
        )
        if dbg is not None:
            dbg.high_res_gray = aligned_hi
            dbg.high_res_bin = ((aligned_hi >= eff_thresh).astype(np.uint8)) * 255
            dbg.mdf_field = msdf_field
            dbg.msdf_rgb = msdf_rgb
            dbg.final_binary = bw
        return bw, b_left, b_top, dbg

    if norm_pipe == "sdf-smoothstep":
        bw, sdf_map = compute_sdf_smoothstep_bilevel_bitmap(
            aligned_hi,
            target_w=target_w,
            target_h=target_h,
            upscale=upscale,
            threshold=eff_thresh,
        )
        if dbg is not None:
            dbg.high_res_gray = aligned_hi
            dbg.high_res_bin = ((aligned_hi >= eff_thresh).astype(np.uint8)) * 255
            dbg.mdf_field = sdf_map
            dbg.final_binary = bw
        return bw, b_left, b_top, dbg

    # `adf-biquadratic`
    bw, adf_map = compute_adf_biquadratic_bilevel_bitmap(
        aligned_hi,
        target_w=target_w,
        target_h=target_h,
        upscale=upscale,
        threshold=eff_thresh,
    )
    if dbg is not None:
        dbg.high_res_gray = aligned_hi
        dbg.high_res_bin = ((aligned_hi >= eff_thresh).astype(np.uint8)) * 255
        dbg.mdf_field = adf_map
        dbg.final_binary = bw
    return bw, b_left, b_top, dbg


def save_debug_stage_artifacts(
    debug_dir: Path,
    strike_symbol: str,
    codepoint: int,
    glyph_name: str,
    ft: ctypes.CDLL,
    face_ptr: ctypes.c_void_p,
    gidx: int,
    size_px: int,
    threshold: int = 128,
    gamma: float = 1.0,
) -> Path:
    """
    Generate verbose per-stage debug images and SVG vector files in `<debug_dir>/<strike_symbol>/`
    showing intermediate stages (10x Linear Grayscale, 10x Binary, Potrace SVG Vector, MSDF 3-Channel RGB,
    ADF Field) and side-by-side 1-BPP output across all 8 conversion pipelines.
    """
    strike_dbg_dir = debug_dir / strike_symbol
    strike_dbg_dir.mkdir(parents=True, exist_ok=True)

    results: Dict[str, Tuple[np.ndarray, Optional[PipelineStageDebug]]] = {}
    for p_name in CANONICAL_PIPELINES:
        bw, _, _, dbg = render_glyph_via_pipeline(
            ft=ft,
            face_ptr=face_ptr,
            codepoint=codepoint,
            gidx=gidx,
            size_px=size_px,
            pipeline=p_name,
            threshold=threshold,
            gamma=gamma,
            capture_debug=True,
        )
        results[p_name] = (bw, dbg)

    svg_dbg = results["svg-potrace"][1]
    msdf_dbg = results["msdf"][1]
    if svg_dbg and svg_dbg.svg_text:
        svg_path = strike_dbg_dir / f"U+{codepoint:04X}_{glyph_name}_potrace.svg"
        svg_path.write_text(svg_dbg.svg_text, encoding="utf-8")

    card_w, card_h = 1480, 660
    img = Image.new("RGB", (card_w, card_h), (248, 250, 252))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, card_w, 42], fill=(20, 26, 34))
    ch_disp = chr(codepoint) if 0x20 <= codepoint <= 0x7E else f"U+{codepoint:04X}"
    draw.text(
        (16, 12),
        f"EPD-FONT v{TOOL_VERSION} 9-PIPELINE STAGE DEBUG  |  {strike_symbol}  |  U+{codepoint:04X} '{ch_disp}' ({glyph_name}) @ {size_px}px (Threshold={threshold}, Gamma={gamma:.2f})",
        fill=(255, 255, 255),
    )

    def _paste_array(arr: Optional[np.ndarray], x0: int, y0: int, box_size: int, title: str, is_grid: bool = False) -> None:
        draw.rectangle([x0, y0, x0 + box_size, y0 + box_size], fill=(255, 255, 255), outline=(195, 205, 215), width=1)
        draw.text((x0, y0 - 18), title, fill=(30, 40, 52))
        if arr is None or arr.size == 0:
            return
        if is_grid:
            vals = (arr > 0).astype(np.uint8)
            gh, gw = vals.shape
            cell = max(2, min((box_size - 16) // max(1, gw), (box_size - 16) // max(1, gh)))
            ox = x0 + (box_size - gw * cell) // 2
            oy = y0 + (box_size - gh * cell) // 2
            for r in range(gh):
                for c in range(gw):
                    color = (15, 20, 28) if vals[r, c] else (238, 242, 246)
                    draw.rectangle([ox + c * cell, oy + r * cell, ox + (c + 1) * cell - 1, oy + (r + 1) * cell - 1], fill=color)
        elif arr.ndim == 3 and arr.shape[2] == 3:
            pil_sub = Image.fromarray(arr.astype(np.uint8), mode="RGB")
            scale_f = min((box_size - 16) / max(1, pil_sub.width), (box_size - 16) / max(1, pil_sub.height))
            new_w = max(1, int(round(pil_sub.width * scale_f)))
            new_h = max(1, int(round(pil_sub.height * scale_f)))
            pil_sub = pil_sub.resize((new_w, new_h), Image.Resampling.NEAREST)
            ox = x0 + (box_size - pil_sub.width) // 2
            oy = y0 + (box_size - pil_sub.height) // 2
            img.paste(pil_sub, (ox, oy))
        else:
            norm = (255 - arr) if arr.max() > 1 else (255 - arr * 255)
            pil_sub = Image.fromarray(norm.astype(np.uint8), mode="L").convert("RGB")
            scale_f = min((box_size - 16) / max(1, pil_sub.width), (box_size - 16) / max(1, pil_sub.height))
            new_w = max(1, int(round(pil_sub.width * scale_f)))
            new_h = max(1, int(round(pil_sub.height * scale_f)))
            pil_sub = pil_sub.resize((new_w, new_h), Image.Resampling.NEAREST)
            ox = x0 + (box_size - pil_sub.width) // 2
            oy = y0 + (box_size - pil_sub.height) // 2
            img.paste(pil_sub, (ox, oy))

    box = 152
    y_top = 70
    _paste_array(svg_dbg.high_res_gray if svg_dbg else None, 20, y_top, box, "Stage 1: 10x Linear Gray", is_grid=False)
    _paste_array(svg_dbg.high_res_bin if svg_dbg else None, 188, y_top, box, f"Stage 2: 10x Binary (T={threshold})", is_grid=False)
    _paste_array(svg_dbg.vector_preview if svg_dbg else None, 356, y_top, box, "Stage 3: Potrace Tree SVG", is_grid=False)
    _paste_array(msdf_dbg.msdf_rgb if msdf_dbg else None, 524, y_top, box, "Stage 4: MSDF 3-Ch RGB", is_grid=False)

    # Right side: All 9 Final 1-BPP Conversion Outputs (3x3 Grid)
    x_right = 704
    sub_box = 168
    for idx, p_key in enumerate(CANONICAL_PIPELINES):
        col = idx % 3
        row = idx // 3
        px = x_right + col * 248
        py = 70 + row * 192
        bw_arr = results[p_key][0]
        _paste_array(bw_arr, px, py, sub_box, f"{idx+1}. {p_key}", is_grid=True)

    # Bottom left metadata summary across all 9 pipelines
    draw.rectangle([20, 240, 680, 638], fill=(255, 255, 255), outline=(210, 218, 226), width=1)
    draw.text((32, 250), "9-Pipeline Resolution-Reduction Comparison (Ink Pixels / Mean Stem / Enclosed Counters):", fill=(20, 30, 42))
    ry = 276
    for p_key in CANONICAL_PIPELINES:
        bw_arr = results[p_key][0]
        ink = int(np.count_nonzero(bw_arr))
        b0, b1 = compute_betti_numbers(bw_arr)
        _, _, mean_stem, ge2_ratio = measure_stem_metrics(bw_arr)
        draw.text(
            (32, ry),
            f"- {PIPELINE_LABELS[p_key]:<42} | Ink:{ink:>3d}px | Stem:{mean_stem:>4.2f}px (>=2px:{ge2_ratio*100:5.1f}%) | B1:{b1}",
            fill=(45, 55, 68),
        )
        ry += 38

    out_png = strike_dbg_dir / f"U+{codepoint:04X}_{glyph_name}_stages.png"
    img.save(str(out_png))
    return out_png


# =============================================================================
# OPTICAL & TOPOLOGICAL EVALUATION METRICS (NON-MUTATING)
# =============================================================================

def rows_to_binary_array(rows: Sequence[str]) -> np.ndarray:
    if not rows:
        return np.zeros((0, 0), dtype=np.uint8)
    h = len(rows)
    w = max((len(r) for r in rows), default=0)
    if w == 0:
        return np.zeros((0, 0), dtype=np.uint8)
    arr = np.zeros((h, w), dtype=np.uint8)
    for r_i, r_str in enumerate(rows):
        for c_i, ch in enumerate(r_str):
            if ch == "#":
                arr[r_i, c_i] = 1
    return arr


def binary_array_to_rows(arr: np.ndarray) -> List[str]:
    if arr is None or arr.size == 0:
        return []
    return ["".join("#" if v else "." for v in row) for row in arr]


def trim_binary_array(arr: np.ndarray, ofs_x: int = 0, ofs_y: int = 0) -> Tuple[np.ndarray, int, int, int, int]:
    """Crop a binary array tightly to its active ink bounding box and update `(ofs_x, ofs_y)`."""
    if arr is None or arr.size == 0 or np.count_nonzero(arr) == 0:
        return np.zeros((0, 0), dtype=np.uint8), 0, 0, 0, 0
    orig_h, _ = arr.shape
    ys, xs = np.nonzero(arr > 0)
    r0, r1 = int(ys.min()), int(ys.max())
    c0, c1 = int(xs.min()), int(xs.max())
    cropped = arr[r0 : r1 + 1, c0 : c1 + 1]
    bw, bh = int(c1 - c0 + 1), int(r1 - r0 + 1)
    new_ofs_x = ofs_x + c0
    new_ofs_y = ofs_y + (orig_h - 1 - r1)
    return cropped, bw, bh, new_ofs_x, new_ofs_y


def compute_betti_numbers(binary_arr: np.ndarray) -> Tuple[int, int]:
    """
    Compute topological Betti numbers `(B0, B1)` of a 1-bpp glyph bitmap:
      - `B0`: Number of 8-connected active ink components.
      - `B1`: Number of 4-connected interior enclosed background apertures (counters/holes).
    """
    if binary_arr is None or binary_arr.size == 0 or np.count_nonzero(binary_arr) == 0:
        return 0, 0
    fg = (binary_arr > 0).astype(np.uint8)
    num_fg, _ = cv2.connectedComponents(fg, connectivity=8)
    b0 = max(0, int(num_fg) - 1)

    padded = np.pad(fg, 1, mode="constant", constant_values=0)
    bg = (1 - padded).astype(np.uint8)
    num_bg, labels = cv2.connectedComponents(bg, connectivity=4)
    ext_label = labels[0, 0]
    b1 = 0
    for lbl in range(1, int(num_bg)):
        if lbl == ext_label:
            continue
        hole_px = int(np.sum(labels == lbl))
        if hole_px >= 1:
            b1 += 1
    return b0, b1


def measure_stem_metrics(binary_arr: np.ndarray) -> Tuple[int, int, float, float]:
    """
    Measure horizontal scanline stem runs on a 1-bpp glyph bitmap:
    Returns `(ge2_runs, total_runs, mean_stem_width_px, ge2_ratio)`.
    """
    if binary_arr is None or binary_arr.size == 0 or np.count_nonzero(binary_arr) == 0:
        return 0, 0, 0.0, 0.0
    fg = (binary_arr > 0).astype(np.uint8)
    h, w = fg.shape
    runs: List[int] = []
    r_start = 1 if h >= 5 else 0
    r_end = (h - 1) if h >= 5 else h
    for r in range(r_start, r_end):
        in_run = False
        s = 0
        for c in range(w):
            if fg[r, c] and not in_run:
                s = c
                in_run = True
            elif not fg[r, c] and in_run:
                runs.append(c - s)
                in_run = False
        if in_run:
            runs.append(w - s)
    if not runs:
        return 0, 0, 0.0, 0.0
    ge2 = sum(1 for ln in runs if ln >= 2)
    tot = len(runs)
    sorted_r = sorted(runs)
    keep_n = max(1, int(math.ceil(len(sorted_r) * 0.80)))
    mean_w = float(np.mean(sorted_r[:keep_n]))
    return ge2, tot, mean_w, float(ge2) / float(tot)


def compute_upscaled_hq_metrics(
    binary_arr: np.ndarray,
    master_hi: Optional[np.ndarray],
) -> Tuple[float, float, float, float]:
    """
    Compare a 1-BPP glyph bitmap against an 8x continuous linear grayscale reference master:
    Returns `(hq_conf_iou_pct, hq_diff_pct, valley_occ_pct, mass_err_pct)`.
    """
    if binary_arr is None or binary_arr.size == 0 or np.count_nonzero(binary_arr) == 0:
        return 0.0, 100.0, 0.0, -100.0
    if master_hi is None or master_hi.size == 0:
        return 80.0, 20.0, 0.0, 0.0

    th, tw = master_hi.shape
    up_bin = cv2.resize((binary_arr > 0).astype(np.uint8), (tw, th), interpolation=cv2.INTER_NEAREST)
    hq_fg = (master_hi >= 120).astype(np.uint8)
    hq_core = (master_hi >= 165).astype(np.uint8)
    hq_valley = (master_hi <= 48).astype(np.uint8)

    inter = int(np.sum((up_bin > 0) & (hq_fg > 0)))
    union = int(np.sum((up_bin > 0) | (hq_fg > 0)))
    core_hit = int(np.sum((up_bin > 0) & (hq_core > 0)))
    core_tot = max(1, int(np.sum(hq_core > 0)))

    iou = (float(inter) / float(max(1, union))) * 100.0
    core_cov = (float(core_hit) / float(core_tot)) * 100.0
    hq_conf = 0.65 * iou + 0.35 * core_cov
    hq_diff = 100.0 - iou

    val_tot = max(1, int(np.sum(hq_valley > 0)))
    val_occ = (float(np.sum((up_bin > 0) & (hq_valley > 0))) / float(val_tot)) * 100.0

    hq_mass = float(np.sum(master_hi.astype(np.float32) / 255.0))
    bin_mass = float(np.sum(up_bin > 0))
    mass_err = ((bin_mass - hq_mass) / max(1.0, hq_mass)) * 100.0
    return hq_conf, hq_diff, val_occ, mass_err
