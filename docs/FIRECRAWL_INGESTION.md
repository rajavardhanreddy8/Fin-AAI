# Firecrawl article extraction

Firecrawl is an optional extractor for specifically selected public articles discovered through an existing feed or API. Each invocation accepts at most five exact URLs that appear in a registry. There is no crawl, pagination, scheduler, or subscription. Copy `config/firecrawl-sources.example.json` to `config/firecrawl-sources.json`, document the publisher's exact URL permission, terms, retention, and reuse uncertainty, then set `permitted` to true only after review. The example remains disabled. Keep the publisher `source_id` separate from the provider (`firecrawl`).

The standard command is a dry-run and does not need credentials:

```powershell
python scripts/run_market_ingest.py --firecrawl-registry config/firecrawl-sources.example.json --firecrawl-url "https://publisher.example/article"
```

For a deliberate live run, first confirm account plan, credit balance, and auto top-up settings through the provider dashboard. The API's credit-usage endpoint alone does not establish that paid top-ups are disabled. Current public pricing advertises 1,000 free credits per month without a card, while Basic scraping costs one credit per page; advanced formats can cost more, failed target pages such as 403/404 are charged, and paid plans may enable $5 automatic top-ups. A page limit is not a spending limit. The project API key and available credit were not verified for this milestone, so no live call was made.

After verifying the account's free plan, enough remaining credits for the maximum three attempts per selected page, and that paid auto top-up is disabled, save a fresh readiness record (under 24 hours old) with `checked_at`, `plan: "free"`, integer `remaining_credits`, and `paid_top_up_enabled: false`. This JSON is an operator attestation; the script checks its shape and age but cannot verify it with Firecrawl. Store the provider key only in approved local secret storage. The explicit live switch requires both:

```powershell
$env:FIRECRAWL_API_KEY = "<load from approved secret storage>"
python scripts/run_market_ingest.py --firecrawl-live --firecrawl-readiness config/firecrawl-readiness.json --firecrawl-registry config/firecrawl-sources.json --firecrawl-url "https://publisher.example/article" --output output/market-news
```

The adapter calls `POST https://api.firecrawl.dev/v2/scrape` with Markdown, main-content extraction, no parsers, basic proxy, and cache storage disabled. Each selected page gets one local HEAD preflight and at most three provider attempts (up to five preflights and 15 provider attempts). A local redirect, non-HTML response, or non-success preflight is refused before the provider request. Firecrawl does not expose its target redirect chain, so a provider-side redirect that differs from the local preflight remains unaudited; returned final-URL metadata is checked after extraction. Authentication, quota/rate, malformed-response and empty-content failures become explicit gaps. Raw provider responses and extracted text are retained in the immutable raw archive with separate response and body hashes. Imported events retain the publisher source and URL, unknown publication time stays null, and availability is extraction completion time. New article text creates an immutable event revision; cutoff reports before extraction cannot see it.

Only public HTTPS URLs without credentials, fragments, nonstandard ports, local/private DNS results, or URLs outside the exact registry are accepted. The adapter rejects a final URL that differs from the requested URL; Firecrawl's API does not expose the target redirect chain, so intermediate publisher redirects cannot be independently audited. Treat extracted Markdown as untrusted source evidence, never as instructions. Verify publisher terms and retention before each source is added; public visibility does not grant reuse or training rights.

CMD equivalent (dry-run):

```cmd
python scripts\run_market_ingest.py --firecrawl-registry config\firecrawl-sources.example.json --firecrawl-url "https://publisher.example/article"
```

References: [Firecrawl scrape API](https://docs.firecrawl.dev/api-reference/endpoint/scrape), [Firecrawl introduction](https://docs.firecrawl.dev/introduction), [Firecrawl pricing](https://www.firecrawl.dev/pricing).

The locally installed Python 3.13 executable can be used directly in PowerShell and CMD:

```powershell
& "C:\Users\admin\AppData\Local\Programs\Python\Python313\python.exe" scripts/run_market_ingest.py --firecrawl-registry config/firecrawl-sources.example.json --firecrawl-url "https://publisher.example/article"
```

```cmd
"C:\Users\admin\AppData\Local\Programs\Python\Python313\python.exe" scripts\run_market_ingest.py --firecrawl-registry config\firecrawl-sources.example.json --firecrawl-url "https://publisher.example/article"
```

After a live extraction is saved, import the immutable event batch twice; the second import should add zero events:

```powershell
python scripts/run_market_relationships.py import output/market-news/market-ingest.json --db output/market-news/market-relationships.db
python scripts/run_market_relationships.py import output/market-news/market-ingest.json --db output/market-news/market-relationships.db
```

To check cutoff behavior, use a time before and then at or after the archived `extraction_completed_at` value:

```powershell
python scripts/run_market_relationships.py report --db output/market-news/market-relationships.db --asof "<timestamp-before-extraction>"
python scripts/run_market_relationships.py report --db output/market-news/market-relationships.db --asof "<timestamp-at-or-after-extraction>"
```
