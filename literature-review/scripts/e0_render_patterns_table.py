"""Render paper/tables/taxonomy-patterns.tex from experiments/EXP-2026-004/aggregates/taxonomy-patterns.json."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "literature-review" / "results" / "taxonomy-patterns.json"
OUT = ROOT / "paper_assets" / "tables" / "taxonomy-patterns.tex"
ROWS = [("S_only", "S only"), ("G_only", "G only"), ("U_only", "U only"), ("mixed_no_C", "Mixed, no C"),
        ("C_only", "C only"), ("mixed_with_C", "Mixed with C"), ("all", "All")]
COLS = ["loop_claim", "loop_match", "tail", "deadline", "load", "feasibility_owned", "coverage_owned"]


def main() -> int:
    global SRC, OUT
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    SRC = args.results_dir / "taxonomy-patterns.json"
    OUT = args.out
    OUT.parent.mkdir(parents=True, exist_ok=True)
    g = json.loads(SRC.read_text())["groups"]
    body = []
    for key, label in ROWS:
        r = g[key]
        if key == "C_only":
            body.append("\\midrule")
        if key == "all":
            body.append("\\midrule")
        body.append(" & ".join([label, str(r["n"])] + [str(r[c]) for c in COLS]) + " \\\\")
    OUT.write_text(r"""\begin{table}[t]
\centering\footnotesize
\setlength{\tabcolsep}{2.6pt}
\renewcommand{\arraystretch}{1.05}
\caption{Reporting evidence and check ownership by decision interface across the 139 families. Rows partition the families by the interface letters of Table~\ref{tab:e0-systematization}, which denote selection (S), generation (G), deterministic computation (C) and unspecified (U). Cells count families. Reporting columns use the evidence audit, and check columns count families whose published entry names an owner. Load has low coding agreement (Table~\ref{tab:e0-agreement}), and the check columns support no prevalence estimate ($\S$\ref{sec:systematization}).}\label{tab:taxonomy-patterns}
\begin{tabular}{@{}lrrrrrrrr@{}}
\toprule
\rowcolor{ebBlue} & & \multicolumn{2}{c}{Loop claim} & & & & \multicolumn{2}{c}{Check owned} \\
\rowcolor{ebBlue} Interface & $n$ & Any & Matched & p95+ & Deadline & Load & Feasib. & Cover. \\
\midrule
""" + "\n".join(body) + "\n\\bottomrule\n\\end{tabular}\n\\end{table}\n", encoding="utf-8")
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
