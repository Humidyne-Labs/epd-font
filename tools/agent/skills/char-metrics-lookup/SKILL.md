---
name: char-metrics-lookup
description: Query exact 1-bpp character or icon metrics, bounding boxes, C UTF-8 literals, and ASCII bitmaps using char_info.py.
---
# Character & Icon Metric Lookup (`char_info.py`)

Never guess the pixel width, height, bearing offset (`ofs_x`, `ofs_y`), or bitmap appearance of any glyph.

## Usage
```bash
# Inspect an ASCII or scientific character in a specific strike:
python tools/agent/tools/char_info.py --strike humid1_font_plex_sans_normal_14 --char "@"

# Inspect a semantic icon in a Phosphor, Lucide, FA7, or Tabler strike:
python tools/agent/tools/char_info.py --strike humid1_icon_phosphor_fill_20 --char "alarm"

# Emit structured JSON for automated layout parsing:
python tools/agent/tools/char_info.py --strike humid1_font_terminus_normal_16 --char "A" --json
```
