# HUMIDITRON AUDIT REPORT — v1.0.10 (Revved from v1.0.9)

- **Repository**: [`Humidyne-Labs/epd-font`](https://github.com/Humidyne-Labs/epd-font)
- **Target OS**: [`Humidyne-Labs/H1OS`](https://github.com/Humidyne-Labs/H1OS)
- **Version**: `v1.0.10` (revved from `v1.0.9`)
- **Audit Reference**: `docs/audits/humid1-audit-v1.0.10.txt` & `docs/audits/exhibits/v1.0.10/`

## 1. Executive Summary of v1.0.9 → v1.0.10 Audit Findings & Fixes

| Audit Item (`humid1-audit-v1.0.10.txt`) | Root Cause Identified in v1.0.9 & Hardware Bench Testing | Resolution Implemented in v1.0.10 | Verification Status |
| :--- | :--- | :--- | :--- |
| **1. `<= 1px` stems too thin to read on physical EPD** | Physical bench testing on the Waveshare 1.54" V2 e-Paper (`200×200`, `188.3 DPI`, `0.135 mm` pixel pitch, exhibit `2026-11-03-23-59-36-040_002.jpg`) showed that `IBMPlexSans-Regular.ttf` (`wght: 400`) rasterizes with `1px` (`0.135 mm`) vertical stems at `12px–16px`, which wash out under ambient reflection. At `12px`, even `Medium` (`wght: 500`) drops to `1px` stems on several glyphs. | 1. Upgraded default `normal_weight` from `400` (`Regular`) to **`500` (`Medium`)** across all schemes and CLI tools, expanding `14px+` vertical stems to solid **`2px` (`0.27 mm`)** while keeping interior counters (`a`, `e`, `o`, `0`, `8`) crisp.<br>2. Added automatic **`>= 2px` Closed-Loop Stem Auto-Floor** for `<= 13px` strikes so `12px` glyphs also achieve `2px` stems without closing counters. | **PASS** — Verified `0` 1px vertical stem deficits across `12px–32px` and confirmed all 5 H1OS screens pass the `188px` width budget (`+22px` to `+74px` clearance). |
| **2. Automated workflow for iterative rendering & repair (OpenCV / contour)** | Needed an automated, deterministic closed-loop tool to inspect 1-BPP glyph topology, enforce `min_stem >= 2px`, protect internal counters, and render visual Before/After repair sheets. | Created `tools/fonts/humid1_bilevel_tuner.py`, added `--workflow repair` (`--min-stem 2`, `--repair-engine [hybrid\|autofloor\|downscale\|contour]`) to `humid1_generate_1bpp.py`, and added `08_iterative_auto_repair.bat` to all 3 `scripts/` directories. | **PASS** — Generates `<out-dir>/inspect_repairs/*_repair.png` Before/After visual comparison sheets with 100% hole-count non-degradation guarantee. |
| **3. H1OS include files required manual agent edits (distro not drop-in ready)** | 1. When `h1os_fonts.h` was included via `lv_conf.h` (`LV_FONT_CUSTOM_INCLUDE`) prior to `lv_font.h`, `LV_FONT_DECLARE` was not yet defined.<br>2. `humid1_fonts.h` concatenated `p_text` twice.<br>3. `plex_fonts.h` / `epd_fonts.h` lacked `HUMID1_FONT_*` macros, while `humid1_fw_emit.py` used `#include "lvgl/lvgl.h"` without `__has_include("lvgl.h")`. | Unified header generation in both `humid1_generate_1bpp.py` and `humid1_fw_emit.py`: added `__has_include("lvgl.h")` detection, forward-declared `struct _lv_font_t; typedef struct _lv_font_t lv_font_t;`, guarded `#ifndef LV_FONT_DECLARE`, removed duplicate concatenation, and emitted all `HUMID1_FONT_*`, `PLEX_FONT_*`, `HUMID1_ICON_*`, and `H1OS_FONT_*` macros in all 4 headers + added `fonts.cmake`. | **PASS** — Verified with `gcc -Wall -Wextra -Werror` across all 63 `.c` files and all 4 `.h` headers (including `#include "h1os_fonts.h"` before `lvgl.h`) with **0 warnings, 0 errors**. |
| **4. Missing key glyphs & fallbacks in H1OS fonts** | 1. `sans normal` had `"fallback": null`, so compound strings (`LV_SYMBOL_TINT " %.1f%%"`, `LV_SYMBOL_REFRESH " %u%%"`) rendered missing boxes (`▯`).<br>2. `LV_SYMBOL_USB` (`0xF287`) and `LV_SYMBOL_BLUETOOTH` (`0xF293`/`0xF294`) live in `FontAwesome7-Brands.otf`, not `Solid`.<br>3. `IBMPlexMono` lacked `U+0394 (Δ)`, `U+03A9 (Ω)`, and `U+03BC (μ)` in its `cmap` (having only `U+2206`, `U+2126`, `U+00B5`). | 1. Chained `sans_bold -> sans_normal -> humid1_icon_fa7_solid_{size}` (and `mono`/`cond`/`serif`/`math` -> `sans_normal -> icon_fa7_solid`) across all sizes `[12, 14, 16, 18, 20, 24, 32]`.<br>2. Added automatic secondary-face lookup from `FontAwesome7-Brands.ttf` (`0xF287` USB, `0xF293`/`0xF294` Bluetooth) + synthesized `0xF8A2` (`LV_SYMBOL_NEW_LINE`) + all 59 LVGL `LV_SYMBOL_*` icons.<br>3. Added homoglyph & secondary-face fallback in `rasterize_font_strike()` so `mono`, `cond`, `serif`, `sans`, and `terminus` contain all **131** UI/telemetry/Greek/arrow glyphs. | **PASS** — All 63 H1OS strikes verified for complete glyph coverage and multi-hop runtime `.fallback` resolution. |

## 2. Deep-Dive: Closed-Loop Iterative Bi-Level Auto-Floor & Repair Engine (`humid1_bilevel_tuner.py`)

### 2.1 Four Selectable Repair Engines (`--repair-engine`)
1. **`autofloor` (Collinear Outward Stem Dilation + Cavity Re-Punching + Hit-or-Miss Junction Thinning)**:
   - Measures horizontal and vertical stem survival under zero-border morphological erosion (`cv2.erode(..., borderValue=0)`).
   - Expands `1px` leftmost stems **outward-left** and `1px` rightmost stems **outward-right** with scanline-run invariance (`dilate_horizontal_preserving_gaps()`) and vertical stem collinearity snapping. Because expansion is directed away from interior cavities, internal counters (`0, 4, 6, 8, 9, A, B, D, O, P, Q, R, a, b, d, e, g, o, p, q`) and arches (`Ω, u, n, h, m`) are never pinched.
   - Re-punches exterior-flood-filled counter masks (`find_internal_counters()`), carves hole centroids if needed, applies `cv2.MORPH_HITMISS` acute corner thinning, and enforces a strict **Hole-Count Non-Degradation Guard** (`holes_after >= holes_before`).
2. **`downscale` (High-Resolution Master Sub-Pixel Phase-Shift & Threshold Optimizer)**:
   - Sweeps a `4×4` sub-pixel spatial phase grid ($\Delta x, \Delta y \in \{0.0, 0.25, 0.5, 0.75\}$) via `cv2.warpAffine` + `cv2.INTER_AREA` downsampling and binarization thresholds $T \in \{85, 105, 125, 145, 165\}$, scored by `score_candidate()` (Euler hole invariance + `>= 2px` stem survival + structural IOU).
3. **`contour` (OpenCV `RETR_CCOMP` Two-Level Polygon Re-Tracing)**:
   - Extracts outer boundaries and inner hole polygons via `cv2.findContours(..., cv2.RETR_CCOMP)`, smooths staircases with `cv2.approxPolyDP`, enforces `min_stem` stroke thickness on outer contours, and re-carves inner holes.
4. **`hybrid` (Default)**:
   - Combines `downscale` sub-pixel phase optimization with `autofloor` collinear outward stem dilation and cavity protection.

## 3. H1OS Drop-In Header & Fallback Chain Verification

### 3.1 Multi-Hop LVGL Fallback Chain (Verified in Compiled Binary)
- `HUMID1_FONT_UI_HEADER` (`&humid1_font_plex_sans_bold_20`)
  $\longrightarrow$ `.fallback = &humid1_font_plex_sans_normal_20`
  $\longrightarrow$ `.fallback = &humid1_icon_fa7_solid_20` (`87` icons including `0xF043` Droplet, `0xF021` Refresh, `0xF0E7` Bolt, `0xF240–0xF244` Battery 0–4, `0xF287` USB, `0xF293`/`0xF294` Bluetooth).
- `HUMID1_FONT_UI_BODY` (`&humid1_font_plex_sans_normal_14`)
  $\longrightarrow$ `.fallback = &humid1_icon_fa7_solid_14`.
- `HUMID1_FONT_TELEMETRY_SM` (`&humid1_font_plex_mono_normal_14`)
  $\longrightarrow$ `.fallback = &humid1_font_plex_sans_normal_14`
  $\longrightarrow$ `.fallback = &humid1_icon_fa7_solid_14`.

### 3.2 Firmware Flash (`.rodata`) & Disk Footprint (`total_disk_size.txt`)

| Target Scheme | Total Strikes | Total Glyphs | Expected MCU Flash (`.rodata` ROM) | Host `.c`/`.h` Disk Size | Fits in 512 KB Flash? | Fits in 1 MB Flash? |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **`example.scheme.json`** (`scripts/example-build-distro`) | `19` | `2,331` | **`83,071 B` (`81.12 KB`)** | `692,118 B` (`675.90 KB`) | **YES (`15.8%`)** | **YES (`7.9%`)** |
| **`h1os_full.scheme.json`** (`scripts/h1os-build-distro`) | `63` | `7,509` | **`290,119 B` (`283.32 KB`)** | `2,461,480 B` (`2,403.79 KB`) | **YES (`55.3%`)** | **YES (`27.7%`)** |
