"""Append one admitted primary document to a new copy of the POWERGRID graph."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from stock_research.context_store import ContextStore, ContextError
from stock_research.primary_document_admission import POWERGRID

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_company_graph import _aware, _json, _url_key


def extend_primary_graph(base_db: Path, output_db: Path, admitted_result: dict, *, asof: str) -> dict:
    """Copy a graph and append one validated primary-document result; never alter base_db."""
    base_db, output_db = Path(base_db), Path(output_db)
    if not base_db.is_file() or output_db.exists() or base_db.resolve() == output_db.resolve():
        raise ValueError("base graph must exist and output must be a distinct new path")
    cutoff = _aware(asof)
    admitted = admitted_result.get("admitted_source") if isinstance(admitted_result, dict) else None
    parsed = admitted_result.get("batch") if isinstance(admitted_result, dict) else None
    if not isinstance(admitted, dict) or not isinstance(parsed, dict) or len(parsed.get("events", [])) != 1:
        raise ValueError("one primary document admission result is required")
    event = parsed["events"][0]
    published = admitted.get("published_at")
    event = {**event, "published_date": published if isinstance(published, str) and len(published) == 10 else None,
             "publication_precision": "date" if isinstance(published, str) and len(published) == 10 else ("timestamp" if published else "unknown")}
    claims = parsed.get("claims", [])
    if (event.get("source_id") != admitted.get("source_id") or event.get("source_url") != admitted.get("source_url")
            or event.get("raw_hash") != admitted.get("raw_hash") or event.get("observed_at") != admitted.get("observed_at")
            or event.get("available_at") != admitted.get("available_at") or event.get("entities") is None
            or "POWERGRID" not in event["entities"]):
        raise ValueError("parsed event does not match admitted POWERGRID evidence")
    if any(claim.get("event_id") != event["event_id"] or claim.get("known_at") != event["available_at"]
           or claim.get("text") not in admitted.get("citations", []) for claim in claims):
        raise ValueError("claims must cite this event's admitted verbatim evidence")
    if len(claims) > 20:
        raise ValueError("primary document exceeds the claim limit")
    if cutoff < _aware(event["available_at"]):
        # A historical as-of query may intentionally precede the document's availability.
        pass

    output_db.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with output_db.open("xb"):
            created = True
        source = sqlite3.connect(base_db)
        target = sqlite3.connect(output_db)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        connection = sqlite3.connect(output_db)
        connection.row_factory = sqlite3.Row
        try:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            required = {"ctx_events", "ctx_nodes", "ctx_claims", "ctx_relationships", "graph_sources",
                        "graph_event_versions", "graph_adjacency", "graph_import_audit"}
            if not required.issubset(tables):
                raise ValueError("base graph does not have the expected relational schema")
            if connection.execute("SELECT 1 FROM ctx_nodes WHERE node_type='company' AND node_id='powergrid'").fetchone() is None:
                raise ValueError("base graph is missing the POWERGRID company node")

            relationships = []
            if claims:
                cid = claims[0]["claim_id"]
                rid = "primary-mention-" + hashlib.sha256(f'{event["event_id"]}\0{cid}'.encode()).hexdigest()
                relationships.append({"relationship_id": rid, "subject_type": "event", "subject_id": event["event_id"],
                    "object_type": "company", "object_id": "powergrid", "relationship_type": "reported_claim",
                    "claim_ids": [claim["claim_id"] for claim in claims], "known_at": event["available_at"],
                    "effective_from": event["available_at"],
                    "interpretation": "The cited primary document mentions POWERGRID; no directional market impact is asserted."})
            batch = {"events": [event], "nodes": [], "claims": claims, "relationships": relationships, "analogs": []}
            store = ContextStore(output_db)
            inserted = store.import_batch(batch)
            replay = store.import_batch(batch)

            encoded_event = _json(event)
            version = (event["event_id"], _url_key(event["source_url"]), encoded_event)
            existing_version = connection.execute("SELECT source_url_key,payload_json FROM graph_event_versions WHERE event_id=?", (event["event_id"],)).fetchone()
            if existing_version and tuple(existing_version) != version[1:]:
                raise ContextError("graph event version ID already exists with different content")
            connection.execute("INSERT OR IGNORE INTO graph_event_versions VALUES(?,?,?)", version)
            source_row = (event["source_id"], event["source_url"], event["event_id"], event["available_at"], event["raw_hash"])
            existing_source = connection.execute("SELECT source_url,known_at,raw_hash FROM graph_sources WHERE source_id=? AND source_url=? AND event_id=?", source_row[:3]).fetchone()
            if existing_source and tuple(existing_source) != source_row[1:]:
                raise ContextError("graph source row conflicts with immutable event evidence")
            connection.execute("INSERT OR IGNORE INTO graph_sources VALUES(?,?,?,?,?)", source_row)
            for relationship in relationships:
                for node_type, node_id, direction in ((relationship["subject_type"], relationship["subject_id"], "outgoing"),
                                                      (relationship["object_type"], relationship["object_id"], "incoming")):
                    connection.execute("INSERT OR IGNORE INTO graph_adjacency VALUES(?,?,?,?,?)",
                        (node_type, node_id, direction, relationship["relationship_id"], relationship["known_at"]))
            base_hash = hashlib.sha256(base_db.read_bytes()).hexdigest()
            envelope_hash = hashlib.sha256(json.dumps(admitted, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
            audit = [(f"primary-base-{event['event_id']}", base_hash),
                     (f"primary-envelope-{event['event_id']}", envelope_hash),
                     (f"primary-raw-{event['event_id']}", admitted["raw_hash"])]
            for name, digest in audit:
                prior = connection.execute("SELECT sha256 FROM graph_import_audit WHERE input_name=?", (name,)).fetchone()
                if prior and prior[0] != digest:
                    raise ContextError("primary graph audit ID already exists with different content")
            connection.executemany("INSERT OR IGNORE INTO graph_import_audit VALUES(?,?)", audit)
            connection.commit()
        except Exception:
            connection.rollback()
            connection.close()
            raise
        connection.close()
        report = ContextStore(output_db).report(asof, max_hops=1, limit=500)
        report.update({"primary_import": {"event_id": event["event_id"], "source_id": event["source_id"],
            "source_url": event["source_url"], "available_at": event["available_at"], "raw_hash": event["raw_hash"],
            "claims": len(claims), "relationships": len(relationships), "inserted": inserted, "replay": replay,
            "visible_at_asof": _aware(event["available_at"]) <= cutoff, "base_sha256": base_hash,
            "envelope_sha256": envelope_hash}})
        return report
    except Exception:
        if created:
            output_db.unlink(missing_ok=True)
        raise
