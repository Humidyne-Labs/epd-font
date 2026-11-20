#!/usr/bin/env python3
"""
char_info.py (v1.0.23) — Agent-First Deterministic Character & Icon Metric Inspector
===================================================================================
Thin CLI wrapper over `epd_typography.inspect_char()`. Queries exact 1-bpp glyph
metrics (advance width, bounding box, bearing offsets, underline metrics, UTF-8 C
literal, and 1:1 ASCII bitmap) from Strike Vaults (`*.json.gz`) or CSV manifests
(`char_widths_<sym>.csv`).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from epd_typography import inspect_char  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="char_info.py",
        description="Deterministic 1-bpp character & icon metric inspector.",
    )
    parser.add_argument("--strike", "-s", type=str, default="humid1_font_plex_sans_normal_14", help="Strike symbol (e.g. plex_sans_normal_14, icon_phosphor_fill_20)")
    parser.add_argument("--char", "-c", type=str, required=True, help="Character ('A', '@'), hex ('0x0040', 'U+E006'), or semantic icon name")
    parser.add_argument("--workspace", "-w", type=str, default=None, help="Target workspace/repository root")
    parser.add_argument("--vault", "-v", type=str, default=None, help="Optional path to humid1_epd_vault.json.gz")
    parser.add_argument("--metrics-dir", "-m", type=str, default=None, help="Optional directory containing char_widths_*.csv manifests")
    parser.add_argument("--csv", action="store_true", help="Prefer CSV metric manifests over Strike Vault")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    try:
        result = inspect_char(
            strike=args.strike,
            char_query=args.char,
            workspace_dir=args.workspace,
            vault_path=args.vault,
            metrics_dir=args.metrics_dir,
            prefer_csv=args.csv,
        )
    except (KeyError, ValueError, FileNotFoundError) as exc:
        print(f"[!] {exc}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(result, indent=2))
        return

    print("=" * 72)
    print(f"CHARACTER / ICON METRIC REPORT — {result['strike']} [{result['source']}]")
    print("=" * 72)
    print(f"  Query / Name    : {args.char} -> '{result['name']}'")
    print(f"  Codepoint       : {result['codepoint_hex']} ({result['unicode_tag']}, dec={result['codepoint_dec']})")
    print(f"  C UTF-8 Literal : {result['c_utf8_literal']}")
    print(
        f"  Strike Metrics  : size={result['size_px']}px, line_height={result['line_height_px']}px, "
        f"base_line={result['base_line_px']}px, underline=({result['underline_position']}, {result['underline_thickness']})"
    )
    print(f"  Advance Width   : {result['adv_w_px']} px (fp4={result['adv_w_fp4']})")
    print(f"  Bounding Box    : w={result['box_w_px']} px, h={result['box_h_px']} px")
    print(f"  Bearing Offsets : ofs_x={result['ofs_x_px']:+d} px, ofs_y={result['ofs_y_px']:+d} px")
    print(f"  Patched State   : {'PATCHED' if result['patched'] else 'BASELINE'}")
    if result.get("csv_path"):
        print(f"  CSV Manifest    : {result['csv_path']}")
    print("-" * 72)
    for idx, r in enumerate(result["rows"]):
        spaced = " ".join("#" if ch == "#" else "." for ch in r)
        print(f"  row {idx:02d} | {spaced}")
    print("=" * 72)


if __name__ == "__main__":
    main()
