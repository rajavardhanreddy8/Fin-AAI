from __future__ import annotations

import hashlib
import json
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


USER_AGENT = "IndianStockResearch/0.2 evidence-collector"


class CollectorError(ValueError):
    """Raised when collected evidence is malformed or cannot be attributed."""


def read_bytes(location: str | Path) -> bytes:
    raw_location = str(location)
    if urlparse(raw_location).scheme in {"http", "https"}:
        request = urllib.request.Request(raw_location, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()
    return Path(location).read_bytes()


def read_json(location: str | Path) -> Any:
    return json.loads(read_bytes(location).decode("utf-8-sig"))


@dataclass(frozen=True, slots=True)
class CollectedDocument:
    document_key: str
    isin: str
    source_id: str
    source_tier: str
    document_type: str
    title: str
    published_at: str
    retrieved_at: str
    source_location: str
    period_end: str | None
    reporting_scope: str
    content_hash: str
    raw_text: str
    confidence: float

    @classmethod
    def from_mapping(cls, row: dict[str, Any]) -> "CollectedDocument":
        required = (
            "document_key",
            "isin",
            "source_id",
            "source_tier",
            "document_type",
            "title",
            "published_at",
            "source_location",
        )
        missing = [name for name in required if not str(row.get(name, "")).strip()]
        if missing:
            raise CollectorError(f"Document is missing required field(s): {', '.join(missing)}")

        isin = str(row["isin"]).strip().upper()
        if len(isin) != 12 or not isin.isalnum():
            raise CollectorError(f"Invalid ISIN in document: {isin!r}")
        source_location = str(row["source_location"]).strip()
        if urlparse(source_location).scheme not in {"http", "https"}:
            raise CollectorError(f"Document source must be an HTTP(S) location: {source_location!r}")
        published_at = date.fromisoformat(str(row["published_at"])[:10]).isoformat()
        period_end_raw = row.get("period_end")
        period_end = date.fromisoformat(str(period_end_raw)[:10]).isoformat() if period_end_raw else None
        scope = str(row.get("reporting_scope", "consolidated")).strip().lower()
        if scope not in {"consolidated", "standalone", "bank", "not_applicable"}:
            raise CollectorError(f"Unsupported reporting scope: {scope!r}")
        raw_text = str(row.get("content_excerpt", "")).strip()
        if not raw_text:
            raw_text = f"{row['title']}\n{source_location}"
        retrieved_at = str(row.get("retrieved_at", "")).strip()
        if retrieved_at:
            datetime.fromisoformat(retrieved_at.replace("Z", "+00:00"))
        else:
            retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        tier = str(row["source_tier"]).strip()
        confidence = {"official": 1.0, "company_primary": 0.95}.get(tier, 0.65)
        return cls(
            document_key=str(row["document_key"]).strip(),
            isin=isin,
            source_id=str(row["source_id"]).strip(),
            source_tier=tier,
            document_type=str(row["document_type"]).strip(),
            title=str(row["title"]).strip(),
            published_at=published_at,
            retrieved_at=retrieved_at,
            source_location=source_location,
            period_end=period_end,
            reporting_scope=scope,
            content_hash=hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
            raw_text=raw_text,
            confidence=confidence,
        )
