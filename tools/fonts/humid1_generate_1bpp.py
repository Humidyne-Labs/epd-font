#!/usr/bin/env python3
"""
humid1_generate_1bpp.py (v1.0.20)
=================================
A 1-bit EPD font generator and asset pipeline for embedded displays.
Repository : https://github.com/Humidyne-Labs/epd-font
Authors    : Humiditron (https://github.com/humiditron) & AI/LLM Development Partner
License    : MIT License

Modular 1-BPP Font & Asset Pipeline Orchestrator (v1.0.20):
  - Nine selectable resolution-reduction bilevel conversion methods (`--pipeline` / `--raster-mode`):
      1. `raw-unhinted`    : Raw Threshold without Hinting (sRGB-to-Linear Grayscale + Gamma + Threshold)
      2. `raw-hinted`      : Raw Threshold with Hinting (sRGB-to-Linear Grayscale + Gamma + Threshold)
      3. `svg-potrace`     : High-Res (10x) Hierarchical RETR_TREE Potrace B-Spline SVG + Aliased Fill
      4. `svg-potrace-jfa` : Sub-mode of `svg-potrace` (`jfa-marching`): 3D OpenCL / CPU Jump Flooding (`1+JFA`)
                             + 2x2 Marching Squares sub-pixel zero-crossing + RETR_TREE Potrace SVG
      5. `mdf`             : High-Res (12x) Median Filter + Directional Signed Distance Field
      6. `msdf`            : Multi-Channel Signed Distance Field (Chlumsky msdfgen 3-Ch RGB Corner SDF)
      7. `sdf-smoothstep`  : High-Res (16x) Euclidean SDF + L2 Jacobian Gradient Smoothstep (Valve / Boesch)
      8. `adf-biquadratic` : MERL Saffron Bi-Quadratic 9-Point Lagrange Adaptively Sampled Distance Field
      9. `otsu-adaptive`   : Otsu (1979) Nonparametric Cumulative-Moment Linear Grayscale Thresholding
      *  `all`            : Run every offered conversion method and dump per-method sheets/chars when enabled
      *  `all-debug`      : Run every offered conversion method with `sheet_debug=true` and `char_debug=true`
  - Strict `char_debug` and `sheet_debug` boolean gating (`false` disables char/sheet PNG generation)
  - Strict Target Hardware Scheme validation (`esp32s3-N8R8-hw_scheme.json` & `genaric_hw.json`, 3 MByte partition, zero hard defaults)
  - Manual Closed-Loop ASCII Patching Workflow & LVGL >= 9.6.0 Validated Fallback Font Pointers.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from humid1_ascii_patches import (
    build_patches_json_from_ascii_root,
    dump_strike_to_ascii_folder,
)
from math_backends import describe_math_backend, select_math_backend, teardown_math_backends
from opencl_dispatcher import describe_hybrid_dispatch_plan
from humid1_bilevel_pipelines import (
    CANONICAL_PIPELINES,
    compute_betti_numbers,
    measure_stem_metrics,
    normalize_pipeline_name,
    rows_to_binary_array,
)
from humid1_ft_raster import (
    GlyphStrike,
    ICON_NAME_REGISTRY,
    RANGE_UI_STR,
    format_strike_symbol,
    get_semantic_glyph_name,
    load_freetype,
    load_icon_name_registry,
    parse_unicode_range,
    rasterize_font_strike,
)
from humid1_lvgl_bdf_export import (
    copy_licenses,
    emit_lvgl_c_file,
    export_bdf_strike,
    export_metric_csvs,
    generate_headers,
    run_screen_width_audit,
    write_total_disk_size_report,
)
from humid1_runtime import (
    PROJECT_TAGLINE,
    TOOL_VERSION,
    detect_host_hardware,
    fail_gracefully,
    index_font_files_recursive,
    install_clean_signal_handlers,
    load_and_validate_hardware_scheme,
    require_valid_path,
    resolve_font_file_recursive,
    run_parallel_tasks,
)
from humid1_visual_check import (
    render_char_by_char_folder,
    render_full_font_inspection_png,
    render_master_char_icon_map_png,
    render_multi_method_comparison_sheet_png,
    render_specimen_sheet,
)

SUBFAMILY_FLOORS = {
    "sans": 10,
    "plex_sans": 10,
    "noto_sans": 10,
    "mono": 10,
    "plex_mono": 10,
    "noto_mono": 10,
    "cond": 10,
    "plex_cond": 10,
    "noto_cond": 10,
    "serif": 10,
    "plex_serif": 10,
    "noto_serif": 10,
    "math": 10,
    "plex_math": 10,
    "noto_math": 10,
    "terminus": 10,
    "unifont": 10,
    "custom": 10,
    "icon_fa7": 10,
    "icon_lucide": 10,
    "icon_phosphor": 10,
    "icon_tabler": 10,
}


def get_family_roles(normal_weight: int = 500, bold_weight: int = 800, italic_weight: int = 600) -> Dict[str, Dict[str, str]]:
    """Map semantic roles to instantiated static TTF filenames."""
    tag = {100: "Thin", 200: "ExtraLight", 300: "Light", 400: "Regular", 450: "Text", 500: "Medium", 600: "SemiBold", 700: "Bold", 800: "ExtraBold"}.get(normal_weight, "Medium")
    b_tag = {600: "SemiBold", 700: "Bold", 800: "ExtraBold"}.get(bold_weight, "ExtraBold" if normal_weight >= 500 else "Bold")
    b_ital_tag = "ExtraBoldItalic" if b_tag == "ExtraBold" else "BoldItalic"
    ital_tag = {400: "Italic", 450: "TextItalic", 500: "MediumItalic", 600: "SemiBoldItalic", 700: "BoldItalic", 800: "ExtraBoldItalic"}.get(italic_weight, "SemiBoldItalic")
    cond_ital_tag = {400: "Italic", 500: "MedItal", 600: "SemiBoldItalic", 700: "BoldItalic", 800: "ExtraBoldItalic"}.get(italic_weight, "SemiBoldItalic")
    mono_ital_tag = {400: "Italic", 500: "MediumItalic", 600: "MediumItalic", 700: "BoldItalic", 800: "ExtraBoldItalic"}.get(italic_weight, "MediumItalic")
    serif_ital_tag = {400: "Italic", 500: "MediumItalic", 600: "SemiBoldItalic", 700: "BoldItalic", 800: "ExtraBoldItalic"}.get(italic_weight, "SemiBoldItalic")

    plex_sans_map = {
        "thin": "IBMPlexSans-Thin.ttf",
        "extralight": "IBMPlexSans-ExtraLight.ttf",
        "light": "IBMPlexSans-Light.ttf",
        "normal": f"IBMPlexSans-{tag}.ttf",
        "regular": "IBMPlexSans-Regular.ttf",
        "text": "IBMPlexSans-Text.ttf",
        "medium": "IBMPlexSans-Medium.ttf",
        "semibold": "IBMPlexSans-SemiBold.ttf",
        "bold": f"IBMPlexSans-{b_tag}.ttf",
        "bold_700": "IBMPlexSans-Bold.ttf",
        "extrabold": "IBMPlexSans-ExtraBold.ttf",
        "italic": f"IBMPlexSans-{ital_tag}.ttf",
        "bold_italic": f"IBMPlexSans-{b_ital_tag}.ttf",
    }
    plex_mono_map = {
        "light": "IBMPlexMono-Light.ttf",
        "normal": f"IBMPlexMono-{tag}.ttf",
        "regular": "IBMPlexMono-Regular.ttf",
        "text": "IBMPlexMono-Text.ttf",
        "medium": "IBMPlexMono-Medium.ttf",
        "semibold": "IBMPlexMono-SemiBold.ttf",
        "bold": f"IBMPlexMono-{b_tag}.ttf",
        "bold_700": "IBMPlexMono-Bold.ttf",
        "extrabold": "IBMPlexMono-ExtraBold.ttf",
        "italic": f"IBMPlexMono-{mono_ital_tag}.ttf",
        "bold_italic": f"IBMPlexMono-{b_ital_tag}.ttf",
    }
    plex_cond_map = {
        "light": "IBMPlexSansCondensed-Light.ttf",
        "normal": f"IBMPlexSansCondensed-{tag}.ttf",
        "regular": "IBMPlexSansCondensed-Regular.ttf",
        "text": "IBMPlexSansCondensed-Text.ttf",
        "medium": "IBMPlexSansCondensed-Medium.ttf",
        "semibold": "IBMPlexSansCondensed-SemiBold.ttf",
        "bold": f"IBMPlexSansCondensed-{b_tag}.ttf",
        "bold_700": "IBMPlexSansCondensed-Bold.ttf",
        "extrabold": "IBMPlexSansCondensed-ExtraBold.ttf",
        "italic": f"IBMPlexSansCondensed-{cond_ital_tag}.ttf",
        "bold_italic": f"IBMPlexSansCondensed-{b_ital_tag}.ttf",
    }
    plex_serif_map = {
        "light": "IBMPlexSerif-Light.ttf",
        "normal": f"IBMPlexSerif-{tag}.ttf",
        "regular": "IBMPlexSerif-Regular.ttf",
        "text": "IBMPlexSerif-Text.ttf",
        "medium": "IBMPlexSerif-Medium.ttf",
        "semibold": "IBMPlexSerif-SemiBold.ttf",
        "bold": f"IBMPlexSerif-{b_tag}.ttf",
        "bold_700": "IBMPlexSerif-Bold.ttf",
        "extrabold": "IBMPlexSerif-ExtraBold.ttf",
        "italic": f"IBMPlexSerif-{serif_ital_tag}.ttf",
        "bold_italic": f"IBMPlexSerif-{b_ital_tag}.ttf",
    }
    noto_sans_map = {
        "normal": "NotoSans-Medium.ttf",
        "regular": "NotoSans-Regular.ttf",
        "medium": "NotoSans-Medium.ttf",
        "bold": "NotoSans-Black.ttf",
        "bold_700": "NotoSans-Bold.ttf",
        "extrabold": "NotoSans-ExtraBold.ttf",
        "black": "NotoSans-Black.ttf",
        "italic": "NotoSans-SemiBoldItalic.ttf",
        "medium_italic": "NotoSans-MediumItalic.ttf",
        "bold_italic": "NotoSans-SemiBoldItalic.ttf",
    }
    noto_cond_map = {
        "normal": "NotoSans-SemiCondensedMedium.ttf",
        "regular": "NotoSans-SemiCondensedMedium.ttf",
        "medium": "NotoSans-SemiCondensedMedium.ttf",
        "semibold": "NotoSans-CondensedSemiBold.ttf",
        "bold": "NotoSans-SemiCondensedBlack.ttf",
        "extrabold": "NotoSans-SemiCondensedExtraBold.ttf",
        "black": "NotoSans-SemiCondensedBlack.ttf",
        "condensed_normal": "NotoSans-CondensedSemiBold.ttf",
        "condensed_bold": "NotoSans-CondensedBlack.ttf",
        "condensed_italic": "NotoSans-CondensedSemiBoldItalic.ttf",
        "italic": "NotoSans-SemiCondensedSemiBoldItalic.ttf",
        "bold_italic": "NotoSans-SemiCondensedSemiBoldItalic.ttf",
    }
    noto_mono_map = {
        "normal": "NotoSansMono-Medium.ttf",
        "regular": "NotoSansMono-Medium.ttf",
        "medium": "NotoSansMono-Medium.ttf",
        "bold": "NotoSansMono-ExtraBold.ttf",
        "extrabold": "NotoSansMono-ExtraBold.ttf",
        "black": "NotoSansMono-Black.ttf",
        "italic": "IBMPlexMono-MediumItalic.ttf",
        "bold_italic": "IBMPlexMono-ExtraBoldItalic.ttf",
    }
    noto_serif_map = {
        "normal": "NotoSerif-Medium.ttf",
        "regular": "NotoSerif-Medium.ttf",
        "medium": "NotoSerif-Medium.ttf",
        "bold": "NotoSerif-Black.ttf",
        "black": "NotoSerif-Black.ttf",
        "italic": "NotoSerif-MediumItalic.ttf",
        "semibold_italic": "NotoSerif-SemiBoldItalic.ttf",
        "bold_italic": "NotoSerif-SemiBoldItalic.ttf",
    }
    noto_math_map = {
        "regular": "NotoSansMath-Regular.ttf",
        "normal": "NotoSansMath-Regular.ttf",
    }
    return {
        "sans": plex_sans_map,
        "plex_sans": plex_sans_map,
        "noto_sans": noto_sans_map,
        "mono": plex_mono_map,
        "plex_mono": plex_mono_map,
        "noto_mono": noto_mono_map,
        "cond": noto_cond_map,
        "noto_cond": noto_cond_map,
        "plex_cond": plex_cond_map,
        "serif": noto_serif_map,
        "noto_serif": noto_serif_map,
        "plex_serif": plex_serif_map,
        "math": noto_math_map,
        "noto_math": noto_math_map,
        "plex_math": {
            "regular": "IBMPlexMath-Regular.ttf",
            "normal": "IBMPlexMath-Regular.ttf",
        },
        "icon_fa7": {
            "solid": "FontAwesome7-Solid.ttf",
            "regular": "FontAwesome7-Regular.ttf",
            "brands": "FontAwesome7-Brands.ttf",
            "normal": "FontAwesome7-Solid.ttf",
        },
        "icon_lucide": {
            "regular": "Lucide-Regular.ttf",
            "normal": "Lucide-Regular.ttf",
        },
        "terminus": {
            "regular": "Terminus-Regular.ttf",
            "normal": "Terminus-Regular.ttf",
            "bold": "Terminus-Bold.ttf",
        },
        "unifont": {
            "regular": "Unifont-Regular.ttf",
            "normal": "Unifont-Regular.ttf",
        },
        "icon_phosphor": {
            "thin": "Phosphor-Thin.ttf",
            "light": "Phosphor-Light.ttf",
            "regular": "Phosphor-Regular.ttf",
            "normal": "Phosphor-Regular.ttf",
            "bold": "Phosphor-Bold.ttf",
            "fill": "Phosphor-Fill.ttf",
            "duotone": "Phosphor-Duotone.ttf",
        },
        "icon_tabler": {
            "thin": "Tabler-Thin200.ttf",
            "light": "Tabler-Light300.ttf",
            "regular": "Tabler-Regular.ttf",
            "normal": "Tabler-Regular.ttf",
            "filled": "Tabler-Filled.ttf",
        },
    }


DEFAULT_ICON_FALLBACK_RANGES = {
    "icon_fa7": "0xF00C,0xF00D,0xF013,0xF015,0xF017,0xF021,0xF023,0xF043,0xF058,0xF071,0xF0E7,0xF1EB,0xF240-0xF244,0xF2C9,0xF2DB",
    "icon_lucide": "0xE01D,0xE053,0xE054,0xE070,0xE0B4,0xE17C,0xE1A1,0xE1AA,0xE1D8,0xE1FB",
    "icon_phosphor": "0xE002,0xE026,0xE06A,0xE094,0xE13E,0xE14E,0xE1F4,0xE208,0xE270,0xE482,0xE4EA,0xE60C",
    "icon_tabler": "0xEA02,0xEA08,0xEA30,0xEA31,0xEA32,0xEA34,0xEA38,0xEA52,0xEB3D,0xEB52",
    "icon_tabler_filled": "0xEE80,0xF357,0xF667-0xF69F,0xF6A0-0xF6BF",
}


def resolve_charset_spec_to_range_str(
    cs_entry: dict,
    default_vendor: str = "",
    style: str = "",
    full_icon_catalog: bool = False,
) -> str:
    parts: List[str] = []
    if "ranges" in cs_entry and cs_entry["ranges"]:
        parts.append(str(cs_entry["ranges"]).strip())

    vendor = cs_entry.get("vendor", default_vendor)
    if vendor == "icon_tabler" and style == "filled":
        vendor = "icon_tabler_filled"
    by_name_map = ICON_NAME_REGISTRY.get("by_name", {}).get(vendor, {})
    if not by_name_map and vendor in ICON_NAME_REGISTRY and isinstance(ICON_NAME_REGISTRY[vendor], dict):
        by_name_map = {v: k for k, v in ICON_NAME_REGISTRY[vendor].items()}

    if cs_entry.get("scope", "").lower() == "all" and by_name_map:
        all_hex = sorted(set(by_name_map.values()), key=lambda x: int(str(x), 16))
        if not full_icon_catalog and len(all_hex) > 128:
            # Select 128 evenly spaced representative icons across the full PUA range unless --full-icon-catalog is set
            step = max(1, len(all_hex) // 128)
            all_hex = all_hex[::step][:128]
        parts.extend(all_hex)

    if "icons" in cs_entry and isinstance(cs_entry["icons"], list):
        for icon_name in cs_entry["icons"]:
            iname = str(icon_name).strip()
            if iname.startswith("0x") or iname.isdigit():
                parts.append(iname)
            elif iname in by_name_map:
                parts.append(by_name_map[iname])
            else:
                iname_low = iname.lower()
                for k, hex_v in by_name_map.items():
                    if k.lower() == iname_low:
                        parts.append(hex_v)
                        break

    return ",".join(p for p in parts if p)


def load_plan_from_scheme_json(
    scheme_path: Path,
    full_icon_catalog: bool = False,
) -> Tuple[dict, List[Tuple[str, str, List[int], str, bool, Optional[str], str]]]:
    scheme = json.loads(scheme_path.read_text(encoding="utf-8"))
    char_sets = scheme.get("character_sets", {})
    plan_out = []
    for entry in scheme.get("strikes", []):
        fam = entry["family"]
        style = entry.get("style", "normal")
        if "ttf_file" in entry and entry["ttf_file"]:
            style = f"custom:{entry['ttf_file']}"
        sizes = list(entry["sizes"])
        cset_names = entry.get("char_sets", [] if fam.startswith("icon_") else ["ascii_printable"])
        iset_names = entry.get("icon_sets", [])

        u_ranges = []
        for cn in cset_names:
            if cn in char_sets:
                r_str = resolve_charset_spec_to_range_str(
                    char_sets[cn],
                    default_vendor=fam,
                    style=style,
                    full_icon_catalog=full_icon_catalog,
                )
                if r_str:
                    u_ranges.append(r_str)
        if u_ranges:
            combined_u_range = ",".join(u_ranges)
        elif fam == "icon_tabler" and style == "filled":
            combined_u_range = DEFAULT_ICON_FALLBACK_RANGES["icon_tabler_filled"]
        elif fam.startswith("icon_"):
            combined_u_range = DEFAULT_ICON_FALLBACK_RANGES.get(fam, "0xE000-0xE03F")
        else:
            combined_u_range = RANGE_UI_STR

        fa_ranges = []
        for iname in iset_names:
            if iname in char_sets:
                r_str = resolve_charset_spec_to_range_str(
                    char_sets[iname],
                    default_vendor="icon_fa7",
                    full_icon_catalog=full_icon_catalog,
                )
                if r_str:
                    fa_ranges.append(r_str)
        combined_fa_range = ",".join(fa_ranges)
        inc_fa = len(fa_ranges) > 0

        fb_pat = entry.get("fallback", None)
        plan_out.append((fam, style, sizes, combined_u_range, inc_fa, fb_pat, combined_fa_range))
    return scheme, plan_out


def export_strike_vault(vault_path: Path, vault_data: dict) -> int:
    vault_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(vault_data, separators=(",", ":"))
    if vault_path.name.endswith(".gz"):
        with gzip.open(vault_path, "wt", encoding="utf-8", compresslevel=9) as f:
            f.write(payload)
    else:
        vault_path.write_text(payload, encoding="utf-8")
    return vault_path.stat().st_size


def build_arg_parser() -> argparse.ArgumentParser:
    epilog_text = """
Nine Bilevel Resolution-Reduction Pipelines (--pipeline / --raster-mode):
-------------------------------------------------------------------------
  1. raw-unhinted    : Direct FreeType unhinted rendering -> sRGB-to-Linear Gray -> gamma -> threshold
  2. raw-hinted      : Grid-fitted hinted FreeType rendering -> sRGB-to-Linear Gray -> gamma -> threshold
  3. svg-potrace     : High-res (10x) linear gray -> threshold -> RETR_TREE Potrace SVG -> aliased fill
  4. svg-potrace-jfa : Sub-mode of svg-potrace (jfa-marching): 3D 1+JFA + 2x2 Marching Squares + Potrace SVG
  5. mdf             : High-res (12x) median filter + directional Signed Distance Field -> threshold
  6. msdf            : Multi-Channel Signed Distance Field (Chlumsky msdfgen 3-Ch RGB corner SDF)
  7. sdf-smoothstep  : High-res (16x) Euclidean SDF + L2 Jacobian gradient smoothstep (Valve / Boesch)
  8. adf-biquadratic : MERL Saffron bi-quadratic 9-point Lagrange Adaptively Sampled Distance Field
  9. otsu-adaptive   : Otsu (1979) cumulative-moment between-class variance threshold on linear gray
  *  all            : Run every offered conversion method (respects char_debug & sheet_debug)
  *  all-debug      : Run every offered conversion method and force dump of all method sheets & chars
"""
    parser = argparse.ArgumentParser(
        prog="humid1_generate_1bpp.py",
        description=(
            f"Humidyne Labs / Humiditron `epd-font` v{TOOL_VERSION} — {PROJECT_TAGLINE}.\n"
            "Supports workflows: 'gen-assets', 'patch', 'check', 'build', 'audit', and 'all'."
        ),
        epilog=epilog_text,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "-w", "--workflow",
        choices=["gen-assets", "patch", "check", "build", "audit", "all"],
        required=True,
        help=(
            "Select workflow stage (required):\n"
            "  gen-assets : Build static .ttf files & metadata JSONs from raw assets\n"
            "  patch      : Dump (--dump) or compile (--apply) Full-Canvas 1:1 ASCII .txt glyph patches\n"
            "  check      : Render Page Check PNGs, Char-by-Char Blueprint PNGs & 200x200 screen audit\n"
            "  build      : Emit LVGL >= 9.6.0 1-bpp .c/.h files, BDFs, CSV metrics & Strike Vault\n"
            "  audit      : Ingest audit scheme, evaluate all 8 pipelines, and generate all assets\n"
            "  all        : Run gen-assets -> patch -> build -> check in sequence"
        ),
    )
    parser.add_argument(
        "-S", "--scheme",
        type=str,
        default=None,
        help="Path to declarative JSON scheme file (required for build/check/audit/dump workflows)",
    )
    parser.add_argument(
        "-H", "--hw-scheme",
        type=str,
        default=None,
        help="Path to target hardware scheme JSON (e.g. esp32s3-N8R8-hw_scheme.json or genaric_hw.json)",
    )
    parser.add_argument(
        "-s", "--src-dir",
        type=str,
        default=None,
        help="Input directory containing static .ttf/.otf/.ttc/.bdf assets (searched recursively)",
    )
    parser.add_argument(
        "-o", "--out-dir", "--build-dir",
        dest="out_dir",
        type=str,
        default=None,
        help="Output build directory for generated files (e.g. build/h1os)",
    )
    parser.add_argument(
        "-d", "--dist-dir",
        type=str,
        default=None,
        help="Output distribution directory for Strike Vault & portable zip bundle (e.g. dist/h1os_distro)",
    )
    parser.add_argument(
        "-p", "--patches",
        type=str,
        default=None,
        help="Path to JSON manual patch manifest (e.g. font_icon_epd_patches.json)",
    )
    parser.add_argument(
        "-a", "--ascii-dir",
        type=str,
        default=None,
        help="Directory for Full-Canvas 1:1 Spaced ASCII .txt glyph folders (e.g. build/h1os/ascii_patches)",
    )
    parser.add_argument(
        "--pipeline", "--raster-mode",
        dest="pipeline",
        choices=[
            "raw-unhinted", "raw-hinted", "svg-potrace", "svg-potrace-jfa", "jfa-marching", "mdf",
            "msdf", "sdf-smoothstep", "adf-biquadratic", "otsu-adaptive",
            "all", "all-debug",
            "autohint-mono", "bytecode-mono", "gray-threshold", "dynamic-threshold",
        ],
        default=None,
        help="Select bilevel conversion pipeline: raw-unhinted, raw-hinted, svg-potrace, svg-potrace-jfa (or jfa-marching), mdf, msdf, sdf-smoothstep, adf-biquadratic, otsu-adaptive, all, or all-debug",
    )
    parser.add_argument(
        "--potrace-submode",
        choices=["potrace", "jfa-marching"],
        default=None,
        help="Optional sub-mode when using svg-potrace: 'potrace' (standard RETR_TREE B-Spline) or 'jfa-marching' (Jump Flooding Algorithm 1+JFA + 2x2 Marching Squares sub-pixel zero-crossing)",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=None,
        help="Binarization threshold override in 1..254 (default: 128 or from scheme JSON)",
    )
    parser.add_argument(
        "--gamma",
        type=float,
        default=None,
        help="Linear grayscale gamma/contrast power factor (default: 1.0 or from scheme JSON; e.g. 1.1 for Saffron body contrast)",
    )
    parser.add_argument(
        "--char-debug",
        dest="char_debug",
        action="store_true",
        default=None,
        help="Enable Char-by-Char Blueprint PNG generation (`inspect_chars/`)",
    )
    parser.add_argument(
        "--no-char-debug",
        dest="char_debug",
        action="store_false",
        help="Disable Char-by-Char Blueprint PNG generation (`char_debug = false`)",
    )
    parser.add_argument(
        "--sheet-debug",
        dest="sheet_debug",
        action="store_true",
        default=None,
        help="Enable Page Check Sheet PNG generation (`inspect_pages/`)",
    )
    parser.add_argument(
        "--no-sheet-debug",
        dest="sheet_debug",
        action="store_false",
        help="Disable Page Check Sheet PNG generation (`sheet_debug = false`)",
    )
    parser.add_argument(
        "--full-icon-catalog",
        action="store_true",
        help="When a scheme uses `scope: all`, rasterize all 18,578 PUA icons instead of the 128-icon audit sample",
    )
    parser.add_argument(
        "--dump",
        action="store_true",
        help="In '--workflow patch', dump strikes to Full-Canvas 1:1 Spaced ASCII .txt folders",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="In '--workflow patch', compile modified ASCII .txt files into --patches JSON",
    )
    parser.add_argument(
        "--trouble-only",
        action="store_true",
        help="When dumping ASCII .txt files, export only the 15 complex characters per strike",
    )
    parser.add_argument(
        "--unicode-preview",
        action="store_true",
        help="Opt-in flag to include the UTF-8 Unicode 1:1 block preview header in dumped ASCII .txt files",
    )
    parser.add_argument(
        "--inspect-chars-filter",
        choices=["all", "trouble", "patched", "ascii", "none"],
        default="all",
        help="Which characters to render in <out-dir>/inspect_chars/ when char_debug=true (default: all)",
    )
    parser.add_argument(
        "--sizes",
        type=int,
        nargs="+",
        default=None,
        help="Optional pixel sizes filter (e.g. --sizes 10 12 14 16 18 20 24 32 40)",
    )
    parser.add_argument(
        "--families",
        type=str,
        nargs="+",
        default=None,
        help="Optional families filter (e.g. --families sans mono icon_lucide)",
    )
    parser.add_argument(
        "--normal-weight",
        type=int,
        choices=[100, 200, 300, 400, 450, 500, 600, 700],
        default=500,
        help="OpenType weight for 'normal' slot (default: 500 Medium)",
    )
    parser.add_argument(
        "--bold-weight",
        type=int,
        choices=[600, 700, 800],
        default=800,
        help="OpenType weight for 'bold' slot (default: 800 ExtraBold)",
    )
    parser.add_argument(
        "--italic-weight",
        type=int,
        choices=[400, 450, 500, 600, 700, 800],
        default=600,
        help="OpenType weight for 'italic' slot (default: 600 SemiBoldItalic)",
    )
    parser.add_argument(
        "--audit-screens",
        action="store_true",
        help="Run automated horizontal screen width budget audit using target display geometry",
    )
    parser.add_argument(
        "--dpi",
        type=float,
        default=None,
        help="Target display pixel density override in DPI",
    )
    parser.add_argument(
        "--accel",
        choices=["auto", "opencl", "opencl-cpu", "hybrid", "umat", "cpu"],
        default=None,
        help="Hardware math acceleration backend (default: auto -> Hybrid OpenCL GPU+CPU / UMat / CPU)",
    )
    parser.add_argument(
        "--shared-ram-mb",
        type=int,
        default=None,
        help="Host/GPU Shared RAM pool budget in MB for CL_MEM_ALLOC_HOST_PTR zero-copy staging (default: auto from 15.7GB shared RAM)",
    )
    parser.add_argument(
        "--screen-width",
        type=int,
        default=None,
        help="Target display horizontal width override in pixels",
    )
    parser.add_argument(
        "--screen-height",
        type=int,
        default=None,
        help="Target display vertical height override in pixels",
    )
    parser.add_argument(
        "--safe-margin",
        type=int,
        default=None,
        help="Horizontal safe margin override in pixels on each side",
    )
    parser.add_argument(
        "--keep-noop-kern",
        action="store_true",
        help="Retain sub-pixel GPOS kerning pairs that round to 0px at target strike size",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose terminal debug output per strike and pipeline stage",
    )
    parser.add_argument(
        "--debug-stages",
        action="store_true",
        help="Emit intermediate stage debug images (10x linear gray, 10x binary, Potrace .svg, MSDF RGB, 8-pipeline grid) to <out-dir>/debug_stages/",
    )
    parser.add_argument(
        "-j", "--jobs",
        type=int,
        default=None,
        help="Number of parallel CPU worker processes (default: auto-detected from host CPU/RAM)",
    )
    return parser


_WORKER_FT = None
_WORKER_FT_LIB = None
_WORKER_FONT_DIR = None


def _compute_strike_method_stats(glyphs: Sequence[GlyphStrike]) -> dict:
    ink_sum = 0
    stems_w = []
    ge2_sum = 0.0
    cnt_ok = 0
    cnt_tot = 0
    for pg in glyphs:
        if not pg.rows:
            continue
        arr = rows_to_binary_array(pg.rows)
        ink_sum += int(arr.sum())
        _, _, mw, gr = measure_stem_metrics(arr)
        if mw > 0:
            stems_w.append(mw)
            ge2_sum += gr
        ch = chr(pg.codepoint) if 0x20 <= pg.codepoint <= 0x7E else ""
        if ch in ("0", "4", "6", "8", "9", "A", "B", "D", "O", "P", "Q", "R", "a", "b", "d", "e", "g", "o", "p", "q"):
            cnt_tot += 1
            _, b1 = compute_betti_numbers(arr)
            exp_b1 = 2 if ch in ("8", "B") else 1
            if b1 >= exp_b1:
                cnt_ok += 1
    n_st = max(1, len(stems_w))
    return {
        "ink_px": ink_sum,
        "mean_stem_px": round(sum(stems_w) / n_st, 2),
        "stem_2px_pct": round((ge2_sum / n_st) * 100.0, 1),
        "counter_pct": round((cnt_ok / max(1, cnt_tot)) * 100.0, 1) if cnt_tot > 0 else 100.0,
    }


def _execute_strike_worker_task(task: dict) -> dict:
    """ProcessPoolExecutor worker that rasterizes and emits all files for a single strike."""
    global _WORKER_FT, _WORKER_FT_LIB, _WORKER_FONT_DIR
    font_dir = Path(task["font_dir"])
    if _WORKER_FT is None:
        _WORKER_FT, _WORKER_FT_LIB = load_freetype()
    if _WORKER_FONT_DIR != task["font_dir"]:
        load_icon_name_registry(font_dir)
        _WORKER_FONT_DIR = task["font_dir"]

    sym_name = task["sym_name"]
    family = task["family"]
    role = task["role"]
    sz = task["sz"]
    ttf_path = Path(task["ttf_path"])
    effective_raster_m = task["effective_raster_m"]
    gamma = float(task.get("gamma", 1.0))
    strike_ascii_dir = Path(task["strike_ascii_dir"]) if task["strike_ascii_dir"] else None
    debug_stages_dir = Path(task["debug_stages_dir"]) if task.get("debug_stages_dir") else None
    run_all_methods = bool(task.get("run_all_methods", False))
    sheet_debug = bool(task.get("sheet_debug", False))
    char_debug = bool(task.get("char_debug", False))

    glyphs, line_h, base_l, upos, uthk, kern_pairs = rasterize_font_strike(
        ft=_WORKER_FT,
        ft_lib=_WORKER_FT_LIB,
        font_path=ttf_path,
        size_px=sz,
        codepoints=task["codepoints"],
        raster_mode=effective_raster_m,
        threshold=task["threshold"],
        gamma=gamma,
        fa_path=None,
        fa_codepoints=None,
        patch_dict=task["strike_patches"],
        ascii_override_dir=strike_ascii_dir,
        enable_kerning=task["enable_kern"],
        prune_noop_kern=task["prune_noop_kern"],
        debug_stages_dir=debug_stages_dir,
        strike_symbol=sym_name,
        family=family,
        verbose=task.get("verbose", False),
    )

    orig_sigs_map: Dict[int, str] = {}
    for g0 in glyphs:
        m_lines = g0.rows if (g0.box_w > 0 and g0.box_h > 0 and g0.rows) else []
        orig_sigs_map[g0.codepoint] = f"{g0.box_w},{g0.box_h},{g0.ofs_x},{g0.ofs_y}|" + ("/".join(m_lines) if m_lines else ".")

    if task["do_build_c"] and task["c_out_dir"]:
        out_file = Path(task["c_out_dir"]) / f"{sym_name}.c"
        rom_b = emit_lvgl_c_file(
            out_file=out_file,
            font_symbol_name=sym_name,
            size_px=sz,
            family=family,
            role=role,
            raster_mode=effective_raster_m,
            glyphs=glyphs,
            line_height=line_h,
            base_line=base_l,
            underline_pos=upos,
            underline_thick=uthk,
            kern_pairs=kern_pairs,
            fallback_symbol=task["fb_sym"],
        )
    else:
        rom_b = sum(len(g.pack_1bpp_bytes()) for g in glyphs) + (len(glyphs) + 1) * 8 + len(kern_pairs) * 3 + 120

    ascii_dumped = 0
    if task["dump_ascii_root"]:
        s_dump_dir = Path(task["dump_ascii_root"]) / sym_name
        ascii_dumped = dump_strike_to_ascii_folder(
            s_dump_dir,
            sym_name,
            glyphs,
            size_px=sz,
            line_height=line_h,
            base_line=base_l,
            trouble_only=task["trouble_only"],
            unicode_preview=task["unicode_preview"],
            family=family,
            orig_signatures=orig_sigs_map,
        )

    png_pages = 0
    if sheet_debug and task["inspect_png_root"]:
        png_file = Path(task["inspect_png_root"]) / f"{sym_name}.png"
        png_pages += render_full_font_inspection_png(
            out_png=png_file,
            font_symbol_name=sym_name,
            family=family,
            role=role,
            size_px=sz,
            raster_mode=effective_raster_m,
            line_height=line_h,
            base_line=base_l,
            glyphs=glyphs,
            rom_bytes=rom_b,
            static_dir=font_dir,
        )

    char_pngs = 0
    if char_debug and task["inspect_chars_root"] and task["inspect_chars_filter"] != "none":
        s_char_dir = Path(task["inspect_chars_root"]) / sym_name
        char_pngs += render_char_by_char_folder(
            strike_char_dir=s_char_dir,
            font_symbol_name=sym_name,
            family=family,
            role=role,
            size_px=sz,
            raster_mode=effective_raster_m,
            line_height=line_h,
            base_line=base_l,
            glyphs=glyphs,
            char_filter=task["inspect_chars_filter"],
            static_dir=font_dir,
        )

    # Multi-method execution when `pipeline="all"` / `"all-debug"` or `--workflow audit`
    all_method_stats: Dict[str, dict] = {}
    if run_all_methods and family not in ("terminus", "unifont"):
        method_strikes_for_sheet: Dict[str, Tuple[Sequence[GlyphStrike], int, int]] = {}
        eval_cps = task["codepoints"]
        for p_method in CANONICAL_PIPELINES:
            if p_method == effective_raster_m:
                p_glyphs, p_lh, p_bl = glyphs, line_h, base_l
            else:
                p_glyphs, p_lh, p_bl, _, _, _ = rasterize_font_strike(
                    ft=_WORKER_FT,
                    ft_lib=_WORKER_FT_LIB,
                    font_path=ttf_path,
                    size_px=sz,
                    codepoints=eval_cps,
                    raster_mode=p_method,
                    threshold=task["threshold"],
                    gamma=gamma,
                    patch_dict=task["strike_patches"],
                    ascii_override_dir=strike_ascii_dir,
                    enable_kerning=False,
                )
            all_method_stats[p_method] = _compute_strike_method_stats(p_glyphs)
            method_strikes_for_sheet[p_method] = (p_glyphs, p_lh, p_bl)

            # When `pipeline="all"` (or `all-debug`) and `sheet_debug=true`, dump EACH method's sheet
            if task.get("dump_each_method_outputs") and sheet_debug and task["inspect_png_root"]:
                m_png_dir = Path(task["inspect_png_root"]) / p_method
                m_png_file = m_png_dir / f"{sym_name}.png"
                png_pages += render_full_font_inspection_png(
                    out_png=m_png_file,
                    font_symbol_name=f"{sym_name} [{p_method}]",
                    family=family,
                    role=role,
                    size_px=sz,
                    raster_mode=p_method,
                    line_height=p_lh,
                    base_line=p_bl,
                    glyphs=p_glyphs,
                    rom_bytes=rom_b,
                    static_dir=font_dir,
                )

            # When `pipeline="all"` (or `all-debug`) and `char_debug=true`, dump EACH method's char cards
            if task.get("dump_each_method_outputs") and char_debug and task["inspect_chars_root"] and task["inspect_chars_filter"] != "none":
                m_char_dir = Path(task["inspect_chars_root"]) / p_method / sym_name
                char_pngs += render_char_by_char_folder(
                    strike_char_dir=m_char_dir,
                    font_symbol_name=f"{sym_name} [{p_method}]",
                    family=family,
                    role=role,
                    size_px=sz,
                    raster_mode=p_method,
                    line_height=p_lh,
                    base_line=p_bl,
                    glyphs=p_glyphs,
                    char_filter=task["inspect_chars_filter"],
                    static_dir=font_dir,
                )

        if task.get("dump_each_method_outputs") and sheet_debug and task["inspect_png_root"]:
            cmp_png = Path(task["inspect_png_root"]) / "compare_methods" / f"{sym_name}_all_methods.png"
            render_multi_method_comparison_sheet_png(
                out_png=cmp_png,
                font_symbol_name=sym_name,
                family=family,
                role=role,
                size_px=sz,
                threshold=task["threshold"],
                gamma=gamma,
                method_strikes=method_strikes_for_sheet,
                method_stats=all_method_stats,
                static_dir=font_dir,
            )
            png_pages += 1

    if task["bdf_out_dir"]:
        bdf_path = Path(task["bdf_out_dir"]) / f"{sym_name}.bdf"
        export_bdf_strike(bdf_path, sym_name, sz, 188.15, line_h, base_l, glyphs)

    if task["metrics_out_dir"]:
        export_metric_csvs(Path(task["metrics_out_dir"]), sym_name, glyphs, kern_pairs)

    vault_entry = {
        "family": family,
        "style": role,
        "size_px": sz,
        "source_ttf": task["ttf_name"],
        "pipeline": effective_raster_m,
        "threshold": task["threshold"],
        "gamma": gamma,
        "line_height": line_h,
        "base_line": base_l,
        "glyphs": [
            {
                "cp": g.codepoint,
                "name": get_semantic_glyph_name(g.codepoint, family),
                "gid": g.glyph_id,
                "adv_w_fp4": g.adv_w_fp4,
                "box_w": g.box_w,
                "box_h": g.box_h,
                "ofs_x": g.ofs_x,
                "ofs_y": g.ofs_y,
                "rows": g.rows,
                "patched": g.patched,
            }
            for g in glyphs
            if g.codepoint > 0
        ],
        "kern_pairs": [[l_gid, r_gid, kv] for (l_gid, r_gid, _, _, kv) in kern_pairs],
    }

    c_disk_b = 0
    if task["do_build_c"] and task["c_out_dir"]:
        cf = Path(task["c_out_dir"]) / f"{sym_name}.c"
        if cf.is_file():
            c_disk_b = cf.stat().st_size

    pt96 = sz * 72.0 / 96.0
    patched_cnt = sum(1 for g in glyphs if g.patched)
    patch_tag = f" [+{patched_cnt} patches]" if patched_cnt else ""
    fb_tag = f" fb->{task['fb_sym']}" if (task.get("verbose") and task.get("fb_sym")) else ""
    mode_disp = "all(8-methods)" if task.get("dump_each_method_outputs") else effective_raster_m
    log_line = (
        f"    [+] {sym_name:<36} | {len(glyphs):>4} glyphs | {len(kern_pairs):>4} kern | "
        f"em={sz:>2}px ({pt96:>4.1f}pt) lh={line_h:>2}px | {mode_disp:<14} (T={task['threshold']}, g={gamma:.2f}) | ~{rom_b:>7,} B ({rom_b/1024:.2f} KB){patch_tag}{fb_tag}"
    )
    return {
        "sym_name": sym_name,
        "c_disk_b": c_disk_b,
        "family": family,
        "role": role,
        "sz": sz,
        "rom_b": rom_b,
        "glyphs": glyphs,
        "line_h": line_h,
        "base_l": base_l,
        "kern_pairs": kern_pairs,
        "ascii_dumped": ascii_dumped,
        "png_pages": png_pages,
        "char_pngs": char_pngs,
        "vault_entry": vault_entry,
        "all_method_stats": all_method_stats,
        "log_line": log_line,
    }


def main() -> None:
    install_clean_signal_handlers()
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent if script_dir.name == "fonts" else script_dir.parent
    parser = build_arg_parser()

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        fail_gracefully(
            "No CLI arguments were provided.",
            "Pass `--workflow <stage>` and `--scheme <scheme.json>` (or `--src-dir` / `--out-dir`).",
        )

    args = parser.parse_args()
    hw_info = detect_host_hardware(args.jobs)
    if args.verbose:
        print(
            f"[*] Host Hardware Detected: OS={hw_info.os_name}, CPU={hw_info.cpu_cores} cores, "
            f"Avail RAM={hw_info.available_ram_mb} MB / {hw_info.total_ram_mb} MB, "
            f"Backend={hw_info.gpu_backend}, Active Workers={hw_info.recommended_workers}"
        )

    # 1. Handle `patch --apply` when compiling ASCII edits into patch JSON
    do_dump_ascii = args.dump or (args.workflow in ("all", "audit"))
    do_apply_ascii = args.apply or (args.workflow == "patch" and not args.dump)

    if do_apply_ascii and args.workflow == "patch" and not do_dump_ascii:
        apply_root = require_valid_path(args.ascii_dir, "--ascii-dir", must_exist=True, expect_dir=True)
        if not args.patches:
            fail_gracefully("Missing `--patches <font_icon_epd_patches.json>` path for `--workflow patch --apply`.")
        patches_path = Path(args.patches).expanduser().resolve()
        cnt = build_patches_json_from_ascii_root(apply_root, patches_path, only_modified=True)
        print(f"[+] Compiled {cnt} modified ASCII glyph patch(es) from {apply_root} -> {patches_path}")
        return

    # 2. Resolve and validate `--src-dir` and `--out-dir`
    if args.workflow == "gen-assets":
        src_assets = require_valid_path(args.src_dir, "--src-dir", must_exist=True, expect_dir=True)
        out_static = Path(args.out_dir).expanduser().resolve() if args.out_dir else fail_gracefully("Missing `--out-dir` for `--workflow gen-assets`.")
        import build_static_ttf_assets as bsta
        bsta.build_all_static_assets(
            src_dir=src_assets,
            out_dir=out_static,
            meta_out_dir=(out_static.parent / "metadata").resolve(),
            force=True,
            jobs=hw_info.recommended_workers,
        )
        bsta.verify_static_ttf_directory(out_static)
        return

    cand_src = require_valid_path(args.src_dir, "--src-dir", must_exist=True, expect_dir=True)
    font_dir = (cand_src / "static_ttfs").resolve() if (cand_src / "static_ttfs").is_dir() else cand_src

    if not args.out_dir:
        fail_gracefully("Missing required `--out-dir <build_dir>` argument.", "Pass `--out-dir build/<target>` on the command line.")
    base_out = Path(args.out_dir).expanduser().resolve()
    if base_out.name == "fonts" and base_out.parent.name == "assets":
        c_out_dir = base_out
        root_out = base_out.parent.parent
    else:
        root_out = base_out
        c_out_dir = root_out / "fonts"

    dist_root = Path(args.dist_dir).expanduser().resolve() if args.dist_dir else (root_out / "dist").resolve()

    if not args.scheme:
        fail_gracefully("Missing required `--scheme <path.scheme.json>` argument.", "Pass `--scheme <file.scheme.json>` to specify the build configuration.")
    scheme_path = require_valid_path(args.scheme, "--scheme", must_exist=True, expect_dir=False)

    load_icon_name_registry(font_dir)
    scheme_cfg, raw_plan = load_plan_from_scheme_json(scheme_path, full_icon_catalog=args.full_icon_catalog)
    rcfg = scheme_cfg.get("raster_config", {})

    # 3. Strictly validate Target Hardware Scheme & single 3 MByte partition constraint (Zero Hard Defaults)
    hw_spec = load_and_validate_hardware_scheme(
        scheme_cfg=scheme_cfg,
        hw_scheme_cli=args.hw_scheme,
        repo_root=repo_root,
        scheme_path=scheme_path,
    )

    # Resolve patches path from CLI or scheme JSON
    raw_patches_cfg = args.patches or rcfg.get("patches_file")
    if raw_patches_cfg:
        p_cand = Path(raw_patches_cfg)
        if not p_cand.is_absolute():
            p_cand = (repo_root / p_cand).resolve() if (repo_root / p_cand).is_file() else (scheme_path.parent / p_cand).resolve()
        patches_path = p_cand
    else:
        patches_path = (repo_root / "font_icon_epd_patches.json").resolve()

    raw_ascii_cfg = args.ascii_dir or rcfg.get("ascii_patches_dir")
    if raw_ascii_cfg:
        a_cand = Path(raw_ascii_cfg)
        default_ascii_dir = a_cand.resolve() if a_cand.is_absolute() else (repo_root / a_cand).resolve()
    else:
        default_ascii_dir = (root_out / "ascii_patches").resolve()

    raw_pipe_arg = (args.pipeline or rcfg.get("pipeline") or rcfg.get("raster_mode") or "raw-hinted").strip().lower()
    potrace_submode = (getattr(args, "potrace_submode", None) or rcfg.get("potrace_submode") or "").strip().lower()
    if potrace_submode == "jfa-marching" and raw_pipe_arg in ("svg-potrace", "potrace", "svg"):
        raw_pipe_arg = "svg-potrace-jfa"
    is_all_debug = (raw_pipe_arg == "all-debug")
    dump_each_method_outputs = raw_pipe_arg in ("all", "all-debug")
    run_all_methods = dump_each_method_outputs or (args.workflow == "audit")
    raster_m = "raw-hinted" if dump_each_method_outputs else normalize_pipeline_name(raw_pipe_arg)

    # Strict `char_debug` and `sheet_debug` boolean gating:
    # - CLI `--char-debug` / `--no-char-debug` takes precedence over `raster_config.char_debug`
    # - CLI `--sheet-debug` / `--no-sheet-debug` takes precedence over `raster_config.sheet_debug`
    # - `--pipeline all-debug` forces both `sheet_debug=True` and `char_debug=True`
    if is_all_debug:
        eff_sheet_debug = True
        eff_char_debug = True
    else:
        if args.sheet_debug is not None:
            eff_sheet_debug = bool(args.sheet_debug)
        elif "sheet_debug" in rcfg:
            eff_sheet_debug = bool(rcfg.get("sheet_debug"))
        else:
            eff_sheet_debug = (args.workflow in ("check", "all"))

        if args.char_debug is not None:
            eff_char_debug = bool(args.char_debug)
        elif "char_debug" in rcfg:
            eff_char_debug = bool(rcfg.get("char_debug"))
        else:
            eff_char_debug = False

    do_build_c = args.workflow in ("build", "audit", "all")
    do_check_png = eff_sheet_debug or eff_char_debug or args.audit_screens

    dump_ascii_root = default_ascii_dir if do_dump_ascii else None
    apply_ascii_root = default_ascii_dir if do_apply_ascii else None
    ascii_ingest_root = default_ascii_dir if default_ascii_dir.is_dir() else None

    inspect_png_root = (root_out / "inspect_pages") if eff_sheet_debug else None
    inspect_chars_root = (root_out / "inspect_chars") if (eff_char_debug and args.inspect_chars_filter != "none") else None
    bdf_out_dir = (root_out / "bdf") if do_build_c else None
    metrics_out_dir = (root_out / "metrics") if (do_build_c or do_check_png) else None
    vault_out_path = (dist_root / "humid1_epd_vault.json.gz") if do_build_c else None
    specimen_out_path = (root_out / "inspect_pages" / "humid1_epd_specimen_188dpi.png") if eff_sheet_debug else None
    debug_stages_root = (root_out / "debug_stages") if (args.debug_stages or rcfg.get("debug_stages", False)) else None

    if apply_ascii_root and apply_ascii_root.is_dir():
        cnt = build_patches_json_from_ascii_root(apply_ascii_root, patches_path, only_modified=True)
        print(f"[+] Compiled {cnt} modified ASCII glyph patch(es) from {apply_ascii_root} -> {patches_path}")

    patch_manifest: dict = {"patches": {}}
    if patches_path.is_file():
        loaded_p = json.loads(patches_path.read_text(encoding="utf-8"))
        if "patches" in loaded_p:
            patch_manifest = loaded_p
        else:
            for k, v in loaded_p.items():
                if not k.startswith("_") and isinstance(v, dict):
                    patch_manifest["patches"][k] = v
        print(f"[+] Loaded manual optical patch manifest: {patches_path}")

    normal_w = int(rcfg.get("normal_weight", args.normal_weight))
    bold_w = int(rcfg.get("bold_weight", args.bold_weight))
    italic_w = int(rcfg.get("italic_weight", args.italic_weight))
    eff_threshold = int(args.threshold if args.threshold is not None else rcfg.get("threshold", 128))
    if not (1 <= eff_threshold <= 254):
        fail_gracefully(f"Invalid `--threshold {eff_threshold}`. Must be an integer in [1..254] (default: 128).")
    eff_gamma = float(args.gamma if args.gamma is not None else rcfg.get("gamma", 1.0))
    if not (0.20 <= eff_gamma <= 3.00):
        fail_gracefully(f"Invalid `--gamma {eff_gamma}`. Must be in [0.20..3.00] (default: 1.0).")

    print(
        f"[+] Loaded declarative font scheme: {scheme_path.name} "
        f"(hw_scheme={hw_spec.hw_scheme_id}, chip={hw_spec.chip_name}, partition_1={hw_spec.partition_1}, "
        f"pipeline={raw_pipe_arg}, threshold={eff_threshold}, gamma={eff_gamma:.2f}, "
        f"sheet_debug={eff_sheet_debug}, char_debug={eff_char_debug})"
    )

    family_roles = get_family_roles(normal_w, bold_w, italic_w)
    if args.families:
        allowed_fams = set(args.families)
        raw_plan = [item for item in raw_plan if item[0] in allowed_fams]

    if do_build_c:
        c_out_dir.mkdir(parents=True, exist_ok=True)

    recursive_font_index = index_font_files_recursive([font_dir, repo_root / "assets"])

    planned_symbols_set = set()
    for _fam, _role, _psizes, _, _, _, _ in raw_plan:
        _r = Path(_role.split("custom:", 1)[1]).stem.lower().replace("-", "_") if _role.startswith("custom:") else _role
        _szs = args.sizes if args.sizes is not None else _psizes
        _fl = SUBFAMILY_FLOORS.get(_fam, 10)
        for _s in _szs:
            if _s >= _fl or scheme_cfg is not None:
                planned_symbols_set.add(format_strike_symbol(_fam, _r, _s))

    def _resolve_smart_fallback(fb_pat: Optional[str], cur_sz: int, cur_sym: str, all_syms: set) -> Optional[str]:
        if not fb_pat:
            return None
        cand = fb_pat.format(size=cur_sz)
        if not cand.startswith("humid1_"):
            if cand.startswith(("plex_sans_", "plex_mono_", "plex_cond_", "plex_serif_", "plex_math_")):
                cand = f"humid1_font_{cand}"
            elif cand.startswith("plex_terminus_"):
                cand = f"humid1_font_{cand[5:]}"
            else:
                cand = f"humid1_font_{cand}"
        if cand == cur_sym:
            return None
        if cand in all_syms:
            return cand
        m = re.match(r"^(.+_)(\d+)$", cand)
        if m:
            prefix = m.group(1)
            avail_sizes = []
            for s_item in all_syms:
                if s_item.startswith(prefix) and s_item != cur_sym:
                    tail = s_item[len(prefix):]
                    if tail.isdigit():
                        avail_sizes.append((int(tail), s_item))
            if avail_sizes:
                le = [x for x in avail_sizes if x[0] <= cur_sz]
                if le:
                    return max(le, key=lambda x: x[0])[1]
                return min(avail_sizes, key=lambda x: abs(x[0] - cur_sz))[1]
        return None

    strike_tasks: List[dict] = []
    for family, role, prof_sizes, range_str, inc_fa5, fb_pattern, fa_range_str in raw_plan:
        if role.startswith("custom:"):
            ttf_name = role.split("custom:", 1)[1]
            role = Path(ttf_name).stem.lower().replace("-", "_")
        else:
            fam_map = family_roles.get(family, family_roles["sans"])
            ttf_name = fam_map.get(role, fam_map.get("normal", "IBMPlexSans-Regular.ttf"))

        sizes_to_build = args.sizes if args.sizes is not None else prof_sizes
        floor_px = SUBFAMILY_FLOORS.get(family, 10)
        valid_sizes = [s for s in sizes_to_build if s >= floor_px or scheme_cfg is not None]

        codepoints = parse_unicode_range(range_str)
        if family.startswith("icon_"):
            codepoints = [cp for cp in codepoints if cp >= 0xE000]
            if family == "icon_tabler" and role == "filled":
                codepoints = [cp for cp in codepoints if cp >= 0xEE80]
                if not codepoints:
                    codepoints = parse_unicode_range(DEFAULT_ICON_FALLBACK_RANGES["icon_tabler_filled"])
        enable_kern = family in ("sans", "plex_sans", "noto_sans", "cond", "plex_cond", "noto_cond", "serif", "plex_serif", "noto_serif", "custom")

        for sz in valid_sizes:
            strike_ttf_name = ttf_name
            if family == "terminus":
                if "bold" in role.lower():
                    for c_sz in (sz, max(12, sz - 2), 16):
                        if resolve_font_file_recursive(f"Terminus-Bold-{c_sz}.ttf", [font_dir], recursive_font_index):
                            strike_ttf_name = f"Terminus-Bold-{c_sz}.ttf"
                            break
                elif "vga" in role.lower():
                    for c_sz in (sz, 16, 14):
                        if resolve_font_file_recursive(f"Terminus-VGA-{c_sz}.ttf", [font_dir], recursive_font_index):
                            strike_ttf_name = f"Terminus-VGA-{c_sz}.ttf"
                            break
                else:
                    for c_sz in (sz, max(12, sz - 2), 16):
                        if resolve_font_file_recursive(f"Terminus-Normal-{c_sz}.ttf", [font_dir], recursive_font_index):
                            strike_ttf_name = f"Terminus-Normal-{c_sz}.ttf"
                            break

            ttf_path = resolve_font_file_recursive(strike_ttf_name, [font_dir, repo_root / "assets"], recursive_font_index)
            if ttf_path is None or not ttf_path.is_file():
                fail_gracefully(
                    f"Missing font asset `{strike_ttf_name}` inside `{font_dir}`.",
                    "Run `01_build_static_ttfs.bat` first or verify `--src-dir` contains the font.",
                )

            sym_name = format_strike_symbol(family, role, sz)
            legacy_sym_name = f"plex_{family}_{role}_{sz}"
            fb_sym = _resolve_smart_fallback(fb_pattern, sz, sym_name, planned_symbols_set)

            strike_patches = (
                patch_manifest.get("patches", {}).get(sym_name)
                or patch_manifest.get("patches", {}).get(legacy_sym_name)
                or {}
            )
            strike_ascii_dir = (ascii_ingest_root / sym_name) if ascii_ingest_root else None
            effective_raster_m = "exact-mono" if family in ("terminus", "unifont") else raster_m

            strike_tasks.append({
                "sym_name": sym_name,
                "family": family,
                "role": role,
                "sz": sz,
                "ttf_name": ttf_path.name,
                "ttf_path": str(ttf_path),
                "font_dir": str(font_dir),
                "codepoints": codepoints,
                "effective_raster_m": effective_raster_m,
                "threshold": eff_threshold,
                "gamma": eff_gamma,
                "strike_patches": strike_patches,
                "strike_ascii_dir": str(strike_ascii_dir) if strike_ascii_dir else None,
                "enable_kern": enable_kern,
                "prune_noop_kern": not args.keep_noop_kern,
                "do_build_c": do_build_c,
                "c_out_dir": str(c_out_dir) if do_build_c else None,
                "fb_sym": fb_sym,
                "dump_ascii_root": str(dump_ascii_root) if dump_ascii_root else None,
                "trouble_only": args.trouble_only,
                "unicode_preview": args.unicode_preview,
                "sheet_debug": eff_sheet_debug,
                "char_debug": eff_char_debug,
                "inspect_png_root": str(inspect_png_root) if inspect_png_root else None,
                "inspect_chars_root": str(inspect_chars_root) if inspect_chars_root else None,
                "inspect_chars_filter": args.inspect_chars_filter,
                "bdf_out_dir": str(bdf_out_dir) if bdf_out_dir else None,
                "metrics_out_dir": str(metrics_out_dir) if metrics_out_dir else None,
                "debug_stages_dir": str(debug_stages_root) if debug_stages_root else None,
                "run_all_methods": (
                    False if (args.workflow == "build" and not eff_sheet_debug and not eff_char_debug and raw_pipe_arg != "all-debug")
                    else (run_all_methods if (len(planned_symbols_set) <= 120 or raw_pipe_arg == "all-debug") else (run_all_methods and sz == 16))
                ),
                "dump_each_method_outputs": dump_each_method_outputs,
                "verbose": args.verbose,
            })

    if getattr(args, "shared_ram_mb", None):
        import os as _os
        _os.environ["EPD_FONT_SHARED_RAM_MB"] = str(args.shared_ram_mb)
    if getattr(args, "accel", None):
        import os as _os
        _os.environ["EPD_FONT_ACCEL"] = str(args.accel)
        select_math_backend(args.accel)

    t_start = time.perf_counter()
    max_workers = hw_info.recommended_workers
    print(f"[*] {describe_hybrid_dispatch_plan(len(strike_tasks), max_workers)}")
    print(f"[*] Processing {len(strike_tasks)} font/icon strikes in parallel across {max_workers} worker processes...")

    compiled_symbols: List[Tuple[str, str, str, int, int]] = []
    compiled_details: List[dict] = []
    strike_cache: Dict[str, Tuple[Dict[int, GlyphStrike], int, int]] = {}
    kern_cache: Dict[str, Dict[Tuple[int, int], int]] = {}
    all_method_rows: List[Tuple[str, int, Dict[str, dict]]] = []
    vault_data: dict = {
        "vault_version": TOOL_VERSION,
        "raster_mode": raw_pipe_arg,
        "threshold": eff_threshold,
        "gamma": eff_gamma,
        "normal_weight": normal_w,
        "hardware_scheme": hw_spec.hw_scheme_id,
        "chip_name": hw_spec.chip_name,
        "partition_1": hw_spec.partition_1,
        "partition_1_bytes": hw_spec.partition_1_bytes,
        "strikes": {},
    }
    total_rom_bytes = 0
    total_ascii_dumped = 0
    total_png_inspected = 0
    total_char_pngs = 0

    worker_results = run_parallel_tasks(_execute_strike_worker_task, strike_tasks, max_workers=max_workers)
    for res in worker_results:
        sym_name = res["sym_name"]
        family = res["family"]
        role = res["role"]
        sz = res["sz"]
        rom_b = res["rom_b"]
        glyphs = res["glyphs"]
        line_h = res["line_h"]
        base_l = res["base_l"]
        kern_pairs = res["kern_pairs"]

        total_rom_bytes += rom_b
        total_ascii_dumped += res["ascii_dumped"]
        total_png_inspected += res["png_pages"]
        total_char_pngs += res["char_pngs"]
        compiled_symbols.append((sym_name, family, role, sz, rom_b))
        compiled_details.append({
            "sym_name": sym_name,
            "family": family,
            "role": role,
            "sz": sz,
            "line_h": line_h,
            "glyph_count": len(glyphs),
            "kern_count": len(kern_pairs),
            "rom_b": rom_b,
            "c_disk_b": res.get("c_disk_b", 0),
        })
        if res.get("all_method_stats"):
            all_method_rows.append((sym_name, sz, res["all_method_stats"]))

        gmap = {g.codepoint: g for g in glyphs}
        strike_cache[sym_name] = (gmap, line_h, base_l)
        kern_cache[sym_name] = {(lc, rc): kv for _, _, lc, rc, kv in kern_pairs}

        if vault_out_path:
            vault_data["strikes"][sym_name] = res["vault_entry"]

        print(res["log_line"])

    elapsed_s = time.perf_counter() - t_start
    print(f"[+] Completed {len(strike_tasks)} strikes in {elapsed_s:.2f}s using {max_workers} CPU cores.")

    if all_method_rows:
        aud_dir = root_out / "audits"
        aud_dir.mkdir(parents=True, exist_ok=True)
        hdr_cols = " | ".join(f"`{pm}` (Stem / >=2px / Cnt)" for pm in CANONICAL_PIPELINES)
        sep_cols = " | ".join(":---" for _ in CANONICAL_PIPELINES)
        md_lines = [
            f"# 8-Pipeline Resolution-Reduction Bilevel Conversion Audit Summary (`epd-font` v{TOOL_VERSION})",
            "",
            f"- **Scheme**: `{scheme_path.name}`",
            f"- **Hardware Scheme**: `{hw_spec.hw_scheme_id}` (`{hw_spec.chip_name}`, `partition_1 = {hw_spec.partition_1}`)",
            f"- **Threshold**: `{eff_threshold}` | **Gamma**: `{eff_gamma:.2f}`",
            "",
            f"| Strike Symbol | Size | {hdr_cols} |",
            f"| :--- | ---: | {sep_cols} |",
        ]
        for s_sym, s_sz, fstats in all_method_rows:
            cells = []
            for pm in CANONICAL_PIPELINES:
                st = fstats.get(pm, {})
                cells.append(f"`{st.get('mean_stem_px', 0):.2f}px` / `{st.get('stem_2px_pct', 0):.1f}%` / `{st.get('counter_pct', 0):.1f}%`")
            md_lines.append(f"| `{s_sym}` | `{s_sz}px` | {' | '.join(cells)} |")
        md_body = "\n".join(md_lines) + "\n"
        aud_file = aud_dir / "audit_8_pipelines_summary.md"
        aud_file.write_text(md_body, encoding="utf-8")
        (aud_dir / "audit_4_pipelines_summary.md").write_text(md_body, encoding="utf-8")
        print(f"[+] Generated 8-Pipeline Resolution-Reduction Audit Summary -> {aud_file}")

    if do_build_c:
        generate_headers(c_out_dir, compiled_symbols, scheme_cfg=scheme_cfg)
        copied_lics = copy_licenses(None, font_dir, c_out_dir)
        if args.verbose:
            print(f"[+] Copied {len(copied_lics)} license files into {c_out_dir / 'licenses'}")

    if vault_out_path:
        v_bytes = export_strike_vault(vault_out_path, vault_data)
        print(f"[+] Exported pre-rasterized Strike Vault ({len(vault_data['strikes'])} strikes) -> {vault_out_path} ({v_bytes:,} B)")

    if do_build_c and compiled_details:
        rep_dpi = args.dpi if args.dpi is not None else hw_spec.dpi
        rep_scheme = scheme_cfg.get("scheme_id", "custom") if scheme_cfg else "custom"
        sz_rep_path = write_total_disk_size_report(
            c_out_dir=c_out_dir,
            root_out=root_out,
            dist_root=dist_root,
            compiled_details=compiled_details,
            vault_path=vault_out_path,
            scheme_id=rep_scheme,
            dpi=rep_dpi,
            scheme_cfg=scheme_cfg,
            hw_spec=hw_spec,
            hw_scheme_cli=args.hw_scheme,
            scheme_path=scheme_path,
        )
        print(f"[+] Generated Flash ROM (.rodata) & Disk Size Report -> {sz_rep_path}")

    if dump_ascii_root:
        print(f"[+] Dumped {total_ascii_dumped:,} Full-Canvas 1:1 Spaced ASCII .txt files across {len(compiled_symbols)} folders in {dump_ascii_root}")

    if eff_sheet_debug and inspect_png_root and strike_cache:
        master_map_png = inspect_png_root / "master_char_icon_map.png"
        render_master_char_icon_map_png(
            out_png=master_map_png,
            strike_cache=strike_cache,
            scheme_id=scheme_cfg.get("scheme_id", "epd-font") if scheme_cfg else "epd-font",
            pipeline_name=raw_pipe_arg,
            static_dir=font_dir,
        )
        print(f"[+] Rendered {total_png_inspected} Auto-Wrapped Page Check PNG sheets + Master Character/Icon Map in {inspect_png_root}")
    elif not eff_sheet_debug:
        print("[*] Sheet inspection PNG generation skipped (`sheet_debug = false`).")

    if eff_char_debug and inspect_chars_root:
        print(f"[+] Rendered {total_char_pngs:,} Char-by-Char Deep-Check Blueprint PNG cards in {inspect_chars_root}")
    elif not eff_char_debug:
        print("[*] Character inspection PNG generation skipped (`char_debug = false`).")

    label_mode = scheme_cfg.get("scheme_id", "custom") if scheme_cfg else "custom"
    print(
        f"\n[+] Scheme '{label_mode}' (pipeline={raw_pipe_arg}, threshold={eff_threshold}, gamma={eff_gamma:.2f}, normal={normal_w}) complete: "
        f"{len(compiled_symbols)} strikes, total ROM = {total_rom_bytes:,} bytes ({total_rom_bytes/1024:.1f} KB / {total_rom_bytes * 100.0 / hw_spec.partition_1_bytes:.2f}% of {hw_spec.partition_1})."
    )

    if (args.audit_screens or eff_sheet_debug) and strike_cache:
        s_dpi = args.dpi if args.dpi is not None else hw_spec.dpi
        s_w = args.screen_width if args.screen_width is not None else hw_spec.width_px
        s_h = args.screen_height if args.screen_height is not None else hw_spec.height_px
        s_m = args.safe_margin if args.safe_margin is not None else hw_spec.safe_margin_px
        p_label = hw_spec.panel
        c_rows = (scheme_cfg or {}).get("screen_audit_rows", None)
        run_screen_width_audit(
            strike_cache,
            kern_cache,
            None,
            screen_width=s_w,
            screen_height=s_h,
            safe_margin=s_m,
            dpi=s_dpi,
            panel_name=p_label,
            custom_rows=c_rows,
        )

    if eff_sheet_debug and specimen_out_path and strike_cache:
        render_specimen_sheet(specimen_out_path, strike_cache)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        teardown_math_backends()
        sys.stderr.write("\n[!] Execution interrupted by user (Ctrl+C). Workers stopped and OpenCL/host memory released cleanly.\n")
        sys.stderr.flush()
        sys.exit(130)
    finally:
        teardown_math_backends()
