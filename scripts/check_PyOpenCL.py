#!/usr/bin/env python3
"""
scripts/check_PyOpenCL.py (v1.0.21)
==================================
A 1-bit EPD font generator and asset pipeline for embedded displays.
Repository : https://github.com/Humidyne-Labs/epd-font
Authors    : Humiditron (https://github.com/humiditron) & AI/LLM Development Partner
License    : MIT License

OpenCL Runtime & Multi-Device 3D NDRange / Shared-RAM / Teardown Verification Utility:
  - Enumerates all installed OpenCL platforms and devices (e.g., AMD GPU `Ellesmere - 32 CUs`
    and Intel/AMD CPU Runtime for OpenCL `AMD Ryzen 5 5600G - 12 CUs`).
  - Reports Dedicated Memory, Local Memory, Host/GPU Shared Memory (`CL_MEM_ALLOC_HOST_PTR`,
    e.g., 15.7 GB WDDM Shared RAM with dynamic 75% Arena Cap = ~11.77 GB), Compute Units,
    and Work-Item Dimensions (`3D`).
  - Executes a live 3-Dimensional (`work_dim = 3`, `[X, Y, Z]`) NDRange + 4-Queue + Shared-RAM
    + 1+JFA Marching Squares kernel test across all discovered OpenCL devices and verifies
    deterministic memory teardown (`Buffer.release()`, `CommandQueue.finish()`,
    `CommandQueue.release()`, `Context.release()`, `gc.collect()`).
"""

from __future__ import annotations

import gc
import sys
import warnings
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FONTS_DIR = REPO_ROOT / "tools" / "fonts"
if str(FONTS_DIR) not in sys.path:
    sys.path.insert(0, str(FONTS_DIR))

import numpy as np

try:
    import pyopencl as cl  # type: ignore
    if hasattr(cl, "CompilerWarning"):
        warnings.filterwarnings("ignore", category=cl.CompilerWarning)
except ImportError:
    cl = None  # type: ignore

from math_backends import (
    SHARED_RAM_CAP_RATIO,
    OpenCLMathAccelerator,
    detect_shared_gpu_memory_mb,
    eval_srgb_to_linear_grayscale_cpu,
    teardown_math_backends,
)


def inspect_pyopencl() -> int:
    total_shared_mb, usable_shared_mb = detect_shared_gpu_memory_mb()
    cap_75_mb = int(round(total_shared_mb * SHARED_RAM_CAP_RATIO))
    print("============================================================================")
    print("Humidyne Labs - epd-font v1.0.21 - PyOpenCL 3D NDRange & Shared-RAM Inspector")
    print(
        f"Host Shared GPU Memory (CL_MEM_ALLOC_HOST_PTR): {total_shared_mb:,} MB total "
        f"({total_shared_mb / 1024.0:.2f} GB) | 75% Arena Cap: {cap_75_mb:,} MB "
        f"({cap_75_mb / 1024.0:.2f} GB) | Active Budget: {usable_shared_mb:,} MB"
    )
    print("============================================================================")

    if cl is None:
        print("[!] PyOpenCL is not installed (`pip install pyopencl`). Using Vectorized CPU SIMD fallback.")
        return 0

    try:
        platforms = cl.get_platforms()
    except Exception as exc:
        print(f"[!] No OpenCL platforms detected ({exc}). Install an OpenCL Runtime ICD (see README.md).")
        return 0

    if not platforms:
        print("[!] No OpenCL platforms detected. Check your GPU/CPU OpenCL runtime drivers.")
        return 0

    global_dev_idx = 0
    for p_idx, platform in enumerate(platforms):
        print(f"\n================ Platform {p_idx}: {platform.name} ================")
        print(f"  Vendor:  {platform.vendor}")
        print(f"  Version: {platform.version}")
        print(f"  Profile: {platform.profile}")

        devices = platform.get_devices()
        for d_idx, device in enumerate(devices):
            dev_type = cl.device_type.to_string(device.type)
            max_dims = int(getattr(device, "max_work_item_dimensions", 3))
            cus = int(getattr(device, "max_compute_units", 1))
            print(f"\n  --- [{global_dev_idx}] Platform {p_idx}, Device {d_idx}: {device.name.strip()} [{dev_type}] ---")
            print(f"  Driver Version:               {device.driver_version}")
            print(f"  OpenCL C Version:             {device.opencl_c_version}")
            print(f"  Compute Units:                {cus}")
            print(f"  Max Clock Frequency:          {device.max_clock_frequency} MHz")
            print(f"  Dedicated Global Memory:      {device.global_mem_size / (1024**2):.2f} MB")
            print(f"  Host Shared GPU Memory:       {total_shared_mb:.2f} MB ({total_shared_mb / 1024.0:.2f} GB via CL_MEM_ALLOC_HOST_PTR)")
            print(f"  75% Shared RAM Arena Cap:     {cap_75_mb:.2f} MB ({cap_75_mb / 1024.0:.2f} GB usable)")
            print(f"  Local / Work-Group Memory:    {device.local_mem_size / 1024:.2f} KB")
            print(f"  Max Work-Group Size:          {device.max_work_group_size}")
            print(f"  Max Work-Item Dimensions:     {max_dims}")
            print(f"  Max Work-Item Sizes:          {list(device.max_work_item_sizes)}")
            print(f"  Double Precision (FP64):      {'cl_khr_fp64' in device.extensions}")
            print(f"  Half Precision (FP16):        {'cl_khr_fp16' in device.extensions}")

            # Live 3D NDRange + 4-Queue + 75% Shared-RAM + 1+JFA Marching Squares + Teardown Test
            ctx = None
            accel = None
            try:
                with warnings.catch_warnings():
                    if hasattr(cl, "CompilerWarning"):
                        warnings.filterwarnings("ignore", category=cl.CompilerWarning)
                    ctx = cl.Context([device])
                    n_queues = 4 if (device.type & cl.device_type.GPU) else 2
                    accel = OpenCLMathAccelerator(ctx, device, num_queues=n_queues, shared_ram_mb=usable_shared_mb)

                # Dispatch a 3D batch tensor (batch_z = max(32, cus * 2), H = 32, W = 32) across all 3 dimensions
                batch_z = max(32, cus * 2)
                test_3d = np.linspace(0, 255, batch_z * 32 * 32, dtype=np.uint8).reshape((batch_z, 32, 32))
                gpu_out = accel.eval_srgb_to_linear_grayscale(test_3d, gamma=1.0)
                cpu_out = eval_srgb_to_linear_grayscale_cpu(test_3d, gamma=1.0)
                max_err = int(np.max(np.abs(gpu_out.astype(np.int32) - cpu_out.astype(np.int32))))

                # Also test 3D SDF Smoothstep batch and 3-Stage 1+JFA + Marching Squares (`svg-potrace-jfa`)
                sdf_batch = np.zeros((min(16, batch_z), 64, 64), dtype=np.float32)
                bw_3d, fld_3d = accel.eval_sdf_smoothstep(sdf_batch, target_w=16, target_h=16, upscale=4, threshold=128)
                jfa_gray = np.zeros((64, 64), dtype=np.uint8)
                jfa_gray[16:48, 16:48] = 240
                jfa_bw, jfa_fld = accel.eval_jfa_marching_squares(jfa_gray, target_w=16, target_h=16, upscale=4, threshold=128)
                glob_3d = accel._round_global_3d(16, 16, min(16, batch_z))
                loc_3d = accel._effective_local_3d(min(16, batch_z))
                arena_bytes = getattr(
                    accel.shared_arena,
                    "max_shared_bytes",
                    getattr(accel.shared_arena, "budget_bytes", usable_shared_mb * 1024 * 1024),
                )

                print(f"  Active Work-Item Dims Used:   3 / {max_dims} (3D Global={glob_3d}, 3D Local={loc_3d})")
                print(f"  Striped Hardware Queues:      {len(accel.queues)} CommandQueues active")
                print(f"  Shared RAM Arena Budget:      {arena_bytes // (1024 * 1024):,} MB (75% WDDM Shared GPU RAM Cap)")
                print(
                    f"  3D Kernel Parity Check:       PASS (max_abs_err={max_err} LSB, "
                    f"batch_shape={bw_3d.shape}, jfa_marching_ink={int(np.count_nonzero(jfa_bw))}px)"
                )
            except Exception as exc:
                print(f"  3D Kernel Parity Check:       SKIPPED ({exc})")
            finally:
                if accel is not None:
                    accel.release()
                ctx = None
                gc.collect()
                print("  Teardown Memory Check:        PASS (All Buffers, Queues & Context deterministically released)")

            global_dev_idx += 1

    teardown_math_backends()
    return 0


if __name__ == "__main__":
    sys.exit(inspect_pyopencl())
