# Humidyne Labs / Humiditron `epd-font` v1.0.17 — Agent Typography & Iconography Rules

1. **Zero Guessing of Pixel Metrics**:
   - NEVER guess character advance widths, bounding boxes, line heights, or string pixel widths.
   - ALWAYS run `python tools/agent/tools/char_info.py` or `python tools/agent/tools/string_info.py` against the compiled Strike Vault (`dist/*/humid1_epd_vault.json.gz`).
2. **Zero Guessing of Icon Codepoints or UTF-8 Bytes**:
   - NEVER fabricate Private Use Area (`0xE000..0xF8FF`) hex values or UTF-8 `î` sequences.
   - ALWAYS look up exact icon names and C UTF-8 literals via `python tools/agent/tools/icon_search.py --query <keyword>`.
3. **Strict `build/` and `dist/` Isolation**:
   - All generated static `.ttf` files (`build/static_ttfs/`), metadata catalogs (`build/metadata/`), and dumped ASCII glyph folders (`build/<workflow>/ascii_patches/`) MUST reside inside `build/`.
   - Hand-tuned pixel patches MUST be persisted in the root-tracked `font_icon_epd_patches.json` via `--workflow patch --apply` so `build/` and `dist/` remain cleanly gitignored.
4. **Sub-Family Pixel Size Floors**:
   - Respect minimum 1-bpp legibility floors: `sans` >= 10px (12px recommended), `mono` >= 10px, `terminus` >= 12px (native 12/14/16/20/24/28/32px), `cond` >= 12px, `math` >= 14px, `serif` >= 16px, `icon_*` >= 12px.
