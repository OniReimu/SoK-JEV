"""Final title/abstract decisions after reconciliation and the coverage-audit sample.

Final decision: the shared decision where the coders agreed before or after reconciliation, otherwise include
(codebook SCR-1.0 reconciliation rule). The sampling frame is all final includes; 50 per stratum are drawn with a
fixed seed before any full-text access is checked.
"""

from __future__ import annotations

import argparse
import json
import random
import re
from collections import Counter
from pathlib import Path

LM_PATTERN = re.compile(
    r"LLM|language model|GPT|generative AI|GenAI|agentic|\bagents?\b|natural language|NLP|\bSLM", re.IGNORECASE
)
PER_STRATUM = 50
SEED = 42


def load_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--screen-dir", type=Path, required=True)
    args = parser.parse_args()
    s = args.screen_dir
    inputs = load_rows(s / "screening_input.jsonl")
    coder = {c: {r["screen_id"]: r for b in sorted((s / c).glob("*.jsonl")) for r in load_rows(b)} for c in ("coderA", "coderB")}
    disagreements = [r["record"]["screen_id"] for r in load_rows(s / "disagreements.jsonl")]
    recon = {}
    for c in ("coderA", "coderB"):
        rows = load_rows(s / "reconcile" / f"{c}.jsonl")
        if [r["screen_id"] for r in rows] != disagreements:
            raise SystemExit(f"reconcile/{c}.jsonl does not cover the disagreement list in order")
        recon[c] = {r["screen_id"]: r["final_decision"] for r in rows}

    final, route = {}, Counter()
    for rec in inputs:
        i = rec["screen_id"]
        a, b = coder["coderA"][i]["decision"], coder["coderB"][i]["decision"]
        if a == b:
            final[i], how = a, "agreed"
        elif recon["coderA"][i] == recon["coderB"][i]:
            final[i], how = recon["coderA"][i], "reconciled"
        else:
            final[i], how = "include", "split_to_fulltext"
        route[how] += 1

    frame = [r for r in inputs if final[r["screen_id"]] == "include"]
    omitted_strata = json.loads((s / "omitted_abstract_strata.json").read_text())
    strata = {"lm": [], "pre_llm": []}
    for r in frame:
        strata[omitted_strata[r["screen_id"]] if r["abstract"] == '[omitted: indexed abstract longer than 3,000 characters]' else ("lm" if LM_PATTERN.search(r["title"] + " " + r["abstract"]) else "pre_llm")].append(r)
    rng = random.Random(SEED)
    sample = []
    for name in ("lm", "pre_llm"):
        ids = sorted(r["screen_id"] for r in strata[name])
        for i in rng.sample(ids, PER_STRATUM):
            rec = next(r for r in strata[name] if r["screen_id"] == i)
            sample.append({**rec, "stratum": name})

    with (s / "final_decisions.jsonl").open("w", encoding="utf-8") as fh:
        for r in inputs:
            fh.write(json.dumps({"screen_id": r["screen_id"], "final_decision": final[r["screen_id"]]}) + "\n")
    with (s / "audit_sample.jsonl").open("w", encoding="utf-8") as fh:
        for r in sample:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    summary = {
        "records": len(inputs),
        "routes": dict(route),
        "final": dict(Counter(final.values())),
        "frame": len(frame),
        "strata": {k: len(v) for k, v in strata.items()},
        "sample": dict(Counter(r["stratum"] for r in sample)),
        "seed": SEED,
    }
    (s / "final_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
