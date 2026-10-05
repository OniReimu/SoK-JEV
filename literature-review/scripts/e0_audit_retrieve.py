"""Retrieve open full text for the coverage-audit sample, in the fixed order of the design.

Order: OpenAlex open-access locations, then an arXiv exact-title search. Every draw keeps its access outcome;
the original draws are retained. Records without open full text are listed for a library request. No contact address is sent.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("e0_recall_openalex", HERE / "e0_recall_openalex.py")
recall = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(recall)

ATOM = "{http://www.w3.org/2005/Atom}"


def download_pdf(url: str, dest: Path) -> str:
    """Return ok, not_pdf (location reachable but no PDF) or error (network/HTTP failure)."""
    req = urllib.request.Request(url, headers={"User-Agent": recall.USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
    except urllib.error.HTTPError as error:
        return "not_pdf" if error.code in (401, 403, 404, 410) else "error"
    except Exception:  # noqa: BLE001 - timeouts and connection failures are retrieval errors
        return "error"
    if not data.startswith(b"%PDF"):
        return "not_pdf"
    dest.write_bytes(data)
    return "ok"


def openalex_pdf_urls(work_ids: list[str]) -> list[str]:
    urls: list[str] = []
    for wid in work_ids:
        params = {"select": "id,best_oa_location,locations"}
        work = recall._open_json(f"https://api.openalex.org/works/{wid.rsplit('/', 1)[-1]}?" + urllib.parse.urlencode(params))
        locs = [work.get("best_oa_location") or {}] + list(work.get("locations") or [])
        for loc in locs:
            if loc.get("is_oa") and loc.get("pdf_url") and loc["pdf_url"] not in urls:
                urls.append(loc["pdf_url"])
    return urls


def arxiv_by_title(title: str, year: str) -> str | None:
    """Accept only a unique exact normalized-title match published within one year of the record."""
    norm = recall.normalize_title(title)
    query = 'ti:"' + re.sub(r"[^\w\s-]", " ", title).strip() + '"'
    url = "http://export.arxiv.org/api/query?" + urllib.parse.urlencode({"search_query": query, "max_results": 5})
    req = urllib.request.Request(url, headers={"User-Agent": recall.USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        root = ET.fromstring(resp.read())
    matches = [e for e in root.findall(f"{ATOM}entry") if recall.normalize_title(e.findtext(f"{ATOM}title", "")) == norm]
    if len(matches) != 1:
        return None
    published = matches[0].findtext(f"{ATOM}published", "")[:4]
    if not (year and published and abs(int(published) - int(year)) <= 1):
        return None
    return matches[0].findtext(f"{ATOM}id", "").replace("/abs/", "/pdf/")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--screen-dir", type=Path, required=True)
    args = parser.parse_args()
    sample = [json.loads(l) for l in (args.screen_dir / "audit_sample.jsonl").read_text(encoding="utf-8").splitlines()]
    out = args.screen_dir / "fulltext"
    out.mkdir(exist_ok=True)
    log = []
    log_path = args.screen_dir / "retrieval_log.jsonl"
    for rec in sample:
        dest = out / f"{rec['screen_id']}.pdf"
        status, source, errors = "no_open_fulltext", "", []
        try:
            if dest.exists():
                status, source = "retrieved", "existing"
            else:
                candidates = openalex_pdf_urls(rec["openalex_id"].split(";"))
                if rec.get("arxiv_id"):
                    candidates.append(f"https://arxiv.org/pdf/{rec['arxiv_id']}")
                for url in candidates:
                    outcome = download_pdf(url, dest)
                    if outcome == "ok":
                        status, source = "retrieved", url
                        break
                    if outcome == "error":
                        errors.append(url)
                if status != "retrieved":
                    time.sleep(3)  # arXiv API etiquette
                    url = arxiv_by_title(rec["title"], rec["year"])
                    if url:
                        outcome = download_pdf(url, dest)
                        if outcome == "ok":
                            status, source = "retrieved", url
                        elif outcome == "error":
                            errors.append(url)
                if status != "retrieved" and errors:
                    status, source = "retrieval_error", ";".join(errors)
        except Exception as error:  # noqa: BLE001 - logged per record, run continues
            status, source = "retrieval_error", f"{type(error).__name__}: {error}"
        log.append({"screen_id": rec["screen_id"], "stratum": rec["stratum"], "status": status, "source": source,
                    "doi": rec["doi"], "title": rec["title"], "year": rec["year"], "type": rec["type"]})
        print(rec["screen_id"], status)
        log_path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in log), encoding="utf-8")
    missing = [r for r in log if r["status"] != "retrieved"]
    print(f"retrieved {len(log) - len(missing)} / {len(log)}; library requests {len(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
