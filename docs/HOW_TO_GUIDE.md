# `epd-font` (`v0.0.6`) — Complete How-To Guide (Installation, Setup, Custom Schemes & Examples)

**Repository:** [Humidyne-Labs/epd-font](https://github.com/Humidyne-Labs/epd-font)  
**Target Firmware OS:** [Humidyne-Labs/H1OS](https://github.com/Humidyne-Labs/H1OS) & `humid1-os`

---

## 1. Environment Setup & Dependency Installation

### 1.1 Windows (Automated via `scripts\00_setup_env.bat`)
Double-click `scripts\00_setup_env.bat` in Windows Explorer, or run it from PowerShell / Command Prompt:
```bat
scripts\00_setup_env.bat
```
This script automatically creates a local `.venv` virtual environment at the repository root and installs:
- **`fonttools>=4.40.0`**: Instantiates [IBM Plex](https://github.com/IBM/plex) Variable TTFs and converts Font Awesome 7 CFF `.otf` files into quadratic TrueType `.ttf` files.
- **`Pillow>=10.0.0`**: Renders the Page Check PNG sheets, 18×–24× Char-by-Char Blueprint PNG cards, and 188-DPI master specimen sheet.
- **`freetype-py>=2.4.0`**: Bundles `libfreetype.dll` on Windows so `generate_plex_1bpp.py` can execute native `FT_LOAD_TARGET_MONO` 1-bit scanline conversion out of the box.

### 1.2 Linux (Ubuntu / Debian / WSL2) & macOS
```bash
# Ubuntu / Debian / WSL2:
sudo apt-get update && sudo apt-get install -y libfreetype6 python3 python3-venv python3-pip
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip "fonttools>=4.40.0" "Pillow>=10.0.0"

# macOS (Homebrew):
brew install freetype python
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip "fonttools>=4.40.0" "Pillow>=10.0.0"
```

*(Note: The downstream firmware emitter `plex_fw_emit.py` used inside `H1OS` requires **zero** external packages—it uses 100% pure Python 3 standard library and runs directly inside ESP-IDF's bundled Python environment).*

---

## 2. Step-by-Step Windows Batch Workflow (`scripts\`)

You never have to type long command-line arguments manually. Run the numbered scripts in `scripts\` in order:

1. **`scripts\01_build_static_ttfs.bat`**:
   - Scans `assets/` (`assets/font_assets/` and `assets/icon_assets/`) and populates `assets/static_ttfs/` with all **54 static `.ttf` fonts**, `licenses/`, and `metadata/*.json` icon catalogs (`fa7_catalog.json`, `lucide_catalog.json`, `phosphor_catalog.json`, `tabler_catalog.json`, `unified_icon_names.json`, `asset_manifest.json`).
2. **`scripts\02_build_h1os_fonts.bat`**:
   - Reads `tools/fonts/schemes/h1os_epd_scheme.json` and compiles all 68 strikes into `build/fonts/` (`.c` and `.h` files), `build/bdf/` (`.bdf` files), `build/metrics/` (`.csv` files), and `build/dist/plex_epd_vault.json.gz`.
3. **`scripts\03_visual_check_pngs.bat`**:
   - Renders Page Check sheets in `build/inspect_pages/<strike>.png`, Char-by-Char Blueprint cards in `build/inspect_chars/<strike>/U+XXXX_<name>.png`, the 188-DPI Specimen Sheet in `build/inspect_pages/plex_epd_specimen_188dpi.png`, and prints the 200×200 SSD1681 screen width audit.
4. **`scripts\04_dump_ascii_patches.bat`**:
   - Exports all strikes into `tools/fonts/ascii_patches/<strike>/U+XXXX_<name>.txt` as Full-Canvas 1:1 Spaced ASCII files.
5. **`scripts\05_apply_ascii_patches.bat`**:
   - Compiles any `.txt` files you edited in `tools/fonts/ascii_patches/` into `tools/fonts/plex_epd_patches.json` and immediately rebuilds `build/fonts/` and `plex_epd_vault.json.gz`.
6. **`scripts\07_package_h1os_deployment.bat`**:
   - Refreshes `dist/h1os_deployment/` and packages `dist/h1os_deployment.zip` for the `H1OS` repository.

---

## 3. Unified Python CLI Reference (1 Input Dir, 1 Output Dir)

All three Python tools in `tools/fonts/` use a clean, non-overlapping flag structure with a **single `--src-dir`** and a **single `--out-dir`**.

### 3.1 Tool 1: `build_static_ttf_assets.py` (Raw Assets → Static TTFs & Catalog JSONs)
```bash
# Default invocation (reads <repo>/assets, writes <repo>/assets/static_ttfs):
python tools/fonts/build_static_ttf_assets.py --verify

# Explicit single input dir and single output dir:
python tools/fonts/build_static_ttf_assets.py \
  --src-dir ./assets \
  --out-dir ./assets/static_ttfs \
  --force \
  --verify

# Rebuild only icon fonts (FA7, Lucide, Phosphor, Tabler):
python tools/fonts/build_static_ttf_assets.py --families icons --force --verify
```

### 3.2 Tool 2: `generate_plex_1bpp.py` (Static TTFs + Scheme → C Fonts, PNGs, ASCII, Vault)
`generate_plex_1bpp.py` takes a single `--src-dir` (default: `assets/static_ttfs`) and a single `--out-dir` (default: `build`), automatically organizing outputs into `build/fonts/`, `build/dist/`, `build/bdf/`, `build/metrics/`, `build/inspect_pages/`, and `build/inspect_chars/`:

```bash
# 1. Build C/H modules, BDFs, CSVs, and Strike Vault into ./build:
python tools/fonts/generate_plex_1bpp.py --workflow build

# 2. Render Page Check PNGs, Char-by-Char Blueprint PNGs, and 200x200 Screen Audit:
python tools/fonts/generate_plex_1bpp.py --workflow check

# 3. Render Char-by-Char Blueprint PNGs for EVERY glyph in 14px and 16px Sans & Lucide:
python tools/fonts/generate_plex_1bpp.py \
  --workflow check \
  --families sans icon_lucide \
  --sizes 14 16 \
  --inspect-chars-filter all

# 4. Dump Full-Canvas 1:1 Spaced ASCII .txt glyph files into tools/fonts/ascii_patches:
python tools/fonts/generate_plex_1bpp.py --workflow patch --dump

# 5. Compile edited ASCII .txt files into tools/fonts/plex_epd_patches.json:
python tools/fonts/generate_plex_1bpp.py --workflow patch --apply

# 6. Run the entire pipeline end-to-end with a custom scheme and output folder:
python tools/fonts/generate_plex_1bpp.py \
  --workflow all \
  --scheme tools/fonts/schemes/icons_modular_scheme.json \
  --src-dir assets/static_ttfs \
  --out-dir build_icons
```

### 3.3 Tool 3: `plex_fw_emit.py` (Zero-Dependency Firmware Emitter for `H1OS`)
```bash
python tools/fonts/plex_fw_emit.py \
  --scheme tools/fonts/schemes/h1os_epd_scheme.json \
  --vault dist/plex_epd_vault.json.gz \
  --ascii-dir tools/fonts/ascii_patches \
  --out-dir build/generated_fonts \
  --sizes 14 16 18 20 24 32
```

---

## 4. How Icon Scoping & Custom Icon Inclusion Works (`schemes/*.json`)

### 4.1 Where Are Available Icons Listed?
When `01_build_static_ttfs.bat` runs, it preserves **100% of upstream icons** inside the `.ttf` binaries in `assets/static_ttfs/` and generates 4 searchable catalog JSON files in `assets/static_ttfs/metadata/`:
- `fa7_catalog.json`: **2,396** Font Awesome v7.0.0 icons (`"battery-full": "0xF240"`, `"wifi": "0xF1EB"`, etc.)
- `lucide_catalog.json`: **2,043** Lucide v1.67.0 icons (`"battery-charging": "0xE054"`, `"thermometer": "0xE186"`, etc.)
- `phosphor_catalog.json`: **1,513** Phosphor v2.1.0 icons (`"battery-high": "0xE0C2"`, `"wind": "0xE4F2"`, etc.)
- `tabler_catalog.json`: **6,257** Tabler v3.50.0 Outline & Filled icons (`"temperature": "0xEB38"`, `"wifi": "0xEB52"`, etc.)

### 4.2 Three Ways to Scope Icons in `tools/fonts/schemes/*.json`
Inside any scheme file (such as `tools/fonts/schemes/h1os_epd_scheme.json`), each entry under `"character_sets"` can define which icons get compiled into C arrays using:

1. **By Human-Readable Icon Names (`"icons": [...]`) — Recommended**:
   Simply list the icon names from `metadata/<vendor>_catalog.json`:
   ```json
   "my_custom_lucide_icons": {
     "description": "Custom Lucide icon subset for H1OS status bar and sensor cards",
     "vendor": "icon_lucide",
     "icons": [
       "activity", "alert-triangle", "battery", "battery-charging", "battery-full",
       "battery-low", "battery-medium", "bell", "bluetooth", "bug", "check",
       "clock", "cloud", "cpu", "database", "droplet", "flame", "gauge",
       "hard-drive", "home", "info", "lock", "memory-stick", "microchip",
       "plug", "power", "qr-code", "radio", "refresh-cw", "satellite",
       "settings", "shield", "signal", "sliders-horizontal", "snowflake",
       "sun", "terminal", "thermometer", "timer", "trash-2", "unlock",
       "usb", "wifi", "wind", "wrench", "zap"
     ]
   }
   ```
2. **By Hexadecimal Codepoints or Ranges (`"ranges"`)**:
   ```json
   "my_hex_icons": {
     "vendor": "icon_fa7",
     "ranges": "0xF001,0xF00C,0xF011-0xF015,0xF240-0xF244"
   }
   ```
3. **Full Vendor Catalog (`"scope": "all"`)**:
   *(Warning: Compiling all 2,000+ icons of a vendor at 16px consumes ~60 KB of flash; use only for desktop catalog previews).*
   ```json
   "lucide_full_catalog": {
     "vendor": "icon_lucide",
     "scope": "all"
   }
   ```

---

## 5. Hand-Tuning Pixels in Notepad++ (`tools/fonts/ascii_patches/`)

1. Run `scripts\04_dump_ascii_patches.bat` to populate `tools/fonts/ascii_patches/<strike_symbol>/U+XXXX_<name>.txt`.
2. Open any glyph file in Notepad++ or VS Code (e.g., `tools/fonts/ascii_patches/plex_cond_bold_14/U+00B0_degree.txt`):
   ```text
   grid_mode: full_canvas
   canvas_x0: 0
   canvas_y_top: 15
   canvas_y_bot: -4
   adv_w_fp4: 95
   box_w: 5
   box_h: 5
   ofs_x: 1
   ofs_y: 5
   ---
   # x: 0 1 2 3 4 5
        . . . . . .  | y=+15 (ASCENDER)
        . . . . . .  | y=+14
        . . . . . .  | y=+13
        . . . . . .  | y=+12
        . . . . . .  | y=+11
        . . . . . .  | y=+10 (CAP_HEIGHT)
        . . # # # .  | y=+09
        . # # . # #  | y=+08
        . # # . # #  | y=+07 (X_HEIGHT)
        . # # . # #  | y=+06
        . . # # # .  | y=+05
        . . . . . .  | y=+04
        . . . . . .  | y=+03
        . . . . . .  | y=+02
        . . . . . .  | y=+01
        - - - - - -  | y=+00 <-- BASELINE (y=0)
   ```
3. Edit `# ` (ink ON) and `. ` (ink OFF) anywhere on the canvas and save the file. `box_w`, `box_h`, `ofs_x`, and `ofs_y` are recalculated automatically from your `#` positions.
4. Run `scripts\05_apply_ascii_patches.bat` to compile your edits into `tools/fonts/plex_epd_patches.json` and regenerate `build/fonts/` and `dist/plex_epd_vault.json.gz`.

---

## 6. Deploying to `H1OS` (`h1os_deployment.zip`)

The `h1os_deployment.zip` archive (also staged in `dist/h1os_deployment/`) is a turnkey drop-in for **[Humidyne-Labs/H1OS](https://github.com/Humidyne-Labs/H1OS)** (`components/h1os/`):
1. Extract `h1os_deployment.zip` into `H1OS/components/h1os/`.
2. It provides:
   - `CMakeLists.txt`: Drop-in replacement for `components/h1os/CMakeLists.txt` that invokes `tools/fonts/plex_fw_emit.py` during `idf.py build`.
   - `tools/fonts/plex_fw_emit.py`: Zero-dependency pure-Python emitter.
   - `tools/fonts/schemes/h1os_epd_scheme.json`: Declarative H1OS font & modular icon scheme.
   - `tools/fonts/dist/plex_epd_vault.json.gz`: Pre-rasterized, patch-baked Strike Vault.
   - `tools/fonts/LICENSES/`: All required upstream font & icon license files.
3. Run `idf.py build`. `plex_fw_emit.py` emits all C font modules, `plex_fonts.h`, and `h1os_fonts.h` into `${CMAKE_CURRENT_BINARY_DIR}/generated_fonts` in `< 0.15 seconds`.
