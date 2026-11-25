"""Visual & Optical Proof Sheet Renderer (specimen_1x.pbm, grid_8x.png, epd_psf_sim.png)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

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

    return out_dir
