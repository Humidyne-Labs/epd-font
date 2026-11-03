# Changelog — `epd-font`

All notable changes to the **[Humidyne-Labs/epd-font](https://github.com/Humidyne-Labs/epd-font)** repository and its **[Humidyne-Labs/H1OS](https://github.com/Humidyne-Labs/H1OS)** deployment bundle are documented in this file.

---

## [`v0.0.6`] / [`v1.0.6`] — 2026-11-03

### Added
- **Runnable Windows Batch Script Suite (`scripts/` Directory)**:
  - Added 9 self-contained Windows `.bat` scripts (`00_setup_env.bat`, `01_build_static_ttfs.bat`, `02_build_h1os_fonts.bat`, `03_visual_check_pngs.bat`, `04_dump_ascii_patches.bat`, `05_apply_ascii_patches.bat`, `06_build_icons_catalog.bat`, `07_package_h1os_deployment.bat`, and `99_run_full_pipeline.bat`) so all build, inspection, patching, and packaging workflows execute in one click without manual CLI entry.
- **Dual-Source Searchable JSON Icon Catalogs (`assets/static_ttfs/metadata/`)**:
  - `build_static_ttf_assets.py` now extracts semantic icon names both from upstream metadata JSONs and directly from the `.ttf`/`.otf` `cmap` and `post` tables (baking Phosphor's 1,512 semantic icon names directly into `Phosphor-*.ttf`), generating `fa7_catalog.json` (`2,396` icons), `lucide_catalog.json` (`2,043` icons), `phosphor_catalog.json` (`1,513` icons), `tabler_catalog.json` (`6,257` icons), `unified_icon_names.json` (`12,209` total mappings), and `asset_manifest.json`.
- **Semantic Icon Name Scoping in Scheme JSONs (`"icons": [...]` & `"scope": "all"`)**:
  - Both `generate_plex_1bpp.py` and `plex_fw_emit.py` now allow `character_sets` in `tools/fonts/schemes/*.json` to specify custom icon subsets using plain English icon names (`"icons": ["wifi", "battery-full", "thermometer", "cpu"]`), hex ranges (`"ranges"`), or `"scope": "all"`.
- **Repository Hygiene & Versioning (`VERSION.json`, `.gitignore`, `LICENSES/`)**:
  - Added `VERSION.json` tracking the repository version (`0.0.6`) alongside exact upstream versions (`math_v1.1.0`, `mono_v1.0.0`, `sans_v0.2.0`, `serif_v2.0.0`, `font_awsome_v7.0.0`, `lucide_icons_v1.67.0`, `phosphor_icons_v2.1.0`, `tabler_icons_v3.50.0`), a root `.gitignore`, and a consolidated `LICENSES/` directory.

### Changed
- **Unified Single-Input (`--src-dir`) and Single-Output (`--out-dir`) CLI Architecture**:
  - Audited and simplified `build_static_ttf_assets.py` and `generate_plex_1bpp.py` so only a single `--src-dir` and a single `--out-dir` are needed (eliminating the dual `--plex-dir` / `--icons-src` / `--font-dir` conflict while retaining hidden backward-compatible aliases).
- **Consolidated Documentation into 4 Canonical Files**:
  - Replaced scattered engineering notes with exactly 4 structured documents: `README.md`, `CHANGELOG.md`, `docs/HOW_TO_GUIDE.md`, and `docs/MAINTAINER_SPEC.md`.

### Fixed
- **Fixed Column-0 `#` Pixel Parsing in `parse_ascii_glyph_folder()`**:
  - Fixed a parser condition where a full-canvas ASCII row whose leftmost pixel at `x=0` was `#` (ink ON, such as the bottom-left foot of `'A'`) had its leading spaces stripped before checking `startswith("#")`, causing that row to be skipped as a comment. Only lines starting with `#` at column 0 (`raw_line.startswith("#")`) or `# x:` / `# ±:` headers are now treated as comments.
- **Fixed Empty Metadata JSON Generation When Upstream `metadata/` Folders Were Omitted**:
  - Restored upstream `metadata/` folders under `assets/icon_assets/` and added direct font `cmap` table extraction so JSON catalogs are never empty.

---

## [`v0.0.5`] — 2026-11-03

### Added
- **Repository Restructuring (`epd-font`)**:
  - Standardized raw upstream directory layout under `assets/font_assets/ibm-plex-font/` (`math_v1.1.0`, `mono_v1.0.0`, `sans_v0.2.0`, `serif_v2.0.0`) and `assets/icon_assets/` (`font_awsome_v7.0.0`, `lucide_icons_v1.67.0`, `phosphor_icons_v2.1.0`, `tabler_icons_v3.50.0`).
- **Standalone Host Raw-to-Static Converter (`build_static_ttf_assets.py`)**:
  - Added host script to instantiate 41 static [IBM Plex](https://github.com/IBM/plex) `.ttf` files and convert/normalize 13 icon `.ttf` files (`FontAwesome7-Solid.ttf`, `Regular.ttf`, `Brands.ttf`, `Lucide-Regular.ttf`, `Phosphor-*.ttf`, `Tabler-*.ttf`).

---

## [`v0.0.4`] — 2026-11-02

### Added
- **Modular Multi-Vendor Icon Strikes (`icon_fa7`, `icon_lucide`, `icon_phosphor`, `icon_tabler`)**:
  - Decoupled icon fonts from IBM Plex text strikes (`plex_sans_*`, `plex_cond_*`), compiling each icon vendor as its own standalone `lv_font_t` strike with optional LVGL `.fallback` chaining and reducing text strike ROM size by ~39%.
- **Exact 5-Space Column Alignment in Full-Canvas ASCII Files**:
  - Matched the 5-character `# x: 0 1 2 3 4 5` header prefix with a 5-space row indentation (`"     "`) and removed the default `UNICODE 1:1 SILHOUETTE PREVIEW` block (moved behind opt-in `--unicode-preview`).

---

## [`v0.0.3`] — 2026-11-02

### Added
- **Full-Canvas 1:1 Spaced ASCII Patch Format & Auto-Bounding-Box Parser**:
  - Plotted every glyph across its full vertical (`ASCENDER` to `DESCENDER`) and horizontal (`adv_w`) canvas using 2-character cells (`# `, `. `, `- `) so monospace editors display a true 1:1 aspect ratio and show exact baseline positioning for underscores (`_`), periods (`.`), and degrees (`°`).
- **Two-Level Visual Check PNG Suite (`inspect_pages/` & `inspect_chars/`)**:
  - Added auto-wrapping specimen strings on Page Check PNGs and 18×–24× integer-zoom Char-by-Char Engineering Blueprint PNG cards.
- **Portable Zero-Dependency Firmware Emitter (`plex_fw_emit.py` & `plex_epd_vault.json.gz`)**:
  - Split heavy desktop foundry operations (`generate_plex_1bpp.py`) from fast, zero-dependency CMake firmware emission (`plex_fw_emit.py`).

---

## [`v0.0.2`] — 2026-11-02

### Fixed
- **Native FreeType 1-Bit Monochrome Rasterization (`FT_LOAD_TARGET_MONO`)**:
  - Switched from 8-bit grayscale thresholding to FreeType 2's native 1-bit scanline converter (`FT_LOAD_RENDER | FT_LOAD_FORCE_AUTOHINT | FT_LOAD_TARGET_MONO | FT_LOAD_MONOCHROME`, `0x21024`) and set `Normal` weight to `Regular (400)` (`1 px` stems) vs. `Bold (700)` (`2 px` stems).

---

## [`v0.0.1`] — 2026-11-01

### Added
- Initial prototype of LVGL v9 1-bpp font generator, Adobe BDF 2.1 exporter, and 200×200 SSD1681 screen width audit.
