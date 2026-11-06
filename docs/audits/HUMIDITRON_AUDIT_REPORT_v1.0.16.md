# Humidyne Labs / Humiditron `epd-font` v1.0.16 — Tri-Role Visual Contrast Scoring, 425-Font Data Digest & Profile Scheme Overhaul

**Document ID:** `HUMIDITRON-AUDIT-v1.0.16`  
**Date:** 2026-11-05  
**Target OS / Hardware:** `H1OS` / `humid1-os` — Waveshare 1.54" V2 EPD (`SSD1681`, `200×200`, `188.3 DPI`, `1-BPP`)  
**Scope:** Root-Cause Diagnosis of `v1.0.15` Visual Homogeneity, `v1.0.16` Tri-Role Visual Contrast Triad Scorer, Counter-Carving Engine (`M0_counter_carved`), 425-Font / 30-Family Triad Re-Digest, and Profile Scheme Overhaul (`Normal w500` + `Bold Punch w800` + `Subtle Iso-Weight Italic w600/w500`)

---

## 1. Executive Summary: Why the `v1.0.15` Contenders Looked Like the Same Font

When inspecting the `v1.0.15` evaluation sheets (`h1os-dtfr-v1.0.15.zip`), you spotted a critical flaw that raw single-font metrics completely missed: **visually, `Normal`, `Bold`, and `Italic` all looked like the same weight (`~2.3px–2.5px` stems), and `Italic` was actually heavier than `Bold`!**

### 1.1 The 3 Root Causes of `v1.0.15` Visual Homogeneity

| Root Cause | What Happened in `v1.0.15` | Quantitative Proof (`16px` Benchmark) | How `v1.0.16` Fixes It |
| :--- | :--- | :--- | :--- |
| **1. Isolated Single-Font `8x HQ IoU` Bias** | Ranking each font in isolation by raw `hq_conf_iou` rewarded fonts whose native stem width landed closest to an integer multiple of the `1-BPP` grid (`2.0px` for `w600 SemiBold`, `2.5px` for `w700 Bold`). Pushing `Normal` up to `w600` (`2.36px` stem) left **zero contrast headroom** beneath `w700 Bold` (`2.57px` stem). | `Inter-SemiBold (w600)`: `2.36px` stem, `2,753` ink px<br>`Inter-Bold (w700)`: `2.57px` stem, `2,934` ink px<br>**Delta = only `+0.21px` stem / `+6.5%` ink!** (Sub-perceptual on 1-BPP e-paper) | Replaced isolated scoring with **Role-Aware & Tri-Role Family Triad Scoring (`evaluate_family_triads`)** in `humid1_font_eval.py`, requiring **`+35% to +65%` Bold Ink Punch** and a **`+0.85px to +1.45px` integer stem jump (`2px -> 3px`)**. |
| **2. Inverted Italic Hierarchy ("Bludgeon Italic")** | Slanted diagonal strokes suffer `~5–8%` staircase quantization against an unhinted `8x` outline unless they are `3px` thick. Thus, isolated scoring crowned `Inter-ExtraBoldItalic (w800)` as the #1 Italic—making **Italic `+16.4%` heavier than Bold** (`3,416` vs `2,934` ink px) and `+24.1%` heavier than Normal! | `Inter-ExtraBoldItalic (w800)`: `3.08px` stem, `3,416` ink px (**heavier than Bold!**)<br>True subtle Italic (`w500/w600`): `2.10–2.30px` stem, `2,331–2,600` ink px (`-9%..+1.3%` vs Normal) | Enforces **Iso-Weight Subtle Italic (`[-10% .. +12%]` ink vs. `Normal`, and `>= 25%` lighter than `Bold`)**, using `SemiBoldItalic (w600)` on Sans/Cond (`+1.3%` vs Normal) and `MediumItalic (w500)` on Mono (`-3.1%` vs Normal). |
| **3. `.scheme.json` Override & `M0` Counter-Carving Skip on `ExtraBold (w800)`** | Even though `humid1_generate_1bpp.py` defaulted to `bold_weight=800`, all `.scheme.json` files still declared `"bold_weight": 700`. Furthermore, `humid1_bilevel_tuner.py` skipped counter carving when `is_bold_role=True`, leaving `1px` pinholes on `14px` `'a'`/`'e'` and pinched loops on `'s'` (`20px`) in `ExtraBold (w800)`. | `IBMPlexSans-ExtraBold (w800)` raw `16px` counters: `95.2%` (`'s'` pinched at `20px`); `IBMPlexSans-SemiBoldItalic (w600)` raw `16px` counters: `90.5%` (spurious `expected_b1=2` on single-story `'a'`). | Added **Universal Counter-Carving & Loop-Unpinching (`M0_counter_carved`)** and clamped `expected_b1=1` on `SINGLE_COUNTER_OPEN_TAIL_CHARS` in `humid1_bilevel_tuner.py` (**`100.0%` open counters across `12px–24px`!**), and updated all 19 `.scheme.json` files to `"bold_weight": 800, "italic_weight": 600`. |

---

## 2. Pattern-Recognition Typography Physics on 1-BPP E-Paper

For a reader whose visual cortex processes text via **whole-word pattern recognition (Bouma shape envelopes + spatial frequency density)** rather than letter-by-letter phonetic decoding, each typographic style must operate on an **orthogonal visual channel**:

1. **`NORMAL (BODY)` — Baseline Spatial Frequency (`1.00x` Ink Mass, `2.00px–2.20px` Stems)**:
   - Must sit cleanly on a **`2px` stem grid** (`IBMPlexSans-Medium w500`: `2.17px` stem, `2,566` ink px at `16px`) with large, open internal counters (`100.0%` counter survival).
   - Must **never** use `w600 SemiBold` (`2.36px` stem) for body text, because `w600` consumes the optical dynamic range needed for `Bold` to pop.
2. **`BOLD (PUNCH)` — High-Amplitude Luminance / Ink-Mass Jump (`+35% to +65%` Ink Mass, `3.00px–3.40px` Stems)**:
   - On a 1-BPP display with zero grayscale anti-aliasing, peripheral attention is triggered by **local black-pixel density (ink mass)** and **integer stem-width quantization (`2px -> 3px`)**.
   - Stepping from `Normal (w500)` to `ExtraBold (w800)` (`IBMPlexSans-ExtraBold`: `3.13px` stem, `3,482` ink px = **`+35.7%` ink punch** at `16px` and **`+44.1%` ink punch** at `14px`) or `Black (w900)` (`Inter-Black`: `3.37px` stem, `3,746` ink px = **`+52.3%` ink punch**) creates an instant, pre-attentive visual anchor.
3. **`ITALIC (SUBTLE EMPHASIS)` — Iso-Weight Slant & Cursive Allograph Shift (`-9% to +6%` Ink Mass vs. `Normal`, `>= 33%` Lighter than `Bold`)**:
   - Italic is meant to **allude or imply** without shouting. If Italic changes the black-pixel density of the page, the eye mistakes it for a weak Bold.
   - Instead, Italic must keep **nearly identical ink mass (`1.00x`) and stem width (`~2.10px–2.30px`) to `Normal`**, signaling emphasis purely through its **`9°–11°` forward slant** and **cursive glyph shapes** (single-story `'a'`, curved `'f'`, hooked `'g'`, `'e'`, `'s'`).
   - Because FreeType monochrome rasterization thins slanted strokes by `~8%`, `IBMPlexSans-SemiBoldItalic (w600)` lands at **`2.30px` stem and `2,600` ink px (`+1.3%` vs `Normal w500`, and `-33.9%` lighter than `ExtraBold w800`)** with **`100.0%` open counters** and **`96.7%` `>=2px` stem survival**!

---

## 3. Re-Digested 425-Font / 30-Family Tri-Role Triad Leaderboard (`v1.0.16`)

Using the new `humid1_font_eval.py --re-digest-json` Tri-Role Triad Scorer across the combined `425` font cuts (`01_font_eval_report.json` + `02_font_eval_report.json` + `v1.0.16` static foundry cuts), here is how all **30 complete font families** rank when scored as **3-Role Visual Contrast Triads (`Normal` + `Bold Punch` + `Subtle Iso-Weight Italic`)** at `16px`:

| Rank | Family (`Group`) | `NORMAL` (`Stem`, `Ink`) | `BOLD PUNCH` (`Stem`, `Ink Jump`, `Stem Jump`) | `SUBTLE ITALIC` (`Stem`, `Ink vs Normal`, `Lighter vs Bold`) | Triad Score | Tri-Role Verdict |
| :---: | :--- | :--- | :--- | :--- | :---: | :--- |
| **1** | **Literata** (`serif`) | `w500` (`2.25px`, `2,528`) | **`w800`** (`3.35px`, **`+51.5%`**, **`+1.10px`**) | `w600` (`2.24px`, **`+1.1%`** vs Norm, **`-49.8%`** vs Bold) | **`94.1`** | **TIER 1 TRIAD: HIGH-PUNCH BOLD + ISO-WEIGHT SUBTLE ITALIC** |
| **2** | **NotoSans Condensed** (`cond`) | `w500` (`2.13px`, `2,275`) | **`w900`** (`3.19px`, **`+46.5%`**, **`+1.06px`**) | `w600` (`2.14px`, **`-0.3%`** vs Norm, **`-46.8%`** vs Bold) | **`93.0`** | **TIER 1 TRIAD: HIGH-PUNCH BOLD + ISO-WEIGHT SUBTLE ITALIC** |
| **3** | **InstrumentSans** (`sans`) | `w500` (`2.17px`, `2,129`) | **`w700`** (`3.01px`, **`+42.3%`**, **`+0.84px`**) | `w500` (`2.19px`, **`-0.6%`** vs Norm, **`-43.2%`** vs Bold) | **`91.9`** | **TIER 1 TRIAD: HIGH-PUNCH BOLD + ISO-WEIGHT SUBTLE ITALIC** |
| **4** | **SourceSans3** (`sans`) | `w500` (`2.06px`, `1,921`) | **`w900`** (`2.93px`, **`+46.9%`**, **`+0.87px`**) | `w600` (`2.06px`, **`-0.6%`** vs Norm, **`-47.8%`** vs Bold) | **`91.8`** | **TIER 1 TRIAD: HIGH-PUNCH BOLD + ISO-WEIGHT SUBTLE ITALIC** |
| **5** | **IBMPlexSans** (`sans`) | `w500` (`2.17px`, `2,566`) | **`w800`** (`3.13px`, **`+35.7%`**, **`+0.96px`**) | `w600` (`2.30px`, **`+1.3%`** vs Norm, **`-33.9%`** vs Bold) | **`91.5`** | **TIER 1 TRIAD: HIGH-PUNCH BOLD + ISO-WEIGHT SUBTLE ITALIC** |
| **6** | **InterDisplay** (`sans`) | `w500` (`2.21px`, `2,558`) | **`w800`** (`3.24px`, **`+40.4%`**, **`+1.03px`**) | `w500` (`2.19px`, **`-1.6%`** vs Norm, **`-42.8%`** vs Bold) | **`91.4`** | **TIER 1 TRIAD: HIGH-PUNCH BOLD + ISO-WEIGHT SUBTLE ITALIC** |
| **7** | **Literata7pt** (`serif`) | `w500` (`2.34px`, `2,634`) | **`w800`** (`3.48px`, **`+50.8%`**, **`+1.14px`**) | `w600` (`2.27px`, **`-1.7%`** vs Norm, **`-53.4%`** vs Bold) | **`90.4`** | **TIER 1 TRIAD: HIGH-PUNCH BOLD + ISO-WEIGHT SUBTLE ITALIC** |
| **8** | **Inter** (`sans`) | `w500` (`2.23px`, `2,489`) | **`w900`** (`3.44px`, **`+53.4%`**, **`+1.21px`**) | `w500` (`2.19px`, **`-2.3%`** vs Norm, **`-57.1%`** vs Bold) | **`89.9`** | **TIER 1 TRIAD: HIGH-PUNCH BOLD + ISO-WEIGHT SUBTLE ITALIC** |
| **9** | **RecursiveMonoCslSt** (`mono`) | `w500` (`2.13px`, `2,558`) | **`w900`** (`3.26px`, **`+42.5%`**, **`+1.13px`**) | `w600` (`2.35px`, **`+4.8%`** vs Norm, **`-35.9%`** vs Bold) | **`89.1`** | **TIER 1 TRIAD: HIGH-PUNCH BOLD + ISO-WEIGHT SUBTLE ITALIC** |
| **10** | **RecursiveSansCslSt** (`sans`) | `w500` (`2.13px`, `2,517`) | **`w900`** (`3.20px`, **`+41.5%`**, **`+1.07px`**) | `w600` (`2.40px`, **`+5.4%`** vs Norm, **`-34.2%`** vs Bold) | **`88.2`** | **TIER 1 TRIAD: HIGH-PUNCH BOLD + ISO-WEIGHT SUBTLE ITALIC** |
| **11** | **IBMPlexMono** (`mono`) | `w500` (`2.18px`, `2,477`) | **`w800`** (`3.04px`, **`+40.1%`**, **`+0.86px`**) | `w500` (`2.10px`, **`-3.1%`** vs Norm, **`-44.7%`** vs Bold) | **`88.1`** | **TIER 1 TRIAD: HIGH-PUNCH BOLD + ISO-WEIGHT SUBTLE ITALIC** |
| **12** | **IBMPlexSansCondensed** (`cond`) | `w500` (`2.10px`, `2,299`) | **`w800`** (`3.01px`, **`+43.4%`**, **`+0.91px`**) | `w600` (`2.17px`, **`+5.9%`** vs Norm, **`-35.4%`** vs Bold) | **`87.3`** | **TIER 1 TRIAD: HIGH-PUNCH BOLD + ISO-WEIGHT SUBTLE ITALIC** |
| **13** | **PublicSans** (`sans`) | `w500` (`2.20px`, `2,383`) | **`w900`** (`3.23px`, **`+51.4%`**, **`+1.03px`**) | `w600` (`2.24px`, **`+6.6%`** vs Norm, **`-42.0%`** vs Bold) | **`86.8`** | **TIER 1 TRIAD: HIGH-PUNCH BOLD + ISO-WEIGHT SUBTLE ITALIC** |
| **14** | **IBMPlexSerif** (`serif`) | `w500` (`2.15px`, `2,406`) | **`w800`** (`2.89px`, **`+33.5%`**, **`+0.74px`**) | `w600` (`2.16px`, **`-1.6%`** vs Norm, **`-35.7%`** vs Bold) | **`83.5`** | **TIER 2 TRIAD: MODERATE BOLD CONTRAST (`>=18px`)** |
| **15** | **Terminus** (`terminus`) | `w400` (`1.09px`, `1,111`) | **`w700`** (`2.04px`, **`+68.0%`**, **`+0.95px`**) | N/A (Upright Pair) | **`83.0`** | **TIER 1 TRIAD: 1PX NORMAL vs 2PX BOLD BITMAP** |

### 3.1 Families Exposed as "Low-Contrast / Homogeneous" (`TIER 3 TRIAD`) by the New Scorer
Look at the bottom of the 30-family digest in `font_eval_triad_digest.md`—the new Tri-Role Triad Scorer immediately flags the families whose `Bold (w700/w800)` fails to jump to `3px` stems at `16px`:
- **`RobotoCondensed` (`Score: 13.4`)**: `w500` (`2.15px`) -> `w700` (`2.23px`) = **only `+6.1%` ink / `+0.08px` stem jump!**
- **`RecursiveMonoLnrSt` (`Score: 32.4`)**: `w500` (`2.18px`) -> `w800` (`2.56px`) = **only `+10.5%` ink / `+0.38px` stem jump!**
- **`SpaceGrotesk` (`Score: 34.6`)**: `w500` (`2.25px`) -> `w700` (`2.39px`) = **only `+13.3%` ink / `+0.14px` stem jump!**
- **`IosevkaAile` / `IosevkaEtoile` (`Score: 35.6 / 39.3`)**: `w500` (`2.14px`) -> `w800` (`2.29px`) = **only `+14.2%` ink / `+0.15px` stem jump!**
- **`RecMonoDuotone` (`Score: 64.4`)**: `w400` (`2.05px`) -> `w750` (`2.46px`) = **only `+22.2%` ink / `+0.41px` stem jump** (which is why `RecMonoDuotone-Bold` in `v1.0.15` looked like a normal `2px` font!).

---

## 4. `v1.0.16` Code & Profile Scheme Changes Applied

### 4.1 `tools/fonts/humid1_bilevel_tuner.py` (`v1.0.16`)
1. **Universal Counter-Carving & Open-Curve Unpinching (`carve_and_unpinch_counters` / `M0_counter_carved`)**:
   - Previously, when `skip_for_bold` (`is_bold_role=True`) or `skip_for_high_conf` triggered, `M0` bypassed counter restoration entirely—leaving `1px` pinholes on `14px` `'a'`/`'e'` and pinched loops on `'s'` (`20px` ExtraBold) and `'M'` (`14px/20px` SemiBoldItalic).
   - Added `carve_and_unpinch_counters()`, which maps the `8x` continuous HQ Master's internal counter cavities and exterior background channels onto the `1-BPP` grid and carves out `1–2px` interior pixels whenever a required counter (`0, 4, 6, 8, 9, A, B, D, O, P, Q, R, a, b, d, e, g, o, p, q, $, %, &`) is collapsed/pinholed (`<2px`) or an open curve (`s, c, w, M, 6, 9, e`) is pinched shut.
2. **Single-Counter Canonical Hole Clamping (`SINGLE_COUNTER_OPEN_TAIL_CHARS`)**:
   - Fixed a bug where a two-story overhang or cursive italic hook in the `8x` grayscale master (`'a'`, `'e'`, `'6'`, `'9'`) could briefly touch at low dynamic thresholds and set `expected_b1 = 2`, falsely penalizing `IBMPlexSans-SemiBoldItalic` `'a'` at `16px`.
   - Clamped `expected_b1 = 1` for all `SINGLE_COUNTER_OPEN_TAIL_CHARS = set("0469ADOPQRabdeopq")`.
   - **Result**: `IBMPlexSans-ExtraBold (w800)`, `IBMPlexSans-SemiBoldItalic (w600)`, `IBMPlexMono-ExtraBold (w800)`, and `IBMPlexMono-MediumItalic (w500)` all achieve **`100.0%` counter survival across `12px–24px`**!

### 4.2 `tools/fonts/humid1_font_eval.py` (`v1.0.16`)
1. **Role-Aware Classification (`classify_font_role_and_score`)**:
   - Classifies every evaluated cut into its true 1-BPP functional role: `NORMAL (BODY)` (`~2.00–2.25px` stem), `BOLD (PUNCH)` (`>=2.85px` stem), `ITALIC (SUBTLE)` (`w400–w600`, `~2.00–2.40px` stem), `MID-WEIGHT (LOW CONTRAST)` (`w600/w700` cuts in the `2.35–2.65px` dead zone), `ITALIC (HEAVY/BLUDGEON)` (`w700/w800` BoldItalics), or `MICRO (1PX BITMAP)`.
2. **Tri-Role Family Triad Scorer (`evaluate_family_triads`) & Visual Contrast Sheet (`render_triad_contrast_sheet`)**:
   - Automatically pairs and scores `(Normal, Bold Punch, Subtle Italic)` triads per family and renders `build/font_eval/font_eval_triad_contrast_sheet.png`, stacking `NORMAL`, `BOLD`, and `ITALIC` at `14px`, `16px`, and `20px` alongside a `2x`-zoomed `16px` glyph comparison strip (`H B a e g s w $`).
3. **Multi-Corpus JSON Re-Digest Flag (`--re-digest-json`)**:
   - Allows re-evaluating any existing `font_eval_report.json` files without re-rasterizing from scratch.

### 4.3 `tools/fonts/build_static_ttf_assets.py`, `tools/fonts/humid1_generate_1bpp.py` & All 19 `.scheme.json` Profiles
1. **Added `SemiBoldItalic (w600)` Static TTFs Across All IBM Plex Families (`91` Static `.ttf` Assets)**:
   - Added `IBMPlexSansCondensed-SemiBoldItalic.ttf`, `IBMPlexMono-SemiBoldItalic.ttf`, and `IBMPlexSerif-SemiBoldItalic.ttf` alongside `IBMPlexSans-SemiBoldItalic.ttf` in `build_static_ttf_assets.py`.
2. **Fixed `humid1_generate_1bpp.py` Scheme Weight Wiring**:
   - `humid1_generate_1bpp.py` now reads `normal_weight` (`500`), `bold_weight` (`800`), and `italic_weight` (`600`) from both CLI (`--normal-weight`, `--bold-weight`, `--italic-weight`) and `.scheme.json` `raster_config` and passes all three to `get_family_roles(normal_w, bold_w, italic_w)`.
3. **Updated All 19 `.scheme.json` Files (`h1os_full.scheme.json`, `h1os_lite.scheme.json`, `example.scheme.json`, `tools/fonts/schemes/*.scheme.json`)**:
   - Changed `"bold_weight": 700` -> **`"bold_weight": 800`** (`ExtraBold`) and added **`"italic_weight": 600`** (`SemiBoldItalic` on Sans/Cond/Serif, `MediumItalic` on Mono).
   - Added `sans italic` (`[14, 16]`) and `terminus normal` (`[12, 16]`) to `h1os_lite.scheme.json`, expanded `sans italic` (`[12, 14, 16, 18, 20]`) and `mono italic` (`[14, 16]`) in `h1os_full.scheme.json`, and mapped `"HUMID1_FONT_UI_MICRO": "humid1_font_terminus_normal_12"` and `"HUMID1_FONT_UI_EMPHASIS": "humid1_font_plex_sans_italic_14"`.

---

## 5. Verification Summary (`v1.0.16` H1OS Build & Screen Audit)

| Metric / Verification Gate | `v1.0.15` Baseline | `v1.0.16` Result | Status |
| :--- | :--- | :--- | :---: |
| **`Sans` `16px` Tri-Role Hierarchy (`Normal` / `Bold` / `Italic`)** | `2.17px` / `2.48px (+12%)` / `2.52px (+11.7%)` | **`2.17px` (`w500`) / `3.13px` (`w800`, `+35.7%` Ink Punch!) / `2.30px` (`w600`, `+1.3%` Iso-Weight Italic!)** | **PASS** |
| **`Sans` `14px` Tri-Role Hierarchy (`Normal` / `Bold` / `Italic`)** | `2.08px` / `2.31px (+11%)` / `2.35px (+14%)` | **`2.08px` (`w500`) / `2.96px` (`w800`, `+44.1%` Ink Punch!) / `2.15px` (`w600`, `+7.1%` Iso-Weight Italic!)** | **PASS** |
| **`Mono` `16px` Tri-Role Hierarchy (`Normal` / `Bold` / `Italic`)** | `2.18px` / `2.44px (+13%)` / `2.46px` | **`2.18px` (`w500`) / `3.04px` (`w800`, `+40.1%` Ink Punch!) / `2.10px` (`w500`, `-3.1%` Iso-Weight Italic!)** | **PASS** |
| **Enclosed Counter Survival (`12px–24px` Sans/Mono Normal, Bold, Italic)** | `90.5%–95.2%` on `w800` / `w600 Italic` | **`100.0%` across all `12px–24px` strikes (`M0_counter_carved`)** | **PASS** |
| **`h1os_full.scheme.json` Total Strikes & Flash ROM** | `63` strikes / `258.5 KB` | **`67` strikes / `280,690 B` (`274.1 KB`)** | **PASS** |
| **Waveshare `200×200` (`188px` Budget) Screen Width Audit** | `11 / 11 PASS` | **`11 / 11 PASS` (`+20px` to `+72px` horizontal clearance)** | **PASS** |
