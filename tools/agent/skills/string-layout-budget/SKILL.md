---
name: string-layout-budget
description: Compute exact LVGL 1-bpp pixel widths, kerning adjustments, and horizontal screen budget clearance using string_info.py.
---
# String Layout & Screen Width Budget Calculator (`string_info.py`)

Never estimate string widths by multiplying character count by an average width. Always run `string_info.py` to compute exact LVGL `fp4` kerning-aware pixel widths and screen clearance.

## Usage
```bash
# Measure a single label against a 200px screen (6px safe margins = 188px usable budget):
python tools/agent/tools/string_info.py --strike humid1_font_plex_sans_bold_16 --text "ENVIRONMENTAL TELEMETRY"

# Audit a two-column (left label + right telemetry value) row on a custom display:
python tools/agent/tools/string_info.py --strike humid1_font_plex_sans_normal_14 --text "Vapor Pressure" \
  --right-text "42.8 hPa" --right-strike humid1_font_plex_mono_bold_14 --screen-width 200 --safe-margin 6
```
