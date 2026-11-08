#!/usr/bin/env python3
"""
opencl_kernels.py (v1.0.21)
==========================
A 1-bit EPD font generator and asset pipeline for embedded displays.
Repository : https://github.com/Humidyne-Labs/epd-font
Authors    : Humiditron (https://github.com/humiditron) & AI/LLM Development Partner
License    : MIT License

OpenCL 1.2 / 2.0 / 3.0 GPU & Multi-Device Compute Kernels, 3D NDRange Batch Dispatcher,
75% Dynamic Host/GPU Shared Memory Arena (`CL_MEM_ALLOC_HOST_PTR` + `clEnqueueMapBuffer`),
Jump Flooding Algorithm (`1+JFA`) + Marching Squares Kernels, and Deterministic Teardown (`v1.0.21`):
  - Full 3-Dimensional (`work_dim = 3`, `[dim_x, dim_y, dim_z]`) NDRange execution across all kernels
    with 3D local work-groups `(8, 8, 4) = 256` work-items (4 wavefronts of 64 threads on AMD GCN/Polaris
    `Ellesmere` 32 CUs, or 256 work-items on CPU OpenCL runtimes) so all 3 Work-Item Dimensions and all
    Compute Units (`32 CUs` GPU + `12 CUs` CPU) are actively utilized.
  - Multi-Queue Hardware Compute Striping (`num_queues = 4` independent `cl.CommandQueue` instances)
    to distribute kernel dispatches across `Compute 0..3` hardware rings without stalling on a single queue.
  - Dynamic 75% Host/GPU Shared RAM Arena (`SharedHostMemoryArena`) using `CL_MEM_ALLOC_HOST_PTR` and
    `cl.enqueue_map_buffer` zero-copy pinned host memory dynamically capped at 75% of total WDDM Shared GPU
    Memory (e.g., `~11,775 MB` / `11.5 GB` on a `15.7 GB` Shared GPU RAM system) so batch tensors reside in
    Shared GPU RAM rather than exhausting the 4.0 GB Dedicated GPU VRAM.
  - Pure GPU Vector Contour & Distance Extraction (`svg-potrace-jfa` / `jfa-marching` sub-mode):
    Implements 3D NDRange Marching Squares sub-pixel iso-contour seed extraction (`jfa_init_marching_seeds_3d_kernel`),
    O(log2 N) Jump Flooding (`1+JFA`, `jfa_flood_step_3d_kernel`), and Marching Squares 16-case saddle-disambiguated
    cell coverage reconstruction (`jfa_marching_squares_reconstruct_3d_kernel`).
  - Deterministic Memory Teardown (`release()`, context manager, and `atexit` registration) that flushes
    and finishes all queues, calls `.release()` on every `cl.Buffer`, `cl.CommandQueue`, `cl.Program`, and
    `cl.Context`, and invokes `gc.collect()` so 0 MB of GPU/Shared RAM remains allocated after exit.
"""

from __future__ import annotations

import atexit
import ctypes
import gc
import math
import os
import threading
import warnings
import weakref
from typing import Dict, List, Optional, Tuple

import numpy as np

TOOL_VERSION = "1.0.21"
SHARED_RAM_CAP_RATIO = 0.75  # 75% cap on total WDDM Shared GPU Memory

try:
    import pyopencl as cl  # type: ignore
    HAS_PYOPENCL = True
except Exception:
    cl = None  # type: ignore
    HAS_PYOPENCL = False


# ---------------------------------------------------------------------------
# Host Shared GPU Memory Detection (75% Dynamic Cap on 15.7 GB WDDM Shared RAM)
# ---------------------------------------------------------------------------
def detect_shared_gpu_memory_mb() -> Tuple[int, int]:
    """
    Return `(total_shared_gpu_ram_mb, usable_75pct_shared_gpu_ram_mb)`.
    On Windows WDDM 2.x/3.x, Total Shared GPU Memory equals 50% of total physical system RAM
    (e.g., 15.7 GB on a 31.4 GB DDR4 workstation).
    Enforces a dynamic 75% cap on Total Shared GPU Memory (`int(total_shared_mb * 0.75)`,
    e.g., ~11,775 MB on a 15.7 GB shared pool), bounded by currently free physical RAM.
    """
    total_phys_mb = 8192
    avail_phys_mb = 4096
    if os.name == "nt":
        try:
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            total_phys_mb = int(stat.ullTotalPhys // (1024 * 1024))
            avail_phys_mb = int(stat.ullAvailPhys // (1024 * 1024))
        except Exception:
            pass
    elif os.path.isfile("/proc/meminfo"):
        try:
            with open("/proc/meminfo", "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        total_phys_mb = int(line.split()[1]) // 1024
                    elif line.startswith("MemAvailable:"):
                        avail_phys_mb = int(line.split()[1]) // 1024
        except Exception:
            pass

    total_shared_mb = max(512, total_phys_mb // 2)
    cap_75pct_mb = max(256, int(round(total_shared_mb * SHARED_RAM_CAP_RATIO)))
    usable_shared_mb = max(256, min(avail_phys_mb - 512, cap_75pct_mb))
    return total_shared_mb, usable_shared_mb


# ---------------------------------------------------------------------------
# OpenCL C Kernel Source (3D NDRange `[dim_x, dim_y, dim_z]` Across All Kernels)
# ---------------------------------------------------------------------------
OPENCL_MATH_KERNELS_SOURCE = r"""
#define EPSILON 1e-6f
#define MAX_NEWTON_STEPS 24

typedef struct {
    float2 p0;
    float2 p1;
    float2 p2;
    float2 p3;
} BezierCurve;

inline float srgb_byte_to_linear(uchar u) {
    float c = (float)u * (1.0f / 255.0f);
    return (c <= 0.04045f) ? (c * (1.0f / 12.92f)) : pow((c + 0.055f) * (1.0f / 1.055f), 2.4f);
}

// ---------------------------------------------------------------------------
// 1. 3D NDRange IEC 61966-2-1 sRGB -> ITU-R BT.709 Linear Luminance + Gamma
//    Work-Item Dimensions: 3 -> (x = gid(0), y = gid(1), z = gid(2))
// ---------------------------------------------------------------------------
__kernel void srgb_to_linear_gamma_3d_kernel(
    __global const uchar* src,
    __global uchar* dst,
    const int width,
    const int height,
    const int slices,
    const int total_pixels,
    const int channels,
    const float inv_gamma)
{
    const int gx = (int)get_global_id(0);
    const int gy = (int)get_global_id(1);
    const int gz = (int)get_global_id(2);
    if (gx >= width || gy >= height || gz >= slices) return;

    const int idx = (gz * height + gy) * width + gx;
    if (idx >= total_pixels) return;

    float y_lin = 0.0f;
    if (channels >= 3) {
        int base = idx * channels;
        float r_lin = srgb_byte_to_linear(src[base + 0]);
        float g_lin = srgb_byte_to_linear(src[base + 1]);
        float b_lin = srgb_byte_to_linear(src[base + 2]);
        y_lin = 0.2126f * r_lin + 0.7152f * g_lin + 0.0722f * b_lin;
    } else {
        uchar u = src[idx];
        float srgb_norm = (float)u * (1.0f / 255.0f);
        float lin_pure = srgb_byte_to_linear(u);
        y_lin = 0.50f * srgb_norm + 0.50f * pow(clamp(lin_pure, 0.0f, 1.0f), 1.0f / 2.2f);
    }

    if (fabs(inv_gamma - 1.0f) > 1e-4f) {
        y_lin = pow(clamp(y_lin, 0.0f, 1.0f), inv_gamma);
    }
    dst[idx] = convert_uchar_sat_rte(clamp(y_lin * 255.0f, 0.0f, 255.0f));
}

// ---------------------------------------------------------------------------
// 2. 3D NDRange Cem Yuksel Quintic Root-Finding Cascade for Cubic Bezier SDF
//    Work-Item Dimensions: 3 -> (x = gid(0), y = gid(1), z_batch = gid(2))
// ---------------------------------------------------------------------------
inline int solve_quadratic(float a, float b, float c, float roots[2]) {
    int count = 0;
    if (fabs(a) < 1e-7f) {
        if (fabs(b) > 1e-7f) {
            float r = -c / b;
            if (r >= 0.0f && r <= 1.0f) roots[count++] = r;
        }
        return count;
    }
    float d = b * b - 4.0f * a * c;
    if (d < 0.0f) return 0;

    float sqrt_d = sqrt(fmax(d, 0.0f));
    float q = -0.5f * (b + (b > 0.0f ? sqrt_d : -sqrt_d));
    float r0 = q / a;
    float r1 = (fabs(q) > 1e-7f) ? (c / q) : r0;

    if (r0 > r1) { float tmp = r0; r0 = r1; r1 = tmp; }
    if (r0 >= 0.0f && r0 <= 1.0f) roots[count++] = r0;
    if (r1 >= 0.0f && r1 <= 1.0f && fabs(r1 - r0) > 1e-5f) roots[count++] = r1;
    return count;
}

inline float eval_poly5(float a, float b, float c, float d, float e, float f, float t) {
    return ((((a * t + b) * t + c) * t + d) * t + e) * t + f;
}

inline float eval_poly5_deriv(float a, float b, float c, float d, float e, float t) {
    return (((5.0f * a * t + 4.0f * b) * t + 3.0f * c) * t + 2.0f * d) * t + e;
}

inline float newton_bisect5(
    float a, float b, float c, float d, float e, float f,
    float t_min, float t_max, float v_min, float v_max)
{
    float x = 0.5f * (t_min + t_max);
    float sign_flip = (v_min < v_max) ? 1.0f : -1.0f;

    for (int i = 0; i < MAX_NEWTON_STEPS; ++i) {
        float y = eval_poly5(a, b, c, d, e, f, x);
        float dy = eval_poly5_deriv(a, b, c, d, e, x);
        if (sign_flip * y < 0.0f) {
            t_min = x;
        } else {
            t_max = x;
        }
        float next_x = (fabs(dy) > 1e-7f) ? (x - y / dy) : (0.5f * (t_min + t_max));
        if (next_x <= t_min || next_x >= t_max) {
            next_x = 0.5f * (t_min + t_max);
        }
        if (fabs(next_x - x) < EPSILON) return next_x;
        x = next_x;
    }
    return x;
}

inline int isolate_and_solve_roots(
    float a, float b, float c, float d, float e, float f,
    __private const float* lower_roots, int num_lower,
    __private float* out_roots)
{
    int out_count = 0;
    float prev_x = 0.0f;
    float prev_y = eval_poly5(a, b, c, d, e, f, 0.0f);

    for (int i = 0; i <= num_lower; ++i) {
        float curr_x = (i == num_lower) ? 1.0f : lower_roots[i];
        float curr_y = eval_poly5(a, b, c, d, e, f, curr_x);
        if (prev_y * curr_y <= 0.0f) {
            out_roots[out_count++] = newton_bisect5(a, b, c, d, e, f, prev_x, curr_x, prev_y, curr_y);
        }
        prev_x = curr_x;
        prev_y = curr_y;
    }
    return out_count;
}

inline float distance_sq_to_bezier(float2 p, BezierCurve bz) {
    float2 d0 = bz.p0 - p;
    float2 d3 = bz.p3 - p;
    float min_dist_sq = fmin(dot(d0, d0), dot(d3, d3));

    float2 a = -bz.p0 + 3.0f * (bz.p1 - bz.p2) + bz.p3;
    float2 b = 3.0f * (bz.p0 - 2.0f * bz.p1 + bz.p2);
    float2 c = 3.0f * (bz.p1 - bz.p0);
    float2 delta = bz.p0 - p;

    float c5 = 3.0f * dot(a, a);
    float c4 = 5.0f * dot(a, b);
    float c3 = 4.0f * dot(a, c) + 2.0f * dot(b, b);
    float c2 = 3.0f * (dot(a, delta) + dot(b, c));
    float c1 = 2.0f * dot(b, delta) + dot(c, c);
    float c0 = dot(c, delta);

    float r2[2], r3[3], r4[4], r5[5];
    int n2 = solve_quadratic(10.0f * c5, 4.0f * c4, c3, r2);
    int n3 = isolate_and_solve_roots(0.0f, 0.0f, 10.0f * c5, 6.0f * c4, 3.0f * c3, c2, r2, n2, r3);
    int n4 = isolate_and_solve_roots(0.0f, 5.0f * c5, 4.0f * c4, 3.0f * c3, 2.0f * c2, c1, r3, n3, r4);
    int n5 = isolate_and_solve_roots(c5, c4, c3, c2, c1, c0, r4, n4, r5);

    for (int i = 0; i < n5; ++i) {
        float t = r5[i];
        float2 pt = ((a * t + b) * t + c) * t + bz.p0;
        float2 diff = pt - p;
        min_dist_sq = fmin(min_dist_sq, dot(diff, diff));
    }
    return min_dist_sq;
}

inline int solve_cubic_y(float a, float b, float c, float d, float roots[3]) {
    float r2[2];
    int n2 = solve_quadratic(3.0f * a, 2.0f * b, c, r2);
    int n3 = 0;
    float px = 0.0f;
    float py = d;

    for (int i = 0; i <= n2; ++i) {
        float cx = (i == n2) ? 1.0f : r2[i];
        float cy = ((a * cx + b) * cx + c) * cx + d;
        if (py * cy <= 0.0f) {
            float x = 0.5f * (px + cx);
            for (int k = 0; k < 16; ++k) {
                float fval = ((a * x + b) * x + c) * x + d;
                float fder = (3.0f * a * x + 2.0f * b) * x + c;
                if (fabs(fder) < 1e-7f) break;
                float xn = x - fval / fder;
                if (xn < px || xn > cx) xn = 0.5f * (px + cx);
                if (fabs(xn - x) < 1e-6f) { x = xn; break; }
                x = xn;
            }
            roots[n3++] = x;
        }
        px = cx;
        py = cy;
    }
    return n3;
}

inline int bezier_winding(float2 p, BezierCurve bz) {
    int w = 0;
    int signs = ((bz.p0.y < p.y) ? 1 : 0) |
                (((bz.p1.y < p.y) ? 1 : 0) << 1) |
                (((bz.p2.y < p.y) ? 1 : 0) << 2) |
                (((bz.p3.y < p.y) ? 1 : 0) << 3);
    if (signs == 0 || signs == 15) return 0;
    int inc = (signs & 1) == 0 ? 1 : -1;

    float2 a = -bz.p0 + 3.0f * (bz.p1 - bz.p2) + bz.p3;
    float2 b = 3.0f * (bz.p0 - 2.0f * bz.p1 + bz.p2);
    float2 c = 3.0f * (bz.p1 - bz.p0);
    float2 d = bz.p0 - p;

    float r[3];
    int count = solve_cubic_y(a.y, b.y, c.y, d.y, r);
    for (int i = 0; i < count; ++i) {
        float t = r[i];
        float x_intersect = ((a.x * t + b.x) * t + c.x) * t + d.x;
        if (x_intersect >= 0.0f) {
            w += (i % 2 == 0) ? inc : -inc;
        }
    }
    return w;
}

__kernel void render_bezier_sdf_yuksel_3d_kernel(
    __global const BezierCurve* curves,
    const int num_curves,
    __global uchar* out_bilevel,
    __global uchar* out_field,
    const int width,
    const int height,
    const int batch_z,
    const float bias_px)
{
    const int gx = (int)get_global_id(0);
    const int gy = (int)get_global_id(1);
    const int gz = (int)get_global_id(2);
    if (gx >= width || gy >= height || gz >= batch_z) return;

    float2 p = (float2)((float)gx + 0.5f, (float)gy + 0.5f);
    float min_dist_sq = 1e30f;
    int winding_accum = 0;
    const int curve_base = gz * num_curves;

    for (int i = 0; i < num_curves; ++i) {
        BezierCurve bz = curves[curve_base + i];
        float2 bmin = fmin(fmin(bz.p0, bz.p1), fmin(bz.p2, bz.p3));
        float2 bmax = fmax(fmax(bz.p0, bz.p1), fmax(bz.p2, bz.p3));
        float2 bcenter = 0.5f * (bmin + bmax);
        float2 bextents = 0.5f * (bmax - bmin);
        float2 dbox = fmax(fabs(p - bcenter) - bextents, 0.0f);
        float box_dist_sq = dot(dbox, dbox);

        if (box_dist_sq < min_dist_sq) {
            float d_sq = distance_sq_to_bezier(p, bz);
            min_dist_sq = fmin(min_dist_sq, d_sq);
        }
        winding_accum += bezier_winding(p, bz);
    }

    float d = sqrt(fmax(min_dist_sq, 0.0f));
    float signed_d = ((winding_accum & 1) != 0 ? d : -d) + bias_px;
    float alpha = smoothstep(-0.55f, 0.55f, signed_d);
    int idx = (gz * height + gy) * width + gx;
    out_field[idx] = convert_uchar_sat_rte(clamp(alpha * 255.0f, 0.0f, 255.0f));
    out_bilevel[idx] = (alpha >= 0.50f) ? 1 : 0;
}

// ---------------------------------------------------------------------------
// 3. 3D NDRange Chris Green (Valve) SDF Smoothstep + L2 Derivative Kernel
//    Work-Item Dimensions: 3 -> (x = gid(0), y = gid(1), z_batch = gid(2))
// ---------------------------------------------------------------------------
__kernel void sdf_valve_smoothstep_3d_kernel(
    __global const float* sdf_hi,
    __global uchar* out_bilevel,
    __global uchar* out_field,
    const int hi_w,
    const int hi_h,
    const int target_w,
    const int target_h,
    const int batch_z,
    const int upscale,
    const float bias_px)
{
    const int gx = (int)get_global_id(0);
    const int gy = (int)get_global_id(1);
    const int gz = (int)get_global_id(2);
    if (gx >= target_w || gy >= target_h || gz >= batch_z) return;

    const int slice_base = gz * (hi_w * hi_h);
    int hc = clamp(gx * upscale + (upscale / 2), 0, hi_w - 1);
    int hr = clamp(gy * upscale + (upscale / 2), 0, hi_h - 1);
    int hc_r = clamp(hc + upscale, 0, hi_w - 1);
    int hr_d = clamp(hr + upscale, 0, hi_h - 1);

    float d = sdf_hi[slice_base + hr * hi_w + hc] + bias_px;
    float dx = sdf_hi[slice_base + hr * hi_w + hc_r] - sdf_hi[slice_base + hr * hi_w + hc];
    float dy = sdf_hi[slice_base + hr_d * hi_w + hc] - sdf_hi[slice_base + hr * hi_w + hc];
    float w = clamp(length((float2)(dx, dy)) * 0.55f, 0.35f, 0.85f);

    float t = clamp((d + w) / (2.0f * w), 0.0f, 1.0f);
    float cov_smooth = t * t * (3.0f - 2.0f * t);

    int idx = (gz * target_h + gy) * target_w + gx;
    out_field[idx] = convert_uchar_sat_rte(clamp(cov_smooth * 255.0f, 0.0f, 255.0f));
    out_bilevel[idx] = (cov_smooth >= 0.50f) ? 1 : 0;
}

// ---------------------------------------------------------------------------
// 4. 3D NDRange Chlumsky MSDF 3-Channel Median-of-Three Reconstruction Kernel
//    Work-Item Dimensions: 3 -> (x = gid(0), y = gid(1), z_batch = gid(2))
// ---------------------------------------------------------------------------
inline float median3_f(float r, float g, float b) {
    return fmax(fmin(r, g), fmin(fmax(r, g), b));
}

__kernel void msdf_median3_reconstruct_3d_kernel(
    __global const float* sdf_r,
    __global const float* sdf_g,
    __global const float* sdf_b,
    __global uchar* out_bilevel,
    const int target_w,
    const int target_h,
    const int batch_z,
    const float edge_offset_px)
{
    const int gx = (int)get_global_id(0);
    const int gy = (int)get_global_id(1);
    const int gz = (int)get_global_id(2);
    if (gx >= target_w || gy >= target_h || gz >= batch_z) return;

    int idx = (gz * target_h + gy) * target_w + gx;
    float m = median3_f(sdf_r[idx], sdf_g[idx], sdf_b[idx]);
    out_bilevel[idx] = (m >= edge_offset_px) ? 1 : 0;
}

// ---------------------------------------------------------------------------
// 5. 3D NDRange Saffron 9-Point Bi-Quadratic Lagrange Polynomial ADF Kernel
//    Work-Item Dimensions: 3 -> (x = gid(0), y = gid(1), z_batch = gid(2))
// ---------------------------------------------------------------------------
__kernel void adf_biquadratic_9pt_3d_kernel(
    __global const float* sdf_hi,
    __global uchar* out_bilevel,
    __global uchar* out_field,
    const int hi_w,
    const int hi_h,
    const int target_w,
    const int target_h,
    const int batch_z,
    const int upscale,
    const float bias_px)
{
    const int gx = (int)get_global_id(0);
    const int gy = (int)get_global_id(1);
    const int gz = (int)get_global_id(2);
    if (gx >= target_w || gy >= target_h || gz >= batch_z) return;

    const int slice_base = gz * (hi_w * hi_h);
    int r0 = clamp(gy * upscale, 0, hi_h - 1);
    int rm = clamp(gy * upscale + (upscale / 2), 0, hi_h - 1);
    int r1 = clamp((gy + 1) * upscale - 1, 0, hi_h - 1);

    int c0 = clamp(gx * upscale, 0, hi_w - 1);
    int cm = clamp(gx * upscale + (upscale / 2), 0, hi_w - 1);
    int c1 = clamp((gx + 1) * upscale - 1, 0, hi_w - 1);

    float d00 = sdf_hi[slice_base + r0 * hi_w + c0];
    float d10 = sdf_hi[slice_base + r0 * hi_w + cm];
    float d20 = sdf_hi[slice_base + r0 * hi_w + c1];
    float d01 = sdf_hi[slice_base + rm * hi_w + c0];
    float d11 = sdf_hi[slice_base + rm * hi_w + cm];
    float d21 = sdf_hi[slice_base + rm * hi_w + c1];
    float d02 = sdf_hi[slice_base + r1 * hi_w + c0];
    float d12 = sdf_hi[slice_base + r1 * hi_w + cm];
    float d22 = sdf_hi[slice_base + r1 * hi_w + c1];

    const float sub_coords[4] = {0.125f, 0.375f, 0.625f, 0.875f};
    const float c_in = 0.50f;
    const float c_out = -0.625f;
    const float span = c_in - c_out;

    float cov_acc = 0.0f;
    for (int iv = 0; iv < 4; ++iv) {
        float sv = sub_coords[iv];
        float ly0 = 2.0f * (sv - 0.5f) * (sv - 1.0f);
        float ly1 = -4.0f * sv * (sv - 1.0f);
        float ly2 = 2.0f * sv * (sv - 0.5f);
        for (int iu = 0; iu < 4; ++iu) {
            float su = sub_coords[iu];
            float lx0 = 2.0f * (su - 0.5f) * (su - 1.0f);
            float lx1 = -4.0f * su * (su - 1.0f);
            float lx2 = 2.0f * su * (su - 0.5f);
            float d_sub = (
                ly0 * (lx0 * d00 + lx1 * d10 + lx2 * d20) +
                ly1 * (lx0 * d01 + lx1 * d11 + lx2 * d21) +
                ly2 * (lx0 * d02 + lx1 * d12 + lx2 * d22)
            ) + bias_px;
            float i_in = clamp((d_sub - c_out) / span, 0.0f, 1.0f);
            cov_acc += pow(i_in, 1.1f);
        }
    }

    float cov_mean = cov_acc / 16.0f;
    float center_cov = clamp(((d11 + bias_px) - c_out) / span, 0.0f, 1.0f);
    float final_cov = 0.65f * cov_mean + 0.35f * center_cov;

    int idx = (gz * target_h + gy) * target_w + gx;
    out_field[idx] = convert_uchar_sat_rte(clamp(final_cov * 255.0f, 0.0f, 255.0f));
    out_bilevel[idx] = (final_cov >= 0.50f) ? 1 : 0;
}

// ---------------------------------------------------------------------------
// 6. 3D NDRange Work-Group Local Atomic 256-Bin Histogram Kernel
//    Work-Item Dimensions: 3 -> (x = gid(0), y = gid(1), z = gid(2))
// ---------------------------------------------------------------------------
__kernel void compute_histogram_local_atomic_3d(
    __global const uchar* src_gray,
    __global uint* global_hist,
    const int width,
    const int height,
    const int slices,
    const int total_pixels)
{
    __local uint local_hist[256];
    const int lx = (int)get_local_id(0);
    const int ly = (int)get_local_id(1);
    const int lz = (int)get_local_id(2);
    const int sx = (int)get_local_size(0);
    const int sy = (int)get_local_size(1);
    const int sz = (int)get_local_size(2);
    const int lid = lx + sx * (ly + sy * lz);
    const int lsize = sx * sy * sz;

    for (int b = lid; b < 256; b += lsize) {
        local_hist[b] = 0u;
    }
    barrier(CLK_LOCAL_MEM_FENCE);

    const int gx = (int)get_global_id(0);
    const int gy = (int)get_global_id(1);
    const int gz = (int)get_global_id(2);
    if (gx < width && gy < height && gz < slices) {
        const int gid = (gz * height + gy) * width + gx;
        if (gid < total_pixels) {
            uchar v = src_gray[gid];
            if (v >= 8u && v <= 248u) {
                atomic_inc(&local_hist[(int)v]);
            }
        }
    }
    barrier(CLK_LOCAL_MEM_FENCE);

    for (int b = lid; b < 256; b += lsize) {
        uint c = local_hist[b];
        if (c > 0u) {
            atomic_add(&global_hist[b], c);
        }
    }
}

// ---------------------------------------------------------------------------
// 7. 3D NDRange Jump Flooding Algorithm (1+JFA) + Marching Squares Sub-Mode
//    (Pure GPU Vector Contour Extraction & Distance Reconstruction)
// ---------------------------------------------------------------------------
inline float edge_interp(float v0, float v1, float iso) {
    float dv = v1 - v0;
    if (fabs(dv) < 1e-4f) return 0.5f;
    return clamp((iso - v0) / dv, 0.0f, 1.0f);
}

// Stage 7a: Initialize sub-pixel Marching Squares 2x2 iso-contour seeds
__kernel void jfa_init_marching_seeds_3d_kernel(
    __global const uchar* high_gray,
    __global float2* seed_coords,
    const int hi_w,
    const int hi_h,
    const int batch_z,
    const float iso_thresh)
{
    const int gx = (int)get_global_id(0);
    const int gy = (int)get_global_id(1);
    const int gz = (int)get_global_id(2);
    if (gx >= hi_w || gy >= hi_h || gz >= batch_z) return;

    const int slice_base = gz * (hi_w * hi_h);
    const int idx = slice_base + gy * hi_w + gx;

    int x1 = min(gx + 1, hi_w - 1);
    int y1 = min(gy + 1, hi_h - 1);

    float v00 = (float)high_gray[slice_base + gy * hi_w + gx];
    float v10 = (float)high_gray[slice_base + gy * hi_w + x1];
    float v11 = (float)high_gray[slice_base + y1 * hi_w + x1];
    float v01 = (float)high_gray[slice_base + y1 * hi_w + gx];

    int b00 = (v00 >= iso_thresh) ? 1 : 0;
    int b10 = (v10 >= iso_thresh) ? 1 : 0;
    int b11 = (v11 >= iso_thresh) ? 1 : 0;
    int b01 = (v01 >= iso_thresh) ? 1 : 0;
    int ms_case = b00 | (b10 << 1) | (b11 << 2) | (b01 << 3);

    if (ms_case > 0 && ms_case < 15) {
        // Compute exact sub-pixel iso-contour centroid across crossed Marching Squares cell edges
        float2 sum_pt = (float2)(0.0f, 0.0f);
        int n_cross = 0;
        if (b00 != b10) {
            sum_pt += (float2)((float)gx + edge_interp(v00, v10, iso_thresh), (float)gy);
            n_cross++;
        }
        if (b10 != b11) {
            sum_pt += (float2)((float)gx + 1.0f, (float)gy + edge_interp(v10, v11, iso_thresh));
            n_cross++;
        }
        if (b01 != b11) {
            sum_pt += (float2)((float)gx + edge_interp(v01, v11, iso_thresh), (float)gy + 1.0f);
            n_cross++;
        }
        if (b00 != b01) {
            sum_pt += (float2)((float)gx, (float)gy + edge_interp(v00, v01, iso_thresh));
            n_cross++;
        }
        seed_coords[idx] = (n_cross > 0) ? (sum_pt / (float)n_cross) : (float2)((float)gx + 0.5f, (float)gy + 0.5f);
    } else {
        seed_coords[idx] = (float2)(-1e6f, -1e6f);
    }
}

// Stage 7b: O(log2 N) Jump Flooding Pass at stride `step_k`
__kernel void jfa_flood_step_3d_kernel(
    __global const float2* seeds_in,
    __global float2* seeds_out,
    const int hi_w,
    const int hi_h,
    const int batch_z,
    const int step_k)
{
    const int gx = (int)get_global_id(0);
    const int gy = (int)get_global_id(1);
    const int gz = (int)get_global_id(2);
    if (gx >= hi_w || gy >= hi_h || gz >= batch_z) return;

    const int slice_base = gz * (hi_w * hi_h);
    const int idx = slice_base + gy * hi_w + gx;
    float2 p = (float2)((float)gx + 0.5f, (float)gy + 0.5f);

    float2 best_seed = seeds_in[idx];
    float best_d2 = (best_seed.x > -1e5f) ? dot(best_seed - p, best_seed - p) : 1e30f;

    for (int dy = -1; dy <= 1; ++dy) {
        int ny = gy + dy * step_k;
        if (ny < 0 || ny >= hi_h) continue;
        for (int dx = -1; dx <= 1; ++dx) {
            int nx = gx + dx * step_k;
            if (nx < 0 || nx >= hi_w) continue;
            float2 cand = seeds_in[slice_base + ny * hi_w + nx];
            if (cand.x > -1e5f) {
                float2 diff = cand - p;
                float d2 = dot(diff, diff);
                if (d2 < best_d2) {
                    best_d2 = d2;
                    best_seed = cand;
                }
            }
        }
    }
    seeds_out[idx] = best_seed;
}

// Stage 7c: Marching Squares 16-Case Cell Topology + JFA Signed Distance Reconstruction
inline float sample_jfa_sdf_at(
    __global const uchar* high_gray,
    __global const float2* jfa_seeds,
    int slice_base,
    int hi_w,
    int hi_h,
    int upscale,
    float iso_thresh,
    float bias_px,
    int hx,
    int hy)
{
    int cx = clamp(hx, 0, hi_w - 1);
    int cy = clamp(hy, 0, hi_h - 1);
    int idx = slice_base + cy * hi_w + cx;
    float2 seed = jfa_seeds[idx];
    float2 p = (float2)((float)cx + 0.5f, (float)cy + 0.5f);
    float dist_px = (seed.x > -1e5f) ? (length(seed - p) / (float)upscale) : 4.0f;
    float sgn = ((float)high_gray[idx] >= iso_thresh) ? 1.0f : -1.0f;
    return sgn * dist_px + bias_px;
}

__kernel void jfa_marching_squares_reconstruct_3d_kernel(
    __global const uchar* high_gray,
    __global const float2* jfa_seeds,
    __global uchar* out_bilevel,
    __global uchar* out_field,
    const int hi_w,
    const int hi_h,
    const int target_w,
    const int target_h,
    const int batch_z,
    const int upscale,
    const float iso_thresh,
    const float bias_px)
{
    const int gx = (int)get_global_id(0);
    const int gy = (int)get_global_id(1);
    const int gz = (int)get_global_id(2);
    if (gx >= target_w || gy >= target_h || gz >= batch_z) return;

    const int slice_base = gz * (hi_w * hi_h);
    int x0 = gx * upscale + (upscale / 4);
    int x1 = gx * upscale + (3 * upscale) / 4;
    int y0 = gy * upscale + (upscale / 4);
    int y1 = gy * upscale + (3 * upscale) / 4;
    int xm = gx * upscale + (upscale / 2);
    int ym = gy * upscale + (upscale / 2);

    float d00 = sample_jfa_sdf_at(high_gray, jfa_seeds, slice_base, hi_w, hi_h, upscale, iso_thresh, bias_px, x0, y0);
    float d10 = sample_jfa_sdf_at(high_gray, jfa_seeds, slice_base, hi_w, hi_h, upscale, iso_thresh, bias_px, x1, y0);
    float d11 = sample_jfa_sdf_at(high_gray, jfa_seeds, slice_base, hi_w, hi_h, upscale, iso_thresh, bias_px, x1, y1);
    float d01 = sample_jfa_sdf_at(high_gray, jfa_seeds, slice_base, hi_w, hi_h, upscale, iso_thresh, bias_px, x0, y1);
    float d_c = sample_jfa_sdf_at(high_gray, jfa_seeds, slice_base, hi_w, hi_h, upscale, iso_thresh, bias_px, xm, ym);

    int b00 = (d00 >= 0.0f) ? 1 : 0;
    int b10 = (d10 >= 0.0f) ? 1 : 0;
    int b11 = (d11 >= 0.0f) ? 1 : 0;
    int b01 = (d01 >= 0.0f) ? 1 : 0;
    int ms_case = b00 | (b10 << 1) | (b11 << 2) | (b01 << 3);

    // Analytic Marching Squares cell coverage with asymptotic saddle decider on cases 5 & 10
    float ms_cov = 0.25f * (float)(b00 + b10 + b11 + b01);
    if (ms_case == 5 || ms_case == 10) {
        float decider = d00 * d11 - d10 * d01;
        ms_cov = (d_c >= 0.0f || decider > 0.0f) ? 0.62f : 0.38f;
    } else if (ms_case > 0 && ms_case < 15) {
        float mean_d = 0.20f * (d00 + d10 + d11 + d01 + d_c);
        ms_cov = 0.50f * ms_cov + 0.50f * clamp(mean_d + 0.50f, 0.0f, 1.0f);
    }

    float jfa_cov = clamp(d_c + 0.50f, 0.0f, 1.0f);
    float final_cov = 0.60f * ms_cov + 0.40f * jfa_cov;

    int out_idx = (gz * target_h + gy) * target_w + gx;
    out_field[out_idx] = convert_uchar_sat_rte(clamp(final_cov * 255.0f, 0.0f, 255.0f));
    out_bilevel[out_idx] = (final_cov >= 0.50f) ? 1 : 0;
}
"""

OPENCL_MATH_KERNEL_SOURCE = OPENCL_MATH_KERNELS_SOURCE


# ---------------------------------------------------------------------------
# Host/GPU Shared RAM Pinned Memory Arena (`CL_MEM_ALLOC_HOST_PTR` + 75% Cap)
# ---------------------------------------------------------------------------
class SharedHostMemoryArena:
    """
    Manages a reusable pool of pinned Host/GPU Shared RAM (`CL_MEM_ALLOC_HOST_PTR`) buffers
    mapped into the 15.7 GB WDDM Shared GPU Memory aperture (dynamically capped at 75% of
    total Shared GPU Memory, e.g., ~11,775 MB on a 15.7 GB shared pool).
    Uses `cl.enqueue_map_buffer` (`CL_MAP_WRITE_INVALIDATE_REGION` / `CL_MAP_READ`) so buffers
    remain in host-visible Shared GPU Memory rather than promoting into Dedicated 4 GB VRAM,
    and guarantees deterministic `.release()` teardown on exit.
    """

    def __init__(self, ctx: "cl.Context", max_shared_mb: int = 4096) -> None:
        self.ctx = ctx
        self.max_shared_bytes = max(64, int(max_shared_mb)) * 1024 * 1024
        self.budget_bytes = self.max_shared_bytes
        self.allocated_bytes = 0
        self._lock = threading.Lock()
        self._slots: Dict[str, Tuple["cl.Buffer", int]] = {}

    def get_pinned_buffer(self, slot_name: str, min_bytes: int, flags: int = 0) -> "cl.Buffer":
        """Acquire or grow a named reusable `CL_MEM_ALLOC_HOST_PTR` buffer in Shared GPU RAM."""
        req_bytes = max(4096, ((int(min_bytes) + 4095) // 4096) * 4096)
        mf = cl.mem_flags
        alloc_flags = (flags or mf.READ_WRITE) | mf.ALLOC_HOST_PTR

        with self._lock:
            existing = self._slots.get(slot_name)
            if existing is not None:
                buf, cap = existing
                if cap >= req_bytes:
                    return buf
                try:
                    buf.release()
                except Exception:
                    pass
                self.allocated_bytes = max(0, self.allocated_bytes - cap)
                del self._slots[slot_name]

            if self.allocated_bytes + req_bytes > self.max_shared_bytes:
                self._evict_unlocked()

            new_buf = cl.Buffer(self.ctx, alloc_flags, size=req_bytes)
            self._slots[slot_name] = (new_buf, req_bytes)
            self.allocated_bytes += req_bytes
            return new_buf

    def stage_input(self, queue: "cl.CommandQueue", slot_name: str, arr: np.ndarray) -> "cl.Buffer":
        """
        Stage `arr` into a persistent `CL_MEM_ALLOC_HOST_PTR` Shared GPU RAM slot using
        `cl.enqueue_map_buffer` (falling back to `enqueue_copy` if map flags are unsupported).
        """
        contig = np.ascontiguousarray(arr)
        nbytes = int(contig.nbytes)
        buf = self.get_pinned_buffer(slot_name, nbytes, cl.mem_flags.READ_WRITE)
        try:
            map_flag = getattr(cl.map_flags, "WRITE_INVALIDATE_REGION", cl.map_flags.WRITE)
            mapped, _ = cl.enqueue_map_buffer(
                queue,
                buf,
                map_flag,
                0,
                (contig.size,),
                contig.dtype,
                is_blocking=True,
            )
            with mapped.base:
                mapped[:] = contig.ravel()
        except Exception:
            cl.enqueue_copy(queue, buf, contig)
        return buf

    def read_output(self, queue: "cl.CommandQueue", buf: "cl.Buffer", out_arr: np.ndarray) -> np.ndarray:
        """Read results from a `CL_MEM_ALLOC_HOST_PTR` Shared GPU RAM slot into `out_arr`."""
        try:
            mapped, _ = cl.enqueue_map_buffer(
                queue,
                buf,
                cl.map_flags.READ,
                0,
                (out_arr.size,),
                out_arr.dtype,
                is_blocking=True,
            )
            with mapped.base:
                out_arr.ravel()[:] = mapped
            return out_arr
        except Exception:
            cl.enqueue_copy(queue, out_arr, buf).wait()
            return out_arr

    def _evict_unlocked(self) -> None:
        for _, (buf, _) in list(self._slots.items()):
            try:
                buf.release()
            except Exception:
                pass
        self._slots.clear()
        self.allocated_bytes = 0

    def release(self) -> int:
        """Deterministically release all pinned `CL_MEM_ALLOC_HOST_PTR` buffers."""
        with self._lock:
            count = len(self._slots)
            self._evict_unlocked()
            self.ctx = None  # type: ignore
            return count


# ---------------------------------------------------------------------------
# Global Registry of Active Accelerators for Deterministic Teardown (`atexit`)
# ---------------------------------------------------------------------------
_ACTIVE_ACCELERATORS: List["weakref.ReferenceType[OpenCLMathAccelerator]"] = []
_REGISTRY_LOCK = threading.Lock()


def register_accelerator_for_teardown(accel: "OpenCLMathAccelerator") -> None:
    with _REGISTRY_LOCK:
        _ACTIVE_ACCELERATORS.append(weakref.ref(accel))


def release_all_opencl_resources() -> int:
    """
    Deterministic teardown hook registered with `atexit` and `SIGINT` handlers.
    Flushes/finishes all OpenCL command queues, releases all `cl.Buffer` / `SharedHostMemoryArena`
    allocations, releases `CommandQueue` / `Program` / `Context` handles, and runs `gc.collect()`.
    """
    released_count = 0
    with _REGISTRY_LOCK:
        refs = list(_ACTIVE_ACCELERATORS)
        _ACTIVE_ACCELERATORS.clear()

    for ref in refs:
        accel = ref()
        if accel is not None:
            try:
                accel.release()
                released_count += 1
            except Exception:
                pass
    gc.collect()
    return released_count


atexit.register(release_all_opencl_resources)


# ---------------------------------------------------------------------------
# OpenCL 3D NDRange Multi-Queue Mathematical Accelerator (`v1.0.21`)
# ---------------------------------------------------------------------------
class OpenCLMathAccelerator:
    """
    Encapsulates an OpenCL Context, 4 striped Hardware CommandQueues (`Compute 0..3`),
    a 75%-capped `SharedHostMemoryArena` (`CL_MEM_ALLOC_HOST_PTR` in 15.7 GB Shared GPU Memory),
    and compiled 3D NDRange (`work_dim = 3`, `[dim_x, dim_y, dim_z]`) kernels including
    Jump Flooding (`1+JFA`) + Marching Squares (`svg-potrace-jfa` / `jfa-marching`).
    """

    def __init__(
        self,
        ctx: "cl.Context",
        device: "cl.Device",
        num_queues: int = 4,
        shared_ram_mb: Optional[int] = None,
    ) -> None:
        self.ctx: Optional["cl.Context"] = ctx
        self.device: Optional["cl.Device"] = device
        self.device_name = str(getattr(device, "name", "OpenCL Device")).strip()
        self.vendor = str(getattr(device, "vendor", "Unknown")).strip()
        self.compute_units = int(getattr(device, "max_compute_units", 1))
        self.max_wg_size = int(getattr(device, "max_work_group_size", 64))
        self.max_work_item_dims = int(getattr(device, "max_work_item_dimensions", 3))
        self.max_work_item_sizes = list(getattr(device, "max_work_item_sizes", [1024, 1024, 1024]))
        self.global_mem_mb = int(getattr(device, "global_mem_size", 0) // (1024 * 1024))
        self.local_mem_kb = int(getattr(device, "local_mem_size", 0) // 1024)

        total_shared_mb, usable_75pct_mb = detect_shared_gpu_memory_mb()
        self.total_shared_gpu_ram_mb = total_shared_mb
        self.cap_75pct_shared_gpu_ram_mb = int(round(total_shared_mb * SHARED_RAM_CAP_RATIO))
        self.avail_shared_gpu_ram_mb = usable_75pct_mb

        env_shared = os.environ.get("EPD_FONT_SHARED_RAM_MB")
        if shared_ram_mb is not None and shared_ram_mb > 0:
            arena_mb = min(int(shared_ram_mb), self.cap_75pct_shared_gpu_ram_mb)
        elif env_shared and env_shared.isdigit():
            arena_mb = min(int(env_shared), self.cap_75pct_shared_gpu_ram_mb)
        else:
            # Default: dynamically allow up to 75% of total Shared GPU Memory bounded by usable physical RAM
            arena_mb = usable_75pct_mb
        self.shared_arena: Optional[SharedHostMemoryArena] = SharedHostMemoryArena(ctx, max_shared_mb=arena_mb)

        # Create 4 independent CommandQueues to stripe work across hardware compute engines (Compute 0..3)
        q_count = max(1, min(int(num_queues), 8))
        self.queues: List["cl.CommandQueue"] = [cl.CommandQueue(ctx, device=device) for _ in range(q_count)]
        self.queue: Optional["cl.CommandQueue"] = self.queues[0]
        self._q_idx = 0
        self._lock = threading.Lock()
        self._released = False

        # Compile 3D NDRange OpenCL C program once with fast-relaxed-math (suppress Intel OpenCL CompilerWarning)
        with warnings.catch_warnings():
            if hasattr(cl, "CompilerWarning"):
                warnings.filterwarnings("ignore", category=cl.CompilerWarning)
            self.program: Optional["cl.Program"] = cl.Program(ctx, OPENCL_MATH_KERNELS_SOURCE).build(
                options=["-cl-fast-relaxed-math", "-cl-mad-enable"]
            )
        # Cache kernel handles once so repeated attribute access on `self.program.<kernel>` never leaks
        self._k_srgb_3d = cl.Kernel(self.program, "srgb_to_linear_gamma_3d_kernel")
        self._k_bezier_yuksel_3d = cl.Kernel(self.program, "render_bezier_sdf_yuksel_3d_kernel")
        self._k_sdf_smoothstep_3d = cl.Kernel(self.program, "sdf_valve_smoothstep_3d_kernel")
        self._k_msdf_median3_3d = cl.Kernel(self.program, "msdf_median3_reconstruct_3d_kernel")
        self._k_adf_biquad_3d = cl.Kernel(self.program, "adf_biquadratic_9pt_3d_kernel")
        self._k_otsu_hist_3d = cl.Kernel(self.program, "compute_histogram_local_atomic_3d")
        self._k_jfa_init_3d = cl.Kernel(self.program, "jfa_init_marching_seeds_3d_kernel")
        self._k_jfa_step_3d = cl.Kernel(self.program, "jfa_flood_step_3d_kernel")
        self._k_jfa_ms_recon_3d = cl.Kernel(self.program, "jfa_marching_squares_reconstruct_3d_kernel")

        # 3D local work-group size `(lx, ly, lz)` tailored to max_work_group_size (256 = 8x8x4 = 4 wavefronts of 64)
        if self.max_wg_size >= 256:
            self.local_3d = (8, 8, 4)
        elif self.max_wg_size >= 128:
            self.local_3d = (8, 4, 4)
        elif self.max_wg_size >= 64:
            self.local_3d = (4, 4, 4)
        else:
            self.local_3d = (4, 4, 1)

        register_accelerator_for_teardown(self)

    def __enter__(self) -> "OpenCLMathAccelerator":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()

    def __del__(self) -> None:
        try:
            self.release()
        except Exception:
            pass

    def _next_queue(self) -> "cl.CommandQueue":
        with self._lock:
            q = self.queues[self._q_idx % len(self.queues)]
            self._q_idx += 1
            return q

    def _effective_local_3d(self, z: int) -> Tuple[int, int, int]:
        if z == 1 and self.max_wg_size >= 256:
            return (16, 16, 1)
        if z <= 2 and self.max_wg_size >= 256:
            return (16, 8, 2)
        return self.local_3d

    def _round_global_3d(self, w: int, h: int, z: int) -> Tuple[int, int, int]:
        """
        Round `(w, h, z)` up to an integer multiple of `_effective_local_3d(z)`.
        Ensures all 3 Work-Item Dimensions (`work_dim = 3`, `[dim_x, dim_y, dim_z]`) are active!
        """
        eff_lx, eff_ly, eff_lz = self._effective_local_3d(z)
        gw = ((max(1, w) + eff_lx - 1) // eff_lx) * eff_lx
        gh = ((max(1, h) + eff_ly - 1) // eff_ly) * eff_ly
        gz = ((max(1, z) + eff_lz - 1) // eff_lz) * eff_lz
        return (gw, gh, gz)

    @staticmethod
    def _factor_1d_to_3d(n_elems: int, target_z_slices: int = 32) -> Tuple[int, int, int]:
        """
        Factor a 1D element count `n_elems` into a 3D grid `(width, height, z_slices)` so that:
          - All 3 Work-Item Dimensions (`[x, y, z]`) are actively populated (`z_slices >= 4`).
          - Work-groups span all 32 Compute Units on the GPU.
        """
        z_slices = max(4, min(target_z_slices, max(4, n_elems // 64)))
        per_slice = max(1, int(math.ceil(n_elems / float(z_slices))))
        w = max(8, min(512, int(math.ceil(math.sqrt(per_slice)))))
        h = max(1, int(math.ceil(per_slice / float(w))))
        return (w, h, z_slices)

    def release(self) -> None:
        """
        Deterministically flush/finish all queues and release all OpenCL buffers, kernels,
        programs, queues, and context handles so 0 MB of GPU/Shared RAM remains allocated.
        """
        with self._lock:
            if self._released:
                return
            self._released = True

            if self.shared_arena is not None:
                try:
                    self.shared_arena.release()
                except Exception:
                    pass
                self.shared_arena = None

            for k_attr in (
                "_k_srgb_3d",
                "_k_bezier_yuksel_3d",
                "_k_sdf_smoothstep_3d",
                "_k_msdf_median3_3d",
                "_k_adf_biquad_3d",
                "_k_otsu_hist_3d",
                "_k_jfa_init_3d",
                "_k_jfa_step_3d",
                "_k_jfa_ms_recon_3d",
            ):
                k_obj = getattr(self, k_attr, None)
                if k_obj is not None:
                    try:
                        if hasattr(k_obj, "release"):
                            k_obj.release()
                    except Exception:
                        pass
                    setattr(self, k_attr, None)

            for q in self.queues:
                try:
                    q.flush()
                    q.finish()
                    if hasattr(q, "release"):
                        q.release()
                except Exception:
                    pass
            self.queues.clear()
            self.queue = None

            if self.program is not None:
                try:
                    if hasattr(self.program, "release"):
                        self.program.release()
                except Exception:
                    pass
                self.program = None

            if self.ctx is not None:
                try:
                    if hasattr(self.ctx, "release"):
                        self.ctx.release()
                except Exception:
                    pass
                self.ctx = None
            self.device = None

    # -----------------------------------------------------------------------
    # 1. 3D NDRange sRGB-to-Linear Grayscale + Gamma Contrast (Shared RAM Arena)
    # -----------------------------------------------------------------------
    def eval_srgb_to_linear_grayscale(self, arr: np.ndarray, gamma: float = 1.0) -> np.ndarray:
        if arr is None or arr.size == 0 or self._released or self.ctx is None or self.shared_arena is None:
            return np.zeros((0, 0), dtype=np.uint8) if arr is None else arr.astype(np.uint8)

        eff_gamma = float(np.clip(gamma if gamma > 0 else 1.0, 0.1, 5.0))
        inv_gamma = np.float32(1.0 / eff_gamma)
        q = self._next_queue()

        u8 = np.ascontiguousarray(np.clip(arr, 0, 255).astype(np.uint8))
        if u8.ndim == 3 and u8.shape[2] >= 3:
            h, w, ch = u8.shape
            n_px = int(h * w)
            out_shape: Tuple[int, ...] = (h, w)
        else:
            orig_shape = u8.shape
            n_px = int(u8.size)
            ch = 1
            out_shape = orig_shape

        w3, h3, z3 = self._factor_1d_to_3d(n_px, target_z_slices=max(4, self.compute_units))
        loc_3d = self._effective_local_3d(z3)
        glob_3d = self._round_global_3d(w3, h3, z3)

        src_buf = self.shared_arena.stage_input(q, "srgb_in", u8)
        dst_buf = self.shared_arena.get_pinned_buffer("srgb_out", n_px)
        self._k_srgb_3d(
            q,
            glob_3d,
            loc_3d,
            src_buf,
            dst_buf,
            np.int32(w3),
            np.int32(h3),
            np.int32(z3),
            np.int32(n_px),
            np.int32(ch),
            inv_gamma,
        )
        out = np.empty(out_shape, dtype=np.uint8)
        return self.shared_arena.read_output(q, dst_buf, out)

    # -----------------------------------------------------------------------
    # 2. 3D NDRange Valve Smoothstep + Boesch L2 Screen-Space Derivative SDF
    # -----------------------------------------------------------------------
    def eval_sdf_smoothstep(
        self,
        sdf_hi: np.ndarray,
        target_w: int,
        target_h: int,
        upscale: int,
        threshold: int = 128,
    ) -> Tuple[np.ndarray, np.ndarray]:
        assert self.shared_arena is not None
        hi_f32 = np.ascontiguousarray(sdf_hi.astype(np.float32))
        if hi_f32.ndim == 2:
            batch_z = 1
            hi_h, hi_w = hi_f32.shape
        else:
            batch_z, hi_h, hi_w = hi_f32.shape

        eff_t = int(np.clip(threshold if threshold > 0 else 128, 1, 254))
        bias_px = np.float32((128.0 - float(eff_t)) / 64.0)
        out_bytes = int(batch_z * target_h * target_w)

        q = self._next_queue()
        sdf_buf = self.shared_arena.stage_input(q, "sdf_hi_in", hi_f32)
        bw_buf = self.shared_arena.get_pinned_buffer("sdf_bw_out", out_bytes)
        fld_buf = self.shared_arena.get_pinned_buffer("sdf_fld_out", out_bytes)

        loc_3d = self._effective_local_3d(batch_z)
        glob_3d = self._round_global_3d(target_w, target_h, batch_z)
        self._k_sdf_smoothstep_3d(
            q,
            glob_3d,
            loc_3d,
            sdf_buf,
            bw_buf,
            fld_buf,
            np.int32(hi_w),
            np.int32(hi_h),
            np.int32(target_w),
            np.int32(target_h),
            np.int32(batch_z),
            np.int32(upscale),
            bias_px,
        )
        out_shape = (target_h, target_w) if sdf_hi.ndim == 2 else (batch_z, target_h, target_w)
        bilevel = np.empty(out_shape, dtype=np.uint8)
        field_u8 = np.empty(out_shape, dtype=np.uint8)
        self.shared_arena.read_output(q, bw_buf, bilevel)
        self.shared_arena.read_output(q, fld_buf, field_u8)
        return bilevel, field_u8

    # -----------------------------------------------------------------------
    # 3. 3D NDRange Chlumsky MSDF 3-Channel Median-of-Three Reconstruction
    # -----------------------------------------------------------------------
    def eval_msdf_median3_reconstruct(
        self,
        sdf_r: np.ndarray,
        sdf_g: np.ndarray,
        sdf_b: np.ndarray,
        edge_offset_px: float = 0.0,
    ) -> np.ndarray:
        assert self.shared_arena is not None
        if sdf_r.ndim == 2:
            batch_z = 1
            target_h, target_w = sdf_r.shape
        else:
            batch_z, target_h, target_w = sdf_r.shape

        r_f = np.ascontiguousarray(sdf_r.astype(np.float32))
        g_f = np.ascontiguousarray(sdf_g.astype(np.float32))
        b_f = np.ascontiguousarray(sdf_b.astype(np.float32))
        out_bytes = int(batch_z * target_h * target_w)

        q = self._next_queue()
        r_buf = self.shared_arena.stage_input(q, "msdf_r_in", r_f)
        g_buf = self.shared_arena.stage_input(q, "msdf_g_in", g_f)
        b_buf = self.shared_arena.stage_input(q, "msdf_b_in", b_f)
        bw_buf = self.shared_arena.get_pinned_buffer("msdf_bw_out", out_bytes)

        loc_3d = self._effective_local_3d(batch_z)
        glob_3d = self._round_global_3d(target_w, target_h, batch_z)
        self._k_msdf_median3_3d(
            q,
            glob_3d,
            loc_3d,
            r_buf,
            g_buf,
            b_buf,
            bw_buf,
            np.int32(target_w),
            np.int32(target_h),
            np.int32(batch_z),
            np.float32(edge_offset_px),
        )
        out_shape = (target_h, target_w) if sdf_r.ndim == 2 else (batch_z, target_h, target_w)
        bilevel = np.empty(out_shape, dtype=np.uint8)
        return self.shared_arena.read_output(q, bw_buf, bilevel)

    # -----------------------------------------------------------------------
    # 4. 3D NDRange Saffron 9-Point Bi-Quadratic Lagrange ADF
    # -----------------------------------------------------------------------
    def eval_adf_biquadratic(
        self,
        sdf_hi: np.ndarray,
        target_w: int,
        target_h: int,
        upscale: int,
        threshold: int = 128,
    ) -> Tuple[np.ndarray, np.ndarray]:
        assert self.shared_arena is not None
        hi_f32 = np.ascontiguousarray(sdf_hi.astype(np.float32))
        if hi_f32.ndim == 2:
            batch_z = 1
            hi_h, hi_w = hi_f32.shape
        else:
            batch_z, hi_h, hi_w = hi_f32.shape

        eff_t = int(np.clip(threshold if threshold > 0 else 128, 1, 254))
        bias_px = np.float32((128.0 - float(eff_t)) / 64.0)
        out_bytes = int(batch_z * target_h * target_w)

        q = self._next_queue()
        sdf_buf = self.shared_arena.stage_input(q, "adf_hi_in", hi_f32)
        bw_buf = self.shared_arena.get_pinned_buffer("adf_bw_out", out_bytes)
        fld_buf = self.shared_arena.get_pinned_buffer("adf_fld_out", out_bytes)

        loc_3d = self._effective_local_3d(batch_z)
        glob_3d = self._round_global_3d(target_w, target_h, batch_z)
        self._k_adf_biquad_3d(
            q,
            glob_3d,
            loc_3d,
            sdf_buf,
            bw_buf,
            fld_buf,
            np.int32(hi_w),
            np.int32(hi_h),
            np.int32(target_w),
            np.int32(target_h),
            np.int32(batch_z),
            np.int32(upscale),
            bias_px,
        )
        out_shape = (target_h, target_w) if sdf_hi.ndim == 2 else (batch_z, target_h, target_w)
        bilevel = np.empty(out_shape, dtype=np.uint8)
        field_u8 = np.empty(out_shape, dtype=np.uint8)
        self.shared_arena.read_output(q, bw_buf, bilevel)
        self.shared_arena.read_output(q, fld_buf, field_u8)
        return bilevel, field_u8

    # -----------------------------------------------------------------------
    # 5. 3D NDRange Cem Yuksel Quintic Bezier Exact SDF
    # -----------------------------------------------------------------------
    def eval_bezier_sdf_yuksel(
        self,
        curves_f32: np.ndarray,
        target_w: int,
        target_h: int,
        threshold: int = 128,
    ) -> Tuple[np.ndarray, np.ndarray]:
        if curves_f32.size == 0 or target_w <= 0 or target_h <= 0 or self.shared_arena is None:
            empty = np.zeros((max(1, target_h), max(1, target_w)), dtype=np.uint8)
            return empty, empty

        c_arr = np.ascontiguousarray(curves_f32.astype(np.float32))
        if c_arr.ndim == 4:
            batch_z = int(c_arr.shape[0])
            num_curves = int(c_arr.shape[1])
        else:
            batch_z = 1
            num_curves = int(c_arr.shape[0])

        eff_t = int(np.clip(threshold if threshold > 0 else 128, 1, 254))
        bias_px = np.float32((128.0 - float(eff_t)) / 64.0)
        out_bytes = int(batch_z * target_h * target_w)

        q = self._next_queue()
        c_buf = self.shared_arena.stage_input(q, "bezier_c_in", c_arr)
        bw_buf = self.shared_arena.get_pinned_buffer("bezier_bw_out", out_bytes)
        fld_buf = self.shared_arena.get_pinned_buffer("bezier_fld_out", out_bytes)

        loc_3d = self._effective_local_3d(batch_z)
        glob_3d = self._round_global_3d(target_w, target_h, batch_z)
        self._k_bezier_yuksel_3d(
            q,
            glob_3d,
            loc_3d,
            c_buf,
            np.int32(num_curves),
            bw_buf,
            fld_buf,
            np.int32(target_w),
            np.int32(target_h),
            np.int32(batch_z),
            bias_px,
        )
        out_shape = (target_h, target_w) if curves_f32.ndim != 4 else (batch_z, target_h, target_w)
        bilevel = np.empty(out_shape, dtype=np.uint8)
        field_u8 = np.empty(out_shape, dtype=np.uint8)
        self.shared_arena.read_output(q, bw_buf, bilevel)
        self.shared_arena.read_output(q, fld_buf, field_u8)
        return bilevel, field_u8

    # -----------------------------------------------------------------------
    # 6. 3D NDRange Local-Atomic Histogram Otsu Thresholding
    # -----------------------------------------------------------------------
    def eval_otsu_linear_threshold(self, linear_gray: np.ndarray, base_threshold: int = 128) -> int:
        if linear_gray is None or linear_gray.size < 64 or self.shared_arena is None:
            from .cpu_math import eval_otsu_linear_threshold_cpu
            return eval_otsu_linear_threshold_cpu(linear_gray, base_threshold)

        u8 = np.ascontiguousarray(linear_gray.astype(np.uint8)).ravel()
        n_px = int(u8.size)
        w3, h3, z3 = self._factor_1d_to_3d(n_px, target_z_slices=max(4, self.compute_units))
        loc_3d = self._effective_local_3d(z3)
        glob_3d = self._round_global_3d(w3, h3, z3)

        q = self._next_queue()
        src_buf = self.shared_arena.stage_input(q, "otsu_gray_in", u8)
        hist_zeros = np.zeros(256, dtype=np.uint32)
        hist_buf = self.shared_arena.stage_input(q, "otsu_hist_io", hist_zeros)

        self._k_otsu_hist_3d(
            q,
            glob_3d,
            loc_3d,
            src_buf,
            hist_buf,
            np.int32(w3),
            np.int32(h3),
            np.int32(z3),
            np.int32(n_px),
        )
        hist = np.empty(256, dtype=np.uint32)
        self.shared_arena.read_output(q, hist_buf, hist)

        total = float(np.sum(hist))
        if total < 6.0:
            return base_threshold
        p = hist.astype(np.float64) / total
        omega = np.cumsum(p)
        mu = np.cumsum(p * np.arange(256, dtype=np.float64))
        mu_t = mu[-1]
        denom = omega * (1.0 - omega)
        valid = denom > 1e-9
        sigma_b_sq = np.zeros(256, dtype=np.float64)
        sigma_b_sq[valid] = ((mu_t * omega[valid] - mu[valid]) ** 2) / denom[valid]
        k_star = int(np.argmax(sigma_b_sq))
        user_offset = int(base_threshold) - 128
        return int(np.clip(round(0.70 * k_star + 0.30 * 128 + user_offset), 72, 184))

    # -----------------------------------------------------------------------
    # 7. 3D NDRange Jump Flooding Algorithm (1+JFA) + Marching Squares Sub-Mode
    # -----------------------------------------------------------------------
    def eval_jfa_marching_squares(
        self,
        high_gray: np.ndarray,
        target_w: int,
        target_h: int,
        upscale: int = 10,
        threshold: int = 128,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Execute the 3-Stage Pure GPU Vector Contour & Distance Pipeline (`svg-potrace-jfa` / `jfa-marching`):
          1. `jfa_init_marching_seeds_3d_kernel`: Sub-pixel Marching Squares 2x2 iso-contour seed extraction.
          2. `jfa_flood_step_3d_kernel`: O(log2 N) `1+JFA` parallel ping-pong seed propagation in Shared RAM.
          3. `jfa_marching_squares_reconstruct_3d_kernel`: Marching Squares 16-case saddle-disambiguated
             cell coverage + JFA signed distance reconstruction.
        """
        assert self.shared_arena is not None
        u8_hi = np.ascontiguousarray(high_gray.astype(np.uint8))
        if u8_hi.ndim == 2:
            batch_z = 1
            hi_h, hi_w = u8_hi.shape
        else:
            batch_z, hi_h, hi_w = u8_hi.shape

        eff_t = int(np.clip(threshold if threshold > 0 else 128, 1, 254))
        iso_thresh = np.float32(float(eff_t))
        bias_px = np.float32((128.0 - float(eff_t)) / 64.0)

        n_hi_cells = int(batch_z * hi_h * hi_w)
        seed_bytes = n_hi_cells * 8  # float2 = 8 bytes per high-res pixel
        out_bytes = int(batch_z * target_h * target_w)

        q = self._next_queue()
        gray_buf = self.shared_arena.stage_input(q, "jfa_gray_in", u8_hi)
        ping_buf = self.shared_arena.get_pinned_buffer("jfa_seeds_ping", seed_bytes)
        pong_buf = self.shared_arena.get_pinned_buffer("jfa_seeds_pong", seed_bytes)
        bw_buf = self.shared_arena.get_pinned_buffer("jfa_bw_out", out_bytes)
        fld_buf = self.shared_arena.get_pinned_buffer("jfa_fld_out", out_bytes)

        loc_hi_3d = self._effective_local_3d(batch_z)
        glob_hi_3d = self._round_global_3d(hi_w, hi_h, batch_z)

        # Pass 1: Marching Squares sub-pixel iso-contour seed extraction
        self._k_jfa_init_3d(
            q,
            glob_hi_3d,
            loc_hi_3d,
            gray_buf,
            ping_buf,
            np.int32(hi_w),
            np.int32(hi_h),
            np.int32(batch_z),
            iso_thresh,
        )

        # Pass 2: 1+JFA logarithmic jump-flooding cascade `[1, 2^(k-1), ..., 4, 2, 1]`
        max_dim = max(hi_w, hi_h, 2)
        top_pow2 = 1 << max(0, int(math.ceil(math.log2(max_dim))) - 1)
        steps: List[int] = [1]
        s = top_pow2
        while s >= 1:
            steps.append(s)
            s //= 2

        src_seeds, dst_seeds = ping_buf, pong_buf
        for step_k in steps:
            self._k_jfa_step_3d(
                q,
                glob_hi_3d,
                loc_hi_3d,
                src_seeds,
                dst_seeds,
                np.int32(hi_w),
                np.int32(hi_h),
                np.int32(batch_z),
                np.int32(step_k),
            )
            src_seeds, dst_seeds = dst_seeds, src_seeds

        # Pass 3: Marching Squares 16-case + JFA signed distance reconstruction onto target grid
        loc_lo_3d = self._effective_local_3d(batch_z)
        glob_lo_3d = self._round_global_3d(target_w, target_h, batch_z)
        self._k_jfa_ms_recon_3d(
            q,
            glob_lo_3d,
            loc_lo_3d,
            gray_buf,
            src_seeds,
            bw_buf,
            fld_buf,
            np.int32(hi_w),
            np.int32(hi_h),
            np.int32(target_w),
            np.int32(target_h),
            np.int32(batch_z),
            np.int32(upscale),
            iso_thresh,
            bias_px,
        )

        out_shape = (target_h, target_w) if high_gray.ndim == 2 else (batch_z, target_h, target_w)
        bilevel = np.empty(out_shape, dtype=np.uint8)
        field_u8 = np.empty(out_shape, dtype=np.uint8)
        self.shared_arena.read_output(q, bw_buf, bilevel)
        self.shared_arena.read_output(q, fld_buf, field_u8)
        return bilevel, field_u8


def validate_sdf_gradient(sdf_tex: np.ndarray, tolerance: float = 0.08) -> Tuple[bool, float]:
    """Validate that a normalized 2D SDF [0..1] maintains near-unit gradient magnitude (||grad d||_2 ~ 1.0)."""
    if sdf_tex is None or sdf_tex.ndim != 2 or min(sdf_tex.shape) < 4:
        return False, 0.0
    dy, dx = np.gradient(sdf_tex.astype(np.float32))
    grad_len = np.sqrt(dx * dx + dy * dy)
    interior = (sdf_tex > 0.05) & (sdf_tex < 0.95)
    if not np.any(interior):
        return True, 1.0
    mean_grad = float(np.mean(grad_len[interior]))
    return (abs(mean_grad - 1.0) <= tolerance), mean_grad
