"""Assemble a retrospective, provenance-preserving POWERGRID news archive offline."""
from __future__ import annotations

import argparse
import calendar
import csv
import hashlib
import html
import json
import math
import re
import sys
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from stock_research.context_store import ContextStore
from stock_research.source_reliability import source_reliability

IST = ZoneInfo("Asia/Kolkata")
START = date(2023, 10, 25)
END = date(2026, 10, 25)
ALIASES = ("POWERGRID", "PGCIL", "Power Grid Corporation", "Power Grid Corporation of India Limited")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _capture_normalized(value: str) -> str:
    value = unicodedata.normalize("NFKC", html.unescape(value)).casefold()
    return re.sub(r"\s+", " ", value).strip()


def _time(value, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a timezone-aware ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"{field} must be a timezone-aware ISO timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware ISO timestamp")
    return parsed.astimezone(timezone.utc)


def _stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _canonical_url(value: str) -> str:
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError("source_url is missing or malformed")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("source_url must be public HTTPS without credentials or fragment")
    host = parsed.hostname.lower().rstrip(".")
    port = parsed.port
    netloc = host if port in (None, 443) else f"{host}:{port}"
    return urlunsplit(("https", netloc, parsed.path.rstrip("/") or "/", parsed.query, ""))


def _mentions_company(title: str, snippet: str) -> bool:
    text = f"{title}\n{snippet}".casefold()
    return any(re.search(r"(?<!\w)" + re.escape(alias.casefold()) + r"(?!\w)", text) for alias in ALIASES)


def _months() -> list[tuple[str, date, date]]:
    rows = []
    year, month = START.year, START.month
    while (year, month) <= (END.year, END.month):
        first = date(year, month, 1)
        last = date(year, month, calendar.monthrange(year, month)[1])
        rows.append((f"{year:04d}-{month:02d}", max(START, first), min(END, last)))
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return rows


def _catalog_events(catalog: dict, *, built_at: datetime) -> tuple[list[dict], dict]:
    catalog_schema = catalog.get("schema_version")
    if catalog_schema not in {"powergrid-news-catalog-v1", *(f"powergrid-verified-news-catalog-v{i}" for i in range(1, 5))}:
        raise ValueError("unsupported Powergrid news catalog schema")
    window = catalog.get("requested_window")
    if not isinstance(window, dict) or window.get("start") != START.isoformat() or window.get("end") != END.isoformat() or window.get("timezone") != "Asia/Kolkata":
        raise ValueError("news catalog must cover 2023-10-25 through 2026-10-25 Asia/Kolkata")
    retrieved = _time(catalog.get("retrieved_at_utc") or catalog.get("catalogued_at_utc") or catalog.get("observed_at_utc"), "catalogued_at_utc")
    if retrieved > built_at:
        raise ValueError("catalog retrieval time is in the future")
    records = catalog.get("records")
    if not isinstance(records, list):
        raise ValueError("news catalog records must be a list")
    accepted, rejected, out_of_range, undated = [], 0, 0, 0
    unverified_date = not_company = 0
    seen_pairs, url_revisions, hash_canonicals = set(), {}, {}
    duplicate_url = duplicate_content = 0
    source_catalog, candidate_sources, inventory = {}, set(), []
    for index, record in enumerate(records):
        entry = {"record_index": index, "record": record, "decision": "rejected"}
        inventory.append(entry)
        if not isinstance(record, dict):
            rejected += 1
            continue
        try:
            source_id = record.get("source_id")
            source_url = record.get("source_url")
            title = record.get("title")
            snippet = record.get("snippet")
            body_excerpt = record.get("body_excerpt")
            if not all(isinstance(v, str) and v.strip() for v in (source_id, source_url, title)):
                raise ValueError
            if snippet is None:
                snippet = body_excerpt if isinstance(body_excerpt, str) else ""
            if not isinstance(snippet, str):
                raise ValueError
            canonical_url = _canonical_url(source_url)
            observed = _time(record.get("observed_at_utc") or record.get("retrieved_at_utc"), f"records[{index}].observed_at_utc")
            fetched_raw = record.get("retrieved_at_utc")
            fetched = _time(fetched_raw, f"records[{index}].retrieved_at_utc") if fetched_raw else observed
            if observed != fetched or observed > built_at:
                raise ValueError
            evidence_known_raw = record.get("publication_evidence_known_at_utc")
            evidence_known = _time(evidence_known_raw, f"records[{index}].publication_evidence_known_at_utc") if evidence_known_raw else observed
            if evidence_known > built_at:
                raise ValueError
            content_hash = record.get("content_sha256") or record.get("capture_sha256")
            if catalog_schema == "powergrid-news-catalog-v1":
                expected_hash = _sha((title + "\n" + snippet).encode("utf-8"))
                if content_hash != expected_hash:
                    raise ValueError
            elif not isinstance(content_hash, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", content_hash):
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            rejected += 1
            continue
        if catalog_schema == "powergrid-news-catalog-v1":
            candidate_sources.add(source_id)
            undated += int(not record.get("published_at"))
            unverified_date += int(bool(record.get("published_at") or record.get("publication_date_candidates")))
            entry["decision"] = "search_metadata_only_not_admitted_as_publisher_event"
            continue
        identity_confirmed = (catalog_schema.startswith("powergrid-verified-news-catalog-v")
                              and record.get("company_id") == "POWERGRID"
                              and isinstance(record.get("attribution"), str) and bool(record["attribution"].strip()))
        if not identity_confirmed and not _mentions_company(title, snippet):
            not_company += 1
            entry["decision"] = "not_company_mentioned_in_title_or_snippet"
            continue
        published_raw = record.get("published_at")
        precision = record.get("publication_precision", "unknown")
        basis = record.get("publication_basis")
        publication_evidence = record.get("publication_evidence")
        publication_verified = (precision in {"day", "date", "minute", "timestamp"} and isinstance(basis, str) and basis in {"publisher_page", "publisher_snippet"}
                                and isinstance(publication_evidence, str) and bool(publication_evidence.strip()))
        published, publication_date, local_day = None, None, None
        if published_raw:
            try:
                if precision in {"day", "date"} or (isinstance(published_raw, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", published_raw)):
                    publication_date = date.fromisoformat(published_raw[:10])
                    local_day = publication_date
                else:
                    published = _time(published_raw, f"records[{index}].published_at")
                    if published > observed:
                        raise ValueError
                    local_day = published.astimezone(IST).date()
                    publication_date = local_day
            except (TypeError, ValueError, OverflowError):
                publication_verified = False
                published, publication_date, local_day = None, None, None
        if not publication_verified:
            published = None
            unverified_date += int(bool(published_raw))
            undated += int(not published_raw)
        if publication_verified and local_day and not START <= local_day <= END:
            out_of_range += 1
            entry["decision"] = "verified_publication_date_out_of_window"
            continue
        content_hash = content_hash.lower()
        available = max(observed, evidence_known)
        pair = (canonical_url, content_hash)
        if pair in seen_pairs:
            duplicate_url += 1
            entry["decision"] = "duplicate_url_and_content_hash"
            continue
        seen_pairs.add(pair)
        has_content_digest = isinstance(record.get("content_sha256"), str)
        if has_content_digest and content_hash in hash_canonicals:
            duplicate_content += 1
        previous = url_revisions.get(canonical_url)
        canonical_id = (previous["canonical_id"] if previous else
                        hash_canonicals.get(content_hash) if has_content_digest else None) or _sha(("url:" + canonical_url).encode())
        if has_content_digest:
            hash_canonicals.setdefault(content_hash, canonical_id)
        source_catalog[source_id] = {"source_id": source_id, "source_group": record.get("source_group"),
                                    "original_upstream_url": record.get("original_upstream_url")}
        event_id = _sha((source_id + "\n" + canonical_url + "\n" + content_hash).encode())
        event = {"event_id": event_id, "canonical_id": canonical_id, "source_id": source_id,
                 "source_url": source_url, "published_at": _stamp(published) if published else None, "observed_at": _stamp(observed),
                 "available_at": _stamp(available), "entities": ["powergrid"], "categories": ["market_news"],
                 "verification_status": "search_result_unverified" if catalog_schema == "powergrid-news-catalog-v1" else "publisher_reported_unverified",
                 "title": title.strip(),
                 "summary": snippet.strip(), "raw_hash": content_hash, "content_hash_basis": record.get("content_hash_basis") or record.get("content_scope"),
                 "original_upstream_url": record.get("original_upstream_url"), "source_group": record.get("source_group"),
                 "query_id": record.get("query_id"), "query_period": record.get("query_period"),
                 "catalog_record_id": record.get("record_id"), "publication_precision": record.get("publication_precision"),
                 "capture_file": record.get("capture_file"), "capture_sha256": record.get("capture_sha256"),
                 "retrieval_basis": record.get("retrieval_basis"), "attribution": record.get("attribution"),
                 "company_id": record.get("company_id"),
                 "publication_date": publication_date.isoformat() if publication_verified and publication_date else None,
                 "publication_date_candidate": published_raw if published_raw and not publication_verified else None,
                 "publication_basis": basis if publication_verified else None,
                 "publication_evidence": publication_evidence if publication_verified else None,
                 "publication_evidence_known_at_utc": _stamp(evidence_known),
                 "publication_timestamp_semantics": record.get("publication_timestamp_semantics"),
                 "publication_time_status": "verified_timestamp" if published else "verified_date_only" if publication_verified else "unknown_or_unverified",
                 "historical_window_eligible": bool(publication_verified and local_day and START <= local_day <= END),
                 "historical_use": "retrospective_event_study_only_retrieved_after_publication",
                 "content_type": record.get("content_type") or "publisher_page_excerpt",
                 "revision_of": previous["event_id"] if previous else None}
        accepted.append(event)
        entry["decision"] = "admitted_event_in_window" if event["historical_window_eligible"] else "admitted_observed_event_date_unverified_or_unknown"
        entry["event_id"] = event_id
        url_revisions[canonical_url] = event
    accepted.sort(key=lambda e: (e["publication_date"] or "9999-99-99", e["source_id"], e["event_id"]))
    periods = catalog.get("query_periods", [])
    if not isinstance(periods, list):
        periods = []
    months = []
    for label, start, end in _months():
        overlaps = []
        for period in periods:
            try:
                ps, pe = date.fromisoformat(period["start"]), date.fromisoformat(period["end"])
                if ps <= end and pe >= start:
                    overlaps.append(period)
            except (TypeError, KeyError, ValueError):
                continue
        successes = [period for period in overlaps if period.get("success") is True]
        months.append({"month": label, "start": start.isoformat(), "end": end.isoformat(),
                       "candidate_events": sum(e["historical_window_eligible"] and e["publication_date"][:7] == label for e in accepted),
                       "query_count": len(overlaps), "successful_query_count": len(successes),
                       "coverage": "searched_non_exhaustive" if successes else "query_failed_or_unproven" if overlaps else "not_searched_or_unproven"})
    quarter_coverage = []
    for year in range(START.year, END.year + 1):
        for quarter in range(1, 5):
            qstart = date(year, quarter * 3 - 2, 1)
            qend = date(year, quarter * 3, calendar.monthrange(year, quarter * 3)[1])
            if qend < START or qstart > END:
                continue
            qstart, qend = max(qstart, START), min(qend, END)
            query_count = 0
            for period in periods:
                try:
                    if date.fromisoformat(period["start"]) <= qend and date.fromisoformat(period["end"]) >= qstart:
                        query_count += 1
                except (TypeError, KeyError, ValueError):
                    pass
            successful = sum(1 for period in periods if period.get("success") is True and
                date.fromisoformat(period["start"]) <= qend and date.fromisoformat(period["end"]) >= qstart)
            quarter_coverage.append({"quarter": f"{year}-Q{quarter}", "start": qstart.isoformat(), "end": qend.isoformat(),
                                     "query_count": query_count, "successful_query_count": successful,
                                     "coverage": "searched_non_exhaustive" if successful else "query_failed_or_unproven" if query_count else "not_searched_or_unproven"})
    coverage = {"months": months, "quarters": quarter_coverage, "candidate_events_by_month": {
        item["month"]: item["candidate_events"] for item in months}, "query_periods": periods,
        "exhaustive": catalog.get("exhaustive") is True, "status": "unproven"}
    stats = {"input_records": len(records), "accepted_events": len(accepted),
             "historical_window_events": sum(e["historical_window_eligible"] for e in accepted),
             "rejected_records": rejected, "not_company_mentioned_records": not_company,
             "out_of_range_records": out_of_range, "undated_records": undated,
             "unverified_publication_date_records": unverified_date,
             "duplicate_url_records": duplicate_url, "duplicate_content_records": duplicate_content,
             "search_snippet_records": sum(isinstance(r, dict) and r.get("content_type") in {"search_snippet", "search_result_snippet"} for r in records),
             "full_text_records": sum(isinstance(r, dict) and isinstance(r.get("full_text"), str) and bool(r["full_text"].strip()) for r in records),
             "gaps": catalog.get("gaps", []), "query_count": catalog.get("query_count"),
             "search_credits_used": catalog.get("search_credits_used"), "credit_cap": catalog.get("credit_cap"),
             "catalog_credit_observations": catalog.get("credit_observations"),
             "catalog_limitations": catalog.get("limitations", []),
              "search_outputs": catalog.get("search_outputs", []),
              "sources": sorted(source_catalog.values(), key=lambda s: s["source_id"]),
              "candidate_sources": sorted(candidate_sources), "inventory": inventory}
    return accepted, {"coverage": coverage, "collection": stats, "retrieved_at_utc": _stamp(retrieved)}


def supplemental_event(document: dict, *, built_at: datetime) -> dict:
    source_id, source_url, published_raw, text = (document.get(key) for key in ("source_id", "source_url", "published_at", "text"))
    metadata = document.get("retrieval_metadata", {})
    title = metadata.get("ogTitle") or metadata.get("og:title") if isinstance(metadata, dict) else None
    if not all(isinstance(value, str) and value.strip() for value in (source_id, source_url, published_raw, title, text)):
        raise ValueError("supplemental event requires source ID, URL, publisher title, publication time and extracted text")
    observed = _time(document.get("observed_at"), "supplemental observed_at")
    published = _time(published_raw, "supplemental published_at")
    if published > observed or observed > built_at or not _mentions_company(title, text):
        raise ValueError("supplemental publisher event has invalid chronology or does not mention POWERGRID")
    url = _canonical_url(source_url)
    content_hash = _sha(text.encode("utf-8"))
    if not isinstance(metadata, dict):
        raise ValueError("supplemental retrieval metadata must be an object")
    evidence = re.search(r"Posted On:\s*\n?([^\n]+)", text, re.IGNORECASE)
    if not evidence:
        raise ValueError("supplemental publisher page lacks its displayed publication-date evidence")
    local_day = published.astimezone(IST).date()
    return {"event_id": _sha((source_id + "\n" + url + "\n" + content_hash).encode()),
            "canonical_id": _sha(("url:" + url).encode()), "source_id": source_id,
            "source_url": source_url, "published_at": _stamp(published), "publication_date": local_day.isoformat(),
            "publication_precision": "timestamp", "publication_time_status": "verified_timestamp",
            "publication_basis": "publisher_page", "publication_evidence": evidence.group(1).strip(),
            "observed_at": _stamp(observed), "available_at": _stamp(observed), "entities": ["powergrid"],
            "categories": ["market_news"], "verification_status": "publisher_reported_unverified",
            "title": title.strip(), "summary": text, "raw_hash": content_hash,
            "content_hash_basis": "full extracted publisher page text", "content_type": "publisher_page",
            "permission_basis": document.get("permission_basis"),
            "training_rights_status": document.get("training_rights_status", "unknown"),
            "historical_window_eligible": START <= local_day <= END,
            "historical_use": "retrospective_event_study_only_retrieved_after_publication"}


def load_verified_daily_bars(csv_path: Path, manifest_path: Path, *, built_at: datetime) -> tuple[list[dict], dict]:
    raw = csv_path.read_bytes()
    manifest_raw = manifest_path.read_bytes()
    manifest = json.loads(manifest_raw)
    if (manifest.get("schema_version") != "powergrid-daily-bars-v1" or manifest.get("status") != "valid"
            or manifest.get("isin") != "INE752E01010" or manifest.get("csv_sha256", "").lower() != _sha(raw)):
        raise ValueError("price manifest must validate this exact POWERGRID CSV and ISIN")
    validation = manifest.get("independent_validation")
    if not isinstance(validation, dict) or validation.get("status") != "passed":
        raise ValueError("daily outcomes require an independent bar-validation receipt")
    retrieved = _time(manifest.get("retrieved_at_utc"), "price manifest retrieved_at_utc")
    if retrieved > built_at:
        raise ValueError("price dataset retrieval time is in the future")
    rows = []
    expected = {"isin", "trade_date", "close", "volume", "source_id", "source_location", "retrieved_at"}
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not expected.issubset(reader.fieldnames):
            raise ValueError("daily price CSV does not match the collection contract")
        for row in reader:
            try:
                if row["isin"] != "INE752E01010" or not row["source_id"].strip() or not row["source_location"].strip():
                    raise ValueError
                day = date.fromisoformat(row["trade_date"])
                close, volume = float(row["close"]), float(row["volume"])
                row_retrieved = _time(row["retrieved_at"], "bar retrieved_at")
                if not math.isfinite(close) or close <= 0 or not math.isfinite(volume) or volume < 0 or row_retrieved > built_at:
                    raise ValueError
            except (KeyError, TypeError, ValueError, OverflowError):
                raise ValueError("daily price CSV contains an invalid identity, date, value or timestamp") from None
            if day < START or day > END or (rows and day <= rows[-1]["trade_date"]):
                raise ValueError("daily bars must be chronological and within the requested history window")
            rows.append({"trade_date": day, "close": close, "volume": volume, "source_id": row["source_id"],
                         "source_location": row["source_location"], "retrieved_at": _stamp(row_retrieved)})
    if len(rows) != manifest.get("rows"):
        raise ValueError("price row count does not match its manifest")
    return rows, {"schema_version": manifest["schema_version"], "csv_sha256": _sha(raw),
                  "manifest_sha256": _sha(manifest_raw), "rows": len(rows), "isin": manifest["isin"],
                  "source_id": manifest.get("source_id"), "retrieved_at_utc": _stamp(retrieved),
                  "coverage": manifest.get("coverage"), "independent_validation": validation}


def daily_reactions(events: list[dict], bars: list[dict]) -> list[dict]:
    by_date = {row["trade_date"]: row for row in bars}
    dates = sorted(by_date)
    outcomes = []
    for event in events:
        if not event.get("historical_window_eligible") or not event.get("publication_date"):
            continue
        published = date.fromisoformat(event["publication_date"])
        if published not in by_date:
            continue
        index = dates.index(published)
        if index == 0:
            continue
        prior, current = by_date[dates[index - 1]], by_date[published]
        outcomes.append({"event_id": event["event_id"], "company_id": "powergrid",
            "publication_date": published.isoformat(), "previous_trade_date": prior["trade_date"].isoformat(),
            "reaction_trade_date": published.isoformat(),
            "close_to_close_return_pct": round((current["close"] / prior["close"] - 1) * 100, 8),
            "source_id": current["source_id"], "source_location": current["source_location"],
            "retrieved_at": current["retrieved_at"], "interpretation": "descriptive publication-date close reaction",
            "daily_timestamp_ambiguity": True, "transaction_costs_adjusted": False,
            "causal_attribution": False, "training_label": False})
    return outcomes


def build(catalog: dict, *, catalog_sha256: str, built_at: datetime | None = None,
          supplemental: dict | None = None, supplemental_sha256: str | None = None) -> dict:
    built_at = built_at or datetime.now(timezone.utc)
    if built_at.tzinfo is None or built_at.utcoffset() is None:
        raise ValueError("built_at must be timezone-aware")
    events, details = _catalog_events(catalog, built_at=built_at.astimezone(timezone.utc))
    if supplemental is not None:
        extra = supplemental_event(supplemental, built_at=built_at.astimezone(timezone.utc))
        if extra["event_id"] not in {event["event_id"] for event in events}:
            events.append(extra)
        details["collection"]["supplemental_event"] = {"event_id": extra["event_id"],
            "source_id": extra["source_id"], "observed_at": extra["observed_at"],
            "published_at": extra["published_at"], "source_sha256": supplemental_sha256}
        sources = details["collection"]["sources"]
        if extra["source_id"] not in {row["source_id"] for row in sources}:
            sources.append({"source_id": extra["source_id"], "source_group": "PIB",
                            "original_upstream_url": extra["source_url"]})
            sources.sort(key=lambda row: row["source_id"])
    return {"schema_version": "company-history-archive-v1", "company": {"name": "Power Grid Corporation of India Limited",
            "nse_symbol": "POWERGRID", "isin": "INE752E01010", "aliases": list(ALIASES)},
            "requested_window": {"start": START.isoformat(), "end": END.isoformat(), "timezone": "Asia/Kolkata"},
            "built_at_utc": _stamp(built_at), "catalog_sha256": catalog_sha256,
            "dataset_status": "partial", "train_ready": False,
            "retrospective_only": True, "events": events, "price_outcomes": [],
            "source_reliability": [], "coverage": details["coverage"], "collection": details["collection"],
            "price_status": "not_supplied_or_not_verified",
            "provenance_policy": {"event_available_at": "actual catalog observed_at_utc, never publication date",
                "event_verification": "publisher-reported; claim truth unknown", "source_accuracy": "not measured; no adjudications imported",
                "lookback_policy": "current retrieval cannot be backdated into a historical trading decision"}}


def _write_new(path: Path, data: bytes) -> str:
    with path.open("xb") as stream:
        stream.write(data)
    return _sha(data)


def _events_csv(events: list[dict]) -> bytes:
    fields = ["event_id", "source_url", "published_at", "publication_date", "publication_precision",
              "publication_timestamp_semantics", "publication_evidence_known_at_utc", "observed_at",
              "title", "source_id", "historical_use", "verification_status"]
    import io
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(events)
    return stream.getvalue().encode("utf-8")


def verify_capture_files(catalog: dict, catalog_path: Path) -> list[dict]:
    files = catalog.get("capture_files")
    if not isinstance(files, list) or not files:
        raise ValueError("verified news catalog requires source-capture file hashes")
    root = catalog_path.resolve().parent
    verified, by_path, contents = [], {}, {}
    for item in files:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ValueError("capture file manifest row is malformed")
        relative = Path(item["path"])
        path = (root / relative).resolve()
        if relative.is_absolute() or ".." in relative.parts or not path.is_relative_to(root):
            raise ValueError("capture file path must stay inside the catalog folder")
        raw = path.read_bytes()
        digest = _sha(raw)
        if not isinstance(item.get("sha256"), str) or item["sha256"].lower() != digest:
            raise ValueError("publisher capture file hash does not match the catalog")
        verified.append({"path": relative.as_posix(), "sha256": digest, "bytes": len(raw)})
        by_path[relative.as_posix()] = digest
        contents[relative.as_posix()] = _capture_normalized(raw.decode("utf-8", errors="replace"))
    for record in catalog.get("records", []):
        if not isinstance(record, dict):
            raise ValueError("verified publisher record is malformed")
        capture = record.get("capture_file")
        digest = record.get("capture_sha256")
        if not isinstance(capture, str) or capture not in by_path or not isinstance(digest, str) or by_path[capture] != digest.lower():
            raise ValueError("publisher record is not bound to a verified capture file")
        evidence = (record.get("source_url"), record.get("title"), record.get("publication_evidence"))
        text = contents[capture]
        if any(not isinstance(value, str) or not value.strip() or _capture_normalized(value) not in text for value in evidence):
            raise ValueError("publisher capture does not contain the record URL, title, and displayed date evidence")
    return verified


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path, help="saved POWERGRID catalog JSON; no network calls")
    parser.add_argument("--output-dir", type=Path, required=True, help="new archive directory")
    parser.add_argument("--receipt", type=Path, help="optional sidecar receipt whose catalog hash must match")
    parser.add_argument("--supplemental-event", type=Path, help="previously retrieved publisher page JSON")
    parser.add_argument("--prices-csv", type=Path, help="optional verified daily POWERGRID OHLCV CSV")
    parser.add_argument("--price-manifest", type=Path, help="hash and independent-validation manifest for --prices-csv")
    args = parser.parse_args(argv)
    try:
        raw = args.catalog.read_bytes()
        catalog = json.loads(raw)
        captures = verify_capture_files(catalog, args.catalog) if str(catalog.get("schema_version", "")).startswith("powergrid-verified-news-catalog-v") else []
        receipt = json.loads(args.receipt.read_text(encoding="utf-8")) if args.receipt else None
        if receipt and (receipt.get("catalog_sha256", "").lower() != _sha(raw).lower()
                        or receipt.get("record_count") not in (None, len(catalog.get("records", [])))):
            raise ValueError("catalog receipt does not match the input catalog")
        supplemental_raw = args.supplemental_event.read_bytes() if args.supplemental_event else None
        supplemental = json.loads(supplemental_raw) if supplemental_raw else None
        if bool(args.prices_csv) != bool(args.price_manifest):
            raise ValueError("--prices-csv and --price-manifest must be supplied together")
        if args.output_dir.exists():
            raise ValueError("output directory exists; select a new immutable archive path")
        archive = build(catalog, catalog_sha256=_sha(raw), supplemental=supplemental,
                        supplemental_sha256=_sha(supplemental_raw) if supplemental_raw else None)
        archive["collection"]["receipt"] = receipt or {"status": "not_supplied"}
        archive["collection"]["verified_capture_files"] = captures
        price_raw_hash = price_manifest_hash = None
        if args.prices_csv:
            bars, price_provenance = load_verified_daily_bars(args.prices_csv, args.price_manifest,
                built_at=datetime.now(timezone.utc))
            archive["price_outcomes"] = daily_reactions(archive["events"], bars)
            archive["price_status"] = "verified_daily_bars_descriptive_only"
            archive["price_provenance"] = price_provenance
            price_raw_hash = _sha(args.prices_csv.read_bytes())
            price_manifest_hash = _sha(args.price_manifest.read_bytes())
        args.output_dir.mkdir(parents=True, exist_ok=False)
        events_bytes = (json.dumps(archive["events"], sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode()
        event_hash = _write_new(args.output_dir / "events.json", events_bytes)
        events_csv_hash = _write_new(args.output_dir / "articles.csv", _events_csv(archive["events"]))
        store = ContextStore(args.output_dir / "context.db")
        store.initialize()
        store.import_batch({"events": archive["events"], "nodes": [], "claims": [], "relationships": [], "analogs": []})
        score_rows = []
        for source in archive["collection"]["sources"]:
            score_rows.append(source_reliability(store, source_id=source["source_id"], company_id="powergrid",
                category="company_performance", asof=archive["built_at_utc"]))
        score_bytes = (json.dumps(score_rows, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode()
        score_hash = _write_new(args.output_dir / "source-scores.json", score_bytes)
        archive["source_reliability"] = score_rows
        archive_bytes = (json.dumps(archive, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode()
        archive_hash = _write_new(args.output_dir / "archive.json", archive_bytes)
        manifest = {key: value for key, value in archive.items() if key not in ("events", "source_reliability")}
        manifest.update({"artifact_hashes": {"catalog_sha256": _sha(raw), "receipt_sha256": _sha(args.receipt.read_bytes()) if args.receipt else None,
            "supplemental_source_sha256": _sha(supplemental_raw) if supplemental_raw else None,
            "price_csv_sha256": price_raw_hash, "price_manifest_sha256": price_manifest_hash, "events_sha256": event_hash,
            "articles_csv_sha256": events_csv_hash,
            "publisher_capture_files": captures,
            "archive_sha256": archive_hash, "source_scores_sha256": score_hash,
            "context_db_sha256": _sha((args.output_dir / "context.db").read_bytes())},
            "import_counts": {"events": len(archive["events"]), "claims": 0, "relationships": 0, "adjudications": 0},
            "source_score_summary": {"source_count": len(score_rows), "adjudicated_count": sum(x["resolved_n"] for x in score_rows),
                                     "all_cold_start": all(x["cold_start"] for x in score_rows)}})
        _write_new(args.output_dir / "manifest.json", (json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode())
        print(json.dumps({"status": "partial", "events": len(archive["events"]), "train_ready": False,
                          "output_dir": str(args.output_dir)}, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f"Company history assembly failed ({type(error).__name__}). Check the catalog and choose a new output directory.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
