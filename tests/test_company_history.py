import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "build_company_history.py"
SPEC = importlib.util.spec_from_file_location("build_company_history", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def record(source="publisher.example", url="https://publisher.example/powergrid", title="POWERGRID approves a project",
           snippet="Power Grid Corporation update", published="2024-01-01T10:00:00+05:30",
           observed="2026-10-24T10:00:00Z"):
    return {"record_id": url, "source_id": source, "source_group": source, "source_url": url,
            "title": title, "published_at": published, "publication_precision": "timestamp",
            "observed_at_utc": observed, "retrieved_at_utc": observed, "content_type": "search_snippet",
            "snippet": snippet, "full_text": None,
            "content_sha256": hashlib.sha256((title + "\n" + snippet).encode()).hexdigest(),
            "content_hash_basis": "search-result title and snippet", "company": {"attribution": "query result only"},
            "original_upstream_url": None, "query_id": "q1",
            "query_period": {"start": "2024-01-01", "end": "2024-03-31"}}


def catalog(records):
    return {"schema_version": "powergrid-news-catalog-v1",
            "requested_window": {"start": "2023-10-25", "end": "2026-10-25", "timezone": "Asia/Kolkata"},
            "retrieved_at_utc": "2026-10-24T10:00:00Z", "query_count": 1, "search_credits_used": 1,
            "credit_cap": 60, "exhaustive": False, "query_periods": [{"start": "2024-01-01", "end": "2024-03-31", "complete": True}],
            "search_outputs": [], "gaps": [], "records": records}


def verified_record():
    row = record()
    row.update({"company_id": "POWERGRID", "attribution": "publisher article explicitly names POWERGRID",
                "publication_basis": "publisher_page", "publication_evidence": "Published: 1 January 2024",
                "content_hash_basis": "SHA-256 of retrieved publisher page text", "content_type": "publisher_page",
                "retrieved_at_utc": None, "body_excerpt": "Power Grid Corporation update"})
    row["content_sha256"] = "a" * 64
    return row


def verified_catalog(records):
    result = catalog(records)
    result["schema_version"] = "powergrid-verified-news-catalog-v1"
    result["records"] = records
    return result


def test_offline_archive_keeps_observation_time_and_never_labels_truth(tmp_path):
    first = record()
    copy = record(source="other.example", url="https://other.example/copy")
    duplicate = record()
    outside = record(url="https://publisher.example/outside", published="2022-01-01T00:00:00Z")
    bad_hash = record(url="https://publisher.example/bad")
    bad_hash["content_sha256"] = "0" * 64
    data = catalog([first, copy, duplicate, outside, bad_hash])
    output = MODULE.build(data, catalog_sha256="a" * 64,
                          built_at=datetime(2026, 10, 25, tzinfo=timezone.utc))
    assert output["events"] == []
    assert output["collection"]["candidate_sources"] == ["other.example", "publisher.example"]
    assert len(output["collection"]["inventory"]) == 5
    assert output["collection"]["inventory"][0]["decision"] == "search_metadata_only_not_admitted_as_publisher_event"
    assert output["collection"]["out_of_range_records"] == 0
    assert output["collection"]["rejected_records"] == 1
    assert output["price_outcomes"] == [] and output["train_ready"] is False
    assert output["dataset_status"] == "partial"
    assert all(month["coverage"] != "complete" for month in output["coverage"]["months"])


def test_cli_imports_only_events_and_writes_zero_adjudication_source_scores(tmp_path, capsys):
    source = tmp_path / "catalog.json"
    capture = tmp_path / "capture.txt"
    row = verified_record()
    capture.write_text(f"{row['source_url']}\n{row['title']}\n{row['publication_evidence']}", encoding="utf-8")
    row["capture_file"] = capture.name
    row["capture_sha256"] = hashlib.sha256(capture.read_bytes()).hexdigest()
    data = verified_catalog([row])
    data["capture_files"] = [{"path": capture.name, "sha256": row["capture_sha256"]}]
    source.write_text(json.dumps(data), encoding="utf-8")
    destination = tmp_path / "history"
    assert MODULE.main([str(source), "--output-dir", str(destination)]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["train_ready"] is False and status["events"] == 1
    archive = json.loads((destination / "archive.json").read_text(encoding="utf-8"))
    assert archive["source_reliability"][0]["resolved_n"] == 0
    assert archive["source_reliability"][0]["cold_start"] is True
    assert archive["price_outcomes"] == []
    article_csv = (destination / "articles.csv").read_text(encoding="utf-8")
    assert "source_url,published_at,publication_date" in article_csv.splitlines()[0]
    assert "retrospective_event_study_only_retrieved_after_publication" in article_csv
    assert MODULE.main([str(source), "--output-dir", str(destination)]) == 2


def test_verified_capture_must_contain_url_title_and_date_evidence(tmp_path):
    capture = tmp_path / "capture.txt"
    row = verified_record()
    capture.write_text(f"{row['source_url']}\n{row['title']}\nnot the displayed date", encoding="utf-8")
    row["capture_file"] = capture.name
    row["capture_sha256"] = hashlib.sha256(capture.read_bytes()).hexdigest()
    data = verified_catalog([row])
    data["capture_files"] = [{"path": capture.name, "sha256": row["capture_sha256"]}]
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="URL, title, and displayed date evidence"):
        MODULE.verify_capture_files(data, catalog_path)


def test_verified_publication_and_retrieval_have_distinct_times():
    data = verified_catalog([verified_record()])
    output = MODULE.build(data, catalog_sha256="b" * 64,
                          built_at=datetime(2026, 10, 25, tzinfo=timezone.utc))
    event = output["events"][0]
    assert event["historical_window_eligible"] is True
    assert event["available_at"] == "2026-10-24T10:00:00.000000Z"
    assert event["published_at"] == "2024-01-01T04:30:00.000000Z"
    assert event["verification_status"] == "publisher_reported_unverified"


def test_later_publication_evidence_is_not_available_at_first_observation_or_in_the_future():
    row = verified_record()
    row["publication_evidence_known_at_utc"] = "2026-10-25T09:00:00Z"
    data = verified_catalog([row])
    output = MODULE.build(data, catalog_sha256="c" * 64,
                          built_at=datetime(2026, 10, 25, 10, tzinfo=timezone.utc))
    event = output["events"][0]
    assert event["observed_at"] == "2026-10-24T10:00:00.000000Z"
    assert event["available_at"] == "2026-10-25T09:00:00.000000Z"

    row["publication_evidence_known_at_utc"] = "2026-10-25T11:00:00Z"
    output = MODULE.build(verified_catalog([row]), catalog_sha256="d" * 64,
                          built_at=datetime(2026, 10, 25, 10, tzinfo=timezone.utc))
    assert output["events"] == []
    assert output["collection"]["rejected_records"] == 1


@pytest.mark.parametrize("changes", [
    {"schema_version": "wrong"},
    {"requested_window": {"start": "2024-01-01", "end": "2026-10-25", "timezone": "Asia/Kolkata"}},
])
def test_rejects_wrong_catalog_or_window(changes):
    data = catalog([])
    data.update(changes)
    with pytest.raises(ValueError):
        MODULE.build(data, catalog_sha256="a" * 64,
                     built_at=datetime(2026, 10, 25, tzinfo=timezone.utc))
