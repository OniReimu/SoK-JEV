"""Offline tests for the OpenAlex recall-check script."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "e0_recall_openalex.py"
SPEC = importlib.util.spec_from_file_location("e0_recall_openalex", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
recall = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recall)


def test_title_normalization_latex_accents_and_punctuation() -> None:
    assert recall.normalize_title(r"{Crème} Br{\^u}lée: An {LLM}-Based System!") == (
        "creme brulee an llm based system"
    )
    assert recall.normalize_title(r"\textit{Intent--Driven} Networks") == "intent driven networks"


def test_doi_and_arxiv_normalization() -> None:
    assert recall.normalize_doi("https://doi.org/10.1109/TNSM.2025.3570017") == (
        "10.1109/tnsm.2025.3570017"
    )
    assert recall.normalize_doi("doi:10.48550/arXiv.2606.06212.") == "10.48550/arxiv.2606.06212"
    assert recall.normalize_arxiv_id("https://arxiv.org/abs/2606.06212v3") == "2606.06212"
    assert recall.normalize_arxiv_id("arXiv:hep-th/9901001v2") == "hep-th/9901001"


def test_deduplication_and_existing_match_fixture() -> None:
    works = [
        (
            "configuration",
            {
                "id": "https://openalex.org/W1",
                "doi": "https://doi.org/10.1000/ONE",
                "title": "An Intent-Driven Network",
                "locations": [],
            },
        ),
        (
            "diagnosis",
            {
                "id": "https://openalex.org/W1",
                "doi": "https://doi.org/10.1000/one",
                "title": "An Intent Driven Network",
                "locations": [],
            },
        ),
        (
            "orchestration",
            {
                "id": "https://openalex.org/W2",
                "title": "A New Orchestrator",
                "locations": [{"landing_page_url": "https://arxiv.org/abs/2401.01234v2"}],
            },
        ),
    ]
    rows = recall.deduplicate_works(works)
    assert len(rows) == 2
    assert rows[0]["matched_queries"] == "configuration;diagnosis"
    assert rows[1]["normalized_arxiv_id"] == "2401.01234"

    index = recall.build_existing_index(
        [("fixture", [{"id": "old-1", "doi": "10.1000/one", "title": "Different"}])]
    )
    counts = recall.annotate_matches(rows, index)
    assert counts["matched_existing"] == 1
    assert rows[0]["matched_by"] == "doi"
    assert rows[0]["matched_records"] == "fixture:old-1"
    assert rows[1]["matched_existing"] == "no"


def test_deduplication_collapses_bridged_rows_and_keeps_all_identifiers() -> None:
    works = [
        ("configuration", {"id": "W1", "doi": "10.1000/a", "title": "T1"}),
        ("orchestration", {"id": "W2", "doi": "10.1000/b", "title": "T2"}),
        ("diagnosis", {"id": "W3", "doi": "10.1000/a", "title": "T2"}),
    ]

    rows = recall.deduplicate_works(works)

    assert len(rows) == 1
    assert set(rows[0]["normalized_doi"].split(";")) == {"10.1000/a", "10.1000/b"}
    assert set(rows[0]["openalex_id"].split(";")) == {"W1", "W2", "W3"}
    assert rows[0]["matched_queries"] == "configuration;orchestration;diagnosis"


def test_merged_arxiv_identifier_is_used_for_existing_match() -> None:
    works = [
        ("configuration", {"id": "W1", "doi": "10.1000/shared", "title": "First"}),
        (
            "diagnosis",
            {
                "id": "W2",
                "doi": "10.1000/shared",
                "title": "Second",
                "locations": [{"landing_page_url": "https://arxiv.org/abs/2401.01234"}],
            },
        ),
    ]
    rows = recall.deduplicate_works(works)
    index = recall.build_existing_index(
        [("fixture", [{"id": "old-arxiv", "arxiv": "arXiv:2401.01234"}])]
    )

    counts = recall.annotate_matches(rows, index)

    assert len(rows) == 1
    assert rows[0]["normalized_arxiv_id"] == "2401.01234"
    assert rows[0]["matched_existing"] == "yes"
    assert rows[0]["matched_by"] == "arxiv"
    assert counts["matched_existing"] == 1


def test_incomplete_pagination_writes_only_incomplete_manifest(tmp_path, monkeypatch) -> None:
    eligibility = tmp_path / "eligibility.json"
    eligibility.write_text('{"records": []}\n', encoding="utf-8")
    output_dir = tmp_path / "run"
    call_count = 0

    def incomplete_fetch(query: str, destination: Path, sleep_seconds: float) -> tuple[int, int, int, int]:
        nonlocal call_count
        del query, sleep_seconds
        destination.write_text("", encoding="utf-8")
        call_count += 1
        # Two rows returned but only one unique work against a reported count of two.
        return (1, 2, 2, 1) if call_count == 1 else (1, 0, 0, 0)

    monkeypatch.setattr(recall, "CODING_SOURCES", eligibility)
    monkeypatch.setattr(recall, "REFERENCES_BIB", eligibility)
    monkeypatch.setattr(recall, "fetch_query", incomplete_fetch)

    exit_code = recall.main(
        ["--eligibility", str(eligibility), "--output-dir", str(output_dir), "--sleep-seconds", "0"]
    )

    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert exit_code != 0
    assert manifest["status"] == "incomplete"
    assert manifest["queries"]["configuration"]["expected_count"] == 2
    assert manifest["queries"]["configuration"]["retrieved_count"] == 2
    assert manifest["queries"]["configuration"]["unique_count"] == 1
    assert not (output_dir / "hits.csv").exists()
    assert not (output_dir / "new_hits.csv").exists()
    assert not (output_dir / "dedup_summary.json").exists()


def test_request_urls_never_contain_contact_information() -> None:
    for query in recall.QUERIES.values():
        url = recall.build_url(query)
        assert "mailto" not in url.lower()
        assert "@" not in url
        assert "cursor=%2A" in url or "cursor=*" in url


def test_repeated_rows_across_pages_count_once(tmp_path, monkeypatch) -> None:
    pages = [
        {"meta": {"count": 2, "next_cursor": "c2"}, "results": [{"id": "W1"}, {"id": "W2"}]},
        {"meta": {"count": 2, "next_cursor": None}, "results": [{"id": "W2"}]},
    ]
    monkeypatch.setattr(recall, "_open_json", lambda url: pages.pop(0))
    result = recall.fetch_query("q", tmp_path / "q.jsonl", 0)
    assert result == (2, 2, 3, 2)
    assert len((tmp_path / "q.jsonl").read_text(encoding="utf-8").splitlines()) == 3
