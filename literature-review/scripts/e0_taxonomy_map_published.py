"""Map the published systematization rows into the frozen TX codebook fields (third, blind pass).

The model sees only the codebook and the published CSV cells, 5 rows per request, 8 requests in flight, and returns one JSON object per
row. `interfaces` is copied from the CSV cell, not from the model. Output is validated by e0_taxonomy_agreement.load.
"""

from __future__ import annotations

import argparse
import csv
import json
import tempfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from e0_taxonomy_agreement import load

ROOT = Path(__file__).resolve().parents[2]
CODEBOOK = ROOT / "literature-review" / "codebooks" / "taxonomy-codebook.md"
CSV = ROOT / "supplement" / "systematization.csv"
CHUNK = 5
CELLS = ("workflow_detail", "observation_check", "observation_detail", "feasibility_check", "feasibility_detail",
         "coverage_check", "coverage_detail")
FIELDS = ("family_id", "interfaces", "path", "roles", "observation", "feasibility", "coverage", "evidence")
INSTRUCTIONS = """You map rows of a published systematization table into a frozen coding scheme. The codebook follows.
Use only each row's cells. For each row return an object with keys family_id, path, roles, observation, feasibility,
coverage, evidence:
- path from workflow_detail only (offline / request_driven / both); null if the cells do not settle it.
- roles from workflow_detail (its leading role phrase names the receiving component); null if not settled.
- each check: "NE" when its *_check cell is NE; otherwise a list with one object per component named in the *_check
  and *_detail cells, with keys component (at most six words), owner, mechanism, evaluated, mapped by the codebook
  definitions, using only that check's *_check and *_detail cells. Use null for owner, mechanism or evaluated when
  those cells do not settle it.
  A check described as proposed or architectural only has evaluated false.
- evidence: at most 30 words quoting the cell phrases relied on.
Values must come from the codebook vocabularies or be null. Reply with a JSON object {"rows": [...]} and nothing else.

"""


def request(rows: list[dict], codebook: str, model: str, key: str) -> list[dict]:
    body = {"model": model, "temperature": 0, "response_format": {"type": "json_object"}, "reasoning": {"effort": "low"},
            "messages": [{"role": "system", "content": INSTRUCTIONS + codebook},
                         {"role": "user", "content": json.dumps([{k: r[k] for k in ("family_id",) + CELLS} for r in rows])}]}
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as resp:
        data = json.load(resp)
    out = json.loads(data["choices"][0]["message"]["content"])["rows"]
    if [o["family_id"] for o in out] != [r["family_id"] for r in rows]:
        raise ValueError("returned ids differ from the request")
    mapped = []
    for r, o in zip(rows, out):
        missing = set(FIELDS) - {"interfaces"} - set(o)
        if missing or not isinstance(o["evidence"], str):
            raise ValueError(f"{r['family_id']}: missing fields {sorted(missing)} or non-text evidence")
        o["interfaces"] = r["interfaces"].split("/")
        mapped.append({k: o[k] for k in FIELDS})
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as tmp:
        tmp.write("".join(json.dumps(m) + "\n" for m in mapped))
    try:
        load(Path(tmp.name), [r["family_id"] for r in rows])
    finally:
        Path(tmp.name).unlink()
    return mapped


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--model", default="z-ai/glm-5.3-flash")
    p.add_argument("--env", type=Path, default=ROOT.parent / ".env")
    a = p.parse_args()
    key = next(line.split("=", 1)[1].strip().strip('"') for line in a.env.read_text().splitlines()
               if line.startswith("OPENROUTER_API_KEY="))
    rows = list(csv.DictReader(CSV.open(newline="", encoding="utf-8")))
    codebook = CODEBOOK.read_text(encoding="utf-8")
    cache = a.out.parent / "map_chunks"
    cache.mkdir(exist_ok=True)

    def run(i: int) -> list[dict]:
        chunk = rows[i:i + CHUNK]
        done = cache / f"{i:03d}.json"
        if done.exists():
            return json.loads(done.read_text())
        for attempt in range(5):
            try:
                got = request(chunk, codebook, a.model, key)
                done.write_text(json.dumps(got))
                print(f"rows {i}-{i + len(chunk) - 1}: mapped", flush=True)
                return got
            except (ValueError, KeyError, TypeError, json.JSONDecodeError, OSError, SystemExit) as e:
                print(f"rows {i}-{i + len(chunk) - 1}: attempt {attempt + 1} failed: {type(e).__name__}: {e}", flush=True)
        raise RuntimeError(f"rows {i}-{i + len(chunk) - 1}: no valid reply")

    with ThreadPoolExecutor(max_workers=8) as pool:
        mapped = [o for got in pool.map(run, range(0, len(rows), CHUNK)) for o in got]
    tmp = a.out.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(m) + "\n" for m in mapped), encoding="utf-8")
    load(tmp, [r["family_id"] for r in rows])
    tmp.replace(a.out)
    print(f"wrote {len(mapped)} rows to {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
