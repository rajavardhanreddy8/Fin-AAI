"""Assemble saved, cited POWERGRID mentions and the accepted impact pilot offline."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from stock_research.context_store import ContextStore
from stock_research.company_impact import save_edge_scores, load_edge_scores


def _read(path: Path):
    raw = path.read_bytes()
    return json.loads(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest()


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _id(prefix, *parts):
    return prefix + hashlib.sha256("\0".join(parts).encode()).hexdigest()


def _url_key(url):
    parts = urlsplit(url)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, parts.query, ""))


def _aware(value):
    if not isinstance(value, str):
        raise ValueError("timezone-aware timestamp required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("invalid timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timezone-aware timestamp required")
    return parsed.astimezone(timezone.utc)


def build(archive_path: Path, pilot_path: Path, source_path: Path, candidates_path: Path, demo_path: Path,
          database_path: Path, report_path: Path, review_path: Path, *, asof: str | None = None, now: datetime | None = None):
    outputs = [database_path, report_path, review_path]
    if len(set(path.resolve() for path in outputs)) != len(outputs) or any(path.exists() for path in outputs):
        raise ValueError("database, report and review outputs must be distinct new paths")
    archive, archive_hash = _read(archive_path)
    pilot, pilot_hash = _read(pilot_path)
    source, source_hash = _read(source_path)
    candidates, candidates_hash = _read(candidates_path)
    _, demo_hash = _read(demo_path)
    if archive.get("schema_version") != "company-history-archive-v1" or not isinstance(archive.get("events"), list):
        raise ValueError("unsupported history archive")
    identity = archive.get("company", {})
    if (identity.get("isin") != "INE752E01010" or identity.get("nse_symbol") != "POWERGRID"
            or "Power Grid Corporation of India Limited" not in identity.get("aliases", [])):
        raise ValueError("history archive must identify POWERGRID by its saved ISIN and aliases")
    manifest_path = archive_path.with_name("manifest.json")
    manifest_hash = events_file_hash = None
    if manifest_path.exists():
        manifest, manifest_hash = _read(manifest_path)
        if manifest.get("artifact_hashes", {}).get("archive_sha256", "").lower() != archive_hash:
            raise ValueError("archive bytes do not match sibling manifest")
        events_path = archive_path.with_name("events.json")
        if events_path.exists():
            events_file_hash = hashlib.sha256(events_path.read_bytes()).hexdigest()
            if manifest.get("artifact_hashes", {}).get("events_sha256", "").lower() != events_file_hash:
                raise ValueError("events file bytes do not match sibling manifest")
    batch = pilot.get("batch")
    if not isinstance(batch, dict) or not pilot.get("scored_edges"):
        raise ValueError("pilot must contain its original batch and accepted scores")
    events = archive["events"]
    event_ids = [row.get("event_id") for row in events]
    if len(set(event_ids)) != len(events):
        raise ValueError("history archive event IDs must be unique")
    if set(event_ids) & {row.get("event_id") for row in batch.get("events", [])}:
        raise ValueError("pilot and history event versions must retain distinct IDs")
    outcomes = archive.get("price_outcomes")
    if not isinstance(outcomes, list):
        raise ValueError("daily outcomes must be a list")
    if any(row.get("causal_attribution") is not False or row.get("training_label") is not False or row.get("daily_timestamp_ambiguity") is not True for row in outcomes):
        raise ValueError("daily outcomes must remain ambiguous descriptive observations, not causal or training labels")
    if candidates.get("status") != "withheld_research_candidates_only" or not isinstance(candidates.get("candidates"), list):
        raise ValueError("withheld research candidate bundle is required")
    if not isinstance(pilot.get("withheld_proposals", []), list):
        raise ValueError("pilot withheld proposals must be a list")
    cutoff = _aware(asof) if asof else None
    accepted = list(batch.get("relationships", []))
    scores = list(pilot["scored_edges"])
    if len(accepted) != 1 or len(scores) != 1 or scores[0].get("relationship_id") != accepted[0].get("relationship_id"):
        raise ValueError("pilot must contain exactly its original accepted edge and score")
    if scores[0].get("score_mode") != "model" or scores[0].get("audit_status") != "completed":
        raise ValueError("accepted pilot score must retain its completed model audit")

    build_time = now or datetime.now(timezone.utc)
    if build_time.tzinfo is None or build_time.utcoffset() is None:
        raise ValueError("graph build time must be timezone-aware")
    build_at = build_time.astimezone(timezone.utc)
    built_at = build_at.isoformat(timespec="microseconds").replace("+00:00", "Z")
    build_time = build_at
    if cutoff is None:
        cutoff, asof = build_at, built_at
    elif cutoff > build_at:
        raise ValueError("asof cutoff cannot follow graph build time")
    if build_time < max([_aware(event["available_at"]) for event in [*batch["events"], *events]] or [build_time]):
        raise ValueError("graph build time precedes saved source availability")
    company = next((n for n in batch.get("nodes", []) if n.get("node_type") == "company" and n.get("node_id") == "powergrid"), None)
    if not company:
        raise ValueError("pilot's original POWERGRID company node is required")
    quote = "POWERGRID, the largest and most experienced transmission service provider in the country"
    source_event = next((e for e in events if e.get("source_id") == source.get("source_id") and e.get("source_url") == source.get("source_url") and len(e.get("summary", "")) > 1000), None)
    source_text = source.get("text", "")
    if (not source_event or quote not in source_event.get("summary", "") or quote not in source_text
            or hashlib.sha256(source_event["summary"].encode("utf-8")).hexdigest() != source_event["raw_hash"].lower()
            or hashlib.sha256(source_text.encode("utf-8")).hexdigest() != source_event["raw_hash"].lower()):
        raise ValueError("sector exposure quote must match the saved, cited PIB source bytes")
    nodes = list(batch.get("nodes", []))
    claims = list(batch.get("claims", []))
    relationships = list(batch.get("relationships", []))
    sector_id = "electric-power-transmission"
    sector_source = {"source_id": source["source_id"], "source_url": source["source_url"],
                     "raw_hash": source_event["raw_hash"], "known_at": source_event["available_at"], "source_event_id": source_event["event_id"]}
    sector_claim_id = _id("claim-", source_event["event_id"], sector_id, "documented_exposure")
    sector_rel_id = _id("relationship-", source_event["event_id"], sector_id, "documented_exposure")
    nodes.append({"node_type": "sector", "node_id": sector_id, "canonical_id": sector_id,
                  "known_at": built_at, "effective_from": built_at, "source": sector_source,
                  "display_name": "Electric power transmission", "classification_status": "descriptive_business_activity_not_official_sector_or_index_membership"})
    claims.append({"claim_id": sector_claim_id, "event_id": source_event["event_id"], "claim_type": "documented_exposure",
                   "text": "POWERGRID, the largest and most experienced transmission service provider in the country",
                   "known_at": built_at, "evidence_refs": [sector_source], "source_authority": "government_release",
                   "corroboration_status": "single_source", "truth_status": "publisher_reported", "confidence": None})
    relationships.append({"relationship_id": sector_rel_id, "subject_type": "company", "subject_id": "powergrid",
                          "object_type": "sector", "object_id": sector_id, "relationship_type": "documented_exposure",
                          "claim_ids": [sector_claim_id], "known_at": built_at, "effective_from": built_at,
                          "interpretation": "The source describes the company's transmission business; this is not an official classification."})
    source_rows = []
    version_rows = []
    for event in batch["events"]:
        version_rows.append((event["event_id"], _url_key(event["source_url"]), event))
        source_rows.append((event["source_id"], event["source_url"], event["event_id"], event["available_at"], event["raw_hash"]))
    for event in events:
        if (event.get("company_id") != "POWERGRID" and "powergrid" not in [str(v).casefold() for v in event.get("entities", [])]) or event.get("verification_status") != "publisher_reported_unverified":
            raise ValueError("archive event is not a publisher-attributed POWERGRID mention")
        eid = event["event_id"]
        evidence = {"source_id": event["source_id"], "source_url": event["source_url"],
                    "raw_hash": event["raw_hash"], "known_at": event["available_at"], "source_event_id": eid}
        claim_id = _id("mention-claim-", eid)
        rel_id = _id("mention-link-", eid)
        claims.append({"claim_id": claim_id, "event_id": eid, "claim_type": "reported_claim",
                       "text": event.get("summary") or event["title"], "known_at": built_at,
                       "evidence_refs": [evidence], "source_authority": "publisher", "corroboration_status": "single_source",
                       "truth_status": "publisher_reported", "confidence": None,
                       "attribution": event.get("attribution") or "POWERGRID is named in the saved publisher page title and text",
                       "capture_file": event.get("capture_file"),
                       "capture_sha256": event.get("capture_sha256"), "content_scope": event.get("content_hash_basis")})
        relationships.append({"relationship_id": rel_id, "subject_type": "event", "subject_id": eid,
                              "object_type": "company", "object_id": "powergrid", "relationship_type": "reported_claim",
                              "claim_ids": [claim_id], "known_at": built_at, "effective_from": built_at,
                              "interpretation": "publisher explicitly mentions POWERGRID; no directional impact asserted"})
        version_rows.append((eid, _url_key(event["source_url"]), event))
        source_rows.append((event["source_id"], event["source_url"], eid, event["available_at"], event["raw_hash"]))
    # The pilot batch is imported byte-for-byte at the payload level, retaining its original event and edge IDs.
    imported = {"events": list(batch["events"]), "nodes": nodes, "claims": claims,
                "relationships": relationships, "analogs": list(batch.get("analogs", []))}
    imported["events"].extend(events)

    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    try:
        connection.executescript("""
        CREATE TABLE graph_event_versions(event_id TEXT PRIMARY KEY, source_url_key TEXT NOT NULL, payload_json TEXT NOT NULL);
        CREATE TABLE graph_sources(source_id TEXT NOT NULL, source_url TEXT NOT NULL, event_id TEXT NOT NULL, known_at TEXT NOT NULL, raw_hash TEXT NOT NULL, PRIMARY KEY(source_id,source_url,event_id));
        CREATE TABLE graph_daily_outcomes(event_id TEXT NOT NULL, reaction_trade_date TEXT NOT NULL, known_at TEXT NOT NULL, payload_json TEXT NOT NULL, PRIMARY KEY(event_id,reaction_trade_date));
        CREATE TABLE graph_adjacency(node_type TEXT NOT NULL, node_id TEXT NOT NULL, direction TEXT NOT NULL CHECK(direction IN ('incoming','outgoing')), relationship_id TEXT NOT NULL, known_at TEXT NOT NULL, PRIMARY KEY(node_type,node_id,direction,relationship_id));
        CREATE TABLE graph_review_queue(queue_id TEXT PRIMARY KEY, status TEXT NOT NULL, known_at TEXT, subject_type TEXT, subject_id TEXT, object_type TEXT, object_id TEXT, payload_json TEXT NOT NULL);
        CREATE TABLE graph_import_audit(input_name TEXT PRIMARY KEY, sha256 TEXT NOT NULL);
        CREATE VIEW graph_edges_outgoing AS SELECT subject_type AS node_type, subject_id AS node_id, relationship_id, known_at FROM ctx_relationships;
        CREATE VIEW graph_edges_incoming AS SELECT object_type AS node_type, object_id AS node_id, relationship_id, known_at FROM ctx_relationships;
        CREATE VIEW graph_source_event_links AS SELECT source_id,source_url,event_id,known_at,raw_hash FROM graph_sources;
        """)
        ContextStore(database_path).initialize()
        store = ContextStore(database_path)
        added = store.import_batch(imported)
        # Re-import through the public store API proves ID-stable idempotence.
        replay = store.import_batch(imported)
        scores_added = save_edge_scores(store, scores, asof=scores[0]["score_known_at"], company_id="powergrid")
        for eid, key, event in version_rows:
            connection.execute("INSERT INTO graph_event_versions VALUES(?,?,?)", (eid, key, _json(event)))
        for row in source_rows:
            connection.execute("INSERT INTO graph_sources VALUES(?,?,?,?,?)", row)
        available_by_id = {event["event_id"]: event["available_at"] for event in imported["events"]}
        for outcome in outcomes:
            known_at = max(_aware(available_by_id[outcome["event_id"]]), _aware(outcome["retrieved_at"])).isoformat(timespec="microseconds").replace("+00:00", "Z")
            connection.execute("INSERT INTO graph_daily_outcomes VALUES(?,?,?,?)", (outcome["event_id"], outcome["reaction_trade_date"], known_at, _json(outcome)))
        for rel in relationships:
            connection.execute("INSERT INTO graph_adjacency VALUES(?,?,?,?,?)", (rel["subject_type"], rel["subject_id"], "outgoing", rel["relationship_id"], rel["known_at"]))
            connection.execute("INSERT INTO graph_adjacency VALUES(?,?,?,?,?)", (rel["object_type"], rel["object_id"], "incoming", rel["relationship_id"], rel["known_at"]))
        queue = []
        for idx, candidate in enumerate(candidates["candidates"]):
            for ref_idx, proposal in enumerate(candidate.get("source_audit_refs", [])):
                full_proposal = {"citation": candidate.get("citation"), "category": candidate.get("category"),
                    "horizon_minutes": candidate.get("horizon_minutes"), "source_audit_ref": proposal}
                queue.append((f"narrative-{idx+1:02d}-{ref_idx+1:02d}", "withheld_missing_direction_evidence",
                    candidates.get("created_at_utc"), proposal.get("subject_type"), proposal.get("subject_id"),
                    proposal.get("object_type"), proposal.get("object_id"), full_proposal))
        for idx, proposal in enumerate(pilot.get("withheld_proposals", [])):
            row = proposal.get("proposal", {})
            queue.append((f"pilot-{idx+1:02d}", "withheld_missing_direction_evidence", pilot.get("model_audit", {}).get("completion_at"),
                row.get("subject_type"), row.get("subject_id"), row.get("object_type"), row.get("object_id"), proposal))
        for row in queue:
            connection.execute("INSERT INTO graph_review_queue VALUES(?,?,?,?,?,?,?,?)", row[:7] + (_json(row[7]),))
        input_hashes = {"archive": archive_hash, "pilot": pilot_hash, "sector_source": source_hash,
            "withheld_candidates": candidates_hash, "manual_demo_excluded": demo_hash}
        if manifest_hash:
            input_hashes["archive_manifest"] = manifest_hash
        if events_file_hash:
            input_hashes["archive_events"] = events_file_hash
        for name, digest in input_hashes.items():
            connection.execute("INSERT INTO graph_import_audit VALUES(?,?)", (name, digest))
        connection.commit()
    except Exception:
        connection.rollback()
        connection.close()
        database_path.unlink(missing_ok=True)
        raise
    connection.close()
    report = store.report(asof, max_hops=1, limit=500)
    visible_scores = load_edge_scores(store, score_version=scores[0]["score_version"], asof=asof)
    direction = {}
    for rel in report["who_how"]["relationships"]:
        source = f'{rel["subject_type"]}/{rel["subject_id"]}'
        target = f'{rel["object_type"]}/{rel["object_id"]}'
        direction.setdefault(source, {"incoming": [], "outgoing": []})["outgoing"].append(rel["relationship_id"])
        direction.setdefault(target, {"incoming": [], "outgoing": []})["incoming"].append(rel["relationship_id"])
    for value in direction.values():
        value["incoming"].sort(); value["outgoing"].sort()
    urls = Counter(url for _, url, _ in version_rows)
    reliability = archive.get("source_reliability", [])
    visible_reliability = [row for row in reliability if row.get("asof") and _aware(row["asof"]) <= cutoff]
    report.update({"input_hashes": input_hashes, "built_at": built_at,
        "counts": {"archive_event_versions": len(events), "pilot_event_versions": len(batch["events"]),
                   "combined_event_versions": len(events)+len(batch["events"]), "distinct_document_urls": len(urls),
                   "duplicate_url_versions": sum(count-1 for count in urls.values() if count > 1),
                   "daily_descriptive_outcomes": len(outcomes), "accepted_policy_company_edges": len(accepted),
                   "documented_company_business_activity_edges": 1,
                   "withheld_narrative_proposals": len(candidates["candidates"]),
                   "withheld_narrative_evidence_refs": sum(len(row.get("source_audit_refs", [])) for row in candidates["candidates"]),
                   "withheld_pilot_proposals": len(pilot.get("withheld_proposals", [])),
                   "asof_visible_score_versions": len(visible_scores),
                   "inventory_event_versions": len(imported["events"]),
                   "asof_visible_event_versions": sum(_aware(event["available_at"]) <= cutoff for event in imported["events"]),
                   "asof_visible_relationships": len(report["who_how"]["relationships"]),
                   "review_queue_inventory": len(queue),
                   "asof_visible_review_items": sum(row[2] is not None and _aware(row[2]) <= cutoff for row in queue)},
        "imported": added, "idempotent_replay": replay, "baseline_score_added": scores_added,
        "accepted_scores": visible_scores,
        "directional_adjacency": direction,
        "manual_demo": {"status": "excluded_demo_only", "sha256": demo_hash},
        "outcome_interpretation": "Daily publication-date price changes are descriptive only; timestamp ambiguity remains and none are training labels.",
        "source_reliability": {"observations": visible_reliability, "inventory_count": len(reliability), "status": "cold_start_unmeasured"},
        "known_gaps": sorted(set(report.get("known_gaps", []) + [
            "Official sector or index membership and weights lack dated supporting evidence and remain unknown.",
            "Retrieved historical mentions are retrospective evidence; they are not point-in-time trading features."]))})
    review_inventory = [{"queue_id": row[0], "status": row[1], "known_at": row[2], "subject_type": row[3], "subject_id": row[4],
        "object_type": row[5], "object_id": row[6], "proposal": row[7], "visible_at_asof": row[2] is not None and _aware(row[2]) <= cutoff} for row in queue]
    review = {"asof": asof, "known_gaps": ["Official sector and index membership evidence is unavailable; no membership edge or weight is asserted."],
        "pending_connections": [{"subject": "company/powergrid", "object": "official sector membership", "evidence_status": "unverified"},
            {"subject": "company/powergrid", "object": "index membership and weight", "evidence_status": "unverified"}],
        "inventory": review_inventory, "visible_at_asof": [row for row in review_inventory if row["visible_at_asof"]],
        "accepted_policy_company_edge": accepted[0], "manual_demo": "Excluded; retained as a hash-only audit reference, not an active score."}
    for path, payload in ((report_path, report), (review_path, review)):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--sector-source", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--manual-demo", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--asof", help="optional timezone-aware historical cutoff; defaults to the captured build time")
    args = parser.parse_args()
    try:
        build(args.archive, args.pilot, args.sector_source, args.candidates, args.manual_demo,
              args.database, args.report, args.review, asof=args.asof)
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
