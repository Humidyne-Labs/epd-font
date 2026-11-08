#!/usr/bin/env python3
"""
build_fonts_hybrid.py (v1.0.22)
==============================
A 1-bit EPD font generator and asset pipeline for embedded displays.
Repository : https://github.com/Humidyne-Labs/epd-font
Authors    : Humiditron (https://github.com/humiditron) & AI/LLM Development Partner
License    : MIT License

Hybrid GPU + CPU Font & Icon Strike Builder Entrypoint (`Jr.Agent_Notes.md` Step 3):
  - Enumerates all OpenCL platforms and devices (`[0] Ellesmere GPU - 32 CUs`,
    `[1] AMD Ryzen 5 5600G CPU - 12 CUs`) and Host Shared GPU Memory (`15.7 GB`).
  - Delegates to `humid1_generate_1bpp.py` with hybrid Single-Owner GPU + Multi-Core CPU
    work-stealing dispatch and deterministic post-run OpenCL memory teardown.
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from humid1_generate_1bpp import main as generate_1bpp_main
from math_backends import teardown_math_backends
from opencl_dispatcher import describe_hybrid_dispatch_plan, get_devices


def main() -> None:
    gpu_dev, cpu_dev, devs = get_devices()
    print("============================================================================")
    print("[*] Hybrid OpenCL + Multi-Core CPU Hardware Dispatch Inventory (v1.0.22):")
    if devs:
        for d in devs:
            print(
                f"    [{d.global_index}] Platform {d.platform_index}, Device {d.device_index}: "
                f"{d.device_name} ({d.device_type_str}) - {d.compute_units} CUs | "
                f"Dims: {d.max_work_item_dims}D {d.max_work_item_sizes}"
            )
    else:
        print("    [*] No OpenCL ICD detected — using Vectorized Host CPU SIMD Workers.")
    print(f"    [*] {describe_hybrid_dispatch_plan(0, 12)}")
    print("============================================================================")

    # If invoked as `build_fonts_hybrid.py --scheme <path>` without `--workflow`, default to `--workflow build`
    if "-w" not in sys.argv and "--workflow" not in sys.argv:
        repo_root = SCRIPT_DIR.parent.parent
        sys.argv.extend(["--workflow", "build"])
        if "-s" not in sys.argv and "--src-dir" not in sys.argv:
            sys.argv.extend(["--src-dir", str(repo_root / "build" / "static_ttfs")])
        if "-o" not in sys.argv and "--out-dir" not in sys.argv and "--build-dir" not in sys.argv:
            sys.argv.extend(["--out-dir", str(repo_root / "build" / "h1os")])
        if "-d" not in sys.argv and "--dist-dir" not in sys.argv:
            sys.argv.extend(["--dist-dir", str(repo_root / "dist" / "h1os_distro")])
        if "-p" not in sys.argv and "--patches" not in sys.argv:
            sys.argv.extend(["--patches", str(repo_root / "font_icon_epd_patches.json")])

    try:
        generate_1bpp_main()
    finally:
        teardown_math_backends()


if __name__ == "__main__":
    main()
