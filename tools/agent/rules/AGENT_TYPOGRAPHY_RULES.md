# Humidyne Labs / Humiditron `epd-font` v1.0.23 — Agent Typography & Iconography Rules

1. **Zero Guessing of Pixel Metrics**:
   - NEVER guess character advance widths, bounding boxes, line heights, or string pixel widths.
   - ALWAYS query via the global `embedded-ops` MCP tools (`epd_char_info`, `epd_string_budget`, `epd_audit_screens`) or `python tools/agent/tools/char_info.py` / `string_info.py` against the Strike Vault (`dist/*/humid1_epd_vault.json.gz`) or CSV manifests (`metrics/char_widths_*.csv`).
2. **Zero Guessing of Icon Codepoints or UTF-8 Bytes**:
   - NEVER fabricate Private Use Area (`0xE000..0xF8FF`) hex values or UTF-8 byte sequences.
   - ALWAYS look up exact icon names and C UTF-8 literals via `epd_icon_search` (or `python tools/agent/tools/icon_search.py --query <keyword>`).
3. **Strict `build/` and `dist/` Isolation**:
   - All generated static `.ttf` files (`build/static_ttfs/`), metadata catalogs (`build/metadata/`), and dumped ASCII glyph folders (`build/<workflow>/ascii_patches/`) MUST reside inside `build/`.
   - Hand-tuned pixel patches MUST be persisted in the root-tracked `font_icon_epd_patches.json` via `--workflow patch --apply` so `build/` and `dist/` remain cleanly gitignored.
4. **Sub-Family Pixel Size Floors**:
   - Respect minimum 1-bpp legibility floors: `sans` >= 10px (12px recommended; 14px minimum in H1OS display UI), `mono` >= 10px, `terminus` >= 12px (native 12/14/16/20/24/28/32px), `cond` >= 12px, `math` >= 14px, `serif` >= 16px, `icon_*` >= 12px.
