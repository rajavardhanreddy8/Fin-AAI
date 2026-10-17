import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from stock_research.context_store import ContextError, ContextStore


def event(event_id="e1", *, canonical="story", available="2026-01-01T00:00:00Z", title="Story", digest="a"):
    return {"event_id": event_id, "canonical_id": canonical, "source_id": "feed", "source_url": f"https://news.test/{digest}",
            "published_at": available, "observed_at": available, "available_at": available, "raw_hash": digest * 64,
            "verification_status": "publisher_reported_unverified", "title": title, "summary": "Reported headline", "entities": []}


def source(row, *, known="2026-01-01T00:00:00Z"):
    return {"source_id": row["source_id"], "source_url": row["source_url"], "raw_hash": row["raw_hash"], "known_at": known,
            "source_event_id": row["event_id"]}


def base_batch():
    e = event()
    claim = {"claim_id": "c1", "event_id": "e1", "claim_type": "documented_exposure", "text": "The filing identifies ACME as exposed.",
             "known_at": "2026-01-01T00:00:00Z", "evidence_refs": [source(e)], "source_authority": "issuer_filing",
             "corroboration_status": "unknown", "truth_status": "unknown", "confidence": None}
    nodes = [{"node_type": "company", "node_id": name, "canonical_id": "ACME", "known_at": "2026-01-01T00:00:00Z",
              "effective_from": "2026-01-01T00:00:00Z", "source": source(e)} for name in ("acme", "acme-alias")]
    rels = [{"relationship_id": name, "subject_type": "event", "subject_id": "e1", "relationship_type": "documented_exposure",
             "object_type": "company", "object_id": target, "known_at": "2026-01-01T00:00:00Z", "claim_ids": ["c1"]}
            for name, target in (("r1", "acme"), ("r2", "acme-alias"))]
    return {"events": [e], "nodes": nodes, "claims": [claim], "relationships": rels, "analogs": []}


def test_import_is_idempotent_and_report_deduplicates_company_paths(tmp_path):
    store = ContextStore(tmp_path / "context.db")
    batch = base_batch()
    assert store.import_batch(batch) == {"events": 1, "nodes": 3, "claims": 1, "relationships": 2, "analogs": 0}
    assert store.import_batch(batch) == {"events": 0, "nodes": 0, "claims": 0, "relationships": 0, "analogs": 0}
    report = store.report("2026-01-02T00:00:00Z", start="event/e1")
    assert len(report["what_trust"]["events"]) == 1
    assert report["who_how"]["unique_affected_companies"] == 1
    assert len(report["who_how"]["relationships"]) == 2
    assert report["who_how"]["relationships"][0]["evidence"][0]["confidence"] is None


def test_conflicting_id_rolls_back_entire_batch(tmp_path):
    store = ContextStore(tmp_path / "context.db")
    store.import_batch({"events": [event()], "nodes": [], "claims": [], "relationships": [], "analogs": []})
    altered = event("e2", canonical="other", digest="b")
    conflict = copy.deepcopy(event(title="Altered"))
    batch = {"events": [altered, conflict], "nodes": [], "claims": [], "relationships": [], "analogs": []}
    with pytest.raises(ContextError, match="different content"):
        store.import_batch(batch)
    assert store.status()["counts"]["ctx_events"] == 1


def test_events_only_are_useful_and_future_event_claim_and_analog_are_hidden(tmp_path):
    store = ContextStore(tmp_path / "context.db")
    old = event()
    future = event("e2", canonical="story", available="2026-01-03T00:00:00Z", title="Later revision", digest="b")
    future_claim = {"claim_id": "future-claim", "event_id": "e2", "claim_type": "reported_claim", "text": "Future claim",
                    "known_at": "2026-01-03T00:00:00Z", "evidence_refs": [source(future, known="2026-01-03T00:00:00Z")]}
    future_relationship = {"relationship_id": "future-r", "subject_type": "event", "subject_id": "e2", "relationship_type": "reported_claim",
                          "object_type": "event", "object_id": "e2", "known_at": "2026-01-03T00:00:00Z", "claim_ids": ["future-claim"]}
    future_analog = {"analog_id": "future-outcome", "event_id": "e1", "decision_at": "2026-01-01T00:00:00Z",
                     "outcome_completed_at": "2026-01-02T00:00:00Z", "known_at": "2026-01-03T00:00:00Z", "horizon_days": 1,
                     "method": "close return", "outcome": "positive", "evidence_refs": [source(old, known="2026-01-03T00:00:00Z")]}
    store.import_batch({"events": [old, future], "nodes": [], "claims": [future_claim], "relationships": [future_relationship], "analogs": [future_analog]})
    early = store.report("2026-01-02T12:00:00Z")
    assert [row["event_id"] for row in early["what_trust"]["events"]] == ["e1"]
    assert early["what_trust"]["coverage"] == "events_only"
    assert early["who_how"]["relationships"] == []
    assert early["why_history"]["analogs"] == []
    assert early["why_history"]["unranked_inventory"] == []
    late = store.report("2026-01-04T00:00:00Z")
    assert [row["event_id"] for row in late["what_trust"]["events"]] == ["e2"]
    assert late["who_how"]["relationships"][0]["evidence"][0]["claim_id"] == "future-claim"
    assert [row["analog_id"] for row in late["why_history"]["analogs"]] == ["future-outcome"]
    scoped = store.report("2026-01-04T00:00:00Z", start="event/e2")
    assert scoped["why_history"]["analogs"] == []
    assert [row["analog_id"] for row in scoped["why_history"]["unranked_inventory"]] == ["future-outcome"]


def test_graph_cycles_keep_lineage_without_repeat_nodes_or_summing(tmp_path):
    store = ContextStore(tmp_path / "context.db")
    batch = base_batch()
    feed = batch["events"][0]
    batch["nodes"].extend([{"node_type": "sector", "node_id": "s1", "canonical_id": "sector-x", "known_at": "2026-01-01T00:00:00Z", "effective_from": "2026-01-01T00:00:00Z", "source": source(feed)},
                           {"node_type": "policy", "node_id": "p1", "canonical_id": "policy-x", "known_at": "2026-01-01T00:00:00Z", "effective_from": "2026-01-01T00:00:00Z", "source": source(feed)},
                           {"node_type": "company", "node_id": "other", "canonical_id": "OTHER", "known_at": "2026-01-01T00:00:00Z", "effective_from": "2026-01-01T00:00:00Z", "source": source(feed)}])
    batch["relationships"].extend([
        {"relationship_id": "r3", "subject_type": "company", "subject_id": "acme", "relationship_type": "estimated_effect", "object_type": "sector", "object_id": "s1", "known_at": "2026-01-01T00:00:00Z", "claim_ids": ["c1"], "estimate": 10, "unit": "percent", "horizon_minutes": 30},
        {"relationship_id": "r4", "subject_type": "sector", "subject_id": "s1", "relationship_type": "reported_claim", "object_type": "policy", "object_id": "p1", "known_at": "2026-01-01T00:00:00Z", "claim_ids": ["c1"]},
        {"relationship_id": "r5", "subject_type": "policy", "subject_id": "p1", "relationship_type": "reported_claim", "object_type": "event", "object_id": "e1", "known_at": "2026-01-01T00:00:00Z", "claim_ids": ["c1"]},
        {"relationship_id": "r6", "subject_type": "company", "subject_id": "other", "relationship_type": "documented_exposure", "object_type": "sector", "object_id": "s1", "known_at": "2026-01-01T00:00:00Z", "claim_ids": ["c1"]},
    ])
    store.import_batch(batch)
    result = store.report("2026-01-02T00:00:00Z", start="event/e1", max_hops=5)
    assert len(result["who_how"]["paths"]) == 4
    assert result["who_how"]["unique_affected_companies"] == 1
    assert result["who_how"]["truncated"] is False
    assert all(path["direction"] == "subject_to_object" for path in result["who_how"]["paths"])
    assert "r6" not in {row["relationship_id"] for row in result["who_how"]["relationships"]}
    assert [row["estimate"] for row in result["who_how"]["relationships"] if "estimate" in row] == [10]
    assert all(row["evidence"][0]["evidence_refs"] for row in result["who_how"]["relationships"])


def test_invalid_future_source_and_dangling_endpoint_reject_atomically(tmp_path):
    store = ContextStore(tmp_path / "context.db")
    batch = base_batch()
    batch["relationships"][0]["object_id"] = "missing"
    with pytest.raises(ContextError, match="existing typed nodes"):
        store.import_batch(batch)
    assert store.status()["counts"]["ctx_events"] == 0

    batch = base_batch()
    batch["claims"][0]["evidence_refs"][0]["known_at"] = "2026-01-01T00:00:01Z"
    with pytest.raises(ContextError, match="not yet known"):
        store.import_batch(batch)
    assert store.status()["counts"]["ctx_events"] == 0

    batch = base_batch()
    future = event("e2", canonical="future", available="2026-01-02T00:00:00Z", digest="b")
    batch["events"].append(future)
    batch["claims"][0]["known_at"] = "2026-01-01T12:00:00Z"
    batch["claims"][0]["evidence_refs"] = [source(future, known="2026-01-01T12:00:00Z")]
    with pytest.raises(ContextError, match="future source event"):
        store.import_batch(batch)
    assert store.status()["counts"]["ctx_events"] == 0


def test_claims_are_reported_without_relationships_and_partial_support_fails_closed(tmp_path):
    store = ContextStore(tmp_path / "context.db")
    e = event()
    known = {"claim_id": "known", "event_id": "e1", "claim_type": "estimated_effect", "text": "A cited analyst estimated a cost.",
             "known_at": "2026-01-01T00:00:00Z", "evidence_refs": [source(e)], "truth_status": "unknown", "confidence": None}
    company = {"node_type": "company", "node_id": "acme", "canonical_id": "ACME", "known_at": "2026-01-01T00:00:00Z",
               "effective_from": "2026-01-01T00:00:00Z", "source": source(e)}
    store.import_batch({"events": [e], "nodes": [company], "claims": [known], "relationships": [], "analogs": []})
    early = store.report("2026-01-02T00:00:00Z", start="event/e1")
    assert [claim["claim_id"] for claim in early["what_trust"]["claims"]] == ["known"]
    assert early["who_how"]["relationships"] == []

    partial_store = ContextStore(tmp_path / "partial.db")
    newer = event("e2", canonical="story", available="2026-01-03T00:00:00Z", title="Later revision", digest="b")
    sector = {"node_type": "sector", "node_id": "s1", "canonical_id": "sector-x", "known_at": "2026-01-01T00:00:00Z",
              "effective_from": "2026-01-01T00:00:00Z", "source": source(e)}
    rel = {"relationship_id": "partial", "subject_type": "company", "subject_id": "acme", "relationship_type": "estimated_effect",
           "object_type": "sector", "object_id": "s1", "known_at": "2026-01-01T00:00:00Z", "claim_ids": ["known"]}
    partial_store.import_batch({"events": [e, newer], "nodes": [company, sector], "claims": [known], "relationships": [rel], "analogs": []})
    asof_late = partial_store.report("2026-01-04T00:00:00Z", start="company/acme")
    assert asof_late["who_how"]["relationships"] == []
    assert any("withheld" in item for item in asof_late["known_gaps"])


def test_traversal_limits_do_not_count_unvisited_companies(tmp_path):
    store = ContextStore(tmp_path / "context.db")
    store.import_batch(base_batch())
    result = store.report("2026-01-02T00:00:00Z", start="event/e1", limit=2)
    assert result["who_how"]["unique_affected_companies"] == 1
    assert result["who_how"]["truncated"] is True
    assert result["who_how"]["coverage"] == "partial"


def test_numeric_estimates_require_effect_type_unit_and_horizon(tmp_path):
    store = ContextStore(tmp_path / "context.db")
    batch = base_batch()
    rel = batch["relationships"][0]
    rel.update(estimate=2.5, unit="percent", horizon_minutes=30)
    with pytest.raises(ContextError, match="estimated_effect"):
        store.import_batch(batch)

    batch = base_batch()
    rel = batch["relationships"][0]
    rel.update(relationship_type="estimated_effect", estimate=2.5, horizon_minutes=30)
    with pytest.raises(ContextError, match="relationship.unit"):
        store.import_batch(batch)


def test_cli_import_status_and_malformed_input_are_concise(tmp_path):
    script = Path(__file__).parents[1] / "scripts" / "run_market_relationships.py"
    db, data = tmp_path / "context.db", tmp_path / "events.json"
    data.write_text(json.dumps({"events": [event()]}), encoding="utf-8")
    imported = subprocess.run([sys.executable, str(script), "import", str(data), "--db", str(db)], capture_output=True, text=True)
    assert imported.returncode == 0 and json.loads(imported.stdout)["events"] == 1
    report = subprocess.run([sys.executable, str(script), "report", "--db", str(db), "--asof", "2026-01-02T00:00:00Z"], capture_output=True, text=True)
    assert report.returncode == 0 and json.loads(report.stdout)["what_trust"]["coverage"] == "events_only"
    data.write_text("{invalid", encoding="utf-8")
    failed = subprocess.run([sys.executable, str(script), "import", str(data), "--db", str(db)], capture_output=True, text=True)
    assert failed.returncode == 2 and "Traceback" not in failed.stderr and "failed" in failed.stderr
