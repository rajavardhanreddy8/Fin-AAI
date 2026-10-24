from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path

import pytest

from stock_research.company_impact import build_impact_batch, load_edge_scores, save_edge_scores
from stock_research.context_store import ContextStore
from stock_research.pilot_agents import NOVA_MODEL


def inputs():
    document = {"source_id": "government_test", "source_url": "https://example.test/release",
        "published_at": "2026-02-24T10:15:00Z", "observed_at": "2026-10-24T06:00:00Z",
        "text": "POWERGRID can expand its investment in transmission projects.",
        "company_names": ["POWERGRID"], "allowed_nodes": [
            {"node_type": "policy", "node_id": "delegation"},
            {"node_type": "company", "node_id": "powergrid"}]}
    proposal = {"title": "Investment capacity may improve", "citation": "POWERGRID can expand its investment",
        "subject_type": "policy", "subject_id": "delegation", "object_type": "company", "object_id": "powergrid",
        "category": "governance_policy", "sentiment": .5, "impact_weight": .2, "confidence": .6,
        "horizon_minutes": 30, "mechanism": "Investment capacity may improve future earnings expectations."}
    audit = {"status": "completed", "resolved_model": NOVA_MODEL, "model_version": NOVA_MODEL,
        "call_id": "a" * 64, "request_id": "test-request", "prompt_hash": "b" * 64,
        "completion_at": "2026-10-24T06:01:00Z", "proposals": [proposal]}
    return document, {"status": "completed", "proposals": [proposal], "audit": audit}


NOW = datetime(2026, 10, 24, 6, 2, tzinfo=timezone.utc)


def test_model_claims_are_stored_once_and_never_backdated_to_publication(tmp_path):
    document, result = inputs()
    output = build_impact_batch(document, result, title="Official policy release", now=NOW)
    batch = output["batch"]
    assert batch["events"][0]["available_at"] == document["observed_at"]
    assert batch["claims"][0]["confidence"] is None
    assert batch["relationships"][0]["relationship_type"] == "estimated_effect"
    assert output["scored_edges"][0]["score_known_at"] == result["audit"]["completion_at"]
    assert output["scored_edges"][0]["audit_available_at"] == result["audit"]["completion_at"]
    store = ContextStore(tmp_path / "graph.db")
    first = store.import_batch(batch)
    assert first["relationships"] == 1
    assert store.import_batch(batch)["relationships"] == 0
    assert store.report("2026-02-25T00:00:00Z")["what_trust"]["events"] == []
    assert store.report("2026-10-24T06:00:30Z")["who_how"]["relationships"] == []
    assert len(store.report(NOW.isoformat())["who_how"]["relationships"]) == 1


@pytest.mark.parametrize("change", ["failed", "tampered", "early_completion", "future_completion", "uncited"])
def test_failed_or_mismatched_model_evidence_is_rejected(change):
    document, result = inputs()
    if change == "failed": result["audit"]["status"] = "failed"
    if change == "tampered": result["proposals"] = [dict(result["proposals"][0], sentiment=-.9)]
    if change == "early_completion": result["audit"]["completion_at"] = "2026-02-24T10:15:00Z"
    if change == "future_completion": result["audit"]["completion_at"] = "2027-01-01T00:00:00Z"
    if change == "uncited":
        result = deepcopy(result)
        result["proposals"][0]["citation"] = "invented quotation"
        result["audit"]["proposals"] = result["proposals"]
    with pytest.raises(ValueError): build_impact_batch(document, result, title="Release", now=NOW)


def test_existing_output_is_rejected_before_building_any_model(tmp_path, monkeypatch):
    path = Path(__file__).parents[1] / "scripts" / "run_company_impact.py"
    spec = importlib.util.spec_from_file_location("company_impact_runner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = tmp_path / "saved.json"
    output.write_text('{"preserved":true}', encoding="utf-8")
    monkeypatch.setattr(module, "build_nova_relationship_interpreter", lambda *a, **k: pytest.fail("model must not be built"))
    assert module.main(["missing.json", "--db", str(tmp_path / "graph.db"), "--output", str(output),
                        "--budget-config", "missing.json", "--usage-db", "missing.db", "--namespace", "test"]) == 2
    assert json.loads(output.read_text())["preserved"] is True


def test_unreviewed_reverse_proposal_is_retained_but_not_imported():
    document, result = inputs()
    result = deepcopy(result)
    reverse = {**result["proposals"][0], "subject_type": "company", "subject_id": "powergrid",
               "object_type": "policy", "object_id": "delegation"}
    result["proposals"].append(reverse)
    result["audit"]["proposals"] = result["proposals"]
    output = build_impact_batch(document, result, title="Release", now=NOW,
        reviewed_directions=[["policy", "delegation", "company", "powergrid"]])
    assert len(output["batch"]["relationships"]) == 1
    assert output["withheld_proposals"][0]["proposal"] == reverse
    assert len(output["model_audit"]["proposals"]) == 2


def test_relational_score_versions_are_append_only_and_time_filtered(tmp_path):
    document, result = inputs()
    data = build_impact_batch(document, result, title="Release", now=NOW)
    store = ContextStore(tmp_path / "graph.db")
    store.import_batch(data["batch"])
    scores = data["scored_edges"]
    assert save_edge_scores(store, scores, asof=NOW.isoformat(), company_id="powergrid") == 1
    assert save_edge_scores(store, scores, asof=NOW.isoformat(), company_id="powergrid") == 0
    version = scores[0]["score_version"]
    assert load_edge_scores(store, score_version=version, asof="2026-10-24T06:00:30Z") == []
    assert load_edge_scores(store, score_version=version, asof=NOW.isoformat()) == scores
    tuned = [{**scores[0], "impact_weight": .9}]
    with pytest.raises(ValueError, match="different content"):
        save_edge_scores(store, tuned, asof=NOW.isoformat(), company_id="powergrid")
    tuned[0]["score_version"] = "new-review-version"
    assert save_edge_scores(store, tuned, asof=NOW.isoformat(), company_id="powergrid") == 1
    assert load_edge_scores(store, score_version=version, asof=NOW.isoformat()) == scores
