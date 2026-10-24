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
