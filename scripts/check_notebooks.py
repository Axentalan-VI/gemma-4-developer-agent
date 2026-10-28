"""Compile every code cell of every notebook. No Kaggle, no GPU, instant.

Exists because a syntax error in a notebook cell is only discovered when Kaggle
runs it: papermill fails at `In [1]`, the run is wasted, and the cause is a
mangled escape from whatever wrote the cell. Three such errors reached Kaggle
before this check existed.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check(path: Path) -> list[str]:
    problems: list[str] = []
    nb = json.loads(path.read_text(encoding="utf-8"))
    for n, cell in enumerate(nb.get("cells", [])):
        if cell.get("cell_type") != "code":
            continue
        src = "".join(cell.get("source", []))
        if not src.strip():
            continue
        try:
            ast.parse(src)
        except SyntaxError as exc:
            cid = cell.get("id", f"#{n}")
            problems.append(f"{path.name} cell {cid!r} line {exc.lineno}: {exc.msg}")
    return problems


def main() -> int:
    targets = sorted((ROOT / "notebooks").glob("*.ipynb"))
    targets += sorted((ROOT / "kernels").rglob("*.ipynb"))
    bad: list[str] = []
    for t in targets:
        bad.extend(check(t))
    for b in bad:
        print("  " + b)
    print(f"{len(targets)} notebook(s) checked, {len(bad)} bad cell(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
