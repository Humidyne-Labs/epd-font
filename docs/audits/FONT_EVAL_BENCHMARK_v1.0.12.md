# Humiditron `epd-font` v1.0.12 — Multi-Font & Weight Hierarchy Benchmark Report

## 1. Executive Summary & Minimum Viable Pixel Size Floors

Each candidate typeface and weight was evaluated across `10px, 12px, 14px, 16px, 20px` both **Before (`Raw`)** and **After (`Tuned`)** the v1.0.12 Multi-Method Iterative Typographic Tournament (`M0..M8` + Bilateral Mirror Synchronization).

| Typeface & Role Label | Source Font File | Weight (`wght`) | Raw Size Floor (`px`) | Tuned Size Floor (`px`) | 14px `>=2px` Stems (`Raw -> Tuned`) | 16px `>=2px` Stems (`Raw -> Tuned`) | 16px Counter Survival | 16px Mean Stem (`px`) | 16px Total Ink (`px`) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |

## 2. 3-Tier Weight Hierarchy Analysis (`normal = Medium 500`, `bold = ExtraBold 800`, `italic = MediumItalic 500`)

In `v1.0.10–v1.0.11`, promoting `normal` from `Regular (400)` to `Medium (500)` improved baseline readability, but left `normal (500)` and `bold (700)` visually nearly identical at `12px–16px` because both `wght=500` and `wght=700` quantize to `2px` vertical stems on a 1-BPP grid. Synthesizing **`ExtraBold (800)`** (`1.45x` horizontal `gvar` weight delta, `1.18x` vertical crossbar delta) and mapping `bold -> ExtraBold (800)` restores a clear, unmistakable 3-tier hierarchy:

| Size (`px`) | `Regular (400)` Ink | `normal = Medium (500)` Ink | Legacy `Bold (700)` Ink (`vs Medium`) | New `bold = ExtraBold (800)` Ink (`vs Medium`) | `italic = MediumItalic (500)` Ink |
| :---: | :---: | :---: | :---: | :---: | :---: |
