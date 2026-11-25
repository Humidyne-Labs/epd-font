# One-Click Windows Batch Workflows (`scripts/`) — `epd-font` v1.0.23

See [docs/WORKFLOW_AND_SCRIPT_CATALOG.md](../docs/WORKFLOW_AND_SCRIPT_CATALOG.md) for the full 5-workflow specification and module inventory.

All suites share [scripts/ensure_local_vlm_server.ps1](file:///C:/Users/Matt/Documents/GitHub/epd-font/scripts/ensure_local_vlm_server.ps1) inside `00_setup_env.bat` so the local `llama-server` VLM endpoint (`http://127.0.0.1:8090/v1/models`) is verified or auto-started before downstream steps run:

1. **`scripts/h1os-build-distro-v1/`** (`00`–`10` + `99`) — **H1OS v1 (Baseline):** `IBM Plex + Noto + Terminus` -> `build/h1os_v1/` -> `dist/epd-font_h1os_v1_v1.0.23.zip`.
2. **`scripts/h1os-build-distro-v2/`** (`00`–`10` + `99`) — **H1OS v2 (20 cm Natural):** `FiraSans + InterTight + FiraSansCondensed (wght=700) + JetBrainsMono + FiraCode + Bitter + Terminus` -> `build/h1os_v2/` -> `dist/epd-font_h1os_v2_v1.0.23.zip`.
3. **`scripts/h1os-build-distro-v3/`** (`00`–`10` + `99`) — **H1OS v3 (4-Round Funnel + Adams Adoption + Micro-Tuned + VLM Patched):** `01_select_v3_tournament_fonts.bat` auto-runs triage if needed, crowning `adams_six` UI + `adams_mono_one` Mono -> `build/h1os_v3/` -> `dist/epd-font_h1os_v3_v1.0.23.zip`.
4. **`scripts/font-eval-suite/`** (`00`–`03` + `99`) — **Evaluation & Tournament Only (No Distro):** Extract bench fonts (`01`), run Rounds 0–2 Good-Apple triage & dynamic Adams adoption (`02`), and run Round 3 OpenType + 9-pipeline Big Fish tournament (`03`).
5. **`scripts/font-audit-suite/`** (`00`–`03` + `99`) — **Read-Only Font Audit (No Distro):** Complete `10px–40px` (`step=2px`) 9-pipeline comparison sheets and VLM vision audit into `build/audit/`.
6. **`scripts/example-build-distro/`** — General-purpose embedded project template (`generic_hw.json`) -> `build/example/` -> `dist/epd-font_example_v1.0.23.zip`.
7. **`scripts/probe_hardware.py` & `scripts/check_PyOpenCL.py`** — Multi-device OpenCL & Shared GPU RAM diagnostic utilities.
