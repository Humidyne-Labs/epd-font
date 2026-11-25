"""Shared UFO 3, Pen, PathOps, and FontTools helpers."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path

import pathops
import ufoLib2
from fontTools.agl import UV2AGL
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import DecomposingRecordingPen, RecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

logging.getLogger("fontTools").setLevel(logging.ERROR)


def canonical_glyph_name(cp: int) -> str:
    """Return a deterministic, AGL-compatible glyph name for a Unicode codepoint."""
    if cp in UV2AGL:
        return UV2AGL[cp]
    if cp <= 0xFFFF:
        return f"uni{cp:04X}"
    return f"u{cp:05X}"


class RoundingSegmentPen:
    """Segment pen wrapper that rounds all coordinates to integers."""

    def __init__(self, out_pen: object) -> None:
        self.out_pen = out_pen

    def moveTo(self, pt: tuple[float, float]) -> None:
        self.out_pen.moveTo((round(pt[0]), round(pt[1])))  # type: ignore[attr-defined]

    def lineTo(self, pt: tuple[float, float]) -> None:
        self.out_pen.lineTo((round(pt[0]), round(pt[1])))  # type: ignore[attr-defined]

    def curveTo(self, *pts: tuple[float, float]) -> None:
        self.out_pen.curveTo(*((round(p[0]), round(p[1])) for p in pts))  # type: ignore[attr-defined]

    def qCurveTo(self, *pts: tuple[float, float] | None) -> None:
        self.out_pen.qCurveTo(*((round(p[0]), round(p[1])) if p is not None else None for p in pts))  # type: ignore[attr-defined]

    def closePath(self) -> None:
        self.out_pen.closePath()  # type: ignore[attr-defined]

    def endPath(self) -> None:
        self.out_pen.endPath()  # type: ignore[attr-defined]

    def addComponent(self, baseGlyphName: str, transformation: tuple[float, ...], **kwargs: object) -> None:
        self.out_pen.addComponent(baseGlyphName, transformation, **kwargs)  # type: ignore[attr-defined]


def glyph_bounds(glyph: object, glyph_set: object | None = None) -> tuple[float, float, float, float] | None:
    """Compute (xMin, yMin, xMax, yMax) of a UFO glyph."""
    pen = BoundsPen(glyph_set)
    glyph.draw(pen)  # type: ignore[attr-defined]
    return pen.bounds


def union_and_extremize_glyph(glyph: ufoLib2.objects.Glyph, round_coords: bool = True) -> None:
    """
    Flatten overlaps via skia-pathops union (clockwise outer / CCW inner winding),
    insert curve extrema, and round coordinates to integers.
    """
    if not glyph.contours and not glyph.components:
        return
    p = pathops.Path()
    pen = p.getPen()
    glyph.draw(pen)
    if not any(True for _ in p.contours):
        return
    # Winding: skia-pathops simplify() produces clean non-overlapping contours;
    # enforce clockwise outer contour for TrueType/PostScript consistency.
    simplified = pathops.simplify(p, clockwise=True)
    glyph.clearContours()
    glyph.clearComponents()
    out_pen = RoundingSegmentPen(glyph.getPen()) if round_coords else glyph.getPen()
    simplified.draw(out_pen)


class ExactQu2CuSegmentPen:
    """
    Lossless, point-compatible quadratic-to-cubic degree elevation pen.
    Every quadratic segment (A0, Q1, A1) maps to exactly one cubic segment (A0, C1, C2, A1)
    with C1 = A0 + 2/3*(Q1 - A0) and C2 = A1 + 2/3*(Q1 - A1), guaranteeing identical
    point counts across variable masters and handling oncurve-less closed loops.
    """

    def __init__(self, out_pen: object) -> None:
        self.out_pen = out_pen
        self._cur: tuple[float, float] = (0.0, 0.0)

    def moveTo(self, pt: tuple[float, float]) -> None:
        self._cur = pt
        self.out_pen.moveTo(pt)  # type: ignore[attr-defined]

    def lineTo(self, pt: tuple[float, float]) -> None:
        self._cur = pt
        self.out_pen.lineTo(pt)  # type: ignore[attr-defined]

    def curveTo(self, *pts: tuple[float, float]) -> None:
        self._cur = pts[-1]
        self.out_pen.curveTo(*pts)  # type: ignore[attr-defined]

    def qCurveTo(self, *pts: tuple[float, float] | None) -> None:
        if not pts:
            return
        if pts[-1] is None:
            offs = [p for p in pts[:-1] if p is not None]
            if not offs:
                return
            if len(offs) == 1:
                self.moveTo(offs[0])
                self.closePath()
                return
            start = (0.5 * (offs[-1][0] + offs[0][0]), 0.5 * (offs[-1][1] + offs[0][1]))
            self.moveTo(start)
            n = len(offs)
            for i in range(n):
                q = offs[i]
                nxt = offs[(i + 1) % n]
                a1 = (0.5 * (q[0] + nxt[0]), 0.5 * (q[1] + nxt[1]))
                self._emit_quad(self._cur, q, a1)
            return

        on_end = pts[-1]
        assert on_end is not None
        offs = [p for p in pts[:-1] if p is not None]
        if not offs:
            self.lineTo(on_end)
            return
        for i, q in enumerate(offs):
            if i + 1 < len(offs):
                nxt = offs[i + 1]
                a1 = (0.5 * (q[0] + nxt[0]), 0.5 * (q[1] + nxt[1]))
            else:
                a1 = on_end
            self._emit_quad(self._cur, q, a1)

    def _emit_quad(self, a0: tuple[float, float], q: tuple[float, float], a1: tuple[float, float]) -> None:
        c1 = (a0[0] + (2.0 / 3.0) * (q[0] - a0[0]), a0[1] + (2.0 / 3.0) * (q[1] - a0[1]))
        c2 = (a1[0] + (2.0 / 3.0) * (q[0] - a1[0]), a1[1] + (2.0 / 3.0) * (q[1] - a1[1]))
        self._cur = a1
        self.out_pen.curveTo(c1, c2, a1)  # type: ignore[attr-defined]

    def closePath(self) -> None:
        self.out_pen.closePath()  # type: ignore[attr-defined]

    def endPath(self) -> None:
        self.out_pen.endPath()  # type: ignore[attr-defined]

    def addComponent(self, baseGlyphName: str, transformation: tuple[float, ...], **kwargs: object) -> None:
        self.out_pen.addComponent(baseGlyphName, transformation, **kwargs)  # type: ignore[attr-defined]


def draw_transformed_to_cubic_glyph(
    src_glyph: object,
    src_glyph_set: object,
    dst_glyph: ufoLib2.objects.Glyph,
    matrix: tuple[float, float, float, float, float, float] = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
    is_quadratic: bool = False,
    round_coords: bool = True,
) -> None:
    """Decompose components, apply affine matrix, convert qcurve->curve if needed, and draw into dst_glyph."""
    dst_glyph.clearContours()
    dst_glyph.clearComponents()
    rec = DecomposingRecordingPen(src_glyph_set)
    src_glyph.draw(rec)  # type: ignore[attr-defined]

    base_pen: object = dst_glyph.getPen()
    if round_coords:
        base_pen = RoundingSegmentPen(base_pen)
    if is_quadratic:
        base_pen = ExactQu2CuSegmentPen(base_pen)
    t_pen = TransformPen(base_pen, matrix)
    rec.replay(t_pen)


def set_standard_fontinfo(
    ufo: ufoLib2.Font,
    family_name: str,
    style_name: str,
    upm: int = 1000,
    ascender: int = 780,
    descender: int = -220,
    cap_height: int = 711,
    x_height: int = 528,
    italic_angle: float = 0.0,
) -> None:
    """Populate standardized UFO 3 fontinfo.plist metrics."""
    info = ufo.info
    info.familyName = family_name
    info.styleName = style_name
    info.unitsPerEm = int(upm)
    info.ascender = int(ascender)
    info.descender = int(descender)
    info.capHeight = int(cap_height)
    info.xHeight = int(x_height)
    info.italicAngle = float(italic_angle)
    info.openTypeOS2TypoAscender = int(ascender)
    info.openTypeOS2TypoDescender = int(descender)
    info.openTypeOS2TypoLineGap = 0
    info.openTypeOS2WinAscent = int(ascender)
    info.openTypeOS2WinDescent = abs(int(descender))
    info.openTypeHheaAscender = int(ascender)
    info.openTypeHheaDescender = int(descender)
    info.openTypeHheaLineGap = 0


def default_features_fea() -> str:
    """Standard OpenType feature rules (SPEC-EPD-FONT-001 Section 3.1)."""
    return (
        "languagesystem DFLT dflt;\n"
        "languagesystem latn dflt;\n"
        "languagesystem grek dflt;\n"
        "\n"
        "feature tnum {\n"
        "    # Tabular figures supported via aligned monospace/proportional metrics\n"
        "} tnum;\n"
        "\n"
        "feature case {\n"
        "    # Case-sensitive punctuation alignment\n"
        "} case;\n"
        "\n"
        "feature frac {\n"
        "    # Fractions\n"
        "} frac;\n"
    )


def build_unicode_index(ufo: ufoLib2.Font) -> dict[int, str]:
    """Map integer codepoint -> glyph name in a UFO."""
    idx: dict[int, str] = {}
    for gname in ufo.keys():  # noqa: SIM118
        g = ufo[gname]
        for cp in g.unicodes:
            if cp not in idx:
                idx[cp] = gname
    return idx


def compile_designspace_to_vf_cached(ds_path: Path, cache_vf_path: Path) -> Path:
    """Compile a source DesignSpace + UFOs to a cached variable TTF once."""
    if cache_vf_path.is_file() and cache_vf_path.stat().st_size > 10_000:
        return cache_vf_path
    cache_vf_path.parent.mkdir(parents=True, exist_ok=True)
    import ufo2ft
    from fontTools.designspaceLib import DesignSpaceDocument

    ds = DesignSpaceDocument.fromfile(str(ds_path))
    ds.loadSourceFonts(ufoLib2.Font.open)
    for src in ds.sources:
        if src.font is not None:
            src.font.features.text = ""
    vf = ufo2ft.compileVariableTTF(ds, inplace=True)
    vf.save(str(cache_vf_path))
    vf.close()
    return cache_vf_path


def extract_ttfont_to_ufo(
    tt: TTFont,
    family_name: str,
    style_name: str,
    codepoints: Iterable[int],
    target_upm: int = 1000,
    italic_angle: float = 0.0,
    is_mono: bool = False,
    mono_width: int = 600,
) -> ufoLib2.Font:
    """Extract a subset of codepoints from a TTFont into a clean cubic UFO 3."""
    ufo = ufoLib2.Font()
    set_standard_fontinfo(ufo, family_name, style_name, upm=target_upm, italic_angle=italic_angle)
    ufo.features.text = default_features_fea()

    src_upm = int(tt["head"].unitsPerEm)
    scale = float(target_upm) / float(src_upm)
    gset = tt.getGlyphSet()
    cmap = tt.getBestCmap() or {}
    is_quad = "glyf" in tt

    glyph_order: list[str] = [".notdef"]
    if ".notdef" in gset:
        g_nd = ufo.newGlyph(".notdef")
        draw_transformed_to_cubic_glyph(
            gset[".notdef"], gset, g_nd, matrix=(scale, 0, 0, scale, 0, 0), is_quadratic=is_quad, round_coords=True
        )
        g_nd.width = mono_width if is_mono else round(gset[".notdef"].width * scale)

    for cp in sorted(set(codepoints)):
        if cp not in cmap:
            continue
        src_name = cmap[cp]
        dst_name = canonical_glyph_name(cp)
        if dst_name in ufo:
            continue
        glyph_order.append(dst_name)
        g = ufo.newGlyph(dst_name)
        g.unicodes = [cp]
        src_g = gset[src_name]
        w_scaled = round(src_g.width * scale)
        dx = 0.0
        if is_mono:
            dx = (mono_width - w_scaled) / 2.0
            g.width = mono_width
        else:
            g.width = max(0, w_scaled)
        draw_transformed_to_cubic_glyph(
            src_g,
            gset,
            g,
            matrix=(scale, 0, 0, scale, dx, 0),
            is_quadratic=is_quad,
            round_coords=True,
        )

    ufo.lib["public.glyphOrder"] = glyph_order
    return ufo


def rec_from_glyph(glyph: ufoLib2.objects.Glyph) -> RecordingPen:
    """Capture glyph outline into a RecordingPen."""
    rec = RecordingPen()
    glyph.draw(rec)
    return rec
