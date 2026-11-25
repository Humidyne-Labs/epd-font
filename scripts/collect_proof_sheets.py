"""Collect all full_glyph_sheet.png proofs (plus showcase) into one flat directory."""

from __future__ import annotations

import shutil
from pathlib import Path


def collect_all_full_sheets(proof_root: Path | None = None) -> Path:
    root = (proof_root or (Path(__file__).resolve().parent.parent / "build" / "proofs")).resolve()
    out_dir = root / "all_full_sheets"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for idx, name in enumerate(("SHOWCASE_MULTI_FONT.png", "SHOWCASE_MULTI_FONT_psf.png")):
        src = root / name
        if src.is_file():
            shutil.copy2(src, out_dir / f"{idx:02d}_{name}")

    copied = 0
    for sheet in sorted(root.glob("*/*/full_glyph_sheet.png")):
        ppem_part = sheet.parent.parent.name
        style_part = sheet.parent.name
        if not ppem_part.isdigit():
            continue
        dst_name = f"{int(ppem_part):02d}px_{style_part}.png"
        shutil.copy2(sheet, out_dir / dst_name)
        copied += 1

    print(f"[+] Collected {copied} full_glyph_sheet.png files -> {out_dir}")
    return out_dir


if __name__ == "__main__":
    collect_all_full_sheets()
