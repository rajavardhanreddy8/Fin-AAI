# POWERGRID three-year archive

## Scope and status

This is a partial retrospective research archive for 2023-10-25 through 2026-10-25 (Asia/Kolkata). It is not a complete news archive, live trading feed, or training-ready dataset. The saved search inventory contains 72 Firecrawl metadata candidates; its search snippets and query-date windows do not establish publication dates, so those candidates remain inventory only. The final native web catalog has 17 publisher-page records with displayed publication-date evidence: 1 from 2023, 10 from 2024, 2 from 2025, and 4 from 2026. An earlier PIB publisher capture adds a distinct 2026 press release. The archive therefore contains 18 distinct publisher URLs, with five records in 2026. Publisher reporting is not an adjudicated statement of truth.

All records were collected after their publication dates. `observed_at` and `available_at` preserve actual retrieval time; publication time is kept separately. Historical records therefore support retrospective event-study research only and must not be represented as information available to a historical trading decision. Date-only records do not imply an intraday time.

## Outputs

Run `python scripts/build_company_history.py <saved-catalog.json> --output-dir <new-directory> --supplemental-event output/impact-pilot/20261024/powergrid-source.json` from the repository root. The assembler is offline and refuses to overwrite an existing output directory. Use `--receipt` when a matching collection receipt exists. Verified publisher catalogs must include hashed capture files beside the catalog. The optional price input requires both `--prices-csv` and `--price-manifest` satisfying the strict documented schema in the script.

The archive contains an immutable event export and a caller-friendly `articles.csv` with source URLs, stated publication time, actual observation time, publication semantics, and retrospective-use labels, plus an isolated ContextStore database, source reliability scores, coverage and inventory counts, and a manifest with input and output hashes. Search metadata is inventoried but not imported as dated events. No claims, relationships, truth adjudications, or source accuracy labels are synthesized. Current source scores are cold-start because no adjudicated outcomes were supplied.

## Price outcomes and limitations

Without independently validated daily bars, price outcomes are explicitly empty, `train_ready` remains false, and no zero-return values are fabricated. If verified bars are later supplied, the assembler reports descriptive publication-date close-to-close movement only. Daily bars cannot resolve intraday timing, overlapping news, market-wide causes, transaction costs, or executable returns. The archive does not generate BUY/SELL signals or orders.

Coverage is marked partial unless completeness is independently established. Search failures, undated metadata, out-of-window verified dates, and deduplication decisions remain in the manifest. A partial sample must not be described as exhaustive three-year coverage.

## Saved results on 25 October 2026

- Final source catalog: `output/powergrid-history/20261025/news/powergrid-verified-news-catalog-v4.json`. Earlier catalog versions remain as audit evidence; some failed the later strict capture checks.
- Dataset: `output/powergrid-history/20261025/dataset-v4/`. The `articles.csv` lists all 18 articles/releases. `context.db`, `events.json`, `source-scores.json` and `manifest.json` preserve provenance and coverage gaps.
- Admission verifies file hashes and that the stated URL, headline and publication evidence appear in the declared capture. It does not cryptographically authenticate a publisher or prove that all fields belong to one article block in a multi-page capture. January/August 2026 recapture times are preserved separately from their earlier headline observations.
- All three source/topic histories have zero adjudicated outcomes. A 0.5 prior is not measured publisher accuracy; no source was assigned an empirical trust rating.
- The initial dataset-v4 had no price bars: NSE access was region-restricted, and one ordinary Yahoo chart request returned HTTP 429. Neither route was retried. The separately approved provider acquisition below later supplied daily prices; the earlier artifacts remain unchanged. Daily prices remain insufficient for a five-minute execution backtest.

## Approved daily-price acquisition

The user approved one fixed five-credit `finance-yahoo-com/equities/history` request for `POWERGRID.NS`, interval `1d`, from 2023-10-25 through 2026-10-25. It returned 740 records dated 2023-10-25 through 2026-10-23, with open/high/low/close/volume, dividend-adjusted close, split factors, unadjusted prices and nine dividend events. The provider identifies the listing as an NSE equity quoted in INR. This is provider-reported identity, not separate exchange confirmation.

The request consumed exactly five credits: balance 251 before and 246 afterward. A confirmed one-credit feedback refund brought the balance to 247, for four net credits. Free retained-workspace exports saved all 740 rows without repeating the paid provider request. The difference from the earlier 253-credit balance occurred before this acquisition and is not attributed to this five-credit request.

Evidence is under `output/powergrid-history/20261025/prices/yahoo-provider-v1/`: `approved-request.json`, `provider-contract.json`, `raw-response.json`, `provider-data.json` and `execution-receipt.json`. Provider observation, first local persistence and later normalization availability are distinct times. Exact network-receipt time was not recorded. Session-calendar completeness, second-source market corroboration and reuse/training rights remain unverified; row counts and date endpoints alone do not establish complete coverage.

Two separate agents normalized and mechanically reviewed the export. All 740 rows match the provider response across prices, adjustment fields, volumes and timestamps. The normalized output is `prices/yahoo-provider-v2/daily-bars.csv`; `prices/independent-price-review.json` records the review's limited scope. The original pending manifest remains unchanged; `prices/yahoo-provider-v2/reviewed-manifest-v1.json` references the completed mechanical review. The symbol-to-ISIN mapping remains project context, not independent exchange verification.

The new `output/powergrid-history/20261025/dataset-v5/` combines the same 18 events with the price provenance and 15 descriptive publication-date close-to-close comparisons in `archive.json`. Three publication dates have no exact-date bar in this response: 2024-05-20, 2025-08-03 and 2025-11-05. No next-session prices were substituted, and these absences have not been adjudicated against an exchange calendar. Daily comparisons use `close`, not dividend-adjusted `adj_close`; dividend effects, overlapping news and announcements after the close can affect interpretation. Every comparison is explicitly noncausal, not cost-adjusted and not a training label. Dataset status remains partial and `train_ready` remains false.

The normalizer refuses to overwrite its outputs and preserves actual local normalization availability separately from provider observation. It can be reproduced with `python scripts/normalize_powergrid_history.py`; use a new `--output-dir` if the default already exists. Three fixture-based normalizer tests plus seven existing history tests passed in the root-run focused suite (10 tests and two subtests). No further model calls, training or trading ran during this approved acquisition.

## AWS interpretation and rejected hypotheses

Eight short, attributed headline/excerpt inputs were submitted to the pinned Nova Lite agent. Seven responses passed JSON/schema checks, yielding 14 proposals. All 14 pointed from company to event and were withheld by the reviewed event-to-company direction gate. No relationship was reversed automatically, and this batch added zero active impact edges or scores. One response failed JSON parsing; its cost and failure remain in the audit, without a retry. The token-estimated total is USD0.001065267 against a USD0.01 limit, rather than a settled invoice.

Inspect `analysis/interpretation-report.json`, `analysis/narrative-sentiment-candidates.json` and `analysis/model-usage.db` under the collection folder. Candidate narrative sentiment is uncalibrated and cannot be treated as an accepted price-impact weight, calibrated probability or trading signal. Better evidence and a reviewed representation of news-to-stock impact are required before these candidates can enter the active graph.

## Collection cost incident

The first Firecrawl batch exceeded the assigned 60-credit cap because concurrent searches included automatic result-page retrieval through `scrapeOptions`. Nine successful receipts report 721 credits in total; three additional requests returned rate-limit errors. The collector reported balance checks of 982 before the batch and 253 afterward, while the root observed an intermediate 921. Those shared-balance observations do not fully reconcile the exact attribution of the 729-credit delta. No USD charge is inferred from these figures.

Further unapproved Firecrawl collection stopped. Native web search/open operations produced the separately verified sample afterward. Raw requests, results and receipts are retained under `news/`; feedback for that earlier batch could not refund credits because its 120-second window had expired. The separate five-credit price-provider request was subsequently approved and executed once, as recorded above. Its one-credit feedback refund does not refund or reconcile the earlier overspend. This dataset does not establish publisher retention or model-training rights.
