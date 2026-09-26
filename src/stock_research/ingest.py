from __future__ import annotations

import csv
import hashlib
import io
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .db import transaction
from .models import EvidenceTier, PriceBar, Security, utc_now


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def register_source(
    db_path: str | Path,
    source_id: str,
    source_name: str,
    evidence_tier: EvidenceTier | str,
    base_url: str | None = None,
) -> None:
    tier = EvidenceTier(evidence_tier).value
    with transaction(db_path) as connection:
        connection.execute(
            """
            INSERT INTO sources(source_id, source_name, base_url, evidence_tier, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source_id) DO UPDATE SET
                source_name=excluded.source_name,
                base_url=excluded.base_url,
                evidence_tier=excluded.evidence_tier
            """,
            (source_id, source_name, base_url, tier, _iso(utc_now())),
        )


def import_universe(db_path: str | Path, csv_path: str | Path) -> int:
    rows: list[Security] = []
    with Path(csv_path).open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            security = Security(
                isin=row["isin"].strip().upper(),
                company_name=row["company_name"].strip(),
                nse_symbol=row.get("nse_symbol", "").strip().upper() or None,
                bse_code=row.get("bse_code", "").strip() or None,
                sector=row.get("sector", "").strip() or None,
                style_bucket=row.get("style_bucket", "watchlist").strip() or "watchlist",
                active=row.get("active", "1").strip().lower() in {"1", "true", "yes"},
            )
            security.validate()
            rows.append(security)

    now = _iso(utc_now())
    with transaction(db_path) as connection:
        for security in rows:
            connection.execute(
                """
                INSERT INTO securities(
                    isin, company_name, nse_symbol, bse_code, sector,
                    style_bucket, active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(isin) DO UPDATE SET
                    company_name=excluded.company_name,
                    nse_symbol=excluded.nse_symbol,
                    bse_code=excluded.bse_code,
                    sector=excluded.sector,
                    style_bucket=excluded.style_bucket,
                    active=excluded.active,
                    updated_at=excluded.updated_at
                """,
                (
                    security.isin,
                    security.company_name,
                    security.nse_symbol,
                    security.bse_code,
                    security.sector,
                    security.style_bucket,
                    int(security.active),
                    now,
                    now,
                ),
            )
    return len(rows)


def _open_text(location: str | Path) -> str:
    raw_location = str(location)
    if urlparse(raw_location).scheme in {"http", "https"}:
        request = urllib.request.Request(
            raw_location,
            headers={"User-Agent": "IndianStockResearch/0.1 research-only"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8-sig")
    return Path(location).read_text(encoding="utf-8-sig")


def import_prices_csv(
    db_path: str | Path,
    location: str | Path,
    source_id: str,
) -> int:
    content = _open_text(location)
    retrieved_at = utc_now()
    rows: list[PriceBar] = []
    for row_number, row in enumerate(csv.DictReader(io.StringIO(content)), start=2):
        try:
            bar = PriceBar(
                isin=row["isin"].strip().upper(),
                trade_date=datetime.strptime(row["trade_date"].strip(), "%Y-%m-%d").date(),
                close=float(row["close"]),
                volume=int(float(row["volume"])) if row.get("volume", "").strip() else None,
                source_id=source_id,
                retrieved_at=retrieved_at,
            )
            bar.validate()
            rows.append(bar)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid price row {row_number}: {exc}") from exc

    with transaction(db_path) as connection:
        for bar in rows:
            connection.execute(
                """
                INSERT INTO price_bars(isin, trade_date, close, volume, source_id, retrieved_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(isin, trade_date, source_id) DO UPDATE SET
                    close=excluded.close,
                    volume=excluded.volume,
                    retrieved_at=excluded.retrieved_at
                """,
                (
                    bar.isin,
                    bar.trade_date.isoformat(),
                    bar.close,
                    bar.volume,
                    bar.source_id,
                    _iso(bar.retrieved_at),
                ),
            )
    return len(rows)


def _child_text(element: ET.Element, names: tuple[str, ...]) -> str | None:
    for child in element:
        local_name = child.tag.rsplit("}", 1)[-1].lower()
        if local_name in names and child.text:
            return child.text.strip()
    return None


def import_filings_feed(
    db_path: str | Path,
    location: str | Path,
    source_id: str,
    default_isin: str | None = None,
) -> int:
    content = _open_text(location)
    root = ET.fromstring(content)
    items = [node for node in root.iter() if node.tag.rsplit("}", 1)[-1].lower() in {"item", "entry"}]
    retrieved_at = utc_now()
    inserted = 0

    with transaction(db_path) as connection:
        source = connection.execute(
            "SELECT evidence_tier FROM sources WHERE source_id = ?", (source_id,)
        ).fetchone()
        if source is None:
            raise ValueError(f"Unknown source_id: {source_id}")
        confidence_by_tier = {
            "official": 1.0,
            "company_primary": 0.9,
            "reputable_secondary": 0.65,
            "market_opinion": 0.35,
            "social": 0.1,
        }
        confidence = confidence_by_tier[source["evidence_tier"]]

        for item in items:
            title = _child_text(item, ("title",)) or "Untitled filing"
            link = _child_text(item, ("link", "guid", "id"))
            if not link:
                link_node = next(
                    (c for c in item if c.tag.rsplit("}", 1)[-1].lower() == "link"), None
                )
                link = link_node.attrib.get("href") if link_node is not None else None
            link = link or f"feed:{hashlib.sha256(title.encode()).hexdigest()[:16]}"
            published = _child_text(item, ("pubdate", "published", "updated", "date"))
            description = _child_text(item, ("description", "summary", "content")) or ""
            combined = f"{title}\n{description}\n{link}"
            digest = hashlib.sha256(combined.encode("utf-8")).hexdigest()
            document_type = classify_document(title)
            before = connection.total_changes
            connection.execute(
                """
                INSERT OR IGNORE INTO documents(
                    isin, source_id, document_type, title, published_at,
                    retrieved_at, source_location, content_hash, confidence, raw_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    default_isin,
                    source_id,
                    document_type,
                    title,
                    published,
                    _iso(retrieved_at),
                    link,
                    digest,
                    confidence,
                    description,
                ),
            )
            inserted += connection.total_changes - before
    return inserted


def classify_document(title: str) -> str:
    lowered = title.lower()
    rules = (
        (("financial result", "quarterly result", "earnings"), "financial_results"),
        (("shareholding",), "shareholding_pattern"),
        (("annual report",), "annual_report"),
        (("auditor",), "auditor_update"),
        (("resignation",), "management_change"),
        (("pledge",), "promoter_pledge"),
        (("order", "contract"), "business_update"),
        (("dividend", "split", "bonus", "buyback"), "corporate_action"),
    )
    for terms, label in rules:
        if any(term in lowered for term in terms):
            return label
    return "exchange_announcement"
