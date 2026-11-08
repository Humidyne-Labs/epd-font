#!/usr/bin/env python3
"""
humid1_runtime.py (v1.0.21)
==========================
A 1-bit EPD font generator and asset pipeline for embedded displays.
Repository : https://github.com/Humidyne-Labs/epd-font
Authors    : Humiditron (https://github.com/humiditron) & AI/LLM Development Partner
License    : MIT License

Host Hardware Detection (Multi-Device OpenCL GPU/CPU + Shared GPU RAM + Multi-Core CPU),
Target Embedded Hardware Scheme Validator (`esp32s3-N8R8-hw_scheme.json` & `generic_hw.json`),
Single-Owner GPU + Multi-Core CPU Work-Stealing Dispatcher (`run_parallel_tasks`),
Clean Signal/Ctrl-C Interruption Handler (Zero Worker Traceback Noise + Deterministic Teardown),
Recursive Asset/License Discovery, and Strict Zero-Default Argument/Path Validation Module (`v1.0.21`).
"""

from __future__ import annotations

import atexit
from collections import deque
import concurrent.futures
import ctypes
import gc
import json
import os
import re
import shutil
import signal
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

TOOL_VERSION = "1.0.21"
REPO_NAME = "epd-font"
PROJECT_TAGLINE = "A 1-bit EPD font generator and asset pipeline for embedded displays"
PUBLIC_REPO_URL = "https://github.com/Humidyne-Labs/epd-font"
HUMIDITRON_URL = "https://github.com/humiditron"

# Exact single supported partition size per hardware specification: 3 MBytes = 3,145,728 bytes
SUPPORTED_PARTITION_BYTES = 3 * 1024 * 1024  # 3,145,728 bytes (3 MBytes)

_INTERRUPTED = False


def enforce_supported_platform() -> None:
    """Ensure execution runs only on supported Windows or Linux hosts."""
    if sys.platform == "darwin":
        sys.stderr.write(
            "[!] Platform Error: Unsupported operating system detected.\n"
            f"    {REPO_NAME} v{TOOL_VERSION} supports Windows (primary) and Linux hosts only.\n"
        )
        sys.exit(2)


def _quiet_unraisable_hook(unraisable: Any) -> None:
    if getattr(unraisable, "exc_type", None) in (KeyboardInterrupt, SystemExit, BrokenPipeError):
        return
    sys.__unraisablehook__(unraisable)


def _sigint_handler(signum: int, frame: Any) -> None:
    """Cleanly handle Ctrl-C (SIGINT) without stack trace noise."""
    global _INTERRUPTED
    if _INTERRUPTED:
        return
    _INTERRUPTED = True
    raise KeyboardInterrupt()


def install_clean_signal_handlers() -> None:
    """Register clean Ctrl-C (SIGINT) and SIGTERM handlers."""
    enforce_supported_platform()
    try:
        sys.unraisablehook = _quiet_unraisable_hook
        signal.signal(signal.SIGINT, _sigint_handler)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, _sigint_handler)
    except Exception:
        pass


def fail_gracefully(message: str, hint: Optional[str] = None, exit_code: int = 1) -> None:
    """Print a structured diagnostic error message, release any OpenCL resources, and exit cleanly."""
    try:
        from math_backends import teardown_math_backends
        teardown_math_backends()
    except Exception:
        pass
    sys.stderr.write(f"[!] Configuration / Argument Error: {message}\n")
    if hint:
        sys.stderr.write(f"    Guidance: {hint}\n")
    sys.stderr.flush()
    sys.exit(exit_code)


def require_valid_path(
    raw_path: Optional[str | Path],
    arg_name: str,
    must_exist: bool = True,
    expect_dir: Optional[bool] = None,
) -> Path:
    """Validate a required CLI or scheme path argument and fail gracefully if missing or invalid."""
    if raw_path is None or str(raw_path).strip() == "":
        fail_gracefully(
            f"Missing required path argument `{arg_name}`.",
            f"Pass `{arg_name} <path>` on the command line or specify it in your `.scheme.json` file.",
        )
    p = Path(str(raw_path)).expanduser().resolve()
    if must_exist and not p.exists():
        fail_gracefully(
            f"Path for `{arg_name}` does not exist: {p}",
            f"Verify that `{p}` exists and is readable before running the pipeline.",
        )
    if must_exist and expect_dir is True and not p.is_dir():
        fail_gracefully(
            f"Expected a directory for `{arg_name}`, but found a file: {p}",
            f"Pass a valid directory path to `{arg_name}`.",
        )
    if must_exist and expect_dir is False and not p.is_file():
        fail_gracefully(
            f"Expected a file for `{arg_name}`, but found a directory: {p}",
            f"Pass a valid file path to `{arg_name}`.",
        )
    return p


def parse_partition_size_string(val: Any, source_label: str) -> int:
    """
    Parse a partition size specification (e.g., `"3 MBytes"`, `"3MB"`, `3145728`) into exact bytes.
    Strictly rejects bit/megabit units or unsupported partition sizes (only 3 MBytes = 3,145,728 B is supported).
    """
    if val is None:
        fail_gracefully(
            f"Missing required partition size attribute in {source_label}.",
            "Specify `\"partition_1\": \"3 MBytes\"` and `\"partition_1_bytes\": 3145728` (or `\"target_partition_bytes\": 3145728`).",
        )
    if isinstance(val, (int, float)):
        b_val = int(val)
    else:
        s = str(val).strip()
        if not s:
            fail_gracefully(
                f"Empty partition size attribute in {source_label}.",
                "Specify `\"partition_1\": \"3 MBytes\"` (3,145,728 bytes).",
            )
        m = re.match(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z]*)\s*$", s)
        if not m:
            fail_gracefully(
                f"Malformed partition size `{val}` in {source_label}.",
                "Use `\"3 MBytes\"`, `\"3MB\"`, or `3145728`.",
            )
        num = float(m.group(1))
        unit = m.group(2).lower()
        if unit in ("", "b", "byte", "bytes"):
            b_val = int(round(num))
        elif unit in ("kb", "kbyte", "kbytes", "kib"):
            b_val = int(round(num * 1024))
        elif unit in ("mb", "mbyte", "mbytes", "mib"):
            b_val = int(round(num * 1024 * 1024))
        elif "bit" in unit:
            fail_gracefully(
                f"Unsupported megabit/bit partition unit `{val}` in {source_label}.",
                "Only the single 3 MByte (3,145,728 bytes) partition size is supported per hardware spec.",
            )
        else:
            fail_gracefully(
                f"Unknown partition unit `{unit}` in `{val}` ({source_label}).",
                "Use `\"3 MBytes\"` or `3145728` bytes.",
            )

    if b_val != SUPPORTED_PARTITION_BYTES:
        fail_gracefully(
            f"Unsupported partition size `{b_val:,} bytes` in {source_label}.",
            f"Only the single 3 MByte ({SUPPORTED_PARTITION_BYTES:,} bytes) partition is supported per the hardware specification.",
        )
    return b_val


@dataclass
class TargetHardwareSpec:
    hw_scheme_id: str
    hw_scheme_path: Optional[Path]
    chip_name: str
    soc_vendor: str
    cpu_architecture: str
    cpu_freq_mhz: int
    flash_total: str
    flash_total_bytes: int
    psram_total: str
    psram_total_bytes: int
    sram_total: str
    sram_total_bytes: int
    partition_1: str
    partition_1_bytes: int
    partition_1_label: str
    panel: str
    controller: str
    width_px: int
    height_px: int
    dpi: float
    safe_margin_px: int
    usable_width_px: int
    color_depth_bpp: int
    lvgl_color_format: str


def load_and_validate_hardware_scheme(
    scheme_cfg: Optional[dict],
    hw_scheme_cli: Optional[str | Path] = None,
    repo_root: Optional[Path] = None,
    scheme_path: Optional[Path] = None,
) -> TargetHardwareSpec:
    """
    Strictly validate target hardware and partition attributes with ZERO hardcoded defaults.
    Loads the referenced hardware scheme JSON (`esp32s3-N8R8-hw_scheme.json` or `generic_hw.json` / `generic_hw.json`)
    and validates `target_display` in `.scheme.json`.
    If the partition constraint (`partition_1` / `partition_1_bytes` / `target_partition_bytes`) or any required
    hardware/display attribute is removed or missing, fails immediately via `fail_gracefully()`.
    """
    if repo_root is None:
        script_dir = Path(__file__).resolve().parent
        repo_root = script_dir.parent.parent if script_dir.name == "fonts" else script_dir.parent

    s_name = scheme_path.name if scheme_path else "scheme.json"
    if not isinstance(scheme_cfg, dict):
        fail_gracefully(
            f"Missing or invalid scheme configuration object in `{s_name}`.",
            "Pass a valid `.scheme.json` file and hardware scheme (`esp32s3-N8R8-hw_scheme.json` or `generic_hw.json`).",
        )

    hw_ref = hw_scheme_cli or scheme_cfg.get("hardware_scheme")
    if isinstance(hw_ref, str) and hw_ref.strip().lower() == "genaric_hw.json":
        hw_ref = "generic_hw.json"
    hw_data: dict = {}
    resolved_hw_path: Optional[Path] = None

    if hw_ref:
        cand_paths = [Path(str(hw_ref))]
        if not cand_paths[0].is_absolute():
            if scheme_path:
                cand_paths.append(scheme_path.parent / str(hw_ref))
                cand_paths.append(scheme_path.parent.parent / str(hw_ref))
            cand_paths.append(repo_root / str(hw_ref))
            cand_paths.append(repo_root / "schemes" / str(hw_ref))
        for cp in cand_paths:
            if cp.is_file():
                resolved_hw_path = cp.resolve()
                break
        if resolved_hw_path is None:
            fail_gracefully(
                f"Hardware scheme file `{hw_ref}` referenced by `{s_name}` does not exist.",
                "Ensure `esp32s3-N8R8-hw_scheme.json` or `generic_hw.json` exists in the repository root or pass `--hw-scheme <path>`.",
            )
        try:
            hw_data = json.loads(resolved_hw_path.read_text(encoding="utf-8"))
        except Exception as exc:
            fail_gracefully(f"Failed to parse hardware scheme JSON `{resolved_hw_path}`: {exc}")

    tdisp = scheme_cfg.get("target_display")
    if not hw_data and not isinstance(tdisp, dict):
        fail_gracefully(
            f"Missing `hardware_scheme` reference in `{s_name}`.",
            "Add `\"hardware_scheme\": \"esp32s3-N8R8-hw_scheme.json\"` (or `\"generic_hw.json\"`) to `.scheme.json` or pass `--hw-scheme <path>`.",
        )

    part_bytes: Optional[int] = None
    part_label_str = "3 MBytes"

    if hw_data:
        hw_src = f"hardware scheme `{resolved_hw_path.name if resolved_hw_path else hw_ref}`"
        if "partition_1" not in hw_data and "partition_1_bytes" not in hw_data:
            fail_gracefully(
                f"Missing required `partition_1` / `partition_1_bytes` attribute in {hw_src}.",
                "Set `\"partition_1\": \"3 MBytes\"` and `\"partition_1_bytes\": 3145728` in the hardware scheme JSON.",
            )
        if "partition_1" in hw_data:
            part_bytes = parse_partition_size_string(hw_data["partition_1"], hw_src)
            part_label_str = str(hw_data["partition_1"]).strip()
        if "partition_1_bytes" in hw_data:
            b_chk = parse_partition_size_string(hw_data["partition_1_bytes"], hw_src)
            part_bytes = b_chk
    elif isinstance(tdisp, dict):
        td_src = f"`target_display` in `{s_name}`"
        if "partition_1" in tdisp and tdisp["partition_1"] is not None:
            part_bytes = parse_partition_size_string(tdisp["partition_1"], td_src)
            part_label_str = str(tdisp["partition_1"]).strip()
        if "partition_1_bytes" in tdisp and tdisp["partition_1_bytes"] is not None:
            part_bytes = parse_partition_size_string(tdisp["partition_1_bytes"], td_src)
        if "target_partition_bytes" in tdisp and tdisp["target_partition_bytes"] is not None:
            part_bytes = parse_partition_size_string(tdisp["target_partition_bytes"], td_src)

    if part_bytes is None or part_bytes != SUPPORTED_PARTITION_BYTES:
        fail_gracefully(
            f"Missing or invalid 3 MByte partition constraint in `{s_name}`.",
            f"Only the single 3 MByte ({SUPPORTED_PARTITION_BYTES:,} bytes) partition is supported.",
        )

    disp_block = hw_data.get("display", {}) if isinstance(hw_data.get("display"), dict) else {}
    tdisp_dict = tdisp if isinstance(tdisp, dict) else {}

    def _req_field(keys: Sequence[str], field_desc: str) -> Any:
        # Authoritative root hardware scheme (`hw_data` & `disp_block`) takes strict precedence
        for k in keys:
            if k in disp_block and disp_block[k] is not None and str(disp_block[k]).strip() != "":
                return disp_block[k]
            if k in hw_data and hw_data[k] is not None and str(hw_data[k]).strip() != "":
                return hw_data[k]
            if k in tdisp_dict and tdisp_dict[k] is not None and str(tdisp_dict[k]).strip() != "":
                return tdisp_dict[k]
        fail_gracefully(
            f"Missing required hardware/display attribute `{keys[0]}` ({field_desc}) in `{s_name}`.",
            "Provide full target hardware attributes via `esp32s3-N8R8-hw_scheme.json` or `generic_hw.json`.",
        )

    chip_name = str(_req_field(["chip_name", "target_soc"], "target microcontroller/chip name"))
    width_px = int(_req_field(["width_px"], "display horizontal width in pixels"))
    height_px = int(_req_field(["height_px"], "display vertical height in pixels"))
    dpi = float(_req_field(["dpi"], "display pixel density in DPI"))
    safe_margin_px = int(_req_field(["safe_margin_px"], "display safe horizontal margin in pixels"))
    color_depth_bpp = int(_req_field(["color_depth_bpp"], "display color depth in bits per pixel"))
    lvgl_color_format = str(_req_field(["lvgl_color_format"], "LVGL color format identifier"))
    panel = str(_req_field(["panel", "display_panel"], "display panel model"))

    usable_width_px = int(tdisp_dict.get("usable_width_px") or disp_block.get("usable_width_px") or (width_px - 2 * safe_margin_px))
    hw_scheme_id = str(hw_data.get("hw_scheme_id") or tdisp_dict.get("hw_scheme_id") or chip_name)
    soc_vendor = str(hw_data.get("soc_vendor") or tdisp_dict.get("soc_vendor") or "Embedded Target")
    cpu_arch = str(hw_data.get("cpu_architecture") or tdisp_dict.get("cpu_architecture") or "32-bit MCU")
    cpu_freq = int(hw_data.get("cpu_freq_mhz") or tdisp_dict.get("cpu_freq_mhz") or 240)
    flash_tot = str(hw_data.get("flash_total") or tdisp_dict.get("flash_total") or "8 MBytes")
    flash_tot_b = int(hw_data.get("flash_total_bytes") or tdisp_dict.get("flash_total_bytes") or (8 * 1024 * 1024))
    psram_tot = str(hw_data.get("psram_total") or tdisp_dict.get("psram_total") or "8 MBytes")
    psram_tot_b = int(hw_data.get("psram_total_bytes") or tdisp_dict.get("psram_total_bytes") or (8 * 1024 * 1024))
    sram_tot = str(hw_data.get("sram_total") or tdisp_dict.get("sram_total") or "512 KBytes")
    sram_tot_b = int(hw_data.get("sram_total_bytes") or tdisp_dict.get("sram_total_bytes") or (512 * 1024))
    part_desc = str(hw_data.get("partition_1_label") or tdisp_dict.get("partition_1_label") or "3 MByte Flash Partition")
    controller = str(disp_block.get("controller") or tdisp_dict.get("controller") or "Monochrome EPD Controller")

    return TargetHardwareSpec(
        hw_scheme_id=hw_scheme_id,
        hw_scheme_path=resolved_hw_path,
        chip_name=chip_name,
        soc_vendor=soc_vendor,
        cpu_architecture=cpu_arch,
        cpu_freq_mhz=cpu_freq,
        flash_total=flash_tot,
        flash_total_bytes=flash_tot_b,
        psram_total=psram_tot,
        psram_total_bytes=psram_tot_b,
        sram_total=sram_tot,
        sram_total_bytes=sram_tot_b,
        partition_1=part_label_str,
        partition_1_bytes=part_bytes,
        partition_1_label=part_desc,
        panel=panel,
        controller=controller,
        width_px=width_px,
        height_px=height_px,
        dpi=dpi,
        safe_margin_px=safe_margin_px,
        usable_width_px=usable_width_px,
        color_depth_bpp=color_depth_bpp,
        lvgl_color_format=lvgl_color_format,
    )


@dataclass
class HostHardwareInfo:
    os_name: str
    cpu_cores: int
    available_ram_mb: int
    total_ram_mb: int
    shared_gpu_ram_mb: int
    avail_shared_gpu_ram_mb: int
    gpu_backend: str
    gpu_enabled: bool
    recommended_workers: int


def detect_host_hardware(requested_jobs: Optional[int] = None) -> HostHardwareInfo:
    """Detect CPU cores, available dynamic RAM, WDDM Shared GPU RAM (15.7 GB), and OpenCL/CUDA acceleration."""
    cpu_cores = os.cpu_count() or 4
    total_ram_mb = 8192
    avail_ram_mb = 4096

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
            total_ram_mb = int(stat.ullTotalPhys // (1024 * 1024))
            avail_ram_mb = int(stat.ullAvailPhys // (1024 * 1024))
        except Exception:
            pass
    elif Path("/proc/meminfo").is_file():
        try:
            mem_txt = Path("/proc/meminfo").read_text(encoding="utf-8", errors="ignore")
            for line in mem_txt.splitlines():
                if line.startswith("MemTotal:"):
                    total_ram_mb = int(line.split()[1]) // 1024
                elif line.startswith("MemAvailable:"):
                    avail_ram_mb = int(line.split()[1]) // 1024
        except Exception:
            pass

    shared_gpu_ram_mb = max(512, total_ram_mb // 2)
    avail_shared_gpu_ram_mb = max(256, min(avail_ram_mb - 512, shared_gpu_ram_mb))

    gpu_backend = "CPU-SIMD (NumPy/OpenCV)"
    gpu_enabled = False
    pref = os.environ.get("EPD_FONT_ACCEL", "auto").strip().lower()
    if pref != "cpu":
        try:
            from math_backends import enumerate_opencl_devices
            devs = enumerate_opencl_devices()
            if devs:
                dev_summaries = [f"{d.device_name} ({d.compute_units} CUs)" for d in devs]
                gpu_backend = f"PyOpenCL 3D NDRange [{' + '.join(dev_summaries)}]"
                gpu_enabled = True
        except Exception:
            pass

    if not gpu_enabled and pref != "cpu":
        try:
            import cv2
            if hasattr(cv2, "cuda") and cv2.cuda.getCudaEnabledDeviceCount() > 0:
                gpu_backend = f"NVIDIA CUDA ({cv2.cuda.getCudaEnabledDeviceCount()} device(s))"
                gpu_enabled = True
            elif hasattr(cv2, "ocl") and cv2.ocl.haveOpenCL():
                gpu_backend = "OpenCL UMat Hardware Acceleration"
                gpu_enabled = True
        except Exception:
            pass

    ram_limited_workers = max(1, avail_ram_mb // 256)
    rec_workers = min(cpu_cores, ram_limited_workers)
    if requested_jobs and requested_jobs > 0:
        rec_workers = requested_jobs

    return HostHardwareInfo(
        os_name="Windows" if os.name == "nt" else "Linux",
        cpu_cores=cpu_cores,
        available_ram_mb=avail_ram_mb,
        total_ram_mb=total_ram_mb,
        shared_gpu_ram_mb=shared_gpu_ram_mb,
        avail_shared_gpu_ram_mb=avail_shared_gpu_ram_mb,
        gpu_backend=gpu_backend,
        gpu_enabled=gpu_enabled,
        recommended_workers=max(1, rec_workers),
    )


def _worker_process_init_gpu() -> None:
    """
    Initializer for the SINGLE Persistent GPU Worker Process (`max_workers=1`):
      1. Ignores `SIGINT` (`Ctrl+C`) in child process so the parent coordinator handles Ctrl+C cleanly.
      2. Sets `EPD_FONT_WORKER_ROLE="gpu"` so this single worker owns the `Ellesmere` discrete GPU
         context (32 CUs, 4 CommandQueues, 3D NDRange, 15.7 GB Shared GPU Memory).
      3. Registers `teardown_math_backends` with `atexit`.
    """
    try:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    except Exception:
        pass
    os.environ["EPD_FONT_WORKER_ROLE"] = "gpu"
    try:
        from math_backends import select_math_backend, teardown_math_backends
        select_math_backend("opencl")
        atexit.register(teardown_math_backends)
    except Exception:
        pass


def _worker_process_init_cpu() -> None:
    """
    Initializer for ProcessPoolExecutor CPU workers:
      1. Sets `signal.signal(signal.SIGINT, signal.SIG_IGN)` so pressing `Ctrl+C` in the console
         does NOT cause 12 child worker processes to dump `KeyboardInterrupt` tracebacks from
         `multiprocessing.queues.get()` (`_winapi.WaitForMultipleObjects`).
      2. Sets `EPD_FONT_WORKER_ROLE="cpu"` so child CPU workers NEVER allocate competing
         discrete GPU OpenCL contexts on `Ellesmere` (`0` VRAM bloat and `0` WDDM context thrashing).
      3. Registers deterministic teardown on worker exit.
    """
    try:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    except Exception:
        pass
    os.environ["EPD_FONT_WORKER_ROLE"] = "cpu"
    os.environ["EPD_FONT_ACCEL"] = "cpu"
    os.environ["OPENCV_OPENCL_RUNTIME"] = "disabled"
    try:
        import cv2
        if hasattr(cv2, "ocl"):
            cv2.ocl.setUseOpenCL(False)
    except Exception:
        pass
    try:
        from math_backends import select_math_backend, teardown_math_backends
        select_math_backend("cpu")
        atexit.register(teardown_math_backends)
    except Exception:
        pass


def _teardown_worker_opencl_noop(_: Any = None) -> int:
    """Explicitly release OpenCL contexts and buffers inside a worker process before pool shutdown."""
    try:
        from math_backends import teardown_math_backends
        return teardown_math_backends()
    except Exception:
        return 0


def _terminate_executor_processes(pool: Any) -> None:
    """
    Explicitly terminate and join all child `SpawnProcess` / `ForkProcess` worker processes
    inside a `ProcessPoolExecutor` so zero orphaned `python.exe` processes or GPU allocations
    remain in Windows Task Manager after completion or `Ctrl+C`.
    """
    if pool is None:
        return
    procs = getattr(pool, "_processes", None)
    if not isinstance(procs, dict):
        return
    for p in list(procs.values()):
        try:
            if p is not None and p.is_alive():
                p.terminate()
        except Exception:
            pass
    for p in list(procs.values()):
        try:
            if p is not None:
                p.join(timeout=1.5)
                if p.is_alive() and hasattr(p, "kill"):
                    p.kill()
        except Exception:
            pass


def run_parallel_tasks(
    worker_fn: Callable[[dict], Any],
    tasks: Sequence[dict],
    max_workers: int = 4,
    use_threads: bool = False,
) -> List[Any]:
    """
    Execute tasks across a Hybrid Single-Owner GPU + Multi-Core CPU Work-Stealing Pool:
      - When an OpenCL GPU/CPU accelerator is available and `use_threads` is False:
          * Spawns `gpu_pool` (`max_workers=1`, `EPD_FONT_WORKER_ROLE="gpu"`) which owns the
            single persistent OpenCL context (`Ellesmere` 32 CUs, 4 CommandQueues, 3D NDRange,
            15.7 GB Shared GPU Memory) and pulls heavy icon/SDF strikes from the front of the deque.
          * Spawns `cpu_pool` (`max_workers=max(1, max_workers - 1)`, `EPD_FONT_WORKER_ROLE="cpu"`)
            which runs on the host CPU cores (`AMD Ryzen 5 5600G` 12 threads) and pulls lightweight
            `Terminus` and small text strikes from the back of the deque, with dynamic work-stealing
            when the two pools meet.
      - Before returning, explicitly runs `_teardown_worker_opencl_noop` on `gpu_pool` so all
        GPU/Shared RAM buffers and contexts are deterministically `.release()`d (`0 MB` post-exit).
      - On `Ctrl+C` (`KeyboardInterrupt`), immediately cancels pending futures, terminates and joins
        all child worker processes (`_terminate_executor_processes`), releases all OpenCL/Shared RAM
        allocations (`teardown_math_backends()`), and prints a single clean teardown message with
        zero tracebacks.
    """
    if not tasks:
        return []

    if len(tasks) == 1 or max_workers <= 1:
        results = []
        try:
            for t in tasks:
                if _INTERRUPTED:
                    raise KeyboardInterrupt()
                results.append(worker_fn(t))
            return results
        except KeyboardInterrupt:
            try:
                from math_backends import teardown_math_backends
                teardown_math_backends()
            except Exception:
                pass
            sys.stderr.write(
                "\n[!] Execution interrupted by user (Ctrl+C). OpenCL/host memory released cleanly.\n"
            )
            sys.stderr.flush()
            sys.exit(130)
        finally:
            try:
                from math_backends import teardown_math_backends
                teardown_math_backends()
            except Exception:
                pass

    # Sort tasks by compute density descending: left of deque = heaviest GPU tasks, right = lightest CPU tasks
    indexed_tasks: List[Tuple[int, dict]] = list(enumerate(tasks))
    has_opencl_gpu = False
    try:
        from opencl_dispatcher import get_devices, score_task_compute_density
        indexed_tasks.sort(key=lambda pair: score_task_compute_density(pair[1]), reverse=True)
        gpu_dev, cpu_ocl_dev, _ = get_devices()
        has_opencl_gpu = (gpu_dev is not None or cpu_ocl_dev is not None)
    except Exception:
        pass

    ordered_results: List[Any] = [None] * len(tasks)

    # Thread-based execution path
    if use_threads or not has_opencl_gpu or max_workers < 2:
        if use_threads:
            pool: Any = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        else:
            prev_sig = signal.signal(signal.SIGINT, signal.SIG_IGN)
            try:
                pool = concurrent.futures.ProcessPoolExecutor(
                    max_workers=max_workers,
                    initializer=_worker_process_init_cpu,
                )
            finally:
                signal.signal(signal.SIGINT, prev_sig)
        futures_map: Dict[concurrent.futures.Future, int] = {}
        try:
            for orig_idx, t in indexed_tasks:
                fut = pool.submit(worker_fn, t)
                futures_map[fut] = orig_idx

            for fut in concurrent.futures.as_completed(futures_map):
                if _INTERRUPTED:
                    raise KeyboardInterrupt()
                orig_idx = futures_map[fut]
                ordered_results[orig_idx] = fut.result()

            pool.shutdown(wait=True)
            return ordered_results
        except KeyboardInterrupt:
            for fut in futures_map:
                fut.cancel()
            if not use_threads:
                _terminate_executor_processes(pool)
            pool.shutdown(wait=False, cancel_futures=True)
            try:
                from math_backends import teardown_math_backends
                teardown_math_backends()
            except Exception:
                pass
            sys.stderr.write(
                "\n[!] Execution interrupted by user (Ctrl+C). Workers stopped and OpenCL/host memory released cleanly.\n"
            )
            sys.stderr.flush()
            sys.exit(130)
        except Exception:
            for fut in futures_map:
                fut.cancel()
            if not use_threads:
                _terminate_executor_processes(pool)
            pool.shutdown(wait=False, cancel_futures=True)
            raise
        finally:
            try:
                from math_backends import teardown_math_backends
                teardown_math_backends()
            except Exception:
                pass
            gc.collect()

    # Hybrid Dual-Pool Work-Stealing Execution (`1` Persistent GPU Worker + `max_workers - 1` CPU Workers)
    cpu_workers = max(1, max_workers - 1)
    prev_sig = signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        gpu_pool = concurrent.futures.ProcessPoolExecutor(
            max_workers=1,
            initializer=_worker_process_init_gpu,
        )
        cpu_pool = concurrent.futures.ProcessPoolExecutor(
            max_workers=cpu_workers,
            initializer=_worker_process_init_cpu,
        )
    finally:
        signal.signal(signal.SIGINT, prev_sig)
    task_deque: deque[Tuple[int, dict]] = deque(indexed_tasks)
    in_flight: Dict[concurrent.futures.Future, Tuple[int, str]] = {}

    try:
        # Seed the single persistent GPU worker from the heavy front of the deque
        if task_deque:
            o_idx, t_item = task_deque.popleft()
            in_flight[gpu_pool.submit(worker_fn, t_item)] = (o_idx, "gpu")

        # Seed the CPU workers from the lightweight back of the deque
        for _ in range(cpu_workers):
            if not task_deque:
                break
            o_idx, t_item = task_deque.pop()
            in_flight[cpu_pool.submit(worker_fn, t_item)] = (o_idx, "cpu")

        while in_flight:
            if _INTERRUPTED:
                raise KeyboardInterrupt()
            done, _ = concurrent.futures.wait(
                in_flight.keys(),
                return_when=concurrent.futures.FIRST_COMPLETED,
            )
            for fut in done:
                o_idx, pool_tag = in_flight.pop(fut)
                ordered_results[o_idx] = fut.result()
                if task_deque:
                    if pool_tag == "gpu":
                        next_idx, next_task = task_deque.popleft()
                        in_flight[gpu_pool.submit(worker_fn, next_task)] = (next_idx, "gpu")
                    else:
                        next_idx, next_task = task_deque.pop()
                        in_flight[cpu_pool.submit(worker_fn, next_task)] = (next_idx, "cpu")

        # Explicitly release OpenCL buffers/contexts inside the persistent GPU worker before shutdown
        try:
            gpu_pool.submit(_teardown_worker_opencl_noop, None).result(timeout=3.0)
        except Exception:
            pass
        gpu_pool.shutdown(wait=True)
        cpu_pool.shutdown(wait=True)
        return ordered_results
    except KeyboardInterrupt:
        for fut in in_flight:
            fut.cancel()
        _terminate_executor_processes(gpu_pool)
        _terminate_executor_processes(cpu_pool)
        gpu_pool.shutdown(wait=False, cancel_futures=True)
        cpu_pool.shutdown(wait=False, cancel_futures=True)
        try:
            from math_backends import teardown_math_backends
            teardown_math_backends()
        except Exception:
            pass
        sys.stderr.write(
            "\n[!] Execution interrupted by user (Ctrl+C). Workers stopped and OpenCL/host memory released cleanly.\n"
        )
        sys.stderr.flush()
        sys.exit(130)
    except Exception:
        for fut in in_flight:
            fut.cancel()
        _terminate_executor_processes(gpu_pool)
        _terminate_executor_processes(cpu_pool)
        gpu_pool.shutdown(wait=False, cancel_futures=True)
        cpu_pool.shutdown(wait=False, cancel_futures=True)
        try:
            from math_backends import teardown_math_backends
            teardown_math_backends()
        except Exception:
            pass
        raise
    finally:
        try:
            from math_backends import teardown_math_backends
            teardown_math_backends()
        except Exception:
            pass
        gc.collect()


def index_font_files_recursive(search_roots: Sequence[Path]) -> Dict[str, Path]:
    """
    Recursively scan one or more directories for font assets (.ttf, .otf, .ttc, .otc, .bdf, .woff)
    and metadata files without modifying any static source file.
    """
    index: Dict[str, Path] = {}
    for root in search_roots:
        if not root or not root.exists():
            continue
        if root.is_file():
            index.setdefault(root.name, root.resolve())
            index.setdefault(root.name.lower(), root.resolve())
            index.setdefault(root.stem.lower(), root.resolve())
            continue
        for dirpath, _, filenames in os.walk(root):
            dp = Path(dirpath)
            for fn in filenames:
                full = (dp / fn).resolve()
                index.setdefault(fn, full)
                index.setdefault(fn.lower(), full)
                index.setdefault(full.stem.lower(), full)
                rel_key = f"{dp.name}/{fn}"
                index.setdefault(rel_key, full)
                index.setdefault(rel_key.lower(), full)
    return index


def resolve_font_file_recursive(
    target_name: str,
    search_roots: Sequence[Path],
    cached_index: Optional[Dict[str, Path]] = None,
) -> Optional[Path]:
    """Resolve a font filename or stem recursively across all search roots."""
    for root in search_roots:
        if root and root.is_dir():
            direct = root / target_name
            if direct.is_file():
                return direct.resolve()
    idx = cached_index if cached_index is not None else index_font_files_recursive(search_roots)
    for cand_key in (
        target_name,
        target_name.lower(),
        Path(target_name).name,
        Path(target_name).name.lower(),
        Path(target_name).stem.lower(),
    ):
        if cand_key in idx and idx[cand_key].is_file():
            return idx[cand_key]
    return None


def collect_all_licenses_recursive(
    search_roots: Sequence[Path],
    dest_license_dirs: Sequence[Path],
    repo_root: Optional[Path] = None,
) -> List[str]:
    """
    Recursively discover all license files (`LICENSE*`, `OFL*`, `COPYING*`, `*License*.txt`)
    across `assets/`, `build/static_ttfs/`, and the repository root `LICENSE`, and copy them
    into every target distribution/build license directory.
    """
    for d in dest_license_dirs:
        d.mkdir(parents=True, exist_ok=True)

    copied_names: List[str] = []
    seen_targets = set()

    if repo_root and (repo_root / "LICENSE").is_file():
        dst_name = "epd-font_MIT_LICENSE.txt"
        for d in dest_license_dirs:
            shutil.copy2(repo_root / "LICENSE", d / dst_name)
        copied_names.append(dst_name)
        seen_targets.add(dst_name.lower())

    for root in search_roots:
        if not root or not root.exists():
            continue
        for dirpath, _, filenames in os.walk(root):
            dp = Path(dirpath)
            if "licenses" in dp.parts:
                for fn in filenames:
                    src_f = dp / fn
                    if src_f.is_file() and fn.lower() not in seen_targets:
                        for d in dest_license_dirs:
                            dst_f = d / fn
                            if src_f.resolve() != dst_f.resolve():
                                shutil.copy2(src_f, dst_f)
                        copied_names.append(fn)
                        seen_targets.add(fn.lower())
                continue
            for fn in filenames:
                low = fn.lower()
                if any(k in low for k in ("license", "ofl.txt", "copying")):
                    src_f = dp / fn
                    parent_tag = dp.name.replace(" ", "_")
                    dst_name = f"{parent_tag}_{fn}" if not fn.endswith(".txt") else f"{parent_tag}_{fn}"
                    if not dst_name.lower().endswith((".txt", ".md")):
                        dst_name += ".txt"
                    if dst_name.lower() not in seen_targets:
                        for d in dest_license_dirs:
                            dst_f = d / dst_name
                            if src_f.resolve() != dst_f.resolve():
                                shutil.copy2(src_f, dst_f)
                        copied_names.append(dst_name)
                        seen_targets.add(dst_name.lower())
    return sorted(copied_names)
