"""Convert bounded, cited Nova hypotheses into immutable graph evidence and scores."""
from __future__ import annotations

from datetime import datetime, timezone
from contextlib import closing
import json
import sqlite3

from .document_parser_agents import validate_relationship_output
from .impact_graph import build_snapshot
from .pilot_agents import NOVA_MODEL, aware, canonical, digest
from .relationship_agent import validate_relationship_proposals


def save_edge_scores(store, scores: list[dict], *, asof: str, company_id: str) -> int:
    """Append validated score versions; an existing version can never change."""
    build_snapshot(store.report(asof), scores, asof=asof, company_id=company_id, horizon_minutes=30)
    if any(aware(score["score_known_at"]) > aware(asof) for score in scores):
        raise ValueError("cannot admit scores not yet known at the write cutoff")
    added = 0
    with closing(sqlite3.connect(store.path, timeout=10)) as db, db:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("""CREATE TABLE IF NOT EXISTS ctx_edge_scores (
            score_version TEXT NOT NULL, relationship_id TEXT NOT NULL REFERENCES ctx_relationships(relationship_id),
            horizon_minutes INTEGER NOT NULL, known_at TEXT NOT NULL, payload_json TEXT NOT NULL,
            PRIMARY KEY(score_version, relationship_id, horizon_minutes))""")
        db.execute("BEGIN IMMEDIATE")
        for score in scores:
            key = (score["score_version"], score["relationship_id"], score["horizon_minutes"])
            encoded = canonical(score)
            previous = db.execute("SELECT payload_json FROM ctx_edge_scores WHERE score_version=? AND relationship_id=? AND horizon_minutes=?", key).fetchone()
            if previous and previous[0] != encoded:
                raise ValueError("score version already exists with different content; create a new version")
            if not previous:
                known = aware(score["score_known_at"]).astimezone(timezone.utc).isoformat(timespec="microseconds")
                db.execute("INSERT INTO ctx_edge_scores VALUES(?,?,?,?,?)", (*key, known, encoded))
                added += 1
    return added


def load_edge_scores(store, *, score_version: str, asof: str) -> list[dict]:
    """Read one explicitly chosen score version at a point in time."""
    cutoff = aware(asof).astimezone(timezone.utc).isoformat(timespec="microseconds")
    with closing(sqlite3.connect(store.path, timeout=10)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ctx_edge_scores'").fetchone():
            return []
        return [json.loads(row[0]) for row in db.execute(
            "SELECT payload_json FROM ctx_edge_scores WHERE score_version=? AND known_at<=? ORDER BY relationship_id,horizon_minutes",
            (score_version, cutoff))]


def build_impact_batch(document: dict, result: dict, *, title: str, reviewed_directions: list[list[str]] | None = None,
                       now: datetime | None = None) -> dict:
    """Keep quotes as reported claims and model mechanisms as estimated relationships."""
    now = now or datetime.now(timezone.utc)
    audit = result.get("audit")
    if (not isinstance(audit, dict) or result.get("status") != "completed"
            or audit.get("status") != "completed" or audit.get("resolved_model") != NOVA_MODEL
            or audit.get("model_version") != NOVA_MODEL or not audit.get("call_id")
            or not audit.get("request_id") or not audit.get("prompt_hash")):
        raise ValueError("a completed, identified Nova relationship audit is required")
    proposals = validate_relationship_output(result.get("proposals"), document)
    if proposals != audit.get("proposals"):
        raise ValueError("proposals differ from the retained model audit")
    observed = aware(document["observed_at"])
    completed = aware(audit["completion_at"])
    published = aware(document["published_at"]) if document.get("published_at") else None
    if now.tzinfo is None or not observed <= completed <= now or (published and published > observed):
        raise ValueError("source observation and model completion times are inconsistent")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("source title is required")
    raw_hash = digest(document["text"])
    event_id = digest(canonical([document["source_url"], raw_hash, document["observed_at"]]))
    event = {"event_id": event_id, "canonical_id": digest(document["source_url"]),
        "source_id": document["source_id"], "source_url": document["source_url"],
        "published_at": document.get("published_at"), "observed_at": document["observed_at"],
        "available_at": document["observed_at"], "raw_hash": raw_hash,
        "verification_status": "government_reported_unverified", "title": title.strip(),
        "summary": "", "entities": document["company_names"]}
    source = {"source_id": event["source_id"], "source_url": event["source_url"],
        "raw_hash": raw_hash, "known_at": event["available_at"], "source_event_id": event_id}
    batch = {"events": [event], "nodes": [], "claims": [], "relationships": [], "analogs": []}
    allowed_nodes = {(node["node_type"], node["node_id"]) for node in document["allowed_nodes"]}
    if reviewed_directions is not None and (not isinstance(reviewed_directions, list) or not reviewed_directions
            or any(not isinstance(pair, list) or len(pair) != 4 or any(not isinstance(x, str) for x in pair)
                   or tuple(pair[:2]) not in allowed_nodes or tuple(pair[2:]) not in allowed_nodes
                   or pair[:2] == pair[2:] for pair in reviewed_directions)):
        raise ValueError("reviewed directions must identify supplied driver and recipient nodes")
    directions = {tuple(pair) for pair in reviewed_directions} if reviewed_directions is not None else None
    used, claims, scores, withheld = set(), {}, [], []
    version = digest(canonical([NOVA_MODEL, audit["prompt_hash"]]))
    for proposal in proposals:
        direction = tuple(proposal[key] for key in ("subject_type", "subject_id", "object_type", "object_id"))
        if directions is not None and direction not in directions:
            withheld.append({"proposal": proposal, "reason": "Direction was not supported in the reviewed source-specific driver/recipient mapping."})
            continue
        cid = digest(canonical([event_id, proposal["citation"]]))
        claims[cid] = {"claim_id": cid, "event_id": event_id, "claim_type": "reported_claim",
            "text": proposal["citation"], "known_at": audit["completion_at"], "evidence_refs": [source],
            "source_authority": "government_release", "corroboration_status": "single_source",
            "truth_status": "publisher_reported", "confidence": None}
        rid = digest(canonical([event_id, proposal, audit["call_id"]]))
        relationship = {key: proposal[key] for key in ("subject_type", "subject_id", "object_type", "object_id", "mechanism", "horizon_minutes")}
        relationship.update(relationship_id=rid, relationship_type="estimated_effect",
            known_at=audit["completion_at"], claim_ids=[cid], model_call_id=audit["call_id"])
        batch["relationships"].append(relationship)
        scores.append({**{key: proposal[key] for key in ("category", "sentiment", "impact_weight", "confidence", "horizon_minutes")},
            "relationship_id": rid, "score_known_at": audit["completion_at"], "score_version": version,
            "score_mode": "model", "audit_call_id": audit["call_id"], "audit_model_version": NOVA_MODEL,
            "audit_available_at": audit["completion_at"], "audit_status": "completed"})
        used.update(((proposal["subject_type"], proposal["subject_id"]), (proposal["object_type"], proposal["object_id"])))
    for node in document["allowed_nodes"]:
        if (node["node_type"], node["node_id"]) in used:
            batch["nodes"].append({**node, "canonical_id": node["node_id"],
                "known_at": source["known_at"], "effective_from": source["known_at"], "source": source})
    batch["claims"] = list(claims.values())
    company_ids = {node["node_id"] for node in document["allowed_nodes"] if node["node_type"] == "company"}
    validate_relationship_proposals(batch, company_ids)
    return {"batch": batch, "scored_edges": scores, "withheld_proposals": withheld,
        "model_audit": audit, "training_ready": False,
        "known_gaps": ["No verified completed price outcomes; weights are uncalibrated model hypotheses.",
                       "Historical document was observed now and is ineligible for earlier decisions."]}
