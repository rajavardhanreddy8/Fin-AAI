"""Import and query time-locked, source-linked market relationship evidence."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from stock_research.context_store import ContextError, ContextStore


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("import", "report", "status"))
    parser.add_argument("input", nargs="?", type=Path, help="JSON file for import")
    parser.add_argument("--db", type=Path, default=Path("output/market-relationships.db"))
    parser.add_argument("--asof", help="timezone-aware ISO cutoff for report")
    parser.add_argument("--start", help="graph start node as type/id")
    parser.add_argument("--max-hops", type=int, default=3)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args(argv)
    store = ContextStore(args.db)
    try:
        if args.operation == "import":
            if args.input is None:
                parser.error("import requires an input JSON file")
            result = store.import_batch(json.loads(args.input.read_text(encoding="utf-8")))
        elif args.operation == "report":
            if args.asof is None:
                parser.error("report requires --asof")
            result = store.report(args.asof, start=args.start, max_hops=args.max_hops, limit=args.limit)
        else:
            result = store.status()
        print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
        return 0
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ContextError, sqlite3.Error, ValueError, TypeError) as error:
        print(f"Market relationship {args.operation} failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
