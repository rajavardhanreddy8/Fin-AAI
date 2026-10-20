"""Offline-composable orchestration for company news evidence."""
from __future__ import annotations

from stock_research.collectors.company_news import collect_company_news
from stock_research.parsing_storage_agent import parse_and_store
from stock_research.relationship_agent import import_relationship_proposals


def run_company_pipeline(*, company, symbol, aliases, start, end, store, interpret,
                         news_options=None, relationship_batch=None, import_relationships=False):
    news = collect_company_news(company, symbol, aliases, start, end, **(news_options or {}))
    documents, gaps = [], list(news["gaps"])
    for event in news["events"]:
        summary = event.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            gaps.append({"unit": "event:" + event.get("event_id", "unknown"),
                         "reason": "summary unavailable; event was not sent for parsing"})
            continue
        documents.append({"source_id": event["source_id"], "source_url": event["source_url"],
                          "published_at": event.get("published_at"), "observed_at": event["observed_at"],
                          "raw_hash": event.get("provider_response_hash", event["raw_hash"]), "text": summary})
    parsed = parse_and_store(store, company=company, symbol=symbol, aliases=aliases,
        start=f"{start}T00:00:00Z" if len(str(start)) == 10 else start,
        end=f"{end}T23:59:59.999999Z" if len(str(end)) == 10 else end,
        documents=documents, interpret=interpret)
    relationships = None
    if relationship_batch is not None:
        if import_relationships:
            relationships = import_relationship_proposals(store, relationship_batch, {symbol.casefold()})
        else:
            relationships = relationship_batch
    return {"news": news, "documents": documents, "parsed": parsed,
            "relationships": relationships, "gaps": gaps}
