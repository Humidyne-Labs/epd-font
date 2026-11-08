# Complete How-To Guide — `epd-font` (v1.0.21)

- **Project**: A 1-bit EPD font generator and asset pipeline for embedded displays
- **Repository**: [Humidyne-Labs/epd-font](https://github.com/Humidyne-Labs/epd-font) (`v1.0.21`)
- **Authors**: [Humiditron](https://github.com/humiditron) (Humidyne Labs) & AI/LLM Collaborative Development Partner
- **Supported Platforms**: Windows (Primary) and Linux (Optional). *(Note: unsupported Apple OS is not supported.)*
- **License**: MIT License (Pipeline & Tooling) / SIL OFL 1.1 / CC-BY-4.0 / ISC / MIT (Upstream Fonts)

## 1. Host Prerequisites & Dependency Installation

`epd-font` v1.0.21 supports two operational modes:
1. **Full Pipeline & Asset Builder (`build_static_ttf_assets.py`, `humid1_generate_1bpp.py`, `humid1_font_eval.py`)**: Requires Python 3.9+, `fonttools`, `Pillow`, `numpy`, `opencv-python`, and `freetype-py` (`freetype.dll` on Windows or `libfreetype.so.6` on Linux).
2. **Downstream Firmware / CMake Vault Emitter (`humid1_fw_emit.py`)**: Requires **ONLY** the standard Python 3 library (`0` third-party packages, `< 0.15s` execution time).

```bash
python -m pip install --upgrade pip
python -m pip install "fonttools>=4.40.0" "Pillow>=10.0.0" "freetype-py>=2.4.0" "numpy>=1.24.0" "opencv-python>=4.8.0"
```

## 2. Selecting Between the 8 Resolution-Reduction Pipelines, Linear Grayscale & Gamma

Pass `--pipeline <method>` (or set `"pipeline"` inside `"raster_config"` in your `.scheme.json` file), optional `--threshold <1..254>` (default `128`), and optional `--gamma <0.1..5.0>` (default `1.0`):

| Pipeline Key | Mathematical Resolution-Reduction Method | Hinting State | Best Suited For |
| :--- | :--- | :--- | :--- |
| `raw-unhinted` | Direct FreeType `8-bit` linear luminance render + gamma + binary threshold (`default 128`) | Unhinted (`FT_LOAD_NO_HINTING`) | Display sizes (`>= 20 px`) and fonts with irregular bytecode hints |
| `raw-hinted` | Grid-fitted FreeType `8-bit` linear luminance render + gamma + binary threshold (`default 128`) | Hinted (`fpgm`/`prep` or symmetric autohint) | Well-hinted UI/Telemetry fonts (`IBM Plex`, `Google Noto`) at `12 px–18 px` |
| `svg-potrace` | `10x` high-res render -> binary threshold -> hierarchical `RETR_TREE` Potrace `.svg` trace -> `+0.5 px` offset -> aliased `LINE_8` fill | Vector center-line traced | Smooth organic curves, serifs, and multi-island filled icons (`Tabler-Filled`, `Phosphor-Fill`) |
| `mdf` | `12x` super-sampled median filter + directional morphological Signed Distance Field -> center-sampled threshold | Continuous distance field | Global stroke-weight tuning via `--threshold` (`116..140`) |
| `msdf` | `12x` Multi-Channel Signed Distance Field ([Chlumsky/msdfgen](https://github.com/Chlumsky/msdfgen)) with 3-channel $(R,G,B)$ corner edge coloring and $\text{median}(R,G,B)$ reconstruction | Multi-channel corner-preserving SDF | Preserving sharp apexes, diagonals (`W`, `M`, `N`, `A`), and technical icons at low ppem |
| `sdf-smoothstep` | `16x` Euclidean Signed Distance Field + Hermite `smoothstep` edge reconstruction ([Red Blob Games SDF Typography](https://www.redblobgames.com/articles/sdf-fonts/)) | Analytical SDF reconstruction | Uniform optical stroke density across mixed sizes |
| `adf-biquadratic` | `16x` Adaptive Distance Field (`ADF`) quadtree ($4\times 4$ cells) with biquadratic surface interpolation $P(u,v)$ | Quadtree biquadratic ADF | High-curvature glyphs and complex mathematical/scientific symbols |
| `otsu-adaptive` | Linear-luminance Otsu global threshold blended with Sauvola local mean/variance adaptive thresholding | Local adaptive threshold | Protecting tight interior counters (`a`, `e`, `8`, `B`, `@`) at small pixel sizes |

### Multi-Method Sheet Dumping (`"pipeline": "all"` or `"all-debug"`) & Debug Gating (`char_debug`, `sheet_debug`)
- When `"char_debug": false` in `.scheme.json` (or `--no-char-debug`), individual character PNG generation (`inspect_chars/`) is completely disabled.
- When `"sheet_debug": false` in `.scheme.json` (or `--no-sheet-debug`), character map sheet PNG generation (`inspect_pages/`) is completely disabled.
- When `"pipeline": "all"` (or `"all-debug"`) is selected and `sheet_debug` is enabled, `humid1_generate_1bpp.py` runs all 8 conversion pipelines and dumps:
  - Per-method full character sheets in `build/<workflow>/inspect_pages/<method>/<symbol>.png`
  - Side-by-side 8-method visual comparison sheets in `build/<workflow>/inspect_pages/compare_methods/<symbol>_all_methods.png`

## 3. Hardware Partition Schemes (`esp32s3-N8R8-hw_scheme.json` & `generic_hw.json`)

Every `.scheme.json` references a hardware scheme (`"hardware_scheme": "esp32s3-N8R8-hw_scheme.json"` or `"generic_hw.json"`) and specifies the single `3 MByte` (`3,145,728` bytes) partition constraint:
```json
"hardware_scheme": "esp32s3-N8R8-hw_scheme.json",
"target_display": {
  "chip_name": "ESP32-S3-N8R8",
  "partition_1": "3 MBytes",
  "target_partition_bytes": 3145728
}
```
All hardcoded partition fallback defaults have been removed in `v1.0.21`: if `"partition_1"` / `"target_partition_bytes"` is removed or does not equal `3 MBytes` (`3,145,728` bytes), the generator immediately exits with a descriptive configuration error.

## 4. Closed-Loop Manual ASCII Patching Workflow

In `v1.0.21`, all pixel-level modifications are controlled directly by the developer:
1. **Step 1 — Generate Static Assets**: Run `01_build_static_ttfs.bat` and `02_build_fonts.bat` to generate static `.ttf` binaries and baseline `.c`/`.h` font strikes using `font_icon_epd_patches.json`.
2. **Step 2 — Dump Visual Inspection PNGs**: Run `03_visual_check_pngs.bat` (`--sheet-debug`) to render per-strike character map sheets (`build/<workflow>/inspect_pages/*.png`) and `master_char_icon_map.png`.
3. **Step 3 — Dump Editable ASCII Files**: Run `04_dump_ascii_patches.bat` (`--workflow patch --dump`) to export Full-Canvas `1:1` Spaced ASCII `.txt` files into `build/<workflow>/ascii_patches/<strike>/`.
4. **Step 4 — Edit ASCII Files**: Open any `U+XXXX_<name>.txt` file in a text editor and toggle `# ` (active ink) and `. ` (background canvas) or `- ` (baseline $y=0$).
5. **Step 5 — Ingest ASCII & Write Patch JSON**: Run `05_apply_ascii_patches.bat` (`--workflow patch --apply`) to compile modified `.txt` files into `font_icon_epd_patches.json`.
6. **Step 6 — Closed-Loop Rebuild**: Run `02_build_fonts.bat` and `03_visual_check_pngs.bat` to regenerate all `.c`/`.h` sources, `.bdf` files, Strike Vault, and verification PNGs with your manual patches applied.

## 5. ESP-IDF & External CMake Build Integration

Use `tools/fonts/humid1_cmake_font_builder.py` or `tools/fonts/cmake/epd_font_esp_idf.cmake` inside any ESP-IDF project:

```cmake
include(${CMAKE_CURRENT_LIST_DIR}/tools/fonts/cmake/epd_font_esp_idf.cmake)

epd_font_generate_lvgl_target(
    TARGET_NAME humid1_epd_fonts
    SCHEME      "${CMAKE_CURRENT_LIST_DIR}/scripts/h1os-build-distro/h1os_full.scheme.json"
    VAULT       "${CMAKE_CURRENT_LIST_DIR}/dist/h1os_distro/humid1_epd_vault.json.gz"
    OUT_DIR     "${CMAKE_CURRENT_BINARY_DIR}/generated_fonts"
)
```
