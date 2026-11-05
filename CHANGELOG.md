# Changelog — `epd-font` (Humidyne Labs 1-BPP Typography Foundry)

All notable changes to the `epd-font` repository and `H1OS` font generation pipeline are documented in this file.

## [v1.0.13] — 2026-11-04

### Fixed
- **External Font Directory Discovery in `humid1_font_eval.py` & `02_run_font_eval.bat`**:
  - Fixed `discover_candidate_fonts()` in `tools/fonts/humid1_font_eval.py` so pointing `--src-dir` at an external font directory (such as the 700MB+ `eval_fonts` collection with 400+ `.ttf`, `.otf`, and `.ttc` TrueType Collection files) recursively discovers and evaluates all Latin fonts in parallel across all CPU cores (`ProcessPoolExecutor`), instead of checking only for hardcoded `IBMPlex*` filenames.
- **Eliminated Valley Clogging on `'W'`, `'w'`, `'M'`, `'m'`, `'N'`, `'X'`, `'s'` (`humid1_bilevel_tuner.py`)**:
  - Enforced the **Multi-Stroke Pigeonhole Law** (`k_runs * min_stem + (k_runs - 1) <= box_w`), **Open-Valley Scanline Run-Count Invariance (`compute_open_valley_stats`)**, and the **Render -> 8x Upscale -> HQ Master Confidence & Valley-Occlusion Sanity Gate (`compute_upscaled_hq_metrics`)**, mathematically preventing open V-valleys in `'W'`/`'w'`/`'M'` from ever being bridged into a solid black mass.
- **Eliminated Stale Legacy Patch Accumulation & Over-Correction on `'A'`, `'B'`, `'f'`, `'g'`, `'s'`, `')'`**:
  - Fixed `build_patches_json_from_ascii_root()` in `tools/fonts/humid1_ascii_patches.py` so each strike dictionary in `font_icon_epd_patches.json` is replaced cleanly rather than merged via `.update()` onto stale `v1.0.9–v1.0.11` overrides.
  - Added the **"Do No Harm" Conservative Surgical Trigger Gate**, leaving already-thick `Bold` / `ExtraBold (800)` glyphs and high-confidence `Medium (500)` glyphs (`HQConf >= 72%`) 100% untouched (`M0_verified`), reducing total compiled patches across all 63 H1OS strikes from `1,816` down to **`651` surgical overrides**.

### Added
- **Pre-Tune (`RAW`) vs. Post-Tune (`TUNED`) Traceability & Per-Font PNG Evaluation Sheets (`build/font_eval/sheets/*_eval.png`)**:
  - `humid1_font_eval.py` now records and renders both untouched FreeType (`PRE-TUNE / RAW`) and tournament-repaired (`POST-TUNE / TUNED`) metrics (`HQ Confidence %`, `HQ Diff %`, `>=2px Stem %`, `Counter %`, and `Tuning Burden %`) across all sizes.
  - Emits a dedicated visual inspection PNG sheet per font (`build/font_eval/sheets/<font_stem>_eval.png`) with 1:1 specimen strings and 2x-zoomed critical glyph strips (`W w M m A B C f g r s $ ( ) [ ] 0 8`), plus `build/font_eval/font_eval_report.csv`, `.md`, `.json`, and `font_eval_comparison_sheet.png`.

## [v1.0.12] — 2026-11-04

### Fixed
- **Root `2px` Stray File Bug (`08_iterative_auto_repair.bat`)**: Removed the stray `2px` file from the repository root and replaced unescaped `>=2px` inside `echo` statements with `2px+` across `scripts/h1os-build-distro/08_iterative_auto_repair.bat`, `scripts/example-build-distro/08_iterative_auto_repair.bat`, and `scripts/full-audit-build-distro/08_iterative_auto_repair.bat` (Windows `cmd.exe` parsed `>=2px` as stdout redirection `> 2px`).
- **Paired Delimiter & Mirror Glyph Asymmetry (`(`, `)`, `[`, `]`, `{`, `}`, `<`, `>`, `/`, `\`, Arrows)**:
  - Replaced the asymmetric `cv2.resize(..., INTER_NEAREST)` `base_cand_iou >= 0.62` gate in `humid1_bilevel_tuner.py` with a **Symmetric Dilated-Skeleton Containment Gate** (`Precision >= 0.85`, `Recall >= 0.84`) so `1px -> 2px` curve thickenings on right-heavy `)`, `]`, `}` are never rejected.
  - Added **Bilateral Mirror-Pair Synchronization (`synchronize_mirror_glyph_pairs()`)** across all upright and italic strikes so `(` <-> `)`, `[` <-> `]`, `{` <-> `}`, `<` <-> `>`, `«` <-> `»`, `‹` <-> `›`, `≤` <-> `≥`, `/` <-> `\`, `←` <-> `→`, and `↑` <-> `↓` are 100% symmetric in dimensions, stem thickness, and pixel silhouette.
- **`$` (`U+0024`) Central Vertical Spine & `1px` Vertical Bars (`|`, `!`)**:
  - Added **Method M8 (`synth_m8_central_spine_expansion`)** to duplicate `1px` interior vertical spines (`c = w // 2`) in `$`, `+`, `±`, `¢`, `¥`, `Φ`, `Ψ` to `2px` (`##.##.##`) while aligning `1px` top/bottom spine tips and keeping both internal counters open (`B1 = 2`).
  - Enabled `w0 == 1` vertical bar auto-flooring (`|` `U+007C` `1x16 -> 2x16`, `!` `U+0021` `1x12 -> 2x12`) and made `_apply_counter_punch()` non-destructive when internal counters are already open (`open_px > 0`).

### Added
- **Anisotropic `ExtraBold (wght=800)` Static TTF Synthesis & 3-Tier Weight Hierarchy**:
  - Upgraded `tools/fonts/build_static_ttf_assets.py` (now generating **88 static `.ttf` files**) to synthesize `IBMPlexSans-ExtraBold.ttf`, `IBMPlexSans-ExtraBoldItalic.ttf`, `IBMPlexSansCondensed-ExtraBold.ttf`, `IBMPlexSansCondensed-ExtraBoldItalic.ttf`, `IBMPlexMono-ExtraBold.ttf`, `IBMPlexMono-ExtraBoldItalic.ttf`, `IBMPlexSerif-ExtraBold.ttf`, and `IBMPlexSerif-ExtraBoldItalic.ttf` via anisotropic `gvar` positive-weight delta extrapolation (`1.45x` horizontal stem weight, `1.18x` vertical bar weight).
  - Mapped `bold -> ExtraBold (800)` when `normal = Medium (500)`, restoring a `+31.1%` to `+48.3%` ink-mass separation (`mean stem 3.11px` vs `2.26px` at `16px`) between `normal`, `bold`, and `italic`.
- **Multi-Font & Weight Tournament Evaluator (`tools/fonts/humid1_font_eval.py` & `scripts/font-eval-suite/01_run_font_eval.bat`)**:
  - Benchmarks candidate typefaces and weights across `10px–20px`, estimates raw vs. tournament-tuned pixel size floors, writes `docs/audits/FONT_EVAL_BENCHMARK_v1.0.12.md`, and renders `build/font_eval/font_eval_comparison_sheet.png`.
- **Modularized Foundry Architecture (`tools/fonts/`)**:
  - Extracted `humid1_ft_raster.py`, `humid1_ascii_patches.py`, `humid1_visual_check.py`, and `humid1_lvgl_bdf_export.py` from `humid1_generate_1bpp.py`, reducing `humid1_generate_1bpp.py` from `4,309` lines to `1,426` lines while preserving 100% CLI and import compatibility.

## [v1.0.11] — 2026-11-04
### Added
- **8-Method Iterative Typographic Correction, Scoring & Evaluation Engine (`tools/fonts/humid1_bilevel_tuner.py`, `SPEC-TYPO-MATH-1BPP-001`)**:
  - Evaluates 8 distinct mathematical synthesis & repair methods per glyph (`M0_untouched`, `M1_phase` sub-pixel phase/threshold sweep, `M2_line_tracer` medial-axis centerline + asymmetric $\begin{bmatrix}1 & 1\end{bmatrix}$ stroke kernel, `M3_sdf` signed distance field zero-level-set perturbation, `M4_hysteresis_inktrap` dual-threshold hysteresis + $\text{LoG}$ acute ink-trap carving, `M5_collinear` whole-stem collinear dilation + Jenson-Garamond counter-punch, `M6_diagonal_rectified` rational slant rectifier, and `M7_mumford_shah_clean` total-variation spur/notch cleaner).
  - Scores every candidate out of `100.0` points against both an **$8\times$ HQ Continuous Master Reference ($U_{\text{HQ}}$)** and a **Smallest-Strike ($12\text{px}$) Nth-Factor Upscale Reference ($U_{\text{base}\times N}$)** with hard gates on Euler-Poincaré Betti numbers ($B_0, B_1$), HQ Structural IOU ($\ge 0.66$), and zero skin tags / zero notches.
- **Prominent `PATCHED OVERRIDES ACTIVE: N / Total GLYPHS` Banner Badge in Page Check PNGs (`03_visual_check_pngs.bat`)**:
  - Every `inspect_pages/<symbol>.png` sheet now displays `PATCHED: N/Total` in the title bar and an emerald-green status pill in the top-right corner alongside green-bordered patched glyph cells.

### Fixed
- **Eliminated 1px "Skin Tags" & Vertical Stem Step Notches (`sans_italic_12` `'M'`, `serif_normal_18` `'N'`, `terminus_normal_12` `'$'`)**:
  - Added `detect_skin_tags_and_notches()` and `clean_skin_tags_and_notches()` enforcing Mumford-Shah Total-Variation boundary smoothness and strict Euler $B_0/B_1$ conservation, and excluded hand-drawn pixel fonts (`terminus`) from morphological auto-dilation.
- **Unified ASCII-Centric Repair & Patch Workflow (`01 -> 04 -> 08 -> 05 -> 02 -> 03 -> 07`)**:
  - `08_iterative_auto_repair.bat` now writes tuned glyphs directly into `build/<target>/ascii_patches/<symbol>/U+XXXX.txt` with `patched: 1` (preserving baseline `orig_signature`) and compiles all **1,818 verified patches** into `font_icon_epd_patches.json` so running `04 -> 08 -> 05 -> 02 -> 03` (or `99_run_full_pipeline.bat`) immediately reflects all patches in the `.c` files and PNG banners.
  - Updated `docs/HOW_TO_GUIDE.md`, `README.md`, `scripts/README.md`, and `docs/MAINTAINER_SPEC.md` with complete workflow diagrams and step-by-step instructions for `08_iterative_auto_repair.bat`.

## [v1.0.10] — 2026-11-04
### Added
- **Closed-Loop Iterative Bi-Level Font & Icon Auto-Repair Engine (`tools/fonts/humid1_bilevel_tuner.py` & `--workflow repair`)**:
  - Added 4 deterministic OpenCV/NumPy repair engines (`hybrid`, `autofloor`, `downscale`, `contour`) enforcing a `>= 2px` minimum stem floor (`--min-stem 2`) with collinear outward stem dilation, exterior flood-fill counter protection, hit-or-miss acute corner thinning, and a strict hole-count non-degradation guard.
  - Added `08_iterative_auto_repair.bat` across `scripts/h1os-build-distro/`, `scripts/example-build-distro/`, and `scripts/full-audit-build-distro/`, generating visual Before/After repair sheets in `<out-dir>/inspect_repairs/*_repair.png`.
- **Complete LVGL `LV_SYMBOL_*` & Font Awesome 7 Brands Merging (`0xF287` USB, `0xF293`/`0xF294` Bluetooth, `0xF8A2` New-Line)**:
  - `rasterize_font_strike()` now automatically queries `FontAwesome7-Brands.ttf` and `FontAwesome7-Regular.ttf` when rasterizing `icon_fa7` (`solid`) and synthesizes a crisp 1-BPP return-arrow (`↵`) for `0xF8A2` (`LV_SYMBOL_NEW_LINE`), bringing every `humid1_icon_fa7_solid_*` strike (`12, 14, 16, 18, 20, 24, 32 px`) to **87 icons**.
- **Complete Greek, Scientific, Arrow & Math Coverage Across `mono`, `cond`, `serif`, and `terminus`**:
  - Added homoglyph equivalence mapping (`Δ <-> ∆`, `Ω <-> Ω`, `μ <-> µ`, `− <-> -`) and secondary-face fallback (`IBMPlexMath-Regular.ttf` / `IBMPlexSans-Medium.ttf`) centered on monospace cell width so all text strikes contain **131 glyphs** (`ascii_printable` + `latin1_units` + `greek_scientific` + `arrows_punctuation`).

### Changed
- **Upgraded Default `normal_weight` from `400` (`Regular`) to `500` (`Medium`)**:
  - Resolves physical 188.3-DPI SSD1681 e-Paper hairline stem washout by expanding `14px+` vertical stems to solid `2px` (`0.27 mm`) strokes while preserving open counters and passing all 5 H1OS `188px` screen width budgets.

### Fixed
- **Drop-In Ready `H1OS` Header & Include Compatibility (`humid1_fonts.h`, `plex_fonts.h`, `epd_fonts.h`, `h1os_fonts.h`)**:
  - Added `#if __has_include("lvgl.h")` auto-detection, `struct _lv_font_t` forward declaration, and `#ifndef LV_FONT_DECLARE` fallback macro at the top of all 4 headers so inclusion from inside `lv_conf.h` (`LV_FONT_CUSTOM_INCLUDE`) compiles with zero warnings or errors.
  - Fixed duplicate file body concatenation in `humid1_fonts.h` and unified `HUMID1_FONT_*`, `PLEX_FONT_*`, `HUMID1_ICON_*`, and `H1OS_FONT_*` role macros across all headers.
- **Full Multi-Hop LVGL `.fallback` Chaining**:
  - Linked `sans_normal_* -> humid1_icon_fa7_solid_*` and `sans_bold_* -> sans_normal_* -> humid1_icon_fa7_solid_*` (plus `mono`, `cond`, `serif`, `math`, `terminus`) with smart fallback symbol resolution so compound strings (`LV_SYMBOL_TINT " %.1f%%"`) render icons and text from a single font pointer.

## [v1.0.9] — 2026-11-03
### Fixed
- **Specimen Sheet (`humid1_epd_specimen_188dpi.png`) Full Symbol & Icon Resolution**:
  - Updated `render_specimen_sheet()` in `tools/fonts/humid1_generate_1bpp.py` to resolve all `humid1_font_plex_*`, `humid1_font_terminus_*`, and `humid1_icon_*` symbols through `_resolve_sym()` with an automatic PUA icon fallback table (`icon_fb_14`, `icon_fb_20`), restoring the Bottom-Left 6× zoomed micro-glyph boxes (`@`, `%`, `e`, `a`, `0`, `A`), the Bottom-Left 14-icon strip, the Top-Left simulated 200×200 panel icons, and all 17 rows of the Right-Column size ladder.
- **Complete Character & Icon Diagnostic PNG Generation (`inspect_chars/`)**:
  - Changed the default `--inspect-chars-filter` from `"trouble"` (which only exported 29 trouble characters for text fonts like `terminus` and only the first 12 icons for icon strikes like `humid1_icon_tabler_regular_40`) to `"all"` across `tools/fonts/humid1_generate_1bpp.py` and all `03_visual_check_pngs.bat` scripts. Every strike now renders 100% of its character or icon inventory in `inspect_chars/<symbol>/`, matching `ascii_patches/<symbol>/` 1-for-1.
  - Added per-worker in-memory UI font caching (`_UI_FONTS_CACHE`) so rendering full `inspect_chars/` sets across all strikes executes up to 10× faster.

### Added
- **Automated Firmware Flash & Disk Size Report (`total_disk_size.txt`)**:
  - Added `write_total_disk_size_report()` to `tools/fonts/humid1_generate_1bpp.py`, automatically writing `total_disk_size.txt` to `<out-dir>/fonts/total_disk_size.txt`, `<out-dir>/total_disk_size.txt`, and `<dist-dir>/total_disk_size.txt` whenever `.c` font assets are built or exported.
  - Details exact MCU Flash `.rodata` bytes/KB (`bitmap[] + glyphs[] + kern[] + struct`), host `.c`/`.h` source file bytes/KB, MCU Flash partition utilization (`64KB` to `8MB`), per-family subtotals, and per-strike metrics (`Em(px)`, `pt@96`, `pt@DPI`, `LineHt`).
- **Explicit Point Size (`pt@96dpi` and `pt@188dpi`) vs. Pixel Size (`px` / `ppem`) Telemetry**:
  - Added `px_to_pt_96dpi()`, `px_to_pt_target_dpi()`, and `format_px_pt_summary()` helpers and surfaced dual point/pixel sizing (`Em: Npx / Xpt@96dpi / Ypt@188dpi | LineBox: Mpx`) across all diagnostic page sheets, individual character PNGs, CLI logs, and `total_disk_size.txt`.
  - Added `22px` (`16.5pt@96dpi`) across all vector and icon strikes in `scripts/full-audit-distro/full_audit_distro.scheme.json` for a continuous `+2px` (`1.5pt@96dpi`) progression (`12, 14, 16, 18, 20, 22, 24, 28, 32, 36, 40 px`).
- **Native GNU Unifont (`unifont-18.0.01.otf`) Support**:
  - Added `"family": "unifont"` (`exact-mono`, `16px` minimum floor) to `humid1_generate_1bpp.py` and `build_static_ttf_assets.py` for optional range-subsetted Unicode symbol/fallback strikes at `16px` and `32px`.

## [v1.0.8] — 2026-11-03 (22 Native Terminus TTF Strikes, Multi-Core Parallelism, Tabler Filled Fix & `humid1_` Naming Overhaul)

### Fixed
- **Eliminated Terminus 18–40pt Horizontal White Scanline Gaps & 12–14pt Downscaling Blur**:
  - **Root Cause 1**: In `v1.0.7`, only `ter-u16n.bdf` and `ter-u16b.bdf` were converted to `.ttf`, forcing 12–14pt and 18–40pt strikes to scale from the 16px grid instead of using Terminus's native hand-drawn BDF strikes (`ter-u12n/b.bdf`, `ter-u14n/b.bdf`, `ter-u18n/b.bdf`, `ter-u20n/b.bdf`, `ter-u22n/b.bdf`, `ter-u24n/b.bdf`, `ter-u28n/b.bdf`, `ter-u32n/b.bdf`).
  - **Root Cause 2**: Each horizontal pixel row in `convert_bdf_to_quadratic_ttf()` was emitted as a separate rectangle contour (`[y_bot, y_top]`), and `bytecode-mono` omitted `FT_LOAD_NO_HINTING` (`0x2`), causing FreeType's Auto-Hinter (`autofit`) to snap and separate shared horizontal edges between adjacent pixel rows (creating CRT-like horizontal white scanlines across 18, 20, 24, 28, 36, and 40pt).
  - **Fix**:
    1. Hosted all 20 Terminus `.bdf` master files + `OFL.TXT` directly in `assets/font_assets/terminus_v4.49.1/` (removing the redundant `.tar.gz` archive).
    2. Built **24 individual Terminus `.ttf` files** in `build/static_ttfs/`: 22 size-specific Normal & Bold strikes (`Terminus-Normal-{12,14,16,18,20,22,24,28,32,36,40}.ttf` and `Terminus-Bold-{12,14,16,18,20,22,24,28,32,36,40}.ttf`, where `36` is an exact 2× integer strike of `18` and `40` is an exact 2× integer strike of `20`) plus `Terminus-VGA-14.ttf` and `Terminus-VGA-16.ttf`.
    3. Rewrote `convert_bdf_to_quadratic_ttf()` with a **2D connected rectilinear polygon contour tracer** where shared internal horizontal and vertical edges between adjacent ON pixels cancel out 100%, leaving zero internal seam lines.
    4. Added `exact-mono` (`FT_LOAD_RENDER | FT_LOAD_NO_HINTING | FT_LOAD_TARGET_MONO | FT_LOAD_MONOCHROME`) for Terminus in `humid1_generate_1bpp.py` so FreeType never runs its Auto-Hinter on pixel-grid Terminus strikes.
- **Fixed `humid1_icon_tabler_filled_12..40` Producing Empty PNGs and Empty ASCII Folders**:
  - **Root Cause**: `Tabler-Filled.ttf` (`1,054` filled icons at `0xEE80..0xFA6D`) has zero codepoint overlap with `Tabler-Regular.ttf` (`5,203` outline icons at `0xEA02..`). Previously, `tabler` `filled` strikes referenced `tabler_core` (`0xEA02..`), matching 0 glyphs in `Tabler-Filled.ttf`.
  - **Fix**: Added dedicated `icon_tabler_filled` catalog (`build/metadata/tabler_filled_catalog.json`), added `tabler_filled_core` and `tabler_filled_all` character sets, and routed `icon_tabler` `style="filled"` strikes to `icon_tabler_filled`. Verified `humid1_icon_tabler_filled_12..40` now rasterizes all `1,051` filled glyphs, dumps all `1,051` ASCII `.txt` files, and renders 5 paginated Page Check PNGs per strike.
- **Fixed `KeyError: 'plex_mono_bold_14'` in `render_specimen_sheet` on `example.scheme.json`**:
  - Added `_resolve_sym()` fallback resolution in `render_specimen_sheet` and `run_screen_width_audit` so schemes that build a subset of strikes (like `example.scheme.json`) never fail with `KeyError`.
- **Fixed Windows `.bat` `echo` Command-Breaking Strings**:
  - Removed all unescaped `&`, `(`, `)`, `<`, `>`, and `|` characters inside `echo` lines across every `.bat` file in `scripts/*/` so `cmd.exe` never misinterprets words after `&` (such as `'humid1-os'` or `'Char'`) as shell commands.

### Added
- **Multi-Core Host CPU Parallelism (`ProcessPoolExecutor` Across All Cores)**:
  - Upgraded both `build_static_ttf_assets.py` and `humid1_generate_1bpp.py` to execute font instantiation, BDF/OTF-to-TTF synthesis, FreeType strike rasterization, LVGL `.c` emission, ASCII `.txt` dumping, and PNG rendering concurrently across all host CPU cores (`os.cpu_count()`, configurable via `-j` / `--jobs`).
- **Paginated Full-Catalog Icon Audit PNGs (`MAX_GLYPHS_PER_PNG_PAGE = 256`)**:
  - Updated `full_audit_distro.scheme.json` to include **all** valid icons across all 4 vendors (`2,349` FA v7.3.1, `2,043` Lucide, `1,513` Phosphor, `5,203` Tabler Outline, `1,054` Tabler Filled) and updated `render_full_font_inspection_png()` to automatically split large strikes into clean 256-glyph pages (`<symbol>_p01_of_05_U+EE80-U+F788.png`, etc.).

### Changed
- **Unified `humid1_` Naming Convention Across Scripts, Symbols, Vault, Headers & Patch Manifest**:
  - Renamed `generate_plex_1bpp.py` $
ightarrow$ **`tools/fonts/humid1_generate_1bpp.py`**.
  - Renamed `plex_fw_emit.py` $
ightarrow$ **`tools/fonts/humid1_fw_emit.py`**.
  - Renamed `plex_epd_vault.json.gz` $
ightarrow$ **`humid1_epd_vault.json.gz`**.
  - Consolidated patch manifests into a single root-tracked **`font_icon_epd_patches.json`** (removed duplicate `epd_font_patches.json` and `tools/fonts/plex_epd_patches.json`).
  - Standardized all generated strike symbols and folder names under the `humid1_` prefix:
    - IBM Plex fonts: `humid1_font_plex_<family>_<style>_<size>` (e.g., `humid1_font_plex_cond_normal_12`)
    - Terminus fonts: `humid1_font_terminus_<style>_<size>` (e.g., `humid1_font_terminus_normal_40`)
    - Modular icons: `humid1_icon_<vendor>_<style>_<size>` (e.g., `humid1_icon_fa7_regular_12`, `humid1_icon_tabler_filled_36`)
  - Removed redundant `scripts/full-audit-build-dev/` directory in favor of `scripts/full-audit-build-distro/`.
  - Preserved Font Awesome **v7.3.1** (`assets/icon_assets/font_awsome_v7.3.1`).

---

## [v1.0.7] — 2026-11-03 (Audit Remediation, General-Purpose Overhaul, Terminus TTF & Agent-First Suite)

### Fixed
- **Resolved `plex_icon_phosphor_fill_20` Empty `U+0069_i.txt` Bug**:
  - Identified that upstream `Phosphor*.ttf` binaries include 30 empty (`0×0` bounding box, `0` advance width) ASCII ligature anchor glyphs (`0x0020..0x007A`, including `0x0069 'i'`) in their `cmap`, and that missing `assets/icon_assets/phosphor_icons_v2.1.0/metadata/selection.json` caused semantic name lookups in `"icons"` to return empty and fall back to `RANGE_UI_STR` (`0x0020-0x007E`).
  - Restored `metadata/selection.json` across `assets/icon_assets/phosphor_icons_v2.1.0/metadata/` (and all icon asset metadata folders).
  - Updated `sanitize_and_unwrap_ttf()` in `build_static_ttf_assets.py` (`strip_non_pua=True`) to strip all `cp < 0xE000` ASCII ligature anchor stubs from `Phosphor-*.ttf` and embed all `1,513` semantic glyph names (`"alarm"`, `"wifi-high"`, `"battery-full"`, etc.) directly into `Phosphor-Regular.ttf`, `Phosphor-Bold.ttf`, `Phosphor-Fill.ttf`, `Phosphor-Light.ttf`, and `Phosphor-Thin.ttf`.
  - Hardened `load_plan_from_scheme_json()` and `rasterize_font_strike()` in `generate_plex_1bpp.py` so `icon_*` families never fall back to `RANGE_UI_STR` and automatically reject `0×0` non-space stubs.

### Added
- **Terminus Font v4.49.1 Native `.ttf` Synthesis (`Terminus-Regular.ttf` & `Terminus-Bold.ttf`)**:
  - Added `convert_bdf_to_quadratic_ttf()` to `build_static_ttf_assets.py`, automatically extracting `assets/font_assets/terminus-font-4.49.1.tar.gz` (`ter-u16n.bdf` and `ter-u16b.bdf`) and synthesizing standards-compliant `1024-UPEM` quadratic TrueType fonts (`Terminus-Regular.ttf` and `Terminus-Bold.ttf`, `1,356` Unicode glyphs each) plus `build/metadata/terminus_catalog.json` and `Terminus_OFL.txt`.
  - Added `"family": "terminus"` (rendered with crisp unhinted `bytecode-mono` pixel accuracy) and `"ttf_file"` custom font support to `generate_plex_1bpp.py`.
- **Agent-First Tooling Suite (`tools/agent/{tools,skills,rules}`)**:
  - Created `tools/agent/tools/char_info.py` (exact glyph metrics, bounding box, UTF-8 C literal, and 1:1 ASCII bitmap lookup).
  - Created `tools/agent/tools/string_info.py` (exact LVGL `fp4` kerning-aware string pixel width and screen budget clearance calculator).
  - Created `tools/agent/tools/icon_search.py` (keyword search across 12,209 icons in FA7, Lucide, Phosphor, and Tabler with ready-to-paste C macros and JSON snippets).
  - Created `tools/agent/tools/font_catalog_info.py` (complete inventory of static TTFs, catalogs, and schemes).
  - Added 4 concise agent skills (`tools/agent/skills/*/SKILL.md`) and `tools/agent/rules/AGENT_TYPOGRAPHY_RULES.md`.
- **16 Curated General-Purpose Schemes (`tools/fonts/schemes/*.scheme.json`)**:
  - Added 16 domain-tailored schemes covering `humid1_reference`, `ui_balanced`, `minimal_mcu_32kb`, `telemetry_tabular_mono`, `terminus_retro_terminal`, `condensed_narrow_hmi`, `ereader_editorial_serif`, `scientific_math_lab`, `weather_station_epd`, `smart_home_thermostat`, `wearable_watch_200x200`, `industrial_scada_plc`, and 4 standalone icon vendor packs.
- **4 Self-Contained Workflow Batch Directories (`scripts/*`)**:
  - Populated `scripts/full-audit-build-dev/`, `scripts/full-audit-build-distro/`, `scripts/h1os-build-distro/`, and `scripts/example-build-distro/` with dedicated `.scheme.json` files and `00`–`99` `.bat` pipelines.

### Changed
- **Strict `build/` vs `dist/` Isolation & Root Patch Manifest (`epd_font_patches.json`)**:
  - Moved all generated `static_ttfs` (`build/static_ttfs/`), `metadata` (`build/metadata/`), and `ascii_patches` (`build/<workflow>/ascii_patches/`) strictly inside `build/`.
  - Established root-tracked `epd_font_patches.json` so hand-tuned pixel patches remain version-controlled in Git while `build/` and `dist/` remain gitignored.
- **General-Purpose Humiditron / Humidyne Labs Branding & MIT License**:
  - Licensed the `epd-font` repository under the **MIT License** (`LICENSE`).
  - Removed hardcoded `H1OS` / `200x200 SSD1681` assumptions from the Python scripts; made `--dpi`, `--screen-width`, `--screen-height`, and `--safe-margin` configurable via CLI flags and scheme JSONs, and moved `h1os_full.scheme.json` & `h1os_lite.scheme.json` into `scripts/h1os-build-distro/`.

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
  - Added `VERSION.json` tracking the repository version (`0.0.6`) alongside exact upstream versions (`math_v1.1.0`, `mono_v1.0.0`, `sans_v0.2.0`, `serif_v2.0.0`, `font_awsome_v7.3.1`, `lucide_icons_v1.67.0`, `phosphor_icons_v2.1.0`, `tabler_icons_v3.50.0`), a root `.gitignore`, and a consolidated `LICENSES/` directory.

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
  - Standardized raw upstream directory layout under `assets/font_assets/ibm-plex-font/` (`math_v1.1.0`, `mono_v1.0.0`, `sans_v0.2.0`, `serif_v2.0.0`) and `assets/icon_assets/` (`font_awsome_v7.3.1`, `lucide_icons_v1.67.0`, `phosphor_icons_v2.1.0`, `tabler_icons_v3.50.0`).
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
