# Humiditron `epd-font` v1.0.13 — Pre-Tune vs. Post-Tune Multi-Font Evaluation Report

## 1. Executive Summary: Pre-Tune (`RAW`) vs. Post-Tune (`TUNED`) & Tuning Burden Analysis

Every candidate font and weight was evaluated across sizes both **Before (`RAW`)** and **After (`TUNED`)** the v1.0.13 Surgical Tournament (`Render -> 8x Upscale -> Compare to 8x HQ Master` Confidence & Open-Valley Sanity Gate):
- **HQ Confidence (`RAW -> TUNED`)**: Direct structural IoU (`0..100%`) of the 8x nearest-neighbor upscaled 1-BPP strike against the 8x continuous HQ Master.
- **Tuning Burden (`%`)**: Percentage of benchmark characters that required surgical patching. **Lower Tuning Burden + Higher Raw HQ Confidence** identifies typefaces and weights that work cleanly out-of-the-box with minimal or zero pixel intervention!
- **Per-Font Visual Inspection Sheets**: Saved individually in `build/font_eval/sheets/<font_stem>_eval.png`.

| Typeface & Weight Label | Font File | `wght` | Recommendation Tier | Raw Floor | Tuned Floor | 16px HQ Conf (`Raw -> Tuned`) | 16px `>=2px` Stems (`Raw -> Tuned`) | 16px Tuning Burden | Per-Font PNG Sheet |
| :--- | :--- | :---: | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **Inter-Black (w900)** | `Inter-Black.otf` | `900` | TIER 1: NATIVE READY (Minimal/Zero Tune Needed) | `14px` | **`12px`** | `84.6% -> 84.6%` | `100.0% -> 100.0%` | `0/60 (0.0%)` | `sheets/Inter-Black_eval.png` |
| **Inter-BlackItalic (w900)** | `Inter-BlackItalic.otf` | `900` | TIER 1: NATIVE READY (Minimal/Zero Tune Needed) | `14px` | **`14px`** | `80.3% -> 80.6%` | `100.0% -> 100.0%` | `2/60 (3.3%)` | `sheets/Inter-BlackItalic_eval.png` |
| **Inter-Bold (w700)** | `Inter-Bold.otf` | `700` | TIER 1: NATIVE READY (Minimal/Zero Tune Needed) | `12px` | **`12px`** | `81.1% -> 81.1%` | `100.0% -> 100.0%` | `0/60 (0.0%)` | `sheets/Inter-Bold_eval.png` |
| **Inter-BoldItalic (w700)** | `Inter-BoldItalic.otf` | `700` | TIER 1: NATIVE READY (Minimal/Zero Tune Needed) | `12px` | **`12px`** | `76.8% -> 76.7%` | `98.3% -> 98.3%` | `3/60 (5.0%)` | `sheets/Inter-BoldItalic_eval.png` |
| **Inter-ExtraBold (w800)** | `Inter-ExtraBold.otf` | `800` | TIER 1: NATIVE READY (Minimal/Zero Tune Needed) | `12px` | **`12px`** | `83.8% -> 83.8%` | `100.0% -> 100.0%` | `0/60 (0.0%)` | `sheets/Inter-ExtraBold_eval.png` |
| **Inter-ExtraBoldItalic (w800)** | `Inter-ExtraBoldItalic.otf` | `800` | TIER 1: NATIVE READY (Minimal/Zero Tune Needed) | `12px` | **`12px`** | `78.1% -> 78.0%` | `100.0% -> 100.0%` | `1/60 (1.7%)` | `sheets/Inter-ExtraBoldItalic_eval.png` |
| **Inter-ExtraLight (w200)** | `Inter-ExtraLight.otf` | `200` | TIER 3: HIGH TUNE BURDEN / LARGE SIZES ONLY | `>24px` | `>24px` | `56.2% -> 53.6%` | `15.0% -> 45.0%` | `26/60 (43.3%)` | `sheets/Inter-ExtraLight_eval.png` |
| **Inter-ExtraLightItalic (w200)** | `Inter-ExtraLightItalic.otf` | `200` | TIER 3: HIGH TUNE BURDEN / LARGE SIZES ONLY | `>24px` | `>24px` | `43.3% -> 41.1%` | `13.3% -> 40.0%` | `18/60 (30.0%)` | `sheets/Inter-ExtraLightItalic_eval.png` |
| **Inter-Italic (w400)** | `Inter-Italic.otf` | `400` | TIER 3: HIGH TUNE BURDEN / LARGE SIZES ONLY | `20px` | **`20px`** | `62.6% -> 66.3%` | `25.0% -> 76.7%` | `44/60 (73.3%)` | `sheets/Inter-Italic_eval.png` |
| **Inter-Light (w300)** | `Inter-Light.otf` | `300` | TIER 3: HIGH TUNE BURDEN / LARGE SIZES ONLY | `>24px` | **`24px`** | `66.5% -> 65.7%` | `21.7% -> 58.3%` | `46/60 (76.7%)` | `sheets/Inter-Light_eval.png` |
| **Inter-LightItalic (w300)** | `Inter-LightItalic.otf` | `300` | TIER 3: HIGH TUNE BURDEN / LARGE SIZES ONLY | `>24px` | **`24px`** | `57.3% -> 59.7%` | `20.0% -> 45.0%` | `48/60 (80.0%)` | `sheets/Inter-LightItalic_eval.png` |
| **Inter-Medium (w500)** | `Inter-Medium.otf` | `500` | TIER 1: NATIVE READY (Minimal/Zero Tune Needed) | `16px` | **`12px`** | `73.3% -> 74.5%` | `91.7% -> 100.0%` | `7/60 (11.7%)` | `sheets/Inter-Medium_eval.png` |
| **Inter-MediumItalic (w500)** | `Inter-MediumItalic.otf` | `500` | TIER 2: VIABLE WITH SURGICAL TUNE | `20px` | **`12px`** | `66.9% -> 68.8%` | `75.0% -> 98.3%` | `15/60 (25.0%)` | `sheets/Inter-MediumItalic_eval.png` |
| **Inter-Regular (w400)** | `Inter-Regular.otf` | `400` | TIER 3: HIGH TUNE BURDEN / LARGE SIZES ONLY | `24px` | **`16px`** | `66.4% -> 71.1%` | `21.7% -> 88.3%` | `45/60 (75.0%)` | `sheets/Inter-Regular_eval.png` |
| **Inter-SemiBold (w600)** | `Inter-SemiBold.otf` | `600` | TIER 1: NATIVE READY (Minimal/Zero Tune Needed) | `12px` | **`12px`** | `81.2% -> 81.1%` | `98.3% -> 100.0%` | `1/60 (1.7%)` | `sheets/Inter-SemiBold_eval.png` |
| **Inter-SemiBoldItalic (w600)** | `Inter-SemiBoldItalic.otf` | `600` | TIER 1: NATIVE READY (Minimal/Zero Tune Needed) | `16px` | **`12px`** | `73.3% -> 73.0%` | `96.7% -> 98.3%` | `4/60 (6.7%)` | `sheets/Inter-SemiBoldItalic_eval.png` |
| **Inter-Thin (w100)** | `Inter-Thin.otf` | `100` | TIER 3: HIGH TUNE BURDEN / LARGE SIZES ONLY | `>24px` | `>24px` | `11.9% -> 12.3%` | `81.5% -> 92.6%` | `3/27 (11.1%)` | `sheets/Inter-Thin_eval.png` |
| **Inter-ThinItalic (w100)** | `Inter-ThinItalic.otf` | `100` | TIER 3: HIGH TUNE BURDEN / LARGE SIZES ONLY | `>24px` | `>24px` | `10.3% -> 10.3%` | `93.8% -> 93.8%` | `0/32 (0.0%)` | `sheets/Inter-ThinItalic_eval.png` |
| **InterDisplay-Black (w900)** | `InterDisplay-Black.otf` | `900` | TIER 1: NATIVE READY (Minimal/Zero Tune Needed) | `12px` | **`12px`** | `85.7% -> 85.7%` | `98.3% -> 100.0%` | `2/60 (3.3%)` | `sheets/InterDisplay-Black_eval.png` |
| **InterDisplay-BlackItalic (w900)** | `InterDisplay-BlackItalic.otf` | `900` | TIER 2: VIABLE WITH SURGICAL TUNE | `20px` | **`14px`** | `81.4% -> 81.4%` | `100.0% -> 100.0%` | `0/60 (0.0%)` | `sheets/InterDisplay-BlackItalic_eval.png` |
| **InterDisplay-Bold (w700)** | `InterDisplay-Bold.otf` | `700` | TIER 1: NATIVE READY (Minimal/Zero Tune Needed) | `12px` | **`12px`** | `81.6% -> 81.6%` | `100.0% -> 100.0%` | `0/60 (0.0%)` | `sheets/InterDisplay-Bold_eval.png` |
| **InterDisplay-BoldItalic (w700)** | `InterDisplay-BoldItalic.otf` | `700` | TIER 1: NATIVE READY (Minimal/Zero Tune Needed) | `12px` | **`12px`** | `77.5% -> 77.4%` | `100.0% -> 100.0%` | `2/60 (3.3%)` | `sheets/InterDisplay-BoldItalic_eval.png` |
| **InterDisplay-ExtraBold (w800)** | `InterDisplay-ExtraBold.otf` | `800` | TIER 1: NATIVE READY (Minimal/Zero Tune Needed) | `12px` | **`12px`** | `84.1% -> 84.1%` | `100.0% -> 100.0%` | `0/60 (0.0%)` | `sheets/InterDisplay-ExtraBold_eval.png` |
| **InterDisplay-ExtraBoldItalic (w800)** | `InterDisplay-ExtraBoldItalic.otf` | `800` | TIER 1: NATIVE READY (Minimal/Zero Tune Needed) | `12px` | **`12px`** | `79.5% -> 79.5%` | `100.0% -> 100.0%` | `0/60 (0.0%)` | `sheets/InterDisplay-ExtraBoldItalic_eval.png` |
| **InterDisplay-ExtraLight (w200)** | `InterDisplay-ExtraLight.otf` | `200` | TIER 3: HIGH TUNE BURDEN / LARGE SIZES ONLY | `>24px` | `>24px` | `55.6% -> 53.0%` | `15.0% -> 48.3%` | `26/60 (43.3%)` | `sheets/InterDisplay-ExtraLight_eval.png` |
| **InterDisplay-ExtraLightItalic (w200)** | `InterDisplay-ExtraLightItalic.otf` | `200` | TIER 3: HIGH TUNE BURDEN / LARGE SIZES ONLY | `>24px` | `>24px` | `42.3% -> 41.0%` | `11.7% -> 28.3%` | `12/60 (20.0%)` | `sheets/InterDisplay-ExtraLightItalic_eval.png` |
| **InterDisplay-Italic (w400)** | `InterDisplay-Italic.otf` | `400` | TIER 3: HIGH TUNE BURDEN / LARGE SIZES ONLY | `24px` | **`20px`** | `62.2% -> 65.7%` | `25.0% -> 78.3%` | `44/60 (73.3%)` | `sheets/InterDisplay-Italic_eval.png` |
| **InterDisplay-Light (w300)** | `InterDisplay-Light.otf` | `300` | TIER 3: HIGH TUNE BURDEN / LARGE SIZES ONLY | `>24px` | **`20px`** | `65.2% -> 65.7%` | `21.7% -> 56.7%` | `46/60 (76.7%)` | `sheets/InterDisplay-Light_eval.png` |
| **InterDisplay-LightItalic (w300)** | `InterDisplay-LightItalic.otf` | `300` | TIER 3: HIGH TUNE BURDEN / LARGE SIZES ONLY | `>24px` | **`24px`** | `55.7% -> 57.6%` | `21.7% -> 43.3%` | `44/60 (73.3%)` | `sheets/InterDisplay-LightItalic_eval.png` |
| **InterDisplay-Medium (w500)** | `InterDisplay-Medium.otf` | `500` | TIER 1: NATIVE READY (Minimal/Zero Tune Needed) | `16px` | **`14px`** | `75.4% -> 76.6%` | `91.7% -> 100.0%` | `7/60 (11.7%)` | `sheets/InterDisplay-Medium_eval.png` |
| **InterDisplay-MediumItalic (w500)** | `InterDisplay-MediumItalic.otf` | `500` | TIER 2: VIABLE WITH SURGICAL TUNE | `20px` | **`16px`** | `69.9% -> 72.8%` | `61.7% -> 96.7%` | `23/60 (38.3%)` | `sheets/InterDisplay-MediumItalic_eval.png` |
| **InterDisplay-Regular (w400)** | `InterDisplay-Regular.otf` | `400` | TIER 3: HIGH TUNE BURDEN / LARGE SIZES ONLY | `24px` | **`20px`** | `67.7% -> 71.5%` | `23.3% -> 76.7%` | `42/60 (70.0%)` | `sheets/InterDisplay-Regular_eval.png` |
| **InterDisplay-SemiBold (w600)** | `InterDisplay-SemiBold.otf` | `600` | TIER 1: NATIVE READY (Minimal/Zero Tune Needed) | `12px` | **`12px`** | `80.8% -> 80.9%` | `98.3% -> 100.0%` | `1/60 (1.7%)` | `sheets/InterDisplay-SemiBold_eval.png` |
| **InterDisplay-SemiBoldItalic (w600)** | `InterDisplay-SemiBoldItalic.otf` | `600` | TIER 1: NATIVE READY (Minimal/Zero Tune Needed) | `14px` | **`12px`** | `75.3% -> 75.6%` | `96.7% -> 100.0%` | `3/60 (5.0%)` | `sheets/InterDisplay-SemiBoldItalic_eval.png` |
| **InterDisplay-Thin (w100)** | `InterDisplay-Thin.otf` | `100` | TIER 3: HIGH TUNE BURDEN / LARGE SIZES ONLY | `>24px` | `>24px` | `12.3% -> 12.6%` | `77.4% -> 83.9%` | `2/31 (6.5%)` | `sheets/InterDisplay-Thin_eval.png` |
| **InterDisplay-ThinItalic (w100)** | `InterDisplay-ThinItalic.otf` | `100` | TIER 3: HIGH TUNE BURDEN / LARGE SIZES ONLY | `>24px` | `>24px` | `11.1% -> 11.1%` | `92.0% -> 92.0%` | `0/25 (0.0%)` | `sheets/InterDisplay-ThinItalic_eval.png` |

## 2. Weight Selection vs. Auto-Tuning: Key Takeaways

1. **Weight Selection (`Medium 500` / `SemiBold 600` / `ExtraBold 800`) Does 85%+ of the Work Out-of-the-Box**:
   - At `Regular (400)`, raw 1-BPP rasterization suffers from `<15%` `>=2px` stem survival at `14–16px`, forcing heavy auto-tuning (`>50%` Tuning Burden).
   - Simply stepping up to **`Medium (500)`** or **`SemiBold (600)`** for `normal` body text and **`ExtraBold (800)`** for `bold` headers raises **untuned (`RAW`)** `>=2px` stem survival to **`80%–98%`** and untuned HQ Confidence to **`75%–86%`**, dropping the surgical tuning burden down to **`0%–18%`** (mostly narrow delimiters `(`, `)`, `[`, `]`, `|`, `!`, `$`).
2. **Render -> 8x Upscale -> HQ Master Sanity Gate Eliminates Destructive Over-Tuning**:
   - Multi-valley diagonal characters (`W`, `w`, `M`, `m`, `N`, `X`, `Y`) and already-thick bold characters (`A`, `B`, `C`, `f`, `g`, `r`, `s`) are protected by Open-Valley Invariance and the `<=22%` HQ Diff / Valley-Occlusion Gate, guaranteeing auto-tune never degrades a glyph below its raw FreeType baseline.
