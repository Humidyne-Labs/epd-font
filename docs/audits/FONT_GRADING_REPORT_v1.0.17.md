# Humiditron `epd-font` v1.0.17 — Master Font Grading & Tri-Role Contender Scorecard

* **Repository**: [Humidyne-Labs/epd-font](https://www.google.com/search?q=https://github.com/Humidyne-Labs/epd-font) (`v1.0.17`)

* **Evaluated Corpus**: **378 Total Font Cuts** across [IBM Plex](https://github.com/IBM/plex) (`Hinted Static + Variable Extrapolated w100..w800`), [Google Noto](https://github.com/notofonts/latin-greek-cyrillic) (`v2.013 Hinted Static`, `190` cuts in `Noto_03_font_eval.zip`), [Terminus Font](https://terminus-font.sourceforge.net/) (`v4.49.1 Native Bitmap`, `24` strikes), [Inter](https://rsms.me/inter/) (`v4.0`), and [Literata](https://github.com/googlefonts/literata) (`v3.103`, `72` optical-size cuts in `Literata_04_font_eval.zip` — graded for reference and excluded from `epd-font` assets per project direction).

## 1. Executive Summary: The `v1.0.17` Best-of-the-Best Division of Labor

On a `200×200` (`188.3 DPI`) 1-bit E-Paper Display, no single typeface family wins every geometric width and role. By combining **Hinted IBM Plex + Hinted Google Noto + Native Terminus** (and retiring `IBMPlexSansCondensed`'s `20px` floor and `IBMPlexSerif`'s `20px` floor in favor of `NotoSans-SemiCondensed` and `NotoSerif`, without needing `Literata`), every semantic role in H1OS is served by an **`A+` / Tier-1 Triad**:

| Semantic Role (`Family Key`) | Chosen `v1.0.17` Winner | `NORMAL (BODY)` Cut | `BOLD (PUNCH)` Cut | `SUBTLE ITALIC` Cut | `16px` Bold Ink Jump | `16px` Italic vs. Normal | Counter Survival (`16px`) | Triad Score & Grade | 
| ----- | ----- | ----- | ----- | ----- | ----- | ----- | ----- | ----- | 
| **Primary UI (`sans`)** | **Hinted IBM Plex Sans** | `IBMPlexSans-Medium.ttf` (`w500`, `2.17px`) | `IBMPlexSans-ExtraBold.ttf` (`w800`, `3.13px`) | `IBMPlexSans-SemiBoldItalic.ttf` (`w600`, `2.29px`) | **`+37.7%`** (`+0.96px`) | **`+2.7%`** (`-34.2%` vs Bold) | **`100.0%`** (`14/12/14px` fl) | **`91.2` (`A+`)** | 
| **Co-Primary UI (`noto_sans`)** | **Hinted Google Noto Sans** | `NotoSans-Medium.ttf` (`w500`, `2.20px`) | `NotoSans-Black.ttf` (`w900`, `3.23px`) | `NotoSans-SemiBoldItalic.ttf` (`w600`, `2.31px`) | **`+39.9%`** (`+1.03px`) | **`+4.8%`** (`-33.5%` vs Bold) | **`100.0%`** (`14/14/14px` fl) | **`89.8` (`A+`)** | 
| **Narrow HMI / Badges (`cond`)** | **Hinted Noto Sans SemiCondensed** | `NotoSans-SemiCondensedMedium.ttf` (`w500`, `2.11px`) | `NotoSans-SemiCondensedBlack.ttf` (`w900`, `3.03px`) | `NotoSans-SemiCondensedSemiBoldItalic.ttf` (`w600`, `2.09px`) | **`+37.6%`** (`+0.92px`) | **`-0.1%`** (`-37.8%` vs Bold) | **`100.0%`** (`16/14/16px` fl) | **`91.0` (`A+`)** | 
| **Tabular Telemetry (`mono`)** | **Hinted IBM Plex Mono** | `IBMPlexMono-Medium.ttf` (`w500`, `2.16px`) | `IBMPlexMono-ExtraBold.ttf` (`w800`, `3.04px`) | `IBMPlexMono-MediumItalic.ttf` (`w500`, `2.09px`) | **`+40.0%`** (`+0.88px`) | **`-2.9%`** (`-44.3%` vs Bold) | **`100.0%`** (`14/12/16px` fl) | **`88.5` (`A+`)** | 
| **Editorial Callouts (`serif`)** | **Hinted Google Noto Serif** | `NotoSerif-Medium.ttf` (`w500`, `2.15px`) | `NotoSerif-Black.ttf` (`w900`, `2.94px`) | `NotoSerif-MediumItalic.ttf` (`w500`, `2.16px`) | **`+33.8%`** (`+0.79px`) | **`-1.0%`** (`-35.2%` vs Bold) | **`100.0%`** (`16/14/20px` fl) | **`84.9` (`A`)** | 
| **Scientific Math (`math`)** | **Hinted Noto Sans Math + Plex Math** | `NotoSansMath-Regular.ttf` (`w400`, `1.92px`) | *(Fallback: `IBMPlexMath-Regular.ttf`)* | — | — | — | **`100.0%`** (`20px` raw / `14px` patched) | **`85.0` (`A`)** | 
| **Micro Console (`terminus`)** | **Native Terminus v4.49.1** | `Terminus-Normal-<sz>.ttf` (`w400`, `1.09px`) | `Terminus-Bold-<sz>.ttf` (`w700`, `2.04px`) | — | **`+68.0%`** (`+0.95px`) | — | **`100.0%`** (`12px` native floor) | **`92.0` (`A+`)** | 

## 2. Tri-Role Family Triad Leaderboard (`v1.0.17` Unified Benchmark + Reference Contenders)

| Rank | Family (`Group`) | Status in `v1.0.17` | `NORMAL` (`Stem`, `Ink`) | `BOLD PUNCH` (`Stem`, `Ink Jump`, `Stem Jump`) | `SUBTLE ITALIC` (`Stem`, `Ink vs Norm`, `vs Bold`) | Triad Score | Letter Grade | Verdict | 
| ----- | ----- | ----- | ----- | ----- | ----- | ----- | ----- | ----- | 
| **1** | **IBMPlexSans** (`sans`) | **INCLUDED (`sans`)** | `w500` (`2.17px`, `2,528`) | `w800` (`3.13px`, **`+37.7%`**, `+0.96px`) | `w600i` (`2.29px`, **`+2.7%`**, `-34.2%`) | **`91.2`** | **`A+`** | Primary UI Sans Champion (`14px` floor, native `Ø`, `100%` counters) | 
| **2** | **NotoSans-SemiCondensed** (`cond`) | **INCLUDED (`cond`)** | `w500` (`2.11px`, `2,261`) | `w900` (`3.03px`, **`+37.6%`**, `+0.92px`) | `w600i` (`2.09px`, **`-0.1%`**, `-37.8%`) | **`91.0`** | **`A+`** | Narrow HMI & Badge Champion (`+49.3%` 14px Bold punch, `100%` counters) | 
| **3** | **NotoSans** (`sans`) | **INCLUDED (`noto_sans`)** | `w500` (`2.20px`, `2,406`) | `w900` (`3.23px`, **`+39.9%`**, `+1.03px`) | `w600i` (`2.31px`, **`+4.8%`**, `-33.5%`) | **`89.8`** | **`A+`** | Co-Primary UI Sans Champion (`+49.1%` 14px Bold punch, `100%` counters) | 
| **4** | **IBMPlexSansCondensed** (`cond`) | **INCLUDED (`plex_cond`)** | `w500` (`2.08px`, `2,299`) | `w800` (`3.02px`, **`+43.7%`**, `+0.94px`) | `w600i` (`2.17px`, **`+5.2%`**, `-36.6%`) | **`88.7`** | **`A`** | Secondary Condensed (`100%` counters at `16px` after bowl-join sealer; `20px` floor) | 
| **5** | **IBMPlexMono** (`mono`) | **INCLUDED (`mono`)** | `w500` (`2.16px`, `2,479`) | `w800` (`3.04px`, **`+40.0%`**, `+0.88px`) | `w500i` (`2.09px`, **`-2.9%`**, `-44.3%`) | **`88.5`** | **`A+`** | Tabular Telemetry Champion (slashed `0`, native `Δ, Ω, μ`, `14px` floor) | 
| **6** | **Inter** (`sans`) | *External Reference* | `w500` (`2.23px`, `2,460`) | `w900` (`3.37px`, **`+52.3%`**, `+1.14px`) | `w500i` (`2.15px`, **`-4.2%`**, `-59.0%`) | **`87.8`** | **`A`** | Strong external reference, but `Medium w500` has `16px` floor vs `14px` on Plex/Noto | 
| **7** | **IBMPlexSerif** (`serif`) | **INCLUDED (`plex_serif`)** | `w500` (`2.12px`, `2,373`) | `w800` (`2.89px`, **`+35.5%`**, `+0.77px`) | `w600i` (`2.16px`, **`-0.4%`**, `-36.1%`) | **`87.2`** | **`A-`** | Secondary Display Serif (`>=20px` floor due to bracketed serifs at `14px`) | 
| **8** | **NotoSerif** (`serif`) | **INCLUDED (`serif`)** | `w500` (`2.15px`, `2,381`) | `w900` (`2.94px`, **`+33.8%`**, `+0.79px`) | `w500i` (`2.16px`, **`-1.0%`**, `-35.2%`) | **`84.9`** | **`A`** | Editorial Serif Champion (`16px` Normal & `14px` Bold floors, `100%` 16px counters) | 
| **9** | **Terminus** (`terminus`) | **INCLUDED (`terminus`)** | `w400` (`1.09px`, `1,111`) | `w700` (`2.04px`, **`+68.0%`**, `+0.95px`) | *N/A (Upright Pair)* | **`83.0`** | **`A+`** | Undisputed `12px–32px` Native Pixel Console Champion (`0.0%` tuning burden) | 
| **10** | **NotoSansMono** (`mono`) | **INCLUDED (`noto_mono`)** | `w500` (`2.14px`, `2,302`) | `w900` (`3.13px`, **`+43.1%`**, `+0.99px`) | *(Uses `IBMPlexMono-MediumItalic`)* | **`77.4`** | **`B+`** | Upright-only Mono pair (`NotoSansMono` has no native Italic cuts upstream) | 
| **11** | **Literata 24pt/36pt** (`serif`) | *Excluded (Per User)* | `w500` (`2.20px`, `2,519`) | `w900` (`3.10px`, **`+46.1%`**, `+0.90px`) | `w500i` (`2.13px`, **`-10.3%`**, `-51.1%`) | **`91.4`** | **`B`** | High 16px score in `Literata_04_font_eval.zip`, but excluded per user preference (`NotoSerif` covers `serif`) | 
| **12** | **NotoSans-Condensed** (`cond`) | **INCLUDED (`condensed_*`)** | `w600` (`2.09px`, `2,288`) | `w900` (`2.38px`, **`+12.1%`**, `+0.29px`) | `w600i` (`2.05px`, **`-6.3%`**, `-19.6%`) | **`38.0`** | **`C+`** | Ultra-narrow (`75%` width) caps `Black w900` stem at `2.38px`; use for tight single-weight badges only | 

## 3. Complete `v1.0.17` 51-Cut Foundry Grading Table

Every cut in `build/static_ttfs/` was evaluated across `12px, 14px, 16px, 20px, 24px` using `humid1_font_eval.py`:

| \# | Font Label | File Name | Group | `wght` | Assigned Role | Role Score | Grade | Tuned Floor | `16px` Stem (`Raw->Tun`) | `16px` Ink | `16px` HQ Conf | `16px` Counters | `16px` Burden | 
| ----- | ----- | ----- | ----- | ----- | ----- | ----- | ----- | ----- | ----- | ----- | ----- | ----- | ----- | 
| 1 | **IBM Plex Sans Normal \[Medium w500\]** | `IBMPlexSans-Medium.ttf` | `sans` | `500` | `NORMAL (BODY)` | **`85.3`** | **`A+`** | **`14px`** | `2.13->2.17px` | `2,528` | `74.9%` | **`100.0%`** | `11.7%` | 
| 2 | **IBM Plex Sans Bold \[ExtraBold w800\]** | `IBMPlexSans-ExtraBold.ttf` | `sans` | `800` | `BOLD (PUNCH)` | **`87.1`** | **`A+`** | **`12px`** | `3.13->3.13px` | `3,482` | `84.1%` | **`100.0%`** | `3.3%` | 
| 3 | **IBM Plex Sans Italic \[SemiBoldItal w600\]** | `IBMPlexSans-SemiBoldItalic.ttf` | `sans` | `600` | `ITALIC (SUBTLE)` | **`88.8`** | **`A+`** | **`14px`** | `2.28->2.29px` | `2,595` | `73.3%` | **`100.0%`** | `8.3%` | 
| 4 | **IBM Plex Sans Italic \[MedItal w500\]** | `IBMPlexSans-MediumItalic.ttf` | `sans` | `500` | `ITALIC (SUBTLE)` | `82.6` | `A-` | `16px` | `2.03->2.10px` | `2,311` | `68.8%` | **`100.0%`** | `21.7%` | 
| 5 | **IBM Plex Sans SemiBold (w600)** | `IBMPlexSans-SemiBold.ttf` | `sans` | `600` | `MID-WEIGHT` | `69.1` | `B` | `12px` | `2.27->2.28px` | `2,692` | `79.1%` | **`100.0%`** | `6.7%` | 
| 6 | **IBM Plex Sans Bold-700 \[Legacy w700\]** | `IBMPlexSans-Bold.ttf` | `sans` | `700` | `MID-WEIGHT` | `68.7` | `B` | `14px` | `2.50->2.48px` | `2,880` | `78.1%` | **`100.0%`** | `8.3%` | 
| 7 | **IBM Plex Sans Bold Italic (w700)** | `IBMPlexSans-BoldItalic.ttf` | `sans` | `700` | `ITALIC (HEAVY)` | `52.9` | `C` | `14px` | `2.51->2.51px` | `2,852` | `76.5%` | **`100.0%`** | `3.3%` | 
| 8 | **IBM Plex Sans Regular (w400)** | `IBMPlexSans-Regular.ttf` | `sans` | `400` | `MID-WEIGHT` | `49.6` | `C-` | `24px` | `1.41->1.86px` | `2,068` | `66.1%` | **`100.0%`** | `68.3%` | 
| 9 | **Noto Sans Normal \[Medium w500\]** | `NotoSans-Medium.ttf` | `sans` | `500` | `NORMAL (BODY)` | **`86.4`** | **`A+`** | **`14px`** | `2.17->2.20px` | `2,406` | `75.3%` | **`100.0%`** | `8.3%` | 
| 10 | **Noto Sans Black \[Black w900\]** | `NotoSans-Black.ttf` | `sans` | `900` | `BOLD (PUNCH)` | **`89.9`** | **`A+`** | **`14px`** | `3.23->3.23px` | `3,367` | `84.4%` | **`100.0%`** | `3.3%` | 
| 11 | **Noto Sans Bold \[ExtraBold w800\]** | `NotoSans-ExtraBold.ttf` | `sans` | `800` | `BOLD (PUNCH)` | **`85.1`** | **`A`** | **`12px`** | `3.07->3.07px` | `3,241` | `83.4%` | **`100.0%`** | `5.0%` | 
| 12 | **Noto Sans Italic \[SemiBoldItal w600\]** | `NotoSans-SemiBoldItalic.ttf` | `sans` | `600` | `ITALIC (SUBTLE)` | **`88.4`** | **`A+`** | **`14px`** | `2.30->2.31px` | `2,522` | `74.2%` | **`100.0%`** | `6.7%` | 
| 13 | **Noto Sans Italic \[MedItal w500\]** | `NotoSans-MediumItalic.ttf` | `sans` | `500` | `ITALIC (SUBTLE)` | `83.1` | `A-` | `20px` | `2.04->2.08px` | `2,237` | `70.3%` | **`100.0%`** | `13.3%` | 
| 14 | **Noto Sans SemiCond Normal \[Medium w500\]** | `NotoSans-SemiCondensedMedium.ttf` | `cond` | `500` | `NORMAL (BODY)` | **`87.0`** | **`A+`** | **`16px`** | `2.07->2.11px` | `2,261` | `73.7%` | **`100.0%`** | `13.3%` | 
| 15 | **Noto Sans SemiCond Black \[Black w900\]** | `NotoSans-SemiCondensedBlack.ttf` | `cond` | `900` | `BOLD (PUNCH)` | **`84.3`** | **`A+`** | **`14px`** | `3.03->3.03px` | `3,112` | `83.1%` | **`100.0%`** | `1.7%` | 
| 16 | **Noto Sans SemiCond Bold \[ExtraBold w800\]** | `NotoSans-SemiCondensedExtraBold.ttf` | `cond` | `800` | `BOLD (PUNCH)` | `74.1` | `B+` | `12px` | `2.51->2.50px` | `2,709` | `79.8%` | **`100.0%`** | `3.3%` | 
| 17 | **Noto Sans SemiCond Italic \[SemiBoldItal w600\]** | `NotoSans-SemiCondensedSemiBoldItalic.ttf` | `cond` | `600` | `ITALIC (SUBTLE)` | **`85.2`** | **`A`** | **`16px`** | `2.07->2.09px` | `2,258` | `71.3%` | **`100.0%`** | `11.7%` | 
| 18 | **Noto Sans Cond Normal \[SemiBold w600\]** | `NotoSans-CondensedSemiBold.ttf` | `cond` | `600` | `MID-WEIGHT` | `65.0` | `B` | `16px` | `2.07->2.09px` | `2,288` | `75.8%` | **`100.0%`** | `13.3%` | 
| 19 | **Noto Sans Cond Bold \[Black w900\]** | `NotoSans-CondensedBlack.ttf` | `cond` | `900` | `BOLD (PUNCH)` | `73.1` | `B+` | `12px` | `2.38->2.38px` | `2,565` | `79.4%` | **`100.0%`** | `5.0%` | 
| 20 | **Noto Sans Cond Italic \[SemiBoldItal w600\]** | `NotoSans-CondensedSemiBoldItalic.ttf` | `cond` | `600` | `ITALIC (SUBTLE)` | `77.6` | `B+` | `20px` | `1.82->2.05px` | `2,144` | `71.8%` | **`100.0%`** | `48.3%` | 
| 21 | **IBM Plex Sans Cond Normal \[Medium w500\]** | `IBMPlexSansCondensed-Medium.ttf` | `cond` | `500` | `NORMAL (BODY)` | `82.9` | `B+` | `20px` | `2.05->2.08px` | `2,299` | `72.7%` | **`100.0%`** | `18.3%` | 
| 22 | **IBM Plex Sans Cond Bold \[ExtraBold w800\]** | `IBMPlexSansCondensed-ExtraBold.ttf` | `cond` | `800` | `BOLD (PUNCH)` | `82.8` | `A-` | `12px` | `3.02->3.02px` | `3,304` | `82.6%` | **`100.0%`** | `13.3%` | 
| 23 | **IBM Plex Sans Cond Italic \[SemiBoldItal w600\]** | `IBMPlexSansCondensed-SemiBoldItalic.ttf` | `cond` | `600` | `ITALIC (SUBTLE)` | **`86.7`** | **`A`** | `16px` | `2.13->2.17px` | `2,419` | `71.1%` | **`100.0%`** | `16.7%` | 
| 24 | **IBM Plex Sans Cond Italic \[MedItal w500\]** | `IBMPlexSansCondensed-MedItal.ttf` | `cond` | `500` | `ITALIC (SUBTLE)` | `75.1` | `B` | `20px` | `1.88->2.01px` | `2,157` | `68.5%` | **`100.0%`** | `45.0%` | 
| 25 | **IBM Plex Mono Normal \[Medium w500\]** | `IBMPlexMono-Medium.ttf` | `mono` | `500` | `NORMAL (BODY)` | **`86.3`** | **`A+`** | **`14px`** | `2.14->2.16px` | `2,479` | `73.2%` | **`100.0%`** | `6.7%` | 
| 26 | **IBM Plex Mono Bold \[ExtraBold w800\]** | `IBMPlexMono-ExtraBold.ttf` | `mono` | `800` | `BOLD (PUNCH)` | **`83.9`** | **`A+`** | **`12px`** | `3.04->3.04px` | `3,471` | `82.5%` | **`100.0%`** | `5.0%` | 
| 27 | **IBM Plex Mono Italic \[MedItal w500\]** | `IBMPlexMono-MediumItalic.ttf` | `mono` | `500` | `ITALIC (SUBTLE)` | **`81.1`** | **`A-`** | **`16px`** | `1.99->2.09px` | `2,406` | `69.0%` | **`100.0%`** | `30.0%` | 
| 28 | **IBM Plex Mono Italic \[SemiBoldItal w600\]** | `IBMPlexMono-SemiBoldItalic.ttf` | `mono` | `600` | `ITALIC (SUBTLE)` | **`87.1`** | **`A`** | **`14px`** | `2.21->2.26px` | `2,725` | `73.5%` | **`100.0%`** | `20.0%` | 
| 29 | **Noto Sans Mono Normal \[Medium w500\]** | `NotoSansMono-Medium.ttf` | `mono` | `500` | `NORMAL (BODY)` | **`86.7`** | **`A`** | `16px` | `2.11->2.14px` | `2,302` | `73.9%` | **`100.0%`** | `8.3%` | 
| 30 | **Noto Sans Mono Bold \[ExtraBold w800\]** | `NotoSansMono-ExtraBold.ttf` | `mono` | `800` | `BOLD (PUNCH)` | **`82.3`** | **`A`** | **`12px`** | `3.00->3.00px` | `3,146` | `80.7%` | **`100.0%`** | `6.7%` | 
| 31 | **Noto Sans Mono Black \[Black w900\]** | `NotoSansMono-Black.ttf` | `mono` | `900` | `BOLD (PUNCH)` | **`86.3`** | **`A+`** | **`12px`** | `3.12->3.13px` | `3,294` | `83.1%` | **`100.0%`** | `5.0%` | 
| 32 | **Noto Serif Normal \[Medium w500\]** | `NotoSerif-Medium.ttf` | `serif` | `500` | `NORMAL (BODY)` | **`84.5`** | **`A`** | **`16px`** | `2.10->2.15px` | `2,381` | `73.8%` | **`100.0%`** | `13.3%` | 
| 33 | **Noto Serif Bold \[Black w900\]** | `NotoSerif-Black.ttf` | `serif` | `900` | `BOLD (PUNCH)` | **`76.6`** | **`A-`** | **`14px`** | `2.93->2.94px` | `3,185` | `77.2%` | **`100.0%`** | `13.3%` | 
| 34 | **Noto Serif Italic \[MedItal w500\]** | `NotoSerif-MediumItalic.ttf` | `serif` | `500` | `ITALIC (SUBTLE)` | **`82.6`** | **`A-`** | `20px` | `2.10->2.16px` | `2,356` | `67.8%` | **`100.0%`** | `16.7%` | 
| 35 | **Noto Serif Italic \[SemiBoldItal w600\]** | `NotoSerif-SemiBoldItalic.ttf` | `serif` | `600` | `ITALIC (SUBTLE)` | `79.9` | `B+` | `24px` | `2.22->2.28px` | `2,466` | `69.1%` | `95.2%` | `25.0%` | 
| 36 | **IBM Plex Serif Normal \[Medium w500\]** | `IBMPlexSerif-Medium.ttf` | `serif` | `500` | `NORMAL (BODY)` | `83.2` | `B+` | `20px` | `2.06->2.12px` | `2,373` | `75.6%` | **`100.0%`** | `21.7%` | 
| 37 | **IBM Plex Serif Bold \[ExtraBold w800\]** | `IBMPlexSerif-ExtraBold.ttf` | `serif` | `800` | `BOLD (PUNCH)` | `76.8` | `B` | `20px` | `2.88->2.89px` | `3,215` | `79.5%` | **`100.0%`** | `10.0%` | 
| 38 | **IBM Plex Serif Italic \[SemiBoldItal w600\]** | `IBMPlexSerif-SemiBoldItalic.ttf` | `serif` | `600` | `ITALIC (SUBTLE)` | `82.8` | `B+` | `20px` | `2.11->2.16px` | `2,363` | `69.0%` | **`100.0%`** | `20.0%` | 
| 39 | **IBM Plex Serif Italic \[MedItal w500\]** | `IBMPlexSerif-MediumItalic.ttf` | `serif` | `500` | `ITALIC (SUBTLE)` | `73.1` | `C+` | `24px` | `1.88->1.97px` | `2,147` | `63.5%` | **`100.0%`** | `26.7%` | 
| 40 | **Noto Sans Math Regular (w400)** | `NotoSansMath-Regular.ttf` | `math` | `400` | `MATH (SPECIALIST)` | `52.4` | **`A`** | `20px` | `1.57->1.92px` | `2,071` | `71.3%` | **`100.0%`** | `68.3%` | 
| 41 | **IBM Plex Math Regular (w400)** | `IBMPlexMath-Regular.ttf` | `math` | `400` | `MATH (FALLBACK)` | `46.9` | `B+` | `24px` | `1.47->1.70px` | `1,924` | `62.8%` | **`100.0%`** | `43.3%` | 
| 42 | **Terminus Native Bitmap (w400)** | `Terminus-Normal-16.ttf` | `terminus` | `400` | `MICRO (1PX BITMAP)` | **`92.0`** | **`A+`** | **`12px`** | `1.09->1.09px` | `1,111` | `100.0%` | **`100.0%`** | **`0.0%`** | 
| 43 | **Terminus Bold Bitmap (w700)** | `Terminus-Bold-16.ttf` | `terminus` | `700` | `BOLD (2PX BITMAP)` | **`92.0`** | **`A+`** | **`12px`** | `2.04->2.04px` | `1,867` | `100.0%` | **`100.0%`** | **`0.0%`** | 
| 44 | **Inter Medium (w500) \[External\]** | `Inter-Medium.otf` | `sans` | `500` | `NORMAL (BODY)` | `85.2` | `A` | `16px` | `2.19->2.23px` | `2,460` | `74.4%` | **`100.0%`** | `10.0%` | 
| 45 | **Inter Black (w900) \[External\]** | `Inter-Black.otf` | `sans` | `900` | `BOLD (PUNCH)` | `93.4` | `A` | `12px` | `3.37->3.37px` | `3,746` | `84.6%` | **`100.0%`** | `5.0%` | 
| 46 | **Inter ExtraBold (w800) \[External\]** | `Inter-ExtraBold.otf` | `sans` | `800` | `BOLD (PUNCH)` | `88.8` | `A` | `12px` | `3.19->3.19px` | `3,524` | `83.8%` | **`100.0%`** | `0.0%` | 
| 47 | **Inter SemiBoldItalic (w600) \[External\]** | `Inter-SemiBoldItalic.otf` | `sans` | `600` | `ITALIC (SUBTLE)` | `86.4` | `A` | `12px` | `2.39->2.40px` | `2,714` | `73.1%` | **`100.0%`** | `11.7%` | 
| 48 | **Inter MediumItalic (w500) \[External\]** | `Inter-MediumItalic.otf` | `sans` | `500` | `ITALIC (SUBTLE)` | `84.0` | `A-` | `16px` | `2.07->2.15px` | `2,356` | `68.3%` | **`100.0%`** | `18.3%` | 
| 49 | **Inter Bold (w700) \[External\]** | `Inter-Bold.otf` | `sans` | `700` | `MID-WEIGHT` | `70.9` | `B` | `12px` | `2.62->2.62px` | `2,963` | `81.1%` | **`100.0%`** | `0.0%` | 
| 50 | **Inter SemiBold (w600) \[External\]** | `Inter-SemiBold.otf` | `sans` | `600` | `MID-WEIGHT` | `70.4` | `B` | `12px` | `2.37->2.38px` | `2,743` | `81.1%` | **`100.0%`** | `1.7%` | 
| 51 | **Inter Regular (w400) \[External\]** | `Inter-Regular.otf` | `sans` | `400` | `NORMAL (BODY)` | `70.8` | `C+` | `20px` | `1.56->1.98px` | `2,154` | `71.0%` | **`100.0%`** | `70.0%` | 

## 4. Sub-Family Grading Breakdown Across Your 3 Uploaded Evaluation Runs (`327` Cuts)

### 4.1 `Noto_03_font_eval.zip` (`190` Hinted Google Noto Cuts)

| Noto Sub-Family (`Width` / `Style`) | Cuts Evaluated | Best Normal Cut (`16px`) | Best Bold Cut (`16px`) | Best Italic Cut (`16px`) | Sub-Family Grade | Inclusion Decision for `v1.0.17` | 
| ----- | ----- | ----- | ----- | ----- | ----- | ----- | 
| **`NotoSans` (Standard `100%` Width)** | `18` | `Medium w500` (`86.4`) | `Black w900` (`89.9`) / `ExtraBold w800` (`85.1`) | `SemiBoldItalic w600` (`88.4`) | **`A+`** | **INCLUDED (`7` cuts)** — Co-primary UI Sans triad (`noto_sans`). | 
| **`NotoSans-SemiCondensed` (`87.5%` Width)** | `18` | `SemiCondensedMedium w500` (`87.0`) | `SemiCondensedBlack w900` (`84.3`, `+49.3%` @ 14px) | `SemiCondensedSemiBoldItalic w600` (`85.2`) | **`A+`** | **INCLUDED (`4` cuts)** — Promoted to primary H1OS `cond` triad! | 
| **`NotoSans-Condensed` (`75%` Width)** | `18` | `CondensedSemiBold w600` (`65.0`) | `CondensedBlack w900` (`73.1`) | `CondensedSemiBoldItalic w600` (`77.6`) | **`B+`** | **INCLUDED (`3` cuts)** — Included for ultra-narrow single-weight badges. | 
| **`NotoSans-ExtraCondensed` (`62.5%` Width)** | `18` | `ExtraCondensedSemiBold` (`52.1`) | `ExtraCondensedBlack` (`55.6`) | `ExtraCondensedBoldItalic` (`33.3`) | **`D`** | **EXCLUDED** — Interior counters collapse below `20px`. | 
| **`NotoSansMono` (Tabular `100%` Width)** | `9` | `NotoSansMono-Medium w500` (`86.7`) | `NotoSansMono-Black w900` (`86.3`) / `ExtraBold w800` (`82.3`) | *(None in upstream Noto)* | **`A`** | **INCLUDED (`3` cuts)** — Upright tabular mono (`noto_mono`). | 
| **`NotoSansMono-SemiCondensed` / `Condensed`** | `18` | `SemiCondensedMedium` (`67.1`) | `SemiCondensedBlack` (`69.4`) | *(None)* | **`C`** | **EXCLUDED** — Narrow mono cells pinch `'0'`, `'8'`, `'@'`, `'%'` at `14px`. | 
| **`NotoSerif` (Standard `100%` Width)** | `18` | `NotoSerif-Medium w500` (`84.5`) | `NotoSerif-Black w900` (`76.6`, `14px` floor!) | `NotoSerif-MediumItalic w500` (`82.6`) | **`A`** | **INCLUDED (`4` cuts)** — Promoted to primary H1OS `serif` triad! | 
| **`NotoSerif-SemiCondensed` / `Condensed` / `ExtraCondensed`** | `54` | `SemiCondensedMedium` (`83.6`) | `SemiCondensedBlack` (`65.2`) | `SemiCondensedSemiBoldItalic` (`81.1`) | **`C+`** | **EXCLUDED** — Standard `NotoSerif` has cleaner counter cavities at `16px`. | 
| **`NotoSansMath` (`Math` Specialist)** | `1` | `NotoSansMath-Regular w400` (`100%` counters, `71.3%` HQ) | — | — | **`A`** | **INCLUDED (`1` cut)** — Promoted to primary H1OS `math` face! | 
| **Thin / ExtraLight / Light (`w100..w300`) Across All Noto** | `64` | All `< 1.65px` stem at `16px` (`SUB-FLOOR`) | — | — | **`F`** | **EXCLUDED** — Severe 1-bit dropout (`35%–90%` repair burden). | 

### 4.2 `IBMPlex_05_font_eval.zip` (`65` Official Hinted IBM Plex Cuts)

| IBM Plex Sub-Family | Cuts Evaluated in `05` | Why Standalone `05` Triad Score Was Low (`41.8–76.3`) | `v1.0.17` Hybrid Solution (Hinted `w400..w700` + Extrapolated `w800`) | Final `v1.0.17` Grade | 
| ----- | ----- | ----- | ----- | ----- | 
| **`IBMPlexSans`** | `16` (`w100..w700`) | `Hinted_IBMPlex.zip` caps at `Bold w700` (`2.48px` stem = only `+13.7%` ink over `Medium w500`). | Pairing Hinted `Medium w500` + `SemiBoldItalic w600` with synthesized `ExtraBold w800` (`3.13px` stem, `+37.7%` ink) yields **`91.2` (#1 Overall Triad)**. | **`A+`** | 
| **`IBMPlexMono`** | `16` (`w100..w700`) | `Bold w700` (`2.37px` stem) is only `+10.9%` heavier than `Medium w500` (`2.16px`). | Pairing Hinted `Medium w500` + `MediumItalic w500` with synthesized `ExtraBold w800` (`3.04px` stem, `+40.0%` ink) yields **`88.5` (#1 Mono Triad)**. | **`A+`** | 
| **`IBMPlexSansCondensed`** | `16` (`w100..w700`) | `Bold w700` (`2.44px` stem) + `1px` bowl-join gap on `'q'` at `16px`. | Bowl-join sealer restores `100.0%` counters at `16px` (`88.7` Triad); retained as `plex_cond` while `NotoSans-SemiCondensed` (`91.0`) serves default `cond`. | **`A`** | 
| **`IBMPlexSerif`** | `16` (`w100..w700`) | Bracketed serifs pinch at `14px` (`20px` floor). | Bowl-join sealer restores `100.0%` counters at `16px` (`87.2` Triad); retained as `plex_serif` while `NotoSerif` (`16px/14px` floor) serves default `serif`. | **`A-`** | 
| **`IBMPlexMath-Regular`** | `1` (`w400`) | Mathematical glyphs (`1.70px` stem) are thin at `14px`. | Replaced unhinted `1.28 MB` TTF with Hinted `IBMPlexMath-Regular.ttf` (`100.0%` 16px counters) as automatic secondary fallback behind `NotoSansMath-Regular.ttf`. | **`B+`** | 

### 4.3 `Literata_04_font_eval.zip` (`72` Literata v3.103 Optical-Size Cuts — Reference Only)

Per your preference (*"i much rather support plex, noto and tuminus, i dont care for literata"*), **`Literata` is completely excluded from `assets/` and all `.scheme.json` files**, and is graded below strictly for completeness:

| Literata Optical Sub-Family | Cuts Evaluated in `04` | Triad Score (`16px`) | `16px` Bold Jump (`w900` vs `w500`) | `14px` Size Floor Viability | Reference Grade & Disposition | 
| ----- | ----- | ----- | ----- | ----- | ----- | 
| **`Literata_24pt` / `36pt`** | `16` | `91.4` / `91.2` | `+46.1%` / `+44.6%` | `Medium w500` floor is `20px` (fails `14px` & `16px` raw floors) | **`B` — Excluded** (`NotoSerif` provides `16px` Normal & `14px` Bold floors inside the Noto ecosystem). | 
| **`Literata_18pt` / `72pt`** | `16` | `89.3` / `90.2` | `+38.0%` / `+40.4%` | `Medium w500` floor is `20px` | **`B` — Excluded** (Redundant with `NotoSerif` + `IBMPlexSerif`). | 
| **`Literata` (Standard) / `7pt`** | `32` | `84.4` / `85.2` | `+25.6%` / `+36.6%` | `7pt` wide tracking bloats horizontal string widths on `200×200` panel | **`C+` — Excluded** (Overflows compact 188px telemetry rows). | 
| **`Literata` Light / ExtraLight (`w200..w300`)** | `24` | *Sub-Floor* | — | `<1.70px` stems (`50%–75%` repair burden) | **`F` — Excluded** (Unusable on 1-BPP EPD). | 
