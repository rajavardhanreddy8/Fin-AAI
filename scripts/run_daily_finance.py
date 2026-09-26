"""Run a bounded pre-market or post-market fin-AAI cycle on the local PC."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stock_research.daily_automation import DEFAULT_DB, run_phase  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("pre", "post"), required=True)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--max-model-calls", type=int, default=4)
    parser.add_argument("--skip-trading-evaluation", action="store_true")
    args = parser.parse_args()
    report = run_phase(args.phase, db=args.db, max_model_calls=args.max_model_calls,
                       evaluate_trading=not args.skip_trading_evaluation)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 2 if report["status"] in ("failed", "partial") else 0


if __name__ == "__main__":
    raise SystemExit(main())
