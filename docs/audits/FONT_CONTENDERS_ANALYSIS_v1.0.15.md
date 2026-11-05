# Humidyne Labs / Humiditron `epd-font` v1.0.15 — 408-Font Contender Analysis & Head-to-Head Comparison vs. IBM Plex

- **Repository**: [`https://github.com/Humidyne-Labs/epd-font`](https://github.com/Humidyne-Labs/epd-font)
- **Target OS**: [`https://github.com/Humidyne-Labs/H1OS`](https://github.com/Humidyne-Labs/H1OS)
- **Version**: `v1.0.15`
- **Source Datasets**:
  - `docs/audits/exhibits/v1.0.15/batch_01/font_eval_report.json` (`15` internal IBM Plex & Terminus cuts + `SemiBold w600` & `BoldItalic w700` added in `v1.0.15`)
  - `docs/audits/exhibits/v1.0.15/batch_02/font_eval_report.json` (`408` external font cuts across `30` typefaces: `Inter`, `InterDisplay`, `InstrumentSans`, `NotoSans`, `PublicSans`, `Roboto`, `RobotoCondensed`, `SourceSans3`, `SpaceGrotesk`, `RecursiveSans*`, `RecursiveMono*`, `RecMono*`, `IosevkaAile`, `IosevkaEtoile`, `Literata*`, `SourceSerif4*`)
- **Target Hardware**: Waveshare 1.54" V2 1-BPP Monochrome E-Paper Display (SSD1681, `200x200` px @ `188.3 DPI`)

---

## 1. Executive Summary: What 425 Evaluated Font Cuts Reveal About 1-BPP E-Paper Typography

Across all **425 evaluated font cuts** (`408` in `batch_02` + `17` in `batch_01`) tested at `[12, 14, 16, 20, 24]` px (`9pt..18pt`), three physical laws govern 1-BPP legibility on a `188.3 DPI` monochrome display:

1. **The `w400` Hairline Law (Why Strict `Regular 400` Outline Fonts Fail Below `20px`)**:
   - Out of all `408` external font cuts in `batch_02`, **zero (`0`) strict `w400 Regular` outline fonts achieved a `14px` or `16px` viable size floor**. At `14px–16px`, `w400` vertical stems quantize to `1px` hairlines (`3.3%–16.7%` `>=2px` stem survival), requiring `65%–78%` artificial pixel thickening (`TIER 3: HIGH TUNE BURDEN`).
   - By contrast, stepping the **Normal / Standard UI role** up to **`SemiBold (w600)`** or **`Medium (w500)`** naturally places vertical and curved stems above the `2.0px` physical grid threshold (`85.0%–96.7%` `>=2px` stem survival out of the box), dropping the viable size floor to **`12px–14px`** and slashing the tuning burden to **`0.0%–6.7%`**!
2. **The `w700` vs. `w800` Counter-Aperture Law for Bold UI (`12px–14px` vs. `>=16px`)**:
   - At `>=16px` (`12pt+`), **`ExtraBold (w800)`** cuts (`InterDisplay-ExtraBold`, `IBMPlexSans-ExtraBold`, `PublicSans-ExtraBold`) achieve the highest raw structural confidence (`82.5%–84.0%` HQ IoU) with thick `3.1px` stems.
   - However, at compact sizes (`12px–14px` / `9pt–10.5pt`), `w800–w900` strokes can pinch lowercase `'a'`, `'e'`, and `'s'` counters shut, whereas well-proportioned **`Bold (w700)`** cuts (`Inter-Bold`, `NotoSans-Bold`, `RecMonoDuotone-Bold`) maintain **`100.0%` open counters all the way down to `12px–14px`** with **`0.0%` tuning burden**!
3. **The Slanted Staircase Law for Italic UI (Why `BoldItalic w700` / `SemiBoldItalic w600` Beats `MediumItalic w500`)**:
   - On a 1-BPP grid without grayscale anti-aliasing, a `9°–12°` italic slant fragments `w400–w500` diagonal stems into `1px` stair-steps (`IBMPlexSans-MediumItalic w500` only achieves `15.0%` `>=2px` stems at `14px` and `60.0%` at `16px`, pushing its floor to `24px`).
   - Stepping the **Italic role** up to **`BoldItalic (w700)`** or **`ExtraBoldItalic (w800)`** (or **`SemiBoldItalic w600`** in `RecursiveSans`) keeps diagonal stems `>=2px` wide across scanlines (`93.3%–96.7%` survival at `14px–16px`), dropping the Italic size floor from `24px` down to **`14px`** with only **`1.7%–5.0%` tuning burden**!

---

## 2. Top 3 Contenders for **Standard / Regular UI (`normal` Role)** vs. IBM Plex

Because "Regular" in UI design refers both to the **Standard Body Text Role (`normal`)** (best served by `w500 Medium` / `w600 SemiBold` on 1-BPP e-paper) and to **Strict `w400 Regular` Cuts**, we present the Top 3 winners in both categories alongside the **IBM Plex** baseline:

### 2.1 Top 3 Contenders for the Standard UI Role (`w500 Medium` / `w600 SemiBold` — Recommended for 188 DPI EPD)

| Rank / Role | Typeface & Cut | `wght` | Raw -> Tuned Floor | `14px` Raw HQ Conf | `14px` Raw `>=2px` Stems | `14px` Raw Counters | `16px` HQ Conf (`Raw -> Tuned`) | `16px` `>=2px` Stems (`Raw -> Tuned`) | `16px` Counters | `16px` Tuning Burden | Composite Score |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Contender #1 (Overall Winner)** | **`Inter-SemiBold`** (`Inter-SemiBold.ttf`) | `600` | **`14px -> 12px`** | **`76.4%`** | **`90.0%`** | **`100.0%`** | **`80.6% -> 80.6%`** | `95.0% -> 96.7%` | **`100.0%`** | **`1/60 (1.7%)`** | **`129.5`** |
| **Contender #2 (Zero-Tune Winner)** | **`InstrumentSans-SemiBold`** (`InstrumentSans-SemiBold.ttf`) | `600` | **`14px -> 14px`** | `75.5%` | **`90.0%`** | **`100.0%`** | `77.7% -> 77.7%` | **`96.7% -> 96.7%`** | **`100.0%`** | **`0/60 (0.0%)`** | **`125.8`** |
| **Contender #3 (Technical UI & Mono)** | **`RecursiveSansLnrSt-SemiBold`** (`RecursiveSansLnrSt-SemiBold.ttf`) | `600` | **`14px -> 14px`** | `76.0%` | **`90.0%`** | `95.2%` | **`80.8% -> 80.8%`** | `95.0% -> 96.7%` | `95.0%` | **`1/60 (1.7%)`** | **`125.5`** |
| **Best Pure `w500` Medium Cut** | **`Roboto-Medium`** / **`RobotoCondensed-Medium`** | `500` | **`16px -> 14px`** | `76.1%` | `80.0%` | **`100.0%`** | `79.5% -> 79.6%` | `90.0% -> 96.7%` | **`100.0%`** | `6/60 (10.0%)` | `118.0` |
| **IBM Plex Baseline (`w600`)** | **`IBMPlexSans-SemiBold`** (`IBMPlexSans-SemiBold.ttf`) | `600` | **`14px -> 14px`** | **`76.5%`** | **`90.0%`** | `95.2%` | **`78.7% -> 79.1%`** | `95.0% -> 98.3%` | **`100.0%`** | `4/60 (6.7%)` | **`124.6`** |
| **IBM Plex Baseline (`w500` Current)** | **`IBMPlexSans-Medium`** (`IBMPlexSans-Medium.ttf`) | `500` | `16px -> 16px` | `69.4%` | `78.3%` | `90.5%` | `74.4% -> 75.1%` | `85.0% -> 91.7%` | **`100.0%`** | `7/60 (11.7%)` | `109.8` |
| **Micro-Size Pixel Champion (`<=12px`)** | **`Terminus-Normal-12..16`** (`Terminus-Normal-16.ttf`) | `400` | **`12px -> 12px`** | **`100.0%`** | **`100.0%`** | **`100.0%`** | **`100.0% -> 100.0%`** | **`100.0% -> 100.0%`** | **`100.0%`** | **`0/60 (0.0%)`** | **`148.0`** |

### 2.2 Top 3 Contenders for Strict `w400 Regular` Outline Fonts (Why `w400` Requires `>=20px` on 1-BPP EPD)

| Rank | Typeface & Cut | `wght` | Raw -> Tuned Floor | `16px` Raw HQ Conf | `16px` Raw `>=2px` Stems | `16px` Counters | `16px` Tuning Burden | Why It Outperformed Other `w400` Cuts |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **#1 Strict `w400`** | **`Literata7pt-Regular`** (`Literata7pt-Regular.ttf`) | `400` | `20px -> 20px` | `67.7% -> 69.0%` | **`70.0% -> 90.0%`** | **`100.0%`** | `12/60 (20.0%)` | Optical `7pt` micro-cut engineered with stout low-contrast serifs and thicker hairlines (`70%` native `>=2px` stems at 16px vs. `<15%` for standard `w400` cuts) |
| **#2 Strict `w400`** | **`RecMonoDuotone-Regular-1.085`** (`RecMonoDuotone-Regular-1.085.ttf`) | `400` | `20px -> 20px` | `66.1% -> 74.0%` | `11.7% -> 86.7%` | `95.0%` | `43/60 (71.7%)` | Wide monospace cell (`600 upem`) keeps counters open at `12px–16px`, though stems are still `1px` without tuning |
| **#3 Strict `w400`** | **`RecursiveSansLnrSt-Regular`** (`RecursiveSansLnrSt-Regular.ttf`) | `400` | `20px -> 20px` | `65.7% -> 73.4%` | `10.0% -> 83.3%` | `95.0%` | `45/60 (75.0%)` | Clean linear geometry with open counters (`95%`), but still requires `75%` stem tuning below `20px` |
| **IBM Plex `w400`** | **`IBMPlexSans-Regular`** (`IBMPlexSans-Regular.ttf`) | `400` | `24px -> 24px` | `62.5% -> 68.7%` | `6.7% -> 63.3%` | **`100.0%`** | `47/60 (78.3%)` | Designed for high-DPI print/LCD; `93.3%` of stems at `16px` are `1px` hairlines |

- **Head-to-Head Verdict (`Normal` Role vs. IBM Plex)**:
  - **`Inter-SemiBold (w600)`** (`Score: 129.5`) and **`InstrumentSans-SemiBold (w600)`** (`Score: 125.8`, **`0.0%` tuning burden at 16px**) are the top external contenders, with **`RecursiveSansLnrSt-SemiBold (w600)`** (`Score: 125.5`) a close #3.
  - However, look at **`IBMPlexSans-SemiBold (w600)`** (`Score: 124.6`): simply stepping IBM Plex's `normal` role from `Medium (w500)` (`Score: 109.8`, `16px` floor) up to **`SemiBold (w600)`** (`Score: 124.6`, **`14px` native floor**, `76.5%` HQConf at `14px`, `78.7%` at `16px`, `95.0%` native `>=2px` stems) closes **90% of the gap** to `Inter-SemiBold` without even changing typeface families!

---

## 3. Top 3 Contenders for **Bold UI (`bold` Role: `w700..w900`)** vs. IBM Plex

| Rank / Role | Typeface & Cut | `wght` | Raw -> Tuned Floor | `12px` Raw HQ / Stems / Cnt | `14px` Raw HQ / Stems / Cnt / Burden | `16px` HQ Conf (`Raw -> Tuned`) | `16px` `>=2px` Stems | `16px` Counters | `16px` Tuning Burden | Composite Score |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Contender #1 (Best Overall Bold)** | **`Inter-Bold`** (`Inter-Bold.ttf`) | `700` | **`12px -> 12px`** | **`76.8%` / `90.0%` / `100%`** | **`79.3%` / `93.3%` / `100%` / `0.0%`** | **`80.7% -> 80.7%`** | **`96.7%`** | **`100.0%`** | **`0/60 (0.0%)`** | **`135.9`** |
| **Contender #2 (Best Monospace Bold)** | **`RecMonoDuotone-Bold-1.085`** / **`RecursiveMonoLnrSt-Bold`** | `750` / `700` | **`12px -> 12px`** | `75.0%` / **`93.3%`** / `95.2%` | `78.3%` / **`95.0%`** / `95.2%` / `1.7%` | **`80.5% -> 80.6%`** | **`95.0%`** | `95.2%` | `2/60 (3.3%)` | **`131.8`** |
| **Contender #3 (Best UI / Condensed Bold)** | **`NotoSans-Bold`** & **`NotoSans-CondensedBold`** | `700` | **`14px -> 14px`** | `76.7%` / `90.0%` / `90.5%` | **`79.7%` / `96.7%` / `100%` / `0.0%`** | **`80.3% -> 80.3%`** | **`96.7%`** | **`100.0%`** | **`0/60 (0.0%)`** | **`127.6`** |
| **Best `>=16px` Hero Display Bold (`w800`)** | **`InterDisplay-ExtraBold`** (`InterDisplay-ExtraBold.ttf`) | `800` | `16px -> 16px` | `79.9%` / `95.0%` / `85.7%` | **`81.6%` / `96.7%` / `100%` / `5.0%`** | **`83.9% -> 83.9%`** | **`98.3%`** | **`100.0%`** | `2/60 (3.3%)` | `121.6` |
| **IBM Plex Baseline (`w700` Bold)** | **`IBMPlexSans-Bold`** (`IBMPlexSans-Bold.ttf`) | `700` | **`14px -> 14px`** | `77.5%` / `81.7%` / `85.7%` | **`78.8%` / `96.7%` / `95.2%` / `1.7%`** | `78.2% -> 77.9%` | `95.0%` | `95.2%` | `4/60 (6.7%)` | **`125.1`** |
| **IBM Plex Baseline (`w800` ExtraBold)** | **`IBMPlexSans-ExtraBold`** (`IBMPlexSans-ExtraBold.ttf`) | `800` | `16px -> 16px` | `79.5%` / `91.7%` / `90.5%` | `79.6%` / `96.7%` / `81.0%` / `1.7%` | **`84.0% -> 84.3%`** | **`96.7%`** | `95.2%` | `2/60 (3.3%)` | `118.6` |

- **Head-to-Head Verdict (`Bold` Role vs. IBM Plex)**:
  - **`Inter-Bold (w700)`** (`Score: 135.9`) is the **single highest-scoring outline font in the entire 408-font dataset**: it achieves a **`12px` native raw floor**, **`100.0%` open counters from `12px` through `24px`**, and a **`0.0%` tuning burden at `14px` and `16px`** (zero glyphs need patching!).
  - **`NotoSans-Bold (w700)`** (`Score: 127.3`) and **`NotoSans-CondensedBold (w700)`** (`Score: 127.6`) also achieve **`0.0%` tuning burden at `14px`–`16px`** with `100.0%` counters.
  - Compared to IBM Plex: **`IBMPlexSans-Bold (w700)`** (`Score: 125.1`, `14px` floor) outperforms `IBMPlexSans-ExtraBold (w800)` (`16px` floor) at `12px–14px` because `w700` keeps lowercase `'a'` and `'e'` counters open at `14px`, whereas **`IBMPlexSans-ExtraBold (w800)`** (`84.0%` HQConf) is superior at `>=16px` (`16px, 18px, 20px, 24px, 32px`) where counters have ample room and the extra stem weight (`3.1px`) creates unmistakable visual hierarchy over `Medium (w500)` / `SemiBold (w600)`.

---

## 4. Top 3 Contenders for **Italic UI (`italic` Role)** vs. IBM Plex

| Rank / Role | Typeface & Cut | `wght` | Raw -> Tuned Floor | `14px` Raw HQ / Stems / Cnt / Burden | `16px` HQ Conf (`Raw -> Tuned`) | `16px` `>=2px` Stems (`Raw -> Tuned`) | `16px` Counters | `16px` Tuning Burden | Composite Score |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Contender #1 (Best Overall Italic)** | **`Inter-ExtraBoldItalic`** / **`InterDisplay-BoldItalic`** | `800` / `700` | **`14px -> 14px`** | **`75.6%` / `93.3%` / `100%` / `5.0%`** | **`78.9% -> 78.8%`** | **`96.7% -> 96.7%`** | `95.2%` | **`3/60 (5.0%)`** | **`125.3`** |
| **Contender #2 (Best Sans & Medium-Weight Italic)** | **`RecursiveSansLnrSt-ExBdItalic (w800)`** & **`RecursiveSansCslSt-SmBdItalic (w600)`** | `800` / `600` | **`14px -> 14px`** (`w800`) / **`16px -> 16px`** (`w600`) | `76.0%` / **`96.7%`** / `95.0%` / **`3.3%`** (`w800`) | `77.2%` (`w800`) / `74.8%` (`w600`) | **`96.7%`** (`w800`) / **`93.3%`** (`w600`) | `95.2%` | **`2/60 (3.3%)`** | **`124.9`** |
| **Contender #3 (Best Classic Humanist Italic)** | **`Roboto-BoldItalic`** (`Roboto-BoldItalic.ttf`) | `700` | **`14px -> 14px`** | `73.4%` / `83.3%` / **`100%`** / **`3.3%`** | `74.6% -> 74.6%` | **`95.0% -> 95.0%`** | `95.0%` | `4/60 (6.7%)` | **`121.9`** |
| **IBM Plex Upgraded Italic (`w700` — New `v1.0.15` Default)** | **`IBMPlexSans-BoldItalic`** (`IBMPlexSans-BoldItalic.ttf`) | `700` | **`16px -> 16px`** | `72.7%` / **`86.7%`** / **`100%`** / **`5.0%`** | **`76.3% -> 76.3%`** | **`96.7% -> 96.7%`** | **`100.0%`** | **`2/60 (3.3%)`** | **`116.2`** |
| **IBM Plex Legacy Italic (`w500` — Prior `v1.0.14` Default)** | **`IBMPlexSans-MediumItalic`** (`IBMPlexSans-MediumItalic.ttf`) | `500` | `24px -> 24px` | `63.2%` / `15.0%` / `85.7%` / `66.7%` | `67.6% -> 69.4%` | `60.0% -> 85.0%` | `95.2%` | `17/60 (28.3%)` | `60.6` |

- **Head-to-Head Verdict (`Italic` Role vs. IBM Plex)**:
  - In `v1.0.14`, `IBMPlexSans-MediumItalic (w500)` (`Score: 60.6`, `24px` floor, `66.7%` tuning burden at `14px`) was by far the weakest strike in the IBM Plex suite.
  - Upgrading the `italic` role in `v1.0.15` (`get_family_roles()` in `humid1_generate_1bpp.py`) from `MediumItalic (w500)` to **`BoldItalic (w700)`** (`IBMPlexSans-BoldItalic.ttf`, `IBMPlexMono-BoldItalic.ttf`, `IBMPlexSerif-BoldItalic.ttf`) transforms IBM Plex Italic overnight:
    - Size floor drops from `24px` to **`16px`** (`100.0%` open counters at both `14px` and `16px`!),
    - Raw `>=2px` stem survival jumps from `15.0%` -> **`86.7%`** at `14px` and `60.0%` -> **`96.7%`** at `16px`, and
    - Tuning burden drops from `66.7%` (at `14px`) / `28.3%` (at `16px`) down to **`5.0%` / `3.3%`**!

---

## 5. Finding the Ideal Font Stack for the Ideal Use Case (Recommended Combinations)

Based on all 425 evaluated font cuts, here are the three optimal, production-ready font stacks depending on whether you want to stay 100% within the **IBM Plex + Terminus** ecosystem or adopt the **Top External Contenders (`Inter` + `Recursive` + `Terminus`)**:

| Target Use Case / Stack | Micro UI (`10px–12px`) | Standard UI (`normal` `14px–24px`) | Bold Headers (`bold` `14px–32px`) | Italic Emphasis (`italic` `14px–16px`) | Tabular Telemetry (`mono` `12px–24px`) | Do You Need Auto-Tune? |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Stack A: Ultimate External Contender Stack ("Zero-Tune Dream Team")** | `Terminus-Normal-12` & `Terminus-Bold-12` (`0.0%` burden) | **`Inter-SemiBold (w600)`** or **`InstrumentSans-SemiBold (w600)`** (`14px` floor, `0%–1.7%` burden) | **`Inter-Bold (w700)`** (`12px–14px`) + **`InterDisplay-ExtraBold (w800)`** (`>=16px`) (`0%–3.3%` burden) | **`Inter-ExtraBoldItalic (w800)`** or **`InterDisplay-BoldItalic (w700)`** (`14px` floor, `3.3%–5.0%` burden) | **`RecMonoDuotone-Bold-1.085`** or **`RecursiveMonoLnrSt-SemiBold (w600)`** (`12px–14px` floor, `1.7%` burden) | **NO stem tuning needed!** (`--tune-mode off` or `--tune-mode wart-only`) |
| **Stack B: Upgraded IBM Plex + Terminus Stack (`v1.0.15` Repo Default)** | `Terminus-Normal-12` & `Terminus-Bold-12` (`0.0%` burden) | **`IBMPlexSans-Medium (w500)`** (or **`IBMPlexSans-SemiBold w600`** for `14px` floor) | **`IBMPlexSans-Bold (w700)`** (`12–14px`) / **`IBMPlexSans-ExtraBold (w800)`** (`>=16px`) | **`IBMPlexSans-BoldItalic (w700)`** (`16px` floor, `100%` counters, `3.3%` burden — upgraded in `v1.0.15`!) | **`IBMPlexMono-Medium (w500)`** & **`IBMPlexMono-ExtraBold (w800)`** | **`--tune-mode wart-only`** at `>=16px`; **`--tune-mode surgical`** only if using `w500` at `12px–14px` |
| **Stack C: High-Density Industrial / Narrow HMI (`200x200` Compact Rows)** | `Terminus-Normal-12` | **`NotoSans-SemiCondensedSemiBold (w600)`** or **`InstrumentSansSemiCondensed-SemiBold (w600)`** (`14px` floor, `0%–3.3%` burden) | **`NotoSans-CondensedBold (w700)`** or **`InstrumentSansCondensed-Bold (w700)`** (`14px` floor, `0%–1.7%` burden) | **`InstrumentSansSemiCondensed-BoldItalic (w700)`** (`16px` floor, `3.3%` burden) | **`IosevkaAile-ExtraBold (w800)`** (`14px` floor, `0.0%` burden) | **NO stem tuning needed!** (`--tune-mode off` or `wart-only`) |
