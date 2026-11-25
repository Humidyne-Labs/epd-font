"""Stage 3: TrueType Compilation, ttfautohint & FreeType FT_LOAD_TARGET_MONO Rasterization."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import freetype
import numpy as np
import ttfautohint
import ufo2ft
import ufoLib2
from fontTools.ttLib import TTFont

from runner.grid_snap import compute_pixel_vertical_metrics
from runner.math_psf import compute_betti_numbers


@dataclass
class RasterizedGlyph:
    codepoint: int
    glyph_id: int
    name: str
    adv_w_fp4: int
    advance_px: int
    box_w: int
    box_h: int
    ofs_x: int
    ofs_y: int
    bitmap: np.ndarray  # uint8 (box_h, box_w) values 0/1

    @property
    def rows(self) -> list[str]:
        if self.box_w <= 0 or self.box_h <= 0:
            return []
        return ["".join("#" if px else "." for px in row) for row in self.bitmap]

    def pack_1bpp_bytes(self) -> bytes:
        if self.box_w <= 0 or self.box_h <= 0:
            return b""
        flat = self.bitmap.reshape(-1)
        out = bytearray()
        cur = 0
        bit_cnt = 0
        for val in flat:
            cur = (cur << 1) | (1 if val else 0)
            bit_cnt += 1
            if bit_cnt == 8:
                out.append(cur)
                cur = 0
                bit_cnt = 0
        if bit_cnt > 0:
            out.append(cur << (8 - bit_cnt))
        return bytes(out)


@dataclass
class CompiledStrike:
    ppem: int
    modifier: str
    style: str
    symbol_name: str
    ttf_path: Path
    font_ascent: int
    font_descent: int
    line_height: int
    base_line: int
    glyphs: list[RasterizedGlyph]
    kern_pairs: list[tuple[int, int, int, int, int]]  # (l_gid, r_gid, l_cp, r_cp, kern_px)
    fallback_symbol: str | None = None
    expected_holes: dict[int, int] | None = None


def compile_and_hint_ufo(
    snapped_ufo: ufoLib2.Font,
    raw_ttf_path: Path,
    hinted_ttf_path: Path,
    hint_cfg: dict[str, Any],
) -> Path:
    """Compile snapped UFO to TTF via ufo2ft and hint with ttfautohint-py."""
    raw_ttf_path.parent.mkdir(parents=True, exist_ok=True)
    hinted_ttf_path.parent.mkdir(parents=True, exist_ok=True)

    tt = ufo2ft.compileTTF(snapped_ufo, removeOverlaps=False, inplace=True)
    tt.save(str(raw_ttf_path))
    tt.close()

    stem_mode_str = str(hint_cfg.get("stem_width_mode", "sss")).lower()
    # Map 'sss' or 'strong' -> 1 (STRONG), 'nnn'/'natural' -> -1, 'qqq'/'quantized' -> 0
    mode_val = 1 if stem_mode_str in ("strong", "sss") else 0

    ttfautohint.ttfautohint(
        in_file=str(raw_ttf_path),
        out_file=str(hinted_ttf_path),
        gray_stem_width_mode=mode_val,
        gdi_cleartype_stem_width_mode=mode_val,
        dw_cleartype_stem_width_mode=mode_val,
        increase_x_height=int(hint_cfg.get("increase_x_height", 0)),
        symbol=bool(hint_cfg.get("symbol_mode", True)),
        hinting_range_min=int(hint_cfg.get("hinting_range_min", 12)),
        hinting_range_max=int(hint_cfg.get("hinting_range_max", 40)),
        hinting_limit=int(hint_cfg.get("hinting_limit", 40)),
        no_info=True,
    )

    # Preserve exact pre-snapped 100*P sub-grid coordinates on cap-height, stem, and counter glyphs
    # so ttfautohint's Latin-only blue zones cannot introduce +/-1px drift vs Greek Δ/Ω or pinch counters.
    presnapped_cps = (
        set(range(0x0030, 0x003A))
        | set(range(0x0041, 0x005B))
        | (set(range(0x0391, 0x03AA)) - {0x03A2})
        | {0x2126, 0x0061, 0x0065, 0x0069, 0x006A, 0x006F, 0x0073, 0x03B1}
    )
    tt_hinted = TTFont(str(hinted_ttf_path))
    cmap_h = tt_hinted.getBestCmap() or {}
    glyf_tbl = tt_hinted.get("glyf")
    if glyf_tbl is not None:
        from fontTools.ttLib.tables import ttProgram

        changed = False
        for cp in presnapped_cps:
            gn = cmap_h.get(cp)
            if gn and gn in glyf_tbl:
                gl = glyf_tbl[gn]
                if hasattr(gl, "program") and gl.program and gl.program.bytecode:
                    gl.program = ttProgram.Program()
                    gl.program.fromBytecode(b"")
                    changed = True
        if changed:
            tt_hinted.save(str(hinted_ttf_path))
    tt_hinted.close()
    return hinted_ttf_path


def _extract_mono_bitmap(bmp: freetype.Bitmap) -> np.ndarray:
    rows, width = int(bmp.rows), int(bmp.width)
    if rows <= 0 or width <= 0:
        return np.zeros((0, 0), dtype=np.uint8)
    pitch = abs(int(bmp.pitch))
    buf = bmp.buffer
    arr = np.zeros((rows, width), dtype=np.uint8)
    for r in range(rows):
        row_off = r * pitch
        for c in range(width):
            byte_val = buf[row_off + (c >> 3)]
            if (byte_val >> (7 - (c & 7))) & 1:
                arr[r, c] = 1
    return arr


def _count_open_bays(fg: np.ndarray) -> int:
    ys, xs = np.nonzero(fg > 0)
    if len(xs) < 3:
        return 0
    pts = np.column_stack((xs, ys)).astype(np.int32)
    hull = cv2.convexHull(pts)
    hull_img = np.zeros_like(fg, dtype=np.uint8)
    cv2.fillConvexPoly(hull_img, hull, 1)
    open_mask = (hull_img > 0) & (fg == 0)
    n_op, _, stats_op, _ = cv2.connectedComponentsWithStats(open_mask.astype(np.uint8), connectivity=4)
    return sum(
        1
        for lbl in range(1, int(n_op))
        if int(stats_op[lbl, cv2.CC_STAT_WIDTH]) >= 1 and int(stats_op[lbl, cv2.CC_STAT_HEIGHT]) >= 1
    )


def heal_spurious_pinholes(arr: np.ndarray, max_holes: int) -> np.ndarray:
    """
    Remove spurious 1-2px enclosed white dropout specks (e.g. inside italic M, Μ, W, K)
    by keeping at most `max_holes` largest 4-connected interior background components.
    """
    if arr.size == 0 or np.count_nonzero(arr) == 0:
        return arr
    padded = np.pad((arr > 0).astype(np.uint8), 1, mode="constant", constant_values=0)
    num_bg, labels, stats, _ = cv2.connectedComponentsWithStats((1 - padded).astype(np.uint8), connectivity=4)
    ext_lbl = int(labels[0, 0])
    holes: list[tuple[int, int]] = []
    for lbl in range(1, int(num_bg)):
        if lbl == ext_lbl:
            continue
        holes.append((int(stats[lbl, cv2.CC_STAT_AREA]), lbl))
    if len(holes) <= max_holes:
        return arr
    holes.sort(reverse=True)
    keep_lbls = {lbl for _, lbl in holes[:max_holes]}
    out = arr.copy()
    inner_lbls = labels[1:-1, 1:-1]
    for _, lbl in holes:
        if lbl not in keep_lbls:
            out[inner_lbls == lbl] = 1
    return out


def enforce_min_stem_floor_safe(
    arr: np.ndarray,
    cp: int,
    target_floor_px: int,
    max_holes: int,
) -> tuple[np.ndarray, int]:
    """
    Thicken 1-px vertical/slanted stroke runs to `target_floor_px` ONLY when doing so
    preserves exact Betti topology (no plugged counters, no bridged inter-stem gaps).
    Returns (conditioned_bitmap, extra_right_cols).
    """
    if arr.size == 0 or cp < 0x0021 or cp > 0x03FF:
        return arr, 0
    if chr(cp) in ".,:;'\"!|/\\-_~^`·°":
        return arr, 0
    cur = arr.copy()
    extra_cols = 0
    open_bay_cp = cp in (0x0073, 0x0053, 0x0063, 0x0043, 0x0065, 0x0032, 0x0033, 0x0035, 0x007A)
    orig_bays = _count_open_bays(cur) if open_bay_cp else 0

    for min_w in range(2, target_floor_px + 1):
        h, w = cur.shape
        if h < 4 or w < 1:
            break
        b0_ref, b1_ref = compute_betti_numbers(cur)
        for r in range(h):
            runs: list[tuple[int, int]] = []
            in_r, s = False, 0
            for c in range(w):
                if cur[r, c] and not in_r:
                    s, in_r = c, True
                elif not cur[r, c] and in_r:
                    runs.append((s, c - 1))
                    in_r = False
            if in_r:
                runs.append((s, w - 1))
            if len(runs) > 3:
                continue
            for c0, c1 in runs:
                run_w = c1 - c0 + 1
                if run_w >= min_w:
                    continue
                has_vert = False
                for nr in (r - 1, r + 1):
                    if 0 <= nr < h and np.any(cur[nr, max(0, c0 - 1) : min(w, c1 + 2)]):
                        has_vert = True
                        break
                if not has_vert:
                    continue

                cands_x: list[int] = []
                if c1 + 1 < w:
                    if c1 + 2 >= w or cur[r, c1 + 2] == 0:
                        cands_x.append(c1 + 1)
                elif c1 + 1 == w:
                    cands_x.append(c1 + 1)
                if c0 - 1 >= 0 and (c0 - 2 < 0 or cur[r, c0 - 2] == 0):
                    cands_x.append(c0 - 1)

                for cx in cands_x:
                    if cx >= cur.shape[1]:
                        test = np.pad(cur, ((0, 0), (0, 1)), mode="constant", constant_values=0)
                    else:
                        test = cur.copy()
                    test[r, cx] = 1
                    b0_t, b1_t = compute_betti_numbers(test)
                    if b0_t != b0_ref or b1_t > min(b1_ref, max_holes) or b1_t < b1_ref:
                        continue
                    if open_bay_cp and _count_open_bays(test) < orig_bays:
                        continue
                    if cx >= cur.shape[1]:
                        extra_cols += 1
                    cur = test
                    w = cur.shape[1]
                    break
    return cur, extra_cols


def rasterize_ttf_mono(
    ttf_path: Path,
    ppem: int,
    modifier: str,
    style: str,
    codepoints: list[int],
    mono_advance_px: int | None = None,
    apply_conditioning: bool = True,
) -> CompiledStrike:
    """Rasterize a hinted TTF at PPEM using FT_LOAD_RENDER | FT_LOAD_TARGET_MONO."""
    ascent_px, descent_px, _, _ = compute_pixel_vertical_metrics(ppem)
    line_height = ascent_px + descent_px
    base_line = descent_px

    face = freetype.Face(str(ttf_path))
    load_flags = freetype.FT_LOAD_RENDER | freetype.FT_LOAD_TARGET_MONO

    tt = TTFont(str(ttf_path), lazy=True)
    cmap = tt.getBestCmap() or {}
    tt.close()

    expected_holes: dict[int, int] = {}
    _known_zero_hole = {
        0x004B, 0x004D, 0x004E, 0x0056, 0x0057, 0x0058, 0x0059, 0x005A,
        0x006B, 0x006D, 0x006E, 0x0076, 0x0077, 0x0078, 0x0079, 0x007A,
        0x0396, 0x039A, 0x039C, 0x039D, 0x03A7, 0x03BA, 0x03BC, 0x03BD, 0x03C7,
    }
    norm_flags = freetype.FT_LOAD_RENDER | freetype.FT_LOAD_TARGET_NORMAL
    face.set_pixel_sizes(0, 64)
    for cp in codepoints:
        if cp in cmap and 0x0021 <= cp <= 0x03FF:
            if cp in _known_zero_hole:
                expected_holes[cp] = 0
                continue
            face.load_char(cp, norm_flags)
            hb = face.glyph.bitmap
            if hb.rows > 0 and hb.width > 0:
                hi_arr = (
                    np.array(hb.buffer, dtype=np.uint8).reshape(hb.rows, hb.width) >= 128
                ).astype(np.uint8)
                _, b1_hi = compute_betti_numbers(hi_arr)
            else:
                b1_hi = 0
            expected_holes[cp] = b1_hi

    face.set_pixel_sizes(0, ppem)
    min_stem_floor = 3 if "bold" in style else 2

    glyphs: list[RasterizedGlyph] = []
    gid = 1
    for cp in sorted(set(codepoints)):
        if cp not in cmap:
            continue
        face.load_char(cp, load_flags)
        slot = face.glyph
        bmp = slot.bitmap
        arr = _extract_mono_bitmap(bmp)
        if apply_conditioning and arr.size > 0 and 0x0021 <= cp <= 0x03FF:
            max_h = expected_holes.get(cp, 2)
            arr = heal_spurious_pinholes(arr, max_h)
            if ppem <= 20:
                arr, _ = enforce_min_stem_floor_safe(arr, cp, min_stem_floor, max_h)

        box_h, box_w = int(arr.shape[0]), int(arr.shape[1])
        ofs_x = int(slot.bitmap_left)
        ofs_y = int(slot.bitmap_top) - box_h
        if modifier == "mono" and mono_advance_px is not None:
            adv_px = int(mono_advance_px)
            adv_fp4 = adv_px * 16
        else:
            adv_fp4 = max(0, round(float(slot.advance.x) / 4.0))
            adv_px = (adv_fp4 + 8) >> 4

        glyphs.append(
            RasterizedGlyph(
                codepoint=cp,
                glyph_id=gid,
                name=cmap[cp],
                adv_w_fp4=adv_fp4,
                advance_px=adv_px,
                box_w=box_w,
                box_h=box_h,
                ofs_x=ofs_x,
                ofs_y=ofs_y,
                bitmap=arr,
            )
        )
        gid += 1

    style_sym = style.replace("-", "_")
    symbol_name = f"humid1_font_epd_{modifier}_{style_sym}_{ppem}"
    fallback_sym = (
        f"humid1_icon_fa7_solid_{ppem}"
        if (modifier == "sans" and style == "normal")
        else f"humid1_font_epd_sans_normal_{ppem}"
    )
    return CompiledStrike(
        ppem=ppem,
        modifier=modifier,
        style=style,
        symbol_name=symbol_name,
        ttf_path=ttf_path,
        font_ascent=ascent_px,
        font_descent=descent_px,
        line_height=line_height,
        base_line=base_line,
        glyphs=glyphs,
        kern_pairs=[],
        fallback_symbol=fallback_sym,
        expected_holes=expected_holes,
    )
