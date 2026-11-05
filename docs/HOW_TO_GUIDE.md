# Complete How-To Guide — `epd-font` (v1.0.13)

**Repository**: `https://github.com/Humidyne-Labs/epd-font`  
**Organization**: Humidyne Labs / Humiditron  
**License**: MIT License (Upstream fonts retain SIL OFL 1.1 / CC-BY-4.0 / ISC / MIT)

---

## 1. Host Prerequisites & Dependency Installation

`epd-font` has two distinct execution environments:
1. **Maintainer / Developer Host (`build_static_ttf_assets.py` & `humid1_generate_1bpp.py`)**: Requires Python 3.9+, `fonttools`, `Pillow`, and `freetype-py` (or system `libfreetype`).
2. **Downstream Firmware / CMake Build (`humid1_fw_emit.py`)**: Requires **ONLY** the standard Python 3 library (`0` pip packages, `0` native C libraries, `< 0.15s` execution time).

### Install Maintainer Python Dependencies:
```bash
python -m pip install --upgrade pip
python -m pip install "fonttools>=4.40.0" "Pillow>=10.0.0" "freetype-py>=2.4.0"
```
*(Or on Windows, double-click `00_setup_env.bat` inside any `scripts\*\` folder.)*

---

## 2. Understanding the `build/`, `dist/`, and Root Patch Architecture

To keep the Git repository lightweight while preserving every pixel-level customization:
- **`assets/` (Tracked in Git)**: Contains raw upstream variable `.ttf` fonts, `.otf` icon fonts, and `terminus-font-4.49.1.tar.gz`.
- **`font_icon_epd_patches.json` (Tracked in Git Root)**: The authoritative optical pixel patch manifest. Whenever you edit a Full-Canvas 1:1 ASCII `.txt` glyph inside `build/<workflow>/ascii_patches/` and run `--workflow patch --apply` (or `05_apply_ascii_patches.bat`), your edits are compiled into `font_icon_epd_patches.json` at the repository root.
- **`build/` (Gitignored)**: Holds all generated intermediate files:
  - `build/static_ttfs/` — All 56 static `.ttf` binaries (`41` IBM Plex + `2` Terminus + `13` Icon TTFs) and `licenses/`.
  - `build/metadata/` — Searchable JSON catalogs (`fa7_catalog.json`, `lucide_catalog.json`, `phosphor_catalog.json`, `tabler_catalog.json`, `terminus_catalog.json`, `plex_catalog.json`, `unified_icon_names.json`, `asset_manifest.json`).
  - `build/<workflow>/ascii_patches/` — Dumped Full-Canvas 1:1 Spaced ASCII `.txt` glyph files.
  - `build/<workflow>/fonts/` — Generated LVGL v9 `.c` files, `epd_fonts.h`, `plex_fonts.h`, and optional `h1os_fonts.h`.
  - `build/<workflow>/inspect_pages/` & `build/<workflow>/inspect_chars/` — Visual inspection PNGs.
- **`dist/` (Gitignored)**: Holds self-contained distribution bundles (`dist/example_distro/`, `dist/audit_distro/`, `dist/h1os_distro/`) ready to drop into any firmware project.

---

## 3. Running the 4 Self-Contained Windows Batch Workflows (`scripts/*`)

Each subdirectory under `scripts/` contains its own `.scheme.json` and numbered `.bat` pipeline (`00` through `99`):

| Workflow Subdirectory | Scheme File(s) | Build Output | Dist Output | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| `scripts/example-build-distro/` | `example.scheme.json` | `build/example/` | `dist/example_distro/` | General-purpose embedded project template (Sans, Mono, Terminus, Lucide, Phosphor) |
| `scripts/full-audit-build-dev/` | `full_audit.scheme.json` | `build/audit_dev/` | `dist/audit_dev_distro/` | Exhaustive 12–40pt developer audit (all fonts & icons + every char PNG & ASCII dump) |
| `scripts/full-audit-build-distro/` | `full_audit_distro.scheme.json` | `build/audit/` | `dist/audit_distro/` | Exhaustive 12–40pt master distribution bundle & Strike Vault |
| `scripts/h1os-build-distro/` | `h1os_full.scheme.json`, `h1os_lite.scheme.json` | `build/h1os/` | `dist/h1os_distro/` | Dedicated H1OS & `humid1-os` firmware deployment bundle |

---

## 4. Customizing Display Geometry & Schemes (`tools/fonts/schemes/*.json`)

You can configure any display resolution, DPI, and safe margin either in your `.scheme.json` under `"target_display"` or on the command line:

```bash
python tools/fonts/humid1_generate_1bpp.py --workflow check \
  --scheme tools/fonts/schemes/weather_station_epd.scheme.json \
  --dpi 112.0 --screen-width 296 --screen-height 128 --safe-margin 6 \
  --out-dir build/weather --dist-dir dist/weather_distro --audit-screens
```

---

## 5. Using the Agent-First Tooling Suite (`tools/agent/`)

Never guess character widths, string pixel lengths, or icon codepoints:

```bash
# 1. Inspect exact pixel metrics and 1:1 ASCII art for any character or icon:
python tools/agent/tools/char_info.py --strike humid1_icon_phosphor_fill_20 --char alarm

# 2. Compute exact kerning-aware string width and screen clearance:
python tools/agent/tools/string_info.py --strike humid1_font_plex_sans_normal_14 --text "Vapor Pressure" \
  --right-text "42.8 hPa" --right-strike humid1_font_plex_mono_bold_14 --screen-width 200 --safe-margin 6

# 3. Search 12,200+ icons across FA7, Lucide, Phosphor, and Tabler:
python tools/agent/tools/icon_search.py --query battery --vendor icon_phosphor

# 4. List all 56 static TTFs, catalogs, and 16 built-in schemes:
python tools/agent/tools/font_catalog_info.py
```


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

