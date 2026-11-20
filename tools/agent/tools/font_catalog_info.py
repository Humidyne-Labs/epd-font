#!/usr/bin/env python3
"""
font_catalog_info.py (v1.0.23) — Agent-First Static TTF, Scheme & Strike Vault Inventory Tool
=============================================================================================
Thin CLI wrapper over `epd_typography.inventory_fonts()`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from epd_typography import inventory_fonts  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="font_catalog_info.py",
        description="Inventory of static TTFs, Vault/CSV strikes, and declared schemes in epd-font v1.0.23.",
    )
    parser.add_argument("--workspace", "-w", type=str, default=None, help="Target workspace/repository root")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    summary = inventory_fonts(workspace_dir=args.workspace)
    if args.json:
        print(json.dumps(summary, indent=2))
        return

    print("=" * 98)
    print("HUMIDYNE LABS / HUMIDITRON epd-font v1.0.23 — CATALOG & SCHEME INVENTORY")
    print("=" * 98)
    print(f"  Workspace Root                            : {summary['workspace_root']}")
    print(f"  Static TTF Binaries in build/static_ttfs/ : {summary['total_static_ttfs']}")
    print(f"  Active Vault Strikes / CSV Manifests      : {summary['vault_strike_count']} vault / {summary['csv_strike_count']} csv")
    for k, v in summary["catalog_counts"].items():
        print(f"  Indexed Catalog [{k:18s}]    : {v:,d} entries")
    print("-" * 98)
    print(f"  Declared Font Schemes ({summary['schemes_count']} total):")
    for sc in summary["schemes"]:
        disp = sc["display"]
        d_str = f"{disp.get('width_px', 200)}x{disp.get('height_px', 200)} @ {disp.get('dpi', 188.15)} DPI"
        print(f"    - {sc['file']:55s} | {sc['total_strikes']:2d} strikes | {d_str:20s} | {sc['hardware_scheme']}")
    print("=" * 98)


if __name__ == "__main__":
    main()
