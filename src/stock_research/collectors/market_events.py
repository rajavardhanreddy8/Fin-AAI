"""Opt-in RSS/Atom event ingestion with bounded, public HTTPS fetching."""
from __future__ import annotations

import hashlib
import ipaddress
import re
import socket
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit, urlunsplit

from .upstox import _stamp, _aware, digest

MAX_FEED_BYTES = 2_000_000
MAX_REDIRECTS = 5
MAX_FEED_RETRIES = 3


class FeedError(ValueError):
    pass


def validate_source(source: dict, resolver=socket.getaddrinfo) -> tuple[str, str, int]:
    if not isinstance(source, dict) or source.get("permitted") is not True:
        raise FeedError("feed source must be explicitly permitted")
    if not isinstance(source.get("source_id"), str) or not source["source_id"].strip():
        raise FeedError("feed source_id is required")
    interval = source.get("polling_interval")
    if not isinstance(interval, (int, float)) or interval <= 0:
        raise FeedError("feed polling_interval must be positive")
    url = source.get("url")
    if not isinstance(url, str) or len(url) > 2048 or any(ord(c) < 32 for c in url):
        raise FeedError("feed URL is malformed")
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username is not None or parts.password is not None or parts.fragment:
        raise FeedError("feed URL must be public HTTPS without credentials or fragment")
    try:
        port = parts.port or 443
    except ValueError:
        raise FeedError("feed URL has an invalid port") from None
    if port != 443:
        raise FeedError("feed URL must use HTTPS port 443")
    host = parts.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".lan")):
        raise FeedError("feed URL host is local or private")
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            addresses = [ipaddress.ip_address(row[4][0]) for row in resolver(host, port, type=socket.SOCK_STREAM)]
        except (OSError, ValueError, IndexError):
            raise FeedError("feed URL host did not resolve to a public address") from None
    if not addresses or any(not address.is_global for address in addresses):
        raise FeedError("feed URL host did not resolve exclusively to public addresses")
    return url, host, port


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _fetch(url: str, resolver=socket.getaddrinfo) -> bytes:
    current = url
    opener = urllib.request.build_opener(_NoRedirect)
    for _ in range(MAX_REDIRECTS + 1):
        validate_source({"source_id": "redirect", "url": current, "permitted": True, "polling_interval": 1}, resolver)
        request = urllib.request.Request(current, headers={"Accept": "application/atom+xml, application/rss+xml, application/xml, text/xml", "User-Agent": "fin-AAI-market-events/1"}, method="GET")
        try:
            with opener.open(request, timeout=15) as response:
                body = response.read(MAX_FEED_BYTES + 1)
                if len(body) > MAX_FEED_BYTES:
                    raise FeedError("feed response exceeds size limit")
                return body
        except urllib.error.HTTPError as error:
            if error.code not in (301, 302, 303, 307, 308):
                raise FeedError(f"feed request failed (HTTP {error.code})") from None
            location = error.headers.get("Location")
            if not location:
                raise FeedError("feed redirect omitted Location") from None
            current = urljoin(current, location)
        except (urllib.error.URLError, TimeoutError, OSError):
            raise FeedError("feed request failed; network details omitted") from None
    raise FeedError("feed exceeded redirect limit")


def fetch_feed(source: dict, *, transport=None, clock=None, resolver=socket.getaddrinfo) -> dict:
    url, _, _ = validate_source(source, resolver)
    observed = _aware(clock() if clock else datetime.now(timezone.utc))
    fetch = transport or (lambda target: _fetch(target, resolver))
    for attempt in range(MAX_FEED_RETRIES):
        try:
            body = fetch(url)
            break
        except FeedError:
            if attempt == MAX_FEED_RETRIES - 1:
                raise

    if not isinstance(body, bytes) or len(body) > MAX_FEED_BYTES:
        raise FeedError("feed response exceeds size limit")
    if re.search(br"<!\s*(DOCTYPE|ENTITY)\b", body, re.IGNORECASE):
        raise FeedError("XML document type and entities are disallowed")
    try:
        ET.fromstring(body)
    except ET.ParseError:
        raise FeedError("feed XML is malformed") from None
    raw = {"source_id": source["source_id"], "dataset": "rss_atom", "request": {"url": url}, "observed_at": _stamp(observed), "response": {"xml": body.decode("utf-8-sig")}}
    return {**raw, "raw_hash": digest(raw)}


def _child_text(element, name):
    found = element.find(name)
    return (found.text or "").strip() if found is not None else ""


def _date(value: str):
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        return _aware(parsed) if parsed.tzinfo else None
    except (TypeError, ValueError, OverflowError):
        try:
            return _aware(value)
        except (TypeError, ValueError, OverflowError):
            return None


def normalize_feed(snapshots: list[dict]) -> list[dict]:
    """Normalize idempotently, retaining cross-source copies and changed revisions."""
    rows, revisions = [], {}
    for snapshot in snapshots:
        if snapshot.get("raw_hash") != digest({key: value for key, value in snapshot.items() if key != "raw_hash"}):
            raise FeedError("raw snapshot hash mismatch")
        observed = _aware(snapshot["observed_at"])
        xml = snapshot.get("response", {}).get("xml", "")
        if re.search(r"<!\s*(DOCTYPE|ENTITY)\b", xml, re.IGNORECASE):
            raise FeedError("XML document type and entities are disallowed")
        try:
            root = ET.fromstring(xml)
        except ET.ParseError:
            raise FeedError("feed XML is malformed") from None
        channel = root.find("channel")
        entries = list(root.findall("item")) if channel is None else list(channel.findall("item"))
        entries += root.findall("{http://www.w3.org/2005/Atom}entry")
        for item in entries:
            title = _child_text(item, "title") or _child_text(item, "{http://www.w3.org/2005/Atom}title")
            link = _child_text(item, "link")
            atom_link = item.find("{http://www.w3.org/2005/Atom}link")
            if atom_link is not None:
                link = atom_link.attrib.get("href", link)
            identity = _child_text(item, "guid") or _child_text(item, "{http://www.w3.org/2005/Atom}id") or link
            if not identity or not title or not link or not link.startswith("https://"):
                continue
            published_raw = (_child_text(item, "pubDate") or _child_text(item, "published") or _child_text(item, "{http://www.w3.org/2005/Atom}published") or _child_text(item, "{http://www.w3.org/2005/Atom}updated"))
            published = _date(published_raw)
            if published and published > observed:
                continue
            summary = _child_text(item, "description") or _child_text(item, "{http://www.w3.org/2005/Atom}summary") or _child_text(item, "{http://www.w3.org/2005/Atom}content")
            article = {"identity": identity.strip(), "url": link.strip(), "title": title, "summary": summary, "published_at": _stamp(published) if published else None}
            content_hash = digest(article)
            canonical_url = urlunsplit((*urlsplit(link.strip())[:4], ""))
            canonical = hashlib.sha256(canonical_url.rstrip("/").encode("utf-8")).hexdigest()
            earlier = revisions.get(canonical, [])
            same_source_revision = next((prior for prior in earlier if prior["source_id"] == snapshot["source_id"] and prior["revision_id"] == content_hash), None)
            if same_source_revision:
                continue
            row = {"event_id": hashlib.sha256(f"{canonical}:{snapshot['source_id']}:{content_hash}".encode()).hexdigest(), "canonical_id": canonical,
                   "source_id": snapshot["source_id"], "source_url": article["url"], "published_at": article["published_at"],
                   "observed_at": _stamp(observed), "available_at": _stamp(max(observed, published) if published else observed),
                   "entities": [], "categories": ["market_news"], "raw_hash": content_hash,
                   "verification_status": "feed_publisher_reported_unverified", "title": title, "summary": summary,
                   "revision_id": content_hash, "revision_of": earlier[-1]["revision_id"] if earlier and earlier[-1]["revision_id"] != content_hash else None,
                   "duplicate_of": next((prior["event_id"] for prior in earlier if prior["revision_id"] == content_hash), None),
                   "evidence_refs": [{"source_url": article["url"], "raw_hash": content_hash}]}
            rows.append(row)
            revisions.setdefault(canonical, []).append(row)
    return rows

