# `epd-font` (`v0.0.6`) — Repository Maintainer & Engineering Specification

**Repository:** [Humidyne-Labs/epd-font](https://github.com/Humidyne-Labs/epd-font)  
**Target Firmware OS:** [Humidyne-Labs/H1OS](https://github.com/Humidyne-Labs/H1OS) & `humid1-os` (ESP32-S3 / SSD1681 200×200 188-DPI Bilevel EPD)  
**Specification Revision:** `v0.0.6`

---

## 1. Repository Architecture & Two-Tier Separation of Concerns

To keep firmware repositories (`H1OS`, `humid1-os`) fast, portable, and free of native C/Python host dependencies (`libfreetype6`, `fonttools`, `Pillow`, `Node.js / npx`), `epd-font` separates **Foundry Authoring** from **Firmware Build-Time Emission**:

```text
┌────────────────────────────────────────────────────────────────────────────┐
│ TIER 1: `epd-font` REPOSITORY (Host Foundry & Visual QA Studio)            │
│                                                                            │
│  [Raw Assets: Variable TTFs + FA7 OTFs + Lucide/Phosphor/Tabler TTFs]      │
│         │                                                                  │
│         ▼  (Script 1: build_static_ttf_assets.py)                          │
│  [assets/static_ttfs/*.ttf (54 Pure TTFs) + metadata/*_catalog.json]       │
│         │                                                                  │
│         ▼  (Script 2: generate_plex_1bpp.py + plex_epd_patches.json)       │
│  [build/inspect_pages/*.png + build/inspect_chars/*.png + build/fonts/*.c] │
│         │                                                                  │
│         ▼  Exports Pre-Rasterized, Patch-Baked Strike Vault                │
│  [dist/plex_epd_vault.json.gz (~295 KB)]                                   │
└───────────────────────────────────────┬────────────────────────────────────┘
                                        │ (Packaged via 07_package_h1os_deployment.bat)
                                        ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ TIER 2: `H1OS` FIRMWARE REPOSITORY (`components/h1os/tools/fonts/`)        │
│                                                                            │
│  [plex_fw_emit.py (Pure Python Stdlib) + h1os_epd_scheme.json + Vault]     │
│         │                                                                  │
│         ▼  (Executed by CMake `add_custom_command` in < 0.15s)             │
│  [${CMAKE_CURRENT_BINARY_DIR}/generated_fonts/plex_*.c + h1os_fonts.h]     │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. FreeType 2 Bilevel 1-BPP Rasterization Specification

### 2.1 Root Causes of 1-BPP Rendering Degradation & Engine Solution

1. **Native 1-Bit Scanline Conversion (`FT_LOAD_TARGET_MONO | FT_LOAD_MONOCHROME`)**:
   - In FreeType 2 (`<freetype/freetype.h>`), `FT_RENDER_MODE_MONO` is enum value `2`, so `FT_LOAD_TARGET_MONO = (2 & 15) << 16 = 0x20000`, paired with `FT_LOAD_MONOCHROME = 1 << 12 = 0x1000`.
   - Unlike 8-bit grayscale thresholding (`FT_LOAD_TARGET_NORMAL` sliced at `>= 128`), `FT_LOAD_TARGET_MONO | FT_LOAD_MONOCHROME` invokes FreeType's dedicated 1-bit monochrome scanline converter (`ftraster.c`) with non-overlapping dropout control (`FT_PIXEL_MODE_MONO`), preventing half-pixel stems from randomly doubling into `2 px` blobs or dropping out.
2. **Symmetric Monochrome Autohinting (`FT_LOAD_FORCE_AUTOHINT`)**:
   - Upstream [IBM Plex](https://github.com/IBM/plex) TrueType bytecode (`fpgm`/`prep`/`cvt `) is tuned for horizontal RGB ClearType sub-pixels (`gasp` flag `0x000A`), which snaps left and right vertical stems asymmetrically on a 1-bit grid (`U`, `N`, `M`, `H`).
   - Combining `FT_LOAD_RENDER | FT_LOAD_FORCE_AUTOHINT | FT_LOAD_TARGET_MONO | FT_LOAD_MONOCHROME` (`0x21024`) engages FreeType's symmetric stem-width normalizer prior to 1-bit scanline conversion.
3. **1:2 Stem Weight Hierarchy (`Regular 400` vs. `Bold 700`)**:
   - Under `FT_LOAD_TARGET_MONO`, `Regular (wght=400)` renders with symmetric `1.0 px` stems and wide-open `4–5 px` counters across `12–16 px`, whereas `Bold (wght=700)` renders with symmetric `2.0 px` stems—providing an unmistakable 2:1 visual hierarchy on reflective e-paper without crowding internal counters.

### 2.2 Sub-Family Safe Pixel Size Floors (188.3 DPI SSD1681 Panel)

| Sub-Family                                                     | Recommended Floor | Hard Minimum | Optical Behavior Below Floor                                     |
|:-------------------------------------------------------------- |:----------------- |:------------ |:---------------------------------------------------------------- |
| **IBM Plex Sans (`sans`)**                                     | `12 px`           | `10 px`      | `e`, `a`, `s`, `@` bowls pinch below `12 px`                     |
| **IBM Plex Mono (`mono`)**                                     | `12 px`           | `10 px`      | `%`, `#`, `@` inner counters merge below `12 px`                 |
| **IBM Plex Sans Condensed (`cond`)**                           | `14 px`           | `12 px`      | `85%` width narrows horizontal counters (`a`, `e`, `8`)          |
| **IBM Plex Serif (`serif`)**                                   | `18 px`           | `16 px`      | High-contrast bracketed serifs require `>= 16 px`                |
| **IBM Plex Math (`math`)**                                     | `16 px`           | `14 px`      | Multi-bar operators (`∑`, `√`, `≈`, `≤`, `≥`) require `>= 16 px` |
| **Modular Icons (`icon_fa7`, `lucide`, `phosphor`, `tabler`)** | `14 px`           | `12 px`      | Multi-stroke 24×24 grid icons resolve cleanly at `14–32 px`      |

---

## 3. Raw-to-Static TrueType (`.ttf`) Conversion Pipelines (`build_static_ttf_assets.py`)

1. **IBM Plex Variable TTF Instantiation (`41` `.ttf` files)**:
   - Uses `fontTools.varLib.instancer.instantiateVariableFont()` to pin `wght` (`100, 200, 300, 400, 450, 500, 600, 700`) and `wdth` (`100.0` for Sans, `85.0` for Condensed) from the upstream Variable TTFs in `assets/font_assets/ibm-plex-font/`.
   - Injects Unicode `cmap` aliases (`U+0394` `Delta`, `U+03A9` `Omega`, `U+03BC` `mu`) into all `IBMPlexMono` cuts.
2. **Font Awesome v7.0.0 CFF `.otf` → Quadratic `.ttf` Conversion (`3` `.ttf` files)**:
   - Converts PostScript cubic Bézier outlines (`CFF ` table) in `Font Awesome 7 Free-Solid-900.otf`, `Free-Regular-400.otf`, and `Brands-Regular-400.otf` into TrueType quadratic B-splines (`glyf` + `loca` tables, `sfntVersion = \x00\x01\x00\x00`) via `Cu2QuPen(max_err=1.0)` and `TTGlyphPen`.
3. **Phosphor v2.1.0 `post` Sanitization & Self-Describing Glyph Naming (`5` `.ttf` files)**:
   - Rebuilds the TrueType `post` table (`formatType = 2.0`) to eliminate the 2 trailing padding bytes in upstream `Phosphor*.ttf` files and embeds all 1,512 semantic icon names from `selection.json` directly into `glyf`, `hmtx`, `cmap`, and `post`.

---

## 4. Git Hygiene (`.gitignore`), Versioning (`VERSION.json`) & License Policy

### 4.1 What Is Tracked in Git vs. Ignored (`.gitignore`)

- **Tracked in Git**:
  - `assets/font_assets/` & `assets/icon_assets/` (upstream raw sources, licenses, and metadata)
  - `assets/static_ttfs/` (standardized `.ttf` binaries, `licenses/`, and `metadata/*_catalog.json`)
  - `tools/fonts/` (`build_static_ttf_assets.py`, `generate_plex_1bpp.py`, `plex_fw_emit.py`, `plex_epd_patches.json`, `schemes/*.json`, `ascii_patches/`)
  - `scripts/*.bat` (Windows automation scripts)
  - `dist/plex_epd_vault.json.gz` & `dist/h1os_deployment/`
  - `README.md`, `CHANGELOG.md`, `VERSION.json`, `LICENSES/`, `docs/HOW_TO_GUIDE.md`, `docs/MAINTAINER_SPEC.md`
- **Ignored in `.gitignore`**:
  - `.venv/`, `venv/`, `__pycache__/`, `*.pyc`
  - `build/`, `build_icons/` (ephemeral build outputs, BDFs, CSVs, and hundreds of MBs of `inspect_pages/` and `inspect_chars/` PNGs generated on demand by `02_build_h1os_fonts.bat` and `03_visual_check_pngs.bat`).

### 4.2 License Compliance & Redistribution Policy

Every generated distribution (`build/fonts/licenses/`, `assets/static_ttfs/licenses/`, `LICENSES/`, and `h1os_deployment.zip`) automatically bundles the exact upstream license texts required for binary and source redistribution:

- **Toolchain Scripts (`*.py`, `*.bat`, `CMakeLists.txt`)**: MIT License (`LICENSES`)
- **IBM Plex Sans, Condensed, Mono, Serif, Math**: SIL Open Font License 1.1 (`LICENSES/IBMPlex_*_OFL.txt`)
- **Font Awesome Free v7.0.0**: CC BY 4.0 (Icons) / SIL OFL 1.1 (Fonts) (`LICENSES/FontAwesome7_LICENSE.txt`)
- **Lucide Icons v1.67.0**: ISC License (`LICENSES/Lucide_ISC_LICENSE.txt`)
- **Phosphor Icons v2.1.0**: MIT License (`LICENSES/Phosphor_MIT_LICENSE.txt`)
- **Tabler Icons v3.50.0**: MIT License (`LICENSES/Tabler_MIT_LICENSE.txt`)
