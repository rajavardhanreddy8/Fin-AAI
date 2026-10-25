import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.build_company_graph import build
from stock_research.context_store import ContextStore
from stock_research.company_impact import save_edge_scores


NOW = datetime(2026, 10, 25, 11, 0, tzinfo=timezone.utc)
PILOT_EVENT = "pilot-event"
POLICY = "policy-powergrid"
COMPANY = "powergrid"
RELATIONSHIP = "accepted-policy-edge"
CLAIM = "accepted-policy-claim"
SOURCE_URL = "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2232115"
SOURCE_TEXT = "POWERGRID, the largest and most experienced transmission service provider in the country"


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def _inputs(root):
    event_source = {"source_id": "pib", "source_url": SOURCE_URL, "raw_hash": "a" * 64,
                    "known_at": "2026-10-24T06:00:00Z", "source_event_id": PILOT_EVENT}
    event = {"event_id": PILOT_EVENT, "canonical_id": "pilot-canonical", "source_id": "pib",
             "source_url": SOURCE_URL, "raw_hash": "a" * 64, "verification_status": "government_reported_unverified",
             "title": "Cabinet approves delegation to POWERGRID", "available_at": "2026-10-24T06:00:00Z",
             "observed_at": "2026-10-24T06:00:00Z", "published_at": "2026-02-24T10:15:00Z",
             "entities": ["POWERGRID"], "summary": SOURCE_TEXT}
    source_claim = {"claim_id": CLAIM, "event_id": PILOT_EVENT, "claim_type": "reported_claim",
        "text": "Government approved enhanced delegation", "known_at": "2026-10-24T06:05:00Z",
        "evidence_refs": [event_source], "source_authority": "government_release",
        "corroboration_status": "single_source", "truth_status": "publisher_reported", "confidence": None}
    batch = {"events": [event], "nodes": [
        {"node_type": "policy", "node_id": POLICY, "canonical_id": POLICY, "known_at": event["available_at"], "effective_from": event["available_at"], "source": event_source},
        {"node_type": "company", "node_id": COMPANY, "canonical_id": COMPANY, "known_at": event["available_at"], "effective_from": event["available_at"], "source": event_source}],
        "claims": [source_claim], "relationships": [{"relationship_id": RELATIONSHIP, "subject_type": "policy",
            "subject_id": POLICY, "object_type": "company", "object_id": COMPANY, "relationship_type": "estimated_effect",
            "claim_ids": [CLAIM], "known_at": "2026-10-24T06:05:00Z", "mechanism": "increased investment capacity"}], "analogs": []}
    score = {"relationship_id": RELATIONSHIP, "score_known_at": "2026-10-24T06:10:00Z", "score_version": "model-v1",
        "score_mode": "model", "audit_call_id": "audit-1", "audit_model_version": "model-1",
        "audit_available_at": "2026-10-24T06:10:00Z", "audit_status": "completed", "category": "company_performance",
        "sentiment": 0.5, "impact_weight": 0.6, "confidence": 0.75, "horizon_minutes": 30}
    news = {"event_id": "news-event", "canonical_id": "news-canonical", "company_id": "POWERGRID",
        "source_id": "publisher", "source_url": "https://publisher.example/article", "raw_hash": "b" * 64,
        "verification_status": "publisher_reported_unverified", "title": "POWERGRID transmission project",
        "available_at": "2026-10-25T05:00:00Z", "observed_at": "2026-10-25T05:00:00Z",
        "published_at": "2025-01-01T00:00:00Z", "entities": ["POWERGRID"], "summary": "POWERGRID won a transmission project."}
    fulltext = {"event_id": "fulltext-event", "canonical_id": "fulltext-canonical", "source_id": "pib",
        "source_url": SOURCE_URL, "raw_hash": "", "verification_status": "publisher_reported_unverified",
        "title": "Cabinet approves delegation to POWERGRID", "available_at": "2026-10-25T05:00:00Z",
        "observed_at": "2026-10-25T05:00:00Z", "published_at": "2026-02-24T10:15:00Z",
        "entities": ["powergrid"], "summary": SOURCE_TEXT + (" Full source text." * 100)}
    fulltext["raw_hash"] = hashlib.sha256(fulltext["summary"].encode()).hexdigest()
    archive = {"schema_version": "company-history-archive-v1", "built_at_utc": "2026-10-25T05:01:00Z",
        "events": [news, fulltext], "price_outcomes": [{"event_id": "news-event", "company_id": "powergrid",
            "publication_date": "2025-01-01", "previous_trade_date": "2024-12-31", "reaction_trade_date": "2025-01-01",
            "close_to_close_return_pct": 1.0, "source_id": "prices", "source_location": "https://prices.example/",
            "retrieved_at": "2026-10-25T05:05:00Z", "interpretation": "descriptive publication-date close reaction",
            "daily_timestamp_ambiguity": True, "transaction_costs_adjusted": False,
            "causal_attribution": False, "training_label": False}],
        "source_reliability": [{"mean": 0.5, "cold_start": True, "resolved_n": 0, "source_id": "publisher"}],
        "company": {"isin": "INE752E01010", "nse_symbol": "POWERGRID", "aliases": ["Power Grid Corporation of India Limited"]}}
    candidates = {"status": "withheld_research_candidates_only", "citation": SOURCE_TEXT, "category": "company_performance",
        "horizon_minutes": 30, "candidates": [{"citation": "POWERGRID transmission project", "category": "company_performance",
        "horizon_minutes": 30, "source_audit_refs": [{"source_record_id": "news-record", "capture_sha256": "c" * 64,
            "call_id": "proposal-call", "subject_type": "company", "subject_id": COMPANY, "object_type": "event",
            "object_id": "news-event", "direction_status": "withheld"}, {"source_record_id": "news-record-2",
            "capture_sha256": "d" * 64, "call_id": "proposal-call-2", "subject_type": "company", "subject_id": COMPANY,
            "object_type": "event", "object_id": "news-event", "direction_status": "withheld"}]}]}
    pilot = {"batch": batch, "scored_edges": [score], "withheld_proposals": [{"proposal": {
        "subject_type": "company", "subject_id": COMPANY, "object_type": "policy", "object_id": POLICY}}]}
    source = {"source_id": "pib", "source_url": SOURCE_URL, "text": fulltext["summary"]}
    return {
        "archive": _write(root / "archive.json", archive), "pilot": _write(root / "pilot.json", pilot),
        "source": _write(root / "source.json", source), "candidates": _write(root / "candidates.json", candidates),
        "demo": _write(root / "demo.json", {"status": "manual_demo_only"}), "event": news, "score": score,
        "outcome": archive["price_outcomes"][0],
    }


def _build(inputs, root, *, asof=None, now=NOW):
    return build(inputs["archive"], inputs["pilot"], inputs["source"], inputs["candidates"], inputs["demo"],
        root / "graph.db", root / "report.json", root / "review.json", asof=asof, now=now)


def test_builder_preserves_citations_score_registry_and_known_at_cutoff(tmp_path):
    inputs = _inputs(tmp_path / "inputs")
    report = _build(inputs, tmp_path / "output", asof="2026-10-24T06:15:00Z")
    assert len(report["who_how"]["relationships"]) == 1
    assert report["who_how"]["relationships"][0]["relationship_id"] == RELATIONSHIP
    assert report["idempotent_replay"]["relationships"] == 0
    assert report["baseline_score_added"] == 1
    assert len(report["directional_adjacency"][f"company/{COMPANY}"]["incoming"]) == 1
    assert report["directional_adjacency"][f"company/{COMPANY}"]["outgoing"] == []
    assert report["source_reliability"]["status"] == "cold_start_unmeasured"

    with sqlite3.connect(tmp_path / "output/graph.db") as db:
        assert db.execute("SELECT count(*) FROM ctx_edge_scores").fetchone()[0] == 1
        assert save_edge_scores(ContextStore(tmp_path / "output/graph.db"), [inputs["score"]],
            asof=inputs["score"]["score_known_at"], company_id=COMPANY) == 0
        assert db.execute("SELECT count(*) FROM ctx_relationships WHERE subject_type='company' AND subject_id=?", (COMPANY,)).fetchone()[0] == 1
        outcome = json.loads(db.execute("SELECT payload_json FROM graph_daily_outcomes").fetchone()[0])
        assert outcome == inputs["outcome"] and outcome["training_label"] is False and outcome["causal_attribution"] is False
        assert db.execute("SELECT known_at FROM graph_daily_outcomes").fetchone()[0] == "2026-10-25T05:05:00.000000Z"
        assert db.execute("SELECT count(*) FROM graph_review_queue").fetchone()[0] == 3
        assert db.execute("SELECT count(DISTINCT queue_id) FROM graph_review_queue").fetchone()[0] == 3

    with pytest.raises(ValueError, match="new paths"):
        _build(inputs, tmp_path / "output")


def test_bad_manifest_digest_and_causal_daily_labels_are_rejected(tmp_path):
    inputs = _inputs(tmp_path / "inputs")
    _write(inputs["archive"].with_name("manifest.json"), {"artifact_hashes": {"archive_sha256": "0" * 64}})
    with pytest.raises(ValueError, match="manifest"):
        _build(inputs, tmp_path / "bad-manifest")

    inputs = _inputs(tmp_path / "other-inputs")
    archive = json.loads(inputs["archive"].read_text(encoding="utf-8"))
    archive["price_outcomes"][0]["training_label"] = True
    _write(inputs["archive"], archive)
    with pytest.raises(ValueError, match="descriptive"):
        _build(inputs, tmp_path / "bad-label")


def test_saved_artifact_cohort_counts_are_reported_without_assuming_fixed_size(tmp_path):
    inputs = _inputs(tmp_path / "inputs")
    archive_hash = hashlib.sha256(inputs["archive"].read_bytes()).hexdigest()
    _write(inputs["archive"].with_name("manifest.json"), {"artifact_hashes": {"archive_sha256": archive_hash}})
    report = _build(inputs, tmp_path / "output")
    assert report["counts"]["archive_event_versions"] == 2
    assert report["counts"]["daily_descriptive_outcomes"] == 1
    assert report["counts"]["asof_visible_relationships"] == 4
    assert report["asof"] == report["built_at"]
    assert report["input_hashes"]["archive_manifest"] == hashlib.sha256(inputs["archive"].with_name("manifest.json").read_bytes()).hexdigest()
