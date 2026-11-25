"""Verification suite for SPEC-EPD-FONT-001 Rev 1.1 pipeline, math, and 6 hard gates."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fontTools.designspaceLib import DesignSpaceDocument
from runner.config import REPO_ROOT, load_config, target_stem_px
from runner.math_psf import compute_betti_numbers, compute_psf_contrast_retention
from tools.agent.tools.epd_typography import discover_artifacts, inventory_fonts, measure_string_budget


def test_python_312_venv_isolation() -> None:
    assert sys.version_info[:2] == (3, 12)
    assert Path(sys.prefix).resolve() == (REPO_ROOT / ".venv").resolve()


def test_stem_schedule_formulas() -> None:
    expected = {
        12: (2, 3),
        14: (2, 3),
        16: (2, 3),
        18: (2, 3),
        20: (2, 3),
        24: (3, 4),
        28: (3, 5),
        32: (4, 5),
        36: (4, 6),
        40: (4, 7),
    }
    for ppem, (norm, bold) in expected.items():
        assert target_stem_px(ppem, "normal") == norm
        assert target_stem_px(ppem, "italic") == norm
        assert target_stem_px(ppem, "bold") == bold
        assert target_stem_px(ppem, "bold-italic") == bold


def test_designspaces_5_1_load_cleanly() -> None:
    cfg = load_config(REPO_ROOT)
    for ppem in cfg.ppem_range:
        ds_path = REPO_ROOT / "designspaces" / f"epd_{ppem}px.designspace"
        assert ds_path.is_file(), f"Missing {ds_path}"
        doc = DesignSpaceDocument.fromfile(str(ds_path))
        assert doc.formatVersion == "5.1"
        assert len(doc.instances) == 12


def test_psf_and_betti_math() -> None:
    import numpy as np

    # 8x8 hollow square -> b0=1, b1=1
    ring = np.zeros((8, 8), dtype=np.uint8)
    ring[1:7, 1:7] = 1
    ring[3:5, 3:5] = 0
    b0, b1 = compute_betti_numbers(ring)
    assert b0 == 1
    assert b1 == 1
    psf = compute_psf_contrast_retention(ring, sigma_um=135.0)
    assert 0.0 < psf["retention_pct"] <= 100.0


def test_full_120_strike_audit_report_passed() -> None:
    report_path = REPO_ROOT / "build" / "proofs" / "audit_report.json"
    assert report_path.is_file(), "Run `scripts/epd_font.bat all` before pytest"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["total_strikes"] == 120
    assert report["passed_strikes"] == 120
    assert report["failed_strikes"] == 0
    assert report["overall_status"] == "PASS"


def test_downstream_artifacts_and_epd_typography_bridge() -> None:
    cfg = load_config(REPO_ROOT)
    req_cps = cfg.mandatory_codepoints()
    assert len(req_cps) >= 520

    arts = discover_artifacts(workspace_dir=str(REPO_ROOT))
    assert arts["vault_path"] is not None
    assert arts["metrics_dir"] is not None

    inv = inventory_fonts(workspace_dir=str(REPO_ROOT))
    assert len(inv["strikes"]) == 120

    budget = measure_string_budget(
        strike="humid1_font_epd_sans_normal_14",
        text="Vapor Pressure",
        right_text="42.8 hPa",
        right_strike="humid1_font_epd_mono_bold_16",
        workspace_dir=str(REPO_ROOT),
    )
    assert budget["fits_budget"] is True
