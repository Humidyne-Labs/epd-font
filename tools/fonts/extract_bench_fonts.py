#!/usr/bin/env python3
"""
extract_bench_fonts.py (v1.0.23)
================================
Extract and categorize font binaries (`.ttf`, `.otf`, `.ttc`, `.otc`, `.bdf`) and
license files from a raw font repository tree (e.g., `assets/bench_assets` / Google
Fonts `fonts-main`) into a clean qualification test directory, stripping repository
metadata (`METADATA.pb`, `DESCRIPTION*.html`, `upstream_info.md`, `article/`, etc.).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import time
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

TOOL_VERSION = "1.0.23"

FONT_EXTS: Set[str] = {".ttf", ".otf", ".ttc", ".otc", ".bdf"}
LICENSE_FILENAMES_LOWER: Set[str] = {
    "ofl.txt",
    "license.txt",
    "licence.txt",
    "ufl.txt",
    "apache.txt",
    "license",
    "licence",
}
SKIP_DIR_NAMES: Set[str] = {
    ".git",
    ".ci",
    ".github",
    "axisregistry",
    "catalog",
    "lang",
    "tags",
    "__pycache__",
}


def is_license_file(path: Path) -> bool:
    low = path.name.lower()
    return low in LICENSE_FILENAMES_LOWER or low.startswith("copying")


def parse_metadata_pb(mpb_path: Path) -> Tuple[str, List[str]]:
    """Parse `category` and `subsets` fields from a Google Fonts `METADATA.pb` file."""
    if not mpb_path.is_file():
        return "UNCATEGORIZED", []
    txt = mpb_path.read_text(encoding="utf-8", errors="ignore")
    m_cat = re.search(r'^\s*category:\s*"([^"]+)"', txt, re.MULTILINE)
    cat = m_cat.group(1).strip().upper() if m_cat else "UNCATEGORIZED"
    subsets = [s.strip().lower() for s in re.findall(r'subsets:\s*"([^"]+)"', txt)]
    return cat, subsets


def extract_bench_fonts(
    src_dir: Path,
    out_dir: Path,
    categories: Optional[Sequence[str]] = None,
    latin_only: bool = False,
    clean: bool = False,
) -> dict:
    """
    Walk `src_dir`, extract all font files + license files per font family, strip
    all metadata, and organize outputs into `<out_dir>/<category>/<family>/`.
    """
    t0 = time.perf_counter()
    if not src_dir.is_dir():
        raise FileNotFoundError(f"Source directory not found: {src_dir}")

    cat_filter: Optional[Set[str]] = (
        {c.strip().upper() for c in categories if c.strip()} if categories else None
    )

    if clean and out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Discover all font files grouped by their logical family directory
    family_fonts: Dict[Path, List[Path]] = {}
    skipped_repo_files = 0
    for dirpath, dirnames, filenames in os.walk(src_dir):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIR_NAMES)
        dp = Path(dirpath)
        for fn in sorted(filenames):
            fp = dp / fn
            if fp.suffix.lower() in FONT_EXTS:
                fam_dir = dp.parent if dp.name.lower() == "static" else dp
                family_fonts.setdefault(fam_dir.resolve(), []).append(fp.resolve())
            else:
                skipped_repo_files += 1

    cat_stats: Dict[str, dict] = {}
    used_fam_targets: Set[Path] = set()
    total_families_copied = 0
    total_fonts_copied = 0
    total_static_copied = 0
    total_variable_copied = 0
    total_licenses_copied = 0
    total_metadata_stripped = 0
    total_families_filtered = 0
    missing_license_families: List[str] = []
    duplicate_font_skipped = 0

    for fam_dir in sorted(family_fonts.keys()):
        fonts = sorted(family_fonts[fam_dir], key=lambda p: (p.parent != fam_dir, p.name.lower()))
        mpb_path = fam_dir / "METADATA.pb"
        cat_upper, subsets = parse_metadata_pb(mpb_path)

        if cat_filter is not None and cat_upper not in cat_filter:
            total_families_filtered += 1
            continue
        if latin_only and mpb_path.is_file() and "latin" not in subsets:
            total_families_filtered += 1
            continue

        cat_slug = cat_upper.lower()
        target_dir = out_dir / cat_slug / fam_dir.name
        if target_dir in used_fam_targets:
            suffix = fam_dir.parent.name
            target_dir = out_dir / cat_slug / f"{fam_dir.name}_{suffix}"
        used_fam_targets.add(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        fam_fonts_copied = 0
        fam_static = 0
        fam_variable = 0
        seen_names: Set[str] = set()

        for src_font in fonts:
            if src_font.name in seen_names:
                duplicate_font_skipped += 1
                continue
            dst_font = target_dir / src_font.name
            if dst_font.exists():
                duplicate_font_skipped += 1
                continue
            shutil.copy2(src_font, dst_font)
            seen_names.add(src_font.name)
            fam_fonts_copied += 1
            if "[" in src_font.name:
                fam_variable += 1
            else:
                fam_static += 1

        # Gather license files inside family root (and static/ if absent at root), strip metadata
        lic_candidates: List[Path] = []
        fam_meta_skipped = 0
        for p in sorted(fam_dir.iterdir()):
            if p.is_file():
                if is_license_file(p):
                    lic_candidates.append(p)
                elif p.suffix.lower() not in FONT_EXTS:
                    fam_meta_skipped += 1
            elif p.is_dir() and p.name.lower() == "article":
                fam_meta_skipped += sum(1 for sub in p.rglob("*") if sub.is_file())
        static_dir = fam_dir / "static"
        if not lic_candidates and static_dir.is_dir():
            for p in sorted(static_dir.iterdir()):
                if p.is_file() and is_license_file(p):
                    lic_candidates.append(p)

        fam_lics_copied = 0
        for lic_src in lic_candidates:
            dst_lic = target_dir / lic_src.name
            if not dst_lic.exists():
                shutil.copy2(lic_src, dst_lic)
                fam_lics_copied += 1

        if fam_lics_copied == 0:
            missing_license_families.append(str(fam_dir.relative_to(src_dir.resolve())))

        cs = cat_stats.setdefault(
            cat_slug,
            {
                "category": cat_upper,
                "families": 0,
                "font_files": 0,
                "static_fonts": 0,
                "variable_fonts": 0,
                "license_files": 0,
            },
        )
        cs["families"] += 1
        cs["font_files"] += fam_fonts_copied
        cs["static_fonts"] += fam_static
        cs["variable_fonts"] += fam_variable
        cs["license_files"] += fam_lics_copied

        total_families_copied += 1
        total_fonts_copied += fam_fonts_copied
        total_static_copied += fam_static
        total_variable_copied += fam_variable
        total_licenses_copied += fam_lics_copied
        total_metadata_stripped += fam_meta_skipped

    elapsed = time.perf_counter() - t0
    ext_counts = Counter(
        p.suffix.lower()
        for p in out_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in FONT_EXTS
    )

    summary = {
        "tool_version": TOOL_VERSION,
        "src_dir": str(src_dir.resolve()),
        "out_dir": str(out_dir.resolve()),
        "categories_filter": list(categories) if categories else ["ALL"],
        "latin_only": bool(latin_only),
        "elapsed_seconds": round(elapsed, 2),
        "totals": {
            "families_extracted": total_families_copied,
            "families_filtered_out": total_families_filtered,
            "font_files": total_fonts_copied,
            "static_fonts": total_static_copied,
            "variable_fonts": total_variable_copied,
            "license_files": total_licenses_copied,
            "family_metadata_files_stripped": total_metadata_stripped,
            "non_font_repo_files_skipped": skipped_repo_files,
            "duplicate_font_names_skipped": duplicate_font_skipped,
            "font_extensions": dict(sorted(ext_counts.items())),
        },
        "by_category": dict(sorted(cat_stats.items())),
        "families_without_license_file": missing_license_families,
    }
    summary_path = out_dir / "extraction_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract & sort font binaries and license files from raw font repos, stripping metadata."
    )
    parser.add_argument(
        "--src-dir",
        default="assets/bench_assets",
        help="Input raw font collection directory (default: assets/bench_assets)",
    )
    parser.add_argument(
        "--out-dir",
        default="build/bench_test_fonts",
        help="Clean output qualification test directory (default: build/bench_test_fonts)",
    )
    parser.add_argument(
        "--categories",
        nargs="+",
        default=None,
        help="Optional METADATA.pb category filter (e.g. SANS_SERIF SERIF MONOSPACE)",
    )
    parser.add_argument(
        "--latin-only",
        action="store_true",
        help="When METADATA.pb is present, include only families listing the 'latin' subset",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove existing --out-dir contents before extracting",
    )
    args = parser.parse_args()

    src_dir = Path(args.src_dir)
    out_dir = Path(args.out_dir)
    summary = extract_bench_fonts(
        src_dir=src_dir,
        out_dir=out_dir,
        categories=args.categories,
        latin_only=args.latin_only,
        clean=args.clean,
    )

    t = summary["totals"]
    print(f"[+] Extracted {t['families_extracted']} families ({t['font_files']} fonts: "
          f"{t['static_fonts']} static, {t['variable_fonts']} variable; "
          f"{t['license_files']} licenses) -> {summary['out_dir']} ({summary['elapsed_seconds']:.2f}s)")
    print(f"    Stripped {t['family_metadata_files_stripped']} family metadata files "
          f"(filtered out {t['families_filtered_out']} families, skipped {t['duplicate_font_names_skipped']} duplicates)")
    print("")
    print(f"{'Category':<16} {'Families':>10} {'Fonts':>10} {'Static':>10} {'Variable':>10} {'Licenses':>10}")
    print("-" * 70)
    for cat_slug, cs in summary["by_category"].items():
        print(
            f"{cat_slug:<16} {cs['families']:>10d} {cs['font_files']:>10d} "
            f"{cs['static_fonts']:>10d} {cs['variable_fonts']:>10d} {cs['license_files']:>10d}"
        )
    if summary["families_without_license_file"]:
        print(f"\n[!] {len(summary['families_without_license_file'])} families had no license file in source directory.")
    print(f"[+] Summary written to {Path(summary['out_dir']) / 'extraction_summary.json'}")


if __name__ == "__main__":
    main()
