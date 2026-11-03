# `epd-font` (`v0.0.6`) — Humidyne Labs 1-BPP Bilevel E-Paper Typography & Modular Icon Suite

**Repository:** [Humidyne-Labs/epd-font](https://github.com/Humidyne-Labs/epd-font)  
**Target Firmware OS:** [Humidyne-Labs/H1OS](https://github.com/Humidyne-Labs/H1OS) & `humid1-os` (ESP32-S3 / SSD1681 200×200 188-DPI EPD / LVGL v9)  
**Current Version:** `v0.0.6` (revved from `v0.0.5`)

---

## 1. Overview

`epd-font` is the standalone 1-bit per pixel (`bpp=1`) bilevel font foundry, Full-Canvas 1:1 ASCII pixel-patching studio, visual QA inspector, and zero-dependency firmware font emitter for **Humidyne Labs** embedded e-paper systems.

It unifies **[IBM Plex](https://github.com/IBM/plex)** (`Sans`, `Sans Condensed`, `Mono`, `Serif`, `Math`) with four modular, swappable icon libraries (**Font Awesome v7.0.0**, **Lucide v1.67.0**, **Phosphor v2.1.0**, and **Tabler v3.50.0**), standardized into **54 uncompressed TrueType (`.ttf`) binaries** and compiled into zero-copy LVGL v9 `lv_font_t` C arrays using FreeType 2's native 1-bit monochrome scanline converter (`FT_LOAD_TARGET_MONO | FT_LOAD_MONOCHROME | FT_LOAD_FORCE_AUTOHINT`).

---

## 2. One-Click Windows Execution (`scripts/` Folder)

All common build, inspection, patching, and deployment tasks are pre-configured as double-clickable Windows batch scripts inside `scripts/` (requiring zero manual command-line typing):

| Windows Script (`scripts\`) | Action Performed |
| :--- | :--- |
| **`00_setup_env.bat`** | Creates `.venv` and installs `fonttools`, `Pillow`, and `freetype-py` (bundles `libfreetype.dll` for Windows). |
| **`01_build_static_ttfs.bat`** | Converts raw assets in `assets/` into 54 static `.ttf` files (`assets/static_ttfs/`), generates searchable icon catalogs (`assets/static_ttfs/metadata/*_catalog.json`), collects licenses, and runs the 54-font verification audit. |
| **`02_build_h1os_fonts.bat`** | Compiles `tools/fonts/schemes/h1os_epd_scheme.json` into LVGL v9 `.c`/`.h` files (`build/fonts/`), BDFs (`build/bdf/`), CSV metrics (`build/metrics/`), and exports the Strike Vault (`build/dist/plex_epd_vault.json.gz`). |
| **`03_visual_check_pngs.bat`** | Renders Auto-Wrapped Page Check PNGs (`build/inspect_pages/*.png`), 18×–24× Char-by-Char Blueprint PNGs (`build/inspect_chars/<strike>/*.png`), the 188-DPI Specimen PNG, and runs the 200×200 SSD1681 screen width audit. |
| **`04_dump_ascii_patches.bat`** | Dumps Full-Canvas 1:1 Spaced ASCII `.txt` glyph files into `tools/fonts/ascii_patches/<strike>/U+XXXX_<name>.txt` for pixel editing in Notepad++ or VS Code. |
| **`05_apply_ascii_patches.bat`** | Compiles modified ASCII `.txt` files from `tools/fonts/ascii_patches/` into `tools/fonts/plex_epd_patches.json` and rebuilds the C fonts and Strike Vault. |
| **`06_build_icons_catalog.bat`** | Compiles the standalone multi-vendor icon scheme (`tools/fonts/schemes/icons_modular_scheme.json`) into `build_icons/`. |
| **`07_package_h1os_deployment.bat`** | Packages `dist/h1os_deployment/` and `dist/h1os_deployment.zip` ready to drop into [Humidyne-Labs/H1OS](https://github.com/Humidyne-Labs/H1OS). |
| **`99_run_full_pipeline.bat`** | Runs `01` → `04` → `02` → `03` → `07` end-to-end in a single execution. |

---

## 3. Repository Directory Structure

```text
epd-font/
├── .gitignore                              # Git ignore rules for .venv/, build/, __pycache__/
├── VERSION.json                            # Authoritative repo & upstream font version manifest (v0.0.6)
├── README.md                               # Doc 1/4: Project overview & quick-start (this file)
├── CHANGELOG.md                            # Doc 2/4: Dedicated version history (v0.0.1 -> v0.0.6)
├── docs/
│   ├── HOW_TO_GUIDE.md                     # Doc 3/4: Complete install, setup, icon scoping & CLI guide
│   └── MAINTAINER_SPEC.md                  # Doc 4/4: Architecture, FreeType internals & license policy
├── LICENSES/                               # All upstream font/icon licenses + repo Apache-2.0 license
├── scripts/                                # Runnable Windows (.bat) execution & test scripts (00..99)
├── assets/
│   ├── font_assets/ibm-plex-font/          # Raw upstream IBM Plex Variable & Math TTFs + licenses
│   ├── icon_assets/                        # Raw upstream FA7, Lucide, Phosphor, Tabler fonts + metadata
│   └── static_ttfs/                        # Generated 54 static .ttf files, licenses/, and metadata/*.json
├── tools/fonts/
│   ├── build_static_ttf_assets.py          # Tool 1: Raw assets -> Static .ttf files & JSON icon catalogs
│   ├── generate_plex_1bpp.py               # Tool 2: Static .ttf files + Scheme -> C/H, PNGs, ASCII, Vault
│   ├── plex_fw_emit.py                     # Tool 3: Zero-dependency pure-Python C/H emitter for H1OS CMake
│   ├── plex_epd_patches.json               # Compiled optical 1-bpp pixel patch manifest
│   ├── schemes/                            # Declarative JSON build schemes (h1os, icons, basic, full)
│   └── ascii_patches/                      # Human-editable Full-Canvas 1:1 Spaced ASCII .txt glyph folders
├── build/                                  # Unified single output directory created by generate_plex_1bpp.py
│   ├── fonts/                              # Generated LVGL v9 .c files, plex_fonts.h, h1os_fonts.h
│   ├── dist/plex_epd_vault.json.gz         # Pre-rasterized Strike Vault
│   ├── bdf/                                # Adobe BDF 2.1 bitmap strikes
│   ├── metrics/                            # Per-strike CSV character width & kerning tables
│   ├── inspect_pages/                      # Auto-wrapped Page Check PNGs + 188-DPI master specimen
│   └── inspect_chars/                      # 18x-24x Char-by-Char Engineering Blueprint PNG cards
└── dist/
    ├── plex_epd_vault.json.gz              # Latest Strike Vault for downstream firmware
    └── h1os_deployment/                    # Turnkey drop-in tree for Humidyne-Labs/H1OS
```

---

## 4. Upstream Font & Icon Versioning & License Matrix (`VERSION.json`)

| Asset Family | Upstream Version | Raw Source Location | Static `.ttf` Count | License & Attribution File |
| :--- | :--- | :--- | :--- | :--- |
| **IBM Plex Sans & Condensed** | `v0.2.0` (Variable) | `assets/font_assets/ibm-plex-font/sans_v0.2.0/` | 22 `.ttf` cuts (`100..700` + `Italic`, `wdth=100/85`) | SIL Open Font License 1.1 (`LICENSES/IBMPlex_Sans_OFL.txt`) |
| **IBM Plex Mono** | `v1.0.0` (Variable) | `assets/font_assets/ibm-plex-font/mono_v1.0.0/` | 9 `.ttf` cuts (`300..700` + `Italic`) | SIL Open Font License 1.1 (`LICENSES/IBMPlex_Mono_OFL.txt`) |
| **IBM Plex Serif** | `v2.0.0` (Variable) | `assets/font_assets/ibm-plex-font/serif_v2.0.0/` | 9 `.ttf` cuts (`300..700` + `Italic`) | SIL Open Font License 1.1 (`LICENSES/IBMPlex_Serif_OFL.txt`) |
| **IBM Plex Math** | `v1.1.0` (Static) | `assets/font_assets/ibm-plex-font/math_v1.1.0/` | 1 `.ttf` cut (`IBMPlexMath-Regular.ttf`, 4,382 glyphs) | SIL Open Font License 1.1 (`LICENSES/IBMPlex_Math_OFL.txt`) |
| **Font Awesome Free** | `v7.0.0` | `assets/icon_assets/font_awsome_v7.0.0/` | 3 `.ttf` cuts (`Solid`, `Regular`, `Brands`) | CC BY 4.0 / SIL OFL 1.1 (`LICENSES/FontAwesome7_LICENSE.txt`) |
| **Lucide Icons** | `v1.67.0` | `assets/icon_assets/lucide_icons_v1.67.0/` | 1 `.ttf` cut (`Lucide-Regular.ttf`, 2,061 icons) | ISC License (`LICENSES/Lucide_ISC_LICENSE.txt`) |
| **Phosphor Icons** | `v2.1.0` | `assets/icon_assets/phosphor_icons_v2.1.0/` | 5 `.ttf` cuts (`Regular`, `Bold`, `Fill`, `Light`, `Thin`) | MIT License (`LICENSES/Phosphor_MIT_LICENSE.txt`) |
| **Tabler Icons** | `v3.50.0` | `assets/icon_assets/tabler_icons_v3.50.0/` | 4 `.ttf` cuts (`Regular`, `Light300`, `Thin200`, `Filled`) | MIT License (`LICENSES/Tabler_MIT_LICENSE.txt`) |

---

## 5. Documentation Map

- **[`CHANGELOG.md`](CHANGELOG.md)**: Complete version history from `v0.0.1` through `v0.0.5` and `v0.0.6`.
- **[`docs/HOW_TO_GUIDE.md`](docs/HOW_TO_GUIDE.md)**: Step-by-step installation, Windows `.bat` workflow, CLI arguments, how to scope/add custom icons by name in `schemes/*.json`, ASCII pixel patching, and `H1OS` CMake integration.
- **[`docs/MAINTAINER_SPEC.md`](docs/MAINTAINER_SPEC.md)**: Formal engineering specification, FreeType `FT_LOAD_TARGET_MONO` rendering architecture, CFF `.otf` to `.ttf` conversion math, `.gitignore` policy, and license compliance rules.
