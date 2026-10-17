"""Append-only, source-linked market relationship evidence store."""
from __future__ import annotations

import json
import math
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit


NODE_TYPES = {"event", "policy", "company", "sector", "index", "economic_factor"}
RELATION_TYPES = {"reported_claim", "documented_exposure", "estimated_effect", "observed_outcome"}
CLAIM_TYPES = RELATION_TYPES
TABLES = ("ctx_events", "ctx_nodes", "ctx_claims", "ctx_relationships", "ctx_relationship_evidence", "ctx_analogs")
SCHEMA = """
CREATE TABLE IF NOT EXISTS ctx_events(event_id TEXT PRIMARY KEY, canonical_id TEXT NOT NULL, available_at TEXT NOT NULL, payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ctx_nodes(node_type TEXT NOT NULL, node_id TEXT NOT NULL, canonical_id TEXT NOT NULL, known_at TEXT NOT NULL, effective_from TEXT NOT NULL, effective_to TEXT, payload_json TEXT NOT NULL, PRIMARY KEY(node_type,node_id));
CREATE TABLE IF NOT EXISTS ctx_claims(claim_id TEXT PRIMARY KEY, event_id TEXT NOT NULL REFERENCES ctx_events(event_id), known_at TEXT NOT NULL, payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ctx_relationships(relationship_id TEXT PRIMARY KEY, subject_type TEXT NOT NULL, subject_id TEXT NOT NULL, object_type TEXT NOT NULL, object_id TEXT NOT NULL, known_at TEXT NOT NULL, payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ctx_analogs(analog_id TEXT PRIMARY KEY, event_id TEXT NOT NULL REFERENCES ctx_events(event_id), decision_at TEXT NOT NULL, completed_at TEXT NOT NULL, known_at TEXT NOT NULL, payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ctx_relationship_evidence(relationship_id TEXT NOT NULL REFERENCES ctx_relationships(relationship_id), claim_id TEXT NOT NULL REFERENCES ctx_claims(claim_id), PRIMARY KEY(relationship_id,claim_id));
"""


class ContextError(ValueError):
    pass


def _json(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError):
        raise ContextError("payload must be finite JSON data") from None


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ContextError(f"{name} is required")
    return value.strip()


def _time(value, name):
    if not isinstance(value, str):
        raise ContextError(f"{name} must be an ISO timestamp with timezone")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ContextError(f"{name} must be an ISO timestamp with timezone") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContextError(f"{name} must be an ISO timestamp with timezone")
    return parsed.astimezone(timezone.utc)


def _stamp(value):
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _hash(value, name):
    value = _text(value, name)
    if not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise ContextError(f"{name} must be a SHA-256 hex digest")
    return value.lower()


def _url(value, name):
    value = _text(value, name)
    try:
        parts = urlsplit(value)
        valid = parts.scheme in ("http", "https") and bool(parts.hostname) and not parts.username and not parts.password
        _ = parts.port
    except ValueError:
        valid = False
    if not valid:
        raise ContextError(f"{name} must be an HTTP(S) URI without credentials")
    return value


def _rows(payload, name):
    rows = payload.get(name, [])
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ContextError(f"{name} must be a list of objects")
    return rows


def _check_event(event):
    for key in ("event_id", "canonical_id", "source_id", "verification_status", "title"):
        _text(event.get(key), f"event.{key}")
    _url(event.get("source_url"), "event.source_url")
    _hash(event.get("raw_hash"), "event.raw_hash")
    available = _time(event.get("available_at"), "event.available_at")
    observed = _time(event.get("observed_at"), "event.observed_at")
    published = _time(event["published_at"], "event.published_at") if event.get("published_at") is not None else None
    if observed > available or (published is not None and published > available):
        raise ContextError("event.available_at precedes its observation or publication")
    if "entities" in event and (not isinstance(event["entities"], list) or any(not isinstance(v, str) or not v for v in event["entities"])):
        raise ContextError("event.entities must be a list of nonempty strings")
    return available


def _check_source(source, name):
    if not isinstance(source, dict):
        raise ContextError(f"{name} must be an object")
    for key in ("source_id", "source_url", "raw_hash", "known_at"):
        _text(source.get(key), f"{name}.{key}") if key in ("source_id", "known_at") else None
    _url(source.get("source_url"), f"{name}.source_url")
    _hash(source.get("raw_hash"), f"{name}.raw_hash")
    return _time(source.get("known_at"), f"{name}.known_at")


def _check_source_event(source, name, events, known_at):
    source_event = source.get("source_event_id")
    if source_event is None:
        return
    source_event = _text(source_event, f"{name}.source_event_id")
    cited = events.get(source_event)
    if cited is None or _time(cited["available_at"], "event.available_at") > known_at:
        raise ContextError(f"{name} references a missing or future source event")
    if (cited["source_id"] != source["source_id"] or cited["raw_hash"].lower() != source["raw_hash"].lower()
            or cited["source_url"] != source["source_url"]):
        raise ContextError(f"{name} source event hash or URL does not match")


def _insert_immutable(connection, table, key, values, payload):
    existing = connection.execute(f"SELECT payload_json FROM {table} WHERE {key}=?", (values[0],)).fetchone()
    encoded = _json(payload)
    if existing:
        if existing[0] != encoded:
            raise ContextError(f"{table} ID already exists with different content: {values[0]}")
        return False
    placeholders = ",".join("?" for _ in range(len(values) + 1))
    connection.execute(f"INSERT INTO {table} VALUES({placeholders})", (*values, encoded))
    return True


def _db(path):
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


class ContextStore:
    def __init__(self, path):
        self.path = Path(path)

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = _db(self.path)
        with closing(connection), connection:
            connection.executescript(SCHEMA)
            for table in TABLES:
                for operation in ("UPDATE", "DELETE"):
                    connection.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_{operation.lower()}_immutable BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT, 'context history is append-only'); END")

    def import_batch(self, batch):
        if not isinstance(batch, dict):
            raise ContextError("import payload must be an object")
        for key in ("events", "nodes", "claims", "relationships", "analogs"):
            _rows(batch, key)
        if not self.path.exists():
            self.initialize()
        events, nodes, claims, relationships, analogs = (_rows(batch, key) for key in ("events", "nodes", "claims", "relationships", "analogs"))
        added = {name: 0 for name in ("events", "nodes", "claims", "relationships", "analogs")}
        connection = _db(self.path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            event_map = {row["event_id"]: row for row in connection.execute("SELECT event_id,payload_json FROM ctx_events")}
            event_map = {key: json.loads(row["payload_json"]) for key, row in event_map.items()}
            for event in events:
                available = _check_event(event)
                event_id = event["event_id"]
                if event_id in event_map and event_map[event_id] != event:
                    raise ContextError(f"ctx_events ID already exists with different content: {event_id}")
                inserted = _insert_immutable(connection, "ctx_events", "event_id", (event_id, event["canonical_id"], _stamp(available)), event)
                added["events"] += inserted
                event_map[event_id] = event
                automatic = {"node_type": "event", "node_id": event_id, "canonical_id": event["canonical_id"], "known_at": event["available_at"], "effective_from": event["available_at"], "effective_to": None, "source": {"source_id": event["source_id"], "source_url": event["source_url"], "raw_hash": event["raw_hash"], "known_at": event["available_at"]}}
                existing = connection.execute("SELECT payload_json FROM ctx_nodes WHERE node_type='event' AND node_id=?", (event_id,)).fetchone()
                encoded = _json(automatic)
                if existing and existing[0] != encoded:
                    raise ContextError(f"event node ID already exists with different content: {event_id}")
                if not existing:
                    connection.execute("INSERT INTO ctx_nodes VALUES(?,?,?,?,?,?,?)", ("event", event_id, event["canonical_id"], _stamp(available), _stamp(available), None, encoded))
                    added["nodes"] += 1
            for node in nodes:
                node_type, node_id = _text(node.get("node_type"), "node.node_type"), _text(node.get("node_id"), "node.node_id")
                if node_type == "event" or node_type not in NODE_TYPES:
                    raise ContextError("node.node_type must be a non-event graph type")
                canonical_id = _text(node.get("canonical_id"), "node.canonical_id")
                known = _time(node.get("known_at"), "node.known_at")
                start = _time(node.get("effective_from"), "node.effective_from")
                end = _time(node["effective_to"], "node.effective_to") if node.get("effective_to") else None
                if end is not None and end <= start:
                    raise ContextError("node.effective_to must follow effective_from")
                source = node.get("source")
                source_known = _check_source(source, "node.source")
                _check_source_event(source, "node.source", event_map, source_known)
                if source_known > known:
                    raise ContextError("node is known before its source")
                payload = {**node, "node_type": node_type, "node_id": node_id, "canonical_id": canonical_id}
                prior = connection.execute("SELECT payload_json FROM ctx_nodes WHERE node_type=? AND node_id=?", (node_type, node_id)).fetchone()
                encoded = _json(payload)
                if prior and prior[0] != encoded:
                    raise ContextError(f"node ID already exists with different content: {node_type}/{node_id}")
                if not prior:
                    connection.execute("INSERT INTO ctx_nodes VALUES(?,?,?,?,?,?,?)", (node_type, node_id, canonical_id, _stamp(known), _stamp(start), _stamp(end) if end else None, encoded))
                    added["nodes"] += 1
            node_map = {(row[0], row[1]) for row in connection.execute("SELECT node_type,node_id FROM ctx_nodes")}
            claim_map = {row[0]: json.loads(row[1]) for row in connection.execute("SELECT claim_id,payload_json FROM ctx_claims")}
            for claim in claims:
                claim_id, event_id = _text(claim.get("claim_id"), "claim.claim_id"), _text(claim.get("event_id"), "claim.event_id")
                if not isinstance(claim.get("claim_type"), str) or claim["claim_type"] not in CLAIM_TYPES or not isinstance(claim.get("text"), str) or not claim["text"].strip():
                    raise ContextError("claim requires a supported claim_type and text")
                if event_id not in event_map:
                    raise ContextError(f"claim references missing event: {event_id}")
                known = _time(claim.get("known_at"), "claim.known_at")
                if _time(event_map[event_id]["available_at"], "event.available_at") > known:
                    raise ContextError("claim refers to an event not yet available")
                refs = claim.get("evidence_refs")
                if not isinstance(refs, list) or not refs:
                    raise ContextError("claim requires evidence_refs")
                for ref in refs:
                    source_known = _check_source(ref, "claim.evidence_ref")
                    if source_known > known:
                        raise ContextError("claim cites evidence not yet known")
                    _check_source_event(ref, "claim.evidence_ref", event_map, source_known)
                for field in ("source_authority", "corroboration_status", "truth_status"):
                    if not isinstance(claim.get(field, "unspecified"), str):
                        raise ContextError(f"claim.{field} must be text; use unspecified when unknown")
                confidence = claim.get("confidence")
                if confidence is not None and (type(confidence) not in (int, float) or not math.isfinite(confidence) or not 0 <= confidence <= 1):
                    raise ContextError("claim.confidence must be null or finite 0..1")
                if event_id not in {key[1] for key in node_map if key[0] == "event"}:
                    raise ContextError(f"claim event node is missing: {event_id}")
                claim = {"source_authority": "unspecified", "corroboration_status": "unspecified", "truth_status": "unspecified", "confidence": None, **claim}
                encoded = _json(claim)
                prior = connection.execute("SELECT payload_json FROM ctx_claims WHERE claim_id=?", (claim_id,)).fetchone()
                if prior and prior[0] != encoded:
                    raise ContextError(f"claim ID already exists with different content: {claim_id}")
                if not prior:
                    connection.execute("INSERT INTO ctx_claims VALUES(?,?,?,?)", (claim_id, event_id, _stamp(known), encoded))
                    added["claims"] += 1
                claim_map[claim_id] = claim
            for relationship in relationships:
                rid = _text(relationship.get("relationship_id"), "relationship.relationship_id")
                st, sid = relationship.get("subject_type"), _text(relationship.get("subject_id"), "relationship.subject_id")
                ot, oid = relationship.get("object_type"), _text(relationship.get("object_id"), "relationship.object_id")
                if not isinstance(st, str) or not isinstance(ot, str) or st not in NODE_TYPES or ot not in NODE_TYPES or (st, sid) not in node_map or (ot, oid) not in node_map:
                    raise ContextError("relationship endpoints must be existing typed nodes")
                if not isinstance(relationship.get("relationship_type"), str) or relationship["relationship_type"] not in RELATION_TYPES:
                    raise ContextError("relationship_type must be reported_claim, documented_exposure, estimated_effect or observed_outcome")
                known = _time(relationship.get("known_at"), "relationship.known_at")
                claim_ids = relationship.get("claim_ids")
                if (not isinstance(claim_ids, list) or not claim_ids
                        or any(not isinstance(cid, str) or not cid for cid in claim_ids)
                        or len(claim_ids) != len(set(claim_ids))):
                    raise ContextError("relationship requires unique claim_ids")
                endpoint_known = {(row["node_type"], row["node_id"]): _time(row["known_at"], "node.known_at")
                                  for row in connection.execute("SELECT node_type,node_id,known_at FROM ctx_nodes")}
                if endpoint_known[(st, sid)] > known or endpoint_known[(ot, oid)] > known:
                    raise ContextError("relationship cites a node not yet known")
                for cid in claim_ids:
                    claim = claim_map.get(cid)
                    if claim is None or _time(claim["known_at"], "claim.known_at") > known:
                        raise ContextError("relationship cites a missing or future claim")
                for field in ("effective_from", "effective_to"):
                    if relationship.get(field) is not None:
                        _time(relationship[field], f"relationship.{field}")
                if relationship.get("effective_to") and _time(relationship["effective_to"], "relationship.effective_to") <= _time(relationship.get("effective_from", relationship["known_at"]), "relationship.effective_from"):
                    raise ContextError("relationship effective interval is invalid")
                estimate = relationship.get("estimate")
                if estimate is not None and (type(estimate) not in (int, float) or not math.isfinite(estimate)):
                    raise ContextError("relationship.estimate must be finite or null")
                if estimate is not None:
                    if relationship["relationship_type"] != "estimated_effect":
                        raise ContextError("numeric impact estimates require relationship_type estimated_effect")
                    _text(relationship.get("unit"), "relationship.unit")
                    horizons = [relationship.get("horizon_days"), relationship.get("horizon_minutes")]
                    if sum(value is not None for value in horizons) != 1 or any(value is not None and (type(value) is not int or value < 1) for value in horizons):
                        raise ContextError("numeric estimates require one positive declared horizon_days or horizon_minutes")
                encoded = _json(relationship)
                prior = connection.execute("SELECT payload_json FROM ctx_relationships WHERE relationship_id=?", (rid,)).fetchone()
                if prior and prior[0] != encoded:
                    raise ContextError(f"relationship ID already exists with different content: {rid}")
                if not prior:
                    connection.execute("INSERT INTO ctx_relationships VALUES(?,?,?,?,?,?,?)", (rid, st, sid, ot, oid, _stamp(known), encoded))
                    for cid in claim_ids:
                        connection.execute("INSERT INTO ctx_relationship_evidence VALUES(?,?)", (rid, cid))
                    added["relationships"] += 1
            for analog in analogs:
                aid, event_id = _text(analog.get("analog_id"), "analog.analog_id"), _text(analog.get("event_id"), "analog.event_id")
                event = event_map.get(event_id)
                if event is None:
                    raise ContextError(f"analog references missing event: {event_id}")
                decision = _time(analog.get("decision_at"), "analog.decision_at")
                completed = _time(analog.get("outcome_completed_at"), "analog.outcome_completed_at")
                known = _time(analog.get("known_at"), "analog.known_at")
                if _time(event["available_at"], "event.available_at") > decision or completed <= decision or known < completed:
                    raise ContextError("analog needs a prior known event and a completed, subsequently recorded outcome")
                horizons = [analog.get("horizon_days"), analog.get("horizon_minutes")]
                if sum(value is not None for value in horizons) != 1 or any(value is not None and (type(value) is not int or value < 1) for value in horizons):
                    raise ContextError("analog requires one positive horizon_days or horizon_minutes")
                for field in ("method", "outcome"):
                    _text(analog.get(field), f"analog.{field}")
                refs = analog.get("evidence_refs")
                if not isinstance(refs, list) or not refs:
                    raise ContextError("analog requires outcome evidence_refs")
                for ref in refs:
                    source_known = _check_source(ref, "analog.evidence_ref")
                    _check_source_event(ref, "analog.evidence_ref", event_map, source_known)
                    if source_known > known:
                        raise ContextError("analog cites evidence not yet known")
                encoded = _json(analog)
                prior = connection.execute("SELECT payload_json FROM ctx_analogs WHERE analog_id=?", (aid,)).fetchone()
                if prior and prior[0] != encoded:
                    raise ContextError(f"analog ID already exists with different content: {aid}")
                if not prior:
                    connection.execute("INSERT INTO ctx_analogs VALUES(?,?,?,?,?,?)", (aid, event_id, _stamp(decision), _stamp(completed), _stamp(known), encoded))
                    added["analogs"] += 1
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return added

    def status(self):
        if not self.path.is_file():
            return {"database": str(self.path), "exists": False, "counts": {table: 0 for table in TABLES}}
        connection = _db(self.path)
        with closing(connection), connection:
            present = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            counts = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] if table in present else 0 for table in TABLES}
        return {"database": str(self.path), "exists": True, "counts": counts}

    def report(self, asof, *, start=None, max_hops=3, limit=100):
        cutoff = _time(asof, "asof")
        if type(max_hops) is not int or not 0 <= max_hops <= 5 or type(limit) is not int or not 1 <= limit <= 500:
            raise ContextError("max_hops must be 0..5 and limit 1..500")
        empty = self.status()
        if not empty["exists"]:
            return {"asof": _stamp(cutoff), "what_trust": {"events": [], "coverage": "no_database"}, "who_how": {"paths": [], "relationships": [], "unique_affected_companies": 0, "coverage": "unknown"}, "why_history": {"analogs": [], "coverage": "unknown"}, "known_gaps": ["No evidence database exists."]}
        connection = _db(self.path)
        with closing(connection), connection:
            raw_events = [json.loads(row[0]) for row in connection.execute("SELECT payload_json FROM ctx_events")]
            selected = {}
            known_event_ids = set()
            for event in raw_events:
                available = _time(event["available_at"], "event.available_at")
                published = _time(event["published_at"], "event.published_at") if event.get("published_at") else None
                if available > cutoff or (published and published > cutoff):
                    continue
                known_event_ids.add(event["event_id"])
                key = event.get("canonical_id") or event["event_id"]
                old = selected.get(key)
                if old is None or (_time(old["available_at"], "event.available_at"), old["event_id"]) < (available, event["event_id"]):
                    selected[key] = event
            visible_events = sorted(selected.values(), key=lambda e: (e["canonical_id"], e["event_id"]))
            event_visible_ids = {event["event_id"] for event in visible_events}
            nodes = {}
            for row in connection.execute("SELECT node_type,node_id,canonical_id,known_at,effective_from,effective_to,payload_json FROM ctx_nodes"):
                key = (row["node_type"], row["node_id"])
                known, start_at = _time(row["known_at"], "node.known_at"), _time(row["effective_from"], "node.effective_from")
                end_at = _time(row["effective_to"], "node.effective_to") if row["effective_to"] else None
                if known <= cutoff and start_at <= cutoff and (end_at is None or cutoff < end_at) and (key[0] != "event" or key[1] in event_visible_ids):
                    nodes[key] = {"node_type": key[0], "node_id": key[1], "canonical_id": row["canonical_id"], "payload": json.loads(row["payload_json"])}
            claims = {}
            for row in connection.execute("SELECT claim_id,event_id,known_at,payload_json FROM ctx_claims"):
                if _time(row["known_at"], "claim.known_at") <= cutoff and row["event_id"] in event_visible_ids:
                    claims[row["claim_id"]] = json.loads(row["payload_json"])
            relationships = []
            ineligible_relationships = []
            for row in connection.execute("SELECT relationship_id,subject_type,subject_id,object_type,object_id,known_at,payload_json FROM ctx_relationships"):
                rel = json.loads(row["payload_json"])
                known = _time(row["known_at"], "relationship.known_at")
                start_at = _time(rel.get("effective_from", rel["known_at"]), "relationship.effective_from")
                end_at = _time(rel["effective_to"], "relationship.effective_to") if rel.get("effective_to") else None
                edge = ((row["subject_type"], row["subject_id"]), (row["object_type"], row["object_id"]))
                evidence = [claims[cid] for cid in rel.get("claim_ids", []) if cid in claims]
                active = known <= cutoff and start_at <= cutoff and (end_at is None or cutoff < end_at) and edge[0] in nodes and edge[1] in nodes
                if active and len(evidence) != len(rel.get("claim_ids", [])):
                    ineligible_relationships.append((edge, rel["relationship_id"]))
                    continue
                if active and evidence:
                    rel["evidence"] = evidence
                    relationships.append((edge, rel))
            analogs = []
            for row in connection.execute("SELECT event_id,decision_at,completed_at,known_at,payload_json FROM ctx_analogs"):
                case = json.loads(row["payload_json"])
                if (row["event_id"] in known_event_ids and _time(row["decision_at"], "analog.decision_at") <= cutoff
                        and _time(row["completed_at"], "analog.completed_at") <= cutoff and _time(row["known_at"], "analog.known_at") <= cutoff):
                    analogs.append(case)
        paths = []
        selected_rels = relationships
        scoped_event_ids = event_visible_ids
        unranked_analogs = []
        traversal_truncated = False
        if start is not None:
            start = tuple(start.split("/", 1)) if isinstance(start, str) and "/" in start else ("", str(start))
            if start not in nodes:
                raise ContextError("start node is unknown at this asof")
            adjacency = {}
            for edge, rel in relationships:
                adjacency.setdefault(edge[0], []).append((edge[1], rel))
            queue = [(start, [start], [])]
            visited = {start}
            seen_rel = set()
            while queue and len(visited) <= limit:
                node, node_path, rel_path = queue.pop(0)
                if rel_path:
                    paths.append({"direction": "subject_to_object", "nodes": [f"{kind}/{node_id}" for kind, node_id in node_path], "relationship_ids": [r["relationship_id"] for r in rel_path]})
                if len(rel_path) >= max_hops:
                    traversal_truncated |= any(other not in node_path for other, _ in adjacency.get(node, []))
                    continue
                for other, rel in sorted(adjacency.get(node, []), key=lambda item: item[1]["relationship_id"]):
                    if other in node_path:
                        seen_rel.add(rel["relationship_id"])
                        continue
                    if other in visited:
                        seen_rel.add(rel["relationship_id"])
                    elif len(visited) < limit:
                        visited.add(other)
                        seen_rel.add(rel["relationship_id"])
                        queue.append((other, node_path + [other], rel_path + [rel]))
                    else:
                        traversal_truncated = True
            selected_rels = [(edge, rel) for edge, rel in relationships if rel["relationship_id"] in seen_rel]
            scoped_event_ids = {node_id for node_type, node_id in visited if node_type == "event"}
            visible_events = [event for event in visible_events if event["event_id"] in scoped_event_ids]
            unranked_analogs = [case for case in analogs if case["event_id"] not in scoped_event_ids]
            analogs = [case for case in analogs if case["event_id"] in scoped_event_ids]
        visible_claims = sorted((claim for claim in claims.values() if claim["event_id"] in scoped_event_ids), key=lambda row: row["claim_id"])
        ineligible_relationship_count = sum(1 for edge, _ in ineligible_relationships
                                            if start is None or edge[0] in visited)
        company_ids = {nodes[key]["canonical_id"] for edge, _ in selected_rels for key in edge if key[0] == "company"}
        gaps = []
        if not visible_events:
            gaps.append("No events known by the selected asof.")
        if not selected_rels:
            gaps.append("No sourced relationship claims are available; who/how remains unknown.")
        if not analogs:
            gaps.append("No completed historical analog outcomes are available; why/history remains unknown.")
        if unranked_analogs:
            gaps.append("Historical outcomes are shown as unranked inventory because no evidence links them to this graph scope.")
        if ineligible_relationship_count:
            gaps.append(f"{ineligible_relationship_count} relationship(s) were withheld because one or more cited claims were not eligible at this asof.")
        if traversal_truncated:
            gaps.append("Graph results are partial because the hop or node limit was reached.")
        return {"asof": _stamp(cutoff),
                "source_integrity_scope": "SHA-256 format and normalized event-reference consistency are checked; source payload authenticity is not verified.",
                "what_trust": {"events": [{**event, "source_lineage": {"source_id": event["source_id"], "source_url": event["source_url"], "raw_hash": event["raw_hash"], "raw_hash_semantics": "upstream digest; not recomputed from normalized event JSON"}} for event in visible_events], "claims": visible_claims, "coverage": ("available" if selected_rels else "claims_available" if visible_claims else "events_only") if visible_events else "unknown"},
                "who_how": {"paths": paths, "relationships": [rel for _, rel in selected_rels], "unique_affected_companies": len(company_ids), "truncated": traversal_truncated, "coverage": "partial" if traversal_truncated else "available" if selected_rels else "unknown"},
                "why_history": {"analogs": sorted(analogs, key=lambda row: row["analog_id"]), "unranked_inventory": sorted(unranked_analogs, key=lambda row: row["analog_id"]), "horizon_interpretation": "declared horizon; not inferred from timestamps", "coverage": "evidence_only" if analogs else "unknown"}, "known_gaps": gaps}

