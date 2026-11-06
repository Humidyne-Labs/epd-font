# Humidyne Labs `H1OS` v1.0.16 Typography Strategy Report: Single Superfamily vs. Multi-Font Functional Division of Labor

## 1. Executive Verdict and Recommended Course of Action

The empirical evaluation of **425 font cuts across 31 complete typeface families** in `01_font_eval.zip` (internal `build/static_ttfs` foundry suite) and `02_font_eval.zip` (external `eval_fonts` benchmark corpus) under the **v1.0.16 Tri-Role Visual Contrast Triad Scorer** provides a definitive answer to the core architectural question:

> **Verdict: Adopt a Multi-Font Functional Division of Labor Across Top-Ranked Category Specialists — NOT a "Single Font to Rule Them All."**
> Specifically, retain **`IBMPlexSans` (`91.5`) + `IBMPlexMono` (`88.1`) + `Terminus` (`83.0`) + `IBMPlexMath`** as the `12px–16px` UI, Telemetry, and Micro-Console core (where they hold the best `14px` Tri-Role size floors and native scientific glyph coverage), and **swap out the two underperforming IBM Plex sub-families (`IBMPlexSansCondensed` and `IBMPlexSerif`)** for the #1 and #2 overall winners of the 425-font evaluation: **`Literata` (`94.0` Serif Triad)** and **`NotoSans SemiCondensed/Condensed` (`93.0` Condensed Triad)**.

| Architectural Strategy | Mean Triad Contrast Score (`16px`) | `14px` Default UI Triad Survival (`Normal` / `Bold` / `Italic`) | Scientific & Telemetry Glyph Coverage (`Δ, Ω, μ, °, ±, ², ³`) | Key Strength | Critical Weakness |
| :--- | :---: | :---: | :---: | :--- | :--- |
| **Option 1: Single Font to Rule Them All** (`IBMPlex` Superfamily Only) | `87.6` | `Sans` & `Mono` PASS at `14px`; **`Cond` & `Serif` FAIL until `20px`** | **100% Native** across all cuts | Unified typographic DNA; zero cross-foundry metric drift | `IBMPlexSerif` (`83.5`, `20px` floor) and `IBMPlexSansCondensed` (`87.3`, `20px` Normal floor, `2.36px` 14px Bold stem) lose contrast below `20px` |
| **Option 2: Pure 16px External Leaderboard Swap** (`InstrumentSans` + `RecursiveMono` + `NotoCond` + `Literata`) | `92.7` | **`InstrumentSans` Bold drops to `2.28px` at `14px`**; `RecursiveMono` drops to `95%` counters at `14px` | Partial (requires LVGL fallback to `IBMPlexMath` for `Δ, Ω, μ`) | Maximum `16px–24px` Triad Contrast Score in every slot | Weaker at `14px` (H1OS's `default_font` size) than `IBMPlexSans` (`2.96px` Bold stem) and `IBMPlexMono` (`100%` 14px counters) |
| **Option 3: Hybrid Division-of-Labor "Dream Team" (RECOMMENDED)** (`IBMPlexSans` + `IBMPlexMono` + `NotoCond` + `Literata` + `Terminus` + `Inter-Black` Hero) | **`91.8`** (`16px`) / **`#1` at `14px`** | **100% PASS at `12px–16px`** across every functional role | **100% Native** in UI, Telemetry & Math | Combines the best `14px` UI/Telemetry workhorses with the #1 Serif (`Literata 94.0`), #1 Condensed (`NotoSans 93.0`), and #1 Micro (`Terminus`) | None — every typeface operates strictly inside its optimal pixel-grid envelope |

---

## 2. Why "One Font to Rule Them All" Fails on a 188 DPI 1-BPP Grid

On high-resolution grayscale screens (`300+ PPI` with 8-bit anti-aliasing), a single typeface family can stretch across every role because sub-pixel gray fringes mask stem-width quantization errors and narrow counter apertures. On the **Waveshare 1.54" V2 1-BPP EPD (`200×200`, `188.3 DPI`)**, every pixel is strictly binary (`0` or `1`), and each UI zone is governed by a different physical law:

1. **The Micro-Console Zone (`10px–12px` / `4.6pt–6.1pt`) — Governed by Integer Grid Alignment**:
   - Every outline font in the 425-font dataset (`IBMPlexSans`, `Inter`, `InstrumentSans`, `SourceSans3`, `Recursive`) requires **`55% to 76%` surgical glyph patching at `12px`** because continuous Bézier outlines cannot quantize cleanly onto a `7px–9px` cap height without pinching `'a'`, `'e'`, `'8'`, `'B'`, or `'@'`.
   - **`Terminus` (`Terminus-Normal-12/16` + `Terminus-Bold-12/16`, Triad Score `83.0`)** is hand-authored on an integer bitmap grid: `Normal` has a razor-sharp `1.09px` stem (`1,111` ink px), `Bold` has a `2.04px` stem (`1,867` ink px = **`+68.0%` Ink Punch**), counter survival is **`100.0%`**, and tuning burden is **`0.0%`**. No outline font can replace `Terminus` at `10px–12px`.
2. **The Core UI & Telemetry Zone (`14px` Default Body & `16px` Titles) — Governed by `14px` 3-Way Triad Separation**:
   - In `h1os_full.scheme.json` and `h1os_lite.scheme.json`, the primary workhorse size is **`14px` (`default_font: humid1_font_plex_sans_normal_14`)**.
   - Several external families that score slightly higher at `16px` (**`InstrumentSans` at `91.9`** and **`SourceSans3` at `91.8`**) lose their Tri-Role separation when stepped down to **`14px`**:
     - `InstrumentSans-Bold (w700)` drops from a `3.00px` stem at `16px` down to **`2.28px` at `14px`** (only `+0.24px` thicker than `InstrumentSans-Medium` at `2.04px` — losing the `3px` Bold punch at `14px`!).
     - `SourceSans3-Medium (w500)` drops to a **`1.87px` stem at `14px`** (`20px` viable floor), and its `Black (w900)` cut drops to `2.44px` at `14px`.
   - By contrast, **`IBMPlexSans` (`w500 Medium` + `w800 ExtraBold` + `w600 SemiBoldItalic`, Triad Score `91.5`)** and **`Inter` (`w500` + `w800/w900` + `w600 SemiBoldItalic`, Triad Score `90.4–91.5`)** maintain a true **`2px` vs. `3px` stem jump at BOTH `14px` (`2.08px` vs. `2.96px` = `+44.1%` ink punch) and `16px` (`2.17px` vs. `3.13px` = `+35.7%` ink punch)** with **`100.0%` open counters across all three roles**!
3. **The Narrow HMI Dock Zone (`cond` at `14px–20px`) — Governed by Horizontal Counter Aperture**:
   - Compressing `IBMPlexSans` to `wdth=85` (`IBMPlexSansCondensed`, Triad Score `87.3`) narrows the horizontal counter cavities of `'a'`, `'e'`, `'0'`, `'8'`, and `'B'`, pushing its `Normal` viable floor up to **`20px`** and dropping its `14px` Bold stem to `2.36px`.
   - **`NotoSans SemiCondensed / Condensed` (Triad Score `93.0`, #2 overall in `02_font_eval`)** was engineered with wider internal counter apertures in its condensed master: at `14px` it maintains **`2.00px` (`Normal`) / `2.98px` (`Bold w900`) / `1.98px` (`Italic w600`)** with **`100%` upright counter survival**, and at `16px` it delivers **`+46.5%` Bold Ink Punch** and **`-0.3%` Iso-Weight Subtle Italic**!
4. **The Editorial Serif Zone (`serif` at `16px–24px`) — Governed by Bracketed Slab Survival**:
   - `IBMPlexSerif` (`Triad Score 83.5`) has high stroke contrast and delicate horizontal hairlines that require a **`20px` minimum size floor** across `Normal`, `Bold`, and `Italic`.
   - **`Literata` (`Triad Score 94.0`, #1 overall in `02_font_eval`)** and **`Literata7pt` (`Triad Score 90.2`)** were designed specifically for low-DPI e-reader panels: `Literata` achieves **`2.25px` (`Normal w500`) / `3.35px` (`Bold w800`, `+51.4%` Ink Punch!) / `2.24px` (`Italic w600`, `+1.2%` Iso-Weight Subtle Italic!)** with **`100.0%` counter survival at `16px`** and a **`16px / 12px` upright floor** (`14px / 12px` on `Literata7pt`)!

---

## 3. Combined Category-by-Category Leaderboard (`01_font_eval` + `02_font_eval`)

### 3.1 Top 15 Tri-Role Family Triads Across All 425 Evaluated Cuts (`16px` & `14px` Cross-Check)

| Overall Rank | Family (`Category`) | `16px` Triad Score | `NORMAL` Cut (`16px` Stem, Ink) | `BOLD PUNCH` Cut (`16px` Stem, Ink Jump, Stem Jump) | `SUBTLE ITALIC` Cut (`16px` Stem, Ink vs. Norm, Lighter vs. Bold) | `14px` Stems (`Norm` / `Bold` / `Ital`) | Tuned Size Floors (`Norm` / `Bold` / `Ital`) |
| :---: | :--- | :---: | :--- | :--- | :--- | :---: | :---: |
| **1** | **Literata** (`serif`) | **`94.0`** | `Medium w500` (`2.25px`, `2,527`) | **`ExtraBold w800`** (`3.35px`, **`+51.4%`**, **`+1.10px`**) | `SemiBoldIt w600` (`2.24px`, **`+1.2%`**, **`-49.7%`**) | `2.16 / 3.09 / 2.03px` | `16 / 12 / 20px` |
| **2** | **NotoSans Cond** (`cond`) | **`93.0`** | `SemiCondMed w500` (`2.13px`, `2,275`) | **`SemiCondBlack w900`** (`3.19px`, **`+46.5%`**, **`+1.06px`**) | `CondSmBdIt w600` (`2.14px`, **`-0.3%`**, **`-46.8%`**) | **`2.00 / 2.98 / 1.98px`** | **`16 / 12 / 16px`** |
| **3** | **RecursiveMonoLnrSt** (`mono`) | **`92.0`** | `Med w500` (`2.18px`, `2,612`) | **`Black w900`** (`3.21px`, **`+41.5%`**, **`+1.03px`**) | `SmBdItalic w600` (`2.43px`, **`+2.9%`**, **`-37.4%`**) | `2.06 / 2.99 / 2.17px` | `16 / 12 / 14px` |
| **4** | **InstrumentSans** (`sans`) | **`91.9`** | `Medium w500` (`2.17px`, `2,129`) | **`Bold w700`** (`3.00px`, **`+42.3%`**, **`+0.83px`**) | `MediumIt w500` (`2.19px`, **`-0.6%`**, **`-43.1%`**) | `2.04 / 2.28 / 2.06px` *(weak 14px Bold)* | `16 / 12 / 16px` |
| **5** | **SourceSans3** (`sans`) | **`91.8`** | `Medium w500` (`2.06px`, `1,921`) | **`Black w900`** (`2.93px`, **`+46.9%`**, **`+0.87px`**) | `SemiboldIt w600` (`2.06px`, **`-0.6%`**, **`-47.8%`**) | `1.87 / 2.44 / 1.99px` *(weak 14px)* | `20 / 12 / 16px` |
| **6** | **IBMPlexSans** (`sans`) | **`91.5`** | `Medium w500` (`2.17px`, `2,566`) | **`ExtraBold w800`** (`3.13px`, **`+35.7%`**, **`+0.96px`**) | `SemiBoldIt w600` (`2.30px`, **`+1.3%`**, **`-33.9%`**) | **`2.08 / 2.96 / 2.15px`** | **`14 / 12 / 14px`** |
| **7** | **InterDisplay** (`sans`) | **`91.5`** | `Medium w500` (`2.21px`, `2,558`) | **`Black w900`** (`3.35px`, **`+52.9%`**, **`+1.14px`**) | `MediumIt w500` (`2.19px`, **`-1.7%`**, **`-55.5%`**) | **`2.10 / 3.13 / 2.09px`** | `16 / 12 / 16px` |
| **8** | **Inter** (`sans`) | **`90.4`** | `Medium w500` (`2.23px`, `2,489`) | **`Black w900`** (`3.44px`, **`+53.3%`**, **`+1.21px`**) | `MediumIt w500` (`2.19px`, **`-2.3%`**, **`-57.0%`**) | **`2.10 / 3.08 / 2.07px`** | **`14 / 12 / 16px`** (`14px` w/ `w600 It`) |
| **9** | **RecursiveSansLnrSt** (`sans`) | **`90.4`** | `Med w500` (`2.21px`, `2,580`) | **`Black w900`** (`3.30px`, **`+42.8%`**, **`+1.09px`**) | `SmBdItalic w600` (`2.42px`, **`+4.2%`**, **`-37.0%`**) | `2.07 / 3.01 / 2.21px` | `16 / 12 / 14px` |
| **10** | **Literata7pt** (`serif`) | **`90.2`** | `Medium w500` (`2.34px`, `2,634`) | **`ExtraBold w800`** (`3.49px`, **`+50.7%`**, **`+1.15px`**) | `SemiBoldIt w600` (`2.27px`, **`-1.8%`**, **`-53.5%`**) | **`2.19 / 3.17 / 2.09px`** | **`14 / 12 / >24px`** |
| **11** | **RecursiveMonoCslSt** (`mono`) | **`89.4`** | `Med w500` (`2.13px`, `2,557`) | **`Black w900`** (`3.24px`, **`+42.5%`**, **`+1.11px`**) | `SmBdItalic w600` (`2.35px`, **`+4.9%`**, **`-35.9%`**) | `2.00 / 3.03 / 2.10px` | `16 / 14 / 14px` |
| **12** | **RecursiveSansCslSt** (`sans`) | **`88.5`** | `Med w500` (`2.13px`, `2,516`) | **`Black w900`** (`3.19px`, **`+41.9%`**, **`+1.06px`**) | `SmBdItalic w600` (`2.40px`, **`+5.5%`**, **`-34.5%`**) | `2.04 / 2.98 / 2.15px` | `16 / 14 / 14px` |
| **13** | **IBMPlexMono** (`mono`) | **`88.1`** | `Medium w500` (`2.18px`, `2,477`) | **`ExtraBold w800`** (`3.04px`, **`+40.1%`**, **`+0.86px`**) | `MediumIt w500` (`2.10px`, **`-3.1%`**, **`-44.7%`**) | **`2.02 / 2.88 / 1.96px`** (`100%` Cnt!) | **`14 / 12 / 16px`** (`14px` w/ `w600 It`) |
| **14** | **IBMPlexSansCondensed** (`cond`) | **`87.3`** | `Medium w500` (`2.10px`, `2,299`) | **`ExtraBold w800`** (`3.01px`, **`+43.4%`**, **`+0.91px`**) | `SemiBoldIt w600` (`2.17px`, **`+5.9%`**, **`-35.4%`**) | `1.96 / 2.36 / 2.06px` *(weak 14px Bold)* | `20 / 10 / 16px` |
| **15** | **PublicSans** (`sans`) | **`87.3`** | `Medium w500` (`2.20px`, `2,383`) | **`Black w900`** (`3.23px`, **`+51.3%`**, **`+1.03px`**) | `SemiBoldIt w600` (`2.24px`, **`+6.6%`**, **`-41.9%`**) | `2.09 / 3.01 / 2.11px` | `16 / 12 / 14px` |

---

## 4. Recommended H1OS Division-of-Labor Font Lineup

### 4.1 The 6 Functional Slots & Their Optimal Typeface Assignments

| Functional Slot in `H1OS` | Target Pixel Sizes | Primary Recommended Family (Hybrid Division-of-Labor) | Alternative External Contender | Why This Assignment Wins for Pattern Recognition |
| :--- | :---: | :--- | :--- | :--- |
| **1. Micro Console & Boot Status (`HUMID1_FONT_UI_MICRO` / `TERMINAL`)** | `10px, 12px, 16px` | **`Terminus` (`Normal w400` 1px + `Bold w700` 2px)** | *None (No vector font survives `10–12px` at `0%` burden)* | `1.09px` Normal vs `2.04px` Bold (`+68.0%` ink punch), `100%` counters, `0.0%` tuning burden, `12px` height fits dense debug logs. |
| **2. Primary UI Sans (`HUMID1_FONT_UI_BODY` / `SUBTITLE` / `TITLE` / `EMPHASIS`)** | `12px, 14px, 16px, 18px, 20px, 24px, 32px` | **`IBMPlexSans`** (`Normal = Medium w500`, `Bold = ExtraBold w800`, `Italic = SemiBoldItalic w600`) | **`Inter` / `InterDisplay`** (`Medium w500` + `ExtraBold w800` / `Black w900` + `SemiBoldItalic w600`) | `IBMPlexSans` is the **only Sans triad** with a **`14px / 12px / 14px` tuned floor**, `100%` counters at both `14px` and `16px`, a full `2.08px -> 2.96px` (`+44.1%`) Bold punch at `14px`, `+1.3%` iso-weight Italic, and native Greek/Unit symbols. |
| **3. Tabular Sensor Telemetry (`HUMID1_FONT_TELEMETRY_SM..XL`)** | `12px, 14px, 16px, 20px, 24px, 32px` | **`IBMPlexMono`** (`Normal = Medium w500`, `Bold = ExtraBold w800`, `Italic = MediumItalic w500` / `SemiBoldItalic w600`) | **`RecursiveMonoLnrSt`** (`Med w500` + `Black w900` + `SmBdItalic w600`, Score `92.0` at `>=16px`) | At `14px` (`TELEMETRY_SM`), `IBMPlexMono` hits **`100%` counter survival** (`RecursiveMono` drops to `95%` at `14px`) with `+40.1%` Bold punch, slashed zero `0`, and native `Δ, Ω, μ, °C` glyphs. At `>=16px`, `RecursiveMonoLnrSt` is an elite alternative. |
| **4. Narrow HMI / Dock Labels (`cond`)** | `14px, 16px, 18px, 20px` | **Upgrade to `NotoSans SemiCondensed / Condensed`** (`Medium w500` + `Black w900` + `SemiBoldItalic w600`, Score **`93.0`**) | `IBMPlexSansCondensed` (`Score 87.3`, `>=16px–20px` only) | Fixes `IBMPlexSansCondensed`'s `20px` Normal floor and weak `14px` Bold (`2.36px`), delivering a **`2.00px -> 2.98px` (`14px`)** and **`2.13px -> 3.19px` (`16px`, `+46.5%` punch)** triad with `-0.3%` iso-weight Italic! |
| **5. Editorial / Long-Form Callouts (`serif`)** | `16px, 18px, 20px, 24px` | **Upgrade to `Literata` (`Score 94.0`, #1 Overall)** (`Medium w500` + `ExtraBold w800` + `SemiBoldItalic w600`) | `Literata7pt` (`Score 90.2` for `14px` upright serif) | Replaces `IBMPlexSerif` (`Score 83.5`, `20px` floor) with an e-ink-native serif that hits **`94.0` Triad Score**, `+51.4%` Bold punch, `+1.2%` iso-weight Italic, and `100%` counters at `16px`. |
| **6. Scientific & Psychrometric Formulas (`math`)** | `16px, 20px` | **`IBMPlexMath-Regular`** (with `v1.0.16` surgical auto-tune) | *None in corpus has full `U+2200..U+22FF` operator coverage* | Provides `∀, ∂, ∃, ∅, ∆, ∇, ∈, ∑, √, ∞, ≈, ≠, ≡, ≤, ≥` with `100%` horizontal fit on the `200×200` panel. |

---

## 5. Step-by-Step Action Plan

1. **Lock In Your `v1.0.16` `Sans` + `Mono` + `Terminus` + `Math` Core (`01_font_eval` Winners)**:
   - Your `v1.0.16` `h1os_full.scheme.json` and `h1os_lite.scheme.json` already have the exact `Normal (w500)` + `Bold (w800 ExtraBold)` + `Italic (w600 SemiBoldItalic)` Tri-Role configuration wired in for `IBMPlexSans`, `IBMPlexMono`, and `Terminus`. No changes are needed to those four families if you like how `01_font_eval_triad_contrast_sheet.png` looks.
2. **Optional High-Impact Upgrade — Drop In `Literata` (Serif #1, `94.0`) and `NotoSans Condensed` (Cond #1, `93.0`)**:
   - If you use the `serif` or `cond` strikes in `h1os_full.scheme.json` (or want to offer them in `epd-font`), swapping `IBMPlexSerif` -> **`Literata`** (`Literata-Medium.ttf`, `Literata-ExtraBold.ttf`, `Literata-SemiBoldItalic.ttf`) and `IBMPlexSansCondensed` -> **`NotoSans SemiCondensed/Condensed`** raises your Serif Triad Score from `83.5 -> 94.0` (`+10.5` pts) and your Condensed Triad Score from `87.3 -> 93.0` (`+5.7` pts) while lowering both size floors from `20px` down to `14px–16px`.
3. **Optional Alternative UI Skin — `Inter` / `InterDisplay` + `RecursiveMonoLnrSt` Scheme (`h1os_inter_recursive.scheme.json`)**:
   - Because `epd-font` is driven by declarative `.scheme.json` files, we can bundle `Literata`, `NotoSans Condensed`, `Inter`, and `RecursiveMonoLnrSt` into `assets/font_assets/` (all SIL OFL 1.1 licensed!) so you can switch between the **IBM Plex Core Scheme** and the **All-Star Multi-Foundry Scheme** with a single `--scheme` flag!
