"""E0 reporting indicators for the frozen 132-family corpus, optionally extended with new families.

Reuses the statistic of the frozen analysis (src/studies/sok/analysis/coding.py): a family is positive on a field when
at least one included scope has a positive code; whole-family bootstrap, seed 42, 10,000 replicates, one shared weight
matrix per stratum; task strata are the union of task labels of a family's reports. With no extension file the output
must reproduce the frozen results exactly (checked by --check-frozen).
"""

from __future__ import annotations

import argparse
import json
import tarfile
from pathlib import Path

import numpy as np

SEED, REPLICATES = 42, 10000
METRICS = [
    ("endpoint", ["model", "dispatch", "network", "service", "other"]),
    ("denominator", ["all", "success", "other", "mixed"]),
    ("tail", ["yes"]), ("deadline", ["yes"]), ("load", ["yes"]), ("queue", ["yes"]),
    ("stability", ["yes"]), ("baseline", ["yes"]),
    ("loop_claim", ["rt", "near_rt", "non_rt", "other"]),
    ("loop_match", ["matched"]),
    ("deployment", ["hosted", "gpu", "edge", "cpu", "other"]),
    ("roundtrip", ["included"]),
    ("format", ["reported"]), ("semantic", ["reported"]), ("final_state", ["reported"]),
    ("gate_separation", ["three"]), ("code", ["public_link"]), ("data", ["public_link"]),
]
TASKS = {"Configuration": "配置", "Orchestration": "编排", "Diagnosis": "诊断"}
NEW_TASKS = {"configuration": "配置", "orchestration": "编排", "diagnosis": "诊断"}


def vals(x):
    return x if isinstance(x, list) else [x]


def load_frozen(coding_tar: Path, eligibility: Path):
    with tarfile.open(coding_tar) as tar:
        final = json.load(tar.extractfile("E0-review/E0-final.json"))
        view = json.load(tar.extractfile("E0-review/E0-paper-view.json"))
    prep = {r["id"]: r for r in json.loads(eligibility.read_text(encoding="utf-8"))["records"]}
    groups = [g for g in view["groups"] if g["scope_decision"] == "include"]
    ids = [g["id"] for g in groups]
    units = final["units"]
    by_group = {g: [u for u in units if u["group"] == g] for g in ids}
    tasks = {g["id"]: sorted({t for r in g["source_reports"] for t in (prep[r].get("task_group") or "").split("/") if t})
             for g in groups}
    return ids, by_group, tasks


def extend(ids, by_group, tasks, new_path: Path):
    for line in new_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        fam = json.loads(line)
        gid = fam["family"]
        assert gid not in by_group, gid
        ids.append(gid)
        by_group[gid] = [{"id": u["uid"], "group": gid, "relation": u["relation"], "answers": u["answers"]}
                         for u in fam["units"]]
        tasks[gid] = sorted(NEW_TASKS[t] for t in fam["task_group"])
        assert tasks[gid] and by_group[gid]


def compute(ids, by_group, tasks):
    strata = {"All": ids, **{n: [g for g in ids if t in tasks[g]] for n, t in TASKS.items()}}
    rng = np.random.default_rng(SEED)
    weights = {s: rng.multinomial(len(gs), np.full(len(gs), 1 / len(gs)), size=REPLICATES) for s, gs in strata.items()}

    def rate(positive, total, stratum="All"):
        a, b = np.array(positive, dtype=float), np.array(total, dtype=float)
        samples = weights[stratum] @ a / (weights[stratum] @ b)
        ci = np.quantile(samples, [0.025, 0.975], method="linear").tolist()
        return {"positive": int(sum(a)), "n": int(sum(b)), "proportion": float(sum(a) / sum(b)), "ci95": ci}

    out = {"families": len(ids), "scopes": sum(len(v) for v in by_group.values()),
           "new_step_scopes": sum(u["relation"] == "new_step" for v in by_group.values() for u in v),
           "strata_sizes": {s: len(g) for s, g in strata.items()}, "metrics": {}}
    for f, positive in METRICS:
        match = lambda u: bool(set(vals(u["answers"][f])) & set(positive))  # noqa: E731
        hit = {g: [u for u in by_group[g] if match(u)] for g in ids}
        out["metrics"][f] = {
            "paper_family": {s: rate([bool(hit[g]) for g in gs], [1] * len(gs), s) for s, gs in strata.items()},
            "scope": rate([len(hit[g]) for g in ids], [len(by_group[g]) for g in ids]),
            "new_step_scope_only": rate(
                [sum(match(u) and u["relation"] == "new_step" for u in by_group[g]) for g in ids],
                [sum(u["relation"] == "new_step" for u in by_group[g]) for g in ids]),
            "families_with_unclear_any_scope": sum(any("unclear" in vals(u["answers"][f]) for u in by_group[g]) for g in ids),
            "families_all_scopes_na": sum(all(vals(u["answers"][f]) == ["na"] for u in by_group[g]) for g in ids),
        }
    return out


def check_frozen(out, results_path: Path) -> None:
    ref = json.loads(results_path.read_text(encoding="utf-8"))
    for m in ref["metrics"]:
        mine = out["metrics"][m["field"]]
        for s, r in m["paper_family"].items():
            assert mine["paper_family"][s]["positive"] == r["positive"], (m["field"], s)
            assert np.allclose(mine["paper_family"][s]["ci95"], r["ci95"], atol=1e-12), (m["field"], s)
        assert mine["scope"]["positive"] == m["scope"]["positive"], m["field"]
        assert np.allclose(mine["scope"]["ci95"], m["scope"]["ci95"], atol=1e-12), m["field"]
        assert mine["new_step_scope_only"]["positive"] == m["new_step_scope_only"]["positive"], m["field"]
        assert np.allclose(mine["new_step_scope_only"]["ci95"], m["new_step_scope_only"]["ci95"], atol=1e-12), m["field"]
        assert mine["families_with_unclear_any_scope"] == m["families_with_unclear_any_scope"], m["field"]
        assert mine["families_all_scopes_na"] == m["families_all_scopes_na"], m["field"]
    print("frozen 132-family results reproduced exactly")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--coding-tar", type=Path, required=True)
    p.add_argument("--eligibility", type=Path, required=True)
    p.add_argument("--new-families", type=Path)
    p.add_argument("--check-frozen", type=Path, help="frozen results.json to compare against (no extension)")
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    ids, by_group, tasks = load_frozen(a.coding_tar, a.eligibility)
    if a.new_families:
        extend(ids, by_group, tasks, a.new_families)
    out = compute(ids, by_group, tasks)
    if a.check_frozen:
        assert not a.new_families
        check_frozen(out, a.check_frozen)
    a.out.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"families": out["families"], "scopes": out["scopes"], "strata": out["strata_sizes"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
