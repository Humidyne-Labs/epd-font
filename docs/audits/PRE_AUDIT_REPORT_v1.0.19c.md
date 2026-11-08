# Formal Pre-Audit Report — `epd-font` v1.0.19c Hardware Workload, Shared RAM & Teardown Assessment (`PRE-AUDIT-v1.0.19c`)

* **Document ID**: `HUMIDITRON-PRE-AUDIT-v1.0.19c`

* **Date**: 2026-11-08

* **Project**: A 1-bit EPD font generator and asset pipeline for embedded displays

* **Repository**: [Humidyne-Labs/epd-font](https://www.google.com/search?q=https://github.com/Humidyne-Labs/epd-font) (`v1.0.19c` -> `v1.0.20` Multi-Device OpenCL Workload Distribution, Shared Memory & Teardown Upgrade)

* **Authors**: [Humiditron](https://www.google.com/search?q=https://github.com/humiditron) (Humidyne Labs) & AI/LLM Collaborative Development Partner

* **Format Policy**: Markdown (`.md`) only — zero `.docx` files in repository.

## 1. Executive Summary & Pre-Audit Scope

Following bench testing of `epd-font` `v1.0.19c` on the target Windows 11 workstation (`AMD Ryzen 5 5600G` 12-thread CPU + `AMD Radeon RX 570 Series / Ellesmere` 32-CU discrete GPU with `4.0 GB` Dedicated VRAM and `15.7 GB` Shared GPU Memory), a formal pre-audit was conducted on `epd-font-v1.0.19c-fixme.zip`, the user's audit specification (`docs/humid1-audit-v1.0.20.md`), hardware probe scripts (`scripts/check_PyOpenCL.py`, `scripts/probe_hardware.py`), and the captured runtime/Task Manager telemetry in `docs/audits/exhibits/v1.0.19c/` (`check_PyOpenCL.py.log`, `run_time_11-07-2026-11-25-pm.log`, `task_manager_01.jpg`, `task_manager_02.jpg`, and `Jr.Agent_Notes.md`).

The pre-audit investigated six specific hardware, memory, and runtime issues observed during `v1.0.19c` testing:

1. **Under-Utilization of GPU Compute Units (`32 CUs`), Hardware Queues (`Compute 0..3`), and Work-Item Dimensions (`Max Work-Item Dimensions: 3`)**: Why `Compute 0` pinned at `100%` while `Compute 1..3` (`0%`) and the 12-thread `CPU` (`3%`) sat idle, and why only 1D/2D work-item dimensions were used instead of all `3` dimensions (`[x, y, z]`).

2. **Unused `15.7 GB` Host/GPU Shared RAM (`Shared GPU memory: 0.2 / 15.7 GB`)**: How to allocate staging and batch tensors in the `15.7 GB` WDDM Shared GPU Memory aperture (`CL_MEM_ALLOC_HOST_PTR` zero-copy pinned host memory) rather than exhausting the `4.0 GB` Dedicated GPU VRAM.

3. **Post-Termination `2.0 GB` GPU Memory Retention (`Dedicated GPU memory: 2.0 / 4.0 GB` after exit)**: Root cause of the `2.0–2.3 GB` VRAM allocation remaining after terminating the script (`task_manager_02.jpg`) and deterministic teardown remediation.

4. **Slow Execution in `02_build_fonts.bat` (`99_run_full_pipeline.bat`)**: Why spawning 12 `ProcessPoolExecutor` workers caused 12 competing OpenCL GPU contexts to thrash over PCIe on tiny per-glyph dispatches.

5. **Noisy `Ctrl+C` (`SIGINT`) Terminal Traceback Output**: Why pressing `Ctrl+C` printed 28 lines of interleaved `multiprocessing.process._bootstrap` `KeyboardInterrupt` tracebacks (`run_time_11-07-2026-11-25-pm.log`).

6. **Multi-Platform OpenCL Runtime Support & `README.md` Documentation**: Supporting simultaneous workload distribution across `[0] Platform 0, Device 0: Ellesmere (ALL | GPU) - 32 CUs` and `[1] Platform 1, Device 0: AMD Ryzen 5 5600G with Radeon Graphics (ALL | CPU) - 12 CUs` (installed via the [Intel CPU Runtime for OpenCL Applications](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-cpu-runtime-for-opencl-applications-with-sycl-support.html)), documenting OpenCL Runtime libraries in `README.md`, and replacing the broken `python -m pyopencl.dump` command with `python scripts/check_PyOpenCL.py` and `python scripts/probe_hardware.py`.

## 2. Pre-Audit Findings Matrix (`PRE-20-01` through `PRE-20-06`)

| Finding ID | Severity | Component / File | Pre-Audit Finding in `v1.0.19c` | Required `v1.0.20` Remediation | 
| ----- | ----- | ----- | ----- | ----- | 
| **`PRE-20-01`** | **Critical** | `tools/fonts/math_backends/opencl_kernels.py` & `hw_dispatch.py` | **1D/2D Per-Glyph Kernel Launches & Single-Queue Bottleneck**: (1) `srgb_to_linear_gamma_kernel` and `compute_histogram_local_atomic` launched 1D NDRanges `(gsize,)`, and distance-field kernels launched 2D NDRanges `(target_w, target_h)` for one glyph at a time (`16x16 = 256` work-items = **1 work-group on 1 Compute Unit**, leaving 31 of 32 CUs idle per launch and leaving Dimension 3 unused). (2) Only a single `cl.CommandQueue` was created, routing all work exclusively to `Compute 0` (`100%`) while `Compute 1..3` remained at `0%`. | Upgrade all OpenCL kernels to **3D NDRange `(dim_x, dim_y, dim_z)`** with 3D work-groups `(8, 8, 4) = 256` work-items (4 wavefronts of 64 threads on `Ellesmere`) so all `3` Work-Item Dimensions (`[x, y, z]`) are utilized and strike batches span `>= 32` work-groups across all `32 CUs`. Stripe work across **4 hardware `cl.CommandQueue` rings** (`Compute 0..3`). | 
| **`PRE-20-02`** | **Critical** | `tools/fonts/humid1_generate_1bpp.py`, `humid1_runtime.py`, & `math_backends/` | **12-Process GPU Context Thrashing & `2.0–2.3 GB` VRAM Leak on Teardown**: (1) `ProcessPoolExecutor(max_workers=12)` spawned 12 `python.exe` processes; every worker lazily called `_probe_and_init_backend()` and created its own `cl.Context` on `Ellesmere` (`12 x ~190 MB = 2.3 GB` Dedicated VRAM) and fought over the WDDM driver lock (`Compute 0` pinned at `100%` context-switching while CPU threads stalled at `3%`). (2) On `Ctrl+C`, `pool.shutdown(wait=False)` exited the parent process without terminating the 12 `SpawnProcess` children or calling `.release()` on `cl.Buffer` / `cl.CommandQueue` / `cl.Context`, leaving `2.0 GB` of Dedicated GPU Memory allocated (`task_manager_02.jpg`). | Enforce **Single-Owner GPU Context Architecture** (`opencl_dispatcher.py`): only 1 persistent GPU coordinator owns the discrete GPU (`Ellesmere`), while child CPU workers set `EPD_FONT_WORKER_ROLE=cpu` (or bind to `[1] Ryzen 5 5600G OpenCL CPU - 12 CUs`). Add deterministic `release()` / `atexit` teardown (`Buffer.release()`, `CommandQueue.finish()`, `CommandQueue.release()`, `gc.collect()`) and terminate child processes on exit. | 
| **`PRE-20-03`** | **High** | `tools/fonts/math_backends/opencl_kernels.py` & `humid1_runtime.py` | **`15.7 GB` Host/GPU Shared Memory (`Shared GPU memory`) Under-Utilized**: `task_manager_01.jpg` showed `2.3 / 4.0 GB` Dedicated GPU Memory used while `Shared GPU memory` was only `0.2 / 15.7 GB`. Temporary `cl.Buffer` objects were allocated and discarded on every call without a persistent pinned host-shared memory arena. | Implement `SharedHostMemoryArena` using `CL_MEM_ALLOC_HOST_PTR` + `cl.enqueue_map_buffer` zero-copy pinned host memory sized from the host's detected WDDM Shared GPU Memory (`15.7 GB` total / configurable `--shared-ram-mb`), reusing pinned host buffers across batches and releasing them deterministically on teardown. | 
| **`PRE-20-04`** | **High** | `tools/fonts/opencl_dispatcher.py`, `humid1_generate_1bpp.py`, & `humid1_bilevel_pipelines.py` | **Sub-Optimal Hardware Workload Partitioning & Slow `raw-hinted` Execution**: (1) `_extract_ft_grayscale()` called `dispatch_srgb_to_linear_grayscale()` on every glyph even for `raw-hinted` small text strikes, incurring PCIe transfer and OpenCL context initialization overhead on all 108 strikes. (2) Both `[0] Ellesmere (GPU - 32 CUs)` and `[1] AMD Ryzen 5 5600G (CPU - 12 CUs)` were detected by `probe_hardware.py`, but tasks were not partitioned between GPU and CPU by computation density. | Create `tools/fonts/opencl_dispatcher.py` (and `tools/fonts/build_fonts_hybrid.py`) to partition tasks per `Jr.Agent_Notes.md`: route heavy icon catalogs (`Tabler`, `Phosphor`, `Lucide`, `FontAwesome 7`), distance-field pipelines (`sdf-smoothstep`, `msdf`, `mdf`, `adf-biquadratic`, `otsu-adaptive`), and large strikes (`>= 24px`) to the GPU (`32 CUs` + 3D batching), while routing `Terminus` BDF/bitmap strikes and small text strikes (`10–22px`) to the 12-thread `Ryzen 5 5600G` CPU workers. | 
| **`PRE-20-05`** | **Medium** | `tools/fonts/humid1_runtime.py` (`L62–78`, `L435–465`) | **Noisy `Ctrl+C` (`KeyboardInterrupt`) Multiprocessing Tracebacks**: When `Ctrl+C` was pressed (`run_time_11-07-2026-11-25-pm.log`), Windows broadcast `CTRL_C_EVENT` to all 12 `SpawnProcess` workers. Because workers did not set `signal.signal(signal.SIGINT, signal.SIG_IGN)` in their initializer, all 12 workers crashed inside `call_queue.get()` (`_winapi.WaitForMultipleObjects`) and dumped raw `Traceback (most recent call last): ... KeyboardInterrupt` stacks to the console. | Pass `initializer=_worker_process_init` (`signal.signal(signal.SIGINT, signal.SIG_IGN)`) to `ProcessPoolExecutor`, explicitly terminate and join active worker processes on `KeyboardInterrupt`, release all OpenCL/shared memory buffers, and print a single clean status line with zero tracebacks. | 
| **`PRE-20-06`** | **Medium** | `README.md`, `scripts/check_PyOpenCL.py`, `scripts/probe_hardware.py`, & `VERSION.json` | **Missing OpenCL Runtime Library Guide in `README.md` & Broken `pyopencl.dump` Command**: (1) `README.md` (`v1.0.19c`) instructed users to run `python -m pyopencl.dump`, which fails on `pyopencl 2026.1.4` (`No module named pyopencl.dump`, `check_PyOpenCL.py.log`). (2) `README.md` lacked installation instructions and links for runtime OpenCL ICD libraries ([Intel CPU Runtime for OpenCL Applications](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-cpu-runtime-for-opencl-applications-with-sycl-support.html), AMD Adrenalin/ROCm OpenCL ICD, NVIDIA OpenCL ICD, and Linux `pocl`/`ocl-icd`). | Update `README.md` (`v1.0.20`) with a dedicated **OpenCL Runtime Libraries & Multi-Device Setup Guide** (including the Intel CPU Runtime for OpenCL Applications, AMD/NVIDIA GPU runtimes, and Linux ICD packages), replace `pyopencl.dump` with `scripts/check_PyOpenCL.py` and `scripts/probe_hardware.py`, and rev all repository files to `v1.0.20`. | 

## 3. Detailed Technical Analysis of Pre-Audit Evidence (`docs/audits/exhibits/v1.0.19c/`)

### 3.1 Telemetry Analysis of `task_manager_01.jpg` and `task_manager_02.jpg`

Inspection of the user's Windows 11 Task Manager captures reveals the exact hardware behavior under `v1.0.19c`:

* **During Execution (`task_manager_01.jpg`)**:

  * `CPU`: **3% utilization** (`4.08 GHz` on `AMD Ryzen 5 5600G`).

  * `GPU 0 (Radeon RX 570 Series)`: **100% utilization** (`62 °C`), but **only `Compute 0` is at 100%**, while `3D` (`1%`), `Compute 1` (`0%`), and `Compute 3` (`0%`) are idle.

  * `Dedicated GPU memory`: **2.3 / 4.0 GB** consumed.

  * `Shared GPU memory`: **0.2 / 15.7 GB** consumed (`15.5 GB` of shared host/GPU aperture sitting unused).

* **After Script Termination via `Ctrl+C` (`task_manager_02.jpg`)**:

  * `GPU 0` utilization drops to `1%`, yet **`Dedicated GPU memory` remains stuck at `2.0 / 4.0 GB`** (`GPU Memory: 2.1 / 19.7 GB`).

* **Root Cause**:

  * When `02_build_fonts.bat` launched `ProcessPoolExecutor(max_workers=12)`, each of the 12 spawned Python worker processes called `get_active_math_backend()` upon rasterizing its first glyph and created an independent `cl.Context` on `Ellesmere` (`GPU 0`).

  * On Windows WDDM (`Driver version: 31.0.21923.11000`, `PAL,HSAIL`), each process-level `cl.Context` reserves `~180–195 MB` of Dedicated GPU Memory for page tables, ring buffers, and compiled ISA binaries (`12 processes × 190 MB ≈ 2.28 GB`).

  * Furthermore, when `Ctrl+C` was pressed, `pool.shutdown(wait=False, cancel_futures=True)` returned in the parent process without terminating the 12 child `SpawnProcess` processes or calling `.release()` on OpenCL contexts and buffers, leaving orphaned worker processes holding `2.0 GB` of Dedicated VRAM.

### 3.2 Analysis of `check_PyOpenCL.py.log` and Multi-Device Enumeration (`probe_hardware.py`)

In `check_PyOpenCL.py.log` and `humid1-audit-v1.0.20.md`, the user's workstation enumerates two OpenCL platforms after installing the [Intel CPU Runtime for OpenCL Applications](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-cpu-runtime-for-opencl-applications-with-sycl-support.html):

* **`[0] Platform 0, Device 0: Ellesmere (ALL | GPU) - 32 CUs`** (`AMD Accelerated Parallel Processing`, `OpenCL 2.1 AMD-APP (3584.0)`, `Max Clock: 1250 MHz`, `Global Memory: 4096.00 MB`, `Local Memory: 32.00 KB`, `Max Work-Group Size: 256`, `Max Work-Item Dimensions: 3`, `Max Work-Item Sizes: [1024, 1024, 1024]`).

* **`[1] Platform 1, Device 0: AMD Ryzen 5 5600G with Radeon Graphics (ALL | CPU) - 12 CUs`** (`Intel(R) OpenCL` CPU Runtime, `12 Compute Units`, `31.4 GB` Host RAM / `15.7 GB` Shared RAM).

By upgrading the OpenCL kernels to **3D NDRanges `(dim_x, dim_y, dim_z)`** (`work_dim = 3`, using `(8, 8, 4)` 3D local work-groups of `256` work-items across glyph batches), striping GPU dispatches across **4 hardware `cl.CommandQueue`s**, staging tensors in the **`15.7 GB` Shared GPU Memory** (`CL_MEM_ALLOC_HOST_PTR`), and partitioning strikes across both `[0] Ellesmere (32 CUs)` and `[1] Ryzen 5 5600G (12 CUs)` with deterministic teardown, all six audit findings are resolved in `v1.0.20`.