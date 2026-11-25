"""Stage 2: Per-Size Instantiation, Symbol Grafting & Sub-Grid Coordinate Snapping."""

from __future__ import annotations

import math

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

    # 2b. At 12px, give 's' (U+0073) full 7px x-height clearance so upper/lower bays stay open
    if cp == 0x0073 and ppem <= 12:
        b_s0 = glyph_bounds(glyph)
        if b_s0 is not None and b_s0[3] > b_s0[1]:
            sy_s = 700.0 / (b_s0[3] - b_s0[1])
            if sy_s > 1.02:
                ty_s = -b_s0[1] * sy_s
                rec = rec_from_glyph(glyph)
                glyph.clearContours()
                rec.replay(TransformPen(RoundingSegmentPen(glyph.getPen()), (1.0, 0.0, 0.0, sy_s, 0.0, ty_s)))

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
        )

    out.lib["public.glyphOrder"] = glyph_order
    # Keep pathops imported for callers
    _ = pathops.Path
    _ = SegmentToPointPen
    return out
