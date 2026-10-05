"""Rewrite the numbers of paper/tables/reporting-coverage.tex from e0_corpus_metrics.py output.

Only the count cells, header denominators and the linked-scope count in the caption change; layout is preserved.
Rendering the frozen 132-family metrics must reproduce the committed table byte for byte (--expect-identical, which
uses the frozen two-line cells). The default writes each cell on one line.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROWS = {
    "Named timing endpoint": "endpoint", "Specified metric denominator": "denominator", "p95 or higher": "tail",
    "Deadline attainment": "deadline", "Input load": "load", "Queue / waiting": "queue",
    "Stability evidence": "stability", "Non-learning comparison": "baseline", "Explicit loop claim": "loop_claim",
    "Supported loop claim": "loop_match", "Named execution location": "deployment",
    "Network round trip included": "roundtrip", "Format check reported": "format",
    "Semantic check reported": "semantic", "Final-state check reported": "final_state",
    "Three gates distinguished": "gate_separation", "Public code pointer": "code", "Public data pointer": "data",
}


def cell(r: dict, stacked: bool) -> str:
    lo, hi = (100 * x for x in r["ci95"])
    if not stacked:
        return f"{r['positive']}/{r['n']} ({100 * r['proportion']:.1f}\\%) \\textcolor{{black!60}}{{[{lo:.1f}, {hi:.1f}]}}"
    return (f"\\shortstack[r]{{{r['positive']}/{r['n']} ({100 * r['proportion']:.1f}\\%)\\\\"
            f"{{\\textcolor{{black!60}}{{[{lo:.1f}, {hi:.1f}]}}}}}}")


def render(table: str, m: dict, stacked: bool = False) -> str:
    fam, scopes, steps = m["families"], m["scopes"], m["new_step_scopes"]
    out = []
    for line in table.splitlines(keepends=True):
        label = line.split(" & ", 1)[0]
        if label in ROWS:
            v = m["metrics"][ROWS[label]]
            line = " & ".join([label, cell(v["paper_family"]["All"], stacked), cell(v["scope"], stacked), cell(v["new_step_scope_only"], stacked),
                               str(v["families_with_unclear_any_scope"]), f"{v['families_all_scopes_na']} \\\\\n"])
        out.append(line)
    text = "".join(out)
    text = re.sub(r"Families \(\d+\) & All scopes \(\d+\) & Step definitions \(\d+\)",
                  f"Families ({fam}) & All scopes ({scopes}) & Step definitions ({steps})", text)
    text = re.sub(r"Step definitions exclude the \d+ linked scopes", f"Step definitions exclude the {scopes - steps} linked scopes", text)
    return text


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--metrics", type=Path, required=True)
    p.add_argument("--table", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--expect-identical", action="store_true")
    a = p.parse_args()
    original = a.table.read_text(encoding="utf-8")
    text = render(original, json.loads(a.metrics.read_text(encoding="utf-8")), stacked=a.expect_identical)
    if a.expect_identical and text != original:
        raise SystemExit("rendered table differs from the committed table")
    a.out.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
