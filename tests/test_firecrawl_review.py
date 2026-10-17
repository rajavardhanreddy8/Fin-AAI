import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from stock_research.collectors.firecrawl import API_URL, FirecrawlError, _request, extract, normalize_articles, validate_url
from stock_research.collectors.upstox import digest


URL = "https://publisher.example/story"
SOURCE = {"source_id": "publisher", "permitted": True, "allowed_urls": [URL],
          "permission_basis": "terms permit this use", "retention": "one year",
          "reuse_uncertainty": "terms do not specify model training rights"}


def resolver(host, port, **kwargs):
    return [(None, None, None, None, ("93.184.216.34", port))]


def snapshot_at(body, completed, title="Headline"):
    response = {"success": True, "data": {"markdown": body, "metadata": {
        "title": title, "sourceURL": URL, "publishedTime": "2026-10-01T00:00:00Z"}}}
    snapshot = {"source_id": "publisher", "dataset": "firecrawl_article", "provider": "firecrawl",
                "request": {"url": URL}, "observed_at": completed.isoformat().replace("+00:00", "Z"),
                "response": response}
    snapshot["raw_hash"] = digest(snapshot)
    return snapshot


def load_command():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_market_ingest.py"
    spec = importlib.util.spec_from_file_location("firecrawl_review_command", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_repeated_late_extraction_is_one_immutable_revision_and_title_changes_are_revisions():
    first = snapshot_at("Article text", datetime(2026, 10, 17, 10, tzinfo=timezone.utc))
    repeated = snapshot_at("Article text", datetime(2026, 10, 18, 10, tzinfo=timezone.utc))
    corrected = snapshot_at("Article text", datetime(2026, 10, 19, 10, tzinfo=timezone.utc), "Corrected headline")

    events = normalize_articles([first, repeated, corrected])

    assert len(events) == 2
    assert events[0]["available_at"].startswith("2026-10-17T10:00:00")
    assert events[1]["revision_of"] == events[0]["revision_id"]
    assert events[0]["extracted_content_hash"] == events[1]["extracted_content_hash"]


def test_firecrawl_only_plan_dry_run_preserves_existing_output_and_never_calls_provider(tmp_path, monkeypatch):
    module = load_command()
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps([SOURCE]), encoding="utf-8")
    output = tmp_path / "canonical"
    output.mkdir()
    prior_artifact = output / "market-ingest.json"
    prior_artifact.write_text('{"status":"prior"}\n', encoding="utf-8")
    prior_checkpoint = output / "checkpoint.json"
    prior_checkpoint.write_text('{"snapshots":["prior"]}\n', encoding="utf-8")

    monkeypatch.setattr(module, "validate_firecrawl_url", lambda *args, **kwargs: URL)
    monkeypatch.setattr(module, "firecrawl_extract", lambda *args: (_ for _ in ()).throw(AssertionError("dry-run called provider")))

    result = module.main(["--firecrawl-registry", str(registry), "--firecrawl-url", URL,
                          "--output", str(output), "--dry-run"])

    assert result == 0
    assert prior_artifact.read_text(encoding="utf-8") == '{"status":"prior"}\n'
    assert prior_checkpoint.read_text(encoding="utf-8") == '{"snapshots":["prior"]}\n'


def test_provider_redirect_metadata_is_rejected_before_snapshot_creation():
    payload = {"success": True, "data": {"markdown": "Article", "metadata": {
        "title": "Headline", "sourceURL": "https://publisher.example/redirected-story", "statusCode": 200}}}
    snapshots, gaps = extract([URL], [SOURCE], api_key="secret",
                              transport=lambda headers, body: (200, {}, json.dumps(payload).encode()),
                              preflight=lambda _: None, clock=lambda: datetime(2026, 10, 17, tzinfo=timezone.utc), resolver=resolver)

    assert snapshots == []
    assert "redirected" in gaps[0]["reason"]


def test_dns_free_dry_run_still_enforces_exact_url_allowlist():
    with pytest.raises(FirecrawlError, match="exactly allowlisted"):
        validate_url("https://publisher.example/unlisted", SOURCE, check_dns=False)


def test_extract_rejects_unpermitted_registry_entry_before_provider_call():
    calls = []
    unpermitted = {**SOURCE, "permitted": False}
    snapshots, gaps = extract([URL], [unpermitted], api_key="secret",
                              transport=lambda *args: calls.append(args), preflight=lambda _: None, resolver=resolver)

    assert snapshots == []
    assert not calls
    assert gaps


def test_preflight_redirect_aborts_before_provider_request():
    calls = []
    snapshots, gaps = extract([URL], [SOURCE], api_key="secret",
                              transport=lambda *args: calls.append(args),
                              preflight=lambda _: (_ for _ in ()).throw(FirecrawlError("publisher URL redirects; extraction is refused")),
                              resolver=resolver)

    assert snapshots == []
    assert "redirects" in gaps[0]["reason"]
    assert calls == []


def test_api_redirect_is_rejected_without_following_or_forwarding_key(monkeypatch):
    calls = []
    class Opener:
        def open(self, request, timeout):
            calls.append(request)
            raise __import__("urllib.error").error.HTTPError(
                API_URL, 302, "redirect", {"Location": "https://api.firecrawl.dev/v2/elsewhere"}, None)
    monkeypatch.setattr("urllib.request.build_opener", lambda *args: Opener())

    with pytest.raises(FirecrawlError, match="redirects are disallowed"):
        _request(API_URL, {"Authorization": "Bearer secret"}, b"{}", 30)
    assert len(calls) == 1


def test_five_pages_and_three_attempts_per_page_bound_total_attempts():
    urls = [f"https://publisher.example/story-{index}" for index in range(5)]
    source = {**SOURCE, "allowed_urls": urls}
    calls = []
    snapshots, gaps = extract(urls, [source], api_key="secret",
                              transport=lambda *args: calls.append(args) or (500, {}, b""),
                              preflight=lambda _: None, resolver=resolver, sleeper=lambda _: None)

    assert snapshots == []
    assert len(gaps) == 5
    assert len(calls) == 15


def test_firecrawl_only_live_run_keeps_prior_checkpoint_evidence_and_reimports_idempotently(tmp_path, monkeypatch):
    from stock_research.context_store import ContextStore

    module = load_command()
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps([SOURCE]), encoding="utf-8")
    output = tmp_path / "market-news"
    output.mkdir()
    feed_xml = (f'<rss><channel><item><title>Headline only</title><link>{URL}</link>'
                '<guid>headline-event</guid></item></channel></rss>')
    prior = {"source_id": "publisher", "dataset": "rss_atom", "request": {"url": "https://publisher.example/rss"},
             "observed_at": "2026-10-17T09:00:00Z", "response": {"xml": feed_xml}}
    prior["raw_hash"] = digest(prior)
    checkpoint = {"request": {"keys": [], "from": "None", "to": "None", "feeds": "old-registry-digest"},
                  "snapshots": [prior], "completed": ["feed:publisher"], "gaps": []}
    (output / "checkpoint.json").write_text(json.dumps(checkpoint), encoding="utf-8")
    now = datetime.now(timezone.utc)
    readiness = tmp_path / "readiness.json"
    readiness.write_text(json.dumps({"checked_at": now.isoformat(), "plan": "free",
                                     "paid_top_up_enabled": False, "remaining_credits": 3}), encoding="utf-8")
    extracted = snapshot_at("Extracted article body", now)
    provider_calls = []
    monkeypatch.setattr(module, "validate_firecrawl_url", lambda *args, **kwargs: URL)
    monkeypatch.setattr(module, "firecrawl_extract", lambda *args: provider_calls.append(args) or ([extracted], []))

    args = ["--firecrawl-registry", str(registry), "--firecrawl-url", URL, "--firecrawl-live",
            "--firecrawl-readiness", str(readiness), "--output", str(output)]
    assert module.main(args) == 0
    first = json.loads((output / "market-ingest.json").read_text(encoding="utf-8"))
    assert any(item["dataset"] == "rss_atom" for item in first["snapshots"])
    assert any(item["dataset"] == "firecrawl_article" for item in first["snapshots"])
    assert len(first["events"]) == 2
    feed_event = next(event for event in first["events"] if event["summary"] == "")
    article_event = next(event for event in first["events"] if event["summary"] == "Extracted article body")
    assert article_event["revision_of"] == feed_event["revision_id"]

    assert module.main(args) == 0
    second = json.loads((output / "market-ingest.json").read_text(encoding="utf-8"))
    assert second["snapshots"] == first["snapshots"]
    assert len(provider_calls) == 1
    store = ContextStore(tmp_path / "context.db")
    batch = {"events": second["events"], "nodes": [], "claims": [], "relationships": [], "analogs": []}
    assert store.import_batch(batch)["events"] == 2
    assert store.import_batch(batch)["events"] == 0


def test_failed_firecrawl_refresh_preserves_prior_snapshot_and_reports_partial(tmp_path, monkeypatch):
    module = load_command()
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps([SOURCE]), encoding="utf-8")
    output = tmp_path / "market-news"
    output.mkdir()
    now = datetime.now(timezone.utc)
    prior = snapshot_at("Previously extracted article", now)
    checkpoint = {"request": {"keys": [], "from": "None", "to": "None", "feeds": None},
                  "snapshots": [prior], "completed": ["firecrawl:" + URL], "gaps": []}
    (output / "checkpoint.json").write_text(json.dumps(checkpoint), encoding="utf-8")
    readiness = tmp_path / "readiness.json"
    readiness.write_text(json.dumps({"checked_at": now.isoformat(), "plan": "free",
                                     "paid_top_up_enabled": False, "remaining_credits": 3}), encoding="utf-8")
    monkeypatch.setattr(module, "validate_firecrawl_url", lambda *args, **kwargs: URL)
    monkeypatch.setattr(module, "firecrawl_extract", lambda *args: ([], [{"unit": "firecrawl:1", "reason": "provider quota"}]))

    result = module.main(["--firecrawl-registry", str(registry), "--firecrawl-url", URL, "--firecrawl-live",
                          "--firecrawl-readiness", str(readiness), "--refresh", "--output", str(output)])

    assert result == 2
    saved = json.loads((output / "market-ingest.json").read_text(encoding="utf-8"))
    assert saved["status"] == "partial"
    assert saved["coverage"]["gaps"] == [{"unit": "firecrawl:" + URL, "reason": "provider quota"}]
    assert saved["snapshots"] == [prior]
