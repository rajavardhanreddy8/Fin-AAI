# NIFTY market context (shadow research)

This milestone adds a deterministic way to summarize dated, source-backed event evidence alongside the NIFTYBEES paper workflow. It is a research baseline, not a validated forecast or a trading signal. Missing evidence remains an explicit gap; the module does not infer company exposure, causes, or neutral scores.

The 2026-10-17 follow-on adds a separate time-aware SQLite evidence/relationship store and a real 20-entry PIB archive. See [NEWS_INTELLIGENCE_TRACKS.md](NEWS_INTELLIGENCE_TRACKS.md) for commands, ownership and next gates, and [NEWS_OPERATIONS_STATUS.md](NEWS_OPERATIONS_STATUS.md) for verification. The first batch has no source publication dates or summaries. Title-only annotations explicitly mark `summary_missing`; this input support is tested with a fake transport, not a live scoring result. No real claims, impact links or learned score weights are established by this archive.

## Input and snapshot

`stock_research.market_context.build_snapshot` accepts normalized event records, separately completed score annotations, and dated constituent membership. Event records use the ingest contract: immutable `event_id`, `canonical_id`, source identity/URL, publication and availability timestamps, entity IDs, raw hash, verification status, and optional revision/duplicate links. Timestamps must include a timezone. The cutoff excludes events whose `available_at` or known publication time is later than `asof`; revisions are selected only from the records known by that cutoff, and canonical copies count once.

Annotations bind to the selected event revision by `event_id`. They carry their own `available_at` (when scoring completed), explicit categories, a score from -100 to 100, confidence from 0 to 1, and evidence references. The canonical categories are company performance; valuation and expectations; sector conditions; governance and policy; domestic economy; global conditions; external risks (including war, sanctions, climate, and water); and market behaviour. A category score is an equal-weight mean of the unique eligible annotations. Coverage is the eligible annotation count, freshness is age in seconds of the most recent eligible annotation, and missing categories have null score/confidence/freshness with zero coverage.

Snapshots include active dated membership known by the cutoff and a SHA-256 content hash. The command accepts one JSON input containing `asof`, `target`, `events`, optional `annotations`, and optional `membership`:

```powershell
python scripts/run_market_context.py input.json --output output/context.json
```

The output path is create-once: an existing identical snapshot is accepted, while different content is rejected. Input extraction and scoring remain caller-owned. An absent or incomplete sector peer set remains a coverage gap, rather than being filled by a presumed relationship.

## Optional event collection and Nova annotation

`run_market_ingest.py` normalizes Upstox candle/news snapshots and explicitly permitted RSS/Atom feeds into hashed raw snapshots, completed five-minute bars, and unscored event rows. A local fixture can be inspected without writing output:

```powershell
python scripts/run_market_ingest.py --fixture fixture.json --dry-run
```

An explicitly permitted feed registry can be added with `--feed-registry feeds.json`. Live Upstox collection uses repeated `--instrument-key` values and optional `--from-date`/`--to-date`; provider authentication and access have not been verified. News sources remain publisher-reported and unverified, and no ingestion score is generated.

`run_market_agents.py` is the separate optional annotation step. Its default is a no-call dry run. `--live` requires a current budget file with Nova pricing and billing evidence, and `--usage-db` stores a durable reservation/audit ledger:

```powershell
python scripts/run_market_agents.py market-ingest/market-ingest.json
python scripts/run_market_agents.py market-ingest/market-ingest.json --live --budget-config budget.json --usage-db market-agents-usage.sqlite --output annotations.json
```

The wrapper pins Nova Lite in `ap-southeast-2`, has no tool access, bounds event text, checks a conservative UTF-8 prompt-size estimate before reserving or calling, and caches by namespace, event hash, model and prompt hash. It validates model identity, complete response status, all eight category keys, score/confidence bounds, evidence references, and completion time. Invalid output or unscored categories remain visible gaps. The reservation uses the prompt-size bound and output ceiling; it is an estimate, not a hard spend cap, and provider billing may lag. No live annotation or provider access was tested in this milestone.

## Index contribution accounting

Membership/weight rows must identify one complete dated snapshot with `snapshot_id`, `known_at`, `effective_at`, `complete`, `member`, and (for contribution calculations) `weight`. The selector chooses only the latest whole snapshot known and effective by the cutoff; it never fills omitted members from older snapshots. It rejects mixed timestamps, duplicate members, and ambiguous same-date snapshots. The collection layer does not yet provide this source data, so inputs are currently explicit offline fixtures/operator-supplied evidence.

`index_contributions` multiplies supplied constituent returns by weights in that selected snapshot. It reports total weight coverage, covered return weight, known contribution, and the separate residual against the supplied index return. It does not scale partial coverage up to 100%; incomplete weights and missing prices remain flagged gaps. Inputs are expected to represent beginning-of-return-period weights. ETF tracking differences can be interpreted as part of the residual only when the caller supplies ETF/index return evidence.

## Peer comparisons, investigations and candidate reviews

The runner keeps `snapshot` as its default operation and supports these create-once JSON outputs through `--operation`:

```powershell
python scripts/run_market_context.py peers.json --operation peer-comparison --output output/peers.json
python scripts/run_market_context.py investigation.json --operation investigation --output output/investigation.json
python scripts/run_market_context.py candidate.json --operation candidate-review --output output/candidate-review.json
python scripts/run_market_context.py rl-decisions.json --operation rl-review --output output/rl-review.json
```

`peer-comparison` requires a documented `peer_set` with `peer_set_id`, `sector`, unique `peer_ids`, expected `metrics`, `methodology`, `source_refs`, `documented_at`, and `effective_at`, plus metric observations containing `company`, `metric`, `value`, `effective_at`, and `available_at`. Only peer definitions and observations known and effective by `asof` are included. Each expected metric reports target coverage, expected and observed peer counts, peer median, and explicit missing peer IDs, including fully uncovered metrics. The selected peer roster and methodology are caller-supplied evidence; this module does not infer sector membership or peer quality.

`investigation` requires an immutable investigation ID, `kind` (`winning_trade`, `losing_trade`, or `eligible_no_trade`), a decision timestamp and the frozen `decision_snapshot`. Original decision evidence must have been available by that timestamp. Discoveries must be later and are stored separately as `possible_explanation` with `unverified` status; no causal claim is emitted. Eligible no-trade records require `decision_snapshot.eligible_no_trade=true`. The command's create-once output path prevents a changed record from replacing the existing record.

`candidate-review` consumes records with unique `event_id`, decision-time category scores, `snapshot_asof`, `snapshot_hash`, and a later `outcome_at`/`outcome_bps`. It refuses snapshots after the decision, duplicate IDs, and nonchronological cutoffs. Training ends at `train_through`; validation decisions and outcomes must fall after the training boundary and by `validation_through`. It produces an explicit `candidate_version`, normalized category weights, and a validation comparison to the frozen `frozen_equal_weight_v1` baseline. Each comparison reports observation/trade counts, mean net basis points, standard error and the supplied per-trade `cost_bps`. Zero costs are explicitly marked `cost_evidence_status=unverified`; nonzero supplied costs also remain operator-supplied and unverified. The report is a hashed shadow review and never promotes or mutates a candidate. It is a lightweight descriptive fit, not proof of predictive value.

`rl-review` consumes uniquely identified decisions with policy version, decision/outcome times, RL and executed actions, override status, and realized return in basis points. Reward attribution additionally requires persisted `execution_matched_rl=true` and `engine_version=2`, and subtracts the supplied per-trade cost. Overridden, mismatched, or unsupported-engine actions have no reward. Zero costs are marked `cost_evidence_status=unverified`; nonzero supplied costs are not tariff-verified either. RL training and chronological validation remain owned by the shared pilot engine (`train_candidate_from_bars` and `compare_holdout`); this review does not retrain or promote those frozen policies.

## Paper journal attachment

`run_intraday_paper.py --context-snapshot` optionally attaches a precomputed shadow snapshot to the completed bar where a paper decision occurs. It validates the hash and shadow status, requires snapshot `asof` no later than the decision timestamp, and stores the payload in `forward_context_snapshots` keyed by run and bar. A changed snapshot cannot resume the same frozen run. Without this option, legacy configuration and decision hashes remain unchanged. The snapshot is audit metadata and is not passed to or used by the action provider or risk rules.

## Limits

The score weights and peer/investigation/candidate outputs are unvalidated shadow research. There is no calibrated confidence, comprehensive sector/index evidence, automated peer set, or established event taxonomy. Peer roster quality, actual trading costs, source authenticity, and candidate generalization remain unverified. The deterministic snapshot module makes no model calls. Optional annotation generation is separate, explicit, and budget-gated; provider access and live annotation remain unverified. Article publication dates alone are insufficient to reconstruct what a historical language model knew; retrospective annotations can leak later model memory even when article timestamps are hidden. Use only annotations generated and frozen prospectively for a defensible historical test. No holdout retuning, automatic policy promotion, or broker operation is part of this module.
