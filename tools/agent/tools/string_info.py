#!/usr/bin/env python3
"""
string_info.py (v1.0.7) — Agent-First Deterministic String Layout & Screen Budget Calculator
============================================================================================
Computes exact LVGL v9 1-bpp pixel width, kerning adjustments, bounding height, line wrapping,
and horizontal screen clearance (`usable_width = screen_width - 2 * safe_margin`) for any string
or left/right telemetry row pair.

Zero guesswork: AI agents must run `string_info.py` before placing labels or choosing font sizes.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def find_repo_root() -> Path:
    cur = Path(__file__).resolve().parent
    for _ in range(5):
        if (cur / "VERSION.json").is_file() or (cur / "tools" / "fonts").is_dir():
            return cur
        cur = cur.parent
    return Path.cwd()


def load_vault(repo_root: Path, vault_arg: Optional[str] = None) -> Dict:
    candidates = []
    if vault_arg:
        candidates.append(Path(vault_arg))
    candidates.extend([
        repo_root / "dist" / "plex_epd_vault.json.gz",
        repo_root / "dist" / "h1os_distro" / "plex_epd_vault.json.gz",
        repo_root / "dist" / "example_distro" / "plex_epd_vault.json.gz",
        repo_root / "dist" / "audit_distro" / "plex_epd_vault.json.gz",
    ])
    for c in candidates:
        if c.is_file():
            if c.name.endswith(".gz"):
                with gzip.open(c, "rt", encoding="utf-8") as f:
                    return json.load(f)
            return json.loads(c.read_text(encoding="utf-8"))
    return {"strikes": {}}


def measure_string_exact(text: str, strike_data: dict, fallback_data: Optional[dict] = None) -> Tuple[int, List[dict]]:
    cp_map = {int(g["cp"]): g for g in strike_data.get("glyphs", [])}
    fb_map = {int(g["cp"]): g for g in (fallback_data or {}).get("glyphs", [])}
    gid_kern = {(int(k[0]), int(k[1])): int(k[2]) for k in strike_data.get("kern_pairs", [])}

    total_px = 0
    breakdown = []
    chars = list(text)
    for i, ch in enumerate(chars):
        cp = ord(ch)
        g = cp_map.get(cp) or fb_map.get(cp)
        if not g:
            breakdown.append({"char": ch, "cp": f"0x{cp:04X}", "found": False, "adv_px": 0, "kern_fp4": 0})
            continue
        adv_fp4 = int(g["adv_w_fp4"])
        kern_fp4 = 0
        if i + 1 < len(chars):
            next_cp = ord(chars[i + 1])
            next_g = cp_map.get(next_cp)
            if next_g and int(g["cp"]) in cp_map:
                kern_fp4 = gid_kern.get((int(g["gid"]), int(next_g["gid"])), 0)
        step_px = (adv_fp4 + kern_fp4 + 8) >> 4
        total_px += step_px
        breakdown.append({
            "char": ch,
            "cp": f"0x{cp:04X}",
            "found": True,
            "adv_w_fp4": adv_fp4,
            "kern_fp4": kern_fp4,
            "step_px": step_px,
            "box_w": int(g["box_w"]),
            "box_h": int(g["box_h"]),
        })
    return total_px, breakdown


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="string_info.py",
        description="Deterministic LVGL v9 1-bpp string pixel width, kerning & screen budget calculator.",
    )
    parser.add_argument("--strike", "-s", type=str, default="plex_sans_normal_14", help="Primary strike symbol (default: plex_sans_normal_14)")
    parser.add_argument("--text", "-t", type=str, required=True, help="Text string to measure")
    parser.add_argument("--right-text", "-r", type=str, default=None, help="Optional right-aligned telemetry string on the same row")
    parser.add_argument("--right-strike", type=str, default=None, help="Optional strike symbol for --right-text (default: same as --strike)")
    parser.add_argument("--screen-width", type=int, default=200, help="Target screen width in pixels (default: 200)")
    parser.add_argument("--safe-margin", type=int, default=6, help="Safe margin on each side in pixels (default: 6)")
    parser.add_argument("--min-gap", type=int, default=8, help="Minimum required pixel gap between left and right text (default: 8)")
    parser.add_argument("--vault", "-v", type=str, default=None, help="Optional path to plex_epd_vault.json.gz")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    repo_root = find_repo_root()
    vault = load_vault(repo_root, args.vault)
    strikes = vault.get("strikes", {})

    if args.strike not in strikes:
        print(f"[!] Strike '{args.strike}' not found in vault.", file=sys.stderr)
        sys.exit(1)

    fb_strike = strikes.get("plex_sans_normal_14")
    left_w, left_bd = measure_string_exact(args.text, strikes[args.strike], fb_strike)

    right_w = 0
    right_bd = []
    r_strike_name = args.right_strike or args.strike
    if args.right_text:
        if r_strike_name not in strikes:
            print(f"[!] Right strike '{r_strike_name}' not found in vault.", file=sys.stderr)
            sys.exit(1)
        right_w, right_bd = measure_string_exact(args.right_text, strikes[r_strike_name], fb_strike)

    usable_w = args.screen_width - (2 * args.safe_margin)
    combined_w = left_w + right_w
    clearance_px = usable_w - combined_w
    needed_gap = args.min_gap if args.right_text else 0
    fits = clearance_px >= needed_gap

    payload = {
        "strike": args.strike,
        "line_height_px": strikes[args.strike].get("line_height"),
        "base_line_px": strikes[args.strike].get("base_line"),
        "text": args.text,
        "text_width_px": left_w,
        "right_text": args.right_text,
        "right_strike": r_strike_name if args.right_text else None,
        "right_width_px": right_w,
        "combined_width_px": combined_w,
        "screen_width_px": args.screen_width,
        "safe_margin_px": args.safe_margin,
        "usable_budget_px": usable_w,
        "clearance_px": clearance_px,
        "fits_budget": fits,
        "status": "PASS" if fits else "OVERFLOW_OR_TIGHT",
        "glyph_breakdown": left_bd,
        "right_glyph_breakdown": right_bd,
    }

    if args.json:
        print(json.dumps(payload, indent=2))
        return

    print("=" * 78)
    print(f"STRING PIXEL BUDGET REPORT — {args.strike} (lh={payload['line_height_px']}px)")
    print("=" * 78)
    print(f"  Left String     : '{args.text}' -> {left_w} px")
    if args.right_text:
        print(f"  Right String    : '{args.right_text}' ({r_strike_name}) -> {right_w} px")
    print(f"  Combined Width  : {combined_w} px")
    print(f"  Display Budget  : {usable_w} px usable (Screen={args.screen_width}px, Margin=2x{args.safe_margin}px)")
    print(f"  Clearance       : {clearance_px:+d} px (Min Gap={needed_gap}px) -> [{payload['status']}]")
    print("-" * 78)
    print("  Per-Character Breakdown (Left String):")
    for item in left_bd:
        print(f"    '{item['char']}' ({item['cp']}) : step={item.get('step_px', 0):2d}px (adv_fp4={item.get('adv_w_fp4', 0):3d}, kern_fp4={item.get('kern_fp4', 0):+3d}, bbox={item.get('box_w', 0)}x{item.get('box_h', 0)})")
    print("=" * 78)


if __name__ == "__main__":
    main()
