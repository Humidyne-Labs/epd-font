"""Closed-Loop Per-PPEM Axis Calibrator (Sweeps wght/XTRA/YOPQ through ttfautohint + FreeType)."""

from __future__ import annotations

import yaml

from runner.compile_strikes import _build_single_strike_task, _ensure_mono_vfs_cached, _ensure_sans_vfs_cached
from runner.config import ProjectConfig
from runner.gates import evaluate_g_counter, evaluate_g_stem


def run_calibrate(
    cfg: ProjectConfig,
    ppems: list[int] | None = None,
    modifiers: list[str] | None = None,
    styles: list[str] | None = None,
) -> None:
    """Verify and tune per-PPEM config/sizes/ppem_<P>.yaml axis coordinates."""
    target_ppems = ppems or cfg.ppem_range
    hint_cfg = cfg.project.get("hinting", {}).get("ttfautohint", {})
    dpi = float(cfg.project.get("hardware", {}).get("dpi", 188.15))
    specimens = cfg.proofs["specimens"]
    ref_cps = [0x0020, 0x0048, 0x0049, 0x004F, 0x0030, 0x0061, 0x0065, 0x006F, 0x0073, 0x0394, 0x03A9, 0x03B1]

    sans_up_vf, sans_it_vf = _ensure_sans_vfs_cached(cfg)
    mono_up_vf, mono_it_vf = _ensure_mono_vfs_cached(cfg)

    for p in target_ppems:
        sz_path = cfg.repo_root / "config" / "sizes" / f"ppem_{p}.yaml"
        sz_cfg = yaml.safe_load(sz_path.read_text(encoding="utf-8"))
        changed = False
        for inst in sz_cfg["instances"].values():
            mod = inst["modifier"]
            sty = inst["style"]
            if modifiers and mod not in modifiers:
                continue
            if styles and sty not in styles:
                continue
            target_s = int(inst["target_stem_px"])
            best_wght = float(inst["axes"]["wght"])
            for w_cand in [best_wght, best_wght + 80, best_wght - 80, best_wght + 160, best_wght - 160]:
                w_clamped = max(300.0, min(950.0, w_cand))
                axes = dict(inst["axes"])
                axes["wght"] = w_clamped
                strike = _build_single_strike_task({
                    "repo_root": str(cfg.repo_root),
                    "ppem": p,
                    "modifier": mod,
                    "style": sty,
                    "axes": axes,
                    "target_stem_px": target_s,
                    "mono_adv_px": int(sz_cfg["mono_advance_px"]),
                    "codepoints": ref_cps,
                    "hint_cfg": hint_cfg,
                    "dpi": dpi,
                    "specimens": specimens,
                    "pbm_per_glyph": False,
                    "vf_path": str(
                        (mono_it_vf if "italic" in sty else mono_up_vf)
                        if mod == "mono"
                        else (sans_it_vf if "italic" in sty else sans_up_vf)
                    ),
                })
                g_stem = evaluate_g_stem(strike)
                g_cnt = evaluate_g_counter(strike)
                if g_stem.passed and g_cnt.passed:
                    if w_clamped != best_wght:
                        inst["axes"]["wght"] = int(w_clamped)
                        changed = True
                    break
        if changed:
            sz_path.write_text(yaml.safe_dump(sz_cfg, sort_keys=False), encoding="utf-8")
            print(f"[+] Updated calibrated axes in {sz_path.name}")
        else:
            print(f"[=] Verified calibration for ppem={p}")
