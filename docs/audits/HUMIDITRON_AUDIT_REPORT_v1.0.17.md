# Humiditron `epd-font` v1.0.17 — Master Code, Auto-Hinting, Scheme & Typography Audit Report

- **Repository**: [Humidyne-Labs/epd-font](https://github.com/Humidyne-Labs/epd-font) (`v1.0.17`)
- **Target OS**: [Humidyne-Labs/H1OS](https://github.com/Humidyne-Labs/H1OS) (`Waveshare 1.54in V2 EPD SSD1681`, `200×200 px`, `188.3 DPI`, `1-BPP`)
- **Upstream Typefaces**: [IBM Plex](https://github.com/IBM/plex) (`Hinted Static + Variable w100..w800`), [Google Noto](https://github.com/notofonts/latin-greek-cyrillic) (`v2.013 Hinted Static`), [Terminus Font](https://terminus-font.sourceforge.net/) (`v4.49.1 Native Bitmap`)
- **Upstream Icon Suites**: [Font Awesome 7](https://fontawesome.com/) (`v7.3.1`), [Lucide Icons](https://lucide.dev/) (`v1.67.0`), [Phosphor Icons](https://phosphoricons.com/) (`v2.1.0`), [Tabler Icons](https://tabler.io/icons) (`v3.50.0`)

## 1. Executive Summary & What's Fixed in `v1.0.17`

Version **`1.0.17`** ("FontLust Division-of-Labor Triad Edition") resolves the root causes uncovered across the `Noto_03_font_eval.zip` (`190` cuts), `IBMPlex_05_font_eval.zip` (`65` cuts), `Literata_04_font_eval.zip` (`72` cuts), and `epd-font-v1.0.16-fixme.zip` audits:

1. **Unified FreeType 2 Auto-Hinting & Rasterization Engine (`tools/fonts/humid1_ft_raster.py`)**:
   - Fixed a critical discrepancy where `humid1_font_eval.py:1031` passed `raster_mode="autohint_mono"` (underscore) while `humid1_generate_1bpp.py` passed `raster_mode="autohint-mono"` (hyphen). In `v1.0.16`, `"autohint_mono"` fell through `resolve_freetype_flags()` to `FT_LOAD_RENDER | FT_LOAD_FORCE_AUTOHINT | FT_LOAD_TARGET_NORMAL` (Symmetric 8-Bit Auto-Hinter + coverage thresholding), whereas `"autohint-mono"` invoked `FT_LOAD_TARGET_MONO | FT_LOAD_MONOCHROME` (legacy 1-bit B&W dropout scanline converter).
   - Benchmarking proved that Symmetric 8-Bit Auto-Hinting + Coverage Thresholding (`FT_LOAD_FORCE_AUTOHINT | FT_LOAD_TARGET_NORMAL`) improves `16px` 8x HQ IoU confidence by **`+3.6%` on `IBMPlexSans-Medium` (`75.0%` vs `71.5%`)** and **`+5.7%` on `IBMPlexSans-SemiBoldItalic` (`73.3%` vs `67.6%`)** while eliminating 1-bit diagonal scanline spurs. `resolve_freetype_flags()` now normalizes `"autohint-mono"` and `"autohint_mono"` to the same high-confidence engine and exposes `"autohint-1bit"`, `"bytecode-mono"`, and `"bytecode-1bit"` explicitly.
2. **Closed-Loop Bowl-Join Bridge Sealer & Pre-Exit Gate Fix (`tools/fonts/humid1_bilevel_tuner.py`)**:
   - Discovered why single characters (`'q'`, `'b'`, `'a'`, `'8'`) on condensed and serif/italic strikes (`IBMPlexSansCondensed`, `IBMPlexSerif`, `NotoSerif-MediumItalic`) previously reported `95.2%` or `85.7%` counter survival at `16px`: their interior counter cavities were already wide open (`6px–20px` of open white space), but a **1-pixel anti-aliased gap (`"."`) at the bowl-to-stem join** allowed 4-connected exterior background flood-fill (`compute_betti_numbers`) to leak into the bowl (`b1 = 0`).
   - Added **Step 2a (`HQ Coverage Hysteresis Arch Recovery + 1px/2px Bowl-Join Bridge Sealer`)** inside `carve_and_unpinch_counters()`, raising `16px` counter survival to **`100.0%` across 50 of 51 benchmarked foundry cuts** (including `100.0%` across every active `IBM Plex`, `Google Noto`, and `Terminus` triad!).
   - Fixed two additional bugs in `inspect_and_repair_glyph_bitmap()`:
     - `Line 1357`: Fixed an undefined `b1_m0_now` reference (`NameError`) when `--tune-mode off` is invoked.
     - `Lines 1423–1438`: Fixed the pre-exit gate checking `b1_base >= expected_b1` instead of `b1_m0_now >= expected_b1`, which previously caused glyphs already repaired by `carve_and_unpinch_counters()` to fall through into the un-carved `M1..M8` tournament.
3. **Curated Hinted IBM Plex + Hinted Google Noto + Terminus Asset Suite (`assets/font_assets/`)**:
   - Added `assets/font_assets/noto_v2.013/` containing **22 curated Hinted Google Noto `.ttf` masters** (`NotoSans`, `NotoSans-SemiCondensed`, `NotoSans-Condensed`, `NotoSansMono`, `NotoSerif`, `NotoSansMath`) + `char_manifest_noto_v2.013.json`.
   - Added `assets/font_assets/ibm-plex-font/hinted_static/` containing **24 official Hinted IBM Plex static `.ttf` masters** (`Regular w400`, `Medium w500`, `SemiBold w600`, `Bold w700`, and Italics across `Sans`, `Condensed`, `Mono`, and `Serif`) alongside the Variable masters (which synthesize `ExtraBold w800` and `ExtraBoldItalic w800i`) and Hinted `IBMPlexMath-Regular.ttf`.
   - Explicitly excluded `Literata` from `assets/` and all `.scheme.json` files per project direction, replacing `serif` with Hinted **`NotoSerif`** (`Medium w500` + `Black w900` + `MediumItalic w500`).
   - Upgraded `build_static_ttf_assets.py` to build and verify **113 static `.ttf` files (`113 PASSED, 0 FAILED`)** in `build/static_ttfs/`.
4. **Zero-Hole Overhaul Across All 20 `.scheme.json` Files**:
   - Audited all `20` `.scheme.json` files across `scripts/` and `tools/fonts/schemes/`. Fixed **6 broken `default_font` pointers** and **121 unresolved `semantic_roles` macro pointers** (`0` unresolved pointers remain across all 20 schemes).
   - Configured `scripts/h1os-build-distro/h1os_full.scheme.json` (`106 strikes`, `274.9 KB` ROM) and `scripts/h1os-build-distro/h1os_lite.scheme.json` (`47 strikes`, `131.1 KB` ROM) with the **Best-of-the-Best Division of Labor** across **Hinted IBM Plex + Hinted Google Noto + Terminus**.

## 2. Deep Auto-Hinting & FreeType 2 Rasterization Audit

### 2.1 Root Cause #1: The `"autohint_mono"` vs. `"autohint-mono"` Discrepancy

During our line-by-line code audit of `v1.0.16`, we compared how `humid1_font_eval.py` and `humid1_generate_1bpp.py` invoked `rasterize_font_strike()`:
- In `tools/fonts/humid1_font_eval.py:1031`, the evaluator called:
  ```python
  rasterize_font_strike(..., raster_mode="autohint_mono", threshold=128)
  ```
- In `tools/fonts/humid1_generate_1bpp.py:689`, the build orchestrator called:
  ```python
  rasterize_font_strike(..., raster_mode="autohint-mono", threshold=128)
  ```
- Inside `tools/fonts/humid1_ft_raster.py:566` (`resolve_freetype_flags()`), `v1.0.16` checked `if raster_mode == "autohint-mono":` (with a hyphen!). Because `"autohint_mono"` used an underscore, it fell through to the `size_px <= 18` branch (`FT_LOAD_RENDER | FT_LOAD_FORCE_AUTOHINT | FT_LOAD_TARGET_NORMAL`), which renders an **8-bit grayscale grid-fitted bitmap** (`FT_PIXEL_MODE_GRAY`) and thresholds at `>= 128` (`50%` coverage). Meanwhile, `"autohint-mono"` returned `FT_LOAD_RENDER | FT_LOAD_FORCE_AUTOHINT | FT_LOAD_TARGET_MONO | FT_LOAD_MONOCHROME`, which invokes FreeType's legacy **1-bit B&W dropout scanline converter** (`FT_PIXEL_MODE_MONO`).

### 2.2 Root Cause #2: Why `ttfautohint` Bytecode (`bytecode-mono`) Thins `Medium (w500)` Stems in 1-Bit Mode

Both [IBM Plex](https://github.com/IBM/plex) (`Hinted_IBMPlex.zip`) and [Google Noto](https://github.com/notofonts/latin-greek-cyrillic) (`Hinted_Noto.zip`) generate their embedded TrueType bytecode (`fpgm`, `prep`, `cvt ` tables) using `ttfautohint`, which is mathematically parameterized for **8-bit anti-aliased grayscale rendering (`FT_LOAD_TARGET_NORMAL`)**. At `16px` (`1000 UPEM`), a `Medium (w500)` stem (`~108 UPEM = 1.73px`) is grid-fitted by `ttfautohint` to `1.6px` of solid core + `0.4px` of anti-aliased fringe.
- When forced through `FT_LOAD_TARGET_MONO` (`NativeBytecode+TargetMono1Bit`), the 1-bit B&W scanline converter discards the anti-aliased fringe, thinning `IBMPlexSans-Medium` from `2.13px` (`2,507` ink px) down to `2.04px` (`2,098` ink px, `-16.3%` ink loss) and `NotoSans-Medium` from `2.17px` (`2,379` ink px) down to `1.97px` (`2,153` ink px).
- Conversely, **Symmetric 8-Bit Auto-Hinting + Coverage Thresholding (`ForceAutohint+TargetNormal`)** snaps both edges of vertical and horizontal stems symmetrically to pixel boundaries before thresholding at `128`, preserving solid `2.13px–2.17px` stems and `100.0%` raw counters:

| Font File (`16px` Raw Benchmark) | `ForceAutohint + TargetNormal` (`v1.0.17` Default) | `ForceAutohint + TargetMono1Bit` (`v1.0.16` Build) | `NativeBytecode + TargetNormal` (`bytecode-mono`) | `NativeBytecode + TargetMono1Bit` (`bytecode-1bit`) |
| :--- | :--- | :--- | :--- | :--- |
| **`IBMPlexSans-Medium.ttf`** (`w500`) | **`2.13px` stem \| `2,507` ink \| `100.0%` cnt** | `2.13px` stem \| `2,334` ink \| `100.0%` cnt | `2.01px` stem \| `2,044` ink \| `100.0%` cnt | `2.04px` stem \| `2,098` ink \| `100.0%` cnt |
| **`IBMPlexSans-Bold.ttf`** (`w700`) | `2.50px` stem \| `2,874` ink \| `95.2%` cnt | `2.37px` stem \| `2,798` ink \| `100.0%` cnt | **`2.60px` stem \| `2,780` ink \| `100.0%` cnt** | `2.64px` stem \| `2,861` ink \| `100.0%` cnt |
| **`NotoSans-Medium.ttf`** (`w500`) | **`2.17px` stem \| `2,379` ink \| `100.0%` cnt** | `2.16px` stem \| `2,332` ink \| `100.0%` cnt | `1.99px` stem \| `2,132` ink \| `100.0%` cnt | `1.97px` stem \| `2,153` ink \| `100.0%` cnt |
| **`NotoSans-Black.ttf`** (`w900`) | **`3.23px` stem \| `3,360` ink \| `100.0%` cnt** | `3.21px` stem \| `3,358` ink \| `100.0%` cnt | `3.19px` stem \| `3,465` ink \| `100.0%` cnt | `3.13px` stem \| `3,468` ink \| `100.0%` cnt |

### 2.3 Root Cause #3: Why `IBMPlex_05_font_eval.zip` Scored `41.8–76.3` When Tested Standalone

In `IBMPlex_05_font_eval.zip`, the 65 official static cuts from `Hinted_IBMPlex.zip` were evaluated without the synthesized `ExtraBold (w800)` cuts from `build/static_ttfs/`:
1. **Upstream IBM Plex Caps Static Weights at `Bold (w700)`**: Unlike Google Noto (which ships native `ExtraBold w800` and `Black w900` cuts), upstream `Hinted_IBMPlex.zip` only includes weights `100..700` (`Thin` through `Bold`). At `16px`, `IBMPlexSans-Bold.ttf` (`w700`) has a mean stem width of `2.48px` (`2,880` ink px), which is only **`+13.7%` more ink** and **`+0.31px` thicker** than `IBMPlexSans-Medium.ttf` (`w500`, `2.17px`, `2,533` ink px). That lands squarely in the homogeneous "Dead Zone" (`< +25%` ink jump), so the Triad Scorer penalized `w500 + w700` to `41.8`.
2. **Combining Hinted Static (`w400..w700`) + Synthesized `ExtraBold (w800)` Restores `#1` Rank (`91.2`)**: In `v1.0.17`, `build_static_ttf_assets.py` pairs the official Hinted IBM Plex static cuts (`IBMPlexSans-Medium.ttf` `w500`, `IBMPlexSans-SemiBoldItalic.ttf` `w600`) with our anisotropically extrapolated `IBMPlexSans-ExtraBold.ttf` (`w800`, `3.13px` stem, `3,482` ink px = **`+37.7%` Bold ink punch** and **`+0.96px` stem jump**), achieving the **#1 Overall Triad Score (`91.2`)**!

## 3. General Code & Topological Tuner Audit (`tools/fonts/*.py`)

| Module | Issue / Defect Identified in `v1.0.16` | Fix Applied in `v1.0.17` | Status |
| :--- | :--- | :--- | :---: |
| `humid1_ft_raster.py` | `resolve_freetype_flags()` treated `"autohint-mono"` and `"autohint_mono"` differently (`FT_LOAD_TARGET_MONO` vs `FT_LOAD_TARGET_NORMAL`). | Normalized `"_" -> "-"` and unified `"autohint-mono"` to `FT_LOAD_RENDER \| FT_LOAD_FORCE_AUTOHINT \| FT_LOAD_TARGET_NORMAL` (`<=20px`), adding explicit `"autohint-1bit"`, `"bytecode-mono"`, and `"bytecode-1bit"`. | **FIXED** |
| `humid1_ft_raster.py` | `rasterize_font_strike()` only opened secondary fallback faces for `IBMPlex*` and `FontAwesome7*`, leaving `Noto*` strikes without cross-font math/symbol fallback. | Extended secondary fallback face resolution to all `ibmplex*` and `noto*` faces (`NotoSans-Medium`, `NotoSansMath-Regular`, `IBMPlexSans-Medium`, `IBMPlexMath-Regular`). | **FIXED** |
| `humid1_ft_raster.py` | `format_strike_symbol()` lacked explicit rules for `noto_*` and `plex_*` family keys. | Added explicit `noto_sans`, `noto_cond`, `noto_mono`, `noto_serif`, `noto_math` and `plex_*` symbol formatting while preserving `humid1_font_plex_<family>_<role>_<sz>` for core roles. | **FIXED** |
| `humid1_bilevel_tuner.py` | `Line 1357`: `holes_after=b1_m0_now` referenced `b1_m0_now` before assignment when `tune_mode == "off"`. | Changed `holes_after=b1_m0_now` to `holes_after=b1_base` inside the `if tune_mode == "off":` block. | **FIXED** |
| `humid1_bilevel_tuner.py` | `Lines 1423–1438`: Pre-exit checks tested `b1_base >= expected_b1` instead of `b1_m0_now >= expected_b1`, discarding `M0_counter_carved` repairs when `needs_h0` was `False`. | Updated `skip_for_multi_valley`, `skip_for_high_conf`, and the pre-exit condition to check `b1_m0_now >= expected_b1`. | **FIXED** |
| `humid1_bilevel_tuner.py` | `carve_and_unpinch_counters()` only cleared `#` pixels when `b1 < expected_b1`, missing glyphs (`'q'`, `'b'`, `'a'`, `'8'`) whose interior counter was already open but leaked through a 1px/2px gap in the bowl-to-stem join. | Added **Step 2a (`HQ Coverage Hysteresis Arch Recovery + 1px/2px Bowl-Join Bridge Sealer`)**, raising `16px` counter survival to **`100.0%`** across 50/51 foundry cuts. | **FIXED** |
| `humid1_font_eval.py` | `extract_base_family_stem()` stripped everything after the first hyphen unless it was a standard weight name, collapsing `NotoSans-SemiCondensed*` and `NotoSans-Condensed*` into `NotoSans`. | Added width-subfamily regex preservation (`SemiCondensed`, `Condensed`, `ExtraCondensed`) so each width subfamily is scored as its own independent triad. | **FIXED** |
| `build_static_ttf_assets.py` | Only built 91 static `.ttf` files from IBM Plex Variable + Terminus + Icons; did not index `noto_v2.013/` or `ibm-plex-font/hinted_static/`. | Added `NOTO_STATIC_COPY_TABLE` (22 Hinted Noto cuts) and `hinted_static/` prioritization, building and verifying **113 static `.ttf` files**. | **FIXED** |
| `humid1_generate_1bpp.py` | `get_family_roles()` mapped `cond`, `serif`, and `math` to `IBMPlexSansCondensed`, `IBMPlexSerif`, and `IBMPlexMath`, which had `20px+` size floors. | Upgraded `cond` -> `NotoSans-SemiCondensed`, `serif` -> `NotoSerif`, and `math` -> `NotoSansMath` (with `IBMPlexMath` fallback), while retaining `plex_cond`, `plex_serif`, `plex_math` and adding `noto_sans`, `noto_mono`. | **FIXED** |

## 4. Comprehensive Audit of All 20 `.scheme.json` Files

In `v1.0.16`, 6 of the 20 `.scheme.json` files had broken `default_font` pointers (`df_miss=True`), 17 of the 20 had unresolved `semantic_roles` macro pointers (`121` broken macro targets total), and multiple schemes had missing triad styles (`cond` `italic`, `serif` `bold`, `serif` `italic`, `mono` `italic`, `terminus` `bold`) or size holes. All 20 `.scheme.json` files have been upgraded to `schema_version: "1.0.17"` with **`0` unresolved `default_font` or `semantic_roles` pointers**:

| Scheme File Path | `v1.0.16` Strikes / Syms | `v1.0.16` Broken Pointers (`df` / `sr`) | `v1.0.17` Strikes / Syms | `v1.0.17` Broken Pointers | Key Holes Fixed in `v1.0.17` |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `scripts/h1os-build-distro/h1os_full.scheme.json` | `17` / `67` | `0` / `0` | **`23` / `106`** | **`0` / `0`** | Added `noto_sans` triad (`14,16,20`), `cond` `bold` `14,24` + `cond` `italic` (`14..20`), `serif` `bold` & `italic` (`16..24`), `mono` `18,32`, `math` `14,24`, `terminus` `bold` (`12,14,16,20`). |
| `scripts/h1os-build-distro/h1os_lite.scheme.json` | `10` / `36` | `0` / `2` | **`14` / `47`** | **`0` / `0`** | Added `cond` `normal` (`14,16`) & `bold` (`14,16,18`), `mono` `italic` (`14,16`), `sans` `italic` `18`, `terminus` `bold` (`12,16`), `icon_fa7` `12`, and resolved `LUCIDE`/`TABLER` macros. |
| `scripts/full-audit-build-distro/full_audit_distro.scheme.json` | `21` / `226` | `0` / `0` | **`23` / `246`** | **`0` / `0`** | Added full `cond` `italic` (`12..40`) and `serif` `italic` (`16..40`) sweeps across all 11 sizes. |
| `scripts/example-build-distro/example.scheme.json` | `7` / `19` | `0` / `5` | **`9` / `27`** | **`0` / `0`** | Added `sans` `bold` `12`, `sans` `italic` (`14,16,20`), `mono` `bold` (`14,16,20,24`), and resolved all 5 `semantic_roles` pointers. |
| `tools/fonts/schemes/humid1_reference.scheme.json` | `17` / `64` | `0` / `0` | **`23` / `106`** | **`0` / `0`** | Synchronized with `h1os_full.scheme.json` (`106` strikes across Plex + Noto + Terminus + 4 Icon Suites). |
| `tools/fonts/schemes/condensed_narrow_hmi.scheme.json` | `4` / `16` | `1` / `12` | **`6` / `26`** | **`0` / `0`** | Added `cond` `bold` `12`, `cond` `italic` (`14..24`), `mono` `bold` (`14..24`), and fixed `default_font` + 12 `semantic_roles`. |
| `tools/fonts/schemes/ereader_editorial_serif.scheme.json` | `4` / `15` | `0` / `12` | **`5` / `23`** | **`0` / `0`** | Unified `serif` `normal`/`bold`/`italic` across `[16,18,20,24,28,32]`, added `sans` `bold` (`14,16`), and resolved 12 `semantic_roles`. |
| `tools/fonts/schemes/industrial_scada_plc.scheme.json` | `6` / `20` | `1` / `8` | **`7` / `27`** | **`0` / `0`** | Unified `cond` `normal`/`bold` (`14..24`), added `terminus` `bold` (`12,14,16`), and fixed `default_font` + 8 `semantic_roles`. |
| `tools/fonts/schemes/terminus_retro_terminal.scheme.json` | `2` / `16` | `1` / `12` | **`2` / `18`** | **`0` / `0`** | Added missing `22px` strike to `terminus` (`12..32`) and resolved `default_font` + 12 `semantic_roles` to Terminus strikes. |
| `tools/fonts/schemes/ui_balanced.scheme.json` | `4` / `14` | `0` / `7` | **`6` / `22`** | **`0` / `0`** | Added `sans` `bold` `12`, `sans` `italic` (`14,16,20`), `mono` `bold` (`14..24`), and resolved 7 `semantic_roles`. |
| `tools/fonts/schemes/minimal_mcu_32kb.scheme.json` | `4` / `6` | `0` / `8` | **`4` / `6`** | **`0` / `0`** | Resolved all 8 `semantic_roles` pointers to the 6 ultra-compact MCU strikes (`<16 KB` ROM). |
| `tools/fonts/schemes/scientific_math_lab.scheme.json` | `4` / `13` | `0` / `10` | **`4` / `13`** | **`0` / `0`** | Upgraded `math` to Hinted `NotoSansMath` + `IBMPlexMath` fallback and resolved all 10 `semantic_roles`. |
| `tools/fonts/schemes/smart_home_thermostat.scheme.json` | `5` / `16` | `0` / `8` | **`5` / `16`** | **`0` / `0`** | Upgraded to `500/800/600` weights and resolved all 8 `semantic_roles`. |
| `tools/fonts/schemes/telemetry_tabular_mono.scheme.json` | `4` / `16` | `0` / `8` | **`4` / `16`** | **`0` / `0`** | Upgraded to Hinted `IBMPlexMono` (`500/800`) and resolved all 8 `semantic_roles`. |
| `tools/fonts/schemes/wearable_watch_200x200.scheme.json` | `5` / `16` | `1` / `8` | **`5` / `16`** | **`0` / `0`** | Fixed `default_font` (`humid1_font_terminus_normal_14`) and resolved all 8 `semantic_roles`. |
| `tools/fonts/schemes/weather_station_epd.scheme.json` | `5` / `21` | `0` / `5` | **`5` / `21`** | **`0` / `0`** | Upgraded to `500/800` weights and resolved all 5 `semantic_roles`. |
| `tools/fonts/schemes/icon_suite_fontawesome7.scheme.json` | `2` / `13` | `1` / `13` | **`2` / `13`** | **`0` / `0`** | Fixed `default_font` (`humid1_icon_fa7_solid_16`) and resolved all 13 `semantic_roles`. |
| `tools/fonts/schemes/icon_suite_lucide.scheme.json` | `1` / `9` | `1` / `13` | **`1` / `9`** | **`0` / `0`** | Fixed `default_font` (`humid1_icon_lucide_regular_16`) and resolved all 13 `semantic_roles`. |
| `tools/fonts/schemes/icon_suite_phosphor.scheme.json` | `5` / `29` | `1` / `13` | **`5` / `29`** | **`0` / `0`** | Fixed `default_font` (`humid1_icon_phosphor_regular_16`) and resolved all 13 `semantic_roles`. |
| `tools/fonts/schemes/icon_suite_tabler.scheme.json` | `4` / `20` | `1` / `13` | **`4` / `20`** | **`0` / `0`** | Fixed `default_font` (`humid1_icon_tabler_regular_16`) and resolved all 13 `semantic_roles`. |

## 5. `200×200` Waveshare 1.54in V2 EPD (`188.3 DPI`) Screen Width & Flash ROM Audit

Both `h1os_full.scheme.json` (`106` strikes, `281,450 B` / `274.9 KB` total Flash ROM) and `h1os_lite.scheme.json` (`47` strikes, `134,238 B` / `131.1 KB` total Flash ROM) pass **11 out of 11 canonical H1OS telemetry rows** within the `188 px` horizontal safe budget (`200 px` panel width minus `2 × 6 px` bezel margins):

| H1OS Screen & Row | Label String | Value String | `Sans` Only (`px`) | `Sans + Mono` (`px`) | `Cond` (`px`) | Margin to `188px` (`Sans`) | Audit Verdict |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **Screen 1: Env Dash** — Header (`14px Bold`) | `HUMIDYNE LABS` | `1/5` | `138 px` | `139 px` | `138 px` | **`+50 px`** | **PASS** |
| **Screen 1: Env Dash** — Hero Row (`20px Bold`) | `104.8°F` | `droplet 99.9%` | `144 px` | `148 px` | `144 px` | **`+44 px`** | **PASS** |
| **Screen 1: Env Dash** — Row 1 (`14px Normal`) | `Status` | `SETTLED (100%)` | `148 px` | `153 px` | `148 px` | **`+40 px`** | **PASS** |
| **Screen 1: Env Dash** — Row 2 (`14px Normal`) | `Vapor Pressure` | `42.8 hPa` | `154 px` | `162 px` | `154 px` | **`+34 px`** | **PASS** |
| **Screen 2: Psychrometrics** — Row 1 (`14px Normal`) | `Dew Point` | `78.4°F (25.8°C)` | `166 px` | `186 px` | `166 px` | **`+22 px`** | **PASS** |
| **Screen 2: Psychrometrics** — Row 2 (`14px Normal`) | `Abs Humidity` | `24.2 g/m³` | `150 px` | `159 px` | `150 px` | **`+38 px`** | **PASS** |
| **Screen 3: Thermal Nodes** — Row 4 (`14px Normal`) | `TriNode ΔT` | `+0.4°C` | `115 px` | `119 px` | `115 px` | **`+73 px`** | **PASS** |
| **Screen 4: System Health** — Row 1 (`14px Normal`) | `Battery` | `batt 4.18V (100%)` | `138 px` | `152 px` | `138 px` | **`+50 px`** | **PASS** |
| **Screen 5: Diagnostics** — Row 4 (`14px Normal`) | `Heap` | `342K (Min 298K)` | `139 px` | `154 px` | `139 px` | **`+49 px`** | **PASS** |
| **Screen 5: Diagnostics** — Row 6 (`14px Normal`) | `Wakes` | `9999 (Ring 32/32)` | `160 px` | `180 px` | `160 px` | **`+28 px`** | **PASS** |
| **Screen 5: Diagnostics** — Row 7 (`14px Normal`) | `CPU` | `240MHz • SHT:OK` | `141 px` | `148 px` | `141 px` | **`+47 px`** | **PASS** |
