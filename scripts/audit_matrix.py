"""CLI wrapper to run the standardized canonical sample matrix audit."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from runner.matrix_audit import run_matrix_audit


def main() -> int:
    res = run_matrix_audit(REPO_ROOT)
    print(f"Wrote build/proofs/MATRIX_AUDIT.md ({len(res['rows'])} family-PPEM rows).")
    print(json.dumps(res["rows"][:4], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
