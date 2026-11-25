# EPD Bi-Level Typography System — Master Specification (Rev 1.1)

| Field | Specification |
| --- | --- |
| **Document ID** | `SPEC-EPD-FONT-001` (`Rev 1.1` — Optical-Floor Proportional Scaling) |
| **Target Display Class** | Electrophoretic Display (EPD), 1-bit bi-level monochrome (`0` = white/background, `1` = black/ink) |
| **Size Envelope** | `12 px` – `40 px` PPEM (Pixels Per EM) |
| **Master Source Format** | Unified Font Object 3 (`UFO 3`) + OpenType `DesignSpace 5.1` XML |
| **Build Orchestration** | Declarative YAML/TOML configuration manifests + `gftools-builder` / `fontmake` |
| **Output Artifacts** | `BDF 2.1`, `PBM` (`P1`/`P4`), Packed C Arrays (`.c`/`.h`), Per-Variant Visual Proofs & Pass/Fail Audit Reports |

---

## 1. Target Application & Optical Constraints (EPD)

Electrophoretic displays impose physical and optical constraints that standard desktop or OLED font pipelines violate:

1. **Zero Hardware Anti-Aliasing:** Each EPD pixel is strictly binary (`1-bit`). Grayscale subpixel edge smoothing is unavailable; outlines are quantized via FreeType's monochrome scan-converter (`FT_LOAD_TARGET_MONO`), where a pixel activates only when its center falls within the glyph contour (subject to dropout-control rules).
2. **Optical Scattering & Ink Spread:** Microcapsule EPD frontplanes exhibit lateral optical point-spread scattering between the active ink layer and the protective top sheet. Single-pixel (`1 px`) vertical stems suffer severe contrast loss and visual fragmentation at a `20 cm` reading distance.
3. **Optical-Floor Proportional Scaling Law:**
* **Optical Floor Regime (`12 px – 18 px`):** Below `18 px`, natural typographic stem ratios drop below `2 px` (for Normal) and `3 px` (for Bold). In this zone, the `opsz` (Optical Size) and `wght` axes clamp stems to hard minimums of **`2 px` (`normal` / `italic`)** and **`3 px` (`bold` / `bold-italic`)**.
* **Proportional Scaling Regime (`18 px – 40 px`):** Once natural stroke thickness clears the optical floor (`>= 18 px`), vertical stems scale linearly with PPEM (`~11%` of PPEM for Normal/Italic; `~17%` of PPEM for Bold) so larger display sizes retain authentic typographic weight and visual hierarchy.

4. **Counter & Aperture Preservation:** Increasing stroke weight at small PPEMs (`12 px – 16 px`) risks closing internal negative spaces (counters in `e`, `a`, `s`, `o`, `α`, `θ`, `Ω`). Horizontal crossbars must remain thinner than vertical stems at low PPEMs (`1 px` minimum) so internal counters preserve at least a `1 px` open gap.

---

## 2. Typography Matrix, Stem Schedule & Acceptance Gates

### 2.1 Style & Modifier Matrix

| Variant ID | Style / Modifier | Size Range (PPEM) | Vertical Stem Rule | Width / Proportion |
| --- | --- | --- | --- | --- |
| `normal` | Upright Regular | `12 px – 40 px` | $\max(2,\; \text{round}(0.11 \times P))\text{ px}$ | Proportional Grotesk / Sans |
| `italic` | Slanted / True Italic | `12 px – 40 px` | $\max(2,\; \text{round}(0.11 \times P))\text{ px}$ | Proportional (`-10°` to `-12°` slant) |
| `bold` | Upright Bold | `12 px – 40 px` | $\max(3,\; S_{\text{norm}}(P) + 1,\; \text{round}(0.17 \times P))\text{ px}$ | Proportional Grotesk / Sans |
| `bold-italic` | Slanted / True Bold Italic | `12 px – 40 px` | $\max(3,\; S_{\text{norm}}(P) + 1,\; \text{round}(0.17 \times P))\text{ px}$ | Proportional (`-10°` to `-12°` slant) |
| `mono` | Fixed-Pitch (`normal`, `bold`, `italic`) | `12 px – 40 px` | Matches `normal` (`>= 2 px`) / `bold` (`>= 3 px`) schedule | Strict uniform advance width (`DWIDTH` constant) |
| `condensed` | Narrow Width (`normal`, `bold`, `italic`) | `12 px – 40 px` | Matches `normal` (`>= 2 px`) / `bold` (`>= 3 px`) schedule | `75% – 82%` of normal advance width |

### 2.2 Per-PPEM Stem Progression Schedule

| PPEM ($P$) | Regime | Normal / Italic Vertical Stem | Normal Horizontal Bar | Bold / Bold-Italic Vertical Stem | Bold Horizontal Bar | Min Bold–Normal Delta ($\Delta$) |
| --- | --- | --- | --- | --- | --- | --- |
| **`12 px`** | Optical Floor Clamped | **`2 px`** *(floor)* | `1 px` | **`3 px`** *(floor)* | `2 px` | `+1 px` |
| **`14 px`** | Optical Floor Clamped | **`2 px`** *(floor)* | `1 px` | **`3 px`** *(floor)* | `2 px` | `+1 px` |
| **`16 px`** | Optical Floor Clamped | **`2 px`** *(floor)* | `1 px` | **`3 px`** *(floor)* | `2 px` | `+1 px` |
| **`18 px`** | Crossover / Natural | **`2 px`** | `2 px` | **`3 px`** | `2 px` | `+1 px` |
| **`20 px`** | Proportional Scaling | **`2 px`** | `2 px` | **`3 px`** | `2–3 px` | `+1 px` |
| **`24 px`** | Proportional Scaling | **`3 px`** | `2 px` | **`4 px`** | `3 px` | `+1 px` |
| **`28 px`** | Proportional Scaling | **`3 px`** | `2–3 px` | **`5 px`** | `3–4 px` | `+2 px` |
| **`32 px`** | Proportional Scaling | **`4 px`** | `3 px` | **`5 px`** | `4 px` | `+1 px` |
| **`36 px`** | Proportional Scaling | **`4 px`** | `3 px` | **`6 px`** | `4–5 px` | `+2 px` |
| **`40 px`** | Proportional Scaling | **`4 px`** | `3–4 px` | **`7 px`** | `5 px` | `+3 px` |

### 2.3 Mandatory Unicode Coverage

Every compiled font instance must include complete, harmonized glyph coverage across the following blocks:

* **Basic Latin & Latin-1 Supplement (`U+0020–U+00FF`):** Printable ASCII, degree (`°`), plus-minus (`±`), micro (`µ`), middle dot (`·`), multiplication/division (`×`, `÷`).
* **Greek and Coptic (`U+0370–U+03FF`):** Full uppercase (`Α–Ω`) and lowercase (`α–ω`) Greek alphabets plus variant symbols (`ϑ`, `ϕ`, `ϖ`, `ϱ`, `ϵ`).
* **Superscripts & Subscripts (`U+2070–U+209F`):** Full numeric and operator sets (`⁰–⁹`, `⁺`, `⁻`, `⁼`, `⁽`, `⁾`, `ⁿ`, `₀–₉`, `₊`, `₋`, `₌`, `₍`, `₎`).
* **Letterlike & Unit Symbols (`U+2100–U+214F`):** `℃`, `℉`, `Ω`, `Å`, `ℏ`, `ℓ`, `ℕ`, `ℝ`, `ℤ`.
* **Arrows (`U+2190–U+21FF`):** Cardinal, diagonal, and logical implication arrows (`←`, `↑`, `→`, `↓`, `↔`, `↕`, `⇒`, `⇔`).
* **Mathematical Operators (`U+2200–U+22FF`):** Set theory, calculus, logic, and relational operators (`∀`, `∂`, `∃`, `∅`, `∆`, `∇`, `∈`, `∉`, `∑`, `∏`, `−`, `∓`, `√`, `∝`, `∞`, `∠`, `∫`, `∬`, `∮`, `∴`, `∵`, `∼`, `≈`, `≠`, `≡`, `≤`, `≥`, `≪`, `≫`, `⊂`, `⊃`, `⊆`, `⊇`, `⊕`, `⊗`, `⊥`, `⋅`).
* **Miscellaneous Technical (`U+2300–U+23FF`):** Diameter (`⌀`), ceiling/floor brackets (`⌈`, `⌉`, `⌊`, `⌋`), angle brackets (`⟨`, `⟩`).

### 2.4 Quantitative Pass/Fail Validation Gates

Automated build verification must report explicit `PASS` or `FAIL` results per size, style, and modifier against six hard gates:

1. **Gate 1 — Vertical Stem Floor & Progression (`G_STEM`):**
* *Measurement:* Median horizontal run-length of active `1` pixels across the middle 50% vertical span of reference glyphs `'I'` (`U+0049`) and `'H'` (`U+0048`).
* *Pass Condition:* `measured_px >= 2` for `normal`/`italic` and `measured_px >= 3` for `bold`/`bold-italic` at all sizes, **and** `abs(measured_px - target_stem_px(P)) == 0` per Section 2.2. Any `1 px` vertical stem is an automatic `FAIL`.

2. **Gate 2 — Weight Contrast Separation (`G_CONTRAST`):**
* *Measurement:* Difference between `bold` stem width and `normal` stem width at identical PPEM $P$ (`stem_bold(P) - stem_normal(P)`).
* *Pass Condition:* `delta_px >= 1` for `P < 24 px`, and `delta_px >= 1` with `stem_bold(P) / stem_normal(P) >= 1.25` for `P >= 24 px`.

3. **Gate 3 — Counter Clearance (`G_COUNTER`):**
* *Measurement:* Connected-component flood-fill of interior `0` pixels inside `'e'`, `'a'`, `'o'`, `'s'`, `'α'`, and `'0'`.
* *Pass Condition:* Interior void area $\ge 1\text{ px}$ height and $\ge 1\text{ px}$ width. Plugged counters (`0` interior void pixels) trigger `FAIL`.

4. **Gate 4 — Vertical Metric & Baseline Lock (`G_METRICS`):**
* *Measurement:* Row index of baseline (`y = 0`) and cap-top across `H`, `O`, `Δ`, `Ω`, `0`.
* *Pass Condition:* Zero vertical baseline drift (`±0 px`) between Latin, Greek, and mathematical operators within the same size/style build.

5. **Gate 5 — Monospace Advance Invariant (`G_MONO`):**
* *Measurement:* `DWIDTH` / `advance_x` across all non-combining glyphs in `mono` variants.
* *Pass Condition:* Standard deviation of `advance_x` across all glyphs equals `0.0`.

6. **Gate 6 — Bounding Box Containment (`G_CLIP`):**
* *Measurement:* Rasterized glyph height and vertical offset against `FONT_ASCENT + FONT_DESCENT`.
* *Pass Condition:* Zero clipped rows above `FONT_ASCENT` or below `FONT_DESCENT`.

---

## 3. Hostable Master Repository Architecture (`UFO 3` + `DesignSpace 5.1`)

All master sources are stored in **UFO 3** directory packages linked by **DesignSpace 5.1** XML files so every outline, metric, and OpenType rule is plain-text Git-diffable and independent of proprietary GUI editors.

### 3.1 UFO 3 Package Structure

Each master `.ufo` directory adheres strictly to the UFO 3 specification:

* `metainfo.plist`: Declares `formatVersion = 3` and authoring metadata.
* `fontinfo.plist`: Defines integer `unitsPerEm`, `ascender`, `descender`, `xHeight`, `capHeight`, `italicAngle`, and OpenType OS/2 metrics.
* `layercontents.plist`: Maps the primary outline layer (`public.default` $\rightarrow$ `glyphs/`).
* `glyphs/contents.plist` & `glyphs/*.glif`: Plain XML Glyph Interchange Format files storing cubic Bézier splines, anchors, and Unicode assignments.
* `features.fea`: OpenType layout rules (tabular figures `tnum`, case-sensitive forms `case`, fractions `frac`, mark positioning `mark`/`mkmk`).
* `lib.plist`: Stores `public.glyphOrder` (enforcing identical glyph ordering across all masters for `varLib` interpolation) and `public.skipExportGlyphs`.

### 3.2 DesignSpace 5.1 Architecture

* **Continuous Axes (`<axes>`):** `wght` (Weight), `wdth` (Width for Condensed), `opsz` (Optical Size), `XTRA` (Counter/Parametric X-Transparency), `YOPQ` (Horizontal Bar Thickness).
* **Discrete Axes (`<axes>`):** `ital` (`0` = Upright, `1` = Italic) and `MONO` (`0` = Proportional, `1` = Monospace) to separate topologically distinct upright vs. true italic glyph constructions without interpolation artifacts.
* **Per-Size Instance Overrides (`public.fontInfo`):** DesignSpace 5.1 `<instance>` elements embed `public.fontInfo` dictionaries to set size-specific UPM scaling and vertical metrics directly at compile time.

### 3.3 Repository Layout

```text
epd-typography-master/
├── config/                          # Modular declarative configuration files
│   ├── project.toml                 # Global PPEM bounds (12–40), stem formulas, validation gates
│   ├── donors.yaml                  # Upstream font sources, commit hashes, Unicode slice maps
│   ├── proofs.yaml                  # Proof-sheet layout, zoom factors, optical blur kernels
│   ├── recipe.yaml                  # gftools-builder declarative compilation pipeline
│   └── sizes/                       # Modular per-PPEM axis calibration manifests
│       ├── ppem_12.yaml
│       ├── ppem_14.yaml
│       ├── ...
│       └── ppem_40.yaml
├── masters/                         # Hostable UFO 3 master sources (Git-tracked XML)
│   ├── sans/                        # Normalized proportional & condensed UFO 3 masters
│   ├── mono/                        # Normalized fixed-pitch UFO 3 masters
│   └── symbols/                     # Normalized Greek, Math & Technical UFO 3 masters
├── designspaces/                    # Generated/versioned DesignSpace 5.1 XML files
│   ├── epd_12px.designspace
│   ├── ...
│   └── epd_40px.designspace
├── runner/                          # Thin, stateless build & validation CLI
│   └── epd_font_cli.py              # Reads config/*.yaml and executes pipeline stages
└── build/                           # Ephemeral build outputs (gitignored)
    ├── ttf/                         # Instantiated & hinted TrueType binaries
    ├── bdf/                         # BDF 2.1 bitmap fonts
    ├── pbm/                         # Raw P1/P4 bi-level bitmaps
    ├── c_arrays/                    # Packed C structs & LVGL font tables
    └── proofs/                      # Visual proof sheets & pass/fail audit JSON/MD

```

---

## 4. Donor Font Selection & Ingestion Strategy

The master set is assembled from four permissive (`SIL OFL-1.1` / `Bitstream Vera`) upstream open-source projects:

| Role | Upstream Project | License | Source Format & Ingestion Method | Contribution to Master Set |
| --- | --- | --- | --- | --- |
| **Primary Proportional & Condensed Base** | **Roboto Flex** (`googlefonts/roboto-flex`) | `SIL OFL-1.1` | Native `.ufo` + `.designspace` (`wght`, `wdth`, `opsz`, `GRAD`, `slnt`, `XOPQ`, `YOPQ`, `XTRA`) | Provides continuous parametric control over vertical stem thickness, horizontal crossbar thickness (`YOPQ`), internal counter width (`XTRA`), and condensed width (`wdth`). |
| **Monospace & Geometric Base** | **Recursive** (`arrowtype/recursive`) | `SIL OFL-1.1` | Native `.ufo` + `.designspace` (`MONO`, `wght`, `slnt`, `CASL`) | Provides clean, low-contrast linear geometry for `mono` (`MONO=1`) and true cursive/slanted italic forms (`slnt=-15`). |
| **Secondary Family Donor (Mono / Condensed)** | **IBM Plex** (`IBM/plex`) | `SIL OFL-1.1` | Ingested from official OFL-1.1 `.ttf`/`.otf` release binaries via `fontTools` / `ufoLib2` into normalized UFO 3 bundles. | Optional donor for high-legibility disambiguated alphanumeric glyphs (`0`, `1`, `I`, `l`) and condensed/mono proportion references. |
| **Math, Greek & Scientific Symbols** | **STIX Two** (`stipub/stixfonts`) + **DejaVu Sans / Mono** | `SIL OFL-1.1` / `Bitstream Vera` | `STIXTwoText` & `STIXTwoMath` ship native `.ufo` + `.designspace` + `.ren` glyph name maps; DejaVu ingested via `ufoLib2` for `12px–18px` bold/regular UI math operators. | Supplies complete Greek (`U+0370–U+03FF`), superscripts/subscripts, unit symbols (`℃`, `℉`, `Ω`, `Å`), arrows, and `U+2200–U+23FF` math/technical operators. |

---

## 5. Normalization & Harmonization Pipeline

All donor sources pass through a deterministic 4-stage normalization pipeline to produce unified `masters/*.ufo` bundles:

1. **UPM Standardization:**
* All master UFOs are scaled to a uniform `unitsPerEm = 1000` (with integer-rounded coordinates) using `fontTools.pens.transformPen.TransformPen`.

2. **Vertical Metric & Mathematical Axis Alignment:**
* Donor symbol UFOs (STIX Two / DejaVu) are scaled uniformly by $s = \frac{\text{xHeight}_{\text{base}}}{\text{xHeight}_{\text{donor}}}$ so lowercase Greek (`α, β, µ, ω`) matches Latin x-height.
* Mathematical operators (`+`, `−`, `×`, `÷`, `=`, `≠`, `≤`, `≥`, `±`, `∑`, `∫`) are vertically translated so their symmetry center aligns with the base font's mathematical axis ($\frac{\text{xHeight}_{\text{base}}}{2}$).

3. **Contour & Path Normalization:**
* Overlapping components are flattened and boolean-unioned via `skia-pathops` (`pathops.union`) so monochrome scan-conversion never encounters self-intersecting winding inversions.
* All outlines are standardized to cubic Bézier splines (`fontTools.pens.qu2cuPen`) with consistent clockwise outer contour winding.
* Glyph names are canonicalized against Adobe Glyph List (AGL) / `.ren` mapping tables, and `public.glyphOrder` is synchronized across every master.

4. **Selective Unicode Grafting:**
* Using the `donors.yaml` codepoint map, missing Unicode slots (`U+0370–U+03FF`, `U+2070–U+23FF`) are copied into the target masters along with matching weight pairings (`Regular` donor $\rightarrow$ `Normal` master; `Bold` donor $\rightarrow$ `Bold` master).

---

## 6. Grid-Fitting & Bi-Level Conversion Methodology

### 6.1 Stage 1 — Master-Level Spline Conditioning

* **Extrema Insertion:** Explicit on-curve anchor nodes are inserted at all horizontal and vertical curve tangents (`0°`, `90°`, `180°`, `270°`) across every `.glif` contour so FreeType's rasterizer detects exact curve boundaries without sub-pixel drift.
* **Integer Coordinate Rounding:** All on-curve and off-curve coordinates in master `.glif` files are quantized to integer units (`round(x), round(y)`).
* **Counter-Protection Axis (`YOPQ` / `XTRA`):** In heavy masters (`wght >= 700`), horizontal crossbars (`e`, `a`, `s`, `θ`, `≡`) are constrained to `60%–70%` of vertical stem width so low-PPEM rasterization retains a minimum `1 px` interior counter void.

### 6.2 Stage 2 — Per-Size DesignSpace Instantiation & Grid Snapping

Each target size $P \in [12..40]$ has a dedicated `.designspace` (`designspaces/epd_<P>px.designspace`) generated from `config/sizes/ppem_<P>.yaml`:

1. **Two-Regime Axis Calibration:**
* **Optical Floor Zone (`12 px – 16 px`):** `wght` is boosted (`620–880`) and `XTRA` is widened so vertical stems reach `2.05 px` (`normal`/`italic`) or `3.10 px` (`bold`) while keeping counters open.
* **Proportional Scaling Zone (`18 px – 40 px`):** `wght` settles onto natural typographic values (`~400–430` for `normal`/`italic`; `~680–730` for `bold`), allowing stem thickness to grow naturally from `2 px` to `4 px` (`normal`) and `3 px` to `7 px` (`bold`) without requiring ultra-thin masters.

2. **Sub-Grid Coordinate Snapping:** Each instantiated UFO is rescaled to `UPM = 100 * P` (where `100` units $= 1.00\text{ px}$). Vertical stem edges are snapped to exact `100`-unit pixel boundaries, and horizontal crossbars are snapped to integer pixel rows before compiling to `.ttf` via `fontmake`.

### 6.3 Stage 3 — Bytecode Autohinting & Monochrome Rasterization

1. **TrueType Autohinting (`ttfautohint`):**
```bash
ttfautohint --stem-width-mode=strong --increase-x-height=16 --symbol --hinting-range-min=12 --hinting-range-max=40 --hinting-limit=40 input.ttf output_hinted.ttf

```

2. **1-Bit Scan-Conversion (`freetype-py`):**
* Hinted `.ttf` binaries are loaded in `freetype-py` with `face.set_pixel_sizes(0, P)` and rasterized via `FT_LOAD_RENDER | FT_LOAD_TARGET_MONO`.

3. **Artifact Serialization:**
* **BDF 2.1 (`.bdf`):** Serialized with exact `BBX`, `DWIDTH`, `FONT_ASCENT`, `FONT_DESCENT`, and MSB-padded hexadecimal `BITMAP` rows.
* **PBM (`.pbm`):** Exported as raw `P1` ASCII and `P4` packed binary bitmaps per glyph and per pangram/equation line.
* **C / LVGL Firmware Tables (`.c` / `.h`):** Bit-packed `uint8_t` glyph bitmaps with `advance_x`, `box_w`, `box_h`, `ofs_x`, `ofs_y`, and Unicode binary-search lookup tables.

---

## 7. Modular Configuration Architecture

### 7.1 `config/project.toml` (Optical Floors, Proportional Formulas & Gates)

```toml
[project]
name = "epd-typography-master"
version = "1.1.0"
master_upm = 1000
ppem_range = [12, 14, 16, 18, 20, 24, 28, 32, 36, 40]

[variants]
styles = ["normal", "italic", "bold", "bold-italic"]
modifiers = ["sans", "mono", "condensed"]

[scaling.normal]
stem_floor_px = 2
stem_em_ratio = 0.11          # target = max(2, round(0.11 * ppem))

[scaling.italic]
stem_floor_px = 2
stem_em_ratio = 0.11          # target = max(2, round(0.11 * ppem))

[scaling.bold]
stem_floor_px = 3
stem_em_ratio = 0.17          # target = max(3, normal_px + 1, round(0.17 * ppem))
min_bold_delta_px = 1

[gates]
min_counter_void_px = 1
max_clipped_rows = 0
stem_tolerance_px = 0         # exact match against per-size schedule

[hinting.ttfautohint]
stem_width_mode = "strong"
increase_x_height = 16
symbol_mode = true

```

### 7.2 `config/sizes/ppem_14.yaml` vs. `config/sizes/ppem_32.yaml`

Contrasting an optical-floor size (`14 px`) against a proportional-scaling size (`32 px`):

```yaml
# config/sizes/ppem_14.yaml (Optical-Floor Clamped Regime)
ppem: 14
build_upm: 1400          # 100 units = 1.00 px
grid_snap_units: 100

instances:
  sans_normal:
    axes: { wght: 640, wdth: 100, opsz: 14, XTRA: 510, YOPQ: 75, ital: 0 }
    target_stem_px: 2    # clamped to 2px floor (natural 1.54px)
  sans_italic:
    axes: { wght: 640, wdth: 100, opsz: 14, XTRA: 510, YOPQ: 75, ital: 1 }
    target_stem_px: 2
  sans_bold:
    axes: { wght: 880, wdth: 100, opsz: 14, XTRA: 530, YOPQ: 95, ital: 0 }
    target_stem_px: 3    # clamped to 3px floor (natural 2.38px)
  condensed_normal:
    axes: { wght: 650, wdth: 78, opsz: 14, XTRA: 515, YOPQ: 75, ital: 0 }
    target_stem_px: 2
  mono_normal:
    axes: { wght: 620, MONO: 1.0, slnt: 0, CASL: 0 }
    target_stem_px: 2
```

```yaml
# config/sizes/ppem_32.yaml (Proportional Scaling Regime)
ppem: 32
build_upm: 3200          # 100 units = 1.00 px
grid_snap_units: 100

instances:
  sans_normal:
    axes: { wght: 420, wdth: 100, opsz: 32, XTRA: 468, YOPQ: 88, ital: 0 }
    target_stem_px: 4    # proportional: round(0.11 * 32) = 4px
  sans_italic:
    axes: { wght: 420, wdth: 100, opsz: 32, XTRA: 468, YOPQ: 88, ital: 1 }
    target_stem_px: 4
  sans_bold:
    axes: { wght: 700, wdth: 100, opsz: 32, XTRA: 468, YOPQ: 120, ital: 0 }
    target_stem_px: 5    # proportional: round(0.17 * 32) = 5px (+1px delta)
  condensed_normal:
    axes: { wght: 430, wdth: 80, opsz: 32, XTRA: 468, YOPQ: 88, ital: 0 }
    target_stem_px: 4
  mono_normal:
    axes: { wght: 430, MONO: 1.0, slnt: 0, CASL: 0 }
    target_stem_px: 4

```

---

## 8. Automated Proofing & Empirical Audit Protocol

Every build emits a complete visual and quantitative proof suite under `build/proofs/<ppem>/<modifier>_<style>/` driven by `config/proofs.yaml`:

1. **Native `1x` Bi-Level Specimen (`specimen_1x.pbm`):**
* Exact pixel-for-pixel `P4` bitmap rendering standardized test strings across Latin (`Hamburgefonstiv 0123456789`), Greek (`ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ αβγδεζηθικλμνξοπρστυφχψω`), and Scientific/Math telemetry expressions (`ΔT = ±0.25 ℃ | RH 48.5% | ∑(xᵢ − µ)² / N ≤ 1.05×10⁻³ Ω·m`).

2. **Grid-Annotated `8x` Inspection Sheet (`grid_8x.png`):**
* Nearest-neighbor `8x` upscaled proof overlaying `1 px` pixel-boundary hairlines, baseline/x-height/cap-height reference lines in cyan, and per-glyph `BBX` advance boxes in magenta.

3. **EPD Optical Scatter Proof (`epd_psf_sim.png`):**
* Convolves the `1x` bi-level bitmap with Gaussian point-spread kernels (`σ = 135 µm` and `σ = 270 µm` scaled to display pitch) to verify contrast retention and counter separation prior to flashing firmware.

4. **Empirical Pass/Fail Audit Ledger (`audit_report.json` & `AUDIT.md`):**
* Records measured stem widths, `bold - normal` contrast deltas, minimum counter void pixels, glyph coverage counts, and explicit `PASS` / `FAIL` status per `(ppem, modifier, style)` tuple. Any failed gate exits the build with a non-zero status code and lists the exact failing glyphs.
