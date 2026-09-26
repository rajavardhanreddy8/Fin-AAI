from __future__ import annotations

import http.cookiejar
import json
import urllib.parse
import urllib.request
from datetime import date, datetime
from typing import Any

from .base import CollectedDocument, CollectorError, read_bytes


NSE_SHAREHOLDING_API = (
    "https://www.nseindia.com/api/corporate-share-holdings-master"
)
_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/140.0 Safari/537.36"
)


def _nse_date(value: str) -> date:
    return datetime.strptime(value.strip(), "%d-%b-%Y").date()


class NSEShareholdingCollector:
    """Discover the latest official NSE shareholding-pattern XBRL filing."""

    def __init__(self) -> None:
        cookies = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cookies)
        )

    def _fetch_rows(self, symbol: str) -> Any:
        quote_url = "https://www.nseindia.com/get-quotes/equity?" + urllib.parse.urlencode(
            {"symbol": symbol}
        )
        page_request = urllib.request.Request(
            quote_url,
            headers={"User-Agent": _BROWSER_USER_AGENT, "Accept": "text/html"},
        )
        with self._opener.open(page_request, timeout=30):
            pass

        api_url = NSE_SHAREHOLDING_API + "?" + urllib.parse.urlencode(
            {"index": "equities", "symbol": symbol}
        )
        api_request = urllib.request.Request(
            api_url,
            headers={
                "User-Agent": _BROWSER_USER_AGENT,
                "Accept": "application/json,text/plain,*/*",
                "Referer": quote_url,
            },
        )
        with self._opener.open(api_request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8-sig"))

    def collect_latest(
        self,
        expected_isin: str,
        expected_symbol: str,
        as_of: date,
    ) -> CollectedDocument:
        isin = expected_isin.strip().upper()
        symbol = expected_symbol.strip().upper()
        payload = self._fetch_rows(symbol)
        if not isinstance(payload, list):
            raise CollectorError("NSE shareholding response must contain a JSON list")

        candidates: list[tuple[date, date, dict[str, Any]]] = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            try:
                period_end = _nse_date(str(row["date"]))
                submitted = _nse_date(str(row["submissionDate"]))
            except (KeyError, TypeError, ValueError):
                continue
            if period_end <= as_of and submitted <= as_of:
                candidates.append((period_end, submitted, row))
        if not candidates:
            raise CollectorError(f"NSE returned no shareholding filing for {symbol} by {as_of}")

        period_end, submitted, row = max(candidates, key=lambda item: (item[0], item[1]))
        row_symbol = str(row.get("symbol", "")).strip().upper()
        if row_symbol != symbol:
            raise CollectorError(
                f"NSE shareholding symbol mismatch: {row_symbol}, expected {symbol}"
            )
        xbrl_url = str(row.get("xbrl", "")).strip()
        if not xbrl_url.startswith("https://nsearchives.nseindia.com/"):
            raise CollectorError(f"NSE shareholding filing has no official XBRL URL: {xbrl_url!r}")
        try:
            xbrl_text = read_bytes(xbrl_url).decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise CollectorError(f"NSE shareholding XBRL is not valid UTF-8: {exc}") from exc
        if isin not in xbrl_text:
            api_isin = str(row.get("isin", "")).strip().upper()
            raise CollectorError(
                f"NSE shareholding XBRL identity mismatch: expected {isin}; "
                f"API metadata reported {api_isin or 'no ISIN'}"
            )

        return CollectedDocument.from_mapping(
            {
                "document_key": f"nse_shareholding:{isin}:{period_end.isoformat()}",
                "isin": isin,
                "source_id": "nse_filings",
                "source_tier": "official",
                "document_type": "shareholding_pattern",
                "title": f"{symbol} shareholding pattern for quarter ended {period_end.isoformat()}",
                "published_at": submitted.isoformat(),
                "retrieved_at": datetime.now().astimezone().isoformat(),
                "source_location": xbrl_url,
                "period_end": period_end.isoformat(),
                "reporting_scope": "not_applicable",
                "content_excerpt": xbrl_text,
            }
        )
