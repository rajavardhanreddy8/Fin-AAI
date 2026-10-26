import hashlib
import json
import sqlite3

import pytest

from scripts.extend_primary_graph import extend_primary_graph
from stock_research.context_store import ContextError, ContextStore
from stock_research.primary_document_admission import admit_primary_document_and_store


TEXT = "Power Grid Corporation of India Limited announced a transmission project."


def _envelope(raw):
    return {
        "identity": {"company": "Power Grid Corporation of India Limited", "symbol": "POWERGRID",
            "isin": "INE752E01010", "source_id": "powergrid-issuer",
            "source_url": "https://www.powergrid.in/en/press-release/example", "title": "Transmission project"},
        "time": {"published_at": "2026-10-25", "observed_at": "2026-10-26T02:00:00Z",
            "rights_checked_at": "2026-10-26T02:10:00Z", "available_at": "2026-10-26T02:10:00Z"},
        "rights": {"automated_retrieval": True, "local_retention": True, "derived_claim_storage": True,
            "evidence_ref": "terms-review", "terms_version": "2026-10-26"},
        "content": {"sha256": hashlib.sha256(raw).hexdigest(), "scope": "full_document",
            "citations": ["announced a transmission project"]},
    }


def _base(path, conflicting_event=None):
    store = ContextStore(path)
    source = {"source_id": "existing", "source_url": "https://www.powergrid.in/", "raw_hash": "a" * 64,
        "known_at": "2026-01-01T00:00:00Z"}
    batch = {"events": [], "nodes": [{"node_type": "company", "node_id": "powergrid", "canonical_id": "POWERGRID",
        "known_at": "2026-01-01T00:00:00Z", "effective_from": "2026-01-01T00:00:00Z", "source": source}],
        "claims": [], "relationships": [], "analogs": []}
    if conflicting_event:
        batch["events"].append(conflicting_event)
    store.import_batch(batch)
    with sqlite3.connect(path) as db:
        db.executescript("""
        CREATE TABLE graph_event_versions(event_id TEXT PRIMARY KEY, source_url_key TEXT NOT NULL, payload_json TEXT NOT NULL);
        CREATE TABLE graph_sources(source_id TEXT NOT NULL, source_url TEXT NOT NULL, event_id TEXT NOT NULL, known_at TEXT NOT NULL, raw_hash TEXT NOT NULL, PRIMARY KEY(source_id,source_url,event_id));
        CREATE TABLE graph_adjacency(node_type TEXT NOT NULL, node_id TEXT NOT NULL, direction TEXT NOT NULL, relationship_id TEXT NOT NULL, known_at TEXT NOT NULL, PRIMARY KEY(node_type,node_id,direction,relationship_id));
        CREATE TABLE graph_import_audit(input_name TEXT PRIMARY KEY, sha256 TEXT NOT NULL);
        """)


def _admitted(tmp_path):
    raw = TEXT.encode()
    result = admit_primary_document_and_store(ContextStore(tmp_path / "temporary-context.db"), _envelope(raw), raw,
        start="2026-10-25T00:00:00Z", end="2026-10-27T00:00:00Z",
        interpret=lambda _: [{"title": "POWERGRID transmission project", "citation": "announced a transmission project"}])
    return result


def test_graph_copy_preserves_lineage_adjacency_cutoff_and_idempotent_replay(tmp_path):
    base = tmp_path / "base.db"
    _base(base)
    original = hashlib.sha256(base.read_bytes()).hexdigest()
    result = _admitted(tmp_path)
    output = tmp_path / "extended.db"
    report = extend_primary_graph(base, output, result, asof="2026-10-26T02:10:00Z")
    event = report["primary_import"]["event_id"]
    assert report["primary_import"]["inserted"]["events"] == 1
    assert report["primary_import"]["replay"]["events"] == 0
    assert report["primary_import"]["visible_at_asof"] is True
    assert hashlib.sha256(base.read_bytes()).hexdigest() == original
    with sqlite3.connect(output) as db:
        stored = json.loads(db.execute("SELECT payload_json FROM ctx_events WHERE event_id=?", (event,)).fetchone()[0])
        assert stored["published_at"] is None and stored["published_date"] == "2026-10-25"
        assert stored["publication_precision"] == "date"
        claim_id = db.execute("SELECT claim_id FROM ctx_claims WHERE event_id=?", (event,)).fetchone()[0]
        rel = db.execute("SELECT relationship_id,known_at FROM ctx_relationships WHERE subject_id=?", (event,)).fetchone()
        assert rel and rel[1] == "2026-10-26T02:10:00.000000Z"
        assert db.execute("SELECT count(*) FROM ctx_relationship_evidence WHERE relationship_id=? AND claim_id=?", (rel[0], claim_id)).fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM graph_sources WHERE event_id=? AND raw_hash=?", (event, result["admitted_source"]["raw_hash"])).fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM graph_event_versions WHERE event_id=?", (event,)).fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM graph_adjacency WHERE relationship_id=?", (rel[0],)).fetchone()[0] == 2
    before = extend_primary_graph(base, tmp_path / "before.db", result, asof="2026-10-26T02:09:59Z")
    assert before["primary_import"]["visible_at_asof"] is False
    assert before["what_trust"]["events"] == []


def test_conflicting_immutable_event_id_rejects_new_copy(tmp_path):
    result = _admitted(tmp_path)
    event = result["batch"]["events"][0]
    conflicting = {**event, "title": "different immutable content"}
    base = tmp_path / "conflict.db"
    _base(base, conflicting)
    output = tmp_path / "rejected.db"
    with pytest.raises(ContextError, match="different content"):
        extend_primary_graph(base, output, result, asof="2026-10-26T02:10:00Z")
    assert not output.exists()


def test_reimported_copy_contains_one_identical_version(tmp_path):
    result = _admitted(tmp_path)
    base = tmp_path / "base.db"
    _base(base)
    first = extend_primary_graph(base, tmp_path / "first.db", result, asof="2026-10-26T03:00:00Z")
    second = extend_primary_graph(base, tmp_path / "second.db", result, asof="2026-10-26T03:00:00Z")
    assert first["primary_import"]["event_id"] == second["primary_import"]["event_id"]
    for name in ("first.db", "second.db"):
        with sqlite3.connect(tmp_path / name) as db:
            assert db.execute("SELECT count(*) FROM ctx_events WHERE event_id=?", (first["primary_import"]["event_id"],)).fetchone()[0] == 1
