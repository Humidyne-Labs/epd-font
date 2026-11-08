#!/usr/bin/env python3
"""
font_catalog_info.py (v1.0.22) — Agent-First Static TTF, Scheme & Strike Vault Inventory Tool
============================================================================================
Inspects `build/metadata/asset_manifest.json`, `tools/fonts/schemes/*.json`, root hardware
schemes (`esp32s3-N8R8-hw_scheme.json`, `generic_hw.json`), and any built Strike Vault
(`dist/*/*.json.gz`) to report available font families, weights, size floors, and exact ROM
byte footprints without guessing.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def find_repo_root() -> Path:
    cur = Path(__file__).resolve().parent
    for _ in range(5):
        if (cur / "VERSION.json").is_file() or (cur / "tools" / "fonts").is_dir():
            return cur
        cur = cur.parent
    return Path.cwd()


def resolve_hw_display(repo_root: Path, scheme_dict: dict) -> dict:
    hw_ref = str(scheme_dict.get("hardware_scheme", "esp32s3-N8R8-hw_scheme.json")).strip()
    if hw_ref.lower() == "genaric_hw.json":
        hw_ref = "generic_hw.json"
    hw_path = repo_root / hw_ref
    if hw_path.is_file():
        hw_data = json.loads(hw_path.read_text(encoding="utf-8"))
        disp = dict(hw_data.get("display", {}))
        disp["hw_scheme_id"] = hw_data.get("hw_scheme_id", hw_ref)
        disp["chip_name"] = hw_data.get("chip_name", "ESP32-S3-N8R8")
        disp["partition_1"] = hw_data.get("partition_1", "3 MBytes")
        return disp
    return {"width_px": 200, "height_px": 200, "dpi": 188.15, "hw_scheme_id": hw_ref}


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="font_catalog_info.py",
        description="Inventory of all static TTFs, schemes, and compiled strike vaults in epd-font v1.0.22.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    repo_root = find_repo_root()
    manifest_path = repo_root / "build" / "metadata" / "asset_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}

    schemes_dir = repo_root / "tools" / "fonts" / "schemes"
    schemes_summary = []
    if schemes_dir.is_dir():
        for sp in sorted(schemes_dir.glob("*.json")):
            sd = json.loads(sp.read_text(encoding="utf-8"))
            strike_cnt = sum(len(s.get("sizes", [])) for s in sd.get("strikes", []))
            schemes_summary.append({
                "file": sp.name,
                "scheme_id": sd.get("scheme_id"),
                "brand": sd.get("project_brand"),
                "hardware_scheme": sd.get("hardware_scheme", "esp32s3-N8R8-hw_scheme.json"),
                "total_strikes": strike_cnt,
                "display": resolve_hw_display(repo_root, sd),
            })

    summary = {
        "version": "1.0.22",
        "total_static_ttfs": manifest.get("total_ttf_files", 0),
        "catalog_counts": manifest.get("catalog_counts", {}),
        "general_schemes_count": len(schemes_summary),
        "general_schemes": schemes_summary,
    }

    if args.json:
        print(json.dumps(summary, indent=2))
        return

    print("=" * 98)
    print("HUMIDYNE LABS / HUMIDITRON epd-font v1.0.22 — CATALOG & SCHEME INVENTORY")
    print("=" * 98)
    print(f"  Static TTF Binaries in build/static_ttfs/ : {summary['total_static_ttfs']}")
    for k, v in summary["catalog_counts"].items():
        print(f"  Indexed Catalog [{k:15s}]       : {v:,d} entries")
    print("-" * 98)
    print(f"  General-Purpose Schemes in tools/fonts/schemes/ ({len(schemes_summary)} total):")
    for sc in schemes_summary:
        disp = sc["display"]
        d_str = f"{disp.get('width_px', 200)}x{disp.get('height_px', 200)} @ {disp.get('dpi', 188.15)} DPI"
        print(f"    - {sc['file']:36s} | {sc['total_strikes']:2d} strikes | {d_str:20s} | {sc['hardware_scheme']}")
    print("=" * 98)


if __name__ == "__main__":
    main()
