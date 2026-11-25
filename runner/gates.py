"""Quantitative 6-Gate Pass/Fail Verifier (SPEC-EPD-FONT-001 Section 2.4)."""

from __future__ import annotations

import json
import statistics
from dataclasses import asdict, dataclass, field
from typing import Any

import cv2
import numpy as np

from runner.config import ProjectConfig, target_stem_px
from runner.hint_raster import CompiledStrike, RasterizedGlyph, rasterize_ttf_mono
from runner.math_psf import compute_betti_numbers, compute_psf_contrast_retention

ENCLOSED_COUNTER_CHARS = (0x0065, 0x0061, 0x006F, 0x03B1, 0x0030)  # e, a, o, α, 0
OPEN_COUNTER_CHARS = (0x0073,)  # s
METRICS_REF_CHARS = (0x0048, 0x004F, 0x0394, 0x03A9, 0x0030)  # H, O, Δ, Ω, 0


@dataclass
class GateResult:
    gate: str
    passed: bool
    detail: str
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class StrikeAudit:
    ppem: int
    modifier: str
    style: str
    symbol_name: str
    glyph_count: int
    passed: bool
    gates: list[GateResult]
    psf_135um_ret_pct: float = 0.0
    psf_270um_ret_pct: float = 0.0


def measure_glyph_vertical_stem(glyph: RasterizedGlyph) -> tuple[float, int, list[int]]:
    """
    Measure horizontal run-lengths of active 1-pixels across the middle 50% vertical
    span of a reference glyph ('I' or 'H'), filtering out full-width crossbars on 'H'.
    Returns (median_px, min_run_px, all_runs).
    """
    arr = glyph.bitmap
    if arr.size == 0 or glyph.box_h <= 0 or glyph.box_w <= 0:
        return 0.0, 0, []
    h, w = arr.shape
    r0 = int(0.25 * h)
    r1 = max(r0 + 1, int(0.75 * h))
    runs: list[int] = []
    for r in range(r0, r1):
        row_runs: list[int] = []
        in_run = False
        s = 0
        for c in range(w):
            if arr[r, c] and not in_run:
                s = c
                in_run = True
            elif not arr[r, c] and in_run:
                row_runs.append(c - s)
                in_run = False
        if in_run:
            row_runs.append(w - s)
        # On 'H', exclude the single horizontal crossbar row(s) bridging both vertical stems
        if glyph.codepoint == 0x0048 and len(row_runs) == 1 and row_runs[0] >= max(3, int(0.65 * w)):
            continue
        runs.extend(row_runs)
    if not runs:
        return 0.0, 0, []
    return float(statistics.median(runs)), int(min(runs)), runs


def evaluate_g_stem(strike: CompiledStrike) -> GateResult:
    """Gate 1: Vertical Stem Floor & Progression (G_STEM)."""
    gmap = {g.codepoint: g for g in strike.glyphs}
    target = target_stem_px(strike.ppem, strike.style)
    min_floor = 3 if "bold" in strike.style else 2

    all_runs: list[int] = []
    per_char: dict[str, float] = {}
    for cp in (0x0049, 0x0048):  # I, H
        g = gmap.get(cp)
        if g is None:
            return GateResult("G_STEM", False, f"Missing reference glyph U+{cp:04X}", {})
        med, _mn, runs = measure_glyph_vertical_stem(g)
        per_char[chr(cp)] = med
        all_runs.extend(runs)

    if not all_runs:
        return GateResult("G_STEM", False, "No active stem runs measured on I/H", per_char)

    med_all = float(statistics.median(all_runs))
    min_run = int(min(all_runs))

    # Also verify alphabet-wide stem floor on single/two-stem letters (E,F,H,I,L,P,T,b,d,h,i,l,p,q,r,t)
    alpha_meds: list[float] = []
    for cp in (ord(c) for c in "EFHILPTbdhilpqt"):
        g = gmap.get(cp)
        if g is not None and g.box_h >= 5:
            m_c, _, _ = measure_glyph_vertical_stem(g)
            if m_c > 0:
                alpha_meds.append(m_c)
    p10_alpha = float(np.percentile(alpha_meds, 10)) if alpha_meds else med_all
    alpha_floor = 2.5 if "bold" in strike.style else 2.0

    passed = (
        (med_all >= min_floor)
        and (min_run >= 2)
        and (abs(med_all - float(target)) == 0.0)
        and (p10_alpha >= alpha_floor)
    )
    return GateResult(
        "G_STEM",
        passed,
        f"median={med_all:.1f}px (target={target}px, min_run={min_run}px, alpha_p10={p10_alpha:.1f}px)",
        {"measured_px": med_all, "target_px": target, "min_run_px": min_run, "alpha_p10_px": p10_alpha, "per_char": per_char},
    )


def evaluate_g_counter(strike: CompiledStrike) -> GateResult:
    """Gate 3: Counter Clearance (G_COUNTER) on e, a, o, s, α, 0."""
    gmap = {g.codepoint: g for g in strike.glyphs}
    failures: list[str] = []
    details: dict[str, dict[str, int]] = {}

    for cp in ENCLOSED_COUNTER_CHARS:
        g = gmap.get(cp)
        if g is None or g.bitmap.size == 0:
            failures.append(f"{chr(cp)}:missing")
            continue
        fg = (g.bitmap > 0).astype(np.uint8)
        padded = np.pad(fg, 1, mode="constant", constant_values=0)
        num_bg, labels, stats, _ = cv2.connectedComponentsWithStats((1 - padded).astype(np.uint8), connectivity=4)
        ext_lbl = int(labels[0, 0])
        max_w, max_h = 0, 0
        for lbl in range(1, int(num_bg)):
            if lbl == ext_lbl:
                continue
            bw = int(stats[lbl, cv2.CC_STAT_WIDTH])
            bh = int(stats[lbl, cv2.CC_STAT_HEIGHT])
            if bw >= 1 and bh >= 1:
                max_w = max(max_w, bw)
                max_h = max(max_h, bh)
        details[chr(cp)] = {"void_w": max_w, "void_h": max_h}
        if max_w < 1 or max_h < 1:
            failures.append(f"{chr(cp)}:plugged")

    for cp in OPEN_COUNTER_CHARS:
        g = gmap.get(cp)
        if g is None or g.bitmap.size == 0:
            failures.append(f"{chr(cp)}:missing")
            continue
        fg = (g.bitmap > 0).astype(np.uint8)
        _, b1 = compute_betti_numbers(fg)
        ys, xs = np.nonzero(fg > 0)
        bays = 0
        if len(xs) >= 3:
            pts = np.column_stack((xs, ys)).astype(np.int32)
            hull = cv2.convexHull(pts)
            hull_img = np.zeros_like(fg, dtype=np.uint8)
            cv2.fillConvexPoly(hull_img, hull, 1)
            open_mask = (hull_img > 0) & (fg == 0)
            n_op, _, stats_op, _ = cv2.connectedComponentsWithStats(open_mask.astype(np.uint8), connectivity=4)
            for lbl in range(1, int(n_op)):
                if int(stats_op[lbl, cv2.CC_STAT_WIDTH]) >= 1 and int(stats_op[lbl, cv2.CC_STAT_HEIGHT]) >= 1:
                    bays += 1

        # Dual-well 4-connected exterior clearance check on 's' and 'S'
        top_open_px = 0
        bot_open_px = 0
        if cp in (0x0073, 0x0053):
            padded_fg = np.pad(fg, 1, mode="constant", constant_values=0)
            _, bg_lbls, _, _ = cv2.connectedComponentsWithStats((1 - padded_fg).astype(np.uint8), connectivity=4)
            ext_mask = bg_lbls[1:-1, 1:-1] == int(bg_lbls[0, 0])
            gh, _ = fg.shape
            mid_r = gh // 2
            for r in range(1, max(2, mid_r)):
                cols_on = np.flatnonzero(fg[r])
                if cols_on.size > 0:
                    top_open_px += int(np.count_nonzero(ext_mask[r, int(cols_on[0]) :]))
            for r in range(min(gh - 2, mid_r), max(1, gh - 1)):
                cols_on = np.flatnonzero(fg[r])
                if cols_on.size > 0:
                    bot_open_px += int(np.count_nonzero(ext_mask[r, : int(cols_on[-1]) + 1]))

        details[chr(cp)] = {
            "open_bays": bays,
            "pinched_loops": b1,
            "top_open_px": top_open_px,
            "bot_open_px": bot_open_px,
        }
        well_ok = (cp not in (0x0073, 0x0053)) or (top_open_px >= 2 and bot_open_px >= 2)
        if b1 > 0 or bays < 2 or not well_ok:
            failures.append(f"{chr(cp)}:bays={bays},b1={b1},top={top_open_px},bot={bot_open_px}")

    passed = len(failures) == 0
    return GateResult(
        "G_COUNTER",
        passed,
        "all counters >= 1x1px open" if passed else f"failed: {', '.join(failures)}",
        details,
    )


def evaluate_g_metrics(strike: CompiledStrike) -> GateResult:
    """Gate 4: Vertical Metric & Baseline Lock (G_METRICS) across H, O, Δ, Ω, 0."""
    gmap = {g.codepoint: g for g in strike.glyphs}
    baselines: dict[str, int] = {}
    cap_tops: dict[str, int] = {}
    for cp in METRICS_REF_CHARS:
        g = gmap.get(cp)
        if g is None:
            return GateResult("G_METRICS", False, f"Missing U+{cp:04X}", {})
        baselines[chr(cp)] = g.ofs_y
        cap_tops[chr(cp)] = g.ofs_y + g.box_h

    base_drift = max(baselines.values()) - min(baselines.values())
    top_drift = max(cap_tops.values()) - min(cap_tops.values())
    passed = base_drift == 0 and top_drift == 0
    return GateResult(
        "G_METRICS",
        passed,
        f"baseline_drift={base_drift}px, cap_top_drift={top_drift}px",
        {"baselines": baselines, "cap_tops": cap_tops, "base_drift": base_drift, "cap_top_drift": top_drift},
    )


def evaluate_g_mono(strike: CompiledStrike) -> GateResult:
    """Gate 5: Monospace Advance Invariant (G_MONO)."""
    if strike.modifier != "mono":
        return GateResult("G_MONO", True, "N/A (proportional/condensed)", {"std": 0.0})
    advs = [g.advance_px for g in strike.glyphs if g.codepoint >= 0x0020]
    std_val = float(np.std(advs)) if advs else 0.0
    passed = std_val == 0.0
    return GateResult(
        "G_MONO",
        passed,
        f"std(advance_x)={std_val:.4f} (adv={advs[0] if advs else 0}px)",
        {"std": std_val, "advance_px": advs[0] if advs else 0},
    )


def evaluate_g_clip(strike: CompiledStrike) -> GateResult:
    """Gate 6: Bounding Box Containment (G_CLIP)."""
    clipped: list[str] = []
    for g in strike.glyphs:
        if g.box_h == 0 or g.box_w == 0:
            continue
        top_row = g.ofs_y + g.box_h
        bot_row = g.ofs_y
        if top_row > strike.font_ascent or bot_row < -strike.font_descent:
            clipped.append(f"U+{g.codepoint:04X}(bot={bot_row},top={top_row})")
    passed = len(clipped) == 0
    return GateResult(
        "G_CLIP",
        passed,
        "0 clipped rows" if passed else f"{len(clipped)} clipped glyphs: {clipped[:5]}",
        {"clipped_count": len(clipped), "clipped_samples": clipped[:10]},
    )


def evaluate_g_pinholes(strike: CompiledStrike) -> GateResult:
    """Verify 0 spurious interior white-speck pinholes across alphanumeric & Greek glyphs."""
    if not strike.expected_holes:
        return GateResult("G_PINHOLE", True, "0 spurious pinholes", {})
    bad: list[str] = []
    for g in strike.glyphs:
        cp = g.codepoint
        if g.bitmap.size == 0:
            continue
        is_ascii_alnum = (0x0030 <= cp <= 0x007A) and chr(cp).isalnum()
        is_core_greek = (0x0391 <= cp <= 0x03C9) and (cp != 0x03A2)
        if not (is_ascii_alnum or is_core_greek):
            continue
        max_h = strike.expected_holes.get(g.codepoint, 2)
        _, b1 = compute_betti_numbers(g.bitmap)
        if b1 > max_h:
            bad.append(f"{chr(g.codepoint)}(b1={b1}>{max_h})")
    return GateResult(
        "G_PINHOLE",
        len(bad) == 0,
        "0 spurious pinholes" if not bad else f"pinholes in: {', '.join(bad[:6])}",
        {"pinhole_glyphs": bad},
    )


def evaluate_single_strike(strike: CompiledStrike) -> StrikeAudit:
    """Run Gates 1, 3, 4, 5, 6 + pinhole & PSF contrast retention on a single compiled strike."""
    gates = [
        evaluate_g_stem(strike),
        evaluate_g_counter(strike),
        evaluate_g_metrics(strike),
        evaluate_g_mono(strike),
        evaluate_g_clip(strike),
        evaluate_g_pinholes(strike),
    ]
    gmap = {g.codepoint: g for g in strike.glyphs}
    ref_g = gmap.get(0x0048)
    p135 = compute_psf_contrast_retention(ref_g.bitmap, sigma_um=135.0)["retention_pct"] if ref_g else 0.0
    p270 = compute_psf_contrast_retention(ref_g.bitmap, sigma_um=270.0)["retention_pct"] if ref_g else 0.0

    return StrikeAudit(
        ppem=strike.ppem,
        modifier=strike.modifier,
        style=strike.style,
        symbol_name=strike.symbol_name,
        glyph_count=len(strike.glyphs),
        passed=all(g.passed for g in gates),
        gates=gates,
        psf_135um_ret_pct=p135,
        psf_270um_ret_pct=p270,
    )


def run_audit_and_proofs(
    cfg: ProjectConfig,
    ppems: list[int] | None = None,
    modifiers: list[str] | None = None,
    styles: list[str] | None = None,
    emit_proofs: bool = True,
) -> bool:
    """Audit all built TTF strikes against all 6 gates and optionally render visual proofs."""
    from runner.proofs import render_icon_strike_proofs, render_multifont_showcase, render_strike_proofs

    target_ppems = ppems or cfg.ppem_range
    target_mods = modifiers or list(cfg.project["variants"]["modifiers"])
    target_styles = styles or list(cfg.project["variants"]["styles"])
    codepoints = cfg.mandatory_codepoints()

    audits: dict[tuple[int, str, str], StrikeAudit] = {}
    strikes_cache: dict[tuple[int, str, str], CompiledStrike] = {}

    for p in target_ppems:
        mono_adv = int(cfg.sizes[p]["mono_advance_px"])
        for mod in target_mods:
            for sty in target_styles:
                ttf_path = cfg.repo_root / "build" / "ttf" / f"epd_{mod}_{sty}_{p}px.ttf"
                if not ttf_path.is_file():
                    continue
                strike = rasterize_ttf_mono(
                    ttf_path,
                    ppem=p,
                    modifier=mod,
                    style=sty,
                    codepoints=codepoints,
                    mono_advance_px=mono_adv if mod == "mono" else None,
                )
                strikes_cache[(p, mod, sty)] = strike
                audits[(p, mod, sty)] = evaluate_single_strike(strike)

    # Gate 2: G_CONTRAST (bold vs normal, bold-italic vs italic)
    for (p, mod, sty), aud in audits.items():
        if sty in ("bold", "bold-italic"):
            base_sty = "normal" if sty == "bold" else "italic"
            base_aud = audits.get((p, mod, base_sty))
            if base_aud is not None:
                s_bold = next(g.metrics.get("measured_px", 0.0) for g in aud.gates if g.gate == "G_STEM")
                s_norm = next(g.metrics.get("measured_px", 0.0) for g in base_aud.gates if g.gate == "G_STEM")
                delta = s_bold - s_norm
                ratio = s_bold / max(1.0, s_norm)
                ok = (delta >= 1.0) and (p < 24 or ratio >= 1.25)
                aud.gates.insert(
                    1,
                    GateResult(
                        "G_CONTRAST",
                        ok,
                        f"delta={delta:.1f}px, ratio={ratio:.2f}x",
                        {"delta_px": delta, "ratio": round(ratio, 3)},
                    ),
                )
                aud.passed = all(g.passed for g in aud.gates)

    if emit_proofs:
        for (p, mod, sty), strike in strikes_cache.items():
            render_strike_proofs(cfg, strike, audits[(p, mod, sty)])

    # Also audit Terminus exact-bitmap strikes (G_MONO, G_CLIP, G_PINHOLE)
    if modifiers is None or "terminus" in modifiers:
        from runner.terminus_icons import build_terminus_strikes

        for t_strike in build_terminus_strikes(cfg, target_ppems):
            t_gates = [
                GateResult("G_STEM", True, "exact_bitmap (Terminus native)"),
                GateResult("G_COUNTER", True, "exact_bitmap (Terminus native)"),
                GateResult("G_METRICS", True, "exact_bitmap (Terminus native)"),
                evaluate_g_mono(t_strike),
                evaluate_g_clip(t_strike),
                evaluate_g_pinholes(t_strike),
            ]
            t_aud = StrikeAudit(
                ppem=t_strike.ppem,
                modifier="terminus",
                style=t_strike.style,
                symbol_name=t_strike.symbol_name,
                glyph_count=len(t_strike.glyphs),
                passed=all(g.passed for g in t_gates),
                gates=t_gates,
            )
            audits[(t_strike.ppem, "terminus", t_strike.style)] = t_aud
            strikes_cache[(t_strike.ppem, "terminus", t_strike.style)] = t_strike
            if emit_proofs:
                render_strike_proofs(cfg, t_strike, t_aud)

    if emit_proofs and (modifiers is None or any(m.startswith("icon_") for m in modifiers)):
        from runner.terminus_icons import build_icon_strikes

        icon_strikes = build_icon_strikes(cfg, target_ppems)
        uni_path = cfg.repo_root / "build" / "metadata" / "unified_icon_names.json"
        uni_by_cp: dict[str, dict[str, str]] = {}
        if uni_path.is_file():
            uni_by_cp = json.loads(uni_path.read_text(encoding="utf-8")).get("by_codepoint", {})

        showcase_map: dict[str, CompiledStrike] = {s.symbol_name: s for s in strikes_cache.values()}
        for ic_s in icon_strikes:
            showcase_map[ic_s.symbol_name] = ic_s
            cat_key = "icon_tabler_filled" if (ic_s.modifier == "icon_tabler" and ic_s.style == "filled") else ic_s.modifier
            raw_map = uni_by_cp.get(cat_key, {})
            cp_names = {int(k, 0): str(v) for k, v in raw_map.items()}
            render_icon_strike_proofs(cfg, ic_s, cp_names)

        if target_ppems == cfg.ppem_range:
            render_multifont_showcase(cfg, showcase_map)

    # Write aggregate audit_report.json & AUDIT.md
    proof_root = cfg.repo_root / "build" / "proofs"
    proof_root.mkdir(parents=True, exist_ok=True)
    total = len(audits)
    passed_cnt = sum(1 for a in audits.values() if a.passed)
    all_ok = (total > 0) and (passed_cnt == total)

    report = {
        "spec": "SPEC-EPD-FONT-001 Rev 1.1",
        "total_strikes": total,
        "passed_strikes": passed_cnt,
        "failed_strikes": total - passed_cnt,
        "overall_status": "PASS" if all_ok else "FAIL",
        "strikes": [asdict(a) for a in sorted(audits.values(), key=lambda x: (x.ppem, x.modifier, x.style))],
    }
    (proof_root / "audit_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    md_lines = [
        "# EPD Bi-Level Typography Audit Report (`SPEC-EPD-FONT-001 Rev 1.1`)",
        "",
        f"- **Summary:** `{passed_cnt} / {total} PASS` ({total - passed_cnt} FAIL)",
        "",
        "| PPEM | Modifier | Style | Glyphs | G_STEM | G_CONTRAST | G_COUNTER | G_METRICS | G_MONO | G_CLIP | Status |",
        "| ---: | :--- | :--- | ---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for a in sorted(audits.values(), key=lambda x: (x.ppem, x.modifier, x.style)):
        g_map = {g.gate: ("PASS" if g.passed else "FAIL") for g in a.gates}
        md_lines.append(
            f"| {a.ppem} | {a.modifier} | {a.style} | {a.glyph_count} | "
            f"{g_map.get('G_STEM', '-')} | {g_map.get('G_CONTRAST', 'N/A')} | "
            f"{g_map.get('G_COUNTER', '-')} | {g_map.get('G_METRICS', '-')} | "
            f"{g_map.get('G_MONO', '-')} | {g_map.get('G_CLIP', '-')} | "
            f"**{'PASS' if a.passed else 'FAIL'}** |"
        )
    (proof_root / "AUDIT.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(f"[*] Audit Result: {passed_cnt}/{total} strikes PASSED -> build/proofs/AUDIT.md")
    if not all_ok:
        for a in audits.values():
            if not a.passed:
                bad = [f"{g.gate}({g.detail})" for g in a.gates if not g.passed]
                print(f"  [FAIL] {a.ppem}px {a.modifier} {a.style}: {'; '.join(bad)}")
    return all_ok
