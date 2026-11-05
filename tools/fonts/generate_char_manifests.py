#!/usr/bin/env python3
"""
generate_char_manifests.py (v1.0.7)
===================================
Humidyne Labs / Humiditron `epd-font` Version-Specific Master Font Character Manifest Generator.

Repository : https://github.com/Humidyne-Labs/epd-font
Author     : Humidyne Labs / Humiditron
License    : MIT License

Purpose:
--------
Generates and maintains a lean, deterministic, version-specific `char_manifest_<family>_v<ver>.json`
inside each master font folder under `assets/font_assets/` and `assets/icon_assets/`.

Why Minimal Character Manifests Instead of Stock Upstream Metadata?
-------------------------------------------------------------------
Upstream icon/font repositories ship multi-megabyte web metadata files (e.g. 16 MB in Tabler,
10.2 MB in Font Awesome 7, 2.15 MB in Phosphor) bloated with full SVG `<path>` vectors,
search aliases, and desktop ligature tables. None of that is needed for 1-bpp FreeType
rasterization or embedded firmware emission.

Each version-specific `char_manifest_<family>_v<ver>.json` records ONLY:
  1. Provenance & Traceability: Upstream repository URL, release version, SPDX license,
     and exact SHA-256 checksums + byte sizes of the untouched master font files.
  2. Codepoint Filter Rules: Valid Unicode/PUA ranges (`min_cp`, `max_cp`) and any excluded
     desktop ligature anchor stubs (such as Phosphor's 30 empty 0x0020..0x007A anchors),
     so the original master `.ttf` files never need to be modified!
  3. Minimal Character / Icon Map: Clean `by_codepoint` ("0xE006": "alarm") and `by_name`
     ("alarm": "0xE006") lookup tables.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from fontTools.ttLib import TTFont

TOOL_VERSION = "1.0.13"

MASTER_FAMILIES_SPEC = [
    {
        "family_id": "ibm_plex_sans",
        "version": "0.2.0",
        "category": "font_assets",
        "rel_dir": "assets/font_assets/ibm-plex-font/sans_v0.2.0",
        "manifest_name": "char_manifest_ibm_plex_sans_v0.2.0.json",
        "upstream_name": "IBM Plex Sans Variable (also source for Condensed wdth=85)",
        "upstream_url": "https://github.com/IBM/plex",
        "spdx_license": "OFL-1.1",
        "master_files": ["IBM Plex Sans Var-Roman.ttf", "IBM Plex Sans Var-Italic.ttf"],
        "min_cp": 0x0020,
        "max_cp": 0xFFFF,
        "cmap_aliases": {},
    },
    {
        "family_id": "ibm_plex_mono",
        "version": "1.0.0",
        "category": "font_assets",
        "rel_dir": "assets/font_assets/ibm-plex-font/mono_v1.0.0",
        "manifest_name": "char_manifest_ibm_plex_mono_v1.0.0.json",
        "upstream_name": "IBM Plex Mono Variable",
        "upstream_url": "https://github.com/IBM/plex",
        "spdx_license": "OFL-1.1",
        "master_files": ["IBM Plex Mono Var-Roman.ttf", "IBM Plex Mono Var-Italic.ttf"],
        "min_cp": 0x0020,
        "max_cp": 0xFFFF,
        "cmap_aliases": {"0x0394": "Delta", "0x03A9": "Omega", "0x03BC": "mu"},
    },
    {
        "family_id": "ibm_plex_serif",
        "version": "2.0.0",
        "category": "font_assets",
        "rel_dir": "assets/font_assets/ibm-plex-font/serif_v2.0.0",
        "manifest_name": "char_manifest_ibm_plex_serif_v2.0.0.json",
        "upstream_name": "IBM Plex Serif Variable",
        "upstream_url": "https://github.com/IBM/plex",
        "spdx_license": "OFL-1.1",
        "master_files": ["IBM Plex Serif Var-Roman.ttf", "IBM Plex Serif Var-Italic.ttf"],
        "min_cp": 0x0020,
        "max_cp": 0xFFFF,
        "cmap_aliases": {},
    },
    {
        "family_id": "ibm_plex_math",
        "version": "1.1.0",
        "category": "font_assets",
        "rel_dir": "assets/font_assets/ibm-plex-font/math_v1.1.0",
        "manifest_name": "char_manifest_ibm_plex_math_v1.1.0.json",
        "upstream_name": "IBM Plex Math Static",
        "upstream_url": "https://github.com/IBM/plex",
        "spdx_license": "OFL-1.1",
        "master_files": ["IBMPlexMath-Regular.ttf"],
        "min_cp": 0x0020,
        "max_cp": 0x10FFFF,
        "cmap_aliases": {},
    },
    {
        "family_id": "terminus",
        "version": "4.49.1",
        "category": "font_assets",
        "rel_dir": "assets/font_assets/terminus_v4.49.1",
        "manifest_name": "char_manifest_terminus_v4.49.1.json",
        "upstream_name": "Terminus Font v4.49.1 (X11 BDF Master Molds -> TrueType)",
        "upstream_url": "https://terminus-font.sourceforge.net/",
        "spdx_license": "OFL-1.1",
        "master_files": ["ter-u12n.bdf", "ter-u12b.bdf", "ter-u14n.bdf", "ter-u14b.bdf", "ter-u14v.bdf", "ter-u16n.bdf", "ter-u16b.bdf", "ter-u16v.bdf", "ter-u18n.bdf", "ter-u18b.bdf", "ter-u20n.bdf", "ter-u20b.bdf", "ter-u22n.bdf", "ter-u22b.bdf", "ter-u24n.bdf", "ter-u24b.bdf", "ter-u28n.bdf", "ter-u28b.bdf", "ter-u32n.bdf", "ter-u32b.bdf"],
        "min_cp": 0x0020,
        "max_cp": 0xFFFF,
        "cmap_aliases": {},
    },
    {
        "family_id": "icon_fa7",
        "version": "7.3.1",
        "category": "icon_assets",
        "rel_dir": "assets/icon_assets/font_awsome_v7.3.1",
        "manifest_name": "char_manifest_fontawesome_v7.3.1.json",
        "upstream_name": "Font Awesome Free v7.0.0 / v7.3.1",
        "upstream_url": "https://github.com/FortAwesome/Font-Awesome",
        "spdx_license": "CC-BY-4.0 AND OFL-1.1",
        "master_files": [
            "Font Awesome 7 Free-Solid-900.otf",
            "Font Awesome 7 Free-Regular-400.otf",
            "Font Awesome 7 Brands-Regular-400.otf",
        ],
        "min_cp": 0xE000,
        "max_cp": 0xF8FF,
        "cmap_aliases": {},
    },
    {
        "family_id": "icon_lucide",
        "version": "1.67.0",
        "category": "icon_assets",
        "rel_dir": "assets/icon_assets/lucide_icons_v1.67.0",
        "manifest_name": "char_manifest_lucide_v1.67.0.json",
        "upstream_name": "Lucide Icons v1.67.0",
        "upstream_url": "https://github.com/lucide-icons/lucide",
        "spdx_license": "ISC",
        "master_files": ["lucide.ttf"],
        "min_cp": 0xE000,
        "max_cp": 0xF8FF,
        "cmap_aliases": {},
    },
    {
        "family_id": "icon_phosphor",
        "version": "2.1.0",
        "category": "icon_assets",
        "rel_dir": "assets/icon_assets/phosphor_icons_v2.1.0",
        "manifest_name": "char_manifest_phosphor_v2.1.0.json",
        "upstream_name": "Phosphor Icons v2.1.0",
        "upstream_url": "https://github.com/phosphor-icons/homepage",
        "spdx_license": "MIT",
        "master_files": [
            "Phosphor.ttf",
            "Phosphor-Bold.ttf",
            "Phosphor-Fill.ttf",
            "Phosphor-Light.ttf",
            "Phosphor-Thin.ttf",
        ],
        "min_cp": 0xE000,
        "max_cp": 0xF8FF,
        "cmap_aliases": {},
    },
    {
        "family_id": "icon_tabler",
        "version": "3.50.0",
        "category": "icon_assets",
        "rel_dir": "assets/icon_assets/tabler_icons_v3.50.0",
        "manifest_name": "char_manifest_tabler_v3.50.0.json",
        "upstream_name": "Tabler Icons v3.50.0",
        "upstream_url": "https://github.com/tabler/tabler-icons",
        "spdx_license": "MIT",
        "master_files": [
            "tabler-icons.ttf",
            "tabler-icons-200.ttf",
            "tabler-icons-300.ttf",
            "tabler-icons-filled.ttf",
        ],
        "min_cp": 0xE000,
        "max_cp": 0x10FFFF,
        "cmap_aliases": {},
    },
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_bdf_codepoints(bdf_path: Path) -> Dict[int, str]:
    out: Dict[int, str] = {}
    if not bdf_path.is_file():
        return out
    cur_name = ""
    for line in bdf_path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if s.startswith("STARTCHAR "):
            cur_name = s.split(None, 1)[1].strip()
        elif s.startswith("ENCODING "):
            cp = int(s.split()[1])
            if cp >= 0x0020:
                out[cp] = cur_name or f"uni{cp:04X}"
    return out


def build_char_manifest_for_spec(
    repo_root: Path,
    spec: dict,
    existing_unified_icons: Optional[dict] = None,
    clean_legacy_metadata_dirs: bool = False,
) -> Tuple[Path, dict]:
    folder = repo_root / spec["rel_dir"]
    manifest_path = folder / spec["manifest_name"]
    min_cp = int(spec["min_cp"])
    max_cp = int(spec["max_cp"])
    fam_id = spec["family_id"]

    # Check if an existing manifest or legacy metadata json has semantic icon names
    cp_to_name: Dict[int, str] = {}

    if existing_unified_icons and fam_id in existing_unified_icons.get("by_codepoint", {}):
        for hex_k, iname in existing_unified_icons["by_codepoint"][fam_id].items():
            cp_to_name[int(hex_k, 16)] = iname

    # Also check any legacy metadata/*.json in folder before cleaning
    meta_sub = folder / "metadata"
    if meta_sub.is_dir():
        for jf in meta_sub.glob("*.json"):
            try:
                data = json.loads(jf.read_text(encoding="utf-8"))
                if jf.name == "icons.json" and fam_id == "icon_fa7":
                    for k, v in data.items():
                        if isinstance(v, dict) and "unicode" in v:
                            cp_to_name.setdefault(int(v["unicode"], 16), k)
                elif jf.name == "codepoints.json" and fam_id == "icon_lucide":
                    for k, v in data.items():
                        cp_to_name.setdefault(int(v), k)
                elif jf.name == "selection.json" and fam_id == "icon_phosphor":
                    for ic in data.get("icons", []):
                        props = ic.get("properties", {})
                        if "code" in props and "name" in props:
                            cp_to_name.setdefault(int(props["code"]), str(props["name"]).split(",")[0].strip())
            except Exception:
                pass

    # If manifest already exists on disk, preserve any semantic names from it
    if manifest_path.is_file():
        try:
            old_m = json.loads(manifest_path.read_text(encoding="utf-8"))
            for hex_k, iname in old_m.get("by_codepoint", {}).items():
                cp_to_name.setdefault(int(hex_k, 16), iname)
        except Exception:
            pass

    master_records = []
    ignored_below_min_cp = 0

    for mf_name in spec["master_files"]:
        mf_path = folder / mf_name
        if not mf_path.is_file():
            continue
        rec = {
            "filename": mf_name,
            "size_bytes": mf_path.stat().st_size,
            "sha256": sha256_file(mf_path),
        }
        if mf_name.lower().endswith((".ttf", ".otf")):
            tt = TTFont(str(mf_path))
            cmap = tt.getBestCmap() or {}
            rec["upem"] = int(tt["head"].unitsPerEm)
            rec["ascent"] = int(tt["hhea"].ascent)
            rec["descent"] = int(tt["hhea"].descent)
            rec["total_raw_cmap_entries"] = len(cmap)
            valid_cnt = 0
            is_filled_tabler = "filled" in mf_name.lower() and fam_id == "icon_tabler"
            for cp, gname in sorted(cmap.items()):
                if cp < min_cp:
                    ignored_below_min_cp += 1
                    continue
                if cp > max_cp:
                    continue
                valid_cnt += 1
                if cp not in cp_to_name or cp_to_name[cp].startswith("uni"):
                    clean_g = gname
                    if is_filled_tabler and not clean_g.endswith("-filled"):
                        clean_g = f"{clean_g}-filled"
                    cp_to_name[cp] = clean_g
            rec["valid_codepoints"] = valid_cnt
        elif mf_name.lower().endswith(".bdf"):
            bdf_map = parse_bdf_codepoints(mf_path)
            rec["valid_codepoints"] = len(bdf_map)
            for cp, gname in bdf_map.items():
                cp_to_name.setdefault(cp, gname)
        master_records.append(rec)

    for hex_k, alias_name in spec.get("cmap_aliases", {}).items():
        cp_to_name[int(hex_k, 16)] = alias_name

    by_codepoint = {f"0x{cp:04X}": name for cp, name in sorted(cp_to_name.items()) if min_cp <= cp <= max_cp}
    by_name = {name: hex_cp for hex_cp, name in sorted(by_codepoint.items(), key=lambda x: x[1])}

    manifest_payload = {
        "manifest_schema": "epd-font-char-manifest-v1.0.13",
        "generator": f"tools/fonts/generate_char_manifests.py (v{TOOL_VERSION})",
        "family_id": fam_id,
        "upstream_name": spec["upstream_name"],
        "upstream_version": spec["version"],
        "upstream_url": spec["upstream_url"],
        "spdx_license": spec["spdx_license"],
        "codepoint_filter": {
            "min_cp_hex": f"0x{min_cp:04X}",
            "max_cp_hex": f"0x{max_cp:04X}",
            "ignored_non_pua_ligature_stubs": ignored_below_min_cp,
        },
        "total_valid_characters": len(by_codepoint),
        "master_files": master_records,
        "by_codepoint": by_codepoint,
        "by_name": by_name,
    }

    manifest_path.write_text(json.dumps(manifest_payload, indent=2) + "\n", encoding="utf-8")

    if clean_legacy_metadata_dirs and meta_sub.is_dir():
        shutil.rmtree(meta_sub)

    return manifest_path, manifest_payload


def generate_all_char_manifests(repo_root: Path, clean_legacy: bool = False) -> List[Path]:
    uni_path = repo_root / "build" / "metadata" / "unified_icon_names.json"
    existing_uni = json.loads(uni_path.read_text(encoding="utf-8")) if uni_path.is_file() else None

    out_paths = []
    print("=" * 102)
    print(f"HUMIDYNE LABS / HUMIDITRON epd-font v{TOOL_VERSION} — MASTER CHARACTER MANIFEST GENERATOR")
    print("=" * 102)
    for spec in MASTER_FAMILIES_SPEC:
        m_path, m_data = build_char_manifest_for_spec(
            repo_root, spec, existing_unified_icons=existing_uni, clean_legacy_metadata_dirs=clean_legacy
        )
        out_paths.append(m_path)
        sz_kb = m_path.stat().st_size / 1024.0
        print(
            f"  [+] {m_path.relative_to(repo_root).as_posix():72s} | "
            f"{m_data['total_valid_characters']:5,d} chars | {sz_kb:6.1f} KB"
        )
    print("=" * 102)
    return out_paths


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="generate_char_manifests.py",
        description="Generate version-specific minimal Character Manifest JSONs per master font family.",
    )
    parser.add_argument(
        "--clean-stock-metadata",
        action="store_true",
        help="Remove bloated upstream stock metadata/ folders after generating the minimal char_manifest_*.json",
    )
    args = parser.parse_args()
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent if script_dir.name == "fonts" else script_dir.parent
    generate_all_char_manifests(repo_root, clean_legacy=args.clean_stock_metadata)


if __name__ == "__main__":
    main()
