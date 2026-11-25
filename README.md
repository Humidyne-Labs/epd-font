# `epd-font` v2.0.0 — EPD Bi-Level Typography System (`SPEC-EPD-FONT-001 Rev 1.1`)

A 1-bit (`LV_COLOR_FORMAT_I1`) Electrophoretic Display (EPD) typography pipeline built on **UFO 3** masters, **DesignSpace 5.1** XML, **sub-grid coordinate snapping (`UPM = 100 * P`)**, **FreeType `FT_LOAD_TARGET_MONO`** rasterization, and **6 quantitative pass/fail gates**.

---

## 1. Architecture Overview

```mermaid
graph LR;
    Donors["UFO 3 Donors (Roboto Flex, Recursive, DejaVu, STIX Two)"] --> Norm["Stage 0: normalize"];
    Norm --> Masters["masters/{sans,mono,symbols}/*.ufo"];
    Masters --> DS["Stage 1: DesignSpace 5.1"];
    DS --> Snap["Stage 2: UPM=100*P Sub-Grid Snap"];
    Snap --> Hint["Stage 3: ufo2ft + ttfautohint + FT_LOAD_TARGET_MONO"];
    Hint --> Out["BDF 2.1, PBM P1/P4, LVGL C/H, CSV, Vault"];
    Hint --> Gates["6 Hard Gates + 1x/8x/PSF Proofs"];
```

---

## 2. Optical-Floor Proportional Scaling Law

- **Optical Floor (`12 px - 16 px`):** Clamps vertical stems to `2 px` (`normal`/`italic`) and `3 px` (`bold`/`bold-italic`) to prevent lateral microcapsule scattering washout.
- **Proportional Scaling (`18 px - 40 px`):** Scales stems linearly with PPEM $P$:

$$
S_{\text{norm}}(P) = \max\bigl(2,\; \text{round}(0.11 \times P)\bigr)\text{ px}
$$

$$
S_{\text{bold}}(P) = \max\bigl(3,\; S_{\text{norm}}(P) + 1,\; \text{round}(0.17 \times P)\bigr)\text{ px}
$$

---

## 3. Isolated Python 3.12 Environment & CLI Usage

All Python tools run strictly inside `<repo>/.venv` (`Python 3.12`, `PYTHONNOUSERSITE=1`) to avoid conflicts with system Python installations.

```powershell
# 1. Provision .venv (once)
powershell -ExecutionPolicy Bypass -File scripts\setup_venv.ps1

# 2. Verify environment isolation
scripts\epd_font.bat --check-env

# 3. Run full 120-strike build, serialization, 6-gate audit, and PSF proofs
scripts\epd_font.bat all
```

Available CLI subcommands (`scripts\epd_font.bat <cmd>`):
- `normalize`: Ingest donor UFOs into normalized `masters/{sans,mono,symbols}/` (`--force` to rebuild).
- `designspaces`: Emit `designspaces/epd_<P>px.designspace` (`format="5.1"`).
- `calibrate`: Sweep per-PPEM axis coordinates in `config/sizes/ppem_<P>.yaml`.
- `build`: Compile, sub-grid snap, hint, rasterize, and serialize `BDF`, `PBM`, `LVGL C/H`, `CSV`, and `humid1_epd_vault.json.gz`.
- `audit` / `proofs`: Evaluate all 6 gates (`G_STEM`, `G_CONTRAST`, `G_COUNTER`, `G_METRICS`, `G_MONO`, `G_CLIP`) and emit `build/proofs/AUDIT.md`, `specimen_1x.pbm`, `grid_8x.png`, and `epd_psf_sim.png`.
