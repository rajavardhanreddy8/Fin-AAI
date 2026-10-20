"""Deterministic validation and append-only storage for cited company events."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Callable, Iterable

from stock_research.context_store import ContextStore


def _date(value: str, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a timezone-aware ISO date or timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"{name} must be a timezone-aware ISO date or timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return parsed.astimezone(timezone.utc)


def parse_documents(*, company: str, symbol: str, aliases: Iterable[str], start: str, end: str,
                    documents: Iterable[dict], interpret: Callable[[dict], list[dict]]) -> dict:
    """Interpret bounded document records; only verbatim cited proposals become reported claims."""
    company = company.strip() if isinstance(company, str) else ""
    symbol = symbol.strip() if isinstance(symbol, str) else ""
    if not company or not symbol:
        raise ValueError("company and symbol are required")
    lower, upper = _date(start, "start"), _date(end, "end")
    if lower > upper:
        raise ValueError("start must not follow end")
    names = {company.casefold(), symbol.casefold(), *(a.casefold() for a in aliases if isinstance(a, str) and a.strip())}
    events, claims, seen, company_node = [], [], set(), None
    for doc in documents:
        if not isinstance(doc, dict) or not isinstance(doc.get("text"), str) or len(doc["text"].encode()) > 65536:
            raise ValueError("each document must contain at most 65536 bytes of text")
        url, source_id = doc.get("source_url"), doc.get("source_id")
        if not isinstance(url, str) or not url.startswith(("https://", "http://")) or not isinstance(source_id, str) or not source_id:
            raise ValueError("document source_id and HTTP(S) source_url are required")
        observed = _date(doc.get("observed_at"), "observed_at")
        published = _date(doc["published_at"], "published_at") if doc.get("published_at") else observed
        if not lower <= published <= upper:
            continue
        proposals = interpret({"source_id": source_id, "source_url": url, "published_at": published.isoformat(),
                               "text": doc["text"][:65536], "company_names": sorted(names)})
        if not isinstance(proposals, list) or len(proposals) > 20:
            raise ValueError("interpretation must return at most 20 proposals")
        raw_hash = hashlib.sha256(doc["text"].encode()).hexdigest()
        supplied_hash = doc.get("raw_hash")
        if supplied_hash is not None:
            if not isinstance(supplied_hash, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", supplied_hash):
                raise ValueError("raw_hash must be a SHA-256 hex digest")
            raw_hash = supplied_hash.lower()
        source = {"source_id": source_id, "source_url": url, "raw_hash": raw_hash,
                  "known_at": observed.isoformat().replace("+00:00", "Z")}
        if company_node is None:
            company_node = {"node_type": "company", "node_id": symbol.casefold(), "canonical_id": symbol,
                "known_at": source["known_at"], "effective_from": published.isoformat().replace("+00:00", "Z"),
                "source": source}
        for proposal in proposals:
            if not isinstance(proposal, dict):
                raise ValueError("proposal must be an object")
            title, quote = proposal.get("title"), proposal.get("citation")
            if not isinstance(title, str) or not title.strip() or not isinstance(quote, str) or len(quote) < 8 or quote not in doc["text"]:
                continue
            if not any(name in (title + " " + quote).casefold() for name in names):
                continue
            key = re.sub(r"\W+", " ", title.casefold()).strip()
            canonical_id = hashlib.sha256(f"{key}|{published.date()}".encode()).hexdigest()
            event_id = hashlib.sha256(f"{canonical_id}|{source_id}|{raw_hash}".encode()).hexdigest()
            if event_id not in seen:
                events.append({"event_id": event_id, "canonical_id": canonical_id, "source_id": source_id,
                    "source_url": url, "published_at": published.isoformat().replace("+00:00", "Z"),
                    "observed_at": source["known_at"], "available_at": source["known_at"],
                    "raw_hash": raw_hash, "verification_status": "publisher_reported_unverified",
                    "title": title.strip(), "summary": quote, "entities": [company, symbol]})
                seen.add(event_id)
            claims.append({"claim_id": hashlib.sha256(f"{event_id}|{raw_hash}|{quote}".encode()).hexdigest(),
                "event_id": event_id, "claim_type": "reported_claim", "text": quote,
                "known_at": source["known_at"], "evidence_refs": [{**source, "source_event_id": event_id}],
                "source_authority": "publisher_reported", "corroboration_status": "unknown",
                "truth_status": "unknown", "confidence": None})
    return {"events": events, "nodes": [company_node] if company_node else [], "claims": claims,
            "relationships": [], "analogs": []}


def parse_and_store(store: ContextStore, **inputs) -> dict:
    batch = parse_documents(**inputs)
    return {"batch": batch, "added": store.import_batch(batch)}
