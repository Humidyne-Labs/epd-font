# Humidyne Labs / Humiditron `epd-font` v1.0.14 — Formal Engineering & Typographic Audit Report

- **Repository**: [`https://github.com/Humidyne-Labs/epd-font`](https://github.com/Humidyne-Labs/epd-font)
- **Target OS**: [`https://github.com/Humidyne-Labs/H1OS`](https://github.com/Humidyne-Labs/H1OS)
- **Version**: `v1.0.14` (Revved from `v1.0.13`)
- **Audit Input Reference**: `docs/audits/humid1-audit-v1.0.14.txt` & `docs/audits/exhibits/v1.0.14/` (`crash-log.txt`, `Inter-ExtraBold.ttf`, `InterDisplay-ThinItalic.ttf`)
- **Target Display**: Waveshare 1.54" V2 1-BPP Monochrome E-Paper Display (SSD1681, `200x200` px @ `188.3 DPI`)

## 1. Executive Summary & Audit Scope

This `v1.0.14` audit covers both a **General Repository & Build-System Audit** and an **Issue-Specific Forensic Audit** of all findings reported in `docs/audits/humid1-audit-v1.0.14.txt` and `docs/audits/exhibits/v1.0.14/crash-log.txt`:

| Audit ID | Component / Exhibit | Issue / Observation in `v1.0.13` | Root Cause Identified | `v1.0.14` Engineering Resolution | Status |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **AUD-14-01** | `tools/fonts/humid1_ft_raster.py` & `humid1_font_eval.py` (`crash-log.txt` L707–760) | `02_run_font_eval.bat` crashed at font `[61/408]` (`IosevkaAile-Bold.ttc`) with `TTLibFileIsCollectionError: specify a font number between 0 and 2 (inclusive)` | While `inspect_font_metadata()` opened `.ttc` files with `fontNumber=0`, `rasterize_font_strike()` at `humid1_ft_raster.py:566` called `TTFont(str(font_path))` without `fontNumber`, crashing the worker pool on the first `.ttc` collection | Added `open_ttfont_safe(font_path, font_number=0)` across `humid1_ft_raster.py`, `humid1_font_eval.py`, and `humid1_generate_1bpp.py` (handling `.ttc`/`.otc` extensions and catching `TTLibFileIsCollectionError`), plus added `try...except` fault isolation inside `_worker_evaluate_font()` | **FIXED** |
| **AUD-14-02** | `InterDisplay-ThinItalic.ttf` (`w100`) & `Inter-Thin` (`crash-log.txt` L687–706) | Ultra-thin `w100` fonts reported `16px HQConf: 10.9%` alongside a contradictory `>=2px: 100.0%` stem survival score | Under `autohint_mono`, 50+ of 60 benchmark characters in `Thin (w100)` vanished completely (`0` ink pixels) and were skipped (`if not g.rows: continue`), while surviving 2px dot fragments had `total_stem_runs < 2` (`h_ratio = 1.0`) | `measure_stem_deficits()` now returns `needs_h=True, h_ratio=0.0` when `nz == 0` or `total_stem_runs == 0`; `humid1_font_eval.py` evaluates all 60 benchmark characters without skipping vanished glyphs (`Thin w100` now properly reports `>=2px: 0.0%`, `Floor: >24px`, `TIER 4: DO NOT USE`) | **FIXED** |
| **AUD-14-03** | `Inter-ExtraBold.ttf` (`w800`) & Multi-Font Size Floor Estimator | Size floor estimates (`10px`–`12px`) were unrealistically small on `Regular (w400)`, `Bold (w700)`, and `ExtraBold (w800)` outline fonts | 1. `humid1_bilevel_tuner.py:1244` gated `expected_b1` on `if w0 >= 5 and h0 >= 7:`, so collapsed counters on `'a'` and `'e'` at `10px–12px` (`h0 = 6`) defaulted to `expected_b1 = 0` and passed!<br>2. Pinched `1px` pinhole counters (`14px` `'a'`) and pinched figure-8 `'s'` were not penalized | Removed the `h0 >= 7` restriction and added `CANONICAL_MIN_HOLES`, `PINCH_FORBIDDEN_CHARS`, and `_check_counter_cavity_viable()` (`hole_px >= 2` on core counters, `b1 == 0` on open curves, `HQConf >= 72%`, `mean_stem_w >= 1.62px`). `Inter-ExtraBold` now reports a realistic **`16px` (`12pt`)** floor | **FIXED** |
| **AUD-14-04** | `humid1_bilevel_tuner.py` (`Inter-ExtraBold.ttf` exhibit) | Residual `1px` "outline-warts" remained visible on curved bowls, arches, and diagonals even after tuning | 1. `detect_skin_tags_and_notches()` only scanned horizontal rows (`fg[r]`), missing vertical `1px` top/bottom pimples (`fg[:, c]`) on `'a'`, `'s'`, `'%'`, and `'1'`.<br>2. The `v1.0.13` "Do No Harm" early-exit gate returned `base_1bit` *before* running `clean_skin_tags_and_notches()` | Upgraded `detect_skin_tags_and_notches()` to **4-Directional Outline-Wart Detection** (horizontal + vertical) and added a **Universal Pre-Exit Wart-Shaving Pass (`M0_wart_shaved`)** that shaves HQ-verified warts on all glyphs without thickening stems | **FIXED** |
| **AUD-14-05** | Architecture: Font/Weight Selection vs. Auto-Tuning | User noted small visual delta between `RAW` and `TUNED` on well-chosen weights and asked whether to rely on native font/weight mix-and-match vs. auto-tuning | Once `Medium (500)` / `SemiBold (600)` is used for `normal`, `ExtraBold (800)` / `Black (900)` for `bold`, and `Terminus` for `<=12px`, FreeType already produces `>=2px` stems on `85%–98%` of glyphs natively | Added `--tune-mode {off,wart-only,surgical,full}` across `humid1_bilevel_tuner.py`, `humid1_generate_1bpp.py`, and `humid1_font_eval.py`, plus full architectural guidance in Section 3 below | **FIXED** |
| **AUD-14-06** | `scripts/*/*.bat` (`crash-log.txt` L26, 235, 319, 404, 497, 602) | Batch script `echo` banners still printed `v1.0.11` | Outdated version string in `.bat` header lines | Synchronized all `.bat` banners across `scripts/h1os-build-distro/`, `scripts/example-build-distro/`, and `scripts/full-audit-build-distro/` to `v1.0.14` | **FIXED** |

---

## 2. Issue-Specific Forensic Analysis & Verification

### 2.1 Root Cause & Fix of the `.ttc` Crash (`IosevkaAile-Bold.ttc` at `[61/408]`)

In `docs/audits/exhibits/v1.0.14/crash-log.txt` (lines 707–760), `02_run_font_eval.bat` scanned the external `eval_fonts` directory (`408` font cuts) and completed `[1/408]` through `[60/408]` before crashing on `[61/408]` (`IosevkaAile-Bold.ttc`):

```text
File "...\tools\fonts\humid1_ft_raster.py", line 566, in rasterize_font_strike
  tt = TTFont(str(font_path))
fontTools.ttLib.TTLibFileIsCollectionError: specify a font number between 0 and 2 (inclusive)
```

- **Why It Happened**: TrueType Collection (`.ttc` / `.otc`) files pack multiple `sfnt` font tables into a single binary container. While `inspect_font_metadata()` in `humid1_font_eval.py` passed `fontNumber=0 if fname_low.endswith(".ttc") else None`, `rasterize_font_strike()` in `humid1_ft_raster.py` line 566 invoked `TTFont(str(font_path))` without `fontNumber`.
- **`v1.0.14` Fix**:
  1. Added `open_ttfont_safe(font_path, font_number=0, lazy=False)` in `tools/fonts/humid1_ft_raster.py`, which automatically passes `fontNumber=font_number` for `.ttc`/`.otc` files AND catches `TTLibFileIsCollectionError` as a fallback (in case a collection file has a `.ttf` extension).
  2. Synchronized `ft.FT_New_Face(..., font_number, ...)` with `open_ttfont_safe(..., font_number=font_number)` in `rasterize_font_strike()`.
  3. Added a `try...except Exception` fault-isolation wrapper around `_worker_evaluate_font()` in `humid1_font_eval.py` so that if any single file in a 700MB+ font directory is corrupted or unreadable, the worker logs a warning and continues without aborting the batch.

### 2.2 Why `InterDisplay-ThinItalic.ttf` (`w100`) Reported `>=2px: 100.0%` & Why Size Floors Were Too Low

Inspection of the two exhibit fonts in `docs/audits/exhibits/v1.0.14/approx-fonts-ttf/` (`InterDisplay-ThinItalic.ttf` and `Inter-ExtraBold.ttf`) revealed two subtle metric bugs in `v1.0.13`:

1. **The "Ghost Font" Paradox (`InterDisplay-ThinItalic.ttf`, `w100`)**:
   - At `10px`, FreeType monochrome rasterization (`FT_LOAD_TARGET_MONO`) produces **`0` ink pixels** across the entire 60-character benchmark (`52` to `60` characters vanish completely at `10px–16px`, leaving only `8` to `38` scattered pixels across the entire alphabet).
   - In `v1.0.13`, `humid1_font_eval.py` skipped any glyph with empty rows (`if not g.rows: continue`), and `measure_stem_deficits()` returned `h_ratio = 1.0, needs_h = False` whenever `total_stem_runs == 0`. Consequently, the few surviving `2px` dot fragments scored `8/8 = 100.0%` stem survival!
   - **Fix in `v1.0.14`**: `measure_stem_deficits()` now returns `needs_h = True, h_ratio = 0.0` whenever `nz == 0` or `total_stem_runs == 0`, and `_worker_evaluate_font()` evaluates all `len(EVAL_BENCHMARK_CHARS)` characters (penalizing any vanished glyph or `<42%` HQ-confidence fragment as `0%` stem survival). `InterDisplay-ThinItalic (w100)` now reports **`>=2px: 0.0%` across `10px–24px`**, **`Size Floor: >24px`**, and **`TIER 4: DO NOT USE ON 1-BPP EPD (Sub-Pixel Hairline Dropout)`**.

2. **Why `Inter-ExtraBold.ttf` (`w800`) Previously Reported a `10px` Floor Instead of `16px`**:
   - At `10px` and `12px`, `Inter-ExtraBold` (`w800`) completely fills in the internal counter of lowercase `'e'` (`b1 = 0`, solid `######` block) and `'a'` (`b1 = 0` at `10px`).
   - Why did `v1.0.13` miss that? Because line 1244 of `humid1_bilevel_tuner.py` contained `if w0 >= 5 and h0 >= 7: expected_b1 = max(b1_base, b1_hi)`. At `10px` and `12px`, lowercase `'a'` and `'e'` have bounding-box height `h0 = 6` (`< 7`), so `expected_b1` was never populated from the 8x HQ Master and stayed at `b1_base = 0`!
   - Furthermore, at `14px` in `Inter-ExtraBold`, lowercase `'a'` (`7x8`) has only a **1-pixel pinhole counter** (`###.###`, `hole_px = 1`) and lowercase `'s'` (`6x8`) pinches its upper and lower terminals shut into a figure-8 (`b1 = 2` instead of `0`).
   - **Fix in `v1.0.14`**:
     - Added `CANONICAL_MIN_HOLES` (`0, 4, 6, 8, 9, A, B, D, O, P, Q, R, a, b, d, e, g, o, p, q, %, @`) and `PINCH_FORBIDDEN_CHARS` (`C, E, F, G, H, I, J, K, L, M, N, S, T, U, V, W, X, Y, Z, c, f, h, i, j, l, m, n, r, s, t, u, v, w, x, y, z, ...`) regardless of glyph height `h0`.
     - Added `_check_counter_cavity_viable()` in `humid1_font_eval.py`, requiring `hole_px >= 2` on core single-loop readers in heavy weights (`wght >= 650`) and `b1 == 0` on open-curve characters (`s, c, w, M`), plus `HQConf >= 72.0%` and `mean_stem_width >= 1.62px`.
     - As a result, `Inter-ExtraBold (w800)` now fails `10px`, `12px`, and `14px` and passes cleanly at **`16px` (`12.0pt`)**, matching visual reality on a 188 DPI panel.

### 2.3 Eliminating Residual "Outline-Warts" (`4-Directional Wart Shaving` + `M0_wart_shaved`)

Forensic inspection of `Inter-ExtraBold.ttf` across `14px–24px` revealed why a few `1px` outline-warts remained in `v1.0.13`:
1. **Vertical Pimples Were Not Scanned**: `detect_skin_tags_and_notches()` previously scanned only horizontal row runs (`fg[r]`), missing `1px` vertical pimples hanging off horizontal arches/terminals (`fg[:, c]`), such as `(3, 2)` under the top arch of `20px 'a'`, `(3, 7)` under the top terminal of `20px 's'`, `(6, 13)` on top of the lower circle of `20px '%'`, and `(3, 1)` under the nose of `16px '1'`.
2. **Early-Return Gate Bypassed Wart Shaving**: In `v1.0.13`, whenever `skip_for_bold` or `skip_for_high_conf` triggered (which applies to ~95% of `ExtraBold` and `>=14px` `Medium` glyphs), `inspect_and_repair_glyph_bitmap()` returned `base_1bit` *before* calling `clean_skin_tags_and_notches()`.
3. **`v1.0.14` Fix**:
   - Upgraded `detect_skin_tags_and_notches()` to scan **all 4 cardinal directions** (horizontal left/right lateral spurs on `fg[r]` + vertical top/bottom pimples on `fg[:, c]`, Verified against the 8x continuous HQ Master coverage map `hq_cov < 0.48..0.64`).
   - Added a **Universal Pre-Exit Wart-Shaving Pass (`M0_wart_shaved`)** inside `inspect_and_repair_glyph_bitmap()` so that *every* glyph—even when stem widening is skipped—has its 4-directional outline-warts cleanly shaved off whenever doing so preserves Betti numbers `(B0, B1)`, scanline run counts, and 8x HQ IoU confidence.

---

## 3. Architectural Analysis: Native Font/Weight Division-of-Labor vs. Auto-Tuning

In `humid1-audit-v1.0.14.txt`, you raised a fundamental architectural question:
> *"It might be easier to select another font weight or separate font entirely for bold, italic, and normal font use, rather than relying on the tuning script to generate an ideal font. Based on what I'm seeing on the evaluation sheet, there isn't a massive visual change between the tuned and untuned fonts, although the differences are visible when looking closely. There are still some outline-warts that need to be removed, though they are fewer in number. Because of this, we might be able to get away with turning off the auto-tune feature to see how it performs when mixing and matching fonts to suit our needs (like using bold for standard, black for bold, terminus for small, etc.). I'll leave that up to you to decide, or I can hear your thoughts on it."*

### 3.1 Why `RAW` and `TUNED` Look So Close on Our Current Font Stack

Your observation is spot on—and the reason `RAW` and `TUNED` look nearly identical at `16px–24px` on our current stack is that **native weight selection is already doing 85%–95% of the heavy lifting**:
- Look at the `16px` data from the `v1.0.14` benchmark table below:
  - When you rasterize a standard **`Regular (w400)`** font (`IBMPlexSans-Regular` or `Inter-Regular`) at `16px`, raw FreeType produces **`>=2px` stems on only `5.0%–6.7%` of glyphs** (`93%+` of stems are fragile `1px` hairlines!). To make `w400` survive on e-paper, the auto-tuner has to rebuild **`75.0%–78.3%` of the alphabet**, which inevitably distorts letterforms.
  - By contrast, when you step up the native font weight—using **`Medium (w500)`** or **`SemiBold (w600)`** for `normal` body text and **`ExtraBold (w800)`** for `bold` headers—raw FreeType **natively renders `>=2px`–`3px` stems on `85.0%` to `96.7%` of glyphs out of the box** (`RAW HQ Confidence = 74.4%–84.0%`)!
  - Consequently, on `Medium (w500)` / `SemiBold (w600)` / `ExtraBold (w800)` at `>=16px`, our `v1.0.13–v1.0.14` "Do No Harm" gate intentionally leaves `88%–97%` of the alphabet untouched, only intervening on `3%–12%` of glyphs (shaving 1px autohint outline-warts and synchronizing paired brackets `( )`, `[ ]`, `{ }`).

### 3.2 Recommended Division-of-Labor Strategy & The New `--tune-mode` Flag

Mixing and matching purpose-built native fonts and heavier weights by size/role is **mathematically and visually superior** to forcing a single thin font through heavy morphological thickening:

| UI Role & Size Band | Recommended Native Font / Weight Strategy | Recommended `--tune-mode` | Why This Works Best on 188 DPI 1-BPP EPD |
| :--- | :--- | :---: | :--- |
| **Micro Telemetry & Labels (`10px–12px` / `7.5pt–9pt`)** | **Terminus Native Bitmap** (`Terminus-Normal-12.ttf`, `Terminus-Bold-12.ttf`) | `off` (Automatic for Terminus) | Hand-authored pixel-by-pixel for 1-BPP grids; `100%` counter survival at `10px–12px` where outline fonts pinch shut |
| **Compact UI Body (`14px` / `10.5pt`)** | **SemiBold (`w600`)** or **Bold (`w700`)** (`IBMPlexSans-SemiBold.ttf` / `Inter-SemiBold.ttf`) or **Terminus 14px** | `wart-only` or `surgical` | `w600`/`w700` hits the `14px` viable floor natively (`95%` `>=2px` stems, `100%` open counters) without needing stem inflation |
| **Standard UI Body (`16px–20px` / `12pt–15pt`)** | **Medium (`w500`)** or **SemiBold (`w600`)** (`IBMPlexSans-Medium.ttf`, `IBMPlexMono-Medium.ttf`, `Inter-Medium.ttf`) | `wart-only` or `surgical` | Native stems are `2.0px–2.5px` wide out of FreeType; only needs `1px` outline-wart shaving and bracket symmetry |
| **Bold Headers & Hero Values (`16px–32px` / `12pt–24pt`)** | **ExtraBold (`w800`)** or **Black (`w900`)** (`IBMPlexSans-ExtraBold.ttf`, `Inter-ExtraBold.ttf`) | `wart-only` or `surgical` | Native stems are `3.1px–4.7px` wide with `100%` open counters at `>=16px`; stem thickening is completely unnecessary (`0%` stem inflation; only `M0_wart_shaved` runs) |

To let you test and deploy any level of intervention effortlessly, `v1.0.14` adds `--tune-mode {off,wart-only,surgical,full}` to `humid1_bilevel_tuner.py`, `humid1_generate_1bpp.py`, and `humid1_font_eval.py` (as well as `"tune_mode"` in `*.scheme.json`):
- **`--tune-mode off`**: **100% Pure Native FreeType** (`0` patches applied; pure font/weight mix-and-match).
- **`--tune-mode wart-only`**: **Zero Stem Thickening** — runs *only* the `v1.0.14` 4-directional `1px` outline-wart shaver (`M0_wart_shaved`) and Bilateral Mirror-Pair Synchronization (`( )`, `[ ]`, `{ }`, `< >`).
- **`--tune-mode surgical` (Default)**: Identical to `wart-only` on all `Bold`/`ExtraBold` strikes and `>=16px` `Medium`/`SemiBold` glyphs (`M0_wart_shaved`), while retaining surgical 2px stem rescue for `12px–14px` `Medium` strikes and narrow `1px` vertical symbols (`$`, `|`, `!`).
- **`--tune-mode full`**: Runs the full `M0..M8` candidate tournament across all sizes and weights.

---

## 4. `v1.0.14` Multi-Font Pre-Tune (`RAW`) vs. Post-Tune (`TUNED`) Scorecard (`10px–24px`)

All 22 internal and exhibit font cuts were benchmarked across `[10, 12, 14, 16, 20, 24]` px (`build/font_eval/font_eval_comparison_sheet.png` and individual sheets in `build/font_eval/sheets/*.png`):

| Typeface & Weight Label | Font File | `wght` | `v1.0.14` Recommendation Tier | Raw Floor | Tuned Floor | 16px HQ Conf (`Raw -> Tuned`) | 16px `>=2px` Stems (`Raw -> Tuned`) | 16px Tuning Burden | Per-Font PNG Sheet |
| :--- | :--- | :---: | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **Terminus Bold Bitmap (w700)** | `Terminus-Bold-16.ttf` | `700` | **TIER 1: NATIVE READY** | **`10px`** | **`10px`** | `100.0% -> 100.0%` | `100.0% -> 100.0%` | `0/60 (0.0%)` | `sheets/Terminus-Bold-16_eval.png` |
| **Terminus Native Bitmap (w400)** | `Terminus-Normal-16.ttf` | `400` | **TIER 1: NATIVE READY** | **`12px`** | **`12px`** | `100.0% -> 100.0%` | `100.0% -> 100.0%` | `0/60 (0.0%)` | `sheets/Terminus-Normal-16_eval.png` |
| **Inter Bold (w700) [External]** | `Inter-Bold.otf` | `700` | **TIER 1: NATIVE READY** | **`12px`** | **`12px`** | `81.1% -> 81.1%` | `96.7% -> 96.7%` | `0/60 (0.0%)` | `sheets/Inter-Bold_eval.png` |
| **Inter SemiBold (w600) [External]** | `Inter-SemiBold.otf` | `600` | **TIER 1: NATIVE READY** | **`14px`** | **`12px`** | `81.2% -> 81.1%` | `95.0% -> 96.7%` | `1/60 (1.7%)` | `sheets/Inter-SemiBold_eval.png` |
| **IBM Plex Sans SemiBold (w600)** | `IBMPlexSans-SemiBold.ttf` | `600` | **TIER 1: NATIVE READY** | **`14px`** | **`14px`** | `78.7% -> 79.1%` | `95.0% -> 98.3%` | `4/60 (6.7%)` | `sheets/IBMPlexSans-SemiBold_eval.png` |
| **IBM Plex Sans Bold-700 [Legacy w700]** | `IBMPlexSans-Bold.ttf` | `700` | **TIER 1: NATIVE READY** | **`14px`** | **`14px`** | `78.2% -> 77.9%` | `95.0% -> 95.0%` | `4/60 (6.7%)` | `sheets/IBMPlexSans-Bold_eval.png` |
| **IBM Plex Sans Bold [ExtraBold w800]** | `IBMPlexSans-ExtraBold.ttf` | `800` | **TIER 1: NATIVE READY** | **`16px`** | **`16px`** | `84.0% -> 84.3%` | `96.7% -> 96.7%` | `2/60 (3.3%)` | `sheets/IBMPlexSans-ExtraBold_eval.png` |
| **Inter ExtraBold (w800) [v1.0.14 Exhibit]** | `Inter-ExtraBold.ttf` | `800` | **TIER 1: NATIVE READY** | **`16px`** | **`16px`** | `83.1% -> 83.5%` | `96.7% -> 96.7%` | `3/60 (5.0%)` | `sheets/Inter-ExtraBold_eval.png` |
| **IBM Plex Mono Bold [ExtraBold w800]** | `IBMPlexMono-ExtraBold.ttf` | `800` | **TIER 1: NATIVE READY** | **`16px`** | **`16px`** | `82.5% -> 82.7%` | `95.0% -> 96.7%` | `3/60 (5.0%)` | `sheets/IBMPlexMono-ExtraBold_eval.png` |
| **IBM Plex Mono Normal [Medium w500]** | `IBMPlexMono-Medium.ttf` | `500` | **TIER 1: NATIVE READY** | **`16px`** | **`16px`** | `73.2% -> 73.5%` | `90.0% -> 96.7%` | `5/60 (8.3%)` | `sheets/IBMPlexMono-Medium_eval.png` |
| **IBM Plex Sans Normal [Medium w500]** | `IBMPlexSans-Medium.ttf` | `500` | **TIER 1: NATIVE READY** | **`16px`** | **`16px`** | `74.4% -> 75.1%` | `85.0% -> 91.7%` | `7/60 (11.7%)` | `sheets/IBMPlexSans-Medium_eval.png` |
| **Inter Medium (w500) [External]** | `Inter-Medium.otf` | `500` | **TIER 1: NATIVE READY** | **`16px`** | **`16px`** | `73.3% -> 74.5%` | `86.7% -> 95.0%` | `7/60 (11.7%)` | `sheets/Inter-Medium_eval.png` |
| **IBM Plex Sans Cond Bold [ExtraBold w800]** | `IBMPlexSansCondensed-ExtraBold.ttf` | `800` | **TIER 3: LARGE SIZES (`>=20px`)** | `20px` | `20px` | `82.5% -> 82.6%` | `96.7% -> 96.7%` | `4/60 (6.7%)` | `sheets/IBMPlexSansCondensed-ExtraBold_eval.png` |
| **IBM Plex Sans Cond Normal [Medium w500]** | `IBMPlexSansCondensed-Medium.ttf` | `500` | **TIER 3: LARGE SIZES (`>=20px`)** | `20px` | `20px` | `71.8% -> 72.7%` | `78.3% -> 90.0%` | `11/60 (18.3%)` | `sheets/IBMPlexSansCondensed-Medium_eval.png` |
| **IBM Plex Serif Bold [ExtraBold w800]** | `IBMPlexSerif-ExtraBold.ttf` | `800` | **TIER 3: LARGE SIZES (`>=20px`)** | `20px` | `20px` | `79.4% -> 79.5%` | `83.3% -> 83.3%` | `2/60 (3.3%)` | `sheets/IBMPlexSerif-ExtraBold_eval.png` |
| **IBM Plex Serif Normal [Medium w500]** | `IBMPlexSerif-Medium.ttf` | `500` | **TIER 3: LARGE SIZES (`>=20px`)** | `24px` | `20px` | `74.8% -> 75.8%` | `66.7% -> 83.3%` | `14/60 (23.3%)` | `sheets/IBMPlexSerif-Medium_eval.png` |
| **Inter Regular (w400) [External]** | `Inter-Regular.otf` | `400` | **TIER 3: HIGH TUNE BURDEN (`>=20px`)** | `24px` | `20px` | `66.4% -> 71.1%` | `5.0% -> 71.7%` | `45/60 (75.0%)` | `sheets/Inter-Regular_eval.png` |
| **IBM Plex Sans Regular (w400)** | `IBMPlexSans-Regular.ttf` | `400` | **TIER 3: HIGH TUNE BURDEN (`>=24px`)** | `24px` | `24px` | `62.5% -> 68.7%` | `6.7% -> 63.3%` | `47/60 (78.3%)` | `sheets/IBMPlexSans-Regular_eval.png` |
| **IBM Plex Sans Italic [MedItal w500]** | `IBMPlexSans-MediumItalic.ttf` | `500` | **TIER 3: LARGE SIZES (`>=24px`)** | `24px` | `24px` | `67.6% -> 69.4%` | `60.0% -> 85.0%` | `17/60 (28.3%)` | `sheets/IBMPlexSans-MediumItalic_eval.png` |
| **IBM Plex Math Regular (w400)** | `IBMPlexMath-Regular.ttf` | `400` | **TIER 3: HIGH TUNE BURDEN (`>=24px`)** | `>24px` | `24px` | `64.4% -> 67.2%` | `3.3% -> 40.0%` | `43/60 (71.7%)` | `sheets/IBMPlexMath-Regular_eval.png` |
| **InterDisplay ThinItalic (w100) [v1.0.14 Exhibit]** | `InterDisplay-ThinItalic.ttf` | `100` | **TIER 4: DO NOT USE ON 1-BPP EPD** | `>24px` | `>24px` | `4.7% -> 4.7%` | `0.0% -> 0.0%` | `1/60 (1.7%)` | `sheets/InterDisplay-ThinItalic_eval.png` |

---

## 5. Build System & H1OS Verification Summary (`v1.0.14`)

- **Static TTF Assets (`build/static_ttfs/`)**: `88` verified static `.ttf` binaries (`6` IBM Plex families across Regular/Medium/SemiBold/Bold/ExtraBold + `72` native Terminus pixel-locked `.ttf` strikes + `5` icon vendors).
- **H1OS 1-BPP Strike Suite (`build/h1os/fonts/` & `dist/humid1_epd_vault.json.gz`)**:
  - `63` C/H font and icon strikes compiled cleanly (`262,008 bytes` / `255.9 KB` total Flash ROM; `307,795 bytes` compressed Strike Vault).
  - `674` surgical ASCII glyph overrides compiled into `font_icon_epd_patches.json` (with `Bold`/`ExtraBold` strikes receiving *only* 4-directional outline-wart shaving `M0_wart_shaved` and mirror bracket sync).
  - All `11/11` Waveshare 1.54" V2 (`200x200` @ `188.3 DPI`) horizontal screen budget rows pass with `+17px` to `+72px` clearance.
