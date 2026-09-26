from __future__ import annotations

from pathlib import Path

from .base import CollectedDocument, CollectorError, read_json


class CompanyIRCollector:
    """Collect company-primary documents from a reproducible IR manifest."""

    def __init__(self, expected_isin: str) -> None:
        self.expected_isin = expected_isin.upper()

    def collect(self, manifest: str | Path) -> list[CollectedDocument]:
        payload = read_json(manifest)
        if not isinstance(payload, list):
            raise CollectorError("IR manifest must contain a JSON list")
        documents = [
            CollectedDocument.from_mapping(row)
            for row in payload
            if row.get("collector") == "company_ir"
        ]
        if any(document.isin != self.expected_isin for document in documents):
            raise CollectorError("IR manifest contains a document for an unexpected ISIN")
        return sorted(documents, key=lambda item: (item.published_at, item.document_key))
