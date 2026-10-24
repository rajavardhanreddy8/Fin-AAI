from datetime import date, datetime, timezone
from io import BytesIO
import json
from urllib.error import HTTPError

import pytest

from stock_research.collectors.upstox import UpstoxClient, UpstoxError, digest, normalize_candles, normalize_news


NOW = datetime(2026, 10, 15, 10, tzinfo=timezone.utc)
KEY = "NSE_EQ|INE040H01021"


def snapshot(article, observed=NOW):
    raw = {"source_id": "upstox", "dataset": "news", "request": {}, "observed_at": observed.isoformat().replace("+00:00", "Z"), "response": {"status": "success", "data": {KEY: [article]}}}
    return {**raw, "raw_hash": digest(raw)}


def article(**overrides):
    return {"heading": "Results", "summary": "Quarterly results", "article_link": "https://news.example/a/", "published_time": int(datetime(2026, 10, 15, 9, tzinfo=timezone.utc).timestamp() * 1000), **overrides}


def test_fixture_normalization_is_deterministic_aware_and_preserves_duplicate_revision():
    original = snapshot(article())
    changed = snapshot(article(summary="Updated summary"))
    rows = normalize_news([original, original, changed])
    assert len(rows) == 2
    assert rows[1]["revision_of"] == rows[0]["revision_id"]
    assert rows[0]["available_at"] == NOW.isoformat().replace("+00:00", "Z")
    assert datetime.fromisoformat(rows[0]["published_at"].replace("Z", "+00:00")).tzinfo
    assert normalize_news([original]) == normalize_news([original])


def test_future_and_unsafe_news_are_rejected_and_hash_is_verified():
    future = article(published_time=int(datetime(2026, 10, 15, 11, tzinfo=timezone.utc).timestamp() * 1000))
    unsafe = article(article_link="http://news.example/a")
    assert normalize_news([snapshot(future)]) == []
    with pytest.raises(ValueError, match="untrusted article URL"):
        normalize_news([snapshot(unsafe)])
    corrupted = snapshot(article())
    corrupted["response"]["data"][KEY][0]["heading"] = "Tampered"
    with pytest.raises(ValueError, match="hash"):
        normalize_news([corrupted])


@pytest.mark.parametrize("bad_article", [None, {"heading": "Bad", "summary": "", "article_link": "https://news.example/a", "published_time": 10**100}])
def test_malformed_news_rows_fail_explicitly_and_raw_snapshot_remains_available(bad_article):
    snap = snapshot(article())
    snap["response"]["data"][KEY] = [bad_article]
    snap["raw_hash"] = digest({key: value for key, value in snap.items() if key != "raw_hash"})
    with pytest.raises(ValueError, match="raw news snapshot"):
        normalize_news([snap])
    assert snap["response"]["data"][KEY] == [bad_article]


def test_unknown_news_publication_time_stays_null():
    row = normalize_news([snapshot(article(published_time=None))])[0]
    assert row["published_at"] is None
    assert row["available_at"] == NOW.isoformat().replace("+00:00", "Z")


def test_candles_fixed_endpoint_and_news_pagination_batches():
    urls = []
    responses = [
        {"status": "success", "data": {"candles": [["2026-10-15T09:15:00+05:30", 1, 2, 1, 2, 10, 0]]}},
        {"status": "success", "data": {KEY: []}, "metadata": {"page": {"total_pages": 2}}},
        {"status": "success", "data": {KEY: []}, "metadata": {"page": {"total_pages": 2}}},
    ]

    def transport(url, headers, timeout):
        assert headers["Authorization"] == "Bearer dummy"
        urls.append(url)
        return 200, {}, json.dumps(responses.pop(0)).encode()

    client = UpstoxClient("dummy", transport=transport, clock=lambda: NOW)
    candle = client.candles(KEY, date(2026, 10, 1), date(2026, 10, 15))
    assert candle["raw_hash"] == digest({key: value for key, value in candle.items() if key != "raw_hash"})
    assert len(normalize_candles(candle)) == 1
    client.news([KEY], page_size=50)
    assert "/v3/historical-candle/" in urls[0] and "/minutes/5/" in urls[0]
    assert "page_number=1" in urls[1] and "page_number=2" in urls[2]
    assert all(url.startswith(("https://api.upstox.com/v2/news?", "https://api.upstox.com/v3/historical-candle/")) for url in urls)


def test_candles_drop_future_incomplete_duplicate_and_invalid_rows():
    rows = [["2026-10-15T10:00:00+00:00", 1, 2, 1, 2, 4, 0],
            ["2026-10-15T09:50:00+00:00", 1, 2, 1, 2, 4, 0],
            ["2026-10-15T09:50:00+00:00", 1, 2, 1, 2, 4, 0],
            ["2026-10-15T09:45:00+00:00", 1, 1, 2, 2, 4, 0]]
    raw = {"source_id": "upstox", "dataset": "candles", "request": {"instrument_key": KEY}, "observed_at": NOW.isoformat().replace("+00:00", "Z"), "response": {"data": {"candles": rows}}}
    snap = {**raw, "raw_hash": digest(raw)}
    assert len(normalize_candles(snap)) == 1


def test_missing_token_and_redacted_http_failure():
    with pytest.raises(UpstoxError, match="UPSTOX_ANALYTICS_TOKEN"):
        UpstoxClient("")._get("https://api.upstox.com/v2/news")

    client = UpstoxClient("SECRET", transport=lambda *_: (401, {}, b"SECRET"))
    with pytest.raises(UpstoxError) as error:
        client._get("https://api.upstox.com/v2/news")
    assert "SECRET" not in str(error.value)


def test_cloudflare_1010_tuple_is_static_and_not_retried_but_generic_403_is_generic():
    body = b'{"error_code":1010,"error_name":"browser_signature_banned","detail":"SECRET raw provider response"}'
    calls = []
    client = UpstoxClient("SECRET", transport=lambda *_: (calls.append(1) or (403, {}, body)))
    with pytest.raises(UpstoxError, match="Cloudflare error 1010.*browser signature.*contact Upstox support") as error:
        client._get("https://api.upstox.com/v2/news")
    assert len(calls) == 1
    assert "SECRET" not in str(error.value) and "raw provider response" not in str(error.value)

    generic = UpstoxClient("SECRET", transport=lambda *_: (403, {}, b'{"error_code":403,"detail":"browser signature"}'))
    with pytest.raises(UpstoxError, match="HTTP 403") as generic_error:
        generic._get("https://api.upstox.com/v2/news")
    assert "Cloudflare" not in str(generic_error.value)

    mismatched = UpstoxClient("SECRET", transport=lambda *_: (403, {}, b'{"error_code":1010,"error_name":"other_error"}'))
    with pytest.raises(UpstoxError, match="HTTP 403") as mismatched_error:
        mismatched._get("https://api.upstox.com/v2/news")
    assert "Cloudflare" not in str(mismatched_error.value)


def test_cloudflare_1010_urllib_http_error_reads_bounded_body_and_is_not_retried():
    calls = []
    body = b'{"error_code":1010,"error_name":"browser_signature_banned","detail":"SECRET raw provider response"}'

    class BoundedBody(BytesIO):
        read_size = None

        def read(self, size=-1):
            self.read_size = size
            return super().read(size)

    response_body = BoundedBody(body)

    def request(*_):
        calls.append(1)
        raise HTTPError("https://api.upstox.com/v2/news", 403, "Forbidden", {}, response_body)

    client = UpstoxClient("SECRET", transport=request)
    with pytest.raises(UpstoxError, match="Cloudflare error 1010.*browser signature.*contact Upstox support") as error:
        client._get("https://api.upstox.com/v2/news")
    assert len(calls) == 1
    assert response_body.read_size == 8192
    assert "SECRET" not in str(error.value) and "raw provider response" not in str(error.value)


def test_retry_after_http_date_uses_timezone_aware_clock_and_is_bounded():
    calls, delays = [], []
    def transport(*_):
        calls.append(1)
        return (503, {"Retry-After": "Thu, 15 Oct 2026 10:00:05 GMT"}, b"") if len(calls) == 1 else (200, {}, b'{"ok":true}')
    client = UpstoxClient("dummy", transport=transport, clock=lambda: NOW, sleeper=delays.append)
    assert client._get("https://api.upstox.com/v2/news") == {"ok": True}
    assert delays == [5]


def test_candle_at_exact_completion_boundary_is_accepted():
    snap = {"source_id": "upstox", "dataset": "candles", "request": {"instrument_key": KEY}, "observed_at": "2026-10-15T10:00:00Z",
            "response": {"data": {"candles": [["2026-10-15T09:55:00Z", 1, 2, 1, 2, 5]]}}}
    snap["raw_hash"] = digest(snap)
    assert len(normalize_candles(snap)) == 1
