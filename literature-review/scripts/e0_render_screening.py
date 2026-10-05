"""Render the screening-flow figure (Fig. 2) with the frozen drawing code, extended by a fourth stage.

Executes src/scripts/sok_concept_figures.py unchanged except for its output and input paths. --control renders the
frozen render_screening() so the result can be compared with the committed figure. Without --control, the frozen
three stages are drawn unchanged and a fourth band records the blind second screening (added families) and the
OpenAlex coverage audit, with counts read from the EXP-2026-004 aggregates.
"""

from __future__ import annotations

import argparse
import json
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
JEV = HERE.parents[1]
SOURCE = JEV / "scripts" / "sok_concept_figures.py"
AGG = JEV / "literature-review" / "results"
EXTRA_HEIGHT = 228


def load_module(out_dir: Path, ledger: Path, method_tex: Path) -> dict:
    src = SOURCE.read_text(encoding="utf-8")
    for old, new in [("PAPER = ROOT / 'paper-sok-csur'", f"PAPER = Path({str(out_dir)!r})"),
                     ("WORK = ROOT / 'artifacts/sok/concept-redesign'", f"WORK = Path({str(out_dir / 'preview')!r})"),
                     ("ledger=ROOT/'docs/sok/e0-current/analysis/screening-flow-source.json'", f"ledger=Path({str(ledger)!r})"),
                     ("(PAPER/'sections/review-method.tex')", f"Path({str(method_tex)!r})"),
                     ("svg=str(target.relative_to(ROOT)),pdf=str(pdf.relative_to(ROOT))", "svg=str(target),pdf=str(pdf)")]:
        assert src.count(old) == 1, old
        src = src.replace(old, new)
    ns = {"__name__": "sok_concept_figures_screening", "__file__": str(SOURCE)}
    exec(compile(src.split("\nif __name__==")[0], str(SOURCE), "exec"), ns)
    return ns


def extended(ns: dict, counts: dict) -> None:
    """Frozen render_screening() with a taller canvas and a fourth stage."""
    frozen = ns["render_screening"]
    Drawing = ns["Drawing"]

    class Taller(Drawing):
        def __init__(self, width, height, title, description, vertical_scale=1):
            super().__init__(width, height + EXTRA_HEIGHT, title, description, vertical_scale)
            self._extra = counts

        def export(self, relative, preview):
            stage_four(self, ns, self._extra)
            return super().export(relative, preview)

    ns["Drawing"] = Taller
    try:
        frozen()
    finally:
        ns["Drawing"] = Drawing


def stage_four(d, ns: dict, k: dict) -> None:
    C, icon = ns["C"], ns["screening_icon"]
    y0 = 688
    d.rect(4, y0, 2008, EXTRA_HEIGHT - 12, C["warm"], stroke="none")
    # Row 1: blind second screening of every set-aside record.
    row = y0 + 16
    boxes = [(24, 330, C["blue"], f"{k['set_aside']} set-aside records", f"{k['ta_b']} + {k['ta_x']} + {k['ft_bg']} from stage 2"),
             (410, 370, C["beige"], "Blind second screen", "two model coders"),
             (836, 330, C["blue"], f"{k['to_fulltext']} full-text checks", f"{k['eligible']} eligible · {k['split']} split"),
             (1222, 300, C["amber"], f"+{k['eligible']} families", f"{k['new_scopes']} coded scopes")]
    for x, w, fill, a, b in boxes:
        d.rect(x, row, w, 80, fill)
        d.text(x + w / 2, row + 34, a, 32, bold=True, max_width=w - 20)
        d.text(x + w / 2, row + 67, b, 28, max_width=w - 20)
    for (x, w, *_), (nx, *_) in zip(boxes, boxes[1:]):
        d.line([(x + w, row + 40), (nx - 4, row + 40)], arrow=True)
    d.line([(1522, row + 40), (1580, row + 40)], arrow=True)
    d.rect(1584, row - 6, 404, 92, C["amber"])
    icon(d, "folder", 1598, row + 6)
    d.text(1810, row + 34, f"{k['families']} analysed families", 34, bold=True, max_width=330)
    d.text(1830, row + 70, f"{k['scopes']} scopes · {k['steps']} steps", 27, max_width=300)
    # Row 2: OpenAlex coverage audit, outside the analysed set.
    row2 = row + 106
    boxes2 = [(24, 330, f"{k['oa_unique']} OpenAlex works", f"−{k['oa_in_corpus']} already in corpus"),
              (410, 370, f"{k['oa_new']} screened", f"{k['oa_pass']} pass title / abstract"),
              (836, 330, f"{k['sample']} sampled", f"{k['sample'] // 2} + {k['sample'] // 2} by stratum"),
              (1222, 430, f"{k['coded']} coded · {k['coded_eligible']} eligible", "coverage audit, not added")]
    for x, w, a, b in boxes2:
        d.rect(x, row2, w, 70, C["light"], dash="6 4" if "audit" in b else None)
        d.text(x + w / 2, row2 + 30, a, 30, bold=True, max_width=w - 20)
        d.text(x + w / 2, row2 + 60, b, 27, max_width=w - 20)
    for (x, w, *_), (nx, *_) in zip(boxes2, boxes2[1:]):
        d.line([(x + w, row2 + 35), (nx - 4, row2 + 35)], arrow=True)
    d.tab(1662, row2 + 52, "4. Verification + coverage", 30)


def counts_from_aggregates(AGG: Path) -> dict:
    q2 = json.loads((AGG / "q2-second-screening.json").read_text())
    nf = json.loads((AGG / "corpus-139-metrics.json").read_text())
    rec = json.loads((AGG / "screening-final.json").read_text())
    audit = json.loads((AGG / "coverage-audit-summary.json").read_text())
    by = q2["by_original"]
    return {
        "set_aside": q2["units"], "ta_b": sum(by["TA-B"].values()), "ta_x": sum(by["TA-X"].values()),
        "ft_bg": sum(by["FT-background"].values()), "to_fulltext": len(q2["to_fulltext_check"]),
        "eligible": nf["families"] - 132, "split": 2, "new_scopes": nf["scopes"] - 405,
        "families": nf["families"], "scopes": nf["scopes"], "steps": nf["new_step_scopes"],
        "oa_unique": 966, "oa_in_corpus": 966 - rec["records"], "oa_new": rec["records"], "oa_pass": rec["final"]["include"],
        "sample": sum(rec["sample"].values()), "coded": audit["coded"],
        "coded_eligible": sum(v["eligible"] for v in audit["by_stratum"].values()),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--analysis-tar", type=Path, required=True)
    p.add_argument("--method-tex", type=Path, default=JEV / "literature-review/results/screening-method-counts.txt")
    p.add_argument("--results-dir", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--control", action="store_true")
    a = p.parse_args()
    a.out_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(a.analysis_tar) as tar:
        member = tar.extractfile("docs/sok/e0-current/analysis/screening-flow-source.json")
        ledger = a.out_dir / "screening-flow-source.json"
        ledger.write_bytes(member.read())
    ns = load_module(a.out_dir, ledger, a.method_tex)
    if a.control:
        ns["render_screening"]()
    else:
        k = counts_from_aggregates(a.results_dir)
        print(json.dumps(k))
        extended(ns, k)
    print("rendered", a.out_dir / "figures" / "screening-flow.pdf")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
