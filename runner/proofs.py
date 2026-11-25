"""Visual & Optical Proof Sheet Renderer (specimen_1x.pbm, grid_8x.png, epd_psf_sim.png)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from runner.config import ProjectConfig
from runner.gates import StrikeAudit
from runner.grid_snap import compute_pixel_vertical_metrics
from runner.hint_raster import CompiledStrike
from runner.math_psf import EPD_DEFAULT_R_BG, EPD_DEFAULT_R_INK, PIXEL_PITCH_UM, simulate_epd_gaussian_psf
from runner.serializers import render_text_bitmap, write_pbm_p4


def render_strike_proofs(cfg: ProjectConfig, strike: CompiledStrike, audit: StrikeAudit) -> Path:
    """Emit specimen_1x.pbm, grid_8x.png, and epd_psf_sim.png under build/proofs/<ppem>/<mod>_<style>/."""
    out_dir = cfg.repo_root / "build" / "proofs" / str(strike.ppem) / f"{strike.modifier}_{strike.style}"
    out_dir.mkdir(parents=True, exist_ok=True)

    specs = cfg.proofs["specimens"]
    lines_text = [specs["latin"], specs["greek"], specs["telemetry"]]
    line_bmps = [render_text_bitmap(strike, t, pad_x=2, pad_y=2) for t in lines_text]
    max_w = max(b.shape[1] for b in line_bmps)
    total_h = sum(b.shape[0] for b in line_bmps)
    stacked = np.zeros((total_h, max_w), dtype=np.uint8)
    y_cur = 0
    for b in line_bmps:
        stacked[y_cur : y_cur + b.shape[0], : b.shape[1]] = b
        y_cur += b.shape[0]

    # 1. Native 1x Bi-Level Specimen (P4)
    write_pbm_p4(stacked, out_dir / "specimen_1x.pbm")

    # 2. Grid-Annotated 8x Inspection Sheet (grid_8x.png)
    zoom = int(cfg.proofs["grid_8x"].get("zoom_factor", 8))
    trouble = specs["trouble"]
    t_bmp = render_text_bitmap(strike, trouble, pad_x=4, pad_y=4)
    th, tw = t_bmp.shape
    up = np.repeat(np.repeat(np.where(t_bmp > 0, 17, 255).astype(np.uint8), zoom, axis=0), zoom, axis=1)
    img = Image.fromarray(up, mode="L").convert("RGB")
    draw = ImageDraw.Draw(img)

    # 1px grid hairlines
    for x in range(0, tw * zoom, zoom):
        draw.line([(x, 0), (x, th * zoom - 1)], fill=(224, 224, 224))
    for y in range(0, th * zoom, zoom):
        draw.line([(0, y), (tw * zoom - 1, y)], fill=(224, 224, 224))

    # Cyan baseline, x-height, cap-height reference lines
    _, _, cap_px, xh_px = compute_pixel_vertical_metrics(strike.ppem)
    base_y = (4 + strike.font_ascent) * zoom
    cap_y = (4 + strike.font_ascent - cap_px) * zoom
    xh_y = (4 + strike.font_ascent - xh_px) * zoom
    draw.line([(0, base_y), (tw * zoom - 1, base_y)], fill=(0, 188, 212), width=1)
    draw.line([(0, cap_y), (tw * zoom - 1, cap_y)], fill=(0, 188, 212), width=1)
    draw.line([(0, xh_y), (tw * zoom - 1, xh_y)], fill=(0, 188, 212), width=1)

    # Magenta per-glyph BBX boxes
    gmap = {g.codepoint: g for g in strike.glyphs}
    pen_x = 4
    for ch in trouble:
        g = gmap.get(ord(ch))
        if g is None:
            pen_x += strike.ppem // 2
            continue
        if g.box_w > 0 and g.box_h > 0:
            x0 = (pen_x + g.ofs_x) * zoom
            y0 = (4 + strike.font_ascent - (g.ofs_y + g.box_h)) * zoom
            x1 = x0 + g.box_w * zoom
            y1 = y0 + g.box_h * zoom
            draw.rectangle([x0, y0, x1, y1], outline=(233, 30, 99), width=1)
        pen_x += g.advance_px
    img.save(out_dir / "grid_8x.png")

    # 3. EPD Optical Scatter Proof (epd_psf_sim.png) at 135um and 270um
    psf_135, _, _ = simulate_epd_gaussian_psf(
        stacked, sigma_px=135.0 / PIXEL_PITCH_UM, r_bg=EPD_DEFAULT_R_BG, r_ink=EPD_DEFAULT_R_INK, pad_px=4
    )
    psf_270, _, _ = simulate_epd_gaussian_psf(
        stacked, sigma_px=270.0 / PIXEL_PITCH_UM, r_bg=EPD_DEFAULT_R_BG, r_ink=EPD_DEFAULT_R_INK, pad_px=4
    )
    crisp_pad = np.pad(np.where(stacked > 0, EPD_DEFAULT_R_INK, EPD_DEFAULT_R_BG).astype(np.float32), 4, constant_values=EPD_DEFAULT_R_BG)
    combined = np.vstack([crisp_pad, psf_135, psf_270]).clip(0, 255).astype(np.uint8)
    psf_img = Image.fromarray(combined, mode="L").resize((combined.shape[1] * 2, combined.shape[0] * 2), Image.Resampling.NEAREST)
    psf_img.save(out_dir / "epd_psf_sim.png")

    # 4. Full Glyph Contact Sheet (all glyphs present in the strike)
    render_full_glyph_sheet(strike, out_dir / "full_glyph_sheet.png")

    return out_dir


def render_full_glyph_sheet(
    strike: CompiledStrike,
    out_path: Path,
    icon_names: dict[int, str] | None = None,
) -> Path:
    """Render a complete labeled contact sheet of every glyph in `strike`."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    glyphs = sorted(strike.glyphs, key=lambda g: g.codepoint)
    is_icon = icon_names is not None
    cols = 14 if is_icon else 22
    zoom = 3 if strike.ppem <= 20 else 2
    max_bw = max([g.box_w for g in glyphs] + [strike.ppem])
    max_bh = max([g.box_h for g in glyphs] + [strike.line_height])
    cell_w = max(56 if is_icon else 38, max_bw * zoom + 14)
    label_h = 22 if is_icon else 13
    cell_h = max_bh * zoom + label_h + 12
    rows = max(1, (len(glyphs) + cols - 1) // cols)
    hdr_h = 28

    img = Image.new("RGB", (cols * cell_w + 16, hdr_h + rows * cell_h + 12), (248, 248, 245))
    draw = ImageDraw.Draw(img)
    font_lbl = ImageFont.load_default()
    fb = strike.fallback_symbol or "none"
    hdr = f"{strike.symbol_name} | {strike.ppem}px | {len(glyphs)} glyphs | lh={strike.line_height}px | fallback={fb}"
    draw.text((10, 7), hdr, fill=(20, 20, 20), font=font_lbl)
    draw.line([(8, hdr_h - 3), (img.width - 8, hdr_h - 3)], fill=(180, 180, 175), width=1)

    for idx, g in enumerate(glyphs):
        r_idx = idx // cols
        c_idx = idx % cols
        x0 = 8 + c_idx * cell_w
        y0 = hdr_h + r_idx * cell_h
        draw.rectangle([x0, y0, x0 + cell_w - 2, y0 + cell_h - 2], outline=(215, 215, 210), width=1)

        # Draw glyph bitmap anchored cleanly inside cell
        if g.box_w > 0 and g.box_h > 0 and g.bitmap.size > 0:
            gx_off = x0 + max(4, (cell_w - 2 - g.box_w * zoom) // 2)
            base_y_cell = y0 + 6 + strike.font_ascent * zoom
            gy_off = max(y0 + 3, base_y_cell - (g.ofs_y + g.box_h) * zoom)
            # Subtle baseline tick
            if y0 + 2 <= base_y_cell <= y0 + cell_h - label_h:
                draw.line([(x0 + 2, base_y_cell), (x0 + cell_w - 4, base_y_cell)], fill=(210, 232, 238), width=1)
            ys_on, xs_on = np.nonzero(g.bitmap > 0)
            for py, px in zip(ys_on.tolist(), xs_on.tolist(), strict=False):
                rx = gx_off + px * zoom
                ry = gy_off + py * zoom
                draw.rectangle([rx, ry, rx + zoom - 1, ry + zoom - 1], fill=(17, 17, 17))

        # Label: U+XXXX (+ icon name if icon suite)
        cp_txt = f"{g.codepoint:04X}"
        if is_icon and icon_names is not None:
            nm = icon_names.get(g.codepoint, "")[:10]
            draw.text((x0 + 3, y0 + cell_h - label_h), cp_txt, fill=(85, 85, 85), font=font_lbl)
            if nm:
                draw.text((x0 + 3, y0 + cell_h - 12), nm, fill=(25, 90, 140), font=font_lbl)
        else:
            ch_disp = chr(g.codepoint) if 0x0021 <= g.codepoint <= 0x007E else ""
            lbl = f"{cp_txt} {ch_disp}".strip()
            draw.text((x0 + 3, y0 + cell_h - 14), lbl, fill=(75, 75, 75), font=font_lbl)

    tmp_out = out_path.with_suffix(".tmp.png")
    img.save(tmp_out)
    tmp_out.replace(out_path)
    return out_path


def render_icon_strike_proofs(
    cfg: ProjectConfig,
    strike: CompiledStrike,
    icon_names: dict[int, str] | None = None,
) -> Path:
    """Emit specimen_1x.pbm, epd_psf_sim.png, and full_glyph_sheet.png for an icon strike."""
    out_dir = cfg.repo_root / "build" / "proofs" / str(strike.ppem) / f"{strike.modifier}_{strike.style}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Build 1x specimen grid (up to 32 icons, 16 per row)
    sample = strike.glyphs[:32]
    per_row = 16
    row_bmps: list[np.ndarray] = []
    for start in range(0, len(sample), per_row):
        chunk = sample[start : start + per_row]
        txt = "".join(chr(g.codepoint) for g in chunk)
        row_bmps.append(render_text_bitmap(strike, txt, pad_x=4, pad_y=3))
    if row_bmps:
        mw = max(b.shape[1] for b in row_bmps)
        th = sum(b.shape[0] for b in row_bmps)
        stacked = np.zeros((th, mw), dtype=np.uint8)
        yc = 0
        for b in row_bmps:
            stacked[yc : yc + b.shape[0], : b.shape[1]] = b
            yc += b.shape[0]
    else:
        stacked = np.zeros((strike.ppem, strike.ppem), dtype=np.uint8)

    write_pbm_p4(stacked, out_dir / "specimen_1x.pbm")

    # 2. PSF simulation
    psf_135, _, _ = simulate_epd_gaussian_psf(
        stacked, sigma_px=135.0 / PIXEL_PITCH_UM, r_bg=EPD_DEFAULT_R_BG, r_ink=EPD_DEFAULT_R_INK, pad_px=4
    )
    psf_270, _, _ = simulate_epd_gaussian_psf(
        stacked, sigma_px=270.0 / PIXEL_PITCH_UM, r_bg=EPD_DEFAULT_R_BG, r_ink=EPD_DEFAULT_R_INK, pad_px=4
    )
    crisp_pad = np.pad(np.where(stacked > 0, EPD_DEFAULT_R_INK, EPD_DEFAULT_R_BG).astype(np.float32), 4, constant_values=EPD_DEFAULT_R_BG)
    combined = np.vstack([crisp_pad, psf_135, psf_270]).clip(0, 255).astype(np.uint8)
    psf_img = Image.fromarray(combined, mode="L").resize((combined.shape[1] * 2, combined.shape[0] * 2), Image.Resampling.NEAREST)
    psf_img.save(out_dir / "epd_psf_sim.png")

    # 3. Full labeled icon contact sheet
    render_full_glyph_sheet(strike, out_dir / "full_glyph_sheet.png", icon_names=icon_names or {})
    return out_dir


def _draw_text_with_fallback(
    canvas: np.ndarray,
    x: int,
    y_top: int,
    text: str,
    primary: CompiledStrike,
    fallback: CompiledStrike | None = None,
    invert: bool = False,
) -> int:
    """Blit `text` onto 1-bit `canvas` using `primary` + optional PUA `fallback`. Returns ending x."""
    pmap = {g.codepoint: g for g in primary.glyphs}
    fmap = {g.codepoint: g for g in fallback.glyphs} if fallback else {}
    ch_h, ch_w = canvas.shape
    pen_x = x
    for ch in text:
        cp = ord(ch)
        g = pmap.get(cp)
        strike_used = primary
        if g is None and cp in fmap and fallback is not None:
            g = fmap[cp]
            strike_used = fallback
        if g is None:
            pen_x += max(3, primary.ppem // 3)
            continue
        if g.box_w > 0 and g.box_h > 0 and g.bitmap.size > 0:
            gx = pen_x + g.ofs_x
            # Align fallback icons cleanly to primary baseline
            gy = y_top + primary.font_ascent - (g.ofs_y + g.box_h)
            if strike_used is not primary:
                gy = y_top + max(0, (primary.font_ascent - g.box_h) // 2 + 1)
            for rr in range(g.box_h):
                dy = gy + rr
                if not (0 <= dy < ch_h):
                    continue
                for cc in range(g.box_w):
                    if g.bitmap[rr, cc]:
                        dx = gx + cc
                        if 0 <= dx < ch_w:
                            canvas[dy, dx] = 0 if invert else 1
        pen_x += g.advance_px
    return pen_x


def render_multifont_showcase(
    cfg: ProjectConfig,
    strikes_by_sym: dict[str, CompiledStrike],
) -> Path:
    """Render a multi-font 1-bit H1OS E-Ink showcase canvas (1x PBM, 3x crisp PNG, PSF PNG)."""
    proof_root = cfg.repo_root / "build" / "proofs"
    proof_root.mkdir(parents=True, exist_ok=True)
    w, h = 520, 360
    canvas = np.zeros((h, w), dtype=np.uint8)

    def get_s(sym: str) -> CompiledStrike | None:
        return strikes_by_sym.get(sym)

    # Outer frame & top status bar (inverted) - 12px Terminus floor (no 12px icons)
    canvas[0:22, 0:w] = 1
    term_b12 = get_s("humid1_font_terminus_bold_12")
    term_n12 = get_s("humid1_font_terminus_normal_12")
    fa14 = get_s("humid1_icon_fa7_solid_14")
    if term_b12:
        _draw_text_with_fallback(canvas, 8, 4, "H1OS // EPD-FONT v2.1  [12px TERMINUS FLOOR]", term_b12, invert=True)
    if term_n12:
        _draw_text_with_fallback(canvas, 342, 4, "\uf1eb 20:41 UTC  \uf240 98%", term_n12, fa14, invert=True)

    # Left Hero Psychrometric Card
    canvas[30:182, 8:264] = 0
    canvas[30, 8:264] = 1
    canvas[181, 8:264] = 1
    canvas[30:182, 8] = 1
    canvas[30:182, 263] = 1
    canvas[30:50, 8:264] = 1

    cond_b14 = get_s("humid1_font_epd_condensed_bold_14")
    sans_b40 = get_s("humid1_font_epd_sans_bold_40")
    sans_n20 = get_s("humid1_font_epd_sans_normal_20")
    sans_i14 = get_s("humid1_font_epd_sans_italic_14")
    luc28 = get_s("humid1_icon_lucide_regular_28")
    phos24 = get_s("humid1_icon_phosphor_regular_24")

    if cond_b14:
        _draw_text_with_fallback(canvas, 14, 31, "CHAMBER A // EQUILIBRIUM", cond_b14, invert=True)
    if sans_b40:
        luc_ch = f"{chr(luc28.glyphs[0].codepoint)} " if (luc28 and luc28.glyphs) else ""
        _draw_text_with_fallback(canvas, 18, 56, f"{luc_ch}23.48", sans_b40, luc28)
    if sans_n20:
        _draw_text_with_fallback(canvas, 198, 66, "°C", sans_n20)
    if sans_n20:
        _draw_text_with_fallback(canvas, 20, 114, "\ue162  48.5 %RH", sans_n20, phos24)
    if sans_i14:
        _draw_text_with_fallback(canvas, 18, 150, "Vapor Equilibrium // Nominal", sans_i14)

    # Right Telemetry Matrix Card
    canvas[30, 272:512] = 1
    canvas[181, 272:512] = 1
    canvas[30:182, 272] = 1
    canvas[30:182, 511] = 1
    canvas[30:50, 272:512] = 1

    mono_b18 = get_s("humid1_font_epd_mono_bold_18")
    mono_n14 = get_s("humid1_font_epd_mono_normal_14")
    sans_i16 = get_s("humid1_font_epd_sans_italic_16")
    if cond_b14:
        _draw_text_with_fallback(canvas, 278, 31, "TELEMETRY & GREEK/MATH", cond_b14, invert=True)
    if mono_b18:
        _draw_text_with_fallback(canvas, 282, 58, "DEW  12.04 °C", mono_b18)
    if mono_n14:
        _draw_text_with_fallback(canvas, 282, 92, "VAP  14.02 hPa | ±0.03", mono_n14)
        _draw_text_with_fallback(canvas, 282, 116, "RES  1.05e-3 Ω·m | PASS", mono_n14)
    if sans_i16:
        _draw_text_with_fallback(canvas, 282, 146, "∑(xᵢ − µ)² / N  [ΑΒΓΜΝΣΩ]", sans_i16)

    # Bottom Multi-Family & 5-Icon-Suite Comparison Band
    canvas[190, 8:512] = 1
    canvas[351, 8:512] = 1
    canvas[190:352, 8] = 1
    canvas[190:352, 511] = 1
    if cond_b14:
        _draw_text_with_fallback(canvas, 16, 194, "FAMILY SPECIMENS & 5 PUA ICON SUITES (1x NATIVE BI-LEVEL)", cond_b14)
    canvas[214, 8:512] = 1

    sans_n16 = get_s("humid1_font_epd_sans_normal_16")
    cond_n16 = get_s("humid1_font_epd_condensed_normal_16")
    mono_n16 = get_s("humid1_font_epd_mono_normal_16")
    term_n14 = get_s("humid1_font_terminus_normal_14")
    sans_bi18 = get_s("humid1_font_epd_sans_bold-italic_18")

    if sans_n16:
        _draw_text_with_fallback(canvas, 16, 219, "Sans 16:      sphinx of black quartz, judge my vow (012345)", sans_n16)
    if cond_n16:
        _draw_text_with_fallback(canvas, 16, 241, "Condensed 16: sensors nominal | H₂O vapor pressure 48.5%", cond_n16)
    if mono_n16:
        _draw_text_with_fallback(canvas, 16, 263, "Mono 16:      0xF0E7  A=188.15 DPI  s/S/M/W/Μ  [OK]", mono_n16)
    if term_n14:
        _draw_text_with_fallback(canvas, 16, 285, "Terminus 14:  exact bitmap alt: sys_stat=READY  mem=3072K", term_n14)
    if sans_bi18:
        _draw_text_with_fallback(canvas, 16, 304, "Bold-It 18:   ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ", sans_bi18)

    # 5-Icon-Suite Row on bottom bar
    icon_suites = [
        ("FA7:", "humid1_icon_fa7_solid_20"),
        ("Luc:", "humid1_icon_lucide_regular_20"),
        ("Phos:", "humid1_icon_phosphor_regular_20"),
        ("PFill:", "humid1_icon_phosphor_fill_20"),
        ("Tab:", "humid1_icon_tabler_regular_20"),
        ("TabF:", "humid1_icon_tabler_filled_20"),
    ]
    ix = 16
    for lbl, sym in icon_suites:
        if term_n14:
            ix = _draw_text_with_fallback(canvas, ix, 330, lbl, term_n14) + 2
        ic_s = get_s(sym)
        if ic_s:
            txt = "".join(chr(g.codepoint) for g in ic_s.glyphs[:1])
            ix = _draw_text_with_fallback(canvas, ix, 326, txt, ic_s) + 8

    # Save 1x PBM, 3x Crisp E-Ink PNG, and PSF Scatter PNG
    pbm_out = proof_root / "SHOWCASE_MULTI_FONT_1x.pbm"
    write_pbm_p4(canvas, pbm_out)

    # E-Ink paper (#ECEBE4) & carbon pigment (#161616) 3x nearest-neighbor PNG
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    rgb[canvas == 0] = (236, 235, 228)
    rgb[canvas > 0] = (22, 22, 22)
    png_out = proof_root / "SHOWCASE_MULTI_FONT.png"
    Image.fromarray(rgb, mode="RGB").resize((w * 3, h * 3), Image.Resampling.NEAREST).save(png_out)

    psf_135, _, _ = simulate_epd_gaussian_psf(
        canvas, sigma_px=135.0 / PIXEL_PITCH_UM, r_bg=EPD_DEFAULT_R_BG, r_ink=EPD_DEFAULT_R_INK, pad_px=4
    )
    crisp_pad = np.pad(np.where(canvas > 0, EPD_DEFAULT_R_INK, EPD_DEFAULT_R_BG).astype(np.float32), 4, constant_values=EPD_DEFAULT_R_BG)
    comb = np.vstack([crisp_pad, psf_135]).clip(0, 255).astype(np.uint8)
    Image.fromarray(comb, mode="L").resize((comb.shape[1] * 2, comb.shape[0] * 2), Image.Resampling.NEAREST).save(
        proof_root / "SHOWCASE_MULTI_FONT_psf.png"
    )
    return png_out
