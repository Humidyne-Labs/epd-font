#!/usr/bin/env python3
"""
humid1_cmake_font_builder.py (v1.0.20)
======================================
A 1-bit EPD font generator and asset pipeline for embedded displays.
Repository : https://github.com/Humidyne-Labs/epd-font
Authors    : Humiditron (https://github.com/humiditron) & AI/LLM Development Partner
License    : MIT License

ESP-IDF & CMake Integration Python Script for Embedded Displays:
  - Can be invoked directly from `CMakeLists.txt` (`execute_process` or `add_custom_command`)
    during an ESP-IDF (`idf.py build`) or standalone CMake firmware build.
  - Supports TWO build modes:
    1. Fast Pre-Rasterized Vault Mode (`--vault <humid1_epd_vault.json.gz>`):
       Zero external Python dependencies (< 0.15s execution).
    2. Direct Font Rasterization Mode (`--src-dir <fonts_dir> --pipeline {raw-unhinted,raw-hinted,svg-potrace,mdf}`):
       Recursively discovers `.ttf/.otf/.ttc/.bdf` assets and generates LVGL >= 9.6.0 `.c`/`.h` files,
       `rom_space_estimate.txt`, and `licenses/`.
  - Supports `--list-sources` to print generated `.c` file paths for CMake `target_sources()`.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from humid1_runtime import (
    TOOL_VERSION,
    fail_gracefully,
    install_clean_signal_handlers,
    require_valid_path,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="humid1_cmake_font_builder.py",
        description=(
            f"Humidyne Labs / Humiditron `epd-font` v{TOOL_VERSION} — ESP-IDF CMake Font Builder.\n"
            "A 1-bit EPD font generator and asset pipeline for embedded displays."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("-S", "--scheme", type=str, required=True, help="Path to declarative .scheme.json file (required)")
    parser.add_argument("-o", "--out-dir", type=str, required=True, help="Output directory for generated LVGL .c/.h files (required)")
    parser.add_argument("-v", "--vault", type=str, default=None, help="Optional path to pre-rasterized humid1_epd_vault.json.gz (fast zero-dependency mode)")
    parser.add_argument("-s", "--src-dir", type=str, default=None, help="Optional path to font directory for direct conversion mode")
    parser.add_argument("-p", "--patches", type=str, default=None, help="Optional path to font_icon_epd_patches.json")
    parser.add_argument("-a", "--ascii-dir", type=str, default=None, help="Optional path to ascii_patches directory")
    parser.add_argument(
        "--pipeline",
        choices=["raw-unhinted", "raw-hinted", "svg-potrace", "svg-potrace-jfa", "jfa-marching", "mdf", "msdf", "sdf-smoothstep", "adf-biquadratic", "otsu-adaptive", "all", "all-debug"],
        default="raw-hinted",
        help="Bilevel conversion method when running in direct --src-dir mode (default: raw-hinted)",
    )
    parser.add_argument("--threshold", type=int, default=128, help="Binarization threshold 1..254 (default: 128)")
    parser.add_argument("--gamma", type=float, default=1.0, help="Linear grayscale gamma factor in [0.1..5.0] (default: 1.0)")
    parser.add_argument("--sizes", type=int, nargs="+", default=None, help="Optional pixel size filter")
    parser.add_argument("--list-sources", action="store_true", help="Print semicolon-separated list of generated .c files for CMake")
    return parser


def main() -> None:
    install_clean_signal_handlers()
    script_dir = Path(__file__).resolve().parent
    parser = build_arg_parser()
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        fail_gracefully("Missing required arguments `--scheme` and `--out-dir`.")
    args = parser.parse_args()

    scheme_path = require_valid_path(args.scheme, "--scheme", must_exist=True, expect_dir=False)
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.vault is None and args.src_dir is None:
        fail_gracefully(
            "Either `--vault <humid1_epd_vault.json.gz>` or `--src-dir <font_dir>` must be provided.",
            "Pass `--vault` for zero-dependency CMake builds or `--src-dir` for direct TTF/OTF/BDF rasterization.",
        )

    if args.vault:
        vault_path = require_valid_path(args.vault, "--vault", must_exist=True, expect_dir=False)
        cmd = [
            sys.executable,
            str(script_dir / "humid1_fw_emit.py"),
            "--scheme", str(scheme_path),
            "--vault", str(vault_path),
            "--out-dir", str(out_dir),
        ]
        if args.ascii_dir:
            cmd.extend(["--ascii-dir", str(require_valid_path(args.ascii_dir, "--ascii-dir", must_exist=True, expect_dir=True))])
        if args.sizes:
            cmd.extend(["--sizes", *[str(s) for s in args.sizes]])
    else:
        src_dir = require_valid_path(args.src_dir, "--src-dir", must_exist=True, expect_dir=True)
        cmd = [
            sys.executable,
            str(script_dir / "humid1_generate_1bpp.py"),
            "--workflow", "build",
            "--scheme", str(scheme_path),
            "--src-dir", str(src_dir),
            "--out-dir", str(out_dir),
            "--pipeline", args.pipeline,
            "--threshold", str(args.threshold),
            "--gamma", str(args.gamma),
        ]
        if args.patches:
            cmd.extend(["--patches", str(require_valid_path(args.patches, "--patches", must_exist=True, expect_dir=False))])
        if args.ascii_dir:
            cmd.extend(["--ascii-dir", str(require_valid_path(args.ascii_dir, "--ascii-dir", must_exist=True, expect_dir=True))])
        if args.sizes:
            cmd.extend(["--sizes", *[str(s) for s in args.sizes]])

    res = subprocess.run(cmd, check=False)
    if res.returncode != 0:
        sys.exit(res.returncode)

    c_dir = (out_dir / "fonts") if (out_dir / "fonts").is_dir() else out_dir
    c_files = sorted(str(p.resolve()) for p in c_dir.glob("*.c"))
    if args.list_sources:
        sys.stdout.write(";".join(c_files) + "\n")


if __name__ == "__main__":
    main()
