# Formal Typography & Maintainer Specification — `epd-font` (v1.0.13)

**Document ID**: `HUMIDITRON-SPEC-EPD-FONT-1.0.13`  
**Repository**: `https://github.com/Humidyne-Labs/epd-font`  
**License**: MIT License (Tooling & C Emitter) / SIL OFL 1.1 / CC-BY-4.0 / ISC / MIT (Upstream Fonts)

---

## 1. Architectural Overview

`epd-font` v1.0.13 separates raw upstream font curation (`assets/`), intermediate TrueType & metadata synthesis (`build/static_ttfs/` and `build/metadata/`), optical pixel-grid patching (`font_icon_epd_patches.json` + `build/<workflow>/ascii_patches/`), and zero-dependency firmware emission (`dist/<workflow>_distro/`).

### 1.1 Supported Typeface & Icon Families (56 Static `.ttf` Cuts)

| Family Key (`scheme.json`) | Upstream Source | Static `.ttf` Cuts (`build/static_ttfs/`) | Recommended 1-BPP Floor | License |
| :--- | :--- | :--- | :--- | :--- |
| `"sans"` | IBM Plex Sans v0.2.0 (`wdth=100`) | 13 cuts (`Thin 100` .. `Bold 700` + Italics) | `12 px` (`10 px` min) | SIL OFL 1.1 |
| `"cond"` | IBM Plex Sans Condensed (`wdth=85`) | 9 cuts (`Light 300` .. `Bold 700` + Italics) | `14 px` (`12 px` min) | SIL OFL 1.1 |
| `"mono"` | IBM Plex Mono v1.0.0 | 9 cuts (`Light 300` .. `Bold 700` + Italics) | `12 px` (`10 px` min) | SIL OFL 1.1 |
| `"serif"` | IBM Plex Serif v2.0.0 | 9 cuts (`Light 300` .. `Bold 700` + Italics) | `16 px` (`18 px` rec) | SIL OFL 1.1 |
| `"math"` | IBM Plex Math v1.1.0 | 1 cut (`IBMPlexMath-Regular.ttf`, 4,382 codepoints) | `14 px` (`16 px` rec) | SIL OFL 1.1 |
| `"terminus"` | Terminus Font v4.49.1 (`ter-u16n/b.bdf`) | 2 cuts (`Terminus-Regular.ttf`, `Terminus-Bold.ttf`, 1,356 glyphs) | `12 px` (native 12–32px) | SIL OFL 1.1 |
| `"icon_fa7"` | Font Awesome Free v7.3.1 | 3 cuts (`Solid`, `Regular`, `Brands` — 2,396 icons) | `12 px` (`14 px` rec) | CC-BY-4.0 / OFL-1.1 |
| `"icon_lucide"` | Lucide Icons v1.16.0 | 1 cut (`Lucide-Regular.ttf` — 2,043 icons) | `12 px` (`14 px` rec) | ISC |
| `"icon_phosphor"` | Phosphor Icons v2.1.0 | 5 cuts (`Thin`, `Light`, `Regular`, `Bold`, `Fill` — 1,513 icons) | `12 px` (`14 px` rec) | MIT |
| `"icon_tabler"` | Tabler Icons v3.41.1 | 4 cuts (`Thin200`, `Light300`, `Regular`, `Filled` — 6,257 icons) | `12 px` (`14 px` rec) | MIT |

---

## 2. PUA Sanitization & Semantic Glyph Naming (`Phosphor-*.ttf`)

Upstream `Phosphor*.ttf` binaries include 30 zero-width (`0×0` bounding box, `0` advance width) ASCII characters (`0x0020..0x007A`, including `0x0069 'i'`) in their `cmap` table to act as OpenType `GSUB` ligature anchors on desktop platforms, while storing all `1,513` real icons in the Private Use Area (`0xE000..0xEE83`) under generic `uniE000` glyph names.

In `v1.0.13`, `build_static_ttf_assets.py` enforces two invariants on all icon `.ttf` binaries:
1. **Non-PUA Ligature Stub Stripping (`strip_non_pua=True`)**: All `cmap` entries with `cp < 0xE000` are stripped from icon `.ttf` binaries during static asset compilation.
2. **Self-Describing Semantic Glyph Names**: `build_static_ttf_assets.py` reads `assets/icon_assets/phosphor_icons_v2.1.0/metadata/selection.json` and bakes the human-readable icon names (`"alarm"`, `"wifi-high"`, `"battery-full"`) directly into the `glyf`, `hmtx`, `cmap`, and `post` tables of every `Phosphor-*.ttf` binary as well as `build/metadata/phosphor_catalog.json`.

---

## 3. Terminus v4.49.1 BDF-to-TTF Synthesis

To provide an ultra-crisp terminal/console font alongside IBM Plex while maintaining a 100% unified TrueType (`.ttf`) pipeline, `build_static_ttf_assets.py` extracts `ter-u16n.bdf` and `ter-u16b.bdf` from `assets/font_assets/terminus-font-4.49.1.tar.gz` and converts every horizontal pixel run into an exact clockwise quadratic TrueType contour (`UPEM = 1024`, `scale = 64 font units/pixel`, `ascent = +768`, `descent = -256`). When `humid1_generate_1bpp.py` rasterizes `"family": "terminus"`, it automatically selects `bytecode-mono` (unhinted exact grid sampling) so `12, 14, 16, 18, 20, 24, 28, 32` px strikes reproduce bit-exact pixel geometry.


## Authoritative Script Execution Order (`00`–`08` & `99`)

Each workflow folder (`scripts/h1os-build-distro/`, `scripts/example-build-distro/`, and `scripts/full-audit-build-distro/`) provides numbered Windows `.bat` launchers designed around an **ASCII-Patch-Centric Iterative Tuning Loop**:

```text
  [00_setup_env.bat]             (One-time Python dependency installation: fonttools, Pillow, freetype-py, numpy, opencv-python)
          │
          ▼
  [01_build_static_ttfs.bat]     (Instantiate 88 static .ttf files -> build/static_ttfs/ + JSON catalogs -> build/metadata/)
          │
          ▼
  [04_dump_ascii_patches.bat]    (Dump baseline 1-BPP strikes -> build/<target>/ascii_patches/<symbol>/U+XXXX_<name>.txt)
          │
          ▼
  [08_iterative_auto_repair.bat] (Run 8-Method HQ Typographic Tournament on ascii_patches/ -> rewrite tuned .txt files
          │                       with `patched: 1` + render Before/After sheets in build/<target>/inspect_repairs/)
          ▼
  [05_apply_ascii_patches.bat]   (Compile all modified/tuned .txt files from ascii_patches/ -> root font_icon_epd_patches.json)
          │
          ▼
  [02_build_fonts.bat]           (Compile LVGL .c/.h modules, BDFs, Strike Vault & total_disk_size.txt with patches applied)
          │
          ▼
  [03_visual_check_pngs.bat]     (Render inspect_pages/*.png [with green PATCHED: N/Total banner] & inspect_chars/*/*.png)
          │
          ▼
  [07_package_distro.bat]        (Package drop-in firmware bundle -> dist/<target>_distro/)
```

### How to Run (Two Supported Workflows)

1. **Automated One-Click Full Pipeline (`99_run_full_pipeline.bat`)**:
   Double-click or run `99_run_full_pipeline.bat`. It automatically runs `01 -> 04 -> 08 -> 05 -> 02 -> 03 -> 07` in sequence so your `.c`/`.h` files, `font_icon_epd_patches.json`, and `inspect_pages/*.png` banners immediately include all tournament-repaired glyphs.
2. **Manual Iterative Tuning & Hand-Patching Loop (`04 -> 08 -> 05 -> 02 -> 03`)**:
   - Run `04_dump_ascii_patches.bat` to populate baseline `.txt` glyph grids in `build\<target>\ascii_patches\`.
   - Run `08_iterative_auto_repair.bat` to run the 8-method OpenCV/HQ-Master tournament (`tools\fonts\humid1_bilevel_tuner.py`). This rewrites improved `.txt` files in `build\<target>\ascii_patches\` with `patched: 1`, generates Before/After visual comparison sheets in `build\<target>\inspect_repairs\*_repair.png`, and updates `font_icon_epd_patches.json`.
   - *(Optional)* Open any `build\<target>\ascii_patches\<symbol>\U+XXXX_<name>.txt` in a text editor, tweak `#` / `.` pixels on the 1:1 spaced canvas, and run `05_apply_ascii_patches.bat` to compile your manual edits into `font_icon_epd_patches.json`.
   - Run `02_build_fonts.bat` followed by `03_visual_check_pngs.bat` to rebuild the `.c`/`.h` font modules and inspect the updated PNG sheets (which display `PATCHED OVERRIDES ACTIVE: N / Total GLYPHS` in the top banner and highlight every patched glyph cell in emerald green).

