#!/usr/bin/env python3
"""CLI wrapper for inspecting P1/P4 PBM bitmaps via epd_bdf_pbm_inspector."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from epd_bdf_pbm_inspector import inspect_pbm


def main() -> int:
    ap = argparse.ArgumentParser(description="Inspect P1/P4 PBM bitmap run-lengths & pinholes.")
    ap.add_argument("pbm_path", help="Path to .pbm file")
    ap.add_argument("--crop-x", type=int, default=0)
    ap.add_argument("--crop-y", type=int, default=0)
    ap.add_argument("--crop-w", type=int, default=0)
    ap.add_argument("--crop-h", type=int, default=0)
    ap.add_argument("--no-ascii", action="store_true")
    args = ap.parse_args()
    res = inspect_pbm(
        args.pbm_path,
        crop_x=args.crop_x,
        crop_y=args.crop_y,
        crop_w=args.crop_w,
        crop_h=args.crop_h,
        render_ascii=not args.no_ascii,
    )
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
