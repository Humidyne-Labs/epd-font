#!/usr/bin/env python3
"""
scripts/probe_hardware.py (v1.0.21)
==================================
A 1-bit EPD font generator and asset pipeline for embedded displays.
Repository : https://github.com/Humidyne-Labs/epd-font
Authors    : Humiditron (https://github.com/humiditron) & AI/LLM Development Partner
License    : MIT License

Multi-Platform OpenCL & Host Shared-RAM Hardware Enumeration Probe:
  - Enumerates all installed OpenCL platforms and devices in compact index format:
      `[0] Platform 0, Device 0: Ellesmere (ALL | GPU) - 32 CUs | Dims: 3D | Dedicated: 4096 MB | Shared RAM: 15.7 GB`
      `[1] Platform 1, Device 0: AMD Ryzen 5 5600G with Radeon Graphics (ALL | CPU) - 12 CUs | Dims: 3D`
  - Reports the active Hybrid GPU + CPU work-stealing dispatch configuration and releases all
    probe handles deterministically on exit.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
FONTS_DIR = REPO_ROOT / "tools" / "fonts"
if str(FONTS_DIR) not in sys.path:
    sys.path.insert(0, str(FONTS_DIR))

try:
    import pyopencl as cl  # type: ignore
except ImportError:
    cl = None  # type: ignore

from math_backends import SHARED_RAM_CAP_RATIO, detect_shared_gpu_memory_mb, teardown_math_backends
from opencl_dispatcher import describe_hybrid_dispatch_plan


def list_all_devices() -> List[Tuple[int, int, str, str, int]]:
    total_shared_mb, avail_shared_mb = detect_shared_gpu_memory_mb()
    cap_75_mb = int(total_shared_mb * SHARED_RAM_CAP_RATIO)
    available: List[Tuple[int, int, str, str, int]] = []

    if cl is not None:
        try:
            platforms = cl.get_platforms()
        except Exception:
            platforms = []
        for p_idx, platform in enumerate(platforms):
            try:
                devices = platform.get_devices()
            except Exception:
                devices = []
            for d_idx, device in enumerate(devices):
                dev_type = cl.device_type.to_string(device.type)
                cus = int(device.max_compute_units)
                dims = int(getattr(device, "max_work_item_dimensions", 3))
                vram_mb = int(getattr(device, "global_mem_size", 0) // (1024 * 1024))
                available.append((p_idx, d_idx, device.name.strip(), dev_type, cus))
                print(
                    f"[{len(available)-1}] Platform {p_idx}, Device {d_idx}: "
                    f"{device.name.strip()} ({dev_type}) - {cus} CUs | "
                    f"Work-Item Dims: {dims}D (Active: 3D) | Dedicated: {vram_mb} MB | "
                    f"Shared RAM: {avail_shared_mb:,}/{total_shared_mb:,} MB (75% Cap: {cap_75_mb:,} MB)"
                )
    else:
        print("[!] PyOpenCL not installed — OpenCL device enumeration skipped.")

    print(f"[*] {describe_hybrid_dispatch_plan(108, 12)}")
    teardown_math_backends()
    return available


if __name__ == "__main__":
    list_all_devices()