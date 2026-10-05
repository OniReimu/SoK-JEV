#!/usr/bin/env python3
"""Run the EXP-2026-004 OpenAlex recall queries and deduplicate the hits."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable, Mapping
from typing import Any


CONFIGURATION_QUERY = '("network configuration" OR "router configuration" OR "intent based networking" OR "network intent") AND ("language model" OR "language models" OR LLM OR LLMs OR "natural language" OR "intent based" OR "intent driven")'
ORCHESTRATION_QUERY = '("network orchestration" OR "service orchestration" OR "network function deployment" OR "intent driven resource allocation") AND ("language model" OR "language models" OR LLM OR LLMs OR "natural language" OR "intent based" OR "intent driven")'
DIAGNOSIS_QUERY = '("network troubleshooting" OR "network diagnosis" OR "network fault diagnosis" OR "network fault localization") AND ("language model" OR "language models" OR LLM OR LLMs OR "natural language" OR "intent based" OR "intent driven")'

QUERIES = {
    "configuration": CONFIGURATION_QUERY,
    "orchestration": ORCHESTRATION_QUERY,
    "diagnosis": DIAGNOSIS_QUERY,
}
DATE_FILTER = "from_publication_date:2016-01-01,to_publication_date:2026-09-28"
OPENALEX_URL = "https://api.openalex.org/works"
USER_AGENT = "jev-sok-recall/1.0"
PER_PAGE = 200
SELECT_FIELDS = (
    "id",
    "doi",
    "title",
    "publication_year",
    "publication_date",
    "type",
    "primary_location",
    "ids",
    "locations",
    "authorships",
)
CSV_FIELDS = (
    "openalex_id",
    "doi",
    "arxiv_id",
    "title",
    "publication_year",
    "publication_date",
    "type",
    "source_display_name",
    "landing_page_url",
    "first_author",
    "matched_queries",
    "normalized_doi",
    "normalized_arxiv_id",
    "normalized_title",
    "matched_existing",
    "matched_by",
    "matched_records",
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CODING_SOURCES = PROJECT_ROOT / "supplement" / "coding-sources.csv"
REFERENCES_BIB = PROJECT_ROOT / "paper" / "references.bib"

_ARXIV_ID = r"(?:[a-z][a-z0-9.-]*/\d{7}|\d{4}\.\d{4,5})"


def normalize_title(value: object) -> str:
    """Normalize a title for conservative exact-title matching."""
    if value is None:
        return ""
    text = str(value)
    # Preserve the base letter in common TeX accent forms such as {\"o}.
    text = re.sub(r"\\[\"'`^~=.]\s*\{?\s*([A-Za-z])\s*\}?", r"\1", text)
    text = re.sub(r"\\[uvHckbdtr]\s*\{\s*([A-Za-z])\s*\}", r"\1", text)
    text = re.sub(r"\\[A-Za-z]+\*?", " ", text)
    text = re.sub(r"\\([#$%&_{}])", r"\1", text)
    text = text.replace("{", "").replace("}", "")
    text = unicodedata.normalize("NFKD", text).lower()
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def normalize_doi(value: object) -> str:
    """Return a lowercase bare DOI, or an empty string if none is present."""
    if value is None:
        return ""
    text = urllib.parse.unquote(str(value)).strip().strip("{}\"'")
    text = re.sub(r"^\s*(?:doi\s*:\s*|https?://(?:dx\.)?doi\.org/)", "", text, flags=re.I)
    match = re.search(r"10\.\d{4,9}/[^\s\"'<>]+", text, flags=re.I)
    if not match:
        return ""
    return match.group(0).rstrip(".,;:)]}").lower()


def normalize_arxiv_id(value: object) -> str:
    """Return a bare, lowercase arXiv identifier without a version suffix."""
    if value is None:
        return ""
    text = urllib.parse.unquote(str(value)).strip()
    patterns = (
        rf"arxiv\.org/(?:abs|pdf)/({_ARXIV_ID})(?:v\d+)?(?:\.pdf)?",
        rf"10\.48550/arxiv\.({_ARXIV_ID})(?:v\d+)?",
        rf"arxiv\s*[:/]\s*({_ARXIV_ID})(?:v\d+)?",
        rf"(?<![A-Za-z0-9./])({_ARXIV_ID})(?:v\d+)?(?![A-Za-z0-9.])",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            return match.group(1).lower()
    return ""


def build_url(query: str, cursor: str = "*") -> str:
    """Build one OpenAlex request URL without contact-identifying parameters."""
    params = {
        "filter": f"title_and_abstract.search:{query},{DATE_FILTER}",
        "select": ",".join(SELECT_FIELDS),
        "per-page": str(PER_PAGE),
        "cursor": cursor,
    }
    url = f"{OPENALEX_URL}?{urllib.parse.urlencode(params)}"
    if "mailto" in url.lower() or "@" in url:
        raise ValueError("OpenAlex request URL unexpectedly contains contact information")
    return url


def _open_json(url: str, retries: int = 3) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.load(response)
            if not isinstance(payload, dict):
                raise ValueError("OpenAlex response is not a JSON object")
            return payload
        except urllib.error.HTTPError as error:
            retryable = error.code == 429 or 500 <= error.code < 600
            if not retryable or attempt == retries:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("unreachable")


def fetch_query(query: str, destination: Path, sleep_seconds: float) -> tuple[int, int, int, int]:
    """Fetch all cursor pages for one query and write the returned works.

    Returns pages, the reported count, rows written and unique work ids. Cursor paging can
    repeat a work across adjacent pages, so completeness compares unique ids to the count.
    """
    cursor = "*"
    pages = 0
    written = 0
    seen_ids: set[str] = set()
    total_hits: int | None = None
    with destination.open("w", encoding="utf-8") as output:
        while cursor:
            payload = _open_json(build_url(query, cursor))
            results = payload.get("results")
            if not isinstance(results, list):
                raise ValueError("OpenAlex response has no results list")
            meta = payload.get("meta")
            if not isinstance(meta, dict):
                raise ValueError("OpenAlex response has no meta object")
            if total_hits is None:
                count = meta.get("count")
                total_hits = count if isinstance(count, int) else 0
            for work in results:
                if not isinstance(work, dict):
                    raise ValueError("OpenAlex returned a non-object work")
                output.write(json.dumps(work, ensure_ascii=False, separators=(",", ":")) + "\n")
                written += 1
                if isinstance(work.get("id"), str):
                    seen_ids.add(work["id"])
            pages += 1
            next_cursor = meta.get("next_cursor")
            cursor = next_cursor if isinstance(next_cursor, str) and next_cursor else ""
            if cursor:
                time.sleep(sleep_seconds)
    expected = total_hits or 0
    unique = len(seen_ids)
    if unique != expected:
        print(
            f"error: OpenAlex reported {expected} hits but returned {unique} unique works ({written} rows)",
            file=sys.stderr,
        )
    return pages, expected, written, unique


def _iter_string_values(value: object) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for nested in value.values():
            yield from _iter_string_values(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _iter_string_values(nested)


def record_keys(record: Mapping[str, Any]) -> dict[str, str]:
    """Extract the three cross-source match keys from a record-like object."""
    title = ""
    for name in ("title", "catalog_title", "display_name"):
        candidate = record.get(name)
        if isinstance(candidate, str) and candidate.strip():
            title = normalize_title(candidate)
            break

    doi = ""
    arxiv_id = ""
    for key, value in record.items():
        key_lower = str(key).lower()
        strings = list(_iter_string_values(value))
        if not doi and ("doi" in key_lower or "url" in key_lower or key_lower == "ids"):
            doi = next((item for item in (normalize_doi(v) for v in strings) if item), "")
        if not arxiv_id and (
            "arxiv" in key_lower
            or "url" in key_lower
            or key_lower in {"id", "record_id", "ids", "locations"}
        ):
            arxiv_id = next((item for item in (normalize_arxiv_id(v) for v in strings) if item), "")
    return {"doi": doi, "arxiv": arxiv_id, "title": title}


def _work_row(work: Mapping[str, Any]) -> dict[str, str]:
    keys = record_keys(work)
    primary = work.get("primary_location")
    primary = primary if isinstance(primary, Mapping) else {}
    source = primary.get("source")
    source = source if isinstance(source, Mapping) else {}
    authorships = work.get("authorships")
    first_author = ""
    if isinstance(authorships, list) and authorships and isinstance(authorships[0], Mapping):
        author = authorships[0].get("author")
        if isinstance(author, Mapping) and isinstance(author.get("display_name"), str):
            first_author = author["display_name"]
    return {
        "openalex_id": str(work.get("id") or ""),
        "doi": str(work.get("doi") or keys["doi"]),
        "arxiv_id": keys["arxiv"],
        "title": str(work.get("title") or ""),
        "publication_year": str(work.get("publication_year") or ""),
        "publication_date": str(work.get("publication_date") or ""),
        "type": str(work.get("type") or ""),
        "source_display_name": str(source.get("display_name") or ""),
        "landing_page_url": str(primary.get("landing_page_url") or ""),
        "first_author": first_author,
        "matched_queries": "",
        "normalized_doi": keys["doi"],
        "normalized_arxiv_id": keys["arxiv"],
        "normalized_title": keys["title"],
        "matched_existing": "",
        "matched_by": "",
        "matched_records": "",
    }


def deduplicate_works(records: Iterable[tuple[str, Mapping[str, Any]]]) -> list[dict[str, str]]:
    """Deduplicate transitively linked OpenAlex works and merge their identifiers."""
    items = [(query_name, _work_row(work)) for query_name, work in records]
    parents = list(range(len(items)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parents[max(left_root, right_root)] = min(left_root, right_root)

    key_owner: dict[tuple[str, str], int] = {}
    for index, (_, row) in enumerate(items):
        keys = (
            ("openalex", row["openalex_id"].lower()),
            ("doi", row["normalized_doi"]),
            ("arxiv", row["normalized_arxiv_id"]),
            ("title", row["normalized_title"]),
        )
        for key in (key for key in keys if key[1]):
            owner = key_owner.setdefault(key, index)
            union(index, owner)

    groups: dict[int, list[tuple[str, dict[str, str]]]] = {}
    for index, item in enumerate(items):
        groups.setdefault(find(index), []).append(item)

    def unique_values(group_rows: Iterable[dict[str, str]], field: str) -> list[str]:
        values: list[str] = []
        seen: set[str] = set()
        for row in group_rows:
            value = row[field]
            identity = value.lower()
            if value and identity not in seen:
                seen.add(identity)
                values.append(value)
        return values

    merged_rows: list[dict[str, str]] = []
    for group in groups.values():
        group_rows = [row for _, row in group]
        merged = group_rows[0].copy()
        for field in CSV_FIELDS:
            if not merged[field]:
                merged[field] = next((row[field] for row in group_rows if row[field]), "")
        for field in (
            "openalex_id",
            "doi",
            "arxiv_id",
            "normalized_doi",
            "normalized_arxiv_id",
            "normalized_title",
        ):
            merged[field] = ";".join(unique_values(group_rows, field))
        query_names = {query_name for query_name, _ in group}
        ordered_queries = [name for name in QUERIES if name in query_names]
        ordered_queries.extend(sorted(query_names.difference(QUERIES)))
        merged["matched_queries"] = ";".join(ordered_queries)
        merged_rows.append(merged)
    return merged_rows


def _balanced_entries(text: str) -> Iterable[str]:
    position = 0
    while True:
        match = re.search(r"@[A-Za-z]+\s*([({])", text[position:])
        if not match:
            return
        start = position + match.end()
        opening = match.group(1)
        closing = "}" if opening == "{" else ")"
        depth = 1
        quoted = False
        escaped = False
        index = start
        while index < len(text) and depth:
            char = text[index]
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = not quoted
            elif not quoted and char == opening:
                depth += 1
            elif not quoted and char == closing:
                depth -= 1
            index += 1
        if depth:
            return
        yield text[start : index - 1]
        position = index


def _parse_bib_fields(entry: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    comma = entry.find(",")
    position = comma + 1 if comma >= 0 else 0
    while position < len(entry):
        match = re.search(r"([A-Za-z][A-Za-z0-9_-]*)\s*=\s*", entry[position:])
        if not match:
            break
        name = match.group(1).lower()
        start = position + match.end()
        if start >= len(entry):
            break
        opener = entry[start]
        if opener in "{\"":
            closer = "}" if opener == "{" else '"'
            depth = 1 if opener == "{" else 0
            index = start + 1
            escaped = False
            while index < len(entry):
                char = entry[index]
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif opener == "{" and char == "{":
                    depth += 1
                elif char == closer:
                    if opener == "{":
                        depth -= 1
                        if depth == 0:
                            break
                    else:
                        break
                index += 1
            value = entry[start + 1 : index]
            position = index + 1
        else:
            index = entry.find(",", start)
            if index < 0:
                index = len(entry)
            value = entry[start:index].strip()
            position = index + 1
        fields[name] = value.strip()
    return fields


def _load_bibliography(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for number, entry in enumerate(_balanced_entries(path.read_text(encoding="utf-8")), start=1):
        fields = _parse_bib_fields(entry)
        records.append(
            {
                "record_id": f"bib:{number}",
                "title": fields.get("title", ""),
                "doi": fields.get("doi", ""),
                "arxiv": fields.get("eprint", "") if fields.get("archiveprefix", "").lower() == "arxiv" else fields.get("arxiv", ""),
                "url": fields.get("url", ""),
            }
        )
    return records


def _load_json_records(path: Path, preferred_key: str = "records") -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    candidates: object = payload
    if isinstance(payload, dict):
        if isinstance(payload.get(preferred_key), list):
            candidates = payload[preferred_key]
        else:
            candidates = next(
                (value for value in payload.values() if isinstance(value, list)),
                [],
            )
    if not isinstance(candidates, list):
        raise ValueError(f"{path} must contain a record list")
    return [item for item in candidates if isinstance(item, dict)]


def _load_coding_sources(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def build_existing_index(
    sources: Iterable[tuple[str, Iterable[Mapping[str, Any]]]],
) -> dict[tuple[str, str], set[str]]:
    """Build a lookup from normalized keys to auditable source identifiers."""
    index: dict[tuple[str, str], set[str]] = {}
    for source_name, records in sources:
        for number, record in enumerate(records, start=1):
            label = str(
                record.get("record_id")
                or record.get("bibliography_key")
                or record.get("id")
                or number
            )
            for kind, value in record_keys(record).items():
                if value:
                    index.setdefault((kind, value), set()).add(f"{source_name}:{label}")
    return index


def annotate_matches(
    rows: list[dict[str, str]], index: Mapping[tuple[str, str], set[str]]
) -> dict[str, int]:
    counts = {"doi": 0, "arxiv": 0, "title": 0, "matched_existing": 0}
    for row in rows:
        values = {
            "doi": row["normalized_doi"].split(";"),
            "arxiv": row["normalized_arxiv_id"].split(";"),
            "title": row["normalized_title"].split(";"),
        }
        matched_by: list[str] = []
        matched_records: set[str] = set()
        for kind, candidates in values.items():
            matches: set[str] = set()
            for value in filter(None, candidates):
                matches.update(index.get((kind, value), set()))
            if matches:
                matched_by.append(kind)
                matched_records.update(matches)
                counts[kind] += 1
        row["matched_existing"] = "yes" if matched_by else "no"
        row["matched_by"] = ";".join(matched_by)
        row["matched_records"] = ";".join(sorted(matched_records))
        if matched_by:
            counts["matched_existing"] += 1
    return counts


def _read_jsonl_records(paths: Mapping[str, Path]) -> Iterable[tuple[str, Mapping[str, Any]]]:
    for query_name, path in paths.items():
        with path.open(encoding="utf-8") as source:
            for line_number, line in enumerate(source, start=1):
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(f"invalid JSON in {path}:{line_number}") from error
                if not isinstance(record, dict):
                    raise ValueError(f"non-object JSON in {path}:{line_number}")
                yield query_name, record


def _write_csv(path: Path, rows: Iterable[Mapping[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--eligibility",
        type=Path,
        help="eligibility JSON containing records[].id and records[].title (required unless --dry-run)",
    )
    parser.add_argument("--catalog", type=Path, help="optional full catalogue JSON")
    parser.add_argument("--output-dir", type=Path, help="output directory")
    parser.add_argument("--sleep-seconds", type=float, default=1.0, help="pause between pages (default: 1.0)")
    parser.add_argument("--dry-run", action="store_true", help="print page-one URLs and exit")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.dry_run:
        for name, query in QUERIES.items():
            print(f"{name}\t{build_url(query)}")
        return 0
    if args.eligibility is None:
        raise SystemExit("--eligibility is required unless --dry-run is used")
    if args.sleep_seconds < 0:
        raise SystemExit("--sleep-seconds must be non-negative")
    for required in (CODING_SOURCES, REFERENCES_BIB, args.eligibility):
        if not required.is_file():
            raise SystemExit(f"required input not found: {required}")
    if args.catalog is not None and not args.catalog.is_file():
        raise SystemExit(f"catalog not found: {args.catalog}")

    started = _utc_now()
    output_dir = args.output_dir
    if output_dir is None:
        stamp = started.strftime("%Y%m%dT%H%M%SZ")
        output_dir = PROJECT_ROOT / "experiments" / "EXP-2026-004" / "runs" / "recall" / stamp
    output_dir.mkdir(parents=True, exist_ok=False)

    raw_paths: dict[str, Path] = {}
    query_stats: dict[str, dict[str, int]] = {}
    for name, query in QUERIES.items():
        path = output_dir / f"{name}.jsonl"
        pages, expected_count, retrieved_count, unique_count = fetch_query(
            query, path, args.sleep_seconds
        )
        raw_paths[name] = path
        query_stats[name] = {
            "page_count": pages,
            "expected_count": expected_count,
            "retrieved_count": retrieved_count,
            "unique_count": unique_count,
            "repeated_rows": retrieved_count - unique_count,
        }

    status = (
        "complete"
        if all(stats["expected_count"] == stats["unique_count"] for stats in query_stats.values())
        else "incomplete"
    )
    completed = _utc_now()
    manifest = {
        "experiment": "EXP-2026-004",
        "status": status,
        "retrieval_started_utc": started.isoformat().replace("+00:00", "Z"),
        "retrieval_completed_utc": completed.isoformat().replace("+00:00", "Z"),
        "user_agent": USER_AGENT,
        "queries": {
            name: {
                "query": query,
                "filter": f"title_and_abstract.search:{query},{DATE_FILTER}",
                **query_stats[name],
                "jsonl": raw_paths[name].name,
                "sha256": _sha256(raw_paths[name]),
            }
            for name, query in QUERIES.items()
        },
        "select_fields": list(SELECT_FIELDS),
        "per_page": PER_PAGE,
    }
    if status == "incomplete":
        (output_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(output_dir, file=sys.stderr)
        return 1

    rows = deduplicate_works(_read_jsonl_records(raw_paths))
    sources: list[tuple[str, Iterable[Mapping[str, Any]]]] = [
        ("coding-sources", _load_coding_sources(CODING_SOURCES)),
        ("eligibility", _load_json_records(args.eligibility)),
        ("references", _load_bibliography(REFERENCES_BIB)),
    ]
    source_counts = {name: len(records) for name, records in sources if isinstance(records, list)}
    if args.catalog is not None:
        catalog_records = _load_json_records(args.catalog)
        sources.append(("catalog", catalog_records))
        source_counts["catalog"] = len(catalog_records)
    existing_index = build_existing_index(sources)
    match_counts = annotate_matches(rows, existing_index)
    new_rows = [row for row in rows if row["matched_existing"] == "no"]
    _write_csv(output_dir / "hits.csv", rows)
    _write_csv(output_dir / "new_hits.csv", new_rows)

    total_raw = sum(stats["retrieved_count"] for stats in query_stats.values())
    summary = {
        "raw_hits_across_queries": total_raw,
        "unique_hits_across_queries": len(rows),
        "duplicates_removed_across_queries": total_raw - len(rows),
        "existing_input_records": source_counts,
        "existing_index_keys": len(existing_index),
        "matched_existing": match_counts["matched_existing"],
        "matched_by_doi": match_counts["doi"],
        "matched_by_arxiv": match_counts["arxiv"],
        "matched_by_title": match_counts["title"],
        "new_hits": len(new_rows),
    }
    (output_dir / "dedup_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
