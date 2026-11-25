"""Stage 2: Per-Size Instantiation, Symbol Grafting & Sub-Grid Coordinate Snapping."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pathops
import ufoLib2
from fontTools.pens.pointPen import SegmentToPointPen
from fontTools.pens.transformPen import TransformPen

from runner.ufo_utils import (
    RoundingSegmentPen,
    build_unicode_index,
    default_features_fea,
    glyph_bounds,
    rec_from_glyph,
    set_standard_fontinfo,
    union_and_extremize_glyph,
)

CAP_LOCK_CPS = set(range(0x0041, 0x005B)) | set(range(0x0030, 0x003A)) | set(range(0x0391, 0x03AA)) - {0x03A2} | {0x2126}
INK_TRAP_CPS = {
    ord(c) for c in "EFGHIJKLMNTVWXYZfhkmnrtuvwxyz12457ΓΕΖΗΙΚΛΜΝΞΠΣΤΥΧΨ"
}


def _flatten_pathops_segments(sk: pathops.Path) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Flatten simplified pathops.Path cubics/quads/lines into short polyline segments."""
    segs: list[tuple[tuple[float, float], tuple[float, float]]] = []
    p0 = (0.0, 0.0)
    cur = (0.0, 0.0)
    for verb, pts in sk:
        if verb == pathops.PathVerb.MOVE:
            cur = p0 = pts[0]
        elif verb == pathops.PathVerb.LINE:
            nxt = pts[0]
            segs.append((cur, nxt))
            cur = nxt
        elif verb == pathops.PathVerb.CUBIC:
            c1, c2, nxt = pts
            for k in range(1, 9):
                t = k / 8.0
                mt = 1.0 - t
                pt = (
                    mt**3 * cur[0] + 3 * mt**2 * t * c1[0] + 3 * mt * t**2 * c2[0] + t**3 * nxt[0],
                    mt**3 * cur[1] + 3 * mt**2 * t * c1[1] + 3 * mt * t**2 * c2[1] + t**3 * nxt[1],
                )
                segs.append((cur, pt))
                cur = pt
        elif verb == pathops.PathVerb.QUAD:
            c1, nxt = pts
            for k in range(1, 7):
                t = k / 6.0
                mt = 1.0 - t
                pt = (
                    mt**2 * cur[0] + 2 * mt * t * c1[0] + t**2 * nxt[0],
                    mt**2 * cur[1] + 2 * mt * t * c1[1] + t**2 * nxt[1],
                )
                segs.append((cur, pt))
                cur = pt
        elif verb == pathops.PathVerb.CLOSE:
            if cur != p0:
                segs.append((cur, p0))
            cur = p0
    return segs


def _scan_axis_intervals(
    segs: list[tuple[tuple[float, float], tuple[float, float]]],
    coord: float,
    horizontal: bool,
) -> list[tuple[float, float]]:
    hits: list[float] = []
    for (x1, y1), (x2, y2) in segs:
        a1, b1, a2, b2 = (y1, x1, y2, x2) if horizontal else (x1, y1, x2, y2)
        if (a1 <= coord < a2) or (a2 <= coord < a1):
            t = (coord - a1) / (a2 - a1)
            hits.append(b1 + t * (b2 - b1))
    hits.sort()
    return [(hits[i], hits[i + 1]) for i in range(0, len(hits) - 1, 2)]


def _tune_s_vector_aperture(
    glyph: ufoLib2.objects.Glyph, cp: int, ppem: int, is_mono: bool = False, is_bold: bool = False
) -> None:
    """
    Pure vector-outline aperture tuning for 's' (U+0073) at UPM = 100 * P:
    Ensures full pixel-locked x-height at 14-16px and preserves >= 1.35px bowl thickness
    while guaranteeing terminal-to-spine separation so ttfautohint + MONO never pinches.
    """
    if not glyph.contours or cp != 0x0073 or ppem > 32:
        return
    if ppem in (14, 16):
        target_h = {14: 800.0, 16: 900.0}[ppem]
        b0 = glyph_bounds(glyph)
        if b0 is not None and b0[3] > b0[1]:
            sy = target_h / (b0[3] - b0[1])
            if sy > 1.02:
                ty = -b0[1] * sy
                rec = rec_from_glyph(glyph)
                glyph.clearContours()
                rec.replay(TransformPen(RoundingSegmentPen(glyph.getPen()), (1.0, 0.0, 0.0, sy, 0.0, ty)))

    sk = pathops.Path()
    glyph.draw(sk.getPen())
    sk.simplify(fix_winding=True)
    b = sk.bounds
    if not b:
        return
    xmin, ymin, xmax, ymax = b
    w = xmax - xmin
    h = ymax - ymin
    if w < 200.0 or h < 400.0:
        return

    segs = _flatten_pathops_segments(sk)
    if is_bold:
        min_gap_u = 215.0 if ppem <= 16 else (195.0 if ppem <= 20 else 145.0)
        min_bowl_u = 120.0 if ppem <= 16 else 135.0
    else:
        min_gap_u = 155.0 if ppem <= 18 else 135.0
        min_bowl_u = 135.0
    cut = pathops.Path()
    has_cut = False
    dx = max(22.0, 0.055 * w)

    # Bottom-left bay aperture
    for x in np.linspace(xmin - 25.0, xmin + 0.45 * w, 28):
        ivs = _scan_axis_intervals(segs, float(x), horizontal=False)
        if len(ivs) >= 2:
            term_top = ivs[0][1]
            spine_bot = ivs[1][0]
            gap = spine_bot - term_top
            if 0.0 <= gap < min_gap_u and (term_top - ivs[0][0]) > min_bowl_u:
                new_term_top = max(ivs[0][0] + min_bowl_u, spine_bot - min_gap_u)
                if new_term_top < term_top:
                    r = pathops.Path()
                    p = r.getPen()
                    p.moveTo((float(x) - dx, new_term_top))
                    p.lineTo((float(x) + dx, new_term_top))
                    p.lineTo((float(x) + dx, spine_bot - 2.0))
                    p.lineTo((float(x) - dx, spine_bot - 2.0))
                    p.closePath()
                    cut = pathops.op(cut, r, pathops.PathOp.UNION) if has_cut else r
                    has_cut = True
        elif len(ivs) == 1 and x < xmin + 0.25 * w:
            y0_i, y1_i = ivs[0]
            if y1_i - y0_i > 320.0:
                y_mid_s = ymin + 0.44 * h
                r = pathops.Path()
                p = r.getPen()
                p.moveTo((float(x) - dx, y_mid_s - 0.55 * min_gap_u))
                p.lineTo((float(x) + dx, y_mid_s - 0.55 * min_gap_u))
                p.lineTo((float(x) + dx, y_mid_s + 0.45 * min_gap_u))
                p.lineTo((float(x) - dx, y_mid_s + 0.45 * min_gap_u))
                p.closePath()
                cut = pathops.op(cut, r, pathops.PathOp.UNION) if has_cut else r
                has_cut = True

    # Top-right bay aperture
    for x in np.linspace(xmax - 0.45 * w, xmax + 25.0, 28):
        ivs = _scan_axis_intervals(segs, float(x), horizontal=False)
        if len(ivs) >= 2:
            spine_top = ivs[-2][1]
            term_bot = ivs[-1][0]
            gap = term_bot - spine_top
            if 0.0 <= gap < min_gap_u and (ivs[-1][1] - term_bot) > min_bowl_u:
                new_term_bot = min(ivs[-1][1] - min_bowl_u, spine_top + min_gap_u)
                if new_term_bot > term_bot:
                    r = pathops.Path()
                    p = r.getPen()
                    p.moveTo((float(x) - dx, spine_top + 2.0))
                    p.lineTo((float(x) + dx, spine_top + 2.0))
                    p.lineTo((float(x) + dx, new_term_bot))
                    p.lineTo((float(x) - dx, new_term_bot))
                    p.closePath()
                    cut = pathops.op(cut, r, pathops.PathOp.UNION) if has_cut else r
                    has_cut = True
        elif len(ivs) == 1 and x > xmax - 0.25 * w:
            y0_i, y1_i = ivs[0]
            if y1_i - y0_i > 320.0:
                y_mid_s = ymin + 0.56 * h
                r = pathops.Path()
                p = r.getPen()
                p.moveTo((float(x) - dx, y_mid_s - 0.45 * min_gap_u))
                p.lineTo((float(x) + dx, y_mid_s - 0.45 * min_gap_u))
                p.lineTo((float(x) + dx, y_mid_s + 0.55 * min_gap_u))
                p.lineTo((float(x) - dx, y_mid_s + 0.55 * min_gap_u))
                p.closePath()
                cut = pathops.op(cut, r, pathops.PathOp.UNION) if has_cut else r
                has_cut = True

    if has_cut:
        carved = pathops.op(sk, cut, pathops.PathOp.DIFFERENCE)
        carved.simplify(fix_winding=True)
        glyph.clearContours()
        carved.draw(RoundingSegmentPen(SegmentToPointPen(glyph.getPointPen())))


def _signed_contour_area(pts: list[tuple[float, float]]) -> float:
    area = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return 0.5 * area


def _split_outer_and_hole_paths(sk: pathops.Path) -> tuple[pathops.Path, pathops.Path]:
    """Separate simplified pathops.Path into outer solid contours and inner counter hole contours."""
    outer = pathops.Path()
    holes = pathops.Path()
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
            contours.append((_signed_contour_area(cur_poly), cur_verbs))
            cur_verbs = []
            cur_poly = []
    if not contours:
        return outer, holes
    largest_area = max(contours, key=lambda item: abs(item[0]))[0]
    outer_sign = 1.0 if largest_area >= 0.0 else -1.0
    o_pen = outer.getPen()
    h_pen = holes.getPen()
    for area, vlist in contours:
        pen = o_pen if (area * outer_sign >= 0.0) else h_pen
        for verb, pts in vlist:
            if verb == pathops.PathVerb.MOVE:
                pen.moveTo(pts[0])
            elif verb == pathops.PathVerb.LINE:
                pen.lineTo(pts[0])
            elif verb == pathops.PathVerb.QUAD:
                pen.qCurveTo(*pts)
            elif verb == pathops.PathVerb.CUBIC:
                pen.curveTo(*pts)
            elif verb == pathops.PathVerb.CLOSE:
                pen.closePath()
    return outer, holes


_OPEN_BAY_EXCLUDE = {ord(c) for c in "sScCGezZ235"}


def _close_vector_ink_traps(glyph: ufoLib2.objects.Glyph, cp: int | None, ppem: int) -> None:
    """
    Fill sub-pixel acute ink traps (< 1.65px) on the outer perimeter of alphanumeric glyphs
    (with counters temporarily solid via _split_outer_and_hole_paths) BEFORE hinting &
    rasterization, then subtract the preserved inner counter holes back cleanly.
    """
    if (
        cp is None
        or not (0x0030 <= cp <= 0x03FF)
        or not chr(cp).isalnum()
        or cp in _OPEN_BAY_EXCLUDE
        or not glyph.contours
    ):
        return
    sk = pathops.Path()
    glyph.draw(sk.getPen())
    sk.simplify(fix_winding=True)
    b = sk.bounds
    if not b:
        return
    xmin, ymin, xmax, ymax = b
    if xmax - xmin < 120.0 or ymax - ymin < 180.0:
        return

    outer, holes = _split_outer_and_hole_paths(sk)
    if not outer.bounds:
        return

    segs = _flatten_pathops_segments(outer)
    slit_u = 165.0 if ppem <= 16 else 145.0
    step_u = 15.0
    look_steps = 18
    bridges = pathops.Path()
    has_bridge = False

    # Horizontal scanlines on outer contour
    ys = np.arange(ymin + 8.0, ymax - 8.0, step_u)
    h_scans = [_scan_axis_intervals(segs, float(y), horizontal=True) for y in ys]
    for idx, y in enumerate(ys):
        ivs = h_scans[idx]
        for k in range(len(ivs) - 1):
            g_l, g_r = ivs[k][1], ivs[k + 1][0]
            if 0.5 < (g_r - g_l) <= slit_u and any(
                0 <= idx + d < len(ys) and any(a0 - 8.0 <= g_l and g_r <= a1 + 8.0 for a0, a1 in h_scans[idx + d])
                for d in range(-look_steps, look_steps + 1)
                if d != 0
            ):
                pr = pathops.Path()
                p = pr.getPen()
                y0, y1 = float(y) - 0.8 * step_u, float(y) + 0.8 * step_u
                p.moveTo((g_l - 8.0, y0))
                p.lineTo((g_r + 8.0, y0))
                p.lineTo((g_r + 8.0, y1))
                p.lineTo((g_l - 8.0, y1))
                p.closePath()
                bridges = pathops.op(bridges, pr, pathops.PathOp.UNION) if has_bridge else pr
                has_bridge = True

    # Vertical scanlines on outer contour
    xs = np.arange(xmin + 8.0, xmax - 8.0, step_u)
    v_scans = [_scan_axis_intervals(segs, float(x), horizontal=False) for x in xs]
    for idx, x in enumerate(xs):
        ivs = v_scans[idx]
        for k in range(len(ivs) - 1):
            g_b, g_t = ivs[k][1], ivs[k + 1][0]
            if 0.5 < (g_t - g_b) <= slit_u and any(
                0 <= idx + d < len(xs) and any(a0 - 8.0 <= g_b and g_t <= a1 + 8.0 for a0, a1 in v_scans[idx + d])
                for d in range(-look_steps, look_steps + 1)
                if d != 0
            ):
                pr = pathops.Path()
                p = pr.getPen()
                x0, x1 = float(x) - 0.8 * step_u, float(x) + 0.8 * step_u
                p.moveTo((x0, g_b - 8.0))
                p.lineTo((x1, g_b - 8.0))
                p.lineTo((x1, g_t + 8.0))
                p.lineTo((x0, g_t + 8.0))
                p.closePath()
                bridges = pathops.op(bridges, pr, pathops.PathOp.UNION) if has_bridge else pr
                has_bridge = True

    if has_bridge:
        merged_outer = pathops.op(outer, bridges, pathops.PathOp.UNION)
        final_path = pathops.op(merged_outer, holes, pathops.PathOp.DIFFERENCE) if holes.bounds else merged_outer
        final_path.simplify(fix_winding=True)
        glyph.clearContours()
        final_path.draw(RoundingSegmentPen(SegmentToPointPen(glyph.getPointPen())))


def compute_pixel_vertical_metrics(ppem: int) -> tuple[int, int, int, int]:
    """
    Compute integer pixel (ascent_px, descent_px, cap_px, xh_px) for a given PPEM.
    Guarantees sufficient x-height at 12-16 px for >=1px interior counters and
    headroom for tall math/accented glyphs without clipping.
    """
    ascent_px = math.ceil(0.85 * ppem) + 2
    descent_px = math.ceil(0.25 * ppem) + 2
    cap_px = max(7, round(0.71 * ppem))
    if ppem <= 12:
        xh_px = 7
    elif ppem <= 14:
        xh_px = 8
    elif ppem <= 16:
        xh_px = 9
    else:
        xh_px = max(9, round(0.54 * ppem))
    return ascent_px, descent_px, cap_px, xh_px


def _snap_glyph_to_grid(
    glyph: ufoLib2.objects.Glyph,
    cp: int | None,
    ppem: int,
    ascent_px: int,
    descent_px: int,
    cap_px: int,
    target_stem_px: int,
    is_italic: bool,
    is_mono: bool,
    mono_adv_u: int,
    is_bold: bool = False,
) -> None:
    """Apply UPM=100*P sub-grid snapping, baseline/cap lock, stem snapping, and clip containment."""
    grid = 100.0
    asc_u = ascent_px * grid
    desc_u = -descent_px * grid
    cap_u = cap_px * grid

    # 1. Monospace advance lock & horizontal centering
    if is_mono:
        old_w = float(glyph.width or mono_adv_u)
        if abs(old_w - mono_adv_u) > 1.0 and (glyph.contours or glyph.components):
            dx = round(((mono_adv_u - old_w) * 0.5) / grid) * grid
            if dx != 0.0:
                rec = rec_from_glyph(glyph)
                glyph.clearContours()
                rec.replay(TransformPen(RoundingSegmentPen(glyph.getPen()), (1.0, 0.0, 0.0, 1.0, dx, 0.0)))
        glyph.width = mono_adv_u
    else:
        # Snap proportional advance width to nearest integer pixel (100 units)
        glyph.width = max(0, int(round(float(glyph.width) / grid) * 100))

    if not glyph.contours:
        return

    # 2. Baseline & Cap-Height lock on uppercase Latin/Greek & digits (G_METRICS)
    b = glyph_bounds(glyph)
    if b is not None and cp in CAP_LOCK_CPS:
        _, y_min, _, y_max = b
        tol = max(55.0, 0.08 * cap_u)
        if -tol <= y_min <= tol and (cap_u - tol) <= y_max <= (cap_u + tol) and y_max > y_min:
            sy = cap_u / (y_max - y_min)
            ty = -y_min * sy
            rec = rec_from_glyph(glyph)
            glyph.clearContours()
            rec.replay(TransformPen(RoundingSegmentPen(glyph.getPen()), (1.0, 0.0, 0.0, sy, 0.0, ty)))

    # 2b. Tune 's' vector aperture & fill sub-pixel ink traps before snapping
    if cp == 0x0073:
        _tune_s_vector_aperture(glyph, cp, ppem, is_mono=is_mono, is_bold=is_bold)
    _close_vector_ink_traps(glyph, cp, ppem)

    # 2c. Prevent 'i' and 'j' tittle dot from merging into the stem in bold strikes
    if cp in (0x0069, 0x006A) and len(glyph.contours) >= 2:
        c_bounds = []
        for idx_c, cnt in enumerate(glyph.contours):
            ys_c = [pt.y for pt in cnt.points]
            if ys_c:
                c_bounds.append((max(ys_c), min(ys_c), idx_c))
        if len(c_bounds) >= 2:
            c_bounds.sort(key=lambda item: item[0])
            stem_ymax, _, _ = c_bounds[-2]
            dot_ymax, dot_ymin, dot_idx = c_bounds[-1]
            if dot_ymin - stem_ymax < 115.0:
                shift_y = min(asc_u - 15.0 - dot_ymax, 115.0 - (dot_ymin - stem_ymax))
                if shift_y > 0.0:
                    for pt in glyph.contours[dot_idx].points:
                        pt.y = round(pt.y + shift_y)

    # 3. Snap vertical/horizontal on-curve segments for upright glyphs
    if not is_italic:
        for cnt in glyph.contours:
            pts = cnt.points
            n = len(pts)
            for i in range(n):
                p0 = pts[i]
                p1 = pts[(i + 1) % n]
                if abs(p0.x - p1.x) <= 4.0 and abs(p0.y - p1.y) >= 0.16 * ppem * grid:
                    sx = round(0.5 * (p0.x + p1.x) / grid) * grid
                    p0.x = sx
                    p1.x = sx
                if abs(p0.y - p1.y) <= 4.0 and abs(p0.x - p1.x) >= 0.16 * ppem * grid:
                    sy_v = round(0.5 * (p0.y + p1.y) / grid) * grid
                    p0.y = sy_v
                    p1.y = sy_v

    # 4. Exact stem width enforcement on 'I' and 'H' vertical/slanted stems
    if cp in (0x0048, 0x0049):
        target_w = target_stem_px * grid
        if not is_italic:
            b_u = glyph_bounds(glyph)
            if cp == 0x0049 and b_u is not None:
                # 'I': snap main vertical stem (longest vertical segments)
                v_segs = []
                for cnt in glyph.contours:
                    pts = cnt.points
                    n = len(pts)
                    for i in range(n):
                        p0, p1 = pts[i], pts[(i + 1) % n]
                        if abs(p0.x - p1.x) <= 2.0 and abs(p0.y - p1.y) >= 0.30 * cap_u:
                            v_segs.append((cnt, i, (i + 1) % n, 0.5 * (p0.x + p1.x)))
                v_segs.sort(key=lambda item: item[3])
                if len(v_segs) == 2:
                    cL, iL0, iL1, xL = v_segs[0]
                    cR, iR0, iR1, _ = v_segs[1]
                    new_xL = round(xL / grid) * grid
                    new_xR = new_xL + target_w
                    cL.points[iL0].x = cL.points[iL1].x = new_xL
                    cR.points[iR0].x = cR.points[iR1].x = new_xR
            elif cp == 0x0048 and b_u is not None:
                # 'H': split into left stem and right stem around horizontal midpoint
                mid_x = 0.5 * (b_u[0] + b_u[2])
                for is_left in (True, False):
                    half_segs = []
                    for cnt in glyph.contours:
                        pts = cnt.points
                        n = len(pts)
                        for i in range(n):
                            p0, p1 = pts[i], pts[(i + 1) % n]
                            xm = 0.5 * (p0.x + p1.x)
                            if (
                                abs(p0.x - p1.x) <= 4.0
                                and abs(p0.y - p1.y) >= 0.18 * cap_u
                                and ((is_left and xm < mid_x) or (not is_left and xm > mid_x))
                            ):
                                half_segs.append((cnt, i, (i + 1) % n, xm))
                    if len(half_segs) >= 2:
                        xs_h = [s[3] for s in half_segs]
                        x_min_h, x_max_h = min(xs_h), max(xs_h)
                        x_mid_stem = 0.5 * (x_min_h + x_max_h)
                        if is_left:
                            new_out = round(x_min_h / grid) * grid
                            new_in = new_out + target_w
                            for cnt, i0, i1, xm in half_segs:
                                nx = new_out if xm < x_mid_stem else new_in
                                cnt.points[i0].x = cnt.points[i1].x = nx
                        else:
                            new_out = round(x_max_h / grid) * grid
                            new_in = new_out - target_w
                            for cnt, i0, i1, xm in half_segs:
                                nx = new_out if xm > x_mid_stem else new_in
                                cnt.points[i0].x = cnt.points[i1].x = nx
        else:
            # Slanted stems: sample at y = 0.25*cap_u and y = 0.75*cap_u (avoids 'H' crossbar)
            b_s = glyph_bounds(glyph)
            if b_s is not None:
                _, y_min_s, _, y_max_s = b_s
                measured_ws: list[float] = []
                for frac in (0.25, 0.75):
                    sample_y = y_min_s + frac * (y_max_s - y_min_s)
                    xs_cross: list[float] = []
                    for cnt in glyph.contours:
                        pts = cnt.points
                        n = len(pts)
                        for i in range(n):
                            p0, p1 = pts[i], pts[(i + 1) % n]
                            if ((p0.y <= sample_y <= p1.y) or (p1.y <= sample_y <= p0.y)) and abs(p1.y - p0.y) > 1.0:
                                t = (sample_y - p0.y) / (p1.y - p0.y)
                                xs_cross.append(p0.x + t * (p1.x - p0.x))
                    xs_cross.sort()
                    if cp == 0x0049 and len(xs_cross) == 2:
                        measured_ws.append(xs_cross[1] - xs_cross[0])
                    elif cp == 0x0048 and len(xs_cross) == 4:
                        measured_ws.append(xs_cross[1] - xs_cross[0])
                        measured_ws.append(xs_cross[3] - xs_cross[2])
                if measured_ws:
                    cur_w = sum(measured_ws) / len(measured_ws)
                    desired_w = target_w + 18.0
                    delta_w = desired_w - cur_w
                    if abs(delta_w) > 8.0:
                        # Pure horizontal point-shift around stem centerline(s): zero vertical distortion!
                        half_d = 0.5 * delta_w
                        b_all = glyph_bounds(glyph)
                        if b_all is not None:
                            x_mid_all = 0.5 * (b_all[0] + b_all[2])
                            slope = math.tan(math.radians(10.0))
                            y_mid_all = 0.5 * (b_all[1] + b_all[3])
                            if cp == 0x0049:
                                for cnt in glyph.contours:
                                    for pt in cnt.points:
                                        # Only widen vertical shaft points (middle 70% height) or full glyph if sans-serif
                                        cx_y = x_mid_all + (pt.y - y_mid_all) * slope
                                        if abs(pt.x - cx_y) <= 1.8 * max(cur_w, target_w):
                                            pt.x = round(pt.x + (half_d if pt.x >= cx_y else -half_d))
                            elif cp == 0x0048:
                                # Shift outer/inner edges of left and right stems horizontally
                                # Sample left and right stem centers at mid_y
                                for cnt in glyph.contours:
                                    for pt in cnt.points:
                                        pass
                                sx_stem = desired_w / max(10.0, cur_w)
                                rec = rec_from_glyph(glyph)
                                glyph.clearContours()
                                rec.replay(TransformPen(RoundingSegmentPen(glyph.getPen()), (sx_stem, 0.0, 0.0, 1.0, 0.0, 0.0)))
                                glyph.width = max(glyph.width, int(round(glyph.width * sx_stem / grid) * 100))

    # 5. Bounding-box containment inside [desc_u + 15, asc_u - 15] (G_CLIP)
    b2 = glyph_bounds(glyph)
    if b2 is not None:
        _, y_min, _, y_max = b2
        lo_lim = desc_u + 15.0
        hi_lim = asc_u - 15.0
        if y_max > hi_lim or y_min < lo_lim:
            span = max(1.0, y_max - y_min)
            avail = max(100.0, hi_lim - lo_lim)
            if span > avail:
                sy = avail / span
                ty = lo_lim - y_min * sy
                rec = rec_from_glyph(glyph)
                glyph.clearContours()
                rec.replay(TransformPen(RoundingSegmentPen(glyph.getPen()), (1.0, 0.0, 0.0, sy, 0.0, ty)))
            else:
                dy = (hi_lim - y_max) if y_max > hi_lim else (lo_lim - y_min)
                rec = rec_from_glyph(glyph)
                glyph.clearContours()
                rec.replay(TransformPen(RoundingSegmentPen(glyph.getPen()), (1.0, 0.0, 0.0, 1.0, 0.0, dy)))


def prepare_snapped_ufo(
    base_ufo: ufoLib2.Font,
    sym_ufo: ufoLib2.Font,
    ppem: int,
    modifier: str,
    style: str,
    target_stem_px: int,
    mono_advance_px: int,
) -> ufoLib2.Font:
    """
    Graft weight-matched symbols, union overlaps, scale to UPM = 100 * P,
    and apply sub-grid snapping to produce a compile-ready UFO 3.
    """
    build_upm = 100 * ppem
    scale = float(build_upm) / float(base_ufo.info.unitsPerEm or 1000)
    ascent_px, descent_px, cap_px, xh_px = compute_pixel_vertical_metrics(ppem)
    is_italic = "italic" in style
    is_mono = modifier == "mono"
    mono_adv_u = 100 * mono_advance_px

    out = ufoLib2.Font()
    ital_angle = float(base_ufo.info.italicAngle or 0.0)
    set_standard_fontinfo(
        out,
        family_name=f"EPD {modifier.capitalize()}",
        style_name=f"{style} {ppem}px",
        upm=build_upm,
        ascender=ascent_px * 100,
        descender=-descent_px * 100,
        cap_height=cap_px * 100,
        x_height=xh_px * 100,
        italic_angle=ital_angle,
    )
    out.features.text = default_features_fea()

    sym_idx = build_unicode_index(sym_ufo)
    base_idx = build_unicode_index(base_ufo)

    # Start with .notdef
    glyph_order: list[str] = []
    if ".notdef" in base_ufo:
        g_nd = out.newGlyph(".notdef")
        rec = rec_from_glyph(base_ufo[".notdef"])
        rec.replay(TransformPen(RoundingSegmentPen(g_nd.getPen()), (scale, 0.0, 0.0, scale, 0.0, 0.0)))
        g_nd.width = mono_adv_u if is_mono else round(base_ufo[".notdef"].width * scale)
        glyph_order.append(".notdef")

    # Union of all codepoints from base and symbols
    all_cps = sorted(set(base_idx.keys()) | set(sym_idx.keys()))
    for cp in all_cps:
        # Use weight/slant-matched symbol master for all non-ASCII-Latin symbols
        use_sym = (cp >= 0x00A0 or cp not in base_idx) and (cp in sym_idx)
        src_ufo = sym_ufo if use_sym else base_ufo
        src_gname = sym_idx[cp] if use_sym else base_idx[cp]
        src_g = src_ufo[src_gname]

        dst_name = src_gname
        if dst_name in out:
            dst_name = f"uni{cp:04X}"
        g = out.newGlyph(dst_name)
        g.unicodes = [cp]
        g.width = round(float(src_g.width) * scale)
        glyph_order.append(dst_name)

        rec = rec_from_glyph(src_g)
        rec.replay(TransformPen(RoundingSegmentPen(g.getPen()), (scale, 0.0, 0.0, scale, 0.0, 0.0)))
        union_and_extremize_glyph(g, round_coords=True)
        _snap_glyph_to_grid(
            g,
            cp=cp,
            ppem=ppem,
            ascent_px=ascent_px,
            descent_px=descent_px,
            cap_px=cap_px,
            target_stem_px=target_stem_px,
            is_italic=is_italic,
            is_mono=is_mono,
            mono_adv_u=mono_adv_u,
            is_bold=("bold" in style),
        )

    out.lib["public.glyphOrder"] = glyph_order
    # Keep pathops imported for callers
    _ = pathops.Path
    _ = SegmentToPointPen
    return out
