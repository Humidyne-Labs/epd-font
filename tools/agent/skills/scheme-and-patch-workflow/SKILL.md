---
name: scheme-and-patch-workflow
description: Customize declarative JSON font schemes, dump/apply Full-Canvas 1:1 ASCII patches, and build dist bundles.
---
# Declarative JSON Scheme & Root Patch Workflow

1. **Inventory Available Fonts & Schemes**:
   ```bash
   python tools/agent/tools/font_catalog_info.py
   ```
2. **Build Static TTFs & Metadata into `build/`**:
   ```bash
   python tools/fonts/build_static_ttf_assets.py --verify
   ```
3. **Dump Editable 1:1 ASCII Patches into `build/<target>/ascii_patches/`**:
   ```bash
   python tools/fonts/generate_plex_1bpp.py --workflow patch --dump --scheme tools/fonts/schemes/humid1_reference.scheme.json --out-dir build/default
   ```
4. **Compile Modified ASCII Patches into Root `epd_font_patches.json`**:
   ```bash
   python tools/fonts/generate_plex_1bpp.py --workflow patch --apply --ascii-dir build/default/ascii_patches --patches epd_font_patches.json
   ```
