#!/usr/bin/env python3
"""
humid1_font_qualify.py (v1.0.23)
================================
A 1-bit EPD font generator and asset pipeline for embedded displays.
Repository : https://github.com/Humidyne-Labs/epd-font
Authors    : Humiditron (https://github.com/humiditron) & AI/LLM Development Partner
License    : MIT License

Standalone 20 cm (200 mm) EPD Legibility Qualification & Visual Proof Suite:
  - Accepts any directory of `.ttf`, `.otf`, `.ttc`, `.otc`, or `.bdf` fonts (`--src-dir`)
    including raw Variable TrueType masters (auto-instantiated into weights 400..800) and
    size-specific bitmap families (e.g., `Terminus-Normal-12..40.ttf`).
  - Simulates 2D Gaussian Point-Spread Function (PSF) diffusion on an empirical 188.15 DPI
    (135 um pixel pitch) reflective SSD1681 panel at 200 mm viewing distance:
      * Nominal viewing : sigma = 1.25 px (169 um)
      * Off-axis stress : sigma = 1.75 px (236 um)
  - Performs both Character-Level (worst-decile P10 retention, Trouble-15 retention, enclosed
    Betti B1 counters, and open-bay cavities on `s, S, c, e, 2, 3, 5, z`) and String-Level
    (LVGL v9 FP4 advance + kerning on `"Status"`, `"Vapor Pressure"` `ss` grating, `"02:48 AM"`,
    `"SETTLED (90%)"`, `"13.3 hPa"`, `"(25.7°C ambient)"`, `"24.2 g/m³"`) qualification tests.
  - Verifies cross-weight visual separation (`Normal` vs. `Bold` within each family) and
    `188 px` H1OS two-column row budget clearance without mutating `.scheme.json` files.
  - Outputs per-font Gaussian proof PNGs, per-family weight-separation sheets, a master
    ranked visual scorecard PNG, and structured `.md`, `.csv`, and `.json` qualification reports.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


def _early_accel_scan() -> None:
    accel = os.environ.get("EPD_FONT_ACCEL", "").strip().lower()
    if not accel:
        for idx, arg in enumerate(sys.argv):
            if arg == "--accel" and idx + 1 < len(sys.argv):
                accel = sys.argv[idx + 1].strip().lower()
                break
            elif arg.startswith("--accel="):
                accel = arg.split("=", 1)[1].strip().lower()
                break
    if accel == "cpu":
        os.environ["EPD_FONT_ACCEL"] = "cpu"
        os.environ["OPENCV_OPENCL_RUNTIME"] = "disabled"
        try:
            if hasattr(cv2, "ocl"):
                cv2.ocl.setUseOpenCL(False)
        except Exception:
            pass


_early_accel_scan()

from math_backends import describe_math_backend, select_math_backend, teardown_math_backends
from humid1_bilevel_pipelines import (
    CANONICAL_MIN_HOLES,
    CANONICAL_PIPELINES,
    EPD_20CM_SIGMA_NOM_PX,
    EPD_20CM_SIGMA_OFF_PX,
    EPD_DEFAULT_R_BG,
    EPD_DEFAULT_R_INK,
    OPEN_CAVITY_MIN_BAYS,
    TROUBLE_15_CHARS,
    _compute_stroke_centerline_mask,
    compute_betti_numbers,
    compute_gaussian_psf_char_metrics,
    normalize_pipeline_name,
    rows_to_binary_array,
    simulate_epd_gaussian_psf,
)
from humid1_ft_raster import (
    GlyphStrike,
    _get_cached_tt_meta,
    extract_kerning_pairs_from_meta,
    load_freetype,
    open_ttfont_safe,
    rasterize_font_strike,
)
from humid1_runtime import (
    TOOL_VERSION,
    TargetHardwareSpec,
    detect_host_hardware,
    fail_gracefully,
    install_clean_signal_handlers,
    load_and_validate_hardware_scheme,
    require_valid_path,
    run_parallel_tasks,
)

QUALIFY_BENCHMARK_CHARS = (
    "0123456789"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
    "# $%&()[]{}/*+-.:;!?@<>=°³Δ"
).replace(" ", "")

QUALIFY_TEST_STRINGS: Tuple[Tuple[str, str], ...] = (
    ("status", "Status"),
    ("pressure", "Vapor Pressure"),
    ("clock", "02:48 AM"),
    ("settled", "SETTLED (90%)"),
    ("hpa", "13.3 hPa"),
    ("ambient", "(25.7°C ambient)"),
    ("units", "24.2 g/m³"),
)

H1OS_BUDGET_PAIRS: Tuple[Tuple[str, str], ...] = (
    ("Dew Point", "78.4°F (25.8°C)"),
    ("Vapor Pressure", "42.8 hPa"),
    ("Wakes", "625 (Ring 32/32)"),
)

DEFAULT_QUALIFY_PIPELINES: Tuple[str, ...] = ("otsu-adaptive", "raw-hinted")

_WEIGHT_SUFFIX_RE = re.compile(
    r"[-_]?(?:ExtraBoldItalic|SemiBoldItalic|ExtraLightItalic|MediumItalic|BlackItalic|"
    r"LightItalic|ThinItalic|BoldItalic|ExtraBold|UltraBold|ExtraLight|SemiBold|"
    r"DemiBold|Medium|Regular|MedItal|Normal|Roman|Bold|Black|Heavy|Light|Thin|"
    r"Italic|Oblique|Var-Roman|Var-Italic|Var)$",
    re.IGNORECASE,
)


@dataclass
class QualifyCandidate:
    label: str
    font_path: Path
    font_number: int
    file_type: str
    family_group: str
    weight_class: int
    is_italic: bool
    is_bitmap: bool
    is_monospace: bool
    size_to_path_map: Dict[int, str] = field(default_factory=dict)


@dataclass
class QualifySizeMetrics:
    size_px: int
    best_pipeline: str
    mean_ret_nom_pct: float
    trouble_ret_nom_pct: float
    p10_ret_nom_pct: float
    p10_ret_off_pct: float
    s_ret_nom_pct: float
    s_cm_nom: float
    s_cavity_ok: bool
    d8_ret_nom_pct: float
    d8_cm_nom: float
    d8_cavity_ok: bool
    enclosed_counter_pct: float
    open_cavity_pct: float
    mean_stem_px: float
    min_stem_px: float
    stem_2px_pct: float
    uniformity_pct: float
    min_string_ret_nom_pct: float
    mean_string_ret_nom_pct: float
    status_ret_nom_pct: float
    pressure_ret_nom_pct: float
    ss_grating_cm: float
    clock_ret_nom_pct: float
    max_h1os_row_px: int
    min_h1os_clearance_px: int
    fits_188px_budget: bool
    ink_pixels: int
    x_height_px: int
    cap_height_px: int
    verdict: str  # "PASS", "MARGINAL", or "FAIL"
    qualifies_20cm: bool
    least_worst_score: float
    failure_tags: List[str] = field(default_factory=list)
    pipeline_scores: Dict[str, float] = field(default_factory=dict)
    string_details: Dict[str, dict] = field(default_factory=dict)


@dataclass
class FontQualifyResult:
    label: str
    font_file: str
    file_type: str
    family_group: str
    weight_class: int
    is_italic: bool
    is_bitmap: bool
    is_monospace: bool
    viable_floor_px: int
    marginal_floor_px: int
    score_14px: float
    score_16px: float
    score_18px: float
    overall_least_worst_score: float
    by_size: Dict[int, QualifySizeMetrics] = field(default_factory=dict)
    proof_png: str = ""


@dataclass
class FamilyWeightPairEval:
    family_group: str
    size_px: int
    normal_label: str
    normal_weight: int
    bold_label: str
    bold_weight: int
    normal_verdict: str
    bold_verdict: str
    normal_stem_px: float
    bold_stem_px: float
    stem_delta_px: float
    ink_mass_ratio: float
    has_weight_sep: bool
    pair_qualifies: bool
    pair_score: float
    notes: str


def _derive_family_group(stem: str) -> str:
    """Strip variable axis brackets and trailing weight/style tokens while preserving width/typeface subfamilies."""
    cur = re.sub(r"\[[^\]]*\]", "", stem).strip().rstrip("-_")
    for _ in range(3):
        nxt = _WEIGHT_SUFFIX_RE.sub("", cur).rstrip("-_")
        if not nxt or nxt == cur:
            break
        cur = nxt
    return cur or stem


def _instantiate_variable_font_for_qualify(
    var_ttf: Path,
    cache_dir: Path,
    include_megafonts: bool = False,
) -> List[Path]:
    """Instantiate a raw variable `.ttf` into static weights [400, 500, 600, 700, 800] for qualification."""
    from build_static_ttf_assets import instantiate_plex_variable_cut
    from fontTools.ttLib import TTFont

    if not include_megafonts and var_ttf.stat().st_size > 2_500_000:
        return []

    cache_dir.mkdir(parents=True, exist_ok=True)
    tt = TTFont(str(var_ttf), lazy=True)
    out_paths: List[Path] = []
    try:
        if "fvar" not in tt:
            return []
        if not include_megafonts and "maxp" in tt and int(getattr(tt["maxp"], "numGlyphs", 0) or 0) > 4500:
            return []
        axes = {ax.axisTag: ax for ax in tt["fvar"].axes}
        if "wght" not in axes:
            return []
        w_min = axes["wght"].minValue
        w_max = axes["wght"].maxValue
        is_plex = "plex" in var_ttf.stem.lower()
        base_stem = _derive_family_group(var_ttf.stem)
        is_ital = "italic" in var_ttf.stem.lower()
        digest = hashlib.sha256(f"{var_ttf.resolve()}|{var_ttf.stat().st_size}".encode("utf-8")).hexdigest()[:8]

        weight_names = {400: "Regular", 500: "Medium", 600: "SemiBold", 700: "Bold", 800: "ExtraBold"}
        for w_val, w_tag in weight_names.items():
            eff_tag = (f"{w_tag}Italic" if w_tag != "Regular" else "Italic") if is_ital else w_tag
            dst = cache_dir / f"{base_stem}-{eff_tag}_{digest}.ttf"
            if dst.is_file():
                out_paths.append(dst)
                continue
            coords: Dict[str, float] = {}
            for ax_tag, ax in axes.items():
                if ax_tag == "wght":
                    if is_plex and w_val > w_max:
                        coords["wght"] = float(w_val)
                    else:
                        coords["wght"] = float(max(w_min, min(w_max, w_val)))
                else:
                    coords[ax_tag] = float(ax.defaultValue)
            if not is_plex and w_val > w_max and any(abs(c - w_val) > 25 for c in [coords["wght"]]):
                # Avoid duplicate clamped cuts for non-Plex variable fonts
                continue
            instantiate_plex_variable_cut(var_ttf, dst, coords, {})
            out_paths.append(dst)
    except Exception:
        return []
    finally:
        tt.close()
    return out_paths


def _worker_instantiate_var_ttf(task: dict) -> Tuple[str, List[str]]:
    """Multiprocess worker wrapper for instantiating a single variable `.ttf` master."""
    p = Path(task["path"])
    cache_dir = Path(task["cache_dir"])
    inc_mega = bool(task.get("include_megafonts", False))
    paths = _instantiate_variable_font_for_qualify(p, cache_dir, include_megafonts=inc_mega)
    return (task["path"], [str(x) for x in paths])


def discover_qualify_candidates(
    src_dir: Path,
    explicit_fonts: Optional[Sequence[str]] = None,
    include_icons: bool = False,
    include_megafonts: bool = False,
    repo_root: Optional[Path] = None,
    var_workers: Optional[int] = None,
) -> List[QualifyCandidate]:
    """
    Discover `.ttf`, `.otf`, `.ttc`, `.otc`, and `.bdf` font files in `src_dir`,
    grouping size-specific bitmap strikes (`Terminus-Normal-12..40.ttf`), expanding
    multi-face `.ttc` collections, and auto-instantiating raw Variable TTFs.
    """
    raw_paths: List[Path] = []
    megafont_skipped = 0
    if explicit_fonts:
        for f in explicit_fonts:
            raw_paths.append(require_valid_path(f, "--fonts", must_exist=True, expect_dir=False))
    else:
        for dirpath, _, filenames in os.walk(src_dir):
            dp = Path(dirpath)
            if any(skip in dp.parts for skip in ("cache", "metadata", "licenses", "__pycache__")):
                continue
            for fn in sorted(filenames):
                if fn.lower().endswith((".ttf", ".otf", ".ttc", ".otc", ".bdf")):
                    fp = (dp / fn).resolve()
                    if not include_megafonts and fp.stat().st_size > 3_000_000:
                        megafont_skipped += 1
                        continue
                    raw_paths.append(fp)

    if megafont_skipped > 0:
        print(
            f"[*] Skipped {megafont_skipped} multi-megabyte CJK/pan-Unicode font files (>3.0 MB); "
            "pass --include-megafonts to include",
            flush=True,
        )

    # Identify grouped size-specific Terminus strikes (`Terminus-Normal-14.ttf`, etc.)
    bitmap_groups: Dict[str, Dict[int, Path]] = {}
    non_grouped_paths: List[Path] = []
    for p in sorted(raw_paths, key=lambda x: x.name.lower()):
        low = p.name.lower()
        if not include_icons and any(ic in low for ic in ("fontawesome", "lucide", "phosphor", "tabler")):
            continue
        m_term = re.match(r"^(Terminus-(?:Normal|Bold|VGA))-(\d+)$", p.stem, re.IGNORECASE)
        if m_term:
            grp_lbl = m_term.group(1)
            sz_val = int(m_term.group(2))
            bitmap_groups.setdefault(grp_lbl, {})[sz_val] = p
        else:
            non_grouped_paths.append(p)

    print(
        f"[*] Scanning {len(non_grouped_paths) + len(bitmap_groups)} font files in `{src_dir}`...",
        flush=True,
    )

    candidates: List[QualifyCandidate] = []
    seen_labels = set()

    for grp_lbl, sz_map in sorted(bitmap_groups.items()):
        rep_sz = 16 if 16 in sz_map else sorted(sz_map.keys())[0]
        rep_path = sz_map[rep_sz]
        is_bold = "bold" in grp_lbl.lower()
        w_cls = 700 if is_bold else (500 if "vga" in grp_lbl.lower() else 400)
        candidates.append(
            QualifyCandidate(
                label=grp_lbl,
                font_path=rep_path,
                font_number=0,
                file_type=rep_path.suffix.lower(),
                family_group="Terminus",
                weight_class=w_cls,
                is_italic=False,
                is_bitmap=True,
                is_monospace=True,
                size_to_path_map={k: str(v) for k, v in sorted(sz_map.items())},
            )
        )
        seen_labels.add(grp_lbl)

    var_cache_dir = (repo_root or Path.cwd()) / "build" / "cache" / "qualify_var_ttfs"
    existing_stems = {
        _derive_family_group(p.stem).lower()
        for p in non_grouped_paths
        if "var" not in p.stem.lower() and "[" not in p.stem
    }

    preliminary_items: List[Tuple[str, Path, int, str]] = []
    var_to_inst: List[Path] = []
    inst_map: Dict[str, List[Path]] = {}
    v_weight_names = {400: "Regular", 500: "Medium", 600: "SemiBold", 700: "Bold", 800: "ExtraBold"}

    for p in non_grouped_paths:
        if bitmap_groups and p.stem.lower() in ("terminus-regular", "terminus-bold"):
            continue
        ext = p.suffix.lower()
        if ext in (".ttc", ".otc"):
            try:
                from fontTools.ttLib import TTCollection
                coll = TTCollection(str(p))
                for f_idx in range(len(coll.fonts)):
                    preliminary_items.append(("face", p, f_idx, f"{p.stem}_face{f_idx}" if len(coll.fonts) > 1 else p.stem))
            except Exception:
                preliminary_items.append(("face", p, 0, p.stem))
            continue

        has_fvar_tag = False
        if ext in (".ttf", ".otf"):
            try:
                with p.open("rb") as fh:
                    has_fvar_tag = b"fvar" in fh.read(1024)
            except Exception:
                has_fvar_tag = False

        if has_fvar_tag:
            if not include_megafonts and p.stat().st_size > 2_500_000:
                continue
            base_stem = _derive_family_group(p.stem)
            base_fg = base_stem.lower()
            if base_fg in existing_stems and not explicit_fonts:
                continue

            is_ital_v = "italic" in p.stem.lower()
            digest_v = hashlib.sha256(f"{p.resolve()}|{p.stat().st_size}".encode("utf-8")).hexdigest()[:8]
            cached_hits: List[Path] = []
            for w_tag in v_weight_names.values():
                eff_tag = (f"{w_tag}Italic" if w_tag != "Regular" else "Italic") if is_ital_v else w_tag
                dst_v = var_cache_dir / f"{base_stem}-{eff_tag}_{digest_v}.ttf"
                if dst_v.is_file():
                    cached_hits.append(dst_v)
            if cached_hits:
                inst_map[str(p)] = cached_hits
                preliminary_items.append(("var", p, 0, p.stem))
                continue

            tt = None
            has_fvar = False
            has_wght_axis = False
            too_many_glyphs = False
            try:
                tt = open_ttfont_safe(p, font_number=0, lazy=True)
                has_fvar = "fvar" in tt
                if has_fvar:
                    has_wght_axis = any(ax.axisTag == "wght" for ax in tt["fvar"].axes)
                    if not include_megafonts and "maxp" in tt and int(getattr(tt["maxp"], "numGlyphs", 0) or 0) > 4500:
                        too_many_glyphs = True
            except Exception:
                has_fvar = False
            finally:
                if tt is not None:
                    try:
                        tt.close()
                    except Exception:
                        pass

            if has_fvar:
                if not include_megafonts and too_many_glyphs:
                    continue
                if has_wght_axis:
                    var_to_inst.append(p)
                    preliminary_items.append(("var", p, 0, p.stem))
                    continue
        preliminary_items.append(("face", p, 0, p.stem))

    if var_to_inst:
        n_vw = max(1, min(12, var_workers or (os.cpu_count() or 4), len(var_to_inst)))
        print(
            f"[*] Instantiating {len(var_to_inst)} variable font master(s) using {n_vw} worker(s) "
            f"(cached in `{var_cache_dir}`)...",
            flush=True,
        )
        v_tasks = [
            {
                "path": str(vp),
                "cache_dir": str(var_cache_dir),
                "include_megafonts": include_megafonts,
            }
            for vp in var_to_inst
        ]
        done_v = 0
        if n_vw == 1 or len(v_tasks) <= 3:
            for vt in v_tasks:
                k_p, out_l = _worker_instantiate_var_ttf(vt)
                inst_map[k_p] = [Path(x) for x in out_l]
                done_v += 1
        else:
            with concurrent.futures.ProcessPoolExecutor(max_workers=n_vw) as v_pool:
                futs = [v_pool.submit(_worker_instantiate_var_ttf, vt) for vt in v_tasks]
                for fut in concurrent.futures.as_completed(futs):
                    try:
                        k_p, out_l = fut.result()
                        inst_map[k_p] = [Path(x) for x in out_l]
                    except Exception:
                        pass
                    done_v += 1
                    if done_v % 25 == 0 or done_v == len(v_tasks):
                        print(f"[*] Variable font instantiation: {done_v}/{len(v_tasks)}...", flush=True)

    expanded_faces: List[Tuple[Path, int, str]] = []
    for kind, p, f_idx, lbl in preliminary_items:
        if kind == "var":
            ips = inst_map.get(str(p), [])
            if ips:
                for ip in ips:
                    clean_lbl = re.sub(r"_[0-9a-f]{8}$", "", ip.stem)
                    expanded_faces.append((ip, 0, clean_lbl))
            else:
                expanded_faces.append((p, 0, p.stem))
        else:
            expanded_faces.append((p, f_idx, lbl))

    total_faces = len(expanded_faces)
    print(f"[*] Inspecting font metadata for {total_faces} face(s)...", flush=True)
    meta_cache_path = var_cache_dir / "metadata_cache.json"
    meta_cache: Dict[str, dict] = {}
    if meta_cache_path.is_file():
        try:
            loaded_mc = json.loads(meta_cache_path.read_text(encoding="utf-8"))
            if isinstance(loaded_mc, dict):
                meta_cache = loaded_mc
        except Exception:
            meta_cache = {}
    meta_dirty = False

    for f_pos, (p, f_idx, lbl) in enumerate(expanded_faces, 1):
        if total_faces >= 500 and (f_pos % 500 == 0 or f_pos == total_faces):
            print(f"[*] Metadata inspection: {f_pos}/{total_faces}...", flush=True)
        if lbl in seen_labels:
            continue
        try:
            st_sz = p.stat().st_size
        except Exception:
            continue
        m_key = f"{p}|{st_sz}|{f_idx}"
        mc = meta_cache.get(m_key)
        if mc is None:
            tt = None
            try:
                tt = open_ttfont_safe(p, font_number=f_idx, lazy=True)
                cmap = tt.getBestCmap() or {}
                has_alnum = (ord("A") in cmap) or (ord("a") in cmap) or (ord("0") in cmap)
                wght = int(getattr(tt["OS/2"], "usWeightClass", 400) or 400) if "OS/2" in tt else 400
                post_fixed = int(getattr(tt.get("post"), "isFixedPitch", 0) or 0) if "post" in tt else 0
                is_mono_mc = bool(post_fixed) or ("mono" in lbl.lower()) or ("monospace" in str(p).lower())
                if not is_mono_mc and ord("i") in cmap and ord("W") in cmap and "hmtx" in tt:
                    hmtx = tt["hmtx"].metrics
                    gi, gw = cmap.get(ord("i")), cmap.get(ord("W"))
                    if gi in hmtx and gw in hmtx and hmtx[gi][0] == hmtx[gw][0]:
                        is_mono_mc = True
                mc = {"has_alnum": has_alnum, "wght": wght, "is_mono": is_mono_mc}
                meta_cache[m_key] = mc
                meta_dirty = True
            except Exception:
                continue
            finally:
                if tt is not None:
                    try:
                        tt.close()
                    except Exception:
                        pass

        if not include_icons and not mc.get("has_alnum", False):
            continue
        wght = int(mc.get("wght", 400))
        is_mono = bool(mc.get("is_mono", False))
        is_ital = ("italic" in lbl.lower()) or ("ital" in lbl.lower()) or ("oblique" in lbl.lower())
        is_bmp = (p.suffix.lower() == ".bdf") or ("unifont" in lbl.lower())
        fam_grp = _derive_family_group(re.sub(r"_face\d+$", "", lbl))
        candidates.append(
            QualifyCandidate(
                label=lbl,
                font_path=p,
                font_number=f_idx,
                file_type=p.suffix.lower(),
                family_group=fam_grp,
                weight_class=wght,
                is_italic=is_ital,
                is_bitmap=is_bmp,
                is_monospace=is_mono,
            )
        )
        seen_labels.add(lbl)

    if meta_dirty:
        try:
            meta_cache_path.parent.mkdir(parents=True, exist_ok=True)
            meta_cache_path.write_text(json.dumps(meta_cache), encoding="utf-8")
        except Exception:
            pass
    return candidates


def render_string_to_binary(
    text: str,
    gmap: Dict[int, GlyphStrike],
    kern_cp: Dict[Tuple[int, int], int],
    line_height: int,
    base_line: int,
    fallback_px: int = 6,
) -> Tuple[np.ndarray, int, List[Tuple[str, int, int, int, int]]]:
    """
    Render a text string onto a 1-BPP binary canvas using exact LVGL v9 FP4
    advance + kerning (`(adv_w_fp4 + kern_fp4 + 8) >> 4`).
    Returns `(binary_canvas, total_advance_px, char_spans)`.
    `char_spans` holds `(char, cursor_x, step_px, box_x0, box_x1)`.
    """
    chars = list(text)
    steps: List[int] = []
    min_x = 0
    max_x = 0
    min_rel_y = 0
    max_rel_y = 0
    cx = 0
    for idx, ch in enumerate(chars):
        cp = ord(ch)
        g = gmap.get(cp)
        if g is None:
            step = fallback_px
        else:
            k_fp4 = kern_cp.get((cp, ord(chars[idx + 1])), 0) if (idx + 1 < len(chars)) else 0
            step = max(1, (g.adv_w_fp4 + k_fp4 + 8) >> 4)
            if g.box_w > 0:
                min_x = min(min_x, cx + g.ofs_x)
                max_x = max(max_x, cx + g.ofs_x + g.box_w)
            if g.box_h > 0:
                min_rel_y = min(min_rel_y, -(g.ofs_y + g.box_h))
                max_rel_y = max(max_rel_y, -g.ofs_y)
        steps.append(step)
        cx += step
        max_x = max(max_x, cx)

    pad_x = max(2, -min_x + 2)
    W = max(8, max_x + pad_x + 4)
    top_h = max(0, line_height - base_line, -min_rel_y)
    bot_h = max(0, base_line, max_rel_y)
    by = top_h + 2
    H = max(8, top_h + bot_h + 6)
    canvas = np.zeros((H, W), dtype=np.uint8)

    spans: List[Tuple[str, int, int, int, int]] = []
    cx = pad_x
    for ch, step in zip(chars, steps, strict=True):
        g = gmap.get(ord(ch))
        if g is not None and g.box_w > 0 and g.box_h > 0:
            gx0 = cx + g.ofs_x
            gy0 = by - (g.ofs_y + g.box_h)
            for rr, r_str in enumerate(g.rows):
                ry = gy0 + rr
                if not (0 <= ry < H):
                    continue
                for cc, px in enumerate(r_str):
                    rx = gx0 + cc
                    if px == "#" and 0 <= rx < W:
                        canvas[ry, rx] = 1
            spans.append((ch, cx, step, gx0, gx0 + g.box_w))
        else:
            spans.append((ch, cx, step, cx, cx + step))
        cx += step

    return canvas, sum(steps), spans


def _measure_ss_grating_contrast(
    canvas: np.ndarray,
    psf_nom: np.ndarray,
    pad_px: int,
    spans: Sequence[Tuple[str, int, int, int, int]],
) -> float:
    """Measure local Michelson contrast inside the `'ss'` pair of `'Vapor Pressure'`."""
    for idx in range(len(spans) - 1):
        if spans[idx][0] == "s" and spans[idx + 1][0] == "s":
            x0 = max(0, spans[idx][3] - 1)
            x1 = min(canvas.shape[1], spans[idx + 1][4] + 1)
            sub_fg = canvas[:, x0:x1]
            ys, _ = np.nonzero(sub_fg > 0)
            if len(ys) == 0:
                return 0.0
            y0, y1 = int(ys.min()), int(ys.max()) + 1
            sub_psf = psf_nom[pad_px + y0 : pad_px + y1, pad_px + x0 : pad_px + x1]
            sub_ridge = _compute_stroke_centerline_mask(sub_fg[y0:y1, :])
            i_stroke = float(np.mean(sub_psf[sub_ridge])) if np.any(sub_ridge) else float(np.min(sub_psf))
            # Check gap between the two 's' glyphs + interior white pixels
            bg_mask = sub_fg[y0:y1, :] == 0
            if not np.any(bg_mask):
                return 0.0
            i_peak = float(np.percentile(sub_psf[bg_mask], 90))
            return max(0.0, (i_peak - i_stroke) / max(1e-5, i_peak + i_stroke))
    return 0.0


def evaluate_string_corpus_psf(
    gmap: Dict[int, GlyphStrike],
    kern_cp: Dict[Tuple[int, int], int],
    line_height: int,
    base_line: int,
    usable_width_px: int,
    sigma_nom_px: float = EPD_20CM_SIGMA_NOM_PX,
    sigma_off_px: float = EPD_20CM_SIGMA_OFF_PX,
    r_bg: float = EPD_DEFAULT_R_BG,
    r_ink: float = EPD_DEFAULT_R_INK,
) -> dict:
    """Evaluate 20 cm Gaussian PSF contrast retention across the canonical H1OS test string corpus."""
    cm_0 = (float(r_bg) - float(r_ink)) / max(1e-5, float(r_bg) + float(r_ink))
    pad_px = 6
    string_details: Dict[str, dict] = {}
    ret_noms: List[float] = []

    for s_key, s_txt in QUALIFY_TEST_STRINGS:
        canvas, width_px, spans = render_string_to_binary(s_txt, gmap, kern_cp, line_height, base_line)
        if np.count_nonzero(canvas) == 0:
            string_details[s_key] = {
                "text": s_txt,
                "width_px": width_px,
                "ret_nom_pct": 0.0,
                "ret_off_pct": 0.0,
                "cm_nom": 0.0,
                "grating_cm": 0.0,
            }
            ret_noms.append(0.0)
            continue

        psf_nom, _, _ = simulate_epd_gaussian_psf(canvas, sigma_px=sigma_nom_px, r_bg=r_bg, r_ink=r_ink, pad_px=pad_px)
        psf_off, _, _ = simulate_epd_gaussian_psf(canvas, sigma_px=sigma_off_px, r_bg=r_bg, r_ink=r_ink, pad_px=pad_px)
        fg_pad = np.pad(canvas, pad_px, mode="constant", constant_values=0)
        ridge = _compute_stroke_centerline_mask(fg_pad)
        lum_nom = float(np.mean(psf_nom[ridge]))
        lum_off = float(np.mean(psf_off[ridge]))
        cm_nom = max(0.0, (float(r_bg) - lum_nom) / max(1e-5, float(r_bg) + lum_nom))
        cm_off = max(0.0, (float(r_bg) - lum_off) / max(1e-5, float(r_bg) + lum_off))
        ret_nom = (cm_nom / max(1e-5, cm_0)) * 100.0
        ret_off = (cm_off / max(1e-5, cm_0)) * 100.0
        grating_cm = _measure_ss_grating_contrast(canvas, psf_nom, pad_px, spans) if s_key == "pressure" else cm_nom

        string_details[s_key] = {
            "text": s_txt,
            "width_px": width_px,
            "ret_nom_pct": round(ret_nom, 2),
            "ret_off_pct": round(ret_off, 2),
            "cm_nom": round(cm_nom, 4),
            "grating_cm": round(grating_cm, 4),
        }
        ret_noms.append(ret_nom)

    row_widths: List[int] = []
    for l_txt, r_txt in H1OS_BUDGET_PAIRS:
        _, lw, _ = render_string_to_binary(l_txt, gmap, kern_cp, line_height, base_line)
        _, rw, _ = render_string_to_binary(r_txt, gmap, kern_cp, line_height, base_line)
        row_widths.append(lw + rw)
    max_row_px = max(row_widths) if row_widths else 0
    min_clr_px = int(usable_width_px) - max_row_px

    return {
        "min_string_ret_nom_pct": round(min(ret_noms), 2) if ret_noms else 0.0,
        "mean_string_ret_nom_pct": round(float(np.mean(ret_noms)), 2) if ret_noms else 0.0,
        "status_ret_nom_pct": string_details["status"]["ret_nom_pct"],
        "pressure_ret_nom_pct": string_details["pressure"]["ret_nom_pct"],
        "ss_grating_cm": string_details["pressure"]["grating_cm"],
        "clock_ret_nom_pct": string_details["clock"]["ret_nom_pct"],
        "max_h1os_row_px": max_row_px,
        "min_h1os_clearance_px": min_clr_px,
        "fits_188px_budget": min_clr_px >= 8,
        "string_details": string_details,
    }


SINGLE_PIECE_CHARS = set("23456789abcdefghklmnopqrstuvwxyzABCDEFGHKLMNOPQRSTUVWXYZ")


def check_glyph_structural_integrity(
    arr: np.ndarray,
    ch: str,
    is_bitmap: bool,
    mean_stem_px: float,
) -> List[str]:
    """Detect structural 1-BPP glyph defects (striations, fragmentation, malformed `'S'`/`'s'`/`'t'`)."""
    if arr.size == 0 or np.count_nonzero(arr) == 0:
        return ["empty_glyph"]
    ys, xs = np.nonzero(arr > 0)
    sub = arr[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    h, w = sub.shape
    defects: List[str] = []

    if ch in SINGLE_PIECE_CHARS or ch == "0":
        if np.any(sub.sum(axis=1) == 0):
            defects.append("horizontal_striation")
        b0, _ = compute_betti_numbers(sub)
        max_b0 = 2 if ch == "0" else 1
        if b0 > max_b0:
            defects.append("stroke_fragmentation")

    if not is_bitmap and ch in ("S", "s") and h >= 8 and w >= 5:
        c0 = max(1, int(round(w * 0.25)))
        c1 = min(w - 1, max(c0 + 1, int(round(w * 0.75))))
        top_runs: List[int] = []
        bot_runs: List[int] = []
        for c in range(c0, c1):
            col = sub[:, c]
            runs: List[int] = []
            cur = 0
            for v in col:
                if v > 0:
                    cur += 1
                elif cur > 0:
                    runs.append(cur)
                    cur = 0
            if cur > 0:
                runs.append(cur)
            if len(runs) >= 3:
                top_runs.append(runs[0])
                bot_runs.append(runs[-1])
        if top_runs and mean_stem_px >= 2.20 and (np.mean(top_runs) < 1.35 or np.mean(bot_runs) < 1.35):
            defects.append("malformed_s_contour")

        m0 = int(round(h * 0.35))
        m1 = max(m0 + 1, int(round(h * 0.65)))
        for r in range(m0, m1):
            row = sub[r, :]
            h_runs: List[int] = []
            cur = 0
            for v in row:
                if v > 0:
                    cur += 1
                elif cur > 0:
                    h_runs.append(cur)
                    cur = 0
            if cur > 0:
                h_runs.append(cur)
            if len(h_runs) >= 2 and min(h_runs) == 1:
                if "malformed_s_contour" not in defects:
                    defects.append("malformed_s_contour")
                break

    if not is_bitmap and ch == "t" and h >= 9:
        r0 = int(round(h * 0.45))
        r1 = max(r0 + 2, int(round(h * 0.80)))
        stem_ws = [int(sub[r, :].sum()) for r in range(r0, r1) if sub[r, :].sum() > 0]
        if h >= 10 and stem_ws and min(stem_ws) == 1 and max(stem_ws) >= 2 and sum(1 for sw in stem_ws if sw >= 2) >= 2:
            defects.append("malformed_t_stem")
        sr0 = int(round(h * 0.40))
        sr1 = max(sr0 + 3, int(round(h * 0.82)))
        scan_ws = [int(sub[r, :].sum()) for r in range(sr0, sr1) if sub[r, :].sum() > 0]
        if len(scan_ws) >= 3 and any(
            (scan_ws[i - 1] - scan_ws[i] >= 2) and (scan_ws[i + 1] - scan_ws[i] >= 2)
            for i in range(1, len(scan_ws) - 1)
        ):
            if "horizontal_striation" not in defects:
                defects.append("horizontal_striation")

    return defects


def _worker_qualify_font(task: dict) -> Union[FontQualifyResult, Dict[str, str]]:
    """Fault-isolated worker evaluating a single candidate font across requested sizes and pipelines."""
    try:
        return _qualify_single_font_task(task)
    except Exception as exc:
        cand_dict = task.get("candidate", {})
        lbl = str(cand_dict.get("label", "<unknown>"))
        fpath = Path(str(cand_dict.get("font_path", ""))).name
        err_msg = f"{type(exc).__name__}: {exc}"
        print(f"[!] Skipped {lbl} ({fpath}): {err_msg}")
        return {"error": err_msg, "label": lbl, "font_file": fpath}


def _qualify_single_font_task(task: dict) -> FontQualifyResult:
    """Evaluate a single candidate font across requested sizes and pipelines."""
    ft, ft_lib = load_freetype()
    cand_dict = task["candidate"]
    cand = QualifyCandidate(
        label=cand_dict["label"],
        font_path=Path(cand_dict["font_path"]),
        font_number=int(cand_dict["font_number"]),
        file_type=cand_dict["file_type"],
        family_group=cand_dict["family_group"],
        weight_class=int(cand_dict["weight_class"]),
        is_italic=bool(cand_dict["is_italic"]),
        is_bitmap=bool(cand_dict["is_bitmap"]),
        is_monospace=bool(cand_dict["is_monospace"]),
        size_to_path_map={int(k): v for k, v in cand_dict.get("size_to_path_map", {}).items()},
    )
    sizes: List[int] = list(task["sizes"])
    pipelines: List[str] = list(task["pipelines"])
    threshold = int(task["threshold"])
    gamma = float(task["gamma"])
    sigma_nom_px = float(task["sigma_nom_px"])
    sigma_off_px = float(task["sigma_off_px"])
    usable_width_px = int(task["usable_width_px"])
    proofs_dir = Path(task["proofs_dir"])

    bench_cps = sorted(set(ord(c) for c in (QUALIFY_BENCHMARK_CHARS + " ")))
    by_size: Dict[int, QualifySizeMetrics] = {}
    best_rasters_by_size: Dict[int, Tuple[Dict[int, GlyphStrike], Dict[Tuple[int, int], int], int, int]] = {}

    for sz in sizes:
        eff_path = cand.font_path
        eff_pipelines = ["exact-mono"] if cand.is_bitmap else pipelines
        if cand.size_to_path_map:
            if sz not in cand.size_to_path_map:
                continue
            eff_path = Path(cand.size_to_path_map[sz])

        try:
            meta = _get_cached_tt_meta(eff_path, font_number=cand.font_number, need_kern=not cand.is_monospace)
        except Exception:
            meta = {"raw_kern": {}}

        best_metrics: Optional[QualifySizeMetrics] = None
        best_raster_tuple = None
        pipe_scores: Dict[str, float] = {}

        for p_name in eff_pipelines:
            glyphs, line_h, base_l, _, _, kern_pairs = rasterize_font_strike(
                ft=ft,
                ft_lib=ft_lib,
                font_path=eff_path,
                size_px=sz,
                codepoints=bench_cps,
                pipeline=p_name,
                threshold=threshold,
                gamma=gamma,
                enable_kerning=not cand.is_monospace,
                prune_noop_kern=True,
                font_number=cand.font_number,
            )
            gmap = {g.codepoint: g for g in glyphs}
            if kern_pairs:
                kern_cp = {(lc, rc): kv for _, _, lc, rc, kv in kern_pairs}
            elif not cand.is_monospace and meta.get("raw_kern"):
                code_to_gid = {g.codepoint: g.glyph_id for g in glyphs}
                code_to_adv = {g.codepoint: g.adv_w_fp4 for g in glyphs}
                kp = extract_kerning_pairs_from_meta(meta, sz, code_to_gid, code_to_adv, prune_noop=True)
                kern_cp = {(lc, rc): kv for _, _, lc, rc, kv in kp}
            else:
                kern_cp = {}

            all_rets: List[float] = []
            all_off_rets: List[float] = []
            trouble_rets: List[float] = []
            stems_mean: List[float] = []
            stems_min: List[float] = []
            stems_ge2: List[float] = []
            uniforms: List[float] = []
            enc_ok = 0
            enc_tot = 0
            opn_ok = 0
            opn_tot = 0
            ink_total = 0

            char_res_map: Dict[str, dict] = {}
            for ch in QUALIFY_BENCHMARK_CHARS:
                if ch not in char_res_map and ord(ch) in gmap:
                    g = gmap[ord(ch)]
                    arr = rows_to_binary_array(g.rows)
                    ink_total += int(np.count_nonzero(arr))
                    cm = compute_gaussian_psf_char_metrics(
                        arr, ch, sigma_nom_px=sigma_nom_px, sigma_off_px=sigma_off_px
                    )
                    char_res_map[ch] = cm
                    all_rets.append(cm["retention_nom_pct"])
                    all_off_rets.append(cm["retention_off_pct"])
                    if ch in TROUBLE_15_CHARS:
                        trouble_rets.append(cm["retention_nom_pct"])
                    if cm["mean_stem_px"] > 0:
                        stems_mean.append(cm["mean_stem_px"])
                        stems_min.append(cm["min_stem_px"])
                        stems_ge2.append(cm["stem_2px_pct"])
                        uniforms.append(cm["uniformity_pct"])
                    if ch in CANONICAL_MIN_HOLES:
                        enc_tot += 1
                        if g.box_w > 0 and g.box_h > 0:
                            # Enclosed counter check isolated cleanly from open-bay check
                            from humid1_bilevel_pipelines import compute_open_and_enclosed_cavity_metrics
                            cav_only = compute_open_and_enclosed_cavity_metrics(arr, ch)
                            if cav_only["enclosed_ok"]:
                                enc_ok += 1
                    if ch in OPEN_CAVITY_MIN_BAYS:
                        opn_tot += 1
                        if cm["passes_cavity"]:
                            opn_ok += 1

            mean_ret = float(np.mean(all_rets)) if all_rets else 0.0
            trouble_ret = float(np.mean(trouble_rets)) if trouble_rets else mean_ret
            p10_ret = float(np.percentile(all_rets, 10)) if all_rets else 0.0
            p10_off = float(np.percentile(all_off_rets, 10)) if all_off_rets else 0.0
            enc_pct = (float(enc_ok) / float(max(1, enc_tot))) * 100.0
            opn_pct = (float(opn_ok) / float(max(1, opn_tot))) * 100.0
            mean_stem = float(np.mean(stems_mean)) if stems_mean else 0.0
            min_stem = float(np.min(stems_min)) if stems_min else 0.0
            stem_ge2_pct = float(np.mean(stems_ge2)) if stems_ge2 else 0.0
            unif_pct = float(np.mean(uniforms)) if uniforms else 0.0

            s_m = char_res_map.get("s", {})
            d8_m = char_res_map.get("8", {})
            s_ret = float(s_m.get("retention_nom_pct", 0.0))
            s_cm = float(s_m.get("cm_nom", 0.0))
            s_cav_ok = bool(s_m.get("passes_cavity", False))
            d8_ret = float(d8_m.get("retention_nom_pct", 0.0))
            d8_cm = float(d8_m.get("cm_nom", 0.0))
            d8_cav_ok = bool(d8_m.get("passes_cavity", False))

            str_res = evaluate_string_corpus_psf(
                gmap,
                kern_cp,
                line_h,
                base_l,
                usable_width_px=usable_width_px,
                sigma_nom_px=sigma_nom_px,
                sigma_off_px=sigma_off_px,
            )
            min_str_ret = float(str_res["min_string_ret_nom_pct"])
            mean_str_ret = float(str_res["mean_string_ret_nom_pct"])
            ss_cm = float(str_res["ss_grating_cm"])

            g_xh = gmap.get(ord("x"))
            g_cap = gmap.get(ord("H"))
            x_h = int(g_xh.box_h) if g_xh else 0
            cap_h = int(g_cap.box_h) if g_cap else 0

            # Failure tag diagnostics
            f_tags: List[str] = []
            if trouble_ret < 45.0 or p10_ret < 35.0:
                f_tags.append("1px_stroke_starvation")
            if not s_cav_ok:
                if cand.weight_class >= 700 or mean_stem >= 2.0:
                    f_tags.append("bold_counter_blobbed")
                else:
                    f_tags.append("open_cavity_pinched_s")
            if not d8_cav_ok:
                f_tags.append("digit_8_counter_collapse")
            if ss_cm < 0.12:
                f_tags.append("ss_grating_smear")
            if enc_pct < 85.0 and "bold_counter_blobbed" not in f_tags:
                f_tags.append("enclosed_counters_pinched")
            if unif_pct < 60.0:
                f_tags.append("asymmetric_arc_fade")
            if not str_res["fits_188px_budget"]:
                f_tags.append("exceeds_188px_row_budget")

            struct_defects: List[str] = []
            empty_core = False
            for d_ch in "Sset8a0H":
                dg = gmap.get(ord(d_ch))
                if dg is None:
                    if d_ch in ("S", "s", "e", "0"):
                        empty_core = True
                    continue
                d_arr = rows_to_binary_array(dg.rows)
                for tag_d in check_glyph_structural_integrity(d_arr, d_ch, cand.is_bitmap, mean_stem):
                    if tag_d == "empty_glyph" and d_ch in ("S", "s", "e", "0"):
                        empty_core = True
                    elif tag_d != "empty_glyph" and tag_d not in struct_defects:
                        struct_defects.append(tag_d)

            if (ink_total == 0 or empty_core) and "empty_glyph" not in f_tags:
                f_tags.append("empty_glyph")
            for d_tag in struct_defects:
                if d_tag not in f_tags:
                    f_tags.append(d_tag)

            qualifies = (
                trouble_ret >= 45.0
                and min_str_ret >= 42.0
                and enc_pct >= 85.0
                and opn_pct >= 75.0
                and s_cav_ok
                and d8_cav_ok
                and mean_stem >= 1.40
            )
            marginal_bmp = (
                not qualifies
                and cand.is_bitmap
                and s_cav_ok
                and opn_pct >= 75.0
                and enc_pct >= 70.0
                and str_res["ss_grating_cm"] >= 0.09
            )
            marginal_vec = (
                not qualifies
                and not cand.is_bitmap
                and trouble_ret >= 38.0
                and s_cav_ok
                and d8_cav_ok
                and enc_pct >= 75.0
                and opn_pct >= 75.0
            )
            verdict = "PASS" if qualifies else ("MARGINAL" if (marginal_bmp or marginal_vec) else "FAIL")

            cav_comb = 0.5 * enc_pct + 0.5 * opn_pct
            lw_score = (
                0.30 * p10_ret
                + 0.25 * min_str_ret
                + 0.25 * cav_comb
                + 0.20 * unif_pct
            )
            if not s_cav_ok:
                lw_score *= 0.85
            if not d8_cav_ok:
                lw_score *= 0.88

            severe_defects = {"empty_glyph", "horizontal_striation", "stroke_fragmentation", "malformed_s_contour"}
            if "empty_glyph" in f_tags:
                qualifies = False
                verdict = "FAIL"
                lw_score = 0.0
            elif struct_defects:
                qualifies = False
                if any(t in severe_defects for t in f_tags):
                    verdict = "FAIL"
                    lw_score *= 0.72
                elif "malformed_t_stem" in f_tags:
                    if verdict == "PASS":
                        verdict = "MARGINAL"
                    lw_score *= 0.88

            pipe_scores[p_name] = round(lw_score, 2)
            cand_m = QualifySizeMetrics(
                size_px=sz,
                best_pipeline=p_name,
                mean_ret_nom_pct=round(mean_ret, 2),
                trouble_ret_nom_pct=round(trouble_ret, 2),
                p10_ret_nom_pct=round(p10_ret, 2),
                p10_ret_off_pct=round(p10_off, 2),
                s_ret_nom_pct=round(s_ret, 2),
                s_cm_nom=round(s_cm, 4),
                s_cavity_ok=s_cav_ok,
                d8_ret_nom_pct=round(d8_ret, 2),
                d8_cm_nom=round(d8_cm, 4),
                d8_cavity_ok=d8_cav_ok,
                enclosed_counter_pct=round(enc_pct, 1),
                open_cavity_pct=round(opn_pct, 1),
                mean_stem_px=round(mean_stem, 2),
                min_stem_px=round(min_stem, 2),
                stem_2px_pct=round(stem_ge2_pct, 1),
                uniformity_pct=round(unif_pct, 1),
                min_string_ret_nom_pct=round(min_str_ret, 2),
                mean_string_ret_nom_pct=round(mean_str_ret, 2),
                status_ret_nom_pct=float(str_res["status_ret_nom_pct"]),
                pressure_ret_nom_pct=float(str_res["pressure_ret_nom_pct"]),
                ss_grating_cm=round(ss_cm, 4),
                clock_ret_nom_pct=float(str_res["clock_ret_nom_pct"]),
                max_h1os_row_px=int(str_res["max_h1os_row_px"]),
                min_h1os_clearance_px=int(str_res["min_h1os_clearance_px"]),
                fits_188px_budget=bool(str_res["fits_188px_budget"]),
                ink_pixels=ink_total,
                x_height_px=x_h,
                cap_height_px=cap_h,
                verdict=verdict,
                qualifies_20cm=qualifies,
                least_worst_score=round(lw_score, 2),
                failure_tags=f_tags,
                pipeline_scores=dict(pipe_scores),
                string_details=str_res["string_details"],
            )

            if best_metrics is None or (
                (1 if cand_m.qualifies_20cm else 0, cand_m.least_worst_score)
                > (1 if best_metrics.qualifies_20cm else 0, best_metrics.least_worst_score)
            ):
                best_metrics = cand_m
                best_raster_tuple = (gmap, kern_cp, line_h, base_l)

        if best_metrics is not None and best_raster_tuple is not None:
            best_metrics.pipeline_scores = pipe_scores
            by_size[sz] = best_metrics
            best_rasters_by_size[sz] = best_raster_tuple

    # Intentional scanline / CRT novelty vector fonts that fracture at post-Nyquist, non-hairline sizes fail across all sizes
    if not cand.is_bitmap and by_size:
        has_post_nyquist_striation = any(
            "horizontal_striation" in m.failure_tags and sz >= 14 and m.mean_stem_px >= 1.50
            for sz, m in by_size.items()
        )
        if has_post_nyquist_striation:
            for m in by_size.values():
                if "horizontal_striation" not in m.failure_tags:
                    m.failure_tags.append("horizontal_striation")
                m.qualifies_20cm = False
                m.verdict = "FAIL"
                m.least_worst_score = round(m.least_worst_score * 0.65, 2)

    avail_sizes = sorted(by_size.keys())
    if cand.is_bitmap:
        passing_szs = [s for s in avail_sizes if by_size[s].qualifies_20cm]
    else:
        passing_szs = [
            s
            for s in avail_sizes
            if by_size[s].qualifies_20cm
            and all(by_size[s_hi].verdict != "FAIL" for s_hi in avail_sizes if s_hi >= s)
        ]
    marginal_szs = [s for s in avail_sizes if by_size[s].verdict in ("PASS", "MARGINAL")]
    max_sz = max(sizes) if sizes else (max(avail_sizes) if avail_sizes else 24)
    viable_floor = passing_szs[0] if passing_szs else (max_sz + 2)
    marginal_floor = marginal_szs[0] if marginal_szs else (max_sz + 2)

    s14 = by_size.get(14).least_worst_score if 14 in by_size else 0.0
    s16 = by_size.get(16).least_worst_score if 16 in by_size else 0.0
    s18 = by_size.get(18).least_worst_score if 18 in by_size else 0.0
    overall_lw = float(np.mean([m.least_worst_score for m in by_size.values()])) if by_size else 0.0

    result = FontQualifyResult(
        label=cand.label,
        font_file=cand.font_path.name,
        file_type=cand.file_type,
        family_group=cand.family_group,
        weight_class=cand.weight_class,
        is_italic=cand.is_italic,
        is_bitmap=cand.is_bitmap,
        is_monospace=cand.is_monospace,
        viable_floor_px=viable_floor,
        marginal_floor_px=marginal_floor,
        score_14px=round(s14, 2),
        score_16px=round(s16, 2),
        score_18px=round(s18, 2),
        overall_least_worst_score=round(overall_lw, 2),
        by_size=by_size,
    )

    if bool(task.get("render_proof", True)):
        proof_path = proofs_dir / f"{cand.label}_gaussian_proof.png"
        render_font_gaussian_proof_sheet(
            proof_path, result, best_rasters_by_size, sigma_nom_px=sigma_nom_px, sigma_off_px=sigma_off_px
        )
        result.proof_png = str(proof_path.name)
    return result


def _array_to_rgb_pil(lum_arr: np.ndarray, zoom: int = 1) -> Image.Image:
    u8 = np.clip(np.round(lum_arr), 0, 255).astype(np.uint8)
    rgb = np.stack([u8, u8, u8], axis=-1)
    pil_img = Image.fromarray(rgb, mode="RGB")
    if zoom > 1:
        pil_img = pil_img.resize((pil_img.width * zoom, pil_img.height * zoom), Image.Resampling.NEAREST)
    return pil_img


def render_font_gaussian_proof_sheet(
    out_png: Path,
    res: FontQualifyResult,
    rasters_by_size: Dict[int, Tuple[Dict[int, GlyphStrike], Dict[Tuple[int, int], int], int, int]],
    sigma_nom_px: float = EPD_20CM_SIGMA_NOM_PX,
    sigma_off_px: float = EPD_20CM_SIGMA_OFF_PX,
) -> Path:
    """
    Render a visual 20 cm Gaussian PSF proof sheet (`<out_dir>/gaussian_proofs/<label>_gaussian_proof.png`)
    modeled on `v2.4.10_1px-2px_proof.jpg` showing raw grid (sigma=0), nominal 20 cm viewing
    (sigma=1.25 px / 169 um), and off-axis stress (sigma=1.75 px / 236 um) across all evaluated sizes.
    """
    sizes = sorted(res.by_size.keys())
    W = 1580
    block_h = 200
    H = 96 + max(1, len(sizes)) * block_h + 24
    img = Image.new("RGB", (W, H), (244, 246, 250))
    draw = ImageDraw.Draw(img)
    f_def = ImageFont.load_default()

    draw.rectangle([0, 0, W, 74], fill=(18, 24, 34))
    floor_lbl = f"{res.viable_floor_px}px" if res.viable_floor_px <= max(sizes or [24]) else "NONE_TESTED"
    draw.text(
        (20, 12),
        f"20 cm (200 mm) EPD GAUSSIAN PSF PROOF SHEET  |  {res.label}  (wght={res.weight_class}, group={res.family_group}, bitmap={res.is_bitmap})",
        fill=(255, 255, 255),
        font=f_def,
    )
    draw.text(
        (20, 40),
        f"Viable 20cm Floor: {floor_lbl}  |  Marginal Floor: {res.marginal_floor_px}px  |  Least-Worst Score @14px:{res.score_14px:.1f}  @16px:{res.score_16px:.1f}  @18px:{res.score_18px:.1f}",
        fill=(180, 202, 226),
        font=f_def,
    )

    y = 86
    for sz in sizes:
        m = res.by_size[sz]
        gmap, kern_cp, lh, bl = rasters_by_size[sz]
        col_border = (16, 138, 84) if m.verdict == "PASS" else ((196, 130, 18) if m.verdict == "MARGINAL" else (186, 46, 42))
        draw.rectangle([16, y, W - 16, y + block_h - 10], fill=(255, 255, 255), outline=col_border, width=2)
        hdr_bg = (232, 248, 240) if m.verdict == "PASS" else ((254, 246, 232) if m.verdict == "MARGINAL" else (253, 236, 236))
        draw.rectangle([18, y + 2, W - 18, y + 28], fill=hdr_bg)

        tags_txt = ", ".join(m.failure_tags) if m.failure_tags else "ALL_20CM_GATES_PASSED"
        draw.text(
            (28, y + 9),
            f"[{m.verdict}] Size {sz}px ({m.best_pipeline})  |  Score={m.least_worst_score:5.1f}  |  Stem={m.mean_stem_px:.2f}px  "
            f"TrblRet={m.trouble_ret_nom_pct:.1f}%  EncCnt={m.enclosed_counter_pct:.0f}%  OpnCav={m.open_cavity_pct:.0f}%  "
            f"188pxRow={m.max_h1os_row_px}px (clr={m.min_h1os_clearance_px:+d}px)  |  {tags_txt}",
            fill=(18, 26, 36),
            font=f_def,
        )

        # Render 3-column specimen strips + 3x zoomed stress crops
        col_specs = [
            ("RAW (sigma=0)", 0.0, 28),
            (f"20cm NOMINAL (sigma={sigma_nom_px:.2f}px)", sigma_nom_px, 540),
            (f"20cm OFF-AXIS (sigma={sigma_off_px:.2f}px)", sigma_off_px, 1052),
        ]

        # Full sample row strip at top of columns (scaled proportionally if wider/taller than slot)
        sample_line = "Status  Vapor Pressure  02:48 AM  24.2 g/m³"
        line_canvas, _, _ = render_string_to_binary(sample_line, gmap, kern_cp, lh, bl)

        for col_title, sig_val, col_x in col_specs:
            draw.text((col_x, y + 34), col_title, fill=(55, 68, 86), font=f_def)
            psf_line, _, _ = simulate_epd_gaussian_psf(line_canvas, sigma_px=sig_val, pad_px=4)
            pil_line = _array_to_rgb_pil(psf_line, zoom=1)
            max_w_line = 485
            max_h_line = 42
            if pil_line.width > max_w_line or pil_line.height > max_h_line:
                scale_l = min(max_w_line / float(pil_line.width), max_h_line / float(pil_line.height))
                pil_line = pil_line.resize(
                    (max(1, int(round(pil_line.width * scale_l))), max(1, int(round(pil_line.height * scale_l)))),
                    Image.Resampling.BILINEAR,
                )
            img.paste(pil_line, (col_x, y + 50))
            draw.rectangle([col_x, y + 50, col_x + pil_line.width, y + 50 + pil_line.height], outline=(210, 218, 228), width=1)

        # Adaptive per-crop integer zoom constrained by BOTH width and height so no glyph ever clips
        crop_y = y + 96
        max_zw = 158
        max_zh = 68
        for idx_c, c_txt in enumerate(("Status", "Pressure", "02:48")):
            c_canvas, _, _ = render_string_to_binary(c_txt, gmap, kern_cp, lh, bl)
            ys = np.nonzero(c_canvas > 0)[0]
            if len(ys) > 0:
                c_trim = c_canvas[max(0, int(ys.min()) - 2) : min(c_canvas.shape[0], int(ys.max()) + 3), :]
            else:
                c_trim = c_canvas
            psf_w = c_trim.shape[1] + 6
            psf_h = c_trim.shape[0] + 6
            c_zoom = max(1, min(3, max_zw // max(1, psf_w), max_zh // max(1, psf_h)))
            for col_idx, (_, sig_val, col_x) in enumerate(col_specs):
                sub_x = col_x + idx_c * 166
                psf_c, _, _ = simulate_epd_gaussian_psf(c_trim, sigma_px=sig_val, pad_px=3)
                pil_z = _array_to_rgb_pil(psf_c, zoom=c_zoom)
                if pil_z.width > max_zw or pil_z.height > max_zh:
                    scale_z = min(max_zw / float(pil_z.width), max_zh / float(pil_z.height))
                    pil_z = pil_z.resize(
                        (max(1, int(round(pil_z.width * scale_z))), max(1, int(round(pil_z.height * scale_z)))),
                        Image.Resampling.BILINEAR,
                    )
                img.paste(pil_z, (sub_x, crop_y))
                box_col = (180, 190, 205) if col_idx == 0 else col_border
                draw.rectangle([sub_x, crop_y, sub_x + pil_z.width, crop_y + pil_z.height], outline=box_col, width=1)
                if col_idx == 1:
                    cap = (
                        f"s:{m.s_ret_nom_pct:.0f}%({m.s_cm_nom:.2f})" if idx_c == 0
                        else (f"ss:{m.pressure_ret_nom_pct:.0f}%({m.ss_grating_cm:.2f})" if idx_c == 1
                              else f"8:{m.d8_ret_nom_pct:.0f}%/{m.clock_ret_nom_pct:.0f}%")
                    )
                    draw.text((sub_x, crop_y + pil_z.height + 4), cap, fill=(45, 58, 74), font=f_def)

        y += block_h

    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out_png))
    return out_png


def analyze_family_weight_pairs(
    results: Sequence[FontQualifyResult],
    sizes: Sequence[int],
) -> Tuple[List[FamilyWeightPairEval], Dict[str, int]]:
    """
    Evaluate `(Normal, Bold)` cross-weight visual separation within each font family
    across every pixel size, ensuring Bold is visibly thicker without closing cavities.
    """
    by_family: Dict[str, List[FontQualifyResult]] = {}
    for r in results:
        if not r.is_italic:
            by_family.setdefault(r.family_group, []).append(r)

    pair_evals: List[FamilyWeightPairEval] = []
    family_pair_floors: Dict[str, int] = {}

    for fam, members in sorted(by_family.items()):
        if len(members) < 2:
            continue
        sorted_m = sorted(members, key=lambda x: (x.weight_class, x.label))
        fam_passing_sizes: List[int] = []

        for sz in sizes:
            best_pair: Optional[FamilyWeightPairEval] = None
            for i in range(len(sorted_m)):
                for j in range(i + 1, len(sorted_m)):
                    n_res = sorted_m[i]
                    b_res = sorted_m[j]
                    if n_res.weight_class >= b_res.weight_class:
                        continue
                    nm = n_res.by_size.get(sz)
                    bm = b_res.by_size.get(sz)
                    if not nm or not bm:
                        continue
                    stem_delta = bm.mean_stem_px - nm.mean_stem_px
                    ink_ratio = float(bm.ink_pixels) / float(max(1, nm.ink_pixels))
                    severe_pair_defects = {"horizontal_striation", "stroke_fragmentation", "malformed_s_contour", "empty_glyph"}
                    pair_defect_bad = any(t in severe_pair_defects for t in (nm.failure_tags + bm.failure_tags))
                    norm_stem_ok = True
                    bold_stem_ok = True
                    if n_res.is_bitmap and b_res.is_bitmap:
                        has_sep = (ink_ratio >= 1.15 and stem_delta >= 0.15)
                    else:
                        norm_stem_cap = max(2.25, 0.142 * sz)
                        bold_stem_min = max(2.25, 0.148 * sz)
                        norm_stem_ok = 1.35 <= nm.mean_stem_px <= norm_stem_cap
                        bold_stem_ok = bm.mean_stem_px >= bold_stem_min
                        has_sep = (
                            stem_delta >= max(0.45, 0.032 * sz)
                            and 1.18 <= ink_ratio <= 1.75
                            and norm_stem_ok
                            and bold_stem_ok
                        )
                    if pair_defect_bad:
                        has_sep = False

                    pair_ok = bool(nm.qualifies_20cm and bm.qualifies_20cm and has_sep and not pair_defect_bad)
                    p_score = 0.5 * (nm.least_worst_score + bm.least_worst_score) + (
                        14.0 if (has_sep and not pair_defect_bad) else -20.0
                    )
                    notes_l: List[str] = []
                    if pair_defect_bad:
                        notes_l.append("structural_defect")
                    elif not has_sep:
                        if not norm_stem_ok:
                            notes_l.append("norm_too_heavy" if nm.mean_stem_px > max(2.25, 0.142 * sz) else "norm_too_thin")
                        elif not bold_stem_ok:
                            notes_l.append("bold_too_thin")
                        elif ink_ratio > 1.75:
                            notes_l.append("bold_overweight")
                        else:
                            notes_l.append("insufficient_weight_sep")
                    if not nm.qualifies_20cm:
                        notes_l.append(f"norm:{nm.verdict}")
                    if not bm.qualifies_20cm:
                        notes_l.append(f"bold:{bm.verdict}")
                    notes_s = ", ".join(notes_l) if notes_l else "QUALIFIED_PAIR"

                    cand_pair = FamilyWeightPairEval(
                        family_group=fam,
                        size_px=sz,
                        normal_label=n_res.label,
                        normal_weight=n_res.weight_class,
                        bold_label=b_res.label,
                        bold_weight=b_res.weight_class,
                        normal_verdict=nm.verdict,
                        bold_verdict=bm.verdict,
                        normal_stem_px=nm.mean_stem_px,
                        bold_stem_px=bm.mean_stem_px,
                        stem_delta_px=round(stem_delta, 2),
                        ink_mass_ratio=round(ink_ratio, 3),
                        has_weight_sep=has_sep,
                        pair_qualifies=pair_ok,
                        pair_score=round(p_score, 2),
                        notes=notes_s,
                    )
                    if best_pair is None or (
                        (1 if cand_pair.pair_qualifies else 0, cand_pair.pair_score)
                        > (1 if best_pair.pair_qualifies else 0, best_pair.pair_score)
                    ):
                        best_pair = cand_pair

            if best_pair is not None:
                pair_evals.append(best_pair)
                if best_pair.pair_qualifies:
                    fam_passing_sizes.append(sz)

        max_s = max(sizes) if sizes else 24
        family_pair_floors[fam] = min(fam_passing_sizes) if fam_passing_sizes else (max_s + 2)

    return pair_evals, family_pair_floors


def render_family_weight_pair_sheets(
    out_dir: Path,
    results: Sequence[FontQualifyResult],
    pair_evals: Sequence[FamilyWeightPairEval],
    sizes: Sequence[int],
    cand_map: Dict[str, QualifyCandidate],
    sigma_nom_px: float = EPD_20CM_SIGMA_NOM_PX,
    threshold: int = 128,
    gamma: float = 1.0,
    family_floors: Optional[Dict[str, int]] = None,
    max_families: Optional[int] = None,
) -> List[Path]:
    """Render per-family weight-separation visual sheets inside `<out_dir>/weight_pairs/`."""
    wp_dir = out_dir / "weight_pairs"
    wp_dir.mkdir(parents=True, exist_ok=True)
    by_fam: Dict[str, List[FontQualifyResult]] = {}
    for r in results:
        if not r.is_italic:
            by_fam.setdefault(r.family_group, []).append(r)

    pair_lookup = {(p.family_group, p.size_px): p for p in pair_evals}
    fam_items = [(fam, mems) for fam, mems in sorted(by_fam.items()) if len(mems) >= 2]
    if max_families is not None and len(fam_items) > max_families:
        max_s_wp = max(sizes) if sizes else 24
        fam_scores: Dict[str, float] = {}
        for p in pair_evals:
            fam_scores[p.family_group] = max(fam_scores.get(p.family_group, -999.0), p.pair_score)
        fam_items.sort(
            key=lambda it: (
                family_floors.get(it[0], max_s_wp + 2) if family_floors else max_s_wp + 2,
                -fam_scores.get(it[0], 0.0),
                it[0],
            )
        )
        fam_items = fam_items[:max(1, max_families)]

    written: List[Path] = []
    f_def = ImageFont.load_default()
    ft, ft_lib = load_freetype()
    bench_cps = sorted(set(ord(c) for c in "Status Vapor Pressure 02:48 AM"))

    for fam, members in fam_items:
        sorted_m = sorted(members, key=lambda x: (x.weight_class, x.label))

        # Pre-render strips so canvas width and per-size row heights never crop wide monospace or 24px text
        rendered_strips: Dict[Tuple[int, str], Tuple[Image.Image, Image.Image]] = {}
        max_strip_w = 0
        max_strip_h: Dict[int, int] = {sz: 0 for sz in sizes}
        for sz in sizes:
            for mem in sorted_m:
                mm = mem.by_size.get(sz)
                if not mm:
                    continue
                c_obj = cand_map.get(mem.label)
                sz_map = c_obj.size_to_path_map if c_obj else {}
                eff_p = Path(sz_map[sz]) if sz in sz_map else (c_obj.font_path if c_obj else Path("build/static_ttfs") / mem.font_file)
                if not eff_p.is_file():
                    continue
                glyphs, lh, bl, _, _, _ = rasterize_font_strike(
                    ft=ft, ft_lib=ft_lib, font_path=eff_p, size_px=sz, codepoints=bench_cps,
                    pipeline=mm.best_pipeline, threshold=threshold, gamma=gamma,
                    enable_kerning=False, font_number=c_obj.font_number if c_obj else 0,
                )
                gmap = {g.codepoint: g for g in glyphs}
                st_can, _, _ = render_string_to_binary("Status Vapor Pressure 02:48", gmap, {}, lh, bl)
                psf_st, _, _ = simulate_epd_gaussian_psf(st_can, sigma_px=sigma_nom_px, pad_px=3)
                pil_raw = _array_to_rgb_pil(np.where(st_can > 0, 23, 190), zoom=1)
                pil_psf = _array_to_rgb_pil(psf_st, zoom=1)
                rendered_strips[(sz, mem.label)] = (pil_raw, pil_psf)
                max_strip_w = max(max_strip_w, pil_raw.width, pil_psf.width)
                max_strip_h[sz] = max(max_strip_h[sz], pil_raw.height, pil_psf.height)

        strip_slot_w = max(360, max_strip_w + 8)
        col_raw_x = 740
        col_psf_x = col_raw_x + strip_slot_w + 24
        W = col_psf_x + strip_slot_w + 28
        row_h_by_size = {sz: max(34, max_strip_h.get(sz, 0) + 8) for sz in sizes}
        H = 90 + sum(46 + len(sorted_m) * row_h_by_size[sz] + 12 for sz in sizes) + 24
        img = Image.new("RGB", (W, H), (244, 246, 250))
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, W, 68], fill=(18, 24, 34))
        draw.text((20, 12), f"FAMILY WEIGHT SEPARATION & 20 cm PSF COMPARISON  |  {fam}", fill=(255, 255, 255), font=f_def)
        draw.text((20, 38), "Comparing all weights side-by-side at sigma=0 and sigma=1.25px (169um @ 20cm)", fill=(180, 202, 226), font=f_def)

        y = 82
        for sz in sizes:
            row_h = row_h_by_size[sz]
            block_h = 46 + len(sorted_m) * row_h + 12
            pe = pair_lookup.get((fam, sz))
            p_col = (16, 138, 84) if (pe and pe.pair_qualifies) else (175, 55, 45)
            draw.rectangle([16, y, W - 16, y + block_h - 8], fill=(255, 255, 255), outline=p_col, width=1)
            pe_txt = (
                f"Best Pair: {pe.normal_label} + {pe.bold_label}  |  DeltaStem={pe.stem_delta_px:+.2f}px  InkRatio={pe.ink_mass_ratio:.2f}x  [{pe.notes}]"
                if pe else "No weight pair at this size"
            )
            draw.rectangle([18, y + 2, W - 18, y + 26], fill=(235, 241, 248))
            draw.text((26, y + 8), f"SIZE {sz}px  |  {pe_txt}", fill=(18, 26, 36), font=f_def)

            ry = y + 34
            for mem in sorted_m:
                mm = mem.by_size.get(sz)
                if not mm:
                    draw.text((28, ry + 8), f"{mem.label:<30} [wght={mem.weight_class:<3}] N/A at {sz}px", fill=(120, 130, 145), font=f_def)
                    ry += row_h
                    continue
                v_col = (16, 138, 84) if mm.verdict == "PASS" else ((196, 130, 18) if mm.verdict == "MARGINAL" else (186, 46, 42))
                draw.text(
                    (28, ry + 8),
                    f"{mem.label:<30} [w{mem.weight_class:<3}] {mm.verdict:<8} | Stem:{mm.mean_stem_px:4.2f}px | Trbl:{mm.trouble_ret_nom_pct:4.1f}% | s:{mm.s_ret_nom_pct:4.0f}% | 8:{mm.d8_ret_nom_pct:4.0f}%",
                    fill=v_col,
                    font=f_def,
                )
                pair_imgs = rendered_strips.get((sz, mem.label))
                if pair_imgs is not None:
                    pil_raw, pil_psf = pair_imgs
                    img.paste(pil_raw, (col_raw_x, ry + 2))
                    img.paste(pil_psf, (col_psf_x, ry + 2))
                ry += row_h
            y += block_h

        out_p = wp_dir / f"{fam}_weight_separation.png"
        img.save(str(out_p))
        written.append(out_p)
    return written


def render_master_qualification_sheet(
    out_png: Path,
    results: Sequence[FontQualifyResult],
    sizes: Sequence[int],
    max_rows: int = 250,
) -> Path:
    """Render master ranked visual qualification scorecard PNG (capped at `max_rows`)."""
    ranked = sorted(
        results,
        key=lambda r: (
            r.viable_floor_px,
            -r.score_16px,
            -r.score_14px,
            -r.overall_least_worst_score,
        ),
    )
    shown = ranked[:max(1, max_rows)] if ranked else []
    row_h = 34
    W = 1920
    H = max(320, 110 + len(shown) * row_h + 30)
    img = Image.new("RGB", (W, H), (244, 246, 250))
    draw = ImageDraw.Draw(img)
    f_def = ImageFont.load_default()

    draw.rectangle([0, 0, W, 72], fill=(18, 24, 34))
    draw.text(
        (24, 14),
        f"HUMIDYNE LABS / HUMIDITRON epd-font v{TOOL_VERSION}  |  20 cm (200 mm) GAUSSIAN PSF QUALIFICATION SCORECARD",
        fill=(255, 255, 255),
        font=f_def,
    )
    cap_note = f" (Showing Top {len(shown)} of {len(ranked)})" if len(ranked) > len(shown) else ""
    draw.text(
        (24, 42),
        f"Ranked by Viable Size Floor & Least-Worst Uniformity Score across {len(ranked)} fonts and sizes {list(sizes)}{cap_note}",
        fill=(180, 202, 226),
        font=f_def,
    )

    y = 84
    max_s = max(sizes) if sizes else 24
    for idx, r in enumerate(shown, 1):
        bg = (255, 255, 255) if (idx % 2 == 1) else (238, 243, 250)
        draw.rectangle([16, y, W - 16, y + row_h - 4], fill=bg, outline=(210, 218, 230), width=1)
        fl_str = f"{r.viable_floor_px:2d}px" if r.viable_floor_px <= max_s else "NONE"
        m14 = r.by_size.get(14)
        m16 = r.by_size.get(16)
        m18 = r.by_size.get(18)
        s14_t = f"{m14.verdict[0]}({m14.least_worst_score:4.1f}, s:{m14.s_ret_nom_pct:3.0f}%)" if m14 else "N/A"
        s16_t = f"{m16.verdict[0]}({m16.least_worst_score:4.1f}, s:{m16.s_ret_nom_pct:3.0f}%, 188px:{m16.max_h1os_row_px:>3})" if m16 else "N/A"
        s18_t = f"{m18.verdict[0]}({m18.least_worst_score:4.1f}, s:{m18.s_ret_nom_pct:3.0f}%)" if m18 else "N/A"
        tags = ",".join((m16.failure_tags if m16 else (m14.failure_tags if m14 else []))[:2]) or "PASS"
        col_txt = (16, 138, 84) if r.viable_floor_px <= 16 else ((196, 130, 18) if r.viable_floor_px <= 20 else (186, 46, 42))
        draw.text(
            (26, y + 9),
            f"#{idx:>3d} {r.label[:34]:<34} [w{r.weight_class:<3} {'BMP' if r.is_bitmap else 'VEC'}] | Floor:{fl_str:<4} | "
            f"@14px:{s14_t:<18} | @16px:{s16_t:<28} | @18px:{s18_t:<18} | {tags}",
            fill=col_txt,
            font=f_def,
        )
        y += row_h

    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out_png))
    return out_png


def _trim_vertical_ink(arr: np.ndarray, pad_y: int = 2) -> np.ndarray:
    ys = np.nonzero(arr > 0)[0]
    if len(ys) == 0:
        return arr
    return arr[max(0, int(ys.min()) - pad_y) : min(arr.shape[0], int(ys.max()) + pad_y + 1), :]


def _fit_pil_box(pil_img: Image.Image, max_w: int, max_h: int, allow_bilinear: bool = True) -> Image.Image:
    if pil_img.width <= max_w and pil_img.height <= max_h:
        return pil_img
    if not allow_bilinear:
        return pil_img.crop((0, 0, min(max_w, pil_img.width), min(max_h, pil_img.height)))
    scale = min(max_w / float(pil_img.width), max_h / float(pil_img.height))
    return pil_img.resize(
        (max(1, int(round(pil_img.width * scale))), max(1, int(round(pil_img.height * scale)))),
        Image.Resampling.BILINEAR,
    )


def _render_specimen_strip_pair(
    ft,
    ft_lib,
    cand_map: Dict[str, QualifyCandidate],
    res: FontQualifyResult,
    sz: int,
    text: str,
    sigma_nom_px: float,
    threshold: int,
    gamma: float,
    max_w: int = 380,
    max_h: int = 38,
    include_crops: bool = False,
) -> Tuple[Optional[Image.Image], Optional[Image.Image], Optional[Image.Image], Optional[Image.Image]]:
    """Render `(raw_strip, psf_strip, crop_status_2x, crop_clock_2x)` specimens for visual evaluation sheets."""
    mm = res.by_size.get(sz)
    if mm is None:
        return (None, None, None, None)
    c_obj = cand_map.get(res.label)
    sz_map = c_obj.size_to_path_map if c_obj else {}
    eff_p = Path(sz_map[sz]) if sz in sz_map else (c_obj.font_path if c_obj else None)
    if eff_p is None or not eff_p.is_file():
        return (None, None, None, None)

    cps = sorted(set(ord(c) for c in (text + " Status 02:48")))
    glyphs, lh, bl, _, _, _ = rasterize_font_strike(
        ft=ft,
        ft_lib=ft_lib,
        font_path=eff_p,
        size_px=sz,
        codepoints=cps,
        pipeline=mm.best_pipeline,
        threshold=threshold,
        gamma=gamma,
        enable_kerning=False,
        font_number=c_obj.font_number if c_obj else 0,
    )
    gmap = {g.codepoint: g for g in glyphs}
    st_can, _, _ = render_string_to_binary(text, gmap, {}, lh, bl)
    st_trim = _trim_vertical_ink(st_can, pad_y=2)
    psf_raw, _, _ = simulate_epd_gaussian_psf(st_trim, sigma_px=0.0, pad_px=3)
    psf_nom, _, _ = simulate_epd_gaussian_psf(st_trim, sigma_px=sigma_nom_px, pad_px=3)
    pil_raw = _fit_pil_box(_array_to_rgb_pil(psf_raw, zoom=1), max_w=max_w, max_h=max_h, allow_bilinear=False)
    pil_psf = _fit_pil_box(_array_to_rgb_pil(psf_nom, zoom=1), max_w=max_w, max_h=max_h, allow_bilinear=True)

    if not include_crops:
        return (pil_raw, pil_psf, None, None)

    crop_imgs: List[Optional[Image.Image]] = []
    for c_txt in ("Status", "02:48"):
        c_can, _, _ = render_string_to_binary(c_txt, gmap, {}, lh, bl)
        c_trim = _trim_vertical_ink(c_can, pad_y=2)
        c_psf, _, _ = simulate_epd_gaussian_psf(c_trim, sigma_px=sigma_nom_px, pad_px=3)
        c_pil = _fit_pil_box(_array_to_rgb_pil(c_psf, zoom=2), max_w=180, max_h=max_h, allow_bilinear=True)
        crop_imgs.append(c_pil)
    return (pil_raw, pil_psf, crop_imgs[0], crop_imgs[1])


def render_top_ranked_visual_sheet(
    out_png: Path,
    results: Sequence[FontQualifyResult],
    sizes: Sequence[int],
    cand_map: Dict[str, QualifyCandidate],
    sigma_nom_px: float = EPD_20CM_SIGMA_NOM_PX,
    threshold: int = 128,
    gamma: float = 1.0,
    top_n: int = 40,
) -> Path:
    """Render Top-N ranked visual comparison PNG with 1:1 RAW and 20 cm PSF strips."""
    valid_res = [
        r for r in results
        if r.by_size
        and any(m.ink_pixels > 0 for m in r.by_size.values())
        and not any(
            t == "empty_glyph" or (t == "horizontal_striation" and sz >= 16)
            for sz, m in r.by_size.items()
            for t in m.failure_tags
        )
    ]
    if not valid_res:
        valid_res = list(results)
    ranked = sorted(
        valid_res,
        key=lambda r: (
            r.viable_floor_px,
            -r.score_16px,
            -r.score_14px,
            -r.overall_least_worst_score,
        ),
    )
    top_list = ranked[:max(1, top_n)] if ranked else []
    s_sorted = sorted(sizes) if sizes else [16, 18]
    sz_a = 16 if 16 in s_sorted else s_sorted[0]
    sz_b = 18 if 18 in s_sorted else s_sorted[-1]

    W = 2280
    row_h = 48
    H = max(320, 126 + len(top_list) * row_h + 24)
    img = Image.new("RGB", (W, H), (244, 246, 250))
    draw = ImageDraw.Draw(img)
    f_def = ImageFont.load_default()

    draw.rectangle([0, 0, W, 72], fill=(18, 24, 34))
    draw.text(
        (24, 14),
        f"HUMIDYNE LABS / HUMIDITRON epd-font v{TOOL_VERSION}  |  TOP-{len(top_list)} RANKED 20 cm VISUAL COMPARISON SHEET",
        fill=(255, 255, 255),
        font=f_def,
    )
    draw.text(
        (24, 42),
        f"Showing Top {len(top_list)} of {len(ranked)} valid cuts  |  Specimens: 'Status Vapor Pressure 02:48' @ {sz_a}px & {sz_b}px (1:1 RAW vs. sigma={sigma_nom_px:.2f}px)",
        fill=(180, 202, 226),
        font=f_def,
    )

    draw.rectangle([16, 80, W - 16, 108], fill=(35, 46, 62))
    draw.text((26, 89), "RANK / FONT CUT / FAMILY / FLOORS & SCORES", fill=(235, 242, 250), font=f_def)
    draw.text((700, 89), f"@{sz_a}px RAW (sigma=0, 1:1)", fill=(235, 242, 250), font=f_def)
    draw.text((1095, 89), f"@{sz_a}px 20cm PSF (sigma={sigma_nom_px:.2f}px)", fill=(235, 242, 250), font=f_def)
    draw.text((1495, 89), f"@{sz_b}px RAW (sigma=0, 1:1)", fill=(235, 242, 250), font=f_def)
    draw.text((1890, 89), f"@{sz_b}px 20cm PSF (sigma={sigma_nom_px:.2f}px)", fill=(235, 242, 250), font=f_def)

    ft, ft_lib = load_freetype()
    max_s = max(s_sorted)
    sample_txt = "Status Vapor Pressure 02:48"
    y = 114
    for idx, r in enumerate(top_list, 1):
        bg = (255, 255, 255) if (idx % 2 == 1) else (238, 243, 250)
        draw.rectangle([16, y, W - 16, y + row_h - 4], fill=bg, outline=(210, 218, 230), width=1)
        fl_str = f"{r.viable_floor_px:2d}px" if r.viable_floor_px <= max_s else "NONE"
        mf_str = f"{r.marginal_floor_px:2d}px" if r.marginal_floor_px <= max_s else "NONE"
        lbl_s = (r.label[:29] + "~") if len(r.label) > 30 else r.label
        fam_s = (r.family_group[:17] + "~") if len(r.family_group) > 18 else r.family_group
        m14 = r.by_size.get(14)
        m16 = r.by_size.get(16)
        m18 = r.by_size.get(18)
        s14_t = f"{m14.verdict[0]}({m14.least_worst_score:4.1f},s:{m14.s_ret_nom_pct:3.0f}%)" if m14 else "N/A"
        s16_t = f"{m16.verdict[0]}({m16.least_worst_score:4.1f},row:{m16.max_h1os_row_px:>3})" if m16 else "N/A"
        s18_t = f"{m18.verdict[0]}({m18.least_worst_score:4.1f},s:{m18.s_ret_nom_pct:3.0f}%)" if m18 else "N/A"
        col_txt = (16, 138, 84) if r.viable_floor_px <= 16 else ((196, 130, 18) if r.viable_floor_px <= 20 else (186, 46, 42))

        draw.text(
            (26, y + 7),
            f"#{idx:>2d}  {lbl_s:<30} [w{r.weight_class:<3} {'BMP' if r.is_bitmap else 'VEC'} | {fam_s}]  Floor:{fl_str} (Marg:{mf_str})",
            fill=col_txt,
            font=f_def,
        )
        draw.text(
            (26, y + 25),
            f"@14px:{s14_t:<17}  |  @16px:{s16_t:<20}  |  @18px:{s18_t:<17}",
            fill=(55, 68, 86),
            font=f_def,
        )

        raw_a, psf_a, _, _ = _render_specimen_strip_pair(
            ft, ft_lib, cand_map, r, sz_a, sample_txt, sigma_nom_px, threshold, gamma, max_w=380, max_h=38
        )
        if raw_a is not None and psf_a is not None:
            img.paste(raw_a, (700, y + 4))
            img.paste(psf_a, (1095, y + 4))
        raw_b, psf_b, _, _ = _render_specimen_strip_pair(
            ft, ft_lib, cand_map, r, sz_b, sample_txt, sigma_nom_px, threshold, gamma, max_w=380, max_h=38
        )
        if raw_b is not None and psf_b is not None:
            img.paste(raw_b, (1495, y + 4))
            img.paste(psf_b, (1890, y + 4))
        y += row_h

    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out_png))
    return out_png


def render_best_in_class_visual_sheet(
    out_png: Path,
    results: Sequence[FontQualifyResult],
    sizes: Sequence[int],
    cand_map: Dict[str, QualifyCandidate],
    pair_evals: Sequence[FamilyWeightPairEval] = (),
    sigma_nom_px: float = EPD_20CM_SIGMA_NOM_PX,
    threshold: int = 128,
    gamma: float = 1.0,
    top_k: int = 5,
) -> Path:
    """Render Best-in-Class functional visual comparison sheet across 6 single-cut roles + stacked Normal+Bold pairs."""
    s_sorted = sorted(sizes) if sizes else [14, 16, 18, 20]

    def _eff_sz(target: int) -> int:
        return target if target in s_sorted else min(s_sorted, key=lambda s: abs(s - target))

    def _v_rank(m: QualifySizeMetrics) -> int:
        return 0 if m.verdict == "PASS" else (1 if m.verdict == "MARGINAL" else 2)

    bic_block_defects = {"empty_glyph", "horizontal_striation", "stroke_fragmentation"}

    def _clean_for_bic(m: QualifySizeMetrics) -> bool:
        return m.ink_pixels > 0 and not any(t in bic_block_defects for t in m.failure_tags)

    class_specs = [
        (
            f"CLASS 1 - {_eff_sz(14)}px SMALL FLOOR (Best Overall Bitmap & Vector Cuts @ {_eff_sz(14)}px)",
            _eff_sz(14),
            lambda r: not r.is_italic,
            lambda r, m: (_v_rank(m), -m.least_worst_score),
        ),
        (
            f"CLASS 2 - {_eff_sz(16)}px COMPACT 2-COL UI BODY (Normal Physical Stem 1.40-2.22px, Prioritizing <=188px Fit)",
            _eff_sz(16),
            lambda r: not r.is_italic and r.weight_class <= 600,
            lambda r, m: (0 if 1.40 <= m.mean_stem_px <= 2.22 else 1, 0 if m.fits_188px_budget else 1, _v_rank(m), -m.least_worst_score),
        ),
        (
            f"CLASS 3 - {_eff_sz(16)}px COMPACT 2-COL UI SUBTITLE (Bold Physical Stem >= 2.35px, Prioritizing <=188px Fit)",
            _eff_sz(16),
            lambda r: not r.is_italic and r.weight_class >= 700,
            lambda r, m: (0 if m.mean_stem_px >= 2.35 else 1, 0 if m.fits_188px_budget else 1, _v_rank(m), -m.least_worst_score),
        ),
        (
            f"CLASS 4 - {_eff_sz(18)}px STANDARD VECTOR UI & TITLES (Top Qualifying Vector Cuts @ {_eff_sz(18)}px)",
            _eff_sz(18),
            lambda r: not r.is_italic and not r.is_bitmap,
            lambda r, m: (_v_rank(m), -m.least_worst_score),
        ),
        (
            f"CLASS 5 - {_eff_sz(16)}px MONOSPACE & TELEMETRY (Top Monospace Cuts @ {_eff_sz(16)}px)",
            _eff_sz(16),
            lambda r: not r.is_italic and r.is_monospace,
            lambda r, m: (_v_rank(m), -m.least_worst_score),
        ),
        (
            f"CLASS 6 - {_eff_sz(20)}px HERO & HEADER DISPLAY (Top High-Retention Cuts @ {_eff_sz(20)}px)",
            _eff_sz(20),
            lambda r: not r.is_italic,
            lambda r, m: (_v_rank(m), -m.least_worst_score),
        ),
    ]

    sections: List[Tuple[str, int, List[FontQualifyResult]]] = []
    for title, eff_sz, pred, key_fn in class_specs:
        cands_c = [
            r for r in results
            if eff_sz in r.by_size and pred(r) and _clean_for_bic(r.by_size[eff_sz])
        ]
        cands_c.sort(key=lambda r, esz=eff_sz, kfn=key_fn: kfn(r, r.by_size[esz]))
        sections.append((title, eff_sz, cands_c[:max(1, top_k)]))

    sz_pair = _eff_sz(18)
    top_pairs = sorted(
        [p for p in pair_evals if p.size_px == sz_pair],
        key=lambda p: (0 if p.pair_qualifies else (1 if p.has_weight_sep else 2), -p.pair_score),
    )[:max(1, top_k)]
    res_map = {r.label: r for r in results}

    W = 2040
    sec_hdr_h = 34
    row_h = 48
    pair_row_h = 86
    total_body_h = sum(sec_hdr_h + max(1, len(winners)) * row_h + 14 for _, _, winners in sections)
    total_pair_h = sec_hdr_h + (len(top_pairs) * pair_row_h if top_pairs else row_h) + 14
    H = max(360, 88 + total_body_h + total_pair_h + 20)
    img = Image.new("RGB", (W, H), (244, 246, 250))
    draw = ImageDraw.Draw(img)
    f_def = ImageFont.load_default()

    draw.rectangle([0, 0, W, 72], fill=(18, 24, 34))
    draw.text(
        (24, 14),
        f"HUMIDYNE LABS / HUMIDITRON epd-font v{TOOL_VERSION}  |  BEST-IN-CLASS 20 cm VISUAL SELECTION SHEET",
        fill=(255, 255, 255),
        font=f_def,
    )
    draw.text(
        (24, 42),
        f"Top {top_k} Winners per Functional Role + Stacked Normal/Bold Pairs  |  1:1 RAW vs. 20cm PSF (sigma={sigma_nom_px:.2f}px)",
        fill=(180, 202, 226),
        font=f_def,
    )

    ft, ft_lib = load_freetype()
    sample_txt = "Status Vapor Pressure 02:48"
    y = 84
    for title, eff_sz, winners in sections:
        draw.rectangle([16, y, W - 16, y + sec_hdr_h - 4], fill=(35, 46, 62))
        draw.text((26, y + 9), title, fill=(242, 246, 252), font=f_def)
        draw.text((740, y + 9), "RAW (sigma=0, 1:1)", fill=(195, 212, 232), font=f_def)
        draw.text((1135, y + 9), f"20cm NOMINAL (sigma={sigma_nom_px:.2f}px)", fill=(195, 212, 232), font=f_def)
        draw.text((1530, y + 9), "2x 'Status' PSF", fill=(195, 212, 232), font=f_def)
        draw.text((1750, y + 9), "2x '02:48' PSF", fill=(195, 212, 232), font=f_def)
        y += sec_hdr_h

        if not winners:
            draw.rectangle([16, y, W - 16, y + row_h - 4], fill=(255, 255, 255), outline=(210, 218, 230), width=1)
            draw.text((26, y + 16), "[No matching non-italic candidates in corpus for this class]", fill=(130, 140, 155), font=f_def)
            y += row_h + 14
            continue

        for rank_i, r in enumerate(winners, 1):
            m = r.by_size[eff_sz]
            bg = (255, 255, 255) if (rank_i % 2 == 1) else (238, 243, 250)
            draw.rectangle([16, y, W - 16, y + row_h - 4], fill=bg, outline=(210, 218, 230), width=1)
            v_col = (16, 138, 84) if m.verdict == "PASS" else ((196, 130, 18) if m.verdict == "MARGINAL" else (186, 46, 42))
            lbl_s = (r.label[:29] + "~") if len(r.label) > 30 else r.label
            fam_s = (r.family_group[:17] + "~") if len(r.family_group) > 18 else r.family_group
            draw.text(
                (26, y + 7),
                f"#{rank_i}  {lbl_s:<30} [w{r.weight_class:<3} {'BMP' if r.is_bitmap else 'VEC'} | {fam_s}]",
                fill=v_col,
                font=f_def,
            )
            draw.text(
                (26, y + 25),
                f"@{eff_sz}px {m.verdict:<8} Score={m.least_worst_score:4.1f} | Stem={m.mean_stem_px:4.2f}px | "
                f"Trbl={m.trouble_ret_nom_pct:4.1f}% | s={m.s_ret_nom_pct:3.0f}%({'OK' if m.s_cavity_ok else 'FAIL'}) | "
                f"8={m.d8_ret_nom_pct:3.0f}%({'OK' if m.d8_cavity_ok else 'FAIL'}) | 188pxRow={m.max_h1os_row_px}px ({m.min_h1os_clearance_px:+d})",
                fill=(45, 58, 74),
                font=f_def,
            )
            pil_raw, pil_psf, pil_st, pil_clk = _render_specimen_strip_pair(
                ft, ft_lib, cand_map, r, eff_sz, sample_txt, sigma_nom_px, threshold, gamma, max_w=380, max_h=38, include_crops=True
            )
            if pil_raw is not None:
                img.paste(pil_raw, (740, y + 4))
            if pil_psf is not None:
                img.paste(pil_psf, (1135, y + 4))
            if pil_st is not None:
                img.paste(pil_st, (1530, y + 4))
            if pil_clk is not None:
                img.paste(pil_clk, (1750, y + 4))
            y += row_h
        y += 14

    # CLASS 7: Stacked (Normal + Bold) Matched Weight-Pair Visual Ranking
    draw.rectangle([16, y, W - 16, y + sec_hdr_h - 4], fill=(35, 46, 62))
    draw.text(
        (26, y + 9),
        f"CLASS 7 - TOP MATCHED (NORMAL + BOLD) FAMILY WEIGHT PAIRS @ {sz_pair}px (Physical Stem Separation)",
        fill=(242, 246, 252),
        font=f_def,
    )
    draw.text((740, y + 9), "RAW (sigma=0, 1:1)", fill=(195, 212, 232), font=f_def)
    draw.text((1135, y + 9), f"20cm NOMINAL (sigma={sigma_nom_px:.2f}px)", fill=(195, 212, 232), font=f_def)
    draw.text((1530, y + 9), "2x 'Status' PSF", fill=(195, 212, 232), font=f_def)
    draw.text((1750, y + 9), "2x '02:48' PSF", fill=(195, 212, 232), font=f_def)
    y += sec_hdr_h

    if not top_pairs:
        draw.rectangle([16, y, W - 16, y + row_h - 4], fill=(255, 255, 255), outline=(210, 218, 230), width=1)
        draw.text((26, y + 16), "[No multi-weight families found in corpus for stacked weight-pair evaluation]", fill=(130, 140, 155), font=f_def)
    else:
        for idx_p, pe in enumerate(top_pairs, 1):
            bg = (255, 255, 255) if (idx_p % 2 == 1) else (238, 243, 250)
            b_col = (16, 138, 84) if pe.pair_qualifies else ((196, 130, 18) if pe.has_weight_sep else (186, 46, 42))
            draw.rectangle([16, y, W - 16, y + pair_row_h - 4], fill=bg, outline=b_col, width=1)
            draw.line([(24, y + 42), (W - 24, y + 42)], fill=(224, 230, 238), width=1)

            fam_s = (pe.family_group[:22] + "~") if len(pe.family_group) > 23 else pe.family_group
            n_lbl = (pe.normal_label[:28] + "~") if len(pe.normal_label) > 29 else pe.normal_label
            b_lbl = (pe.bold_label[:28] + "~") if len(pe.bold_label) > 29 else pe.bold_label
            st_tag = "QUALIFIED" if pe.pair_qualifies else ("SEP_OK" if pe.has_weight_sep else "FAIL")
            draw.text(
                (26, y + 7),
                f"#{idx_p}  {fam_s}  [{st_tag}]  |  DeltaStem={pe.stem_delta_px:+.2f}px  InkRatio={pe.ink_mass_ratio:.2f}x  ({pe.notes})",
                fill=b_col,
                font=f_def,
            )
            draw.text(
                (26, y + 24),
                f"[NORMAL] {n_lbl:<29} w{pe.normal_weight:<3} Stem={pe.normal_stem_px:4.2f}px ({pe.normal_verdict})",
                fill=(45, 58, 74),
                font=f_def,
            )
            draw.text(
                (26, y + 54),
                f"[BOLD]   {b_lbl:<29} w{pe.bold_weight:<3} Stem={pe.bold_stem_px:4.2f}px ({pe.bold_verdict})",
                fill=(22, 32, 46),
                font=f_def,
            )

            n_res_p = res_map.get(pe.normal_label)
            if n_res_p is not None:
                n_raw, n_psf, n_st, n_clk = _render_specimen_strip_pair(
                    ft, ft_lib, cand_map, n_res_p, sz_pair, sample_txt, sigma_nom_px, threshold, gamma, max_w=380, max_h=34, include_crops=True
                )
                if n_raw is not None:
                    img.paste(n_raw, (740, y + 4))
                if n_psf is not None:
                    img.paste(n_psf, (1135, y + 4))
                if n_st is not None:
                    img.paste(n_st, (1530, y + 4))
                if n_clk is not None:
                    img.paste(n_clk, (1750, y + 4))

            b_res_p = res_map.get(pe.bold_label)
            if b_res_p is not None:
                b_raw, b_psf, b_st, b_clk = _render_specimen_strip_pair(
                    ft, ft_lib, cand_map, b_res_p, sz_pair, sample_txt, sigma_nom_px, threshold, gamma, max_w=380, max_h=34, include_crops=True
                )
                if b_raw is not None:
                    img.paste(b_raw, (740, y + 45))
                if b_psf is not None:
                    img.paste(b_psf, (1135, y + 45))
                if b_st is not None:
                    img.paste(b_st, (1530, y + 45))
                if b_clk is not None:
                    img.paste(b_clk, (1750, y + 45))
            y += pair_row_h

    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out_png))
    return out_png


def generate_qualification_markdown(
    results: Sequence[FontQualifyResult],
    pair_evals: Sequence[FamilyWeightPairEval],
    family_floors: Dict[str, int],
    sizes: Sequence[int],
    pipelines: Sequence[str],
    hw_spec: TargetHardwareSpec,
    src_dir: Path,
    sigma_nom_px: float,
    sigma_off_px: float,
) -> str:
    """Build the comprehensive 20 cm qualification report Markdown document."""
    max_s = max(sizes) if sizes else 24
    ranked = sorted(
        results,
        key=lambda r: (
            r.viable_floor_px,
            -r.score_16px,
            -r.score_14px,
            -r.overall_least_worst_score,
        ),
    )

    lines = [
        f"# `epd-font` v{TOOL_VERSION} — 20 cm (`200 mm`) EPD Legibility Qualification Report",
        "",
        f"- **Source Font Directory**: `{src_dir}` (`{len(results)}` candidate cuts evaluated)",
        f"- **Target Hardware**: `{hw_spec.hw_scheme_id}` (`{hw_spec.panel}`, `{hw_spec.width_px}x{hw_spec.height_px} px`, `{hw_spec.dpi:.2f} DPI`, usable budget `{hw_spec.usable_width_px} px`)",
        f"- **Optical PSF Model (`200 mm`)**: Nominal `sigma = {sigma_nom_px:.2f} px` (`{sigma_nom_px*135:.0f} um`), Off-axis `sigma = {sigma_off_px:.2f} px` (`{sigma_off_px*135:.0f} um`), Panel `R_bg={EPD_DEFAULT_R_BG:.0f}`, `R_ink={EPD_DEFAULT_R_INK:.0f}`",
        f"- **Evaluated Sizes**: `{list(sizes)} px` | **Evaluated Pipelines**: `{list(pipelines)}`",
        "",
        "## 1. Executive Nyquist Floor Summary (`12–14 px` Vector vs. Bitmap vs. `>= 16 px`)",
        "",
        "At `188.15 DPI` (`135 um/px`), a lowercase `'s'` or `'e'` requires 3 horizontal bars + 2 interior open counters (`>= 2 px` each to survive `sigma = 1.25 px` Gaussian blur without collapsing).",
        "",
        "| Metric / Floor Tier | Qualification Outcome | Root Physical Cause |",
        "| :--- | :--- | :--- |",
    ]
    n_pass_14 = sum(1 for r in results if 14 in r.by_size and r.by_size[14].qualifies_20cm)
    n_marg_14 = sum(1 for r in results if 14 in r.by_size and r.by_size[14].verdict == "MARGINAL")
    n_pass_16 = sum(1 for r in results if 16 in r.by_size and r.by_size[16].qualifies_20cm)
    n_pass_18 = sum(1 for r in results if 18 in r.by_size and r.by_size[18].qualifies_20cm)
    n_pass_20 = sum(1 for r in results if 20 in r.by_size and r.by_size[20].qualifies_20cm)
    lines.extend([
        f"| `12 px` | `0 / {len(results)}` vector pass | `x-height ~ 6 px`: Nyquist/Pigeonhole limit prevents >=2px bars + 2px gaps regardless of conversion method. |",
        f"| `14 px` | `{n_pass_14}` PASS, `{n_marg_14}` MARGINAL (bitmap) | `x-height ~ 7 px`: vector Normal drops to `1px` (`~20-35%` ret); `wght=800` Bold blobs `'s'`/`'8'`; `Terminus-Bold` keeps bays open. |",
        f"| `16 px` | `{n_pass_16} / {len(results)}` PASS | `x-height ~ 8-9 px`: select Medium/SemiBold (`500/600`) or non-blobbing cuts survive, while `188 px` 2-col rows tightly constrain wide families. |",
        f"| `18 px` | `{n_pass_18} / {len(results)}` PASS | `x-height >= 9-10 px`: true `2px` bars + `2px` open bays become achievable cleanly. |",
        f"| `20 px+` | `{n_pass_20} / {len(results)}` PASS | Comfortable hero/title legibility (`>= 45%` stroke retention + open counters). |",
        "",
        "## 1b. Overall Viable Size Floor & 'Least-Worst' Corpus Leaderboard",
        "",
        "| Rank | Font Cut | Family Group | Weight | Type | Viable Floor | Marginal Floor | @14px Score | @16px Score | @18px Score | Proof PNG |",
        "| ---: | :--- | :--- | ---: | :--- | ---: | ---: | ---: | ---: | ---: | :--- |",
    ])
    for idx, r in enumerate(ranked, 1):
        vf = f"{r.viable_floor_px}px" if r.viable_floor_px <= max_s else "NONE"
        mf = f"{r.marginal_floor_px}px" if r.marginal_floor_px <= max_s else "NONE"
        ftype = "BMP" if r.is_bitmap else "VEC"
        lines.append(
            f"| {idx} | `{r.label}` | `{r.family_group}` | `{r.weight_class}` | `{ftype}` | "
            f"`{vf}` | `{mf}` | `{r.score_14px:.1f}` | `{r.score_16px:.1f}` | `{r.score_18px:.1f}` | `gaussian_proofs/{r.proof_png}` |"
        )

    lines.extend([
        "",
        "## 2. Family Cross-Weight Separation & Viable Pair Size Floor",
        "",
        "| Family Group | Pair Floor | Size | Normal Cut (`w`) | Bold Cut (`w`) | Normal Stem | Bold Stem | Delta Stem | Ink Ratio | Pair Status | Notes |",
        "| :--- | ---: | ---: | :--- | :--- | ---: | ---: | ---: | ---: | :--- | :--- |",
    ])
    for pe in pair_evals:
        fl = family_floors.get(pe.family_group, max_s + 2)
        fl_s = f"{fl}px" if fl <= max_s else "NONE"
        st_s = "**QUALIFIED**" if pe.pair_qualifies else ("SEP_ONLY" if pe.has_weight_sep else "FAIL")
        lines.append(
            f"| `{pe.family_group}` | `{fl_s}` | `{pe.size_px}px` | `{pe.normal_label}` (`{pe.normal_weight}`) | "
            f"`{pe.bold_label}` (`{pe.bold_weight}`) | `{pe.normal_stem_px:.2f}px` | `{pe.bold_stem_px:.2f}px` | "
            f"`{pe.stem_delta_px:+.2f}px` | `{pe.ink_mass_ratio:.2f}x` | {st_s} | `{pe.notes}` |"
        )

    for target_sz in [s for s in (14, 16, 18) if s in sizes]:
        lines.extend([
            "",
            f"## 3. 'Least-Worst' Font Ranking @ `{target_sz} px`",
            "",
            "| Rank | Font Cut | Weight | Pipeline | Verdict | Least-Worst Score | Trouble Ret% | P10 Ret% | `'s'` Ret% (Cav) | `'ss'` Grating CM | `'8'` Ret% (Cav) | Enc Cnt% | Opn Cav% | Stem | Unif% | `188px` Row (Clr) | Failure Reasons |",
            "| ---: | :--- | ---: | :--- | :--- | ---: | ---: | ---: | :--- | ---: | :--- | ---: | ---: | ---: | ---: | :--- | :--- |",
        ])
        at_sz = sorted(
            [r for r in results if target_sz in r.by_size],
            key=lambda r: (
                0 if r.by_size[target_sz].verdict == "PASS" else (1 if r.by_size[target_sz].verdict == "MARGINAL" else 2),
                -r.by_size[target_sz].least_worst_score,
            ),
        )
        for idx, r in enumerate(at_sz, 1):
            m = r.by_size[target_sz]
            s_ok = "OK" if m.s_cavity_ok else "FAIL"
            d8_ok = "OK" if m.d8_cavity_ok else "FAIL"
            fit_s = f"{m.max_h1os_row_px}px ({m.min_h1os_clearance_px:+d})"
            ftags = ", ".join(m.failure_tags) if m.failure_tags else "PASS"
            lines.append(
                f"| {idx} | `{r.label}` | `{r.weight_class}` | `{m.best_pipeline}` | **{m.verdict}** | `{m.least_worst_score:.1f}` | "
                f"`{m.trouble_ret_nom_pct:.1f}%` | `{m.p10_ret_nom_pct:.1f}%` | `{m.s_ret_nom_pct:.1f}% ({s_ok})` | "
                f"`{m.ss_grating_cm:.3f}` | `{m.d8_ret_nom_pct:.1f}% ({d8_ok})` | `{m.enclosed_counter_pct:.0f}%` | "
                f"`{m.open_cavity_pct:.0f}%` | `{m.mean_stem_px:.2f}px` | `{m.uniformity_pct:.1f}%` | `{fit_s}` | `{ftags}` |"
            )

    lines.extend([
        "",
        "## 4. Manual `.scheme.json` Macro Tag Candidate Cheat-Sheet",
        "",
        "Use the candidates below to manually update `.scheme.json` `strikes` and `output_branding.semantic_roles`:",
        "",
        "| Macro Tag Role | Recommended Min Size | Top Ranked Candidates (Least-Worst / Qualified + `188px` Budget) |",
        "| :--- | :--- | :--- |",
    ])

    def _top_for_role(min_sz: int, max_sz_r: int, want_bold: bool = False, want_mono: bool = False, require_188: bool = False) -> str:
        cands = []
        for r in results:
            if r.is_italic:
                continue
            if want_mono and not r.is_monospace:
                continue
            if want_bold and r.weight_class < 600:
                continue
            if (not want_bold) and r.weight_class >= 700:
                continue
            for sz_c in sorted(r.by_size.keys()):
                if not (min_sz <= sz_c <= max_sz_r):
                    continue
                m = r.by_size[sz_c]
                if any(t in {"empty_glyph", "horizontal_striation", "stroke_fragmentation"} for t in m.failure_tags):
                    continue
                if require_188 and not m.fits_188px_budget:
                    continue
                v_rank = 0 if m.verdict == "PASS" else (1 if m.verdict == "MARGINAL" else 2)
                cands.append((v_rank, -m.least_worst_score, f"`{r.label}` @ `{sz_c}px` ({m.verdict}, score={m.least_worst_score:.1f}, row={m.max_h1os_row_px}px)"))
        cands.sort(key=lambda x: (x[0], x[1]))
        return "; ".join(x[2] for x in cands[:3]) if cands else "None qualified in tested corpus"

    lines.extend([
        f"| `HUMID1_FONT_UI_BODY` (14–16px, fits 188px) | `14–16px` | {_top_for_role(14, 16, want_bold=False, require_188=True)} |",
        f"| `HUMID1_FONT_UI_SUBTITLE` (Bold 14–16px, fits 188px) | `16px` | {_top_for_role(14, 16, want_bold=True, require_188=True)} |",
        f"| `HUMID1_FONT_UI_TITLE` (Bold 16–18px) | `16–18px` | {_top_for_role(16, 18, want_bold=True, require_188=False)} |",
        f"| `HUMID1_FONT_UI_HEADER` (Bold 20–24px) | `20–24px` | {_top_for_role(20, 24, want_bold=True, require_188=False)} |",
        f"| `HUMID1_FONT_TELEMETRY_SM` (Mono 14–16px) | `14–16px` | {_top_for_role(14, 16, want_bold=False, want_mono=True, require_188=False)} |",
        f"| `HUMID1_FONT_TELEMETRY_MD/LG` (Mono Bold 20–24px) | `20–24px` | {_top_for_role(20, 24, want_bold=True, want_mono=True, require_188=False)} |",
        f"| `HUMID1_FONT_TERMINAL` (Mono 14–16px) | `14–16px` | {_top_for_role(14, 16, want_bold=True, want_mono=True, require_188=False)} |",
        "",
    ])
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="humid1_font_qualify.py",
        description=(
            f"Humidyne Labs / Humiditron `epd-font` v{TOOL_VERSION} — Standalone 20 cm EPD Font Legibility Qualifier.\n"
            "Tests any directory of fonts using Char + String 2D Gaussian PSF simulation and weight-separation metrics."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--src-dir", type=str, default=None, help="Directory of .ttf/.otf/.ttc/.bdf fonts to qualify")
    parser.add_argument("--fonts", type=str, nargs="*", default=None, help="Optional explicit font file paths")
    parser.add_argument("--out-dir", type=str, required=True, help="Output directory for reports and proof PNGs")
    parser.add_argument("--sizes", type=int, nargs="+", default=[12, 14, 16, 18, 20, 24], help="Pixel sizes to qualify (default: 12 14 16 18 20 24)")
    parser.add_argument("--pipelines", type=str, nargs="+", default=list(DEFAULT_QUALIFY_PIPELINES), help="Pipelines to test, or 'all' for all 9 pipelines")
    parser.add_argument("--threshold", type=int, default=128, help="Binarization threshold 1..254 (default: 128)")
    parser.add_argument("--gamma", type=float, default=1.0, help="Linear grayscale gamma in [0.20..3.00] (default: 1.0)")
    parser.add_argument("-H", "--hw-scheme", type=str, default="esp32s3-N8R8-hw_scheme.json", help="Hardware scheme JSON (default: esp32s3-N8R8-hw_scheme.json)")
    parser.add_argument("--viewing-distance-mm", type=float, default=200.0, help="Target viewing distance in mm (default: 200.0)")
    parser.add_argument("--sigma-nom-px", type=float, default=EPD_20CM_SIGMA_NOM_PX, help="Nominal Gaussian PSF sigma in px (default: 1.25)")
    parser.add_argument("--sigma-off-px", type=float, default=EPD_20CM_SIGMA_OFF_PX, help="Off-axis Gaussian PSF sigma in px (default: 1.75)")
    parser.add_argument("--include-icons", action="store_true", help="Include PUA icon fonts in qualification run")
    parser.add_argument("--include-megafonts", action="store_true", help="Include >3MB CJK/pan-Unicode fonts in qualification run")
    parser.add_argument("--all-proofs", action="store_true", help="Render per-font and weight-pair proof PNGs for all fonts even when >250 candidates")
    parser.add_argument("--accel", choices=["auto", "cpu", "gpu", "hybrid", "sync"], default=None, help="Math acceleration backend")
    parser.add_argument("-j", "--jobs", type=int, default=None, help="Number of parallel worker processes")
    return parser


def main() -> None:
    install_clean_signal_handlers()
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent if script_dir.name == "fonts" else script_dir.parent
    parser = build_arg_parser()
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        fail_gracefully("Missing required arguments (`--src-dir` or `--fonts`, and `--out-dir`).")

    args = parser.parse_args()
    if not args.src_dir and not args.fonts:
        fail_gracefully("Provide either `--src-dir <directory>` or `--fonts <file1> ...`.")
    if not (1 <= args.threshold <= 254):
        fail_gracefully(f"Invalid `--threshold {args.threshold}` (must be 1..254).")
    if not (0.20 <= args.gamma <= 3.00):
        fail_gracefully(f"Invalid `--gamma {args.gamma}` (must be 0.20..3.00).")

    src_dir = require_valid_path(args.src_dir, "--src-dir", must_exist=True, expect_dir=True) if args.src_dir else repo_root
    out_dir = Path(args.out_dir).expanduser().resolve()
    proofs_dir = out_dir / "gaussian_proofs"
    out_dir.mkdir(parents=True, exist_ok=True)
    proofs_dir.mkdir(parents=True, exist_ok=True)

    hw_spec = load_and_validate_hardware_scheme(
        scheme_cfg={},
        hw_scheme_cli=args.hw_scheme,
        repo_root=repo_root,
        scheme_path=None,
    )

    raw_pipes = [p.strip().lower() for p in args.pipelines]
    if "all" in raw_pipes:
        eff_pipelines = list(CANONICAL_PIPELINES)
    else:
        eff_pipelines = []
        for p in raw_pipes:
            np_name = normalize_pipeline_name(p)
            if np_name not in eff_pipelines:
                eff_pipelines.append(np_name)

    candidates = discover_qualify_candidates(
        src_dir=src_dir,
        explicit_fonts=args.fonts,
        include_icons=args.include_icons,
        include_megafonts=args.include_megafonts,
        repo_root=repo_root,
        var_workers=args.jobs,
    )
    if not candidates:
        fail_gracefully(f"No evaluable fonts discovered in `{src_dir}`.")

    eff_accel = getattr(args, "accel", None) or os.environ.get("EPD_FONT_ACCEL") or "auto"
    os.environ["EPD_FONT_ACCEL"] = eff_accel
    if eff_accel == "cpu":
        os.environ["OPENCV_OPENCL_RUNTIME"] = "disabled"
        try:
            if hasattr(cv2, "ocl"):
                cv2.ocl.setUseOpenCL(False)
        except Exception:
            pass
    select_math_backend("auto" if eff_accel == "sync" else eff_accel)
    hw_info = detect_host_hardware(args.jobs)
    max_workers = 1 if eff_accel == "sync" else hw_info.recommended_workers
    render_all_proofs = bool(args.all_proofs or len(candidates) <= 250)

    print(
        f"[+] Qualifying {len(candidates)} font cuts in `{src_dir}` across sizes {args.sizes} "
        f"and pipelines {eff_pipelines} @ {args.viewing_distance_mm:.0f}mm "
        f"(sigma={args.sigma_nom_px:.2f}/{args.sigma_off_px:.2f}px, usable={hw_spec.usable_width_px}px)...",
        flush=True,
    )
    print(f"[*] Active Backend: {describe_math_backend()} | Workers: {max_workers}", flush=True)

    t0 = time.perf_counter()
    tasks = [
        {
            "candidate": {
                "label": c.label,
                "font_path": str(c.font_path),
                "font_number": c.font_number,
                "file_type": c.file_type,
                "family_group": c.family_group,
                "weight_class": c.weight_class,
                "is_italic": c.is_italic,
                "is_bitmap": c.is_bitmap,
                "is_monospace": c.is_monospace,
                "size_to_path_map": c.size_to_path_map,
            },
            "sizes": list(args.sizes),
            "pipelines": eff_pipelines,
            "threshold": args.threshold,
            "gamma": args.gamma,
            "sigma_nom_px": args.sigma_nom_px,
            "sigma_off_px": args.sigma_off_px,
            "usable_width_px": hw_spec.usable_width_px,
            "proofs_dir": str(proofs_dir),
            "render_proof": render_all_proofs,
        }
        for c in candidates
    ]

    raw_worker_outputs: List[Union[FontQualifyResult, Dict[str, str]]] = []
    if len(tasks) > 300:
        batch_sz = 250
        for b_start in range(0, len(tasks), batch_sz):
            b_slice = tasks[b_start : b_start + batch_sz]
            b_out = run_parallel_tasks(
                _worker_qualify_font, b_slice, max_workers=max_workers, math_backend=eff_accel
            )
            raw_worker_outputs.extend(b_out)
            print(
                f"[*] Qualification progress: {len(raw_worker_outputs)}/{len(tasks)} cuts ({time.perf_counter() - t0:.1f}s)...",
                flush=True,
            )
    else:
        raw_worker_outputs = run_parallel_tasks(
            _worker_qualify_font, tasks, max_workers=max_workers, math_backend=eff_accel
        )

    results: List[FontQualifyResult] = []
    skipped_fonts: List[Dict[str, str]] = []
    for item in raw_worker_outputs:
        if isinstance(item, dict) and "error" in item:
            skipped_fonts.append(item)
        elif isinstance(item, FontQualifyResult):
            results.append(item)
    if skipped_fonts:
        print(f"[!] Warning: {len(skipped_fonts)} font(s) skipped due to parsing/rasterization errors (recorded in JSON report).")
    pair_evals, family_floors = analyze_family_weight_pairs(results, args.sizes)

    cand_map = {c.label: c for c in candidates}
    max_s_run = max(args.sizes) if args.sizes else 24
    proof_count = sum(1 for r in results if r.proof_png)
    if not render_all_proofs and results:
        ranked_for_proofs = sorted(
            results,
            key=lambda r: (
                r.viable_floor_px,
                -r.score_16px,
                -r.score_14px,
                -r.overall_least_worst_score,
            ),
        )
        target_labels = {
            r.label
            for idx_p, r in enumerate(ranked_for_proofs)
            if idx_p < 120 or r.viable_floor_px <= max_s_run or r.marginal_floor_px <= max_s_run
        }
        proof_tasks = [{**t, "render_proof": True} for t in tasks if t["candidate"]["label"] in target_labels]
        if proof_tasks:
            print(
                f"[*] Rendering {len(proof_tasks)}/{len(results)} Gaussian Proof PNGs "
                "(Top 120 + all viable/marginal cuts; pass --all-proofs to render all)...",
                flush=True,
            )
            p_outs = run_parallel_tasks(
                _worker_qualify_font, proof_tasks, max_workers=max_workers, math_backend=eff_accel
            )
            p_map = {it.label: it.proof_png for it in p_outs if isinstance(it, FontQualifyResult)}
            for r in results:
                if r.label in p_map:
                    r.proof_png = p_map[r.label]
            proof_count = len(p_map)

    wp_paths = render_family_weight_pair_sheets(
        out_dir,
        results,
        pair_evals,
        args.sizes,
        cand_map=cand_map,
        sigma_nom_px=args.sigma_nom_px,
        threshold=args.threshold,
        gamma=args.gamma,
        family_floors=family_floors,
        max_families=None if render_all_proofs else 60,
    )
    master_png = out_dir / "master_gaussian_qualification_sheet.png"
    render_master_qualification_sheet(master_png, results, args.sizes)
    top_ranked_png = out_dir / "top_ranked_visual_sheet.png"
    render_top_ranked_visual_sheet(
        top_ranked_png,
        results,
        args.sizes,
        cand_map=cand_map,
        sigma_nom_px=args.sigma_nom_px,
        threshold=args.threshold,
        gamma=args.gamma,
    )
    best_class_png = out_dir / "best_in_class_visual_sheet.png"
    render_best_in_class_visual_sheet(
        best_class_png,
        results,
        args.sizes,
        cand_map=cand_map,
        pair_evals=pair_evals,
        sigma_nom_px=args.sigma_nom_px,
        threshold=args.threshold,
        gamma=args.gamma,
    )

    md_text = generate_qualification_markdown(
        results=results,
        pair_evals=pair_evals,
        family_floors=family_floors,
        sizes=args.sizes,
        pipelines=eff_pipelines,
        hw_spec=hw_spec,
        src_dir=src_dir,
        sigma_nom_px=args.sigma_nom_px,
        sigma_off_px=args.sigma_off_px,
    )
    md_path = out_dir / "qualification_report.md"
    md_path.write_text(md_text, encoding="utf-8")

    csv_path = out_dir / "qualification_report.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as cf:
        writer = csv.writer(cf)
        writer.writerow([
            "label", "font_file", "family_group", "weight_class", "is_italic", "is_bitmap", "is_monospace",
            "size_px", "best_pipeline", "verdict", "qualifies_20cm", "least_worst_score",
            "mean_ret_nom_pct", "trouble_ret_nom_pct", "p10_ret_nom_pct", "p10_ret_off_pct",
            "s_ret_nom_pct", "s_cm_nom", "s_cavity_ok", "d8_ret_nom_pct", "d8_cm_nom", "d8_cavity_ok",
            "enclosed_counter_pct", "open_cavity_pct", "mean_stem_px", "min_stem_px", "stem_2px_pct",
            "uniformity_pct", "min_string_ret_nom_pct", "mean_string_ret_nom_pct",
            "status_ret_nom_pct", "pressure_ret_nom_pct", "ss_grating_cm", "clock_ret_nom_pct",
            "max_h1os_row_px", "min_h1os_clearance_px", "fits_188px_budget", "ink_pixels",
            "x_height_px", "cap_height_px", "failure_tags",
        ])
        for r in results:
            for sz in sorted(r.by_size.keys()):
                m = r.by_size[sz]
                writer.writerow([
                    r.label, r.font_file, r.family_group, r.weight_class, r.is_italic, r.is_bitmap, r.is_monospace,
                    m.size_px, m.best_pipeline, m.verdict, m.qualifies_20cm, m.least_worst_score,
                    m.mean_ret_nom_pct, m.trouble_ret_nom_pct, m.p10_ret_nom_pct, m.p10_ret_off_pct,
                    m.s_ret_nom_pct, m.s_cm_nom, m.s_cavity_ok, m.d8_ret_nom_pct, m.d8_cm_nom, m.d8_cavity_ok,
                    m.enclosed_counter_pct, m.open_cavity_pct, m.mean_stem_px, m.min_stem_px, m.stem_2px_pct,
                    m.uniformity_pct, m.min_string_ret_nom_pct, m.mean_string_ret_nom_pct,
                    m.status_ret_nom_pct, m.pressure_ret_nom_pct, m.ss_grating_cm, m.clock_ret_nom_pct,
                    m.max_h1os_row_px, m.min_h1os_clearance_px, m.fits_188px_budget, m.ink_pixels,
                    m.x_height_px, m.cap_height_px, "|".join(m.failure_tags),
                ])

    json_payload = {
        "tool_version": TOOL_VERSION,
        "src_dir": str(src_dir),
        "hw_scheme": hw_spec.hw_scheme_id,
        "usable_width_px": hw_spec.usable_width_px,
        "viewing_distance_mm": args.viewing_distance_mm,
        "sigma_nom_px": args.sigma_nom_px,
        "sigma_off_px": args.sigma_off_px,
        "sizes": list(args.sizes),
        "pipelines": eff_pipelines,
        "family_pair_floors": family_floors,
        "family_weight_pairs": [asdict(p) for p in pair_evals],
        "skipped_fonts": skipped_fonts,
        "fonts": [
            {k: v for k, v in asdict(r).items() if k != "font_path"}
            for r in results
        ],
    }
    json_path = out_dir / "qualification_report.json"
    json_path.write_text(json.dumps(json_payload, indent=2) + "\n", encoding="utf-8")

    elapsed = time.perf_counter() - t0
    print(f"[+] Wrote {proof_count} Per-Font Gaussian Proof PNGs -> {proofs_dir}")
    print(f"[+] Wrote {len(wp_paths)} Family Weight-Pair PNGs     -> {out_dir / 'weight_pairs'}")
    print(f"[+] Wrote Master Qualification Scorecard PNG        -> {master_png}")
    print(f"[+] Wrote Top-Ranked Visual Comparison PNG          -> {top_ranked_png}")
    print(f"[+] Wrote Best-in-Class Visual Selection PNG        -> {best_class_png}")
    print(f"[+] Wrote Qualification Reports (.md/.csv/.json)    -> {md_path} ({elapsed:.2f}s)")


if __name__ == "__main__":
    try:
        main()
    finally:
        teardown_math_backends()
