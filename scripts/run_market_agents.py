"""Optionally annotate ingested market events through the budgeted Nova wrapper."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stock_research.market_context_agents import annotate_events, build_market_context_annotator  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="market-ingest JSON or an object with events")
    parser.add_argument("--live", action="store_true", help="invoke Nova through the validated spend ledger")
    parser.add_argument("--budget-config", type=Path)
    parser.add_argument("--usage-db", type=Path, default=Path("market-agents-usage.sqlite"))
    parser.add_argument("--namespace", default="market-context-v1")
    parser.add_argument("--profile", help="optional AWS CLI profile; Region stays ap-southeast-2")
    parser.add_argument("--output", type=Path, help="write annotation JSON here; default prints JSON")
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        events = payload if isinstance(payload, list) else payload["events"]
        if not isinstance(events, list):
            raise ValueError("input must contain an events list")
        if args.live:
            if not args.budget_config:
                raise ValueError("--live requires --budget-config with current Nova price and billing evidence")
            annotator = build_market_context_annotator(args.budget_config, args.usage_db, args.namespace, profile=args.profile)
            result = {"status": "complete", **annotate_events(events, annotator)}
        else:
            result = {"status": "dry_run", "events": len(events), "message": "No model call was made; pass --live with current budget evidence to annotate."}
        output = json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        if args.output:
            args.output.write_text(output, encoding="utf-8")
        else:
            print(output, end="")
        return 0
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"Market annotation failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
