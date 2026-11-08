# `epd-font` (v1.0.19c) — A 1-bit EPD Font Generator and Asset Pipeline for Embedded Displays

[![Version](https://img.shields.io/badge/version-v1.0.19c-blue.svg)](VERSION.json)
[![Repository](https://img.shields.io/badge/github-Humidyne--Labs%2Fepd--font-181717.svg)](https://github.com/Humidyne-Labs/epd-font)
[![Lead Developer](https://img.shields.io/badge/developer-Humiditron-0A66C2.svg)](https://github.com/humiditron)
[![License](https://img.shields.io/badge/license-MIT%20%2F%20OFL--1.1%20%2F%20ISC-green.svg)](LICENSE)

**`epd-font`** is **A 1-bit EPD font generator and asset pipeline for embedded displays**, designed and developed collaboratively by **[Humiditron](https://github.com/humiditron)** (Humidyne Labs) and the **AI/LLM Collaborative Development Partner** for monochrome Electrophoretic Displays (EPD) such as the Waveshare 1.54" e-Paper V2 (`SSD1681` / `GDEY0154D67`, `200 × 200` pixels @ `188.15 DPI`), OLEDs, Memory LCDs, and LVGL `>= 9.6.0` (and v8/v9) embedded applications ([public repository](https://github.com/Humidyne-Labs/epd-font)).

## 1. Core Capabilities in v1.0.19c

1. **Eight Deterministic Resolution-Reduction (`1-bpp`) Conversion Pipelines + Linear Grayscale & Gamma (`tools/fonts/humid1_bilevel_pipelines.py`)**:
   - **True Linear Grayscale + Optional Gamma**: Converts sRGB or single-channel coverage rasters to ITU-R BT.709 / IEC 61966-2-1 linear luminance ($Y_{\text{lin}} = 0.2126 R_{\text{lin}} + 0.7152 G_{\text{lin}} + 0.0722 B_{\text{lin}}$) with configurable gamma adjustment (`--gamma`, default `1.0`).
   - **`raw-unhinted`**: Direct unhinted FreeType `8-bit` linear grayscale rasterization (`FT_LOAD_NO_HINTING`) + configurable binary threshold (default `128`).
   - **`raw-hinted`**: Grid-fitted hinted FreeType linear grayscale rasterization (`FT_LOAD_TARGET_NORMAL` / `FT_LOAD_FORCE_AUTOHINT`) + configurable binary threshold (default `128`).
   - **`svg-potrace`**: High-resolution (`10x`) anti-aliased rasterization -> binary threshold -> hierarchical `cv2.RETR_TREE` Potrace B-spline / cubic Bézier vector contour tracing (`.svg`) -> `+0.5 px` half-pixel center alignment -> non-antialiased (`LINE_8` topological tree-depth fill) low-resolution re-rasterization ([Potrace Vector Tracing](https://potrace.sourceforge.net/)).
   - **`mdf`**: High-resolution (`12x`) super-sampling with median filtering (`cv2.medianBlur`) + directional morphological Signed Distance Field (`SDF`) -> pixel-center downsampling.
   - **`msdf`**: True Multi-Channel Signed Distance Field (`12x` super-sampling -> 3-channel $(R, G, B)$ contour edge coloring at sharp corners -> directional signed pseudo-distance -> $\text{median}(R, G, B)$ reconstruction per [Chlumsky/msdfgen](https://github.com/Chlumsky/msdfgen)).
   - **`sdf-smoothstep`**: Supersampled Euclidean Signed Distance Field (`16x`) with $L_2$ screen-space gradient width and analytical Hermite `smoothstep` edge reconstruction ([Red Blob Games SDF Typography](https://www.redblobgames.com/articles/sdf-fonts/)).
   - **`adf-biquadratic`**: Adaptive Distance Field (`ADF`) quadtree subdivision (`12x–16x` -> $4\times 4$ cells) with 9-point biquadratic Lagrange polynomial surface interpolation ($P(u,v)$) for corner and thin-stem preservation.
   - **`otsu-adaptive`**: Linear-luminance global Otsu threshold ($\sigma_B^2(k^*)$) blended with local adaptive thresholding for interior counter preservation.
2. **Modular GPU/CPU Mathematical Abstraction & Hardware Dispatch (`tools/fonts/math_backends/`)**:
   - Abstracts all mathematical kernels into `opencl_kernels.py` ([Khronos OpenCL 3.0 Unified Specification](https://registry.khronos.org/OpenCL/specs/unified/refpages/man/html/)), `umat_math.py` (OpenCV Transparent API `cv2.UMat`), `cpu_math.py` (vectorized `NumPy`/`OpenCV` SIMD), and `hw_dispatch.py`.
   - Automatically probes GPU/OpenCL support at startup (`--accel {auto,opencl,umat,cpu}`), verifies kernel parity and unit SDF gradient slope ($\|\nabla d\|_2 \approx 1.0$), and routes math calls to the active accelerator (including Cem Yüksel's degree-5 to degree-2 monotonic derivative cascade for exact cubic Bézier distance evaluation).
3. **Strict `char_debug` & `sheet_debug` Boolean Gating + `'all'` / `'all-debug'` Multi-Method Comparison**:
   - Individual character blueprint cards (`inspect_chars/`) and strike character map sheets (`inspect_pages/`) are strictly gated off when `"char_debug": false` and `"sheet_debug": false` in `.scheme.json` (or `--no-char-debug` / `--no-sheet-debug`).
   - Setting `"pipeline": "all"` (or `"all-debug"`) in `.scheme.json` executes all 8 conversion methods and dumps every method's sheet (`inspect_pages/<method>/<symbol>.png`) plus a side-by-side multi-method comparison sheet (`inspect_pages/compare_methods/<symbol>_all_methods.png`).
4. **Hardware Scheme Files (`esp32s3-N8R8-hw_scheme.json`, `genaric_hw.json`), `188.15 DPI` Calibration & Strict `3 MByte` Partition Validation**:
   - Calibrated to the exact physical pixel density of the Waveshare 1.54" e-Paper V2 (`200 × 200` pixels across `27.00 mm × 27.00 mm`, `0.135 mm` pixel pitch -> `188.15 DPI`).
   - Supports only the single `3 MByte` (`3,145,728` bytes) hardware partition constraint in `rom_space_estimate.txt` and `total_disk_size.txt`, with **zero hardcoded fallback defaults**.
5. **Closed-Loop Manual ASCII Patching & LVGL `>= 9.6.0` ESP-IDF CMake Integration**:
   - Includes `humid1_cmake_font_builder.py`, `humid1_fw_emit.py`, `cmake/epd_font_esp_idf.cmake`, and `humid1_package_distro.py` for zero-dependency ESP-IDF CMake builds and portable versioned `.zip` distribution bundles (`dist/epd-font_<workflow>_v1.0.19c.zip`).

## 2. Detailed Installation & Setup Guide

### 2.1 System Prerequisites

| Prerequisite | Requirement / Version | Notes & Platform Details |
| :--- | :--- | :--- |
| **Operating System** | **Windows 10 / 11 (x64)** or **Linux (x86_64 / ARM64)** | Windows is the primary one-click `.bat` host; Linux is fully supported via CLI/CMake. *(Apple OS is not supported.)* |
| **Python Runtime** | **Python `3.9` or newer** (`3.10`, `3.11`, or `3.12` recommended) | Download from [python.org/downloads](https://www.python.org/downloads/). On Windows, check **"Add python.exe to PATH"** in the installer. |
| **pip Package Manager** | **`pip >= 23.0`** (bundled with Python 3.9+) | Verify with `python -m pip --version`. |
| **FreeType 2 Shared Library** | **`libfreetype` (`>= 2.10`)** | Bundled automatically on Windows and Linux when installing `freetype-py>=2.4.0` via `pip`. On Linux, you may also install `libfreetype6` via `apt`/`dnf`. |
| **GPU / OpenCL Runtime *(Optional)*** | **OpenCL `1.2` / `3.0` ICD** ([Khronos OpenCL](https://registry.khronos.org/OpenCL/specs/unified/refpages/man/html/)) | Optional for GPU kernel acceleration (`pyopencl` / `cv2.UMat`) on AMD GCN/Polaris/RDNA, NVIDIA, or Intel GPUs. Automatically falls back to vectorized CPU if absent. |
| **ESP-IDF / CMake *(Optional)*** | **ESP-IDF `v5.x`** & **CMake `>= 3.16`** | Needed only when compiling generated LVGL `>= 9.6.0` `.c`/`.h` font targets into MCU firmware. |

### 2.2 Required & Optional Python Packages

`epd-font` operates in two distinct modes depending on whether you are **generating/auditing font assets** or **emitting C/H files from a pre-compiled Strike Vault during firmware builds**:

1. **Mode A — Downstream Firmware / CMake Vault Emitter (`tools/fonts/humid1_fw_emit.py`)**:
   - **Third-Party Packages Needed**: **None (`0` external packages)**. Uses 100% Python 3 standard library (`json`, `gzip`, `pathlib`, `argparse`, `shutil`, `re`, `signal`) and executes in `< 0.15s`.
2. **Mode B — Full Font Generator, 8-Pipeline Converter, Visual Inspector & Evaluator (`humid1_generate_1bpp.py`, `build_static_ttf_assets.py`, `humid1_font_eval.py`)**:
   - Requires the 5 core packages in `requirements.txt` (plus optional `pyopencl` for direct OpenCL GPU kernel execution):

| Python Package | Minimum Version | Role in `epd-font` Pipeline | Required? |
| :--- | :--- | :--- | :--- |
| [`fonttools`](https://pypi.org/project/fonttools/) | `>= 4.40.0` | Parses `.ttf`/`.otf`/`.ttc` tables (`cmap`, `hmtx`, `head`, `hhea`, `OS/2`, `kern`, `gvar`), synthesizes static cuts, and converts X11 `.bdf` strikes to `.ttf` | **Required** |
| [`Pillow`](https://pypi.org/project/Pillow/) | `>= 10.0.0` | Renders per-strike page check sheets (`inspect_pages/`), multi-method comparison sheets, `188.15 DPI` EPD specimen mockups, and per-character blueprint cards | **Required** |
| [`freetype-py`](https://pypi.org/project/freetype-py/) | `>= 2.4.0` | Provides the cross-platform `freetype.dll` / `libfreetype.so` C binary used by `humid1_ft_raster.py` for hinted, unhinted, and high-resolution glyph rendering | **Required** |
| [`numpy`](https://pypi.org/project/numpy/) | `>= 1.24.0` | Vectorized array math, IEC 61966-2-1 sRGB-to-linear luminance LUTs, Betti number ($B_0, B_1$) topology verification, Otsu histograms, and CPU polynomial solvers | **Required** |
| [`opencv-python`](https://pypi.org/project/opencv-python/) | `>= 4.8.0` | Euclidean distance transforms (`cv2.distanceTransform`), hierarchical `cv2.RETR_TREE` Potrace contour extraction, morphological filtering, and `cv2.UMat` OpenCL acceleration | **Required** |
| [`pyopencl`](https://pypi.org/project/pyopencl/) | `>= 2023.1` | Compiles and dispatches OpenCL C kernels (`tools/fonts/math_backends/opencl_kernels.py`) on AMD, NVIDIA, and Intel GPUs | *Optional (Auto-fallback to CPU/UMat)* |

### 2.3 Step-by-Step Python & `pip` Installation Guide

#### Option A: One-Click Windows Setup (`.bat` Launcher)
On Windows 10/11 with Python 3.9+ on your `PATH`, double-click or run `00_setup_env.bat` from any workflow folder in `scripts/`:
```cmd
scripts\h1os-build-distro\00_setup_env.bat
```
This script verifies your Python installation, upgrades `pip`, installs all 5 required packages (`fonttools`, `Pillow`, `freetype-py`, `numpy`, `opencv-python`), and attempts an optional `pyopencl` install (gracefully skipping `pyopencl` if no OpenCL ICD is present).

#### Option B: Manual Installation via `pip` and `requirements.txt` (Windows PowerShell / CMD)
We recommend using a dedicated Python virtual environment (`.venv`) so package versions stay isolated:
```powershell
# 1. Open PowerShell or Command Prompt in the epd-font repository root
cd path\to\epd-font

# 2. Verify Python 3.9+ is installed and on PATH
python --version

# 3. (Recommended) Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\activate

# 4. Upgrade pip, setuptools, and wheel
python -m pip install --upgrade pip setuptools wheel

# 5. Install all core required packages from requirements.txt
python -m pip install -r requirements.txt

# 6. (Optional) Install PyOpenCL if your system has an AMD, NVIDIA, or Intel OpenCL driver
python -m pip install "pyopencl>=2023.1"
```
If you prefer to install the core packages directly without `requirements.txt`:
```powershell
python -m pip install "fonttools>=4.40.0" "Pillow>=10.0.0" "freetype-py>=2.4.0" "numpy>=1.24.0" "opencv-python>=4.8.0"
```

#### Option C: Manual Installation on Linux (`Ubuntu / Debian / Fedora / Arch`)
```bash
# 1. Install Python 3, venv, pip, and system FreeType library
# Ubuntu / Debian:
sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip libfreetype6
# (Optional for OpenCL GPU acceleration on Linux):
# sudo apt-get install -y ocl-icd-libopencl1 opencl-headers clinfo

# 2. Create and activate a virtual environment in the epd-font root
python3 -m venv .venv
source .venv/bin/activate

# 3. Upgrade pip and install core dependencies
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install -r requirements.txt

# 4. (Optional) Install PyOpenCL for GPU kernel dispatch
python3 -m pip install "pyopencl>=2023.1"
```

### 2.4 Verifying Your Installation & Hardware Acceleration Backend

Run the following one-liner from the repository root to verify that all libraries, the FreeType C binary, and the `math_backends` hardware dispatcher load properly:
```bash
python -c "import sys; sys.path.insert(0, 'tools/fonts'); from humid1_ft_raster import load_freetype; from math_backends import describe_math_backend; load_freetype(); print('FreeType OK |', describe_math_backend())"
```
Expected output:
- **With PyOpenCL GPU**: `FreeType OK | backend=opencl (GPU: <Device Name>, CUs=32, max_wg=256, sdf_grad_ok=True)`
- **With OpenCV UMat**: `FreeType OK | backend=umat (GPU_UMAT: <Device Name>, CUs=..., max_wg=256, sdf_grad_ok=True)`
- **CPU-Only Host**: `FreeType OK | backend=cpu (CPU: Vectorized NumPy/OpenCV SIMD Engine, CUs=..., max_wg=1, sdf_grad_ok=True)`

You can also force a specific mathematical backend at any time via the `--accel {auto,opencl,umat,cpu}` CLI flag or the `EPD_FONT_ACCEL` environment variable:
```bash
# Force OpenCL GPU backend (or auto-fallback if unavailable)
python tools/fonts/humid1_generate_1bpp.py --workflow build --scheme scripts/h1os-build-distro/h1os_full.scheme.json --src-dir build/static_ttfs --out-dir build/h1os --accel opencl

# Force deterministic CPU SIMD backend
python tools/fonts/humid1_generate_1bpp.py --workflow build --scheme scripts/h1os-build-distro/h1os_full.scheme.json --src-dir build/static_ttfs --out-dir build/h1os --accel cpu
```

## 3. Repository Directory Structure (`v1.0.19c`)

```text
epd-font/
├── LICENSE                                  # MIT License (Humidyne Labs / Humiditron pipeline & tooling)
├── VERSION.json                             # Release & upstream asset version manifest (v1.0.19c)
├── requirements.txt                         # Pip dependency manifest for core & optional GPU packages
├── esp32s3-N8R8-hw_scheme.json              # Root ESP32-S3-N8R8 hardware scheme (188.15 DPI, partition_1: "3 MBytes")
├── genaric_hw.json                          # Root generic hardware scheme (188.15 DPI, partition_1: "3 MBytes")
├── font_icon_epd_patches.json               # Root-tracked manual 1-bpp pixel patch manifest
├── README.md                                # Primary repository overview, installation & quick-start guide
├── CHANGELOG.md                             # Chronological release history (v0.0.1 -> v1.0.19c)
├── docs/
│   ├── HOW_TO_GUIDE.md                      # Complete CLI, scheme, 8-pipeline & ESP-IDF CMake guide
│   ├── MAINTAINER_SPEC.md                   # Formal 1-bpp mathematical, GPU OpenCL & pipeline specification
│   ├── LEGACY_METHODOLOGY_v1.0.17.md        # Archival summary of legacy v1.0.17 methodology
│   └── audits/                              # Pre-Audit, Post-Audit, and 8-Pipeline Evaluation Reports
├── scripts/                                 # One-click Windows (.bat) workflow directories:
│   ├── full-audit-build-distro/             #   1. Complete 10px-40px (step 2px) visual audit & distro
│   ├── h1os-build-distro/                   #   2. H1OS & humid1-os schemes (h1os_full & h1os_lite)
│   ├── example-build-distro/                #   3. General-purpose embedded display project workflow
│   └── font-eval-suite/                     #   4. Multi-font 8-pipeline evaluation suite
├── assets/                                  # Untouched, versioned static upstream font & icon archives
│   ├── font_assets/                         #   - Hinted IBM Plex, Hinted Google Noto v2.013, Terminus v4.49.1
│   └── icon_assets/                         #   - Font Awesome v7.3.1, Lucide v1.67.0, Phosphor v2.1.0, Tabler v3.50.0
├── tools/
│   ├── fonts/
│   │   ├── math_backends/                   # Modular GPU/CPU math abstraction & hardware dispatcher:
│   │   │   ├── __init__.py                  #   - Unified mathematical dispatch exports
│   │   │   ├── hw_dispatch.py               #   - Runtime GPU/UMat/CPU capability probe & router
│   │   │   ├── opencl_kernels.py            #   - OpenCL 3.0 kernels (Yuksel Bezier SDF, Valve SDF, MSDF, ADF, Otsu)
│   │   │   ├── umat_math.py                 #   - OpenCV Transparent API (cv2.UMat) OpenCL tier
│   │   │   └── cpu_math.py                  #   - Vectorized NumPy/OpenCV SIMD CPU backend
│   │   ├── humid1_runtime.py                # Hardware scheme validation, GPU/CPU/RAM scaling, Ctrl-C handler
│   │   ├── humid1_bilevel_pipelines.py      # 8 bilevel pipelines + linear grayscale + gamma
│   │   ├── build_static_ttf_assets.py       # Raw assets -> build/static_ttfs/*.ttf + build/metadata/*.json
│   │   ├── humid1_generate_1bpp.py          # Master pipeline orchestrator (gen-assets, patch, check, build, audit)
│   │   ├── humid1_font_eval.py              # 8-Pipeline per-font, per-size benchmark & visual evaluator
│   │   ├── humid1_fw_emit.py                # Zero-dependency CMake firmware emitter (< 0.15s)
│   │   ├── humid1_cmake_font_builder.py     # ESP-IDF CMake font builder integration script
│   │   ├── humid1_package_distro.py         # Versioned distribution packager & zipper
│   │   ├── cmake/                           # epd_font_esp_idf.cmake & example_CMakeLists.txt
│   │   └── schemes/                         # 16 curated declarative JSON font schemes
│   └── agent/                               # Deterministic glyph/string/icon inspection tools
├── build/                                   # [Gitignored] static_ttfs, metadata, cache, evals, audits, per-scheme outputs
└── dist/                                    # [Gitignored] Versioned portable distribution bundles & .zip archives
```

## 4. Quick Start Workflows

### A. One-Click Windows Batch Workflows (`scripts/*`)
Run `00_setup_env.bat` once to install dependencies, then run `99_run_full_pipeline.bat` inside any workflow folder:
- **General Example Project**: `scripts\example-build-distro\99_run_full_pipeline.bat` -> outputs to `build\example\` and `dist\epd-font_example_v1.0.19c.zip`
- **Full 10px–40px (Step 2px) Master Audit**: `scripts\full-audit-build-distro\99_run_full_pipeline.bat` -> outputs to `build\audit\` and `dist\epd-font_audit_v1.0.19c.zip`
- **H1OS / `humid1-os` Deployment**: `scripts\h1os-build-distro\99_run_full_pipeline.bat` -> outputs to `build\h1os\` and `dist\epd-font_h1os_v1.0.19c.zip`

### B. Command-Line Usage (Windows & Linux Python 3)
```bash
# 1. Synthesize static .ttf files into build/static_ttfs/ and catalogs into build/metadata/
python tools/fonts/build_static_ttf_assets.py --src-dir assets --out-dir build/static_ttfs --meta-out-dir build/metadata --verify

# 2. Build 1-bpp C/H fonts, BDFs, CSVs, and Strike Vault using any of the 8 conversion pipelines
python tools/fonts/humid1_generate_1bpp.py --workflow build \
  --scheme scripts/h1os-build-distro/h1os_full.scheme.json \
  --src-dir build/static_ttfs --out-dir build/h1os --dist-dir dist/h1os_distro \
  --pipeline msdf --threshold 128 --gamma 1.0 --accel auto

# 3. Dump all 8 conversion method sheets for side-by-side manual review
python tools/fonts/humid1_generate_1bpp.py --workflow check \
  --scheme scripts/example-build-distro/example.scheme.json \
  --src-dir build/static_ttfs --out-dir build/example \
  --pipeline all --sheet-debug --no-char-debug --accel auto

# 4. Evaluate candidate fonts across all 8 conversion pipelines and multiple sizes
python tools/fonts/humid1_font_eval.py \
  --src-dir build/static_ttfs --out-dir build/evals/static_ttfs \
  --sizes 10 12 14 16 20 24 --threshold 128 --gamma 1.0 --accel auto
```

## 5. Credits & Attribution

- **Lead Designer & Developer**: **[Humiditron](https://github.com/humiditron)** ([Humidyne Labs](https://github.com/Humidyne-Labs/epd-font))
- **AI/LLM Development Partner**: Collaborative architecture design, mathematical pipeline implementation (`raw-unhinted`, `raw-hinted`, `svg-potrace`, `mdf`, `msdf`, `sdf-smoothstep`, `adf-biquadratic`, `otsu-adaptive`), OpenCL GPU / CPU math abstraction (`tools/fonts/math_backends/`), LVGL `>= 9.6.0` integration, and automated verification suite.
