# `epd-font` (v1.0.12) — Humidyne Labs / Humiditron 1-BPP Bilevel Embedded Font & Modular Icon Studio

[![Version](https://img.shields.io/badge/version-v1.0.12-blue.svg)](VERSION.json)
[![Repository](https://img.shields.io/badge/github-Humidyne--Labs%2Fepd--font-181717.svg)](https://github.com/Humidyne-Labs/epd-font)
[![License](https://img.shields.io/badge/license-MIT%20%2F%20OFL--1.1%20%2F%20ISC-green.svg)](LICENSE)

**`epd-font`** is a general-purpose, deterministic **1-bit-per-pixel (`1-bpp`) bilevel typography and modular iconography studio** engineered by **Humidyne Labs / Humiditron** for monochrome E-Paper Displays (EPD), OLEDs, Sharp Memory LCDs, and embedded LVGL v8/v9 applications.

---

## 1. Key Capabilities in v1.0.12

1. **80 Standardized Static TrueType (`.ttf`) Binaries (`build/static_ttfs/`)**:
   - **IBM Plex Suite (41 cuts)**: `Sans` (`Thin 100`..`Bold 700` + Italics), `Sans Condensed` (`wdth=85`), `Mono`, `Serif`, and `Math`.
   - **Terminus Font v4.49.1 (26 cuts: 22 size-specific Normal/Bold 12-40pt + VGA 14/16 + Regular/Bold aliases)**: `Terminus-Regular.ttf` and `Terminus-Bold.ttf` (`1,356` glyphs each, automatically synthesized from `assets/font_assets/terminus-font-4.49.1.tar.gz` into pure quadratic `.ttf` outlines).
   - **4 Modular Icon Suites (13 cuts, 12,200+ indexed PUA icons)**:
     - **Font Awesome v7.3.1** (`Solid`, `Regular`, `Brands` — `2,396` icons)
     - **Lucide v1.16.0** (`Regular` — `2,043` icons)
     - **Phosphor v2.1.0** (`Thin`, `Light`, `Regular`, `Bold`, `Fill` — `1,513` PUA-sanitized icons with semantic glyph names baked in)
     - **Tabler v3.41.1** (`Thin200`, `Light300`, `Regular`, `Filled` — `6,257` icons)
   - **Custom `.ttf` Support**: Drop any third-party `.ttf` into `build/static_ttfs/` and reference `"ttf_file": "YourFont.ttf"` in any `.scheme.json`.
2. **Clean Git-Friendly `build/` vs `dist/` vs Root Patch Architecture**:
   - **`build/`** (gitignored): Houses all generated intermediate artifacts—`build/static_ttfs/`, `build/metadata/`, `build/<workflow>/ascii_patches/`, `build/<workflow>/fonts/`, `build/<workflow>/bdf/`, `build/<workflow>/metrics/`, `build/<workflow>/inspect_pages/`, and `build/<workflow>/inspect_chars/`.
   - **`dist/`** (gitignored): Houses self-contained distribution bundles (`dist/example_distro/`, `dist/audit_distro/`, `dist/h1os_distro/`) containing the pre-rasterized Strike Vault (`humid1_epd_vault.json.gz`), zero-dependency emitter (`humid1_fw_emit.py`), `.c`/`.h` sources, and licenses.
   - **`font_icon_epd_patches.json`** (root-tracked in Git): Persists hand-edited 1:1 ASCII pixel patches at the repository root so `build/` and `dist/` can be deleted or ignored without ever losing pixel-level glyph refinements.
3. **Configurable Display Geometry (`--dpi`, `--screen-width`, `--screen-height`, `--safe-margin`)**:
   - No hardcoded panel assumptions: configure target resolution, DPI, and safe margins via CLI flags or the `"target_display"` object in any `.scheme.json`.
4. **Agent-First Tooling Suite (`tools/agent/`)**:
   - Purpose-built CLI tools (`char_info.py`, `string_info.py`, `icon_search.py`, `font_catalog_info.py`), `skills/*/SKILL.md`, and `rules/AGENT_TYPOGRAPHY_RULES.md` that give AI coding agents and engineers exact pixel metrics, kerning-aware string widths, and PUA icon UTF-8 literals with zero guessing.

---

## 2. Repository Directory Structure (`v1.0.12`)

```text
epd-font/
├── LICENSE                                  # MIT License (Humidyne Labs / Humiditron code & tooling)
├── VERSION.json                             # Release & upstream asset version manifest (v1.0.12)
├── font_icon_epd_patches.json               # Root-tracked optical 1-bpp pixel patch manifest (persisted in Git)
├── README.md                                # Primary repository overview & quick-start
├── CHANGELOG.md                             # Chronological release history (v0.0.1 -> v1.0.12)
├── docs/
│   ├── HOW_TO_GUIDE.md                      # Complete installation, CLI, scheme & CMake integration guide
│   ├── MAINTAINER_SPEC.md                   # Formal 1-bpp typography & rasterization specification
│   └── audits/                              # Audit Reports
├── scripts/                                 # Self-contained Windows (.bat) workflow directories:
│   ├── full-audit-build-distro/             #   2. All fonts & icons (12-40pt) master audit distribution bundle
│   ├── h1os-build-distro/                   #   3. H1OS & humid1-os schemes (h1os_full & h1os_lite) + distro builder
│   └── example-build-distro/                #   4. General-purpose embedded project example workflow
├── assets/                                  # Immutable upstream raw font & icon source archives/trees
│   ├── font_assets/                         #   - IBM Plex Variable TTFs + terminus-font-4.49.1.tar.gz
│   └── icon_assets/                         #   - FA v7.2.0, Lucide v1.16.0, Phosphor v2.1.0, Tabler v3.41.1
├── tools/
│   ├── fonts/
│   │   ├── build_static_ttf_assets.py       # Raw assets -> build/static_ttfs/*.ttf + build/metadata/*.json
│   │   ├── humid1_generate_1bpp.py          # Master 4-workflow 1-bpp studio (gen-assets, patch, check, build)
│   │   ├── humid1_fw_emit.py                # Portable zero-dependency CMake firmware emitter (< 0.15s)
│   │   └── schemes/                         # 16 curated general-purpose declarative JSON font schemes
│   └── agent/                               # Agent-First deterministic inspection suite (zero guessing!)
│       ├── tools/                           #   - char_info.py, string_info.py, icon_search.py, font_catalog_info.py
│       ├── skills/                          #   - Concise SKILL.md definitions for AI coding agents
│       └── rules/                           #   - AGENT_TYPOGRAPHY_RULES.md
├── build/                                   # [Gitignored] All generated static_ttfs, metadata, ascii_patches, PNGs
└── dist/                                    # [Gitignored] Self-contained firmware distribution bundles
```

---

## 3. Quick Start

### A. One-Click Windows Batch Workflows (`scripts/*`)
Double-click or run `99_run_full_pipeline.bat` inside any of the 4 workflow folders:
- **General Example Project**: `scripts\example-build-distro\99_run_full_pipeline.bat` -> outputs to `build\example\` and `dist\example_distro\`
- **Full 12–40pt Master Audit (Dev)**: `scripts\full-audit-build-dev\99_run_full_pipeline.bat` -> outputs to `build\audit_dev\` and `dist\audit_dev_distro\`
- **Full 12–40pt Master Audit (Distro)**: `scripts\full-audit-build-distro\99_run_full_pipeline.bat` -> outputs to `build\audit\` and `dist\audit_distro\`
- **H1OS / `humid1-os` Deployment**: `scripts\h1os-build-distro\99_run_full_pipeline.bat` -> outputs to `build\h1os\` and `dist\h1os_distro\`

### B. Command-Line Usage (Cross-Platform Python 3)
```bash
# 1. Install host Python dependencies
pip install "fonttools>=4.40.0" "Pillow>=10.0.0" "freetype-py>=2.4.0"

# 2. Synthesize all 88 static .ttf files into build/static_ttfs/ and catalogs into build/metadata/
python tools/fonts/build_static_ttf_assets.py --verify

# 3. Build 1-bpp C/H fonts, BDFs, CSVs, and Strike Vault using any general scheme
python tools/fonts/humid1_generate_1bpp.py --workflow build \
  --scheme tools/fonts/schemes/humid1_reference.scheme.json \
  --out-dir build/humid1 --dist-dir dist/humid1_distro

# 4. Query exact glyph/string metrics & search icons via the Agent-First tools
python tools/agent/tools/char_info.py --strike humid1_icon_phosphor_fill_20 --char alarm
python tools/agent/tools/string_info.py --strike humid1_font_plex_sans_normal_14 --text "Vapor Pressure" --right-text "42.8 hPa" --right-strike humid1_font_plex_mono_bold_14
python tools/agent/tools/icon_search.py --query thermometer
```

---

## 4. Documentation Index

- **[Complete How-To Guide (`docs/HOW_TO_GUIDE.md`)](docs/HOW_TO_GUIDE.md)** — Step-by-step installation, CLI reference, 16 schemes guide, custom ASCII patching, and CMake integration.
- **[Maintainer & Architecture Specification (`docs/MAINTAINER_SPEC.md`)](docs/MAINTAINER_SPEC.md)** — Formal 1-bpp rasterization math, Terminus BDF-to-TTF synthesis, and PUA icon catalog architecture.
- **[Formal v1.0.12 Engineering & Audit Report (`docs/audits/HUMIDITRON_AUDIT_REPORT_v1.0.12.md`)](docs/audits/HUMIDITRON_AUDIT_REPORT_v1.0.12.md)** — Root-cause analysis of the Phosphor Fill `U+0069_i.txt` bug, repository general-purpose refactoring, Terminus integration, and Agent-First tooling verification.
- **[Changelog (`CHANGELOG.md`)](CHANGELOG.md)** — Full version history through `v1.0.12`.


## Authoritative Script Execution Order (`00`–`08` & `99`)

Each workflow folder (`scripts/h1os-build-distro/`, `scripts/example-build-distro/`, and `scripts/full-audit-build-distro/`) provides numbered Windows `.bat` launchers designed around an **ASCII-Patch-Centric Iterative Tuning Loop**:

```text
  [00_setup_env.bat]             (One-time Python dependency installation: fonttools, Pillow, freetype-py, numpy, opencv-python)
          │
          ▼
  [01_build_static_ttfs.bat]     (Instantiate 88 static .ttf files -> build/static_ttfs/ + JSON catalogs -> build/metadata/)
          │
          ▼
  [04_dump_ascii_patches.bat]    (Dump baseline 1-BPP strikes -> build/<target>/ascii_patches/<symbol>/U+XXXX_<name>.txt)
          │
          ▼
  [08_iterative_auto_repair.bat] (Run 8-Method HQ Typographic Tournament on ascii_patches/ -> rewrite tuned .txt files
          │                       with `patched: 1` + render Before/After sheets in build/<target>/inspect_repairs/)
          ▼
  [05_apply_ascii_patches.bat]   (Compile all modified/tuned .txt files from ascii_patches/ -> root font_icon_epd_patches.json)
          │
          ▼
  [02_build_fonts.bat]           (Compile LVGL .c/.h modules, BDFs, Strike Vault & total_disk_size.txt with patches applied)
          │
          ▼
  [03_visual_check_pngs.bat]     (Render inspect_pages/*.png [with green PATCHED: N/Total banner] & inspect_chars/*/*.png)
          │
          ▼
  [07_package_distro.bat]        (Package drop-in firmware bundle -> dist/<target>_distro/)
```

### How to Run (Two Supported Workflows)

1. **Automated One-Click Full Pipeline (`99_run_full_pipeline.bat`)**:
   Double-click or run `99_run_full_pipeline.bat`. It automatically runs `01 -> 04 -> 08 -> 05 -> 02 -> 03 -> 07` in sequence so your `.c`/`.h` files, `font_icon_epd_patches.json`, and `inspect_pages/*.png` banners immediately include all tournament-repaired glyphs.
2. **Manual Iterative Tuning & Hand-Patching Loop (`04 -> 08 -> 05 -> 02 -> 03`)**:
   - Run `04_dump_ascii_patches.bat` to populate baseline `.txt` glyph grids in `build\<target>\ascii_patches\`.
   - Run `08_iterative_auto_repair.bat` to run the 8-method OpenCV/HQ-Master tournament (`tools\fonts\humid1_bilevel_tuner.py`). This rewrites improved `.txt` files in `build\<target>\ascii_patches\` with `patched: 1`, generates Before/After visual comparison sheets in `build\<target>\inspect_repairs\*_repair.png`, and updates `font_icon_epd_patches.json`.
   - *(Optional)* Open any `build\<target>\ascii_patches\<symbol>\U+XXXX_<name>.txt` in a text editor, tweak `#` / `.` pixels on the 1:1 spaced canvas, and run `05_apply_ascii_patches.bat` to compile your manual edits into `font_icon_epd_patches.json`.
   - Run `02_build_fonts.bat` followed by `03_visual_check_pngs.bat` to rebuild the `.c`/`.h` font modules and inspect the updated PNG sheets (which display `PATCHED OVERRIDES ACTIVE: N / Total GLYPHS` in the top banner and highlight every patched glyph cell in emerald green).

