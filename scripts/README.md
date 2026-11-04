## Build Sub-folder Sizes, 99 Script Runner

```TEXT
full-audit-build-distro = 3.61GB
h1os-build-distro       = 542MB
example-build-distro    = 167MB
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

