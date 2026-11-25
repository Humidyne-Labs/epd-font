"""Orchestrate Stage 2 & Stage 3 Strike Compilation across all PPEMs, Modifiers & Styles."""

from __future__ import annotations

import concurrent.futures
from pathlib import Path
from typing import Any

import ufoLib2
from fontTools.designspaceLib import DesignSpaceDocument
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

from runner.config import ProjectConfig
from runner.grid_snap import prepare_snapped_ufo
from runner.hint_raster import CompiledStrike, compile_and_hint_ufo, rasterize_ttf_mono
from runner.serializers import (
    export_bdf,
    export_csv_metrics,
    export_lvgl_c_file,
    export_master_headers,
    export_strike_vault,
    render_text_bitmap,
    write_pbm_p1,
    write_pbm_p4,
)
from runner.ufo_utils import extract_ttfont_to_ufo


def _load_symbol_ufos(masters_dir: Path) -> dict[str, ufoLib2.Font]:
    sym_dir = masters_dir / "symbols"
    names = [
        "Symbols-Regular",
        "Symbols-Bold",
        "Symbols-Italic",
        "Symbols-BoldItalic",
        "Symbols-Mono-Regular",
        "Symbols-Mono-Bold",
        "Symbols-Mono-Italic",
        "Symbols-Mono-BoldItalic",
    ]
    return {n: ufoLib2.Font.open(sym_dir / f"{n}.ufo") for n in names}


def _symbol_key(modifier: str, style: str) -> str:
    prefix = "Symbols-Mono" if modifier == "mono" else "Symbols"
    s_map = {"normal": "Regular", "bold": "Bold", "italic": "Italic", "bold-italic": "BoldItalic"}
    return f"{prefix}-{s_map[style]}"


def _build_single_strike_task(task: dict[str, Any]) -> CompiledStrike:
    repo_root = Path(task["repo_root"])
    ppem = int(task["ppem"])
    modifier = str(task["modifier"])
    style = str(task["style"])
    axes = dict(task["axes"])
    target_stem_px = int(task["target_stem_px"])
    mono_adv_px = int(task["mono_adv_px"])
    codepoints = list(task["codepoints"])
    hint_cfg = dict(task["hint_cfg"])
    dpi = float(task["dpi"])
    specimens = dict(task["specimens"])
    pbm_per_glyph = bool(task["pbm_per_glyph"])

    # Instantiate base UFO from cached DesignSpace VF for fast exact interpolation
    vf_path = Path(task["vf_path"])
    vf_tt = TTFont(str(vf_path))
    vf_axes = {a.axisTag for a in vf_tt["fvar"].axes} if "fvar" in vf_tt else set()
    loc: dict[str, float] = {}
    for k, v in axes.items():
        if k in vf_axes:
            loc[k] = float(v)
    if modifier != "mono" and "slnt" in vf_axes:
        loc["slnt"] = -10.0 if "italic" in style else 0.0
    if modifier == "mono" and "slnt" in vf_axes:
        loc["slnt"] = -15.0 if "italic" in style else 0.0
    if modifier == "mono" and "CRSV" in vf_axes:
        loc["CRSV"] = 1.0 if "italic" in style else 0.0
    if modifier == "mono" and "CASL" in vf_axes:
        loc["CASL"] = 0.0

    inst_tt = instantiateVariableFont(vf_tt, loc, inplace=False)
    vf_tt.close()

    ital_ang = -10.0 if ("italic" in style and modifier != "mono") else (-15.0 if "italic" in style else 0.0)
    base_ufo = extract_ttfont_to_ufo(
        inst_tt,
        family_name=f"EPD {modifier.capitalize()}",
        style_name=style,
        codepoints=[cp for cp in codepoints if cp < 0x00A0 or cp <= 0x00FF],
        target_upm=1000,
        italic_angle=ital_ang,
        is_mono=(modifier == "mono"),
        mono_width=600,
    )
    inst_tt.close()

    sym_path = repo_root / "masters" / "symbols" / f"{_symbol_key(modifier, style)}.ufo"
    sym_ufo = ufoLib2.Font.open(sym_path)

    snapped_ufo = prepare_snapped_ufo(
        base_ufo=base_ufo,
        sym_ufo=sym_ufo,
        ppem=ppem,
        modifier=modifier,
        style=style,
        target_stem_px=target_stem_px,
        mono_advance_px=mono_adv_px,
    )

    if bool(task.get("save_snapped_ufo", False)):
        snapped_path = repo_root / "build" / "snapped_ufo" / f"epd_{modifier}_{style}_{ppem}px.ufo"
        snapped_path.parent.mkdir(parents=True, exist_ok=True)
        snapped_ufo.save(snapped_path, overwrite=True)

    raw_ttf = repo_root / "build" / "ttf" / f"epd_{modifier}_{style}_{ppem}px_raw.ttf"
    hinted_ttf = repo_root / "build" / "ttf" / f"epd_{modifier}_{style}_{ppem}px.ttf"
    compile_and_hint_ufo(snapped_ufo, raw_ttf, hinted_ttf, hint_cfg)

    strike = rasterize_ttf_mono(
        hinted_ttf,
        ppem=ppem,
        modifier=modifier,
        style=style,
        codepoints=codepoints,
        mono_advance_px=mono_adv_px if modifier == "mono" else None,
    )

    # Serialize outputs
    export_bdf(strike, repo_root / "build" / "bdf" / f"{strike.symbol_name}.bdf", dpi=dpi)
    export_lvgl_c_file(strike, repo_root / "build" / "c_arrays" / f"{strike.symbol_name}.c")
    export_csv_metrics(strike, repo_root / "build" / "metrics")

    pbm_dir = repo_root / "build" / "pbm" / f"{ppem}px" / f"{modifier}_{style}"
    for key, text in (("latin", specimens["latin"]), ("greek", specimens["greek"]), ("telemetry", specimens["telemetry"])):
        bmp = render_text_bitmap(strike, text)
        write_pbm_p1(bmp, pbm_dir / f"{key}_p1.pbm")
        write_pbm_p4(bmp, pbm_dir / f"{key}_p4.pbm")

    if pbm_per_glyph:
        g_dir = pbm_dir / "glyphs"
        for g in strike.glyphs:
            write_pbm_p1(g.bitmap, g_dir / f"U+{g.codepoint:04X}_p1.pbm")
            write_pbm_p4(g.bitmap, g_dir / f"U+{g.codepoint:04X}_p4.pbm")

    return strike


def _ensure_sans_vfs_cached(cfg: ProjectConfig) -> tuple[Path, Path]:
    """Compile self-contained Upright and Italic Sans VFs directly from masters/sans/*.ufo."""
    up_vf = cfg.repo_root / "build" / "cache" / "EPDSans_Upright_VF.ttf"
    it_vf = cfg.repo_root / "build" / "cache" / "EPDSans_Italic_VF.ttf"
    if up_vf.is_file() and it_vf.is_file():
        return up_vf, it_vf
    up_vf.parent.mkdir(parents=True, exist_ok=True)
    import ufo2ft
    from fontTools.designspaceLib import AxisDescriptor, DesignSpaceDocument, SourceDescriptor

    sans_dir = cfg.repo_root / "masters" / "sans"
    corners = [
        ("Default", 400, 100, 14, 468, 79, 96),
        ("Bold", 900, 100, 14, 468, 79, 96),
        ("Cond", 400, 75, 14, 468, 79, 96),
        ("CondBold", 900, 75, 14, 468, 79, 96),
        ("Opsz12", 400, 100, 12, 468, 79, 96),
        ("Opsz40", 400, 100, 40, 468, 79, 96),
        ("XTRA560", 400, 100, 14, 560, 79, 96),
        ("YOPQ55", 400, 100, 14, 468, 55, 96),
        ("YOPQ130", 400, 100, 14, 468, 130, 96),
        ("XOPQ60", 400, 100, 14, 468, 79, 60),
        ("XOPQ175", 400, 100, 14, 468, 79, 175),
    ]
    for out_p, prefix in ((up_vf, "Upright"), (it_vf, "Italic")):
        doc = DesignSpaceDocument()
        doc.addAxis(AxisDescriptor(tag="wght", name="Weight", minimum=400, default=400, maximum=900))
        doc.addAxis(AxisDescriptor(tag="wdth", name="Width", minimum=75, default=100, maximum=100))
        doc.addAxis(AxisDescriptor(tag="opsz", name="Optical Size", minimum=12, default=14, maximum=40))
        doc.addAxis(AxisDescriptor(tag="XTRA", name="Counter Transparency", minimum=468, default=468, maximum=560))
        doc.addAxis(AxisDescriptor(tag="YOPQ", name="Horizontal Bar Thickness", minimum=55, default=79, maximum=130))
        doc.addAxis(AxisDescriptor(tag="XOPQ", name="Vertical Stem Thickness", minimum=60, default=96, maximum=175))
        for tag, wg, wd, op, xt, yo, xo in corners:
            src = SourceDescriptor()
            src.font = ufoLib2.Font.open(sans_dir / f"EPDSans-{prefix}-{tag}.ufo")
            src.font.features.text = ""
            src.location = {
                "Weight": wg,
                "Width": wd,
                "Optical Size": op,
                "Counter Transparency": xt,
                "Horizontal Bar Thickness": yo,
                "Vertical Stem Thickness": xo,
            }
            doc.addSource(src)
        vf = ufo2ft.compileVariableTTF(doc, inplace=True)
        vf.save(str(out_p))
        vf.close()
    return up_vf, it_vf


def _ensure_mono_vfs_cached(cfg: ProjectConfig) -> tuple[Path, Path]:
    """Compile clean Upright and Italic Mono VFs from masters/mono/*.ufo."""
    up_vf = cfg.repo_root / "build" / "cache" / "EPDMono_Upright_VF.ttf"
    it_vf = cfg.repo_root / "build" / "cache" / "EPDMono_Italic_VF.ttf"
    if up_vf.is_file() and it_vf.is_file():
        return up_vf, it_vf
    up_vf.parent.mkdir(parents=True, exist_ok=True)
    import ufo2ft
    from fontTools.designspaceLib import AxisDescriptor, SourceDescriptor

    mono_dir = cfg.repo_root / "masters" / "mono"
    for out_p, prefix in ((up_vf, "Upright"), (it_vf, "Italic")):
        doc = DesignSpaceDocument()
        doc.addAxis(AxisDescriptor(tag="wght", name="Weight", minimum=300, default=300, maximum=1000))
        for tag, w in (("A", 300), ("B", 800), ("C", 1000)):
            src = SourceDescriptor()
            src.font = ufoLib2.Font.open(mono_dir / f"EPDMono-{prefix}-{tag}.ufo")
            src.font.features.text = ""
            src.location = {"Weight": w}
            doc.addSource(src)
        vf = ufo2ft.compileVariableTTF(doc, inplace=True)
        vf.save(str(out_p))
        vf.close()
    return up_vf, it_vf


def run_build(
    cfg: ProjectConfig,
    ppems: list[int] | None = None,
    modifiers: list[str] | None = None,
    styles: list[str] | None = None,
    pbm_per_glyph: bool = False,
    save_snapped_ufo: bool = False,
    jobs: int = 4,
) -> list[CompiledStrike]:
    """Compile, snap, hint, rasterize, and serialize all requested strikes."""
    target_ppems = ppems or cfg.ppem_range
    codepoints = cfg.mandatory_codepoints()
    hint_cfg = cfg.project.get("hinting", {}).get("ttfautohint", {})
    dpi = float(cfg.project.get("hardware", {}).get("dpi", 188.15))
    specimens = cfg.proofs["specimens"]

    sans_up_vf, sans_it_vf = _ensure_sans_vfs_cached(cfg)
    mono_up_vf, mono_it_vf = _ensure_mono_vfs_cached(cfg)

    tasks: list[dict[str, Any]] = []
    for p in target_ppems:
        sz_cfg = cfg.sizes[p]
        mono_adv = int(sz_cfg["mono_advance_px"])
        for inst_cfg in sz_cfg["instances"].values():
            mod = str(inst_cfg["modifier"])
            sty = str(inst_cfg["style"])
            if modifiers and mod not in modifiers:
                continue
            if styles and sty not in styles:
                continue
            if mod == "mono":
                vf_sel = mono_it_vf if "italic" in sty else mono_up_vf
            else:
                vf_sel = sans_it_vf if "italic" in sty else sans_up_vf
            tasks.append({
                "repo_root": str(cfg.repo_root),
                "ppem": p,
                "modifier": mod,
                "style": sty,
                "axes": dict(inst_cfg["axes"]),
                "target_stem_px": int(inst_cfg["target_stem_px"]),
                "mono_adv_px": mono_adv,
                "codepoints": codepoints,
                "hint_cfg": hint_cfg,
                "dpi": dpi,
                "specimens": specimens,
                "pbm_per_glyph": pbm_per_glyph,
                "save_snapped_ufo": save_snapped_ufo,
                "vf_path": str(vf_sel),
            })

    print(f"[*] Building {len(tasks)} strikes across {len(target_ppems)} PPEM(s) with {max(1, jobs)} worker(s)...")
    strikes: list[CompiledStrike] = []
    if jobs <= 1 or len(tasks) <= 2:
        strikes = [_build_single_strike_task(t) for t in tasks]
    else:
        with concurrent.futures.ProcessPoolExecutor(max_workers=jobs) as pool:
            strikes = list(pool.map(_build_single_strike_task, tasks))

    # Build Terminus bitmap strikes & PUA Icon suites when not filtered out
    from runner.terminus_icons import build_icon_strikes, build_terminus_strikes

    if modifiers is None or "terminus" in modifiers:
        strikes.extend(build_terminus_strikes(cfg, target_ppems))
    if modifiers is None or any(m.startswith("icon_") for m in modifiers):
        strikes.extend(build_icon_strikes(cfg, target_ppems))

    export_master_headers(strikes, cfg.repo_root / "build" / "c_arrays")
    export_strike_vault(strikes, cfg.repo_root / "build" / "dist" / "humid1_epd_vault.json.gz")
    print(f"[+] Built {len(strikes)} strikes -> build/{{ttf,bdf,pbm,c_arrays,metrics,dist}}")
    return strikes
