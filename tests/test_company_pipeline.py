from stock_research.collectors.upstox import digest
from stock_research.company_pipeline import run_company_pipeline
from stock_research.context_store import ContextStore


def test_company_pipeline_preserves_snapshot_lineage_and_reports_missing_summary(tmp_path):
    url = "https://publisher.example/story"
    snapshot = {"source_id": "publisher", "dataset": "firecrawl_article", "provider": "firecrawl",
        "request": {"url": url}, "observed_at": "2026-10-20T10:00:00Z",
        "response": {"success": True, "data": {"markdown": "", "metadata": {
            "title": "Acme update", "sourceURL": url, "publishedTime": "2026-10-19T10:00:00Z"}}}}
    snapshot["raw_hash"] = digest(snapshot)
    event = {"event_id": "e1", "canonical_id": "c1", "source_id": "publisher", "source_url": url,
        "published_at": "2026-10-19T10:00:00Z", "observed_at": "2026-10-20T10:00:00Z",
        "available_at": "2026-10-20T10:00:00Z", "raw_hash": "a" * 64,
        "provider_response_hash": snapshot["raw_hash"], "title": "Acme update", "summary": "Acme announced an expansion.",
        "verification_status": "publisher_reported_unverified"}
    news_options = {"article_extract": lambda *args, **kwargs: ([snapshot], []),
        "firecrawl_urls": [url], "firecrawl_sources": [{"source_id": "publisher", "permitted": True,
            "allowed_urls": [url], "permission_basis": "test", "retention": "test", "reuse_uncertainty": "unknown"}]}
    # Keep the collector boundary deterministic while supplying both usable and unusable summaries.
    from stock_research import company_pipeline
    original = company_pipeline.collect_company_news
    company_pipeline.collect_company_news = lambda *args, **kwargs: {"events": [event, event | {
        "event_id": "e2", "summary": "", "source_url": "https://publisher.example/empty"}], "gaps": [], "snapshots": [snapshot]}
    try:
        result = run_company_pipeline(company="Acme", symbol="ACME", aliases=[], start="2026-10-19", end="2026-10-20",
            store=ContextStore(tmp_path / "context.db"), interpret=lambda doc: [], news_options=news_options)
    finally:
        company_pipeline.collect_company_news = original
    assert result["documents"] == [{"source_id": "publisher", "source_url": url,
        "published_at": event["published_at"], "observed_at": event["observed_at"],
        "raw_hash": snapshot["raw_hash"], "text": event["summary"]}]
    assert result["parsed"]["batch"]["events"] == []
    assert result["gaps"] == [{"unit": "event:e2", "reason": "summary unavailable; event was not sent for parsing"}]
