"""Pre-reconciliation agreement between the two title/abstract screeners and the disagreement list.

Fails closed unless both coders return exactly one valid row per input record, in input order.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

DECISIONS = ("include", "background", "exclude")


def load_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_coder(screen_dir: Path, coder: str, batches: list[Path]) -> dict[str, dict]:
    found = {p.name for p in (screen_dir / coder).glob("*.jsonl")}
    if found != {b.name for b in batches}:
        raise SystemExit(f"{coder}: output files {sorted(found)} differ from input batches")
    rows: dict[str, dict] = {}
    for batch in batches:
        expected = [r["screen_id"] for r in load_rows(batch)]
        got = load_rows(screen_dir / coder / batch.name)
        if [r.get("screen_id") for r in got] != expected:
            raise SystemExit(f"{coder}/{batch.name}: screen_id sequence differs from input")
        for r in got:
            if r.get("decision") not in DECISIONS:
                raise SystemExit(f"{coder}/{batch.name}: invalid decision for {r['screen_id']}")
            rows[r["screen_id"]] = r
    return rows


def kappa_ac1(a: list[str], b: list[str], categories: tuple[str, ...]) -> tuple[float, float, float]:
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe_k = sum(ca[c] * cb[c] for c in categories) / n**2
    pi = {c: (ca[c] + cb[c]) / (2 * n) for c in categories}
    q = len(categories)
    pe_g = sum(p * (1 - p) for p in pi.values()) / (q - 1)
    kappa = (po - pe_k) / (1 - pe_k) if pe_k < 1 else 1.0
    ac1 = (po - pe_g) / (1 - pe_g) if pe_g < 1 else 1.0
    return po, kappa, ac1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--screen-dir", type=Path, required=True)
    args = parser.parse_args()
    batches = sorted((args.screen_dir / "batches").glob("batch-*.jsonl"))
    canonical = [r["screen_id"] for r in load_rows(args.screen_dir / "screening_input.jsonl")]
    if [r["screen_id"] for b in batches for r in load_rows(b)] != canonical:
        raise SystemExit("input batches do not reproduce screening_input.jsonl in order")
    a_rows = load_coder(args.screen_dir, "coderA", batches)
    b_rows = load_coder(args.screen_dir, "coderB", batches)
    ids = list(a_rows)
    a = [a_rows[i]["decision"] for i in ids]
    b = [b_rows[i]["decision"] for i in ids]
    to_bin = lambda xs: ["include" if x == "include" else "other" for x in xs]  # noqa: E731
    po3, k3, g3 = kappa_ac1(a, b, DECISIONS)
    po2, k2, g2 = kappa_ac1(to_bin(a), to_bin(b), ("include", "other"))
    summary = {
        "records": len(ids),
        "coderA": dict(Counter(a)),
        "coderB": dict(Counter(b)),
        "three_class": {"exact": po3, "kappa": k3, "ac1": g3},
        "include_vs_not": {"exact": po2, "kappa": k2, "ac1": g2},
        "both_include": sum(x == y == "include" for x, y in zip(a, b)),
        "disagreements": sum(x != y for x, y in zip(a, b)),
        "crosstab": {f"{x}|{y}": n for (x, y), n in sorted(Counter(zip(a, b)).items())},
    }
    (args.screen_dir / "agreement.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    inputs = {r["screen_id"]: r for batch in batches for r in load_rows(batch)}
    with (args.screen_dir / "disagreements.jsonl").open("w", encoding="utf-8") as fh:
        for i in ids:
            if a_rows[i]["decision"] != b_rows[i]["decision"]:
                fh.write(json.dumps({"record": inputs[i], "coderA": a_rows[i], "coderB": b_rows[i]}, ensure_ascii=False) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
