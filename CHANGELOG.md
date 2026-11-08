# Changelog — `epd-font` (A 1-bit EPD Font Generator and Asset Pipeline for Embedded Displays)

All notable changes to the `epd-font` repository ([Humidyne-Labs/epd-font](https://github.com/Humidyne-Labs/epd-font)) designed and developed by [Humiditron](https://github.com/humiditron) and the AI/LLM Collaborative Development Partner are documented in this file.

## [v1.0.21] — 2026-11-08

### Changed
- **Single-Source-of-Truth Hardware & Display Configuration (`esp32s3-N8R8-hw_scheme.json`, `generic_hw.json`, All 20 `.scheme.json` Files)**:
  - Removed the redundant 13-line `"target_display"` dictionary from all 20 `.scheme.json` files (`scripts/h1os-build-distro/h1os_full.scheme.json`, `h1os_lite.scheme.json`, `scripts/example-build-distro/example.scheme.json`, `scripts/full-audit-build-distro/full_audit_distro.scheme.json`, and all 16 schemes in `tools/fonts/schemes/*.scheme.json`).
  - Every `.scheme.json` now references its authoritative root hardware scheme (`"hardware_scheme": "esp32s3-N8R8-hw_scheme.json"` or `"generic_hw.json"`) at the top of the file, and `load_and_validate_hardware_scheme()` in `humid1_runtime.py`, `humid1_fw_emit.py`, `font_catalog_info.py`, and `string_info.py` resolve all MCU, `3 MByte` (`3,145,728` bytes) partition, and display (`200x200 @ 188.15 DPI`) attributes directly from the hardware config (or CLI `--hw-scheme <path>`).
- **1-Click Windows `.bat` Launcher & CMake Argument Cohesion (`scripts/*/*.bat`, `humid1_cmake_font_builder.py`, `humid1_fw_emit.py`, `humid1_font_eval.py`, `epd_font_esp_idf.cmake`)**:
  - Updated all 29 Windows 1-click `.bat` launchers (`scripts/h1os-build-distro/`, `scripts/example-build-distro/`, `scripts/full-audit-build-distro/`, and `scripts/font-eval-suite/`) to pass explicit `--hw-scheme`, `--scheme`, `--src-dir`, `--out-dir`, `--dist-dir`, and `--patches` arguments matching each script's exact workflow scope (`--workflow audit` in `full-audit-build-distro/03_visual_check_pngs.bat`, `--hw-scheme generic_hw.json` in `example-build-distro/`, and `--hw-scheme esp32s3-N8R8-hw_scheme.json` in `h1os-build-distro/` and `font-eval-suite/`).
  - Added `-H` / `--hw-scheme` (`HW_SCHEME` in CMake) across `humid1_fw_emit.py`, `humid1_cmake_font_builder.py`, `humid1_package_distro.py`, `humid1_font_eval.py`, `string_info.py`, and `epd_font_esp_idf.cmake`.

### Fixed
- **Spelling, Filename Case Normalization, Unused Code & AST Cohesion Audit (`PRE_AUDIT_REPORT_v1.0.20.md`, `POST_AUDIT_REPORT_v1.0.21.md`)**:
  - Removed the misspelled duplicate `genaric_hw.json` file and corrected `"hw_scheme_id": "generic_hw"` inside `generic_hw.json` (retaining a transparent fallback in `load_and_validate_hardware_scheme()` if an external script passes `genaric_hw.json`).
  - Wired `dispatch_median_blur`, `dispatch_morphology_close`, and `dispatch_msdf_median3_reconstruct` into `compute_mdf_bilevel_bitmap()` and `compute_msdf_bilevel_bitmap()` in `humid1_bilevel_pipelines.py`, deduplicated `trim_binary_array()` and `binary_array_to_rows()` in `humid1_ft_raster.py`, and removed all unused imports and dead functions (`0` unused imports and `0` dead definitions across all 26 Python modules).
  - Removed the duplicate `docs/LEGACY_METHODOLOGY_v1.0.17.md`, moved `docs/humid1-audit-v1.0.20.md` to `docs/audits/notes/humid1-audit-v1.0.20.md`, and normalized `docs/audits/H1OS_FONT_STRATEGY_REPORT_v1.0.16.md`.
  - Fixed `SharedHostMemoryArena.budget_bytes` attribute parity and suppressed Intel OpenCL `CompilerWarning` noise in `scripts/check_PyOpenCL.py` and `tools/fonts/math_backends/opencl_kernels.py`.

## [v1.0.20] — 2026-11-08

### Added
- **Multi-Device 3D NDRange OpenCL Kernels & 4-Queue Hardware Compute Striping (`tools/fonts/math_backends/opencl_kernels.py`, `hw_dispatch.py`)**:
  - Upgraded all six OpenCL C kernels (`srgb_to_linear_gamma_3d_kernel`, `render_bezier_sdf_yuksel_3d_kernel`, `sdf_valve_smoothstep_3d_kernel`, `msdf_median3_reconstruct_3d_kernel`, `adf_biquadratic_9pt_3d_kernel`, and `compute_histogram_local_atomic_3d`) to execute over full **3-Dimensional NDRanges (`work_dim = 3`, `[dim_x, dim_y, dim_z]`)** with 3D local work-groups `(8, 8, 4) = 256` work-items (`4` wavefronts of `64` threads on AMD GCN/Polaris `Ellesmere`), ensuring all `3` Work-Item Dimensions and all `32` GPU Compute Units (`2,048` stream processors) are actively utilized.
  - Added multi-queue command striping (`4` independent `cl.CommandQueue` instances per GPU context) to distribute kernel launches across multiple hardware compute rings (`Compute 0..3`).
- **Dynamic `75%` Host/GPU Shared Memory Arena (`SharedHostMemoryArena`, `SHARED_RAM_CAP_RATIO = 0.75`, `CL_MEM_ALLOC_HOST_PTR` + `clEnqueueMapBuffer`)**:
  - Added `detect_shared_gpu_memory_mb()` and `SharedHostMemoryArena` in `opencl_kernels.py` with a dynamic **`75%` cap on Total WDDM Shared GPU Memory** (`~11,775 MB` out of `15.7 GB` Shared GPU RAM on a `31.4 GB` Windows 11 system, bounded by free physical RAM minus a `512 MB` OS reserve) and persistent `cl.enqueue_map_buffer` (`CL_MAP_WRITE_INVALIDATE_REGION` / `CL_MAP_READ`) staging so batch tensors remain in host-visible GTT Shared GPU Memory rather than promoting into and exhausting the `4.0 GB` Dedicated GPU VRAM.
- **Jump Flooding Algorithm (`1+JFA`) + `2x2` Marching Squares Sub-Mode (`svg-potrace-jfa` / `--potrace-submode jfa-marching`)**:
  - Added `svg-potrace-jfa` (`jfa-marching`) as a selectable 9th pipeline and sub-mode of `svg-potrace` (`notes/potrace_break_down.md`), backed by three 3D NDRange OpenCL kernels (`jfa_init_marching_seeds_3d_kernel`, `jfa_flood_step_3d_kernel`, and `jfa_marching_squares_reconstruct_3d_kernel`) and a matching vectorized CPU implementation (`eval_jfa_marching_squares_cpu`). Combines branch-uniform `2x2` Marching Squares sub-pixel zero-crossing seed interpolation and logarithmic `1+JFA` jump flooding with `cv2.RETR_TREE` Potrace B-Spline `.svg` generation while remaining 100% MIT-licensed with zero GPL dependencies.
- **Heterogeneous GPU + CPU Work-Stealing Dispatcher (`tools/fonts/opencl_dispatcher.py`, `tools/fonts/build_fonts_hybrid.py`, `humid1_runtime.py`)**:
  - Added `opencl_dispatcher.py` and `build_fonts_hybrid.py` to enumerate and coordinate both discrete GPU OpenCL devices (`[0] Platform 0, Device 0: Ellesmere (ALL | GPU) - 32 CUs`) and host CPU OpenCL runtimes (`[1] Platform 1, Device 0: AMD Ryzen 5 5600G with Radeon Graphics (ALL | CPU) - 12 CUs` installed via the [Intel CPU Runtime for OpenCL Applications](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-cpu-runtime-for-opencl-applications-with-sycl-support.html)).
  - Implemented dual-pool deque work-stealing in `run_parallel_tasks()`: a single persistent GPU worker (`EPD_FONT_WORKER_ROLE="gpu"`) pulls heavy icon catalogs (`Tabler`, `Phosphor`, `Lucide`, `FontAwesome 7`), distance-field pipelines, and high point-size strikes (`28..40px`) from the front of the deque while `N-1` CPU workers (`EPD_FONT_WORKER_ROLE="cpu"`) pull `Terminus` bitmap strikes and small text strikes (`10..26px`) from the back of the deque.
- **OpenCL Runtime Libraries Setup Guide & Hardware Diagnostic Scripts (`README.md`, `scripts/check_PyOpenCL.py`, `scripts/probe_hardware.py`)**:
  - Documented installation and configuration of runtime OpenCL ICD libraries in `README.md` (Section 2.4 & 2.5), including the [Intel CPU Runtime for OpenCL Applications with SYCL Support](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-cpu-runtime-for-opencl-applications-with-sycl-support.html), [AMD Software: Adrenalin Edition / ROCm OpenCL Runtime](https://www.amd.com/en/support), [NVIDIA OpenCL ICD Runtime](https://developer.nvidia.com/opencl), and Linux `pocl` / `ocl-icd-libopencl1`.
  - Replaced legacy `python -m pyopencl.dump` instructions with `scripts/probe_hardware.py` and `scripts/check_PyOpenCL.py`.
- **Formal Pre-Audit and Post-Audit Reports (`docs/audits/PRE_AUDIT_REPORT_v1.0.19c.md`, `docs/audits/POST_AUDIT_REPORT_v1.0.20.md`)**:
  - Authored formal Markdown pre-audit (`v1.0.19c` baseline telemetry analysis) and post-audit (`v1.0.20` verification) reports with zero `.docx` files in the repository.

### Fixed
- **Eliminated `2.0–2.3 GB` Post-Termination GPU Memory Retention & Multi-Process Context Thrashing (`humid1_runtime.py`, `opencl_kernels.py`, `hw_dispatch.py`)**:
  - Enforced Single-Owner GPU Context isolation (`EPD_FONT_WORKER_ROLE="cpu"` in CPU worker processes) so `ProcessPoolExecutor` no longer spawns 12 competing `cl.Context` instances on the discrete GPU (`12 x ~190 MB = 2.3 GB` Dedicated VRAM).
  - Added deterministic `teardown_math_backends()` and `OpenCLMathAccelerator.release()` (`atexit` + `finally:` hooks) that flush/finish all queues, explicitly `.release()` every `cl.Buffer`, `cl.Kernel`, `cl.CommandQueue`, `cl.Program`, and `cl.Context`, terminate child worker processes before exit, and invoke `gc.collect()` so `0 MB` of GPU/Shared RAM remains allocated after termination.
- **Eliminated Noisy `Ctrl+C` (`KeyboardInterrupt`) Worker Tracebacks & Accelerated `raw-hinted` Builds (`humid1_runtime.py`, `build_static_ttf_assets.py`, `cpu_math.py`)**:
  - Registered `signal.signal(signal.SIGINT, signal.SIG_IGN)` inside child worker process initializers and added explicit `_terminate_executor_processes()` cleanup on `KeyboardInterrupt`, eliminating the interleaved `multiprocessing.process._bootstrap` stack traces when pressing `Ctrl+C`.
  - Added a precomputed L1-cached 256-byte `uint8` LUT (`_SRGB_GRAY_GAMMA1_U8_LUT`) for `gamma == 1.0` single-channel grayscale conversion, eliminating per-glyph PCIe transfer overhead on `raw-hinted` and `raw-unhinted` text strikes.

## [v1.0.19c] — 2026-11-07

### Added
- **Comprehensive Installation & Setup Guide (`README.md`, `requirements.txt`, `scripts/*/00_setup_env.bat`)**:
  - Added a detailed Installation and Setup Guide in `README.md` covering host operating system prerequisites (`Windows 10/11 x64` and `Linux x86_64/ARM64`), Python `3.9+` runtime setup, FreeType 2 shared library (`freetype.dll` / `libfreetype.so`) bundling, optional OpenCL `1.2`/`3.0` GPU driver setup ([Khronos OpenCL 3.0 Unified Specification](https://registry.khronos.org/OpenCL/specs/unified/refpages/man/html/)), required vs. optional package breakdown (`fonttools>=4.40.0`, `Pillow>=10.0.0`, `freetype-py>=2.4.0`, `numpy>=1.24.0`, `opencv-python>=4.8.0`, and optional `pyopencl>=2023.1`), step-by-step `venv` + `pip` commands for Windows (`PowerShell`/`CMD`) and Linux (`bash`), and one-line environment & hardware backend verification.
  - Added root `requirements.txt` and updated `scripts/*/00_setup_env.bat` to upgrade `pip setuptools wheel` and install from `requirements.txt`.

## [v1.0.19b] — 2026-11-07

### Added
- **Modular GPU/CPU Mathematical Abstraction Package (`tools/fonts/math_backends/`)**:
  - Abstracted all resolution-reduction, polynomial root-finding, luminance linearization, and thresholding math into four modular backend files:
    1. `tools/fonts/math_backends/opencl_kernels.py`: PyOpenCL GPU / heterogeneous compute kernels conforming to the [Khronos OpenCL 3.0 Unified Specification](https://registry.khronos.org/OpenCL/specs/unified/refpages/man/html/), implementing `srgb_to_linear_gamma_kernel`, `render_bezier_sdf_yuksel_kernel` (Cem Yüksel degree-5 to degree-2 monotonic derivative cascade + Newton-Bisection quintic solver + cubic ray-crossing winding parity), `sdf_valve_smoothstep_kernel` ($L_2$ screen-space gradient smoothstep), `msdf_median3_reconstruct_kernel` ([Chlumsky/msdfgen](https://github.com/Chlumsky/msdfgen)), `adf_biquadratic_9pt_kernel` (Saffron 9-point biquadratic Lagrange $4\times 4$ quadrature), and `compute_histogram_local_atomic` (`__local uint local_hist[256]` work-group atomic histogram for Otsu $\sigma_B^2(k^*)$). Uses wavefront-aligned `16x8` / `8x8` work-groups and `CL_MEM_ALLOC_HOST_PTR` zero-copy pinned host buffers.
    2. `tools/fonts/math_backends/umat_math.py`: OpenCV Transparent API (`cv2.ocl` / `cv2.UMat`) OpenCL secondary GPU acceleration tier.
    3. `tools/fonts/math_backends/cpu_math.py`: Vectorized `NumPy` / `OpenCV` CPU implementations with 1:1 function signatures (including CPU Cem Yüksel quintic Bézier root-finding).
    4. `tools/fonts/math_backends/hw_dispatch.py`: Runtime hardware capability probe (`select_math_backend()`, `describe_math_backend()`, `validate_sdf_gradient()`) that verifies device compiler availability, kernel parity, and unit SDF gradient slope ($\|\nabla d\|_2 \approx 1.0$) before dispatching math calls to `opencl`, `umat`, or `cpu`.
  - Added `--accel {auto,opencl,umat,cpu}` CLI flag (and `"math_backend": "auto"` in `.scheme.json`) to `humid1_generate_1bpp.py` and `humid1_font_eval.py`.

### Changed
- **Calibrated Exact Physical EPD Resolution to `188.15 DPI` (`25.4 mm / 0.135 mm`)**:
  - Updated target display resolution from `188.3 DPI` to **`188.15 DPI`** across `esp32s3-N8R8-hw_scheme.json`, `genaric_hw.json`, `generic_hw.json`, all `20` `.scheme.json` files, `.bdf` / `.c` / `.h` exporters, and visual specimen sheets per the Waveshare 1.54" e-Paper V2 (`SSD1681` / `GDEY0154D67`) mechanical specification (`200 x 200` pixels, `27.00 mm x 27.00 mm` active area, `0.135 mm x 0.135 mm` pixel pitch).
- **Documented Physical Justification for 1-Bit Bilevel EPD Rendering**:
  - Documented the electro-optical constraints of 2-bit (4-level) EPD driving (Arrhenius thermal viscosity drift, Kubelka-Munk sigmoidal reflectance, inter-frame hysteresis across SSD1681 `0x24`/`0x26` 5,000-byte RAM planes, DC bias degradation, and `1,000–1,500 ms` refresh latency vs. `250–350 ms` 1-bit partial updates) in `docs/MAINTAINER_SPEC.md` and `docs/audits/POST_AUDIT_REPORT_v1.0.19b.md`.

## [v1.0.19] — 2026-11-07

### Added
- **Eight Resolution-Reduction Conversion Pipelines (`tools/fonts/humid1_bilevel_pipelines.py`, `humid1_ft_raster.py`, `humid1_font_eval.py`)**:
  - Added true **Multi-Channel Signed Distance Field (`msdf`)** pipeline ([Chlumsky/msdfgen](https://github.com/Chlumsky/msdfgen)) using corner-delimited contour decomposition, 3-channel $(R, G, B)$ edge coloring (`Yellow`, `Cyan`, `Magenta`), directional signed pseudo-distance evaluation, and $\text{median}(R, G, B)$ corner-preserving reconstruction alongside `mdf`.
  - Added three resolution-reduction pipelines derived from the distance-field and vector rasterization literature:
    1. **`sdf-smoothstep`**: `16x` Euclidean Signed Distance Field with analytical Hermite `smoothstep` edge reconstruction ([Red Blob Games SDF Typography](https://www.redblobgames.com/articles/sdf-fonts/)).
    2. **`adf-biquadratic`**: Adaptive Distance Field (`ADF`) quadtree subdivision (`16x` -> $4\times 4$ cells) with 9-point biquadratic polynomial surface interpolation $P(u, v)$.
    3. **`otsu-adaptive`**: Linear-luminance Otsu global threshold blended with local Sauvola mean/variance adaptive thresholding for small-ppem counter preservation.
  - Added **True sRGB-to-Linear Grayscale Conversion (`rgb_to_linear_grayscale`) + Optional Gamma Factor (`--gamma`)**: Converts sRGB or single-channel coverage rasters to linear luminance ($Y_{\text{lin}} = 0.2126 R_{\text{lin}} + 0.7152 G_{\text{lin}} + 0.0722 B_{\text{lin}}$) and applies configurable gamma adjustment (`--gamma`, default `1.0`) prior to thresholding.
- **Root Hardware Partition Schemes (`esp32s3-N8R8-hw_scheme.json`, `genaric_hw.json`, `generic_hw.json`) & Strict Single `3 MByte` Partition Validation**:
  - Added root `esp32s3-N8R8-hw_scheme.json` and `genaric_hw.json` (`"partition_1": "3 MBytes"`, `"partition_1_bytes": 3145728`).
  - Removed all hardcoded partition fallback defaults (`3 Mbit`, `64 KB..8 MB` lookup tables) in `humid1_runtime.py`, `humid1_lvgl_bdf_export.py`, and `humid1_fw_emit.py`. If the `3 MByte` (`3,145,728` bytes) partition specification is removed or missing from `.scheme.json` / hardware scheme, the pipeline fails immediately with a clear configuration error.
- **Strict `char_debug` & `sheet_debug` Boolean Gating + `all` / `all-debug` Multi-Method Sheet Comparison (`humid1_generate_1bpp.py`, `humid1_visual_check.py`)**:
  - Added explicit `"char_debug"` (`--char-debug` / `--no-char-debug`) and `"sheet_debug"` (`--sheet-debug` / `--no-sheet-debug`) boolean controls. When `false`, zero character PNGs or sheet PNGs are emitted.
  - When `"pipeline": "all"` or `"all-debug"` is configured, the pipeline executes all 8 conversion methods and dumps per-method character sheets (`inspect_pages/<method>/<symbol>.png`) and side-by-side 8-method visual comparison sheets (`inspect_pages/compare_methods/<symbol>_all_methods.png`).
- **Formal Pre-Audit and Post-Audit Reports (`docs/audits/PRE_AUDIT_REPORT_v1.0.18.md`, `docs/audits/POST_AUDIT_REPORT_v1.0.19.md`)**:
  - Authored formal Markdown pre-audit (`v1.0.18` baseline) and post-audit (`v1.0.19` verification) reports with zero `.docx` files in the repository.

### Fixed
- **Resolved Full Audit (`scripts/full-audit-build-distro/`) Crash (`humid1_ft_raster.py`, `humid1_generate_1bpp.py`, `full-audit-build-distro/*.bat`)**:
  - Fixed `TTFont` file handle leak in `_get_cached_tt_meta()` / `rasterize_font_strike()` that previously leaked `11,040` open file descriptors across worker processes during the 368-strike `10px..40px` (`step 2px`) audit (`OSError: Too many open files` / `BrokenProcessPool` on Windows CRT).
  - Updated `02_build_fonts.bat` and `99_run_full_pipeline.bat` to eliminate redundant triple-audit passes and respect `char_debug: false` by default.
- **Resolved Filled Icon Asset Sheet Rendering Bug (`humid1_ft_raster.py`, `humid1_bilevel_pipelines.py`, `humid1_visual_check.py`)**:
  - Fixed `load_icon_name_registry()` rebinding `ICON_NAME_REGISTRY` locally instead of mutating the shared dictionary in place (`clear()` + `update()`), which previously caused `humid1_icon_tabler_filled_*` (`Tabler-Filled.ttf`, `U+EE80..U+FA6D`) to resolve `0` glyphs (`PATCHED: 0/0`, blank sheet).
  - Upgraded `svg-potrace` contour extraction from two-level `cv2.RETR_CCOMP` to full hierarchical `cv2.RETR_TREE` with topological tree-depth rasterization so filled icons with nested interior cutouts (`Tabler-Filled.ttf`, `Phosphor-Fill.ttf`, `FontAwesome7-Solid.ttf`) preserve all interior islands and counters.
  - Fixed `draw_icon()` in `humid1_visual_check.py` to render filled icons cleanly on the 200x200 EPD specimen screens.
- **Removed Retained Legacy Auto-Tuner Dead Code**:
  - Deleted `tools/fonts/humid1_bilevel_tuner.py` and removed deprecated `--auto-floor`, `--repair-engine`, and `--tune-mode` flags from `humid1_generate_1bpp.py`.

## [v1.0.18] — 2026-11-07

### Added
- **Four-Method Bilevel (`1-bpp`) Conversion Pipeline Engine (`tools/fonts/humid1_bilevel_pipelines.py`, `humid1_ft_raster.py`)**:
  - Implemented `raw-unhinted` (direct unhinted FreeType grayscale rasterization + configurable threshold, default `128`).
  - Implemented `raw-hinted` (grid-fitted hinted FreeType rasterization + configurable threshold, default `128`).
  - Implemented `svg-potrace` (high-resolution `10x` anti-aliased rasterization -> binary threshold -> Potrace B-spline / cubic Bézier `.svg` vector contour tracing -> `+0.5 px` half-pixel center alignment -> non-antialiased `LINE_8` even-odd re-rasterization).
  - Implemented `mdf` (high-resolution `12x` super-sampling with median filter + Multi-Channel / Euclidean Signed Distance Field computation -> pixel-center downsampling -> configurable threshold, default `128`).
- **Per-Stage Visual Debug Output (`--debug-stages`, `--verbose`)**:
  - Added `save_debug_stage_artifacts()` emitting raw `.svg` vector files and 5-stage visual comparison cards (`10x Grayscale`, `10x Binary`, `Potrace SVG Vector`, `MDF Distance Field`, and `4-Pipeline 1-BPP Grid`) into `build/<workflow>/debug_stages/`.
- **4-Pipeline Per-Font, Per-Size Evaluation & Visual Audit Suite (`humid1_font_eval.py`, `humid1_generate_1bpp.py`)**:
  - Updated `humid1_font_eval.py` and `--workflow audit` to evaluate all 4 conversion methods (`raw-unhinted`, `raw-hinted`, `svg-potrace`, `mdf`) for every font and every pixel size, generating per-font 4-pipeline comparison PNGs (`build/evals/sheets/*_eval.png`) and master comparison scorecards.
  - Updated `full_audit_distro.scheme.json` and `TERMINUS_BDF_CONVERSION_TABLE` to cover the complete `10px - 40px` (`step size 2px`) ladder (`16` even pixel sizes per strike) and enabled `.bdf` output across all sizes `10px..40px`.
  - Added `render_master_char_icon_map_png()` generating a combined full-scheme master character and icon map PNG (`inspect_pages/master_char_icon_map.png`) alongside per-strike sheets and per-character blueprint PNGs.
- **ESP-IDF CMake Font Builder & Portable Versioned Distribution Packager (`humid1_cmake_font_builder.py`, `humid1_package_distro.py`, `cmake/`)**:
  - Added `tools/fonts/humid1_cmake_font_builder.py`, `tools/fonts/cmake/epd_font_esp_idf.cmake`, and `tools/fonts/cmake/example_CMakeLists.txt` for direct integration into ESP-IDF CMake build systems.
  - Added `tools/fonts/humid1_package_distro.py` to automatically copy all upstream font/icon/pipeline license files and package versioned `.zip` archives (`dist/epd-font_<workflow>_v1.0.18.zip`).
- **Host Hardware Utilization, Clean `Ctrl-C` Handling & Strict CLI Validation (`tools/fonts/humid1_runtime.py`)**:
  - Added GPU/OpenCL/CUDA detection (`cv2.UMat`), multi-core CPU / dynamic RAM worker scaling, deterministic strike caching (`build/cache/`), clean `SIGINT` (`Ctrl-C`) worker pool shutdown, recursive font/license discovery across `.ttf/.otf/.ttc/.bdf` files, and explicit CLI/path validation with zero hardcoded user paths.
- **ESP32-S3-N8R8 (`3 Mbit` & `3 MByte`) Per-Build & Per-Font-Pair ROM Space Estimator (`rom_space_estimate.txt`)**:
  - Added configurable partition targets (`target_partition_bits`, `target_partition_bytes`, `--partition-config <ini>`) and per-font-pair (`Normal + Bold`) `.rodata` tables to `rom_space_estimate.txt` and `total_disk_size.txt`.
- **Formal Pre-Audit, Post-Audit & Legacy Methodology Documentation (`docs/`)**:
  - Added `docs/LEGACY_METHODOLOGY_v1.0.17.md`, `docs/audits/PRE_AUDIT_REPORT_v1.0.17.md`, and `docs/audits/POST_AUDIT_REPORT_v1.0.18.md`.

### Changed
- **Retired Algorithmic Auto-Tuner in Favor of Manual Closed-Loop ASCII Patching**:
  - Removed automatic glyph mutation (`08_iterative_auto_repair.bat` and `M0..M8` auto-tuning passes) and cleared synthetic auto-tuner entries from `font_icon_epd_patches.json` so all glyph adjustments are controlled manually via Full-Canvas `1:1` ASCII patch files.
- **LVGL `>= 9.6.0` Validated Fallback Font Pointers (`humid1_lvgl_bdf_export.py`, `humid1_fw_emit.py`)**:
  - Fixed fallback symbol prefix normalization and DAG validation in `humid1_fw_emit.py` and `humid1_lvgl_bdf_export.py`, adding `#if LV_VERSION_CHECK(9, 6, 0) || LVGL_VERSION_MAJOR >= 9` and `.static_bitmap = 0` support.
- **Project Rebranding & Lexicon Rule Compliance**:
  - Rebranded repository as `"A 1-bit EPD font generator and asset pipeline for embedded displays"` (`epd-font`) crediting both [Humiditron](https://github.com/humiditron) and the AI/LLM development partner, and updated terminology across the repository to strictly follow IEEE, mathematical, and scientific nomenclature.

## [v1.0.17] — 2026-11-05

### Added
- **Curated Hinted Google Noto (`noto_v2.013`) + Hinted IBM Plex (`hinted_static`) Asset Suite (`assets/font_assets/`, `build_static_ttf_assets.py`)**:
  - Added 22 curated Hinted Google Noto v2.013 `.ttf` cuts (`NotoSans`, `NotoSans-SemiCondensed`, `NotoSans-Condensed`, `NotoSansMono`, `NotoSerif`, `NotoSansMath`) + `char_manifest_noto_v2.013.json`.
  - Added 24 official Hinted IBM Plex static `.ttf` cuts (`Regular w400`, `Medium w500`, `SemiBold w600`, `Bold w700` + Italics across `Sans`, `Condensed`, `Mono`, `Serif`) alongside Variable masters (`ExtraBold w800` synthesis) and Hinted `IBMPlexMath-Regular.ttf`.
  - `build_static_ttf_assets.py` now builds and verifies **113 static `.ttf` files (`113 PASSED, 0 FAILED`)** in `build/static_ttfs/`.
- **Best-of-the-Best Division-of-Labor Mapping (`humid1_generate_1bpp.py`, `h1os_full.scheme.json`, `h1os_lite.scheme.json`)**:
  - Upgraded `cond` role to Hinted `NotoSans-SemiCondensed` (`Medium w500` + `Black w900` + `SemiBoldItalic w600` — Triad Score `91.0`, `14px` Bold floor, `100.0%` counters), `serif` role to Hinted `NotoSerif` (`Medium w500` + `Black w900` + `MediumItalic w500` — Triad Score `84.9`, `16px/14px` floors, replacing `IBMPlexSerif` without `Literata`), and `math` role to Hinted `NotoSansMath-Regular.ttf` (with automatic secondary glyph fallback to `IBMPlexMath-Regular.ttf`).
  - Added explicit `noto_sans`, `noto_cond`, `noto_mono`, `noto_serif`, `noto_math`, `plex_sans`, `plex_cond`, `plex_mono`, `plex_serif`, and `plex_math` family keys.

### Fixed
- **Unified FreeType 2 Auto-Hinting Engine (`humid1_ft_raster.py`, `humid1_font_eval.py`)**:
  - Fixed `"autohint_mono"` vs `"autohint-mono"` discrepancy in `resolve_freetype_flags()` so both build and evaluation pipelines execute Symmetric 8-Bit Auto-Hinting + Coverage Thresholding (`FT_LOAD_RENDER | FT_LOAD_FORCE_AUTOHINT | FT_LOAD_TARGET_NORMAL`), improving `16px` HQ confidence by `+3.6%..+5.7%` and eliminating 1-bit scanline spurs. Added `--raster-mode` CLI flag to `humid1_font_eval.py`.
- **Closed-Loop Bowl-Join Bridge Sealer & Pre-Exit Gate Fix (`humid1_bilevel_tuner.py`)**:
  - Added Step 2a (`HQ Coverage Hysteresis Arch Recovery + 1px/2px Bowl-Join Bridge Sealer`) inside `preserve_interior_apertures()` to seal 1px anti-aliased bowl-to-stem join leaks on `q, b, a, 8`, achieving **`100.0%` counter survival at `16px` across 50 of 51 foundry cuts**.
  - Fixed undefined `b1_m0_now` variable in `inspect_and_repair_glyph_bitmap()` when `--tune-mode off` is used, and fixed pre-exit checks (`lines 1423–1438`) testing `b1_base` instead of `b1_m0_now`.
- **Width-Preserving Family Stem Extraction (`humid1_font_eval.py`)**:
  - Updated `extract_base_family_stem()` to preserve `SemiCondensed`, `Condensed`, and `ExtraCondensed` width sub-families during Triad evaluation.
- **Zero-Hole Audit & Fix Across All 20 `.scheme.json` Files**:
  - Upgraded all 20 `.scheme.json` files to `schema_version: "1.0.17"`, fixed 6 broken `default_font` pointers and 121 unresolved `semantic_roles` pointers (`0` broken pointers remain), and recompiled `1,073` auto-repaired glyph patches into `font_icon_epd_patches.json`.

## [v1.0.16] — 2026-11-05

### Fixed
- **Resolved Visual Weight Homogeneity Across `Normal`, `Bold`, and `Italic` (`humid1_font_eval.py`, `humid1_generate_1bpp.py`, `*.scheme.json`)**:
  - Diagnosed why single-font isolated scoring in `v1.0.15` caused `Normal (w600 SemiBold, 2.36px)`, `Bold (w700 Bold, 2.57px — only +6.5% ink delta)`, and `Italic (w800 ExtraBoldItalic, 3.08px — heavier than Bold!)` to look like the same weight or invert the hierarchy.
  - Fixed `humid1_generate_1bpp.py` ignoring `bold_weight` and `italic_weight` from `.scheme.json` and updated all 19 `.scheme.json` files (`h1os_full.scheme.json`, `h1os_lite.scheme.json`, `example.scheme.json`, `tools/fonts/schemes/*.scheme.json`) from `"bold_weight": 700` to **`"bold_weight": 800, "italic_weight": 600, "normal_weight": 500`**.
  - `Sans` at `16px` now delivers **`2.17px` `Normal` (`w500`, `2,566` ink)** vs. **`3.13px` `Bold` (`w800 ExtraBold`, `3,482` ink = `+35.7%` Ink Contrast Gain / `+0.96px` stem jump!)** vs. **`2.30px` `Italic` (`w600 SemiBoldItalic`, `2,600` ink = `+1.3%` iso-weight subtle emphasis, `-33.9%` lighter than Bold!)**.
- **Universal Aperture-Preservation & Loop-Unpinching on Heavy `ExtraBold (w800)` / `Black (w900)` & `Italic` Cuts (`humid1_bilevel_tuner.py`)**:
  - Added `preserve_interior_apertures()` (`M0_counter_carved`) so glyphs that skip stem thickening (`is_bold_role=True` or high-confidence `M0`) still have collapsed/pinholed counters (`<2px` on `a, e, o, b, d, p, q, g, 0, 4, 6, 8, 9, A, B, D, O, P, Q, R, $, %, &`) and pinched open curves (`s, c, w, M`) precisely opened open using the `8x` HQ continuous master.
  - Clamped `expected_b1 = 1` on `SINGLE_COUNTER_OPEN_TAIL_CHARS` (`0469ADOPQRabdeopq`) so single-story italic `a` or two-story hooks never trigger false 2-hole targets. Both `IBMPlexSans-ExtraBold (w800)` and `IBMPlexSans-SemiBoldItalic (w600)` now achieve **`100.0%` counter survival from `12px` to `24px`**.

### Added
- **Tri-Role Visual Contrast Triad Scorer & Contrast Sheet (`humid1_font_eval.py`)**:
  - Added `classify_font_role_and_score()`, `evaluate_family_triads()`, `render_triad_contrast_sheet()` (`build/font_eval/font_eval_triad_contrast_sheet.png`), and `--re-digest-json` to evaluate complete `(Normal + Bold Contrast Gain + Subtle Iso-Weight Italic)` family triads and re-digest the 425-font / 30-family evaluation corpus.
- **Instantiated `SemiBoldItalic (w600)` Static TTFs Across All IBM Plex Families (`build_static_ttf_assets.py`)**:
  - Added `IBMPlexSansCondensed-SemiBoldItalic.ttf`, `IBMPlexMono-SemiBoldItalic.ttf`, and `IBMPlexSerif-SemiBoldItalic.ttf` alongside `IBMPlexSans-SemiBoldItalic.ttf`.

## [v1.0.15] — 2026-11-05

### Fixed
- **Master Multi-Font Evaluation Sheet Truncation Bug (`humid1_font_eval.py`)**:
  - Removed the hardcoded `shown = list(summaries[:60])` slice in `render_font_eval_comparison_sheet()` that silently dropped fonts `61..408` during large external evaluations (`batch_02`).
  - When `len(summaries) > 75`, `render_font_eval_comparison_sheet()` now emits **paginated full-corpus sheets (`font_eval_comparison_sheet_p01_of_XX.png` .. `pXX_of_XX.png`)** plotting **100% of evaluated samples** without hitting vertical texture limits, while writing `font_eval_comparison_sheet.png` as the **Top 75 Ranked Contenders Overview** sorted by `compute_composite_epd_score()`.
- **Replaced Rigid `128` Threshold with Weight-, Size-, and Otsu-Adaptive Dynamic Thresholding (`humid1_ft_raster.py` & `humid1_bilevel_tuner.py`)**:
  - Added `compute_dynamic_threshold()` (`humid1_ft_raster.py`) and `compute_dynamic_hq_threshold()` (`humid1_bilevel_tuner.py`), plus `--raster-mode dynamic-threshold` and `--threshold 0` (auto).
  - Dynamically lowers the binarization threshold (`104..118`) on `w400–w500` cuts to preserve split `1.5px` stems as `2px`, and raises it (`136..152`) on `w700–w900` heavy cuts to prevent gray fringe bleed from pinching enclosed counters (`'a'`, `'e'`, `'8'`, `'B'`).
- **Upgraded Default `italic` Role from `MediumItalic (w500)` to `BoldItalic (w700)` (`humid1_generate_1bpp.py`)**:
  - Replaced `IBMPlexSans-MediumItalic.ttf` (`24px` floor, `15.0%` `>=2px` stems at `14px`, `66.7%` tuning burden) with `IBMPlexSans-BoldItalic.ttf` (and `IBMPlexMono-BoldItalic.ttf`, `IBMPlexSerif-BoldItalic.ttf`) when `normal_weight >= 500`, improving the Italic viable size floor from `24px` to **`16px`** (`96.7%` `>=2px` stems, `100.0%` open counters, `3.3%` tuning burden).
- **General Code Audit Cleanups (`humid1_ft_raster.py`, `tools/agent/`, `schemes/`)**:
  - Removed duplicate mid-file import block in `humid1_ft_raster.py`, suppressed `fontTools` `2 extra bytes in post.stringData array` console warnings, and synchronized all version strings across `tools/agent/`, `tools/fonts/`, `scripts/`, `schemes/`, and `VERSION.json` to `v1.0.15`.

### Changed
- **Simplified `humid1_bilevel_tuner.py` into a Clean 3-Stage Architecture (~2.5x Faster)**:
  - Pruned redundant/low-yield synthesis passes (`M1`'s 18 `warpAffine` shifts, `M2`'s `0.4%`-win-rate 4x Python medial-axis loop, `M3`'s duplicate 4x SDF, and `M6`'s 1-way shift) into 3 orthogonal stages: **Stage 0 (`M0_wart_shaved`)** 4-Directional Outline-spur Shaver, **Stage 1 (`M1_dyn_thresh` / `M1_hysteresis`)** Dynamic Threshold + Dual-Hysteresis 8x HQ Area-Downscale, **Stage 2 (`M2_collinear`)** Outward/In-Place Collinear Stem Floor, and **Stage 3 (`M3_central_spine` + `MirrorSync`)**.

### Added
- **408-Font Contender Analysis & Head-to-Head Comparison vs. IBM Plex (`docs/audits/FONT_CONTENDERS_ANALYSIS_v1.0.15.md`)**:
  - Documented the Top 3 Contenders for Regular/Normal (`Inter-SemiBold w600`, `InstrumentSans-SemiBold w600`, `RecursiveSansLnrSt-SemiBold w600`), Bold (`Inter-Bold w700`, `RecMonoDuotone-Bold w750`, `NotoSans-Bold w700`), and Italic (`Inter-ExtraBoldItalic w800`, `RecursiveSansLnrSt-ExBdItalic w800` / `SmBdItalic w600`, `Roboto-BoldItalic w700`) compared head-to-head against IBM Plex and Terminus.

## [v1.0.14] — 2026-11-04

### Fixed
- **`.ttc` TrueType Collection Crash in `humid1_ft_raster.py` & `humid1_font_eval.py` (`crash-log.txt` Font `[61/408]`)**:
  - Fixed `rasterize_font_strike()` in `tools/fonts/humid1_ft_raster.py` (line 566) throwing `fontTools.ttLib.TTLibFileIsCollectionError: specify a font number between 0 and 2 (inclusive)` when evaluating `.ttc` TrueType Collection files (such as `IosevkaAile-Bold.ttc`).
  - Added `open_ttfont_safe(font_path, font_number=0, lazy=False)` across `humid1_ft_raster.py`, `humid1_font_eval.py`, and `humid1_generate_1bpp.py`, plus `try...except Exception` worker fault isolation in `_worker_evaluate_font()` so a single corrupted or unreadable font in a 400+ font directory never halts the multi-core evaluation pool.
- **"Ghost Font" `>=2px: 100.0%` Paradox on Ultra-Thin Weights (`Inter-Thin w100` / `InterDisplay-ThinItalic w100`)**:
  - Fixed `measure_stem_deficits()` in `humid1_bilevel_tuner.py` returning `h_ratio = 1.0, needs_h = False` when `nz == 0` or `total_stem_runs == 0`, and updated `_worker_evaluate_font()` in `humid1_font_eval.py` to evaluate all `len(EVAL_BENCHMARK_CHARS)` characters without skipping vanished glyphs (`box_w == 0`). Ultra-thin `w100–w200` cuts that suffer sub-pixel hairline dropout under 1-BPP rasterization now properly report `>=2px: 0.0%`, `Size Floor: >24px`, and `TIER 4: DO NOT USE ON 1-BPP EPD`.
- **Recalibrated Realistic Pixel Size Floor Estimator (`size_floor_raw_px` & `size_floor_tuned_px`)**:
  - Removed the `if w0 >= 5 and h0 >= 7:` gate on `expected_b1` in `humid1_bilevel_tuner.py` that caused collapsed counters on lowercase `a` and `e` at `10px–12px` (`h0 = 6`) to be ignored (`expected_b1 = 0`).
  - Added `CANONICAL_MIN_HOLES`, `PINCH_FORBIDDEN_CHARS`, and `_check_counter_cavity_viable()` (`hole_px >= 2` on core single-loop counters in heavy weights `wght >= 650`, `b1 == 0` on open curves `s`, `c`, `w`, `M`, `HQConf >= 72.0%`, and `mean_stem_width >= 1.62px`). Heavy cuts (`Inter-ExtraBold w800`, `IBMPlexSans-ExtraBold w800`) now report a realistic **`16px` (`12.0pt`)** floor instead of `10px–12px`.
- **Eliminated Residual 4-Directional "Outline-spurs" (`M0_wart_shaved`)**:
  - Upgraded `detect_skin_tags_and_notches()` in `humid1_bilevel_tuner.py` to scan all 4 cardinal directions (horizontal left/right lateral spurs on `fg[r]` + vertical top/bottom protrusions on `fg[:, c]` verified against the 8x continuous HQ Master coverage map).
  - Added a **Universal Pre-Exit spur-Shaving Pass (`M0_wart_shaved`)** inside `inspect_and_repair_glyph_bitmap()` so that even glyphs that skip stem thickening (`Bold`/`ExtraBold` and `>=14px` `Medium`/`SemiBold`) have their 1px autohint outline-spurs cleanly shaved off.
- **Synchronized `.bat` Script Banners to `v1.0.14`**:
  - Updated all batch script `echo` headers across `scripts/h1os-build-distro/`, `scripts/example-build-distro/`, and `scripts/full-audit-build-distro/` from `v1.0.11` to `v1.0.14`.

### Added
- **Selectable `--tune-mode {off,spur-only,targeted,full}` Across Build & Evaluation Pipeline**:
  - Added `--tune-mode` to `humid1_bilevel_tuner.py`, `humid1_generate_1bpp.py`, and `humid1_font_eval.py` (plus `"tune_mode"` in `*.scheme.json`) to support native font/weight division-of-labor (`off` = 100% pure FreeType, `spur-only` = zero stem thickening with 4-directional spur shaving + mirror bracket sync, `targeted` = default, `full` = full multi-method evaluation).

## [v1.0.13] — 2026-11-04

### Fixed
- **External Font Directory Discovery in `humid1_font_eval.py` & `02_run_font_eval.bat`**:
  - Fixed `discover_candidate_fonts()` in `tools/fonts/humid1_font_eval.py` so pointing `--src-dir` at an external font directory (such as the 700MB+ `eval_fonts` collection with 400+ `.ttf`, `.otf`, and `.ttc` TrueType Collection files) recursively discovers and evaluates all Latin fonts in parallel across all CPU cores (`ProcessPoolExecutor`), instead of checking only for hardcoded `IBMPlex*` filenames.
- **Eliminated Valley Clogging on `'W'`, `'w'`, `'M'`, `'m'`, `'N'`, `'X'`, `'s'` (`humid1_bilevel_tuner.py`)**:
  - Enforced the **Multi-Stroke Pigeonhole Law** (`k_runs * min_stem + (k_runs - 1) <= box_w`), **Open-Valley Scanline Run-Count Invariance (`compute_open_valley_stats`)**, and the **Render -> 8x Upscale -> HQ Master Confidence & Valley-Occlusion Sanity Gate (`compute_upscaled_hq_metrics`)**, mathematically preventing open V-valleys in `'W'`/`'w'`/`'M'` from ever being bridged into a solid black mass.
- **Eliminated Stale Legacy Patch Accumulation & Over-Correction on `'A'`, `'B'`, `'f'`, `'g'`, `'s'`, `')'`**:
  - Fixed `build_patches_json_from_ascii_root()` in `tools/fonts/humid1_ascii_patches.py` so each strike dictionary in `font_icon_epd_patches.json` is replaced cleanly rather than merged via `.update()` onto stale `v1.0.9–v1.0.11` overrides.
  - Added the **"Do No Harm" Conservative Targeted Trigger Gate**, leaving already-thick `Bold` / `ExtraBold (800)` glyphs and high-confidence `Medium (500)` glyphs (`HQConf >= 72%`) 100% untouched (`M0_verified`), reducing total compiled patches across all 63 H1OS strikes from `1,816` down to **`651` targeted overrides**.

### Added
- **Pre-Tune (`RAW`) vs. Post-Tune (`TUNED`) Traceability & Per-Font PNG Evaluation Sheets (`build/font_eval/sheets/*_eval.png`)**:
  - `humid1_font_eval.py` now records and renders both untouched FreeType (`PRE-TUNE / RAW`) and multi-method evaluation-repaired (`POST-TUNE / TUNED`) metrics (`HQ Confidence %`, `HQ Diff %`, `>=2px Stem %`, `Counter %`, and `Tuning Burden %`) across all sizes.
  - Emits a dedicated visual inspection PNG sheet per font (`build/font_eval/sheets/<font_stem>_eval.png`) with 1:1 specimen strings and 2x-zoomed critical glyph strips (`W w M m A B C f g r s $ ( ) [ ] 0 8`), plus `build/font_eval/font_eval_report.csv`, `.md`, `.json`, and `font_eval_comparison_sheet.png`.

## [v1.0.12] — 2026-11-04

### Fixed
- **Root `2px` Stray File Bug (`08_iterative_auto_repair.bat`)**: Removed the stray `2px` file from the repository root and replaced unescaped `>=2px` inside `echo` statements with `2px+` across `scripts/h1os-build-distro/08_iterative_auto_repair.bat`, `scripts/example-build-distro/08_iterative_auto_repair.bat`, and `scripts/full-audit-build-distro/08_iterative_auto_repair.bat` (Windows `cmd.exe` parsed `>=2px` as stdout redirection `> 2px`).
- **Paired Delimiter & Mirror Glyph Asymmetry (`(`, `)`, `[`, `]`, `{`, `}`, `<`, `>`, `/`, `\`, Arrows)**:
  - Replaced the asymmetric `cv2.resize(..., INTER_NEAREST)` `base_cand_iou >= 0.62` gate in `humid1_bilevel_tuner.py` with a **Symmetric Dilated-Skeleton Containment Gate** (`Precision >= 0.85`, `Recall >= 0.84`) so `1px -> 2px` curve thickenings on right-heavy `)`, `]`, `}` are never rejected.
  - Added **Bilateral Mirror-Pair Synchronization (`synchronize_mirror_glyph_pairs()`)** across all upright and italic strikes so `(` <-> `)`, `[` <-> `]`, `{` <-> `}`, `<` <-> `>`, `«` <-> `»`, `‹` <-> `›`, `≤` <-> `≥`, `/` <-> `\`, `←` <-> `→`, and `↑` <-> `↓` are 100% symmetric in dimensions, stem thickness, and pixel silhouette.
- **`$` (`U+0024`) Central Vertical Spine & `1px` Vertical Bars (`|`, `!`)**:
  - Added **Method M8 (`synth_m8_central_spine_expansion`)** to duplicate `1px` interior vertical spines (`c = w // 2`) in `$`, `+`, `±`, `¢`, `¥`, `Φ`, `Ψ` to `2px` (`##.##.##`) while aligning `1px` top/bottom spine tips and keeping both internal counters open (`B1 = 2`).
  - Enabled `w0 == 1` vertical bar auto-flooring (`|` `U+007C` `1x16 -> 2x16`, `!` `U+0021` `1x12 -> 2x12`) and made `_apply_counter_punch()` non-destructive when internal counters are already open (`open_px > 0`).

### Added
- **Anisotropic `ExtraBold (wght=800)` Static TTF Synthesis & 3-Tier Weight Hierarchy**:
  - Upgraded `tools/fonts/build_static_ttf_assets.py` (now generating **88 static `.ttf` files**) to synthesize `IBMPlexSans-ExtraBold.ttf`, `IBMPlexSans-ExtraBoldItalic.ttf`, `IBMPlexSansCondensed-ExtraBold.ttf`, `IBMPlexSansCondensed-ExtraBoldItalic.ttf`, `IBMPlexMono-ExtraBold.ttf`, `IBMPlexMono-ExtraBoldItalic.ttf`, `IBMPlexSerif-ExtraBold.ttf`, and `IBMPlexSerif-ExtraBoldItalic.ttf` via anisotropic `gvar` positive-weight delta extrapolation (`1.45x` horizontal stem weight, `1.18x` vertical bar weight).
  - Mapped `bold -> ExtraBold (800)` when `normal = Medium (500)`, restoring a `+31.1%` to `+48.3%` ink-mass separation (`mean stem 3.11px` vs `2.26px` at `16px`) between `normal`, `bold`, and `italic`.
- **Multi-Font & Weight Multi-Method Evaluation Evaluator (`tools/fonts/humid1_font_eval.py` & `scripts/font-eval-suite/01_run_font_eval.bat`)**:
  - Benchmarks candidate typefaces and weights across `10px–20px`, estimates raw vs. multi-method evaluation-tuned pixel size floors, writes `docs/audits/FONT_EVAL_BENCHMARK_v1.0.12.md`, and renders `build/font_eval/font_eval_comparison_sheet.png`.
- **Modularized Foundry Architecture (`tools/fonts/`)**:
  - Extracted `humid1_ft_raster.py`, `humid1_ascii_patches.py`, `humid1_visual_check.py`, and `humid1_lvgl_bdf_export.py` from `humid1_generate_1bpp.py`, reducing `humid1_generate_1bpp.py` from `4,309` lines to `1,426` lines while preserving 100% CLI and import compatibility.

## [v1.0.11] — 2026-11-04
### Added
- **8-Method Iterative Typographic Correction, Scoring & Evaluation Engine (`tools/fonts/humid1_bilevel_tuner.py`, `SPEC-TYPO-MATH-1BPP-001`)**:
  - Evaluates 8 distinct mathematical synthesis & repair methods per glyph (`M0_untouched`, `M1_phase` sub-pixel phase/threshold sweep, `M2_line_tracer` medial-axis centerline + asymmetric $\begin{bmatrix}1 & 1\end{bmatrix}$ stroke kernel, `M3_sdf` signed distance field zero-level-set perturbation, `M4_hysteresis_inktrap` dual-threshold hysteresis + $\text{LoG}$ acute ink-trap opening, `M5_collinear` whole-stem collinear dilation + Jenson-Garamond counter-contrast gain, `M6_diagonal_rectified` rational slant rectifier, and `M7_mumford_shah_clean` total-variation spur/notch cleaner).
  - Scores every candidate out of `100.0` points against both an **$8\times$ HQ Continuous Master Reference ($U_{\text{HQ}}$)** and a **Smallest-Strike ($12\text{px}$) Nth-Factor Upscale Reference ($U_{\text{base}\times N}$)** with hard gates on Euler-Poincaré Betti numbers ($B_0, B_1$), HQ Structural IOU ($\ge 0.66$), and zero skin tags / zero notches.
- **Prominent `PATCHED OVERRIDES ACTIVE: N / Total GLYPHS` Banner Badge in Page Check PNGs (`03_visual_check_pngs.bat`)**:
  - Every `inspect_pages/<symbol>.png` sheet now displays `PATCHED: N/Total` in the title bar and an emerald-green status pill in the top-right corner alongside green-bordered patched glyph cells.

### Fixed
- **Eliminated 1px "Skin Tags" & Vertical Stem Step Notches (`sans_italic_12` `'M'`, `serif_normal_18` `'N'`, `terminus_normal_12` `'$'`)**:
  - Added `detect_skin_tags_and_notches()` and `clean_skin_tags_and_notches()` enforcing Mumford-Shah Total-Variation boundary smoothness and strict Euler $B_0/B_1$ conservation, and excluded hand-drawn pixel fonts (`terminus`) from morphological auto-dilation.
- **Unified ASCII-Centric Repair & Patch Workflow (`01 -> 04 -> 08 -> 05 -> 02 -> 03 -> 07`)**:
  - `08_iterative_auto_repair.bat` now writes tuned glyphs directly into `build/<target>/ascii_patches/<symbol>/U+XXXX.txt` with `patched: 1` (preserving baseline `orig_signature`) and compiles all **1,818 verified patches** into `font_icon_epd_patches.json` so running `04 -> 08 -> 05 -> 02 -> 03` (or `99_run_full_pipeline.bat`) immediately reflects all patches in the `.c` files and PNG banners.
  - Updated `docs/HOW_TO_GUIDE.md`, `README.md`, `scripts/README.md`, and `docs/MAINTAINER_SPEC.md` with complete workflow diagrams and step-by-step instructions for `08_iterative_auto_repair.bat`.

## [v1.0.10] — 2026-11-04
### Added
- **Closed-Loop Iterative Bi-Level Font & Icon Auto-Repair Engine (`tools/fonts/humid1_bilevel_tuner.py` & `--workflow repair`)**:
  - Added 4 deterministic OpenCV/NumPy repair engines (`hybrid`, `autofloor`, `downscale`, `contour`) enforcing a `>= 2px` minimum stem floor (`--min-stem 2`) with collinear outward stem dilation, exterior flood-fill counter protection, hit-or-miss acute corner thinning, and a strict hole-count non-degradation guard.
  - Added `08_iterative_auto_repair.bat` across `scripts/h1os-build-distro/`, `scripts/example-build-distro/`, and `scripts/full-audit-build-distro/`, generating visual Before/After repair sheets in `<out-dir>/inspect_repairs/*_repair.png`.
- **Complete LVGL `LV_SYMBOL_*` & Font Awesome 7 Brands Merging (`0xF287` USB, `0xF293`/`0xF294` Bluetooth, `0xF8A2` New-Line)**:
  - `rasterize_font_strike()` now automatically queries `FontAwesome7-Brands.ttf` and `FontAwesome7-Regular.ttf` when rasterizing `icon_fa7` (`solid`) and synthesizes a crisp 1-BPP return-arrow (`↵`) for `0xF8A2` (`LV_SYMBOL_NEW_LINE`), bringing every `humid1_icon_fa7_solid_*` strike (`12, 14, 16, 18, 20, 24, 32 px`) to **87 icons**.
- **Complete Greek, Scientific, Arrow & Math Coverage Across `mono`, `cond`, `serif`, and `terminus`**:
  - Added homoglyph equivalence mapping (`Δ <-> ∆`, `Ω <-> Ω`, `μ <-> µ`, `− <-> -`) and secondary-face fallback (`IBMPlexMath-Regular.ttf` / `IBMPlexSans-Medium.ttf`) centered on monospace cell width so all text strikes contain **131 glyphs** (`ascii_printable` + `latin1_units` + `greek_scientific` + `arrows_punctuation`).

### Changed
- **Upgraded Default `normal_weight` from `400` (`Regular`) to `500` (`Medium`)**:
  - Resolves physical 188.3-DPI SSD1681 e-Paper hairline stem washout by expanding `14px+` vertical stems to solid `2px` (`0.27 mm`) strokes while preserving open counters and passing all 5 H1OS `188px` screen width budgets.

### Fixed
- **Drop-In Ready `H1OS` Header & Include Compatibility (`humid1_fonts.h`, `plex_fonts.h`, `epd_fonts.h`, `h1os_fonts.h`)**:
  - Added `#if __has_include("lvgl.h")` auto-detection, `struct _lv_font_t` forward declaration, and `#ifndef LV_FONT_DECLARE` fallback macro at the top of all 4 headers so inclusion from inside `lv_conf.h` (`LV_FONT_CUSTOM_INCLUDE`) compiles with zero warnings or errors.
  - Fixed duplicate file body concatenation in `humid1_fonts.h` and unified `HUMID1_FONT_*`, `PLEX_FONT_*`, `HUMID1_ICON_*`, and `H1OS_FONT_*` role macros across all headers.
- **Full Multi-Hop LVGL `.fallback` Chaining**:
  - Linked `sans_normal_* -> humid1_icon_fa7_solid_*` and `sans_bold_* -> sans_normal_* -> humid1_icon_fa7_solid_*` (plus `mono`, `cond`, `serif`, `math`, `terminus`) with smart fallback symbol resolution so compound strings (`LV_SYMBOL_TINT " %.1f%%"`) render icons and text from a single font pointer.

## [v1.0.9] — 2026-11-03
### Fixed
- **Specimen Sheet (`humid1_epd_specimen_188dpi.png`) Full Symbol & Icon Resolution**:
  - Updated `render_specimen_sheet()` in `tools/fonts/humid1_generate_1bpp.py` to resolve all `humid1_font_plex_*`, `humid1_font_terminus_*`, and `humid1_icon_*` symbols through `_resolve_sym()` with an automatic PUA icon fallback table (`icon_fb_14`, `icon_fb_20`), restoring the Bottom-Left 6× zoomed micro-glyph boxes (`@`, `%`, `e`, `a`, `0`, `A`), the Bottom-Left 14-icon strip, the Top-Left simulated 200×200 panel icons, and all 17 rows of the Right-Column size ladder.
- **Complete Character & Icon Diagnostic PNG Generation (`inspect_chars/`)**:
  - Changed the default `--inspect-chars-filter` from `"trouble"` (which only exported 29 trouble characters for text fonts like `terminus` and only the first 12 icons for icon strikes like `humid1_icon_tabler_regular_40`) to `"all"` across `tools/fonts/humid1_generate_1bpp.py` and all `03_visual_check_pngs.bat` scripts. Every strike now renders 100% of its character or icon inventory in `inspect_chars/<symbol>/`, matching `ascii_patches/<symbol>/` 1-for-1.
  - Added per-worker in-memory UI font caching (`_UI_FONTS_CACHE`) so rendering full `inspect_chars/` sets across all strikes executes up to 10× faster.

### Added
- **Automated Firmware Flash & Disk Size Report (`total_disk_size.txt`)**:
  - Added `write_total_disk_size_report()` to `tools/fonts/humid1_generate_1bpp.py`, automatically writing `total_disk_size.txt` to `<out-dir>/fonts/total_disk_size.txt`, `<out-dir>/total_disk_size.txt`, and `<dist-dir>/total_disk_size.txt` whenever `.c` font assets are built or exported.
  - Details exact MCU Flash `.rodata` bytes/KB (`bitmap[] + glyphs[] + kern[] + struct`), host `.c`/`.h` source file bytes/KB, MCU Flash partition utilization (`64KB` to `8MB`), per-family subtotals, and per-strike metrics (`Em(px)`, `pt@96`, `pt@DPI`, `LineHt`).
- **Explicit Point Size (`pt@96dpi` and `pt@188dpi`) vs. Pixel Size (`px` / `ppem`) Telemetry**:
  - Added `px_to_pt_96dpi()`, `px_to_pt_target_dpi()`, and `format_px_pt_summary()` helpers and surfaced dual point/pixel sizing (`Em: Npx / Xpt@96dpi / Ypt@188dpi | LineBox: Mpx`) across all diagnostic page sheets, individual character PNGs, CLI logs, and `total_disk_size.txt`.
  - Added `22px` (`16.5pt@96dpi`) across all vector and icon strikes in `scripts/full-audit-distro/full_audit_distro.scheme.json` for a continuous `+2px` (`1.5pt@96dpi`) progression (`12, 14, 16, 18, 20, 22, 24, 28, 32, 36, 40 px`).
- **Native GNU Unifont (`unifont-18.0.01.otf`) Support**:
  - Added `"family": "unifont"` (`exact-mono`, `16px` minimum floor) to `humid1_generate_1bpp.py` and `build_static_ttf_assets.py` for optional range-subsetted Unicode symbol/fallback strikes at `16px` and `32px`.

## [v1.0.8] — 2026-11-03 (22 Native Terminus TTF Strikes, Multi-Core Parallelism, Tabler Filled Fix & `humid1_` Naming Overhaul)

### Fixed
- **Eliminated Terminus 18–40pt Horizontal White Scanline Gaps & 12–14pt Downscaling Blur**:
  - **Root Cause 1**: In `v1.0.7`, only `ter-u16n.bdf` and `ter-u16b.bdf` were converted to `.ttf`, forcing 12–14pt and 18–40pt strikes to scale from the 16px grid instead of using Terminus's native hand-drawn BDF strikes (`ter-u12n/b.bdf`, `ter-u14n/b.bdf`, `ter-u18n/b.bdf`, `ter-u20n/b.bdf`, `ter-u22n/b.bdf`, `ter-u24n/b.bdf`, `ter-u28n/b.bdf`, `ter-u32n/b.bdf`).
  - **Root Cause 2**: Each horizontal pixel row in `convert_bdf_to_quadratic_ttf()` was emitted as a separate rectangle contour (`[y_bot, y_top]`), and `bytecode-mono` omitted `FT_LOAD_NO_HINTING` (`0x2`), causing FreeType's Auto-Hinter (`autofit`) to snap and separate shared horizontal edges between adjacent pixel rows (creating CRT-like horizontal white scanlines across 18, 20, 24, 28, 36, and 40pt).
  - **Fix**:
    1. Hosted all 20 Terminus `.bdf` master files + `OFL.TXT` directly in `assets/font_assets/terminus_v4.49.1/` (removing the redundant `.tar.gz` archive).
    2. Built **24 individual Terminus `.ttf` files** in `build/static_ttfs/`: 22 size-specific Normal & Bold strikes (`Terminus-Normal-{12,14,16,18,20,22,24,28,32,36,40}.ttf` and `Terminus-Bold-{12,14,16,18,20,22,24,28,32,36,40}.ttf`, where `36` is an exact 2× integer strike of `18` and `40` is an exact 2× integer strike of `20`) plus `Terminus-VGA-14.ttf` and `Terminus-VGA-16.ttf`.
    3. Rewrote `convert_bdf_to_quadratic_ttf()` with a **2D connected rectilinear polygon contour tracer** where shared internal horizontal and vertical edges between adjacent ON pixels cancel out 100%, leaving zero internal seam lines.
    4. Added `exact-mono` (`FT_LOAD_RENDER | FT_LOAD_NO_HINTING | FT_LOAD_TARGET_MONO | FT_LOAD_MONOCHROME`) for Terminus in `humid1_generate_1bpp.py` so FreeType never runs its Auto-Hinter on pixel-grid Terminus strikes.
- **Fixed `humid1_icon_tabler_filled_12..40` Producing Empty PNGs and Empty ASCII Folders**:
  - **Root Cause**: `Tabler-Filled.ttf` (`1,054` filled icons at `0xEE80..0xFA6D`) has zero codepoint overlap with `Tabler-Regular.ttf` (`5,203` outline icons at `0xEA02..`). Previously, `tabler` `filled` strikes referenced `tabler_core` (`0xEA02..`), matching 0 glyphs in `Tabler-Filled.ttf`.
  - **Fix**: Added dedicated `icon_tabler_filled` catalog (`build/metadata/tabler_filled_catalog.json`), added `tabler_filled_core` and `tabler_filled_all` character sets, and routed `icon_tabler` `style="filled"` strikes to `icon_tabler_filled`. Verified `humid1_icon_tabler_filled_12..40` now rasterizes all `1,051` filled glyphs, dumps all `1,051` ASCII `.txt` files, and renders 5 paginated Page Check PNGs per strike.
- **Fixed `KeyError: 'plex_mono_bold_14'` in `render_specimen_sheet` on `example.scheme.json`**:
  - Added `_resolve_sym()` fallback resolution in `render_specimen_sheet` and `run_screen_width_audit` so schemes that build a subset of strikes (like `example.scheme.json`) never fail with `KeyError`.
- **Fixed Windows `.bat` `echo` Command-Breaking Strings**:
  - Removed all unescaped `&`, `(`, `)`, `<`, `>`, and `|` characters inside `echo` lines across every `.bat` file in `scripts/*/` so `cmd.exe` never misinterprets words after `&` (such as `'humid1-os'` or `'Char'`) as shell commands.

### Added
- **Multi-Core Host CPU Parallelism (`ProcessPoolExecutor` Across All Cores)**:
  - Upgraded both `build_static_ttf_assets.py` and `humid1_generate_1bpp.py` to execute font instantiation, BDF/OTF-to-TTF synthesis, FreeType strike rasterization, LVGL `.c` emission, ASCII `.txt` dumping, and PNG rendering concurrently across all host CPU cores (`os.cpu_count()`, configurable via `-j` / `--jobs`).
- **Paginated Full-Catalog Icon Audit PNGs (`MAX_GLYPHS_PER_PNG_PAGE = 256`)**:
  - Updated `full_audit_distro.scheme.json` to include **all** valid icons across all 4 vendors (`2,349` FA v7.3.1, `2,043` Lucide, `1,513` Phosphor, `5,203` Tabler Outline, `1,054` Tabler Filled) and updated `render_full_font_inspection_png()` to automatically split large strikes into clean 256-glyph pages (`<symbol>_p01_of_05_U+EE80-U+F788.png`, etc.).

### Changed
- **Unified `humid1_` Naming Convention Across Scripts, Symbols, Vault, Headers & Patch Manifest**:
  - Renamed `generate_plex_1bpp.py` $
ightarrow$ **`tools/fonts/humid1_generate_1bpp.py`**.
  - Renamed `plex_fw_emit.py` $
ightarrow$ **`tools/fonts/humid1_fw_emit.py`**.
  - Renamed `plex_epd_vault.json.gz` $
ightarrow$ **`humid1_epd_vault.json.gz`**.
  - Consolidated patch manifests into a single root-tracked **`font_icon_epd_patches.json`** (removed duplicate `epd_font_patches.json` and `tools/fonts/plex_epd_patches.json`).
  - Standardized all generated strike symbols and folder names under the `humid1_` prefix:
    - IBM Plex fonts: `humid1_font_plex_<family>_<style>_<size>` (e.g., `humid1_font_plex_cond_normal_12`)
    - Terminus fonts: `humid1_font_terminus_<style>_<size>` (e.g., `humid1_font_terminus_normal_40`)
    - Modular icons: `humid1_icon_<vendor>_<style>_<size>` (e.g., `humid1_icon_fa7_regular_12`, `humid1_icon_tabler_filled_36`)
  - Removed redundant `scripts/full-audit-build-dev/` directory in favor of `scripts/full-audit-build-distro/`.
  - Preserved Font Awesome **v7.3.1** (`assets/icon_assets/font_awsome_v7.3.1`).

---

## [v1.0.7] — 2026-11-03 (Audit Remediation, General-Purpose Overhaul, Terminus TTF & Agent-First Suite)

### Fixed
- **Resolved `plex_icon_phosphor_fill_20` Empty `U+0069_i.txt` Bug**:
  - Identified that upstream `Phosphor*.ttf` binaries include 30 empty (`0×0` bounding box, `0` advance width) ASCII ligature anchor glyphs (`0x0020..0x007A`, including `0x0069 'i'`) in their `cmap`, and that missing `assets/icon_assets/phosphor_icons_v2.1.0/metadata/selection.json` caused semantic name lookups in `"icons"` to return empty and fall back to `RANGE_UI_STR` (`0x0020-0x007E`).
  - Restored `metadata/selection.json` across `assets/icon_assets/phosphor_icons_v2.1.0/metadata/` (and all icon asset metadata folders).
  - Updated `sanitize_and_unwrap_ttf()` in `build_static_ttf_assets.py` (`strip_non_pua=True`) to strip all `cp < 0xE000` ASCII ligature anchor stubs from `Phosphor-*.ttf` and embed all `1,513` semantic glyph names (`"alarm"`, `"wifi-high"`, `"battery-full"`, etc.) directly into `Phosphor-Regular.ttf`, `Phosphor-Bold.ttf`, `Phosphor-Fill.ttf`, `Phosphor-Light.ttf`, and `Phosphor-Thin.ttf`.
  - Hardened `load_plan_from_scheme_json()` and `rasterize_font_strike()` in `generate_plex_1bpp.py` so `icon_*` families never fall back to `RANGE_UI_STR` and automatically reject `0×0` non-space stubs.

### Added
- **Terminus Font v4.49.1 Native `.ttf` Synthesis (`Terminus-Regular.ttf` & `Terminus-Bold.ttf`)**:
  - Added `convert_bdf_to_quadratic_ttf()` to `build_static_ttf_assets.py`, automatically extracting `assets/font_assets/terminus-font-4.49.1.tar.gz` (`ter-u16n.bdf` and `ter-u16b.bdf`) and synthesizing standards-compliant `1024-UPEM` quadratic TrueType fonts (`Terminus-Regular.ttf` and `Terminus-Bold.ttf`, `1,356` Unicode glyphs each) plus `build/metadata/terminus_catalog.json` and `Terminus_OFL.txt`.
  - Added `"family": "terminus"` (rendered with crisp unhinted `bytecode-mono` pixel accuracy) and `"ttf_file"` custom font support to `generate_plex_1bpp.py`.
- **Agent-First Tooling Suite (`tools/agent/{tools,skills,rules}`)**:
  - Created `tools/agent/tools/char_info.py` (exact glyph metrics, bounding box, UTF-8 C literal, and 1:1 ASCII bitmap lookup).
  - Created `tools/agent/tools/string_info.py` (exact LVGL `fp4` kerning-aware string pixel width and screen budget clearance calculator).
  - Created `tools/agent/tools/icon_search.py` (keyword search across 12,209 icons in FA7, Lucide, Phosphor, and Tabler with ready-to-paste C macros and JSON snippets).
  - Created `tools/agent/tools/font_catalog_info.py` (complete inventory of static TTFs, catalogs, and schemes).
  - Added 4 concise agent skills (`tools/agent/skills/*/SKILL.md`) and `tools/agent/rules/AGENT_TYPOGRAPHY_RULES.md`.
- **16 Curated General-Purpose Schemes (`tools/fonts/schemes/*.scheme.json`)**:
  - Added 16 domain-tailored schemes covering `humid1_reference`, `ui_balanced`, `minimal_mcu_32kb`, `telemetry_tabular_mono`, `terminus_retro_terminal`, `condensed_narrow_hmi`, `ereader_editorial_serif`, `scientific_math_lab`, `weather_station_epd`, `smart_home_thermostat`, `wearable_watch_200x200`, `industrial_scada_plc`, and 4 standalone icon vendor packs.
- **4 Self-Contained Workflow Batch Directories (`scripts/*`)**:
  - Populated `scripts/full-audit-build-dev/`, `scripts/full-audit-build-distro/`, `scripts/h1os-build-distro/`, and `scripts/example-build-distro/` with dedicated `.scheme.json` files and `00`–`99` `.bat` pipelines.

### Changed
- **Strict `build/` vs `dist/` Isolation & Root Patch Manifest (`epd_font_patches.json`)**:
  - Moved all generated `static_ttfs` (`build/static_ttfs/`), `metadata` (`build/metadata/`), and `ascii_patches` (`build/<workflow>/ascii_patches/`) strictly inside `build/`.
  - Established root-tracked `epd_font_patches.json` so hand-tuned pixel patches remain version-controlled in Git while `build/` and `dist/` remain gitignored.
- **General-Purpose Humiditron / Humidyne Labs Branding & MIT License**:
  - Licensed the `epd-font` repository under the **MIT License** (`LICENSE`).
  - Removed hardcoded `H1OS` / `200x200 SSD1681` assumptions from the Python scripts; made `--dpi`, `--screen-width`, `--screen-height`, and `--safe-margin` configurable via CLI flags and scheme JSONs, and moved `h1os_full.scheme.json` & `h1os_lite.scheme.json` into `scripts/h1os-build-distro/`.

# Changelog — `epd-font`

All notable changes to the **[Humidyne-Labs/epd-font](https://github.com/Humidyne-Labs/epd-font)** repository and its **[Humidyne-Labs/H1OS](https://github.com/Humidyne-Labs/H1OS)** deployment bundle are documented in this file.

---

## [`v0.0.6`] / [`v1.0.6`] — 2026-11-03

### Added
- **Runnable Windows Batch Script Suite (`scripts/` Directory)**:
  - Added 9 self-contained Windows `.bat` scripts (`00_setup_env.bat`, `01_build_static_ttfs.bat`, `02_build_h1os_fonts.bat`, `03_visual_check_pngs.bat`, `04_dump_ascii_patches.bat`, `05_apply_ascii_patches.bat`, `06_build_icons_catalog.bat`, `07_package_h1os_deployment.bat`, and `99_run_full_pipeline.bat`) so all build, inspection, patching, and packaging workflows execute in one click without manual CLI entry.
- **Dual-Source Searchable JSON Icon Catalogs (`assets/static_ttfs/metadata/`)**:
  - `build_static_ttf_assets.py` now extracts semantic icon names both from upstream metadata JSONs and directly from the `.ttf`/`.otf` `cmap` and `post` tables (baking Phosphor's 1,512 semantic icon names directly into `Phosphor-*.ttf`), generating `fa7_catalog.json` (`2,396` icons), `lucide_catalog.json` (`2,043` icons), `phosphor_catalog.json` (`1,513` icons), `tabler_catalog.json` (`6,257` icons), `unified_icon_names.json` (`12,209` total mappings), and `asset_manifest.json`.
- **Semantic Icon Name Scoping in Scheme JSONs (`"icons": [...]` & `"scope": "all"`)**:
  - Both `generate_plex_1bpp.py` and `plex_fw_emit.py` now allow `character_sets` in `tools/fonts/schemes/*.json` to specify custom icon subsets using plain English icon names (`"icons": ["wifi", "battery-full", "thermometer", "cpu"]`), hex ranges (`"ranges"`), or `"scope": "all"`.
- **Repository Hygiene & Versioning (`VERSION.json`, `.gitignore`, `LICENSES/`)**:
  - Added `VERSION.json` tracking the repository version (`0.0.6`) alongside exact upstream versions (`math_v1.1.0`, `mono_v1.0.0`, `sans_v0.2.0`, `serif_v2.0.0`, `font_awsome_v7.3.1`, `lucide_icons_v1.67.0`, `phosphor_icons_v2.1.0`, `tabler_icons_v3.50.0`), a root `.gitignore`, and a consolidated `LICENSES/` directory.

### Changed
- **Unified Single-Input (`--src-dir`) and Single-Output (`--out-dir`) CLI Architecture**:
  - Audited and simplified `build_static_ttf_assets.py` and `generate_plex_1bpp.py` so only a single `--src-dir` and a single `--out-dir` are needed (eliminating the dual `--plex-dir` / `--icons-src` / `--font-dir` conflict while retaining hidden backward-compatible aliases).
- **Consolidated Documentation into 4 Canonical Files**:
  - Replaced scattered technical design notes with exactly 4 structured documents: `README.md`, `CHANGELOG.md`, `docs/HOW_TO_GUIDE.md`, and `docs/MAINTAINER_SPEC.md`.

### Fixed
- **Fixed Column-0 `#` Pixel Parsing in `parse_ascii_glyph_folder()`**:
  - Fixed a parser condition where a full-canvas ASCII row whose leftmost pixel at `x=0` was `#` (ink ON, such as the bottom-left foot of `'A'`) had its leading spaces stripped before checking `startswith("#")`, causing that row to be skipped as a comment. Only lines starting with `#` at column 0 (`raw_line.startswith("#")`) or `# x:` / `# ±:` headers are now treated as comments.
- **Fixed Empty Metadata JSON Generation When Upstream `metadata/` Folders Were Omitted**:
  - Restored upstream `metadata/` folders under `assets/icon_assets/` and added direct font `cmap` table extraction so JSON catalogs are never empty.

---

## [`v0.0.5`] — 2026-11-03

### Added
- **Repository Restructuring (`epd-font`)**:
  - Standardized raw upstream directory layout under `assets/font_assets/ibm-plex-font/` (`math_v1.1.0`, `mono_v1.0.0`, `sans_v0.2.0`, `serif_v2.0.0`) and `assets/icon_assets/` (`font_awsome_v7.3.1`, `lucide_icons_v1.67.0`, `phosphor_icons_v2.1.0`, `tabler_icons_v3.50.0`).
- **Standalone Host Raw-to-Static Converter (`build_static_ttf_assets.py`)**:
  - Added host script to instantiate 41 static [IBM Plex](https://github.com/IBM/plex) `.ttf` files and convert/normalize 13 icon `.ttf` files (`FontAwesome7-Solid.ttf`, `Regular.ttf`, `Brands.ttf`, `Lucide-Regular.ttf`, `Phosphor-*.ttf`, `Tabler-*.ttf`).

---

## [`v0.0.4`] — 2026-11-02

### Added
- **Modular Multi-Vendor Icon Strikes (`icon_fa7`, `icon_lucide`, `icon_phosphor`, `icon_tabler`)**:
  - Decoupled icon fonts from IBM Plex text strikes (`plex_sans_*`, `plex_cond_*`), compiling each icon vendor as its own standalone `lv_font_t` strike with optional LVGL `.fallback` chaining and reducing text strike ROM size by ~39%.
- **Exact 5-Space Column Alignment in Full-Canvas ASCII Files**:
  - Matched the 5-character `# x: 0 1 2 3 4 5` header prefix with a 5-space row indentation (`"     "`) and removed the default `UNICODE 1:1 SILHOUETTE PREVIEW` block (moved behind opt-in `--unicode-preview`).

---

## [`v0.0.3`] — 2026-11-02

### Added
- **Full-Canvas 1:1 Spaced ASCII Patch Format & Auto-Bounding-Box Parser**:
  - Plotted every glyph across its full vertical (`ASCENDER` to `DESCENDER`) and horizontal (`adv_w`) canvas using 2-character cells (`# `, `. `, `- `) so monospace editors display a true 1:1 aspect ratio and show exact baseline positioning for underscores (`_`), periods (`.`), and degrees (`°`).
- **Two-Level Visual Check PNG Suite (`inspect_pages/` & `inspect_chars/`)**:
  - Added auto-wrapping specimen strings on Page Check PNGs and 18×–24× integer-zoom Char-by-Char Technical Design Blueprint PNG cards.
- **Portable Zero-Dependency Firmware Emitter (`plex_fw_emit.py` & `plex_epd_vault.json.gz`)**:
  - Split heavy desktop foundry operations (`generate_plex_1bpp.py`) from fast, zero-dependency CMake firmware emission (`plex_fw_emit.py`).

---

## [`v0.0.2`] — 2026-11-02

### Fixed
- **Native FreeType 1-Bit Monochrome Rasterization (`FT_LOAD_TARGET_MONO`)**:
  - Switched from 8-bit grayscale thresholding to FreeType 2's native 1-bit scanline converter (`FT_LOAD_RENDER | FT_LOAD_FORCE_AUTOHINT | FT_LOAD_TARGET_MONO | FT_LOAD_MONOCHROME`, `0x21024`) and set `Normal` weight to `Regular (400)` (`1 px` stems) vs. `Bold (700)` (`2 px` stems).

---

## [`v0.0.1`] — 2026-11-01

### Added
- Initial prototype of LVGL v9 1-bpp font generator, Adobe BDF 2.1 exporter, and 200×200 SSD1681 screen width audit.
