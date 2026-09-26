from __future__ import annotations

from pathlib import Path

from .base import CollectedDocument, CollectorError, read_json


class NSEFilingsCollector:
    """Collect official exchange filings from an exported NSE evidence manifest.

    NSE endpoints may throttle unattended clients. A persisted manifest makes the
    evidence set deterministic while retaining the original archive URL.
    """

    def __init__(self, expected_isin: str) -> None:
        self.expected_isin = expected_isin.upper()

    def collect(self, manifest: str | Path) -> list[CollectedDocument]:
        payload = read_json(manifest)
        if not isinstance(payload, list):
            raise CollectorError("NSE manifest must contain a JSON list")
        documents = [
            CollectedDocument.from_mapping(row)
            for row in payload
            if row.get("collector") == "nse_filings"
        ]
        if any(document.isin != self.expected_isin for document in documents):
            raise CollectorError("NSE manifest contains a document for an unexpected ISIN")
        return sorted(documents, key=lambda item: (item.published_at, item.document_key))
