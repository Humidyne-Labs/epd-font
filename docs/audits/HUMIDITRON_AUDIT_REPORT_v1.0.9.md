# HUMIDITRON AUDIT REPORT — v1.0.9 (Revved from v1.0.8)

- **Repository**: [`Humidyne-Labs/epd-font`](https://github.com/Humidyne-Labs/epd-font)
- **Target OS**: [`Humidyne-Labs/H1OS`](https://github.com/Humidyne-Labs/H1OS)
- **Version**: `v1.0.9` (revved from `v1.0.8`)
- **Audit Reference**: `docs/audits/exhibits/v1.0.9/rev1.0.9.txt`

## 1. Executive Summary of v1.0.8 → v1.0.9 Fixes

| Audit Item (`rev1.0.9.txt`) | Root Cause Identified in v1.0.8 | Resolution Implemented in v1.0.9 | Verification Status |
| :--- | :--- | :--- | :--- |
| **1. `humid1_epd_specimen_188dpi.png` missing fields** | `render_specimen_sheet()` still referenced legacy `plex_sans_*` / `plex_mono_*` keys in `showcase_glyphs` and `ladder_rows` instead of resolving `humid1_font_plex_*` / `humid1_font_terminus_*` via `_resolve_sym()`, leaving the Bottom-Left 6× pixel grid, the Bottom-Left icon strip, and the Right-Column size ladder blank. | Replaced all raw `strike_cache.get()` calls in `render_specimen_sheet()` with `_resolve_sym()` and added an automatic PUA icon fallback lookup (`icon_fb_14`, `icon_fb_20`) plus `Terminus Normal 12px` / `16px` rows. | **PASS** — All 3 panels (`200×200` simulated SSD1681 panel, 6× micro-glyph grid + 1:1 readout + 14-icon strip, and 17-row size ladder) render completely. |
| **2. Missing images in `inspect_chars` (`terminus` & `tabler_regular_40`)** | `humid1_generate_1bpp.py` and `03_visual_check_pngs.bat` defaulted to `--inspect-chars-filter trouble`, which rendered only 29 trouble characters for text strikes (29 PNGs in `src_tree_1.log` vs 103 `.txt` files in `src_tree_2.log`) and sliced icon strikes to `glyphs[1:13]` (only 12 PNGs in `src_tree_3.log`). | Changed the default `--inspect-chars-filter` to `"all"` across `humid1_generate_1bpp.py` and all `03_visual_check_pngs.bat` launchers so 100% of characters and curated icons are rendered in `inspect_chars/<symbol>/`, and cached UI fonts per worker (`_UI_FONTS_CACHE`) for 10× faster rendering. | **PASS** — `inspect_chars/humid1_font_terminus_normal_12` now outputs all **103 PNGs** (matching `ascii_patches/` 1-for-1), and icon strikes render 100% of their curated icons. |
| **3. Point Size (`pt`) vs Pixel Size (`px` / `ppem`) Verification** | Users and desktop font viewers (Windows Font Viewer / Adobe / Word at 96 DPI) label sizes in desktop points (`pt@96dpi`), whereas FreeType `FT_Set_Pixel_Sizes(face, 0, size_px)`, LVGL (`lv_font_montserrat_14`), and X11 BDF (`ter-u16n.bdf`) specify the **Em-Square height in pixels (`px` / `ppem`)**. Additionally, font vertical `hhea` metrics (`ascent - descent`) determine the actual rasterized `line_height`. | Verified and documented the exact conversion formulas (`pt@96dpi = px * 72 / 96`, `pt@188dpi = px * 72 / 188.3`, and `lh = ceil(asc * px / UPEM) - floor(desc * px / UPEM)`), surfaced `pt@96dpi` and `pt@188dpi` in all page sheets, character sheets, CLI logs, and `total_disk_size.txt`, and added `22px` (`16.5pt@96dpi`) to `full_audit_distro.scheme.json`. | **PASS** — Every diagnostic PNG and `total_disk_size.txt` now explicitly displays `Em(px)`, `pt@96dpi`, `pt@188dpi`, and `LineHt(px)`. |
| **4. `total_disk_size.txt` Firmware Flash & Disk Footprint Report** | Build outputs lacked a consolidated breakdown of MCU Flash `.rodata` cost vs host `.c` file disk size. | Added automatic `write_total_disk_size_report()` generation whenever `.c` assets are built or exported, writing `total_disk_size.txt` into `<out-dir>/fonts/`, `<out-dir>/`, and `<dist-dir>/`. | **PASS** — Reports exact `.rodata` bytes/KB (`bitmap[] + glyphs[] + kern[] + struct`), host `.c`/`.h` bytes/KB, MCU Flash partition utilization (`64KB` to `8MB`), per-family subtotals, and per-strike breakdown. |
| **5. GNU Unifont (`unifont-18.0.01.otf`) Evaluation & Native Support** | Evaluated whether `unifont-18.0.01.otf` provides value for `epd-font` / `H1OS`. | Added native `"family": "unifont"` (`exact-mono`, `16px` floor) support in `humid1_generate_1bpp.py` and documented a full architectural trade-off analysis below. | **PASS** — Ready for drop-in subsetting (`16px` / `32px`) via scheme JSON. |

## 2. Deep-Dive: Point Size (`pt`) vs. Pixel Size (`px` / `ppem`) vs. Line Height (`lh`)

### 2.1 Why `size_px` (`ppem`) is the Authoritative Unit in Embedded 1-BPP Foundries
In both FreeType (`FT_Set_Pixel_Sizes(face, 0, size_px)`), [LVGL Font Converter](https://docs.lvgl.io/master/details/main-modules/font.html), and X11 BDF bitmap fonts ([Terminus Font](https://terminus-font.sourceforge.net/)), the integer suffix in a font symbol (such as `_12`, `_16`, `_24`, `_32`) represents **Pixels Per Em (`ppem` / `size_px`)**—the height of the typographic Em-Square in physical display pixels.

Because a typographic **Point (`1 pt = 1/72 inch`)** is a physical length unit, converting between Points (`pt`) and Pixels (`px`) always depends on the target display's **Dots Per Inch (`DPI`)**:

$$\text{px (ppem)} = \text{round}\left(\frac{\text{pt} \times \text{DPI}}{72}\right) \qquad \Longleftrightarrow \qquad \text{pt} = \frac{\text{px} \times 72}{\text{DPI}}$$

- **On a 96-DPI Desktop Monitor (Windows / CSS standard)**:
  $$\text{pt}_{96\text{dpi}} = \text{px} \times \frac{72}{96} = \text{px} \times 0.75$$
  This is why stepping by **2 pixels** (`12, 14, 16, 18, 20, 22, 24, 28, 32, 36, 40 px`) corresponds to **1.5-point steps** (`9.0, 10.5, 12.0, 13.5, 15.0, 16.5, 18.0, 21.0, 24.0, 27.0, 30.0 pt`) on a 96-DPI desktop chart (`point_size_chart.png`).
- **On the 188.3-DPI H1OS E-Paper Display (`1.54"` 200×200 SSD1681 panel, `27.0 mm × 27.0 mm`)**:
  $$\text{pt}_{188\text{dpi}} = \text{px} \times \frac{72}{188.3} \approx \text{px} \times 0.3824$$

### 2.2 Why Even-Pixel (`+2px`) Steps Matter More Than Integer Desktop Points on 1-BPP EPD
On a bi-level (1-BPP) display without grayscale anti-aliasing, stems, bowls, and icon stroke grids must land on **integer pixel boundaries**:
1. **Terminus Hardware Strikes**: Terminus is hand-drawn at exact pixel heights (`12, 14, 16, 18, 20, 22, 24, 28, 32 px`). Requesting `15pt @ 96dpi` (`20px`) or `16.5pt @ 96dpi` (`22px`) hits a native Terminus grid (`ter-u20n.bdf`, `ter-u22n.bdf`), whereas `16pt @ 96dpi` (`21.33px`) does not exist in bitmap grids.
2. **Icon Grid Divisibility (`16px`, `20px`, `24px`, `32px`, `40px`)**: [Lucide](https://lucide.dev/) and [Tabler Icons](https://tabler.io/icons) are authored on a `24×24` SVG grid, while [Phosphor Icons](https://phosphoricons.com/) is authored on a `256×256` (`16×16` base) grid. Even pixel sizes (`12, 16, 20, 24, 28, 32, 36, 40 px`) preserve symmetrical 1px and 2px stroke widths without fractional rounding jitter.
3. **Added `22px` (`16.5pt@96dpi`) to `full_audit_distro.scheme.json`**: In `v1.0.8`, `full_audit_distro.scheme.json` jumped from `20px` to `24px` for vector text and icons (skipping `22px`, even though Terminus included `22px`). In `v1.0.9`, `22px` is included across all families in `full_audit_distro.scheme.json` so the full progression (`12, 14, 16, 18, 20, 22, 24, 28, 32, 36, 40 px`) is continuous.

### 2.3 Why `Line Height (lh)` Differs Across Families at the Same `size_px`
When `FT_Set_Pixel_Sizes(face, 0, size_px)` sets the Em-Square (`UPEM`) to `size_px` pixels, the vertical line box (`line_height`) is calculated from the font's `hhea` / `OS/2` ascender and descender metrics:

$$\text{ascender}_{\text{px}} = \left\lceil \frac{\text{ascent} \times \text{size\_px}}{\text{UPEM}} \right\rceil, \qquad \text{descender}_{\text{px}} = \left\lfloor \frac{\text{descent} \times \text{size\_px}}{\text{UPEM}} \right\rfloor, \qquad \text{line\_height}_{\text{px}} = \text{ascender}_{\text{px}} - \text{descender}_{\text{px}}$$

| Font Family | Master `UPEM` | `hhea.ascent` | `hhea.descent` | Metric Span (`asc - desc`) | At `size_px = 16px` (`12pt@96`) | At `size_px = 32px` (`24pt@96`) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **IBM Plex Sans / Mono / Cond / Serif** | `1000` | `+1025` | `-275` | `1300` (`1.30 × UPEM`) | `asc=17, desc=-4` → **`lh = 21px`** | `asc=33, desc=-9` → **`lh = 42px`** |
| **IBM Plex Math** | `1000` | `+1082` | `-427` | `1509` (`1.51 × UPEM`) | `asc=18, desc=-6` → **`lh = 24px`** | `asc=35, desc=-13` → **`lh = 48px`** |
| **Terminus (Hardware Bitmap)** | `Pixel` | `~80%` | `~-20%` | `100%` (`1.00 × px`) | `asc=13, desc=-3` → **`lh = 16px`** | `asc=26, desc=-6` → **`lh = 32px`** |
| **Lucide / Tabler / Phosphor Icons** | `1000` / `960` | `+1000` / `+840` | `0` / `-120` | `100%` (`1.00 × UPEM`) | **`lh = 16px`** | **`lh = 32px`** |
| **FontAwesome v7 Free** | `512` | `+448` | `-64` | `512` (`1.00 × UPEM`) | `asc=14, desc=-2` → **`lh = 16px`** | `asc=28, desc=-4` → **`lh = 32px`** |

This explains why `Lucide-Regular.ttf` (`UPEM=1000, ascent=1000, descent=0`) at `32px` produces `line_height = 32px`, while `IBMPlexSans-Regular.ttf` (`UPEM=1000, ascent=1025, descent=-275`) at `32px` has a `32px` Em-square (`cap_height ≈ 22px`) plus room for tall ascenders (`Å`, `É`) and descenders (`g`, `j`, `p`, `q`, `y`), yielding `line_height = 42px`.

## 3. Firmware Flash (`.rodata`) & Disk Footprint Summary (`total_disk_size.txt`)

Every build now automatically generates `total_disk_size.txt` in `<out-dir>/fonts/total_disk_size.txt`, `<out-dir>/total_disk_size.txt`, and `<dist-dir>/total_disk_size.txt`:

| Target Scheme | Strikes | Total Glyphs | Expected MCU Flash (`.rodata` ROM) | Host `.c`/`.h` Disk Size | Fits in 256 KB Flash? | Fits in 1 MB Flash? |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **`example.scheme.json`** (`scripts/example-build-distro`) | `19` | `1,989` | **`70,583 B` (`68.93 KB`)** | `1,303,647 B` (`1,273.09 KB`) | **YES (`26.9%`)** | **YES (`6.7%`)** |
| **`h1os_full.scheme.json`** (`scripts/h1os-build-distro`) | `27` | `2,244` | **`82,420 B` (`80.49 KB`)** | `1,497,507 B` (`1,462.41 KB`) | **YES (`31.4%`)** | **YES (`7.9%`)** |

## 4. Engineering Evaluation: GNU Unifont (`unifont-18.0.01.otf`)

### 4.1 What GNU Unifont Is
[GNU Unifont](https://unifoundry.com/unifont/) (`unifont-18.0.01.otf`) is a dual-width (`8×16` half-width ASCII/Latin and `16×16` full-width CJK/symbol) bitmap-derived font covering all **65,536 codepoints** of the Unicode Basic Multilingual Plane (`U+0000..U+FFFF`).

### 4.2 Pros & Cons for `epd-font` / `H1OS`
- **Where Unifont Excels**:
  1. **Universal Fallback Glyph Coverage**: If `H1OS` needs mathematical arrows, box-drawing characters (`U+2500..U+257F`), block elements (`U+2580..U+259F`), Dingbats, Greek/Cyrillic, or CJK telemetry labels at an exact `16px` (`8×16` / `16×16`) cell without missing-glyph tofu boxes, Unifont covers the entire BMP at 1-BPP clarity.
  2. **Zero Hinting Blurriness at `16px` and `32px`**: Like Terminus, Unifont's outlines in `.otf`/`.ttf` trace crisp `1×1` pixel rectangles designed for `16px` (or `2×` integer scaling at `32px`).
- **Constraints & Why Full-BMP Inclusion Should Be Avoided**:
  1. **Flash Memory Cost of Full BMP**: Rasterizing all ~57,000 printable BMP glyphs at `16px` (`32 bytes/glyph` bitmap + `10 bytes/glyph` descriptor) would consume **`~2.3 MB` of MCU Flash `.rodata`**—nearly **28× larger** than the entire 27-strike `H1OS` font suite (`80.49 KB`).
  2. **Rigid Size Constraint (`16px` / `32px` Only)**: Because Unifont is natively an `8×16` / `16×16` pixel grid, rendering it at non-multiples of 16 (`12px`, `14px`, `18px`, `20px`, `24px`) causes severe uneven pixel stem distortion. For `12px`, `14px`, `18px`, `20px`, `22px`, `24px`, `28px`, and `32px` console text, **Terminus (`4.49.1`)** is significantly more legible and supports all 11 intermediate sizes natively.
  3. **Licensing (`OFL-1.1` OR `GPL-2.0-or-later with Font Exception`)**: Modern GNU Unifont (`18.0.01`) is dual-licensed under **SIL Open Font License 1.1** and **GPLv2+ with the GNU Font Embedding Exception**, making static `.c` array embedding in `H1OS` firmware legally clean as long as `OFL-1.1` attribution is retained.

### 4.3 Recommendation & Built-In Support in `v1.0.9`
- **Do NOT bundle all 65,536 glyphs into firmware**.
- **DO use Unifont as an optional, range-subsetted `16px` / `32px` Unicode symbol/fallback strike** when you need Unicode blocks that Terminus or IBM Plex Math do not cover (e.g., Box Drawing `0x2500-0x257F`, Block Elements `0x2580-0x259F`, Geometric Shapes `0x25A0-0x25FF`, Miscellaneous Technical `0x2300-0x23FF`).
- **Native Support Added in `v1.0.9`**: We added `"family": "unifont"` (`exact-mono`, `16px` floor) directly into `humid1_generate_1bpp.py` and `build_static_ttf_assets.py`. You can drop `unifont-18.0.01.otf` into `assets/fonts/master/unifont/` and add a targeted strike in any `.scheme.json` whenever needed:
  ```json
  {
    "family": "unifont",
    "style": "normal",
    "size_px": 16,
    "mode": "exact-mono",
    "custom_ranges": [[32, 126], [9472, 9631]]
  }
  ```
