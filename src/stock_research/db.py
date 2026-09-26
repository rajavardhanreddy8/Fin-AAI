from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS securities (
    isin TEXT PRIMARY KEY,
    company_name TEXT NOT NULL,
    nse_symbol TEXT,
    bse_code TEXT,
    sector TEXT,
    style_bucket TEXT NOT NULL DEFAULT 'watchlist',
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_securities_nse
    ON securities(nse_symbol) WHERE nse_symbol IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_securities_bse
    ON securities(bse_code) WHERE bse_code IS NOT NULL;

CREATE TABLE IF NOT EXISTS sources (
    source_id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    base_url TEXT,
    evidence_tier TEXT NOT NULL CHECK(evidence_tier IN
        ('official', 'company_primary', 'reputable_secondary', 'market_opinion', 'social')),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1)),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    document_id INTEGER PRIMARY KEY AUTOINCREMENT,
    isin TEXT,
    source_id TEXT NOT NULL,
    document_type TEXT NOT NULL,
    title TEXT NOT NULL,
    published_at TEXT,
    retrieved_at TEXT NOT NULL,
    source_location TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
    raw_text TEXT,
    document_key TEXT,
    period_end TEXT,
    reporting_scope TEXT NOT NULL DEFAULT 'consolidated',
    validation_status TEXT NOT NULL DEFAULT 'accepted'
        CHECK(validation_status IN ('accepted', 'rejected')),
    FOREIGN KEY(isin) REFERENCES securities(isin),
    FOREIGN KEY(source_id) REFERENCES sources(source_id),
    UNIQUE(source_id, source_location, content_hash)
);
CREATE INDEX IF NOT EXISTS ix_documents_isin_published
    ON documents(isin, published_at DESC);

CREATE TABLE IF NOT EXISTS price_bars (
    isin TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    close REAL NOT NULL CHECK(close > 0),
    volume INTEGER CHECK(volume IS NULL OR volume >= 0),
    source_id TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    PRIMARY KEY(isin, trade_date, source_id),
    FOREIGN KEY(isin) REFERENCES securities(isin),
    FOREIGN KEY(source_id) REFERENCES sources(source_id)
);

CREATE TABLE IF NOT EXISTS financial_facts (
    fact_id INTEGER PRIMARY KEY AUTOINCREMENT,
    isin TEXT NOT NULL,
    metric TEXT NOT NULL,
    value REAL,
    unit TEXT,
    period_end TEXT NOT NULL,
    period_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    document_id INTEGER,
    retrieved_at TEXT NOT NULL,
    publication_date TEXT,
    currency TEXT NOT NULL DEFAULT 'INR',
    source_value TEXT,
    source_location TEXT,
    evidence_label TEXT NOT NULL DEFAULT 'fact_source_reported',
    confidence_label TEXT NOT NULL DEFAULT 'high'
        CHECK(confidence_label IN ('high', 'medium', 'low')),
    statement_scope TEXT NOT NULL DEFAULT 'consolidated',
    validation_status TEXT NOT NULL DEFAULT 'accepted'
        CHECK(validation_status IN ('accepted', 'rejected')),
    FOREIGN KEY(isin) REFERENCES securities(isin),
    FOREIGN KEY(source_id) REFERENCES sources(source_id),
    FOREIGN KEY(document_id) REFERENCES documents(document_id),
    UNIQUE(isin, metric, period_end, period_type, source_id, statement_scope)
);

CREATE TABLE IF NOT EXISTS ownership_facts (
    ownership_fact_id INTEGER PRIMARY KEY AUTOINCREMENT,
    isin TEXT NOT NULL,
    metric TEXT NOT NULL CHECK(metric IN
        ('promoter_holding_pct', 'promoter_shares', 'promoter_pledged_flag')),
    value REAL NOT NULL,
    unit TEXT NOT NULL CHECK(unit IN ('ratio', 'shares', 'boolean')),
    period_end TEXT NOT NULL,
    source_id TEXT NOT NULL,
    document_id INTEGER NOT NULL,
    retrieved_at TEXT NOT NULL,
    source_location TEXT NOT NULL,
    evidence_label TEXT NOT NULL,
    validation_status TEXT NOT NULL DEFAULT 'accepted'
        CHECK(validation_status IN ('accepted', 'rejected')),
    FOREIGN KEY(isin) REFERENCES securities(isin),
    FOREIGN KEY(source_id) REFERENCES sources(source_id),
    FOREIGN KEY(document_id) REFERENCES documents(document_id),
    UNIQUE(isin, metric, period_end, source_id)
);
CREATE INDEX IF NOT EXISTS ix_ownership_facts_isin_period
    ON ownership_facts(isin, period_end DESC, metric);

CREATE TABLE IF NOT EXISTS portfolio_holdings (
    holding_id INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_name TEXT NOT NULL,
    isin TEXT NOT NULL,
    quantity REAL NOT NULL CHECK(quantity >= 0),
    average_cost REAL CHECK(average_cost IS NULL OR average_cost >= 0),
    as_of_date TEXT NOT NULL,
    import_source TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    FOREIGN KEY(isin) REFERENCES securities(isin),
    UNIQUE(portfolio_name, isin, as_of_date)
);

CREATE TABLE IF NOT EXISTS watchlist (
    isin TEXT PRIMARY KEY,
    added_at TEXT NOT NULL,
    reason TEXT,
    priority INTEGER NOT NULL DEFAULT 3 CHECK(priority BETWEEN 1 AND 5),
    FOREIGN KEY(isin) REFERENCES securities(isin)
);

CREATE TABLE IF NOT EXISTS recommendations (
    recommendation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    isin TEXT NOT NULL,
    created_at TEXT NOT NULL,
    classification TEXT NOT NULL CHECK(classification IN
        ('core_investment', 'high_risk_investment', 'speculative_investment', 'watchlist_only', 'avoid')),
    action TEXT NOT NULL,
    score REAL,
    confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
    facts_json TEXT NOT NULL,
    assumptions_json TEXT NOT NULL,
    risks_json TEXT NOT NULL,
    opinion TEXT NOT NULL,
    entry_zone_json TEXT,
    exit_triggers_json TEXT NOT NULL CHECK(exit_triggers_json <> '[]'),
    thesis TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    FOREIGN KEY(isin) REFERENCES securities(isin)
);

CREATE TABLE IF NOT EXISTS recommendation_evidence (
    recommendation_id INTEGER NOT NULL,
    document_id INTEGER NOT NULL,
    claim TEXT NOT NULL,
    PRIMARY KEY(recommendation_id, document_id, claim),
    FOREIGN KEY(recommendation_id) REFERENCES recommendations(recommendation_id),
    FOREIGN KEY(document_id) REFERENCES documents(document_id)
);

CREATE TABLE IF NOT EXISTS recommendation_outcomes (
    outcome_id INTEGER PRIMARY KEY AUTOINCREMENT,
    recommendation_id INTEGER NOT NULL,
    measured_at TEXT NOT NULL,
    horizon_days INTEGER NOT NULL CHECK(horizon_days > 0),
    absolute_return REAL,
    benchmark_return REAL,
    thesis_status TEXT NOT NULL,
    review_notes TEXT,
    FOREIGN KEY(recommendation_id) REFERENCES recommendations(recommendation_id),
    UNIQUE(recommendation_id, horizon_days)
);

CREATE TABLE IF NOT EXISTS quality_issues (
    issue_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    isin TEXT,
    check_name TEXT NOT NULL,
    severity TEXT NOT NULL CHECK(severity IN ('info', 'warning', 'blocking')),
    message TEXT NOT NULL,
    detected_at TEXT NOT NULL,
    resolved_at TEXT,
    FOREIGN KEY(isin) REFERENCES securities(isin)
);

CREATE TABLE IF NOT EXISTS governance_flags (
    flag_id INTEGER PRIMARY KEY AUTOINCREMENT,
    isin TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    event_key TEXT NOT NULL,
    severity TEXT NOT NULL CHECK(severity IN ('info', 'warning', 'blocking')),
    message TEXT NOT NULL,
    source_document_id INTEGER,
    detected_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open', 'resolved')),
    FOREIGN KEY(isin) REFERENCES securities(isin),
    FOREIGN KEY(source_document_id) REFERENCES documents(document_id),
    UNIQUE(isin, rule_id, event_key)
);
CREATE INDEX IF NOT EXISTS ix_governance_flags_isin_status
    ON governance_flags(isin, status, detected_at DESC);

CREATE TABLE IF NOT EXISTS material_changes (
    change_id INTEGER PRIMARY KEY AUTOINCREMENT,
    isin TEXT NOT NULL,
    change_key TEXT NOT NULL,
    change_type TEXT NOT NULL,
    severity TEXT NOT NULL CHECK(severity IN ('info', 'warning', 'blocking')),
    summary TEXT NOT NULL,
    source_document_id INTEGER,
    effective_date TEXT NOT NULL,
    detected_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new' CHECK(status IN ('new', 'reviewed')),
    FOREIGN KEY(isin) REFERENCES securities(isin),
    FOREIGN KEY(source_document_id) REFERENCES documents(document_id),
    UNIQUE(isin, change_key)
);
CREATE INDEX IF NOT EXISTS ix_material_changes_isin_effective
    ON material_changes(isin, effective_date DESC, severity);

CREATE TRIGGER IF NOT EXISTS recommendations_no_update
BEFORE UPDATE ON recommendations
BEGIN
    SELECT RAISE(ABORT, 'recommendations are append-only');
END;

CREATE TRIGGER IF NOT EXISTS recommendations_no_delete
BEFORE DELETE ON recommendations
BEGIN
    SELECT RAISE(ABORT, 'recommendations are append-only');
END;
"""


def _open_connection(path: str | Path) -> sqlite3.Connection:
    """Create and configure a raw SQLite connection."""
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")

    return connection


@contextmanager
def connect(path: str | Path) -> Iterator[sqlite3.Connection]:
    """Open a connection and always release the SQLite file handle.

    SQLite's built-in connection context manager commits or rolls back,
    but it does not close the connection. This can leave the database
    locked on Windows and cause WinError 32 during temporary-directory
    cleanup.
    """
    connection = _open_connection(path)

    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database(path: str | Path) -> None:
    with connect(path) as connection:
        connection.executescript(SCHEMA)
        _ensure_phase2_columns(connection)


def _ensure_phase2_columns(connection: sqlite3.Connection) -> None:
    """Add non-destructive Phase 2 provenance fields to existing SQLite files."""
    additions = {
        "documents": {
            "document_key": "TEXT",
            "period_end": "TEXT",
            "reporting_scope": "TEXT NOT NULL DEFAULT 'consolidated'",
            "validation_status": "TEXT NOT NULL DEFAULT 'accepted'",
        },
        "financial_facts": {
            "publication_date": "TEXT",
            "currency": "TEXT NOT NULL DEFAULT 'INR'",
            "source_value": "TEXT",
            "source_location": "TEXT",
            "evidence_label": "TEXT NOT NULL DEFAULT 'fact_source_reported'",
            "confidence_label": "TEXT NOT NULL DEFAULT 'high'",
            "statement_scope": "TEXT NOT NULL DEFAULT 'consolidated'",
            "validation_status": "TEXT NOT NULL DEFAULT 'accepted'",
        },
    }
    for table, columns in additions.items():
        existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
        for column, definition in columns.items():
            if column not in existing:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


@contextmanager
def transaction(path: str | Path) -> Iterator[sqlite3.Connection]:
    connection = _open_connection(path)
    try:
        connection.execute("BEGIN")
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
