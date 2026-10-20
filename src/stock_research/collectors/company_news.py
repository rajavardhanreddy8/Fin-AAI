"""Company-scoped orchestration for approved feeds, Firecrawl, and supplied Upstox snapshots."""
from __future__ import annotations

import re
from datetime import date, datetime

from .firecrawl import extract, normalize_articles
from .market_events import fetch_feed, normalize_feed
from .upstox import digest, normalize_news


def collect_company_news(company_name, exchange_symbol, aliases, start, end, *, feed_sources=(),
                         firecrawl_urls=(), firecrawl_sources=(), upstox_snapshots=(), prior_events=(),
                         feed_fetch=fetch_feed, article_extract=extract, clock=None):
    """Collect from caller-selected approved sources; providers are invoked only when URLs/sources supplied."""
    if not isinstance(company_name, str) or not company_name.strip() or not isinstance(exchange_symbol, str) or not exchange_symbol.strip():
        raise ValueError("company name and exchange symbol are required")
    start, end = date.fromisoformat(str(start)), date.fromisoformat(str(end))
    if start > end:
        raise ValueError("start date must not follow end date")
    names = {company_name.strip().casefold(), exchange_symbol.strip().casefold()}
    names.update(value.strip().casefold() for value in aliases if isinstance(value, str) and value.strip())
    snapshots, gaps = [], []
    for source in feed_sources:
        if source.get("permitted") is not True:
            gaps.append({"unit": "feed:" + str(source.get("source_id", "unknown")), "reason": "feed source must be explicitly permitted"})
            continue
        try:
            snapshots.append(feed_fetch(source, **({"clock": clock} if clock else {})))
        except (ValueError, OSError) as error:
            gaps.append({"unit": "feed:" + str(source.get("source_id", "unknown")), "reason": str(error)})
    if firecrawl_urls:
        fresh, failures = article_extract(firecrawl_urls, firecrawl_sources, **({"clock": clock} if clock else {}))
        snapshots.extend(fresh)
        gaps.extend(failures)
    elif prior_events and article_extract is not extract:
        # Injected/offline collectors can replay prior inputs for deterministic dedupe.
        fresh, failures = article_extract([], firecrawl_sources, **({"clock": clock} if clock else {}))
        snapshots.extend(fresh)
        gaps.extend(failures)
    snapshots.extend(upstox_snapshots)
    valid = [item for item in snapshots if item.get("raw_hash") == digest({key: value for key, value in item.items() if key != "raw_hash"})]
    events = normalize_feed([item for item in valid if item.get("dataset") == "rss_atom"])
    events.extend(normalize_articles([item for item in valid if item.get("dataset") == "firecrawl_article"]))
    events.extend(normalize_news([item for item in upstox_snapshots if item.get("dataset") == "news"]))
    seen = {(item.get("canonical_id"), item.get("revision_id")): item for item in prior_events}
    selected, duplicates = [], []
    for event in events:
        published = event.get("published_at")
        timestamp = datetime.fromisoformat(published.replace("Z", "+00:00")).date() if published else date.fromisoformat(event["observed_at"][:10])
        text = " ".join((event.get("title", ""), event.get("summary", ""), event.get("source_url", ""))).casefold()
        if start <= timestamp <= end and any(re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text) for name in names):
            key = (event.get("canonical_id"), event.get("revision_id"))
            if key in seen:
                duplicates.append({"event_id": event["event_id"], "duplicate_of": seen[key].get("event_id")})
            else:
                selected.append(event)
                seen[key] = event
    return {"company": company_name, "exchange_symbol": exchange_symbol, "aliases": sorted(names),
            "date_range": {"start": start.isoformat(), "end": end.isoformat()},
            "snapshots": snapshots, "events": selected, "duplicates": duplicates, "gaps": gaps}
