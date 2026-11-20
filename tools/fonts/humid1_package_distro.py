#!/usr/bin/env python3
"""
humid1_package_distro.py (v1.0.23)
==================================
A 1-bit EPD font generator and asset pipeline for embedded displays.
Repository : https://github.com/Humidyne-Labs/epd-font
Authors    : Humiditron (https://github.com/humiditron) & AI/LLM Development Partner
License    : MIT License

Portable Distribution Bundler & Versioned Zip Archive Generator:
Packages a self-contained firmware distribution directory (`--dist-dir`) and creates
a versioned `.zip` archive (`epd-font_<workflow>_v1.0.23.zip`) containing:
  - Static build blob (`humid1_epd_vault.json.gz`)
  - Hardware scheme descriptors (`esp32s3-N8R8-hw_scheme.json`, `generic_hw.json`)
  - CMake-compatible Python scripts (`tools/humid1_fw_emit.py`, `tools/humid1_cmake_font_builder.py`, `tools/humid1_runtime.py`)
  - Example ESP-IDF CMake files (`cmake/CMakeLists.txt`, `cmake/epd_font_esp_idf.cmake`)
  - Automatically copied font, icon, and MIT repository license files (`licenses/`)
  - Generated LVGL >= 9.6.0 `.c`/`.h` sources (`fonts/`)
  - ROM space estimate reports (`rom_space_estimate.txt`, `total_disk_size.txt`)
  - Comprehensive `README.md` with version info (`v1.0.23`), credits, and full font/strike inventory.
"""

from __future__ import annotations

import argparse
import gzip
import json
import shutil
import sys
import zipfile
from pathlib import Path
from typing import List

from humid1_runtime import (
    HUMIDITRON_URL,
    PROJECT_TAGLINE,
    PUBLIC_REPO_URL,
    REPO_NAME,
    TOOL_VERSION,
    collect_all_licenses_recursive,
    fail_gracefully,
    install_clean_signal_handlers,
    require_valid_path,
)


def package_distribution_bundle(
    build_dir: Path,
    dist_dir: Path,
    scheme_paths: List[Path],
    repo_root: Path,
    bundle_name: str = "h1os",
) -> Path:
    """Assemble the distribution directory and create a versioned .zip archive inside dist_dir.parent."""
    dist_dir.mkdir(parents=True, exist_ok=True)
    for sub in ("fonts", "metrics", "schemes", "tools", "cmake", "metadata", "licenses"):
        (dist_dir / sub).mkdir(parents=True, exist_ok=True)

    # 1. Copy scheme files and root hardware scheme files
    for sp in scheme_paths:
        if sp.is_file():
            shutil.copy2(sp, dist_dir / "schemes" / sp.name)
    for hw_name in ("esp32s3-N8R8-hw_scheme.json", "generic_hw.json"):
        hw_src = repo_root / hw_name
        if hw_src.is_file():
            shutil.copy2(hw_src, dist_dir / hw_name)
            shutil.copy2(hw_src, dist_dir / "schemes" / hw_name)

    # 2. Copy CMake-compatible Python scripts & runtime helpers
    fonts_tool_dir = repo_root / "tools" / "fonts"
    for script_name in (
        "humid1_fw_emit.py",
        "humid1_cmake_font_builder.py",
        "humid1_runtime.py",
    ):
        src_s = fonts_tool_dir / script_name
        if src_s.is_file():
            shutil.copy2(src_s, dist_dir / "tools" / script_name)

    # 3. Copy example CMake files and tailor root CMakeLists.txt default scheme to primary scheme
    cmake_src_dir = fonts_tool_dir / "cmake"
    primary_scheme_name = scheme_paths[0].name if scheme_paths else "h1os_full.scheme.json"
    if cmake_src_dir.is_dir():
        for cf in cmake_src_dir.glob("*"):
            if cf.is_file():
                shutil.copy2(cf, dist_dir / "cmake" / cf.name)
        ex_cmake = cmake_src_dir / "example_CMakeLists.txt"
        if ex_cmake.is_file():
            cmake_txt = ex_cmake.read_text(encoding="utf-8")
            cmake_txt = cmake_txt.replace("schemes/h1os_full.scheme.json", f"schemes/{primary_scheme_name}")
            (dist_dir / "CMakeLists.txt").write_text(cmake_txt, encoding="utf-8")

    # 4. Copy patch manifest & repository MIT license
    if (repo_root / "font_icon_epd_patches.json").is_file():
        shutil.copy2(repo_root / "font_icon_epd_patches.json", dist_dir / "font_icon_epd_patches.json")
    if (repo_root / "LICENSE").is_file():
        shutil.copy2(repo_root / "LICENSE", dist_dir / "LICENSE")

    # 5. Copy metadata catalogs
    meta_src = repo_root / "build" / "metadata"
    if not meta_src.is_dir():
        meta_src = build_dir.parent / "metadata"
    stale_plex_cat = dist_dir / "metadata" / "plex_catalog.json"
    if stale_plex_cat.is_file():
        stale_plex_cat.unlink()
    if meta_src.is_dir():
        for jf in meta_src.glob("*.json"):
            if jf.name == "plex_catalog.json":
                continue
            shutil.copy2(jf, dist_dir / "metadata" / jf.name)

    # 6. Copy generated C/H fonts & ROM reports from build_dir (prune stale fonts first)
    c_src = build_dir / "fonts"
    for old_cf in (dist_dir / "fonts").glob("*.c"):
        old_cf.unlink()
    for old_hf in (dist_dir / "fonts").glob("*.h"):
        old_hf.unlink()
    if c_src.is_dir():
        for f in c_src.glob("*"):
            if f.is_file():
                shutil.copy2(f, dist_dir / "fonts" / f.name)
    m_src = build_dir / "metrics"
    for old_mf in (dist_dir / "metrics").glob("*.csv"):
        old_mf.unlink()
    if m_src.is_dir():
        for mf in m_src.glob("*.csv"):
            if mf.is_file():
                shutil.copy2(mf, dist_dir / "metrics" / mf.name)
    for r_file in ("rom_space_estimate.txt", "total_disk_size.txt"):
        if (build_dir / r_file).is_file():
            shutil.copy2(build_dir / r_file, dist_dir / r_file)

    # 7. Automatically collect & copy all font/icon/pipeline license files
    copied_lics = collect_all_licenses_recursive(
        search_roots=[repo_root / "assets", repo_root / "build" / "static_ttfs", build_dir],
        dest_license_dirs=[dist_dir / "licenses", dist_dir / "fonts" / "licenses"],
        repo_root=repo_root,
    )

    # 8. Inspect Strike Vault to build complete font list and validate packaged schemes
    vault_file = dist_dir / "humid1_epd_vault.json.gz"
    src_vault = build_dir / "dist" / "humid1_epd_vault.json.gz"
    if src_vault.is_file() and src_vault.resolve() != vault_file.resolve():
        shutil.copy2(src_vault, vault_file)

    strike_rows: List[str] = []
    if vault_file.is_file():
        with gzip.open(vault_file, "rt", encoding="utf-8") as vf:
            vdata = json.load(vf)
        vault_strikes = vdata.get("strikes", {})
        for sym, s_info in sorted(vault_strikes.items()):
            strike_rows.append(
                f"| `{sym}` | `{s_info.get('family', '')}` | `{s_info.get('style', '')}` | "
                f"`{s_info.get('size_px', '')} px` | `{s_info.get('source_ttf', '')}` | "
                f"`{len(s_info.get('glyphs', []))}` | `{len(s_info.get('kern_pairs', []))}` |"
            )

        # Remove stale extra scheme files in dist_dir/schemes that are not in scheme_paths
        keep_schemes = {sp.name for sp in scheme_paths} | {"esp32s3-N8R8-hw_scheme.json", "generic_hw.json"}
        for old_sf in (dist_dir / "schemes").glob("*.json"):
            if old_sf.name not in keep_schemes:
                old_sf.unlink()

        # Verify every packaged scheme's strikes exist in the Strike Vault
        for sp in scheme_paths:
            if not sp.is_file():
                continue
            scfg = json.loads(sp.read_text(encoding="utf-8"))
            missing_in_vault: List[str] = []
            for st in scfg.get("strikes", []):
                fam = st["family"]
                style = st.get("style", "normal")
                if "ttf_file" in st and st["ttf_file"]:
                    style = Path(st["ttf_file"]).stem.lower().replace("-", "_")
                for sz in st.get("sizes", []):
                    sym = (
                        f"humid1_font_plex_{fam}_{style}_{sz}"
                        if fam in ("sans", "cond", "mono", "serif", "math")
                        else (
                            f"humid1_font_terminus_{style}_{sz}"
                            if fam == "terminus"
                            else (
                                f"humid1_{fam}_{style}_{sz}"
                                if fam.startswith("icon_")
                                else f"humid1_font_{fam}_{style}_{sz}"
                            )
                        )
                    )
                    if sym not in vault_strikes:
                        missing_in_vault.append(sym)
            if missing_in_vault:
                fail_gracefully(
                    f"Packaged scheme `{sp.name}` references {len(missing_in_vault)} strike(s) missing from `{vault_file.name}`: {missing_in_vault[:5]}",
                    "Only include compatible subset schemes in `--schemes`, or rebuild the vault from the superset scheme first.",
                )

    readme_lines = [
        f"# `{REPO_NAME}` v{TOOL_VERSION} — Portable Embedded Firmware Font Distribution (`{bundle_name}`)",
        "",
        f"> **{PROJECT_TAGLINE}**",
        "",
        f"- **Repository**: [{PUBLIC_REPO_URL}]({PUBLIC_REPO_URL})",
        f"- **Version**: `v{TOOL_VERSION}`",
        f"- **Lead Designer & Developer**: [Humiditron]({HUMIDITRON_URL}) (Humidyne Labs) & AI/LLM Development Partner",
        "- **Pipeline & Tooling License**: MIT License (`LICENSE`)",
        "- **Upstream Font & Icon Licenses**: SIL OFL 1.1, CC-BY 4.0, ISC, MIT (see `licenses/`)",
        "",
        "## 1. Bundle Contents",
        "",
        "- `humid1_epd_vault.json.gz`: Pre-rasterized 1-bit Strike Vault static build blob.",
        "- `esp32s3-N8R8-hw_scheme.json` & `generic_hw.json`: Hardware partition scheme files (`3 MByte` = `3,145,728` bytes single partition budget, zero hardcoded fallbacks).",
        "- `fonts/`: Pre-generated LVGL `>= 9.6.0` `.c` modules and `.h` headers (`humid1_fonts.h`, `h1os_fonts.h` / configured `compat_header`).",
        "- `metrics/`: Per-strike `char_widths_<symbol>.csv` and `kern_pairs_<symbol>.csv` telemetry/layout manifests for DuckDB SQL and `embedded-ops` MCP tools.",
        "- `tools/humid1_fw_emit.py` & `tools/humid1_cmake_font_builder.py`: Zero-dependency ESP-IDF CMake Python scripts.",
        "- `CMakeLists.txt` & `cmake/epd_font_esp_idf.cmake`: Example ESP-IDF CMake integration files.",
        "- `schemes/`: Declarative JSON font scheme configuration files.",
        "- `licenses/`: Complete upstream font and icon license files (`" + "`, `".join(copied_lics) + "`).",
        "- `rom_space_estimate.txt` & `total_disk_size.txt`: Approximate `.rodata` ROM space breakdown per build, per font-file pair, and per strike against the `3 MByte` (`3,145,728` bytes) hardware partition.",
        "",
        "## 2. Quick ESP-IDF CMake Integration",
        "",
        "```cmake",
        "include(${CMAKE_CURRENT_LIST_DIR}/cmake/epd_font_esp_idf.cmake)",
        "epd_font_generate_lvgl_target(",
        "    TARGET_NAME humid1_epd_fonts",
        "    SCHEME      ${CMAKE_CURRENT_LIST_DIR}/schemes/" + (scheme_paths[0].name if scheme_paths else "h1os_full.scheme.json"),
        "    VAULT       ${CMAKE_CURRENT_LIST_DIR}/humid1_epd_vault.json.gz",
        "    OUT_DIR     ${CMAKE_CURRENT_BINARY_DIR}/generated_fonts",
        ")",
        "target_link_libraries(${COMPONENT_LIB} PUBLIC humid1_epd_fonts)",
        "```",
        "",
        f"## 3. Included Font & Icon Strikes ({len(strike_rows)} Strikes)",
        "",
        "| Strike Symbol | Family | Style | Size | Source Asset | Glyphs | Kerning Pairs |",
        "| :--- | :--- | :--- | :--- | :--- | ---: | ---: |",
        *strike_rows,
        "",
    ]
    (dist_dir / "README.md").write_text("\n".join(readme_lines), encoding="utf-8")

    # 9. Create versioned zip archive inside dist_dir.parent (e.g. dist/epd-font_h1os_v1.0.23.zip)
    for stale_z in dist_dir.glob("*.zip"):
        stale_z.unlink()
    zip_name = f"{REPO_NAME}_{bundle_name}_v{TOOL_VERSION}.zip"
    zip_path = dist_dir.parent / zip_name
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for file_p in sorted(dist_dir.rglob("*")):
            if file_p.is_file():
                arcname = f"{dist_dir.name}/{file_p.relative_to(dist_dir).as_posix()}"
                zf.write(file_p, arcname)

    print(f"[+] Packaged versioned distribution archive -> {zip_path} ({zip_path.stat().st_size:,} bytes)")
    return zip_path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="humid1_package_distro.py",
        description=f"Humidyne Labs / Humiditron `epd-font` v{TOOL_VERSION} — Portable Distribution Bundler & Zipper.",
    )
    parser.add_argument("-b", "--build-dir", type=str, required=True, help="Input build directory (e.g. build/h1os)")
    parser.add_argument("-d", "--dist-dir", type=str, required=True, help="Output distribution directory (e.g. dist/h1os_distro)")
    parser.add_argument("-S", "--schemes", type=str, nargs="+", required=True, help="One or more .scheme.json files to include")
    parser.add_argument("-n", "--name", type=str, default="distro", help="Bundle identifier tag (e.g. h1os, example, audit)")
    return parser


def main() -> None:
    install_clean_signal_handlers()
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent if script_dir.name == "fonts" else script_dir.parent
    parser = build_arg_parser()
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        fail_gracefully("Missing required arguments `--build-dir`, `--dist-dir`, and `--schemes`.")
    args = parser.parse_args()

    build_dir = require_valid_path(args.build_dir, "--build-dir", must_exist=True, expect_dir=True)
    dist_dir = Path(args.dist_dir).expanduser().resolve()
    schemes: List[Path] = []
    for s in args.schemes:
        for matched in sorted(Path().glob(s)) if ("*" in s or "?" in s) else [Path(s)]:
            schemes.append(require_valid_path(matched, "--schemes", must_exist=True, expect_dir=False))

    package_distribution_bundle(
        build_dir=build_dir,
        dist_dir=dist_dir,
        scheme_paths=schemes,
        repo_root=repo_root,
        bundle_name=args.name,
    )


if __name__ == "__main__":
    main()
