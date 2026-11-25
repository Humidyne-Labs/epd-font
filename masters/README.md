# `masters/` — Self-Contained Stock Glyph & Icon Master Tree

This directory holds all normalized, plain-text Git-diffable **UFO 3** masters, **Terminus BDF** bitmap masters, **Icon** vector masters, and upstream **SPDX licenses** required to build every `epd-font` strike without any external donor archives.

## Directory Layout

| Directory | Contents | Source Donor & License |
| :--- | :--- | :--- |
| `sans/` | 22 orthogonal UFO 3 masters (`11` Upright + `11` Italic, `UPM=1000`, cubic Bézier) spanning `wght`, `wdth`, `opsz`, `XTRA`, `YOPQ`, `XOPQ` | **Roboto Flex** `v3.200` (`SIL OFL-1.1`) |
| `mono/` | 6 orthogonal UFO 3 masters (`3` Upright + `3` Italic, `UPM=1000`, cubic Bézier, `width=600`) | **Recursive Mono-Linear** `v1.085` (`SIL OFL-1.1`) |
| `symbols/` | 8 harmonized UFO 3 symbol masters (Greek, Superscripts/Subscripts, Units, Arrows, Math `U+2200–U+22FF`, Technical) | **DejaVu** `v2.37` (`Bitstream Vera`) + **STIX Two** `v2.13b171` (`SIL OFL-1.1`) |
| `terminus/` | 20 native X11 BDF bitmap masters (`ter-u{12..32}{n,b,v}.bdf`) | **Terminus Font** `v4.49.1` (`SIL OFL-1.1`) |
| `icons/` | 4 PUA vector icon suites (`Font Awesome 7.3.1`, `Lucide 1.67.0`, `Phosphor 2.1.0`, `Tabler 3.50.0`) with `char_manifest_*.json` | `CC-BY-4.0`, `OFL-1.1`, `ISC`, `MIT` |
| `licenses/` | Complete upstream license files for all bundled donors | See individual files in `licenses/` |
