"""Cross-tabulate the published three-axis systematization against the 18-field reporting indicators (139 families).

Axes come from paper/supplement/systematization.csv (interfaces S/G/C, check columns NE or owned). Indicators use the
frozen family statistic of e0_corpus_metrics.py (positive when any scope is positive). Descriptive counts only.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from e0_corpus_metrics import METRICS, extend, load_frozen, vals

ROOT = Path(__file__).resolve().parents[2]
CSV = ROOT / "supplement" / "systematization.csv"
FIELDS = ("loop_claim", "loop_match", "tail", "deadline", "load", "baseline", "final_state", "gate_separation")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--coding-tar", type=Path, required=True)
    p.add_argument("--eligibility", type=Path, required=True)
    p.add_argument("--new-families", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    ids, by_group, tasks = load_frozen(a.coding_tar, a.eligibility)
    extend(ids, by_group, tasks, a.new_families)
    rows = {r["family_id"]: r for r in csv.DictReader(CSV.open(newline="", encoding="utf-8"))}
    if set(rows) != set(ids):
        raise SystemExit(f"family sets differ: csv-only {sorted(set(rows) - set(ids))}, coding-only {sorted(set(ids) - set(rows))}")
    positive = dict(METRICS)
    hit = {f: {g: any(set(vals(u["answers"][f])) & set(positive[f]) for u in by_group[g]) for g in ids} for f in FIELDS}
    iface = {g: set(rows[g]["interfaces"].split("/")) for g in ids}
    owned = {c: {g: rows[g][f"{c}_check"] != "NE" for g in ids} for c in ("observation", "feasibility", "coverage")}

    groups = {
        "all": ids,
        "has_S": [g for g in ids if "S" in iface[g]], "has_G": [g for g in ids if "G" in iface[g]],
        "has_C": [g for g in ids if "C" in iface[g]],
        "G_only": [g for g in ids if iface[g] == {"G"}], "S_only": [g for g in ids if iface[g] == {"S"}],
        "C_only": [g for g in ids if iface[g] == {"C"}],
        "no_C": [g for g in ids if "C" not in iface[g]],
        "U_only": [g for g in ids if iface[g] == {"U"}],
        "mixed_no_C": [g for g in ids if "C" not in iface[g] and len(iface[g]) > 1],
        "mixed_with_C": [g for g in ids if "C" in iface[g] and len(iface[g]) > 1],
        "feasibility_owned": [g for g in ids if owned["feasibility"][g]],
        "feasibility_NE": [g for g in ids if not owned["feasibility"][g]],
        "loop_claim": [g for g in ids if hit["loop_claim"][g]],
    }
    rows_ = ("S_only", "G_only", "U_only", "mixed_no_C", "C_only", "mixed_with_C")
    if sum(len(groups[r]) for r in rows_) != len(ids) or len({g for r in rows_ for g in groups[r]}) != len(ids):
        raise SystemExit("interface rows do not partition the families")
    out = {"families": len(ids), "groups": {}}
    for name, gs in groups.items():
        out["groups"][name] = {
            "n": len(gs),
            **{f: sum(hit[f][g] for g in gs) for f in FIELDS},
            **{f"{c}_owned": sum(owned[c][g] for g in gs) for c in owned},
            "any_check_owned": sum(any(owned[c][g] for c in owned) for g in gs),
        }
    from collections import Counter
    out["interface_sets"] = dict(Counter("/".join(sorted(iface[g], key="SGCU".index)) for g in ids).most_common())
    a.out.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
