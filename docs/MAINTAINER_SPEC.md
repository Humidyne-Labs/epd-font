# Formal Typography & Maintainer Specification — `epd-font` (v1.0.8)

**Document ID**: `HUMIDITRON-SPEC-EPD-FONT-1.0.8`  
**Repository**: `https://github.com/Humidyne-Labs/epd-font`  
**License**: MIT License (Tooling & C Emitter) / SIL OFL 1.1 / CC-BY-4.0 / ISC / MIT (Upstream Fonts)

---

## 1. Architectural Overview

`epd-font` v1.0.8 separates raw upstream font curation (`assets/`), intermediate TrueType & metadata synthesis (`build/static_ttfs/` and `build/metadata/`), optical pixel-grid patching (`font_icon_epd_patches.json` + `build/<workflow>/ascii_patches/`), and zero-dependency firmware emission (`dist/<workflow>_distro/`).

### 1.1 Supported Typeface & Icon Families (56 Static `.ttf` Cuts)

| Family Key (`scheme.json`) | Upstream Source | Static `.ttf` Cuts (`build/static_ttfs/`) | Recommended 1-BPP Floor | License |
| :--- | :--- | :--- | :--- | :--- |
| `"sans"` | IBM Plex Sans v0.2.0 (`wdth=100`) | 13 cuts (`Thin 100` .. `Bold 700` + Italics) | `12 px` (`10 px` min) | SIL OFL 1.1 |
| `"cond"` | IBM Plex Sans Condensed (`wdth=85`) | 9 cuts (`Light 300` .. `Bold 700` + Italics) | `14 px` (`12 px` min) | SIL OFL 1.1 |
| `"mono"` | IBM Plex Mono v1.0.0 | 9 cuts (`Light 300` .. `Bold 700` + Italics) | `12 px` (`10 px` min) | SIL OFL 1.1 |
| `"serif"` | IBM Plex Serif v2.0.0 | 9 cuts (`Light 300` .. `Bold 700` + Italics) | `16 px` (`18 px` rec) | SIL OFL 1.1 |
| `"math"` | IBM Plex Math v1.1.0 | 1 cut (`IBMPlexMath-Regular.ttf`, 4,382 codepoints) | `14 px` (`16 px` rec) | SIL OFL 1.1 |
| `"terminus"` | Terminus Font v4.49.1 (`ter-u16n/b.bdf`) | 2 cuts (`Terminus-Regular.ttf`, `Terminus-Bold.ttf`, 1,356 glyphs) | `12 px` (native 12–32px) | SIL OFL 1.1 |
| `"icon_fa7"` | Font Awesome Free v7.3.1 | 3 cuts (`Solid`, `Regular`, `Brands` — 2,396 icons) | `12 px` (`14 px` rec) | CC-BY-4.0 / OFL-1.1 |
| `"icon_lucide"` | Lucide Icons v1.16.0 | 1 cut (`Lucide-Regular.ttf` — 2,043 icons) | `12 px` (`14 px` rec) | ISC |
| `"icon_phosphor"` | Phosphor Icons v2.1.0 | 5 cuts (`Thin`, `Light`, `Regular`, `Bold`, `Fill` — 1,513 icons) | `12 px` (`14 px` rec) | MIT |
| `"icon_tabler"` | Tabler Icons v3.41.1 | 4 cuts (`Thin200`, `Light300`, `Regular`, `Filled` — 6,257 icons) | `12 px` (`14 px` rec) | MIT |

---

## 2. PUA Sanitization & Semantic Glyph Naming (`Phosphor-*.ttf`)

Upstream `Phosphor*.ttf` binaries include 30 zero-width (`0×0` bounding box, `0` advance width) ASCII characters (`0x0020..0x007A`, including `0x0069 'i'`) in their `cmap` table to act as OpenType `GSUB` ligature anchors on desktop platforms, while storing all `1,513` real icons in the Private Use Area (`0xE000..0xEE83`) under generic `uniE000` glyph names.

In `v1.0.8`, `build_static_ttf_assets.py` enforces two invariants on all icon `.ttf` binaries:
1. **Non-PUA Ligature Stub Stripping (`strip_non_pua=True`)**: All `cmap` entries with `cp < 0xE000` are stripped from icon `.ttf` binaries during static asset compilation.
2. **Self-Describing Semantic Glyph Names**: `build_static_ttf_assets.py` reads `assets/icon_assets/phosphor_icons_v2.1.0/metadata/selection.json` and bakes the human-readable icon names (`"alarm"`, `"wifi-high"`, `"battery-full"`) directly into the `glyf`, `hmtx`, `cmap`, and `post` tables of every `Phosphor-*.ttf` binary as well as `build/metadata/phosphor_catalog.json`.

---

## 3. Terminus v4.49.1 BDF-to-TTF Synthesis

To provide an ultra-crisp terminal/console font alongside IBM Plex while maintaining a 100% unified TrueType (`.ttf`) pipeline, `build_static_ttf_assets.py` extracts `ter-u16n.bdf` and `ter-u16b.bdf` from `assets/font_assets/terminus-font-4.49.1.tar.gz` and converts every horizontal pixel run into an exact clockwise quadratic TrueType contour (`UPEM = 1024`, `scale = 64 font units/pixel`, `ascent = +768`, `descent = -256`). When `humid1_generate_1bpp.py` rasterizes `"family": "terminus"`, it automatically selects `bytecode-mono` (unhinted exact grid sampling) so `12, 14, 16, 18, 20, 24, 28, 32` px strikes reproduce bit-exact pixel geometry.
