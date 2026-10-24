"""Review historical source reliability and produce a paper-only event response."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from stock_research.context_store import ContextStore
from stock_research.source_reliability import response_policy, save_adjudications, source_reliability


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    adjudicate = commands.add_parser("adjudicate", help="append reviewed source verdicts")
    adjudicate.add_argument("input", type=Path, help="JSON list of cited adjudication records")
    adjudicate.add_argument("--db", type=Path, required=True)
    adjudicate.add_argument("--asof", required=True)
    adjudicate.add_argument("--output", type=Path, required=True)
    review = commands.add_parser("review-event", help="append reviewed event authentication/origin evidence")
    review.add_argument("input", type=Path, help="JSON list of event review records")
    review.add_argument("--db", type=Path, required=True)
    review.add_argument("--asof", required=True)
    review.add_argument("--output", type=Path, required=True)
    for name in ("score", "respond"):
        command = commands.add_parser(name)
        command.add_argument("--db", type=Path, required=True)
        command.add_argument("--asof", required=True)
        command.add_argument("--output", type=Path, required=True)
        command.add_argument("--company-id", required=True)
        command.add_argument("--category", required=True)
        command.add_argument("--source-id" if name == "score" else "--event-id", required=True)
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise ValueError("output exists; select a new version artifact")
        if not args.db.is_file():
            raise ValueError("database must be an existing ContextStore database")
        # Reject malformed as-of values before any database mutation.
        cutoff = datetime.fromisoformat(args.asof.replace("Z", "+00:00"))
        if cutoff.tzinfo is None or cutoff.utcoffset() is None:
            raise ValueError("asof must include a timezone")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        store = ContextStore(args.db)
        if args.command == "adjudicate":
            records = _read(args.input)
            if not isinstance(records, list):
                raise ValueError("adjudication input must be a JSON list")
            result = {"status": "research_only", "added": save_adjudications(store, records, asof=args.asof)}
        elif args.command == "review-event":
            from stock_research.source_reliability import save_event_reviews
            records = _read(args.input)
            if not isinstance(records, list):
                raise ValueError("event review input must be a JSON list")
            result = {"status": "research_only", "added": save_event_reviews(store, records, asof=args.asof)}
        elif args.command == "score":
            result = source_reliability(store, source_id=args.source_id, company_id=args.company_id,
                                        category=args.category, asof=args.asof)
        else:
            result = response_policy(store, event_id=args.event_id, company_id=args.company_id,
                                     category=args.category, asof=args.asof)
        encoded = json.dumps(result, sort_keys=True, indent=2, allow_nan=False)
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(encoded + "\n")
        print(json.dumps({"status": "research_only", "path": str(args.output)}))
        return 0
    except (OSError, sqlite3.Error, KeyError, TypeError, ValueError) as error:
        print(f"Source response failed ({type(error).__name__}). Check the input, database, and output path.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
