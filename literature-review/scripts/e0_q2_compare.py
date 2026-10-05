"""Final Q2 second-screening decisions and their comparison with the original screening.

Final decision: shared coder decision, else shared reconciled decision, else include (codebook SCR-1.0). A record
whose final decision is include while the original was background/exclusion goes to full-text verification.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def rows(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--q2-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    q = args.q2_dir
    key = {r["screen_id"]: r for r in rows(q / "q2_key.jsonl")}
    coder = {c: {r["screen_id"]: r["decision"] for b in sorted((q / c).glob("*.jsonl")) for r in rows(b)} for c in ("coderA", "coderB")}
    recon = {c: {r["screen_id"]: r["final_decision"] for r in rows(q / "reconcile" / f"{c}.jsonl")} for c in ("coderA", "coderB")}
    if set(coder["coderA"]) != set(key) or set(coder["coderB"]) != set(key):
        raise SystemExit("coder outputs do not cover the Q2 units")
    final, route = {}, Counter()
    for i in key:
        a, b = coder["coderA"][i], coder["coderB"][i]
        if a == b:
            final[i], how = a, "agreed"
        elif recon["coderA"].get(i) == recon["coderB"].get(i) and i in recon["coderA"]:
            final[i], how = recon["coderA"][i], "reconciled"
        else:
            final[i], how = "include", "split_to_fulltext"
        route[how] += 1
    original_class = {"TA-B": "background", "TA-X": "exclude", "FT-background": "background"}
    flips = [i for i in key if final[i] == "include"]
    summary = {
        "units": len(key),
        "routes": dict(route),
        "final": dict(Counter(final.values())),
        "by_original": {o: dict(Counter(final[i] for i in key if key[i]["original"] == o)) for o in original_class},
        "same_class_as_original": sum(final[i] == original_class[key[i]["original"]] for i in key),
        "to_fulltext_check": [{"screen_id": i, "catalog_id": key[i]["catalog_id"], "original": key[i]["original"],
                               "original_reason": key[i]["reason"], "route": "include"} for i in flips],
    }
    args.out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "to_fulltext_check"}, indent=2))
    for f in summary["to_fulltext_check"]:
        print(f["screen_id"], f["catalog_id"], f["original"], "|", f["original_reason"][:90])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
