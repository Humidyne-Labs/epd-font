#!/usr/bin/env python3
"""
epd_typography.py (v1.0.23) — Canonical Single-Source EPD Font, Icon & Layout Engine
=====================================================================================
Provides unified, zero-dependency Python stdlib typography inspection over:
  1. Pre-rasterized Strike Vaults (`humid1_epd_vault.json.gz`)
  2. Per-strike CSV metric & kerning manifests (`char_widths_<sym>.csv`, `kern_pairs_<sym>.csv`)
  3. Unified PUA icon catalogs (`unified_icon_names.json`)
  4. C/C++ UI screen string-width auditing against target display margins (`esp32s3-N8R8-hw_scheme.json`)

Used directly by the `tools/agent/tools/*.py` CLI wrappers and the `embedded-ops` MCP server.
"""

from __future__ import annotations

import codecs
import csv
import gzip
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

TOOL_VERSION = "1.0.23"

# Built-in FontAwesome PUA mappings for LVGL built-in LV_SYMBOL_* macros
LVGL_SYMBOL_MAP: Dict[str, str] = {
    "LV_SYMBOL_AUDIO": "\uf001",
    "LV_SYMBOL_VIDEO": "\uf008",
    "LV_SYMBOL_LIST": "\uf00b",
    "LV_SYMBOL_OK": "\uf00c",
    "LV_SYMBOL_CLOSE": "\uf00d",
    "LV_SYMBOL_POWER": "\uf011",
    "LV_SYMBOL_SETTINGS": "\uf013",
    "LV_SYMBOL_HOME": "\uf015",
    "LV_SYMBOL_DOWNLOAD": "\uf019",
    "LV_SYMBOL_DRIVE": "\uf01c",
    "LV_SYMBOL_REFRESH": "\uf021",
    "LV_SYMBOL_MUTE": "\uf026",
    "LV_SYMBOL_VOLUME_MID": "\uf027",
    "LV_SYMBOL_VOLUME_MAX": "\uf028",
    "LV_SYMBOL_IMAGE": "\uf03e",
    "LV_SYMBOL_TINT": "\uf043",
    "LV_SYMBOL_PREV": "\uf048",
    "LV_SYMBOL_PLAY": "\uf04b",
    "LV_SYMBOL_PAUSE": "\uf04c",
    "LV_SYMBOL_STOP": "\uf04d",
    "LV_SYMBOL_NEXT": "\uf051",
    "LV_SYMBOL_PLUS": "\uf067",
    "LV_SYMBOL_MINUS": "\uf068",
    "LV_SYMBOL_WARNING": "\uf071",
    "LV_SYMBOL_EYE_OPEN": "\uf06e",
    "LV_SYMBOL_EYE_CLOSE": "\uf070",
    "LV_SYMBOL_WIFI": "\uf1eb",
    "LV_SYMBOL_BATTERY_FULL": "\uf240",
    "LV_SYMBOL_BATTERY_3": "\uf241",
    "LV_SYMBOL_BATTERY_2": "\uf242",
    "LV_SYMBOL_BATTERY_1": "\uf243",
    "LV_SYMBOL_BATTERY_EMPTY": "\uf244",
    "LV_SYMBOL_USB": "\uf287",
    "LV_SYMBOL_BLUETOOTH": "\uf293",
    "LV_SYMBOL_CHARGE": "\uf0e7",
    "LV_SYMBOL_BELL": "\uf0f3",
    "LV_SYMBOL_SD_CARD": "\uf7c2",
}

_VAULT_CACHE: Dict[str, Tuple[float, dict]] = {}


def epd_font_repo_root() -> Path:
    """Return the canonical `epd-font` repository root containing this module."""
    cur = Path(__file__).resolve().parent
    for _ in range(5):
        if (cur / "VERSION.json").is_file() or (cur / "tools" / "fonts").is_dir():
            return cur
        cur = cur.parent
    return Path.cwd()


def resolve_workspace_root(workspace_dir: Optional[str | Path] = None) -> Path:
    """Resolve the active workspace (explicit path, matching CWD repo, or `epd-font`)."""
    if workspace_dir:
        return Path(workspace_dir).expanduser().resolve()
    cwd = Path.cwd().resolve()
    if any(
        (cwd / marker).exists()
        for marker in ("components/h1os", "VERSION.json", "tools/fonts", "firmware", "dist")
    ):
        return cwd
    return epd_font_repo_root()


def _dedup_paths(paths: Sequence[Path]) -> List[Path]:
    out: List[Path] = []
    seen = set()
    for p in paths:
        rp = str(p.resolve()) if p.exists() else str(p)
        if rp not in seen:
            seen.add(rp)
            out.append(p)
    return out


def discover_artifacts(
    workspace_dir: Optional[str | Path] = None,
    vault_path: Optional[str | Path] = None,
    metrics_dir: Optional[str | Path] = None,
    metadata_dir: Optional[str | Path] = None,
) -> dict:
    """
    Locate Strike Vault, CSV metrics directory, icon metadata catalog, header directories,
    hardware scheme files, and profile schemes, prioritizing `workspace_dir` before falling back to `epd-font`.
    """
    ws = resolve_workspace_root(workspace_dir)
    ef = epd_font_repo_root()
    roots = _dedup_paths([ws, ef])

    found_vault: Optional[Path] = None
    if vault_path:
        vp = Path(vault_path).expanduser().resolve()
        if vp.is_file():
            found_vault = vp
    if found_vault is None:
        for r in roots:
            cands = [
                r / "components" / "h1os" / "tools" / "fonts" / "humid1_epd_vault.json.gz",
                r / "firmware" / "components" / "h1os" / "tools" / "fonts" / "humid1_epd_vault.json.gz",
                *sorted((r / "firmware" / "managed_components").glob("*h1os*/tools/fonts/humid1_epd_vault.json.gz") if (r / "firmware" / "managed_components").is_dir() else []),
                r / "dist" / "h1os_distro" / "humid1_epd_vault.json.gz",
                r / "dist" / "humid1_epd_vault.json.gz",
                *sorted((r / "dist").glob("*/humid1_epd_vault.json.gz") if (r / "dist").is_dir() else []),
                *sorted((r / "build").glob("*/dist/humid1_epd_vault.json.gz") if (r / "build").is_dir() else []),
                r / "build" / "dist" / "humid1_epd_vault.json.gz",
            ]
            for c in cands:
                if c.is_file():
                    found_vault = c.resolve()
                    break
            if found_vault is not None:
                break

    found_metrics: Optional[Path] = None
    if metrics_dir:
        mp = Path(metrics_dir).expanduser().resolve()
        if mp.is_dir():
            found_metrics = mp
    if found_metrics is None:
        for r in roots:
            cands = [
                r / "components" / "h1os" / "tools" / "fonts" / "metrics",
                r / "firmware" / "components" / "h1os" / "tools" / "fonts" / "metrics",
                *sorted((r / "firmware" / "managed_components").glob("*h1os*/tools/fonts/metrics") if (r / "firmware" / "managed_components").is_dir() else []),
                r / "dist" / "h1os_distro" / "metrics",
                r / "build" / "h1os" / "metrics",
                *sorted((r / "dist").glob("*/metrics") if (r / "dist").is_dir() else []),
                *sorted((r / "build").glob("*/metrics") if (r / "build").is_dir() else []),
                r / "tools" / "fonts" / "metrics",
                r / "firmware" / "tools" / "fonts" / "metrics",
            ]
            for c in cands:
                if c.is_dir() and any(c.glob("char_widths_*.csv")):
                    found_metrics = c.resolve()
                    break
            if found_metrics is not None:
                break

    found_meta_dir: Optional[Path] = None
    found_uni: Optional[Path] = None
    if metadata_dir:
        md = Path(metadata_dir).expanduser().resolve()
        if (md / "unified_icon_names.json").is_file():
            found_meta_dir = md
            found_uni = (md / "unified_icon_names.json").resolve()
    if found_uni is None:
        for r in roots:
            cands = [
                r / "components" / "h1os" / "tools" / "fonts" / "metadata",
                r / "firmware" / "components" / "h1os" / "tools" / "fonts" / "metadata",
                *sorted((r / "firmware" / "managed_components").glob("*h1os*/tools/fonts/metadata") if (r / "firmware" / "managed_components").is_dir() else []),
                r / "dist" / "h1os_distro" / "metadata",
                r / "build" / "metadata",
                *sorted((r / "dist").glob("*/metadata") if (r / "dist").is_dir() else []),
            ]
            for c in cands:
                if (c / "unified_icon_names.json").is_file():
                    found_meta_dir = c.resolve()
                    found_uni = (c / "unified_icon_names.json").resolve()
                    break
            if found_uni is not None:
                break

    header_dirs: List[Path] = []
    for r in roots:
        for c in (
            r / "components" / "h1os" / "tools" / "fonts" / "fonts",
            r / "firmware" / "components" / "h1os" / "tools" / "fonts" / "fonts",
            *sorted((r / "firmware" / "managed_components").glob("*h1os*/tools/fonts/fonts") if (r / "firmware" / "managed_components").is_dir() else []),
            r / "dist" / "h1os_distro" / "fonts",
            r / "build" / "h1os" / "fonts",
        ):
            if c.is_dir():
                header_dirs.append(c.resolve())

    return {
        "workspace_root": ws,
        "epd_font_root": ef,
        "roots": roots,
        "vault_path": found_vault,
        "metrics_dir": found_metrics,
        "metadata_dir": found_meta_dir,
        "unified_icon_names": found_uni,
        "header_dirs": _dedup_paths(header_dirs),
    }


def _read_vault(vault_path: Optional[Path]) -> dict:
    if vault_path is None or not vault_path.is_file():
        return {"strikes": {}}
    key = str(vault_path.resolve())
    mtime = vault_path.stat().st_mtime
    cached = _VAULT_CACHE.get(key)
    if cached and cached[0] == mtime:
        return cached[1]
    if vault_path.name.endswith(".gz"):
        with gzip.open(vault_path, "rt", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = json.loads(vault_path.read_text(encoding="utf-8"))
    _VAULT_CACHE[key] = (mtime, data)
    return data


def _normalize_strike_candidates(strike_name: str) -> List[str]:
    s = strike_name.strip()
    cands = [s]
    if not s.startswith("humid1_"):
        cands.extend([
            f"humid1_font_{s}",
            f"humid1_{s}",
            f"humid1_font_plex_{s}",
        ])
    return cands


def _infer_family_style_size(strike_name: str) -> Tuple[str, str, Optional[int]]:
    m_sz = re.search(r"_(\d+)$", strike_name)
    sz = int(m_sz.group(1)) if m_sz else None
    body = re.sub(r"_\d+$", "", strike_name)
    if body.startswith("humid1_icon_"):
        rest = body[len("humid1_icon_"):]
        parts = rest.split("_", 1)
        return f"icon_{parts[0]}", (parts[1] if len(parts) > 1 else "regular"), sz
    if body.startswith("humid1_font_"):
        rest = body[len("humid1_font_"):]
        for fam in ("plex_sans", "plex_mono", "plex_cond", "plex_serif", "plex_math",
                    "noto_sans", "noto_mono", "noto_cond", "noto_serif", "noto_math", "terminus", "unifont"):
            if rest.startswith(fam + "_"):
                return fam, rest[len(fam) + 1:], sz
        parts = rest.split("_", 1)
        return parts[0], (parts[1] if len(parts) > 1 else "normal"), sz
    return "custom", "normal", sz


def _load_strike_from_csv(strike_name: str, metrics_dir: Optional[Path]) -> Optional[Tuple[str, dict]]:
    if metrics_dir is None or not metrics_dir.is_dir():
        return None
    for cand in _normalize_strike_candidates(strike_name):
        cw_csv = metrics_dir / f"char_widths_{cand}.csv"
        if not cw_csv.is_file():
            continue
        fam, style, sz = _infer_family_style_size(cand)
        glyphs: List[dict] = []
        with cw_csv.open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                cp = int(row["unicode_dec"])
                adv_fp4 = int(row["adv_w_raw"])
                glyphs.append({
                    "cp": cp,
                    "gid": cp,
                    "name": row.get("char", ""),
                    "adv_w_fp4": adv_fp4,
                    "box_w": int(row["box_w"]),
                    "box_h": int(row["box_h"]),
                    "ofs_x": int(row["ofs_x"]),
                    "ofs_y": int(row["ofs_y"]),
                    "rows": [],
                    "patched": False,
                })
        kp_csv = metrics_dir / f"kern_pairs_{cand}.csv"
        kern_cp: Dict[Tuple[int, int], int] = {}
        if kp_csv.is_file():
            with kp_csv.open("r", encoding="utf-8-sig", newline="") as kf:
                for krow in csv.DictReader(kf):
                    lc = int(krow["left_code"], 16)
                    rc = int(krow["right_code"], 16)
                    kern_cp[(lc, rc)] = int(krow["kern_raw_16th"])
        return cand, {
            "family": fam,
            "style": style,
            "size_px": sz,
            "line_height": None,
            "base_line": None,
            "underline_position": None,
            "underline_thickness": None,
            "glyphs": glyphs,
            "kern_cp": kern_cp,
            "source": "csv",
            "csv_path": str(cw_csv),
        }
    return None


def load_strike(
    strike_name: str,
    artifacts: dict,
    prefer_csv: bool = False,
) -> Tuple[str, dict]:
    """Load a font/icon strike from Vault or CSV manifests, returning `(resolved_name, normalized_strike_dict)`."""
    metrics_dir: Optional[Path] = artifacts.get("metrics_dir")
    vault_path: Optional[Path] = artifacts.get("vault_path")

    if prefer_csv:
        csv_loaded = _load_strike_from_csv(strike_name, metrics_dir)
        if csv_loaded is not None:
            return csv_loaded

    vault = _read_vault(vault_path)
    strikes = vault.get("strikes", {})
    for cand in _normalize_strike_candidates(strike_name):
        if cand in strikes:
            st = strikes[cand]
            gid_to_cp = {int(g["gid"]): int(g["cp"]) for g in st.get("glyphs", []) if "gid" in g}
            kern_cp: Dict[Tuple[int, int], int] = {}
            for kp in st.get("kern_pairs", []):
                l_cp = gid_to_cp.get(int(kp[0]))
                r_cp = gid_to_cp.get(int(kp[1]))
                if l_cp is not None and r_cp is not None:
                    kern_cp[(l_cp, r_cp)] = int(kp[2])
            csv_file = (metrics_dir / f"char_widths_{cand}.csv") if metrics_dir else None
            return cand, {
                "family": st.get("family"),
                "style": st.get("style"),
                "size_px": st.get("size_px"),
                "line_height": st.get("line_height"),
                "base_line": st.get("base_line"),
                "underline_position": st.get("underline_position"),
                "underline_thickness": st.get("underline_thickness"),
                "glyphs": st.get("glyphs", []),
                "kern_cp": kern_cp,
                "source": "vault",
                "csv_path": str(csv_file) if (csv_file and csv_file.is_file()) else None,
            }

    csv_loaded = _load_strike_from_csv(strike_name, metrics_dir)
    if csv_loaded is not None:
        return csv_loaded

    avail = sorted(strikes.keys())[:15]
    if not avail and metrics_dir and metrics_dir.is_dir():
        avail = sorted(p.stem.replace("char_widths_", "") for p in metrics_dir.glob("char_widths_*.csv"))[:15]
    raise KeyError(f"Strike '{strike_name}' not found in Vault or CSV manifests. Sample available: {avail}")


def resolve_query_to_codepoint(
    query: str,
    artifacts: dict,
    family: str = "",
    style: str = "",
) -> int:
    """Resolve character, U+XXXX, 0xXXXX, integer codepoint, or semantic icon name to Unicode codepoint."""
    q = query.strip()
    if q.upper().startswith("U+"):
        return int(q[2:], 16)
    if q.lower().startswith("0x"):
        return int(q, 16)
    if len(q) == 1:
        return ord(q)
    if q.isdigit():
        return int(q)

    uni_path: Optional[Path] = artifacts.get("unified_icon_names")
    if uni_path and uni_path.is_file():
        data = json.loads(uni_path.read_text(encoding="utf-8"))
        by_name = data.get("by_name", {})
        if family == "icon_tabler" and "filled" in str(style).lower():
            vendors = ["icon_tabler_filled", "icon_tabler"]
        elif family in by_name:
            vendors = [family]
        else:
            vendors = list(by_name.keys())
        for v in vendors:
            vmap = by_name.get(v, {})
            if q in vmap:
                return int(vmap[q], 16)
            q_low = q.lower()
            for k, hex_cp in vmap.items():
                if k.lower() == q_low:
                    return int(hex_cp, 16)
    raise ValueError(f"Could not resolve '{query}' to a Unicode codepoint or semantic icon name.")


def cp_to_c_utf8_escape(cp: int) -> str:
    return "".join(f"\\x{byte:02X}" for byte in chr(cp).encode("utf-8"))


def _resolve_hw_display(hw_scheme: str, artifacts: dict) -> Tuple[int, int]:
    """Return `(screen_width_px, safe_margin_px)` from hardware scheme JSON (default 200, 6)."""
    cands: List[Path] = []
    hp = Path(hw_scheme)
    if hp.is_absolute():
        cands.append(hp)
    for r in artifacts["roots"]:
        cands.extend([
            r / hw_scheme,
            r / "components" / "h1os" / "tools" / "fonts" / "schemes" / hw_scheme,
            r / "firmware" / "components" / "h1os" / "tools" / "fonts" / "schemes" / hw_scheme,
            *sorted((r / "firmware" / "managed_components").glob(f"*h1os*/tools/fonts/schemes/{hw_scheme}") if (r / "firmware" / "managed_components").is_dir() else []),
            r / "dist" / "h1os_distro" / hw_scheme,
            r / "dist" / "h1os_distro" / "schemes" / hw_scheme,
        ])
    for c in cands:
        if c.is_file():
            disp = json.loads(c.read_text(encoding="utf-8")).get("display", {})
            return int(disp.get("width_px", 200)), int(disp.get("safe_margin_px", 6))
    return 200, 6


def inspect_char(
    strike: str,
    char_query: str,
    workspace_dir: Optional[str | Path] = None,
    vault_path: Optional[str | Path] = None,
    metrics_dir: Optional[str | Path] = None,
    prefer_csv: bool = False,
) -> dict:
    """Return exact 1-bpp metrics (plus rows bitmap when backed by Vault) for a single character or icon."""
    artifacts = discover_artifacts(workspace_dir, vault_path=vault_path, metrics_dir=metrics_dir)
    resolved_strike, st = load_strike(strike, artifacts, prefer_csv=prefer_csv)
    cp = resolve_query_to_codepoint(
        char_query,
        artifacts,
        family=str(st.get("family", "")),
        style=str(st.get("style", "")),
    )

    glyph = None
    for g in st.get("glyphs", []):
        if int(g["cp"]) == cp:
            glyph = g
            break
    if glyph is None:
        raise KeyError(f"Codepoint 0x{cp:04X} not present in strike '{resolved_strike}'.")

    adv_fp4 = int(glyph["adv_w_fp4"])
    adv_px = (adv_fp4 + 8) >> 4
    return {
        "strike": resolved_strike,
        "source": st["source"],
        "csv_path": st.get("csv_path"),
        "family": st.get("family"),
        "style": st.get("style"),
        "size_px": st.get("size_px"),
        "line_height_px": st.get("line_height"),
        "base_line_px": st.get("base_line"),
        "underline_position": st.get("underline_position"),
        "underline_thickness": st.get("underline_thickness"),
        "codepoint_dec": cp,
        "codepoint_hex": f"0x{cp:04X}",
        "unicode_tag": f"U+{cp:04X}",
        "c_utf8_literal": f'"{cp_to_c_utf8_escape(cp)}"',
        "name": glyph.get("name", ""),
        "glyph_id": glyph.get("gid"),
        "adv_w_px": adv_px,
        "adv_w_fp4": adv_fp4,
        "box_w_px": int(glyph["box_w"]),
        "box_h_px": int(glyph["box_h"]),
        "ofs_x_px": int(glyph["ofs_x"]),
        "ofs_y_px": int(glyph["ofs_y"]),
        "patched": bool(glyph.get("patched", False)),
        "rows": glyph.get("rows", []),
    }


def measure_string_exact(
    text: str,
    strike_data: dict,
    fallback_strikes: Sequence[dict] = (),
) -> Tuple[int, List[dict]]:
    """Compute exact LVGL v9 rendered pixel width `(adv_w_fp4 + kern_fp4 + 8) >> 4` across `text`."""
    cp_map = {int(g["cp"]): g for g in strike_data.get("glyphs", [])}
    fb_maps = [{int(g["cp"]): g for g in fb.get("glyphs", [])} for fb in fallback_strikes]
    cp_kern: Dict[Tuple[int, int], int] = strike_data.get("kern_cp", {})

    total_px = 0
    breakdown: List[dict] = []
    chars = list(text)
    for i, ch in enumerate(chars):
        cp = ord(ch)
        g = cp_map.get(cp)
        if g is None:
            for fm in fb_maps:
                if cp in fm:
                    g = fm[cp]
                    break
        if g is None:
            breakdown.append({"char": ch, "cp": f"0x{cp:04X}", "found": False, "step_px": 0, "adv_w_fp4": 0, "kern_fp4": 0})
            continue
        adv_fp4 = int(g["adv_w_fp4"])
        kern_fp4 = 0
        if i + 1 < len(chars):
            next_cp = ord(chars[i + 1])
            if cp in cp_map and next_cp in cp_map:
                kern_fp4 = cp_kern.get((cp, next_cp), 0)
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
            "ofs_x": int(g["ofs_x"]),
            "ofs_y": int(g["ofs_y"]),
        })
    return total_px, breakdown


def _collect_fallbacks(strike_data: dict, artifacts: dict, prefer_csv: bool) -> List[dict]:
    fallbacks: List[dict] = []
    sz = strike_data.get("size_px") or 14
    for cand in (f"humid1_icon_fa7_solid_{sz}", "humid1_icon_fa7_solid_14", "humid1_font_plex_sans_normal_14"):
        try:
            _, fb = load_strike(cand, artifacts, prefer_csv=prefer_csv)
            fallbacks.append(fb)
        except KeyError:
            pass
    return fallbacks


def measure_string_budget(
    strike: str,
    text: str,
    right_text: Optional[str] = None,
    right_strike: Optional[str] = None,
    hw_scheme: str = "esp32s3-N8R8-hw_scheme.json",
    min_gap: int = 8,
    workspace_dir: Optional[str | Path] = None,
    vault_path: Optional[str | Path] = None,
    metrics_dir: Optional[str | Path] = None,
    prefer_csv: bool = False,
) -> dict:
    """Measure pixel width and screen-margin clearance for a left string or left+right telemetry row."""
    artifacts = discover_artifacts(workspace_dir, vault_path=vault_path, metrics_dir=metrics_dir)
    resolved_left, left_st = load_strike(strike, artifacts, prefer_csv=prefer_csv)
    left_fbs = _collect_fallbacks(left_st, artifacts, prefer_csv=prefer_csv)
    left_w, left_bd = measure_string_exact(text, left_st, left_fbs)

    right_w = 0
    right_bd: List[dict] = []
    r_strike_name = right_strike or resolved_left
    if right_text:
        r_strike_name, right_st = load_strike(r_strike_name, artifacts, prefer_csv=prefer_csv)
        right_fbs = _collect_fallbacks(right_st, artifacts, prefer_csv=prefer_csv)
        right_w, right_bd = measure_string_exact(right_text, right_st, right_fbs)

    screen_w, safe_m = _resolve_hw_display(hw_scheme, artifacts)
    usable_w = screen_w - (2 * safe_m)
    combined_w = left_w + right_w
    clearance_px = usable_w - combined_w
    needed_gap = min_gap if right_text else 0
    fits = clearance_px >= needed_gap

    return {
        "strike": resolved_left,
        "source": left_st["source"],
        "csv_path": left_st.get("csv_path"),
        "line_height_px": left_st.get("line_height"),
        "base_line_px": left_st.get("base_line"),
        "text": text,
        "text_width_px": left_w,
        "right_text": right_text,
        "right_strike": r_strike_name if right_text else None,
        "right_width_px": right_w,
        "combined_width_px": combined_w,
        "screen_width_px": screen_w,
        "safe_margin_px": safe_m,
        "usable_budget_px": usable_w,
        "clearance_px": clearance_px,
        "fits_budget": fits,
        "status": "PASS" if fits else "OVERFLOW_OR_TIGHT",
        "glyph_breakdown": left_bd,
        "right_glyph_breakdown": right_bd,
    }


def _strip_c_comments(code: str) -> str:
    code = re.sub(r"/\*.*?\*/", " ", code, flags=re.DOTALL)
    code = re.sub(r"//[^\n]*", "", code)
    return code


def _load_header_macros(header_dirs: Sequence[Path]) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Parse font macro -> strike symbol and string-literal macro -> decoded string from generated headers."""
    font_macros: Dict[str, str] = {}
    str_macros: Dict[str, str] = dict(LVGL_SYMBOL_MAP)
    for hdir in header_dirs:
        for hname in ("humid1_fonts.h", "h1os_fonts.h", "epd_fonts.h"):
            hp = hdir / hname
            if not hp.is_file():
                continue
            for line in hp.read_text(encoding="utf-8", errors="ignore").splitlines():
                m_font = re.match(r"^\s*#define\s+([A-Z0-9_]+)\s+\(&([a-z0-9_]+)\)", line)
                if m_font:
                    font_macros.setdefault(m_font.group(1), m_font.group(2))
                    continue
                m_str = re.match(r'^\s*#define\s+([A-Z0-9_]+)\s+"([^"]*)"', line)
                if m_str:
                    str_macros.setdefault(m_str.group(1), _decode_c_string_literal(m_str.group(2)))
    return font_macros, str_macros


def _decode_c_string_literal(raw: str) -> str:
    """Decode C escapes including raw `\\xHH` multi-byte UTF-8 sequences into Unicode text."""
    out = bytearray()
    i = 0
    n = len(raw)
    while i < n:
        ch = raw[i]
        if ch != "\\" or i + 1 >= n:
            out.extend(ch.encode("utf-8"))
            i += 1
            continue
        nxt = raw[i + 1]
        if nxt == "x":
            m = re.match(r"([0-9A-Fa-f]{1,2})", raw[i + 2:])
            if m:
                out.append(int(m.group(1), 16))
                i += 2 + len(m.group(1))
                continue
        elif nxt == "n":
            out.extend(b"\n")
            i += 2
            continue
        elif nxt == "t":
            out.extend(b"\t")
            i += 2
            continue
        elif nxt in ('"', "\\", "'"):
            out.extend(nxt.encode("utf-8"))
            i += 2
            continue
        elif nxt in ("u", "U"):
            digits = 4 if nxt == "u" else 8
            hex_part = raw[i + 2 : i + 2 + digits]
            if len(hex_part) == digits and re.fullmatch(r"[0-9A-Fa-f]+", hex_part):
                out.extend(chr(int(hex_part, 16)).encode("utf-8"))
                i += 2 + digits
                continue
        out.extend(nxt.encode("utf-8"))
        i += 2
    return codecs.decode(bytes(out), "utf-8", errors="replace")


def _simulate_printf_worst_case(fmt: str) -> str:
    s = fmt.replace("%%", "\x00PCT\x00")
    s = re.sub(r"%\+?0?\d*\.0f", lambda m: "+100" if "+" in m.group(0) else "100", s)
    s = re.sub(r"%\+?0?\d*\.1f", lambda m: "+72.5" if "+" in m.group(0) else "72.5", s)
    s = re.sub(r"%\+?0?\d*\.2f", lambda m: "+4.12" if "+" in m.group(0) else "4.12", s)
    s = re.sub(r"%\+?0?\d*\.\d+f", "72.50", s)
    s = re.sub(r"%0?\d*[l]*[du]", lambda m: "00" if "02" in m.group(0) else "625", s)
    s = re.sub(r"%0?\d*[l]*[xX]", "FF", s)
    s = s.replace("%s", "CHARGED").replace("%c", "C")
    return s.replace("\x00PCT\x00", "%")


def audit_screen_strings(
    workspace_dir: Optional[str | Path] = None,
    screen_dir: Optional[str | Path] = None,
    default_strike: str = "humid1_font_plex_sans_normal_14",
    hw_scheme: str = "esp32s3-N8R8-hw_scheme.json",
    vault_path: Optional[str | Path] = None,
    metrics_dir: Optional[str | Path] = None,
) -> dict:
    """
    Scan C/C++ UI screen files for `lv_label_set_text[_fmt]` calls, resolve widget font bindings
    and LVGL/UTF-8 symbol macros, and check every line against `usable_budget_px` (`188 px`).
    """
    artifacts = discover_artifacts(workspace_dir, vault_path=vault_path, metrics_dir=metrics_dir)
    ws = artifacts["workspace_root"]

    resolved_sdir: Optional[Path] = None
    if screen_dir:
        cand = Path(screen_dir)
        resolved_sdir = cand if cand.is_absolute() else (ws / cand)
    else:
        for cand in (
            ws / "examples" / "H1OS" / "main" / "screens",
            ws / "firmware" / "main" / "screens",
            ws / "main" / "screens",
        ):
            if cand.is_dir():
                resolved_sdir = cand
                break

    if resolved_sdir is None or not resolved_sdir.is_dir():
        raise FileNotFoundError(f"UI screen directory not found under workspace '{ws}'. Pass screen_dir explicitly.")

    c_files = sorted(list(resolved_sdir.glob("*.c")) + list(resolved_sdir.glob("*.cpp")))
    if not c_files:
        raise FileNotFoundError(f"No C/C++ screen source files found in '{resolved_sdir}'.")

    font_macros, str_macros = _load_header_macros(artifacts["header_dirs"])
    resolved_def_strike, def_st = load_strike(default_strike, artifacts)
    def_fbs = _collect_fallbacks(def_st, artifacts, prefer_csv=False)
    strike_cache_local: Dict[str, Tuple[dict, List[dict]]] = {resolved_def_strike: (def_st, def_fbs)}

    screen_w, safe_m = _resolve_hw_display(hw_scheme, artifacts)
    usable_w = screen_w - (2 * safe_m)

    set_text_pat = re.compile(
        r"lv_label_set_text(?:_fmt)?\s*\(\s*([^,]+?)\s*,\s*((?:(?:\"(?:[^\"\\]|\\.)*\")|(?:[A-Z0-9_]+))(?:\s+(?:(?:\"(?:[^\"\\]|\\.)*\")|(?:[A-Z0-9_]+)))*)\s*[,)]",
        re.DOTALL,
    )
    font_bind_pat = re.compile(
        r"lv_obj_set_style_text_font\s*\(\s*([^,]+?)\s*,\s*([^,]+?)\s*,",
        re.DOTALL,
    )

    overflows: List[dict] = []
    checked: List[dict] = []
    total_checked = 0

    for c_file in c_files:
        clean = _strip_c_comments(c_file.read_text(encoding="utf-8", errors="ignore"))
        var_fonts: Dict[str, str] = {}
        events: List[Tuple[int, str, re.Match]] = []
        for m in font_bind_pat.finditer(clean):
            events.append((m.start(), "font", m))
        for m in set_text_pat.finditer(clean):
            events.append((m.start(), "text", m))
        events.sort(key=lambda x: x[0])

        for _, kind, m in events:
            if kind == "font":
                target_var = m.group(1).strip()
                font_expr = m.group(2).strip().lstrip("&")
                mapped_sym = font_macros.get(font_expr, font_expr)
                try:
                    if mapped_sym not in strike_cache_local:
                        r_sym, st_d = load_strike(mapped_sym, artifacts)
                        strike_cache_local[mapped_sym] = (st_d, _collect_fallbacks(st_d, artifacts, prefer_csv=False))
                        strike_cache_local[r_sym] = strike_cache_local[mapped_sym]
                    var_fonts[target_var] = mapped_sym
                except KeyError:
                    pass
                continue

            target_var = m.group(1).strip()
            expr = m.group(2).strip()
            parts: List[str] = []
            for tok_m in re.finditer(r'"((?:[^"\\]|\\.)*)"|([A-Z0-9_]+)', expr):
                if tok_m.group(1) is not None:
                    parts.append(_decode_c_string_literal(tok_m.group(1)))
                else:
                    ident = tok_m.group(2)
                    if ident in str_macros:
                        parts.append(str_macros[ident])
                    elif ident in ("PRIu32", "PRId32"):
                        parts.append("lu")
            full_raw = "".join(parts)
            if not full_raw.strip():
                continue

            sim_str = _simulate_printf_worst_case(full_raw)
            active_key = var_fonts.get(target_var, resolved_def_strike)
            st_data, st_fbs = strike_cache_local[active_key]

            for line_txt in sim_str.split("\n"):
                line_s = line_txt.strip()
                if not line_s:
                    continue
                w_px, _ = measure_string_exact(line_s, st_data, st_fbs)
                total_checked += 1
                entry = {
                    "file": c_file.name,
                    "widget": target_var,
                    "strike": active_key,
                    "line": line_s,
                    "width_px": w_px,
                    "usable_budget_px": usable_w,
                    "clearance_px": usable_w - w_px,
                    "status": "PASS" if w_px <= usable_w else "FAIL",
                }
                checked.append(entry)
                if w_px > usable_w:
                    overflows.append(entry)

    return {
        "screen_dir": str(resolved_sdir),
        "files_scanned": [f.name for f in c_files],
        "default_strike": resolved_def_strike,
        "screen_width_px": screen_w,
        "safe_margin_px": safe_m,
        "usable_budget_px": usable_w,
        "total_strings_checked": total_checked,
        "overflow_count": len(overflows),
        "status": "PASS" if not overflows else "FAIL",
        "overflows": overflows,
        "checked": checked,
    }


def search_icons(
    query: str,
    vendor: str = "all",
    limit: int = 25,
    workspace_dir: Optional[str | Path] = None,
) -> dict:
    """Search `unified_icon_names.json` across FA7, Lucide, Phosphor, Tabler, and Tabler-Filled."""
    artifacts = discover_artifacts(workspace_dir)
    uni_path: Optional[Path] = artifacts.get("unified_icon_names")
    if uni_path is None or not uni_path.is_file():
        raise FileNotFoundError("unified_icon_names.json not found in workspace or epd-font build/metadata.")

    uni = json.loads(uni_path.read_text(encoding="utf-8"))
    by_name = uni.get("by_name", {})
    q_low = query.lower().strip()

    vendors = (
        [vendor]
        if vendor != "all"
        else ["icon_fa7", "icon_lucide", "icon_phosphor", "icon_tabler", "icon_tabler_filled"]
    )
    matches = []
    for v in vendors:
        vmap = by_name.get(v, {})
        v_cnt = 0
        v_macro = "TABLER_FILLED" if v == "icon_tabler_filled" else v.split("_")[1].upper()
        for name, hex_cp in sorted(vmap.items()):
            if q_low in name.lower() or q_low == hex_cp.lower():
                cp = int(hex_cp, 16)
                macro_suffix = name.upper().replace("-", "_")
                lit = cp_to_c_utf8_escape(cp)
                matches.append({
                    "vendor": v,
                    "name": name,
                    "codepoint_hex": hex_cp,
                    "codepoint_dec": cp,
                    "c_utf8_literal": f'"{lit}"',
                    "c_define": f'#define HUMID1_ICON_{v_macro}_{macro_suffix} "{lit}"',
                })
                v_cnt += 1
                if v_cnt >= limit:
                    break

    return {
        "query": query,
        "vendor": vendor,
        "metadata_path": str(uni_path),
        "total_matches": len(matches),
        "matches": matches,
    }


def _resolve_hw_display_summary(roots: Sequence[Path], scheme_dict: dict) -> dict:
    hw_ref = str(scheme_dict.get("hardware_scheme", "esp32s3-N8R8-hw_scheme.json")).strip()
    for r in roots:
        for cand in (
            r / hw_ref,
            r / "components" / "h1os" / "tools" / "fonts" / "schemes" / hw_ref,
            r / "firmware" / "components" / "h1os" / "tools" / "fonts" / "schemes" / hw_ref,
            *sorted((r / "firmware" / "managed_components").glob(f"*h1os*/tools/fonts/schemes/{hw_ref}") if (r / "firmware" / "managed_components").is_dir() else []),
        ):
            if cand.is_file():
                hw_data = json.loads(cand.read_text(encoding="utf-8"))
                disp = dict(hw_data.get("display", {}))
                p_bytes = int(hw_data.get("partition_bytes", 3145728))
                disp["hw_scheme_id"] = hw_data.get("hw_scheme_id", hw_ref)
                disp["chip_name"] = hw_data.get("chip_name", "ESP32-S3-N8R8")
                disp["partition_bytes"] = p_bytes
                disp["partition_mb"] = round(p_bytes / (1024 * 1024), 2)
                return disp
    return {"width_px": 200, "height_px": 200, "dpi": 188.15, "hw_scheme_id": hw_ref}


def inventory_fonts(workspace_dir: Optional[str | Path] = None) -> dict:
    """Summarize active Vault strikes, CSV metric manifests, asset manifest counts, and schemes."""
    artifacts = discover_artifacts(workspace_dir)
    ws = artifacts["workspace_root"]
    ef = artifacts["epd_font_root"]
    roots = artifacts["roots"]

    manifest: dict = {}
    for r in roots:
        for mp in (
            r / "components" / "h1os" / "tools" / "fonts" / "metadata" / "asset_manifest.json",
            r / "firmware" / "components" / "h1os" / "tools" / "fonts" / "metadata" / "asset_manifest.json",
            *sorted((r / "firmware" / "managed_components").glob("*h1os*/tools/fonts/metadata/asset_manifest.json") if (r / "firmware" / "managed_components").is_dir() else []),
            r / "build" / "metadata" / "asset_manifest.json",
        ):
            if mp.is_file():
                manifest = json.loads(mp.read_text(encoding="utf-8"))
                break
        if manifest:
            break

    scheme_files: List[Path] = []
    for base in (
        ws / "components" / "h1os" / "tools" / "fonts" / "schemes",
        ws / "firmware" / "components" / "h1os" / "tools" / "fonts" / "schemes",
        *sorted((ws / "firmware" / "managed_components").glob("*h1os*/tools/fonts/schemes") if (ws / "firmware" / "managed_components").is_dir() else []),
        ef / "tools" / "fonts" / "schemes",
        ef / "scripts",
    ):
        if base.is_dir():
            scheme_files.extend(sorted(base.rglob("*.scheme.json")))
    scheme_files = _dedup_paths(scheme_files)

    schemes_summary = []
    for sp in scheme_files:
        sd = json.loads(sp.read_text(encoding="utf-8"))
        strike_cnt = sum(len(s.get("sizes", [])) for s in sd.get("strikes", []))
        rel_base = ws if ws in sp.parents else ef
        schemes_summary.append({
            "file": sp.relative_to(rel_base).as_posix(),
            "scheme_id": sd.get("scheme_id"),
            "brand": sd.get("project_brand"),
            "hardware_scheme": sd.get("hardware_scheme", "esp32s3-N8R8-hw_scheme.json"),
            "total_strikes": strike_cnt,
            "display": _resolve_hw_display_summary(roots, sd),
        })

    vault_data = _read_vault(artifacts.get("vault_path"))
    vault_strikes = vault_data.get("strikes", {})
    metrics_dir: Optional[Path] = artifacts.get("metrics_dir")
    csv_files = sorted(metrics_dir.glob("char_widths_*.csv")) if metrics_dir else []

    strike_names = sorted(set(vault_strikes.keys()) | {p.stem.replace("char_widths_", "") for p in csv_files})
    return {
        "version": TOOL_VERSION,
        "workspace_root": str(ws),
        "vault_path": str(artifacts["vault_path"]) if artifacts["vault_path"] else None,
        "metrics_dir": str(metrics_dir) if metrics_dir else None,
        "vault_strike_count": len(vault_strikes),
        "csv_strike_count": len(csv_files),
        "strikes": strike_names,
        "total_static_ttfs": manifest.get("total_ttf_files", 0),
        "catalog_counts": manifest.get("catalog_counts", {}),
        "schemes_count": len(schemes_summary),
        "schemes": schemes_summary,
    }


__all__ = [
    "TOOL_VERSION",
    "LVGL_SYMBOL_MAP",
    "discover_artifacts",
    "load_strike",
    "inspect_char",
    "measure_string_budget",
    "audit_screen_strings",
    "search_icons",
    "inventory_fonts",
]
