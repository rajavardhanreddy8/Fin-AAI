# Pilot API and forward-paper milestone

Updated 2026-10-16. Codex builds this code; deployed decisions use caller-owned provider APIs. No cloud resources, credentials, live orders or scheduled services were created by this track.

## What runs

- `stock_research.pilot_agents`: Nova Lite Converse transport, Jev typed Choice transport, strict `decide(evidence: dict, rl_action: str | None) -> str`, one-step Nova coordinator and SQLite spend reservations.
- `scripts/run_intraday_paper.py`: starts a persistent run and consumes one newly observed completed bar per invocation. `--strategy rules` is the explicit default. `--strategy jev` and `--strategy nova-jev` require a validated budget-evidence file and cannot silently start as rules-only.
- `provider_readiness(*, probe=False) -> dict`: secret-safe status. `probe=True` reads provider catalogues only. Readiness remains false until invocation and required evidence are independently verified.
- Fourteen offline checks cover bounded tools, typed protocol, requested/resolved model lineage, immutable evidence/RL inputs, budget/FX blocks, reserved crashes, invalid responses, restart across simulated entry/exit, clock provenance and read-only journal rebuild.

```powershell
python -m unittest discover -s tests -p test_pilot_agents.py -v
python scripts/run_intraday_paper.py --status
python scripts/run_intraday_paper.py --probe
```

## Provider evidence and blockers

The default process still has no selected `AWS_PROFILE`, so ordinary readiness output remains fail-closed. A separate read-only check on 2026-10-09 authenticated the existing `fin-aai` profile, verified that the project is FREE/ACTIVE with USD115.57 credits remaining through 2027-04-02, found Nova Lite active with on-demand inference in `ap-southeast-2`, and simulated an allowed `bedrock:InvokeModel` decision for that model. This establishes current project-plan, catalogue, and IAM-policy evidence; it does not establish Bedrock runtime service eligibility or a successful paid response. Nova uses only `amazon.nova-lite-v1:0`, with explicit `maxTokens=192`, timeouts and one paid attempt. See [Nova Lite model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-lite.html).

The default text catalogue first returned `typesafe/jev-router`, a dynamic-price chat router. The Decisions catalogue read on 2026-10-09 verified `typesafe/jev-1.13`, 64,000 context tokens, USD 0.000000042/input token and zero output-token price. The adapter uses `POST https://openrouter.ai/api/alpha/decisions`, one Choice with four actions, and retains probabilities/confidence. It records the returned dated snapshot and rejects other model families. The documented snapshot example is `typesafe/jev-1.13-20260917`; no invocation established which snapshot this project would receive. Sources: [OpenRouter Jev tutorial](https://openrouter.ai/docs/guides/community/jev-tutorial), [Decisions reference](https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request), [Decisions catalogue](https://openrouter.ai/api/v1/models?output_modalities=decisions).

The OpenRouter key stays in the process environment and is never stored in the secret-free JSON file passed through `--budget-config`. `--status --strategy jev --budget-config path/to/pilot-budget.json` reports whether Jev-only model and billing evidence is valid without disclosing its sources. That path requires the frozen credit ceiling, exact Jev price and resolved snapshot, dated USD/INR evidence, and daily `infra`, `storage` and `jev:YYYY-MM` reconciliation evidence. `--strategy nova-jev` additionally requires Nova price and `bedrock` billing evidence. Jev’s typed API has no documented `max_tokens` argument; its response is bounded by one fixed four-option question, validated token counts and a bounded HTTP read. It does not generate chat prose.

The readiness result lists the current required billing scopes even when no file exists. It rejects duplicate scopes and requires fresh (within one day) `infra`, `storage`, and current-month `jev:YYYY-MM` reconciliation evidence before a Jev-only decider is constructed; Nova-Jev also requires `bedrock`.

## Spending contract

`UsageLedger(path, credit_usd)` freezes a caller-supplied, verified credit ceiling. The 2026-10-09 FREE/ACTIVE USD115.57 project-plan snapshot and expiry 2027-04-02 are evidence inputs, not an AWS enforced spending limit or service-access proof. Save its evidence link beside the integration configuration. The ledger enforces 50% infrastructure, 25% Bedrock and 5% storage envelopes, retaining 20% reserve; new paid calls stop at 80% of an applicable envelope or total credit ceiling. Jev has a separate INR300/month envelope and INR240 entry/training stop.

A 2026-10-09 Cost Explorer query for October service costs returned estimated values and no Amazon Bedrock line item. That is a useful current-use observation, but it is not cumulative, final billing evidence and cannot populate the required `infra`, `bedrock`, or `storage` reconciliations. Jev billing and a verified USD/INR rate are still absent.

`PriceEvidence` requires exact model, rates, context ceiling, source and verification timestamp no older than one day. Jev additionally requires positive dated USD/INR rate evidence. No exchange rate is guessed. Input is capped at 8192 bytes. Reservations use the verified full context ceiling plus 192 output tokens to cover unknown tokenization. For the observed Jev price/context this is USD0.001344, before an evidence-backed INR conversion. Nova reservations can be larger; replacing full-context reservation requires verified token-count support. This simplification is conservative, not a claim that each prompt consumes a full context.

Before a call, import dated cumulative invoices with `ledger.reconcile(scope, amount, as_of, source, included_call_ids=())`. AWS scopes `infra`, `bedrock`, `storage` are cumulative since the frozen ceiling; Jev scope is `jev:YYYY-MM`. AWS imports are USD, Jev imports INR using verified conversion. Sources must identify retained billing evidence. Missing/stale reconciliation blocks paid calls. Import only invoice-confirmed call IDs to release local double counting; unidentified calls remain additional charges, including uncertain timeout/crash reservations. There is no automatic billing feed yet.

The ledger commits reservation before network access and caches completed, blocked and uncertain requests by namespace/provider/model/prompt/input hashes. A restarted uncertain request abstains and is never silently reissued. An operator must reconcile it before deliberately using a new namespace. Calls persist the fixed prompt and original input, requested/expected/resolved model/version, prompt/input/response hashes, model choices/distributions, RL override, purpose, tokens, currency, price/FX sources, reservation/charged cost, latency and safe failure classification. Entry and training calls stop at 80%; exit/reconciliation calls may use the retained capacity but never exceed the hard monthly/credit ceiling. Paper decisions retain the associated provider audit record. Engine execution overrides remain in the shared transition ledger. Provider exceptions are recorded without secret-bearing message text.

Budget exhaustion affects model calls and entry permission; deterministic stops, drawdown/session liquidation and reconciliation remain outside model authority. This does not enforce costs incurred by other AWS software: daily billing integration and provider-side spend controls remain necessary before unattended use.

## Forward-paper contract

Start before the first prospective completed bar, with explicit sensitivity assumptions and the existing calendar database:

```powershell
python scripts/run_intraday_paper.py --start --assumptions config/intraday-paper-assumptions.json --calendar-db output/finance-automation.db
python scripts/run_intraday_paper.py --bar path/to/completed-bar.json --assumptions config/intraday-paper-assumptions.json --calendar-db output/finance-automation.db
python scripts/run_intraday_paper.py --start --strategy jev --budget-config path/to/pilot-budget.json --assumptions path/to/assumptions.json --calendar-db output/finance-automation.db
python scripts/run_intraday_paper.py --start --policy-db output/intraday-pilot.db --policy-version candidate-20261007 --assumptions path/to/assumptions.json --calendar-db output/finance-automation.db --review-pilot-db output/intraday-pilot.db
```

`--policy-db` and `--policy-version` are paired: the runner accepts only an explicitly named `candidate` or `active` policy with historical-training provenance and matching execution assumptions. It does not promote that candidate. Its serialized values and a content-fingerprinted strategy ID are frozen into the forward journal so the read-only rebuild can reproduce RL-only or RL+provider decisions. The start response includes that strategy ID; pass it to `python -m stock_research.cli pilot-status --pilot-db output/intraday-pilot.db --forward-db output/intraday-forward.db --strategy-id <strategy-id>` for a later review. `--review-pilot-db` appends the same read-only candidate and forward-paper review to each scheduled session result.

The paper runner remains one fresh-bar invocation by design. The local Breeze collector can now atomically write that handoff through `--paper-bar-output` (also exposed as `-PaperBarOutput` by `start_local_breeze_ingest.ps1`), but only after it has uploaded the matching raw snapshot. It accepts exactly the requested final five-minute NIFBEE/NSE candle and rejects missing, duplicate, mismatched, or invalid OHLCV rows. A scheduler may then invoke the paper command with that path and `--review-pilot-db`; repeated handoffs remain idempotent in the paper journal.

The existing Breeze launcher still requests a fresh interactive session credential, so it is not suitable for unattended scheduling. A credential-refresh design and a concrete scheduler identity must be independently reviewed before scheduling the collector; do not bypass that gate by persisting the session token.

The assumptions JSON contains `fee_bps`, `minimum_fee_inr`, `slippage_bps`, `decision_latency_seconds` and `participation_rate`. These are declared simulation inputs, not verified ICICI tariffs. A positive declared latency is required; a response arriving later than that bound abstains. A 180-second bound accommodates the admitted 120-second bar age and bounded provider calls, but actual observations must validate operational latency.

The runner reuses `load_calendar`, `official_url` and `session_times`. It retains each admission calendar; special sessions unsupported by the engine fail closed. Calendar amendment completeness is still a qualification gap. Bars must be timezone-aware, finite and complete, fresh within 120 seconds and completed after persisted start. Historical CSV supplied with `--warmup` only warms indicators and cannot create trades/decisions before start. Without warmup, the first 35 observations warm indicators. Missing bars block engine entries while deterministic position protections continue against admitted fresh bars.

Frozen configuration, original observations and decision inputs are persisted in SQLite. Run starts and bars record whether the runner used its system clock or an injected test clock; older rows migrate as `unknown`. Full-prefix `replay(..., decide=cached_decide, terminal=False)` rebuilds cash/risk/pending decisions using cached callbacks. Completed trades have unique hashes; repeated bars return the existing summary, conflicting revisions fail, and changed strategy/assumptions/warmup cannot resume the same run. The engine's read-only forward audit rejects injected/unknown clocks and reconstructs exact decisions and completed trades before counting complete sessions. It is still an internal simulation consistency check; prospective source verification and actual execution assumptions remain open. A separate usage-ledger database is required for paid adapters while the paper database holds its rebuild transaction. Engine checkpoints describe simulated state, not broker reconciliation.

This is a restart-safe paper-runner foundation, not an independently qualified execution service. Forward summaries remain `qualified=false`; no 30-session gate, active-policy promotion, post-close candidate scheduler, collector credential automation, billing feed or cloud deployment is claimed. Run no real orders from this module.

## 2026-10-16 operational integration status

`scripts/run_paper_session.py` now consumes the collector's one-file atomic handoff, invokes the existing runner once, serializes overlapping consumers with a local exclusive lock, retains failed input for retry, and archives only a successful delivery under `processed/`. It writes `output/paper-operation/latest.json` with `waiting`, `processed`, or `blocked`; Windows Task Scheduler records nonzero blocked exits. The consumer never creates a run from a missing handoff and never turns a historical bar into prospective evidence.

`scripts/register_paper_tasks.ps1 -RunId <session-specific-id>` prepares three local weekday tasks: a 09:10 immutable run start, a 09:20–15:30 five-minute consumer, and a 15:45 read-only `pilot-status` review. Add `-PolicyVersion <candidate-or-active-version>` only to attach an explicitly selected frozen policy; omission keeps the rules baseline. Pass `-PythonPath <interpreter>` if `python` is not on `PATH`. `-WhatIf` previews the task registration without creating tasks. It does not register a collector, candidate trainer, provider call, or policy promotion. Breeze session bootstrap remains an owner-operated local prompt, so multiday unattended collection is deliberately unavailable until a supported refresh method is evidenced.

| State | Evidence on 2026-10-16 |
| --- | --- |
| Implemented | Local handoff consumer, lock/retry/archive behavior, runner `.env` loading with process values taking priority, and task-registration script. |
| Tested offline | All 5 consumer waiting/success/restart/failure/overlap/policy-forwarding tests passed on 2026-10-16; all 21 engine chronology/risk/reward/frozen-policy tests also passed. `register_paper_tasks.ps1 -WhatIf` produced the explicit policy-aware commands without Task Scheduler access. |
| Authenticated | Read-only `GET https://openrouter.ai/api/v1/key` accepted the configured `.env` key on 2026-10-16. It reported free-tier status, zero current usage, and a USD3 key limit with USD3 remaining. The secret was neither logged nor stored. The current Decisions catalogue listed `typesafe/jev-1.13`, a 262,144-token context, and USD0.000000042 prompt-token pricing. One bounded typed smoke with `rules_action=ABSTAIN` returned a valid `ABSTAIN`, resolved `typesafe/jev-1.13-20260917`, and reported 412 input/50 output tokens at USD0.000017304. A subsequent key read remained rounded to zero usage and USD3 remaining. This was not a paper decision and did not reach the engine. Nova remains unverified: no AWS credential variables or readable AWS profile are configured, `aws` is absent from `PATH`, and no project Python environment provides `boto3`. |
| Deployed | No task was registered, no AWS resource was provisioned, and no cloud deployment occurred. |
| Continuously observed | No prospective completed bar, session, trade, provider decision, or scheduled task history exists. |

The key metadata, public catalogue, and bounded smoke establish OpenRouter access and the resolved Jev identity, but not the required Jev budget evidence. Paper-provider decisions remain blocked until a dated USD/INR source and the required current `infra`, `storage`, and `jev:2026-10` reconciliations are retained in the secret-free budget configuration.

The bundled interpreter lacks optional `certifi` and `boto3`. The Breeze transport now uses Python's verified platform trust store when `certifi` is unavailable, while retaining `BREEZE_CA_BUNDLE` support for a trusted inspection CA; this permits its offline HTTP/TLS checks. The actual Nova runtime remains unavailable. The provider probe mock supplies isolated `boto3`/`botocore` doubles, and all 19 provider/paper tests pass without those packages. This is test coverage for the contract, not evidence of Bedrock connectivity or access. Use a Python environment with the declared optional AWS dependencies for a runtime smoke.

## Authenticated AWS evidence — 2026-10-16

The local AWS CLI v2.38.1 session authenticated successfully with the project-managed role. A read-only `freetier get-account-plan-state` result reports `FREE` / `ACTIVE`, USD 108.21 remaining credits, and expiry `2027-04-02T13:25:02.518000+00:00`. This replaces the older USD 115.57 and USD 117.44 snapshots; it is an evidence input, not an application spend cap.

In `ap-southeast-2`, the Bedrock catalogue lists `amazon.nova-lite-v1:0` with `ON_DEMAND` and `INFERENCE_PROFILE` support. Cost Explorer returned estimated 2026-10-01 through 2026-10-16 unblended cost of USD `-0.0000004645`. No model runtime request, Jev request, IAM simulation, infrastructure change, task registration, or deployment was made. Catalogue access does not establish a successful Bedrock runtime invocation; daily price, FX, Jev snapshot and billing-reconciliation evidence remain required before paid decisions.
