#!/usr/bin/env python3
"""
opencl_dispatcher.py (v1.0.22)
=============================
A 1-bit EPD font generator and asset pipeline for embedded displays.
Repository : https://github.com/Humidyne-Labs/epd-font
Authors    : Humiditron (https://github.com/humiditron) & AI/LLM Development Partner
License    : MIT License

Heterogeneous Multi-Device OpenCL & CPU Workload Coordinator (`v1.0.22`):
  - Discovers discrete GPU OpenCL devices (e.g., `[0] Platform 0, Device 0: Ellesmere (ALL | GPU) - 32 CUs`)
    and host CPU OpenCL runtimes (e.g., `[1] Platform 1, Device 0: AMD Ryzen 5 5600G (ALL | CPU) - 12 CUs`
    installed via Intel CPU Runtime for OpenCL Applications).
  - Enforces a Single-Owner Persistent GPU Context (`gpu_worker_process` with `EPD_FONT_WORKER_ROLE="gpu"`)
    paired with CPU worker processes (`cpu_worker_process` with `EPD_FONT_WORKER_ROLE="cpu"`), eliminating
    multi-process GPU context thrashing and preventing the 2.0–2.3 GB Dedicated VRAM retention observed
    when 12 processes open competing GPU contexts.
  - Partitions font and icon strike tasks by computational density:
      * Heavy tasks -> Discrete GPU (`Ellesmere`, 32 CUs, 4 CommandQueues, 3D NDRange, 15.7 GB Shared RAM):
        Large icon catalogs (`icon_tabler`, `icon_phosphor`, `icon_lucide`, `icon_fa7`), distance-field
        pipelines (`sdf-smoothstep`, `msdf`, `mdf`, `adf-biquadratic`, `otsu-adaptive`, `svg-potrace`),
        and high point-size strikes (`28px..40px`).
      * Lightweight / pre-gridded tasks -> Host CPU Workers (`AMD Ryzen 5 5600G`, 12 CUs / 12 threads):
        `Terminus` BDF-to-TTF / `exact-mono` strikes and small text strikes (`10px..26px`).
  - Performs deterministic teardown (`teardown_math_backends()`, `Buffer.release()`, `CommandQueue.finish()`,
    `gc.collect()`) and clean `SIGINT` (`Ctrl+C`) worker termination with zero console tracebacks.
"""

from __future__ import annotations

import atexit
import os
import signal
import sys
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from math_backends import (
    HAS_PYOPENCL,
    OpenCLDeviceDescriptor,
    detect_shared_gpu_memory_mb,
    enumerate_opencl_devices,
    select_math_backend,
    teardown_math_backends,
)

TOOL_VERSION = "1.0.22"

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
    Discover the primary discrete/integrated OpenCL GPU device (e.g., `Ellesmere - 32 CUs`)
    and the secondary OpenCL CPU runtime device (e.g., `AMD Ryzen 5 5600G - 12 CUs`).
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
                dname = str(getattr(d, "name", ""))
                if (dtype & getattr(cl.device_type, "GPU", 4)):
                    if gpu_dev is None or "Ellesmere" in dname or int(getattr(d, "max_compute_units", 0)) > int(getattr(gpu_dev, "max_compute_units", 0)):
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
        Ideal for the persistent GPU worker (`Ellesmere`, 32 CUs, 3D NDRange).
      - Low score (< 200): `Terminus` bitmap (`exact-mono`) strikes and small `10..22px` text strikes.
        Ideal for fast L1-cached CPU workers (`Ryzen 5 5600G`, 12 threads).
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


def partition_strike_tasks_hybrid(
    tasks: Sequence[dict],
) -> Tuple[List[dict], List[dict]]:
    """
    Partition `tasks` into `(gpu_priority_tasks, cpu_priority_tasks)` based on computation density
    per `Jr.Agent_Notes.md` Step 2:
      1. Discrete GPU (`Ellesmere`, 32 CUs):
         - Massive Icon Catalogs (`Tabler`, `Phosphor`, `Lucide`, `FontAwesome 7`)
         - High point-size antialiased / distance-field sheets (`sz >= 28` or SDF/MSDF/ADF/Potrace/Otsu)
      2. CPU Workers (`Ryzen 5 5600G`, 12 CUs / 12 threads):
         - All `Terminus` BDF-to-TTF / `exact-mono` conversions
         - Small text strikes (`10..26px`) where L1-cached CPU execution avoids PCIe DMA overhead.
    """
    gpu_tasks: List[dict] = []
    cpu_tasks: List[dict] = []

    for idx, t in enumerate(tasks):
        t_copy = dict(t) if isinstance(t, dict) else {"payload": t}
        t_copy.setdefault("_orig_idx", idx)
        fam = str(t_copy.get("family", "")).lower()
        pipe = str(t_copy.get("effective_raster_m", "raw-hinted")).lower()
        sz = int(t_copy.get("sz", 16))
        run_all = bool(t_copy.get("run_all_methods", False))

        if fam in ("terminus", "unifont") or pipe == "exact-mono":
            cpu_tasks.append(t_copy)
        elif fam in HEAVY_ICON_FAMILIES or run_all or pipe in DISTANCE_FIELD_PIPELINES or sz >= 28:
            gpu_tasks.append(t_copy)
        else:
            cpu_tasks.append(t_copy)

    gpu_tasks.sort(key=score_task_compute_density, reverse=True)
    cpu_tasks.sort(key=score_task_compute_density)
    return gpu_tasks, cpu_tasks


def init_worker_environment(role: str = "cpu") -> None:
    """
    Initializer for child worker processes:
      1. Ignores `SIGINT` (`Ctrl+C`) in child workers so the parent coordinator handles `Ctrl+C`
         cleanly without 12 interleaved `KeyboardInterrupt` tracebacks from `multiprocessing.queues`.
      2. Sets `EPD_FONT_WORKER_ROLE` (`"gpu"` for the single persistent GPU worker, `"cpu"` for CPU
         workers) so CPU workers NEVER allocate competing discrete GPU OpenCL contexts.
      3. Registers `teardown_math_backends` with `atexit` for deterministic buffer/context release.
    """
    try:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    except Exception:
        pass
    os.environ["EPD_FONT_WORKER_ROLE"] = role
    if role == "gpu":
        select_math_backend("opencl")
    else:
        os.environ["EPD_FONT_ACCEL"] = "cpu"
        os.environ["OPENCV_OPENCL_RUNTIME"] = "disabled"
        try:
            import cv2
            if hasattr(cv2, "ocl"):
                cv2.ocl.setUseOpenCL(False)
        except Exception:
            pass
        select_math_backend("cpu")
    atexit.register(teardown_math_backends)


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
    "partition_strike_tasks_hybrid",
    "init_worker_environment",
    "describe_hybrid_dispatch_plan",
    "teardown_math_backends",
]
