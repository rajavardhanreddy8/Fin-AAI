from datetime import datetime, timezone
import socket

import pytest

from stock_research.collectors.market_events import FeedError, fetch_feed, normalize_feed, validate_source
from stock_research.collectors.upstox import digest


NOW = datetime(2026, 10, 15, 10, tzinfo=timezone.utc)
SOURCE = {"source_id": "licensed-feed", "url": "https://feed.example/rss", "permitted": True, "polling_interval": 60}
PUBLIC = lambda host, port, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]


def test_rss_atom_timestamps_unknown_and_revision_duplicate():
    rss = b'''<rss><channel><item><title>Results</title><link>https://publisher.example/a</link><guid>a</guid><pubDate>Thu, 15 Oct 2026 09:00:00 +0000</pubDate><description>First</description></item><item><title>No date</title><link>https://publisher.example/b</link><guid>b</guid></item></channel></rss>'''
    first = fetch_feed(SOURCE, transport=lambda _: rss, clock=lambda: NOW, resolver=PUBLIC)
    changed = rss.replace(b"First", b"Revised")
    second = fetch_feed(SOURCE, transport=lambda _: changed, clock=lambda: NOW, resolver=PUBLIC)
    rows = normalize_feed([first, first, second])
    assert len(rows) == 3
    assert rows[0]["published_at"] == "2026-10-15T09:00:00Z"
    assert rows[1]["published_at"] is None
    assert rows[1]["available_at"] == "2026-10-15T10:00:00Z"
    assert rows[2]["revision_of"] == rows[0]["revision_id"]

    syndicated = {**first, "source_id": "second-permitted-feed"}
    syndicated["raw_hash"] = digest({k: v for k, v in syndicated.items() if k != "raw_hash"})
    copies = normalize_feed([first, syndicated])
    assert len(copies) == 4
    assert copies[2]["duplicate_of"] == copies[0]["event_id"]

    atom = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Atom</title><id>tag:example,1</id><link href="https://publisher.example/c"/><published>2026-10-15T11:00:00Z</published></entry></feed>'''
    assert normalize_feed([fetch_feed(SOURCE, transport=lambda _: atom, clock=lambda: NOW, resolver=PUBLIC)]) == []


def test_repeated_observation_keeps_earliest_event_and_changed_content_is_revision():
    rss = b'''<rss><channel><item><title>Results</title><link>https://publisher.example/a</link><guid>a</guid><pubDate>Thu, 15 Oct 2026 09:00:00 +0000</pubDate><description>First</description></item></channel></rss>'''
    first = fetch_feed(SOURCE, transport=lambda _: rss, clock=lambda: NOW, resolver=PUBLIC)
    later_time = datetime(2026, 10, 16, 10, tzinfo=timezone.utc)
    later = {**first, "observed_at": later_time.isoformat().replace("+00:00", "Z")}
    later["raw_hash"] = digest({key: value for key, value in later.items() if key != "raw_hash"})
    revised = fetch_feed(SOURCE, transport=lambda _: rss.replace(b"First", b"Revised"), clock=lambda: later_time, resolver=PUBLIC)

    rows = normalize_feed([first, later, revised])
    assert len(rows) == 2
    assert rows[0]["available_at"] == "2026-10-15T10:00:00Z"
    assert rows[0]["observed_at"] == "2026-10-15T10:00:00Z"
    assert rows[1]["event_id"] != rows[0]["event_id"]
    assert rows[1]["revision_of"] == rows[0]["revision_id"]


@pytest.mark.parametrize("url", ["http://feed.example/rss", "https://user:pass@feed.example/rss", "https://127.0.0.1/feed", "https://localhost/feed", "https://feed.example:444/rss", "file:///tmp/feed"])
def test_source_url_policy_rejects_unsafe_urls(url):
    with pytest.raises(FeedError):
        validate_source({**SOURCE, "url": url}, PUBLIC)


def test_registry_permission_redirect_dns_xml_and_size_are_checked():
    with pytest.raises(FeedError, match="permitted"):
        validate_source({**SOURCE, "permitted": False}, PUBLIC)
    with pytest.raises(FeedError, match="public addresses"):
        validate_source(SOURCE, lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.2", 443))])
    with pytest.raises(FeedError, match="entities"):
        fetch_feed(SOURCE, transport=lambda _: b"<!DOCTYPE x [<!ENTITY a 'b'>]><rss/>", clock=lambda: NOW, resolver=PUBLIC)
    with pytest.raises(FeedError, match="size"):
        fetch_feed(SOURCE, transport=lambda _: b" " * 2_000_001, clock=lambda: NOW, resolver=PUBLIC)
