"""Additive local tables for dated research runs. No legacy table is rewritten."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from .db import connect, initialize_database

IST = timezone(timedelta(hours=5, minutes=30))


def now_utc():
    return datetime.now(timezone.utc)


def stamp(value=None):
    value = value or now_utc()
    if value.tzinfo is None:
        raise ValueError('An explicit timezone is required')
    return value.astimezone(timezone.utc).isoformat(timespec='microseconds')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


SCHEMA = """
CREATE TABLE IF NOT EXISTS universe_snapshots (
    snapshot_id TEXT PRIMARY KEY, observed_date TEXT NOT NULL, retrieved_at TEXT NOT NULL,
    source_url TEXT NOT NULL, content_hash TEXT NOT NULL, constituent_count INTEGER NOT NULL,
    raw_csv TEXT NOT NULL, UNIQUE(observed_date,content_hash)
);
CREATE TABLE IF NOT EXISTS universe_members (
    snapshot_id TEXT NOT NULL REFERENCES universe_snapshots(snapshot_id),
    isin TEXT NOT NULL REFERENCES securities(isin), symbol TEXT NOT NULL,
    company_name TEXT NOT NULL, industry TEXT NOT NULL, taxonomy TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('entered','retained','exited')),
    PRIMARY KEY(snapshot_id,isin), UNIQUE(snapshot_id,symbol)
);
CREATE TABLE IF NOT EXISTS source_attempts (
    attempt_id INTEGER PRIMARY KEY, source TEXT NOT NULL, attempted_at TEXT NOT NULL,
    status TEXT NOT NULL, detail TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS universe_exclusions (
    snapshot_id TEXT NOT NULL REFERENCES universe_snapshots(snapshot_id),
    symbol TEXT NOT NULL, raw_row_json TEXT NOT NULL, reason TEXT NOT NULL,
    PRIMARY KEY(snapshot_id,symbol)
);
CREATE TABLE IF NOT EXISTS market_calendars (
    calendar_id TEXT PRIMARY KEY, year INTEGER NOT NULL, source_url TEXT NOT NULL,
    retrieved_at TEXT NOT NULL, payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS research_runs (
    run_id TEXT PRIMARY KEY, mode TEXT NOT NULL, started_at TEXT NOT NULL,
    finished_at TEXT, status TEXT NOT NULL, membership_id TEXT,
    detail_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS evidence_snapshots (
    evidence_id TEXT PRIMARY KEY, isin TEXT NOT NULL REFERENCES securities(isin),
    cutoff TEXT NOT NULL, created_at TEXT NOT NULL, content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_evidence_company ON evidence_snapshots(isin,created_at);
CREATE TABLE IF NOT EXISTS coverage (
    run_id TEXT NOT NULL REFERENCES research_runs(run_id), isin TEXT NOT NULL,
    evidence_id TEXT NOT NULL REFERENCES evidence_snapshots(evidence_id),
    status TEXT NOT NULL CHECK(status IN ('verified','stale','missing','blocked')),
    detail_json TEXT NOT NULL, latest_price_date TEXT, last_review_at TEXT,
    PRIMARY KEY(run_id,isin)
);
CREATE TABLE IF NOT EXISTS research_triggers (
    trigger_id TEXT PRIMARY KEY, isin TEXT NOT NULL REFERENCES securities(isin),
    kind TEXT NOT NULL, event_key TEXT NOT NULL, priority INTEGER NOT NULL,
    specialists_json TEXT NOT NULL, evidence_id TEXT NOT NULL REFERENCES evidence_snapshots(evidence_id),
    created_at TEXT NOT NULL, UNIQUE(isin,kind,event_key)
);
CREATE TABLE IF NOT EXISTS specialist_jobs (
    job_id TEXT PRIMARY KEY, isin TEXT NOT NULL, specialist TEXT NOT NULL,
    evidence_id TEXT NOT NULL REFERENCES evidence_snapshots(evidence_id),
    dependency_hash TEXT NOT NULL, prompt_version TEXT NOT NULL, model TEXT NOT NULL,
    priority INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'queued', reason TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, available_at TEXT NOT NULL,
    UNIQUE(isin,specialist,dependency_hash,prompt_version,model)
);
CREATE TABLE IF NOT EXISTS specialist_results (
    result_id TEXT PRIMARY KEY, job_id TEXT NOT NULL UNIQUE REFERENCES specialist_jobs(job_id),
    created_at TEXT NOT NULL, result_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS quota_events (
    event_id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, reserved_tokens INTEGER NOT NULL,
    model TEXT NOT NULL, headers_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS quota_state (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1), blocked_until TEXT NOT NULL, reason TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS forecasts (
    forecast_id TEXT PRIMARY KEY, isin TEXT NOT NULL, target_session TEXT NOT NULL,
    created_at TEXT NOT NULL, cutoff TEXT NOT NULL,
    evidence_id TEXT NOT NULL REFERENCES evidence_snapshots(evidence_id),
    membership_id TEXT NOT NULL REFERENCES universe_snapshots(snapshot_id),
    origin TEXT NOT NULL CHECK(origin IN ('baseline','llm')),
    model_version TEXT NOT NULL, probabilities_json TEXT NOT NULL,
    previous_close REAL NOT NULL CHECK(previous_close>0), previous_session TEXT NOT NULL,
    UNIQUE(isin,target_session,origin)
);
CREATE TABLE IF NOT EXISTS forecast_scores (
    forecast_id TEXT PRIMARY KEY REFERENCES forecasts(forecast_id), measured_at TEXT NOT NULL,
    outcome TEXT NOT NULL, actual_close REAL NOT NULL, return_value REAL NOT NULL,
    accuracy REAL NOT NULL, brier REAL NOT NULL, price_evidence_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS long_term_slots (
    result_id TEXT NOT NULL REFERENCES specialist_results(result_id), months INTEGER NOT NULL CHECK(months IN (3,6,12)),
    due_date TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
    PRIMARY KEY(result_id,months)
);
CREATE TABLE IF NOT EXISTS improvement_proposals (
    proposal_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, title TEXT NOT NULL,
    rationale TEXT NOT NULL, change_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'proposed' CHECK(status IN ('proposed','approved','rejected')),
    decided_at TEXT
);
"""


def initialize(db):
    initialize_database(db)
    with connect(db) as c:
        c.executescript(SCHEMA)
        for table in ('universe_snapshots', 'universe_members', 'universe_exclusions', 'market_calendars',
                      'evidence_snapshots', 'research_triggers', 'specialist_results',
                      'forecasts', 'forecast_scores'):
            for operation in ('UPDATE', 'DELETE'):
                c.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_immutable_{operation} "
                          f"BEFORE {operation} ON {table} BEGIN "
                          "SELECT RAISE(ABORT, 'research history is immutable'); END")


def source_attempt(db, source, status, detail):
    with connect(db) as c:
        c.execute('INSERT INTO source_attempts(source,attempted_at,status,detail) VALUES(?,?,?,?)',
                  (source, stamp(), status, detail))
