"""Build the blind second-screening input (EXP-2026-004 Q2) for the original exclusions.

Units: catalog records decided B (background) or X (outside scope) at title/abstract, plus eligibility records moved
to background at full text. Coders see title, year, venue and abstract only; the original decision and reason stay in
a separate key file.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("e0_recall_openalex", HERE / "e0_recall_openalex.py")
recall = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(recall)
_spec2 = importlib.util.spec_from_file_location("e0_screen_prepare", HERE / "e0_screen_prepare.py")
prep = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(prep)


def openalex_abstract(doi: str | None, title: str) -> str:
    if doi:
        params = {"filter": f"doi:{recall.normalize_doi(doi)}", "select": "id,abstract_inverted_index"}
    else:
        clean = " ".join(recall.normalize_title(title).split()[:20])
        params = {"filter": f"title.search:{clean}", "select": "id,title,abstract_inverted_index", "per-page": "5"}
    payload = recall._open_json("https://api.openalex.org/works?" + urllib.parse.urlencode(params))
    for work in payload.get("results", []):
        if doi or recall.normalize_title(work.get("title") or "") == recall.normalize_title(title):
            return prep.rebuild_abstract(work.get("abstract_inverted_index"))
    return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--e0-dir", type=Path, required=True, help="prepared-work/docs/sok/e0-current")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    catalog = json.loads((args.e0_dir / "catalog.json").read_text(encoding="utf-8"))["records"]
    elig = json.loads((args.e0_dir / "eligibility.json").read_text(encoding="utf-8"))["records"]
    by_id = {r["id"]: r for r in catalog}
    units = [(r, "TA-" + r["decision"]) for r in catalog if r["decision"] in ("B", "X")]
    units += [(by_id.get(e["id"], e), "FT-background") for e in elig if e["status"] == "scope_background"]

    args.out_dir.mkdir(parents=True, exist_ok=True)
    inputs, keys, failed = [], [], []
    for n, (rec, original) in enumerate(units, start=1):
        sid = f"Q{n:03d}"
        abstract = rec.get("abstract") or ""
        if not abstract:
            try:
                abstract = openalex_abstract(rec.get("doi"), rec.get("title", ""))
            except Exception as error:  # noqa: BLE001 - collected and reported, output withheld
                failed.append(f"{rec['id']}: {type(error).__name__}: {error}")
        published = rec.get("published")
        year = (published if isinstance(published, str) else "")[:4] or str((rec.get("bibtex") or {}).get("year", ""))
        venue = (rec.get("bibtex") or {}).get("journal") or (rec.get("bibtex") or {}).get("booktitle") or ""
        inputs.append({"screen_id": sid, "title": rec.get("title", ""), "year": year, "type": "", "venue": venue, "abstract": abstract})
        keys.append({"screen_id": sid, "catalog_id": rec["id"], "original": original, "reason": rec.get("reason", "")})
    if failed:
        raise SystemExit("abstract lookup failed; no output written:\n" + "\n".join(failed))
    with (args.out_dir / "q2_input.jsonl").open("w", encoding="utf-8") as fh:
        for r in inputs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    with (args.out_dir / "q2_key.jsonl").open("w", encoding="utf-8") as fh:
        for r in keys:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"units {len(inputs)}; with abstract {sum(1 for r in inputs if r['abstract'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
