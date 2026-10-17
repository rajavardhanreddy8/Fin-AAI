"""Consume one atomically written fresh paper-bar handoff and record a local status."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _consume(bar: Path, *, report: Path, runner_args: list[str]) -> int:
    observed_at = datetime.now(timezone.utc).isoformat()
    if not bar.exists():
        write_json(report, {"status": "waiting", "observed_at": observed_at, "bar": str(bar), "message": "No admitted completed-bar handoff is available."})
        return 0
    try:
        payload = json.loads(bar.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not all(key in payload for key in ("at", "open", "high", "low", "close", "volume")):
            raise ValueError("handoff is not a complete paper bar")
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "run_intraday_paper.py"), "--bar", str(bar), *runner_args], cwd=ROOT, capture_output=True, text=True, timeout=30, env=os.environ.copy())
        detail = json.loads(result.stdout) if result.stdout.strip().startswith("{") else {"stdout": result.stdout[-1000:], "stderr": result.stderr[-1000:]}
        if result.returncode:
            write_json(report, {"status": "blocked", "observed_at": observed_at, "bar": str(bar), "runner": detail})
            return 2
        archived = bar.parent / "processed" / bar.name
        archived.parent.mkdir(parents=True, exist_ok=True)
        if archived.exists() and archived.read_bytes() != bar.read_bytes():
            raise ValueError("processed handoff conflicts with fresh handoff")
        if bar.exists():
            bar.replace(archived)
        write_json(report, {"status": "processed", "observed_at": observed_at, "bar": str(archived), "runner": detail})
        return 0
    except (OSError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as error:
        write_json(report, {"status": "blocked", "observed_at": observed_at, "bar": str(bar), "reason": str(error)})
        return 2


def consume(bar: Path, *, report: Path, runner_args: list[str]) -> int:
    lock = report.with_suffix(report.suffix + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return 2
    try:
        return _consume(bar, report=report, runner_args=runner_args)
    finally:
        os.close(descriptor)
        lock.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bar", type=Path, required=True, help="collector's atomically written completed-bar handoff")
    parser.add_argument("--report", type=Path, default=Path("output/paper-operation/latest.json"))
    parser.add_argument("--state-db", default="output/intraday-forward.db")
    parser.add_argument("--calendar-db", default="output/finance-automation.db")
    parser.add_argument("--run-id", required=True, help="session-specific frozen paper-run identity")
    parser.add_argument("--assumptions", default="config/intraday-paper-assumptions.json")
    parser.add_argument("--review-pilot-db")
    parser.add_argument("--policy-db", help="pilot database containing an explicitly selected frozen policy")
    parser.add_argument("--policy-version", help="candidate or active policy version to use unchanged")
    args = parser.parse_args(argv)
    if bool(args.policy_db) != bool(args.policy_version):
        parser.error("--policy-db and --policy-version must be supplied together")
    runner_args = ["--state-db", args.state_db, "--calendar-db", args.calendar_db, "--run-id", args.run_id, "--assumptions", args.assumptions]
    if args.review_pilot_db:
        runner_args += ["--review-pilot-db", args.review_pilot_db]
    if args.policy_db:
        runner_args += ["--policy-db", args.policy_db, "--policy-version", args.policy_version]
    return consume(args.bar, report=args.report, runner_args=runner_args)


if __name__ == "__main__":
    raise SystemExit(main())
