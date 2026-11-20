#!/usr/bin/env python3
"""
opencl_kernels.py (v1.0.23)
==========================
A 1-bit EPD font generator and asset pipeline for embedded displays.
Repository : https://github.com/Humidyne-Labs/epd-font
Authors    : Humiditron (https://github.com/humiditron) & AI/LLM Development Partner
License    : MIT License

OpenCL 1.2 / 2.0 / 3.0 GPU & Multi-Device Compute Kernels, 3D NDRange Batch Dispatcher,
75% Dynamic Host/GPU Shared Memory Arena (`CL_MEM_ALLOC_HOST_PTR` + `clEnqueueMapBuffer`),
Jump Flooding Algorithm (`1+JFA`) + Marching Squares Kernels, and Deterministic Teardown (`v1.0.23`):
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
import subprocess
import threading
import time
import warnings
import weakref
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

TOOL_VERSION = "1.0.23"
SHARED_RAM_CAP_RATIO = 0.75  # 75% cap on total WDDM Shared GPU Memory

cl = None  # type: ignore
HAS_PYOPENCL = False


def ensure_pyopencl() -> bool:
    """Dynamically probe and load PyOpenCL only when hardware acceleration is permitted."""
    global cl, HAS_PYOPENCL
    eff = os.environ.get("EPD_FONT_ACCEL", "auto").strip().lower()
    role = os.environ.get("EPD_FONT_WORKER_ROLE", "").strip().lower()
    if eff == "cpu" or role == "cpu":
        cl = None
        HAS_PYOPENCL = False
        return False
    if cl is not None and HAS_PYOPENCL:
        return True
    try:
        import pyopencl as _cl  # type: ignore
        cl = _cl
        HAS_PYOPENCL = True
        return True
    except Exception:
        cl = None
        HAS_PYOPENCL = False
        return False


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
    usable_shared_mb = max(256, min(avail_phys_mb - 1024, cap_75pct_mb))
    return total_shared_mb, usable_shared_mb


# ---------------------------------------------------------------------------
# OpenCL C Kernel Source (3D NDRange `[dim_x, dim_y, dim_z]` Across All Kernels)
# ---------------------------------------------------------------------------
OPENCL_MATH_KERNELS_SOURCE = r"""
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
    __global uchar* out_field,
    const int target_w,
    const int target_h,
    const int batch_z,
    const float bias_px)
{
    const int gx = (int)get_global_id(0);
    const int gy = (int)get_global_id(1);
    const int gz = (int)get_global_id(2);
    if (gx >= target_w || gy >= target_h || gz >= batch_z) return;

    int idx = (gz * target_h + gy) * target_w + gx;
    float m = median3_f(sdf_r[idx], sdf_g[idx], sdf_b[idx]);

    int x_r = min(gx + 1, target_w - 1);
    int y_d = min(gy + 1, target_h - 1);
    int idx_r = (gz * target_h + gy) * target_w + x_r;
    int idx_d = (gz * target_h + y_d) * target_w + gx;

    float m_r = median3_f(sdf_r[idx_r], sdf_g[idx_r], sdf_b[idx_r]);
    float m_d = median3_f(sdf_r[idx_d], sdf_g[idx_d], sdf_b[idx_d]);

    float dx = m_r - m;
    float dy = m_d - m;
    float w = clamp(length((float2)(dx, dy)), 0.65f, 1.50f);

    float cov = clamp((m + bias_px) / w + 0.5f, 0.0f, 1.0f);
    out_field[idx] = convert_uchar_sat_rte(clamp(cov * 255.0f, 0.0f, 255.0f));
    out_bilevel[idx] = (cov >= 0.50f) ? 1 : 0;
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

// ---------------------------------------------------------------------------
// 8. 3D NDRange WDDM Shared Memory Page-Touch Kernel
// ---------------------------------------------------------------------------
__kernel void touch_shared_pages_3d_kernel(
    __global uchar* buf,
    const long nbytes)
{
    const long idx = (long)get_global_id(0) * 4096L;
    if (idx < nbytes) {
        buf[idx] ^= (uchar)0;
    }
}

// ---------------------------------------------------------------------------
// 9. Coalesced 3D short2 1+JFA Signed Distance Field Kernels (4 bytes/pixel)
// ---------------------------------------------------------------------------
#define JFA_NO_SEED ((short)-30000)

__kernel void jfa_boundary_init_short2_3d_kernel(
    __global const uchar* gray,
    __global short2* seeds,
    const int W,
    const int H,
    const int B,
    const uchar thresh)
{
    const int x = (int)get_global_id(0);
    const int y = (int)get_global_id(1);
    const int z = (int)get_global_id(2);
    if (x >= W || y >= H || z >= B) return;

    const int base = z * H * W;
    const int idx = base + y * W + x;
    const int fg = (gray[idx] >= thresh) ? 1 : 0;

    int sx = 0;
    int sy = 0;
    int cnt = 0;
    if (x > 0 && (((gray[idx - 1] >= thresh) ? 1 : 0) != fg)) {
        sx += 2 * x - 1;
        sy += 2 * y;
        cnt++;
    }
    if (x + 1 < W && (((gray[idx + 1] >= thresh) ? 1 : 0) != fg)) {
        sx += 2 * x + 1;
        sy += 2 * y;
        cnt++;
    }
    if (y > 0 && (((gray[idx - W] >= thresh) ? 1 : 0) != fg)) {
        sx += 2 * x;
        sy += 2 * y - 1;
        cnt++;
    }
    if (y + 1 < H && (((gray[idx + W] >= thresh) ? 1 : 0) != fg)) {
        sx += 2 * x;
        sy += 2 * y + 1;
        cnt++;
    }

    if (cnt > 0) {
        seeds[idx] = (short2)((short)(sx / cnt), (short)(sy / cnt));
    } else {
        seeds[idx] = (short2)(JFA_NO_SEED, JFA_NO_SEED);
    }
}

__kernel void jfa_step_short2_3d_kernel(
    __global const short2* in_s,
    __global short2* out_s,
    const int W,
    const int H,
    const int B,
    const int step_k)
{
    const int x = (int)get_global_id(0);
    const int y = (int)get_global_id(1);
    const int z = (int)get_global_id(2);
    if (x >= W || y >= H || z >= B) return;

    const int base = z * H * W;
    const int idx = base + y * W + x;
    const int px = 2 * x;
    const int py = 2 * y;

    short2 best = in_s[idx];
    int best_d2 = 0x3fffffff;
    if (best.x != JFA_NO_SEED) {
        int dx = (int)best.x - px;
        int dy = (int)best.y - py;
        best_d2 = dx * dx + dy * dy;
    }

    for (int oy = -1; oy <= 1; ++oy) {
        int ny = y + oy * step_k;
        if (ny < 0 || ny >= H) continue;
        int row = base + ny * W;
        for (int ox = -1; ox <= 1; ++ox) {
            if (ox == 0 && oy == 0) continue;
            int nx = x + ox * step_k;
            if (nx < 0 || nx >= W) continue;
            short2 c = in_s[row + nx];
            if (c.x != JFA_NO_SEED) {
                int dx = (int)c.x - px;
                int dy = (int)c.y - py;
                int d2 = dx * dx + dy * dy;
                if (d2 < best_d2) {
                    best_d2 = d2;
                    best = c;
                }
            }
        }
    }
    out_s[idx] = best;
}

__kernel void jfa_short2_to_sdf_3d_kernel(
    __global const uchar* gray,
    __global const short2* seeds,
    __global float* sdf_out,
    const int W,
    const int H,
    const int B,
    const uchar thresh,
    const float inv_upscale)
{
    const int x = (int)get_global_id(0);
    const int y = (int)get_global_id(1);
    const int z = (int)get_global_id(2);
    if (x >= W || y >= H || z >= B) return;

    const int idx = (z * H + y) * W + x;
    short2 s = seeds[idx];
    float d = 4.0f;
    if (s.x != JFA_NO_SEED) {
        float dx = 0.5f * (float)((int)s.x - 2 * x);
        float dy = 0.5f * (float)((int)s.y - 2 * y);
        d = (sqrt(dx * dx + dy * dy) + 0.5f) * inv_upscale;
    }
    float sgn = (gray[idx] >= thresh) ? 1.0f : -1.0f;
    sdf_out[idx] = clamp(sgn * d, -4.0f, 4.0f);
}

// ---------------------------------------------------------------------------
// 10. 3D Per-Slice Batched Otsu Local-Atomic Histogram Kernel (local_size.z == 1)
// ---------------------------------------------------------------------------
__kernel void otsu_hist_batch_3d_kernel(
    __global const uchar* src_gray,
    __global const int* slice_dims,
    __global uint* global_hists,
    const int max_w,
    const int max_h,
    const int batch_z)
{
    __local uint local_hist[256];
    const int lx = (int)get_local_id(0);
    const int ly = (int)get_local_id(1);
    const int sx = (int)get_local_size(0);
    const int sy = (int)get_local_size(1);
    const int lid = lx + sx * ly;
    const int lsize = sx * sy;

    for (int b = lid; b < 256; b += lsize) {
        local_hist[b] = 0u;
    }
    barrier(CLK_LOCAL_MEM_FENCE);

    const int gx = (int)get_global_id(0);
    const int gy = (int)get_global_id(1);
    const int gz = (int)get_global_id(2);
    if (gz < batch_z) {
        const int gw = slice_dims[gz * 2 + 0];
        const int gh = slice_dims[gz * 2 + 1];
        if (gx < gw && gy < gh) {
            const int gid = (gz * max_h + gy) * max_w + gx;
            uchar v = src_gray[gid];
            if (v >= 8u && v <= 248u) {
                atomic_inc(&local_hist[(int)v]);
            }
        }
    }
    barrier(CLK_LOCAL_MEM_FENCE);

    if (gz < batch_z) {
        const int hist_base = gz * 256;
        for (int b = lid; b < 256; b += lsize) {
            uint c = local_hist[b];
            if (c > 0u) {
                atomic_add(&global_hists[hist_base + b], c);
            }
        }
    }
}

// ---------------------------------------------------------------------------
// 11. 3D Binarize, Median Blur, Directional Morphology, MDF & MSDF Helpers
// ---------------------------------------------------------------------------
__kernel void binarize_u8_3d_kernel(
    __global const uchar* gray,
    __global uchar* mask,
    const int W,
    const int H,
    const int B,
    const uchar thresh)
{
    const int x = (int)get_global_id(0);
    const int y = (int)get_global_id(1);
    const int z = (int)get_global_id(2);
    if (x >= W || y >= H || z >= B) return;
    const int idx = (z * H + y) * W + x;
    mask[idx] = (gray[idx] >= thresh) ? (uchar)1 : (uchar)0;
}

__kernel void median_blur_3d_kernel(
    __global const uchar* src,
    __global uchar* dst,
    const int W,
    const int H,
    const int B,
    const int radius)
{
    const int x = (int)get_global_id(0);
    const int y = (int)get_global_id(1);
    const int z = (int)get_global_id(2);
    if (x >= W || y >= H || z >= B) return;

    const int base = z * H * W;
    const int r = (radius <= 1) ? 1 : 2;
    const int n = (r == 1) ? 9 : 25;
    const int mid = n / 2;
    uchar vals[25];
    int k = 0;

    for (int dy = -r; dy <= r; ++dy) {
        int ny = clamp(y + dy, 0, H - 1);
        int row = base + ny * W;
        for (int dx = -r; dx <= r; ++dx) {
            int nx = clamp(x + dx, 0, W - 1);
            vals[k++] = src[row + nx];
        }
    }

    for (int i = 0; i <= mid; ++i) {
        int min_idx = i;
        uchar min_val = vals[i];
        for (int j = i + 1; j < n; ++j) {
            if (vals[j] < min_val) {
                min_val = vals[j];
                min_idx = j;
            }
        }
        vals[min_idx] = vals[i];
        vals[i] = min_val;
    }
    dst[base + y * W + x] = vals[mid];
}

__kernel void morph_dilate_dir_3d_kernel(
    __global const uchar* src,
    __global uchar* dst,
    const int W,
    const int H,
    const int B,
    const int dx,
    const int dy,
    const int r_neg,
    const int r_pos)
{
    const int x = (int)get_global_id(0);
    const int y = (int)get_global_id(1);
    const int z = (int)get_global_id(2);
    if (x >= W || y >= H || z >= B) return;

    const int base = z * H * W;
    uchar m = 0;
    for (int k = -r_neg; k <= r_pos; ++k) {
        int nx = clamp(x + k * dx, 0, W - 1);
        int ny = clamp(y + k * dy, 0, H - 1);
        uchar v = src[base + ny * W + nx];
        if (v > m) m = v;
    }
    dst[base + y * W + x] = m;
}

__kernel void morph_erode_dir_3d_kernel(
    __global const uchar* src,
    __global uchar* dst,
    const int W,
    const int H,
    const int B,
    const int dx,
    const int dy,
    const int r_neg,
    const int r_pos)
{
    const int x = (int)get_global_id(0);
    const int y = (int)get_global_id(1);
    const int z = (int)get_global_id(2);
    if (x >= W || y >= H || z >= B) return;

    const int base = z * H * W;
    uchar m = 255;
    for (int k = -r_neg; k <= r_pos; ++k) {
        int nx = clamp(x + k * dx, 0, W - 1);
        int ny = clamp(y + k * dy, 0, H - 1);
        uchar v = src[base + ny * W + nx];
        if (v < m) m = v;
    }
    dst[base + y * W + x] = m;
}

__kernel void combine_max_u8_3d_kernel(
    __global const uchar* a,
    __global const uchar* b,
    __global uchar* out,
    const int W,
    const int H,
    const int B)
{
    const int x = (int)get_global_id(0);
    const int y = (int)get_global_id(1);
    const int z = (int)get_global_id(2);
    if (x >= W || y >= H || z >= B) return;
    const int idx = (z * H + y) * W + x;
    out[idx] = max(a[idx], b[idx]);
}

__kernel void mdf_reconstruct_3d_kernel(
    __global const float* sdf_iso,
    __global const float* sdf_h,
    __global const float* sdf_v,
    __global uchar* out_bw,
    __global uchar* out_fld,
    const int hi_w,
    const int hi_h,
    const int target_w,
    const int target_h,
    const int batch_z,
    const int upscale,
    const int eff_thresh)
{
    const int gx = (int)get_global_id(0);
    const int gy = (int)get_global_id(1);
    const int gz = (int)get_global_id(2);
    if (gx >= target_w || gy >= target_h || gz >= batch_z) return;

    const int slice_base = gz * (hi_w * hi_h);
    const int r0 = gy * upscale;
    const int r1 = min(r0 + upscale, hi_h);
    const int c0 = gx * upscale;
    const int c1 = min(c0 + upscale, hi_w);

    float sum_val = 0.0f;
    int cnt = 0;
    for (int hr = r0; hr < r1; ++hr) {
        int row = slice_base + hr * hi_w;
        for (int hc = c0; hc < c1; ++hc) {
            int hidx = row + hc;
            float m = clamp(median3_f(sdf_iso[hidx], sdf_h[hidx], sdf_v[hidx]), -4.0f, 4.0f);
            float enc = clamp(128.0f + m * 64.0f, 0.0f, 255.0f);
            sum_val += enc;
            cnt++;
        }
    }
    float area_avg = (cnt > 0) ? (sum_val / (float)cnt) : 0.0f;

    const int rm = clamp(r0 + (upscale / 2), 0, hi_h - 1);
    const int cm = clamp(c0 + (upscale / 2), 0, hi_w - 1);
    const int cidx = slice_base + rm * hi_w + cm;
    float mc = clamp(median3_f(sdf_iso[cidx], sdf_h[cidx], sdf_v[cidx]), -4.0f, 4.0f);
    float center_val = clamp(128.0f + mc * 64.0f, 0.0f, 255.0f);

    float mdf_low = 0.60f * area_avg + 0.40f * center_val;
    uchar m_u8 = convert_uchar_sat_rte(clamp(mdf_low, 0.0f, 255.0f));

    const int out_idx = (gz * target_h + gy) * target_w + gx;
    out_fld[out_idx] = m_u8;
    out_bw[out_idx] = (m_u8 >= (uchar)eff_thresh) ? (uchar)1 : (uchar)0;
}

__kernel void msdf_downsample_rgb_3d_kernel(
    __global const uchar* gray_hi,
    __global const float* sdf_iso,
    __global const float* sdf_r,
    __global const float* sdf_g,
    __global float* out_r,
    __global float* out_g,
    __global float* out_b,
    const int hi_w,
    const int hi_h,
    const int target_w,
    const int target_h,
    const int batch_z,
    const int upscale)
{
    const int gx = (int)get_global_id(0);
    const int gy = (int)get_global_id(1);
    const int gz = (int)get_global_id(2);
    if (gx >= target_w || gy >= target_h || gz >= batch_z) return;

    const int slice_base = gz * (hi_w * hi_h);
    const int r0 = gy * upscale;
    const int r1 = min(r0 + upscale, hi_h);
    const int c0 = gx * upscale;
    const int c1 = min(c0 + upscale, hi_w);
    const float inv_up = 0.12f / (float)max(1, upscale);

    float sum_r = 0.0f;
    float sum_g = 0.0f;
    float sum_b = 0.0f;
    int cnt = 0;

    for (int hr = r0; hr < r1; ++hr) {
        int rm1 = max(hr - 1, 0);
        int rp1 = min(hr + 1, hi_h - 1);
        for (int hc = c0; hc < c1; ++hc) {
            int cm1 = max(hc - 1, 0);
            int cp1 = min(hc + 1, hi_w - 1);
            int hidx = slice_base + hr * hi_w + hc;

            float g00 = (float)gray_hi[slice_base + rm1 * hi_w + cm1];
            float g10 = (float)gray_hi[slice_base + rm1 * hi_w + hc];
            float g20 = (float)gray_hi[slice_base + rm1 * hi_w + cp1];
            float g01 = (float)gray_hi[slice_base + hr  * hi_w + cm1];
            float g21 = (float)gray_hi[slice_base + hr  * hi_w + cp1];
            float g02 = (float)gray_hi[slice_base + rp1 * hi_w + cm1];
            float g12 = (float)gray_hi[slice_base + rp1 * hi_w + hc];
            float g22 = (float)gray_hi[slice_base + rp1 * hi_w + cp1];

            float sx = (g20 + 2.0f * g21 + g22) - (g00 + 2.0f * g01 + g02);
            float sy = (g02 + 2.0f * g12 + g22) - (g00 + 2.0f * g10 + g20);
            float gmag = hypot(sx, sy) + 1e-5f;
            float aniso = ((fabs(sx) - fabs(sy)) / gmag) * inv_up;

            sum_r += clamp(128.0f + clamp(sdf_r[hidx], -4.0f, 4.0f) * 64.0f, 0.0f, 255.0f);
            sum_g += clamp(128.0f + clamp(sdf_g[hidx], -4.0f, 4.0f) * 64.0f, 0.0f, 255.0f);
            sum_b += clamp(128.0f + clamp(sdf_iso[hidx] + aniso, -4.0f, 4.0f) * 64.0f, 0.0f, 255.0f);
            cnt++;
        }
    }

    float inv_cnt = (cnt > 0) ? (1.0f / (float)cnt) : 0.0f;
    float ar = sum_r * inv_cnt;
    float ag = sum_g * inv_cnt;
    float ab = sum_b * inv_cnt;

    const int rm = clamp(r0 + (upscale / 2), 0, hi_h - 1);
    const int cm = clamp(c0 + (upscale / 2), 0, hi_w - 1);
    const int cidx = slice_base + rm * hi_w + cm;
    float cr = clamp(128.0f + clamp(sdf_r[cidx], -4.0f, 4.0f) * 64.0f, 0.0f, 255.0f);
    float cg = clamp(128.0f + clamp(sdf_g[cidx], -4.0f, 4.0f) * 64.0f, 0.0f, 255.0f);
    float cb = clamp(128.0f + clamp(sdf_iso[cidx], -4.0f, 4.0f) * 64.0f, 0.0f, 255.0f);

    float br = rint(clamp(0.55f * ar + 0.45f * cr, 0.0f, 255.0f));
    float bg = rint(clamp(0.55f * ag + 0.45f * cg, 0.0f, 255.0f));
    float bb = rint(clamp(0.55f * ab + 0.45f * cb, 0.0f, 255.0f));

    const int out_idx = (gz * target_h + gy) * target_w + gx;
    out_r[out_idx] = (br - 128.0f) / 64.0f;
    out_g[out_idx] = (bg - 128.0f) / 64.0f;
    out_b[out_idx] = (bb - 128.0f) / 64.0f;
}
"""


# ---------------------------------------------------------------------------
# Host/GPU Shared RAM Pinned Memory Arena (`CL_MEM_ALLOC_HOST_PTR` + 75% Cap)
# ---------------------------------------------------------------------------
class SharedHostMemoryArena:
    """
    Manages a reusable pool of pinned Host/GPU Shared RAM (`CL_MEM_ALLOC_HOST_PTR`) buffers
    mapped into the WDDM Shared GPU Memory aperture (dynamically capped at 75% of total Shared
    GPU Memory, e.g., ~12,054 MB on a 32 GB system), plus an optional bounded Dedicated VRAM
    hot-scratch tier (`EPD_FONT_SHARED_MODE=auto`, or 100% Shared RAM when `"shared"`).
    Uses OpenCL-spec-compliant `cl.enqueue_map_buffer` -> copy -> unmap (`mapped.base.release`)
    for staging/readback, drains active command queues prior to buffer eviction/resize, and
    guarantees deterministic `.release()` teardown on exit.
    """

    def __init__(
        self,
        ctx: "cl.Context",
        max_shared_mb: int = 4096,
        device: Optional["cl.Device"] = None,
        queues: Optional[List["cl.CommandQueue"]] = None,
    ) -> None:
        ensure_pyopencl()
        self.ctx = ctx
        if device is None and ctx is not None:
            try:
                devs = getattr(ctx, "devices", None) or []
                if devs:
                    device = devs[0]
            except Exception:
                device = None
        self.device = device
        self._queues_ref: Optional[List["cl.CommandQueue"]] = queues

        self.max_shared_bytes = max(64, int(max_shared_mb)) * 1024 * 1024
        self.budget_bytes = self.max_shared_bytes
        dev_max_alloc = int(getattr(device, "max_mem_alloc_size", 0)) if device is not None else 0
        self.max_single_alloc_bytes = (
            min(int(dev_max_alloc * 0.90), self.max_shared_bytes) if dev_max_alloc > 0 else self.max_shared_bytes
        )

        dev_type = int(getattr(device, "type", 0)) if device is not None else 0
        is_gpu = bool(dev_type & getattr(cl.device_type, "GPU", 4)) if cl is not None else False
        is_cpu_dev = bool(dev_type & getattr(cl.device_type, "CPU", 2)) and not is_gpu if cl is not None else False
        host_unified = bool(getattr(device, "host_unified_memory", 0)) if device is not None else False
        shared_mode = os.environ.get("EPD_FONT_SHARED_MODE", "auto").strip().lower()
        self.shared_mode = "shared" if shared_mode == "shared" else "auto"
        dev_global_bytes = int(getattr(device, "global_mem_size", 0)) if device is not None else 0

        if is_cpu_dev or host_unified or self.shared_mode == "shared" or dev_global_bytes <= 0:
            self.vram_scratch_budget = 0
        else:
            self.vram_scratch_budget = min(int(dev_global_bytes * 0.45), self.max_single_alloc_bytes)

        self.allocated_bytes = 0
        self.peak_allocated_bytes = 0
        self.vram_allocated_bytes = 0
        self.peak_vram_allocated_bytes = 0
        self._lock = threading.Lock()
        self._slots: Dict[str, Tuple["cl.Buffer", int, bool]] = {}

    def _drain_queues_unlocked(self) -> None:
        if self._queues_ref:
            for q in self._queues_ref:
                try:
                    q.finish()
                except Exception:
                    pass

    def _release_slot_unlocked(self, slot_name: str) -> None:
        entry = self._slots.pop(slot_name, None)
        if entry is None:
            return
        buf, cap, is_shared = entry
        try:
            buf.release()
        except Exception:
            pass
        if is_shared:
            self.allocated_bytes = max(0, self.allocated_bytes - cap)
        else:
            self.vram_allocated_bytes = max(0, self.vram_allocated_bytes - cap)

    def get_pinned_buffer(
        self,
        slot_name: str,
        min_bytes: int,
        flags: int = 0,
        queue: Optional["cl.CommandQueue"] = None,
    ) -> "cl.Buffer":
        """Acquire or grow a named reusable `CL_MEM_ALLOC_HOST_PTR` buffer in Shared GPU RAM."""
        ensure_pyopencl()
        req_bytes = max(4096, ((int(min_bytes) + 4095) // 4096) * 4096)
        if req_bytes > self.max_single_alloc_bytes:
            raise MemoryError(
                f"Requested Shared GPU RAM buffer '{slot_name}' ({req_bytes // (1024 * 1024)} MB) "
                f"exceeds device single-allocation ceiling ({self.max_single_alloc_bytes // (1024 * 1024)} MB)."
            )
        mf = cl.mem_flags
        alloc_flags = (flags or mf.READ_WRITE) | mf.ALLOC_HOST_PTR

        with self._lock:
            existing = self._slots.get(slot_name)
            if existing is not None:
                buf, cap, is_shared = existing
                if is_shared and cap >= req_bytes:
                    return buf
                self._drain_queues_unlocked()
                self._release_slot_unlocked(slot_name)

            if self.allocated_bytes + req_bytes > self.max_shared_bytes:
                self._drain_queues_unlocked()
                self._evict_unlocked(shared_only=True)

            new_buf = cl.Buffer(self.ctx, alloc_flags, size=req_bytes)
            self._slots[slot_name] = (new_buf, req_bytes, True)
            self.allocated_bytes += req_bytes
            self.peak_allocated_bytes = max(self.peak_allocated_bytes, self.allocated_bytes)
            return new_buf

    def get_scratch_buffer(
        self,
        slot_name: str,
        min_bytes: int,
        prefer_shared: bool = False,
    ) -> "cl.Buffer":
        """
        Acquire a device-side working scratch buffer: uses bounded high-bandwidth Dedicated VRAM
        when `EPD_FONT_SHARED_MODE=auto` and within `vram_scratch_budget`, overflowing seamlessly
        to WDDM Shared GPU Memory (`CL_MEM_ALLOC_HOST_PTR`) for larger buffers or `shared` mode.
        """
        ensure_pyopencl()
        req_bytes = max(4096, ((int(min_bytes) + 4095) // 4096) * 4096)
        if prefer_shared or self.vram_scratch_budget <= 0 or req_bytes > self.vram_scratch_budget:
            return self.get_pinned_buffer(slot_name, req_bytes)

        with self._lock:
            existing = self._slots.get(slot_name)
            if existing is not None:
                buf, cap, is_shared = existing
                if not is_shared and cap >= req_bytes:
                    return buf
                self._drain_queues_unlocked()
                self._release_slot_unlocked(slot_name)

            if self.vram_allocated_bytes + req_bytes > self.vram_scratch_budget:
                self._drain_queues_unlocked()
                self._evict_vram_unlocked()

            if self.vram_allocated_bytes + req_bytes <= self.vram_scratch_budget:
                try:
                    new_buf = cl.Buffer(self.ctx, cl.mem_flags.READ_WRITE, size=req_bytes)
                    self._slots[slot_name] = (new_buf, req_bytes, False)
                    self.vram_allocated_bytes += req_bytes
                    self.peak_vram_allocated_bytes = max(self.peak_vram_allocated_bytes, self.vram_allocated_bytes)
                    return new_buf
                except Exception:
                    pass

        return self.get_pinned_buffer(slot_name, req_bytes)

    def compute_max_batch_z(self, slice_bytes: int, num_buffers: int, requested_z: int) -> int:
        """Compute maximum safe `batch_z` respecting device `max_mem_alloc_size` and 75% Shared RAM cap."""
        req_z = max(1, int(requested_z))
        per_slice = max(1, int(slice_bytes))
        n_bufs = max(1, int(num_buffers))
        max_by_single = max(1, self.max_single_alloc_bytes // per_slice)
        max_by_total = max(1, int(self.max_shared_bytes * 0.80) // (per_slice * n_bufs))
        return max(1, min(req_z, max_by_single, max_by_total))

    def stage_input(self, queue: "cl.CommandQueue", slot_name: str, arr: np.ndarray) -> "cl.Buffer":
        """
        Stage `arr` into a `CL_MEM_ALLOC_HOST_PTR` Shared GPU RAM slot using spec-compliant
        `cl.enqueue_map_buffer` -> `np.copyto` -> unmap (`mapped.base.release`).
        """
        contig = np.ascontiguousarray(arr)
        nbytes = int(contig.nbytes)
        buf = self.get_pinned_buffer(slot_name, nbytes, cl.mem_flags.READ_WRITE, queue=queue)
        if nbytes == 0:
            return buf
        try:
            map_flag = getattr(cl.map_flags, "WRITE_INVALIDATE_REGION", cl.map_flags.WRITE)
            mapped, _ = cl.enqueue_map_buffer(
                queue,
                buf,
                map_flag,
                0,
                (nbytes,),
                np.uint8,
                is_blocking=True,
            )
            try:
                np.copyto(mapped, contig.view(np.uint8).ravel())
            finally:
                try:
                    mapped.base.release(queue)
                except Exception:
                    mapped.base.release()
            return buf
        except Exception:
            cl.enqueue_copy(queue, buf, contig)
            return buf

    def read_output(self, queue: "cl.CommandQueue", buf: "cl.Buffer", out_arr: np.ndarray) -> np.ndarray:
        """Read results from an OpenCL buffer into `out_arr` via spec-compliant map/unmap."""
        nbytes = int(out_arr.nbytes)
        if nbytes == 0:
            queue.finish()
            return out_arr
        try:
            mapped, _ = cl.enqueue_map_buffer(
                queue,
                buf,
                cl.map_flags.READ,
                0,
                (nbytes,),
                np.uint8,
                is_blocking=True,
            )
            try:
                np.copyto(out_arr.view(np.uint8).ravel(), mapped)
            finally:
                try:
                    mapped.base.release(queue)
                except Exception:
                    mapped.base.release()
            return out_arr
        except Exception:
            cl.enqueue_copy(queue, out_arr, buf).wait()
            return out_arr

    def get_stats(self) -> Dict[str, float]:
        with self._lock:
            return {
                "shared_mode": self.shared_mode,
                "allocated_mb": round(self.allocated_bytes / (1024.0 * 1024.0), 2),
                "peak_shared_mb": round(self.peak_allocated_bytes / (1024.0 * 1024.0), 2),
                "vram_scratch_mb": round(self.vram_allocated_bytes / (1024.0 * 1024.0), 2),
                "peak_vram_scratch_mb": round(self.peak_vram_allocated_bytes / (1024.0 * 1024.0), 2),
                "max_shared_mb": round(self.max_shared_bytes / (1024.0 * 1024.0), 2),
                "max_single_alloc_mb": round(self.max_single_alloc_bytes / (1024.0 * 1024.0), 2),
                "vram_budget_mb": round(self.vram_scratch_budget / (1024.0 * 1024.0), 2),
                "slot_count": len(self._slots),
            }

    def _evict_vram_unlocked(self) -> None:
        for slot_name in [k for k, (_, _, is_shared) in self._slots.items() if not is_shared]:
            self._release_slot_unlocked(slot_name)

    def _evict_unlocked(self, shared_only: bool = False) -> None:
        keys = [k for k, (_, _, is_shared) in self._slots.items() if (not shared_only or is_shared)]
        for slot_name in keys:
            self._release_slot_unlocked(slot_name)
        if not shared_only:
            self._slots.clear()
            self.allocated_bytes = 0
            self.vram_allocated_bytes = 0

    def release(self) -> int:
        """Deterministically drain queues and release all Shared RAM & VRAM `cl.Buffer` slots."""
        with self._lock:
            count = len(self._slots)
            self._drain_queues_unlocked()
            self._evict_unlocked(shared_only=False)
            self._queues_ref = None
            self.device = None
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
# OpenCL 3D NDRange Multi-Queue Mathematical Accelerator (`v1.0.23`)
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
        ensure_pyopencl()
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

        # Create 4 independent CommandQueues to stripe work across hardware compute engines (Compute 0..3)
        q_count = max(1, min(int(num_queues), 8))
        self.queues: List["cl.CommandQueue"] = [cl.CommandQueue(ctx, device=device) for _ in range(q_count)]
        self.queue: Optional["cl.CommandQueue"] = self.queues[0]
        self._q_idx = 0
        self._lock = threading.Lock()
        self._released = False
        self.total_dispatches = 0
        self.total_slices_processed = 0

        self.shared_arena: Optional[SharedHostMemoryArena] = SharedHostMemoryArena(
            ctx, max_shared_mb=arena_mb, device=device, queues=self.queues
        )

        # Compile 3D NDRange OpenCL C program once with fast-relaxed-math (suppress Intel OpenCL CompilerWarning)
        with warnings.catch_warnings():
            if hasattr(cl, "CompilerWarning"):
                warnings.filterwarnings("ignore", category=cl.CompilerWarning)
            self.program: Optional["cl.Program"] = cl.Program(ctx, OPENCL_MATH_KERNELS_SOURCE).build(
                options=["-cl-fast-relaxed-math", "-cl-mad-enable"]
            )
        # Cache kernel handles once so repeated attribute access on `self.program.<kernel>` never leaks
        self._k_srgb_3d = cl.Kernel(self.program, "srgb_to_linear_gamma_3d_kernel")
        self._k_sdf_smoothstep_3d = cl.Kernel(self.program, "sdf_valve_smoothstep_3d_kernel")
        self._k_msdf_median3_3d = cl.Kernel(self.program, "msdf_median3_reconstruct_3d_kernel")
        self._k_adf_biquad_3d = cl.Kernel(self.program, "adf_biquadratic_9pt_3d_kernel")
        self._k_otsu_hist_3d = cl.Kernel(self.program, "compute_histogram_local_atomic_3d")
        self._k_jfa_init_3d = cl.Kernel(self.program, "jfa_init_marching_seeds_3d_kernel")
        self._k_jfa_step_3d = cl.Kernel(self.program, "jfa_flood_step_3d_kernel")
        self._k_jfa_ms_recon_3d = cl.Kernel(self.program, "jfa_marching_squares_reconstruct_3d_kernel")
        self._k_touch_pages = cl.Kernel(self.program, "touch_shared_pages_3d_kernel")
        self._k_jfa_bnd_init = cl.Kernel(self.program, "jfa_boundary_init_short2_3d_kernel")
        self._k_jfa_step_s2 = cl.Kernel(self.program, "jfa_step_short2_3d_kernel")
        self._k_jfa_s2_sdf = cl.Kernel(self.program, "jfa_short2_to_sdf_3d_kernel")
        self._k_otsu_batch_3d = cl.Kernel(self.program, "otsu_hist_batch_3d_kernel")
        self._k_binarize_3d = cl.Kernel(self.program, "binarize_u8_3d_kernel")
        self._k_median_blur_3d = cl.Kernel(self.program, "median_blur_3d_kernel")
        self._k_morph_dilate_3d = cl.Kernel(self.program, "morph_dilate_dir_3d_kernel")
        self._k_morph_erode_3d = cl.Kernel(self.program, "morph_erode_dir_3d_kernel")
        self._k_combine_max_3d = cl.Kernel(self.program, "combine_max_u8_3d_kernel")
        self._k_mdf_recon_3d = cl.Kernel(self.program, "mdf_reconstruct_3d_kernel")
        self._k_msdf_down_3d = cl.Kernel(self.program, "msdf_downsample_rgb_3d_kernel")

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

    def _effective_local_2d1(self) -> Tuple[int, int, int]:
        if self.max_wg_size >= 256:
            return (16, 16, 1)
        if self.max_wg_size >= 64:
            return (8, 8, 1)
        return (4, 4, 1)

    def _round_global_2d1(self, w: int, h: int, z: int) -> Tuple[int, int, int]:
        lx, ly, _ = self._effective_local_2d1()
        gw = ((max(1, w) + lx - 1) // lx) * lx
        gh = ((max(1, h) + ly - 1) // ly) * ly
        return (gw, gh, max(1, z))

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

    def get_telemetry(self) -> Dict[str, Any]:
        arena_stats = self.shared_arena.get_stats() if self.shared_arena is not None else {}
        return {
            "device_name": self.device_name,
            "compute_units": self.compute_units,
            "num_queues": len(self.queues),
            "total_dispatches": self.total_dispatches,
            "total_slices_processed": self.total_slices_processed,
            **arena_stats,
        }

    def release(self) -> None:
        """
        Deterministically flush/finish all queues and release all OpenCL buffers, kernels,
        programs, queues, and context handles so 0 MB of GPU/Shared RAM remains allocated.
        """
        with self._lock:
            if self._released:
                return
            self._released = True

            for q in self.queues:
                try:
                    q.flush()
                    q.finish()
                except Exception:
                    pass

            if self.shared_arena is not None:
                try:
                    self.shared_arena.release()
                except Exception:
                    pass
                self.shared_arena = None

            for k_attr in (
                "_k_srgb_3d",
                "_k_sdf_smoothstep_3d",
                "_k_msdf_median3_3d",
                "_k_adf_biquad_3d",
                "_k_otsu_hist_3d",
                "_k_jfa_init_3d",
                "_k_jfa_step_3d",
                "_k_jfa_ms_recon_3d",
                "_k_touch_pages",
                "_k_jfa_bnd_init",
                "_k_jfa_step_s2",
                "_k_jfa_s2_sdf",
                "_k_otsu_batch_3d",
                "_k_binarize_3d",
                "_k_median_blur_3d",
                "_k_morph_dilate_3d",
                "_k_morph_erode_3d",
                "_k_combine_max_3d",
                "_k_mdf_recon_3d",
                "_k_msdf_down_3d",
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
        gc.collect()

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
        msdf_rgb_or_r: np.ndarray,
        sdf_g: Optional[np.ndarray] = None,
        sdf_b: Optional[np.ndarray] = None,
        threshold: int = 128,
        edge_offset_px: float = 0.0,
    ) -> Tuple[np.ndarray, np.ndarray]:
        assert self.shared_arena is not None
        if sdf_g is not None and sdf_b is not None:
            r_arr, g_arr, b_arr = msdf_rgb_or_r, sdf_g, sdf_b
        elif msdf_rgb_or_r.ndim >= 3 and msdf_rgb_or_r.shape[-1] == 3:
            r_arr = msdf_rgb_or_r[..., 0]
            g_arr = msdf_rgb_or_r[..., 1]
            b_arr = msdf_rgb_or_r[..., 2]
        else:
            raise ValueError("eval_msdf_median3_reconstruct requires 3 channels")

        if r_arr.ndim == 2:
            batch_z = 1
            target_h, target_w = r_arr.shape
        else:
            batch_z, target_h, target_w = r_arr.shape

        eff_t = int(np.clip(threshold if threshold > 0 else 128, 1, 254))
        if np.issubdtype(msdf_rgb_or_r.dtype, np.integer):
            r_f = np.ascontiguousarray((r_arr.astype(np.float32) - 128.0) / 64.0)
            g_f = np.ascontiguousarray((g_arr.astype(np.float32) - 128.0) / 64.0)
            b_f = np.ascontiguousarray((b_arr.astype(np.float32) - 128.0) / 64.0)
        else:
            r_f = np.ascontiguousarray(r_arr.astype(np.float32))
            g_f = np.ascontiguousarray(g_arr.astype(np.float32))
            b_f = np.ascontiguousarray(b_arr.astype(np.float32))

        bias_px = np.float32((128.0 - float(eff_t)) / 64.0 + float(edge_offset_px))
        out_bytes = int(batch_z * target_h * target_w)

        q = self._next_queue()
        r_buf = self.shared_arena.stage_input(q, "msdf_r_in", r_f)
        g_buf = self.shared_arena.stage_input(q, "msdf_g_in", g_f)
        b_buf = self.shared_arena.stage_input(q, "msdf_b_in", b_f)
        bw_buf = self.shared_arena.get_pinned_buffer("msdf_bw_out", out_bytes)
        fld_buf = self.shared_arena.get_pinned_buffer("msdf_fld_out", out_bytes)

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
            fld_buf,
            np.int32(target_w),
            np.int32(target_h),
            np.int32(batch_z),
            bias_px,
        )
        out_shape = (target_h, target_w) if r_arr.ndim == 2 else (batch_z, target_h, target_w)
        bilevel = np.empty(out_shape, dtype=np.uint8)
        field_u8 = np.empty(out_shape, dtype=np.uint8)
        self.shared_arena.read_output(q, bw_buf, bilevel)
        self.shared_arena.read_output(q, fld_buf, field_u8)
        return bilevel, field_u8

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
        ping_buf = self.shared_arena.get_scratch_buffer("jfa_seeds_ping", seed_bytes)
        pong_buf = self.shared_arena.get_scratch_buffer("jfa_seeds_pong", seed_bytes)
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
        self.total_dispatches += 1
        self.total_slices_processed += batch_z

        out_shape = (target_h, target_w) if high_gray.ndim == 2 else (batch_z, target_h, target_w)
        bilevel = np.empty(out_shape, dtype=np.uint8)
        field_u8 = np.empty(out_shape, dtype=np.uint8)
        self.shared_arena.read_output(q, bw_buf, bilevel)
        self.shared_arena.read_output(q, fld_buf, field_u8)
        return bilevel, field_u8

    # -----------------------------------------------------------------------
    # 8. 3D Coalesced short2 1+JFA Helper, Median Blur & Directional Morphology
    # -----------------------------------------------------------------------
    def _run_jfa_short2_sdf_on_device(
        self,
        q: "cl.CommandQueue",
        gray_or_mask_buf: "cl.Buffer",
        out_sdf_buf: "cl.Buffer",
        hi_w: int,
        hi_h: int,
        batch_z: int,
        upscale: int,
        thresh_u8: int,
        slot_prefix: str = "jfa_s2",
    ) -> None:
        assert self.shared_arena is not None
        seed_bytes = int(batch_z * hi_h * hi_w * 4)
        ping_buf = self.shared_arena.get_scratch_buffer(f"{slot_prefix}_ping", seed_bytes)
        pong_buf = self.shared_arena.get_scratch_buffer(f"{slot_prefix}_pong", seed_bytes)

        loc = self._effective_local_2d1()
        glob = self._round_global_2d1(hi_w, hi_h, batch_z)
        self._k_jfa_bnd_init(
            q,
            glob,
            loc,
            gray_or_mask_buf,
            ping_buf,
            np.int32(hi_w),
            np.int32(hi_h),
            np.int32(batch_z),
            np.uint8(thresh_u8),
        )

        band = max(32, 4 * int(upscale))
        top_pow2 = 1 << max(0, int(math.ceil(math.log2(band))))
        steps: List[int] = [1]
        s = top_pow2
        while s >= 1:
            steps.append(s)
            s //= 2

        src_s, dst_s = ping_buf, pong_buf
        for step_k in steps:
            self._k_jfa_step_s2(
                q,
                glob,
                loc,
                src_s,
                dst_s,
                np.int32(hi_w),
                np.int32(hi_h),
                np.int32(batch_z),
                np.int32(step_k),
            )
            src_s, dst_s = dst_s, src_s

        self._k_jfa_s2_sdf(
            q,
            glob,
            loc,
            gray_or_mask_buf,
            src_s,
            out_sdf_buf,
            np.int32(hi_w),
            np.int32(hi_h),
            np.int32(batch_z),
            np.uint8(thresh_u8),
            np.float32(1.0 / float(max(1, upscale))),
        )

    def eval_median_blur(self, arr: np.ndarray, ksize: int) -> np.ndarray:
        if arr is None or arr.size == 0 or ksize <= 1 or self.shared_arena is None or self._released:
            return arr
        if ksize > 5:
            import cv2
            return cv2.medianBlur(arr, ksize)
        u8 = np.ascontiguousarray(arr.astype(np.uint8))
        if u8.ndim == 2:
            batch_z = 1
            h, w = u8.shape
            out_shape: Tuple[int, ...] = (h, w)
        else:
            batch_z, h, w = u8.shape
            out_shape = (batch_z, h, w)
        radius = 1 if ksize <= 3 else 2
        q = self._next_queue()
        src_buf = self.shared_arena.stage_input(q, "med_in", u8)
        dst_buf = self.shared_arena.get_pinned_buffer("med_out", int(u8.nbytes))
        loc = self._effective_local_2d1()
        glob = self._round_global_2d1(w, h, batch_z)
        self._k_median_blur_3d(q, glob, loc, src_buf, dst_buf, np.int32(w), np.int32(h), np.int32(batch_z), np.int32(radius))
        self.total_dispatches += 1
        self.total_slices_processed += batch_z
        out = np.empty(out_shape, dtype=np.uint8)
        return self.shared_arena.read_output(q, dst_buf, out)

    def eval_morphology_close(self, arr: np.ndarray, kernel: np.ndarray) -> np.ndarray:
        if arr is None or arr.size == 0 or self.shared_arena is None or self._released:
            return arr
        kh, kw = kernel.shape[:2]
        is_horiz = (kh == 1 and kw >= 2 and bool(np.all(kernel > 0)))
        is_vert = (kw == 1 and kh >= 2 and bool(np.all(kernel > 0)))
        if not (is_horiz or is_vert):
            import cv2
            return cv2.morphologyEx(arr, cv2.MORPH_CLOSE, kernel)

        u8 = np.ascontiguousarray(arr.astype(np.uint8))
        if u8.ndim == 2:
            batch_z = 1
            h, w = u8.shape
            out_shape: Tuple[int, ...] = (h, w)
        else:
            batch_z, h, w = u8.shape
            out_shape = (batch_z, h, w)
        k_span = kw if is_horiz else kh
        dx, dy = (1, 0) if is_horiz else (0, 1)
        r_neg = k_span // 2
        r_pos = k_span - 1 - r_neg

        q = self._next_queue()
        src_buf = self.shared_arena.stage_input(q, "morph_in", u8)
        tmp_buf = self.shared_arena.get_scratch_buffer("morph_tmp", int(u8.nbytes))
        dst_buf = self.shared_arena.get_pinned_buffer("morph_out", int(u8.nbytes))
        loc = self._effective_local_2d1()
        glob = self._round_global_2d1(w, h, batch_z)
        self._k_morph_dilate_3d(
            q, glob, loc, src_buf, tmp_buf, np.int32(w), np.int32(h), np.int32(batch_z),
            np.int32(dx), np.int32(dy), np.int32(r_neg), np.int32(r_pos),
        )
        self._k_morph_erode_3d(
            q, glob, loc, tmp_buf, dst_buf, np.int32(w), np.int32(h), np.int32(batch_z),
            np.int32(dx), np.int32(dy), np.int32(r_pos), np.int32(r_neg),
        )
        self.total_dispatches += 1
        self.total_slices_processed += batch_z
        out = np.empty(out_shape, dtype=np.uint8)
        return self.shared_arena.read_output(q, dst_buf, out)

    # -----------------------------------------------------------------------
    # 9. Full 3D NDRange Batched Strike Pipeline Execution
    # -----------------------------------------------------------------------
    def eval_pipeline_batch_3d(
        self,
        pipeline: str,
        raw_batch_u8: np.ndarray,
        glyph_dims: np.ndarray,
        target_w: int,
        target_h: int,
        upscale: int = 1,
        threshold: int = 128,
        gamma: float = 1.0,
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """
        Execute an entire glyph strike as a single 3D `(batch_z, H, W)` OpenCL GPU batch
        (automatically chunked across `Compute 0..3` to honor `max_mem_alloc_size` and the
        75% WDDM Shared GPU Memory cap).

        Returns `(bilevel_batch, aux_lin_gray_batch)`:
          - `raw-unhinted`, `raw-hinted`, `otsu-adaptive`, `sdf-smoothstep`,
            `adf-biquadratic`, `mdf`, `msdf`: `(bilevel_u8[B, target_h, target_w], None)`
          - `svg-potrace`: `(None, lin_gray_u8[B, H, W])`
          - `svg-potrace-jfa`: `(bilevel_u8[B, target_h, target_w], lin_gray_u8[B, H, W])`
        """
        assert self.shared_arena is not None
        if raw_batch_u8 is None or raw_batch_u8.size == 0:
            empty_bw = np.zeros((0, max(1, target_h), max(1, target_w)), dtype=np.uint8)
            return empty_bw, None

        B, H, W = raw_batch_u8.shape
        eff_t = int(np.clip(threshold if threshold > 0 else 128, 1, 254))
        eff_gamma = float(np.clip(gamma if gamma > 0 else 1.0, 0.1, 5.0))
        inv_gamma = np.float32(1.0 / eff_gamma)
        bias_px = np.float32((128.0 - float(eff_t)) / 64.0)

        if pipeline in ("mdf", "msdf"):
            bytes_per_px_equiv = 24
        elif pipeline in ("sdf-smoothstep", "adf-biquadratic", "svg-potrace-jfa"):
            bytes_per_px_equiv = 16
        else:
            bytes_per_px_equiv = 4

        max_chunk_z = self.shared_arena.compute_max_batch_z(W * H, bytes_per_px_equiv, B)
        out_bw: Optional[np.ndarray] = (
            None if pipeline == "svg-potrace" else np.empty((B, target_h, target_w), dtype=np.uint8)
        )
        out_aux: Optional[np.ndarray] = (
            np.empty((B, H, W), dtype=np.uint8) if pipeline in ("svg-potrace", "svg-potrace-jfa") else None
        )

        loc_2d1 = self._effective_local_2d1()
        for z0 in range(0, B, max_chunk_z):
            z1 = min(B, z0 + max_chunk_z)
            cz = z1 - z0
            q = self._next_queue()

            chunk_u8 = np.ascontiguousarray(raw_batch_u8[z0:z1], dtype=np.uint8)
            n_hi_px = int(cz * H * W)
            n_lo_px = int(cz * target_h * target_w)

            src_buf = self.shared_arena.stage_input(q, "b3d_raw_in", chunk_u8)
            need_lin_readback = pipeline in ("otsu-adaptive", "svg-potrace", "svg-potrace-jfa")
            lin_buf = (
                self.shared_arena.get_pinned_buffer("b3d_lin_pin", n_hi_px)
                if need_lin_readback
                else self.shared_arena.get_scratch_buffer("b3d_lin_scr", n_hi_px)
            )
            loc_hi_3d = self._effective_local_3d(cz)
            glob_hi_3d = self._round_global_3d(W, H, cz)
            self._k_srgb_3d(
                q,
                glob_hi_3d,
                loc_hi_3d,
                src_buf,
                lin_buf,
                np.int32(W),
                np.int32(H),
                np.int32(cz),
                np.int32(n_hi_px),
                np.int32(1),
                inv_gamma,
            )

            glob_hi_2d1 = self._round_global_2d1(W, H, cz)
            loc_lo_3d = self._effective_local_3d(cz)
            glob_lo_3d = self._round_global_3d(target_w, target_h, cz)

            if pipeline in ("raw-unhinted", "raw-hinted"):
                bw_buf = self.shared_arena.get_pinned_buffer("b3d_bw_out", n_lo_px)
                self._k_binarize_3d(
                    q, glob_hi_2d1, loc_2d1, lin_buf, bw_buf,
                    np.int32(W), np.int32(H), np.int32(cz), np.uint8(eff_t),
                )
                assert out_bw is not None
                self.shared_arena.read_output(q, bw_buf, out_bw[z0:z1])

            elif pipeline == "otsu-adaptive":
                dims_i32 = np.ascontiguousarray(glyph_dims[z0:z1], dtype=np.int32)
                dims_buf = self.shared_arena.stage_input(q, "b3d_dims_in", dims_i32)
                hist_zeros = np.zeros((cz, 256), dtype=np.uint32)
                hist_buf = self.shared_arena.stage_input(q, "b3d_otsu_hists", hist_zeros)
                self._k_otsu_batch_3d(
                    q, glob_hi_2d1, loc_2d1, lin_buf, dims_buf, hist_buf,
                    np.int32(W), np.int32(H), np.int32(cz),
                )
                hists = np.empty((cz, 256), dtype=np.uint32)
                lin_chunk = np.empty((cz, H, W), dtype=np.uint8)
                self.shared_arena.read_output(q, hist_buf, hists)
                self.shared_arena.read_output(q, lin_buf, lin_chunk)

                bins_f = np.arange(256, dtype=np.float64)
                user_offset = int(eff_t) - 128
                assert out_bw is not None
                for i in range(cz):
                    gw_i = int(dims_i32[i, 0])
                    gh_i = int(dims_i32[i, 1])
                    h_vec = hists[i]
                    tot = float(np.sum(h_vec))
                    if gw_i * gh_i < 64 or tot < 6.0:
                        use_t = eff_t
                    else:
                        p = h_vec.astype(np.float64) / tot
                        omega = np.cumsum(p)
                        mu = np.cumsum(p * bins_f)
                        mu_t = mu[-1]
                        denom = omega * (1.0 - omega)
                        valid = denom > 1e-9
                        sigma_b = np.zeros(256, dtype=np.float64)
                        sigma_b[valid] = ((mu_t * omega[valid] - mu[valid]) ** 2) / denom[valid]
                        k_star = int(np.argmax(sigma_b))
                        use_t = int(np.clip(round(0.70 * k_star + 0.30 * 128 + user_offset), 72, 184))
                    out_bw[z0 + i] = (lin_chunk[i] >= use_t).astype(np.uint8)

            elif pipeline == "svg-potrace":
                assert out_aux is not None
                self.shared_arena.read_output(q, lin_buf, out_aux[z0:z1])

            elif pipeline == "svg-potrace-jfa":
                iso_thresh = np.float32(float(eff_t))
                ping_buf = self.shared_arena.get_scratch_buffer("b3d_jfa_f2_ping", n_hi_px * 8)
                pong_buf = self.shared_arena.get_scratch_buffer("b3d_jfa_f2_pong", n_hi_px * 8)
                bw_buf = self.shared_arena.get_pinned_buffer("b3d_bw_out", n_lo_px)
                fld_buf = self.shared_arena.get_scratch_buffer("b3d_fld_scr", n_lo_px)

                self._k_jfa_init_3d(
                    q, glob_hi_3d, loc_hi_3d, lin_buf, ping_buf,
                    np.int32(W), np.int32(H), np.int32(cz), iso_thresh,
                )
                max_dim = max(W, H, 2)
                top_pow2 = 1 << max(0, int(math.ceil(math.log2(max_dim))) - 1)
                steps: List[int] = [1]
                s = top_pow2
                while s >= 1:
                    steps.append(s)
                    s //= 2
                src_s, dst_s = ping_buf, pong_buf
                for step_k in steps:
                    self._k_jfa_step_3d(
                        q, glob_hi_3d, loc_hi_3d, src_s, dst_s,
                        np.int32(W), np.int32(H), np.int32(cz), np.int32(step_k),
                    )
                    src_s, dst_s = dst_s, src_s

                self._k_jfa_ms_recon_3d(
                    q, glob_lo_3d, loc_lo_3d, lin_buf, src_s, bw_buf, fld_buf,
                    np.int32(W), np.int32(H), np.int32(target_w), np.int32(target_h),
                    np.int32(cz), np.int32(upscale), iso_thresh, bias_px,
                )
                assert out_bw is not None and out_aux is not None
                self.shared_arena.read_output(q, bw_buf, out_bw[z0:z1])
                self.shared_arena.read_output(q, lin_buf, out_aux[z0:z1])

            elif pipeline == "sdf-smoothstep":
                sdf_buf = self.shared_arena.get_scratch_buffer("b3d_sdf_0", n_hi_px * 4)
                self._run_jfa_short2_sdf_on_device(q, lin_buf, sdf_buf, W, H, cz, upscale, 128, "b3d_jfa_s2")
                bw_buf = self.shared_arena.get_pinned_buffer("b3d_bw_out", n_lo_px)
                fld_buf = self.shared_arena.get_scratch_buffer("b3d_fld_scr", n_lo_px)
                self._k_sdf_smoothstep_3d(
                    q, glob_lo_3d, loc_lo_3d, sdf_buf, bw_buf, fld_buf,
                    np.int32(W), np.int32(H), np.int32(target_w), np.int32(target_h),
                    np.int32(cz), np.int32(upscale), bias_px,
                )
                assert out_bw is not None
                self.shared_arena.read_output(q, bw_buf, out_bw[z0:z1])

            elif pipeline == "adf-biquadratic":
                sdf_buf = self.shared_arena.get_scratch_buffer("b3d_sdf_0", n_hi_px * 4)
                self._run_jfa_short2_sdf_on_device(q, lin_buf, sdf_buf, W, H, cz, upscale, 128, "b3d_jfa_s2")
                bw_buf = self.shared_arena.get_pinned_buffer("b3d_bw_out", n_lo_px)
                fld_buf = self.shared_arena.get_scratch_buffer("b3d_fld_scr", n_lo_px)
                self._k_adf_biquad_3d(
                    q, glob_lo_3d, loc_lo_3d, sdf_buf, bw_buf, fld_buf,
                    np.int32(W), np.int32(H), np.int32(target_w), np.int32(target_h),
                    np.int32(cz), np.int32(upscale), bias_px,
                )
                assert out_bw is not None
                self.shared_arena.read_output(q, bw_buf, out_bw[z0:z1])

            elif pipeline == "mdf":
                k_rad = 1 if upscale < 10 else 2
                med_buf = self.shared_arena.get_scratch_buffer("b3d_med", n_hi_px)
                fg_buf = self.shared_arena.get_scratch_buffer("b3d_fg", n_hi_px)
                tmp_buf = self.shared_arena.get_scratch_buffer("b3d_tmp", n_hi_px)
                fg_h_buf = self.shared_arena.get_scratch_buffer("b3d_fgh", n_hi_px)
                fg_v_buf = self.shared_arena.get_scratch_buffer("b3d_fgv", n_hi_px)

                self._k_median_blur_3d(
                    q, glob_hi_2d1, loc_2d1, lin_buf, med_buf,
                    np.int32(W), np.int32(H), np.int32(cz), np.int32(k_rad),
                )
                self._k_binarize_3d(
                    q, glob_hi_2d1, loc_2d1, med_buf, fg_buf,
                    np.int32(W), np.int32(H), np.int32(cz), np.uint8(128),
                )

                k_span = max(3, upscale // 3)
                r_neg = k_span // 2
                r_pos = k_span - 1 - r_neg
                self._k_morph_dilate_3d(
                    q, glob_hi_2d1, loc_2d1, fg_buf, tmp_buf,
                    np.int32(W), np.int32(H), np.int32(cz),
                    np.int32(1), np.int32(0), np.int32(r_neg), np.int32(r_pos),
                )
                self._k_morph_erode_3d(
                    q, glob_hi_2d1, loc_2d1, tmp_buf, fg_h_buf,
                    np.int32(W), np.int32(H), np.int32(cz),
                    np.int32(1), np.int32(0), np.int32(r_pos), np.int32(r_neg),
                )
                self._k_morph_dilate_3d(
                    q, glob_hi_2d1, loc_2d1, fg_buf, tmp_buf,
                    np.int32(W), np.int32(H), np.int32(cz),
                    np.int32(0), np.int32(1), np.int32(r_neg), np.int32(r_pos),
                )
                self._k_morph_erode_3d(
                    q, glob_hi_2d1, loc_2d1, tmp_buf, fg_v_buf,
                    np.int32(W), np.int32(H), np.int32(cz),
                    np.int32(0), np.int32(1), np.int32(r_pos), np.int32(r_neg),
                )

                sdf_iso_buf = self.shared_arena.get_scratch_buffer("b3d_sdf_0", n_hi_px * 4)
                sdf_h_buf = self.shared_arena.get_scratch_buffer("b3d_sdf_1", n_hi_px * 4)
                sdf_v_buf = self.shared_arena.get_scratch_buffer("b3d_sdf_2", n_hi_px * 4)
                self._run_jfa_short2_sdf_on_device(q, fg_buf, sdf_iso_buf, W, H, cz, upscale, 1, "b3d_jfa_s2")
                self._run_jfa_short2_sdf_on_device(q, fg_h_buf, sdf_h_buf, W, H, cz, upscale, 1, "b3d_jfa_s2")
                self._run_jfa_short2_sdf_on_device(q, fg_v_buf, sdf_v_buf, W, H, cz, upscale, 1, "b3d_jfa_s2")

                bw_buf = self.shared_arena.get_pinned_buffer("b3d_bw_out", n_lo_px)
                fld_buf = self.shared_arena.get_scratch_buffer("b3d_fld_scr", n_lo_px)
                self._k_mdf_recon_3d(
                    q, glob_lo_3d, loc_lo_3d, sdf_iso_buf, sdf_h_buf, sdf_v_buf, bw_buf, fld_buf,
                    np.int32(W), np.int32(H), np.int32(target_w), np.int32(target_h),
                    np.int32(cz), np.int32(upscale), np.int32(eff_t),
                )
                assert out_bw is not None
                self.shared_arena.read_output(q, bw_buf, out_bw[z0:z1])

            elif pipeline == "msdf":
                fg_buf = self.shared_arena.get_scratch_buffer("b3d_fg", n_hi_px)
                tmp_buf = self.shared_arena.get_scratch_buffer("b3d_tmp", n_hi_px)
                diag_buf = self.shared_arena.get_scratch_buffer("b3d_diag", n_hi_px)
                mask_r_buf = self.shared_arena.get_scratch_buffer("b3d_msdf_mr", n_hi_px)
                mask_g_buf = self.shared_arena.get_scratch_buffer("b3d_msdf_mg", n_hi_px)

                self._k_binarize_3d(
                    q, glob_hi_2d1, loc_2d1, lin_buf, fg_buf,
                    np.int32(W), np.int32(H), np.int32(cz), np.uint8(128),
                )
                k_span = max(3, upscale // 3)
                r_neg = k_span // 2
                r_pos = k_span - 1 - r_neg

                # Channel R = max(close(horiz), close(diag1))
                self._k_morph_dilate_3d(
                    q, glob_hi_2d1, loc_2d1, fg_buf, tmp_buf,
                    np.int32(W), np.int32(H), np.int32(cz),
                    np.int32(1), np.int32(0), np.int32(r_neg), np.int32(r_pos),
                )
                self._k_morph_erode_3d(
                    q, glob_hi_2d1, loc_2d1, tmp_buf, mask_r_buf,
                    np.int32(W), np.int32(H), np.int32(cz),
                    np.int32(1), np.int32(0), np.int32(r_pos), np.int32(r_neg),
                )
                self._k_morph_dilate_3d(
                    q, glob_hi_2d1, loc_2d1, fg_buf, tmp_buf,
                    np.int32(W), np.int32(H), np.int32(cz),
                    np.int32(1), np.int32(1), np.int32(r_neg), np.int32(r_pos),
                )
                self._k_morph_erode_3d(
                    q, glob_hi_2d1, loc_2d1, tmp_buf, diag_buf,
                    np.int32(W), np.int32(H), np.int32(cz),
                    np.int32(1), np.int32(1), np.int32(r_pos), np.int32(r_neg),
                )
                self._k_combine_max_3d(
                    q, glob_hi_2d1, loc_2d1, mask_r_buf, diag_buf, mask_r_buf,
                    np.int32(W), np.int32(H), np.int32(cz),
                )

                # Channel G = max(close(vert), close(diag2))
                self._k_morph_dilate_3d(
                    q, glob_hi_2d1, loc_2d1, fg_buf, tmp_buf,
                    np.int32(W), np.int32(H), np.int32(cz),
                    np.int32(0), np.int32(1), np.int32(r_neg), np.int32(r_pos),
                )
                self._k_morph_erode_3d(
                    q, glob_hi_2d1, loc_2d1, tmp_buf, mask_g_buf,
                    np.int32(W), np.int32(H), np.int32(cz),
                    np.int32(0), np.int32(1), np.int32(r_pos), np.int32(r_neg),
                )
                self._k_morph_dilate_3d(
                    q, glob_hi_2d1, loc_2d1, fg_buf, tmp_buf,
                    np.int32(W), np.int32(H), np.int32(cz),
                    np.int32(-1), np.int32(1), np.int32(r_neg), np.int32(r_pos),
                )
                self._k_morph_erode_3d(
                    q, glob_hi_2d1, loc_2d1, tmp_buf, diag_buf,
                    np.int32(W), np.int32(H), np.int32(cz),
                    np.int32(-1), np.int32(1), np.int32(r_pos), np.int32(r_neg),
                )
                self._k_combine_max_3d(
                    q, glob_hi_2d1, loc_2d1, mask_g_buf, diag_buf, mask_g_buf,
                    np.int32(W), np.int32(H), np.int32(cz),
                )

                sdf_iso_buf = self.shared_arena.get_scratch_buffer("b3d_sdf_0", n_hi_px * 4)
                sdf_r_buf = self.shared_arena.get_scratch_buffer("b3d_sdf_1", n_hi_px * 4)
                sdf_g_buf = self.shared_arena.get_scratch_buffer("b3d_sdf_2", n_hi_px * 4)
                self._run_jfa_short2_sdf_on_device(q, fg_buf, sdf_iso_buf, W, H, cz, upscale, 1, "b3d_jfa_s2")
                self._run_jfa_short2_sdf_on_device(q, mask_r_buf, sdf_r_buf, W, H, cz, upscale, 1, "b3d_jfa_s2")
                self._run_jfa_short2_sdf_on_device(q, mask_g_buf, sdf_g_buf, W, H, cz, upscale, 1, "b3d_jfa_s2")

                low_r_buf = self.shared_arena.get_scratch_buffer("b3d_msdf_lr", n_lo_px * 4)
                low_g_buf = self.shared_arena.get_scratch_buffer("b3d_msdf_lg", n_lo_px * 4)
                low_b_buf = self.shared_arena.get_scratch_buffer("b3d_msdf_lb", n_lo_px * 4)
                self._k_msdf_down_3d(
                    q, glob_lo_3d, loc_lo_3d, lin_buf, sdf_iso_buf, sdf_r_buf, sdf_g_buf,
                    low_r_buf, low_g_buf, low_b_buf,
                    np.int32(W), np.int32(H), np.int32(target_w), np.int32(target_h),
                    np.int32(cz), np.int32(upscale),
                )

                bw_buf = self.shared_arena.get_pinned_buffer("b3d_bw_out", n_lo_px)
                fld_buf = self.shared_arena.get_scratch_buffer("b3d_fld_scr", n_lo_px)
                self._k_msdf_median3_3d(
                    q, glob_lo_3d, loc_lo_3d, low_r_buf, low_g_buf, low_b_buf, bw_buf, fld_buf,
                    np.int32(target_w), np.int32(target_h), np.int32(cz), bias_px,
                )
                assert out_bw is not None
                self.shared_arena.read_output(q, bw_buf, out_bw[z0:z1])
            else:
                raise ValueError(f"Unsupported batch pipeline '{pipeline}'")

            self.total_dispatches += 1
            self.total_slices_processed += cz

        return out_bw, out_aux

    # -----------------------------------------------------------------------
    # 10. WDDM Shared GPU Memory Stress & PDH Verification Utility
    # -----------------------------------------------------------------------
    @staticmethod
    def _query_wddm_gpu_process_memory_mb() -> Tuple[Optional[float], Optional[float]]:
        if os.name != "nt":
            return None, None
        pid = os.getpid()
        ps = (
            f"$ded = (Get-Counter '\\GPU Process Memory(pid_{pid}_*)\\Dedicated Usage' -ErrorAction SilentlyContinue).CounterSamples | "
            f"Measure-Object -Property CookedValue -Sum | Select-Object -ExpandProperty Sum; "
            f"$shr = (Get-Counter '\\GPU Process Memory(pid_{pid}_*)\\Shared Usage' -ErrorAction SilentlyContinue).CounterSamples | "
            f"Measure-Object -Property CookedValue -Sum | Select-Object -ExpandProperty Sum; "
            f"Write-Output (([math]::Round([double]$ded/1MB, 2)).ToString() + ',' + ([math]::Round([double]$shr/1MB, 2)).ToString())"
        )
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=10)
            parts = r.stdout.strip().split(",")
            if len(parts) == 2:
                return float(parts[0]), float(parts[1])
        except Exception:
            pass
        return None, None

    def touch_shared_memory_mb(self, target_mb: int, hold_seconds: float = 0.0) -> Dict[str, Any]:
        """
        Allocate `target_mb` in `CL_MEM_ALLOC_HOST_PTR` WDDM Shared GPU Memory chunks,
        touch every 4 KB page via `touch_shared_pages_3d_kernel`, optionally hold for
        Task Manager observation, query Windows PDH Dedicated vs Shared usage, and release cleanly.
        """
        assert self.shared_arena is not None and self.ctx is not None
        ensure_pyopencl()
        q = self._next_queue()
        q.finish()
        ded_before, shr_before = self._query_wddm_gpu_process_memory_mb()

        req_bytes = min(max(4, int(target_mb)) * 1024 * 1024, self.shared_arena.max_shared_bytes)
        chunk_cap = min(256 * 1024 * 1024, self.shared_arena.max_single_alloc_bytes)
        chunk_cap = max(4096, (chunk_cap // 4096) * 4096)

        bufs: List["cl.Buffer"] = []
        allocated = 0
        try:
            while allocated < req_bytes:
                sz = min(chunk_cap, req_bytes - allocated)
                sz = max(4096, ((sz + 4095) // 4096) * 4096)
                buf = cl.Buffer(self.ctx, cl.mem_flags.READ_WRITE | cl.mem_flags.ALLOC_HOST_PTR, size=sz)
                bufs.append(buf)
                n_pages = (sz + 4095) // 4096
                wg = min(256, max(1, self.max_wg_size))
                g_pages = ((n_pages + wg - 1) // wg) * wg
                self._k_touch_pages(q, (g_pages,), (wg,), buf, np.int64(sz))
                allocated += sz
            q.finish()
            ded_active, shr_active = self._query_wddm_gpu_process_memory_mb()
            if hold_seconds > 0:
                time.sleep(float(hold_seconds))
        finally:
            for b in bufs:
                try:
                    b.release()
                except Exception:
                    pass
            bufs.clear()
            q.finish()
            gc.collect()

        ded_after, shr_after = self._query_wddm_gpu_process_memory_mb()
        return {
            "requested_mb": int(target_mb),
            "allocated_mb": round(allocated / (1024.0 * 1024.0), 2),
            "dedicated_before_mb": ded_before,
            "shared_before_mb": shr_before,
            "dedicated_active_mb": ded_active,
            "shared_active_mb": shr_active,
            "dedicated_after_mb": ded_after,
            "shared_after_mb": shr_after,
        }


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
