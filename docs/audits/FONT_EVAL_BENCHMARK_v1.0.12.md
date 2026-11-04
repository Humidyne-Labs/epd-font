# Humiditron `epd-font` v1.0.12 — Multi-Font & Weight Hierarchy Benchmark Report

## 1. Executive Summary & Minimum Viable Pixel Size Floors

Each candidate typeface and weight was evaluated across `10px, 12px, 14px, 16px, 20px` both **Before (`Raw`)** and **After (`Tuned`)** the v1.0.12 Multi-Method Iterative Typographic Tournament (`M0..M8` + Bilateral Mirror Synchronization).

| Typeface & Role Label | Source Font File | Weight (`wght`) | Raw Size Floor (`px`) | Tuned Size Floor (`px`) | 14px `>=2px` Stems (`Raw -> Tuned`) | 16px `>=2px` Stems (`Raw -> Tuned`) | 16px Counter Survival | 16px Mean Stem (`px`) | 16px Total Ink (`px`) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **IBM Plex Sans Regular (400)** | `IBMPlexSans-Regular.ttf` | `400` | `>20px` | **`16px`** | `10.5% -> 87.7%` | `8.8% -> 98.2%` | `100.0%` | `2.19px` | `2,299` |
| **IBM Plex Sans Normal [Medium 500]** | `IBMPlexSans-Medium.ttf` | `500` | `20px` | **`10px`** | `71.9% -> 96.5%` | `78.9% -> 98.2%` | `100.0%` | `2.26px` | `2,533` |
| **IBM Plex Sans Bold-700 [Legacy]** | `IBMPlexSans-Bold.ttf` | `700` | `14px` | **`10px`** | `93.0% -> 96.5%` | `94.7% -> 98.2%` | `100.0%` | `2.54px` | `2,762` |
| **IBM Plex Sans Bold [ExtraBold 800]** | `IBMPlexSans-ExtraBold.ttf` | `800` | `12px` | **`10px`** | `96.5% -> 98.2%` | `94.7% -> 100.0%` | `100.0%` | `3.11px` | `3,321` |
| **IBM Plex Sans Italic [MedItal 500]** | `IBMPlexSans-MediumItalic.ttf` | `500` | `20px` | **`12px`** | `14.0% -> 89.5%` | `42.1% -> 94.7%` | `100.0%` | `2.28px` | `2,426` |
| **IBM Plex Mono Normal [Medium 500]** | `IBMPlexMono-Medium.ttf` | `500` | `20px` | **`10px`** | `66.7% -> 96.5%` | `80.7% -> 100.0%` | `100.0%` | `2.25px` | `2,478` |
| **IBM Plex Mono Bold [ExtraBold 800]** | `IBMPlexMono-ExtraBold.ttf` | `800` | `12px` | **`10px`** | `96.5% -> 100.0%` | `93.0% -> 100.0%` | `100.0%` | `3.05px` | `3,307` |
| **IBM Plex Serif Normal [Medium 500]** | `IBMPlexSerif-Medium.ttf` | `500` | `>20px` | **`10px`** | `49.1% -> 93.0%` | `61.4% -> 98.2%` | `95.2%` | `2.31px` | `2,432` |
| **IBM Plex Serif Bold [ExtraBold 800]** | `IBMPlexSerif-ExtraBold.ttf` | `800` | `20px` | **`10px`** | `77.2% -> 98.2%` | `78.9% -> 100.0%` | `95.2%` | `2.99px` | `3,163` |
| **IBM Plex Math Regular (400)** | `IBMPlexMath-Regular.ttf` | `400` | `>20px` | **`16px`** | `8.8% -> 77.2%` | `8.8% -> 89.5%` | `100.0%` | `2.26px` | `2,402` |
| **Terminus Native Bitmap (400)** | `Terminus-Normal-16.ttf` | `400` | `12px` | **`12px`** | `100.0% -> 100.0%` | `100.0% -> 100.0%` | `100.0%` | `1.09px` | `1,056` |
| **Inter Medium (500) [External]** | `Inter-Medium.otf` | `500` | `16px` | **`10px`** | `31.6% -> 98.2%` | `82.5% -> 100.0%` | `100.0%` | `2.29px` | `2,422` |
| **Inter ExtraBold (800) [External]** | `Inter-ExtraBold.otf` | `800` | `10px` | **`10px`** | `96.5% -> 98.2%` | `96.5% -> 98.2%` | `100.0%` | `3.18px` | `3,346` |

## 2. 3-Tier Weight Hierarchy Analysis (`normal = Medium 500`, `bold = ExtraBold 800`, `italic = MediumItalic 500`)

In `v1.0.10–v1.0.11`, promoting `normal` from `Regular (400)` to `Medium (500)` improved baseline readability, but left `normal (500)` and `bold (700)` visually nearly identical at `12px–16px` because both `wght=500` and `wght=700` quantize to `2px` vertical stems on a 1-BPP grid. Synthesizing **`ExtraBold (800)`** (`1.45x` horizontal `gvar` weight delta, `1.18x` vertical crossbar delta) and mapping `bold -> ExtraBold (800)` restores a clear, unmistakable 3-tier hierarchy:

| Size (`px`) | `Regular (400)` Ink | `normal = Medium (500)` Ink | Legacy `Bold (700)` Ink (`vs Medium`) | New `bold = ExtraBold (800)` Ink (`vs Medium`) | `italic = MediumItalic (500)` Ink |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **10px** | `1,221 px` | `1,246 px` | `1,443 px (+15.8%)` | **`1,457 px (+16.9%)`** | `1,223 px` |
| **12px** | `1,447 px` | `1,646 px` | `1,883 px (+14.4%)` | **`1,923 px (+16.8%)`** | `1,702 px` |
| **14px** | `1,958 px` | `1,976 px` | `2,213 px (+12.0%)` | **`2,714 px (+37.3%)`** | `1,962 px` |
| **16px** | `2,299 px` | `2,533 px` | `2,762 px (+9.0%)` | **`3,321 px (+31.1%)`** | `2,426 px` |
| **20px** | `2,803 px` | `3,262 px` | `4,152 px (+27.3%)` | **`4,839 px (+48.3%)`** | `3,207 px` |
