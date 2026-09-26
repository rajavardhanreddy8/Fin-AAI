from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from .base import CollectorError, read_bytes


@dataclass(frozen=True, slots=True)
class CollectedPrice:
    isin: str
    trade_date: date
    close: float
    volume: int
    source_id: str
    source_location: str
    retrieved_at: str


class PriceCSVCollector:
    def __init__(self, expected_isin: str, source_id: str, source_location: str) -> None:
        self.expected_isin = expected_isin.upper()
        self.source_id = source_id
        self.source_location = source_location

    def collect(self, location: str | Path) -> list[CollectedPrice]:
        content = read_bytes(location).decode("utf-8-sig")
        retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        rows: list[CollectedPrice] = []
        for row_number, row in enumerate(csv.DictReader(io.StringIO(content)), start=2):
            try:
                isin = row["isin"].strip().upper()
                trade_date = date.fromisoformat(row["trade_date"].strip())
                close = float(row["close"])
                volume = int(row["volume"])
            except (KeyError, TypeError, ValueError) as exc:
                raise CollectorError(f"Invalid price row {row_number}: {exc}") from exc
            if isin != self.expected_isin:
                raise CollectorError(f"Unexpected ISIN in price row {row_number}: {isin}")
            if close <= 0 or volume < 0:
                raise CollectorError(f"Invalid price or volume in row {row_number}")
            rows.append(
                CollectedPrice(
                    isin=isin,
                    trade_date=trade_date,
                    close=close,
                    volume=volume,
                    source_id=self.source_id,
                    source_location=self.source_location,
                    retrieved_at=retrieved_at,
                )
            )
        if not rows:
            raise CollectorError("Price file contains no rows")
        return sorted(rows, key=lambda item: item.trade_date)
