# POWERGRID relational sentiment pilot

This pipeline creates cited company-news relationships and separately versioned scores. It is a research dataset. It has not demonstrated price prediction or qualified any trading strategy.

## Meaning of a weighted relationship

Each relationship identifies a driver and an affected entity. A policy-to-company edge and a company-to-policy edge are different hypotheses with independent evidence, mechanisms, scores and horizons. Incoming and outgoing adjacency views make a stored edge discoverable from either endpoint without creating another causal assertion.

The pilot keeps these fields separate:

| Field | Interpretation |
| --- | --- |
| Source authority, citation and content hash | Where a reported statement came from; not a guarantee of truth |
| Sentiment, -1 to 1 | Narrative polarity of the source statement |
| Impact weight, -1 to 1 | Proposed signed transmission from the driver to the recipient |
| Confidence, 0 to 1 | Model self-assessment; not a calibrated probability |
| Category | One of the existing eight market-context categories |
| Horizon | Separate 5-, 30- or 60-minute hypothesis |
| Observation and model-completion time | Earliest times the evidence and its interpretation entered this system |
| Score version and model audit | Immutable interpretation identity and provider-call reference |

Official index constituent weights are dated source facts. They must not be changed by training. Model coefficients describing how news relates to returns are separately tunable parameters.

## Working path

Firecrawl connector -> saved permitted public document -> budgeted Nova Lite relationship agent in ap-southeast-2 -> exact-citation and source-specific direction validation -> ContextStore SQL relationships -> immutable SQL score versions -> frozen feature snapshots -> candidate evaluation.

The runtime uses the existing pinned Nova Lite transport and spend ledger. It limits output to 512 tokens, permits no arbitrary tools or SQL, admits only supplied entity IDs, caches a completed call, and validates every proposal before storage. The language model can propose a score; deterministic code owns all database writes. This is API-based inference from the local runner. An always-on AgentCore service has not been deployed.

Source evidence is retained separately from interpretations. Reported quotations become claims; mechanisms remain estimated effects. A source-specific driver/recipient mapping can withhold a reversed or unsupported proposal while preserving it in the audit. Re-importing an accepted batch adds no duplicate rows.

## Verified pilot on 24 October 2026

Firecrawl retrieved a [PIB Cabinet announcement](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2232115&reg=3&lang=1) about POWERGRID's subsidiary investment delegation. The page displays 24 February 2026, 15:45 IST. The system first retrieved it in October; it cannot be used in a simulated February decision. Third-party reproduction/training rights are not inferred from tool access.

One Nova Lite call completed with 887 input and 291 output tokens. Current official Sydney token rates imply USD0.000129213 in model cost; this is a token estimate, not a settled invoice. The call produced two proposals. The policy-to-POWERGRID proposal passed source-specific direction review. The company-to-policy proposal reversed the mechanism described in the source and was withheld.

The resulting isolated database has one event, one reported claim, one accepted estimated relationship and zero observed price outcomes. Its three nodes are the event, policy and company. The original model score and an explicit manual demonstration are stored in `ctx_edge_scores` under separate versions. The manual demonstration changes the edge impact weight from 0.6 to 0.4, changing its heuristic feature from 0.225 to 0.150. Neither number is a percentage price forecast, and neither version is an activated trading policy.

Inspect the local artifacts:

- `output/impact-pilot/20261024/powergrid-source.json`: retrieved content, source metadata and observation time.
- `output/impact-pilot/20261024/company-impact-input.json`: exact bounded model input and reviewed directions.
- `output/impact-pilot/20261024/relationships.db`: SQL graph and immutable edge-score versions.
- `output/impact-pilot/20261024/model-usage.db`: durable provider call, reservation, usage and cost audit.
- `output/impact-pilot/20261024/powergrid-impact-v1.json`: initial accepted/withheld proposals and snapshots.
- `output/impact-pilot/20261024/powergrid-impact-v2.json`: verified replay with incoming/outgoing graph views; no duplicate records or additional model call.
- `output/impact-pilot/20261024/manual-tuning-demo.json`: separate illustrative manual change.
- `output/impact-pilot/20261024/verification.json`: counts, idempotency and missing-training-data check.

## Populated archive graph on 25 October 2026

The offline assembler `scripts/build_company_graph.py` combines the saved three-year POWERGRID sample with the earlier accepted policy pilot. The latest isolated output is `output/powergrid-graph/20261025/v4/`: `relationships.db`, `graph-report.json` and `review-queue.json`. Earlier versions remain audit snapshots. No provider inference, training, cloud resource creation or trading occurs in this step.

| Stored item | Count and meaning |
| --- | --- |
| News/evidence | 19 immutable event versions across 18 distinct source URLs; the PIB article has two separately preserved capture versions |
| Reported mentions | 18 article-to-company links saying the publisher discusses POWERGRID; no impact weight or truth guarantee |
| Business exposure | One cited company-to-power-transmission activity link; a normalized business description, not an official sector classification |
| Impact hypothesis | One unchanged policy-to-company edge and its original model score from the earlier pilot |
| Daily observations | 15 publication-date close comparisons, stored separately with causal attribution and training-label flags both false |
| Quarantine | 14 later model proposals and one earlier inverse proposal remain withheld; none was reversed into an accepted effect |

The sector claim quotes the saved PIB description of POWERGRID's transmission business. Its evidence points to the full-text archive event and matching text hash, preserving the older bounded pilot capture unchanged. New mention and business-exposure interpretations become known at actual graph-build time. Their source observation times remain separate. An explicit older `--asof` excludes those new interpretations; omitting it uses the captured build time. Re-importing the same accepted batch adds zero events, nodes, claims, relationships or analogs.

### Storage and inspection

`ctx_events`, `ctx_nodes`, `ctx_claims` and `ctx_relationships` hold the cited graph. The original score uses the existing `ctx_edge_scores` registry. The manual tuning demonstration stays excluded and has only an audit hash in this import. Source reliability, model confidence and effect weight remain separate; no publisher has adjudicated reliability history.

Supplemental SQL tables make the saved evidence inspectable:

- `graph_sources`: source-to-event provenance, with source URL, observation availability and content hash.
- `graph_event_versions`: source URL groups and exact original event payloads, preserving revisions without counting them as independent stories.
- `graph_adjacency`: incoming and outgoing references to the same directed relationship, with its known time. These references do not create inverse influence.
- `graph_daily_outcomes`: descriptive daily comparisons and their actual availability; these are not minute-horizon outcomes or causal edges.
- `graph_review_queue`: original proposal direction, citation and audit references retained for review.
- `graph_import_audit`: seven input hashes, including the archive manifest and the excluded manual demonstration.

Read the report's `directional_adjacency` to inspect both sides of a relationship. Direct SQL inspection must apply its time cutoff, for example:

```sql
SELECT direction, relationship_id, known_at
FROM graph_adjacency
WHERE node_type = 'company' AND node_id = 'powergrid'
  AND julianday(known_at) <= julianday(:asof);
```

The builder requires explicit saved inputs and new output paths. Use `python scripts/build_company_graph.py --help` for the arguments. It verifies the archive's sibling manifest when present, source text hashes and company identity; hashes detect local content changes and do not authenticate a publisher. Its report distinguishes complete import inventory from records visible at the requested cutoff.

Root verification passed 46 focused graph/store/score tests. After the final report-only fields were added, the three graph-specific tests passed again. Synthetic fixtures make these tests independent of ignored local output. Independent artifact reviews are `output/powergrid-graph/20261025/review-v1.json` and `review-v2-independent.json`. An interrupted write left `review-v2.json` containing null; it is not a validation receipt.

### Remaining connections

At the v4 checkpoint, official index membership, dated constituent weights and official sector classification were pending. The official Nifty constituent CSV could not be read by the browser because of its MIME type; one ordinary HTTPS download then failed TLS verification. Both failure receipts are retained under `output/powergrid-graph/20261025/evidence/`; verification was not weakened and no membership row was fabricated. The later permitted-network download and dated snapshot import below resolve one historical exposure fact; current membership and current weights remain unknown.

The graph is usable for evidence lookup and review. It is not a calibrated sentiment predictor. Broader permitted news coverage, adjudicated source facts, independently corroborated prices, point-in-time evidence and untouched evaluation remain required before predictive training or trading qualification.

## Reviewed source fact and historical index exposure

The latest reviewed derived graph is `output/index-exposure/20261025/applied-v3/relationships.db`. It extends a SQLite backup of the source-review graph in `output/source-adjudication/20261025/applied-v2/`, which itself preserves the v4 graph. Every parent row is retained; earlier failed generated attempts are explicitly marked invalid. Current/pre-cutoff reports, manifests, verification and `independent-review-plan-v1.json` are beside the final database.

The [official Nifty 50 whitepaper](https://niftyindices.com/docs/default-source/indices/nifty-50/nifty-50-whitepaper_2026.pdf?sfvrsn=dd206335_2), Exhibit 26 on PDF page 22 (printed page 42), lists POWERGRID with sector **Power** and weight **1.18%** in the snapshot dated **27 February 2026**. The original PDF, SHA-256 and rendered table are retained under `output/powergrid-graph/20261025/evidence/index-permitted-download-v1/`. A normal HTTPS download succeeded after requesting permitted network access; TLS validation and source identity were unchanged. Text and visual row alignment were both checked.

That weight is stored in a cited `documented_exposure` claim and company-to-index relationship with `snapshot_date=2026-02-27`, `temporal_scope=historical_snapshot_only` and `current_membership_asserted=false`. It is not an `estimated_effect`, impact score or tunable coefficient. No continuous membership interval is inferred. The snapshot date is not treated as publication time; publication remains unknown and actual October retrieval/review times control availability. The PDF does not supply a symbol or ISIN; the separate issuer filing provides that identity cross-check.

The derived database contains 21 evidence-event versions, 25 nodes, 21 cited claims and 21 directed relationships. It retains the one original impact score, 15 descriptive daily observations and 15 withheld proposals. Supplemental provenance/version tables include the new verification and index documents, and 42 adjacency references cover both directions of the 21 existing directed edges. The index import adds one source event, one index node, one claim and one relationship; replay adds zero. A cutoff before the actual review excludes the new index connection.

The source history contains one AI-assisted, narrowly scoped confirmed appointment proposition; its experimental score is uncalibrated and below the historical sample threshold. No origin-authentication reviews or trading permissions were added. See [source review details](SOURCE_RELIABILITY.md). The prior model-score payload is unchanged, and official weights remain separate from that score.

The broker-independent RSS collector is a separate local infrastructure checkpoint: `output/alternative-news-20261025/events.json` contains 20 general PIB observations with unknown publication dates and no POWERGRID title matches. They are not imported as POWERGRID relationships or historical trading features. The provider track reports 21 tests in its local `docs/DATA_PROVIDER_ALTERNATIVES.md` plan; this graph milestone did not rerun or publish that track's pending code changes. Independent daily-price reconciliation, broader permitted news, source adjudications and prospective measurement still remain.

## One-date official NSE price corroboration

The [official NSE CM-UDiFF archive for 23 October 2026](https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_20261023_F_0000.csv.zip) was retrieved once over normal HTTPS, returning HTTP 200 without a redirect. The ZIP was observed at **2026-10-25T17:19:47.870834Z**; that is evidence availability, not its trading date. Its SHA-256 is `009b57f15cb36e14fa956b2e585b69b23f279eb8532c2c63c0adf0aa2ed77689`.

The unique **POWERGRID / INE752E01010 / EQ** row dated **23 October 2026** records open **248.05**, high **248.60**, low **242.30**, close **247.40**, and volume **5,917,098**. Independent review parsed the original ZIP CSV in memory and compared all five values directly with the original saved Yahoo provider response in `output/powergrid-history/20261025/prices/yahoo-provider-v1/provider-data.json`, using its unadjusted OHLC and volume. The values match exactly. Identity, date, OHLC bounds, volume, source hashes and artifact receipts were checked.

The original ZIP, request receipt, comparison, limitations and independent review are retained in `output/official-price-corroboration/20261025/probe-v1/`. The canonical price CSV and graph databases were unchanged. This corroborates one date for one instrument; the other 739 rows, session completeness, adjusted-price equivalence and source retention/reuse rights remain unreviewed. It supplies no minute-horizon label or causal attribution and does not qualify a predictor or trading system.

`scripts/verify_powergrid_bhavcopy.py` now makes the same check reusable without downloading anything. It accepts a previously saved official ZIP, the retained provider JSON, a trading date and a new output path; it rejects wrong identity, series or date, and compares only unadjusted OHLCV. The first offline replay is `output/official-price-corroboration/20261026/replay-v1.json`. It is a one-date verifier, not a backfill tool.

## Updating weights and learning

Evidence is append-only. Change a manually assigned score by adding another `score_version` with a later `score_known_at` and explicit manual origin. Read the chosen version with `load_edge_scores`; a query does not silently choose or activate the latest score. Existing version IDs reject changed content.

The first learning model is a small linear return predictor trained with mean-squared-error gradients. This is a differentiable baseline, so its coefficients and intercept can be updated by backpropagation. It does not fine-tune Nova or Jev. Coefficients are shared by structural feature type, rather than memorizing a unique parameter for each historical article.

The baseline uses direct incoming company edges. It does not recursively add paths through a cyclic graph. Repeated evidence for the same event and structural feature contributes once; graph views still retain all cited relationships. If parallel edges compete for that contribution, the lowest relationship ID is the explicit deterministic tie-break, not an assertion that its mechanism is superior.

Training needs a separately sourced price-outcome label and an embedded frozen snapshot for each example:

```json
{
  "sample_id": "unique-observation",
  "event_id": "source-event-id",
  "company_id": "powergrid",
  "horizon_minutes": 30,
  "decision_at": "2026-11-02T04:30:00Z",
  "outcome_completed_at": "2026-11-02T05:00:00Z",
  "label_known_at": "2026-11-02T05:01:00Z",
  "target_return_bps": 0,
  "provenance": "real",
  "snapshot": "replace with the full frozen snapshot object"
}
```

This is a schema illustration, not an observed trade or return. Real outcomes must include verified price provenance in the upstream label record. The `real` tag is operator-supplied and does not authenticate a dataset. Snapshot hashes detect modification; they do not prove timestamps or source authenticity.

Training verifies finite values, immutable snapshot hashes, company/horizon consistency, and feature availability before the decision. Labels must complete and become known before the respective cutoff. Shared event IDs are purged across the training/validation boundary; later holdout observations do not update coefficients. At least 20 training and five validation examples are required even to create a review candidate. These minimums are software admission checks and are insufficient by themselves for live qualification.

Candidates retain parent/version IDs, provenance counts, cutoffs, feature schema, availability time and validation error against a zero-return baseline. Future prediction requires the candidate and snapshot to be available at that timestamp, with matching company/horizon/features. Candidate prediction is exploratory and cannot authorize execution. Holdout evaluation, calibration, costs and forward paper qualification remain required. Selection by validation is not an untouched holdout result.

## Commands

From the project directory, process a reviewed document explicitly:

```text
python scripts/run_company_impact.py SOURCE.json --db GRAPH.db --output NEW_VERSION.json --budget-config CURRENT_NOVA_BUDGET.json --usage-db USAGE.db --namespace UNIQUE_EXPERIMENT --profile fin-aai
```

The source JSON contains `title`, `document` and `reviewed_directions`. The document contains `source_id`, `source_url`, `published_at`, `observed_at`, `text`, `company_names` and `allowed_nodes`. Direction rows contain `[subject_type, subject_id, object_type, object_id]`. Use only reviewed permitted content. An existing output path is refused before constructing a provider client.

Build snapshots or manually adjust/train/predict candidate coefficients using `scripts/run_impact_graph.py`; its `--help` describes each JSON input shape. Every output path must be new. No command automatically promotes a candidate.

## Remaining evidence gaps

Source-history scoring and immediate paper-response guidance are documented in [SOURCE_RELIABILITY.md](SOURCE_RELIABILITY.md). They remain experimental and separate from impact scores.

The Upstox gateway block prevents acquiring verified POWERGRID candle outcomes through that adapter. No real return model has been trained. The first document is historical material observed now, and its minute-horizon scores are uncalibrated hypotheses rather than a fresh intraday signal. More permitted events, verified price outcomes, source-rights review, out-of-sample comparison and forward paper measurements are needed before a predictive claim or an always-on cloud release.
