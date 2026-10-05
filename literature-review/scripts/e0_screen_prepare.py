"""Build the title/abstract screening input for the OpenAlex recall hits.

Reads new_hits.csv from a complete recall run, fetches each work's abstract from OpenAlex
(no contact address is sent), and writes screening_input.jsonl plus coder batch files.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import time
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("e0_recall_openalex", HERE / "e0_recall_openalex.py")
recall = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(recall)

IDS_PER_CALL = 50


def rebuild_abstract(inverted: dict[str, list[int]] | None) -> str:
    if not inverted:
        return ""
    positions = [(pos, word) for word, poss in inverted.items() for pos in poss]
    return " ".join(word for _, word in sorted(positions))


def fetch_abstracts(work_ids: list[str], sleep_seconds: float) -> dict[str, str]:
    abstracts: dict[str, str] = {}
    short_ids = [w.rsplit("/", 1)[-1] for w in work_ids]
    for start in range(0, len(short_ids), IDS_PER_CALL):
        chunk = short_ids[start : start + IDS_PER_CALL]
        params = {
            "filter": "openalex:" + "|".join(chunk),
            "select": "id,abstract_inverted_index",
            "per-page": str(IDS_PER_CALL),
        }
        payload = recall._open_json("https://api.openalex.org/works?" + urllib.parse.urlencode(params))
        for work in payload.get("results", []):
            abstracts[work["id"]] = rebuild_abstract(work.get("abstract_inverted_index"))
        time.sleep(sleep_seconds)
    return abstracts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=110)
    parser.add_argument("--sleep-seconds", type=float, default=0.2)
    args = parser.parse_args()

    manifest = json.loads((args.run_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "complete":
        raise SystemExit("recall run is not complete")
    rows = list(csv.DictReader((args.run_dir / "new_hits.csv").open(encoding="utf-8")))
    all_ids = sorted({i for r in rows for i in r["openalex_id"].split(";")})
    abstracts = fetch_abstracts(all_ids, args.sleep_seconds)
    missing_fetch = [i for i in all_ids if i not in abstracts]
    if missing_fetch:
        raise SystemExit(f"OpenAlex returned no record for {len(missing_fetch)} ids")

    out_dir = args.run_dir / "screening"
    (out_dir / "batches").mkdir(parents=True, exist_ok=True)
    records = []
    for n, row in enumerate(rows, start=1):
        texts = [abstracts[i] for i in row["openalex_id"].split(";") if abstracts[i]]
        records.append(
            {
                "screen_id": f"S{n:04d}",
                "openalex_id": row["openalex_id"],
                "doi": row["normalized_doi"],
                "arxiv_id": row["normalized_arxiv_id"],
                "title": row["title"],
                "year": row["publication_year"],
                "type": row["type"],
                "venue": row["source_display_name"],
                "abstract": max(texts, key=len) if texts else "",
            }
        )
    with (out_dir / "screening_input.jsonl").open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    coder_view = [{k: r[k] for k in ("screen_id", "title", "year", "type", "venue", "abstract")} for r in records]
    for b, start in enumerate(range(0, len(coder_view), args.batch_size), start=1):
        path = out_dir / "batches" / f"batch-{b:02d}.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for rec in coder_view[start : start + args.batch_size]:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    with_abstract = sum(1 for r in records if r["abstract"])
    print(f"records {len(records)}; with abstract {with_abstract}; batches {b}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
