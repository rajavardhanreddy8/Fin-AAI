"""Scheduled, evidence-first Nifty 500 research and trading evaluation.

This module records what ran and why it abstained. It never routes an order.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from .db import connect
from .nifty_engine import refresh_announcements, refresh_prices, screen_universe
from .nifty_forecasts import make_forecasts, performance, score_forecasts
from .nifty_specialists import run_queue
from .nifty_store import IST, initialize, now_utc, stamp
from .nifty_universe import (
    current_members,
    load_calendar,
    previous_session,
    refresh_calendar,
    refresh_universe,
    session_times,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = PROJECT_ROOT / "output" / "finance-automation.db"
AUTOMATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS automation_runs (
    run_key TEXT PRIMARY KEY, phase TEXT NOT NULL, session_date TEXT NOT NULL,
    status TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT,
    attempts INTEGER NOT NULL DEFAULT 1, report_json TEXT NOT NULL DEFAULT '{}'
);
"""


def phase_gate(phase: str, now: datetime, calendar: dict) -> str | None:
    """Reject non-session and ill-timed runs before touching market evidence."""
    if phase not in ("pre", "post") or now.tzinfo is None:
        raise ValueError("Choose pre or post with a timezone-aware clock")
    local = now.astimezone(IST)
    hours = session_times(calendar, local.date())
    if not hours:
        return "exchange_closed"
    opening, closing = hours
    if phase == "pre" and local >= opening:
        return "after_market_open"
    if phase == "post" and local < closing + timedelta(minutes=15):
        return "before_completed_close"
    return None


def _claim(db: Path, key: str, phase: str, day: str, now: datetime) -> dict | None:
    with connect(db) as c:
        c.execute(AUTOMATION_SCHEMA)
        c.execute("BEGIN IMMEDIATE")
        row = c.execute("SELECT * FROM automation_runs WHERE run_key=?", (key,)).fetchone()
        if row and row["status"] in ("completed", "skipped"):
            old = json.loads(row["report_json"])
            if old.get("reason") != "before_completed_close":
                return old
        if row and row["status"] == "running":
            started = datetime.fromisoformat(row["started_at"])
            if now - started < timedelta(hours=2):
                return {"status": "already_running", "runKey": key, "startedAt": row["started_at"]}
        c.execute("""INSERT INTO automation_runs(run_key,phase,session_date,status,started_at)
                     VALUES(?,?,?,?,?) ON CONFLICT(run_key) DO UPDATE SET
                     status='running',started_at=excluded.started_at,finished_at=NULL,
                     attempts=automation_runs.attempts+1,report_json='{}'""",
                  (key, phase, day, "running", stamp(now)))
    return None


def _finish(db: Path, key: str, report: dict, now: datetime, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"finance-automation-{key.replace(':', '-')}.json"
    temporary = target.with_suffix(".json.tmp")
    report["reportPath"] = str(target)
    temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(target)
    with connect(db) as c:
        c.execute("UPDATE automation_runs SET status=?,finished_at=?,report_json=? WHERE run_key=?",
                  (report["status"], stamp(now), json.dumps(report, ensure_ascii=False), key))
    return report


def _calendar(db: Path, year: int) -> dict:
    try:
        return load_calendar(db, year)
    except ValueError:
        return refresh_calendar(db)


def _membership(db: Path, day: str) -> list[dict]:
    snapshot, members = current_members(db)
    if not snapshot or snapshot["observed_date"] != day:
        refresh_universe(db)
        snapshot, members = current_members(db)
    if not snapshot or len(members) != 500:
        raise ValueError("Current official Nifty 500 membership is incomplete")
    return members


def _trade_evaluation(timeout_seconds: int = 240) -> dict:
    node = shutil.which("node")
    script = PROJECT_ROOT / "scripts" / "evaluate_finance_daily.mjs"
    if not node or not script.exists():
        raise RuntimeError("Node.js or the daily trading evaluator is unavailable")
    completed = subprocess.run(
        [node, str(script)], cwd=PROJECT_ROOT, capture_output=True, text=True,
        timeout=timeout_seconds, check=False,
    )
    if completed.returncode:
        raise RuntimeError((completed.stderr or completed.stdout).strip()[-500:])
    result = json.loads(completed.stdout)
    if not result.get("promotionGate"):
        raise ValueError("Trading evaluation omitted its promotion gate")
    return result


def run_phase(
    phase: str,
    *,
    db: Path = DEFAULT_DB,
    output_dir: Path | None = None,
    now: datetime | None = None,
    max_model_calls: int = 4,
    evaluate_trading: bool = True,
) -> dict:
    now = now or now_utc()
    if now.tzinfo is None or phase not in ("pre", "post") or max_model_calls < 0:
        raise ValueError("A valid phase, timezone-aware clock and nonnegative model budget are required")
    db = Path(db)
    db.parent.mkdir(parents=True, exist_ok=True)
    output_dir = Path(output_dir or db.parent)
    initialize(db)
    day = now.astimezone(IST).date()
    key = f"{day.isoformat()}:{phase}"
    previous = _claim(db, key, phase, day.isoformat(), now)
    if previous is not None:
        return previous
    report: dict = {"runKey": key, "phase": phase, "sessionDate": day.isoformat(),
                    "startedAt": stamp(now), "status": "running", "errors": [],
                    "boundary": "Research and simulation only; no broker orders or rule changes."}
    try:
        calendar = _calendar(db, day.year)
        skip = phase_gate(phase, now, calendar)
        if skip:
            report.update(status="skipped", reason=skip)
            return _finish(db, key, report, now_utc(), output_dir)
        members = _membership(db, day.isoformat())
        report["constituents"] = len(members)
        model = os.getenv("RESEARCH_LLM_MODEL", os.getenv("GROQ_MODEL", "")).strip()
        if phase == "pre":
            prior = previous_session(calendar, day)
            refresh_prices(db, members, prior, sessions=1)
            scan = screen_universe(db, mode="pre_market", model=model,
                                   expected_price_date=prior)
            report["screen"] = scan
            if scan["status"] != "completed":
                report["errors"].extend(scan.get("errors", []))
            else:
                report["forecasts"] = make_forecasts(db, scan["run_id"], calendar)
        else:
            refresh_prices(db, members, day, sessions=1)
            try:
                report["newAnnouncements"] = refresh_announcements(
                    db, members, day - timedelta(days=7), day)
            except Exception as exc:
                report["errors"].append(f"announcements: {type(exc).__name__}: {exc}"[:400])
            scan = screen_universe(db, mode="post_market", model=model,
                                   expected_price_date=day)
            report["screen"] = scan
            report["errors"].extend(scan.get("errors", []))
            report["forecastScores"] = score_forecasts(db, calendar)
            report["forecastPerformance"] = performance(db)
            if evaluate_trading:
                try:
                    report["trading"] = _trade_evaluation()
                except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
                    report["errors"].append(f"trading evaluation: {type(exc).__name__}: {exc}"[:400])
        report["modelQueue"] = run_queue(db, max_calls=max_model_calls) if max_model_calls else {"status": "disabled", "calls": 0}
        report["status"] = "partial" if report["errors"] else "completed"
    except Exception as exc:
        report["status"] = "failed"
        report["errors"].append(f"{type(exc).__name__}: {exc}"[:400])
    return _finish(db, key, report, now_utc(), output_dir)
