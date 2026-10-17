"""Bounded Firecrawl article extraction for explicitly permitted public pages."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import socket
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit

from .market_events import _NoRedirect
from .upstox import _aware, _stamp, digest

API_URL = "https://api.firecrawl.dev/v2/scrape"
MAX_PAGES = 5
MAX_ATTEMPTS = 3
MAX_RESPONSE_BYTES = 2_000_000


class FirecrawlError(ValueError):
    pass


def validate_url(url, source, resolver=socket.getaddrinfo, *, check_dns=True):
    if not isinstance(url, str) or len(url) > 2048 or any(ord(c) < 32 for c in url):
        raise FirecrawlError("article URL is malformed")
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username is not None or parts.password is not None or parts.fragment:
        raise FirecrawlError("article URL must be public HTTPS without credentials or fragment")
    try:
        port = parts.port or 443
    except ValueError:
        raise FirecrawlError("article URL has an invalid port") from None
    if port != 443:
        raise FirecrawlError("article URL must use HTTPS port 443")
    host = parts.hostname.rstrip(".").lower()
    if not isinstance(source, dict) or url not in source.get("allowed_urls", []):
        raise FirecrawlError("article URL is not exactly allowlisted for this publisher")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".lan")):
        raise FirecrawlError("article host is local or private")
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        if not check_dns:
            return url
        try:
            addresses = [ipaddress.ip_address(row[4][0]) for row in resolver(host, port, type=socket.SOCK_STREAM)]
        except (OSError, ValueError, IndexError):
            raise FirecrawlError("article host did not resolve to a public address") from None
    if not addresses or any(not ip.is_global for ip in addresses):
        raise FirecrawlError("article host did not resolve exclusively to public addresses")
    return url


def _completion_stamp(value):
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def load_registry(path):
    sources = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(sources, list):
        raise FirecrawlError("Firecrawl registry must be a JSON list")
    seen = set()
    for source in sources:
        if (not isinstance(source, dict) or type(source.get("permitted")) is not bool or not isinstance(source.get("source_id"), str)
                or not source["source_id"].strip() or source["source_id"] in seen
                or not isinstance(source.get("allowed_urls"), list) or not source["allowed_urls"]
                or not isinstance(source.get("permission_basis"), str) or not source["permission_basis"].strip()
                or not isinstance(source.get("retention"), str) or not source["retention"].strip()
                or not isinstance(source.get("reuse_uncertainty"), str) or not source["reuse_uncertainty"].strip()):
            raise FirecrawlError("each publisher requires source_id, permission, retention, reuse uncertainty, exact URLs and a permitted flag")
        seen.add(source["source_id"])
        if any(not isinstance(url, str) or not url for url in source["allowed_urls"]):
            raise FirecrawlError("publisher allowed_urls must contain exact URLs")
    return sources


def _request(url, headers, body, timeout):
    opener = urllib.request.build_opener(_NoRedirect)
    current = url
    for _ in range(1):
        request = urllib.request.Request(current, data=body, headers=headers, method="POST")
        try:
            with opener.open(request, timeout=timeout) as response:
                return response.status, response.headers, response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as error:
            if error.code not in (301, 302, 303, 307, 308):
                return error.code, error.headers, error.read(MAX_RESPONSE_BYTES + 1)
            location = error.headers.get("Location")
            if not location:
                raise FirecrawlError("Firecrawl redirect omitted Location") from None
            target = urljoin(current, location)
            raise FirecrawlError("Firecrawl API redirects are disallowed")
    raise FirecrawlError("Firecrawl API exceeded redirect limit")


def _preflight(url):
    request = urllib.request.Request(url, headers={"User-Agent": "fin-AAI-firecrawl-preflight/1"}, method="HEAD")
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=15) as response:
            status, content_type = response.status, response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as error:
        if error.code in (301, 302, 303, 307, 308):
            raise FirecrawlError("publisher URL redirects; extraction is refused") from None
        raise FirecrawlError(f"publisher preflight failed (HTTP {error.code})") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise FirecrawlError("publisher preflight failed; network details omitted") from None
    if not 200 <= status < 300 or content_type.split(";", 1)[0].strip().lower() not in ("text/html", "application/xhtml+xml"):
        raise FirecrawlError("publisher preflight did not return an HTML success response")


def extract(urls, registry, *, api_key=None, transport=None, preflight=None, clock=None, resolver=socket.getaddrinfo, sleeper=time.sleep):
    """Return immutable provider snapshots and per-URL gaps; never logs auth or response bodies."""
    if len(urls) > MAX_PAGES:
        raise FirecrawlError(f"Firecrawl is limited to {MAX_PAGES} pages per invocation")
    if len(urls) != len(set(urls)):
        raise FirecrawlError("duplicate Firecrawl URLs are not allowed in one invocation")
    if not urls:
        return [], []
    token = api_key if api_key is not None else os.environ.get("FIRECRAWL_API_KEY", "")
    if not token:
        return [], [{"unit": "firecrawl", "reason": "FIRECRAWL_API_KEY is not configured"}]
    by_domain = {}
    for source in registry:
        if source.get("permitted") is not True or not source.get("permission_basis") or not source.get("retention") or not source.get("reuse_uncertainty"):
            continue
        for allowed_url in source["allowed_urls"]:
            by_domain[allowed_url] = source
    fetch = transport or (lambda headers, body: _request(API_URL, headers, body, 30))
    check_page = preflight or (_preflight if transport is None else lambda _: None)
    snapshots, gaps = [], []
    for index, url in enumerate(urls):
        try:
            # Resolve source by exact or subdomain allowlist match, then validate the original URL.
            source = by_domain.get(url)
            if source is None or source.get("permitted") is not True:
                raise FirecrawlError("article host is not allowlisted for a permitted publisher")
            validate_url(url, source, resolver)
            check_page(url)
            payload = json.dumps({"url": url, "formats": ["markdown"], "onlyMainContent": True, "parsers": [], "proxy": "basic", "storeInCache": False}, separators=(",", ":")).encode()
            response = None
            for attempt in range(MAX_ATTEMPTS):
                try:
                    status, headers, body = fetch({"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"}, payload)
                except (urllib.error.URLError, TimeoutError, OSError):
                    if attempt == MAX_ATTEMPTS - 1:
                        raise FirecrawlError("Firecrawl request failed; network details omitted") from None
                    sleeper(2 ** attempt)
                    continue
                if not isinstance(body, bytes) or len(body) > MAX_RESPONSE_BYTES:
                    raise FirecrawlError("Firecrawl response exceeds size limit")
                if status == 200:
                    try:
                        response = json.loads(body)
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        raise FirecrawlError("Firecrawl returned malformed JSON") from None
                    break
                if status not in (429, 500, 502, 503, 504) or attempt == MAX_ATTEMPTS - 1:
                    reason = "authentication" if status in (401, 403) else "quota or rate limit" if status in (402, 429) else "provider request"
                    raise FirecrawlError(f"Firecrawl {reason} failed (HTTP {status}); credentials and response details redacted")
                sleeper(min(2 ** attempt, 4))
            if not isinstance(response, dict) or response.get("success") is not True or not isinstance(response.get("data"), dict):
                raise FirecrawlError("Firecrawl response has an invalid success/data shape")
            data = response["data"]
            markdown = data.get("markdown")
            metadata = data.get("metadata", {})
            if not isinstance(markdown, str) or not markdown.strip() or not isinstance(metadata, dict):
                raise FirecrawlError("Firecrawl returned empty article text or malformed metadata")
            if not isinstance(metadata.get("title"), str) or not metadata["title"].strip():
                raise FirecrawlError("Firecrawl article title is missing")
            final_url = metadata.get("sourceURL")
            if final_url != url or (metadata.get("url") and metadata["url"] != url):
                raise FirecrawlError("Firecrawl reported a redirected publisher URL; redirects require explicit allowlisting")
            if metadata.get("statusCode") is not None and (type(metadata["statusCode"]) is not int or not 200 <= metadata["statusCode"] < 300) or metadata.get("error"):
                raise FirecrawlError("Firecrawl returned an error page")
            completed = _aware(clock() if clock else datetime.now(timezone.utc))
            snapshot = {"source_id": source["source_id"], "dataset": "firecrawl_article", "provider": "firecrawl",
                        "request": {"url": url, "formats": ["markdown"], "onlyMainContent": True, "parsers": [], "proxy": "basic", "storeInCache": False}, "observed_at": _completion_stamp(completed),
                        "provenance": {"permission_basis": source["permission_basis"], "terms_url": source.get("terms_url"), "retention": source["retention"], "reuse_uncertainty": source["reuse_uncertainty"]},
                        "response": response, "raw_hash": ""}
            snapshot["raw_hash"] = digest({key: value for key, value in snapshot.items() if key != "raw_hash"})
            snapshots.append(snapshot)
        except (FirecrawlError, urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
            reason = str(error) if isinstance(error, FirecrawlError) else "Firecrawl request failed; network details omitted"
            gaps.append({"unit": f"firecrawl:{index + 1}", "reason": reason})
    return snapshots, gaps


def normalize_articles(snapshots, prior_events=()):
    rows = []
    revisions = {}
    for prior in prior_events:
        if prior.get("canonical_id") and prior.get("revision_id"):
            revisions.setdefault(prior["canonical_id"], []).append(prior)
    for snapshot in snapshots:
        if snapshot.get("raw_hash") != digest({key: value for key, value in snapshot.items() if key != "raw_hash"}):
            raise FirecrawlError("raw snapshot hash mismatch")
        if snapshot.get("dataset") != "firecrawl_article":
            continue
        observed = _aware(snapshot["observed_at"])
        response = snapshot.get("response", {})
        if not isinstance(response, dict) or response.get("success") is not True or not isinstance(response.get("data"), dict):
            raise FirecrawlError("Firecrawl response has an invalid success/data shape")
        data, metadata = response["data"], response["data"].get("metadata", {})
        body = data.get("markdown")
        if not isinstance(body, str) or not body.strip() or not isinstance(metadata, dict):
            raise FirecrawlError("Firecrawl returned empty article text or malformed metadata")
        url = snapshot.get("request", {}).get("url")
        final_url = metadata.get("sourceURL")
        if final_url != url or (metadata.get("url") and metadata["url"] != url):
            raise FirecrawlError("Firecrawl reported a redirected publisher URL; redirects require explicit allowlisting")
        if metadata.get("statusCode") is not None and (type(metadata["statusCode"]) is not int or not 200 <= metadata["statusCode"] < 300) or metadata.get("error"):
            raise FirecrawlError("Firecrawl returned an error page")
        if not isinstance(url, str) or not isinstance(final_url, str):
            raise FirecrawlError("Firecrawl article URL is missing")
        title = metadata.get("title") if isinstance(metadata.get("title"), str) else ""
        if not title.strip():
            raise FirecrawlError("Firecrawl article title is missing")
        published_raw = metadata.get("publishedTime")
        try:
            published = _aware(published_raw) if published_raw else None
        except (TypeError, ValueError, OverflowError):
            published = None
        if published and published > observed:
            published = None
        body_hash = digest(body)
        revision_hash = digest({"body_hash": body_hash, "title": title, "published_at": _stamp(published) if published else None})
        canonical_id = hashlib.sha256(url.split("#", 1)[0].rstrip("/").encode()).hexdigest()
        older = revisions.get(canonical_id, [])
        if any(item["revision_id"] == revision_hash for item in older):
            continue
        event_id = hashlib.sha256(f"{canonical_id}:{snapshot['source_id']}:{revision_hash}".encode()).hexdigest()
        completed = _completion_stamp(observed)
        rows.append({"event_id": event_id, "canonical_id": canonical_id, "source_id": snapshot["source_id"], "source_url": url,
                     "provider": "firecrawl", "published_at": _stamp(published) if published else None,
                     "observed_at": completed, "available_at": completed, "entities": [],
                     "categories": ["market_news"], "raw_hash": revision_hash,
                     "provider_response_hash": snapshot["raw_hash"], "extracted_content_hash": body_hash,
                     "verification_status": "publisher_reported_unverified", "title": title, "summary": body,
                     "revision_id": revision_hash, "revision_of": older[-1]["revision_id"] if older else None,
                     "duplicate_of": None,
                     "evidence_refs": [{"source_url": url, "raw_hash": body_hash}],
                     "extraction_completed_at": completed})
        revisions.setdefault(canonical_id, []).append(rows[-1])
    return rows
