#!/usr/bin/env python3
"""
string_info.py (v1.0.23) — Agent-First Deterministic String Layout & Screen Audit Tool
=======================================================================================
Thin CLI wrapper over `epd_typography.measure_string_budget()` and
`epd_typography.audit_screen_strings()`. Validates single labels, two-column
telemetry rows, and full C/C++ UI screen source directories against display margins.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from epd_typography import audit_screen_strings, measure_string_budget  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="string_info.py",
        description="Deterministic LVGL v9 1-bpp string pixel width, kerning & screen budget calculator.",
    )
    parser.add_argument("--strike", "-s", type=str, default="humid1_font_plex_sans_normal_14", help="Primary strike symbol (default: plex_sans_normal_14)")
    parser.add_argument("--text", "-t", type=str, default=None, help="Text string to measure (omit when using --audit-screens)")
    parser.add_argument("--right-text", "-r", type=str, default=None, help="Optional right-aligned telemetry string on the same row")
    parser.add_argument("--right-strike", type=str, default=None, help="Optional strike symbol for --right-text (default: same as --strike)")
    parser.add_argument("--audit-screens", action="store_true", help="Scan UI screen C/C++ files for lv_label_set_text[_fmt] budget overflows")
    parser.add_argument("--screen-dir", type=str, default=None, help="Explicit C/C++ UI screen directory for --audit-screens")
    parser.add_argument("-H", "--hw-scheme", type=str, default="esp32s3-N8R8-hw_scheme.json", help="Target hardware scheme JSON")
    parser.add_argument("--min-gap", type=int, default=8, help="Minimum required pixel gap between left and right text (default: 8)")
    parser.add_argument("--workspace", "-w", type=str, default=None, help="Target workspace/repository root")
    parser.add_argument("--vault", "-v", type=str, default=None, help="Optional path to humid1_epd_vault.json.gz")
    parser.add_argument("--metrics-dir", "-m", type=str, default=None, help="Optional directory containing char_widths_*.csv manifests")
    parser.add_argument("--csv", action="store_true", help="Prefer CSV metric manifests over Strike Vault")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    if not args.audit_screens and not args.text:
        parser.error("Provide --text <string> or pass --audit-screens.")

    if args.audit_screens:
        try:
            report = audit_screen_strings(
                workspace_dir=args.workspace,
                screen_dir=args.screen_dir,
                default_strike=args.strike,
                hw_scheme=args.hw_scheme,
                vault_path=args.vault,
                metrics_dir=args.metrics_dir,
            )
        except (KeyError, ValueError, FileNotFoundError) as exc:
            print(f"[!] {exc}", file=sys.stderr)
            sys.exit(1)

        if args.json:
            print(json.dumps(report, indent=2))
            if report["overflow_count"] > 0:
                sys.exit(1)
            return

        print("=" * 84)
        print(f"UI SCREEN STRING BUDGET AUDIT — {report['screen_dir']} (Budget <= {report['usable_budget_px']} px)")
        print("=" * 84)
        for ov in report["overflows"]:
            print(
                f"  [FAIL] {ov['width_px']:>3d}px > {ov['usable_budget_px']}px | "
                f"{ov['file']:24s} | {ov['strike']} | '{ov['line']}'"
            )
        print(
            f"Summary: checked {report['total_strings_checked']} line(s) across {len(report['files_scanned'])} file(s), "
            f"overflows={report['overflow_count']} -> [{report['status']}]"
        )
        print("=" * 84)
        if report["overflow_count"] > 0:
            sys.exit(1)
        return

    try:
        payload = measure_string_budget(
            strike=args.strike,
            text=args.text,
            right_text=args.right_text,
            right_strike=args.right_strike,
            hw_scheme=args.hw_scheme,
            min_gap=args.min_gap,
            workspace_dir=args.workspace,
            vault_path=args.vault,
            metrics_dir=args.metrics_dir,
            prefer_csv=args.csv,
        )
    except (KeyError, ValueError, FileNotFoundError) as exc:
        print(f"[!] {exc}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(payload, indent=2))
        return

    needed_gap = args.min_gap if args.right_text else 0
    print("=" * 78)
    print(f"STRING PIXEL BUDGET REPORT — {payload['strike']} (lh={payload['line_height_px']}px, src={payload['source']})")
    print("=" * 78)
    print(f"  Left String     : '{args.text}' -> {payload['text_width_px']} px")
    if args.right_text:
        print(f"  Right String    : '{args.right_text}' ({payload['right_strike']}) -> {payload['right_width_px']} px")
    print(f"  Combined Width  : {payload['combined_width_px']} px")
    print(f"  Display Budget  : {payload['usable_budget_px']} px usable (Screen={payload['screen_width_px']}px, Margin=2x{payload['safe_margin_px']}px)")
    print(f"  Clearance       : {payload['clearance_px']:+d} px (Min Gap={needed_gap}px) -> [{payload['status']}]")
    if payload.get("csv_path"):
        print(f"  CSV Manifest    : {payload['csv_path']}")
    print("-" * 78)
    print("  Per-Character Breakdown (Left String):")
    for item in payload["glyph_breakdown"]:
        print(
            f"    '{item['char']}' ({item['cp']}) : step={item.get('step_px', 0):2d}px "
            f"(adv_fp4={item.get('adv_w_fp4', 0):3d}, kern_fp4={item.get('kern_fp4', 0):+3d}, "
            f"bbox={item.get('box_w', 0)}x{item.get('box_h', 0)})"
        )
    print("=" * 78)


if __name__ == "__main__":
    main()
