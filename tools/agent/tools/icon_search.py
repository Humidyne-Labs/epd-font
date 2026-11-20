#!/usr/bin/env python3
"""
icon_search.py (v1.0.23) — Agent-First Multi-Vendor Icon Catalog Search & C Macro Generator
==========================================================================================
Thin CLI wrapper over `epd_typography.search_icons()`. Searches `unified_icon_names.json`
across Font Awesome 7, Lucide, Phosphor, Tabler Outline, and Tabler Filled.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from epd_typography import search_icons  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="icon_search.py",
        description="Search 12,200+ embedded icons across Font Awesome 7, Lucide, Phosphor, Tabler, and Tabler Filled.",
    )
    parser.add_argument("--query", "-q", type=str, required=True, help="Search keyword (e.g. 'battery', 'wifi', 'thermometer', 'alarm')")
    parser.add_argument(
        "--vendor", "-v",
        choices=["all", "icon_fa7", "icon_lucide", "icon_phosphor", "icon_tabler", "icon_tabler_filled"],
        default="all",
        help="Filter by icon vendor",
    )
    parser.add_argument("--limit", "-n", type=int, default=25, help="Max results per vendor (default: 25)")
    parser.add_argument("--workspace", "-w", type=str, default=None, help="Target workspace/repository root")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    try:
        res = search_icons(
            query=args.query,
            vendor=args.vendor,
            limit=args.limit,
            workspace_dir=args.workspace,
        )
    except FileNotFoundError as exc:
        print(f"[!] {exc}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(res, indent=2))
        return

    matches = res["matches"]
    print("=" * 102)
    print(f"ICON CATALOG SEARCH RESULTS FOR '{args.query}' ({len(matches)} matches shown)")
    print("=" * 102)
    print(f"{'Vendor':18s} | {'Semantic Name':26s} | {'Codepoint':9s} | {'C UTF-8 Literal':16s} | {'C Macro Suggestion'}")
    print("-" * 102)
    for m in matches:
        print(f"{m['vendor']:18s} | {m['name']:26s} | {m['codepoint_hex']:9s} | {m['c_utf8_literal']:16s} | {m['c_define']}")
    print("=" * 102)


if __name__ == "__main__":
    main()
