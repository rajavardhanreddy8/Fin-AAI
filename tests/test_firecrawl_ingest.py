import json
from datetime import datetime, timezone

import pytest

from stock_research.collectors.firecrawl import FirecrawlError, extract, load_registry, normalize_articles, validate_url
from stock_research.context_store import ContextStore
from stock_research.collectors.upstox import digest


URL = "https://publisher.example/article"
SOURCE = {"source_id": "publisher", "permitted": True, "allowed_urls": [URL],
          "permission_basis": "terms permit this use", "retention": "one year", "reuse_uncertainty": "training rights unknown"}


def resolver(host, port, **kwargs):
    return [(None, None, None, None, ("93.184.216.34", port))]


def provider(markdown="Article body", *, published=None, source_url=URL):
    return {"success": True, "data": {"markdown": markdown, "metadata": {"title": "Headline", "sourceURL": source_url, "publishedTime": published}}}


def transport_for(payloads, calls=None):
    calls = calls if calls is not None else []
    def transport(headers, body):
        calls.append((headers, json.loads(body)))
        item = payloads.pop(0)
        return item
    return transport


def test_registry_exact_urls_and_public_url_boundary(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps([SOURCE]))
    assert load_registry(path)[0]["allowed_urls"] == [URL]
    for value in ("http://publisher.example/story", "https://user@publisher.example/story", "https://publisher.example:444/story", "https://publisher.example.evil/story"):
        with pytest.raises(FirecrawlError):
            validate_url(value, SOURCE, resolver)
    with pytest.raises(FirecrawlError):
        validate_url(URL, SOURCE, lambda *args, **kwargs: [(None, None, None, None, ("127.0.0.1", 443))])


def test_success_keeps_provider_hash_publisher_identity_and_unknown_date():
    now = datetime(2026, 10, 17, 10, tzinfo=timezone.utc)
    snapshots, gaps = extract([URL], [SOURCE], api_key="secret", transport=transport_for([(200, {}, json.dumps(provider()).encode())]), clock=lambda: now, resolver=resolver)
    assert gaps == []
    assert len(snapshots) == 1
    assert snapshots[0]["source_id"] == "publisher" and snapshots[0]["provider"] == "firecrawl"
    event = normalize_articles(snapshots)[0]
    assert event["published_at"] is None
    assert event["available_at"] == "2026-10-17T10:00:00.000000Z"
    assert event["provider_response_hash"] == snapshots[0]["raw_hash"]
    assert event["extracted_content_hash"] == digest("Article body")


@pytest.mark.parametrize("status,reason", [(401, "authentication"), (402, "quota or rate limit"), (429, "quota or rate limit"), (503, "provider request")])
def test_auth_quota_and_provider_errors_are_redacted(status, reason):
    calls = []
    responses = [(status, {}, b"secret body")] * (3 if status in (429, 503) else 1)
    snapshots, gaps = extract([URL], [SOURCE], api_key="secret", transport=transport_for(responses, calls), resolver=resolver, sleeper=lambda _: None)
    assert snapshots == [] and reason in gaps[0]["reason"]
    assert "secret" not in json.dumps(gaps)
    assert len(calls) == (3 if status in (429, 503) else 1)


@pytest.mark.parametrize("body", [b"not json", b'{"success": false}', json.dumps({"success": True, "data": {"markdown": "", "metadata": {}}}).encode()])
def test_malformed_shape_and_empty_text_are_gaps(body):
    _, gaps = extract([URL], [SOURCE], api_key="secret", transport=transport_for([(200, {}, body)]), resolver=resolver)
    assert len(gaps) == 1


def test_attempt_and_page_bounds_and_missing_credentials():
    assert extract([URL], [SOURCE], api_key="", resolver=resolver)[1][0]["reason"] == "FIRECRAWL_API_KEY is not configured"
    with pytest.raises(FirecrawlError, match="5 pages"):
        extract([URL] * 6, [SOURCE], api_key="secret", resolver=resolver)
    calls = []
    payloads = [(429, {}, b"")] * 3
    _, gaps = extract([URL], [SOURCE], api_key="secret", transport=transport_for(payloads, calls), resolver=resolver, sleeper=lambda _: None)
    assert len(calls) == 3 and len(gaps) == 1


def test_late_extraction_cutoff_dup_import_and_changed_content_revision(tmp_path):
    timeline = iter([datetime(2026, 10, 17, 10, microsecond=1, tzinfo=timezone.utc), datetime(2026, 10, 18, 10, tzinfo=timezone.utc)])
    first, _ = extract([URL], [SOURCE], api_key="secret", transport=transport_for([(200, {}, json.dumps(provider(published="2026-10-01T00:00:00Z")).encode())]), clock=lambda: next(timeline), resolver=resolver)
    changed, _ = extract([URL], [SOURCE], api_key="secret", transport=transport_for([(200, {}, json.dumps(provider("Corrected article", published="2026-10-01T00:00:00Z")).encode())]), clock=lambda: next(timeline), resolver=resolver)
    events = normalize_articles(first + first + changed)
    assert len(events) == 2
    assert events[1]["revision_of"] == events[0]["revision_id"]
    store = ContextStore(tmp_path / "context.db")
    batch = {"events": events, "nodes": [], "claims": [], "relationships": [], "analogs": []}
    assert store.import_batch(batch)["events"] == 2
    assert store.import_batch(batch)["events"] == 0
    before = store.report("2026-10-17T10:00:00.000000Z")
    after = store.report("2026-10-17T10:00:00.000001Z")
    assert before["what_trust"]["events"] == []
    assert len(after["what_trust"]["events"]) == 1
    assert after["what_trust"]["events"][0]["summary"] == "Article body"
    later = store.report("2026-10-18T10:00:00Z")
    assert later["what_trust"]["events"][0]["summary"] == "Corrected article"


def test_cli_dry_run_needs_no_dns_credentials_or_output_writes(tmp_path, capsys):
    import importlib.util
    from pathlib import Path

    command = Path(__file__).resolve().parents[1] / "scripts" / "run_market_ingest.py"
    spec = importlib.util.spec_from_file_location("firecrawl_dry_run_cli", command)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    registry = Path(__file__).resolve().parents[1] / "config" / "firecrawl-sources.example.json"
    out = tmp_path / "must-not-exist"
    assert module.main(["--firecrawl-registry", str(registry), "--firecrawl-url", URL, "--output", str(out)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["provider_call"] is False and result["dns_resolution"] == "not checked"
    assert not out.exists()
