#!/usr/bin/env python3
"""CLI wrapper for inspecting BDF 2.1 fonts via epd_bdf_pbm_inspector."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from epd_bdf_pbm_inspector import inspect_bdf


def main() -> int:
    ap = argparse.ArgumentParser(description="Inspect BDF 2.1 bitmap font consistency & weight metrics.")
    ap.add_argument("bdf_path", help="Path to .bdf file")
    ap.add_argument("--compare", default="", help="Optional comparison .bdf (e.g. normal vs bold)")
    ap.add_argument("--chars", default="", help="Comma-separated characters or hex codepoints")
    args = ap.parse_args()
    res = inspect_bdf(args.bdf_path, compare_bdf_path=args.compare or None, char_query=args.chars)
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
