"""Offline inspection and optional live Upstox market-data ingestion."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from stock_research.collectors.upstox import UpstoxClient, UpstoxError, normalize_candles, normalize_news
from stock_research.collectors.market_events import FeedError, fetch_feed, normalize_feed
from stock_research.collectors.firecrawl import FirecrawlError, extract as firecrawl_extract, load_registry as load_firecrawl_registry, normalize_articles, validate_url as validate_firecrawl_url
from stock_research.collectors.upstox import digest


def _save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _archive_raw(output_dir, snapshots):
    for snapshot in snapshots:
        raw_hash = snapshot.get("raw_hash")
        if raw_hash != digest({key: value for key, value in snapshot.items() if key != "raw_hash"}):
            raise ValueError("refusing to archive a snapshot with an invalid raw hash")
        source_dir = hashlib.sha256(snapshot["source_id"].encode("utf-8")).hexdigest()[:16]
        path = output_dir / "raw" / source_dir / f"{raw_hash}.json"
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing != snapshot:
                raise ValueError("immutable raw snapshot path already contains different data")
        else:
            _save(path, snapshot)


def _coverage(snapshots, gaps, start, end):
    integrity, duplicates, revisions = [], 0, 0
    for snapshot in snapshots:
        valid = snapshot.get("raw_hash") == digest({key: value for key, value in snapshot.items() if key != "raw_hash"})
        integrity.append({"source_id": snapshot.get("source_id"), "dataset": snapshot.get("dataset"), "raw_hash": snapshot.get("raw_hash"), "valid": valid})
    seen = set()
    valid_snapshots = [s for s in snapshots if s.get("raw_hash") == digest({key: value for key, value in s.items() if key != "raw_hash"})]
    for event in (normalize_news([s for s in valid_snapshots if s.get("dataset") == "news"])
                  + normalize_feed([s for s in valid_snapshots if s.get("dataset") == "rss_atom"])
                  + normalize_articles([s for s in valid_snapshots if s.get("dataset") == "firecrawl_article"])):
        key = (event["canonical_id"], event["revision_id"])
        duplicates += key in seen
        seen.add(key)
        revisions += event.get("revision_of") is not None
    raw_hashes = [snapshot.get("raw_hash") for snapshot in snapshots]
    duplicates += len(raw_hashes) - len(set(raw_hashes))
    expected = []
    if start and end:
        expected = [(start + timedelta(days=n)).isoformat() for n in range((end-start).days + 1) if (start + timedelta(days=n)).weekday() < 5]
    candle_dates = {row["at"][:10] for s in valid_snapshots if s.get("dataset") == "candles" for row in normalize_candles(s)}
    return {"retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "freshness_seconds": {s.get("source_id"): max(0, int((datetime.now(timezone.utc)-datetime.fromisoformat(s["observed_at"].replace("Z", "+00:00"))).total_seconds())) for s in snapshots},
            "expected_weekdays": expected, "missing_sessions": sorted(set(expected)-candle_dates) if expected else [],
            "session_calendar": "weekdays only; exchange holidays and special sessions are not excluded",
            "gaps": gaps,
            "duplicates": duplicates, "revisions": revisions, "raw_integrity": integrity,
            "integrity_failures": sum(not row["valid"] for row in integrity)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, help="offline JSON list containing provider snapshots")
    parser.add_argument("--feed-registry", type=Path, help="JSON list of explicitly permitted RSS/Atom sources")
    parser.add_argument("--instrument-key", action="append", default=[])
    parser.add_argument("--from-date", type=date.fromisoformat)
    parser.add_argument("--to-date", type=date.fromisoformat)
    parser.add_argument("--output", type=Path, default=Path("market-ingest"))
    parser.add_argument("--dry-run", action="store_true", help="inspect and hash fixture without writing")
    parser.add_argument("--max-sources", type=int, default=100, help="maximum feed sources per run")
    parser.add_argument("--refresh", action="store_true", help="refetch units already marked complete in the local checkpoint")
    parser.add_argument("--firecrawl-registry", type=Path, help="JSON list of publishers and exact permitted article URLs")
    parser.add_argument("--firecrawl-url", action="append", default=[], help="exact allowed public article URL (maximum 5)")
    parser.add_argument("--firecrawl-live", action="store_true", help="explicitly call Firecrawl; otherwise only validate a dry-run plan")
    parser.add_argument("--firecrawl-readiness", type=Path, help="fresh free-plan/credits/auto-top-up evidence required for live extraction")
    args = parser.parse_args(argv)
    if args.max_sources < 1:
        parser.error("--max-sources must be positive")
    if len(args.instrument_key) > args.max_sources:
        parser.error("instrument keys exceed --max-sources limit")
    if len(args.firecrawl_url) > 5:
        parser.error("Firecrawl is limited to five pages per invocation")
    if bool(args.firecrawl_url) != bool(args.firecrawl_registry):
        parser.error("--firecrawl-url and --firecrawl-registry must be provided together")
    if args.firecrawl_live and not args.firecrawl_url:
        parser.error("--firecrawl-live requires at least one --firecrawl-url")
    if args.dry_run and args.firecrawl_live:
        parser.error("--dry-run cannot be combined with live Firecrawl extraction")
    if args.firecrawl_readiness and not args.firecrawl_live:
        parser.error("--firecrawl-readiness applies only with --firecrawl-live")
    if args.fixture and args.firecrawl_live:
        parser.error("--fixture cannot be combined with live Firecrawl extraction")
    try:
        if args.firecrawl_url and not args.firecrawl_live and not args.fixture and not args.instrument_key and not args.feed_registry:
            sources = load_firecrawl_registry(args.firecrawl_registry)
            allowed = {url for source in sources for url in source["allowed_urls"]}
            if any(url not in allowed for url in args.firecrawl_url):
                raise FirecrawlError("every Firecrawl URL must exactly match a permitted registry URL")
            for url in args.firecrawl_url:
                validate_firecrawl_url(url, next(source for source in sources if url in source["allowed_urls"]), check_dns=False)
            print(json.dumps({"status": "dry_run", "provider_call": False, "selected_urls": args.firecrawl_url,
                              "page_limit": 5, "provider_attempt_limit": 0, "dns_resolution": "not checked"}, sort_keys=True))
            return 0
        if args.fixture:
            snapshots = json.loads(args.fixture.read_text(encoding="utf-8"))
        else:
            if not args.instrument_key and not args.feed_registry and not args.firecrawl_url:
                parser.error("live collection requires --instrument-key")
            if (args.from_date or args.to_date) and not args.instrument_key:
                parser.error("historical candles require --instrument-key")
            client = UpstoxClient() if args.instrument_key else None
            snapshots = []
            if args.from_date or args.to_date:
                if not args.from_date or not args.to_date:
                    parser.error("both --from-date and --to-date are required for candles")
            else:
                snapshots = []
        gaps = []
        if not args.fixture:
            checkpoint_path = args.output / "checkpoint.json"
            request = {"keys": args.instrument_key, "from": str(args.from_date), "to": str(args.to_date),
                       "feeds": digest(args.feed_registry.read_bytes()) if args.feed_registry else None}
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8")) if checkpoint_path.exists() else {"request": request, "snapshots": [], "completed": []}
            if checkpoint.get("request") != request:
                checkpoint["request"] = checkpoint.get("request") if args.firecrawl_registry else request
                checkpoint["completed"] = [unit for unit in checkpoint.get("completed", []) if unit.startswith("firecrawl:")]
                checkpoint["gaps"] = [gap for gap in checkpoint.get("gaps", []) if str(gap.get("unit", "")).startswith("firecrawl:")]
            gaps = checkpoint.get("gaps", [])
            snapshots = checkpoint["snapshots"]
            units = ([f"candle:{key}" for key in args.instrument_key] if args.from_date else []) + [f"news:{key}" for key in args.instrument_key]
            for unit in units:
                if unit in checkpoint["completed"]: continue
                try:
                    dataset, key = unit.split(":", 1)
                    snapshots.extend([client.candles(key, args.from_date, args.to_date)] if dataset == "candle" else client.news([key]))
                    checkpoint["completed"].append(unit)
                except (UpstoxError, ValueError) as error:
                    gaps = [gap for gap in gaps if gap["unit"] != unit] + [{"unit": unit, "reason": str(error)}]
                else:
                    gaps = [gap for gap in gaps if gap["unit"] != unit]
                checkpoint["snapshots"] = snapshots
                checkpoint["gaps"] = gaps
                _save(checkpoint_path, checkpoint)
        firecrawl_sources, firecrawl_plan = [], None
        if args.firecrawl_registry:
            firecrawl_sources = load_firecrawl_registry(args.firecrawl_registry)
            allowed = {url for source in firecrawl_sources for url in source["allowed_urls"]}
            if any(url not in allowed for url in args.firecrawl_url):
                raise FirecrawlError("every Firecrawl URL must exactly match a permitted registry URL")
            for url in args.firecrawl_url:
                validate_firecrawl_url(url, next(source for source in firecrawl_sources if url in source["allowed_urls"]))
            if args.firecrawl_live:
                if not args.firecrawl_readiness:
                    raise FirecrawlError("live extraction requires --firecrawl-readiness proving free credits and auto top-up disabled")
                try:
                    readiness = json.loads(args.firecrawl_readiness.read_text(encoding="utf-8"))
                    if not isinstance(readiness, dict) or not isinstance(readiness.get("checked_at"), str):
                        raise ValueError
                    checked = datetime.fromisoformat(readiness["checked_at"].replace("Z", "+00:00"))
                    if checked.tzinfo is None or checked.utcoffset() is None:
                        raise ValueError
                except (ValueError, TypeError, OSError):
                    raise FirecrawlError("Firecrawl readiness record is malformed or lacks a timezone") from None
                age = (datetime.now(timezone.utc) - checked.astimezone(timezone.utc)).total_seconds()
                required_credits = len(args.firecrawl_url) * 3
                if (readiness.get("plan") != "free" or readiness.get("paid_top_up_enabled") is not False
                        or type(readiness.get("remaining_credits")) is not int or readiness["remaining_credits"] < required_credits
                        or age < 0 or age > 24 * 60 * 60):
                    raise FirecrawlError("Firecrawl readiness must be under 24 hours old, free plan, enough credits for all retries, and paid top-up disabled")
                completed_units = checkpoint.setdefault("completed", [])
                for url in args.firecrawl_url:
                    unit = "firecrawl:" + url
                    if unit in completed_units and not args.refresh:
                        continue
                    fresh, failures = firecrawl_extract([url], firecrawl_sources)
                    snapshots.extend(item for item in fresh if item.get("raw_hash") not in {prior.get("raw_hash") for prior in snapshots})
                    gaps = [gap for gap in gaps if gap.get("unit") != unit]
                    gaps.extend({**failure, "unit": unit} for failure in failures)
                    if fresh:
                        if unit not in completed_units: completed_units.append(unit)
                        gaps = [gap for gap in gaps if gap.get("unit") != unit]
                    checkpoint["snapshots"] = snapshots
                    checkpoint["gaps"] = gaps
                    _save(checkpoint_path, checkpoint)
                firecrawl_plan = {"mode": "live", "selected_pages": len(args.firecrawl_url), "provider_attempt_limit": len(args.firecrawl_url) * 3}
            else:
                firecrawl_plan = {"mode": "dry-run", "selected_pages": len(args.firecrawl_url), "provider_attempt_limit": 0}
        if args.feed_registry:
            sources = json.loads(args.feed_registry.read_text(encoding="utf-8"))
            if not isinstance(sources, list):
                raise FeedError("feed registry must be a JSON list")
            if len(sources) > args.max_sources:
                raise FeedError(f"feed registry exceeds --max-sources limit ({args.max_sources})")
            if not args.fixture:
                done = checkpoint.setdefault("completed", [])
                for source in sources:
                    unit = "feed:" + source["source_id"]
                    if unit in done and not args.refresh: continue
                    try:
                        fresh_snapshot = fetch_feed(source)
                        if not any(item.get("raw_hash") == fresh_snapshot.get("raw_hash") for item in snapshots):
                            snapshots.append(fresh_snapshot)
                        if unit not in done: done.append(unit)
                    except (FeedError, OSError) as error: gaps = [gap for gap in gaps if gap["unit"] != unit] + [{"unit": unit, "reason": str(error)}]
                    else: gaps = [gap for gap in gaps if gap["unit"] != unit]
                    checkpoint["gaps"] = gaps
                    checkpoint["snapshots"] = snapshots
                    _save(checkpoint_path, checkpoint)
            else:
                snapshots.extend(fetch_feed(source) for source in sources[:args.max_sources])
        valid_snapshots = [item for item in snapshots if item.get("raw_hash") == digest({key: value for key, value in item.items() if key != "raw_hash"})]
        events = normalize_news([item for item in valid_snapshots if item.get("dataset") == "news"])
        events.extend(normalize_feed([item for item in valid_snapshots if item.get("dataset") == "rss_atom"]))
        events.extend(normalize_articles([item for item in valid_snapshots if item.get("dataset") == "firecrawl_article"], prior_events=events))
        bars = [bar for item in valid_snapshots if item.get("dataset") == "candles" for bar in normalize_candles(item)]
        if not args.fixture:
            checkpoint["snapshots"] = snapshots
            checkpoint["gaps"] = gaps
            _save(checkpoint_path, checkpoint)
        coverage = _coverage(snapshots, gaps, args.from_date, args.to_date)
        if firecrawl_plan:
            coverage["firecrawl"] = firecrawl_plan
        if coverage["integrity_failures"] or (gaps and not snapshots):
            status = "failed"
        elif gaps or coverage["missing_sessions"]:
            status = "partial"
        else:
            status = "complete"
        output = {"status": status, "snapshots": snapshots, "bars": bars, "events": events,
                  "counts": {"snapshots": len(snapshots), "bars": len(bars), "news_events": len(events)}, "coverage": coverage}
        if not args.dry_run:
            args.output.mkdir(parents=True, exist_ok=True)
            _archive_raw(args.output, valid_snapshots)
            _save(args.output / "events.json", events)
            path = args.output / "market-ingest.json"
            _save(path, output)
            print(f"Wrote {path} ({len(snapshots)} snapshots, {len(events)} events)")
        else:
            print(json.dumps({"status": status, **output["counts"]}, sort_keys=True))
        if not args.dry_run:
            print(f"Collection status: {status} (gaps={len(coverage['gaps'])}, integrity_failures={coverage['integrity_failures']})")
        return 0 if status == "complete" else 2
    except (OSError, ValueError, UpstoxError, FeedError, FirecrawlError) as error:
        print(f"Market ingestion failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
