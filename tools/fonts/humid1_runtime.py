#!/usr/bin/env python3
"""
humid1_runtime.py (v1.0.23)
==========================
A 1-bit EPD font generator and asset pipeline for embedded displays.
Repository : https://github.com/Humidyne-Labs/epd-font
Authors    : Humiditron (https://github.com/humiditron) & AI/LLM Development Partner
License    : MIT License

Host Hardware Detection (Multi-Device OpenCL GPU/CPU + Shared GPU RAM + Multi-Core CPU),
Target Embedded Hardware Scheme Validator (`esp32s3-N8R8-hw_scheme.json` & `generic_hw.json`),
Single-Owner GPU + Multi-Core CPU Work-Stealing Dispatcher (`run_parallel_tasks`),
Clean Signal/Ctrl-C Interruption Handler (Zero Worker Traceback Noise + Deterministic Teardown),
Recursive Asset/License Discovery, and Strict Zero-Default Argument/Path Validation Module (`v1.0.23`).
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

TOOL_VERSION = "1.0.23"
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
            "Specify `\"partition_bytes\": 3145728` in hardware scheme JSON.",
        )
    if isinstance(val, (int, float)):
        b_val = int(val)
    else:
        s = str(val).strip()
        if not s:
            fail_gracefully(
                f"Empty partition size attribute in {source_label}.",
                "Specify `\"partition_bytes\": 3145728` (3 MBytes).",
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
    partition_bytes: int
    panel: str
    width_px: int
    height_px: int
    dpi: float
    safe_margin_px: int
    usable_width_px: int
    color_depth_bpp: int
    lvgl_color_format: str

    @property
    def partition_label(self) -> str:
        return f"{self.partition_bytes // (1024 * 1024)} MBytes"


REQUIRED_HW_TOP_KEYS = {
    "schema_version",
    "hw_scheme_id",
    "description",
    "chip_name",
    "soc_vendor",
    "partition_bytes",
    "display",
}

REQUIRED_HW_DISPLAY_KEYS = {
    "panel",
    "width_px",
    "height_px",
    "dpi",
    "safe_margin_px",
    "color_depth_bpp",
    "lvgl_color_format",
}

REQUIRED_SCHEME_TOP_KEYS = {
    "schema_version",
    "scheme_id",
    "project_brand",
    "description",
    "spdx_license",
    "hardware_scheme",
    "raster_config",
    "output_branding",
    "character_sets",
    "strikes",
}

REQUIRED_RASTER_CONFIG_KEYS = {
    "pipeline",
    "math_backend",
    "threshold",
    "gamma",
    "normal_weight",
    "bold_weight",
    "italic_weight",
    "patches_file",
    "ascii_patches_dir",
    "sheet_debug",
    "char_debug",
    "debug_stages",
}

VALID_PIPELINE_VALUES = {
    "raw-unhinted",
    "raw-hinted",
    "svg-potrace",
    "svg-potrace-jfa",
    "mdf",
    "msdf",
    "sdf-smoothstep",
    "adf-biquadratic",
    "otsu-adaptive",
    "all",
    "all-debug",
}

VALID_MATH_BACKEND_VALUES = {
    "auto",
    "cpu",
    "gpu",
    "hybrid",
    "sync",
}


def validate_scheme_config(scheme_cfg: Any, scheme_path: Optional[Path] = None) -> dict:
    """
    Strictly validate a profile `.scheme.json` dictionary against the Singular Configuration
    Variable Matrix (`v1.0.23`) with ZERO assumed defaults and ZERO dangling/unknown keys.
    """
    s_name = scheme_path.name if scheme_path else "scheme.json"
    if not isinstance(scheme_cfg, dict):
        fail_gracefully(
            f"Invalid JSON root in `{s_name}`: expected an object.",
            "Ensure the `.scheme.json` file contains a valid JSON object.",
        )

    missing_top = sorted(REQUIRED_SCHEME_TOP_KEYS - set(scheme_cfg.keys()))
    if missing_top:
        fail_gracefully(
            f"Missing required top-level configuration key(s) {missing_top} in `{s_name}` (default values are not assumed).",
            "Refer to the Master Configuration Matrix in `README.md` / `docs/HOW_TO_GUIDE.md`.",
        )

    unknown_top = sorted(set(scheme_cfg.keys()) - REQUIRED_SCHEME_TOP_KEYS - {"screen_audit_rows"})
    if unknown_top:
        fail_gracefully(
            f"Unknown or redundant top-level key(s) {unknown_top} in `{s_name}`.",
            "Remove legacy/dangling keys (such as `target_display`) so each variable is defined in exactly 1 place.",
        )

    rcfg = scheme_cfg.get("raster_config")
    if not isinstance(rcfg, dict):
        fail_gracefully(f"`raster_config` in `{s_name}` must be a JSON object.")

    missing_rcfg = sorted(REQUIRED_RASTER_CONFIG_KEYS - set(rcfg.keys()))
    if missing_rcfg:
        fail_gracefully(
            f"Missing required `raster_config` variable(s) {missing_rcfg} in `{s_name}` (default values are not assumed).",
            "Specify all 12 `raster_config` variables explicitly in `.scheme.json`.",
        )

    unknown_rcfg = sorted(set(rcfg.keys()) - REQUIRED_RASTER_CONFIG_KEYS)
    if unknown_rcfg:
        fail_gracefully(
            f"Unknown or duplicate `raster_config` variable(s) {unknown_rcfg} in `{s_name}`.",
            "Remove legacy duplicate keys (such as `raster_mode` or `condensed_width`) per the Singular Configuration Matrix.",
        )

    pipe_val = str(rcfg["pipeline"]).strip().lower()
    if pipe_val not in VALID_PIPELINE_VALUES:
        fail_gracefully(
            f"Invalid `raster_config.pipeline` value `'{rcfg['pipeline']}'` in `{s_name}`.",
            f"Must be one of: {sorted(VALID_PIPELINE_VALUES)}.",
        )

    mb_val = str(rcfg["math_backend"]).strip().lower()
    if mb_val not in VALID_MATH_BACKEND_VALUES:
        fail_gracefully(
            f"Invalid `raster_config.math_backend` value `'{rcfg['math_backend']}'` in `{s_name}`.",
            f"Must be one of: {sorted(VALID_MATH_BACKEND_VALUES)}.",
        )

    thresh = rcfg["threshold"]
    if not isinstance(thresh, int) or isinstance(thresh, bool) or not (1 <= thresh <= 254):
        fail_gracefully(
            f"Invalid `raster_config.threshold` value `{thresh}` in `{s_name}`.",
            "Must be an integer in `[1..254]` (e.g., `128`).",
        )

    gamma = rcfg["gamma"]
    if not isinstance(gamma, (int, float)) or isinstance(gamma, bool) or not (0.20 <= float(gamma) <= 3.00):
        fail_gracefully(
            f"Invalid `raster_config.gamma` value `{gamma}` in `{s_name}`.",
            "Must be a number in `[0.20..3.00]` (e.g., `1.0`).",
        )

    for w_key in ("normal_weight", "bold_weight", "italic_weight"):
        wv = rcfg[w_key]
        if not isinstance(wv, int) or isinstance(wv, bool) or not (100 <= wv <= 900):
            fail_gracefully(
                f"Invalid `raster_config.{w_key}` value `{wv}` in `{s_name}`.",
                "Must be an integer OpenType weight in `[100..900]` (e.g., `500`, `800`, `600`).",
            )

    for b_key in ("sheet_debug", "char_debug", "debug_stages"):
        if not isinstance(rcfg[b_key], bool):
            fail_gracefully(
                f"Invalid `raster_config.{b_key}` value `{rcfg[b_key]}` in `{s_name}`.",
                "Must be a JSON boolean (`true` or `false`).",
            )

    for s_key in ("patches_file", "ascii_patches_dir"):
        if not isinstance(rcfg[s_key], str) or not rcfg[s_key].strip():
            fail_gracefully(
                f"Invalid `raster_config.{s_key}` in `{s_name}`.",
                "Must be a non-empty relative path string.",
            )

    allowed_strike_pipes = (VALID_PIPELINE_VALUES - {"all", "all-debug"}) | {"exact-mono"}
    for idx, st in enumerate(scheme_cfg.get("strikes", [])):
        if isinstance(st, dict) and "pipeline" in st and st["pipeline"] is not None:
            sp_val = str(st["pipeline"]).strip().lower()
            if sp_val not in allowed_strike_pipes:
                fail_gracefully(
                    f"Invalid per-strike `strikes[{idx}].pipeline` value `'{st['pipeline']}'` in `{s_name}`.",
                    f"Must be one of: {sorted(allowed_strike_pipes)}.",
                )

    return rcfg


def load_and_validate_hardware_scheme(
    scheme_cfg: Optional[dict],
    hw_scheme_cli: Optional[str | Path] = None,
    repo_root: Optional[Path] = None,
    scheme_path: Optional[Path] = None,
) -> TargetHardwareSpec:
    """
    Strictly validate target hardware and partition attributes from the root hardware scheme
    JSON (`esp32s3-N8R8-hw_scheme.json` or `generic_hw.json`) with ZERO assumed defaults and
    ZERO duplicate keys.
    """
    if repo_root is None:
        script_dir = Path(__file__).resolve().parent
        repo_root = script_dir.parent.parent if script_dir.name == "fonts" else script_dir.parent

    s_name = scheme_path.name if scheme_path else "scheme.json"
    hw_ref = hw_scheme_cli
    if not hw_ref and isinstance(scheme_cfg, dict):
        hw_ref = scheme_cfg.get("hardware_scheme")

    if not hw_ref or not str(hw_ref).strip():
        fail_gracefully(
            f"Missing required `hardware_scheme` reference in `{s_name}` (default values are not assumed).",
            "Set 'hardware_scheme': 'esp32s3-N8R8-hw_scheme.json' (or 'generic_hw.json') in `.scheme.json`.",
        )

    cand_paths = [Path(str(hw_ref))]
    if not cand_paths[0].is_absolute():
        if scheme_path:
            cand_paths.append(scheme_path.parent / str(hw_ref))
            cand_paths.append(scheme_path.parent.parent / str(hw_ref))
        cand_paths.append(repo_root / str(hw_ref))
        cand_paths.append(repo_root / "schemes" / str(hw_ref))

    resolved_hw_path: Optional[Path] = None
    for cp in cand_paths:
        if cp.is_file():
            resolved_hw_path = cp.resolve()
            break

    if resolved_hw_path is None:
        fail_gracefully(
            f"Hardware scheme file `{hw_ref}` referenced by `{s_name}` does not exist.",
            "Ensure `esp32s3-N8R8-hw_scheme.json` or `generic_hw.json` exists in the repository root.",
        )

    try:
        hw_data = json.loads(resolved_hw_path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail_gracefully(f"Failed to parse hardware scheme JSON `{resolved_hw_path}`: {exc}")

    hw_src = f"`{resolved_hw_path.name}`"
    if not isinstance(hw_data, dict):
        fail_gracefully(f"Hardware scheme {hw_src} must be a JSON object.")

    missing_hw = sorted(REQUIRED_HW_TOP_KEYS - set(hw_data.keys()))
    if missing_hw:
        fail_gracefully(
            f"Missing required hardware attribute(s) {missing_hw} in {hw_src} (default values are not assumed).",
            "Refer to the Master Configuration Matrix in `README.md`.",
        )

    unknown_hw = sorted(set(hw_data.keys()) - REQUIRED_HW_TOP_KEYS)
    if unknown_hw:
        fail_gracefully(
            f"Unknown or duplicate hardware attribute(s) {unknown_hw} in {hw_src}.",
            "Keep only singular hardware keys (`partition_bytes`, `chip_name`, `soc_vendor`, `display`).",
        )

    part_bytes = parse_partition_size_string(hw_data["partition_bytes"], hw_src)
    disp = hw_data.get("display")
    if not isinstance(disp, dict):
        fail_gracefully(f"`display` in {hw_src} must be a JSON object.")

    missing_disp = sorted(REQUIRED_HW_DISPLAY_KEYS - set(disp.keys()))
    if missing_disp:
        fail_gracefully(
            f"Missing required `display` attribute(s) {missing_disp} in {hw_src} (default values are not assumed).",
            "Specify `panel`, `width_px`, `height_px`, `dpi`, `safe_margin_px`, `color_depth_bpp`, and `lvgl_color_format`.",
        )

    unknown_disp = sorted(set(disp.keys()) - REQUIRED_HW_DISPLAY_KEYS)
    if unknown_disp:
        fail_gracefully(
            f"Unknown or redundant `display` attribute(s) {unknown_disp} in {hw_src}.",
            "Remove duplicate/derived display keys (such as `usable_width_px` or `ppi`).",
        )

    width_px = int(disp["width_px"])
    height_px = int(disp["height_px"])
    dpi = float(disp["dpi"])
    safe_margin_px = int(disp["safe_margin_px"])
    color_depth_bpp = int(disp["color_depth_bpp"])
    usable_width_px = width_px - (2 * safe_margin_px)
    if width_px <= 0 or height_px <= 0 or usable_width_px <= 0 or dpi <= 0.0 or color_depth_bpp != 1:
        fail_gracefully(
            f"Invalid display geometry in {hw_src}: width={width_px}, height={height_px}, dpi={dpi}, bpp={color_depth_bpp}.",
            "Ensure positive pixel dimensions, `dpi > 0`, and `color_depth_bpp == 1`.",
        )

    return TargetHardwareSpec(
        hw_scheme_id=str(hw_data["hw_scheme_id"]).strip(),
        hw_scheme_path=resolved_hw_path,
        chip_name=str(hw_data["chip_name"]).strip(),
        soc_vendor=str(hw_data["soc_vendor"]).strip(),
        partition_bytes=part_bytes,
        panel=str(disp["panel"]).strip(),
        width_px=width_px,
        height_px=height_px,
        dpi=dpi,
        safe_margin_px=safe_margin_px,
        usable_width_px=usable_width_px,
        color_depth_bpp=color_depth_bpp,
        lvgl_color_format=str(disp["lvgl_color_format"]).strip(),
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
      2. Sets `EPD_FONT_WORKER_ROLE="gpu"` and `EPD_FONT_ACCEL="gpu"` so this single worker owns the
         `Ellesmere` discrete GPU context (32 CUs, 4 CommandQueues, 3D NDRange, 75% Shared GPU Memory).
      3. Registers `teardown_math_backends` with `atexit`.
    """
    try:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    except Exception:
        pass
    os.environ["EPD_FONT_WORKER_ROLE"] = "gpu"
    os.environ["EPD_FONT_ACCEL"] = "gpu"
    try:
        from math_backends import select_math_backend, teardown_math_backends
        select_math_backend("gpu")
        atexit.register(teardown_math_backends)
    except Exception as exc:
        sys.stderr.write(f"[!] Fatal GPU Worker OpenCL initialization error: {exc}\n")
        sys.stderr.flush()
        raise


def _worker_process_init_cpu() -> None:
    """
    Initializer for ProcessPoolExecutor CPU workers:
      1. Sets `signal.signal(signal.SIGINT, signal.SIG_IGN)` so pressing `Ctrl+C` in the console
         does NOT cause child worker processes to dump `KeyboardInterrupt` tracebacks.
      2. Sets `EPD_FONT_WORKER_ROLE="cpu"` and `EPD_FONT_ACCEL="cpu"` so child CPU workers NEVER
         allocate competing discrete GPU OpenCL contexts (`0` VRAM bloat and `0` context thrashing).
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
    math_backend: Optional[str] = None,
) -> List[Any]:
    """
    Execute tasks asynchronously according to the validated `math_backend` operating mode:
      - `"sync"`: Synchronous single-process execution in the main process.
      - `"cpu"` : Asynchronous multi-core CPU execution (`max_workers` `ProcessPoolExecutor` CPU workers,
                  `EPD_FONT_WORKER_ROLE="cpu"`, zero GPU contexts).
      - `"gpu"` : Dedicated GPU acceleration (`gpu_pool` with `max_workers=1`, `EPD_FONT_WORKER_ROLE="gpu"`,
                  `EPD_FONT_ACCEL="gpu"`) executing all vector/distance-field/thresholding tasks on the GPU,
                  orchestrated asynchronously from the CPU (with bitmap `exact-mono` tasks routed to a helper
                  CPU worker). Raises an explicit error if no verified GPU is available.
      - `"hybrid"` / `"auto"`: Dual-pool work-stealing deque (`1` persistent GPU worker pulling heavy tasks
                  from the front + `max_workers - 1` async CPU workers pulling lightweight tasks from the back).
                  In `"hybrid"`, raises an explicit error if no OpenCL GPU is present; in `"auto"`, delegates
                  to the async multi-core CPU pool when no OpenCL GPU is detected.
    """
    if not tasks:
        return []

    eff_mode = (math_backend or os.environ.get("EPD_FONT_ACCEL", "auto")).strip().lower()
    if eff_mode not in VALID_MATH_BACKEND_VALUES:
        fail_gracefully(
            f"Unsupported `math_backend` mode `'{eff_mode}'`.",
            f"Valid modes are: {sorted(VALID_MATH_BACKEND_VALUES)}.",
        )

    # Check hardware upfront before executing tasks
    has_opencl_gpu = False
    if eff_mode != "cpu":
        try:
            from opencl_dispatcher import get_devices
            gpu_dev, cpu_ocl_dev, _ = get_devices()
            has_opencl_gpu = (gpu_dev is not None or cpu_ocl_dev is not None)
        except Exception:
            has_opencl_gpu = False

    if eff_mode in ("gpu", "hybrid") and not has_opencl_gpu:
        fail_gracefully(
            f"Hardware check failed for `math_backend = '{eff_mode}'`: no compatible OpenCL GPU/accelerator was detected on this host.",
            "Install an OpenCL GPU runtime (see `README.md`) or set 'math_backend': 'auto' or 'cpu' in your `.scheme.json`.",
        )

    # Release any parent-process probe context before spawning worker processes
    if eff_mode != "sync":
        try:
            from math_backends import teardown_math_backends
            teardown_math_backends()
        except Exception:
            pass

    # 1. Synchronous single-process mode (`math_backend = "sync"`)
    if eff_mode == "sync":
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
    try:
        from opencl_dispatcher import score_task_compute_density
        indexed_tasks.sort(key=lambda pair: score_task_compute_density(pair[1]), reverse=True)
    except Exception:
        pass

    ordered_results: List[Any] = [None] * len(tasks)

    # 2. Pure Async Multi-Core CPU mode (`math_backend = "cpu"`, or `"auto"` when no OpenCL GPU is present)
    if use_threads or eff_mode == "cpu" or (eff_mode == "auto" and not has_opencl_gpu):
        if use_threads:
            pool: Any = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        else:
            prev_sig = signal.signal(signal.SIGINT, signal.SIG_IGN)
            try:
                pool = concurrent.futures.ProcessPoolExecutor(
                    max_workers=max(1, max_workers),
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

    # 3. Dedicated GPU Mode (`math_backend = "gpu"`):
    #    All vector/distance-field/thresholding tasks run in the persistent GPU worker (`EPD_FONT_ACCEL="gpu"`),
    #    while native pre-gridded bitmap strikes (`exact-mono` / `Terminus`) run in 1 helper CPU worker.
    if eff_mode == "gpu":
        has_mono = any(
            isinstance(t, dict)
            and (
                str(t.get("family", "")).lower() in ("terminus", "unifont")
                or str(t.get("pipeline", "")).lower() == "exact-mono"
            )
            for t in tasks
        )
        prev_sig = signal.signal(signal.SIGINT, signal.SIG_IGN)
        cpu_pool = None
        try:
            gpu_pool = concurrent.futures.ProcessPoolExecutor(
                max_workers=1,
                initializer=_worker_process_init_gpu,
            )
            if has_mono:
                cpu_pool = concurrent.futures.ProcessPoolExecutor(
                    max_workers=1,
                    initializer=_worker_process_init_cpu,
                )
        finally:
            signal.signal(signal.SIGINT, prev_sig)

        futures_map_gpu: Dict[concurrent.futures.Future, int] = {}
        try:
            for orig_idx, t in indexed_tasks:
                fam = str(t.get("family", "")).lower() if isinstance(t, dict) else ""
                pipe = str(t.get("pipeline", "")).lower() if isinstance(t, dict) else ""
                if cpu_pool is not None and (fam in ("terminus", "unifont") or pipe == "exact-mono"):
                    fut = cpu_pool.submit(worker_fn, t)
                else:
                    fut = gpu_pool.submit(worker_fn, t)
                futures_map_gpu[fut] = orig_idx

            for fut in concurrent.futures.as_completed(futures_map_gpu):
                if _INTERRUPTED:
                    raise KeyboardInterrupt()
                orig_idx = futures_map_gpu[fut]
                ordered_results[orig_idx] = fut.result()

            try:
                gpu_pool.submit(_teardown_worker_opencl_noop, None).result(timeout=3.0)
            except Exception:
                pass
            gpu_pool.shutdown(wait=True)
            if cpu_pool is not None:
                cpu_pool.shutdown(wait=True)
            return ordered_results
        except KeyboardInterrupt:
            for fut in futures_map_gpu:
                fut.cancel()
            _terminate_executor_processes(gpu_pool)
            if cpu_pool is not None:
                _terminate_executor_processes(cpu_pool)
            gpu_pool.shutdown(wait=False, cancel_futures=True)
            if cpu_pool is not None:
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
            for fut in futures_map_gpu:
                fut.cancel()
            _terminate_executor_processes(gpu_pool)
            if cpu_pool is not None:
                _terminate_executor_processes(cpu_pool)
            gpu_pool.shutdown(wait=False, cancel_futures=True)
            if cpu_pool is not None:
                cpu_pool.shutdown(wait=False, cancel_futures=True)
            raise
        finally:
            try:
                from math_backends import teardown_math_backends
                teardown_math_backends()
            except Exception:
                pass
            gc.collect()

    # 4. Hybrid Dual-Pool Work-Stealing Execution (`math_backend = "auto"` or `"hybrid"` with OpenCL GPU):
    #    `1` Persistent GPU Worker (heavy front of deque) + `min(max_workers - 1, len(tasks) - 1)` CPU Workers
    cpu_workers = min(max(1, max_workers - 1), max(0, len(tasks) - 1))
    prev_sig = signal.signal(signal.SIGINT, signal.SIG_IGN)
    cpu_pool = None
    try:
        gpu_pool = concurrent.futures.ProcessPoolExecutor(
            max_workers=1,
            initializer=_worker_process_init_gpu,
        )
        if cpu_workers > 0:
            cpu_pool = concurrent.futures.ProcessPoolExecutor(
                max_workers=cpu_workers,
                initializer=_worker_process_init_cpu,
            )
    finally:
        signal.signal(signal.SIGINT, prev_sig)
    task_deque: deque[Tuple[int, dict]] = deque(indexed_tasks)
    in_flight: Dict[concurrent.futures.Future, Tuple[int, str]] = {}

    try:
        if task_deque:
            o_idx, t_item = task_deque.popleft()
            in_flight[gpu_pool.submit(worker_fn, t_item)] = (o_idx, "gpu")

        if cpu_pool is not None:
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
                    if pool_tag == "gpu" or cpu_pool is None:
                        next_idx, next_task = task_deque.popleft()
                        in_flight[gpu_pool.submit(worker_fn, next_task)] = (next_idx, "gpu")
                    else:
                        next_idx, next_task = task_deque.pop()
                        in_flight[cpu_pool.submit(worker_fn, next_task)] = (next_idx, "cpu")

        try:
            gpu_pool.submit(_teardown_worker_opencl_noop, None).result(timeout=3.0)
        except Exception:
            pass
        gpu_pool.shutdown(wait=True)
        if cpu_pool is not None:
            cpu_pool.shutdown(wait=True)
        return ordered_results
    except KeyboardInterrupt:
        for fut in in_flight:
            fut.cancel()
        _terminate_executor_processes(gpu_pool)
        if cpu_pool is not None:
            _terminate_executor_processes(cpu_pool)
        gpu_pool.shutdown(wait=False, cancel_futures=True)
        if cpu_pool is not None:
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
        if cpu_pool is not None:
            _terminate_executor_processes(cpu_pool)
        gpu_pool.shutdown(wait=False, cancel_futures=True)
        if cpu_pool is not None:
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
