"""Final values for the Q2 new families (codebook NF-1.0) and their own agreement stratum.

Agreement is computed on the independent (pre-reconciliation) codings at the family level: for each family and field,
whether the family is positive under the frozen positive set. Final values: the reconciled coding of coder B supplies
the unit structure. Every field whose family-level value set still differs is listed as unresolved. When the two
reconciled codings also differ on family-level positivity, the field is set to `unclear` in every unit of that family
and the indicator gets lower/upper bounds; a category-level split with the same positivity keeps coder B's values.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from e0_corpus_metrics import METRICS, vals

POSITIVE = dict(METRICS)
MULTI = {"endpoint", "deployment"}
EXPECTED = {"Q006", "Q010", "Q060", "Q077", "Q085", "Q090", "Q109"}


def load(path_glob: list[Path]) -> dict[str, dict]:
    out = {}
    for p in sorted(path_glob):
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if r["family"] in out:
                    raise SystemExit(f"duplicate family {r['family']} in {p}")
                out[r["family"]] = r
    return out


def value_set(fam: dict, field: str) -> list[str]:
    """Family-level distinct values of a field, the representation stored for the frozen families."""
    return sorted({v for u in fam["units"] for v in vals(u["answers"][field])})


def positive(fam: dict, field: str) -> bool:
    return any(set(vals(u["answers"][field])) & set(POSITIVE[field]) for u in fam["units"])


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--nf-dir", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--summary", type=Path, required=True)
    a = p.parse_args()
    ind_a = load(list((a.nf_dir / "coderA").glob("*.jsonl")))
    ind_b = load(list((a.nf_dir / "coderB").glob("*.jsonl")))
    rec_a = load([a.nf_dir / "reconcile" / "coderA.jsonl"])
    rec_b = load([a.nf_dir / "reconcile" / "coderB.jsonl"])
    fams = sorted(ind_a)
    for name, d in (("A", ind_a), ("B", ind_b), ("A reconciled", rec_a), ("B reconciled", rec_b)):
        if set(d) != EXPECTED:
            raise SystemExit(f"coder {name} families {sorted(d)} differ from the expected seven")

    agreement = {f: sum(positive(ind_a[x], f) == positive(ind_b[x], f) for x in fams) for f in POSITIVE}
    unresolved, finals = [], []
    for x in fams:
        final = json.loads(json.dumps(rec_b[x]))
        if sorted(rec_a[x]["task_group"]) != sorted(rec_b[x]["task_group"]):
            final["task_group"] = sorted(set(rec_a[x]["task_group"]) | set(rec_b[x]["task_group"]))
            unresolved.append({"family": x, "field": "task_group", "A": rec_a[x]["task_group"], "B": rec_b[x]["task_group"]})
        for f in POSITIVE:
            va, vb = value_set(rec_a[x], f), value_set(rec_b[x], f)
            if va != vb:
                pa, pb = positive(rec_a[x], f), positive(rec_b[x], f)
                if pa != pb:  # indicator-level split: undecided, bounded
                    for u in final["units"]:
                        u["answers"][f] = ["unclear"] if f in MULTI else "unclear"
                unresolved.append({"family": x, "field": f, "A_values": va, "B_values": vb,
                                   "A_positive": pa, "B_positive": pb, "bounds_differ": pa != pb})
        final["unit_counts"] = {"A": len(rec_a[x]["units"]), "B": len(rec_b[x]["units"])}
        finals.append(final)

    a.out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in finals), encoding="utf-8")
    summary = {
        "families": len(fams),
        "independent_family_level_agreement": {f: f"{k}/{len(fams)}" for f, k in agreement.items()},
        "independent_agreement_total": f"{sum(agreement.values())}/{len(fams) * len(POSITIVE)}",
        "unresolved_after_reconciliation": unresolved,
        "final_positive_counts": {f: sum(positive(r, f) for r in finals) for f in POSITIVE},
        "upper_bound_positive_counts": {
            f: sum(positive(r, f) for r in finals)
            + sum(1 for u in unresolved if u.get("field") == f and u["bounds_differ"]) for f in POSITIVE},
    }
    a.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "independent_family_level_agreement"}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
