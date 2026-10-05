"""Agreement between two taxonomy codings (TX codebook): two coders, or one coder and the published-table mapping.

Statistics follow experiments/EXP-2026-004/taxonomy-codebook.md "Procedure and reporting". Both files must cover
exactly the ids in --ids; vocabularies are validated. A `null` field (published mapping only) drops that family from
that field's comparison.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from e0_screen_agreement import kappa_ac1

INTERFACES = ("S", "G", "C", "U")
PATHS = ("offline", "request_driven", "both", "unclear")
ROLES = ("intent_handler", "config_synthesis", "controller", "assurance", "planning", "policy_agent", "other")
OWNERS = ("engine", "separate_model", "controller", "tool", "human", "other")
MECHANISMS = ("model_judgment", "deterministic", "execution_test", "formal", "human_review", "other")
CHECKS = ("observation", "feasibility", "coverage")


def load(path: Path, ids: list[str]) -> dict[str, dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    got = [r["family_id"] for r in rows]
    if sorted(got) != sorted(ids) or len(set(got)) != len(got):
        raise SystemExit(f"{path}: family ids differ from the id list")
    out = {}
    for r in rows:
        fid = r["family_id"]
        for key, vocab in (("interfaces", INTERFACES), ("roles", ROLES)):
            if r[key] is not None and (not r[key] or set(r[key]) - set(vocab)):
                raise SystemExit(f"{path}:{fid}: bad {key} {r[key]}")
        if r["path"] is not None and r["path"] not in PATHS:
            raise SystemExit(f"{path}:{fid}: bad path {r['path']}")
        for c in CHECKS:
            v = r[c]
            if v is None or v == "NE":
                continue
            if not isinstance(v, list) or not v:
                raise SystemExit(f"{path}:{fid}: bad {c} {v}")
            for o in v:
                if not isinstance(o, dict) or {"component", "owner", "mechanism", "evaluated"} - set(o):
                    raise SystemExit(f"{path}:{fid}: {c} component lacks fields {o}")
                if o.get("owner") not in OWNERS + (None,) or o.get("mechanism") not in MECHANISMS + (None,):
                    raise SystemExit(f"{path}:{fid}: bad {c} component {o}")
                if o.get("evaluated") not in (True, False, None):
                    raise SystemExit(f"{path}:{fid}: bad {c} evaluated {o}")
        out[fid] = r
    return out


def stat(a: list[str], b: list[str], cats: tuple[str, ...]) -> dict:
    if not a:
        return {"n": 0}
    po, k, g = kappa_ac1(a, b, cats)
    pe_k = sum(a.count(c) * b.count(c) for c in cats) / len(a) ** 2
    return {"n": len(a), "agreement": round(po, 3), "kappa": None if pe_k == 1 else round(k, 3), "ac1": round(g, 3)}


def exact(a: list, b: list) -> dict:
    return {"n": len(a), "exact": round(sum(x == y for x, y in zip(a, b)) / len(a), 3)} if a else {"n": 0}


def multiselect(A: dict, B: dict, ids: list[str], key: str, vocab: tuple[str, ...]) -> dict:
    keep = [i for i in ids if A[i][key] is not None and B[i][key] is not None]
    out = {"exact_set": exact([set(A[i][key]) for i in keep], [set(B[i][key]) for i in keep])}
    for v in vocab:
        out[v] = stat([str(v in A[i][key]) for i in keep], [str(v in B[i][key]) for i in keep], ("True", "False"))
    return out


def check(A: dict, B: dict, ids: list[str], c: str) -> dict:
    keep = [i for i in ids if A[i][c] is not None and B[i][c] is not None]
    perf = lambda r: str(r[c] != "NE")
    out = {"performed": stat([perf(A[i]) for i in keep], [perf(B[i]) for i in keep], ("True", "False"))}
    both = [i for i in keep if A[i][c] != "NE" and B[i][c] != "NE"]
    for name, keys in (("owner", ("owner",)), ("mechanism", ("mechanism",)), ("owner_mechanism", ("owner", "mechanism"))):
        f = lambda v: frozenset(tuple(o[k] for k in keys) for o in v)
        sub = [i for i in both if all(o[k] is not None for o in A[i][c] + B[i][c] for k in keys)]
        out[name] = exact([f(A[i][c]) for i in sub], [f(B[i][c]) for i in sub])
    def ev(v):
        vals = [o["evaluated"] for o in v]
        return "True" if True in vals else ("False" if all(x is False for x in vals) else None)
    sub = [i for i in both if ev(A[i][c]) is not None and ev(B[i][c]) is not None]
    out["any_evaluated"] = stat([ev(A[i][c]) for i in sub], [ev(B[i][c]) for i in sub], ("True", "False"))
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--ids", type=Path, required=True)
    p.add_argument("--a", type=Path, required=True)
    p.add_argument("--b", type=Path, required=True)
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    ids = [x for x in args.ids.read_text().split() if x]
    A, B = load(args.a, ids), load(args.b, ids)
    keep = [i for i in ids if A[i]["path"] is not None and B[i]["path"] is not None]
    res = {"families": len(ids),
           "interfaces": multiselect(A, B, ids, "interfaces", INTERFACES),
           "path": stat([A[i]["path"] for i in keep], [B[i]["path"] for i in keep], PATHS),
           "roles": multiselect(A, B, ids, "roles", ROLES),
           **{c: check(A, B, ids, c) for c in CHECKS}}
    text = json.dumps(res, indent=1)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
