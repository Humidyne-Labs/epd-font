# Humiditron `epd-font` v1.0.13 — Formal Engineering & Typographic Audit Report

- **Repository**: [https://github.com/Humidyne-Labs/epd-font](https://github.com/Humidyne-Labs/epd-font)
- **Target OS**: [https://github.com/Humidyne-Labs/H1OS](https://github.com/Humidyne-Labs/H1OS) (`humid1-os`)
- **Audit Scope**: `v1.0.12` $\to$ **`v1.0.13`** (`docs/audits/humid1-audit-v1.0.13.txt` & `docs/audits/exhibits/v1.0.13/`)
- **Total Static TrueType (`.ttf`) Assets**: **88 Verified `.ttf` Files**
- **Total Surgical Auto-Repaired Patches**: **651 Verified Patches** (down from `1,816` in `v1.0.12` after purging stale legacy overrides and enforcing the `8x` Upscaled-to-HQ Confidence & Open-Valley Sanity Gate)

---

## 1. Executive Summary of Audit Findings & Engineering Resolutions

| Audit Issue (`humid1-audit-v1.0.13.txt`) | Root Cause Identified | `v1.0.13` Engineering Resolution | Verification Status |
| :--- | :--- | :--- | :--- |
| **1. `02_run_font_eval.bat` Benchmarked `0` Fonts on `eval_fonts` (`>700 MB`, 408 Files)** | In `v1.0.12`, `humid1_font_eval.py` checked a hardcoded list of `IBMPlex*` filenames whenever `--fonts` was omitted. Pointing `--src-dir` at `eval_fonts` (`InstrumentSans`, `Inter`, `Iosevka*.ttc`, `Literata`, `NotoSans`, `PublicSans`, `Recursive`, `Roboto`, `SourceSans3`, `SourceSerif4`, `SpaceGrotesk`) matched `0` files. | Upgraded `discover_candidate_fonts()` in `humid1_font_eval.py` to recursively scan any `--src-dir` for all `.ttf`, `.otf`, `.ttc` (TrueType Collection), and `.bdf` files, inspect `cmap` and `OS/2.usWeightClass`, filter out PUA-only icon fonts, and evaluate all discovered fonts in parallel across all CPU cores (`ProcessPoolExecutor`). | **VERIFIED (Scans `.ttf`/`.otf`/`.ttc` recursively)** |
| **2. Missing Pre-Tune vs. Post-Tune Traceability & Per-Font PNG Sheets** | `v1.0.12` only rendered post-tune specimens in a single combined image, making it hard to see whether auto-tune improved or degraded a font or which fonts needed excessive tuning. | Upgraded `humid1_font_eval.py` to compute and display **both `PRE-TUNE (RAW)` and `POST-TUNE (TUNED)`** metrics (`HQ Confidence %`, `HQ Diff %`, `>=2px Stem %`, `Counter %`, and `Tuning Burden %`), emit **one dedicated PNG sheet per font (`build/font_eval/sheets/<font_stem>_eval.png`)**, and rank fonts into **Tiers 1–3** by natural untuned fitness. | **VERIFIED (`sheets/<font>_eval.png` + Pre/Post rows)** |
| **3. `'W'` & `'w'` Turning Into a Solid Black Mass (`cond_normal_14`, `mono_normal_16`, `sans_italic_12`)** | By the **Pigeonhole Principle**, a 4-stroke `'w'`/`'W'` with `2px` strokes ($4\times 2 = 8\text{px}$) and 3 open `1px` V-valleys ($3\times 1 = 3\text{px}$) requires $\ge 11\text{px}$ width. Inside a `9x9` or `10x9` cell, forcing `2px` stems onto all 4 strokes collapsed the open V-valleys (which had $B_1 = 0$ enclosed holes, so Betti lock didn't catch them), spiking HQ Valley Occlusion from `26.2%` to **`94.4%`** and Ink Mass Error from `+1.8%` to **`+79.8%`**! | Implemented the **Multi-Stroke Pigeonhole Law**, **Open-Valley Scanline Run-Count Invariance (`compute_open_valley_stats()`)**, and the **Render $\to$ $8\times$ Upscale $\to$ HQ Master Sanity Gate (`compute_upscaled_hq_metrics()`)**, rejecting any candidate that bridges open V-valleys or increases HQ valley occlusion by $>3.0\%–5.5\%$. | **VERIFIED (`W` & `w` 100% open & untouched)** |
| **4. Over-Correction on `'A'`, `'B'`, `'f'`, `'g'`, `'s'`, and `32px` `')'` in Bold Strikes** | Two compounding causes: (a) `build_patches_json_from_ascii_root()` called `.update()` on the existing `font_icon_epd_patches.json`, preserving stale `v1.0.9–v1.0.11` (`Bold 700`) overrides even when `v1.0.12` did not patch them, overwriting pristine `ExtraBold (800)` glyphs; (b) `measure_stem_deficits()` counted `1px` pointed apex rows (`r=0`, `r=h-1` on `'A'`) as stem deficits. | Purged all stale legacy patches from `font_icon_epd_patches.json`, fixed `build_patches_json_from_ascii_root()` to replace each strike dict cleanly, excluded top/bottom apex rows (`r=0`, `r=h-1`) from stem deficit triggers, and added the **"Do No Harm" Conservative Trigger Gate** for bold and high-confidence glyphs (`HQConf >= 72%`). | **VERIFIED (`A, B, C, f, g, r, s, (, )` 100% pristine)** |

---

## 2. Quantitative Proof: Render $\to$ Upscale ($8\times$) $\to$ Compare to HQ Master (`compute_upscaled_hq_metrics`)

In `humid1-audit-v1.0.13.txt`, you proposed a critical sanity check:
> *"if we render, upscale, then compare to HQ, could we not derive a confidence score from that? as at least a sanity check? (oh, xyz char diff's by idk, 20%, etc...)"*

We implemented `compute_upscaled_hq_metrics(bitmap_1bit, hq_master)` in `tools/fonts/humid1_bilevel_tuner.py` (`v1.0.13`) and measured the exact Pre-Tune (`RAW`) vs. `v1.0.12` Patched vs. `v1.0.13` Surgical output on every single exhibit from `docs/audits/exhibits/v1.0.13/`:

| Exhibit Strike & Glyph | `v1.0.12` Failure Mode | Raw FreeType `HQConf` (`Diff%`) | `v1.0.12` Valley Occlusion (`Raw -> v1.0.12`) | `v1.0.12` Ink Mass Error (`Raw -> v1.0.12`) | `v1.0.13` Action & Verified Result |
| :--- | :--- | :---: | :---: | :---: | :--- |
| `cond_normal_14` `'W'` (`11x10`) | Lower 80% filled solid black | `56.4%` (`24.7%`) | `21.2% -> 73.6%` (**`+52.4%` clogged!**) | `-0.3% -> +92.5%` | **REJECTED by Valley/Mass Gate $\to$ `M0_verified` (Untouched, open V-valleys)** |
| `mono_normal_16` `'w'` (`9x9`) | Turned into solid `9x9` black square | `63.7%` (`24.2%`) | `26.2% -> 94.4%` (**`+68.2%` clogged!**) | `+1.8% -> +79.8%` | **REJECTED by Pigeonhole & Valley Gate $\to$ `M0_verified` (Untouched, open V-valleys)** |
| `sans_italic_12` `'W'` (`10x9`) | Clogged into solid black block | `50.2%` (`30.5%`) | `32.2% -> 80.0%` (**`+47.8%` clogged!**) | `+18.7% -> +109.7%` | **REJECTED by Valley/Mass Gate $\to$ `M0_verified` (Untouched, open V-valleys)** |
| `sans_italic_12` `'M'` (`9x9`) | Right valley clogged solid | `45.4%` (`32.5%`) | `28.6% -> 31.6%` | `+3.3% -> +33.4%` | **REJECTED by Multi-Valley Gate $\to$ `M0_verified` (Untouched, open V-valleys)** |
| `sans_bold_14` `'A'`, `'B'`, `'C'` | Stale `v1.0.10` patch overwrote `'A'` & `'B'` | `70.6%`, `87.1%`, `76.8%` (`10.9%–19.0%`) | `23.1%`, `35.0%`, `19.2%` | `+5.6%`, `+9.2%`, `+11.6%` | **Stale patches purged $\to$ `M0_verified` (`A`, `B`, `C` all 100% untouched `ExtraBold 800`)** |
| `sans_bold_12` `'f'`, `'g'` | Stale `Bold 700` patch overwrote `'f'` & `'g'` | `77.2%`, `69.6%` (`16.1%–24.8%`) | `21.9%`, `37.1%` | `+10.9%`, `+12.8%` | **Stale patches purged $\to$ `M0_verified` (`f`, `g` both 100% untouched `ExtraBold 800`)** |
| `mono_bold_14` `'f'`, `'g'` | Over-thickened `'f'` (`HQConf` dropped `87.1% -> 84.1%`) | `87.1%`, `71.2%` (`8.8%–22.3%`) | `19.0% -> 25.0%` | `+11.3% -> +15.2%` | **Protected by Bold Gate $\to$ `M0_verified` (`f`, `g` both 100% untouched `ExtraBold 800`)** |
| `mono_bold_16` `'g'`, `'r'`, `'s'` | `'s'` valley clogged (`ValleyOcc` `16.2% -> 44.8%`) | `75.9%`, `84.2%`, `79.8%` (`10.4%–17.0%`) | `16.2% -> 44.8%` on `'s'` | `-2.7% -> +18.2%` on `'s'` | **Protected by Bold & Valley Gate $\to$ `M0_verified` (`g, r, s` 100% untouched)** |
| `mono_bold_32` `'('`, `')'`, `'*'` | Stale patch shrank `')'` from `12x29` to `10x29` | `84.8%`, `88.5%`, `87.9%` (`4.8%–7.2%`) | `4.6%–11.0%` | `+3.8%–+6.5%` | **Stale patches purged $\to$ `(` & `)` both `12x29` (`5px` curve), `'*'` untouched `17x16`** |

---

## 3. Weight Selection vs. Auto-Tuning: Answering the Core Question

In `humid1-audit-v1.0.13.txt`, you asked:
> *"What if all we had to do was change the weight? What if the auto tune is actually making things worse? Arguably, any new result is valid data, and valid data is progress."*

The `v1.0.13` Pre-Tune (`RAW`) vs. Post-Tune (`TUNED`) benchmark across 20 internal/external font cuts (`build/font_eval/font_eval_report.md`) provides the exact answer:

| Typeface & Weight Label | `wght` | Recommendation Tier | Raw Floor | Tuned Floor | 16px HQ Conf (`Raw -> Tuned`) | 16px `>=2px` Stems (`Raw -> Tuned`) | 16px Tuning Burden (`Patched / Total`) |
| :--- | :---: | :--- | :---: | :---: | :---: | :---: | :---: |
| **IBM Plex Sans Regular (w400)** | `400` | TIER 3: HIGH TUNE BURDEN | `24px` | `20px` | `62.5% -> 68.7%` | `21.7% -> 78.3%` | `47/60` (**`78.3%`**) |
| **IBM Plex Sans Normal [Medium w500]** | `500` | **TIER 1: NATIVE READY** | **`14px`** | **`14px`** | `74.4% -> 75.1%` | **`93.3% -> 100.0%`** | **`6/60` (`10.0%`)** |
| **IBM Plex Sans SemiBold (w600)** | `600` | **TIER 1: NATIVE READY** | **`12px`** | **`12px`** | `78.7% -> 79.1%` | **`96.7% -> 100.0%`** | **`3/60` (`5.0%`)** |
| **IBM Plex Sans Bold [ExtraBold w800]** | `800` | **TIER 1: NATIVE READY** | **`12px`** | **`10px`** | `84.0% -> 84.3%` | **`100.0% -> 100.0%`** | **`2/60` (`3.3%`)** |
| **IBM Plex Mono Normal [Medium w500]** | `500` | **TIER 1: NATIVE READY** | **`14px`** | **`14px`** | `73.2% -> 73.5%` | **`93.3% -> 100.0%`** | **`4/60` (`6.7%`)** |
| **IBM Plex Mono Bold [ExtraBold w800]** | `800` | **TIER 1: NATIVE READY** | **`12px`** | **`12px`** | `82.5% -> 82.7%` | **`98.3% -> 100.0%`** | **`3/60` (`5.0%`)** |
| **Inter Regular (w400) [External]** | `400` | TIER 3: HIGH TUNE BURDEN | `24px` | `16px` | `66.4% -> 71.1%` | `21.7% -> 88.3%` | `45/60` (**`75.0%`**) |
| **Inter Medium (w500) [External]** | `500` | **TIER 1: NATIVE READY** | **`16px`** | **`12px`** | `73.3% -> 74.5%` | **`91.7% -> 100.0%`** | **`7/60` (`11.7%`)** |
| **Inter SemiBold (w600) [External]** | `600` | **TIER 1: NATIVE READY** | **`12px`** | **`10px`** | `81.2% -> 81.1%` | **`98.3% -> 100.0%`** | **`1/60` (`1.7%`)** |
| **Inter Bold (w700) [External]** | `700` | **TIER 1: NATIVE READY** | **`10px`** | **`10px`** | `81.1% -> 81.1%` | **`100.0% -> 100.0%`** | **`0/60` (`0.0%`)** |
| **Inter ExtraBold (w800) [External]** | `800` | **TIER 1: NATIVE READY** | **`10px`** | **`10px`** | `83.8% -> 83.8%` | **`100.0% -> 100.0%`** | **`0/60` (`0.0%`)** |
| **Terminus Native Bitmap (w400)** | `400` | **TIER 1: NATIVE READY** | **`12px`** | **`12px`** | `100.0% -> 100.0%` | **`100.0% -> 100.0%`** | **`0/60` (`0.0%`)** |

### Key Conclusions from the Data:
1. **Weight Selection Does 90%+ of the Work Naturally**:
   - At `Regular (400)`, `75%–78%` of glyphs at `16px` have `1px` stems (`21.7%` raw `>=2px` survival). Trying to force a `Regular (400)` font to have `2px` stems via post-raster morphological tuning requires modifying almost every glyph (`78%` Tuning Burden), which inevitably distorts complex multi-stroke characters (`W`, `w`, `M`, `m`, `s`).
   - Simply choosing **`Medium (500)`** or **`SemiBold (600)`** for `normal` and **`ExtraBold (800)`** for `bold` gives **`93.3%–100.0%` `>=2px` stems right out of FreeType (`RAW`)** with **`74%–84%` HQ Confidence**!
2. **Surgical Auto-Tune Should Only Touch the `3%–10%` Outliers**:
   - Even in `Medium (500)` or `SemiBold (600)`, a handful of punctuation/symbol glyphs (`$`, `(`, `)`, `[`, `]`, `|`, `!`, `/`, `\`) are still drawn with `1px` lines by type designers.
   - With `v1.0.13`'s **Conservative Surgical Trigger + $8\times$ Upscaled-to-HQ Sanity Gate**, `90%–97%` of glyphs in `Medium (500)` and `ExtraBold (800)` are left **100% untouched (`M0_verified`)**, while only the `3%–10%` thin delimiters (`$`, `(`, `)`, `|`) are surgically thickened and mirror-synced!

---

## 4. Running the Upgraded Font Evaluation Suite on Your `eval_fonts` Collection (`>700 MB`)

You can now run `scripts\font-eval-suite\02_run_font_eval.bat` directly against `C:\Users\Matt\Documents\GitHub\_backup_archive\epd-font\eval_fonts` (or pass any folder path as an argument):
```bat
scripts\font-eval-suite\02_run_font_eval.bat
```
- **Recursive Discovery**: Automatically finds all `.ttf`, `.otf`, and `.ttc` files (including `IosevkaAile-*.ttc`, `IosevkaEtoile-*.ttc`, `InstrumentSans`, `Inter`, `Literata`, `NotoSans`, `PublicSans`, `RecMono`, `Recursive`, `Roboto`, `SourceSans3`, `SourceSerif4`, `SpaceGrotesk`).
- **Per-Font Pre/Post Visual Sheets**: Writes an individual PNG inspection sheet for every font into `build\font_eval\sheets\<FontName>_eval.png` showing `PRE-TUNE (RAW)` vs `POST-TUNE (TUNED)` across `12px, 14px, 16px, 20px, 24px`.
- **Sortable CSV & Markdown Leaderboard**: Writes `build\font_eval\font_eval_report.csv` and `build\font_eval\font_eval_report.md` so you can filter for `TIER 1: NATIVE READY` fonts with `<15%` Tuning Burden.
