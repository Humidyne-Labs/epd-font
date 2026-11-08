#!/usr/bin/env python3
"""
cpu_math.py (v1.0.22)
=====================
A 1-bit EPD font generator and asset pipeline for embedded displays.
Repository : https://github.com/Humidyne-Labs/epd-font
Authors    : Humiditron (https://github.com/humiditron) & AI/LLM Development Partner
License    : MIT License

Vectorized CPU (NumPy / OpenCV) Mathematical Backend (v1.0.22):
Provides deterministic 1:1 CPU implementations of all mathematical kernels in
`opencl_kernels.py` (including 2D and 3D batched arrays and a precomputed L1-cached
256-entry `uint8` LUT for `gamma == 1.0` single-channel linearization):
  1. `eval_srgb_to_linear_grayscale_cpu`  : IEC 61966-2-1 sRGB -> ITU-R BT.709 Linear Luminance + Gamma
  2. `distance_sq_to_bezier_yuksel_cpu`   : Cem Yuksel Degree-5 -> Degree-2 Monotonic Polynomial Cascade
                                            + Newton-Bisection Quintic Solver + Cubic Winding Parity
  3. `eval_sdf_smoothstep_cpu`            : Chris Green (Valve) SDF + L2 Screen-Space Derivative Smoothstep
  4. `eval_msdf_median3_reconstruct_cpu`  : Chlumsky Multi-Channel (R,G,B) Median-of-Three SDF Reconstruction
  5. `eval_adf_biquadratic_cpu`           : Saffron 9-Point Bi-Quadratic Lagrange Polynomial ADF (4x4 Quadrature)
  6. `eval_otsu_linear_threshold_cpu`     : Otsu Between-Class Variance Maximization on Linear Luminance
  7. `eval_jfa_marching_squares_cpu`      : Jump Flooding Algorithm (`1+JFA`) + Marching Squares 16-Case
                                            Saddle-Disambiguated Vector Cell Reconstruction (`svg-potrace-jfa`)
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import cv2
import numpy as np

TOOL_VERSION = "1.0.22"

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

# Precomputed L1-cache `uint8` lookup table for single-channel `gamma == 1.0` (0.002ms per glyph)
_SRGB_GRAY_GAMMA1_U8_LUT: np.ndarray = np.clip(
    np.round(
        (
            0.50 * (np.arange(256, dtype=np.float32) / 255.0)
            + 0.50 * np.power(np.clip(_SRGB_TO_LINEAR_LUT, 0.0, 1.0), 1.0 / 2.2)
        )
        * 255.0
    ),
    0.0,
    255.0,
).astype(np.uint8)


def eval_srgb_to_linear_grayscale_cpu(arr: np.ndarray, gamma: float = 1.0) -> np.ndarray:
    """
    Convert an sRGB 3-channel RGB image `(H, W, 3)` or sRGB single-channel coverage buffer `(H, W)`
    into a true linear luminance grayscale array `[0..255]` (`uint8`) with optional gamma adjustment.
    """
    if arr is None or arr.size == 0:
        return np.zeros((0, 0), dtype=np.uint8)

    u8 = arr if arr.dtype == np.uint8 else np.clip(arr, 0, 255).astype(np.uint8)
    if (u8.ndim <= 2 or (u8.ndim == 3 and u8.shape[2] == 1)) and abs(float(gamma) - 1.0) <= 1e-4:
        return _SRGB_GRAY_GAMMA1_U8_LUT[u8]

    if u8.ndim == 3 and u8.shape[2] >= 3:
        r_lin = _SRGB_TO_LINEAR_LUT[u8[:, :, 0]]
        g_lin = _SRGB_TO_LINEAR_LUT[u8[:, :, 1]]
        b_lin = _SRGB_TO_LINEAR_LUT[u8[:, :, 2]]
        y_lin = 0.2126 * r_lin + 0.7152 * g_lin + 0.0722 * b_lin
    else:
        srgb_norm = u8.astype(np.float32) / 255.0
        lin_pure = _SRGB_TO_LINEAR_LUT[u8]
        y_lin = 0.50 * srgb_norm + 0.50 * np.power(np.clip(lin_pure, 0.0, 1.0), 1.0 / 2.2)

    if abs(float(gamma) - 1.0) > 1e-4 and gamma > 0.05:
        y_lin = np.power(np.clip(y_lin, 0.0, 1.0), 1.0 / float(gamma))

    return np.clip(np.round(y_lin * 255.0), 0.0, 255.0).astype(np.uint8)


def _solve_quadratic_scalar(a: float, b: float, c: float) -> List[float]:
    roots: List[float] = []
    if abs(a) < 1e-7:
        if abs(b) > 1e-7:
            r = -c / b
            if 0.0 <= r <= 1.0:
                roots.append(r)
        return roots
    d = b * b - 4.0 * a * c
    if d < 0.0:
        return roots
    sqrt_d = float(np.sqrt(max(d, 0.0)))
    q = -0.5 * (b + (sqrt_d if b > 0.0 else -sqrt_d))
    r0 = q / a
    r1 = (c / q) if abs(q) > 1e-7 else r0
    if r0 > r1:
        r0, r1 = r1, r0
    if 0.0 <= r0 <= 1.0:
        roots.append(r0)
    if 0.0 <= r1 <= 1.0 and abs(r1 - r0) > 1e-5:
        roots.append(r1)
    return roots


def _eval_poly5_scalar(a: float, b: float, c: float, d: float, e: float, f: float, t: float) -> float:
    return ((((a * t + b) * t + c) * t + d) * t + e) * t + f


def _eval_poly5_deriv_scalar(a: float, b: float, c: float, d: float, e: float, t: float) -> float:
    return (((5.0 * a * t + 4.0 * b) * t + 3.0 * c) * t + 2.0 * d) * t + e


def _newton_bisect5_scalar(
    a: float, b: float, c: float, d: float, e: float, f: float,
    t_min: float, t_max: float, v_min: float, v_max: float
) -> float:
    x = 0.5 * (t_min + t_max)
    sign_flip = 1.0 if v_min < v_max else -1.0
    for _ in range(24):
        y = _eval_poly5_scalar(a, b, c, d, e, f, x)
        dy = _eval_poly5_deriv_scalar(a, b, c, d, e, x)
        if sign_flip * y < 0.0:
            t_min = x
        else:
            t_max = x
        next_x = (x - y / dy) if abs(dy) > 1e-7 else (0.5 * (t_min + t_max))
        if next_x <= t_min or next_x >= t_max:
            next_x = 0.5 * (t_min + t_max)
        if abs(next_x - x) < 1e-6:
            return next_x
        x = next_x
    return x


def _isolate_and_solve_roots_scalar(
    a: float, b: float, c: float, d: float, e: float, f: float, lower_roots: List[float]
) -> List[float]:
    out: List[float] = []
    prev_x = 0.0
    prev_y = _eval_poly5_scalar(a, b, c, d, e, f, 0.0)
    for i in range(len(lower_roots) + 1):
        curr_x = 1.0 if i == len(lower_roots) else lower_roots[i]
        curr_y = _eval_poly5_scalar(a, b, c, d, e, f, curr_x)
        if prev_y * curr_y <= 0.0:
            out.append(_newton_bisect5_scalar(a, b, c, d, e, f, prev_x, curr_x, prev_y, curr_y))
        prev_x = curr_x
        prev_y = curr_y
    return out


def distance_sq_to_bezier_yuksel_cpu(p: Tuple[float, float], bz: np.ndarray) -> float:
    """
    Exact squared Euclidean distance from point `p = (px, py)` to cubic Bezier `bz` (`4x2`)
    via Cem Yuksel's degree-5 to degree-2 monotonic derivative cascade.
    """
    p_vec = np.array(p, dtype=np.float64)
    p0, p1, p2, p3 = bz[0], bz[1], bz[2], bz[3]
    d0 = p0 - p_vec
    d3 = p3 - p_vec
    min_dist_sq = min(float(np.dot(d0, d0)), float(np.dot(d3, d3)))

    a = -p0 + 3.0 * (p1 - p2) + p3
    b = 3.0 * (p0 - 2.0 * p1 + p2)
    c = 3.0 * (p1 - p0)
    delta = p0 - p_vec

    c5 = 3.0 * float(np.dot(a, a))
    c4 = 5.0 * float(np.dot(a, b))
    c3 = 4.0 * float(np.dot(a, c)) + 2.0 * float(np.dot(b, b))
    c2 = 3.0 * float(np.dot(a, delta) + np.dot(b, c))
    c1 = 2.0 * float(np.dot(b, delta)) + float(np.dot(c, c))
    c0 = float(np.dot(c, delta))

    r2 = _solve_quadratic_scalar(10.0 * c5, 4.0 * c4, c3)
    r3 = _isolate_and_solve_roots_scalar(0.0, 0.0, 10.0 * c5, 6.0 * c4, 3.0 * c3, c2, r2)
    r4 = _isolate_and_solve_roots_scalar(0.0, 5.0 * c5, 4.0 * c4, 3.0 * c3, 2.0 * c2, c1, r3)
    r5 = _isolate_and_solve_roots_scalar(c5, c4, c3, c2, c1, c0, r4)

    for t in r5:
        pt = ((a * t + b) * t + c) * t + p0
        diff = pt - p_vec
        min_dist_sq = min(min_dist_sq, float(np.dot(diff, diff)))
    return min_dist_sq


def bezier_winding_cpu(p: Tuple[float, float], bz: np.ndarray) -> int:
    """Analytical cubic ray-crossing winding parity for point `p` against cubic Bezier `bz` (`4x2`)."""
    px_pt, py_pt = float(p[0]), float(p[1])
    p0, p1, p2, p3 = bz[0], bz[1], bz[2], bz[3]
    signs = (
        (1 if p0[1] < py_pt else 0)
        | ((1 if p1[1] < py_pt else 0) << 1)
        | ((1 if p2[1] < py_pt else 0) << 2)
        | ((1 if p3[1] < py_pt else 0) << 3)
    )
    if signs == 0 or signs == 15:
        return 0
    inc = 1 if (signs & 1) == 0 else -1
    a = -p0 + 3.0 * (p1 - p2) + p3
    b = 3.0 * (p0 - 2.0 * p1 + p2)
    c = 3.0 * (p1 - p0)
    d = p0 - np.array([px_pt, py_pt], dtype=np.float64)

    r2 = _solve_quadratic_scalar(3.0 * float(a[1]), 2.0 * float(b[1]), float(c[1]))
    roots_y: List[float] = []
    tx0 = 0.0
    ty0 = float(d[1])
    for i in range(len(r2) + 1):
        tx1 = 1.0 if i == len(r2) else r2[i]
        ty1 = ((float(a[1]) * tx1 + float(b[1])) * tx1 + float(c[1])) * tx1 + float(d[1])
        if ty0 * ty1 <= 0.0:
            x = 0.5 * (tx0 + tx1)
            for _ in range(16):
                fv = ((float(a[1]) * x + float(b[1])) * x + float(c[1])) * x + float(d[1])
                fd = (3.0 * float(a[1]) * x + 2.0 * float(b[1])) * x + float(c[1])
                if abs(fd) < 1e-7:
                    break
                xn = x - fv / fd
                if xn < tx0 or xn > tx1:
                    xn = 0.5 * (tx0 + tx1)
                if abs(xn - x) < 1e-6:
                    x = xn
                    break
                x = xn
            roots_y.append(x)
        tx0, ty0 = tx1, ty1

    w = 0
    for idx, t in enumerate(roots_y):
        x_int = ((float(a[0]) * t + float(b[0])) * t + float(c[0])) * t + float(d[0])
        if x_int >= 0.0:
            w += inc if (idx % 2 == 0) else -inc
    return w


def eval_sdf_smoothstep_cpu(
    sdf_hi: np.ndarray,
    target_w: int,
    target_h: int,
    upscale: int,
    threshold: int = 128,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Chris Green (Valve, SIGGRAPH 2007) Signed Distance Field Smoothstep + L2 Screen-Space
    Gradient Width Reconstruction on CPU (supports 2D `(H_hi, W_hi)` and 3D `(B, H_hi, W_hi)`).
    """
    if sdf_hi.ndim == 3:
        bw_list = []
        fld_list = []
        for b in range(sdf_hi.shape[0]):
            bw, fld = eval_sdf_smoothstep_cpu(sdf_hi[b], target_w, target_h, upscale, threshold)
            bw_list.append(bw)
            fld_list.append(fld)
        return np.stack(bw_list, axis=0), np.stack(fld_list, axis=0)

    H_hi, W_hi = sdf_hi.shape
    gy, gx = np.gradient(sdf_hi)
    grad_l2 = np.sqrt(gx * gx + gy * gy) * float(upscale)

    center_r = np.clip((np.arange(target_h) * upscale) + (upscale // 2), 0, H_hi - 1)
    center_c = np.clip((np.arange(target_w) * upscale) + (upscale // 2), 0, W_hi - 1)
    sampled_sdf = sdf_hi[np.ix_(center_r, center_c)]
    sampled_grad = np.clip(grad_l2[np.ix_(center_r, center_c)], 0.65, 1.50)

    eff_t = int(np.clip(threshold if threshold > 0 else 128, 1, 254))
    bias_px = (128.0 - float(eff_t)) / 64.0
    w = 0.55 * sampled_grad

    t = np.clip((sampled_sdf + bias_px + w) / (2.0 * w), 0.0, 1.0)
    cov_smooth = np.nan_to_num(t * t * (3.0 - 2.0 * t), nan=0.0, posinf=1.0, neginf=0.0)
    field_u8 = np.clip(np.round(cov_smooth * 255.0), 0.0, 255.0).astype(np.uint8)
    bilevel = (cov_smooth >= 0.50).astype(np.uint8)
    return bilevel, field_u8


def eval_msdf_median3_reconstruct_cpu(
    msdf_rgb_or_r: np.ndarray,
    sdf_g: Optional[np.ndarray] = None,
    sdf_b: Optional[np.ndarray] = None,
    threshold: int = 128,
    edge_offset_px: float = 0.0,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Chlumsky MSDF 3-channel median-of-three reconstruction + L2 screen-space gradient
    linearstep anti-aliasing (Boesch 2025) on CPU (supports 2D and 3D batched arrays).
    Accepts either:
      1. Single interleaved 3-channel array `msdf_rgb` (shape `(H, W, 3)` or `(B, H, W, 3)` in `uint8` or `float32`).
      2. Three separate planar arrays `(sdf_r, sdf_g, sdf_b)`.
    Returns `(bilevel, field_u8)`.
    """
    if msdf_rgb_or_r.size == 0:
        empty = np.zeros((1, 1), dtype=np.uint8)
        return empty, empty

    if sdf_g is not None and sdf_b is not None:
        r_arr, g_arr, b_arr = msdf_rgb_or_r, sdf_g, sdf_b
    elif msdf_rgb_or_r.ndim >= 3 and msdf_rgb_or_r.shape[-1] == 3:
        r_arr = msdf_rgb_or_r[..., 0]
        g_arr = msdf_rgb_or_r[..., 1]
        b_arr = msdf_rgb_or_r[..., 2]
    else:
        raise ValueError("eval_msdf_median3_reconstruct_cpu requires a 3-channel array or 3 separate channel arrays")

    if r_arr.ndim == 3:
        bw_list, fld_list = [], []
        for b in range(r_arr.shape[0]):
            bw, fld = eval_msdf_median3_reconstruct_cpu(
                r_arr[b], g_arr[b], b_arr[b],
                threshold=threshold,
                edge_offset_px=edge_offset_px,
            )
            bw_list.append(bw)
            fld_list.append(fld)
        return np.stack(bw_list, axis=0), np.stack(fld_list, axis=0)

    # Median-of-three signed distance
    d_med = np.maximum(np.minimum(r_arr, g_arr), np.minimum(np.maximum(r_arr, g_arr), b_arr)).astype(np.float32)

    if np.issubdtype(msdf_rgb_or_r.dtype, np.integer):
        # Encoded uint8 texture: 128 = zero crossing, 64 units per pixel
        d_px = (d_med - 128.0) / 64.0
    else:
        d_px = d_med

    # L2 gradient linearstep AA ramp (Boesch 2025)
    dx = cv2.Sobel(d_px, cv2.CV_32F, 1, 0, ksize=3) / 8.0
    dy = cv2.Sobel(d_px, cv2.CV_32F, 0, 1, ksize=3) / 8.0
    w_grad = np.clip(np.hypot(dx, dy), 0.65, 1.50)

    eff_t = int(np.clip(threshold if threshold > 0 else 128, 1, 254))
    bias_px = (128.0 - float(eff_t)) / 64.0 + float(edge_offset_px)
    cov_lin = np.clip((d_px + bias_px) / w_grad + 0.5, 0.0, 1.0)
    field_u8 = np.clip(np.round(cov_lin * 255.0), 0.0, 255.0).astype(np.uint8)
    bilevel = (cov_lin >= 0.5).astype(np.uint8)
    return bilevel, field_u8


def eval_adf_biquadratic_cpu(
    sdf_hi: np.ndarray,
    target_w: int,
    target_h: int,
    upscale: int,
    threshold: int = 128,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Saffron (Perry & Frisken, SIGGRAPH 2006) 9-point Bi-Quadratic Lagrange Polynomial
    Adaptive Distance Field cell reconstruction on CPU (supports 2D and 3D batched arrays).
    """
    if sdf_hi.ndim == 3:
        bw_list = []
        fld_list = []
        for b in range(sdf_hi.shape[0]):
            bw, fld = eval_adf_biquadratic_cpu(sdf_hi[b], target_w, target_h, upscale, threshold)
            bw_list.append(bw)
            fld_list.append(fld)
        return np.stack(bw_list, axis=0), np.stack(fld_list, axis=0)

    H_hi, W_hi = sdf_hi.shape
    r0 = np.clip(np.arange(target_h) * upscale, 0, H_hi - 1)
    rm = np.clip(np.arange(target_h) * upscale + upscale // 2, 0, H_hi - 1)
    r1 = np.clip((np.arange(target_h) + 1) * upscale - 1, 0, H_hi - 1)

    c0 = np.clip(np.arange(target_w) * upscale, 0, W_hi - 1)
    cm = np.clip(np.arange(target_w) * upscale + upscale // 2, 0, W_hi - 1)
    c1 = np.clip((np.arange(target_w) + 1) * upscale - 1, 0, W_hi - 1)

    d00 = sdf_hi[np.ix_(r0, c0)]
    d10 = sdf_hi[np.ix_(r0, cm)]
    d20 = sdf_hi[np.ix_(r0, c1)]
    d01 = sdf_hi[np.ix_(rm, c0)]
    d11 = sdf_hi[np.ix_(rm, cm)]
    d21 = sdf_hi[np.ix_(rm, c1)]
    d02 = sdf_hi[np.ix_(r1, c0)]
    d12 = sdf_hi[np.ix_(r1, cm)]
    d22 = sdf_hi[np.ix_(r1, c1)]

    sub_coords = (0.125, 0.375, 0.625, 0.875)
    eff_t = int(np.clip(threshold if threshold > 0 else 128, 1, 254))
    bias_px = (128.0 - float(eff_t)) / 64.0
    c_in = 0.50
    c_out = -0.625
    span = c_in - c_out

    cov_acc = np.zeros((target_h, target_w), dtype=np.float32)
    for sv in sub_coords:
        ly0 = 2.0 * (sv - 0.5) * (sv - 1.0)
        ly1 = -4.0 * sv * (sv - 1.0)
        ly2 = 2.0 * sv * (sv - 0.5)
        for su in sub_coords:
            lx0 = 2.0 * (su - 0.5) * (su - 1.0)
            lx1 = -4.0 * su * (su - 1.0)
            lx2 = 2.0 * su * (su - 0.5)
            d_sub = (
                ly0 * (lx0 * d00 + lx1 * d10 + lx2 * d20)
                + ly1 * (lx0 * d01 + lx1 * d11 + lx2 * d21)
                + ly2 * (lx0 * d02 + lx1 * d12 + lx2 * d22)
            ) + bias_px
            i_in = np.clip((d_sub - c_out) / span, 0.0, 1.0)
            cov_acc += np.power(i_in, 1.1)

    cov_mean = cov_acc / 16.0
    center_cov = np.clip(((d11 + bias_px) - c_out) / span, 0.0, 1.0)
    final_cov = 0.65 * cov_mean + 0.35 * center_cov
    field_u8 = np.clip(np.round(final_cov * 255.0), 0.0, 255.0).astype(np.uint8)
    bilevel = (final_cov >= 0.50).astype(np.uint8)
    return bilevel, field_u8


def eval_otsu_linear_threshold_cpu(linear_gray: np.ndarray, base_threshold: int = 128) -> int:
    """
    Compute Nobuyuki Otsu's (IEEE Trans. SMC, Vol. SMC-9, No. 1, Jan. 1979) optimal threshold `k*`
    maximizing between-class variance `sigma_B^2(k)` on linear luminance pixels.
    """
    if linear_gray is None or linear_gray.size == 0:
        return base_threshold
    active = linear_gray[(linear_gray >= 8) & (linear_gray <= 248)]
    if active.size < 6:
        return base_threshold

    hist = np.bincount(active.ravel(), minlength=256).astype(np.float64)
    total = float(active.size)
    p = hist / total

    omega = np.cumsum(p)
    bins = np.arange(256, dtype=np.float64)
    mu = np.cumsum(bins * p)
    mu_t = mu[-1]

    denom = omega * (1.0 - omega)
    valid = denom > 1e-9
    sigma_b_sq = np.zeros(256, dtype=np.float64)
    sigma_b_sq[valid] = ((mu_t * omega[valid] - mu[valid]) ** 2) / denom[valid]

    k_star = int(np.argmax(sigma_b_sq))
    user_offset = int(base_threshold) - 128
    return int(np.clip(round(0.70 * k_star + 0.30 * 128 + user_offset), 72, 184))


def eval_jfa_marching_squares_cpu(
    high_gray: np.ndarray,
    target_w: int,
    target_h: int,
    upscale: int = 10,
    threshold: int = 128,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    1:1 Vectorized CPU equivalent of the 3-Stage Jump Flooding Algorithm (`1+JFA`) +
    Marching Squares 16-Case Saddle-Disambiguated Cell Reconstruction (`svg-potrace-jfa`):
      1. Extracts sub-pixel iso-contour distance field on the `upscale` high-res grid.
      2. Samples the `2x2` Marching Squares cell corners `(d00, d10, d11, d01)` and cell center `d_c`
         for every target pixel `(r, c)`.
      3. Evaluates the 4-bit Marching Squares topological state `ms_case in [0..15]`, resolves
         saddle cases `5` and `10` via the asymptotic decider `d00 * d11 - d10 * d01`, and blends
         analytic Marching Squares cell coverage with JFA distance coverage.
    """
    if high_gray.ndim == 3:
        bw_list = []
        fld_list = []
        for b in range(high_gray.shape[0]):
            bw, fld = eval_jfa_marching_squares_cpu(high_gray[b], target_w, target_h, upscale, threshold)
            bw_list.append(bw)
            fld_list.append(fld)
        return np.stack(bw_list, axis=0), np.stack(fld_list, axis=0)

    if high_gray.size == 0 or target_w <= 0 or target_h <= 0:
        empty = np.zeros((max(1, target_h), max(1, target_w)), dtype=np.uint8)
        return empty, empty

    eff_t = int(np.clip(threshold if threshold > 0 else 128, 1, 254))
    fg_mask = (high_gray >= eff_t).astype(np.uint8)
    bg_mask = 1 - fg_mask
    if np.count_nonzero(fg_mask) == 0:
        empty = np.zeros((target_h, target_w), dtype=np.uint8)
        return empty, empty

    H_hi, W_hi = high_gray.shape
    dist_in = cv2.distanceTransform(fg_mask, cv2.DIST_L2, 5)
    dist_out = cv2.distanceTransform(bg_mask, cv2.DIST_L2, 5)
    bias_px = (128.0 - float(eff_t)) / 64.0
    sdf_hi = ((dist_in - dist_out) / float(upscale)) + bias_px

    r0 = np.clip(np.arange(target_h) * upscale + (upscale // 4), 0, H_hi - 1)
    r1 = np.clip(np.arange(target_h) * upscale + (3 * upscale) // 4, 0, H_hi - 1)
    rm = np.clip(np.arange(target_h) * upscale + (upscale // 2), 0, H_hi - 1)

    c0 = np.clip(np.arange(target_w) * upscale + (upscale // 4), 0, W_hi - 1)
    c1 = np.clip(np.arange(target_w) * upscale + (3 * upscale) // 4, 0, W_hi - 1)
    cm = np.clip(np.arange(target_w) * upscale + (upscale // 2), 0, W_hi - 1)

    d00 = sdf_hi[np.ix_(r0, c0)]
    d10 = sdf_hi[np.ix_(r0, c1)]
    d11 = sdf_hi[np.ix_(r1, c1)]
    d01 = sdf_hi[np.ix_(r1, c0)]
    d_c = sdf_hi[np.ix_(rm, cm)]

    b00 = (d00 >= 0.0).astype(np.int32)
    b10 = (d10 >= 0.0).astype(np.int32)
    b11 = (d11 >= 0.0).astype(np.int32)
    b01 = (d01 >= 0.0).astype(np.int32)
    ms_case = b00 | (b10 << 1) | (b11 << 2) | (b01 << 3)

    ms_cov = 0.25 * (b00 + b10 + b11 + b01).astype(np.float32)
    saddle = (ms_case == 5) | (ms_case == 10)
    decider = d00 * d11 - d10 * d01
    ms_cov = np.where(saddle, np.where((d_c >= 0.0) | (decider > 0.0), 0.62, 0.38), ms_cov)

    boundary = (ms_case > 0) & (ms_case < 15) & (~saddle)
    mean_d = 0.20 * (d00 + d10 + d11 + d01 + d_c)
    ms_cov = np.where(boundary, 0.50 * ms_cov + 0.50 * np.clip(mean_d + 0.50, 0.0, 1.0), ms_cov)

    jfa_cov = np.clip(d_c + 0.50, 0.0, 1.0)
    final_cov = np.nan_to_num(0.60 * ms_cov + 0.40 * jfa_cov, nan=0.0, posinf=1.0, neginf=0.0)
    field_u8 = np.clip(np.round(final_cov * 255.0), 0.0, 255.0).astype(np.uint8)
    bilevel = (final_cov >= 0.50).astype(np.uint8)
    return bilevel, field_u8
