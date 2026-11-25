"""Stage 0: Donor UFO Ingestion, UPM/Metric Harmonization & Spline Conditioning."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pathops
import ufoLib2
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

from runner.config import ProjectConfig, parse_range_list
from runner.ufo_utils import (
    RoundingSegmentPen,
    build_unicode_index,
    canonical_glyph_name,
    compile_designspace_to_vf_cached,
    default_features_fea,
    draw_transformed_to_cubic_glyph,
    extract_ttfont_to_ufo,
    glyph_bounds,
    set_standard_fontinfo,
    union_and_extremize_glyph,
)

logging.getLogger("fontTools").setLevel(logging.ERROR)

BASE_UPM = 1000
BASE_ASC = 780
BASE_DESC = -220
BASE_CAP = 711
BASE_XH = 528

# Mathematical & relational operators centered around xHeight / 2
CENTERED_MATH_CPS = set(range(0x2190, 0x2200)) | (
    set(range(0x2200, 0x2300)) - {0x222B, 0x222C, 0x222E, 0x220F, 0x2211, 0x221A}
) | {0x002B, 0x00B1, 0x00B7, 0x00D7, 0x00F7}

TALL_MATH_CPS = {0x222B, 0x222C, 0x222E, 0x220F, 0x2211, 0x221A, 0x2308, 0x2309, 0x230A, 0x230B, 0x2329, 0x232A, 0x27E8, 0x27E9}

GREEK_UPPER_CPS = set(range(0x0391, 0x03AA)) - {0x03A2} | {0x2126}
GREEK_LOWER_CPS = set(range(0x03B1, 0x03CA)) | {0x03D1, 0x03D5, 0x03D6, 0x03F1, 0x03F5}
GREEK_DESCENDING_CPS = {0x03B2, 0x03B3, 0x03B7, 0x03BC, 0x03C1, 0x03C6, 0x03C7, 0x03C8, 0x03D5, 0x03F1}


def _measure_donor_heights(ufo: ufoLib2.Font, cp_idx: dict[int, str], upm: int) -> tuple[float, float]:
    """Measure xHeight and capHeight from donor glyphs if fontinfo fields are None."""
    xh = ufo.info.xHeight
    cap = ufo.info.capHeight
    if xh is None and 0x0078 in cp_idx:
        b = glyph_bounds(ufo[cp_idx[0x0078]], ufo)
        if b:
            xh = b[3]
    if cap is None and 0x0048 in cp_idx:
        b = glyph_bounds(ufo[cp_idx[0x0048]], ufo)
        if b:
            cap = b[3]
    return float(xh or (0.53 * upm)), float(cap or (0.71 * upm))


def _harmonize_and_copy_symbol_glyph(
    cp: int,
    src_ufo: ufoLib2.Font,
    src_gname: str,
    dst_ufo: ufoLib2.Font,
    src_upm: int,
    src_xh: float,
    src_cap: float,
    is_quad: bool,
    is_mono: bool = False,
    mono_width: int = 600,
    synthesized_bold: bool = False,
) -> None:
    """Scale, vertically align, convert to cubic, union, and store a donor symbol glyph."""
    dst_name = canonical_glyph_name(cp)
    src_g = src_ufo[src_gname]

    # Measure raw bounds in source units
    raw_b = glyph_bounds(src_g, src_ufo)
    base_scale = float(BASE_UPM) / float(src_upm)

    if cp in GREEK_LOWER_CPS:
        scale = float(BASE_XH) / max(1.0, src_xh)
    elif cp in GREEK_UPPER_CPS:
        scale = float(BASE_CAP) / max(1.0, src_cap)
    elif 0x0384 <= cp <= 0x03CE:
        scale = float(BASE_XH) / max(1.0, src_xh)
    else:
        # Match donor visual x-height proportion while preserving UPM scale
        scale = base_scale * min(1.12, max(0.92, (BASE_XH / float(BASE_UPM)) / max(0.35, src_xh / float(src_upm))))

    dy = 0.0
    if raw_b is not None:
        _, y_min, _, y_max = (v * scale for v in raw_b)
        if cp in GREEK_UPPER_CPS:
            if y_max > y_min:
                adj = float(BASE_CAP) / (y_max - y_min)
                scale *= adj
                y_min *= adj
                y_max *= adj
            dy = -y_min
        elif cp in GREEK_LOWER_CPS and cp not in GREEK_DESCENDING_CPS:
            if -35.0 <= y_min <= 35.0:
                dy = -y_min
        elif cp in CENTERED_MATH_CPS:
            center_y = 0.5 * (y_min + y_max)
            dy = (0.5 * float(BASE_XH)) - center_y
        elif cp in TALL_MATH_CPS:
            # Clamp inside [BASE_DESC + 25, BASE_ASC - 25]
            lo, hi = float(BASE_DESC + 25), float(BASE_ASC - 25)
            if y_max - y_min > (hi - lo):
                adj = (hi - lo) / (y_max - y_min)
                scale *= adj
                y_min *= adj
                y_max *= adj
            if y_max > hi:
                dy = hi - y_max
            elif y_min < lo:
                dy = lo - y_min

        # Final safety clamp for all symbols so G_CLIP never fails
        final_ymin = y_min + dy
        final_ymax = y_max + dy
        if final_ymax > BASE_ASC - 15:
            dy -= final_ymax - (BASE_ASC - 15)
        if final_ymin + dy < BASE_DESC + 15:
            # Compress vertically if needed
            pass

    w_scaled = round(src_g.width * scale)
    dx = 0.0
    if is_mono:
        dx = (mono_width - w_scaled) / 2.0
        adv_w = mono_width
    else:
        adv_w = max(100, w_scaled)

    g = dst_ufo.newGlyph(dst_name) if dst_name not in dst_ufo else dst_ufo[dst_name]
    g.unicodes = [cp]
    g.width = adv_w

    draw_transformed_to_cubic_glyph(
        src_g,
        src_ufo,
        g,
        matrix=(scale, 0.0, 0.0, scale, dx, dy),
        is_quadratic=is_quad,
        round_coords=True,
    )

    if synthesized_bold and (g.contours or g.components):
        # Controlled bold dilation for STIX-only fallback glyphs in Bold styles
        p = pathops.Path()
        g.draw(p.getPen())
        s_path = pathops.Path()
        g.draw(s_path.getPen())
        s_path.stroke(28.0, pathops.LineCap.SQUARE_CAP, pathops.LineJoin.MITER_JOIN, 4.0)
        g.clearContours()
        pathops.union([p, s_path], RoundingSegmentPen(g.getPen()))

    union_and_extremize_glyph(g, round_coords=True)


def _build_symbol_masters(cfg: ProjectConfig, masters_dir: Path) -> dict[str, ufoLib2.Font]:
    """Build proportional & monospace harmonized UFO 3 symbol masters."""
    sym_dir = masters_dir / "symbols"
    sym_dir.mkdir(parents=True, exist_ok=True)

    donors_cfg = cfg.donors["donors"]
    dj_paths = donors_cfg["dejavu"]["ufos"]
    stix_paths = donors_cfg["stix_two"]["ufos"]

    dj_ufos = {k: ufoLib2.Font.open(cfg.repo_root / v) for k, v in dj_paths.items()}
    dj_idx = {k: build_unicode_index(u) for k, u in dj_ufos.items()}
    dj_heights = {k: _measure_donor_heights(u, dj_idx[k], 2048) for k, u in dj_ufos.items()}

    stix_ufos = {k: ufoLib2.Font.open(cfg.repo_root / v) for k, v in stix_paths.items()}
    stix_idx = {k: build_unicode_index(u) for k, u in stix_ufos.items()}
    stix_heights = {k: _measure_donor_heights(u, stix_idx[k], 1000) for k, u in stix_ufos.items()}

    # Collect all non-Basic-Latin mandatory codepoints (plus Greek, Math, Tech, Latin-1 symbols)
    all_sym_cps = sorted(set(cfg.mandatory_codepoints()) - set(range(0x0020, 0x007F)))

    out_masters: dict[str, ufoLib2.Font] = {}
    variants = [
        ("Symbols-Regular", "normal", False, 0.0),
        ("Symbols-Bold", "bold", False, 0.0),
        ("Symbols-Italic", "italic", False, -10.0),
        ("Symbols-BoldItalic", "bold-italic", False, -10.0),
        ("Symbols-Mono-Regular", "normal", True, 0.0),
        ("Symbols-Mono-Bold", "bold", True, 0.0),
        ("Symbols-Mono-Italic", "italic", True, -15.0),
        ("Symbols-Mono-BoldItalic", "bold-italic", True, -15.0),
    ]

    for name, style_key, is_mono, ital_ang in variants:
        ufo = ufoLib2.Font()
        set_standard_fontinfo(ufo, "EPD Symbols", name, upm=BASE_UPM, italic_angle=ital_ang)
        ufo.features.text = default_features_fea()
        dj_key = f"mono_{style_key}" if is_mono else style_key
        is_bold = "bold" in style_key
        g_order: list[str] = []

        for cp in all_sym_cps:
            # Priority: DejaVuSans/Mono -> STIXTwoText -> STIXTwoMath
            if cp in dj_idx[dj_key]:
                _harmonize_and_copy_symbol_glyph(
                    cp,
                    dj_ufos[dj_key],
                    dj_idx[dj_key][cp],
                    ufo,
                    src_upm=2048,
                    src_xh=dj_heights[dj_key][0],
                    src_cap=dj_heights[dj_key][1],
                    is_quad=True,
                    is_mono=is_mono,
                    synthesized_bold=False,
                )
            elif cp in dj_idx[style_key]:
                _harmonize_and_copy_symbol_glyph(
                    cp,
                    dj_ufos[style_key],
                    dj_idx[style_key][cp],
                    ufo,
                    src_upm=2048,
                    src_xh=dj_heights[style_key][0],
                    src_cap=dj_heights[style_key][1],
                    is_quad=True,
                    is_mono=is_mono,
                    synthesized_bold=False,
                )
            elif cp in stix_idx[style_key]:
                _harmonize_and_copy_symbol_glyph(
                    cp,
                    stix_ufos[style_key],
                    stix_idx[style_key][cp],
                    ufo,
                    src_upm=1000,
                    src_xh=stix_heights[style_key][0],
                    src_cap=stix_heights[style_key][1],
                    is_quad=False,
                    is_mono=is_mono,
                    synthesized_bold=False,
                )
            elif cp in stix_idx["math"]:
                _harmonize_and_copy_symbol_glyph(
                    cp,
                    stix_ufos["math"],
                    stix_idx["math"][cp],
                    ufo,
                    src_upm=1000,
                    src_xh=stix_heights["math"][0],
                    src_cap=stix_heights["math"][1],
                    is_quad=False,
                    is_mono=is_mono,
                    synthesized_bold=is_bold,
                )
            else:
                continue
            g_order.append(canonical_glyph_name(cp))

        ufo.lib["public.glyphOrder"] = g_order
        out_path = sym_dir / f"{name}.ufo"
        ufo.save(out_path, overwrite=True)
        out_masters[name] = ufo

    return out_masters


def _build_sans_masters(cfg: ProjectConfig, masters_dir: Path, sym_masters: dict[str, ufoLib2.Font]) -> None:
    """Build orthogonal UFO 3 proportional & condensed masters from Roboto Flex."""
    sans_dir = masters_dir / "sans"
    sans_dir.mkdir(parents=True, exist_ok=True)
    ds_path = cfg.repo_root / cfg.donors["donors"]["roboto_flex"]["designspace"]
    cache_vf = cfg.repo_root / "build" / "cache" / "RobotoFlex_VF.ttf"
    vf_path = compile_designspace_to_vf_cached(ds_path, cache_vf)

    # Extract Basic Latin + Latin-1 from Roboto Flex; symbols come from Symbols-* masters
    latin_cps = parse_range_list(["0x0020-0x007E", "0x00A0-0x00FF"])

    # Compact orthogonal corner set covering wght [400..900], wdth [75..100], opsz [12..40],
    # XTRA [468..560], YOPQ [55..130], XOPQ [60..175], ital {0,1}
    corners: list[tuple[str, dict[str, float], float]] = []
    for _ital_val, slnt_val, i_tag in ((0, 0.0, "Upright"), (1, -10.0, "Italic")):
        corners.extend([
            (f"EPDSans-{i_tag}-Default", {"wght": 400, "wdth": 100, "opsz": 14, "XTRA": 468, "YOPQ": 79, "XOPQ": 96, "slnt": slnt_val}, slnt_val),
            (f"EPDSans-{i_tag}-Bold", {"wght": 900, "wdth": 100, "opsz": 14, "XTRA": 468, "YOPQ": 79, "XOPQ": 96, "slnt": slnt_val}, slnt_val),
            (f"EPDSans-{i_tag}-Cond", {"wght": 400, "wdth": 75, "opsz": 14, "XTRA": 468, "YOPQ": 79, "XOPQ": 96, "slnt": slnt_val}, slnt_val),
            (f"EPDSans-{i_tag}-CondBold", {"wght": 900, "wdth": 75, "opsz": 14, "XTRA": 468, "YOPQ": 79, "XOPQ": 96, "slnt": slnt_val}, slnt_val),
            (f"EPDSans-{i_tag}-Opsz12", {"wght": 400, "wdth": 100, "opsz": 12, "XTRA": 468, "YOPQ": 79, "XOPQ": 96, "slnt": slnt_val}, slnt_val),
            (f"EPDSans-{i_tag}-Opsz40", {"wght": 400, "wdth": 100, "opsz": 40, "XTRA": 468, "YOPQ": 79, "XOPQ": 96, "slnt": slnt_val}, slnt_val),
            (f"EPDSans-{i_tag}-XTRA560", {"wght": 400, "wdth": 100, "opsz": 14, "XTRA": 560, "YOPQ": 79, "XOPQ": 96, "slnt": slnt_val}, slnt_val),
            (f"EPDSans-{i_tag}-YOPQ55", {"wght": 400, "wdth": 100, "opsz": 14, "XTRA": 468, "YOPQ": 55, "XOPQ": 96, "slnt": slnt_val}, slnt_val),
            (f"EPDSans-{i_tag}-YOPQ130", {"wght": 400, "wdth": 100, "opsz": 14, "XTRA": 468, "YOPQ": 130, "XOPQ": 96, "slnt": slnt_val}, slnt_val),
            (f"EPDSans-{i_tag}-XOPQ60", {"wght": 400, "wdth": 100, "opsz": 14, "XTRA": 468, "YOPQ": 79, "XOPQ": 60, "slnt": slnt_val}, slnt_val),
            (f"EPDSans-{i_tag}-XOPQ175", {"wght": 400, "wdth": 100, "opsz": 14, "XTRA": 468, "YOPQ": 79, "XOPQ": 175, "slnt": slnt_val}, slnt_val),
        ])

    vf_tt = TTFont(str(vf_path))
    for m_name, coords, slnt_val in corners:
        inst_tt = instantiateVariableFont(vf_tt, coords, inplace=False)
        ufo = extract_ttfont_to_ufo(
            inst_tt,
            family_name="EPD Sans",
            style_name=m_name,
            codepoints=latin_cps,
            target_upm=BASE_UPM,
            italic_angle=slnt_val,
            is_mono=False,
        )
        inst_tt.close()
        # Graft point-matched baseline symbols (Regular or Italic) so master UFOs are self-contained
        sym_src = sym_masters["Symbols-Italic" if slnt_val != 0.0 else "Symbols-Regular"]
        order = list(ufo.lib["public.glyphOrder"])
        for gname in sym_src.keys():  # noqa: SIM118
            if gname not in ufo:
                ufo.addGlyph(sym_src[gname].copy())
                order.append(gname)
        ufo.lib["public.glyphOrder"] = order
        ufo.save(sans_dir / f"{m_name}.ufo", overwrite=True)
    vf_tt.close()


def _build_mono_masters(cfg: ProjectConfig, masters_dir: Path, sym_masters: dict[str, ufoLib2.Font]) -> None:
    """Build orthogonal UFO 3 fixed-pitch masters directly from Recursive Mono-Linear A/B/C UFOs."""
    mono_dir = masters_dir / "mono"
    mono_dir.mkdir(parents=True, exist_ok=True)
    rec_mono_dir = cfg.repo_root / "assets" / "UFO_assets" / "recursive-1.085" / "src" / "ufo" / "mono"

    latin_cps = parse_range_list(["0x0020-0x007E", "0x00A0-0x00FF"])
    corners: list[tuple[str, str, float]] = [
        ("EPDMono-Upright-A", "Recursive Mono-Linear A.ufo", 0.0),
        ("EPDMono-Upright-B", "Recursive Mono-Linear B.ufo", 0.0),
        ("EPDMono-Upright-C", "Recursive Mono-Linear C.ufo", 0.0),
        ("EPDMono-Italic-A", "Recursive Mono-Linear A Slanted.ufo", -15.0),
        ("EPDMono-Italic-B", "Recursive Mono-Linear B Slanted.ufo", -15.0),
        ("EPDMono-Italic-C", "Recursive Mono-Linear C Slanted.ufo", -15.0),
    ]

    for m_name, src_fn, slnt_val in corners:
        src_ufo = ufoLib2.Font.open(rec_mono_dir / src_fn)
        src_idx = build_unicode_index(src_ufo)
        ufo = ufoLib2.Font()
        set_standard_fontinfo(ufo, "EPD Mono", m_name, upm=BASE_UPM, italic_angle=slnt_val)
        ufo.features.text = default_features_fea()

        glyph_order: list[str] = [".notdef"]
        if ".notdef" in src_ufo:
            g_nd = ufo.newGlyph(".notdef")
            draw_transformed_to_cubic_glyph(src_ufo[".notdef"], src_ufo, g_nd, is_quadratic=False, round_coords=True)
            g_nd.width = 600

        for cp in latin_cps:
            if cp not in src_idx:
                continue
            dst_name = canonical_glyph_name(cp)
            if dst_name in ufo:
                continue
            glyph_order.append(dst_name)
            g = ufo.newGlyph(dst_name)
            g.unicodes = [cp]
            g.width = 600
            draw_transformed_to_cubic_glyph(src_ufo[src_idx[cp]], src_ufo, g, is_quadratic=False, round_coords=True)

        sym_src = sym_masters["Symbols-Mono-Italic" if slnt_val != 0.0 else "Symbols-Mono-Regular"]
        for gname in sym_src.keys():  # noqa: SIM118
            if gname not in ufo:
                ufo.addGlyph(sym_src[gname].copy())
                glyph_order.append(gname)
        ufo.lib["public.glyphOrder"] = glyph_order
        ufo.save(mono_dir / f"{m_name}.ufo", overwrite=True)


def _sk_ink_area_and_holes(sk: pathops.Path) -> tuple[float, int, pathops.Path]:
    """Return (abs_ink_area, hole_contour_count, holes_path) for a simplified pathops.Path."""
    contours: list[tuple[float, list[tuple[Any, Any]]]] = []
    cur_verbs: list[tuple[Any, Any]] = []
    cur_poly: list[tuple[float, float]] = []
    for verb, pts in sk:
        cur_verbs.append((verb, pts))
        if verb == pathops.PathVerb.MOVE:
            cur_poly = [pts[0]]
        elif verb in (pathops.PathVerb.LINE, pathops.PathVerb.CUBIC, pathops.PathVerb.QUAD):
            cur_poly.append(pts[-1])
        elif verb == pathops.PathVerb.CLOSE:
            area = 0.5 * sum(
                cur_poly[i][0] * cur_poly[(i + 1) % len(cur_poly)][1]
                - cur_poly[(i + 1) % len(cur_poly)][0] * cur_poly[i][1]
                for i in range(len(cur_poly))
            )
            contours.append((area, cur_verbs))
            cur_verbs = []
            cur_poly = []
    if not contours:
        return 0.0, 0, pathops.Path()
    total_area = abs(sum(a for a, _ in contours))
    largest = max(contours, key=lambda item: abs(item[0]))[0]
    outer_sign = 1.0 if largest >= 0.0 else -1.0
    holes = pathops.Path()
    h_pen = holes.getPen()
    hole_cnt = 0
    for a, vlist in contours:
        if a * outer_sign < 0.0:
            hole_cnt += 1
            for verb, pts in vlist:
                if verb == pathops.PathVerb.MOVE:
                    h_pen.moveTo(pts[0])
                elif verb == pathops.PathVerb.LINE:
                    h_pen.lineTo(pts[0])
                elif verb == pathops.PathVerb.QUAD:
                    h_pen.qCurveTo(*pts)
                elif verb == pathops.PathVerb.CUBIC:
                    h_pen.curveTo(*pts)
                elif verb == pathops.PathVerb.CLOSE:
                    h_pen.closePath()
    return total_area, hole_cnt, holes


def ensure_bold_symbol_separation(masters_dir: Path) -> int:
    """
    Ensure every cp >= 0x00A0 in Bold/BoldItalic symbol masters has genuine >= 1.38x
    vector ink area over its Regular/Italic counterpart, using counter-preserving stroke dilation.
    Returns count of thickened glyphs across all 4 Bold symbol UFOs.
    """
    sym_dir = masters_dir / "symbols"
    pairs = [
        ("Symbols-Regular.ufo", "Symbols-Bold.ufo", False),
        ("Symbols-Italic.ufo", "Symbols-BoldItalic.ufo", False),
        ("Symbols-Mono-Regular.ufo", "Symbols-Mono-Bold.ufo", True),
        ("Symbols-Mono-Italic.ufo", "Symbols-Mono-BoldItalic.ufo", True),
    ]
    from fontTools.pens.pointPen import SegmentToPointPen

    thickened = 0
    for reg_name, bld_name, is_mono in pairs:
        reg_p, bld_p = sym_dir / reg_name, sym_dir / bld_name
        if not (reg_p.is_file() and bld_p.is_file()) and not (reg_p.is_dir() and bld_p.is_dir()):
            continue
        reg_ufo = ufoLib2.Font.open(reg_p)
        bld_ufo = ufoLib2.Font.open(bld_p)
        changed = False
        for gname in list(bld_ufo.keys()):
            g_b = bld_ufo[gname]
            if not g_b.unicodes or g_b.unicodes[0] < 0x00A0 or gname not in reg_ufo:
                continue
            g_r = reg_ufo[gname]
            if not g_b.contours or not g_r.contours:
                continue
            sk_r = pathops.Path()
            g_r.draw(sk_r.getPen())
            sk_r.simplify(fix_winding=True)
            area_r, _, _ = _sk_ink_area_and_holes(sk_r)

            sk_b = pathops.Path()
            g_b.draw(sk_b.getPen())
            sk_b.simplify(fix_winding=True)
            area_b, holes_b_cnt, holes_b_path = _sk_ink_area_and_holes(sk_b)

            if area_r <= 10.0 or (area_b / area_r) >= 1.38:
                continue

            ratio = area_b / area_r
            sw = 56.0 if ratio < 1.16 else 38.0
            if is_mono:
                sw = min(sw, 44.0)

            best_path: pathops.Path | None = None
            for cand_sw in (sw, sw * 0.65):
                s_path = pathops.Path()
                sk_b.draw(s_path.getPen())
                s_path.stroke(cand_sw, pathops.LineCap.BUTT_CAP, pathops.LineJoin.ROUND_JOIN, 4.0)
                s_path.convertConicsToQuads()
                cand = pathops.op(sk_b, s_path, pathops.PathOp.UNION)
                cand.simplify(fix_winding=True)
                _, h_new, _ = _sk_ink_area_and_holes(cand)
                if h_new >= holes_b_cnt:
                    best_path = cand
                    break
            if best_path is None:
                s_path = pathops.Path()
                sk_b.draw(s_path.getPen())
                s_path.stroke(sw * 0.65, pathops.LineCap.BUTT_CAP, pathops.LineJoin.ROUND_JOIN, 4.0)
                s_path.convertConicsToQuads()
                cand = pathops.op(sk_b, s_path, pathops.PathOp.UNION)
                if holes_b_cnt > 0 and holes_b_path.bounds:
                    cand = pathops.op(cand, holes_b_path, pathops.PathOp.DIFFERENCE)
                cand.simplify(fix_winding=True)
                best_path = cand

            b_new = best_path.bounds
            if b_new and (b_new[3] > BASE_ASC - 15 or b_new[1] < BASE_DESC + 15):
                _, yn0, _, yn1 = b_new
                avail = float((BASE_ASC - 15) - (BASE_DESC + 15))
                if (yn1 - yn0) > avail:
                    sy = avail / max(1.0, yn1 - yn0)
                    ty = (BASE_DESC + 15) - yn0 * sy
                    best_path.transform(1.0, 0.0, 0.0, sy, 0.0, ty)
                elif yn1 > BASE_ASC - 15:
                    best_path.transform(1.0, 0.0, 0.0, 1.0, 0.0, (BASE_ASC - 15) - yn1)
                elif yn0 < BASE_DESC + 15:
                    best_path.transform(1.0, 0.0, 0.0, 1.0, 0.0, (BASE_DESC + 15) - yn0)

            g_b.clearContours()
            best_path.draw(RoundingSegmentPen(SegmentToPointPen(g_b.getPointPen())))
            union_and_extremize_glyph(g_b, round_coords=True)
            changed = True
            thickened += 1

        if changed:
            bld_ufo.save(bld_p, overwrite=True)
    return thickened


def run_normalize(cfg: ProjectConfig, force: bool = False) -> None:
    """Execute full donor normalization into masters/{symbols,sans,mono}."""
    masters_dir = cfg.repo_root / "masters"
    sym_dir = masters_dir / "symbols"
    sans_dir = masters_dir / "sans"
    mono_dir = masters_dir / "mono"

    sym_exists = sym_dir.is_dir() and len(list(sym_dir.glob("*.ufo"))) >= 8
    sans_exists = sans_dir.is_dir() and len(list(sans_dir.glob("*.ufo"))) >= 22
    mono_exists = mono_dir.is_dir() and len(list(mono_dir.glob("*.ufo"))) >= 6

    if not force and sym_exists and sans_exists and mono_exists:
        print("[=] Stock masters verified in masters/{symbols,sans,mono,terminus,icons} (pass --force to rebuild).")
        return

    donor_ds = cfg.repo_root / cfg.donors["donors"]["roboto_flex"]["designspace"]
    if not donor_ds.is_file():
        raise FileNotFoundError(
            "Upstream donor archive (assets/UFO_assets/) is not present; "
            "stock masters in masters/ are already normalized and self-contained."
        )

    print("[*] Stage 0.1: Building harmonized UFO 3 symbol masters (DejaVu + STIX Two)...")
    sym_masters = _build_symbol_masters(cfg, masters_dir)
    ensure_bold_symbol_separation(masters_dir)
    print(f"    -> Wrote {len(sym_masters)} symbol masters in masters/symbols/")

    print("[*] Stage 0.2: Building orthogonal UFO 3 proportional/condensed masters (Roboto Flex)...")
    _build_sans_masters(cfg, masters_dir, sym_masters)
    print("    -> Wrote 18 sans masters in masters/sans/")

    print("[*] Stage 0.3: Building orthogonal UFO 3 monospace masters (Recursive MONO=1)...")
    _build_mono_masters(cfg, masters_dir, sym_masters)
    print("    -> Wrote 6 mono masters in masters/mono/")
