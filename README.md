# `epd-font` (v1.0.23) — A 1-bit EPD Font Generator and Asset Pipeline for Embedded Displays

[![Version](https://img.shields.io/badge/version-v1.0.23-blue.svg)](VERSION.json)
[![Repository](https://img.shields.io/badge/github-Humidyne--Labs%2Fepd--font-181717.svg)](https://github.com/Humidyne-Labs/epd-font)
[![Lead Developer](https://img.shields.io/badge/developer-Humiditron-0A66C2.svg)](https://github.com/humiditron)
[![License](https://img.shields.io/badge/license-MIT%20%2F%20OFL--1.1%20%2F%20ISC-green.svg)](LICENSE)

**`epd-font`** is **A 1-bit EPD font generator and asset pipeline for embedded displays**, designed and developed collaboratively by **[Humiditron](https://github.com/humiditron)** (Humidyne Labs) and the **AI/LLM Collaborative Development Partner** for monochrome Electrophoretic Displays (EPD) such as the Waveshare 1.54" e-Paper V2 (`SSD1681` / `GDEY0154D67`, `200 × 200` pixels @ `188.15 DPI`), OLEDs, Memory LCDs, and LVGL `>= 9.6.0` (LVGL v9+) embedded applications ([public repository](https://github.com/Humidyne-Labs/epd-font)).

## 1. Core Capabilities in v1.0.23

1. **Nine Deterministic Resolution-Reduction (`1-bpp`) Conversion Pipelines + Linear Grayscale & Gamma (`tools/fonts/humid1_bilevel_pipelines.py`)**:
   - **True Linear Grayscale + Optional Gamma**: Converts sRGB or single-channel coverage rasters to ITU-R BT.709 / IEC 61966-2-1 linear luminance ($Y_{\text{lin}} = 0.2126 R_{\text{lin}} + 0.7152 G_{\text{lin}} + 0.0722 B_{\text{lin}}$) with configurable gamma adjustment (`raster_config.gamma`, default `1.0`) and an L1-cached 256-entry `uint8` LUT for `gamma == 1.0`.
   - **`raw-unhinted`**: Direct unhinted FreeType `8-bit` linear grayscale rasterization (`FT_LOAD_NO_HINTING`) + configurable binary threshold (`raster_config.threshold`, default `128`).
   - **`raw-hinted`**: Grid-fitted hinted FreeType linear grayscale rasterization (`FT_LOAD_TARGET_NORMAL` / `FT_LOAD_FORCE_AUTOHINT`) + configurable binary threshold (`raster_config.threshold`, default `128`).
   - **`svg-potrace`**: High-resolution (`10x`) anti-aliased rasterization -> binary threshold -> hierarchical `cv2.RETR_TREE` Potrace B-spline / cubic Bézier vector contour tracing (`.svg`) -> `+0.5 px` half-pixel center alignment -> non-antialiased (`LINE_8` topological tree-depth fill) low-resolution re-rasterization ([Potrace Vector Tracing](https://potrace.sourceforge.net/)).
   - **`svg-potrace-jfa`**: Sub-mode of `svg-potrace` (`jfa-marching`) executing 3D NDRange Jump Flooding (`1+JFA`) + 2x2 Marching Squares sub-pixel zero-crossing contour extraction fused with hierarchical `RETR_TREE` Potrace vector topology.
   - **`mdf`**: High-resolution (`12x`) super-sampling with median filtering + directional morphological Signed Distance Field (`SDF`) -> pixel-center downsampling.
   - **`msdf`**: True Multi-Channel Signed Distance Field (`12x` super-sampling -> 3-channel $(R, G, B)$ contour edge coloring at sharp corners -> directional signed pseudo-distance -> $\text{median}(R, G, B)$ reconstruction per [Chlumsky/msdfgen](https://github.com/Chlumsky/msdfgen)).
   - **`sdf-smoothstep`**: Supersampled Euclidean Signed Distance Field (`16x`) with $L_2$ screen-space gradient width and analytical Hermite `smoothstep` edge reconstruction ([Red Blob Games SDF Typography](https://www.redblobgames.com/articles/sdf-fonts/)).
   - **`adf-biquadratic`**: Adaptive Distance Field (`ADF`) quadtree subdivision (`12x–16x` -> $4\times 4$ cells) with 9-point biquadratic Lagrange polynomial surface interpolation ($P(u,v)$) for corner and thin-stem preservation.
   - **`otsu-adaptive`**: Linear-luminance global Otsu threshold ($\sigma_B^2(k^*)$) computed via 3D NDRange per-slice local-atomic histograms.
2. **Multi-Device 3D NDRange OpenCL Acceleration, Hybrid Shared GPU Memory & Deterministic Teardown (`tools/fonts/math_backends/`, `tools/fonts/opencl_dispatcher.py`, `tools/fonts/humid1_runtime.py`)**:
   - **Full 3-Dimensional (`work_dim = 3`, `[dim_x, dim_y, dim_z]`) Strike-Batched Kernels**: Packs entire font/icon strikes into `(batch_z, H, W)` 3D tensors and dispatches 3D NDRange OpenCL C kernels (`srgb_to_linear_gamma_3d_kernel`, `jfa_boundary_init_short2_3d_kernel`, `jfa_step_short2_3d_kernel`, `jfa_short2_to_sdf_3d_kernel`, `sdf_valve_smoothstep_3d_kernel`, `msdf_downsample_rgb_3d_kernel`, `msdf_median3_reconstruct_3d_kernel`, `mdf_reconstruct_3d_kernel`, `adf_biquadratic_9pt_3d_kernel`, `otsu_hist_batch_3d_kernel`) across all Compute Units (`32` CUs GPU + `12` CUs CPU).
   - **4-Queue Hardware Compute Striping (`Compute 0..3`)**: Stripes chunked 3D batch dispatches across `4` independent `cl.CommandQueue` instances with queue-drained buffer lifecycle management.
   - **Hybrid WDDM Shared GPU Memory Staging + Bounded VRAM Hot-Scratch (`SharedHostMemoryArena`)**: Stages host inputs/outputs in `CL_MEM_ALLOC_HOST_PTR` WDDM Shared GPU Memory (capped at 75% of total Shared GPU Memory, configurable via `EPD_FONT_SHARED_RAM_MB`) using OpenCL-spec-compliant `cl.enqueue_map_buffer` -> copy -> unmap, while placing device-side hot scratch in bounded Dedicated VRAM (`EPD_FONT_SHARED_MODE=auto`) with automatic overflow to Shared GPU Memory for giant batches (or 100% Shared GPU Memory when `EPD_FONT_SHARED_MODE=shared`).
   - **Single-Owner GPU + Multi-Core CPU Work-Stealing Pool (`opencl_dispatcher.py` & `humid1_runtime.py`)**: Spawns `1` persistent GPU worker (`EPD_FONT_WORKER_ROLE="gpu"`, feeding heavy icon catalogs and distance-field strikes from the front of the work deque) alongside `N-1` CPU workers (`EPD_FONT_WORKER_ROLE="cpu"`, feeding `Terminus` BDF and small text strikes from the back of the work deque). Prevents multi-process GPU context thrashing and eliminates VRAM multiplication.
   - **Deterministic Memory Teardown & Clean `Ctrl+C` (`SIGINT`) Handling**: Drains all queues, calls `.release()` on every `cl.Buffer`, drops all kernel/program/queue/context references, runs `gc.collect()` on exit, and sets `SIGINT=SIG_IGN` in child worker initializers so pressing `Ctrl+C` stops workers immediately with **zero traceback spam** and **0 MB of retained GPU/host memory**.
3. **Strict `char_debug` & `sheet_debug` Boolean Gating + `'all'` / `'all-debug'` Multi-Method Comparison**:
   - Individual character blueprint cards (`inspect_chars/`) and strike character map sheets (`inspect_pages/`) are strictly gated off when `"char_debug": false` and `"sheet_debug": false` in `.scheme.json`.
   - Setting `"pipeline": "all"` (or `"all-debug"`) in `.scheme.json` executes all 9 conversion methods and dumps every method's sheet (`inspect_pages/<method>/<symbol>.png`), per-method `master_char_icon_map.png`, and comparison sheets (`inspect_pages/compare_methods/<font_stem>_<lo>px_<hi>px.png`, or `<font_stem>_<sz>px.png` for single-size families).
4. **Hardware Scheme Files (`esp32s3-N8R8-hw_scheme.json`, `generic_hw.json`), `188.15 DPI` Calibration & Strict `3 MByte` Partition Validation**:
   - Calibrated to the exact physical pixel density of the Waveshare 1.54" e-Paper V2 (`200 × 200` pixels across `27.00 mm × 27.00 mm`, `0.135 mm` pixel pitch -> `188.15 DPI`).
   - Supports only the single `3 MByte` (`3,145,728` bytes) hardware partition constraint in `rom_space_estimate.txt` and `total_disk_size.txt`, with **zero hardcoded fallback defaults**.
5. **Closed-Loop Manual ASCII Patching, CSV Metric Manifests & LVGL `>= 9.6.0` ESP-IDF CMake Integration**:
   - Includes `humid1_cmake_font_builder.py`, `humid1_fw_emit.py`, `cmake/epd_font_esp_idf.cmake`, and `humid1_package_distro.py` for zero-dependency ESP-IDF CMake builds, per-strike metric CSVs (`metrics/*.csv` for `epd_typography.py` / `embedded-ops` MCP & DuckDB), and portable versioned `.zip` distribution bundles (`dist/epd-font_<workflow>_v1.0.23.zip`).

## 2. Detailed Installation, OpenCL Runtime Libraries & Setup Guide

### 2.1 System Prerequisites

| Prerequisite | Requirement / Version | Notes & Platform Details |
| :--- | :--- | :--- |
| **Operating System** | **Windows 10 / 11 (x64)** or **Linux (x86_64 / ARM64)** | Windows is the primary one-click `.bat` host; Linux is fully supported via CLI/CMake. *(Apple OS is not supported.)* |
| **Python Runtime** | **Python `3.9` or newer** (`3.10`–`3.14` supported) | Download from [python.org/downloads](https://www.python.org/downloads/). On Windows, check **"Add python.exe to PATH"** in the installer. |
| **pip Package Manager** | **`pip >= 23.0`** (bundled with Python 3.9+) | Verify with `python -m pip --version`. |
| **FreeType 2 Shared Library** | **`libfreetype` (`>= 2.10`)** | Bundled automatically on Windows and Linux when installing `freetype-py>=2.4.0` via `pip`. On Linux, you may also install `libfreetype6` via `apt`/`dnf`. |
| **OpenCL Runtime ICDs *(Optional)*** | **OpenCL `1.2` / `2.0` / `3.0` ICD** ([Khronos OpenCL](https://registry.khronos.org/OpenCL/specs/unified/refpages/man/html/)) | Supports both **GPU OpenCL Runtimes** (AMD Adrenalin `amdocl64.dll`, NVIDIA `nvopencl64.dll`) and **CPU OpenCL Runtimes** ([Intel CPU Runtime for OpenCL Applications](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-cpu-runtime-for-opencl-applications-with-sycl-support.html)). See **Section 2.4** below. |
| **ESP-IDF / CMake *(Optional)*** | **ESP-IDF `v5.x`** & **CMake `>= 3.16`** | Needed only when compiling generated LVGL `>= 9.6.0` `.c`/`.h` font targets into MCU firmware. |

### 2.2 Required & Optional Python Packages

`epd-font` operates in two distinct modes depending on whether you are **generating/auditing font assets** or **emitting C/H files from a pre-compiled Strike Vault during firmware builds**:

1. **Mode A — Downstream Firmware / CMake Vault Emitter (`tools/fonts/humid1_fw_emit.py`)**:
   - **Third-Party Packages Needed**: **None (`0` external packages)**. Uses 100% Python 3 standard library (`json`, `gzip`, `pathlib`, `argparse`, `shutil`, `re`, `signal`) and executes in `< 0.15s`.
2. **Mode B — Full Font Generator, 9-Pipeline Converter, Visual Inspector & Evaluator (`humid1_generate_1bpp.py`, `build_static_ttf_assets.py`, `humid1_font_eval.py`)**:
   - Requires the 5 core packages in `requirements.txt` (plus optional `pyopencl` for 3D NDRange OpenCL GPU/CPU kernel execution):

| Python Package | Minimum Version | Role in `epd-font` Pipeline | Required? |
| :--- | :--- | :--- | :--- |
| [`fonttools`](https://pypi.org/project/fonttools/) | `>= 4.40.0` | Parses `.ttf`/`.otf`/`.ttc` tables (`cmap`, `hmtx`, `head`, `hhea`, `OS/2`, `kern`, `gvar`), synthesizes static cuts, and converts X11 `.bdf` strikes to `.ttf` | **Required** |
| [`Pillow`](https://pypi.org/project/Pillow/) | `>= 10.0.0` | Renders per-strike page check sheets (`inspect_pages/`), multi-method comparison sheets, `188.15 DPI` EPD specimen mockups, and per-character blueprint cards | **Required** |
| [`freetype-py`](https://pypi.org/project/freetype-py/) | `>= 2.4.0` | Provides the cross-platform `freetype.dll` / `libfreetype.so` C binary used by `humid1_ft_raster.py` for hinted, unhinted, and high-resolution glyph rendering | **Required** |
| [`numpy`](https://pypi.org/project/numpy/) | `>= 1.24.0` | Vectorized array math, IEC 61966-2-1 sRGB-to-linear luminance LUTs, Betti number ($B_0, B_1$) topology verification, Otsu histograms, and CPU polynomial solvers | **Required** |
| [`opencv-python`](https://pypi.org/project/opencv-python/) | `>= 4.8.0` | Euclidean distance transforms (`cv2.distanceTransform`), hierarchical `cv2.RETR_TREE` Potrace contour extraction, morphological filtering, and `cv2.UMat` OpenCL acceleration | **Required** |
| [`pyopencl`](https://pypi.org/project/pyopencl/) | `>= 2023.1` | Compiles and dispatches 3D NDRange OpenCL C kernels (`tools/fonts/math_backends/opencl_kernels.py`) on AMD/NVIDIA/Intel GPUs and multi-core x86_64 CPU OpenCL runtimes | *Optional (Auto-fallback to CPU/UMat)* |

### 2.3 Step-by-Step Python & `pip` Installation Guide

#### Option A: One-Click Windows Setup (`.bat` Launcher)
On Windows 10/11 with Python 3.9+ on your `PATH`, double-click or run `00_setup_env.bat` from any workflow folder in `scripts/`:
```cmd
scripts\h1os-build-distro\00_setup_env.bat
```
This script verifies your Python installation, upgrades `pip setuptools wheel`, installs all 5 required packages (`fonttools`, `Pillow`, `freetype-py`, `numpy`, `opencv-python`), and installs `pyopencl` when an OpenCL ICD is present.

#### Option B: Manual Installation via `pip` and `requirements.txt` (Windows PowerShell / CMD)
```powershell
# 1. Open PowerShell or Command Prompt in the epd-font repository root
cd path\to\epd-font

# 2. Verify Python 3.9+ is installed and on PATH
python --version

# 3. (Optional) Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\activate

# 4. Upgrade pip, setuptools, and wheel
python -m pip install --upgrade pip setuptools wheel

# 5. Install all core required packages from requirements.txt
python -m pip install -r requirements.txt

# 6. Install PyOpenCL for 3D NDRange GPU & CPU OpenCL acceleration
python -m pip install "pyopencl>=2023.1"
```

#### Option C: Manual Installation on Linux (`Ubuntu / Debian / Fedora / Arch`)
```bash
# 1. Install Python 3, venv, pip, FreeType, and OpenCL ICD loader packages
sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip libfreetype6 ocl-icd-libopencl1 opencl-headers clinfo

# 2. Create and activate a virtual environment in the epd-font root
python3 -m venv .venv
source .venv/bin/activate

# 3. Upgrade pip and install core dependencies + PyOpenCL
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install -r requirements.txt
python3 -m pip install "pyopencl>=2023.1"
```

### 2.4 Runtime OpenCL Libraries & Drivers Setup Guide (GPU & CPU Runtimes)

To enable `PyOpenCL` hardware acceleration across **both discrete/integrated GPUs and multi-core host CPUs**, your operating system requires at least one **OpenCL Installable Client Driver (ICD)** registered with the Khronos OpenCL ICD Loader (`OpenCL.dll` on Windows / `libOpenCL.so.1` on Linux, per the [Khronos OpenCL 3.0 Unified Specification](https://registry.khronos.org/OpenCL/specs/unified/refpages/man/html/)).

| Target Hardware Device | Runtime OpenCL Library / ICD Package | Platform & Installation Instructions | Typical Device Enumeration in `probe_hardware.py` |
| :--- | :--- | :--- | :--- |
| **Multi-Core x86_64 CPUs (`AMD Ryzen` & `Intel Core / Xeon`)** | **[Intel CPU Runtime for OpenCL Applications with SYCL Support](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-cpu-runtime-for-opencl-applications-with-sycl-support.html)** (`intelocl64.dll` / `libintelocl.so` / `intel-opencl-rt`) | **Windows & Linux**: Download the standalone **Intel CPU Runtime for OpenCL Applications** installer from [Intel Developer Zone](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-cpu-runtime-for-opencl-applications-with-sycl-support.html) (or install via `python -m pip install intel-opencl-rt`). Exposes all logical x86_64 threads on **both AMD Ryzen and Intel CPUs** as an OpenCL `CL_DEVICE_TYPE_CPU` compute target with AVX2 SIMD vectorization. | `[1] Platform 1, Device 0: AMD Ryzen 5 5600G with Radeon Graphics (ALL \| CPU) - 12 CUs` |
| **AMD Discrete & Integrated GPUs (`Polaris / RX 500`, `Vega`, `RDNA`)** | **[AMD Software: Adrenalin Edition](https://www.amd.com/en/support)** (`amdocl64.dll`, `PAL,HSAIL`) / **ROCm OpenCL Runtime** (`rocm-opencl-runtime`) | **Windows**: Included automatically with [AMD Software: Adrenalin Edition](https://www.amd.com/en/support) (`Driver >= 31.0.22923`, OpenCL 2.1 `AMD-APP`).<br>**Linux**: Install `rocm-opencl-runtime` or `mesa-opencl-icd`. | `[0] Platform 0, Device 0: Ellesmere (ALL \| GPU) - 32 CUs` |
| **NVIDIA Discrete GPUs (`GTX / RTX / Quadro`)** | **[NVIDIA OpenCL ICD Runtime](https://developer.nvidia.com/opencl)** (`nvopencl64.dll` / `libnvidia-opencl.so`) | **Windows**: Bundled with standard NVIDIA Game Ready / Studio Drivers.<br>**Linux**: `sudo apt-get install -y nvidia-opencl-icd` | `[0] Platform 0, Device 0: NVIDIA GeForce ... (ALL \| GPU)` |
| **Generic Linux CPU / Fallback OpenCL Runtime** | **[Portable Computing Language (`pocl`)](https://portablecl.org/)** (`pocl-opencl-icd`) | **Linux (`Ubuntu / Debian`)**: `sudo apt-get install -y pocl-opencl-icd ocl-icd-libopencl1 clinfo` | `[0] Platform 0, Device 0: cpu-... (ALL \| CPU)` |

#### Windows OpenCL ICD Registry Verification (Optional Troubleshooting)
On Windows 10/11, registered OpenCL runtimes appear under `HKEY_LOCAL_MACHINE\SOFTWARE\Khronos\OpenCL\Vendors`. You can list all registered `.dll` ICDs in PowerShell with:
```powershell
Get-ItemProperty "HKLM:\SOFTWARE\Khronos\OpenCL\Vendors"
```

### 2.5 Verifying OpenCL Devices, 3D Work-Item Dimensions, Shared RAM & Teardown

*(Note: Recent versions of `PyOpenCL` (`>= 2025.x / 2026.x`) removed the legacy `python -m pyopencl.dump` command. Use the included `scripts/probe_hardware.py` and `scripts/check_PyOpenCL.py` utilities instead.)*

1. **Quick Multi-Device & Shared-RAM Enumeration Probe (`scripts/probe_hardware.py`)**:
   ```powershell
   python scripts/probe_hardware.py
   ```
   Example output on a workstation with an **AMD Radeon RX 570 (`Ellesmere`, 32 CUs)** and **AMD Ryzen 5 5600G (12 CUs via Intel CPU Runtime for OpenCL)**:
   ```text
   [0] Platform 0, Device 0: Ellesmere (ALL | GPU) - 32 CUs | Work-Item Dims: 3D (Active: 3D) | Dedicated: 4096 MB | Shared RAM: 15,700/15,700 MB
   [1] Platform 1, Device 0: AMD Ryzen 5 5600G with Radeon Graphics (ALL | CPU) - 12 CUs | Work-Item Dims: 3D (Active: 3D) | Dedicated: 31400 MB | Shared RAM: 15,700/15,700 MB
   [*] Hybrid Compute Dispatch (108 tasks): GPU=[Ellesmere (32 CUs, 3D NDRange, 4 Queues)] | CPU=[AMD Ryzen 5 5600G with Radeon Graphics (12 CUs), 12 workers] | Shared RAM Pool=15,700/15,700 MB (CL_MEM_ALLOC_HOST_PTR)
   ```

2. **Full 3D NDRange Kernel Parity, WDDM Shared GPU RAM & Deterministic Teardown Check (`scripts/check_PyOpenCL.py`)**:
   ```powershell
   python scripts/check_PyOpenCL.py --stress-shared-mb 2048 --hold-seconds 15
   ```
   Verifies that all `3` Work-Item Dimensions, `4` hardware command queues, batched 3D pipeline parity (`sdf-smoothstep`, `adf-biquadratic`, `mdf`, `msdf`, `svg-potrace-jfa`, `otsu-adaptive`), live `CL_MEM_ALLOC_HOST_PTR` WDDM Shared GPU RAM allocation (`--stress-shared-mb` with optional `--hold-seconds` for Windows Task Manager observation), and deterministic buffer/context teardown (`0 MB` retained post-exit) pass on every installed OpenCL platform.

3. **One-Line FreeType + `math_backends` Verification**:
   ```powershell
   python -c "import sys; sys.path.insert(0, 'tools/fonts'); from humid1_ft_raster import load_freetype; from math_backends import describe_math_backend, teardown_math_backends; load_freetype(); print('FreeType OK |', describe_math_backend()); teardown_math_backends()"
   ```

## 3. Repository Directory Structure (`v1.0.23`)

```text
epd-font/
├── LICENSE                                  # MIT License (Humidyne Labs / Humiditron pipeline & tooling)
├── VERSION.json                             # Release & upstream asset version manifest (v1.0.23)
├── requirements.txt                         # Pip dependency manifest for core & optional GPU packages
├── esp32s3-N8R8-hw_scheme.json              # Root ESP32-S3-N8R8 hardware scheme (188.15 DPI, partition_bytes: 3145728 / 3 MBytes)
├── generic_hw.json                          # Root generic hardware scheme (188.15 DPI, partition_bytes: 3145728 / 3 MBytes)
├── font_icon_epd_patches.json               # Root-tracked manual 1-bpp pixel patch manifest
├── README.md                                # Primary repository overview, OpenCL runtime & setup guide
├── CHANGELOG.md                             # Chronological release history (v0.0.1 -> v1.0.23)
├── docs/
│   ├── HOW_TO_GUIDE.md                      # Complete CLI, scheme, 9-pipeline & ESP-IDF CMake guide
│   └── MAINTAINER_SPEC.md                   # Formal 1-bpp mathematical, 3D OpenCL & pipeline specification
├── scripts/                                 # One-click Windows (.bat) workflows & OpenCL diagnostic tools:
│   ├── check_PyOpenCL.py                    #   - Detailed 3D NDRange, Shared RAM & teardown inspector
│   ├── probe_hardware.py                    #   - Compact multi-platform GPU + CPU OpenCL device probe
│   ├── full-audit-build-distro/             #   1. Complete 10px-40px (step 2px) visual audit & distro
│   ├── h1os-build-distro/                   #   2. H1OS & humid1-os schemes (h1os_full, h1os_lite & 03b 9-method PNGs)
│   ├── example-build-distro/                #   3. General-purpose embedded display project workflow
│   └── font-eval-suite/                     #   4. Multi-font 9-pipeline evaluation suite
├── assets/                                  # Untouched, versioned static upstream font & icon archives
│   ├── font_assets/                         #   - Hinted IBM Plex, Hinted Google Noto v2.013, Terminus v4.49.1
│   └── icon_assets/                         #   - Font Awesome v7.3.1, Lucide v1.67.0, Phosphor v2.1.0, Tabler v3.50.0
├── tools/
│   ├── fonts/
│   │   ├── math_backends/                   # Modular 3D NDRange GPU/CPU math abstraction & dispatcher:
│   │   │   ├── __init__.py                  #   - Unified mathematical dispatch & teardown exports
│   │   │   ├── hw_dispatch.py               #   - Multi-device capability probe, worker-role isolation & router
│   │   │   ├── opencl_kernels.py            #   - 3D NDRange OpenCL kernels + 4 queues + SharedHostMemoryArena (75% Dynamic Cap on Total WDDM Shared GPU Memory via persistent `CL_MEM_ALLOC_HOST_PTR` + `clEnqueueMapBuffer` slots)
│   │   │   ├── umat_math.py                 #   - OpenCV Transparent API (cv2.UMat) OpenCL tier
│   │   │   └── cpu_math.py                  #   - Vectorized NumPy/OpenCV SIMD CPU backend + L1 LUT
│   │   ├── opencl_dispatcher.py             # Heterogeneous GPU + CPU workload coordinator
│   │   ├── humid1_runtime.py                # Dual-pool work-stealing, clean Ctrl-C & deterministic teardown
│   │   ├── humid1_bilevel_pipelines.py      # 9 bilevel pipelines + linear grayscale + gamma
│   │   ├── build_static_ttf_assets.py       # Raw assets -> build/static_ttfs/*.ttf + build/metadata/*.json
│   │   ├── humid1_generate_1bpp.py          # Master pipeline orchestrator (gen-assets, patch, check, build, audit)
│   │   ├── humid1_font_eval.py              # 9-Pipeline per-font, per-size benchmark & visual evaluator
│   │   ├── humid1_fw_emit.py                # Zero-dependency CMake firmware emitter (< 0.15s)
│   │   ├── humid1_cmake_font_builder.py     # ESP-IDF CMake font builder integration script
│   │   ├── humid1_package_distro.py         # Versioned distribution packager (includes metrics/*.csv) & zipper
│   │   ├── cmake/                           # epd_font_esp_idf.cmake & example_CMakeLists.txt
│   │   └── schemes/                         # 16 curated declarative JSON font schemes
│   └── agent/                               # Single-source epd_typography engine + thin CLI wrappers (exposed via embedded-ops MCP)
├── build/                                   # [Gitignored] static_ttfs, metadata, cache, evals, audits, per-scheme outputs
└── dist/                                    # [Gitignored] Versioned portable distribution bundles & .zip archives
```

## 4. Quick Start Workflows

### A. One-Click Windows Batch Workflows (`scripts/*`)
Run `00_setup_env.bat` once to install dependencies, then run `99_run_full_pipeline.bat` inside any workflow folder:
- **General Example Project**: `scripts\example-build-distro\99_run_full_pipeline.bat` -> outputs to `build\example\` and `dist\epd-font_example_v1.0.23.zip`
- **Full 10px–40px (Step 2px) Master Audit**: `scripts\full-audit-build-distro\99_run_full_pipeline.bat` -> outputs to `build\audit\` and `dist\epd-font_audit_v1.0.23.zip`
- **H1OS / `humid1-os` Deployment**: `scripts\h1os-build-distro\99_run_full_pipeline.bat` -> outputs to `build\h1os\` and `dist\epd-font_h1os_v1.0.23.zip` (plus `03b_compare_all_9_methods_pngs.bat` -> `build\h1os_9method_audit\`)

### B. Command-Line Usage (Windows & Linux Python 3)

In `v1.0.23`, `humid1_generate_1bpp.py` reads all rasterization, pipeline, backend, threshold, gamma, and debug settings from `raster_config` inside `--scheme <file.scheme.json>`, keeping the CLI minimal and deterministic:

| Tool / Script | Valid CLI Arguments | Notes |
| :--- | :--- | :--- |
| **`tools/fonts/humid1_generate_1bpp.py`** | `-w/--workflow {gen-assets,patch,check,build,audit,all}`, `-S/--scheme <path>`, `-s/--src-dir <dir>`, `-o/--out-dir/--build-dir <dir>`, `-d/--dist-dir <dir>`, `-a/--ascii-dir <dir>`, `-p/--patches <json>`, `--dump`, `--apply`, `-j/--jobs <N>`, `-v/--verbose` | `--workflow` is required. Raster settings (`pipeline`, `math_backend`, `threshold`, `gamma`, `sheet_debug`, `char_debug`, `debug_stages`) live in `.scheme.json`. Optional env vars: `EPD_FONT_SHARED_MODE=auto\|shared`, `EPD_FONT_SHARED_RAM_MB=<MB>`. |
| **`tools/fonts/humid1_font_eval.py`** | `--src-dir <dir>`, `--fonts <f1...>`, `--out-dir <dir>`, `--sizes <N...>`, `--threshold <1..254>`, `--gamma <0.1..5.0>`, `-H/--hw-scheme <json>`, `--accel {auto,cpu,gpu,hybrid,sync}`, `-j/--jobs <N>`, `--update-docs` | Standalone 9-pipeline evaluator across font cuts and pixel sizes. |

```bash
# 0. Probe OpenCL GPU + CPU devices, 3D NDRange support, and Shared GPU RAM
python scripts/probe_hardware.py
python scripts/check_PyOpenCL.py --stress-shared-mb 512

# 1. Synthesize static .ttf files into build/static_ttfs/ and catalogs into build/metadata/
python tools/fonts/build_static_ttf_assets.py --src-dir assets --out-dir build/static_ttfs --meta-out-dir build/metadata --verify

# 2. Build 1-bpp C/H fonts, BDFs, CSVs, and Strike Vault using scheme-driven GPU/CPU dispatch
python tools/fonts/humid1_generate_1bpp.py --workflow build ^
  --scheme scripts/h1os-build-distro/h1os_full.scheme.json ^
  --src-dir build/static_ttfs --out-dir build/h1os --dist-dir dist/h1os_distro

# 3. Generate all 9-method visual PNG comparison sheets across all H1OS fonts & sizes
python tools/fonts/humid1_generate_1bpp.py --workflow audit ^
  --scheme scripts/h1os-build-distro/h1os_full.scheme.json ^
  --src-dir build/static_ttfs --out-dir build/h1os_9method_audit --dist-dir dist/h1os_9method_audit_distro

# 4. Run full 9-pipeline audit & inspection sheet generation (`pipeline: "all-debug"`) on single debug font
python tools/fonts/humid1_generate_1bpp.py --workflow audit ^
  --scheme scripts/h1os-build-distro/h1os_debug.scheme.json ^
  --src-dir build/static_ttfs --out-dir build/h1os_debug --dist-dir dist/h1os_debug_distro

# 5. Evaluate candidate fonts across all 9 conversion pipelines and multiple sizes
python tools/fonts/humid1_font_eval.py ^
  --hw-scheme esp32s3-N8R8-hw_scheme.json ^
  --src-dir build/static_ttfs --out-dir build/evals/static_ttfs ^
  --sizes 10 12 14 16 20 24 --threshold 128 --gamma 1.0 --accel auto
```

## 5. Credits & Attribution

- **Lead Designer & Developer**: **[Humiditron](https://github.com/humiditron)** ([Humidyne Labs](https://github.com/Humidyne-Labs/epd-font))
- **AI/LLM Development Partner**: Collaborative architecture design, mathematical pipeline implementation (`raw-unhinted`, `raw-hinted`, `svg-potrace`, `svg-potrace-jfa`, `mdf`, `msdf`, `sdf-smoothstep`, `adf-biquadratic`, `otsu-adaptive`), 3D NDRange OpenCL GPU / CPU math abstraction (`tools/fonts/math_backends/`, `tools/fonts/opencl_dispatcher.py`), LVGL `>= 9.6.0` integration, and automated verification suite.


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
- `build/<target>/inspect_pages/compare_methods/` — Side-by-side `<font_stem>_<lo>px_<hi>px.png` comparison sheets featuring the scheme's low-detail (`16px` or `min`) & high-detail (`38px` or `max`) strikes (or `<font_stem>_<sz>px.png` for single-size families) across all 9 conversion pipelines.

To verify the entire debug pipeline against **1 font (`IBM Plex Sans Normal` @ `16px` & `38px`)** in seconds rather than running all 108/368 strikes, run:
```bat
scripts\h1os-build-distro\08_run_single_font_debug.bat
```
or via Python CLI:
```bash
python tools/fonts/humid1_generate_1bpp.py --workflow audit --scheme scripts/h1os-build-distro/h1os_debug.scheme.json --src-dir build/static_ttfs --out-dir build/h1os_debug --dist-dir dist/h1os_debug_distro
```
