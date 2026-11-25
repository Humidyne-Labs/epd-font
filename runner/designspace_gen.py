"""DesignSpace 5.1 XML Generator per PPEM."""

from __future__ import annotations

from pathlib import Path

from fontTools.designspaceLib import (
    AxisDescriptor,
    DesignSpaceDocument,
    DiscreteAxisDescriptor,
    InstanceDescriptor,
    SourceDescriptor,
)

from runner.config import ProjectConfig


def generate_designspace_for_ppem(cfg: ProjectConfig, ppem: int) -> Path:
    """Emit designspaces/epd_<P>px.designspace (format 5.1) from config/sizes/ppem_<P>.yaml."""
    sz_cfg = cfg.sizes[ppem]
    ds_dir = cfg.repo_root / "designspaces"
    ds_dir.mkdir(parents=True, exist_ok=True)
    out_path = ds_dir / f"epd_{ppem}px.designspace"

    doc = DesignSpaceDocument()
    doc.formatVersion = "5.1"

    # Continuous axes (SPEC-EPD-FONT-001 Section 3.2)
    for tag, name, mn, df, mx in [
        ("wght", "Weight", 300, 400, 1000),
        ("wdth", "Width", 75, 100, 100),
        ("opsz", "Optical Size", 12, ppem, 40),
        ("XTRA", "Counter Transparency", 468, 468, 560),
        ("YOPQ", "Horizontal Bar Thickness", 55, 79, 130),
    ]:
        ax = AxisDescriptor()
        ax.tag = tag
        ax.name = name
        ax.minimum = mn
        ax.default = df
        ax.maximum = mx
        doc.addAxis(ax)

    # Discrete axes (ital and MONO)
    d_ital = DiscreteAxisDescriptor()
    d_ital.tag = "ital"
    d_ital.name = "Italic"
    d_ital.values = [0, 1]
    d_ital.default = 0
    doc.addAxis(d_ital)

    d_mono = DiscreteAxisDescriptor()
    d_mono.tag = "MONO"
    d_mono.name = "Monospace"
    d_mono.values = [0, 1]
    d_mono.default = 0
    doc.addAxis(d_mono)

    # Sans / Condensed sources (MONO = 0)
    sans_map = [
        ("EPDSans-Upright-Default.ufo", 0, 400, 100, 14, 468, 79),
        ("EPDSans-Upright-Bold.ufo", 0, 900, 100, 14, 468, 79),
        ("EPDSans-Upright-Cond.ufo", 0, 400, 75, 14, 468, 79),
        ("EPDSans-Upright-CondBold.ufo", 0, 900, 75, 14, 468, 79),
        ("EPDSans-Upright-Opsz12.ufo", 0, 400, 100, 12, 468, 79),
        ("EPDSans-Upright-Opsz40.ufo", 0, 400, 100, 40, 468, 79),
        ("EPDSans-Upright-XTRA560.ufo", 0, 400, 100, 14, 560, 79),
        ("EPDSans-Upright-YOPQ55.ufo", 0, 400, 100, 14, 468, 55),
        ("EPDSans-Upright-YOPQ130.ufo", 0, 400, 100, 14, 468, 130),
        ("EPDSans-Italic-Default.ufo", 1, 400, 100, 14, 468, 79),
        ("EPDSans-Italic-Bold.ufo", 1, 900, 100, 14, 468, 79),
        ("EPDSans-Italic-Cond.ufo", 1, 400, 75, 14, 468, 79),
        ("EPDSans-Italic-CondBold.ufo", 1, 900, 75, 14, 468, 79),
        ("EPDSans-Italic-Opsz12.ufo", 1, 400, 100, 12, 468, 79),
        ("EPDSans-Italic-Opsz40.ufo", 1, 400, 100, 40, 468, 79),
        ("EPDSans-Italic-XTRA560.ufo", 1, 400, 100, 14, 560, 79),
        ("EPDSans-Italic-YOPQ55.ufo", 1, 400, 100, 14, 468, 55),
        ("EPDSans-Italic-YOPQ130.ufo", 1, 400, 100, 14, 468, 130),
    ]
    for fn, ital_v, wght_v, wdth_v, opsz_v, xtra_v, yopq_v in sans_map:
        src = SourceDescriptor()
        src.filename = f"../masters/sans/{fn}"
        src.familyName = "EPD Sans"
        src.styleName = fn.replace(".ufo", "")
        src.location = {
            "Weight": wght_v,
            "Width": wdth_v,
            "Optical Size": opsz_v,
            "Counter Transparency": xtra_v,
            "Horizontal Bar Thickness": yopq_v,
            "Italic": ital_v,
            "Monospace": 0,
        }
        doc.addSource(src)

    # Mono sources (MONO = 1)
    mono_map = [
        ("EPDMono-Upright-A.ufo", 0, 300),
        ("EPDMono-Upright-B.ufo", 0, 800),
        ("EPDMono-Upright-C.ufo", 0, 1000),
        ("EPDMono-Italic-A.ufo", 1, 300),
        ("EPDMono-Italic-B.ufo", 1, 800),
        ("EPDMono-Italic-C.ufo", 1, 1000),
    ]
    for fn, ital_v, wght_v in mono_map:
        src = SourceDescriptor()
        src.filename = f"../masters/mono/{fn}"
        src.familyName = "EPD Mono"
        src.styleName = fn.replace(".ufo", "")
        src.location = {
            "Weight": wght_v,
            "Width": 100,
            "Optical Size": ppem,
            "Counter Transparency": 468,
            "Horizontal Bar Thickness": 79,
            "Italic": ital_v,
            "Monospace": 1,
        }
        doc.addSource(src)

    build_upm = int(sz_cfg["build_upm"])
    for inst_id, inst_cfg in sz_cfg["instances"].items():
        ax_vals = inst_cfg["axes"]
        inst = InstanceDescriptor()
        inst.familyName = f"EPD {inst_cfg['modifier'].capitalize()}"
        inst.styleName = f"{inst_cfg['style']} {ppem}px"
        inst.name = f"epd_{inst_id}_{ppem}px"
        inst.location = {
            "Weight": float(ax_vals.get("wght", 400)),
            "Width": float(ax_vals.get("wdth", 100)),
            "Optical Size": float(ax_vals.get("opsz", ppem)),
            "Counter Transparency": float(ax_vals.get("XTRA", 468)),
            "Horizontal Bar Thickness": float(ax_vals.get("YOPQ", 79)),
            "Italic": int(ax_vals.get("ital", 0)),
            "Monospace": int(ax_vals.get("MONO", 0)),
        }
        inst.lib["public.fontInfo"] = {
            "unitsPerEm": build_upm,
            "ascender": round(build_upm * 0.78),
            "descender": -round(build_upm * 0.22),
            "capHeight": round(build_upm * 0.711),
            "xHeight": round(build_upm * 0.528),
        }
        doc.addInstance(inst)

    doc.write(str(out_path))
    return out_path


def generate_all_designspaces(cfg: ProjectConfig, ppems: list[int] | None = None) -> list[Path]:
    """Generate DesignSpace 5.1 files for requested PPEMs."""
    targets = ppems or cfg.ppem_range
    paths = [generate_designspace_for_ppem(cfg, p) for p in targets]
    print(f"[+] Generated {len(paths)} DesignSpace 5.1 files in designspaces/")
    return paths
