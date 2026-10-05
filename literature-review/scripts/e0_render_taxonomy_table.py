"""Render paper/tables/taxonomy-reliability.tex from the EXP-2026-004 taxonomy agreement aggregates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGG = ROOT / "literature-review" / "results"
OUT = ROOT / "paper_assets" / "tables" / "taxonomy-reliability.tex"
MIN_N = 20  # owner and mechanism comparisons with the published table below this size are not shown


def k(v):
    return "N/A" if v is None else f"{v:.2f}"


def main() -> int:
    global AGG, OUT
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    AGG = args.results_dir
    OUT = args.out
    OUT.parent.mkdir(parents=True, exist_ok=True)
    I, A, B = (json.loads((AGG / f"taxonomy-{n}.json").read_text()) for n in
               ("intercoder", "coderA-vs-published", "coderB-vs-published"))
    rows: list[str] = []

    def group(title: str) -> None:
        rows.append(f"\\rowcolor{{ebAmber!45}}\\multicolumn{{7}}{{l}}{{\\textbf{{\\itshape {title}}}}} \\\\*")

    def stat(label: str, get) -> None:
        i, a, b = get(I), get(A), get(B)
        rows.append(f"{label} & {i['n']} & {100 * i['agreement']:.1f} & {k(i['kappa'])} & {i['ac1']:.2f} & "
                    f"{k(a['kappa'])} & {k(b['kappa'])} \\\\")

    def exact(label: str, get) -> None:
        i, a, b = get(I), get(A), get(B)
        pub = [f"{100 * x['exact']:.1f}\\%" if x["n"] >= MIN_N else "--" for x in (a, b)]
        rows.append(f"{label} & {i['n']} & {100 * i['exact']:.1f} & -- & -- & {pub[0]} & {pub[1]} \\\\")

    group("Decision interface")
    for letter, name in (("S", "Selection (S)"), ("G", "Generation (G)"), ("C", "Computation (C)")):
        stat(name, lambda r, L=letter: r["interfaces"][L])
    exact("Exact interface set", lambda r: r["interfaces"]["exact_set"])
    group("Execution path")
    stat("Offline / request-driven / both", lambda r: r["path"])
    exact("Exact receiving-role set", lambda r: r["roles"]["exact_set"])
    group("Check present")
    for c in ("observation", "feasibility", "coverage"):
        stat(c.capitalize(), lambda r, c=c: r[c]["performed"])
    group("Check owner and mechanism, where both coders find the check")
    for c in ("observation", "feasibility", "coverage"):
        exact(f"{c.capitalize()} owner", lambda r, c=c: r[c]["owner"])
        exact(f"{c.capitalize()} mechanism", lambda r, c=c: r[c]["mechanism"])

    OUT.write_text("""\\begin{table}[!htbp]
\\centering\\footnotesize
\\setlength{\\tabcolsep}{3pt}
\\renewcommand{\\arraystretch}{1.08}
\\caption{Reproducibility of the three-axis systematization over the 129 families outside the 10-family pilot. Two model coders (GPT and Claude) recoded each family blind from full text under a frozen codebook. A third blind pass mapped the published cells into the same fields. A is observed agreement. Rows without $\\kappa$ report exact set agreement. The last two columns give each coder's agreement with the published entries ($\\kappa$, or exact agreement in percent), over families whose published cells settle the field (path 103, receiving roles 125). Owner and mechanism comparisons with fewer than %d shared checks are omitted.}\\label{tab:tx-reliability}
\\begin{tabular}{@{}p{0.34\\columnwidth}rrrrrr@{}}
\\toprule
\\rowcolor{ebBlue} & & \\multicolumn{3}{c}{Coder vs coder} & \\multicolumn{2}{c}{Coder vs table} \\\\
\\rowcolor{ebBlue} Field & $n$ & A (\\%%) & $\\kappa$ & AC1 & GPT & Claude \\\\
\\midrule
""" % MIN_N + "\n".join(rows) + "\n\\bottomrule\n\\end{tabular}\n\\end{table}\n", encoding="utf-8")
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
