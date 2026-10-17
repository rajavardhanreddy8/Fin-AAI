"""Consume one fresh completed bar per invocation. No scheduler or broker calls."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from contextlib import closing, contextmanager
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from stock_research.intraday_pilot import Bar, ExecutionAssumptions, IST, QPolicy, load_bars, pilot_status, replay, _validated_bars
from stock_research.nifty_universe import load_calendar, official_url, session_times
from stock_research.pilot_agents import ACTIONS, aware, build_paper_decider, canonical, digest, provider_readiness
from stock_research.market_context import CATEGORIES


def load_context_snapshot(path: str | Path) -> tuple[dict, str]:
    snapshot = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_context_snapshot(snapshot)


def load_project_env(path: str | Path | None = None) -> None:
    """Load simple KEY=VALUE entries without overriding the caller's environment."""
    env_path = Path(path) if path is not None else Path(__file__).resolve().parents[1] / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not key or not key.replace("_", "a").isalnum() or key[0].isdigit():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


def validate_context_snapshot(snapshot: dict) -> tuple[dict, str]:
    snapshot = dict(snapshot)
    claimed = snapshot.pop("snapshot_hash", None)
    expected = hashlib.sha256(canonical(snapshot).encode()).hexdigest()
    if claimed != expected or snapshot.get("status") != "shadow_unvalidated" or not snapshot.get("asof"):
        raise ValueError("context snapshot hash or shadow status invalid")
    aware(snapshot["asof"])
    categories = snapshot.get("categories")
    if not isinstance(categories, dict) or set(categories) != set(CATEGORIES):
        raise ValueError("context snapshot categories invalid")
    for value in categories.values():
        score, confidence, coverage = value.get("score"), value.get("confidence"), value.get("coverage")
        if (score is not None and not -100 <= float(score) <= 100) or (confidence is not None and not 0 <= float(confidence) <= 1) or type(coverage) is not int or coverage < 0 or not isinstance(value.get("evidence_refs"), list):
            raise ValueError("context snapshot category values invalid")
    snapshot["snapshot_hash"] = claimed
    return snapshot, claimed


def load_frozen_policy(path: str | Path, version: str, assumptions: ExecutionAssumptions) -> tuple[QPolicy, str]:
    """Load an explicitly selected historical policy without changing its status."""
    with closing(sqlite3.connect(path)) as db:
        row = db.execute(
            "SELECT status, values_json, metadata_json FROM pilot_policies WHERE version=?",
            (version,),
        ).fetchone()
    if not row or row[0] not in {"candidate", "active"}:
        raise ValueError("named frozen policy is not an available candidate or active policy")
    metadata = json.loads(row[2])
    if metadata.get("provenance") != "historical-training-only":
        raise ValueError("named frozen policy lacks historical-training provenance")
    if canonical(metadata.get("execution_assumptions")) != canonical(asdict(assumptions)):
        raise ValueError("named frozen policy execution assumptions differ from paper assumptions")
    policy = QPolicy.from_json(row[1])
    policy.version = version
    return policy, f"rl:{version}:{digest(canonical(policy.to_json()))}"


class PaperRunner:
    """Full-prefix deterministic rebuild; journaled API decisions survive restarts."""
    def __init__(self, path: str | Path, run_id: str, calendar: dict, assumptions: ExecutionAssumptions, *, decide: Callable | None = None, policy: QPolicy | None = None, strategy_id: str = "rules-v2", warmup: list[Bar] | None = None, context_snapshot: dict | None = None, now: datetime | None = None) -> None:
        self.path, self.run_id, self.calendar = str(path), run_id, calendar
        self.assumptions, self.decide, self.policy, self.strategy_id = assumptions, decide, policy, strategy_id
        start_clock = "system" if now is None else "injected"
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None or assumptions.decision_latency_seconds <= 0:
            raise ValueError("aware start and positive declared latency required")
        official_url(calendar["source"])
        warmup = _validated_bars(warmup or [], minimum=1) if warmup else []
        if any(bar.at + timedelta(minutes=5) > now for bar in warmup):
            raise ValueError("warmup must be known before paper start")
        config_data = {"strategy_id": strategy_id, "assumptions": asdict(assumptions), "policy": policy.to_json() if policy else None, "warmup": [self.bar_json(bar) for bar in warmup]}
        if context_snapshot is not None:
            config_data["context_snapshot_hash"] = context_snapshot.get("snapshot_hash")
        config = canonical(config_data)
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS forward_runs(run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, config TEXT NOT NULL, summary TEXT NOT NULL, clock_source TEXT NOT NULL DEFAULT 'unknown');
            CREATE TABLE IF NOT EXISTS forward_bars(run_id TEXT NOT NULL, at TEXT NOT NULL, payload TEXT NOT NULL, observed_at TEXT NOT NULL, calendar_json TEXT NOT NULL, clock_source TEXT NOT NULL DEFAULT 'unknown', PRIMARY KEY(run_id,at));
            CREATE TABLE IF NOT EXISTS forward_decisions(run_id TEXT NOT NULL, input_hash TEXT NOT NULL, packet TEXT NOT NULL, action TEXT NOT NULL, decided_at TEXT NOT NULL, audit_json TEXT NOT NULL DEFAULT '{}', PRIMARY KEY(run_id,input_hash));
            CREATE TABLE IF NOT EXISTS forward_trades(run_id TEXT NOT NULL, trade_hash TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(run_id,trade_hash));
            CREATE TABLE IF NOT EXISTS forward_context_snapshots(run_id TEXT NOT NULL, at TEXT NOT NULL, context_hash TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(run_id,at));
            """)
            if "audit_json" not in {row[1] for row in db.execute("PRAGMA table_info(forward_decisions)")}:
                db.execute("ALTER TABLE forward_decisions ADD COLUMN audit_json TEXT NOT NULL DEFAULT '{}'")
            for table in ("forward_runs", "forward_bars"):
                if "clock_source" not in {row[1] for row in db.execute(f"PRAGMA table_info({table})")}:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN clock_source TEXT NOT NULL DEFAULT 'unknown'")
            old = db.execute("SELECT * FROM forward_runs WHERE run_id=?", (run_id,)).fetchone()
            if old and old["config"] != config:
                raise ValueError("paper configuration changed; frozen run cannot resume")
            db.execute("INSERT OR IGNORE INTO forward_runs(run_id,started_at,config,summary,clock_source) VALUES(?,?,?,?,?)", (run_id, now.isoformat(), config, "{}", start_clock))
            self.started_at = aware(old["started_at"]) if old else now
        self.warmup = warmup
        self.context_snapshot = context_snapshot
        if context_snapshot is not None:
            self.context_snapshot, _ = validate_context_snapshot(context_snapshot)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def bar_json(bar: Bar) -> dict:
        return {**asdict(bar), "at": bar.at.isoformat()}

    def ingest(self, bar: Bar, *, now: datetime | None = None) -> dict:
        real_clock = now is None
        now = now or datetime.now(timezone.utc)
        if bar.at.tzinfo is None:
            raise ValueError("forward bar timestamp must include timezone")
        bar = _validated_bars([bar], minimum=1)[0]
        raw = canonical(self.bar_json(bar))
        with self.connect() as db:
            # ponytail: serialized rebuild is O(total observed bars); incremental engine when measured slow.
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT payload FROM forward_bars WHERE run_id=? AND at=?", (self.run_id, bar.at.isoformat())).fetchone()
            if old:
                if old[0] != raw:
                    raise ValueError("completed bar changed after observation")
                return json.loads(db.execute("SELECT summary FROM forward_runs WHERE run_id=?", (self.run_id,)).fetchone()[0])
            completed_at = bar.at + timedelta(minutes=5)
            if now.tzinfo is None or not timedelta(0) <= now - completed_at <= timedelta(seconds=120) or completed_at <= self.started_at:
                raise ValueError("stale, incomplete or historical bar; no forward paper decision")
            bounds = session_times(self.calendar, bar.at.astimezone(IST).date())
            if not bounds or not bounds[0] <= bar.at < bounds[1] or completed_at > bounds[1]:
                raise ValueError("bar outside admitted exchange session")
            if bounds[0].hour != 9 or bounds[0].minute != 15 or bounds[1].hour != 15 or bounds[1].minute != 30:
                raise ValueError("engine special-session timing support unavailable")
            stored = db.execute("SELECT payload FROM forward_bars WHERE run_id=? ORDER BY at", (self.run_id,)).fetchall()
            observed = [Bar(aware(item["at"]), *(item[key] for key in ("open", "high", "low", "close", "volume"))) for item in (json.loads(row[0]) for row in stored)]
            if observed and bar.at <= observed[-1].at:
                raise ValueError("out-of-order forward bar")
            db.execute("INSERT INTO forward_bars(run_id,at,payload,observed_at,calendar_json,clock_source) VALUES(?,?,?,?,?,?)", (self.run_id, bar.at.isoformat(), raw, now.isoformat(), canonical(self.calendar), "system" if real_clock else "injected"))

            context_errors: list[str] = []

            def cached_decide(evidence: dict, rl_action: str | None) -> str:
                decision_at = aware(evidence["decision_at"])
                if decision_at <= self.started_at:
                    return "ABSTAIN"
                packet = canonical({"evidence": evidence, "rl_action": rl_action})
                key = digest(packet)
                cached = db.execute("SELECT action FROM forward_decisions WHERE run_id=? AND input_hash=?", (self.run_id, key)).fetchone()
                if cached:
                    return cached[0]
                if decision_at != completed_at:
                    return "ABSTAIN"  # Recorded early observations only warm indicators.
                if self.context_snapshot is not None:
                    snapshot_at = aware(self.context_snapshot["asof"])
                    if snapshot_at > decision_at:
                        context_errors.append(f"market-context snapshot {snapshot_at.isoformat()} was not available at decision time {decision_at.isoformat()}")
                        return "ABSTAIN"
                    context_hash = self.context_snapshot["snapshot_hash"]
                    existing = db.execute("SELECT context_hash FROM forward_context_snapshots WHERE run_id=? AND at=?", (self.run_id, bar.at.isoformat())).fetchone()
                    if existing and existing[0] != context_hash:
                        context_errors.append("frozen market-context snapshot changed for this bar")
                        return "ABSTAIN"
                    db.execute("INSERT OR IGNORE INTO forward_context_snapshots VALUES(?,?,?,?)", (self.run_id, bar.at.isoformat(), context_hash, canonical(self.context_snapshot)))
                action = self.decide(evidence, rl_action) if self.decide else evidence["rules_action"]
                if action not in ACTIONS:
                    action = "ABSTAIN"
                actual_now = datetime.now(timezone.utc) if real_clock else now
                # A late response cannot be used at an already-passed simulated open.
                if actual_now - decision_at > timedelta(seconds=self.assumptions.decision_latency_seconds):
                    action = "ABSTAIN"
                owner = getattr(self.decide, "__self__", None)
                audit = getattr(owner, "last_audit", {}) if owner else {}
                db.execute("INSERT INTO forward_decisions VALUES(?,?,?,?,?,?)", (self.run_id, key, packet, action, actual_now.isoformat(), canonical(audit)))
                return action

            prefix = self.warmup + observed + [bar]
            if len(prefix) < 35:
                summary = {"provenance": "forward-observed-paper", "status": "indicator_warmup", "observed_bars": len(observed) + 1, "completed_trades": 0, "qualified": False}
                db.execute("UPDATE forward_runs SET summary=? WHERE run_id=?", (canonical(summary), self.run_id))
                return summary
            result = replay(prefix, decide=cached_decide, policy=self.policy, assumptions=self.assumptions, terminal=False)
            if context_errors:
                raise ValueError(context_errors[0])
            trades = [trade for trade in result.trades if aware(trade["entry_at"]) >= self.started_at]
            for trade in trades:
                payload = canonical(trade)
                db.execute("INSERT OR IGNORE INTO forward_trades VALUES(?,?,?)", (self.run_id, digest(payload), payload))
            summary = {"provenance": "forward-observed-paper", "started_at": self.started_at.isoformat(), "observed_bars": len(observed) + 1, "warmup_bars": len(self.warmup), "completed_trades": len(trades), "state": result.final_state, "defects": result.defects, "assumptions": asdict(self.assumptions), "qualified": False, "qualification_gaps": ["execution engine not independently qualified", "calendar amendments/costs/fills remain evidence gaps", "completed full-session qualification not implemented"]}
            db.execute("UPDATE forward_runs SET summary=? WHERE run_id=?", (canonical(summary), self.run_id))
            return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--probe", action="store_true", help="read provider catalogues; no generation")
    parser.add_argument("--bar", help="single completed bar JSON: at/open/high/low/close/volume")
    parser.add_argument("--start", action="store_true", help="persist start before observing bars")
    parser.add_argument("--warmup", help="immutable historical CSV for indicators only")
    parser.add_argument("--state-db", default="output/intraday-forward.db")
    parser.add_argument("--calendar-db", default="output/finance-automation.db")
    parser.add_argument("--run-id", default="niftybees-forward-rules-v2")
    parser.add_argument("--assumptions", help="explicit JSON ExecutionAssumptions; sensitivity inputs, not verified tariffs")
    parser.add_argument("--strategy", choices=("rules", "jev", "nova-jev"), default="rules")
    parser.add_argument("--budget-config", help="secret-free provider price, billing and exact-model evidence JSON")
    parser.add_argument("--usage-db", default="output/intraday-api-usage.db")
    parser.add_argument("--policy-db", help="pilot SQLite database containing the explicitly selected frozen policy")
    parser.add_argument("--policy-version", help="candidate or active historical policy version to use unchanged")
    parser.add_argument("--context-snapshot", help="precomputed frozen shadow market-context JSON snapshot")
    parser.add_argument("--review-pilot-db", help="append the existing read-only candidate and forward-paper review")
    args = parser.parse_args()
    load_project_env()
    try:
        if args.status or args.probe:
            print(json.dumps(provider_readiness(probe=args.probe, budget_config=args.budget_config, strategy=args.strategy), indent=2))
            return 0
        if not args.assumptions or not (args.bar or args.start):
            parser.error("--assumptions and --start or --bar required")
        now = datetime.now(timezone.utc)
        payload = json.loads(Path(args.bar).read_text(encoding="utf-8")) if args.bar else None
        bar = Bar(aware(payload["at"]), *(float(payload[key]) for key in ("open", "high", "low", "close", "volume"))) if payload else None
        costs = ExecutionAssumptions(**json.loads(Path(args.assumptions).read_text(encoding="utf-8")))
        if bool(args.policy_db) != bool(args.policy_version):
            raise ValueError("--policy-db and --policy-version must be supplied together")
        decide, strategy_id = None, "rules-v2"
        if args.strategy != "rules":
            if not args.budget_config:
                raise ValueError("--budget-config is required for a provider strategy")
            decide, strategy_id = build_paper_decider(args.strategy, args.budget_config, args.usage_db, args.run_id, profile=os.getenv("AWS_PROFILE") or None)
        policy = None
        if args.policy_db:
            policy, policy_id = load_frozen_policy(args.policy_db, args.policy_version, costs)
            strategy_id = f"{strategy_id}+{policy_id}"
        calendar = load_calendar(args.calendar_db, (bar.at if bar else now).astimezone(IST).year)
        context_snapshot = load_context_snapshot(args.context_snapshot)[0] if args.context_snapshot else None
        runner = PaperRunner(args.state_db, args.run_id, calendar, costs, decide=decide, policy=policy, strategy_id=strategy_id, warmup=load_bars(args.warmup) if args.warmup else None, context_snapshot=context_snapshot)
        result = runner.ingest(bar) if bar else {"status": "started", "started_at": runner.started_at.isoformat(), "strategy_id": runner.strategy_id, "qualified": False}
        if args.review_pilot_db:
            result = {"paper": result, "candidate_review": pilot_status(args.review_pilot_db, forward_db_path=args.state_db, strategy_id=runner.strategy_id)}
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, KeyError, OSError, sqlite3.Error) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
