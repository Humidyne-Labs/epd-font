---
name: icon-catalog-search
description: Search 12,200+ icons across Font Awesome 7, Lucide, Phosphor, and Tabler and generate C UTF-8 macros using icon_search.py.
---
# Multi-Vendor Icon Catalog Search (`icon_search.py`)

Never guess Private Use Area (PUA) hex codepoints (`0xE000..0xF8FF`) or UTF-8 byte sequences for icons. Always query `build/metadata/unified_icon_names.json` via `icon_search.py`.

## Usage
```bash
# Search all 4 icon vendors by keyword:
python tools/agent/tools/icon_search.py --query "battery"

# Filter to a single vendor (icon_phosphor, icon_lucide, icon_fa7, icon_tabler):
python tools/agent/tools/icon_search.py --query "wifi" --vendor icon_phosphor --json
```
