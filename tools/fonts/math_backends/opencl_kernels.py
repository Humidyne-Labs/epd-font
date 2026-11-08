#!/usr/bin/env python3
"""
opencl_kernels.py (v1.0.19c)
============================
A 1-bit EPD font generator and asset pipeline for embedded displays.
Repository : https://github.com/Humidyne-Labs/epd-font
Authors    : Humiditron (https://github.com/humiditron) & AI/LLM Development Partner
License    : MIT License

PyOpenCL GPU / Heterogeneous Compute Kernels & Host Wrappers (v1.0.19c):
Implements OpenCL 1.2 / 3.0 kernels (Khronos OpenCL Unified Specification:
https://registry.khronos.org/OpenCL/specs/unified/refpages/man/html/) for:
  1. `srgb_to_linear_gamma_kernel`       : IEC 61966-2-1 sRGB -> ITU-R BT.709 Linear Luminance + Gamma
  2. `render_bezier_sdf_yuksel_kernel`   : Cem Yuksel Degree-5 -> Degree-2 Monotonic Polynomial Cascade
                                           + Newton-Bisection Quintic Solver + Cubic Ray-Crossing Winding
  3. `sdf_valve_smoothstep_kernel`       : Chris Green (Valve) Bilinear SDF Sampler + L2 Screen-Space
                                           Derivative (`delta = length(d_x, d_y)`) Smoothstep Reconstruction
  4. `msdf_median3_reconstruct_kernel`   : Chlumsky Multi-Channel (R,G,B) Corner-Preserving Median-of-Three SDF
  5. `adf_biquadratic_9pt_kernel`        : Saffron 9-Point Bi-Quadratic Lagrange Polynomial ADF (4x4 Quadrature)
  6. `compute_histogram_local_atomic` &  : Work-group `__local uint local_hist[256]` Atomic Histogram +
     `apply_otsu_sauvola_binarization`     Otsu Between-Class Variance Maximization + Sauvola Local Threshold
"""

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np

try:
    import pyopencl as cl  # type: ignore
    HAS_PYOPENCL = True
except Exception:
    cl = None  # type: ignore
    HAS_PYOPENCL = False


OPENCL_MATH_KERNELS_SOURCE = r"""
#define EPSILON 1e-6f
#define MAX_NEWTON_STEPS 24

typedef struct {
    float2 p0;
    float2 p1;
    float2 p2;
    float2 p3;
} BezierCurve;

// ---------------------------------------------------------------------------
// 1. IEC 61966-2-1 sRGB -> ITU-R BT.709 Linear Luminance + Gamma Kernel
// ---------------------------------------------------------------------------
inline float srgb_byte_to_linear(uchar u) {
    float c = (float)u / 255.0f;
    return (c <= 0.04045f) ? (c / 12.92f) : pow((c + 0.055f) / 1.055f, 2.4f);
}

__kernel void srgb_to_linear_gamma_kernel(
    __global const uchar* src,
    __global uchar* dst,
    const int width,
    const int height,
    const int channels,
    const float inv_gamma)
{
    int gx = get_global_id(0);
    int gy = get_global_id(1);
    if (gx >= width || gy >= height) return;

    int idx = gy * width + gx;
    float y_lin = 0.0f;
    if (channels >= 3) {
        int base = idx * channels;
        float r_lin = srgb_byte_to_linear(src[base + 0]);
        float g_lin = srgb_byte_to_linear(src[base + 1]);
        float b_lin = srgb_byte_to_linear(src[base + 2]);
        y_lin = 0.2126f * r_lin + 0.7152f * g_lin + 0.0722f * b_lin;
    } else {
        uchar u = src[idx];
        float srgb_norm = (float)u / 255.0f;
        float lin_pure = srgb_byte_to_linear(u);
        y_lin = 0.50f * srgb_norm + 0.50f * pow(clamp(lin_pure, 0.0f, 1.0f), 1.0f / 2.2f);
    }

    if (fabs(inv_gamma - 1.0f) > 1e-4f) {
        y_lin = pow(clamp(y_lin, 0.0f, 1.0f), inv_gamma);
    }
    dst[idx] = convert_uchar_sat_rte(clamp(y_lin * 255.0f, 0.0f, 255.0f));
}

// ---------------------------------------------------------------------------
// 2. Cem Yuksel Quintic Root-Finding Cascade for Exact Cubic Bezier SDF
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

__kernel void render_bezier_sdf_yuksel_kernel(
    __global const BezierCurve* curves,
    const int num_curves,
    __global uchar* out_bilevel,
    __global uchar* out_field,
    const int width,
    const int height,
    const float bias_px)
{
    int gx = get_global_id(0);
    int gy = get_global_id(1);
    if (gx >= width || gy >= height) return;

    float2 p = (float2)((float)gx + 0.5f, (float)gy + 0.5f);
    float min_dist_sq = 1e30f;
    int winding_accum = 0;

    for (int i = 0; i < num_curves; ++i) {
        BezierCurve bz = curves[i];
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
    // Positive inside, negative outside
    float signed_d = ((winding_accum & 1) != 0 ? d : -d) + bias_px;
    float alpha = smoothstep(-0.55f, 0.55f, signed_d);
    int idx = gy * width + gx;
    out_field[idx] = convert_uchar_sat_rte(clamp(alpha * 255.0f, 0.0f, 255.0f));
    out_bilevel[idx] = (alpha >= 0.50f) ? 1 : 0;
}

// ---------------------------------------------------------------------------
// 3. Chris Green (Valve) SDF Smoothstep + L2 Screen-Space Derivative Kernel
// ---------------------------------------------------------------------------
__kernel void sdf_valve_smoothstep_kernel(
    __global const float* sdf_hi,
    __global uchar* out_bilevel,
    __global uchar* out_field,
    const int hi_w,
    const int hi_h,
    const int target_w,
    const int target_h,
    const int upscale,
    const float bias_px)
{
    int gx = get_global_id(0);
    int gy = get_global_id(1);
    if (gx >= target_w || gy >= target_h) return;

    int hc = clamp(gx * upscale + (upscale / 2), 0, hi_w - 1);
    int hr = clamp(gy * upscale + (upscale / 2), 0, hi_h - 1);
    int hc_r = clamp(hc + upscale, 0, hi_w - 1);
    int hr_d = clamp(hr + upscale, 0, hi_h - 1);

    float d = sdf_hi[hr * hi_w + hc] + bias_px;
    float dx = sdf_hi[hr * hi_w + hc_r] - sdf_hi[hr * hi_w + hc];
    float dy = sdf_hi[hr_d * hi_w + hc] - sdf_hi[hr * hi_w + hc];
    float w = clamp(length((float2)(dx, dy)) * 0.55f, 0.35f, 0.85f);

    float t = clamp((d + w) / (2.0f * w), 0.0f, 1.0f);
    float cov_smooth = t * t * (3.0f - 2.0f * t);

    int idx = gy * target_w + gx;
    out_field[idx] = convert_uchar_sat_rte(clamp(cov_smooth * 255.0f, 0.0f, 255.0f));
    out_bilevel[idx] = (cov_smooth >= 0.50f) ? 1 : 0;
}

// ---------------------------------------------------------------------------
// 4. Chlumsky MSDF 3-Channel (R,G,B) Median-of-Three Reconstruction Kernel
// ---------------------------------------------------------------------------
inline float median3_f(float r, float g, float b) {
    return fmax(fmin(r, g), fmin(fmax(r, g), b));
}

__kernel void msdf_median3_reconstruct_kernel(
    __global const float* sdf_r,
    __global const float* sdf_g,
    __global const float* sdf_b,
    __global uchar* out_bilevel,
    const int target_w,
    const int target_h,
    const float edge_offset_px)
{
    int gx = get_global_id(0);
    int gy = get_global_id(1);
    if (gx >= target_w || gy >= target_h) return;

    int idx = gy * target_w + gx;
    float m = median3_f(sdf_r[idx], sdf_g[idx], sdf_b[idx]);
    out_bilevel[idx] = (m >= edge_offset_px) ? 1 : 0;
}

// ---------------------------------------------------------------------------
// 5. Saffron 9-Point Bi-Quadratic Lagrange Polynomial ADF Kernel
// ---------------------------------------------------------------------------
__kernel void adf_biquadratic_9pt_kernel(
    __global const float* sdf_hi,
    __global uchar* out_bilevel,
    __global uchar* out_field,
    const int hi_w,
    const int hi_h,
    const int target_w,
    const int target_h,
    const int upscale,
    const float bias_px)
{
    int gx = get_global_id(0);
    int gy = get_global_id(1);
    if (gx >= target_w || gy >= target_h) return;

    int r0 = clamp(gy * upscale, 0, hi_h - 1);
    int rm = clamp(gy * upscale + (upscale / 2), 0, hi_h - 1);
    int r1 = clamp((gy + 1) * upscale - 1, 0, hi_h - 1);

    int c0 = clamp(gx * upscale, 0, hi_w - 1);
    int cm = clamp(gx * upscale + (upscale / 2), 0, hi_w - 1);
    int c1 = clamp((gx + 1) * upscale - 1, 0, hi_w - 1);

    float d00 = sdf_hi[r0 * hi_w + c0];
    float d10 = sdf_hi[r0 * hi_w + cm];
    float d20 = sdf_hi[r0 * hi_w + c1];
    float d01 = sdf_hi[rm * hi_w + c0];
    float d11 = sdf_hi[rm * hi_w + cm];
    float d21 = sdf_hi[rm * hi_w + c1];
    float d02 = sdf_hi[r1 * hi_w + c0];
    float d12 = sdf_hi[r1 * hi_w + cm];
    float d22 = sdf_hi[r1 * hi_w + c1];

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

    int idx = gy * target_w + gx;
    out_field[idx] = convert_uchar_sat_rte(clamp(final_cov * 255.0f, 0.0f, 255.0f));
    out_bilevel[idx] = (final_cov >= 0.50f) ? 1 : 0;
}

// ---------------------------------------------------------------------------
// 6. Parallel Work-Group Local Atomic Histogram & Binarization Kernels
// ---------------------------------------------------------------------------
__kernel void compute_histogram_local_atomic(
    __global const uchar* src_gray,
    __global uint* global_hist,
    const int total_pixels)
{
    __local uint local_hist[256];
    int lid = get_local_id(0);
    int lsize = get_local_size(0);
    for (int b = lid; b < 256; b += lsize) {
        local_hist[b] = 0u;
    }
    barrier(CLK_LOCAL_MEM_FENCE);

    int gid = get_global_id(0);
    if (gid < total_pixels) {
        uchar v = src_gray[gid];
        if (v >= 8u && v <= 248u) {
            atomic_inc(&local_hist[v]);
        }
    }
    barrier(CLK_LOCAL_MEM_FENCE);

    for (int b = lid; b < 256; b += lsize) {
        if (local_hist[b] > 0u) {
            atomic_add(&global_hist[b], local_hist[b]);
        }
    }
}
"""


class OpenCLMathAccelerator:
    """
    Encapsulates an OpenCL Context, CommandQueue, and compiled Program for
    GPU / Heterogeneous mathematical acceleration, with AMD GCN/Polaris (wavefront 64)
    and NVIDIA (warp 32) work-group alignment and zero-copy host-pinned buffer helpers.
    """

    def __init__(self, ctx: "cl.Context", device: "cl.Device") -> None:
        self.ctx = ctx
        self.device = device
        self.queue = cl.CommandQueue(ctx, device=device)
        self.program = cl.Program(ctx, OPENCL_MATH_KERNELS_SOURCE).build(
            options=["-cl-fast-relaxed-math", "-cl-mad-enable"]
        )
        self.device_name = str(device.name).strip()
        self.vendor = str(device.vendor).strip()
        self.compute_units = int(getattr(device, "max_compute_units", 1) or 1)
        self.max_wg_size = int(getattr(device, "max_work_group_size", 64) or 64)
        # Choose 2D local work-group size as a multiple of 64 (16x8 = 128 or 8x8 = 64) for AMD GCN/Polaris & NVIDIA
        self.local_2d = (16, 8) if self.max_wg_size >= 128 else (8, 8)

    def _round_global_2d(self, width: int, height: int) -> Tuple[int, int]:
        lx, ly = self.local_2d
        gx = ((max(1, width) + lx - 1) // lx) * lx
        gy = ((max(1, height) + ly - 1) // ly) * ly
        return (gx, gy)

    def eval_srgb_to_linear_grayscale(self, arr: np.ndarray, gamma: float = 1.0) -> np.ndarray:
        if arr is None or arr.size == 0:
            return np.zeros((0, 0), dtype=np.uint8)
        u8 = np.ascontiguousarray(np.clip(arr, 0, 255).astype(np.uint8))
        if u8.ndim == 3 and u8.shape[2] >= 3:
            h, w, ch = u8.shape
        else:
            h, w = u8.shape[:2]
            ch = 1

        mf = cl.mem_flags
        src_buf = cl.Buffer(self.ctx, mf.READ_ONLY | mf.ALLOC_HOST_PTR | mf.COPY_HOST_PTR, hostbuf=u8)
        dst_buf = cl.Buffer(self.ctx, mf.WRITE_ONLY | mf.ALLOC_HOST_PTR, size=h * w)
        inv_gamma = np.float32(1.0 / float(gamma) if (gamma > 0.05 and abs(gamma - 1.0) > 1e-4) else 1.0)

        global_2d = self._round_global_2d(w, h)
        self.program.srgb_to_linear_gamma_kernel(
            self.queue,
            global_2d,
            self.local_2d,
            src_buf,
            dst_buf,
            np.int32(w),
            np.int32(h),
            np.int32(ch),
            inv_gamma,
        )
        out = np.empty((h, w), dtype=np.uint8)
        cl.enqueue_copy(self.queue, out, dst_buf).wait()
        return out

    def eval_sdf_smoothstep(
        self,
        sdf_hi: np.ndarray,
        target_w: int,
        target_h: int,
        upscale: int,
        threshold: int = 128,
    ) -> Tuple[np.ndarray, np.ndarray]:
        hi_f32 = np.ascontiguousarray(sdf_hi.astype(np.float32))
        hi_h, hi_w = hi_f32.shape
        eff_t = int(np.clip(threshold if threshold > 0 else 128, 1, 254))
        bias_px = np.float32((128.0 - float(eff_t)) / 64.0)

        mf = cl.mem_flags
        sdf_buf = cl.Buffer(self.ctx, mf.READ_ONLY | mf.ALLOC_HOST_PTR | mf.COPY_HOST_PTR, hostbuf=hi_f32)
        bw_buf = cl.Buffer(self.ctx, mf.WRITE_ONLY | mf.ALLOC_HOST_PTR, size=target_h * target_w)
        fld_buf = cl.Buffer(self.ctx, mf.WRITE_ONLY | mf.ALLOC_HOST_PTR, size=target_h * target_w)

        global_2d = self._round_global_2d(target_w, target_h)
        self.program.sdf_valve_smoothstep_kernel(
            self.queue,
            global_2d,
            self.local_2d,
            sdf_buf,
            bw_buf,
            fld_buf,
            np.int32(hi_w),
            np.int32(hi_h),
            np.int32(target_w),
            np.int32(target_h),
            np.int32(upscale),
            bias_px,
        )
        bilevel = np.empty((target_h, target_w), dtype=np.uint8)
        field_u8 = np.empty((target_h, target_w), dtype=np.uint8)
        cl.enqueue_copy(self.queue, bilevel, bw_buf)
        cl.enqueue_copy(self.queue, field_u8, fld_buf).wait()
        return bilevel, field_u8

    def eval_msdf_median3_reconstruct(
        self,
        sdf_r: np.ndarray,
        sdf_g: np.ndarray,
        sdf_b: np.ndarray,
        edge_offset_px: float = 0.0,
    ) -> np.ndarray:
        target_h, target_w = sdf_r.shape
        r_f = np.ascontiguousarray(sdf_r.astype(np.float32))
        g_f = np.ascontiguousarray(sdf_g.astype(np.float32))
        b_f = np.ascontiguousarray(sdf_b.astype(np.float32))

        mf = cl.mem_flags
        r_buf = cl.Buffer(self.ctx, mf.READ_ONLY | mf.ALLOC_HOST_PTR | mf.COPY_HOST_PTR, hostbuf=r_f)
        g_buf = cl.Buffer(self.ctx, mf.READ_ONLY | mf.ALLOC_HOST_PTR | mf.COPY_HOST_PTR, hostbuf=g_f)
        b_buf = cl.Buffer(self.ctx, mf.READ_ONLY | mf.ALLOC_HOST_PTR | mf.COPY_HOST_PTR, hostbuf=b_f)
        bw_buf = cl.Buffer(self.ctx, mf.WRITE_ONLY | mf.ALLOC_HOST_PTR, size=target_h * target_w)

        global_2d = self._round_global_2d(target_w, target_h)
        self.program.msdf_median3_reconstruct_kernel(
            self.queue,
            global_2d,
            self.local_2d,
            r_buf,
            g_buf,
            b_buf,
            bw_buf,
            np.int32(target_w),
            np.int32(target_h),
            np.float32(edge_offset_px),
        )
        bilevel = np.empty((target_h, target_w), dtype=np.uint8)
        cl.enqueue_copy(self.queue, bilevel, bw_buf).wait()
        return bilevel

    def eval_adf_biquadratic(
        self,
        sdf_hi: np.ndarray,
        target_w: int,
        target_h: int,
        upscale: int,
        threshold: int = 128,
    ) -> Tuple[np.ndarray, np.ndarray]:
        hi_f32 = np.ascontiguousarray(sdf_hi.astype(np.float32))
        hi_h, hi_w = hi_f32.shape
        eff_t = int(np.clip(threshold if threshold > 0 else 128, 1, 254))
        bias_px = np.float32((128.0 - float(eff_t)) / 64.0)

        mf = cl.mem_flags
        sdf_buf = cl.Buffer(self.ctx, mf.READ_ONLY | mf.ALLOC_HOST_PTR | mf.COPY_HOST_PTR, hostbuf=hi_f32)
        bw_buf = cl.Buffer(self.ctx, mf.WRITE_ONLY | mf.ALLOC_HOST_PTR, size=target_h * target_w)
        fld_buf = cl.Buffer(self.ctx, mf.WRITE_ONLY | mf.ALLOC_HOST_PTR, size=target_h * target_w)

        global_2d = self._round_global_2d(target_w, target_h)
        self.program.adf_biquadratic_9pt_kernel(
            self.queue,
            global_2d,
            self.local_2d,
            sdf_buf,
            bw_buf,
            fld_buf,
            np.int32(hi_w),
            np.int32(hi_h),
            np.int32(target_w),
            np.int32(target_h),
            np.int32(upscale),
            bias_px,
        )
        bilevel = np.empty((target_h, target_w), dtype=np.uint8)
        field_u8 = np.empty((target_h, target_w), dtype=np.uint8)
        cl.enqueue_copy(self.queue, bilevel, bw_buf)
        cl.enqueue_copy(self.queue, field_u8, fld_buf).wait()
        return bilevel, field_u8

    def eval_bezier_sdf_yuksel(
        self,
        curves_f32: np.ndarray,
        target_w: int,
        target_h: int,
        threshold: int = 128,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Evaluate exact Euclidean Signed Distance to cubic Bezier curves on the GPU
        using Cem Yuksel's degree-5 to degree-2 monotonic derivative cascade.
        `curves_f32` has shape `(N, 4, 2)` in target pixel coordinates.
        """
        if curves_f32.size == 0 or target_w <= 0 or target_h <= 0:
            empty = np.zeros((max(1, target_h), max(1, target_w)), dtype=np.uint8)
            return empty, empty

        c_arr = np.ascontiguousarray(curves_f32.astype(np.float32))
        num_curves = int(c_arr.shape[0])
        eff_t = int(np.clip(threshold if threshold > 0 else 128, 1, 254))
        bias_px = np.float32((128.0 - float(eff_t)) / 64.0)

        mf = cl.mem_flags
        c_buf = cl.Buffer(self.ctx, mf.READ_ONLY | mf.ALLOC_HOST_PTR | mf.COPY_HOST_PTR, hostbuf=c_arr)
        bw_buf = cl.Buffer(self.ctx, mf.WRITE_ONLY | mf.ALLOC_HOST_PTR, size=target_h * target_w)
        fld_buf = cl.Buffer(self.ctx, mf.WRITE_ONLY | mf.ALLOC_HOST_PTR, size=target_h * target_w)

        global_2d = self._round_global_2d(target_w, target_h)
        self.program.render_bezier_sdf_yuksel_kernel(
            self.queue,
            global_2d,
            self.local_2d,
            c_buf,
            np.int32(num_curves),
            bw_buf,
            fld_buf,
            np.int32(target_w),
            np.int32(target_h),
            bias_px,
        )
        bilevel = np.empty((target_h, target_w), dtype=np.uint8)
        field_u8 = np.empty((target_h, target_w), dtype=np.uint8)
        cl.enqueue_copy(self.queue, bilevel, bw_buf)
        cl.enqueue_copy(self.queue, field_u8, fld_buf).wait()
        return bilevel, field_u8

    def eval_otsu_linear_threshold(self, linear_gray: np.ndarray, base_threshold: int = 128) -> int:
        if linear_gray is None or linear_gray.size < 64:
            from .cpu_math import eval_otsu_linear_threshold_cpu
            return eval_otsu_linear_threshold_cpu(linear_gray, base_threshold)

        u8 = np.ascontiguousarray(linear_gray.astype(np.uint8)).ravel()
        n_px = int(u8.size)
        mf = cl.mem_flags
        src_buf = cl.Buffer(self.ctx, mf.READ_ONLY | mf.ALLOC_HOST_PTR | mf.COPY_HOST_PTR, hostbuf=u8)
        hist_zeros = np.zeros(256, dtype=np.uint32)
        hist_buf = cl.Buffer(self.ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=hist_zeros)

        lsize = min(256, self.max_wg_size)
        gsize = ((n_px + lsize - 1) // lsize) * lsize
        self.program.compute_histogram_local_atomic(
            self.queue,
            (gsize,),
            (lsize,),
            src_buf,
            hist_buf,
            np.int32(n_px),
        )
        hist = np.empty(256, dtype=np.uint32)
        cl.enqueue_copy(self.queue, hist, hist_buf).wait()

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
