# Formal Developer & Pipeline Specification — `epd-font` (v1.0.23)

- **Document ID**: `HUMIDITRON-SPEC-EPD-FONT-1.0.23`
- **Project**: A 1-bit EPD font generator and asset pipeline for embedded displays
- **Repository**: [Humidyne-Labs/epd-font](https://github.com/Humidyne-Labs/epd-font) (`v1.0.23`)
- **Authors**: [Humiditron](https://github.com/humiditron) (Humidyne Labs) & AI/LLM Collaborative Development Partner
- **License**: MIT License (Tooling & C Emitter) / SIL OFL 1.1 / CC-BY-4.0 / ISC / MIT (Upstream Fonts)

## 1. Architectural Overview & Source Traceability

`epd-font` v1.0.23 enforces strict separation between immutable upstream static font archives (`assets/`), intermediate build/evaluation/audit outputs (`build/`), root-tracked manual pixel patches (`font_icon_epd_patches.json`), root hardware schemes (`esp32s3-N8R8-hw_scheme.json`, `generic_hw.json`), and portable versioned firmware distributions (`dist/`):
- **Static Source Immutability**: Files in `assets/` (or any custom `--src-dir` font directory) are searched recursively (`os.walk`) and are **never modified in place**, preserving SHA-256 source traceability.
- **Logical `build/` Subdirectory Tree**:
  - `build/static_ttfs/` — Standardized static `.ttf` cuts (`112` cuts across IBM Plex, Google Noto, Terminus `10px–40px`, and 4 icon suites) + `licenses/`.
  - `build/metadata/` — Searchable JSON catalogs and `asset_manifest.json` with SHA-256 digests.
  - `build/cache/` — Deterministic cache for on-the-fly `.bdf -> .ttf` conversions and intermediate rasters.
  - `build/evals/` — 9-pipeline evaluation reports (`.md`, `.csv`, `.json`), per-font sheets (`sheets/*_eval.png`), and master scorecards (`font_eval_comparison_sheet.png`).
  - `build/audits/` — 9-pipeline audit summaries (`audit_9_pipelines_summary.md`).
  - `build/<scheme>/` — Scheme-specific `fonts/`, `bdf/`, `metrics/`, `ascii_patches/`, `inspect_pages/`, `inspect_chars/`, and `debug_stages/`.

## 2. Linear Grayscale Conversion, Gamma Correction & the Nine Resolution-Reduction Pipelines

### 2.1 True sRGB-to-Linear Luminance & Optional Gamma Correction
Given an input 3-channel sRGB raster $(R, G, B) \in [0, 255]^3$ or single-channel coverage buffer $C \in [0, 255]$, each normalized channel $c_s = C / 255$ is linearized via the piecewise IEC 61966-2-1 sRGB transfer function:
$$c_{\text{lin}} = \begin{cases} \dfrac{c_s}{12.92}, & c_s \le 0.04045 \\[6pt] \left(\dfrac{c_s + 0.055}{1.055}\right)^{2.4}, & c_s > 0.04045 \end{cases}$$
For RGB inputs, linear relative luminance is computed via ITU-R BT.709 weights:
$$Y_{\text{lin}} = 0.2126\,R_{\text{lin}} + 0.7152\,G_{\text{lin}} + 0.0722\,B_{\text{lin}}$$
followed by optional user-specified gamma adjustment $\gamma \in [0.1, 5.0]$ (default $\gamma = 1.0$):
$$G_{\text{lin}}(x, y) = \operatorname{round}\!\left(255 \cdot \left(Y_{\text{lin}}(x, y)\right)^{1 / \gamma}\right) \in [0, 255]$$

### 2.2 Mathematical Specification of the Nine Bilevel (`1-bpp`) Pipelines
Let $T \in [1, 254]$ denote the configurable binarization threshold (default $T = 128$):

1. **Pipeline 1 (`raw-unhinted`)**:
   Renders $G_{\text{unhinted}}(x, y)$ at target resolution $S$ with `FT_LOAD_RENDER | FT_LOAD_NO_HINTING | FT_LOAD_TARGET_NORMAL`, applies linear grayscale + $\gamma$, and thresholds at $T$:
   $$B_{\text{raw-unhinted}}(x, y) = \mathbb{I}\!\left(G_{\text{lin, unhinted}}(x, y) \ge T\right)$$
2. **Pipeline 2 (`raw-hinted`)**:
   Renders $G_{\text{hinted}}(x, y)$ at target resolution $S$ with grid-fitting instructions active (`FT_LOAD_RENDER | FT_LOAD_TARGET_NORMAL` or `FT_LOAD_FORCE_AUTOHINT`), applies linear grayscale + $\gamma$, and thresholds at $T$:
   $$B_{\text{raw-hinted}}(x, y) = \mathbb{I}\!\left(G_{\text{lin, hinted}}(x, y) \ge T\right)$$
3. **Pipeline 3 (`svg-potrace`) & Pipeline 4 (`svg-potrace-jfa`)**:
   `svg-potrace` renders high-resolution grayscale $G_{10\times}(u, v)$ at scale $M = 10$, binarizes at $T$, traces the full nested contour hierarchy via `cv2.RETR_TREE` (preserving multi-level interior cutouts and nested islands in filled icons), fits Potrace cubic Bézier splines governed by corner parameter $\alpha_{\max} = 1.0$ ([Potrace Vector Tracing](https://potrace.sourceforge.net/)), applies the $+0.5\text{ px}$ half-pixel center-grid translation, and rasterizes contours in topological tree-depth order using non-antialiased `cv2.LINE_8`. `svg-potrace-jfa` adds 3D NDRange `1+JFA` + 2x2 Marching Squares sub-pixel zero-crossing extraction fused with hierarchical `RETR_TREE` Potrace vector topology.
4. **Pipeline 5 (`mdf`)**:
   Renders $G_{12\times}(u, v)$ at scale $M = 12$, applies median filter $\tilde{G}_{12\times} = \operatorname{Median}_{k \times k}(G_{12\times})$, computes isotropic and directional horizontal/vertical morphological signed distance fields ($\text{SDF}_{\text{iso}}, \text{SDF}_H, \text{SDF}_V$), takes $\operatorname{med}(\text{SDF}_{\text{iso}}, \text{SDF}_H, \text{SDF}_V)$, downsamples onto target pixel centers, and thresholds at $T$.
5. **Pipeline 6 (`msdf`)**:
   Implements true Multi-Channel Signed Distance Field reconstruction ([Chlumsky/msdfgen](https://github.com/Chlumsky/msdfgen)): decomposes contours into corner-delimited edge segments ($\theta_{\text{turn}} \ge 28^\circ$), cycles 3-channel $(R, G, B)$ edge color masks (`Y=RG`, `C=GB`, `M=RB`) across sequential smooth edges so every sharp corner shares exactly one active channel and differs in the other two, evaluates per-channel signed distance fields $(D_R, D_G, D_B)$ using corner bisector disambiguation, reconstructs the corner-preserving scalar distance via the median operator:
   $$D_{\text{MSDF}}(x, y) = \operatorname{median}\!\left(D_R(x, y),\, D_G(x, y),\, D_B(x, y)\right)$$
   and thresholds at $T$.
6. **Pipeline 7 (`sdf-smoothstep`)**:
   Computes a `16x` Euclidean Signed Distance Field $d(u, v) = d_{\text{in}}(u, v) - d_{\text{out}}(u, v)$ and applies analytical Hermite `smoothstep` edge reconstruction ([Red Blob Games SDF Typography](https://www.redblobgames.com/articles/sdf-fonts/)):
   $$\alpha(t) = 3t^2 - 2t^3, \quad t = \operatorname{clamp}\!\left(\frac{d(x, y) + w}{2w},\, 0,\, 1\right)$$
   followed by thresholding at $T$.
7. **Pipeline 8 (`adf-biquadratic`)**:
   Partitions the `16x` Euclidean SDF into an Adaptive Distance Field (`ADF`) quadtree of $4\times 4$ cells per target pixel and reconstructs each target pixel via 9-point biquadratic Lagrange polynomial evaluation $P(u, v)$ centered on the sub-cell grid.
8. **Pipeline 9 (`otsu-adaptive`)**:
   Combines global linear-luminance Otsu inter-class variance maximization ($T_{\text{Otsu}}$) with local Sauvola window mean/standard-deviation adaptive thresholding ($T_{\text{Sauvola}}(x, y) = \mu_W(x, y)\,[1 + k(\sigma_W(x, y)/R - 1)]$) to prevent interior counter closure at small pixel sizes.


### 2.3 Modular Mathematical Abstraction & Hardware-Checked GPU/CPU Dispatch (`tools/fonts/math_backends/`)
In `v1.0.23`, all resolution-reduction, polynomial root-finding, luminance linearization, and histogram thresholding math is abstracted into `tools/fonts/math_backends/`:
- `hw_dispatch.py`: Probes available compute hardware at startup (`select_math_backend()`, `describe_math_backend()`) and routes each mathematical call across three tiers:
  1. **`opencl` (`opencl_kernels.py`)**: PyOpenCL GPU / heterogeneous kernels conforming to the [Khronos OpenCL 3.0 Unified Specification](https://registry.khronos.org/OpenCL/specs/unified/refpages/man/html/), including `srgb_to_linear_gamma_3d_kernel`, `jfa_boundary_init_short2_3d_kernel`, `jfa_step_short2_3d_kernel`, `jfa_short2_to_sdf_3d_kernel`, `sdf_valve_smoothstep_3d_kernel` ($L_2$ screen-space derivative anti-aliasing), `msdf_median3_reconstruct_3d_kernel` ([Chlumsky/msdfgen](https://github.com/Chlumsky/msdfgen)), `adf_biquadratic_9pt_3d_kernel` (Saffron 9-point biquadratic Lagrange quadrature), and `compute_histogram_local_atomic_3d` / `otsu_hist_batch_3d_kernel` (`__local uint local_hist[256]` atomic reduction for Otsu $\sigma_B^2(k^*)$), using `CL_MEM_ALLOC_HOST_PTR` pinned transfers.
  2. **`umat` (`umat_math.py`)**: OpenCV Transparent API (`cv2.ocl` / `cv2.UMat`) OpenCL queue for morphological closing and median filtering when `pyopencl` is absent.
  3. **`cpu` (`cpu_math.py`)**: Deterministic vectorized `NumPy` / `OpenCV` SIMD fallback with 1:1 function signatures.
- **Physical Display Resolution (`188.15 DPI`) & 1-Bit Bilevel Justification**:
  Per the Waveshare 1.54" e-Paper V2 (`SSD1681` / `GDEY0154D67`) mechanical specification (`200 x 200` pixels across a `27.00 mm x 27.00 mm` active area, `0.135 mm x 0.135 mm` square pixel pitch), the exact physical pixel density is:
  $$\text{DPI} = \frac{25.4\text{ mm/inch}}{0.135\text{ mm/pixel}} = 188.1481\dots\text{ DPI} \approx \mathbf{188.15\text{ DPI}}$$
  Because 2-bit (4-level) analog grayscale driving on bistable electrophoretic microcapsules suffers from Arrhenius thermal viscosity drift ($\eta(T) \propto e^{E_a / RT}$), steep Kubelka-Munk sigmoidal reflectance, inter-frame hysteresis across the SSD1681 dual 5,000-byte RAM banks (`0x24` and `0x26`), net DC bias degradation, and `1,000–1,500 ms` refresh latency (vs. `250–350 ms` for 1-bit partial updates), all target output strikes remain strictly 1-bit bilevel (`LV_COLOR_FORMAT_I1`) while using continuous distance-field and polynomial math during high-resolution-to-low-resolution downsampling.

## 3. LVGL `>= 9.6.0` Descriptor & Fallback Chain Specification

Every emitted `.c` module defines `static const lv_font_fmt_txt_dsc_t font_dsc` and `const lv_font_t <symbol>` (LVGL v9+ only, with zero LVGL v6/v7/v8 compatibility shims) with:
- Validated forward declaration `extern const lv_font_t <fallback_symbol>;` when a fallback is configured.
- Circular-include-safe strike declarations inside `humid1_fonts.h` using `#if !defined(LV_CONF_INTERNAL_H)`, forward-declared `struct _lv_font_t`, and `EPD_FONT_EXTERN_DECLARE(<symbol>);` so `CONFIG_LV_FONT_CUSTOM_INCLUDE="h1os_fonts.h"` compiles cleanly before `lv_types.h` and `lv_font.h` (with `#define LV_FONT_CUSTOM_DECLARE LV_FONT_DECLARE(...)` and no trailing semicolon in `h1os_fonts.h`).
- `.fallback = &<fallback_symbol>` guarded by `#if LVGL_VERSION_MAJOR >= 9`.
- `.cap_height` and `.x_height` guarded by `#if LV_VERSION_CHECK(9, 6, 0) || LVGL_VERSION_MAJOR >= 10`.
- `.static_bitmap = 0` guarded by `#if LV_VERSION_CHECK(9, 3, 0) || (LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 3) || LVGL_VERSION_MAJOR > 9`.
- Directed Acyclic Graph (DAG) verification ensuring every `.fallback` target exists in the active scheme's compiled symbol table and never forms a self-loop.

## 4. Single `3 MByte` (`3,145,728` Bytes) Hardware Partition Validation

`load_and_validate_hardware_scheme()` in `humid1_runtime.py` and `write_total_disk_size_report()` in `humid1_lvgl_bdf_export.py` enforce a single `3 MByte` (`3,145,728` bytes) hardware partition constraint loaded from `esp32s3-N8R8-hw_scheme.json` or `generic_hw.json` and `.scheme.json`, with **zero hardcoded fallback values**. Exact `.rodata` Flash byte footprints are computed via:
$$\text{ROM}_{\text{strike}} = B_{\text{bitmap}} + 8(N_{\text{glyphs}} + 1) + 20 N_{\text{cmaps}} + 2 N_{\text{sparse}} + 3 N_{\text{kern}} + 60$$
and reported against the validated `3 MByte` (`3,072 KB` = `3,145,728 B`) hardware partition alongside per-font-pair (`Normal + Bold`) totals.
