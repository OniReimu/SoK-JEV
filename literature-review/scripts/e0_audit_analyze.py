"""Coverage-audit estimates for the four headline fields.

Joins coded rows with the complete retrieval manifest. Final value per field: the coders' shared value, else the
shared reconciled value, else unresolved. Reports per-stratum counts with Wilson intervals, a frame-weighted
estimate among eligible records, and bounds treating every inaccessible draw and every unresolved value as negative
(lower) or positive and eligible (upper).
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import random
from pathlib import Path

FIELDS = ("eligibility", "explicit_loop_claim", "supported_loop_claim", "tail_latency", "deadline_attainment")
CLAIMS = {"RT/fast", "near-RT", "non-RT", "other budget or multiple loops"}
INDICATORS = {  # name -> (source field, positive test)
    "loop_claim": ("explicit_loop_claim", lambda v: v in CLAIMS),
    "matched_claim": ("supported_loop_claim", lambda v: v == "matched"),
    "tail_p95": ("tail_latency", lambda v: v == "reported"),
    "deadline": ("deadline_attainment", lambda v: v == "reported"),
}
BOOT = 2000
SEED = 42
MAR_NOTE = (
    "The frame-weighted estimate and its interval assume that access and coding are missing at random within "
    "stratum; the bounds make no such assumption."
)
CORPUS = {"loop_claim": 48, "matched_claim": 4, "tail_p95": 9, "deadline": 4}  # of 132 families


def load_rows(paths: list[str]) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for p in sorted(paths):
        for line in Path(p).read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                rows[r["screen_id"]] = r
    return rows


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--screen-dir", type=Path, required=True)
    args = parser.parse_args()
    s = args.screen_dir
    manifest = load_rows([str(s / "retrieval_log.jsonl")])
    summary = json.loads((s / "final_summary.json").read_text(encoding="utf-8"))
    frame = summary["strata"]
    a = load_rows(glob.glob(str(s / "audit/coderA/*.jsonl")))
    b = load_rows(glob.glob(str(s / "audit/coderB/*.jsonl")))
    ra = load_rows(glob.glob(str(s / "audit/reconcile/coderA*.jsonl")))
    rb = load_rows(glob.glob(str(s / "audit/reconcile/coderB*.jsonl")))
    if set(a) != set(b):
        raise SystemExit("coders A and B coded different record sets")

    final: dict[str, dict] = {}
    for i in a:
        row = {}
        for f in FIELDS:
            va, vb = a[i][f], b[i][f]
            if va == vb:
                row[f] = va
            elif i in ra and i in rb and ra[i][f] == rb[i][f]:
                row[f] = ra[i][f]
            else:
                row[f] = "UNRESOLVED"
        final[i] = row

    out = {"coded": len(final), "draws": len(manifest), "by_stratum": {}, "weighted": {}, "bounds": {}, "corpus": {}}
    per = {}
    for st in ("lm", "pre_llm"):
        draws = [i for i, m in manifest.items() if m["stratum"] == st]
        coded = [i for i in draws if i in final]
        elig = [i for i in coded if final[i]["eligibility"] == "eligible"]
        unres_elig = [i for i in coded if final[i]["eligibility"] == "UNRESOLVED"]
        res = {"draws": len(draws), "coded": len(coded), "eligible": len(elig), "eligibility_unresolved": len(unres_elig)}
        for name, (field, fn) in INDICATORS.items():
            k = sum(fn(final[i][field]) for i in elig)
            unres = sum(final[i][field] == "UNRESOLVED" for i in elig)
            lo, hi = wilson(k, len(elig))
            res[name] = {"k": k, "n": len(elig), "wilson95": [lo, hi], "field_unresolved": unres}
            missing = len(draws) - len(coded) + len(unres_elig)
            # bounds over draws: lower = missing all eligible-negative; upper = missing all eligible-positive
            res[name]["lower_counts"] = [k, len(elig) + missing]
            res[name]["upper_counts"] = [k + missing + unres, len(elig) + missing]
            out["bounds"].setdefault(name, {})[st] = {
                "lower": k / (len(elig) + missing) if len(elig) + missing else math.nan,
                "upper": (k + missing + unres) / (len(elig) + missing) if len(elig) + missing else math.nan,
            }
        res["_elig_ids"] = elig
        per[st] = res
    out["by_stratum"] = per
    rng = random.Random(SEED)
    coded_ids = {st: [i for i, m in manifest.items() if m["stratum"] == st and i in final] for st in per}

    def ratio(sample: dict[str, list[str]], field: str, fn) -> float:
        num = den = 0.0
        for st, ids in sample.items():
            if not ids:
                continue
            w = frame[st] / len(ids)
            elig = [i for i in ids if final[i]["eligibility"] == "eligible"]
            num += w * sum(fn(final[i][field]) for i in elig)
            den += w * len(elig)
        return num / den if den else math.nan

    for name, (field, fn) in INDICATORS.items():
        point = ratio(coded_ids, field, fn)
        boots = sorted(
            v
            for v in (
                ratio({st: [rng.choice(ids) for _ in ids] for st, ids in coded_ids.items()}, field, fn)
                for _ in range(BOOT)
            )
            if not math.isnan(v)
        )
        ci = [boots[int(0.025 * len(boots))], boots[int(0.975 * len(boots)) - 1]] if boots else [math.nan, math.nan]
        out["weighted"][name] = {"estimate": point, "bootstrap95": ci}
        agg = {}
        for side in ("lower", "upper"):
            num = den = 0.0
            for st in per:
                if per[st]["draws"]:
                    w = frame[st] / per[st]["draws"]
                    kk, nn = per[st][name][f"{side}_counts"]
                    num += w * kk
                    den += w * nn
            agg[side] = num / den if den else math.nan
        out["bounds"][name]["frame_weighted"] = agg
        out["corpus"][name] = CORPUS[name] / 132
    for st in per:
        per[st].pop("_elig_ids", None)
    out["assumption"] = MAR_NOTE
    (s / "audit" / "audit_summary.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    (s / "audit" / "final_rows.jsonl").write_text(
        "".join(json.dumps({"screen_id": i, **r}) + "\n" for i, r in sorted(final.items())), encoding="utf-8"
    )
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
