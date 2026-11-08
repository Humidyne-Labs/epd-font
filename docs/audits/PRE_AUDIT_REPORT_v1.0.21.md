# Formal Pre-Audit Report — `epd-font` v1.0.21 Runtime Crash, Hardware Delegation, Singular Config Matrix & Output Structure Audit (`PRE-AUDIT-v1.0.21`)

- **Document ID**: `HUMIDITRON-PRE-AUDIT-v1.0.21`
- **Date**: 2026-11-08
- **Project**: A 1-bit EPD font generator and asset pipeline for embedded displays
- **Repository**: [Humidyne-Labs/epd-font](https://github.com/Humidyne-Labs/epd-font) (`v1.0.21` -> `v1.0.22`)
- **Authors**: [Humiditron](https://github.com/humiditron) (Humidyne Labs) & AI/LLM Collaborative Development Partner
- **Reference Exhibits**: `docs/audits/exhibits/v1.0.21/debugging-11-08-26-12-06-pm.log`, `docs/audits/notes/humid1-audit-v1.0.22.md`
- **Format Policy**: Markdown (`.md`) only — zero `.docx` files in repository.

## 1. Executive Summary

Following user testing of `epd-font v1.0.21` on the target Windows 11 workstation (`AMD Ryzen 5 5600G` 12 CUs + discrete `AMD Radeon RX Ellesmere` 32 CUs, `16,072 MB` Total Shared GPU Memory / `12,054 MB` 75% Arena Cap) and inspection of the intermediate Jr. Agent repair attempt (`epd-font-v1.0.21-fixme.zip`), a comprehensive pre-audit was conducted across the entire codebase, configuration files, async/multiprocessing runtime, OpenCL/CPU hardware dispatchers, CLI interfaces, and output directory structures.

Five critical and architectural findings (`PRE-22-01` through `PRE-22-05`) were identified and scheduled for remediation in `v1.0.22`:

| Finding ID | Subsystem | Severity | Pre-Audit Root Cause (`v1.0.21` / Jr. Agent State) | Target Remediation in `v1.0.22` |
| :--- | :--- | :--- | :--- | :--- |
| **`PRE-22-01`** | **`"debug_stages": true` Crash (`save_debug_stage_artifacts`)** | **High (Crash)** | In `tools/fonts/humid1_bilevel_pipelines.py:854`, the Jr. Agent removed `font_path` and `ft_lib` from `save_debug_stage_artifacts()`, but left `font_path=f_path, ft_lib=ft_lib` in the caller at `tools/fonts/humid1_ft_raster.py:728`. Enabling `"debug_stages": true` in `h1os_full.scheme.json` immediately crashed worker processes with `TypeError: save_debug_stage_artifacts() got an unexpected keyword argument 'font_path'`. | Remove the stale `font_path` and `ft_lib` keyword arguments at `humid1_ft_raster.py:728` so `save_debug_stage_artifacts()` executes cleanly when `"debug_stages": true` is enabled. |
| **`PRE-22-02`** | **`math_backend` Config-to-Runtime Disconnect & Silent Fallbacks** | **High** | 1. `run_parallel_tasks()` in `humid1_runtime.py` ignored the scheme's `math_backend` setting and always used the same pool topology.<br>2. `hw_dispatch.py` imposed high buffer-size thresholds (`arr.size >= 65536`, `>= 16384`, `>= 4096`) that caused individual glyphs to bypass OpenCL GPU kernels even when `math_backend = "gpu"` was selected.<br>3. `_probe_and_init_backend()` silently fell back to `"cpu"` when a requested hardware backend failed or was invalid. | Enforce strict upfront hardware verification and mode delegation for `"auto"`, `"cpu"`, `"gpu"`, `"hybrid"`, and `"sync"`. Remove silent fallbacks (fail with a clear error if `"gpu"` or `"hybrid"` is configured without verified GPU hardware) and remove the artificial buffer-size skips when running in `"gpu"` mode. |
| **`PRE-22-03`** | **Duplicate Config Variables, Assumed Defaults & Bloated CLI Flags** | **Medium-High** | 1. `esp32s3-N8R8-hw_scheme.json` and `generic_hw.json` contained duplicate string/byte pairs (`partition_1` + `partition_1_bytes`, `flash_total` + `flash_total_bytes`, `psram_total` + `psram_total_bytes`, `sram_total` + `sram_total_bytes`), unused metadata keys, and redundant `usable_width_px`.<br>2. `humid1_generate_1bpp.py` exposed 33 CLI flags duplicating scheme/hardware variables (`--dpi`, `--screen-width`, `--threshold`, `--gamma`, `--normal-weight`, etc.) and relied on hardcoded `.get(..., default)` fallbacks instead of strict validation. | Establish a **Singular Configuration Variable Matrix** (1 spot, 1 var, zero duplicate vars, zero assumed defaults). Strip redundant keys from `esp32s3-N8R8-hw_scheme.json` and `generic_hw.json`, enforce strict schema validation on all `.scheme.json` and hardware JSON files, and reduce all Python tool CLIs to minimal, consistent path/workflow flags. |
| **`PRE-22-04`** | **`inspect_pages/` Subdirectory Structure, Per-Method `master_char_icon_map.png` & `16px`/`38px` `compare_methods/`** | **Medium** | 1. Primary strike PNGs, `master_char_icon_map.png`, and `humid1_epd_specimen_188dpi.png` were written loose in `inspect_pages/` instead of `inspect_pages/default/`.<br>2. Method subdirectories (`inspect_pages/<method>/`) lacked their own `master_char_icon_map.png`.<br>3. `inspect_pages/compare_methods/` rendered one size per file instead of comparing **`16px` (low-detail) & `38px` (high-detail)** side-by-side. | Place all primary sheets in `inspect_pages/default/` (zero loose PNGs in `inspect_pages/`), generate `master_char_icon_map.png` inside every method subdirectory (`adf-biquadratic/` through `svg-potrace-jfa/` and `default/`), and upgrade `compare_methods/<font>.png` to feature both **`16px` (low-detail) & `38px` (high-detail)** across all 9 methods. |
| **`PRE-22-05`** | **Missing Single-Font Fast Debug Scheme (`h1os_debug.scheme.json`) & Outdated Docs/Agent Skills** | **Medium** | Verifying `"all-debug"` and `"debug_stages": true` on `h1os_full.scheme.json` required running 108 strikes (`972` method evaluations). Agent skill/rule files and `README.md` / `HOW_TO_GUIDE.md` lacked a complete Master Configuration Variable Matrix and `math_backend` mode breakdown. | Create `scripts/h1os-build-distro/h1os_debug.scheme.json` (1 font family with `16px` & `38px`, `pipeline: "all-debug"`, `sheet_debug: true`, `char_debug: true`, `debug_stages: true`) + `08_run_debug_scheme.bat`, and update `README.md`, `docs/HOW_TO_GUIDE.md`, and `tools/agent/` skills/rules. |

## 2. Detailed Technical Analysis

### 2.1 Analysis of the `"debug_stages": true` Exception (`PRE-22-01`)

From `docs/audits/exhibits/v1.0.21/debugging-11-08-26-12-06-pm.log`:
```text
  File "C:\Users\Matt\Documents\GitHub\epd-font\tools\fonts\humid1_ft_raster.py", line 728, in render_single
    save_debug_stage_artifacts(
        debug_dir=debug_stages_dir,
        strike_symbol=sym_lbl,
        codepoint=code,
        glyph_name=get_semantic_glyph_name(code, family),
        ft=ft,
        face_ptr=f_ptr,
        font_path=f_path,
        ft_lib=ft_lib,
        gidx=gidx,
        size_px=size_px,
        threshold=eff_thresh,
        gamma=gamma,
    )
TypeError: save_debug_stage_artifacts() got an unexpected keyword argument 'font_path'
```
Because the Jr. Agent removed `font_path: Path` and `ft_lib: ctypes.c_void_p` from `def save_debug_stage_artifacts(...)` in `humid1_bilevel_pipelines.py` without updating `humid1_ft_raster.py:728`, any scheme with `"debug_stages": true` failed on the first glyph of the first strike.

### 2.2 Analysis of `math_backend` Delegation & Hardware Resource Management (`PRE-22-02`)

1. **Worker Pool Topology Disconnect**:
   - In `v1.0.21`, `run_parallel_tasks()` in `humid1_runtime.py` always checked `has_opencl_gpu = (gpu_dev is not None or cpu_ocl_dev is not None)` and spawned `1` GPU worker + `11` CPU workers when `math_backend` was `"auto"` OR `"gpu"`. When `math_backend = "gpu"` was requested, the 11 CPU workers had `EPD_FONT_WORKER_ROLE="cpu"` set in `_worker_process_init_cpu()`, forcing 91% of the strikes to run on CPU instead of GPU.
   - Conversely, inside the GPU worker, `hw_dispatch.py` skipped OpenCL dispatch whenever `arr.size < 65536` (for sRGB linearization) or `< 16384` (for Otsu thresholding, median blur, and morphology close). For typical `12px–24px` glyph bitmaps, those size thresholds prevented GPU kernel execution.
2. **Memory & Thread Safety Check**:
   - `_terminate_executor_processes()` and `teardown_math_backends()` properly release `CL_MEM_ALLOC_HOST_PTR` buffers and `cl.Context` handles on exit and `Ctrl+C`, but `_probe_and_init_backend()` in the parent process created a probe `cl.Context` during `select_math_backend()` before spawning child workers. Releasing the parent probe context immediately after hardware validation ensures the parent process holds `0 MB` of GPU/Shared RAM while child workers execute.

### 2.3 Singular Configuration Audit ("1 Spot, 1 Var, Zero Defaults") (`PRE-22-03`)

Auditing all JSON configuration files and Python CLIs revealed:
- **Hardware Scheme JSON (`esp32s3-N8R8-hw_scheme.json`, `generic_hw.json`)**:
  - Redundant dual-unit fields: `partition_1` (`"3 MBytes"`) + `partition_1_bytes` (`3145728`), `flash_total` + `flash_total_bytes`, `psram_total` + `psram_total_bytes`, `sram_total` + `sram_total_bytes`.
  - Unused informational fields: `cpu_architecture`, `cpu_freq_mhz`, `flash_total*`, `psram_total*`, `sram_total*`, `partition_1_label`, `display.controller`.
  - Redundant derived field: `display.usable_width_px` (`188`), which is strictly `display.width_px - (2 * display.safe_margin_px)`.
  - **Cleaned Hardware Schema (`v1.0.22`)**: Retains only the 12 active, non-overlapping hardware and display variables: `schema_version`, `hw_scheme_id`, `description`, `chip_name`, `soc_vendor`, `partition_bytes`, and `display.{panel, width_px, height_px, dpi, safe_margin_px, color_depth_bpp, lvgl_color_format}`.
- **Profile Scheme JSON (`*.scheme.json`)**:
  - All operating parameters reside in `.scheme.json` (`hardware_scheme`, `raster_config`, `output_branding`, `character_sets`, `strikes`).
  - Removed all hardcoded `.get(..., default)` fallbacks in `humid1_runtime.py` and `humid1_generate_1bpp.py`: every required variable in `hardware_scheme` and `.scheme.json` is validated upfront before execution, and any missing, unknown, or out-of-range variable immediately halts execution with a clear diagnostic message.
