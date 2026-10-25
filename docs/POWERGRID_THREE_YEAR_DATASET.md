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
- No price bars were acquired. NSE access was region-restricted, and a single ordinary request to the independent Yahoo chart source returned HTTP 429. Neither route was retried after those restrictions were established. Daily prices would still be insufficient for a five-minute execution backtest.

## AWS interpretation and rejected hypotheses

Eight short, attributed headline/excerpt inputs were submitted to the pinned Nova Lite agent. Seven responses passed JSON/schema checks, yielding 14 proposals. All 14 pointed from company to event and were withheld by the reviewed event-to-company direction gate. No relationship was reversed automatically, and this batch added zero active impact edges or scores. One response failed JSON parsing; its cost and failure remain in the audit, without a retry. The token-estimated total is USD0.001065267 against a USD0.01 limit, rather than a settled invoice.

Inspect `analysis/interpretation-report.json`, `analysis/narrative-sentiment-candidates.json` and `analysis/model-usage.db` under the collection folder. Candidate narrative sentiment is uncalibrated and cannot be treated as an accepted price-impact weight, calibrated probability or trading signal. Better evidence and a reviewed representation of news-to-stock impact are required before these candidates can enter the active graph.

## Collection cost incident

The first Firecrawl batch exceeded the assigned 60-credit cap because concurrent searches included automatic result-page retrieval through `scrapeOptions`. Nine successful receipts report 721 credits in total; three additional requests returned rate-limit errors. The collector reported balance checks of 982 before the batch and 253 afterward, while the root observed an intermediate 921. Those shared-balance observations do not fully reconcile the exact attribution of the 729-credit delta. No USD charge is inferred from these figures.

Further Firecrawl collection stopped. Native web search/open operations produced the separately verified sample afterward. Raw requests, results and receipts are retained under `news/`; a feedback attempt could not refund credits because its 120-second window had expired. A proposed separate, fixed five-credit price-provider request has not been executed and requires the user's response. This dataset does not establish publisher retention or model-training rights.
