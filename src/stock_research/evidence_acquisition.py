"""Plan attributable evidence-acquisition work from a completed coverage screen.

This module deliberately does not guess filing URLs or treat market data as a
substitute for financial disclosures. It creates a bounded queue for official
exchange and company-IR collection routes, preserving every unresolved gap.
"""
from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from .db import connect
from .nifty_store import canonical, digest, now_utc, stamp


TASK_SCHEMA = """
CREATE TABLE IF NOT EXISTS evidence_acquisition_tasks (
    task_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES research_runs(run_id),
    isin TEXT NOT NULL REFERENCES securities(isin),
    symbol TEXT NOT NULL,
    company_name TEXT NOT NULL,
    priority INTEGER NOT NULL CHECK(priority BETWEEN 1 AND 4),
    status TEXT NOT NULL DEFAULT 'planned' CHECK(status IN ('planned','collected','blocked','manual_review')),
    source_routes_json TEXT NOT NULL,
    gaps_json TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(run_id, isin)
);
CREATE INDEX IF NOT EXISTS ix_evidence_acquisition_tasks_run_priority
    ON evidence_acquisition_tasks(run_id, priority, company_name);
"""


def _routes(gaps: list[str]) -> list[str]:
    routes: list[str] = []
    if any("Shareholding" in gap for gap in gaps):
        routes.append("official_nse_shareholding")
    if any("annual" in gap.lower() or "quarterly" in gap.lower() for gap in gaps):
        routes.extend(("official_nse_financial_filing", "company_ir_annual_or_results"))
    if not routes:
        routes.append("manual_source_review")
    return list(dict.fromkeys(routes))


def _priority(status: str, state: str, gaps: list[str], announcements: int) -> tuple[int, str]:
    if status == "stale":
        return 1, "Existing profile is close to usable but needs a fresh disclosed period."
    if status == "blocked" and not any("Unsupported sector" in gap for gap in gaps):
        return 1, "A source-backed blocker needs immediate evidence review."
    if state == "entered":
        return 2, "New index constituent requires an attributable baseline evidence pack."
    if announcements:
        return 2, "Recent official announcements may contain the missing filing evidence."
    if status == "missing":
        return 3, "No research-ready profile exists; acquire only the declared missing disclosures."
    return 4, "Sector-specific or non-document gap needs manual research design."


def plan_acquisition(db: str | Path, run_id: str, *, limit: int = 25) -> dict[str, Any]:
    """Persist a deterministic, bounded evidence queue for one completed screen."""
    if limit < 1:
        raise ValueError("Evidence acquisition batch limit must be positive")
    cutoff = now_utc() - timedelta(days=7)
    with connect(db) as connection:
        connection.executescript(TASK_SCHEMA)
        run = connection.execute("SELECT status FROM research_runs WHERE run_id=?", (run_id,)).fetchone()
        if not run or run["status"] != "completed":
            raise ValueError("Evidence acquisition requires a completed screening run")
        rows = connection.execute(
            """SELECT c.isin,c.status,c.detail_json,m.symbol,m.company_name,m.state,
                      COUNT(d.document_id) AS recent_announcements
                 FROM coverage c JOIN universe_members m ON m.isin=c.isin
                      AND m.snapshot_id=(SELECT membership_id FROM research_runs WHERE run_id=c.run_id)
                 LEFT JOIN documents d ON d.isin=c.isin AND d.document_type='announcement'
                      AND d.published_at>=?
                 WHERE c.run_id=? AND c.status!='verified'
                 GROUP BY c.isin,c.status,c.detail_json,m.symbol,m.company_name,m.state""",
            (stamp(cutoff), run_id),
        ).fetchall()
        planned: list[dict[str, Any]] = []
        for row in rows:
            gaps = json.loads(row["detail_json"])
            priority, reason = _priority(row["status"], row["state"], gaps, row["recent_announcements"])
            planned.append({
                "isin": row["isin"], "symbol": row["symbol"], "companyName": row["company_name"],
                "priority": priority, "gaps": gaps, "sourceRoutes": _routes(gaps), "reason": reason,
                "recentAnnouncements": row["recent_announcements"],
            })
        planned.sort(key=lambda item: (item["priority"], -item["recentAnnouncements"], item["companyName"]))
        selected = planned[:limit]
        created = stamp()
        for task in selected:
            task_id = digest([run_id, task["isin"]])
            connection.execute(
                """INSERT OR IGNORE INTO evidence_acquisition_tasks
                   (task_id,run_id,isin,symbol,company_name,priority,source_routes_json,gaps_json,reason,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (task_id, run_id, task["isin"], task["symbol"], task["companyName"], task["priority"],
                 canonical(task["sourceRoutes"]), canonical(task["gaps"]), task["reason"], created),
            )
            task["taskId"] = task_id
    by_priority = {str(priority): sum(1 for task in selected if task["priority"] == priority) for priority in range(1, 5)}
    return {
        "status": "planned",
        "screeningRunId": run_id,
        "eligible": len(planned),
        "planned": len(selected),
        "byPriority": by_priority,
        "tasks": selected,
        "boundary": "Tasks name official NSE and company-IR source routes only; collection requires attributable documents.",
    }
