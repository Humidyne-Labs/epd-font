#!/usr/bin/env python3
"""
hw_dispatch.py (v1.0.21)
========================
A 1-bit EPD font generator and asset pipeline for embedded displays.
Repository : https://github.com/Humidyne-Labs/epd-font
Authors    : Humiditron (https://github.com/humiditron) & AI/LLM Development Partner
License    : MIT License

Multi-Device Hardware Capability Check, 3D NDRange GPU/CPU Dispatcher, 75% Shared RAM Arena &
Deterministic Teardown (`v1.0.21`):
  - Enumerates all available OpenCL platforms and devices (e.g., `[0] Ellesmere (GPU - 32 CUs)` and
    `[1] AMD Ryzen 5 5600G with Radeon Graphics (CPU - 12 CUs)` installed via Intel CPU Runtime for OpenCL).
  - Enforces Single-Owner GPU Context isolation (`EPD_FONT_WORKER_ROLE="cpu"` in child CPU workers) so
    `ProcessPoolExecutor` workers never create 12 competing contexts on the discrete GPU (`0` context thrashing
    and `0 MB` post-termination VRAM leak).
  - Utilizes 3D Work-Item Dimensions (`work_dim = 3`, `[dim_x, dim_y, dim_z]`), 4 striped hardware command
    queues (`Compute 0..3`), and 75% of the Host/GPU Shared RAM (`CL_MEM_ALLOC_HOST_PTR` + `clEnqueueMapBuffer`).
  - Exposes `dispatch_jfa_marching_squares` for the Jump Flooding Algorithm (`1+JFA`) + Marching Squares
    vector contour sub-mode (`svg-potrace-jfa` / `jfa-marching`).
  - Exposes `teardown_math_backends()` (`atexit`-registered) to deterministically release all OpenCL buffers,
    queues, programs, and contexts upon script exit or `Ctrl+C`.
"""

from __future__ import annotations

import atexit
import gc
import os
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import cv2
import numpy as np

from .cpu_math import (
    bezier_winding_cpu,
    distance_sq_to_bezier_yuksel_cpu,
    eval_adf_biquadratic_cpu,
    eval_jfa_marching_squares_cpu,
    eval_msdf_median3_reconstruct_cpu,
    eval_otsu_linear_threshold_cpu,
    eval_sdf_smoothstep_cpu,
    eval_srgb_to_linear_grayscale_cpu,
)
from .opencl_kernels import (
    HAS_PYOPENCL,
    SHARED_RAM_CAP_RATIO,
    OpenCLMathAccelerator,
    cl,
    detect_shared_gpu_memory_mb,
    release_all_opencl_resources,
    validate_sdf_gradient,
)
from .umat_math import is_opencv_umat_opencl_active, umat_median_blur, umat_morphology_close

TOOL_VERSION = "1.0.21"


@dataclass
class OpenCLDeviceDescriptor:
    global_index: int
    platform_index: int
    device_index: int
    platform_name: str
    device_name: str
    vendor: str
    device_type_str: str
    is_gpu: bool
    is_cpu: bool
    compute_units: int
    max_work_group_size: int
    max_work_item_dims: int
    max_work_item_sizes: List[int]
    global_mem_mb: int
    local_mem_kb: int
    opencl_version: str


@dataclass
class MathBackendStatus:
    backend_id: str  # "opencl", "umat", or "cpu"
    device_name: str
    vendor: str
    device_type: str  # "GPU", "OPENCL_CPU", "ACCELERATOR", "GPU_UMAT", "CPU"
    compute_units: int
    max_work_group_size: int
    opencl_version: str
    zero_copy_host_ptr: bool
    sdf_gradient_verified: bool
    mean_sdf_gradient: float
    work_item_dimensions: int = 3
    num_command_queues: int = 4
    shared_gpu_ram_mb: int = 0
    shared_gpu_ram_cap_75pct_mb: int = 0
    secondary_cpu_opencl_device: Optional[str] = None
    secondary_cpu_opencl_cus: int = 0
    discovered_devices: List[OpenCLDeviceDescriptor] = field(default_factory=list)


_ACTIVE_ACCEL: Optional[OpenCLMathAccelerator] = None
_ACTIVE_CPU_OCL_ACCEL: Optional[OpenCLMathAccelerator] = None
_ACTIVE_STATUS: Optional[MathBackendStatus] = None


def enumerate_opencl_devices() -> List[OpenCLDeviceDescriptor]:
    """Enumerate all OpenCL platforms and devices installed on the host."""
    out: List[OpenCLDeviceDescriptor] = []
    if not HAS_PYOPENCL or cl is None:
        return out
    try:
        platforms = cl.get_platforms()
    except Exception:
        return out

    g_idx = 0
    for p_idx, plat in enumerate(platforms):
        p_name = str(getattr(plat, "name", f"Platform {p_idx}")).strip()
        try:
            devs = plat.get_devices()
        except Exception:
            devs = []
        for d_idx, dev in enumerate(devs):
            try:
                dtype_bits = int(getattr(dev, "type", 0))
                dtype_str = cl.device_type.to_string(dtype_bits)
            except Exception:
                dtype_bits = 0
                dtype_str = "UNKNOWN"
            is_gpu = bool(dtype_bits & getattr(cl.device_type, "GPU", 4))
            is_cpu = bool(dtype_bits & getattr(cl.device_type, "CPU", 2)) and not is_gpu
            out.append(
                OpenCLDeviceDescriptor(
                    global_index=g_idx,
                    platform_index=p_idx,
                    device_index=d_idx,
                    platform_name=p_name,
                    device_name=str(getattr(dev, "name", f"Device {d_idx}")).strip(),
                    vendor=str(getattr(dev, "vendor", "Unknown")).strip(),
                    device_type_str=dtype_str,
                    is_gpu=is_gpu,
                    is_cpu=is_cpu,
                    compute_units=int(getattr(dev, "max_compute_units", 1)),
                    max_work_group_size=int(getattr(dev, "max_work_group_size", 64)),
                    max_work_item_dims=int(getattr(dev, "max_work_item_dimensions", 3)),
                    max_work_item_sizes=list(getattr(dev, "max_work_item_sizes", [1024, 1024, 1024])),
                    global_mem_mb=int(getattr(dev, "global_mem_size", 0) // (1024 * 1024)),
                    local_mem_kb=int(getattr(dev, "local_mem_size", 0) // 1024),
                    opencl_version=str(getattr(dev, "version", getattr(plat, "version", "OpenCL"))).strip(),
                )
            )
            g_idx += 1
    return out


def teardown_math_backends() -> int:
    """
    Deterministically release all active GPU/CPU OpenCL contexts, command queues,
    and `CL_MEM_ALLOC_HOST_PTR` shared memory buffers, and run `gc.collect()`.
    """
    global _ACTIVE_ACCEL, _ACTIVE_CPU_OCL_ACCEL, _ACTIVE_STATUS
    if _ACTIVE_ACCEL is not None:
        try:
            _ACTIVE_ACCEL.release()
        except Exception:
            pass
        _ACTIVE_ACCEL = None
    if _ACTIVE_CPU_OCL_ACCEL is not None:
        try:
            _ACTIVE_CPU_OCL_ACCEL.release()
        except Exception:
            pass
        _ACTIVE_CPU_OCL_ACCEL = None
    _ACTIVE_STATUS = None
    n_rel = release_all_opencl_resources()
    try:
        if hasattr(cv2, "ocl") and cv2.ocl.useOpenCL():
            cv2.ocl.finish()
    except Exception:
        pass
    gc.collect()
    return n_rel


atexit.register(teardown_math_backends)


def _probe_and_init_backend(preferred: Optional[str] = None) -> MathBackendStatus:
    global _ACTIVE_ACCEL, _ACTIVE_CPU_OCL_ACCEL, _ACTIVE_STATUS

    if _ACTIVE_ACCEL is not None or _ACTIVE_CPU_OCL_ACCEL is not None:
        teardown_math_backends()

    worker_role = os.environ.get("EPD_FONT_WORKER_ROLE", "").strip().lower()
    pref = (preferred or os.environ.get("EPD_FONT_ACCEL", "auto")).strip().lower()
    if pref not in ("auto", "opencl", "gpu", "umat", "cpu", "opencl-cpu", "hybrid"):
        pref = "auto"

    res = 32
    grid = np.linspace(-1.0, 1.0, res, dtype=np.float32)
    xx, yy = np.meshgrid(grid, grid)
    synth_sdf = np.clip((0.6 - np.sqrt(xx * xx + yy * yy)) * (res / 2.0) / float(res) + 0.5, 0.0, 1.0)
    grad_ok, mean_grad = validate_sdf_gradient(synth_sdf * float(res), tolerance=0.15)
    total_shared_mb, usable_75pct_mb = detect_shared_gpu_memory_mb()
    cap_75pct_mb = int(round(total_shared_mb * SHARED_RAM_CAP_RATIO))

    if worker_role == "cpu":
        pref = "cpu"

    discovered = enumerate_opencl_devices() if (pref != "cpu" and HAS_PYOPENCL and cl is not None) else []

    if pref != "cpu" and HAS_PYOPENCL and cl is not None:
        try:
            platforms = cl.get_platforms()
            gpu_dev = None
            gpu_plat = None
            cpu_ocl_dev = None
            cpu_ocl_plat = None
            accel_dev = None
            accel_plat = None

            for plat in platforms:
                try:
                    devs = plat.get_devices()
                except Exception:
                    devs = []
                for d in devs:
                    if not (getattr(d, "available", 1) and getattr(d, "compiler_available", 1)):
                        continue
                    dtype = int(getattr(d, "type", 0))
                    if (dtype & getattr(cl.device_type, "GPU", 4)) and gpu_dev is None:
                        gpu_dev = d
                        gpu_plat = plat
                    elif (dtype & getattr(cl.device_type, "CPU", 2)) and cpu_ocl_dev is None:
                        cpu_ocl_dev = d
                        cpu_ocl_plat = plat
                    elif (dtype & getattr(cl.device_type, "ACCELERATOR", 8)) and accel_dev is None:
                        accel_dev = d
                        accel_plat = plat

            chosen_dev = None
            chosen_plat = None
            chosen_type_str = "GPU"

            if worker_role == "opencl_cpu" or pref == "opencl-cpu":
                if cpu_ocl_dev is not None:
                    chosen_dev, chosen_plat, chosen_type_str = cpu_ocl_dev, cpu_ocl_plat, "OPENCL_CPU"
            else:
                if gpu_dev is not None:
                    chosen_dev, chosen_plat, chosen_type_str = gpu_dev, gpu_plat, "GPU"
                elif accel_dev is not None:
                    chosen_dev, chosen_plat, chosen_type_str = accel_dev, accel_plat, "ACCELERATOR"
                elif cpu_ocl_dev is not None and pref in ("opencl", "auto", "hybrid"):
                    chosen_dev, chosen_plat, chosen_type_str = cpu_ocl_dev, cpu_ocl_plat, "OPENCL_CPU"

            if chosen_dev is not None:
                n_queues = 4 if chosen_type_str == "GPU" else 2
                ctx = cl.Context([chosen_dev])
                accel = OpenCLMathAccelerator(ctx, chosen_dev, num_queues=n_queues)
                test_in = np.array([[0, 64, 128, 192, 255]], dtype=np.uint8)
                gpu_out = accel.eval_srgb_to_linear_grayscale(test_in, gamma=1.0)
                cpu_out = eval_srgb_to_linear_grayscale_cpu(test_in, gamma=1.0)
                if np.max(np.abs(gpu_out.astype(np.int32) - cpu_out.astype(np.int32))) <= 1:
                    _ACTIVE_ACCEL = accel
                    sec_cpu_name = str(getattr(cpu_ocl_dev, "name", "")).strip() if (cpu_ocl_dev is not None and chosen_dev != cpu_ocl_dev) else None
                    sec_cpu_cus = int(getattr(cpu_ocl_dev, "max_compute_units", 0)) if (cpu_ocl_dev is not None and chosen_dev != cpu_ocl_dev) else 0
                    _ACTIVE_STATUS = MathBackendStatus(
                        backend_id="opencl",
                        device_name=accel.device_name,
                        vendor=accel.vendor,
                        device_type=chosen_type_str,
                        compute_units=accel.compute_units,
                        max_work_group_size=accel.max_wg_size,
                        opencl_version=str(getattr(chosen_dev, "version", chosen_plat.version if chosen_plat else "OpenCL")).strip(),
                        zero_copy_host_ptr=True,
                        sdf_gradient_verified=grad_ok,
                        mean_sdf_gradient=round(mean_grad, 4),
                        work_item_dimensions=3,
                        num_command_queues=len(accel.queues),
                        shared_gpu_ram_mb=total_shared_mb,
                        shared_gpu_ram_cap_75pct_mb=cap_75pct_mb,
                        secondary_cpu_opencl_device=sec_cpu_name,
                        secondary_cpu_opencl_cus=sec_cpu_cus,
                        discovered_devices=discovered,
                    )
                    return _ACTIVE_STATUS
                else:
                    accel.release()
        except Exception:
            if _ACTIVE_ACCEL is not None:
                try:
                    _ACTIVE_ACCEL.release()
                except Exception:
                    pass
                _ACTIVE_ACCEL = None

    if pref in ("auto", "umat", "gpu") and worker_role != "cpu" and is_opencv_umat_opencl_active():
        dev_name = "OpenCV UMat OpenCL Device"
        try:
            dev = cv2.ocl.Device.getDefault()
            if dev is not None and dev.name():
                dev_name = str(dev.name()).strip()
        except Exception:
            pass
        _ACTIVE_ACCEL = None
        _ACTIVE_STATUS = MathBackendStatus(
            backend_id="umat",
            device_name=dev_name,
            vendor="OpenCV Transparent API (cl.Image / UMat)",
            device_type="GPU_UMAT",
            compute_units=os.cpu_count() or 2,
            max_work_group_size=256,
            opencl_version="OpenCV OCL",
            zero_copy_host_ptr=True,
            sdf_gradient_verified=grad_ok,
            mean_sdf_gradient=round(mean_grad, 4),
            work_item_dimensions=3,
            num_command_queues=1,
            shared_gpu_ram_mb=total_shared_mb,
            shared_gpu_ram_cap_75pct_mb=cap_75pct_mb,
            discovered_devices=discovered,
        )
        return _ACTIVE_STATUS

    _ACTIVE_ACCEL = None
    _ACTIVE_STATUS = MathBackendStatus(
        backend_id="cpu",
        device_name="Vectorized NumPy/OpenCV SIMD Engine",
        vendor="Host CPU",
        device_type="CPU",
        compute_units=os.cpu_count() or 2,
        max_work_group_size=1,
        opencl_version="N/A (CPU Fallback)",
        zero_copy_host_ptr=True,
        sdf_gradient_verified=grad_ok,
        mean_sdf_gradient=round(mean_grad, 4),
        work_item_dimensions=3,
        num_command_queues=1,
        shared_gpu_ram_mb=total_shared_mb,
        shared_gpu_ram_cap_75pct_mb=cap_75pct_mb,
        discovered_devices=discovered,
    )
    return _ACTIVE_STATUS


def get_active_math_backend() -> MathBackendStatus:
    global _ACTIVE_STATUS
    if _ACTIVE_STATUS is None:
        return _probe_and_init_backend()
    return _ACTIVE_STATUS


def select_math_backend(preferred: str = "auto") -> MathBackendStatus:
    """Explicitly re-probe and select the active math backend (`auto`, `opencl`, `umat`, `cpu`)."""
    return _probe_and_init_backend(preferred)


def describe_math_backend() -> str:
    st = get_active_math_backend()
    sec = (
        f" + OpenCL-CPU: {st.secondary_cpu_opencl_device} ({st.secondary_cpu_opencl_cus} CUs)"
        if st.secondary_cpu_opencl_device
        else ""
    )
    return (
        f"backend={st.backend_id} ({st.device_type}: {st.device_name}, "
        f"CUs={st.compute_units}, dims={st.work_item_dimensions}D, queues={st.num_command_queues}, "
        f"shared_ram_75pct={st.shared_gpu_ram_cap_75pct_mb}/{st.shared_gpu_ram_mb}MB, max_wg={st.max_work_group_size}, "
        f"sdf_grad_ok={st.sdf_gradient_verified}{sec})"
    )


# ---------------------------------------------------------------------------
# Hardware-Checked Dynamic 3D NDRange Mathematical Dispatch Functions
# ---------------------------------------------------------------------------
def dispatch_srgb_to_linear_grayscale(arr: np.ndarray, gamma: float = 1.0) -> np.ndarray:
    """
    Dispatch IEC 61966-2-1 sRGB -> ITU-R BT.709 Linear Luminance + Gamma.
    Uses L1-cached CPU LUT for small single-glyph buffers (`< 65,536` px) to avoid PCIe overhead,
    and dispatches large / 3D-batched buffers (`>= 65,536` px) to 3D NDRange OpenCL GPU.
    """
    if arr is None or arr.size == 0:
        return np.zeros((0, 0), dtype=np.uint8)
    if arr.size < 65536 and (arr.ndim <= 2 or (arr.ndim == 3 and arr.shape[2] == 1)) and abs(float(gamma) - 1.0) <= 1e-4:
        return eval_srgb_to_linear_grayscale_cpu(arr, gamma=gamma)

    if os.environ.get("EPD_FONT_WORKER_ROLE", "").strip().lower() == "cpu":
        return eval_srgb_to_linear_grayscale_cpu(arr, gamma=gamma)

    st = get_active_math_backend()
    if st.backend_id == "opencl" and _ACTIVE_ACCEL is not None and arr.size >= 65536:
        try:
            return _ACTIVE_ACCEL.eval_srgb_to_linear_grayscale(arr, gamma=gamma)
        except Exception:
            pass
    return eval_srgb_to_linear_grayscale_cpu(arr, gamma=gamma)


def dispatch_sdf_smoothstep(
    sdf_hi: np.ndarray,
    target_w: int,
    target_h: int,
    upscale: int,
    threshold: int = 128,
) -> Tuple[np.ndarray, np.ndarray]:
    """Dispatch Chris Green (Valve) 3D NDRange SDF Smoothstep + L2 Screen-Space Derivative reconstruction."""
    if os.environ.get("EPD_FONT_WORKER_ROLE", "").strip().lower() == "cpu":
        return eval_sdf_smoothstep_cpu(sdf_hi, target_w, target_h, upscale, threshold)
    st = get_active_math_backend()
    if st.backend_id == "opencl" and _ACTIVE_ACCEL is not None and sdf_hi.size >= 4096:
        try:
            return _ACTIVE_ACCEL.eval_sdf_smoothstep(sdf_hi, target_w, target_h, upscale, threshold)
        except Exception:
            pass
    return eval_sdf_smoothstep_cpu(sdf_hi, target_w, target_h, upscale, threshold)


def dispatch_msdf_median3_reconstruct(
    msdf_rgb_or_r: np.ndarray,
    sdf_g: Optional[np.ndarray] = None,
    sdf_b: Optional[np.ndarray] = None,
    threshold: int = 128,
    edge_offset_px: float = 0.0,
) -> Tuple[np.ndarray, np.ndarray]:
    """Dispatch Chlumsky MSDF 3-channel 3D NDRange median-of-three reconstruction to GPU (OpenCL) or CPU."""
    if os.environ.get("EPD_FONT_WORKER_ROLE", "").strip().lower() == "cpu":
        return eval_msdf_median3_reconstruct_cpu(msdf_rgb_or_r, sdf_g, sdf_b, threshold, edge_offset_px)
    st = get_active_math_backend()
    if st.backend_id == "opencl" and _ACTIVE_ACCEL is not None and msdf_rgb_or_r.size >= 1024:
        try:
            return _ACTIVE_ACCEL.eval_msdf_median3_reconstruct(msdf_rgb_or_r, sdf_g, sdf_b, threshold, edge_offset_px)
        except Exception:
            pass
    return eval_msdf_median3_reconstruct_cpu(msdf_rgb_or_r, sdf_g, sdf_b, threshold, edge_offset_px)


def dispatch_adf_biquadratic(
    sdf_hi: np.ndarray,
    target_w: int,
    target_h: int,
    upscale: int,
    threshold: int = 128,
) -> Tuple[np.ndarray, np.ndarray]:
    """Dispatch Saffron 9-point Bi-Quadratic Lagrange Polynomial 3D NDRange ADF cell reconstruction."""
    if os.environ.get("EPD_FONT_WORKER_ROLE", "").strip().lower() == "cpu":
        return eval_adf_biquadratic_cpu(sdf_hi, target_w, target_h, upscale, threshold)
    st = get_active_math_backend()
    if st.backend_id == "opencl" and _ACTIVE_ACCEL is not None and sdf_hi.size >= 4096:
        try:
            return _ACTIVE_ACCEL.eval_adf_biquadratic(sdf_hi, target_w, target_h, upscale, threshold)
        except Exception:
            pass
    return eval_adf_biquadratic_cpu(sdf_hi, target_w, target_h, upscale, threshold)


def dispatch_otsu_linear_threshold(linear_gray: np.ndarray, base_threshold: int = 128) -> int:
    """Dispatch Otsu's between-class variance optimal threshold selection (3D NDRange atomic histogram)."""
    if os.environ.get("EPD_FONT_WORKER_ROLE", "").strip().lower() == "cpu":
        return eval_otsu_linear_threshold_cpu(linear_gray, base_threshold)
    st = get_active_math_backend()
    if st.backend_id == "opencl" and _ACTIVE_ACCEL is not None and linear_gray is not None and linear_gray.size >= 16384:
        try:
            return _ACTIVE_ACCEL.eval_otsu_linear_threshold(linear_gray, base_threshold)
        except Exception:
            pass
    return eval_otsu_linear_threshold_cpu(linear_gray, base_threshold)


def dispatch_jfa_marching_squares(
    high_gray: np.ndarray,
    target_w: int,
    target_h: int,
    upscale: int = 10,
    threshold: int = 128,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Dispatch the 3-Stage Jump Flooding Algorithm (`1+JFA`) + Marching Squares 16-Case
    Vector Contour Sub-Mode (`svg-potrace-jfa` / `jfa-marching`) to 3D NDRange OpenCL GPU or CPU.
    """
    if os.environ.get("EPD_FONT_WORKER_ROLE", "").strip().lower() == "cpu":
        return eval_jfa_marching_squares_cpu(high_gray, target_w, target_h, upscale, threshold)
    st = get_active_math_backend()
    if st.backend_id == "opencl" and _ACTIVE_ACCEL is not None and high_gray is not None and high_gray.size >= 2048:
        try:
            return _ACTIVE_ACCEL.eval_jfa_marching_squares(high_gray, target_w, target_h, upscale, threshold)
        except Exception:
            pass
    return eval_jfa_marching_squares_cpu(high_gray, target_w, target_h, upscale, threshold)


def dispatch_median_blur(arr: np.ndarray, ksize: int) -> np.ndarray:
    """Dispatch median filtering to OpenCV UMat OpenCL queue or CPU."""
    if os.environ.get("EPD_FONT_WORKER_ROLE", "").strip().lower() == "cpu" or arr.size < 16384:
        return cv2.medianBlur(arr, ksize) if (ksize > 1 and arr.size > 0) else arr
    st = get_active_math_backend()
    if st.backend_id in ("opencl", "umat"):
        return umat_median_blur(arr, ksize)
    return cv2.medianBlur(arr, ksize) if (ksize > 1 and arr.size > 0) else arr


def dispatch_morphology_close(arr: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """Dispatch morphological closing to OpenCV UMat OpenCL queue or CPU."""
    if os.environ.get("EPD_FONT_WORKER_ROLE", "").strip().lower() == "cpu" or arr.size < 16384:
        return cv2.morphologyEx(arr, cv2.MORPH_CLOSE, kernel)
    st = get_active_math_backend()
    if st.backend_id in ("opencl", "umat"):
        return umat_morphology_close(arr, kernel)
    return cv2.morphologyEx(arr, cv2.MORPH_CLOSE, kernel)


def dispatch_bezier_sdf_yuksel(
    curves_f32: np.ndarray,
    target_w: int,
    target_h: int,
    threshold: int = 128,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Dispatch Cem Yuksel's degree-5 to degree-2 monotonic derivative cascade for exact
    cubic Bezier SDF evaluation to 3D NDRange OpenCL GPU (`render_bezier_sdf_yuksel_3d_kernel`) or CPU.
    """
    if os.environ.get("EPD_FONT_WORKER_ROLE", "").strip().lower() != "cpu":
        st = get_active_math_backend()
        if st.backend_id == "opencl" and _ACTIVE_ACCEL is not None:
            try:
                return _ACTIVE_ACCEL.eval_bezier_sdf_yuksel(curves_f32, target_w, target_h, threshold)
            except Exception:
                pass

    if curves_f32.size == 0 or target_w <= 0 or target_h <= 0:
        empty = np.zeros((max(1, target_h), max(1, target_w)), dtype=np.uint8)
        return empty, empty

    eff_t = int(np.clip(threshold if threshold > 0 else 128, 1, 254))
    bias_px = (128.0 - float(eff_t)) / 64.0
    bilevel = np.zeros((target_h, target_w), dtype=np.uint8)
    field_u8 = np.zeros((target_h, target_w), dtype=np.uint8)
    for r in range(target_h):
        py = r + 0.5
        for c in range(target_w):
            px = c + 0.5
            min_d_sq = min(distance_sq_to_bezier_yuksel_cpu((px, py), bz) for bz in curves_f32)
            winding = sum(bezier_winding_cpu((px, py), bz) for bz in curves_f32)
            d_mag = float(np.sqrt(max(min_d_sq, 0.0)))
            signed_d = (d_mag if (winding & 1) != 0 else -d_mag) + bias_px
            t = float(np.clip((signed_d + 0.55) / 1.10, 0.0, 1.0))
            alpha = t * t * (3.0 - 2.0 * t)
            field_u8[r, c] = int(round(alpha * 255.0))
            bilevel[r, c] = 1 if alpha >= 0.50 else 0
    return bilevel, field_u8
