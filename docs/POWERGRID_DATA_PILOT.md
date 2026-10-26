# POWERGRID data pilot

Selected on 2026-10-24 Asia/Kolkata for company-news research and paper evaluation. This selects a research subject; it does not change the NIFTYBEES trading instrument or authorize a trade.

- Company: Power Grid Corporation of India Limited
- NSE symbol: POWERGRID
- ISIN: INE752E01010
- Upstox instrument key: NSE_EQ|INE752E01010
- Aliases for company filtering: POWERGRID, PGCIL, Power Grid Corporation, Power Grid Corporation of India Limited
- Identity evidence: [official exchange filing](https://nsearchives.nseindia.com/corporate/ixbrl/INTEGRATED_FILING_INDAS_182974_05082026225714_iXBRL_WEB.html).

## Source readiness

| Data | Source | Current evidence and next gate |
| --- | --- | --- |
| Policy news | Existing permitted PIB RSS registry | Local archive has 238 event records at 2026-10-24T05:30:03Z. Exact company-name/alias scan finds zero POWERGRID matches. General policy records are not company-impact evidence. |
| Company news | Upstox News API | Adapter and saved token exist. Live request is blocked by HTTP 403 / Cloudflare 1010. Once provider access is restored, verify token authentication and one company response. Retention/training rights remain unconfirmed. |
| Five-minute prices | Upstox historical candles | Same HTTP 403 / Cloudflare 1010 on a single POWERGRID session request. No POWERGRID bars were acquired in this check. |
| Issuer announcements | [POWERGRID press releases](https://www.powergrid.in/en/press-release) | Reviewed as a source candidate only. No automated collection permission was established. |
| Results and financial statements | [POWERGRID annual results](https://www.powergrid.in/en/annual-results) | Reviewed as a source candidate only. Do not treat website availability as a training-data license. |

## Archived-news audit, 26 October 2026

The local catalog and dataset manifest contain **17** dated publisher records, correcting an earlier planning count of 18. Their URL, title, capture hash and manifest bindings all validate; no duplicate URL or captured-content hash was found. Every record was observed retrospectively on 25 October 2026 and stores selected excerpts rather than a full licensed article. None is eligible as a historical decision-time feature or a training record because retention, redistribution and model-training rights are unestablished. The full audit is at `output/company-news-gap/20261026/audit-v1.json`.

POWERGRID's own [press-release archive](https://www.powergrid.in/en/press-release), [meetings/notices archive](https://www.powergrid.in/en/meetingsnotices), [annual-results archive](https://www.powergrid.in/en/annual-results), and [financial-presentations archive](https://www.powergrid.in/en/financials-presentations) provide dated primary-document candidates across the needed period. They are discovery and manual-review channels until their automated retrieval and retention terms are recorded. Primary status does not itself create a training-data license.

Upstox's [Analytics Token documentation](https://upstox.com/developer/api-documentation/analytics-token/) documents free read-only news and historical access without a static IP, with one-year token validity. Its [News API](https://upstox.com/developer/api-documentation/get-news/) supplies only the preceding seven days; this is not a five-year news archive.

## Verified access diagnosis

The local `.env.local` contains a nonempty `UPSTOX_ANALYTICS_TOKEN`. It has no saved Bearer prefix, surrounding quotes or whitespace. A decoded, unverified expiry field is in the future; this does not verify the token signature, scope, revocation status or provider acceptance.

Read-only news, historical candles and market-status probes returned HTTP 403. The gateway's JSON reports `error_code=1010`, `error_name=browser_signature_banned`, `retryable=false` and `owner_action_required=true`. The reported reason is a browser-signature access block. Requests stopped after diagnosis. No user-agent spoofing, proxy change or alternate hosting route was used.

[Cloudflare's resolution](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-1xxx-errors/error-1010/) is to notify the site owner. Use [Upstox support](https://upstox.com/contact-us/) with the endpoint, date/time and error 1010; do not send the token. Provider-approved access must be restored before retesting authentication.

AWS `fin-aai` identity verification succeeded on 2026-10-24. AWS authentication and this provider access restriction are separate. Firebase is not needed to diagnose the provider block or run the existing local SQLite evidence pipeline.

## Next acceptance check

1. Record a source-specific permission and retention decision for the POWERGRID primary-document archives; do not scrape or train on them until then.
2. Obtain provider-approved access to the documented Upstox API endpoints.
3. Recheck one POWERGRID news page and one completed five-minute price session; retain provenance only under confirmed usage rights.
4. Parse cited events and propose explicit policy/company/sector relationships using the existing agents. Preserve unknown dates and observed times.
5. Measure subsequent price outcomes without claiming causation. Train only after coverage, rights and chronological evaluation checks pass.
