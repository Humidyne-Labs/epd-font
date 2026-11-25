"""Terminus BDF & PUA Icon Suite Compilers for epd-font v2.1."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import freetype
import numpy as np
import yaml
from fontTools.ttLib import TTFont

from runner.config import ProjectConfig
from runner.hint_raster import CompiledStrike, RasterizedGlyph
from runner.serializers import (
    export_bdf,
    export_csv_metrics,
    export_lvgl_c_file,
    render_text_bitmap,
    write_pbm_p1,
    write_pbm_p4,
)


def _parse_bdf_file(bdf_path: Path) -> tuple[int, int, list[dict[str, Any]]]:
    """Parse X11 BDF 2.1 file -> (ascent, descent, glyph_dicts)."""
    ascent, descent = 12, 4
    glyphs: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    in_bmp = False
    for raw in bdf_path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = raw.strip()
        if s.startswith("FONT_ASCENT "):
            ascent = int(s.split()[1])
        elif s.startswith("FONT_DESCENT "):
            descent = int(s.split()[1])
        elif s.startswith("STARTCHAR "):
            cur = {"name": s.split(None, 1)[1], "cp": -1, "dwidth": 8, "bbx": (8, 16, 0, -4), "rows": []}
            in_bmp = False
        elif cur is not None:
            if s.startswith("ENCODING "):
                cur["cp"] = int(s.split()[1])
            elif s.startswith("DWIDTH "):
                cur["dwidth"] = int(s.split()[1])
            elif s.startswith("BBX "):
                cur["bbx"] = tuple(int(x) for x in s.split()[1:5])
            elif s == "BITMAP":
                in_bmp = True
            elif s == "ENDCHAR":
                if cur["cp"] >= 0:
                    glyphs.append(cur)
                cur = None
                in_bmp = False
            elif in_bmp:
                cur["rows"].append(s)
    return ascent, descent, glyphs


def _bdf_rows_to_array(hex_rows: list[str], box_w: int, box_h: int) -> np.ndarray:
    if box_w <= 0 or box_h <= 0:
        return np.zeros((0, 0), dtype=np.uint8)
    arr = np.zeros((box_h, box_w), dtype=np.uint8)
    row_bytes = (box_w + 7) // 8
    total_bits = row_bytes * 8
    for r_idx, h_str in enumerate(hex_rows[:box_h]):
        val = int(h_str, 16) if h_str else 0
        for c in range(box_w):
            if (val >> (total_bits - 1 - c)) & 1:
                arr[r_idx, c] = 1
    return arr


def build_terminus_strikes(cfg: ProjectConfig, ppems: list[int]) -> list[CompiledStrike]:
    """Compile native Terminus BDF strikes (12..32 px) and exact 2x strikes (36, 40 px)."""
    term_dir = cfg.repo_root / "masters" / "terminus"
    if not term_dir.is_dir():
        return []

    codepoints_set = set(cfg.mandatory_codepoints())
    dpi = float(cfg.project.get("hardware", {}).get("dpi", 188.15))
    specimens = cfg.proofs["specimens"]
    strikes: list[CompiledStrike] = []

    for p in ppems:
        src_p, scale = (p // 2, 2) if p in (36, 40) else (p, 1)
        for style, suffix in (("normal", "n"), ("bold", "b")):
            bdf_file = term_dir / f"ter-u{src_p}{suffix}.bdf"
            if not bdf_file.is_file():
                continue
            asc, desc, raw_glyphs = _parse_bdf_file(bdf_file)
            asc_s, desc_s = asc * scale, desc * scale
            r_glyphs: list[RasterizedGlyph] = []
            gid = 1
            for g in sorted((x for x in raw_glyphs if x["cp"] in codepoints_set), key=lambda x: x["cp"]):
                bw, bh, ox, oy = g["bbx"]
                arr = _bdf_rows_to_array(g["rows"], bw, bh)
                if scale > 1 and arr.size > 0:
                    arr = np.repeat(np.repeat(arr, scale, axis=0), scale, axis=1)
                adv_px = int(g["dwidth"]) * scale
                r_glyphs.append(
                    RasterizedGlyph(
                        codepoint=int(g["cp"]),
                        glyph_id=gid,
                        name=str(g["name"]),
                        adv_w_fp4=adv_px * 16,
                        advance_px=adv_px,
                        box_w=bw * scale,
                        box_h=bh * scale,
                        ofs_x=ox * scale,
                        ofs_y=oy * scale,
                        bitmap=arr,
                    )
                )
                gid += 1

            sym = f"humid1_font_terminus_{style}_{p}"
            if p < 14:
                fallback = f"humid1_font_terminus_normal_{p}" if style != "normal" else None
            else:
                fallback = f"humid1_icon_fa7_solid_{p}" if style == "normal" else f"humid1_font_terminus_normal_{p}"
            strike = CompiledStrike(
                ppem=p,
                modifier="terminus",
                style=style,
                symbol_name=sym,
                ttf_path=bdf_file,
                font_ascent=asc_s,
                font_descent=desc_s,
                line_height=asc_s + desc_s,
                base_line=desc_s,
                glyphs=r_glyphs,
                kern_pairs=[],
                fallback_symbol=fallback,
            )
            export_bdf(strike, cfg.repo_root / "build" / "bdf" / f"{sym}.bdf", dpi=dpi)
            export_lvgl_c_file(strike, cfg.repo_root / "build" / "c_arrays" / f"{sym}.c")
            export_csv_metrics(strike, cfg.repo_root / "build" / "metrics")
            pbm_dir = cfg.repo_root / "build" / "pbm" / f"{p}px" / f"terminus_{style}"
            for key, text in (("latin", specimens["latin"]), ("greek", specimens["greek"]), ("telemetry", specimens["telemetry"])):
                bmp = render_text_bitmap(strike, text)
                write_pbm_p1(bmp, pbm_dir / f"{key}_p1.pbm")
                write_pbm_p4(bmp, pbm_dir / f"{key}_p4.pbm")
            strikes.append(strike)

    return strikes


def _build_unified_icon_catalog(cfg: ProjectConfig, icons_cfg: dict[str, Any]) -> None:
    """Build build/metadata/unified_icon_names.json from masters/icons/*/char_manifest_*.json."""
    meta_dir = cfg.repo_root / "build" / "metadata"
    meta_dir.mkdir(parents=True, exist_ok=True)
    by_cp: dict[str, dict[str, str]] = {}
    by_name: dict[str, dict[str, str]] = {}
    for suite_key, s_cfg in icons_cfg.get("suites", {}).items():
        fam = str(s_cfg["family"])
        cat_key = "icon_tabler_filled" if suite_key == "icon_tabler_filled" else fam
        m_path = cfg.repo_root / s_cfg["manifest"]
        if not m_path.is_file():
            continue
        m_data = json.loads(m_path.read_text(encoding="utf-8"))
        raw_cp = m_data.get("by_codepoint", {})
        raw_nm = m_data.get("by_name", {})
        if suite_key == "icon_tabler_filled":
            by_cp.setdefault(cat_key, {}).update({k: v for k, v in raw_cp.items() if str(v).endswith("-filled")})
            by_name.setdefault(cat_key, {}).update({k: v for k, v in raw_nm.items() if str(k).endswith("-filled")})
        else:
            by_cp.setdefault(cat_key, {}).update(raw_cp)
            by_name.setdefault(cat_key, {}).update(raw_nm)
    (meta_dir / "unified_icon_names.json").write_text(
        json.dumps({"schema_version": "2.1.0", "by_codepoint": by_cp, "by_name": by_name}, indent=2),
        encoding="utf-8",
    )


def build_icon_strikes(cfg: ProjectConfig, ppems: list[int]) -> list[CompiledStrike]:
    """Rasterize curated PUA icon packs across all PPEMs via analytical coverage thresholding."""
    icons_yaml = cfg.repo_root / "config" / "icons.yaml"
    if not icons_yaml.is_file():
        return []
    icons_cfg = yaml.safe_load(icons_yaml.read_text(encoding="utf-8"))
    _build_unified_icon_catalog(cfg, icons_cfg)

    dpi = float(cfg.project.get("hardware", {}).get("dpi", 188.15))
    strikes: list[CompiledStrike] = []
    icon_ppems = [p for p in ppems if p >= 14]
    if not icon_ppems:
        return []

    for suite_cfg in icons_cfg.get("suites", {}).values():
        fam = str(suite_cfg["family"])
        sty = str(suite_cfg["style"])
        font_path = cfg.repo_root / suite_cfg["font_file"]
        if not font_path.is_file():
            continue
        m_path = cfg.repo_root / suite_cfg["manifest"]
        m_data = json.loads(m_path.read_text(encoding="utf-8")) if m_path.is_file() else {}
        by_name_map = m_data.get("by_name", {})

        cps: set[int] = {int(c, 0) for c in suite_cfg.get("codepoints", [])}
        for nm in suite_cfg.get("names", []):
            cand_nm = f"{nm}-filled" if fam == "icon_tabler_filled" and not nm.endswith("-filled") else nm
            if cand_nm in by_name_map:
                cps.add(int(by_name_map[cand_nm], 0))
            elif nm in by_name_map:
                cps.add(int(by_name_map[nm], 0))

        tt = TTFont(str(font_path), lazy=True)
        cmap = tt.getBestCmap() or {}
        tt.close()
        valid_cps = sorted(cp for cp in cps if cp in cmap)
        face = freetype.Face(str(font_path))

        for p in icon_ppems:
            face.set_pixel_sizes(0, p)
            asc_px = max(1, round(p * 0.85))
            desc_px = max(1, p - asc_px)
            r_glyphs: list[RasterizedGlyph] = []
            gid = 1
            for cp in valid_cps:
                face.load_char(cp, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_TARGET_NORMAL)
                slot = face.glyph
                bmp = slot.bitmap
                rows, width = int(bmp.rows), int(bmp.width)
                pitch = abs(int(bmp.pitch))
                if rows > 0 and width > 0:
                    raw = np.frombuffer(bytes(bmp.buffer), dtype=np.uint8).reshape((rows, pitch))[:, :width]
                    arr = (raw >= 115).astype(np.uint8)
                else:
                    arr = np.zeros((0, 0), dtype=np.uint8)
                ofs_x = int(slot.bitmap_left)
                ofs_y = int(slot.bitmap_top) - rows
                # Clamp vertical bounds inside [ -desc_px, asc_px ]
                if rows > 0 and ofs_y + rows > asc_px:
                    ofs_y = asc_px - rows
                if rows > 0 and ofs_y < -desc_px:
                    ofs_y = -desc_px
                adv_fp4 = max(0, round(float(slot.advance.x) / 4.0))
                adv_px = (adv_fp4 + 8) >> 4
                r_glyphs.append(
                    RasterizedGlyph(
                        codepoint=cp,
                        glyph_id=gid,
                        name=cmap[cp],
                        adv_w_fp4=adv_fp4,
                        advance_px=adv_px,
                        box_w=width,
                        box_h=rows,
                        ofs_x=ofs_x,
                        ofs_y=ofs_y,
                        bitmap=arr,
                    )
                )
                gid += 1

            sym = f"humid1_{fam}_{sty}_{p}"
            strike = CompiledStrike(
                ppem=p,
                modifier=fam,
                style=sty,
                symbol_name=sym,
                ttf_path=font_path,
                font_ascent=asc_px,
                font_descent=desc_px,
                line_height=asc_px + desc_px,
                base_line=desc_px,
                glyphs=r_glyphs,
                kern_pairs=[],
                fallback_symbol=None,
            )
            export_bdf(strike, cfg.repo_root / "build" / "bdf" / f"{sym}.bdf", dpi=dpi)
            export_lvgl_c_file(strike, cfg.repo_root / "build" / "c_arrays" / f"{sym}.c")
            export_csv_metrics(strike, cfg.repo_root / "build" / "metrics")
            strikes.append(strike)

    return strikes
