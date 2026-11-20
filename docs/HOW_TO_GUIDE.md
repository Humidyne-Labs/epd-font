# Complete How-To Guide — `epd-font` (v1.0.23)

- **Project**: A 1-bit EPD font generator and asset pipeline for embedded displays
- **Repository**: [Humidyne-Labs/epd-font](https://github.com/Humidyne-Labs/epd-font) (`v1.0.23`)
- **Authors**: [Humiditron](https://github.com/humiditron) (Humidyne Labs) & AI/LLM Collaborative Development Partner
- **Supported Platforms**: Windows (Primary) and Linux (Optional). *(Note: unsupported Apple OS is not supported.)*
- **License**: MIT License (Pipeline & Tooling) / SIL OFL 1.1 / CC-BY-4.0 / ISC / MIT (Upstream Fonts)

## 1. Host Prerequisites & Dependency Installation

`epd-font` v1.0.23 supports two operational modes:
1. **Full Pipeline & Asset Builder (`build_static_ttf_assets.py`, `humid1_generate_1bpp.py`, `humid1_font_eval.py`)**: Requires Python 3.9+, `fonttools`, `Pillow`, `numpy`, `opencv-python`, and `freetype-py` (`freetype.dll` on Windows or `libfreetype.so.6` on Linux).
2. **Downstream Firmware / CMake Vault Emitter (`humid1_fw_emit.py`)**: Requires **ONLY** the standard Python 3 library (`0` third-party packages, `< 0.15s` execution time).

```bash
python -m pip install --upgrade pip
python -m pip install "fonttools>=4.40.0" "Pillow>=10.0.0" "freetype-py>=2.4.0" "numpy>=1.24.0" "opencv-python>=4.8.0"
```

## 2. Selecting Between the 9 Resolution-Reduction Pipelines, Linear Grayscale & Gamma

Configure `"pipeline"`, `"math_backend"`, `"threshold"` (`1..254`, default `128`), `"gamma"` (`0.20..3.00`, default `1.0`), and `"sheet_debug"` / `"char_debug"` / `"debug_stages"` inside `"raster_config"` in your `.scheme.json` file (for `humid1_font_eval.py`, pass `--threshold`, `--gamma`, `--accel`):

| Pipeline Key | Mathematical Resolution-Reduction Method | Hinting State | Best Suited For |
| :--- | :--- | :--- | :--- |
| `raw-unhinted` | Direct FreeType `8-bit` linear luminance render + gamma + binary threshold (`default 128`) | Unhinted (`FT_LOAD_NO_HINTING`) | Display sizes (`>= 20 px`) and fonts with irregular bytecode hints |
| `raw-hinted` | Grid-fitted FreeType `8-bit` linear luminance render + gamma + binary threshold (`default 128`) | Hinted (`fpgm`/`prep` or symmetric autohint) | Well-hinted UI/Telemetry fonts (`IBM Plex`, `Google Noto`) at `12 px–18 px` |
| `svg-potrace` | `10x` high-res render -> binary threshold -> hierarchical `RETR_TREE` Potrace `.svg` trace -> `+0.5 px` offset -> aliased `LINE_8` fill | Vector center-line traced | Smooth organic curves, serifs, and multi-island filled icons (`Tabler-Filled`, `Phosphor-Fill`) |
| `svg-potrace-jfa` | Sub-mode of `svg-potrace`: 3D NDRange Jump Flooding (`1+JFA`) + 2x2 Marching Squares zero-crossing + `RETR_TREE` Potrace topology | JFA + Marching Squares + Vector | Tight apertures and sharp corners needing sub-pixel distance accuracy |
| `mdf` | `12x` super-sampled median filter + directional morphological Signed Distance Field -> center-sampled threshold | Continuous distance field | Global stroke-weight tuning via `raster_config.threshold` (`116..140`) |
| `msdf` | `12x` Multi-Channel Signed Distance Field ([Chlumsky/msdfgen](https://github.com/Chlumsky/msdfgen)) with 3-channel $(R,G,B)$ corner edge coloring and $\text{median}(R,G,B)$ reconstruction | Multi-channel corner-preserving SDF | Preserving sharp apexes, diagonals (`W`, `M`, `N`, `A`), and technical icons at low ppem |
| `sdf-smoothstep` | `16x` Euclidean Signed Distance Field + Hermite `smoothstep` edge reconstruction ([Red Blob Games SDF Typography](https://www.redblobgames.com/articles/sdf-fonts/)) | Analytical SDF reconstruction | Uniform optical stroke density across mixed sizes |
| `adf-biquadratic` | `12x` Adaptive Distance Field (`ADF`) quadtree ($4\times 4$ cells) with biquadratic surface interpolation $P(u,v)$ | Quadtree biquadratic ADF | High-curvature glyphs and complex mathematical/scientific symbols |
| `otsu-adaptive` | Linear-luminance Otsu global threshold ($\sigma_B^2(k^*)$) computed on 3D NDRange per-slice histograms | Local adaptive threshold | Protecting tight interior counters (`a`, `e`, `8`, `B`, `@`) at small pixel sizes |

### Multi-Method Sheet Dumping (`"pipeline": "all"` or `"all-debug"`) & Debug Gating (`char_debug`, `sheet_debug`)
- When `"char_debug": false` in `.scheme.json`, individual character PNG generation (`inspect_chars/`) is completely disabled.
- When `"sheet_debug": false` in `.scheme.json`, character map sheet PNG generation (`inspect_pages/`) is completely disabled.
- When `"pipeline": "all"` (or `"all-debug"` / `--workflow audit`) is selected and `sheet_debug` is enabled, `humid1_generate_1bpp.py` runs all 9 conversion pipelines and dumps:
  - Per-method full character sheets + `master_char_icon_map.png` in `build/<workflow>/inspect_pages/<method>/`
  - Side-by-side `16px` & `38px` 9-method visual comparison sheets in `build/<workflow>/inspect_pages/compare_methods/<font_stem>_16px_38px.png`

## 3. Hardware Partition Schemes (`esp32s3-N8R8-hw_scheme.json` & `generic_hw.json`)

Every `.scheme.json` references a root hardware scheme (`"hardware_scheme": "esp32s3-N8R8-hw_scheme.json"` or `"generic_hw.json"`) defining the target SoC, single `3 MByte` (`3,145,728` bytes) partition constraint, and display geometry:
```json
{
  "schema_version": "1.0.23",
  "hw_scheme_id": "esp32s3-N8R8",
  "description": "Espressif ESP32-S3-N8R8 target with Waveshare 1.54in V2 Monochrome EPD",
  "chip_name": "ESP32-S3-N8R8",
  "soc_vendor": "Espressif Systems",
  "partition_bytes": 3145728,
  "display": {
    "panel": "Waveshare 1.54in V2 Monochrome EPD (SSD1681)",
    "width_px": 200,
    "height_px": 200,
    "dpi": 188.15,
    "safe_margin_px": 6,
    "color_depth_bpp": 1,
    "lvgl_color_format": "LV_COLOR_FORMAT_I1"
  }
}
```
All hardcoded fallback defaults have been removed: if `"partition_bytes"` is removed or does not equal `3145728` (`3 MBytes`), or if any required `raster_config` or `display` key is missing, the generator immediately exits with a descriptive configuration error.

## 4. Closed-Loop Manual ASCII Patching Workflow

In `v1.0.23`, all pixel-level modifications are controlled directly by the developer:
1. **Step 1 — Generate Static Assets**: Run `01_build_static_ttfs.bat` and `02_build_fonts.bat` to generate static `.ttf` binaries and baseline `.c`/`.h` font strikes using `font_icon_epd_patches.json`.
2. **Step 2 — Dump Visual Inspection PNGs**: Run `03_visual_check_pngs.bat` (`--workflow check`) to render per-strike character map sheets (`build/<workflow>/inspect_pages/default/*.png`) and `master_char_icon_map.png`.
3. **Step 3 — Dump Editable ASCII Files**: Run `04_dump_ascii_patches.bat` (`--workflow patch --dump`) to export Full-Canvas `1:1` Spaced ASCII `.txt` files into `build/<workflow>/ascii_patches/<strike>/`.
4. **Step 4 — Edit ASCII Files**: Open any `U+XXXX_<name>.txt` file in a text editor and toggle `# ` (active ink) and `. ` (background canvas) or `- ` (baseline $y=0$).
5. **Step 5 — Ingest ASCII & Write Patch JSON**: Run `05_apply_ascii_patches.bat` (`--workflow patch --apply`) to compile modified `.txt` files into `font_icon_epd_patches.json`.
6. **Step 6 — Closed-Loop Rebuild**: Run `02_build_fonts.bat` and `03_visual_check_pngs.bat` to regenerate all `.c`/`.h` sources, `.bdf` files, Strike Vault, and verification PNGs with your manual patches applied.

## 5. ESP-IDF CMake Integration & Distro CSV Metric Manifests

Each packaged bundle (`dist/<workflow>_distro/` and `dist/epd-font_<workflow>_v1.0.23.zip`) ships:
- `fonts/*.c`, `humid1_fonts.h`, and any configured `compat_header` (`h1os_fonts.h` / `epd_fonts.h`)
- `metrics/char_widths_<symbol>.csv` and `metrics/kern_pairs_<symbol>.csv` (per-strike glyph box, offset, FP4 advance, and kerning pairs)
- `bdf/*.bdf`, `humid1_epd_vault.json.gz`, `unified_icon_names.json`, and `CMakeLists.txt`

Query typography budgets directly via the global `embedded-ops` MCP tools (`epd_char_info`, `epd_string_budget`, `epd_audit_screens`, `epd_icon_search`, `epd_font_inventory`) backed by `tools/agent/tools/epd_typography.py`, or run SQL queries over `metrics/char_widths_*.csv` via `duckdb`.

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


## Master Configuration Variable Matrix & `math_backend` Reference (`v1.0.23`)

`epd-font v1.0.23` enforces a strict **Singular Configuration ("1 Spot, 1 Variable, Zero Assumed Defaults")** architecture. Every variable is defined in **one authoritative location** — either the **Hardware Configuration JSON** (`esp32s3-N8R8-hw_scheme.json` / `generic_hw.json`) or the **Profile Scheme JSON** (`*.scheme.json`). No variable is duplicated across files or CLI flags, and missing, unknown, or out-of-range variables halt execution immediately with a diagnostic error message.

### 1. Hardware Configuration Matrix (`esp32s3-N8R8-hw_scheme.json` / `generic_hw.json`)

| Variable Path | Type | Allowed Values / Domain | Purpose & Single-Source Usage |
| :--- | :--- | :--- | :--- |
| `schema_version` | `string` | `"1.0.23"` | Schema version identifier validated by `load_and_validate_hardware_scheme()`. |
| `hw_scheme_id` | `string` | e.g., `"esp32s3-N8R8"`, `"generic_hw"` | Unique hardware target identifier recorded in Strike Vaults and ROM reports. |
| `description` | `string` | Non-empty string | Human-readable summary of the target MCU and display platform. |
| `chip_name` | `string` | e.g., `"ESP32-S3-N8R8"`, `"Generic-32bit-MCU"` | Target microcontroller identifier displayed in Flash `.rodata` reports. |
| `soc_vendor` | `string` | e.g., `"Espressif Systems"` | Microcontroller vendor name for formal audit and ROM reports. |
| `partition_bytes` | `int` | `3145728` (`3 MBytes` exact) | Single supported Flash `.rodata` partition capacity in bytes (`3,145,728` bytes). |
| `display.panel` | `string` | e.g., `"Waveshare 1.54in V2 Monochrome EPD (SSD1681)"` | Physical display panel model name used in screen-width audit headers. |
| `display.width_px` | `int` | Positive integer (`200`) | Horizontal display resolution in pixels. |
| `display.height_px` | `int` | Positive integer (`200`) | Vertical display resolution in pixels. |
| `display.dpi` | `float` | Positive float (`188.15`) | Exact physical pixel density (`25.4 mm / 0.135 mm = 188.15 DPI`); single resolution variable (no `ppi`). |
| `display.safe_margin_px` | `int` | Non-negative integer (`6`) | Safe bezel margin per side in pixels (`usable_width_px` is derived as `width_px - 2 * safe_margin_px = 188`). |
| `display.color_depth_bpp` | `int` | `1` | Bilevel monochrome bit depth (`1` bit per pixel). |
| `display.lvgl_color_format` | `string` | `"LV_COLOR_FORMAT_I1"` | LVGL `>= 9.6.0` 1-bit indexed color format constant. |

### 2. Profile Scheme Configuration Matrix (`*.scheme.json`)

| Variable Path | Type | Allowed Values / Domain | Purpose & Single-Source Usage |
| :--- | :--- | :--- | :--- |
| `schema_version` | `string` | `"1.0.23"` | Schema version identifier validated by `validate_scheme_config()`. |
| `scheme_id` | `string` | e.g., `"h1os_epd_v1_full"`, `"h1os_epd_v1_debug_single_font"` | Unique profile identifier used in headers, vaults, and audit reports. |
| `project_brand` | `string` | Non-empty string | Project title rendered on visual inspection sheets and header banners. |
| `description` | `string` | Non-empty string | Summary of the font/icon strikes included in the profile. |
| `spdx_license` | `string` | e.g., `"MIT AND OFL-1.1"` | SPDX license expression written into generated C/H headers. |
| `hardware_scheme` | `string` | `"esp32s3-N8R8-hw_scheme.json"` or `"generic_hw.json"` | Reference to the root Hardware Configuration JSON (composes the `[hardware.json + profile.json]` pair). |
| `raster_config.pipeline` | `string` | `"raw-unhinted"`, `"raw-hinted"`, `"svg-potrace"`, `"svg-potrace-jfa"`, `"mdf"`, `"msdf"`, `"sdf-smoothstep"`, `"adf-biquadratic"`, `"otsu-adaptive"`, `"all"`, `"all-debug"` | Selects the resolution-reduction bilevel conversion method (or `"all"` / `"all-debug"` to evaluate all 9 pipelines). |
| `raster_config.math_backend` | `string` | `"auto"`, `"cpu"`, `"gpu"`, `"hybrid"`, `"sync"` | Selects the hardware compute delegation and multiprocessing execution mode (see Section 3 below). |
| `raster_config.threshold` | `int` | `1..254` (`128` nominal) | Binarization luminance threshold in linear `[0..255]` grayscale space. |
| `raster_config.gamma` | `float` | `0.20..3.00` (`1.0` nominal) | Linear luminance contrast power factor applied prior to thresholding. |
| `raster_config.normal_weight` | `int` | `100..900` (`500` Medium / `400` Regular) | OpenType weight mapped to the `"normal"` style slot. |
| `raster_config.bold_weight` | `int` | `100..900` (`800` ExtraBold / `700` Bold) | OpenType weight mapped to the `"bold"` style slot. |
| `raster_config.italic_weight` | `int` | `100..900` (`600` SemiBoldItalic / `400` Italic) | OpenType weight mapped to the `"italic"` style slot. |
| `raster_config.patches_file` | `string` | `"font_icon_epd_patches.json"` | Path to the manual pixel patch manifest JSON. |
| `raster_config.ascii_patches_dir` | `string` | e.g., `"build/h1os/ascii_patches"` | Directory for dumping and ingesting editable 1:1 ASCII `.txt` glyph files. |
| `raster_config.sheet_debug` | `bool` | `true` or `false` | Enables/disables generation of `inspect_pages/` PNG sheets and `master_char_icon_map.png`. |
| `raster_config.char_debug` | `bool` | `true` or `false` | Enables/disables generation of `inspect_chars/` per-glyph blueprint PNG cards. |
| `raster_config.debug_stages` | `bool` | `true` or `false` | Enables/disables `debug_stages/` 9-pipeline stage breakdown PNGs and Potrace `.svg` vectors. |
| `output_branding` | `object` | `{symbol_prefix, primary_header, compat_header, default_font, semantic_roles}` | C symbol naming prefix (`humid1_`), output header filenames, and semantic role macros. |
| `character_sets` | `object` | Map of named character/icon sets | Defines Unicode ranges (`ranges`) or semantic icon lists (`vendor`, `scope`, `icons`). |
| `strikes` | `array` | List of `{family, style, sizes, char_sets, kerning, fallback}` | Declares every font/icon strike, point-size array, kerning toggle, and LVGL fallback pointer. |

### 3. `math_backend` Operating Modes & Hardware Pre-Check Behavior

Before any strike task is dispatched, `humid1_generate_1bpp.py` and `humid1_runtime.py` inspect the host hardware and validate `raster_config.math_backend` with **zero silent fallbacks**:

| `math_backend` Value | Hardware Requirement & Pre-Check | Execution & Resource Delegation Behavior |
| :--- | :--- | :--- |
| **`"auto"`** | Probes OpenCL GPU/CPU runtimes and host CPU cores. Never fails if a GPU is absent. | **Automatic Asynchronous Delegation**: If a verified OpenCL GPU (e.g., `Ellesmere`, 32 CUs) is detected, spawns `1` persistent GPU worker (for heavy icon catalogs, distance-field pipelines, and `28..40px` strikes) + `N-1` async CPU workers (for `Terminus` bitmap strikes and small text strikes). If no GPU is present, runs all tasks across `N` async CPU workers. |
| **`"cpu"`** | Requires host CPU (`>= 1` core). | **100% Asynchronous Multi-Core CPU**: Spawns `N` `ProcessPoolExecutor` CPU workers (`EPD_FONT_WORKER_ROLE="cpu"`, OpenCL GPU and OpenCV UMat disabled). Zero GPU contexts or VRAM/Shared GPU RAM buffers are allocated. |
| **`"gpu"`** | **Strict GPU Pre-Check**: Requires a verified OpenCL GPU (or OpenCV UMat GPU). **Halts immediately with an error if no GPU is available.** | **Dedicated GPU Acceleration + CPU Orchestration**: Routes all applicable mathematical operations (sRGB-to-linear luminance + gamma, SDF smoothstep, MSDF median-of-3, ADF biquadratic 9-pt Lagrange, Otsu local-atomic histogram, `1+JFA` + Marching Squares, morphological close, median blur, and compute-density task sorting) through the GPU accelerator (`3D NDRange`, `4` queues, `75%` Shared GPU RAM Arena), while the CPU orchestrates FreeType outline loading and file I/O. |
| **`"hybrid"`** | **Strict Hybrid Pre-Check**: Requires BOTH a verified OpenCL GPU and multi-core host CPU. **Halts immediately with an error if no GPU is available.** | **Explicit Dual-Pool Work-Stealing Deque**: Spawns `1` persistent GPU worker pulling the highest-density tasks from the front of the work-stealing deque and `N-1` async CPU workers pulling lightweight tasks from the back of the deque. |
| **`"sync"`** | Requires host CPU (`1` process). | **Synchronous Single-Process Mode (`misc`)**: Executes all strike tasks sequentially in the main process without spawning `ProcessPoolExecutor` child workers (useful for deterministic profiling and debugging). |

### 4. Structured `inspect_pages/` Output Hierarchy (`all` / `all-debug` & Single-Font `h1os_debug.scheme.json`)

When `sheet_debug = true` (or `pipeline = "all-debug"` / `--workflow audit`), all generated inspection PNGs are organized into logical subdirectories under `build/<target>/inspect_pages/` (**zero loose `.png` files in `inspect_pages/`**):
- `build/<target>/inspect_pages/adf-biquadratic/` — All strike sheets + `master_char_icon_map.png`
- `build/<target>/inspect_pages/mdf/` — All strike sheets + `master_char_icon_map.png`
- `build/<target>/inspect_pages/msdf/` — All strike sheets + `master_char_icon_map.png`
- `build/<target>/inspect_pages/otsu-adaptive/` — All strike sheets + `master_char_icon_map.png`
- `build/<target>/inspect_pages/raw-hinted/` — All strike sheets + `master_char_icon_map.png`
- `build/<target>/inspect_pages/raw-unhinted/` — All strike sheets + `master_char_icon_map.png`
- `build/<target>/inspect_pages/sdf-smoothstep/` — All strike sheets + `master_char_icon_map.png`
- `build/<target>/inspect_pages/svg-potrace/` — All strike sheets + `master_char_icon_map.png`
- `build/<target>/inspect_pages/svg-potrace-jfa/` — All strike sheets + `master_char_icon_map.png`
- `build/<target>/inspect_pages/default/` — Default selection strike sheets + `master_char_icon_map.png` + `humid1_epd_specimen_188dpi.png`
- `build/<target>/inspect_pages/compare_methods/` — Side-by-side `<font_stem>_16px_38px.png` comparison sheets featuring **`16px` (Low-Detail) & `38px` (High-Detail)** across all 9 conversion pipelines.

To verify the entire debug pipeline against **1 font (`IBM Plex Sans Normal` @ `16px` & `38px`)** in seconds rather than running all 108/368 strikes, run:
```bat
scripts\h1os-build-distro\08_run_single_font_debug.bat
```
or via Python CLI:
```bash
python tools/fonts/humid1_generate_1bpp.py --workflow audit --scheme scripts/h1os-build-distro/h1os_debug.scheme.json --src-dir build/static_ttfs --out-dir build/h1os_debug --dist-dir dist/h1os_debug_distro
```
