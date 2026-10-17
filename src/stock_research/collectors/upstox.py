"""Read-only Upstox Analytics Token market data collector."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

HISTORY_URL = "https://api.upstox.com/v3/historical-candle"
NEWS_URL = "https://api.upstox.com/v2/news"


class UpstoxError(RuntimeError):
    pass


def canonical_json(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(value) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical_json(value)).hexdigest()


def _aware(value: str | datetime) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


def _stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class UpstoxClient:
    """Fixed-endpoint, read-only client. Pass transport and clock for offline tests."""

    def __init__(self, token: str | None = None, *, transport=None, clock=None, sleeper=time.sleep):
        self.token = token if token is not None else os.environ.get("UPSTOX_ANALYTICS_TOKEN", "")
        self.transport = transport or self._request
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.sleeper = sleeper

    @staticmethod
    def _request(url, headers, timeout):
        with urlopen(Request(url, headers=headers, method="GET"), timeout=timeout) as response:  # nosec B310: URL constants below
            return response.status, response.headers, response.read()

    def _get(self, url):
        if not self.token:
            raise UpstoxError("Set UPSTOX_ANALYTICS_TOKEN to use live ingestion")
        for attempt in range(4):
            try:
                status, headers, body = self.transport(url, {"Accept": "application/json", "Authorization": f"Bearer {self.token}"}, 30)
            except (HTTPError, URLError, TimeoutError, OSError) as error:
                status = getattr(error, "code", None)
                headers = getattr(error, "headers", {}) or {}
                body = b""
                if status not in (429, 500, 502, 503, 504) or attempt == 3:
                    raise UpstoxError(f"Upstox request failed ({status or type(error).__name__}); credentials and response details redacted") from None
            else:
                if status == 200:
                    try:
                        return json.loads(body)
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        raise UpstoxError("Upstox returned malformed JSON") from None
                if status not in (429, 500, 502, 503, 504) or attempt == 3:
                    raise UpstoxError(f"Upstox request failed (HTTP {status}); credentials and response details redacted")
            retry_after = headers.get("Retry-After", "")
            try:
                delay = min(30, max(0, int(retry_after)))
            except ValueError:
                try:
                    delay = min(30, max(0, (parsedate_to_datetime(retry_after) - _aware(self.clock())).total_seconds()))
                except (TypeError, ValueError, OverflowError):
                    delay = 2 ** attempt
            self.sleeper(delay)
        raise UpstoxError("Upstox request failed; credentials and response details redacted")

    def candles(self, instrument_key: str, start: date, end: date) -> dict:
        if not re.fullmatch(r"[A-Z0-9_]+\|[A-Za-z0-9_-]+", instrument_key):
            raise ValueError("invalid Upstox instrument key")
        if start > end or (end - start).days > 30:
            raise ValueError("5-minute historical requests must be ordered and span at most 31 calendar dates")
        url = f"{HISTORY_URL}/{quote(instrument_key, safe='')}/minutes/5/{end.isoformat()}/{start.isoformat()}"
        raw = self._get(url)
        return self._snapshot("candles", {"instrument_key": instrument_key, "unit": "minutes", "interval": 5, "from": start.isoformat(), "to": end.isoformat()}, raw)

    def news(self, instrument_keys: list[str], *, page_size: int = 100) -> list[dict]:
        if not 1 <= page_size <= 100:
            raise ValueError("news page_size must be 1..100")
        if any(not re.fullmatch(r"[A-Z0-9_]+\|[A-Za-z0-9_-]+", key) for key in instrument_keys):
            raise ValueError("invalid Upstox instrument key")
        snapshots = []
        for offset in range(0, len(dict.fromkeys(instrument_keys)), 30):
            batch = list(dict.fromkeys(instrument_keys))[offset:offset + 30]
            page = 1
            while page <= 100:
                query = urlencode({"category": "instrument_keys", "instrument_keys": ",".join(batch), "page_number": page, "page_size": page_size})
                raw = self._get(f"{NEWS_URL}?{query}")
                snapshots.append(self._snapshot("news", {"instrument_keys": batch, "page_number": page, "page_size": page_size}, raw))
                metadata = raw.get("metadata", {}).get("page", {}) if isinstance(raw, dict) else {}
                total = metadata.get("total_pages", page)
                if not isinstance(total, int) or total < page:
                    break
                if page >= min(total, 100):
                    break
                page += 1
        return snapshots

    def _snapshot(self, dataset, request, response):
        observed = _aware(self.clock())
        raw = {"source_id": "upstox", "dataset": dataset, "request": request, "observed_at": _stamp(observed), "response": response}
        return {**raw, "raw_hash": digest(raw)}


def normalize_news(snapshots: list[dict]) -> list[dict]:
    """Normalize immutable provider revisions and merge repeated instrument mappings."""
    rows, prior = [], {}
    for snapshot in snapshots:
        raw_hash = snapshot.get("raw_hash")
        if raw_hash != digest({key: value for key, value in snapshot.items() if key != "raw_hash"}):
            raise ValueError("raw snapshot hash mismatch")
        observed = _aware(snapshot["observed_at"])
        data = snapshot.get("response", {}).get("data", {})
        if not isinstance(data, dict):
            continue
        for instrument_key, articles in data.items():
            if not isinstance(articles, list):
                continue
            for article in articles:
                if not isinstance(article, dict):
                    raise ValueError("malformed article in raw news snapshot")
                url = article.get("article_link")
                title = str(article.get("heading", "")).strip()
                millis = article.get("published_time")
                if not isinstance(url, str) or not url.startswith("https://"):
                    raise ValueError("untrusted article URL in raw news snapshot")
                if not title or (millis is not None and (not isinstance(millis, (int, float)) or not math.isfinite(millis))):
                    raise ValueError("malformed article fields in raw news snapshot")
                try:
                    published = datetime.fromtimestamp(millis / 1000, timezone.utc) if millis is not None else None
                except (OverflowError, OSError, ValueError):
                    raise ValueError("unrepresentable publication time in raw news snapshot") from None
                if published and published > observed:
                    continue
                article_hash = digest(article)
                canonical_id = hashlib.sha256(url.split("#", 1)[0].rstrip("/").encode()).hexdigest()
                seen = prior.get(canonical_id, [])
                same_revision = next((row for row in seen if row["revision_id"] == article_hash), None)
                if same_revision:
                    if instrument_key not in same_revision["entities"]:
                        same_revision["entities"].append(instrument_key)
                    continue
                row = {
                    "event_id": hashlib.sha256(f"{canonical_id}:{article_hash}".encode()).hexdigest(),
                    "canonical_id": canonical_id, "source_id": "upstox_news", "source_url": url,
                    "published_at": _stamp(published) if published else None, "observed_at": _stamp(observed),
                    "available_at": _stamp(max(observed, published) if published else observed),
                    "revision_id": article_hash, "revision_of": seen[-1]["revision_id"] if seen else None,
                    "duplicate_of": None,
                    "instrument_key": instrument_key, "entities": [instrument_key], "categories": ["market_news"],
                    "verification_status": "provider_reported_unverified",
                    "title": title, "summary": str(article.get("summary", "")), "raw_hash": article_hash,
                    "evidence_refs": [{"source_url": url, "raw_hash": article_hash}],
                }
                rows.append(row)
                prior.setdefault(canonical_id, []).append(row)
    return rows


def normalize_candles(snapshot: dict) -> list[dict]:
    """Return valid completed five-minute bars; the raw provider payload stays untouched."""
    if snapshot.get("raw_hash") != digest({key: value for key, value in snapshot.items() if key != "raw_hash"}):
        raise ValueError("raw snapshot hash mismatch")
    observed = _aware(snapshot["observed_at"])
    key = snapshot.get("request", {}).get("instrument_key")
    candles = snapshot.get("response", {}).get("data", {}).get("candles", [])
    rows, seen = [], set()
    for candle in candles:
        if not isinstance(candle, list) or len(candle) < 6:
            continue
        try:
            at = _aware(candle[0])
            values = [float(value) for value in candle[1:6]]
        except (TypeError, ValueError, OverflowError):
            continue
        op, high, low, close, volume = values
        if at + timedelta(minutes=5) > observed or at in seen or not all(map(math.isfinite, values)):
            continue
        if min(op, high, low, close) <= 0 or volume < 0 or low > min(op, close) or high < max(op, close):
            continue
        seen.add(at)
        rows.append({"instrument_key": key, "at": _stamp(at), "open": op, "high": high, "low": low, "close": close, "volume": volume, "raw_hash": snapshot["raw_hash"]})
    return sorted(rows, key=lambda row: row["at"])

