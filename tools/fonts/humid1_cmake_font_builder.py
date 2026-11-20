#!/usr/bin/env python3
"""
humid1_cmake_font_builder.py (v1.0.23)
======================================
A 1-bit EPD font generator and asset pipeline for embedded displays.
Repository : https://github.com/Humidyne-Labs/epd-font
Authors    : Humiditron (https://github.com/humiditron) & AI/LLM Development Partner
License    : MIT License

ESP-IDF & CMake Integration Python Script for Embedded Displays (`v1.0.23`):
  - Invoked directly from `CMakeLists.txt` (`execute_process` or `add_custom_command`)
    during an ESP-IDF (`idf.py build`) or standalone CMake firmware build.
  - All typography, pipeline, threshold, gamma, and hardware parameters are read strictly
    from `--scheme <.scheme.json>` and its referenced `hardware_scheme` (1 spot, 1 var).
  - Supports TWO build modes:
    1. Fast Pre-Rasterized Vault Mode (`--vault <humid1_epd_vault.json.gz>`):
       Zero external Python dependencies (< 0.15s execution).
    2. Direct Font Rasterization Mode (`--src-dir <fonts_dir>`):
       Recursively discovers `.ttf/.otf/.ttc/.bdf` assets and generates LVGL >= 9.6.0 `.c`/`.h` files,
       `rom_space_estimate.txt`, and `licenses/`.
  - Supports `--list-sources` to print generated `.c` file paths for CMake `target_sources()`.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

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
    parser.add_argument("-a", "--ascii-dir", type=str, default=None, help="Optional path to ascii_patches directory")
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

    vault_cand = None
    if args.vault:
        vault_cand = require_valid_path(args.vault, "--vault", must_exist=True, expect_dir=False)
    else:
        for auto_v in (
            scheme_path.parent.parent / "humid1_epd_vault.json.gz",
            script_dir.parent / "humid1_epd_vault.json.gz",
            script_dir.parent.parent / "dist" / "h1os_distro" / "humid1_epd_vault.json.gz",
        ):
            if auto_v.is_file():
                vault_cand = auto_v.resolve()
                break

    if vault_cand is not None and not args.src_dir:
        cmd = [
            sys.executable,
            str(script_dir / "humid1_fw_emit.py"),
            "--scheme", str(scheme_path),
            "--vault", str(vault_cand),
            "--out-dir", str(out_dir),
        ]
        if args.ascii_dir:
            cmd.extend(["--ascii-dir", str(require_valid_path(args.ascii_dir, "--ascii-dir", must_exist=True, expect_dir=True))])
    elif args.src_dir:
        src_dir = require_valid_path(args.src_dir, "--src-dir", must_exist=True, expect_dir=True)
        cmd = [
            sys.executable,
            str(script_dir / "humid1_generate_1bpp.py"),
            "--workflow", "build",
            "--scheme", str(scheme_path),
            "--src-dir", str(src_dir),
            "--out-dir", str(out_dir),
        ]
        if args.ascii_dir:
            cmd.extend(["--ascii-dir", str(require_valid_path(args.ascii_dir, "--ascii-dir", must_exist=True, expect_dir=True))])
    else:
        fail_gracefully(
            "Neither `--vault <humid1_epd_vault.json.gz>` nor `--src-dir <fonts_dir>` was provided or found.",
            "Pass `--vault <path>` for fast CMake emission or `--src-dir <path>` for direct font conversion.",
        )

    res = subprocess.run(
        cmd,
        stdout=(subprocess.PIPE if args.list_sources else None),
        stderr=sys.stderr,
        text=True,
    )
    if res.returncode != 0:
        fail_gracefully(f"CMake font builder subprocess failed with exit code {res.returncode}.")

    c_files = sorted(out_dir.glob("*.c"))
    if not c_files and (out_dir / "fonts").is_dir():
        c_files = sorted((out_dir / "fonts").glob("*.c"))
    h_files = sorted(out_dir.glob("*.h"))
    if not h_files and (out_dir / "fonts").is_dir():
        h_files = sorted((out_dir / "fonts").glob("*.h"))

    manifest_lines = [
        "# Auto-generated by humid1_cmake_font_builder.py",
        "set(EPD_FONT_C_FILES",
        *[f'    "{f.resolve().as_posix()}"' for f in c_files],
        ")",
        "set(EPD_FONT_H_FILES",
        *[f'    "{f.resolve().as_posix()}"' for f in h_files],
        ")",
    ]
    (out_dir / "epd_fonts_manifest.cmake").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")

    if args.list_sources:
        sys.stdout.write(";".join(str(f.resolve().as_posix()) for f in c_files))
        sys.stdout.flush()


if __name__ == "__main__":
    main()
