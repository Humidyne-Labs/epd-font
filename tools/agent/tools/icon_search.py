#!/usr/bin/env python3
"""
icon_search.py (v1.0.9) — Agent-First Multi-Vendor Icon Catalog Search & C Macro Generator
==========================================================================================
Searches `build/metadata/{fa7,lucide,phosphor,tabler}_catalog.json` (12,200+ icons) by
keyword, substring, regex, or codepoint, and outputs:
  - Exact semantic icon name for `.scheme.json` `"icons": [...]`
  - Unicode Private Use Area hex codepoint (`0xE006`)
  - Exact UTF-8 C string literal (`"\xEE\x80\x86"`) for LVGL `lv_label_set_text()`
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def find_repo_root() -> Path:
    cur = Path(__file__).resolve().parent
    for _ in range(5):
        if (cur / "VERSION.json").is_file() or (cur / "tools" / "fonts").is_dir():
            return cur
        cur = cur.parent
    return Path.cwd()


def cp_to_c_utf8_escape(cp: int) -> str:
    b = chr(cp).encode("utf-8")
    return "".join(f"\\x{byte:02X}" for byte in b)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="icon_search.py",
        description="Search 12,200+ embedded icons across Font Awesome 7, Lucide, Phosphor, and Tabler.",
    )
    parser.add_argument("--query", "-q", type=str, required=True, help="Search keyword (e.g. 'battery', 'wifi', 'thermometer', 'alarm')")
    parser.add_argument("--vendor", "-v", choices=["all", "icon_fa7", "icon_lucide", "icon_phosphor", "icon_tabler"], default="all", help="Filter by icon vendor")
    parser.add_argument("--limit", "-n", type=int, default=25, help="Max results per vendor (default: 25)")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    repo_root = find_repo_root()
    uni_path = repo_root / "build" / "metadata" / "unified_icon_names.json"
    if not uni_path.is_file():
        print(f"[!] Metadata catalog not found at {uni_path}. Run build_static_ttf_assets.py first.", file=sys.stderr)
        sys.exit(1)

    uni = json.loads(uni_path.read_text(encoding="utf-8"))
    by_name = uni.get("by_name", {})
    q_low = args.query.lower().strip()

    vendors = [args.vendor] if args.vendor != "all" else ["icon_fa7", "icon_lucide", "icon_phosphor", "icon_tabler"]
    matches = []

    for v in vendors:
        vmap = by_name.get(v, {})
        v_cnt = 0
        for name, hex_cp in sorted(vmap.items()):
            if q_low in name.lower() or q_low == hex_cp.lower():
                cp = int(hex_cp, 16)
                macro_suffix = name.upper().replace("-", "_")
                matches.append({
                    "vendor": v,
                    "name": name,
                    "codepoint_hex": hex_cp,
                    "codepoint_dec": cp,
                    "c_utf8_literal": f'"{cp_to_c_utf8_escape(cp)}"',
                    "c_define": f'#define HUMID1_ICON_{v.split("_")[1].upper()}_{macro_suffix} "{cp_to_c_utf8_escape(cp)}"',
                })
                v_cnt += 1
                if v_cnt >= args.limit:
                    break

    if args.json:
        print(json.dumps({"query": args.query, "total_matches": len(matches), "matches": matches}, indent=2))
        return

    print("=" * 96)
    print(f"ICON CATALOG SEARCH RESULTS FOR '{args.query}' ({len(matches)} matches shown)")
    print("=" * 96)
    print(f"{'Vendor':15s} | {'Semantic Name':28s} | {'Codepoint':9s} | {'C UTF-8 Literal':16s} | {'C Macro Suggestion'}")
    print("-" * 96)
    for m in matches:
        print(f"{m['vendor']:15s} | {m['name']:28s} | {m['codepoint_hex']:9s} | {m['c_utf8_literal']:16s} | {m['c_define']}")
    print("=" * 96)


if __name__ == "__main__":
    main()
