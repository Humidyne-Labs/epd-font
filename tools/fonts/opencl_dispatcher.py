#!/usr/bin/env python3
"""
opencl_dispatcher.py (v1.0.23)
=============================
A 1-bit EPD font generator and asset pipeline for embedded displays.
Repository : https://github.com/Humidyne-Labs/epd-font
Authors    : Humiditron (https://github.com/humiditron) & AI/LLM Development Partner
License    : MIT License

Heterogeneous Multi-Device OpenCL & CPU Workload Coordinator (`v1.0.23`):
  - Discovers discrete/integrated GPU OpenCL devices and host CPU OpenCL runtimes.
  - Supports a Single-Owner Persistent GPU Context (`EPD_FONT_WORKER_ROLE="gpu"`) paired with
    CPU worker processes (`EPD_FONT_WORKER_ROLE="cpu"`), eliminating multi-process GPU context
    thrashing and VRAM bloat when parallel CPU workers run alongside the GPU worker.
  - Scores font and icon strike tasks by computational density:
      * Heavy tasks: Icon catalogs (`icon_tabler`, `icon_phosphor`, `icon_lucide`, `icon_fa7`),
        distance-field pipelines (`sdf-smoothstep`, `msdf`, `mdf`, `adf-biquadratic`, `otsu-adaptive`,
        `svg-potrace`), and high point-size strikes (`28px..40px`).
      * Lightweight / pre-gridded tasks: `Terminus` bitmap / `exact-mono` strikes and small text
        strikes (`10px..26px`).
  - Reports structured hardware dispatch plans (`describe_hybrid_dispatch_plan`) and exposes
    deterministic OpenCL teardown (`teardown_math_backends`).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, List, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from math_backends import (
    OpenCLDeviceDescriptor,
    detect_shared_gpu_memory_mb,
    enumerate_opencl_devices,
    teardown_math_backends,
)

TOOL_VERSION = "1.0.23"

HEAVY_ICON_FAMILIES = {"icon_tabler", "icon_phosphor", "icon_lucide", "icon_fa7"}
DISTANCE_FIELD_PIPELINES = {
    "sdf-smoothstep",
    "msdf",
    "mdf",
    "adf-biquadratic",
    "otsu-adaptive",
    "svg-potrace",
    "svg-potrace-jfa",
    "jfa-marching",
    "all",
    "all-debug",
}


def get_devices() -> Tuple[Optional[Any], Optional[Any], List[OpenCLDeviceDescriptor]]:
    """
    Discover the primary discrete/integrated OpenCL GPU device and secondary OpenCL CPU device
    (selecting the device with the highest compute-unit count per type).
    Returns `(gpu_dev, cpu_dev, all_descriptors)`.
    """
    eff = os.environ.get("EPD_FONT_ACCEL", "auto").strip().lower()
    role = os.environ.get("EPD_FONT_WORKER_ROLE", "").strip().lower()
    if eff == "cpu" or role == "cpu":
        return None, None, []

    from math_backends.opencl_kernels import ensure_pyopencl
    if not ensure_pyopencl():
        return None, None, []

    from math_backends.opencl_kernels import cl
    if cl is None:
        return None, None, []

    descriptors = enumerate_opencl_devices()
    gpu_dev = None
    cpu_dev = None
    try:
        platforms = cl.get_platforms()
        for p in platforms:
            try:
                devs = p.get_devices()
            except Exception:
                devs = []
            for d in devs:
                dtype = int(getattr(d, "type", 0))
                if (dtype & getattr(cl.device_type, "GPU", 4)):
                    if gpu_dev is None or int(getattr(d, "max_compute_units", 0)) > int(getattr(gpu_dev, "max_compute_units", 0)):
                        gpu_dev = d
                elif (dtype & getattr(cl.device_type, "CPU", 2)):
                    if cpu_dev is None or int(getattr(d, "max_compute_units", 0)) > int(getattr(cpu_dev, "max_compute_units", 0)):
                        cpu_dev = d
    except Exception:
        pass

    return gpu_dev, cpu_dev, descriptors


def score_task_compute_density(task: dict) -> float:
    """
    Compute a numerical priority score representing floating-point / distance-field
    computation density for a strike task:
      - High score (> 1000): Heavy icon catalogs (`Tabler`, `Phosphor`, `Lucide`, `FontAwesome 7`),
        multi-method `all`/`all-debug` audits, and large point-size distance-field strikes (`28..40px`).
      - Low score (< 200): `Terminus` bitmap (`exact-mono`) strikes and small `10..22px` text strikes.
    """
    if not isinstance(task, dict):
        return 100.0
    family = str(task.get("family", "")).lower()
    pipe = str(task.get("effective_raster_m", task.get("pipeline", "raw-hinted"))).lower()
    sz = int(task.get("sz", 16))
    n_cps = len(task.get("codepoints", [])) or 95
    run_all = bool(task.get("run_all_methods", False))

    if family in ("terminus", "unifont") or pipe == "exact-mono":
        return float(sz) * 0.5

    mult = 1.0
    if run_all or pipe in ("all", "all-debug"):
        mult *= 8.0
    elif pipe in DISTANCE_FIELD_PIPELINES:
        mult *= 4.0

    if family in HEAVY_ICON_FAMILIES:
        mult *= 3.5

    if sz >= 28:
        mult *= 2.2
    elif sz <= 16 and pipe in ("raw-hinted", "raw-unhinted") and not run_all:
        mult *= 0.25

    return float(n_cps) * float(sz * sz) * mult / 256.0


def describe_hybrid_dispatch_plan(total_tasks: int, max_workers: int, math_backend: Optional[str] = None) -> str:
    pref = (math_backend or os.environ.get("EPD_FONT_ACCEL", "auto")).strip().lower()
    threads = os.cpu_count() or max_workers
    if pref == "sync":
        return (
            f"Synchronous Single-Process Dispatch ({total_tasks} tasks): "
            f"Mode=sync | Workers=1 (Main Process) | Host CPU={threads} threads"
        )
    if pref == "cpu":
        return (
            f"Async Multi-Core CPU Dispatch ({total_tasks} tasks): "
            f"Mode=cpu | CPU=[Host CPU SIMD ({threads} threads), {max_workers} async workers] | GPU=Disabled"
        )
    gpu_dev, cpu_dev, _ = get_devices()
    if gpu_dev is None and cpu_dev is None:
        return (
            f"Auto-Delegated CPU Compute Dispatch ({total_tasks} tasks): "
            f"Mode={pref} -> CPU=[Host CPU SIMD ({threads} threads), {max_workers} async workers] (No OpenCL GPU detected)"
        )
    total_shared_mb, avail_shared_mb = detect_shared_gpu_memory_mb()
    gpu_str = (
        f"{gpu_dev.name.strip()} ({gpu_dev.max_compute_units} CUs, 3D NDRange, 4 Queues)"
        if gpu_dev is not None
        else f"{cpu_dev.name.strip()} ({cpu_dev.max_compute_units} CUs, OpenCL CPU)"
    )
    if pref == "gpu":
        return (
            f"Dedicated GPU Compute Dispatch ({total_tasks} tasks): "
            f"Mode=gpu | GPU=[{gpu_str}] | CPU=[Orchestration Only] | "
            f"Shared RAM Arena={avail_shared_mb:,}/{total_shared_mb:,} MB (75% Cap, CL_MEM_ALLOC_HOST_PTR)"
        )
    cpu_ocl_str = (
        f"{cpu_dev.name.strip()} ({cpu_dev.max_compute_units} CUs)"
        if cpu_dev is not None
        else f"Host CPU SIMD ({threads} threads)"
    )
    return (
        f"Hybrid Async Work-Stealing Dispatch ({total_tasks} tasks): "
        f"Mode={pref} | GPU=[1 Worker: {gpu_str}] + CPU=[{max(1, max_workers - 1)} Workers: {cpu_ocl_str}] | "
        f"Shared RAM Arena={avail_shared_mb:,}/{total_shared_mb:,} MB (75% Cap, CL_MEM_ALLOC_HOST_PTR)"
    )


__all__ = [
    "get_devices",
    "score_task_compute_density",
    "describe_hybrid_dispatch_plan",
    "teardown_math_backends",
]
