#!/usr/bin/env python3
"""Stateless CLI entrypoint for the EPD Bi-Level Typography System (SPEC-EPD-FONT-001 Rev 1.1)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXPECTED_VENV = (REPO_ROOT / ".venv").resolve()


def enforce_project_venv() -> None:
    """Ensure execution strictly inside the repo's Python 3.12 .venv."""
    cur_prefix = Path(sys.prefix).resolve()
    venv_py = EXPECTED_VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if cur_prefix != EXPECTED_VENV:
        if not venv_py.is_file():
            sys.stderr.write(
                f"[!] Virtual environment not found at '{EXPECTED_VENV}'.\n"
                "    Run `scripts\\setup_venv.ps1` (or `uv venv .venv --python 3.12`) first.\n"
            )
            raise SystemExit(2)
        env = os.environ.copy()
        env["PYTHONNOUSERSITE"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONUNBUFFERED"] = "1"
        os.execve(str(venv_py), [str(venv_py), str(Path(__file__).resolve()), *sys.argv[1:]], env)
    if sys.version_info[:2] != (3, 12):
        sys.stderr.write(f"[!] Expected Python 3.12 in .venv, got {sys.version_info.major}.{sys.version_info.minor}.\n")
        raise SystemExit(2)


enforce_project_venv()

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
from collections.abc import Sequence

from runner.config import load_config


def _parse_ppems(ppem_arg: str | None, default_ppems: list[int]) -> list[int]:
    if not ppem_arg:
        return default_ppems
    vals = [int(x.strip()) for x in ppem_arg.split(",") if x.strip()]
    for v in vals:
        if v not in default_ppems:
            raise SystemExit(f"[!] Unsupported PPEM {v}; allowed: {default_ppems}")
    return vals


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="epd_font_cli",
        description="SPEC-EPD-FONT-001 Rev 1.1 — UFO 3 + DesignSpace 5.1 Bi-Level EPD Typography Pipeline",
    )
    parser.add_argument("--check-env", action="store_true", help="Verify Python 3.12 .venv isolation and exit")
    parser.add_argument("--ppem", type=str, default=None, help="Comma-separated PPEM subset (e.g. 12,14,24)")
    parser.add_argument("--modifiers", type=str, default=None, help="Comma-separated modifiers (sans,mono,condensed)")
    parser.add_argument("--styles", type=str, default=None, help="Comma-separated styles (normal,italic,bold,bold-italic)")
    parser.add_argument("--pbm-per-glyph", action="store_true", help="Also emit individual glyph PBM P1/P4 files")
    parser.add_argument("--force", action="store_true", help="Force re-normalization of masters/")
    parser.add_argument("--save-snapped-ufo", action="store_true", help="Write intermediate snapped UFOs to build/snapped_ufo")
    parser.add_argument("-j", "--jobs", type=int, default=os.cpu_count() or 4, help="Parallel worker count")
    parser.add_argument(
        "command",
        nargs="?",
        default="all",
        choices=["normalize", "designspaces", "calibrate", "build", "audit", "proofs", "all"],
        help="Pipeline stage to execute",
    )
    args = parser.parse_args(argv)

    if args.check_env:
        import fontTools  # noqa: F401
        import freetype  # noqa: F401
        import pathops  # noqa: F401
        import ttfautohint  # noqa: F401
        import ufoLib2  # noqa: F401

        print(f"[+] Python: {sys.version.split()[0]} | sys.prefix: {sys.prefix}")
        print(f"[+] PYTHONNOUSERSITE={os.environ.get('PYTHONNOUSERSITE', '')}")
        print("[+] All core UFO/DesignSpace/PathOps/ttfautohint/FreeType packages verified.")
        return 0

    cfg = load_config(REPO_ROOT)
    ppems = _parse_ppems(args.ppem, cfg.ppem_range)
    modifiers = [m.strip() for m in args.modifiers.split(",")] if args.modifiers else None
    styles = [s.strip() for s in args.styles.split(",")] if args.styles else None

    cmd = args.command
    if cmd in ("normalize", "all"):
        from runner.normalize import run_normalize

        run_normalize(cfg, force=args.force)

    if cmd in ("designspaces", "all"):
        from runner.designspace_gen import generate_all_designspaces

        generate_all_designspaces(cfg, ppems=ppems)

    if cmd == "calibrate":
        from runner.calibrate import run_calibrate

        run_calibrate(cfg, ppems=ppems, modifiers=modifiers, styles=styles)
        return 0

    if cmd in ("build", "all"):
        from runner.compile_strikes import run_build

        run_build(
            cfg,
            ppems=ppems,
            modifiers=modifiers,
            styles=styles,
            pbm_per_glyph=args.pbm_per_glyph,
            save_snapped_ufo=args.save_snapped_ufo,
            jobs=args.jobs,
        )

    if cmd in ("audit", "proofs", "all"):
        from runner.gates import run_audit_and_proofs

        passed = run_audit_and_proofs(
            cfg,
            ppems=ppems,
            modifiers=modifiers,
            styles=styles,
            emit_proofs=(cmd in ("proofs", "all")),
        )
        return 0 if passed else 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
