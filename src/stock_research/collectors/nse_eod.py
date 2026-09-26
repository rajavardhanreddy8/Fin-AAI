from __future__ import annotations

import csv
import io
import zipfile
from datetime import date, datetime, timedelta, timezone
from urllib.error import HTTPError

from .base import CollectorError, read_bytes
from .price_csv import CollectedPrice


NSE_EOD_SOURCE_ID = "nse_eod_bhavcopy"
NSE_EOD_SOURCE_NAME = "NSE CM-UDiFF Common Bhavcopy Final"
NSE_EOD_BASE_URL = "https://nsearchives.nseindia.com/content/cm/"


def bhavcopy_url(trade_date: date) -> str:
    stamp = trade_date.strftime("%Y%m%d")
    return f"{NSE_EOD_BASE_URL}BhavCopy_NSE_CM_0_0_0_{stamp}_F_0000.csv.zip"


class NSEBhavcopyCollector:
    """Collect official NSE cash-market close and volume from CM-UDiFF."""

    def collect(self, trade_date: date, expected_isins: set[str], *, require_all: bool = True) -> list[CollectedPrice]:
        if not expected_isins:
            raise CollectorError("At least one expected ISIN is required")
        expected = {isin.strip().upper() for isin in expected_isins}
        location = bhavcopy_url(trade_date)
        payload = read_bytes(location)
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
                if len(members) != 1:
                    raise CollectorError("NSE bhavcopy archive must contain exactly one CSV")
                content = archive.read(members[0]).decode("utf-8-sig")
        except (zipfile.BadZipFile, UnicodeDecodeError) as exc:
            raise CollectorError(f"Invalid NSE bhavcopy archive: {exc}") from exc

        retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        found: dict[str, CollectedPrice] = {}
        for row_number, row in enumerate(csv.DictReader(io.StringIO(content)), start=2):
            isin = str(row.get("ISIN", "")).strip().upper()
            if isin not in expected or str(row.get("SctySrs", "")).strip() != "EQ":
                continue
            try:
                row_date = date.fromisoformat(row["TradDt"].strip())
                close = float(row["ClsPric"])
                volume = int(row["TtlTradgVol"])
            except (KeyError, TypeError, ValueError) as exc:
                raise CollectorError(f"Invalid NSE bhavcopy row {row_number}: {exc}") from exc
            if row_date != trade_date:
                raise CollectorError(
                    f"NSE bhavcopy row {row_number} is dated {row_date}, expected {trade_date}"
                )
            if close <= 0 or volume < 0:
                raise CollectorError(f"Invalid NSE price or volume in row {row_number}")
            if isin in found:
                raise CollectorError(f"Duplicate NSE EQ row for {isin}")
            found[isin] = CollectedPrice(
                isin=isin,
                trade_date=row_date,
                close=close,
                volume=volume,
                source_id=NSE_EOD_SOURCE_ID,
                source_location=location,
                retrieved_at=retrieved_at,
            )

        missing = sorted(expected - set(found))
        if missing and require_all:
            raise CollectorError(f"NSE bhavcopy is missing expected EQ ISIN(s): {', '.join(missing)}")
        return [found[isin] for isin in sorted(found)]

    def collect_recent(
        self,
        as_of: date,
        expected_isins: set[str],
        *,
        sessions: int = 4,
        calendar_lookback_days: int = 10,
    ) -> list[CollectedPrice]:
        """Collect recent sessions, tolerating weekends, holidays, and unpublished files."""
        if sessions < 1 or calendar_lookback_days < 1:
            raise ValueError("NSE EOD collection limits must be positive")
        rows: list[CollectedPrice] = []
        cursor = as_of
        floor = as_of - timedelta(days=calendar_lookback_days - 1)
        while cursor >= floor and len(rows) < sessions * len(expected_isins):
            if cursor.weekday() < 5:
                try:
                    rows.extend(self.collect(cursor, expected_isins))
                except HTTPError as exc:
                    if exc.code != 404:
                        raise
            cursor -= timedelta(days=1)
        if not rows:
            raise CollectorError(
                f"No official NSE bhavcopy was available in the {calendar_lookback_days}-day window"
            )
        return sorted(rows, key=lambda row: (row.trade_date, row.isin))
