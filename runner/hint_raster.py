"""Stage 3: TrueType Compilation, ttfautohint & FreeType FT_LOAD_TARGET_MONO Rasterization."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import freetype
import numpy as np
import ttfautohint
import ufo2ft
import ufoLib2
from fontTools.ttLib import TTFont

from runner.grid_snap import compute_pixel_vertical_metrics


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


def rasterize_ttf_mono(
    ttf_path: Path,
    ppem: int,
    modifier: str,
    style: str,
    codepoints: list[int],
    mono_advance_px: int | None = None,
) -> CompiledStrike:
    """Rasterize a hinted TTF at PPEM using FT_LOAD_RENDER | FT_LOAD_TARGET_MONO."""
    ascent_px, descent_px, _, _ = compute_pixel_vertical_metrics(ppem)
    line_height = ascent_px + descent_px
    base_line = descent_px

    face = freetype.Face(str(ttf_path))
    face.set_pixel_sizes(0, ppem)
    load_flags = freetype.FT_LOAD_RENDER | freetype.FT_LOAD_TARGET_MONO

    tt = TTFont(str(ttf_path), lazy=True)
    cmap = tt.getBestCmap() or {}
    tt.close()

    glyphs: list[RasterizedGlyph] = []
    gid = 1
    for cp in sorted(set(codepoints)):
        if cp not in cmap:
            continue
        face.load_char(cp, load_flags)
        slot = face.glyph
        bmp = slot.bitmap
        arr = _extract_mono_bitmap(bmp)
        box_h, box_w = int(arr.shape[0]), int(arr.shape[1])
        ofs_x = int(slot.bitmap_left)
        ofs_y = int(slot.bitmap_top) - box_h
        if modifier == "mono" and mono_advance_px is not None:
            adv_px = int(mono_advance_px)
            adv_fp4 = adv_px * 16
        else:
            # FreeType advance.x is 26.6 fixed-point; LVGL adv_w is FP4 (1/16 px)
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
    )
