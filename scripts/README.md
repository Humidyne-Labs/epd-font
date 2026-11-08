# One-Click Windows Batch Workflows (`scripts/`) — `epd-font` v1.0.21

Each subdirectory under `scripts/` provides self-contained Windows `.bat` launchers (`00` through `07` and `99_run_full_pipeline.bat`) with zero hardcoded user paths and explicit `--hw-scheme` hardware configuration binding:

1. `scripts/h1os-build-distro/` — Builds the `H1OS` / `humid1-os` firmware font suite (`h1os_full.scheme.json` and `h1os_lite.scheme.json`) backed by `--hw-scheme esp32s3-N8R8-hw_scheme.json` into `build/h1os/` and packages `dist/epd-font_h1os_v1.0.21.zip`.
2. `scripts/example-build-distro/` — Builds the general-purpose embedded project template (`example.scheme.json`) backed by `--hw-scheme generic_hw.json` into `build/example/` and packages `dist/epd-font_example_v1.0.21.zip`.
3. `scripts/full-audit-build-distro/` — Runs the complete `10px - 40px` (`step size 2px`) visual audit across all fonts, icons, and all 9 resolution-reduction pipelines (`raw-unhinted`, `raw-hinted`, `svg-potrace`, `svg-potrace-jfa`, `mdf`, `msdf`, `sdf-smoothstep`, `adf-biquadratic`, `otsu-adaptive`) backed by `--hw-scheme esp32s3-N8R8-hw_scheme.json` into `build/audit/` and packages `dist/epd-font_audit_v1.0.21.zip`.
4. `scripts/font-eval-suite/` — Runs `humid1_font_eval.py` across all 9 resolution-reduction pipelines (`01_run_font_eval.bat` for `build/static_ttfs` and `02_run_font_eval.bat <custom_font_dir>` for external font collections) using `--hw-scheme esp32s3-N8R8-hw_scheme.json`.
5. `scripts/probe_hardware.py` & `scripts/check_PyOpenCL.py` — Multi-device OpenCL (`Ellesmere` 32 CUs + `AMD Ryzen 5 5600G` 12 CUs) & `75%` Shared GPU RAM (`CL_MEM_ALLOC_HOST_PTR`) diagnostic utilities.
