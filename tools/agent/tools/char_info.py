#!/usr/bin/env python3
"""
char_info.py (v1.0.9) — Agent-First Deterministic Character & Icon Metric Inspector
===================================================================================
Queries exact 1-bpp glyph metrics (advance width, bounding box, bearing offsets,
UTF-8 C literal, and 1:1 ASCII bitmap) from a compiled Strike Vault (`dist/*/*.json.gz`),
metrics CSV (`build/*/metrics/`), or directly from `build/metadata/*_catalog.json`.

Zero guesswork: AI agents and firmware engineers must run this tool to inspect
exact pixel dimensions and bitmaps of characters or icons before hardcoding offsets.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional


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
        repo_root / "dist" / "humid1_epd_vault.json.gz",
        repo_root / "dist" / "h1os_distro" / "humid1_epd_vault.json.gz",
        repo_root / "dist" / "example_distro" / "humid1_epd_vault.json.gz",
        repo_root / "dist" / "audit_distro" / "humid1_epd_vault.json.gz",
        repo_root / "build" / "dist" / "humid1_epd_vault.json.gz",
    ])
    for c in candidates:
        if c.is_file():
            if c.name.endswith(".gz"):
                with gzip.open(c, "rt", encoding="utf-8") as f:
                    return json.load(f)
            return json.loads(c.read_text(encoding="utf-8"))
    return {"strikes": {}}


def resolve_query_to_codepoint(query: str, repo_root: Path, family: str = "") -> int:
    q = query.strip()
    if q.upper().startswith("U+"):
        return int(q[2:], 16)
    if q.lower().startswith("0x"):
        return int(q, 16)
    if len(q) == 1:
        return ord(q)
    if q.isdigit():
        return int(q)

    # Search unified_icon_names.json by semantic name
    uni_path = repo_root / "build" / "metadata" / "unified_icon_names.json"
    if uni_path.is_file():
        data = json.loads(uni_path.read_text(encoding="utf-8"))
        by_name = data.get("by_name", {})
        vendors = [family] if family in by_name else list(by_name.keys())
        for v in vendors:
            vmap = by_name.get(v, {})
            if q in vmap:
                return int(vmap[q], 16)
            for k, hex_cp in vmap.items():
                if k.lower() == q.lower():
                    return int(hex_cp, 16)
    raise ValueError(f"Could not resolve '{query}' to a Unicode codepoint or icon name.")


def cp_to_c_utf8_escape(cp: int) -> str:
    b = chr(cp).encode("utf-8")
    return "".join(f"\\x{byte:02X}" for byte in b)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="char_info.py",
        description="Deterministic 1-bpp character & icon metric inspector for AI agents and engineers.",
    )
    parser.add_argument("--strike", "-s", type=str, default="humid1_font_plex_sans_normal_14", help="Strike symbol (e.g. plex_sans_normal_14, plex_icon_phosphor_fill_20)")
    parser.add_argument("--char", "-c", type=str, required=True, help="Character ('A', '@'), hex ('0x0040', 'U+E006'), or icon name ('alarm', 'wifi-high')")
    parser.add_argument("--vault", "-v", type=str, default=None, help="Optional path to humid1_epd_vault.json.gz")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    repo_root = find_repo_root()
    vault = load_vault(repo_root, args.vault)
    strikes = vault.get("strikes", {})

    if args.strike not in strikes:
        for alt in (f"humid1_font_{args.strike}", f"humid1_{args.strike}", f"humid1_font_plex_{args.strike}"):
            if alt in strikes:
                args.strike = alt
                break
    if args.strike not in strikes:
        print(f"[!] Strike '{args.strike}' not found in vault. Available strikes: {', '.join(sorted(strikes.keys())[:15])}...", file=sys.stderr)
        sys.exit(1)

    st = strikes[args.strike]
    cp = resolve_query_to_codepoint(args.char, repo_root, family=st.get("family", ""))

    glyph = None
    for g in st.get("glyphs", []):
        if int(g["cp"]) == cp:
            glyph = g
            break

    if not glyph:
        print(f"[!] Codepoint 0x{cp:04X} not present in strike '{args.strike}'.", file=sys.stderr)
        sys.exit(1)

    adv_px = (int(glyph["adv_w_fp4"]) + 8) >> 4
    result = {
        "strike": args.strike,
        "family": st.get("family"),
        "style": st.get("style"),
        "size_px": st.get("size_px"),
        "line_height_px": st.get("line_height"),
        "base_line_px": st.get("base_line"),
        "codepoint_dec": cp,
        "codepoint_hex": f"0x{cp:04X}",
        "unicode_tag": f"U+{cp:04X}",
        "c_utf8_literal": f'"{cp_to_c_utf8_escape(cp)}"',
        "name": glyph.get("name", ""),
        "glyph_id": glyph.get("gid"),
        "adv_w_px": adv_px,
        "adv_w_fp4": glyph.get("adv_w_fp4"),
        "box_w_px": glyph.get("box_w"),
        "box_h_px": glyph.get("box_h"),
        "ofs_x_px": glyph.get("ofs_x"),
        "ofs_y_px": glyph.get("ofs_y"),
        "patched": glyph.get("patched", False),
        "rows": glyph.get("rows", []),
    }

    if args.json:
        print(json.dumps(result, indent=2))
        return

    print("=" * 72)
    print(f"CHARACTER / ICON METRIC REPORT — {args.strike}")
    print("=" * 72)
    print(f"  Query / Name    : {args.char} -> '{result['name']}'")
    print(f"  Codepoint       : {result['codepoint_hex']} ({result['unicode_tag']}, dec={cp})")
    print(f"  C UTF-8 Literal : {result['c_utf8_literal']}")
    print(f"  Strike Metrics  : size={result['size_px']}px, line_height={result['line_height_px']}px, base_line={result['base_line_px']}px")
    print(f"  Advance Width   : {result['adv_w_px']} px (fp4={result['adv_w_fp4']})")
    print(f"  Bounding Box    : w={result['box_w_px']} px, h={result['box_h_px']} px")
    print(f"  Bearing Offsets : ofs_x={result['ofs_x_px']:+d} px, ofs_y={result['ofs_y_px']:+d} px")
    print(f"  Patched State   : {'PATCHED' if result['patched'] else 'BASELINE'}")
    print("-" * 72)
    for idx, r in enumerate(result["rows"]):
        spaced = " ".join("#" if ch == "#" else "." for ch in r)
        print(f"  row {idx:02d} | {spaced}")
    print("=" * 72)


if __name__ == "__main__":
    main()
