# Formal Pre-Audit Report — `epd-font` v1.0.20 Public-Release Cohesion, Config Single-Source & Codebase Audit (`PRE-AUDIT-v1.0.20`)

- **Document ID**: `HUMIDITRON-PRE-AUDIT-v1.0.20`
- **Date**: 2026-11-08
- **Project**: A 1-bit EPD font generator and asset pipeline for embedded displays
- **Repository**: [Humidyne-Labs/epd-font](https://github.com/Humidyne-Labs/epd-font) (`v1.0.20` -> `v1.0.21`)
- **Authors**: [Humiditron](https://github.com/humiditron) (Humidyne Labs) & AI/LLM Collaborative Development Partner
- **Format Policy**: Markdown (`.md`) only — zero `.docx` files in repository.

## 1. Executive Summary

Prior to tagging the public `v1.0.21` release of [Humidyne-Labs/epd-font](https://github.com/Humidyne-Labs/epd-font), a full-repository static, structural, configuration, and script cohesion audit was conducted across all 26 Python modules (`tools/fonts/`, `tools/agent/tools/`, `scripts/`), 20 declarative font schemes (`.scheme.json`), root hardware schemes, 29 Windows 1-click `.bat` launchers, CMake scripts, and documentation files.

The pre-audit identified four categories of findings (`PRE-21-01` through `PRE-21-04`) that must be resolved to achieve strict Single Source of Truth (SSOT) configuration, zero unused code/imports, consistent file naming/spelling, and 100% argument cohesion across all 1-click scripts.

| Finding ID | Category | Affected Files | Pre-Audit Root Cause & Cohesion Impact | Target Resolution in `v1.0.21` |
| :--- | :--- | :--- | :--- | :--- |
| **`PRE-21-01`** | **Hardware & Display Config Duplication (`target_display` vs. Root Hardware Config)** | All 20 `.scheme.json` files, `humid1_runtime.py`, `humid1_fw_emit.py`, `font_catalog_info.py`, `string_info.py` | Every `.scheme.json` embedded a 13-line `"target_display"` dictionary (`panel`, `width_px`, `height_px`, `dpi`, `safe_margin_px`, `usable_width_px`, `color_depth_bpp`, `lvgl_color_format`, `target_partition_bytes`, `target_soc`, `chip_name`, `partition_1`) that duplicated the root hardware configuration files (`esp32s3-N8R8-hw_scheme.json` and `generic_hw.json`). In `humid1_runtime.py` (`L267-301`), `target_display` fields took precedence over `hw_data` when `--hw-scheme` was not passed on the CLI, creating a dual-config maintenance hazard. | Remove `"target_display"` from all 20 `.scheme.json` files. Reference `"hardware_scheme": "esp32s3-N8R8-hw_scheme.json"` (or `"generic_hw.json"`) at the top of each `.scheme.json` and make `load_and_validate_hardware_scheme()` + `--hw-scheme` the single source of truth for all hardware, partition (`3 MBytes` = `3,145,728` bytes), and display (`200x200 @ 188.15 DPI`) parameters. |
| **`PRE-21-02`** | **Spelling Errors, Duplicate Files & Filename Casing Inconsistencies** | `genaric_hw.json`, `generic_hw.json`, `example.scheme.json`, `docs/LEGACY_METHODOLOGY_v1.0.17.md`, `docs/humid1-audit-v1.0.20.md`, `docs/audits/h1os_font_strategy_report_v1_0_16.md` | 1. Root contained a misspelled `genaric_hw.json` duplicate alongside `generic_hw.json`, and `generic_hw.json` contained `"hw_scheme_id": "genaric_hw"`.<br>2. `LEGACY_METHODOLOGY_v1.0.17.md` existed in both `docs/` and `docs/audits/`.<br>3. `docs/humid1-audit-v1.0.20.md` was placed in `docs/` rather than `docs/audits/notes/`.<br>4. `docs/audits/h1os_font_strategy_report_v1_0_16.md` used lowercase snake_case while all other reports in `docs/audits/` used uppercase (`H1OS_FONT_STRATEGY_REPORT_v1.0.16.md`). | Remove `genaric_hw.json`; set `"hw_scheme_id": "generic_hw"` and `"chip_name": "Generic-32bit-MCU"` in `generic_hw.json`; update all references to `generic_hw.json`; remove the duplicate `docs/LEGACY_METHODOLOGY_v1.0.17.md`; move `docs/humid1-audit-v1.0.20.md` into `docs/audits/notes/`; and rename `docs/audits/H1OS_FONT_STRATEGY_REPORT_v1.0.16.md`. |
| **`PRE-21-03`** | **1-Click `.bat` Script, CMake & Agent Skill CLI Argument Cohesion** | `scripts/h1os-build-distro/*.bat`, `scripts/example-build-distro/*.bat`, `scripts/full-audit-build-distro/*.bat`, `scripts/font-eval-suite/*.bat`, `humid1_cmake_font_builder.py`, `epd_font_esp_idf.cmake`, `tools/agent/skills/scheme-and-patch-workflow/SKILL.md` | 1. The 1-click `.bat` scripts did not explicitly pass `--hw-scheme` (`esp32s3-N8R8-hw_scheme.json` or `generic_hw.json`) or `--potrace-submode` support.<br>2. `scripts/full-audit-build-distro/03_visual_check_pngs.bat` invoked `--workflow check` instead of `--workflow audit` (which evaluates all 9 conversion pipelines and generates the multi-pipeline audit summary table).<br>3. `humid1_cmake_font_builder.py`, `humid1_fw_emit.py`, and `epd_font_esp_idf.cmake` lacked an explicit `--hw-scheme` (`HW_SCHEME`) option.<br>4. `tools/agent/skills/scheme-and-patch-workflow/SKILL.md` omitted required `--src-dir`, `--out-dir`, and `--hw-scheme` arguments. | Update all 1-click `.bat` scripts to pass explicit `--hw-scheme`, `--scheme`, `--src-dir`, `--out-dir`, `--dist-dir`, and `--patches` arguments matching each workflow's scope; add `--hw-scheme` (`HW_SCHEME`) to `humid1_fw_emit.py`, `humid1_cmake_font_builder.py`, `humid1_font_eval.py`, and `epd_font_esp_idf.cmake`; and update `SKILL.md` examples. |
| **`PRE-21-04`** | **Unused Code, Dead Imports & Unwired Hardware Math Dispatches** | 12 Python files in `tools/fonts/` and `tools/agent/tools/` | AST static analysis identified:<br>1. Unwired math backend dispatches (`dispatch_median_blur`, `dispatch_morphology_close`, `dispatch_msdf_median3_reconstruct`) imported in `humid1_bilevel_pipelines.py` while `compute_mdf_bilevel_bitmap()` and `compute_msdf_bilevel_bitmap()` called raw CPU `cv2`/`np` routines directly.<br>2. Duplicate helper definitions (`binary_array_to_rows`, `trim_binary_array`) and unused `resolve_freetype_flags` in `humid1_ft_raster.py`.<br>3. Unused imports across 12 modules (`List`, `gzip`, `sys`, `re`, `shutil`, `unicodedata`, `Tuple`, `json`, `os`, `gc`, `Callable`, `Dict`, etc.). | Route `compute_mdf_bilevel_bitmap()` and `compute_msdf_bilevel_bitmap()` through `dispatch_median_blur`, `dispatch_morphology_close`, and `dispatch_msdf_median3_reconstruct`; import `binary_array_to_rows` and `trim_binary_array` in `humid1_ft_raster.py`; remove `resolve_freetype_flags` and all unused imports so AST static analysis reports `0` unused imports and `0` dead functions. |

## 2. Detailed Pre-Audit Evidence

### 2.1 Configuration Duplication Analysis (`PRE-21-01`)

In `v1.0.20`, root `esp32s3-N8R8-hw_scheme.json` and `generic_hw.json` already defined the complete hardware and display specification:
```json
{
  "schema_version": "1.0.20",
  "hw_scheme_id": "esp32s3-N8R8",
  "chip_name": "ESP32-S3-N8R8",
  "partition_1": "3 MBytes",
  "partition_1_bytes": 3145728,
  "display": {
    "panel": "Waveshare 1.54in V2 Monochrome EPD (SSD1681)",
    "controller": "Solomon Systech SSD1681",
    "width_px": 200,
    "height_px": 200,
    "dpi": 188.15,
    "safe_margin_px": 6,
    "usable_width_px": 188,
    "color_depth_bpp": 1,
    "lvgl_color_format": "LV_COLOR_FORMAT_I1"
  }
}
```
Simultaneously, all 20 `.scheme.json` files duplicated those exact fields inside `"target_display": { ... }`. Consolidating all hardware and display attributes into `esp32s3-N8R8-hw_scheme.json` and `generic_hw.json` eliminates 260 lines of duplicated JSON across the 20 schemes and guarantees that changing a display or hardware parameter in the root hardware config immediately propagates to every scheme and tool.

### 2.2 Static AST Unused-Import & Dead-Code Inventory (`PRE-21-04`)

Running an AST symbol-reference scan across all 26 `.py` files in `v1.0.20` flagged:
- `tools/agent/tools/char_info.py`: unused `List` (`L20`)
- `tools/agent/tools/font_catalog_info.py`: unused `gzip` (`L13`), `sys` (`L15`), and legacy `sd.get("target_display", {})` (`L51`)
- `tools/fonts/build_static_ttf_assets.py`: duplicate bottom-of-file imports `detect_host_hardware`, `collect_all_licenses_recursive` (`L1033`)
- `tools/fonts/generate_char_manifests.py`: unused `re` (`L38`), `shutil` (`L39`), `sys` (`L40`), `unicodedata` (`L41`)
- `tools/fonts/humid1_ascii_patches.py`: unused `Tuple` (`L14`), `get_semantic_glyph_name` (`L16`)
- `tools/fonts/humid1_bilevel_pipelines.py`: imported `dispatch_bezier_sdf_yuksel`, `dispatch_median_blur`, `dispatch_morphology_close`, `dispatch_msdf_median3_reconstruct`, `describe_math_backend`, `select_math_backend` (`L41`) without invoking them in `compute_mdf_bilevel_bitmap` / `compute_msdf_bilevel_bitmap`
- `tools/fonts/humid1_cmake_font_builder.py`: unused `json` (`L25`)
- `tools/fonts/humid1_ft_raster.py`: unused `CANONICAL_PIPELINES`, `FT_LOAD_NO_AUTOHINT`, `FT_LOAD_TARGET_LIGHT`, `FT_PIXEL_MODE_GRAY`, `FT_PIXEL_MODE_MONO` (`L33`), dead function `resolve_freetype_flags` (`L578`), and inline re-implementations of `binary_array_to_rows` and `trim_binary_array`
- `tools/fonts/humid1_fw_emit.py`: unused `os` (`L25`)
- `tools/fonts/humid1_generate_1bpp.py`: unused `describe_math_backend` (`L48`)
- `tools/fonts/math_backends/umat_math.py`: unused `eval_*_cpu` imports (`L24`)
- `tools/fonts/opencl_dispatcher.py`: unused `gc` (`L32`), `Callable`, `Dict` (`L37`)
