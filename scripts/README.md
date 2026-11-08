# One-Click Windows Batch Workflows (`scripts/`) — `epd-font` v1.0.20

Each subdirectory under `scripts/` provides self-contained Windows `.bat` launchers (`00` through `07` and `99_run_full_pipeline.bat`) with zero hardcoded user paths:

1. `scripts/h1os-build-distro/` — Builds the `H1OS` / `humid1-os` firmware font suite (`h1os_full.scheme.json` and `h1os_lite.scheme.json`) into `build/h1os/` and packages `dist/epd-font_h1os_v1.0.20.zip`.
2. `scripts/example-build-distro/` — Builds the general-purpose embedded project template (`example.scheme.json`) into `build/example/` and packages `dist/epd-font_example_v1.0.20.zip`.
3. `scripts/full-audit-build-distro/` — Runs the complete `10px - 40px` (`step size 2px`) visual audit across all fonts, icons, and all 8 resolution-reduction pipelines into `build/audit/` and packages `dist/epd-font_audit_v1.0.20.zip`.
4. `scripts/font-eval-suite/` — Runs `humid1_font_eval.py` across all 8 resolution-reduction pipelines (`01_run_font_eval.bat` for `build/static_ttfs` and `02_run_font_eval.bat <custom_font_dir>` for external font collections).
