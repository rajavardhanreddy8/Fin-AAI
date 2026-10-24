import importlib.util
import json
import sqlite3
from pathlib import Path

from stock_research.context_store import ContextStore


COMMAND = Path(__file__).parents[1] / "scripts" / "run_source_response.py"
spec = importlib.util.spec_from_file_location("source_response_command", COMMAND)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


def graph(path):
    store = ContextStore(path)
    stamp = "2026-01-01T00:00:00Z"
    event = {"event_id": "evt", "canonical_id": "story", "source_id": "wire", "source_url": "https://news.test/a",
             "raw_hash": "a" * 64, "published_at": stamp, "observed_at": stamp, "available_at": stamp,
             "verification_status": "unverified", "title": "fixture", "entities": ["ACME"]}
    company = {"node_type": "company", "node_id": "acme", "canonical_id": "ACME", "known_at": stamp,
               "effective_from": stamp, "source": {"source_id": "wire", "source_url": event["source_url"],
               "raw_hash": event["raw_hash"], "known_at": stamp}}
    store.import_batch({"events": [event], "nodes": [company], "claims": [], "relationships": [], "analogs": []})
    return store


def test_existing_output_refused_before_input_or_database_mutation(tmp_path):
    db = tmp_path / "ctx.db"
    store = graph(db)
    output = tmp_path / "exists.json"
    output.write_text('{"preserved":true}', encoding="utf-8")
    assert cli.main(["adjudicate", str(tmp_path / "missing.json"), "--db", str(db), "--asof",
                     "2026-01-01T00:00:00Z", "--output", str(output)]) == 2
    assert json.loads(output.read_text(encoding="utf-8")) == {"preserved": True}
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ctx_source_adjudications'").fetchone() is None


def test_score_source_without_history_against_real_temporary_context_db(tmp_path):
    db = tmp_path / "ctx.db"
    graph(db)
    output = tmp_path / "score.json"
    assert cli.main(["score", "--source-id", "wire", "--company-id", "ACME", "--category",
                     "company_performance", "--asof", "2026-01-01T00:00:00Z", "--db", str(db),
                     "--output", str(output)]) == 0
    score = json.loads(output.read_text(encoding="utf-8"))
    assert score["cold_start"] is True
    assert score["resolved_n"] == 0
    assert score["calibrated"] is False


def test_reviewed_fresh_primary_event_can_be_paper_evaluated_without_source_history(tmp_path):
    db = tmp_path / "ctx.db"
    store = graph(db)
    review = {"review_id": "review-1", "event_id": "evt", "company_id": "ACME",
              "category": "company_performance", "known_at": "2026-01-01T00:00:00Z",
              "reviewer_id": "reviewer", "origin_status": "authenticated_primary",
              "authentication_method": "reviewed official publisher domain", "corroboration_event_ids": [],
              "evidence_refs": [{"source_id": "wire", "source_url": "https://news.test/a",
                  "raw_hash": "a" * 64, "known_at": "2026-01-01T00:00:00Z", "source_event_id": "evt",
                  "citation": "official company release"}]}
    source = tmp_path / "reviews.json"
    source.write_text(json.dumps([review]), encoding="utf-8")
    assert cli.main(["review-event", str(source), "--db", str(db), "--asof", "2026-01-01T00:00:00Z",
                     "--output", str(tmp_path / "review-out.json")]) == 0
    response_path = tmp_path / "response.json"
    assert cli.main(["respond", "--event-id", "evt", "--company-id", "ACME", "--category",
                     "company_performance", "--asof", "2026-01-01T00:00:00Z", "--db", str(db),
                     "--output", str(response_path)]) == 0
    response = json.loads(response_path.read_text(encoding="utf-8"))
    assert response["action"] == "paper_evaluate_now"
    assert response["reliability"]["cold_start"] is True
    assert response["live_order_authorized"] is False
    assert response["execution"] == "none"
