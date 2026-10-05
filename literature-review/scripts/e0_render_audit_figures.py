"""Render the reporting-coverage figures (reporting-{a,b,c,d,legend}.pdf) with the frozen plotting code.

Executes src/scripts/sok_family_figures.py unchanged except for its module-level inputs: the E0 results come from
e0_corpus_metrics.py output, the unrelated study inputs are stubbed, and output goes to --out-dir. Only audit() runs.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[1] / "scripts" / "sok_family_figures.py"
INPUT_LINE = "S, E, A, SPARSE, LOAD = [read(s) for s in SOURCE_FILES[:5]]"
OUT_LINE = "OUT = ROOT / 'paper-sok-csur/figures/family'"
NAMES = {"e0-audit-0": "reporting-a", "e0-audit-1": "reporting-b", "e0-audit-2": "reporting-c",
         "e0-audit-3": "reporting-d", "e0-audit-legend": "reporting-legend"}


def results_view(metrics: dict) -> dict:
    """The subset of the frozen results.json that audit() reads."""
    sizes = metrics["strata_sizes"]
    return {"metrics": [{"field": f, "paper_family": v["paper_family"]} for f, v in metrics["metrics"].items()],
            "strata": {k: list(range(n)) for k, n in sizes.items()}}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--metrics", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    a = p.parse_args()
    src = SOURCE.read_text(encoding="utf-8")
    assert src.count(INPUT_LINE) == 1 and src.count(OUT_LINE) == 1
    a.out_dir.mkdir(parents=True, exist_ok=True)
    work = a.out_dir / "family"
    src = src.replace(OUT_LINE, f"OUT = Path({str(work)!r})")
    src = src.replace(INPUT_LINE, "S, E, SPARSE, LOAD = {'cells': []}, {}, {}, {}\nA = __A__")
    receipt = "str(p.relative_to(ROOT/'paper-sok-csur'))"
    assert src.count(receipt) >= 1
    src = src.replace(receipt, "str(p)")  # build receipts only; the output lives outside the frozen tree
    namespace = {"__name__": "sok_family_figures_audit", "__file__": str(SOURCE),
                 "__A__": results_view(json.loads(a.metrics.read_text(encoding="utf-8")))}
    exec(compile(src.split("\nif __name__ ==")[0], str(SOURCE), "exec"), namespace)
    namespace["audit"]()
    for old, new in NAMES.items():
        shutil.copy2(work / f"{old}.pdf", a.out_dir / f"{new}.pdf")
    print("rendered", ", ".join(NAMES.values()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
