"""Declarative configuration loader and mathematical stem schedule helpers."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


def target_stem_px(ppem: int, style: str) -> int:
    """Compute target vertical stem width in pixels per SPEC-EPD-FONT-001 Section 2.1-2.2."""
    norm = max(2, round(0.11 * ppem))
    if style in ("normal", "italic"):
        return norm
    if style in ("bold", "bold-italic"):
        return max(3, norm + 1, round(0.17 * ppem))
    raise ValueError(f"Unknown style: {style}")


def target_hbar_px(ppem: int, style: str, project_cfg: dict[str, Any] | None = None) -> int:
    """Return target horizontal crossbar thickness in pixels."""
    if project_cfg and "schedule" in project_cfg:
        entry = project_cfg["schedule"].get(str(ppem)) or project_cfg["schedule"].get(ppem)
        if isinstance(entry, dict):
            key = "bold_hbar" if "bold" in style else "normal_hbar"
            if key in entry:
                return int(entry[key])
    stem = target_stem_px(ppem, style)
    return max(1, round(stem * 0.65))


def parse_range_list(ranges: list[str]) -> list[int]:
    """Expand hex/int range strings (e.g. '0x0020-0x007E', '0x038C') into sorted codepoints."""
    cps: set[int] = set()
    for item in ranges:
        s = str(item).strip()
        if "-" in s:
            lo_s, hi_s = s.split("-", 1)
            lo = int(lo_s, 0)
            hi = int(hi_s, 0)
            cps.update(range(lo, hi + 1))
        else:
            cps.add(int(s, 0))
    return sorted(cps)


@dataclass
class ProjectConfig:
    repo_root: Path
    project: dict[str, Any]
    donors: dict[str, Any]
    proofs: dict[str, Any]
    recipe: dict[str, Any]
    sizes: dict[int, dict[str, Any]]

    @property
    def ppem_range(self) -> list[int]:
        return [int(x) for x in self.project["project"]["ppem_range"]]

    @property
    def terminus_ppem_range(self) -> list[int]:
        raw = self.project["project"].get("terminus_ppem_range", [12, *self.ppem_range])
        return [int(x) for x in raw]

    def mandatory_codepoints(self) -> list[int]:
        """Return sorted list of all mandatory codepoints from config/donors.yaml."""
        cps: set[int] = set()
        for blk in self.donors.get("unicode_blocks", {}).values():
            cps.update(parse_range_list(blk.get("ranges", [])))
        return sorted(cps)

    def block_codepoints(self) -> dict[str, list[int]]:
        """Return mapping of block_name -> sorted codepoints."""
        return {
            name: parse_range_list(blk.get("ranges", []))
            for name, blk in self.donors.get("unicode_blocks", {}).items()
        }


def load_config(repo_root: Path | None = None) -> ProjectConfig:
    """Load all config/*.toml and config/*.yaml manifests."""
    root = (repo_root or REPO_ROOT).resolve()
    cfg_dir = root / "config"
    with (cfg_dir / "project.toml").open("rb") as f:
        project = tomllib.load(f)
    donors = yaml.safe_load((cfg_dir / "donors.yaml").read_text(encoding="utf-8"))
    proofs = yaml.safe_load((cfg_dir / "proofs.yaml").read_text(encoding="utf-8"))
    recipe = yaml.safe_load((cfg_dir / "recipe.yaml").read_text(encoding="utf-8"))

    sizes: dict[int, dict[str, Any]] = {}
    for p in project["project"]["ppem_range"]:
        sz_path = cfg_dir / "sizes" / f"ppem_{int(p)}.yaml"
        sizes[int(p)] = yaml.safe_load(sz_path.read_text(encoding="utf-8"))

    return ProjectConfig(
        repo_root=root,
        project=project,
        donors=donors,
        proofs=proofs,
        recipe=recipe,
        sizes=sizes,
    )
