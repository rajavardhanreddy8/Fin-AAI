# Source reliability and paper responses

This is an experimental research and paper-evaluation aid. It does not place orders, make trading decisions, or automatically promote a model or policy.

## What the score means

Reliability measures historical fact accuracy from reviewed, cited adjudications. It is separate from event impact: an accurate publisher may report news with little market effect, and markets can move on false rumors. A high score is not a directional forecast or a reason to wait before assessing an event.

An event may be assessed immediately from one reviewed, authenticated primary company or government source, even when that publisher has no reliability history. This permits paper evaluation only; it does not establish that the claim is true, predict impact, or authorize a trade. Authentication is a bounded human/provider assertion, not cryptographic proof, and it does not verify the underlying claim or price impact. A publisher's reputation alone never triggers a directional decision. Other publisher reports need a reviewed authentication record, support from a different source with an independent origin, and sufficient historical reliability before directional paper evaluation. Uncertain or unsupported evidence leads to `monitor_now`. The policy response is conditional (`paper_evaluate_now` or `monitor_now`) and carries `monitor_risk`; it is never an order or BUY/SELL instruction. Monitoring is a risk response, not a trust-based delay rule.

Source IDs should identify a stable publisher and are evaluated only within the requested company and category. For example, `pib_powergrid_policy` is a topic-scoped source ID, not a universal score for PIB. A feed-specific ID is appropriate only when the feed itself is the publisher. Syndicated copies should retain their original upstream origin; copies of one wire story are not independent corroboration. Independent-origin corroboration is a reviewed assertion; source IDs alone cannot establish whether two reports are copies or independent. Company and category scope is exact. The system does not fall back to a broader company, category, or publisher scope.

Adjudications are append-only and cite the evidence reviewed. Queries use the latest verdict known by the requested cutoff, including corrections as later records. Canonical deduplication avoids counting repeated observations of the same underlying fact as independent evidence. The mean uses beta-one smoothing; the raw Wilson 95% lower bound, sample counts, and uncertainty remain visible alongside it. A score becomes available when the system observed/adjudicated it; publication dates do not backdate availability to earlier market observations.

## Experimental admission parameters

For non-primary publishers, the historical reliability branch expects at least 20 resolved adjudications and a Wilson 95% lower bound of at least 0.80, plus independent-origin support. All events must be no more than 60 seconds past local observation at assessment; publication-to-observation delay must be at most 300 seconds. A primary company/government event still needs a fresh observation and a reviewed authentication record, but bypasses the historical sample threshold. Both paths leave impact `unvalidated`. These are versioned, review-only experimental parameters. They are not a calibrated predictor, and passing them does not establish profitability or live-trading readiness.

## Commands

All commands require an existing ContextStore database and a new output path. They make no network or model calls and execute only local research operations.

Append reviewed event authentication and origin records from a JSON list. Records carry the event, exact company/category, `origin_status`, authentication method, cited evidence, reviewer, and corroborating event IDs. Independent support must be from a different source and canonical event:

```text
python scripts/run_source_response.py review-event event-reviews.json --db relationships.db --asof 2026-10-24T12:00:00Z --output event-review-v1.json
```

Append cited adjudications from a JSON list:

```text
python scripts/run_source_response.py adjudicate adjudications.json --db relationships.db --asof 2026-10-24T12:00:00Z --output adjudication-v1.json
```

Query the exact publisher, company, and category:

```text
python scripts/run_source_response.py score --source-id publisher-id --company-id powergrid --category governance_policy --asof 2026-10-24T12:00:00Z --db relationships.db --output source-score-v1.json
```

Assess a received event with the policy:

```text
python scripts/run_source_response.py respond --event-id event-id --company-id powergrid --category governance_policy --asof 2026-10-24T12:00:00Z --db relationships.db --output response-v1.json
```

The adjudication record contains `adjudication_id`, `event_id`, `company_id`, `category`, `verdict` (`confirmed`, `refuted`, or `unresolved`), `known_at`, `reviewer_id`, nonempty `evidence_refs`, and `verification_refs`. `evidence_refs` anchor the report under review. Confirmed and refuted verdicts require one or more verification references showing proof or correction; unresolved verdicts may use an empty list. Each reference contains `source_id`, `source_url`, `raw_hash`, `known_at`, precise `citation`, and optionally `source_event_id`. Verification must be known by the verdict time and differ from the reviewed report's URL/hash. Both reference sets are human-reviewed citations, not externally verified by an authentication service.

The event review record contains `review_id`, `event_id`, `company_id`, `category`, `known_at`, `reviewer_id`, `origin_status` (`authenticated_primary`, `authenticated_publisher`, or `unverified`), `authentication_method`, `evidence_refs`, and `corroboration_event_ids`. Authentication status is a reviewer assertion; the command does not authenticate reviewer roles or publisher identity through a runtime identity service. Authenticated reviews require cited evidence. For publisher reviews, corroboration event IDs must identify timely, different-source and different-canonical events.

These clearly synthetic examples show the record shapes. The values are fixtures only; they are not real source evidence or performance:

```json
[
  {
    "adjudication_id": "fixture-adj-1",
    "event_id": "fixture-event-1",
    "company_id": "fixture-company",
    "category": "company_performance",
    "verdict": "confirmed",
    "known_at": "2026-01-01T00:00:10Z",
    "reviewer_id": "fixture-reviewer",
    "evidence_refs": [{
      "source_id": "fixture_publisher_company_performance",
      "source_url": "https://example.test/fixture",
      "raw_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "known_at": "2026-01-01T00:00:10Z",
      "source_event_id": "fixture-event-1",
      "citation": "fixture paragraph 1"
    }],
    "verification_refs": [{
      "source_id": "fixture_independent_verifier",
      "source_url": "https://example.test/fixture-verification",
      "raw_hash": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
      "known_at": "2026-01-01T00:00:10Z",
      "citation": "fixture independent confirmation"
    }]
  }
]
```

```json
[
  {
    "review_id": "fixture-review-1",
    "event_id": "fixture-event-1",
    "company_id": "fixture-company",
    "category": "company_performance",
    "known_at": "2026-01-01T00:00:10Z",
    "reviewer_id": "fixture-reviewer",
    "origin_status": "authenticated_primary",
    "authentication_method": "fixture domain review",
    "evidence_refs": [{
      "source_id": "fixture_company_primary",
      "source_url": "https://example.test/fixture-primary",
      "raw_hash": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "known_at": "2026-01-01T00:00:10Z",
      "source_event_id": "fixture-event-1",
      "citation": "fixture official release"
    }],
    "corroboration_event_ids": []
  }
]
```

| Response action | Meaning |
| --- | --- |
| `paper_evaluate_now` | Eligible for immediate review-only paper evaluation. Primary source authentication can qualify without history; non-primary sources still need the historical reliability threshold and independent support. Impact remains unvalidated. |
| `monitor_now` | At least one freshness, review, corroboration, or reliability gate is unmet. Continue monitoring the event. |
| `abstain_directional_entry` | A cited refutation blocks directional paper entry for this event. Monitoring continues for updates or corrections. |

`paper_evaluate_now` means eligible for a review-only paper evaluation. It is distinct from a paper trade; execution is always `none`, and no BUY/SELL direction or order is produced. Input record and response details follow the versioned `stock_research.source_reliability` API. Keep original upstream origin with every review. An illustrative fixture in the command tests is synthetic and is not evidence of any publisher's performance.

## First reviewed real fact, 25 October 2026

`output/source-adjudication/20261025/applied-v2/relationships.db` is a SQLite backup of the populated POWERGRID graph with one additional issuer-filing event and one narrowly scoped source adjudication. The parent graph is unchanged. `adjudication-v1.json`, `scope-note.md`, before/after scores, `import-manifest.json`, `verification.json` and `independent-review-plan-v1.json` preserve the import and its review. The encoding-corrupted earlier `applied-v1` attempt is marked invalid and is not an accepted dataset.

The selected PIB report says the named person assumed POWERGRID's CMD position. A separate [POWERGRID governance filing](https://www.powergrid.in/sites/default/files/Investor_Relation/Reports_Filings/Corporate_Governance/2026-27/CG_Report_2026-27_Q1.html) supports that appointment and supplies an effective date of 1 April 2026. The verdict covers the selected appointment proposition; it does not adjudicate other article statements, establish an exact assumption hour or count company-origin documents as independently originating reports.

The reviewer is explicitly AI-assisted, with no authenticated human identity assertion. No origin-authentication review was added. Full source captures, exact citations and original hashes are separate from the new verdict time. The filing's quarter-end date is not used as publication time; publication remains unknown, and actual capture availability is retained.

The `pib-ministry-of-power` / `powergrid` / `governance_policy` history changes from zero resolved records to one confirmed selected proposition. Its beta-smoothed mean is approximately 0.667 and Wilson lower bound approximately 0.207. These are small-sample experimental statistics, not a demonstrated publisher accuracy rate or a probability that the next report is true. The score remains `calibrated=false`, `live_order_authorized=false`, and below the 20-record historical admission threshold. Other company/category scopes gain no evidence from this review.

Replay adds zero adjudications. A cutoff immediately before the verdict still returns zero resolved records. The original 20 graph relationships, one model score, 15 descriptive daily outcomes and 15 quarantined proposals are preserved. The issuer filing also provides a separately recorded company-reported symbol/ISIN identity check against Yahoo metadata; it does not corroborate price values or exchange-calendar coverage.

## Local artifacts from the earlier pilot

The POWERGRID experiment has an isolated copy of the source-linked graph at `output/source-reliability/20261024/powergrid-source-review.db`. Verification on 24 October 2026 found one event, one claim, one relationship, zero truth adjudications and zero origin reviews. Its actual response is `monitor_now`: the report is stale and no origin review is available. The saved outputs are:

- `output/source-reliability/20261024/source-score-v2.json`
- `output/source-reliability/20261024/response-v1.json`
- `output/source-reliability/20261024/verification.json`

The earlier `source-score-v1.json` is an exploratory future-cutoff query, excluded from the current-time verification. No future observation was collected. The full repository suite passed 299 tests, including 29 focused database/response compatibility checks. No provider call or order was made for this milestone.

An empty history (`resolved_n: 0`) means no empirical reliability claim can be made about PIB or any other publisher. In particular, there is no measured universal PIB reputation score.

## Limitations

Reliability is historical and scope-specific. Sparse, delayed, or disputed adjudications can leave wide uncertainty. Syndication can make apparently separate sources dependent. Freshness thresholds and the 20-record/0.80 criteria are experimental settings that require versioned review. No source-performance claims are made here; no real source dataset is asserted by the schema or test fixture.

Time checks use supplied evidence and review timestamps; hashes and timestamp syntax do not prove historical authenticity. Preserve the original output snapshots for each decision. Backfilled records or a recomputed historical query do not establish that a score actually existed then. Company attribution and independent origin remain reviewer assertions. The conservative support gate also rejects copies with the same canonical story ID; distinct IDs still do not prove independent reporting. Automated identity verification, a fast news feed and a calibrated price-impact model remain separate work.
