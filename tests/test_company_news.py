from datetime import datetime, timezone

from stock_research.collectors.company_news import collect_company_news
from stock_research.collectors.upstox import digest


NOW = datetime(2026, 10, 20, 10, tzinfo=timezone.utc)
SOURCE = {"source_id": "publisher", "permitted": True, "allowed_urls": ["https://publisher.example/story"],
          "permission_basis": "permission", "retention": "one year", "reuse_uncertainty": "unknown"}


def snapshot(body="Reliance results"):
    value = {"source_id": "publisher", "dataset": "firecrawl_article", "provider": "firecrawl",
             "request": {"url": SOURCE["allowed_urls"][0]}, "observed_at": "2026-10-20T10:00:00Z",
             "response": {"success": True, "data": {"markdown": body, "metadata": {
                 "title": "Reliance Industries results", "sourceURL": SOURCE["allowed_urls"][0],
                 "publishedTime": "2026-10-19T10:00:00Z"}}}}
    value["raw_hash"] = digest(value)
    return value


def test_company_range_and_alias_dedupe_preserves_raw_history():
    one = snapshot()
    revised = snapshot("Reliance results revised")
    calls = []
    result = collect_company_news("Reliance Industries", "RELIANCE", ["RIL"], "2026-10-19", "2026-10-20",
                                  firecrawl_urls=SOURCE["allowed_urls"], firecrawl_sources=[SOURCE],
                                  article_extract=lambda urls, sources, **kwargs: calls.append(urls) or ([one, revised], []))
    assert calls == [SOURCE["allowed_urls"]]
    assert len(result["snapshots"]) == 2
    assert len(result["events"]) == 2
    assert result["events"][1]["revision_of"] == result["events"][0]["revision_id"]
    repeated = collect_company_news("Reliance Industries", "RELIANCE", ["RIL"], "2026-10-19", "2026-10-20",
                                    firecrawl_sources=[SOURCE], prior_events=result["events"],
                                    article_extract=lambda *args, **kwargs: ([one, revised], []))
    assert repeated["events"] == []
    assert len(repeated["duplicates"]) == 2
    assert len(repeated["snapshots"]) == 2


def test_company_dates_require_ordered_valid_dates():
    import pytest
    with pytest.raises(ValueError):
        collect_company_news("A", "A", [], "2026-10-21", "2026-10-20")


def test_supplied_upstox_snapshots_are_normalized_and_filtered():
    import pytest
    from datetime import datetime, timezone

    def upstox_snapshot(items):
        value = {"source_id": "upstox", "dataset": "news", "request": {},
                 "observed_at": "2026-10-20T10:00:00Z", "response": {"data": {
                     "NSE_EQ|INE002A01018": items}}}
        value["raw_hash"] = digest(value)
        return value

    matching = {"article_link": "https://news.example/reliance", "heading": "RIL Reliance update",
                "summary": "Reliance Industries", "published_time": int(datetime(2026, 10, 19, tzinfo=timezone.utc).timestamp() * 1000)}
    unrelated = {"article_link": "https://news.example/other", "heading": "Other company", "summary": "Unrelated",
                 "published_time": int(datetime(2026, 10, 19, tzinfo=timezone.utc).timestamp() * 1000)}
    snap = upstox_snapshot([matching, unrelated])
    result = collect_company_news("Reliance Industries", "RELIANCE", ["RIL"], "2026-10-19", "2026-10-20",
                                  upstox_snapshots=[snap])
    assert len(result["events"]) == 1
    event = result["events"][0]
    assert event["title"] == "RIL Reliance update"
    assert event["published_at"] == "2026-10-19T00:00:00Z"
    assert event["observed_at"] == snap["observed_at"]
    assert event["revision_id"]
    assert len(result["snapshots"]) == 1

    corrupted = {**snap, "raw_hash": "0" * 64}
    with pytest.raises(ValueError, match="raw snapshot hash mismatch"):
        collect_company_news("Reliance Industries", "RELIANCE", ["RIL"], "2026-10-19", "2026-10-20",
                             upstox_snapshots=[corrupted])
