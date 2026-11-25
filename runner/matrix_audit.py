"""Standardized Cross-Size & Cross-Weight Canonical Sample Matrix Auditor."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from tools.agent.tools.epd_bdf_pbm_inspector import _measure_h_and_v_runs, _parse_bdf


def run_matrix_audit(repo_root: Path) -> dict[str, Any]:
    """Audit Normal-vs-Bold separation across standardized categories for all built families & sizes."""
    samples_cfg = yaml.safe_load((repo_root / "config" / "audit_samples.yaml").read_text(encoding="utf-8"))
    categories: dict[str, list[str]] = {
        k: list(v["chars"]) for k, v in samples_cfg.get("categories", {}).items()
    }
    min_ratio = float(samples_cfg.get("min_bold_ink_ratio", 1.18))
    bdf_dir = repo_root / "build" / "bdf"
    proof_dir = repo_root / "build" / "proofs"
    proof_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    md_lines = [
        "# Standardized Canonical Character Matrix Audit",
        "",
        f"Minimum target Bold-vs-Normal ink ratio: `{min_ratio:.2f}x`",
        "",
        "| Family | PPEM | " + " | ".join(f"{c} (ink)" for c in categories) + " | Norm vMed | Bold vMed |",
        "| :--- | ---: | " + " | ".join(":---:" for _ in categories) + " | ---: | ---: |",
    ]

    for mod in ("sans", "condensed", "mono"):
        for bdf_norm in sorted(bdf_dir.glob(f"humid1_font_epd_{mod}_normal_*.bdf")):
            ppem_str = bdf_norm.stem.rsplit("_", 1)[-1]
            if not ppem_str.isdigit():
                continue
            ppem = int(ppem_str)
            bdf_bold = bdf_dir / f"humid1_font_epd_{mod}_bold_{ppem}.bdf"
            if not bdf_bold.is_file():
                continue

            gn = _parse_bdf(bdf_norm)["glyphs"]
            gb = _parse_bdf(bdf_bold)["glyphs"]

            def _vmed(gmap: dict[int, Any]) -> float:
                meds: list[float] = []
                for ch in ("I", "H", "E", "F", "L", "T", "n", "l"):
                    g = gmap.get(ord(ch))
                    if g and g.box_h >= 5:
                        hr, _ = _measure_h_and_v_runs(g.rows, cp=ord(ch))
                        if hr:
                            hr_s = sorted(hr)
                            meds.append(float(hr_s[len(hr_s) // 2]))
                meds.sort()
                return meds[len(meds) // 2] if meds else 0.0

            n_vmed = _vmed(gn)
            b_vmed = _vmed(gb)
            cat_res: dict[str, dict[str, Any]] = {}
            cells: list[str] = []
            for cname, chs in categories.items():
                n_ink = 0
                b_ink = 0
                for ch in chs:
                    cp = ord(ch)
                    if cp in gn and cp in gb:
                        n_ink += sum(sum(r) for r in gn[cp].rows)
                        b_ink += sum(sum(r) for r in gb[cp].rows)
                ratio = round(b_ink / max(1.0, float(n_ink)), 2)
                ok = ratio >= min_ratio
                cat_res[cname] = {"norm_ink": n_ink, "bold_ink": b_ink, "ratio": ratio, "ok": ok}
                cells.append(f"{ratio:.2f}x" if ok else f"**{ratio:.2f}x!**")

            rows.append({
                "family": mod,
                "ppem": ppem,
                "norm_vmed": n_vmed,
                "bold_vmed": b_vmed,
                "categories": cat_res,
            })
            md_lines.append(
                f"| {mod} | {ppem} | " + " | ".join(cells) + f" | {n_vmed:.1f}px | {b_vmed:.1f}px |"
            )

    (proof_dir / "MATRIX_AUDIT.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    payload = {"schema_version": "2.1.0", "min_bold_ink_ratio": min_ratio, "rows": rows}
    (proof_dir / "matrix_audit.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
