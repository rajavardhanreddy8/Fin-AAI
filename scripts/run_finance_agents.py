"""Dispatch the fin-AAI specialist-agent workflow for one market phase."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stock_research.daily_automation import (  # noqa: E402
    DEFAULT_DB,
    _calendar,
    _claim,
    _finish,
    _membership,
    phase_gate,
)
from stock_research.finance_agents import AgentContext, FinanceOrchestrator  # noqa: E402
from stock_research.nifty_store import IST, initialize, now_utc, stamp  # noqa: E402


def run_agent_phase(
    phase: str,
    *,
    db: Path = DEFAULT_DB,
    output_dir: Path | None = None,
    now: datetime | None = None,
    max_model_calls: int = 4,
    evaluate_trading: bool = True,
) -> dict:
    """Run the named-agent workflow once, with the existing idempotent run ledger."""
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
    report: dict = {
        "runKey": key,
        "phase": phase,
        "sessionDate": day.isoformat(),
        "startedAt": stamp(now),
        "status": "running",
        "errors": [],
        "boundary": "Research and simulation only; agents cannot place orders or change rules.",
        "paperTrading": {
            "status": "separate_momentum_ledger",
            "ordersCreated": 0,
            "message": "This local scheduler does not create or advance paper orders; paper positions remain in the authenticated Momentum ledger."
        },
    }
    try:
        calendar = _calendar(db, day.year)
        skip = phase_gate(phase, now, calendar)
        if skip:
            report.update(status="skipped", reason=skip)
            return _finish(db, key, report, now_utc(), output_dir)
        members = _membership(db, day.isoformat())
        report["constituents"] = len(members)
        report["orchestration"] = FinanceOrchestrator().run(AgentContext(
            phase=phase,
            db=db,
            session_date=day,
            calendar=calendar,
            members=members,
            max_model_calls=max_model_calls,
            evaluate_trading=evaluate_trading,
        ))
        report["errors"].extend(report["orchestration"]["errors"])
        report["status"] = report["orchestration"]["status"]
    except Exception as exc:
        report["status"] = "failed"
        report["errors"].append(f"{type(exc).__name__}: {exc}"[:400])
    return _finish(db, key, report, now_utc(), output_dir)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("pre", "post"), required=True)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--max-model-calls", type=int, default=4)
    parser.add_argument("--skip-trading-evaluation", action="store_true")
    args = parser.parse_args()
    report = run_agent_phase(
        args.phase,
        db=args.db,
        max_model_calls=args.max_model_calls,
        evaluate_trading=not args.skip_trading_evaluation,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 2 if report["status"] in ("failed", "partial") else 0


if __name__ == "__main__":
    raise SystemExit(main())


