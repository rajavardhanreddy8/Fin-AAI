"""Refresh Momentum's broad discovery price snapshots from official NSE bhavcopies.

This is a discovery-data refresh only. It never changes financial evidence,
research status, governance flags, or a company into an investable candidate.
Names absent from an EQ bhavcopy remain explicitly without a refreshed price.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path
from urllib.error import HTTPError

from stock_research.collectors.base import CollectorError
from stock_research.collectors.nse_eod import NSEBhavcopyCollector


def recent_prices(as_of: date, isins: set[str], sessions: int) -> tuple[list, set[str]]:
    collector = NSEBhavcopyCollector()
    rows = []
    cursor = as_of
    floor = as_of - timedelta(days=12)
    dates_seen: set[date] = set()
    while cursor >= floor and len(dates_seen) < sessions:
        if cursor.weekday() < 5:
            try:
                batch = collector.collect(cursor, isins, require_all=False)
            except HTTPError as exc:
                if exc.code != 404:
                    raise
            else:
                if batch:
                    rows.extend(batch)
                    dates_seen.add(cursor)
        cursor -= timedelta(days=1)
    if not rows:
        raise CollectorError("No official NSE bhavcopy was available in the refresh window")
    found = {row.isin for row in rows}
    return rows, isins - found


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", default="momentum-site/lib/finance-seed.json")
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--sessions", type=int, default=4)
    args = parser.parse_args()
    if args.sessions < 1:
        raise SystemExit("--sessions must be positive")
    seed_path = Path(args.seed)
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    companies = seed.get("companies", [])
    isins = {str(company["isin"]).strip().upper() for company in companies if company.get("isin")}
    rows, missing = recent_prices(args.as_of, isins, args.sessions)
    latest: dict[str, object] = {}
    for row in rows:
        prior = latest.get(row.isin)
        if prior is None or row.trade_date > prior.trade_date:
            latest[row.isin] = row
    updated = 0
    for company in companies:
        row = latest.get(str(company.get("isin", "")).upper())
        if row is None:
            continue
        company["price"] = {
            "close": row.close,
            "volume": row.volume,
            "trade_date": row.trade_date.isoformat(),
            "source_id": row.source_id,
            "source_location": row.source_location,
            "retrieved_at": row.retrieved_at,
        }
        updated += 1
    seed["exportedAt"] = max(row.retrieved_at for row in rows)
    seed["source"] = "Official NSE CM-UDiFF EOD refresh for discovery prices and volumes; accepted filings and financial facts separately control evidence-ready research."
    seed_path.write_text(json.dumps(seed, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({"updated": updated, "missing_from_eq_bhavcopy": sorted(missing), "latest_session": max(row.trade_date for row in rows).isoformat()}, indent=2))


if __name__ == "__main__":
    main()
